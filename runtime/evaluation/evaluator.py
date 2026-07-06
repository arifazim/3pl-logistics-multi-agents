"""Deterministic evaluator signals for loop guardrails."""

from __future__ import annotations

from typing import Any


class MarginEvaluator:
    """Deterministic margin evaluation — no LLM arithmetic."""

    MARGIN_FLOOR_PCT = 12.0
    COMPETITIVENESS_BAND_PCT = 15.0  # Allow up to 15% above cheapest
    RELIABILITY_THRESHOLD = 85.0

    @staticmethod
    def real_margin(customer_price: float, vendor_cost: float) -> float:
        """Calculate actual margin percentage deterministically."""
        if customer_price <= 0 or vendor_cost <= 0:
            return 0.0
        return ((customer_price - vendor_cost) / customer_price) * 100

    @staticmethod
    def margin_passes(customer_price: float, vendor_cost: float) -> bool:
        """Check if margin meets floor."""
        return MarginEvaluator.real_margin(customer_price, vendor_cost) >= MarginEvaluator.MARGIN_FLOOR_PCT

    @staticmethod
    def competitiveness_passes(customer_price: float, cheapest_vendor_cost: float) -> bool:
        """Check if price is within competitiveness band of cheapest."""
        if cheapest_vendor_cost <= 0:
            return False
        max_allowed = cheapest_vendor_cost * (1 + MarginEvaluator.COMPETITIVENESS_BAND_PCT / 100)
        return customer_price <= max_allowed

    @staticmethod
    def reliability_passes(vendor_reliability: float) -> bool:
        """Check if vendor meets reliability threshold."""
        return vendor_reliability >= MarginEvaluator.RELIABILITY_THRESHOLD

    @staticmethod
    def evaluate(
        customer_price: float,
        vendor_cost: float,
        cheapest_vendor_cost: float,
        vendor_reliability: float,
    ) -> dict[str, Any]:
        """Full evaluation with all checks."""
        margin_pct = MarginEvaluator.real_margin(customer_price, vendor_cost)
        margin_ok = MarginEvaluator.margin_passes(customer_price, vendor_cost)
        competitive = MarginEvaluator.competitiveness_passes(customer_price, cheapest_vendor_cost)
        reliable = MarginEvaluator.reliability_passes(vendor_reliability)

        return {
            "margin_pct": margin_pct,
            "margin_ok": margin_ok,
            "competitive": competitive,
            "reliable": reliable,
            "passes": margin_ok and competitive and reliable,
            "margin_gap": MarginEvaluator.MARGIN_FLOOR_PCT - margin_pct if not margin_ok else 0,
        }
