import pytest
from runtime.tools.vendor_scorer import VendorScorer

@pytest.mark.asyncio
async def test_vendor_scoring():
    scorer = VendorScorer()
    score_data = await scorer.score_vendor("V001", "Tracy->Fremont")
    assert 0 <= score_data["final_score"] <= 100
    assert "reliability_score" in score_data
    assert "cost_score" in score_data

@pytest.mark.asyncio
async def test_vendor_ranking():
    scorer = VendorScorer()
    rankings = await scorer.rank_vendors("Tracy->Fremont")
    assert len(rankings) > 0
    # Verify sorted by score (descending)
    for i in range(len(rankings) - 1):
        assert rankings[i]["final_score"] >= rankings[i+1]["final_score"]
