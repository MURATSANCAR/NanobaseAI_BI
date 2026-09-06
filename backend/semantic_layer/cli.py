"""CLI: python -m semantic_layer.cli <command>

  init-db                          create sl_* tables (SQLite or Postgres from SEMANTIC_STORE_DSN)
  pipeline [--project D] [--connection F] [--enum-probe J] [--llm]   full offline run
  profile / mine / docs / certify   individual stages
  resolve "soru"                   show the SemanticQuery the runtime would build
  compile "soru"                   resolve + deterministic compile (no LLM)
  explain "terim"                  why this mapping (certified senses + candidates)
  status                           counts, latest catalog version
  export-knowledge --out DIR       write a self-contained knowledge pack (validated pairs + docs) from the catalog
  concepts [--status S] [--type T] list concepts
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store


def _settings(args) -> SemanticSettings:
    s = SemanticSettings.from_env()
    if getattr(args, "store", None):
        s.store_dsn = args.store
    if getattr(args, "datasource", None):
        s.datasource_id = args.datasource
    if getattr(args, "tenant", None):
        s.tenant_id = args.tenant
    if getattr(args, "project", None):
        s.project_dir = Path(args.project).resolve()
    if getattr(args, "connection", None):
        s.connection_file = args.connection
    if getattr(args, "min_support", None):
        s.min_support = int(args.min_support)
    return s


def _dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="semantic_layer")
    ap.add_argument("--store", help="SQLAlchemy DSN (default env SEMANTIC_STORE_DSN / NANOBASE_META_DSN / sqlite)")
    ap.add_argument("--datasource")
    ap.add_argument("--tenant")
    ap.add_argument("--project", "--knowledge", dest="project", help="knowledge pack dir (knowledge/, optional models/)")
    ap.add_argument("--connection", help="connection JSON (mssql/postgres)")
    ap.add_argument("--enum-probe", help="offline enum probe JSON (artifacts/timas/apply-all.json)")
    ap.add_argument("--min-support", type=int)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    p = sub.add_parser("pipeline"); p.add_argument("--llm", action="store_true"); p.add_argument("--skip-profile", action="store_true"); p.add_argument("--intugle", action="store_true", help="use Intugle for link/glossary discovery when installed"); p.add_argument("--note", default="")
    sub.add_parser("profile")
    sub.add_parser("mine")
    sub.add_parser("docs")
    sub.add_parser("certify")
    sub.add_parser("status")
    p = sub.add_parser("export-knowledge"); p.add_argument("--out", required=True)
    p = sub.add_parser("resolve"); p.add_argument("question")
    p = sub.add_parser("compile"); p.add_argument("question")
    p = sub.add_parser("explain"); p.add_argument("term")
    p = sub.add_parser("concepts"); p.add_argument("--status"); p.add_argument("--type"); p.add_argument("--q")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    s = _settings(args)
    store = open_store(s.store_dsn)

    if args.cmd == "init-db":
        store.create_all()
        print("ok:", s.store_dsn.split("@")[-1])
        return 0
    if args.cmd == "export-knowledge":
        from semantic_layer.history.sources import export_pack

        _dump(export_pack(store, s, Path(args.out)))
        return 0
    from semantic_layer import pipeline as pl

    if args.cmd == "pipeline":
        llm = None
        if args.llm:
            from semantic_layer.candidates.llm_client import LlmClient

            llm = LlmClient(s.llm_base, s.llm_model, s.llm_key, s.llm_timeout)
        import os as _os

        use_intugle = args.intugle or _os.environ.get("SEMANTIC_INTUGLE", "").lower() in ("1", "true", "yes")
        _dump(pl.run_pipeline(store, s, enum_probe=Path(args.enum_probe) if args.enum_probe else None, skip_profile=args.skip_profile, llm=llm, use_intugle=use_intugle, note=args.note))
        return 0
    if args.cmd == "profile":
        c = pl.build_connector(s, enum_probe=Path(args.enum_probe) if args.enum_probe else None)
        try:
            profiles = pl.run_profile(store, s, c)
        finally:
            c.close()
        from semantic_layer.profiler.profiler import profile_summary

        _dump(profile_summary(profiles))
        return 0
    profiles = store.list_profiles(s.datasource_id)
    if args.cmd == "mine":
        _dump(pl.run_mine(store, s, profiles, s.project_dir))
        return 0
    if args.cmd == "docs":
        from semantic_layer.candidates.generator import CandidateGenerator

        gen = CandidateGenerator(store, s.tenant_id, s.datasource_id, profiles)
        _dump({"docs": gen.ingest_project_docs(s.project_dir), "profile_evidence": gen.attach_profile_evidence()})
        return 0
    if args.cmd == "certify":
        from semantic_layer.evidence.engine import EvidenceEngine

        _dump(EvidenceEngine(store, min_support=s.min_support, threshold=s.certify_threshold).run(s.tenant_id, s.datasource_id, profiles))
        return 0
    if args.cmd == "status":
        _dump({"status": store.status_counts(s.tenant_id, s.datasource_id), "certified_by_type": store.type_counts(s.tenant_id, s.datasource_id), "version": store.latest_version(s.tenant_id, s.datasource_id), "profiles": len(profiles), "queries": store.query_stats(s.tenant_id, s.datasource_id)})
        return 0
    from semantic_layer.runtime.resolver import SemanticResolver

    resolver = SemanticResolver(store, s.tenant_id, s.datasource_id, profiles)
    if args.cmd == "resolve":
        _dump(resolver.resolve(args.question).to_dict())
        return 0
    if args.cmd == "compile":
        from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider

        q = resolver.resolve(args.question)
        comp = DeterministicCompiler(profiles, s.context, s.dialect, default_filters=default_filters_provider(store, s.tenant_id, s.datasource_id))
        out = comp.compile(q, store)
        _dump({"query": q.to_dict(), "sql": out.sql if out else None, "explain": out.explain if out else comp.plan(q)[1]})
        return 0
    if args.cmd == "explain":
        _dump(resolver.explain_term(args.term))
        return 0
    if args.cmd == "concepts":
        rows = store.search_concepts(s.tenant_id, s.datasource_id, args.q) if args.q else store.find_concepts(s.tenant_id, s.datasource_id, status=args.status, semantic_type=args.type, limit=2000)
        for c in rows:
            maps = store.list_mappings(c.id)
            tgt = "; ".join((m.formula or f"{m.entity}.{m.column} {m.operator} {m.values}") for m in maps)
            print(f"{c.status:14} {c.semantic_type:16} {c.term!r:30} conf={c.confidence:.2f} v{c.version} → {tgt[:110]}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
