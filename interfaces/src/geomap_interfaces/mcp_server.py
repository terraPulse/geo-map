"""Read-only MCP tools on the official Python SDK.

The server returns dataset metadata and URLs. It does not return image bytes,
does not accept a raster URL, and registers no mutation tools. ``build_server``
does not listen. ``serverless_app`` builds a stateless Streamable HTTP ASGI app
and also does not listen; the host must enter the session-manager lifespan.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .auth import Principal, can_read
from .catalog import detail_record, links, list_records
from .errors import InterfaceError
from .paths import dataset_id_error
from .runtime import Runtime
from .values import point_value, window_stats

_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

_INSTRUCTIONS = (
    "Read-only discovery for configured geo-map datasets. "
    "Tools return structured metadata and URLs, never image bytes or base64 rasters. "
    "They cannot fetch an arbitrary URL and they cannot create, update, or delete data. "
    "A dataset without a quantitative backend has no scientific value; do not infer one from a styled PNG."
)


def build_server(runtime: Runtime, principal: Principal) -> MCPServer:
    server = MCPServer(
        "geomap-interfaces",
        title="geo-map interfaces",
        instructions=_INSTRUCTIONS,
        version="0.1.0",
        log_level="WARNING",
    )

    def require(dataset_id: str):
        if dataset_id_error(dataset_id):
            raise ToolError("not_found: unknown dataset")
        dataset = runtime.registry.get(dataset_id)
        if dataset is None:
            raise ToolError("not_found: unknown dataset")
        if not can_read(dataset.access, principal):
            raise ToolError("forbidden: principal cannot read this dataset")
        return dataset

    @server.tool(name="list_datasets", annotations=_READ_ONLY)
    def list_datasets() -> dict:
        """List datasets the current principal may read."""

        return list_records(runtime, principal)

    @server.tool(name="describe_dataset", annotations=_READ_ONLY)
    def describe_dataset(dataset_id: str) -> dict:
        """Describe one dataset, including zoom, CRS, style, and whether numeric values exist."""

        return detail_record(runtime, require(dataset_id))

    @server.tool(name="dataset_links", annotations=_READ_ONLY)
    def dataset_links(dataset_id: str) -> dict:
        """Return TileJSON, tile template, WMS, value, and asset URLs for one dataset."""

        dataset = require(dataset_id)
        return {"dataset_id": dataset.id, "links": links(runtime, dataset)}

    @server.tool(name="dataset_value", annotations=_READ_ONLY)
    def dataset_value(dataset_id: str, lon: float, lat: float) -> dict:
        """Read one numeric value. Returns available=false when no quantitative backend is configured."""

        dataset = require(dataset_id)
        try:
            result = point_value(runtime.data_root, dataset, lon, lat, runtime.budgets)
        except InterfaceError as exc:
            raise ToolError(f"{exc.code}: {exc.message}") from exc
        return result

    @server.tool(name="dataset_stats", annotations=_READ_ONLY)
    def dataset_stats(dataset_id: str, west: float, south: float, east: float, north: float) -> dict:
        """Summarize a numeric window in EPSG:4326. Does not sample styled PNG colors."""

        dataset = require(dataset_id)
        try:
            result = window_stats(runtime.data_root, dataset, west, south, east, north, runtime.budgets)
        except InterfaceError as exc:
            raise ToolError(f"{exc.code}: {exc.message}") from exc
        return result

    return server


def serverless_app(runtime: Runtime, principal: Principal):
    """Stateless JSON Streamable HTTP app. Does not bind a port or open a session."""

    server = build_server(runtime, principal)
    app = server.streamable_http_app(json_response=True, stateless_http=True, streamable_http_path="/mcp")
    return server, app
