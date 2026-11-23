"""Validate layer records against geo-map.layer-registry.v1.

Structural problems reject the write. Publish blockers can be saved on a
draft and are rejected by publish. Nothing here reads a URL or a tile.
"""

import math
import re
from urllib.parse import urlparse

from .canonical import content_digest
from .effects import REGISTRY_EFFECTS_STORED
from .schema_contract import (
    AGGREGATES,
    AUTHORIZED_ACCOUNT,
    BACKEND_COG,
    BACKEND_PNG,
    BACKENDS,
    CLIENT_LAYER_KEYS,
    DENIED_SUBSTRINGS,
    INVENTORY_REGISTRY,
    INVENTORY_SYNTHETIC,
    SCHEMA_ID,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    STATUSES,
    TILE_PIXEL_SIZE,
    WEB_MERCATOR_LIMIT,
)

_TAG_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def issue(severity, field, code, message):
    return {"severity": severity, "field": field, "code": code, "message": message}


def _error(field, code, message):
    return issue("error", field, code, message)


def _blocker(field, code, message):
    return issue("publish_blocker", field, code, message)


def _warning(field, code, message):
    return issue("warning", field, code, message)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _denied(value):
    text = value if isinstance(value, str) else ""
    lowered = text.lower()
    return any(item in lowered for item in DENIED_SUBSTRINGS)


def assert_no_denied_text(text, field="payload"):
    if _denied(text):
        return _error(
            field,
            "denied_reference",
            "This staging registry refuses production tile-bucket and admin-domain references.",
        )
    return None


def validate_tag(tag):
    errors = []
    if not isinstance(tag, str) or not tag:
        return [_error("tag", "tag_required", "Tag is required.")]
    if len(tag) > 256:
        errors.append(_error("tag", "tag_length", "Tag must be 256 characters or fewer."))
    if tag.startswith("/") or tag.endswith("/") or "//" in tag:
        errors.append(_error("tag", "tag_slashes", "Tag must not start or end with a slash or contain empty segments."))
    if "\\" in tag or any(ord(ch) < 32 or ch.isspace() for ch in tag):
        errors.append(_error("tag", "tag_chars", "Tag must not contain whitespace, backslashes, or control characters."))
    segments = tag.split("/")
    for segment in segments:
        if segment in {".", ".."} or not _TAG_SEGMENT.match(segment or ""):
            errors.append(
                _error(
                    "tag",
                    "tag_segment",
                    "Each tag segment must start with a letter or digit and use only letters, digits, dot, underscore, plus, or hyphen.",
                )
            )
            break
    denied = assert_no_denied_text(tag, "tag")
    if denied:
        errors.append(denied)
    return errors


