"""A2UIConciergeAgent summarizes an AP2/commerce settlement in its narrative."""

import pytest

from runtime.agents.a2ui_concierge_agent import A2UIConciergeAgent, Audience


@pytest.mark.asyncio
async def test_narrative_includes_commerce_settlement():
    agent = A2UIConciergeAgent()
    outputs = {
        "commerce": {
            "vendor_name": "FalconFreight", "agreed_rate": 320.0,
            "margin_percentage": 14.4, "funding_type": "ach",
            "processor": "stripe", "payment_status": "processing",
        }
    }
    narrative = await agent.generate_narrative(Audience.EXECUTIVE, outputs, context="AP2 demo")
    body = narrative.narrative.lower()
    assert "falconfreight" in body
    assert "320" in narrative.narrative
    takeaways = " ".join(narrative.key_takeaways)
    assert "FalconFreight" in takeaways
    assert "ach" in takeaways.lower()
