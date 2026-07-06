import os

import pytest

from runtime.agy.loader import load_agy
from runtime.agents.quotation_decision_agent import QuotationDecisionAgent
from runtime.skills.loader import load_skills


def test_agy_prompt_loaded():
    agy = load_agy("quotation_decision")
    assert "QUOTATION_DECISION_AGENT" in agy["prompt"]
    assert "vendor_quotation" in agy.get("skills", [])


def test_skills_loaded():
    text = load_skills(["vendor_quotation", "compliance_and_risk"])
    # Skills are loaded — check for content from the actual SKILL.md files
    assert "vendor_quotation" in text.lower()
    assert "compliance_and_risk" in text.lower() or "compliance" in text.lower()


@pytest.mark.asyncio
async def test_offline_decision_runs_tool_pipeline():
    os.environ["ALLOW_OFFLINE_AGENT"] = "1"
    agent = QuotationDecisionAgent()
    result = await agent.decide({"lane": "Tracy->Fremont", "weight": 1000, "delivery_time": 20})
    assert result.agent_mode == "offline"
    assert "rank_vendors_for_lane" in result.payload["tool_trace"]
    assert "compute_margin_quote" in result.payload["tool_trace"]
    assert result.payload["customer_quote"]["pricing_basis"] == "selected_vendor_cost"
    assert result.payload["customer_quote"]["margin_percentage"] >= 12.0
    # Margin is floor (12%), NOT tautological 15% from rate card target
    assert result.payload["customer_quote"]["target_margin_reference"] == 15
    assert result.payload["customer_quote"]["margin_percentage"] == pytest.approx(12.0, abs=0.1)


@pytest.mark.asyncio
async def test_sla_violation_fails_compliance():
    os.environ["ALLOW_OFFLINE_AGENT"] = "1"
    agent = QuotationDecisionAgent()
    result = await agent.decide({"lane": "Tracy->Fremont", "delivery_time": 26})
    assert result.payload["compliance"]["sla_compliance"]["compliant"] is False
    assert result.payload["compliance"]["passed"] is False
