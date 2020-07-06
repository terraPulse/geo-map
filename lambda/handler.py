'''
Provide map tile service through Lambda

Author: Min Feng
Date: 10/03/2019
'''

def init_path():
    import os
    # import sys

    _cwd = os.getcwd()
    _env = os.environ

    _out = '/tmp'

    # _env['PYTHONPATH'] = os.path.join(_cwd, 'lib')
    _env['G_INI'] = os.path.join(_out, 'ini')
    _env['G_LOG'] = os.path.join(_out, 'log')
    _env['G_TMP'] = os.path.join(_out, 'tmp')
    # _env['PATH'] = _env['PATH'] + ':' + os.path.join(_cwd, 'libs') + ':' + os.path.join(_cwd, 'bin')
    # _env['LD_LIBRARY_PATH'] = _cwd + ':' + os.path.join(_cwd, 'libs')
    # _env['GDAL_DATA'] = os.path.join(_cwd, 'local', 'share', 'gdal')

    # _dirs = ['lib', 'libs']
    # _d_ins = [os.path.join(sys.path[0], _d) for _d in _dirs if \
    #         os.path.exists(os.path.join(sys.path[0], _d))]
    # sys.path = [sys.path[0]] + _d_ins + sys.path[1:]

    from gio import config
    # config.load('config.ini')

    _tmp = _env['G_TMP']
    config.set('conf', 'temp', _tmp)
    config.set('conf', 'cache', os.path.join(_tmp, 'cache'))
    config.set('conf', 'enable_cache_lock', False)
    config.set('general', 'nodata_file', 's3://geo-map-tiles/etc/nodata.png')

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
    # import logging
    init_path()

    # _ps = event['queryStringParameters']
    _path = event['path']

    # import re
    # _m = re.match('^\/map\/(.+)/(\-?[\d\.]+)\/(\-?[\d\.]+)\/(\-?[\d\.]+)\.png$', _path)

    # _p = _m.group(1)
    # _z = int(_m.group(2))
    # _x = int(_m.group(3))
    # _y = int(_m.group(4))

    from geo_map_util import map_tile_parse
    _f = map_tile_parse.map_tile().get(_path)

    return _output_file(_f)
