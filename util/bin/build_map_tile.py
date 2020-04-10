#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Author:  Min Feng
Version: 0.1
Create: 2016-12-05
Description: create map tiles for the given tile code
'''

def main(opts):
	_tag = opts.tag.strip()

	if opts.level < 9:
		return

	from gio import config

	_inp = config.get(_tag, 'file', '')
	if not _inp:
		return

	import os
	_out = os.path.join(config.get('conf', 'output'), _tag)
	_fot = os.path.join(_out, str(opts.level), str(opts.col), str(opts.row) + '.png')
	
	from gio import file_mag

	if file_mag.get(_fot).exists():
		return

	_pec = config.getint(_tag, 'percent', None)
	_clr = config.get(_tag, 'color', None)
	if _clr is None:
		_clr = os.path.join(_out, 'color.txt')

	import map_tile
	map_tile.make_tile(_inp, opts.level, opts.col, opts.row, \
			_pec, _clr, _out)

	if file_mag.get(_fot).exists():
		import sys
		sys.exit(1)

def usage():
	_p = environ_mag.usage(False)

	_p.add_argument('-t', '--tag', dest='tag', required=True)
	_p.add_argument('-l', '--level', dest='level', required=True, type=int)
	_p.add_argument('-c', '--col', dest='col', required=True, type=int)
	_p.add_argument('-r', '--row', dest='row', required=True, type=int)

	return _p

if __name__ == '__main__':
	from gio import environ_mag
	environ_mag.init_path()
	environ_mag.run(main, [environ_mag.config(usage())])
