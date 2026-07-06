"""Skill structure + loader integration tests."""

import pytest

from runtime.skills.loader import (
    AGENT_SKILLS,
    list_available_skills,
    load_agent_skills,
    load_skill,
    load_skills,
)

EXPECTED_SKILLS = {
    "operations_insight",
    "load_planning",
    "customer_quotation",
    "vendor_quotation",
    "commerce",
    "compliance_and_risk",
    "a2ui_concierge",
    "security_sentinel",
    "evaluation",
    "human_supervisor",
}


def test_all_ten_skills_present_and_discoverable():
    available = set(list_available_skills())
    assert EXPECTED_SKILLS.issubset(available), (
        f"missing skills: {EXPECTED_SKILLS - available}"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED_SKILLS))
def test_each_skill_document_is_well_formed(name):
    doc = load_skill(name)
    assert doc.strip(), f"{name} SKILL.md is empty"
    assert f"# Skill: {name}" in doc
    # Every skill states its purpose, its rules, and its anti-patterns.
    assert "## Purpose" in doc
    assert "## Anti-patterns" in doc


def test_registry_skills_all_exist_on_disk():
    available = set(list_available_skills())
    for agent, skills in AGENT_SKILLS.items():
        for skill in skills:
            assert skill in available, f"{agent} references unknown skill '{skill}'"


def test_load_agent_skills_concatenates_registered_docs():
    text = load_agent_skills("quotation_decision_agent")
    assert "## Skill: vendor_quotation" in text
    assert "## Skill: customer_quotation" in text
    assert "## Skill: compliance_and_risk" in text


def test_missing_skill_raises_in_strict_mode():
    with pytest.raises(FileNotFoundError):
        load_skills(["does_not_exist"])


def test_missing_skill_skipped_when_not_strict():
    # Non-strict skips unknown skills but still returns the valid ones.
    text = load_skills(["evaluation", "does_not_exist"], strict=False)
    assert "## Skill: evaluation" in text
