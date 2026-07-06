"""Tests for Day 3 — Structured Output: Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from runtime.schemas import (
    AgentMode,
    A2ANegotiationResult,
    A2AOfferSchema,
    ComplianceResult,
    CustomerQuote,
    HITLDecisionSchema,
    PolicyCheckResult,
    QuotationResult,
    SLATier,
    TrajectoryEvalSchema,
    TrajectoryStepSchema,
)


# ── CustomerQuote ──────────────────────────────────────────────────────────────

def test_customer_quote_valid():
    q = CustomerQuote(
        lane="Tracy->Fremont",
        weight=1000,
        sla_tier=SLATier.standard,
        selected_vendor_id="V002",
        vendor_cost=320.0,
        customer_price=363.64,
        total_rate=363.64,
        margin=43.64,
        margin_percentage=12.0,
        pricing_basis="selected_vendor_cost",
    )
    assert q.margin_percentage == 12.0
    assert q.pricing_basis == "selected_vendor_cost"


def test_customer_quote_rejects_wrong_pricing_basis():
    with pytest.raises(ValidationError, match="pricing_basis"):
        CustomerQuote(
            lane="Tracy->Fremont", weight=1000, sla_tier=SLATier.standard,
            selected_vendor_id="V002", vendor_cost=320.0,
            customer_price=363.64, total_rate=363.64,
            margin=43.64, margin_percentage=12.0,
            pricing_basis="rate_card",   # ← wrong — should be rejected
        )


def test_customer_quote_rejects_negative_margin():
    with pytest.raises(ValidationError, match="greater_than_equal"):
        CustomerQuote(
            lane="Tracy->Fremont", weight=1000, sla_tier=SLATier.standard,
            selected_vendor_id="V002", vendor_cost=400.0,
            customer_price=300.0, total_rate=300.0,
            margin=-100.0, margin_percentage=-33.3,
        )


# ── HITLDecisionSchema ─────────────────────────────────────────────────────────

def test_hitl_no_approval():
    h = HITLDecisionSchema(requires_approval=False, reasons=[])
    assert not h.requires_approval


def test_hitl_with_reasons():
    h = HITLDecisionSchema(
        requires_approval=True,
        reasons=["Low margin protection violation: 10.0% < 12%"],
    )
    assert h.requires_approval
    assert len(h.reasons) == 1


# ── TrajectoryEvalSchema ───────────────────────────────────────────────────────

def test_trajectory_requires_steps():
    with pytest.raises(ValidationError, match="step"):
        TrajectoryEvalSchema(passed=True, steps=[], violations=[])


def test_trajectory_valid():
    t = TrajectoryEvalSchema(
        passed=True,
        steps=[TrajectoryStepSchema(name="vendor_selected", passed=True, detail="V002")],
        violations=[],
    )
    assert t.passed


# ── ComplianceResult ───────────────────────────────────────────────────────────

def test_compliance_passed_requires_all_checks():
    policy = PolicyCheckResult(
        policy_name="margin_protection", op="gte", compliant=True, threshold=12.0, value=14.0, rule="margin >= 12%"
    )
    with pytest.raises(ValidationError, match="checks missing"):
        ComplianceResult(
            passed=True,
            margin_compliance=policy,
            # sla_compliance and weight_compliance missing
        )


def test_compliance_failed_allows_missing_checks():
    c = ComplianceResult(passed=False)
    assert not c.passed


# ── QuotationResult (top-level) ────────────────────────────────────────────────

def test_quotation_result_minimal_valid():
    r = QuotationResult(
        workflow="dual_quotation",
        agent="test_agent",
        agent_mode=AgentMode.offline,
        lane="Tracy->Fremont",
        hitl=HITLDecisionSchema(requires_approval=False),
    )
    assert r.workflow == "dual_quotation"
    assert r.agent_mode == AgentMode.offline


def test_quotation_result_rejects_unknown_workflow():
    with pytest.raises(ValidationError, match="Unknown workflow"):
        QuotationResult(
            workflow="make_money",   # ← not a known workflow
            agent_mode=AgentMode.offline,
            lane="Tracy->Fremont",
            hitl=HITLDecisionSchema(requires_approval=False),
        )


def test_quotation_result_extra_fields_tolerated():
    """Extra fields from MCP or future versions should not break validation."""
    r = QuotationResult.model_validate({
        "workflow": "dual_quotation",
        "agent_mode": "offline",
        "lane": "Tracy->Fremont",
        "hitl": {"requires_approval": False},
        "some_future_field": "ignored_gracefully",
    })
    assert r is not None


# ── A2A schemas ────────────────────────────────────────────────────────────────

def test_a2a_offer_valid():
    offer = A2AOfferSchema(
        vendor_id="V002", vendor_name="FalconFreight",
        offered_rate=320.0, accepted=True, counter_offer=None,
        round_num=1, reason="Accepted", reliability_score=95.0,
        timestamp="2026-06-28T00:00:00Z",
    )
    assert offer.accepted


def test_a2a_result_valid():
    result = A2ANegotiationResult(
        shipment_id="SHP-001", lane="Tracy->Fremont",
        agreed=True, agreed_vendor_id="V002", agreed_rate=320.0,
        summary="Agreed: V002 at $320.00",
        mcp_reference_cost=320.0,
    )
    assert result.agreed


# ── Schema from real agent output ─────────────────────────────────────────────

def test_schema_validates_real_like_payload():
    """Simulate what QuotationDecisionAgent.decide() actually returns."""
    payload = {
        "workflow": "dual_quotation",
        "agent": "quotation_decision_agent",
        "agent_mode": "offline",
        "lane": "Tracy->Fremont",
        "vendor_quotes": [{"vendor_id": "V001", "rate": 300.0}],
        "ranked_vendors": [],
        "recommended_vendor": {"vendor_id": "V002", "final_score": 83.5},
        "customer_quote": {
            "lane": "Tracy->Fremont",
            "weight": 1000,
            "sla_tier": "standard",
            "selected_vendor_id": "V002",
            "vendor_cost": 320.0,
            "customer_price": 363.64,
            "total_rate": 363.64,
            "margin": 43.64,
            "margin_percentage": 12.0,
            "pricing_basis": "selected_vendor_cost",
        },
        "compliance": {
            "passed": True,
            "margin_compliance": {"policy_name": "margin_protection", "op": "gte", "compliant": True, "threshold": 12.0, "value": 14.0, "rule": "margin >= 12%"},
            "sla_compliance": {"policy_name": "sla_compliance", "op": "lte", "compliant": True, "threshold": 24.0, "value": 20.0, "rule": "delivery_time <= 24h"},
            "weight_compliance": {"policy_name": "weight_limit", "op": "lte", "compliant": True, "threshold": 45000, "value": 1000, "rule": "weight <= 45000 lbs"},
        },
        "hitl": {"requires_approval": False, "reasons": []},
        "trajectory_eval": {
            "passed": True,
            "steps": [{"name": "vendor_selected", "passed": True, "detail": "V002"}],
            "violations": [],
        },
        "pricing_basis": "selected_vendor_cost",
        "tool_trace": ["rank_vendors_for_lane", "compute_margin_quote", "check_compliance"],
    }
    r = QuotationResult.model_validate(payload)
    assert r.workflow == "dual_quotation"
    assert r.customer_quote is not None
    assert r.customer_quote.margin_percentage == 12.0
    assert r.compliance is not None
    assert r.compliance.passed
    assert r.trajectory_eval is not None
    assert r.trajectory_eval.passed
