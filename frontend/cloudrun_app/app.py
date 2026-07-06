from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Enable offline mode for demo without API key
os.environ["ALLOW_OFFLINE_AGENT"] = "1"

# Load .env (Stripe/Plaid sandbox keys) BEFORE the agent system resolves the payment stack.
from runtime.env import load_dotenv
load_dotenv()

print(f"Project root: {project_root}")
print(f"Python path: {sys.path[:3]}")
print(f"Offline mode: ALLOW_OFFLINE_AGENT=1")

from runtime.agent_system import AgentSystem
from runtime.adapters.pl3_mcp_client import Pl3McpClient
from runtime.agents.orchestrator_agent import OrchestratorAgent
from runtime.loops.loop1_vendor_evaluator import VendorEvaluatorLoop
from runtime.loops.loop2_compliance_replan import ComplianceReplanLoop
from runtime.loops.loop3_kaizen import KaizenMetaLoop
from runtime.memory import history_store, session_memory
from mcp_servers.pl3_server.data import EVAL_SHIPMENTS
from runtime.agents.operations_insight_agent import OperationsInsightAgent
from runtime.agents.load_planning_agent import LoadPlanningAgent
from runtime.agents.a2ui_concierge_agent import A2UIConciergeAgent
from runtime.agents.security_sentinel_agent import SecuritySentinelAgent

# Mount static files for CSS/JS
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
app = FastAPI(title="3PL Quotation Intelligence System", version="4.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize agent system
agent_system     = AgentSystem()
mcp_client       = Pl3McpClient()
orchestrator     = OrchestratorAgent()
loop1            = VendorEvaluatorLoop()
loop2            = ComplianceReplanLoop()
loop3            = KaizenMetaLoop()


@app.get("/health")
async def health():
    return {"status": "ok", "agent": agent_system.agent_metadata()}


@app.get("/api/telemetry")
async def get_telemetry():
    """Retrieve operational KPIs via MCP telemetry.get_snapshot."""
    try:
        return JSONResponse(mcp_client.call("telemetry.get_snapshot"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/eval-samples")
async def get_eval_samples():
    """Return deterministic local eval cases for dashboard playback."""
    return JSONResponse({"count": len(EVAL_SHIPMENTS), "samples": EVAL_SHIPMENTS})

@app.post("/api/eval-run")
async def run_eval_batch(request: Request):
    """Run a bounded sample batch through the dual-quotation workflow."""
    try:
        data = await request.json()
        limit = min(max(int(data.get("limit", 10)), 1), len(EVAL_SHIPMENTS))
        samples = EVAL_SHIPMENTS[:limit]
        results = []

        for sample in samples:
            result = await agent_system.execute_agent_workflow("dual_quotation", sample)
            results.append(
                {
                    "shipment_id": sample["shipment_id"],
                    "lane": sample["lane"],
                    "sla_tier": sample["sla_tier"],
                    "weight": sample["weight"],
                    "selected_vendor": (result.get("recommended_vendor") or {}).get("vendor_id"),
                    "total_rate": (result.get("customer_quote") or {}).get("total_rate"),
                    "margin_percentage": (result.get("customer_quote") or {}).get("margin_percentage"),
                    "compliance_passed": (result.get("compliance") or {}).get("passed", False),
                    "trajectory_passed": (result.get("trajectory_eval") or {}).get("passed", False),
                    "hitl_required": (result.get("hitl") or {}).get("requires_approval", False),
                }
            )

        passed = sum(1 for item in results if item["trajectory_passed"])
        return JSONResponse(
            {
                "count": len(results),
                "passed": passed,
                "pass_rate": round((passed / len(results)) * 100, 1) if results else 0,
                "results": results,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/architecture", response_class=HTMLResponse)
async def architecture():
    """Full system architecture diagram."""
    try:
        return HTMLResponse((TEMPLATES_DIR / "architecture.html").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HTMLResponse("<h1>Architecture template not found</h1>", status_code=404)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard view."""
    try:
        return HTMLResponse((TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HTMLResponse("<h1>Dashboard template not found</h1>", status_code=404)

@app.post("/api/dual-quote")
async def generate_dual_quote(request: Request):
    """Dual-quotation vertical slice - vendor select, margin, compliance, HITL."""
    try:
        data = await request.json()
        print(f"[DEBUG] dual-quote input: {data}")
        result = await agent_system.execute_agent_workflow("dual_quotation", data)
        print(f"[DEBUG] dual-quote result: {result}")
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] dual-quote failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/quote")
async def generate_customer_quote(request: Request):
    """Generate customer quotation"""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("customer_quotation", data)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/vendor-quote")
async def request_vendor_quote(request: Request):
    """Request vendor quotations"""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("vendor_quotation", data)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/load-plan")
async def generate_load_plan(request: Request):
    """Generate optimized load plan"""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("load_planning", data)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/compliance-check")
async def check_compliance(request: Request):
    """Check compliance for a shipment"""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("compliance_check", data)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/a2a-negotiate")
async def a2a_negotiate(request: Request):
    """A2A vendor negotiation — broker ↔ vendor-side agents, multi-round counter-offer protocol."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("a2a_negotiation", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] a2a-negotiate failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ap2-payment")
async def ap2_payment(request: Request):
    """AP2 payment — Intent/Cart mandates, negotiation, approval, sandbox payment the vendor receives.

    Body: {lane, weight?, sla_tier?, shipment_id?, max_amount?, human_approved?, approver?}.
    Defaults to the safe MockProcessor; real Stripe test-mode / Plaid sandbox only when
    ALLOW_LIVE_PAYMENTS=1 with test/sandbox keys. Live credentials are hard-blocked.
    """
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("ap2_payment", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] ap2-payment failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/human-review")
async def human_review(request: Request):
    """HITL structured summary — action, rationale, key metrics, recommendation, reversibility."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("human_review", data)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/operations-insight")
async def operations_insight(request: Request):
    """Operations insight — bottleneck detection, dwell prediction, flow analysis."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("operations_insight", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] operations-insight failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vendor-reliability")
async def vendor_reliability(request: Request):
    """Vendor reliability scoring from historical performance data."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("vendor_reliability", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] vendor-reliability failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pallet-readiness")
async def pallet_readiness(request: Request):
    """Pallet readiness check at warehouse."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("pallet_readiness", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] pallet-readiness failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-dashboard")
async def generate_dashboard(request: Request):
    """Generate dashboard view for specific audience."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("generate_dashboard", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] generate-dashboard failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-narrative")
async def generate_narrative(request: Request):
    """Generate narrative summary for specific audience."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("generate_narrative", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] generate-narrative failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/red-team-test")
async def red_team_test(request: Request):
    """Run red team adversarial security test."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("red_team_test", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] red-team-test failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/blue-team-hardening")
async def blue_team_hardening(request: Request):
    """Run blue team defense hardening."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("blue_team_hardening", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] blue-team-hardening failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/green-team-validation")
async def green_team_validation(request: Request):
    """Run green team continuous validation."""
    try:
        data = await request.json()
        result = await agent_system.execute_agent_workflow("green_team_validation", data)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] green-team-validation failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security-summary")
