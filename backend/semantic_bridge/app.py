"""Semantic Bridge — the cockpit contract (/api/v1/ask, /run_sql, /engine, /generate_summary).

    USER → Qwen-free Resolver → CERTIFIED catalog → DeterministicCompiler → SQL Server
                           └─ MISS / complex → ExistingCompiler (Qwen + certified facts) → dry-run → SQL Server

Also: /api/v1/feedback (validated Q→SQL → History Miner input), /api/v1/semantic/* (resolve, explain,
status, certify), /api/v1/schema/* (inventory + annotations for the portal layer).
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
from collections import OrderedDict
import logging
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from semantic_layer import SEMANTIC_LAYER_VERSION
from semantic_layer.candidates.generator import CandidateGenerator
from semantic_layer.conventions import Conventions
from semantic_layer.candidates.llm_client import LlmClient
from semantic_layer.config import SemanticSettings
from semantic_layer.data_source import CRM, LOGO, data_source, source_by_entity
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.history.sources import _pid as pair_id, load_project_pairs, load_query_log
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.models import Annotation, ConceptStatus, Evidence, EvidenceType, SchemaProfile, SemanticQuery, TemporalSlot
from semantic_layer.models import Mapping as SLMapping, SemanticType
from semantic_layer.naming import label_context, logicalize_sql
from semantic_layer.normalize import normalize_term, tokenize
from semantic_layer.profiler.connectors import Connector, connector_from_file
from semantic_layer.runtime.compiler import CompilerRouter, DeterministicCompiler, Dialect, ExistingCompiler, default_filters_provider, empty_result_note, fast_summary, is_empty_result
# The fragment shown to a reviewer must be the fragment the compiler will emit; rendering a
# second, prettier version of it would let the screen and the engine disagree.
from semantic_layer.runtime.compiler import _pred_sql as compiled_predicate
from semantic_layer.runtime.audit import audit_sql, repair_qualifiers_sql, unmet_obligations
from semantic_layer.runtime import critic, value_labels
from semantic_layer.runtime.guardrails import is_query_timeout, allowed_tables, is_connection_error, physicalize_sql, referenced_tables, strip_comments, strip_trailing_semicolon, validate_sql
from semantic_layer.runtime.llm_jobs import LlmJobs
from semantic_layer.runtime.llm_queue import NORMAL, LlmQueue, QueuedLlm
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.store.catalog_store import CatalogStore, open_store, result_fingerprint

log = logging.getLogger("semantic_bridge")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _timed(batches, box: list):
    """Veritabanı süresi (dbMs) için: yalnız kaynaktan satır beklenen an sayılır.

    Parti parti okunan sonuçta araya dosyaya yazma girer; o süre veritabanının değildir.
    box[0] saniye cinsinden birikir. Arayüz bunu "Veritabanında … sürede geldi" diye gösterir.
    """
    it = iter(batches)
    while True:
        t0 = time.monotonic()
        try:
            item = next(it)
        except StopIteration:
            box[0] += time.monotonic() - t0
            return
        box[0] += time.monotonic() - t0
        yield item


def db_timing(result: Optional[dict]) -> dict:
    """Bir sonucun veritabanı süresi bilgisi, her uçta aynı biçimde.

    dbMs: satırları üreten yürütmenin veritabanında geçen süresi (ms). Önbellekten gelen
    sonuçta o ilk yürütmenin süresidir; `cached` true olur, `computedAt` (epoch sn) ne zaman
    hesaplandığını söyler. Süre ölçülmediyse dbMs None'dır — uydurulmaz.
    """
    r = result or {}
    out = {"dbMs": r.get("dbMs"), "cached": bool(r.get("cached")), "computedAt": r.get("computedAt")}
    if r.get("dbParts"):
        out["dbParts"] = r["dbParts"]
    return out


class Runtime:
    """Process-wide state: store, profiles, resolver, compilers, DB connector, recall index."""

    def __init__(self, settings: SemanticSettings, *, store: Optional[CatalogStore] = None, connector: Optional[Connector] = None, llm=None, queue: Optional[LlmQueue] = None):
        self.settings = settings
        self.store = store or open_store(settings.store_dsn)
        self.connector = connector
        self.crm_connector = None
        _crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
        if _crm_file and Path(_crm_file).exists():
            try:
                self.crm_connector = connector_from_file(_crm_file)
            except Exception as _e:  # noqa: BLE001
                log.warning("CRM connector kurulamadi: %s", str(_e)[:200])
        # One model serves everyone: requests that need it are admitted in arrival order, never rejected.
        self.queue = queue or LlmQueue.from_env(self.store.engine)
        self.llm = QueuedLlm(llm, self.queue, tenant_id=settings.tenant_id, datasource_id=settings.datasource_id) if llm is not None else None
        # Prompts other modules leave at the door (202 + id). Reads `self.llm` at run time: the admin
        # screen swaps the client without a restart.
        self.jobs = LlmJobs.from_env(self.store.engine, lambda: self.llm, slots=self.queue.slots,
                                     tenant_id=settings.tenant_id, datasource_id=settings.datasource_id)
        self._engine_lock = threading.Lock()
        # Executed results, kept whole so the table, the chart and the export read the same rows.
        self._results: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._results_lock = threading.RLock()
        self._complete_cache = OrderedDict()
        from semantic_bridge.result_files import ResultFiles
        self.result_files = ResultFiles()
        self._results_max = int(os.environ.get("SEMANTIC_RESULT_KEEP", "64"))
        self._result_ttl = float(os.environ.get("SEMANTIC_RESULT_TTL_SEC", "1800"))
        self.threads: dict[str, list[dict[str, str]]] = {}
        self.thread_plans: dict[str, Any] = {}
        self.profiles = one_entity_per_pattern(self.store.list_profiles(settings.datasource_id),
                                              self.store.concept_entities(settings.tenant_id, settings.datasource_id))
        self.rules_text = self._load_rules()
        self.pairs = load_project_pairs(settings.project_dir) if settings.project_dir else []
        self._catalog_version = None
        self._inventory_cache: dict[tuple, dict[str, Any]] = {}
        self._checked_at = 0.0
        # ---- sonuç önbelleği + arka plan tazeleyici -------------------------------------------
        # Kokpit açılışta beş ağır toplama sorgusu ister; tek bağlantı üstünde bunlar sıraya girer ve
        # kullanıcı toplam süreyi ekranda bekler. Önbellek bu beklemeyi devralır: istek anında elde
        # olanı alır, sorguyu kullanıcı adına arka plandaki tazeleyici çalıştırır.
        self._cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()
        self._cache_ttl = int(os.environ.get("SEMANTIC_CACHE_TTL_SEC", "300"))
        # Son `hot_window` saniye içinde sorulan sorgular sıcaktır; tazeleyici yalnız onlara bakar,
        # bir kez sorulup bırakılan sorgu kendiliğinden listeden düşer.
        self._refresh_sec = float(os.environ.get("SEMANTIC_REFRESH_SEC", "15"))
        self._hot_window = float(os.environ.get("SEMANTIC_HOT_WINDOW_SEC", "900"))
        # Tazeleme kaynağın tamamını bize ayıramaz: tek bağlantı var ve kullanıcının sorusu da aynı
        # sıraya giriyor. Bir turun toplam sorgu süresi, turun 1/duty'sini geçemez — beş ağır toplama
        # on beş saniyede bir koşacaksa ve toplamı on saniye tutuyorsa, tur kendiliğinden uzar.
        self._refresh_duty = float(os.environ.get("SEMANTIC_REFRESH_DUTY", "5"))
        # Tazeleyici cevap alamıyorsa bayat kopya sonsuza kadar servis edilmez: bu yaştan sonra
        # istek yeniden kaynağa iner ve kullanıcı beklemeyi görür — çünkü artık gerçek odur.
        self._stale_max = float(os.environ.get("SEMANTIC_STALE_MAX_SEC", "900"))
        self._hot: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._hot_lock = threading.Lock()
        self._waiting = 0                      # bağlantıyı bekleyen kullanıcı isteği sayısı
        self._wait_lock = threading.Lock()
        self._stop = threading.Event()
        self._refresher: Optional[threading.Thread] = None
        self.rebuild()

    #: Documents the miner reads but the prompt does not carry. `sql/` holds the validated Q→SQL pairs,
    #: which reach the model through recall instead. `reference/` holds generated vendor material —
    #: 168 KB of Logo's data dictionary — whose codes reach a question through the catalog, for the
    #: columns that question actually touches. Pasting either into every prompt spends the context on
    #: the schema the question did not ask about.
    _NOT_IN_PROMPT = {"sql", "reference"}

    def _load_rules(self) -> str:
        """Operator documentation shipped with the deployment — every *.md under knowledge/ except
        the ones that reach the model by another route."""
        pd = self.settings.project_dir
        if not pd or not (pd / "knowledge").exists():
            return ""
        # Each document keeps its boundary: the compiler leaves out, per question, a document that
        # declares itself to be about a source the question does not read (see `rules_for`).
        parts = [f"<!-- belge: {f.relative_to(pd / 'knowledge').as_posix()} -->\n" + f.read_text(encoding="utf-8")
                 for f in sorted((pd / "knowledge").rglob("*.md"))
                 if f.parent.name not in self._NOT_IN_PROMPT]
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
        from semantic_layer.runtime.language_pool import file_stamp
        if version != self._catalog_version:
            log.info("catalog changed (%s → %s) — reloading profiles", self._catalog_version, version)
            self.rebuild()
        elif file_stamp(os.environ.get("SEMANTIC_LANGUAGE_POOL")) != getattr(self, "_language_pool_stamp", None):
            self._reload_language_pool_in_background()

    def _reload_language_pool_in_background(self) -> None:
        """A published pool of ~180k phrases takes the better part of a minute to validate and index.
        Doing that inside the request that noticed the new file made one person wait for it, so the new
        pool is built on a thread while the old one keeps answering, then swapped in whole."""
        if getattr(self, "_pool_loading", False):
            return
        self._pool_loading = True
        from semantic_layer.runtime.language_pool import LanguagePool, file_stamp
        pool_path = os.environ.get("SEMANTIC_LANGUAGE_POOL")
        stamp = file_stamp(pool_path)
        profiles, existing = self.profiles, self.existing

        def load() -> None:
            try:
                started = time.perf_counter()
                pool = LanguagePool.load(pool_path, profiles, self.settings.datasource_id,
                                         existing.annotations if existing is not None else {})
                if self.profiles is not profiles:
                    return          # a catalog rebuild ran meanwhile and loaded its own pool
                self.language_pool = pool
                if existing is not None:
                    existing.language_pool = pool
                self._language_pool_stamp = stamp
                log.info("language pool reloaded in background: %d candidates, %d stale/invalid rejected, hash %s, %.1fs",
                         len(pool.entries), pool.rejected, pool.content_hash[:12], time.perf_counter() - started)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
                self._language_pool_stamp = stamp   # do not retry a broken file every 30 seconds
                log.warning("language pool reload failed, keeping the previous pool: %s", e)
            finally:
                self._pool_loading = False

        threading.Thread(target=load, name="language-pool-reload", daemon=True).start()

    def rebuild(self) -> None:
        s = self.settings
        self.profiles = one_entity_per_pattern(self.store.list_profiles(s.datasource_id),
                                              self.store.concept_entities(s.tenant_id, s.datasource_id))
        self._catalog_version = self.store.catalog_fingerprint(s.tenant_id, s.datasource_id)
        self._checked_at = time.time()
        self._inventory_cache: dict[tuple, dict[str, Any]] = {}
        self.conventions = Conventions.from_profiles(self.profiles)
        if s.project_dir:
            self.conventions.load_equivalences(s.project_dir / "equivalences.yml")
        # Declared period coverage the nightly measurement did not refute: the period chooser and the
        # gate read it off the profile; a table without it keeps needing its date filter.
        from semantic_layer import coverage as coverage_mod
        coverage_mod.apply(self.profiles, self.store, s)
        if not s.dialect:
            s.dialect = getattr(self.connector, "dialect", "") or "generic"
        default_temporal = _default_period()
        self.resolver = SemanticResolver(self.store, s.tenant_id, s.datasource_id, self.profiles, default_temporal=default_temporal, conventions=self.conventions, verified_pairs=self.pairs)
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
        # The vocabulary someone has already written down tells the prompt which tables matter; a
        # three-hundred-table schema would not fit in a local model's context, and sending it whole
        # would bury the handful that answer the question.
        try:
            index = self.store.certified_index(s.tenant_id, s.datasource_id)
            maps_all = [m for senses in index.values() for _, maps in senses for m in maps]
            existing.catalog_entities = {m.entity for m in maps_all}
            # Which columns, not just which tables. When a context budget forces a choice, the
            # columns a certified concept is built on are the ones that must survive it.
            cols: set[tuple[str, str]] = set()
            for m in maps_all:
                if m.entity and m.column:
                    cols.add((m.entity, m.column.upper()))
                for ent, col in re.findall(r"\b(\w+)\.\"?(\w+)\"?", str(m.formula or "")):
                    cols.add((ent, col.upper()))
            existing.catalog_columns = cols
        except Exception as e:  # noqa: BLE001
            log.debug("catalog entity set unavailable: %s", e)
        # Vector routing over the catalog, for questions whose words nobody has written down yet. It
        # is strictly additional: the certified vocabulary above is consulted first and always, and a
        # deployment with no index — or one whose index is unreachable — routes exactly as before.
        # Column-level lexical and value search. Nothing to deploy and nothing to keep in step: it is
        # built from the catalog already in memory, costs milliseconds, and says which word or which
        # value matched. It runs after the certified vocabulary, so it can only add tables a question
        # would otherwise have had no way to reach. Set SEMANTIC_COLUMN_ROUTER=0 to turn it off.
        if os.environ.get("SEMANTIC_COLUMN_ROUTER", "1").strip() not in ("0", "false", "no", "off"):
            try:
                from semantic_layer.runtime.column_index import ColumnIndex

                existing.columns = ColumnIndex(self.profiles, existing.annotations)
                # The resolver reads it too: a word the certified vocabulary has no entry for may
                # still be the name of a column this schema carries, and that is decided while the
                # question is being resolved — not later, by a model guessing at a column name.
                self.resolver.columns = existing.columns
                log.info("column index enabled: %d columns, %d distinct values",
                         len(existing.columns.docs), len(existing.columns.values))
            except Exception as e:  # noqa: BLE001
                log.warning("column index unavailable, routing from the catalog alone: %s", e)

        # Narrows the retrieved shortlist before it becomes a prompt — the step every schema-linking
        # result says matters most. Measured on this deployment's golden set:
        #
        #     no selector   12.0 tables   precision 0.17   recall 17/17
        #     selector       5.1 tables   precision 0.31   recall 17/17   ~4.2s
        #
        # Default is shadow: it runs, it logs what it would have kept, and the prompt is unchanged.
        # SEMANTIC_TABLE_SELECTOR=on applies it; =off skips the call entirely.
        # `existing` is the model-backed compiler; with SEMANTIC_LLM=0 there is none, and reading its
        # selector mode raised AttributeError before the service could start at all. A deployment that
        # has deliberately turned the model off must still come up on the deterministic path.
        if existing is not None and existing.selector_mode in ("shadow", "on") and s.llm_base:
            try:
                from semantic_layer.runtime.table_selector import TableSelector

                base = os.environ.get("SEMANTIC_SELECTOR_BASE", "").strip() or s.llm_base
                model = os.environ.get("SEMANTIC_SELECTOR_MODEL", "").strip() or s.llm_model
                timeout = float(os.environ.get("SEMANTIC_SELECTOR_TIMEOUT_SEC", "30"))
                # A reasoning model asked to name tables spends most of its time explaining the
                # choice to itself. It is not wanted here and the person asking pays for it.
                client = LlmClient(base, model, s.llm_key, timeout,
                                   extra={"chat_template_kwargs": {"enable_thinking": False}} | s.llm_extra)
                # Through the same line as every other call: it used to go straight to the provider,
                # one more concurrent request than the slot count says there is.
                existing.selector = TableSelector(QueuedLlm(client, self.queue, purpose="nl2sql:selector",
                                                            tenant_id=s.tenant_id, datasource_id=s.datasource_id))
                log.info("table selector enabled (%s, model %s, mode %s)", base, model, existing.selector_mode)
            except Exception as e:  # noqa: BLE001
                log.warning("table selector unavailable, sending every retrieved table: %s", e)

        # Looks a word the resolver could not place up in the data before the prompt is built —
        # the one move a person makes that this system did not: open the database and run a SELECT
        # before writing the query. Needs the live connector; without one, nothing changes.
        if self.connector is not None and os.environ.get("SEMANTIC_VALUE_PROBE", "1").strip() not in ("0", "false", "no", "off"):
            try:
                from semantic_layer.runtime.value_probe import ValueProbe

                existing.probe = ValueProbe(self.connector, self.profiles)
                log.info("value probe enabled (%d columns, %.0fs budget)",
                         existing.probe.max_columns, existing.probe.budget)
            except Exception as e:  # noqa: BLE001
                log.warning("value probe unavailable, questions answered from the catalog alone: %s", e)

        try:
            from semantic_layer.runtime.table_router import TableRouter

            router = TableRouter(s.datasource_id)
            if router.configured:
                existing.router = router
                log.info("table router enabled (%s, collection %s)", router.qdrant_url, router.collection)
        except Exception as e:  # noqa: BLE001
            log.debug("table router unavailable, routing from the catalog alone: %s", e)
        # What people wrote in the portal is the last word on what a column means; until now the model
        # never saw it. The newest annotation for a table or column wins over an older one.
        try:
            by_pattern = {p.table_pattern: p.entity for p in self.profiles}
            said: dict[tuple[str, Optional[str]], str] = {}
            for a in sorted(self.store.list_annotations(s.datasource_id), key=lambda a: a.created_at):
                entity = by_pattern.get(a.table_pattern)
                if entity and a.text:
                    said[(entity, (a.column or "").upper() or None)] = a.text
            existing.annotations = said
            if said:
                log.info("%d portal annotations carried into the model prompt", len(said))
        except Exception as e:  # noqa: BLE001
            log.debug("annotations unavailable: %s", e)
        from semantic_layer.runtime.language_pool import LanguagePool, file_stamp
        pool_path = os.environ.get("SEMANTIC_LANGUAGE_POOL")
        self._language_pool_stamp = file_stamp(pool_path)
        try:
            self.language_pool = LanguagePool.load(pool_path, self.profiles, s.datasource_id,
                                                   existing.annotations if existing is not None else {})
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
            log.warning("language pool unavailable: %s", e)
            self.language_pool = LanguagePool()
        if existing is not None:
            existing.language_pool = self.language_pool
        log.info("language pool: %d candidates, %d stale/invalid rejected, hash %s",
                 len(self.language_pool.entries), self.language_pool.rejected, self.language_pool.content_hash[:12])
        self.router = CompilerRouter(det, existing, strict_miss=s.strict_miss, primary=os.environ.get("SEMANTIC_COMPILER", ""), shadow=shadow, alternates=alternates)

    # ------------------------------------------------------------------ recall (Memory ON)
    def recall(self, question: str, exclude_nl: Optional[str] = None) -> list[dict[str, str]]:
        """Token-Jaccard recall over validated pairs (project knowledge + runtime-validated log). No vectors."""
        q = set(tokenize(question))
        if not q:
            return []
        rows = [{"nl": p.nl, "sql": p.sql} for p in self.pairs if p.source != "seed"]
        for r in self.store.list_validated_queries(self.settings.tenant_id, self.settings.datasource_id, limit=500):
            rows.append({"nl": r["question"], "sql": logicalize_sql(r["sql_text"])})
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
    def _physical(self, sql: str, period: Optional[tuple] = None, *, scope=None) -> str:
        """`period` lets an entity split one-table-per-year resolve to the tables that year needs.

        Passed only where the question is known. The endpoints that take raw SQL have no question and
        no period, and there the behaviour is what it always was: one entity, one table.
        """
        from semantic_layer.runtime.context_scope import execution_profiles
        profiles = execution_profiles(sql, self.profiles, scope, self.settings.dialect or "tsql")
        return physicalize_sql(strip_trailing_semicolon(sql), profiles, {**self.settings.context, **(scope or {})},
                               self.settings.dialect, period=period)

    @staticmethod
    def _asked_period(q: Any) -> Optional[tuple]:
        """The span a question asked for, or None when it named no period at all."""
        if q is None:
            return None
        start = min((t.start for t in getattr(q, "temporal", []) if t.start), default=None)
        end = max((t.end for t in getattr(q, "temporal", []) if t.end), default=None)
        return (start, end) if start and end else None

    def _conn_for(self, sql: str):
        if self.crm_connector is None or "timas_mscrm" not in (sql or "").lower():
            return self.connector
        residual = re.sub(r"\[?timas_mscrm\]?\.\[?dbo\]?\.", " ", sql, flags=re.I)
        if re.search(r"(?<![\w.])\[?dbo\]?\.", residual, re.I) or re.search(r"(?<![\w.])\[?LG_\w", residual):
            raise ValueError("Logo ve CRM artik ayri sunucularda; tek soruda birlestirilemez.")
        return self.crm_connector

    def dry_run(self, sql: str) -> None:
        if self.connector is None:
            raise RuntimeError("no database connector")
        with self._engine_lock:
            self._conn_for(sql).dry_run(sql)

    def run_sql(self, sql: str, limit: int, period: Optional[tuple] = None, *, scope=None) -> dict[str, Any]:
        sql = strip_comments(sql or "")
        ok, why = validate_sql(sql)
        if not ok:
            raise ValueError(f"SQL rejected: {why}")
        # The endpoint reads the catalog's tables — not everything the database login can reach.
        ok, why = allowed_tables(sql, self.profiles, self.settings.context, self.settings.dialect or None)
        if not ok:
            raise ValueError(f"SQL rejected: {why}")
        limit = max(1, min(int(limit or self.settings.max_rows), self.settings.max_rows))
        # The period travels with the SQL so the answer is executed against the same tables the
        # response reports. Without it the two disagree the moment a question spans a year boundary,
        # and the row the person is looking at came from a table the explanation does not name. It is
        # also part of the cache key by construction: it changes `phys`, and `phys` is what is hashed.
        phys = self._physical(sql, period, **({"scope": scope} if scope else {}))
        key = hashlib.sha256(f"{limit}\n{phys}".encode()).hexdigest()
        if self._cache_ttl > 0:
            self._touch_hot(key, phys, limit)
            hit = self._cache.get(key)
            if hit:
                age = time.time() - hit[0]
                # Taze kopya doğrudan gider. Süresi geçmiş kopya da gider — ama yalnız tazeleyici
                # ayaktaysa: o zaman bekleme kimseye bir şey kazandırmaz, yenisi zaten yolda.
                if age < self._cache_ttl or (self._refresher_alive() and age < self._stale_max):
                    out = self._served(hit[1], hit[0])
                    out["cached"] = True
                    return self._labelled(sql, out)
        out, duration = self._execute(phys, limit, interactive=True)
        computed_at = time.time()
        self._remember(key, out, duration, computed_at=computed_at)
        served = self._served(out, computed_at)
        served["cached"] = False
        return self._labelled(sql, served)

    def _labelled(self, sql: str, out: dict[str, Any]) -> dict[str, Any]:
        """Seçim listesi kodları etiketiyle: insan "4" değil "Satış" görür (value_labels katalogdan)."""
        try:
            mapping = value_labels.label_map(sql, self.profiles, self.settings.dialect or "tsql")
            if mapping and out.get("records"):
                out = dict(out, records=value_labels.apply(out["records"], mapping))
        except Exception:  # noqa: BLE001 — etiket bir kolaylıktır, cevabı düşürmez
            log.exception("value label decoding failed")
        return out

    # ------------------------------------------------------------------ önbellek iç işleyişi

    def _execute(self, phys: str, limit: int, *, interactive: bool) -> tuple[dict[str, Any], float]:
        """Tek bağlantı, tek sıra. `interactive` olan istek beklerken tazeleyici sıraya girmez."""
        if self.connector is None:
            raise RuntimeError("no database connector")
        if interactive:
            with self._wait_lock:
                self._waiting += 1
        try:
            with self._engine_lock:
                t0 = time.monotonic()
                cols, rows, truncated = self._conn_for(phys).execute(phys, limit)
                duration = time.monotonic() - t0
        finally:
            if interactive:
                with self._wait_lock:
                    self._waiting -= 1
        return {"columns": cols, "records": rows, "totalRows": len(rows), "truncated": truncated, "physicalSql": phys,
                "dbMs": int(round(duration * 1000))}, duration

    def run_complete(self, sql: str, period=None, *, scope=None) -> dict[str, Any]:
        ok, why = validate_sql(sql)
        if not ok:
            raise ValueError(why)
        ok, why = allowed_tables(sql, self.profiles, self.settings.context, self.settings.dialect or None)
        if not ok:
            raise ValueError(why)
        phys = self._physical(sql, period, **({"scope": scope} if scope else {}))
        if not hasattr(self.connector, 'batches'):
            # Non-DB adapters retain their explicit bounded execution contract.
            return self.run_sql(sql, self.settings.max_rows, period, **({"scope": scope} if scope else {}))
        with self._wait_lock:
            self._waiting += 1
        try:
            with self._engine_lock:
                key = hashlib.sha256(phys.encode()).hexdigest()
                cached = self._complete_cache.get(key)
                if cached and self._cache_ttl > 0 and time.time() - cached[0] < self._cache_ttl and Path(cached[1]['_result_file']).exists():
                    return dict(self._served(cached[1], cached[0]), cached=True)
                with self._results_lock:
                    for rid, snap in list(self._results.items()):
                        if time.time() - snap['at'] > self._result_ttl:
                            self._discard_result(rid)
                    # Reserve room before execution; older downloadable snapshots expire first.
                    reserve = min(self.result_files.max_bytes, self.result_files.disk_budget)
                    while self._results and sum(p.stat().st_size for p in Path(self.result_files.directory.name).glob('*.jsonl')) + reserve > self.result_files.disk_budget:
                        self._discard_result(next(iter(self._results)))
                db = [0.0]
                try:
                    mapping = value_labels.label_map(sql, self.profiles, self.settings.dialect or "tsql")
                except Exception:  # noqa: BLE001
                    mapping = {}
                source = self._conn_for(phys).batches(phys)
                if mapping:
                    source = ((cols, value_labels.apply(rows, mapping)) for cols, rows in source)
                out = self.result_files.write(_timed(source, db), self.settings.max_rows)
                out.update(physicalSql=phys, cached=False, dbMs=int(round(db[0] * 1000)))
                computed_at = time.time()
                self._complete_cache[key] = (computed_at, out)
                self._complete_cache.move_to_end(key)
                while len(self._complete_cache) > 64:
                    self._complete_cache.popitem(last=False)
        finally:
            with self._wait_lock:
                self._waiting -= 1
        out.update(physicalSql=phys, cached=False)
        return self._served(out, computed_at)

    def _discard_result(self, rid):
        old = self._results.pop(rid, None)
        if old and old.get('_result_file') and not any(s.get('_result_file') == old['_result_file'] for s in self._results.values()):
            self.result_files.remove(old['_result_file'])

    def remember_result(self, result: dict[str, Any], *, question: str, sql: str) -> None:
        """Keep the whole executed result so everything downstream reads the same rows.

        The display shows a page of it and the export needs all of it; without this the export had to
        run the query again, which is a different execution against data that can have changed, and
        it went out without the period the answer was computed with. Bound to the tenant this bridge
        serves and dropped after `_result_ttl`; a caller asking for one that is gone is told so
        rather than quietly served a fresh run of the same SQL.
        """
        rid = result.get("id")
        if not rid:
            return
        with self._results_lock:
            self._results[rid] = {
                "tenant_id": self.settings.tenant_id,
                "at": time.time(),
                "computedAt": result.get("computedAt", time.time()),
                "question": question,
                "sql": sql,
                "physicalSql": result.get("physicalSql"),
                "columns": result.get("columns") or [],
                "records": [] if result.get("_result_file") else result.get("records") or [],
                "_result_file": result.get("_result_file"),
                "totalRows": result.get("totalRows") or 0,
                "truncated": bool(result.get("truncated")),
                "dataCoverage": result.get("dataCoverage", []), "dataNotes": result.get("dataNotes", []),
                "comparison": result.get("comparison"),
            }
            for old_id, old in list(self._results.items()):
                if time.time() - old['at'] > self._result_ttl:
                    self._discard_result(old_id)
            while len(self._results) > self._results_max:
                self._discard_result(next(iter(self._results)))

    def stored_result(self, rid: str, *, load_rows: bool = True) -> Optional[dict[str, Any]]:
        with self._results_lock:
            snap = self._results.get(rid)
            if snap is None:
                return None
            if time.time() - snap["at"] > self._result_ttl:
                self._discard_result(rid)
                return None
            if snap["tenant_id"] != self.settings.tenant_id:
                return None
            if load_rows and snap.get("_result_file"):
                return dict(snap, records=self.result_files.read(snap["_result_file"]))
            return snap

    def attach_widget(self, result: dict[str, Any], question: str) -> None:
        """The chart spec for a result set, decided in the backend so every surface draws the same one."""
        try:
            from nanobase_api.chat_widgets import widgets_from_query_result  # optional, same as legacy bridge

            widgets = widgets_from_query_result(columns=result.get("columns"), rows=result.get("records"),
                                                title=(question or "").strip() or None)
            if widgets:
                w = dict(widgets[0])
                w.pop("sql", None)
                if w.get("type") != "multi_card":
                    w.pop("data", None)
                # Multiple grouping dimensions cannot be collapsed into one label.
                names = [c['name'] for c in result.get('columns', [])]
                sample = result.get('records') or []
                categorical = [n for n in names if any(isinstance(row.get(n), str) for row in sample)]
                if len(categorical) > 1:
                    w = {'id': w.get('id'), 'type': 'table', 'title': question}
                result["widget"] = w
        except Exception:  # noqa: BLE001
            pass

    def _served(self, out: dict[str, Any], computed_at: float) -> dict[str, Any]:
        """Sonucun bu isteğe ait kopyası. Yaş cevabın içinde gider: arayüz rakamın ne zaman
        hesaplandığını söyleyebilsin, "canlı" etiketi bir dakikalık kopyanın üstünde durmasın."""
        copy = dict(out)
        copy["id"] = uuid.uuid4().hex
        copy["computedAt"] = round(computed_at, 3)
        copy["ageSec"] = round(max(0.0, time.time() - computed_at), 1)
        return copy

    def _remember(self, key: str, out: dict[str, Any], duration: float, *, computed_at: Optional[float] = None) -> None:
        if self._cache_ttl <= 0 or len(out.get("records") or []) > 200:
            with self._hot_lock:
                self._hot.pop(key, None)
            return
        self._cache[key] = (time.time() if computed_at is None else computed_at, out)
        self._cache.move_to_end(key)
        budget = int(os.environ.get("SEMANTIC_CACHE_MAX_ROWS", "5000"))
        while len(self._cache) > 64 or sum(len(v[1].get("records") or []) for v in self._cache.values()) > budget:
            dropped, _ = self._cache.popitem(last=False)
            with self._hot_lock:
                self._hot.pop(dropped, None)
        with self._hot_lock:
            hot = self._hot.get(key)
            if hot is not None:
                hot["duration"] = duration
                hot["fails"] = 0

    def _touch_hot(self, key: str, phys: str, limit: int) -> None:
        """Sorulan her sorgu sıcak listeye yazılır; tazeleyicinin işi bu listeyi güncel tutmaktır."""
        with self._hot_lock:
            hot = self._hot.get(key)
            if hot is None:
                hot = self._hot[key] = {"sql": phys, "limit": limit, "duration": 0.0, "fails": 0}
            hot["asked"] = time.time()
            self._hot.move_to_end(key)
            while len(self._hot) > 64:
                self._hot.popitem(last=False)

    def _refresher_alive(self) -> bool:
        t = self._refresher
        return t is not None and t.is_alive()

    def start_refresher(self) -> None:
        """Sıcak sorguları kullanıcıdan önce tazeleyen tek iş parçacığı. Uygulama ayağa kalkarken
        çağrılır; SEMANTIC_REFRESH_SEC=0 ile kapatılır ve o zaman her istek kaynağa iner."""
        if self._refresh_sec <= 0 or self._cache_ttl <= 0 or self.connector is None:
            return
        if self._refresher_alive():
            return
        self._stop = threading.Event()
        self._refresher = threading.Thread(target=self._refresh_loop, name="sql-refresh", daemon=True)
        self._refresher.start()
        log.info("background refresh on: every %.0fs, hot window %.0fs", self._refresh_sec, self._hot_window)

    def stop_refresher(self) -> None:
        self._stop.set()

    def llm_for(self, module: str, priority: Optional[int] = None):
        """The shared model, asked on behalf of `module`: the queue shares slots between modules, so
        it has to know which one is asking. None when no model is configured."""
        return self.llm.for_module(module, priority=priority) if isinstance(self.llm, QueuedLlm) else self.llm

    def _refresh_loop(self) -> None:
        while not self._stop.wait(self._refresh_sec):
            try:
                self._refresh_tick()
            except Exception as e:  # noqa: BLE001
                log.warning("refresh tick failed: %s", e)

    def _refresh_tick(self) -> None:
        now = time.time()
        with self._hot_lock:
            for k, hot in list(self._hot.items()):
                if now - hot.get("asked", 0.0) > self._hot_window:
                    self._hot.pop(k, None)        # kimse bakmıyor: kaynağı da meşgul etmeyelim
            # Tur uzunluğu sıcak kümenin tamamına bakılarak bulunur: tek tek bakılırsa beş sorgunun
            # her biri sınırı aşmaz ama beşi birden bağlantıyı doldurur.
            cycle = max(self._refresh_sec, sum(h.get("duration", 0.0) for h in self._hot.values()) * self._refresh_duty)
            due = []
            for k, hot in self._hot.items():
                cached_at = self._cache[k][0] if k in self._cache else 0.0
                if now - cached_at >= cycle:
                    due.append((k, dict(hot)))
        for key, hot in due:
            if self._waiting or self._stop.is_set():
                return                            # bekleyen bir kullanıcı varsa sıra onun
            self._refresh_one(key, hot)

    def _refresh_one(self, key: str, hot: dict[str, Any]) -> None:
        try:
            out, duration = self._execute(hot["sql"], hot["limit"], interactive=False)
        except Exception as e:  # noqa: BLE001
            with self._hot_lock:
                cur = self._hot.get(key)
                if cur is not None:
                    cur["fails"] = cur.get("fails", 0) + 1
                    if cur["fails"] >= 5:         # kaynak cevap vermiyor: denemeyi bırak, istek gelince yeniden dene
                        self._hot.pop(key, None)
            log.warning("background refresh failed (%s…): %s", key[:8], e)
            return
        self._remember(key, out, duration)

    def cache_stats(self) -> dict[str, Any]:
        with self._hot_lock:
            hot = len(self._hot)
        return {"entries": len(self._cache), "hot": hot, "ttlSec": self._cache_ttl, "refreshSec": self._refresh_sec, "refreshing": self._refresher_alive()}

    def summarize(self, question: str, sql: str, result: dict[str, Any], sq: Optional[SemanticQuery] = None) -> str:
        cols = [c["name"] for c in result.get("columns") or []]
        # Observed row dates are not loading-completeness evidence. Keep coverage
        # notes even when a partial period has a nonempty aggregate.
        note = ""
        if sq is not None:
            note = " ".join(e for e in sq.explanation if "kısmen gözleniyor" in e or "gözlenen veri kapsamı dışında" in e or "Karşılaştırmada" in e)
            if sq.absence_contract:
                note += " " + sq.absence_contract.get("scope_note", "")
            if note:
                note = " " + note
        if result.get('truncated'):
            note += " Sonuç sınırda kesildi; toplam satır sayısı bilinmiyor."
        if not (result.get("records") or []) and not int(result.get("totalRows") or 0):
            note += empty_result_note(sql, self.rules_text)
        # A condition on a column that carries no information (never filled, or declared by a person
        # to hold something other than its name says) is said with the answer: "0 satır" or "1.061
        # satır" otherwise reads as a fact about the business when it is a fact about the data entry.
        try:
            from semantic_layer.runtime.column_facts import notes_text, nothing_came_back, predicate_column_notes
            data_notes = predicate_column_notes(sql, self.profiles, getattr(self.existing, "annotations", None) or {},
                                                sources=self.router.gate_sources(),
                                                result_is_empty=nothing_came_back(result.get("records") or [], int(result.get("totalRows") or 0)))
        except Exception as e:  # noqa: BLE001
            log.debug("column data notes unavailable: %s", e)
            data_notes = []
        result["dataNotes"] = data_notes
        note += notes_text(data_notes)
        if self.settings.summary_mode == "llm" and self.llm is not None:
            sample = result["records"][:20]
            prompt = ("Aşağıdaki soru ve sorgu sonucunu 1-3 cümlede Türkçe özetle. Sayıları Türkçe biçimle, yorum katma, sadece veride olanı söyle.\n"
                      f"Soru: {question}\nSatır sayısı: {result['totalRows']}\nİlk satırlar (JSON): {json.dumps(sample, ensure_ascii=False)[:4000]}")
            try:
                return self.llm_for("summary").chat([{"role": "user", "content": prompt}], max_tokens=300).strip() + note
            except Exception as e:  # noqa: BLE001
                log.warning("llm summary failed: %s", e)
        return fast_summary(question, cols, result.get("records") or [], int(result.get("totalRows") or 0)) + note

    # ------------------------------------------------------------------ ask
    def ask(self, question: str, *, thread_id: Optional[str], sample_size: int, exclude_nl: Optional[str] = None, execute: bool = True, progress=None, username: Optional[str] = None) -> dict[str, Any]:
        report = progress or (lambda stage: None)
        report("understanding")
        t0 = time.perf_counter()
        timings: dict[str, int] = {}
        thread_id = thread_id or uuid.uuid4().hex

        def _log(*, sql, compiler, catalog_version, executed, resolved=None, answer_type=None,
                 answer_summary=None, error=None, row_count=None, latency_ms=None,
                 result_fingerprint=None, result_json=None, gate=None) -> str:
            """Promt izleyici kaydı: her dal buradan geçer, böylece kim sordu / ne cevap döndü / kapı
            ne dedi tek yerde ve eksiksiz yazılır (bkz. sl_query_log, /api/v1/admin/prompts)."""
            return self.store.log_query(
                self.settings.tenant_id, self.settings.datasource_id, question,
                sql=sql, compiler=compiler, catalog_version=catalog_version,
                resolved=(resolved if resolved is not None else {}), executed=executed,
                row_count=row_count, latency_ms=latency_ms, error=error,
                result_fingerprint=result_fingerprint, username=username, thread_id=thread_id,
                answer_type=answer_type, answer_summary=answer_summary,
                result_json=result_json, gate_json=gate)
        thread = self.threads.setdefault(thread_id, [])
        # a long-lived process must not accumulate every conversation it ever served
        if len(self.threads) > 200:
            for stale in list(self.threads)[:-100]:
                self.threads.pop(stale, None)
                self.thread_plans.pop(stale, None)
        from semantic_bridge.chat_scope import BI_INTRO, is_intro
        if is_intro(question):
            qid = _log(sql=None, compiler="intro", catalog_version=None, executed=False,
                       answer_type="MODULE_INTRO", answer_summary=BI_INTRO)
            return {"id": uuid.uuid4().hex, "type": "MODULE_INTRO", "module": "bi",
                    "explanation": BI_INTRO, "threadId": thread_id, "timings": timings, "queryId": qid}
        self.ensure_fresh()
        t = time.perf_counter()
        from semantic_layer.runtime.conversation import compose_followup, bind_followup_value
        effective_question, context_error = compose_followup(question, self.thread_plans.get(thread_id))
        if context_error:
            qid = _log(sql=None, compiler="clarification", catalog_version=None, executed=False,
                       answer_type="CLARIFICATION", answer_summary=context_error)
            return {"id": uuid.uuid4().hex, "type": "CLARIFICATION", "explanation": context_error,
                    "threadId": thread_id, "timings": timings, "queryId": qid}
        sq = self.resolver.resolve(effective_question)
        sq.language_candidates = self.language_pool.search(effective_question)
        sq.language_pool_hash = self.language_pool.content_hash
        from semantic_layer.runtime.context_scope import extract_scope
        sq.context_scope, scope_errors = extract_scope(effective_question, getattr(self.settings, "pattern_labels", []), self.profiles)
        sq.clarification.extend(scope_errors)
        scope_args = {"scope": sq.context_scope} if sq.context_scope else {}
        # Certified data concepts are positive evidence of a BI request. Only unplaced
        # questions need the conversational classifier; unknown terms remain eligible.
        if not any(slot.mapping is not None for slot in sq.slots) and is_intro(
                question, self.llm_for("chat"), has_context=bool(self.thread_plans.get(thread_id))):
            qid = _log(sql=None, compiler="intro", catalog_version=sq.catalog_version, executed=False,
                       resolved=sq.to_dict(), answer_type="MODULE_INTRO", answer_summary=BI_INTRO)
            return {"id": uuid.uuid4().hex, "type": "MODULE_INTRO", "module": "bi",
                    "explanation": BI_INTRO, "threadId": thread_id, "timings": timings, "queryId": qid}
        if self.thread_plans.get(thread_id) is not None and getattr(self, "existing", None) is not None:
            bind_followup_value(question, sq, self.thread_plans[thread_id], self.existing.probe,
                                self.existing.columns, self.conventions)
        if effective_question != question:
            sq.explanation.append(f"Konuşma bağlamıyla tamamlanan soru: {effective_question}")
        timings["resolve_ms"] = int((time.perf_counter() - t) * 1000)
        if any(c["status"] == "OUTSIDE_OBSERVED" for c in sq.data_coverage):
            reason = " ".join(e for e in sq.explanation if "gözlenen veri kapsamı dışında" in e)
            qid = _log(sql=None, compiler="coverage", catalog_version=sq.catalog_version,
                       resolved=sq.to_dict(), executed=False, error=reason,
                       answer_type="DATA_UNAVAILABLE", answer_summary=reason,
                       gate={"dataCoverage": list(sq.data_coverage)})
            return {"id": uuid.uuid4().hex, "type": "DATA_UNAVAILABLE", "explanation": reason,
                    "threadId": thread_id, "timings": timings, "semantic": {"query": sq.to_dict()}, "queryId": qid}
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
        if compiled.compiler == "incomplete":
            reason = "Sorudaki koşulların tamamı doğrulanamadı: " + "; ".join(compiled.explain)
            if sq.unresolved:
                # The gate's objection is the symptom; a word the catalog cannot place is the cause.
                # Lead with what the person can act on: which word, and where the data may sit.
                hints = [c for c in (sq.candidates or []) if c.get("term") in sq.unresolved]
                where = "; ".join(f"'{c['term']}' → " + ", ".join(f"{e}.{c['column']}" for e in (c.get("entities") or [])[:2]) for c in hints[:3])
                reason = (f"'{', '.join(sq.unresolved[:3])}' katalogda tanımlı bir kavram değil; bu yüzden üretilen sorgu doğrulanamadı. "
                          + (f"Şemada karşılığı olabilecek kolonlar: {where}. " if where else "")
                          + "Terimi Veri Sözlüğü'nden tanımlarsanız soru cevaplanır. Kapı gerekçesi: " + "; ".join(compiled.explain))
            qid = _log(sql=None, compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                       resolved=sq.to_dict(), executed=False, error=reason,
                       answer_type="INCOMPLETE_ANSWER", answer_summary=reason,
                       gate={"explain": list(compiled.explain)})
            return {"id": uuid.uuid4().hex, "type": "INCOMPLETE_ANSWER", "explanation": reason,
                    "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        if compiled.compiler == "clarification":
            reason = " ".join(compiled.explain)
            qid = _log(sql=None, compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                       resolved=sq.to_dict(), executed=False,
                       answer_type="CLARIFICATION", answer_summary=reason,
                       gate={"explain": list(compiled.explain)})
            thread.extend([{"role": "user", "content": question}, {"role": "assistant", "content": reason}])
            return {"id": uuid.uuid4().hex, "type": "CLARIFICATION", "needs_clarification": True,
                    "explanation": reason, "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        if compiled.plan is not None:
            return self._answer_plan(question, sq, compiled, semantic, thread, thread_id, timings, t0,
                                     sample_size, scope_args, report, execute)
        if not compiled.sql:
            reason = "; ".join(compiled.explain)[:500]
            if sq.out_of_scope:
                reason = next((e for e in sq.explanation if "kapsamı dışında" in e), reason)
            qid = _log(sql=None, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=reason,
                       answer_type="NON_SQL_QUERY", answer_summary=reason, gate={"explain": list(compiled.explain)})
            return {"id": uuid.uuid4().hex, "type": "NON_SQL_QUERY", "explanation": reason or "Model bu soru için SQL üretmedi.", "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        sql = repair_qualifiers_sql(strip_trailing_semicolon(compiled.sql))
        ok, why = validate_sql(sql)
        if not ok:
            reason = f"Guardrail: {why}"
            qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=reason,
                       answer_type="SQL_INVALID", answer_summary=reason, gate={"guardrail": why})
            return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": reason, "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        # What the question asked for and the statement does not deliver. Checked for every query,
        # certified or not: a comparison is built by the deterministic compiler too, and a single
        # period returned for "geçen yıla göre" is a complete-looking answer to a different question.
        unmet = unmet_obligations(sq, sql, sources=self.router.gate_sources())
        if unmet:
            reason = "Sorudaki koşulların tamamı doğrulanamadı: " + "; ".join(unmet)
            log.warning("obligation unmet q=%r %s sql=%s", question[:80], unmet, " ".join(sql.split())[:1500])
            semantic["unmetObligations"] = unmet
            qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=reason,
                       answer_type="INCOMPLETE_ANSWER", answer_summary=reason, gate={"unmetObligations": list(unmet)})
            return {"id": uuid.uuid4().hex, "type": "INCOMPLETE_ANSWER", "sql": sql, "explanation": reason,
                    "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}

        # The prompt asks the model to honour the certified catalog; this is where we check that it did.
        # A query that contradicts a certified fact answers a different question than the one asked.
        if not compiled.certified:
            contradictions = audit_sql(sq, sql, conventions=self.conventions)
            if contradictions:
                semantic["catalogAudit"] = contradictions
                reason = "Üretilen SQL sertifikalı katalogla çelişiyor: " + "; ".join(contradictions)
                log.warning("catalog audit refused q=%r %s", question[:80], contradictions)
                qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=reason,
                           answer_type="SQL_INVALID", answer_summary=reason, gate={"catalogAudit": list(contradictions)})
                return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": reason, "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        repairs = 0
        error: Optional[str] = None
        critic_notes: list[dict] = []
        if self.connector is not None:
            for attempt in range(3):
                try:
                    # Read the query against what the catalog already knows *before* asking the
                    # database. A column the model invented or a join it mis-keyed is the catalog's
                    # to catch, with a message the model can repair against — not a raw driver error
                    # ("Invalid column name 'AMOUNT'") that the person should never be shown. The
                    # reviewer never executes and fails open on anything it cannot read, so running it
                    # first only moves *where* a catalog-visible fault is caught, from the database to
                    # here; the dry_run below still catches everything the catalog cannot see.
                    found = critic.review(sql, self.profiles, self.settings.dialect or "tsql",
                                          names=self.store.entity_terms(self.settings.tenant_id, self.settings.datasource_id))
                    critic_notes = [f.to_dict() for f in found]
                    blocking = [f for f in found if f.severity == "block"]
                    if blocking:
                        log.warning("critic refused q=%r %s", question[:80], [f.kind for f in blocking])
                        if attempt == 2 or self.existing is None or compiled.compiler == "deterministic":
                            # Out of attempts, or the SQL came from the deterministic compiler — which
                            # builds from the catalog rather than guessing, so a finding against it is
                            # this system's own bug and rewriting it with a model would hide that.
                            error = "; ".join(f.message for f in blocking)
                            break
                        repairs += 1
                        fixed = self.existing.repair(sq, sql, "; ".join(f.message for f in blocking), thread)
                        if not fixed:
                            error = "; ".join(f.message for f in blocking)
                            break
                        sql = strip_trailing_semicolon(fixed)
                        continue
                    # The catalog is satisfied; now the database confirms the query parses and runs.
                    # The fan-out that inflates a SUM was judged above, before anything ran.
                    self.dry_run(self._physical(sql, self._asked_period(sq), **scope_args))
                    error = None
                    break
                except Exception as e:  # noqa: BLE001
                    error = str(e)[:1500]
                    if is_connection_error(e):
                        # The database went away. No rewrite of this SQL can help, and telling the user
                        # their question was invalid would send them looking in the wrong place.
                        log.error("data source unreachable q=%r err=%s", question[:80], error[:300])
                        _ds_msg = "Veri kaynağına şu an ulaşılamıyor; soruda bir sorun yok. Bağlantı geri geldiğinde aynı soru çalışacak."
                        qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=f"data source unreachable: {error}",
                                   answer_type="DATA_SOURCE_UNAVAILABLE", answer_summary=_ds_msg)
                        return {"id": uuid.uuid4().hex, "type": "DATA_SOURCE_UNAVAILABLE", "sql": sql,
                                "explanation": _ds_msg,
                                "threadId": thread_id, "repairs": repairs, "timings": timings, "semantic": semantic, "queryId": qid}
                    log.warning("dry_run failed (attempt %d) q=%r err=%s", attempt + 1, question[:80], error[:300])
                    if attempt == 2 or self.existing is None or compiled.compiler == "deterministic":
                        break
                    repairs += 1
                    fixed = self.existing.repair(sq, sql, error, thread)
                    if not fixed:
                        break
                    sql = strip_trailing_semicolon(fixed)
        if critic_notes:
            semantic["critic"] = critic_notes
        if error:
            # A query the reviewer stopped is a different thing from one the database rejected, and
            # the person is owed the difference: the first has an explanation they can act on, the
            # second is a fault. Both refuse — neither returns a number nobody can trust.
            blocked = any(n.get("severity") == "block" for n in critic_notes)
            # A reviewer's finding is written to be read by a person and points at something they can
            # act on, so it is shown as-is. A raw database error is a fault in the generated SQL, not
            # a fact about the question, and its provider text ("Invalid column name 'AMOUNT'", driver
            # codes, fragments of the statement) must never surface as the answer: the person is told,
            # honestly, that no trustworthy answer could be produced. The raw error stays in the log
            # and the gate for whoever operates the deployment.
            explanation = error if blocked else (
                "Bu soruya güvenilir bir cevap üretilemedi: üretilen sorgu veritabanında çalışmadı. "
                "Soru bir sorun içermiyorsa biraz daha belirginleştirmeyi ya da az sonra tekrar denemeyi deneyin.")
            qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=error,
                       answer_type="SQL_INVALID", answer_summary=explanation, gate={"critic": critic_notes} if critic_notes else None)
            return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": explanation, "threadId": thread_id, "repairs": repairs, "timings": timings, "semantic": semantic, "queryId": qid}
        # Repairs can remove filters or period predicates. Validate the exact final
        # statement, including previews; never trust the pre-repair verdict.
        final_problems = unmet_obligations(sq, sql, sources=self.router.gate_sources()) + audit_sql(sq, sql, conventions=self.conventions)
        semantic["query"] = sq.to_dict()
        if final_problems:
            reason = "Sorudaki koşulların tamamı doğrulanamadı: " + "; ".join(final_problems)
            # The refused statement is the evidence a refusal is judged by.
            log.warning("obligation unmet after repair q=%r %s sql=%s", question[:80], final_problems, " ".join(sql.split())[:1500])
            semantic["unmetObligations"] = final_problems
            qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                       resolved=sq.to_dict(), executed=False, error=reason,
                       answer_type="INCOMPLETE_ANSWER", answer_summary=reason, gate={"unmetObligations": list(final_problems)})
            return {"id": uuid.uuid4().hex, "type": "INCOMPLETE_ANSWER", "explanation": reason,
                    "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        if not execute or self.connector is None:
            qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False,
                       answer_type="TEXT_TO_SQL", answer_summary="(sorgu üretildi, çalıştırılmadı)")
            return {"id": uuid.uuid4().hex, "type": "TEXT_TO_SQL", "sql": sql, "physicalSql": self._physical(sql, self._asked_period(sq), **scope_args), "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid, "executed": False}
        t = time.perf_counter()
        try:
            # Executed once, whole. The client is shown a page of it; the export needs all of it, and
            # asking twice would be a second execution against data that can have moved.
            report("querying")
            result = self.run_complete(sql, self._asked_period(sq), **scope_args)
        except Exception as e:  # noqa: BLE001
            err = str(e)[:800]
            down = is_connection_error(e)
            slow = is_query_timeout(e)
            limit = getattr(self.connector, "query_timeout", "?")
            if down:
                log.error("data source unreachable during execution q=%r err=%s", question[:80], err[:300])
            elif slow:
                log.warning("query timeout (%ss) q=%r", limit, question[:80])
            _exec_msg = ("Veri kaynağına şu an ulaşılamıyor; soruda bir sorun yok. Bağlantı geri geldiğinde aynı soru çalışacak."
                         if down else
                         (f"Sorgu veritabanında {limit} saniyede bitmedi; soru doğru, veri büyük. Dönemi ya da kapsamı daraltın ya da yeniden deneyin."
                          if slow else f"Sorgu çalıştırılamadı: {err}"))
            _type = "DATA_SOURCE_UNAVAILABLE" if down else ("QUERY_TIMEOUT" if slow else "SQL_INVALID")
            qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False,
                       error=(f"data source unreachable: {err}" if down else (f"query timeout: {err}" if slow else err)),
                       answer_type=_type, answer_summary=_exec_msg)
            return {"id": uuid.uuid4().hex,
                    "type": _type, "sql": sql,
                    "explanation": _exec_msg,
                    "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        timings["run_sql_ms"] = int((time.perf_counter() - t) * 1000)
        report("presenting")
        from semantic_bridge.presentation import presentation_spec
        result["presentation"] = presentation_spec(sql, result, sq, compiled.compiler)
        result["dataCoverage"] = list(sq.data_coverage)
        result["comparison"] = sq.comparison
        self.attach_widget(result, question)
        self.remember_result(result, question=question, sql=sql)
        shown = list(result["records"])[: max(1, int(sample_size or 50))]
        t = time.perf_counter()
        summary = self.summarize(question, sql, result, sq)
        # What a ratio was measured against is part of the answer, not of the log: a share taken over
        # "contracts that have a party row" reads as a share of all contracts unless it is said.
        base_notes = [n["message"] for n in critic_notes if n.get("kind") == "RATIO_BASE" and n.get("severity") == "warn"]
        if base_notes:
            summary = (summary + " Not: " + " ".join(dict.fromkeys(base_notes))).strip()
        timings["summary_ms"] = int((time.perf_counter() - t) * 1000)
        fp = result.get("resultFingerprint") or result_fingerprint([c["name"] for c in result["columns"]], result["records"])
        # Kullanıcı kararı: tam sonuç (tüm satırlar) kaydın içinde durur, böylece incelerken neyin
        # döndüğünü birebir görürüz. Motorun satır tavanı zaten kesiyor; devasa kaçaklar _cap_result'la
        # düşürülür. Kapı kararları (eleştiri) da promtla birlikte saklanır.
        stored_result = {"columns": result["columns"], "records": list(result["records"]),
                         "totalRows": result["totalRows"], "truncated": result.get("truncated")}
        gate = {k: semantic[k] for k in ("critic", "unmetObligations", "catalogAudit") if k in semantic} or None
        if result.get("dataNotes"):
            gate = {**(gate or {}), "dataNotes": result["dataNotes"]}
        qid = _log(sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(),
                   executed=True, row_count=result["totalRows"], latency_ms=int((time.perf_counter() - t0) * 1000),
                   result_fingerprint=fp, answer_type="TEXT_TO_SQL", answer_summary=summary,
                   result_json=stored_result, gate=gate)
        self.thread_plans[thread_id] = sq
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
            # The rows this answer was computed from, carried with it. The client used to re-send the
            # SQL to /run_sql to fill its table, and that second execution went out without the
            # period: a question spanning years read one table instead of the union, so the summary
            # said one number and the table under it showed another. It also ran the query twice and
            # ran it for answers that had already been refused. One execution, one set of rows,
            # everything downstream — table, chart, export — reads these.
            "resultId": result["id"],
            "presentation": result.get("presentation"),
            "comparison": result.get("comparison"),
            "dataCoverage": result.get("dataCoverage", []), "dataNotes": result.get("dataNotes", []),
            "columns": result["columns"],
            "records": shown,
            "shownRows": len(shown),
            "truncated": result.get("truncated"),
            "cached": result.get("cached"),
            "ageSec": result.get("ageSec"),
            "computedAt": result.get("computedAt"),
            "dbMs": result.get("dbMs"),
            "widget": result.get("widget"),
            "threadId": thread_id,
            "rowCount": result["totalRows"],
            "totalRows": result["totalRows"],
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "repairs": repairs,
            "timings": timings,
            "recallExcluded": bool(exclude_nl),
            "semantic": semantic,
            "queryId": qid,
        }

    def _plan_rows(self, part, period, scope_args, timing=None):
        """One part of a two-server plan, read whole from the server its tables live on.

        `timing` verilirse parçanın veritabanında geçen süresi {name, source, ms} olarak eklenir."""
        from semantic_layer.runtime.federated import source_of_schema  # noqa: F401 (same rule as the plan)
        connector = self.crm_connector if (part.source and self.crm_connector is not None) else self.connector
        if connector is None:
            raise RuntimeError("no database connector")
        phys = self._physical(part.sql, period, **scope_args)
        if self._conn_for(phys) is not connector:
            raise ValueError(f"'{part.name}' parçası bildirdiği kaynağın dışında bir tablo okuyor")
        box = [0.0]
        try:
            with self._engine_lock:
                if hasattr(connector, "batches"):
                    yield from _timed(connector.batches(phys), box)
                else:
                    t0 = time.monotonic()
                    cols, rows, truncated = connector.execute(phys, self.result_files.max_rows)
                    box[0] += time.monotonic() - t0
                    if truncated:
                        raise ValueError(f"'{part.name}' parçası okunabilecek satır sınırını aştı; dönemi daraltın")
                    yield cols, rows
        finally:
            if timing is not None:
                timing.append({"name": part.name, "source": "crm" if connector is self.crm_connector else "logo",
                               "ms": int(round(box[0] * 1000))})

    def _answer_plan(self, question, sq, compiled, semantic, thread, thread_id, timings, t0,
                     sample_size, scope_args, report, execute):
        """A question that needs both databases: each part on its own server, combined in memory."""
        from semantic_layer.runtime import federated
        plan = compiled.plan
        text = compiled.sql
        semantic["plan"] = plan.to_dict()
        if not execute or self.connector is None:
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=text,
                                       compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                                       resolved=sq.to_dict(), executed=False)
            return {"id": uuid.uuid4().hex, "type": "TEXT_TO_SQL", "sql": text, "threadId": thread_id,
                    "timings": timings, "semantic": semantic, "queryId": qid, "executed": False}
        t = time.perf_counter()
        period = self._asked_period(sq)
        try:
            report("querying")
            parts_ms: list = []
            columns, rows = federated.execute(plan, lambda part: self._plan_rows(part, period, scope_args, parts_ms))
            out = self.result_files.write(iter([(columns, rows)]), self.settings.max_rows)
        except Exception as e:  # noqa: BLE001
            err = str(e)[:800]
            down = is_connection_error(e)
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=text,
                                       compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                                       resolved=sq.to_dict(), executed=False,
                                       error=(f"data source unreachable: {err}" if down else err))
            return {"id": uuid.uuid4().hex, "type": "DATA_SOURCE_UNAVAILABLE" if down else "SQL_INVALID",
                    "sql": text,
                    "explanation": ("Veri kaynağına şu an ulaşılamıyor; soruda bir sorun yok. Bağlantı geri geldiğinde aynı soru çalışacak."
                                    if down else f"İki sunuculu plan çalıştırılamadı: {err}"),
                    "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        timings["run_sql_ms"] = int((time.perf_counter() - t) * 1000)
        out.update(physicalSql=text, cached=False, dbMs=sum(p["ms"] for p in parts_ms), dbParts=parts_ms)
        result = self._served(out, time.time())
        report("presenting")
        from semantic_bridge.presentation import presentation_spec
        try:
            result["presentation"] = presentation_spec(plan.final, result, sq, compiled.compiler)
        except Exception:  # noqa: BLE001
            result["presentation"] = None
        result["dataCoverage"] = list(sq.data_coverage)
        result["comparison"] = sq.comparison
        self.attach_widget(result, question)
        self.remember_result(result, question=question, sql=text)
        shown = list(result["records"])[: max(1, int(sample_size or 50))]
        t = time.perf_counter()
        summary = self.summarize(question, text, result, sq)
        timings["summary_ms"] = int((time.perf_counter() - t) * 1000)
        fp = result.get("resultFingerprint") or result_fingerprint([c["name"] for c in result["columns"]], result["records"])
        qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=text,
                                   compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                                   resolved=sq.to_dict(), executed=True, row_count=result["totalRows"],
                                   latency_ms=int((time.perf_counter() - t0) * 1000), result_fingerprint=fp)
        self.thread_plans[thread_id] = sq
        thread.append({"role": "user", "content": question})
        thread.append({"role": "assistant", "content": f"```json\n{json.dumps(plan.to_dict(), ensure_ascii=False)}\n```"})
        del thread[:-12]
        log.info("ask ok compiler=%s plan parts=%d rows=%d timings=%s q=%r", compiled.compiler, len(plan.parts),
                 result["totalRows"], timings, question[:80])
        return {"id": result["id"], "type": "TEXT_TO_SQL", "sql": text, "physicalSql": text, "summary": summary,
                "resultId": result["id"], "presentation": result.get("presentation"),
                "comparison": result.get("comparison"), "dataCoverage": result.get("dataCoverage", []), "dataNotes": result.get("dataNotes", []),
                "columns": result["columns"], "records": shown, "shownRows": len(shown),
                "truncated": False, "cached": False, "ageSec": result.get("ageSec"),
                "computedAt": result.get("computedAt"), "widget": result.get("widget"),
                "dbMs": result.get("dbMs"), "dbParts": result.get("dbParts"),
                "threadId": thread_id, "rowCount": result["totalRows"], "totalRows": result["totalRows"],
                "latency_ms": int((time.perf_counter() - t0) * 1000), "repairs": 0, "timings": timings,
                "semantic": semantic, "queryId": qid, "federated": True}

    # ------------------------------------------------------------------ portal layer
    def inventory(self, *, search: str = "", entity: str = "", scope: str = "", limit: int = 0, offset: int = 0, with_columns: bool = True) -> dict[str, Any]:
        """The catalogue of what was discovered.

        The whole thing is eight megabytes across 837 tables and 27,000 columns, which is not something
        to hand a browser on every visit. A caller that wants the list asks without columns and gets a
        few kilobytes; a caller that opens one table asks for that table.

        The answer is remembered until the catalog itself changes. It is built from profiles that only
        move when the pipeline runs — nightly, or when someone runs it — so a timer would either
        refresh work that nothing changed or serve a stale page after a rebuild. Keying on the catalog
        fingerprint does neither: the first request after a rebuild pays, every one after it is free.
        """
        s = self.settings
        key = (self._catalog_version, search.lower(), entity.upper(), scope.upper(), limit, offset, with_columns)
        hit = self._inventory_cache.get(key)
        if hit is not None:
            return hit
        anns = self.store.list_annotations(s.datasource_id)
        suggested = {(x["tablePattern"], (x["column"] or "").upper() or None): x for x in self.store.list_suggestions(s.datasource_id)}
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
        wanted = [p for p in self.profiles
                  if (not entity or p.entity.upper() == entity.upper())
                  and (not scope or _table_scope(p.table_name)[0] == scope.upper())
                  and (not search or search.lower() in p.entity.lower() or search.lower() in p.table_name.lower()
                       or any(search.lower() in c.name.lower() for c in p.columns))]
        # Which scopes exist at all, counted before the page is cut — the screen needs the full list of
        # choices, not the ones that happen to fall on this page. A source with no scoping says nothing
        # here and the screen shows no filter.
        scopes: dict[str, int] = {}
        for prof in self.profiles:
            code = _table_scope(prof.table_name)[0]
            if code:
                scopes[code] = scopes.get(code, 0) + 1
        # Fullest first. A data dictionary is read to find where the business lives, and a schema of
        # hundreds of tables is mostly empty scaffolding; ordering by name buries the handful that
        # matter somewhere in the middle of the alphabet.
        wanted.sort(key=lambda p: (-(p.row_count or 0), p.entity))
        total = len(wanted)
        if limit:
            wanted = wanted[offset : offset + limit]
        tables = []
        undefined_cols = 0
        for p in wanted:
            cols = []
            for c in p.columns:
                cons = concepts_by_col.get((p.entity, c.name.upper()), [])
                col_anns = [{"id": a.id, "text": a.text, "author": a.author, "createdAt": a.created_at.isoformat()} for a in by_key.get((p.table_pattern, c.name.upper()), [])]
                defined = bool(c.description) or bool(col_anns) or any(x["status"] == ConceptStatus.CERTIFIED for x in cons)
                # what we worked out ourselves is knowledge, but it is not a definition: a column only
                # this system has an opinion about is still one nobody has explained
                if not defined:
                    undefined_cols += 1
                cols.append({
                    "name": c.name, "type": c.data_type, "nullable": c.nullable, "isPrimaryKey": c.is_primary_key,
                    "ref": f"{c.ref_entity}.{c.ref_column}" if c.ref_entity else None,
                    "sensitive": c.sensitive, "sensitivityReason": c.sensitivity_reason,
                    "sentinelValues": list(c.sentinel_values),
                    "distinct": c.distinct_count, "topValues": [] if c.sensitive else [[v, n] for v, n in c.top_values[:12]],
                    # three readings of one column, kept apart: what the source says, what we concluded
                    # from the data, and what a person typed in the portal
                    "description": c.description, "derived": list(c.derived), "unit": c.unit,
                    # what the system read on its own, kept apart from what anyone has confirmed
                    "suggestion": suggested.get((p.table_pattern, c.name.upper())),
                    "annotations": col_anns, "concepts": cons,
                    "status": "CERTIFIED" if any(x["status"] == ConceptStatus.CERTIFIED for x in cons) else ("CANDIDATE" if cons else ("DESCRIBED" if defined else "UNDEFINED")),
                })
            scope_code, scope_sub = _table_scope(p.table_name)
            tables.append({
                "entity": p.entity, "tableName": p.table_name, "tablePattern": p.table_pattern, "schema": p.schema_name,
                "scope": scope_code or None, "scopeSub": scope_sub or None,
                "context": label_context(p.context, s.pattern_labels),
                "description": p.description, "rowCount": p.row_count, "primaryKey": p.primary_key, "relationships": p.relationships,
                "annotations": [{"id": a.id, "text": a.text, "author": a.author, "createdAt": a.created_at.isoformat()} for a in by_key.get((p.table_pattern, None), [])],
                "columns": cols if with_columns else [],
                "columnCount": len(cols),
                "certifiedColumns": sum(1 for c in cols if c["status"] == "CERTIFIED"),
                "undefinedColumns": sum(1 for c in cols if c["status"] == "UNDEFINED"),
                "scannedAt": p.scanned_at.isoformat(),
            })
        out = {"datasourceId": s.datasource_id, "tables": tables, "tableCount": len(tables), "total": total,
               "scopes": [{"code": c, "tables": n} for c, n in sorted(scopes.items(), key=lambda kv: kv[0])],
               "columnCount": sum(t["columnCount"] for t in tables), "undefinedColumns": undefined_cols,
               "catalog": self.store.status_counts(s.tenant_id, s.datasource_id), "version": self.store.latest_version(s.tenant_id, s.datasource_id)}
        if len(self._inventory_cache) > 24:      # a handful of views, not an unbounded memory of them
            self._inventory_cache.clear()
        self._inventory_cache[key] = out
        return out

    def gaps(self) -> dict[str, Any]:
        """Açıklaması eksik tablo ve kolonlar, tablo kalıbına göre gruplu.

        Logo her yıl ve firma için aynı tabloyu yeniden açar (LG_211_01_STLINE, LG_411_01_STLINE…); açıklama da
        kalıba yazılır. Tablo tablo listelemek aynı eksiği yirmi kez gösterirdi. Kalıp başına bir satır: toplam
        satır, kaç kopya, kaç kolon eksik. Kolonlar ayrı uçtan, seçilince gelir.
        """
        inv = self.inventory(with_columns=True)
        cached = getattr(self, "_gaps_cache", None)
        if cached is not None and cached[0] is inv:
            return cached[1]
        groups: dict[str, list[dict[str, Any]]] = {}
        for t in inv["tables"]:
            groups.setdefault(t.get("tablePattern") or t["tableName"], []).append(t)
        items = []
        total_cols = undefined_cols = 0
        for pattern, tables in groups.items():
            tables.sort(key=lambda t: -(t.get("rowCount") or 0))
            rep = tables[0]
            cols = self._merged_columns(tables)
            missing = [c for c in cols if c["status"] == "UNDEFINED"]
            table_desc = rep.get("description") or ((rep.get("annotations") or [{}])[-1].get("text") if rep.get("annotations") else None)
            rows = sum(t.get("rowCount") or 0 for t in tables)
            total_cols += len(cols)
            undefined_cols += len(missing)
            items.append({
                "tablePattern": pattern, "example": rep["tableName"], "copies": len(tables),
                "source": data_source(rep.get("schema")),
                "description": table_desc, "tableMissing": not table_desc, "rows": rows,
                "columns": len(cols), "missing": len(missing),
                "suggestions": sum(1 for c in missing if c.get("suggestion")),
            })
        items.sort(key=lambda x: (x["rows"] == 0, -(x["missing"] + (1 if x["tableMissing"] else 0) > 0), -x["rows"], x["example"]))
        with_gaps = [x for x in items if x["missing"] or x["tableMissing"]]
        out = {
            "summary": {"patterns": len(items), "patternsWithGaps": len(with_gaps),
                        "tablesWithoutDescription": sum(1 for x in items if x["tableMissing"]),
                        "columns": total_cols, "missingColumns": undefined_cols,
                        "suggestions": sum(x["suggestions"] for x in items),
                        "bySource": {src: sum(1 for x in items if x["source"] == src) for src in (LOGO, CRM)}},
            "items": items,
        }
        self._gaps_cache = (inv, out)
        return out

    @staticmethod
    def _merged_columns(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Kalıbın kolonları: bir kopyada tanımlıysa tanımlı sayılır; örnek değerler en dolu kopyadan."""
        rank = {"CERTIFIED": 3, "CANDIDATE": 2, "DESCRIBED": 1, "UNDEFINED": 0}
        out: dict[str, dict[str, Any]] = {}
        for t in tables:
            for c in t.get("columns") or []:
                k = c["name"].upper()
                cur = out.get(k)
                if cur is None or rank.get(c["status"], 0) > rank.get(cur["status"], 0):
                    out[k] = c
                elif not cur.get("topValues") and c.get("topValues"):
                    out[k] = {**cur, "topValues": c["topValues"]}
        return list(out.values())

    def gap_detail(self, table_pattern: str) -> Optional[dict[str, Any]]:
        inv = self.inventory(with_columns=True)
        tables = [t for t in inv["tables"] if (t.get("tablePattern") or t["tableName"]) == table_pattern]
        if not tables:
            return None
        tables.sort(key=lambda t: -(t.get("rowCount") or 0))
        rep = tables[0]
        cols = self._merged_columns(tables)
        def view(c: dict[str, Any]) -> dict[str, Any]:
            said = (c.get("annotations") or [])
            return {"name": c["name"], "type": c.get("type"), "status": c["status"], "isPrimaryKey": c.get("isPrimaryKey"),
                    "ref": c.get("ref"), "sensitive": c.get("sensitive"), "distinct": c.get("distinct"),
                    "topValues": c.get("topValues") or [], "unit": c.get("unit"), "derived": c.get("derived") or [],
                    "description": said[-1]["text"] if said else c.get("description"),
                    "annotationId": said[-1]["id"] if said else None,
                    "suggestion": c.get("suggestion")}
        table_ann = rep.get("annotations") or []
        return {
            "tablePattern": table_pattern, "example": rep["tableName"], "source": data_source(rep.get("schema")),
            "tables": [{"name": t["tableName"], "rows": t.get("rowCount") or 0, "context": t.get("context")} for t in tables],
            "description": table_ann[-1]["text"] if table_ann else rep.get("description"),
            "tableAnnotationId": table_ann[-1]["id"] if table_ann else None,
            "rows": sum(t.get("rowCount") or 0 for t in tables),
            # Satır sayısı ve örnek değerler canlı sorgu değil, şema taramasında okundu; süresi ölçülmedi.
            "scannedAt": max((t.get("scannedAt") or "" for t in tables), default="") or None,
            "primaryKey": rep.get("primaryKey"),
            "missing": [view(c) for c in cols if c["status"] == "UNDEFINED"],
            "described": [view(c) for c in cols if c["status"] != "UNDEFINED"],
        }

    def add_annotation(self, table_pattern: str, column: Optional[str], text: str, author: str) -> dict[str, Any]:
        s = self.settings
        ann = self.store.add_annotation(Annotation(datasource_id=s.datasource_id, table_pattern=table_pattern, column=(column or None), text=text.strip(), author=author))
        gen = CandidateGenerator(self.store, s.tenant_id, s.datasource_id, self.profiles, self.conventions)
        ingested = gen.ingest_annotation(table_pattern, column, text, f"annotation:{ann.id}")
        self._inventory_cache.clear()      # what someone just wrote has to show on the very next read
        # The sentence they just wrote is the best description this field will ever have: the
        # everyday names come from it right away, not at the next timer tick.
        entity = next((p.entity for p in self.profiles if p.table_pattern == table_pattern), None)
        if entity:
            self.generate_vocabulary(entity, column)
        return {"annotation": {"id": ann.id, "tablePattern": table_pattern, "column": column, "text": ann.text, "author": author}, "candidates": ingested}

    def generate_vocabulary(self, entity: str, column: Optional[str] = None) -> bool:
        """Everyday names for one field, in the background; the request that asked for it returns
        at once. False when there is no model to ask."""
        if self.llm is None:
            return False
        from semantic_layer import vocabulary

        def run():
            try:
                only = [(entity, column)] if column is not None else [(entity, c.name) for p in self.profiles if p.entity == entity for c in p.columns] + [(entity, None)]
                out = vocabulary.maintain(self.store, self.settings, self.llm_for("vocabulary", NORMAL), self.profiles, max_targets=len(only) or 1, only=only)
                log.info("vocabulary generated for %s.%s: %s", entity, column or "*", out)
            except Exception as e:  # noqa: BLE001
                log.warning("vocabulary generation failed for %s.%s: %s", entity, column, e)
        # SQLite keeps one connection for the whole process; a second thread on it interleaves
        # its commits with the request's. Only Postgres gets the background thread.
        if self.store.engine.dialect.name == "sqlite":
            run()
        else:
            threading.Thread(target=run, name=f"vocab:{entity}.{column or '*'}", daemon=True).start()
        return True

    def certify(self, note: str = "") -> dict[str, Any]:
        s = self.settings
        gen = CandidateGenerator(self.store, s.tenant_id, s.datasource_id, self.profiles, self.conventions)
        gen.attach_profile_evidence()
        # Try to break the new candidates before weighing them. Everything upstream looks for reasons
        # to believe a term; without this step the only thing standing between a plausible-looking
        # mapping and the vocabulary is somebody noticing.
        try:
            from semantic_layer.evidence.refute import Refuter

            said = getattr(self.existing, "annotations", None) or {}
            broken = Refuter(self.store, s.tenant_id, s.datasource_id, self.profiles, said).run()
            if broken:
                log.info("çürütülen aday: %d (%s)", len(broken),
                         ", ".join(sorted({b["why"] for b in broken})))
        except Exception as e:  # noqa: BLE001
            log.warning("çürütme adımı çalışmadı, aday havuzu süzülmeden geçti: %s", e)
        rep = EvidenceEngine(self.store, min_support=s.min_support, threshold=s.certify_threshold).run(s.tenant_id, s.datasource_id, self.profiles, note=note)
        self.rebuild()
        return rep


