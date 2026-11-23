"""Deployed handler path for renderer preview.

Settings.from_env and build_api construct the Lambda client. botocore
Stubber answers invoke. No request leaves the process.
"""

import base64
import io
import json
import os
import time
import unittest
from unittest.mock import patch

import boto3
from botocore.stub import Stubber

import support

import layer_manager_lambda
from layer_manager.png_codec import png_size
from layer_manager.renderer_preview import ALLOWED_FUNCTION_ARN, apigateway_event, fixture_adapter

POOL = "us-west-2_Example"
CLIENT = "client"


class PreviewHandlerTests(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in _ENV}
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
        os.environ["AWS_REGION"] = "us-west-2"
        os.environ["AWS_DEFAULT_REGION"] = "us-west-2"
        layer_manager_lambda._API = None

    def tearDown(self):
        layer_manager_lambda._API = None
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_handler_lists_then_returns_a_binary_png_from_the_fixed_arn(self):
        self._staging(renderer="lambda")
        dynamo = boto3.client("dynamodb", region_name="us-west-2")
        remote = boto3.client("lambda", region_name="us-west-2")
        stub = Stubber(remote)
        layer_event = apigateway_event("/tiletest/v1/layers")
        tile_event = apigateway_event("/tiletest/v1/map/fixture/demo-pyramid/2/0/0.png")
        stub.add_response("invoke", _invoke_result(fixture_adapter(layer_event)))
        stub.add_response("invoke", _invoke_result(fixture_adapter(layer_event)))
        stub.add_response("invoke", _invoke_result(fixture_adapter(tile_event)))
        stub.activate()
        created = []
        seen = []

        class Recording:
            def invoke(self, **kwargs):
                seen.append(kwargs)
                return remote.invoke(**kwargs)

        def factory(name, **kwargs):
            created.append((name, kwargs.get("region_name")))
            if name == "dynamodb":
                return dynamo
            if name == "lambda":
                self.assertEqual(kwargs.get("region_name"), "us-west-2")
                return Recording()
            raise AssertionError(name)

        with patch("boto3.client", factory):
            listed = layer_manager_lambda.handler(_event("GET", "/v1/preview/layers", claims=_claims("layer-reader")), None)
            image = layer_manager_lambda.handler(
                _event(
                    "GET",
                    "/v1/preview/tile",
                    query={"layer_id": "fixture/demo-pyramid", "z": "2", "x": "0", "y": "0", "order": "map"},
                    claims=_claims("layer-admin"),
                ),
                None,
            )
        stub.assert_no_pending_responses()
        self.assertEqual([item[0] for item in created], ["dynamodb", "lambda"])
        self.assertEqual(listed["statusCode"], 200)
        self.assertFalse(listed["isBase64Encoded"])
        document = json.loads(listed["body"])
        self.assertEqual(document["result"]["layers"][0]["id"], "fixture/demo-pyramid")
        self.assertEqual(image["statusCode"], 200)
        self.assertTrue(image["isBase64Encoded"])
        self.assertEqual(image["headers"]["content-type"], "image/png")
        blob = base64.b64decode(image["body"])
        self.assertEqual(png_size(blob), (256, 256))
        self.assertTrue(blob.startswith(b"\x89PNG"))
        self.assertEqual(len(seen), 3)
        for call in seen:
            self.assertEqual(call["FunctionName"], ALLOWED_FUNCTION_ARN)
            event = json.loads(call["Payload"].decode("utf-8"))
            self.assertEqual(event["headers"], {})
            self.assertNotIn("authorization", json.dumps(event).lower())

    def test_disabled_mode_does_not_construct_a_lambda_client(self):
        self._staging(renderer="disabled")
        created = []

        def factory(name, **kwargs):
            created.append(name)
            return boto3.client("dynamodb", region_name="us-west-2")

        real_client = boto3.client
        with patch("boto3.client", side_effect=lambda name, **kwargs: _disabled_factory(name, created, real_client, **kwargs)):
            response = layer_manager_lambda.handler(_event("GET", "/v1/preview/layers", claims=_claims("layer-admin")), None)
        self.assertNotIn("lambda", created)
        self.assertFalse(response["isBase64Encoded"])
        body = json.loads(response["body"])
        self.assertEqual(body["result"]["integration_status"], "unconfigured")
        self.assertIn("not invoked", body["result"]["note"])

    def test_auth_and_bounds_stay_on_the_handler(self):
        self._staging(renderer="disabled")
        dynamo = boto3.client("dynamodb", region_name="us-west-2")
        with patch("boto3.client", return_value=dynamo):
            anonymous = layer_manager_lambda.handler(_event("GET", "/v1/preview/layers"), None)
            layer_manager_lambda._API = None
            forbidden = layer_manager_lambda.handler(_event("GET", "/v1/preview/layers", claims=_claims(None)), None)
        self.assertEqual(anonymous["statusCode"], 401)
        self.assertFalse(anonymous["isBase64Encoded"])
        self.assertEqual(forbidden["statusCode"], 403)
        self.assertFalse(forbidden["isBase64Encoded"])

        layer_manager_lambda._API = None
        self._staging(renderer="lambda")
        remote = boto3.client("lambda", region_name="us-west-2")
        stub = Stubber(remote)
        stub.add_response("invoke", _invoke_result(fixture_adapter(apigateway_event("/tiletest/v1/layers"))))
        stub.activate()

        def factory(name, **kwargs):
            if name == "lambda":
                return remote
            return dynamo

        with patch("boto3.client", side_effect=factory):
            bounds = layer_manager_lambda.handler(
                _event(
                    "GET",
                    "/v1/preview/tile",
                    query={"layer_id": "fixture/demo-pyramid", "z": "99", "x": "0", "y": "0"},
                    claims=_claims("layer-reader"),
                ),
                None,
            )
        stub.assert_no_pending_responses()
        self.assertEqual(bounds["statusCode"], 422)
        self.assertFalse(bounds["isBase64Encoded"])
        self.assertIn("Zoom", json.loads(bounds["body"])["error"]["message"])

    def _staging(self, renderer):
        os.environ["LAYER_MANAGER_ENV"] = "staging"
        os.environ["LAYER_MANAGER_AUTH_MODE"] = "apigateway-cognito"
        os.environ["LAYER_MANAGER_REPOSITORY"] = "dynamodb"
        os.environ["LAYER_MANAGER_DYNAMODB_TABLE"] = "geo-map-layer-manager-staging-registry"
        os.environ["LAYER_MANAGER_DYNAMODB_REGION"] = "us-west-2"
        os.environ["LAYER_MANAGER_COGNITO_REGION"] = "us-west-2"
        os.environ["LAYER_MANAGER_COGNITO_USER_POOL_ID"] = POOL
        os.environ["LAYER_MANAGER_COGNITO_CLIENT_ID"] = CLIENT
        os.environ["LAYER_MANAGER_CORS_ORIGINS"] = "https://d111111abcdef8.cloudfront.net"
        os.environ["LAYER_MANAGER_RENDERER_MODE"] = renderer
        os.environ["LAYER_MANAGER_RENDERER_FUNCTION_ARN"] = ALLOWED_FUNCTION_ARN if renderer == "lambda" else ""
        os.environ["LAYER_MANAGER_BUILDS_ENABLED"] = "false"
        os.environ["LAYER_MANAGER_BUILD_EXECUTOR"] = "disabled"
        os.environ["LAYER_MANAGER_ALLOW_FIXTURE_AUTH"] = "0"
        os.environ["LAYER_MANAGER_SEED_FIXTURES"] = "0"


