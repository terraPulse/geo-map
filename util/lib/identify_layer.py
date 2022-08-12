'''
File: identify_pixel.py
Author: Min Feng
Version: 0.1
Create: 2016-04-30 02:09:18
Description:
'''

import logging

def _geojson(txt):
	from gio import geo_base as gb
	from osgeo import ogr
	import json

# 	_g = ogr.CreateGeometryFromJson(str(json.dumps(txt)))
	_g = ogr.CreateGeometryFromJson(str(txt))
	if _g is None:
		raise Exception('failed to parse GeoJSON data')
	_g.AssignSpatialReference(gb.proj_from_epsg())

	_b = gb.geo_polygon(_g)
	return _b.project_to(gb.modis_projection())

def _create_mak(ext, cell):
    import math

    _cols = int(math.ceil(ext.width() / cell))
    _rows = int(math.ceil(ext.height() / cell))

    if 0 in [_cols, _rows]:
        raise Exception('failed to create the extent')
        return None

    _geo = [ext.minx, cell, 0, ext.maxy, 0, -cell]

    from gio import geo_base as gb
    from gio import geo_raster as ge
    
    return ge.geo_raster_info(_geo, _cols, _rows, gb.modis_projection())

def _reg_mask(geo):
    from gio import rasterize_band as rb
    from gio import geo_raster as ge
    
    if not geo:
        return None

    _ext = geo.extent()

    _dev = 100
    _cel = max(_ext.height() / _dev, _ext.width() / _dev)
    if _cel <= 0:
        logging.warning('failed to create mask for the requested area')
        return None
        
    _ext = _ext.buffer(_cel / 2.0)
    _reg = _create_mak(_ext, _cel)
    
    if _reg == None:
        logging.warning('failed to create mask for the requested area')
        return None

    from gio import file_unzip
    with file_unzip.zip() as _zip:
        _f_img = _zip.generate_file('', '.img')
        _f_shp = _zip.generate_file('', '.shp')
    
        rb.rasterize_band(_reg, geo.buffer(_cel / 2.0), _f_img, _f_shp)
        _mak = ge.open(_f_img).get_band().cache()
        _mak.proj = geo.proj
    
        return _mak

def _read(f, x, y):
    from gio import geo_raster_ex as gx
    from gio import geo_base as gb
    from gio import geo_raster as ge
    
    if f.endswith('.shp') or f.startswith('PG:'):
        _pt = gb.geo_point(x, y, ge.proj_from_epsg())
        _bb = gx.load(f, _pt)
        if _bb is None:
            return None
        return _bb.read(_pt)
        
    _bnd = ge.open(f)
    if _bnd is None:
        return None
        
    _bnd = _bnd.get_band()
    _pt = gb.geo_point(x, y, ge.proj_from_epsg()).project_to(_bnd.proj)
    return _bnd.read_location(_pt.x, _pt.y)

def _read_block(f, bnd):
    if f.endswith('.shp') or f.startswith('PG:'):
        from gio import geo_raster_ex as gx
        return gx.read_block(f, bnd)

    from gio import geo_raster as ge
    return ge.open(f).get_band().read_block(bnd)

