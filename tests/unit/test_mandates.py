"""Unit tests for the AP2 mandate layer + payment guards (no network)."""

import pytest

from runtime.commerce.mandates import (
    MandateStatus,
    approve_cart_mandate,
    build_cart_mandate,
    build_intent_mandate,
)
from runtime.commerce.payments import (
    MockProcessor,
    PaymentError,
    StripeProcessor,
    get_payment_stack,
)


def _intent(cap=400.0):
    return build_intent_mandate(
        shipment_id="SHP-1", lane="Tracy->Fremont", weight_lbs=1000, max_amount=cap
    )


def test_intent_mandate_has_id_and_content_hash():
    im = _intent()
    assert im.mandate_id.startswith("intent_")
    assert im.status == MandateStatus.issued
    assert len(im.content_hash) == 64  # sha256 hex


def test_cart_mandate_chains_to_intent_and_hashes():
    im = _intent()
    cm = build_cart_mandate(
        intent=im, vendor_id="V002", vendor_name="FalconFreight",
        agreed_rate=320.0, customer_price=373.87, margin_percentage=14.4,
    )
    assert cm.intent_mandate_id == im.mandate_id
    assert cm.status == MandateStatus.pending_approval
    assert not cm.is_approved
    assert len(cm.content_hash) == 64


def test_cart_mandate_rejects_rate_over_intent_cap():
    im = _intent(cap=300.0)
    with pytest.raises(ValueError, match="exceeds intent max_amount"):
        build_cart_mandate(
            intent=im, vendor_id="V002", vendor_name="FalconFreight",
            agreed_rate=350.0, customer_price=400.0, margin_percentage=12.5,
        )


def test_approve_cart_mandate_stamps_authorization():
    im = _intent()
    cm = build_cart_mandate(
        intent=im, vendor_id="V002", vendor_name="FalconFreight",
        agreed_rate=320.0, customer_price=373.87, margin_percentage=14.4,
    )
    approve_cart_mandate(cm, approver="dispatcher", reasons=["High-value load"])
    assert cm.is_approved
    assert cm.approved_by == "dispatcher"
    assert cm.approved_at is not None


def test_mock_processor_refuses_unapproved_cart():
    im = _intent()
    cm = build_cart_mandate(
        intent=im, vendor_id="V002", vendor_name="FalconFreight",
        agreed_rate=320.0, customer_price=373.87, margin_percentage=14.4,
    )
    with pytest.raises(PaymentError, match="not 'approved'"):
        MockProcessor().charge(cm)


def test_mock_processor_charges_approved_cart():
    im = _intent()
    cm = build_cart_mandate(
        intent=im, vendor_id="V002", vendor_name="FalconFreight",
        agreed_rate=320.0, customer_price=373.87, margin_percentage=14.4,
    )
    approve_cart_mandate(cm, approver="auto_policy")
    receipt = MockProcessor().charge(cm)
    assert receipt.processor == "mock"
    assert receipt.amount == 320.0
    assert receipt.cart_mandate_id == cm.mandate_id


def test_get_payment_stack_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("ALLOW_LIVE_PAYMENTS", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    stack = get_payment_stack()
    assert stack.mode == "mock"
    assert stack.processor.name == "mock"


def test_get_payment_stack_hard_blocks_live_stripe_key(monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_PAYMENTS", "1")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_live_should_be_blocked")
    with pytest.raises(PaymentError, match="Live Stripe key"):
        get_payment_stack()


def test_get_payment_stack_hard_blocks_plaid_production(monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_PAYMENTS", "1")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_ok")
    monkeypatch.setenv("PLAID_ENV", "production")
    with pytest.raises(PaymentError, match="production"):
        get_payment_stack()


def test_stripe_processor_rejects_live_key_directly():
    with pytest.raises(PaymentError, match="Live Stripe key"):
        StripeProcessor(api_key="sk_live_nope")
