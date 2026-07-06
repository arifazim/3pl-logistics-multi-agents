"""Deterministic pricing — margin from SELECTED vendor effective cost (rate + weight surcharge)."""

from __future__ import annotations

import math
from typing import Any

from runtime.adapters.pl3_mcp_client import Pl3McpClient

MARGIN_FLOOR_PCT = 12.0
SLA_VENDOR_MULTIPLIER = {"standard": 1.0, "express": 1.15}
SLA_CUSTOMER_PREMIUM = {"standard": 0.0, "express": 0.10}


class QuotationEngine:
    def __init__(self, mcp: Pl3McpClient | None = None):
        self.mcp = mcp or Pl3McpClient()

    def calculate_customer_quote(
        self,
        lane: str,
        weight: float = 1000,
        sla_tier: str = "standard",
        vendor_id: str | None = None,
    ) -> dict[str, Any]:
        ranking = self.mcp.rank_vendors(lane, weight_lbs=weight)
        selected = ranking.get("selected")
        if not selected:
            return {"error": "no_vendor_for_lane", "lane": lane}

        if vendor_id:
            selected = next((v for v in ranking.get("ranked", []) if v["vendor_id"] == vendor_id), selected)

        # Actual vendor cost = effective rate (base + weight surcharge) × SLA multiplier
        vendor_cost_base = float(selected.get("effective_rate", selected["rate"]))
        vendor_mult = SLA_VENDOR_MULTIPLIER.get(sla_tier, 1.0)
        vendor_cost = round(vendor_cost_base * vendor_mult, 2)

        customer_base = vendor_cost / (1 - MARGIN_FLOOR_PCT / 100)
        customer_premium = SLA_CUSTOMER_PREMIUM.get(sla_tier, 0.0)
        # Round the price UP to the nearest cent so 2-decimal rounding can never
        # push the realized margin below the floor (e.g. 373.86 would yield 11.999%).
        customer_price = math.ceil(customer_base * (1 + customer_premium) * 100) / 100

        margin_dollars = round(customer_price - vendor_cost, 2)
        margin_pct = round((margin_dollars / customer_price) * 100, 2) if customer_price else 0.0

        lane_meta = self.mcp.call("rate_card.get_customer_lane", lane=lane)

        return {
            "lane": lane,
            "weight": weight,
            "weight_surcharge": selected.get("weight_surcharge", 0),
            "sla_tier": sla_tier,
            "selected_vendor_id": selected["vendor_id"],
            "selected_vendor_name": selected.get("name"),
            "selected_vendor_score": selected.get("final_score"),
            "vendor_cost_base": vendor_cost_base,
            "vendor_cost": vendor_cost,
            "customer_price": customer_price,
            "total_rate": customer_price,
            "margin": margin_dollars,
            "margin_percentage": margin_pct,
            "margin_floor_pct": MARGIN_FLOOR_PCT,
            "list_price_reference": lane_meta.get("base_rate"),
            "target_margin_reference": lane_meta.get("target_margin_pct"),
            "pricing_basis": "selected_vendor_cost",
        }

    def get_vendor_quotes(self, lane: str) -> list[dict[str, Any]]:
        return self.mcp.get_vendor_rates(lane).get("quotes", [])

    def validate_margin(self, customer_price: float, vendor_cost: float) -> bool:
        if customer_price <= 0 or vendor_cost <= 0:
            return False
        return ((customer_price - vendor_cost) / customer_price) * 100 >= MARGIN_FLOOR_PCT
