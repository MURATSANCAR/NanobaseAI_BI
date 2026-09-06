"""Semantic Bridge — the cockpit contract (/api/v1/ask, /run_sql, /engine, /generate_summary).

    USER → Qwen-free Resolver → CERTIFIED catalog → DeterministicCompiler → SQL Server
                           └─ MISS / complex → ExistingCompiler (Qwen + certified facts) → dry-run → SQL Server

Also: /api/v1/feedback (validated Q→SQL → History Miner input), /api/v1/semantic/* (resolve, explain,
status, certify), /api/v1/schema/* (inventory + annotations for the portal layer).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from semantic_layer import SEMANTIC_LAYER_VERSION
from semantic_layer.candidates.generator import CandidateGenerator
from semantic_layer.conventions import Conventions
from semantic_layer.candidates.llm_client import LlmClient
from semantic_layer.config import SemanticSettings
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.history.sources import load_project_pairs
from semantic_layer.models import Annotation, ConceptStatus, TemporalSlot
from semantic_layer.naming import label_context
from semantic_layer.normalize import normalize_term, tokenize
from semantic_layer.profiler.connectors import Connector, connector_from_file
from semantic_layer.runtime.compiler import CompilerRouter, DeterministicCompiler, ExistingCompiler, default_filters_provider, fast_summary
from semantic_layer.runtime.audit import audit_sql
from semantic_layer.runtime.guardrails import allowed_tables, physicalize_sql, referenced_tables, strip_comments, strip_trailing_semicolon, validate_sql
from semantic_layer.runtime.llm_queue import LlmQueue, QueuedLlm
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.store.catalog_store import CatalogStore, open_store, result_fingerprint

log = logging.getLogger("semantic_bridge")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class Runtime:
    """Process-wide state: store, profiles, resolver, compilers, DB connector, recall index."""

    def __init__(self, settings: SemanticSettings, *, store: Optional[CatalogStore] = None, connector: Optional[Connector] = None, llm=None, queue: Optional[LlmQueue] = None):
        self.settings = settings
        self.store = store or open_store(settings.store_dsn)
        self.connector = connector
        # One model serves everyone: requests that need it are admitted in arrival order, never rejected.
        self.queue = queue or LlmQueue.from_env(self.store.engine)
        self.llm = QueuedLlm(llm, self.queue, tenant_id=settings.tenant_id, datasource_id=settings.datasource_id) if llm is not None else None
        self._engine_lock = threading.Lock()
        self.threads: dict[str, list[dict[str, str]]] = {}
        self.profiles = self.store.list_profiles(settings.datasource_id)
        self.rules_text = self._load_rules()
        self.pairs = load_project_pairs(settings.project_dir) if settings.project_dir else []
        self._catalog_version = None
        self._checked_at = 0.0
        self._cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()
        self._cache_ttl = int(os.environ.get("SEMANTIC_CACHE_TTL_SEC", "300"))
        self.rebuild()

    def _load_rules(self) -> str:
        """Operator documentation shipped with the deployment — every *.md under knowledge/ except
        the validated Q→SQL pairs (those are the miner's input, and reach the LLM through recall)."""
        pd = self.settings.project_dir
        if not pd or not (pd / "knowledge").exists():
            return ""
        parts = [f.read_text(encoding="utf-8") for f in sorted((pd / "knowledge").rglob("*.md")) if f.parent.name != "sql"]
        return "\n\n".join(parts)

    def ensure_fresh(self, *, every: float = 30.0) -> None:
        """Pick up a catalog published by another process (the nightly worker, the portal, a sibling
        uvicorn worker). A reload request only ever reaches one worker, so each worker checks for itself:
        one cheap version read at most every `every` seconds, and a rebuild only when it actually moved."""
        now = time.time()
        if now - self._checked_at < every:
            return
        self._checked_at = now
        try:
            version = self.store.catalog_fingerprint(self.settings.tenant_id, self.settings.datasource_id)
        except Exception as e:  # noqa: BLE001
            log.debug("catalog version check failed: %s", e)
            return
        if version != self._catalog_version:
            log.info("catalog changed (%s → %s) — reloading profiles", self._catalog_version, version)
            self.rebuild()

    def rebuild(self) -> None:
        s = self.settings
        self.profiles = self.store.list_profiles(s.datasource_id)
        self._catalog_version = self.store.catalog_fingerprint(s.tenant_id, s.datasource_id)
        self._checked_at = time.time()
        self.conventions = Conventions.from_profiles(self.profiles)
        if not s.dialect:
            s.dialect = getattr(self.connector, "dialect", "") or "generic"
        default_temporal = None
        dp = os.environ.get("SEMANTIC_DEFAULT_PERIOD", "")  # e.g. YEAR:2026
        if dp.startswith("YEAR:"):
            from datetime import date

            y = int(dp.split(":")[1])
            default_temporal = TemporalSlot(text="varsayılan", primitive="YEAR", start=date(y, 1, 1), end=date(y + 1, 1, 1), grain="YEAR", params={"year": y, "default": True})
        self.resolver = SemanticResolver(self.store, s.tenant_id, s.datasource_id, self.profiles, default_temporal=default_temporal, conventions=self.conventions)
        det = DeterministicCompiler(self.profiles, s.context, s.dialect, default_filters=default_filters_provider(self.store, s.tenant_id, s.datasource_id), conventions=self.conventions)
        existing = None
        if self.llm is not None:
            existing = ExistingCompiler(self.llm, self.profiles, s.context, rules_text=self.rules_text, recall=self.recall if s.recall_enabled else None, dialect=s.dialect, conventions=self.conventions)
        self.existing = existing
        # SuperSonic joins only when configured: "shadow" measures it next to the answer, "primary"
        # is an explicit experiment. Neither is on by default (SEMANTIC_COMPILER / SUPERSONIC_MODE).
        alternates: dict[str, Any] = {}
        shadow: list[Any] = []
        try:
            from semantic_layer.runtime.supersonic import build_adapter

            adapter = build_adapter()
            if adapter is not None:
                alternates["supersonic"] = adapter
                if os.environ.get("SUPERSONIC_MODE", "shadow").lower() == "shadow":
                    shadow.append(adapter)
                log.info("supersonic adapter enabled (mode=%s)", os.environ.get("SUPERSONIC_MODE", "shadow"))
        except Exception as e:  # noqa: BLE001
            log.warning("supersonic adapter unavailable: %s", e)
        self.router = CompilerRouter(det, existing, strict_miss=s.strict_miss, primary=os.environ.get("SEMANTIC_COMPILER", ""), shadow=shadow, alternates=alternates)

    # ------------------------------------------------------------------ recall (Memory ON)
    def recall(self, question: str, exclude_nl: Optional[str] = None) -> list[dict[str, str]]:
        """Token-Jaccard recall over validated pairs (project knowledge + runtime-validated log). No vectors."""
        q = set(tokenize(question))
        if not q:
            return []
        rows = [{"nl": p.nl, "sql": p.sql} for p in self.pairs if p.source != "seed"]
        for r in self.store.list_validated_queries(self.settings.tenant_id, self.settings.datasource_id, limit=500):
            rows.append({"nl": r["question"], "sql": r["sql_text"]})
        ex = normalize_term(exclude_nl) if exclude_nl else None
        scored = []
        for r in rows:
            if ex and normalize_term(r["nl"]) == ex:
                continue
            t = set(tokenize(r["nl"]))
            if not t:
                continue
            j = len(q & t) / len(q | t)
            if j > 0.12:
                scored.append((j, r))
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[: self.settings.recall_limit]]

    # ------------------------------------------------------------------ execution
    def _physical(self, sql: str) -> str:
        return physicalize_sql(strip_trailing_semicolon(sql), self.profiles, self.settings.context, self.settings.dialect)

    def dry_run(self, sql: str) -> None:
        if self.connector is None:
            raise RuntimeError("no database connector")
        with self._engine_lock:
            self.connector.dry_run(sql)

    def run_sql(self, sql: str, limit: int) -> dict[str, Any]:
        sql = strip_comments(sql or "")
        ok, why = validate_sql(sql)
        if not ok:
            raise ValueError(f"SQL rejected: {why}")
        # The endpoint reads the catalog's tables — not everything the database login can reach.
        ok, why = allowed_tables(sql, self.profiles, self.settings.context, self.settings.dialect or None)
        if not ok:
            raise ValueError(f"SQL rejected: {why}")
        limit = max(1, min(int(limit or self.settings.max_rows), self.settings.max_rows))
        phys = self._physical(sql)
        key = hashlib.sha256(f"{limit}\n{phys}".encode()).hexdigest()
        if self._cache_ttl > 0:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < self._cache_ttl:
                out = dict(hit[1])
                out["id"] = uuid.uuid4().hex
                out["cached"] = True
                return out
        if self.connector is None:
            raise RuntimeError("no database connector")
        with self._engine_lock:
            cols, rows, truncated = self.connector.execute(phys, limit)
        out = {"id": uuid.uuid4().hex, "columns": cols, "records": rows, "totalRows": len(rows), "truncated": truncated, "cached": False, "physicalSql": phys}
        if self._cache_ttl > 0 and len(out.get("records") or []) <= 200:
            self._cache[key] = (time.time(), out)
            budget = int(os.environ.get("SEMANTIC_CACHE_MAX_ROWS", "5000"))
            while len(self._cache) > 64 or sum(len(v[1].get("records") or []) for v in self._cache.values()) > budget:
                self._cache.popitem(last=False)
        return out

    def summarize(self, question: str, sql: str, result: dict[str, Any]) -> str:
        cols = [c["name"] for c in result.get("columns") or []]
        if self.settings.summary_mode == "llm" and self.llm is not None:
            sample = result["records"][:20]
            prompt = ("Aşağıdaki soru ve sorgu sonucunu 1-3 cümlede Türkçe özetle. Sayıları Türkçe biçimle, yorum katma, sadece veride olanı söyle.\n"
                      f"Soru: {question}\nSatır sayısı: {result['totalRows']}\nİlk satırlar (JSON): {json.dumps(sample, ensure_ascii=False)[:4000]}")
            try:
                return self.llm.chat([{"role": "user", "content": prompt}], max_tokens=300).strip()
            except Exception as e:  # noqa: BLE001
                log.warning("llm summary failed: %s", e)
        return fast_summary(question, cols, result.get("records") or [], int(result.get("totalRows") or 0))

    # ------------------------------------------------------------------ ask
    def ask(self, question: str, *, thread_id: Optional[str], sample_size: int, exclude_nl: Optional[str] = None, execute: bool = True) -> dict[str, Any]:
        t0 = time.perf_counter()
        timings: dict[str, int] = {}
        thread_id = thread_id or uuid.uuid4().hex
        thread = self.threads.setdefault(thread_id, [])
        # a long-lived process must not accumulate every conversation it ever served
        if len(self.threads) > 200:
            for stale in list(self.threads)[:-100]:
                self.threads.pop(stale, None)
        self.ensure_fresh()
        t = time.perf_counter()
        sq = self.resolver.resolve(question)
        timings["resolve_ms"] = int((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        compiled = self.router.compile(sq, self.store, thread, recall=(lambda q: self.recall(q, exclude_nl)) if (exclude_nl and self.settings.recall_enabled) else None)
        timings["compile_ms"] = int((time.perf_counter() - t) * 1000)
        if compiled.llm_ms:
            timings["llm_ms"] = compiled.llm_ms
        queued = {}
        if isinstance(self.llm, QueuedLlm) and self.llm.last_wait_ms:
            timings["queue_wait_ms"] = self.llm.last_wait_ms
            queued = {"waitedMs": self.llm.last_wait_ms, "aheadOnArrival": self.llm.last_ahead}
        semantic = {"query": sq.to_dict(), "compiler": compiled.compiler, "certified": compiled.certified, "explain": compiled.explain, "catalogVersion": compiled.catalog_version}
        if queued:
            semantic["queue"] = queued
        if not compiled.sql:
            reason = "; ".join(compiled.explain)[:500]
            if sq.out_of_scope:
                reason = next((e for e in sq.explanation if "kapsamı dışında" in e), reason)
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=None, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=reason)
            return {"id": uuid.uuid4().hex, "type": "NON_SQL_QUERY", "explanation": reason or "Model bu soru için SQL üretmedi.", "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        sql = strip_trailing_semicolon(compiled.sql)
        ok, why = validate_sql(sql)
        if not ok:
            return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": f"Guardrail: {why}", "threadId": thread_id, "timings": timings, "semantic": semantic}
        # The prompt asks the model to honour the certified catalog; this is where we check that it did.
        # A query that contradicts a certified fact answers a different question than the one asked.
        if not compiled.certified:
            contradictions = audit_sql(sq, sql, conventions=self.conventions)
            if contradictions:
                semantic["catalogAudit"] = contradictions
                reason = "Üretilen SQL sertifikalı katalogla çelişiyor: " + "; ".join(contradictions)
                log.warning("catalog audit refused q=%r %s", question[:80], contradictions)
                qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=reason)
                return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": reason, "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        repairs = 0
        error: Optional[str] = None
        if self.connector is not None:
            for attempt in range(2):
                try:
                    self.dry_run(self._physical(sql))
                    error = None
                    break
                except Exception as e:  # noqa: BLE001
                    error = str(e)[:1500]
                    log.warning("dry_run failed (attempt %d) q=%r err=%s", attempt + 1, question[:80], error[:300])
                    if attempt == 1 or self.existing is None or compiled.compiler == "deterministic":
                        break
                    repairs += 1
                    fixed = self.existing.repair(sq, sql, error, thread)
                    if not fixed:
                        break
                    sql = strip_trailing_semicolon(fixed)
        if error:
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=error)
            return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": f"Üretilen SQL doğrulanamadı: {error}", "threadId": thread_id, "repairs": repairs, "timings": timings, "semantic": semantic, "queryId": qid}
        if not execute or self.connector is None:
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False)
            return {"id": uuid.uuid4().hex, "type": "TEXT_TO_SQL", "sql": sql, "physicalSql": self._physical(sql), "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid, "executed": False}
        t = time.perf_counter()
        try:
            result = self.run_sql(sql, sample_size)
        except Exception as e:  # noqa: BLE001
            err = str(e)[:800]
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=err)
            return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": f"Sorgu çalıştırılamadı: {err}", "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        timings["run_sql_ms"] = int((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        summary = self.summarize(question, sql, result)
        timings["summary_ms"] = int((time.perf_counter() - t) * 1000)
        fp = result_fingerprint([c["name"] for c in result["columns"]], result["records"])
        qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=True, row_count=result["totalRows"], latency_ms=int((time.perf_counter() - t0) * 1000), result_fingerprint=fp)
        thread.append({"role": "user", "content": question})
        thread.append({"role": "assistant", "content": f"```sql\n{sql}\n```"})
        del thread[:-12]
        log.info("ask ok compiler=%s certified=%s rows=%d timings=%s q=%r", compiled.compiler, compiled.certified, result["totalRows"], timings, question[:80])
        return {
            "id": result["id"],
            "type": "TEXT_TO_SQL",
            "sql": sql,
            "physicalSql": result.get("physicalSql"),
            "summary": summary,
            "threadId": thread_id,
            "rowCount": result["totalRows"],
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "repairs": repairs,
            "timings": timings,
            "recallExcluded": bool(exclude_nl),
            "semantic": semantic,
            "queryId": qid,
        }

    # ------------------------------------------------------------------ portal layer
    def inventory(self) -> dict[str, Any]:
        s = self.settings
        anns = self.store.list_annotations(s.datasource_id)
        by_key: dict[tuple[str, Optional[str]], list[Annotation]] = {}
        for a in anns:
            by_key.setdefault((a.table_pattern, (a.column or "").upper() or None), []).append(a)
        concepts_by_col: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for c in self.store.find_concepts(s.tenant_id, s.datasource_id, limit=100000):
            if c.status in (ConceptStatus.REJECTED,):
                continue
            for m in self.store.list_mappings(c.id):
                if m.column:
                    concepts_by_col.setdefault((m.entity, m.column.upper()), []).append({"id": c.id, "term": c.term, "type": c.semantic_type, "status": c.status, "operator": m.operator, "values": m.values, "confidence": round(c.confidence, 2)})
                elif m.formula:
                    for ref in re.findall(r"\b([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\b", m.formula):
                        concepts_by_col.setdefault((ref[0], ref[1]), []).append({"id": c.id, "term": c.term, "type": c.semantic_type, "status": c.status, "formula": m.formula, "confidence": round(c.confidence, 2)})
        tables = []
        undefined_cols = 0
        for p in self.profiles:
            cols = []
            for c in p.columns:
                cons = concepts_by_col.get((p.entity, c.name.upper()), [])
                col_anns = [{"id": a.id, "text": a.text, "author": a.author, "createdAt": a.created_at.isoformat()} for a in by_key.get((p.table_pattern, c.name.upper()), [])]
                defined = bool(c.description) or bool(col_anns) or any(x["status"] == ConceptStatus.CERTIFIED for x in cons)
                if not defined:
                    undefined_cols += 1
                cols.append({
                    "name": c.name, "type": c.data_type, "nullable": c.nullable, "isPrimaryKey": c.is_primary_key,
                    "ref": f"{c.ref_entity}.{c.ref_column}" if c.ref_entity else None,
                    "sensitive": c.sensitive, "sensitivityReason": c.sensitivity_reason,
                    "sentinelValues": list(c.sentinel_values),
                    "distinct": c.distinct_count, "topValues": [] if c.sensitive else [[v, n] for v, n in c.top_values[:12]],
                    "description": c.description, "annotations": col_anns, "concepts": cons,
                    "status": "CERTIFIED" if any(x["status"] == ConceptStatus.CERTIFIED for x in cons) else ("CANDIDATE" if cons else ("DESCRIBED" if defined else "UNDEFINED")),
                })
            tables.append({
                "entity": p.entity, "tableName": p.table_name, "tablePattern": p.table_pattern, "schema": p.schema_name,
                "context": label_context(p.context, s.pattern_labels),
                "description": p.description, "rowCount": p.row_count, "primaryKey": p.primary_key, "relationships": p.relationships,
                "annotations": [{"id": a.id, "text": a.text, "author": a.author, "createdAt": a.created_at.isoformat()} for a in by_key.get((p.table_pattern, None), [])],
                "columns": cols, "undefinedColumns": sum(1 for c in cols if c["status"] == "UNDEFINED"), "scannedAt": p.scanned_at.isoformat(),
            })
        return {"datasourceId": s.datasource_id, "tables": tables, "tableCount": len(tables), "columnCount": sum(len(t["columns"]) for t in tables), "undefinedColumns": undefined_cols, "catalog": self.store.status_counts(s.tenant_id, s.datasource_id), "version": self.store.latest_version(s.tenant_id, s.datasource_id)}

    def add_annotation(self, table_pattern: str, column: Optional[str], text: str, author: str) -> dict[str, Any]:
        s = self.settings
        ann = self.store.add_annotation(Annotation(datasource_id=s.datasource_id, table_pattern=table_pattern, column=(column or None), text=text.strip(), author=author))
        gen = CandidateGenerator(self.store, s.tenant_id, s.datasource_id, self.profiles, self.conventions)
        ingested = gen.ingest_annotation(table_pattern, column, text, f"annotation:{ann.id}")
        return {"annotation": {"id": ann.id, "tablePattern": table_pattern, "column": column, "text": ann.text, "author": author}, "candidates": ingested}

    def certify(self, note: str = "") -> dict[str, Any]:
        s = self.settings
        gen = CandidateGenerator(self.store, s.tenant_id, s.datasource_id, self.profiles, self.conventions)
        gen.attach_profile_evidence()
        rep = EvidenceEngine(self.store, min_support=s.min_support, threshold=s.certify_threshold).run(s.tenant_id, s.datasource_id, self.profiles, note=note)
        self.rebuild()
        return rep


# ---------------------------------------------------------------------- FastAPI

class RunSqlIn(BaseModel):
    sql: str
    limit: int | None = Field(default=None, ge=0)
    question: str | None = None


class AskIn(BaseModel):
    question: str
    threadId: str | None = None
    language: str | None = "TR"
    sampleSize: int | None = 50
    excludeNl: str | None = None
    execute: bool | None = True


class FeedbackIn(BaseModel):
    queryId: str
    validated: bool
    comment: str | None = None


class AnnotationIn(BaseModel):
    tablePattern: str
    column: str | None = None
    text: str
    author: str | None = None


def build_runtime(settings: Optional[SemanticSettings] = None, *, store: Optional[CatalogStore] = None, connector: Optional[Connector] = None, llm=None, allow_no_llm: bool = True) -> Runtime:
    settings = settings or SemanticSettings.from_env()
    if connector is None and settings.connection_file and Path(settings.connection_file).exists():
        connector = connector_from_file(settings.connection_file)
    if llm is None and settings.llm_base and os.environ.get("SEMANTIC_LLM", "1") not in ("0", "false"):
        llm = LlmClient(settings.llm_base, settings.llm_model, settings.llm_key, settings.llm_timeout)
    return Runtime(settings, store=store, connector=connector, llm=llm)


def _require_admin(request: Any) -> None:
    """Reading and asking sit behind the site's own authentication; changing the catalog needs a token.
    Without this, anything that can reach the cockpit's API path could recertify the semantics."""
    token = os.environ.get("SEMANTIC_ADMIN_TOKEN", "")
    if not token:
        return                      # not configured: the loopback binding is the only control
    supplied = request.headers.get("x-semantic-admin", "") or request.query_params.get("admin_token", "")
    if not secrets_compare(supplied, token):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "admin token required"})


