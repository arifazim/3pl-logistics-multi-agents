"""Vendor scoring via consolidated MCP."""

from __future__ import annotations

from typing import Any

from runtime.adapters.pl3_mcp_client import Pl3McpClient


class VendorScorer:
    def __init__(self, mcp: Pl3McpClient | None = None):
        self.mcp = mcp or Pl3McpClient()

    async def score_vendor(self, vendor_id: str, lane: str, weight: float = 1000.0) -> dict[str, Any]:
        ranking = self.mcp.rank_vendors(lane, weight_lbs=weight)
        for vendor in ranking.get("ranked", []):
            if vendor["vendor_id"] == vendor_id:
                return vendor
        return {"vendor_id": vendor_id, "final_score": 0, "reason": "No rate for lane"}

    async def rank_vendors(self, lane: str, weight: float = 1000.0, requirements: dict | None = None) -> list[dict[str, Any]]:
        return self.mcp.rank_vendors(lane, weight_lbs=weight).get("ranked", [])
