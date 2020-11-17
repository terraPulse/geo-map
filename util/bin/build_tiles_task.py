#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: build_tiles_task.py
Author: Min Feng
Version: 0.1
Create: 2015-09-10 16:02:12
Description:
'''

def _make_tile(f, lev, num, col, row, pec, vals, solid_bg, clr, msk, out, params, opts, d_out):
    if opts.level_min is not None:
        if lev < opts.level_min:
            return

    if opts.level_max is not None:
        if lev > opts.level_max:
            return
        
    if d_out:
        import os
        out = d_out
        clr = os.path.join(d_out, os.path.basename(clr))

    # if not (lev == 7 and col == 11 and row == 97):
    #     return

    from geo_map_util import map_tile
    map_tile.make_tile(f, lev, col, row, pec, vals, solid_bg, clr, msk, out, \
            agg=params.get('agg', None), opts=params)

def main(opts):
    import pickle
    import os
    from gio import config
    import logging
    from gio import file_mag

    _out = os.path.join(config.get('conf', 'input'), opts.tag)

    with open(file_mag.get(os.path.join(_out, 'tasks.txt')).get(), 'rb') as _fi:
        _ps = pickle.load(_fi)

    from gio import multi_task
    _tt = multi_task.load(_ps, opts)
    print('%s tasks' % len(_tt))
    
    _d_out = config.get('conf', 'output')
    if _d_out:
        logging.info('updating output folder %s' % _d_out)
        _tt = [_t[:-2] + (_d_out, ) for _t in _tt]

    _f_ini = os.path.join(_out, 'setting.ini')
    _met = {}

    if file_mag.get(_f_ini).exists():
        logging.info('loading setting file: %s' % _f_ini)
        from gio import obj
        _met = obj.load(file_mag.get(_f_ini).get())

    multi_task.run(_make_tile, _tt, opts, (_met, opts, _out))
    print()

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-d', '-i', '--input', dest='input')
    _p.add_argument('-t', '--tag', dest='tag', required=True)
    _p.add_argument('-o', '--output', dest='output')
    _p.add_argument('-c', '--cache', dest='cache')

    _p.add_argument('--level-min', dest='level_min', type=int)
    _p.add_argument('--level-max', dest='level_max', type=int)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

