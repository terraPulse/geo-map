"""Declarative dataset registry, schema ``geo-map.dataset-registry/v0``.

Unknown fields are rejected so a sibling admin app cannot silently invent
contract fields. Local paths and remote credentials are not part of the
public record produced by :func:`public_dataset`.
"""

from __future__ import annotations

import json
import math
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from . import SCHEMA_ID
from .budgets import Budgets
from .errors import RegistryError
from .mercator import MAX_LAT
from .paths import dataset_id_error

_SEGMENT = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-")
_MEDIA_TYPES = {
    "application/json",
    "application/geo+json",
    "text/plain",
    "image/png",
    "image/tiff",
}
_DOWNLOAD_MEDIA = {"application/json", "application/geo+json", "text/plain"}
_ASSET_ROLES = {"source-data", "metadata", "style"}
_ROLE_NAME = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


@dataclass(frozen=True)
class Nodata:
    rgba: tuple[int, int, int, int]


@dataclass(frozen=True)
class Block:
    merge: int
    tile_pixels: int

    @property
    def pixels(self) -> int:
        return self.merge * self.tile_pixels


@dataclass(frozen=True)
class Zooms:
    native: int
    stored: tuple[int, ...]
    view_min: int
    view_max: int


@dataclass(frozen=True)
class Pyramid:
    layout: str
    zooms: Zooms
    block: Block
    nodata: Nodata


@dataclass(frozen=True)
class Style:
    id: str
    title: str
    kind: str


@dataclass(frozen=True)
class Access:
    visibility: str
    read_roles: tuple[str, ...]


@dataclass(frozen=True)
class Asset:
    id: str
    role: str
    title: str
    media_type: str
    local: str | None
    href: str | None

    @property
    def downloadable(self) -> bool:
        return self.local is not None and self.role in {"source-data", "metadata"} and self.media_type in _DOWNLOAD_MEDIA


@dataclass(frozen=True)
class Quantitative:
    backend: str
    path: str
    band: int
    nodata: float | None


@dataclass(frozen=True)
class Legacy:
    version: float | None
    imported_from: str | None
    source_configured: bool
    source_scheme: str | None
    bounds_source: str


@dataclass(frozen=True)
class Dataset:
    id: str
    title: str
    description: str
    backend: str
    bounds: tuple[float, float, float, float]
    crs: str
    pyramid: Pyramid | None
    styles: tuple[Style, ...]
    revision: str
    access: Access
    assets: tuple[Asset, ...]
    quantitative: Quantitative | None
    legacy: Legacy | None


@dataclass(frozen=True)
class Registry:
    schema: str
    datasets: tuple[Dataset, ...]

    def get(self, dataset_id: str) -> Dataset | None:
        for dataset in self.datasets:
            if dataset.id == dataset_id:
                return dataset
        return None


def load_registry(path: Path, budgets: Budgets | None = None) -> Registry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return registry_from_obj(payload, budgets=budgets)


def registry_from_obj(payload: object, budgets: Budgets | None = None) -> Registry:
    limits = budgets or Budgets()
    limits.check()
    obj = _object(payload, "registry")
    _unknown(obj, {"schema", "datasets"}, "registry")
    if obj.get("schema") != SCHEMA_ID:
        raise RegistryError(f"schema must be {SCHEMA_ID}")
    rows = obj.get("datasets")
    if not isinstance(rows, list) or not rows:
        raise RegistryError("datasets must be a non-empty list")
    datasets = tuple(_dataset(row, index, limits) for index, row in enumerate(rows))
    ids = [item.id for item in datasets]
    if len(ids) != len(set(ids)):
        raise RegistryError("dataset ids must be unique")
    return Registry(schema=SCHEMA_ID, datasets=datasets)


def registry_to_obj(registry: Registry) -> dict:
    return {"schema": registry.schema, "datasets": [_dataset_obj(item) for item in registry.datasets]}


