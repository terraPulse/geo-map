"""Hard limits shared by tiles, WMS, assets, and numeric reads."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Budgets:
    max_wms_edge: int = 1024
    max_wms_pixels: int = 1024 * 1024
    max_blocks: int = 16
    max_mosaic_pixels: int = 4_000_000
    max_asset_bytes: int = 1_000_000
    max_stats_cells: int = 262_144
    max_zoom: int = 22
    tile_edge: int = 256

    def check(self) -> None:
        if self.max_wms_edge < 1 or self.max_wms_pixels < 1:
            raise ValueError("pixel budgets must be positive")
        if self.max_blocks < 1 or self.max_mosaic_pixels < 1:
            raise ValueError("mosaic budgets must be positive")
        if self.tile_edge != 256:
            raise ValueError("the PNG pyramid contract uses 256-pixel tiles")
        if self.max_zoom < 0 or self.max_zoom > 28:
            raise ValueError("max_zoom is out of range")
