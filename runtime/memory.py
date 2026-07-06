"""Agentic Memory — Day 4 concept: state persistence across interactions.

Three memory scopes:

1. InSessionMemory  — per-request tool-call state (already existed as DecisionState).
   Extended here to be addressable by session_id so multi-turn conversations work.

2. ShipmentHistoryStore — persists completed quotation results keyed by shipment_id.
   Survives restarts when MEMORY_BACKEND=file (default: in-memory for dev).
   Answers questions like "what did we quote for EVAL-042 last time?"

3. AgentContextBuffer — sliding window of recent decisions fed back to the agent
   as 'memory context' in the system prompt. Implements the classic
   agent memory pattern: summarise past, inject into new request.

Design constraints:
- No external database required for dev/test (in-memory dict default)
- File-backed mode for Cloud Run (uses /tmp — ephemeral but survives within instance)
- Thread-safe (asyncio.Lock)
- Bounded: max MAX_HISTORY entries to prevent unbounded growth
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Config ────────────────────────────────────────────────────────────────────
MAX_HISTORY    = int(os.getenv("MEMORY_MAX_HISTORY", "200"))
MEMORY_BACKEND = os.getenv("MEMORY_BACKEND", "memory")   # "memory" | "file"
MEMORY_DIR     = Path(os.getenv("MEMORY_DIR", "/tmp/3pl_memory"))


# ── In-Session Memory (per request, keyed by session_id) ─────────────────────

class InSessionMemory:
    """
    Stores the mutable tool-call state for one agent session.
    Keyed by session_id so long-running async runs don't collide.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def set(self, session_id: str, key: str, value: Any) -> None:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {}
            self._sessions[session_id][key] = value

    async def get(self, session_id: str, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._sessions.get(session_id, {}).get(key, default)

    async def get_session(self, session_id: str) -> dict[str, Any]:
        async with self._lock:
            return dict(self._sessions.get(session_id, {}))

    async def clear_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def all_session_ids(self) -> list[str]:
        async with self._lock:
            return list(self._sessions.keys())


# ── Shipment History Store (cross-request persistence) ───────────────────────

class ShipmentHistoryStore:
    """
    Persists completed quotation payloads keyed by shipment_id.

    In memory mode: OrderedDict (LRU-style eviction at MAX_HISTORY).
    In file mode: each record written to MEMORY_DIR/{shipment_id}.json.
    """

    def __init__(self) -> None:
        self._store: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        if MEMORY_BACKEND == "file":
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    async def save(self, shipment_id: str, payload: dict[str, Any]) -> None:
        record = {
            **payload,
            "_memory_saved_at": datetime.now(timezone.utc).isoformat(),
            "_shipment_id": shipment_id,
        }
        async with self._lock:
            self._store[shipment_id] = record
            # Evict oldest if over limit
            while len(self._store) > MAX_HISTORY:
                self._store.popitem(last=False)

        if MEMORY_BACKEND == "file":
            path = MEMORY_DIR / f"{shipment_id}.json"
            path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

    async def get(self, shipment_id: str) -> dict[str, Any] | None:
        async with self._lock:
            if shipment_id in self._store:
                return self._store[shipment_id]

        if MEMORY_BACKEND == "file":
            path = MEMORY_DIR / f"{shipment_id}.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                async with self._lock:
                    self._store[shipment_id] = data
                return data
        return None

    async def recent(self, n: int = 10) -> list[dict[str, Any]]:
        """Return the n most-recently saved records."""
        async with self._lock:
            items = list(self._store.values())
        return items[-n:]

    async def search(self, lane: str | None = None, vendor_id: str | None = None) -> list[dict[str, Any]]:
        """Simple filter — find records matching lane and/or vendor_id."""
        async with self._lock:
            items = list(self._store.values())

        results = []
        for item in items:
            q = item.get("customer_quote") or {}
            rv = item.get("recommended_vendor") or {}
            lane_match   = lane is None or item.get("lane") == lane or q.get("lane") == lane
            vendor_match = vendor_id is None or rv.get("vendor_id") == vendor_id or q.get("selected_vendor_id") == vendor_id
            if lane_match and vendor_match:
                results.append(item)
        return results

    async def stats(self) -> dict[str, Any]:
        """Aggregate stats over stored history."""
        async with self._lock:
            items = list(self._store.values())

        if not items:
            return {"count": 0}

        margins = [
            (item.get("customer_quote") or {}).get("margin_percentage", 0)
            for item in items
            if (item.get("customer_quote") or {}).get("margin_percentage") is not None
        ]
        hitl_count = sum(
            1 for item in items
            if (item.get("hitl") or {}).get("requires_approval", False)
        )
        lanes: dict[str, int] = {}
        for item in items:
            l = item.get("lane", "unknown")
            lanes[l] = lanes.get(l, 0) + 1

        return {
            "count": len(items),
            "avg_margin_pct": round(sum(margins) / len(margins), 2) if margins else 0,
            "hitl_rate_pct": round(hitl_count / len(items) * 100, 1),
            "lanes": lanes,
        }


# ── Agent Context Buffer (recent decisions → system prompt injection) ─────────

class AgentContextBuffer:
    """
    Maintains a sliding window of recent agent decisions.

    build_context_string() returns a compact summary that can be appended to
    the agent's system instruction so it 'remembers' recent lanes/vendors/margins
    without access to a database.

    This is the canonical 'agentic memory' pattern from Day 4.
    """

    WINDOW = 5  # how many recent decisions to include

    def __init__(self, store: ShipmentHistoryStore) -> None:
        self._store = store

    async def build_context_string(self) -> str:
        recent = await self._store.recent(self.WINDOW)
        if not recent:
            return ""

        lines = ["## Recent Quotation Context (last decisions)"]
        for r in reversed(recent):
            q   = r.get("customer_quote") or {}
            v   = r.get("recommended_vendor") or {}
            h   = r.get("hitl") or {}
            sid = r.get("_shipment_id") or r.get("lane", "?")
            line = (
                f"- {sid}: lane={r.get('lane','?')} vendor={v.get('vendor_id','?')} "
                f"rate=${q.get('total_rate',0):.0f} margin={q.get('margin_percentage',0):.1f}% "
                f"hitl={'yes' if h.get('requires_approval') else 'no'}"
            )
            lines.append(line)
        return "\n".join(lines)


# ── Singleton instances (shared across FastAPI lifetime) ──────────────────────

session_memory  = InSessionMemory()
history_store   = ShipmentHistoryStore()
context_buffer  = AgentContextBuffer(history_store)
