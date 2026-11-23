'''Local counter and timing harness for PNG-block resampling.

Run from the repository root:

    python tests/bench_tile_resample.py

Prints one JSON object. The figures are measurements from this process
against a synthetic PNG. They are not a claim about production latency.
No network calls are made.
'''

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / 'util' / 'lib'
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import numpy as np
from PIL import Image
import io

from tile_runtime import TileCache


def synthetic_block(tiles=4, tile=256):
    '''One large RGBA block. Each 256px child has its own color.'''
    size = tiles * tile
    pixels = np.zeros((size, size, 4), dtype=np.uint8)
    colors = {}
    for row in range(tiles):
        for col in range(tiles):
            color = (col * 40, row * 40, 90, 255)
            pixels[row * tile:(row + 1) * tile, col * tile:(col + 1) * tile] = color
            colors[(col, row)] = color
    image = Image.fromarray(pixels, 'RGBA')
    handle = io.BytesIO()
    image.save(handle, format='PNG')
    return handle.getvalue(), colors


def _fetch_all(cache, payload, colors, tiles=4, tile=256):
    seen = {}

    def loader():
        cache.note_stat()
        cache.note_get(len(payload))
        return payload

    started = time.perf_counter()
    for row in range(tiles):
        for col in range(tiles):
            data = cache.get_or_load_bytes('block', loader)
            box = (col * tile, row * tile, (col + 1) * tile, (row + 1) * tile)
            crop = cache.crop_png('block', data, box)
            seen[(col, row)] = crop.getpixel((0, 0))
    elapsed = time.perf_counter() - started
    return seen, elapsed


def run_bench():
    payload, colors = synthetic_block()
    cached = TileCache(max_bytes=32 * 1024 * 1024, max_items=8, ttl=600)
    uncached = TileCache(max_bytes=0, max_items=0, ttl=600)
    cached_colors, cached_elapsed = _fetch_all(cached, payload, colors)
    uncached_colors, uncached_elapsed = _fetch_all(uncached, payload, colors)
    if cached_colors != colors or uncached_colors != colors:
        raise AssertionError('cropped block pixels do not match the synthetic source')
    cached_stats = cached.snapshot()
    uncached_stats = uncached.snapshot()
    cached_stats['wall_seconds'] = cached_elapsed
    uncached_stats['wall_seconds'] = uncached_elapsed
    cached_stats['png_bytes'] = len(payload)
    uncached_stats['png_bytes'] = len(payload)
    return cached_stats, uncached_stats


def main():
    cached, uncached = run_bench()
    json.dump(
        {
            'fixture': 'synthetic 1024x1024 RGBA PNG, 16 child crops',
            'cached': cached,
            'cache_disabled': uncached,
        },
        sys.stdout,
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
