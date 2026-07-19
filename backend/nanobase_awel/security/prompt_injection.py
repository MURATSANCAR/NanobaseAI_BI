"""Lightweight prompt-injection detectors for adversarial tests."""

from __future__ import annotations

INJECTION_MARKERS = (
    "ignore all instructions",
    "önceki talimatları unut",
    "forget previous",
    "system prompt",
    "doğrudan db",
    "query gateway'i kullanma",
    "bypass gateway",
    "drop table",
    "pg_sleep",
)


def looks_like_injection(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in INJECTION_MARKERS)
