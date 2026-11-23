'''
File: map_tile_interpo.py
Author: Min Feng
Description: interpolate map tiles from pregenerated levels
'''

import logging

class interpo:

    def __init__(self, map, tile):
        self.map = map
        self.tile = tile

    def __str__(self):
        return 'map={} {}'.format(self.map, self.tile)

    def file(self):
        from gio import config
        _repo = config.get('general', 'map_path')

        _m = self.map
        _t = self.tile.zx_y

        _f = f'{_repo}/{_m}/tiles/{_t.z}/{_t.x}/{_t.y}.png'
        return _f

    def config(self):
        from gio import config
        from gio import file_mag
        import json
        import os
        from .tile_runtime import get_cache

        _repo = config.get('general', 'map_path')
        _f = os.path.join(_repo, self.map, 'setting.ini')
        _key = 'setting:' + _f
        _cache = get_cache()

        def _load():
            _mag = file_mag.get(_f)
            _cache.note_stat()
            if not _mag.exists():
                return None
            _raw = _mag.read()
            if not _raw:
                return None
            if isinstance(_raw, str):
                _raw = _raw.encode('utf-8')
            _cache.note_get(len(_raw))
            return _raw

        _raw = _cache.get_or_load_bytes(_key, _load)
        if not _raw:
            raise Exception('failed to load layer setting %s' % _f)
        return json.loads(_raw)

    def read_file(self):
        from PIL import Image
        import io
        from . import map_tile_parse

        _b = map_tile_parse.map_tile_util().load(self.map, self.tile.zx_y)
        return Image.open(io.BytesIO(_b))
        
    # def subset(self, box):
    #     _m = self.read_file()
    #     if not _m:
    #         return None

    #     from PIL import Image
    #     return _m.crop(box).resize((256, 256), resample=Image.NEAREST)

    def _image(self, level):
        if level is None:
            return None

        if level == self.tile.z:
            return self.read_file()

        if level < self.tile.z:
            return self.zoomin(level)

        return self.zoomout(level)

    def image(self, level):
        logging.info('interpolate tile (%s) from level %s' % (self.url(), level))
        _o = self._image(level)
        if _o:
            return _o

        from PIL import Image
        return Image.new('RGBA', (256, 256), (0,0,0,0))

    def zoomin(self, level):
        from .tile_runtime import child_sample_window, get_cache
        import time

        _spec = child_sample_window(
            self.tile.x, self.tile.y, self.tile.z, level, self.tile.merge)
        if _spec is None:
            return None

        from . import map_tile
        _to = map_tile.zxy(level, _spec['parent_x'], _spec['parent_y'], _spec['parent_merge'])
        _t = interpo(self.map, _to)

        _m = _t.read_file()
        if not _m:
            return None

        from PIL import Image
        _t0 = time.perf_counter()
        _out = _m.crop(_spec['box']).resize(_spec['size'], resample=Image.NEAREST)
        get_cache().record_resample(time.perf_counter() - _t0)
        return _out

    def zoomin_tiles(self, level):
        # deprecated
        
        _ti = self.tile
        _ld = _ti.z - level
        if _ld <= 0:
            return
        
        _z = 256
        _d = 2 ** _ld
        _s = _z / _d
        _tx = int(_ti.x / _d)
        _ty = int(_ti.y / _d)
        
        _dx = (_ti.x % _d)
        _dy = (_ti.y % _d)
        
        _bx = _dx * _s
        _by = _dy * _s

        from . import map_tile
        _tt = interpo(self.map, map_tile.zxy(level, _tx, _ty))
        _bb = (_bx, _by, _bx + _s, _by + _s)
        
        return _tt.subset(_bb)

    def zoomout(self, level):
        from PIL import Image
        from . import map_tile

        _ti = self.tile
        _ld = level - _ti.z
        
        _z = 256 * self.tile.merge
        _d = (2 ** _ld)

        _x = self.tile.x * _d
        _y = self.tile.y * _d
        
        _t = interpo(self.map, map_tile.zxy(level, _x, _y, self.tile.merge * _d))
        _m = _t.read_file()
        
        if not _m:
            return _m

        _d = (2 ** _ld)
        _s = int(_z / _d)

        _o = Image.new('RGBA', (_z, _z), (0,0,0,0))
        _o.paste(_m.resize((_z, _z), resample=Image.BICUBIC), (0, 0))            
        return _o

    def zoomout_tiles(self, level):
        # deprecated
        
        from PIL import Image
        from . import map_tile

        _ti = self.tile
        _ld = level - _ti.z
        
        _z = 256

        _o = Image.new('RGBA', (_z, _z), (0,0,0,0))

        _d = 2 ** _ld
        _s = int(_z / _d)
        
        _tx = int(_ti.x * _d)
        _ty = int(_ti.y * _d)
        
        for _xi in range(_d):
            for _yi in range(_d):
                _x = _tx + _xi
                _y = _ty + _yi
                
                _t = interpo(self.map, map_tile.zxy(level, _x, _y))
                _m = _t.read_file()
                
                if _m:
                    _o.paste(_m.resize((_s, _s), resample=Image.BICUBIC), 
                            (_xi * _s, _yi * _s))
        
        return _o

    def url(self):
        _t = self.tile.zx_y
        return f'{self.map}/{_t.z}/{_t.x}/{_t.y}.png'

    def find_nearest_level(self, ls):
        from .tile_runtime import nearest_stored_level
        return nearest_stored_level(self.tile.z, ls)
            
    def interpo_tile(self, ls):
        _l = self.find_nearest_level(ls)
        return self.image(_l)
            
    # def generate(self):
    #     _path = 'map/' + self.url()
    #     logging.info('generating map tile %s' % _path)

    #     import boto3
    #     import json
    #     from gio import config

    #     _node = config.get('general', 'map_tile_lambda')
    #     _client = boto3.client('lambda')
    #     _i = {'path': _path}
    #     _r = _client.invoke(
    #             FunctionName=_node,
    #             InvocationType='RequestResponse',
    #             Payload=json.dumps(_i)
    #         )

    #     _o = json.loads(_r['Payload'].read())
    #     return _o

    def image_to_bytes(self, i):
        import io
        _b = io.BytesIO()
        i.save(_b, format='PNG')
        return _b.getvalue()

    def levels(self):
        _cs = self.config()
        return _cs.get('processed_levels', None)

    def enabled(self):
        return self.levels() is not None

    # def read(self):
    #     _i = self.read_file()
    #     if _i:
    #         logging.info('existed tile: %s' % self)
    #         return self.image_to_bytes(_i)
    #     return None

    def interpolate(self):
        _ls = self.levels()
        if _ls is None:
            return None

        logging.info('interpolated tile: %s' % self)
        return self.image_to_bytes(self.interpo_tile(_ls))