_ENV = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_EC2_METADATA_DISABLED",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "LAYER_MANAGER_ENV",
    "LAYER_MANAGER_AUTH_MODE",
    "LAYER_MANAGER_REPOSITORY",
    "LAYER_MANAGER_DYNAMODB_TABLE",
    "LAYER_MANAGER_DYNAMODB_REGION",
    "LAYER_MANAGER_COGNITO_REGION",
    "LAYER_MANAGER_COGNITO_USER_POOL_ID",
    "LAYER_MANAGER_COGNITO_CLIENT_ID",
    "LAYER_MANAGER_CORS_ORIGINS",
    "LAYER_MANAGER_RENDERER_MODE",
    "LAYER_MANAGER_RENDERER_FUNCTION_ARN",
    "LAYER_MANAGER_BUILDS_ENABLED",
    "LAYER_MANAGER_BUILD_EXECUTOR",
    "LAYER_MANAGER_ALLOW_FIXTURE_AUTH",
    "LAYER_MANAGER_SEED_FIXTURES",
)


def _disabled_factory(name, created, real_client, **kwargs):
    created.append(name)
    if name == "lambda":
        raise AssertionError("disabled mode constructed a Lambda client")
    return real_client("dynamodb", region_name="us-west-2")


def _claims(group):
    claims = {
        "iss": f"https://cognito-idp.us-west-2.amazonaws.com/{POOL}",
        "aud": CLIENT,
        "token_use": "access",
        "exp": str(int(time.time()) + 600),
        "sub": "user-sub",
        "username": "operator",
    }
    if group:
        claims["cognito:groups"] = group
    return claims


def _event(method, path, query=None, claims=None):
    context = {"http": {"method": method, "path": path}}
    if claims is not None:
        context["authorizer"] = {"jwt": {"claims": claims}}
    return {
        "version": "2.0",
        "rawPath": path,
        "headers": {"authorization": "Bearer admin-token-must-not-be-forwarded"},
        "queryStringParameters": query,
        "requestContext": context,
        "isBase64Encoded": False,
    }


def _invoke_result(document):
    return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(document).encode("utf-8"))}


if __name__ == "__main__":
    unittest.main()
