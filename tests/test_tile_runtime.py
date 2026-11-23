'''Regression tests for tile-view correctness. No network and no gio.'''

import importlib.util
import os
import pathlib
import sys
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / 'util' / 'lib'
sys.path.insert(0, str(LIB))

import tile_runtime
from tile_runtime import (
    MAX_ZOOM,
    TileCache,
    apply_region_mask,
    child_sample_window,
    is_safe_layer_tag,
    nearest_stored_level,
    normalize_loc,
    normalize_service_path,
    safe_child_path,
    view_miss_action,
)

import numpy as np
from PIL import Image


def _load_handler():
    spec = importlib.util.spec_from_file_location(
        'geomap_lambda_handler', ROOT / 'lambda' / 'handler.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _package(name):
    import types
    if name in sys.modules and getattr(sys.modules[name], '__path__', None):
        return sys.modules[name]
    module = types.ModuleType(name)
    module.__path__ = [str(LIB)]
    module.__file__ = str(LIB / '__init__.py')
    sys.modules[name] = module
    return module


class ViewMissTests(unittest.TestCase):
    def test_block_layer_view_miss_does_not_render_source(self):
        self.assertEqual(view_miss_action(False, True, False), 'nodata')
        self.assertEqual(view_miss_action(False, True, True), 'nodata')

    def test_pregeneration_still_renders_source(self):
        self.assertEqual(view_miss_action(True, True, True), 'render_source')
        self.assertEqual(view_miss_action(True, False, True), 'render_source')

    def test_legacy_dynamic_layers_keep_floor(self):
        self.assertEqual(view_miss_action(False, False, True), 'nodata')
        self.assertEqual(view_miss_action(False, False, False), 'render_source')

    def test_force_flag_restores_source_render(self):
        self.assertEqual(
            view_miss_action(False, True, False, force_source_render=True),
            'render_source')

    def test_build_script_marks_pregeneration(self):
        text = (ROOT / 'util' / 'bin' / 'build_tiles_task.py').read_text()
        self.assertIn('building_tiles=True', text)

    def test_view_reader_uses_the_policy(self):
        text = (ROOT / 'util' / 'lib' / 'map_tile_task.py').read_text()
        self.assertIn('view_miss_action(', text)
        self.assertIn("if _action == 'nodata'", text)


class PathTests(unittest.TestCase):
    def test_legacy_service_indexes(self):
        self.assertEqual(
            normalize_service_path('lincoln/water/y2025/12/10/20.png', 'zx_y'),
            'lincoln/water/y2025/12/10/20.png')
        # Far-edge form. Level 12 has 4096 indexes; "_1" -> 4094.
        self.assertEqual(
            normalize_service_path('lincoln/water/y2025/12/10/_1.png', 'zx_y'),
            'lincoln/water/y2025/12/10/4094.png')
        # Service parser treats "_0" as 0. The Lambda parser does not.
        self.assertEqual(normalize_loc('_0', 3, False), 0)
        self.assertEqual(
            normalize_service_path('tag/2/1/0.png', 'zxy'),
            'tag/2/1/0.png')
        self.assertEqual(
            normalize_service_path('tag/2/1/1.png', 'zxy'),
            'tag/2/1/2.png')
        self.assertEqual(
            normalize_service_path('tag/1/1/2.png', 'xyz'),
            'tag/2/1/2.png')

    def test_rejects_escape_and_extreme_zoom(self):
        self.assertIsNone(normalize_service_path('../etc/1/2/3.png', 'zx_y'))
        self.assertIsNone(normalize_service_path('a/../b/1/2/3.png', 'zx_y'))
        self.assertIsNone(normalize_service_path('tag/%s/0/0.png' % (MAX_ZOOM + 1), 'zx_y'))
        self.assertEqual(
            normalize_service_path('tag/%s/0/0.png' % MAX_ZOOM, 'zx_y'),
            'tag/%s/0/0.png' % MAX_ZOOM)
        self.assertFalse(is_safe_layer_tag('..'))
        self.assertTrue(is_safe_layer_tag('lincoln/water_freq/y2025'))

    def test_bad_order_still_raises(self):
        with self.assertRaises(Exception):
            normalize_service_path('tag/1/2/3.png', 'nope')

    def test_join_cannot_discard_the_root(self):
        self.assertEqual(os.path.join('s3://bucket/web', '/etc/passwd'), '/etc/passwd')
        self.assertIsNone(safe_child_path('s3://bucket/web', '/etc/passwd'))
        self.assertIsNone(safe_child_path('s3://bucket/web', '../secret.png'))
        self.assertEqual(
            safe_child_path('s3://bucket/web', 'js/map.js'),
            os.path.join('s3://bucket/web', 'js/map.js'))


class ResamplePolicyTests(unittest.TestCase):
    def test_nearest_stored_level_uses_the_candidate(self):
        # Historical bug: a one-item candidate list returned levels[0].
        self.assertEqual(nearest_stored_level(8, [12, 5]), 5)
        self.assertEqual(nearest_stored_level(7, [3, 5, 12]), 5)
        self.assertEqual(nearest_stored_level(2, [3, 5, 12]), 3)
        self.assertIsNone(nearest_stored_level(4, []))

    def test_level_zero_is_a_real_source(self):
        _package('geo_map_util')
        interpo_mod = importlib.import_module('geo_map_util.map_tile_interpo')

        class Tile:
            z = 2
            x = 0
            y = 0
            merge = 1

        calls = []

        def fake_zoomin(self, level):
            calls.append(level)
            return Image.new('RGBA', (1, 1), (1, 2, 3, 4))

        original = interpo_mod.interpo.zoomin
        interpo_mod.interpo.zoomin = fake_zoomin
        try:
            image = interpo_mod.interpo('layer', Tile())._image(0)
        finally:
            interpo_mod.interpo.zoomin = original
        self.assertEqual(calls, [0])
        self.assertEqual(image.getpixel((0, 0)), (1, 2, 3, 4))

    def test_zoomin_copies_the_child_half(self):
        _package('geo_map_util')
        interpo_mod = importlib.import_module('geo_map_util.map_tile_interpo')
        parent = Image.new('RGBA', (256, 256), (0, 0, 255, 255))
        draw = parent.load()
        for y in range(256):
            for x in range(128):
                draw[x, y] = (255, 0, 0, 255)

        def fake_read(self):
            return parent

        original = interpo_mod.interpo.read_file
        interpo_mod.interpo.read_file = fake_read
        try:
            class Tile:
                def __init__(self, x):
                    self.z = 3
                    self.x = x
                    self.y = 0
                    self.merge = 1
                    self.zx_y = self

            left = interpo_mod.interpo('layer', Tile(0)).zoomin(2)
            right = interpo_mod.interpo('layer', Tile(1)).zoomin(2)
        finally:
            interpo_mod.interpo.read_file = original
        self.assertEqual(left.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(right.getpixel((0, 0)), (0, 0, 255, 255))
        window = child_sample_window(1, 0, 3, 2, 1)
        self.assertEqual(window['box'], (128, 0, 256, 128))


class MaskTests(unittest.TestCase):
    def test_rgba_alpha_survives_inside_the_region(self):
        data = np.zeros((4, 2, 2), dtype=np.uint8)
        data[0:3, :, :] = 10
        data[3, :, :] = 200
        mask = np.array([[1, 0], [1, 0]], dtype=np.uint8)
        apply_region_mask(data, mask, None)
        self.assertEqual(int(data[3, 0, 0]), 200)
        self.assertEqual(int(data[3, 0, 1]), 0)
        self.assertEqual(int(data[0, 0, 1]), 10)

    def test_single_band_uses_nodata_outside(self):
        data = np.array([[5, 6], [7, 8]], dtype=np.uint8)
        mask = np.array([[1, 0], [0, 1]], dtype=np.uint8)
        apply_region_mask(data, mask, 255)
        self.assertEqual(data.tolist(), [[5, 255], [255, 8]])

    def test_missing_nodata_and_alpha_still_fail(self):
        with self.assertRaises(Exception):
            apply_region_mask(np.zeros((2, 2), dtype=np.uint8), np.ones((2, 2)), None)
        with self.assertRaises(Exception):
            apply_region_mask(np.zeros((3, 2, 2), dtype=np.uint8), np.ones((2, 2)), 0)

    def test_lambda_copy_no_longer_zeroes_the_whole_alpha(self):
        text = (ROOT / 'lambda' / 'handler.py').read_text()
        self.assertNotIn('bnd.data[3, :, :] = 0', text)
        self.assertIn('apply_region_mask', text)


class LambdaResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handler = _load_handler()

    def test_missing_and_unsafe_paths_return_400(self):
        missing = self.handler.lambda_handler({}, None)
        self.assertEqual(missing['statusCode'], 400)
        self.assertFalse(missing['isBase64Encoded'])
        unsafe = self.handler.prepare_request({'path': '/a/../b/1/2/3.png'})
        self.assertIsNone(unsafe[0])
        self.assertEqual(unsafe[1]['statusCode'], 400)
        extreme = self.handler.prepare_request({'path': '/tag/31/0/0.png'})
        self.assertEqual(extreme[1]['statusCode'], 400)

    def test_legacy_lambda_index_and_valid_path(self):
        normalize = self.handler.map_tile._normalize_path
        self.assertEqual(normalize(None, 'tag/3/_0/1.png'), 'tag/3/7/1.png')
        self.assertEqual(normalize(None, 'tag/3/1/_1.png'), 'tag/3/1/6.png')
        path, err = self.handler.prepare_request(
            {'path': '/lincoln/water/y2025/3/1/2.png'})
        self.assertIsNone(err)
        self.assertEqual(path, 'lincoln/water/y2025/3/1/2.png')

    def test_exhausted_retries_return_json_500(self):
        failure = self.handler.failure_response()
        self.assertEqual(failure['statusCode'], 500)
        self.assertIn('failed to produce the tile', failure['body'])
        self.assertNotIn('isBase64Encoded": true', str(failure).lower())
        source = (ROOT / 'lambda' / 'handler.py').read_text()
        self.assertIn('return failure_response()', source)


class CacheTests(unittest.TestCase):
    def test_single_flight_and_byte_cap(self):
        cache = TileCache(max_bytes=100, max_items=4, ttl=60)
        calls = {'n': 0}

        def loader():
            calls['n'] += 1
            time.sleep(0.05)
            cache.note_stat()
            payload = b'x' * 40
            cache.note_get(len(payload))
            return payload

        results = []

        def worker():
            results.append(cache.get_or_load_bytes('block', loader))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(calls['n'], 1)
        self.assertEqual(len(results), 8)
        self.assertTrue(all(item == b'x' * 40 for item in results))
        self.assertEqual(cache.snapshot()['remote_get'], 1)
        self.assertLessEqual(cache.snapshot()['stored_bytes'], 100)

        cache.put_bytes('a', b'y' * 80)
        cache.put_bytes('b', b'z' * 80)
        self.assertLessEqual(cache.snapshot()['stored_bytes'], 100)

    def test_expired_entry_is_reread(self):
        cache = TileCache(max_bytes=1000, max_items=4, ttl=-1)
        cache.put_bytes('k', b'abc')
        self.assertIsNone(cache.get_bytes('k'))


class BlockFetchTests(unittest.TestCase):
    def test_sixteen_crops_decode_the_block_once(self):
        spec = importlib.util.spec_from_file_location(
            'bench_tile_resample', ROOT / 'tests' / 'bench_tile_resample.py')
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)
        cached, uncached = bench.run_bench()
        self.assertEqual(cached['remote_get'], 1)
        self.assertEqual(cached['decode_calls'], 1)
        self.assertEqual(cached['image_hits'], 15)
        self.assertEqual(uncached['remote_get'], 16)
        self.assertEqual(uncached['decode_calls'], 16)
        self.assertGreater(cached['remote_bytes'], 0)
        self.assertGreater(uncached['decode_seconds'], 0)
        self.assertGreater(cached['resample_seconds'], 0)


if __name__ == '__main__':
    unittest.main()
