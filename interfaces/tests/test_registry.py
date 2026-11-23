import json

import pytest

from geomap_interfaces.errors import RegistryError
from geomap_interfaces.registry import registry_from_obj

from support import _registry


def test_registry_accepts_slash_ids_and_reports_public_fields():
    registry = registry_from_obj(_registry())
    dataset = registry.get("demo/quad")
    assert dataset is not None
    assert dataset.pyramid.block.pixels == 512
    assert dataset.quantitative is None
    public = json.dumps(dataset.assets[0].local)
    assert "source.geojson" in public


def test_registry_rejects_unknown_fields_secrets_and_bad_links():
    payload = _registry()
    payload["datasets"][0]["password"] = "secret"
    with pytest.raises(RegistryError, match="unknown fields"):
        registry_from_obj(payload)

    payload = _registry()
    payload["datasets"][0]["assets"][1]["href"] = "https://user:pass@data.example/quad.json"
    with pytest.raises(RegistryError, match="credentials"):
        registry_from_obj(payload)

    payload = _registry()
    payload["datasets"][0]["id"] = "../secret"
    with pytest.raises(RegistryError, match="dataset id"):
        registry_from_obj(payload)

    payload = _registry()
    payload["datasets"][0]["assets"][0]["local"] = "../secret.txt"
    with pytest.raises(RegistryError, match="escapes"):
        registry_from_obj(payload)


def test_schema_document_names_the_contract_fields():
    from pathlib import Path

    schema = json.loads((Path(__file__).parents[1] / "docs" / "dataset-registry.schema.json").read_text(encoding="utf-8"))
    assert schema["$id"].endswith("geo-map.dataset-registry/v0")
    properties = schema["$defs"]["dataset"]["properties"]
    for name in ("id", "backend", "bounds", "crs", "pyramid", "styles", "revision", "access", "quantitative"):
        assert name in properties
    assert properties["backend"]["enum"] == ["png", "cog"]
    pyramid = schema["$defs"]["pyramid"]["properties"]
    assert set(pyramid["zooms"]["$ref"] and schema["$defs"]["zooms"]["required"]) >= {
        "native",
        "stored",
        "view_min",
        "view_max",
    }
