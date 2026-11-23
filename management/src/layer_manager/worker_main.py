"""Container entrypoint for one pyramid batch.

Reads BUILD_SPEC_JSON. Downloads an object only when BUILD_ALLOW_S3=1 and the
URI is allowlisted. Uploads PNGs only when BUILD_OUTPUT_BUCKET is set. This
process does not start work when the spec is missing.
"""

import json
import os
import sys
import tempfile

from .pyramid_engine import PyramidError, render_pyramid
from .s3_source import download_allowlisted, upload_outputs


def main(argv=None, s3_client=None):
    del argv
    raw = os.environ.get("BUILD_SPEC_JSON") or sys.stdin.read() or "{}"
    spec = json.loads(raw)
    try:
        source, fetched = _source(spec, s3_client)
        result = render_pyramid(
            source,
            spec["output_dir"],
            spec["bounds"],
            spec["zooms"],
            spec.get("tile_merge", 1),
            spec.get("resampling", "nearest"),
            spec["stops"],
            completed=spec.get("completed") or [],
            batch_size=spec.get("batch_size"),
        )
        uploaded = []
        bucket = os.environ.get("BUILD_OUTPUT_BUCKET") or ""
        if bucket:
            if s3_client is None or os.environ.get("BUILD_ALLOW_S3") != "1":
                raise PyramidError(
                    "output_writer_unconfigured",
                    "Output bucket is set but S3 writes are off. No PNG was uploaded.",
                )
            uploaded = upload_outputs(
                spec["output_dir"], result["written"], bucket, spec.get("output_prefix") or "", s3_client
            )
    except PyramidError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "message": exc.message, "tiles_written": 0, "real_s3_write": False}))
        return 1
    payload = {
        "ok": not result["stopped"] and len(result["completed"]) == result["total"],
        "real_s3_write": bool(uploaded),
        "uploaded": uploaded,
        "fetched": fetched,
        **result,
    }
    print(json.dumps(payload))
    return 0 if payload["ok"] else 3


def _source(spec, s3_client):
    uri = spec.get("source_uri") or ""
    if uri.startswith("s3://"):
        if os.environ.get("BUILD_ALLOW_S3") != "1" or s3_client is None:
            raise PyramidError(
                "source_reader_unconfigured",
                "S3 reads are off. No object was fetched and no PNG was written.",
            )
        dest = download_allowlisted(uri, spec.get("allowlist") or "", tempfile.mkdtemp(prefix="pyramid-source-"), s3_client)
        return dest, True
    path = spec.get("source_path")
    if not path:
        raise PyramidError("source_missing", "No local raster path was provided. No PNG was written.")
    return path, False


if __name__ == "__main__":
    raise SystemExit(main())
