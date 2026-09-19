"""Which period a source copy holds — declared by a person, contested by the data, never inferred.

A period-partitioned source keeps one copy of its tables per fiscal period, and the copy's name says
nothing the system may trust about the period (`00-source-topology.md`). The measured min/max of a
date column says even less: on this deployment the 2026 line table runs to 2027-03-23 (two forward-
dated rows) and the 2021–2025 one to 2030-03-20 (seventy). A gate that read those as coverage would
call an unfiltered 2026 query proven for 2027.

So coverage is a **declaration** in the knowledge pack (`coverage.yml`): which placeholder context
holds which half-open range, who said so and why. The nightly job then tries to refute it: it counts
the rows whose business date falls outside the declared range. Zero rows → `declared`, and the gate
lets a query on that table answer for its period without a date filter. Any rows → `contested`: the
declaration stands as a claim, the filter stays required, and the count is shown to the person who
can clean the rows or fix the claim.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_layer.models import SchemaProfile
from semantic_layer.store import schema as S

log = logging.getLogger(__name__)

DECLARED, CONTESTED, UNMEASURED = "declared", "contested", "unmeasured"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_table(engine: sa.Engine) -> None:
    S.sl_coverage.create(engine, checkfirst=True)


# --------------------------------------------------------------------------- the declaration

def load_rules(path: Path) -> list[dict[str, Any]]:
    """`coverage.yml` → validated rules. A rule names a placeholder context (`{n0: "411"}`) or one
    table, a half-open date range, the person and the reason. Two rules that overlap on the same
    context are a mistake in the file, not a choice for the code."""
    if not path.exists():
        return []
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules: list[dict[str, Any]] = []
    for i, raw in enumerate(data.get("coverage") or []):
        if not isinstance(raw, dict):
            raise ValueError(f"coverage[{i}]: sözlük bekleniyor")
        if not (raw.get("context") or raw.get("table")):
            raise ValueError(f"coverage[{i}]: context ya da table gerekli")
        try:
            start, end = date.fromisoformat(str(raw["from"])), date.fromisoformat(str(raw["to"]))
        except (KeyError, ValueError) as e:
            raise ValueError(f"coverage[{i}]: from/to ISO tarih olmalı ({e})")
        if start >= end:
            raise ValueError(f"coverage[{i}]: from < to olmalı ([from, to) yarı açık)")
        if not raw.get("verified_by") or not raw.get("reason"):
            raise ValueError(f"coverage[{i}]: verified_by ve reason zorunlu — beyan sahipsiz olamaz")
        rules.append({"context": {str(k): str(v) for k, v in (raw.get("context") or {}).items()},
                      "table": str(raw.get("table") or "").upper() or None,
                      "entities": [str(e).upper() for e in (raw.get("entities") or [])],
                      "from": start, "to": end, "verified_by": str(raw["verified_by"]), "reason": str(raw["reason"])})
    for a in rules:
        for b in rules:
            if a is b or a["table"] != b["table"] or a["context"] != b["context"]:
                continue
            if set(a["entities"]) & set(b["entities"]) or not a["entities"] or not b["entities"]:
                if a["from"] < b["to"] and b["from"] < a["to"] and a is not b and rules.index(a) < rules.index(b):
                    raise ValueError(f"coverage: {a['context'] or a['table']} için örtüşen iki beyan")
    return rules


def rule_for(profile: SchemaProfile, rules: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The declaration that names this table: by exact name, else by every placeholder value in its
    pattern context matching the rule's."""
    name = profile.table_name.upper()
    ctx = {str(k): str(v) for k, v in (getattr(profile, "context", None) or {}).items()}
    for r in rules:
        if r["table"] and r["table"] == name:
            return r
    for r in rules:
        if r["table"] or not r["context"]:
            continue
        if r["entities"] and profile.entity.upper() not in r["entities"]:
            continue
        if all(ctx.get(k) == v for k, v in r["context"].items()):
            return r
    return None


# --------------------------------------------------------------------------- refutation

