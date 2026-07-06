import pytest
from runtime.agent_system import AgentSystem

@pytest.mark.asyncio
async def test_customer_quote_end_to_end():
    agent_system = AgentSystem()
    input_data = {
        "lane": "Tracy->Fremont",
        "weight": 1000,
        "sla_tier": "standard"
    }
    result = await agent_system.execute_agent_workflow("customer_quotation", input_data)
    assert result["workflow"] == "customer_quotation"
    assert result["quote"]["margin_percentage"] >= 12.0
    assert result["quote"]["total_rate"] > 0
