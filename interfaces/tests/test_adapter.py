import sys
from pathlib import Path

from geomap_interfaces.apigw import apigateway_v2_handler
from geomap_interfaces.quant import cog as cog_module

from support import build_runtime


def test_package_does_not_import_the_legacy_runtime():
    assert not any(name == "gio" or name.startswith("geo_map") or name == "boto3" for name in sys.modules)
    source = Path(__file__).parents[1].joinpath("src/geomap_interfaces/pyramid.py").read_text(encoding="utf-8")
    assert "import gio" not in source
    assert "rasterio" not in source
    head = Path(cog_module.__file__).read_text(encoding="utf-8").split("def _libraries", 1)[0]
    assert "import rasterio" not in head


def test_api_gateway_adapter_encodes_small_pngs_locally(tmp_path):
    runtime = build_runtime(tmp_path)
    health = apigateway_v2_handler(
        runtime,
        {"rawPath": "/interfaces/health", "rawQueryString": "", "headers": {}, "requestContext": {"http": {"method": "GET"}}},
    )
    assert health["statusCode"] == 200
    assert health["isBase64Encoded"] is False
    assert "provisional-not-certified" in health["body"]
    tile = apigateway_v2_handler(
        runtime,
        {
            "rawPath": "/interfaces/datasets/demo/numbers/tiles/0/0/0.png",
            "rawQueryString": "",
            "headers": {},
            "requestContext": {"http": {"method": "GET"}},
        },
    )
    assert tile["statusCode"] == 200 and tile["isBase64Encoded"] is True
    import base64

    assert base64.b64decode(tile["body"]).startswith(b"\x89PNG")


def test_cog_reader_uses_an_injected_library_without_sampling_png(tmp_path, monkeypatch):
    import numpy as np

    class Source:
        crs = "EPSG:4326"
        width = 2
        height = 2
        nodata = -9999.0
        transform = None

        def index(self, x, y):
            return 0, 1

        def read(self, band, window=None):
            return np.array([[42.5]])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Rasterio:
        @staticmethod
        def open(path):
            return Source()

    def transform(src, dst, xs, ys):
        return xs, ys

    import types

    rasterio = types.ModuleType("rasterio")
    rasterio.open = Rasterio.open
    warp = types.ModuleType("rasterio.warp")
    warp.transform = transform
    warp.transform_bounds = transform
    windows = types.ModuleType("rasterio.windows")
    windows.from_bounds = lambda *args: None
    windows.Window = lambda *args: None
    monkeypatch.setitem(sys.modules, "rasterio", rasterio)
    monkeypatch.setitem(sys.modules, "rasterio.warp", warp)
    monkeypatch.setitem(sys.modules, "rasterio.windows", windows)
    target = tmp_path / "demo" / "cog"
    target.mkdir(parents=True)
    (target / "values.tif").write_bytes(b"stub")
    result = cog_module.cog_point(target, "values.tif", 0.1, 0.2, 1, -9999.0, build_runtime(tmp_path).budgets)
    assert result["value"] == 42.5
    assert result["nodata"] is False
