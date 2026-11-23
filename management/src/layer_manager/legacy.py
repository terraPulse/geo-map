"""Import and export legacy setting.ini JSON and color.txt.

setting.ini is JSON in the current tile writer even though the suffix is
.ini. This module only transforms text the caller already has. It does not
open paths, and it does not write a tile repository.
"""

import re
from urllib.parse import urlparse

from .canonical import sha256_text
from .schema_contract import BACKEND_PNG, LEGACY_NAMESPACE, TILE_PIXEL_SIZE

_COLOR_WS = re.compile(r"^(\S+)\s+(\d+),(\d+),(\d+),(\d+)(?:\s+(.*))?$")


def parse_color_txt(text):
    if text is None:
        return []
    if not isinstance(text, str):
        raise TypeError("color_txt must be a string")
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("# QGIS"):
        lines = lines[2:]
    stops = []
    for raw_line in lines:
        raw = raw_line.strip()
        if not raw or raw.startswith("#"):
            continue
        match = _COLOR_WS.match(raw)
        if match:
            label = (match.group(6) or "").strip()
            stops.append(
                {
                    "value": float(match.group(1)),
                    "rgba": [int(match.group(i)) for i in range(2, 6)],
                    "label": label[:80],
                }
            )
            continue
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) < 5:
            continue
        label = parts[5] if len(parts) > 5 else ""
        stops.append(
            {
                "value": float(parts[0]),
                "rgba": [int(parts[i]) for i in range(1, 5)],
                "label": label[:80],
            }
        )
    return stops


def format_color_txt(stops):
    lines = [
        "# exported by geo-map layer registry",
        "# registry export does not write this file into the tile repository",
    ]
    for stop in stops or []:
        rgba = ",".join(str(int(channel)) for channel in stop["rgba"])
        lines.append(f"{stop['value']} {rgba}")
        label = stop.get("label") or ""
        if label:
            lines.append(f"# stop {stop['value']} {label}")
    return "\n".join(lines) + "\n"


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def legacy_to_client_layer(tag, setting, color_txt="", recorded_at=None):
    """Map one legacy setting object into a client layer plus legacy_compat."""
    if not isinstance(setting, dict):
        raise TypeError("setting must be a JSON object")
    if not isinstance(tag, str):
        raise TypeError("tag must be a string")
    stops = parse_color_txt(color_txt or "")
    levels = setting.get("processed_levels") or []
    if not isinstance(levels, list):
        levels = []
    version = _number(setting.get("version")) or 2.0
    layout = "version-1-root" if version < 2 else "version-2-tiles"
    sources = []
    file_uri = setting.get("file")
    if isinstance(file_uri, str) and file_uri and recorded_at:
        sources.append(
            {
                "revision_id": "legacy-file",
                "uri": file_uri,
                "note": "Imported from legacy setting.ini file field. Not fetched.",
                "recorded_at": recorded_at,
            }
        )
    origin = setting.get("origin")
    if isinstance(origin, str) and origin and recorded_at:
        sources.append(
            {
                "revision_id": "legacy-origin",
                "uri": origin if "://" in origin else f"synthetic://legacy-origin/{tag}",
                "note": f"Legacy origin reference: {origin}",
                "recorded_at": recorded_at,
            }
        )
    title = setting.get("title")
    if not isinstance(title, str) or not title.strip():
        title = tag
    layer = {
        "tag": tag,
        "title": title,
        "backend": BACKEND_PNG,
        "pyramid": {
            "layout": layout,
            "tile_pixel_size": TILE_PIXEL_SIZE,
            "tile_merge": int(setting["tile_merge"]) if isinstance(setting.get("tile_merge"), int) else 1,
            "min_static_level": setting.get("min_static_level"),
            "min_dynamic_level": setting.get("min_dynamic_level"),
            "processed_levels": [int(level) for level in levels if isinstance(level, int)],
            "version": version,
            "aggregate": setting.get("agg") if setting.get("agg") in {"mean", "median", "dominated"} else "median",
            "persistent": True,
        },
        "cog": None,
        "bounds": None,
        "style": {"type": "color-ramp", "stops": stops},
        "nodata": {
            "min_value": _number(setting.get("min_value")),
            "max_value": _number(setting.get("max_value")),
            "fill_nodata": _number(setting.get("fill_nodata")),
            "raster_nodata": _number(setting.get("nodata")),
        },
        "source_revisions": sources,
        "authorized_tile_template": None,
    }
    compat = {
        "namespace": LEGACY_NAMESPACE,
        "setting": setting,
        "color_txt_sha256": sha256_text(color_txt) if color_txt else None,
    }
    return layer, compat


def export_legacy(record):
    """Return setting JSON and color.txt text. Nothing is written."""
    compat = record.get("legacy_compat") or {}
    setting = dict(compat.get("setting") or {})
    if setting.get("namespace") == LEGACY_NAMESPACE:
        setting.pop("namespace", None)
    setting["title"] = record["title"]
    pyramid = record.get("pyramid") or {}
    if pyramid:
        setting["version"] = pyramid.get("version", 2.0)
        setting["tile_merge"] = pyramid.get("tile_merge", 1)
        setting["min_static_level"] = pyramid.get("min_static_level")
        setting["min_dynamic_level"] = pyramid.get("min_dynamic_level")
        setting["processed_levels"] = list(pyramid.get("processed_levels") or [])
        setting["agg"] = pyramid.get("aggregate", "median")
        setting["visible"] = setting.get("visible", True)
    nodata = record.get("nodata") or {}
    for source_name, legacy_name in (
        ("min_value", "min_value"),
        ("max_value", "max_value"),
        ("fill_nodata", "fill_nodata"),
    ):
        if nodata.get(source_name) is not None:
            setting[legacy_name] = nodata[source_name]
    warnings = [
        "Export returns text only. It does not write setting.ini or color.txt and does not regenerate PNGs."
    ]
    file_uri = setting.get("file")
    if isinstance(file_uri, str) and file_uri:
        parsed = urlparse(file_uri)
        if parsed.scheme == "synthetic":
            warnings.append("The stored file reference is synthetic and is not a tile-server path.")
    color_txt = format_color_txt((record.get("style") or {}).get("stops") or [])
    return {
        "namespace": LEGACY_NAMESPACE,
        "schema": record["schema"],
        "tag": record["tag"],
        "written": False,
        "setting": setting,
        "color_txt": color_txt,
        "warnings": warnings,
    }
