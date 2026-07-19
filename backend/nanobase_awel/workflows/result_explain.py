"""nanobase-result-explain-v1 — masked/limited result only."""

from __future__ import annotations

import json

from nanobase_awel import EXPLAIN_WORKFLOW
from nanobase_awel.contracts.explanation import ResultExplanation, ResultExplanationRequest
from nanobase_awel.operators.answer_fidelity_validator import (
    deterministic_fallback_answer,
    validate_answer_fidelity,
)
from nanobase_awel.operators.llm_operator import chat_completion
from nanobase_awel.operators.prompt_builder import render_simple, result_explain_prompts
from nanobase_awel.operators.result_summarizer import summarize_result
from nanobase_awel.operators.structured_parser import extract_json_object


async def run_result_explain(req: ResultExplanationRequest) -> ResultExplanation:
    # normalize columns
    col_names = []
    for c in req.columns:
        col_names.append(str(c.get("name") if isinstance(c, dict) else c))

    summary = summarize_result(col_names, req.rows, truncated=req.truncated, max_sample=100)
    system, user_tpl = result_explain_prompts()
    user = render_simple(
        user_tpl,
        question=req.question,
        sql=req.executedSql,
        summary=json.dumps(
            {
                "rowCount": summary["rowCount"],
                "truncated": summary["truncated"],
                "columns": summary["columns"],
                "numericStatistics": summary["numericStatistics"],
            },
            ensure_ascii=False,
            default=str,
        ),
        sample_rows=json.dumps(summary["sampleRows"][:20], ensure_ascii=False, default=str),
        truncated=str(req.truncated),
    )

    used_fallback = False
    fidelity_ok = True
    answer = ""
    insights: list[str] = []
    warnings: list[str] = []

    try:
        # Short timeout: under CPU contention prefer deterministic fallback
        # over multi-minute Qwen stalls that surface as hard chat errors.
        raw = await chat_completion(
            system, user, temperature=0.1, max_tokens=800, timeout_s=25.0
        )
        parsed = extract_json_object(raw)
        answer = str(parsed.get("answer") or "").strip()
        insights = parsed.get("insights") if isinstance(parsed.get("insights"), list) else []
        warnings = parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else []
        if answer:
            fidelity_ok, problems = validate_answer_fidelity(
                answer, summary=summary, rows=req.rows
            )
            if not fidelity_ok:
                used_fallback = True
                answer = deterministic_fallback_answer(
                    summary=summary,
                    columns=col_names,
                    rows=req.rows,
                    truncated=req.truncated,
                )
                warnings = [*warnings, "fidelity_fallback", *problems[:3]]
        else:
            used_fallback = True
            answer = deterministic_fallback_answer(
                summary=summary,
                columns=col_names,
                rows=req.rows,
                truncated=req.truncated,
            )
    except Exception:
        used_fallback = True
        answer = deterministic_fallback_answer(
            summary=summary,
            columns=col_names,
            rows=req.rows,
            truncated=req.truncated,
        )
        warnings = ["explain_failed_fallback"]

    if req.truncated and not any("kesil" in str(w).lower() or "truncat" in str(w).lower() for w in warnings):
        warnings = [*warnings, "Sonuç satır limiti nedeniyle kesilmiş olabilir."]

    return ResultExplanation(
        workflow=EXPLAIN_WORKFLOW,
        answer=answer,
        insights=[str(i) for i in insights],
        warnings=[str(w) for w in warnings],
        fidelityPassed=fidelity_ok and not used_fallback,
        usedFallback=used_fallback,
        summary={
            "rowCount": summary["rowCount"],
            "truncated": summary["truncated"],
            "numericStatistics": summary["numericStatistics"],
        },
    )
