'''
File: mod_classify.pyx
Author: Min Feng
Version: 0.1
Create: 2015-07-09 17:10:27
Description: 
'''
import logging
import numpy as np
cimport numpy as np
cimport cython

@cython.boundscheck(False)
@cython.wraparound(False)

def train(obj):
	logging.debug('start training')

	import os
	import config
	import params

	_bnd_mak = obj.band('qa')
	_sr_bnd_names = ['b2', 'b3', 'b4', 'b5']

	cdef np.ndarray[np.uint8_t, ndim=2] _dat_flg = \
			np.zeros((_bnd_mak.height, _bnd_mak.width), dtype=np.uint8)

	# estimate the number of samples
	# _cache_lines = config.cfg.getint('conf', 'cache_lines')

	import progress_percentage
	_ppp = progress_percentage.progress_percentage(_bnd_mak.height)

	cdef np.ndarray[np.uint8_t, ndim=2] _dat_mak = _bnd_mak.data
	cdef np.ndarray[np.uint8_t, ndim=2] _dat_fcc = obj.band('fcc').data
	cdef np.ndarray[np.int16_t, ndim=2] _dat

	cdef int _row, _col
	cdef np.uint8_t _v_mak, _v_fcc, _v_flg
	cdef np.int16_t _val

	# _filter_snow = config.cfg.getboolean('conf', 'filter_snow')

	import collections
	_cs = collections.defaultdict(lambda: 0.0)
	_vs_bnd = collections.defaultdict(lambda: [])

	for _row in xrange(_bnd_mak.height):
		_ppp.next()

		for _col in xrange(_bnd_mak.width):
			_v_mak = _dat_mak[_row, _col]
			_v_fcc = _dat_fcc[_row, _col]

			# if _v_mak == params.MSS_NODATA or _v_mak == params.MSS_WATER: # or _v_mak == params.MSS_CLOUD:
			if _v_mak == params.MSS_NODATA: # or _v_mak == params.MSS_CLOUD:
				continue

			if _v_fcc not in (params.FCC_FOREST, params.FCC_WATER, params.FCC_NONFOREST):
				continue

			_v_flg = _v_mak * 10 + _v_fcc

			_dat_flg[_row, _col] = _v_flg
			_cs[_v_flg] += 1

	_ppp.done()

	obj._bnds['flg'] = _bnd_mak.from_grid(_dat_flg, nodata=0)

	_dict_str = lambda dd: ', '.join(['%s: %s' % (_k, dd[_k]) for _k in sorted(dd.keys())])
	logging.info('pixel nums: ' + _dict_str(_cs))

	_bnd_chk = obj.band(config.cfg.get('param', 'chk_band'))
	_sat_chk = {}
	_ext_chk = {}
	for _v in _cs.keys():
		_ss = _stat(_bnd_chk.data, _dat_flg, _v)
		_sat_chk[_v] = _ss
		_ext_chk[_v] = [_ss['avg'] - 1.96 * _ss['std'], _ss['avg'] + 1.96 * _ss['std']]

	_max_sample_num = config.cfg.getint('param', 'max_sample_num')
	_max_sample_rat = config.cfg.getfloat('param', 'max_sample_rat')
	logging.info('max sample nums: %s' % _max_sample_num)

	_s_sum = sum(_cs.values())
	if _s_sum == 0:
		raise Exception('no valid sample collected')

	_t_rat = min(_max_sample_num / _s_sum, 1.0)
	_s_rat = {_k: min((min(_max_sample_num, _v) / float(_v)) if _v > 0 else 0, \
			_max_sample_rat) for _k, _v in _cs.items()}

	logging.info('sample rates: %s' % _dict_str(_s_rat))

	# load target values
	_s_tar = {_k: int(config.cfg.getfloat('target', str(_k))) for _k in _cs.keys() if \
			config.cfg.has_option('target', str(_k))}
	logging.info('sample targets: %s' % _dict_str(_s_tar))

	# load weight values
	_s_wet = {_k: float(config.cfg.getfloat('weight', str(_k))) for _k in _cs.keys() if \
			config.cfg.has_option('weight', str(_k))}
	logging.info('sample weights: %s' % _dict_str(_s_wet))

	_b_ns_int16 = config.cfg.get('param', 'names').replace(' ', '').split(',')

	_vars = _write_names_file(obj.file_name('model', 'names'), _b_ns_int16)
	logging.info('vars: %s' % ', '.join(_vars))

	_ss = collections.defaultdict(lambda: 0.0)
	_num_skip = 0
	_null = '?'

	cdef np.ndarray[np.int16_t, ndim=2] _dat_chk = _bnd_chk.data

	# produce data file for training
	with open(obj.file_name('model', 'data'), 'w') as _o_dat:
		import random

		_ppp = progress_percentage.progress_percentage(_bnd_mak.height)
		for _row in xrange(_bnd_mak.height):
			_ppp.next()

			for _col in xrange(_bnd_mak.width):
				_v_flg = _dat_flg[_row, _col]

				if _v_flg not in _s_tar:
					continue

				if _v_flg not in _s_wet:
					continue

				if _v_flg == 0 or _v_flg >= 100:
					continue

				if _s_rat[_v_flg] <= 0:
					continue

				if _s_wet[_v_flg] < 0:
					continue

				_v_chk = _dat_chk[_row, _col]
				if _v_chk < _ext_chk[_v_flg][0] or _v_chk > _ext_chk[_v_flg][1]:
					continue

				if random.random() > _s_rat[_v_flg]:
					continue

				_x, _y = _bnd_mak.to_location(_col, _row)
				_sas = [_x, _y, _v_flg]
				for _tag in _b_ns_int16:
					_bnd = obj.band(_tag)
					_dat = _bnd.data
					_val = _dat[_row, _col]
					if _bnd.nodata != None and _val == _bnd.nodata:
						_sas.append(_null)
					else:
						_sas.append(_val)

				_sas.append(_s_tar[_v_flg])
				_sas.append(_s_wet[_v_flg])

				_output_record(_o_dat, _sas)
				_ss[_v_flg] += 1

		_ppp.done()

	logging.info('skipped pixels: %s' % _num_skip)
	logging.info('sample numbers: ' + _dict_str(_ss))

	_f_out = obj.file_name('model', 'tree')
	_cmd = '%s -f %s' % (config.get_at('conf', 'see5'), _f_out[:len(_f_out) - 5])

	import run_commands
	run_commands.run(_cmd)

	return _vars, {} #_vs_var

