# Dataset schema contract

Schema id: `geo-map.layer-registry.v1`

File: `management/contracts/layer-registry-v1.schema.json`

This file is not under `interfaces/`. The parent integrates it into the sibling standards branch before any shared client depends on it. This branch does not create or edit `interfaces/`.

The legacy tile writer stores a different document: JSON in `{map_path}/{tag}/setting.ini`, plus `color.txt`. That namespace is `geo-map.legacy-setting-ini`. Import copies it into `legacy_compat` and does not treat the ini document as the registry schema. Export rebuilds an ini object for an operator to apply by hand. Unknown legacy keys such as `burn_band` are preserved. Nothing is written back to the tile repository.

Tags may contain slashes. `demo/water_freq/y2025` is one layer id. `..`, empty segments, and a leading or trailing slash are rejected.

`registry_effects.png_pyramid_regenerated_on_write` is fixed to `false`. A client cannot store `true`.

Staging also rejects payload text that mentions `geo-map-tiles` or `admin.terrapulse.com`, so a live setting.ini that points at the production tile bucket cannot be imported in this increment.

## Gap with interfaces v0

`interfaces/` on `cursor/interfaces-standards-8f3e` (`6068bd3`) publishes `geo-map.dataset-registry/v0` (`interfaces/docs/dataset-registry.schema.json`). This registry publishes `geo-map.layer-registry.v1`. They are not interchangeable, and this branch does not edit `interfaces/`.

| | Registry v1, this branch | Interfaces v0 |
| --- | --- | --- |
| Document | One layer record | `{schema, datasets[]}` |
| Identity | `tag` | `id` |
| Backend | `png-pyramid` or `cog` | `png` or `cog` |
| Bounds | Object `minx,miny,maxx,maxy` plus `crs` | Four-number WGS84 array, `crs` separate |
| Pyramid | `processed_levels`, `tile_merge`, layout `version-2-tiles` or `version-1-root` | `zooms.native/stored/view_min/view_max`, `block.merge`, layout `legacy-v2` or `legacy-v1` |
| Style | Color-ramp stops with RGBA | `styles[]` of `{id,title,kind: styled-png}` |
| Nodata | Numeric min, max, fill, raster | RGBA tuple |
| Revision | Integer, optimistic | String |
| Lifecycle | `draft` or `published`, audit, synthetic flag | `access.visibility`, no draft workflow |

A later integration has to map these fields explicitly. Deploying this stack does not make the interfaces package read the DynamoDB registry.
