# Raster pyramid worker

The admin Lambda does not render pyramids. A generated GeoTIFF is read with rasterio 1.4.3, whose manylinux wheel carries GDAL. The legacy `gio` package is not installed and is not imported. `osgeo` is not required.

The engine keeps the version-2 block grid: Web Mercator, 256px tiles, `tile_merge` 1–8, color-ramp stops, and nearest, bilinear, or cubic resampling. Output paths are `tiles/{z}/{x}/{y}.png` under a job prefix `builds/{job_id}/`. A later job uses a new prefix. Completed PNGs are skipped on retry, so a resumed batch does not write the same object twice.

`max_build_tiles` (default 32) is the number of blocks in one batch. `build_absolute_max` (default 256) rejects a larger plan before anything is queued. 256 is a staging guard, not a measured global pyramid. A plan between those two numbers is several batches. A resumed block is skipped only when its sha256 matches the checkpoint. A different hash fails the job and does not overwrite the object. Cancel stops the next block. A failed or cancelled job cannot be published. Publish of a validated raster job stores a `geo-map.layer-registry.v1` record and also returns a `geomap.png_pyramid` 1.0.0 manifest plus a separate `geo-map.dataset-registry/v0` export. Those two schemas are not the same document. `live_aws_verified` stays false in this process.

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

## Container check on this machine

Rootless podman 4.9.3 built `localhost/geo-map-layer-manager-worker:local` (`acb8dc8b00fb`). The slim base image needs `libexpat1` or rasterio fails to import `libexpat.so.1`. The image was not pushed and no ECR repository was created.

A `--network none` run with `BUILD_ALLOW_S3=0` read a generated GeoTIFF mounted from the host and wrote `tiles/3/0/0.png`, `tiles/4/0/0.png`, and `tiles/4/1/0.png`. The west center was `(45, 0, 134, 255)`, the east center was `(136, 0, 43, 255)`, and the nodata corner was transparent. The same image refused an `s3://` source while the flag was off and wrote no PNG. That run did not call AWS.

The S3 get/head/put path is covered by a botocore Stubber. Creating the client does not send a request, and every operation in that test is stubbed. It is not a live verification.

Rebuild from this tree:

```bash
podman build -f management/worker/Dockerfile -t geo-map-layer-manager-worker:local .
```

The parent still has to choose the ECR tag, subnet ids, a security group that can reach S3 and ECR on 443, and the source bucket and prefix. The output bucket name, when the condition is true, is `geo-map-layer-manager-staging-builds-544020760996`. The image reference must be `544020760996.dkr.ecr.us-west-2.amazonaws.com/geo-map-layer-manager-worker:<tag>` and cannot be `latest`. Default limits are a batch of 32 and an absolute cap of 256 blocks. That cap is not a measured global workload.
