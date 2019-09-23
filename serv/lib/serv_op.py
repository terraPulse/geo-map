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

    def _ndvi(self, x, y, frm=None):
        from . import mod_ndvi
        from gio import file_unzip
        from gio import config

        _l = config.get('general', 'ndvi_path')

        with file_unzip.file_unzip() as _zip:
            _f_tmp  = _zip.generate_file('', '.csv') if frm == 'csv' else None
            _rs = mod_ndvi.extract_NDVI(_l, x, y, 600, _f_tmp)
            if _f_tmp:
                return self.output_file(_f_tmp)
            else:
                return self.output_json(_rs)

    def _ndvi_chart(self, x, y):
        from gio import file_unzip
        from gio import run_commands
        import os

        with file_unzip.file_unzip() as _zip:
            _d_tmp  = _zip.generate_file()
            os.makedirs(_d_tmp)

            _d_dat = '/data/glcf-nx-001/jnagol/data/CBR_2015_proc/NDVI_stacks'
            _cmd = 'Rscript Z_jot_plot_NDVI_TS_server_side.R %s %s %s %s' % (_d_tmp, _d_dat, y, x)

            run_commands.run(_cmd, cwd='/data/glcf-st-004/data/workspace/fengm/serv/script')

            _f_img = os.path.join(_d_tmp, 'Z_jot_plot.png')
            if os.path.exists(_f_img):
                logging.info('loading NDVI (%s, %s) %s' % (x, y, _f_img))
                return self.output_file(_f_img)

            raise Exception('no file found %s' % _f_img)

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
            print(_c)

            logging.info('RUN: ' + _c)
            run_commands.run(_c)

            return self.output_file(_f_tmp)

    def task(self, path):
        if path == 'ndvi':
            _x = self.pf('x')
            _y = self.pf('y')

            return self._ndvi(_x, _y, self.pp('frm', None))
            # return self._ndvi_chart(_x, _y)

        if path == 'ndvi_p':
            _x = self.pf('x')
            _y = self.pf('y')

            import requests
            # _json = requests.get('http://terrapulse.com:8080/_ndvi?x=%s&y=%s' % (_x, _y))
            _json = requests.get('http://52.54.49.254:8080/_ndvi?x=%s&y=%s' % (_x, _y))

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
