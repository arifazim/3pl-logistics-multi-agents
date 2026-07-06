# AGENTS.md

Developer and agentic-IDE reference for the **3PL Multi-Agent Optimization System**.

This file is the operational guide for **OpenCode** (antigravity IDE) sessions and any agentic tool (Cursor, Windsurf, etc.) working in this repository. 

---

## Development environment

| Tool                           | Version / detail                                                        |
| ------------------------------ | ----------------------------------------------------------------------- |
| **OpenCode** (antigravity IDE) | Primary IDE — agentic coding, refactoring, test generation, doc writing |
| **Antigravity models**         | LLM backbone for OpenCode sessions (claude-sonnet-4 / latest)           |
| **Google ADK**                 | `google-adk>=1.0` — `LlmAgent`, `InMemoryRunner`, tool registration     |
| **Google Agent CLI**           | `agents-cli` — scaffold, evaluate, deploy the fleet                     |
| **Vertex AI / Gemini**         | `gemini-2.0-flash` (default) configured in `runtime/config.yaml`        |
| **Google Cloud Run**           | Target runtime — `deployment/cloudrun/`                                 |
| **Google Secret Manager**      | `GEMINI_API_KEY` at deploy time                                         |
| **uv**                         | Package manager + virtualenv                                            |
| **Python**                     | ≥3.10                                                                   |

---

## Common commands

```bash
# Install all dependencies (stripe + plaid are core deps, not optional)
uv sync

# Run the full test suite (140 tests, no network, no API keys needed)
uv run pytest -q

# Run a single test file
uv run pytest tests/unit/test_commerce_agent.py -q

# Run a single test
uv run pytest tests/unit/test_orchestrator.py::test_name -q

# Run trajectory (end-to-end flow) tests only
uv run pytest tests/trajectory/ -q

# Launch the dashboard API (http://localhost:9000)
uv run uvicorn frontend.cloudrun_app.app:app --host 0.0.0.0 --port 9000 --reload

# Run the MCP server standalone (stdio JSON-RPC)
PYTHONPATH=. python -m mcp_servers.pl3_server.server

# Verify sandbox payment flow (needs .env with ALLOW_LIVE_PAYMENTS=1 + test/sandbox keys)
uv run python scripts/verify_payments.py

# Capture test output for submission
uv run pytest -q | tee logs/pytest.txt
```

---

## Environment flags

Two flags gate all LLM and network behaviour:

| Flag                    | Default | Effect                                                                                                                                                                                                                      |
| ----------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ALLOW_OFFLINE_AGENT=1` | unset   | `QuotationDecisionAgent` and `OrchestratorAgent` run deterministic tool orchestration without calling Gemini. Required for all unit tests. Without this flag and without `GEMINI_API_KEY`, LLM agents raise `RuntimeError`. |
| `ALLOW_LIVE_PAYMENTS=1` | unset   | `CommerceAgent` uses real Stripe test-mode / Plaid sandbox rails. Default is a network-free `MockProcessor`. Live credentials (`sk_live_`, `PLAID_ENV=production`) are **hard-blocked in code** regardless.                 |

Set both in `.env` (see `.env.example`). Tests set `ALLOW_OFFLINE_AGENT=1` automatically.

---

## Architecture

Eight ADK/Gemini + deterministic agents take a natural-language freight request through
**quote → A2A negotiation → AP2 payment → HITL approval → A2UI presentation**.

**Governing rule: LLMs orchestrate, deterministic Python tools compute.**
All money math, vendor ranking, routing, and compliance/HITL thresholds live in plain
Python — never in an LLM.

### Agent harness (three layers — consistent across all 8 agents)

```
Layer 1 — Declaration  :  agy/agents/{name}.agy   YAML: name, description, skills, tools, prompt
Layer 2 — Skill context:  skills/{name}/SKILL.md  Purpose / Rules / Output contract / Anti-patterns
Layer 3 — Runtime      :  Python __init__          load_agy() + load_agent_skills() → self._instruction
```

For `QuotationDecisionAgent` and `OrchestratorAgent`, `self._instruction` is also injected
into a Google ADK `Agent` object + `InMemoryRunner` so Gemini orchestrates tool calls.
For deterministic agents, `self._skill_context` holds the loaded contract for logging/audit.

### Layered layout

```
runtime/agents/         — 8 agent classes + vendor_side_agents.py (A2A carrier agents)
runtime/agent_system.py — AgentSystem: wires all agents, loads agent_graph.yaml,
                          dispatches execute_agent_workflow(name, input)
