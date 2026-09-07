"""What is wrong with a query that will run and return a number.

The checks before this one ask whether a query is *allowed* — SELECT only, catalog tables only,
names that resolve. They do not ask whether the number it returns is the number that was asked for,
and that is where the answers that cost the most come from: a join that repeats rows under a SUM
returns a total that is larger than the truth by a factor nobody sees, and a SUM over a code column
returns garbage that formats like money. The database accepts both.

So this reads the query the way a careful reviewer would, against what the catalog knows about the
tables in it, and says what it found. It never rewrites and never executes; what happens with a
finding is the caller's decision. And it fails open — a query it cannot parse gets no findings, not
a refusal, because a reviewer who cannot read the page has nothing to say about it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import sqlglot
from sqlglot import exp

from semantic_layer.models import SchemaProfile
from semantic_layer.naming import logical_table

_NUMERIC = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "money", "smallmoney", "double", "number")
_INFLATABLE = (exp.Sum, exp.Avg)   # COUNT(*) over a fan-out is also inflated; COUNT(DISTINCT) is not


@dataclass(frozen=True)
class Finding:
    kind: str          # FANOUT | NON_NUMERIC | UNKNOWN_COLUMN | UNKNOWN_JOIN
    severity: str      # block | warn
    message: str       # in the language the person asked in, usable as a repair instruction

    def to_dict(self) -> dict:
        return {"kind": self.kind, "severity": self.severity, "message": self.message}


def _profiles_by_name(profiles: list[SchemaProfile]) -> tuple[dict[str, SchemaProfile], dict[str, SchemaProfile]]:
    by_table: dict[str, SchemaProfile] = {}
    by_entity: dict[str, SchemaProfile] = {}
    for p in profiles:
        by_table[p.table_name.upper()] = p
        by_table[f"{p.schema_name}_{p.table_name}".upper()] = p
        by_table[f"{p.schema_name}.{p.table_name}".upper()] = p
        by_entity.setdefault(p.entity, p)
    return by_table, by_entity


def _resolve(node: exp.Table, by_table: dict, by_entity: dict) -> Optional[SchemaProfile]:
    raw = node.name
    key = ((node.db + "_") if node.db else "") + raw
    prof = by_table.get(key.upper()) or by_table.get(raw.upper())
    if prof is None:
        lt = logical_table(raw)
        prof = by_entity.get(lt.entity)
    return prof


def _is_pk(prof: SchemaProfile, column: str) -> bool:
    c = column.upper()
    if c in {k.upper() for k in prof.primary_key}:
        return True
    col = prof.column(column)
    return bool(col and col.is_primary_key)


def _is_numeric(prof: SchemaProfile, column: str) -> Optional[bool]:
    col = prof.column(column)
    if col is None or not col.data_type:
        return None
    return any(col.data_type.lower().startswith(t) for t in _NUMERIC)


def review(sql: str, profiles: list[SchemaProfile], dialect: str = "tsql") -> list[Finding]:
    """Findings about `sql`, most serious first. Empty when there is nothing to say or nothing to read."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001
        try:
            tree = sqlglot.parse_one(sql)
        except Exception:  # noqa: BLE001
            return []
    by_table, by_entity = _profiles_by_name(profiles)
    findings: list[Finding] = []

    for select in tree.find_all(exp.Select):
        # Which alias names which table, within this SELECT.
        tables: dict[str, SchemaProfile] = {}
        for t in select.find_all(exp.Table):
            prof = _resolve(t, by_table, by_entity)
            if prof is not None:
                tables[(t.alias or t.name).upper()] = prof
        if not tables:
            continue

        # Each join: which side keeps its rows and which side gets repeated. The side whose join
        # column is its own primary key matches at most one row per row of the other side, so the
        # other side's rows are preserved and *this* side's rows are repeated once per match.
        repeated: set[str] = set()           # aliases whose rows are multiplied by a join
        uncertain: set[str] = set()          # neither side keyed: could go either way
        for join in select.find_all(exp.Join):
            on = join.args.get("on")
            if on is None:
                continue
            for eq in on.find_all(exp.EQ):
                l, r = eq.left, eq.right
                if not (isinstance(l, exp.Column) and isinstance(r, exp.Column)):
                    continue
                la, ra = (l.table or "").upper(), (r.table or "").upper()
                lp, rp = tables.get(la), tables.get(ra)
                if lp is None or rp is None or la == ra:
                    continue
                lk, rk = _is_pk(lp, l.name), _is_pk(rp, r.name)
                if lk and not rk:
                    repeated.add(la)
                elif rk and not lk:
                    repeated.add(ra)
                elif not lk and not rk:
                    uncertain.update({la, ra})
                # A join the catalog has no relationship for — only said where the catalog has
                # relationships for these tables at all, so a graph still being filled in stays quiet.
                known = [(x["column"].upper(), x["ref_entity"], (x.get("ref_column") or "").upper())
                         for x in (lp.relationships or []) + (rp.relationships or [])]
                if known:
                    pairs = {(l.name.upper(), rp.entity, r.name.upper()), (r.name.upper(), lp.entity, l.name.upper())}
                    if not any((c, e, rc) in pairs or (c, e) in {(a, b) for a, b, _ in pairs} for c, e, rc in known):
                        findings.append(Finding("UNKNOWN_JOIN", "warn",
                            f"{lp.entity}.{l.name} = {rp.entity}.{r.name} bağlantısı katalogdaki ilişkilerde yok; "
                            f"bu iki tablo bu kolonlar üzerinden birleşmeyebilir."))

        for agg in select.find_all(exp.AggFunc):
            inner = agg.this
            distinct = isinstance(inner, exp.Distinct)
            if distinct:
                continue                       # COUNT(DISTINCT x) / SUM(DISTINCT x) survive a fan-out
            cols = list(inner.find_all(exp.Column)) if isinstance(inner, exp.Expression) else []
            if isinstance(agg, _INFLATABLE) or (isinstance(agg, exp.Count) and not cols):
                # COUNT(*) has no column: inflated whenever any table in the SELECT is repeated.
                hit = [c for c in cols if (c.table or "").upper() in repeated] if cols else \
                      ([None] if isinstance(agg, exp.Count) and repeated else [])
                if hit:
                    aliases = ({(c.table or "").upper() for c in cols if c is not None} & repeated) or repeated
                    who = ", ".join(sorted(tables[a].entity for a in aliases if a in tables))
                    findings.append(Finding("FANOUT", "block",
                        f"{agg.sql(dialect=dialect)} şişirilmiş: {who} tablosunun satırları join yüzünden "
                        f"tekrarlanıyor ve toplama her tekrarı bir daha sayıyor. Toplamı tekrarlanmayan tarafta al, "
                        f"ya da önce alt sorguda tekilleştir."))
                elif cols and any((c.table or "").upper() in uncertain for c in cols):
                    findings.append(Finding("FANOUT", "warn",
                        f"{agg.sql(dialect=dialect)}: join'in iki tarafı da anahtar değil; satırlar çoğalıyor olabilir."))
            if isinstance(agg, (exp.Sum, exp.Avg)):
                for c in cols:
                    prof = tables.get((c.table or "").upper()) if c.table else (next(iter(tables.values())) if len(tables) == 1 else None)
                    if prof is None:
                        continue
                    num = _is_numeric(prof, c.name)
                    if num is False:
                        findings.append(Finding("NON_NUMERIC", "block",
                            f"{agg.sql(dialect=dialect)}: {prof.entity}.{c.name} sayısal değil "
                            f"({prof.column(c.name).data_type}); bu kolon toplanamaz."))

        # A column the catalog says the table does not have.
        for c in select.find_all(exp.Column):
            if not c.table:
                continue
            prof = tables.get(c.table.upper())
            if prof is None or not prof.columns or c.name == "*":
                continue
            if prof.column(c.name) is None:
                findings.append(Finding("UNKNOWN_COLUMN", "block",
                    f"{prof.entity} tablosunda {c.name} adında kolon yok."))

    order = {"block": 0, "warn": 1}
    seen: set[tuple] = set()
    out = []
    for f in sorted(findings, key=lambda f: order[f.severity]):
        if (f.kind, f.message) not in seen:
            seen.add((f.kind, f.message))
            out.append(f)
    return out
