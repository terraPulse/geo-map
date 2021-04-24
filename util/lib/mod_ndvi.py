'''
File: mod_ndvi.py
Author: Min Feng
Version: 0.1
Create: 2017-05-16 15:31:20
Description:
'''

def identify_loc(lon, lat):
    from gio import geo_raster as ge
    from gio import geo_base as gb
    from gio import geo_raster_ex as gx
    from gio import modis_util

    _proj_geo = gb.proj_from_epsg()
    _proj_sin = gb.modis_projection()

    _p = gx.geo_point(lon, lat, _proj_geo)
    _t =_p.project_to(_proj_sin)

    _x = _t.x
    _y = _t.y

    _col,_row = modis_util.modis_info().pixel(_x,_y)
    _tile = modis_util.modis_info().tile(_x,_y)

    _ext = modis_util.modis_info().extent(_tile)
    _num = 2400
    _cel = _ext.width() / _num

    _bnd = ge.geo_band_info([_ext.minx, _cel, 0, _ext.maxy, 0, -_cel], _num, _num, _proj_sin)
    _eee = _bnd.cell_extent(_col, _row).to_polygon().project_to(_proj_geo)

    return _eee, _row, _col, _tile, _t

def search_files(f, _tile,_b_c,_b_r):
    import re
    import os
    import logging
    import shutil
    from gio import config
    from gio import file_mag

    if f is None:
        return {}

    _f = file_mag.get(f).get()
    logging.info('getting list file %s to %s' % (f, _f))

    _ss ={}
    for _l in open(_f).read().strip().splitlines():
        _file = os.path.basename(_l)

        _m = re.match('\w{4}_V01_%s_(\d{4})_c%s_r%s\.dat' % (_tile,_b_c,_b_r), _file) \
                or re.match('%s_r%02dc%02d_(\d{4})_\w{4}.dat' % (_tile, _b_r, _b_c), _file)
        if _m:
            _yy = int(_m.group(1))
            _ff = _l
            _ss[_yy] = _ff
        
    if f.startswith('s3://') and config.getboolean('conf', 'remove_cached_s3_list', True):
        try:
            logging.info('remove the cached list: %s' % _f)
            os.remove(_f)
        except Exception:
            pass

    return _ss

def _year_length(_yy):
    if _yy % 4 == 0:
        return 366

    return 365

def _clean_data(f):
    import logging
    import os

    try:
        logging.info('remove the cached file: %s' % f)
        os.remove(f)
    except Exception:
        pass

def read_bytes(_dat, year, _rr, _cc, cell, version):
    import struct
    import logging
    from gio import file_mag

    _pn = _rr * cell + _cc

    _days = 365 if version == 1 else _year_length(year)
    _day_span = _days
    _gzip = False

    if version != 1:
        from gio import config
        if True or config.getboolean('conf', 'enable_gzip', False):
            _f_met = file_mag.get(_dat[:-3] + 'met')
            if _f_met.exists():
                _f_met = _f_met.get()

                from gio import metadata
                _met = metadata.load(_f_met)

                _gzip = _met.compressed
                _day_span = min(_days, _met.date_end)

                if _day_span < _days:
                    _clean_data(_f_met)
    
    _f_dat = file_mag.get(_dat).get()

    # print ('loading %s days (%s) at %s (%s, %s ~ %s)' % (_f_dat, _days, _pn, _rr, _cc, cell))
    logging.info('loading %s days (%s, %s) at %s (%s, %s ~ %s)' % (_f_dat, _days, _day_span, _pn, _rr, _cc, cell))

    if _gzip:
        import gzip
        with gzip.open(_f_dat, 'rb') as _f_in:
            _f_in.seek(_pn * (2 * _days),0)
            _bytes = _f_in.read(2 * _day_span)
            _pixels = struct.unpack('%sh' % _day_span,_bytes)
    else:
        with open(_f_dat, 'rb') as _f_in:
            _f_in.seek(_pn * (2 * _days),0)
            _bytes = _f_in.read(2 * _day_span)
            _pixels = struct.unpack('%sh' % _day_span,_bytes)
        
    if _day_span < _days:
        _clean_data(_f_dat)

    return _pixels

def yd2ymd(_yy,_dd):
    import datetime
    _date = '%s%s' % (_yy,_dd)
    _ymd = str(datetime.datetime.strptime(_date, '%Y%j').strftime('%Y-%m-%d'))
    return _ymd

