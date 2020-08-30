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
        for _row in range(_rows):
            for _col in range(_cols):
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

def _mask_grid(bnd, f, fzip):
    from gio import rasterize_band as rb
    from gio import geo_base as gb
    from gio import file_mag
    
    _pol = [_p for _p, _a in gb.load_shp(file_mag.get(f).get(), ext=bnd.extent().to_polygon())]
    _msk = rb.to_mask(bnd, _pol)
    _shp = bnd.data.shape
    
    if len(_shp) == 2:
        if bnd.nodata is None:
            raise Exception('nodata needs to be set for the input raster')
        bnd.data[_msk.data != 1] = bnd.nodata
        return
    
    if len(_shp) == 3:
        if _shp[0] != 4:
            raise Exception('no transparency band provided')
            
        bnd.data[3, :, :] = 0
        return
    
    raise Exception('failed to recognize the image type')

def make_tile(f, lev, col, row, percent, vals, solid_bg, f_clr, f_msk, d_out, agg=None, opts={}):
    # from osgeo import gdal
    # gdal.UseExceptions()
    import os
    from gio import file_mag

    if opts.get('version', 1.0) < 2.0:
        _d = os.path.join(d_out, str(lev), str(col))
    else:
        _d = os.path.join(d_out, 'tiles', str(lev), str(col))
        
    _f = os.path.join(_d, '%s.png' % row)
    logging.debug('generating tile at %s' % _f)
    
    if file_mag.get(_f).exists():
        logging.debug('skip %s' % _f)
        return

    from gio import file_unzip
    with file_unzip.file_unzip() as _zip:
        from gio import config
        _cache = config.get('conf', 'cache', None)
        if not _cache:
            _tmp = _zip.generate_file()
            config.set('conf', 'cache', os.path.join(_tmp, 'cache'))

        _ext = tiles().extent(lev, col, row)

        _finp = file_mag.get(f).get()

        logging.debug('generate tile %s' % _f)
        
        _d_tmp = _zip.generate_file()
        os.makedirs(_d_tmp)
        _f_tmp = os.path.join(_d_tmp, os.path.basename(_f))
        
        if percent != None:
            band(_finp, lev, _ext, f_msk, solid_bg, opts, _zip).make_perc(_ext, percent, \
                    vals, f_clr, _f_tmp, agg=agg, \
                    mag=opts.get('mag', None), opts=opts)
        else:
            band(_finp, lev, _ext, f_msk, solid_bg, opts, _zip).make(_ext, \
                    f_clr, _f_tmp, agg=agg, opts=opts)
                    
        file_unzip.compress_folder(_d_tmp, os.path.dirname(_f), [])

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
        for i in range(_c.GetCount()):
            try:
                _v = _c.GetColorEntry(i)
            except:
                _v = _rg

            if len(_v) == 3:
                _v = list(_v) + [255]

            _cs[i] = list(map(_rg, _v))

        return _cs

    def save(self, f):
        _ls = []
        for _k, _v in list(self._cs.items()):
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
            return list(_f.items())['FILE']

        return None

