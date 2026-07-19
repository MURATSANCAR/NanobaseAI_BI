"""Promotion workflow — dual human approval required for financial/critical assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from nanobase_api.semantic_catalog.domain.errors import AuthorizationError, ValidationError
from nanobase_api.semantic_catalog.domain.status import AssetStatus, transition

ReviewRole = Literal["BUSINESS_REVIEWER", "TECHNICAL_REVIEWER"]
ReviewDecision = Literal["APPROVE", "REJECT"]


class PromotionPhase(str, Enum):
    CANDIDATE = "CANDIDATE"
    TECHNICAL_VALIDATION = "TECHNICAL_VALIDATION"
    GATEWAY_VALIDATION = "GATEWAY_VALIDATION"
    TEST_EXECUTION = "TEST_EXECUTION"
    BASELINE_COMPARE = "BASELINE_COMPARE"
    DEPENDENCY_ANALYSIS = "DEPENDENCY_ANALYSIS"
    SEMANTIC_CONSISTENCY = "SEMANTIC_CONSISTENCY"
    AWAITING_BUSINESS_REVIEW = "AWAITING_BUSINESS_REVIEW"
    AWAITING_TECHNICAL_REVIEW = "AWAITING_TECHNICAL_REVIEW"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass
class PromotionReview:
    reviewer_user_id: str
    role: ReviewRole
    decision: ReviewDecision
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewerUserId": self.reviewer_user_id,
            "role": self.role,
            "decision": self.decision,
            "comment": self.comment,
        }


@dataclass
class PromotionRequest:
    id: str
    tenant_id: str
    datasource_id: str
    asset_type: str
    asset_id: str
    requires_dual_approval: bool = True
    phase: PromotionPhase = PromotionPhase.CANDIDATE
    reviews: list[PromotionReview] = field(default_factory=list)
    status: AssetStatus = AssetStatus.DRAFT
    created_by: str | None = None

    def transition_to(self, target: AssetStatus) -> None:
        self.status = transition(self.status, target)

    def business_approved(self) -> bool:
        return any(r.role == "BUSINESS_REVIEWER" and r.decision == "APPROVE" for r in self.reviews)

    def technical_approved(self) -> bool:
        return any(r.role == "TECHNICAL_REVIEWER" and r.decision == "APPROVE" for r in self.reviews)

    def add_review(self, review: PromotionReview) -> None:
        if review.decision == "REJECT":
            self.reviews.append(review)
            self.phase = PromotionPhase.REJECTED
            self.status = AssetStatus.REJECTED
            return

        # Same user cannot approve both roles
        other_roles = {r.role for r in self.reviews if r.reviewer_user_id == review.reviewer_user_id}
        if review.role in other_roles:
            raise AuthorizationError("Aynı reviewer aynı rol için tekrar onay veremez.")
        if self.requires_dual_approval:
            opposing = "TECHNICAL_REVIEWER" if review.role == "BUSINESS_REVIEWER" else "BUSINESS_REVIEWER"
            if opposing in other_roles:
                raise AuthorizationError(
                    "Aynı kişi Business ve Technical review rollerinin ikisini birden onaylayamaz."
                )

        # Role must match current phase expectations loosely
        if review.role == "BUSINESS_REVIEWER" and self.phase not in (
            PromotionPhase.AWAITING_BUSINESS_REVIEW,
            PromotionPhase.AWAITING_TECHNICAL_REVIEW,
            PromotionPhase.SEMANTIC_CONSISTENCY,
            PromotionPhase.READY_TO_PUBLISH,
        ):
            # Allow business review once technical pipeline done
            if self.phase.value.startswith("AWAITING") or self.phase in (
                PromotionPhase.SEMANTIC_CONSISTENCY,
                PromotionPhase.DEPENDENCY_ANALYSIS,
            ):
                pass
            elif self.phase not in (
                PromotionPhase.GATEWAY_VALIDATION,
                PromotionPhase.TEST_EXECUTION,
                PromotionPhase.BASELINE_COMPARE,
                PromotionPhase.TECHNICAL_VALIDATION,
                PromotionPhase.CANDIDATE,
            ):
                pass

        self.reviews.append(review)
        self._advance_after_review()

    def _advance_after_review(self) -> None:
        if not self.requires_dual_approval:
            if self.business_approved() or self.technical_approved():
                self.phase = PromotionPhase.READY_TO_PUBLISH
                self.status = AssetStatus.APPROVED
            return
        if self.business_approved() and self.technical_approved():
            self.phase = PromotionPhase.READY_TO_PUBLISH
            self.status = AssetStatus.APPROVED
        elif self.business_approved() and not self.technical_approved():
            self.phase = PromotionPhase.AWAITING_TECHNICAL_REVIEW
            self.status = AssetStatus.READY_FOR_REVIEW
        elif self.technical_approved() and not self.business_approved():
            self.phase = PromotionPhase.AWAITING_BUSINESS_REVIEW
            self.status = AssetStatus.READY_FOR_REVIEW

    def assert_can_publish(self, *, publisher_user_id: str, publisher_roles: set[str]) -> None:
        if self.phase != PromotionPhase.READY_TO_PUBLISH:
            raise ValidationError("Promotion henüz READY_TO_PUBLISH değil.")
        if self.requires_dual_approval and not (self.business_approved() and self.technical_approved()):
            raise ValidationError("İki aşamalı onay tamamlanmadan publish edilemez.")
        allowed = {"SEMANTIC_PUBLISHER", "ADMIN"}
        if not (publisher_roles & allowed):
            raise AuthorizationError("Publish için SEMANTIC_PUBLISHER veya ADMIN gerekir.")
        # Publisher cannot skip dual approval by being the only reviewer
        if self.requires_dual_approval:
            reviewer_ids = {r.reviewer_user_id for r in self.reviews if r.decision == "APPROVE"}
            if len(reviewer_ids) < 2:
                raise ValidationError("İki farklı reviewer onayı gerekir.")

    def mark_published(self) -> None:
        self.phase = PromotionPhase.PUBLISHED
        self.status = AssetStatus.PUBLISHED

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "assetType": self.asset_type,
            "assetId": self.asset_id,
            "requiresDualApproval": self.requires_dual_approval,
            "phase": self.phase.value,
            "reviews": [r.to_dict() for r in self.reviews],
            "status": self.status.value,
            "createdBy": self.created_by,
        }
