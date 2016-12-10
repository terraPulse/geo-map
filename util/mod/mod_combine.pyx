import numpy as np
import logging
cimport numpy as np
cimport cython

@cython.boundscheck(False)
@cython.wraparound(False)

def update(bbs, bs1, bs2, idx):
	import params

	# bs1[1].data[bs1[0].data == params.VAL_WATER] = 0.50
	# bs2[1].data[bs2[0].data == params.VAL_WATER] = 0.50

	# bs1[1].data[bs1[0].data == params.VAL_CLOUD] = 0.50
	if None in bs2:
		return

	if type(None) in [type(_b.data) for _b in bs2]:
		return

	bs2[1].data[bs2[0].data == params.VAL_CLOUD] = 0.50

	# bs1[0].data[bs1[0].data == params.VAL_CLOUD] = params.VAL_NONFOREST
	# bs2[0].data[bs2[0].data == params.VAL_CLOUD] = params.VAL_NONFOREST

	# import mod_grid
	# _dat = (bs2[1].data > bs1[1].data) & (bs1[0].data != bs1[0].nodata)
	# mod_grid.update(bs1[0].data, _dat, bs2[0].data)
	# mod_grid.update(bs1[1].data, _dat, bs2[1].data)

	_b1_bnd = bs1[0]
	# _b1_err = bs1[1]

	_b2_bnd = bs2[0]
	_b2_err = bs2[1]

	cdef int _rows = _b1_bnd.height, _cols = _b1_bnd.width
	cdef int _row, _col, _v1, _v2, _nodata = _b1_bnd.nodata
	cdef float _e

	cdef np.ndarray[np.uint8_t, ndim=2] _dat1 = _b1_bnd.data
	cdef np.ndarray[np.uint8_t, ndim=2] _dat2 = _b2_bnd.data

	# cdef np.ndarray[np.float32_t, ndim=2] _err1 = _b1_err.data
	cdef np.ndarray[np.float32_t, ndim=2] _err2 = _b2_err.data

	for _row in xrange(_rows):
		for _col in xrange(_cols):
			_v1 = _dat1[_row, _col]
			if _v1 == _nodata:
				continue

			_v2 = _dat2[_row, _col]
			if _v2 == _nodata:
				continue

			_e = _err2[_row, _col]

			_i = _row * _cols + _col
			_m = bbs[_i]

			if _v2 not in _m:
				_m[_v2] = [1, _e, idx]
			else:
				_m[_v2][0] += 1
				_m[_v2][1] += _e

def output(bbs, bs1):
	import params

	_b_bnd = bs1[0]
	_b_err = bs1[1]
	_b_idx = bs1[2]

	cdef int _rows = _b_bnd.height, _cols = _b_bnd.width
	cdef int _row, _col, _v, _d, _nodata = _b_bnd.nodata
	cdef float _e
	cdef np.ndarray[np.uint8_t, ndim=2] _dat = _b_bnd.data
	cdef np.ndarray[np.uint8_t, ndim=2] _idx = _b_idx.data
	cdef np.ndarray[np.float32_t, ndim=2] _err = _b_err.data

	for _row in xrange(_rows):
		for _col in xrange(_cols):
			_v = _dat[_row, _col]
			if _v == _nodata:
				continue

			_i = _row * _b_bnd.width + _col
			if _i not in bbs:
				continue

			_m = bbs[_i]

			_t = 0
			_e = 0
			_d = _b_idx.nodata

			_n = 0
			for _k, _w in _m.items():
				# if (_w[1] / _w[0]) > _n:
				if _w[1] > _n:
					_t = _k
					_n = _w[0]
					_e = _w[1] / _w[0]
					_d = _w[2]

			_dat[_row, _col] = _t
			_err[_row, _col] = _e
			_idx[_row, _col] = _d

def _load_ext(tile):
	from osgeo import ogr
	import geo_base_c as gb
	import config

	_shp = ogr.Open(config.cfg.get('conf', 'wrs'))
	_lyr = _shp.GetLayer()

	for _f in _lyr:
		_t = _f['PATHROW'].strip()
		if _t == tile:
			return gb.geo_polygon(_f.geometry().Clone())

	return None

def _make_ext(prj, cell, tile, fzip):
	import config

	_ext = _load_ext(tile)
	if _ext == None:
		return None

	_ext = _ext.project_to(prj)

	_dis = config.cfg.getfloat('conf', 'buffer')
	if _dis > 0:
		_ext.poly = _ext.poly.Buffer(_dis, 1)

	_box = _ext.extent()

	import geo_raster_c as ge
	_bnd = ge.geo_band_info([_box.minx, cell, 0, _box.maxy, 0, -cell], \
			int(_box.width()/cell), int(_box.height()/cell),  prj)

	import rasterize_band
	_out = fzip.generate_file('', '.img')

	rasterize_band.rasterize_polygon(_bnd, _ext, _out, fzip.generate_file('', '.shp'))
	_bnd = ge.open(_out).get_band().cache()
	_bnd.nodata = 0
	_bnd.data[_bnd.data == 1] = 255

	return _bnd

def combine(tile, fs, f_clr, d_out):
	import file_unzip
	import landsat

	with file_unzip.file_unzip() as _zip:
		return _combine(tile, fs, f_clr, d_out, _zip)

def tree():
	import collections
	return collections.defaultdict(tree)