def _dataset(value: object, index: int, budgets: Budgets) -> Dataset:
    ctx = f"datasets[{index}]"
    obj = _object(value, ctx)
    _unknown(
        obj,
        {
            "id",
            "title",
            "description",
            "backend",
            "bounds",
            "crs",
            "pyramid",
            "styles",
            "revision",
            "access",
            "assets",
            "quantitative",
            "legacy",
        },
        ctx,
    )
    dataset_id = _require(obj, "id", ctx)
    if dataset_id_error(dataset_id):
        raise RegistryError(f"{ctx}.id is not a valid dataset id")
    title = _text(_require(obj, "title", ctx), f"{ctx}.title", 200)
    description = _text(obj.get("description", ""), f"{ctx}.description", 2000)
    backend = _require(obj, "backend", ctx)
    if backend not in {"png", "cog"}:
        raise RegistryError(f"{ctx}.backend must be png or cog")
    bounds = _bounds(_require(obj, "bounds", ctx), f"{ctx}.bounds")
    crs = _require(obj, "crs", ctx)
    if crs not in {"EPSG:3857", "EPSG:4326"}:
        raise RegistryError(f"{ctx}.crs must be EPSG:3857 or EPSG:4326")
    pyramid = None if obj.get("pyramid") is None else _pyramid(obj.get("pyramid"), f"{ctx}.pyramid", budgets)
    styles = _styles(obj.get("styles", []), f"{ctx}.styles")
    revision = _revision(_require(obj, "revision", ctx), f"{ctx}.revision")
    access = _access(_require(obj, "access", ctx), f"{ctx}.access")
    assets = _assets(obj.get("assets", []), f"{ctx}.assets")
    quantitative = None if obj.get("quantitative") in (None, {}) else _quantitative(obj.get("quantitative"), f"{ctx}.quantitative")
    legacy = None if obj.get("legacy") is None else _legacy(obj.get("legacy"), f"{ctx}.legacy")
    if backend == "png":
        if pyramid is None:
            raise RegistryError(f"{ctx} png backend requires a pyramid")
        if crs != "EPSG:3857":
            raise RegistryError(f"{ctx} png pyramid crs must be EPSG:3857")
        if not styles:
            raise RegistryError(f"{ctx} png backend requires at least one style")
    if backend == "cog":
        if quantitative is None or quantitative.backend != "cog":
            raise RegistryError(f"{ctx} cog backend requires quantitative.backend cog")
    if pyramid is not None and not styles:
        raise RegistryError(f"{ctx} a styled pyramid requires at least one style")
    asset_ids = [item.id for item in assets]
    if len(asset_ids) != len(set(asset_ids)):
        raise RegistryError(f"{ctx}.assets ids must be unique")
    style_ids = [item.id for item in styles]
    if len(style_ids) != len(set(style_ids)):
        raise RegistryError(f"{ctx}.styles ids must be unique")
    return Dataset(
        id=dataset_id,
        title=title,
        description=description,
        backend=backend,
        bounds=bounds,
        crs=crs,
        pyramid=pyramid,
        styles=styles,
        revision=revision,
        access=access,
        assets=assets,
        quantitative=quantitative,
        legacy=legacy,
    )


def _pyramid(value: object, ctx: str, budgets: Budgets) -> Pyramid:
    obj = _object(value, ctx)
    _unknown(obj, {"layout", "zooms", "block", "nodata"}, ctx)
    layout = obj.get("layout")
    if layout not in {"legacy-v2", "legacy-v1"}:
        raise RegistryError(f"{ctx}.layout must be legacy-v2 or legacy-v1")
    zooms = _zooms(_require(obj, "zooms", ctx), f"{ctx}.zooms", budgets)
    block = _block(_require(obj, "block", ctx), f"{ctx}.block")
    nodata = _nodata(obj.get("nodata", {"rgba": [0, 0, 0, 0]}), f"{ctx}.nodata")
    return Pyramid(layout=layout, zooms=zooms, block=block, nodata=nodata)


def _zooms(value: object, ctx: str, budgets: Budgets) -> Zooms:
    obj = _object(value, ctx)
    _unknown(obj, {"native", "stored", "view_min", "view_max"}, ctx)
    native = _zoom(_require(obj, "native", ctx), f"{ctx}.native", budgets.max_zoom)
    stored_raw = _require(obj, "stored", ctx)
    if not isinstance(stored_raw, list) or not stored_raw:
        raise RegistryError(f"{ctx}.stored must be a non-empty list")
    stored = tuple(_zoom(item, f"{ctx}.stored", budgets.max_zoom) for item in stored_raw)
    if len(stored) != len(set(stored)):
        raise RegistryError(f"{ctx}.stored contains duplicates")
    view_min = _zoom(_require(obj, "view_min", ctx), f"{ctx}.view_min", budgets.max_zoom)
    view_max = _zoom(_require(obj, "view_max", ctx), f"{ctx}.view_max", budgets.max_zoom)
    if view_min > view_max:
        raise RegistryError(f"{ctx}.view_min cannot exceed view_max")
    if any(level < view_min or level > view_max for level in stored):
        raise RegistryError(f"{ctx}.stored levels must lie inside the view range")
    return Zooms(native=native, stored=tuple(sorted(stored)), view_min=view_min, view_max=view_max)


