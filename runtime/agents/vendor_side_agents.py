"""Vendor-side A2A agents — each represents a real carrier.

Each VendorAgent:
- Receives a QuoteRequest (lane, weight, sla_tier, target_price)
- Responds with a QuoteOffer (rate, counter_offer, accept/reject)
- Runs up to MAX_ROUNDS of counter-offer negotiation
- Has distinct personality: margin floor, concession rate, reliability threshold

A2ANegotiator orchestrates the broker ↔ vendor exchange.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from runtime.commerce.mandates import PaymentReceipt

# ── Data contracts ──────────────────────────────────────────────────────────

@dataclass
class QuoteRequest:
    lane: str
    weight_lbs: float
    sla_tier: str
    shipment_id: str
    target_price: float          # broker's target — vendor tries to beat this
    max_rounds: int = 3


@dataclass
class QuoteOffer:
    vendor_id: str
    vendor_name: str
    offered_rate: float
    accepted: bool               # vendor accepts broker's target_price
    counter_offer: float | None  # vendor's counter if not accepted
    round_num: int
    reason: str
    reliability_score: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class NegotiationResult:
    shipment_id: str
    lane: str
    rounds: list[dict[str, Any]]
    agreed_vendor_id: str | None
    agreed_rate: float | None
    agreed: bool
    all_offers: list[QuoteOffer]
    summary: str


# ── Base vendor agent ────────────────────────────────────────────────────────

class VendorAgent:
    """Base class for carrier-side A2A agents."""

    vendor_id: str
    vendor_name: str
    base_rate_by_lane: dict[str, float]
    reliability_score: float
    margin_floor_pct: float      # vendor won't go below this margin
    max_concession_pct: float    # max % they'll drop per round
    sla_multipliers: dict[str, float]

    def respond(self, request: QuoteRequest, round_num: int = 1) -> QuoteOffer:
        """Produce a quote offer for the given request and round."""
        base = self.base_rate_by_lane.get(request.lane)
        if base is None:
            return QuoteOffer(
                vendor_id=self.vendor_id, vendor_name=self.vendor_name,
                offered_rate=0, accepted=False, counter_offer=None,
                round_num=round_num, reason="No rate for this lane",
                reliability_score=self.reliability_score,
            )

        # Apply SLA multiplier
        sla_mult = self.sla_multipliers.get(request.sla_tier, 1.0)
        # Weight surcharge: $0.02/lb above 1000 lb baseline
        weight_extra = max(0.0, (request.weight_lbs - 1000) * 0.02)
        base_cost = round((base + weight_extra) * sla_mult, 2)

        # Each successive round: vendor concedes by max_concession_pct
        concession = 1.0 - (self.max_concession_pct / 100) * (round_num - 1)
        concession = max(concession, 1.0 - (self.max_concession_pct / 100) * 2)  # cap total discount
        offered_rate = round(base_cost * concession, 2)

        # Can we accept the broker's target?
        # Vendor accepts if target >= offered_rate (they make money)
        accepted = request.target_price >= offered_rate
        counter = None if accepted else offered_rate

        reason = (
            f"Accepted at ${request.target_price:.2f} (our cost ${offered_rate:.2f})"
            if accepted
            else f"Counter ${offered_rate:.2f} — below our floor of ${round(base_cost * (1 - self.margin_floor_pct/100), 2):.2f}"
        )
        return QuoteOffer(
            vendor_id=self.vendor_id, vendor_name=self.vendor_name,
            offered_rate=offered_rate, accepted=accepted,
            counter_offer=counter, round_num=round_num,
            reason=reason, reliability_score=self.reliability_score,
        )

    def acknowledge_payment(self, receipt: "PaymentReceipt") -> dict[str, Any]:
        """Merchant side of AP2: confirm the carrier received the (sandbox) payment."""
        return {
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "acknowledged": True,
            "receipt_id": receipt.receipt_id,
            "amount": receipt.amount,
            "currency": receipt.currency,
            "processor": receipt.processor,
            "processor_ref": receipt.processor_ref,
            "message": f"{self.vendor_name} confirms receipt of ${receipt.amount:.2f} {receipt.currency}.",
        }


# ── Concrete vendor agents ────────────────────────────────────────────────────

class SwiftTransportAgent(VendorAgent):
    vendor_id = "V001"
    vendor_name = "SwiftTransport"
    base_rate_by_lane = {"Tracy->Fremont": 300.0, "Manteca->Hayward": 330.0}
    reliability_score = 92.0
    margin_floor_pct = 8.0
    max_concession_pct = 4.0
    sla_multipliers = {"standard": 1.0, "express": 1.12}


class FalconFreightAgent(VendorAgent):
    vendor_id = "V002"
    vendor_name = "FalconFreight"
    base_rate_by_lane = {"Tracy->Fremont": 320.0, "Manteca->Hayward": 345.0}
    reliability_score = 95.0
    margin_floor_pct = 10.0    # Higher reliability — less willing to discount
    max_concession_pct = 2.5
    sla_multipliers = {"standard": 1.0, "express": 1.15}


class EcoHaulAgent(VendorAgent):
    vendor_id = "V003"
    vendor_name = "EcoHaul"
    base_rate_by_lane = {"Tracy->Fremont": 285.0, "Manteca->Hayward": 350.0}
    reliability_score = 88.0
    margin_floor_pct = 6.0     # More aggressive — willing to compete on price
    max_concession_pct = 6.0
    sla_multipliers = {"standard": 1.0, "express": 1.10}


# Registry: vendor_id → agent instance
VENDOR_AGENTS: dict[str, VendorAgent] = {
    "V001": SwiftTransportAgent(),
    "V002": FalconFreightAgent(),
    "V003": EcoHaulAgent(),
}


# ── A2A Negotiator ────────────────────────────────────────────────────────────

class A2ANegotiator:
    """
    Broker-side orchestrator for A2A vendor negotiation.

    Protocol (quote_request / counter_offer):
    1. Broker sends QuoteRequest to all eligible vendors simultaneously
    2. Vendors respond with QuoteOffer (accept or counter)
    3. If no acceptance: broker adjusts target slightly upward (within margin floor)
       and re-sends to vendors who countered
    4. Repeat up to MAX_ROUNDS
    5. Select best accepted offer (highest reliability among acceptances)

    Guardrails:
    - Broker never breaches 12% margin floor when adjusting target
    - MAX_ROUNDS bounded (default 3)
    - All offers logged for audit trail
    """

    BROKER_MARGIN_FLOOR_PCT = 12.0
    MAX_ROUNDS = 3

    def __init__(self, vendor_agents: dict[str, VendorAgent] | None = None):
        self.agents = vendor_agents or VENDOR_AGENTS

    def negotiate(
        self,
        lane: str,
        weight_lbs: float,
        sla_tier: str,
        vendor_cost_from_mcp: float,    # the MCP-ranked best vendor's cost
        shipment_id: str = "UNKNOWN",
    ) -> NegotiationResult:
        """
        Run multi-round A2A negotiation.

        target_price starts at vendor_cost_from_mcp (what MCP says the winner charges).
        Broker nudges it up by 2% per round if no one accepts, staying within margin floor.
        """
        # Calculate broker's max buyable price: vendor_cost / (1 - margin_floor)
        max_broker_target = round(vendor_cost_from_mcp / (1 - self.BROKER_MARGIN_FLOOR_PCT / 100), 2)
        target = vendor_cost_from_mcp   # start tight — see if any vendor will match

        # Only invite vendors who serve this lane
        eligible = {
            vid: agent for vid, agent in self.agents.items()
            if lane in agent.base_rate_by_lane
        }
        if not eligible:
            return NegotiationResult(
                shipment_id=shipment_id, lane=lane, rounds=[], agreed_vendor_id=None,
                agreed_rate=None, agreed=False, all_offers=[],
                summary=f"No vendors serve lane {lane}",
            )

        all_offers: list[QuoteOffer] = []
        rounds_log: list[dict[str, Any]] = []
        active_vendors = dict(eligible)  # shrinks each round
        agreed_vendor_id = None
        agreed_rate = None

        for round_num in range(1, self.MAX_ROUNDS + 1):
            round_offers: list[QuoteOffer] = []

            for vid, agent in active_vendors.items():
                req = QuoteRequest(
                    lane=lane, weight_lbs=weight_lbs, sla_tier=sla_tier,
                    shipment_id=shipment_id, target_price=target,
                    max_rounds=self.MAX_ROUNDS,
                )
                offer = agent.respond(req, round_num=round_num)
                round_offers.append(offer)
                all_offers.append(offer)

            acceptances = [o for o in round_offers if o.accepted]
            counters = [o for o in round_offers if not o.accepted]

            rounds_log.append({
                "round": round_num,
                "broker_target": target,
                "offers": [
                    {"vendor_id": o.vendor_id, "vendor_name": o.vendor_name,
                     "offered_rate": o.offered_rate, "accepted": o.accepted,
                     "counter_offer": o.counter_offer, "reason": o.reason}
                    for o in round_offers
                ],
                "acceptances": len(acceptances),
                "counters": len(counters),
            })

            if acceptances:
                # Pick highest reliability among those who accepted
                best = max(acceptances, key=lambda o: o.reliability_score)
                agreed_vendor_id = best.vendor_id
                agreed_rate = best.offered_rate
                break

            if not counters:
                break  # Everyone declined — no point continuing

            # Nudge target up by 2% for next round, capped at max_broker_target
            target = min(round(target * 1.02, 2), max_broker_target)
            # Only keep vendors who countered (others already declined cleanly)
            active_vendors = {o.vendor_id: active_vendors[o.vendor_id] for o in counters if o.vendor_id in active_vendors}

        agreed = agreed_vendor_id is not None
        summary = (
            f"Agreed: {agreed_vendor_id} at ${agreed_rate:.2f} after {len(rounds_log)} round(s)"
            if agreed
            else f"No agreement after {len(rounds_log)} round(s) — escalating to HITL"
        )
        return NegotiationResult(
            shipment_id=shipment_id, lane=lane, rounds=rounds_log,
            agreed_vendor_id=agreed_vendor_id, agreed_rate=agreed_rate,
            agreed=agreed, all_offers=all_offers, summary=summary,
        )
