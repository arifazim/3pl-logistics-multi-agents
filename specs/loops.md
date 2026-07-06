# Closed Loops — MVP (Built)

Only **Loop 1** and **Loop 3** are implemented. Loop 2 (vendor reliability) is folded into `vendor.rank_for_lane`. Loop 4+ are future work.

---

## Loop 1 — SDLC Kaizen

**Goal:** Specs → tests → trajectory eval → improvement proposals.

**Module:** `runtime/loops/loop1_sdlc_kaizen.py`

**Cycle:**
1. Gherkin specs in `specs/gherkin/`
2. Trajectory evaluator asserts dual-quotation flow
3. `pytest tests/` — full suite
4. Kaizen report surfaces failures and spec gaps

**Run:**
```bash
PYTHONPATH=. python -c "from runtime.loops.loop1_sdlc_kaizen import run_sdlc_kaizen_loop; print(run_sdlc_kaizen_loop())"
```

---

## Loop 3 — Two-Sided Quotation

**Goal:** Customer price balanced against **selected vendor's actual cost** with margin ≥ 12%.

**Module:** `runtime/loops/loop3_two_sided_quotation.py`

**Cycle:**
1. Customer quote request for lane
2. `quotation_decision_agent` ranks vendors (MCP `vendor.rank_for_lane`)
3. `QuotationEngine` prices from selected vendor cost
4. Policy compliance + HITL gate
5. Trajectory eval + telemetry

**Run:**
```bash
PYTHONPATH=. python -c "from runtime.loops.loop3_two_sided_quotation import run_two_sided_quotation_loop_sync; print(run_two_sided_quotation_loop_sync())"
```

---

## Skipped (not stubbed)

| Loop | Reason |
|------|--------|
| Loop 2 — Vendor Reliability | Ranking + telemetry in MCP; no separate loop agent |
| Loop 4 — Route Optimization | Future OR-Tools; not LLM |
| Loop 5–7 — Security theater / Phase progression | Out of capstone scope |

**Future work:** OR-Tools VRP, extended agent fleet — one line in ARCHITECTURE.md only.
