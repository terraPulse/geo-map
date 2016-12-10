#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: map_server.py
Author: Min Feng
Version: 0.1
Create: 2015-07-22 15:57:18
Description:
'''

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

def main(opts):
	_routes = [
			(r'/_(.+)', 'geo_map_serv.serv_op.op'),
			(r'/map/(.+)', 'geo_map_serv.serv_web.map_obj'),
			# (r'/web/(.+)', 'serv_web.web'),
			(r'/?([^_].*)', 'geo_map_serv.serv_test.test'),
			]

	_config = {}
	_config['webapp2_extras.sessions'] = {
			'secret_key': 'something-very-secret'
			}

	import webapp2

	_app = webapp2.WSGIApplication(routes=_routes, debug=True, config=_config)
	_app.error_handlers[400] = handle_error
	_app.error_handlers[404] = handle_error

	from paste import httpserver
	from gio import config
	httpserver.serve(_app, host=config.get_at('general', 'host'), port=config.get_at('general', 'port'))
	print 'done'

def usage():
	_p = environ_mag.usage(False)

	return _p

if __name__ == '__main__':
	from gio import environ_mag
	environ_mag.init_path()
	environ_mag.run(main, [environ_mag.config(usage())])