def build(obj):
	logging.debug('start building')

	import config
	import params

	_bnd_mak = obj.band('qa')

	cdef np.ndarray[np.uint8_t, ndim=2] _dat_out = \
			np.zeros((_bnd_mak.height, _bnd_mak.width), dtype=np.uint8)
	cdef np.ndarray[np.float32_t, ndim=2] _dat_err = \
			np.empty((_bnd_mak.height, _bnd_mak.width), dtype=np.float32)
	cdef np.ndarray[np.int16_t, ndim=2] _dat
	cdef np.int16_t _val
	cdef int _row, _col
	cdef np.ndarray[np.uint8_t, ndim=2] _dat_mak = _bnd_mak.data
	cdef np.ndarray[np.uint8_t, ndim=2] _dat_land = obj.band('land').data

	_dat_err.fill(params.ERR_NODATA)

	import progress_percentage
	_ppp = progress_percentage.progress_percentage(_bnd_mak.height)

	_f_data = obj.file_name('model', 'cases')
	_o_data = open(_f_data, 'w')
	_loc_s = []

	_bnd_tags = _load_columns()
	logging.info('SR bands: ' + str(_bnd_tags))

	# _filter_shadow = config.cfg.getboolean('conf', 'filter_shadow')
	# _filter_ocean = config.cfg.getboolean('conf', 'filter_ocean')
	# _filter_snow = config.cfg.getboolean('conf', 'filter_snow')
	# _filter_extra = config.cfg.getboolean('conf', 'filter_extra')

	# logging.info('filter shadow: %s, ocean: %s, snow: %s, extra %s' % \
	# 		(_filter_shadow, _filter_ocean, _filter_snow, _filter_extra))

	_max_cache_pixels = config.cfg.getint('param', 'max_cache_pixels') 
	_skip_cloud = config.cfg.getboolean('param', 'skip_cloud')

	_null = '?'
	for _row in xrange(_bnd_mak.height):
		_ppp.next()

		for _col in xrange(_bnd_mak.width):
			_v_mak = _dat_mak[_row, _col]
			_v_land = _dat_land[_row, _col]

			if _v_mak == params.MSS_NODATA:
				continue

			# if _v_mak == params.MSS_WATER:
			# 	_dat_out[_row, _col] = params.VAL_WATER
			# 	_dat_err[_row, _col] = params.ERR_WATER
			# 	continue

			if _v_land != 1:
				_dat_out[_row, _col] = params.VAL_WATER
				_dat_err[_row, _col] = 1.0
				continue

			if _skip_cloud and _v_mak == params.MSS_CLOUD:
				_dat_out[_row, _col] = params.VAL_CLOUD
				_dat_err[_row, _col] = params.ERR_CLOUD
				continue

			_sas = [_null, _null, _null] # add x, y, flag columns
			for _tag in _bnd_tags:
				_bnd = obj.band(_tag)
				_dat = _bnd.data
				_val = _dat[_row, _col]
				if _bnd.nodata != None and _val == _bnd.nodata:
					_sas.append(_null)
				else:
					_sas.append(_val)

			_sas.append(_null)
			_sas.append(_null)

			_output_record(_o_data, _sas)
			_loc_s.append((_row, _col))

			if len(_loc_s) >= _max_cache_pixels:
				_o_data.flush()
				_o_data.close()
				_predict_block(_f_data, _dat_out, _dat_err, _loc_s)

				logging.info('next block')
				_o_data = open(_f_data, 'w')
				_loc_s = []

	if len(_loc_s) > 0:
		_o_data.flush()
		_o_data.close()
		_predict_block(_f_data, _dat_out, _dat_err, _loc_s)

	# remove the temperary file
	del _loc_s

	import os
	if not config.cfg.getboolean('conf', 'debug'):
		os.remove(_f_data)
	_ppp.done()

	_bnd_wat = _bnd_mak.from_grid(_dat_out, nodata=0)
	filter_noise(_bnd_wat, obj.band('qa'))

	obj._bnds['dat'] = _bnd_wat
	obj._bnds['err'] = _bnd_mak.from_grid(_dat_err, nodata=-9999)

