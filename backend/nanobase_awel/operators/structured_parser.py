"""Parse LLM JSON into structured models (one format-repair attempt)."""

from __future__ import annotations

import json
import re
from typing import Any

from nanobase_awel.contracts.errors import OUTPUT_PARSE_FAILED, WorkflowError
from nanobase_awel.contracts.planning import PlanStatus, SqlPlan

try:
    import sqlglot
except ImportError:  # pragma: no cover
    sqlglot = None



def _parse_any_dialect(sql_text: str):
    """Parse as PostgreSQL first, then T-SQL (TOP N etc.) — plans may target SQL Server."""
    import sqlglot as _sg

    try:
        return _sg.parse_one(sql_text, read="postgres")
    except Exception:
        return _sg.parse_one(sql_text, read="tsql")

def extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    # strip markdown fences anywhere ("Here is the plan:\n```json ..." included)
    if "```" in text:
        text = re.sub(r"```(?:json|sql)?\s*", "", text, flags=re.I)
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    # Balanced scan: try to decode from each "{" instead of one greedy
    # first-{ .. last-} span (which breaks on prose containing braces or
    # multiple JSON objects).
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            data, _end = decoder.raw_decode(text, idx)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        idx = text.find("{", idx + 1)
    return {}


def _cut_at_semicolon_outside_strings(text: str) -> str:
    """Split at the first ';' that is not inside a quoted literal/identifier."""
    in_single = False
    in_double = False
    for i, ch in enumerate(text):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ";" and not in_single and not in_double:
            return text[:i]
    return text


def normalize_single_select_sql(sql: str | None) -> str | None:
    """Keep a single SELECT/WITH statement (Gateway rejects ';')."""
    if sql is None:
        return None
    text = str(sql).strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:sql|postgres)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    # Models sometimes emit literal backslash-escapes instead of real newlines.
    # Only unwrap when the text has no real newlines — otherwise the escapes
    # belong to string literals inside otherwise well-formed SQL.
    if ("\\n" in text or "\\t" in text) and "\n" not in text:
        text = (
            text.replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
        )
    m = re.search(r"(?is)\b((?:with|select)\b[\s\S]+)", text)
    if m:
        text = m.group(1).strip()
    # Drop trailing prose / extra statements after the first terminator
    # (';' inside quoted literals is not a terminator).
    if ";" in text:
        text = _cut_at_semicolon_outside_strings(text).strip()
    text = text.rstrip(";").strip()
    if not text:
        return None
    # Reject CoT prose that merely mentions WITH/SELECT (needs a FROM/clause shape).
    if not re.search(r"(?is)\b(from|where|group\s+by|order\s+by|limit)\b", text):
        if not re.match(r"(?is)^select\s+\d+", text):
            return None
    if "`" in text and " from " not in text.lower():
        return None
    return text


def _sql_parses(sql: str) -> bool:
    """Salvaged free-text SQL must at least parse — a truncated completion
    (finish_reason=length) otherwise flows downstream as a 'PLANNED' query."""
    if sqlglot is None:  # pragma: no cover
        return True
    try:
        _parse_any_dialect(sql)
        return True
    except Exception:
        return False


def parse_sql_plan(raw: str, *, prompt_version: str, model_profile: str, metadata_version: str = "") -> SqlPlan:
    parsed = extract_json_object(raw)
    if not parsed:
        # last chance: pull SELECT
        extracted = normalize_single_select_sql(raw)
        if extracted and not _sql_parses(extracted):
            raise WorkflowError(
                OUTPUT_PARSE_FAILED,
                "LLM çıktısı JSON değil ve içindeki SQL bütün değil (muhtemelen kesilmiş).",
            )
        if extracted:
            return SqlPlan(
                status=PlanStatus.PLANNED,
                sql=extracted,
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
    if status_raw in ("SUCCESS", "OK", "COMPLETE", "COMPLETED"):
        status_raw = "PLANNED"
    if status_raw in ("ERROR", "FAIL", "FAILURE"):
        # A model-declared error must not silently run just because sql is set.
        status_raw = "FAILED"
    try:
        status = PlanStatus(status_raw)
    except ValueError:
        status = PlanStatus.PLANNED if parsed.get("sql") else PlanStatus.FAILED

    sql_raw = parsed.get("sql")
    # Some models nest a second JSON plan inside the sql field.
    if isinstance(sql_raw, str) and sql_raw.strip().startswith("{"):
        nested = extract_json_object(sql_raw)
        if nested.get("status") or nested.get("sql") is not None:
            parsed = {**parsed, **nested}
            status_raw = str(parsed.get("status") or status_raw).upper()
            try:
                status = PlanStatus(status_raw)
            except ValueError:
                status = PlanStatus.PLANNED if parsed.get("sql") else PlanStatus.FAILED
            sql_raw = parsed.get("sql")
    sql = normalize_single_select_sql(sql_raw if sql_raw is not None else None)

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
        # Provenance is stamped by the pipeline; model-supplied values are
        # untrusted and must never overwrite audit metadata.
        promptVersion=prompt_version,
        modelProfile=model_profile,
        metadataVersion=metadata_version,
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
