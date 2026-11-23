'''Allowlist of PNG pyramid layers. Version geomap.png_pyramid 1.0.0.

The request cannot name a bucket or an arbitrary URL. Only ids in this
document are served, and every key stays under that layer's key_prefix.
'''

from tile_runtime import MAX_ZOOM, is_safe_layer_tag, is_safe_relative_path

ADAPTER = 'geomap.png_pyramid'
ADAPTER_VERSION = '1.0.0'
MAX_MERGE = 8
MAX_LAYERS = 32


class RegistryError(ValueError):
    pass


def validate_registry(document):
    if not isinstance(document, dict):
        raise RegistryError('registry must be an object')
    if document.get('adapter') != ADAPTER:
        raise RegistryError('registry adapter is not %s' % ADAPTER)
    if document.get('adapter_version') != ADAPTER_VERSION:
        raise RegistryError('registry adapter_version is not %s' % ADAPTER_VERSION)
    layers = document.get('layers')
    if not isinstance(layers, list) or not layers or len(layers) > MAX_LAYERS:
        raise RegistryError('registry layers must be a non-empty list')
    seen = {}
    for layer in layers:
        parsed = _layer(layer)
        if parsed['id'] in seen:
            raise RegistryError('duplicate layer id')
        seen[parsed['id']] = parsed
    return {
        'adapter': ADAPTER,
        'adapter_version': ADAPTER_VERSION,
        'layers': seen,
    }


def _layer(layer):
    if not isinstance(layer, dict):
        raise RegistryError('layer must be an object')
    if 'bucket' in layer or 'url' in layer or 's3_uri' in layer:
        raise RegistryError('layer records cannot carry a bucket or URL')
    ident = layer.get('id')
    if not is_safe_layer_tag(ident):
        raise RegistryError('layer id is not allowed')
    storage = layer.get('storage')
    if storage not in ('package', 's3'):
        raise RegistryError('layer storage must be package or s3')
    prefix = layer.get('key_prefix')
    if not is_safe_relative_path(prefix):
        raise RegistryError('layer key_prefix is not allowed')
    if prefix.startswith('s3:') or '://' in prefix:
        raise RegistryError('layer key_prefix is not allowed')
    merge = layer.get('tile_merge', 1)
    if not isinstance(merge, int) or isinstance(merge, bool) or not 1 <= merge <= MAX_MERGE:
        raise RegistryError('tile_merge must be an integer from 1 to %s' % MAX_MERGE)
    if layer.get('tile_size', 256) != 256:
        raise RegistryError('tile_size must be 256')
    version = layer.get('version', 2)
    if version not in (1, 2) and not (isinstance(version, float) and version in (1.0, 2.0)):
        raise RegistryError('version must be 1 or 2')
    levels = layer.get('processed_levels')
    if not isinstance(levels, list) or not levels:
        raise RegistryError('processed_levels must be a non-empty list')
    clean_levels = []
    for level in levels:
        if not isinstance(level, int) or isinstance(level, bool) or level < 0 or level > MAX_ZOOM:
            raise RegistryError('processed level is out of range')
        clean_levels.append(level)
    max_zoom = layer.get('max_zoom', MAX_ZOOM)
    if not isinstance(max_zoom, int) or isinstance(max_zoom, bool) or max_zoom < 0 or max_zoom > MAX_ZOOM:
        raise RegistryError('max_zoom is out of range')
    if layer.get('fixture') is True and storage != 'package':
        raise RegistryError('fixture layers must use package storage')
    return {
        'id': ident,
        'title': str(layer.get('title') or ident)[:200],
        'fixture': bool(layer.get('fixture', False)),
        'storage': storage,
        'key_prefix': prefix.strip('/'),
        'version': int(version),
        'tile_size': 256,
        'tile_merge': merge,
        'processed_levels': sorted(set(clean_levels)),
        'max_zoom': max_zoom,
    }


def public_layer(layer, order_note):
    return {
        'id': layer['id'],
        'title': layer['title'],
        'fixture': layer['fixture'],
        'storage': 'package' if layer['storage'] == 'package' else 's3-prefix',
        'tile_merge': layer['tile_merge'],
        'tile_size': 256,
        'version': layer['version'],
        'processed_levels': list(layer['processed_levels']),
        'max_zoom': layer['max_zoom'],
        'tile_path': order_note,
    }
