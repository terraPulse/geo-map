'''
File: mod_ndvi.py
Author: Min Feng
Version: 0.1
Create: 2017-05-16 15:31:20
Description:
'''

_format_ndvi = '365h'

def identify_loc(lon,lat):
	from gio import geo_raster as ge
	from gio import geo_base as gb
	from gio import geo_raster_ex as gx
	from gio import modis_util

	_proj_geo = gb.proj_from_epsg()
	_proj_sin = gb.modis_projection()

	_p = gx.geo_point(lon, lat, _proj_geo)
	_t =_p.project_to(_proj_sin)

	_x = _t.x
	_y = _t.y

	_col,_row = modis_util.modis_info().pixel(_x,_y)
	_tile = modis_util.modis_info().tile(_x,_y)

	_ext = modis_util.modis_info().extent(_tile)
	_num = 2400
	_cel = _ext.width() / _num

	_bnd = ge.geo_band_info([_ext.minx, _cel, 0, _ext.maxy, 0, -_cel], _num, _num, _proj_sin)
	_eee = _bnd.cell_extent(_col, _row).to_polygon().project_to(_proj_geo)

	return _eee, _row, _col, _tile, _t

def search_files(f, _tile,_b_c,_b_r):
	import re
	import os

	_ss ={}
	for _l in open(f).read().strip().splitlines():
		_file = os.path.basename(_l)

		_m = re.match('NDVI_V01_%s_(\d{4})_c%s_r%s\.dat' % (_tile,_b_c,_b_r), _file)
		if _m:
			_yy = int(_m.group(1))
			_ff = _l
			_ss[_yy] = _ff

	return _ss

def read_bytes(_dat,_rr,_cc,cell):
	import struct

	_pn = _rr * cell + _cc
	with open(_dat, 'rb') as _f_in:
		_f_in.seek(_pn * 730,0)
		_bytes = _f_in.read(730)
		_pixels = struct.unpack(_format_ndvi,_bytes)
	return _pixels

def yd2ymd(_yy,_dd):
	import datetime
	_date = '%s%s' % (_yy,_dd)
	_ymd = str(datetime.datetime.strptime(_date, '%Y%j').strftime('%Y-%m-%d'))
	return _ymd

def extract_NDVI(f_in,lon,lat,cell, f_out=None):
	from gio import geo_raster_ex as gx
	from gio import config
	import logging

	_ext, _row, _col,_tile, _pt = identify_loc(lon, lat)
	_wat = gx.geo_band_stack_zip.from_shapefile(config.get('general', 'water_path')).read(_pt)

	if _wat != 0:
		logging.warning('water pixel %s, %s' % (lon, lat))
		return {'ext': _ext.poly.ExportToJson(), 'data': []}

	_rr = _row % cell
	_cc = _col % cell
	b_r = _row / cell
	b_c = _col / cell

	_ss = search_files(f_in,_tile,b_c,b_r)
	_yy = list(_ss.keys())
	_yy.sort()

	_as = ['YYYY_MM_DD,NDVI']
	_ls = []
	for _y in _yy:
		_dat = _ss[_y]
		_pixels = read_bytes(_dat,_rr,_cc,cell)
		for _d in range(365):
			val = _pixels[_d]

			if val < 100:
				continue

			if val > 990:
				continue

			_date = yd2ymd(_y,_d + 1)

			_as.append('%s,%s' % (_date, val / 1000.0))
			_ls.append([_date, val / 1000.0])

	_ss = [_l[1] for _l in _ls]
	for _i in range(len(_ls)):
		_vs = [_s for _s in _ss[max(0, _i - 3): min(_i + 3, len(_ss))]]
		# _ls[_i][1] = sorted(_vs)[len(_vs) / 2]
		_ls[_i][1] = sum(_vs) / len(_vs)

	if f_out:
		with open(f_out, 'w') as _fo:
			_fo.write('\n'.join(_as))

	return {'ext': _ext.poly.ExportToJson(), 'data': _ls if len(_ls) > 30 else []}
#
# 	import json
# 	with open(f_out, 'w') as _fo:
# 		json.dump(_ls, _fo)

def main(opts):
	_l = '/data/glcf-nx-002/data/PALSAR/modis/ndvi/bip/list/ndvi_bip.txt'
	extract_NDVI(_l, -73.090337, 49.581254,600, 'NDVI_time_series.csv')

def usage():
	_p = environ_mag.usage(False)

	return _p

if __name__ == '__main__':
	from gio import environ_mag
	environ_mag.init_path()
	environ_mag.run(main, [environ_mag.config(usage())])