def _block(value: object, ctx: str) -> Block:
    obj = _object(value, ctx)
    _unknown(obj, {"merge", "tile_pixels", "pixels"}, ctx)
    merge = obj.get("merge")
    tile_pixels = obj.get("tile_pixels")
    if not isinstance(merge, int) or isinstance(merge, bool) or merge < 1 or merge > 64:
        raise RegistryError(f"{ctx}.merge must be an integer from 1 to 64")
    if tile_pixels != 256:
        raise RegistryError(f"{ctx}.tile_pixels must be 256")
    pixels = merge * tile_pixels
    if "pixels" in obj and obj["pixels"] != pixels:
        raise RegistryError(f"{ctx}.pixels must equal merge * tile_pixels")
    return Block(merge=merge, tile_pixels=tile_pixels)


def _nodata(value: object, ctx: str) -> Nodata:
    obj = _object(value, ctx)
    _unknown(obj, {"rgba"}, ctx)
    rgba = obj.get("rgba")
    if not isinstance(rgba, list) or len(rgba) != 4 or any(not _byte(item) for item in rgba):
        raise RegistryError(f"{ctx}.rgba must be four integers from 0 to 255")
    return Nodata(rgba=(int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3])))


def _styles(value: object, ctx: str) -> tuple[Style, ...]:
    if not isinstance(value, list):
        raise RegistryError(f"{ctx} must be a list")
    styles = []
    for index, item in enumerate(value):
        obj = _object(item, f"{ctx}[{index}]")
        _unknown(obj, {"id", "title", "kind"}, f"{ctx}[{index}]")
        kind = obj.get("kind")
        if kind != "styled-png":
            raise RegistryError(f"{ctx}[{index}].kind must be styled-png")
        styles.append(
            Style(
                id=_token(_require(obj, "id", f"{ctx}[{index}]"), f"{ctx}[{index}].id"),
                title=_text(_require(obj, "title", f"{ctx}[{index}]"), f"{ctx}[{index}].title", 200),
                kind="styled-png",
            )
        )
    return tuple(styles)


def _access(value: object, ctx: str) -> Access:
    obj = _object(value, ctx)
    _unknown(obj, {"visibility", "read_roles"}, ctx)
    visibility = obj.get("visibility")
    if visibility not in {"public", "restricted"}:
        raise RegistryError(f"{ctx}.visibility must be public or restricted")
    roles_raw = obj.get("read_roles", [])
    if not isinstance(roles_raw, list):
        raise RegistryError(f"{ctx}.read_roles must be a list")
    roles = tuple(_role(item, f"{ctx}.read_roles") for item in roles_raw)
    if len(roles) != len(set(roles)):
        raise RegistryError(f"{ctx}.read_roles contains duplicates")
    if visibility == "public" and roles:
        raise RegistryError(f"{ctx} public datasets cannot list read_roles")
    return Access(visibility=visibility, read_roles=roles)


def _assets(value: object, ctx: str) -> tuple[Asset, ...]:
    if not isinstance(value, list):
        raise RegistryError(f"{ctx} must be a list")
    assets = []
    for index, item in enumerate(value):
        place = f"{ctx}[{index}]"
        obj = _object(item, place)
        _unknown(obj, {"id", "role", "title", "media_type", "local", "href"}, place)
        local = obj.get("local")
        href = obj.get("href")
        if (local is None) == (href is None):
            raise RegistryError(f"{place} must set exactly one of local or href")
        if local is not None:
            local = _relative_path(local, f"{place}.local")
        if href is not None:
            href = _href(href, f"{place}.href")
        role = obj.get("role")
        if role not in _ASSET_ROLES:
            raise RegistryError(f"{place}.role is not supported")
        media = obj.get("media_type")
        if media not in _MEDIA_TYPES:
            raise RegistryError(f"{place}.media_type is not supported")
        assets.append(
            Asset(
                id=_token(_require(obj, "id", place), f"{place}.id"),
                role=role,
                title=_text(_require(obj, "title", place), f"{place}.title", 200),
                media_type=media,
                local=local,
                href=href,
            )
        )
    return tuple(assets)


