# Skill: evaluation

## Purpose
Judge whether a workflow run is correct using deterministic checks and trajectory
evaluation — the quality gate for the system.

## Checks (backed by MarginEvaluator + trajectory_evaluator)
1. **Margin** — realized margin `(customer_price − vendor_cost) / customer_price` ≥ 12%.
2. **Competitiveness** — customer price is sane relative to the cheapest vendor cost.
3. **Reliability** — selected vendor reliability meets the minimum bar.
4. **Trajectory** — the agent took the required steps in order (rank → quote → compliance
   → HITL → eval) with each step's evidence present.

## Rules
1. Evaluation is deterministic — recompute from the run's own numbers, never trust a
   self-reported "passed" flag from the agent under test.
2. A run passes only if every check passes; report the first failing check and why.
3. Trajectory evaluation checks step presence and ordering, not just the final answer.
4. Use the 100-case deterministic `EVAL_SHIPMENTS` set for regression comparisons.

## Output contract
`{passed: bool, checks: [{name, passed, expected, actual}], failing_reason,
trajectory: {passed, steps: [...]}}`

## Anti-patterns
- NEVER pass a run because it "looks right" — recompute the margin.
- NEVER accept the agent's own margin figure without re-deriving it.
- NEVER skip trajectory checks just because the final price is correct.
