# Test Lambda: PNG pyramid viewer

Isolated function for a parent to deploy in terraPulse account `544020760996`, region `us-west-2`. It is not the production `/maptiles` front and it is not merged by this change.

The zip does **not** contain `lambda/handler.py`. That file is the legacy source-raster generator. This function only crops and resamples PNGs that are already stored.

## Why this runtime

`gio`, GDAL, and the Cython modules under `util/mod/` are what the batch renderer needs to *create* tiles from rasters. The view path for a block layer only needs the PNG bytes, Pillow, and the pure helpers in `util/lib/tile_runtime.py`.

| Piece | Choice | Checked |
|---|---|---|
| Runtime | Lambda `python3.12`, architecture `x86_64` | Builder is CPython 3.12. The zip is imported and invoked locally. |
| Pillow | `12.2.0` `manylinux2014_x86_64` / `manylinux_2_17` `cp312` wheel, sha256 in the manifest | `12.3.0` has no manylinux2014 wheel in the index this builder saw. `12.2.0` downloaded with `--only-binary` and installed `--no-deps`. |
| boto3 | Lambda runtime copy, not vendored | Imported only when `TILE_BUCKET` is set and a layer's storage is `s3`. Fixture invokes do not import it. |
| gio / GDAL / Cython | Not in the artifact | Zip layout test fails if those trees are packed. |

Python 3.14 (`map-tiles-dev`) was not selected. This builder did not compile or invoke a 3.14 Lambda runtime, so this document does not claim that runtime.

## Adapter the management preview calls

```
adapter: geomap.png_pyramid
adapter_version: 1.0.0
```

| Method | Path | Result |
|---|---|---|
| GET | `/tiletest/v1/layers` | Allowlist, URL templates, `source_raster_reads: false` |
| GET | `/tiletest/v1/layers/{layer_id}` | One allowlisted layer. Unknown id is 403 |
| GET | `/tiletest/v1/{order}/{layer_id}/{z}/{x}/{y}.png` | `order` is `map`, `zx_y`, or `zxy` |
| GET | `/tiletest/v1/xyz/{layer_id}/{x}/{y}/{z}.png` | Same normalizer as the Flask `xyz` order |
| OPTIONS | same paths | CORS only when `Origin` equals `TILE_CORS_ORIGIN` |

`map` uses the same index math as `zx_y`. Far-edge `_` / `-` indexes follow `normalize_service_path` (the service rule, including `_0` → `0`).

PNG responses:

- `content-type: image/png`
- `isBase64Encoded: true` (payload format 2.0, which Function URLs and HTTP APIs use)
- `x-geomap-adapter: geomap.png_pyramid`
- `x-geomap-adapter-version: 1.0.0`
- `x-geomap-tile: tile` or `nodata`
- a missing stored PNG is HTTP 200 with a transparent 256×256 PNG, not a source-raster render
- `GEOMAP_VIEW_SOURCE_RENDER` is ignored

If a REST API (payload format 1.0) is put in front later, set its binary media type to `image/png`. A Function URL with `InvokeMode: BUFFERED` does not need that setting when `isBase64Encoded` is true.

The registry cannot name a bucket or a URL. S3 layers are relative `key_prefix` values under `TILE_BUCKET` + `TILE_KEY_ROOT`. The request path cannot be an absolute URL. Zoom, column, and row must fall inside the layer `max_zoom` and `2^z`.

Packaged demo layer id: `fixture/demo-pyramid`. The PNG is synthetic and labeled FIXTURE. It is not a public production layer. Stored level is `2`, `tile_merge` is `2`, object key `fixture/demo-pyramid/tiles/2/0/0.png`.

## Auth and CORS

Default stack auth is Function URL `AWS_IAM`. No public invoke permission is created. A management backend signs requests.

Browser preview uses `AuthMode=header`. The parent passes `TileAuthToken` at deploy time (NoEcho). The handler compares `x-tile-test-token` with `hmac.compare_digest`. An empty token fails closed with 401. The token is not in git.

`CorsOrigin` is one exact origin. `*` is ignored. Unmatched `Origin` on OPTIONS is 403 and does not get `access-control-allow-origin`.

## Build

From the repo root, with Python 3.12:

```bash
python3 deploy/tile_pyramid_test/build_artifact.py
```

The default zip is `build/geomap-tile-pyramid-test-py312-x86_64.zip` plus a `.manifest.json` (sha256, Pillow wheel sha256, handler, runtime). `build/` is gitignored.

A build from this commit is byte-stable. The published copy is:

```
sha256 b26d702a488432863846e0b27717de0e441d0169bc727a3774ffa1b161a0b6ed
bytes  7886717
pillow wheel sha256 b86024e52a1b269467a802258c25521e6d742349d760728092e1bc2d135b4d76
```

Override the output with `TILE_PYRAMID_ZIP`.

## Deploy (parent executor)

Do not run this from an unauthenticated agent. The script checks the account and region, uploads the zip, and deploys `infra/tile_pyramid_test/template.yaml` as stack `geomap-tile-pyramid-test`.

```bash
export AWS_REGION=us-west-2
export ARTIFACT_BUCKET=...   # bucket you already own, for the zip only
export AUTH_MODE=iam          # or header, with TILE_AUTH_TOKEN set outside git
# optional staging reads:
# export TILE_BUCKET=...
# export TILE_KEY_PREFIX=tile-pyramid-test/
bash infra/tile_pyramid_test/parent-deploy.sh
```

The role's only data permission is `s3:GetObject` on `arn:aws:s3:::${TileBucket}/${TileKeyPrefix}*`, and only when `TileBucket` is non-empty. No `ListBucket`, no writes. Reserved concurrency 2, timeout 10 seconds, memory 512 MB, log retention 7 days.

After deploy, the stack outputs `FunctionUrl`. Fixture check (header mode shown; IAM mode needs SigV4 instead of the header):

```bash
curl -sS -D - -o /tmp/tile.png \
  -H "x-tile-test-token: $TILE_AUTH_TOKEN" \
  "$FUNCTION_URL/tiletest/v1/zx_y/fixture/demo-pyramid/2/1/0.png"
```

Expect `content-type: image/png` and a 256×256 PNG. `GET $FUNCTION_URL/tiletest/v1/layers` is the document the management UI should cache for layer ids and templates.

## Limits

- Coarser-than-stored views follow the historical single-tile BICUBIC `zoomout`, not a mosaic.
- `tile_merge` above 8 is rejected at registry load.
- The in-process PNG cache is per execution environment (`GEOMAP_TILE_CACHE_BYTES`, default 64 MiB).
- This zip was not invoked inside the Lambda service. Local import and `lambda_handler` calls are the test. Pillow's manylinux2014 wheel matches the Amazon Linux glibc used by `python3.12` x86_64; that is a compatibility argument, not a cloud invoke log.
