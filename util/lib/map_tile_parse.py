'''
File: map_tile_parse.py
Author: Min Feng
Description: parse the URL, process and return the output tile
'''

import os
import logging
from gio import file_unzip
from gio import file_mag
from gio import config
from . import map_tile_task
from . import map_tile_merge
from . import map_tile

class map_tile_util:

    def _load_setting(self, tag, tile):
        import os
        from gio import obj
        from gio import config
        from gio import file_mag
        from .tile_runtime import get_cache, materialize_bytes

        _out = os.path.join(config.get('general', 'map_path'), tag)
        _path = os.path.join(_out, 'setting.ini')
        _key = 'setting:' + _path
        _cache = get_cache()

        def _load():
            _mag = file_mag.get(_path)
            _cache.note_stat()
            if not _mag.exists():
                return None
            _raw = _mag.read()
            if not _raw:
                return None
            if isinstance(_raw, str):
                _raw = _raw.encode('utf-8')
            _cache.note_get(len(_raw))
            return _raw

        _raw = _cache.get_or_load_bytes(_key, _load)
        if _raw:
            _met = obj.load(materialize_bytes(_key, _raw, '.ini'))
        else:
            _met = obj.obj()

        _met.lev = tile.z
        _met.row = tile.y
        _met.col = tile.x
        _met.tag = tag

        return _met

    def load(self, tag, tile):
        from . import map_tile_interpo
        
        _met = self._load_setting(tag, tile)
        _d_web = config.get_at('general', 'map_path')
        _merge = int(_met.get('tile_merge', 1))

        _zxy = map_tile.zxy.from_tile(tile)
        _intp = map_tile_interpo.interpo(tag, _zxy)

        if _intp.enabled() and (tile.z not in _intp.levels()):
            return _intp.interpolate()

        if _merge == tile.merge:
            return map_tile_task.map_tile_task().read(_met, _d_web, tag, tile)

        return map_tile_merge.tile_merge().read(_zxy, _merge, _met, _d_web, tag)

    def get(self, tag, lev, col, row, merge=1):
        _tile = map_tile.tile(lev, col, row, merge)
        _img = self.load(tag, _tile)
        
        if not _img:
            return nodata_image(256 * merge)
        return _img

def _parse_url(f):
    import re

    _m = re.search('^(.+)\/(\d+)\/(\d+)\/(\d+).png$', f)
    if _m is None:
        logging.warning('failed to parse %s' % f)
        return None

    _tag = _m.group(1)
    
    _lev = int(_m.group(2))
    _col = int(_m.group(3))
    _row = int(_m.group(4))
    
    return {'tag': _tag, 'lev': _lev, 'col': _col, 'row': _row}
    
def _normalize_loc(v, lev, reverse=False):
    from .tile_runtime import normalize_loc
    return normalize_loc(v, lev, reverse)

def _normalize_path(p, order):
    from .tile_runtime import normalize_service_path
    return normalize_service_path(p, order)

def nodata_image(size):
    import PIL.Image
    import io

    _im = PIL.Image.new(mode = "RGBA", size = (size, size),
                       color = (0, 0, 0, 0))

    _io = io.BytesIO()
    _im.save(_io, format='PNG')
    return _io.getvalue()
        
def get(path, tile_order='zx_y', merge=1):
    _path = path
    if not _path:
        _path = '/'

    from .tile_runtime import safe_child_path

    _norm = _normalize_path(path, tile_order)
    if not _norm:
        from gio import config
        from gio import file_mag

        _child = safe_child_path(config.get('general', 'map_path'), path)
        if _child is None:
            return None
        _f = file_mag.get(_child)
        if _f.exists():
            with open(_f.get(), 'rb') as _fi:
                return _fi.read()
        return None
    _path = _norm
    
    _pss = _parse_url(_path)
    if _pss is None:
        return None
        
    _pss['merge'] = merge
    _out = map_tile_util().get(**_pss)

    logging.debug('output %s, %s' % (_path, len(_out) if _out is not None else '<None>'))
    return _out