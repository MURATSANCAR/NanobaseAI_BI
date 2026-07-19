from __future__ import annotations

from nanobase_awel.contracts.errors import VALIDATION_ERROR, WorkflowError
from nanobase_awel.contracts.planning import SqlPlanningRequest
from nanobase_awel.contracts.repair import SqlRepairRequest
from nanobase_awel.contracts.errors import NON_REPAIRABLE_CODES, REPAIR_LIMIT_EXCEEDED, REPAIR_NOT_ALLOWED


def validate_planning_request(req: SqlPlanningRequest) -> None:
    if not (req.question or "").strip():
        raise WorkflowError(VALIDATION_ERROR, "Soru boş olamaz.")
    if len(req.question.encode("utf-8")) > 8192:
        raise WorkflowError(VALIDATION_ERROR, "Soru uzunluk limiti aşıldı.")
    if not req.datasourceId:
        raise WorkflowError(VALIDATION_ERROR, "datasourceId gerekli.")
    if req.dialect not in ("postgres", "postgresql"):
        # postgres-first
        if req.dialect not in ("oracle", "hana"):
            raise WorkflowError(VALIDATION_ERROR, "Desteklenmeyen dialect.")


def validate_repair_request(req: SqlRepairRequest) -> None:
    if req.attempt < 1 or req.attempt > 2:
        raise WorkflowError(REPAIR_LIMIT_EXCEEDED, "Repair attempt limiti aşıldı.")
    code = req.gatewayError.code
    if code in NON_REPAIRABLE_CODES:
        raise WorkflowError(REPAIR_NOT_ALLOWED, f"Bu hata için repair yok: {code}")
    if not req.previousSql.strip():
        raise WorkflowError(VALIDATION_ERROR, "previousSql gerekli.")