def _validate_pyramid(pyramid, backend, issues):
    if backend != BACKEND_PNG:
        if pyramid is not None:
            issues.append(_error("pyramid", "pyramid_not_used", "COG layers must set pyramid to null."))
        return None
    if not isinstance(pyramid, dict):
        issues.append(_error("pyramid", "pyramid_required", "PNG-pyramid layers require a pyramid object."))
        return None
    allowed = {
        "layout",
        "tile_pixel_size",
        "tile_merge",
        "min_static_level",
        "min_dynamic_level",
        "processed_levels",
        "version",
        "aggregate",
        "persistent",
    }
    _unknown(pyramid, allowed, "pyramid", issues)
    layout = pyramid.get("layout", "version-2-tiles")
    if layout not in {"version-2-tiles", "version-1-root"}:
        issues.append(_error("pyramid.layout", "layout", "Layout must be version-2-tiles or version-1-root."))
    if pyramid.get("tile_pixel_size", TILE_PIXEL_SIZE) != TILE_PIXEL_SIZE:
        issues.append(
            _error(
                "pyramid.tile_pixel_size",
                "tile_pixel_size",
                "The legacy PNG server uses 256 pixel tiles. Other sizes are rejected.",
            )
        )
    merge = pyramid.get("tile_merge", 1)
    if not isinstance(merge, int) or isinstance(merge, bool) or not 1 <= merge <= 64:
        issues.append(_error("pyramid.tile_merge", "tile_merge", "tile_merge must be an integer from 1 to 64."))
    for name in ("min_static_level", "min_dynamic_level"):
        value = pyramid.get(name)
        if name == "min_dynamic_level" and value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 24:
            issues.append(_error(f"pyramid.{name}", "zoom", f"{name} must be an integer zoom from 0 to 24."))
    levels = pyramid.get("processed_levels", [])
    if not isinstance(levels, list) or any(not isinstance(z, int) or isinstance(z, bool) or not 0 <= z <= 24 for z in levels):
        issues.append(_error("pyramid.processed_levels", "zooms", "processed_levels must be a list of zooms from 0 to 24."))
        levels = []
    elif len(set(levels)) != len(levels):
        issues.append(_error("pyramid.processed_levels", "zooms_duplicate", "processed_levels must be unique."))
    version = pyramid.get("version", 2.0)
    if not _is_number(version) or version <= 0:
        issues.append(_error("pyramid.version", "version", "pyramid.version must be a positive number."))
    elif version < 2 and layout == "version-2-tiles":
        issues.append(_warning("pyramid.layout", "layout_version", "version below 2 uses the legacy root layout, not tiles/."))
    elif version >= 2 and layout == "version-1-root":
        issues.append(_warning("pyramid.layout", "layout_version", "version 2 and above store PNGs under tiles/."))
    aggregate = pyramid.get("aggregate", "median")
    if aggregate not in AGGREGATES:
        issues.append(_error("pyramid.aggregate", "aggregate", "aggregate must be mean, median, or dominated."))
    if pyramid.get("persistent", True) is not True:
        issues.append(_error("pyramid.persistent", "persistent", "PNG pyramids are persistent. This registry cannot mark them disposable."))
    static_level = pyramid.get("min_static_level")
    dynamic_level = pyramid.get("min_dynamic_level")
    if isinstance(static_level, int) and isinstance(dynamic_level, int) and dynamic_level < static_level:
        issues.append(_error("pyramid.min_dynamic_level", "zoom_order", "min_dynamic_level cannot be below min_static_level."))
    if isinstance(static_level, int) and levels and static_level not in levels:
        issues.append(
            _warning(
                "pyramid.processed_levels",
                "static_not_processed",
                "min_static_level is not in processed_levels. The legacy interpolator treats processed_levels as the pre-generated zooms.",
            )
        )
    if not levels:
        issues.append(
            _blocker(
                "pyramid.processed_levels",
                "zooms_required",
                "Publish requires at least one processed zoom. Saving this draft does not generate those PNGs.",
            )
        )
    return {
        "layout": layout,
        "tile_pixel_size": TILE_PIXEL_SIZE,
        "tile_merge": merge if isinstance(merge, int) else 1,
        "min_static_level": pyramid.get("min_static_level"),
        "min_dynamic_level": pyramid.get("min_dynamic_level"),
        "processed_levels": sorted(set(levels)) if levels else [],
        "version": version if _is_number(version) else 2.0,
        "aggregate": aggregate if aggregate in AGGREGATES else "median",
        "persistent": True,
    }


