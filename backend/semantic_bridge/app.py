"""Semantic Bridge — the cockpit contract (/api/v1/ask, /run_sql, /engine, /generate_summary).

    USER → Qwen-free Resolver → CERTIFIED catalog → DeterministicCompiler → SQL Server
                           └─ MISS / complex → ExistingCompiler (Qwen + certified facts) → dry-run → SQL Server

Also: /api/v1/feedback (validated Q→SQL → History Miner input), /api/v1/semantic/* (resolve, explain,
status, certify), /api/v1/schema/* (inventory + annotations for the portal layer).
"""

from __future__ import annotations

import hashlib
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
from semantic_layer.history.sources import _pid as pair_id, load_project_pairs, load_query_log
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.models import Annotation, ConceptStatus, Evidence, EvidenceType, SchemaProfile, SemanticQuery, TemporalSlot
from semantic_layer.models import Mapping as SLMapping, SemanticType
from semantic_layer.naming import label_context
from semantic_layer.normalize import normalize_term, tokenize
from semantic_layer.profiler.connectors import Connector, connector_from_file
from semantic_layer.runtime.compiler import CompilerRouter, DeterministicCompiler, Dialect, ExistingCompiler, default_filters_provider, fast_summary, is_empty_result
# The fragment shown to a reviewer must be the fragment the compiler will emit; rendering a
# second, prettier version of it would let the screen and the engine disagree.
from semantic_layer.runtime.compiler import _pred_sql as compiled_predicate
from semantic_layer.runtime.audit import audit_sql, unmet_obligations
from semantic_layer.runtime import critic
from semantic_layer.runtime.guardrails import allowed_tables, is_connection_error, physicalize_sql, referenced_tables, strip_comments, strip_trailing_semicolon, validate_sql
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
        # Executed results, kept whole so the table, the chart and the export read the same rows.
        self._results: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._results_lock = threading.Lock()
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
        parts = [f.read_text(encoding="utf-8") for f in sorted((pd / "knowledge").rglob("*.md"))
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
        if version != self._catalog_version:
            log.info("catalog changed (%s → %s) — reloading profiles", self._catalog_version, version)
            self.rebuild()

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
        # result says matters most. Measured on this deployment's golden set with the A40 model:
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
                                   extra={"chat_template_kwargs": {"enable_thinking": False}})
                existing.selector = TableSelector(client)
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
    def _physical(self, sql: str, period: Optional[tuple] = None) -> str:
        """`period` lets an entity split one-table-per-year resolve to the tables that year needs.

        Passed only where the question is known. The endpoints that take raw SQL have no question and
        no period, and there the behaviour is what it always was: one entity, one table.
        """
        return physicalize_sql(strip_trailing_semicolon(sql), self.profiles, self.settings.context,
                               self.settings.dialect, period=period)

    @staticmethod
    def _asked_period(q: Any) -> Optional[tuple]:
        """The span a question asked for, or None when it named no period at all."""
        if q is None:
            return None
        start = min((t.start for t in getattr(q, "temporal", []) if t.start), default=None)
        end = max((t.end for t in getattr(q, "temporal", []) if t.end), default=None)
        return (start, end) if start and end else None

    def dry_run(self, sql: str) -> None:
        if self.connector is None:
            raise RuntimeError("no database connector")
        with self._engine_lock:
            self.connector.dry_run(sql)

    def run_sql(self, sql: str, limit: int, period: Optional[tuple] = None) -> dict[str, Any]:
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
        phys = self._physical(sql, period)
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
                    return out
        out, duration = self._execute(phys, limit, interactive=True)
        self._remember(key, out, duration)
        served = self._served(out, time.time())
        served["cached"] = False
        return served

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
                cols, rows, truncated = self.connector.execute(phys, limit)
                duration = time.monotonic() - t0
        finally:
            if interactive:
                with self._wait_lock:
                    self._waiting -= 1
        return {"columns": cols, "records": rows, "totalRows": len(rows), "truncated": truncated, "physicalSql": phys}, duration

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
                "question": question,
                "sql": sql,
                "physicalSql": result.get("physicalSql"),
                "columns": result.get("columns") or [],
                "records": result.get("records") or [],
                "totalRows": result.get("totalRows") or 0,
                "truncated": bool(result.get("truncated")),
                "dataCoverage": result.get("dataCoverage", []),
                "comparison": result.get("comparison"),
            }
            while len(self._results) > self._results_max:
                self._results.popitem(last=False)

    def stored_result(self, rid: str) -> Optional[dict[str, Any]]:
        with self._results_lock:
            snap = self._results.get(rid)
            if snap is None:
                return None
            if time.time() - snap["at"] > self._result_ttl:
                self._results.pop(rid, None)
                return None
            if snap["tenant_id"] != self.settings.tenant_id:
                return None
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

    def _remember(self, key: str, out: dict[str, Any], duration: float) -> None:
        if self._cache_ttl <= 0 or len(out.get("records") or []) > 200:
            return
        self._cache[key] = (time.time(), out)
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
        if self.settings.summary_mode == "llm" and self.llm is not None:
            sample = result["records"][:20]
            prompt = ("Aşağıdaki soru ve sorgu sonucunu 1-3 cümlede Türkçe özetle. Sayıları Türkçe biçimle, yorum katma, sadece veride olanı söyle.\n"
                      f"Soru: {question}\nSatır sayısı: {result['totalRows']}\nİlk satırlar (JSON): {json.dumps(sample, ensure_ascii=False)[:4000]}")
            try:
                return self.llm.chat([{"role": "user", "content": prompt}], max_tokens=300).strip() + note
            except Exception as e:  # noqa: BLE001
                log.warning("llm summary failed: %s", e)
        return fast_summary(question, cols, result.get("records") or [], int(result.get("totalRows") or 0)) + note

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
                self.thread_plans.pop(stale, None)
        self.ensure_fresh()
        t = time.perf_counter()
        from semantic_layer.runtime.conversation import compose_followup
        effective_question, context_error = compose_followup(question, self.thread_plans.get(thread_id))
        if context_error:
            return {"id": uuid.uuid4().hex, "type": "CLARIFICATION", "explanation": context_error,
                    "threadId": thread_id, "timings": timings}
        sq = self.resolver.resolve(effective_question)
        if effective_question != question:
            sq.explanation.append(f"Konuşma bağlamıyla tamamlanan soru: {effective_question}")
        timings["resolve_ms"] = int((time.perf_counter() - t) * 1000)
        if any(c["status"] == "OUTSIDE_OBSERVED" for c in sq.data_coverage):
            reason = " ".join(e for e in sq.explanation if "gözlenen veri kapsamı dışında" in e)
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=None, compiler="coverage", catalog_version=sq.catalog_version,
                                      resolved=sq.to_dict(), executed=False, error=reason)
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
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=None,
                                      compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                                      resolved=sq.to_dict(), executed=False, error=reason)
            return {"id": uuid.uuid4().hex, "type": "INCOMPLETE_ANSWER", "explanation": reason,
                    "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        if compiled.compiler == "clarification":
            reason = " ".join(compiled.explain)
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=None,
                                      compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                                      resolved=sq.to_dict(), executed=False)
            thread.extend([{"role": "user", "content": question}, {"role": "assistant", "content": reason}])
            return {"id": uuid.uuid4().hex, "type": "CLARIFICATION", "needs_clarification": True,
                    "explanation": reason, "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
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
        # What the question asked for and the statement does not deliver. Checked for every query,
        # certified or not: a comparison is built by the deterministic compiler too, and a single
        # period returned for "geçen yıla göre" is a complete-looking answer to a different question.
        unmet = unmet_obligations(sq, sql)
        if unmet:
            reason = "Sorudaki koşulların tamamı doğrulanamadı: " + "; ".join(unmet)
            log.warning("obligation unmet q=%r %s", question[:80], unmet)
            semantic["unmetObligations"] = unmet
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=reason)
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
                qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=reason)
                return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": reason, "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        repairs = 0
        error: Optional[str] = None
        critic_notes: list[dict] = []
        if self.connector is not None:
            for attempt in range(2):
                try:
                    self.dry_run(self._physical(sql, self._asked_period(sq)))
                    error = None
                    # The database has now agreed the query is valid. Whether it returns the number
                    # that was asked for is a different question and the one that costs the most: a
                    # join that repeats rows under a SUM returns a total larger than the truth by a
                    # factor nobody sees, and the database is perfectly happy with it. Reviewed after
                    # dry_run so the reviewer works on a query already known to parse and resolve.
                    found = critic.review(sql, self.profiles, self.settings.dialect or "tsql")
                    critic_notes = [f.to_dict() for f in found]
                    blocking = [f for f in found if f.severity == "block"]
                    if not blocking:
                        break
                    log.warning("critic refused q=%r %s", question[:80], [f.kind for f in blocking])
                    if attempt == 1 or self.existing is None or compiled.compiler == "deterministic":
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
                except Exception as e:  # noqa: BLE001
                    error = str(e)[:1500]
                    if is_connection_error(e):
                        # The database went away. No rewrite of this SQL can help, and telling the user
                        # their question was invalid would send them looking in the wrong place.
                        log.error("data source unreachable q=%r err=%s", question[:80], error[:300])
                        qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=f"data source unreachable: {error}")
                        return {"id": uuid.uuid4().hex, "type": "DATA_SOURCE_UNAVAILABLE", "sql": sql,
                                "explanation": "Veri kaynağına şu an ulaşılamıyor; soruda bir sorun yok. Bağlantı geri geldiğinde aynı soru çalışacak.",
                                "threadId": thread_id, "repairs": repairs, "timings": timings, "semantic": semantic, "queryId": qid}
                    log.warning("dry_run failed (attempt %d) q=%r err=%s", attempt + 1, question[:80], error[:300])
                    if attempt == 1 or self.existing is None or compiled.compiler == "deterministic":
                        break
                    repairs += 1
                    fixed = self.existing.repair(sq, sql, error, thread)
                    if not fixed:
                        break
                    sql = strip_trailing_semicolon(fixed)
        if critic_notes:
            semantic["critic"] = critic_notes
        if error:
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=error)
            # A query the reviewer stopped is a different thing from one the database rejected, and
            # the person is owed the difference: the first has an explanation they can act on, the
            # second is a fault. Both refuse — neither returns a number nobody can trust.
            blocked = any(n.get("severity") == "block" for n in critic_notes)
            explanation = error if blocked else f"Üretilen SQL doğrulanamadı: {error}"
            return {"id": uuid.uuid4().hex, "type": "SQL_INVALID", "sql": sql, "explanation": explanation, "threadId": thread_id, "repairs": repairs, "timings": timings, "semantic": semantic, "queryId": qid}
        # Repairs can remove filters or period predicates. Validate the exact final
        # statement, including previews; never trust the pre-repair verdict.
        final_problems = unmet_obligations(sq, sql) + audit_sql(sq, sql, conventions=self.conventions)
        semantic["query"] = sq.to_dict()
        if final_problems:
            reason = "Sorudaki koşulların tamamı doğrulanamadı: " + "; ".join(final_problems)
            semantic["unmetObligations"] = final_problems
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql,
                                      compiler=compiled.compiler, catalog_version=compiled.catalog_version,
                                      resolved=sq.to_dict(), executed=False, error=reason)
            return {"id": uuid.uuid4().hex, "type": "INCOMPLETE_ANSWER", "explanation": reason,
                    "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        if not execute or self.connector is None:
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False)
            return {"id": uuid.uuid4().hex, "type": "TEXT_TO_SQL", "sql": sql, "physicalSql": self._physical(sql, self._asked_period(sq)), "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid, "executed": False}
        t = time.perf_counter()
        try:
            # Executed once, whole. The client is shown a page of it; the export needs all of it, and
            # asking twice would be a second execution against data that can have moved.
            result = self.run_sql(sql, self.settings.max_rows, self._asked_period(sq))
        except Exception as e:  # noqa: BLE001
            err = str(e)[:800]
            down = is_connection_error(e)
            if down:
                log.error("data source unreachable during execution q=%r err=%s", question[:80], err[:300])
            qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=False, error=(f"data source unreachable: {err}" if down else err))
            return {"id": uuid.uuid4().hex,
                    "type": "DATA_SOURCE_UNAVAILABLE" if down else "SQL_INVALID", "sql": sql,
                    "explanation": ("Veri kaynağına şu an ulaşılamıyor; soruda bir sorun yok. Bağlantı geri geldiğinde aynı soru çalışacak."
                                    if down else f"Sorgu çalıştırılamadı: {err}"),
                    "threadId": thread_id, "timings": timings, "semantic": semantic, "queryId": qid}
        timings["run_sql_ms"] = int((time.perf_counter() - t) * 1000)
        result["dataCoverage"] = list(sq.data_coverage)
        result["comparison"] = sq.comparison
        self.attach_widget(result, question)
        self.remember_result(result, question=question, sql=sql)
        shown = list(result["records"])[: max(1, int(sample_size or 50))]
        t = time.perf_counter()
        summary = self.summarize(question, sql, result, sq)
        timings["summary_ms"] = int((time.perf_counter() - t) * 1000)
        fp = result_fingerprint([c["name"] for c in result["columns"]], result["records"])
        qid = self.store.log_query(self.settings.tenant_id, self.settings.datasource_id, question, sql=sql, compiler=compiled.compiler, catalog_version=compiled.catalog_version, resolved=sq.to_dict(), executed=True, row_count=result["totalRows"], latency_ms=int((time.perf_counter() - t0) * 1000), result_fingerprint=fp)
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
            "dataCoverage": result.get("dataCoverage", []),
            "columns": result["columns"],
            "records": shown,
            "shownRows": len(shown),
            "truncated": result.get("truncated"),
            "cached": result.get("cached"),
            "ageSec": result.get("ageSec"),
            "computedAt": result.get("computedAt"),
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

    def add_annotation(self, table_pattern: str, column: Optional[str], text: str, author: str) -> dict[str, Any]:
        s = self.settings
        ann = self.store.add_annotation(Annotation(datasource_id=s.datasource_id, table_pattern=table_pattern, column=(column or None), text=text.strip(), author=author))
        gen = CandidateGenerator(self.store, s.tenant_id, s.datasource_id, self.profiles, self.conventions)
        ingested = gen.ingest_annotation(table_pattern, column, text, f"annotation:{ann.id}")
        self._inventory_cache.clear()      # what someone just wrote has to show on the very next read
        return {"annotation": {"id": ann.id, "tablePattern": table_pattern, "column": column, "text": ann.text, "author": author}, "candidates": ingested}

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
        llm = LlmClient(settings.llm_base, settings.llm_model, settings.llm_key, settings.llm_timeout)
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
    """Reading and asking sit behind the site's own authentication; changing the catalog needs a token.
    Without this, anything that can reach the cockpit's API path could recertify the semantics."""
    token = os.environ.get("SEMANTIC_ADMIN_TOKEN", "")
    if not token:
        return                      # not configured: the loopback binding is the only control
    supplied = request.headers.get("x-semantic-admin", "") or request.query_params.get("admin_token", "")
    if not secrets_compare(supplied, token):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "admin token required"})


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


