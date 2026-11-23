"""Source and output path checks. No bucket is listed unless it was configured."""

from urllib.parse import urlparse

from .errors import ValidationFailed

DENIED = ("geo-map-tiles", "admin.terrapulse.com", "map-tiles-dev")


def parse_allowlist(text):
    entries = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValidationFailed("Source allowlist entries must look like name=s3://bucket/prefix/.", [])
        name, uri = part.split("=", 1)
        name = name.strip()
        uri = uri.strip()
        if not name or "/" in name or name in {".", ".."}:
            raise ValidationFailed("Source name is not allowed.", [])
        prefix = _prefix(uri)
        entries.append({"id": name, "uri": prefix, "kind": "s3"})
    return tuple(entries)


def _prefix(uri):
    lowered = uri.lower()
    if any(item in lowered for item in DENIED):
        raise ValidationFailed("That bucket is not an allowed build source.", [])
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or parsed.username:
        raise ValidationFailed("Source URI must be s3://bucket/prefix/.", [])
    path = parsed.path if parsed.path.endswith("/") else parsed.path + "/"
    if path == "/" or ".." in path.split("/"):
        raise ValidationFailed("Source prefix is not allowed.", [])
    return f"s3://{parsed.netloc}{path}"


def resolve_key(prefix, key):
    if not isinstance(key, str) or not key or key.startswith("/") or "\\" in key or "://" in key:
        raise ValidationFailed("Object key is not allowed.", [])
    parts = [part for part in key.split("/") if part != ""]
    if any(part in {".", ".."} for part in parts):
        raise ValidationFailed("Object key cannot contain . or .. segments.", [])
    return prefix + "/".join(parts)


def output_prefix_for(root, job_id):
    if not job_id or "/" in job_id or job_id in {".", ".."}:
        raise ValidationFailed("Job id cannot be used as an output prefix.", [])
    root = root.strip("/")
    return f"{root}/{job_id}/" if root else f"{job_id}/"
