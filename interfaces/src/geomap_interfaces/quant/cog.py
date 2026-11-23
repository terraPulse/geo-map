"""Optional COG reader. rasterio is imported only when a COG query runs."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..budgets import Budgets
from ..errors import InterfaceError
from ..paths import safe_join


def cog_point(dataset_dir: Path, relative: str, lon: float, lat: float, band: int, nodata: float | None, budgets: Budgets) -> dict:
    del budgets
    rasterio, transform, _bounds, _from_bounds, _window = _libraries()
    path = safe_join(dataset_dir, relative)
    if not path.is_file():
        raise InterfaceError("quantitative_source_unreadable", "quantitative source could not be read", 500)
    try:
        with rasterio.open(path) as source:
            if source.crs is None:
                raise InterfaceError("quantitative_source_unreadable", "quantitative source has no CRS", 500)
            marker = source_nodata(nodata, source.nodata)
            xs, ys = transform("EPSG:4326", source.crs, [lon], [lat])
            row, col = source.index(xs[0], ys[0])
            if row < 0 or col < 0 or row >= source.height or col >= source.width:
                return {"available": True, "crs": "EPSG:4326", "value": None, "nodata": True}
            sample = source.read(band, window=((int(row), int(row) + 1), (int(col), int(col) + 1)))
            value = float(sample[0, 0])
    except InterfaceError:
        raise
    except Exception as exc:
        raise InterfaceError("quantitative_source_unreadable", "quantitative source could not be read", 500) from exc
    if _missing(value, marker):
        return {"available": True, "crs": "EPSG:4326", "value": None, "nodata": True}
    return {"available": True, "crs": "EPSG:4326", "value": value, "nodata": False}


def cog_stats(
    dataset_dir: Path,
    relative: str,
    west: float,
    south: float,
    east: float,
    north: float,
    band: int,
    nodata: float | None,
    budgets: Budgets,
) -> dict:
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise InterfaceError("invalid_bbox", "geographic bbox is invalid", 400)
    rasterio, _transform, transform_bounds, from_bounds, window_type = _libraries()
    path = safe_join(dataset_dir, relative)
    if not path.is_file():
        raise InterfaceError("quantitative_source_unreadable", "quantitative source could not be read", 500)
    try:
        with rasterio.open(path) as source:
            if source.crs is None:
                raise InterfaceError("quantitative_source_unreadable", "quantitative source has no CRS", 500)
            left, bottom, right, top = transform_bounds("EPSG:4326", source.crs, west, south, east, north)
            window = from_bounds(left, bottom, right, top, source.transform).round_offsets().round_lengths()
            window = window.intersection(window_type(0, 0, source.width, source.height))
            if window.width <= 0 or window.height <= 0:
                return _empty()
            if window.width * window.height > budgets.max_stats_cells:
                raise InterfaceError("budget_exceeded", "quantitative window exceeds the cell budget", 400)
            array = np.asarray(source.read(band, window=window), dtype=np.float64)
            marker = source_nodata(nodata, source.nodata)
    except InterfaceError:
        raise
    except Exception as exc:
        raise InterfaceError("quantitative_source_unreadable", "quantitative source could not be read", 500) from exc
    valid = np.isfinite(array)
    if marker is not None:
        valid &= array != marker
    nodata_count = int(array.size - int(np.count_nonzero(valid)))
    if not np.any(valid):
        return _empty(nodata_count)
    chosen = array[valid]
    return {
        "available": True,
        "crs": "EPSG:4326",
        "count": int(chosen.size),
        "nodata_count": nodata_count,
        "min": float(chosen.min()),
        "max": float(chosen.max()),
        "mean": float(chosen.mean()),
    }


def source_nodata(configured: float | None, native: object) -> float | None:
    if configured is not None:
        return float(configured)
    if native is None:
        return None
    try:
        value = float(native)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value):
        return None
    return value


def _libraries():
    try:
        import rasterio
        from rasterio.warp import transform, transform_bounds
        from rasterio.windows import Window, from_bounds
    except ImportError as exc:
        raise InterfaceError(
            "quantitative_dependency_missing",
            "The COG quantitative backend requires the optional rasterio extra. No value was estimated.",
            501,
        ) from exc
    return rasterio, transform, transform_bounds, from_bounds, Window


def _missing(value: float, nodata: float | None) -> bool:
    if not np.isfinite(value):
        return True
    return nodata is not None and value == nodata


def _empty(nodata_count: int = 0) -> dict:
    return {
        "available": True,
        "crs": "EPSG:4326",
        "count": 0,
        "nodata_count": nodata_count,
        "min": None,
        "max": None,
        "mean": None,
    }
