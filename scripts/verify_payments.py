"""Verify the Plaid + Stripe integration with a fake (sandbox/test) transaction.

Usage:
    # Mock mode (no keys needed) — proves the wiring:
    uv run python scripts/verify_payments.py

    # Live sandbox — copy .env.example to .env, fill TEST/SANDBOX keys, then:
    #   ALLOW_LIVE_PAYMENTS=1, STRIPE_API_KEY=sk_test_..., PLAID_* (sandbox)
    uv run python scripts/verify_payments.py

Safety: live Stripe keys (sk_live_) and PLAID_ENV=production are hard-blocked upstream.
This never moves real money.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency). Does not overwrite already-set vars."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val


def _mask(v: str | None) -> str:
    if not v:
        return "(unset)"
    return f"{v[:7]}…{v[-2:]}" if len(v) > 10 else "SET"


async def main() -> int:
    _load_dotenv()

    from runtime.commerce.payments import get_payment_stack
    from runtime.agents.commerce_agent import CommerceAgent

    print("=" * 64)
    print("AP2 payment verification")
    print("=" * 64)
    print(f"ALLOW_LIVE_PAYMENTS = {os.getenv('ALLOW_LIVE_PAYMENTS') or '(unset)'}")
    print(f"STRIPE_API_KEY      = {_mask(os.getenv('STRIPE_API_KEY'))}")
    print(f"PLAID_ENV           = {os.getenv('PLAID_ENV', 'sandbox')}")
    print(f"PLAID_CLIENT_ID     = {_mask(os.getenv('PLAID_CLIENT_ID'))}")
    print(f"STRIPE_VENDOR_MAP   = {os.getenv('STRIPE_VENDOR_ACCOUNT_MAP') or '(unset)'}")

    try:
        stack = get_payment_stack()
    except Exception as exc:  # e.g. live-key hard block
        print(f"\n[BLOCKED] {exc}")
        return 1

    print(f"\nResolved payment mode : {stack.mode}")
    print(f"Processor             : {stack.processor.name}")
    print(f"Funding provider      : {stack.funding_provider.name}")

    if stack.mode == "mock":
        print("\n(Mock mode — set ALLOW_LIVE_PAYMENTS=1 + test/sandbox keys in .env for a real "
              "sandbox transaction.)")

    # 1) Verify the funding source (Plaid sandbox when configured, else mock descriptor).
    print("\n--- Funding source (Plaid) ---")
    funding = stack.funding_provider.describe()
    print(json.dumps(funding, indent=2))

    # 2) Run the full AP2 settle flow — negotiate, approve, charge, vendor receives.
    print("\n--- AP2 settle (vendor receives payment) ---")
    agent = CommerceAgent()
    result = await agent.settle(
        lane="Tracy->Fremont", weight_lbs=1000, sla_tier="standard",
        shipment_id="VERIFY-1", human_approved=True, approver="verify_script", persist=False,
    )
    print(f"status          : {result['status']}")
    if result["status"] != "settled":
        print(json.dumps(result, indent=2))
        return 2
    receipt = result["receipt"]
    print(f"processor       : {receipt['processor']}")
    print(f"processor_ref   : {receipt['processor_ref']}")
    print(f"charge status   : {receipt.get('status')}")
    print(f"charge type     : {receipt.get('stripe_object_type', 'mock')}")
    print(f"amount          : ${receipt['amount']:.2f} {receipt['currency']}")
    print(f"vendor ack      : {result['vendor_acknowledgement']['message']}")

    ok = receipt["processor"] == stack.processor.name
    print("\n" + ("PASS ✅  integration verified." if ok else "FAIL ❌"))
    if stack.mode == "live_sandbox" and receipt["processor"] == "stripe":
        print("Check the Stripe TEST dashboard → Payments for this PaymentIntent.")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
