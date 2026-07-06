import pytest
from runtime.agent_system import AgentSystem


@pytest.mark.asyncio
async def test_vendor_quote_end_to_end():
    agent_system = AgentSystem()
    result = await agent_system.execute_agent_workflow("vendor_quotation", {"lane": "Tracy->Fremont"})
    assert result["workflow"] == "vendor_quotation"
    assert len(result["ranked_vendors"]) > 0
    assert result["recommended_vendor"] is not None
    assert result["recommended_vendor"]["final_score"] > 0
    assert result["recommended_vendor"]["vendor_id"] == "V002"
