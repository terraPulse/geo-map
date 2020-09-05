'''
File: serv_init.py
Author: Min Feng
Version: 0.1
Create: 2017-11-14 14:11:03
Description:
'''

def not_found(error):
    return 'error (%s)' % error.code, error.code, {'Content-Type': 'application/json'}

def handle_error(error):
    import json
    from flask import make_response

    _res = {
            'status': 'error',
            'status_code': 500,
            'error_message': str(error),
            }

    return make_response((json.dumps(_res), 500, {'Content-Type': 'application/json'}))

def op_req(path):
    import re
    from flask import request
    from . import serv_op, serv_web

    _m = re.match('_(.+)', path)
    if _m:
        return serv_op.op(request).get(_m.group(1))

    _m = re.match('map/(.+)', path)
    if _m:
        return serv_web.map_obj(request).get(_m.group(1))

    return serv_web.web(request).get(path)

def op(path):
    import logging

    try:
        _r = op_req(path)
        if _r is None:
            raise Exception('failed to process request')

        _r.headers["Pragma"] = "no-cache"
        _r.headers["Expires"] = "0"
        _r.headers['Cache-Control'] = 'public, max-age=0'
        _r.headers['Access-Control-Allow-Origin'] = '*'

        return _r
    except KeyboardInterrupt:
        print('\n\n* User stopped the program')
        import sys
        sys.exit(0)
    except Exception as err:
        import traceback

        logging.error(traceback.format_exc())
        logging.error(str(err))

        print('\n\n* Error:', err)
        raise err

    # from flask import abort
    # abort(404)

def init():
    from flask import Flask
    from gio import config
    from gio import logging_util

    config.load('map_server2')

    import os
    _f_log = os.environ['G_LOG_S']
    logging_util.init(_f_log, True)

    _app = Flask(__name__)

    _app.add_url_rule('/', 'index', op, defaults={'path': ''}, methods=["GET", "POST", "PUT"])
    _app.add_url_rule('/<path:path>', 'index', op, methods=["GET", "POST", "PUT"])
    _app.register_error_handler(404, not_found)

    if config.getboolean('conf', 'debug', False) == False:
        _app.register_error_handler(Exception, handle_error)

    return _app

app = init()

