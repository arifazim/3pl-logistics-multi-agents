"""Payment rails for the AP2 demo — Mock (default), Stripe (test mode), Plaid (Sandbox).

Safety model (mirrors the ALLOW_OFFLINE_AGENT pattern in quotation_decision_agent.py):
- The DEFAULT is always MockProcessor — no network, deterministic, safe for CI/tests.
- Real rails are used ONLY when `ALLOW_LIVE_PAYMENTS=1` is explicitly set AND keys exist.
- Live credentials are HARD-BLOCKED: a `sk_live_*` Stripe key or `PLAID_ENV=production`
  raises immediately. This is a fake-payment demo; it must never touch real money.
- A charge may only be executed against an APPROVED Cart Mandate; the amount comes from
  the mandate, never recomputed here; the idempotency key is the cart mandate id.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from runtime.commerce.mandates import CartMandate, PaymentReceipt


class PaymentError(RuntimeError):
    pass


def _ensure_chargeable(cart: CartMandate) -> None:
    if not cart.is_approved:
        raise PaymentError(
            f"Cart mandate {cart.mandate_id} is '{cart.status.value}', not 'approved' — "
            "refusing to charge. Human authorization (Cart Mandate approval) is required."
        )


# ── Funding source (Plaid) ────────────────────────────────────────────────────

class FundingSourceProvider(Protocol):
    name: str

    def describe(self, for_ach: bool = False) -> Optional[dict[str, Any]]:
        """Return a funding-source descriptor for the payment method, or None."""
        ...


class MockFundingProvider:
    name = "mock"

    def describe(self, for_ach: bool = False) -> Optional[dict[str, Any]]:
        d: dict[str, Any] = {
            "provider": "mock",
            "institution": "Sandbox Bank",
            "account_mask": "0000",
            "verified": True,
            "funding_type": "ach" if for_ach else "card",
        }
        if for_ach:
            d["stripe_bank_account_token"] = "btok_mock_sandbox"
        return d


class PlaidFundingProvider:
    """Plaid Sandbox funding-source verification (lazy import; sandbox only).

    When `emit_stripe_token=True`, it also mints a Stripe bank-account token via Plaid's
    `/processor/stripe/bank_account_token/create` — the ACH funding source Stripe charges
    against (no card). Sandbox only; no real money.
    """

    name = "plaid"

    def __init__(self, client_id: str, secret: str, env: str = "sandbox", emit_stripe_token: bool = False):
        if env == "production":
            raise PaymentError("PLAID_ENV=production is blocked in this demo — use sandbox.")
        self.client_id, self.secret, self.env = client_id, secret, env
        self.emit_stripe_token = emit_stripe_token

    def describe(self, for_ach: Optional[bool] = None) -> Optional[dict[str, Any]]:
        emit_token = self.emit_stripe_token if for_ach is None else for_ach
        try:
            import plaid
            from plaid.api import plaid_api
            from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
            from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
            from plaid.model.products import Products
            from plaid.model.accounts_get_request import AccountsGetRequest

            config = plaid.Configuration(
                host=plaid.Environment.Sandbox,
                api_key={"clientId": self.client_id, "secret": self.secret},
            )
            client = plaid_api.PlaidApi(plaid.ApiClient(config))
            pt = client.sandbox_public_token_create(
                SandboxPublicTokenCreateRequest(
                    institution_id="ins_109508", initial_products=[Products("auth")]
                )
            )
            access = client.item_public_token_exchange(
                ItemPublicTokenExchangeRequest(public_token=pt.public_token)
            )
            access_token = access.access_token
            accounts = client.accounts_get(AccountsGetRequest(access_token=access_token))
            acct = accounts.accounts[0]
            descriptor = {
                "provider": "plaid",
                "env": self.env,
                "institution": "First Platypus Bank",
                "account_mask": getattr(acct, "mask", "0000"),
                "account_id": acct.account_id,
                "verified": True,  # the bank account was verified via Plaid
                "funding_type": "bank_account",
            }
            if emit_token:
                # Minting the Stripe token requires the Plaid<->Stripe integration to be
                # enabled on the account. If it isn't, keep the verified bank account and
                # let the charge fall back to card — don't discard the whole verification.
                try:
                    from plaid.model.processor_stripe_bank_account_token_create_request import (
                        ProcessorStripeBankAccountTokenCreateRequest,
                    )
                    tok = client.processor_stripe_bank_account_token_create(
                        ProcessorStripeBankAccountTokenCreateRequest(
                            access_token=access_token, account_id=acct.account_id
                        )
                    )
                    descriptor["stripe_bank_account_token"] = tok.stripe_bank_account_token
                    descriptor["funding_type"] = "ach"
                except Exception as tok_exc:  # noqa: BLE001
                    msg = str(tok_exc)
                    if "INVALID_PRODUCT" in msg or "not enabled for the Stripe" in msg:
                        msg = ("Plaid<->Stripe integration not enabled for these keys — "
                               "enable it at https://plaid.com/docs/auth/partnerships/stripe/")
                    descriptor["stripe_token_error"] = msg[:200]
                    descriptor["ach_available"] = False
            return descriptor
        except Exception as exc:  # noqa: BLE001 — sandbox is best-effort in a demo
            return {"provider": "plaid", "env": self.env, "verified": False, "error": str(exc)}


# ── Payment processors ─────────────────────────────────────────────────────────

class PaymentProcessor(Protocol):
    name: str

    def charge(self, cart: CartMandate, funding_source: Optional[dict[str, Any]] = None) -> PaymentReceipt:
        ...


class MockProcessor:
    """Deterministic in-memory processor — the safe default (no network)."""

    name = "mock"

    def charge(self, cart: CartMandate, funding_source: Optional[dict[str, Any]] = None) -> PaymentReceipt:
        _ensure_chargeable(cart)
        ftype = (funding_source or {}).get("funding_type", "card")
        return PaymentReceipt(
            cart_mandate_id=cart.mandate_id,
            vendor_id=cart.vendor_id,
            amount=cart.agreed_rate,
            currency=cart.currency,
            processor="mock",
            processor_ref=f"mock_{'ach' if ftype == 'ach' else 'pi'}_{cart.mandate_id}",
            funding_source=funding_source,
            status="settled",
            funding_type=ftype,
            stripe_object_type="mock",
        )


class StripeProcessor:
    """Stripe test-mode processor. Transfers to a vendor connected account when mapped,
    otherwise creates a PaymentIntent as a stand-in. Lazy import; test keys only."""

    name = "stripe"

    def __init__(self, api_key: str, vendor_account_map: Optional[dict[str, str]] = None):
        if api_key.startswith("sk_live_"):
            raise PaymentError("Live Stripe key detected — blocked. Use a test key (sk_test_...).")
        self.api_key = api_key
        self.vendor_account_map = vendor_account_map or {}

    def charge(self, cart: CartMandate, funding_source: Optional[dict[str, Any]] = None) -> PaymentReceipt:
        _ensure_chargeable(cart)
        import stripe

        stripe.api_key = self.api_key
        amount_cents = int(round(cart.agreed_rate * 100))
        idempotency = cart.mandate_id  # prevents double-charge on retry
        dest = self.vendor_account_map.get(cart.vendor_id)

        # ACH path: the Plaid-linked bank account is the funding source of record. Stripe
        # deprecated legacy bank-account-token charges, so we settle via the modern
        # us_bank_account PaymentIntent using Stripe's test bank details. On any ACH error
        # we fall back to the card path so the demo never breaks.
        btok = (funding_source or {}).get("stripe_bank_account_token")
        ach_fallback_reason: str | None = None
        if btok:
            try:
                customer = stripe.Customer.create(
                    name="AP2 Demo Payer", email="ap2-demo@example.com",
                    metadata={"cart_mandate_id": cart.mandate_id, "plaid_token": btok[:24]},
                    idempotency_key=f"cust_{idempotency}",
                )
                pm = stripe.PaymentMethod.create(
                    type="us_bank_account",
                    us_bank_account={
                        "account_number": "000123456789",   # Stripe test account (succeeds)
                        "routing_number": "110000000",
                        "account_holder_type": "individual",
                        "account_type": "checking",
                    },
                    billing_details={"name": "AP2 Demo Payer", "email": "ap2-demo@example.com"},
                )
                pi_kwargs: dict[str, Any] = dict(
                    amount=amount_cents, currency=cart.currency.lower(),
                    customer=customer.id, payment_method=pm.id,
                    payment_method_types=["us_bank_account"], confirm=True,
                    payment_method_options={"us_bank_account": {"verification_method": "automatic"}},
                    mandate_data={"customer_acceptance": {"type": "offline"}},
                    metadata={"cart_mandate_id": cart.mandate_id, "vendor_id": cart.vendor_id,
                              "shipment_id": cart.shipment_id},
                )
                kind = "ach_payment_intent"
                if dest:
                    pi_kwargs["transfer_data"] = {"destination": dest}
                    kind = "ach_destination_charge"
                obj = stripe.PaymentIntent.create(**pi_kwargs, idempotency_key=idempotency)
                # ACH via manual entry needs micro-deposit verification. In test mode the
                # standard amounts [32, 45] confirm it instantly, advancing to "processing".
                if getattr(obj, "status", "") == "requires_action":
                    try:
                        obj = stripe.PaymentIntent.verify_microdeposits(obj.id, amounts=[32, 45])
                    except Exception:  # noqa: BLE001 — leave it in requires_action if this fails
                        pass
                return PaymentReceipt(
                    cart_mandate_id=cart.mandate_id, vendor_id=cart.vendor_id,
                    amount=cart.agreed_rate, currency=cart.currency, processor="stripe",
                    processor_ref=obj.id, funding_source=funding_source,
                    status=getattr(obj, "status", "unknown"),  # ACH: "processing" then succeeds
                    stripe_object_type=kind, vendor_destination=dest, funding_type="ach",
                )
            except Exception as ach_exc:  # noqa: BLE001 — degrade to card, keep the demo alive
                ach_fallback_reason = str(ach_exc)[:200]

        # A confirmed test-mode PaymentIntent using the built-in test card. When the vendor
        # has a mapped Connect account, this becomes a DESTINATION CHARGE so the funds route
        # to the carrier (the vendor genuinely "receives" the sandbox payment).
        kwargs: dict[str, Any] = dict(
            amount=amount_cents,
            currency=cart.currency.lower(),
            payment_method="pm_card_visa",
            payment_method_types=["card"],
            confirm=True,
            metadata={"cart_mandate_id": cart.mandate_id, "vendor_id": cart.vendor_id,
                      "shipment_id": cart.shipment_id},
        )
        kind = "payment_intent"
        if dest:
            kwargs["transfer_data"] = {"destination": dest}
            kind = "destination_charge"

        obj = stripe.PaymentIntent.create(**kwargs, idempotency_key=idempotency)

        return PaymentReceipt(
            cart_mandate_id=cart.mandate_id,
            vendor_id=cart.vendor_id,
            amount=cart.agreed_rate,
            currency=cart.currency,
            processor="stripe",
            processor_ref=obj.id,
            funding_source=funding_source,
            status=getattr(obj, "status", "unknown"),  # "succeeded" in test mode
            stripe_object_type=kind,
            vendor_destination=dest,
            funding_type="card",
            ach_fallback_reason=ach_fallback_reason,
        )


# ── Factory (safety guard lives here) ──────────────────────────────────────────

@dataclass
class PaymentStack:
    processor: PaymentProcessor
    funding_provider: FundingSourceProvider
    mode: str  # "mock" | "live_sandbox"
    note: str | None = None


def _parse_vendor_map(raw: str) -> dict[str, str]:
    # Format: "V001=acct_123,V002=acct_456"
    out: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def get_payment_stack() -> PaymentStack:
    """Return the payment stack, defaulting to the safe MockProcessor.

    Real (sandbox) rails require ALLOW_LIVE_PAYMENTS=1 AND valid test/sandbox creds.
    Live credentials are hard-blocked regardless.
    """
    stripe_key = os.getenv("STRIPE_API_KEY", "")
    plaid_env = os.getenv("PLAID_ENV", "sandbox")

    # Hard blocks — never proceed with live credentials, even by accident.
    if stripe_key.startswith("sk_live_"):
        raise PaymentError("Live Stripe key (sk_live_*) detected — blocked. This is a test-only demo.")
    if plaid_env == "production":
        raise PaymentError("PLAID_ENV=production detected — blocked. Use sandbox.")

    if os.getenv("ALLOW_LIVE_PAYMENTS") != "1" or not stripe_key:
        return PaymentStack(MockProcessor(), MockFundingProvider(), mode="mock")

    # Live requested — ensure the Stripe SDK is actually importable. If not, degrade to
    # mock (never 500) and tell the operator how to fix it.
    try:
        import stripe  # noqa: F401
    except ImportError:
        return PaymentStack(
            MockProcessor(), MockFundingProvider(), mode="mock",
            note="Stripe SDK not installed — run `uv sync` (stripe is a core dependency). Using MockProcessor.",
        )

    processor = StripeProcessor(
        api_key=stripe_key,
        vendor_account_map=_parse_vendor_map(os.getenv("STRIPE_VENDOR_ACCOUNT_MAP", "")),
    )
    plaid_id, plaid_secret = os.getenv("PLAID_CLIENT_ID"), os.getenv("PLAID_SECRET")
    # PAYMENT_METHOD=ach → fund via a Plaid-linked bank account (Stripe bank-account token).
    use_ach = os.getenv("PAYMENT_METHOD", "card").lower() == "ach"
    funding: FundingSourceProvider = (
        PlaidFundingProvider(plaid_id, plaid_secret, env=plaid_env, emit_stripe_token=use_ach)
        if plaid_id and plaid_secret
        else MockFundingProvider()
    )
    return PaymentStack(processor, funding, mode="live_sandbox")
