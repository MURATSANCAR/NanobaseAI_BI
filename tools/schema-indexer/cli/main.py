from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="schema-indexer", description="Nanobase Schema Indexer (Faz 2)")
    p.add_argument(
        "--datasource",
        default=None,
        help="Datasource id (default: REPORTING_DATASOURCE_ID / any id in neon-ro map)",
    )
    p.add_argument(
        "--schemas",
        default=None,
        help="Comma-separated schemas (default: analytics,public for reporting; public otherwise)",
    )
    p.add_argument("--collection", default=None, help="Qdrant collection override")
    p.add_argument("--recreate", action="store_true", help="Drop+recreate collection before upsert")
    p.add_argument("--skip-samples", action="store_true")
    p.add_argument("--skip-profile", action="store_true")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--json", action="store_true", help="Print ScanReport JSON to stdout")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pkg = Path(__file__).resolve().parents[1]
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))

    from config import IndexerConfig, _reporting_datasource_id
    from pipeline import run_index

    ds = args.datasource or _reporting_datasource_id()
    reporting_id = _reporting_datasource_id()
    if ds == "nanobase_test":
        ds = reporting_id
    if args.schemas:
        schemas = tuple(s.strip() for s in args.schemas.split(",") if s.strip())
    elif ds == reporting_id:
        schemas = ("analytics", "public")
    else:
        schemas = ("public",)

    cfg = IndexerConfig(
        datasource_id=ds,
        collection=args.collection,
        schemas=schemas,
        skip_samples=args.skip_samples,
        skip_profile=args.skip_profile,
        recreate_collection=args.recreate,
    )
    if args.out_dir:
        cfg.out_dir = Path(args.out_dir)

    report = run_index(cfg)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
