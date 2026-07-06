"""AP2 mandate layer (simulated JSON mandates).

Models the Agent Payments Protocol authorization chain:

    IntentMandate  — "agent, you may spend up to max_amount on this shipment"
    CartMandate    — "this exact vendor at this exact rate" (human-approved)
    PaymentReceipt — proof the vendor/merchant received the (sandbox) payment

These are structured JSON objects with a sha256 `content_hash` for tamper-evidence.
They deliberately DO NOT carry cryptographic verifiable-credential signatures — this is
an honest simulation of AP2's *flow and authorization model*, not its non-repudiation
crypto. Signed VCs (Ed25519/JWT) are a documented future upgrade.

Authorization rules enforced here:
- A Cart Mandate's `agreed_rate` may never exceed the Intent Mandate's `max_amount`.
- A payment may only be executed against an `approved` Cart Mandate (see payments.py).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def content_hash(fields: dict[str, Any]) -> str:
    """Deterministic sha256 over the canonical JSON of the given fields."""
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MandateStatus(str, Enum):
    issued = "issued"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"


class IntentMandate(BaseModel):
    """Buyer's spend authorization for one shipment."""

    mandate_id: str = Field(default_factory=lambda: _new_id("intent"))
    shipment_id: str
    lane: str
    weight_lbs: float = Field(gt=0)
    sla_tier: str = "standard"
    max_amount: float = Field(gt=0)  # hard spend cap
    currency: str = "USD"
    constraints: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    status: MandateStatus = MandateStatus.issued
    content_hash: str = ""

    model_config = {"extra": "allow"}

    def core(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "shipment_id": self.shipment_id,
            "lane": self.lane,
            "weight_lbs": self.weight_lbs,
            "sla_tier": self.sla_tier,
            "max_amount": self.max_amount,
            "currency": self.currency,
            "constraints": self.constraints,
        }


class CartMandate(BaseModel):
    """The specific vendor + rate the buyer agrees to, chained to an Intent Mandate."""

    mandate_id: str = Field(default_factory=lambda: _new_id("cart"))
    intent_mandate_id: str
    shipment_id: str
    lane: str
    vendor_id: str
    vendor_name: str | None = None
    agreed_rate: float = Field(gt=0)
    customer_price: float = Field(gt=0)
    margin_percentage: float
    currency: str = "USD"
    created_at: str = Field(default_factory=_now_iso)
    status: MandateStatus = MandateStatus.pending_approval
    approved_by: str | None = None
    approved_at: str | None = None
    hitl_reasons: list[str] = Field(default_factory=list)
    content_hash: str = ""

    model_config = {"extra": "allow"}

    def core(self) -> dict[str, Any]:
        return {
            "mandate_id": self.mandate_id,
            "intent_mandate_id": self.intent_mandate_id,
            "shipment_id": self.shipment_id,
            "lane": self.lane,
            "vendor_id": self.vendor_id,
            "agreed_rate": self.agreed_rate,
            "customer_price": self.customer_price,
            "currency": self.currency,
        }

    @property
    def is_approved(self) -> bool:
        return self.status == MandateStatus.approved


class PaymentReceipt(BaseModel):
    """Proof the vendor/merchant received the (sandbox) payment."""

    receipt_id: str = Field(default_factory=lambda: _new_id("rcpt"))
    cart_mandate_id: str
    vendor_id: str
    amount: float = Field(gt=0)
    currency: str = "USD"
    processor: str  # "mock" | "stripe"
    processor_ref: str  # PaymentIntent / Transfer id (or mock id)
    funding_source: dict[str, Any] | None = None  # Plaid descriptor, if any
    status: str = "settled"
    created_at: str = Field(default_factory=_now_iso)

    model_config = {"extra": "allow"}


# ── Builders / transitions ────────────────────────────────────────────────────

def build_intent_mandate(
    *,
    shipment_id: str,
    lane: str,
    weight_lbs: float,
    max_amount: float,
    sla_tier: str = "standard",
    constraints: dict[str, Any] | None = None,
) -> IntentMandate:
    im = IntentMandate(
        shipment_id=shipment_id,
        lane=lane,
        weight_lbs=weight_lbs,
        sla_tier=sla_tier,
        max_amount=max_amount,
        constraints=constraints or {},
    )
    im.content_hash = content_hash(im.core())
    return im


def build_cart_mandate(
    *,
    intent: IntentMandate,
    vendor_id: str,
    vendor_name: str | None,
    agreed_rate: float,
    customer_price: float,
    margin_percentage: float,
) -> CartMandate:
    """Build a Cart Mandate chained to an Intent Mandate.

    Raises ValueError if the agreed rate exceeds the intent's spend cap — the buyer
    agent must never commit to more than the user authorized.
    """
    if agreed_rate > intent.max_amount:
        raise ValueError(
            f"agreed_rate ${agreed_rate:.2f} exceeds intent max_amount "
            f"${intent.max_amount:.2f} for {intent.shipment_id}"
        )
    cm = CartMandate(
        intent_mandate_id=intent.mandate_id,
        shipment_id=intent.shipment_id,
        lane=intent.lane,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        agreed_rate=agreed_rate,
        customer_price=customer_price,
        margin_percentage=margin_percentage,
        currency=intent.currency,
    )
    cm.content_hash = content_hash(cm.core())
    return cm


def approve_cart_mandate(cart: CartMandate, approver: str, reasons: list[str] | None = None) -> CartMandate:
    """Human-in-the-loop authorization — the AP2 Cart Mandate signature step."""
    cart.status = MandateStatus.approved
    cart.approved_by = approver
    cart.approved_at = _now_iso()
    if reasons:
        cart.hitl_reasons = reasons
    return cart


def reject_cart_mandate(cart: CartMandate, reasons: list[str] | None = None) -> CartMandate:
    cart.status = MandateStatus.rejected
    if reasons:
        cart.hitl_reasons = reasons
    return cart
