'''Isolated TEST Lambda for PNG-pyramid viewing.

Handler: handler.lambda_handler
Runtime target: python3.12 on x86_64. boto3 is the Lambda runtime's client.
Pillow decodes PNGs. tile_runtime supplies the shared cache and zoomin math.

This module does not import gio, GDAL, Cython, or lambda/handler.py.
GEOMAP_VIEW_SOURCE_RENDER is ignored. A miss is a transparent PNG.
'''

import base64
import hmac
import json
import os

from registry import ADAPTER, ADAPTER_VERSION, RegistryError, public_layer, validate_registry
from serve import (
    TILE_PX,
    file_index_from_zxy,
    in_pyramid,
    select_source_level,
    stored_object_rel,
    zoomin_view,
    zoomout_source_zxy,
)
from tile_runtime import MAX_ZOOM, is_safe_relative_path, normalize_service_path

API_PREFIX = '/tiletest/v1'
_REGISTRY = None
_PACKAGE = None
_S3 = None


class RequestError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def lambda_handler(event, context):
    if not isinstance(event, dict):
        return _json(400, 'missing request', {})
    method = _method(event)
    try:
        if method == 'OPTIONS':
            return _options(event)
        if method not in ('GET', 'HEAD'):
            return _json(405, 'method not allowed', event)
        _authorize(event)
        path = _path(event)
        if path == API_PREFIX or path == API_PREFIX + '/':
            return _json_body(200, _service_document(), event)
        if path == API_PREFIX + '/layers':
            return _json_body(200, _layers_document(), event)
        if path.startswith(API_PREFIX + '/layers/'):
            ident = path[len(API_PREFIX + '/layers/'):]
            return _json_body(200, _one_layer(ident), event)
        if path.startswith(API_PREFIX + '/'):
            raw, kind = _tile(path[len(API_PREFIX) + 1:])
            return _png(raw, kind, event, method == 'HEAD')
        return _json(404, 'not found', event)
    except RequestError as exc:
        return _json(exc.status, exc.message, event)
    except RegistryError as exc:
        return _json(500, 'registry rejected: %s' % exc, event)


def _tile(rest):
    order, legacy = _split_order(rest)
    if order == 'map':
        order = 'zx_y'
    try:
        normalized = normalize_service_path(legacy, order)
    except Exception:
        raise RequestError(400, 'invalid tile path')
    if not normalized or not normalized.endswith('.png'):
        raise RequestError(400, 'invalid tile path')
    parts = normalized[:-4].split('/')
    if len(parts) < 4:
        raise RequestError(400, 'invalid tile path')
    try:
        level = int(parts[-3])
        x = int(parts[-2])
        y = int(parts[-1])
    except ValueError:
        raise RequestError(400, 'invalid tile path')
    ident = '/'.join(parts[:-3])
    layer = _registry()['layers'].get(ident)
    if layer is None:
        raise RequestError(403, 'layer is not in the test allowlist')
    limit = min(layer['max_zoom'], MAX_ZOOM)
    if not in_pyramid(level, x, y, limit):
        raise RequestError(400, 'tile index is out of range')
    image, kind = _render(layer, level, x, y)
    import io
    handle = io.BytesIO()
    image.save(handle, format='PNG')
    return handle.getvalue(), kind


def _render(layer, level, x, y):
    from PIL import Image
    source, mode = select_source_level(level, layer['processed_levels'])
    if mode == 'nodata' or source is None:
        return _empty(), 'nodata'
    if mode == 'stored':
        view = _load_view(layer, level, x, y)
        if view is None:
            return _empty(), 'nodata'
        return view, 'tile'
    if mode == 'zoomin':
        parent = _parent_view(layer, level, x, y, source)
        if parent is None:
            return _empty(), 'nodata'
        view = zoomin_view(parent, level, x, y, source)
        if view is None:
            return _empty(), 'nodata'
        return view, 'tile'
    zx, zy = zoomout_source_zxy(level, x, y, source)
    fx, fy = file_index_from_zxy(source, zx, zy, 1)
    if not in_pyramid(source, fx, fy, layer['max_zoom']):
        return _empty(), 'nodata'
    parent = _load_view(layer, source, fx, fy)
    if parent is None:
        return _empty(), 'nodata'
    return parent.resize((TILE_PX, TILE_PX), resample=Image.Resampling.BICUBIC), 'tile'


