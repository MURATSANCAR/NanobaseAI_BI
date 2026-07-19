"""Scenario risk tiers."""

from __future__ import annotations

from enum import Enum


class RiskTier(str, Enum):
    A = "A"  # auto-publish after tests
    B = "B"  # requires review
    C = "C"  # expert approval
    D = "D"  # never auto-generate
