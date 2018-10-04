'''
File: identify_pixel.py
Author: Min Feng
Version: 0.1
Create: 2016-04-30 02:09:18
Description:
'''

def _read(f, x, y):
    from gio import geo_raster_ex as gx
    from gio import geo_base as gb
    from gio import geo_raster as ge

    _shp = gx.geo_band_stack_zip.from_shapefile(f)
    _val = _shp.read(gb.geo_point(x, y, ge.proj_from_epsg()))

    return _val

def pixel(tag, lon, lat):
    from gio import config
    import logging

    _ks = {}
    if config.cfg.has_section(tag):
        for _k in config.cfg.options(tag):
            _ks[_k] = config.get(tag, _k)

    _vs = {}
    for _k, _f in _ks.items():
        logging.info('checking %s=%s' % (_k, _f))
        if not _f.endswith('.shp'):
            continue

        _vs[_k] = _read(_f, lon, lat)

    return _vs

def main(opts):
    _x, _y = -69.41634178161534, 18.438209639795115
    print pixel('dr', _x, _y)

def usage():
    _p = environ_mag.usage(False)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

