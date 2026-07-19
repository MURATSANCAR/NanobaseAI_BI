"""Scenario engine test defaults — slim combinations + memory store."""

from __future__ import annotations

import os

# Keep unit tests fast; production defaults remain full scale.
os.environ.setdefault("SCENARIO_COMBINATION_SCALE", "slim")
os.environ.setdefault("SCENARIO_SQL_DISABLED", "1")
os.environ.setdefault("SCENARIO_ALLOW_DETERMINISTIC_EMBED", "1")
os.environ.setdefault("SCENARIO_REQUIRE_QDRANT", "0")
os.environ.setdefault("SCENARIO_REQUIRE_LIVE_VALIDATION", "0")
os.environ.setdefault("SCENARIO_REQUIRE_SQL", "0")
