'''
File: serv_test.py
Author: Min Feng
Version: 0.1
Create: 2016-04-28 11:36:07
Description:
'''

import serv_base
import logging

class test(serv_base.service_base):

	def __init__(self, request, response):
		serv_base.service_base.__init__(self, request, response)

	def task(self, path):
		import os
		from gio import config

		_path = path
		if _path == '' or _path == '/':
			_path  = 'index.html'

		_d_web = config.get_at('general', 'test_path')
		_f_res = os.path.join(_d_web, _path)

		if os.path.exists(_f_res):
			logging.info('loading web path: ' + path)
			return self.output_file(_f_res)

		raise Exception('no file found %s' % _f_res)

