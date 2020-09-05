'''
File: map_server2.py
Author: Min Feng
Version: 0.1
Create: 2017-10-03 18:33:50
Description:
'''

import logging

def get_ip_address():
    from gio import run_commands

    _d = [_v.strip() for _v in run_commands.run('hostname -I')[1].split(' ') if _v.strip()]
    logging.info('ip list: ' + ', '.join(_d))

    if len(_d) == 0:
        raise Exception('failed to find ip address')

    _ip_in = [_v for _v in _d if _v.startswith('192.')]
    if len(_ip_in) == 1:
        return _ip_in[0]

    return _d[0]

def main(opts):
    from gio import config
    from gio import logging_util

    config.load('map_server2')
    
    _ip = config.get('conf', 'host')
    if not (_ip and _ip.strip()):
        _ip = get_ip_address()

    logging.info('ip address: ' + _ip)

    _ssl_key = config.get('conf', 'ssl_key')
    _ssl_crt = config.get('conf', 'ssl_crt')
    _kernal = config.get('conf', 'kernal')

    _con = None
    if _ssl_key or _ssl_crt:
        logging.info('use SSL key %s, %s' % (_ssl_key, _ssl_crt))
        _con = '--certfile %s --keyfile %s ' % (_ssl_crt, _ssl_key)

    _port = config.getint('conf', 'port', 8090)
    _pnum = config.getint('conf', 'process', 10)

    _time_out = config.getint('conf', 'timeout', 60)
    _graceful_time_out = config.getint('conf', 'graceful_timeout', 60)

    _ps = []

    _ps.append('--timeout=%s' % _time_out)
    _ps.append('--graceful-timeout=%s' % _graceful_time_out)
    _ps.append('-w %s' % _pnum)

    _f_log = logging_util.find_log()
    _f_log_err = _f_log[:-4] + '_err.log'

    _ps.append('--access-logfile=%s' % _f_log)
    _ps.append('--error-logfile=%s' % _f_log_err)
    # _ps.append('--max-requests=10')

    if _kernal:
        _ps.append('-k ' + _kernal)

    import os
    from gio import logging_util

    _f_log_eee = logging_util.find_log()[:-9] + '_in.log'
    os.environ['G_LOG_S'] = _f_log_eee
    logging.info('log_s: %s' % _f_log_eee)

    # os.environ['G_INI_S'] = config.find_log()':-9' + '.ini'

    _cmd = 'gunicorn %s -b %s:%s %s %s' % (_con if _con else '', _ip, _port, ' '.join(_ps), 'geo_map_serv.serv_init:app')
    logging.info('command: %s' % _cmd)

    from gio import run_commands
    run_commands.run(_cmd, env=os.environ)

    # _app.run(host=_ip, port=config.getint('conf', 'port', 8090), \
    #         threaded=config.getboolean('conf', 'threaded', False), \
    #         ssl_context=_context, \
    #         processes=config.getint('conf', 'process', 3))

def usage():
    _p = environ_mag.usage(False)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])


