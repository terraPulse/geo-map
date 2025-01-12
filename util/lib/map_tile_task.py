'''
File: map_tile_task.py
Author: Min Feng
Description: execute the task for generating map tiles
'''

import os
from gio import file_unzip
from gio import file_mag
from gio import config
from . import map_tile
import logging

_jobs = []
_tods = []

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

class map_tile_task:

    def __init__(self):
        self.min_level = config.getint('conf', 'min_level', 9)

    def _dmap_mag(self, f, f_out):
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

    def _dmap_mag_single(self, met, tile):
        try:
            return self._dmap_single(met, tile)
        finally:
            pass
        
    def _dmap_single(self, met, tile):
        _tag = met.tag
        
        _lev = tile.level
        _col = tile.col
        _row = tile.row

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

        from . import map_tile_render
        map_tile_render.make_tile(_inp, tile, _pec, _valid_vals, _solid_bg, _clr, _mask, _out, agg=_agg, opts=met)

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

    def read(self, met, d_web, tag, tile):
        _out_file = tile.file(os.path.join(d_web, tag), met.get('version', 1.0))

        if _out_file.exists():
            return _out_file.read()

        self._dmap_mag_single(met, tile)
        
        if not _out_file.exists():
            _ooo = self._nodata_image(tile.merge * 256)
            if config.getboolean('conf', 'keep_nodata_tiles', False):
                _out_file.write(_ooo)
            return _ooo

        self._post_proc(_out_file, met, tile.merge)
        return _out_file.read()
