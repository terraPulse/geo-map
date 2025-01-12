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

class loc_image:

    def __init__(self, loc, img):
        self.loc = loc
        self.img = img

def rrow(lev, row, merge):
    assert row < 0
    return (2 ** lev) + row - merge

def image_to_bytes(i):
    import io
    _b = io.BytesIO()
    i.save(_b, format='PNG')
    return _b.getvalue()

class tile_r:

    def __init__(self, level, col, row, merge=1):
        self.level = level
        self.col = col
        self.row = row if row > 0 else rrow(level, row, merge)
        self.merge = merge
        
        from geo_map_util import map_tile
        self.tile = map_tile.tile(level, col, rrow(level, -self.row, merge), merge)

    @staticmethod
    def from_tile(tile):
        return tile_r(tile.level, tile.col, rrow(tile.level, -tile.row, tile.merge))

    def __repr__(self):
        return (lambda x: f'{x.level}/{x.col}/{x.row}@{x.merge}')(self)

class tile_merge:

    def tile_union(self, t1, t2):
        return {'x1': max(t1.col, t2.col), 
                'y1': max(t1.row, t2.row), 
                'x2': min(t1.col + t1.merge, t2.col + t2.merge),
                'y2': min(t1.row + t1.merge, t2.row + t2.merge)}
    
    def empty_image(self, merge=1):
        from PIL import Image
        return Image.new('RGBA', (256 * merge, 256 * merge), (0,0,0,0))
    
    def make_box(self, bb, t):
        _sx = t.col
        _sy = t.row
        
        _bx = (bb['x1'] - _sx, bb['y1'] - _sy, bb['x2'] - _sx, bb['y2'] - _sy)
        return [_b * 256 for _b in _bx]
    
    def read_tile(self, tile_src, tile_tar, met, d_inp, tag):
        _bb = self.tile_union(tile_src, tile_tar)
        
        if _bb['x2'] <= _bb['x1'] or _bb['y2'] <= _bb['y1']:
            return None
    
        _sx = _bb['x1'] - tile_tar.col
        _sy = _bb['y1'] - tile_tar.row
        
        _da = map_tile_task().read(met, d_inp, tag, tile_src.level, 
                                   tile_src.tile.col, tile_src.tile.row, tile_src.merge)

        from PIL import Image
        import io

        _ii = Image.open(io.BytesIO(_da))
        return loc_image((_sx * 256, _sy * 256), _ii.crop(self.make_box(_bb, tile_src)))

    def c_col(self, d, merge):
        return int((d // merge) * merge)
    
    def c_row(self, d, merge, level):
        import math
        
        _r = rrow(level, -d, merge)
        _v = int(math.ceil(_r / merge) * merge)
    
        return rrow(level, -_v, merge)

    def read(self, t, merge, met, d_inp, tag):
        _img = self.empty_image(t.merge)

        for _col in range(t.col, t.col + t.merge, merge):
            for _row in range(t.row, t.row + t.merge, merge):
                _z = tile_r(t.level, \
                                   self.c_col(_col, merge), \
                                   self.c_row(_row, merge, t.level), \
                                   merge)

                _i = self.read_tile(_z, t, met, d_inp, tag)
                if not _i:
                    continue
    
                _img.paste(_i.img, _i.loc)
                
        return image_to_bytes(_img)

class map_tile_task:

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
        
    def _burn(self, f, met, merge):
        import numpy as np
        import io
        from PIL import Image
        
        _load_img = lambda x: np.array(Image.open(x))
        
        _img = _load_img(io.BytesIO(f.read()))
        if 'burn_band' in met:
            _opts = met.get('burn_band', {})
            _mlev = _opts.getint('level', 1)
            if met.lev >= _mlev:
                _ftag = _opts.get('input')
                _finp = map_tile_util().get(_ftag, met.lev, met.col, met.row, merge)
                if _finp:
                    _offs = _opts.get('offset', 200)
                    logging.debug('burn band %s, %s' % (_ftag, _offs))
                    _burn_band(_img, _load_img(io.BytesIO(_finp)), _offs)
            
        if 'burn_transparency' in met:
            _opts = met.get('burn_transparency', {})
            _mlev = _opts.getint('level', 1)
            if met.lev >= _mlev:
                _ftag = _opts.get('input')
                _finp = map_tile_util().get(_ftag, met.lev, met.col, met.row, merge)
                if _finp:
                    logging.debug('burn transparency %s' % (_ftag))
                    _burn_transparency(_img, _load_img(io.BytesIO(_finp)))
        
        return Image.fromarray(_img)

    def _post_proc(self, f, met, merge):
        if not f:
            return False
            
        if 'burn_band' in met or 'burn_transparency' in met:
            _img = self._burn(f, met, merge)
            f.write(image_to_bytes(_img))
            return True
            
        return False
        
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

    def read(self, met, d_web, tag, lev, col, row, merge=1):
        from geo_map_util import map_tile
        
        _tile = map_tile.tile(lev, col, row, merge)
        _out_file = _tile.file(os.path.join(d_web, met.tag), met.get('version', 1.0))

        if _out_file.exists():
            return _out_file.read()
            
        self._dmap_mag_single(met)
        
        if not _out_file.exists():
            _ooo = self._nodata_image(merge * 256)
            if config.getboolean('conf', 'keep_nodata_tiles', True):
                _out_file.write(_ooo)
            return _ooo

        self._post_proc(_out_file, met, merge)
        return _out_file.read()

class map_tile_util:

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

    def _get(self, tag, lev, col, row, merge=1):
        _met = self._load_setting(tag, lev, col, row)
        _d_web = config.get_at('general', 'map_path')

        _merge = _met.get('tile_merge', 1)
        if _merge == merge:
            return map_tile_task().read(_met, _d_web, tag, lev, col, row, merge)

        return tile_merge().read(tile_r(lev, col, -row, merge), _merge, _met, _d_web, tag)

    def get(self, tag, lev, col, row, merge=1):
        _img = self._get(tag, lev, col, row, merge)
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
    
    logging.debug('output %s, %s' % (_path, len(_out)))
    return _out