def yd2obj(_yy,_dd):
    import datetime
    _date = '%s%s' % (_yy,_dd)
    return datetime.datetime.strptime(_date, '%Y%j')

def read_pt(f, pt):
    if f.endswith('.shp'):
        from gio import geo_raster_ex as gx
        _val = gx.geo_band_stack_zip.from_shapefile(f).read(pt)
        return _val
    else:
        from gio import geo_raster as ge
        _bnd = ge.open(f).get_band()
        _pt = pt.project_to(_bnd.proj)

        return _bnd.read_location(_pt.x, _pt.y)

def _normal_vals(ds):
    import numpy as np

    _ss = {}

    for _d, _vs in ds.items():
        if len(_vs) < 2:
            continue

        _vv = np.array(_vs)
        _ss[_d] = (np.median(_vv), _vv.std())

    return _ss

def _pt_NDVI(f_in, lon, lat, cell, filter_water=True, tag=None, version=2, v_min=-1000, v_max=1000, ys=None, ye=None):
    from gio import geo_raster_ex as gx
    from gio import config
    import logging

    _ext, _row, _col, _tile, _pt = identify_loc(lon, lat)

    if filter_water:
        _f_wat = config.get('general', 'water_path')
        _wat = gx.geo_band_stack_zip.from_shapefile(_f_wat).read(_pt) if _f_wat else None

        if _wat is not None and _wat != 0:
            logging.warning('water pixel %s, %s' % (lon, lat))
            return None

    if tag:
        _path = config.get('mask', tag)
        if _path:
            _val = read_pt(_path, _pt)
            if _val != 1:
                logging.warning('masked pixel %s, %s' % (lon, lat))
                return None

    _rr = _row % cell
    _cc = _col % cell
    b_r = _row / cell
    b_c = _col / cell

    logging.info('located tile %s' % ', '.join(map(str, (_rr, _cc, b_r, b_c))))

    _ss = search_files(f_in, _tile, b_c, b_r)
    logging.info('found files %s' % str(_ss))

    _yy = list(_ss.keys())
    if len(_yy) == 0:
        return None

    _yy.sort()

    _vs = {}
    _ds = {}
    for _y in _yy:
        if ys is not None:
            if _y < ys:
                continue

        if ye is not None:
            if _y > ye:
                continue

        try:
            _pixels = read_bytes(_ss[_y], _y, _rr, _cc, cell, version)
        except Exception:
            continue

        logging.info('load pixels %s %s %s %s' % (_y, len(_pixels), _pixels[:5], _pixels[-5:]))
        for _d in range(len(_pixels)):
            val = _pixels[_d]
            _dd = (_y * 1000) + _d
            
            _vs[_dd] = None

            if val < v_min:
                continue

            if val > v_max:
                continue

            _v = val / 1000.0
            if _d not in _ds:
                _ds[_d] = []

            _ds[_d].append(_v)
            _vs[_dd] = _v

    return _yy, _vs, _normal_vals(_ds)

def _mean_ndvi(vs, idx, d=7, interpolate=True):
    if idx not in vs:
        return None

    _v = vs[idx]
    if not interpolate:
        return _v

    _vs = []
    for i in range(-d, d+1):
        if i == 0:
            continue

        if idx + i not in vs:
            continue

        if vs[idx + i] is None:
            continue

        _vs.append(vs[idx + i])

    if len(_vs) == 0:
        return _v

    _a = sum(_vs) / len(_vs)
    if _v is None or (abs(_v - _a) > 0.005):
        vs[idx] = _a
        _v = _a

    return _v