def _quantitative(value: object, ctx: str) -> Quantitative:
    obj = _object(value, ctx)
    _unknown(obj, {"backend", "path", "band", "nodata"}, ctx)
    backend = obj.get("backend")
    if backend not in {"grid", "cog"}:
        raise RegistryError(f"{ctx}.backend must be grid or cog")
    path = _relative_path(_require(obj, "path", ctx), f"{ctx}.path")
    band = obj.get("band", 1)
    if not isinstance(band, int) or isinstance(band, bool) or band < 1 or band > 64:
        raise RegistryError(f"{ctx}.band must be an integer from 1 to 64")
    nodata = obj.get("nodata")
    if nodata is not None and not _finite_number(nodata):
        raise RegistryError(f"{ctx}.nodata must be a finite number or null")
    return Quantitative(backend=backend, path=path, band=band, nodata=None if nodata is None else float(nodata))


def _legacy(value: object, ctx: str) -> Legacy:
    obj = _object(value, ctx)
    _unknown(obj, {"version", "imported_from", "source_configured", "source_scheme", "bounds_source"}, ctx)
    version = obj.get("version")
    if version is not None and not _finite_number(version):
        raise RegistryError(f"{ctx}.version must be a number or null")
    imported = obj.get("imported_from")
    if imported is not None:
        imported = _text(imported, f"{ctx}.imported_from", 80)
    scheme = obj.get("source_scheme")
    if scheme is not None:
        scheme = _text(scheme, f"{ctx}.source_scheme", 32)
        if any(ch not in set("abcdefghijklmnopqrstuvwxyz0123456789") for ch in scheme):
            raise RegistryError(f"{ctx}.source_scheme has a disallowed character")
    if not isinstance(obj.get("source_configured"), bool):
        raise RegistryError(f"{ctx}.source_configured must be a boolean")
    bounds_source = _text(_require(obj, "bounds_source", ctx), f"{ctx}.bounds_source", 80)
    return Legacy(
        version=None if version is None else float(version),
        imported_from=imported,
        source_configured=obj["source_configured"],
        source_scheme=scheme,
        bounds_source=bounds_source,
    )


def _dataset_obj(dataset: Dataset) -> dict:
    payload = {
        "id": dataset.id,
        "title": dataset.title,
        "description": dataset.description,
        "backend": dataset.backend,
        "bounds": list(dataset.bounds),
        "crs": dataset.crs,
        "pyramid": None if dataset.pyramid is None else _pyramid_obj(dataset.pyramid),
        "styles": [{"id": item.id, "title": item.title, "kind": item.kind} for item in dataset.styles],
        "revision": dataset.revision,
        "access": {"visibility": dataset.access.visibility, "read_roles": list(dataset.access.read_roles)},
        "assets": [
            {
                "id": item.id,
                "role": item.role,
                "title": item.title,
                "media_type": item.media_type,
                **({"local": item.local} if item.local else {"href": item.href}),
            }
            for item in dataset.assets
        ],
        "quantitative": None
        if dataset.quantitative is None
        else {
            "backend": dataset.quantitative.backend,
            "path": dataset.quantitative.path,
            "band": dataset.quantitative.band,
            "nodata": dataset.quantitative.nodata,
        },
    }
    if dataset.legacy is not None:
        payload["legacy"] = {
            "version": dataset.legacy.version,
            "imported_from": dataset.legacy.imported_from,
            "source_configured": dataset.legacy.source_configured,
            "source_scheme": dataset.legacy.source_scheme,
            "bounds_source": dataset.legacy.bounds_source,
        }
    return payload


def _pyramid_obj(pyramid: Pyramid) -> dict:
    return {
        "layout": pyramid.layout,
        "zooms": {
            "native": pyramid.zooms.native,
            "stored": list(pyramid.zooms.stored),
            "view_min": pyramid.zooms.view_min,
            "view_max": pyramid.zooms.view_max,
        },
        "block": {"merge": pyramid.block.merge, "tile_pixels": pyramid.block.tile_pixels, "pixels": pyramid.block.pixels},
        "nodata": {"rgba": list(pyramid.nodata.rgba)},
    }


