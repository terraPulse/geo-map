'''
File: generate_legend.py
Author: Min Feng
Version: 0.1
Create: 2017-09-03 01:39:15
Description:
'''

def load_color_file(f):
    _ls = open(f).read().strip().splitlines()[2:]

    _vs = []
    _cs = {255: (255, 255, 255, 0)}

    _p = -1
    for _l in _ls:
        _p += 1

        _vv = _l.split(',')
        if len(_vv) != 6:
            raise Exception('color file cannot be accepted')

        _vs.append(float(_vv[0]))
        _cs[_p] = tuple(map(int, _vv[1:5]))

    return _vs, _cs


def main(opts):
    from geo_map_util import map_color
    import PIL.Image

    _f_clr = opts.input
    _vs, _cs = map_color.load_color_file(_f_clr)

    _rows = 180
    _img = PIL.Image.new('RGBA', (81, _rows), (255, 255, 255, 0))

    for _row in xrange(0, _rows):
        for _col in xrange(0, 10):
            _rrr = min(_rows - 1, int((_row * len(_vs)) /_rows))
            _clr = _cs[_rrr]

            _img.putpixel((_col, _row), _clr)

    import PIL.ImageDraw
    import PIL.ImageFont
    from gio import config

    _fnt = PIL.ImageFont.truetype(config.get('conf', 'font'), 12)
    _dra = PIL.ImageDraw.Draw(_img)

    _txt = lambda x: opts.format % x
    _dra.text((12, 1), _txt(_vs[0].v), font=_fnt, fill=(0, 0, 0, 255))
    _dra.text((12, _rows / 2 - 14), _txt(_vs[len(_vs) / 2].v), font=_fnt, fill=(0, 0, 0, 255))
    _dra.text((12, _rows - 14), _txt(_vs[-2].v), font=_fnt, fill=(0, 0, 0, 255))

    _img.save(opts.output)

def usage():
    _p = environ_mag.usage(False)

    _p.add_argument('-i', '--input', dest='input', required=True)
    _p.add_argument('-f', '--format', dest='format', default='%0.0f')
    _p.add_argument('-o', '--output', dest='output', required=True)

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])

