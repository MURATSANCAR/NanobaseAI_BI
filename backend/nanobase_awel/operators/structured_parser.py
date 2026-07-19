"""Parse LLM JSON into structured models (one format-repair attempt)."""

from __future__ import annotations

import json
import re
from typing import Any

from nanobase_awel.contracts.errors import OUTPUT_PARSE_FAILED, WorkflowError
from nanobase_awel.contracts.planning import PlanStatus, SqlPlan


def extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    # strip markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def parse_sql_plan(raw: str, *, prompt_version: str, model_profile: str, metadata_version: str = "") -> SqlPlan:
    parsed = extract_json_object(raw)
    if not parsed:
        # last chance: pull SELECT
        m = re.search(r"(SELECT\b[\s\S]{8,4000})", raw or "", re.I)
        if m:
            return SqlPlan(
                status=PlanStatus.PLANNED,
                sql=m.group(1).strip().rstrip(";"),
                dialect="postgres",
                tables=[],
                columns=[],
                confidence=0.4,
                promptVersion=prompt_version,
                modelProfile=model_profile,
                metadataVersion=metadata_version,
                warnings=["sql_extracted_from_free_text"],
            )
        raise WorkflowError(OUTPUT_PARSE_FAILED, "LLM çıktısı JSON olarak ayrıştırılamadı.")

    status_raw = str(parsed.get("status") or "PLANNED").upper()
    try:
        status = PlanStatus(status_raw)
    except ValueError:
        status = PlanStatus.PLANNED if parsed.get("sql") else PlanStatus.FAILED

    sql = parsed.get("sql")
    if sql is not None:
        sql = str(sql).strip().rstrip(";") or None

    plan = SqlPlan(
        status=status,
        sql=sql,
        dialect=str(parsed.get("dialect") or "postgres").replace("postgresql", "postgres"),
        tables=[str(t) for t in (parsed.get("tables") or []) if t],
        columns=[str(c) for c in (parsed.get("columns") or []) if c],
        functions=[str(f) for f in (parsed.get("functions") or []) if f],
        assumptions=parsed.get("assumptions") if isinstance(parsed.get("assumptions"), list) else [],
        warnings=parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else [],
        ambiguities=parsed.get("ambiguities") if isinstance(parsed.get("ambiguities"), list) else [],
        clarificationQuestion=parsed.get("clarificationQuestion") or parsed.get("clarification_question"),
        confidence=parsed.get("confidence"),
        promptVersion=str(parsed.get("promptVersion") or prompt_version),
        modelProfile=str(parsed.get("modelProfile") or model_profile),
        metadataVersion=str(parsed.get("metadataVersion") or metadata_version),
    )

    if plan.status == PlanStatus.PLANNED:
        if not plan.sql:
            raise WorkflowError(OUTPUT_PARSE_FAILED, "PLANNED durumundaunda SQL boş olamaz.")
    if plan.status == PlanStatus.AMBIGUOUS:
        plan.sql = None
        if not plan.clarificationQuestion and not plan.ambiguities:
            plan.ambiguities = ["Belirsizlik bildirildi ancak açıklama yok."]
            plan.clarificationQuestion = "Soruyu biraz daha netleştirebilir misiniz?"
    return plan
