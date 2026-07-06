"""End-to-end delivery test — validates complete flow from quotation to final result."""

import pytest

from runtime.agent_system import AgentSystem


@pytest.fixture(autouse=True)
def offline_agent(monkeypatch):
    monkeypatch.setenv("ALLOW_OFFLINE_AGENT", "1")


@pytest.mark.asyncio
async def test_end_to_end_delivery_flow():
    """Full dual-quotation flow produces valid quotation with trajectory pass."""
    agent_system = AgentSystem()
    result = await agent_system.execute_agent_workflow(
        "dual_quotation",
        {
            "lane": "Tracy->Fremont",
            "weight": 2500,
            "sla_tier": "standard",
            "delivery_time": 20,
            "shipment_id": "E2E-001",
        },
    )

    assert result["workflow"] == "dual_quotation"
    assert result["customer_quote"]["total_rate"] > 0
    assert result["customer_quote"]["margin_percentage"] >= 12.0
    assert result["trajectory_eval"]["passed"] is True
    assert result["compliance"]["passed"] is True
    assert "tool_trace" in result