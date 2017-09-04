'''
File: colorize_raster.py
Author: Min Feng
Version: 0.1
Create: 2017-09-01 18:35:53
Description:
'''

def load_color_file(f):
	_ls = open(f).read().strip().splitlines()[2:]

	_vs = []
	_cs = {255: (255, 255, 255, 0)}

	_p = -1
	for _l in _ls:
		_p += 1

		_vv = _l.split(',')
		if len(_vv) != 6:
			raise Exception('color file cannot be accepted')

		_vs.append(float(_vv[0]))
		_cs[_p] = tuple(map(int, _vv[1:5]))

	return _vs, _cs

def main(opts):
	from gio import geo_raster as ge

	_vs, _cs = load_color_file(opts.color)

	_bnd = ge.open(opts.input).get_band().cache()
	_dat = _bnd.data

	print 'nodata:', _bnd.nodata

	import numpy as np

	_ddd = np.empty((_bnd.height, _bnd.width), dtype=np.uint8)
	_ddd.fill(255)

	if _bnd.nodata is not None:
		_ddd[_dat != _bnd.nodata] = 0

	for _i in xrange(len(_vs) - 1):
		_idx = (_dat >= _vs[_i]) & (_dat < _vs[_i + 1])
		_ddd[_idx] = _i

	if _bnd.nodata is not None:
		_ddd[_dat == _bnd.nodata] = 255

	from gio import file_unzip
	import os

	with file_unzip.file_unzip() as _zip:
		_d_tmp = _zip.generate_file()
		os.makedirs(_d_tmp)

		_f_out = os.path.join(_d_tmp, os.path.basename(opts.output))
		_clr = ge.map_colortable(_cs)
		_bnd.from_grid(_ddd, nodata=255).save(_f_out, color_table=_clr, opts=['compress=deflate', 'tiled=yes'])

		file_unzip.compress_folder(_d_tmp, os.path.dirname(opts.output), [])

def usage():
	_p = environ_mag.usage(False)

	_p.add_argument('-i', '--input', dest='input', required=True)
	_p.add_argument('-c', '--color', dest='color', required=True)
	_p.add_argument('-o', '--output', dest='output', required=True)

	return _p

if __name__ == '__main__':
	from gio import environ_mag
	environ_mag.init_path()
	environ_mag.run(main, [environ_mag.config(usage())])

