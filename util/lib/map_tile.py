#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Author:  Min Feng
Version: 0.1
Create: 2016-12-06
Description: provide functions/classes for managing map tiles
'''

class tile:

    def __init__(self, z, x, y, merge=1):
        self.z = z
        self.x = x
        self.y = y
        self.merge = merge
        self.tiles = tile_mag(merge)

    def size(self):
        '''Size of the tile in mapping unit'''
        return self.merge * self.tiles.tile_size(self.z)

    def cell(self):
        '''Pixel cell size in mapping unit'''
        return self.tiles.cell(self.z)

    def raster(self):
        _r = self.tiles.tile_size(self.z)
        _c = _r / self.tiles.s

        _x = -self.tiles.p + (self.x * _r)
        _y = -self.tiles.p + (self.y * _r)

        _geo = [_x, _c, 0, _y + _r * self.merge, 0, -_c]

        from gio import geo_raster as ge
        return ge.geo_raster_info(_geo, \
                                  self.tiles.s * self.merge, \
                                  self.tiles.s * self.merge, \
                                  self.tiles.prj)

    def extent(self):
        _r = self.tiles.tile_size(self.z)
        _c = _r / self.tiles.s

        _x = -self.tiles.p + (self.x * _r)
        _y = -self.tiles.p + (self.y * _r)

        from gio import geo_base as gb
        return gb.geo_extent(_x, _y, _x + _r * self.merge, \
                             _y + _r * self.merge, self.tiles.prj)

    @property
    def level(self):
        return self.z

    @property
    def col(self):
        return self.x

    @property
    def row(self):
        return self.y

    def file(self, d_out, version=2.0):
        import os
        from gio import file_mag
        
        if version < 2.0:
            _d = os.path.join(d_out, str(self.level), str(self.col))
        else:
            _d = os.path.join(d_out, 'tiles', str(self.level), str(self.col))
            
        _f = os.path.join(_d, '%s.png' % self.row)
        return file_mag.get(_f)

    def __repr__(self):
        return (lambda x: f'{x.z}/{x.x}/{x.y}@{x.merge}')(self)

class tile_mag:

    def __init__(self, merge=1):
        from gio import config
        import math
        
        self.b = 6378137.0
        
        self.s = 256
        self.merge = merge
        if self.merge < 1:
            raise Exception('merging factor too small (%s)' % self.merge)
            
        self.p = self.b * math.pi

        from gio import geo_base as gb
        self.prj = gb.proj_from_epsg(3857)

    def list(self, level, ext=None):
        _r = self.tile_size(level)

        _rows = 2 ** level
        _cols = 2 ** level
        
        _num = -1
        for _row in range(0, _rows, self.merge):
            for _col in range(0, _cols, self.merge):
                _num += 1

                _t = tile(level, _col, _row, self.merge)
                _e = _t.extent()

                if ext is None or _e.is_intersect(ext):
                    yield level, _num, _col, _row

    def tile_size(self, level):
        return (2 * self.p) / (2 ** level)

    def cell(self, level):
        return self.tile_size(level) / self.s

def rrow(lev, row, merge=1):
    assert row <= 0
    return (2 ** lev) + row - merge

def image_to_bytes(i):
    import io
    _b = io.BytesIO()
    i.save(_b, format='PNG')
    return _b.getvalue()

class zxy:

    def __init__(self, z, x, y, merge=1):
        self.z = z
        self.x = x
        self.y = y if y > 0 else rrow(z, y, merge)
        self.merge = merge
        
    @staticmethod
    def from_tile(tile):
        return zxy(tile.z, tile.x, rrow(tile.z, -tile.y, tile.merge))

    @property
    def tile(self):
        return tile(self.z, self.x, rrow(self.z, -self.y, self.merge), self.merge)

    @property
    def zx_y(self):
        return tile(self.z, self.x, rrow(self.z, -self.y, self.merge), self.merge)

    @property
    def level(self):
        return self.z

    @property
    def col(self):
        return self.x

    @property
    def row(self):
        return self.y

    def __repr__(self):
        return (lambda x: f'{x.z}/{x.x}/{x.y}@{x.merge}')(self)