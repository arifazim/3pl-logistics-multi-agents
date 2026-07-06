"""Verify StripeProcessor builds the correct test-mode charge (no network).

Injects a fake `stripe` module so we can assert the exact PaymentIntent parameters
(confirmed test card, idempotency key, destination charge) without any API call.
"""

import sys
import types

import pytest

from runtime.commerce.mandates import approve_cart_mandate, build_cart_mandate, build_intent_mandate
from runtime.commerce.payments import StripeProcessor


class _FakePI:
    def __init__(self, **kwargs):
        self.id = "pi_test_123"
        self.status = "succeeded"


def _install_fake_stripe(monkeypatch):
    captured = {}

    fake = types.ModuleType("stripe")

    class PaymentIntent:
        @staticmethod
        def create(**kwargs):
            captured["kwargs"] = kwargs
            return _FakePI(**kwargs)

    fake.PaymentIntent = PaymentIntent
    fake.api_key = None
    monkeypatch.setitem(sys.modules, "stripe", fake)
    return captured


def _approved_cart(rate=320.0):
    intent = build_intent_mandate(shipment_id="SHP-S", lane="Tracy->Fremont", weight_lbs=1000, max_amount=500)
    cart = build_cart_mandate(
        intent=intent, vendor_id="V002", vendor_name="FalconFreight",
        agreed_rate=rate, customer_price=400.0, margin_percentage=20.0,
    )
    approve_cart_mandate(cart, approver="test")
    return cart


def test_stripe_charge_confirms_test_payment_intent(monkeypatch):
    captured = _install_fake_stripe(monkeypatch)
    receipt = StripeProcessor(api_key="sk_test_abc").charge(_approved_cart())

    kw = captured["kwargs"]
    assert kw["amount"] == 32000  # cents
    assert kw["payment_method"] == "pm_card_visa"
    assert kw["confirm"] is True
    assert kw["idempotency_key"].startswith("cart_")
    assert "transfer_data" not in kw  # no vendor account mapped
    assert receipt.processor == "stripe"
    assert receipt.processor_ref == "pi_test_123"
    assert receipt.status == "succeeded"
    assert receipt.stripe_object_type == "payment_intent"


def test_stripe_charge_routes_to_vendor_connected_account(monkeypatch):
    captured = _install_fake_stripe(monkeypatch)
    proc = StripeProcessor(api_key="sk_test_abc", vendor_account_map={"V002": "acct_test_v002"})
    receipt = proc.charge(_approved_cart())

    assert captured["kwargs"]["transfer_data"] == {"destination": "acct_test_v002"}
    assert receipt.stripe_object_type == "destination_charge"
    assert receipt.vendor_destination == "acct_test_v002"


class _FakeObj:
    def __init__(self, oid, status="processing"):
        self.id = oid
        self.status = status


def _install_fake_stripe_ach(monkeypatch, pi_status="processing"):
    captured = {}
    fake = types.ModuleType("stripe")

    class Customer:
        @staticmethod
        def create(**kwargs):
            captured["customer"] = kwargs
            return _FakeObj("cus_test_1")

    class PaymentMethod:
        @staticmethod
        def create(**kwargs):
            captured["payment_method"] = kwargs
            return _FakeObj("pm_bank_1")

    class PaymentIntent:
        @staticmethod
        def create(**kwargs):
            captured["payment_intent"] = kwargs
            return _FakeObj("pi_ach_1", status=pi_status)

    fake.Customer = Customer
    fake.PaymentMethod = PaymentMethod
    fake.PaymentIntent = PaymentIntent
    fake.api_key = None
    monkeypatch.setitem(sys.modules, "stripe", fake)
    return captured


def test_stripe_ach_uses_us_bank_account_payment_intent(monkeypatch):
    captured = _install_fake_stripe_ach(monkeypatch)
    funding = {"provider": "plaid", "funding_type": "ach", "stripe_bank_account_token": "btok_test_9"}
    receipt = StripeProcessor(api_key="sk_test_abc").charge(_approved_cart(), funding_source=funding)

    # Modern ACH: a us_bank_account PaymentMethod on a PaymentIntent (not the legacy Charge API).
    assert captured["payment_method"]["type"] == "us_bank_account"
    pi = captured["payment_intent"]
    assert pi["payment_method_types"] == ["us_bank_account"]
    assert pi["customer"] == "cus_test_1"
    assert pi["amount"] == 32000
    assert receipt.funding_type == "ach"
    assert receipt.stripe_object_type == "ach_payment_intent"
    assert receipt.processor_ref == "pi_ach_1"


def test_stripe_ach_routes_to_vendor_when_mapped(monkeypatch):
    captured = _install_fake_stripe_ach(monkeypatch)
    funding = {"stripe_bank_account_token": "btok_test_9"}
    proc = StripeProcessor(api_key="sk_test_abc", vendor_account_map={"V002": "acct_test_v002"})
    receipt = proc.charge(_approved_cart(), funding_source=funding)
    assert captured["payment_intent"]["transfer_data"] == {"destination": "acct_test_v002"}
    assert receipt.stripe_object_type == "ach_destination_charge"


def test_stripe_ach_falls_back_to_card_on_error(monkeypatch):
    # ACH raises -> card PaymentIntent path runs, recording the fallback reason.
    fake = types.ModuleType("stripe")

    class Customer:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("ACH unavailable")

    class PaymentIntent:
        @staticmethod
        def create(**kwargs):
            return _FakeObj("pi_card_fallback", status="succeeded")

    fake.Customer = Customer
    fake.PaymentIntent = PaymentIntent
    fake.api_key = None
    monkeypatch.setitem(sys.modules, "stripe", fake)

    funding = {"stripe_bank_account_token": "btok_test_9"}
    receipt = StripeProcessor(api_key="sk_test_abc").charge(_approved_cart(), funding_source=funding)
    assert receipt.funding_type == "card"
    assert receipt.processor_ref == "pi_card_fallback"
    assert "ACH unavailable" in receipt.ach_fallback_reason


def test_stripe_refuses_unapproved_cart(monkeypatch):
    _install_fake_stripe(monkeypatch)
    intent = build_intent_mandate(shipment_id="X", lane="Tracy->Fremont", weight_lbs=1000, max_amount=500)
    cart = build_cart_mandate(
        intent=intent, vendor_id="V002", vendor_name="FalconFreight",
        agreed_rate=320.0, customer_price=400.0, margin_percentage=20.0,
    )  # not approved
    from runtime.commerce.payments import PaymentError

    with pytest.raises(PaymentError):
        StripeProcessor(api_key="sk_test_abc").charge(cart)
