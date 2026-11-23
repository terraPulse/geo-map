"""Render a source raster into a version-2 PNG block pyramid.

The supported runtime is rasterio 1.4.3, whose wheel carries GDAL. The legacy
gio package is not required and is not imported. S3 is read only through an
injected fetcher after the URI passes the allowlist. This module does not
create a boto3 client.
"""

import os

from .png_codec import png_size
from .tile_math import TILE_PX, iter_blocks

RESAMPLING = ("nearest", "bilinear", "cubic")


class PyramidError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def require_rasterio():
    try:
        import rasterio  # noqa: F401
    except ImportError as exc:
        raise PyramidError(
            "raster_runtime_missing",
            "rasterio/GDAL is not installed. gio is not used. No PNG was written.",
        ) from exc


def fixture_bounds():
    from .tile_math import HALF, tile_span

    span = tile_span(4)
    return {
        "crs": "EPSG:3857",
        "minx": -HALF,
        "miny": -HALF,
        "maxx": -HALF + (2 * span) - 1.0,
        "maxy": -HALF + span - 1.0,
    }


def write_gradient_geotiff(path):
    """Deterministic EPSG:3857 raster covering zoom-4 tiles (0,0) and (1,0)."""
    require_rasterio()
    import numpy as np
    import rasterio
    from rasterio.transform import from_bounds

    box = fixture_bounds()
    minx, miny, maxx, maxy = box["minx"], box["miny"], box["maxx"], box["maxy"]
    width, height = 128, 64
    values = np.linspace(0, 100, width, dtype=np.float32)
    grid = np.tile(values, (height, 1))
    grid[0:12, 0:16] = -9999
    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs="EPSG:3857",
        transform=transform,
        nodata=-9999,
    ) as dataset:
        dataset.write(grid, 1)
    return {
        "crs": "EPSG:3857",
        "bounds": {"crs": "EPSG:3857", "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
        "width": width,
        "height": height,
        "nodata": -9999,
        "bands": 1,
        "resolution_m": (maxx - minx) / width,
    }


def describe_raster(path):
    require_rasterio()
    import rasterio

    with rasterio.open(path) as source:
        box = source.bounds
        return {
            "crs": str(source.crs) if source.crs else None,
            "resolution_m": abs(source.res[0]) if source.res else None,
            "bands": source.count,
            "nodata": source.nodata,
            "bounds": {
                "crs": "EPSG:3857" if source.crs and source.crs.to_epsg() == 3857 else str(source.crs),
                "minx": box.left,
                "miny": box.bottom,
                "maxx": box.right,
                "maxy": box.top,
            },
            "read_s3": False,
        }


def render_pyramid(source_path, output_dir, bounds, zooms, merge, resampling, stops, completed=None, batch_size=None, should_continue=None):
    require_rasterio()
    import rasterio
    from PIL import Image
    from rasterio.warp import Resampling

    if resampling not in RESAMPLING:
        raise PyramidError("resampling", "resampling must be nearest, bilinear, or cubic.")
    method = {"nearest": Resampling.nearest, "bilinear": Resampling.bilinear, "cubic": Resampling.cubic}[resampling]
    blocks = iter_blocks(bounds, zooms, merge)
    done = set(completed or [])
    remaining = [block for block in blocks if _relative(block) not in done]
    batch = remaining if batch_size is None else remaining[: int(batch_size)]
    written = []
    with rasterio.open(source_path) as source:
        for block in batch:
            if should_continue is not None and not should_continue():
                return {"written": written, "stopped": True, "total": len(blocks), "completed": sorted(done)}
            relative = _relative(block)
            array = _sample(source, block, method)
            image = _colorize(array, stops, source.nodata)
            target = os.path.join(output_dir, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            Image.fromarray(image, "RGBA").save(target, format="PNG")
            with open(target, "rb") as handle:
                blob = handle.read()
            if png_size(blob) != (block["width"], block["height"]):
                raise PyramidError("png_size", f"{relative} is not {block['width']} pixels.")
            if block["width"] % TILE_PX or block["height"] % TILE_PX:
                raise PyramidError("png_size", "block edge is not a multiple of 256.")
            done.add(relative)
            written.append(relative)
    return {"written": written, "stopped": False, "total": len(blocks), "completed": sorted(done)}


def _relative(block):
    return f"tiles/{block['z']}/{block['x']}/{block['y']}.png"


def _sample(source, block, method):
    import numpy as np
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject

    width, height = block["width"], block["height"]
    destination = np.full((height, width), -9999, dtype=np.float32)
    reproject(
        source=rasterio_band(source),
        destination=destination,
        src_transform=source.transform,
        src_crs=source.crs,
        src_nodata=source.nodata,
        dst_transform=from_bounds(block["minx"], block["miny"], block["maxx"], block["maxy"], width, height),
        dst_crs="EPSG:3857",
        dst_nodata=-9999,
        resampling=method,
    )
    return destination


def rasterio_band(source):
    import rasterio

    return rasterio.band(source, 1)


def _colorize(values, stops, nodata):
    import numpy as np

    ordered = sorted(stops, key=lambda item: item["value"])
    if len(ordered) < 2:
        raise PyramidError("style", "A raster pyramid needs at least two color stops.")
    height, width = values.shape
    colors = np.zeros((height, width, 4), dtype=np.float32)
    colors[:, :] = ordered[0]["rgba"]
    for left, right in zip(ordered, ordered[1:]):
        span = float(right["value"]) - float(left["value"]) or 1.0
        weight = np.clip((values - float(left["value"])) / span, 0, 1)[..., None]
        mixed = (1 - weight) * np.array(left["rgba"]) + weight * np.array(right["rgba"])
        window = (values >= left["value"]) & (values <= right["value"])
        colors[window] = mixed[window]
    above = values > ordered[-1]["value"]
    colors[above] = ordered[-1]["rgba"]
    missing = ~np.isfinite(values)
    if nodata is not None:
        missing = missing | (values == np.float32(nodata)) | (values == -9999)
    colors[missing] = 0
    return colors.astype(np.uint8)
