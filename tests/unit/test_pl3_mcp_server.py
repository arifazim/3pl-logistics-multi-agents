import pytest
from mcp_servers.pl3_server.handlers import TOOL_REGISTRY


def test_mcp_tool_registry_namespaced():
    assert "rate_card.get_vendor_rates" in TOOL_REGISTRY
    assert "vendor.rank_for_lane" in TOOL_REGISTRY
    assert "policy.check_compliance" in TOOL_REGISTRY


def test_vendor_rank_selects_reliability_over_cheapest():
    import json

    raw = TOOL_REGISTRY["vendor.rank_for_lane"](lane="Tracy->Fremont", weight_lbs=1000)
    data = json.loads(raw)
    assert data["selected"]["vendor_id"] == "V002"


def test_policy_sla_uses_lte():
    import json

    ok = json.loads(TOOL_REGISTRY["policy.check_compliance"](policy_name="sla_compliance", value=20))
    bad = json.loads(TOOL_REGISTRY["policy.check_compliance"](policy_name="sla_compliance", value=26))
    assert ok["compliant"] is True
    assert bad["compliant"] is False


def test_weight_increases_effective_rate():
    import json

    light = json.loads(TOOL_REGISTRY["vendor.rank_for_lane"](lane="Tracy->Fremont", weight_lbs=1000))
    heavy = json.loads(TOOL_REGISTRY["vendor.rank_for_lane"](lane="Tracy->Fremont", weight_lbs=5000))
    assert heavy["selected"]["weight_surcharge"] > light["selected"]["weight_surcharge"]
