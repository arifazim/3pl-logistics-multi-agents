import pytest
from runtime.agent_system import AgentSystem


@pytest.mark.asyncio
async def test_load_planning_produces_real_load_plan():
    """Load planning is now backed by LoadPlanningAgent (VRP), not a future-work stub."""
    agent_system = AgentSystem()
    result = await agent_system.execute_agent_workflow(
        "load_planning",
        {
            "orders": [
                {
                    "order_id": "O1",
                    "pickup_warehouse": "Tracy",
                    "delivery_location": "Fremont",
                    "pallet_count": 10,
                    "weight_lbs": 5000,
                    "priority": "standard",
                    "time_window_start": "2026-07-01T08:00:00",
                    "time_window_end": "2026-07-01T18:00:00",
                    "sla_tier": "standard",
                },
                {
                    "order_id": "O2",
                    "pickup_warehouse": "Tracy",
                    "delivery_location": "Fremont",
                    "pallet_count": 6,
                    "weight_lbs": 3000,
                    "priority": "urgent",
                    "time_window_start": "2026-07-01T08:00:00",
                    "time_window_end": "2026-07-01T14:00:00",
                    "sla_tier": "express",
                },
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
            "planning_horizon_hours": 24,
        },
    )

    assert result["workflow"] == "load_planning"
    assert result["solver"] in {"ortools", "heuristic"}

    # A real load plan is produced for the single driver serving both Tracy orders.
    assert len(result["load_plans"]) == 1
    plan = result["load_plans"][0]
    assert plan["driver_id"] == "D1"
    assert plan["total_pallets"] == 16
    assert plan["total_distance_miles"] > 0

    # Two same-lane orders (Tracy -> Fremont) yield a consolidation opportunity.
    assert len(result["consolidation_opportunities"]) == 1
    consolidation = result["consolidation_opportunities"][0]
    assert consolidation["shared_warehouse"] == "Tracy"
    assert consolidation["shared_destination"] == "Fremont"
    assert set(consolidation["orders"]) == {"O1", "O2"}
    assert consolidation["estimated_savings_usd"] > 0

    assert result["metrics"]["total_orders"] == 2


@pytest.mark.asyncio
async def test_load_planning_no_orders_returns_empty_plan():
    """With no orders, the agent returns an empty (but well-formed) plan, not a crash."""
    agent_system = AgentSystem()
    result = await agent_system.execute_agent_workflow(
        "load_planning",
        {"orders": [], "drivers": [], "planning_horizon_hours": 24},
    )
    assert result["workflow"] == "load_planning"
    assert result["load_plans"] == []
    assert result["metrics"]["total_orders"] == 0