def _validate_cog(cog, backend, issues):
    if backend != BACKEND_COG:
        if cog is not None:
            issues.append(_error("cog", "cog_not_used", "PNG-pyramid layers must set cog to null."))
        return None
    if not isinstance(cog, dict):
        issues.append(_blocker("cog", "cog_required", "COG layers need a cog object before publish."))
        return None
    _unknown(cog, {"block_size", "overview_levels", "href_note"}, "cog", issues)
    block = cog.get("block_size")
    overviews = cog.get("overview_levels", [])
    if (
        not isinstance(block, list)
        or len(block) != 2
        or any(not isinstance(n, int) or isinstance(n, bool) or not 64 <= n <= 4096 for n in block)
    ):
        issues.append(_blocker("cog.block_size", "block_size", "COG block_size must be two integers from 64 to 4096."))
        block = None
    elif block not in ([256, 256], [512, 512]):
        issues.append(_warning("cog.block_size", "block_size_unusual", "COG block sizes are usually 256 or 512."))
    if not isinstance(overviews, list) or any(not isinstance(z, int) or isinstance(z, bool) or z < 0 for z in overviews):
        issues.append(_error("cog.overview_levels", "overviews", "overview_levels must be a list of non-negative integers."))
        overviews = []
    note = cog.get("href_note", "Reference only. The registry does not fetch or rewrite the COG.")
    if not isinstance(note, str) or len(note) > 300:
        issues.append(_error("cog.href_note", "href_note", "href_note must be a string of at most 300 characters."))
        note = "Reference only. The registry does not fetch or rewrite the COG."
    issues.append(
        _warning(
            "backend",
            "cog_not_served",
            "The legacy map server serves PNG pyramids and does not read this COG. Registering it does not convert tiles.",
        )
    )
    return {
        "block_size": block,
        "overview_levels": sorted(set(overviews)),
        "href_note": note,
    }


def _validate_bounds(bounds, issues):
    if bounds is None:
        issues.append(_blocker("bounds", "bounds_required", "Publish requires bounds. The legacy setting.ini does not store them."))
        return None
    if not isinstance(bounds, dict):
        issues.append(_error("bounds", "bounds_type", "bounds must be an object or null."))
        return None
    _unknown(bounds, {"crs", "minx", "miny", "maxx", "maxy"}, "bounds", issues)
    crs = bounds.get("crs", "EPSG:3857")
    if crs not in {"EPSG:3857", "EPSG:4326"}:
        issues.append(_error("bounds.crs", "crs", "crs must be EPSG:3857 or EPSG:4326."))
    nums = {}
    ok = True
    for name in ("minx", "miny", "maxx", "maxy"):
        value = bounds.get(name)
        if not _is_number(value):
            issues.append(_error(f"bounds.{name}", "bounds_number", f"{name} must be a finite number."))
            ok = False
        else:
            nums[name] = float(value)
    if not ok:
        return None
    if nums["minx"] >= nums["maxx"] or nums["miny"] >= nums["maxy"]:
        issues.append(_error("bounds", "bounds_order", "min values must be less than max values."))
        return None
    if crs == "EPSG:4326":
        if not (-180 <= nums["minx"] <= 180 and -180 <= nums["maxx"] <= 180 and -90 <= nums["miny"] <= 90 and -90 <= nums["maxy"] <= 90):
            issues.append(_error("bounds", "bounds_range", "EPSG:4326 bounds are outside longitude/latitude limits."))
        issues.append(_warning("bounds.crs", "not_mercator", "The PNG pyramid is Web Mercator. EPSG:4326 bounds are informational."))
    if crs == "EPSG:3857":
        limit = WEB_MERCATOR_LIMIT + 1
        if any(abs(nums[name]) > limit for name in nums):
            issues.append(_error("bounds", "bounds_range", "EPSG:3857 bounds exceed the Web Mercator world extent."))
    return {"crs": crs, "minx": nums["minx"], "miny": nums["miny"], "maxx": nums["maxx"], "maxy": nums["maxy"]}


