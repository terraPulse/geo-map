'''
File: serv_op.py
Author: Min Feng
Version: 0.1
Create: 2016-04-28 11:34:49
Description:
'''

import serv_base
import logging

class op(serv_base.service_base):

	def __init__(self, request, response):
		serv_base.service_base.__init__(self, request, response)

	def _ndvi(self, x, y, frm=None):
		import mod_ndvi
		from gio import file_unzip
		from gio import config

		_l = config.get('general', 'ndvi_path')

		with file_unzip.file_unzip() as _zip:
			_f_tmp  = _zip.generate_file('', '.csv') if frm == 'csv' else None
			_rs = mod_ndvi.extract_NDVI(_l, x, y, 600, _f_tmp)
			if _f_tmp:
				self.output_file(_f_tmp)
			else:
				self.output_json(_rs)

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
		import identify_tile
		self.output_json(identify_tile.tile(x, y))

	def _pixel(self, x, y):
		import identify_pixel
		_vals = identify_pixel.pixels(x, y)

		self.output_json(''.join(['<div><b>%s:</b> %s</div>' % (_k, _vals[_k]) for _k in sorted(_vals.keys())]))

	def task(self, path):
		if path == 'ndvi':
			_x = self.pf('x')
			_y = self.pf('y')

			return self._ndvi(_x, _y, self.pp('frm', None))
			# return self._ndvi_chart(_x, _y)

		if path == 'tile':
			_x = self.pf('x')
			_y = self.pf('y')

			return self._wrs_tile(_x, _y)

		if path == 'pixel':
			_x = self.pf('x')
			_y = self.pf('y')

			return self._pixel(_x, _y)

		if path == 'user/login':
			_user = self.pp('user_name')
			_pass = self.pp('password')

			from gio import config
			if _user == config.get('conf', 'user', 'global') and _pass == config.get('conf', 'password', 'global'):
				self.output_json({'user_name': _user, 'real_name': 'Test'})
			else:
				raise Exception('authorization failed')

