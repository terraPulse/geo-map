#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: build_tiles_make.py
Author: Min Feng
Version: 0.1
Create: 2015-09-10 15:46:23
Description: make tiling tasks
'''

import logging

def format_path(p):
    if p.startswith('/a/'):
        return '/'.join([''] + p.split('/')[3:])

    return p

def load_shp(f):
    from osgeo import ogr
    from gio import file_mag
    from gio import geo_base as gb

    _shp = ogr.Open(file_mag.get(f).get())
    if _shp is None:
        raise Exception('Failed to load shapefile ' + f)

    _lyr = _shp.GetLayer()
    _objs = []
    _area = None

    for _f in _lyr:
        _geo = _f.geometry()
        if _geo is None:
            continue
        
        _obj = gb.geo_polygon(_geo.Clone())
        _ext = _obj.extent()

        _objs.append(_obj)
        if _area is None:
            _area = _ext
        else:
            _area = _area.union(_ext)

    from gio import geo_raster as ge
    _prj = ge.proj_from_epsg(3857)

    _reg = _area.to_polygon().segment_ratio(30).project_to(_prj)
    return _reg.extent()

def load_img(f, fzip):
    from gio import geo_raster as ge

    _prj = ge.proj_from_epsg(3857)
    _reg = ge.open(fzip.unzip(f)).extent().to_polygon().segment_ratio(30).project_to(_prj)

    return _reg.extent()

class color_table:

    def __init__(self, cs):
        self._cs = cs

    @staticmethod
    def load(f, fzip):
        import os

        _ext = os.path.splitext(f.lower())[1]

        _f = f
        if _ext == '.shp' or f.startswith('PG:'):
            _f = color_table.load_sample(f)

        from gio import geo_raster as ge
        _m = ge.open(fzip.unzip(_f))
        if _m.band_num > 1:
            return color_table({})
        
        _b = _m.get_band()

        if _b.color_table is None:
            return None
        else:
            return color_table(color_table._color_table(_b.color_table))

    @staticmethod
    def _color_table(c):
        _cs = {}
        if c is None:
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
        if _shp is None:
            raise Exception('Failed to load shapefile ' + f)

        _lyr = _shp.GetLayer()
        for _f in _lyr:
            _is = _f.items()
            return _is.get('FILE', _is.get('file'))

        raise None

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
                if ext is None or _ext.is_intersect(ext):
                    yield level, _num, _col, _row

    def cell(self, level):
        _r = (2 * self.p) / (2 ** level)
        return _r / self.s

    def extent(self, level, col, row):
        _r = (2 * self.p) / (2 ** level)
        _c = _r / self.s

        _x = -self.p + (col * _r)
        _y = -self.p + (row * _r)

        _geo = [_x, _c, 0, _y + _r, 0, -_c]

        from gio import geo_raster as ge
        return ge.geo_raster_info(_geo, self.s, self.s, self.prj)

def make(f_inp, f_clr, f_tclr, levels, title, percent, valid_vals, agg, d_out, d_ooo, fzip, opts):
    import os
    from gio import file_mag

    _f = f_inp if f_inp.startswith('PG:') else file_mag.get(f_inp).get()
    if not _f:
        raise Exception('failed to load %s' % f_inp)

    # detect the extent of input file
    _ext = load_shp(_f) if f_inp.endswith('.shp') or f_inp.upper().startswith('PG:') else load_img(_f, fzip)
    if opts.region:
        _rrr = load_shp(opts.region)
        _ext = _ext.intersect(_rrr)

    logging.info('detected extent %s' % str(_ext))
    print('detected extent', _ext)

    _f_clr = os.path.join(d_out, 'color.txt')
    if not f_clr:
        logging.info('load color table from the input data')
        if f_tclr:
            from geo_map_util import map_color
            _f_clr = color_table(map_color.load_color_file(f_tclr)[1]).save(_f_clr)
        else:
            _f_clr = color_table.load(_f, fzip).save(_f_clr)

        print('loading color table', _f_clr)
    else:
        import shutil
        shutil.copy(f_clr, _f_clr)

    if not _f_clr:
        raise Exception('failed to find color table')

    _tiles = tiles()

    _ps = []
    print(os.path.join(d_ooo, os.path.basename(_f_clr)))
    for _lev in range(levels[0], levels[1]+1):
        print(' - checking level', _lev, '(%.2f)' % _tiles.cell(_lev))
        for _lev, _num, _col, _row in _tiles.list(_lev, _ext):
            _ps.append((f_inp, _lev, _num, _col, _row, percent, valid_vals, opts.solid_bg == True, \
                    os.path.basename(_f_clr), opts.mask, ''))

    logging.info('found %s task' % len(_ps))
    print('found %s tasks' % len(_ps))

    # print 'write map.html'
    # from gio import geo_raster as ge
    # _ext_geo = _ext.to_polygon().segment_ratio(30).project_to(ge.proj_from_epsg()).extent()

    # _f_out = os.path.join(d_out, 'map.html')
    # with open(config.cfg.get('conf', 'openlayers_temp'), 'r') as _fi, open(_f_out, 'w') as _fo:
    #     _fo.write(_fi.read() % {
    #             'title': os.path.basename(f_inp),
    #             'xmin': _ext_geo.minx, 'xmax': _ext_geo.maxx,
    #             'ymin': _ext_geo.miny, 'ymax': _ext_geo.maxy,
    #             'zmin': levels[0], 'zmax': levels[1]
    #             })

    print('write to', os.path.join(d_ooo, 'tasks.txt'))
    with open(os.path.join(d_out, 'tasks.txt'), 'wb') as _fo:
        import pickle
        pickle.dump(_ps, _fo)

    from gio import obj
    _obj = obj.obj()

    _obj.file = f_inp
    if percent is not None:
        _obj.percent = percent
    if title:
        _obj.title = title

    if valid_vals:
        _obj.valid_vals = valid_vals

    if opts.mask:
        _obj.mask = opts.mask

    if opts.region:
        _obj.region = opts.region

    if opts.solid_bg:
        _obj.solid_bg = True

    # if opts.options:
    #     import re
    #     for _co in opts.options:
    #         _m = re.match('(.+)\s*\=\s*(.+)', _co)
    #         if _m:
    #             print 'option %s=%s' % (_m.group(1), _m.group(2))
    #             _obj[_m.gruop(1)] = _m.group(2)
    #         else:
    #             print ' skip %s' % _co

    if opts.zero_rate is not None:
        print('zero rate: ', opts.zero_rate)
        _obj.zero_rate = opts.zero_rate
        
    if opts.mmu is not None:
        print('mmu: ', opts.mmu)
        _obj.mmu = opts.mmu
        
    if opts.weights is not None:
        print('weights: ', opts.weights)
        _obj.weights = opts.weights
        
    if opts.min_value is not None:
        print('min_value: ', opts.min_value)
        _obj.min_value = opts.min_value
        
    if opts.max_value is not None:
        print('max_value: ', opts.max_value)
        _obj.max_value = opts.max_value
        
    _min_dynamic_level = levels[1]
    if _min_dynamic_level is not None:
        print('min_dynamic_level: ', _min_dynamic_level)
        _obj.min_dynamic_level = _min_dynamic_level

    _obj.visible = True
    _obj.version = opts.version

    if agg:
        _obj.agg = agg

    if f_tclr:
        _obj.translate_color = os.path.abspath(f_tclr) if os.path.exists(f_tclr) else f_tclr
        
    if opts.burn_band_input:
        _obj.burn_band.input = opts.burn_band_input
        if opts.burn_band_offset is not None:
            _obj.burn_band.offset = opts.burn_band_offset
        _obj.burn_band.level = opts.burn_band_level
            
    if opts.burn_transparency_input:
        _obj.burn_transparency.input = opts.burn_transparency_input
        _obj.burn_transparency.level = opts.burn_transparency_level

    _obj.save(os.path.join(d_out, 'setting.ini'))

def main(opts):
    from osgeo import gdal
    gdal.UseExceptions()
    
    if opts.hillshade:
        opts.burn_band_input = 'dem/aw3d30/hillshade-lit'
        opts.burn_band_offset = 200
        opts.burn_band_level = 5

    from gio import config
    from gio import run_commands
    import os
    
    _d_out = os.path.join(config.get('conf', 'output'), opts.tag)
    if not _d_out.startswith('s3://'):
        _d_out = format_path(os.path.abspath(_d_out))

    from gio import file_unzip
    with file_unzip.file_unzip() as _zip:
        _f_inp = config.get('conf', 'input')
        if not (_f_inp.startswith('s3://') or _f_inp.startswith('PG:')):
            _f_inp = os.path.abspath(_f_inp)
        
        _d_tmp = _zip.generate_file()
        os.makedirs(_d_tmp)
        
        make(format_path(_f_inp), config.get('conf', 'color'), config.get('conf', 'translate_color'), \
                opts.levels, opts.title, opts.percent, opts.valid_vals, opts.agg, _d_tmp, \
                _d_out, _zip, opts)
                
        file_unzip.compress_folder(_d_tmp, _d_out, [])
        
    if opts.update_list:
        print('update map list')
        
        _cmd = 'update_map_list.py -o %s' % config.get('conf', 'output')
        run_commands.run(_cmd)

    if opts.execute:
        print('generate map tiles')

        _cmd = 'build_tiles_task.py -t %s -i %s ' % (opts.tag, config.get('conf', 'output'))
        # _agg = ' -a %s ' % opts.agg if opts.agg else ''
        _tsk = '-in %s -ip %s -ts %s %s -tw %s -to %s' % ( \
                opts.instance_num, opts.instance_pos, opts.task_num, \
                        '-se' if opts.skip_error else '', opts.time_wait, opts.task_order)

        # run_commands.run(_cmd + _agg + _tsk)
        run_commands.run(_cmd + _tsk)

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-i', '--input', dest='input', required=True)
    _p.add_argument('-d', '-o', '--output', dest='output')
    _p.add_argument('-c', '--color', dest='color')
    _p.add_argument('--translate-color', dest='translate_color')
    _p.add_argument('-t', '--tag', dest='tag', required=True)
    _p.add_argument('-a', '--agg', dest='agg')
    _p.add_argument('--title', dest='title')
    _p.add_argument('-p', '--percent', dest='percent', default=None, type=int, help='target type, background type')
    _p.add_argument('--solid-bg', dest='solid_bg', action='store_true')
    _p.add_argument('-v', '--valid-vals', dest='valid_vals', type=int, nargs='*')
    _p.add_argument('-m', '--mask', dest='mask')
    _p.add_argument('-r', '--region', dest='region')
    _p.add_argument('-l', '--levels', dest='levels', default=[3, 5], nargs=2, type=int)
    _p.add_argument('--zero-rate', dest='zero_rate', type=float)
    _p.add_argument('--weights', dest='weights')
    _p.add_argument('--mmu', dest='mmu', type=int, default=0)
    _p.add_argument('--min-value', dest='min_value', type=float)
    _p.add_argument('--max-value', dest='max_value', type=float)
    _p.add_argument('--version', dest='version', type=float, default=2.0)
    
    _p.add_argument('--hillshade', dest='hillshade', type='bool')
    
    _p.add_argument('--burn-band-input', dest='burn_band_input')
    _p.add_argument('--burn-band-offset', dest='burn_band_offset', type=int, default=250)
    _p.add_argument('--burn-band-level', dest='burn_band_level', type=int, default=1)
    
    _p.add_argument('--burn-transparency-input', dest='burn_transparency_input')
    _p.add_argument('--burn-transparency-level', dest='burn_transparency_level', type=int, default=1)

    _p.add_argument('-e', '--execute', dest='execute', type='bool', \
        help='run build_tiles_task.py after the map task is defined')
        
    _p.add_argument('-u', '--update-list', dest='update_list', type='bool', default=True, \
        help='run update_map_list.py after the map task is defined')

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])
