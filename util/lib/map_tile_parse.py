'''
File: map_tile_parse.py
Author: Min Feng
Description: parse the URL, process and return the output tile
'''

import os
from gio import file_unzip
from gio import file_mag
from gio import config
import logging

_jobs = []
_tods = []

class map_tile:

    def __init__(self):
        from gio import config
        self.min_level = config.getint('conf', 'min_level', 9)

    def _dmap_mag(self, f, f_out):
        from gio import config
        _pro = config.get('general', 'dmap', None)
        if not _pro:
            return

        if len(_jobs) > 50 or f in _jobs:
            logging.warning('exceed 50 tasks (%s)' % len(_jobs))
            return

        _jobs.append(f)
        try:
            return self._dmap(f, f_out)
            # import time
            # time.sleep(2.0)
        finally:
            _jobs.pop()

    def _dmap(self, f, f_out):
        import os
        from gio import config

        _pro = config.get('general', 'dmap')
        _pro = _pro.replace('%[', '%(').replace(']', ')')

        if not _pro:
            return

        if os.path.exists(f):
            return

        import re
        _m = re.search('([^\/]+)\/(\d+)\/(\d+)\/(\d+).png', f)
        _c = _pro % {'tag': _m.group(1), 'level': _m.group(2), 'col': _m.group(3), 'row': _m.group(4)}

        from gio import run_commands
        _rs = run_commands.run(_c)

        logging.debug('create tile: %s (%s)' % (_c, _rs[0]))

        return _rs[0] == 0

    def _dmap_mag_single(self, met):
        try:
            return self._dmap_single(met)
        finally:
            pass
        
    def _load_setting(self, tag, lev, col, row):
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

        _met.lev = lev
        _met.row = row
        _met.col = col
        _met.tag = tag

        return _met

    def _dmap_single(self, met):
        from gio import config
        import os

        _tag = met.tag
        _lev = met.getint('lev')
        _col = met.getint('col')
        _row = met.getint('row')

        _out = os.path.join(config.get('general', 'map_path'), _tag)

        _inp = None
        _agg = None
        _valid_vals = None
        _solid_bg = False
        _mask = None
        _min_level = self.min_level

        logging.info('+ %s (%s, %s, %s, %s)' % (len(_jobs), _tag, _lev, _col, _row))

        if config.cfg.has_section(_tag):
            _inp = config.get(_tag, 'file', '')
            _pec = config.getint(_tag, 'percent', None)
            _clr = config.get(_tag, 'color', None)

        _inp = met.get('file')
        _pec = met.getint('percent')
        _clr = met.get('color')
        _solid_bg = met.get('solid_bg')
        _agg = met.get('agg')

        _valid_vals = met.get('valid_vals')
        _mask = met.get('mask')
        _min_level = met.get('min_dynamic_level', self.min_level)

        if config.getboolean('conf', 'skip_low_levels', True) and _lev < _min_level:
            logging.warning('skip level %s < %s' % (_lev, _min_level))
            return

        if _inp is None:
            return

        if _clr is None:
            _clr = os.path.join(_out, 'color.txt')

        from geo_map_util import map_tile
        map_tile.make_tile(_inp, _lev, _col, _row, _pec, _valid_vals, _solid_bg, _clr, _mask, _out, agg=_agg, opts=met)

    def _split_vars(self, c):
        _vs = c.split('&')
        _ps = {}

        for _v in _vs:
            if '=' in _v:
                _n, _t = _v.split('=')
                _ps[_n] = _t
            else:
                _ps[_v] = None

        return _ps
        
    def _burn(self, f, met):
        import numpy as np
        import io
        from PIL import Image
        
        _load_img = lambda x: np.array(Image.open(x))
        
        _img = _load_img(f)
        if 'burn_band' in met:
            _opts = met.get('burn_band', {})
            _mlev = _opts.getint('level', 1)
            if met.lev >= _mlev:
                _ftag = _opts.get('input')
                _finp = map_tile().get(_ftag, met.lev, met.col, met.row)
                if _finp:
                    _offs = _opts.get('offset', 200)
                    logging.debug('burn band %s, %s' % (_ftag, _offs))
                    _burn_band(_img, _load_img(io.BytesIO(_finp)), _offs)
            
        if 'burn_transparency' in met:
            _opts = met.get('burn_transparency', {})
            _mlev = _opts.getint('level', 1)
            if met.lev >= _mlev:
                _ftag = _opts.get('input')
                _finp = map_tile().get(_ftag, met.lev, met.col, met.row)
                if _finp:
                    logging.debug('burn transparency %s' % (_ftag))
                    _burn_transparency(_img, _load_img(io.BytesIO(_finp)))
        
        return Image.fromarray(_img)

    def _post_proc(self, f, met):
        if not f:
            return None
            
        _f = file_mag.get(f).get()
        if 'burn_band' in met or 'burn_transparency' in met:
            _img = self._burn(_f, met)
            with open(_f, 'wb') as _fo:
                _img.save(_fo, format='PNG')
                
            # if f != _f:
            #     file_mag.get(f).put(_f)
                
            # _buf = io.BytesIO()
            # _img.save(_buf, format='PNG')
            # return _buf.getvalue()
            
        return _f
        
    def _read_file(self, f):
        return file_mag.get(f).read()
        # with open(file_mag.get(f).get(), 'rb') as _fi:
        #     return _fi.read()

    def _nodata_image(self, size):
        import PIL.Image
        import io

        _im = PIL.Image.new(mode = "RGBA", size = (size, size),
                           color = (0, 0, 0, 0))
 
        _io = io.BytesIO()
        _im.save(_io, format='PNG')
        return _io.getvalue()

    def get_image(self, tag, lev, col, row):
        from geo_map_util import map_tile
        
        _met = self._load_setting(tag, lev, col, row)
        _tile = map_tile.tile(lev, col, row, _met.get('tile_merge', 1))
        _d_web = config.get_at('general', 'map_path')

        _out_file = _tile.file(os.path.join(_d_web, _met.tag), _met.get('version', 1.0))
        if _out_file.exists():
            return _out_file.read()
            
        with file_unzip.zip() as _zip:
            _cache = config.get('conf', 'cache', None)
            if not _cache:
                _tmp = _zip.generate_file()
                config.set('conf', 'cache', os.path.join(_tmp, 'cache'))

            self._dmap_mag_single(_met)
            _is_nodata = not _out_file.exists()
            
            # logging.info('existance of the output %s' % _is_nodata)
            # logging.info('keep nodata %s' % config.getboolean('conf', 'keep_nodata_tiles', True))
            if _is_nodata:
                _ooo = self._nodata_image(_met.get('tile_merge', 1) * 256)
                if config.getboolean('conf', 'keep_nodata_tiles', True):
                    _out_file.write(_ooo)
                return _ooo

            _out = str(_out_file)
            _ooo = self._post_proc(_out, _met)
            if _out != _ooo:
                _out_file.put(_ooo)
            
            return self._read_file(_ooo)

        raise Exception('no module found %s' % tag)

    def get(self, tag, lev, col, row):
        _img = self.get_image(tag, lev, col, row)
        if not _img:
            return None
        return _img

def _burn_band(b1, b2, offset=200):
    import numpy as np

    for _b in range(3):
        _o = b1[:, :, _b].astype(np.int16)
        _x = b2[:, :, _b]
        
        _o += _x
        _o -= offset
        
        _o[_o < 0] = 0
        _o[_o > 255] = 255
        
        b1[:, :, _b] = _o.astype(np.uint8)
        
    _a = b1[:, :, 3]
    _a[b2[:, :, 3] == 0] = 0
    b1[:, :, 3] = _a

    return b1

def _burn_transparency(b1, b2):
    import numpy as np
    b1[:, :, 3] = np.minimum(np.minimum(b1[:, :, 3], b2[:, :, 0]), b2[:, :, 3])
    return b1

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
        
def get(path, tile_order='zx_y'):
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
        
    _out = map_tile().get(**_pss)
    logging.debug('output %s, %s' % (_path, len(_out)))
    return _out