#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
File: build_tiles_task.py
Author: Min Feng
Version: 0.1
Create: 2015-09-10 16:02:12
Description:
'''

def _make_tile(f, lev, num, col, row, pec, clr, out):
	from geo_map_util import map_tile
	map_tile.make_tile(f, lev, col, row, pec, clr, out)

def main(opts):
	import pickle
	import os
	from gio import config

	with open(os.path.join(config.get('conf', 'input'), opts.tag, 'tasks.txt'), 'rb') as _fi:
		_ps = pickle.load(_fi)

	from gio import multi_task
	_tt = multi_task.load(_ps, opts)
	print '%s tasks' % len(_tt)

	if opts.output:
		print 'updating output folder', opts.output
		_tt = [_t[:-2] + (config.get('conf', 'output'), ) for _t in _tt]

	multi_task.run(_make_tile, _tt, opts)

def usage():
	_p = environ_mag.usage(True)

	_p.add_argument('-i', '--input', dest='input')
	_p.add_argument('-t', '--tag', dest='tag', required=True)
	_p.add_argument('-o', '--output', dest='output')
	_p.add_argument('-a', '--aggregate', dest='aggregate')

	return _p

if __name__ == '__main__':
	from gio import environ_mag
	environ_mag.init_path()
	environ_mag.run(main, [environ_mag.config(usage())])

