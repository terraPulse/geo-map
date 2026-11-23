'''Invoke the PNG-pyramid test handler and the built zip. No AWS calls.'''

import importlib
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / 'deploy' / 'tile_pyramid_test'
LIB = ROOT / 'util' / 'lib'
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(PKG))

import fixture_data
import handler
import reader
import serve
from fixture_data import LAYER_ID, QUADRANTS


def _png(body, encoded=True):
    raw = body if not encoded else __import__('base64').b64decode(body)
    return Image.open(io.BytesIO(raw))


def _event(path, method='GET', headers=None, version='2.0'):
    headers = headers or {}
    if version == '2.0':
        return {
            'version': '2.0',
            'rawPath': path,
            'rawQueryString': '',
            'headers': headers,
            'requestContext': {'http': {'method': method, 'path': path}},
            'isBase64Encoded': False,
        }
    return {
        'path': path,
        'httpMethod': method,
        'headers': headers,
        'requestContext': {},
        'isBase64Encoded': False,
    }


class PyramidTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        fixture_data.write_fixture(os.path.join(self.root, 'fixtures'))
        os.environ['TILE_FIXTURE_ROOT'] = os.path.join(self.root, 'fixtures')
        os.environ['TILE_REGISTRY_JSON'] = json.dumps(fixture_data.registry_document())
        os.environ['TILE_AUTH_MODE'] = 'iam'
        os.environ.pop('TILE_AUTH_TOKEN', None)
        os.environ.pop('TILE_BUCKET', None)
        os.environ['TILE_CORS_ORIGIN'] = 'https://preview.example.test'
        handler.reset_for_tests()

    def tearDown(self):
        handler.reset_for_tests()
        self.tmp.cleanup()

    def test_block_window_matches_historical_merge_box(self):
        self.assertEqual(serve.block_window(2, 1, 0, 2), (0, 0, (256, 256, 512, 512)))
        self.assertEqual(serve.block_window(2, 0, 1, 2)[2], (0, 0, 256, 256))

    def test_v2_tile_is_binary_png_of_the_block_quadrant(self):
        response = handler.lambda_handler(
            _event('/tiletest/v1/zx_y/%s/2/1/0.png' % LAYER_ID), None)
        self.assertEqual(response['statusCode'], 200)
        self.assertTrue(response['isBase64Encoded'])
        self.assertEqual(response['headers']['content-type'], 'image/png')
        self.assertEqual(response['headers']['x-geomap-tile'], 'tile')
        self.assertEqual(response['headers']['x-geomap-adapter'], 'geomap.png_pyramid')
        image = _png(response['body'])
        self.assertEqual(image.size, (256, 256))
        self.assertEqual(image.getpixel((0, 0)), QUADRANTS[(1, 0)])

    def test_zoomin_and_zoomout_use_png_colors_only(self):
        finer = handler.lambda_handler(
            _event('/tiletest/v1/map/%s/3/2/0.png' % LAYER_ID), None)
        self.assertEqual(_png(finer['body']).getpixel((10, 10)), QUADRANTS[(1, 0)])
        coarser = handler.lambda_handler(
            _event('/tiletest/v1/zx_y/%s/1/0/0.png' % LAYER_ID), None)
        self.assertEqual(_png(coarser['body']).getpixel((10, 10)), QUADRANTS[(0, 1)])

    def test_missing_png_is_transparent_and_source_flag_is_ignored(self):
        os.environ['GEOMAP_VIEW_SOURCE_RENDER'] = '1'
        handler.reset_for_tests()
        response = handler.lambda_handler(
            _event('/tiletest/v1/zx_y/%s/2/3/3.png' % LAYER_ID), None)
        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(response['headers']['x-geomap-tile'], 'nodata')
        image = _png(response['body'])
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0, 0))
        os.environ.pop('GEOMAP_VIEW_SOURCE_RENDER', None)

    def test_bounds_allowlist_and_urls(self):
        over = handler.lambda_handler(
            _event('/tiletest/v1/zx_y/%s/2/4/0.png' % LAYER_ID), None)
        self.assertEqual(over['statusCode'], 400)
        unknown = handler.lambda_handler(
            _event('/tiletest/v1/zx_y/fixture/not-allowed/2/0/0.png'), None)
        self.assertEqual(unknown['statusCode'], 403)
        escaped = handler.lambda_handler(
            _event('/tiletest/v1/zx_y/../secret/2/0/0.png'), None)
        self.assertEqual(escaped['statusCode'], 400)
        remote = handler.lambda_handler(
            _event('/tiletest/v1/https://example.test/a/2/0/0.png'), None)
        self.assertEqual(remote['statusCode'], 400)

    def test_metadata_contract_for_a_management_preview(self):
        response = handler.lambda_handler(_event('/tiletest/v1/layers'), None)
        self.assertEqual(response['statusCode'], 200)
        self.assertFalse(response['isBase64Encoded'])
        body = json.loads(response['body'])
        self.assertEqual(body['adapter'], 'geomap.png_pyramid')
        self.assertEqual(body['adapter_version'], '1.0.0')
        self.assertFalse(body['source_raster_reads'])
        self.assertEqual(body['layers'][0]['id'], LAYER_ID)
        self.assertTrue(body['layers'][0]['fixture'])
        self.assertNotIn('bucket', json.dumps(body))

    def test_header_auth_fails_closed_and_cors_is_exact(self):
        os.environ['TILE_AUTH_MODE'] = 'header'
        os.environ['TILE_AUTH_TOKEN'] = ''
        handler.reset_for_tests()
        closed = handler.lambda_handler(
            _event('/tiletest/v1/layers'), None)
        self.assertEqual(closed['statusCode'], 401)
        os.environ['TILE_AUTH_TOKEN'] = 'test-token-value'
        handler.reset_for_tests()
        denied = handler.lambda_handler(_event('/tiletest/v1/layers'), None)
        self.assertEqual(denied['statusCode'], 401)
        ok = handler.lambda_handler(
            _event('/tiletest/v1/layers', headers={'x-tile-test-token': 'test-token-value'}),
            None)
        self.assertEqual(ok['statusCode'], 200)
        preflight = handler.lambda_handler(
            _event('/tiletest/v1/layers', method='OPTIONS',
                   headers={'origin': 'https://preview.example.test'}),
            None)
        self.assertEqual(preflight['statusCode'], 204)
        self.assertEqual(
            preflight['headers']['access-control-allow-origin'],
            'https://preview.example.test')
        other = handler.lambda_handler(
            _event('/tiletest/v1/layers', method='OPTIONS',
                   headers={'origin': 'https://evil.example.test'}),
            None)
        self.assertEqual(other['statusCode'], 403)
        self.assertNotIn('access-control-allow-origin', other['headers'])

    def test_payload_v1_shape_still_returns_a_png(self):
        response = handler.lambda_handler(
            _event('/tiletest/v1/zxy/%s/2/1/0.png' % LAYER_ID, version='1.0'), None)
        self.assertEqual(response['statusCode'], 200)
        self.assertTrue(response['isBase64Encoded'])
        self.assertEqual(response['headers']['content-type'], 'image/png')

    def test_registry_rejects_bucket_override_and_bad_prefix(self):
        document = fixture_data.registry_document()
        document['layers'][0]['bucket'] = 'other-bucket'
        with self.assertRaises(Exception):
            import registry
            registry.validate_registry(document)
        self.assertIsNone(reader._s3_key('tile-pyramid-test', '../secret.png'))
        self.assertEqual(
            reader._s3_key('tile-pyramid-test', 'fixture/demo-pyramid/tiles/2/0/0.png'),
            'tile-pyramid-test/fixture/demo-pyramid/tiles/2/0/0.png')

    def test_s3_reader_uses_one_injected_client(self):
        class Body:
            def __init__(self, data):
                self.data = data

            def read(self):
                return self.data

        class Client:
            def __init__(self):
                self.calls = []

            def get_object(self, Bucket, Key):
                self.calls.append((Bucket, Key))
                return {'Body': Body(b'\x89PNG fake')}

        client = Client()
        s3 = reader.S3Reader('staging-bucket', 'tile-pyramid-test', client=client)
        first_key, first = s3.get_bytes('fixture/demo-pyramid/tiles/2/0/0.png')
        second_key, second = s3.get_bytes('fixture/demo-pyramid/tiles/2/0/0.png')
        self.assertEqual(first, second)
        self.assertEqual(first_key, second_key)
        self.assertEqual(client.calls, [(
            'staging-bucket',
            'tile-pyramid-test/fixture/demo-pyramid/tiles/2/0/0.png',
        )])


