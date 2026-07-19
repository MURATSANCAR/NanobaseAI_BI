"""Semantic asset status machine.

DRAFT → PUBLISHED is forbidden. All publishes go through validation + review.
"""

from __future__ import annotations

from enum import Enum

from nanobase_api.semantic_catalog.domain.errors import InvalidTransitionError


class AssetStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"
    STALE = "STALE"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"
    PREPARING = "PREPARING"
    READY = "READY"
    FAILED = "FAILED"


# Production retrieval may only use these.
RETRIEVAL_ALLOWED = frozenset({AssetStatus.PUBLISHED})

_TRANSITIONS: dict[AssetStatus, frozenset[AssetStatus]] = {
    AssetStatus.DRAFT: frozenset({AssetStatus.VALIDATING, AssetStatus.ARCHIVED, AssetStatus.REJECTED}),
    AssetStatus.VALIDATING: frozenset(
        {AssetStatus.VALIDATION_FAILED, AssetStatus.READY_FOR_REVIEW, AssetStatus.FAILED}
    ),
    AssetStatus.VALIDATION_FAILED: frozenset({AssetStatus.DRAFT, AssetStatus.ARCHIVED}),
    AssetStatus.READY_FOR_REVIEW: frozenset(
        {AssetStatus.APPROVED, AssetStatus.REJECTED, AssetStatus.VALIDATING}
    ),
    AssetStatus.APPROVED: frozenset({AssetStatus.PUBLISHED, AssetStatus.PREPARING, AssetStatus.REJECTED}),
    AssetStatus.PREPARING: frozenset({AssetStatus.READY, AssetStatus.FAILED}),
    AssetStatus.READY: frozenset({AssetStatus.PUBLISHED, AssetStatus.FAILED}),
    AssetStatus.PUBLISHED: frozenset(
        {AssetStatus.DEPRECATED, AssetStatus.STALE, AssetStatus.ARCHIVED}
    ),
    AssetStatus.DEPRECATED: frozenset({AssetStatus.ARCHIVED, AssetStatus.STALE}),
    AssetStatus.STALE: frozenset({AssetStatus.DRAFT, AssetStatus.VALIDATING, AssetStatus.ARCHIVED}),
    AssetStatus.REJECTED: frozenset({AssetStatus.DRAFT, AssetStatus.ARCHIVED}),
    AssetStatus.FAILED: frozenset({AssetStatus.DRAFT, AssetStatus.APPROVED, AssetStatus.ARCHIVED}),
    AssetStatus.ARCHIVED: frozenset(),
}


def allowed_transitions(status: AssetStatus) -> frozenset[AssetStatus]:
    return _TRANSITIONS.get(status, frozenset())


def transition(current: AssetStatus, target: AssetStatus) -> AssetStatus:
    """Apply a status transition or raise InvalidTransitionError."""
    if current == target:
        return current
    # Explicit ban: never draft → published
    if current == AssetStatus.DRAFT and target == AssetStatus.PUBLISHED:
        raise InvalidTransitionError(current.value, target.value)
    if target not in allowed_transitions(current):
        raise InvalidTransitionError(current.value, target.value)
    return target


def is_retrieval_eligible(status: AssetStatus | str) -> bool:
    if isinstance(status, str):
        try:
            status = AssetStatus(status)
        except ValueError:
            return False
    return status in RETRIEVAL_ALLOWED
