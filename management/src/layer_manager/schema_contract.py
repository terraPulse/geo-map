"""Dataset contract constants for geo-map.layer-registry.v1.

The sibling interfaces branch owns any future copy under interfaces/.
This package is the staging registry's copy. The parent integrates the
schema before any shared use. Do not treat this module as a license to
edit interfaces/.
"""

SCHEMA_ID = "geo-map.layer-registry.v1"
LEGACY_NAMESPACE = "geo-map.legacy-setting-ini"
CONTRACT_VERSION = 1

# Phrases the API requires. The UI must show the same strings.
CONFIRM_CREATE_DRAFT = "create-draft"
CONFIRM_PUBLISH = "publish-registry-only"
CONFIRM_IMPORT = "import-legacy-draft"
CONFIRM_RESTORE = "restore-registry-only"

CONFIRMATIONS = (
    CONFIRM_CREATE_DRAFT,
    CONFIRM_PUBLISH,
    CONFIRM_IMPORT,
    CONFIRM_RESTORE,
)

INVENTORY_REGISTRY = "registry"
INVENTORY_SYNTHETIC = "synthetic-fixture"

BACKEND_PNG = "png-pyramid"
BACKEND_COG = "cog"
BACKENDS = (BACKEND_PNG, BACKEND_COG)

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUSES = (STATUS_DRAFT, STATUS_PUBLISHED)

ROLE_ADMIN = "layer-admin"
ROLE_READER = "layer-reader"
ROLES = (ROLE_ADMIN, ROLE_READER)

AUTHORIZED_ACCOUNT = "544020760996"
AUTHORIZED_REGION = "us-west-2"
AUTHORIZED_PROFILE = "mfeng"
REFUSED_PROFILE = "6g"

# Staging guard: this increment refuses to store live-system pointers.
DENIED_SUBSTRINGS = (
    "geo-map-tiles",
    "admin.terrapulse.com",
    "arn:aws:s3:::geo-map-tiles",
)

STORED_RECORD_KEYS = (
    "schema",
    "tag",
    "title",
    "status",
    "revision",
    "synthetic",
    "inventory",
    "backend",
    "pyramid",
    "cog",
    "bounds",
    "style",
    "nodata",
    "source_revisions",
    "authorized_tile_template",
    "legacy_compat",
    "validation",
    "registry_effects",
    "created_at",
    "updated_at",
    "updated_by",
    "content_digest",
)

CLIENT_LAYER_KEYS = (
    "tag",
    "title",
    "backend",
    "pyramid",
    "cog",
    "bounds",
    "style",
    "nodata",
    "source_revisions",
    "authorized_tile_template",
)

AGGREGATES = ("mean", "median", "dominated")

TILE_PIXEL_SIZE = 256
WEB_MERCATOR_LIMIT = 20037508.342789244
