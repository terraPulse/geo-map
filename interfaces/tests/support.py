"""Synthetic pyramids and a registry. Nothing here is a production dataset."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from geomap_interfaces.auth import Principal
from geomap_interfaces.budgets import Budgets
from geomap_interfaces.mercator import MAX_LAT, ORIGIN_SHIFT, lat_from_mercator
from geomap_interfaces.registry import registry_from_obj
from geomap_interfaces.runtime import Runtime

WORLD = [-180.0, -MAX_LAT, 180.0, MAX_LAT]
ANALYST = Principal("ada", frozenset({"analyst"}))


def write_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGBA").save(path, format="PNG")


def quadrant_block(nodata_southwest: bool) -> np.ndarray:
    image = np.zeros((512, 512, 4), dtype=np.uint8)
    image[0:256, 0:256] = (0, 180, 0, 255)
    image[0:256, 256:384] = (180, 0, 0, 255)
    image[0:256, 384:512] = (255, 140, 0, 255)
    image[256:512, 256:512] = (255, 220, 0, 255)
    if not nodata_southwest:
        image[256:512, 0:256] = (0, 0, 220, 255)
    return image


def latitude_block() -> np.ndarray:
    image = np.zeros((512, 512, 4), dtype=np.uint8)
    resolution = (2 * ORIGIN_SHIFT) / 512.0
    for row in range(512):
        northing = ORIGIN_SHIFT - (row + 0.5) * resolution
        latitude = float(lat_from_mercator(northing))
        image[row, :] = (255, 255, 255, 255) if latitude >= 60.0 else (0, 0, 0, 255)
    return image


def solid(color: tuple[int, int, int, int], size: int = 256) -> np.ndarray:
    image = np.zeros((size, size, 4), dtype=np.uint8)
    image[:, :] = color
    return image


def build_runtime(root: Path) -> Runtime:
    write_png(root / "demo" / "quad" / "tiles" / "1" / "0" / "0.png", quadrant_block(True))
    write_png(root / "demo" / "latband" / "tiles" / "1" / "0" / "0.png", latitude_block())
    write_png(root / "demo" / "bounded" / "tiles" / "1" / "0" / "0.png", quadrant_block(False))
    write_png(root / "demo" / "numbers" / "tiles" / "0" / "0" / "0.png", solid((255, 0, 0, 255)))
    write_png(root / "private" / "layer" / "tiles" / "0" / "0" / "0.png", solid((0, 255, 0, 255)))
    (root / "demo" / "quad" / "original.tif").write_bytes(b"not-a-raster")
    (root / "demo" / "quad" / "source.geojson").write_text('{"type":"FeatureCollection","features":[]}\n', encoding="utf-8")
    _write_grid(root / "demo" / "numbers")
    registry = registry_from_obj(_registry())
    return Runtime(
        registry=registry,
        data_root=root,
        public_base="https://maps.example",
        budgets=Budgets(),
        tokens={"analyst-token": ANALYST},
    )


def _write_grid(directory: Path) -> None:
    values = np.array(
        [
            [1, 2, 3, -9999],
            [5, 6, 7, 8],
            [9, 10, 11, 12],
            [13, 14, 15, 16],
        ],
        dtype="<f8",
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "values.json").write_text(
        json.dumps(
            {
                "crs": "EPSG:4326",
                "west": -10,
                "south": 40,
                "east": -6,
                "north": 44,
                "width": 4,
                "height": 4,
                "nodata": -9999,
                "dtype": "float64",
            }
        ),
        encoding="utf-8",
    )
    values.tofile(directory / "values.f64")


def _pyramid(stored, native, view_min, view_max, merge):
    return {
        "layout": "legacy-v2",
        "zooms": {"native": native, "stored": stored, "view_min": view_min, "view_max": view_max},
        "block": {"merge": merge, "tile_pixels": 256, "pixels": merge * 256},
        "nodata": {"rgba": [0, 0, 0, 0]},
    }


def _styled(dataset_id, title, bounds, pyramid):
    return {
        "id": dataset_id,
        "title": title,
        "description": title,
        "backend": "png",
        "bounds": bounds,
        "crs": "EPSG:3857",
        "pyramid": pyramid,
        "styles": [
            {"id": "default", "title": "Styled PNG", "kind": "styled-png"},
            {"id": "alias", "title": "Same styled PNG", "kind": "styled-png"},
        ],
        "revision": "r1",
        "access": {"visibility": "public"},
        "assets": [],
        "quantitative": None,
    }


def _registry() -> dict:
    quad = _styled("demo/quad", "Quadrant pyramid", WORLD, _pyramid([1], 1, 0, 3, 2))
    quad["assets"] = [
        {
            "id": "source",
            "role": "source-data",
            "title": "Source descriptor",
            "media_type": "application/geo+json",
            "local": "source.geojson",
        },
        {
            "id": "upstream",
            "role": "source-data",
            "title": "Upstream link",
            "media_type": "application/json",
            "href": "https://data.example/quad.json",
        },
    ]
    numbers = _styled("demo/numbers", "Red picture with a numeric grid", WORLD, _pyramid([0], 0, 0, 0, 1))
    numbers["styles"] = [{"id": "default", "title": "Styled PNG", "kind": "styled-png"}]
    numbers["quantitative"] = {"backend": "grid", "path": "values.json", "band": 1, "nodata": -9999}
    private = _styled("private/layer", "Restricted layer", WORLD, _pyramid([0], 0, 0, 0, 1))
    private["styles"] = [{"id": "default", "title": "Styled PNG", "kind": "styled-png"}]
    private["access"] = {"visibility": "restricted", "read_roles": ["analyst"]}
    return {
        "schema": "geo-map.dataset-registry/v0",
        "datasets": [
            quad,
            _styled("demo/latband", "Latitude band", WORLD, _pyramid([1], 1, 0, 2, 2)),
            _styled("demo/bounded", "North-east bounds", [0, 0, 180, MAX_LAT], _pyramid([1], 1, 0, 2, 2)),
            numbers,
            private,
            {
                "id": "demo/cog",
                "title": "COG values",
                "description": "Numeric COG without a styled pyramid.",
                "backend": "cog",
                "bounds": [-1, -1, 1, 1],
                "crs": "EPSG:4326",
                "pyramid": None,
                "styles": [],
                "revision": "r1",
                "access": {"visibility": "public"},
                "assets": [],
                "quantitative": {"backend": "cog", "path": "values.tif", "band": 1, "nodata": -9999},
            },
        ],
    }


def call(app, path: str, query: str = "", headers=None, method: str = "GET"):
    import io

    captured = {}

    def start_response(status, response_headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = response_headers

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "SERVER_NAME": "test",
        "SERVER_PORT": "80",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(),
        "wsgi.errors": io.StringIO(),
        "CONTENT_LENGTH": "0",
        "wsgi.multiprocess": False,
        "wsgi.multithread": False,
        "wsgi.run_once": True,
    }
    for key, value in (headers or {}).items():
        environ["HTTP_" + key.upper().replace("-", "_")] = value
    body = b"".join(app(environ, start_response))
    return captured["status"], captured["headers"], body
