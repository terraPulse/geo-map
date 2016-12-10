'''
File: build_tiles_make.py
Author: Min Feng
Version: 0.1
Create: 2015-09-10 15:46:23
Description: make tiling tasks
'''

import logging

def load_shp(f):
	from osgeo import ogr
	import geo_base_c as gb

	_shp = ogr.Open(f)
	if _shp == None:
		raise Exception('Failed to load shapefile ' + f)

	_lyr = _shp.GetLayer()
	_objs = []
	_area = None

	for _f in _lyr:
		_obj = gb.geo_polygon(_f.geometry().Clone())
		_ext = _obj.extent()

		_objs.append(_obj)
		if _area == None:
			_area = _ext
		else:
			_area = _area.union(_ext)

	import geo_raster_c as ge
	_prj = ge.proj_from_epsg(3857)

	_reg = _area.to_polygon().segment_ratio(30).project_to(_prj)
	return _reg.extent()

def load_img(f, fzip):
	import geo_raster_c as ge

	_prj = ge.proj_from_epsg(3857)
	_reg = ge.open(fzip.unzip(f)).extent().to_polygon().segment_ratio(30).project_to(_prj)

	return _reg.extent()

class color_table:

	def __init__(self, c):
		self._cs = self._color_table(c)

	@staticmethod
	def load(f, fzip):
		import os

		_ext = os.path.splitext(f.lower())[1]

		_f = f
		if _ext == '.shp':
			_f = color_table.load_sample(f)

		import geo_raster_c as ge
		_b = ge.open(fzip.unzip(_f)).get_band()

		if _b.color_table == None:
			return None
		else:
			return color_table(_b.color_table)

	def _color_table(self, c):
		_cs = {}
		if c == None:
			return None

		_rg = lambda x: min(max(0, x), 255)

		_c = c
		for i in xrange(_c.GetCount()):
			try:
				_v = _c.GetColorEntry(i)
			except:
				_v = _rg

			if len(_v) == 3:
				_v = list(_v) + [255]

			_cs[i] = map(_rg, _v)

		return _cs

	def save(self, f):
		_ls = []
		for _k, _v in self._cs.items():
			_ls.append('%s %s' % (_k, ','.join(map(str, _v))))

		with open(f, 'w') as _fo:
			_fo.write('\n'.join(_ls))

		return f

	@staticmethod
	def load_sample(f):
		from osgeo import ogr

		_shp = ogr.Open(f)
		if _shp == None:
			raise Exception('Failed to load shapefile ' + f)

		_lyr = _shp.GetLayer()
		for _f in _lyr:
			return _f.items()['FILE']

		raise None

class tiles:

	def __init__(self):
		import math
		import geo_raster_c as ge

		self.b = 6378137.0
		self.s = 256
		self.p = self.b * math.pi

		self.prj = ge.proj_from_epsg(3857)

	def list(self, level, ext=None):
		import geo_base_c as gb

		_r = (2 * self.p) / (2 ** level)

		_rows = 2 ** level
		_cols = 2 ** level

		_num = -1
		for _row in xrange(_rows):
			for _col in xrange(_cols):
				_num += 1

				_x = -self.p + (_col * _r)
				_y = -self.p + (_row * _r)

				_ext = gb.geo_extent(_x, _y, _x + _r, _y + _r, self.prj)
				if ext == None or _ext.is_intersect(ext):
					yield level, _num, _col, _row

	def cell(self, level):
		_r = (2 * self.p) / (2 ** level)
		return _r / self.s

	def extent(self, level, col, row):
		_r = (2 * self.p) / (2 ** level)
		_c = _r / self.s

		_x = -self.p + (col * _r)
		_y = -self.p + (row * _r)

		_geo = [_x, _c, 0, _y + _r, 0, -_c]

		import geo_raster_c as ge
		return ge.geo_raster_info(_geo, self.s, self.s, self.prj)

def make(f_inp, f_clr, levels, percent, d_out, fzip):
	import os
	import config

	# detect the extent of input file
	_ext = load_shp(f_inp) if f_inp.endswith('.shp') else load_img(f_inp, fzip)
	logging.info('detected extent %s' % str(_ext))
	print 'detected extent', _ext

	_f_clr = os.path.join(d_out, 'color.txt')
	if not f_clr:
		logging.info('load color table from the input data')
		_f_clr = color_table.load(f_inp, fzip).save(_f_clr)
		print 'loading color table', _f_clr
	else:
		import shutil
		shutil.copy(f_clr, _f_clr)

	if not _f_clr:
		raise Exception('failed to find color table')

	_tiles = tiles()

	_ps = []
	for _lev in xrange(levels[0], levels[1]+1):
		print ' - checking level', _lev, '(%.2f)' % _tiles.cell(_lev)
		for _lev, _num, _col, _row in _tiles.list(_lev, _ext):
			_ps.append((f_inp, _lev, _num, _col, _row, percent, _f_clr, d_out))

	logging.info('found %s task' % len(_ps))
	print 'found %s tasks' % len(_ps)

	print 'write map.html'
	import geo_raster_c as ge
	_ext_geo = _ext.to_polygon().segment_ratio(30).project_to(ge.proj_from_epsg()).extent()

	_f_out = os.path.join(d_out, 'map.html')
	with open(config.cfg.get('conf', 'openlayers_temp'), 'r') as _fi, open(_f_out, 'w') as _fo:
		_fo.write(_fi.read() % {
				'title': os.path.basename(f_inp),
				'xmin': _ext_geo.minx, 'xmax': _ext_geo.maxx,
				'ymin': _ext_geo.miny, 'ymax': _ext_geo.maxy,
				'zmin': levels[0], 'zmax': levels[1]
				})

	with open(os.path.join(d_out, 'tasks.txt'), 'wb') as _fo:
		import pickle
		pickle.dump(_ps, _fo)

def main():
	_opts = _init_env()

	from osgeo import gdal
	gdal.UseExceptions()

	import os

	_d_out = _opts.output
	os.path.exists(_d_out) or os.makedirs(_d_out)

	import file_unzip
	with file_unzip.file_unzip() as _zip:
		make(_opts.input, _opts.color, _opts.levels, _opts.percent, _opts.output, _zip)

def _usage():
	import argparse

	_p = argparse.ArgumentParser()
	_p.add_argument('--logging', dest='logging')
	_p.add_argument('--config', dest='config')
	_p.add_argument('--temp', dest='temp')

	_p.add_argument('-i', '--input', dest='input', required=True)
	_p.add_argument('-o', '--output', dest='output', required=True)
	_p.add_argument('-c', '--color', dest='color')
			# default='/data/glcf-st-004/data/workspace/fengm/prog/fcc_1975/v2/conf/colors/colors_dat.txt')
	_p.add_argument('-p', '--percent', dest='percent', default=None, type=int, help='target type, background type')
	_p.add_argument('-l', '--levels', dest='levels', default=[5, 10], nargs=2, type=int)

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

	if not config.cfg.has_section('conf'):
		config.cfg.add_section('conf')

	for _k, _v in _opts.__dict__.items():
		if _v != None:
			config.cfg.set('conf', _k, str(_v))


	import file_unzip as fz
	fz.clean(fz.default_dir(_opts.temp))

	return _opts

if __name__ == '__main__':
	main()

