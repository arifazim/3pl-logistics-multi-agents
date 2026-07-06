"""Load Planning Agent — Plan pickups and deliveries across warehouse network.

This agent uses OR-Tools to solve Vehicle Routing Problems (VRP) for:
- Tracy, Manteca, Livermore, Fremont, Hayward warehouse network
- Optimal route consolidation
- Pickup/delivery scheduling
- Driver availability constraints
- Vendor capacity management

Inputs: orders, pallet counts, dock schedules, driver availability, vendor capacity
Outputs: optimized load plans, consolidation opportunities, route suggestions
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from runtime.agy.loader import load_agy
from runtime.skills.loader import load_agent_skills


class Warehouse(Enum):
    TRACY = "Tracy"
    MANTECA = "Manteca"
    LIVERMORE = "Livermore"
    FREMONT = "Fremont"
    HAYWARD = "Hayward"


@dataclass
class Order:
    order_id: str
    pickup_warehouse: Warehouse
    delivery_location: str
    pallet_count: int
    weight_lbs: float
    priority: str  # "urgent", "standard", "low"
    time_window_start: datetime
    time_window_end: datetime
    sla_tier: str


@dataclass
class Driver:
    driver_id: str
    current_location: Warehouse
    available_start: datetime
    available_end: datetime
    max_pallets: int
    max_weight_lbs: float
    current_route: List[str]


@dataclass
class RouteStop:
    location: str
    stop_type: str  # "pickup" or "delivery"
    order_id: str
    estimated_arrival: datetime
    estimated_departure: datetime
    pallet_count: int
    weight_lbs: float


@dataclass
class LoadPlan:
    driver_id: str
    route: List[RouteStop]
    total_distance_miles: float
    total_duration_hours: float
    total_pallets: int
    total_weight_lbs: float
    utilization_pct: float
    consolidation_opportunities: List[str]


@dataclass
class ConsolidationOpportunity:
    orders: List[str]
    shared_warehouse: Warehouse
    shared_destination: str
    combined_pallets: int
    estimated_savings_usd: float


class LoadPlanningAgent:
    """
    Load planning agent using OR-Tools for VRP optimization.

    Solves the Vehicle Routing Problem with Time Windows (VRPTW)
    for the 3PL warehouse network.
    """

    # Routing assumptions shared by the OR-Tools solver and the heuristic fallback.
    AVG_SPEED_MPH = 40.0
    PICKUP_SERVICE_MIN = 30
    DELIVERY_SERVICE_MIN = 45

    # Warehouse coordinates (approximate lat/lon for distance calculation)
    WAREHOUSE_COORDS = {
        Warehouse.TRACY: (37.7397, -121.4252),
        Warehouse.MANTECA: (37.8233, -121.2163),
        Warehouse.LIVERMORE: (37.6819, -121.7680),
        Warehouse.FREMONT: (37.5485, -121.9886),
        Warehouse.HAYWARD: (37.6688, -122.0808),
    }

    AGY_NAME = "load_planning"

    def __init__(self):
        self._drivers: List[Driver] = []
        self._orders: List[Order] = []
        self._distance_matrix: Dict[Tuple[str, str], float] = {}
        # ── Agent harness: load .agy spec + skill contracts ──────────────────
        self._agy = load_agy(self.AGY_NAME)
        self._skill_context = load_agent_skills("load_planning_agent")
        # Try to import OR-Tools
        try:
            from ortools.constraint_solver import routing_enums_pb2
            from ortools.constraint_solver import pywrapcp

            self._ortools_available = True
        except ImportError:
            self._ortools_available = False
            print("Warning: OR-Tools not available. Using heuristic fallback.")

    def set_drivers(self, drivers: List[Driver]) -> None:
        """Set available drivers for planning."""
        self._drivers = drivers

    def set_orders(self, orders: List[Order]) -> None:
        """Set orders to be planned."""
        self._orders = orders

    async def optimize_loads(self, planning_horizon_hours: int = 24) -> Dict[str, Any]:
        """
        Generate optimized load plans for all orders.

        Returns:
            Dictionary with load plans, consolidation opportunities, and metrics.
        """
        if not self._orders:
            return {
                "load_plans": [],
                "consolidation_opportunities": [],
                "metrics": {
                    "total_orders": 0,
                    "total_distance": 0,
                    "avg_utilization": 0,
                },
            }

        # Build distance matrix
        self._build_distance_matrix()

        # Generate load plans
        if self._ortools_available:
            load_plans = await self._solve_with_ortools()
        else:
            load_plans = self._solve_heuristic()

        # Find consolidation opportunities
        consolidations = self._find_consolidation_opportunities()

        # Calculate metrics
        total_distance = sum(lp.total_distance_miles for lp in load_plans)
        avg_utilization = (
            sum(lp.utilization_pct for lp in load_plans) / len(load_plans)
            if load_plans
            else 0
        )

        return {
            "load_plans": [self._serialize_load_plan(lp) for lp in load_plans],
            "consolidation_opportunities": [
                self._serialize_consolidation(c) for c in consolidations
            ],
            "metrics": {
                "total_orders": len(self._orders),
                "total_drivers_used": len(load_plans),
                "total_distance_miles": round(total_distance, 2),
                "avg_utilization_pct": round(avg_utilization, 1),
                "planning_horizon_hours": planning_horizon_hours,
            },
            "solver": "ortools" if self._ortools_available else "heuristic",
        }

    def _build_distance_matrix(self) -> None:
        """Build distance matrix between all locations.

        Warehouses are keyed by their string value (not the Warehouse enum) so the
        matrix is consistent with delivery-location strings and the route builder,
        which look up distances by string location names.
        """
        locations = [wh.value for wh in self.WAREHOUSE_COORDS.keys()]

        # Add delivery locations from orders
        delivery_locations = set()
        for order in self._orders:
            delivery_locations.add(order.delivery_location)

        all_locations = list(locations) + list(delivery_locations)

        for loc1 in all_locations:
            for loc2 in all_locations:
                if loc1 == loc2:
                    self._distance_matrix[(loc1, loc2)] = 0
                else:
                    self._distance_matrix[(loc1, loc2)] = self._calculate_distance(
                        loc1, loc2
                    )

    def _calculate_distance(self, loc1: str, loc2: str) -> float:
        """Calculate distance between two locations using Haversine formula."""
        # Get coordinates
        coord1 = self._get_coordinates(loc1)
        coord2 = self._get_coordinates(loc2)

        if not coord1 or not coord2:
            # Fallback to approximate distance
            return 50.0

        lat1, lon1 = coord1
        lat2, lon2 = coord2

        # Haversine formula
        R = 3959.0  # Earth's radius in miles
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(
            math.radians(lat1)
        ) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) * math.sin(dlon / 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c

        return distance

    def _get_coordinates(self, location: str) -> Optional[Tuple[float, float]]:
        """Get coordinates for a location."""
        # Check if it's a warehouse
        for wh, coords in self.WAREHOUSE_COORDS.items():
            if wh.value == location:
                return coords

        # For delivery locations, use approximate coordinates based on warehouse
        # In production, this would query a geocoding service
        if "Fremont" in location:
            return (37.5485, -121.9886)
        elif "Hayward" in location:
            return (37.6688, -122.0808)
        elif "Livermore" in location:
            return (37.6819, -121.7680)
        elif "Tracy" in location:
            return (37.7397, -121.4252)
        elif "Manteca" in location:
            return (37.8233, -121.2163)

        return None

    async def _solve_with_ortools(self) -> List[LoadPlan]:
        """Solve the Capacitated VRP with Time Windows (CVRPTW) with OR-Tools.

        Orders are clustered by pickup warehouse. Each warehouse is a depot whose
        stationed drivers form the vehicle fleet; the model enforces pallet and
        weight capacities plus per-order delivery time windows and minimizes total
        travel distance. Clusters with no stationed driver or no feasible solution
        fall back to the nearest-neighbour heuristic so a plan is always returned.
        """
        load_plans: List[LoadPlan] = []

        warehouse_orders: Dict[Warehouse, List[Order]] = {}
        for order in self._orders:
            warehouse_orders.setdefault(order.pickup_warehouse, []).append(order)

        used_driver_ids: set[str] = set()
        for warehouse, orders in warehouse_orders.items():
            fleet = [
                d
                for d in self._drivers
                if d.current_location == warehouse
                and d.driver_id not in used_driver_ids
            ]
            cluster_plans: Optional[List[LoadPlan]] = None
            if fleet:
                cluster_plans = self._solve_cluster_cvrptw(warehouse, orders, fleet)

            if cluster_plans is None:
                # No stationed driver or solver found the cluster infeasible: fall back.
                fallback = next(
                    (d for d in self._drivers if d.driver_id not in used_driver_ids),
                    None,
                )
                if fallback is None:
                    continue
                cluster_plans = [
                    self._build_route_for_warehouse(fallback, warehouse, orders)
                ]

            for plan in cluster_plans:
                used_driver_ids.add(plan.driver_id)
            load_plans.extend(cluster_plans)

        return load_plans

    def _solve_cluster_cvrptw(
        self,
        warehouse: Warehouse,
        orders: List[Order],
        fleet: List[Driver],
    ) -> Optional[List[LoadPlan]]:
        """Build and solve one warehouse's CVRPTW. Returns None if no solution found."""
        from ortools.constraint_solver import routing_enums_pb2
        from ortools.constraint_solver import pywrapcp

        # Node 0 is the depot (warehouse); nodes 1..N are order deliveries.
        node_locations = [warehouse.value] + [o.delivery_location for o in orders]
        num_nodes = len(node_locations)
        num_vehicles = len(fleet)

        # Time reference: earliest of any driver start or order window start.
        t0 = min(
            [d.available_start for d in fleet] + [o.time_window_start for o in orders]
        )

        def to_min(dt: datetime) -> int:
            return int(round((dt - t0).total_seconds() / 60.0))

        # Per-node delivery time windows (depot handled via vehicle start/end below).
        node_windows = [(0, 0)]  # placeholder for depot, widened later
        for o in orders:
            node_windows.append(
                (max(0, to_min(o.time_window_start)), to_min(o.time_window_end))
            )

        horizon = (
            max(
                [w[1] for w in node_windows[1:]]
                + [to_min(d.available_end) for d in fleet]
            )
            + self.DELIVERY_SERVICE_MIN
        )
        node_windows[0] = (0, horizon)

        # Demands per node.
        pallet_demand = [0] + [o.pallet_count for o in orders]
        weight_demand = [0] + [int(round(o.weight_lbs)) for o in orders]

        manager = pywrapcp.RoutingIndexManager(num_nodes, num_vehicles, 0)
        routing = pywrapcp.RoutingModel(manager)

        # Arc cost = travel distance in scaled integer miles (minimize total distance).
        def distance_between(from_node: int, to_node: int) -> float:
            return self._distance_matrix.get(
                (node_locations[from_node], node_locations[to_node]),
                self._calculate_distance(
                    node_locations[from_node], node_locations[to_node]
                ),
            )

        def distance_cb(from_index: int, to_index: int) -> int:
            return int(
                round(
                    distance_between(
                        manager.IndexToNode(from_index), manager.IndexToNode(to_index)
                    )
                    * 100
                )
            )

        transit_idx = routing.RegisterTransitCallback(distance_cb)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

        # Capacity dimension: pallets.
        def pallet_cb(from_index: int) -> int:
            return pallet_demand[manager.IndexToNode(from_index)]

        pallet_idx = routing.RegisterUnaryTransitCallback(pallet_cb)
        routing.AddDimensionWithVehicleCapacity(
            pallet_idx, 0, [d.max_pallets for d in fleet], True, "Pallets"
        )

        # Capacity dimension: weight.
        def weight_cb(from_index: int) -> int:
            return weight_demand[manager.IndexToNode(from_index)]

        weight_idx = routing.RegisterUnaryTransitCallback(weight_cb)
        routing.AddDimensionWithVehicleCapacity(
            weight_idx, 0, [int(round(d.max_weight_lbs)) for d in fleet], True, "Weight"
        )

        # Time dimension: travel time + service time at the origin node.
        def time_cb(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            travel_min = int(
                round(distance_between(from_node, to_node) / self.AVG_SPEED_MPH * 60)
            )
            service = (
                self.PICKUP_SERVICE_MIN if from_node == 0 else self.DELIVERY_SERVICE_MIN
            )
            return travel_min + service

        time_idx = routing.RegisterTransitCallback(time_cb)
        routing.AddDimension(time_idx, horizon, horizon, False, "Time")
        time_dim = routing.GetDimensionOrDie("Time")

        # Apply delivery time windows.
        for node in range(1, num_nodes):
            index = manager.NodeToIndex(node)
            start, end = node_windows[node]
            time_dim.CumulVar(index).SetRange(start, min(end, horizon))

        # Apply per-vehicle availability windows at start/end.
        for v, driver in enumerate(fleet):
            start_index = routing.Start(v)
            time_dim.CumulVar(start_index).SetRange(
                max(0, to_min(driver.available_start)), horizon
            )
            end_index = routing.End(v)
            time_dim.CumulVar(end_index).SetRange(
                0, min(to_min(driver.available_end), horizon)
            )

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_params.time_limit.FromSeconds(2)

        solution = routing.SolveWithParameters(search_params)
        if solution is None:
            return None

        return self._extract_load_plans(
            manager,
            routing,
            solution,
            time_dim,
            fleet,
            orders,
            warehouse,
            node_locations,
            t0,
        )

    def _extract_load_plans(
        self,
        manager,
        routing,
        solution,
        time_dim,
        fleet,
        orders,
        warehouse,
        node_locations,
        t0,
    ) -> List[LoadPlan]:
        """Convert an OR-Tools solution into LoadPlan objects (one per used vehicle)."""
        order_by_node = {i + 1: o for i, o in enumerate(orders)}
        load_plans: List[LoadPlan] = []

        for v, driver in enumerate(fleet):
            index = routing.Start(v)
            if routing.IsEnd(solution.Value(routing.NextVar(index))):
                continue  # vehicle unused

            served_orders = [
                order_by_node[manager.IndexToNode(idx)]
                for idx in self._route_node_indices(routing, solution, v)
                if manager.IndexToNode(idx) != 0
            ]

            # Batch pickup at the depot/warehouse.
            depot_min = solution.Value(time_dim.CumulVar(routing.Start(v)))
            route_stops: List[RouteStop] = [
                RouteStop(
                    location=warehouse.value,
                    stop_type="pickup",
                    order_id="BATCH",
                    estimated_arrival=t0 + timedelta(minutes=depot_min),
                    estimated_departure=t0
                    + timedelta(minutes=depot_min + self.PICKUP_SERVICE_MIN),
                    pallet_count=sum(o.pallet_count for o in served_orders),
                    weight_lbs=sum(o.weight_lbs for o in served_orders),
                )
            ]

            total_distance = 0.0
            index = routing.Start(v)
            prev_node = manager.IndexToNode(index)
            while not routing.IsEnd(index):
                next_index = solution.Value(routing.NextVar(index))
                next_node = manager.IndexToNode(next_index)
                total_distance += self._distance_matrix.get(
                    (node_locations[prev_node], node_locations[next_node]),
                    self._calculate_distance(
                        node_locations[prev_node], node_locations[next_node]
                    ),
                )
                if next_node != 0 and not routing.IsEnd(next_index):
                    order = order_by_node[next_node]
                    arrival_min = solution.Value(time_dim.CumulVar(next_index))
                    route_stops.append(
                        RouteStop(
                            location=order.delivery_location,
                            stop_type="delivery",
                            order_id=order.order_id,
                            estimated_arrival=t0 + timedelta(minutes=arrival_min),
                            estimated_departure=t0
                            + timedelta(
                                minutes=arrival_min + self.DELIVERY_SERVICE_MIN
                            ),
                            pallet_count=order.pallet_count,
                            weight_lbs=order.weight_lbs,
                        )
                    )
                index = next_index
                prev_node = next_node

            total_pallets = sum(o.pallet_count for o in served_orders)
            total_weight = sum(o.weight_lbs for o in served_orders)
            end_min = solution.Value(time_dim.CumulVar(routing.End(v)))
            load_plans.append(
                LoadPlan(
                    driver_id=driver.driver_id,
                    route=route_stops,
                    total_distance_miles=total_distance,
                    total_duration_hours=(end_min - depot_min) / 60.0,
                    total_pallets=total_pallets,
                    total_weight_lbs=total_weight,
                    utilization_pct=(total_pallets / driver.max_pallets * 100)
                    if driver.max_pallets > 0
                    else 0,
                    consolidation_opportunities=[],
                )
            )

        return load_plans

    @staticmethod
    def _route_node_indices(routing, solution, vehicle: int) -> List[int]:
        """Yield the solver indices visited by a vehicle, in order (excluding the end)."""
        indices = []
        index = routing.Start(vehicle)
        while not routing.IsEnd(index):
            indices.append(index)
            index = solution.Value(routing.NextVar(index))
        return indices

    def _solve_heuristic(self) -> List[LoadPlan]:
        """Solve VRP using heuristic algorithms (fallback when OR-Tools unavailable)."""
        load_plans: List[LoadPlan] = []

        # Simple nearest-neighbor heuristic
        # Group orders by pickup warehouse
        warehouse_orders: Dict[Warehouse, List[Order]] = {}
        for order in self._orders:
            if order.pickup_warehouse not in warehouse_orders:
                warehouse_orders[order.pickup_warehouse] = []
            warehouse_orders[order.pickup_warehouse].append(order)

        # Assign drivers to warehouses
        driver_idx = 0
        for warehouse, orders in warehouse_orders.items():
            if driver_idx >= len(self._drivers):
                break

            driver = self._drivers[driver_idx]
            route = self._build_route_for_warehouse(driver, warehouse, orders)

            load_plans.append(route)
            driver_idx += 1

        return load_plans

    def _build_route_for_warehouse(
        self, driver: Driver, warehouse: Warehouse, orders: List[Order]
    ) -> LoadPlan:
        """Build a route for a driver serving orders from a specific warehouse."""
        # Sort orders by priority and time window
        sorted_orders = sorted(
            orders,
            key=lambda o: (
                0 if o.priority == "urgent" else 1 if o.priority == "standard" else 2,
                o.time_window_start,
            ),
        )

        route_stops: List[RouteStop] = []
        total_pallets = 0
        total_weight = 0
        total_distance = 0
        current_time = driver.available_start

        # Add pickup stop at warehouse
        pickup_stop = RouteStop(
            location=warehouse.value,
            stop_type="pickup",
            order_id="BATCH",
            estimated_arrival=current_time,
            estimated_departure=current_time + timedelta(minutes=30),
            pallet_count=sum(o.pallet_count for o in sorted_orders),
            weight_lbs=sum(o.weight_lbs for o in sorted_orders),
        )
        route_stops.append(pickup_stop)

        # Add delivery stops
        for order in sorted_orders:
            # Calculate travel time
            prev_location = route_stops[-1].location
            travel_time_hours = (
                self._distance_matrix.get((prev_location, order.delivery_location), 1.0)
                / 40.0
            )  # Assume 40 mph average

            arrival_time = current_time + timedelta(hours=travel_time_hours)

            # Check time window
            if arrival_time < order.time_window_start:
                arrival_time = order.time_window_start

            departure_time = arrival_time + timedelta(minutes=45)  # Unloading time

            delivery_stop = RouteStop(
                location=order.delivery_location,
                stop_type="delivery",
                order_id=order.order_id,
                estimated_arrival=arrival_time,
                estimated_departure=departure_time,
                pallet_count=order.pallet_count,
                weight_lbs=order.weight_lbs,
            )
            route_stops.append(delivery_stop)

            total_pallets += order.pallet_count
            total_weight += order.weight_lbs
            total_distance += self._distance_matrix.get(
                (prev_location, order.delivery_location), 50.0
            )
            current_time = departure_time

        # Calculate utilization
        utilization_pct = (
            (total_pallets / driver.max_pallets * 100) if driver.max_pallets > 0 else 0
        )

        return LoadPlan(
            driver_id=driver.driver_id,
            route=route_stops,
            total_distance_miles=total_distance,
            total_duration_hours=(current_time - driver.available_start).total_seconds()
            / 3600,
            total_pallets=total_pallets,
            total_weight_lbs=total_weight,
            utilization_pct=utilization_pct,
            consolidation_opportunities=[],
        )

    def _find_consolidation_opportunities(self) -> List[ConsolidationOpportunity]:
        """Find opportunities to consolidate orders."""
        opportunities: List[ConsolidationOpportunity] = []

        # Group orders by warehouse and destination
        warehouse_dest_groups: Dict[Tuple[Warehouse, str], List[Order]] = {}
        for order in self._orders:
            key = (order.pickup_warehouse, order.delivery_location)
            if key not in warehouse_dest_groups:
                warehouse_dest_groups[key] = []
            warehouse_dest_groups[key].append(order)

        # Find groups with multiple orders
        for (warehouse, destination), orders in warehouse_dest_groups.items():
            if len(orders) > 1:
                combined_pallets = sum(o.pallet_count for o in orders)
                # Estimate savings (consolidated trip vs individual trips)
                individual_distance = len(orders) * self._calculate_distance(
                    warehouse.value, destination
                )
                consolidated_distance = self._calculate_distance(
                    warehouse.value, destination
                )
                savings_miles = individual_distance - consolidated_distance
                estimated_savings = savings_miles * 2.5  # $2.50 per mile estimate

                opportunities.append(
                    ConsolidationOpportunity(
                        orders=[o.order_id for o in orders],
                        shared_warehouse=warehouse,
                        shared_destination=destination,
                        combined_pallets=combined_pallets,
                        estimated_savings_usd=round(estimated_savings, 2),
                    )
                )

        return opportunities

    def _serialize_load_plan(self, lp: LoadPlan) -> Dict[str, Any]:
        return {
            "driver_id": lp.driver_id,
            "route": [
                {
                    "location": stop.location,
                    "stop_type": stop.stop_type,
                    "order_id": stop.order_id,
                    "estimated_arrival": stop.estimated_arrival.isoformat(),
                    "estimated_departure": stop.estimated_departure.isoformat(),
                    "pallet_count": stop.pallet_count,
                    "weight_lbs": stop.weight_lbs,
                }
                for stop in lp.route
            ],
            "total_distance_miles": round(lp.total_distance_miles, 2),
            "total_duration_hours": round(lp.total_duration_hours, 2),
            "total_pallets": lp.total_pallets,
            "total_weight_lbs": round(lp.total_weight_lbs, 2),
            "utilization_pct": round(lp.utilization_pct, 1),
        }

    def _serialize_consolidation(self, c: ConsolidationOpportunity) -> Dict[str, Any]:
        return {
            "orders": c.orders,
            "shared_warehouse": c.shared_warehouse.value,
            "shared_destination": c.shared_destination,
            "combined_pallets": c.combined_pallets,
            "estimated_savings_usd": c.estimated_savings_usd,
        }
