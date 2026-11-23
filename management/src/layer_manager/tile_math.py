"""Web Mercator tile counts matching util/lib/map_tile.py.

Counts are exact for an EPSG:3857 box and a merge factor. They do not open
a raster, so they are a plan, not a measured build.
"""

import math

EARTH = 6378137.0
HALF = EARTH * math.pi
TILE_PX = 256
MAX_MERGE = 8


def tile_span(level):
    return (2 * HALF) / (2 ** level)


def count_tiles(bounds, zooms, merge):
    """Return (count, sample) or raise ValueError if the box is not usable."""
    merge = int(merge)
    if merge < 1 or merge > MAX_MERGE:
        raise ValueError("tile_merge")
    minx, miny, maxx, maxy = (float(bounds["minx"]), float(bounds["miny"]), float(bounds["maxx"]), float(bounds["maxy"]))
    if minx >= maxx or miny >= maxy:
        raise ValueError("bounds")
    total = 0
    sample = []
    for level in zooms:
        level = int(level)
        if level < 0 or level > 24:
            raise ValueError("zoom")
        span = tile_span(level)
        limit = 2 ** level
        col0 = max(0, int((minx + HALF) / span))
        col1 = min(limit - 1, int((maxx + HALF) / span))
        row0 = max(0, int((miny + HALF) / span))
        row1 = min(limit - 1, int((maxy + HALF) / span))
        if col1 < col0 or row1 < row0:
            continue
        start_col = col0 - (col0 % merge)
        start_row = row0 - (row0 % merge)
        cols = list(range(start_col, col1 + 1, merge))
        rows = list(range(start_row, row1 + 1, merge))
        total += len(cols) * len(rows)
        if len(sample) < 5 and cols and rows:
            sample.append({"z": level, "x": cols[0], "y": rows[0]})
    return total, sample
