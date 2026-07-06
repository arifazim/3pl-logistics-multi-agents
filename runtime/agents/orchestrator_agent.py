"""Orchestrator Agent — Day 2: Multi-Agent Systems.

This is a real LLM-powered routing agent that:
1. Receives a natural language or structured request
2. Decides which sub-agent / workflow to invoke (task decomposition)
3. Passes structured data between agents (A2A communication)
4. Returns a unified response

The orchestrator itself is an ADK Agent whose tools are the downstream workflows.
It does NOT do math — it routes and decomposes tasks, then delegates.

Without GEMINI_API_KEY: falls back to deterministic keyword routing (offline mode).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from runtime.agy.loader import load_agy
from runtime.memory import context_buffer, history_store
from runtime.skills.loader import load_agent_skills

try:
    from google.adk.agents import Agent as AdkAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types as genai_types

    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False


@dataclass
class OrchestratorDecision:
    workflow: str
    params: dict[str, Any]
    reasoning: str
    agent_mode: str  # "adk" | "offline"


class OrchestratorAgent:
    """
    LLM-routing orchestrator. Wraps an ADK agent whose tools are workflow dispatchers.

    Day 2 demonstration:
    - Agent orchestration: OrchestratorAgent → QuotationDecisionAgent / A2ANegotiator
    - Task decomposition: natural language → structured workflow call
    - Structured agent communication: every inter-agent message is a typed dict
    """

    AGY_NAME = "orchestrator"

    def __init__(self) -> None:
        self._runner: Any = None
        self._agent: Any = None
        # ── Agent harness: load .agy spec + skill contracts ──────────────────
        self._agy = load_agy(self.AGY_NAME)
        skill_text = load_agent_skills("orchestrator_agent")
        self._instruction = f"{self._agy['prompt']}\n\n# Loaded Skills\n\n{skill_text}"
        if ADK_AVAILABLE:
            self._agent = AdkAgent(
                name=self._agy.get("name", "orchestrator_agent"),
                model=os.getenv("ADK_MODEL", "gemini-2.0-flash"),
                instruction=self._instruction,
                tools=[
                    self._tool_use_workflow,
                    self._tool_recall_history,
                    self._tool_get_memory_stats,
                ],
            )
            self._runner = InMemoryRunner(
                agent=self._agent, app_name="zero_touch_3pl_orchestrator"
            )

    # ── ADK tool stubs (the orchestrator calls these; actual work in AgentSystem) ──

    def _tool_use_workflow(self, workflow: str, params_json: str = "{}") -> str:
        """Route to a workflow. Returns the workflow name + params for the caller to execute."""
        try:
            params = json.loads(params_json) if params_json else {}
        except json.JSONDecodeError:
            params = {}
        return json.dumps({"_route": workflow, "_params": params})

    def _tool_recall_history(self, shipment_id: str) -> str:
        """Recall a past quotation result from memory by shipment_id."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            record = loop.run_until_complete(history_store.get(shipment_id))
        except RuntimeError:
            record = None
        if not record:
            return json.dumps(
                {"error": f"No memory found for shipment_id={shipment_id}"}
            )
        q = record.get("customer_quote") or {}
        v = record.get("recommended_vendor") or {}
        return json.dumps(
            {
                "shipment_id": shipment_id,
                "lane": record.get("lane"),
                "vendor": v.get("vendor_id"),
                "total_rate": q.get("total_rate"),
                "margin_pct": q.get("margin_percentage"),
                "hitl": (record.get("hitl") or {}).get("requires_approval"),
                "saved_at": record.get("_memory_saved_at"),
            }
        )

    def _tool_get_memory_stats(self) -> str:
        """Return aggregate stats from the shipment history memory store."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            stats = loop.run_until_complete(history_store.stats())
        except RuntimeError:
            stats = {"count": 0}
        return json.dumps(stats)

    # ── Public interface ──────────────────────────────────────────────────────

    async def route(
        self, message: str, context: dict[str, Any] | None = None
    ) -> OrchestratorDecision:
        """
        Parse a natural language or JSON message and return a routing decision.
        """
        ctx = context or {}

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        allow_off = os.getenv("ALLOW_OFFLINE_AGENT", "0") == "1"

        if ADK_AVAILABLE and api_key and self._runner:
            return await self._route_via_adk(message, ctx)
        elif allow_off:
            return self._route_offline(message, ctx)
        else:
            raise RuntimeError(
                "GEMINI_API_KEY required. Set ALLOW_OFFLINE_AGENT=1 for offline routing."
            )

    async def _route_via_adk(
        self, message: str, ctx: dict[str, Any]
    ) -> OrchestratorDecision:
        """Use Gemini to decide routing."""
        import uuid

        memory_ctx = await context_buffer.build_context_string()
        full_msg = f"{memory_ctx}\n\nUser request: {message}" if memory_ctx else message

        session = await self._runner.session_service.create_session(
            app_name="zero_touch_3pl_orchestrator",
            user_id="dispatcher",
            session_id=str(uuid.uuid4()),
        )
        content = genai_types.Content(
            role="user", parts=[genai_types.Part(text=full_msg)]
        )

        last_text = ""
        async for event in self._runner.run_async(
            user_id="dispatcher", session_id=session.id, new_message=content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                last_text = event.content.parts[0].text or ""

        return self._parse_adk_response(last_text, message)

    def _parse_adk_response(self, text: str, original_msg: str) -> OrchestratorDecision:
        """Try to extract JSON routing decision from LLM response."""
        # Try to find a JSON block
        match = re.search(r'\{[^{}]*"workflow"[^{}]*\}', text, re.S)
        if match:
            try:
                d = json.loads(match.group())
                return OrchestratorDecision(
                    workflow=d.get("workflow", "dual_quotation"),
                    params=d.get("params", {}),
                    reasoning=d.get("reasoning", text[:200]),
                    agent_mode="adk",
                )
            except json.JSONDecodeError:
                pass
        # Fallback: keyword-based from original message
        decision = self._route_offline(original_msg, {})
        decision.agent_mode = "adk"
        decision.reasoning = text[:200] or decision.reasoning
        return decision

    def _route_offline(self, message: str, ctx: dict[str, Any]) -> OrchestratorDecision:
        """
        Deterministic keyword routing — no LLM needed.
        Demonstrates task decomposition without model dependency.
        """
        msg_lower = message.lower()
        params = self._extract_params(message, ctx)

        # Memory recall
        sid_match = re.search(r"\b(EVAL|MANUAL|A2A|LOOP)-\d+\b", message)
        if sid_match and any(
            w in msg_lower for w in ("recall", "history", "last time", "previous")
        ):
            return OrchestratorDecision(
                workflow="recall_history",
                params={"shipment_id": sid_match.group()},
                reasoning=f"Detected memory recall request for {sid_match.group()}",
                agent_mode="offline",
            )

        # Negotiation
        if any(w in msg_lower for w in ("negotiate", "counter", "a2a", "vendor offer")):
            return OrchestratorDecision(
                workflow="a2a_negotiation",
                params=params,
                reasoning="Detected A2A negotiation keywords",
                agent_mode="offline",
            )

        # Vendor-only
        if any(
            w in msg_lower
            for w in ("rank vendor", "carrier", "who can haul", "available vendor")
        ):
            return OrchestratorDecision(
                workflow="vendor_quotation",
                params=params,
                reasoning="Detected vendor ranking request",
                agent_mode="offline",
            )

        # Compliance only
        if any(
            w in msg_lower for w in ("complian", "policy", "sla check", "margin check")
        ):
            return OrchestratorDecision(
                workflow="compliance_check",
                params=params,
                reasoning="Detected compliance-only request",
                agent_mode="offline",
            )

        # Stats / memory
        if any(
            w in msg_lower for w in ("stats", "history", "how many", "average margin")
        ):
            return OrchestratorDecision(
                workflow="memory_stats",
                params={},
                reasoning="Detected memory stats request",
                agent_mode="offline",
            )

        # Default: full dual quotation
        return OrchestratorDecision(
            workflow="dual_quotation",
            params=params,
            reasoning="Default routing: full dual-quotation pipeline",
            agent_mode="offline",
        )

    def _extract_params(self, message: str, ctx: dict[str, Any]) -> dict[str, Any]:
        """Extract structured params from natural language message."""
        params = {
            "lane": ctx.get("lane", "Tracy->Fremont"),
            "weight": ctx.get("weight", 1000),
            "sla_tier": ctx.get("sla_tier", "standard"),
            "delivery_time": ctx.get("delivery_time", 20),
            "shipment_id": ctx.get("shipment_id", "NL-001"),
        }

        # Lane patterns: "Tracy to Fremont", "Tracy->Fremont"
        lane_m = re.search(r"(\w+)\s*(?:to|->)\s*(\w+)", message, re.I)
        if lane_m:
            params["lane"] = (
                f"{lane_m.group(1).capitalize()}->{lane_m.group(2).capitalize()}"
            )

        # Weight: "5000 lbs", "2000lb"
        weight_m = re.search(r"(\d[\d,]*)\s*(?:lbs?|pounds?|kg)", message, re.I)
        if weight_m:
            params["weight"] = float(weight_m.group(1).replace(",", ""))

        # SLA
        if "express" in message.lower():
            params["sla_tier"] = "express"
        elif "standard" in message.lower():
            params["sla_tier"] = "standard"

        # Delivery hours
        deliv_m = re.search(r"(\d+)\s*(?:hour|hr)", message, re.I)
        if deliv_m:
            params["delivery_time"] = float(deliv_m.group(1))

        # Shipment ID
        sid_m = re.search(r"\b(EVAL|MANUAL|LOOP|NL)-\d+\b", message)
        if sid_m:
            params["shipment_id"] = sid_m.group()

        return params
