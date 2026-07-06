"""CommerceAgent AP2 settle-flow tests (MockProcessor, no network)."""

import pytest

from runtime.agents.commerce_agent import CommerceAgent
from runtime.commerce.mandates import MandateStatus
from runtime.hitl.gate import HitlDecision


@pytest.mark.asyncio
async def test_settle_happy_path_charges_and_vendor_acknowledges():
    agent = CommerceAgent()
    result = await agent.settle(
        lane="Tracy->Fremont", weight_lbs=1000, sla_tier="standard",
        shipment_id="SHP-HAPPY", persist=False,
    )
    assert result["status"] == "settled"
    assert result["payment_mode"] == "mock"

    # Mandate chain is present and chained.
    assert result["cart_mandate"]["intent_mandate_id"] == result["intent_mandate"]["mandate_id"]
    assert result["cart_mandate"]["status"] == MandateStatus.executed.value

    # The vendor received the payment.
    receipt = result["receipt"]
    assert receipt["processor"] == "mock"
    assert receipt["amount"] == result["cart_mandate"]["agreed_rate"]
    assert result["vendor_acknowledgement"]["acknowledged"] is True
    assert result["vendor_acknowledgement"]["receipt_id"] == receipt["receipt_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,expected", [("card", "card"), ("ach", "ach")])
async def test_settle_funding_method_toggle(method, expected):
    result = await CommerceAgent().settle(
        lane="Tracy->Fremont", shipment_id=f"SHP-{method}", human_approved=True,
        payment_method=method, persist=False,
    )
    assert result["status"] == "settled"
    assert result["payment_method"] == method
    assert result["receipt"]["funding_type"] == expected


@pytest.mark.asyncio
async def test_settle_response_carries_negotiation_and_quote():
    result = await CommerceAgent().settle(
        lane="Tracy->Fremont", shipment_id="SHP-RICH", human_approved=True, persist=False
    )
    # The UI needs the negotiation rounds (live A2A) and the quote block.
    assert result["negotiation"]["rounds"]
    assert result["quote"]["selected_vendor_id"] == result["cart_mandate"]["vendor_id"]
    assert result["quote"]["customer_price"] > result["quote"]["agreed_rate"]


@pytest.mark.asyncio
async def test_settle_rejects_when_cap_below_negotiated_rate():
    agent = CommerceAgent()
    result = await agent.settle(
        lane="Tracy->Fremont", weight_lbs=1000, shipment_id="SHP-CAP",
        max_amount=1.0, persist=False,  # absurdly low spend cap
    )
    assert result["status"] == "rejected_cap_exceeded"
    assert "receipt" not in result  # no payment executed


@pytest.mark.asyncio
async def test_settle_requires_approval_blocks_charge(monkeypatch):
    # Force HITL to require approval regardless of the numbers.
    monkeypatch.setattr(
        "runtime.agents.commerce_agent.evaluate_hitl",
        lambda **kw: HitlDecision(requires_approval=True, reasons=["forced"], queue_payload={}),
    )
    agent = CommerceAgent()
    result = await agent.settle(
        lane="Tracy->Fremont", shipment_id="SHP-PEND", human_approved=False, persist=False
    )
    assert result["status"] == "pending_approval"
    assert result["requires_hitl"] is True
    assert result["cart_mandate"]["status"] == MandateStatus.pending_approval.value
    assert "receipt" not in result  # nothing charged without approval


@pytest.mark.asyncio
async def test_settle_with_human_approval_charges(monkeypatch):
    monkeypatch.setattr(
        "runtime.agents.commerce_agent.evaluate_hitl",
        lambda **kw: HitlDecision(requires_approval=True, reasons=["forced"], queue_payload={}),
    )
    agent = CommerceAgent()
    result = await agent.settle(
        lane="Tracy->Fremont", shipment_id="SHP-APPR",
        human_approved=True, approver="ops_manager", persist=False,
    )
    assert result["status"] == "settled"
    assert result["cart_mandate"]["approved_by"] == "ops_manager"
    assert result["receipt"]["processor"] == "mock"
