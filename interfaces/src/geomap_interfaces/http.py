"""WSGI application for discovery, TileJSON, tiles, WMS, and numeric reads.

The application does not bind a socket. Tests and a host process call it.
Legacy ``/map/...`` URLs are not registered here.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

from .auth import ANONYMOUS, Principal, can_read
from .catalog import asset_bytes, asset_record, detail_record, links, list_records, tilejson
from .errors import InterfaceError, WmsError
from .pyramid import encode_png, render_xyz
from .runtime import Runtime
from .values import point_value, window_stats
from .wms import exception_xml, handle_wms

_TILE = re.compile(r"^(?P<id>.+)/tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)\.png$")
_TILEJSON = re.compile(r"^(?P<id>.+)/tilejson$")
_ASSET_CONTENT = re.compile(r"^(?P<id>.+)/assets/(?P<asset>[^/]+)/content$")
_ASSET = re.compile(r"^(?P<id>.+)/assets/(?P<asset>[^/]+)$")
_ASSETS = re.compile(r"^(?P<id>.+)/assets$")
_VALUE = re.compile(r"^(?P<id>.+)/value$")
_STATS = re.compile(r"^(?P<id>.+)/stats$")
_DETAIL = re.compile(r"^(?P<id>[^/]+(?:/[^/]+)*)$")


def build_app(runtime: Runtime):
    def app(environ, start_response):
        status, headers, body = _dispatch(runtime, environ)
        start_response(status, headers)
        return [body]

    return app


def _dispatch(runtime: Runtime, environ) -> tuple[str, list[tuple[str, str]], bytes]:
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO") or "/"
    if method != "GET":
        return _json_error(InterfaceError("method_not_allowed", "Only GET is implemented", 405), ANONYMOUS)
    try:
        if path == "/interfaces/wms":
            return _wms(runtime, environ)
        principal = _principal(environ, runtime)
        if path == "/interfaces/health":
            return _json(
                {
                    "status": "ok",
                    "interfaces": ["discovery", "tilejson", "wms-1.3.0", "mcp"],
                    "wms": "1.3.0",
                    "conformance": "provisional-not-certified",
                },
                principal,
            )
        if path == "/interfaces/datasets":
            return _json(list_records(runtime, principal), principal)
        if path.startswith("/interfaces/datasets/"):
            return _dataset(runtime, principal, path[len("/interfaces/datasets/") :], environ)
        raise InterfaceError("not_found", "No such interface route", 404)
    except InterfaceError as exc:
        return _json_error(exc, ANONYMOUS)


def _wms(runtime: Runtime, environ) -> tuple[str, list[tuple[str, str]], bytes]:
    try:
        principal = _principal(environ, runtime)
    except InterfaceError as exc:
        error = WmsError("AccessDenied", "authorization failed", exc.status)
        body = exception_xml(error)
        return _status(exc.status), _headers("text/xml; charset=utf-8", body, ANONYMOUS), body
    status, content_type, body = handle_wms(runtime, principal, environ.get("QUERY_STRING") or "")
    return _status(status), _headers(content_type, body, principal), body


def _dataset(runtime: Runtime, principal: Principal, rest: str, environ) -> tuple[str, list[tuple[str, str]], bytes]:
    matched = _match(rest)
    if matched is None:
        raise InterfaceError("not_found", "unknown dataset", 404)
    kind, dataset_id, extra = matched
    dataset = _authorized(runtime, principal, dataset_id)
    if kind == "detail":
        return _json(detail_record(runtime, dataset), principal)
    if kind == "tilejson":
        return _json(tilejson(runtime, dataset), principal)
    if kind == "assets":
        return _json({"assets": [asset_record(runtime, dataset, asset) for asset in dataset.assets]}, principal)
    if kind == "asset":
        asset = _asset(dataset, extra["asset"])
        return _json(asset_record(runtime, dataset, asset), principal)
    if kind == "asset_content":
        asset = _asset(dataset, extra["asset"])
        media, body = asset_bytes(runtime, dataset, asset)
        return _status(200), _headers(media, body, principal), body
    if kind == "value":
        query = _single_query(environ)
        return _json(point_value(runtime.data_root, dataset, _float(query, "lon"), _float(query, "lat"), runtime.budgets), principal)
    if kind == "stats":
        query = _single_query(environ)
        return _json(
            window_stats(
                runtime.data_root,
                dataset,
                _float(query, "west"),
                _float(query, "south"),
                _float(query, "east"),
                _float(query, "north"),
                runtime.budgets,
            ),
            principal,
        )
    if kind == "tile":
        image = render_xyz(dataset, runtime.store, int(extra["z"]), int(extra["x"]), int(extra["y"]), runtime.budgets)
        body = encode_png(image)
        return _status(200), _headers("image/png", body, principal), body
    raise InterfaceError("not_found", "unknown dataset", 404)


def _authorized(runtime: Runtime, principal: Principal, dataset_id: str) -> object:
    from .paths import dataset_id_error

    if dataset_id_error(dataset_id):
        raise InterfaceError("not_found", "unknown dataset", 404)
    dataset = runtime.registry.get(dataset_id)
    if dataset is None:
        raise InterfaceError("not_found", "unknown dataset", 404)
    if not can_read(dataset.access, principal):
        raise InterfaceError("forbidden", "principal cannot read this dataset", 403)
    return dataset


def _asset(dataset, asset_id: str):
    for asset in dataset.assets:
        if asset.id == asset_id:
            return asset
    raise InterfaceError("not_found", "unknown asset", 404)


def _match(rest: str):
    for pattern, kind in (
        (_TILE, "tile"),
        (_TILEJSON, "tilejson"),
        (_ASSET_CONTENT, "asset_content"),
        (_ASSET, "asset"),
        (_ASSETS, "assets"),
        (_VALUE, "value"),
        (_STATS, "stats"),
        (_DETAIL, "detail"),
    ):
        found = pattern.fullmatch(rest)
        if found:
            return kind, found.group("id"), found.groupdict()
    return None


def _principal(environ, runtime: Runtime) -> Principal:
    header = environ.get("HTTP_AUTHORIZATION")
    if not header:
        return ANONYMOUS
    scheme, _, token = header.partition(" ")
    if scheme != "Bearer" or not token or " " in token:
        raise InterfaceError("unauthorized", "Authorization must be a Bearer token", 401)
    principal = runtime.tokens.get(token)
    if principal is None:
        raise InterfaceError("unauthorized", "Unknown bearer token", 401)
    return principal


def _single_query(environ) -> dict[str, str]:
    parsed = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
    values: dict[str, str] = {}
    for key, items in parsed.items():
        if len(items) != 1:
            raise InterfaceError("invalid_request", "duplicate query parameter", 400)
        values[key] = items[0]
    return values


def _float(query: dict[str, str], name: str) -> float:
    if name not in query or query[name] == "":
        raise InterfaceError("invalid_request", f"{name} is required", 400)
    try:
        value = float(query[name])
    except ValueError as exc:
        raise InterfaceError("invalid_request", f"{name} must be a number", 400) from exc
    if value != value or value in {float("inf"), float("-inf")}:
        raise InterfaceError("invalid_request", f"{name} must be finite", 400)
    return value


def _json(payload: dict, principal: Principal):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _status(200), _headers("application/json; charset=utf-8", body, principal), body


def _json_error(exc: InterfaceError, principal: Principal):
    body = json.dumps({"error": {"code": exc.code, "message": exc.message}}, ensure_ascii=False).encode("utf-8")
    return _status(exc.status), _headers("application/json; charset=utf-8", body, principal), body


def _status(code: int) -> str:
    text = {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        500: "Internal Server Error",
        501: "Not Implemented",
    }
    return f"{code} {text.get(code, 'Error')}"


def _headers(content_type: str, body: bytes, principal: Principal) -> list[tuple[str, str]]:
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ]
    if principal.anonymous:
        headers.append(("Access-Control-Allow-Origin", "*"))
    return headers


# Re-exported for callers that want the link map without going through WSGI.
dataset_links = links
