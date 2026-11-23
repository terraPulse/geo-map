"""Turn one queue message into a Batch SubmitJob call.

The image, queue, and job definition come from the function environment.
A message that names an image or a bucket is rejected.
"""

import json
import os

from .image_policy import validate_image_uri
from .s3_source import split_allowlisted


def submit_message(body, client, job_queue, job_definition, image_uri, allowlist):
    if not isinstance(body, dict):
        raise ValueError("queue message must be an object")
    if body.get("image") or body.get("output_bucket") or body.get("job_definition") or body.get("job_queue"):
        raise ValueError("The queue message cannot choose an image, queue, or bucket.")
    job_id = body.get("job_id") or ""
    if len(job_id) != 32 or any(ch not in "0123456789abcdef" for ch in job_id):
        raise ValueError("job_id is required")
    if not body.get("bounds") or not body.get("zooms"):
        raise ValueError("bounds and zooms are required")
    validate_image_uri(image_uri)
    if not job_queue or not job_definition or ".." in job_queue or ".." in job_definition:
        raise ValueError("Batch queue and job definition must come from the function environment.")
    source = body.get("source_uri") or ""
    if source.startswith("s3://"):
        split_allowlisted(source, allowlist)
    trusted = {
        "job_id": job_id,
        "source_uri": source,
        "allowlist": allowlist,
        "bounds": body["bounds"],
        "zooms": body["zooms"],
        "tile_merge": body.get("tile_merge", 1),
        "resampling": body.get("resampling", "nearest"),
        "stops": body.get("stops"),
        "output_prefix": f"builds/{job_id}",
        "output_dir": "/tmp/pyramid-out",
        "batch_size": body.get("batch_size"),
        "hashes": body.get("hashes") or {},
    }
    response = client.submit_job(
        jobName="pyramid-" + job_id[:40],
        jobQueue=job_queue,
        jobDefinition=job_definition,
        containerOverrides={
            "environment": [
                {"name": "BUILD_SPEC_JSON", "value": json.dumps(trusted)},
                {"name": "BUILD_ALLOW_S3", "value": "1"},
                {"name": "BUILD_SOURCE_ALLOWLIST", "value": allowlist},
            ],
        },
    )
    return {
        "batch_job_id": response.get("jobId"),
        "job_name": "pyramid-" + job_id[:40],
        "image_from_message": False,
        "spec": trusted,
    }


def handler(event, context):
    import boto3

    del context
    client = boto3.client("batch", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    queue = os.environ["BUILD_JOB_QUEUE"]
    definition = os.environ["BUILD_JOB_DEFINITION"]
    image = os.environ["BUILD_IMAGE_URI"]
    allowlist = os.environ.get("BUILD_SOURCE_ALLOWLIST") or ""
    submitted = []
    for record in event.get("Records") or []:
        body = json.loads(record["body"])
        submitted.append(submit_message(body, client, queue, definition, image, allowlist))
    return {"submitted": submitted}
