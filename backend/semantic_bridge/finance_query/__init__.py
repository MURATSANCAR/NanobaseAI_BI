"""Fresh financial question engine; legacy SQL generation is never a fallback."""
from __future__ import annotations
from collections import OrderedDict
import hashlib
import json
import logging
import os
from pathlib import Path
import time
import uuid

from .contracts import CONTRACT_HASH as BASE_CONTRACT_HASH, METRICS, ContractError
from .planner import follows, build
from .executor import Executor
from .result_metadata import describe_columns, calculation_definitions
from .crm_query import CRM_CAPABILITIES
from .crm_reports import CRM_REPORT_CAPABILITIES
from .logo_reports import LOGO_REPORT_CAPABILITIES

CONTRACT_HASH = hashlib.sha256(json.dumps({"base": BASE_CONTRACT_HASH, "crm": CRM_CAPABILITIES,
    "crmReports": CRM_REPORT_CAPABILITIES, "logoReports": LOGO_REPORT_CAPABILITIES}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

log = logging.getLogger(__name__)
ENGINE_HASH = hashlib.sha256(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
    for p in Path(__file__).parent.glob("*.py")}, sort_keys=True).encode()).hexdigest()


def _tr(value):
    if value is None:
        return "Değer yok / hesaplanamadı"
    if isinstance(value, (float, int)):
        return f"{value:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
    return str(value)


