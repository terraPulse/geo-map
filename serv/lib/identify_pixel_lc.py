'''
File: identify_pixel.py
Author: Min Feng
Version: 0.1
Create: 2016-04-30 02:09:18
Description:
'''

def nlcd_text(v):
    _ts = {
            11: 'Open Water',
            12: 'Perennial Ice/Snow',
            21: 'Developed, Open Space',
            22: 'Developed, Low Intensity',
            23: 'Developed, Medium Intensity',
            24: 'Developed High Intensity',
            31: 'Barren Land (Rock/Sand/Clay)',
            41: 'Deciduous Forest',
            42: 'Evergreen Forest',
            43: 'Mixed Forest',
            51: 'Dwarf Scrub',
            52: 'Shrub/Scrub',
            71: 'Grassland/Herbaceous',
            72: 'Sedge/Herbaceous',
            73: 'Lichens',
            74: 'Moss',
            81: 'Pasture/Hay',
            82: 'Cultivated Crops',
            90: 'Woody Wetlands',
            95: 'Emergent Herbaceous Wetlands',
            }

    if v in _ts:
        return _ts[v]

    return v

def pixel(f, x, y):
    from gio import geo_raster_ex as gx
    from gio import geo_base as gb
    from gio import geo_raster as ge

    _shp = gx.geo_band_stack_zip.from_shapefile(f)
    _val = _shp.read(gb.geo_point(x, y, ge.proj_from_epsg()))

    return _val

def pixels(x, y, tags=None):
    _tags = {
            'TCC (2015)': '/data/mfeng/data/tcc/list/tcc_global_dat_m.shp',
            'Water Freq (2010-2015)': '/data/mfeng/data/water/list/global_water_freq_2010_2015.shp',
            'Elevation': '/data/mfeng/data/dem/srtm/list/srtm_30m.shp',
            'NLCD 2011': '/data/mfeng/data/lc/nlcd/nlcd_2011_landcover_2011_edition_2014_10_10/extent.shp'
            }

    _vals = {}
    for _k, _f in list(_tags.items()):
        if tags is not None and _k not in tags:
            continue

        _vals[_k] = pixel(_f, x, y)

        if 'nlcd' in _k.lower():
            _vals[_k] = nlcd_text(_vals[_k])

    return _vals

def main(opts):
    print(pixels(-76.940678, 38.982370))

def usage():
    _p = environ_mag.usage(False)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

