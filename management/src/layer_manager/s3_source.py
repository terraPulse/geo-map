"""Allowlisted S3 object names. No client is constructed here."""

from urllib.parse import urlparse

from .build_allow import parse_allowlist, resolve_key
from .errors import ValidationFailed
from .pyramid_engine import PyramidError


def split_allowlisted(uri, allowlist_text):
    """Return (bucket, key) only when uri sits under a configured prefix."""
    if not isinstance(uri, str) or not uri.startswith("s3://"):
        raise PyramidError("source_not_allowlisted", "Source URI must be an allowlisted s3:// object.")
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
            return bucket, key
    raise PyramidError("source_not_allowlisted", "Refusing a URI outside the source allowlist. Nothing was fetched.")


def download_allowlisted(uri, allowlist_text, dest_dir, client):
    import os

    bucket, key = split_allowlisted(uri, allowlist_text)
    dest = os.path.join(dest_dir, os.path.basename(key) or "source.tif")
    os.makedirs(dest_dir, exist_ok=True)
    client.download_file(bucket, key, dest)
    return dest


def upload_outputs(output_dir, written, bucket, prefix, client):
    """Upload already-rendered PNGs. The caller supplies the client."""
    import os

    prefix = prefix.strip("/")
    uploaded = []
    for relative in written:
        if not relative.startswith("tiles/") or ".." in relative.split("/"):
            raise PyramidError("output_key", "Refusing an output path outside tiles/.")
        local = os.path.join(output_dir, relative)
        key = f"{prefix}/{relative}" if prefix else relative
        client.upload_file(local, bucket, key)
        uploaded.append(key)
    return uploaded
