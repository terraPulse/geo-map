"""Response flags. Dangerous effects are constants and stay false."""


def effects(*, registry_updated):
    return {
        "registry_updated": bool(registry_updated),
        "png_pyramid_regenerated": False,
        "cog_rewritten": False,
        "legacy_setting_ini_written": False,
        "legacy_color_txt_written": False,
        "production_bucket_mutated": False,
        "tile_bytes_written": False,
        "remote_urls_fetched": False,
        "dns_changed": False,
        "users_invited": False,
    }


REGISTRY_EFFECTS_STORED = {
    "png_pyramid_regenerated_on_write": False,
    "note": (
        "Writing this registry record does not regenerate PNG pyramids, "
        "rewrite COGs, or update legacy setting.ini files."
    ),
}