class band:

    def __init__(self, f, lev, ext, f_msk, solid_bg, opts, fzip):
        # from gio import geo_base as gb
        # _eee = _ext.extent().to_polygon().project_to(gb.modis_projection()).extent()

        self.bnd = self._load_file(f, lev, ext, fzip)
        if self.bnd is None:
            return
        
        self.level = lev
        self.color = self.bnd[0].color_table if len(self.bnd) == 1 else None
        self.solid_bg = solid_bg
        self.translate_color = opts.get('translate_color', None)

        self.mask = None
        if f_msk:
            from gio import geo_raster_ex as gx
            from gio import geo_raster as ge

            self.mask = gx.geo_band_stack_zip.from_shapefile(f_msk, extent=ext) if not f_msk.endswith('.tif') \
                    else ge.open(f_msk).get_band()
                    
        self.region = opts.get('region', None)
        self.fzip = fzip
    
    def _load_file(self, f, lev, ext, fzip):
        from gio import geo_raster_ex as gx
        from gio import geo_raster as ge
        
        if not (f.endswith('.shp') or f.startswith('PG:')):
            _img = ge.open(fzip.unzip(f))
            _bnd = [x for x in [_img.get_band(_b + 1) for _b in range(_img.band_num)] if x is not None]
            return _bnd
            
        _bnd = gx.geo_band_stack_zip.from_shapefile(f, file_unzip=fzip, extent=ext)
        if _bnd is not None:
            return [_bnd]
            
        return None

    def _color(self, c):
        _cs = {}
        if c == None:
            return None

        _rg = lambda x: min(max(0, x), 255)

        _c = c.Clone()
        for i in range(_c.GetCount()):
            try:
                _v = _c.GetColorEntry(i)
            except:
                _v = _rg

            if len(_v) == 3:
                _v = list(_v) + [255]

            _cs[i] = list(map(_rg, _v))

        return _cs

    def _save(self, bnd, cs, f, opts):
        from gio import geo_raster as ge
        import numpy as np
        
        if self.translate_color:
            _bnd = bnd.colorize_rgba(self.translate_color, True)
        else:
            _bnd = bnd.colorize_rgba(cs, False)
            
        _bnd = self._burn(_bnd, opts)
        _bnd.to_image().save(f)
        
    def _load_color(self, f):
        import re
        from gio import file_mag

        _cs = {}
        with open(file_mag.get(f).get()) as _fi:
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
        if cs == None or len(list(cs.keys())) == 0:
            raise Exception('no color table provided')

        _c2 = cs[v_val]
        if len(_c2) > 3:
            _c2 = _c2[:3] + [255]

        # _c1 = [255, 255, 255, 0] #cs[v_non]
        # _c1 = list(map(lambda x: max(0, min(255, x)), [(255 + _v) / 2 for _v in _c2]))
        _c1 = list([max(0, min(255, x)) for x in [(255 + _v) / 2 for _v in _c2]])

        if len(_c1) > 3:
            _c1 = _c1[:3]

        _c1 = _c1 + [80]

        _ss = [(_c2[i] - _c1[i]) / float(scale) for i in range(len(_c1))]
        _cs = {0: [255, 255, 255, 0]}

        for i in range(scale):
            _cs[i + 1] = [int(_c1[_b] + (i * _ss[_b]))  for _b in range(len(_c1))]
            if len(_cs[i+1]) > 3:
                _cs[i+1][-1] = max(_cs[i+1][-1], 80)

        return _cs

    def _interp_colors_t(self, cs, v_val, scale=100, mag=1):
        if cs == None or len(list(cs.keys())) == 0:
            raise Exception('no color table provided')

        _c2 = cs[v_val]
        if len(_c2) > 3:
            _c2 = _c2[:3]

        _mag = (1 if mag is None else mag)

        _cs = {255: [255, 255, 255, 0]}
        for i in range(scale + 1):
            _t = min(int(i * 2.56 * _mag), 255)
            _cs[i] = list(_c2) + [_t]

        return _cs

    def _interp_colors_solid_bg(self, cs, v_val, scale=100, max_val=100):
        if cs == None or len(list(cs.keys())) == 0:
            raise Exception('no color table provided')

        _c2 = cs[v_val]
        _c1 = [255, 255, 255]

        if len(_c1) > 3:
            _c1 = _c1[:3]

        _c1 = _c1 + [255]

        _ss = [(_c2[i] - _c1[i]) / float(max_val) for i in range(len(_c1))]
        _cs = {0: [255, 255, 255, 255], 255: [0, 0, 0, 0]}

        for i in range(scale):
            # _cs[i + 1] = [int(_c1[_b] + (min(i, max_val) * _ss[_b]))  for _b in xrange(len(_c1))]
            _cs[i + 1] = [max(0, min(255, x)) for x in [int(_c1[_b] + i * _ss[_b])  for _b in range(len(_c1))]]
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
        return _bnd

    def _load_data(self, bnd_inp, bnd_out, zoom, perc=None, vals=None, agg=None, opts={}):
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

            _bnd = self._load_block(bnd_out.scale(zoom))
            if _bnd is None:
                return None

            return agg_band.perc(_bnd, bnd_out, perc, vals)

        _agg = agg or config.get('conf', 'aggregate', 'median')

        if zoom <= 1:
            _bnd = self._load_block(bnd_out)
            if _bnd is None:
                return None

            # if _agg == 'mean':
            #     _bnd.data[_bnd.data > 100] = _bnd.nodata
            
            return _bnd

        if _agg in ['median']:
            _zero_rate = float(opts.get('zero_rate', 1.0))
            return agg_band.median(self._load_block(bnd_out.scale(zoom)), bnd_out, False, _zero_rate)

        if _agg in ['dominated']:
            _wets = opts.get('weights')
            if _wets:
                import json
                _wets = json.loads(_wets)
                
            _bnd_inp = self._load_block(bnd_out.scale(zoom))
            if _bnd_inp is None:
                return None
                
            _bnd = agg_band.dominated(_bnd_inp, bnd_out, _wets)
            _bnd.color_table = _bnd_inp.color_table
            
            return _bnd

        if _agg == 'mean':
            _bnd_inp = self._load_block(bnd_out.scale(zoom))
            if _bnd_inp is None:
                return None
                
            _bnd = agg_band.mean(_bnd_inp, bnd_out)
            _bnd.color_table = _bnd_inp.color_table
            
            # _bnd = agg_band.mean(_bnd_inp, bnd_out, 0, 100)
            # _bnd.data[_bnd.data > 100] = _bnd.nodata
            return _bnd

        raise Exception('unknown aggregate option: %s' % _agg)

    def _load_band(self, bnd, perc=None, vals=None, agg=None, opts={}):
        if self.bnd is None:
            return None
            
        if len(self.bnd) == 1:
            _zoom = min(int(bnd.geo_transform[1] / self.bnd[0].cell_size), 5)
            _bnd = self._load_data(self.bnd[0], bnd, _zoom, perc, vals, agg, opts)

            if _bnd is None:
                return None
                
            _val = opts.get('min_value', None)
            if _val is not None and _bnd.nodata is not None:
                _bnd.data[_bnd.data < _val] = _bnd.nodata
                
            _val = opts.get('max_value', None)
            if _val is not None and _bnd.nodata is not None:
                _bnd.data[_bnd.data > _val] = _bnd.nodata
                
            _mmu = opts.get('mmu', 0)
            if _mmu > 0:
                from gio import mod_filter
                mod_filter.filter_band_mmu(_bnd, num=_mmu)

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
            return [self.bnd[_b].read_block(bnd) for _b in range(len(self.bnd))]
            
    def _burn(self, bnd, opts):
        _bnd = bnd
        
        if 'burn_band' in opts:
            _opts = opts.get('burn_band', {})
            _mlev = _opts.getint('level', 1)
            if self.level >= _mlev:
                _clrs = _opts.get('color')
                _finp = _opts.get('input')
                _offs = _opts.get('offset', 200)
                
                logging.debug('burn band %s, %s, %s' % (_finp, _clrs, _offs))
                
                from gio import band_op
                _bnd = band_op.burn_band(_bnd, None, _finp, _clrs, _offs)
            
        if 'burn_transparency' in opts:
            _opts = opts.get('burn_transparency', {})
            _mlev = _opts.getint('level', 1)
            if self.level >= _mlev:
                _clrs = _opts.get('color', None)
                _finp = _opts.get('input')
                _vmin = _opts.getfloat('value_min')
                _vmax = _opts.getfloat('value_max')
                
                logging.debug('burn transparency %s, %s, %s' % (_finp, _vmin, _vmax))
                
                from gio import band_op
                _bnd = band_op.burn_transparency(_bnd, None, _finp, _vmin, _vmax)
        
        return _bnd
            
    def _img_to_png(self, bnds, f, opts):
        import numpy as np
        
        _msk = bnds[0]
        
        _dat = np.empty((4, _msk.height, _msk.width), dtype=np.uint8)
        _dat.fill(255)
        
        for _b in range(min(4, len(bnds))):
            _dat[_b, :, :] = bnds[_b].data
            
        if self.mask is not None:
            _mmm = self.mask.read_block(_msk)
            if _mmm:
                _dat[3, :, :][_mmm.data != 1] = 0
                
        _bnd = _msk.from_grid(_dat)
        _bnd = self._burn(_bnd, opts)
        
        if self.region is not None:
            from gio import file_unzip as fzip
            with fzip.zip() as _zip:
                _mask_grid(_bnd, self.region, _zip)
                
        self._save_rgb(_bnd, f)

    def _save_band(self, bnd, cs, f_out, opts):
        if cs == None or list(cs.keys()) == 0:
            raise Exception('failed to find color table')

        if len(bnd) == 0:
            return
        
        if len(bnd) > 1:
            return self._img_to_png(bnd, f_out, opts)
            
        if bnd[0] == None:
            return

        if self.mask is not None:
            _msk = self.mask.read_block(bnd[0])
            if _msk:
                bnd[0].data[_msk.data != 1] = bnd[0].nodata

        if self.region is not None:
            from gio import file_unzip as fzip
            with fzip.zip() as _zip:
                _mask_grid(bnd[0], self.region, _zip)

        self._save(bnd[0], cs, f_out, opts)
            
    def make(self, bnd, f_clr, f_out, agg=None, opts={}):
        _bnd = self._load_band(bnd, agg=agg, opts=opts)
        if _bnd is None:
            return

        _cs = self._load_color_table(f_clr)
        self._save_band(_bnd, _cs, f_out, opts)

    def make_perc(self, bnd, val, vals, f_clr, f_out, agg=None, mag=1, opts={}):
        _bnd = self._load_band(bnd, val, vals, agg=agg, opts=opts)
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

        self._save_band(_bnd, _cs, f_out, opts)
