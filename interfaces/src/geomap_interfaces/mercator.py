"""Web Mercator helpers matching the legacy tile grid.

The legacy library uses Earth radius 6378137 m, 256-pixel tiles, and XYZ row 0
at the north edge. Stored PNG blocks use the south-west tile index (TMS row).
"""

import math

import numpy as np

EARTH_RADIUS = 6378137.0
ORIGIN_SHIFT = math.pi * EARTH_RADIUS
MAX_LAT = math.degrees(2.0 * math.atan(math.exp(math.pi)) - math.pi / 2.0)
WORLD_BOUNDS = (-180.0, -MAX_LAT, 180.0, MAX_LAT)


def mercator_x(lon: np.ndarray | float) -> np.ndarray:
    return EARTH_RADIUS * np.radians(np.asarray(lon, dtype=np.float64))


def mercator_y(lat: np.ndarray | float) -> np.ndarray:
    values = np.asarray(lat, dtype=np.float64)
    return EARTH_RADIUS * np.log(np.tan(math.pi / 4.0 + np.radians(values) / 2.0))


def lon_from_mercator(x: np.ndarray | float) -> np.ndarray:
    return np.degrees(np.asarray(x, dtype=np.float64) / EARTH_RADIUS)


def lat_from_mercator(y: np.ndarray | float) -> np.ndarray:
    radians = np.asarray(y, dtype=np.float64) / EARTH_RADIUS
    return np.degrees(2.0 * np.arctan(np.exp(radians)) - math.pi / 2.0)


def tile_span_m(zoom: int) -> float:
    return (2.0 * ORIGIN_SHIFT) / float(2**zoom)


def xyz_bounds(zoom: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return west, south, east, north in EPSG:3857 for an XYZ tile."""

    span = tile_span_m(zoom)
    west = -ORIGIN_SHIFT + x * span
    north = ORIGIN_SHIFT - y * span
    return west, north - span, west + span, north
