"""Numeric point and summary queries. Refuses to sample styled PNG colors."""

from __future__ import annotations

from .budgets import Budgets
from .errors import InterfaceError
from .paths import safe_join
from .quant.cog import cog_point, cog_stats
from .quant.grid import grid_point, grid_stats
from .registry import Dataset

_ABSENT = {
    "available": False,
    "reason": "quantitative_backend_not_configured",
    "message": "No quantitative backend is configured. Styled PNG samples are not scientific values.",
}


def point_value(data_root, dataset: Dataset, lon: float, lat: float, budgets: Budgets) -> dict:
    _check_point(lon, lat)
    if dataset.quantitative is None:
        return dict(_ABSENT)
    directory = safe_join(data_root, dataset.id)
    spec = dataset.quantitative
    if spec.backend == "grid":
        return grid_point(directory, spec.path, lon, lat, budgets)
    if spec.backend == "cog":
        return cog_point(directory, spec.path, lon, lat, spec.band, spec.nodata, budgets)
    raise InterfaceError("quantitative_backend_not_configured", _ABSENT["message"], 409)


def window_stats(data_root, dataset: Dataset, west: float, south: float, east: float, north: float, budgets: Budgets) -> dict:
    if dataset.quantitative is None:
        return dict(_ABSENT)
    directory = safe_join(data_root, dataset.id)
    spec = dataset.quantitative
    if spec.backend == "grid":
        return grid_stats(directory, spec.path, west, south, east, north, budgets)
    if spec.backend == "cog":
        return cog_stats(directory, spec.path, west, south, east, north, spec.band, spec.nodata, budgets)
    raise InterfaceError("quantitative_backend_not_configured", _ABSENT["message"], 409)


def _check_point(lon: float, lat: float) -> None:
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise InterfaceError("invalid_point", "lon/lat is outside the geographic domain", 400)
