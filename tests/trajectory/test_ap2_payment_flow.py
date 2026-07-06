"""Trajectory test: AP2 payment flow through the AgentSystem workflow."""

import pytest

from runtime.agent_system import AgentSystem
from runtime.memory import history_store


@pytest.mark.asyncio
async def test_ap2_payment_end_to_end():
    system = AgentSystem()
    result = await system.execute_agent_workflow(
        "ap2_payment",
        {"lane": "Tracy->Fremont", "weight": 1000, "sla_tier": "standard",
         "shipment_id": "SHP-TRAJ-1", "persist": False},
    )

    assert result["workflow"] == "ap2_payment"
    assert result["status"] == "settled"

    # Full AP2 mandate chain: Intent -> Cart -> Receipt -> vendor acknowledgement.
    intent, cart = result["intent_mandate"], result["cart_mandate"]
    assert cart["agreed_rate"] <= intent["max_amount"]  # never over the spend cap
    assert cart["intent_mandate_id"] == intent["mandate_id"]
    assert result["receipt"]["amount"] == cart["agreed_rate"]
    assert result["vendor_acknowledgement"]["acknowledged"] is True


@pytest.mark.asyncio
async def test_ap2_payment_persists_audit_chain():
    system = AgentSystem()
    await system.execute_agent_workflow(
        "ap2_payment",
        {"lane": "Tracy->Fremont", "shipment_id": "SHP-TRAJ-AUDIT", "persist": True},
    )
    saved = await history_store.get("SHP-TRAJ-AUDIT")
    assert saved is not None
    ap2 = saved["ap2"]
    assert ap2["intent_mandate"]["shipment_id"] == "SHP-TRAJ-AUDIT"
    assert ap2["cart_mandate"]["content_hash"]
    assert ap2["receipt"]["processor"] == "mock"