def _output_record(fo, vs):
	_vs = [str(_v) for _v in vs]
	fo.write(','.join(_vs))
	fo.write('\n')

def _write_names_file(f, sr_tags):
	import config

	_ls = ['result.']
	_ls.append('')
	_ls.append('x: ignore.')
	_ls.append('y: ignore.')
	_ls.append('flg: ignore.')

	_cfg = config.cfg

	_vs = []
	_add_name = lambda x: _vs.append((x, _cfg.get('names', x) \
			if _cfg.has_option('names', x) else 'ignore'))

	for _b in sr_tags:
		_add_name('%s' % (_b))

	for _n, _v in _vs:
		_ls.append('%s: %s.' % (_n, _v))

	_ls.append('result: %s.' % config.cfg.get('param', 'result'))
	_ls.append('case weight: continuous.')

	logging.info('write name file to ' + f)
	with open(f, 'w') as _f:
		_f.write('\n'.join(_ls))

	return [_v[0] for _v in _vs if _v[1] != 'ignore']

def _predict_block(f_case, np.ndarray[np.uint8_t, ndim=2] dat_out,
		np.ndarray[np.float32_t, ndim=2] dat_err, locs):
	logging.debug('predict block %s' % len(locs))
	import config

	_exe = config.get_at('conf', 'see5Sam')
	_cmd = '%s -f %s' % (_exe, f_case[:-6])

	import run_commands
	_rs = run_commands.run(_cmd)
	if _rs[0] != 0:
		raise Exception('failed to run see5Sam')

	_ls = _rs[1].splitlines()[3:]
	cdef int _nu = 0

	logging.debug('predicted lines %s' % len(_ls))
	import re
	for _l in _ls:
		_m = re.match('^\s*\d+\s+\S+\s+(\S+)\s+\[(.+)\]\s*$', _l)
		if _m:
			dat_out[locs[_nu][0], locs[_nu][1]] = int(_m.group(1))
			dat_err[locs[_nu][0], locs[_nu][1]] = float(_m.group(2))
			_nu += 1

	logging.info('predicted %d values (%d)' % (_nu, len(locs)))
	assert(_nu == len(locs))

def _load_columns():
	import config
	return config.cfg.get('param', 'names').replace(' ', '').split(',')

def _stat(dat, ref, val):
	'''return: count, min, max, mean, std'''
	_mak = (ref != val)
	_dat = np.ma.array(dat, mask=_mak)
	_sta = {'num': _dat.count(), 'min': _dat.min(), 'max': _dat.max(), 'avg': _dat.mean(), 'std': _dat.std()}
	logging.info('stat %s: (%s): ' % (val, str(_sta)))
	return _sta

def filter_noise(bnd, bnd_qa):
	import config
	import mod_filter
	import params

	if config.cfg.getboolean('param', 'expand_forest'):
		logging.info('expend water pixels')

		_dat = bnd_qa.data
		_num = mod_filter.expand(bnd.data, \
				(_dat == params.MSS_FOREST1) | (_dat == params.MSS_FOREST2),\
				params.VAL_FOREST, params.VAL_NONFOREST)
		logging.info('filtered %s pixels' % _num)

		_num = mod_filter.expand(bnd.data, \
				(_dat == params.MSS_LAND) | (_dat == params.MSS_FOREST2),\
				params.VAL_NONFOREST, params.VAL_FOREST)

		logging.info('filtered %s pixels' % _num)

	if config.cfg.getboolean('param', 'filter_noise'):
		logging.info('filter noises')

		_dis = config.cfg.getfloat('filter_noise', 'search')
		_min = config.cfg.getint('filter_noise', 'min_num')

		logging.info('filter noise (dis: %s, num: %s)' % (_dis, _min))
		_num = mod_filter.clean(bnd, _dis, _min, params.VAL_FOREST, params.VAL_NONFOREST)
		logging.info('filtered %s pixels' % _num)

		_num = mod_filter.clean(bnd, _dis, _min, params.VAL_NONFOREST, params.VAL_FOREST)
		logging.info('filtered %s pixels' % _num)

