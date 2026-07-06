import math

import pytest
from runtime.tools.quotation_engine import QuotationEngine, MARGIN_FLOOR_PCT


def test_margin_from_selected_vendor_not_cheapest():
    """V002 wins on reliability despite not being the cheapest — margin uses its cost."""
    engine = QuotationEngine()
    ranking = engine.mcp.rank_vendors("Tracy->Fremont")
    cheapest_rate = min(v["rate"] for v in ranking["ranked"])
    quote = engine.calculate_customer_quote("Tracy->Fremont", sla_tier="standard")

    assert quote["selected_vendor_id"] == "V002"
    # V002 is selected on reliability even though a cheaper vendor exists on this lane.
    assert quote["vendor_cost_base"] == 329.0
    assert quote["vendor_cost_base"] > cheapest_rate
    assert quote["pricing_basis"] == "selected_vendor_cost"

    expected_price = math.ceil(329.0 / (1 - MARGIN_FLOOR_PCT / 100) * 100) / 100
    assert quote["total_rate"] == expected_price
    assert quote["margin_percentage"] >= MARGIN_FLOOR_PCT
    assert engine.validate_margin(quote["total_rate"], quote["vendor_cost"])


def test_margin_is_floor_not_rate_card_tautology():
    """Rate card says target 15% but pricing uses 12% floor on vendor cost."""
    engine = QuotationEngine()
    quote = engine.calculate_customer_quote("Tracy->Fremont")
    assert quote["target_margin_reference"] == 15
    assert quote["margin_percentage"] == pytest.approx(12.0, abs=0.1)


def test_customer_quote_margin_floor():
    engine = QuotationEngine()
    quote = engine.calculate_customer_quote("Manteca->Hayward", sla_tier="standard")
    assert quote["margin_percentage"] >= MARGIN_FLOOR_PCT
    # V002 tops the ranking on this lane (highest reliability and lowest rate).
    assert quote["selected_vendor_id"] == "V002"


def test_weight_increases_vendor_cost():
    engine = QuotationEngine()
    light = engine.calculate_customer_quote("Tracy->Fremont", weight=1000)
    heavy = engine.calculate_customer_quote("Tracy->Fremont", weight=5000)
    assert heavy["vendor_cost"] > light["vendor_cost"]


def test_margin_validation():
    engine = QuotationEngine()
    assert engine.validate_margin(customer_price=450, vendor_cost=380) is True
    assert engine.validate_margin(customer_price=400, vendor_cost=380) is False
