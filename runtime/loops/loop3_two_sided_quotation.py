"""Loop 3 — Two-Sided Quotation: customer price ↔ vendor cost margin balance."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, List

from runtime.agent_system import AgentSystem


@dataclass
class QuotationLoopMetrics:
    lane: str
    selected_vendor_id: str
    vendor_cost: float
    customer_price: float
    margin_pct: float
    trajectory_passed: bool
    hitl_required: bool
    violations: List[str] = field(default_factory=list)


@dataclass
class TwoSidedQuotationReport:
    runs: List[QuotationLoopMetrics] = field(default_factory=list)
    all_margins_above_floor: bool = False
    avg_margin_pct: float = 0.0


async def run_two_sided_quotation_loop(lanes: List[str] | None = None) -> TwoSidedQuotationReport:
    """Execute Loop 3 across lanes — track margin from selected vendor cost."""
    lanes = lanes or ["Tracy->Fremont", "Manteca->Hayward"]
    system = AgentSystem()
    report = TwoSidedQuotationReport()

    for lane in lanes:
        result = await system.execute_agent_workflow(
            "dual_quotation",
            {"lane": lane, "sla_tier": "standard", "delivery_time": 20, "shipment_id": f"LOOP3-{lane}"},
        )
        quote = result.get("customer_quote") or {}
        metrics = QuotationLoopMetrics(
            lane=lane,
            selected_vendor_id=quote.get("selected_vendor_id", ""),
            vendor_cost=float(quote.get("vendor_cost", 0)),
            customer_price=float(quote.get("total_rate", 0)),
            margin_pct=float(quote.get("margin_percentage", 0)),
            trajectory_passed=result.get("trajectory_eval", {}).get("passed", False),
            hitl_required=result.get("hitl", {}).get("requires_approval", False),
            violations=result.get("trajectory_eval", {}).get("violations", []),
        )
        report.runs.append(metrics)

    margins = [r.margin_pct for r in report.runs if r.margin_pct > 0]
    report.all_margins_above_floor = all(m >= 12.0 for m in margins)
    report.avg_margin_pct = round(sum(margins) / len(margins), 2) if margins else 0.0
    return report


def run_two_sided_quotation_loop_sync(lanes: List[str] | None = None) -> TwoSidedQuotationReport:
    return asyncio.run(run_two_sided_quotation_loop(lanes))
