"""Trajectory evaluator — asserts dual-quotation flow against Gherkin-derived rules.

This replaces a generic EVALUATION_AGENT stub with testable assertions on the
one workflow we actually build.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

MARGIN_FLOOR_PCT = 12.0


@dataclass
class TrajectoryStep:
    name: str
    passed: bool
    detail: str


@dataclass
class TrajectoryResult:
    passed: bool
    steps: List[TrajectoryStep] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)


def evaluate_dual_quotation_trajectory(result: Dict[str, Any]) -> TrajectoryResult:
    """Assert end-to-end dual_quotation workflow output."""
    steps: List[TrajectoryStep] = []
    violations: List[str] = []

    # Step 1: Vendor quotes gathered
    vendor_quotes = result.get("vendor_quotes") or []
    v_ok = len(vendor_quotes) > 0
    steps.append(TrajectoryStep("vendor_quotes_gathered", v_ok, f"{len(vendor_quotes)} quotes"))
    if not v_ok:
        violations.append("No vendor quotes returned")

    # Step 2: Recommended vendor selected (reliability-weighted)
    rec = result.get("recommended_vendor")
    r_ok = rec is not None and rec.get("final_score", 0) > 0
    steps.append(TrajectoryStep("vendor_selected", r_ok, str(rec.get("vendor_id") if rec else None)))
    if not r_ok:
        violations.append("No recommended vendor")

    # Step 3: Customer quote from deterministic engine
    quote = result.get("customer_quote") or {}
    q_ok = quote.get("total_rate", 0) > 0
    steps.append(TrajectoryStep("customer_quote_computed", q_ok, f"total={quote.get('total_rate')}"))
    if not q_ok:
        violations.append("Customer quote missing or zero")

    # Step 4: Margin from SELECTED vendor cost (the pitch)
    selected_id = quote.get("selected_vendor_id")
    rec_id = rec.get("vendor_id") if rec else None
    basis_ok = (
        quote.get("pricing_basis") == "selected_vendor_cost"
        and selected_id == rec_id
        and quote.get("vendor_cost", 0) > 0
    )
    steps.append(
        TrajectoryStep(
            "margin_from_selected_vendor",
            basis_ok,
            f"vendor={selected_id} cost={quote.get('vendor_cost')}",
        ),
    )
    if not basis_ok:
        violations.append("Customer quote not based on selected vendor cost")

    # Step 5: Margin protection (Gherkin: margin >= 12%)
    margin_pct = quote.get("margin_percentage", 0)
    m_ok = margin_pct >= MARGIN_FLOOR_PCT
    steps.append(
        TrajectoryStep("margin_protection", m_ok, f"margin={margin_pct}% floor={MARGIN_FLOOR_PCT}%"),
    )
    if not m_ok:
        violations.append(f"Margin {margin_pct}% below floor {MARGIN_FLOOR_PCT}%")

    # Step 6: Compliance checked via policy server
    compliance = result.get("compliance") or {}
    c_ok = "margin_compliance" in compliance or "passed" in compliance
    steps.append(TrajectoryStep("compliance_checked", c_ok, str(compliance.get("passed"))))
    if not c_ok:
        violations.append("Compliance results missing")

    # Step 7: HITL gate evaluated (not an agent)
    hitl = result.get("hitl") or {}
    h_ok = "requires_approval" in hitl
    steps.append(TrajectoryStep("hitl_gate_evaluated", h_ok, str(hitl.get("reasons", []))))
    if not h_ok:
        violations.append("HITL gate not evaluated")

    # Step 8: Vendor text sanitized when present
    if result.get("vendor_text_raw") is not None:
        san = result.get("vendor_text_sanitized") or {}
        s_ok = "flagged" in san
        steps.append(TrajectoryStep("vendor_text_sanitized", s_ok, str(san.get("reasons", []))))
        if not s_ok:
            violations.append("Vendor text sanitization missing")

    passed = all(s.passed for s in steps) and len(violations) == 0
    return TrajectoryResult(passed=passed, steps=steps, violations=violations)
