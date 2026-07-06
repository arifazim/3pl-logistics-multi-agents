"""Tool handlers — namespaced MCP tools (rate_card, vendor, policy, telemetry, tms)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from .data import (
    CUSTOMER_RATES,
    MARGIN_FLOOR_PCT,
    POLICIES,
    SHIPMENTS,
    TELEMETRY_SNAPSHOT,
    VENDOR_DIRECTORY,
    VENDOR_RATES,
)

WEIGHT_RATE_PER_LB = 0.02  # $0.02/lb above 1000 lb baseline


def _ok(payload: Any) -> str:
    return json.dumps(payload, default=str)


def _weight_surcharge(weight_lbs: float) -> float:
    baseline = 1000.0
    if weight_lbs <= baseline:
        return 0.0
    return round((weight_lbs - baseline) * WEIGHT_RATE_PER_LB, 2)


def rate_card_get_customer_lane(lane: str) -> str:
    """rate_card.get_customer_lane — list price metadata (reference only, not used for margin)."""
    info = CUSTOMER_RATES.get(lane, {"base_rate": 0, "target_margin_pct": MARGIN_FLOOR_PCT})
    return _ok({"lane": lane, **info, "note": "reference_only_not_pricing_basis"})


def rate_card_get_vendor_rates(lane: str) -> str:
    """rate_card.get_vendor_rates — vendor bids for a lane."""
    quotes = [v for v in VENDOR_RATES if v["lane"] == lane]
    return _ok({"lane": lane, "quotes": quotes})


def vendor_list() -> str:
    """vendor.list — active carriers from vendor directory."""
    vendors = [
        {"vendor_id": vid, **{k: v[k] for k in ("name", "reliability_score", "status")}}
        for vid, v in VENDOR_DIRECTORY.items()
    ]
    return _ok({"vendors": vendors})


def vendor_get(vendor_id: str) -> str:
    """vendor.get — carrier dossier from vendor directory."""
    details = VENDOR_DIRECTORY.get(vendor_id)
    if not details:
        return _ok({"error": f"Vendor {vendor_id} not found"})
    return _ok({"vendor_id": vendor_id, **details})


def vendor_rank_for_lane(lane: str, weight_lbs: float = 1000.0) -> str:
    """vendor.rank_for_lane — 70% vendor-directory reliability / 30% cost (includes weight surcharge)."""
    quotes = [v for v in VENDOR_RATES if v["lane"] == lane]
    scored = []
    max_rate = 500.0
    weight_extra = _weight_surcharge(weight_lbs)

    for q in quotes:
        vid = q["vendor_id"]
        directory = VENDOR_DIRECTORY.get(vid, {})
        # Reliability from vendor DIRECTORY (authoritative), not rate card duplicate field
        reliability = float(directory.get("reliability_score", q.get("reliability_score", 50)))
        effective_rate = float(q["rate"]) + weight_extra
        cost_score = 0.0 if effective_rate >= max_rate else ((max_rate - effective_rate) / max_rate) * 100
        final_score = (reliability * 0.7) + (cost_score * 0.3)
        scored.append(
            {
                **q,
                "name": directory.get("name"),
                "reliability_score": reliability,
                "effective_rate": round(effective_rate, 2),
                "weight_surcharge": weight_extra,
                "cost_score": round(cost_score, 2),
                "final_score": round(final_score, 2),
            }
        )
    scored.sort(key=lambda x: x["final_score"], reverse=True)
    return _ok({"lane": lane, "weight_lbs": weight_lbs, "ranked": scored, "selected": scored[0] if scored else None})


def policy_list() -> str:
    """policy.list — Gherkin-backed policies with per-policy comparator op."""
    return _ok({"policies": POLICIES})


def policy_check_compliance(policy_name: str, value: float, shipment_id: str = "UNKNOWN") -> str:
    """policy.check_compliance — gte for margin, lte for SLA/weight."""
    policy = next((p for p in POLICIES if p["name"] == policy_name), None)
    if not policy:
        return _ok({"compliant": False, "reason": "Policy not found", "shipment_id": shipment_id})
    op = policy.get("op", "gte")
    threshold = policy["threshold"]
    if op == "gte":
        compliant = value >= threshold
    elif op == "lte":
        compliant = value <= threshold
    else:
        compliant = False
    return _ok(
        {
            "shipment_id": shipment_id,
            "policy_name": policy_name,
            "op": op,
            "compliant": compliant,
            "threshold": threshold,
            "value": value,
            "rule": policy["rule"],
        }
    )


def telemetry_get_snapshot() -> str:
    """telemetry.get_snapshot — operational KPIs."""
    return _ok(TELEMETRY_SNAPSHOT)


def telemetry_log_event(event_type: str, agent: str, data_json: str = "{}") -> str:
    """telemetry.log_event — structured trace."""
    try:
        data = json.loads(data_json) if data_json else {}
    except json.JSONDecodeError:
        data = {"raw": data_json}
    return _ok(
        {
            "status": "logged",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "agent": agent,
            "data": data,
        }
    )


def tms_list_shipments() -> str:
    """tms.list_shipments — active shipments."""
    return _ok({"shipments": SHIPMENTS})


TOOL_REGISTRY: Dict[str, Callable[..., str]] = {
    "rate_card.get_customer_lane": rate_card_get_customer_lane,
    "rate_card.get_vendor_rates": rate_card_get_vendor_rates,
    "vendor.list": vendor_list,
    "vendor.get": vendor_get,
    "vendor.rank_for_lane": vendor_rank_for_lane,
    "policy.list": policy_list,
    "policy.check_compliance": policy_check_compliance,
    "telemetry.get_snapshot": telemetry_get_snapshot,
    "telemetry.log_event": telemetry_log_event,
    "tms.list_shipments": tms_list_shipments,
}
