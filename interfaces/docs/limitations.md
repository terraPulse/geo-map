# Limitations and deployment prerequisites

This increment is an additive library and test suite. It does not deploy, merge, or call AWS.

## Preserved on purpose

- Legacy URLs such as `/map/{id}/{z}/{x}/{y}.png` stay on the existing server. This package does not register them.
- The PNG pyramid is still the styled backend. Viewing zooms resample stored blocks. Missing blocks become nodata; they are not rendered from the original raster.
- `util/`, `serv/`, and `lambda/` are unchanged so sibling renderer and admin work does not collide with this branch.

## Not implemented

- OGC compliance certification, WMS 1.1.1, `GetFeatureInfo`, `GetLegendGraphic`, WFS, WMTS, WCS, and SLD.
- Antimeridian-wrapping bboxes, time dimensions, and CRS values other than EPSG:3857, EPSG:4326, and CRS:84.
- POST for WMS. Only GET is implemented.
- Recoloring. Every advertised style reads the same styled PNG blocks.
- Scientific resampling. Display sampling is nearest-neighbor so class colors and nodata stay intact. Means and other statistics come only from a quantitative backend.
- On-demand tile generation, hillshade burning, and dynamic levels that read source rasters.
- Fetching `https` asset links, `s3://` objects, or any caller-supplied raster URL.
- Mutation tools, anonymous writes, and user administration.
- A listening MCP or HTTP server. Factories return WSGI and ASGI apps; nothing in this package binds a port.
- Formal auth beyond a bearer-token map. CORS `*` is set only for anonymous responses.

Existence of a restricted id is distinguishable from an unknown id (`403` versus `404`) for a caller who can hit the route. Lists hide restricted ids.

## Deployment prerequisites

1. Publish a registry JSON file that validates as `geo-map.dataset-registry/v0`, and a data root that contains the stored PNG blocks (and local quantitative files, if configured).
2. Set `public_base` to the HTTPS origin so TileJSON and WMS links are absolute.
3. Provide `GEOMAP_INTERFACE_TOKENS` outside the source tree for restricted datasets. Do not commit tokens.
4. Mount the WSGI app at the same host without overlapping `/map/`.
5. For MCP Streamable HTTP, mount `serverless_app` and enter the SDK session-manager lifespan. Choose the principal before building the server; the tools do not read the HTTP Authorization header themselves.
6. Allow `image/png` as binary on API Gateway if the `apigateway_v2_handler` adapter is used. The adapter is local and is not an AWS invocation.
7. Install the `cog` extra only for datasets whose quantitative backend is `cog`.
8. Keep the legacy tile process running until clients move to `/interfaces/...`.
9. Review budgets (`max_wms_edge`, `max_wms_pixels`, `max_blocks`, `max_mosaic_pixels`, `max_asset_bytes`, `max_stats_cells`) before exposing the app beyond a fixture.
10. Do not point this unreleased process at production buckets or invoke production Lambdas as part of bringing the package up. Wire a read-only filesystem or object adapter in a later increment after the auth review.
