"""Build queue and raster worker. gio is not called."""

import json
import os
import threading
import uuid

from .build_allow import output_prefix_for, parse_allowlist, resolve_key
from .canonical import content_digest, utcnow
from .errors import Conflict, NotFound, ValidationFailed
from .interfaces_export import export_dataset_v0
from .png_codec import encode_rgba, png_size
from .pyramid_engine import PyramidError, describe_raster, render_pyramid, write_gradient_geotiff
from .renderer_manifest import renderer_manifest
from .schema_contract import CONFIRM_PUBLISH, CONFIRM_QUEUE_BUILD
from .tile_math import MAX_MERGE, count_tiles
from .validate import digest_input, structural_errors, validate_client_layer, validate_tag

FIXTURE_SOURCE = {
    "id": "fixture-demo",
    "kind": "fixture-offline",
    "title": "Offline fixture dataset",
    "uri": "synthetic://fixture/demo-build",
    "real_s3": False,
    "inspection": {
        "crs": "EPSG:3857",
        "resolution_m": 30,
        "bands": 1,
        "nodata": None,
        "bounds": {"crs": "EPSG:3857", "minx": -20037508.0, "miny": -20037508.0, "maxx": -19000000.0, "maxy": -19000000.0},
        "source": "fixture-offline",
        "read_s3": False,
    },
}

RASTER_STOPS = (
    {"value": 0, "rgba": [0, 0, 180, 255]},
    {"value": 100, "rgba": [180, 0, 0, 255]},
)


class BuildStore:
    def get(self, job_id):
        raise NotImplementedError

    def save(self, job):
        raise NotImplementedError

    def find_idempotency(self, key):
        raise NotImplementedError


class MemoryBuildStore(BuildStore):
    def __init__(self):
        self._jobs = {}
        self._idem = {}
        self._lock = threading.Lock()

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else json_copy(job)

    def save(self, job):
        with self._lock:
            self._jobs[job["job_id"]] = json_copy(job)
            if job.get("idempotency_key"):
                self._idem[job["idempotency_key"]] = job["job_id"]
            return json_copy(job)

    def find_idempotency(self, key):
        with self._lock:
            job_id = self._idem.get(key)
            if not job_id:
                return None
            return json_copy(self._jobs[job_id])


def json_copy(value):
    import json

    return json.loads(json.dumps(value))


