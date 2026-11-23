# Provisional dataset registry contract (v0)

Schema id: `geo-map.dataset-registry/v0`

This document is the contract a sibling admin app can write against. The machine-readable copy is [dataset-registry.schema.json](dataset-registry.schema.json). The loader rejects unknown fields, so new admin fields need a schema bump rather than a silent extension.

The contract is provisional. Field names below are what this package loads and serves. It is not a promise that a later v0 revision will accept every extra key.

## Document

```json
{
  "schema": "geo-map.dataset-registry/v0",
  "datasets": []
}
```

Dataset ids may contain slashes (`lincoln/water_freq/y2025`). Each segment starts with a letter or digit and then uses letters, digits, `.`, `_`, or `-`. The id is a path under the data root, not a URL and not a filesystem escape.

## Dataset fields

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Slash-separated id. Unique in the file. |
| `title`, `description` | title yes | Display text. Descriptions are optional. |
| `backend` | yes | `png` for a styled pyramid, or `cog` for a numeric COG without requiring a pyramid. |
| `bounds` | yes | `[west, south, east, north]` in WGS84 degrees. No antimeridian wrap. Latitude must stay inside the Web Mercator domain. |
| `crs` | yes | `EPSG:3857` for a PNG pyramid. `EPSG:4326` is allowed for a COG-only dataset. |
| `pyramid` | yes for `png` | Stored block layout, zooms, and nodata. `null` when there is nothing to draw. |
| `styles` | yes for a pyramid | Names of styled PNG presentations. `kind` is only `styled-png`. Extra names share the same blocks; this increment does not recolor. |
| `revision` | yes | Opaque data revision copied into TileJSON `version`. |
| `access` | yes | `visibility` is `public` or `restricted`. Restricted datasets list `read_roles`. Public datasets must not list roles. |
| `assets` | no | Source-data or metadata links. Exactly one of `local` (relative path) or `href` (https, no userinfo). |
| `quantitative` | no | `grid` or `cog` numeric source. `null` means values are unavailable. |
| `legacy` | no | Redacted import note. No source URIs. |

`png` requires a pyramid, `EPSG:3857`, and at least one style. `cog` requires `quantitative.backend = "cog"`. A PNG dataset may also carry a quantitative source. WMS and TileJSON are advertised only when `pyramid` is present.

## Pyramid

```json
"pyramid": {
  "layout": "legacy-v2",
  "zooms": {"native": 12, "stored": [3, 6, 9], "view_min": 0, "view_max": 12},
  "block": {"merge": 8, "tile_pixels": 256, "pixels": 2048},
  "nodata": {"rgba": [0, 0, 0, 0]}
}
```

- `layout: legacy-v2` reads `{data_root}/{id}/tiles/{z}/{x}/{y}.png`.
- `layout: legacy-v1` reads `{data_root}/{id}/{z}/{x}/{y}.png`.
- `x` and `y` are the south-west tile of the block (the legacy TMS index), aligned to `merge`.
- `pixels` must equal `merge * 256`. The file is one RGBA PNG of that edge length, north at the top.
- `stored` lists the levels that exist on disk. View zooms outside that list are nearest-neighbor resamples of those blocks. The reader does not open the original raster.
- `native` is the source resolution zoom recorded for clients. It does not have to be one of `stored`.
- Every `stored` zoom must lie inside `view_min`..`view_max`.

Nodata pixels, and pixels outside `bounds`, are transparent in PNG responses.

## Access

The same rule is used by discovery, TileJSON, tiles, WMS, numeric reads, asset bytes, and MCP:

- `public`: anonymous read.
- `restricted`: the caller needs a bearer token whose roles intersect `read_roles`.
- Unknown datasets are `404`. Known datasets the caller cannot read are `403`. Lists omit them.
- Tokens are not stored in the registry. A host supplies `GEOMAP_INTERFACE_TOKENS` or passes a token map to `Runtime`. The JSON shape is `{"<token>": {"subject": "<name>", "roles": ["analyst"]}}`.