def _parent_view(layer, level, x, y, source):
    from serve import zxy_from_file_index
    from tile_runtime import child_sample_window
    zx, zy = zxy_from_file_index(level, x, y, 1)
    spec = child_sample_window(zx, zy, level, source, 1)
    if spec is None:
        return None
    fx, fy = file_index_from_zxy(source, int(spec['parent_x']), int(spec['parent_y']), 1)
    if not in_pyramid(source, fx, fy, layer['max_zoom']):
        return None
    return _load_view(layer, source, fx, fy)


def _load_view(layer, level, x, y):
    from tile_runtime import get_cache
    file_x, file_y, box = _block_origin(layer, level, x, y)
    relative = stored_object_rel(layer, level, file_x, file_y)
    prefix = layer['key_prefix'] + '/'
    if not is_safe_relative_path(relative) or not relative.startswith(prefix):
        raise RequestError(403, 'layer key escaped its prefix')
    cache_key, raw = _reader(layer).get_bytes(relative)
    if not raw:
        return None
    try:
        image = get_cache().crop_png(cache_key, raw, box)
    except Exception:
        return None
    if image is None or image.size != (TILE_PX, TILE_PX):
        return None
    return image


def _block_origin(layer, level, x, y):
    from serve import block_window
    return block_window(level, x, y, layer['tile_merge'])


def _reader(layer):
    if layer['storage'] == 'package':
        return _package_reader()
    bucket = os.environ.get('TILE_BUCKET', '').strip()
    if not bucket:
        raise RequestError(503, 's3 storage is not configured')
    return _s3_reader(bucket)


def _package_reader():
    global _PACKAGE
    if _PACKAGE is None:
        from reader import PackageReader
        root = os.environ.get('TILE_FIXTURE_ROOT') or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'fixtures')
        _PACKAGE = PackageReader(root)
    return _PACKAGE


def _s3_reader(bucket):
    global _S3
    if _S3 is None or _S3.bucket != bucket:
        from reader import S3Reader
        _S3 = S3Reader(bucket, os.environ.get('TILE_KEY_ROOT', ''))
    return _S3


def _registry():
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY
    raw = os.environ.get('TILE_REGISTRY_JSON')
    if raw:
        document = json.loads(raw)
    else:
        path = os.environ.get('TILE_REGISTRY_PATH') or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'registry.json')
        with open(path, 'r', encoding='utf-8') as handle:
            document = json.load(handle)
    _REGISTRY = validate_registry(document)
    return _REGISTRY


def reset_for_tests():
    global _REGISTRY, _PACKAGE, _S3
    _REGISTRY = None
    _PACKAGE = None
    _S3 = None
    from tile_runtime import reset_cache
    reset_cache()


def _split_order(rest):
    if '/' not in rest:
        raise RequestError(400, 'invalid tile path')
    order, legacy = rest.split('/', 1)
    if order not in ('map', 'zx_y', 'zxy', 'xyz'):
        raise RequestError(400, 'invalid tile order')
    return order, legacy


def _authorize(event):
    mode = os.environ.get('TILE_AUTH_MODE', 'iam').strip().lower()
    if mode == 'iam':
        return
    if mode != 'header':
        raise RequestError(401, 'unauthorized')
    expected = os.environ.get('TILE_AUTH_TOKEN', '')
    if not expected:
        raise RequestError(401, 'unauthorized')
    presented = _header(event, 'x-tile-test-token')
    if not presented or not _same(presented, expected):
        raise RequestError(401, 'unauthorized')


def _same(presented, expected):
    if len(presented) != len(expected):
        return False
    return hmac.compare_digest(presented, expected)


