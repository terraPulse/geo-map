'''
File: map_tile_parse.py
Author: Min Feng
Description: parse the URL, process and return the output tile
'''

import logging

_jobs = []
_tods = []

class map_tile:

    def __init__(self):
        from gio import config
        self.min_level = config.getint('conf', 'min_level', 9)

    def _dmap_mag(self, f, f_out):
        from gio import config
        _pro = config.get('general', 'dmap', None)
        if not _pro:
            return

        if len(_jobs) > 50 or f in _jobs:
            logging.warning('exceed 50 tasks (%s)' % len(_jobs))
            return

        _jobs.append(f)
        try:
            return self._dmap(f, f_out)
            # import time
            # time.sleep(2.0)
        finally:
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

        from gio import run_commands
        _rs = run_commands.run(_c)

        logging.debug('create tile: %s (%s)' % (_c, _rs[0]))

        return _rs[0] == 0

    def _dmap_mag_single(self, f, met):
        try:
            return self._dmap_single(f, met)
        finally:
            pass

    def _load_setting(self, f_inp):
        import re
        import os

        _m = re.search('^(.+)\/(\d+)\/(\d+)\/(\d+).png$', f_inp)

        _tag = _m.group(1)
        _lev = int(_m.group(2))
        _col = int(_m.group(3))
        _row = int(_m.group(4))

        from gio import obj
        from gio import config
        from gio import file_mag
        from gio import obj

        _out = os.path.join(config.get('general', 'map_path'), _tag)
        _f_ini = file_mag.get(os.path.join(_out, 'setting.ini')).get()

        if _f_ini:
            _met = obj.load(_f_ini)
        else:
            _met = obj.obj()

        _met.lev = _lev
        _met.row = _row
        _met.col = _col
        _met.tag = _tag

        return _met

    def _dmap_single(self, f_inp, met):
        from gio import config
        import os

        _tag = met.tag
        _lev = met.getint('lev')
        _col = met.getint('col')
        _row = met.getint('row')

        _out = os.path.join(config.get('general', 'map_path'), _tag)

        _inp = None
        _agg = None
        _valid_vals = None
        _solid_bg = False
        _mask = None
        _min_level = self.min_level

        logging.info('+ %s (%s, %s, %s)' % (len(_jobs), _lev, _col, _row))

        if config.cfg.has_section(_tag):
            _inp = config.get(_tag, 'file', '')
            _pec = config.getint(_tag, 'percent', None)
            _clr = config.get(_tag, 'color', None)

        _inp = met.get('file')
        _pec = met.getint('percent')
        _clr = met.get('color')
        _solid_bg = met.get('solid_bg')
        _agg = met.get('agg')

        _valid_vals = met.get('valid_vals')
        _mask = met.get('mask')
        _min_level = met.get('min_dynamic_level', self.min_level)

        if _lev < _min_level:
            logging.warning('skip level %s < %s' % (_lev, _min_level))
            return

        if _inp is None:
            return

        if _clr is None:
            _clr = os.path.join(_out, 'color.txt')

        from geo_map_util import map_tile
        map_tile.make_tile(_inp, _lev, _col, _row, _pec, _valid_vals, _solid_bg, _clr, _mask, _out, agg=_agg, opts=met)

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

    def _normalize_path(self, p):
        import re
        _m = re.search('^(.+)\/(\d+)\/([_\-]?\d+)\/([_\-]?\d+)(.png)$', p)
        if not _m:
            return None

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

    def get(self, path):
        import os
        from gio import config
        from gio import file_mag

        if not path:
            path = '/'

        _q, _v = path.split('/', 1) if '/' in path else ('', path)
        _d_web = config.get_at('general', 'map_path')

        logging.debug('map path: %s' % _d_web)

        _loc = self._normalize_path(path)

        _met = self._load_setting(_loc)
        if _met.get('version', 1.0) >= 2.0:
            _out = os.path.join(_d_web, _met.tag, 'tiles', '%s' % _met.lev, '%s' % _met.col, '%s.png' % _met.row)
        else:
            _out = os.path.join(_d_web, _met.tag, '%s' % _met.lev, '%s' % _met.col, '%s.png' % _met.row)

        logging.debug('request tile %s' % _out)

        if not _out.endswith('.png'):
            raise Exception('failed to find %s' % _loc)

        from gio import file_unzip
        from gio import config

        with file_unzip.zip() as _zip:
            _cache = config.get('conf', 'cache', None)
            if not _cache:
                _tmp = _zip.generate_file()
                config.set('conf', 'cache', os.path.join(_tmp, 'cache'))

            if not file_mag.get(_out).exists():
                logging.debug('generating map tile (%s)' % _out)
                self._dmap_mag_single(_loc, _met)

                logging.debug('get tile %s' % _out)
                if not file_mag.get(_out).exists():
                    _out = config.get('general', 'nodata_file')

            return _out

        raise Exception('no module found %s' % _q)

