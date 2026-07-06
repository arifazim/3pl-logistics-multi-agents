from mcp_servers.pl3_server.data import CUSTOMER_RATES, EVAL_SHIPMENTS


def test_eval_shipments_include_100_deterministic_cases():
    assert len(EVAL_SHIPMENTS) == 100
    assert EVAL_SHIPMENTS[0]["shipment_id"] == "EVAL-001"
    assert EVAL_SHIPMENTS[-1]["shipment_id"] == "EVAL-100"


def test_eval_shipments_use_supported_lanes_and_sla_tiers():
    lanes = {sample["lane"] for sample in EVAL_SHIPMENTS}
    sla_tiers = {sample["sla_tier"] for sample in EVAL_SHIPMENTS}

    # Every eval lane must be a lane the pricing engine actually supports.
    assert lanes.issubset(set(CUSTOMER_RATES.keys()))
    assert sla_tiers == {"standard", "express"}
