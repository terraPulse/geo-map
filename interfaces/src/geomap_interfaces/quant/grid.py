"""Local north-up float64 grid. The header is JSON and the body is raw little-endian."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from ..budgets import Budgets
from ..errors import InterfaceError
from ..paths import safe_join

_HEADER_FIELDS = {"crs", "west", "south", "east", "north", "width", "height", "nodata", "dtype"}


def grid_point(dataset_dir: Path, relative: str, lon: float, lat: float, budgets: Budgets) -> dict:
    values, header = _load(dataset_dir, relative, budgets)
    col, row = _cell(header, lon, lat)
    if col is None:
        return _present(None, nodata=True)
    value = float(values[row, col])
    if _is_nodata(value, header["nodata"]):
        return _present(None, nodata=True)
    return _present(value, nodata=False)


def grid_stats(
    dataset_dir: Path,
    relative: str,
    west: float,
    south: float,
    east: float,
    north: float,
    budgets: Budgets,
) -> dict:
    _geo_box(west, south, east, north)
    values, header = _load(dataset_dir, relative, budgets)
    width = int(header["width"])
    height = int(header["height"])
    cell_w = (header["east"] - header["west"]) / width
    cell_h = (header["north"] - header["south"]) / height
    selected = []
    nodata_count = 0
    for row in range(height):
        center_lat = header["north"] - (row + 0.5) * cell_h
        if center_lat < south or center_lat > north:
            continue
        for col in range(width):
            center_lon = header["west"] + (col + 0.5) * cell_w
            if center_lon < west or center_lon > east:
                continue
            value = float(values[row, col])
            if _is_nodata(value, header["nodata"]):
                nodata_count += 1
            else:
                selected.append(value)
    if not selected:
        return {
            "available": True,
            "crs": "EPSG:4326",
            "count": 0,
            "nodata_count": nodata_count,
            "min": None,
            "max": None,
            "mean": None,
        }
    array = np.asarray(selected, dtype=np.float64)
    return {
        "available": True,
        "crs": "EPSG:4326",
        "count": int(array.size),
        "nodata_count": nodata_count,
        "min": float(array.min()),
        "max": float(array.max()),
        "mean": float(array.mean()),
    }


def _load(dataset_dir: Path, relative: str, budgets: Budgets):
    header_path = safe_join(dataset_dir, relative)
    if header_path.suffix != ".json" or not header_path.is_file():
        raise InterfaceError("quantitative_source_unreadable", "quantitative grid header is missing", 500)
    try:
        header = json.loads(header_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InterfaceError("quantitative_source_unreadable", "quantitative grid header is invalid", 500) from exc
    if not isinstance(header, dict) or set(header) != _HEADER_FIELDS:
        raise InterfaceError("quantitative_source_unreadable", "quantitative grid header is invalid", 500)
    if header["crs"] != "EPSG:4326" or header["dtype"] != "float64":
        raise InterfaceError("quantitative_source_unreadable", "quantitative grid must be EPSG:4326 float64", 500)
    width = header["width"]
    height = header["height"]
    if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
        raise InterfaceError("quantitative_source_unreadable", "quantitative grid size is invalid", 500)
    if width * height > budgets.max_stats_cells:
        raise InterfaceError("budget_exceeded", "quantitative grid exceeds the cell budget", 400)
    _geo_box(float(header["west"]), float(header["south"]), float(header["east"]), float(header["north"]))
    body = header_path.with_suffix(".f64")
    resolved = safe_join(dataset_dir, str(Path(relative).with_suffix(".f64")))
    if resolved != body.resolve() or not resolved.is_file():
        raise InterfaceError("quantitative_source_unreadable", "quantitative grid body is missing", 500)
    expected = width * height * 8
    if resolved.stat().st_size != expected:
        raise InterfaceError("quantitative_source_unreadable", "quantitative grid body size does not match", 500)
    values = np.fromfile(resolved, dtype="<f8").reshape((height, width))
    header = {
        "west": float(header["west"]),
        "south": float(header["south"]),
        "east": float(header["east"]),
        "north": float(header["north"]),
        "width": width,
        "height": height,
        "nodata": None if header["nodata"] is None else float(header["nodata"]),
    }
    return values, header


def _cell(header: dict, lon: float, lat: float) -> tuple[int | None, int | None]:
    if lon < header["west"] or lon > header["east"] or lat < header["south"] or lat > header["north"]:
        return None, None
    width = header["width"]
    height = header["height"]
    col = int(math.floor((lon - header["west"]) / ((header["east"] - header["west"]) / width)))
    row = int(math.floor((header["north"] - lat) / ((header["north"] - header["south"]) / height)))
    if lon == header["east"]:
        col = width - 1
    if lat == header["south"]:
        row = height - 1
    if col < 0 or row < 0 or col >= width or row >= height:
        return None, None
    return col, row


def _present(value: float | None, nodata: bool) -> dict:
    return {"available": True, "crs": "EPSG:4326", "value": value, "nodata": nodata}


def _is_nodata(value: float, nodata: float | None) -> bool:
    if math.isnan(value):
        return True
    return nodata is not None and value == nodata


def _geo_box(west: float, south: float, east: float, north: float) -> None:
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise InterfaceError("invalid_bbox", "geographic bbox is invalid", 400)
