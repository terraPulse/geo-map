"""Build queue and worker. Real GDAL builds stay locked; fixtures are labeled."""

import os
import threading
import uuid

from .build_allow import output_prefix_for, parse_allowlist, resolve_key
from .canonical import content_digest, utcnow
from .errors import Conflict, NotFound, ValidationFailed
from .png_codec import encode_rgba, png_size
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
    def __init__(self, store, settings, layer_service, output_root):
        self.store = store
        self.settings = settings
        self.layers = layer_service
        self.output_root = output_root
        self._lock = threading.Lock()

    def config(self):
        runtime = probe_builder()
        return {
            "real_builds_enabled": bool(self.settings.builds_enabled),
            "fixture_builds": self.settings.build_executor == "fixture-offline",
            "executor": self.settings.build_executor,
            "runtime": runtime,
            "max_tiles": self.settings.max_build_tiles,
            "max_merge": MAX_MERGE,
            "output_configured": bool(self.settings.output_prefix),
            "sources": [item["id"] for item in self._sources()],
            "real_s3_writes": False,
            "note": (
                "Real S3 builds are disabled until an allowlisted source and the gio/GDAL worker are configured. "
                "A fixture job is labeled fixture-offline and is not an S3 build."
            ),
        }

    def list_sources(self):
        return {"sources": self._sources(), "bucket_scan": False}

    def inspect(self, source_id, key=None):
        source = self._source(source_id)
        if source["kind"] == "fixture-offline":
            info = dict(source["inspection"])
            info["source_id"] = source_id
            info["key"] = None
            return info
        if key is None:
            raise ValidationFailed("An object key is required for an S3 source.", [])
        uri = resolve_key(source["uri"], key)
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
            "pixel_estimate": pixels,
            "storage_bytes_upper": pixels * 4,
            "approximate": True,
            "sample_tiles": sample,
            "layout": "version-2-tiles",
            "output_note": "A later real build would write a new version prefix. This plan writes nothing.",
        }
        accepted = 0 < total <= self.settings.max_build_tiles and merge <= MAX_MERGE
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
            "execution_mode": "fixture-offline" if plan["source_kind"] == "fixture-offline" else "gio",
            "real_s3_write": False,
            "actor": actor,
            "role": role,
            "idempotency_key": key,
            "plan_digest": plan["content_digest"],
            "plan": plan,
            "source": {"id": plan["source_id"], "kind": plan["source_kind"]},
            "output_prefix": prefix,
            "attempt": 1,
            "cancel_requested": False,
            "progress": {"completed_tiles": 0, "total_tiles": plan["tile_count"], "fraction": 0},
            "checkpoint": None,
            "logs": [{"at": utcnow(), "message": "queued"}],
            "tiles_written": 0,
            "output_validation": {"ok": False, "real_s3": False},
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
        return {"job": self.store.save(job), "duplicate": False}

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
            job["progress"] = {"completed_tiles": 0, "total_tiles": job["plan"]["tile_count"], "fraction": 0}
            job["tiles_written"] = 0
            job["output_validation"] = {"ok": False, "real_s3": False}
            job["logs"].append({"at": utcnow(), "message": f"retry {job['attempt']} by {actor}"})
            job["updated_at"] = utcnow()
            return {"job": self.store.save(job)}

    def run_once(self):
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
        return self._refuse_gio(job)

    def publish(self, job_id, actor, role, confirmation, expected_revision=None):
        if confirmation != CONFIRM_PUBLISH:
            raise ValidationFailed("Confirmation phrase must be exactly publish-registry-only.", [])
        job = self._require(job_id)
        if job["status"] != "succeeded" or not job["output_validation"].get("ok"):
            raise Conflict("Only a validated successful build can be published.", [])
        layer_body = {
            "tag": job["plan"]["tag"],
            "title": job["plan"]["title"],
            "backend": "png-pyramid",
            "pyramid": {
                "layout": "version-2-tiles",
                "tile_pixel_size": 256,
                "tile_merge": job["plan"]["tile_merge"],
                "min_static_level": job["plan"]["zooms"][0],
                "min_dynamic_level": job["plan"]["zooms"][-1],
                "processed_levels": job["plan"]["zooms"],
                "version": 2.0,
                "aggregate": job["plan"]["aggregate"],
                "persistent": True,
            },
            "cog": None,
            "bounds": FIXTURE_SOURCE["inspection"]["bounds"],
            "style": {"type": "color-ramp", "stops": [{"value": 0, "rgba": [70, 130, 180, 255], "label": "fixture"}]},
            "nodata": {"min_value": None, "max_value": None, "fill_nodata": None, "raster_nodata": None},
            "source_revisions": [
                {
                    "revision_id": job["job_id"][:12],
                    "uri": "synthetic://fixture/build/" + job["job_id"],
                    "note": "fixture-offline build. Not an S3 object and not a production tile.",
                    "recorded_at": utcnow(),
                }
            ],
            "authorized_tile_template": None,
        }
        normalized, issues = validate_client_layer(layer_body)
        if structural_errors(issues):
            raise ValidationFailed("Build metadata is not publishable.", structural_errors(issues))
        stored = self.layers.seed_fixture({**layer_body, "status": "published"}, actor=actor, role=role)
        return {
            "layer": stored,
            "effects": {
                "registry_updated": True,
                "png_pyramid_regenerated": False,
                "real_s3_write": False,
                "execution_mode": job["execution_mode"],
            },
            "build": {"job_id": job["job_id"], "real_s3_write": False, "synthetic": True},
        }

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
        for item in self.settings.source_allowlist:
            rows.append({"id": item["id"], "kind": "s3", "title": item["id"], "uri": item["uri"], "real_s3": False})
        return rows

    def _source(self, source_id):
        for item in self._sources():
            if item["id"] == source_id:
                if item["kind"] == "fixture-offline":
                    return FIXTURE_SOURCE
                return item
        raise ValidationFailed("Source is not in the configured allowlist.", [])

    def _can_submit(self, source):
        if source["kind"] == "fixture-offline":
            return self.settings.build_executor == "fixture-offline"
        return bool(self.settings.builds_enabled and self.settings.build_executor == "gio")

    def _block_reason(self, source, accepted):
        if not accepted:
            return "Plan exceeds the tile cap. It was not queued."
        if source["kind"] != "fixture-offline" and not self.settings.builds_enabled:
            return "Real builds are disabled. No job was queued."
        return "This executor cannot queue that source."


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