def _combine(tile, fs, f_clr, d_out, fzip):
	if len(fs) == 0:
		return

	import os
	import metadata

	_met = metadata.metadata()
	_met['target'] = fs[0]

	_tmp, _ter = load_img(fs[0])
	_bnd = _make_ext(_tmp.proj, _tmp.geo_transform[1], tile, fzip)

	import numpy as np

	_der = np.empty([_bnd.height, _bnd.width], dtype=np.float32)
	_der.fill(-9999)
	_err = _bnd.from_grid(_der, nodata=-9999)

	_idx = np.empty([_bnd.height, _bnd.width], dtype=np.uint8)
	_idx.fill(255)
	_ibn = _bnd.from_grid(_idx, nodata=255)

	import progress_percentage
	_ppp = progress_percentage.progress_percentage(len(fs))

	import collections
	_bbs = collections.defaultdict(lambda: {})

	_ls = []
	for _i in xrange(0, len(fs)):
		_ppp.next()
		_met['input'][_i] = fs[_i]
		# update(_bbs, (_bnd, _err), load_img(fs[_i], _bnd), _i)
		update(_bbs, (_bnd, None), load_img(fs[_i], _bnd), _i)
		_ls.append('%s=%s' % (_i, fs[_i]))

	_ppp.done()

	output(_bbs, (_bnd, _err, _ibn))

	import landsat
	_inf = landsat.parse(fs[0])

	os.path.exists(d_out) or os.makedirs(d_out)

	_f_out = os.path.join(d_out, '%s_com_dat.tif' % _inf.tile)
	_f_err = os.path.join(d_out, '%s_com_err.tif' % _inf.tile)
	_f_idx = os.path.join(d_out, '%s_com_idx.tif' % _inf.tile)
	_f_txt = os.path.join(d_out, '%s_com_idx.txt' % _inf.tile)
	_f_met = os.path.join(d_out, '%s_com_met.txt' % _inf.tile)

	_met['output'] = _f_out

	_bnd.save(_f_out, color_table=load_color(f_clr), opts=['compress=lzw'])
	_ibn.save(_f_idx, opts=['compress=lzw'])
	_err.save(_f_err, opts=['compress=lzw'])
	_met.save(_f_met)

	with open(_f_txt, 'w') as _fo:
		_fo.write('\n'.join(_ls))

def load_img(f, bnd=None):
	import geo_raster_c as ge

	if bnd == None:
		return ge.open(f).get_band().cache(), \
				ge.open(f.replace('_dat.tif', '_err.tif')).get_band().cache()
	else:
		return ge.open(f).get_band().read_block(bnd), \
			ge.open(f.replace('_dat.tif', '_err.tif')).get_band().read_block(bnd)

def load_color(f):
	import geo_raster_c as ge
	return ge.load_colortable(f)

	# _bnd = ge.open(f).get_band()
	# return _bnd.color_table

def combine_bnd(tag, bnd, fs, f_clr, d_out):
	import file_unzip

	with file_unzip.file_unzip() as _zip:
		return _combine_bnd(tag, bnd, fs, f_clr, d_out, _zip)

def _combine_bnd(tag, bnd, fs, f_clr, d_out, fzip):
	if len(fs) == 0:
		return

	import os
	import metadata

	_met = metadata.metadata()

	import geo_raster_ex_c as gx
	import config

	_bnd = gx.geo_band_stack_zip.from_shapefile(config.cfg.get('conf', 'land'), file_unzip=fzip).read_block(bnd)
	if _bnd == None:
		return

	_bnd.nodata = 0
	_bnd.data[_bnd.data == 1] = 255

	import numpy as np

	_der = np.empty([_bnd.height, _bnd.width], dtype=np.float32)
	_der.fill(-9999)
	_err = _bnd.from_grid(_der, nodata=-9999)

	_idx = np.empty([_bnd.height, _bnd.width], dtype=np.uint8)
	_idx.fill(255)
	_ibn = _bnd.from_grid(_idx, nodata=255)

	import progress_percentage
	_ppp = progress_percentage.progress_percentage(len(fs))

	import collections
	_bbs = collections.defaultdict(lambda: {})

	_ls = []
	for _i in xrange(0, len(fs)):
		_ppp.next()
		_met['input'][_i] = fs[_i]

		# update(_bbs, (_bnd, _err), load_img(fs[_i], _bnd), _i)
		update(_bbs, (_bnd, None), load_img(fs[_i], _bnd), _i)
		_ls.append('%s=%s' % (_i, fs[_i]))

	_ppp.done()

	output(_bbs, (_bnd, _err, _ibn))

	os.path.exists(d_out) or os.makedirs(d_out)

	_f_out = os.path.join(d_out, '%s_com_dat.tif' % tag)
	_f_err = os.path.join(d_out, '%s_com_err.tif' % tag)
	_f_idx = os.path.join(d_out, '%s_com_idx.tif' % tag)
	_f_txt = os.path.join(d_out, '%s_com_idx.txt' % tag)
	_f_met = os.path.join(d_out, '%s_com_met.txt' % tag)

	_met['output'] = _f_out

	_bnd.save(_f_out, color_table=load_color(f_clr), opts=['compress=lzw'])
	_ibn.save(_f_idx, opts=['compress=lzw'])
	_err.save(_f_err, opts=['compress=lzw'])
	_met.save(_f_met)

	with open(_f_txt, 'w') as _fo:
		_fo.write('\n'.join(_ls))