def _validate_style(style, issues):
    if style is None:
        style = {"type": "color-ramp", "stops": []}
    if not isinstance(style, dict):
        issues.append(_error("style", "style_type", "style must be an object."))
        return {"type": "color-ramp", "stops": []}
    _unknown(style, {"type", "stops"}, "style", issues)
    if style.get("type", "color-ramp") != "color-ramp":
        issues.append(_error("style.type", "style_type", "Only color-ramp styles are accepted in this increment."))
    stops_in = style.get("stops", [])
    stops = []
    if not isinstance(stops_in, list):
        issues.append(_error("style.stops", "stops_type", "style.stops must be a list."))
        stops_in = []
    if len(stops_in) > 256:
        issues.append(_error("style.stops", "stops_length", "A ramp may contain at most 256 stops."))
        stops_in = stops_in[:256]
    for index, stop in enumerate(stops_in):
        field = f"style.stops[{index}]"
        if not isinstance(stop, dict):
            issues.append(_error(field, "stop_type", "Each stop must be an object."))
            continue
        _unknown(stop, {"value", "rgba", "label"}, field, issues)
        value = stop.get("value")
        rgba = stop.get("rgba")
        label = stop.get("label", "")
        if not _is_number(value):
            issues.append(_error(field + ".value", "stop_value", "Stop value must be a finite number."))
            continue
        if (
            not isinstance(rgba, list)
            or len(rgba) != 4
            or any(not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 255 for channel in rgba)
        ):
            issues.append(_error(field + ".rgba", "stop_rgba", "rgba must be four integers from 0 to 255."))
            continue
        if not isinstance(label, str) or len(label) > 80:
            issues.append(_error(field + ".label", "stop_label", "label must be a string of at most 80 characters."))
            label = ""
        stops.append({"value": float(value), "rgba": list(rgba), "label": label})
    if not stops:
        issues.append(_blocker("style.stops", "style_required", "Publish requires at least one color stop."))
    return {"type": "color-ramp", "stops": stops}


def _validate_nodata(nodata, issues):
    if nodata is None:
        nodata = {}
    if not isinstance(nodata, dict):
        issues.append(_error("nodata", "nodata_type", "nodata must be an object."))
        return {"min_value": None, "max_value": None, "fill_nodata": None, "raster_nodata": None}
    _unknown(nodata, {"min_value", "max_value", "fill_nodata", "raster_nodata"}, "nodata", issues)
    out = {}
    for name in ("min_value", "max_value", "fill_nodata", "raster_nodata"):
        value = nodata.get(name)
        if value is None:
            out[name] = None
            continue
        if not _is_number(value):
            issues.append(_error(f"nodata.{name}", "nodata_number", f"{name} must be a finite number or null."))
            out[name] = None
        else:
            out[name] = float(value)
    if out.get("min_value") is not None and out.get("max_value") is not None and out["min_value"] > out["max_value"]:
        issues.append(_error("nodata", "nodata_range", "min_value cannot be greater than max_value."))
    return out


def _validate_sources(sources, issues):
    if sources is None:
        sources = []
    if not isinstance(sources, list):
        issues.append(_error("source_revisions", "sources_type", "source_revisions must be a list."))
        return []
    if len(sources) > 50:
        issues.append(_error("source_revisions", "sources_length", "At most 50 source revisions are stored."))
        sources = sources[:50]
    out = []
    seen = set()
    for index, source in enumerate(sources):
        field = f"source_revisions[{index}]"
        if not isinstance(source, dict):
            issues.append(_error(field, "source_type", "Each source revision must be an object."))
            continue
        _unknown(source, {"revision_id", "uri", "note", "recorded_at"}, field, issues)
        revision_id = source.get("revision_id")
        uri = source.get("uri")
        note = source.get("note", "")
        recorded_at = source.get("recorded_at")
        if not isinstance(revision_id, str) or not revision_id or len(revision_id) > 80:
            issues.append(_error(field + ".revision_id", "source_id", "revision_id is required and must be at most 80 characters."))
            continue
        if revision_id in seen:
            issues.append(_error(field + ".revision_id", "source_duplicate", "revision_id values must be unique."))
        seen.add(revision_id)
        uri_issue = _validate_reference_uri(uri, field + ".uri")
        if uri_issue:
            issues.append(uri_issue)
            continue
        if not isinstance(note, str) or len(note) > 500:
            issues.append(_error(field + ".note", "source_note", "note must be a string of at most 500 characters."))
            note = ""
        if not isinstance(recorded_at, str) or not _ISO.match(recorded_at):
            issues.append(_error(field + ".recorded_at", "source_time", "recorded_at must be an ISO-8601 timestamp."))
            continue
        parsed = urlparse(uri)
        if parsed.scheme in {"s3", "https"}:
            issues.append(
                _warning(
                    field + ".uri",
                    "reference_only",
                    "The URI is stored as a reference. The registry does not read it.",
                )
            )
        if parsed.scheme == "synthetic":
            issues.append(
                _warning(
                    field + ".uri",
                    "synthetic_source",
                    "Synthetic source reference. Not a production object.",
                )
            )
        out.append({"revision_id": revision_id, "uri": uri, "note": note, "recorded_at": recorded_at})
    return out


