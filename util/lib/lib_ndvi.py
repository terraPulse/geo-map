'''
File: combine_ndvi_max.py
Author: Min Feng
Version: 0.1
Create: 2018-06-27 23:57:54
Description:
'''

def add_NDVI_8(image):
    _NDVI = image.normalizedDifference(["B5", "B4"]).rename('NDVI')
    _add_NDVI_1 = image.addBands(_NDVI)
    
    return _add_NDVI_1
    
def add_NDVI_457(image):
    _NDVI = image.normalizedDifference(["B4", "B3"]).rename('NDVI')
    _add_NDVI_1 = image.addBands(_NDVI)
    
    return _add_NDVI_1

def add_NDSI_8(image):
    _NDVI = image.normalizedDifference(["B3", "B6"]).rename('NDVI')
    _add_NDVI_1 = image.addBands(_NDVI)
    
    return _add_NDVI_1
    
def add_NDSI_457(image):
    _NDVI = image.normalizedDifference(["B2", "B5"]).rename('NDVI')
    _add_NDVI_1 = image.addBands(_NDVI)
    
    return _add_NDVI_1
    
def add_NDWI_8(image):
    _NDVI = image.normalizedDifference(["B3", "B5"]).rename('NDVI')
    _add_NDVI_1 = image.addBands(_NDVI)
    
    return _add_NDVI_1
    
def add_NDWI_457(image):
    _NDVI = image.normalizedDifference(["B2", "B4"]).rename('NDVI')
    _add_NDVI_1 = image.addBands(_NDVI)
    
    return _add_NDVI_1

def add_landsat_records(pt, ls, images, ndvi_func, date_s, date_e):
    import ee
    import datetime
    
    if date_s and date_e:
        if date_s >= date_e:
            return
            
    _landsat = ee.ImageCollection(images)
    _ls = _landsat.filterBounds(pt) #.filterDate('2013-04-11','2019-09-01');

    if date_s and date_e:
        _ls = _landsat.filterDate(date_s, date_e)

    _list_image = _ls.map(ndvi_func)
    _list = _list_image.select("NDVI").getRegion(pt, 30)
    
    for _l in _list.getInfo()[1:]:
        _d = datetime.datetime.fromtimestamp(_l[3] / 1e3)
        _v = _l[4]

        if _v is None or _v < -1.0 or _v > 1.0:
            continue
        
        ls[_d] = _v

def agg_monthly(ls):
    import datetime

    _ms = {}
    for _d, _k in ls.items():
        _t = datetime.datetime(_d.year, _d.month, 15)
        if _t not in _ms:
            _ms[_t] = []
        
        _ms[_t].append(_k)

    _ds = {}
    for _d, _vs in _ms.items():
        if len(_vs) == 1:
            _ds[_d] = _vs[0]
            continue

        _ds[_d] = sorted(_vs, reverse=True)[int(len(_vs) / 2)]

    return _ds

def agg_yearly(ls):
    import datetime

    _ms = {}
    for _d, _k in ls.items():
        _t = datetime.datetime(_d.year, 7, 1)
        if _t not in _ms:
            _ms[_t] = []
        
        _ms[_t].append(_k)

    _ds = {}
    for _d, _vs in _ms.items():
        if len(_vs) == 1:
            _ds[_d] = _vs[0]
            continue

        _ds[_d] = sorted(_vs, reverse=True)[int(len(_vs) / 2)]

    return _ds
  
