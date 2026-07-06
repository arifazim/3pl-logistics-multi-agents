import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from runtime.agents.a2ui_concierge_agent import A2UIConciergeAgent
from runtime.agents.commerce_agent import CommerceAgent
from runtime.agents.human_supervisor_agent import HumanSupervisorAgent
from runtime.agents.load_planning_agent import LoadPlanningAgent
from runtime.agents.operations_insight_agent import OperationsInsightAgent
from runtime.agents.orchestrator_agent import OrchestratorAgent
from runtime.agents.quotation_decision_agent import QuotationDecisionAgent
from runtime.agents.security_sentinel_agent import SecuritySentinelAgent
from runtime.agents.vendor_side_agents import A2ANegotiator
from runtime.agy.loader import load_agy
from runtime.skills.loader import AGENT_SKILLS, list_available_skills
from runtime.tools.route_optimizer import RouteOptimizer


class AgentSystem:
    """Executes dual_quotation via ADK quotation_decision_agent + agent_graph.yaml config."""

    def __init__(self, agent_graph_path: str = "agy/agent_graph.yaml"):
        # Resolve path relative to project root
        if not Path(agent_graph_path).is_absolute():
            project_root = Path(__file__).resolve().parent.parent
            agent_graph_path = project_root / agent_graph_path
        self.agent_graph = self._load_agent_graph(agent_graph_path)
        self.decision_agent = QuotationDecisionAgent()
        self.route_optimizer = RouteOptimizer()
        self.a2a_negotiator = A2ANegotiator()
        self.orchestrator = OrchestratorAgent()
        self.operations_insight = OperationsInsightAgent()
        self.load_planning = LoadPlanningAgent()
        self.a2ui_concierge = A2UIConciergeAgent()
        self.security_sentinel = SecuritySentinelAgent()
        self.human_supervisor = HumanSupervisorAgent()
        self.commerce_agent = CommerceAgent(
            mcp=self.decision_agent.mcp, supervisor=self.human_supervisor
        )
        self._loaded_agy = load_agy("quotation_decision")

    def _load_agent_graph(self, path: str | Path) -> Dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def execute_agent_workflow(
        self, workflow_name: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        graph_workflows = self.agent_graph.get("workflows") or {}
        if workflow_name == "dual_quotation" or workflow_name in graph_workflows:
            if workflow_name == "dual_quotation":
                result = await self.decision_agent.decide(input_data)
                return {
                    **result.payload,
                    "explanation": result.explanation,
                    "agent_mode": result.agent_mode,
                }

        if workflow_name == "customer_quotation":
            quote = self.decision_agent.quotation_engine.calculate_customer_quote(
                input_data["lane"],
                weight=float(input_data.get("weight", 1000)),
                sla_tier=input_data.get("sla_tier", "standard"),
            )
            return {
                "quote": quote,
                "workflow": "customer_quotation",
                "source": "deterministic_quotation_engine",
            }

        if workflow_name == "vendor_quotation":
            ranking = self.decision_agent.mcp.rank_vendors(
                input_data["lane"], weight_lbs=float(input_data.get("weight", 1000))
            )
            return {
                "workflow": "vendor_quotation",
                "ranked_vendors": ranking.get("ranked", []),
                "recommended_vendor": ranking.get("selected"),
                "a2a": {"protocol": "vendor_negotiation"},
            }

        if workflow_name == "compliance_check":
            c = self.decision_agent.check_compliance(
                input_data.get("margin", 0),
                input_data.get("delivery_time", 20),
                float(input_data.get("weight", 1000)),
                input_data.get("shipment_id", "UNKNOWN"),
            )
            return {"compliance": c, "workflow": "compliance_check"}

        if workflow_name == "load_planning":
            # Use real LoadPlanningAgent instead of stub
            from runtime.agents.load_planning_agent import Order, Driver, Warehouse

            orders = []
            for o in input_data.get("orders", []):
                orders.append(
                    Order(
                        order_id=o["order_id"],
                        pickup_warehouse=Warehouse(o["pickup_warehouse"]),
                        delivery_location=o["delivery_location"],
                        pallet_count=o["pallet_count"],
                        weight_lbs=o["weight_lbs"],
                        priority=o.get("priority", "standard"),
                        time_window_start=datetime.fromisoformat(
                            o["time_window_start"]
                        ),
                        time_window_end=datetime.fromisoformat(o["time_window_end"]),
                        sla_tier=o.get("sla_tier", "standard"),
                    )
                )
            drivers = []
            for d in input_data.get("drivers", []):
                drivers.append(
                    Driver(
                        driver_id=d["driver_id"],
                        current_location=Warehouse(d["current_location"]),
                        available_start=datetime.fromisoformat(d["available_start"]),
                        available_end=datetime.fromisoformat(d["available_end"]),
                        max_pallets=d["max_pallets"],
                        max_weight_lbs=d["max_weight_lbs"],
                        current_route=d.get("current_route", []),
                    )
                )
            self.load_planning.set_orders(orders)
            self.load_planning.set_drivers(drivers)
            result = await self.load_planning.optimize_loads(
                input_data.get("planning_horizon_hours", 24)
            )
            return {**result, "workflow": "load_planning"}

        if workflow_name == "operations_insight":
            from runtime.agents.operations_insight_agent import FlowType

            result = await self.operations_insight.analyze_warehouse_flows(
                start_warehouse=input_data["start_warehouse"],
                end_location=input_data["end_location"],
                flow_type=FlowType(
                    input_data.get("flow_type", "warehouse_to_warehouse")
                ),
                time_window_hours=input_data.get("time_window_hours", 24),
            )
            return {**result, "workflow": "operations_insight"}

        if workflow_name == "vendor_reliability":
            result = await self.operations_insight.score_vendor_reliability(
                vendor_id=input_data["vendor_id"],
                lookback_days=input_data.get("lookback_days", 30),
            )
            return {
                "vendor_id": result.vendor_id,
                "overall_score": result.overall_score,
                "on_time_delivery_rate": result.on_time_delivery_rate,
                "damage_rate": result.damage_rate,
                "communication_score": result.communication_score,
                "capacity_utilization": result.capacity_utilization,
                "trend": result.trend,
                "last_updated": result.last_updated.isoformat(),
                "workflow": "vendor_reliability",
            }

        if workflow_name == "pallet_readiness":
            result = await self.operations_insight.check_pallet_readiness(
                warehouse=input_data["warehouse"]
            )
            return {
                "warehouse": result.warehouse,
                "total_pallets": result.total_pallets,
                "ready_pallets": result.ready_pallets,
                "pending_pallets": result.pending_pallets,
                "blocked_pallets": result.blocked_pallets,
                "readiness_percentage": result.readiness_percentage,
                "estimated_completion_time": result.estimated_completion_time.isoformat()
                if result.estimated_completion_time
                else None,
                "workflow": "pallet_readiness",
            }

        if workflow_name == "generate_dashboard":
            from runtime.agents.a2ui_concierge_agent import Audience

            result = await self.a2ui_concierge.generate_dashboard(
                audience=Audience(input_data.get("audience", "dispatcher")),
                agent_outputs=input_data.get("agent_outputs", {}),
                telemetry=input_data.get("telemetry", {}),
            )
            return self.a2ui_concierge.serialize_dashboard(result)

        if workflow_name == "generate_narrative":
            from runtime.agents.a2ui_concierge_agent import Audience

            result = await self.a2ui_concierge.generate_narrative(
                audience=Audience(input_data.get("audience", "dispatcher")),
                agent_outputs=input_data.get("agent_outputs", {}),
                context=input_data.get("context", ""),
            )
            return self.a2ui_concierge.serialize_narrative(result)

        if workflow_name == "red_team_test":
            result = await self.security_sentinel.run_red_team_test(
                test_target=input_data["test_target"],
                test_type=input_data.get("test_type", "prompt_injection"),
            )
            return {**result, "workflow": "red_team_test"}

        if workflow_name == "blue_team_hardening":
            result = await self.security_sentinel.run_blue_team_hardening(
                hardening_type=input_data.get("hardening_type", "input_validation")
            )
            return {**result, "workflow": "blue_team_hardening"}

        if workflow_name == "green_team_validation":
            result = await self.security_sentinel.run_green_team_validation(
                validation_type=input_data.get("validation_type", "regression")
            )
            return {**result, "workflow": "green_team_validation"}

        if workflow_name == "security_summary":
            result = self.security_sentinel.get_security_summary()
            return {**result, "workflow": "security_summary"}

        if workflow_name == "human_review":
            result = self.human_supervisor.review(
                action=input_data.get("action", "Review shipment decision"),
                margin_pct=float(input_data.get("margin_pct", 0.0)),
                total_rate=float(input_data.get("total_rate", 0.0)),
                vendor_id=input_data.get("vendor_id"),
                compliance_passed=bool(input_data.get("compliance_passed", True)),
                vendor_text_flagged=bool(input_data.get("vendor_text_flagged", False)),
                shipment_id=input_data.get("shipment_id", "UNKNOWN"),
                lane=input_data.get("lane"),
                action_type=input_data.get("action_type", "review"),
            )
            return {**result, "workflow": "human_review"}

        if workflow_name == "ap2_payment":
            return await self.commerce_agent.settle(
                lane=input_data["lane"],
                weight_lbs=float(input_data.get("weight", 1000)),
                sla_tier=input_data.get("sla_tier", "standard"),
                shipment_id=input_data.get("shipment_id", "UNKNOWN"),
                max_amount=input_data.get("max_amount"),
                human_approved=bool(input_data.get("human_approved", False)),
                approver=input_data.get("approver", "dispatcher"),
                payment_method=input_data.get("payment_method", "card"),
                persist=bool(input_data.get("persist", True)),
            )

        if workflow_name == "a2a_negotiation":
            # A2A: use MCP-ranked vendor cost as broker's starting target
            lane = input_data["lane"]
            weight = float(input_data.get("weight", 1000))
            sla_tier = input_data.get("sla_tier", "standard")
            shipment_id = input_data.get("shipment_id", "UNKNOWN")
            ranking = self.decision_agent.mcp.rank_vendors(lane, weight_lbs=weight)
            selected = ranking.get("selected") or {}
            vendor_cost = float(
                selected.get("effective_rate", selected.get("rate", 300))
            )
            result = self.a2a_negotiator.negotiate(
                lane=lane,
                weight_lbs=weight,
                sla_tier=sla_tier,
                vendor_cost_from_mcp=vendor_cost,
                shipment_id=shipment_id,
            )
            return {
                "workflow": "a2a_negotiation",
                "shipment_id": result.shipment_id,
                "lane": result.lane,
                "agreed": result.agreed,
                "agreed_vendor_id": result.agreed_vendor_id,
                "agreed_rate": result.agreed_rate,
                "rounds": result.rounds,
                "summary": result.summary,
                "all_offers": [
                    {
                        "vendor_id": o.vendor_id,
                        "vendor_name": o.vendor_name,
                        "offered_rate": o.offered_rate,
                        "accepted": o.accepted,
                        "counter_offer": o.counter_offer,
                        "round_num": o.round_num,
                        "reason": o.reason,
                        "reliability_score": o.reliability_score,
                        "timestamp": o.timestamp,
                    }
                    for o in result.all_offers
                ],
                "mcp_reference_cost": vendor_cost,
            }

        return {"error": f"Unknown workflow: {workflow_name}"}

    def agent_metadata(self) -> dict[str, Any]:
        return {
            "agy": self._loaded_agy.get("name"),
            "skills": self._loaded_agy.get("skills"),
            "mcp_server": self.agent_graph.get("mcp_server"),
            "instruction_loaded": bool(self.decision_agent.get_instruction()),
            "fleet_skills": AGENT_SKILLS,
            "available_skills": list_available_skills(),
        }
