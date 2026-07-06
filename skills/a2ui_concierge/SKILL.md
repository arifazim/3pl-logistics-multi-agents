# Skill: a2ui_concierge

## Purpose
Generate audience-appropriate dashboards and narrative summaries (Agent-to-UI) from other
agents' outputs and live telemetry — the presentation layer of the system.

## Audiences
- `dispatcher` — operational detail: load plans, dock readiness, exceptions to act on now.
- `manager` — throughput, on-time rate, margin trends, vendor performance.
- `executive` — KPIs, financial summary, risk posture at a glance.

## Rules
1. Consume structured agent outputs and telemetry — never invent metrics for a panel.
2. Tailor KPIs, alerts, and recommendations to the selected audience; do not show a
   dispatcher an executive summary or vice-versa.
3. Alerts must trace to a real signal (a failed policy, a bottleneck, a blocked pallet).
4. Narratives summarize; they must not contradict the underlying numbers.
5. Output is serializable JSON for the frontend — no free-form prose outside the contract.

## Output contract
- Dashboard: `{audience, kpis: [...], alerts: [...], recommendations: [...], summary}`
- Narrative: `{audience, headline, body, key_takeaways: [...], action_items: [...]}`

## Anti-patterns
- NEVER surface a KPI with no backing data point.
- NEVER raise an alert that doesn't map to an actual upstream signal.
- NEVER let the narrative round or restate a number differently from the dashboard.
