# Integration boundaries

This note is for people changing the tile renderer. It records which URL and storage contracts stay here, and which trees belong to other work.

Reviewed repository revision at the start of this change: `master` `6bf43ab1c2f22c6da8e50ef423bd1afb86b18bd3`.

## What this repository serves

The Flask service in `serv/` accepts the historical tile orders and the `/_…` operations:

- `/map/{tag}/{z}/{x}/{y}.png` and `/zx_y/…` use the `zx_y` index math
- `/zxy/…` flips the row with the existing normalizer, including the long-standing row-`0` result
- `/xyz/{tag}/{x}/{y}/{z}.png` reads the level from the last component
- `_` or `-` before an index still counts from the far edge in each parser

`lambda/handler.py` keeps its own normalizer. In particular `_0` is the last index there, and it is index `0` in `map_tile_parse`. Those two parsers were not unified.

Layer metadata remains `{map_path}/{tag}/setting.ini`. Version 2 PNGs remain `{map_path}/{tag}/tiles/{z}/{x}/{y}.png`. Older layers omit `tiles/`.

## PNG blocks

Layers that set `processed_levels` are block layers. Those levels are the pregenerated PNGs (including large `tile_merge` blocks). A view request for any other level is resampled from the nearest stored PNG. A missing PNG on that view path becomes a transparent tile. It does not open the source raster.

`build_tiles_task.py` still passes `building_tiles=True`, so pregeneration can rasterize from the source. Layers without `processed_levels` still render on demand above `min_dynamic_level`.

`GEOMAP_VIEW_SOURCE_RENDER=1` turns the block-layer miss path back into source rendering. `GEOMAP_TILE_CACHE_BYTES=0` turns off the in-process PNG cache. Neither variable calls AWS.

The cache is per process, TTL-bounded, and single-flight per object key. It does not create a boto3 client. Object storage connections stay inside `gio`.

## Production front ends are outside this tree

Operators have described three public fronts: `/maptiles` handled by Node `load-tiles`, a legacy Python 3.8 renderer, and `map-tiles-dev` on Python 3.14. This repository does not contain those deployments. `lambda/handler.py` must not be assumed to be the code those fronts run. A deploy of this handler has to include `util/lib/tile_runtime.py` (the handler adds `util/lib` to `sys.path` when the module is not already imported).

No live AWS configuration was read or changed for this work.

## Reserved for other branches

Do not add these trees in renderer fixes:

- `management/` and `infra/layer-manager/` — authenticated serverless layer admin
- `interfaces/` — additive WMS, TileJSON, MCP, and data API

Those surfaces should call the tile orders above, or read the same `setting.ini` and PNG keys, instead of growing a second renderer.