def public_dataset(dataset: Dataset) -> dict:
    """Client-facing record. Omits filesystem paths and role grants."""

    record = {
        "id": dataset.id,
        "title": dataset.title,
        "description": dataset.description,
        "backend": dataset.backend,
        "bounds": list(dataset.bounds),
        "crs": dataset.crs,
        "revision": dataset.revision,
        "styled_png": dataset.pyramid is not None,
        "styles": [{"id": item.id, "title": item.title, "kind": item.kind} for item in dataset.styles],
        "quantitative": {
            "configured": dataset.quantitative is not None,
            "backend": None if dataset.quantitative is None else dataset.quantitative.backend,
        },
        "access": {"visibility": dataset.access.visibility},
        "pyramid": None
        if dataset.pyramid is None
        else {
            "layout": dataset.pyramid.layout,
            "native_zoom": dataset.pyramid.zooms.native,
            "stored_zooms": list(dataset.pyramid.zooms.stored),
            "view_min": dataset.pyramid.zooms.view_min,
            "view_max": dataset.pyramid.zooms.view_max,
            "block_merge": dataset.pyramid.block.merge,
            "block_pixels": dataset.pyramid.block.pixels,
            "tile_pixels": dataset.pyramid.block.tile_pixels,
            "nodata": list(dataset.pyramid.nodata.rgba),
        },
    }
    if dataset.legacy is not None:
        record["legacy"] = {
            "version": dataset.legacy.version,
            "imported_from": dataset.legacy.imported_from,
            "source_configured": dataset.legacy.source_configured,
            "source_scheme": dataset.legacy.source_scheme,
            "bounds_source": dataset.legacy.bounds_source,
        }
    return record


def _object(value: object, ctx: str) -> dict:
    if not isinstance(value, dict):
        raise RegistryError(f"{ctx} must be an object")
    return value


def _unknown(obj: dict, allowed: set[str], ctx: str) -> None:
    extra = sorted(set(obj) - allowed)
    if extra:
        raise RegistryError(f"{ctx} has unknown fields: {', '.join(extra)}")


def _require(obj: dict, key: str, ctx: str):
    if key not in obj:
        raise RegistryError(f"{ctx}.{key} is required")
    return obj[key]


def _text(value: object, ctx: str, limit: int) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise RegistryError(f"{ctx} must be a string of at most {limit} characters")
    return value


def _token(value: object, ctx: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise RegistryError(f"{ctx} must be a short token")
    if value[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789":
        raise RegistryError(f"{ctx} has an invalid token")
    if any(ch not in _SEGMENT for ch in value):
        raise RegistryError(f"{ctx} has an invalid token")
    return value


def _role(value: object, ctx: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 32 or value[0] not in "abcdefghijklmnopqrstuvwxyz":
        raise RegistryError(f"{ctx} has an invalid role")
    if any(ch not in _ROLE_NAME for ch in value):
        raise RegistryError(f"{ctx} has an invalid role")
    return value


def _revision(value: object, ctx: str) -> str:
    text = _text(value, ctx, 64)
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-")
    if not text or any(ch not in allowed for ch in text):
        raise RegistryError(f"{ctx} has an invalid revision")
    return text


def _zoom(value: object, ctx: str, max_zoom: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > max_zoom:
        raise RegistryError(f"{ctx} must be an integer zoom from 0 to {max_zoom}")
    return value


def _bounds(value: object, ctx: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4 or any(not _finite_number(item) for item in value):
        raise RegistryError(f"{ctx} must be west, south, east, north")
    west, south, east, north = (float(item) for item in value)
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise RegistryError(f"{ctx} is outside longitude/latitude limits")
    if south < -MAX_LAT - 1e-9 or north > MAX_LAT + 1e-9:
        raise RegistryError(f"{ctx} latitude exceeds the Web Mercator domain")
    return west, south, east, north


def _relative_path(value: object, ctx: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 240 or value.startswith(("/", "\\")) or "\\" in value:
        raise RegistryError(f"{ctx} must be a relative path")
    parts = Path(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RegistryError(f"{ctx} escapes its directory")
    for part in parts:
        if any(ch not in _SEGMENT for ch in part):
            raise RegistryError(f"{ctx} has a disallowed character")
    return value


def _href(value: object, ctx: str) -> str:
    if not isinstance(value, str) or len(value) > 500:
        raise RegistryError(f"{ctx} is not a usable link")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise RegistryError(f"{ctx} must be an https link without credentials")
    return value


def _byte(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))