# ---------------------------------------------------------------------- FastAPI

def _year_slot(year: int) -> TemporalSlot:
    from datetime import date

    return TemporalSlot(text="varsayılan", primitive="YEAR", start=date(year, 1, 1), end=date(year + 1, 1, 1),
                        grain="YEAR", params={"year": year, "default": True})


def _default_period():
    """Which period a question that names none is about.

    Nobody writing "geçen ay ciro" means a year they did not mention: they mean now. So the default is
    the year it currently is, read when the question is asked rather than when the service started —
    a process that has been up since December would otherwise answer January's questions against last
    year, and say nothing about having done so.

    SEMANTIC_DEFAULT_PERIOD=YEAR:<n> still pins a specific year for a deployment that wants one, and
    SEMANTIC_DEFAULT_PERIOD=NONE turns the fallback off so an undated question stays undated.
    """
    dp = os.environ.get("SEMANTIC_DEFAULT_PERIOD", "").strip()
    if dp.upper() in ("NONE", "OFF"):
        return None
    if dp.upper().startswith("YEAR:") and dp.split(":", 1)[1].strip().isdigit():
        return _year_slot(int(dp.split(":", 1)[1]))
    from datetime import date

    return lambda: _year_slot(date.today().year)


def _table_scope(table_name: str) -> tuple[str, str]:
    """The sub-database a physical table belongs to, and its subdivision within it.

    Sources that hold one set of tables per company, per fiscal year or per tenant encode that in the
    name — `LG_411_01_INVOICE` is company 411, period 01 — and a catalogue of such a source is mostly
    the same few hundred tables repeated. Without something to filter on, the screen shows one table
    twenty times over and the reader cannot tell which copy is the one they want.

    Nothing is guessed: a name that carries no such prefix returns nothing and is never filtered.
    """
    m = re.match(r"^[A-Z]+_(\d+)_(?:(\d+)_)?[A-Z][A-Z0-9_]*$", (table_name or "").upper())
    return (m.group(1), m.group(2) or "") if m else ("", "")


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
        llm = LlmClient(settings.llm_base, settings.llm_model, settings.llm_key, settings.llm_timeout,
                        extra=settings.llm_extra)
    return Runtime(settings, store=store, connector=connector, llm=llm)


