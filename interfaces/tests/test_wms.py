import io
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

from geomap_interfaces.http import build_app
from geomap_interfaces.mercator import MAX_LAT, ORIGIN_SHIFT

from support import build_runtime, call

WMS = "http://www.opengis.net/wms"
OGC = "http://www.opengis.net/ogc"


def _app(tmp_path):
    return build_app(build_runtime(tmp_path))


def _xml(body: bytes):
    return ET.fromstring(body)


def _layer(root, name):
    for layer in root.iter(f"{{{WMS}}}Layer"):
        node = layer.find(f"{{{WMS}}}Name")
        if node is not None and node.text == name:
            return layer
    raise AssertionError(name)


def test_capabilities_advertise_only_implemented_operations_and_axis_order(tmp_path):
    status, _headers, body = call(_app(tmp_path), "/interfaces/wms", "SERVICE=WMS&REQUEST=GetCapabilities")
    assert status.startswith("200")
    text = body.decode()
    assert "not an OGC compliance certification" in text
    assert "GetFeatureInfo" not in text
    assert "EPSG:27700" not in text
    root = _xml(body)
    request = root.find(f".//{{{WMS}}}Request")
    names = {child.tag.rsplit("}", 1)[-1] for child in list(request)}
    assert names == {"GetCapabilities", "GetMap"}
    layer = _layer(root, "demo/quad")
    crs = [node.text for node in layer.findall(f"{{{WMS}}}CRS")]
    assert crs == ["EPSG:3857", "EPSG:4326", "CRS:84"]
    boxes = {node.attrib["CRS"]: node.attrib for node in layer.findall(f"{{{WMS}}}BoundingBox")}
    assert float(boxes["EPSG:4326"]["minx"]) == pytest_approx(-MAX_LAT)
    assert float(boxes["EPSG:4326"]["miny"]) == pytest_approx(-180)
    assert float(boxes["CRS:84"]["minx"]) == pytest_approx(-180)
    assert float(boxes["CRS:84"]["miny"]) == pytest_approx(-MAX_LAT)
    geographic = layer.find(f"{{{WMS}}}EX_GeographicBoundingBox")
    assert float(geographic.find(f"{{{WMS}}}westBoundLongitude").text) == pytest_approx(-180)
    assert "demo/cog" not in text
    assert "private/layer" not in text


def test_getmap_respects_axis_order_nodata_and_geographic_sampling(tmp_path):
    app = _app(tmp_path)
    origin = ORIGIN_SHIFT
    orange = _png(
        app,
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&CRS=EPSG:3857"
        f"&BBOX={origin * 0.75},{origin * 0.25},{origin * 0.95},{origin * 0.75}"
        "&WIDTH=8&HEIGHT=8&FORMAT=image/png&STYLES=",
    )
    assert np.all(orange[:, :, 0] == 255) and np.all(orange[:, :, 1] == 140)

    geographic = _png(
        app,
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/latband&CRS=EPSG:4326"
        "&BBOX=0,0,80,180&WIDTH=4&HEIGHT=80&FORMAT=image/png",
    )
    crs84 = _png(
        app,
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/latband&CRS=CRS:84"
        "&BBOX=0,0,180,80&WIDTH=4&HEIGHT=80&FORMAT=image/png",
    )
    assert geographic[10, 0, 0] == 255
    assert geographic[30, 0, 0] == 0
    assert np.array_equal(geographic, crs84)

    nodata = _png(
        app,
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&CRS=EPSG:3857"
        f"&BBOX={-origin * 0.8},{-origin * 0.8},{-origin * 0.2},{-origin * 0.2}"
        "&WIDTH=6&HEIGHT=6&FORMAT=image/png&TRANSPARENT=TRUE",
    )
    assert np.all(nodata[:, :, 3] == 0)
    opaque = _png(
        app,
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&CRS=EPSG:3857"
        f"&BBOX={-origin * 0.8},{-origin * 0.8},{-origin * 0.2},{-origin * 0.2}"
        "&WIDTH=6&HEIGHT=6&FORMAT=image/png&TRANSPARENT=FALSE",
    )
    assert np.all(opaque[:, :, :3] == 255)
    assert np.all(opaque[:, :, 3] == 255)


def test_getmap_errors_are_xml_exceptions(tmp_path):
    app = _app(tmp_path)
    cases = {
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=demo/quad&CRS=EPSG:3857&BBOX=0,0,1,1&WIDTH=2&HEIGHT=2&FORMAT=image/png": "InvalidVersion",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&SRS=EPSG:4326&CRS=EPSG:4326&BBOX=0,0,1,1&WIDTH=2&HEIGHT=2&FORMAT=image/png": "InvalidParameterValue",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&CRS=EPSG:27700&BBOX=0,0,1,1&WIDTH=2&HEIGHT=2&FORMAT=image/png": "InvalidCRS",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&CRS=EPSG:4326&BBOX=0,0,180,80&WIDTH=2&HEIGHT=2&FORMAT=image/png": "InvalidBBOX",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&CRS=EPSG:3857&BBOX=0,0,1,1&WIDTH=2&HEIGHT=2&FORMAT=image/jpeg": "InvalidFormat",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=missing&CRS=EPSG:3857&BBOX=0,0,1,1&WIDTH=2&HEIGHT=2&FORMAT=image/png": "LayerNotDefined",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&CRS=EPSG:3857&BBOX=0,0,1,1&WIDTH=2&HEIGHT=2&FORMAT=image/png&STYLES=classified": "StyleNotDefined",
        "SERVICE=WMS&REQUEST=GetFeatureInfo&VERSION=1.3.0": "OperationNotSupported",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=demo/quad&CRS=EPSG:3857&BBOX=0,0,1,1&WIDTH=5000&HEIGHT=2&FORMAT=image/png": "InvalidDimension",
    }
    for query, code in cases.items():
        status, headers, body = call(app, "/interfaces/wms", query)
        assert headers_type(headers).startswith("text/xml")
        node = _xml(body).find(f"{{{OGC}}}ServiceException")
        assert node is not None and node.attrib["code"] == code
        assert status.startswith("400") or status.startswith("404")


def test_restricted_layer_is_denied_until_the_role_is_present(tmp_path):
    app = _app(tmp_path)
    status, _headers, body = call(
        app,
        "/interfaces/wms",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=private/layer&CRS=EPSG:3857&BBOX=-1000,-1000,1000,1000&WIDTH=2&HEIGHT=2&FORMAT=image/png",
    )
    assert status.startswith("403")
    assert _xml(body).find(f"{{{OGC}}}ServiceException").attrib["code"] == "AccessDenied"
    status, headers, body = call(
        app,
        "/interfaces/wms",
        "SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=private/layer&CRS=EPSG:3857&BBOX=-1000,-1000,1000,1000&WIDTH=2&HEIGHT=2&FORMAT=image/png",
        headers={"Authorization": "Bearer analyst-token"},
    )
    assert status.startswith("200")
    assert headers_type(headers) == "image/png"
    assert np.all(np.array(Image.open(io.BytesIO(body)))[:, :, 1] == 255)


def _png(app, query: str) -> np.ndarray:
    status, headers, body = call(app, "/interfaces/wms", query)
    assert status.startswith("200"), body
    assert headers_type(headers) == "image/png"
    return np.array(Image.open(io.BytesIO(body)))


def headers_type(headers) -> str:
    return dict(headers)["Content-Type"].split(";", 1)[0]


def pytest_approx(value):
    import pytest

    return pytest.approx(value, abs=1e-6)
