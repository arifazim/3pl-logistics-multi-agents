"""A2UI Concierge Agent — Generate UI views and narratives for stakeholders.

This agent provides:
- Dashboard generation for dispatchers, planners, and finance teams
- Narrative summaries ("explain-like-I'm-a-dispatcher")
- KPI visualizations
- Actionable insights presentation

Inputs: agent outputs, telemetry, KPIs
Outputs: dashboards, summaries, narratives
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from runtime.agy.loader import load_agy
from runtime.skills.loader import load_agent_skills


class Audience(Enum):
    DISPATCHER = "dispatcher"
    PLANNER = "planner"
    FINANCE = "finance"
    EXECUTIVE = "executive"


@dataclass
class DashboardView:
    audience: Audience
    title: str
    summary: str
    kpis: Dict[str, Any]
    alerts: List[str]
    recommendations: List[str]
    generated_at: datetime


@dataclass
class NarrativeSummary:
    audience: Audience
    title: str
    narrative: str
    key_takeaways: List[str]
    action_items: List[str]
    generated_at: datetime


class A2UIConciergeAgent:
    """
    Generates UI views and narratives for different stakeholder audiences.

    Transforms complex agent outputs into human-readable, actionable formats
    tailored to specific roles (dispatcher, planner, finance, executive).
    """

    AGY_NAME = "a2ui_concierge"

    def __init__(self):
        # ── Agent harness: load .agy spec + skill contracts ──────────────────
        self._agy = load_agy(self.AGY_NAME)
        self._skill_context = load_agent_skills("a2ui_concierge_agent")
        self._templates = self._load_templates()

    def _load_templates(self) -> Dict[str, str]:
        """Load narrative templates for different audiences."""
        return {
            "dispatcher": {
                "summary": "Dispatch Summary for {date}",
                "narrative": "As a dispatcher, here's what you need to know today: {content}",
                "takeaway_prefix": "•",
                "action_prefix": "→",
            },
            "planner": {
                "summary": "Planning Overview for {date}",
                "narrative": "From a planning perspective: {content}",
                "takeaway_prefix": "•",
                "action_prefix": "→",
            },
            "finance": {
                "summary": "Financial Performance for {date}",
                "narrative": "Financial highlights: {content}",
                "takeaway_prefix": "•",
                "action_prefix": "→",
            },
            "executive": {
                "summary": "Executive Briefing for {date}",
                "narrative": "Executive summary: {content}",
                "takeaway_prefix": "•",
                "action_prefix": "→",
            },
        }

    async def generate_dashboard(
        self,
        audience: Audience,
        agent_outputs: Dict[str, Any],
        telemetry: Dict[str, Any],
    ) -> DashboardView:
        """
        Generate a dashboard view for a specific audience.

        Args:
            audience: Target audience (dispatcher, planner, finance, executive)
            agent_outputs: Dictionary of outputs from various agents
            telemetry: Telemetry data and KPIs

        Returns:
            DashboardView with audience-tailored content
        """
        template = self._templates[audience.value]

        # Extract relevant KPIs based on audience
        kpis = self._extract_audience_kpis(audience, telemetry)

        # Generate alerts
        alerts = self._generate_alerts(audience, agent_outputs, telemetry)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            audience, agent_outputs, telemetry
        )

        # Generate summary
        summary = template["summary"].format(date=datetime.now().strftime("%Y-%m-%d"))

        return DashboardView(
            audience=audience,
            title=summary,
            summary=self._generate_summary_text(audience, agent_outputs, telemetry),
            kpis=kpis,
            alerts=alerts,
            recommendations=recommendations,
            generated_at=datetime.now(timezone.utc),
        )

    async def generate_narrative(
        self, audience: Audience, agent_outputs: Dict[str, Any], context: str = ""
    ) -> NarrativeSummary:
        """
        Generate a narrative summary for a specific audience.

        Args:
            audience: Target audience
            agent_outputs: Dictionary of outputs from various agents
            context: Additional context for the narrative

        Returns:
            NarrativeSummary with audience-tailored narrative
        """
        template = self._templates[audience.value]

        # Generate narrative content
        narrative_content = self._generate_narrative_content(
            audience, agent_outputs, context
        )

        # Extract key takeaways
        key_takeaways = self._extract_key_takeaways(audience, agent_outputs)

        # Extract action items
        action_items = self._extract_action_items(audience, agent_outputs)

        # Format narrative
        narrative = template["narrative"].format(content=narrative_content)

        return NarrativeSummary(
            audience=audience,
            title=template["summary"].format(date=datetime.now().strftime("%Y-%m-%d")),
            narrative=narrative,
            key_takeaways=key_takeaways,
            action_items=action_items,
            generated_at=datetime.now(timezone.utc),
        )

    def _extract_audience_kpis(
        self, audience: Audience, telemetry: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract KPIs relevant to the audience."""
        kpis = {}

        if audience == Audience.DISPATCHER:
            kpis = {
                "active_shipments": telemetry.get("active_shipments", 0),
                "on_time_rate": telemetry.get("on_time_delivery_rate", 0),
                "pending_approvals": telemetry.get("hitl_queue_length", 0),
                "avg_dwell_time": telemetry.get("avg_dwell_hours", 0),
            }
        elif audience == Audience.PLANNER:
            kpis = {
                "load_utilization": telemetry.get("avg_load_utilization", 0),
                "consolidation_savings": telemetry.get("consolidation_savings_usd", 0),
                "driver_availability": telemetry.get("available_drivers", 0),
                "route_efficiency": telemetry.get("route_efficiency_pct", 0),
            }
        elif audience == Audience.FINANCE:
            kpis = {
                "total_revenue": telemetry.get("total_revenue", 0),
                "total_margin": telemetry.get("total_margin", 0),
                "margin_percentage": telemetry.get("avg_margin_pct", 0),
                "cost_savings": telemetry.get("cost_savings", 0),
            }
        elif audience == Audience.EXECUTIVE:
            kpis = {
                "overall_performance": telemetry.get("overall_score", 0),
                "customer_satisfaction": telemetry.get("customer_satisfaction", 0),
                "vendor_reliability": telemetry.get("avg_vendor_reliability", 0),
                "operational_efficiency": telemetry.get("operational_efficiency", 0),
            }

        return kpis

    def _generate_alerts(
        self,
        audience: Audience,
        agent_outputs: Dict[str, Any],
        telemetry: Dict[str, Any],
    ) -> List[str]:
        """Generate alerts based on audience and data."""
        alerts = []

        # Check for bottlenecks
        if "operations_insight" in agent_outputs:
            bottlenecks = agent_outputs["operations_insight"].get("bottlenecks", [])
            for bottleneck in bottlenecks:
                if bottleneck.get("severity") in ["high", "critical"]:
                    alerts.append(
                        f"⚠️ {bottleneck.get('type')} at {bottleneck.get('location')}: {bottleneck.get('recommendation')}"
                    )

        # Check for compliance issues
        if "compliance" in agent_outputs:
            compliance = agent_outputs["compliance"]
            if not compliance.get("passed", True):
                alerts.append(
                    f"🚨 Compliance violation: {compliance.get('violations', [])}"
                )

        # Check for HITL escalations
        if "hitl" in agent_outputs:
            hitl = agent_outputs["hitl"]
            if hitl.get("requires_approval", False):
                alerts.append(f"🔔 Human approval required: {hitl.get('reasons', [])}")

        # Audience-specific alerts
        if audience == Audience.DISPATCHER:
            if telemetry.get("pending_approvals", 0) > 5:
                alerts.append(
                    f"⏳ High pending approvals: {telemetry.get('pending_approvals')}"
                )
        elif audience == Audience.FINANCE:
            if telemetry.get("margin_percentage", 0) < 12:
                alerts.append(
                    f"💰 Margin below threshold: {telemetry.get('margin_percentage')}%"
                )

        return alerts[:5]  # Limit to top 5 alerts

    def _generate_recommendations(
        self,
        audience: Audience,
        agent_outputs: Dict[str, Any],
        telemetry: Dict[str, Any],
    ) -> List[str]:
        """Generate recommendations based on audience and data."""
        recommendations = []

        # Extract from agent outputs
        if "operations_insight" in agent_outputs:
            dwell_pred = agent_outputs["operations_insight"].get("dwell_prediction", {})
            actions = dwell_pred.get("suggested_actions", [])
            recommendations.extend(actions)

        # Audience-specific recommendations
        if audience == Audience.DISPATCHER:
            recommendations.append("Review pending HITL approvals")
            recommendations.append("Monitor high-priority shipments")
        elif audience == Audience.PLANNER:
            recommendations.append("Review consolidation opportunities")
            recommendations.append("Optimize driver schedules")
        elif audience == Audience.FINANCE:
            recommendations.append("Review margin trends")
            recommendations.append("Analyze cost savings opportunities")
        elif audience == Audience.EXECUTIVE:
            recommendations.append("Review overall performance metrics")
            recommendations.append("Assess strategic initiatives")

        return recommendations[:5]  # Limit to top 5 recommendations

    def _generate_summary_text(
        self,
        audience: Audience,
        agent_outputs: Dict[str, Any],
        telemetry: Dict[str, Any],
    ) -> str:
        """Generate summary text for the dashboard."""
        parts = []

        # Operations insight
        if "operations_insight" in agent_outputs:
            flow_analysis = agent_outputs["operations_insight"].get("flow_analysis", {})
            parts.append(
                f"Flow analysis for {flow_analysis.get('start', 'N/A')} → {flow_analysis.get('end', 'N/A')}"
            )

        # Load planning
        if "load_planning" in agent_outputs:
            metrics = agent_outputs["load_planning"].get("metrics", {})
            parts.append(
                f"Load planning: {metrics.get('total_orders', 0)} orders, {metrics.get('total_drivers_used', 0)} drivers"
            )

        # Compliance
        if "compliance" in agent_outputs:
            compliance = agent_outputs["compliance"]
            status = "✓ Passed" if compliance.get("passed", True) else "✗ Failed"
            parts.append(f"Compliance: {status}")

        return " | ".join(parts) if parts else "No summary available"

    def _generate_narrative_content(
        self, audience: Audience, agent_outputs: Dict[str, Any], context: str
    ) -> str:
        """Generate narrative content based on audience."""
        content_parts = []

        # Add context if provided
        if context:
            content_parts.append(context)

        # Add operations insight
        if "operations_insight" in agent_outputs:
            bottlenecks = agent_outputs["operations_insight"].get("bottlenecks", [])
            if bottlenecks:
                content_parts.append(
                    f"Identified {len(bottlenecks)} operational bottlenecks requiring attention."
                )

        # Add load planning insights
        if "load_planning" in agent_outputs:
            consolidations = agent_outputs["load_planning"].get(
                "consolidation_opportunities", []
            )
            if consolidations:
                content_parts.append(
                    f"Found {len(consolidations)} consolidation opportunities with potential savings."
                )

        # Add compliance status
        if "compliance" in agent_outputs:
            compliance = agent_outputs["compliance"]
            if compliance.get("passed", True):
                content_parts.append("All compliance checks passed successfully.")
            else:
                content_parts.append("Compliance violations detected requiring review.")

        # Add vendor reliability
        if "vendor_reliability" in agent_outputs:
            vendor_score = agent_outputs["vendor_reliability"].get("overall_score", 0)
            content_parts.append(f"Vendor reliability score: {vendor_score}/100.")

        # Add commerce / AP2 settlement
        if "commerce" in agent_outputs:
            c = agent_outputs["commerce"]
            vendor = c.get("vendor_name") or c.get("vendor_id", "the carrier")
            rate = c.get("agreed_rate", 0) or 0
            status = c.get("payment_status", "settled")
            funding = c.get("funding_type", "card")
            content_parts.append(
                f"Contract locked with {vendor} at ${rate:,.2f} (margin "
                f"{c.get('margin_percentage', 0):.1f}%). Payment {status} via "
                f"{c.get('processor', 'AP2')} ({funding})."
            )

        return (
            " ".join(content_parts)
            if content_parts
            else "No specific updates at this time."
        )

    def _extract_key_takeaways(
        self, audience: Audience, agent_outputs: Dict[str, Any]
    ) -> List[str]:
        """Extract key takeaways for the audience."""
        takeaways = []

        # Operations insights
        if "operations_insight" in agent_outputs:
            dwell_pred = agent_outputs["operations_insight"].get("dwell_prediction", {})
            predicted = dwell_pred.get("predicted_dwell_hours", 0)
            takeaways.append(f"Predicted dwell time: {predicted:.1f} hours")

        # Load planning
        if "load_planning" in agent_outputs:
            metrics = agent_outputs["load_planning"].get("metrics", {})
            takeaways.append(
                f"Total distance: {metrics.get('total_distance_miles', 0):.1f} miles"
            )
            takeaways.append(
                f"Average utilization: {metrics.get('avg_utilization_pct', 0):.1f}%"
            )

        # Compliance
        if "compliance" in agent_outputs:
            compliance = agent_outputs["compliance"]
            takeaways.append(
                f"Compliance status: {'Passed' if compliance.get('passed', True) else 'Failed'}"
            )

        # Commerce / AP2 settlement
        if "commerce" in agent_outputs:
            c = agent_outputs["commerce"]
            takeaways.append(f"Carrier: {c.get('vendor_name') or c.get('vendor_id')}")
            takeaways.append(
                f"Paid: ${(c.get('agreed_rate', 0) or 0):,.2f} via {c.get('funding_type', 'card')}"
            )
            takeaways.append(f"Margin protected: {c.get('margin_percentage', 0):.1f}%")
            takeaways.append(f"Payment: {c.get('payment_status', 'settled')}")

        return takeaways[:5]

    def _extract_action_items(
        self, audience: Audience, agent_outputs: Dict[str, Any]
    ) -> List[str]:
        """Extract action items for the audience."""
        actions = []

        # From bottlenecks
        if "operations_insight" in agent_outputs:
            bottlenecks = agent_outputs["operations_insight"].get("bottlenecks", [])
            for bottleneck in bottlenecks:
                if bottleneck.get("severity") in ["high", "critical"]:
                    actions.append(bottleneck.get("recommendation", ""))

        # From HITL
        if "hitl" in agent_outputs:
            hitl = agent_outputs["hitl"]
            if hitl.get("requires_approval", False):
                actions.append("Review and approve HITL escalation")

        # From consolidations
        if "load_planning" in agent_outputs:
            consolidations = agent_outputs["load_planning"].get(
                "consolidation_opportunities", []
            )
            for cons in consolidations:
                actions.append(f"Review consolidation: {cons.get('orders', [])}")

        return actions[:5]

    def serialize_dashboard(self, dashboard: DashboardView) -> Dict[str, Any]:
        """Serialize DashboardView to dictionary."""
        return {
            "audience": dashboard.audience.value,
            "title": dashboard.title,
            "summary": dashboard.summary,
            "kpis": dashboard.kpis,
            "alerts": dashboard.alerts,
            "recommendations": dashboard.recommendations,
            "generated_at": dashboard.generated_at.isoformat(),
        }

    def serialize_narrative(self, narrative: NarrativeSummary) -> Dict[str, Any]:
        """Serialize NarrativeSummary to dictionary."""
        return {
            "audience": narrative.audience.value,
            "title": narrative.title,
            "narrative": narrative.narrative,
            "key_takeaways": narrative.key_takeaways,
            "action_items": narrative.action_items,
            "generated_at": narrative.generated_at.isoformat(),
        }
