"""Load agent skill markdown from skills/{name}/SKILL.md.

Skills are organized skill-centric: each lives in its own directory under `skills/`
with a `SKILL.md` describing its purpose, rules, output contract, and anti-patterns.
Agents declare the skills they load either via their `.agy` `skills:` list or via the
`AGENT_SKILLS` registry below.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / "skills"

# Explicit agent -> skills mapping. Mirrors the `skills:` lists in agy/agents/*.agy and
# documents which skill contracts each agent in the fleet is expected to honor.
AGENT_SKILLS: dict[str, list[str]] = {
    "quotation_decision_agent": [
        "vendor_quotation",
        "customer_quotation",
        "compliance_and_risk",
    ],
    "orchestrator_agent": ["operations_insight"],
    "commerce_agent": ["commerce", "vendor_quotation"],
    "human_supervisor_agent": ["human_supervisor", "compliance_and_risk"],
    "operations_insight_agent": ["operations_insight"],
    "load_planning_agent": ["load_planning"],
    "a2ui_concierge_agent": ["a2ui_concierge"],
    "security_sentinel_agent": ["security_sentinel"],
    # evaluation skill is used by QuotationDecisionAgent's trajectory_evaluator tool,
    # not by a standalone agent — loaded on demand via load_skill("evaluation").
}


def skill_path(name: str) -> Path:
    """Return the path to a skill's SKILL.md (may not exist)."""
    return SKILLS_DIR / name / "SKILL.md"


def list_available_skills() -> list[str]:
    """Discover every skill directory that contains a SKILL.md, sorted by name."""
    if not SKILLS_DIR.exists():
        return []
    return sorted(p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md") if p.is_file())


def load_skill(name: str) -> str:
    """Load a single skill document. Raises if the skill is missing."""
    path = skill_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"Skill '{name}' not found at {path}. "
            f"Available skills: {', '.join(list_available_skills()) or '(none)'}"
        )
    return path.read_text(encoding="utf-8")


def load_skills(skill_names: list[str], strict: bool = True) -> str:
    """Concatenate skill documents for agent instruction context.

    With strict=True (default) a missing skill raises FileNotFoundError so a typo in an
    agent's skill list fails loudly instead of silently dropping instructions.
    """
    sections: list[str] = []
    for name in skill_names:
        if not skill_path(name).exists():
            if strict:
                raise FileNotFoundError(
                    f"Skill '{name}' not found at {skill_path(name)}. "
                    f"Available skills: {', '.join(list_available_skills()) or '(none)'}"
                )
            continue
        sections.append(f"## Skill: {name}\n\n{load_skill(name)}")
    return "\n\n---\n\n".join(sections)


def load_agent_skills(agent_name: str, strict: bool = True) -> str:
    """Load the concatenated skills registered for an agent in AGENT_SKILLS."""
    return load_skills(AGENT_SKILLS.get(agent_name, []), strict=strict)
