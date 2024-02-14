#!/usr/bin/env python
# -*- coding: utf-8 -*-

def copy_tiles(d_inp, d_out):
    import os
    
    if os.path.isdir(d_inp):
        _cmd = 'aws s3 cp %s %s --recursive' % (d_inp, d_out)
    else:
        _cmd = 'aws s3 cp %s %s' % (d_inp, d_out)
    
    from gio import run_commands as run
    run.run(_cmd)

def migrate(d_inp, tag, d_out):
    import os
    import re
    from gio import obj
    from gio import config
    from gio import file_mag
    
    _d_lyr = os.path.join(d_inp, tag)
    _d_out = os.path.join(d_out, tag)
    
    _f_cfg = os.path.join(_d_lyr, 'setting.ini')
    _f_ccc = os.path.join(_d_out, 'setting.ini')
    
    print('migrate', tag)
    if file_mag.get(_f_ccc).exists():
        return
    
    _cfg = obj.load(_f_cfg)
    _old = _cfg.get('version', 1) < 2
    
    if not _old:
        _d_out = os.path.join(d_out, tag)
        return copy_tiles(_d_lyr, _d_out)
    
    _cfg.version = 2.0
    
    print('output', _f_ccc)
    _cfg.save(_f_ccc)
    
    for _f in os.listdir(_d_lyr):
        if _f in ['setting.ini']:
            continue
        
        _is_tile = re.match('\d+', _f) is not None
        
        _f_inp = os.path.join(_d_lyr, _f)
        _f_out = os.path.join(_d_out, 'tiles', _f) if _is_tile else os.path.join(_d_out, _f)
        
        # print('copying', _f, _is_tile)
        copy_tiles(_f_inp, _f_out)

def main(opts):
    migrate(opts.input, opts.tag, opts.output)

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-i', '--input', dest='input', required=True)
    _p.add_argument('-t', '--tag', dest='tag', required=True)
    _p.add_argument('-o', '--output', dest='output', required=True)
    
    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())]) 