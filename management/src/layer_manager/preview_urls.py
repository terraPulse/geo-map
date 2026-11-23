"""Preview addresses for a tile backend that may not exist yet.

This module never retrieves a URL. A configured base URL only fills in the
historical path from the performance-branch contract (PR 2). Publishing a
registry record does not generate tiles, and this service does not call the
tile backend.
"""

from urllib.parse import quote, urlparse

PATH_ORDERS = ("map", "zx_y", "zxy", "xyz")

# PR 2 (cursor/tile-view-correctness-720a) keeps these historical orders.
# {tag} keeps slash separators. Each segment is escaped on its own.
_ORDER_PATH = {
    "map": "/map/{tag}/{z}/{x}/{y}.png",
    "zx_y": "/zx_y/{tag}/{z}/{x}/{y}.png",
    "zxy": "/zxy/{tag}/{z}/{x}/{y}.png",
    "xyz": "/xyz/{tag}/{x}/{y}/{z}.png",
}


def encode_tag(tag):
    """Preserve '/' between segments. Do not encode the tag as one path piece."""
    return "/".join(quote(part, safe="") for part in str(tag).split("/"))


def compose_template(base_url, path_order, tag):
    path = _ORDER_PATH[path_order].replace("{tag}", encode_tag(tag))
    return base_url.rstrip("/") + path


def tile_backend_status(base_url, path_order):
    common = {
        "path_order": path_order,
        "integrated": False,
        "calls_backend": False,
        "publish_generates_tiles": False,
        "performance_branch": "cursor/tile-view-correctness-720a",
        "performance_pr": "https://github.com/terraPulse/geo-map/pull/2",
        "admin_authorization_sent": False,
    }
    if not base_url:
        common.update(
            {
                "endpoint_supplied": False,
                "base_url": None,
                "integration_status": "awaiting-parent-endpoint",
                "note": (
                    "No tile-backend base URL is configured. "
                    "The parent will supply the test endpoint for the performance branch. "
                    "This registry does not call that Lambda or any production tile front."
                ),
            }
        )
        return common
    common.update(
        {
            "endpoint_supplied": True,
            "base_url": base_url.rstrip("/"),
            "integration_status": "address-only",
            "note": (
                "The base URL is an address template only. "
                "Publishing a layer does not generate tiles, and this service does not call the backend."
            ),
        }
    )
    return common


def describe_preview(record, preview_hosts, tile_backend_base_url="", tile_path_order="map"):
    status = tile_backend_status(tile_backend_base_url, tile_path_order)
    tag = record.get("tag") or ""
    composed = compose_template(tile_backend_base_url, tile_path_order, tag) if status["endpoint_supplied"] and tag else None
    stored = record.get("authorized_tile_template")
    stored_ok = _stored_allowed(stored, preview_hosts)
    template = composed or (stored if stored_ok else None)
    if composed:
        mode = "address-only"
        reason = (
            "Preview address uses the configured tile-backend base URL and keeps slashes in the layer id. "
            "The URL is not requested. Publishing does not generate tiles."
        )
    elif not stored:
        mode = "awaiting-parent-endpoint"
        reason = status["note"]
    elif stored_ok:
        mode = "authorized-template"
        reason = "Stored template matches the preview allowlist. This service does not request the URL."
    else:
        mode = "rejected"
        template = None
        reason = "Stored template host is not allowlisted. It is not returned and not requested."
    return {
        "mode": mode,
        "template": template,
        "composed_template": composed,
        "stored_template": stored if stored_ok else None,
        "sample_tile_url": None,
        "remote_fetch": False,
        "integrated": False,
        "calls_backend": False,
        "publish_generates_tiles": False,
        "tag_encoding": "slash-preserved",
        "tile_backend": status,
        "reason": reason,
    }


def _stored_allowed(template, preview_hosts):
    if not template:
        return False
    parsed = urlparse(template)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    origin = f"https://{parsed.hostname}"
    if parsed.port:
        origin += f":{parsed.port}"
    allowed = {host.rstrip("/") for host in preview_hosts or ()}
    return origin in allowed
