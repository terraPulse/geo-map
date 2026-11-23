"""geomap.png_pyramid 1.0.0 manifest for one validated build.

The layer object has no bucket and no URL. That matches the test renderer
registry. The output bucket stays beside the document, for the operator.
"""

from .renderer_preview import ADAPTER, ADAPTER_VERSION


def renderer_manifest(job):
    plan = job["plan"]
    zooms = [int(level) for level in plan["zooms"]]
    job_id = job["job_id"]
    storage = "s3" if job.get("real_s3_write") else "package"
    layer = {
        "id": plan["tag"],
        "title": plan["title"],
        "fixture": False,
        "storage": storage,
        "key_prefix": f"builds/{job_id}",
        "tile_merge": int(plan["tile_merge"]),
        "tile_size": 256,
        "version": 2,
        "processed_levels": zooms,
        "max_zoom": max(zooms),
    }
    return {
        "adapter": ADAPTER,
        "adapter_version": ADAPTER_VERSION,
        "live_aws_verified": False,
        "output_bucket": job.get("output_bucket"),
        "layers": [layer],
    }
