"""Loop 2: Plan → compliance-critic → replan with bounded iterations."""

from __future__ import annotations

from typing import Any

from runtime.adapters.pl3_mcp_client import Pl3McpClient
from runtime.evaluation.evaluator import MarginEvaluator


class ComplianceReplanLoop:
    """Bounded iteration loop for compliance-critic → replan.

    Guardrails:
    - Max M iterations
    - Deterministic compliance check (not LLM)
    - Escalation if still violating after M
    - A2A handoff: planning agent ↔ compliance agent
    """

    MAX_ITERATIONS = 3

    def __init__(self, mcp: Pl3McpClient | None = None):
        self.mcp = mcp or Pl3McpClient()
        self.margin_evaluator = MarginEvaluator()

    def execute(
        self,
        shipment_id: str,
        lane: str,
        weight: float,
        margin: float,
        delivery_time: float,
        initial_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute compliance-critic → replan loop.

        Algorithm:
        1. Propose assignment (route/vendor/dock slot)
        2. Loop (max M rounds):
           - violations = compliance_check(assignment)
           - If none: break → proceed
           - Else: replan around violated constraint (next slot / next vendor)
        3. Escalate if still violating after M
        """
        # Step 1: Initial plan (or use provided)
        current_plan = initial_plan or self._generate_initial_plan(shipment_id, lane, weight)

        # Step 2: Bounded iteration loop
        iteration = 0
        violations = []
        final_plan = current_plan

        for iteration in range(self.MAX_ITERATIONS):
            # Deterministic compliance check
            check_result = self._compliance_check(
                shipment_id, margin, delivery_time, weight, current_plan
            )
            violations = check_result.get("violations", [])

            if not violations:
                break  # No violations → proceed

            # Replan around violated constraint
            current_plan = self._replan_around_violations(current_plan, violations, iteration)
            final_plan = current_plan

        # Step 3: Escalation if still violating
        if violations:
            return {
                "status": "escalate_to_hitl",
                "shipment_id": shipment_id,
                "violations": violations,
                "iteration_count": iteration + 1,
                "final_plan": final_plan,
                "escalation_reason": f"Still violating after {iteration + 1} replan attempts",
            }

        return {
            "status": "success",
            "shipment_id": shipment_id,
            "final_plan": final_plan,
            "iteration_count": iteration + 1,
            "compliance_check": {"violations": [], "passed": True},
        }

    def _generate_initial_plan(self, shipment_id: str, lane: str, weight: float) -> dict[str, Any]:
        """Generate initial assignment plan."""
        # Simple initial plan: select top vendor, assign to first available dock
        ranking = self.mcp.rank_vendors(lane, weight_lbs=weight)
        selected = ranking.get("selected", ranking.get("ranked", [{}])[0])

        return {
            "shipment_id": shipment_id,
            "vendor_id": selected.get("vendor_id", "V001"),
            "dock_id": "D001",
            "warehouse": lane.split("->")[0] if "->" in lane else "Tracy",
            "weight": weight,
        }

    def _compliance_check(
        self,
        shipment_id: str,
        margin: float,
        delivery_time: float,
        weight: float,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Deterministic compliance check — no LLM."""
        violations = []

        # Margin check — margin parameter IS the margin percentage
        if margin < MarginEvaluator.MARGIN_FLOOR_PCT:
            violations.append({
                "type": "margin",
                "threshold": MarginEvaluator.MARGIN_FLOOR_PCT,
                "actual": margin,
            })

        # SLA check (delivery time <= 24h)
        if delivery_time > 24:
            violations.append({
                "type": "sla",
                "threshold": 24,
                "actual": delivery_time,
            })

        # Weight check (<= 45000 lbs)
        if weight > 45000:
            violations.append({
                "type": "weight",
                "threshold": 45000,
                "actual": weight,
            })

        return {"violations": violations, "passed": len(violations) == 0}

    def _replan_around_violations(
        self, current_plan: dict[str, Any], violations: list[dict[str, Any]], iteration: int
    ) -> dict[str, Any]:
        """Replan around violated constraints (deterministic)."""
        new_plan = current_plan.copy()

        for violation in violations:
            if violation["type"] == "margin":
                # Try next vendor (deterministic by ranking)
                ranking = self.mcp.rank_vendors(
                    f"{new_plan['warehouse']}->{new_plan.get('destination', 'Fremont')}",
                    weight_lbs=new_plan["weight"],
                )
                ranked = ranking.get("ranked", [])
                current_idx = next(
                    (i for i, v in enumerate(ranked) if v["vendor_id"] == new_plan["vendor_id"]),
                    -1,
                )
                if current_idx + 1 < len(ranked):
                    new_plan["vendor_id"] = ranked[current_idx + 1]["vendor_id"]

            elif violation["type"] == "sla":
                # Try express tier (faster delivery)
                new_plan["sla_tier"] = "express"

            elif violation["type"] == "weight":
                # Split shipment (simplified: reduce weight)
                new_plan["weight"] = violation["threshold"]

        return new_plan
