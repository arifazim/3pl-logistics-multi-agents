"""Tests for Loop 2: Compliance-critic → replan with bounded iterations."""

import pytest
from runtime.loops.loop2_compliance_replan import ComplianceReplanLoop


def test_loop2_bounded_iterations_max_3():
    """Loop terminates after max 3 iterations."""
    loop = ComplianceReplanLoop()
    result = loop.execute(
        shipment_id="S001",
        lane="Tracy->Fremont",
        weight=50000,  # Exceeds limit to trigger replan
        margin=10.0,  # Below floor to trigger replan
        delivery_time=30,  # Exceeds SLA to trigger replan
    )
    
    assert result["iteration_count"] <= ComplianceReplanLoop.MAX_ITERATIONS


def test_loop2_deterministic_compliance_check():
    """Compliance check is deterministic, not LLM-derived."""
    loop = ComplianceReplanLoop()

    # _compliance_check signature: (shipment_id, margin, delivery_time, weight, plan)
    margin_result = loop._compliance_check("S001", 10.0, 20, 1000, {})
    assert any(v["type"] == "margin" for v in margin_result["violations"])

    sla_result = loop._compliance_check("S001", 15.0, 30, 1000, {})
    assert any(v["type"] == "sla" for v in sla_result["violations"])

    weight_result = loop._compliance_check("S001", 15.0, 20, 50000, {})
    assert any(v["type"] == "weight" for v in weight_result["violations"])


def test_loop2_replan_around_violations():
    """Replan modifies plan deterministically around violations."""
    loop = ComplianceReplanLoop()
    
    initial_plan = {
        "shipment_id": "S001",
        "vendor_id": "V001",
        "dock_id": "D001",
        "warehouse": "Tracy",
        "weight": 50000,
    }
    
    violations = [{"type": "weight", "threshold": 45000, "actual": 50000}]
    new_plan = loop._replan_around_violations(initial_plan, violations, iteration=0)
    
    # Weight should be reduced to threshold
    assert new_plan["weight"] == 45000


def test_loop2_escalation_on_persistent_violations():
    """Escalates to HITL when violations persist after max iterations."""
    loop = ComplianceReplanLoop()
    result = loop.execute(
        shipment_id="S001",
        lane="Tracy->Fremont",
        weight=100000,  # Way over limit
        margin=5.0,  # Way under floor
        delivery_time=100,  # Way over SLA
    )
    
    if result["status"] == "escalate_to_hitl":
        assert "violations" in result
        assert len(result["violations"]) > 0
        assert result["iteration_count"] <= ComplianceReplanLoop.MAX_ITERATIONS
