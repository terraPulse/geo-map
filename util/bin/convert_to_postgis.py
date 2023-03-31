#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
File: convert_to_postgis.py
Author: Min Feng
Description: convert a map tile layer to PostGIS based data source
'''

def copy_tiles(d_inp, d_out):
    import os
    
    if os.path.isdir(d_inp):
        _cmd = 'aws s3 cp %s %s --recursive' % (d_inp, d_out)
    else:
        _cmd = 'aws s3 cp %s %s' % (d_inp, d_out)
    
    from gio import run_commands as run
    run.run(_cmd)
    
def migrate(d_inp, tag_inp, d_out, tag_out):
    import os
    import re
    import logging
    from gio import obj
    from gio import config
    from gio import file_mag
    
    logging.info('migrate %s(%s) to %s(%s)' % (d_inp, tag_inp, d_out, tag_out))
    print('migrate %s(%s) to %s(%s)' % (d_inp, tag_inp, d_out, tag_out))
    
    _d_lyr = os.path.join(d_inp, tag_inp)
    _d_out = os.path.join(d_out, tag_out)
    
    _f_cfg = os.path.join(_d_lyr, 'setting.ini')
    _f_ccc = os.path.join(_d_out, 'setting.ini')
    
    if not config.getboolean('conf', 'overwrite') and file_mag.get(_f_ccc).exists():
        logging.warning('skip existed layer %s (%s)' % (d_inp, tag_inp))
        return False
    
    _b_cvt = d_inp == d_out and tag_inp == tag_out
    
    if not file_mag.get(_f_cfg).exists():
        logging.warning('no setting file (%s)' % _f_cfg)
        return False
    
    _cfg = obj.load(_f_cfg)
    _old = _cfg.get('version', 1) < 2
    
    if _old and _b_cvt:
        logging.warning('cannot convert version 1 map-tile layer')
        return False
    
    if  _old:
        _cfg.version = 2.0
    
    _inp = _cfg.file
    logging.info('input data file %s' % _cfg.file)
    
    if not (_inp.startswith('PG:') or _inp.lower().endswith('.shp')):
        logging.warning('the input file (%s) needs to be a shapefile or PG' % _inp)
        return False
        
    from geo_map_util import map_tile_util
    _con = map_tile_util.shp_to_psql(_inp, tag_out)
    if not _con:
        logging.error('failed to convert the file (%s) to PostGIS' % _inp)
        return False
        
    _cfg.file = _con
    _cfg.origin = _inp
    
    _old = _cfg.get('origin', '')
    if _old:
        _cfg.origin2 = _old
    
    logging.info('output setting file %s' % _f_ccc)
    _cfg.save(_f_ccc)
    
    if _b_cvt:
        return True
    
    _b_copy_tiles = config.getboolean('conf', 'copy_tiles', False)
    
    _ffs = [os.path.basename(str(_f)) for _f in file_mag.get(_d_lyr + '/').list(recursive=False)]
    if _b_copy_tiles:
        _ffs.append('tiles')
    
    for _f in _ffs:
        _n = _f
        
        if not _n or _n in ['setting.ini']:
            continue
        
        _f_inp = os.path.join(_d_lyr, _n)
        _f_out = os.path.join(_d_out, _n)
        
        # print('copying', _f, _is_tile)
        copy_tiles(_f_inp, _f_out)
    
    logging.info('add layer (%s) to map list' % (tag_out))
    from geo_map_util import map_tile_util
    map_tile_util.add_item_to_list(tag_out, d_out)
    
    return True

def main(opts):
    from gio import config
    _g = lambda x: config.get('conf', x)
    
    if not _g('input'):
        logging.error('no input folder provided')
        return
    
    _d_out = _g('output') if _g('output') else _g('input')
    _tag_out = _g('tag_out') if _g('tag_out') else _g('tag_inp')
    
    if not migrate(_g('input'), _g('tag_inp'), _d_out, _tag_out):
        return
    
    if not _d_out.startswith('s3://'):
        return
    
    # clean up the cached setting file
    import os
    from gio import file_mag
    
    _f_ini = file_mag.get(os.path.join(_d_out, _tag_out, 'setting.ini')).get()
    if os.path.exists(_f_ini):
        os.remove(_f_ini)

def usage():
    _p = environ_mag.usage(False)

    _p.add_argument('-i', '--input', dest='input')
    _p.add_argument('-t', '--tag-inp', dest='tag_inp', required=True)
    _p.add_argument('-n', '--tag-out', dest='tag_out')
    _p.add_argument('-c', '--copy-tiles', dest='copy_tiles', type='bool')
    _p.add_argument('-o', '--output', dest='output')
    
    _p.add_argument('-w', '--overwrite', dest='overwrite', type='bool')
    
    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())]) 