runtime/tools/          — quotation_engine (margin), vendor_scorer (70/30 via MCP),
                          route_optimizer
runtime/security/       — vendor_text_sanitizer.py (prompt-injection defense)
runtime/hitl/           — gate.py (deterministic HITL escalation thresholds)
runtime/evaluation/     — trajectory_evaluator + margin evaluator
runtime/commerce/       — mandates.py (Intent/Cart, sha256 content_hash)
                          payments.py (MockProcessor / Stripe / Plaid, live-key guards)
runtime/memory.py       — InSessionMemory, ShipmentHistoryStore, AgentContextBuffer
runtime/loops/          — 3 bounded autonomous loops
mcp_servers/pl3_server/ — real stdio JSON-RPC MCP server (5 namespaces)
frontend/cloudrun_app/  — FastAPI app (all /api/* endpoints + UI templates)
agy/agents/*.agy        — agent declaration files (prompt + skills + tools + input schema)
agy/agent_graph.yaml    — authoritative fleet/workflow/loop/MCP/payments map
skills/*/SKILL.md       — 10 skill contracts (one per skill directory)
deployment/cloudrun/    — Dockerfile, service.yaml, deploy.sh for Google Cloud Run
.github/workflows/      — ci.yml (test + lint + Docker build on push/PR)
```

### Config-driven behaviour (edit these, not hardcoded values)

- **`agy/agent_graph.yaml`** — authoritative fleet/workflow/loop/MCP/payments map. Adding a
  workflow means: (1) a new node/workflow entry here, (2) a branch in
  `AgentSystem.execute_agent_workflow`, (3) a FastAPI route.
- **`runtime/config.yaml`** — `min_margin_percentage: 12.0`, Gemini model names
  (`gemini-2.0-flash` default), SLA thresholds, surcharges, capacity limits.
- **`agy/agents/*.agy`** + **`skills/*/SKILL.md`** — agent instructions and skill contracts.
  The skills loader is **strict**: a missing skill raises `FileNotFoundError` loudly.
- **`runtime/skills/loader.py`** — `AGENT_SKILLS` registry maps each agent class to its
  skill list. Kept in sync with `agy/agents/*.agy` skills lists.

---

## Non-negotiable invariants (do not weaken)

1. **12% margin floor**: `customer_price = ceil(vendor_cost / (1 − 0.12))` from the
   **selected** vendor's cost (not rate card, not cheapest bid), rounded up to the cent.
   Enforced in Python only. Guarded by `test_margin_is_floor_not_rate_card_tautology`.

2. **AP2 charge safety**: no payment without an approved Cart Mandate; never above the
   Intent spend cap. Guarded by `test_no_payment_without_approved_cart_mandate`.

3. **HITL gate**: auto-escalates on margin < 12%, load value ≥ $10k, compliance failure,
   or prompt-injection flag. Thresholds in `runtime/hitl/gate.py`.

4. **Live-key hard-block**: `sk_live_` Stripe keys and `PLAID_ENV=production` raise
   `ValueError` before any network call. `ALLOW_LIVE_PAYMENTS=1` required for test-mode.

5. **Skills loader strict**: `load_skills(names, strict=True)` raises `FileNotFoundError`
   on any missing skill. Never silently drops instructions.

6. **Agent harness**: every agent must have an `.agy` file in `agy/agents/` and call
   `load_agy()` + `load_agent_skills()` in `__init__`. Do not add hardcoded instructions.

---

## Autonomous loops (all bounded — never unbounded)

| Loop                                | File                         | Max iterations | Guardrail                                                      |
| ----------------------------------- | ---------------------------- | -------------- | -------------------------------------------------------------- |
| Loop 1 — Vendor Evaluator-Optimizer | `loop1_vendor_evaluator.py`  | 5              | Deterministic margin check; HITL escalation on gap > 2%        |
| Loop 2 — Compliance-Critic → Replan | `loop2_compliance_replan.py` | 3              | Deterministic compliance check; A2A handoff                    |
| Loop 3 — Kaizen Meta-Loop           | `loop3_kaizen.py`            | 3              | Runs pytest; classifies failures; writes `specs/kaizen_log.md` |

---

## Deployment (Google Cloud Run)

```bash
# Prerequisites: gcloud CLI authenticated, project set, APIs enabled
gcloud services enable artifactregistry.googleapis.com run.googleapis.com secretmanager.googleapis.com

# Store the Gemini API key in Secret Manager
echo "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-

# Build and push the Docker image
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/3pl-orchestrator/3pl-orchestrator"
docker build -t ${IMAGE} -f deployment/cloudrun/Dockerfile .
gcloud auth configure-docker ${REGION}-docker.pkg.dev
docker push ${IMAGE}

# Deploy to Cloud Run
gcloud run deploy 3pl-orchestrator \
  --image=${IMAGE} \
  --platform=managed \
  --region=${REGION} \
  --allow-unauthenticated \
  --port=9000 \
  --set-secrets=GEMINI_API_KEY=gemini-api-key:latest \
  --cpu=2 --memory=2Gi --max-instances=10 --min-instances=1

# Verify
curl https://YOUR_SERVICE_URL/health
```

Full walkthrough in `BUILD.md`. CI/CD in `.github/workflows/ci.yml`.

---

## Adding a new agent (checklist)

1. Create `agy/agents/{name}.agy` with `name`, `description`, `skills`, `tools`, `prompt` fields.
2. Create `skills/{name}/SKILL.md` if a new skill is needed (Purpose / Rules / Output contract / Anti-patterns).
3. Add the skill to `AGENT_SKILLS` in `runtime/skills/loader.py`.
4. Add a node to `agy/agent_graph.yaml` with `file:`, `module:`, `skills:`, `harness:` fields.
5. Implement the Python class in `runtime/agents/{name}_agent.py`:
   - `AGY_NAME = "{name}"`
   - `__init__`: call `load_agy(self.AGY_NAME)` and `load_agent_skills("{name}_agent")`
   - For LLM agents: construct `AdkAgent` and `InMemoryRunner`
6. Instantiate in `AgentSystem.__init__`.
7. Add the workflow branch to `AgentSystem.execute_agent_workflow`.
8. Add a FastAPI route in `frontend/cloudrun_app/app.py`.
9. Add tests in `tests/unit/test_{name}_agent.py` and `tests/trajectory/`.

---

## Key test files

| File                                           | Covers                                                             |
| ---------------------------------------------- | ------------------------------------------------------------------ |
| `tests/unit/test_adk_agent.py`                 | `.agy` loading, skill loading, offline tool pipeline, margin floor |
| `tests/unit/test_skills.py`                    | All 10 skill files present, well-formed, registry consistent       |
| `tests/unit/test_agent_graph.py`               | YAML structure, node skills exist on disk, workflow bindings       |
| `tests/unit/test_commerce_agent.py`            | AP2 mandate chain, cap enforcement, approve-before-charge          |
| `tests/unit/test_mandates.py`                  | Intent/Cart mandate construction, content_hash                     |
| `tests/unit/test_stripe_processor.py`          | Card + ACH paths (fake stripe module, no network)                  |
| `tests/unit/test_memory.py`                    | ShipmentHistoryStore, AgentContextBuffer                           |
| `tests/unit/test_vendor_text_sanitizer.py`     | Prompt-injection detection                                         |
| `tests/unit/test_cvrptw_solver.py`             | OR-Tools CVRPTW capacity + time-window constraints                 |
| `tests/trajectory/test_ap2_payment_flow.py`    | Full AP2 end-to-end trajectory                                     |
| `tests/trajectory/test_dual_quotation_flow.py` | Dual quotation end-to-end trajectory                               |

---

## Docs

- [README.md](README.md) — quickstart, agent table, guardrails, tech stack
- [ARCHITECTURE.md](ARCHITECTURE.md) — full system design, harness, workflows, Google stack
- [KAGGLE.md](KAGGLE.md) — Kaggle submission package
- [BUILD.md](BUILD.md) — Cloud Run build + deploy walkthrough
- [REVIEW.md](REVIEW.md) — capability-by-capability review
