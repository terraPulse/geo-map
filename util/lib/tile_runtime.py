'''
Shared tile-view helpers.

Viewing tiles are cut from pregenerated PNG blocks. These helpers keep that
path free of source-raster reads, bound in-process cache memory, and reject
path inputs that would escape the layer prefix.

The cache is process-local. It does not open S3 clients; callers supply the
read. GEOMAP_TILE_CACHE_BYTES=0 disables storage. GEOMAP_VIEW_SOURCE_RENDER=1
restores on-demand source rendering for layers that publish processed_levels.
'''

import hashlib
import os
import tempfile
import threading
import time
from collections import OrderedDict

MAX_ZOOM = 30
MAX_TAG_LEN = 512
MAX_PATH_LEN = 1024

_DEFAULT_CACHE_BYTES = 64 * 1024 * 1024
_DEFAULT_CACHE_ITEMS = 8
_DEFAULT_CACHE_TTL = 300.0


def source_render_forced():
    return os.environ.get('GEOMAP_VIEW_SOURCE_RENDER', '') == '1'


def is_safe_layer_tag(tag):
    '''Layer ids are relative prefixes such as lincoln/water/y2025.'''
    if not isinstance(tag, str) or not tag or len(tag) > MAX_TAG_LEN:
        return False
    if '\x00' in tag or '\\' in tag or tag.startswith('/'):
        return False
    for part in tag.split('/'):
        if part in ('', '.', '..'):
            return False
    return True


def is_safe_relative_path(rel):
    '''Reject absolute paths and parent segments before os.path.join.'''
    if not isinstance(rel, str) or not rel or len(rel) > MAX_PATH_LEN:
        return False
    if '\x00' in rel or '\\' in rel or rel.startswith('/') or rel.startswith('s3:'):
        return False
    for part in rel.split('/'):
        if part in ('', '.', '..'):
            return False
    return True


def safe_child_path(root, rel):
    if not isinstance(root, str) or not root:
        return None
    if os.path.isabs(rel or ''):
        return None
    if not is_safe_relative_path(rel):
        return None
    return os.path.join(root, rel)


def normalize_loc(value, level, reverse=False):
    '''Match map_tile_parse._normalize_loc, including the zero-index quirk.'''
    if level < 0 or level > MAX_ZOOM:
        return None
    parsed = int(str(value).replace('_', '-'))
    if reverse:
        parsed = parsed * -1
    if parsed >= 0:
        return parsed
    return (2 ** level) + parsed - 1


def normalize_service_path(path, order):
    '''Service URL normalizer for zx_y, zxy, and xyz.

    Numeric rules match the historical parser. Unsafe tags and zoom levels
    above MAX_ZOOM are rejected instead of being joined onto the tile root.
    '''
    import re

    if not isinstance(path, str) or not path or len(path) > MAX_PATH_LEN:
        return None
    match = re.search(r'^(.+)/(\d+)/([_\-]?\d+)/([_\-]?\d+)(.png)$', path)
    if match is None:
        return None

    tag = match.group(1)
    if not is_safe_layer_tag(tag):
        return None

    if order == 'zx_y':
        level = int(match.group(2))
        col = normalize_loc(match.group(3), level, False)
        row = normalize_loc(match.group(4), level, False)
    elif order == 'zxy':
        level = int(match.group(2))
        col = normalize_loc(match.group(3), level, False)
        row = normalize_loc(match.group(4), level, True)
    elif order == 'xyz':
        level = int(match.group(4))
        col = normalize_loc(match.group(2), level, False)
        row = normalize_loc(match.group(3), level, True)
    else:
        raise Exception('unsupported order request %' % order)

    if level < 0 or level > MAX_ZOOM or col is None or row is None:
        return None
    return '%s/%s/%s/%s%s' % (tag, level, col, row, match.group(5))


def view_miss_action(building_tiles, has_block_levels, below_dynamic_floor,
                     force_source_render=False):
    '''Decide what a missing PNG means.

    Pregeneration (building_tiles) still renders from the source raster.
    A layer with processed_levels is a block layer: a view miss stays a
    transparent PNG and does not open the source raster. Legacy layers
    without processed_levels keep on-demand rendering above the dynamic floor.
    '''
    if building_tiles:
        return 'render_source'
    if has_block_levels and not force_source_render:
        return 'nodata'
    if below_dynamic_floor:
        return 'nodata'
    return 'render_source'


def nearest_stored_level(request_z, levels):
    '''Prefer the nearest coarser pregenerated level, then any nearer level.

    A single candidate is that candidate. The previous parser returned
    levels[0] whenever the candidate list had length 1, which ignored a
    coarser level that was not stored first.
    '''
    if not levels:
        return None
    chosen = [(level, request_z - level) for level in levels if request_z > level]
    if not chosen:
        chosen = [(level, abs(level - request_z)) for level in levels]
    if len(chosen) == 1:
        return chosen[0][0]
    chosen.sort(key=lambda item: item[1])
    return chosen[0][0]


