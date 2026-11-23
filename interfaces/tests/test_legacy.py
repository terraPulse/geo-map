import json

from geomap_interfaces.legacy import dataset_from_legacy, import_legacy_tree
from geomap_interfaces.registry import registry_from_obj, registry_to_obj


LEGACY = {
    "title": "Water frequency",
    "version": 2.0,
    "tile_merge": 8,
    "processed_levels": [3, 6, 9],
    "min_static_level": 3,
    "min_dynamic_level": 12,
    "visible": True,
    "file": "s3://secret-bucket/data/water.tif",
    "color": "s3://secret-bucket/color.txt",
    "password": "do-not-copy",
    "burn_band": {"input": "s3://secret-bucket/hillshade.tif", "offset": 180},
}


def test_legacy_json_import_drops_source_locations():
    dataset = dataset_from_legacy("lincoln/water_freq/y2025", json.dumps(LEGACY))
    registry = registry_from_obj({"schema": "geo-map.dataset-registry/v0", "datasets": [dataset]})
    encoded = json.dumps(registry_to_obj(registry))
    assert "secret-bucket" not in encoded
    assert "do-not-copy" not in encoded
    assert "water.tif" not in encoded
    imported = registry.get("lincoln/water_freq/y2025")
    assert imported.pyramid.block.pixels == 2048
    assert imported.pyramid.zooms.stored == (3, 6, 9)
    assert imported.pyramid.zooms.native == 12
    assert imported.pyramid.zooms.view_max == 12
    assert imported.legacy.source_scheme == "s3"
    assert imported.legacy.bounds_source == "assumed_web_mercator_world"
    assert imported.quantitative is None


def test_legacy_ini_and_hidden_layer(tmp_path):
    text = "\n".join(
        [
            "[map]",
            "title = Slope",
            "version = 1.0",
            "tile_merge = 4",
            "processed_levels = 2, 4",
            "visible = false",
            "file = /var/private/slope.tif",
        ]
    )
    dataset = dataset_from_legacy("terrain/slope", text)
    assert dataset["pyramid"]["layout"] == "legacy-v1"
    assert dataset["access"]["visibility"] == "restricted"
    assert dataset["legacy"]["source_configured"] is False

    folder = tmp_path / "lincoln" / "water"
    folder.mkdir(parents=True)
    (folder / "setting.ini").write_text(json.dumps(LEGACY), encoding="utf-8")
    (folder / "tiles").mkdir()
    registry = import_legacy_tree(tmp_path)
    assert [item.id for item in registry.datasets] == ["lincoln/water"]


def test_cli_validate_and_import(tmp_path, capsys):
    from geomap_interfaces.cli import main

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"schema": "geo-map.dataset-registry/v0", "datasets": [dataset_from_legacy("terrain/slope", json.dumps({
            "title": "Slope",
            "version": 2,
            "processed_levels": [1],
            "tile_merge": 1,
        }))] }),
        encoding="utf-8",
    )
    assert main(["validate", str(registry_path)]) == 0
    assert "terrain/slope" in capsys.readouterr().out

    folder = tmp_path / "tree" / "lincoln" / "water"
    folder.mkdir(parents=True)
    (folder / "setting.ini").write_text(json.dumps(LEGACY), encoding="utf-8")
    assert main(["import-legacy", str(tmp_path / "tree")]) == 0
    exported = capsys.readouterr().out
    assert "lincoln/water" in exported
    assert "secret-bucket" not in exported
