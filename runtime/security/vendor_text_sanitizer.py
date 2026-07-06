"""Sanitize vendor-supplied text before it reaches agent context.

This is the scoped security spine for the capstone: defend against prompt
injection via emails, portal quotes, and other vendor-origin text.
"""

import re
from dataclasses import dataclass
from typing import List, Tuple

INJECTION_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("ignore_instructions", re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I)),
    ("system_override", re.compile(r"^\s*system\s*:", re.I | re.M)),
    ("role_override", re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I)),
    ("jailbreak", re.compile(r"\b(DAN|jailbreak|developer\s+mode)\b", re.I)),
    ("delimiter_injection", re.compile(r"```\s*(system|assistant)", re.I)),
    ("hidden_instruction", re.compile(r"\[INST\]|\[/INST\]|<\|im_start\|>", re.I)),
]

MAX_VENDOR_TEXT_LENGTH = 8_000


@dataclass
class SanitizeResult:
    text: str
    flagged: bool
    reasons: List[str]
    truncated: bool


def sanitize_vendor_text(raw: str) -> SanitizeResult:
    """Return cleaned text and whether HITL escalation is recommended."""
    reasons: List[str] = []
    text = raw or ""
    truncated = False

    if len(text) > MAX_VENDOR_TEXT_LENGTH:
        text = text[:MAX_VENDOR_TEXT_LENGTH]
        truncated = True
        reasons.append("truncated: exceeded max length")

    for name, pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            reasons.append(f"injection_pattern:{name}")
            text = pattern.sub("[REDACTED]", text)

    flagged = len(reasons) > 0
    return SanitizeResult(text=text, flagged=flagged, reasons=reasons, truncated=truncated)
