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
    
def add_landsat_records(pt, ls, images, ndvi_func, date_s, date_e):
    import ee
    import datetime
    
    _landsat = ee.ImageCollection(images)
    _ls = _landsat.filterBounds(pt) #.filterDate('2013-04-11','2019-09-01');

    if date_s and date_e:
        _ls = _landsat.filterBounds(date_s, date_e)

    _list_image = _ls.map(ndvi_func)
    _list = _list_image.select("NDVI").getRegion(pt, 30)
    
    for _l in _list.getInfo()[1:]:
        _d = datetime.datetime.fromtimestamp(_l[3] / 1e3)
        _v = _l[4]

        if _v is None or _v < -1.0 or _v > 1.0:
            continue
        
        ls[_d] = _v
  
def gee_ndvi(x, y, date_s=None, date_e=None):
    import ee
    ee.Initialize()
    
    _pt = ee.Geometry.Point(x, y)
    _ls = {}

    add_landsat_records(_pt, _ls, 'LANDSAT/LC08/C01/T1_TOA', add_NDVI_8, date_s, date_e)
    add_landsat_records(_pt, _ls, 'LANDSAT/LE07/C01/T1_TOA', add_NDVI_457, date_s, date_e)
    add_landsat_records(_pt, _ls, 'LANDSAT/LT05/C01/T1_TOA', add_NDVI_457, date_s, date_e)
    add_landsat_records(_pt, _ls, 'LANDSAT/LT04/C01/T1_TOA', add_NDVI_457, date_s, date_e)

    return _ls

def plot(ds, t, f_out, width=1020, height=250, dpi=96):
    import matplotlib
    matplotlib.use('Agg')

    import matplotlib.pyplot as plt
    _fig = plt.figure(1, figsize=(int(width/dpi), int(height/dpi)))

    from matplotlib.ticker import MaxNLocator
    # import matplotlib.dates as mdates

    _axes = plt.axes([0.05, 0.15, 0.93, 0.70])
    
    _xs = []
    _ys = []
    
    for _d in sorted(ds.keys()):
        _xs.append(_d)
        _ys.append(ds[_d])

    plt.plot(_xs, _ys, 'go-', markersize=0.8, linewidth=0.1)
    
    if t:
        plt.title(t)

    _axes.xaxis.set_minor_locator(MaxNLocator(integer=True))
    _axes.xaxis.set_major_locator(MaxNLocator(integer=True))

    _axes.set_ylim([0, 1.05])

    _axes.grid(True, which='major', alpha=0.6, linewidth=1.5)
    _axes.grid(True, which='minor', alpha=0.3)

    _fig.savefig(f_out)
