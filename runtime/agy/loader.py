"""Load .agy agent definition files (prompt, skills, tools)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
AGY_DIR = ROOT / "agy" / "agents"


def load_agy(agent_name: str) -> dict[str, Any]:
    """Load agent definition from agy/agents/{name}.agy"""
    path = AGY_DIR / f"{agent_name}.agy"
    if not path.exists():
        raise FileNotFoundError(f"Agent definition not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data.get("prompt"):
        raise ValueError(f"Agent {agent_name} missing prompt in {path}")
    return data
