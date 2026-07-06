# Skill: customer_quotation

## Purpose
Produce the customer-facing price for a lane, priced from the **selected vendor's actual
cost** — not the rate card, not the cheapest bid.

## Rules
1. Always call `compute_margin_quote` (deterministic QuotationEngine) — the LLM never
   computes margin or price.
2. Pricing basis is the SELECTED vendor's effective cost (base rate + weight surcharge),
   after the `vendor_quotation` ranking picks the carrier.
3. Vendor cost = effective rate × SLA vendor multiplier (standard 1.0×, express 1.15×).
4. Customer price = vendor_cost ÷ (1 − 12% floor), rounded **up** to the cent so the
   realized margin never dips below the 12% floor, then × (1 + SLA customer premium).
5. The rate-card `target_margin_pct` (e.g. 15%) is reference only — the enforced floor is
   12% on the selected vendor's cost.

## Output contract
`{lane, sla_tier, selected_vendor_id, selected_vendor_name, vendor_cost_base, vendor_cost,
customer_price, total_rate, margin, margin_percentage, margin_floor_pct,
list_price_reference, target_margin_reference, pricing_basis: "selected_vendor_cost"}`

## Anti-patterns
- NEVER price off the rate card list price — that hides the true margin.
- NEVER base margin on the cheapest vendor when a costlier one was selected on reliability.
- NEVER round the customer price down below the 12% floor.
- NEVER quote a lane without a vendor ranking (`vendor_quotation`) first.
