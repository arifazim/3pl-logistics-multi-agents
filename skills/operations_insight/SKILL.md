# Skill: operations_insight

## Purpose
Surface operational intelligence across the warehouse network: flow bottlenecks,
dock dwell predictions, vendor reliability, and pallet readiness.

## Capabilities (backed by OperationsInsightAgent)
1. `analyze_warehouse_flows(start_warehouse, end_location, flow_type, time_window_hours)`
   — detect bottlenecks along a `warehouse_to_warehouse` / `warehouse_to_customer` /
   `inbound` / `outbound` flow.
2. `score_vendor_reliability(vendor_id, lookback_days)` — composite score from on-time
   delivery, damage rate, communication, and capacity utilization, plus a trend.
3. `check_pallet_readiness(warehouse)` — ready / pending / blocked pallet counts and a
   readiness percentage with an estimated completion time.

## Rules
1. Pull metrics from MCP telemetry — never invent throughput, dwell, or damage figures.
2. Bottleneck detection is heuristic + data driven; always attach the evidence
   (which metric crossed which threshold).
3. Reliability scores are advisory inputs to `vendor_quotation`, not a substitute for
   the 70/30 ranking.
4. Dwell predictions are estimates — label them as predictions, not commitments.

## Output contract
- Flows: `{bottlenecks: [{location, severity, cause, metric}], dwell_predictions: [...]}`
- Reliability: `{vendor_id, overall_score, on_time_delivery_rate, damage_rate, communication_score, capacity_utilization, trend}`
- Readiness: `{warehouse, total_pallets, ready_pallets, pending_pallets, blocked_pallets, readiness_percentage, estimated_completion_time}`

## Anti-patterns
- NEVER fabricate telemetry when the MCP call returns no data — report the gap.
- NEVER present a dwell prediction as a guaranteed dock time.
- NEVER let a high reliability score alone auto-approve a low-margin load.
