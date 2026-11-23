"""Pure API Gateway HTTP API v2 adapter. It does not call AWS."""

from __future__ import annotations

import base64
import io

from .http import build_app
from .runtime import Runtime


def apigateway_v2_handler(runtime: Runtime, event: dict, context=None) -> dict:
    del context
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "GET")
    path = event.get("rawPath") or "/"
    headers = {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(raw_body)
    elif isinstance(raw_body, str):
        body = raw_body.encode("utf-8")
    else:
        body = raw_body
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": event.get("rawQueryString") or "",
        "SERVER_NAME": "interfaces.local",
        "SERVER_PORT": "443",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "https",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(),
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.multiprocess": False,
        "wsgi.multithread": False,
        "wsgi.run_once": True,
    }
    if "authorization" in headers:
        environ["HTTP_AUTHORIZATION"] = headers["authorization"]
    captured: dict = {}

    def start_response(status, response_headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = response_headers

    payload = b"".join(build_app(runtime)(environ, start_response))
    content_type = "application/octet-stream"
    response_headers = {}
    for key, value in captured.get("headers", []):
        response_headers[key] = value
        if key.lower() == "content-type":
            content_type = value
    binary = content_type.split(";", 1)[0] == "image/png"
    return {
        "statusCode": int(captured["status"].split(" ", 1)[0]),
        "headers": response_headers,
        "isBase64Encoded": binary,
        "body": base64.b64encode(payload).decode("ascii") if binary else payload.decode("utf-8"),
    }
