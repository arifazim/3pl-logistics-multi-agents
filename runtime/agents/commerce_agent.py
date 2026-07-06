"""Commerce Agent — AP2 buyer/broker orchestrating mandate → negotiate → approve → pay.

End-to-end AP2 (Agent Payments Protocol) demonstration:
  1. Issue an Intent Mandate (spend cap for the shipment).
  2. Run A2A vendor negotiation (reuses A2ANegotiator).
  3. Build a Cart Mandate for the agreed vendor + rate (amount <= intent cap).
  4. Human-in-the-loop approval == Cart Mandate authorization (reuses evaluate_hitl).
  5. Execute payment ONLY on an approved Cart Mandate (rails from get_payment_stack()).
  6. The vendor/carrier agent acknowledges receipt of the (sandbox) payment.
  7. Persist the full mandate chain + receipt as an audit trail.
"""

from __future__ import annotations

from typing import Any

from runtime.adapters.pl3_mcp_client import Pl3McpClient
from runtime.agents.human_supervisor_agent import HumanSupervisorAgent
from runtime.agents.vendor_side_agents import A2ANegotiator
from runtime.agy.loader import load_agy
from runtime.commerce.mandates import (
    CartMandate,
    MandateStatus,
    approve_cart_mandate,
    build_cart_mandate,
    build_intent_mandate,
)
from runtime.commerce.payments import PaymentStack, get_payment_stack
from runtime.hitl.gate import evaluate_hitl
from runtime.memory import history_store
from runtime.skills.loader import load_agent_skills
from runtime.tools.quotation_engine import QuotationEngine


