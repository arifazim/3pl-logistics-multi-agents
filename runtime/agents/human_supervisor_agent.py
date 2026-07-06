"""Human Supervisor Agent — decide when a human must approve, and present a
structured, decision-ready summary at the HITL gate.

Implements the `human_supervisor` skill contract: it reuses `evaluate_hitl`
(runtime/hitl/gate.py) for the escalation triggers, then wraps the raw decision in a
structured summary a supervisor can act on in seconds — action, rationale, key metrics,
recommendation, and reversibility.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from runtime.agy.loader import load_agy
from runtime.hitl.gate import evaluate_hitl
from runtime.skills.loader import load_agent_skills


class KeyMetrics(BaseModel):
    margin_pct: float
    total_rate: float
    vendor_id: str | None = None


class SupervisorSummary(BaseModel):
    action: str
    rationale: str
    key_metrics: KeyMetrics
    recommendation: str
    reversibility: str  # "reversible" | "hard_to_reverse"


class SupervisorReview(BaseModel):
    requires_approval: bool
    reasons: list[str] = Field(default_factory=list)
    summary: SupervisorSummary
    queue_payload: dict[str, Any] | None = None


class HumanSupervisorAgent:
    """Produces structured HITL summaries. Escalation logic stays in evaluate_hitl."""

    AGY_NAME = "human_supervisor"
    # Actions that move money or commit a dispatch are hard to undo once executed.
    HARD_TO_REVERSE_ACTIONS = {"execute_payment", "settle", "dispatch"}

    def __init__(self) -> None:
        # ── Agent harness: load .agy spec + skill contracts ──────────────────
        self._agy = load_agy(self.AGY_NAME)
        self._skill_context = load_agent_skills("human_supervisor_agent")

    def review(
        self,
        *,
        action: str,
        margin_pct: float,
        total_rate: float,
        vendor_id: str | None = None,
        compliance_passed: bool = True,
        vendor_text_flagged: bool = False,
        shipment_id: str = "UNKNOWN",
        lane: str | None = None,
        action_type: str = "review",
    ) -> dict[str, Any]:
        decision = evaluate_hitl(
            margin_pct=margin_pct,
            load_value=total_rate,
            compliance_passed=compliance_passed,
            vendor_text_flagged=vendor_text_flagged,
        )

        reversibility = (
            "hard_to_reverse"
            if action_type in self.HARD_TO_REVERSE_ACTIONS
            else "reversible"
        )
        if decision.requires_approval:
            rationale = (
                f"{len(decision.reasons)} policy trigger(s) require human sign-off before "
                f"proceeding: {'; '.join(decision.reasons)}."
            )
            recommendation = (
                "ESCALATE — hold and route to a human supervisor for approval."
            )
        else:
            rationale = (
                "Margin, load value, and compliance checks are all within policy."
            )
            recommendation = (
                "AUTO-APPROVE — safe to proceed without human intervention."
            )

        summary = SupervisorSummary(
            action=action,
            rationale=rationale,
            key_metrics=KeyMetrics(
                margin_pct=margin_pct, total_rate=total_rate, vendor_id=vendor_id
            ),
            recommendation=recommendation,
            reversibility=reversibility,
        )
        review = SupervisorReview(
            requires_approval=decision.requires_approval,
            reasons=decision.reasons,
            summary=summary,
            queue_payload=decision.queue_payload
            or {"shipment_id": shipment_id, "lane": lane, "action": action},
        )
        return review.model_dump(mode="json")
