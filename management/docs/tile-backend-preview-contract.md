# Tile backend preview contract

The performance branch (`cursor/tile-view-correctness-720a`, pull request 2) is a separate tile renderer. It is not deployed by this registry. Its public path shapes, recorded in that branch's `doc/integration_boundaries.md`, are:

| `path_order` | Path after the base URL |
| --- | --- |
| `map` | `/map/{tag}/{z}/{x}/{y}.png` |
| `zx_y` | `/zx_y/{tag}/{z}/{x}/{y}.png` |
| `zxy` | `/zxy/{tag}/{z}/{x}/{y}.png` |
| `xyz` | `/xyz/{tag}/{x}/{y}/{z}.png` |

`{tag}` keeps slash separators. `demo/water_freq/y2025` stays `demo/water_freq/y2025`. The registry encodes each segment and does not turn `/` into `%2F`. That matches the historical parser, which treats the tag as everything before the last three numeric components.

## Deployment-time configuration

Leave both values empty or at the default until the parent has a test endpoint. Do not point them at `admin.terrapulse.com`, a `geo-map-tiles` bucket, or the existing `map-tiles-dev` front.

| Setting | Environment variable | CloudFormation parameter | Default |
| --- | --- | --- | --- |
| Base URL | `LAYER_MANAGER_TILE_BACKEND_BASE_URL` | `TileBackendBaseUrl` | empty |
| Path order | `LAYER_MANAGER_TILE_PATH_ORDER` | `TilePathOrder` | `map` |

The base URL is an origin or prefix, for example `https://abc123.execute-api.us-west-2.amazonaws.com`. It is not a template: `.png`, `{z}`, and `{tag}` are rejected. The process also rejects `http`, userinfo, and the production names above. An empty value is valid and means the endpoint is not known.

`config.js` may repeat the same public values after `render_config.py` reads stack outputs. The API is authoritative. `integrated` in that file is always `false`.

## Response fields

`GET /v1/session`, `GET /v1/contract`, and every layer preview include `tile_backend`:

| Field | Type | Meaning |
| --- | --- | --- |
| `endpoint_supplied` | boolean | A base URL was configured. |
| `base_url` | string or null | That URL, with no trailing slash. Null when unset. |
| `path_order` | string | `map`, `zx_y`, `zxy`, or `xyz`. |
| `integrated` | boolean | Always `false` in this increment. |
| `calls_backend` | boolean | Always `false`. The registry does not call the tile Lambda. |
| `publish_generates_tiles` | boolean | Always `false`. |
| `admin_authorization_sent` | boolean | Always `false`. The Cognito access token is not sent to the tile host. |
| `integration_status` | string | `awaiting-parent-endpoint` or `address-only`. |
| `performance_branch` | string | Branch name of PR 2. Not a live claim. |
| `performance_pr` | string | Pull request URL. |
| `note` | string | Human-readable status. |

A layer preview adds:

| Field | Meaning |
| --- | --- |
| `mode` | `awaiting-parent-endpoint`, `address-only`, `authorized-template`, or `rejected`. |
| `template` | Address to display, or null. |
| `composed_template` | Server-built address when a base URL and tag exist. |
| `stored_template` | A previously stored template whose host is allowlisted, otherwise null. |
| `sample_tile_url` | Always null. The UI does not substitute coordinates and request a PNG. |
| `remote_fetch` | Always `false`. |
| `tag_encoding` | `slash-preserved`. |

`GET /v1/contract` also returns `preview_contract.orders` with the four patterns and `admin_authorization_sent_to_tiles: false`.

Example when the parent has supplied a test base and the tag contains slashes:

```json
{
  "mode": "address-only",
  "template": "https://abc123.execute-api.us-west-2.amazonaws.com/map/demo/water_freq/y2025/{z}/{x}/{y}.png",
  "composed_template": "https://abc123.execute-api.us-west-2.amazonaws.com/map/demo/water_freq/y2025/{z}/{x}/{y}.png",
  "sample_tile_url": null,
  "remote_fetch": false,
  "integrated": false,
  "calls_backend": false,
  "publish_generates_tiles": false,
  "tag_encoding": "slash-preserved"
}
```

## Auth and CORS

The admin API and the tile service are different origins.

- Browser calls to `/v1/*` use the Cognito access token and the admin API origin. API Gateway CORS allows only `https://{cloudfront-domain}`.
- The console shows a tile address as text. It does not set an image URL, so the tile host does not need to allow the admin origin, and the admin token is not attached.
- CloudFront's content security policy allows images only from `'self'` and `data:`. The region-wide `execute-api` entry is `connect-src` for the admin API and Cognito, not permission to load tiles.
- Do not add the tile origin to the admin API `AllowOrigins`. That would let a page on the tile host call the registry.
- The tile Lambda's own auth, if any, belongs to that stack. This registry does not assume it.

## What is still required before any live coupling

1. Parent deploys an isolated test API for the performance branch and records its HTTPS base URL. This repository does not do that.
2. Parent sets `TileBackendBaseUrl` and, if needed, `TilePathOrder`, then updates this stack. Until that update, `integration_status` stays `awaiting-parent-endpoint`.
3. Parent confirms the test API reads an isolated tile prefix, not `s3://geo-map-tiles-w2`.
4. Parent reconciles `management/contracts/layer-registry-v1.schema.json` into the interfaces branch before any shared client uses the schema.
5. A later change can load PNG bytes in the browser only after the tile host's anonymous-or-separate auth and the console `img-src` policy are reviewed. Publishing a registry row still will not generate those PNGs.