def _lower_tr(text: str) -> str:
    """Turkish lowercase. `"İptal".lower()` gives "i̇ptal" — an i with a stray combining dot, which is
    what the review screen was printing at the start of every sentence."""
    return (text or "").replace("İ", "i").replace("I", "ı").lower()


def _head(meaning: str | None) -> str:
    """The column's name for itself, without its parenthetical code list.

    Splitting on the first "(" is not enough: Logo writes "(İndirim, masraf, promosyon satırları
    için) Hesaplama türü (1=Yüzde, 2=Miktar…)" and that leaves a dangling ")" mid-sentence."""
    t = (meaning or "").strip()
    out, depth = [], 0
    for ch in t:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split()).strip(" ,;-")


def _decode(meaning: str | None, value: str) -> str | None:
    """What the source itself calls this code.

    Logo writes its enumerations into the column description — "Fatura türü (1=Mal alım faturası,
    ..., 8=Toptan satış faturası)". A reviewer asked to approve `TRCODE IN (8)` has to know Logo's
    own manual to answer; asked to approve "faturanın türü Toptan satış faturası olanlar", they can
    answer from their own work. Nothing here is written by us: the labels come from the source.
    """
    if not meaning or value is None:
        return None
    for k, v in re.findall(r"(\w+)\s*=\s*([^,()]+)", meaning):
        if k.strip() == str(value).strip():
            return v.strip()
    return None