def create_app(runtime: Optional[Runtime] = None) -> FastAPI:
    state: dict[str, Any] = {"rt": runtime}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if state["rt"] is None:
            state["rt"] = build_runtime()
        rt = state["rt"]
        log.info("semantic bridge ready: profiles=%d certified=%s llm=%s db=%s", len(rt.profiles), rt.store.status_counts(rt.settings.tenant_id, rt.settings.datasource_id).get("CERTIFIED"), bool(rt.llm), bool(rt.connector))
        rt.start_refresher()
        try:
            yield
        finally:
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
    def stored_result(result_id: str, request: Request) -> dict[str, Any]:
        """The whole result of one execution, for a client that showed a page of it.

        Not a re-run: if this execution is gone the caller is told so and asks its question again.
        Serving a fresh run of the same SQL under the same identity would hand back numbers the user
        never saw, computed at a different moment, with the same air of being "the same result".
        """
        _require_caller(request)
        snap = rt().stored_result(result_id)
        if snap is None:
            raise HTTPException(status_code=410, detail={
                "code": "RESULT_GONE",
                "message": "Bu sonucun saklama süresi doldu. Aynı soruyu tekrar sorun — eski SQL sessizce yeniden çalıştırılmaz."})
        return {"id": result_id, "columns": snap["columns"], "records": snap["records"],
                "totalRows": snap["totalRows"], "truncated": snap["truncated"],
                "question": snap["question"], "sql": snap["sql"], "computedAt": snap["at"],
                "dataCoverage": snap.get("dataCoverage", []), "comparison": snap.get("comparison")}

    @app.post("/api/v1/ask")
    def ask(body: AskIn, request: Request) -> dict[str, Any]:
        _require_caller(request)
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
        r = rt()
        s = r.settings
        decision = str((body or {}).get("decision") or "").strip().upper()
        if decision not in ("APPROVE", "REJECT", "CORRECT"):
            raise HTTPException(status_code=400, detail={"code": "BAD_DECISION",
                                                         "message": "decision APPROVE, REJECT ya da CORRECT olmalı"})
        bundle = r.store.concept_bundle(concept_id)
        if not bundle:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        who = str((body or {}).get("by") or request.headers.get("X-User") or "portal")
        note = str((body or {}).get("note") or "")
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

    @app.get("/api/v1/semantic/review")
    def review_queue(limit: int = 100, source: str = "used") -> dict[str, Any]:
        """What is waiting for a person to decide, the most supported first.

        Each row carries what the term would mean, where it points, and what stands behind it — the
        queries it was seen in, the documents that describe it, what the data shows. Without those a
        reviewer is being asked to approve a word, which nobody can do responsibly.
        """
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
        out = []
        for x in pool[:limit]:
            c, m = x["concept"], x["mapping"]
            prof = r.resolver.by_entity.get(m.entity) if m else None
            col = prof.column(m.column) if prof and m and m.column else None
            meaning = col.meaning(said.get((m.entity, (m.column or "").upper()))) if col and m else None
            out.append({
                "id": c.id, "term": c.term, "type": c.semantic_type, "confidence": c.confidence,
                "mapping": m.to_dict() if m else None,
                "evidence": x["evidence"], "evidenceCount": x["evidenceCount"],
                # what the data itself shows about the column this term claims
                "observed": [{"value": v, "rows": n, "label": _decode(meaning, v)}
                             for v, n in (col.top_values or [])[:6]] if col else [],
                "columnMeaning": meaning,
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
        return rt().add_annotation(body.tablePattern, body.column, body.text, body.author or "cockpit")

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
        return {"ok": rt().store.retire_annotation(annotation_id)}

    return app


app = create_app()
