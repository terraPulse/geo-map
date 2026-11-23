"""Local server for the registry UI and API. Not used in AWS."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .fixtures_seed import seed_missing
from .http_api import Api

UI_ROOT = Path(__file__).resolve().parents[2] / "ui"
_CONTENT = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


def config_javascript(settings):
    payload = {
        "authMode": settings.auth_mode,
        "environment": settings.env,
        "apiBase": "",
        "syntheticFixtures": bool(settings.seed_fixtures),
        "signup": False,
        "cognito": None,
        "effectsNotice": "Saving or publishing changes the registry only. Existing PNG pyramids are not regenerated.",
    }
    return "window.LAYER_MANAGER_CONFIG = " + json.dumps(payload, indent=2) + ";\n"


class LocalHandler(BaseHTTPRequestHandler):
    api: Api = None
    settings = None

    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route()

    def do_PATCH(self):
        self._route()

    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        if origin and origin in self.settings.cors_origins:
            self.send_response(204)
            self.send_header("access-control-allow-origin", origin)
            self.send_header("access-control-allow-headers", "authorization, content-type, x-layer-manager-fixture-actor")
            self.send_header("access-control-allow-methods", "GET, POST, PATCH, OPTIONS")
            self.send_header("vary", "Origin")
            self.end_headers()
            return
        self.send_response(403)
        self.end_headers()

    def log_message(self, fmt, *args):
        # Avoid writing request lines that can carry bearer tokens.
        return

    def _route(self):
        parts = urlsplit(self.path)
        path = parts.path
        if path == "/ready":
            body = b'{"ok":true,"service":"layer-manager"}'
            self._send(200, "application/json; charset=utf-8", body)
            return
        if path == "/config.js":
            self._send(200, "text/javascript; charset=utf-8", config_javascript(self.settings).encode("utf-8"))
            return
        if path.startswith("/v1/"):
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b""
            status, headers, payload = self.api.handle(
                self.command,
                path,
                _query(parts.query),
                {key: value for key, value in self.headers.items()},
                raw,
            )
            self._send(status, headers.get("content-type", "application/json"), payload, headers)
            return
        self._static(path)

    def _static(self, path):
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        if relative == "config.js" or ".." in relative.split("/"):
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        file_path = (UI_ROOT / relative).resolve()
        if UI_ROOT.resolve() not in file_path.parents and file_path != UI_ROOT.resolve():
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        if not file_path.is_file():
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return
        content_type = _CONTENT.get(file_path.suffix, "application/octet-stream")
        self._send(200, content_type, file_path.read_bytes())

    def _send(self, status, content_type, payload, extra=None):
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        self.send_header("x-content-type-options", "nosniff")
        if extra:
            for key, value in extra.items():
                if key.lower() != "content-type":
                    self.send_header(key, value)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _query(raw):
    from urllib.parse import parse_qs

    return parse_qs(raw, keep_blank_values=False)


def make_server(settings, api, port=8765):
    handler = type("BoundHandler", (LocalHandler,), {"api": api, "settings": settings})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    return server


def prepare_local(settings, api):
    if settings.env == "local" and settings.seed_fixtures:
        seed_missing(api.service, actor="fixture-seed", role="layer-admin")
    if settings.env == "local" and settings.build_executor == "fixture-offline" and api.builds is not None:
        import threading
        import time

        def _pump():
            while True:
                try:
                    api.builds.run_once()
                except Exception:
                    pass
                time.sleep(0.2)

        threading.Thread(target=_pump, name="fixture-build-worker", daemon=True).start()
    return api
