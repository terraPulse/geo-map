'''
File: map_tile_merge.py
Author: Min Feng
Description: merge the map tiles to reduce number of files
'''
from . import map_tile_task
from . import map_tile

class loc_image:

    def __init__(self, loc, img):
        self.loc = loc
        self.img = img

class tile_merge:

    def tile_union(self, t1, t2):
        return {'x1': max(t1.col, t2.col), 
                'y1': max(t1.row, t2.row), 
                'x2': min(t1.col + t1.merge, t2.col + t2.merge),
                'y2': min(t1.row + t1.merge, t2.row + t2.merge)}
    
    def empty_image(self, merge=1):
        from PIL import Image
        return Image.new('RGBA', (256 * merge, 256 * merge), (0,0,0,0))
    
    def make_box(self, bb, t):
        _sx = t.col
        _sy = t.row
        
        _bx = (bb['x1'] - _sx, bb['y1'] - _sy, bb['x2'] - _sx, bb['y2'] - _sy)
        return [_b * 256 for _b in _bx]
    
    def read_tile(self, tile_src, tile_tar, met, d_inp, tag):
        _bb = self.tile_union(tile_src, tile_tar)

        if _bb['x2'] <= _bb['x1'] or _bb['y2'] <= _bb['y1']:
            return None
    
        _sx = _bb['x1'] - tile_tar.col
        _sy = _bb['y1'] - tile_tar.row

        _da = map_tile_task.map_tile_task().read(met, d_inp, tag, tile_src.tile)

        from PIL import Image
        import io

        _ii = Image.open(io.BytesIO(_da))
        return loc_image((_sx * 256, _sy * 256), _ii.crop(self.make_box(_bb, tile_src)))

    def c_col(self, d, merge):
        return int((d // merge) * merge)
    
    def c_row(self, d, merge, level):
        import math
        
        _r = map_tile.rrow(level, -d, merge)
        _v = int(math.ceil(_r / merge) * merge)
    
        return map_tile.rrow(level, -_v, merge)

    def read(self, t, merge, met, d_inp, tag):
        _img = self.empty_image(t.merge)

        for _col in range(t.col, t.col + t.merge, merge):
            for _row in range(t.row, t.row + t.merge, merge):
                _z = map_tile.zxy(t.level, \
                                   self.c_col(_col, merge), \
                                   self.c_row(_row, merge, t.level), \
                                   merge)
                _i = self.read_tile(_z, t, met, d_inp, tag)
                if not _i:
                    continue
    
                _img.paste(_i.img, _i.loc)
                
        return map_tile.image_to_bytes(_img)