class CommerceAgent:
    """Broker-side AP2 agent. Math stays in QuotationEngine; routing/negotiation reused."""

    AGY_NAME = "commerce"

    def __init__(
        self,
        mcp: Pl3McpClient | None = None,
        negotiator: A2ANegotiator | None = None,
        payment_stack: PaymentStack | None = None,
        supervisor: HumanSupervisorAgent | None = None,
    ):
        self.mcp = mcp or Pl3McpClient()
        self.quotation_engine = QuotationEngine(self.mcp)
        self.negotiator = negotiator or A2ANegotiator()
        self.payment_stack = payment_stack or get_payment_stack()
        self.supervisor = supervisor or HumanSupervisorAgent()
        # ── Agent harness: load .agy spec + skill contracts ──────────────────
        self._agy = load_agy(self.AGY_NAME)
        self._skill_context = load_agent_skills("commerce_agent")

    async def settle(
        self,
        *,
        lane: str,
        weight_lbs: float = 1000.0,
        sla_tier: str = "standard",
        shipment_id: str = "UNKNOWN",
        max_amount: float | None = None,
        human_approved: bool = False,
        approver: str = "dispatcher",
        payment_method: str = "card",
        persist: bool = True,
    ) -> dict[str, Any]:
        # 1. Intent Mandate — spend cap for this shipment.
        ranking = self.mcp.rank_vendors(lane, weight_lbs=weight_lbs)
        selected = ranking.get("selected") or {}
        vendor_cost_from_mcp = float(
            selected.get("effective_rate", selected.get("rate", 300.0))
        )
        cap = (
            max_amount
            if max_amount is not None
            else round(vendor_cost_from_mcp * 1.25, 2)
        )
        intent = build_intent_mandate(
            shipment_id=shipment_id,
            lane=lane,
            weight_lbs=weight_lbs,
            max_amount=cap,
            sla_tier=sla_tier,
            constraints={"margin_floor_pct": 12.0},
        )

        # 2. A2A negotiation (reused).
        neg = self.negotiator.negotiate(
            lane=lane,
            weight_lbs=weight_lbs,
            sla_tier=sla_tier,
            vendor_cost_from_mcp=vendor_cost_from_mcp,
            shipment_id=shipment_id,
        )
        if not neg.agreed:
            return {
                "workflow": "ap2_payment",
                "status": "no_agreement",
                "requires_hitl": True,
                "intent_mandate": intent.model_dump(mode="json"),
                "negotiation_summary": neg.summary,
                "payment_mode": self.payment_stack.mode,
            }

        agreed_rate = float(neg.agreed_rate)
        vendor_agent = self.negotiator.agents.get(neg.agreed_vendor_id)
        vendor_name = vendor_agent.vendor_name if vendor_agent else selected.get("name")

        # 3. Cart Mandate — customer price from the deterministic engine; margin vs the
        #    actually-negotiated cost. Raises if the negotiated rate exceeds the cap.
        quote = self.quotation_engine.calculate_customer_quote(
            lane, weight=weight_lbs, sla_tier=sla_tier, vendor_id=neg.agreed_vendor_id
        )
        customer_price = float(quote["customer_price"])
        margin_pct = (
            round((customer_price - agreed_rate) / customer_price * 100, 2)
            if customer_price
            else 0.0
        )
        try:
            cart = build_cart_mandate(
                intent=intent,
                vendor_id=neg.agreed_vendor_id,
                vendor_name=vendor_name,
                agreed_rate=agreed_rate,
                customer_price=customer_price,
                margin_percentage=margin_pct,
            )
        except ValueError as exc:
            return {
                "workflow": "ap2_payment",
                "status": "rejected_cap_exceeded",
                "requires_hitl": True,
                "intent_mandate": intent.model_dump(mode="json"),
                "negotiation_summary": neg.summary,
                "error": str(exc),
                "payment_mode": self.payment_stack.mode,
            }

        # 4. HITL == Cart Mandate authorization.
        hitl = evaluate_hitl(
            margin_pct=margin_pct, load_value=customer_price, compliance_passed=True
        )
        if hitl.requires_approval and not human_approved:
            supervisor_summary = self.supervisor.review(
                action=f"Execute AP2 payment ${agreed_rate:.2f} to {vendor_name or neg.agreed_vendor_id} for {shipment_id}",
                margin_pct=margin_pct,
                total_rate=customer_price,
                vendor_id=neg.agreed_vendor_id,
                shipment_id=shipment_id,
                lane=lane,
                action_type="execute_payment",
            )
            audit = self._audit(intent, cart, None, None, neg)
            if persist:
                await history_store.save(shipment_id, audit)
            return {
                "workflow": "ap2_payment",
                "status": "pending_approval",
                "requires_hitl": True,
                "hitl_reasons": hitl.reasons,
                "supervisor_summary": supervisor_summary,
                "intent_mandate": intent.model_dump(mode="json"),
                "cart_mandate": cart.model_dump(mode="json"),
                "negotiation_summary": neg.summary,
                "payment_mode": self.payment_stack.mode,
            }
        approve_cart_mandate(
            cart,
            approver=approver if human_approved else "auto_policy",
            reasons=hitl.reasons,
        )

        # 5. Execute payment (approved cart only), 6. vendor acknowledges receipt.
        #    Funding method is chosen per-request: ACH links a Plaid bank account, card uses
        #    Stripe's test card. In live mode ACH pulls a real Plaid-verified funding source.
        want_ach = payment_method.lower() == "ach"
        if want_ach:
            funding = self.payment_stack.funding_provider.describe(for_ach=True)
        else:
            funding = {
                "provider": self.payment_stack.processor.name,
                "funding_type": "card",
                "brand": "visa",
                "last4": "4242",
            }
        receipt = self.payment_stack.processor.charge(cart, funding_source=funding)
        cart.status = MandateStatus.executed
        vendor_ack = (
            vendor_agent.acknowledge_payment(receipt)
            if vendor_agent
            else {"acknowledged": False, "reason": "vendor agent not found"}
        )

        # 7. Persist audit chain.
        audit = self._audit(intent, cart, receipt, vendor_ack, neg)
        if persist:
            await history_store.save(shipment_id, audit)

        return {
            "workflow": "ap2_payment",
            "status": "settled",
            "requires_hitl": False,
            "quote": {
                "lane": lane,
                "selected_vendor_id": neg.agreed_vendor_id,
                "selected_vendor_name": vendor_name,
                "customer_price": customer_price,
                "agreed_rate": agreed_rate,
                "margin_percentage": margin_pct,
                "sla_tier": sla_tier,
            },
            "negotiation": {
                "agreed": neg.agreed,
                "agreed_vendor_id": neg.agreed_vendor_id,
                "agreed_rate": neg.agreed_rate,
                "summary": neg.summary,
                "rounds": neg.rounds,
            },
            "intent_mandate": intent.model_dump(mode="json"),
            "cart_mandate": cart.model_dump(mode="json"),
            "receipt": receipt.model_dump(mode="json"),
            "vendor_acknowledgement": vendor_ack,
            "negotiation_summary": neg.summary,
            "payment_method": payment_method,
            "payment_mode": self.payment_stack.mode,
            "payment_note": self.payment_stack.note,
        }

    @staticmethod
    def _audit(intent, cart: CartMandate, receipt, vendor_ack, neg) -> dict[str, Any]:
        return {
            "lane": intent.lane,
            "ap2": {
                "intent_mandate": intent.model_dump(mode="json"),
                "cart_mandate": cart.model_dump(mode="json"),
                "receipt": receipt.model_dump(mode="json") if receipt else None,
                "vendor_acknowledgement": vendor_ack,
            },
            "negotiation": {
                "agreed": neg.agreed,
                "agreed_vendor_id": neg.agreed_vendor_id,
                "agreed_rate": neg.agreed_rate,
                "summary": neg.summary,
            },
            "customer_quote": {
                "total_rate": cart.customer_price,
                "margin_percentage": cart.margin_percentage,
            },
            "recommended_vendor": {"vendor_id": cart.vendor_id},
            "hitl": {"requires_approval": cart.status != MandateStatus.executed},
        }