def _service_document():
    return {
        'adapter': ADAPTER,
        'adapter_version': ADAPTER_VERSION,
        'fixture_only_by_default': True,
        'source_raster_reads': False,
        'tile_url_template': API_PREFIX + '/{order}/{layer_id}/{z}/{x}/{y}.png',
        'xyz_tile_url_template': API_PREFIX + '/xyz/{layer_id}/{x}/{y}/{z}.png',
        'orders': ['map', 'zx_y', 'zxy', 'xyz'],
        'layers_url': API_PREFIX + '/layers',
        'binary': {
            'content_type': 'image/png',
            'is_base64_encoded': True,
            'payload_format': 'API Gateway payload 2.0 / Function URL',
        },
        'auth': {
            'default': 'iam',
            'header': 'x-tile-test-token',
        },
    }


def _layers_document():
    layers = [_public(layer) for layer in _registry()['layers'].values()]
    body = _service_document()
    body['layers'] = layers
    return body


def _one_layer(ident):
    layer = _registry()['layers'].get(ident)
    if layer is None:
        raise RequestError(403, 'layer is not in the test allowlist')
    body = _service_document()
    body['layer'] = _public(layer)
    return body


def _public(layer):
    return public_layer(layer, API_PREFIX + '/{order}/' + layer['id'] + '/{z}/{x}/{y}.png')


def _empty():
    from PIL import Image
    return Image.new('RGBA', (TILE_PX, TILE_PX), (0, 0, 0, 0))


def _png(raw, kind, event, head):
    headers = _base_headers(event)
    headers['content-type'] = 'image/png'
    headers['x-geomap-tile'] = kind
    headers['cache-control'] = 'no-store' if kind == 'nodata' else 'public, max-age=60'
    if head:
        return {'statusCode': 200, 'headers': headers, 'isBase64Encoded': False, 'body': ''}
    return {
        'statusCode': 200,
        'headers': headers,
        'isBase64Encoded': True,
        'body': base64.b64encode(raw).decode('ascii'),
    }


def _options(event):
    headers = _cors(event)
    if 'access-control-allow-origin' not in headers and os.environ.get('TILE_CORS_ORIGIN', '').strip():
        return _json(403, 'origin is not allowed', event)
    return {'statusCode': 204, 'headers': headers, 'isBase64Encoded': False, 'body': ''}


def _json(status, message, event):
    return _json_body(status, {
        'status': 'error',
        'error_message': message,
        'adapter': ADAPTER,
        'adapter_version': ADAPTER_VERSION,
    }, event)


def _json_body(status, payload, event):
    headers = _base_headers(event)
    headers['content-type'] = 'application/json'
    return {
        'statusCode': status,
        'headers': headers,
        'isBase64Encoded': False,
        'body': json.dumps(payload),
    }


def _base_headers(event):
    headers = {
        'x-geomap-adapter': ADAPTER,
        'x-geomap-adapter-version': ADAPTER_VERSION,
    }
    headers.update(_cors(event))
    return headers


def _cors(event):
    allowed = os.environ.get('TILE_CORS_ORIGIN', '').strip()
    if not allowed or allowed == '*':
        return {}
    origin = _header(event, 'origin')
    if origin != allowed:
        return {}
    return {
        'access-control-allow-origin': allowed,
        'access-control-allow-methods': 'GET, HEAD, OPTIONS',
        'access-control-allow-headers': 'content-type, x-tile-test-token, authorization',
        'vary': 'Origin',
    }


def _path(event):
    raw = event.get('rawPath')
    if not isinstance(raw, str) or not raw:
        raw = event.get('path')
    if not isinstance(raw, str) or not raw.startswith('/'):
        raise RequestError(400, 'missing path')
    if '?' in raw or raw.startswith('//') or '\\' in raw or '://' in raw:
        raise RequestError(400, 'invalid path')
    if len(raw) > 1024:
        raise RequestError(400, 'invalid path')
    return raw.rstrip('/') if raw != '/' else raw


def _method(event):
    http = event.get('requestContext', {})
    if isinstance(http, dict):
        inner = http.get('http')
        if isinstance(inner, dict) and isinstance(inner.get('method'), str):
            return inner['method'].upper()
    method = event.get('httpMethod')
    if isinstance(method, str):
        return method.upper()
    return 'GET'


def _header(event, name):
    headers = event.get('headers') or {}
    if not isinstance(headers, dict):
        return ''
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == name and isinstance(value, str):
            return value
    return ''
