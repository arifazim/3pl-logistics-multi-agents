# MCP ADAPTER
# Exposes local MCP server endpoints as standard python functions for agent tools.

import mcp.tms_server.server as tms
import mcp.customer_rate_card_server.server as customer_rates
import mcp.vendor_rate_card_server.server as vendor_rates
import mcp.telemetry_server.server as telemetry
import mcp.policy_server.server as policy
import mcp.wms_server.server as wms
import mcp.vendor_directory_server.server as vendor_dir

# TMS Tools
def get_shipments() -> dict:
    """Retrieve all shipments currently in the Transport Management System."""
    return tms.get_shipments()

def create_shipment(origin: str, destination: str, weight_lbs: float, volume_cbft: float, sla_tier: str = "Standard", urgency: str = "Medium") -> dict:
    """Create a new shipment in the TMS.
    
    Args:
        origin: City of origin (e.g. Chicago)
        destination: City of destination (e.g. New York)
        weight_lbs: Weight of shipment in lbs
        volume_cbft: Volume of shipment in cubic feet
        sla_tier: Standard, Express, or Saver
        urgency: Low, Medium, or High
    """
    return tms.create_shipment({
        "origin": origin,
        "destination": destination,
        "weight_lbs": weight_lbs,
        "volume_cbft": volume_cbft,
        "sla_tier": sla_tier,
        "urgency": urgency
    })

def update_shipment_status(shipment_id: str, status: str) -> dict:
    """Update shipment status in the TMS (e.g. Pending, Assigned, In-Transit, Delivered, Escalated)."""
    return tms.update_status(shipment_id, status)

def get_routes(origin: str, destination: str) -> dict:
    """Retrieve route details between two cities, including distance and transit hours."""
    return tms.get_routes(origin, destination)

# Customer Pricing Tools
def get_customer_price(origin: str, destination: str, sla_tier: str = "Standard") -> dict:
    """Get the customer pricing rate card details for a specific lane and SLA tier."""
    return customer_rates.get_price(origin, destination, sla_tier)

def calculate_customer_quote(origin: str, destination: str, weight_lbs: float, volume_cbft: float, sla_tier: str = "Standard") -> dict:
    """Calculate a complete pricing quote for a customer shipment."""
    return customer_rates.calculate_quote(origin, destination, weight_lbs, volume_cbft, sla_tier)

# Vendor Bidding Tools
def get_vendor_rate(vendor_id: str, origin: str, destination: str) -> dict:
    """Get the rate card details for a specific vendor on a lane."""
    return vendor_rates.get_rate(vendor_id, origin, destination)

def compare_vendor_rates(origin: str, destination: str, weight_lbs: float = 10000, volume_cbft: float = 300) -> dict:
    """Compare rates across all carriers for a given lane and shipment size."""
    return vendor_rates.compare_vendors(origin, destination, weight_lbs, volume_cbft)

# Telemetry Tools
def get_telemetry_metrics() -> dict:
    """Get system-wide logistics performance metrics and KPIs."""
    return telemetry.metrics()

def append_telemetry_log(level: str, message: str) -> dict:
    """Append a trace log entry in telemetry server."""
    return telemetry.logs(action="append", level=level, message=message)

def get_telemetry_logs() -> dict:
    """Get the recent list of telemetry trace logs."""
    return telemetry.logs(action="get")

def raise_telemetry_alert(alert_type: str, message: str) -> dict:
    """Raise a system alert in telemetry server (alert_type can be WARNING, CRITICAL, INFO)."""
    return telemetry.alerts(action="raise", alert_type=alert_type, message=message)

def get_active_alerts() -> dict:
    """Retrieve active system telemetry alerts."""
    return telemetry.alerts(action="get")

def resolve_telemetry_alert(message: str) -> dict:
    """Resolve active telemetry alerts matching the message."""
    return telemetry.alerts(action="resolve", message=message)

# Policy Tools
def get_policies() -> dict:
    """Retrieve all operational, safety, and pricing policies."""
    return policy.get_policies()

def validate_shipment_policy(origin: str, destination: str, cargo_type: str = "Standard", weight_lbs: float = 10000) -> dict:
    """Validate shipment details against compliance, route, and weight policies."""
    return policy.validate_shipment(origin, destination, cargo_type, weight_lbs)

# WMS Tools
def get_warehouse_inventory(warehouse_id: str) -> dict:
    """Get inventory status for a specific warehouse (e.g. WH_CHI, WH_NYC, WH_HOU, WH_LAX)."""
    return wms.get_inventory(warehouse_id)

def check_pallet_readiness(shipment_id: str) -> dict:
    """Check if the pallets for a shipment are ready and packed at the dock."""
    return wms.check_pallet_readiness(shipment_id)

def get_warehouse_dock_schedule(warehouse_id: str) -> dict:
    """Get the active loading dock schedules for a specific warehouse."""
    return wms.get_dock_schedule(warehouse_id)

# Vendor Directory Tools
def list_vendors() -> dict:
    """Retrieve the list of all active vendor carriers in the system."""
    return vendor_dir.list_vendors()

def get_vendor_details(vendor_id: str) -> dict:
    """Get the full dossier for a specific carrier vendor."""
    return vendor_dir.get_vendor_details(vendor_id)

def get_vendor_reliability_score(vendor_id: str) -> dict:
    """Retrieve the reliability score (0.0 - 1.0) for a vendor."""
    return vendor_dir.get_reliability_score(vendor_id)
