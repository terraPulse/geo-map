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
        from gio import obj

        _out = os.path.join(config.get('general', 'map_path'), tag)

        _f_ini = file_mag.get(os.path.join(_out, 'setting.ini')).get()
        if _f_ini:
            _met = obj.load(_f_ini)
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
    _v = int(v.replace('_', '-'))
    
    if reverse:
        _v = _v * -1
        
    if _v >= 0:
        return _v
    
    return (2 ** lev) + _v - 1

def _normalize_path(p, order):
    import re
    _m = re.search('^(.+)\/(\d+)\/([_\-]?\d+)\/([_\-]?\d+)(.png)$', p)
    if not _m:
        return None

    _tag = _m.group(1)
    
    if order == 'zx_y':
        _lev = int(_m.group(2))
        _col = _normalize_loc(_m.group(3), _lev)
        _row = _normalize_loc(_m.group(4), _lev)
    elif order == 'zxy':
        _lev = int(_m.group(2))
        _col = _normalize_loc(_m.group(3), _lev)
        _row = _normalize_loc(_m.group(4), _lev, reverse=True)
    elif order == 'xyz':
        _lev = int(_m.group(4))
        _col = _normalize_loc(_m.group(2), _lev)
        _row = _normalize_loc(_m.group(3), _lev, reverse=True)
    else:
        raise Exception('unsupported order request %' % order)

    return '%s/%s/%s/%s%s' % (_tag, _lev, _col, _row, _m.group(5))

def nodata_image(size):
    import PIL.Image
    import io

    _im = PIL.Image.new(mode = "RGBA", size = (size, size),
                       color = (0, 0, 0, 0))

    _io = io.BytesIO()
    _im.save(_io, format='PNG')
    return _io.getvalue()
        
def get(path, tile_order='zx_y', merge=1):
    import os

    _path = path
    if not _path:
        _path = '/'

    _path = _normalize_path(path, tile_order)
    if not _path:
        from gio import config
        from gio import file_mag

        _f = file_mag.get(os.path.join(config.get('general', 'map_path'), path))
        if _f.exists():
            with open(_f.get(), 'rb') as _fi:
                return _fi.read()
        return None
    
    _pss = _parse_url(_path)
    if _pss is None:
        return None
        
    _pss['merge'] = merge
    _out = map_tile_util().get(**_pss)

    logging.debug('output %s, %s' % (_path, len(_out) if _out is not None else '<None>'))
    return _out