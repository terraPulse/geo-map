#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
File: generate_legend.py
Author: Min Feng
Version: 0.1
Create: 2017-09-03 01:39:15
Description:
'''

def main(opts):
    from geo_map_util import map_color
    import PIL.Image

    _f_clr = opts.input
    _vs, _cs = map_color.load_color_file(_f_clr)

    _height = 200
    _buf = 6
    _rows = _height - (2 * _buf)

    _img = PIL.Image.new('RGBA', (81, _height), (255, 255, 255, 0 if opts.transparent_bg else 255))

    for _row in range(0, _rows):
        for _col in range(0, 10):
            _rrr = min(_rows - 1, int((_row * len(_vs)) /_rows))
            _clr = _cs[_rrr]

            _img.putpixel((_col, _buf + _row), _clr)

    _font_size = 12
    _font_offset = -1 * (_font_size / 2 + 1) #_font_size / 2 - 2

    import PIL.ImageDraw
    import PIL.ImageFont
    from gio import config

    _fnt = PIL.ImageFont.truetype(config.get('conf', 'font'), _font_size)
    _dra = PIL.ImageDraw.Draw(_img)

    _txt = lambda x: opts.format % x
    _num = min(len(_vs), opts.ticks)

    for _i in range(_num):
        _pos = _i * 1.0 / _num
        _dra.text((13, int(_rows * _pos + _buf + _font_offset)), \
                _txt(_vs[int(len(_vs) * _pos)].t), font=_fnt, fill=(0, 0, 0, 255))

    _dra.text((13, _rows + _buf + _font_offset), _txt(_vs[-1].t), font=_fnt, fill=(0, 0, 0, 255))

    _img.save(opts.output)

def usage():
    _p = environ_mag.usage(False)

    _p.add_argument('-i', '--input', dest='input', required=True)
    _p.add_argument('-f', '--format', dest='format', default='%s')
    _p.add_argument('-o', '--output', dest='output', required=True)
    _p.add_argument('-t', '--ticks', dest='ticks', type=int, default=6)
    _p.add_argument('-b', '--transparent-bg', dest='transparent_bg', action='store_true', default=False)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])
