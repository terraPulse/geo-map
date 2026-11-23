"""Registry repositories.

Memory and file adapters are the test and local implementations. The
DynamoDB adapter is separate so local tests do not import boto3. All
adapters enforce optimistic revision checks and append an audit record.
"""

import json
import os
import threading
import uuid
from urllib.parse import quote

from .canonical import clone, utcnow
from .errors import Conflict, NotFound

try:
    import fcntl
except ImportError:  # pragma: no cover - local agent is Linux
    fcntl = None


class LayerRepository:
    def get(self, tag):
        raise NotImplementedError

    def create(self, record, audit):
        raise NotImplementedError

    def update(self, tag, record, expected_revision, audit):
        raise NotImplementedError

    def list_layers(self):
        raise NotImplementedError

    def list_audit(self, tag):
        raise NotImplementedError


class MemoryRepository(LayerRepository):
    def __init__(self):
        self._layers = {}
        self._audit = {}
        self._lock = threading.Lock()

    def get(self, tag):
        with self._lock:
            record = self._layers.get(tag)
            return clone(record) if record else None

    def create(self, record, audit):
        tag = record["tag"]
        with self._lock:
            if tag in self._layers:
                raise Conflict(f"Layer {tag} already exists. Import and create never overwrite silently.")
            self._layers[tag] = clone(record)
            self._audit.setdefault(tag, []).append(clone(audit))
            return clone(record)

    def update(self, tag, record, expected_revision, audit):
        with self._lock:
            current = self._layers.get(tag)
            if current is None:
                raise NotFound(f"No layer is registered for {tag}.")
            if int(current["revision"]) != int(expected_revision):
                raise Conflict(
                    f"Revision conflict for {tag}. Expected {expected_revision} and found {current['revision']}."
                )
            self._layers[tag] = clone(record)
            self._audit.setdefault(tag, []).append(clone(audit))
            return clone(record)

    def list_layers(self):
        with self._lock:
            return [clone(self._layers[tag]) for tag in sorted(self._layers)]

    def list_audit(self, tag):
        with self._lock:
            return [clone(item) for item in reversed(self._audit.get(tag, []))]


def _encode_tag(tag):
    return quote(tag, safe="")


class FileRepository(LayerRepository):
    """One JSON document per layer under a directory the process owns."""

    def __init__(self, root):
        self.root = root
        self._thread = threading.Lock()
        os.makedirs(os.path.join(root, "layers"), exist_ok=True)
        os.makedirs(os.path.join(root, "audit"), exist_ok=True)

    def _layer_path(self, tag):
        return os.path.join(self.root, "layers", _encode_tag(tag) + ".json")

    def _audit_path(self, tag):
        return os.path.join(self.root, "audit", _encode_tag(tag) + ".jsonl")

    def _lock(self):
        return _FileLock(os.path.join(self.root, ".lock"), self._thread)

    def get(self, tag):
        path = self._layer_path(tag)
        with self._lock():
            if not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)

    def create(self, record, audit):
        path = self._layer_path(record["tag"])
        with self._lock():
            if os.path.exists(path):
                raise Conflict(
                    f"Layer {record['tag']} already exists. Import and create never overwrite silently."
                )
            self._write_json(path, record)
            self._append_audit(record["tag"], audit)
            return clone(record)

    def update(self, tag, record, expected_revision, audit):
        path = self._layer_path(tag)
        with self._lock():
            if not os.path.exists(path):
                raise NotFound(f"No layer is registered for {tag}.")
            with open(path, "r", encoding="utf-8") as handle:
                current = json.load(handle)
            if int(current["revision"]) != int(expected_revision):
                raise Conflict(
                    f"Revision conflict for {tag}. Expected {expected_revision} and found {current['revision']}."
                )
            self._write_json(path, record)
            self._append_audit(tag, audit)
            return clone(record)

    def list_layers(self):
        directory = os.path.join(self.root, "layers")
        with self._lock():
            records = []
            for name in sorted(os.listdir(directory)):
                if not name.endswith(".json"):
                    continue
                with open(os.path.join(directory, name), "r", encoding="utf-8") as handle:
                    records.append(json.load(handle))
            records.sort(key=lambda item: item["tag"])
            return records

    def list_audit(self, tag):
        path = self._audit_path(tag)
        with self._lock():
            if not os.path.exists(path):
                return []
            rows = []
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
            rows.reverse()
            return rows

    def _write_json(self, path, record):
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)

    def _append_audit(self, tag, audit):
        path = self._audit_path(tag)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(audit, sort_keys=True) + "\n")


class _FileLock:
    def __init__(self, path, thread_lock):
        self.path = path
        self.thread_lock = thread_lock
        self.handle = None

    def __enter__(self):
        self.thread_lock.acquire()
        self.handle = open(self.path, "a+", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.handle is not None and fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                self.handle.close()
        finally:
            self.thread_lock.release()


def new_audit(*, tag, action, actor, role, from_revision, to_revision, changed_fields, snapshot):
    return {
        "audit_id": uuid.uuid4().hex,
        "tag": tag,
        "action": action,
        "actor_sub": actor,
        "actor_role": role,
        "at": utcnow(),
        "from_revision": from_revision,
        "to_revision": to_revision,
        "changed_fields": list(changed_fields),
        "snapshot": clone(snapshot),
        "effects": {
            "png_pyramid_regenerated": False,
            "tile_bytes_written": False,
            "legacy_setting_ini_written": False,
        },
    }
