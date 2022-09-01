
import logging

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
    
def shp_to_psql(f_shp, tag=None, overwrite=False):
    from gio import config
    from gio import file_mag
    
    if f_shp.lower().endswith('.shp'):
        _shp = file_mag.get(f_shp).get()
        if not _shp:
            logging.warning('failed to get the input shapefile')
            return None
    else:
        if not f_shp.startwith('PG:'):
            logging.warning('only supports shapefile or PG input')
            return None
        
    _g = lambda x: config.get('pgdb', x)
    if not _g('host'):
        raise Exception('no PostGIS connection provided')
        
    _con = 'PG:host=%s user=%s dbname=%s password=%s' % (_g('host'), _g('user'), _g('dbname'), _g('password'))
    
    import re
    _tag = 'map_%s' % (re.sub('[^\w\d]', '_', tag))
    
    _out = _con + ' tables=%s' % _tag
    if pg_lyr_exists(_out) and overwrite == False:
        logging.info('PG layer (%s) already exists' % _tag)
        return _out 
        
    _cmd = ("ogr2ogr -f 'PostgreSQL' '%s' '%s' -lco GEOMETRY_NAME=geom " \
            + "-lco FID=gid -lco PRECISION=no -nlt GEOMETRY -nln %s -overwrite") \
            % (_con, _shp, _tag)
    
    from gio import run_commands as run
    run.run(_cmd)
    
    if not pg_lyr_exists(_out):
        logging.error('failed to create PG layer %s' % _tag)
        return None
        
    return _out

def pg_lyr_exists(f, layer_name=None):
    from osgeo import ogr

    _shp = ogr.Open(f)
    if _shp is None:
        return False

    _lyr = _shp.GetLayer(layer_name) if layer_name else _shp.GetLayer()
    return _lyr is None or _lyr.GetLayerDefn().GetFieldCount() > 0
