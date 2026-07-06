import pytest
from runtime.tools.route_optimizer import RouteOptimizer


@pytest.mark.asyncio
async def test_optimize_route_returns_explicit_stub():
    optimizer = RouteOptimizer()
    shipments = [
        {"id": "S001", "origin": "Tracy", "destination": "Fremont", "pallets": 10},
    ]
    result = await optimizer.optimize_route_stub(shipments)
    assert result["status"] == "stub"
    assert "OR-Tools" in result["future_work"]
    assert result["shipment_count"] == 1
    assert "S001" in result["shipment_ids"]


@pytest.mark.asyncio
async def test_load_planning_workflow_optimizes_orders():
    """The load_planning workflow now runs the real LoadPlanningAgent VRP solver."""
    from runtime.agent_system import AgentSystem

    agent_system = AgentSystem()
    result = await agent_system.execute_agent_workflow(
        "load_planning",
        {
            "orders": [
                {
                    "order_id": "O1",
                    "pickup_warehouse": "Tracy",
                    "delivery_location": "Fremont",
                    "pallet_count": 8,
                    "weight_lbs": 4000,
                    "priority": "standard",
                    "time_window_start": "2026-07-01T08:00:00",
                    "time_window_end": "2026-07-01T18:00:00",
                    "sla_tier": "standard",
                }
            ],
            "drivers": [
                {
                    "driver_id": "D1",
                    "current_location": "Tracy",
                    "available_start": "2026-07-01T06:00:00",
                    "available_end": "2026-07-01T20:00:00",
                    "max_pallets": 24,
                    "max_weight_lbs": 45000,
                    "current_route": [],
                }
            ],
        },
    )
    assert result["workflow"] == "load_planning"
    assert result["solver"] in {"ortools", "heuristic"}
    assert len(result["load_plans"]) == 1
    assert result["load_plans"][0]["total_pallets"] == 8
