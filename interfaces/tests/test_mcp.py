import asyncio
import json

from mcp import Client
from mcp.types.version import LATEST_HANDSHAKE_VERSION, LATEST_PROTOCOL_VERSION

from geomap_interfaces.auth import ANONYMOUS
from geomap_interfaces.mcp_server import build_server, serverless_app

from support import ANALYST, build_runtime

EXPECTED = {"list_datasets", "describe_dataset", "dataset_links", "dataset_value", "dataset_stats"}


def test_handshake_discovery_invocation_and_authorization(tmp_path):
    runtime = build_runtime(tmp_path)
    asyncio.run(_handshake(runtime))
    asyncio.run(_modern(runtime))


def test_serverless_app_is_stateless_and_does_not_listen(tmp_path):
    runtime = build_runtime(tmp_path)
    server, app = serverless_app(runtime, ANONYMOUS)
    assert server.session_manager.stateless is True
    assert server.session_manager.json_response is True
    assert app is not None


async def _handshake(runtime):
    server = build_server(runtime, ANONYMOUS)
    async with Client(server, mode="legacy") as client:
        assert client.protocol_version == LATEST_HANDSHAKE_VERSION
        assert client.server_info.name == "geomap-interfaces"
        assert client.server_capabilities.tools is not None
        await _tools_and_calls(client, restricted=False)


async def _modern(runtime):
    server = build_server(runtime, ANALYST)
    async with Client(server) as client:
        assert client.protocol_version == LATEST_PROTOCOL_VERSION
        await _tools_and_calls(client, restricted=True)


async def _tools_and_calls(client, restricted: bool):
    listing = await client.list_tools()
    names = {tool.name for tool in listing.tools}
    assert names == EXPECTED
    for tool in listing.tools:
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is False
        assert "url" not in tool.input_schema.get("properties", {})
    resources = await client.list_resources()
    assert resources.resources == []

    listed = _payload(await client.call_tool("list_datasets", {}))
    ids = [item["id"] for item in listed["datasets"]]
    assert "demo/quad" in ids
    assert ("private/layer" in ids) is restricted

    links = _payload(await client.call_tool("dataset_links", {"dataset_id": "demo/quad"}))
    assert links["links"]["tilejson"].endswith("/demo/quad/tilejson")
    assert "base64" not in json.dumps(links)

    absent = _payload(await client.call_tool("dataset_value", {"dataset_id": "demo/quad", "lon": 1, "lat": 1}))
    assert absent["available"] is False
    assert "value" not in absent

    present = _payload(await client.call_tool("dataset_value", {"dataset_id": "demo/numbers", "lon": -9.5, "lat": 43.5}))
    assert present["value"] == 1.0

    denied = await client.call_tool("describe_dataset", {"dataset_id": "private/layer"})
    if restricted:
        assert denied.is_error is False
    else:
        assert denied.is_error is True
        assert "forbidden:" in denied.content[0].text


def _payload(result) -> dict:
    assert result.is_error is False
    if isinstance(result.structured_content, dict) and "datasets" in result.structured_content or (
        isinstance(result.structured_content, dict) and "available" in result.structured_content
    ):
        return result.structured_content
    if isinstance(result.structured_content, dict) and "result" in result.structured_content:
        return result.structured_content["result"]
    return json.loads(result.content[0].text)
