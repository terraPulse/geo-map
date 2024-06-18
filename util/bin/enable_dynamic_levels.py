#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: enable_dynamic_levels.py
Author: Min Feng
Version: 0.1
Create: 2023-11-2020 16:02:12
Description:
'''

import logging

def map_tile_levels(rep, tag, lvls):
    from gio import file_mag
    import json
    
    _f = f'{rep}/{tag}/setting.ini'
    _q = file_mag.get(_f)
    
    if not _q.exists():
        print(f'failed to find layer {tag}')
        return
    
    logging.info('loading layer setting file: {}'.format(str(_q)))
    _c = json.loads(_q.read().decode('utf-8'))
    
    _c['processed_levels'] = lvls
    _q.write(json.dumps(_c, indent=4))
    
    print(f'enabled layer with levels {lvls}')
    
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
    
def main(opts):
    from gio import config
    
    _rep = config.get('conf', 'input')
    logging.info(f'repository: {_rep}')
    
    map_tile_levels(_rep, opts.tag, parse_levels(opts.levels))
    if config.getboolean('conf', 'execute'):
        from gio import run_commands
        
        print('generate map tiles')
        _cmd = 'build_tiles_task.py -t %s ' % (opts.tag, )
        # _agg = ' -a %s ' % opts.agg if opts.agg else ''
        _tsk = '-in %s -ip %s -ts %s %s -tw %s -to %s' % ( \
                opts.instance_num, opts.instance_pos, opts.task_num, \
                        '-se' if opts.skip_error else '', opts.time_wait, opts.task_order)
        run_commands.run(_cmd + _tsk)

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-i', '--input', dest='input')
    _p.add_argument('-t', '--tag', dest='tag', required=True)
    _p.add_argument('-l', '--levels', dest='levels', nargs='*', required=True)
    _p.add_argument('-e', '--execute', dest='execute', type='bool')

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])