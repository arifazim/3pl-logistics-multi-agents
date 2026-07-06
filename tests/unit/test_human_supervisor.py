"""HumanSupervisorAgent structured-summary tests."""

import pytest

from runtime.agents.human_supervisor_agent import HumanSupervisorAgent


def _review(**over):
    base = dict(action="Dispatch load", margin_pct=14.0, total_rate=400.0, vendor_id="V002")
    base.update(over)
    return HumanSupervisorAgent().review(**base)


def test_clean_load_auto_approves():
    r = _review()
    assert r["requires_approval"] is False
    assert "AUTO-APPROVE" in r["summary"]["recommendation"]
    assert r["reasons"] == []


def test_low_margin_escalates():
    r = _review(margin_pct=9.0)
    assert r["requires_approval"] is True
    assert any("margin protection" in x for x in r["reasons"])
    assert "ESCALATE" in r["summary"]["recommendation"]


def test_high_value_escalates_even_when_clean():
    r = _review(margin_pct=20.0, total_rate=15000.0)
    assert r["requires_approval"] is True
    assert any("High-value load" in x for x in r["reasons"])


def test_structured_summary_shape():
    r = _review()
    summary = r["summary"]
    assert set(summary) == {"action", "rationale", "key_metrics", "recommendation", "reversibility"}
    assert set(summary["key_metrics"]) == {"margin_pct", "total_rate", "vendor_id"}
    assert "queue_payload" in r


def test_payment_action_is_hard_to_reverse():
    assert _review(action_type="execute_payment")["summary"]["reversibility"] == "hard_to_reverse"
    assert _review(action_type="review")["summary"]["reversibility"] == "reversible"


@pytest.mark.asyncio
async def test_commerce_escalation_includes_supervisor_summary(monkeypatch):
    from runtime.agents.commerce_agent import CommerceAgent
    from runtime.hitl.gate import HitlDecision

    monkeypatch.setattr(
        "runtime.agents.commerce_agent.evaluate_hitl",
        lambda **kw: HitlDecision(requires_approval=True, reasons=["forced"], queue_payload={}),
    )
    result = await CommerceAgent().settle(
        lane="Tracy->Fremont", shipment_id="SHP-SUP", human_approved=False, persist=False
    )
    assert result["status"] == "pending_approval"
    assert "supervisor_summary" in result
    assert result["supervisor_summary"]["summary"]["reversibility"] == "hard_to_reverse"
