"""Process settings. Staging fails closed. No secrets are embedded."""

from urllib.parse import urlparse

from .build_allow import parse_allowlist
from .errors import ConfigurationError
from .preview_urls import PATH_ORDERS
from .schema_contract import AUTHORIZED_ACCOUNT, AUTHORIZED_REGION

_BACKEND_DENIED = (
    "admin.terrapulse.com",
    "geo-map-tiles",
    "map-tiles-dev",
)


def _flag(env, name, default="0"):
    return env.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _csv(env, name):
    raw = env.get(name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


class Settings:
    def __init__(
        self,
        *,
        env,
        auth_mode,
        repository,
        file_root,
        dynamodb_table,
        dynamodb_region,
        cognito_region,
        cognito_user_pool_id,
        cognito_client_id,
        preview_hosts,
        tile_backend_base_url="",
        tile_path_order="map",
        builds_enabled=False,
        build_executor="disabled",
        source_allowlist="",
        output_prefix="builds",
        max_build_tiles=32,
        renderer_mode="disabled",
        renderer_function_arn="",
        seed_fixtures,
        allow_fixture_auth,
        cors_origins,
        emit_cors,
        authorized_account=AUTHORIZED_ACCOUNT,
        authorized_region=AUTHORIZED_REGION,
    ):
        self.env = env
        self.auth_mode = auth_mode
        self.repository = repository
        self.file_root = file_root
        self.dynamodb_table = dynamodb_table
        self.dynamodb_region = dynamodb_region
        self.cognito_region = cognito_region
        self.cognito_user_pool_id = cognito_user_pool_id
        self.cognito_client_id = cognito_client_id
        self.preview_hosts = tuple(preview_hosts)
        self.tile_backend_base_url = (tile_backend_base_url or "").rstrip("/")
        self.tile_path_order = tile_path_order or "map"
        self.builds_enabled = bool(builds_enabled)
        self.build_executor = build_executor or "disabled"
        self.source_allowlist = parse_source_allowlist(source_allowlist)
        self.output_prefix = output_prefix or "builds"
        self.max_build_tiles = int(max_build_tiles)
        self.renderer_mode = renderer_mode or "disabled"
        self.renderer_function_arn = renderer_function_arn or ""
        self.seed_fixtures = seed_fixtures
        self.allow_fixture_auth = allow_fixture_auth
        self.cors_origins = tuple(cors_origins)
        self.emit_cors = emit_cors
        self.authorized_account = authorized_account
        self.authorized_region = authorized_region
        self._validate()

    def _validate(self):
        if self.env in {"prod", "production"}:
            raise ConfigurationError("This increment refuses LAYER_MANAGER_ENV=prod.")
        if self.env not in {"local", "staging", "test"}:
            raise ConfigurationError("LAYER_MANAGER_ENV must be local, test, or staging.")
        if self.allow_fixture_auth and self.env not in {"local", "test"}:
            raise ConfigurationError("Fixture identities are local-only.")
        if self.auth_mode == "local-fixture" and self.env not in {"local", "test"}:
            raise ConfigurationError("local-fixture auth is local-only.")
        if self.seed_fixtures and self.env not in {"local", "staging"}:
            raise ConfigurationError("Fixture seed is only defined for local and staging.")
        if self.auth_mode == "local-fixture" and not self.allow_fixture_auth:
            raise ConfigurationError("local-fixture auth requires LAYER_MANAGER_ALLOW_FIXTURE_AUTH=1.")
        if self.env == "staging":
            if self.auth_mode != "apigateway-cognito":
                raise ConfigurationError("Staging auth must be apigateway-cognito.")
            if self.repository != "dynamodb":
                raise ConfigurationError("Staging repository must be dynamodb.")
            if not self.dynamodb_table or not self.dynamodb_region:
                raise ConfigurationError("Staging DynamoDB table and region are required.")
            if self.dynamodb_region != self.authorized_region:
                raise ConfigurationError("Staging DynamoDB region must be us-west-2.")
            if not self.cognito_region or not self.cognito_user_pool_id or not self.cognito_client_id:
                raise ConfigurationError("Staging Cognito settings are required.")
            if self.cognito_region != self.authorized_region:
                raise ConfigurationError("Staging Cognito region must be us-west-2.")
            if self.allow_fixture_auth:
                raise ConfigurationError("Staging refuses fixture auth.")
        if "*" in self.cors_origins:
            raise ConfigurationError("CORS origin * is refused.")
        for host in self.preview_hosts:
            if host == "*" or not host.startswith("https://") or _denied_backend(host):
                raise ConfigurationError("Preview hosts must be explicit https origins and must not be the admin domain or tile buckets.")
        if self.tile_path_order not in PATH_ORDERS:
            raise ConfigurationError("Tile path order must be map, zx_y, zxy, or xyz.")
        if self.tile_backend_base_url:
            validate_tile_backend_base(self.tile_backend_base_url)
        if self.build_executor not in {"disabled", "fixture-offline", "gio"}:
            raise ConfigurationError("Build executor is not recognized.")
        if self.renderer_mode not in {"disabled", "fixture-offline", "lambda"}:
            raise ConfigurationError("Renderer mode is not recognized.")
        if self.env == "staging" and self.build_executor == "fixture-offline":
            raise ConfigurationError("Staging does not run fixture builds.")
        if self.env == "staging" and self.renderer_mode == "fixture-offline":
            raise ConfigurationError("Staging does not use the offline renderer fixture.")
        if self.renderer_mode == "lambda":
            from .renderer_preview import validate_function_arn

            validate_function_arn(self.renderer_function_arn)
        if self.builds_enabled and not self.source_allowlist:
            raise ConfigurationError("Real builds require a source allowlist.")
        if ".." in self.output_prefix or self.output_prefix.startswith("/"):
            raise ConfigurationError("Output prefix is not allowed.")

    def effective_preview_hosts(self):
        hosts = list(self.preview_hosts)
        if self.tile_backend_base_url:
            origin = origin_of(self.tile_backend_base_url)
            if origin not in hosts:
                hosts.append(origin)
        return tuple(hosts)

    @classmethod
    def from_env(cls, env=None):
        if env is None:
            import os

            env = os.environ
        name = env.get("LAYER_MANAGER_ENV", "local").strip().lower()
        if name == "staging":
            auth_mode = env.get("LAYER_MANAGER_AUTH_MODE", "apigateway-cognito").strip()
            repository = env.get("LAYER_MANAGER_REPOSITORY", "dynamodb").strip()
            seed_default = "1"
        elif name == "test":
            auth_mode = env.get("LAYER_MANAGER_AUTH_MODE", "local-fixture").strip()
            repository = env.get("LAYER_MANAGER_REPOSITORY", "memory").strip()
            seed_default = "0"
        else:
            auth_mode = env.get("LAYER_MANAGER_AUTH_MODE", "local-fixture").strip()
            repository = env.get("LAYER_MANAGER_REPOSITORY", "file").strip()
            seed_default = "1"
        return cls(
            env=name,
            auth_mode=auth_mode,
            repository=repository,
            file_root=env.get("LAYER_MANAGER_FILE_ROOT") or None,
            dynamodb_table=env.get("LAYER_MANAGER_DYNAMODB_TABLE") or None,
            dynamodb_region=env.get("LAYER_MANAGER_DYNAMODB_REGION") or env.get("AWS_REGION") or None,
            cognito_region=env.get("LAYER_MANAGER_COGNITO_REGION") or None,
            cognito_user_pool_id=env.get("LAYER_MANAGER_COGNITO_USER_POOL_ID") or None,
            cognito_client_id=env.get("LAYER_MANAGER_COGNITO_CLIENT_ID") or None,
            preview_hosts=_csv(env, "LAYER_MANAGER_PREVIEW_HOSTS"),
            tile_backend_base_url=env.get("LAYER_MANAGER_TILE_BACKEND_BASE_URL", ""),
            tile_path_order=env.get("LAYER_MANAGER_TILE_PATH_ORDER", "map") or "map",
            builds_enabled=_flag(env, "LAYER_MANAGER_BUILDS_ENABLED", "0"),
            build_executor=env.get("LAYER_MANAGER_BUILD_EXECUTOR", "disabled") or "disabled",
            source_allowlist=env.get("LAYER_MANAGER_SOURCE_ALLOWLIST", ""),
            output_prefix=env.get("LAYER_MANAGER_OUTPUT_PREFIX", "builds") or "builds",
            max_build_tiles=int(env.get("LAYER_MANAGER_MAX_BUILD_TILES", "32") or "32"),
            renderer_mode=env.get("LAYER_MANAGER_RENDERER_MODE", "disabled") or "disabled",
            renderer_function_arn=env.get("LAYER_MANAGER_RENDERER_FUNCTION_ARN", ""),
            seed_fixtures=_flag(env, "LAYER_MANAGER_SEED_FIXTURES", seed_default),
            allow_fixture_auth=_flag(env, "LAYER_MANAGER_ALLOW_FIXTURE_AUTH", "1" if name in {"local", "test"} else "0"),
            cors_origins=_csv(env, "LAYER_MANAGER_CORS_ORIGINS"),
            emit_cors=_flag(env, "LAYER_MANAGER_EMIT_CORS", "1" if name == "local" else "0"),
        )


def parse_source_allowlist(value):
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return parse_allowlist(value)


def _denied_backend(value):
    lowered = value.lower()
    return any(item in lowered for item in _BACKEND_DENIED)


def origin_of(url):
    parsed = urlparse(url)
    origin = f"https://{parsed.hostname}" if parsed.hostname else ""
    if parsed.port:
        origin += f":{parsed.port}"
    return origin


def validate_tile_backend_base(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ConfigurationError("Tile backend base URL must be https and must not include userinfo.")
    if _denied_backend(url):
        raise ConfigurationError(
            "Tile backend base URL must not target the admin domain, the tile buckets, or the existing map-tiles-dev front."
        )
    if ".png" in parsed.path or "{z}" in url or "{tag}" in url:
        raise ConfigurationError("Tile backend base URL is an origin or prefix, not a tile template.")
