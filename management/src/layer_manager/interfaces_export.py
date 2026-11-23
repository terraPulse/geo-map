"""Export one layer-registry v1 record as a dataset-registry v0 document.

The two schemas are not the same store. This function does not write the
v0 document into the registry and does not edit interfaces/.
"""

import math

from .tile_math import EARTH, HALF

SCHEMA = "geo-map.dataset-registry/v0"


def export_dataset_v0(record):
    bounds = record["bounds"]
    west, south = _wgs84(bounds["minx"], bounds["miny"])
    east, north = _wgs84(bounds["maxx"], bounds["maxy"])
    levels = [int(level) for level in record["pyramid"]["processed_levels"]]
    merge = int(record["pyramid"]["tile_merge"])
    uri = (record.get("source_revisions") or [{}])[0].get("uri") or ""
    return {
        "schema": SCHEMA,
        "datasets": [
            {
                "id": record["tag"],
                "title": record["title"],
                "backend": "png" if record["backend"] == "png-pyramid" else "cog",
                "bounds": [west, south, east, north],
                "crs": "EPSG:3857" if bounds.get("crs") == "EPSG:3857" else bounds.get("crs"),
                "pyramid": {
                    "layout": "legacy-v2" if record["pyramid"].get("version", 2) >= 2 else "legacy-v1",
                    "zooms": {
                        "native": max(levels),
                        "stored": levels,
                        "view_min": min(levels),
                        "view_max": max(levels),
                    },
                    "block": {"merge": merge, "tile_pixels": 256, "pixels": 256 * merge},
                    "nodata": {"rgba": [0, 0, 0, 0]},
                },
                "styles": [{"id": "ramp", "title": record["title"], "kind": "styled-png"}],
                "revision": str(record["revision"]),
                "access": {"visibility": "restricted", "read_roles": ["layer-reader", "layer-admin"]},
                "legacy": {
                    "version": 2,
                    "imported_from": "geo-map.layer-registry.v1",
                    "source_configured": uri.startswith("s3://"),
                    "source_scheme": "s3" if uri.startswith("s3://") else "synthetic",
                    "bounds_source": "registry-v1-mercator",
                },
            }
        ],
        "not_interchangeable_with": "geo-map.layer-registry.v1",
    }


def _wgs84(x, y):
    longitude = (float(x) / HALF) * 180.0
    latitude = math.degrees(math.atan(math.sinh(float(y) / EARTH)))
    return longitude, latitude
