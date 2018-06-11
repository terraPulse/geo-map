#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Author:  Min Feng
Version: 0.1
Create: 2016-12-06
Description: provide functions for generating map tiles
'''

import logging

class tiles:

    def __init__(self):
        import math
        from gio import geo_raster as ge

        self.b = 6378137.0
        self.s = 256
        self.p = self.b * math.pi

        self.prj = ge.proj_from_epsg(3857)

    def list(self, level, ext=None):
        from gio import geo_base as gb

        _r = (2 * self.p) / (2 ** level)

        _rows = 2 ** level
        _cols = 2 ** level

        _num = -1
        for _row in xrange(_rows):
            for _col in xrange(_cols):
                _num += 1

                _x = -self.p + (_col * _r)
                _y = -self.p + (_row * _r)

                _ext = gb.geo_extent(_x, _y, _x + _r, _y + _r, self.prj)
                if ext == None or _ext.is_intersect(ext):
                    yield level, _num, _col, _row

    def extent(self, level, col, row):
        _r = (2 * self.p) / (2 ** level)
        _c = _r / self.s

        _x = -self.p + (col * _r)
        _y = -self.p + (row * _r)

        _geo = [_x, _c, 0, _y + _r, 0, -_c]

        from gio import geo_raster as ge
        return ge.geo_raster_info(_geo, self.s, self.s, self.prj)

def make_tile(f, lev, col, row, percent, vals, solid_bg, f_clr, f_msk, d_out, agg=None, opts={}):
    # from osgeo import gdal
    # gdal.UseExceptions()
    import os

    _d = os.path.join(d_out, str(lev), str(col))

    _f = os.path.join(_d, '%s.png' % row)
    if os.path.exists(_f) and os.path.getsize(_f) > 0:
        logging.debug('skip %s' % _f)
        return

    from gio import file_unzip
    with file_unzip.file_unzip() as _zip:
        try:
            os.path.exists(_d) or os.makedirs(_d)
        except Exception:
            pass

        from gio import config
        _cache = config.get('conf', 'cache', None)
        if not _cache:
            _tmp = _zip.generate_file()
            config.set('conf', 'cache', os.path.join(_tmp, 'cache'))

        _ext = tiles().extent(lev, col, row)

        from gio import geo_base as gb
        _eee = _ext.extent().to_polygon().project_to(gb.modis_projection()).extent()

        from gio import file_mag
        _finp = file_mag.get(f).get()

        logging.debug('generate tile %s' % _f)
        if percent != None:
            band(_finp, lev, _eee, f_msk, solid_bg, opts, _zip).make_perc(_ext, percent, vals, f_clr, _f, agg=agg, \
                    mag=opts.get('mag', None))
        else:
            band(_finp, lev, _eee, f_msk, solid_bg, opts, _zip).make(_ext, f_clr, _f, agg=agg)

class color_table:

    def __init__(self, c):
        self._cs = self._color_table(c)

    @staticmethod
    def load(f, fzip):
        import os

        _ext = os.path.splitext(f.lower())[1]

        _f = f
        if _ext == '.shp':
            _f = color_table.load_sample(f)

        from gio import geo_raster as ge
        _b = ge.open(fzip.unzip(_f)).get_band()

        if _b.color_table == None:
            return None
        else:
            return color_table(_b.color_table)

    def _color_table(self, c):
        _cs = {}
        if c == None:
            return None

        _rg = lambda x: min(max(0, x), 255)

        _c = c
        for i in xrange(_c.GetCount()):
            try:
                _v = _c.GetColorEntry(i)
            except:
                _v = _rg

            if len(_v) == 3:
                _v = list(_v) + [255]

            _cs[i] = map(_rg, _v)

        return _cs

    def save(self, f):
        _ls = []
        for _k, _v in self._cs.items():
            _ls.append('%s %s' % (_k, ','.join(map(str, _v))))

        with open(f, 'w') as _fo:
            _fo.write('\n'.join(_ls))

        return f

    @staticmethod
    def load_sample(f):
        from osgeo import ogr

        _shp = ogr.Open(f)
        if _shp == None:
            raise Exception('Failed to load shapefile ' + f)

        _lyr = _shp.GetLayer()
        for _f in _lyr:
            return _f.items()['FILE']

        raise None

class band:

    def __init__(self, f, lev, e, f_msk, solid_bg, opts, fzip):
        from gio import geo_raster_ex as gx
        from gio import geo_raster as ge

        self.bnd = []
        if f.endswith('.shp'):
            if lev > 6:
                _f_shp = fzip.generate_file('', '.shp')
                _cmd = 'ogr2ogr -spat %s %s %s %s %s %s' % (e.minx, e.miny, e.maxx, e.maxy, _f_shp, f)

                from gio import run_commands
                run_commands.run(_cmd)
            else:
                _f_shp = f

            _bnd = gx.geo_band_stack_zip.from_shapefile(_f_shp, file_unzip=fzip, )
            if _bnd is not None:
                self.bnd = [_bnd]
        else:
            _img = ge.open(fzip.unzip(f))
            self.bnd = filter(lambda x: x is not None, [_img.get_band(_b + 1) for _b in xrange(_img.band_num)])

        self.color = self.bnd[0].color_table if len(self.bnd) == 1 else None
        self.solid_bg = solid_bg
        self.translate_color = opts.get('translate_color', None)

        self.mask = None
        if f_msk:
            self.mask = gx.geo_band_stack_zip.from_shapefile(f_msk) if f_msk.endswith('.shp') \
                    else ge.open(f_msk).get_band()

        self.fzip = fzip

    def _color(self, c):
        _cs = {}
        if c == None:
            return None

        _rg = lambda x: min(max(0, x), 255)

        _c = c.Clone()
        for i in xrange(_c.GetCount()):
            try:
                _v = _c.GetColorEntry(i)
            except:
                _v = _rg

            if len(_v) == 3:
                _v = list(_v) + [255]

            _cs[i] = map(_rg, _v)

        return _cs

    def _save(self, bnd, cs, f):
        import mod_image
        _dat = mod_image.convert(bnd, cs)

        import png
        png.from_array(_dat, 'RGBA').save(f)

    def _load_color(self, f):
        import re

        _cs = {}
        with open(f) as _fi:
            for _l in _fi.read().splitlines():
                _vs = re.split('\s+', _l.strip())
                if len(_vs) < 2:
                    continue

                _cc = list(map(int, re.split('\s*,\s*', _vs[1])))
                if len(_cc) == 3:
                    _cc.append(255)

                _cs[int(_vs[0])] = _cc

        return _cs

    def _interp_colors(self, cs, v_val, scale=100):
        if cs == None or len(cs.keys()) == 0:
            raise Exception('no color table provided')

        _c2 = cs[v_val]
        if len(_c2) > 3:
            _c2 = _c2[:3] + [255]

        # _c1 = [255, 255, 255, 0] #cs[v_non]
        # _c1 = list(map(lambda x: max(0, min(255, x)), [(255 + _v) / 2 for _v in _c2]))
        _c1 = list(map(lambda x: max(0, min(255, x)), [(255 + _v) / 2 for _v in _c2]))

        if len(_c1) > 3:
            _c1 = _c1[:3]

        _c1 = _c1 + [80]

        _ss = [(_c2[i] - _c1[i]) / float(scale) for i in xrange(len(_c1))]
        _cs = {0: [255, 255, 255, 0]}

        for i in xrange(scale):
            _cs[i + 1] = [int(_c1[_b] + (i * _ss[_b]))  for _b in xrange(len(_c1))]
            if len(_cs[i+1]) > 3:
                _cs[i+1][-1] = max(_cs[i+1][-1], 80)

            # print i, _cs[i]

        return _cs

    def _interp_colors_t(self, cs, v_val, scale=100, mag=1):
        if cs == None or len(cs.keys()) == 0:
            raise Exception('no color table provided')

        _c2 = cs[v_val]
        if len(_c2) > 3:
            _c2 = _c2[:3]

        _mag = (1 if mag is None else mag)

        _cs = {255: [255, 255, 255, 0]}
        for i in xrange(scale + 1):
            _t = min(int(i * 2.56 * _mag), 255)
            _cs[i] = list(_c2) + [_t]

        return _cs

    def _interp_colors_solid_bg(self, cs, v_val, scale=100, max_val=100):
        if cs == None or len(cs.keys()) == 0:
            raise Exception('no color table provided')

        _c2 = cs[v_val]
        _c1 = [255, 255, 255]

        if len(_c1) > 3:
            _c1 = _c1[:3]

        _c1 = _c1 + [255]

        _ss = [(_c2[i] - _c1[i]) / float(max_val) for i in xrange(len(_c1))]
        _cs = {0: [255, 255, 255, 255], 255: [0, 0, 0, 0]}

        for i in xrange(scale):
            # _cs[i + 1] = [int(_c1[_b] + (min(i, max_val) * _ss[_b]))  for _b in xrange(len(_c1))]
            _cs[i + 1] = map(lambda x: max(0, min(255, x)), [int(_c1[_b] + i * _ss[_b])  for _b in xrange(len(_c1))])
            if len(_cs[i+1]) > 3:
                _cs[i+1][-1] = max(_cs[i+1][-1], 255)

        return _cs

    def _load_color_table(self, f_clr):
        if f_clr:
            logging.debug('use color table %r' % f_clr)
            return self._load_color(f_clr)

        if self.color == None:
            raise Exception('no color table provided')

        logging.debug('use internal color table')
        return self._color(self.color)

    def _scale_band(self, bnd, div):
        from gio import geo_raster as ge
        import math

        _geo = (lambda x: [x[0], x[1] / div, x[2] / div, x[3], x[4] / div, x[5] / div])(bnd.geo_transform)

        return ge.geo_band_info(_geo,
                int(math.ceil(bnd.width * float(div))),
                int(math.ceil(bnd.height * float(div))),
                bnd.proj)

    def _load_block(self, mak):
        _bnd = self.bnd[0].read_block(mak)

        if _bnd and self.translate_color:
            import map_color
            _bnd = map_color.colorize_band(_bnd, self.translate_color)

        return _bnd

    def _load_data(self, bnd_inp, bnd_out, zoom, perc=None, vals=None, agg=None):
        from gio import config
        from gio import agg_band

        if perc is not None:
            if zoom <= 1:
                import numpy as np

                _bnd = self._load_block(bnd_out)
                if _bnd is None:
                    return None

                _ddd = _bnd.data

                _dat = _ddd.astype(np.uint8)
                _dat.fill(255)

                if vals:
                    for _v in vals:
                        if _v == _bnd.nodata:
                            continue

                        _dat[_ddd == _v] = 0
                else:
                    _dd1 = _ddd != _bnd.nodata
                    _dv1 = _dd1 & (_ddd != perc)

                    _dat[_dv1] = 0

                _dv2 = _ddd == perc
                _dat[_dv2] = 100

                _bnd = _bnd.from_grid(_dat, nodata=255)
                return _bnd

            return agg_band.perc(self._load_block(bnd_out.scale(zoom)), bnd_out, perc, vals)

        _agg = agg or config.get('conf', 'aggregate', 'median')

        if zoom <= 1:
            _bnd = self._load_block(bnd_out)
            if _bnd is None:
                return None

            if _agg == 'mean':
                _bnd.data[_bnd.data > 100] = _bnd.nodata
            return _bnd

        if _agg in ['median']:
            return agg_band.median(self._load_block(bnd_out.scale(zoom)), bnd_out, False)

        if _agg in ['dominated']:
            return agg_band.dominated(self._load_block(bnd_out.scale(zoom)), bnd_out, False)

        if _agg == 'mean':
            _bnd_inp = self._load_block(bnd_out.scale(zoom))
            if _bnd_inp is None:
                return None

            _bnd = agg_band.mean(_bnd_inp, bnd_out, 0, 100)
            _bnd.data[_bnd.data > 100] = _bnd.nodata

            # add water pixels
            # _bnd_inp.data[_bnd_inp.data <= 100] = 0
            # _msk = agg_band.dominated(_bnd_inp, bnd_out, False)
            # _bnd.data[_msk.data == 200] = 200

            return _bnd

        raise Exception('unknown aggregate option: %s' % _agg)

    def _load_band(self, bnd, perc=None, vals=None, agg=None):
        if len(self.bnd) == 1:
            _zoom = min(int(bnd.geo_transform[1] / self.bnd[0].cell_size), 5)
            _bnd = self._load_data(self.bnd[0], bnd, _zoom, perc, vals, agg)

            if _bnd is None:
                return None

            # _bnd.save('test_data2.tif')

            # if perc != None:
            #     _idx = (_bnd.data > 0) & (_bnd.data < 10)
            #     _bnd.data[_idx] = 10

            # from gio import config
            # if config.cfg.getboolean('conf', 'mmu'):
            #     import filter_band
            #     _bnd = filter_band.mmu(_bnd, 1, 1)

            return [_bnd]
        else:
            return [self.bnd[_b].read_block(bnd) for _b in xrange(len(self.bnd))]

    def _save_band(self, bnd, cs, f_out):
        if cs == None or cs.keys() == 0:
            raise Exception('failed to find color table')

        if len(bnd) == 0:
            return

        if len(bnd) == 1:
            if bnd[0] == None:
                return

            if self.mask is not None:
                _msk = self.mask.read_block(bnd[0])
                if _msk:
                    bnd[0].data[_msk.data != 1] = bnd[0].nodata

            self._save(bnd[0], cs, f_out)
        else:
            from osgeo import gdal
            _img = gdal.GetDriverByName('PNG').Create(f_out, bnd[0].width,\
                    bnd[0].height, len(self.bnd), gdal.GDT_Byte)

            for _b in xrange(len(self.bnd)):
                _img.get_band(_b+1).write(self.bnd[_b].read_block(bnd[0]).data, 0, 0)

            _img.flush()

    def make(self, bnd, f_clr, f_out, agg=None):
        _bnd = self._load_band(bnd, agg=agg)
        if _bnd is None:
            return

        _cs = self._load_color_table(f_clr)

        # import json
        # json.dump(_cs, open('test_color.txt', 'w'))
        # _bnd[0].save(f_out[:-4] + '.tif')
        # self._save_band(_bnd, _cs, 'test_preview.png')

        self._save_band(_bnd, _cs, f_out)

    def make_perc(self, bnd, val, vals, f_clr, f_out, agg=None, mag=1):
        _bnd = self._load_band(bnd, val, vals, agg=agg)
        if _bnd is None:
            return

        if self.solid_bg:
            _cs = self._interp_colors_solid_bg(self._load_color_table(f_clr), val)
        else:
            _cs = self._interp_colors_t(self._load_color_table(f_clr), val, mag=mag)

        # import json
        # json.dump(_cs, open('test_color.txt', 'w'))

        # from gio import color_table as ct
        # _bnd[0].save(f_out[:-4] + '.tif', color_table=ct.map_colortable(_cs))

        # self._save_band(_bnd, _cs, 'test_preview.png')

        self._save_band(_bnd, _cs, f_out)

