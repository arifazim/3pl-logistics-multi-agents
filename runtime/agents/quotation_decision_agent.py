"""Quotation Decision Agent — real ADK agent with MCP tools and .agy-loaded instruction."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from runtime.adapters.pl3_mcp_client import Pl3McpClient
from runtime.agy.loader import load_agy
from runtime.evaluation.trajectory_evaluator import evaluate_dual_quotation_trajectory
from runtime.hitl.gate import evaluate_hitl
from runtime.memory import history_store, session_memory
from runtime.schemas import QuotationResult
from runtime.security.vendor_text_sanitizer import sanitize_vendor_text as _sanitize
from runtime.skills.loader import load_skills
from runtime.tools.quotation_engine import QuotationEngine

try:
    from google.adk.agents import Agent as AdkAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    AdkAgent = None  # type: ignore
    InMemoryRunner = None  # type: ignore
    types = None  # type: ignore


@dataclass
class DecisionState:
    """Mutable state populated by ADK tool calls."""

    ranking: dict[str, Any] | None = None
    quote: dict[str, Any] | None = None
    compliance: dict[str, Any] | None = None
    sanitization: dict[str, Any] | None = None
    tool_trace: list[str] = field(default_factory=list)


@dataclass
class DecisionResult:
    payload: dict[str, Any]
    explanation: str
    agent_mode: str  # "adk" | "offline"


class QuotationDecisionAgent:
    """Single ADK agent: vendor selection, compliance, exceptions. Math stays in tools."""

    AGY_NAME = "quotation_decision"

    def __init__(self, mcp: Pl3McpClient | None = None):
        self.mcp = mcp or Pl3McpClient()
        self.quotation_engine = QuotationEngine(self.mcp)
        self._agy = load_agy(self.AGY_NAME)
        self._instruction = self._build_instruction()
        self._state = DecisionState()
        self._runner: Any = None
        self._adk_agent: Any = None
        if ADK_AVAILABLE:
            self._adk_agent = self._build_adk_agent()
            self._runner = InMemoryRunner(agent=self._adk_agent, app_name="zero_touch_3pl")

    def _build_instruction(self) -> str:
        skills = self._agy.get("skills") or []
        skill_text = load_skills(skills)
        return f"{self._agy['prompt']}\n\n# Loaded Skills\n\n{skill_text}"

    def _build_adk_agent(self):
        return AdkAgent(
            name=self._agy.get("name", "quotation_decision_agent"),
            model=os.getenv("ADK_MODEL", "gemini-2.0-flash"),
            instruction=self._instruction,
            tools=[
                self.rank_vendors_for_lane,
                self.compute_margin_quote,
                self.check_compliance,
                self.sanitize_vendor_text,
            ],
        )

    # --- ADK tools (update DecisionState + call MCP/deterministic engine) ---

    def rank_vendors_for_lane(self, lane: str, weight_lbs: float = 1000.0) -> dict[str, Any]:
        """Rank carriers for lane via MCP vendor.rank_for_lane (70/30 reliability/cost)."""
        result = self.mcp.rank_vendors(lane, weight_lbs=weight_lbs)
        self._state.ranking = result
        self._state.tool_trace.append("rank_vendors_for_lane")
        return result

    def compute_margin_quote(
        self, lane: str, sla_tier: str = "standard", weight_lbs: float = 1000.0, vendor_id: str = ""
    ) -> dict[str, Any]:
        """Compute customer price from SELECTED vendor effective cost. Code computes margin."""
        vid = vendor_id or None
        quote = self.quotation_engine.calculate_customer_quote(
            lane, weight=weight_lbs, sla_tier=sla_tier, vendor_id=vid
        )
        self._state.quote = quote
        self._state.tool_trace.append("compute_margin_quote")
        return quote

    def check_compliance(
        self, margin_pct: float, delivery_time: float, weight_lbs: float = 1000.0, shipment_id: str = "UNKNOWN"
    ) -> dict[str, Any]:
        """Check margin (gte 12), SLA (lte 24h), weight (lte 45000) via MCP policy tools."""
        margin = self.mcp.check_policy("margin_protection", margin_pct, shipment_id)
        sla = self.mcp.check_policy("sla_compliance", delivery_time, shipment_id)
        weight = self.mcp.check_policy("weight_limit", weight_lbs, shipment_id)
        result = {
            "margin_compliance": margin,
            "sla_compliance": sla,
            "weight_compliance": weight,
            "passed": all(
                p.get("compliant", False) for p in (margin, sla, weight)
            ),
        }
        self._state.compliance = result
        self._state.tool_trace.append("check_compliance")
        return result

    def sanitize_vendor_text(self, text: str) -> dict[str, Any]:
        """Sanitize vendor-supplied text — prompt injection defense."""
        result = _sanitize(text)
        payload = {
            "text": result.text,
            "flagged": result.flagged,
            "reasons": result.reasons,
            "truncated": result.truncated,
        }
        self._state.sanitization = payload
        self._state.tool_trace.append("sanitize_vendor_text")
        return payload

    async def _run_adk(self, user_message: str) -> str:
        """Execute ADK InMemoryRunner — real Gemini LLM orchestrating tool calls."""
        if not self._runner or not types:
            raise RuntimeError("google-adk not installed")

        session = await self._runner.session_service.create_session(
            app_name="zero_touch_3pl",
            user_id="dispatcher",
            session_id=str(uuid.uuid4()),
        )
        content = types.Content(role="user", parts=[types.Part(text=user_message)])

        final_text = ""
        async for event in self._runner.run_async(
            user_id="dispatcher",
            session_id=session.id,
            new_message=content,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text or ""

        return final_text or "Agent completed tool orchestration."

    def _build_user_message(self, input_data: dict[str, Any]) -> str:
        return json.dumps(
            {
                "task": "dual_quotation_decision",
                "lane": input_data["lane"],
                "sla_tier": input_data.get("sla_tier", "standard"),
                "weight_lbs": input_data.get("weight", 1000),
                "shipment_id": input_data.get("shipment_id", "UNKNOWN"),
                "delivery_time_hours": input_data.get("delivery_time", 20),
                "vendor_text": input_data.get("vendor_text"),
                "instructions": (
                    "Call tools in order: sanitize if vendor_text, rank_vendors_for_lane, "
                    "compute_margin_quote, check_compliance. Explain decision for dispatcher."
                ),
            },
            indent=2,
        )

    async def decide(self, input_data: dict[str, Any]) -> DecisionResult:
        """ADK agent orchestrates tools; payload built from tool state."""
        self._state = DecisionState()
        lane = input_data["lane"]
        weight = float(input_data.get("weight", 1000))
        sla_tier = input_data.get("sla_tier", "standard")
        shipment_id = input_data.get("shipment_id", "UNKNOWN")
        delivery_time = float(input_data.get("delivery_time", 20))
        vendor_text = input_data.get("vendor_text")

        agent_mode = "offline"
        explanation = ""

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        allow_offline = os.getenv("ALLOW_OFFLINE_AGENT", "0") == "1"

        if ADK_AVAILABLE and api_key and self._runner:
            try:
                explanation = await self._run_adk(self._build_user_message(input_data))
                agent_mode = "adk"
            except Exception as exc:
                if not allow_offline:
                    raise RuntimeError(f"ADK agent failed (set ALLOW_OFFLINE_AGENT=1 for tests): {exc}") from exc
                explanation = f"ADK error, offline fallback: {exc}"
        elif not allow_offline:
            raise RuntimeError(
                "GEMINI_API_KEY required for ADK agent. Set ALLOW_OFFLINE_AGENT=1 only for unit tests."
            )
        else:
            explanation = "Offline tool orchestration (ALLOW_OFFLINE_AGENT=1)."

        # Ensure tool pipeline ran (ADK should have called tools; offline runs them explicitly)
        if "rank_vendors_for_lane" not in self._state.tool_trace:
            self.rank_vendors_for_lane(lane, weight_lbs=weight)
        if vendor_text and "sanitize_vendor_text" not in self._state.tool_trace:
            self.sanitize_vendor_text(vendor_text)
        if self._state.sanitization and self._state.sanitization.get("flagged"):
            hitl = evaluate_hitl(
                margin_pct=0,
                load_value=0,
                compliance_passed=False,
                vendor_text_flagged=True,
            )
            return DecisionResult(
                payload={
                    "workflow": "dual_quotation",
                    "agent": self._agy.get("name"),
                    "agent_mode": agent_mode,
                    "status": "blocked",
                    "vendor_text_sanitized": self._state.sanitization,
                    "hitl": {"requires_approval": True, "reasons": hitl.reasons},
                    "tool_trace": self._state.tool_trace,
                },
                explanation=explanation or "Vendor text flagged.",
                agent_mode=agent_mode,
            )

        if "compute_margin_quote" not in self._state.tool_trace:
            self.compute_margin_quote(lane, sla_tier, weight)
        if "check_compliance" not in self._state.tool_trace:
            quote = self._state.quote or {}
            self.check_compliance(
                quote.get("margin_percentage", 0), delivery_time, weight, shipment_id
            )

        quote = self._state.quote or {}
        ranking = self._state.ranking or {}
        compliance = self._state.compliance or {}
        selected = ranking.get("selected")

        hitl = evaluate_hitl(
            margin_pct=quote.get("margin_percentage", 0),
            load_value=quote.get("total_rate", 0),
            compliance_passed=compliance.get("passed", False),
            vendor_text_flagged=bool(self._state.sanitization and self._state.sanitization.get("flagged")),
        )

        vendor_quotes = self.quotation_engine.get_vendor_quotes(lane)

        payload: dict[str, Any] = {
            "workflow": "dual_quotation",
            "agent": self._agy.get("name"),
            "agent_mode": agent_mode,
            "agy_file": f"agy/agents/{self.AGY_NAME}.agy",
            "lane": lane,
            "vendor_quotes": vendor_quotes,
            "ranked_vendors": ranking.get("ranked", []),
            "recommended_vendor": selected,
            "customer_quote": quote,
            "compliance": compliance,
            "hitl": {
                "requires_approval": hitl.requires_approval,
                "reasons": hitl.reasons,
                "queue_payload": hitl.queue_payload,
            },
            "pricing_basis": "selected_vendor_cost",
            "tool_trace": self._state.tool_trace,
            "a2a": {"protocol": "vendor_negotiation", "vendor_count": len(vendor_quotes)},
        }

        if self._state.sanitization:
            payload["vendor_text_sanitized"] = self._state.sanitization

        trajectory = evaluate_dual_quotation_trajectory(payload)
        payload["trajectory_eval"] = {
            "passed": trajectory.passed,
            "steps": [{"name": s.name, "passed": s.passed, "detail": s.detail} for s in trajectory.steps],
            "violations": trajectory.violations,
        }

        self.mcp.log_event("dual_quotation", self._agy.get("name", "agent"), {"lane": lane, "mode": agent_mode})

        if not explanation:
            explanation = self._fallback_explanation(quote, selected, compliance, hitl)

        # ── Structured output validation (Day 3) ────────────────────────────
        # Validate payload against Pydantic schema before returning.
        # This ensures the LLM pipeline never silently produces malformed output.
        try:
            QuotationResult.model_validate({**payload, "explanation": explanation})
        except Exception as schema_err:
            payload["schema_validation_error"] = str(schema_err)

        # ── Agentic Memory (Day 4) ───────────────────────────────────────────
        # Persist result to history store so future runs can reference past decisions.
        await history_store.save(shipment_id, payload)
        # Also stash in session memory for this request's session_id.
        await session_memory.set(shipment_id, "last_result", payload)

        return DecisionResult(payload=payload, explanation=explanation, agent_mode=agent_mode)

    def _fallback_explanation(self, quote, selected, compliance, hitl) -> str:
        vid = quote.get("selected_vendor_id", "?")
        return (
            f"Selected {vid} at ${quote.get('vendor_cost', 0):.2f} vendor cost → "
            f"${quote.get('total_rate', 0):.2f} customer price ({quote.get('margin_percentage')}% margin). "
            f"Compliance: {'pass' if compliance.get('passed') else 'fail'}. "
            f"HITL: {'yes' if hitl.requires_approval else 'no'}."
        )

    def get_adk_agent(self):
        return self._adk_agent

    def get_instruction(self) -> str:
        return self._instruction
