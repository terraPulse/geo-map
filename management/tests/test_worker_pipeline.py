"""Enqueue, dispatch, and worker using a botocore Stubber.

Creating the client object does not send a request. Every operation is
stubbed. This is not a live AWS verification.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import boto3
from botocore.stub import Stubber

import support

from layer_manager.batch_submit import submit_message
from layer_manager.build_jobs import BuildService, MemoryBuildStore
from layer_manager.image_policy import validate_image_uri
from layer_manager.pyramid_engine import write_gradient_geotiff
from layer_manager.repository import MemoryRepository
from layer_manager.schema_contract import CONFIRM_PUBLISH, CONFIRM_QUEUE_BUILD
from layer_manager.service import LayerService
from layer_manager.worker_main import main as worker_main

ALLOW = "demo=s3://example-fixture-source/datasets/"
IMAGE = "544020760996.dkr.ecr.us-west-2.amazonaws.com/geo-map-layer-manager-worker:local"
BUCKET = "example-output"
KEY = "datasets/gradient.tif"


class WorkerPipelineTests(unittest.TestCase):
    def setUp(self):
        self._saved = {name: os.environ.get(name) for name in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_EC2_METADATA_DISABLED",
            "AWS_REGION",
            "AWS_DEFAULT_REGION",
            "BUILD_ALLOW_S3",
            "BUILD_SOURCE_ALLOWLIST",
            "BUILD_OUTPUT_BUCKET",
            "BUILD_SPEC_JSON",
        )}
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
        os.environ["AWS_REGION"] = "us-west-2"
        os.environ["AWS_DEFAULT_REGION"] = "us-west-2"

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_image_names_from_requests_are_rejected(self):
        validate_image_uri(IMAGE)
        for bad in (
            "ubuntu:22.04",
            "public.ecr.aws/example/worker:local",
            IMAGE.rsplit(":", 1)[0] + ":latest",
            "544020760996.dkr.ecr.us-east-1.amazonaws.com/geo-map-layer-manager-worker:local",
        ):
            with self.assertRaises(Exception):
                validate_image_uri(bad)

    def test_entrypoint_builds_a_client_and_publish_uses_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "gradient.tif")
            write_gradient_geotiff(source)
            blob = open(source, "rb").read()
            settings = support.local_settings(
                build_executor="rasterio",
                builds_enabled=True,
                source_allowlist=ALLOW,
                orchestrator="batch",
                build_queue_url="https://example.invalid/queue",
                s3_reads_enabled=True,
                max_build_tiles=8,
            )

            class Queue:
                def __init__(self):
                    self.messages = []

                def send_message(self, QueueUrl, MessageBody):
                    self.messages.append(json.loads(MessageBody))

            queue = Queue()
            builds = BuildService(MemoryBuildStore(), settings, LayerService(MemoryRepository()), tmp, queue_client=queue)

            class Batch:
                def __init__(self):
                    self.jobs = []

                def submit_job(self, **kwargs):
                    self.jobs.append(kwargs)
                    return {"jobId": "batch-stub-1"}

            client = boto3.client("s3", region_name="us-west-2")
            stub = Stubber(client)
            stub.add_response("get_object", {"Body": io.BytesIO(blob)}, {"Bucket": "example-fixture-source", "Key": KEY})
            stub.add_response("get_object", {"Body": io.BytesIO(blob)}, {"Bucket": "example-fixture-source", "Key": KEY})
            for _tile in range(2):
                stub.add_client_error("head_object", service_error_code="404", service_message="Not Found", http_status_code=404)
                stub.add_response("put_object", {"ETag": '"first"'})
            stub.activate()
            constructed = []

            def factory(name, **kwargs):
                constructed.append((name, kwargs.get("region_name")))
                return client

            os.environ["BUILD_ALLOW_S3"] = "1"
            os.environ["BUILD_SOURCE_ALLOWLIST"] = ALLOW
            os.environ["BUILD_OUTPUT_BUCKET"] = BUCKET
            with patch("boto3.client", factory):
                job = builds.submit({
                    "source_id": "demo",
                    "key": "gradient.tif",
                    "tag": "demo/raster/s3",
                    "title": "Gradient",
                    "zooms": [4],
                    "tile_merge": 1,
                    "confirmation": CONFIRM_QUEUE_BUILD,
                    "idempotency_key": "pipeline-001",
                }, "admin", "layer-admin")["job"]
            self.assertEqual(constructed, [("s3", "us-west-2")])
            self.assertEqual(len(queue.messages), 1)
            dispatched = submit_message(queue.messages[0], Batch(), "pyramid-queue", "pyramid-definition", IMAGE, ALLOW)
            spec = dispatched["spec"]
            spec["output_dir"] = os.path.join(tmp, "out")
            self.assertEqual(spec["output_prefix"], f"builds/{job['job_id']}")
            self.assertNotIn("image", spec)
            os.environ["BUILD_SPEC_JSON"] = json.dumps(spec)
            with patch("boto3.client", factory):
                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    code = worker_main()
            self.assertEqual(code, 0)
            self.assertEqual(constructed, [("s3", "us-west-2"), ("s3", "us-west-2")])
            payload = json.loads(captured.getvalue())
            self.assertTrue(payload["real_s3_write"])
            self.assertFalse(payload["live_aws_verified"])
            self.assertEqual(len(payload["uploaded"]), 2)
            self.assertTrue(all(key.startswith(f"builds/{job['job_id']}/tiles/") for key in payload["uploaded"]))
            stub.assert_no_pending_responses()

            finished = builds.apply_worker_report(job["job_id"], payload)
            self.assertEqual(finished["status"], "succeeded")
            self.assertTrue(finished["output_validation"]["ok"])
            self.assertFalse(finished["live_aws_verified"])
            published = builds.publish(job["job_id"], "admin", "layer-admin", CONFIRM_PUBLISH)
            self.assertFalse(published["layer"]["synthetic"])
            self.assertEqual(published["layer"]["schema"], "geo-map.layer-registry.v1")
            manifest = published["renderer_manifest"]
            self.assertEqual(manifest["adapter"], "geomap.png_pyramid")
            self.assertEqual(manifest["layers"][0]["storage"], "s3")
            self.assertEqual(manifest["layers"][0]["key_prefix"], f"builds/{job['job_id']}")
            self.assertNotIn("bucket", manifest["layers"][0])
            self.assertEqual(published["interfaces_v0"]["schema"], "geo-map.dataset-registry/v0")
            self.assertFalse(published["effects"]["live_aws_verified"])
            self._sibling_accepts(manifest)

            failed = builds.store.save({
                **finished,
                "job_id": "b" * 32,
                "status": "failed",
                "idempotency_key": None,
                "output_validation": {"ok": False, "live_aws_verified": False},
            })
            with self.assertRaises(Exception):
                builds.publish(failed["job_id"], "admin", "layer-admin", CONFIRM_PUBLISH)
            cancelled = builds.store.save({**failed, "job_id": "c" * 32, "status": "cancelled", "idempotency_key": None})
            with self.assertRaises(Exception):
                builds.publish(cancelled["job_id"], "admin", "layer-admin", CONFIRM_PUBLISH)

            stub.deactivate()
            spec["hashes"] = payload["hashes"]
            os.environ["BUILD_SPEC_JSON"] = json.dumps(spec)
            retry = Stubber(client)
            retry.add_response("get_object", {"Body": io.BytesIO(blob)}, {"Bucket": "example-fixture-source", "Key": KEY})
            for relative in payload["completed"]:
                retry.add_response(
                    "head_object",
                    {"Metadata": {"sha256": payload["hashes"][relative]}},
                    {"Bucket": BUCKET, "Key": f"builds/{job['job_id']}/{relative}"},
                )
            retry.activate()
            with patch("boto3.client", factory):
                with contextlib.redirect_stdout(io.StringIO()):
                    again = worker_main()
            self.assertEqual(again, 0)
            retry.assert_no_pending_responses()

    def _sibling_accepts(self, manifest):
        import pathlib
        import subprocess
        import sys

        root = pathlib.Path(tempfile.mkdtemp())
        sha = "8292c07b2e42a5b6776569d947142d6f275f9e8b"
        for source, dest in (
            (f"{sha}:util/lib/tile_runtime.py", root / "tile_runtime.py"),
            (f"{sha}:deploy/tile_pyramid_test/registry.py", root / "registry.py"),
        ):
            text = subprocess.check_output(["git", "show", source], cwd=support.ROOT.parents[0])
            dest.write_bytes(text)
        sys.path.insert(0, str(root))
        try:
            import importlib

            registry = importlib.import_module("registry")
            document = {
                "adapter": manifest["adapter"],
                "adapter_version": manifest["adapter_version"],
                "layers": manifest["layers"],
            }
            parsed = registry.validate_registry(document)
            self.assertEqual(parsed["layers"]["demo/raster/s3"]["key_prefix"], manifest["layers"][0]["key_prefix"])
        finally:
            sys.path.remove(str(root))
            for name in ("registry", "tile_runtime"):
                sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
