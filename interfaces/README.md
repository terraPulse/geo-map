# geo-map interfaces

Provisional read-only API for geo-map datasets. It discovers datasets, serves TileJSON and XYZ tiles, answers WMS 1.3.0 `GetCapabilities` and `GetMap`, and exposes the same records through MCP. It does not replace the legacy `/map/...` server and it does not render source rasters.

Styled images are resampled from stored PNG blocks. Numeric values are returned only when a dataset configures a quantitative backend (`grid` or optional `cog`). A styled PNG color is not treated as a measurement.

## Layout

`interfaces/` is a separate package (`geomap-interfaces`, import `geomap_interfaces`). It does not import `gio`, `geo_map_util`, or `geo_map_serv`.

```text
interfaces/
  docs/          provisional registry contract and the v0 JSON Schema
  src/           library, WSGI app, API Gateway adapter, MCP server
  tests/         offline synthetic fixtures
```

## Run the tests

From the repository root:

```bash
python3 -m pip install -e "./interfaces[dev]"
python3 -m pytest interfaces/tests
```

The COG reader imports `rasterio` only when a COG query runs. Install `rasterio` with the `cog` extra when that backend is configured. Tests do not require it.

## Commands

```bash
geomap-interfaces validate registry.json
geomap-interfaces import-legacy /path/to/local/tile/root
```

Both commands are offline. There is no serve command in this increment.

## What a host mounts

- WSGI: `geomap_interfaces.http.build_app(runtime)`
- API Gateway HTTP API v2, local adapter only: `geomap_interfaces.apigw.apigateway_v2_handler`
- MCP Streamable HTTP, stateless JSON, not listening: `geomap_interfaces.mcp_server.serverless_app`

Routes live under `/interfaces/`. `/map/...` is intentionally absent.

See [docs/registry-contract.md](docs/registry-contract.md) for the registry the admin app can write, and [docs/limitations.md](docs/limitations.md) for what this increment does not do.