def secrets_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(str(a or ""), str(b or ""))


def create_app(runtime: Optional[Runtime] = None) -> FastAPI:
    state: dict[str, Any] = {"rt": runtime}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if state["rt"] is None:
            state["rt"] = build_runtime()
        rt = state["rt"]
        log.info("semantic bridge ready: profiles=%d certified=%s llm=%s db=%s", len(rt.profiles), rt.store.status_counts(rt.settings.tenant_id, rt.settings.datasource_id).get("CERTIFIED"), bool(rt.llm), bool(rt.connector))
        yield

    app = FastAPI(title="NanobaseAI Semantic Bridge", version=SEMANTIC_LAYER_VERSION, lifespan=lifespan)

    def rt() -> Runtime:
        if state["rt"] is None:
            state["rt"] = build_runtime()
        return state["rt"]

    @app.get("/health")
    def health() -> JSONResponse:
        r = rt()
        return JSONResponse({"status": "ok", "service": "nanobaseai-bi-semantic-bridge", "version": SEMANTIC_LAYER_VERSION, "profiles": len(r.profiles), "catalog": r.store.status_counts(r.settings.tenant_id, r.settings.datasource_id), "llm": bool(r.llm), "db": bool(r.connector), "pid": os.getpid()})

    @app.get("/api/v1/engine")
    def engine_status() -> dict[str, Any]:
        r = rt()
        deployed = False
        if r.connector is not None and r.profiles:
            try:
                p = r.profiles[0]
                pk = p.primary_key[0] if p.primary_key else p.columns[0].name
                label = f"{p.schema_name}_{p.table_name}" if p.schema_name else p.table_name
                r.run_sql(f'SELECT TOP 1 "{pk}" FROM {label}' if r.settings.dialect == "tsql" else f'SELECT "{pk}" FROM {label} LIMIT 1', 1)
                deployed = True
            except Exception as e:  # noqa: BLE001
                log.warning("engine probe failed: %s", e)
        v = r.store.latest_version(r.settings.tenant_id, r.settings.datasource_id)
        return {"dataSource": r.connector.dialect if r.connector else "offline", "models": len(r.profiles), "views": 0, "cubes": 0, "relationships": sum(len(p.relationships) for p in r.profiles), "deployed": deployed, "project": r.settings.datasource_id, "engine": "semantic-layer", "catalogVersion": v["version"] if v else 0, "certified": r.store.status_counts(r.settings.tenant_id, r.settings.datasource_id).get("CERTIFIED", 0)}

    @app.post("/api/v1/run_sql")
    def run_sql_ep(body: RunSqlIn) -> dict[str, Any]:
        r = rt()
        try:
            result = r.run_sql(body.sql, body.limit or r.settings.max_rows)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail={"code": type(e).__name__, "message": str(e)[:1200]}) from e
        try:
            from nanobase_api.chat_widgets import widgets_from_query_result  # optional, same as legacy bridge

            widgets = widgets_from_query_result(columns=result.get("columns"), rows=result.get("records"), title=(body.question or "").strip() or None)
            if widgets:
                w = dict(widgets[0])
                w.pop("sql", None)
                if w.get("type") != "multi_card":
                    w.pop("data", None)
                result["widget"] = w
        except Exception:  # noqa: BLE001
            pass
        return result

    @app.post("/api/v1/ask")
    def ask(body: AskIn) -> dict[str, Any]:
        q = body.question.strip()
        if not q:
            raise HTTPException(status_code=422, detail={"code": "EMPTY_QUESTION", "message": "Soru boş."})
        try:
            return rt().ask(q, thread_id=body.threadId, sample_size=int(body.sampleSize or 50), exclude_nl=body.excludeNl, execute=bool(body.execute if body.execute is not None else True))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("ask failed")
            raise HTTPException(status_code=502, detail={"code": type(e).__name__, "message": str(e)[:800]}) from e

    @app.post("/api/v1/generate_summary")
    def generate_summary(body: dict[str, Any]) -> dict[str, Any]:
        r = rt()
        try:
            result = r.run_sql(str(body.get("sql") or ""), int(body.get("sampleSize") or 50))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail={"code": type(e).__name__, "message": str(e)[:400]}) from e
        return {"summary": r.summarize(str(body.get("question") or ""), str(body.get("sql") or ""), result)}

    @app.post("/api/v1/feedback")
    def feedback(body: FeedbackIn) -> dict[str, Any]:
        ok = rt().store.mark_validated(body.queryId, body.validated)
        return {"ok": ok, "queryId": body.queryId, "validated": body.validated, "note": "validated pairs feed the History Miner on the next pipeline run"}

    # --- semantic
    @app.post("/api/v1/semantic/resolve")
    def resolve(body: AskIn) -> dict[str, Any]:
        r = rt()
        sq = r.resolver.resolve(body.question)
        det = r.router.deterministic
        plan_ok, reason = det.plan(sq) if det else (None, "no deterministic compiler")
        out = det.compile(sq, r.store) if det and plan_ok else None
        return {"query": sq.to_dict(), "deterministic": {"ok": out is not None, "reason": reason, "sql": out.sql if out else None, "explain": out.explain if out else []}}

    @app.get("/api/v1/semantic/explain")
    def explain(term: str) -> dict[str, Any]:
        return rt().resolver.explain_term(term)

    @app.get("/api/v1/semantic/status")
    def semantic_status() -> dict[str, Any]:
        r = rt()
        s = r.settings
        return {"ok": True, "engine": "semantic-layer", "version": SEMANTIC_LAYER_VERSION, "status": r.store.status_counts(s.tenant_id, s.datasource_id), "certifiedByType": r.store.type_counts(s.tenant_id, s.datasource_id), "catalogVersion": r.store.latest_version(s.tenant_id, s.datasource_id), "profiles": len(r.profiles), "queries": r.store.query_stats(s.tenant_id, s.datasource_id), "unresolved": dict(list(r.store.list_unresolved_terms(s.tenant_id, s.datasource_id).items())[:30]), "recall": s.recall_enabled, "strictMiss": s.strict_miss}

    @app.post("/api/v1/semantic/certify")
    def certify(request: Request, body: dict[str, Any] | None = None) -> dict[str, Any]:
        _require_admin(request)
        return rt().certify(note=str((body or {}).get("note") or "api certify"))

    @app.get("/api/v1/llm/queue")
    def llm_queue() -> dict[str, Any]:
        """Who is using the model and who is waiting — the cockpit shows this instead of a spinner."""
        r = rt()
        return r.queue.status()

    @app.get("/api/v1/semantic/ab")
    def ab_status() -> dict[str, Any]:
        """What the shadow compilers produced next to the answers this process served."""
        r = rt()
        rows = list(r.router.shadow_results)
        agree = sum(1 for x in rows if x.get("same_as_primary"))
        return {
            "primary": r.router.primary or "auto (deterministic → llm)",
            "shadow": [getattr(c, "name", str(c)) for c in r.router.shadow],
            "alternates": sorted(r.router.alternates),
            "samples": len(rows),
            "agreement": round(agree / len(rows), 3) if rows else None,
            "meanShadowMs": int(sum(x.get("ms", 0) for x in rows) / len(rows)) if rows else 0,
            "recent": rows[-10:],
        }

    @app.post("/api/v1/semantic/reload")
    def reload(request: Request) -> dict[str, Any]:
        _require_admin(request)
        r = rt()
        r.pairs = load_project_pairs(r.settings.project_dir) if r.settings.project_dir else []
        r.rules_text = r._load_rules()
        r.rebuild()
        return {"ok": True, "profiles": len(r.profiles)}

    @app.get("/api/v1/semantic/concepts")
    def concepts(status: str | None = None, type: str | None = None, q: str | None = None, limit: int = 500) -> dict[str, Any]:
        r = rt()
        s = r.settings
        rows = r.store.search_concepts(s.tenant_id, s.datasource_id, q, limit) if q else r.store.find_concepts(s.tenant_id, s.datasource_id, status=status, semantic_type=type, limit=limit)
        return {"items": [{"concept": c.to_dict(), "mappings": [m.to_dict() for m in r.store.list_mappings(c.id)]} for c in rows]}

    @app.get("/api/v1/semantic/concepts/{concept_id}")
    def concept(concept_id: str) -> dict[str, Any]:
        b = rt().store.concept_bundle(concept_id)
        if not b:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        return b

    # --- portal layer: schema inventory + annotations
    @app.get("/api/v1/schema/inventory")
    def inventory() -> dict[str, Any]:
        return rt().inventory()

    @app.post("/api/v1/schema/annotations")
    def add_annotation(request: Request, body: AnnotationIn) -> dict[str, Any]:
        _require_admin(request)
        if not body.text.strip():
            raise HTTPException(status_code=422, detail={"code": "EMPTY_TEXT"})
        return rt().add_annotation(body.tablePattern, body.column, body.text, body.author or "cockpit")

    @app.get("/api/v1/schema/annotations")
    def list_annotations(tablePattern: str | None = None) -> dict[str, Any]:
        r = rt()
        return {"items": [{"id": a.id, "tablePattern": a.table_pattern, "column": a.column, "text": a.text, "author": a.author, "createdAt": a.created_at.isoformat()} for a in r.store.list_annotations(r.settings.datasource_id, tablePattern)]}

    @app.delete("/api/v1/schema/annotations/{annotation_id}")
    def retire_annotation(request: Request, annotation_id: str) -> dict[str, Any]:
        _require_admin(request)
        return {"ok": rt().store.retire_annotation(annotation_id)}

    return app


app = create_app()
