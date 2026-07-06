# Security Scope — What Applies and What Does Not

## Threat model for this capstone

This system is a **logistics quotation orchestrator**. Agents read vendor-supplied text (emails, portal quotes, rate sheets) and can **commit money** (approve quotes, assign carriers). The realistic adversarial surface is:

> **Prompt injection via vendor-supplied text** reaching an agent that executes financial actions.

We do **not** install packages at runtime, expose a public agent marketplace, or run continuous red-team exercises against a route planner. Applying all seven Effective Trust pillars here would be **security theater**.

---

## In scope (built)

### 1. Vendor text sanitization (`runtime/security/vendor_text_sanitizer.py`)

Before any vendor quote text enters an LLM context or influences a decision:

- Strip known injection patterns (`ignore previous instructions`, `system:`, role overrides)
- Enforce max length and character allowlist for structured fields
- Flag suspicious content for HITL escalation instead of silent pass-through
- Log sanitization events to telemetry

### 2. Input sandboxing on quotation workflow

- Vendor quotes enter only through the `vendor_quotation` workflow path
- Structured fields (rate, vendor_id) validated against MCP responses — never trusted from free text alone
- Margin and pricing decisions use `QuotationEngine` only; LLM cannot override numeric outputs

### 3. Policy-first execution

- Gherkin specs define margin floor, SLA limits, escalation rules
- Compliance checks call policy MCP; failures block auto-approval

---

## Out of scope (documented, not stubbed)

| Pillar | Why it does not apply |
|--------|----------------------|
| **Slopsquatting defense** | No runtime package installation by agents |
| **Red/Blue/Green continuous adversarial testing** | Overkill for a quotation workflow; no autonomous attack surface worth continuous fuzzing |
| **Ephemeral sandboxing (containers)** | Capstone runs local MCP mocks; production would use Cloud Run isolation — not simulated here |
| **Dependency verification** | Static `uv.lock`; no agent-driven `pip install` |
| **Fraud detection ML** | Out of slice; vendor reliability uses deterministic scorer |

---

## Production extensions (one paragraph for write-up)

In production we would add: OAuth-scoped MCP access, audit logging to BigQuery, VPC-SC for vendor integrations, and Cloud Armor on the dashboard API. Those are infrastructure concerns, not agent-graph nodes.
