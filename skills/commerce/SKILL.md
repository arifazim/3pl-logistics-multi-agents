# Skill: commerce

## Purpose
Run agent-to-agent (A2A) carrier negotiation and simulate the AP2 / UCP commerce
protocol: a broker agent solicits offers from carrier agents, exchanges counter-offers,
and settles on an agreed rate within mandate limits.

## AP2 mandate chain (CommerceAgent.settle)
1. **Intent Mandate** — a hard spend cap (`max_amount`) authorizing the agent to buy for a
   shipment. Seeded target for negotiation comes from the MCP-ranked vendor's effective cost.
2. **Cart Mandate** — the specific `{vendor_id, agreed_rate, customer_price, margin}`. Its
   `agreed_rate` may NEVER exceed the Intent Mandate cap (`build_cart_mandate` rejects it).
3. **Human approval == Cart Mandate authorization** — `evaluate_hitl` decides; an approved
   cart is stamped with approver + timestamp. No approval → no charge.
4. **Payment execution** — only against an APPROVED cart; the vendor agent acknowledges
   receipt (`acknowledge_payment`). Idempotency key = cart mandate id.

## Rules
1. The broker's opening target is seeded from the MCP-ranked vendor's effective cost —
   never a guessed number.
2. Each carrier agent (Swift, Falcon, EcoHaul, …) responds with an offer or counter-offer
   per round; negotiation is bounded (max rounds) to guarantee termination.
3. The agreed carrier is chosen on the settled rate **and** reliability, consistent with
   `vendor_quotation` (never rate alone).
4. Payment rails default to a safe MockProcessor; real Stripe test-mode / Plaid sandbox is
   used only with `ALLOW_LIVE_PAYMENTS=1`. Live credentials are hard-blocked.
5. Every offer, counter, acceptance, mandate, and receipt is logged for a non-repudiable
   audit trail. Mandates are simulated JSON with a content hash — not yet signed VCs.

## Output contract
`{shipment_id, lane, agreed: bool, agreed_vendor_id, agreed_rate, rounds, summary,
all_offers: [{vendor_id, vendor_name, offered_rate, accepted, counter_offer, round_num,
reason, reliability_score}], mcp_reference_cost}`

## Anti-patterns
- NEVER charge without an approved Cart Mandate.
- NEVER commit to a rate above the Intent Mandate spend cap.
- NEVER negotiate unbounded — always enforce the round cap.
- NEVER settle without recording the mandate chain + receipt (audit requirement).
- NEVER use live payment credentials in this demo.
