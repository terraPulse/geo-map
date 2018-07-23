'''
File: identify_pixel.py
Author: Min Feng
Version: 0.1
Create: 2016-04-30 02:09:18
Description:
'''

def pixel(f, x, y):
	from gio import geo_raster_ex as gx
	from gio import geo_base as gb
	from gio import geo_raster as ge

	_shp = gx.geo_band_stack_zip.from_shapefile(f)
	_val = _shp.read(gb.geo_point(x, y, ge.proj_from_epsg()))

	return _val

def pixels(x, y):
	_tags = {
			'tcc_2001': '/data/glcf-nx-002/data/PALSAR/vcf_test/vcf/com3_tif/list/shp/tcc_gls2000.shp',
			'tcc_2005': '/data/glcf-nx-002/data/PALSAR/vcf_test/vcf/com3_tif/list/shp/tcc_gls2005.shp',
			'tcc_2010': '/data/glcf-nx-003/fengm/vcf/vcf_2010_4/list/shp/global_tcc_tm.shp'
			}

	_vals = {}
	for _k, _f in _tags.items():
		_vals[_k] = pixel(_f, x, y)

	return _vals

def main():
	_opts = _init_env()

	print pixels(100, 40)

def _usage():
	import argparse

	_p = argparse.ArgumentParser()
	_p.add_argument('--logging', dest='logging')
	_p.add_argument('--config', dest='config')
	_p.add_argument('--temp', dest='temp')

	return _p.parse_args()

def _init_env():
	import os, sys

	_dirs = ['lib', 'libs']
	_d_ins = [os.path.join(sys.path[0], _d) for _d in _dirs if \
			os.path.exists(os.path.join(sys.path[0], _d))]
	sys.path = [sys.path[0]] + _d_ins + sys.path[1:]

	_opts = _usage()

	import logging_util
	logging_util.init(_opts.logging)

	import config
	config.load(_opts.config)

	import file_unzip as fz
	fz.clean(fz.default_dir(_opts.temp))

	return _opts

if __name__ == '__main__':
	main()
