"""Scenario status machine.

GENERATED → PUBLISHED is forbidden. Retrieval may only use PUBLISHED.
"""

from __future__ import annotations

from enum import Enum

from nanobase_api.scenario_engine.domain.errors import InvalidTransitionError


class ScenarioStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    GENERATED = "GENERATED"
    STATIC_VALIDATING = "STATIC_VALIDATING"
    STATIC_VALIDATED = "STATIC_VALIDATED"
    EXECUTION_VALIDATING = "EXECUTION_VALIDATING"
    EXECUTION_VALIDATED = "EXECUTION_VALIDATED"
    PERFORMANCE_VALIDATING = "PERFORMANCE_VALIDATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    STALE = "STALE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"
    PREPARING = "PREPARING"
    READY = "READY"
    FAILED = "FAILED"


RETRIEVAL_ALLOWED = frozenset({ScenarioStatus.PUBLISHED})

_TRANSITIONS: dict[ScenarioStatus, frozenset[ScenarioStatus]] = {
    ScenarioStatus.DISCOVERED: frozenset({ScenarioStatus.GENERATED, ScenarioStatus.ARCHIVED}),
    ScenarioStatus.GENERATED: frozenset(
        {ScenarioStatus.STATIC_VALIDATING, ScenarioStatus.REJECTED, ScenarioStatus.ARCHIVED}
    ),
    ScenarioStatus.STATIC_VALIDATING: frozenset(
        {ScenarioStatus.STATIC_VALIDATED, ScenarioStatus.FAILED, ScenarioStatus.REJECTED}
    ),
    ScenarioStatus.STATIC_VALIDATED: frozenset(
        {ScenarioStatus.EXECUTION_VALIDATING, ScenarioStatus.REJECTED}
    ),
    ScenarioStatus.EXECUTION_VALIDATING: frozenset(
        {ScenarioStatus.EXECUTION_VALIDATED, ScenarioStatus.FAILED, ScenarioStatus.REJECTED}
    ),
    ScenarioStatus.EXECUTION_VALIDATED: frozenset(
        {ScenarioStatus.PERFORMANCE_VALIDATING, ScenarioStatus.READY_FOR_REVIEW}
    ),
    ScenarioStatus.PERFORMANCE_VALIDATING: frozenset(
        {
            ScenarioStatus.READY_FOR_REVIEW,
            ScenarioStatus.APPROVED,
            ScenarioStatus.FAILED,
            ScenarioStatus.REJECTED,
        }
    ),
    ScenarioStatus.READY_FOR_REVIEW: frozenset(
        {ScenarioStatus.APPROVED, ScenarioStatus.REJECTED, ScenarioStatus.STATIC_VALIDATING}
    ),
    ScenarioStatus.APPROVED: frozenset(
        {ScenarioStatus.PREPARING, ScenarioStatus.PUBLISHED, ScenarioStatus.REJECTED}
    ),
    ScenarioStatus.PREPARING: frozenset({ScenarioStatus.READY, ScenarioStatus.FAILED}),
    ScenarioStatus.READY: frozenset({ScenarioStatus.PUBLISHED, ScenarioStatus.FAILED}),
    ScenarioStatus.PUBLISHED: frozenset(
        {ScenarioStatus.DEPRECATED, ScenarioStatus.STALE, ScenarioStatus.ARCHIVED}
    ),
    ScenarioStatus.DEPRECATED: frozenset({ScenarioStatus.ARCHIVED, ScenarioStatus.STALE}),
    ScenarioStatus.STALE: frozenset(
        {ScenarioStatus.GENERATED, ScenarioStatus.STATIC_VALIDATING, ScenarioStatus.ARCHIVED}
    ),
    ScenarioStatus.REJECTED: frozenset({ScenarioStatus.GENERATED, ScenarioStatus.ARCHIVED}),
    ScenarioStatus.FAILED: frozenset(
        {ScenarioStatus.GENERATED, ScenarioStatus.APPROVED, ScenarioStatus.ARCHIVED}
    ),
    ScenarioStatus.ARCHIVED: frozenset(),
}


def allowed_transitions(status: ScenarioStatus) -> frozenset[ScenarioStatus]:
    return _TRANSITIONS.get(status, frozenset())


def transition(current: ScenarioStatus, target: ScenarioStatus) -> ScenarioStatus:
    if current == target:
        return current
    # Explicit ban: never skip validation into published
    if current == ScenarioStatus.GENERATED and target == ScenarioStatus.PUBLISHED:
        raise InvalidTransitionError(current.value, target.value)
    if current == ScenarioStatus.DISCOVERED and target == ScenarioStatus.PUBLISHED:
        raise InvalidTransitionError(current.value, target.value)
    if target not in allowed_transitions(current):
        raise InvalidTransitionError(current.value, target.value)
    return target


def is_retrieval_eligible(status: ScenarioStatus | str) -> bool:
    if isinstance(status, str):
        try:
            status = ScenarioStatus(status)
        except ValueError:
            return False
    return status in RETRIEVAL_ALLOWED
