"""Functional validation records — required before SAP metric publish."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError

SAP_FUNCTIONAL_VALIDATION_REQUIRED = "SAP_FUNCTIONAL_VALIDATION_REQUIRED"


def assert_functional_approval(record: dict[str, Any] | None, *, metric_code: str) -> None:
    if not record:
        raise GatewayError(
            SAP_FUNCTIONAL_VALIDATION_REQUIRED,
            f"Functional validation missing for {metric_code}.",
            status=403,
        )
    status = str(record.get("status") or "").upper()
    if status not in ("APPROVED", "PUBLISHED"):
        raise GatewayError(
            SAP_FUNCTIONAL_VALIDATION_REQUIRED,
            f"Functional validation not APPROVED for {metric_code} (status={status}).",
            status=403,
        )
    roles = {
        str(record.get("validatedByRole") or ""),
        *(str(r) for r in (record.get("approverRoles") or [])),
    }
    if not any("FI" in r or "FUNCTIONAL" in r or "CONSULTANT" in r for r in roles):
        # Require explicit technical + functional dual approval fields when present
        if not record.get("technicalReviewer") or not record.get("functionalReviewer"):
            if "SAP_FI_CONSULTANT" not in roles and "SAP_FUNCTIONAL" not in roles:
                raise GatewayError(
                    SAP_FUNCTIONAL_VALIDATION_REQUIRED,
                    "SAP functional reviewer approval required.",
                    status=403,
                )
