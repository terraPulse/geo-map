"""Load and insert clearly labeled synthetic fixtures.

Fixtures are not the live inventory. Seed inserts only missing tags and
never overwrites an existing revision.
"""

import json
from pathlib import Path

from .errors import Conflict, ValidationFailed
from .schema_contract import INVENTORY_SYNTHETIC, SCHEMA_ID


def fixture_path():
    packaged = Path(__file__).with_name("synthetic_fixtures.json")
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_layers.json"


def load_fixture_document(path=None):
    path = Path(path) if path else fixture_path()
    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    note = document.get("schema_note", "")
    if "SYNTHETIC" not in note.upper():
        raise ValueError("Fixture document must declare that it is synthetic.")
    layers = document.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("Fixture document has no layers.")
    return layers


def seed_missing(service, layers=None, actor="fixture-seed", role="layer-admin"):
    """Insert fixtures that are absent. Existing tags are skipped."""
    layers = load_fixture_document() if layers is None else layers
    inserted = []
    skipped = []
    for layer in layers:
        tag = layer.get("tag")
        if service.repository.get(tag) is not None:
            skipped.append(tag)
            continue
        try:
            service.seed_fixture(layer, actor=actor, role=role)
        except Conflict:
            skipped.append(tag)
            continue
        stored = service.repository.get(tag)
        if not stored or not stored["synthetic"] or stored["inventory"] != INVENTORY_SYNTHETIC:
            raise ValidationFailed("Fixture seed refused to store a record that is not labeled synthetic.", [])
        if stored["schema"] != SCHEMA_ID:
            raise ValidationFailed("Fixture seed wrote an unexpected schema.", [])
        inserted.append(tag)
    return {"inserted": inserted, "skipped": skipped, "synthetic": True}
