"""Offline pipeline: profile → mine history → docs → profile evidence → (optional LLM candidates) →
certify → version. Used by the CLI, the nightly worker and the portal "refresh" action."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from semantic_layer.candidates.generator import CandidateGenerator
from semantic_layer.config import SemanticSettings
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.history.miner import HistoryMiner
from semantic_layer.history.sources import dedupe, load_project_pairs, load_query_log
from semantic_layer.models import SchemaProfile
from semantic_layer.profiler.connectors import Connector, ModelFileConnector, connector_from_file
from semantic_layer.conventions import Conventions
from semantic_layer.profiler.profiler import Profiler, column_index, infer_links, profile_summary
from semantic_layer.store.catalog_store import CatalogStore

log = logging.getLogger(__name__)
_last_profiler: Any = None


def build_connector(settings: SemanticSettings, *, project_dir: Optional[Path] = None, connection_file: Optional[str] = None, enum_probe: Optional[Path] = None) -> Connector:
    conn_file = connection_file or settings.connection_file
    if conn_file and Path(conn_file).exists():
        return connector_from_file(conn_file)
    proj = project_dir or settings.project_dir
    if proj and (Path(proj) / "models").exists():
        return ModelFileConnector(Path(proj), enum_probe)
    raise RuntimeError("no connection file and no knowledge pack with models/ — nothing to profile")


def run_profile(store: CatalogStore, settings: SemanticSettings, connector: Connector, *, schema: Optional[str] = None, like: Optional[str] = None, probe_links: Optional[bool] = None) -> list[SchemaProfile]:
    """Discover tables/columns/enums/keys. Schema and dialect default to the connector's own."""
    schema = schema or settings.schema_name or getattr(connector, "default_schema", "")
    # No count limits. An ERP that keeps one table set per firm and one per firm-period (Logo: 310
    # shapes → well over a thousand physical tables) blew straight through the old 300-table cap, and
    # everything past it was not merely unprofiled but absent from the catalog — so the catalog said
    # one thing and the database another, and no plan or report built on it could be reconciled.
    # Cataloguing is cheap (names, columns, keys). Deep probing is the expensive half — value
    # inventories are full scans — and it is bounded by its wall clock, not by a table count; both
    # environment variables remain for a deployment that deliberately wants a bounded run.
    def _cap(name: str) -> Optional[int]:
        raw = (os.environ.get(name) or "").strip()
        return int(raw) if raw.isdigit() and int(raw) > 0 else None

    prof = Profiler(connector, enum_max_distinct=settings.enum_max_distinct, max_tables=_cap("SEMANTIC_MAX_TABLES"))
    profiles = prof.profile(settings.datasource_id, schema, (like if like is not None else settings.table_like) or None, deep_limit=_cap("SEMANTIC_DEEP_TABLES"))
    # Value-overlap link inference asks the customer's database a question per candidate column. On a
    # real warehouse that is a deliberate, opt-in cost (SEMANTIC_PROBE_LINKS=1); on a local/file source
    # it is free, so it stays on there.
    if probe_links is None:
        probe_links = os.environ.get("SEMANTIC_PROBE_LINKS", "").lower() in ("1", "true", "yes") or getattr(connector, "dialect", "") == "sqlite"
    if probe_links and hasattr(connector, "execute"):
        try:
            added = infer_links(profiles, connector)
            if added:
                log.info("link inference added %d relationships from value overlap", added)
        except Exception as e:  # noqa: BLE001
            log.warning("link inference skipped: %s", e)
    globals()["_last_profiler"] = prof
    if not settings.dialect:
        settings.dialect = getattr(connector, "dialect", "") or "generic"
    for p in profiles:
        store.upsert_profile(p)
    removed = store.prune_profiles(settings.datasource_id, [p.table_pattern for p in profiles])
    if removed:
        log.info("pruned %d profile rows no longer in scope", removed)
    return profiles


def run_mine(store: CatalogStore, settings: SemanticSettings, profiles: list[SchemaProfile], project_dir: Optional[Path], conventions: Optional[Conventions] = None) -> dict[str, Any]:
    pairs = load_project_pairs(project_dir or settings.project_dir)
    pairs += load_query_log(store.list_validated_queries(settings.tenant_id, settings.datasource_id))
    pairs = dedupe(pairs)
    conv = conventions or Conventions.from_profiles(profiles)
    miner = HistoryMiner(column_index(profiles), conventions=conv)
    res = miner.mine(pairs)
    conv.learn_time_hint(res.temporal_bindings)
    persisted = miner.persist(res, store, settings.tenant_id, settings.datasource_id)
    return {"summary": res.summary(), "persisted": persisted, "context": res.context, "time_columns": dict(conv.time_hint)}


