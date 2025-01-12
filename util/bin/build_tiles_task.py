#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: build_tiles_task.py
Author: Min Feng
Version: 0.1
Create: 2015-09-10 16:02:12
Description:
'''

import logging

# class tiles:

#     def __init__(self):
#         import math
#         from gio import geo_raster as ge

#         self.b = 6378137.0
#         self.s = 256
#         self.p = self.b * math.pi

#         self.prj = ge.proj_from_epsg(3857)

#     def list(self, level, ext=None):
#         from gio import geo_base as gb

#         _r = (2 * self.p) / (2 ** level)

#         _rows = 2 ** level
#         _cols = 2 ** level

#         _num = -1
#         for _row in range(_rows):
#             for _col in range(_cols):
#                 _num += 1

#                 _x = -self.p + (_col * _r)
#                 _y = -self.p + (_row * _r)

#                 _ext = gb.geo_extent(_x, _y, _x + _r, _y + _r, self.prj)
#                 if ext is None or _ext.is_intersect(ext):
#                     yield level, _num, _col, _row

#     def cell(self, level):
#         _r = (2 * self.p) / (2 ** level)
#         return _r / self.s

#     def extent(self, level, col, row):
#         _r = (2 * self.p) / (2 ** level)
#         _c = _r / self.s

#         _x = -self.p + (col * _r)
#         _y = -self.p + (row * _r)

#         _geo = [_x, _c, 0, _y + _r, 0, -_c]

#         from gio import geo_raster as ge
#         return ge.geo_raster_info(_geo, self.s, self.s, self.prj)

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

def create_tasks(met, opts, levels, fzip):
    import os
    from gio import file_mag
    from gio import obj
    from geo_map_util import map_tile
    
    f_inp = met.file
    f_reg = opts.region if opts.region else met.region

    _f = f_inp if f_inp.startswith('PG:') else file_mag.get(f_inp).get()
    if not _f:
        raise Exception('failed to load %s' % f_inp)

    # detect the extent of input file
    _ext = load_shp(_f) if f_inp.endswith('.shp') or f_inp.upper().startswith('PG:') else load_img(_f, fzip)
    if f_reg:
        _rrr = load_shp(f_reg)
        _ext = _ext.intersect(_rrr)

    logging.info('detected extent %s' % str(_ext))
    print('detected extent', _ext)

    _tiles = map_tile.tile_mag(met.get('tile_merge', 1))

    _ps = []
    for _lev in levels:
        print(' - checking level', _lev, '(%.2f)' % _tiles.cell(_lev))
        for _lev, _num, _col, _row in _tiles.list(_lev, _ext):
            _ps.append((_lev, _num, _col, _row))

    logging.info('found %s task' % len(_ps))
    print('found %s tasks' % len(_ps))
    
    return _ps

def make_tile(lev, num, col, row, met, opts, inp):
    from geo_map_util import map_tile_task
    from geo_map_util import map_tile
    from gio import config
    
    _tag = opts.tag
    met.tag = _tag

    _tile = map_tile.tile(lev, col, row, met.get('tile_merge', 1))
    _d_web = config.get('general', 'map_path')

    return map_tile_task.map_tile_task().read(met, _d_web, _tag, _tile)
    
def parse_levels(lvls):
    import re
    
    _ls = []
    for _l in lvls:
        _m = re.match('^[0-9]+$', _l)
        if _m:
            _ls.append(int(_l))
            continue
            
        _m = re.match('^([0-9]+)\-([0-9]+)$', _l)
        if _m:
            for _z in range(int(_m.group(1)), int(_m.group(2)) + 1):
                _ls.append(_z)
            continue
                
        raise Exception('failed to parse {}'.format(_l))
        
    return sorted(list(set(_ls)))

def load_levels(met):
    if met.get('processed_levels') is not None:
        return met.get('processed_levels')
    return list(range(met.get('min_static_level', 3), met.get('min_dynamic_level', 9)+1))

def main(opts):
    import os
    import logging
    from gio import config
    from gio import file_mag
    
    config.set('conf', 'skip_low_levels', False)
    # config.set('conf', 'keep_nodata_tiles', True)
    config.set('general', 'map_path', config.get('conf', 'input'))
    
    _out = os.path.join(config.get('conf', 'input'), opts.tag)
    _f_ini = opts.setting or os.path.join(_out, 'setting.ini')
    
    if not file_mag.get(_f_ini).exists():
        logging.error('failed to find setting file: %s' % _f_ini)
        return
        
    from gio import obj
    _met = obj.load(file_mag.get(_f_ini).get())
    
    _lev = parse_levels(opts.levels) if opts.levels else load_levels(_met)    
    opts.levels = _lev
    print('levels: %s' % opts.levels)
    
#     opts.level_min = min(opts.levels)
#     opts.level_max = max(opts.levels)
    
    if opts.clean_tiles:
        if _met.version < 2.0:
            logging.warning('skip cleaning tiles for old versions (<2.0)')
        else:
            logging.info('cleaning tiles')
            print('cleaning tiles')
            
            from gio import file_mag
            file_mag.get(os.path.join(_out, 'tiles')).remove()
            
    from gio import file_unzip
    with file_unzip.zip() as _zip:
        _tt = create_tasks(_met, opts, opts.levels, _zip)
        
    from gio import multi_task
    multi_task.run(make_tile, multi_task.load(_tt, opts), opts, (_met, opts, _out))
    print()

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-d', '-i', '--input', dest='input')
    _p.add_argument('-t', '--tag', dest='tag', required=True)
    _p.add_argument('-o', '--output', dest='output')
    _p.add_argument('-s', '--setting', dest='setting')
    _p.add_argument('-c', '--cache', dest='cache')
    
    _p.add_argument('-k', '--keep-nodata-tiles', dest='keep_nodata_tiles', type='bool', default=False,
                   help='keep the nodata map tiles')
    _p.add_argument('--clean-tiles', dest='clean_tiles', type='bool', \
            help='remove the tiles previously generated for the layer')

    _p.add_argument('-r', '--region', dest='region')
    _p.add_argument('-l', '--levels', dest='levels', nargs='*')

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

