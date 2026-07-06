"""Tests for Loop 3: Meta-loop (spec → build → eval → kaizen → spec)."""

import pytest
from runtime.loops.loop3_kaizen import KaizenMetaLoop


def test_loop3_bounded_iterations_max_3():
    """Meta-loop terminates after max 3 iterations."""
    loop = KaizenMetaLoop()
    result = loop.execute()
    assert result["iterations"] <= KaizenMetaLoop.MAX_ITERATIONS


def test_loop3_deterministic_eval_via_pytest():
    """Eval uses pytest (deterministic), not LLM judgment."""
    loop = KaizenMetaLoop()
    result = loop._run_trajectory_eval()
    assert "status" in result
    assert "failures" in result
    assert isinstance(result["failures"], list)


def test_loop3_kaizen_log_populated():
    """Kaizen log is populated with real eval failures."""
    from runtime.loops.loop3_kaizen import KAIZEN_LOG
    loop = KaizenMetaLoop()
    failures = [{"test": "test_vendor_quote_flow", "detail": "AssertionError", "timestamp": "2024-01-01T00:00:00"}]
    classified = {"vendor": 1}
    loop._append_kaizen_log(failures, classified, [], iteration=0)
    assert KAIZEN_LOG.exists()
    content = KAIZEN_LOG.read_text()
    assert "Kaizen Cycle 1" in content
    assert "test_vendor_quote_flow" in content


def test_loop3_auto_refinement_returns_result():
    """execute() returns auto_refined key."""
    loop = KaizenMetaLoop()
    result = loop.execute()
    assert "auto_refined" in result
    assert "refinements_applied" in result
