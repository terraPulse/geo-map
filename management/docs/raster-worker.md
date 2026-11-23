# Raster pyramid worker

The admin Lambda does not render pyramids. A generated GeoTIFF is read with rasterio 1.4.3, whose manylinux wheel carries GDAL. The legacy `gio` package is not installed and is not imported. `osgeo` is not required.

The engine keeps the version-2 block grid: Web Mercator, 256px tiles, `tile_merge` 1–8, color-ramp stops, and nearest, bilinear, or cubic resampling. Output paths are `tiles/{z}/{x}/{y}.png` under a job prefix `builds/{job_id}/`. A later job uses a new prefix. Completed PNGs are skipped on retry, so a resumed batch does not write the same object twice.

`max_build_tiles` (default 32) is the number of blocks in one batch. `build_absolute_max` (default 4096) rejects a plan before anything is queued. A plan between those two numbers is several batches with a checkpoint. Cancel stops the next block. Publish is allowed only after every planned block validated. The registry record is still synthetic, and `png_pyramid_regenerated` stays false.

## S3

A source URI is accepted only when it sits under `LAYER_MANAGER_SOURCE_ALLOWLIST` (`name=s3://bucket/prefix/`). Buckets whose names contain `geo-map-tiles`, `admin.terrapulse.com`, or `map-tiles-dev` are refused. Without an injected reader, inspect returns `source_reader_unconfigured`, `read_s3` is false, and no PNG is written. The container downloads only when `BUILD_ALLOW_S3=1` and uploads only when `BUILD_OUTPUT_BUCKET` is also set.

## Scale to zero

The staging template creates no Batch resources unless `EnableBuilds=true` and the source bucket, image URI, subnet ids, and security group are all set. With those values the template adds:

- a private output bucket `geo-map-layer-manager-staging-builds-544020760996`
- an SQS queue and a dead-letter queue
- a submitter Lambda (reserved concurrency 2) that calls `batch:SubmitJob`
- a Fargate compute environment with minimum 0 vCPU, maximum 4, and public IP assignment so no NAT gateway is required
- a job role that can `s3:GetObject` and `s3:ListBucket` on the source prefix and `s3:PutObject` on `builds/*` in the output bucket

The API Lambda stays off the worker route. Its executor becomes `rasterio` and its orchestrator becomes `batch` only under that same condition, which means it sends one queue message and does not render. The default stack update, with builds and preview left off, does not create these resources.

No NAT, RDS, ALB, or EC2 start/stop permission is in the template. Idle Lambda, HTTP API, DynamoDB on-demand, Cognito, CloudFront, and SQS stay near the existing staging cost. Batch and Fargate charge per vCPU-second only after a job starts. Point-in-time recovery and 14-day logs are unchanged. Reserved concurrency has no hourly fee; if the account cannot reserve it, the update fails closed rather than running unbounded.

## Not built on this machine

Docker is not installed in the cloud-agent VM, so no image was built and no ECR repository was created. The image build, from a machine that has Docker, is:

```bash
docker build -f management/worker/Dockerfile -t geo-map-layer-manager-worker:local .
```

The parent still has to choose the image URI, two subnet ids, a security group, the source bucket and prefix, and confirm the output bucket name before `EnableBuilds` can be true. This repository does not submit a job or call AWS.
