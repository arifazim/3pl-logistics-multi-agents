"""MCP stdio client — speaks JSON-RPC tools/list and tools/call to pl3_server."""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]


class Pl3McpStdioClient:
    """Real MCP protocol client over stdio subprocess."""

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._stdio_ctx = None
        self._session_ctx = None

    @asynccontextmanager
    async def connect(self) -> AsyncIterator["Pl3McpStdioClient"]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_servers.pl3_server.server"],
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                try:
                    yield self
                finally:
                    self._session = None

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("MCP client not connected — use async with client.connect()")
        result = await self._session.call_tool(name, arguments or {})
        if not result.content:
            return {}
        text = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
        return json.loads(text)

    async def list_tools(self) -> list[str]:
        if not self._session:
            raise RuntimeError("MCP client not connected")
        tools = await self._session.list_tools()
        return [t.name for t in tools.tools]
