"""API Gateway and CloudFormation entrypoint.

Signature checks stay with the API Gateway Cognito JWT authorizer. This
module does not create users, write tiles, or call AWS except the
CloudFormation response URL and the DynamoDB client the repository builds.
"""

from layer_manager.app_factory import build_api
from layer_manager.cfn_response import send_cfn_response
from layer_manager.seed_handler import assert_staging_stack, handle_seed_event
from layer_manager.settings import Settings

_API = None


def get_api():
    global _API
    if _API is None:
        _API = build_api(Settings.from_env())
    return _API


def handler(event, context):
    if _is_seed_event(event):
        return seed_handler(event, context)
    return api_handler(event, context)


def api_handler(event, context, api=None):
    api = api or get_api()
    request = event.get("requestContext", {}).get("http", {})
    method = request.get("method", "GET")
    path = event.get("rawPath") or request.get("path") or "/"
    headers = event.get("headers") or {}
    query = event.get("queryStringParameters") or {}
    body = event.get("body") or b""
    if event.get("isBase64Encoded") and isinstance(body, str):
        import base64

        body = base64.b64decode(body)
    status, response_headers, payload = api.handle(
        method,
        path,
        query,
        headers,
        body,
        apigateway_event=event,
    )
    return {
        "statusCode": status,
        "headers": response_headers,
        "body": payload.decode("utf-8"),
        "isBase64Encoded": False,
    }


def seed_handler(event, context, service=None):
    try:
        assert_staging_stack(event)
        service = service or get_api().service
        return handle_seed_event(event, service, send_cfn_response)
    except Exception:
        try:
            send_cfn_response(event, "FAILED", {"error": "rejected"})
        except Exception:
            return {"ok": False, "error": "rejected"}
        return {"ok": False, "error": "rejected"}


def _is_seed_event(event):
    return (
        isinstance(event, dict)
        and event.get("RequestType") in {"Create", "Update", "Delete"}
        and "ResponseURL" in event
        and "StackId" in event
    )