class ArtifactTests(unittest.TestCase):
    def test_zip_imports_and_serves_without_gio(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, 'function.zip')
            env = os.environ.copy()
            env['TILE_PYRAMID_ZIP'] = zip_path
            subprocess.check_call(
                [sys.executable, str(PKG / 'build_artifact.py')],
                cwd=str(ROOT),
                env=env,
            )
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
            self.assertIn('handler.py', names)
            self.assertIn('tile_runtime.py', names)
            self.assertIn('registry.json', names)
            self.assertTrue(any(name.startswith('PIL/') for name in names))
            self.assertTrue(any(name.endswith('fixtures/fixture/demo-pyramid/tiles/2/0/0.png')
                                for name in names))
            self.assertFalse(any(name.startswith('gio/') or name.endswith('/handler.py') and
                                 name != 'handler.py' for name in names))
            joined = '\n'.join(names)
            self.assertNotIn('lambda/handler.py', joined)
            self.assertNotIn('mod_grid', joined)
            unpack = os.path.join(tmp, 'task')
            os.makedirs(unpack)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(unpack)
            handler_text = (pathlib.Path(unpack) / 'handler.py').read_text()
            self.assertIn('PNG-pyramid', handler_text)
            self.assertNotIn('def make_tile', handler_text)
            for name in ('handler', 'serve', 'registry', 'reader', 'tile_runtime', 'fixture_data'):
                sys.modules.pop(name, None)
            sys.path.insert(0, unpack)
            try:
                unpacked = importlib.import_module('handler')
                unpacked.reset_for_tests()
                os.environ['TILE_AUTH_MODE'] = 'iam'
                os.environ.pop('TILE_REGISTRY_JSON', None)
                os.environ.pop('TILE_FIXTURE_ROOT', None)
                os.environ['TILE_CORS_ORIGIN'] = ''
                response = unpacked.lambda_handler(
                    _event('/tiletest/v1/zx_y/%s/2/1/0.png' % LAYER_ID), None)
            finally:
                sys.path.remove(unpack)
                sys.modules.pop('handler', None)
            self.assertEqual(response['statusCode'], 200)
            self.assertTrue(response['isBase64Encoded'])
            self.assertEqual(_png(response['body']).getpixel((0, 0)), QUADRANTS[(1, 0)])
            manifest = json.loads(pathlib.Path(zip_path + '.manifest.json').read_text())
            self.assertEqual(manifest['runtime'], 'python3.12')
            self.assertEqual(manifest['handler'], 'handler.lambda_handler')
            self.assertEqual(len(manifest['sha256']), 64)


if __name__ == '__main__':
    unittest.main()
