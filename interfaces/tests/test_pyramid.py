import numpy as np
import pytest
from PIL import Image

from geomap_interfaces.errors import InterfaceError
from geomap_interfaces.mercator import ORIGIN_SHIFT
from geomap_interfaces.pyramid import render_bbox, render_xyz

from support import build_runtime


def test_view_zooms_resample_stored_blocks_and_ignore_source_files(tmp_path, monkeypatch):
    runtime = build_runtime(tmp_path)
    dataset = runtime.registry.get("demo/quad")
    opened = []
    real_open = Image.open

    def spy(path, *args, **kwargs):
        opened.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Image, "open", spy)
    north_east = render_xyz(dataset, runtime.store, 1, 1, 0, runtime.budgets)
    assert tuple(north_east[0, 10]) == (180, 0, 0, 255)
    assert tuple(north_east[0, 200]) == (255, 140, 0, 255)
    finer = render_xyz(dataset, runtime.store, 2, 3, 0, runtime.budgets)
    assert np.all(finer[:, :, 0] == 255)
    assert np.all(finer[:, :, 1] == 140)
    south_west = render_xyz(dataset, runtime.store, 1, 0, 1, runtime.budgets)
    assert np.all(south_west[:, :, 3] == 0)
    assert opened
    assert all(path.endswith("/demo/quad/tiles/1/0/0.png") for path in opened)


def test_arbitrary_mercator_window_is_cropped_not_a_whole_tile(tmp_path):
    runtime = build_runtime(tmp_path)
    dataset = runtime.registry.get("demo/quad")
    origin = ORIGIN_SHIFT
    orange = render_bbox(
        dataset,
        runtime.store,
        sampling="mercator",
        west=origin * 0.75,
        south=origin * 0.25,
        east=origin * 0.95,
        north=origin * 0.75,
        width=8,
        height=8,
        budgets=runtime.budgets,
    )
    assert np.all(orange[:, :, 0] == 255)
    assert np.all(orange[:, :, 1] == 140)
    red = render_bbox(
        dataset,
        runtime.store,
        sampling="mercator",
        west=origin * 0.10,
        south=origin * 0.20,
        east=origin * 0.40,
        north=origin * 0.80,
        width=8,
        height=8,
        budgets=runtime.budgets,
    )
    assert np.all(red[:, :, 0] == 180)
    assert np.all(red[:, :, 1] == 0)


def test_dataset_bounds_mask_pixels_outside_the_declared_extent(tmp_path):
    runtime = build_runtime(tmp_path)
    dataset = runtime.registry.get("demo/bounded")
    origin = ORIGIN_SHIFT
    masked = render_bbox(
        dataset,
        runtime.store,
        sampling="mercator",
        west=-origin * 0.80,
        south=-origin * 0.80,
        east=-origin * 0.20,
        north=-origin * 0.20,
        width=6,
        height=6,
        budgets=runtime.budgets,
    )
    assert np.all(masked[:, :, 3] == 0)


def test_symlink_block_outside_the_root_is_rejected(tmp_path):
    runtime = build_runtime(tmp_path)
    outside = tmp_path.parent / "outside-block.png"
    Image.fromarray(np.full((512, 512, 4), (1, 2, 3, 255), dtype=np.uint8), mode="RGBA").save(outside)
    block = tmp_path / "demo" / "quad" / "tiles" / "1" / "0" / "0.png"
    block.unlink()
    block.symlink_to(outside)
    dataset = runtime.registry.get("demo/quad")
    with pytest.raises(InterfaceError, match="escapes"):
        render_xyz(dataset, runtime.store, 1, 1, 0, runtime.budgets)
