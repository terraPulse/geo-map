"""DynamoDB repository for the staging registry table.

The Lambda role is expected to allow GetItem, PutItem, Query, and
TransactWriteItems on this table only. DeleteItem and Scan are not used.
boto3 is imported only when a real client is requested.
"""

import json

from .canonical import clone
from .errors import Conflict, NotFound
from .repository import LayerRepository


class ConditionalWriteFailed(Exception):
    pass


def _is_conditional(exc):
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    code = response.get("Error", {}).get("Code", "")
    return code in {"ConditionalCheckFailedException", "TransactionCanceledException"}


class DynamoRepository(LayerRepository):
    def __init__(self, client, table_name):
        if not table_name:
            raise ValueError("table_name is required")
        self.client = client
        self.table_name = table_name

    def get(self, tag):
        result = self.client.get_item(
            TableName=self.table_name,
            Key={"pk": {"S": "LAYER"}, "sk": {"S": tag}},
            ConsistentRead=True,
        )
        item = result.get("Item")
        if not item:
            return None
        return json.loads(item["payload"]["S"])

    def create(self, record, audit):
        try:
            self._transact(
                [
                    self._put_layer(record, condition="attribute_not_exists(sk)"),
                    self._put_audit(audit),
                ]
            )
        except ConditionalWriteFailed as exc:
            raise Conflict(
                f"Layer {record['tag']} already exists. Import and create never overwrite silently."
            ) from exc
        return clone(record)

    def update(self, tag, record, expected_revision, audit):
        current = self.get(tag)
        if current is None:
            raise NotFound(f"No layer is registered for {tag}.")
        try:
            self._transact(
                [
                    self._put_layer(
                        record,
                        condition="revision = :expected",
                        values={":expected": {"N": str(int(expected_revision))}},
                    ),
                    self._put_audit(audit),
                ]
            )
        except ConditionalWriteFailed as exc:
            found = self.get(tag)
            found_revision = found["revision"] if found else "missing"
            raise Conflict(
                f"Revision conflict for {tag}. Expected {expected_revision} and found {found_revision}."
            ) from exc
        return clone(record)

    def list_layers(self):
        records = []
        start_key = None
        while True:
            kwargs = {
                "TableName": self.table_name,
                "KeyConditionExpression": "pk = :pk",
                "ExpressionAttributeValues": {":pk": {"S": "LAYER"}},
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            result = self.client.query(**kwargs)
            for item in result.get("Items", []):
                records.append(json.loads(item["payload"]["S"]))
            start_key = result.get("LastEvaluatedKey")
            if not start_key:
                break
        records.sort(key=lambda item: item["tag"])
        return records

    def list_audit(self, tag):
        result = self.client.query(
            TableName=self.table_name,
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": {"S": f"AUDIT#{tag}"}},
            ScanIndexForward=False,
        )
        return [json.loads(item["payload"]["S"]) for item in result.get("Items", [])]

    def _put_layer(self, record, condition, values=None):
        item = {
            "pk": {"S": "LAYER"},
            "sk": {"S": record["tag"]},
            "revision": {"N": str(int(record["revision"]))},
            "status": {"S": record["status"]},
            "synthetic": {"S": "true" if record["synthetic"] else "false"},
            "payload": {"S": json.dumps(record, sort_keys=True)},
        }
        put = {"TableName": self.table_name, "Item": item, "ConditionExpression": condition}
        if values:
            put["ExpressionAttributeValues"] = values
        return {"Put": put}

    def _put_audit(self, audit):
        item = {
            "pk": {"S": f"AUDIT#{audit['tag']}"},
            "sk": {"S": f"{audit['at']}#{audit['audit_id']}"},
            "payload": {"S": json.dumps(audit, sort_keys=True)},
        }
        return {"Put": {"TableName": self.table_name, "Item": item}}

    def _transact(self, items):
        try:
            self.client.transact_write_items(TransactItems=items)
        except ConditionalWriteFailed:
            raise
        except Exception as exc:
            if _is_conditional(exc):
                raise ConditionalWriteFailed(str(exc)) from exc
            raise


def boto3_client(region):
    import boto3

    return boto3.client("dynamodb", region_name=region)
