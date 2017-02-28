#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: map_server.py
Author: Min Feng
Version: 0.1
Create: 2015-07-22 15:57:18
Description:
'''

import logging

def handle_error(request, response, exception):
	import json

	response.headers.add_header('Content-Type', 'application/json')
	result = {
			'status': 'error',
			'status_code': exception.code,
			'error_message': exception.explanation,
			}

	response.write(json.dumps(result))
	response.set_status(exception.code)

def get_ip_address():
	import subprocess

	_p = subprocess.Popen(['hostname', '-I'], stdout=subprocess.PIPE)
	_d = [_v.strip() for _v in _p.communicate()[0].split(' ') if _v.strip()]

	logging.info('ip list: ' + ', '.join(_d))
	if len(_d) == 0:
		raise Exception('failed to find ip address')

	_ip_in = [_v for _v in _d if _v.startswith('192.')]
	if len(_ip_in) == 1:
		return _ip_in[0]

	return _d[0]

def main(opts):
	_routes = [
			(r'/_(.+)', 'geo_map_serv.serv_op.op'),
			(r'/map/(.+)', 'geo_map_serv.serv_web.map_obj'),
			# (r'/web/(.+)', 'serv_web.web'),
			(r'/?([^_].*)', 'geo_map_serv.serv_web.web'),
			]

	_config = {}
	_config['webapp2_extras.sessions'] = {
			'secret_key': 'something-very-secret'
			}

	import webapp2

	_app = webapp2.WSGIApplication(routes=_routes, debug=True, config=_config)
	_app.error_handlers[400] = handle_error
	_app.error_handlers[404] = handle_error

	from gio import config
	_ip = config.cfg.get('general', 'host')
	if not _ip.strip():
		_ip = get_ip_address()

	print 'ip address:', _ip
	logging.info('ip address: ' + _ip)

	from paste import httpserver
	httpserver.serve(_app, host=_ip, port=config.get_at('general', 'port'))
	print 'done'

def usage():
	_p = environ_mag.usage(False)

	return _p

if __name__ == '__main__':
	from gio import environ_mag
	environ_mag.init_path()
	environ_mag.run(main, [environ_mag.config(usage())])

