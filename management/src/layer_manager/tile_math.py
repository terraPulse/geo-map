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


def iter_blocks(bounds, zooms, merge):
    """Version-2 block origins. One block is merge by merge Web Mercator tiles."""
    merge = int(merge)
    if merge < 1 or merge > MAX_MERGE:
        raise ValueError("tile_merge")
    minx, miny, maxx, maxy = (float(bounds["minx"]), float(bounds["miny"]), float(bounds["maxx"]), float(bounds["maxy"]))
    if minx >= maxx or miny >= maxy:
        raise ValueError("bounds")
    blocks = []
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
        for y in range(row0 - (row0 % merge), row1 + 1, merge):
            for x in range(col0 - (col0 % merge), col1 + 1, merge):
                origin_x = -HALF + x * span
                origin_y = -HALF + y * span
                blocks.append({
                    "z": level,
                    "x": x,
                    "y": y,
                    "minx": origin_x,
                    "miny": origin_y,
                    "maxx": origin_x + span * merge,
                    "maxy": origin_y + span * merge,
                    "width": TILE_PX * merge,
                    "height": TILE_PX * merge,
                })
    return blocks


def count_tiles(bounds, zooms, merge):
    """Return (count, sample). The sample is not a substitute for the block list."""
    blocks = iter_blocks(bounds, zooms, merge)
    sample = [{"z": block["z"], "x": block["x"], "y": block["y"]} for block in blocks[:5]]
    return len(blocks), sample
