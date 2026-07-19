"""Post-invoice domain rollout order (Faz 4).

Invoice go/no-go must pass before enabling these generators.
"""

from __future__ import annotations

from nanobase_api.scenario_engine.infrastructure.dialects import DOMAIN_ROLLOUT, next_domain_after

# Placeholder: each domain gets its own combination planner module when unlocked.
ENABLED_DOMAINS: frozenset[str] = frozenset({"invoice"})


def is_domain_enabled(domain: str) -> bool:
    return domain in ENABLED_DOMAINS


def unlock_next_domain(current: str = "invoice") -> str | None:
    nxt = next_domain_after(current)
    return nxt


def rollout_plan() -> list[str]:
    return list(DOMAIN_ROLLOUT)
