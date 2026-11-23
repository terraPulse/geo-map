"""Discovery, TileJSON, and asset records that do not embed raster bytes."""

from __future__ import annotations

from .errors import InterfaceError
from .paths import safe_join
from .registry import Asset, Dataset


def list_records(runtime, principal) -> dict:
    from .auth import can_read

    rows = [summary(item) for item in runtime.registry.datasets if can_read(item.access, principal)]
    return {"datasets": rows}


def detail_record(runtime, dataset: Dataset) -> dict:
    from .registry import public_dataset

    record = public_dataset(dataset)
    record["links"] = links(runtime, dataset)
    record["assets"] = [asset_record(runtime, dataset, asset) for asset in dataset.assets]
    return record


def summary(dataset: Dataset) -> dict:
    return {
        "id": dataset.id,
        "title": dataset.title,
        "backend": dataset.backend,
        "bounds": list(dataset.bounds),
        "crs": dataset.crs,
        "revision": dataset.revision,
        "styled_png": dataset.pyramid is not None,
        "quantitative": dataset.quantitative is not None,
    }


def links(runtime, dataset: Dataset) -> dict:
    root = _root(runtime, dataset.id)
    payload = {
        "self": root,
        "wms": _join(runtime, "/interfaces/wms"),
        "value": root + "/value",
        "stats": root + "/stats",
        "assets": root + "/assets",
    }
    if dataset.pyramid is not None:
        payload["tilejson"] = root + "/tilejson"
        payload["tiles"] = root + "/tiles/{z}/{x}/{y}.png"
    return payload


def tilejson(runtime, dataset: Dataset) -> dict:
    if dataset.pyramid is None:
        raise InterfaceError("styled_pyramid_not_configured", "dataset has no styled PNG pyramid", 409)
    west, south, east, north = dataset.bounds
    zooms = dataset.pyramid.zooms
    return {
        "tilejson": "3.0.0",
        "name": dataset.id,
        "description": dataset.description or dataset.title,
        "version": dataset.revision,
        "scheme": "xyz",
        "tiles": [links(runtime, dataset)["tiles"]],
        "minzoom": zooms.view_min,
        "maxzoom": zooms.view_max,
        "bounds": [west, south, east, north],
        "center": [(west + east) / 2.0, (south + north) / 2.0, zooms.native],
        "attribution": dataset.title,
        "geomap:nativezoom": zooms.native,
        "geomap:stored_zooms": list(zooms.stored),
        "geomap:block_pixels": dataset.pyramid.block.pixels,
        "geomap:revision": dataset.revision,
        "geomap:note": "Tiles are nearest-neighbor resamples of stored styled PNG blocks, not quantitative values.",
    }


def asset_record(runtime, dataset: Dataset, asset: Asset) -> dict:
    link = _root(runtime, dataset.id) + "/assets/" + asset.id
    record = {
        "id": asset.id,
        "role": asset.role,
        "title": asset.title,
        "media_type": asset.media_type,
        "retrieval": "local-content" if asset.downloadable else "metadata-only",
        "link": link,
    }
    if asset.href:
        record["href"] = asset.href
    if asset.downloadable:
        record["content_link"] = link + "/content"
    return record


def asset_bytes(runtime, dataset: Dataset, asset: Asset) -> tuple[str, bytes]:
    if not asset.downloadable or asset.local is None:
        raise InterfaceError(
            "remote_asset_not_fetched",
            "This asset is metadata only. The server does not fetch remote or styled raster bytes.",
            400,
        )
    directory = safe_join(runtime.data_root, dataset.id)
    path = safe_join(directory, asset.local)
    if not path.is_file():
        raise InterfaceError("not_found", "asset content is not available", 404)
    size = path.stat().st_size
    if size > runtime.budgets.max_asset_bytes:
        raise InterfaceError("budget_exceeded", "asset exceeds the byte budget", 400)
    return asset.media_type, path.read_bytes()


def _root(runtime, dataset_id: str) -> str:
    return _join(runtime, "/interfaces/datasets/" + dataset_id)


def _join(runtime, path: str) -> str:
    base = runtime.public_base.rstrip("/")
    return base + path