async def security_summary():
    """Get security summary."""
    try:
        result = await agent_system.execute_agent_workflow("security_summary", {})
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[ERROR] security-summary failed: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/loop/1")
async def run_loop1(request: Request):
    """Loop 1 — Vendor Evaluator: bounded vendor re-scoring with margin guardrails."""
    try:
        data = await request.json()
        result = loop1.execute(
            lane=data.get("lane", "Tracy->Fremont"),
            weight=float(data.get("weight", 1000)),
            sla_tier=data.get("sla_tier", "standard"),
        )
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/loop/2")
async def run_loop2(request: Request):
    """Loop 2 — Compliance-Critic: plan → compliance check → replan, max 3 iterations."""
    try:
        data = await request.json()
        result = loop2.execute(
            shipment_id=data.get("shipment_id", "LOOP2-TEST"),
            lane=data.get("lane", "Tracy->Fremont"),
            weight=float(data.get("weight", 1000)),
            margin=float(data.get("margin", 14.0)),
            delivery_time=float(data.get("delivery_time", 20)),
        )
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/loop/3")
async def run_loop3(request: Request):
    """Loop 3 — Kaizen Meta-Loop: auto-classify failures, refine config + Gherkin, re-eval."""
    try:
        data = await request.json()
        fresh_loop = KaizenMetaLoop()  # fresh instance per run
        result = fresh_loop.execute(spec_filter=data.get("spec_filter"))
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Day 2: Multi-Agent Orchestrator ──────────────────────────────────────────

