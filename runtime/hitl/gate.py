"""Human-in-the-loop gate — not an agent.

Escalates when automated approval is unsafe. Humans review via dashboard queue.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

DEFAULT_MARGIN_FLOOR_PCT = 12.0
DEFAULT_HIGH_VALUE_THRESHOLD = 10_000.0


@dataclass
class HitlDecision:
    requires_approval: bool
    reasons: List[str]
    queue_payload: Optional[Dict[str, Any]]


def evaluate_hitl(
    *,
    margin_pct: float,
    load_value: float,
    compliance_passed: bool,
    vendor_text_flagged: bool = False,
    margin_floor: float = DEFAULT_MARGIN_FLOOR_PCT,
    high_value_threshold: float = DEFAULT_HIGH_VALUE_THRESHOLD,
) -> HitlDecision:
    reasons: List[str] = []

    if margin_pct < margin_floor:
        reasons.append(f"Low margin protection violation: {margin_pct:.2f}% < {margin_floor}%")
    if load_value >= high_value_threshold:
        reasons.append(f"High-value load: ${load_value:,.2f} >= ${high_value_threshold:,.2f}")
    if not compliance_passed:
        reasons.append("Compliance check failed")
    if vendor_text_flagged:
        reasons.append("Vendor text flagged by sanitizer — possible prompt injection")

    requires = len(reasons) > 0
    payload = None
    if requires:
        payload = {
            "status": "pending_human_approval",
            "reasons": reasons,
            "margin_pct": margin_pct,
            "load_value": load_value,
        }

    return HitlDecision(requires_approval=requires, reasons=reasons, queue_payload=payload)
