"""MCP tool access — in-process (tests) or stdio protocol (production)."""

from __future__ import annotations

import json
import os
from typing import Any

from mcp_servers.pl3_server.handlers import TOOL_REGISTRY


class Pl3McpClient:
    """Calls consolidated MCP tool handlers (in-process). Same names as stdio MCP server."""

    def call(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        if tool_name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown MCP tool: {tool_name}")
        return json.loads(TOOL_REGISTRY[tool_name](**kwargs))

    def rank_vendors(self, lane: str, weight_lbs: float = 1000.0) -> dict[str, Any]:
        return self.call("vendor.rank_for_lane", lane=lane, weight_lbs=weight_lbs)

    def get_vendor_rates(self, lane: str) -> dict[str, Any]:
        return self.call("rate_card.get_vendor_rates", lane=lane)

    def check_policy(self, policy_name: str, value: float, shipment_id: str = "UNKNOWN") -> dict[str, Any]:
        return self.call(
            "policy.check_compliance",
            policy_name=policy_name,
            value=value,
            shipment_id=shipment_id,
        )

    def log_event(self, event_type: str, agent: str, data: dict | None = None) -> dict[str, Any]:
        return self.call(
            "telemetry.log_event",
            event_type=event_type,
            agent=agent,
            data_json=json.dumps(data or {}),
        )

    @staticmethod
    def use_stdio() -> bool:
        return os.getenv("MCP_USE_STDIO", "0") == "1"
