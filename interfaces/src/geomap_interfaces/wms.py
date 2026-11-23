"""WMS 1.3.0 GetCapabilities and GetMap for styled PNG pyramids.

Only CRS values and operations implemented below are advertised. This is not
an OGC compliance certification. GetMap assembles stored blocks and resamples
an arbitrary bbox; it does not return a single XYZ tile under another name.
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET

import numpy as np

from .auth import Principal, can_read
from .errors import WmsError
from .mercator import ORIGIN_SHIFT, mercator_x, mercator_y
from .pyramid import encode_png, render_bbox
from .registry import Dataset
from .runtime import Runtime

WMS_NS = "http://www.opengis.net/wms"
XLINK_NS = "http://www.w3.org/1999/xlink"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
OGC_NS = "http://www.opengis.net/ogc"
_CRS = {
    "EPSG:3857": "xy",
    "EPSG:4326": "latlon",
    "CRS:84": "lonlat",
}


def handle_wms(runtime: Runtime, principal: Principal, query_string: str) -> tuple[int, str, bytes]:
    try:
        params = _params(query_string)
        request = params.get("REQUEST")
        if not request:
            raise WmsError("MissingParameterValue", "REQUEST is required")
        name = request.strip().lower()
        if name == "getcapabilities":
            _version_for_capabilities(params)
            return 200, "text/xml; charset=utf-8", capabilities_xml(runtime, principal)
        if name == "getmap":
            return 200, "image/png", get_map(runtime, principal, params)
        raise WmsError("OperationNotSupported", "Only GetCapabilities and GetMap are implemented")
    except WmsError as exc:
        return exc.status, "text/xml; charset=utf-8", exception_xml(exc)


def capabilities_xml(runtime: Runtime, principal: Principal) -> bytes:
    ET.register_namespace("", WMS_NS)
    ET.register_namespace("xlink", XLINK_NS)
    ET.register_namespace("xsi", XSI_NS)
    root = ET.Element(
        f"{{{WMS_NS}}}WMS_Capabilities",
        {"version": "1.3.0"},
    )
    root.set(
        f"{{{XSI_NS}}}schemaLocation",
        "http://www.opengis.net/wms http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd",
    )
    service = ET.SubElement(root, f"{{{WMS_NS}}}Service")
    _text(service, "Name", "WMS")
    _text(service, "Title", "geo-map interfaces")
    _text(
        service,
        "Abstract",
        "Provisional WMS 1.3.0 GetCapabilities and GetMap over stored styled PNG blocks. "
        "This is not an OGC compliance certification. GetMap resamples an arbitrary bbox "
        "from those blocks. Quantitative values are not served by GetMap.",
    )
    _online(service, "OnlineResource", _endpoint(runtime))
    _text(service, "Fees", "none")
    _text(service, "AccessConstraints", "Per-dataset read permission. Public datasets are anonymous.")
    keyword_list = ET.SubElement(service, f"{{{WMS_NS}}}KeywordList")
    for word in ("WMS", "1.3.0", "PNG", "provisional"):
        _text(keyword_list, "Keyword", word)

    capability = ET.SubElement(root, f"{{{WMS_NS}}}Capability")
    request = ET.SubElement(capability, f"{{{WMS_NS}}}Request")
    for operation, fmt in (("GetCapabilities", "text/xml"), ("GetMap", "image/png")):
        node = ET.SubElement(request, f"{{{WMS_NS}}}{operation}")
        _text(node, "Format", fmt)
        dcp = ET.SubElement(node, f"{{{WMS_NS}}}DCPType")
        http = ET.SubElement(dcp, f"{{{WMS_NS}}}HTTP")
        get = ET.SubElement(http, f"{{{WMS_NS}}}Get")
        _online(get, "OnlineResource", _endpoint(runtime))
    exceptions = ET.SubElement(capability, f"{{{WMS_NS}}}Exception")
    _text(exceptions, "Format", "XML")

    layer = ET.SubElement(capability, f"{{{WMS_NS}}}Layer")
    _text(layer, "Title", "geo-map datasets")
    for crs in _CRS:
        _text(layer, "CRS", crs)
    for dataset in runtime.registry.datasets:
        if dataset.pyramid is None or not can_read(dataset.access, principal):
            continue
        layer.append(_layer(dataset))
    return _bytes(root)


def get_map(runtime: Runtime, principal: Principal, params: dict[str, str]) -> bytes:
    if "SRS" in params:
        raise WmsError("InvalidParameterValue", "WMS 1.3.0 uses CRS. SRS is the 1.1.1 parameter and is not accepted.")
    version = params.get("VERSION")
    if version != "1.3.0":
        raise WmsError("InvalidVersion", "VERSION must be 1.3.0")
    service = params.get("SERVICE", "WMS")
    if service.upper() != "WMS":
        raise WmsError("InvalidParameterValue", "SERVICE must be WMS")
    for key in ("LAYERS", "CRS", "BBOX", "WIDTH", "HEIGHT", "FORMAT"):
        if key not in params or params[key] == "":
            raise WmsError("MissingParameterValue", f"{key} is required")
    layers = [item for item in params["LAYERS"].split(",") if item != ""]
    if len(params["LAYERS"].split(",")) != 1 or len(layers) != 1:
        raise WmsError("LayerLimit", "GetMap accepts exactly one layer")
    dataset = _layer_lookup(runtime, principal, layers[0])
    crs = params["CRS"].strip().upper()
    if crs not in _CRS:
        raise WmsError("InvalidCRS", "CRS is not one of the advertised values")
    if params["FORMAT"] != "image/png":
        raise WmsError("InvalidFormat", "FORMAT must be image/png")
    style = params.get("STYLES", "")
    known = {item.id for item in dataset.styles}
    if style == "":
        if not dataset.styles:
            raise WmsError("StyleNotDefined", "dataset has no styled PNG style")
    elif style not in known:
        raise WmsError("StyleNotDefined", "STYLES is not a name advertised for this layer")
    width = _dimension(params["WIDTH"], "WIDTH", runtime)
    height = _dimension(params["HEIGHT"], "HEIGHT", runtime)
    if width * height > runtime.budgets.max_wms_pixels:
        raise WmsError("InvalidDimension", "WIDTH times HEIGHT exceeds the pixel budget", 400)
    sampling, west, south, east, north = _interpret(crs, _bbox(params["BBOX"]))
    try:
        image = render_bbox(
            dataset,
            runtime.store,
            sampling=sampling,
            west=west,
            south=south,
            east=east,
            north=north,
            width=width,
            height=height,
            budgets=runtime.budgets,
        )
    except WmsError:
        raise
    except Exception as exc:
        from .errors import InterfaceError

        if isinstance(exc, InterfaceError) and exc.code == "budget_exceeded":
            raise WmsError("InvalidDimension", exc.message, 400) from exc
        if isinstance(exc, InterfaceError) and exc.code == "invalid_bbox":
            raise WmsError("InvalidBBOX", exc.message, 400) from exc
        if isinstance(exc, InterfaceError):
            raise WmsError("InvalidParameterValue", exc.message, exc.status) from exc
        raise
    transparent = params.get("TRANSPARENT", "TRUE").strip().upper() != "FALSE"
    if not transparent:
        image = _flatten(image, _background(params.get("BGCOLOR")))
    return encode_png(image)


def exception_xml(error: WmsError) -> bytes:
    ET.register_namespace("", OGC_NS)
    ET.register_namespace("xsi", XSI_NS)
    root = ET.Element(f"{{{OGC_NS}}}ServiceExceptionReport", {"version": "1.3.0"})
    root.set(
        f"{{{XSI_NS}}}schemaLocation",
        "http://www.opengis.net/ogc http://schemas.opengis.net/wms/1.3.0/exceptions_1_3_0.xsd",
    )
    node = ET.SubElement(root, f"{{{OGC_NS}}}ServiceException", {"code": error.ogc_code})
    node.text = error.message
    return _bytes(root)


def _layer(dataset: Dataset) -> ET.Element:
    node = ET.Element(f"{{{WMS_NS}}}Layer", {"queryable": "0"})
    _text(node, "Name", dataset.id)
    _text(node, "Title", dataset.title)
    _text(node, "Abstract", dataset.description or dataset.title)
    for crs in _CRS:
        _text(node, "CRS", crs)
    west, south, east, north = dataset.bounds
    geo = ET.SubElement(node, f"{{{WMS_NS}}}EX_GeographicBoundingBox")
    _text(geo, "westBoundLongitude", _num(west))
    _text(geo, "eastBoundLongitude", _num(east))
    _text(geo, "southBoundLatitude", _num(south))
    _text(geo, "northBoundLatitude", _num(north))
    _bbox_element(node, "CRS:84", west, south, east, north)
    _bbox_element(node, "EPSG:4326", south, west, north, east)
    mx0 = float(mercator_x(west))
    my0 = float(mercator_y(south))
    mx1 = float(mercator_x(east))
    my1 = float(mercator_y(north))
    _bbox_element(node, "EPSG:3857", mx0, my0, mx1, my1)
    for style in dataset.styles:
        style_node = ET.SubElement(node, f"{{{WMS_NS}}}Style")
        _text(style_node, "Name", style.id)
        _text(style_node, "Title", style.title)
    return node


def _bbox_element(parent: ET.Element, crs: str, minx: float, miny: float, maxx: float, maxy: float) -> None:
    ET.SubElement(
        parent,
        f"{{{WMS_NS}}}BoundingBox",
        {"CRS": crs, "minx": _num(minx), "miny": _num(miny), "maxx": _num(maxx), "maxy": _num(maxy)},
    )


def _layer_lookup(runtime: Runtime, principal: Principal, layer: str) -> Dataset:
    dataset = runtime.registry.get(layer)
    if dataset is None or dataset.pyramid is None:
        raise WmsError("LayerNotDefined", "layer is not available", 404)
    if not can_read(dataset.access, principal):
        raise WmsError("AccessDenied", "principal cannot read this layer", 403)
    return dataset


def _interpret(crs: str, values: tuple[float, float, float, float]) -> tuple[str, float, float, float, float]:
    order = _CRS[crs]
    first, second, third, fourth = values
    if order == "xy":
        west, south, east, north = first, second, third, fourth
        limit = ORIGIN_SHIFT + 1e-6
        if west >= east or south >= north or max(abs(west), abs(east), abs(south), abs(north)) > limit:
            raise WmsError("InvalidBBOX", "EPSG:3857 bbox is outside the Web Mercator domain")
        return "mercator", west, south, east, north
    if order == "latlon":
        south, west, north, east = first, second, third, fourth
    else:
        west, south, east, north = first, second, third, fourth
    from .mercator import MAX_LAT

    if not (-180.0 <= west < east <= 180.0 and -MAX_LAT <= south < north <= MAX_LAT):
        raise WmsError("InvalidBBOX", "geographic bbox is invalid, uses the wrong axis order, or crosses the antimeridian")
    return "geographic", west, south, east, north


def _bbox(text: str) -> tuple[float, float, float, float]:
    parts = text.split(",")
    if len(parts) != 4:
        raise WmsError("InvalidBBOX", "BBOX must contain four numbers")
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise WmsError("InvalidBBOX", "BBOX must contain four numbers") from exc
    if not all(np.isfinite(value) for value in values):
        raise WmsError("InvalidBBOX", "BBOX values must be finite")
    return values  # type: ignore[return-value]


def _dimension(text: str, name: str, runtime: Runtime) -> int:
    if not text.isdigit():
        raise WmsError("InvalidDimension", f"{name} must be a positive integer")
    value = int(text)
    if value < 1 or value > runtime.budgets.max_wms_edge:
        raise WmsError("InvalidDimension", f"{name} exceeds the pixel budget")
    return value


def _background(text: str | None) -> tuple[int, int, int]:
    if text is None or text == "":
        return (255, 255, 255)
    raw = text[2:] if text.lower().startswith("0x") else text
    if len(raw) != 6:
        raise WmsError("InvalidParameterValue", "BGCOLOR must be 0xRRGGBB")
    try:
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    except ValueError as exc:
        raise WmsError("InvalidParameterValue", "BGCOLOR must be 0xRRGGBB") from exc


def _flatten(image: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    alpha = image[:, :, 3:4].astype(np.float64) / 255.0
    rgb = image[:, :, :3].astype(np.float64)
    background = np.asarray(color, dtype=np.float64)
    flat = rgb * alpha + background * (1.0 - alpha)
    output = np.zeros_like(image)
    output[:, :, :3] = np.rint(flat).astype(np.uint8)
    output[:, :, 3] = 255
    return output


def _version_for_capabilities(params: dict[str, str]) -> None:
    service = params.get("SERVICE")
    if service is not None and service.upper() != "WMS":
        raise WmsError("InvalidParameterValue", "SERVICE must be WMS")
    version = params.get("VERSION")
    if version is not None and version != "1.3.0":
        raise WmsError("InvalidVersion", "Only WMS 1.3.0 is implemented")


def _params(query_string: str) -> dict[str, str]:
    parsed = urllib.parse.parse_qs(query_string, keep_blank_values=True)
    folded: dict[str, str] = {}
    for key, values in parsed.items():
        name = key.upper()
        if len(values) != 1 or name in folded:
            raise WmsError("InvalidParameterValue", "duplicate parameter")
        folded[name] = values[0]
    return folded


def _endpoint(runtime: Runtime) -> str:
    return runtime.public_base.rstrip("/") + "/interfaces/wms"


def _text(parent: ET.Element, tag: str, value: str) -> None:
    node = ET.SubElement(parent, f"{{{WMS_NS}}}{tag}")
    node.text = value


def _online(parent: ET.Element, tag: str, href: str) -> None:
    ET.SubElement(parent, f"{{{WMS_NS}}}{tag}", {f"{{{XLINK_NS}}}type": "simple", f"{{{XLINK_NS}}}href": href})


def _num(value: float) -> str:
    return format(value, ".8f").rstrip("0").rstrip(".")


def _bytes(root: ET.Element) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")
