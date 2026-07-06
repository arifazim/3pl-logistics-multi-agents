"""Tests for Day 2 (Multi-Agent orchestration) + Bonus (Vibe Coding / NL routing)."""

import os
import pytest

os.environ.setdefault("ALLOW_OFFLINE_AGENT", "1")

from runtime.agents.orchestrator_agent import OrchestratorAgent


@pytest.fixture
def agent():
    return OrchestratorAgent()


# ── Offline keyword routing ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_default_routes_to_dual_quotation(agent):
    d = await agent.route("Quote a shipment from Tracy to Fremont")
    assert d.workflow == "dual_quotation"
    assert d.agent_mode == "offline"


@pytest.mark.asyncio
async def test_negotiation_keywords(agent):
    d = await agent.route("Negotiate with vendors for this load")
    assert d.workflow == "a2a_negotiation"


@pytest.mark.asyncio
async def test_carrier_ranking_keywords(agent):
    d = await agent.route("Which carriers can haul this?")
    assert d.workflow == "vendor_quotation"


@pytest.mark.asyncio
async def test_compliance_keywords(agent):
    d = await agent.route("Check compliance for this shipment")
    assert d.workflow == "compliance_check"


@pytest.mark.asyncio
async def test_memory_stats_keywords(agent):
    d = await agent.route("What's the average margin in history?")
    assert d.workflow == "memory_stats"


@pytest.mark.asyncio
async def test_recall_keywords(agent):
    d = await agent.route("Recall EVAL-042 from history")
    assert d.workflow == "recall_history"
    assert d.params.get("shipment_id") == "EVAL-042"


# ── Parameter extraction ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extracts_weight(agent):
    d = await agent.route("Quote 5000 lbs from Tracy to Fremont")
    assert d.params["weight"] == 5000.0


@pytest.mark.asyncio
async def test_extracts_express_sla(agent):
    d = await agent.route("I need an express shipment on Tracy->Fremont")
    assert d.params["sla_tier"] == "express"


@pytest.mark.asyncio
async def test_extracts_lane(agent):
    d = await agent.route("Move freight from Tracy to Fremont")
    assert "Tracy" in d.params["lane"]
    assert "Fremont" in d.params["lane"]


@pytest.mark.asyncio
async def test_extracts_delivery_hours(agent):
    d = await agent.route("Quote Tracy to Fremont within 18 hours")
    assert d.params["delivery_time"] == 18.0


# ── Reasoning is populated ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reasoning_present(agent):
    d = await agent.route("Give me a quote")
    assert d.reasoning
    assert len(d.reasoning) > 0


# ── Context override ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_overrides_defaults(agent):
    d = await agent.route("Quote this", context={"lane": "Manteca->Hayward", "weight": 8000})
    assert d.params["lane"] == "Manteca->Hayward"
    assert d.params["weight"] == 8000
