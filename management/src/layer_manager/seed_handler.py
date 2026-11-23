"""Custom-resource seed. Inserts labeled fixtures and does not delete them."""

from .errors import ConfigurationError
from .fixtures_seed import seed_missing
from .schema_contract import AUTHORIZED_ACCOUNT, AUTHORIZED_REGION


def assert_staging_stack(event):
    stack_id = event.get("StackId", "")
    expected = f"arn:aws:cloudformation:{AUTHORIZED_REGION}:{AUTHORIZED_ACCOUNT}:stack/"
    if not stack_id.startswith(expected):
        raise ConfigurationError("Seed refused because the stack is not the authorized us-west-2 staging account.")


def handle_seed_event(event, service, send_response):
    try:
        request_type = event.get("RequestType")
        if request_type == "Delete":
            send_response(
                event,
                "SUCCESS",
                {"Deleted": "false", "Reason": "no-op; deleting the stack removes the staging table"},
            )
            return {"deleted": False}
        if str((event.get("ResourceProperties") or {}).get("SeedSyntheticFixtures", "")).lower() not in {"true", "1"}:
            send_response(event, "SUCCESS", {"Inserted": 0, "Skipped": 0, "Seeded": "false"})
            return {"seeded": False, "inserted": [], "skipped": []}
        result = seed_missing(service, actor="staging-seed", role="layer-admin")
        send_response(
            event,
            "SUCCESS",
            {"Inserted": len(result["inserted"]), "Skipped": len(result["skipped"]), "Seeded": "true"},
        )
        return result
    except Exception as exc:
        send_response(event, "FAILED", {"Error": type(exc).__name__})
        return {"failed": type(exc).__name__}