def answer(runtime, question, thread_id, sample_size, execute, progress, username):
    context_key = (username, thread_id)
    previous = getattr(runtime, "_finance_plans", {}).get(context_key)
    if not follows(question):
        previous = None
    # Follow-up context belongs only to the new engine, never a legacy semantic plan.
    started = time.monotonic()
    engine = Executor(runtime)
    plan = None
    sql = None
    state = {"engine": "finance_contract_v1", "contractHash": CONTRACT_HASH, "engineCodeHash": ENGINE_HASH,
             "crmContractHash": hashlib.sha256(json.dumps(CRM_CAPABILITIES, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
             "legacyCatalogUsed": False, "legacySqlFallback": False, "readRetries": engine.read_retries,
             "stage": "planning"}

    def record(kind, summary, result=None, error=None):
        nonlocal sql
        state["sourcePeriods"] = engine.source_periods
        state["executions"] = engine.runs
        sql = "\n\n".join("-- " + run["source"] + "\n" + run["sql"] for run in engine.runs) or None
        return runtime.store.log_query(runtime.settings.tenant_id, runtime.settings.datasource_id, question,
            sql=sql, compiler="finance_contract_v1", catalog_version=None, resolved=state,
            executed=result is not None, row_count=result.get("totalRows") if result else None,
            latency_ms=round((time.monotonic()-started)*1000), error=error, username=username,
            thread_id=thread_id, answer_type=kind, answer_summary=summary,
            result_json=result, gate_json={"contractHash": CONTRACT_HASH, "engineCodeHash": ENGINE_HASH, "contractChecked": result is not None,
                                         "independentlyVerified": False})

    try:
        progress("understanding")
        state["planning"] = []
        model = runtime.llm_for("finance")
        state["model"] = getattr(getattr(model, "llm", model), "model", None)
        plan = build(question, model, previous, state["planning"])
        state["plan"] = plan.to_dict()
        if not execute:
            message = "Finans soru planı hazır; veri okunmadı."
            return {"id": uuid.uuid4().hex, "type": "CLARIFICATION", "explanation": message,
                    "threadId": thread_id, "semantic": state, "queryId": record("CLARIFICATION", message)}
        state["stage"] = "source_execution"
        progress("executing")
        rows = engine.execute(plan)
        state["stage"] = "result_processing"
        state["sourcePeriods"] = engine.source_periods
        state["executions"] = engine.runs
        fields = list(rows[0]) if rows else []
        if not rows and engine.output_fields:
            fields = engine.output_fields
        elif not rows:
            for d in plan.dimensions:
                fields.extend(["book_code", "book_name"] if d == "book" else ["customer_code", "customer_name"] if d == "customer" else [d])
            if len(plan.periods)>1:
                fields = ["period_start", "period_end_exclusive", *fields]
            fields += list(plan.metrics)
        numeric = set(plan.metrics) | {d.id for d in plan.derived}
        if plan.comparison:
            numeric = {"base_value", "target_value", plan.comparison.id}
        if plan.crm or getattr(plan, "sections", ()) or getattr(plan, "logo_report", None) or getattr(plan, "crm_report", None):
            numeric = set(getattr(engine, "numeric_fields", []))
        for spec in getattr(plan, "analytics", ()):
            if spec["op"] == "contribution":
                numeric.update(spec["id"]+suffix for suffix in ("_group_total", "_share_pct", "_cumulative_pct"))
        if any(set(row) != set(fields) for row in rows) or any(m not in fields for m in numeric):
            raise ContractError("Cevabın kolonları ölçü sözleşmesini sağlamıyor.", code="SOURCE_CONTRACT_VIOLATION")
        columns = describe_columns(plan, fields, numeric)
        labels = {column["name"]: column for column in columns}
        definition_items = calculation_definitions(plan)
        sql = "\n\n".join("-- " + run["source"] + "\n" + run["sql"] for run in engine.runs)
        notes = list(dict.fromkeys(engine.notes))
        if "author" in plan.dimensions:
            notes.append("Yazar kırılımı kitap künyesindeki yazar metnidir; kişi kimliği ve telif sahipliği çıkarımı yapılmaz.")
        definitions = " ".join(definition_items)
        def label(k):
            return labels.get(k, {}).get("label", METRICS[k].label if k in METRICS else k)
        if len(rows) == 1 and not plan.dimensions and not plan.crm and not engine.section_results:
            summary = " · ".join(f"{label(k)}: {_tr(v)} {labels.get(k, {}).get('unit', METRICS[k].unit if k in METRICS else '')}".strip() for k,v in rows[0].items())
        else:
            limit = plan.crm.get("limit") if plan.crm else plan.limit
            summary = f"{len(rows)} satır. " + (f"İstenen ilk {limit} sonuç gösteriliyor. " if limit else "")
            if rows:
                summary += "İlk satır: " + " · ".join(f"{label(k)}: {_tr(v)}" for k,v in rows[0].items())
        if definitions:
            summary += " Hesap tanımı: " + definitions
        if notes:
            summary += " Veri notu: " + " ".join(notes)
        kind = "PARTIAL_ANSWER" if engine.gaps or not engine.coverage_complete else "TEXT_TO_SQL"
        if engine.section_results:
            summary = f"{len(engine.section_results)} rapor bölümü hazır. " + " · ".join(f"{s['title']}: {s['totalRows']} satır" if s["status"] == "COMPLETE" else f"{s['title']}: tamamlanamadı" for s in engine.section_results)
        if engine.gaps:
            summary += " Kesin cevaplanamayan kısımlar: " + " · ".join(g["reason"] for g in engine.gaps)
        state["gaps"] = engine.gaps
        rid = uuid.uuid4().hex
        result = {"id": rid, "columns": columns, "records": rows, "totalRows": len(rows), "truncated": False,
                  "physicalSql": sql, "computedAt": time.time(), "cached": False,
                  "dbMs": sum(x["dbMs"] for x in engine.runs),
                  "dataNotes": [{"message": n, "severity": "info" if engine.coverage_complete else "warn"} for n in notes],
                  "dataCoverage": engine.source_periods, "definitions": definition_items,
                  "sourceComplete": engine.coverage_complete}
        if engine.section_results:
            result["sections"] = engine.section_results
        result["gaps"] = engine.gaps
        progress("presenting")
        if not engine.section_results and not plan.logo_report and not plan.crm_report:
            runtime.attach_widget(result, question)
        runtime.remember_result(result, question=question, sql=sql)
        state["stage"] = "complete"
        qid = record(kind, summary, result)
        if not hasattr(runtime, "_finance_plans"):
            runtime._finance_plans = OrderedDict()
        runtime._finance_plans[context_key] = {"question": question, "plan": plan.to_dict()}
        while len(runtime._finance_plans)>200:
            runtime._finance_plans.popitem(last=False)
        return {**result, "type": kind, "sql": sql, "resultId": rid, "summary": summary,
                "records": rows[:max(1,min(sample_size,500))], "shownRows": min(len(rows),max(1,min(sample_size,500))),
                "rowCount": len(rows), "threadId": thread_id, "queryId": qid, "semantic": state,
                "answerQuality": {"contractChecked": True, "independentlyVerified": False,
                                  "sourceComplete": engine.coverage_complete, "contractHash": CONTRACT_HASH}}
    except ContractError as exc:
        message = str(exc)
        status = exc.code
        kind = "CLARIFICATION" if status == "NEEDS_CLARIFICATION" else status
        state["outcome"] = status
        state["failureStage"] = state["stage"]
        qid = record(kind, message, error=message)
        return {"id": uuid.uuid4().hex, "type": kind, "needs_clarification": status == "NEEDS_CLARIFICATION",
                "explanation": message, "threadId": thread_id, "semantic": state, "queryId": qid}
    except Exception as exc:
        from semantic_bridge import access
        if isinstance(exc, access.DataScopeError):
            raise
        log.exception("finance contract question failed")
        phase = state["stage"]
        if phase == "planning":
            kind = "PLAN_INVALID"
            message = "Finans sorusunun planlama veya model hizmeti işlemi tamamlanamadı; veri kaynaklarına sorgu gönderilmedi."
        elif phase == "source_execution":
            kind = "DATA_SOURCE_UNAVAILABLE"
            message = "Finans cevabı doğrulanamadı; veri kaynağını okuma veya hesap yürütme işlemi tamamlanamadı."
        else:
            kind = "PLAN_INVALID"
            message = "Finans sonucu hazırlanırken doğrulama tamamlanamadı; sonuç sunulmadı."
        state["outcome"] = kind
        state["failureStage"] = phase
        # Details remain in restricted server logs, never the user-visible query record.
        qid = record(kind, message, error=message)
        return {"id": uuid.uuid4().hex, "type": kind, "explanation": message,
                "threadId": thread_id, "semantic": state, "queryId": qid}
