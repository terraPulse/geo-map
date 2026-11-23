import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ROOT = Path(__file__).resolve().parents[1]


def local_settings(**overrides):
    from layer_manager.settings import Settings

    values = dict(
        env="test",
        auth_mode="local-fixture",
        repository="memory",
        file_root=None,
        dynamodb_table=None,
        dynamodb_region=None,
        cognito_region=None,
        cognito_user_pool_id=None,
        cognito_client_id=None,
        preview_hosts=(),
        seed_fixtures=False,
        allow_fixture_auth=True,
        cors_origins=("http://127.0.0.1:8765",),
        emit_cors=True,
    )
    values.update(overrides)
    return Settings(**values)


def staging_settings(**overrides):
    from layer_manager.settings import Settings

    values = dict(
        env="staging",
        auth_mode="apigateway-cognito",
        repository="dynamodb",
        file_root=None,
        dynamodb_table="geo-map-layer-manager-staging-registry",
        dynamodb_region="us-west-2",
        cognito_region="us-west-2",
        cognito_user_pool_id="us-west-2_Example",
        cognito_client_id="client",
        preview_hosts=(),
        seed_fixtures=False,
        allow_fixture_auth=False,
        cors_origins=("https://d111111abcdef8.cloudfront.net",),
        emit_cors=False,
    )
    values.update(overrides)
    return Settings(**values)


def api(settings=None):
    from layer_manager.app_factory import build_api
    from layer_manager.repository import MemoryRepository

    settings = settings or local_settings()
    return build_api(settings, repository=MemoryRepository())


def call(api_obj, method, path, body=None, actor="fixture-admin", event=None, headers=None):
    import json

    headers = dict(headers or {})
    if actor:
        headers["x-layer-manager-fixture-actor"] = actor
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    query = {}
    if "?" in path:
        path, raw_query = path.split("?", 1)
        from urllib.parse import parse_qs

        query = parse_qs(raw_query)
    status, response_headers, payload = api_obj.handle(method, path, query, headers, raw, apigateway_event=event)
    return status, response_headers, json.loads(payload.decode("utf-8"))
