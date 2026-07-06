# Skill: vendor_quotation

## Purpose
Select the best carrier for a lane using a reliability-weighted score.

## Rules
1. Always call `rank_vendors_for_lane` — never guess carrier names.
2. Use the MCP `vendor.rank_for_lane` tool with 70% reliability / 30% cost weighting.
3. The top-ranked vendor by `final_score` is the recommended carrier.
4. Weight surcharge applies above 1000 lbs at $0.02/lb.
5. Express SLA multiplier = 1.15× on vendor cost; Standard = 1.0×.

## Output contract
Return: `{ranked: [...], selected: {vendor_id, final_score, effective_rate, reliability_score}}`

## Anti-patterns
- NEVER pick a vendor based on name recognition.
- NEVER assume a vendor serves a lane without calling the tool.
- NEVER skip the ranking call even if only one vendor is known.
