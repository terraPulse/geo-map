"""JSON HTTP API shared by the local server and API Gateway.

Every /v1 route requires an authenticated actor. The local /ready probe is
not part of this class.
"""

import json
from urllib.parse import parse_qs

from .auth import authenticate, require_writer
from .effects import effects
from .errors import LayerManagerError, PayloadTooLarge, ValidationFailed
from .preview_urls import tile_backend_status
from .schema_contract import SCHEMA_ID
from .service import LayerService

MAX_BODY = 256 * 1024

_WRITES = {
    ("POST", "/v1/layers"),
    ("PATCH", "/v1/layers/item"),
    ("POST", "/v1/layers/item/publish"),
    ("POST", "/v1/layers/import-legacy"),
    ("POST", "/v1/layers/item/restore"),
}


class Api:
    def __init__(self, service, settings):
        self.service = service
        self.settings = settings

    def handle(self, method, path, query, headers, body, apigateway_event=None, now=None):
        method = method.upper()
        path = path.split("?", 1)[0]
        if path != "/v1/session":
            # session is still authenticated; this branch only normalizes path
            pass
        try:
            if len(body or b"") > MAX_BODY:
                raise PayloadTooLarge("JSON body exceeds 256 KiB.")
            actor = authenticate(headers, apigateway_event, self.settings, now=now)
            if (method, path) in _WRITES:
                require_writer(actor)
            payload = _json_body(body) if body else {}
            status, result = self._dispatch(method, path, query, payload, actor)
            return self._respond(status, {"ok": True, "result": result}, headers)
        except LayerManagerError as exc:
            return self._respond(exc.status, exc.to_body(), headers)
        except json.JSONDecodeError:
            err = ValidationFailed("Request body is not JSON.", [])
            return self._respond(err.status, err.to_body(), headers)

    def _dispatch(self, method, path, query, payload, actor):
        if method == "GET" and path == "/v1/session":
            return 200, self._session(actor)
        if method == "GET" and path == "/v1/contract":
            return 200, {
                "schema": SCHEMA_ID,
                "effects": effects(registry_updated=False),
                "note": "Parent integrates this contract into the interfaces standards branch before shared use.",
                "tile_backend": tile_backend_status(self.settings.tile_backend_base_url, self.settings.tile_path_order),
                "preview_contract": {
                    "orders": {
                        "map": "/map/{tag}/{z}/{x}/{y}.png",
                        "zx_y": "/zx_y/{tag}/{z}/{x}/{y}.png",
                        "zxy": "/zxy/{tag}/{z}/{x}/{y}.png",
                        "xyz": "/xyz/{tag}/{x}/{y}/{z}.png",
                    },
                    "tag_encoding": "slash-preserved",
                    "remote_fetch": False,
                    "admin_authorization_sent_to_tiles": False,
                },
            }
        if method == "GET" and path == "/v1/layers":
            return 200, self.service.list_layers(
                query=query.get("q", [""])[0] if isinstance(query.get("q"), list) else query.get("q"),
                status=_one(query, "status"),
                limit=_one(query, "limit") or 100,
            )
        if method == "POST" and path == "/v1/layers/preview":
            require_writer(actor)
            return 200, self.service.preview(payload.get("layer") or payload)
        if method == "POST" and path == "/v1/layers":
            return 201, self.service.create_draft(
                payload.get("layer") or {},
                payload.get("content_digest"),
                payload.get("confirmation"),
                actor.sub,
                actor.role,
            )
        if method == "GET" and path == "/v1/layers/item":
            return 200, self.service.get_layer(_tag(query, payload))
        if method == "PATCH" and path == "/v1/layers/item":
            return 200, self.service.update_layer(
                _tag(query, payload),
                payload.get("layer") or {},
                payload.get("expected_revision"),
                actor.sub,
                actor.role,
            )
        if method == "POST" and path == "/v1/layers/item/publish":
            return 200, self.service.publish(
                _tag(query, payload),
                payload.get("expected_revision"),
                payload.get("confirmation"),
                actor.sub,
                actor.role,
            )
        if method == "POST" and path == "/v1/layers/import-legacy":
            return 201, self.service.import_legacy(
                payload.get("tag"),
                payload.get("setting"),
                payload.get("color_txt") or "",
                payload.get("confirmation"),
                actor.sub,
                actor.role,
            )
        if method == "POST" and path == "/v1/layers/export-legacy":
            return 200, self.service.export_legacy(_tag(query, payload))
        if method == "GET" and path == "/v1/layers/audit":
            return 200, self.service.list_audit(_tag(query, payload))
        if method == "POST" and path == "/v1/layers/item/restore":
            return 200, self.service.restore(
                _tag(query, payload),
                payload.get("audit_id"),
                payload.get("expected_revision"),
                payload.get("confirmation"),
                actor.sub,
                actor.role,
            )
        return 404, None

    def _session(self, actor):
        banner = (
            "Local fixture identity. Synthetic fixtures are not the live tile inventory."
            if actor.synthetic_identity
            else "Signed in through the staging Cognito pool. Records badged synthetic are fixtures."
        )
        return {
            "actor": actor.to_dict(),
            "environment": self.settings.env,
            "schema": SCHEMA_ID,
            "banner": banner,
            "effects_notice": (
                "Saving or publishing changes the registry only. Existing PNG pyramids are not regenerated."
            ),
            "signup": False,
            "tile_backend": tile_backend_status(self.settings.tile_backend_base_url, self.settings.tile_path_order),
        }

    def _respond(self, status, body, request_headers):
        if status == 404 and body.get("result", "missing") is None:
            body = {
                "ok": False,
                "error": {"code": "not_found", "message": "No such API route.", "details": []},
            }
        encoded = json.dumps(body).encode("utf-8")
        headers = {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "x-layer-manager-writes": "registry-only",
        }
        if self.settings.emit_cors:
            origin = _origin(request_headers)
            if origin and origin in self.settings.cors_origins:
                headers["access-control-allow-origin"] = origin
                headers["vary"] = "Origin"
                headers["access-control-allow-headers"] = "authorization, content-type, x-layer-manager-fixture-actor"
                headers["access-control-allow-methods"] = "GET, POST, PATCH, OPTIONS"
        return status, headers, encoded


def _json_body(body):
    if isinstance(body, (bytes, bytearray)):
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))
    if isinstance(body, str):
        if not body:
            return {}
        return json.loads(body)
    return {}


def _one(query, name):
    value = query.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _tag(query, payload):
    tag = _one(query, "tag") or (payload.get("tag") if isinstance(payload, dict) else None)
    if not tag:
        raise ValidationFailed("tag is required.", [{"field": "tag", "code": "tag_required", "message": "tag is required."}])
    return tag


def _origin(headers):
    for key, value in (headers or {}).items():
        if key.lower() == "origin":
            return value
    return None


def query_from_string(raw):
    if not raw:
        return {}
    return parse_qs(raw, keep_blank_values=False)


def build_service(repository, settings):
    return LayerService(
        repository,
        settings.effective_preview_hosts(),
        tile_backend_base_url=settings.tile_backend_base_url,
        tile_path_order=settings.tile_path_order,
    )
