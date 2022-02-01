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
    if p.startswith('s3://') or p.startswith('PG:'):
        return p
        
    import os
    return os.path.abspath(p)

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
    if _reg is None:
        raise Exception('failed to prepare the input file')
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
        shutil.copy(file_mag.get(f_clr).get(), _f_clr)

    if not _f_clr:
        raise Exception('failed to find color table')

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
        
    if opts.fill_nodata is not None:
        print('fill nodata:', opts.fill_nodata)
        _obj.fill_nodata = opts.fill_nodata
        
    if opts.values_mapping is not None:
        print('values_mapping:', format_path(opts.values_mapping))
        _obj.values_mapping = format_path(opts.values_mapping)
        
    _min_dynamic_level = levels[1]
    if _min_dynamic_level is not None:
        print('min_dynamic_level: ', _min_dynamic_level)
        _obj.min_dynamic_level = _min_dynamic_level
        
    print('min_static_level: ', levels[0])
    _obj.min_static_level = levels[0]

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
    
def add_item_to_list(l, d_out):
    from gio import file_mag
    import os
    
    _f_idx = file_mag.get(os.path.join(d_out, 'list.txt'))
    
    _ls = []
    if _f_idx.exists():
        if str(_f_idx).startswith('s3://'):
            os.remove(_f_idx.get())
    
        with open(_f_idx.get()) as _fi:
            _ls = _fi.read().strip().splitlines()
            
    if l in _ls:
        return False
    
    _ls.append(l)
    logging.info('add %s to %s (%s)' % (l, _f_idx, len(_ls)))
    
    from gio import file_unzip as fz
    with fz.zip() as _zip:
        _zip.save('\n'.join(_ls), str(_f_idx))
        
    return True
    
def main(opts):
    from osgeo import gdal
    gdal.UseExceptions()
    
    if opts.hillshade:
        opts.burn_band_input = 'dem/aw3d30/hillshade-lit'
        opts.burn_band_offset = 200
        opts.burn_band_level = 1

    from gio import config
    from gio import run_commands
    import os
    
    _d_out = format_path(os.path.join(config.get('conf', 'output'), opts.tag))

    from gio import file_unzip
    with file_unzip.file_unzip() as _zip:
        _f_inp = format_path(config.get('conf', 'input'))
        
        _d_tmp = _zip.generate_file()
        os.makedirs(_d_tmp)
        
        make(_f_inp, config.get('conf', 'color'), config.get('conf', 'translate_color'), \
                opts.levels, opts.title, opts.percent, opts.valid_vals, opts.agg, _d_tmp, \
                _d_out, _zip, opts)
                
        if opts.clean_tiles:
            if opts.version < 2.0:
                logging.warning('skip cleaning tiles for old versions (<2.0)')
            else:
                logging.info('cleaning tiles')
                print('cleaning tiles')
                
                from gio import file_mag
                file_mag.get(os.path.join(_d_out, 'tiles')).remove()

        file_unzip.compress_folder(_d_tmp, _d_out, [])
        
    # update the map list ot add the new layer
    if opts.update_list:
        print('update map list')
        add_item_to_list(opts.tag, config.get('conf', 'output'))
        
        # _cmd = 'update_map_list.py -o %s' % config.get('conf', 'output')
        # run_commands.run(_cmd)

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
    _p.add_argument('--fill-nodata', dest='fill_nodata', type=float)
    _p.add_argument('-v', '--valid-vals', dest='valid_vals', type=int, nargs='*')
    _p.add_argument('-m', '--mask', dest='mask')
    _p.add_argument('-r', '--region', dest='region')
    _p.add_argument('-l', '--levels', dest='levels', default=[3, 9], nargs=2, type=int)
    _p.add_argument('--zero-rate', dest='zero_rate', type=float)
    _p.add_argument('--weights', dest='weights')
    _p.add_argument('--mmu', dest='mmu', type=int, default=0)
    _p.add_argument('--min-value', dest='min_value', type=float)
    _p.add_argument('--max-value', dest='max_value', type=float)
    _p.add_argument('--version', dest='version', type=float, default=2.0)
    _p.add_argument('--values-mapping', dest='values_mapping')
    _p.add_argument('--clean-tiles', dest='clean_tiles', type='bool', \
            help='remove the tiles previously generated for the layer')
    
    _p.add_argument('--hillshade', dest='hillshade', type='bool')
    
    _p.add_argument('--burn-band-input', dest='burn_band_input')
    _p.add_argument('--burn-band-offset', dest='burn_band_offset', type=int, default=250)
    _p.add_argument('--burn-band-level', dest='burn_band_level', type=int, default=1)
    
    _p.add_argument('--burn-transparency-input', dest='burn_transparency_input')
    _p.add_argument('--burn-transparency-level', dest='burn_transparency_level', type=int, default=1)

    _p.add_argument('-e', '--execute', dest='execute', type='bool', \
        help='run build_tiles_task.py after the map task is defined')
        
    _p.add_argument('--update-list', dest='update_list', type='bool', default=True, \
        help='run update_map_list.py after the map task is defined')

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])