def _convert_results(tag, os, f_out, interpolate=True):
    import logging

    _as = ['YYYY_MM_DD,' + tag.upper() + ',medium,STD']
    _ls = []

    if os is None:
        return []

    _ys, _vs, _ss = os

    _min_d = min(_vs.keys())
    _max_d = max(_vs.keys())

    logging.info('date period: %s - %s, interpolate=%s' % (_min_d, _max_d, interpolate))

    for _y in _ys:
        for _d in range(365):
            _dd = _y * 1000 + _d
            if _dd < _min_d or _dd > _max_d:
                continue

            _v = _mean_ndvi(_vs, _dd, interpolate=interpolate)

            _v_m = None
            _v_s = None

            if _d in _ss:
                _v_m, _v_s = _ss[_d]

            _date = yd2ymd(_y, _d + 1)

            if _v is not None:
                _v = round(_v, 2)

            if _v_m is not None:
                _v_m = round(_v_m, 2)

            if _v_s is not None:
                _v_s = round(_v_s, 2)

            # if _v is not None:
            #     if abs(_v - _v_m) > min(0.3, 2.96 * _v_s):
            #         _v = None

            # if _dd > 2020320:
            #     print(_dd, _date, _v, _v_m, _v_s)

            if _v_m is None or _v_s is None:
                _ls.append([_date, _v, None, None])
                continue

            _as.append('%s,%s,%s,%s' % (_date, _v if _v else '', _v_m, _v_s))
            _ls.append([_date, _v, _v_m, _v_s])

            # _as.append('%s,%s' % (_date, _v if _v else ''))
            # _ls.append([_date, _v])

    # _ss = [_l[1] for _l in _ls]
    # for _i in range(len(_ls)):
    #     _vs = [_s for _s in _ss[max(0, _i - 3): min(_i + 3, len(_ss))]]
    #     # _ls[_i][1] = sorted(_vs)[len(_vs) / 2]
    #     _ls[_i][1] = sum(_vs) / len(_vs)

    if f_out:
        with open(f_out, 'w') as _fo:
            _fo.write('\n'.join(_as))

    return _ls

def _load_list(c):
    from gio import config

    _ds = config.cfg.defaults()
    _cs = {}
    for _n, _v in config.cfg.items(c):
        if _n in _ds:
            continue

        _cs[_n] = _v

    return _cs

def extract_NDVI(lon, lat, tag=None, ys=1000, ye=3000, f_out=None, interpolate=True):
    from gio import config
    import logging

    _ext, _row, _col, _tile, _pt = identify_loc(lon, lat)
    _os = None

    for _n, _l in _load_list('ndvi_path').items():
        logging.info('load %s, %s list %s, interpolate %s' % (tag, _n, _l, interpolate))

        _os = _pt_NDVI(_l, lon, lat, 200, True, tag, v_min=-100, v_max=990, ys=ys, ye=ye)
        if _os is not None:
            logging.info('load records %s (%s)' % (len(_os[1]), _os[0]))
            return {'ext': _ext.poly.ExportToJson(), 'data': _convert_results('NDVI', _os, f_out, interpolate=interpolate)}

    logging.info('loading default NDVI records')
    if _os is None or len(_os[0]) == 0:
        _l = config.get('general', 'ndvi_path_o')
        if not _l:
            return None
        _os = _pt_NDVI(_l, lon, lat, 600, tag, version=1, ys=ys, ye=ye)

    return {'ext': _ext.poly.ExportToJson(), 'data': _convert_results('NDVI', _os, f_out, interpolate=interpolate)}

def extract_NDWI(lon, lat, tag=None, ys=1000, ye=3000, f_out=None, interpolate=True):
    from gio import config
    import logging

    _ext, _row, _col, _tile, _pt = identify_loc(lon, lat)
    _os = None

    for _n, _l in _load_list('ndwi_path').items():
        logging.info('load %s, %s list %s' % (tag, _n, _l))

        _os = _pt_NDVI(_l, lon, lat, 200, False, tag, ys=ys, ye=ye)
        if _os is not None:
            return {'ext': _ext.poly.ExportToJson(), 'data': _convert_results('NDWI', _os, f_out, interpolate=interpolate)}

    return {'ext': _ext.poly.ExportToJson(), 'data': []}

def extract_NDSI(lon, lat, tag=None, ys=1000, ye=3000, f_out=None, interpolate=True):
    from gio import config
    import logging

    _ext, _row, _col, _tile, _pt = identify_loc(lon, lat)
    _os = None

    for _n, _l in _load_list('ndsi_path').items():
        logging.info('load %s, %s list %s' % (tag, _n, _l))

        _os = _pt_NDVI(_l, lon, lat, 200, False, tag, ys=ys, ye=ye)
        if _os is not None:
            return {'ext': _ext.poly.ExportToJson(), 'data': _convert_results('NDSI', _os, f_out, interpolate=interpolate)}

    return {'ext': _ext.poly.ExportToJson(), 'data': []}

def main(opts):
    _l = '/data/mfeng/data/ndvi/list/ndvi_bip.txt'
    extract_NDVI(_l, -73.090337, 49.581254,600, f_out='NDVI_time_series.csv')

def usage():
    _p = environ_mag.usage(False)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

