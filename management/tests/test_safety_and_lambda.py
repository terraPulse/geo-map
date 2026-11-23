import ast
import json
import threading
import unittest
import urllib.request
from pathlib import Path

import support

from layer_manager.cfn_response import response_host_allowed
from layer_manager.seed_handler import handle_seed_event
from layer_manager_lambda import api_handler


SRC = Path(__file__).resolve().parents[1] / "src"
BANNED = {
    "urlopen",
    "urlretrieve",
    "put_object",
    "delete_object",
    "upload_file",
    "admin_create_user",
    "send_email",
    "Popen",
    "system",
}


class SafetyTests(unittest.TestCase):
    def test_sources_do_not_fetch_or_write_tiles(self):
        for path in SRC.rglob("*.py"):
            if path.name in {"cfn_response.py", "layer_manager_lambda.py"}:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = self._name(node.func)
                    self.assertNotIn(name, BANNED, f"{path.name} calls {name}")

    def test_response_url_is_restricted(self):
        self.assertTrue(
            response_host_allowed(
                "https://cloudformation-custom-resource-response-uswest2.s3.us-west-2.amazonaws.com/arn"
            )
        )
        self.assertFalse(response_host_allowed("https://evil.example/collect"))
        self.assertFalse(response_host_allowed("http://cloudformation-custom-resource-response.s3.amazonaws.com/x"))

    def test_seed_is_idempotent_and_reports_counts_only(self):
        api = support.api()
        sent = {}

        def send(event, status, data):
            sent["status"] = status
            sent["data"] = data

        event = {
            "RequestType": "Create",
            "StackId": "arn:aws:cloudformation:us-west-2:544020760996:stack/geo-map-layer-manager-staging/abc",
            "RequestId": "r1",
            "LogicalResourceId": "SyntheticSeed",
            "ResponseURL": "https://cloudformation-custom-resource-response-uswest2.s3.us-west-2.amazonaws.com/x",
            "ResourceProperties": {"SeedSyntheticFixtures": "true"},
        }
        result = handle_seed_event(event, api.service, send)
        self.assertEqual(len(result["inserted"]), 3)
        self.assertEqual(sent["data"]["Inserted"], 3)
        self.assertNotIn("tag", sent["data"])
        again = handle_seed_event(dict(event, RequestType="Update"), api.service, send)
        self.assertEqual(again["inserted"], [])
        self.assertEqual(len(again["skipped"]), 3)
        deleted = handle_seed_event(dict(event, RequestType="Delete"), api.service, send)
        self.assertFalse(deleted["deleted"])
        self.assertIsNotNone(api.service.repository.get("demo/water_freq/y2025"))

    def _name(self, func):
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return ""


class LambdaTests(unittest.TestCase):
    def test_missing_authorizer_is_401(self):
        api = support.api(support.staging_settings())
        response = api_handler(
            {"requestContext": {"http": {"method": "GET", "path": "/v1/layers"}}, "rawPath": "/v1/layers"},
            None,
            api=api,
        )
        self.assertEqual(response["statusCode"], 401)
        self.assertNotIn("authorization", json.dumps(response["headers"]).lower())

    def test_local_server_round_trip(self):
        from layer_manager.local_server import make_server, prepare_local

        settings = support.local_settings(env="local", seed_fixtures=True, file_root=None, repository="memory")
        api = support.api(settings)
        prepare_local(settings, api)
        server = make_server(settings, api, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            base = f"http://127.0.0.1:{port}"
            ready = urllib.request.urlopen(base + "/ready", timeout=5)
            self.assertEqual(ready.status, 200)
            request = urllib.request.Request(
                base + "/v1/layers?q=water",
                headers={"x-layer-manager-fixture-actor": "fixture-admin"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(body["result"]["layers"][0]["synthetic"], True)
            page = urllib.request.urlopen(base + "/", timeout=5)
            html = page.read().decode("utf-8")
            self.assertIn("do not regenerate PNG", html)
            self.assertIn('id: "layer-search"', (support.ROOT / "ui" / "app.js").read_text(encoding="utf-8"))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