def _plain(term: str, kind: str, mapping: dict[str, Any] | None, meaning: str | None,
           table_said: str | None, readable=lambda f: f) -> str:
    """One sentence a person can agree or disagree with, without knowing the table.

    The row used to read «kanal» → CLCARD.SPECODE2. Nobody outside the data team can judge that, and
    a reviewer who cannot judge either approves everything or nothing. Both are worse than no queue.
    """
    if not mapping:
        return f"«{term}» bir şeye bağlanmamış."
    where = table_said or {"CLCARD": "cari kartı", "ITEMS": "malzeme kartı", "INVOICE": "fatura",
                           "STLINE": "fatura satırı"}.get(mapping.get("entity", ""), mapping.get("entity", ""))
    field = _head(meaning) or mapping.get("column") or ""
    if mapping.get("formula"):
        return f"«{term}» bir hesap: {readable(mapping['formula'])}"
    if mapping.get("operator") == "JOIN":
        return f"«{term}» iki tabloyu birbirine bağlar: {mapping.get('entity')}.{mapping.get('column')} → {', '.join(mapping.get('values') or [])}"
    vals = mapping.get("values") or []
    if vals:
        labels = [(_decode(meaning, v) or v) for v in vals]
        joined = " veya ".join(labels)
        # The operator is half the claim. `OUTCOST <> 0` and `OUTCOST = 0` select opposite halves of
        # the table, and a sentence that drops the operator asks a reviewer to approve the wrong one.
        op = (mapping.get("operator") or "IN").upper()
        tail = "olmayanlar" if op in ("<>", "!=", "NOT IN") else "olanlar"
        return f"«{term}» dendiğinde: {where} kayıtlarından, {_lower_tr(field) or 'alanı'} {joined} {tail}."
    return f"«{term}» dendiğinde {where}ndaki «{field}» alanı kastediliyor."


def _formula_reader(prof, said: dict) -> Any:
    """Read a metric back in the words the source uses for its own columns.

    `SUM(CASE WHEN INVOICE.TRCODE IN (2,3) THEN INVOICE.NETTOTAL ELSE 0 END)` is a correct answer to
    a question nobody asked. What a reviewer needs is which column and which codes, in the names Logo
    itself prints on them — then "iade tutarı" is either right or wrong, and they can say which.
    """
    def head(col: str) -> str:
        c = prof.column(col) if prof else None
        m = c.meaning(said.get((prof.entity, col.upper()))) if c and prof else None
        return _head(m) or col

    def one(f: str) -> str:
        out = f
        for ent, col in sorted(set(re.findall(r"\b(\w+)\.\"?(\w+)\"?", f)), key=lambda x: -len(x[1])):
            c = prof.column(col) if prof else None
            if c is None:
                continue
            label = head(col)
            meaning = c.meaning(said.get((prof.entity, col.upper()))) if prof else None
            def codes(mo, meaning=meaning):
                vals = [v.strip() for v in mo.group(2).split(",")]
                return mo.group(1) + ", ".join(_decode(meaning, v) or v for v in vals) + mo.group(3)
            out = re.sub(rf"({re.escape(ent)}\.\"?{col}\"?\s+IN\s*\()([^)]*)(\))", codes, out)
            out = re.sub(rf"({re.escape(ent)}\.\"?{col}\"?\s*=\s*)(\w+)()",
                         lambda mo, meaning=meaning: mo.group(1) + (_decode(meaning, mo.group(2)) or mo.group(2)), out)
            out = out.replace(f"{ent}.\"{col}\"", label).replace(f"{ent}.{col}", label)
        return out
    return one


# Where a line of SQL wants to break for a reader. A validated pair arrives as one long string; a
# reviewer asked "is this what «hizmet» means?" should not have to scan four hundred characters to
# find the one predicate that answers it.
# A join keeps its own adjective: breaking between INNER and JOIN puts a word alone on a line and
# makes the query look mangled, which costs the reader exactly the trust the panel is trying to earn.
_SQL_BREAK = re.compile(
    r"(?<!\bINNER)(?<!\bLEFT)(?<!\bRIGHT)(?<!\bFULL)(?<!\bCROSS)(?<!\bOUTER)"
    r"\s+(?=(?:SELECT|FROM|WHERE|AND|OR|GROUP\s+BY|ORDER\s+BY|HAVING|"
    r"(?:LEFT|RIGHT|INNER|FULL|CROSS)(?:\s+OUTER)?\s+JOIN|JOIN|UNION|WITH|ON)\b)", re.I)


def _sql_lines(sql: str, limit: int = 40, width: int = 320) -> list[str]:
    lines = [x.strip() for x in _SQL_BREAK.split(" ".join((sql or "").split())) if x.strip()]
    return [(x[:width] + " …") if len(x) > width else x for x in lines[:limit]]


def _pair_view(p: Any, needles: list[str]) -> dict[str, Any]:
    """One validated question→SQL pair as evidence: the question somebody actually asked, the SQL that
    answered it, and which of its lines carry the claim under review."""
    lines = _sql_lines(p.sql)
    low = [x.lower() for x in lines]
    hits = [i for i, x in enumerate(low) if any(n and n.lower() in x for n in needles)]
    return {"question": p.nl, "lines": lines, "hits": hits, "source": p.source, "at": p.created_at or None}


def _needles(m: dict[str, Any] | None) -> list[str]:
    """The words to look for in a query: the column this term claims, and the columns its formula reads."""
    if not m:
        return []
    out = [m["column"]] if m.get("column") else []
    out += re.findall(r"\b\w+\.\"?(\w+)\"?", m.get("formula") or "")
    return list(dict.fromkeys(x for x in out if x))


def _fragment(m: dict[str, Any], d: Dialect) -> str | None:
    """The SQL this term puts into a query once it is approved — nothing more, nothing prettier."""
    if m.get("formula"):
        return m["formula"]
    op = (m.get("operator") or "").upper()
    if op == "JOIN":
        return f"{m.get('entity')}.{m.get('column')} = {', '.join(m.get('values') or [])}"
    if m.get("column") and m.get("values"):
        return compiled_predicate(m["entity"], SLMapping("", m["entity"], m.get("table_pattern") or "",
                                                         column=m["column"], operator=m.get("operator"),
                                                         values=list(m.get("values") or [])), d)
    if m.get("column"):
        return f"{m['entity']}.{d.q(m['column'])}"
    return None


def _require_admin(request: Any) -> None:
    """Reading and asking sit behind the site's own authentication; changing the catalog needs proof.

    Two callers, two proofs. A server or CLI job (nightly scan, deploy, certify) presents the shared
    `x-semantic-admin` token. A person in the browser presents nothing extra — the browser carries no
    admin key — so they are known from the login service's AD session cookie, and pass when that
    account is one of the configured admins. Either proof is enough; without a token configured, the
    loopback binding is the only control and both pass. Before this, the approve/reject/add buttons on
    the Eş anlamlılar screen (all session-only) failed with 403 wherever the token was set."""
    token = os.environ.get("SEMANTIC_ADMIN_TOKEN", "")
    if not token:
        return                      # not configured: the loopback binding is the only control
    supplied = request.headers.get("x-semantic-admin", "") or request.query_params.get("admin_token", "")
    if secrets_compare(supplied, token):
        return                      # server/CLI: shared token
    if _session_is_admin(request):
        return                      # browser: AD-logged-in admin, identity from the session cookie
    raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "admin token required"})


def _session_is_admin(request: Any) -> bool:
    """True when the request carries a login-service session whose account is a configured admin.
    Any failure (no cookie, login service down, not an admin) is a plain False — never an exception,
    so a token caller is unaffected and a missing session falls through to the 403 above."""
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    try:
        user = board_mod.user_of(request.headers.get("cookie", ""))
    except Exception:  # noqa: BLE001
        return False
    return admin_mod.is_admin(user)


def _require_caller(request: Any) -> None:
    """Who may send this service SQL to run.

    This bridge has its own front door: it does not share the portal's session, so the main API's
    auth mode protects nothing here. `/api/v1/run_sql` takes SQL from the caller and runs it against
    the customer database, which makes an unauthenticated reachable bridge a read-anything console
    over everything the database login can see — the catalog check narrows which tables, not who is
    asking. Configure SEMANTIC_CALLER_TOKEN wherever the bridge is reachable by more than loopback.
    """
    token = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
    if not token:
        return                      # not configured: the loopback binding is the only control
    supplied = request.headers.get("x-semantic-caller", "") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not secrets_compare(supplied, token):
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "caller token required"})