def child_sample_window(dst_x, dst_y, dst_z, src_z, dst_merge):
    '''Crop window used to resample a finer view tile from a coarser PNG.

    The arithmetic is the historical zoomin() path, including true division.
    '''
    level_delta = dst_z - src_z
    if level_delta <= 0:
        return None
    span = 2 ** level_delta
    parent_merge = max(1, dst_merge / span)
    pixel_span = int(max(1, (parent_merge * 256) / span))
    offset_x = dst_x % span
    offset_y = dst_y % span
    return {
        'parent_x': int(dst_x / span),
        'parent_y': int(dst_y / span),
        'parent_merge': parent_merge,
        'box': (
            offset_x * pixel_span,
            offset_y * pixel_span,
            (offset_x + 1) * pixel_span,
            (offset_y + 1) * pixel_span,
        ),
        'size': (dst_merge * 256, dst_merge * 256),
    }


def apply_region_mask(data, mask, nodata):
    '''Apply a polygon mask in place.

    Single-band rasters take the nodata value outside the mask. Four-band
    images keep interior alpha and clear alpha outside the mask. The mask
    value 1 is inside.
    '''
    if getattr(data, 'ndim', None) == 2:
        if nodata is None:
            raise Exception('nodata needs to be set for the input raster')
        data[mask != 1] = nodata
        return data
    if getattr(data, 'ndim', None) == 3:
        if data.shape[0] != 4:
            raise Exception('no transparency band provided')
        data[3, :, :][mask != 1] = 0
        return data
    raise Exception('failed to recognize the image type')


def durable_cache_dir():
    path = os.environ.get('GEOMAP_GDAL_CACHE') or os.path.join(
        tempfile.gettempdir(), 'geomap-gdal-cache')
    os.makedirs(path, exist_ok=True)
    return path


def ensure_process_cache_dir(read_current, write_dir):
    '''Publish one durable gio cache directory for this process.

    A request-scoped temp directory was stored in the global config and then
    deleted when the request finished, so later renders kept a dead path.
    '''
    current = read_current()
    if current:
        return current
    with _DIR_LOCK:
        current = read_current()
        if current:
            return current
        path = durable_cache_dir()
        write_dir(path)
        return path


def materialize_bytes(key, data, suffix):
    '''Write cached setting bytes to a stable local file for gio.obj.load.'''
    if isinstance(data, str):
        data = data.encode('utf-8')
    directory = os.path.join(tempfile.gettempdir(), 'geomap-settings')
    os.makedirs(directory, exist_ok=True)
    name = hashlib.sha256(key.encode('utf-8')).hexdigest() + suffix
    final = os.path.join(directory, name)
    temporary = final + '.tmp'
    with open(temporary, 'wb') as handle:
        handle.write(data)
    os.replace(temporary, final)
    return final


class _Gate:
    def __init__(self):
        self.event = threading.Event()
        self.data = None
        self.finished = False
        self.error = None


