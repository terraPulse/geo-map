import io
import json

import numpy as np
from PIL import Image

from geomap_interfaces.http import build_app

from support import build_runtime, call


def test_discovery_tilejson_assets_and_values_stay_separate(tmp_path):
    app = build_app(build_runtime(tmp_path))
    status, _headers, body = call(app, "/interfaces/datasets")
    ids = [item["id"] for item in json.loads(body)["datasets"]]
    assert "demo/quad" in ids and "demo/numbers" in ids and "demo/cog" in ids
    assert "private/layer" not in ids

    status, _headers, body = call(app, "/interfaces/datasets/demo/quad/tilejson")
    tilejson = json.loads(body)
    assert tilejson["tilejson"] == "3.0.0"
    assert tilejson["scheme"] == "xyz"
    assert tilejson["tiles"] == ["https://maps.example/interfaces/datasets/demo/quad/tiles/{z}/{x}/{y}.png"]
    assert tilejson["minzoom"] == 0 and tilejson["maxzoom"] == 3
    assert "base64" not in body.decode()

    status, headers, body = call(app, "/interfaces/datasets/demo/quad/tiles/2/3/0.png")
    assert status.startswith("200")
    image = np.array(Image.open(io.BytesIO(body)))
    assert np.all(image[:, :, 0] == 255) and np.all(image[:, :, 1] == 140)

    status, _headers, body = call(app, "/interfaces/datasets/demo/quad/assets")
    assets = {item["id"]: item for item in json.loads(body)["assets"]}
    assert assets["source"]["retrieval"] == "local-content"
    assert assets["upstream"]["retrieval"] == "metadata-only"
    assert assets["upstream"]["href"] == "https://data.example/quad.json"
    status, headers, body = call(app, "/interfaces/datasets/demo/quad/assets/source/content")
    assert json.loads(body)["type"] == "FeatureCollection"
    status, _headers, body = call(app, "/interfaces/datasets/demo/quad/assets/upstream/content")
    assert json.loads(body)["error"]["code"] == "remote_asset_not_fetched"

    status, _headers, body = call(app, "/interfaces/datasets/demo/quad/value", "lon=1&lat=1")
    payload = json.loads(body)
    assert payload["available"] is False
    assert payload["reason"] == "quantitative_backend_not_configured"
    assert "value" not in payload
    assert "255" not in body.decode()

    status, _headers, body = call(app, "/interfaces/datasets/demo/numbers/value", "lon=-9.5&lat=43.5")
    assert json.loads(body) == {"available": True, "crs": "EPSG:4326", "value": 1.0, "nodata": False}
    status, _headers, body = call(app, "/interfaces/datasets/demo/numbers/value", "lon=-6.5&lat=43.5")
    assert json.loads(body)["nodata"] is True and json.loads(body)["value"] is None
    status, _headers, body = call(app, "/interfaces/datasets/demo/numbers/stats", "west=-10&south=40&east=-6&north=44")
    stats = json.loads(body)
    assert stats["count"] == 15 and stats["nodata_count"] == 1
    assert stats["min"] == 1 and stats["max"] == 16 and stats["mean"] == 8.8

    status, _headers, body = call(app, "/map/demo/quad/1/1/0.png")
    assert status.startswith("404")


def test_permissions_are_shared_by_tiles_and_details(tmp_path):
    app = build_app(build_runtime(tmp_path))
    status, _headers, body = call(app, "/interfaces/datasets/private/layer")
    assert status.startswith("403")
    assert json.loads(body)["error"]["code"] == "forbidden"
    status, _headers, _body = call(app, "/interfaces/datasets/private/layer/tiles/0/0/0.png")
    assert status.startswith("403")
    status, headers, body = call(
        app,
        "/interfaces/datasets/private/layer/tiles/0/0/0.png",
        headers={"Authorization": "Bearer analyst-token"},
    )
    assert status.startswith("200")
    assert dict(headers)["Content-Type"] == "image/png"
    assert "Access-Control-Allow-Origin" not in dict(headers)
    status, _headers, body = call(app, "/interfaces/datasets", headers={"Authorization": "Bearer analyst-token"})
    assert "private/layer" in [item["id"] for item in json.loads(body)["datasets"]]
    status, _headers, body = call(app, "/interfaces/datasets", headers={"Authorization": "Bearer nope"})
    assert status.startswith("401")


def test_cog_without_rasterio_does_not_invent_a_number(tmp_path):
    app = build_app(build_runtime(tmp_path))
    status, _headers, body = call(app, "/interfaces/datasets/demo/cog/value", "lon=0&lat=0")
    payload = json.loads(body)
    assert status.startswith("501")
    assert payload["error"]["code"] == "quantitative_dependency_missing"
    assert "value" not in payload["error"]["message"] or "estimated" in payload["error"]["message"]
    status, _headers, body = call(
        app,
        "/interfaces/wms",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/cog&CRS=EPSG:4326&BBOX=-1,-1,1,1&WIDTH=2&HEIGHT=2&FORMAT=image/png",
    )
    assert b"LayerNotDefined" in body
