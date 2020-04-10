'''
File: extract_ndvi_records
Author: Min Feng
Version: 0.1
Create: 2019-11-24 23:57:54
Description:
'''

def main(opts):
    from geo_map_util import lib_ndvi
    import re

    _x, _y = float(opts.coordinate[0]), float(opts.coordinate[1])
    _rs = lib_ndvi.gee_ndvi(_x, _y)

    from gio import file_unzip
    with file_unzip.zip() as _zip:
        if opts.output.endswith('.png'):
            import os
            (lambda x: os.path.exists(x) or os.makedirs(x))(os.path.dirname(os.path.abspath(opts.output)))

            lib_ndvi.plot(_rs, '%.6f,%.6f' % (_x, _y), opts.output)
        else:
            _ls = ['date,ndvi']
            for _r in sorted(_rs.keys()):
                _ls.append('%s,%.3f' % (_r.strftime('%Y-%m-%d'), _rs[_r]))

            _zip.save('\n'.join(_ls), opts.output)
    
def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-i', '--coordinate', dest='coordinate', required=True, nargs='+')
    _p.add_argument('-o', '--output', dest='output', required=True)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

