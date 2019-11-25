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

def _read_block(f, bnd):
    if f.endswith('.shp'):
        from gio import geo_raster_ex as gx
        return gx.geo_band_stack_zip.from_shapefile(f).read_block(bnd)

    from gio import geo_raster as ge
    return ge.open(f).get_band().read_block(bnd)

def _reg(lon, lat, reg):
    from gio import config
    from gio import geo_base as gb
    from gio import geo_raster as ge

    _cell = 30
    _dist = 5
    _proj = gb.modis_projection()

    _pt = gb.geo_point(lon, lat, gb.proj_from_epsg()).project_to(_proj)

    _go = [_pt.x - _dist * _cell, _cell, 0, _pt.y + _dist * _cell, 0, -_cell]
    _bd = ge.geo_raster_info(_go, _dist * 2 + 1, _dist * 2 + 1, _proj)

    _f = config.get('mask', reg)

    import logging
    logging.info('load mask file %s %s' % (reg, _f))

    if not _f:
        raise Exception('failed to find file for mask %s' % reg)

    _mm = _read_block(_f, _bd)
    if _mm is None:
        return None

    _vv = _mm.read_cell(_dist, _dist)
    if _vv <= 0:
        return None

    import numpy as np
    _dd = (_mm.data == _vv).astype(np.uint8)
    if _dd.sum() <= 0:
        return None

    return _mm.from_grid(_dd)

def _median(g):
    # import logging
    _vs = g.compressed().tolist()

    # logging.info(_vs)
    if len(_vs) == 0:
        return None

    _vs.sort()
    return _vs[len(_vs) / 2]

def _extract_reg(tag, mak):
    from gio import config
    import logging
    import numpy.ma

    _ks = {}
    if config.cfg.has_section(tag):
        for _k in config.cfg.options(tag):
            if _k in config.cfg.defaults():
                continue

            _ks[_k] = config.get(tag, _k)

    _vs = {}
    for _k, _f in list(_ks.items()):
        logging.info('checking %s=%s' % (_k, _f))

        _bd = _read_block(_f, mak)

        # _da = numpy.ma.array(_bd.data, mask=(mak.data != 1))
        # if int(_k) == 2001:
        #     logging.info(_da.compressed())
        #
        # _da = numpy.ma.array(_bd.data, mask=(mak.data != 1) | (_bd.data == _bd.nodata))
        # if int(_k) == 2001:
        #     logging.info(_da.compressed())
        # _vv = np.ma.median(_da)

        _da = numpy.ma.array(_bd.data, mask=(mak.data != 1) | (_bd.data == _bd.nodata))
        _vv = _median(_da)

        if _vv is None:
            continue

        _vs[_k] = _vv

    return _vs

def _extract_pt(tag, lon, lat):
    from gio import config
    import logging

    _ks = {}
    if config.cfg.has_section(tag):
        for _k in config.cfg.options(tag):
            if _k in config.cfg.defaults():
                continue

            _ks[_k] = config.get(tag, _k)

    _vs = {}
    for _k, _f in list(_ks.items()):
        logging.info('checking %s=%s' % (_k, _f))
        if not _f.endswith('.shp'):
            continue

        _vs[_k] = _read(_f, lon, lat)

    return _vs

def pixel(tag, lon, lat, reg=None):
    if reg is not None:
        _mak = _reg(lon, lat, reg)
        if _mak is not None:
            return _extract_reg(tag, _mak)

    return _extract_pt(tag, lon, lat)

def main(opts):
    _x, _y = -69.41634178161534, 18.438209639795115
    print(pixel('dr', _x, _y))

def usage():
    _p = environ_mag.usage(False)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

