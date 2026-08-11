"""Precompiled query scenario engine."""

from __future__ import annotations

# 1.1.0 (2026-08-11): contract-complete generation — status columns are
# stamped from classification onto every status-bearing plan and the compiler
# refuses to guess (CompilerColumnUnknown). Plans from 1.0.0 could carry a
# hardcoded English "status" fallback (219/777 published erp scenarios shipped
# broken SQL against Turkish-columned tables). The bump also ensures rebuilds
# aren't idempotent-skipped against 1.0.0-generation published instances.
GENERATOR_VERSION = "1.1.0"

__all__ = ["GENERATOR_VERSION"]