def _median(g):
    _vs = g.compressed().tolist()

    # logging.info(_vs)
    if len(_vs) == 0:
        return None

    _vs.sort()
    return _vs[len(_vs) // 2]
    
def _mean(g):
    _vs = g.compressed().tolist()

    # logging.info(_vs)
    if len(_vs) == 0:
        return None

    return sum(_vs) / len(_vs)
    
def _categories(g):
    _vs = g.compressed().tolist()

    # logging.info(_vs)
    if len(_vs) == 0:
        return {}
        
    _ss = {}
    for _v in _vs:
        _v = round(_v, 1)
        if _v not in _ss:
            _ss[_v] = 0
            
        _ss[_v] += 1.0
        
    _rs = {}
    
    _tt = len(_vs)
    if _tt <= 0:
        return _rs
     
    for _k, _v in _ss.items():
        _rs[_k] = round(_v / _tt, 3)

    return _rs

def _extract_reg(tag, mak, cat=False, agg='median', val_min=None, val_max=None):
    from gio import config
    import numpy.ma
    from . import map_values
    
    _met = _load_setting(tag)
    if _met is None:
        return None
    
    _f = _met.get('file')
    if not _f:
        logging.warning('failed to find the data layer (%s)' % tag)
        return None

    _bd = _read_block(_f, mak)
    if not _bd:
        logging.warning('failed to create mask')
        return None
        
    _msk = (mak.data != 1) | (_bd.data == _bd.nodata)
    
    # use min and max values
    _min_val = _met.get('min_value') if val_min is None else val_min
    if _min_val is not None:
        logging.info('apply min value: %s' % _min_val)
        _msk = _msk | (_bd.data < _min_val)
    
    _max_val = _met.get('max_value') if val_max is None else val_max
    if _max_val is not None:
        logging.info('apply max value: %s' % _max_val)
        _msk = _msk | (_bd.data > _max_val)
    
    _da = numpy.ma.array(_bd.data, mask=_msk)
    
    if cat:
        _rs = _categories(_da)
        if _rs is None:
            return _rs
            
        _cs = {}
        for _k in sorted(_rs.keys()):
            _cs[map_values.text(tag, None, _met, _k)] = _rs[_k]
            
        return map_values.categories(tag, None, _met, _cs)
        
    if agg == 'median':
        return map_values.text(tag, None, _met, _median(_da))
    
    if agg == 'mean':
        return map_values.text(tag, None, _met, _mean(_da))
        
    raise Exception('supported aggregation %s' % agg)
    
def _extract_pt(tag, lon, lat):
    from gio import config

    _met = _load_setting(tag)
    if _met is None:
        return None
    
    _f = _met.get('file')
    if not _f:
        return None

    _v = _read(_f, lon, lat)
    if _v is None:
        return None
    
    # use min and max values
    _min_val = _met.get('min_value')
    if _min_val is not None:
        if _v < _min_val:
            return None
    
    _max_val = _met.get('max_value')
    if _max_val is not None:
        if _v > _max_val:
            return None
    
    from . import map_values
    return map_values.text(tag, None, _met, _v)
    
def _load_setting(tag):
    import os
    from gio import file_mag
    from gio import config
    
    _f_ini = os.path.join(config.get('general', 'map_path'), tag, 'setting.ini')
    if not file_mag.get(_f_ini).exists():
        logging.warning('no setting file found for %s' % tag)
        return None
        
    from gio import obj
    _met = obj.load(file_mag.get(_f_ini).get())
    
    return _met
    
def loc(tag, lon, lat):
    logging.info('query location %s, %s, %s' % (tag, lon, lat))
    
    if not tag:
        return None
        
    import re
    _vs = []
    for _t in re.split('[;,]', tag):
        _vs.append(_extract_pt(_t, lon, lat))
    return _vs
    
def reg(tag, reg, cat=False, agg='median', val_min=None, val_max=None):
    logging.info('query polygon %s, %s, %s' % (tag, cat, reg))
    
    if not tag:
        return None
        
    _mak = _reg_mask(_geojson(reg))
    if _mak is None:
        logging.warning('failed to create mask')
        return None
    
    import re
    _vs = []
    for _t in re.split('[;,]', tag):
        _vs.append(_extract_reg(_t, _mak, cat, agg, val_min, val_max))
    return _vs

def main(opts):
    from gio import config
    
    config.set('general', 'map_path', '/mnt/data1/mfeng/var/map')
    
    print(loc('global_tcc_2019_m', -76.85327814, 39.24435027))
    
    _geo = '{ "type": "Polygon", "coordinates": [ [ [ -76.85541629791258, 39.247044154820415 ], [ -76.85691833496094, 39.24661210203028 ], [ -76.85786247253418, 39.246213281707774 ], [ -76.85754060745239, 39.24536578099245 ], [ -76.85696125030518, 39.244800774826274 ], [ -76.85640335083006, 39.24488386425382 ], [ -76.85595273971558, 39.24543225200691 ], [ -76.85565233230591, 39.245781223799185 ], [ -76.85541629791258, 39.246362839594475 ], [ -76.85522317886353, 39.24664533695477 ], [ -76.85548067092896, 39.246944450566616 ], [ -76.85541629791258, 39.247044154820415 ] ] ] }'
    
    print(reg('global_tcc_2019_m', _geo))
    print(reg('global_tcc_2019_m', _geo, True))

def usage():
    _p = environ_mag.usage(False)
    
    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())]) 
