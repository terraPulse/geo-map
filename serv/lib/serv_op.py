'''
File: serv_op.py
Author: Min Feng
Version: 0.1
Create: 2016-04-28 11:34:49
Description:
'''

from . import serv_base
import logging

class op(serv_base.service_base):

    def __init__(self, request):
        serv_base.service_base.__init__(self, request)

    def _loc(self, tag, x, y, v):
        logging.info('location query: tag (%s), pt (%s, %s)' % (tag, x, y))

        from geo_map_util import identify_layer as il
        return self.output_json(il.loc(tag, x, y))

    def _reg(self, tag, reg, v):
        logging.info('reg query: tag (%s)' % (tag, ))

        from geo_map_util import identify_layer as il
        return self.output_json(il.reg(tag, reg))

    def _cat(self, tag, reg, v):
        logging.info('cat query: tag (%s)' % (tag, ))

        from geo_map_util import identify_layer as il
        return self.output_json(il.reg(tag, reg, True))

    def _ndvi(self, x, y, frm='png'):
        from geo_map_util import mod_ndvi
        from gio import file_unzip
        from gio import config

        _l = config.get('general', 'ndvi_path')
        if _l.startswith('http:'):
            _url = _l + ('x=%s&y=%s' % (x, y))
            logging.info('URL: %s' % _url)

            import requests
            _r = requests.get(_url)
            return self.output_json(_r.json())

        with file_unzip.file_unzip() as _zip:
            _f_tmp  = _zip.generate_file('', '.csv') if frm == 'csv' else None
            _rs = mod_ndvi.extract_NDVI(_l, x, y, 600, _f_tmp)
            if _f_tmp:
                return self.output_file(_f_tmp)
            else:
                return self.output_json(_rs)

    def _gee_index(self, x, y, frm=None, w=1020, h=250, tag='ndvi', agg=None, s=None, e=None):
        from geo_map_util import gee_ndvi as lib_ndvi

        _x, _y = x, y

        _rs = None

        if tag == 'ndvi':
            _rs = lib_ndvi.gee_ndvi(_x, _y, date_s=s, date_e=e)
        elif tag == 'ndwi':
            _rs = lib_ndvi.gee_ndwi(_x, _y, date_s=s, date_e=e)
        elif tag == 'ndsi':
            _rs = lib_ndvi.gee_ndsi(_x, _y, date_s=s, date_e=e)
        else:
            raise Exception('unsupported index %s' % tag)

        if agg:
            if agg == 'month':
                _rs = lib_ndvi.agg_monthly(_rs)
            elif agg == 'year':
                _rs = lib_ndvi.agg_yearly(_rs)
            else:
                raise Exception('unsupported aggregation type %s' % agg)

        from gio import file_unzip
        with file_unzip.zip() as _zip:
            if not frm or frm == 'json':
                _ls = []
                for _r in sorted(_rs.keys()):
                    _ls.append((_r.strftime('%Y-%m-%d'), '%.3f' % _rs[_r]))
                return self.output_json({'data': _ls})

            _t = 'ndvi_%.6f_%.6f' % (_x, _y)

            if frm.lower() == 'png':
                _f_tmp  = _zip.generate_file('', '.png')
                lib_ndvi.plot(_rs, None, _f_tmp, w, h)
                with open(_f_tmp, 'rb') as _fi:
                    return self.output_byte(_t + '.png', _fi.read(), False)
            else:
                _ls = ['date,ndvi']
                for _r in sorted(_rs.keys()):
                    _ls.append('%s,%.3f' % (_r.strftime('%Y-%m-%d'), _rs[_r]))

                _f_tmp  = _zip.generate_file('', '.csv')
                _zip.save('\n'.join(_ls), _f_tmp)

                with open(_f_tmp, 'rb') as _fi:
                    return self.output_byte(_t + '.csv', _fi.read())

            raise Exception('unsupported format %s' % frm)

    def _wrs_tile(self, x, y):
        from . import identify_tile
        return self.output_json(identify_tile.tile(x, y))

    def _pixel(self, tag, x, y, vtype='json', reg=None):
        logging.info('pixel query: tag (%s), pt (%s, %s)' % (tag, x, y))

        if tag == 'lc':
            if reg:
                raise Exception('extract LC pixel does not support reg parameter')

            from . import identify_pixel_lc
            _vals = identify_pixel_lc.pixels(x, y)
            vtype = 'html'
        else:
            from . import identify_pixel
            _vals = identify_pixel.pixel(tag, x, y, reg)

        if vtype == 'json':
            return self.output_json(_vals)

        if vtype == 'html':
            _to_lon = lambda v: '%s%s' % (abs(v), 'E' if v >= 0 else 'W')
            _to_lat = lambda v: '%s%s' % (abs(v), 'N' if v >= 0 else 'S')

            _txt = '<div><b>%s, %s</b></div><hr/>' % (_to_lon(x), _to_lat(y))
            return self.output_json(''.join([_txt] + ['<div><b>%s:</b> %s (%s)</div>' % \
                    (_k, ('-' * (_vals[_k] / 2)) if _vals[_k] is not None else '', \
                    _vals[_k]) for _k in sorted(_vals.keys())]))

    def _forest_info(self, x, y):
        from gio import config
        _cmd = config.get('conf', 'cmd_forest', \
                'detect_forest_change_pt.py --config $G_INI/detect_forest_change_test.ini -o {f} -c {x} {y}')

        from gio import file_unzip
        with file_unzip.file_unzip() as _zip:
            _f_tmp = _zip.generate_file('', '.png')

            from gio import run_commands
            _c = _cmd.format(**{'x': x, 'y': y, 'f': _f_tmp})

            logging.info('RUN: ' + _c)
            run_commands.run(_c)

            return self.output_file(_f_tmp)

    def task(self, path):
        if path == 'ndvi':
            _x = self.pf('x')
            _y = self.pf('y')

            return self._ndvi(_x, _y, self.pp('frm', None))

        if path == 'gee_ndvi':
            _x = self.pf('x')
            _y = self.pf('y')

            return self._gee_index(_x, _y, self.pp('format', self.pp('frm', None)), \
                    self.pi('w'), self.pi('h'), tag=self.pp('tag', 'ndvi'), agg=self.pp('agg'), \
                    s=self.pp('s'), e=self.pp('e'))

        if path == 'ndvi_p':
            _x = self.pf('x')
            _y = self.pf('y')
            _d = self.pp('data', 'NDVI')

            logging.info('request index: %s, %s (%s)' % (_x, _y, _d))

            import requests
            # _json = requests.get('http://terrapulse.com:8080/_ndvi?x=%s&y=%s' % (_x, _y))
            # _json = requests.get('http://52.54.49.254:8080/_ndvi?x=%s&y=%s' % (_x, _y))
            _json = requests.get('http://10.0.1.11:8080/_ndvi?x=%s&y=%s&data=%s' % (_x, _y, _d))

            return self.output_json(_json.json())

        if path == 'tile':
            _x = self.pf('x')
            _y = self.pf('y')

            return self._wrs_tile(_x, _y)

        if path == 'pixel':
            _tag = self.pp('tag', 'lc')
            _v = self.pp('v', 'json')
            _x = self.pf('x')
            _y = self.pf('y')
            _reg = self.pp('reg')

            return self._pixel(_tag, _x, _y, _v, _reg)

        if path == 'query/loc':
            _tag = self.pp('tag')
            _v = self.pp('v', 'json')
            _x = self.pf('lon', self.pf('x'))
            _y = self.pf('lat', self.pf('y'))

            return self._loc(_tag, _x, _y, _v)

        if path == 'query/reg':
            _tag = self.pp('tag')
            _v = self.pp('v', 'json')
            _geo = self.pp('geo')

            return self._reg(_tag, _geo, _v)

        if path == 'query/cat':
            _tag = self.pp('tag')
            _v = self.pp('v', 'json')
            _geo = self.pp('geo')

            return self._cat(_tag, _geo, _v)

        if path == 'forest':
            _x = self.pf('x')
            _y = self.pf('y')

            return self._forest_info(_x, _y)

        if path == 'user/login':
            _user = self.pp('user_name')
            _pass = self.pp('password')

            from gio import config
            if _user == config.get('conf', 'user', 'global') and _pass == config.get('conf', 'password', 'global'):
                return self.output_json({'user_name': _user, 'real_name': 'Test'})
            else:
                raise Exception('authorization failed')
