'''
File: map_server2.py
Author: Min Feng
Version: 0.1
Create: 2017-10-03 18:33:50
Description:
'''

import logging

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

def op_req(path):
    import re
    from flask import request
    from geo_map_serv import serv_op, serv_web

    # return '%s_____' % request.values['test']

    _m = re.match('_(.+)', path)
    if _m:
        return serv_op.op(request).get(_m.group(1))

    _m = re.match('map/(.+)', path)
    if _m:
        return serv_web.map_obj(request).get(_m.group(1))

    return serv_web.web(request).get(path)

def op(path):
    try:
        _r = op_req(path)
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

    if _r is None:
        raise Exception('failed to process the request')

    _r.headers["Cache-Control"] = 'no-cache, no-store, must-revalidate'
    _r.headers["Pragma"] = "no-cache"
    _r.headers["Expires"] = "0"
    _r.headers['Cache-Control'] = 'public, max-age=0'
    _r.headers['Access-Control-Allow-Origin'] = '*'

    return _r

    # from flask import abort
    # abort(404)

def main(opts):
    from flask import Flask
    from gio import config

    _app = Flask(__name__)

    _app.add_url_rule('/', 'index', op, defaults={'path': ''}, methods=["GET", "POST", "PUT"])
    _app.add_url_rule('/<path:path>', 'index', op, methods=["GET", "POST", "PUT"])
    _app.register_error_handler(404, not_found)

    if config.getboolean('conf', 'debug', False) == False:
        _app.register_error_handler(Exception, handle_error)

    from gio import config
    _ip = config.get('conf', 'host')
    if not (_ip and _ip.strip()):
        _ip = get_ip_address()

    logging.info('ip address: ' + _ip)

    _ssl_key = config.get('conf', 'ssl_key')
    _ssl_crt = config.get('conf', 'ssl_crt')

    _context = None
    if _ssl_key or _ssl_crt:
        # from OpenSSL import SSL
        # _context = SSL.Context(SSL.SSLv23_METHOD)
        # if _ssl_key:
        #     logging.info('use SSL key' % _ssl_key)
        #     _context.use_privatekey_file(_ssl_key)
        # if _ssl_crt:
        #     logging.info('use SSL crt' % _ssl_crt)
        #     _context.use_certificate_file(_ssl_crt)
        logging.info('use SSL key %s, %s' % (_ssl_key, _ssl_crt))
        _context = (_ssl_crt, _ssl_key)

    _app.run(host=_ip, port=config.getint('conf', 'port', 8090), \
            threaded=config.getboolean('conf', 'threaded', False), \
            ssl_context=_context, \
            processes=config.getint('conf', 'process', 3))

def usage():
    _p = environ_mag.usage(False)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])