def measure_spill(connector, profile: SchemaProfile, column: str, start: date, end: date) -> Optional[int]:
    """Rows whose business date lies outside [start, end). None when the source cannot be asked."""
    if connector is None or not getattr(connector, "supports_execution", False):
        return None
    q = connector.q
    target = f"{q(profile.schema_name)}.{q(profile.table_name)}" if profile.schema_name and getattr(connector, "dialect", "") != "sqlite" else q(profile.table_name)
    sql = f"SELECT COUNT(*) AS n FROM {target} WHERE {q(column)} < '{start.isoformat()}' OR {q(column)} >= '{end.isoformat()}'"
    _, rows, _ = connector.execute(sql, 1)
    if not rows:
        return None
    value = next(iter(rows[0].values()))
    return int(value or 0)


def refresh(store, settings, profiles: Iterable[SchemaProfile], rules: list[dict[str, Any]], connector, conventions,
            *, entities: Optional[Iterable[str]] = None) -> dict[str, Any]:
    """Re-measure every declared table and record the verdict. Cheap on a table without a
    declaration: it is skipped, and nothing about it is assumed. `entities` narrows the work to the
    tables the catalog can actually answer from — a context rule names a whole firm's copy, and
    counting rows in every report view of it buys nothing."""
    ensure_table(store.engine)
    now = _now()
    wanted = {e.upper() for e in entities} if entities is not None else None
    out = {"declared": 0, "contested": 0, "unmeasured": 0, "skipped": 0, "rows": []}
    with store.engine.begin() as conn:
        for p in profiles:
            r = rule_for(p, rules)
            if r is None or (wanted is not None and p.entity.upper() not in wanted) or getattr(p, "row_count", None) is None:
                out["skipped"] += 1        # undeclared, out of the catalog's reach, or a view (no row count)
                continue
            column = conventions.time_column(p.entity) if conventions is not None else None
            spill: Optional[int] = None
            if column and p.column(column) is not None:
                try:
                    spill = measure_spill(connector, p, column, r["from"], r["to"])
                except Exception as e:  # noqa: BLE001
                    log.warning("coverage: %s ölçülemedi: %s", p.table_name, e)
            status = UNMEASURED if spill is None else (DECLARED if spill == 0 else CONTESTED)
            out[status] += 1
            row = dict(tenant_id=settings.tenant_id, datasource_id=settings.datasource_id, table_name=p.table_name.upper(), entity=p.entity,
                       time_column=column, declared_from=r["from"].isoformat(), declared_to=r["to"].isoformat(), spill=spill, status=status,
                       verified_by=r["verified_by"], reason=r["reason"], measured_at=now if spill is not None else None, updated_at=now)
            existing = conn.execute(sa.select(S.sl_coverage.c.id).where(S.sl_coverage.c.tenant_id == settings.tenant_id,
                                                                        S.sl_coverage.c.datasource_id == settings.datasource_id,
                                                                        S.sl_coverage.c.table_name == p.table_name.upper())).first()
            if existing:
                conn.execute(S.sl_coverage.update().where(S.sl_coverage.c.id == existing[0]).values(**row))
            else:
                conn.execute(S.sl_coverage.insert().values(id=uuid.uuid4().hex, **row))
            out["rows"].append({"table": p.table_name, "entity": p.entity, "column": column, "from": row["declared_from"], "to": row["declared_to"], "spill": spill, "status": status})
    return out


def statuses(store, settings) -> dict[str, dict[str, Any]]:
    ensure_table(store.engine)
    stmt = sa.select(S.sl_coverage).where(S.sl_coverage.c.tenant_id == settings.tenant_id, S.sl_coverage.c.datasource_id == settings.datasource_id)
    with store.engine.connect() as conn:
        return {r.table_name.upper(): dict(r._mapping) for r in conn.execute(stmt)}


def apply(profiles: Iterable[SchemaProfile], store, settings) -> int:
    """Hand each profile its verdict: `declared_window` is set only on a table whose declaration the
    data did not refute. The period chooser and the gate read that attribute and nothing else."""
    if store is None:
        return 0
    try:
        verdicts = statuses(store, settings)
    except Exception as e:  # noqa: BLE001
        log.warning("coverage: durumlar okunamadı: %s", e)
        return 0
    n = 0
    for p in profiles:
        v = verdicts.get(p.table_name.upper())
        if v and v["status"] == DECLARED:
            p.declared_window = (v["declared_from"], v["declared_to"])
            n += 1
        else:
            p.declared_window = None
    return n


__all__ = ["load_rules", "rule_for", "measure_spill", "refresh", "statuses", "apply", "ensure_table", "DECLARED", "CONTESTED", "UNMEASURED"]
