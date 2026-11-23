import unittest

import support

from layer_manager.errors import ConfigurationError
from layer_manager.fixtures_seed import seed_missing
from layer_manager.preview_urls import compose_template, encode_tag
from layer_manager.repository import MemoryRepository
from layer_manager.schema_contract import CONFIRM_PUBLISH
from layer_manager.service import LayerService


BASE = "https://example-test.execute-api.us-west-2.amazonaws.com"


class TileAddressTests(unittest.TestCase):
    def test_slashes_stay_in_the_historical_paths(self):
        tag = "demo/water_freq/y2025"
        self.assertNotIn("%2F", encode_tag(tag))
        self.assertEqual(
            compose_template(BASE, "map", tag),
            BASE + "/map/demo/water_freq/y2025/{z}/{x}/{y}.png",
        )
        self.assertEqual(
            compose_template(BASE, "zx_y", tag),
            BASE + "/zx_y/demo/water_freq/y2025/{z}/{x}/{y}.png",
        )
        self.assertEqual(
            compose_template(BASE, "zxy", tag),
            BASE + "/zxy/demo/water_freq/y2025/{z}/{x}/{y}.png",
        )
        self.assertEqual(
            compose_template(BASE, "xyz", tag),
            BASE + "/xyz/demo/water_freq/y2025/{x}/{y}/{z}.png",
        )

    def test_unset_backend_is_not_integrated_and_has_no_production_host(self):
        service = LayerService(MemoryRepository())
        seed_missing(service)
        body = service.get_layer("demo/water_freq/y2025")
        preview = body["preview"]
        self.assertFalse(preview["integrated"])
        self.assertFalse(preview["calls_backend"])
        self.assertFalse(preview["publish_generates_tiles"])
        self.assertIsNone(preview["template"])
        self.assertIsNone(preview["sample_tile_url"])
        self.assertEqual(preview["tile_backend"]["integration_status"], "awaiting-parent-endpoint")
        text = str(preview)
        self.assertNotIn("admin.terrapulse.com", text)
        self.assertNotIn("geo-map-tiles", text)
        self.assertNotIn("map-tiles-dev", text)

    def test_supplied_test_base_is_address_only(self):
        service = LayerService(MemoryRepository(), tile_backend_base_url=BASE, tile_path_order="map")
        seed_missing(service)
        preview = service.get_layer("demo/water_freq/y2025")["preview"]
        self.assertEqual(preview["mode"], "address-only")
        self.assertTrue(preview["template"].endswith("/map/demo/water_freq/y2025/{z}/{x}/{y}.png"))
        self.assertFalse(preview["integrated"])
        self.assertFalse(preview["remote_fetch"])
        with self.assertRaises(Exception):
            service.publish("demo/slope/draft", 1, CONFIRM_PUBLISH, "admin", "layer-admin")
        self.assertEqual(service.repository.get("demo/slope/draft")["status"], "draft")

    def test_publish_of_a_complete_layer_still_does_not_generate_tiles(self):
        service = LayerService(MemoryRepository(), tile_backend_base_url=BASE)
        seed_missing(service)
        published = service.publish("demo/water_freq/y2025", 1, CONFIRM_PUBLISH, "admin", "layer-admin")
        self.assertEqual(published["layer"]["status"], "published")
        self.assertFalse(published["effects"]["png_pyramid_regenerated"])
        self.assertFalse(published["effects"]["tile_bytes_written"])
        self.assertFalse(published["preview"]["publish_generates_tiles"])
        self.assertFalse(published["preview"]["calls_backend"])

    def test_production_and_existing_fronts_are_refused(self):
        for url in (
            "https://admin.terrapulse.com",
            "https://tiles.example/geo-map-tiles/map",
            "https://map-tiles-dev.example.com",
            "http://example-test.execute-api.us-west-2.amazonaws.com",
            BASE + "/map/demo/{z}/{x}/{y}.png",
        ):
            with self.assertRaises(ConfigurationError):
                support.staging_settings(tile_backend_base_url=url)

    def test_contract_endpoint_reports_the_orders(self):
        api = support.api(support.local_settings(tile_backend_base_url=BASE, tile_path_order="xyz"))
        status, _, body = support.call(api, "GET", "/v1/contract")
        self.assertEqual(status, 200)
        orders = body["result"]["preview_contract"]["orders"]
        self.assertIn("{tag}", orders["xyz"])
        self.assertEqual(body["result"]["tile_backend"]["path_order"], "xyz")
        self.assertFalse(body["result"]["tile_backend"]["integrated"])
        self.assertFalse(body["result"]["preview_contract"]["admin_authorization_sent_to_tiles"])


if __name__ == "__main__":
    unittest.main()
