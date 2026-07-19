#!/usr/bin/env python3
"""Unit checks for schema-indexer fingerprint (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "tools" / "schema-indexer"
sys.path.insert(0, str(PKG))

from fingerprint import sha256_fingerprint  # noqa: E402


def test_stable():
    a = sha256_fingerprint("bi_reporting", "public", "invoice", "remaining_amount", "numeric", False, "desc", "fk")
    b = sha256_fingerprint("bi_reporting", "public", "invoice", "remaining_amount", "numeric", False, "desc", "fk")
    assert a == b
    assert len(a) == 64


def test_changes_on_desc():
    a = sha256_fingerprint("ds", "s", "t", "c", "int", True, "old", "")
    b = sha256_fingerprint("ds", "s", "t", "c", "int", True, "new", "")
    assert a != b


if __name__ == "__main__":
    test_stable()
    test_changes_on_desc()
    print("fingerprint ok")
