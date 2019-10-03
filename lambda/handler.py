'''
Provide map tile service through Lambda

Author: Min Feng
Date: 10/03/2019
'''

def init_path():
    import os
    import sys
    
    _cwd = os.getcwd()
    _env = os.environ
    
    _out = '/tmp'

    _env['PYTHONPATH'] = os.path.join(_cwd, 'lib')
    _env['G_INI'] = os.path.join(_out, 'ini')
    _env['G_LOG'] = os.path.join(_out, 'log')
    _env['G_TMP'] = os.path.join(_out, 'tmp')
    _env['PATH'] = _env['PATH'] + ':' + os.path.join(_cwd, 'libs') + ':' + os.path.join(_cwd, 'bin')
    _env['LD_LIBRARY_PATH'] = _cwd + ':' + os.path.join(_cwd, 'libs')
    _env['GDAL_DATA'] = os.path.join(_cwd, 'local', 'share', 'gdal')
    
    _dirs = ['lib', 'libs']
    _d_ins = [os.path.join(sys.path[0], _d) for _d in _dirs if \
            os.path.exists(os.path.join(sys.path[0], _d))]
    sys.path = [sys.path[0]] + _d_ins + sys.path[1:]
    
    from gio import config
    config.load('config.ini')
    
    _tmp = _env['G_TMP']
    config.set('conf', 'temp', _tmp)
    config.set('conf', 'cache', os.path.join(_tmp, 'cache'))
    config.set('conf', 'enable_cache_lock', False)

def _normalize_path(p):
    import re
    _m = re.search('^/map/(.+)\/(\d+)\/([_\-]?\d+)\/([_\-]?\d+)(.png)$', p)
    if not _m:
        return p

    _tag = _m.group(1)
    _lev = int(_m.group(2))
    _col = _m.group(3)
    _row = _m.group(4)

    _num = 2 ** _lev

    if _col[0] in ('_', '-'):
        _col = _num - int(_col[1:]) - 1
    else:
        _col = int(_col)

    if _row[0] in ('_', '-'):
        _row = _num - int(_row[1:]) - 1
    else:
        _row = int(_row)

    return '%s/%s/%s/%s%s' % (_tag, _lev, _col, _row, _m.group(5))
    
def _dmap(f_inp):
    from gio import config
    from gio import file_mag
    import os
    import re

    _m = re.search('^(.+)\/(\d+)\/(\d+)\/(\d+).png$', f_inp)

    _tag = _m.group(1)
    _lev = int(_m.group(2))
    _col = int(_m.group(3))
    _row = int(_m.group(4))

    _out = os.path.join(config.get('general', 'map_path'), _tag)
    _inp = None
    _agg = None
    _valid_vals = None
    _solid_bg = False
    _mask = None
    
    if config.cfg.has_section(_tag):
        _inp = config.get(_tag, 'file', '')
        _pec = config.getint(_tag, 'percent', None)
        _clr = config.get(_tag, 'color', None)
    else:
        _f_ini = os.path.join(_out, 'setting.ini')
        
        if file_mag.get(_f_ini).exists():
            from gio import obj
            _met = obj.load(file_mag.get(_f_ini).get())

            _inp = _met.get('file')
            _pec = _met.getint('percent')
            _clr = _met.get('color')
            _solid_bg = _met.get('solid_bg')
            _agg = _met.get('agg')

            _valid_vals = _met.get('valid_vals')
            _mask = _met.get('mask')

    if _inp is None:
        return

    if _clr is None:
        _clr = os.path.join(_out, 'color.txt')
        
    from geo_map_util import map_tile
    map_tile.make_tile(_inp, _lev, _col, _row, _pec, _valid_vals, _solid_bg, _clr, _mask, _out, agg=_agg, opts=_met)
    
def _output_file(f):
    from gio import file_mag
    import base64
    
    with open(file_mag.get(f).get(), 'rb') as _fi:
        return {
              "isBase64Encoded": True,
              "statusCode": 200,
              "headers": { "content-type": "image/png"},
              "body":  base64.b64encode(_fi.read())
            }

def handler(event, context):
    import logging
    
    init_path()
    
    # _ps = event['queryStringParameters']
    _path = event['path']
    
    # import re
    # _m = re.match('^\/map\/(.+)/(\-?[\d\.]+)\/(\-?[\d\.]+)\/(\-?[\d\.]+)\.png$', _path)
    
    # _p = _m.group(1)
    # _z = int(_m.group(2))
    # _x = int(_m.group(3))
    # _y = int(_m.group(4))
    
    import os
    from gio import config
    from gio import file_mag
    
    _d_web = config.get('general', 'map_path')
    _path = _normalize_path(_path)
    _f = os.path.join(_d_web, _path)
    
    if file_mag.get(_f).exists():
        return _output_file(_f)
        
    _dmap(_path)
    if not file_mag.get(_f).exists():
        _f = config.get_at('general', 'nodata_file')
        
    return _output_file(_f)
