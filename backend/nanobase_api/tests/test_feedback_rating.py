#!/usr/bin/env python3
"""Feedback rating validation (-1|0|1) + comment rules."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("NANOBASE_ENV", "development")


def _validate(rating: object, comment: str | None, question: str = "q") -> tuple[bool, str]:
    """Mirror app.py query_feedback rules for unit coverage without ASGI."""
    try:
        r = int(rating)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False, "question and rating (-1|0|1) required"
    c = (comment or "").strip()
    if not question or r not in (-1, 0, 1):
        return False, "question and rating (-1|0|1) required"
    if r in (-1, 0) and len(c) < 5:
        return False, "comment required"
    return True, "ok"


def test_feedback_rules():
    assert _validate(1, None)[0]
    assert _validate(0, "ab")[0] is False
    assert _validate(0, "enough detail here")[0]
    assert _validate(-1, "wrong total amount")[0]
    assert _validate(2, "x")[0] is False
    print("feedback_rules ok")


if __name__ == "__main__":
    test_feedback_rules()
