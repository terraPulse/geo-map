import json
import unittest

import support

from layer_manager_lambda import api_handler

CONSOLE = "https://d1p7xtlh8zwywg.cloudfront.net"


def api():
    return support.api(support.local_settings(cors_origins=(CONSOLE,), emit_cors=False))


def preflight(api_obj, path, origin, method, headers):
    request_headers = {
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": headers,
    }
    return api_obj.handle("OPTIONS", path, {}, request_headers, b"")


class PreflightTests(unittest.TestCase):
    def test_full_browser_preflight_is_2xx_for_exact_console_origin(self):
        app = api()
        for path in ("/v1/layers", "/v1/layers/item"):
            for method in ("GET", "POST", "PATCH"):
                status, headers, body = preflight(app, path, CONSOLE, method, "authorization,content-type")
                self.assertEqual(status, 204, path)
                self.assertEqual(body, b"")
                self.assertEqual(headers["access-control-allow-origin"], CONSOLE)
                self.assertIn("GET", headers["access-control-allow-methods"])
                self.assertIn("authorization", headers["access-control-allow-headers"])
                self.assertNotIn(b"layers", body)

    def test_bad_origin_and_plain_options_do_not_grant_cors(self):
        app = api()
        status, headers, body = preflight(app, "/v1/layers", "https://evil.example", "GET", "authorization")
        self.assertEqual(status, 403)
        self.assertNotIn("access-control-allow-origin", headers)
        self.assertNotIn(b"evil.example", body)
        status, headers, _ = app.handle("OPTIONS", "/v1/layers", {}, {}, b"")
        self.assertEqual(status, 403)
        self.assertNotIn("access-control-allow-origin", headers)

    def test_disallowed_request_header_is_rejected(self):
        app = api()
        status, headers, _ = preflight(app, "/v1/layers", CONSOLE, "GET", "authorization,x-evil")
        self.assertEqual(status, 403)
        self.assertNotIn("access-control-allow-origin", headers)

    def test_anonymous_get_and_post_stay_401(self):
        app = api()
        for method, path in (("GET", "/v1/layers"), ("POST", "/v1/layers"), ("POST", "/v1/layers/item/publish")):
            status, headers, body = support.call(
                app,
                method,
                path,
                {} if method == "POST" else None,
                actor=None,
                headers={"Origin": CONSOLE},
            )
            self.assertEqual(status, 401, path)
            self.assertNotIn("layers", json.dumps(body.get("result", "")))

    def test_lambda_event_preflight_does_not_require_authorizer(self):
        app = api()
        response = api_handler(
            {
                "rawPath": "/v1/layers",
                "headers": {
                    "origin": CONSOLE,
                    "access-control-request-method": "GET",
                    "access-control-request-headers": "authorization,content-type",
                },
                "requestContext": {"http": {"method": "OPTIONS", "path": "/v1/layers"}},
            },
            None,
            api=app,
        )
        self.assertEqual(response["statusCode"], 204)
        self.assertEqual(response["headers"]["access-control-allow-origin"], CONSOLE)
        self.assertEqual(response["body"], "")
        denied = api_handler(
            {
                "rawPath": "/v1/layers",
                "headers": {"origin": CONSOLE},
                "requestContext": {"http": {"method": "GET", "path": "/v1/layers"}},
            },
            None,
            api=app,
        )
        self.assertEqual(denied["statusCode"], 401)


if __name__ == "__main__":
    unittest.main()
