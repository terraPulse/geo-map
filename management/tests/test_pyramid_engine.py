import contextlib
import io
import json
import os
import tempfile
import unittest

from PIL import Image

import support

from layer_manager.batch_submit import submit_message
from layer_manager.build_jobs import BuildService, MemoryBuildStore
from layer_manager.pyramid_engine import render_pyramid, write_gradient_geotiff
from layer_manager.repository import MemoryRepository
from layer_manager.s3_source import split_allowlisted
from layer_manager.schema_contract import CONFIRM_PUBLISH, CONFIRM_QUEUE_BUILD
from layer_manager.service import LayerService
from layer_manager.worker_main import main as worker_main

STOPS = (
    {"value": 0, "rgba": [0, 0, 180, 255]},
    {"value": 100, "rgba": [180, 0, 0, 255]},
)


class PyramidEngineTests(unittest.TestCase):
    def test_generated_geotiff_becomes_distinct_blocks_at_two_zooms(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "gradient.tif")
            meta = write_gradient_geotiff(source)
            out = os.path.join(tmp, "pyramid")
            result = render_pyramid(source, out, meta["bounds"], [3, 4], 1, "nearest", STOPS)
            self.assertEqual(result["total"], 3)
            self.assertEqual(result["written"], ["tiles/3/0/0.png", "tiles/4/0/0.png", "tiles/4/1/0.png"])
            west = Image.open(os.path.join(out, "tiles/4/0/0.png"))
            east = Image.open(os.path.join(out, "tiles/4/1/0.png"))
            coarse = Image.open(os.path.join(out, "tiles/3/0/0.png"))
            self.assertEqual(west.size, (256, 256))
            self.assertEqual(east.size, (256, 256))
            self.assertEqual(coarse.size, (256, 256))
            self.assertEqual(west.getpixel((2, 2))[3], 0)
            west_pixel = west.getpixel((128, 200))
            east_pixel = east.getpixel((128, 200))
            self.assertGreater(west_pixel[2], west_pixel[0])
            self.assertGreater(east_pixel[0], east_pixel[2])
            self.assertGreater(east_pixel[0], west_pixel[0])
            coarse_pixel = coarse.getpixel((128, 220))
            self.assertEqual(coarse_pixel[3], 255)
            self.assertNotEqual(west_pixel, east_pixel)
            again = render_pyramid(
                source,
                out,
                meta["bounds"],
                [3, 4],
                1,
                "nearest",
                STOPS,
                completed=result["completed"],
                hashes=result["hashes"],
            )
            self.assertEqual(again["written"], [])
            self.assertEqual(again["completed"], result["completed"])

    def test_service_batches_resume_and_does_not_publish_an_s3_build(self):
        settings = support.local_settings(build_executor="rasterio", builds_enabled=False, max_build_tiles=1)
        with tempfile.TemporaryDirectory() as tmp:
            builds = BuildService(MemoryBuildStore(), settings, LayerService(MemoryRepository()), tmp)
            body = {
                "source_id": "raster-fixture",
                "tag": "demo/raster/gradient",
                "title": "Gradient pyramid",
                "zooms": [3, 4],
                "tile_merge": 1,
                "resampling": "nearest",
                "confirmation": CONFIRM_QUEUE_BUILD,
                "idempotency_key": "raster-batch-001",
            }
            plan = builds.plan(body)
            self.assertEqual(plan["tile_count"], 3)
            self.assertEqual(plan["batch_size"], 1)
            self.assertEqual(plan["batch_count"], 3)
            self.assertTrue(plan["submittable"])
            job = builds.submit(body, "admin", "layer-admin")["job"]
            self.assertEqual(job["execution_mode"], "rasterio")
            self.assertFalse(job["real_s3_write"])
            first = builds.run_once()
            self.assertEqual(first["status"], "queued")
            self.assertEqual(first["tiles_written"], 1)
            builds.cancel(first["job_id"], "admin")
            self.assertIsNone(builds.run_once())
            retried = builds.retry(first["job_id"], "admin")["job"]
            self.assertEqual(retried["tiles_written"], 1)
            second = builds.run_once()
            third = builds.run_once()
            self.assertEqual(third["status"], "succeeded")
            self.assertEqual(third["tiles_written"], 3)
            self.assertEqual(len(set(third["completed"])), 3)
            self.assertFalse(third["real_s3_write"])
            self.assertEqual(third["output_validation"]["engine"], "rasterio")
            root = os.path.join(tmp, third["output_prefix"])
            pngs = []
            for dirpath, _dirs, names in os.walk(root):
                pngs.extend(name for name in names if name.endswith(".png"))
            self.assertEqual(len(pngs), 3)
            published = builds.publish(third["job_id"], "admin", "layer-admin", CONFIRM_PUBLISH)
            self.assertFalse(published["layer"]["synthetic"])
            self.assertEqual(published["layer"]["inventory"], "registry")
            self.assertEqual(published["renderer_manifest"]["adapter"], "geomap.png_pyramid")
            self.assertIsNone(published["renderer_manifest"]["layers"][0].get("bucket"))
            self.assertEqual(published["interfaces_v0"]["schema"], "geo-map.dataset-registry/v0")
            self.assertNotEqual(published["interfaces_v0"]["schema"], published["layer"]["schema"])
            self.assertFalse(published["effects"]["png_pyramid_regenerated"])
            self.assertFalse(published["effects"]["live_aws_verified"])
            self.assertFalse(published["effects"]["real_s3_write"])
            self.assertEqual(second["tiles_written"], 2)

    def test_s3_reader_is_allowlisted_and_unconfigured_reads_nothing(self):
        with self.assertRaises(Exception):
            split_allowlisted(
                "s3://geo-map-tiles-w2/tiles/a.tif",
                "bad=s3://geo-map-tiles-w2/tiles/",
            )
        with self.assertRaises(Exception):
            split_allowlisted(
                "s3://example-fixture-source/other/a.tif",
                "demo=s3://example-fixture-source/datasets/",
            )
        bucket, key = split_allowlisted(
            "s3://example-fixture-source/datasets/gradient.tif",
            "demo=s3://example-fixture-source/datasets/",
        )
        self.assertEqual(bucket, "example-fixture-source")
        self.assertEqual(key, "datasets/gradient.tif")
        settings = support.local_settings(
            build_executor="rasterio",
            builds_enabled=True,
            source_allowlist="demo=s3://example-fixture-source/datasets/",
        )
        builds = BuildService(MemoryBuildStore(), settings, LayerService(MemoryRepository()), "/tmp")
        blocked = builds.inspect("demo", "gradient.tif")
        self.assertEqual(blocked["code"], "source_reader_unconfigured")
        self.assertFalse(blocked["read_s3"])
        self.assertIsNone(blocked["crs"])
        job = builds.store.save({
            "job_id": "s3job",
            "status": "queued",
            "execution_mode": "rasterio",
            "real_s3_write": False,
            "cancel_requested": False,
            "source": {"id": "demo", "kind": "s3", "uri": "s3://example-fixture-source/datasets/gradient.tif"},
            "plan": {"zooms": [4], "tile_merge": 1, "resampling": "nearest", "batch_size": 2, "tile_count": 1},
            "progress": {"completed_tiles": 0, "total_tiles": 1, "fraction": 0},
            "completed": [],
            "logs": [],
            "tiles_written": 0,
            "output_validation": {"ok": False, "real_s3": False},
            "output_prefix": "builds/s3job/",
            "idempotency_key": None,
        })
        failed = builds.run_once()
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"]["code"], "source_reader_unconfigured")
        self.assertEqual(failed["tiles_written"], 0)
        self.assertFalse(failed["real_s3_write"])
        self.assertEqual(job["job_id"], "s3job")

    def test_injected_fetcher_plans_from_the_real_geotiff_and_batch_enqueue_does_not_call_aws(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "gradient.tif")
            write_gradient_geotiff(source)
            seen = []

            def fetch(uri):
                seen.append(uri)
                return source

            class Queue:
                def __init__(self):
                    self.messages = []

                def send_message(self, QueueUrl, MessageBody):
                    self.messages.append((QueueUrl, json.loads(MessageBody)))

            class Batch:
                def __init__(self):
                    self.jobs = []

                def submit_job(self, **kwargs):
                    self.jobs.append(kwargs)
                    return {"jobId": "fake-batch-1"}

            settings = support.local_settings(
                build_executor="rasterio",
                builds_enabled=True,
                source_allowlist="demo=s3://example-fixture-source/datasets/",
                orchestrator="batch",
                build_queue_url="https://example.invalid/queue",
                max_build_tiles=8,
            )
            queue = Queue()
            builds = BuildService(
                MemoryBuildStore(), settings, LayerService(MemoryRepository()), tmp, source_fetch=fetch, queue_client=queue
            )
            info = builds.inspect("demo", "gradient.tif")
            self.assertEqual(info["crs"], "EPSG:3857")
            self.assertFalse(info["read_s3"])
            self.assertEqual(seen, ["s3://example-fixture-source/datasets/gradient.tif"])
            body = {
                "source_id": "demo",
                "key": "gradient.tif",
                "tag": "demo/raster/s3",
                "zooms": [4],
                "tile_merge": 1,
                "confirmation": CONFIRM_QUEUE_BUILD,
                "idempotency_key": "raster-s3-001",
            }
            queued = builds.submit(body, "admin", "layer-admin")["job"]
            self.assertEqual(queued["status"], "queued")
            self.assertFalse(queued["real_s3_write"])
            self.assertEqual(len(queue.messages), 1)
            message = queue.messages[0][1]
            self.assertEqual(message["source_uri"], "s3://example-fixture-source/datasets/gradient.tif")
            self.assertIn("datasets/", message["allowlist"])
            batch = Batch()
            submitted = submit_message(
                message,
                batch,
                "pyramid-queue",
                "pyramid-definition",
                "544020760996.dkr.ecr.us-west-2.amazonaws.com/geo-map-layer-manager-worker:local",
                "demo=s3://example-fixture-source/datasets/",
            )
            self.assertEqual(submitted["batch_job_id"], "fake-batch-1")
            self.assertFalse(submitted["image_from_message"])
            self.assertEqual(batch.jobs[0]["jobQueue"], "pyramid-queue")
            self.assertIsNone(builds.run_once())
            message["image"] = "public.ecr.aws/example:latest"
            with self.assertRaises(ValueError):
                submit_message(
                    message,
                    batch,
                    "pyramid-queue",
                    "pyramid-definition",
                    "544020760996.dkr.ecr.us-west-2.amazonaws.com/geo-map-layer-manager-worker:local",
                    "demo=s3://example-fixture-source/datasets/",
                )

    def test_worker_refuses_s3_until_a_client_is_injected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "gradient.tif")
            meta = write_gradient_geotiff(source)
            out = os.path.join(tmp, "out")
            spec = {
                "source_uri": "s3://example-fixture-source/datasets/gradient.tif",
                "allowlist": "demo=s3://example-fixture-source/datasets/",
                "output_dir": out,
                "bounds": meta["bounds"],
                "zooms": [4],
                "tile_merge": 1,
                "resampling": "nearest",
                "stops": list(STOPS),
                "output_prefix": "builds/job/",
            }
            previous = os.environ.get("BUILD_SPEC_JSON")
            allow = os.environ.get("BUILD_ALLOW_S3")
            bucket = os.environ.get("BUILD_OUTPUT_BUCKET")
            os.environ["BUILD_SPEC_JSON"] = json.dumps(spec)
            os.environ.pop("BUILD_ALLOW_S3", None)
            os.environ.pop("BUILD_OUTPUT_BUCKET", None)
            try:
                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    code = worker_main(s3_client=None)
                self.assertEqual(code, 1)
                self.assertIn("source_reader_unconfigured", captured.getvalue())
                self.assertIn('"real_s3_write": false', captured.getvalue())
            finally:
                _restore("BUILD_SPEC_JSON", previous)
                _restore("BUILD_ALLOW_S3", allow)
                _restore("BUILD_OUTPUT_BUCKET", bucket)


def _restore(name, value):
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
