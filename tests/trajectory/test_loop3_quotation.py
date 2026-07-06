import pytest
from runtime.loops.loop3_two_sided_quotation import run_two_sided_quotation_loop


@pytest.fixture(autouse=True)
def offline_agent(monkeypatch):
    monkeypatch.setenv("ALLOW_OFFLINE_AGENT", "1")


@pytest.mark.asyncio
async def test_loop3_two_sided_quotation():
    report = await run_two_sided_quotation_loop()
    assert len(report.runs) == 2
    assert report.all_margins_above_floor
    assert report.avg_margin_pct >= 12.0
    for run in report.runs:
        assert run.vendor_cost > 0
        assert run.customer_price > run.vendor_cost
