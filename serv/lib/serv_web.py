

from . import serv_base
import logging

_jobs = []
_tods = []

class web(serv_base.service_base):

    def __init__(self, request):
        serv_base.service_base.__init__(self, request)

    def _add_maps(self, f, fzip):
        from gio import config
        from gio import obj
        import os

        _d_map = config.get('general', 'map_path')
        _fs = []
        for _d in sorted(os.listdir(_d_map)):
            _f = os.path.join(_d_map, _d, 'setting.ini')
            logging.debug('loading %s' % _f)
            if os.path.exists(_f):
                _obj = obj.load(_f)

                if _obj.get('visible', True) == False:
                    continue

                _tit = _obj.get('title', _d)
                _lin = '\tmap.addLayer(create_layer(\'/map/%s\', \'%s\'));' % (_d, _tit)
                _fs.append(_lin)

                logging.debug('add layer %s: %s' % (_tit, _d))

        if len(_fs) == 0:
            return f
        else:
            _f = fzip.generate_file('', '.js')
            _p = '// **map**'
            with open(_f, 'w') as _fo, open(f, 'r') as _fi:
                _fo.write(_fi.read().replace(_p, '\n'.join(_fs + ['\t' + _p])))

            return _f

    def task(self, path):
        import os
        import re
        from gio import config
        from gio import file_unzip
        from gio import file_mag

        _path = path
        if _path == '' or _path == '/':
            _path  = 'index.html'

        _d_web = config.get_at('general', 'web_path')
        _f_res = os.path.join(_d_web, _path)

        if file_mag.get(_f_res).exists():
            logging.error('no file found %s' % _f_res)
            return

        logging.debug('loading web path: ' + path)
        if re.search('js/map.*\.js', _f_res):
            with file_unzip.file_unzip() as _zip:
                return self.output_file(self._add_maps(_f_res, _zip))

        return self.output_file(_f_res)

_zips = {}

def load_zips(load=False):
    global _zips

    if not load:
        return _zips

    import os
    from gio import config
    from . import read_zip

    _root = config.get_at('general', 'map_path')
    for _f in os.listdir(_root):
        if _f.endswith('.zip'):
            _t = _f[:-4]
            if _t not in _zips:
                import sys
                sys.stdout.flush()

                _zips[_t] = read_zip.zip_file(os.path.join(_root, _f))

    return _zips

class map_obj(serv_base.service_base):

    def __init__(self, request, order='zx_y'):
        serv_base.service_base.__init__(self, request)
        self._tile_order = order

    def task(self, path):
        from geo_map_util import map_tile_parse
        return self.output_byte(path, map_tile_parse.get(path, self._tile_order))
        
        # from gio import file_unzip
        # with file_unzip.zip() as _zip:
        #     _f_out = _zip.generate_file('', '.png')
        #     with open(_f_out, 'wb') as _fo:
        #         _fo.write(map_tile_parse.get(path))
                
        #     return self.output_file(_f_out)

        # _zips = load_zips()
        # if _p not in _zips.keys():
        #     if os.path.exists(os.path.join(_d_web, _p + '.zip')):
        #         _zips = load_zips(True)

        # if _p in _zips:
        #     _r = _zips[_p].load(_v)
        #     if _r == None:
        #         if _v.endswith('.png'):
        #             return self.output_file(config.get_at('general', 'nodata_file'))
        #         raise Exception('failed to find page %s' % path)
        #     else:
        #         return self.output_byte(path, _r)
