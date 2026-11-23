import json
import tempfile
import unittest
from pathlib import Path

import support

support  # path bootstrap

from layer_manager.canonical import content_digest
from layer_manager.dynamodb_repository import ConditionalWriteFailed, DynamoRepository
from layer_manager.errors import ConfigurationError
from layer_manager.fixtures_seed import load_fixture_document, seed_missing
from layer_manager.legacy import export_legacy, legacy_to_client_layer, parse_color_txt
from layer_manager.repository import FileRepository, MemoryRepository
from layer_manager.schema_contract import CONFIRM_CREATE_DRAFT, CONFIRM_IMPORT, CONFIRM_PUBLISH, SCHEMA_ID
from layer_manager.service import LayerService
from layer_manager.settings import Settings
from layer_manager.validate import editable_from_stored, validate_client_layer


def water_layer():
    layer = dict(load_fixture_document()[0])
    layer.pop("status", None)
    return layer


class ValidateTests(unittest.TestCase):
    def test_slash_tag_is_valid(self):
        normalized, issues = validate_client_layer(water_layer())
        self.assertEqual(normalized["tag"], "demo/water_freq/y2025")
        self.assertFalse([item for item in issues if item["severity"] == "error"])

    def test_parent_segments_rejected(self):
        layer = water_layer()
        layer["tag"] = "demo/../secret"
        _, issues = validate_client_layer(layer)
        self.assertTrue(any(item["code"] == "tag_segment" for item in issues))

    def test_production_bucket_reference_rejected(self):
        layer = water_layer()
        layer["source_revisions"][0]["uri"] = "s3://geo-map-tiles-w2/tiles/demo"
        _, issues = validate_client_layer(layer)
        self.assertTrue(any(item["code"] == "denied_reference" for item in issues))

    def test_regeneration_flag_cannot_be_set_by_omission(self):
        from layer_manager.effects import REGISTRY_EFFECTS_STORED

        self.assertFalse(REGISTRY_EFFECTS_STORED["png_pyramid_regenerated_on_write"])

    def test_preview_host_must_be_allowlisted(self):
        layer = water_layer()
        layer["authorized_tile_template"] = "https://evil.example/map/demo/water_freq/y2025/{z}/{x}/{y}.png"
        _, issues = validate_client_layer(layer, preview_hosts=("https://tiles.example",))
        self.assertTrue(any(item["code"] == "template_host" for item in issues))

    def test_allowlisted_template_is_not_fetched(self):
        layer = water_layer()
        layer["authorized_tile_template"] = "https://tiles.example/map/demo/water_freq/y2025/{z}/{x}/{y}.png"
        normalized, issues = validate_client_layer(layer, preview_hosts=("https://tiles.example",))
        self.assertEqual(normalized["authorized_tile_template"], layer["authorized_tile_template"])
        self.assertFalse(any(item["severity"] == "error" for item in issues))


class LegacyTests(unittest.TestCase):
    def test_round_trip_color_and_setting(self):
        setting = {
            "file": "s3://example-fixture-source/demo/list.shp",
            "title": "Water frequency",
            "version": 2.0,
            "tile_merge": 8,
            "min_static_level": 3,
            "min_dynamic_level": 5,
            "processed_levels": [3, 4, 5],
            "min_value": 0,
            "max_value": 100,
            "agg": "mean",
            "burn_band": {"input": "synthetic://hillshade", "offset": 180},
            "visible": True,
        }
        color = "0 255,255,255,0\n100 0,60,120,255\n"
        layer, compat = legacy_to_client_layer("demo/water/y2025", setting, color, "2026-01-15T00:00:00Z")
        self.assertEqual(layer["backend"], "png-pyramid")
        self.assertEqual(layer["pyramid"]["tile_merge"], 8)
        self.assertEqual(len(layer["style"]["stops"]), 2)
        self.assertEqual(compat["setting"]["burn_band"]["offset"], 180)
        stops = parse_color_txt(color)
        self.assertEqual(stops[1]["rgba"], [0, 60, 120, 255])

    def test_qgis_color_map(self):
        text = "# QGIS Generated Color Map Export File\nINTERPOLATION:INTERPOLATED\n0,1,2,3,255,low\n"
        stops = parse_color_txt(text)
        self.assertEqual(stops[0]["label"], "low")
        self.assertEqual(stops[0]["rgba"], [1, 2, 3, 255])


