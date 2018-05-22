

import serv_base
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
            logging.info('loading %s' % _f)
            if os.path.exists(_f):
                _obj = obj.load(_f)

                if _obj.get('visible', True) == False:
                    continue

                _tit = _obj.get('title', _d)
                _lin = '\tmap.addLayer(create_layer(\'/map/%s\', \'%s\'));' % (_d, _tit)
                _fs.append(_lin)

                logging.info('add layer %s: %s' % (_tit, _d))

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

        _path = path
        if _path == '' or _path == '/':
            _path  = 'index.html'

        _d_web = config.get_at('general', 'web_path')
        _f_res = os.path.join(_d_web, _path)

        if not os.path.exists(_f_res):
            logging.error('no file found %s' % _f_res)
            return
            # raise Exception('no file found %s' % _f_res)

        logging.info('loading web path: ' + path)
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
    import read_zip

    _root = config.get_at('general', 'map_path')
    for _f in os.listdir(_root):
        if _f.endswith('.zip'):
            _t = _f[:-4]
            if _t not in _zips:
                print ' + loading zip', _f,
                import sys
                sys.stdout.flush()

                _zips[_t] = read_zip.zip_file(os.path.join(_root, _f))
                print 'done'

    return _zips

class map_obj(serv_base.service_base):

    def __init__(self, request):
        from gio import config

        serv_base.service_base.__init__(self, request)
        self.min_level = config.getint('conf', 'min_level', 9)

    def _dmap_mag(self, f, f_out):
        from gio import config
        _pro = config.get('general', 'dmap', None)
        if not _pro:
            return

        if len(_jobs) > 50 or f in _jobs:
            logging.warning('exceed 50 tasks (%s)' % len(_jobs))
            return
            # return _tods.append(f)

        _jobs.append(f)
        print '+', len(_jobs)

        try:
            return self._dmap(f, f_out)
            # import time
            # time.sleep(2.0)
        finally:
            print '-', len(_jobs)
            _jobs.pop()

    def _dmap(self, f, f_out):
        import os
        from gio import config

        _pro = config.get('general', 'dmap')
        _pro = _pro.replace('%[', '%(').replace(']', ')')

        if not _pro:
            return

        if os.path.exists(f):
            return

        import re
        _m = re.search('([^\/]+)\/(\d+)\/(\d+)\/(\d+).png', f)
        _c = _pro % {'tag': _m.group(1), 'level': _m.group(2), 'col': _m.group(3), 'row': _m.group(4)}

        # print _c
        from gio import run_commands
        _rs = run_commands.run(_c)

        logging.info('create tile: %s (%s)' % (_c, _rs[0]))

        return _rs[0] == 0
        # print 'done', _c

    def _dmap_mag_single(self, f, f_out):
        # if len(_jobs) > 10 or f in _jobs:
        #     logging.warning('exceed 10 tasks (%s)' % len(_jobs))
        #     return

        import re
        _m = re.search('([^\/]+)\/(\d+)\/(\d+)\/(\d+).png', f)
        _lev = int(_m.group(2))
        if _lev < self.min_level:
            logging.warning('skip level %s < %s' % (_lev, self.min_level))
            return

        # _jobs.append(f)

        _col = int(_m.group(3))
        _row = int(_m.group(4))

        print '+ %s (%s, %s, %s)' % (len(_jobs), _lev, _col, _row)

        try:
            return self._dmap_single(f, f_out)
            # import time
            # time.sleep(2.0)
        finally:
            pass
            # print '-', len(_jobs)
            # _jobs.pop()

    def _dmap_single(self, f_inp, f_out):
        from gio import config
        import os
        import re

        if os.path.exists(f_out):
            return

        _m = re.search('([^\/]+)\/(\d+)\/(\d+)\/(\d+).png', f_inp)

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
            if os.path.exists(_f_ini):
                from gio import obj
                _met = obj.load(_f_ini)

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

        logging.debug('generated tile %s' % f_inp)

    def _format_path(self, p):
        if p.startswith('/a/'):
            return '/'.join([''] + p.split('/')[3:])

        return p

    def _split_vars(self, c):
        _vs = c.split('&')
        _ps = {}

        for _v in _vs:
            if '=' in _v:
                _n, _t = _v.split('=')
                _ps[_n] = _t
            else:
                _ps[_v] = None

        return _ps

    def task(self, path):
        import os
        from gio import config

        if not path:
            path = '/'

        _p, _v = path.split('/', 1) if '/' in path else ('', path)
        _d_web = config.get_at('general', 'map_path')

        if os.path.exists(os.path.join(_d_web, _p) if _p else _d_web):
            logging.info('loading web path: ' + path)
            _f = self._format_path(os.path.join(_d_web, path))

            if not os.path.exists(_f):
                # if self.pp('cache') == '1':
                logging.info('generating map tile (%s)' % _f)

                self._dmap_mag_single(path, _f)

                # _f = config.get_at('general', 'nodata_file')

                # if os.path.exists(_f) == False:
                #     print path, _f

                if not os.path.exists(_f):
                    _f = config.get_at('general', 'nodata_file')

            return self.output_file(_f)

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

        raise Exception('no module found %s' % _p)

