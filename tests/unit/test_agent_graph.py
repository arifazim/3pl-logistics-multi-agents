"""Verify agent_graph.yaml declares the full agent fleet and their workflows."""

from pathlib import Path

import yaml

from runtime.skills.loader import list_available_skills

ROOT = Path(__file__).resolve().parents[2]
GRAPH = yaml.safe_load((ROOT / "agy" / "agent_graph.yaml").read_text())["graph"]

EXPECTED_NODES = {
    "quotation_decision", "operations_insight", "load_planning", "a2ui_concierge",
    "security_sentinel", "commerce", "human_supervisor",
}
EXPECTED_WORKFLOWS = {
    "dual_quotation", "operations_insight", "load_planning", "generate_dashboard",
    "red_team_test", "ap2_payment", "human_review",
}


def test_graph_declares_full_fleet():
    node_names = {n["name"] for n in GRAPH["nodes"]}
    assert EXPECTED_NODES.issubset(node_names), f"missing nodes: {EXPECTED_NODES - node_names}"


def test_graph_declares_new_workflows():
    workflows = set(GRAPH["workflows"].keys())
    assert EXPECTED_WORKFLOWS.issubset(workflows), f"missing: {EXPECTED_WORKFLOWS - workflows}"


def test_every_node_skill_exists_on_disk():
    available = set(list_available_skills())
    for node in GRAPH["nodes"]:
        for skill in node.get("skills", []):
            assert skill in available, f"node {node['name']} references unknown skill '{skill}'"


def test_ap2_payment_workflow_is_bound_to_commerce():
    assert GRAPH["workflows"]["ap2_payment"]["agent"] == "commerce"
    assert GRAPH["workflows"]["human_review"]["agent"] == "human_supervisor"