def _validate_reference_uri(uri, field):
    if not isinstance(uri, str) or not uri or len(uri) > 500:
        return _error(field, "uri", "uri is required and must be at most 500 characters.")
    denied = assert_no_denied_text(uri, field)
    if denied:
        return denied
    parsed = urlparse(uri)
    if parsed.scheme not in {"synthetic", "s3", "https"}:
        return _error(field, "uri_scheme", "uri scheme must be synthetic, s3, or https. file, http, and javascript are rejected.")
    if parsed.scheme == "https" and (not parsed.hostname or parsed.username or parsed.password):
        return _error(field, "uri_host", "https references need a host and must not embed userinfo.")
    if parsed.scheme == "s3" and (not parsed.netloc or "/" not in parsed.path):
        return _error(field, "uri_s3", "s3 references must look like s3://bucket/key.")
    return None


def _validate_template(template, tag, hosts, issues):
    if template is None or template == "":
        return None
    if not isinstance(template, str):
        issues.append(_error("authorized_tile_template", "template_type", "authorized_tile_template must be a string or null."))
        return None
    denied = assert_no_denied_text(template, "authorized_tile_template")
    if denied:
        issues.append(denied)
        return None
    parsed = urlparse(template)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        issues.append(_error("authorized_tile_template", "template_url", "A tile template must be https, without userinfo."))
        return None
    origin = f"https://{parsed.hostname}"
    if parsed.port:
        origin += f":{parsed.port}"
    allowed = {host.rstrip("/") for host in hosts}
    if origin not in allowed:
        issues.append(
            _error(
                "authorized_tile_template",
                "template_host",
                "Tile template host is not in the configured preview allowlist. The registry does not fetch it.",
            )
        )
        return None
    if tag and tag not in parsed.path:
        issues.append(
            _error(
                "authorized_tile_template",
                "template_tag",
                "Tile template path must contain the layer tag.",
            )
        )
        return None
    if "{z}" not in template or "{x}" not in template or "{y}" not in template:
        issues.append(_error("authorized_tile_template", "template_tokens", "Tile template must include {z}, {x}, and {y}."))
        return None
    return template


def _unknown(payload, allowed, field, issues):
    if not isinstance(payload, dict):
        return
    extra = sorted(set(payload) - set(allowed))
    for key in extra:
        issues.append(_error(f"{field}.{key}" if field else key, "unknown_field", f"Unknown field {key}."))


def _scan_denied(value, field, issues):
    if isinstance(value, str):
        denied = assert_no_denied_text(value, field)
        if denied:
            issues.append(denied)
    elif isinstance(value, dict):
        for key, item in value.items():
            _scan_denied(item, f"{field}.{key}" if field else key, issues)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_denied(item, f"{field}[{index}]", issues)


