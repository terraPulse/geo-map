#!/usr/bin/env python
# -*- coding: utf-8 -*-

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
	from gio import geo_base as gb

	_shp = ogr.Open(f)
	if _shp is None:
		raise Exception('Failed to load shapefile ' + f)

	_lyr = _shp.GetLayer()
	_objs = []
	_area = None

	for _f in _lyr:
		_obj = gb.geo_polygon(_f.geometry().Clone())
		_ext = _obj.extent()

		_objs.append(_obj)
		if _area is None:
			_area = _ext
		else:
			_area = _area.union(_ext)

	from gio import geo_raster as ge
	_prj = ge.proj_from_epsg(3857)

	_reg = _area.to_polygon().segment_ratio(30).project_to(_prj)
	return _reg.extent()

def load_img(f, fzip):
	from gio import geo_raster as ge

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

		from gio import geo_raster as ge
		_b = ge.open(fzip.unzip(_f)).get_band()

		if _b.color_table is None:
			return None
		else:
			return color_table(_b.color_table)

	def _color_table(self, c):
		_cs = {}
		if c is None:
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
		if _shp is None:
			raise Exception('Failed to load shapefile ' + f)

		_lyr = _shp.GetLayer()
		for _f in _lyr:
			return _f.items()['FILE']

		raise None

class tiles:

	def __init__(self):
		import math
		from gio import geo_raster as ge

		self.b = 6378137.0
		self.s = 256
		self.p = self.b * math.pi

		self.prj = ge.proj_from_epsg(3857)

	def list(self, level, ext=None):
		from gio import geo_base as gb

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
				if ext is None or _ext.is_intersect(ext):
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

		from gio import geo_raster as ge
		return ge.geo_raster_info(_geo, self.s, self.s, self.prj)

def make(f_inp, f_clr, levels, title, percent, d_out, fzip):
	import os

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

	# print 'write map.html'
	# from gio import geo_raster as ge
	# _ext_geo = _ext.to_polygon().segment_ratio(30).project_to(ge.proj_from_epsg()).extent()

	# _f_out = os.path.join(d_out, 'map.html')
	# with open(config.cfg.get('conf', 'openlayers_temp'), 'r') as _fi, open(_f_out, 'w') as _fo:
	# 	_fo.write(_fi.read() % {
	# 			'title': os.path.basename(f_inp),
	# 			'xmin': _ext_geo.minx, 'xmax': _ext_geo.maxx,
	# 			'ymin': _ext_geo.miny, 'ymax': _ext_geo.maxy,
	# 			'zmin': levels[0], 'zmax': levels[1]
	# 			})

	print 'write to', os.path.join(d_out, 'tasks.txt')
	with open(os.path.join(d_out, 'tasks.txt'), 'wb') as _fo:
		import pickle
		pickle.dump(_ps, _fo)

	from gio import obj
	_obj = obj.obj()

	_obj.file = f_inp
	if percent is not None:
		_obj.percent = percent
	if title:
		_obj.title = title

	_obj.save(os.path.join(d_out, 'setting.ini'))

def main(opts):
	from osgeo import gdal
	gdal.UseExceptions()

	from gio import config

	import os
	_d_out = os.path.abspath(os.path.join(config.get('conf', 'output'), opts.tag))
	os.path.exists(_d_out) or os.makedirs(_d_out)

	from gio import file_unzip
	with file_unzip.file_unzip() as _zip:
		make(os.path.abspath(config.get('conf', 'input')), config.get('conf', 'color'), \
				opts.levels, opts.title, opts.percent, _d_out, _zip)

def usage():
	_p = environ_mag.usage(False)

	_p.add_argument('-i', '--input', dest='input', required=True)
	_p.add_argument('-o', '--output', dest='output')
	_p.add_argument('-c', '--color', dest='color')
	_p.add_argument('-t', '--tag', dest='tag', required=True)
	_p.add_argument('--title', dest='title')
	_p.add_argument('-p', '--percent', dest='percent', default=None, type=int, help='target type, background type')
	_p.add_argument('-l', '--levels', dest='levels', default=[5, 11], nargs=2, type=int)

	return _p

if __name__ == '__main__':
	from gio import environ_mag
	environ_mag.init_path()
	environ_mag.run(main, [environ_mag.config(usage())])

