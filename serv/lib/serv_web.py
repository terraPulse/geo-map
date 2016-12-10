

import serv_base
import logging

_jobs = []
_tods = []

class web(serv_base.service_base):

	def __init__(self, request, response):
		serv_base.service_base.__init__(self, request, response)

	def task(self, path):
		import os
		from gio import config

		_d_web = config.get_at('general', 'web_path')
		_f_res = os.path.join(_d_web, path)

		if os.path.exists(_f_res):
			logging.info('loading web path: ' + path)
			return self.output_file(_f_res)

		raise Exception('no file found %s' % _f_res)

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

	def __init__(self, request, response):
		serv_base.service_base.__init__(self, request, response)

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
		if len(_jobs) > 10 or f in _jobs:
			logging.warning('exceed 10 tasks (%s)' % len(_jobs))
			return
			# return _tods.append(f)

		_jobs.append(f)
		print '+', len(_jobs)

		try:
			return self._dmap_single(f, f_out)
			# import time
			# time.sleep(2.0)
		finally:
			print '-', len(_jobs)
			_jobs.pop()

	def _dmap_single(self, f_inp, f_out):
		from gio import config
		import os
		import re

		_m = re.search('([^\/]+)\/(\d+)\/(\d+)\/(\d+).png', f_inp)

		_tag = _m.group(1)
		_lev = int(_m.group(2))
		_col = int(_m.group(3))
		_row = int(_m.group(4))

		if not config.cfg.has_section(_tag):
			return

		_inp = config.get(_tag, 'file', '')
		if not _inp:
			return

		if os.path.exists(f_out):
			return

		_pec = config.getint(_tag, 'percent', None)
		_clr = config.get(_tag, 'color', None)

		_out = os.path.join(config.get('conf', 'output'), _tag)

		if _clr is None:
			_clr = os.path.join(_out, 'color.txt')
        #
		# _c = _pro % {'tag': _m.group(1), 'level': _m.group(2), 'col': _m.group(3), 'row': _m.group(4)}

		import map_tile
		map_tile.make_tile(_inp, _lev, _col, _row, _pec, _clr, _out)
		logging.info('generated tile %s' % f_inp)

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

		_p, _v = path.split('/', 1)

		_d_web = config.get_at('general', 'map_path')

		if os.path.exists(os.path.join(_d_web, _p)):
			logging.info('loading web path: ' + path)
			_f = self._format_path(os.path.join(_d_web, path))

			if not os.path.exists(_f):
				# if self.pp('cache') == '1':
				self._dmap_mag_single(path, _f)

				# _f = config.get_at('general', 'nodata_file')

				# if os.path.exists(_f) == False:
				# 	print path, _f

				if not os.path.exists(_f):
					_f = config.get_at('general', 'nodata_file')

			return self.output_file(_f)

		_zips = load_zips()
		if _p not in _zips.keys():
			if os.path.exists(os.path.join(_d_web, _p + '.zip')):
				_zips = load_zips(True)

		if _p in _zips:
			_r = _zips[_p].load(_v)
			if _r == None:
				if _v.endswith('.png'):
					return self.output_file(config.get_at('general', 'nodata_file'))
				raise Exception('failed to find page %s' % path)
			else:
				return self.output_byte(path, _r)

		raise Exception('no module found %s' % _p)

