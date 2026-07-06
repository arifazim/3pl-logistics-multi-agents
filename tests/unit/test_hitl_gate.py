from runtime.hitl.gate import evaluate_hitl


def test_hitl_not_required_when_all_clear():
    decision = evaluate_hitl(margin_pct=15.0, load_value=5000, compliance_passed=True)
    assert decision.requires_approval is False
    assert decision.reasons == []


def test_hitl_margin_violation():
    decision = evaluate_hitl(margin_pct=9.0, load_value=5000, compliance_passed=True)
    assert decision.requires_approval is True
    assert any("margin" in r.lower() for r in decision.reasons)


def test_hitl_high_value_load():
    decision = evaluate_hitl(margin_pct=15.0, load_value=15000, compliance_passed=True)
    assert decision.requires_approval is True
    assert any("high-value" in r.lower() for r in decision.reasons)


def test_hitl_vendor_text_flagged():
    decision = evaluate_hitl(
        margin_pct=15.0, load_value=5000, compliance_passed=True, vendor_text_flagged=True,
    )
    assert decision.requires_approval is True
    assert any("sanitizer" in r.lower() or "injection" in r.lower() for r in decision.reasons)
