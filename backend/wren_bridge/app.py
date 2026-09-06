"""NanobaseAI BI — Wren bridge (:8794).

Serves the cockpit's semantic-engine contract on top of the WrenAI main-line engine
(`wrenai` package, in-process DataFusion/MDL engine — no wren-ui, no wren-ai-service):

    POST /api/v1/run_sql   {sql, limit}            → {id, columns[{name,type}], records[], totalRows}
    POST /api/v1/ask       {question, threadId?}   → {id, sql, summary, threadId, explanation?}
    GET  /api/v1/engine                            → {dataSource, models, deployed, project}
    GET  /health

`ask` = the orchestration the legacy wren-ai-service used to do, now driven by our own LLM
(OpenAI-compatible endpoint, the A40 llama.cpp server) over Wren's context tools:
rules (knowledge/rules) → recalled NL→SQL pairs (knowledge/sql) → schema context (get_context / describe_schema)
→ LLM writes MDL SQL → dry_run (structured error → one repair round) → run_sql → short Turkish summary.
The LLM never sees credentials; SQL is validated and executed by the engine with a row limit.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger("nanobaseai.wren_bridge")

PROJECT = Path(os.environ.get("WREN_PROJECT", "/data/nanobaseai/bi/wren-project/logo_timas")).resolve()
CONNECTION_FILE = os.environ.get("WREN_CONNECTION_FILE", "")
LLM_BASE = os.environ.get("OPENAI_API_BASE", "http://172.17.0.1:8020/v1").rstrip("/")
LLM_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL_NAME", "nanobaseai-bi-llm")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT_SEC", "240"))
MAX_ROWS = int(os.environ.get("WREN_MAX_ROWS", "500"))
CONTEXT_ITEMS = int(os.environ.get("WREN_CONTEXT_ITEMS", "40"))
RECALL_LIMIT = int(os.environ.get("WREN_RECALL_LIMIT", "4"))

from contextlib import asynccontextmanager


def _warm() -> None:
    try:
        engine()
        _memory_store().get_context(manifest(), "ciro", limit=1)
        log.info("wren bridge warm: engine + memory ready")
    except Exception:  # noqa: BLE001
        log.exception("wren bridge warm-up failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.environ.get("WREN_BRIDGE_WARM", "1") == "1":
        threading.Thread(target=_warm, name="wren-warm", daemon=True).start()
    yield


app = FastAPI(title="NanobaseAI BI Wren bridge", version="0.1.0", lifespan=lifespan)

_engine: Any = None
_engine_lock = threading.Lock()  # one pyodbc/DataFusion session per process: serialize engine calls (FastAPI runs sync handlers in a threadpool)
_manifest: dict | None = None
_data_source: str = ""
_threads: dict[str, list[dict[str, str]]] = {}


# --- engine -----------------------------------------------------------------------


def _load_connection() -> tuple[str, dict]:
    if not CONNECTION_FILE:
        raise RuntimeError("WREN_CONNECTION_FILE is not set")
    data = json.loads(Path(CONNECTION_FILE).read_text(encoding="utf-8"))
    if "properties" in data and "datasource" in data:  # envelope
        return str(data["datasource"]), dict(data["properties"])
    ds = str(data.pop("datasource"))
    return ds, data


def engine():
    global _engine, _manifest, _data_source
    if _engine is None:
        from wren.context import build_json
        from wren.engine import WrenEngine
        from wren.model.data_source import DataSource

        mdl_path = PROJECT / "target" / "mdl.json"
        if mdl_path.exists():
            _manifest = json.loads(mdl_path.read_text(encoding="utf-8"))
        else:
            _manifest = build_json(PROJECT)
        ds, conn = _load_connection()
        _data_source = ds
        manifest_str = base64.b64encode(json.dumps(_manifest).encode("utf-8")).decode("ascii")
        # strict_mode + denied_functions come from ~/.wren/config.json (WREN_HOME), the same file the CLI reads:
        # only MDL-declared tables may be referenced and dangerous functions are rejected before execution.
        from wren.config import load_config

        wren_home = Path(os.environ.get("WREN_HOME", str(Path.home() / ".wren")))
        cfg = load_config(wren_home)
        _engine = WrenEngine(manifest_str, DataSource(ds.lower()), conn, config=cfg)
        log.info("engine config: strict_mode=%s denied_functions=%d", cfg.strict_mode, len(cfg.denied_functions))
        log.info("wren engine ready: project=%s datasource=%s models=%d", PROJECT, ds, len(_manifest.get("models", [])))
    return _engine


def manifest() -> dict:
    engine()
    return _manifest or {}


def _normalize(v: Any) -> Any:
    import datetime as dt
    import decimal
    import math

    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray)):
        return v.decode(errors="replace")
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):
        return _normalize(v.item())
    if isinstance(v, dict):
        return {k: _normalize(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_normalize(x) for x in v]
    return v


def run_sql(sql: str, limit: int) -> dict:
    limit = max(1, min(int(limit or MAX_ROWS), MAX_ROWS))
    with _engine_lock:
        table = engine().query(sql, limit + 1)
    rows = [{k: _normalize(x) for k, x in r.items()} for r in table.to_pylist()]
    truncated = len(rows) > limit
    rows = rows[:limit]
    cols = [{"name": f.name, "type": str(f.type)} for f in table.schema]
    return {"id": uuid.uuid4().hex, "columns": cols, "records": rows, "totalRows": len(rows), "truncated": truncated}


# --- models -------------------------------------------------------------------------


class RunSqlIn(BaseModel):
    sql: str
    limit: int | None = Field(default=None, ge=0)


class AskIn(BaseModel):
    question: str
    threadId: str | None = None
    language: str | None = "TR"
    sampleSize: int | None = 50


# --- endpoints ----------------------------------------------------------------------


@app.get("/health")
def health() -> JSONResponse:
    try:
        m = manifest()
        return JSONResponse({"status": "ok", "service": "nanobaseai-bi-wren-bridge", "project": str(PROJECT), "dataSource": _data_source, "models": len(m.get("models", []))})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "error": f"{type(e).__name__}: {e}"}, status_code=503)


@app.get("/api/v1/engine")
def engine_status() -> dict:
    m = manifest()
    deployed = True
    try:
        first = m["models"][0]["name"]
        pk = m["models"][0].get("primaryKey") or m["models"][0]["columns"][0]["name"]
        with _engine_lock:
            engine().query(f'SELECT "{pk}" FROM "{first}"', 1)
    except Exception as e:  # noqa: BLE001
        log.warning("engine probe failed: %s", e)
        deployed = False
    return {
        "dataSource": _data_source,
        "models": len(m.get("models", [])),
        "views": len(m.get("views", []) or []),
        "cubes": len(m.get("cubes", []) or []),
        "relationships": len(m.get("relationships", []) or []),
        "deployed": deployed,
        "project": PROJECT.name,
        "engine": "wrenai-core",
    }


@app.post("/api/v1/run_sql")
def run_sql_ep(body: RunSqlIn) -> dict:
    try:
        return run_sql(body.sql, body.limit or MAX_ROWS)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail={"code": _err_code(e), "message": str(e)[:1200]}) from e


def _err_code(e: Exception) -> str:
    code = getattr(e, "code", None)
    return str(getattr(code, "value", code) or type(e).__name__)


# --- ask orchestration --------------------------------------------------------------


def _rules() -> str:
    from wren.context import load_rules

    content, _ = load_rules(PROJECT)
    return content or ""


def _recall(question: str) -> list[dict]:
    try:
        from wren.memory.index_backend import get_index

        idx = get_index(PROJECT, str(PROJECT / ".wren" / "memory"))
        return list(idx.search(question, limit=RECALL_LIMIT) or [])
    except Exception as e:  # noqa: BLE001
        log.warning("recall failed: %s", e)
        return []


_store: Any = None


def _memory_store():
    """One MemoryStore per process: the embedding model load (~15 s on CPU) happens once, at warm-up."""
    global _store
    if _store is None:
        from wren.memory.store import MemoryStore

        _store = MemoryStore(path=str(PROJECT / ".wren" / "memory"))
    return _store


def _model_index() -> str:
    """Compact model list (name → physical table, primary key, column count): the LLM must know every model name."""
    lines = []
    for m in manifest().get("models", []):
        tr = m.get("tableReference") or {}
        lines.append(f'- "{m["name"]}" → {tr.get("schema", "")}.{tr.get("table", "")} · pk {m.get("primaryKey") or "-"} · {len(m.get("columns", []))} kolon')
    return "\n".join(lines)


def _schema_context(question: str, recalled: list[dict] | None = None) -> str:
    """Semantic schema retrieval (WrenAI memory: LanceDB over MDL items) + the columns the recalled
    SQL pairs reference. Only these items reach the LLM — never the full 1.6k-column schema."""
    m = manifest()
    picked: dict[str, dict[str, str]] = {}  # model → {column: type}

    def add(model: str, col: str, typ: str = "") -> None:
        if model and col:
            picked.setdefault(model, {})[col] = typ

    try:
        ctx = _memory_store().get_context(m, question, limit=CONTEXT_ITEMS)
        for r in (ctx.get("results") or []) if isinstance(ctx, dict) else []:
            if r.get("item_type") == "column":
                add(str(r.get("model_name") or ""), str(r.get("item_name") or ""), str(r.get("data_type") or ""))
            elif r.get("item_type") == "model":
                picked.setdefault(str(r.get("item_name") or r.get("model_name") or ""), {})
    except Exception as e:  # noqa: BLE001
        log.warning("get_context unavailable (%s) — using recalled SQL columns only", e)
    # columns referenced by recalled, verified SQL pairs (exact names, highest signal)
    col_types = {mm["name"]: {c["name"]: str(c.get("type") or "") for c in mm.get("columns", [])} for mm in m.get("models", [])}
    for r in recalled or []:
        sql = str(r.get("sql_query") or r.get("sql") or "")
        for model in col_types:
            if model in sql:
                for col in re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"', sql):
                    if col in col_types[model]:
                        add(model, col, col_types[model][col])
    lines = []
    for model, cols in picked.items():
        if model not in col_types:
            continue
        shown = ", ".join(f'"{c}" {t}'.strip() for c, t in sorted(cols.items()))
        lines.append(f'"{model}": {shown or "(ilgili kolon bulunamadı)"}')
    return "\n".join(lines) or "(bağlam bulunamadı — model listesine bak)"


def _model_names() -> list[str]:
    return [m["name"] for m in manifest().get("models", [])]


SYSTEM_PROMPT = """Sen NanobaseAI BI'ın SQL üreticisisin. Görevin: kullanıcının Türkçe iş sorusunu, aşağıdaki semantik modeller (MDL) üzerinde çalışan TEK bir SELECT sorgusuna çevirmek.
Kurallar:
- Yalnız verilen model adlarını kullan (ör. "dbo_LG_411_01_INVOICE"); tablo/kolon adlarını çift tırnak içinde yaz.
- Hedef veritabanı SQL Server (T-SQL). LIMIT yerine TOP kullan; GROUP BY içinde takma ad veya sıra numarası kullanma, ifadeyi tekrar yaz.
- Tarih kırılımı: ay için DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1); gün için CAST("DATE_" AS DATE).
- İş kurallarına (TRCODE, LINETYPE, CANCELLED = 0 vb.) mutlaka uy.
- Yalnız SELECT üret; DML/DDL yok. Sonuç satır sayısını makul tut (TOP 50 gibi).
- Çıktı biçimi: sadece ```sql ... ``` bloğu, başka açıklama yazma. Soru veriyle cevaplanamıyorsa tek satır: NO_SQL: <neden>."""


def _llm(messages: list[dict[str, str]], *, max_tokens: int = 1024, temperature: float = 0.0) -> str:
    headers = {"Content-Type": "application/json"}
    if LLM_KEY:
        headers["Authorization"] = f"Bearer {LLM_KEY}"
    payload = {"model": LLM_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": False}
    with httpx.Client(timeout=LLM_TIMEOUT) as c:
        r = c.post(f"{LLM_BASE}/chat/completions", json=payload, headers=headers)
    if r.status_code >= 400:
        raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
    return str(r.json()["choices"][0]["message"]["content"] or "")


_SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def _extract_sql(text: str) -> str | None:
    m = _SQL_BLOCK.search(text)
    sql = (m.group(1) if m else text).strip().rstrip(";").strip()
    if not sql or sql.upper().startswith("NO_SQL"):
        return None
    if not re.match(r"(?is)^\s*(with|select)\b", sql):
        return None
    if re.search(r"(?i)\b(insert|update|delete|drop|alter|truncate|merge|exec|execute)\b", sql):
        return None
    return sql


def _build_messages(question: str, thread: list[dict[str, str]]) -> list[dict[str, str]]:
    rules = _rules()
    recalled = _recall(question)
    schema = _schema_context(question, recalled)
    examples = "\n\n".join(
        f"Soru: {r.get('nl_query') or r.get('nl') or ''}\nSQL:\n{r.get('sql_query') or r.get('sql') or ''}" for r in recalled if (r.get("sql_query") or r.get("sql"))
    )
    ctx = [
        "## Modeller\n" + _model_index(),
        "## İş kuralları\n" + (rules or "(yok)"),
        "## Doğrulanmış örnek soru→SQL çiftleri\n" + (examples or "(yok)"),
        "## Şema bağlamı (soruyla ilgili model/kolonlar)\n" + schema,
    ]
    msgs: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + "\n\n".join(ctx)}]
    for t in thread[-6:]:
        msgs.append(t)
    msgs.append({"role": "user", "content": question})
    return msgs


def _summarize(question: str, sql: str, result: dict) -> str:
    sample = result["records"][:20]
    prompt = (
        "Aşağıdaki soru ve sorgu sonucunu 1-3 cümlede Türkçe özetle. Sayıları Türkçe biçimle (binlik ayırıcı nokta), yorum katma, sadece veride olanı söyle.\n"
        f"Soru: {question}\nSatır sayısı: {result['totalRows']}\nİlk satırlar (JSON): {json.dumps(sample, ensure_ascii=False)[:4000]}"
    )
    try:
        return _llm([{"role": "user", "content": prompt}], max_tokens=300).strip()
    except Exception as e:  # noqa: BLE001
        log.warning("summary failed: %s", e)
        return f"{result['totalRows']} satır döndü."


@app.post("/api/v1/ask")
def ask(body: AskIn) -> dict:
    t0 = time.perf_counter()
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=422, detail={"code": "EMPTY_QUESTION", "message": "Soru boş."})
    thread_id = body.threadId or uuid.uuid4().hex
    thread = _threads.setdefault(thread_id, [])
    timings: dict[str, int] = {}
    repairs = 0
    try:
        t = time.perf_counter()
        messages = _build_messages(q, thread)
        timings["context_ms"] = int((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        text = _llm(messages)
        timings["llm_ms"] = int((time.perf_counter() - t) * 1000)
        sql = _extract_sql(text)
        if not sql:
            reason = text.strip().replace("NO_SQL:", "").strip()[:500]
            log.info("ask NON_SQL q=%r reason=%r", q[:80], reason[:200])
            return {"id": uuid.uuid4().hex, "type": "NON_SQL_QUERY", "explanation": reason or "Model bu soru için SQL üretmedi.", "threadId": thread_id, "timings": timings}
        # validate; one repair round with the engine's structured error
        error: str | None = None
        for attempt in range(2):
            try:
                with _engine_lock:
                    engine().dry_run(sql)
                error = None
                break
            except Exception as e:  # noqa: BLE001
                error = str(e)[:1500]
                log.warning("ask dry_run failed (attempt %d) q=%r err=%s", attempt + 1, q[:80], error[:300])
                if attempt == 1:
                    break
                repairs += 1
                fix = _llm(messages + [{"role": "assistant", "content": f"```sql\n{sql}\n```"}, {"role": "user", "content": f"Bu sorgu motor doğrulamasından geçmedi. Hata: {error}\nSorguyu düzelt, yalnız ```sql``` bloğu döndür."}])
                sql2 = _extract_sql(fix)
                if not sql2:
                    break
                sql = sql2
        if error:
            log.warning("ask SQL_INVALID q=%r repairs=%d err=%s", q[:80], repairs, error[:300])
            return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": f"Üretilen SQL doğrulanamadı: {error}", "threadId": thread_id, "repairs": repairs, "timings": timings}
        t = time.perf_counter()
        result = run_sql(sql, int(body.sampleSize or 50))
        timings["run_sql_ms"] = int((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        summary = _summarize(q, sql, result)
        timings["summary_ms"] = int((time.perf_counter() - t) * 1000)
        log.info("ask ok q=%r rows=%d repairs=%d timings=%s", q[:80], result["totalRows"], repairs, timings)
        thread.append({"role": "user", "content": q})
        thread.append({"role": "assistant", "content": f"```sql\n{sql}\n```"})
        return {
            "id": result["id"],
            "type": "TEXT_TO_SQL",
            "sql": sql,
            "summary": summary,
            "threadId": thread_id,
            "rowCount": result["totalRows"],
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "repairs": repairs,
            "timings": timings,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("ask failed")
        raise HTTPException(status_code=502, detail={"code": _err_code(e), "message": str(e)[:800]}) from e


@app.post("/api/v1/generate_summary")
def generate_summary(body: dict) -> dict:
    sql = str(body.get("sql") or "")
    q = str(body.get("question") or "")
    result = run_sql(sql, int(body.get("sampleSize") or 50))
    return {"summary": _summarize(q, sql, result)}
