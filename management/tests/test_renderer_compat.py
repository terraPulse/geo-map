"""Worker PNGs must fit the sibling renderer's block reader.

The reader is loaded from commit 8292c07 of cursor/tile-view-correctness-720a.
This test does not modify that branch.
"""

import importlib
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

import support

from layer_manager.pyramid_engine import render_pyramid, sha256_bytes, write_gradient_geotiff

READER = "8292c07b2e42a5b6776569d947142d6f275f9e8b"
STOPS = (
    {"value": 0, "rgba": [0, 0, 180, 255]},
    {"value": 100, "rgba": [180, 0, 0, 255]},
)


class RendererCompatTests(unittest.TestCase):
    def test_merge_block_matches_reader_crop_for_native_coarse_and_nodata(self):
        serve = _load_serve()
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "gradient.tif")
            meta = write_gradient_geotiff(source)
            for resampling in ("nearest", "bilinear", "cubic"):
                out = os.path.join(tmp, resampling)
                result = render_pyramid(source, out, meta["bounds"], [3, 4], 2, resampling, STOPS)
                self.assertGreaterEqual(result["total"], 1)
                block_path = os.path.join(out, "tiles/4/0/0.png")
                image = Image.open(block_path)
                self.assertEqual(image.size, (512, 512))
                raw = open(block_path, "rb").read()
                layer = {"tile_merge": 2, "key_prefix": "builds/demo", "version": 2}
                west = serve.view_png_from_block(layer, raw, 4, 0, 0)
                east = serve.view_png_from_block(layer, raw, 4, 1, 0)
                north = serve.view_png_from_block(layer, raw, 4, 0, 1)
                self.assertEqual(west.size, (256, 256))
                self.assertEqual(east.size, (256, 256))
                self.assertEqual(north.size, (256, 256))
                self.assertGreater(west.getpixel((128, 200))[2], east.getpixel((128, 200))[2])
                self.assertEqual(north.getpixel((128, 128))[3], 0)
                relative = serve.stored_object_rel(layer, 4, 0, 0)
                self.assertEqual(relative, "builds/demo/tiles/4/0/0.png")
            coarse = Image.open(os.path.join(tmp, "nearest", "tiles/3/0/0.png"))
            self.assertEqual(coarse.size, (512, 512))
            pixels = list(coarse.getdata())
            self.assertTrue(any(pixel[3] == 255 for pixel in pixels))
            self.assertTrue(any(pixel[3] == 0 for pixel in pixels))

    def test_checkpoint_requires_the_same_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "gradient.tif")
            meta = write_gradient_geotiff(source)
            out = os.path.join(tmp, "pyramid")
            result = render_pyramid(source, out, meta["bounds"], [4], 1, "nearest", STOPS)
            target = os.path.join(out, result["completed"][0])
            with open(target, "wb") as handle:
                handle.write(b"not-the-png")
            with self.assertRaises(Exception) as raised:
                render_pyramid(
                    source,
                    out,
                    meta["bounds"],
                    [4],
                    1,
                    "nearest",
                    STOPS,
                    completed=result["completed"],
                    hashes=result["hashes"],
                )
            self.assertEqual(raised.exception.code, "tile_hash_mismatch")
            self.assertNotEqual(sha256_bytes(open(target, "rb").read()), result["hashes"][result["completed"][0]])


def _load_serve():
    root = pathlib.Path(tempfile.mkdtemp())
    repo = support.ROOT.parents[0]
    for source, dest in (
        (f"{READER}:util/lib/tile_runtime.py", root / "tile_runtime.py"),
        (f"{READER}:deploy/tile_pyramid_test/serve.py", root / "serve.py"),
    ):
        dest.write_bytes(subprocess.check_output(["git", "show", source], cwd=repo))
    sys.path.insert(0, str(root))
    return importlib.import_module("serve")


if __name__ == "__main__":
    unittest.main()
