# Builds and renderer preview

Commit after `c12db1d2a4101939d7f0f4b5b9521edba2763330`. The artifacts from that commit stay the ones already being deployed. This document is the next delta. It was not applied to AWS by this coding run.

## Renderer preview

The isolated function is `arn:aws:lambda:us-west-2:544020760996:function:geomap-tile-pyramid-test`. Its Function URL uses `AWS_IAM` and is not called by this app. The browser never sees that URL, a signing key, or the admin Cognito token on a renderer request.

When `RendererInvokeEnabled` is `true`, the admin Lambda may call `lambda:InvokeFunction` on that ARN only. The event is API Gateway payload 2.0:

- `GET /tiletest/v1/layers`
- `GET /tiletest/v1/map/{layer_id}/{z}/{x}/{y}.png`

`layer_id` may contain slashes. The only layer the deployed function currently allows is `fixture/demo-pyramid`. A tile is shown only if that id is in the allowlist the function returns. Zoom and indexes are checked before the invoke. The decoded PNG must be 256 by 256 and at most 2 MB.

Default is `RendererInvokeEnabled=false`. `GET /v1/preview/status` then returns `integration_status: unconfigured` and `pending: true`. No invoke is attempted.

The browser loads a preview with `GET /v1/preview/tile` and its admin bearer header, then uses a blob object URL. The token is not put in the query string.

An offline fixture adapter uses the same event and response shape for tests. Its responses are labeled `fixture-offline`. They are not live Lambda calls and they are not S3 builds.

## Tile builds

`build_tiles_task.py` needs `gio` and GDAL. Those libraries are not in the admin Lambda. A global build is not run inside the HTTP request.

The admin API can estimate a version-2 PNG block pyramid (`tiles/{z}/{x}/{y}.png`, merge 1 through 8, the same layout the test renderer reads). The count uses the Web Mercator math from `util/lib/map_tile.py`. It is an upper-bound plan. It does not open the raster.

A plan over `LAYER_MANAGER_MAX_BUILD_TILES` (default 32) is returned and not queued.

Real builds stay off unless `EnableBuilds=true` and `SourceBucketName` is a non-tile bucket. The source key must stay under that prefix. `..`, another bucket, and `geo-map-tiles` are rejected. This Lambda still sets `LAYER_MANAGER_BUILD_EXECUTOR=disabled`, so a real job is not started here. Inspecting an S3 object without GDAL returns `inspect_runtime_missing` and does not invent CRS, resolution, bands, nodata, or bounds.

The offline fixture source `fixture-demo` can queue one small PNG when the process is explicitly in `fixture-offline` mode. That file is written on local disk, status `succeeded`, `real_s3_write: false`. Publishing it creates a synthetic registry row. It does not regenerate an existing pyramid.

A queued gio job fails with `builder_runtime_missing` or `builder_locked` and `tiles_written: 0`. That failure is not reported as success.

Jobs move `queued`, `running`, `succeeded`, `failed`, or `cancelled`. Cancel of a queued job does not start work and does not touch EC2. Retry is allowed only after failure or cancel and reuses the same job id. The same idempotency key and plan return the original job. A different plan with that key is a conflict.

## What is still unverified in AWS

- No invoke of `geomap-tile-pyramid-test` was made.
- No Batch compute environment, queue, or container image is in this template. A later image that contains the gio toolchain, two subnets, and a security group are required before a real build can run. That image was not selected.
- The output bucket for real tiles was not created. The prefix `builds/{job_id}/` is the intended new version location. It must not be an existing tile prefix.
- Job rows in this slice live in the admin process. A durable table is required before real builds are enabled on more than one Lambda environment.
- `geo-map.layer-registry.v1` is still not `geo-map.dataset-registry/v0`.
