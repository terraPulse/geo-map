import io
import json
import tempfile
import unittest

import support

from layer_manager.build_jobs import BuildService, MemoryBuildStore
from layer_manager.errors import Conflict
from layer_manager.png_codec import png_size
from layer_manager.renderer_preview import ALLOWED_FUNCTION_ARN, RendererPreview, apigateway_event
from layer_manager.repository import MemoryRepository
from layer_manager.schema_contract import CONFIRM_PUBLISH, CONFIRM_QUEUE_BUILD
from layer_manager.service import LayerService


def fixture_settings():
    return support.local_settings(build_executor="fixture-offline", renderer_mode="fixture-offline", builds_enabled=False)


def service(settings=None):
    settings = settings or fixture_settings()
    layers = LayerService(MemoryRepository())
    with tempfile.TemporaryDirectory() as tmp:
        yield settings, BuildService(MemoryBuildStore(), settings, layers, tmp), tmp


class BuildTests(unittest.TestCase):
    def test_fixture_job_writes_a_png_and_is_not_s3(self):
        settings = fixture_settings()
        layers = LayerService(MemoryRepository())
        with tempfile.TemporaryDirectory() as tmp:
            builds = BuildService(MemoryBuildStore(), settings, layers, tmp)
            plan = builds.plan({"source_id": "fixture-demo", "tag": "demo/built/fixture", "zooms": [2], "tile_merge": 1})
            self.assertTrue(plan["approximate"])
            self.assertEqual(plan["tile_count"], 1)
            self.assertTrue(plan["submittable"])
            queued = builds.submit(self._body(), "admin", "layer-admin")["job"]
            self.assertEqual(queued["status"], "queued")
            self.assertFalse(queued["real_s3_write"])
            finished = builds.run_once()
            self.assertEqual(finished["status"], "succeeded")
            self.assertEqual(finished["execution_mode"], "fixture-offline")
            self.assertEqual(finished["progress"]["completed_tiles"], 1)
            self.assertFalse(finished["real_s3_write"])
            self.assertTrue(finished["output_validation"]["ok"])
            with open(tmp + "/" + finished["output_prefix"] + finished["checkpoint"], "rb") as handle:
                blob = handle.read()
            self.assertEqual(png_size(blob), (256, 256))
            published = builds.publish(finished["job_id"], "admin", "layer-admin", CONFIRM_PUBLISH)
            self.assertTrue(published["layer"]["synthetic"])
            self.assertFalse(published["effects"]["png_pyramid_regenerated"])
            self.assertFalse(published["effects"]["real_s3_write"])

    def test_oversized_plan_is_not_queued(self):
        settings = fixture_settings()
        builds = BuildService(MemoryBuildStore(), settings, LayerService(MemoryRepository()), "/tmp")
        plan = builds.plan({
            "source_id": "fixture-demo",
            "tag": "demo/too/big",
            "zooms": [10],
            "tile_merge": 1,
        })
        self.assertFalse(plan["accepted"])
        self.assertIn("tile cap", plan["reason"])
        with self.assertRaises(Exception):
            builds.submit({
                "source_id": "fixture-demo",
                "tag": "demo/too/big",
                "zooms": [10],
                "tile_merge": 1,
                "confirmation": CONFIRM_QUEUE_BUILD,
                "idempotency_key": "too-big-001",
            }, "admin", "layer-admin")

    def test_real_source_is_rejected_without_allowlist_and_gio_fails_honestly(self):
        settings = support.local_settings(builds_enabled=False, build_executor="gio")
        builds = BuildService(MemoryBuildStore(), settings, LayerService(MemoryRepository()), "/tmp")
        with self.assertRaises(Exception):
            builds.inspect("not-configured", "raster.tif")
        settings = support.local_settings(
            builds_enabled=True,
            build_executor="gio",
            source_allowlist="demo=s3://example-fixture-source/datasets/",
        )
        builds = BuildService(MemoryBuildStore(), settings, LayerService(MemoryRepository()), "/tmp")
        with self.assertRaises(Exception):
            builds.inspect("demo", "../secret.tif")
        with self.assertRaises(Exception):
            builds.inspect("demo", "s3://geo-map-tiles-w2/tiles/a.tif")
        blocked = builds.inspect("demo", "water.tif")
        self.assertEqual(blocked["code"], "inspect_runtime_missing")
        self.assertIsNone(blocked["crs"])
        self.assertFalse(blocked["read_s3"])
        body = {
            "source_id": "demo",
            "key": "water.tif",
            "tag": "demo/real/layer",
            "zooms": [2],
            "tile_merge": 1,
            "confirmation": CONFIRM_QUEUE_BUILD,
            "idempotency_key": "real-001",
        }
        plan = builds.plan(body)
        self.assertFalse(plan["submittable"])
        with self.assertRaises(Exception):
            builds.submit(body, "admin", "layer-admin")
        queued = builds.store.save({
            "job_id": "giojob",
            "status": "queued",
            "execution_mode": "gio",
            "real_s3_write": False,
            "cancel_requested": False,
            "plan": {"tile_count": 1, "tile_merge": 1, "sample_tiles": []},
            "progress": {"completed_tiles": 0, "total_tiles": 1, "fraction": 0},
            "logs": [],
            "tiles_written": 0,
            "output_validation": {"ok": False, "real_s3": False},
            "idempotency_key": None,
        })
        failed = builds.run_once()
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"]["code"], "builder_runtime_missing")
        self.assertEqual(failed["tiles_written"], 0)
        self.assertFalse(failed["real_s3_write"])
        self.assertEqual(queued["job_id"], "giojob")

    def test_cancel_retry_and_idempotency(self):
        settings = fixture_settings()
        builds = BuildService(MemoryBuildStore(), settings, LayerService(MemoryRepository()), "/tmp")
        first = builds.submit(self._body(), "admin", "layer-admin")["job"]
        again = builds.submit(self._body(), "admin", "layer-admin")
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["job"]["job_id"], first["job_id"])
        cancelled = builds.cancel(first["job_id"], "admin")["job"]
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(builds.run_once(), None)
        retried = builds.retry(first["job_id"], "admin")["job"]
        self.assertEqual(retried["status"], "queued")
        self.assertEqual(retried["attempt"], 2)
        with self.assertRaises(Conflict):
            builds.submit({**self._body(), "tag": "demo/other/tag"}, "admin", "layer-admin")

    def test_disabled_renderer_is_explicit_and_mock_invoke_hides_admin_token(self):
        api = support.api()
        status, _, body = support.call(api, "GET", "/v1/preview/status")
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["integration_status"], "unconfigured")
        self.assertTrue(body["result"]["pending"])
        status, _, body = support.call(api, "GET", "/v1/preview/tile?layer_id=fixture/demo-pyramid&z=2&x=0&y=0")
        self.assertEqual(status, 409)
        self.assertIn("not invoked", body["error"]["message"])

        seen = {}

        class Invoker:
            def invoke(self, FunctionName, InvocationType, Payload):
                event = json.loads(Payload.decode("utf-8"))
                seen["name"] = FunctionName
                seen["headers"] = event["headers"]
                seen["path"] = event["rawPath"]
                from layer_manager.renderer_preview import fixture_adapter

                raw = json.dumps(fixture_adapter(event)).encode("utf-8")
                return {"Payload": io.BytesIO(raw)}

        settings = support.local_settings(renderer_mode="lambda", renderer_function_arn=ALLOWED_FUNCTION_ARN)
        preview = RendererPreview(settings, invoker=Invoker())
        listing = preview.list_layers()
        self.assertEqual(seen["name"], ALLOWED_FUNCTION_ARN)
        self.assertEqual(seen["headers"], {})
        self.assertEqual(listing["layers"][0]["id"], "fixture/demo-pyramid")
        self.assertTrue(listing["fixture_only"])
        blob, meta = preview.tile("fixture/demo-pyramid", 2, 0, 0, "map")
        self.assertEqual(png_size(blob), (256, 256))
        self.assertEqual(meta["source"], "lambda")
        self.assertFalse(meta["real_s3_build"])
        self.assertNotIn("authorization", {key.lower() for key in seen["headers"]})
        with self.assertRaises(Exception):
            preview.tile("lincoln/water_freq/y2025", 2, 0, 0, "map")
        event = apigateway_event("/tiletest/v1/map/fixture/demo-pyramid/2/0/0.png")
        self.assertNotIn("authorization", event["headers"])

    def test_api_denies_anonymous_build_and_reader_submit(self):
        api = support.api(fixture_settings())
        status, _, _ = support.call(api, "POST", "/v1/builds/plan", {"source_id": "fixture-demo"}, actor=None)
        self.assertEqual(status, 401)
        status, _, _ = support.call(api, "POST", "/v1/builds/plan", {"source_id": "fixture-demo", "tag": "demo/built/fixture", "zooms": [2]}, actor="fixture-reader")
        self.assertEqual(status, 403)
        status, _, body = support.call(api, "GET", "/v1/builds/config", actor="fixture-reader")
        self.assertEqual(status, 200)
        self.assertFalse(body["result"]["real_builds_enabled"])

    def _body(self):
        return {
            "source_id": "fixture-demo",
            "tag": "demo/built/fixture",
            "title": "Fixture build",
            "zooms": [2],
            "tile_merge": 1,
            "confirmation": CONFIRM_QUEUE_BUILD,
            "idempotency_key": "fixture-key-001",
        }


if __name__ == "__main__":
    unittest.main()
