# Capstone Review — 3PL Multi-Agent Optimization System

## Development Toolchain

Built end-to-end using **OpenCode** (antigravity IDE) with **antigravity models**, **Google ADK**,
**Google Agent CLI**, and **Google Cloud**:

| Tool                             | Role                                                                                   |
| -------------------------------- | -------------------------------------------------------------------------------------- |
| **OpenCode** (antigravity IDE)   | Agentic coding, refactoring, test generation, doc writing throughout the build         |
| **Antigravity models**           | LLM backbone for all OpenCode development sessions                                     |
| **Google ADK**                   | Agent framework (`LlmAgent`, `InMemoryRunner`, tool registration) for all 8 agents     |
| **Google Agent CLI**             | Fleet scaffolding, evaluation runs, Cloud Run deployment                               |
| **Vertex AI — Gemini 2.0 Flash** | LLM for `QuotationDecisionAgent` and `OrchestratorAgent` (default model)               |
| **Google Cloud Run**             | Serverless deployment target (`deployment/cloudrun/`)                                  |
| **Google Secret Manager**        | `GEMINI_API_KEY` injection at runtime                                                  |
| **MCP** (stdio JSON-RPC)         | Tool protocol — all 5 namespaces (`rate_card`, `vendor`, `policy`, `telemetry`, `tms`) |

---

## Built Scope

This capstone implements a **production-grade multi-agent system** with real autonomous capabilities:

- **8 ADK/Gemini Agents**: full fleet (see `runtime/agents/` and `agy/agent_graph.yaml`)
- **1 Real MCP Server**: `mcp_servers/pl3_server` — stdio JSON-RPC protocol, 5 namespaces
- **Deterministic Tools**: `QuotationEngine`, `VendorScorer`, `OR-Tools CVRPTW`, `VendorTextSanitizer`
- **AP2 Payment Flow**: Intent Mandate → A2A negotiation → Cart Mandate → HITL → Stripe/Plaid
- **3 Autonomous Loops**: Vendor evaluator, compliance-critic, kaizen meta-loop
- **A2A Protocol**: Vendor negotiation via `SwiftTransport`, `FalconFreight`, `EcoHaul` agents
- **HITL Gate**: Deterministic escalation for low margin, high value, compliance failure, injection
- **FastAPI Dashboard**: REST API + UI with AP2 Pay, Agents, Vibe, and Architecture tabs
- **140 pytest tests**: unit + trajectory, all passing, offline-safe

## What We Demonstrate

### 1. Real MCP Protocol Implementation

- **Built**: stdio JSON-RPC MCP server with 5 namespaces (`rate_card`, `vendor`, `policy`, `telemetry`, `tms`)
- **Real-world**: Production-grade protocol, not REST mocks
- **Alignment**: Agents call tools through MCP — same pattern as real tool-use deployments

### 2. Multi-Agent Fleet (8 Agents)

- **Built**: `QuotationDecisionAgent` (ADK + Gemini LLM), `CommerceAgent`, `HumanSupervisorAgent`,
  `A2UIConciergeAgent`, `OperationsInsightAgent`, `LoadPlanningAgent`, `SecuritySentinelAgent`,
  `OrchestratorAgent` + carrier-side A2A agents
- **Real-world**: Specialized roles, clean separation of concerns
- **Alignment**: LLMs orchestrate; deterministic Python tools compute

### 3. AP2 Agent Payments (Flagship)

- **Built**: Intent Mandate (spend cap) → A2A negotiation → Cart Mandate → HITL → Stripe test-mode / Plaid sandbox
- **Real-world**: Real payment rails; vendor actually receives (fake-money) payment
- **Alignment**: Only pays on approved Cart Mandate within cap; live keys hard-blocked

### 4. Real OR-Tools Optimization (not LLM guessing)

- **Built**: Capacitated VRP with Time Windows — two dimensions (pallets + weight), delivery windows,
  distance minimization, nearest-neighbour fallback
- **Real-world**: VRP is NP-hard; LLMs should never solve routing
- **Alignment**: Deterministic solver, provably optimal within OR-Tools bounds

### 5. Deterministic Guardrails

- **Built**: 12% margin floor in Python (`ceil(vendor_cost / (1-0.12))`), prompt-injection sanitizer,
  HITL gate, live-payment hard-blocks, no-charge-without-approval