def run_pipeline(
    store: CatalogStore,
    settings: SemanticSettings,
    *,
    project_dir: Optional[Path] = None,
    connection_file: Optional[str] = None,
    enum_probe: Optional[Path] = None,
    skip_profile: bool = False,
    llm=None,
    use_intugle: bool = False,
    probe: bool = True,
    note: str = "",
) -> dict[str, Any]:
    t0 = time.perf_counter()
    report: dict[str, Any] = {}
    project_dir = project_dir or settings.project_dir
    connector = None
    if skip_profile:
        profiles = store.list_profiles(settings.datasource_id)
        if probe:
            # Re-certifying on stored profiles still has to confront the catalog with the data — that
            # is what the probe is for. Without a connector the whole run used to die at the last step.
            try:
                connector = build_connector(settings, project_dir=project_dir, connection_file=connection_file, enum_probe=enum_probe)
            except Exception as e:  # noqa: BLE001
                log.warning("probe skipped: no connector (%s)", str(e)[:200])
                report["probe"] = {"skipped": f"no connector: {str(e)[:200]}"}
    else:
        connector = build_connector(settings, project_dir=project_dir, connection_file=connection_file, enum_probe=enum_probe)
        profiles = run_profile(store, settings, connector)
    if use_intugle:
        from semantic_layer.profiler import intugle_adapter

        ir = intugle_adapter.run(profiles)
        if ir.ran:
            for p in profiles:
                store.upsert_profile(p)
        report["intugle"] = ir.to_dict()
    conventions = Conventions.from_profiles(profiles)
    report["profile"] = profile_summary(profiles)
    if getattr(_last_profiler, "truncated", None):
        report["profile"]["not_profiled"] = _last_profiler.truncated[:20]
        report["profile"]["not_profiled_count"] = len(_last_profiler.truncated)
    report["mine"] = run_mine(store, settings, profiles, project_dir, conventions)
    gen = CandidateGenerator(store, settings.tenant_id, settings.datasource_id, profiles, conventions)
    report["docs"] = gen.ingest_project_docs(project_dir)
    report["profile_evidence"] = gen.attach_profile_evidence()
    if llm is not None:
        # A model timeout must not cost the whole nightly run: candidates are a bonus, not a precondition.
        # Two separate readings, and one failing must not take the other with it: they were in one
        # try block, so a context overflow in the first meant the second never ran at all.
        try:
            unresolved = store.list_unresolved_terms(settings.tenant_id, settings.datasource_id)
            report["llm"] = gen.llm_candidates(llm, list(unresolved)[:20])
        except Exception as e:  # noqa: BLE001
            log.warning("llm candidate stage skipped: %s", e)
            report["llm"] = {"error": str(e)[:200]}
        try:
            # read the schema itself: a column no question has ever mentioned would otherwise stay
            # nameless for ever, and there are tens of thousands of them
            report["proposals"] = gen.propose_column_meanings(llm, max_columns=int(os.environ.get("SEMANTIC_PROPOSE_COLUMNS", "200")))
        except Exception as e:  # noqa: BLE001
            log.warning("column proposal stage skipped: %s", e)
            report["proposals"] = {"error": str(e)[:200]}
    if use_intugle and report.get("intugle", {}).get("ran"):
        from semantic_layer.profiler import intugle_adapter

        report["intugle"]["evidence"] = intugle_adapter.attach_evidence(store, settings.tenant_id, settings.datasource_id, profiles, intugle_adapter.IntugleReport(available=True, ran=True)).evidence
    engine = EvidenceEngine(store, min_support=settings.min_support, threshold=settings.certify_threshold)
    report["certify"] = engine.run(settings.tenant_id, settings.datasource_id, profiles, note=note + " (pre-probe)")

    # Confront the catalog with the data: do the codes occur, do the metrics run, do related tables agree,
    # and how far is each measure actually populated. Then certify again with what the database answered.
    if probe and connector is not None and getattr(connector, "supports_execution", False):
        from semantic_layer.evidence.probe import probe_all

        try:
            rep = probe_all(store, settings.tenant_id, settings.datasource_id, profiles, connector, conventions, context=settings.context, dialect=settings.dialect)
            report["probe"] = rep.to_dict()
            for p in profiles:
                store.upsert_profile(p)          # freshness notes land on the columns
            report["certify"] = engine.run(settings.tenant_id, settings.datasource_id, profiles, note=note)
        except Exception as e:  # noqa: BLE001
            log.warning("probing skipped: %s", e)
            report["probe"] = {"error": str(e)[:200]}
    if connector is not None:
        connector.close()
    report["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return report
