"""Operations Insight Agent — Analyze warehouse-to-warehouse and warehouse-to-partner flows.

This agent provides:
- Bottleneck detection across warehouse operations
- Dwell time predictions
- Vendor reliability scoring from TMS/WMS data
- Pallet readiness analysis

Inputs: MCP_TMS, MCP_WMS, spreadsheets, telemetry
Outputs: bottlenecks, dwell predictions, vendor reliability scores, pallet readiness
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List
from enum import Enum

from runtime.agy.loader import load_agy
from runtime.skills.loader import load_agent_skills


class FlowType(Enum):
    WAREHOUSE_TO_WAREHOUSE = "warehouse_to_warehouse"
    WAREHOUSE_TO_PARTNER = "warehouse_to_partner"
    PARTNER_TO_WAREHOUSE = "partner_to_warehouse"


@dataclass
class Bottleneck:
    location: str
    type: str  # "dock_congestion", "labor_shortage", "equipment_failure", "capacity_limit"
    severity: str  # "low", "medium", "high", "critical"
    estimated_delay_hours: float
    affected_lanes: List[str]
    recommendation: str


@dataclass
class DwellPrediction:
    warehouse: str
    current_dwell_hours: float
    predicted_dwell_hours: float
    confidence: float
    factors: List[str]
    suggested_actions: List[str]


@dataclass
class VendorReliabilityScore:
    vendor_id: str
    overall_score: float
    on_time_delivery_rate: float
    damage_rate: float
    communication_score: float
    capacity_utilization: float
    trend: str  # "improving", "stable", "declining"
    last_updated: datetime


@dataclass
class PalletReadiness:
    warehouse: str
    total_pallets: int
    ready_pallets: int
    pending_pallets: int
    blocked_pallets: int
    readiness_percentage: float
    estimated_completion_time: datetime | None


class OperationsInsightAgent:
    """
    Analyzes operational flows and provides actionable insights.

    Uses MCP tools to fetch TMS/WMS data and applies deterministic algorithms
    for bottleneck detection, dwell prediction, and vendor scoring.
    """

    AGY_NAME = "operations_insight"

    def __init__(self):
        self._tms_client = None
        self._wms_client = None
        self._historical_data: Dict[str, Any] = {}
        # ── Agent harness: load .agy spec + skill contracts ──────────────────
        self._agy = load_agy(self.AGY_NAME)
        self._skill_context = load_agent_skills("operations_insight_agent")
        # Initialize MCP clients if available
        try:
            from runtime.adapters.pl3_mcp_client import Pl3McpClient

            self._mcp_client = Pl3McpClient()
        except ImportError:
            self._mcp_client = None

    async def analyze_warehouse_flows(
        self,
        start_warehouse: str,
        end_location: str,
        flow_type: FlowType = FlowType.WAREHOUSE_TO_WAREHOUSE,
        time_window_hours: int = 24,
    ) -> Dict[str, Any]:
        """
        Analyze flows between warehouses or partners.

        Returns bottleneck analysis, dwell predictions, and flow metrics.
        """
        bottlenecks = await self._detect_bottlenecks(
            start_warehouse, end_location, flow_type
        )
        dwell_pred = await self._predict_dwell_time(start_warehouse, time_window_hours)

        return {
            "flow_analysis": {
                "start": start_warehouse,
                "end": end_location,
                "type": flow_type.value,
                "time_window_hours": time_window_hours,
            },
            "bottlenecks": [self._serialize_bottleneck(b) for b in bottlenecks],
            "dwell_prediction": self._serialize_dwell_prediction(dwell_pred),
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _detect_bottlenecks(
        self, location: str, end_location: str, flow_type: FlowType
    ) -> List[Bottleneck]:
        """Detect operational bottlenecks using MCP data and heuristics."""
        bottlenecks: List[Bottleneck] = []

        # Fetch real-time data from MCP if available
        if self._mcp_client:
            try:
                tms_data = await self._mcp_client.call_tool(
                    "tms", "get_active_shipments", {}
                )
                wms_data = await self._mcp_client.call_tool(
                    "wms", "get_dock_status", {}
                )
            except Exception:
                tms_data = {}
                wms_data = {}
        else:
            # Simulated data for demo
            tms_data = {"active_shipments": 15, "capacity": 20}
            wms_data = {"docks_available": 3, "docks_total": 8}

        # Check dock congestion
        if wms_data:
            docks_available = wms_data.get("docks_available", 5)
            docks_total = wms_data.get("docks_total", 10)
            utilization = 1 - (docks_available / docks_total) if docks_total > 0 else 0

            if utilization > 0.8:
                bottlenecks.append(
                    Bottleneck(
                        location=location,
                        type="dock_congestion",
                        severity="high" if utilization > 0.9 else "medium",
                        estimated_delay_hours=utilization * 2,
                        affected_lanes=[f"{location}->{end_location}"],
                        recommendation="Reschedule non-urgent pickups or add temporary dock capacity",
                    )
                )

        # Check capacity limits
        if tms_data:
            active = tms_data.get("active_shipments", 0)
            capacity = tms_data.get("capacity", 20)
            if active >= capacity * 0.9:
                bottlenecks.append(
                    Bottleneck(
                        location=location,
                        type="capacity_limit",
                        severity="critical",
                        estimated_delay_hours=4,
                        affected_lanes=[f"{location}->{end_location}"],
                        recommendation="Immediate vendor diversification required",
                    )
                )

        # Simulated equipment failure check
        import random

        if random.random() < 0.1:  # 10% chance of simulated equipment issue
            bottlenecks.append(
                Bottleneck(
                    location=location,
                    type="equipment_failure",
                    severity="medium",
                    estimated_delay_hours=2,
                    affected_lanes=[f"{location}->{end_location}"],
                    recommendation="Dispatch maintenance team; reroute to alternate dock",
                )
            )

        return bottlenecks

    async def _predict_dwell_time(
        self, warehouse: str, time_window_hours: int
    ) -> DwellPrediction:
        """Predict dwell time based on historical patterns and current conditions."""
        # In production, this would use ML models trained on historical data
        # For now, use deterministic heuristics

        base_dwell = 4.0  # hours
        factors = []

        # Time of day factor
        hour = datetime.utcnow().hour
        if 6 <= hour < 10 or 14 <= hour < 18:  # Peak hours
            base_dwell *= 1.5
            factors.append("Peak hour congestion")

        # Day of week factor
        weekday = datetime.utcnow().weekday()
        if weekday == 0:  # Monday
            base_dwell *= 1.3
            factors.append("Monday backlog")
        elif weekday == 4:  # Friday
            base_dwell *= 1.2
            factors.append("Friday rush")

        # Fetch current dock status
        if self._mcp_client:
            try:
                dock_status = await self._mcp_client.call_tool(
                    "wms", "get_dock_status", {}
                )
                queue_length = dock_status.get("queue_length", 0)
                if queue_length > 5:
                    base_dwell += queue_length * 0.5
                    factors.append(f"Dock queue: {queue_length} trucks")
            except Exception:
                pass

        confidence = 0.75 if len(factors) > 0 else 0.85

        return DwellPrediction(
            warehouse=warehouse,
            current_dwell_hours=base_dwell * 0.8,
            predicted_dwell_hours=base_dwell,
            confidence=confidence,
            factors=factors,
            suggested_actions=[
                "Stagger pickup appointments by 30-minute intervals",
                "Pre-allocate dock slots for high-priority lanes",
                "Consider off-peak scheduling for non-urgent loads",
            ]
            if base_dwell > 5
            else [],
        )

    async def score_vendor_reliability(
        self, vendor_id: str, lookback_days: int = 30
    ) -> VendorReliabilityScore:
        """
        Calculate vendor reliability score from historical performance data.

        Scoring components:
        - On-time delivery rate (40% weight)
        - Damage rate (25% weight, inverted)
        - Communication score (20% weight)
        - Capacity utilization (15% weight)
        """
        # Fetch historical data from MCP
        if self._mcp_client:
            try:
                vendor_data = await self._mcp_client.call_tool(
                    "vendor",
                    "get_performance_history",
                    {"vendor_id": vendor_id, "days": lookback_days},
                )
            except Exception:
                vendor_data = {}
        else:
            # Simulated data for demo
            vendor_data = {
                "on_time_deliveries": 45,
                "total_deliveries": 50,
                "damaged_shipments": 2,
                "communication_score": 4.2,  # out of 5
                "avg_capacity_utilization": 0.75,
            }

        # Calculate components
        total_deliveries = vendor_data.get("total_deliveries", 1)
        on_time_rate = vendor_data.get("on_time_deliveries", 0) / total_deliveries
        damage_rate = vendor_data.get("damaged_shipments", 0) / total_deliveries
        comm_score = vendor_data.get("communication_score", 3.0) / 5.0
        capacity_util = vendor_data.get("avg_capacity_utilization", 0.5)

        # Weighted score
        overall_score = (
            on_time_rate * 0.40
            + (1 - damage_rate) * 0.25
            + comm_score * 0.20
            + min(capacity_util, 0.9) / 0.9 * 0.15
        ) * 100

        # Determine trend (simplified)
        trend = "stable"
        if on_time_rate > 0.95:
            trend = "improving"
        elif on_time_rate < 0.85:
            trend = "declining"

        return VendorReliabilityScore(
            vendor_id=vendor_id,
            overall_score=round(overall_score, 1),
            on_time_delivery_rate=round(on_time_rate * 100, 1),
            damage_rate=round(damage_rate * 100, 1),
            communication_score=round(comm_score * 5, 1),
            capacity_utilization=round(capacity_util * 100, 1),
            trend=trend,
            last_updated=datetime.utcnow(),
        )

    async def check_pallet_readiness(self, warehouse: str) -> PalletReadiness:
        """Check pallet readiness status at a warehouse."""
        if self._mcp_client:
            try:
                pallet_data = await self._mcp_client.call_tool(
                    "wms", "get_pallet_status", {"warehouse": warehouse}
                )
            except Exception:
                pallet_data = {}
        else:
            # Simulated data
            pallet_data = {
                "total_pallets": 150,
                "ready_pallets": 120,
                "pending_pallets": 25,
                "blocked_pallets": 5,
            }

        total = pallet_data.get("total_pallets", 0)
        ready = pallet_data.get("ready_pallets", 0)
        pending = pallet_data.get("pending_pallets", 0)
        blocked = pallet_data.get("blocked_pallets", 0)

        readiness_pct = (ready / total * 100) if total > 0 else 0

        # Estimate completion time for pending pallets
        est_completion = None
        if pending > 0:
            est_completion = datetime.utcnow() + timedelta(hours=pending * 0.5)

        return PalletReadiness(
            warehouse=warehouse,
            total_pallets=total,
            ready_pallets=ready,
            pending_pallets=pending,
            blocked_pallets=blocked,
            readiness_percentage=round(readiness_pct, 1),
            estimated_completion_time=est_completion,
        )

    def _serialize_bottleneck(self, b: Bottleneck) -> Dict[str, Any]:
        return {
            "location": b.location,
            "type": b.type,
            "severity": b.severity,
            "estimated_delay_hours": b.estimated_delay_hours,
            "affected_lanes": b.affected_lanes,
            "recommendation": b.recommendation,
        }

    def _serialize_dwell_prediction(self, d: DwellPrediction) -> Dict[str, Any]:
        return {
            "warehouse": d.warehouse,
            "current_dwell_hours": d.current_dwell_hours,
            "predicted_dwell_hours": d.predicted_dwell_hours,
            "confidence": d.confidence,
            "factors": d.factors,
            "suggested_actions": d.suggested_actions,
        }
