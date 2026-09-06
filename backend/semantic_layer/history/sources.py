"""Validated Q→SQL sources: the knowledge pack (pairs-export.yml, knowledge/sql/*.md) and the runtime query log.

These are plain files owned by the product — a pack can be exported from the catalog itself
(`semantic_layer.cli export-knowledge`), so no third-party project layout is required."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from semantic_layer.models import ValidatedPair
from semantic_layer.normalize import normalize_term

_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)


def _pid(nl: str, sql: str) -> str:
    return "pair_" + hashlib.sha1((normalize_term(nl) + "\n" + " ".join(sql.split()).lower()).encode()).hexdigest()[:12]


def load_pairs_export(path: Path) -> list[ValidatedPair]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for p in data.get("pairs") or []:
        nl, sql = str(p.get("nl") or ""), str(p.get("sql") or "")
        if not nl or not sql:
            continue
        src = str(p.get("source") or "user")
        out.append(ValidatedPair(_pid(nl, sql), nl, sql, src, str(p.get("created_at") or ""), p.get("datasource"), weight=0.2 if src == "seed" else 1.0))
    return out


def load_knowledge_sql_dir(path: Path) -> list[ValidatedPair]:
    if not path.exists():
        return []
    out = []
    for f in sorted(path.glob("*.md")):
        m = _FRONT.match(f.read_text(encoding="utf-8"))
        if not m:
            continue
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except Exception:  # noqa: BLE001
            continue
        nl, sql = str(meta.get("nl") or ""), str(meta.get("sql") or "")
        if nl and sql:
            out.append(ValidatedPair(_pid(nl, sql), nl, sql, str(meta.get("source") or "user"), str(meta.get("created_at") or ""), meta.get("datasource")))
    return out


def load_query_log(rows: Iterable[dict[str, Any]]) -> list[ValidatedPair]:
    out = []
    for r in rows:
        nl, sql = str(r.get("question") or ""), str(r.get("sql_text") or "")
        if nl and sql:
            out.append(ValidatedPair(str(r.get("id") or _pid(nl, sql)), nl, sql, "runtime_validated", str(r.get("created_at") or ""), r.get("datasource_id")))
    return out


def dedupe(pairs: Iterable[ValidatedPair]) -> list[ValidatedPair]:
    seen: dict[str, ValidatedPair] = {}
    for p in pairs:
        key = _pid(p.nl, p.sql)
        if key not in seen or (seen[key].source == "seed" and p.source != "seed"):
            seen[key] = p
    return list(seen.values())


def load_project_pairs(project_dir: Optional[Path]) -> list[ValidatedPair]:
    if not project_dir:
        return []
    pairs = load_pairs_export(project_dir / "knowledge" / "pairs-export.yml")
    pairs += load_knowledge_sql_dir(project_dir / "knowledge" / "sql")
    return dedupe(pairs)


def export_pack(store, settings, out_dir: Path) -> dict[str, Any]:
    """Write a knowledge pack the product owns: every validated question→SQL pair the catalog knows
    (runtime-validated + previously imported) plus the operator documentation, in the plain layout the
    miner reads. After this the deployment no longer needs the directory it was bootstrapped from."""
    out_dir = Path(out_dir)
    (out_dir / "knowledge" / "sql").mkdir(parents=True, exist_ok=True)
    pairs = load_project_pairs(settings.project_dir)
    pairs += load_query_log(store.list_validated_queries(settings.tenant_id, settings.datasource_id))
    pairs = [p for p in dedupe(pairs) if p.source != "seed"]
    payload = {
        "version": 1,
        "datasource": settings.datasource_id,
        "pairs": [{"nl": p.nl, "sql": p.sql, "source": p.source, "created_at": p.created_at} for p in pairs],
    }
    (out_dir / "knowledge" / "pairs-export.yml").write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    copied = 0
    src = settings.project_dir / "knowledge" if settings.project_dir else None
    if src and src.exists():
        for f in sorted(src.rglob("*.md")):
            if f.parent.name == "sql":
                continue
            target = out_dir / "knowledge" / f.parent.name / f.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            copied += 1
    return {"out": str(out_dir), "pairs": len(pairs), "docs": copied}
