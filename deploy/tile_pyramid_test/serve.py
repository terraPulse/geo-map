'''PNG-pyramid view math for the isolated test Lambda.

This module never imports gio, GDAL, or the legacy source-raster handler.
A missing PNG stays a transparent tile.
'''

import math

from tile_runtime import child_sample_window, nearest_stored_level

TILE_PX = 256


def rrow(level, row, merge=1):
    '''Same far-edge conversion as util/lib/map_tile.py rrow.'''
    if row > 0:
        raise ValueError('rrow expects a non-positive row')
    return (2 ** level) + row - int(merge)


def file_index_from_zxy(level, zx, zy, merge=1):
    return int(zx), rrow(level, -int(zy), merge)


def zxy_from_file_index(level, x, y, merge=1):
    return int(x), rrow(level, -int(y), merge)


def block_window(level, x, y, merge):
    '''File origin and pixel box for one view tile inside a merged PNG.

    x and y are zx_y file indexes. The box matches tile_merge.make_box for a
    merge=1 request against a stored block of `merge` tiles. Pixel (0, 0) is
    the north-west of the block: larger file-row indexes sit toward y=0.
    '''
    merge = int(merge)
    if merge < 1:
        raise ValueError('tile_merge')
    if merge == 1:
        return int(x), int(y), (0, 0, TILE_PX, TILE_PX)

    zx = int(x)
    zy = rrow(level, -int(y), 1)
    origin_x = (zx // merge) * merge
    flipped = rrow(level, -zy, merge)
    snapped = int(math.ceil(flipped / float(merge)) * merge)
    origin_y = rrow(level, -snapped, merge)
    file_x = origin_x
    file_y = rrow(level, -origin_y, merge)
    x1 = max(origin_x, zx)
    y1 = max(origin_y, zy)
    x2 = min(origin_x + merge, zx + 1)
    y2 = min(origin_y + merge, zy + 1)
    box = (
        (x1 - origin_x) * TILE_PX,
        (y1 - origin_y) * TILE_PX,
        (x2 - origin_x) * TILE_PX,
        (y2 - origin_y) * TILE_PX,
    )
    return file_x, file_y, box


def in_pyramid(level, x, y, max_zoom):
    if level < 0 or level > max_zoom:
        return False
    span = 2 ** level
    return 0 <= x < span and 0 <= y < span


def stored_object_rel(layer, level, x, y):
    prefix = layer['key_prefix'].strip('/')
    if int(layer.get('version', 2)) < 2:
        tail = '%s/%s/%s.png' % (level, x, y)
    else:
        tail = 'tiles/%s/%s/%s.png' % (level, x, y)
    if prefix:
        return prefix + '/' + tail
    return tail


def _as_image(raw):
    import io
    from PIL import Image
    if not raw:
        return None
    image = Image.open(io.BytesIO(raw))
    image.load()
    return image


def view_png_from_block(layer, raw, level, x, y):
    '''Crop a 256px view tile from one stored block PNG. None if it does not fit.'''
    image = _as_image(raw)
    if image is None:
        return None
    _file_x, _file_y, box = block_window(level, x, y, layer['tile_merge'])
    width, height = image.size
    if box[2] > width or box[3] > height or box[0] < 0 or box[1] < 0:
        return None
    crop = image.crop(box)
    if crop.size != (TILE_PX, TILE_PX):
        crop = crop.resize((TILE_PX, TILE_PX), resample=image.Resampling.NEAREST)
    return crop


def zoomin_view(parent, level, x, y, source_level):
    '''NEAREST resample matching interpo.zoomin for a merge=1 view tile.'''
    from PIL import Image
    zx, zy = zxy_from_file_index(level, x, y, 1)
    spec = child_sample_window(zx, zy, level, source_level, 1)
    if spec is None or parent is None:
        return None
    box = tuple(int(v) for v in spec['box'])
    crop = parent.crop(box)
    return crop.resize((TILE_PX, TILE_PX), resample=Image.Resampling.NEAREST)


def zoomout_source_zxy(level, x, y, source_level):
    '''The single finer zxy tile historical interpo.zoomout reads.'''
    zx, zy = zxy_from_file_index(level, x, y, 1)
    span = 2 ** (source_level - level)
    return zx * span, zy * span


def select_source_level(level, processed_levels):
    if level in processed_levels:
        return level, 'stored'
    source = nearest_stored_level(level, processed_levels)
    if source is None:
        return None, 'nodata'
    if source < level:
        return source, 'zoomin'
    if source == level:
        return source, 'stored'
    return source, 'zoomout'
