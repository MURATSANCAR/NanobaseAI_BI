"""nanobase-result-explain-v1 — masked/limited result only."""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Callable

from nanobase_awel import EXPLAIN_WORKFLOW
from nanobase_awel.contracts.explanation import ResultExplanation, ResultExplanationRequest
from nanobase_awel.operators.answer_fidelity_validator import (
    deterministic_fallback_answer,
    validate_answer_fidelity,
)
from nanobase_awel.operators.llm_operator import chat_completion
from nanobase_awel.operators.model_queue import progress_sink
from nanobase_awel.operators.prompt_builder import render_simple, result_explain_prompts
from nanobase_awel.operators.result_summarizer import summarize_result
from nanobase_awel.operators.structured_parser import extract_json_object

# Total wall-clock caps. Streaming shows progress, so it may run longer than
# the buffered path before falling back to the deterministic answer.
EXPLAIN_TIMEOUT_SEC = float(os.environ.get("EXPLAIN_TIMEOUT_SEC", "25"))
EXPLAIN_STREAM_TIMEOUT_SEC = float(os.environ.get("EXPLAIN_STREAM_TIMEOUT_SEC", "90"))

_ANSWER_KEY_RE = re.compile(r'"answer"\s*:\s*"')

_JSON_UNESCAPE = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
    '"': '"',
    "\\": "\\",
    "/": "/",
}


class AnswerStreamExtractor:
    """Incrementally pull the top-level ``"answer"`` string value out of a
    *streaming* JSON completion and forward only its decoded text.

    The explain contract is JSON ({answer, insights, warnings}); raw deltas
    would show JSON syntax to the user, so we surface just the answer text as
    it is generated. Non-JSON output simply never matches → nothing streams
    and the buffered fallback path applies unchanged.
    """

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._buf = ""
        self._sent = 0
        self._done = False

    def feed(self, chunk: str) -> None:
        if self._done or not chunk:
            return
        self._buf += chunk
        m = _ANSWER_KEY_RE.search(self._buf)
        if not m:
            return
        decoded, closed = self._decode_from(m.end())
        if len(decoded) > self._sent:
            delta = decoded[self._sent :]
            self._sent = len(decoded)
            try:
                self._emit(delta)
            except Exception:
                self._done = True
        if closed:
            self._done = True

    def _decode_from(self, start: int) -> tuple[str, bool]:
        out: list[str] = []
        i = start
        buf = self._buf
        while i < len(buf):
            ch = buf[i]
            if ch == "\\":
                if i + 1 >= len(buf):
                    break  # escape split across chunks — wait for more
                nxt = buf[i + 1]
                if nxt == "u":
                    if i + 6 > len(buf):
                        break  # partial \uXXXX — wait for more
                    try:
                        out.append(chr(int(buf[i + 2 : i + 6], 16)))
                    except ValueError:
                        out.append(buf[i : i + 6])
                    i += 6
                    continue
                out.append(_JSON_UNESCAPE.get(nxt, nxt))
                i += 2
                continue
            if ch == '"':
                return "".join(out), True
            out.append(ch)
            i += 1
        return "".join(out), False


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
        # Stream the answer text to the UI when a progress sink is attached
        # (chat SSE); httpx stream timeouts are per-read, so wrap with a total
        # wall-clock cap — under CPU contention prefer deterministic fallback
        # over multi-minute Qwen stalls that surface as hard chat errors.
        sink = progress_sink.get()
        on_delta = None
        total_timeout = EXPLAIN_TIMEOUT_SEC
        if sink is not None:
            extractor = AnswerStreamExtractor(
                lambda t: sink.put_nowait({"phase": "token", "delta": t})
            )
            on_delta = extractor.feed
            total_timeout = EXPLAIN_STREAM_TIMEOUT_SEC
        raw = await asyncio.wait_for(
            chat_completion(
                system,
                user,
                temperature=0.1,
                max_tokens=800,
                timeout_s=total_timeout,
                on_delta=on_delta,
            ),
            timeout=total_timeout,
        )
        parsed = extract_json_object(raw)
        answer = str(parsed.get("answer") or "").strip()
        insights = parsed.get("insights") if isinstance(parsed.get("insights"), list) else []
        warnings = parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else []
        if answer:
            fidelity_ok, problems = validate_answer_fidelity(
                answer,
                summary=summary,
                rows=req.rows,
                question=req.question,
                sql=req.executedSql,
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