class TileCache:
    '''Bounded TTL cache for PNG bytes and decoded images.

    One in-flight loader runs per key. Waiters reuse that result, including a
    miss, so a burst of view requests does not each open the same object.
    Misses are not stored after the burst; the next request checks again.
    '''

    def __init__(self, max_bytes=_DEFAULT_CACHE_BYTES, max_items=_DEFAULT_CACHE_ITEMS,
                 ttl=_DEFAULT_CACHE_TTL):
        self.max_bytes = int(max_bytes)
        self.max_items = int(max_items)
        self.ttl = float(ttl)
        self._lock = threading.RLock()
        self._bytes = OrderedDict()
        self._images = OrderedDict()
        self._inflight = {}
        self._stored_bytes = 0
        self.stats = {
            'byte_hits': 0,
            'remote_stat': 0,
            'remote_get': 0,
            'remote_bytes': 0,
            'decode_calls': 0,
            'decode_seconds': 0.0,
            'resample_calls': 0,
            'resample_seconds': 0.0,
            'image_hits': 0,
            'image_stores': 0,
        }

    def note_stat(self):
        with self._lock:
            self.stats['remote_stat'] += 1

    def note_get(self, nbytes):
        with self._lock:
            self.stats['remote_get'] += 1
            self.stats['remote_bytes'] += int(nbytes)

    def record_resample(self, seconds):
        with self._lock:
            self.stats['resample_calls'] += 1
            self.stats['resample_seconds'] += float(seconds)

    def get_bytes(self, key):
        with self._lock:
            hit = self._peek_bytes(key)
            if hit is None:
                return None
            self.stats['byte_hits'] += 1
            return hit

    def put_bytes(self, key, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        with self._lock:
            self._store_bytes(key, data)

    def invalidate(self, key):
        with self._lock:
            self._drop_bytes(key)
            self._drop_image(key)

    def get_or_load_bytes(self, key, loader):
        with self._lock:
            hit = self._peek_bytes(key)
            if hit is not None:
                self.stats['byte_hits'] += 1
                return hit
            gate = self._inflight.get(key)
            if gate is None:
                gate = _Gate()
                self._inflight[key] = gate
                leader = True
            else:
                leader = False
        if not leader:
            gate.event.wait()
            with self._lock:
                if gate.error is not None:
                    raise gate.error
                hit = self._peek_bytes(key)
                if hit is not None:
                    self.stats['byte_hits'] += 1
                    return hit
                if gate.finished:
                    return gate.data
            return self.get_or_load_bytes(key, loader)
        try:
            data = loader()
            if isinstance(data, str):
                data = data.encode('utf-8')
            if data is not None:
                self.put_bytes(key, data)
            gate.data = data
            gate.finished = True
            return data
        except BaseException as exc:
            gate.error = exc
            gate.finished = True
            raise
        finally:
            gate.event.set()
            with self._lock:
                if self._inflight.get(key) is gate:
                    self._inflight.pop(key, None)

    def crop_png(self, key, data, box):
        '''Decode a cached PNG at most once, then crop.

        The decoded image is kept only when `data` is the cached byte object
        for `key`. Generated nodata placeholders are decoded and dropped.
        '''
        if data is None:
            return None
        if isinstance(data, str):
            data = data.encode('utf-8')
        from PIL import Image
        import io

        with self._lock:
            cached = self._peek_bytes(key)
            image = self._peek_image(key) if cached is data else None
            if image is not None:
                self.stats['image_hits'] += 1
            else:
                started = time.perf_counter()
                image = Image.open(io.BytesIO(data))
                image.load()
                self.stats['decode_calls'] += 1
                self.stats['decode_seconds'] += time.perf_counter() - started
                if cached is data:
                    self._store_image(key, image)
            started = time.perf_counter()
            cropped = image.crop(box)
            self.stats['resample_calls'] += 1
            self.stats['resample_seconds'] += time.perf_counter() - started
            return cropped

    def snapshot(self):
        with self._lock:
            out = dict(self.stats)
            out['stored_bytes'] = self._stored_bytes
            out['byte_entries'] = len(self._bytes)
            out['image_entries'] = len(self._images)
            return out

    def _peek_bytes(self, key):
        item = self._bytes.get(key)
        if item is None:
            return None
        data, expires, _size = item
        if expires < time.monotonic():
            self._drop_bytes(key)
            self._drop_image(key)
            return None
        self._bytes.move_to_end(key)
        return data

    def _peek_image(self, key):
        item = self._images.get(key)
        if item is None:
            return None
        image, expires, _size = item
        if expires < time.monotonic():
            self._drop_image(key)
            return None
        self._images.move_to_end(key)
        return image

    def _store_bytes(self, key, data):
        if self.max_bytes <= 0 or self.max_items <= 0:
            return
        self._drop_bytes(key)
        size = len(data)
        if size > self.max_bytes:
            return
        self._bytes[key] = (data, time.monotonic() + self.ttl, size)
        self._stored_bytes += size
        self._evict()

    def _store_image(self, key, image):
        if self.max_bytes <= 0 or self.max_items <= 0:
            return
        self._drop_image(key)
        size = image_nbytes(image)
        if size > self.max_bytes:
            return
        self._images[key] = (image, time.monotonic() + self.ttl, size)
        self._stored_bytes += size
        self.stats['image_stores'] += 1
        self._evict()

    def _drop_bytes(self, key):
        item = self._bytes.pop(key, None)
        if item is not None:
            self._stored_bytes -= item[2]

    def _drop_image(self, key):
        item = self._images.pop(key, None)
        if item is not None:
            self._stored_bytes -= item[2]

    def _evict(self):
        while self.max_items and len(self._bytes) > self.max_items:
            key = next(iter(self._bytes))
            self._drop_bytes(key)
            self._drop_image(key)
        while self._stored_bytes > self.max_bytes and (self._images or self._bytes):
            if self._images:
                self._drop_image(next(iter(self._images)))
                continue
            self._drop_bytes(next(iter(self._bytes)))


def image_nbytes(image):
    width, height = image.size
    return int(width) * int(height) * len(image.getbands())


_DIR_LOCK = threading.Lock()
_CACHE = None
_CACHE_LOCK = threading.Lock()


def get_cache():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    with _CACHE_LOCK:
        if _CACHE is None:
            _CACHE = TileCache(
                max_bytes=_env_int('GEOMAP_TILE_CACHE_BYTES', _DEFAULT_CACHE_BYTES),
                max_items=_env_int('GEOMAP_TILE_CACHE_ITEMS', _DEFAULT_CACHE_ITEMS),
                ttl=_env_float('GEOMAP_TILE_CACHE_TTL', _DEFAULT_CACHE_TTL),
            )
        return _CACHE


def reset_cache():
    '''Test hook. Re-read cache limits from the environment.'''
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = None


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == '':
        return default
    return int(raw)


def _env_float(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == '':
        return default
    return float(raw)
