"""Offline pipeline: profile → mine history → docs → profile evidence → (optional LLM candidates) →
certify → version. Used by the CLI, the nightly worker and the portal "refresh" action."""

from __future__ import annotations

import logging
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


def build_connector(settings: SemanticSettings, *, project_dir: Optional[Path] = None, connection_file: Optional[str] = None, enum_probe: Optional[Path] = None) -> Connector:
    conn_file = connection_file or settings.connection_file
    if conn_file and Path(conn_file).exists():
        return connector_from_file(conn_file)
    proj = project_dir or settings.project_dir
    if proj and (Path(proj) / "models").exists():
        return ModelFileConnector(Path(proj), enum_probe)
    raise RuntimeError("no connection file and no knowledge pack with models/ — nothing to profile")


def run_profile(store: CatalogStore, settings: SemanticSettings, connector: Connector, *, schema: Optional[str] = None, like: Optional[str] = None, probe_links: bool = True) -> list[SchemaProfile]:
    """Discover tables/columns/enums/keys. Schema and dialect default to the connector's own."""
    schema = schema or settings.schema_name or getattr(connector, "default_schema", "")
    prof = Profiler(connector, enum_max_distinct=settings.enum_max_distinct)
    profiles = prof.profile(settings.datasource_id, schema, (like if like is not None else settings.table_like) or None)
    if probe_links and hasattr(connector, "execute"):
        try:
            added = infer_links(profiles, connector)
            if added:
                log.info("link inference added %d relationships from value overlap", added)
        except Exception as e:  # noqa: BLE001
            log.warning("link inference skipped: %s", e)
    if not settings.dialect:
        settings.dialect = getattr(connector, "dialect", "") or "generic"
    for p in profiles:
        store.upsert_profile(p)
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
    if skip_profile:
        profiles = store.list_profiles(settings.datasource_id)
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
    report["mine"] = run_mine(store, settings, profiles, project_dir, conventions)
    gen = CandidateGenerator(store, settings.tenant_id, settings.datasource_id, profiles, conventions)
    report["docs"] = gen.ingest_project_docs(project_dir)
    report["profile_evidence"] = gen.attach_profile_evidence()
    if llm is not None:
        unresolved = store.list_unresolved_terms(settings.tenant_id, settings.datasource_id)
        report["llm"] = gen.llm_candidates(llm, list(unresolved)[:20])
    if use_intugle and report.get("intugle", {}).get("ran"):
        from semantic_layer.profiler import intugle_adapter

        report["intugle"]["evidence"] = intugle_adapter.attach_evidence(store, settings.tenant_id, settings.datasource_id, profiles, intugle_adapter.IntugleReport(available=True, ran=True)).evidence
    engine = EvidenceEngine(store, min_support=settings.min_support, threshold=settings.certify_threshold)
    report["certify"] = engine.run(settings.tenant_id, settings.datasource_id, profiles, note=note + " (pre-probe)")

    # Confront the catalog with the data: do the codes occur, do the metrics run, do related tables agree,
    # and how far is each measure actually populated. Then certify again with what the database answered.
    if probe and connector is not None and hasattr(connector, "execute"):
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
