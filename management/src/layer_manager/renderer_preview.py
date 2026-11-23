"""Preview tiles by invoking the isolated test function, or not at all.

The browser never receives the function URL, a signing key, or the admin
token inside the renderer event. Disabled mode returns an explicit
unconfigured status and does not call AWS.
"""

import base64
import json

from .errors import ConfigurationError, Conflict, ValidationFailed
from .png_codec import encode_rgba, png_size

ALLOWED_FUNCTION_ARN = "arn:aws:lambda:us-west-2:544020760996:function:geomap-tile-pyramid-test"
ADAPTER = "geomap.png_pyramid"
ADAPTER_VERSION = "1.0.0"
API_PREFIX = "/tiletest/v1"
MAX_DECODED = 2_000_000
MAX_ZOOM = 24
ORDERS = ("map", "zx_y", "zxy", "xyz")


def validate_function_arn(arn):
    if arn != ALLOWED_FUNCTION_ARN:
        raise ConfigurationError(
            "Renderer invoke is limited to function geomap-tile-pyramid-test in account 544020760996."
        )


def lambda_client_from_config(settings):
    """Build the Lambda client used by the deployed entrypoint. No invoke happens here."""
    validate_function_arn(settings.renderer_function_arn)
    if settings.authorized_region != "us-west-2":
        raise ConfigurationError("Renderer invoke region must be us-west-2. No AWS call was made.")
    import boto3
    from botocore.config import Config

    return boto3.client(
        "lambda",
        region_name="us-west-2",
        config=Config(connect_timeout=2, read_timeout=8, retries={"max_attempts": 2}),
    )


def apigateway_event(path):
    if not isinstance(path, str) or len(path) > 1024 or not path.startswith(API_PREFIX + "/"):
        raise ValidationFailed("Renderer path is not allowed.", [])
    if ".." in path or "\\" in path or "://" in path or "?" in path:
        raise ValidationFailed("Renderer path is not allowed.", [])
    return {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {},
        "isBase64Encoded": False,
        "requestContext": {"http": {"method": "GET", "path": path}},
    }


def tile_path(order, layer_id, z, x, y):
    if order not in ORDERS:
        raise ValidationFailed("Tile order is not supported.", [])
    if order == "xyz":
        return f"{API_PREFIX}/xyz/{layer_id}/{x}/{y}/{z}.png"
    return f"{API_PREFIX}/{order}/{layer_id}/{z}/{x}/{y}.png"


