"""Turn one queue message into a Batch SubmitJob call.

The handler constructs a client only when AWS invokes it. Tests call
submit_message with a fake client and never import boto3.
"""

import json
import os


def submit_message(body, client, job_queue, job_definition):
    job_id = body.get("job_id") or ""
    if not job_id or "/" in job_id:
        raise ValueError("job_id is required")
    if not body.get("bounds") or not body.get("zooms"):
        raise ValueError("bounds and zooms are required")
    response = client.submit_job(
        jobName="pyramid-" + job_id[:40],
        jobQueue=job_queue,
        jobDefinition=job_definition,
        containerOverrides={
            "environment": [{"name": "BUILD_SPEC_JSON", "value": json.dumps(body)}],
        },
    )
    return {"batch_job_id": response.get("jobId"), "job_name": "pyramid-" + job_id[:40]}


def handler(event, context):
    import boto3

    del context
    client = boto3.client("batch", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    queue = os.environ["BUILD_JOB_QUEUE"]
    definition = os.environ["BUILD_JOB_DEFINITION"]
    submitted = []
    for record in event.get("Records") or []:
        body = json.loads(record["body"])
        submitted.append(submit_message(body, client, queue, definition))
    return {"submitted": submitted}
