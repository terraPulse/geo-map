"""Canonical JSON and clocks. No network and no filesystem."""

import copy
import hashlib
import json
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_digest(value):
    return sha256_text(canonical_json(value))


def clone(value):
    return copy.deepcopy(value)
