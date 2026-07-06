"""Loop 1: Quote/vendor evaluator-optimizer with deterministic margin guardrails."""

from __future__ import annotations

from typing import Any

from runtime.adapters.pl3_mcp_client import Pl3McpClient
from runtime.evaluation.evaluator import MarginEvaluator
from runtime.tools.quotation_engine import QuotationEngine


class VendorEvaluatorLoop:
    """Bounded iteration loop for vendor selection with deterministic margin checks.

    Guardrails:
    - Max N iterations (shrinking candidate set)
    - Deterministic margin check (not LLM)
    - Escalation to HITL if no candidate passes
    - Tried-set tracking to prevent cycling
    """

    MAX_ITERATIONS = 5
    HITL_MARGIN_GAP_THRESHOLD = 2.0  # Escalate if margin gap > 2%

    def __init__(self, mcp: Pl3McpClient | None = None):
        self.mcp = mcp or Pl3McpClient()
        self.quotation_engine = QuotationEngine(mcp=self.mcp)
        self.evaluator = MarginEvaluator()

    def execute(
        self,
        lane: str,
        weight: float = 1000,
        sla_tier: str = "standard",
        vendor_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute vendor evaluator loop.

        Algorithm:
        1. Gather vendor quotes (deterministic ranking)
        2. Loop (max N rounds, shrinking candidate set):
           - Select next-best untried vendor
           - Calculate real_margin deterministically
           - eval = margin ≥ floor AND competitiveness AND reliability
           - If passes: break → propose
           - Else: mark vendor tried, continue
        3. If no candidate passes after N: escalate to HITL with margin gap
        """
        # Step 1: Gather vendor quotes
        ranking = self.mcp.rank_vendors(lane, weight_lbs=weight)
        ranked_vendors = ranking.get("ranked", [])
        cheapest_vendor = ranked_vendors[0] if ranked_vendors else None

        if not ranked_vendors:
            return {"status": "no_vendors", "lane": lane, "escalation": "hitl"}

        # Step 2: Bounded iteration loop
        tried_vendor_ids = set()
        iteration = 0
        selected_vendor = None
        evaluation_result = None

        for iteration in range(self.MAX_ITERATIONS):
            # Select next-best untried vendor
            candidate = self._select_next_untried(ranked_vendors, tried_vendor_ids)
            if not candidate:
                break  # No more candidates

            tried_vendor_ids.add(candidate["vendor_id"])

            # Calculate customer price deterministically
            quote = self.quotation_engine.calculate_customer_quote(
                lane, weight=weight, sla_tier=sla_tier, vendor_id=candidate["vendor_id"]
            )

            # Deterministic evaluation
            evaluation_result = self.evaluator.evaluate(
                customer_price=quote["customer_price"],
                vendor_cost=quote["vendor_cost"],
                cheapest_vendor_cost=cheapest_vendor["rate"] if cheapest_vendor else quote["vendor_cost"],
                vendor_reliability=candidate.get("reliability_score", 0),
            )

            if evaluation_result["passes"]:
                selected_vendor = candidate
                break

        # Step 3: Escalation if no candidate passes
        if not selected_vendor:
            margin_gap = evaluation_result.get("margin_gap", 0) if evaluation_result else 0
            escalation_reason = (
                f"Margin gap {margin_gap}% after {iteration + 1} iterations"
                if margin_gap > self.HITL_MARGIN_GAP_THRESHOLD
                else f"No vendor passed evaluation after {iteration + 1} iterations"
            )
            return {
                "status": "escalate_to_hitl",
                "lane": lane,
                "weight": weight,
                "sla_tier": sla_tier,
                "tried_vendors": list(tried_vendor_ids),
                "margin_gap": margin_gap,
                "escalation_reason": escalation_reason,
                "iteration_count": iteration + 1,
            }

        # Success path
        final_quote = self.quotation_engine.calculate_customer_quote(
            lane, weight=weight, sla_tier=sla_tier, vendor_id=selected_vendor["vendor_id"]
        )

        return {
            "status": "success",
            "lane": lane,
            "weight": weight,
            "sla_tier": sla_tier,
            "selected_vendor": selected_vendor,
            "quote": final_quote,
            "evaluation": evaluation_result,
            "iteration_count": iteration + 1,
            "tried_vendors": list(tried_vendor_ids),
        }

    def _select_next_untried(self, ranked_vendors: list[dict[str, Any]], tried_ids: set[str]) -> dict[str, Any] | None:
        """Select next-best untried vendor from ranked list."""
        for vendor in ranked_vendors:
            if vendor["vendor_id"] not in tried_ids:
                return vendor
        return None
