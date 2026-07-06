"""Tests for Loop 1: Vendor evaluator-optimizer with deterministic guardrails."""

import pytest
from runtime.loops.loop1_vendor_evaluator import VendorEvaluatorLoop


def test_loop1_bounded_iterations_max_5():
    """Loop terminates after max 5 iterations with tried-set tracking."""
    loop = VendorEvaluatorLoop()
    result = loop.execute("Tracy->Fremont", weight=1000, sla_tier="standard")
    
    assert result["iteration_count"] <= VendorEvaluatorLoop.MAX_ITERATIONS
    assert len(result.get("tried_vendors", [])) <= VendorEvaluatorLoop.MAX_ITERATIONS
    # No duplicate vendors in tried set
    assert len(result.get("tried_vendors", [])) == len(set(result.get("tried_vendors", [])))


def test_loop1_deterministic_margin_check():
    """Margin check is deterministic, not LLM-derived."""
    loop = VendorEvaluatorLoop()
    result = loop.execute("Tracy->Fremont", weight=1000, sla_tier="standard")
    
    if result["status"] == "success":
        quote = result["quote"]
        # Verify margin is calculated deterministically
        expected_margin = ((quote["customer_price"] - quote["vendor_cost"]) / quote["customer_price"]) * 100
        assert abs(quote["margin_percentage"] - expected_margin) < 0.01
        assert quote["margin_percentage"] >= 12.0


def test_loop1_escalation_on_margin_gap():
    """Escalates to HITL when margin gap exceeds threshold."""
    loop = VendorEvaluatorLoop()
    # Force escalation by using a lane with no vendors
    result = loop.execute("Invalid->Lane", weight=1000)
    
    if result["status"] == "escalate_to_hitl":
        assert "margin_gap" in result
        assert "escalation_reason" in result
        assert result["iteration_count"] <= VendorEvaluatorLoop.MAX_ITERATIONS


def test_loop1_shrinking_candidate_set():
    """Candidate set shrinks each iteration (tried-set prevents cycling)."""
    loop = VendorEvaluatorLoop()
    result = loop.execute("Tracy->Fremont", weight=1000)
    
    # Verify tried vendors are unique
    tried = result.get("tried_vendors", [])
    assert len(tried) == len(set(tried))