A legacy `visible: false` import becomes `restricted` with no roles, so it stays unread until an admin sets roles.

## Assets and quantitative data

Local asset bytes are served only for `source-data` or `metadata` assets whose media type is `application/json`, `application/geo+json`, or `text/plain`, and only from a path inside the dataset directory, under the byte budget. https `href` values are returned as links and are not fetched. Credential URLs are rejected at load.

`quantitative.backend = "grid"` reads `{path}` JSON plus a sibling `.f64` little-endian grid in EPSG:4326, north row first. `cog` reads a local GeoTIFF through optional `rasterio`. If `quantitative` is null, value and stats responses say `quantitative_backend_not_configured` and do not sample the PNG. If `rasterio` is not installed, a COG query returns `quantitative_dependency_missing` and no estimated number.

## Legacy `setting.ini` import

`geomap_interfaces.legacy.import_legacy_tree` walks a local directory for `setting.ini` (JSON, or a flat INI). Mapping:

| Legacy key | Registry |
| --- | --- |
| directory path | `id` |
| `title` | `title` |
| `version` | `pyramid.layout` (`legacy-v2` when version >= 2) and `legacy.version` |
| `processed_levels` | `zooms.stored` |
| `min_dynamic_level` | `zooms.native` (else max stored) |
| `min_static_level` | `zooms.view_min`, widened so every stored level is visible |
| `tile_merge` | `block.merge` and `block.pixels` |
| `visible: false` | `access.visibility = restricted` and no roles |
| `bounds` | copied when present; otherwise the Web Mercator world and `legacy.bounds_source = assumed_web_mercator_world` |
| `file` | not copied. `legacy.source_scheme` keeps only the URI scheme, such as `s3` |

Dropped keys include `file`, `color`, `mask`, `region`, `password`, `token`, `values_mapping`, and nested source paths. Import does not attach a quantitative backend, because the legacy file path may be remote or non-numeric.

## Public HTTP

| Method and path | Response |
| --- | --- |
| `GET /interfaces/datasets` | Readable datasets. |
| `GET /interfaces/datasets/{id}` | Public record, links, asset metadata. |
| `GET /interfaces/datasets/{id}/tilejson` | TileJSON 3.0.0, scheme `xyz`. |
| `GET /interfaces/datasets/{id}/tiles/{z}/{x}/{y}.png` | XYZ tile resampled from stored blocks. |
| `GET /interfaces/datasets/{id}/assets` | Asset metadata. |
| `GET /interfaces/datasets/{id}/assets/{asset}/content` | Allowlisted local text/JSON only. |
| `GET /interfaces/datasets/{id}/value?lon=&lat=` | Numeric point, or an explicit unavailable result. |
| `GET /interfaces/datasets/{id}/stats?west=&south=&east=&north=` | Numeric summary in EPSG:4326. |
| `GET /interfaces/wms` | WMS 1.3.0 GetCapabilities and GetMap. |

`{id}` may contain slashes. TileJSON `y` is XYZ (0 at the north). Stored files keep the legacy south-west index.

WMS 1.3.0 advertises `GetCapabilities` and `GetMap`, formats `text/xml` and `image/png`, and CRS `EPSG:3857` (easting, northing), `EPSG:4326` (latitude, longitude), and `CRS:84` (longitude, latitude). `GetMap` builds a mosaic of stored blocks and samples the requested pixel grid. Geographic requests are spaced evenly in latitude and longitude. The capabilities abstract states that this is not an OGC compliance certification.

## MCP

Tools, all read-only: `list_datasets`, `describe_dataset`, `dataset_links`, `dataset_value`, `dataset_stats`. They return JSON records and URLs. They do not accept a URL argument and they do not return image bytes. The server is built for one already-authenticated principal. `serverless_app` returns a stateless Streamable HTTP ASGI app and does not listen; the host enters `session_manager.run()`.
