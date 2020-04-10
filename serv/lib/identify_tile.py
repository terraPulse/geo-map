
def tile(x, y):
	from osgeo import ogr

	_f = '/data/glcf-st-004/data/workspace/fengm/data/landsat/wrs2_descending.shp'

	_shp = ogr.Open(_f)
	_lyr = _shp.GetLayer()

	_wkt = 'POINT (%s %s)' % (x, y)
	_lyr.SetSpatialFilter(ogr.CreateGeometryFromWkt(_wkt))

	_tss = []
	for _r in _lyr:
		_tss.append(_r['PATHROW'])

	return _tss

def main():
	_opts = _init_env()

	tile(100, 40)

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

	if not config.cfg.has_section('conf'):
		config.cfg.add_section('conf')

	for _k, _v in list(_opts.__dict__.items()):
		if _v != None:
			config.cfg.set('conf', _k, str(_v))


	import file_unzip as fz
	fz.clean(fz.default_dir(_opts.temp))

	return _opts

if __name__ == '__main__':
	main()

