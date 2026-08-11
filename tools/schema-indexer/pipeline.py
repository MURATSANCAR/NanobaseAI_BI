from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from config import LEGACY_TABLES, IndexerConfig
from embedder import BgeM3Embedder
from models import ScanReport
from normalizer import normalize_documents
from qdrant_writer import QdrantWriter
from scanner import apply_controlled_profiling, scan_metadata


def run_index(cfg: IndexerConfig) -> ScanReport:
    """Full Schema Indexer pipeline with fingerprint skip + soft delete."""
    t0 = time.time()
    errors: list[str] = []

    from config import _reporting_datasource_id

    reporting_id = _reporting_datasource_id()
    ds = reporting_id if cfg.datasource_id == "nanobase_test" else cfg.datasource_id
    cfg.datasource_id = ds
    collection = cfg.resolved_collection()

    tables, relationships = scan_metadata(cfg)
    legacy = LEGACY_TABLES.get(ds) or frozenset()
    if legacy:
        tables = [t for t in tables if (t.schema_name, t.table_name) not in legacy]
        relationships = [
            r
            for r in relationships
            if (r.from_schema, r.from_table) not in legacy
            and (r.to_schema, r.to_table) not in legacy
        ]
    tables = apply_controlled_profiling(cfg, tables)
    docs = normalize_documents(ds, tables, relationships)

    writer = QdrantWriter(cfg.qdrant_url, collection, cfg.vector_size)
    writer.ensure_collection(recreate=cfg.recreate_collection)

    existing_fp = {} if cfg.recreate_collection else writer.existing_fingerprints(ds)
    to_embed = []
    skipped = 0
    for doc in docs:
        if existing_fp.get(doc.document_key) == doc.fingerprint:
            skipped += 1
        else:
            to_embed.append(doc)

    embedded = 0
    upserted = 0
    if to_embed:
        embedder = BgeM3Embedder(cfg.embed_url, batch_size=cfg.embed_batch)
        vectors = embedder.embed([d.text for d in to_embed])
        if vectors and len(vectors[0]) != cfg.vector_size:
            raise SystemExit(f"vector dim {len(vectors[0])} != {cfg.vector_size}")
        embedded = len(vectors)
        upserted = writer.upsert(to_embed, vectors)

    current_keys = {d.document_key for d in docs}
    existing_ids = {} if cfg.recreate_collection else writer.existing_point_ids(ds)
    stale = [k for k in existing_ids if k not in current_keys]
    soft_deleted = writer.delete_keys(stale) if stale else 0

    report = ScanReport(
        datasource_id=ds,
        collection=collection,
        schemas=list(cfg.schemas),
        tables_scanned=len(tables),
        documents_total=len(docs),
        embedded=embedded,
        skipped_unchanged=skipped,
        upserted=upserted,
        soft_deleted=soft_deleted,
        elapsed_s=round(time.time() - t0, 2),
        points_count=writer.points_count(),
        sample_docs=[d.to_dict() for d in docs[:3]],
        errors=errors,
    )

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.out_dir / f"schema-index-{ds}.json"
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **report.to_dict(),
        "document_type_counts": {
            "TABLE": sum(1 for d in docs if d.document_type == "TABLE"),
            "COLUMN": sum(1 for d in docs if d.document_type == "COLUMN"),
            "RELATIONSHIP": sum(1 for d in docs if d.document_type == "RELATIONSHIP"),
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if ds == reporting_id:
        (cfg.out_dir / "phase-2-schema-index.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        f"[schema-indexer] ds={ds} tables={report.tables_scanned} docs={report.documents_total} "
        f"embed={embedded} skip={skipped} delete={soft_deleted} "
        f"points={report.points_count} → {path}"
    )
    return report