class RepositoryTests(unittest.TestCase):
    def test_file_repository_keeps_slashes_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = FileRepository(tmp)
            service = LayerService(repo)
            seeded = seed_missing(service)
            self.assertEqual(len(seeded["inserted"]), 3)
            again = seed_missing(service)
            self.assertEqual(again["inserted"], [])
            self.assertEqual(len(again["skipped"]), 3)
            stored = repo.get("demo/water_freq/y2025")
            self.assertTrue(stored["synthetic"])
            names = list(Path(tmp, "layers").iterdir())
            self.assertTrue(all("/" not in path.name for path in names))

    def test_memory_revision_conflict(self):
        repo = MemoryRepository()
        service = LayerService(repo)
        seed_missing(service)
        current = repo.get("demo/slope/draft")
        service.update_layer("demo/slope/draft", {"title": "Renamed slope"}, current["revision"], "fixture-admin", "layer-admin")
        with self.assertRaises(Exception) as caught:
            service.update_layer("demo/slope/draft", {"title": "Lost update"}, current["revision"], "fixture-admin", "layer-admin")
        self.assertIn("Revision conflict", str(caught.exception))


class DynamoFake:
    def __init__(self):
        self.items = {}

    def get_item(self, TableName, Key, ConsistentRead=False):
        item = self.items.get((Key["pk"]["S"], Key["sk"]["S"]))
        return {"Item": item} if item else {}

    def query(self, **kwargs):
        pk = kwargs["ExpressionAttributeValues"][":pk"]["S"]
        rows = [item for (item_pk, _), item in self.items.items() if item_pk == pk]
        if kwargs.get("ScanIndexForward") is False:
            rows = list(reversed(rows))
        return {"Items": rows}

    def transact_write_items(self, TransactItems):
        for entry in TransactItems:
            put = entry["Put"]
            condition = put.get("ConditionExpression")
            item = put["Item"]
            key = (item["pk"]["S"], item["sk"]["S"])
            if condition == "attribute_not_exists(sk)" and key in self.items:
                raise ConditionalWriteFailed(key)
            if condition == "revision = :expected":
                expected = int(put["ExpressionAttributeValues"][":expected"]["N"])
                current = self.items.get(key)
                if current is None or int(current["revision"]["N"]) != expected:
                    raise ConditionalWriteFailed(key)
        for entry in TransactItems:
            item = entry["Put"]["Item"]
            self.items[(item["pk"]["S"], item["sk"]["S"])] = item


class DynamoTests(unittest.TestCase):
    def test_conditional_create_and_update(self):
        repo = DynamoRepository(DynamoFake(), "registry")
        service = LayerService(repo)
        seed_missing(service)
        again = seed_missing(service)
        self.assertEqual(again["inserted"], [])
        current = repo.get("demo/water_freq/y2025")
        updated = dict(current)
        updated["title"] = "Edited"
        updated["revision"] = current["revision"] + 1
        from layer_manager.repository import new_audit

        audit = new_audit(
            tag=current["tag"],
            action="update",
            actor="admin",
            role="layer-admin",
            from_revision=current["revision"],
            to_revision=updated["revision"],
            changed_fields=["title"],
            snapshot=updated,
        )
        repo.update(current["tag"], updated, current["revision"], audit)
        self.assertEqual(repo.get(current["tag"])["title"], "Edited")
        self.assertTrue(repo.list_audit(current["tag"]))
        source = Path(__file__).resolve().parents[1].joinpath("src/layer_manager/dynamodb_repository.py").read_text(encoding="utf-8")
        self.assertNotIn("delete_item", source)
        self.assertNotIn(".scan(", source)


class SettingsTests(unittest.TestCase):
    def test_prod_and_wildcard_and_wrong_region_refused(self):
        with self.assertRaises(ConfigurationError):
            support.local_settings(env="prod")
        with self.assertRaises(ConfigurationError):
            support.staging_settings(cors_origins=("*",))
        with self.assertRaises(ConfigurationError):
            support.staging_settings(allow_fixture_auth=True)
        with self.assertRaises(ConfigurationError):
            support.staging_settings(dynamodb_region="us-east-1")
        with self.assertRaises(ConfigurationError):
            support.staging_settings(preview_hosts=("https://admin.terrapulse.com",))

    def test_from_env_staging_requires_cognito(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"LAYER_MANAGER_ENV": "staging"})


