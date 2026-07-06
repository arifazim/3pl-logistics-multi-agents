"""Minimal .env loader (no dependency) — used by the API and verification script.

Loads KEY=VALUE lines from the project-root .env into os.environ without overwriting
values already set in the real environment. Must be called before any code that reads
payment credentials (get_payment_stack) constructs its clients.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: str | Path | None = None) -> bool:
    """Load .env into os.environ. Returns True if a file was found."""
    env_path = Path(path) if path else ROOT / ".env"
    if not env_path.exists():
        return False
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val
    return True
