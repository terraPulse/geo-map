#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: build_tiles_task.py
Author: Min Feng
Version: 0.1
Create: 2015-09-10 16:02:12
Description:
'''

def _make_tile(f, lev, num, col, row, pec, vals, solid_bg, clr, msk, out, params, opts):
    if opts.level_min is not None:
        if lev < opts.level_min:
            return

    if opts.level_max is not None:
        if lev > opts.level_max:
            return

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

    _out = os.path.join(config.get('conf', 'input'), opts.tag)

    with open(os.path.join(_out, 'tasks.txt'), 'rb') as _fi:
        _ps = pickle.load(_fi)

    from gio import multi_task
    _tt = multi_task.load(_ps, opts)
    print '%s tasks' % len(_tt)

    if opts.output:
        logging.info('updating output folder %s' % opts.output)
        _tt = [_t[:-2] + (config.get('conf', 'output'), ) for _t in _tt]

    _f_ini = os.path.join(_out, 'setting.ini')
    _met = {}

    if os.path.exists(_f_ini):
        logging.info('loading setting file: %s' % _f_ini)
        from gio import obj
        _met = obj.load(_f_ini)

    multi_task.run(_make_tile, _tt, opts, (_met, opts, ))

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-i', '--input', dest='input')
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

