"""Tests for the real OR-Tools CVRPTW solver in LoadPlanningAgent.

These exercise the actual OR-Tools routing model (capacity + time windows) against
the Tracy/Manteca/Livermore/Fremont/Hayward warehouse network. If OR-Tools is not
installed the agent falls back to the heuristic, so capacity/window assertions that
depend on the solver are skipped in that case.
"""

from datetime import datetime

import pytest

from runtime.agents.load_planning_agent import (
    Driver,
    LoadPlanningAgent,
    Order,
    Warehouse,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 1, hour, minute)


def _agent_with(orders, drivers) -> LoadPlanningAgent:
    agent = LoadPlanningAgent()
    agent.set_orders(orders)
    agent.set_drivers(drivers)
    return agent


@pytest.mark.asyncio
async def test_ortools_is_used_when_available():
    agent = _agent_with(
        [Order("O1", Warehouse.TRACY, "Fremont", 4, 2000, "standard", _dt(8), _dt(18), "standard")],
        [Driver("D1", Warehouse.TRACY, _dt(6), _dt(20), 24, 45000, [])],
    )
    result = await agent.optimize_loads(24)
    if not agent._ortools_available:
        pytest.skip("OR-Tools not installed; heuristic fallback in use")
    assert result["solver"] == "ortools"
    assert len(result["load_plans"]) == 1


@pytest.mark.asyncio
async def test_pallet_capacity_forces_second_vehicle():
    """24 pallets across same-warehouse orders must split when a truck caps at 16."""
    orders = [
        Order("O1", Warehouse.TRACY, "Fremont", 10, 5000, "standard", _dt(8), _dt(18), "standard"),
        Order("O2", Warehouse.TRACY, "Hayward", 8, 4000, "standard", _dt(8), _dt(18), "standard"),
        Order("O3", Warehouse.TRACY, "Fremont", 6, 3000, "standard", _dt(8), _dt(18), "standard"),
    ]
    drivers = [
        Driver("D1", Warehouse.TRACY, _dt(6), _dt(20), 16, 45000, []),
        Driver("D2", Warehouse.TRACY, _dt(6), _dt(20), 16, 45000, []),
    ]
    agent = _agent_with(orders, drivers)
    result = await agent.optimize_loads(24)
    if not agent._ortools_available:
        pytest.skip("OR-Tools not installed; heuristic fallback in use")

    assert result["solver"] == "ortools"
    # No single truck may exceed its 16-pallet capacity.
    assert all(lp["total_pallets"] <= 16 for lp in result["load_plans"])
    # All 24 pallets are still delivered.
    assert sum(lp["total_pallets"] for lp in result["load_plans"]) == 24
    # Splitting requires two vehicles.
    assert len(result["load_plans"]) == 2


@pytest.mark.asyncio
async def test_delivery_time_windows_are_respected():
    """Each delivery must arrive within its order's [start, end] window."""
    orders = [
        Order("O1", Warehouse.TRACY, "Fremont", 4, 2000, "urgent", _dt(8), _dt(12), "express"),
        Order("O2", Warehouse.TRACY, "Fremont", 4, 2000, "standard", _dt(14), _dt(18), "standard"),
    ]
    drivers = [Driver("D1", Warehouse.TRACY, _dt(6), _dt(20), 24, 45000, [])]
    agent = _agent_with(orders, drivers)
    result = await agent.optimize_loads(24)
    if not agent._ortools_available:
        pytest.skip("OR-Tools not installed; heuristic fallback in use")

    windows = {"O1": (_dt(8), _dt(12)), "O2": (_dt(14), _dt(18))}
    for plan in result["load_plans"]:
        for stop in plan["route"]:
            if stop["stop_type"] != "delivery":
                continue
            arrival = datetime.fromisoformat(stop["estimated_arrival"])
            start, end = windows[stop["order_id"]]
            assert start <= arrival <= end, f"{stop['order_id']} arrived {arrival} outside window"


@pytest.mark.asyncio
async def test_multi_warehouse_orders_are_planned_independently():
    """Orders across different warehouses each get their stationed driver."""
    orders = [
        Order("O1", Warehouse.TRACY, "Fremont", 5, 2500, "standard", _dt(8), _dt(18), "standard"),
        Order("O2", Warehouse.MANTECA, "Hayward", 5, 2500, "standard", _dt(8), _dt(18), "standard"),
    ]
    drivers = [
        Driver("D1", Warehouse.TRACY, _dt(6), _dt(20), 24, 45000, []),
        Driver("D2", Warehouse.MANTECA, _dt(6), _dt(20), 24, 45000, []),
    ]
    agent = _agent_with(orders, drivers)
    result = await agent.optimize_loads(24)

    assert result["metrics"]["total_orders"] == 2
    driver_ids = {lp["driver_id"] for lp in result["load_plans"]}
    assert driver_ids == {"D1", "D2"}
