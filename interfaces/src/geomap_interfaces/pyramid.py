"""Resample stored PNG blocks. This module never opens a source raster."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image

from .budgets import Budgets
from .errors import InterfaceError
from .mercator import MAX_LAT, ORIGIN_SHIFT, lat_from_mercator, lon_from_mercator, mercator_x, mercator_y, tile_span_m
from .paths import safe_join
from .registry import Dataset


class BlockStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def read_block(self, dataset: Dataset, zoom: int, tms_col: int, tms_row: int) -> np.ndarray | None:
        if dataset.pyramid is None:
            raise InterfaceError("styled_pyramid_not_configured", "dataset has no styled PNG pyramid", 409)
        relative = _block_relative(dataset, zoom, tms_col, tms_row)
        path = safe_join(self.root, relative)
        if not path.is_file():
            return None
        with Image.open(path) as handle:
            image = np.asarray(handle.convert("RGBA"), dtype=np.uint8).copy()
        expected = dataset.pyramid.block.pixels
        if image.shape != (expected, expected, 4):
            raise InterfaceError("invalid_block", "stored PNG block has an unexpected size", 500)
        return image


def render_bbox(
    dataset: Dataset,
    store: BlockStore,
    *,
    sampling: str,
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
    budgets: Budgets,
) -> np.ndarray:
    """Paint ``width`` by ``height`` pixels for an arbitrary bbox.

    ``sampling="mercator"`` spaces pixels evenly in EPSG:3857.
    ``sampling="geographic"`` spaces pixels evenly in longitude and latitude
    and only then converts each pixel to Web Mercator. That is the WMS 1.3.0
    geographic request; it is not an XYZ tile stretched over the bbox.
    """

    if dataset.pyramid is None:
        raise InterfaceError("styled_pyramid_not_configured", "dataset has no styled PNG pyramid", 409)
    if width < 1 or height < 1:
        raise InterfaceError("invalid_dimension", "width and height must be positive", 400)
    if width > budgets.max_wms_edge or height > budgets.max_wms_edge or width * height > budgets.max_wms_pixels:
        raise InterfaceError("budget_exceeded", "requested image exceeds the pixel budget", 400)
    if sampling == "mercator":
        _mercator_box(west, south, east, north)
        sample_x = west + (np.arange(width, dtype=np.float64) + 0.5) * (east - west) / width
        sample_y = north - (np.arange(height, dtype=np.float64) + 0.5) * (north - south) / height
        cover = (west, south, east, north)
        longitudes = lon_from_mercator(sample_x)
        latitudes = lat_from_mercator(sample_y)
    elif sampling == "geographic":
        _geographic_box(west, south, east, north)
        longitudes = west + (np.arange(width, dtype=np.float64) + 0.5) * (east - west) / width
        latitudes = north - (np.arange(height, dtype=np.float64) + 0.5) * (north - south) / height
        sample_x = np.asarray(mercator_x(longitudes), dtype=np.float64)
        sample_y = np.asarray(mercator_y(latitudes), dtype=np.float64)
        cover = (
            float(mercator_x(west)),
            float(mercator_y(south)),
            float(mercator_x(east)),
            float(mercator_y(north)),
        )
    else:
        raise InterfaceError("invalid_request", "unknown sampling mode", 500)

    mosaic, origin_west, origin_north, resolution = _mosaic(dataset, store, cover, width, budgets)
    output = np.zeros((height, width, 4), dtype=np.uint8)
    if mosaic is None:
        return output
    sx = (sample_x - origin_west) / resolution - 0.5
    sy = (origin_north - sample_y) / resolution - 0.5
    ix = np.floor(sx + 0.5).astype(np.int64)
    iy = np.floor(sy + 0.5).astype(np.int64)
    valid_x = (ix >= 0) & (ix < mosaic.shape[1])
    valid_y = (iy >= 0) & (iy < mosaic.shape[0])
    ok = valid_y[:, np.newaxis] & valid_x[np.newaxis, :]
    safe_x = np.clip(ix, 0, mosaic.shape[1] - 1)
    safe_y = np.clip(iy, 0, mosaic.shape[0] - 1)
    sampled = mosaic[safe_y[:, np.newaxis], safe_x[np.newaxis, :]]
    output[ok] = sampled[ok]
    nodata = np.asarray(dataset.pyramid.nodata.rgba, dtype=np.uint8)
    output[np.all(output == nodata, axis=2), 3] = 0
    bound_w, bound_s, bound_e, bound_n = dataset.bounds
    inside = ((longitudes >= bound_w) & (longitudes <= bound_e))[np.newaxis, :] & (
        (latitudes >= bound_s) & (latitudes <= bound_n)
    )[:, np.newaxis]
    output[~inside, 3] = 0
    return output


def render_xyz(dataset: Dataset, store: BlockStore, zoom: int, x: int, y: int, budgets: Budgets) -> np.ndarray:
    from .mercator import xyz_bounds

    if dataset.pyramid is None:
        raise InterfaceError("styled_pyramid_not_configured", "dataset has no styled PNG pyramid", 409)
    zooms = dataset.pyramid.zooms
    if zoom < zooms.view_min or zoom > zooms.view_max:
        raise InterfaceError("invalid_zoom", "zoom is outside the dataset view range", 400)
    limit = 2**zoom
    if x < 0 or y < 0 or x >= limit or y >= limit:
        raise InterfaceError("invalid_tile", "tile index is outside the zoom", 400)
    west, south, east, north = xyz_bounds(zoom, x, y)
    return render_bbox(
        dataset,
        store,
        sampling="mercator",
        west=west,
        south=south,
        east=east,
        north=north,
        width=budgets.tile_edge,
        height=budgets.tile_edge,
        budgets=budgets,
    )


def encode_png(image: np.ndarray) -> bytes:
    import io

    buffer = io.BytesIO()
    Image.fromarray(image, mode="RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def _mosaic(dataset: Dataset, store: BlockStore, cover: tuple[float, float, float, float], width: int, budgets: Budgets):
    west, south, east, north = cover
    meters_per_pixel = (east - west) / float(width)
    stored = list(dataset.pyramid.zooms.stored)
    ideal = math.log2((2.0 * ORIGIN_SHIFT) / (dataset.pyramid.block.tile_pixels * meters_per_pixel))
    preferred = min(stored, key=lambda level: (abs(level - ideal), level))
    ordered = [preferred]
    ordered.extend(sorted((level for level in stored if level < preferred), reverse=True))
    ordered.extend(sorted(level for level in stored if level > preferred))
    last_error: InterfaceError | None = None
    for zoom in ordered:
        try:
            return _mosaic_at(dataset, store, cover, zoom, budgets)
        except InterfaceError as exc:
            if exc.code != "budget_exceeded":
                raise
            last_error = exc
    if last_error:
        raise last_error
    raise InterfaceError("budget_exceeded", "requested image exceeds the tile budget", 400)


def _mosaic_at(dataset: Dataset, store: BlockStore, cover: tuple[float, float, float, float], zoom: int, budgets: Budgets):
    west, south, east, north = cover
    columns = _index_span(west, east, zoom)
    rows = _index_span(south, north, zoom)
    if columns is None or rows is None:
        return None, 0.0, 0.0, 1.0
    merge = dataset.pyramid.block.merge
    tile_pixels = dataset.pyramid.block.tile_pixels
    col0, col1 = columns
    row0, row1 = rows
    blocks = [
        (col, row)
        for col in range((col0 // merge) * merge, col1 + 1, merge)
        for row in range((row0 // merge) * merge, row1 + 1, merge)
    ]
    if len(blocks) > budgets.max_blocks:
        raise InterfaceError("budget_exceeded", "requested image exceeds the tile budget", 400)
    min_col = min(col for col, _row in blocks)
    max_col = max(col for col, _row in blocks) + merge
    min_row = min(row for _col, row in blocks)
    max_row = max(row for _col, row in blocks) + merge
    mosaic_width = (max_col - min_col) * tile_pixels
    mosaic_height = (max_row - min_row) * tile_pixels
    if mosaic_width * mosaic_height > budgets.max_mosaic_pixels:
        raise InterfaceError("budget_exceeded", "requested image exceeds the tile budget", 400)
    mosaic = np.zeros((mosaic_height, mosaic_width, 4), dtype=np.uint8)
    for col, row in blocks:
        block = store.read_block(dataset, zoom, col, row)
        if block is None:
            continue
        pixel_x = (col - min_col) * tile_pixels
        pixel_y = (max_row - (row + merge)) * tile_pixels
        mosaic[pixel_y : pixel_y + block.shape[0], pixel_x : pixel_x + block.shape[1]] = block
    tile_m = tile_span_m(zoom)
    origin_west = -ORIGIN_SHIFT + min_col * tile_m
    origin_north = -ORIGIN_SHIFT + max_row * tile_m
    resolution = tile_m / tile_pixels
    return mosaic, origin_west, origin_north, resolution


def _index_span(min_m: float, max_m: float, zoom: int) -> tuple[int, int] | None:
    tile_m = tile_span_m(zoom)
    origin = -ORIGIN_SHIFT
    limit = 2**zoom
    start = math.floor((min_m - origin) / tile_m + 1e-9)
    stop = math.floor((max_m - origin) / tile_m - 1e-9)
    start = max(0, start)
    stop = min(limit - 1, stop)
    if stop < start:
        return None
    return start, stop


def _block_relative(dataset: Dataset, zoom: int, tms_col: int, tms_row: int) -> str:
    layout = dataset.pyramid.layout
    name = f"{tms_row}.png"
    if layout == "legacy-v1":
        parts = (dataset.id, str(zoom), str(tms_col), name)
    else:
        parts = (dataset.id, "tiles", str(zoom), str(tms_col), name)
    return "/".join(parts)


def _mercator_box(west: float, south: float, east: float, north: float) -> None:
    limit = ORIGIN_SHIFT + 1e-6
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        raise InterfaceError("invalid_bbox", "bbox values must be finite", 400)
    if west >= east or south >= north or abs(west) > limit or abs(east) > limit or abs(south) > limit or abs(north) > limit:
        raise InterfaceError("invalid_bbox", "bbox is outside the Web Mercator domain", 400)


def _geographic_box(west: float, south: float, east: float, north: float) -> None:
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        raise InterfaceError("invalid_bbox", "bbox values must be finite", 400)
    if not (-180.0 <= west < east <= 180.0 and -MAX_LAT <= south < north <= MAX_LAT):
        raise InterfaceError("invalid_bbox", "geographic bbox is invalid or crosses the antimeridian", 400)

