# Skill: load_planning

## Purpose
Plan pickups and deliveries across the Tracy / Manteca / Livermore / Fremont / Hayward
warehouse network by solving a Capacitated Vehicle Routing Problem with Time Windows
(CVRPTW).

## Rules
1. Routing is NP-hard — the LLM MUST NOT compute or reorder routes. Always delegate to
   the deterministic `LoadPlanningAgent.optimize_loads` tool (OR-Tools).
2. The solver enforces two capacity dimensions — **pallets** and **weight (lbs)** — per
   driver. No vehicle may exceed either limit.
3. Every delivery must land inside its order's `[time_window_start, time_window_end]`.
   Vehicle routes are bounded by each driver's `[available_start, available_end]`.
4. Orders are clustered by pickup warehouse; each warehouse's stationed drivers form its
   vehicle fleet.
5. The objective is minimum total travel distance (Haversine miles).
6. If OR-Tools is unavailable, or a cluster is infeasible, fall back to the
   nearest-neighbour heuristic — but always label `solver` accordingly.

## Output contract
`{load_plans: [{driver_id, route: [{location, stop_type, order_id, estimated_arrival,
estimated_departure, pallet_count, weight_lbs}], total_distance_miles,
total_duration_hours, total_pallets, total_weight_lbs, utilization_pct}],
consolidation_opportunities: [...], metrics: {...}, solver: "ortools" | "heuristic"}`

## Anti-patterns
- NEVER hand-optimize a route or "improve" the solver's ordering in the LLM.
- NEVER emit a plan where a truck exceeds pallet or weight capacity.
- NEVER schedule a delivery outside its time window — prefer waiting to violating.
- NEVER claim "optimized" output when the heuristic fallback was used.
