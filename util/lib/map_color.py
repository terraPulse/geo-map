'''
File: map_color.py
Author: Min Feng
Version: 0.1
Create: 2018-05-17 17:47:48
Description: colorize the map
'''

class color:

    def __init__(self, n, v, c, t):
        self.n = n
        self.v = v
        self.c = c
        self.t = t

    def __lt__(self, o):
        return self.v < o.v

    def __gt__(self, o):
        return self.v > o.v

    def __eq__(self, o):
        return self.v == o.v

    def __nq__(self, o):
        return self.v != o.v

def load_color_file(f):
    from gio import file_mag
    with open(file_mag.get(f).get()) as _fi:
        _ls = _fi.read().strip().splitlines()[2:]

    _cs = {}
    _vs = []
    _n = 0

    for _l in _ls:
        _vv = _l.split(',')
        if len(_vv) != 6:
            continue

        _cc = tuple(map(int, _vv[1:5]))
        _t = _vv[5]

        _vs.append(color(_n, float(_vv[0]), _cc, _t))
        _cs[_n] = _cc
        _ls[_n] = _vv[5]

        _n += 1

    if _n <= 0:
        raise Exception('no color entries found')

    return sorted(_vs), _cs

def colorize(f_inp, f_clr, f_out):
    from gio import geo_raster as ge
    from gio import file_unzip
    import os

    _bnd = ge.open(f_inp).get_band().cache()

    with file_unzip.file_unzip() as _zip:
        _d_tmp = _zip.generate_file()
        os.makedirs(_d_tmp)

        _f_out = os.path.join(_d_tmp, os.path.basename(f_out))
        colorize_band(_bnd, f_clr).save(_f_out, opts=['compress=deflate', 'tiled=yes'])

        file_unzip.compress_folder(_d_tmp, os.path.dirname(f_out), [])

def colorize_band(bnd, f_clr):
    from gio import geo_raster as ge
    import numpy as np

    _vs, _cs = load_color_file(f_clr)

    _bnd = bnd
    _dat = _bnd.data

    _ddd = np.empty((_bnd.height, _bnd.width), dtype=np.uint8)
    _ddd.fill(255)

    _ino = (_dat != _bnd.nodata) if _bnd.nodata is not None else (_dat != -9999)

    for _v in _vs:
        _idx = (_ddd == 255) & (_dat <= _v.v) & _ino
        _ddd[_idx] = _v.n

    if _bnd.nodata is not None:
        _ddd[_ino == False] = 255

    _out = _bnd.from_grid(_ddd, nodata=255)

    _clr = ge.map_colortable(_cs)
    _out.color_table = _clr

    return _out
