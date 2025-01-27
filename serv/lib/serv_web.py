

from . import serv_base
import logging

_jobs = []
_tods = []

class web(serv_base.service_base):

    def __init__(self, request):
        serv_base.service_base.__init__(self, request)

    def _add_maps_list(self, f_map, host, fzip):
        import os
        from gio import file_mag

        _f_map = file_mag.get(os.path.join(f_map, 'list.txt'))
        if not _f_map.exists():
            return []

        _fs = []
        for _l in sorted(_f_map.read().decode('utf-8').strip().splitlines()):
            _ll = '\tcreate_layer(\'%s/map/%s\', \'%s\', false, map);' % (host, _l, _l)
            _fs.append(_ll)
            
        return _fs

    def _add_maps_dir(self, d_map, host, fzip):
        from gio import config
        from gio import obj
        import os

        _d_map = d_map
        
        _fs = []
        for _d in sorted(os.listdir(_d_map)):
            _f = os.path.join(_d_map, _d, 'setting.ini')
            logging.debug('loading %s' % _f)
            if os.path.exists(_f):
                _obj = obj.load(_f)

                if _obj.get('visible', True) == False:
                    continue

                _tit = _obj.get('title', _d)
                _lin = '\tmap.addLayer(create_layer(\'%s/map/%s\', \'%s\'));' % (host, _d, _tit)
                _fs.append(_lin)

                logging.debug('add layer %s: %s' % (_tit, _d))
                
        return _fs

    def _add_maps(self, f, fzip):
        from gio import file_mag
        from gio import config
        from gio import obj
        import os

        _d_map = config.get('general', 'map_path')
        _host = config.get('general', 'map_host', '')
        
        logging.info('map path: %s (%s)' % (_d_map, os.path.isdir(_d_map)))
        
        _fs = self._add_maps_dirs(_d_map, _host, fzip) if os.path.isdir(_d_map) \
                else self._add_maps_list(_d_map, _host, fzip)

        if len(_fs) == 0:
            return f
        else:
            _f = fzip.generate_file('', '.js')
            _p = '// **map**'
            with open(_f, 'w') as _fo:
                _t = file_mag.get(f).read()
                if not _t:
                    return None
                _fo.write(_t.decode('utf-8').replace(_p, '\n'.join(_fs + ['\t' + _p])))
            return _f

    def _set_host(self, f, fzip):
        from gio import file_mag

        _host = config.get('general', 'map_host', '')
        
        _f = fzip.generate_file('', '.js')
        _p = '{{host}}'
        with open(_f, 'w') as _fo:
            _t = file_mag.get(f).read()
            if not _t:
                return None
            _fo.write(_t.decode('utf-8').replace(_p, _sev))
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

        if not file_mag.get(_f_res).exists():
            logging.error('no file found %s' % _f_res)
            return

        logging.debug('loading web path: ' + path)
        if re.search('js/map.*\.js', _f_res):
            with file_unzip.file_unzip() as _zip:
                return self.output_file(self._add_maps(_f_res, _zip))
                
        if re.search('js/map_controls\.js', _f_res):
            with file_unzip.file_unzip() as _zip:
                return self.output_file(self._set_host(_f_res, _zip))

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

        _r = map_tile_parse.get(path, self._tile_order)
        if _r is None:
            return None

        return self.output_byte(path, _r)
        
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
