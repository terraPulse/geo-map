"""Import legacy ``setting.ini`` metadata without copying secrets or source URIs.

The historical file is JSON (despite the ``.ini`` suffix) and may also be a
flat INI document. Source paths, colors, masks, and credential-like keys are
dropped. A scheme such as ``s3`` is retained only as a label.
"""

from __future__ import annotations

import configparser
import json
from pathlib import Path

from .errors import RegistryError
from .mercator import WORLD_BOUNDS
from .paths import dataset_id_error
from .registry import Registry, registry_from_obj

def parse_legacy_text(text: str) -> dict:
    stripped = text.strip()
    if not stripped:
        raise RegistryError("legacy setting is empty")
    if stripped.startswith("{"):
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise RegistryError("legacy setting must be a JSON object")
        return payload
    parser = configparser.ConfigParser()
    parser.read_string(stripped)
    flat: dict = {}
    for section in parser.sections():
        for key, value in parser.items(section):
            flat[key] = _coerce_ini(value)
    if not flat:
        raise RegistryError("legacy setting has no keys")
    return flat


def dataset_from_legacy(dataset_id: str, text: str) -> dict:
    if dataset_id_error(dataset_id):
        raise RegistryError("legacy dataset id is invalid")
    raw = parse_legacy_text(text)
    scheme = _source_scheme(raw)
    stored = _stored_levels(raw)
    if not stored:
        raise RegistryError("legacy setting has no processed_levels")
    native = _optional_int(raw.get("min_dynamic_level"))
    if native is None:
        native = max(stored)
    view_min = _optional_int(raw.get("min_static_level"))
    if view_min is None:
        view_min = min(stored)
    view_min = min(int(view_min), min(stored))
    view_max = max(int(native), max(stored), int(view_min))
    merge = _optional_int(raw.get("tile_merge")) or 1
    if merge < 1:
        raise RegistryError("legacy tile_merge is invalid")
    version = raw.get("version", 2)
    try:
        version_num = float(version)
    except (TypeError, ValueError) as exc:
        raise RegistryError("legacy version is invalid") from exc
    title = raw.get("title") if isinstance(raw.get("title"), str) and raw.get("title") else dataset_id
    bounds = _bounds(raw)
    visible = raw.get("visible", True)
    if visible is False:
        access = {"visibility": "restricted", "read_roles": []}
    else:
        access = {"visibility": "public"}
    return {
        "id": dataset_id,
        "title": title[:200],
        "description": "Imported from legacy setting.ini. Source paths were not copied.",
        "backend": "png",
        "bounds": list(bounds),
        "crs": "EPSG:3857",
        "pyramid": {
            "layout": "legacy-v1" if version_num < 2 else "legacy-v2",
            "zooms": {
                "native": int(native),
                "stored": stored,
                "view_min": int(view_min),
                "view_max": int(view_max),
            },
            "block": {"merge": int(merge), "tile_pixels": 256, "pixels": int(merge) * 256},
            "nodata": {"rgba": [0, 0, 0, 0]},
        },
        "styles": [{"id": "default", "title": "Styled PNG", "kind": "styled-png"}],
        "revision": "legacy",
        "access": access,
        "assets": [],
        "quantitative": None,
        "legacy": {
            "version": version_num,
            "imported_from": "setting.ini",
            "source_configured": scheme is not None,
            "source_scheme": scheme,
            "bounds_source": "legacy" if _has_bounds(raw) else "assumed_web_mercator_world",
        },
    }


def import_legacy_tree(root: Path) -> Registry:
    base = Path(root).resolve()
    found: list[dict] = []

    def walk(directory: Path, depth: int) -> None:
        if depth > 6:
            return
        for child in sorted(directory.iterdir(), key=lambda item: item.name):
            if not child.is_dir() or child.is_symlink():
                continue
            if child.name.startswith(".") or child.name in {"tiles", "__pycache__"}:
                continue
            setting = child / "setting.ini"
            if setting.is_file() and not setting.is_symlink():
                dataset_id = child.relative_to(base).as_posix()
                found.append(dataset_from_legacy(dataset_id, setting.read_text(encoding="utf-8")))
                continue
            walk(child, depth + 1)

    walk(base, 0)
    if not found:
        raise RegistryError("no legacy setting.ini files were found")
    return registry_from_obj({"schema": "geo-map.dataset-registry/v0", "datasets": found})


def _source_scheme(raw: dict) -> str | None:
    file_value = raw.get("file")
    if not isinstance(file_value, str) or "://" not in file_value:
        return None
    scheme = file_value.split("://", 1)[0].lower()
    if not scheme or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789" for ch in scheme):
        return None
    return scheme


def _stored_levels(raw: dict) -> list[int]:
    value = raw.get("processed_levels")
    if value is None:
        return []
    if isinstance(value, str):
        pieces = value.replace(",", " ").split()
        return [int(piece) for piece in pieces]
    if isinstance(value, list):
        return [int(item) for item in value]
    raise RegistryError("legacy processed_levels is invalid")


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _has_bounds(raw: dict) -> bool:
    bounds = raw.get("bounds")
    return isinstance(bounds, list) and len(bounds) == 4


def _bounds(raw: dict) -> tuple[float, float, float, float]:
    if _has_bounds(raw):
        return tuple(float(item) for item in raw["bounds"])  # type: ignore[return-value]
    return WORLD_BOUNDS


def _coerce_ini(value: str):
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text
