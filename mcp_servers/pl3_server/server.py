"""Consolidated 3PL MCP server — stdio JSON-RPC (tools/list, tools/call).

Run: PYTHONPATH=. python -m mcp_servers.pl3_server.server
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

# Official MCP SDK (pip package `mcp`) — NOT the legacy mcp/ REST folder
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_servers.pl3_server.handlers import TOOL_REGISTRY

server = Server("3pl-orchestrator")


def _tool_schema(name: str, fn) -> Tool:
    schemas: dict[str, dict] = {
        "rate_card.get_customer_lane": {
            "type": "object",
            "properties": {"lane": {"type": "string"}},
            "required": ["lane"],
        },
        "rate_card.get_vendor_rates": {
            "type": "object",
            "properties": {"lane": {"type": "string"}},
            "required": ["lane"],
        },
        "vendor.list": {"type": "object", "properties": {}},
        "vendor.get": {
            "type": "object",
            "properties": {"vendor_id": {"type": "string"}},
            "required": ["vendor_id"],
        },
        "vendor.rank_for_lane": {
            "type": "object",
            "properties": {"lane": {"type": "string"}, "weight_lbs": {"type": "number"}},
            "required": ["lane"],
        },
        "policy.list": {"type": "object", "properties": {}},
        "policy.check_compliance": {
            "type": "object",
            "properties": {
                "policy_name": {"type": "string"},
                "value": {"type": "number"},
                "shipment_id": {"type": "string"},
            },
            "required": ["policy_name", "value"],
        },
        "telemetry.get_snapshot": {"type": "object", "properties": {}},
        "telemetry.log_event": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "agent": {"type": "string"},
                "data_json": {"type": "string"},
            },
            "required": ["event_type", "agent"],
        },
        "tms.list_shipments": {"type": "object", "properties": {}},
    }
    return Tool(
        name=name,
        description=(fn.__doc__ or name).strip(),
        inputSchema=schemas.get(name, {"type": "object", "properties": {}}),
    )


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [_tool_schema(name, fn) for name, fn in TOOL_REGISTRY.items()]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    if name not in TOOL_REGISTRY:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    args = arguments or {}
    result = TOOL_REGISTRY[name](**args)
    return [TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
