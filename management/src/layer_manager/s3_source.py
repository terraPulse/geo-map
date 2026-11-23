"""Allowlisted S3 reads and versioned PNG writes.

s3_client_from_environment is what the container entrypoint calls. It does
not send a request by itself. Tests replace boto3.client with a Stubber
client. This module never calls AWS on import.
"""

import os
from urllib.parse import urlparse

from .build_allow import parse_allowlist, resolve_key
from .errors import ValidationFailed
from .pyramid_engine import PyramidError, sha256_bytes

DENIED = ("geo-map-tiles", "admin.terrapulse.com", "map-tiles-dev")


def s3_client_from_environment():
    """Build the process S3 client from AWS_REGION. No API call is made here."""
    import boto3
    from botocore.config import Config

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or ""
    if region != "us-west-2":
        raise PyramidError("region", "S3 client region must be us-west-2. No request was sent.")
    return boto3.client(
        "s3",
        region_name=region,
        config=Config(connect_timeout=2, read_timeout=10, retries={"max_attempts": 2}),
    )


def split_allowlisted(uri, allowlist_text):
    """Return (bucket, key) only when uri sits under a configured prefix."""
    if not isinstance(uri, str) or not uri.startswith("s3://"):
        raise PyramidError("source_not_allowlisted", "Source URI must be an allowlisted s3:// object.")
    _reject_denied(uri)
    try:
        entries = parse_allowlist(allowlist_text)
    except ValidationFailed as exc:
        raise PyramidError("source_not_allowlisted", exc.message) from exc
    for entry in entries:
        prefix = entry["uri"]
        if uri.startswith(prefix):
            key = uri[len(prefix):]
            full = resolve_key(prefix, key)
            if full != uri:
                raise PyramidError("source_not_allowlisted", "Object key is outside the allowlisted prefix.")
            bucket = urlparse(prefix).netloc
            object_key = urlparse(full).path.lstrip("/")
            _reject_denied(bucket)
            return bucket, object_key
    raise PyramidError("source_not_allowlisted", "Refusing a URI outside the source allowlist. Nothing was fetched.")


def assert_output_target(bucket, prefix, job_id):
    if not isinstance(bucket, str) or not bucket or "/" in bucket or bucket.startswith("."):
        raise PyramidError("output_bucket", "Output bucket is not configured. No PNG was uploaded.")
    _reject_denied(bucket)
    if not isinstance(job_id, str) or len(job_id) != 32 or any(ch not in "0123456789abcdef" for ch in job_id):
        raise PyramidError("output_prefix", "Job id cannot be used as a version prefix. No PNG was uploaded.")
    expected = f"builds/{job_id}"
    cleaned = (prefix or "").strip("/")
    if cleaned != expected:
        raise PyramidError("output_prefix", "Output prefix must be builds/{job_id}. The requested prefix was not used.")
    return expected


def download_allowlisted(uri, allowlist_text, dest_dir, client):
    bucket, key = split_allowlisted(uri, allowlist_text)
    dest = os.path.join(dest_dir, os.path.basename(key) or "source.tif")
    os.makedirs(dest_dir, exist_ok=True)
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()
    if not body:
        raise PyramidError("source_empty", "The allowlisted object was empty. No PNG was written.")
    with open(dest, "wb") as handle:
        handle.write(body)
    return dest


def upload_outputs(output_dir, hashes, bucket, prefix, job_id, client):
    """Put each PNG under builds/{job_id}/. An existing object must match sha256."""
    version = assert_output_target(bucket, prefix, job_id)
    uploaded = []
    unchanged = []
    for relative, digest in sorted(hashes.items()):
        if not relative.startswith("tiles/") or ".." in relative.split("/"):
            raise PyramidError("output_key", "Refusing an output path outside tiles/.")
        local = os.path.join(output_dir, relative)
        with open(local, "rb") as handle:
            blob = handle.read()
        if sha256_bytes(blob) != digest:
            raise PyramidError("tile_hash_mismatch", f"{relative} no longer matches its checkpoint. It was not uploaded.")
        key = f"{version}/{relative}"
        state = _put_if_absent(client, bucket, key, blob, digest)
        if state == "written":
            uploaded.append(key)
        else:
            unchanged.append(key)
    return {"uploaded": uploaded, "unchanged": unchanged, "live_aws_verified": False}


def _put_if_absent(client, bucket, key, blob, digest):
    from botocore.exceptions import ClientError

    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in {"404", "NoSuchKey", "NotFound"}:
            raise PyramidError("output_head", f"Could not check {key}. No PNG was uploaded.") from exc
        head = None
    if head is not None:
        remote = (head.get("Metadata") or {}).get("sha256")
        if remote != digest:
            raise PyramidError(
                "tile_hash_mismatch",
                f"{key} already exists with a different sha256. It was not overwritten.",
            )
        return "unchanged"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=blob,
        ContentType="image/png",
        Metadata={"sha256": digest},
    )
    return "written"


def _reject_denied(value):
    lowered = value.lower()
    if any(item in lowered for item in DENIED):
        raise PyramidError("source_not_allowlisted", "That bucket is not an allowed build source. Nothing was fetched.")
