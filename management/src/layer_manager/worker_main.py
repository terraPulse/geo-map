"""Container entrypoint for one pyramid batch.

When BUILD_ALLOW_S3=1 and no client is passed in, this process constructs
the S3 client from AWS_REGION. Tests patch boto3.client. Nothing is fetched
when the flag is off.
"""

import json
import os
import sys
import tempfile

from .pyramid_engine import PyramidError, render_pyramid
from .s3_source import (
    assert_output_target,
    download_allowlisted,
    s3_client_from_environment,
    upload_outputs,
)


def main(argv=None, s3_client=None):
    del argv
    raw = os.environ.get("BUILD_SPEC_JSON") or sys.stdin.read() or "{}"
    spec = json.loads(raw)
    try:
        client = _client(spec, s3_client)
        source, fetched = _source(spec, client)
        output_dir = _output_dir(spec)
        result = render_pyramid(
            source,
            output_dir,
            spec["bounds"],
            spec["zooms"],
            spec.get("tile_merge", 1),
            spec.get("resampling", "nearest"),
            spec["stops"],
            completed=list((spec.get("hashes") or {})),
            hashes=spec.get("hashes") or {},
            batch_size=spec.get("batch_size"),
        )
        report = _upload(spec, output_dir, result, client)
    except PyramidError as exc:
        print(json.dumps({
            "ok": False,
            "code": exc.code,
            "message": exc.message,
            "tiles_written": 0,
            "real_s3_write": False,
            "live_aws_verified": False,
        }))
        return 1
    payload = {
        "ok": not result["stopped"] and len(result["completed"]) == result["total"],
        "real_s3_write": bool(report["uploaded"] or report["unchanged"]),
        "live_aws_verified": False,
        "uploaded": report["uploaded"],
        "unchanged": report["unchanged"],
        "fetched": fetched,
        "output_bucket": os.environ.get("BUILD_OUTPUT_BUCKET") or None,
        **result,
    }
    print(json.dumps(payload))
    return 0 if payload["ok"] else 3


def _client(spec, s3_client):
    needs_s3 = (spec.get("source_uri") or "").startswith("s3://") or bool(os.environ.get("BUILD_OUTPUT_BUCKET"))
    if not needs_s3:
        return s3_client
    if os.environ.get("BUILD_ALLOW_S3") != "1":
        return None
    if s3_client is not None:
        return s3_client
    return s3_client_from_environment()


def _source(spec, client):
    uri = spec.get("source_uri") or ""
    if uri.startswith("s3://"):
        allowlist = os.environ.get("BUILD_SOURCE_ALLOWLIST") or ""
        if not allowlist or client is None:
            raise PyramidError(
                "source_reader_unconfigured",
                "S3 reads are off. No object was fetched and no PNG was written.",
            )
        if spec.get("allowlist") and spec.get("allowlist") != allowlist:
            raise PyramidError(
                "source_not_allowlisted",
                "The job allowlist does not match BUILD_SOURCE_ALLOWLIST. Nothing was fetched.",
            )
        dest = download_allowlisted(uri, allowlist, tempfile.mkdtemp(prefix="pyramid-source-"), client)
        return dest, True
    path = spec.get("source_path")
    if not path or not os.path.isfile(path):
        raise PyramidError("source_missing", "No local raster path was provided. No PNG was written.")
    return path, False


def _output_dir(spec):
    raw = spec.get("output_dir") or "/tmp/pyramid-out"
    if not isinstance(raw, str) or not raw.startswith("/tmp/"):
        raise PyramidError("output_dir", "Output directory must be under /tmp. The requested path was not used.")
    os.makedirs(raw, exist_ok=True)
    return raw


def _upload(spec, output_dir, result, client):
    bucket = os.environ.get("BUILD_OUTPUT_BUCKET") or ""
    if not bucket:
        return {"uploaded": [], "unchanged": []}
    if client is None or os.environ.get("BUILD_ALLOW_S3") != "1":
        raise PyramidError(
            "output_writer_unconfigured",
            "Output bucket is set but S3 writes are off. No PNG was uploaded.",
        )
    assert_output_target(bucket, spec.get("output_prefix"), spec.get("job_id"))
    return upload_outputs(
        output_dir,
        result["hashes"],
        bucket,
        spec.get("output_prefix"),
        spec.get("job_id"),
        client,
    )


if __name__ == "__main__":
    raise SystemExit(main())
