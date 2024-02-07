#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: build_tiles_task.py
Author: Min Feng
Version: 0.1
Create: 2015-09-10 16:02:12
Description:
'''

import logging

def parse_levels(lvls):
    import re
    
    _ls = []
    for _l in lvls:
        _m = re.match('^[0-9]+$', _l)
        if _m:
            _ls.append(int(_l))
            continue
            
        _m = re.match('^([0-9]+)\-([0-9]+)$', _l)
        if _m:
            for _z in range(int(_m.group(1)), int(_m.group(2)) + 1):
                _ls.append(_z)
            continue
                
        raise Exception('failed to parse {}'.format(_l))
        
    return _ls

def remove_files(f):
    from gio import config
    from gio import file_mag
    
    if config.getboolean('conf', 'aws_cli'):
        from gio import run_commands as run
        logging.info('remove tiles use awscli command')
        _cmd = 'aws s3 rm %s --recursive' % f
        return run.run(_cmd)

    file_mag.get(f).remove()

def clean_tiles(lvls, out):
    import os
    from gio import file_mag
    
    if len(lvls) == 1 and lvls[0].lower() in ('true', '*', 'all'):
        logging.info('cleaning tiles')
        print('cleaning tiles')
        return remove_files(os.path.join(out, 'tiles'))

    _lvls = parse_levels(lvls)
    logging.info('cleaning tiles at levels (%s)' % _lvls)
    print('cleaning tiles at levels (%s)' % _lvls)
    
    for _l in _lvls:
        logging.info('cleaning level (%s)' % _l)
        remove_files(os.path.join(out, 'tiles', str(_l)))

def main(opts):
    import os
    import logging
    from gio import config
    from gio import file_mag
    
    config.set('conf', 'skip_low_levels', False)
    # config.set('conf', 'keep_nodata_tiles', True)
    config.set('general', 'map_path', config.get('conf', 'input'))
    
    _out = os.path.join(config.get('conf', 'input'), opts.tag)
    _f_ini = opts.setting or os.path.join(_out, 'setting.ini')
    
    if not file_mag.get(_f_ini).exists():
        logging.error('failed to find setting file: %s' % _f_ini)
        return
        
    from gio import obj
    _met = obj.load(file_mag.get(_f_ini).get())
        
    if _met.version < 2.0:
        logging.warning('skip cleaning tiles for old versions (<2.0)')
    else:
        clean_tiles(opts.levels, _out)            

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-d', '-i', '--input', dest='input')
    _p.add_argument('-t', '--tag', dest='tag', required=True)
    _p.add_argument('-o', '--output', dest='output')
    _p.add_argument('-s', '--setting', dest='setting')
    _p.add_argument('-c', '--cache', dest='cache')
    
    _p.add_argument('-l', '--levels', dest='levels', nargs='*', required=True, \
            help='remove the tiles previously generated for the layer')
    _p.add_argument('-a', '--aws-cli', dest='aws_cli', type='bool')

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