def secrets_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(str(a or ""), str(b or ""))


def _review_vocabulary(r: "Runtime", said: dict) -> Any:
    """Kuyruktaki kök terimleri okunur yazmak için dağıtımın kendi kelimeleri. Katalog sürümü başına bir kez."""
    from semantic_bridge.labels import Vocabulary

    key = (getattr(r, "_catalog_version", None), id(r.profiles), len(r.profiles), hash(r.rules_text or ""),
           hash(tuple(sorted((str(k), str(v)) for k, v in said.items()))))
    cached = getattr(r, "_review_vocab", None)
    if cached and cached[0] == key:
        return cached[1]
    texts: list[Any] = [r.rules_text]
    for p in r.profiles:
        texts.append(p.description)
        for col in p.columns:
            texts.append(col.description)
            texts.append(said.get((p.entity, col.name.upper())))
    texts.extend(v for v in said.values() if isinstance(v, str))
    vocab = Vocabulary.from_texts(t for t in texts if isinstance(t, str))
    r._review_vocab = (key, vocab)
    return vocab


def _actor(request: Any) -> str:
    """Değişiklik kaydı için kişi: giriş servisinin oturumu, yoksa "portal"."""
    from semantic_bridge import board as board_mod

    try:
        return board_mod.user_of(request.headers.get("cookie", ""))
    except Exception:  # noqa: BLE001
        return "portal"


def _ask_user(request: Any) -> Optional[str]:
    """Promt izleyici için soruyu soran AD hesabı; oturum yoksa (sunucu/jeton çağrısı) None."""
    from semantic_bridge import board as board_mod

    try:
        return board_mod.user_of(request.headers.get("cookie", "")) or None
    except Exception:  # noqa: BLE001
        return None