def validate_client_layer(payload, preview_hosts=()):
    """Return (normalized_client_dict, issues)."""
    issues = []
    if not isinstance(payload, dict):
        return {}, [_error("layer", "layer_type", "layer must be an object.")]
    _unknown(payload, CLIENT_LAYER_KEYS, "", issues)
    _scan_denied(payload, "", issues)
    tag = payload.get("tag")
    issues.extend(validate_tag(tag) if isinstance(tag, str) else [_error("tag", "tag_required", "Tag is required.")])
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        issues.append(_error("title", "title", "Title is required and must be at most 200 characters."))
        title = title if isinstance(title, str) else ""
    backend = payload.get("backend")
    if backend not in BACKENDS:
        issues.append(_error("backend", "backend", "backend must be png-pyramid or cog."))
        backend = BACKEND_PNG
    pyramid = _validate_pyramid(payload.get("pyramid"), backend, issues)
    cog = _validate_cog(payload.get("cog"), backend, issues)
    bounds = _validate_bounds(payload.get("bounds"), issues)
    style = _validate_style(payload.get("style"), issues)
    nodata = _validate_nodata(payload.get("nodata"), issues)
    sources = _validate_sources(payload.get("source_revisions"), issues)
    template = _validate_template(payload.get("authorized_tile_template"), tag if isinstance(tag, str) else "", preview_hosts, issues)
    normalized = {
        "tag": tag if isinstance(tag, str) else "",
        "title": title.strip() if isinstance(title, str) else "",
        "backend": backend if backend in BACKENDS else BACKEND_PNG,
        "pyramid": pyramid,
        "cog": cog,
        "bounds": bounds,
        "style": style,
        "nodata": nodata,
        "source_revisions": sources,
        "authorized_tile_template": template,
    }
    return normalized, issues


def structural_errors(issues):
    return [item for item in issues if item["severity"] == "error"]


def publish_blockers(issues):
    return [item for item in issues if item["severity"] == "publish_blocker"]


def warnings(issues):
    return [item for item in issues if item["severity"] == "warning"]


def digest_input(normalized):
    """Digest covers the editable catalog fields, not server metadata."""
    return content_digest(normalized)


def validation_summary(issues):
    errors = structural_errors(issues)
    blockers = publish_blockers(issues)
    return {
        "valid_for_draft": not errors,
        "valid_for_publish": not errors and not blockers,
        "errors": errors,
        "publish_blockers": blockers,
        "warnings": warnings(issues),
    }


def build_stored_record(
    normalized,
    issues,
    *,
    actor,
    now,
    revision,
    status,
    synthetic,
    inventory,
    created_at=None,
    legacy_compat=None,
):
    if status not in STATUSES:
        raise ValueError("status")
    if inventory == INVENTORY_SYNTHETIC:
        synthetic = True
    if synthetic and inventory != INVENTORY_SYNTHETIC:
        inventory = INVENTORY_SYNTHETIC
    if not synthetic:
        inventory = INVENTORY_REGISTRY
    summary = validation_summary(issues)
    record = {
        "schema": SCHEMA_ID,
        "tag": normalized["tag"],
        "title": normalized["title"],
        "status": status,
        "revision": int(revision),
        "synthetic": bool(synthetic),
        "inventory": inventory,
        "backend": normalized["backend"],
        "pyramid": normalized["pyramid"],
        "cog": normalized["cog"],
        "bounds": normalized["bounds"],
        "style": normalized["style"],
        "nodata": normalized["nodata"],
        "source_revisions": normalized["source_revisions"],
        "authorized_tile_template": normalized.get("authorized_tile_template"),
        "legacy_compat": legacy_compat
        or {
            "namespace": "geo-map.legacy-setting-ini",
            "setting": {},
            "color_txt_sha256": None,
        },
        "validation": summary,
        "registry_effects": dict(REGISTRY_EFFECTS_STORED),
        "created_at": created_at or now,
        "updated_at": now,
        "updated_by": actor,
        "content_digest": digest_input(normalized),
    }
    if record["registry_effects"]["png_pyramid_regenerated_on_write"] is not False:
        raise ValueError("registry effects flag corrupted")
    account_note = AUTHORIZED_ACCOUNT  # referenced so the guard stays next to the schema
    if not account_note:
        raise ValueError("account")
    return record


def editable_from_stored(record):
    return {
        "tag": record["tag"],
        "title": record["title"],
        "backend": record["backend"],
        "pyramid": record["pyramid"],
        "cog": record["cog"],
        "bounds": record["bounds"],
        "style": record["style"],
        "nodata": record["nodata"],
        "source_revisions": record["source_revisions"],
        "authorized_tile_template": record.get("authorized_tile_template"),
    }