def gee_ndvi(x, y, date_s=None, date_e=None):
    import ee
    ee.Initialize()
    
    _pt = ee.Geometry.Point(x, y)
    _ls = {}

    # add_landsat_records(_pt, _ls, 'LANDSAT/LC08/C01/T1_TOA', add_NDVI_8, date_s, date_e)
    # add_landsat_records(_pt, _ls, 'LANDSAT/LE07/C01/T1_TOA', add_NDVI_457, date_s, date_e)
    # add_landsat_records(_pt, _ls, 'LANDSAT/LT05/C01/T1_TOA', add_NDVI_457, date_s, date_e)
    # add_landsat_records(_pt, _ls, 'LANDSAT/LT04/C01/T1_TOA', add_NDVI_457, date_s, date_e)

    _s = lambda x: date_s if date_s and (date_s > x) else x
    _e = lambda x: date_e if date_e and (date_e < x) else x

    add_landsat_records(_pt, _ls, 'LANDSAT/LC08/C01/T1_TOA', add_NDVI_8, _s('2013-04-11'), _e('2019-09-01'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LE07/C01/T1_TOA', add_NDVI_457, _s('1999-01-01'), _e('2013-04-11'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LT05/C01/T1_TOA', add_NDVI_457, _s('1984-01-01'), _e('1999-01-01'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LT04/C01/T1_TOA', add_NDVI_457, _s('1982-08-22'), _e('1984-01-01'))

    return _ls

def gee_ndsi(x, y, date_s=None, date_e=None):
    import ee
    ee.Initialize()
    
    _pt = ee.Geometry.Point(x, y)
    _ls = {}

    _s = lambda x: date_s if date_s and (date_s > x) else x
    _e = lambda x: date_e if date_e and (date_e < x) else x

    add_landsat_records(_pt, _ls, 'LANDSAT/LC08/C01/T1_TOA', add_NDVI_8, _s('2013-04-11'), _e('2019-09-01'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LE07/C01/T1_TOA', add_NDVI_457, _s('1999-01-01'), _e('2013-04-11'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LT05/C01/T1_TOA', add_NDVI_457, _s('1984-01-01'), _e('1999-01-01'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LT04/C01/T1_TOA', add_NDVI_457, _s('1982-08-22'), _e('1984-01-01'))

    return _ls

def gee_ndwi(x, y, date_s=None, date_e=None):
    import ee
    ee.Initialize()
    
    _pt = ee.Geometry.Point(x, y)
    _ls = {}

    _s = lambda x: date_s if date_s and (date_s > x) else x
    _e = lambda x: date_e if date_e and (date_e < x) else x

    add_landsat_records(_pt, _ls, 'LANDSAT/LC08/C01/T1_TOA', add_NDVI_8, _s('2013-04-11'), _e('2019-09-01'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LE07/C01/T1_TOA', add_NDVI_457, _s('1999-01-01'), _e('2013-04-11'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LT05/C01/T1_TOA', add_NDVI_457, _s('1984-01-01'), _e('1999-01-01'))
    add_landsat_records(_pt, _ls, 'LANDSAT/LT04/C01/T1_TOA', add_NDVI_457, _s('1982-08-22'), _e('1984-01-01'))

    return _ls

def plot(ds, t, f_out, width=1020, height=250, dpi=96):
    import matplotlib
    matplotlib.use('Agg')

    import matplotlib.pyplot as plt
    _fig = plt.figure(1, figsize=(int(width/dpi), int(height/dpi)), dpi=dpi)

    from matplotlib.ticker import MaxNLocator
    # import matplotlib.dates as mdates

    _axes = plt.axes([0.05, 0.18, 0.93, 0.70])
    
    _xs = []
    _ys = []
    
    _ds = sorted(ds.keys())
    for _d in _ds:
        _xs.append(_d)
        _ys.append(ds[_d])

    plt.plot(_xs, _ys, 'go-', markersize=1.2, linewidth=0.20)
    
    if t:
        plt.title(t)

    _addy = True

    import matplotlib.dates as mdates

    # _fmt = mdates.DateFormatter('%m/%Y' if _addy else '%m/%y')
    _fmt = mdates.DateFormatter('%Y' if _addy else '%m/%y')
    _axes.xaxis.set_major_formatter(_fmt)

    # _axes.xaxis.set_major_locator(mdates.YearLocator(interval=12))
    _axes.xaxis.set_major_locator(mdates.YearLocator())
    _axes.xaxis.set_minor_locator(mdates.MonthLocator())

    # _axes.xaxis.set_minor_locator(MaxNLocator(integer=True))
    # _axes.xaxis.set_major_locator(MaxNLocator(integer=True))

    _axes.set_ylim([0, 1.05])

    import datetime
    _axes.set_xlim([datetime.datetime(_ds[0].year, 1, 1), datetime.datetime(_ds[-1].year, 12, 31)])

    _axes.grid(True, which='major', alpha=0.6, linewidth=1.0)
    _axes.grid(True, which='minor', alpha=0.3)

    for _t in _axes.yaxis.get_major_ticks():
        _t.label.set_fontsize(9)

    for _t in _axes.xaxis.get_major_ticks():
        _t.label.set_fontsize(9)
        if _addy:
            _t.label.set_rotation(35)
            _t.label.set_ha('center')
        else:
            _t.label.set_rotation(15)

    _fig.savefig(f_out)