class RendererPreview:
    def __init__(self, settings, invoker=None):
        self.settings = settings
        self.invoker = invoker

    def status(self):
        mode = self.settings.renderer_mode
        enabled = mode in {"lambda", "fixture-offline"}
        return {
            "integration_status": "unconfigured" if not enabled else mode,
            "enabled": enabled,
            "pending": not enabled,
            "mode": mode,
            "adapter": ADAPTER,
            "adapter_version": ADAPTER_VERSION,
            "function_configured": mode == "lambda",
            "function_arn_public": ALLOWED_FUNCTION_ARN if mode == "lambda" else None,
            "function_url_used": False,
            "admin_token_forwarded": False,
            "aws_invoked_by_this_process": False,
            "note": _note(mode),
        }

    def list_layers(self):
        if self.settings.renderer_mode == "disabled":
            body = self.status()
            body["layers"] = []
            body["fixture_only"] = None
            return body
        document = self._call(API_PREFIX + "/layers")
        layers = document.get("layers") if isinstance(document, dict) else None
        if document.get("adapter") != ADAPTER or document.get("adapter_version") != ADAPTER_VERSION:
            raise ValidationFailed("Renderer allowlist is not geomap.png_pyramid 1.0.0.", [])
        if not isinstance(layers, list):
            raise ValidationFailed("Renderer allowlist did not include layers.", [])
        clean = []
        for layer in layers:
            if not isinstance(layer, dict) or not isinstance(layer.get("id"), str):
                continue
            clean.append(
                {
                    "id": layer["id"],
                    "title": str(layer.get("title") or layer["id"])[:200],
                    "fixture": bool(layer.get("fixture")),
                    "max_zoom": layer.get("max_zoom"),
                    "processed_levels": layer.get("processed_levels") or [],
                    "tile_merge": layer.get("tile_merge"),
                    "real_s3_build": False,
                }
            )
        return {
            **self.status(),
            "layers": clean,
            "fixture_only": all(layer["fixture"] for layer in clean) if clean else True,
            "source_raster_reads": False,
        }

    def tile(self, layer_id, z, x, y, order="map"):
        listing = self.list_layers()
        if not listing["enabled"]:
            raise Conflict("Renderer preview is unconfigured. The test function was not invoked.", [])
        allowed = {layer["id"]: layer for layer in listing["layers"]}
        layer = allowed.get(layer_id)
        if layer is None:
            raise ValidationFailed("That layer is not in the renderer allowlist.", [])
        self._indexes(layer, z, x, y)
        path = tile_path(order, layer_id, z, x, y)
        blob, meta = self._call_png(path)
        size = png_size(blob)
        if size != (256, 256):
            raise ValidationFailed("Renderer PNG is not a 256 by 256 image.", [])
        return blob, {
            "source": listing["mode"],
            "fixture": layer["fixture"],
            "real_s3_build": False,
            "registry_publish": False,
            "layer_id": layer_id,
            "adapter": meta.get("adapter") or ADAPTER,
        }

    def _indexes(self, layer, z, x, y):
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (z, x, y)):
            raise ValidationFailed("z, x, and y must be integers.", [])
        cap = layer.get("max_zoom")
        limit = MAX_ZOOM if not isinstance(cap, int) else min(cap, MAX_ZOOM)
        if z < 0 or z > limit:
            raise ValidationFailed("Zoom is outside the renderer allowlist.", [])
        span = 2 ** z
        if x < 0 or y < 0 or x >= span or y >= span:
            raise ValidationFailed("Tile index is outside the zoom.", [])

    def _call(self, path):
        event = apigateway_event(path)
        payload = self._invoke(event)
        if payload.get("statusCode") != 200 or payload.get("isBase64Encoded"):
            raise ValidationFailed("Renderer did not return a JSON allowlist.", [])
        body = payload.get("body") or ""
        if len(body) > 200_000:
            raise ValidationFailed("Renderer allowlist is too large.", [])
        return json.loads(body)

    def _call_png(self, path):
        event = apigateway_event(path)
        payload = self._invoke(event)
        if payload.get("statusCode") != 200 or not payload.get("isBase64Encoded"):
            raise ValidationFailed("Renderer did not return a base64 PNG.", [])
        raw = base64.b64decode(payload.get("body") or "", validate=True)
        if len(raw) > MAX_DECODED:
            raise ValidationFailed("Renderer PNG exceeds the size limit.", [])
        headers = {str(key).lower(): value for key, value in (payload.get("headers") or {}).items()}
        if headers.get("content-type") != "image/png":
            raise ValidationFailed("Renderer response is not image/png.", [])
        return raw, {"adapter": headers.get("x-geomap-adapter")}

    def _invoke(self, event):
        if any(str(key).lower() in {"authorization", "cookie", "x-tile-test-token"} for key in event.get("headers") or {}):
            raise ValidationFailed("Renderer event must not carry admin credentials.", [])
        mode = self.settings.renderer_mode
        if mode == "fixture-offline":
            return fixture_adapter(event)
        if mode != "lambda":
            raise Conflict("Renderer preview is unconfigured. The test function was not invoked.", [])
        validate_function_arn(self.settings.renderer_function_arn)
        if self.invoker is None:
            raise Conflict("Renderer invoke client is not configured. No AWS call was made.", [])
        try:
            response = self.invoker.invoke(
                FunctionName=ALLOWED_FUNCTION_ARN,
                InvocationType="RequestResponse",
                Payload=json.dumps(event).encode("utf-8"),
            )
        except Exception as exc:
            raise Conflict("Renderer invoke failed. No tile was returned.", []) from exc
        if response.get("FunctionError"):
            raise Conflict("Renderer function returned an error. No tile was returned.", [])
        payload = response.get("Payload")
        raw = payload.read() if hasattr(payload, "read") else payload
        if not isinstance(raw, (bytes, bytearray)):
            raw = str(raw or "").encode("utf-8")
        if len(raw) > MAX_DECODED + 10_000:
            raise ValidationFailed("Renderer payload exceeds the size limit.", [])
        return json.loads(raw.decode("utf-8"))


def fixture_adapter(event):
    """Offline stand-in for geomap.png_pyramid 1.0.0. Not a Lambda invoke."""
    path = event["rawPath"]
    if path == API_PREFIX + "/layers":
        body = {
            "adapter": ADAPTER,
            "adapter_version": ADAPTER_VERSION,
            "fixture_only_by_default": True,
            "source_raster_reads": False,
            "layers": [
                {
                    "id": "fixture/demo-pyramid",
                    "title": "Packaged demo pyramid",
                    "fixture": True,
                    "storage": "package",
                    "tile_merge": 2,
                    "tile_size": 256,
                    "version": 2,
                    "processed_levels": [2],
                    "max_zoom": 8,
                    "tile_path": API_PREFIX + "/{order}/fixture/demo-pyramid/{z}/{x}/{y}.png",
                }
            ],
        }
        return {"statusCode": 200, "headers": {"content-type": "application/json", "x-geomap-adapter": ADAPTER}, "isBase64Encoded": False, "body": json.dumps(body)}
    if path.startswith(API_PREFIX + "/map/fixture/demo-pyramid/"):
        png = encode_rgba(256, 256, (70, 130, 180, 255))
        return {
            "statusCode": 200,
            "headers": {"content-type": "image/png", "x-geomap-adapter": ADAPTER, "x-geomap-tile": "tile"},
            "isBase64Encoded": True,
            "body": base64.b64encode(png).decode("ascii"),
        }
    return {
        "statusCode": 403,
        "headers": {"content-type": "application/json", "x-geomap-adapter": ADAPTER},
        "isBase64Encoded": False,
        "body": json.dumps({"status": "error", "error_message": "layer is not in the test allowlist", "adapter": ADAPTER}),
    }


def _note(mode):
    if mode == "disabled":
        return "Renderer preview is unconfigured. geomap-tile-pyramid-test is not invoked."
    if mode == "fixture-offline":
        return "Offline fixture adapter. This is not a live Lambda invoke and not an S3 tile build."
    return "The admin API invokes geomap-tile-pyramid-test by ARN. The browser does not call the function URL."
