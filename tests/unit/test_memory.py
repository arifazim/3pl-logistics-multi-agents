"""Tests for Day 4 — Agentic Memory: InSessionMemory, ShipmentHistoryStore, AgentContextBuffer."""

import pytest
from runtime.memory import InSessionMemory, ShipmentHistoryStore, AgentContextBuffer


# ── InSessionMemory ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_set_get():
    mem = InSessionMemory()
    await mem.set("sess-1", "ranking", {"vendor": "V002"})
    result = await mem.get("sess-1", "ranking")
    assert result == {"vendor": "V002"}


@pytest.mark.asyncio
async def test_session_default_returns_none():
    mem = InSessionMemory()
    result = await mem.get("sess-x", "ranking", default=None)
    assert result is None


@pytest.mark.asyncio
async def test_session_clear():
    mem = InSessionMemory()
    await mem.set("sess-2", "quote", {"total_rate": 400})
    await mem.clear_session("sess-2")
    result = await mem.get("sess-2", "quote")
    assert result is None


@pytest.mark.asyncio
async def test_session_isolation():
    """Different session IDs must not share state."""
    mem = InSessionMemory()
    await mem.set("sess-a", "key", "value-a")
    await mem.set("sess-b", "key", "value-b")
    assert await mem.get("sess-a", "key") == "value-a"
    assert await mem.get("sess-b", "key") == "value-b"


# ── ShipmentHistoryStore ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_save_and_get():
    store = ShipmentHistoryStore()
    payload = {
        "lane": "Tracy->Fremont",
        "customer_quote": {"total_rate": 380.23, "margin_percentage": 13.5},
        "recommended_vendor": {"vendor_id": "V002"},
        "hitl": {"requires_approval": False},
    }
    await store.save("SHP-001", payload)
    record = await store.get("SHP-001")
    assert record is not None
    assert record["lane"] == "Tracy->Fremont"
    assert record["_shipment_id"] == "SHP-001"
    assert "_memory_saved_at" in record


@pytest.mark.asyncio
async def test_history_get_missing():
    store = ShipmentHistoryStore()
    result = await store.get("DOES-NOT-EXIST")
    assert result is None


@pytest.mark.asyncio
async def test_history_recent_ordering():
    store = ShipmentHistoryStore()
    for i in range(5):
        await store.save(f"SHP-{i:03d}", {"lane": f"Lane-{i}", "customer_quote": {"total_rate": 300 + i * 10, "margin_percentage": 12 + i}, "hitl": {"requires_approval": False}})
    recent = await store.recent(3)
    assert len(recent) == 3
    # Most recent should be SHP-004
    ids = [r["_shipment_id"] for r in recent]
    assert "SHP-004" in ids


@pytest.mark.asyncio
async def test_history_stats():
    store = ShipmentHistoryStore()
    await store.save("S1", {"lane": "Tracy->Fremont", "customer_quote": {"total_rate": 380, "margin_percentage": 14.0}, "recommended_vendor": {"vendor_id": "V002"}, "hitl": {"requires_approval": False}})
    await store.save("S2", {"lane": "Tracy->Fremont", "customer_quote": {"total_rate": 420, "margin_percentage": 16.0}, "recommended_vendor": {"vendor_id": "V001"}, "hitl": {"requires_approval": True}})
    stats = await store.stats()
    assert stats["count"] == 2
    assert stats["avg_margin_pct"] == 15.0
    assert stats["hitl_rate_pct"] == 50.0


@pytest.mark.asyncio
async def test_history_search_by_lane():
    store = ShipmentHistoryStore()
    await store.save("TF-1", {"lane": "Tracy->Fremont", "customer_quote": {"total_rate": 380, "margin_percentage": 13}, "hitl": {"requires_approval": False}})
    await store.save("MH-1", {"lane": "Manteca->Hayward", "customer_quote": {"total_rate": 410, "margin_percentage": 14}, "hitl": {"requires_approval": False}})
    tf_results = await store.search(lane="Tracy->Fremont")
    assert all(r["lane"] == "Tracy->Fremont" for r in tf_results)
    assert len(tf_results) >= 1


@pytest.mark.asyncio
async def test_history_max_eviction():
    """Store should not grow beyond MAX_HISTORY."""
    from runtime.memory import MAX_HISTORY
    store = ShipmentHistoryStore()
    # Write more than the limit
    for i in range(MAX_HISTORY + 5):
        await store.save(f"EVICT-{i:04d}", {"lane": "Tracy->Fremont", "customer_quote": {"total_rate": 300, "margin_percentage": 12}, "hitl": {"requires_approval": False}})
    stats = await store.stats()
    assert stats["count"] <= MAX_HISTORY


# ── AgentContextBuffer ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_buffer_empty():
    store = ShipmentHistoryStore()
    buf = AgentContextBuffer(store)
    ctx = await buf.build_context_string()
    assert ctx == ""


@pytest.mark.asyncio
async def test_context_buffer_has_content():
    store = ShipmentHistoryStore()
    await store.save("CTX-001", {
        "lane": "Tracy->Fremont",
        "customer_quote": {"total_rate": 380, "margin_percentage": 14.0},
        "recommended_vendor": {"vendor_id": "V002"},
        "hitl": {"requires_approval": False},
    })
    buf = AgentContextBuffer(store)
    ctx = await buf.build_context_string()
    assert "Tracy->Fremont" in ctx
    assert "CTX-001" in ctx
    assert "V002" in ctx