class ServiceFlowTests(unittest.TestCase):
    def setUp(self):
        self.service = LayerService(MemoryRepository(), preview_hosts=("https://tiles.example",))

    def test_preview_create_publish_does_not_claim_tile_writes(self):
        layer = water_layer()
        layer["tag"] = "demo/new/layer"
        preview = self.service.preview(layer)
        self.assertFalse(preview["persisted"])
        self.assertFalse(preview["effects"]["png_pyramid_regenerated"])
        self.assertFalse(preview["effects"]["remote_urls_fetched"])
        created = self.service.create_draft(layer, preview["content_digest"], CONFIRM_CREATE_DRAFT, "admin", "layer-admin")
        self.assertEqual(created["layer"]["status"], "draft")
        self.assertFalse(created["effects"]["tile_bytes_written"])
        self.assertFalse(created["effects"]["legacy_setting_ini_written"])
        published = self.service.publish("demo/new/layer", 1, CONFIRM_PUBLISH, "admin", "layer-admin")
        self.assertEqual(published["layer"]["status"], "published")
        self.assertEqual(published["layer"]["revision"], 2)
        self.assertFalse(published["effects"]["png_pyramid_regenerated"])
        self.assertFalse(published["effects"]["production_bucket_mutated"])
        self.assertFalse(published["effects"]["users_invited"])

    def test_import_does_not_overwrite(self):
        setting = {"title": "Imported", "version": 2, "processed_levels": [3], "tile_merge": 1, "min_static_level": 3}
        color = "1 10,20,30,255\n"
        first = self.service.import_legacy("lab/sample", setting, color, CONFIRM_IMPORT, "admin", "layer-admin", "2026-03-01T00:00:00Z")
        self.assertEqual(first["layer"]["status"], "draft")
        exported = export_legacy(first["layer"])
        self.assertFalse(exported["written"])
        self.assertEqual(exported["setting"]["title"], "Imported")
        self.assertIn("10,20,30,255", exported["color_txt"])
        with self.assertRaises(Exception) as caught:
            self.service.import_legacy("lab/sample", setting, color, CONFIRM_IMPORT, "admin", "layer-admin", "2026-03-01T00:00:00Z")
        self.assertIn("does not overwrite", str(caught.exception))

    def test_wrong_digest_saves_nothing(self):
        layer = water_layer()
        layer["tag"] = "demo/digest"
        with self.assertRaises(Exception):
            self.service.create_draft(layer, "0" * 64, CONFIRM_CREATE_DRAFT, "admin", "layer-admin")
        self.assertIsNone(self.service.repository.get("demo/digest"))

    def test_restore_keeps_a_new_revision(self):
        layer = water_layer()
        layer["tag"] = "demo/restore"
        preview = self.service.preview(layer)
        self.service.create_draft(layer, preview["content_digest"], CONFIRM_CREATE_DRAFT, "admin", "layer-admin")
        self.service.update_layer("demo/restore", {"title": "Changed"}, 1, "admin", "layer-admin")
        audit = self.service.list_audit("demo/restore")["audit"]
        created = next(item for item in audit if item["action"] == "create-draft")
        restored = self.service.restore("demo/restore", created["audit_id"], 2, "restore-registry-only", "admin", "layer-admin")
        self.assertEqual(restored["layer"]["revision"], 3)
        self.assertEqual(restored["layer"]["title"], layer["title"])
        self.assertFalse(restored["effects"]["png_pyramid_regenerated"])

    def test_digest_tracks_normalized_content(self):
        layer = water_layer()
        preview = self.service.preview(layer)
        normalized, _ = validate_client_layer(layer)
        self.assertEqual(preview["content_digest"], content_digest(normalized))
        stored_view = editable_from_stored(
            {
                "tag": normalized["tag"],
                "title": normalized["title"],
                "backend": normalized["backend"],
                "pyramid": normalized["pyramid"],
                "cog": normalized["cog"],
                "bounds": normalized["bounds"],
                "style": normalized["style"],
                "nodata": normalized["nodata"],
                "source_revisions": normalized["source_revisions"],
                "authorized_tile_template": normalized["authorized_tile_template"],
            }
        )
        self.assertEqual(stored_view["tag"], normalized["tag"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.api = support.api()

    def test_anonymous_is_denied(self):
        status, _, body = support.call(self.api, "GET", "/v1/layers", actor=None)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "unauthorized")

    def test_reader_cannot_write_and_admin_can_list_slashes(self):
        from layer_manager.fixtures_seed import seed_missing

        seed_missing(self.api.service)
        status, _, _ = support.call(self.api, "POST", "/v1/layers/preview", {"layer": water_layer()}, actor="fixture-reader")
        self.assertEqual(status, 403)
        status, _, body = support.call(self.api, "GET", "/v1/layers?q=water", actor="fixture-reader")
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["layers"][0]["tag"], "demo/water_freq/y2025")
        self.assertIn("synthetic", body["result"]["inventory_note"])

    def test_fixture_header_rejected_for_cognito_mode(self):
        from layer_manager.app_factory import build_api
        from layer_manager.repository import MemoryRepository

        api = build_api(support.staging_settings(), repository=MemoryRepository())
        event = {"requestContext": {}}
        status, _, body = support.call(api, "GET", "/v1/session", actor="fixture-admin", event=event)
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "unauthorized")

    def test_cognito_claims_enforce_role_issuer_and_expiry(self):
        from layer_manager.app_factory import build_api
        from layer_manager.repository import MemoryRepository

        settings = support.staging_settings()
        api = build_api(settings, repository=MemoryRepository())
        good = self._event(settings, groups="[layer-reader]", exp=9999999999)
        status, _, body = support.call(api, "GET", "/v1/session", actor=None, event=good)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["result"]["actor"]["role"], "layer-reader")
        self.assertFalse(body["result"]["signup"])
        writer = self._event(settings, groups="layer-admin", exp=9999999999)
        status, _, body = support.call(api, "POST", "/v1/layers/preview", {"layer": water_layer()}, actor=None, event=writer)
        self.assertEqual(status, 200, body)
        self.assertFalse(body["result"]["effects"]["png_pyramid_regenerated"])
        bad_issuer = self._event(settings, issuer="https://evil.example/pool", exp=9999999999)
        status, _, _ = support.call(api, "GET", "/v1/session", actor=None, event=bad_issuer)
        self.assertEqual(status, 401)
        no_group = self._event(settings, groups="users", exp=9999999999)
        status, _, body = support.call(api, "GET", "/v1/session", actor=None, event=no_group)
        self.assertEqual(status, 403)
        expired = self._event(settings, exp=1)
        status, _, _ = support.call(api, "GET", "/v1/session", actor=None, event=expired)
        self.assertEqual(status, 401)

    def test_publish_phrase_and_search(self):
        from layer_manager.fixtures_seed import seed_missing

        seed_missing(self.api.service)
        status, _, body = support.call(
            self.api,
            "POST",
            "/v1/layers/item/publish?tag=demo/slope/draft",
            {"expected_revision": 1, "confirmation": CONFIRM_PUBLISH},
        )
        self.assertEqual(status, 422)
        self.assertFalse(body["ok"])
        status, _, body = support.call(self.api, "GET", "/v1/layers/item?tag=demo/canopy_cover/cog")
        self.assertEqual(body["result"]["layer"]["backend"], "cog")
        self.assertIn("does not read this COG", json.dumps(body))
        self.assertFalse(body["result"]["effects"]["cog_rewritten"])

    def _event(self, settings, groups="[layer-admin]", exp=9999999999, issuer=None):
        return {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "user-1",
                            "username": "ada",
                            "iss": issuer or f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}",
                            "client_id": settings.cognito_client_id,
                            "token_use": "access",
                            "exp": str(exp),
                            "cognito:groups": groups,
                        }
                    }
                }
            }
        }


class ContractTests(unittest.TestCase):
    def test_schema_file_matches_stored_keys(self):
        from layer_manager.schema_contract import STORED_RECORD_KEYS

        document = json.loads((support.ROOT / "contracts" / "layer-registry-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(document["$id"], SCHEMA_ID)
        self.assertEqual(tuple(document["required"]), tuple(STORED_RECORD_KEYS))
        ui = (support.ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn(CONFIRM_PUBLISH, ui)
        self.assertIn("does not regenerate", ui.lower())
        self.assertNotIn("Rebuild pyramid", ui)
        self.assertNotIn("demo/water_freq/y2025", ui)


if __name__ == "__main__":
    unittest.main()
