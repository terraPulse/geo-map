'''
File: colorize_raster.py
Author: Min Feng
Version: 0.1
Create: 2017-09-01 18:35:53
Description:
'''

def main(opts):
    from geo_map_util import map_color
    map_color.colorize(opts.input, opts.color, opts.output)

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

