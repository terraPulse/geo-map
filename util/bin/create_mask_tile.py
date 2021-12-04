'''
File: create_mask_tile.py
Author: Min Feng
Version: 0.1
Create: 2021-12-03 17:33:46
Description: create mask (1=valid, 0=invalid) from a shapefile
'''

import logging

def _mask_grid(bnd, f, fzip):
    from gio import rasterize_band as rb
    from gio import geo_base as gb
    from gio import file_mag
    
    _pol = [_p for _p, _a in gb.load_shp(file_mag.get(f).get(), ext=bnd.extent().to_polygon())]
    return rb.to_mask(bnd, _pol)

def _task(tile, t, f_inp, d_out, ps):
    import os
    from gio import file_unzip
    from gio import file_mag
    from gio import config
    from gio import geo_raster_ex as gx
    import logging

    _tag = tile.tag
    
    _col, _row = tile.h, tile.v
    _tag = '%s%s' % (_col, _row)
    
    _d_out = os.path.join(d_out, _col, _row, _tag)
    _f_out = os.path.join(_d_out, '%s_%s.tif' % (_tag, t))

    if file_mag.get(_f_out).exists():
        logging.debug('skip existing result for %s' % _tag)
        return

    with file_unzip.zip() as _zip:
        _bnd = _mask_grid(tile.extent(), f_inp, _zip)
        _zip.save(_bnd, _f_out)

def main(opts):
    import os
    from gio import file_mag
    from gio import config

    _d_out = opts.output
    if not _d_out:
        return

    _f_mak = file_mag.get(os.path.join(_d_out, 'tasks.txt'))
    _f_shp = file_mag.get(os.path.join(_d_out, 'tasks.shp'))

    from gio import global_task
    if not _f_mak.exists():
        if not opts.input:
            raise Exception('need to previde input extent file')

        _f_inp = file_mag.get(opts.region or opts.input)
        if not _f_inp:
            raise Exception('need to provide extent file for initailization')

        _image_size = config.getint('conf', 'image_size', 3000)
        _cell_size = config.getfloat('conf', 'cell_size', 30)

        _tag = config.get('conf', 'tag')
        if _tag is None:
            raise Exception('need to provide tag')

        _proj = config.get('conf', 'proj')
        _edge = config.getint('conf', 'edge')

        from gio import geo_base as gb
        if _proj:
            _proj = gb.proj_from_proj4(_proj)

        if _proj.IsGeographic() and opts.geog == True:
            _proj = gb.proj_from_epsg()
            _cell_size = _cell_size / 120000.0
            
            print('use geog projection (%s)' % _cell_size)

        print(('projection: %s' % _proj))
        print(('tag: %s, image size: %s, cell size: %s, edge: %s' % (_tag, _image_size, _cell_size, _edge)))

        _ts = global_task.make(_f_inp.get(), None, f_shp=_f_shp, \
                edge=_edge, \
                proj=_proj, \
                image_size=_image_size, \
                cell_size=_cell_size)

        global_task.save(_ts, _f_mak, \
                {'edge': _edge, \
                    't': _tag, 'proj': _proj.ExportToProj4()})
                    
        return
    
    _gs = global_task.loads(_f_mak)
    _ms = _gs['params']
    _ts = _gs['tiles']

    _tt = opts.test_tile
    if _tt:
        _ts = [_t for _t in _ts if _t.tag in _tt]

    _tt = _ms.get('t', opts.tag) if opts.tag is None else opts.tag
    _d_out = opts.output

    from gio import multi_task
    multi_task.run(_task, [(_r, _tt, opts.input, os.path.join(_d_out, 'data'), opts) \
            for _r in multi_task.load(_ts, opts)], opts)

    _f_idx = os.path.join(opts.output, '{}.shp'.format(opts.tag))
    _cmd = 'generate_tiles_extent.py -i {inp} -e {tag}.tif -o {out}'.format(inp=opts.output, tag=opts.tag, out=_f_idx)
    from gio import run_commands
    
    print('generate index file:', _f_idx)
    run_commands.run(_cmd)

def usage():
    _p = environ_mag.usage(True)

    _p.add_argument('-i', '--input', dest='input')
    _p.add_argument('-r', '--region', dest='region')
    _p.add_argument('-t', '--tag', dest='tag', default='mask')
    
    _p.add_argument('--geog', dest='geog', type='bool', default=True)
    _p.add_argument('-p', '--proj', dest='proj', default='EPSG:4326')
    
    _p.add_argument('-s', '--image-size', dest='image_size', default=3000, type=int)
    _p.add_argument('-c', '--cell-size', dest='cell_size', default=99.0, type=float)
    _p.add_argument('-e', '--edge', dest='edge', type=int, default=0)
    
    _p.add_argument('-o', '--output', dest='output', required=True)
    _p.add_argument('--test-tile', dest='test_tile')

    return _p

if __name__ == '__main__':
    from gio import environ_mag
    environ_mag.init_path()
    environ_mag.run(main, [environ_mag.config(usage())])