def create_app(runtime: Optional[Runtime] = None) -> FastAPI:
    state: dict[str, Any] = {"rt": runtime}
    from semantic_bridge import admin as admin_mod

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if state["rt"] is None:
            state["rt"] = build_runtime()
        rt = state["rt"]
        log.info("semantic bridge ready: profiles=%d certified=%s llm=%s db=%s", len(rt.profiles), rt.store.status_counts(rt.settings.tenant_id, rt.settings.datasource_id).get("CERTIFIED"), bool(rt.llm), bool(rt.connector))
        rt.start_refresher()
        # Every request waiting for the model holds one of these threads while it waits. Forty (the
        # default) is forty waiting prompts and then /health queues behind them too.
        try:
            import anyio.to_thread

            anyio.to_thread.current_default_thread_limiter().total_tokens = int(os.environ.get("SEMANTIC_THREADPOOL", "200"))
        except Exception as e:  # noqa: BLE001
            log.warning("thread pool size left at its default: %s", e)
        if os.environ.get("SEMANTIC_LLM_JOBS", "1").strip() not in ("0", "false", "no", "off"):
            rt.jobs.start()
        try:
            yield
        finally:
            rt.jobs.stop()
            rt.stop_refresher()

    app = FastAPI(title="NanobaseAI Semantic Bridge", version=SEMANTIC_LAYER_VERSION, lifespan=lifespan)

    def rt() -> Runtime:
        if state["rt"] is None:
            state["rt"] = build_runtime()
        return state["rt"]

    @app.get("/health")
    def health() -> JSONResponse:
        r = rt()
        return JSONResponse({"status": "ok", "service": "nanobaseai-bi-semantic-bridge", "version": SEMANTIC_LAYER_VERSION, "profiles": len(r.profiles), "catalog": r.store.status_counts(r.settings.tenant_id, r.settings.datasource_id), "llm": bool(r.llm), "db": bool(r.connector), "pid": os.getpid(), "cache": r.cache_stats()})

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

    def _sql_failure(e: Exception) -> HTTPException:
        """Turn a failed statement into the right answer for the caller.

        Unreachable or overloaded source → 503 and a sentence the reader can act on: wait and retry.
        Anything else is a statement the source rejected, which is a 400 and worth showing verbatim.
        """
        if is_connection_error(e):
            return HTTPException(status_code=503, detail={
                "code": "DATA_SOURCE_UNAVAILABLE",
                "message": "Veri kaynağı şu anda yanıt vermiyor. Sorgu doğru; birazdan tekrar deneyin.",
                "detail": str(e)[:400],
                "retryable": True,
            })
        return HTTPException(status_code=400, detail={"code": type(e).__name__, "message": str(e)[:1200]})

    @app.post("/api/v1/run_sql")
    def run_sql_ep(body: RunSqlIn, request: Request) -> dict[str, Any]:
        _require_caller(request)
        r = rt()
        try:
            result = r.run_sql(body.sql, body.limit or r.settings.max_rows)
        except Exception as e:  # noqa: BLE001
            # A query that timed out or lost its connection is not a bad request. Reported as 400 it
            # reads to the user as "your question was wrong" and to the client as "do not retry" —
            # both false, and both send people looking for a fault that is not there.
            raise _sql_failure(e) from e
        r.attach_widget(result, body.question or "")
        return result

    @app.get("/api/v1/result/{result_id}")
    def stored_result(result_id: str, request: Request):
        """The whole result of one execution, for a client that showed a page of it.

        Not a re-run: if this execution is gone the caller is told so and asks its question again.
        Serving a fresh run of the same SQL under the same identity would hand back numbers the user
        never saw, computed at a different moment, with the same air of being "the same result".
        """
        _require_caller(request)
        runtime = rt()
        stream = None
        # Pin the open file while eviction is excluded. An open descriptor survives unlink.
        with runtime._results_lock:
            snap = runtime.stored_result(result_id, load_rows=False)
            if snap and snap.get('_result_file'):
                try:
                    stream = open(snap['_result_file'], 'rb')
                except FileNotFoundError:
                    snap = None
        if snap is None:
            raise HTTPException(status_code=410, detail={
                "code": "RESULT_GONE",
                "message": "Bu sonucun saklama süresi doldu. Aynı soruyu tekrar sorun — eski SQL sessizce yeniden çalıştırılmaz."})
        if snap.get('_result_file'):
            meta = {k: v for k, v in snap.items() if k not in ('_result_file', 'records', 'tenant_id', 'at')}
            meta.update(id=result_id, computedAt=snap.get('computedAt', snap['at']))
            def chunks():
                try:
                    yield (json.dumps(meta, ensure_ascii=False)[:-1] + ', "records":[').encode()
                    first = True
                    buffer = bytearray()
                    for line in stream:
                        if not first:
                            buffer.extend(b',')
                        buffer.extend(line.rstrip(b'\n'))
                        first = False
                        if len(buffer) >= 65536:
                            yield bytes(buffer)
                            buffer.clear()
                    buffer.extend(b']}')
                    yield bytes(buffer)
                finally:
                    stream.close()
            return StreamingResponse(chunks(), media_type='application/json')
        return {"id": result_id, "columns": snap["columns"], "records": snap["records"],
                "totalRows": snap["totalRows"], "truncated": snap["truncated"],
                "question": snap["question"], "sql": snap["sql"], "computedAt": snap.get("computedAt", snap["at"]),
                "dataCoverage": snap.get("dataCoverage", []), "comparison": snap.get("comparison")}

    @app.post("/api/v1/ask")
    def ask(body: AskIn, request: Request) -> dict[str, Any]:
        _require_caller(request)
        q = body.question.strip()
        if not q:
            raise HTTPException(status_code=422, detail={"code": "EMPTY_QUESTION", "message": "Soru boş."})
        try:
            return rt().ask(q, thread_id=body.threadId, sample_size=int(body.sampleSize or 50), exclude_nl=body.excludeNl, execute=bool(body.execute if body.execute is not None else True), username=_ask_user(request))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("ask failed")
            raise HTTPException(status_code=502, detail={"code": type(e).__name__, "message": str(e)[:800]}) from e

    @app.post("/api/v1/ask/stream")
    async def ask_stream(body: AskIn, request: Request):
        """One execution, actual lifecycle events, and its final result. Never replay on disconnect."""
        _require_caller(request)
        q = body.question.strip()
        if not q:
            raise HTTPException(status_code=422, detail={"code": "EMPTY_QUESTION", "message": "Soru boş."})
        async def events():
            queue = asyncio.Queue()
            loop = asyncio.get_running_loop()
            def progress(stage):
                loop.call_soon_threadsafe(queue.put_nowait, {"event": "stage", "stage": stage})
            asker = _ask_user(request)
            async def work():
                try:
                    answer = await run_in_threadpool(rt().ask, q, thread_id=body.threadId,
                        sample_size=int(body.sampleSize or 50), exclude_nl=body.excludeNl,
                        execute=bool(body.execute if body.execute is not None else True), progress=progress,
                        username=asker)
                    await queue.put({"event": "result", "result": answer})
                except Exception:
                    log.exception("stream ask failed")
                    await queue.put({"event": "error", "message": "Sorgu tamamlanamadı. Lütfen tekrar deneyin."})
            task = asyncio.create_task(work())
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield json.dumps({"event": "heartbeat"}) + "\n"
                        continue
                    yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
                    if event["event"] in ("result", "error"):
                        break
            finally:
                # Cancelling the await does not retry or start a second database execution.
                if not task.done():
                    task.cancel()
        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})

    @app.post("/api/v1/generate_summary")
    def generate_summary(body: dict[str, Any]) -> dict[str, Any]:
        r = rt()
        try:
            result = r.run_sql(str(body.get("sql") or ""), int(body.get("sampleSize") or 50))
        except Exception as e:  # noqa: BLE001
            raise _sql_failure(e) from e
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

    @app.get("/api/v1/semantic/gaps")
    def semantic_gaps(days: int = 30, limit: int = 50) -> dict[str, Any]:
        """What real users asked for that the catalog cannot place yet.

        The portal's annotation page reads this: each term here is a piece of the business nobody has
        written down, ranked by how often people ask for it, with the questions that were being asked.
        """
        r = rt()
        s = r.settings
        gaps = r.store.term_gaps(s.tenant_id, s.datasource_id, since_days=max(1, min(days, 365)), limit=max(1, min(limit, 200)))
        unmeasured = [p.entity for p in r.profiles if p.time_window is None]
        return {"ok": True, "days": days, "gaps": gaps, "unmeasuredWindows": unmeasured}

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
        return r.queue.status() | {"jobs": r.jobs.stats()}

    # ---------------------------------------------------------------- prompts left at the door
    def _job_for(job_id: str, request: Request) -> dict[str, Any]:
        """The job, if this caller may see it: whoever left it, an admin, or a service caller."""
        r = rt()
        found, owner = r.jobs.owner(job_id)
        user = _ask_user(request)
        if found and owner and user and owner != user and not admin_mod.is_admin(user):
            found = False
        view = r.jobs.get(job_id) if found else None
        if view is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "İş bulunamadı."})
        return view

    @app.post("/api/v1/llm/jobs", status_code=202)
    def llm_job_submit(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Leave a prompt, get an id. The connection closes now; the answer is asked for later
        (GET …/{id}, …/{id}?wait=25 or …/{id}/events). Nothing here waits for the model."""
        _require_caller(request)
        r = rt()
        if r.llm is None:
            raise HTTPException(status_code=503, detail={"code": "NO_MODEL", "message": "Model bağlı değil."})
        module = str(body.get("module") or "").strip()
        if not module:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "module: hangi modülün sorduğu gerekli."})
        try:
            return r.jobs.submit(body.get("messages"), module=module, priority=body.get("priority"), user_id=_ask_user(request),
                                 max_tokens=int(body.get("maxTokens") or 4096), temperature=float(body.get("temperature") or 0.0),
                                 dedup=bool(body.get("dedup", True)), cache_ttl_sec=int(body.get("cacheTtlSec") or 0))
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": str(e)}) from e

    @app.get("/api/v1/llm/jobs/{job_id}")
    async def llm_job_get(job_id: str, request: Request, wait: float = 0.0) -> dict[str, Any]:
        """`wait` (seconds, at most 300) holds the answer back until the job closes — one request
        instead of a polling loop, without holding a server thread while it waits."""
        _require_caller(request)
        view = await run_in_threadpool(_job_for, job_id, request)
        deadline = time.monotonic() + max(0.0, min(float(wait or 0.0), 300.0))
        pause = 0.25
        while view["status"] in ("QUEUED", "RUNNING") and time.monotonic() < deadline:
            await asyncio.sleep(min(pause, max(0.0, deadline - time.monotonic())))
            pause = min(pause * 1.5, 2.0)
            view = await run_in_threadpool(_job_for, job_id, request)
        return view

    @app.get("/api/v1/llm/jobs/{job_id}/events")
    async def llm_job_events(job_id: str, request: Request):
        """The job's life as it happens, one JSON object per line: every change of status or place in
        line, a heartbeat every 15 seconds, and the closed job last."""
        _require_caller(request)
        first = await run_in_threadpool(_job_for, job_id, request)

        async def events():
            view, seen, quiet, pause = first, None, 0.0, 0.5
            while True:
                mark = (view["status"], view["phase"], view["position"])
                if mark != seen:
                    seen, quiet, pause = mark, 0.0, 0.5
                    yield json.dumps({"event": "status", "job": view}, ensure_ascii=False, default=str) + "\n"
                    if view["status"] not in ("QUEUED", "RUNNING"):
                        return
                elif quiet >= 15:
                    quiet = 0.0
                    yield json.dumps({"event": "heartbeat"}) + "\n"
                await asyncio.sleep(pause)
                quiet += pause
                pause = min(pause * 1.5, 2.0)
                try:
                    view = await run_in_threadpool(_job_for, job_id, request)
                except HTTPException:
                    yield json.dumps({"event": "error", "message": "İş bulunamadı."}, ensure_ascii=False) + "\n"
                    return

        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})

    @app.delete("/api/v1/llm/jobs/{job_id}")
    def llm_job_cancel(job_id: str, request: Request) -> dict[str, Any]:
        _require_caller(request)
        _job_for(job_id, request)
        return rt().jobs.cancel(job_id) or {}

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
    def concepts(request: Request, status: str | None = None, type: str | None = None, q: str | None = None, limit: int = 500) -> dict[str, Any]:
        _admin_gate(request)
        r = rt()
        s = r.settings
        rows = r.store.search_concepts(s.tenant_id, s.datasource_id, q, limit) if q else r.store.find_concepts(s.tenant_id, s.datasource_id, status=status, semantic_type=type, limit=limit)
        src = source_by_entity(r.profiles)
        return {"items": [{"concept": c.to_dict(), "mappings": [{**m.to_dict(), "source": src.get(m.entity)} for m in r.store.list_mappings(c.id)]} for c in rows]}

    @app.post("/api/v1/semantic/concepts/{concept_id}/review")
    def review_concept(concept_id: str, request: Request, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """A person's yes or no on one proposed term.

        The evidence engine can propose and can measure, but there are terms only the business can
        settle: whether "iskonto" means this column and this code, whether a word is worth having at
        all. Those proposals sit as candidates until somebody looks, and on this deployment a hundred
        and ninety-five of them were sitting while questions were being refused for want of the very
        words they define.

        A yes is recorded as human evidence, not as a bare status change, so the next engine run can
        see who decided and does not undo it. A no is a rejection with the same standing: the term
        stops being proposed rather than coming back every night.
        """
        _require_admin(request)
        _admin_gate(request)
        r = rt()
        s = r.settings
        decision = str((body or {}).get("decision") or "").strip().upper()
        if decision not in ("APPROVE", "REJECT", "CORRECT"):
            raise HTTPException(status_code=400, detail={"code": "BAD_DECISION",
                                                         "message": "decision APPROVE, REJECT ya da CORRECT olmalı"})
        bundle = r.store.concept_bundle(concept_id)
        if not bundle:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        who = str((body or {}).get("by") or request.headers.get("X-User") or _actor(request))
        note = str((body or {}).get("note") or "")
        if decision != "CORRECT" or note.strip():
            admin_mod.audit(r.store.engine, who, {"APPROVE": "approve", "REJECT": "reject", "CORRECT": "correct"}[decision],
                            "term", concept_id, bundle["concept"].get("term"),
                            {k: v for k, v in {"note": note, "column": (body or {}).get("column")}.items() if v})
        eng = EvidenceEngine(r.store, min_support=r.settings.min_support, threshold=r.settings.certify_threshold)
        if decision == "APPROVE":
            # Two writes, and both matter. The evidence row is the audit trail — who said so, when,
            # in what words. The human_certify call is what makes the decision hold: the engine reads
            # `human_certified_by` when it re-scores, and a concept without that marker is re-judged
            # on its evidence every night and quietly demoted no matter who approved it.
            r.store.add_evidence(Evidence(concept_id, EvidenceType.HUMAN_ANNOTATION, f"portal:{who}",
                                          support_count=1, weight=1.0,
                                          payload={"snippet": note or "portalden onaylandı", "by": who}))
            eng.human_certify(concept_id, who, reason=note)
        elif decision == "CORRECT":
            # "Neither of your two buttons." A reviewer who can see the term is wrong usually knows
            # what is right, and that sentence is the most valuable thing this screen can collect —
            # more than the rejection. So a correction does three things: it retires the wrong
            # reading, it keeps the person's own words where the model reads them, and, when they
            # point at the right column, it certifies that instead. Anything less throws the
            # knowledge away and asks them again tomorrow.
            if not note.strip():
                raise HTTPException(status_code=400, detail={"code": "NOTE_REQUIRED",
                                                             "message": "düzeltme için açıklama gerekli"})
            bundle_maps = bundle.get("mappings") or []
            entity = str((body or {}).get("entity") or (bundle_maps[0].get("entity") if bundle_maps else ""))
            column = str((body or {}).get("column") or "").strip().upper()
            pattern = bundle_maps[0].get("table_pattern") if bundle_maps else ""
            prof = r.resolver.by_entity.get(entity)
            if column and (prof is None or prof.column(column) is None):
                raise HTTPException(status_code=400, detail={"code": "NO_SUCH_COLUMN",
                                                             "message": f"{entity} tablosunda {column} yok"})
            eng.human_reject(concept_id, who, reason=f"düzeltildi: {note}")
            said_of = column or None
            r.add_annotation(prof.table_pattern if prof else pattern, said_of, note, who)
            fixed = None
            if column:
                term = str((body or {}).get("term") or bundle["concept"]["term"])
                m = SLMapping("", entity, prof.table_pattern, column=column)
                c2, _ = r.store.upsert_concept(s.tenant_id, s.datasource_id, term,
                                               bundle["concept"]["semantic_type"], mapping=m,
                                               status=ConceptStatus.CANDIDATE)
                r.store.add_evidence(Evidence(c2.id, EvidenceType.HUMAN_ANNOTATION, f"portal:{who}",
                                              support_count=1, weight=1.0,
                                              payload={"snippet": note, "by": who, "corrects": concept_id}))
                eng.human_certify(c2.id, who, reason=note)
                fixed = c2.id
            return {"ok": True, "concept_id": concept_id, "status": decision, "corrected_to": fixed,
                    "certified": r.store.status_counts(s.tenant_id, s.datasource_id)}
        else:
            eng.human_reject(concept_id, who, reason=note)
        # No rebuild here on purpose: certifying moves the catalog fingerprint, and the runtime's own
        # version check reloads on the next question. Rebuilding per click would cost seconds each
        # time, and a reviewer works through a queue of them.
        return {"ok": True, "concept_id": concept_id, "status": decision,
                "certified": r.store.status_counts(r.settings.tenant_id, r.settings.datasource_id)}

    # A term nobody ever used and no query ever ran is not yet worth a person's minute. Logo's own
    # field labels alone produce hundreds of fragments — "islem gerceklestik ay" — and a queue made
    # mostly of those is a queue nobody works through. So the default queue is the terms that came
    # out of real use: a query that ran, a person's note, a binding someone wrote. ?source=all shows
    # the rest for anyone who wants to mine it.
    _USED = ("EXECUTION", "VALIDATED_SQL", "HUMAN_ANNOTATION", "ALIAS_BINDING", "EXPLICIT_BINDING")

    @app.get("/api/v1/semantic/vocabulary")
    def vocabulary_list(status: str = "PROPOSED", entity: str | None = None, limit: int = 5000) -> dict[str, Any]:
        """Everyday names waiting for a person: grouped by field, with the phrasings each would
        unlock and, for a dropped one, why the system did not dare propose it."""
        from semantic_layer import vocabulary
        r = rt()
        items = vocabulary.listing(r.store, r.settings, status=status.upper(), entity=entity, limit=limit)
        groups: dict[tuple, dict[str, Any]] = {}
        src = source_by_entity(r.profiles)
        for it in items:
            key = (it["entity"], it["column"])
            g = groups.setdefault(key, {"entity": it["entity"], "column": it["column"], "source": src.get(it["entity"]), "items": []})
            g["items"].append(it)
        return {"groups": list(groups.values()), "counts": vocabulary.counts(r.store, r.settings)}

    @app.get("/api/v1/semantic/vocabulary/gaps")
    def vocabulary_gaps(entity: str | None = None) -> dict[str, Any]:
        """Fields nothing can be generated for — no comment, no annotation — so a person can write
        the one sentence that unblocks them."""
        from semantic_layer import vocabulary
        r = rt()
        entities = [entity] if entity else None
        if entities is None:
            # by default the entities the certified catalog already reaches: those are the fields a
            # question can land on today, and a gap there costs an answer
            entities = sorted({m.entity for c in r.store.find_concepts(r.settings.tenant_id, r.settings.datasource_id, status=ConceptStatus.CERTIFIED, limit=100000)
                               for m in r.store.list_mappings(c.id)})
        src = source_by_entity(r.profiles)
        return {"items": [{**g, "source": src.get(g["entity"])} for g in vocabulary.gaps(r.store, r.settings, r.profiles, entities=entities)]}

    @app.post("/api/v1/semantic/vocabulary/{row_id}/decide")
    def vocabulary_decide(row_id: str, request: Request, body: dict[str, Any] | None = None) -> dict[str, Any]:
        from semantic_layer import vocabulary
        _require_admin(request)
        r = rt()
        who = str((body or {}).get("by") or request.headers.get("X-User") or _actor(request))
        decision = str((body or {}).get("decision") or "").strip().upper()
        try:
            eng = EvidenceEngine(r.store, min_support=r.settings.min_support, threshold=r.settings.certify_threshold)
            out = vocabulary.decide(r.store, r.settings, r.profiles, eng, row_id, decision, who, str((body or {}).get("note") or ""))
        except KeyError:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"code": "BAD_DECISION", "message": str(e)})
        admin_mod.audit(r.store.engine, who, "approve" if decision == "APPROVE" else "reject", "synonym", row_id, None, body)
        return out

    @app.post("/api/v1/semantic/vocabulary")
    def vocabulary_add(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """A person's own word for a field. Theirs from the first moment: approved, attached, and
        never touched by generation afterwards."""
        from semantic_layer import vocabulary
        _require_admin(request)
        r = rt()
        who = str(body.get("by") or request.headers.get("X-User") or _actor(request))
        entity, term = str(body.get("entity") or ""), str(body.get("term") or "")
        if not entity or not term.strip():
            raise HTTPException(status_code=422, detail={"code": "EMPTY", "message": "entity ve term gerekli"})
        eng = EvidenceEngine(r.store, min_support=r.settings.min_support, threshold=r.settings.certify_threshold)
        out = vocabulary.add_human(r.store, r.settings, r.profiles, eng, entity, body.get("column"), term, who, body.get("examples"))
        admin_mod.audit(r.store.engine, who, "create", "synonym", out["id"], term, {"entity": entity, "column": body.get("column")})
        return out

    @app.post("/api/v1/semantic/vocabulary/generate")
    def vocabulary_generate(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Ask now for one field (or a whole table) instead of waiting for the timer."""
        _require_admin(request)
        entity = str(body.get("entity") or "")
        if not entity:
            raise HTTPException(status_code=422, detail={"code": "EMPTY", "message": "entity gerekli"})
        started = rt().generate_vocabulary(entity, body.get("column"))
        return {"started": started}

    @app.get("/api/v1/semantic/review")
    def review_queue(request: Request, limit: int = 100, source: str = "used") -> dict[str, Any]:
        """What is waiting for a person to decide, the most supported first.

        Each row carries what the term would mean, where it points, and what stands behind it — the
        queries it was seen in, the documents that describe it, what the data shows. Without those a
        reviewer is being asked to approve a word, which nobody can do responsibly.
        """
        _admin_gate(request)
        r = rt()
        s = r.settings
        rows = r.store.review_rows(s.tenant_id, s.datasource_id, ConceptStatus.CANDIDATE, limit=2000)
        # Two kinds of proposal are not questions for a person, and both are recognisable from the
        # catalog rather than from a list somebody has to maintain:
        #
        #  - the deployment's own default filter. Every generated query carries `CANCELLED = 0`, so
        #    every word in every question gets seen next to it and proposed as its meaning. That is
        #    how "kartindaki" and "satisi" ended up in a queue meant for business terms.
        #  - a term that is simply a column's name. "trcode" is what the schema calls the field; a
        #    business vocabulary is the words people use *instead* of that.
        def target(m) -> tuple:
            # what a filter actually selects, regardless of how it was written: `= 0` and `IN (0)`
            # are the same restriction, and the queue must not treat them as two different claims.
            return (m.entity, (m.column or "").upper(), tuple(sorted(m.values or [])))
        defaults = {target(m) for c in r.store.find_concepts(
                        s.tenant_id, s.datasource_id, semantic_type=SemanticType.DEFAULT_FILTER, limit=200)
                    for m in r.store.list_mappings(c.id)}
        schema_words = {c.name.upper() for p in r.profiles for c in p.columns}
        # Two more that are not questions for a person:
        #
        #  - a mapping onto something that is not a table. A query's own CTE aliases (RANKED, FATURA,
        #    ISKONTO) get mined as if they were entities; nobody can rule on a name that exists only
        #    inside one SELECT, and approving it would certify a mapping that can never resolve.
        #  - a mapping onto a table with no rows. Whatever the term means, this deployment holds no
        #    evidence either way, so the reviewer would be guessing and the answer would change
        #    nothing today.
        empty = {p.entity for p in r.profiles if p.row_count == 0}
        def routine(x) -> bool:
            m = x["mapping"]
            if not m:
                return False
            if m.entity not in r.resolver.by_entity or m.entity in empty:
                return True
            return target(m) in defaults or x["concept"].term.upper() in schema_words
        rows = [x for x in rows if not routine(x)] if source != "all" else rows
        used = [x for x in rows if any(k in _USED for k in x["evidence"])]
        pool = rows if source == "all" else used
        pool.sort(key=lambda x: (-(x["concept"].confidence or 0), -x["evidenceCount"]))
        # The same word pointing at the same place is one decision, not three. Senses genuinely
        # differ by what they select, so that — not the concept id — is what makes a row distinct;
        # the strongest-supported copy is the one shown, and approving it settles the question.
        seen: set[tuple] = set()
        deduped = []
        for x in pool:
            m = x["mapping"]
            k = (x["concept"].term, x["concept"].semantic_type,
                 m.entity if m else None, (m.column or "").upper() if m else None,
                 tuple(sorted(m.values or [])) if m else (), (m.formula or "") if m else "")
            if k in seen:
                continue
            seen.add(k)
            deduped.append(x)
        pool = deduped
        said = getattr(r.existing, "annotations", None) or {}
        vocab = _review_vocabulary(r, said)

        # Aynı yere işaret eden, biri ötekinin kısaltması olan iki terim ("kanal payi yuz" ile
        # "kanal payi yuzd") iki karar değildir; uzun olan kalır, kısa olan ayrıca sorulmaz.
        def target_key(x) -> tuple:
            m = x["mapping"]
            return (x["concept"].semantic_type, m.entity if m else None, (m.column or "").upper() if m else None,
                    tuple(sorted(m.values or [])) if m else (), (m.formula or "") if m else "")
        by_target: dict[tuple, list] = {}
        for x in pool:
            by_target.setdefault(target_key(x), []).append(x)
        shadowed = set()
        for group in by_target.values():
            for a in group:
                for b in group:
                    ta, tb = a["concept"].term, b["concept"].term
                    if a is not b and len(ta) < len(tb) and tb.startswith(ta):
                        shadowed.add(id(a))
        pool = [x for x in pool if id(x) not in shadowed]
        out = []
        for x in pool[:limit]:
            c, m = x["concept"], x["mapping"]
            prof = r.resolver.by_entity.get(m.entity) if m else None
            col = prof.column(m.column) if prof and m and m.column else None
            meaning = col.meaning(said.get((m.entity, (m.column or "").upper()))) if col and m else None
            out.append({
                "id": c.id, "term": c.term, "label": vocab.readable(c.term), "type": c.semantic_type, "confidence": c.confidence,
                "source": data_source(prof.schema_name) if prof else None,
                "mapping": m.to_dict() if m else None,
                "evidence": x["evidence"], "evidenceCount": x["evidenceCount"],
                # what the data itself shows about the column this term claims
                "observed": [{"value": v, "rows": n, "label": _decode(meaning, v)}
                             for v, n in (col.top_values or [])[:6]] if col else [],
                "columnMeaning": meaning,
                "scannedAt": prof.scanned_at.isoformat() if prof is not None and getattr(prof, "scanned_at", None) else None,
                "plain": _plain(c.term, c.semantic_type, m.to_dict() if m else None, meaning,
                                said.get((m.entity, None)) if m else None,
                                readable=_formula_reader(prof, said)),
                "counterEvidence": x["counterEvidence"],
            })
        return {"waiting": len(pool), "used": len(used), "total": len(rows), "source": source, "items": out}

    @app.get("/api/v1/semantic/concepts/{concept_id}")
    def concept(concept_id: str) -> dict[str, Any]:
        b = rt().store.concept_bundle(concept_id)
        if not b:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        return b

    # Which part of the system proposed a term, said the way a reviewer would say it. The name of the
    # module means nothing to them; how the sentence was arrived at means everything.
    _PRODUCER = {
        "history_miner": "çalışmış sorgular tarandı",
        "doc_miner": "kaynağın kendi açıklaması okundu",
        "profiler": "verinin kendisi ölçüldü",
        "qwen": "model önerdi",
        "human": "bir kişi yazdı",
    }

    @app.get("/api/v1/semantic/concepts/{concept_id}/provenance")
    def provenance(concept_id: str, examples: int = 3) -> dict[str, Any]:
        """Everything behind one pending term, in a form the person deciding can actually check.

        The queue row says what the term would mean; it does not say why the system believes that, and
        a reviewer cannot responsibly approve a claim whose grounds are a chip reading "doğrulanmış
        sorgu ×2". This returns the grounds themselves: the questions the term was seen in with the SQL
        that answered them, the sentence in the source documentation, the counts measured in the
        column, the note somebody left — and, separately, the exact SQL fragment approving it will put
        into future queries. Everything here already existed; none of it was reachable from the screen.
        """
        r = rt()
        b = r.store.concept_bundle(concept_id)
        if not b:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        c, maps = b["concept"], b.get("mappings") or []
        m = maps[0] if maps else None
        prof = r.resolver.by_entity.get(m["entity"]) if m else None
        said = getattr(r.existing, "annotations", None) or {}
        col = prof.column(m["column"]) if prof and m and m.get("column") else None
        meaning = col.meaning(said.get((m["entity"], (m.get("column") or "").upper()))) if col and m else None
        d = Dialect(r.settings.dialect or "")

        target = None
        if m:
            target = {
                "entity": m.get("entity"), "table": m.get("table_pattern"),
                # the pattern is what the catalog holds; the reviewer recognises the real table name.
                "tableExample": prof.table_name if prof else None,
                "tableRows": prof.row_count if prof else None,
                "column": m.get("column"), "operator": m.get("operator"), "values": m.get("values") or [],
                "formula": m.get("formula"), "columnType": col.data_type if col else None,
                "columnMeaning": meaning,
                # what the source itself says about this column, kept apart from what we concluded.
                "columnDoc": col.description if col else None,
                "derived": [dict(x) for x in (col.derived or [])] if col else [],
                "sql": _fragment(m, d),
                "readable": _formula_reader(prof, said)(m["formula"]) if m.get("formula") else None,
            }

        # Pair ids in the evidence resolve against the same two sources the miner read: the knowledge
        # pack and the validated query log. Ids are matched on content as well, because a pair that was
        # re-exported keeps its text but not its row id — and an unresolvable id must be reported as a
        # gap, not quietly dropped, or the screen would claim less evidence than the decision used.
        index: dict[str, Any] = {}
        for p in list(r.pairs) + load_query_log(r.store.list_validated_queries(
                r.settings.tenant_id, r.settings.datasource_id, limit=500)):
            index.setdefault(p.id, p)
            index.setdefault(pair_id(p.nl, p.sql), p)
        needles = _needles(m)

        # A payload carries whatever the miner that wrote it had to say; these are the keys that mean
        # something to a person, in the order a person reads them.
        _KEEP = ("snippet", "rationale", "confidence", "precision", "raw_precision", "recall",
                 "term_total", "aliases", "fit", "counts", "distinct", "value", "rows", "share",
                 "ratio", "ref", "by", "missing", "expected", "found")
        ev = []
        for e in b.get("evidence") or []:
            pl = e.get("payload") or {}
            ids = [str(x) for x in (pl.get("pairs") or [])]
            found = [index[i] for i in ids if i in index]
            ev.append({
                "kind": e["evidence_type"], "source": e["source_id"],
                "support": e.get("support_count"), "weight": e.get("weight"), "at": e.get("created_at"),
                "seenIn": len(ids), "missing": len(ids) - len(found),
                "examples": [_pair_view(x, needles) for x in found[:max(0, examples)]],
                "detail": {k: pl[k] for k in _KEEP if k in pl},
            })
        # Strongest first, and a query somebody ran outranks a sentence a model wrote about it.
        rank = {"EXECUTION": 0, "VALIDATED_SQL": 1, "EXPLICIT_BINDING": 2, "ALIAS_BINDING": 3,
                "HUMAN_ANNOTATION": 4, "DOC": 5, "PROFILE": 6, "LLM_CANDIDATE": 7}
        ev.sort(key=lambda x: (rank.get(x["kind"], 9), -(x["support"] or 0)))

        conflicts = [{"type": x.get("conflict_type"), "severity": x.get("severity"),
                      "source": x.get("source_id"), "at": x.get("created_at"),
                      "detail": {k: v for k, v in (x.get("payload") or {}).items() if k != "support"}}
                     for x in (b.get("counterEvidence") or [])]
        # The nightly run re-proposes what it proposed yesterday, so a term mined for two weeks carries
        # fourteen identical candidate rows. A reviewer needs to know how it was found, once, and when
        # it was last found — not the run history.
        produced, seen_by = [], set()
        for x in (b.get("candidates") or []):
            k = (x.get("generated_by"), x.get("model_version"))
            if k in seen_by:
                continue
            seen_by.add(k)
            produced.append({"by": x.get("generated_by"), "how": _PRODUCER.get(str(x.get("generated_by")), ""),
                             "model": x.get("model_version"), "at": x.get("created_at"),
                             "detail": {kk: vv for kk, vv in (x.get("payload") or {}).items() if kk != "pairs"}})

        return {"id": concept_id, "term": c.get("term"), "type": c.get("semantic_type"),
                "status": c.get("status"), "confidence": c.get("confidence"),
                "plain": _plain(c.get("term", ""), c.get("semantic_type", ""), m, meaning,
                                said.get((m["entity"], None)) if m else None,
                                readable=_formula_reader(prof, said)),
                "target": target, "evidence": ev, "conflicts": conflicts, "producedBy": produced}

    # --- portal layer: schema inventory + annotations
    @app.get("/api/v1/schema/inventory")
    def inventory(q: str = "", entity: str = "", scope: str = "", limit: int = 0, offset: int = 0, columns: bool = True) -> dict[str, Any]:
        """The catalogue, with a second attempt and an honest banner when it cannot be produced.

        A page that comes back empty and says nothing reads as "this database has nothing in it",
        which is a different and much worse statement than "I could not read the catalogue just now".
        A failure is retried once against a freshly loaded catalog, and if it still cannot be built the
        answer carries a warning for the screen to show rather than an empty list that looks like fact.
        """
        r = rt()
        last = ""
        for attempt in (1, 2):
            try:
                out = r.inventory(search=q, entity=entity, scope=scope, limit=max(0, limit), offset=max(0, offset), with_columns=columns)
                if out["tables"] or out.get("total"):
                    return out
                last = "katalog boş döndü"
            except Exception as e:  # noqa: BLE001
                last = str(e)[:200]
                log.warning("inventory attempt %d failed: %s", attempt, last)
            if attempt == 1:
                r.rebuild()          # the catalog may have moved under a stale set of profiles
        empty = {"datasourceId": r.settings.datasource_id, "tables": [], "tableCount": 0, "total": 0,
                 "scopes": [], "columnCount": 0, "undefinedColumns": 0, "catalog": {}, "version": None}
        if q or entity or scope:
            empty["warning"] = "Bu aramaya uyan tablo bulunamadı."
        else:
            empty["warning"] = (f"Katalog şu an okunamıyor ({last}). Gece taraması henüz çalışmamış olabilir; "
                                "birkaç dakika sonra tekrar deneyin, sürerse yöneticinize bildirin.")
        log.error("inventory could not be produced: %s", last)
        return empty

    @app.post("/api/v1/schema/annotations")
    def add_annotation(request: Request, body: AnnotationIn) -> dict[str, Any]:
        _require_admin(request)
        if not body.text.strip():
            raise HTTPException(status_code=422, detail={"code": "EMPTY_TEXT"})
        out = rt().add_annotation(body.tablePattern, body.column, body.text, body.author or "cockpit")
        admin_mod.audit(rt().store.engine, _actor(request), "create", "annotation", out.get("id"),
                        f"{body.tablePattern}.{body.column or ''}".rstrip("."), {"text": body.text})
        return out

    @app.put("/api/v1/schema/annotations/{annotation_id}")
    def update_annotation(request: Request, annotation_id: str, body: AnnotationIn) -> dict[str, Any]:
        """Correct what someone wrote earlier.

        A correction is a new statement, not an edit of the old one: the previous text is retired and
        kept, so the record still shows what was believed before and who changed it. Only the newest
        reaches the model, which is what makes fixing a wrong label actually fix the answers.
        """
        _require_admin(request)
        if not body.text.strip():
            raise HTTPException(status_code=422, detail={"code": "EMPTY_TEXT"})
        r = rt()
        r.store.retire_annotation(annotation_id)
        out = r.add_annotation(body.tablePattern, body.column, body.text, body.author or "cockpit")
        out["replaced"] = annotation_id
        admin_mod.audit(r.store.engine, _actor(request), "update", "annotation", annotation_id,
                        f"{body.tablePattern}.{body.column or ''}".rstrip("."), {"text": body.text})
        return out

    @app.post("/api/v1/schema/suggestions/{suggestion_id}/accept")
    def accept_suggestion(request: Request, suggestion_id: str, author: str = "kokpit") -> dict[str, Any]:
        """Accepting is what turns a reading into a definition — and it is a person's act, recorded as
        theirs. The suggestion itself never had the standing to certify anything."""
        _require_admin(request)
        r = rt()
        sug = r.store.close_suggestion(suggestion_id, "ACCEPTED")
        if sug is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        out = r.add_annotation(sug["tablePattern"], sug["column"], sug["text"], author)
        out["accepted"] = suggestion_id
        return out

    @app.post("/api/v1/schema/suggestions/{suggestion_id}/dismiss")
    def dismiss_suggestion(request: Request, suggestion_id: str) -> dict[str, Any]:
        _require_admin(request)
        r = rt()
        if r.store.close_suggestion(suggestion_id, "DISMISSED") is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        r._inventory_cache.clear()
        return {"ok": True, "dismissed": suggestion_id}

    @app.get("/api/v1/schema/annotations")
    def list_annotations(tablePattern: str | None = None) -> dict[str, Any]:
        r = rt()
        return {"items": [{"id": a.id, "tablePattern": a.table_pattern, "column": a.column, "text": a.text, "author": a.author, "createdAt": a.created_at.isoformat()} for a in r.store.list_annotations(r.settings.datasource_id, tablePattern)]}

    @app.delete("/api/v1/schema/annotations/{annotation_id}")
    def retire_annotation(request: Request, annotation_id: str) -> dict[str, Any]:
        _require_admin(request)
        ok = rt().store.retire_annotation(annotation_id)
        if ok:
            admin_mod.audit(rt().store.engine, _actor(request), "delete", "annotation", annotation_id, None)
        return {"ok": ok}

    # ------------------------------------------------------------------ eksik açıklamalar (veri sözlüğü)
    # Okumak herkese açık; yazmak AD oturumlu yöneticiye. Tarayıcı yönetici anahtarı taşımaz, kişi oturumdan bilinir.

    def _describer(request: Request) -> str:
        _require_caller(request)
        user = _board_user(request)
        admin_mod.ensure(rt().store.engine)
        if not admin_mod.is_admin(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Açıklama yazmak yöneticilere açık."})
        return user

    @app.get("/api/v1/schema/gaps")
    def schema_gaps(request: Request) -> dict[str, Any]:
        _admin_gate(request)
        return rt().gaps()

    @app.get("/api/v1/schema/gaps/detail")
    def schema_gap_detail(request: Request, tablePattern: str) -> dict[str, Any]:
        _admin_gate(request)
        out = rt().gap_detail(tablePattern)
        if out is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Tablo bulunamadı."})
        return out

    @app.post("/api/v1/schema/gaps/describe")
    def schema_gap_describe(request: Request, body: AnnotationIn) -> dict[str, Any]:
        user = _describer(request)
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail={"code": "EMPTY_TEXT", "message": "Açıklama boş olamaz."})
        r = rt()
        existing = [a for a in r.store.list_annotations(r.settings.datasource_id, body.tablePattern)
                    if (a.column or "").upper() == (body.column or "").upper()]
        for a in existing:
            r.store.retire_annotation(a.id)
        out = r.add_annotation(body.tablePattern, body.column, text, user)
        admin_mod.audit(r.store.engine, user, "update" if existing else "create", "annotation", out["annotation"]["id"],
                        f"{body.tablePattern}.{body.column or ''}".rstrip("."), {"text": text})
        return out

    @app.post("/api/v1/schema/gaps/suggestions/{suggestion_id}/accept")
    def schema_gap_accept(request: Request, suggestion_id: str) -> dict[str, Any]:
        user = _describer(request)
        r = rt()
        sug = r.store.close_suggestion(suggestion_id, "ACCEPTED")
        if sug is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Öneri bulunamadı."})
        out = r.add_annotation(sug["tablePattern"], sug["column"], sug["text"], user)
        admin_mod.audit(r.store.engine, user, "create", "annotation", out["annotation"]["id"],
                        f"{sug['tablePattern']}.{sug['column'] or ''}".rstrip("."), {"text": sug["text"], "suggestion": suggestion_id})
        return out

    @app.post("/api/v1/schema/gaps/suggestions/{suggestion_id}/dismiss")
    def schema_gap_dismiss(request: Request, suggestion_id: str) -> dict[str, Any]:
        user = _describer(request)
        r = rt()
        sug = r.store.close_suggestion(suggestion_id, "DISMISSED")
        if sug is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Öneri bulunamadı."})
        r._inventory_cache.clear()
        admin_mod.audit(r.store.engine, user, "delete", "annotation", suggestion_id,
                        f"{sug['tablePattern']}.{sug['column'] or ''}".rstrip("."), {"dismissed": sug["text"]})
        return {"ok": True}

    # ------------------------------------------------------------------ uyarılar
    # Kural bir sorudur; kontrol burada yapılır, zamanlayıcı yalnız /check'i çağırır.
    from semantic_bridge import alerts as alerts_mod

    def _alerts() -> tuple[Runtime, Any, str, str]:
        r = rt()
        alerts_mod.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r, r.store.engine, r.settings.tenant_id, r.settings.datasource_id

    def _alert_runner(r: Runtime):
        def run(rule: dict[str, Any]) -> dict[str, Any]:
            if (rule.get("question") or "").strip():
                return r.ask(rule["question"], thread_id=None, sample_size=5, execute=True)
            return r.run_sql(rule["sql"], 5)
        return run

    def _alert_check(r: Runtime, engine: Any, tenant: str, ds: str, only: Optional[str] = None) -> dict[str, Any]:
        return alerts_mod.check(engine, tenant, ds, _alert_runner(r),
                                alerts_mod.email_notifier(admin_mod.conf("ALERT_LINK")), only=only)

    def _alert_fail(e: Exception) -> HTTPException:
        return HTTPException(status_code=422, detail={"code": "INVALID_ALERT", "message": str(e)})

    def _alert_owner(request: Request) -> str:
        # Uyarı kişiye aittir; oturum yoksa (giriş servisi çerezi çözemedi) 401.
        return _board_user(request)

    @app.get("/api/v1/alerts")
    def alerts_list(request: Request) -> dict[str, Any]:
        _require_caller(request)
        user = _alert_owner(request)
        _, engine, tenant, ds = _alerts()
        return {"user": user, "alerts": alerts_mod.list_rules(engine, tenant, ds, user), "email": alerts_mod.email_status()}

    @app.post("/api/v1/alerts")
    def alerts_create(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _require_caller(request)
        user = _alert_owner(request)
        r, engine, tenant, ds = _alerts()
        try:
            rule = alerts_mod.create_rule(engine, tenant, ds, body, by=user)
        except alerts_mod.AlertError as e:
            raise _alert_fail(e) from None
        admin_mod.audit(engine, user, "create", "alert", rule["id"], rule["title"],
                        {"question": rule["question"], "condition": rule["condition"], "threshold": rule["threshold"],
                         "recipients": rule["recipients"]})
        # Kurulur kurulmaz ölçülür ama istek beklemez: yavaş bir cevap tarayıcıyı zaman aşımına düşürüp
        # kişiye aynı kuralı ikinci kez kaydettirmesin. Ekran listeyi birkaç saniye sonra yeniden okur.
        if os.environ.get("ALERT_MEASURE_ON_CREATE", "background") == "sync":
            _alert_check(r, engine, tenant, ds, only=rule["id"])
            return alerts_mod.get_rule(engine, tenant, ds, rule["id"]) or rule
        threading.Thread(target=_alert_check, args=(r, engine, tenant, ds, rule["id"]), daemon=True).start()
        return rule

    def _alert_patch(request: Request, rule_id: str, body: dict[str, Any], owner: Optional[str], actor: str) -> dict[str, Any]:
        _, engine, tenant, ds = _alerts()
        before = alerts_mod.get_rule(engine, tenant, ds, rule_id, owner)
        if before is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Kural bulunamadı."})
        try:
            rule = alerts_mod.update_rule(engine, tenant, ds, rule_id, body, owner)
        except alerts_mod.AlertError as e:
            raise _alert_fail(e) from None
        if rule is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Kural bulunamadı."})
        diff = admin_mod.changes(before, rule, ["title", "question", "condition", "threshold", "recipients", "status"])
        if diff:
            admin_mod.audit(engine, actor, "update", "alert", rule_id, rule["title"], diff)
        return rule

    def _alert_remove(rule_id: str, owner: Optional[str], actor: str) -> dict[str, Any]:
        _, engine, tenant, ds = _alerts()
        before = alerts_mod.get_rule(engine, tenant, ds, rule_id, owner)
        if before is None or not alerts_mod.delete_rule(engine, tenant, ds, rule_id, owner):
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Kural bulunamadı."})
        admin_mod.audit(engine, actor, "delete", "alert", rule_id, before.get("title"),
                        {"question": before.get("question"), "owner": before.get("created_by")})
        return {"ok": True}

    @app.patch("/api/v1/alerts/{rule_id}")
    def alerts_update(rule_id: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _require_caller(request)
        user = _alert_owner(request)
        return _alert_patch(request, rule_id, body, user, user)

    @app.delete("/api/v1/alerts/{rule_id}")
    def alerts_delete(rule_id: str, request: Request) -> dict[str, Any]:
        _require_caller(request)
        user = _alert_owner(request)
        return _alert_remove(rule_id, user, user)

    @app.post("/api/v1/alerts/check")
    def alerts_check(request: Request, id: Optional[str] = None) -> dict[str, Any]:
        """Ekrandan: yalnız kişinin kuralları. Zamanlayıcıdan (çerez yok, yalnız çağıran jetonu): hepsi."""
        _require_caller(request)
        owner: Optional[str] = None
        if request.headers.get("cookie"):
            owner = _alert_owner(request)
        r, engine, tenant, ds = _alerts()
        if id and owner is not None and alerts_mod.get_rule(engine, tenant, ds, id, owner) is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Kural bulunamadı."})
        return alerts_mod.check(engine, tenant, ds, _alert_runner(r),
                                alerts_mod.email_notifier(admin_mod.conf("ALERT_LINK")), only=id, owner=owner)

    @app.get("/api/v1/alerts/{rule_id}/events")
    def alerts_events(rule_id: str, request: Request, limit: int = 50) -> dict[str, Any]:
        _require_caller(request)
        user = _alert_owner(request)
        _, engine, tenant, ds = _alerts()
        ev = alerts_mod.events(engine, tenant, ds, rule_id, limit, owner=user)
        if ev is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Kural bulunamadı."})
        return {"events": ev}

    # ------------------------------------------------------------------ pano
    # Kartlar ve son sonuçları burada durur; kimlik giriş servisinden çerezle çözülür.
    from semantic_bridge import board as board_mod

    def _board() -> tuple[Runtime, Any, str, str]:
        r = rt()
        board_mod.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r, r.store.engine, r.settings.tenant_id, r.settings.datasource_id

    def _board_user(request: Request) -> str:
        try:
            return board_mod.user_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None

    def _admin_gate(request: Request) -> str:
        """Yönetim, Veri Sözlüğü ve Onaylar ekranları yalnız yöneticilere açık: portal oturumundaki
        AD hesabı yönetici listesinde ya da yönetici AD grubunda olmalı. Diğer roller 403 alır."""
        _require_caller(request)
        user = _board_user(request)
        admin_mod.ensure(rt().store.engine)
        if not admin_mod.is_admin(user):
            raise HTTPException(status_code=403,
                                detail={"code": "FORBIDDEN", "message": "Bu ekran yalnız yöneticiler içindir."})
        return user

    def _board_runner(r: Runtime):
        return lambda sql: r.run_sql(sql, r.settings.max_rows)

    @app.get("/api/v1/board")
    def board_get(request: Request) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        _, engine, tenant, ds = _board()
        return {"user": user, "cards": board_mod.list_cards(engine, tenant, ds, user)}

    @app.put("/api/v1/board")
    def board_put(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        _, engine, tenant, ds = _board()
        before = {c["id"]: c for c in board_mod.list_cards(engine, tenant, ds, user)}
        try:
            cards = board_mod.save_cards(engine, tenant, ds, user, list(body.get("cards") or []))
        except board_mod.BoardError as e:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BOARD", "message": str(e)}) from e
        # Konum/boyut her sürüklemede kaydedilir; kayda yalnız ekleme, silme ve anlamlı değişiklik girer.
        after = {c["id"]: c for c in cards}
        for cid, c in after.items():
            if cid not in before:
                admin_mod.audit(engine, user, "create", "board", cid, c["title"], {"question": c["question"], "chart": c["chart"]})
            else:
                diff = admin_mod.changes(before[cid], c, ["title", "note", "question", "chart", "refresh", "refreshAt"])
                if diff:
                    admin_mod.audit(engine, user, "update", "board", cid, c["title"], diff)
        for cid, c in before.items():
            if cid not in after:
                admin_mod.audit(engine, user, "delete", "board", cid, c["title"], {"question": c["question"]})
        return {"user": user, "cards": cards}

    @app.post("/api/v1/board/cards/{card_id}/run")
    def board_run(card_id: str, request: Request) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        r, engine, tenant, ds = _board()
        try:
            out = board_mod.run_card(engine, tenant, ds, user, card_id, _board_runner(r))
        except Exception as e:  # noqa: BLE001
            raise _sql_failure(e) from e
        if out is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Kart bulunamadı."})
        return out

    @app.get("/api/v1/board/export.xlsx")
    def board_export(request: Request, ids: str = ""):
        """Kartlar tek Excel kitabında: özet + kart başına sayfa. SQL burada tam koşar, tavan yok."""
        from datetime import datetime
        from fastapi.responses import Response as FileBytes
        from semantic_bridge import board_excel

        _require_caller(request)
        user = _board_user(request)
        r, engine, tenant, ds = _board()
        cards = board_mod.list_cards(engine, tenant, ds, user)
        wanted = [i for i in ids.split(",") if i]
        if wanted:
            order = {cid: k for k, cid in enumerate(wanted)}
            cards = sorted((c for c in cards if c["id"] in order), key=lambda c: order[c["id"]])
        if not cards:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Aktarılacak kart yok."})

        def fetch(sql: str):
            out = r.run_complete(sql)
            path = out.get("_result_file")
            rows = r.result_files.read(path) if path else list(out.get("records") or [])
            return list(out.get("columns") or []), rows

        data = board_excel.build(cards, fetch, user=user, now=datetime.now(board_mod._LOCAL).replace(tzinfo=None))
        name = "pano" if len(cards) > 1 else re.sub(r"[^A-Za-z0-9]+", "-", cards[0]["title"].translate(str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU"))).strip("-").lower()[:60] or "kart"
        admin_mod.audit(engine, user, "export", "board", ",".join(c["id"] for c in cards)[:200], name, {"cards": len(cards), "format": "xlsx"})
        return FileBytes(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}-{datetime.now().strftime("%Y-%m-%d")}.xlsx"'},
        )

    @app.post("/api/v1/board/run-due")
    def board_run_due(request: Request) -> dict[str, Any]:
        _require_caller(request)
        r, engine, tenant, ds = _board()
        return board_mod.run_due(engine, tenant, ds, _board_runner(r))

    # ------------------------------------------------------------------ planlı raporlar
    # Plan bir sorudur; dosya sunucuda üretilir, SMTP varsa gönderilir, yoksa ekrandan indirilir.
    from fastapi.responses import FileResponse
    from semantic_bridge import reports as reports_mod

    def _reports() -> tuple[Runtime, Any, str, str]:
        r = rt()
        reports_mod.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r, r.store.engine, r.settings.tenant_id, r.settings.datasource_id

    def _report_asker(r: Runtime):
        # Soru her çalışmada yeniden çözülür ("bu ay" o günü anlatsın); veri ayrıca tam çekilir.
        return lambda q: r.ask(q, thread_id=None, sample_size=1, execute=False)

    def _report_fetcher(r: Runtime):
        def fetch(sql: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
            out = r.run_complete(sql)
            path = out.get("_result_file")
            rows = r.result_files.read(path) if path else list(out.get("records") or [])
            return list(out.get("columns") or []), rows, db_timing(out)
        return fetch

    _REPORT_FIELDS = ["title", "question", "when", "recipients", "fmt", "status", "columns"]

    def _report_fail(e: Exception) -> HTTPException:
        return HTTPException(status_code=422, detail={"code": "INVALID_REPORT", "message": str(e)})

    @app.get("/api/v1/reports")
    def reports_list(request: Request) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        _, engine, tenant, ds = _reports()
        return {"user": user, "reports": reports_mod.list_reports(engine, tenant, ds, user), "email": alerts_mod.email_status()}

    @app.post("/api/v1/reports/parse")
    def reports_parse(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Cümleyi plana çevirir ve veri sorusunu motora sorup önizleme döndürür; kaydetmez."""
        _require_caller(request)
        _board_user(request)
        r, _, _, _ = _reports()
        draft = reports_mod.parse_prompt(str(body.get("text") or ""))
        draft.update(_report_preview(r, draft["question"], []))
        return draft

    def _report_preview(r: Runtime, question: str, spec: list[dict[str, Any]]) -> dict[str, Any]:
        """Soruyu motora sorar; ilk PREVIEW_ROWS satırı ve kolon düzenini döndürür. Dosyaya tamamı yazılır."""
        try:
            a = r.ask(question, thread_id=None, sample_size=reports_mod.PREVIEW_ROWS, execute=True)
        except Exception as e:  # noqa: BLE001
            raise _sql_failure(e) from e
        source = list(a.get("columns") or [])
        layout, added, dropped = reports_mod.merge_columns(spec, source)
        return {"question": question, "sql": a.get("sql") or "", "columns": source,
                "records": list(a.get("records") or [])[: reports_mod.PREVIEW_ROWS],
                "rowCount": a.get("rowCount"), "summary": a.get("summary") or a.get("explanation") or "",
                "layout": layout, "added": added, "dropped": dropped, **db_timing(a)}

    @app.post("/api/v1/reports/preview")
    def reports_preview(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Elle değiştirilen soru için önizlemeyi yeniler; kişinin kolon düzeni kaynak adı aynı kalan kolonlarda korunur."""
        _require_caller(request)
        _board_user(request)
        r, _, _, _ = _reports()
        question = " ".join(str(body.get("question") or "").split())
        if not question:
            raise _report_fail(reports_mod.ReportError("Raporun neyi listeleyeceği yazılmalı."))
        try:
            spec = reports_mod.clean_columns(body.get("columns") or [])
        except reports_mod.ReportError as e:
            raise _report_fail(e) from e
        return _report_preview(r, question, spec)

    @app.post("/api/v1/reports/refine")
    def reports_refine(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Önizlemede düzeltme: cümle kolon düzenini ya da veri sorusunu değiştirir; kaydetmez.

        Yalnız kolon değiştiyse veri yeniden çekilmez. Soru değiştiyse motora yeniden sorulur ve kişinin
        kurduğu adlar/gizlemeler kaynak adı aynı kalan kolonlarda korunur.
        """
        _require_caller(request)
        _board_user(request)
        r, _, _, _ = _reports()
        question = " ".join(str(body.get("question") or "").split())
        if not question:
            raise _report_fail(reports_mod.ReportError("Önce bir veri sorusu gerekiyor."))
        try:
            plan = reports_mod.refine_plan(r.llm_for("reports"), question, body.get("columns") or [], str(body.get("instruction") or ""))
        except reports_mod.ReportError as e:
            raise _report_fail(e) from e
        except Exception as e:  # noqa: BLE001
            log.warning("reports refine: model hatası: %s", e)
            raise HTTPException(status_code=503, detail={"code": "MODEL_UNAVAILABLE", "retryable": True,
                                "message": "Model şu an yanıt vermedi. Kolonları tablodan düzenleyebilir ya da birazdan yeniden deneyebilirsiniz."}) from e
        out: dict[str, Any] = {"changes": plan["changes"], "via": plan["via"], "requery": plan["requery"]}
        if plan["requery"]:
            out.update(_report_preview(r, plan["question"], plan["columns"]))
        else:
            out.update(question=question, layout=plan["columns"], added=[], dropped=[])
        return out

    @app.post("/api/v1/reports")
    def reports_create(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        _, engine, tenant, ds = _reports()
        try:
            rep = reports_mod.create_report(engine, tenant, ds, user, body)
        except reports_mod.ReportError as e:
            raise _report_fail(e) from e
        admin_mod.audit(engine, user, "create", "report", rep["id"], rep["title"],
                        {"question": rep["question"], "when": rep["when"], "recipients": rep["recipients"], "fmt": rep["fmt"],
                         "columns": rep["columns"]})
        return rep

    @app.patch("/api/v1/reports/{rid}")
    def reports_update(rid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        _, engine, tenant, ds = _reports()
        before = reports_mod.get_report(engine, tenant, ds, user, rid) or {}
        try:
            out = reports_mod.update_report(engine, tenant, ds, user, rid, body)
        except reports_mod.ReportError as e:
            raise _report_fail(e) from e
        if out is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Rapor bulunamadı."})
        diff = admin_mod.changes(before, out, _REPORT_FIELDS)
        if diff:
            admin_mod.audit(engine, user, "update", "report", rid, out["title"], diff)
        return out

    @app.delete("/api/v1/reports/{rid}")
    def reports_delete(rid: str, request: Request) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        _, engine, tenant, ds = _reports()
        before = reports_mod.get_report(engine, tenant, ds, user, rid)
        if not reports_mod.delete_report(engine, tenant, ds, user, rid):
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Rapor bulunamadı."})
        admin_mod.audit(engine, user, "delete", "report", rid, (before or {}).get("title"),
                        {"question": (before or {}).get("question"), "when": (before or {}).get("when")})
        return {"ok": True}

    @app.post("/api/v1/reports/{rid}/run")
    def reports_run(rid: str, request: Request) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        r, engine, tenant, ds = _reports()
        if reports_mod.get_report(engine, tenant, ds, user, rid) is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Rapor bulunamadı."})
        out = reports_mod.run_report(engine, rid, _report_asker(r), _report_fetcher(r), manual=True,
                                     link=admin_mod.conf("ALERT_LINK"))
        admin_mod.audit(engine, user, "run", "report", rid, out.get("title"),
                        {"status": out.get("lastStatus"), "rows": out.get("lastRows"), "error": out.get("lastError")})
        return out

    @app.get("/api/v1/reports/{rid}/file")
    def reports_file(rid: str, request: Request):
        _require_caller(request)
        user = _board_user(request)
        _, engine, tenant, ds = _reports()
        found = reports_mod.file_of(engine, tenant, ds, user, rid)
        if not found:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Henüz üretilmiş dosya yok."})
        path, ctype = found
        return FileResponse(str(path), media_type=ctype, filename=path.name)

    @app.post("/api/v1/reports/run-due")
    def reports_run_due(request: Request) -> dict[str, Any]:
        _require_caller(request)
        r, engine, tenant, ds = _reports()
        return reports_mod.run_due(engine, tenant, ds, _report_asker(r), _report_fetcher(r),
                                   link=admin_mod.conf("ALERT_LINK"))

    # ------------------------------------------------------------------ kişi tercihleri
    # Kişinin ekran düzeni gibi kendi alanları: AD hesabına bağlı, sunucuda. Tarayıcı yalnız önbellek tutar.
    from semantic_bridge import prefs as prefs_mod

    def _prefs(request: Request) -> tuple[Any, str, str, str]:
        _require_caller(request)
        user = _board_user(request)
        r = rt()
        prefs_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, r.settings.datasource_id, user

    @app.get("/api/v1/me/prefs/{key}")
    def prefs_get(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, ds, user = _prefs(request)
        try:
            return {"user": user, "key": key, **prefs_mod.get(engine, tenant, ds, user, key)}
        except prefs_mod.PrefError as e:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PREF", "message": str(e)}) from e

    @app.put("/api/v1/me/prefs/{key}")
    def prefs_put(key: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, ds, user = _prefs(request)
        try:
            return {"user": user, "key": key, **prefs_mod.put(engine, tenant, ds, user, key, body.get("value"))}
        except prefs_mod.PrefError as e:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PREF", "message": str(e)}) from e

    @app.delete("/api/v1/me/prefs/{key}")
    def prefs_delete(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, ds, user = _prefs(request)
        try:
            return {"ok": prefs_mod.delete(engine, tenant, ds, user, key)}
        except prefs_mod.PrefError as e:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PREF", "message": str(e)}) from e

    # ------------------------------------------------------------------ toplantı odaları
    # Ortak kaynak: rezervasyonu herkes görür, kimin yaptığı oturumdan gelir. Odaları yönetici tanımlar.
    from semantic_bridge import rooms as rooms_mod

    def _rooms(request: Request) -> tuple[Any, str, str, str, bool]:
        _require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        rooms_mod.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display, admin_mod.is_admin(user)

    def _room_error(e: "rooms_mod.RoomError") -> HTTPException:
        detail: dict[str, Any] = {"code": type(e).__name__.upper(), "message": str(e)}
        if isinstance(e, rooms_mod.Conflict):
            detail["booking"] = e.booking
        return HTTPException(status_code=e.status, detail=detail)

    @app.get("/api/v1/rooms")
    def rooms_day(request: Request, date: str = "") -> dict[str, Any]:
        engine, tenant, user, display, is_admin = _rooms(request)
        day = date or rooms_mod.today()
        try:
            view = rooms_mod.day_view(engine, tenant, day, user, is_admin)
        except rooms_mod.RoomError as e:
            raise _room_error(e) from e
        return {**view, "me": {"username": user, "displayName": display, "admin": is_admin}}

    @app.get("/api/v1/rooms/now")
    def rooms_now(request: Request) -> dict[str, Any]:
        engine, tenant, user, display, is_admin = _rooms(request)
        return {**rooms_mod.now_view(engine, tenant, user), "me": {"username": user, "displayName": display, "admin": is_admin}}

    @app.post("/api/v1/rooms/{room_id}/bookings", status_code=201)
    def rooms_book(room_id: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, display, _ = _rooms(request)
        try:
            b = rooms_mod.book(engine, tenant, room_id, user, display, body)
        except rooms_mod.RoomError as e:
            raise _room_error(e) from e
        admin_mod.audit(engine, user, "create", "booking", b["id"],
                        f"{b['roomName']} · {b['date']} {b['startLocal']}–{b['endLocal']}", {"title": b["title"]})
        return b

    @app.delete("/api/v1/rooms/bookings/{booking_id}")
    def rooms_cancel(booking_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _, is_admin = _rooms(request)
        try:
            b = rooms_mod.cancel(engine, tenant, booking_id, user, is_admin)
        except rooms_mod.RoomError as e:
            raise _room_error(e) from e
        admin_mod.audit(engine, user, "delete", "booking", b["id"],
                        f"{b['date']} {b['startLocal']}–{b['endLocal']} · {b['displayName']}", {"roomId": b["roomId"]})
        return {"ok": True, "booking": b}

    @app.post("/api/v1/admin/rooms", status_code=201)
    def rooms_add(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _, is_admin = _rooms(request)
        if not is_admin:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Oda eklemek yönetici yetkisi ister."})
        try:
            room = rooms_mod.add_room(engine, tenant, user, body)
        except rooms_mod.RoomError as e:
            raise _room_error(e) from e
        admin_mod.audit(engine, user, "create", "room", room["id"], room["name"], room)
        return room

    @app.delete("/api/v1/admin/rooms/{room_id}")
    def rooms_remove(room_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _, is_admin = _rooms(request)
        if not is_admin:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Oda kaldırmak yönetici yetkisi ister."})
        try:
            room = rooms_mod.remove_room(engine, tenant, user, room_id)
        except rooms_mod.RoomError as e:
            raise _room_error(e) from e
        admin_mod.audit(engine, user, "delete", "room", room["id"], room["name"], {"cancelledBookings": room["cancelledBookings"]})
        return room

    # ------------------------------------------------------------------ kampüs kutlamaları
    # "Kutla" kutlanan kişinin ekranına bildirim düşer. Kutlayan ve alan oturumdan gelir.
    from semantic_bridge import greetings as greetings_mod

    def _greetings(request: Request) -> tuple[Any, str, str, str]:
        _require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        greetings_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    @app.get("/api/v1/greetings")
    def greetings_state(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = _greetings(request)
        return {"sent": greetings_mod.sent_today(engine, tenant, user),
                "inbox": greetings_mod.inbox(engine, tenant, user, display),
                # Kampüs zili ve alkış duvarı: görülmüş olsa da son 30 günün kayıtları.
                "received": greetings_mod.received(engine, tenant, user, display),
                "wall": greetings_mod.wall(engine, tenant)}

    @app.post("/api/v1/greetings", status_code=201)
    def greetings_send(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, display = _greetings(request)
        try:
            return greetings_mod.send(engine, tenant, user, display, body)
        except greetings_mod.GreetingError as e:
            raise HTTPException(status_code=e.status, detail={"code": "INVALID_GREETING", "message": str(e)}) from e

    @app.post("/api/v1/greetings/seen")
    def greetings_seen(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, display = _greetings(request)
        ids = body.get("ids") if isinstance(body.get("ids"), list) else []
        return {"marked": greetings_mod.mark_seen(engine, tenant, user, display, ids)}

    # ------------------------------------------------------------------ kişi rehberi ve profil
    # Rehber CRM'den gelir (yalnız gerçek, etkin kullanıcılar). Kişinin eklediği dahili/kat/fotoğraf sunucuda.
    from semantic_bridge import people as people_mod

    people_dir = people_mod.Directory()

    def _people(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = _greetings(request)
        people_mod.ensure(engine)
        admin_mod.ensure(engine)
        return engine, tenant, user, display

    def _crm_people(fresh: bool = False) -> tuple[list[dict[str, Any]], float, bool]:
        r = rt()
        truncated = False

        def run(sql: str) -> dict[str, Any]:
            nonlocal truncated
            out = r.run_sql(sql, r.settings.max_rows)
            truncated = bool(out.get("truncated"))
            return out

        try:
            rows, at = people_dir.rows(
                admin_mod.conf("CRM_SCHEMA"), run, fresh=fresh,
                ad=lambda: people_mod.ad_people({k: admin_mod.conf(k) for k in admin_mod.store_keys("ad")}),
                max_idle_days=_int_conf("PEOPLE_MAX_IDLE_DAYS", 365))
        except people_mod.ProfileError as e:
            raise HTTPException(status_code=503, detail={"code": "CRM_NOT_CONFIGURED", "message": str(e)}) from e
        except Exception as e:  # noqa: BLE001
            log.warning("people: CRM okunamadı: %s", e)
            raise HTTPException(status_code=503, detail={"code": "CRM_UNAVAILABLE",
                                                         "message": "CRM'e şu an ulaşılamıyor; rehber okunamadı."}) from e
        return rows, at, truncated

    def _int_conf(key: str, default: int) -> int:
        try:
            return max(0, int(admin_mod.conf(key) or default))
        except ValueError:
            return default

    def _profile_error(e: "people_mod.ProfileError") -> HTTPException:
        return HTTPException(status_code=e.status, detail={"code": "INVALID_PROFILE", "message": str(e)})

    @app.get("/api/v1/people")
    def people_list(request: Request, fresh: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = _people(request)
        asked = time.time()
        rows, at, truncated = _crm_people(fresh)
        items = people_mod.people(engine, tenant, rows)
        return {"items": items, "total": len(items), "truncated": truncated, "source": "crm",
                "adChecked": people_dir.ad_checked, "db": people_dir.timing(from_memory=at < asked),
                "at": datetime.fromtimestamp(at, timezone.utc).isoformat()}

    @app.get("/api/v1/me/profile")
    def profile_get(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = _people(request)
        asked = time.time()
        db = None
        try:
            rows, at, _ = _crm_people()
            db = people_dir.timing(from_memory=at < asked)
        except HTTPException:
            rows = []          # CRM kapalıyken kişi kendi alanlarını yine görür ve düzenler
        out = people_mod.me(engine, tenant, user, display, rows)
        out["db"] = db
        return out

    @app.put("/api/v1/me/profile")
    def profile_put(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, display = _people(request)
        before = people_mod.me(engine, tenant, user, display, [])["fields"]
        try:
            fields = people_mod.save_fields(engine, tenant, user, body)
        except people_mod.ProfileError as e:
            raise _profile_error(e) from e
        admin_mod.audit(engine, user, "update", "profile", user, display,
                        {k: {"önce": before.get(k, ""), "sonra": v} for k, v in fields.items() if before.get(k, "") != v})
        return profile_get(request)

    @app.put("/api/v1/me/profile/photo")
    def profile_photo_put(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, display = _people(request)
        try:
            version = people_mod.save_photo(engine, tenant, user, str(body.get("dataUrl") or ""))
        except people_mod.ProfileError as e:
            raise _profile_error(e) from e
        admin_mod.audit(engine, user, "update", "profile", user, f"{display} · fotoğraf", {"photoVersion": version})
        return {"photoVersion": version}

    @app.delete("/api/v1/me/profile/photo")
    def profile_photo_delete(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = _people(request)
        people_mod.delete_photo(engine, tenant, user)
        admin_mod.audit(engine, user, "delete", "profile", user, f"{display} · fotoğraf", {})
        return {"ok": True}

    @app.get("/api/v1/people/{username}/photo")
    def people_photo(username: str, request: Request) -> Response:
        engine, tenant, _, _ = _people(request)
        found = people_mod.photo(engine, tenant, username)
        if not found:
            raise HTTPException(status_code=404, detail={"code": "NO_PHOTO", "message": "Fotoğraf yok."})
        blob, mime = found
        # Adres sürüm numarasını (?v=) taşır; sürüm değişince yeni adres, bu yüzden uzun önbellek güvenli.
        return Response(content=blob, media_type=mime,
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})

    # ------------------------------------------------------------------ yönetim
    # Ayarlar, herkesin tanımları ve değişiklik kaydı. Yetki: oturumdaki AD hesabı yönetici listesinde olmalı.

    def _admin(request: Request) -> tuple[Runtime, Any, str, str, str]:
        _require_caller(request)
        user = _board_user(request)
        r = rt()
        admin_mod.ensure(r.store.engine)
        if not admin_mod.is_admin(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bu ekran yalnız yöneticiler içindir."})
        return r, r.store.engine, r.settings.tenant_id, r.settings.datasource_id, user

    def _admin_fail(e: Exception) -> HTTPException:
        return HTTPException(status_code=422, detail={"code": "INVALID", "message": str(e)})

    def _apply_settings(r: Runtime, changed: list[str]) -> dict[str, Any]:
        """Kaydedilen bağlantı ayarını çalışan servise uygular: yönetici ayarı değiştirip
        birinin servisi yeniden başlatmasını beklemesin. Yeni bağlantı denenmeden takılmaz —
        kurulamazsa eski bağlantı yerinde kalır ve neden kurulamadığı geri döner."""
        keys = set(changed)
        s, applied, error = r.settings, [], None
        if keys & set(admin_mod.LLM_KEYS):
            s.llm_base = admin_mod.conf("OPENAI_API_BASE").rstrip("/")
            s.llm_model = admin_mod.conf("LLM_MODEL_NAME")
            s.llm_key = admin_mod.conf("OPENAI_API_KEY")
            try:
                s.llm_timeout = float(admin_mod.conf("LLM_TIMEOUT_SEC") or 240)
            except ValueError:
                pass
            client = LlmClient(s.llm_base, s.llm_model, s.llm_key, s.llm_timeout, extra=s.llm_extra)
            r.llm = QueuedLlm(client, r.queue, tenant_id=s.tenant_id, datasource_id=s.datasource_id)
            applied.append("model")
        if keys & set(admin_mod.store_keys("db")):
            path = s.connection_file or admin_mod.DB_FILE
            old = r.connector
            try:
                fresh = connector_from_file(path)
                fresh.execute("SELECT 1", 1)                       # kurulmadan takas edilmez
                r.connector = fresh
                s.dialect = getattr(fresh, "dialect", "") or s.dialect
                applied.append("veritabanı")
                if old is not None:
                    threading.Thread(target=lambda: _close_quietly(old), name="old-connector-close", daemon=True).start()
            except Exception as e:  # noqa: BLE001
                error = f"Yeni veritabanı ayarı kaydedildi ama bağlantı kurulamadı, eski bağlantı sürüyor: {type(e).__name__}: {e}"[:400]
                log.warning("admin: yeni bağlantı kurulamadı: %s", e)
        if applied:
            r.rebuild()
            log.info("admin: ayar uygulandı (%s)", ", ".join(applied))
        return {"applied": applied, "applyError": error}

    def _close_quietly(c: Any) -> None:
        try:
            c.close()
        except Exception as e:  # noqa: BLE001
            log.debug("eski bağlantı kapatılamadı: %s", e)

    @app.get("/api/v1/admin/me")
    def admin_me(request: Request) -> dict[str, Any]:
        _require_caller(request)
        user = _board_user(request)
        admin_mod.ensure(rt().store.engine)
        return {"user": user, "isAdmin": admin_mod.is_admin(user)}

    @app.get("/api/v1/admin/group")
    def admin_group(request: Request) -> dict[str, Any]:
        """Yönetici AD grubunun kayıtlı anlık görüntüsü: üyeler ve son tazeleme zamanı (canlı okumaz)."""
        _admin(request)
        return admin_mod.group_snapshot()

    @app.post("/api/v1/admin/group/refresh")
    def admin_group_refresh(request: Request) -> dict[str, Any]:
        """Yönetici AD grubunu canlı okuyup DB anlık görüntüsünü tazeler.
        15 dk'lık `timas-admin-group.timer` çağırır (caller token ile); yönetici ekrandan da tetikler."""
        _require_caller(request)
        return admin_mod.refresh_admin_group(rt().store.engine)

    @app.get("/api/v1/admin/overview")
    def admin_overview(request: Request) -> dict[str, Any]:
        r, engine, tenant, ds, _ = _admin(request)
        reports = admin_mod.all_reports(engine, tenant, ds)
        alerts_mod.ensure(engine)
        alerts = alerts_mod.list_rules(engine, tenant, ds)
        cards = admin_mod.all_cards(engine, tenant, ds)
        people = admin_mod.users(engine, tenant, ds)
        return {
            "counts": {
                "reports": len(reports), "reportsActive": sum(1 for x in reports if x["status"] == "active"),
                "reportsFailed": sum(1 for x in reports if x["lastStatus"] == "failed"),
                "alerts": len(alerts), "alertsActive": sum(1 for x in alerts if x["status"] == "active"),
                "alertsTriggered": sum(1 for x in alerts if x["state"] == "triggered"),
                "cards": len(cards), "cardsFailed": sum(1 for x in cards if x["lastError"]),
                "users": len(people), "admins": len(admin_mod.admins()),
            },
            "email": alerts_mod.email_status(),
            "engine": {"model": admin_mod.LLM_DISPLAY, "llm": bool(r.llm), "db": bool(r.connector),
                       "catalog": r.store.status_counts(tenant, ds), "profiles": len(r.profiles)},
            **admin_mod.system_status(),
            "recent": admin_mod.audit_list(engine, limit=8)["items"],
        }

    @app.get("/api/v1/admin/settings")
    def admin_settings(request: Request) -> dict[str, Any]:
        _admin(request)
        return admin_mod.settings_view()

    @app.put("/api/v1/admin/settings")
    def admin_settings_save(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        r, engine, _, _, user = _admin(request)
        try:
            out = admin_mod.save_settings(engine, user, dict(body.get("values") or {}))
        except admin_mod.AdminError as e:
            raise _admin_fail(e) from e
        return {**out, **_apply_settings(r, out["changed"])}

    @app.delete("/api/v1/admin/settings/{key}")
    def admin_settings_reset(key: str, request: Request) -> dict[str, Any]:
        _, engine, _, _, user = _admin(request)
        try:
            return admin_mod.reset_setting(engine, user, key)
        except admin_mod.AdminError as e:
            raise _admin_fail(e) from e

    @app.post("/api/v1/admin/email/test")
    def admin_email_test(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _, engine, _, _, user = _admin(request)
        to = str(body.get("to") or "").strip()
        if "@" not in to:
            raise _admin_fail(ValueError("Deneme için geçerli bir e-posta adresi yazın."))
        ok, message = admin_mod.smtp_test(to)
        admin_mod.audit(engine, user, "test", "setting", "email", "SMTP denemesi", {"to": to, "ok": ok, "message": message})
        return {"ok": ok, "message": message}

    @app.post("/api/v1/admin/directory/test")
    def admin_directory_test(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _, engine, _, _, user = _admin(request)
        username = str(body.get("username") or "").strip()
        ok, message = admin_mod.directory_test(username)
        admin_mod.audit(engine, user, "test", "setting", "directory", "Active Directory denemesi",
                        {"username": username or None, "ok": ok, "message": message})
        return {"ok": ok, "message": message}

    # Bağlantı denemeleri: hepsi kaydedilmiş ayarla gerçek bağlantıyı kurar, sonucu değişiklik
    # kaydına yazar. Ayrı uçlar, çünkü her biri kendi süresini alır ve ekranda ayrı beklenir.
    _CHECK_TITLE = {"database": "Logo veritabanı denemesi", "crm": "CRM denemesi", "llm": "Model denemesi",
                    "directory": "Active Directory denemesi", "email": "E-posta ayarı denemesi",
                    "store": "Meta veritabanı denemesi"}

    @app.post("/api/v1/admin/tests/{check_id}")
    def admin_test_run(check_id: str, request: Request) -> dict[str, Any]:
        _, engine, _, _, user = _admin(request)
        try:
            out = admin_mod.run_check(check_id)
        except admin_mod.AdminError as e:
            raise _admin_fail(e) from e
        admin_mod.audit(engine, user, "test", "setting", check_id, _CHECK_TITLE.get(check_id, f"{check_id} denemesi"),
                        {"ok": out["ok"], "message": out["message"]})
        return out

    @app.post("/api/v1/admin/tests")
    def admin_tests_all(request: Request) -> dict[str, Any]:
        _, engine, _, _, user = _admin(request)
        out = admin_mod.run_checks()
        admin_mod.audit(engine, user, "test", "setting", "all", "Tüm bağlantı denemeleri",
                        {i["id"]: ("başarılı" if i["ok"] else i["message"]) for i in out["items"]})
        return out

    @app.get("/api/v1/admin/system")
    def admin_system(request: Request) -> dict[str, Any]:
        _admin(request)
        return {**admin_mod.system_info(), "checks": [{"id": c["id"], "group": c["group"], "label": c["label"]} for c in admin_mod.CHECKS]}

    @app.get("/api/v1/admin/reports")
    def admin_reports(request: Request) -> dict[str, Any]:
        _, engine, tenant, ds, _ = _admin(request)
        return {"items": admin_mod.all_reports(engine, tenant, ds)}

    @app.patch("/api/v1/admin/reports/{rid}")
    def admin_report_update(rid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _, engine, tenant, ds, user = _admin(request)
        before = reports_mod.get_report(engine, tenant, ds, None, rid)
        if before is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Rapor bulunamadı."})
        try:
            out = reports_mod.update_report(engine, tenant, ds, None, rid, body)  # type: ignore[arg-type]
        except reports_mod.ReportError as e:
            raise _report_fail(e) from e
        diff = admin_mod.changes(before, out or {}, _REPORT_FIELDS)
        if diff:
            admin_mod.audit(engine, user, "update", "report", rid, (out or before)["title"], diff)
        return out or before

    @app.delete("/api/v1/admin/reports/{rid}")
    def admin_report_delete(rid: str, request: Request) -> dict[str, Any]:
        _, engine, tenant, ds, user = _admin(request)
        before = reports_mod.get_report(engine, tenant, ds, None, rid)
        if before is None or not reports_mod.delete_report(engine, tenant, ds, None, rid):  # type: ignore[arg-type]
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Rapor bulunamadı."})
        admin_mod.audit(engine, user, "delete", "report", rid, before["title"], {"question": before["question"], "when": before["when"]})
        return {"ok": True}

    @app.get("/api/v1/admin/alerts")
    def admin_alerts(request: Request) -> dict[str, Any]:
        _, engine, tenant, ds, _ = _admin(request)
        alerts_mod.ensure(engine)
        return {"items": alerts_mod.list_rules(engine, tenant, ds)}

    @app.patch("/api/v1/admin/alerts/{rule_id}")
    def admin_alert_update(rule_id: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _, _, _, _, user = _admin(request)
        return _alert_patch(request, rule_id, body, None, user)

    @app.delete("/api/v1/admin/alerts/{rule_id}")
    def admin_alert_delete(rule_id: str, request: Request) -> dict[str, Any]:
        _, _, _, _, user = _admin(request)
        return _alert_remove(rule_id, None, user)

    @app.get("/api/v1/admin/cards")
    def admin_cards(request: Request) -> dict[str, Any]:
        _, engine, tenant, ds, _ = _admin(request)
        return {"items": admin_mod.all_cards(engine, tenant, ds)}

    @app.delete("/api/v1/admin/cards/{card_id}")
    def admin_card_delete(card_id: str, request: Request) -> dict[str, Any]:
        _, engine, tenant, ds, user = _admin(request)
        row = admin_mod.delete_card(engine, tenant, ds, card_id)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Kart bulunamadı."})
        admin_mod.audit(engine, user, "delete", "board", card_id, row["title"], {"owner": row["username"]})
        return {"ok": True}

    @app.get("/api/v1/admin/users")
    def admin_users(request: Request) -> dict[str, Any]:
        _, engine, tenant, ds, _ = _admin(request)
        return {"items": admin_mod.users(engine, tenant, ds)}

    @app.get("/api/v1/admin/audit")
    def admin_audit(request: Request, kind: Optional[str] = None, actor: Optional[str] = None,
                    action: Optional[str] = None, q: Optional[str] = None, before: Optional[int] = None,
                    limit: int = 100) -> dict[str, Any]:
        _, engine, _, _, _ = _admin(request)
        return admin_mod.audit_list(engine, kind=kind, actor=actor, action=action, q=q, before=before, limit=limit)

    # ------------------------------------------------------------------ promt izleyici
    # Her promt (soru + üretilen SQL + sonuç + kapı kararları) sl_query_log'a yazılır (bkz.
    # Runtime.ask._log). Bu uçlar yalnız yöneticiye, incelemek ve nereyi düzelteceğimizi görmek için.

    @app.get("/api/v1/admin/prompts")
    def admin_prompts(request: Request, limit: int = 60, offset: int = 0, only: Optional[str] = None,
                      q: Optional[str] = None, user: Optional[str] = None, days: Optional[int] = None) -> dict[str, Any]:
        _, _, tenant, ds, _ = _admin(request)
        return rt().store.list_query_log(tenant, ds, limit=limit, offset=offset, only=only,
                                         search=q, username=user, since_days=days)

    @app.get("/api/v1/admin/prompts/overview")
    def admin_prompts_overview(request: Request, days: int = 30) -> dict[str, Any]:
        _, _, tenant, ds, _ = _admin(request)
        return rt().store.query_log_overview(tenant, ds, since_days=max(1, min(int(days), 365)))

    @app.get("/api/v1/admin/prompts/export.csv")
    def admin_prompts_export(request: Request, only: Optional[str] = None, q: Optional[str] = None,
                             user: Optional[str] = None, days: Optional[int] = None) -> Response:
        _, _, tenant, ds, actor = _admin(request)
        # Çevrimdışı incelemek için ("biz alıp inceleyeceğiz"): süzgece uyan promtlar tek CSV.
        # Sonuç satırları değil, kaydın çekirdeği — soru, SQL, cevap, süre, hata, inceleme notu.
        cols = ["createdAt", "username", "answerType", "compiler", "executed", "rowCount",
                "latencyMs", "reviewFlag", "reviewNote", "question", "sql", "answerSummary", "error", "id"]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        offset = 0
        while True:
            page = rt().store.list_query_log(tenant, ds, limit=200, offset=offset, only=only,
                                             search=q, username=user, since_days=days)
            for it in page["items"]:
                w.writerow([it.get(c) if it.get(c) is not None else "" for c in cols])
            if not page.get("hasMore"):
                break
            offset = page["nextOffset"]
        admin_mod.audit(rt().store.engine, actor, "run", "setting", "prompts-export", "Promt dışa aktarma",
                        {"only": only or "all", "q": q or "", "user": user or "", "days": days or "all"})
        return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="promtlar.csv"'})

    @app.get("/api/v1/admin/prompts/{qid}")
    def admin_prompt_detail(qid: str, request: Request) -> dict[str, Any]:
        _, _, tenant, ds, _ = _admin(request)
        row = rt().store.get_query_log(tenant, ds, qid)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Promt bulunamadı."})
        return row

    @app.patch("/api/v1/admin/prompts/{qid}")
    def admin_prompt_mark(qid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        _, engine, tenant, ds, user = _admin(request)
        flag = body.get("flag")
        if flag is not None:
            flag = str(flag).strip().lower()
            if flag not in ("", "todo", "fixed", "ignored"):
                raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Geçersiz işaret."})
        note = body.get("note")
        row = rt().store.mark_query_log(tenant, ds, qid, flag=flag,
                                        note=(str(note) if note is not None else None), reviewed_by=user)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Promt bulunamadı."})
        admin_mod.audit(engine, user, "update", "prompt", qid, (row.get("question") or "")[:80],
                        {"flag": row.get("reviewFlag") or "", "note": (row.get("reviewNote") or "")[:120]})
        return row

    return app


app = create_app()