@app.post("/api/orchestrate")
async def orchestrate(request: Request):
    """
    Natural language or structured request → OrchestratorAgent routes to the right workflow.
    Day 2 (Multi-Agent) + Bonus (Vibe Coding): natural language as first-class input.
    """
    try:
        data = await request.json()
        message = data.get("message", "")
        context = data.get("context", {})
        if not message:
            raise HTTPException(status_code=400, detail="'message' field required")

        decision = await orchestrator.route(message, context)

        # Execute the routed workflow
        if decision.workflow == "recall_history":
            sid    = decision.params.get("shipment_id", "")
            record = await history_store.get(sid)
            return JSONResponse({
                "routed_to": "recall_history",
                "shipment_id": sid,
                "record": record,
                "reasoning": decision.reasoning,
                "agent_mode": decision.agent_mode,
            })

        if decision.workflow == "memory_stats":
            stats = await history_store.stats()
            return JSONResponse({
                "routed_to": "memory_stats",
                "stats": stats,
                "reasoning": decision.reasoning,
                "agent_mode": decision.agent_mode,
            })

        result = await agent_system.execute_agent_workflow(decision.workflow, decision.params)
        return JSONResponse({
            "routed_to": decision.workflow,
            "params": decision.params,
            "reasoning": decision.reasoning,
            "agent_mode": decision.agent_mode,
            "result": result,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Day 4: Agentic Memory endpoints ──────────────────────────────────────────

@app.get("/api/memory/stats")
async def memory_stats():
    """Aggregate stats from the shipment history memory store."""
    try:
        return JSONResponse(await history_store.stats())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/{shipment_id}")
async def memory_recall(shipment_id: str):
    """Recall a past quotation result from memory."""
    record = await history_store.get(shipment_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No memory for {shipment_id}")
    return JSONResponse(record)


@app.get("/api/memory")
async def memory_recent():
    """Return the 20 most recent stored quotations."""
    try:
        items = await history_store.recent(20)
        return JSONResponse({"count": len(items), "records": items})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Bonus: Vibe Coding — natural language as first-class input ────────────────
# The /api/vibe endpoint is the canonical "vibe coding" demo:
# you describe what you want in plain English and the system figures out
# the right workflow, parameters, and agents to call.

VIBE_EXAMPLES = [
    "Quote a 5000 lb standard shipment from Tracy to Fremont",
    "Who are the best carriers for Manteca to Hayward express?",
    "Negotiate with vendors for a 2000 lb express load on Tracy->Fremont",
    "Check compliance for a 20-hour delivery with 14% margin",
    "What's the average margin across recent quotations?",
    "Recall the last quote for EVAL-001",
]

@app.post("/api/vibe")
async def vibe_query(request: Request):
    """
    Bonus: Vibe Coding — natural language as first-class code.

    Send any plain English description of what you need.
    The OrchestratorAgent parses intent, extracts parameters, routes to the
    correct workflow, and returns structured results.

    Examples:
      {"message": "Quote 5000 lbs Tracy to Fremont express"}
      {"message": "Negotiate with carriers for a standard load"}
      {"message": "What's the average margin in memory?"}
      {"message": "Recall EVAL-042"}
    """
    try:
        data = await request.json()
        message = data.get("message", "").strip()
        if not message:
            return JSONResponse({
                "error": "Provide a 'message' field with your natural language request.",
                "examples": VIBE_EXAMPLES,
            }, status_code=400)

        # Route via orchestrator (LLM if GEMINI_API_KEY set, keyword otherwise)
        decision = await orchestrator.route(message, data.get("context", {}))

        # Execute
        if decision.workflow == "recall_history":
            sid    = decision.params.get("shipment_id", "")
            record = await history_store.get(sid)
            return JSONResponse({
                "vibe_input": message,
                "understood_as": "recall past quotation",
                "routed_to": "recall_history",
                "reasoning": decision.reasoning,
                "agent_mode": decision.agent_mode,
                "result": record or {"error": f"No memory for {sid}"},
            })

        if decision.workflow == "memory_stats":
            stats = await history_store.stats()
            return JSONResponse({
                "vibe_input": message,
                "understood_as": "memory statistics",
                "routed_to": "memory_stats",
                "reasoning": decision.reasoning,
                "agent_mode": decision.agent_mode,
                "result": stats,
            })

        result = await agent_system.execute_agent_workflow(decision.workflow, decision.params)
        return JSONResponse({
            "vibe_input": message,
            "understood_as": decision.workflow.replace("_", " "),
            "routed_to": decision.workflow,
            "extracted_params": decision.params,
            "reasoning": decision.reasoning,
            "agent_mode": decision.agent_mode,
            "result": result,
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vibe/examples")
async def vibe_examples():
    """Return example natural language queries for the vibe endpoint."""
    return JSONResponse({"examples": VIBE_EXAMPLES})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