- **Real-world**: Financial systems never use LLMs for arithmetic
- **Alignment**: Proven by `test_margin_is_floor_not_rate_card_tautology`

### 6. Evaluation + Agentic Memory

- **Built**: 8-step trajectory evaluator, 100 deterministic EVAL cases, `ShipmentHistoryStore`
  (file-backed), `AgentContextBuffer` (sliding window injected into system prompt)
- **Real-world**: Agent-as-judge evaluation; memory enables conversational continuity
- **Alignment**: Day 4 patterns implemented end-to-end

### 7. Deployment + CI/CD

- **Built**: Cloud Run Dockerfile + `service.yaml` + `deploy.sh` + `.github/workflows/ci.yml`
- **Real-world**: Production-deployable, secrets via Secret Manager
- **Alignment**: `uv sync && uv run pytest -q && docker build ...` pipeline works

## Technical Excellence

### Deterministic vs LLM Responsibilities

| Task                                      | Owner                                       | Why                                         |
| ----------------------------------------- | ------------------------------------------- | ------------------------------------------- |
| Margin calculation                        | `QuotationEngine` (Python)                  | LLM math errors unacceptable in finance     |
| Vendor ranking                            | `VendorScorer` / MCP `vendor.rank_for_lane` | Deterministic 70/30 weighted score          |
| Route optimization                        | OR-Tools CVRPTW                             | VRP is NP-hard; LLMs can't solve it         |
| Compliance / HITL triggers                | `evaluate_hitl` (Python)                    | Deterministic thresholds, auditable         |
| Payment execution                         | Stripe/Plaid SDKs                           | Real rails; charge only on approved mandate |
| Routing, negotiation strategy, narratives | LLM agents                                  | Appropriate use of LLMs                     |

### Loop Guardrails

**Loop 1: Vendor Evaluator-Optimizer**

- Max 5 iterations; shrinking candidate set; tried-set tracking; HITL escalation on margin gap > 2%

**Loop 2: Compliance-Critic → Replan**

- Max 3 iterations; A2A handoff; deterministic compliance checks; escalation if violations persist

**Loop 3: Kaizen Meta-Loop**

- Max 3 iterations; runs pytest; classifies failure patterns; writes `specs/kaizen_log.md`

## Success Metrics

- ✅ Built with **OpenCode** (antigravity IDE) + **antigravity models** throughout
- ✅ **Google ADK** harness on all 8 agents — `.agy` + skill contracts + runtime wiring
- ✅ **Google Agent CLI** used for scaffolding and deployment
- ✅ **Vertex AI Gemini 2.0 Flash** as the LLM for ADK agents
- ✅ **Google Cloud Run** deployment ready (Dockerfile + service.yaml + deploy.sh)
- ✅ **Google Secret Manager** for `GEMINI_API_KEY` at runtime
- ✅ Real stdio **MCP** server (not REST mocks) — 5 namespaces
- ✅ 8-agent fleet fully wired in `AgentSystem` with `OrchestratorAgent` integrated
- ✅ AP2 mandate chain: Intent → Cart → HITL → payment
- ✅ OR-Tools CVRPTW load planning (real solver)
- ✅ Deterministic 12% margin floor — not a tautology
- ✅ Bounded autonomous loops with escalation (never unbounded)
- ✅ HITL gate for exception handling
- ✅ 140 pytest tests passing (unit + trajectory), offline-safe
- ✅ Kaggle notebook (`3pl_multi_agent_optimization.ipynb`) — runs offline, no keys

## What This Is NOT

- **NOT a demo** — Production-grade code with real MCP protocol, real OR-Tools, real Stripe/Plaid
- **NOT a tautology** — Margin computed from selected vendor effective cost, not rate card
- **NOT LLM math** — All financial calculations deterministic
- **NOT unbounded loops** — All loops have max iterations and escalation

## Conclusion

This capstone demonstrates a **real autonomous logistics system** built with **OpenCode**
(antigravity IDE), **Google ADK**, **Google Agent CLI**, and **Google Cloud** — covering every
day of the 5-Day Gen-AI Agents course with concrete, runnable evidence.

The AP2 payment flow (Intent Mandate → A2A negotiation → Cart Mandate → HITL → Stripe/Plaid)
is the most differentiated element — it shows agents that can actually move (fake) money with
proper authorization chains and guardrails, all built and validated through agentic development
in OpenCode with antigravity models.
