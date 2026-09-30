"""Fresh financial question engine; legacy SQL generation is never a fallback."""
from __future__ import annotations
from collections import OrderedDict
import hashlib
import json
import logging
import os
import time
import uuid

from .contracts import CONTRACT_HASH, METRICS, ContractError
from .planner import claims, build
from .executor import Executor

log = logging.getLogger(__name__)


def _tr(value):
    if isinstance(value, (float, int)):
        return f"{value:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
    return str(value)


def answer(runtime, question, thread_id, sample_size, execute, progress, username):
    if os.environ.get("FINANCE_QUERY_MODE", "off") != "contract":
        return None
    previous = getattr(runtime, "_finance_plans", {}).get(thread_id)
    if not claims(question) and previous is None:
        return None
    # Follow-up context belongs only to the new engine, never a legacy semantic plan.
    started = time.monotonic()
    engine = Executor(runtime)
    plan = None
    sql = None
    state = {"engine": "finance_contract_v1", "contractHash": CONTRACT_HASH,
             "legacyCatalogUsed": False, "legacySqlFallback": False}

    def record(kind, summary, result=None, error=None):
        return runtime.store.log_query(runtime.settings.tenant_id, runtime.settings.datasource_id, question,
            sql=sql, compiler="finance_contract_v1", catalog_version=None, resolved=state,
            executed=result is not None, row_count=result.get("totalRows") if result else None,
            latency_ms=round((time.monotonic()-started)*1000), error=error, username=username,
            thread_id=thread_id, answer_type=kind, answer_summary=summary,
            result_json=result, gate_json={"contractHash": CONTRACT_HASH, "contractChecked": result is not None,
                                         "independentlyVerified": False})

    try:
        progress("understanding")
        plan = build(question, runtime.llm_for("finance"), previous)
        state["plan"] = plan.to_dict()
        if not execute:
            message = "Finans soru planı hazır; veri okunmadı."
            return {"id": uuid.uuid4().hex, "type": "CLARIFICATION", "explanation": message,
                    "threadId": thread_id, "semantic": state, "queryId": record("CLARIFICATION", message)}
        progress("executing")
        rows = engine.execute(plan)
        state["sourcePeriods"] = engine.source_periods
        state["executions"] = engine.runs
        fields = list(rows[0]) if rows else []
        if not rows:
            for d in plan.dimensions:
                fields.extend(["book_code", "book_name"] if d == "book" else ["customer_code", "customer_name"] if d == "customer" else [d])
            if len(plan.periods)>1:
                fields = ["period_start", "period_end_exclusive", *fields]
            fields += list(plan.metrics)
        if any(set(row) != set(fields) for row in rows) or any(m not in fields for m in plan.metrics):
            raise ContractError("Cevabın kolonları ölçü sözleşmesini sağlamıyor.")
        columns = [{"name": k, "type": "float" if k in plan.metrics else "str",
                    **({"label": METRICS[k].label, "unit": METRICS[k].unit} if k in METRICS else {})} for k in fields]
        sql = "\n\n".join("-- " + run["source"] + "\n" + run["sql"] for run in engine.runs)
        notes = list(dict.fromkeys(engine.notes))
        if "author" in plan.dimensions:
            notes.append("Yazar kırılımı kitap künyesindeki yazar metnidir; kişi kimliği ve telif sahipliği çıkarımı yapılmaz.")
        definitions = " ".join(METRICS[m].definition for m in plan.metrics)
        if len(rows) == 1 and not plan.dimensions and len(plan.periods)==1 or len(rows)==1 and not plan.periods:
            summary = " · ".join(f"{METRICS[m].label}: {_tr(rows[0][m])} {METRICS[m].unit}" for m in plan.metrics)
        else:
            summary = f"{len(rows)} satır. " + (f"İstenen ilk {plan.limit} sonuç gösteriliyor. " if plan.limit else "")
            if rows:
                summary += "İlk satır: " + " · ".join(f"{METRICS[k].label if k in METRICS else k}: {_tr(v)}" for k,v in rows[0].items())
        summary += " Hesap tanımı: " + definitions
        if notes:
            summary += " Veri notu: " + " ".join(notes)
        rid = uuid.uuid4().hex
        result = {"id": rid, "columns": columns, "records": rows, "totalRows": len(rows), "truncated": False,
                  "physicalSql": sql, "computedAt": time.time(), "cached": False,
                  "dbMs": sum(x["dbMs"] for x in engine.runs),
                  "dataNotes": [{"message": n, "severity": "warn"} for n in notes],
                  "dataCoverage": engine.source_periods}
        progress("presenting")
        runtime.attach_widget(result, question)
        runtime.remember_result(result, question=question, sql=sql)
        qid = record("TEXT_TO_SQL", summary, result)
        if not hasattr(runtime, "_finance_plans"):
            runtime._finance_plans = OrderedDict()
        runtime._finance_plans[thread_id] = {"question": question, "plan": plan.to_dict()}
        while len(runtime._finance_plans)>200:
            runtime._finance_plans.popitem(last=False)
        return {**result, "type": "TEXT_TO_SQL", "sql": sql, "resultId": rid, "summary": summary,
                "records": rows[:max(1,min(sample_size,500))], "shownRows": min(len(rows),max(1,min(sample_size,500))),
                "rowCount": len(rows), "threadId": thread_id, "queryId": qid, "semantic": state,
                "answerQuality": {"contractChecked": True, "independentlyVerified": False,
                                  "sourceComplete": not notes, "contractHash": CONTRACT_HASH}}
    except ContractError as exc:
        message = str(exc)
        qid = record("CLARIFICATION", message, error=message)
        return {"id": uuid.uuid4().hex, "type": "CLARIFICATION", "needs_clarification": True,
                "explanation": message, "threadId": thread_id, "semantic": state, "queryId": qid}
    except Exception as exc:
        from semantic_bridge import access
        if isinstance(exc, access.DataScopeError):
            raise
        log.exception("finance contract question failed")
        message = "Finans cevabı doğrulanamadı; kaynak bağlantısı veya sözleşme yürütmesi tamamlanamadı."
        qid = record("DATA_SOURCE_UNAVAILABLE", message, error=type(exc).__name__ + ": " + str(exc)[:600])
        return {"id": uuid.uuid4().hex, "type": "DATA_SOURCE_UNAVAILABLE", "explanation": message,
                "threadId": thread_id, "semantic": state, "queryId": qid}
