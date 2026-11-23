"""CloudFormation custom-resource responses.

The response URL is posted only when it is an AWS CloudFormation response
endpoint. Layer records are not included in the body.
"""

import json
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("custom-resource response redirect refused")


def response_host_allowed(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and "cloudformation-custom-resource-response" in host
        and host.endswith(".amazonaws.com")
        and parsed.username is None
    )


def send_cfn_response(event, status, data, opener=None):
    url = event.get("ResponseURL", "")
    if not response_host_allowed(url):
        raise ValueError("Refusing to post a custom-resource response to a non-AWS URL.")
    body = {
        "Status": status,
        "Reason": "layer-manager seed",
        "PhysicalResourceId": event.get("PhysicalResourceId") or "synthetic-fixtures-v1",
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "NoEcho": True,
        "Data": {key: str(value) for key, value in data.items()},
    }
    raw = json.dumps(body).encode("utf-8")
    request = Request(url, data=raw, method="PUT")
    request.add_header("content-type", "")
    opener = opener or build_opener(_RejectRedirect)
    with opener.open(request, timeout=5) as response:
        response.read()
    return body
