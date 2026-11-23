"""Use cases for the staging layer registry.

Writes update the registry and the audit log only. They do not regenerate
PNG pyramids, rewrite COGs, or touch legacy setting.ini files.
"""

import hmac

from .canonical import clone, utcnow
from .effects import effects
from .errors import ConfirmationRequired, Conflict, NotFound, ValidationFailed
from .legacy import export_legacy, legacy_to_client_layer
from .preview_urls import describe_preview
from .repository import new_audit
from .schema_contract import (
    CONFIRM_CREATE_DRAFT,
    CONFIRM_IMPORT,
    CONFIRM_PUBLISH,
    CONFIRM_RESTORE,
    INVENTORY_REGISTRY,
    INVENTORY_SYNTHETIC,
    ROLE_ADMIN,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
)
from .validate import (
    build_stored_record,
    digest_input,
    editable_from_stored,
    publish_blockers,
    structural_errors,
    validate_client_layer,
)


def _revision(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationFailed(
            "expected_revision must be an integer.",
            [{"field": "expected_revision", "code": "revision", "message": "expected_revision must be an integer."}],
        )
    return value


def _changed(before, after):
    if before is None:
        return sorted(after.keys())
    changed = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed.append(key)
    return changed


def _confirm(provided, expected):
    if not isinstance(provided, str) or not hmac.compare_digest(provided, expected):
        raise ConfirmationRequired(
            f"Confirmation phrase must be exactly {expected}.",
            [{"field": "confirmation", "code": "confirmation", "message": expected}],
        )


class LayerService:
    def __init__(self, repository, preview_hosts=(), tile_backend_base_url="", tile_path_order="map"):
        self.repository = repository
        self.preview_hosts = tuple(preview_hosts)
        self.tile_backend_base_url = tile_backend_base_url or ""
        self.tile_path_order = tile_path_order or "map"

    def _describe(self, record):
        return describe_preview(
            record,
            self.preview_hosts,
            tile_backend_base_url=self.tile_backend_base_url,
            tile_path_order=self.tile_path_order,
        )

    def list_layers(self, query=None, status=None, limit=100):
        limit = max(1, min(int(limit or 100), 500))
        needle = (query or "").strip().lower()
        rows = []
        for record in self.repository.list_layers():
            if status and record["status"] != status:
                continue
            if needle and needle not in record["tag"].lower() and needle not in record["title"].lower() and needle not in record["backend"]:
                continue
            rows.append(_summary(record))
        truncated = len(rows) > limit
        return {"layers": rows[:limit], "truncated": truncated, "inventory_note": _inventory_note(rows)}

    def get_layer(self, tag):
        record = self._require(tag)
        return {"layer": record, "preview": self._describe(record), "effects": effects(registry_updated=False)}

    def preview(self, layer):
        normalized, issues = validate_client_layer(layer, self.preview_hosts)
        errors = structural_errors(issues)
        summary = {
            "normalized": normalized,
            "validation": {
                "valid_for_draft": not errors,
                "valid_for_publish": not errors and not publish_blockers(issues),
                "errors": errors,
                "publish_blockers": publish_blockers(issues),
                "warnings": [item for item in issues if item["severity"] == "warning"],
            },
            "content_digest": digest_input(normalized) if not errors else None,
            "preview": self._describe(normalized),
            "effects": effects(registry_updated=False),
            "persisted": False,
        }
        return summary

    def create_draft(self, layer, content_digest, confirmation, actor, role):
        _confirm(confirmation, CONFIRM_CREATE_DRAFT)
        normalized, issues = self._ready(layer)
        digest = digest_input(normalized)
        if not isinstance(content_digest, str) or not hmac.compare_digest(content_digest, digest):
            raise Conflict("Preview digest does not match this payload. Run preview again. Nothing was saved.")
        record = self._store_new(
            normalized,
            issues,
            actor=actor,
            role=role,
            status=STATUS_DRAFT,
            synthetic=False,
            action="create-draft",
        )
        return self._write_result(record)

    def update_layer(self, tag, layer, expected_revision, actor, role):
        expected_revision = _revision(expected_revision)
        current = self._require(tag)
        if layer.get("tag") not in {None, tag}:
            raise ValidationFailed("The tag is the layer identity and cannot be changed.", [])
        merged = editable_from_stored(current)
        for key, value in layer.items():
            if key == "tag":
                continue
            merged[key] = value
        merged["tag"] = tag
        normalized, issues = self._ready(merged)
        record = build_stored_record(
            normalized,
            issues,
            actor=actor,
            now=utcnow(),
            revision=int(current["revision"]) + 1,
            status=current["status"],
            synthetic=current["synthetic"],
            inventory=current["inventory"],
            created_at=current["created_at"],
            legacy_compat=current["legacy_compat"],
        )
        saved = self._commit_update(current, record, expected_revision, actor, role, "update")
        return self._write_result(saved)

    def publish(self, tag, expected_revision, confirmation, actor, role):
        _confirm(confirmation, CONFIRM_PUBLISH)
        expected_revision = _revision(expected_revision)
        current = self._require(tag)
        normalized, issues = validate_client_layer(editable_from_stored(current), self.preview_hosts)
        errors = structural_errors(issues)
        blockers = publish_blockers(issues)
        if errors or blockers:
            raise ValidationFailed(
                "Publish is blocked. The registry was not changed and no PNGs were generated.",
                errors + blockers,
            )
        record = build_stored_record(
            normalized,
            issues,
            actor=actor,
            now=utcnow(),
            revision=int(current["revision"]) + 1,
            status=STATUS_PUBLISHED,
            synthetic=current["synthetic"],
            inventory=current["inventory"],
            created_at=current["created_at"],
            legacy_compat=current["legacy_compat"],
        )
        saved = self._commit_update(current, record, expected_revision, actor, role, "publish")
        return self._write_result(saved)

    def import_legacy(self, tag, setting, color_txt, confirmation, actor, role, recorded_at=None):
        _confirm(confirmation, CONFIRM_IMPORT)
        if self.repository.get(tag) is not None:
            raise Conflict(f"Layer {tag} already exists. Legacy import does not overwrite it.")
        layer, compat = legacy_to_client_layer(tag, setting, color_txt or "", recorded_at or utcnow())
        normalized, issues = self._ready(layer)
        record = self._store_new(
            normalized,
            issues,
            actor=actor,
            role=role,
            status=STATUS_DRAFT,
            synthetic=False,
            action="import-legacy",
            legacy_compat=compat,
        )
        result = self._write_result(record)
        result["legacy_namespace"] = compat["namespace"]
        return result

    def export_legacy(self, tag):
        record = self._require(tag)
        exported = export_legacy(record)
        exported["effects"] = effects(registry_updated=False)
        return exported

    def list_audit(self, tag):
        self._require(tag)
        return {"tag": tag, "audit": self.repository.list_audit(tag)}

    def restore(self, tag, audit_id, expected_revision, confirmation, actor, role):
        _confirm(confirmation, CONFIRM_RESTORE)
        expected_revision = _revision(expected_revision)
        current = self._require(tag)
        snapshot = None
        for event in self.repository.list_audit(tag):
            if event["audit_id"] == audit_id:
                snapshot = event.get("snapshot")
                break
        if not snapshot:
            raise NotFound(f"No audit snapshot {audit_id} exists for {tag}.")
        normalized, issues = self._ready(editable_from_stored(snapshot))
        record = build_stored_record(
            normalized,
            issues,
            actor=actor,
            now=utcnow(),
            revision=int(current["revision"]) + 1,
            status=snapshot["status"] if snapshot["status"] in {STATUS_DRAFT, STATUS_PUBLISHED} else current["status"],
            synthetic=current["synthetic"],
            inventory=current["inventory"],
            created_at=current["created_at"],
            legacy_compat=snapshot.get("legacy_compat") or current["legacy_compat"],
        )
        if record["status"] == STATUS_PUBLISHED and not record["validation"]["valid_for_publish"]:
            record["status"] = STATUS_DRAFT
        saved = self._commit_update(current, record, expected_revision, actor, role, "restore")
        return self._write_result(saved)

    def register_validated_output(self, layer, actor, role):
        """Store a validated build as a registry record. It is not a synthetic fixture."""
        incoming = clone(layer)
        incoming.pop("status", None)
        incoming.pop("synthetic", None)
        normalized, issues = self._ready(incoming)
        if publish_blockers(issues):
            raise ValidationFailed("The build output is not publishable.", publish_blockers(issues))
        return self._store_new(
            normalized,
            issues,
            actor=actor,
            role=role,
            status=STATUS_PUBLISHED,
            synthetic=False,
            action="register-build-output",
            inventory=INVENTORY_REGISTRY,
        )

    def seed_fixture(self, layer, actor, role):
        """Internal seed path. Forces the synthetic inventory label."""
        incoming = clone(layer)
        incoming.pop("status", None)
        incoming.pop("synthetic", None)
        status = layer.get("status", STATUS_DRAFT)
        if status not in {STATUS_DRAFT, STATUS_PUBLISHED}:
            status = STATUS_DRAFT
        normalized, issues = self._ready(incoming)
        if status == STATUS_PUBLISHED and publish_blockers(issues):
            raise ValidationFailed("Synthetic published fixtures must be publishable.", publish_blockers(issues))
        return self._store_new(
            normalized,
            issues,
            actor=actor,
            role=role,
            status=status,
            synthetic=True,
            action="seed-fixture",
            inventory=INVENTORY_SYNTHETIC,
        )

    def _ready(self, layer):
        normalized, issues = validate_client_layer(layer, self.preview_hosts)
        errors = structural_errors(issues)
        if errors:
            raise ValidationFailed("The layer metadata is not valid. Nothing was saved.", errors)
        return normalized, issues

    def _require(self, tag):
        record = self.repository.get(tag)
        if record is None:
            raise NotFound(f"No layer is registered for {tag}.")
        return record

    def _store_new(self, normalized, issues, *, actor, role, status, synthetic, action, legacy_compat=None, inventory=None):
        now = utcnow()
        record = build_stored_record(
            normalized,
            issues,
            actor=actor,
            now=now,
            revision=1,
            status=status,
            synthetic=synthetic,
            inventory=inventory or ("synthetic-fixture" if synthetic else "registry"),
            legacy_compat=legacy_compat,
        )
        audit = new_audit(
            tag=record["tag"],
            action=action,
            actor=actor,
            role=role,
            from_revision=0,
            to_revision=1,
            changed_fields=_changed(None, record),
            snapshot=record,
        )
        return self.repository.create(record, audit)

    def _commit_update(self, current, record, expected_revision, actor, role, action):
        if int(expected_revision) != int(current["revision"]):
            raise Conflict(
                f"Revision conflict for {current['tag']}. Expected {expected_revision} and found {current['revision']}."
            )
        audit = new_audit(
            tag=record["tag"],
            action=action,
            actor=actor,
            role=role,
            from_revision=int(current["revision"]),
            to_revision=int(record["revision"]),
            changed_fields=_changed(current, record),
            snapshot=record,
        )
        return self.repository.update(record["tag"], record, expected_revision, audit)

    def _write_result(self, record):
        return {
            "layer": record,
            "preview": self._describe(record),
            "effects": effects(registry_updated=True),
        }


def _summary(record):
    pyramid = record.get("pyramid") or {}
    cog = record.get("cog") or {}
    return {
        "tag": record["tag"],
        "title": record["title"],
        "status": record["status"],
        "revision": record["revision"],
        "synthetic": record["synthetic"],
        "inventory": record["inventory"],
        "backend": record["backend"],
        "processed_levels": pyramid.get("processed_levels") or [],
        "tile_pixel_size": pyramid.get("tile_pixel_size"),
        "tile_merge": pyramid.get("tile_merge"),
        "block_size": cog.get("block_size"),
        "valid_for_publish": record["validation"]["valid_for_publish"],
        "publish_blocker_count": len(record["validation"]["publish_blockers"]),
        "updated_at": record["updated_at"],
    }


def _inventory_note(rows):
    if rows and all(row["synthetic"] for row in rows):
        return "Every layer in this result is a labeled synthetic fixture. This is not the live tile inventory."
    if any(row["synthetic"] for row in rows):
        return "Rows badged synthetic are fixtures. They were not read from the live tile bucket."
    return "Registry contents are whatever operators saved here. This list is not a scan of the live tile bucket."


# Imported by seed to keep the role constant visible to tests.
SEED_ROLE = ROLE_ADMIN