class BuildService:
    def __init__(self, store, settings, layer_service, output_root, source_fetch=None, queue_client=None, s3_client=None):
        self.store = store
        self.settings = settings
        self.layers = layer_service
        self.output_root = output_root
        self.source_fetch = source_fetch
        self.queue_client = queue_client
        self.s3_client = s3_client
        self._lock = threading.Lock()

    def config(self):
        runtime = probe_builder()
        return {
            "real_builds_enabled": bool(self.settings.builds_enabled),
            "fixture_builds": self.settings.build_executor == "fixture-offline",
            "executor": self.settings.build_executor,
            "runtime": runtime,
            "max_tiles": self.settings.max_build_tiles,
            "batch_size": self.settings.max_build_tiles,
            "absolute_max": self.settings.build_absolute_max,
            "orchestrator": self.settings.orchestrator,
            "max_merge": MAX_MERGE,
            "output_configured": bool(self.settings.output_prefix),
            "sources": [item["id"] for item in self._sources()],
            "real_s3_writes": False,
            "note": (
                "32 is the batch size, not a limit on the pyramid. "
                "The staging API stays disabled until an allowlisted source, output bucket, image, and subnets are set. "
                "A rasterio run writes local version-2 PNGs and is not an S3 build. gio is not used."
            ),
        }

    def list_sources(self):
        return {"sources": self._sources(), "bucket_scan": False}

    def inspect(self, source_id, key=None):
        source = self._source(source_id)
        if source["kind"] in {"fixture-offline", "raster-fixture"}:
            info = dict(source["inspection"])
            info["source_id"] = source_id
            info["key"] = None
            info["uri"] = source.get("uri")
            info["read_s3"] = False
            return info
        if key is None:
            raise ValidationFailed("An object key is required for an S3 source.", [])
        uri = resolve_key(source["uri"], key)
        if self.settings.build_executor == "rasterio":
            client = self.s3_client
            if client is None and self.settings.s3_reads_enabled:
                from .s3_source import s3_client_from_environment

                client = s3_client_from_environment()
            if client is None and self.source_fetch is None:
                return {
                    "source_id": source_id,
                    "uri": uri,
                    "status": "blocked",
                    "code": "source_reader_unconfigured",
                    "crs": None,
                    "resolution_m": None,
                    "bands": None,
                    "nodata": None,
                    "bounds": None,
                    "read_s3": False,
                    "message": "No S3 reader is configured. The object was not fetched and no metadata was invented.",
                }
            if self.source_fetch is not None and client is None:
                path = self.source_fetch(uri)
            else:
                import tempfile

                from .s3_source import download_allowlisted

                path = download_allowlisted(uri, self.settings.source_allowlist_text, tempfile.mkdtemp(prefix="inspect-"), client)
            info = describe_raster(path)
            info["source_id"] = source_id
            info["uri"] = uri
            info["key"] = key
            info["status"] = "inspected"
            info["read_s3"] = client is not None
            info["live_aws_verified"] = False
            return info
        runtime = probe_builder()
        if not runtime["gio_importable"] or not runtime["gdal_importable"]:
            return {
                "source_id": source_id,
                "uri": uri,
                "status": "blocked",
                "code": "inspect_runtime_missing",
                "crs": None,
                "resolution_m": None,
                "bands": None,
                "nodata": None,
                "bounds": None,
                "read_s3": False,
                "message": "gio and GDAL are not installed. Raster metadata was not invented and S3 was not read.",
            }
        return {
            "source_id": source_id,
            "uri": uri,
            "status": "blocked",
            "code": "inspect_locked",
            "read_s3": False,
            "message": "GDAL imported, but live raster reads stay locked until a reviewed Batch image is selected.",
        }

    def plan(self, body):
        source = self._source(body.get("source_id"))
        inspection = self.inspect(source["id"], body.get("key"))
        if inspection.get("status") == "blocked":
            return {"accepted": False, "submittable": False, "reason": inspection["code"], "inspection": inspection, "approximate": True}
        tag_errors = validate_tag(body.get("tag"))
        if tag_errors:
            return {"accepted": False, "submittable": False, "reason": "tag", "issues": tag_errors, "approximate": True}
        if body.get("resampling", "nearest") not in {"nearest", "bilinear", "cubic"}:
            raise ValidationFailed("resampling must be nearest, bilinear, or cubic.", [])
        if body.get("aggregate", "median") not in {"mean", "median", "dominated"}:
            raise ValidationFailed("aggregate must be mean, median, or dominated.", [])
        zooms = body.get("zooms") or [2]
        merge = int(body.get("tile_merge") or 1)
        try:
            total, sample = count_tiles(inspection["bounds"], zooms, merge)
        except ValueError as exc:
            raise ValidationFailed(str(exc), []) from exc
        pixels = total * (256 * merge) ** 2
        batch = max(1, int(self.settings.max_build_tiles))
        absolute = int(self.settings.build_absolute_max)
        plan = {
            "source_id": source["id"],
            "source_kind": source["kind"],
            "real_s3": False,
            "tag": body.get("tag"),
            "title": body.get("title") or body.get("tag"),
            "zooms": [int(z) for z in zooms],
            "tile_merge": merge,
            "aggregate": body.get("aggregate") or "median",
            "resampling": body.get("resampling") or "nearest",
            "resampling_applied": False,
            "tile_count": total,
            "batch_size": batch,
            "batch_count": (total + batch - 1) // batch if total else 0,
            "absolute_max": absolute,
            "pixel_estimate": pixels,
            "storage_bytes_upper": pixels * 4,
            "approximate": True,
            "sample_tiles": sample,
            "bounds": inspection.get("bounds"),
            "source_uri": inspection.get("uri") or source.get("uri"),
            "layout": "version-2-tiles",
            "output_note": (
                f"The raster engine writes version-2 blocks in batches of {batch}. "
                "That batch size is not a claim that one batch covers a global pyramid."
            ),
        }
        accepted = 0 < total <= absolute and merge <= MAX_MERGE
        plan["accepted"] = accepted
        plan["submittable"] = accepted and self._can_submit(source)
        plan["reason"] = None if plan["submittable"] else self._block_reason(source, accepted)
        plan["content_digest"] = content_digest({k: plan[k] for k in ("source_id", "tag", "zooms", "tile_merge", "tile_count")})
        return plan

    def submit(self, body, actor, role):
        if body.get("confirmation") != CONFIRM_QUEUE_BUILD:
            raise ValidationFailed("Confirmation phrase must be exactly queue-build.", [])
        plan = self.plan(body)
        if not plan.get("accepted"):
            raise ValidationFailed("The plan is over the tile limit or incomplete. No job was queued.", [plan])
        if not plan.get("submittable"):
            raise Conflict(plan.get("reason") or "Build was not queued.", [plan])
        key = body.get("idempotency_key")
        if not isinstance(key, str) or len(key) < 8 or len(key) > 80:
            raise ValidationFailed("idempotency_key is required.", [])
        existing = self.store.find_idempotency(key)
        if existing:
            if existing["plan_digest"] != plan["content_digest"]:
                raise Conflict("This idempotency key was already used for a different plan.", [])
            return {"job": existing, "duplicate": True}
        job_id = uuid.uuid4().hex
        prefix = output_prefix_for(self.settings.output_prefix or "builds", job_id)
        job = {
            "job_id": job_id,
            "status": "queued",
            "execution_mode": _execution_mode(plan["source_kind"], self.settings.build_executor),
            "real_s3_write": False,
            "actor": actor,
            "role": role,
            "idempotency_key": key,
            "plan_digest": plan["content_digest"],
            "plan": plan,
            "source": {"id": plan["source_id"], "kind": plan["source_kind"], "uri": plan.get("source_uri")},
            "output_prefix": prefix,
            "attempt": 1,
            "cancel_requested": False,
            "progress": {"completed_tiles": 0, "total_tiles": plan["tile_count"], "fraction": 0},
            "checkpoint": None,
            "logs": [{"at": utcnow(), "message": "queued"}],
            "tiles_written": 0,
            "completed": [],
            "tile_hashes": {},
            "live_aws_verified": False,
            "output_validation": {"ok": False, "real_s3": False, "live_aws_verified": False},
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
        if self.settings.orchestrator == "batch":
            self._enqueue(job)
        return {"job": self.store.save(job), "duplicate": False}

    def _enqueue(self, job):
        if not self.settings.build_queue_url and self.queue_client is None:
            raise Conflict("Build queue is not configured. No job was submitted.", [])
        client = self.queue_client
        if client is None:
            import boto3

            client = boto3.client("sqs", region_name=self.settings.authorized_region)
        body = {
            "job_id": job["job_id"],
            "source_uri": job["source"].get("uri"),
            "allowlist": self.settings.source_allowlist_text,
            "bounds": job["plan"].get("bounds"),
            "zooms": job["plan"]["zooms"],
            "tile_merge": job["plan"]["tile_merge"],
            "resampling": job["plan"]["resampling"],
            "stops": list(RASTER_STOPS),
            "output_prefix": job["output_prefix"],
            "batch_size": job["plan"].get("batch_size"),
            "hashes": job.get("tile_hashes") or {},
        }
        client.send_message(QueueUrl=self.settings.build_queue_url or "configured", MessageBody=json.dumps(body))
        job["logs"].append({"at": utcnow(), "message": "enqueued for Batch"})

    def get(self, job_id):
        job = self.store.get(job_id)
        if job is None:
            raise NotFound("No such build.")
        return {"job": job}

    def cancel(self, job_id, actor):
        with self._lock:
            job = self._require(job_id)
            if job["status"] in {"succeeded", "failed", "cancelled"}:
                raise Conflict("This build is already finished.", [])
            job["cancel_requested"] = True
            job["logs"].append({"at": utcnow(), "message": f"cancel requested by {actor}"})
            if job["status"] == "queued":
                job["status"] = "cancelled"
                job["updated_at"] = utcnow()
            return {"job": self.store.save(job)}

    def retry(self, job_id, actor):
        with self._lock:
            job = self._require(job_id)
            if job["status"] not in {"failed", "cancelled"}:
                raise Conflict("Only a failed or cancelled build can be retried.", [])
            job["attempt"] += 1
            job["status"] = "queued"
            job["cancel_requested"] = False
            job["progress"] = {
                "completed_tiles": len(job.get("completed") or []),
                "total_tiles": job["plan"]["tile_count"],
                "fraction": 0,
            }
            job["tiles_written"] = len(job.get("completed") or [])
            job["output_validation"] = {"ok": False, "real_s3": False}
            job["logs"].append({"at": utcnow(), "message": f"retry {job['attempt']} by {actor}"})
            job["updated_at"] = utcnow()
            return {"job": self.store.save(job)}

    def run_once(self):
        if self.settings.orchestrator == "batch":
            return None
        job = self._next_queued()
        if job is None:
            return None
        if job["cancel_requested"]:
            job["status"] = "cancelled"
            job["updated_at"] = utcnow()
            return self.store.save(job)
        job["status"] = "running"
        job["logs"].append({"at": utcnow(), "message": "running"})
        self.store.save(job)
        if job["execution_mode"] == "fixture-offline":
            return self._run_fixture(job)
        if job["execution_mode"] == "rasterio":
            return self._run_rasterio(job)
        return self._refuse_gio(job)

    def publish(self, job_id, actor, role, confirmation, expected_revision=None):
        if confirmation != CONFIRM_PUBLISH:
            raise ValidationFailed("Confirmation phrase must be exactly publish-registry-only.", [])
        job = self._require(job_id)
        if job["status"] != "succeeded" or not job["output_validation"].get("ok"):
            raise Conflict("Only a validated successful build can be published.", [])
        if job.get("live_aws_verified") or job["output_validation"].get("live_aws_verified"):
            raise Conflict("This process cannot mark a build as live-verified.", [])
        layer_body = {
            "tag": job["plan"]["tag"],
            "title": job["plan"]["title"],
            "backend": "png-pyramid",
            "pyramid": {
                "layout": "version-2-tiles",
                "tile_pixel_size": 256,
                "tile_merge": job["plan"]["tile_merge"],
                "min_static_level": min(job["plan"]["zooms"]),
                "min_dynamic_level": max(job["plan"]["zooms"]),
                "processed_levels": job["plan"]["zooms"],
                "version": 2.0,
                "aggregate": job["plan"]["aggregate"],
                "persistent": True,
            },
            "cog": None,
            "bounds": job["plan"].get("bounds") or FIXTURE_SOURCE["inspection"]["bounds"],
            "style": _publish_style(job),
            "nodata": {
                "min_value": None,
                "max_value": None,
                "fill_nodata": None,
                "raster_nodata": -9999 if job["execution_mode"] == "rasterio" else None,
            },
            "source_revisions": [
                {
                    "revision_id": job["job_id"][:12],
                    "uri": _publish_uri(job),
                    "note": "Validated worker output. Not a live inventory check and not the production tile bucket.",
                    "recorded_at": utcnow(),
                }
            ],
            "authorized_tile_template": None,
        }
        normalized, issues = validate_client_layer(layer_body)
        if structural_errors(issues):
            raise ValidationFailed("Build metadata is not publishable.", structural_errors(issues))
        if job["execution_mode"] == "rasterio":
            stored = self.layers.register_validated_output(layer_body, actor=actor, role=role)
            manifest = renderer_manifest(job)
            exported = export_dataset_v0(stored)
            synthetic = False
        else:
            stored = self.layers.seed_fixture({**layer_body, "status": "published"}, actor=actor, role=role)
            manifest = None
            exported = None
            synthetic = True
        return {
            "layer": stored,
            "renderer_manifest": manifest,
            "interfaces_v0": exported,
            "schema_gap": "Stored record is geo-map.layer-registry.v1. interfaces_v0 is a separate export, not the stored document.",
            "effects": {
                "registry_updated": True,
                "png_pyramid_regenerated": False,
                "real_s3_write": bool(job.get("real_s3_write")),
                "live_aws_verified": False,
                "execution_mode": job["execution_mode"],
            },
            "build": {
                "job_id": job["job_id"],
                "real_s3_write": bool(job.get("real_s3_write")),
                "live_aws_verified": False,
                "synthetic": synthetic,
            },
        }

    def apply_worker_report(self, job_id, payload):
        job = self._require(job_id)
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            raise Conflict("This build is already finished.", [])
        job["live_aws_verified"] = False
        job["real_s3_write"] = bool(payload.get("real_s3_write"))
        job["output_bucket"] = payload.get("output_bucket")
        hashes = payload.get("hashes") or {}
        completed = payload.get("completed") or []
        matched = payload.get("ok") and completed and len(completed) == payload.get("total") and all(path in hashes for path in completed)
        if not matched:
            job["status"] = "cancelled" if payload.get("stopped") else "failed"
            job["error"] = {
                "code": payload.get("code") or "worker_failed",
                "message": payload.get("message") or "The worker did not validate every block.",
            }
            job["output_validation"] = {"ok": False, "real_s3": False, "live_aws_verified": False}
        else:
            job["status"] = "succeeded"
            job["tile_hashes"] = hashes
            job["completed"] = completed
            job["tiles_written"] = len(completed)
            job["progress"] = {"completed_tiles": len(completed), "total_tiles": payload["total"], "fraction": 1}
            job["output_validation"] = {
                "ok": True,
                "real_s3": job["real_s3_write"],
                "live_aws_verified": False,
                "engine": "rasterio",
                "png_blocks": len(completed),
                "sha256": hashes,
            }
        job["logs"].append({"at": utcnow(), "message": job["status"] + " from worker report"})
        job["updated_at"] = utcnow()
        return self.store.save(job)

    def _run_fixture(self, job):
        total = job["plan"]["tile_count"]
        sample = job["plan"]["sample_tiles"] or [{"z": 2, "x": 0, "y": 0}]
        written = 0
        for index, tile in enumerate(sample[:total]):
            current = self.store.get(job["job_id"])
            if current["cancel_requested"]:
                current["status"] = "cancelled"
                current["tiles_written"] = written
                current["updated_at"] = utcnow()
                return self.store.save(current)
            blob = encode_rgba(256 * job["plan"]["tile_merge"], 256 * job["plan"]["tile_merge"], (70, 130, 180, 255))
            path = os.path.join(self.output_root, job["output_prefix"], "tiles", str(tile["z"]), str(tile["x"]), f"{tile['y']}.png")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(blob)
            if png_size(blob)[0] != 256 * job["plan"]["tile_merge"]:
                raise RuntimeError("png size")
            written += 1
            current["progress"] = {"completed_tiles": written, "total_tiles": total, "fraction": written / total}
            current["checkpoint"] = f"tiles/{tile['z']}/{tile['x']}/{tile['y']}.png"
            current["tiles_written"] = written
            current["logs"].append({"at": utcnow(), "message": f"wrote {current['checkpoint']} (fixture-offline)"})
            self.store.save(current)
        current = self.store.get(job["job_id"])
        current["status"] = "succeeded"
        current["output_validation"] = {"ok": written == min(total, len(sample)) and written > 0, "real_s3": False, "png": True}
        current["updated_at"] = utcnow()
        current["logs"].append({"at": utcnow(), "message": "fixture-offline finished. No S3 write."})
        return self.store.save(current)

    def _refuse_gio(self, job):
        runtime = probe_builder()
        if not runtime["gio_importable"] or not runtime["gdal_importable"]:
            code = "builder_runtime_missing"
            message = "gio and GDAL are not installed. build_tiles_task.py did not run. No tile was written."
        else:
            code = "builder_locked"
            message = "gio imported, but this process will not start a raster build. No tile was written."
        job["status"] = "failed"
        job["error"] = {"code": code, "message": message}
        job["tiles_written"] = 0
        job["real_s3_write"] = False
        job["output_validation"] = {"ok": False, "real_s3": False}
        job["logs"].append({"at": utcnow(), "message": message})
        job["updated_at"] = utcnow()
        return self.store.save(job)

    def _next_queued(self):
        # Memory store keeps insertion order via dict in 3.7+.
        if not hasattr(self.store, "_jobs"):
            return None
        with self.store._lock:
            for job in self.store._jobs.values():
                if job["status"] == "queued":
                    return json_copy(job)
        return None

    def _require(self, job_id):
        job = self.store.get(job_id)
        if job is None:
            raise NotFound("No such build.")
        return job

    def _sources(self):
        rows = []
        if self.settings.build_executor == "fixture-offline":
            rows.append({k: FIXTURE_SOURCE[k] for k in ("id", "kind", "title", "uri", "real_s3")})
        if self.settings.build_executor == "rasterio":
            rows.append({
                "id": "raster-fixture",
                "kind": "raster-fixture",
                "title": "Generated GeoTIFF exercised by the rasterio engine",
                "uri": "synthetic://fixture/gradient-geotiff",
                "real_s3": False,
            })
        for item in self.settings.source_allowlist:
            rows.append({"id": item["id"], "kind": "s3", "title": item["id"], "uri": item["uri"], "real_s3": False})
        return rows

    def _source(self, source_id):
        for item in self._sources():
            if item["id"] == source_id:
                if item["kind"] == "fixture-offline":
                    return FIXTURE_SOURCE
                if item["kind"] == "raster-fixture":
                    from .pyramid_engine import fixture_bounds

                    return {**item, "inspection": {
                        "crs": "EPSG:3857",
                        "resolution_m": None,
                        "bands": 1,
                        "nodata": -9999,
                        "bounds": fixture_bounds(),
                        "source": "rasterio",
                        "read_s3": False,
                    }}
                return item
        raise ValidationFailed("Source is not in the configured allowlist.", [])

    def _can_submit(self, source):
        if source["kind"] == "fixture-offline":
            return self.settings.build_executor == "fixture-offline"
        if source["kind"] == "raster-fixture":
            return self.settings.build_executor == "rasterio"
        return bool(self.settings.builds_enabled and self.settings.build_executor == "rasterio")

    def _block_reason(self, source, accepted):
        if not accepted:
            return "Plan exceeds the absolute tile budget. It was not queued."
        if source["kind"] == "s3" and not self.settings.builds_enabled:
            return "Real builds are disabled. No job was queued."
        return "This executor cannot queue that source."

    def _run_rasterio(self, job):
        try:
            if job["source"]["kind"] == "raster-fixture":
                source_path = os.path.join(self.output_root, job["output_prefix"], "source.tif")
                os.makedirs(os.path.dirname(source_path), exist_ok=True)
                meta = write_gradient_geotiff(source_path)
                bounds = meta["bounds"]
            else:
                uri = job["source"].get("uri")
                if self.source_fetch is None:
                    raise PyramidError(
                        "source_reader_unconfigured",
                        "No S3 reader is configured. The object was not fetched and no PNG was written.",
                    )
                source_path = self.source_fetch(uri)
                bounds = job["plan"].get("bounds") or job["source"].get("bounds")
                if not bounds:
                    raise PyramidError("bounds", "S3 inspect did not supply bounds. No PNG was written.")
            destination = os.path.join(self.output_root, job["output_prefix"])

            def should_continue():
                current = self.store.get(job["job_id"])
                return current is not None and not current["cancel_requested"]

            result = render_pyramid(
                source_path,
                destination,
                bounds,
                job["plan"]["zooms"],
                job["plan"]["tile_merge"],
                job["plan"]["resampling"],
                list(RASTER_STOPS),
                completed=job.get("completed") or [],
                hashes=job.get("tile_hashes") or {},
                batch_size=job["plan"].get("batch_size") or self.settings.max_build_tiles,
                should_continue=should_continue,
            )
        except PyramidError as exc:
            job["status"] = "failed"
            job["error"] = {"code": exc.code, "message": exc.message}
            job["tiles_written"] = len(job.get("completed") or [])
            job["real_s3_write"] = False
            job["logs"].append({"at": utcnow(), "message": exc.message})
            job["updated_at"] = utcnow()
            return self.store.save(job)
        current = self.store.get(job["job_id"])
        current["completed"] = result["completed"]
        current["tile_hashes"] = result["hashes"]
        current["tiles_written"] = len(result["completed"])
        current["real_s3_write"] = False
        total = result["total"] or 1
        current["progress"] = {
            "completed_tiles": len(result["completed"]),
            "total_tiles": result["total"],
            "fraction": len(result["completed"]) / total,
        }
        current["checkpoint"] = result["written"][-1] if result["written"] else current.get("checkpoint")
        current["logs"].append({
            "at": utcnow(),
            "message": f"rasterio wrote {len(result['written'])} block(s); {len(result['completed'])}/{result['total']}",
        })
        if result["stopped"] or current["cancel_requested"]:
            current["status"] = "cancelled"
        elif len(result["completed"]) < result["total"]:
            current["status"] = "queued"
        else:
            current["status"] = "succeeded"
            current["output_validation"] = {
                "ok": True,
                "real_s3": False,
                "engine": "rasterio",
                "png_blocks": len(result["completed"]),
            }
        current["updated_at"] = utcnow()
        return self.store.save(current)


def _publish_style(job):
    if job["execution_mode"] == "rasterio":
        return {"type": "color-ramp", "stops": [{**stop, "label": "ramp"} for stop in RASTER_STOPS]}
    return {"type": "color-ramp", "stops": [{"value": 0, "rgba": [70, 130, 180, 255], "label": "fixture"}]}


def _publish_uri(job):
    bucket = job.get("output_bucket")
    if job.get("real_s3_write") and bucket:
        return f"s3://{bucket}/builds/{job['job_id']}/"
    return "synthetic://fixture/build/" + job["job_id"]


def _execution_mode(kind, executor):
    if kind == "fixture-offline":
        return "fixture-offline"
    if executor == "rasterio" and kind in {"raster-fixture", "s3"}:
        return "rasterio"
    return "gio"


def probe_builder():
    missing = []
    for name in ("gio", "osgeo.gdal"):
        try:
            __import__(name if name != "osgeo.gdal" else "osgeo")
            if name == "osgeo.gdal":
                __import__("osgeo.gdal")
        except ImportError:
            missing.append(name)
    return {
        "gio_importable": "gio" not in missing,
        "gdal_importable": "osgeo.gdal" not in missing,
        "missing": missing,
        "ran_build_tiles_task": False,
    }
