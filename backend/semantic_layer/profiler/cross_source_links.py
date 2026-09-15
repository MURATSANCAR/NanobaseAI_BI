"""Join relationships between two databases that share nothing but values.

The ERP and the CRM sit on the same server, but neither declares a foreign key into the other and
neither names its columns after the other's. What ties a CRM account to an ERP customer card is that
one column of the first holds the key values of the second. That is the only thing looked at here:

    1. catalog   — which column pairs could hold the same values at all (types, key-ness, value
                   inventories the scan already collected). No SQL. Counted, never truncated.
    2. sample    — one cheap sampled read per table gives each column a value profile: its family
                   (integer / code / guid), the *shape* of its values (``TIM2020000010552`` →
                   ``AAA9999999999999``) and its range. Pairs whose shapes or ranges cannot meet are
                   dropped here, with the reason kept.
    3. contain   — the sampled values of the referencing column are looked up in the key column of
                   every period table of the target shape. What fraction was found, and in which
                   period, is the first real evidence.
    4. corroborate — an integer key is a counter: 1..350.000 is "contained" in every large table's
                   key. So a pair of rows joined through the candidate must also agree on something
                   else (a name, a code) before an integer link is believed. A code or guid is its
                   own proof and is only corroborated when more than one target competes for it.
    5. confirm   — for what survives, the full distinct coverage is measured once, per period table,
                   with the referencing side's own time column used to tell "outside the target's
                   window" apart from "does not match".

Nothing in this module knows a table or a column name. Every threshold is a named parameter of
:class:`LinkThresholds`, and every link carries the numbers it was accepted on.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Protocol

from semantic_layer.models import ColumnProfile, SchemaProfile

log = logging.getLogger(__name__)

INT, CODE, GUID = "int", "code", "guid"
LINK_SOURCE = "cross-source-overlap"

_INT_TYPES = ("bigint", "int", "smallint")          # tinyint cannot be a key of anything worth joining
_TEXT_TYPES = ("char", "varchar", "nchar", "nvarchar", "text", "string")
_GUID_TYPES = ("uniqueidentifier", "uuid")
_EXCLUDED_TYPES = ("date", "time", "bit", "bool", "float", "real", "decimal", "numeric", "money",
                   "binary", "image", "xml", "geography", "geometry", "hierarchyid", "tinyint", "ntext")
_GUID_RE = re.compile(r"^\{?[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}?$")
_INT_RE = re.compile(r"^-?\d{1,18}$")
_SCOPE_MAX_DISTINCT = 64                      # same bound conventions.py uses for a business type code


# ------------------------------------------------------------------------------------------ parameters

@dataclass(frozen=True)
class LinkThresholds:
    """Every number a decision is made on. Defaults are justified in the discovery report."""

    sample_rows: int = 2000              # rows read per table for value profiles (TABLESAMPLE)
    sample_values: int = 200             # distinct values per column kept for probing
    min_distinct: int = 20               # a column showing fewer distinct values cannot be tested
    code_mask_diversity: float = 0.5     # distinct shapes / distinct values at most this → identifier
    max_space_share: float = 0.2         # values with inner whitespace: names/sentences, not codes
    key_sample_uniqueness: float = 0.95  # a non-declared key column must look unique in its sample
    shape_overlap: float = 0.5           # share of referencing values whose shape the key also shows
    sample_containment: float = 0.5      # share of sampled values found in the target (step 3)
    corroboration_rate: float = 0.6      # joined rows agreeing on some other attribute (step 4)
    corroboration_min_pairs: int = 20    # compared row pairs needed for that rate to mean anything
    confirmed_coverage: float = 0.9      # full distinct coverage inside the target's window (step 5)
    min_matched: int = 50                # matched distinct values needed to accept at all
    int_lift: float = 0.1                # containment must beat the key's density by this much


# ------------------------------------------------------------------------------------------ helpers

def source_of(schema_name: Optional[str]) -> str:
    """Which database a profile lives in: the qualifier before the schema, or the connection's own.

    ``Timas_MSCRM.dbo`` → ``TIMAS_MSCRM``; ``dbo`` → ``""`` (the default database). Two profiles are
    from different sources exactly when these differ — no product name is involved.
    """
    parts = [p for p in (schema_name or "").split(".") if p]
    return parts[0].upper() if len(parts) >= 2 else ""


def declared_family(data_type: str) -> Optional[str]:
    t = (data_type or "").lower()
    if any(x in t for x in _GUID_TYPES):
        return GUID
    if any(t.startswith(x) for x in _EXCLUDED_TYPES):
        return None
    base = t.split("(")[0].strip()
    if base in _INT_TYPES:
        return INT
    if base in _TEXT_TYPES or base.endswith("char"):
        return "text"
    return None


def value_mask(value: str) -> str:
    """The shape of a value: digits → 9, letters → A (any alphabet), everything else kept."""
    out = []
    for ch in value:
        if ch.isdigit():
            out.append("9")
        elif ch.isalpha():
            out.append("A")
        else:
            out.append(ch)
    return "".join(out)


def fold(value: Any) -> str:
    """Comparison form: trimmed, case- and accent-insensitive (the CRM compares that way itself)."""
    s = unicodedata.normalize("NFKD", str(value).strip().casefold())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.replace("ı", "i")


def _clean(values: Iterable[Any]) -> list[str]:
    out = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s and s.upper() not in ("NULL",):
            out.append(s)
    return out


@dataclass
class ValueProfile:
    """What a sample says about one column."""

    family: Optional[str]                # int | code | guid | None (not an identifier)
    distinct: int = 0
    rows: int = 0
    values: list[str] = field(default_factory=list)
    masks: dict[str, int] = field(default_factory=dict)
    vmin: Optional[int] = None
    vmax: Optional[int] = None
    uniqueness: float = 0.0              # distinct / non-null rows in the sample
    reason: str = ""


def profile_values(raw: list[Any], declared: Optional[str], th: LinkThresholds) -> ValueProfile:
    vals = _clean(raw)
    distinct = sorted(set(vals))
    vp = ValueProfile(family=None, distinct=len(distinct), rows=len(vals),
                      uniqueness=(len(distinct) / len(vals)) if vals else 0.0)
    if declared is None:
        vp.reason = "type"
        return vp
    if len(distinct) < th.min_distinct:
        vp.reason = f"distinct<{th.min_distinct}"
        return vp
    if all(_INT_RE.match(v) for v in distinct) and all(v == "0" or not v.lstrip("-").startswith("0") for v in distinct):
        nums = [int(v) for v in distinct]
        vp.family, vp.vmin, vp.vmax = INT, min(nums), max(nums)
        # Leading zeros are a code ("00123"), not a counter; negative or zero values are sentinels.
        keep = [str(n) for n in sorted(nums) if n > 0]
        vp.values = _spread(keep, th.sample_values)
        if len(keep) < th.min_distinct:
            vp.family, vp.reason = None, "positive-distinct<min"
        return vp
    if declared == GUID or all(_GUID_RE.match(v) for v in distinct):
        vp.family = GUID
        vp.values = _spread([v.strip("{}").upper() for v in distinct], th.sample_values)
        return vp
    masks = Counter(value_mask(v) for v in distinct)
    spaces = sum(1 for v in distinct if re.search(r"\S\s+\S", v)) / len(distinct)
    diversity = len(masks) / len(distinct)
    vp.masks = dict(masks)
    if spaces > th.max_space_share:
        vp.reason = f"free text (spaces {spaces:.2f})"
        return vp
    if diversity > th.code_mask_diversity:
        vp.reason = f"shape diversity {diversity:.2f}"
        return vp
    if not any(ch.isdigit() for v in distinct for ch in v):
        vp.reason = "no digits"             # a word list, not an identifier
        return vp
    vp.family = CODE
    vp.values = _spread(distinct, th.sample_values)
    return vp


def _spread(values: list[str], n: int) -> list[str]:
    """`n` values spread evenly over a sorted list — the whole range, not its first page."""
    if len(values) <= n:
        return list(values)
    step = len(values) / n
    return [values[int(i * step)] for i in range(n)]


# ------------------------------------------------------------------------------------------ shapes

@dataclass
class Shape:
    """One logical table: every physical copy (period, firm) of a pattern in one schema."""

    source: str
    schema_name: str
    pattern: str
    entity: str
    tables: list[SchemaProfile]

    @property
    def key(self) -> str:
        return f"{self.schema_name}|{self.pattern}"

    def representative(self) -> SchemaProfile:
        """The copy to read value profiles from: the newest measured window, then the largest."""
        return max(self.tables, key=lambda p: (str(p.time_window[1]) if p.time_window else "",
                                               p.row_count or 0, p.table_name))

    def is_periodic(self) -> bool:
        """Copies that each hold a different stretch of time (not copies of the same rows)."""
        windows = sorted((str(p.time_window[0])[:10], str(p.time_window[1])[:10])
                         for p in self.tables if p.time_window)
        if len(self.tables) < 2 or len(windows) < len(self.tables):
            return False
        return all(windows[i][1] <= windows[i + 1][0] for i in range(len(windows) - 1))


def shapes_of(profiles: Iterable[SchemaProfile]) -> list[Shape]:
    groups: dict[tuple[str, str], list[SchemaProfile]] = {}
    for p in profiles:
        groups.setdefault((p.schema_name or "", p.table_pattern), []).append(p)
    out = []
    for (schema, pattern), tables in sorted(groups.items()):
        out.append(Shape(source_of(schema), schema, pattern, tables[0].entity, sorted(tables, key=lambda t: t.table_name)))
    return out


def _is_enum(col: ColumnProfile) -> bool:
    return bool(col.top_values) and col.distinct_count is not None and col.distinct_count <= _SCOPE_MAX_DISTINCT \
        and len(col.top_values) >= (col.distinct_count or 0)


def referencing_columns(shape: Shape) -> list[ColumnProfile]:
    """Columns of a shape that could hold another table's key: identifier types, not personal data,
    not a type code, not this table's own single-column key."""
    rep = shape.representative()
    own_key = {k.upper() for k in rep.primary_key} if len(rep.primary_key) == 1 else set()
    out = []
    for c in rep.columns:
        if c.sensitive or c.name.upper() in own_key or declared_family(c.data_type) is None or _is_enum(c):
            continue
        out.append(c)
    return out


def key_columns(shape: Shape) -> list[ColumnProfile]:
    """Columns a reference could point at: the declared single-column key, and any other identifier-
    typed column (its uniqueness is measured from the sample before it is used)."""
    rep = shape.representative()
    out = []
    for c in rep.columns:
        if c.sensitive or declared_family(c.data_type) is None or _is_enum(c):
            continue
        out.append(c)
    return out


def is_declared_key(shape: Shape, column: str) -> bool:
    rep = shape.representative()
    return len(rep.primary_key) == 1 and rep.primary_key[0].upper() == column.upper()


def _compatible(ref_type: str, key_type: str) -> bool:
    a, b = declared_family(ref_type), declared_family(key_type)
    if a is None or b is None:
        return False
    if GUID in (a, b):
        return a == b or "text" in (a, b)
    return True                              # int ↔ int, int ↔ text (digits stored as text), text ↔ text


def _catalog_overlap(ref: ColumnProfile, key: ColumnProfile) -> Optional[float]:
    """Share of the referencing column's scanned values also scanned on the key side, when both
    inventories exist. Inventories are top-N lists, so a low figure means nothing; a high one is a hint."""
    if not ref.top_values or not key.top_values:
        return None
    a = {fold(v) for v, _ in ref.top_values}
    b = {fold(v) for v, _ in key.top_values}
    return len(a & b) / len(a) if a else None


@dataclass
class CatalogCandidates:
    shapes_by_source: dict[str, int]
    referencing: int
    keys: int
    pairs: int                                   # type-compatible pairs across sources, both directions
    pairs_by_direction: dict[str, int]
    catalog_value_hints: list[dict[str, Any]]    # pairs whose scanned inventories already overlap


def catalog_candidates(profiles: list[SchemaProfile]) -> CatalogCandidates:
    """Step 1 — from the catalog alone. Counts every type-compatible pair; drops nothing silently."""
    shapes = shapes_of(profiles)
    by_source = Counter(s.source for s in shapes)
    refs = {s.key: referencing_columns(s) for s in shapes}
    keys = {s.key: key_columns(s) for s in shapes}
    pairs = 0
    by_dir: Counter = Counter()
    hints = []
    type_buckets: dict[tuple[str, str], int] = Counter()
    for s in shapes:
        for k in keys[s.key]:
            type_buckets[(s.source, declared_family(k.data_type) or "")] += 1
    for s in shapes:
        for r in refs[s.key]:
            rf = declared_family(r.data_type)
            for (src, kf), n in type_buckets.items():
                if src == s.source:
                    continue
                if (GUID in (rf, kf) and rf != kf and "text" not in (rf, kf)):
                    continue
                pairs += n
                by_dir[f"{s.source or 'default'}->{src or 'default'}"] += n
    # Inventory overlap is cheap to compute only where both lists exist; it is reported as a hint.
    inv_keys = [(s, k) for s in shapes for k in keys[s.key] if k.top_values]
    for s in shapes:
        for r in refs[s.key]:
            if not r.top_values:
                continue
            for t, k in inv_keys:
                if t.source == s.source or not _compatible(r.data_type, k.data_type):
                    continue
                ov = _catalog_overlap(r, k)
                if ov and ov >= 0.5:
                    hints.append({"ref": f"{s.entity}.{r.name}", "key": f"{t.entity}.{k.name}", "overlap": round(ov, 3)})
    return CatalogCandidates(dict(by_source), sum(len(v) for v in refs.values()), sum(len(v) for v in keys.values()),
                             pairs, dict(by_dir), hints)


# ------------------------------------------------------------------------------------------ probing

class LinkProbe(Protocol):
    """The SQL this discovery needs. One implementation per dialect; tests use SQLite."""

    def sample(self, table: SchemaProfile, columns: list[str], rows: int) -> list[dict[str, Any]]: ...
    def key_range(self, table: SchemaProfile, column: str) -> tuple[Optional[int], Optional[int]]: ...
    def contained(self, table: SchemaProfile, column: str, values: list[str], family: str) -> set[str]: ...
    def rows_by(self, table: SchemaProfile, column: str, values: list[str], family: str,
                columns: list[str]) -> list[dict[str, Any]]: ...
    def coverage(self, ref: SchemaProfile, column: str, family: str, targets: list[SchemaProfile],
                 key: str, since: Optional[tuple[str, str]]) -> dict[str, Any]: ...
    def key_uniqueness(self, table: SchemaProfile, column: str) -> tuple[int, int]: ...


def _lit(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


class _SqlProbe:
    family_sql = "tsql"

    def __init__(self, connector: Any, *, timeout: Optional[int] = None):
        self.c = connector
        self.queries = 0
        self.seconds = 0.0
        if timeout and hasattr(connector, "query_timeout"):
            connector.query_timeout = timeout
            if getattr(connector, "_conn", None) is not None:
                connector._conn.timeout = timeout

    # -- dialect bits
    def q(self, ident: str) -> str:
        return f"[{ident}]"

    def table(self, p: SchemaProfile) -> str:
        parts = [x for x in (p.schema_name or "").split(".") if x]
        return ".".join(self.q(x) for x in parts + [p.table_name])

    hint = " OPTION (MAXDOP 1)"

    def run(self, sql: str, limit: int = 1_000_000) -> list[dict[str, Any]]:
        t = time.monotonic()
        try:
            _, rows, _ = self.c.execute(sql, limit)
        finally:
            self.queries += 1
            self.seconds += time.monotonic() - t
        return rows

    def as_text(self, expr: str) -> str:
        return f"CAST({expr} AS nvarchar(450))"

    def sample(self, table, columns, rows):
        cols = ", ".join(f"{self.as_text(self.q(c))} AS {self.q(c)}" for c in columns)
        n = table.row_count or 0
        if n > rows * 5:
            pct = max(0.01, min(100.0, rows * 150.0 / n))    # pages are uneven: over-read, TOP trims
            sql = f"SELECT TOP ({rows}) {cols} FROM {self.table(table)} TABLESAMPLE SYSTEM ({pct:.4f} PERCENT){self.hint}"
            try:
                got = self.run(sql, rows)
                if len(got) >= min(rows, n) // 4:
                    return got
            except Exception as e:  # noqa: BLE001 - a view cannot be table-sampled
                log.debug("tablesample failed on %s: %s", table.table_name, e)
        return self.run(f"SELECT TOP ({rows}) {cols} FROM {self.table(table)}{self.hint}", rows)

    def key_range(self, table, column):
        rows = self.run(f"SELECT MIN({self.q(column)}) AS mn, MAX({self.q(column)}) AS mx FROM {self.table(table)}{self.hint}", 1)
        if not rows:
            return None, None
        mn, mx = rows[0].get("mn"), rows[0].get("mx")
        return (int(mn) if mn is not None else None), (int(mx) if mx is not None else None)

    def _in_list(self, values: list[str], family: str) -> str:
        if family == INT:
            return ", ".join(str(int(v)) for v in values)
        return ", ".join(_lit(v) for v in values)

    def contained(self, table, column, values, family):
        found: set[str] = set()
        for i in range(0, len(values), 500):
            chunk = values[i:i + 500]
            rows = self.run(f"SELECT DISTINCT {self.as_text(self.q(column))} AS v FROM {self.table(table)} "
                            f"WHERE {self.q(column)} IN ({self._in_list(chunk, family)}){self.hint}")
            found.update(fold(r["v"]) for r in rows if r.get("v") is not None)
        return found

    def rows_by(self, table, column, values, family, columns):
        cols = ", ".join(f"{self.as_text(self.q(c))} AS {self.q(c)}" for c in dict.fromkeys([column] + columns))
        out: list[dict[str, Any]] = []
        for i in range(0, len(values), 500):
            chunk = values[i:i + 500]
            out += self.run(f"SELECT {cols} FROM {self.table(table)} WHERE {self.q(column)} IN ({self._in_list(chunk, family)}){self.hint}")
        return out

    def _ref_value(self, column: str, family: str) -> str:
        if family == INT:
            return f"TRY_CAST({self.q(column)} AS bigint)"
        # Two databases, two collations: comparing across them is an error unless one side names one.
        return f"{self.as_text(self.q(column))} COLLATE DATABASE_DEFAULT"

    def coverage(self, ref, column, family, targets, key, since):
        where = f"{self.q(column)} IS NOT NULL"
        if since:
            where += f" AND {self.q(since[0])} >= '{since[1]}'"
        flags = []
        for i, t in enumerate(targets):
            flags.append(f"CASE WHEN EXISTS (SELECT 1 FROM {self.table(t)} k WHERE k.{self.q(key)} = s.v) THEN 1 ELSE 0 END AS h{i}")
        hs = [f"h{i}" for i in range(len(targets))]
        total = " + ".join(hs)
        sql = (f"WITH s AS (SELECT DISTINCT {self._ref_value(column, family)} AS v FROM {self.table(ref)} WHERE {where}), "
               f"f AS (SELECT {', '.join(flags)} FROM s WHERE s.v IS NOT NULL) "
               f"SELECT COUNT(*) AS total, " + ", ".join(f"SUM({h}) AS {h}" for h in hs)
               + f", SUM(CASE WHEN {total} > 0 THEN 1 ELSE 0 END) AS matched"
               + f", SUM(CASE WHEN {total} > 1 THEN 1 ELSE 0 END) AS multi FROM f{self.hint}")
        row = self.run(sql, 1)[0]
        rows = self.run(f"SELECT COUNT_BIG(*) AS n, COUNT(DISTINCT {self.q(column)}) AS d FROM {self.table(ref)} WHERE {where}{self.hint}", 1)[0]
        return {"distinct": int(row["total"] or 0), "matched": int(row["matched"] or 0), "multi_period": int(row["multi"] or 0),
                "per_table": {t.table_name: int(row[f"h{i}"] or 0) for i, t in enumerate(targets)},
                "ref_rows": int(rows["n"] or 0), "ref_distinct_raw": int(rows["d"] or 0)}

    def key_uniqueness(self, table, column):
        row = self.run(f"SELECT COUNT_BIG({self.q(column)}) AS n, COUNT(DISTINCT {self.q(column)}) AS d FROM {self.table(table)}{self.hint}", 1)[0]
        return int(row["n"] or 0), int(row["d"] or 0)


class TsqlLinkProbe(_SqlProbe):
    pass


class SqliteLinkProbe(_SqlProbe):
    """SQLite with the second database ATTACHed: ``schema_name`` is the attached name."""

    hint = ""

    def q(self, ident: str) -> str:
        return f'"{ident}"'

    def as_text(self, expr: str) -> str:
        return f"CAST({expr} AS TEXT)"

    def sample(self, table, columns, rows):
        cols = ", ".join(f"{self.as_text(self.q(c))} AS {self.q(c)}" for c in columns)
        return self.run(f"SELECT {cols} FROM {self.table(table)} ORDER BY random() LIMIT {int(rows)}", rows)

    def table(self, p):
        parts = [x for x in (p.schema_name or "").split(".") if x][:1]
        return ".".join(self.q(x) for x in parts + [p.table_name])

    def _ref_value(self, column, family):
        return f"CAST({self.q(column)} AS INTEGER)" if family == INT else f"{self.as_text(self.q(column))} COLLATE NOCASE"

    def coverage(self, ref, column, family, targets, key, since):
        where = f"{self.q(column)} IS NOT NULL"
        if since:
            where += f" AND {self.q(since[0])} >= '{since[1]}'"
        hs = []
        flags = []
        for i, t in enumerate(targets):
            flags.append(f"CASE WHEN EXISTS (SELECT 1 FROM {self.table(t)} k WHERE k.{self.q(key)} = s.v) THEN 1 ELSE 0 END AS h{i}")
            hs.append(f"h{i}")
        total = " + ".join(hs)
        sql = (f"WITH s AS (SELECT DISTINCT {self._ref_value(column, family)} AS v FROM {self.table(ref)} WHERE {where}), "
               f"f AS (SELECT {', '.join(flags)} FROM s WHERE s.v IS NOT NULL) "
               f"SELECT COUNT(*) AS total, " + ", ".join(f"SUM({h}) AS {h}" for h in hs)
               + f", SUM(CASE WHEN {total} > 0 THEN 1 ELSE 0 END) AS matched, SUM(CASE WHEN {total} > 1 THEN 1 ELSE 0 END) AS multi FROM f")
        row = self.run(sql, 1)[0]
        rows = self.run(f"SELECT COUNT(*) AS n, COUNT(DISTINCT {self.q(column)}) AS d FROM {self.table(ref)} WHERE {where}", 1)[0]
        return {"distinct": int(row["total"] or 0), "matched": int(row["matched"] or 0), "multi_period": int(row["multi"] or 0),
                "per_table": {t.table_name: int(row[f"h{i}"] or 0) for i, t in enumerate(targets)},
                "ref_rows": int(rows["n"] or 0), "ref_distinct_raw": int(rows["d"] or 0)}

    def key_uniqueness(self, table, column):
        row = self.run(f"SELECT COUNT({self.q(column)}) AS n, COUNT(DISTINCT {self.q(column)}) AS d FROM {self.table(table)}", 1)[0]
        return int(row["n"] or 0), int(row["d"] or 0)

    def contained(self, table, column, values, family):
        vals = self._in_list(values, family).replace("N'", "'")
        rows = self.run(f"SELECT DISTINCT {self.as_text(self.q(column))} AS v FROM {self.table(table)} WHERE {self.q(column)} IN ({vals})")
        return {fold(r["v"]) for r in rows if r.get("v") is not None}

    def rows_by(self, table, column, values, family, columns):
        cols = ", ".join(f"{self.as_text(self.q(c))} AS {self.q(c)}" for c in dict.fromkeys([column] + columns))
        vals = self._in_list(values, family).replace("N'", "'")
        return self.run(f"SELECT {cols} FROM {self.table(table)} WHERE {self.q(column)} IN ({vals})")


def probe_for(connector: Any, *, timeout: Optional[int] = None) -> _SqlProbe:
    dialect = getattr(connector, "dialect", "tsql")
    return SqliteLinkProbe(connector, timeout=timeout) if dialect == "sqlite" else TsqlLinkProbe(connector, timeout=timeout)


# ------------------------------------------------------------------------------------------ discovery

@dataclass
class ColumnSample:
    shape: str
    column: str
    declared: str
    profile: ValueProfile


@dataclass
class PairResult:
    ref_shape: str
    ref_entity: str
    ref_column: str
    key_shape: str
    key_entity: str
    key_column: str
    family: str
    stage: str                             # where it stopped: shape | contain | corroborate | confirm | accepted
    reason: str = ""
    shape_overlap: Optional[float] = None
    sample_size: int = 0
    sample_matched: int = 0
    sample_containment: Optional[float] = None
    sample_per_table: dict[str, int] = field(default_factory=dict)
    key_density: Optional[float] = None
    corroboration: Optional[dict[str, Any]] = None
    coverage: Optional[dict[str, Any]] = None
    key_uniqueness: Optional[dict[str, Any]] = None
    period_semantics: Optional[str] = None
    measured_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryReport:
    started_at: str
    finished_at: str = ""
    catalog: dict[str, Any] = field(default_factory=dict)
    sampled_tables: int = 0
    sample_failures: list[dict[str, str]] = field(default_factory=list)
    column_families: dict[str, int] = field(default_factory=dict)
    not_identifier: dict[str, int] = field(default_factory=dict)
    blocked: dict[str, int] = field(default_factory=dict)
    pairs: list[PairResult] = field(default_factory=list)
    queries: int = 0
    query_seconds: float = 0.0
    thresholds: dict[str, Any] = field(default_factory=dict)

    def accepted(self) -> list[PairResult]:
        return [p for p in self.pairs if p.stage == "accepted"]

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["accepted"] = [p.as_dict() for p in self.accepted()]
        return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lookup_family(ref: ColumnSample, key: ColumnSample) -> str:
    """How the two sides are compared: as integers only when both hold integers and the key is
    declared as one; otherwise as text, so a text key is never forced through a numeric conversion."""
    if ref.profile.family == INT and key.profile.family == INT and declared_family(key.declared) == INT:
        return INT
    return GUID if ref.profile.family == GUID else CODE


class CrossSourceLinkDiscovery:
    def __init__(self, profiles: list[SchemaProfile], probe: LinkProbe, *, thresholds: Optional[LinkThresholds] = None,
                 time_column: Optional[Callable[[SchemaProfile], Optional[str]]] = None,
                 progress: Optional[Callable[[str], None]] = None):
        self.profiles = profiles
        self.probe = probe
        self.th = thresholds or LinkThresholds()
        self.shapes = {s.key: s for s in shapes_of(profiles)}
        self.progress = progress or (lambda m: log.info(m))
        if time_column is None:
            from semantic_layer.conventions import Conventions
            conv = Conventions.from_profiles(profiles)
            time_column = lambda p: conv.time_column(p.entity)  # noqa: E731
        self.time_column = time_column
        self.samples: dict[tuple[str, str], ColumnSample] = {}
        self.ranges: dict[tuple[str, str], tuple[Optional[int], Optional[int]]] = {}
        self._ref_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}

    # -- step 2: value profiles
    def sample_all(self, report: DiscoveryReport) -> None:
        wanted: dict[str, dict[str, ColumnProfile]] = {}
        for s in self.shapes.values():
            cols = {c.name: c for c in referencing_columns(s)}
            cols.update({c.name: c for c in key_columns(s)})
            if cols and s.source in self._sources_with_partner():
                wanted[s.key] = cols
        for i, (key, cols) in enumerate(sorted(wanted.items())):
            shape = self.shapes[key]
            rep = shape.representative()
            try:
                rows = self.probe.sample(rep, list(cols), self.th.sample_rows)
            except Exception as e:  # noqa: BLE001
                report.sample_failures.append({"table": f"{rep.schema_name}.{rep.table_name}", "error": str(e)[:300]})
                continue
            report.sampled_tables += 1
            for name, col in cols.items():
                vp = profile_values([r.get(name) for r in rows], declared_family(col.data_type), self.th)
                self.samples[(key, name.upper())] = ColumnSample(key, name, col.data_type, vp)
                if vp.family:
                    report.column_families[vp.family] = report.column_families.get(vp.family, 0) + 1
                else:
                    bucket = vp.reason.split(" ")[0].split("<")[0] or "other"
                    report.not_identifier[bucket] = report.not_identifier.get(bucket, 0) + 1
            if (i + 1) % 100 == 0:
                self.progress(f"sampled {i + 1}/{len(wanted)} tables")

    def _sources_with_partner(self) -> set[str]:
        sources = {s.source for s in self.shapes.values()}
        return sources if len(sources) > 1 else set()

    # -- step 2b: blocking
    def _key_ok(self, shape: Shape, sample: ColumnSample) -> bool:
        if is_declared_key(shape, sample.column):
            return True
        return sample.profile.family != INT and sample.profile.uniqueness >= self.th.key_sample_uniqueness

    def blocked_pairs(self, report: DiscoveryReport) -> list[tuple[ColumnSample, ColumnSample]]:
        refs = [s for s in self.samples.values() if s.profile.family
                and not is_declared_key(self.shapes[s.shape], s.column)]
        keys = [s for s in self.samples.values() if s.profile.family and self._key_ok(self.shapes[s.shape], s)]
        by_family: dict[str, list[ColumnSample]] = {}
        for k in keys:
            by_family.setdefault(k.profile.family, []).append(k)
        out = []
        for r in refs:
            rs = self.shapes[r.shape]
            # Digits-only references can also sit in a code column that mixes digits and letters.
            partners = by_family.get(r.profile.family, []) + (by_family.get(CODE, []) if r.profile.family == INT else [])
            for k in partners:
                ks = self.shapes[k.shape]
                if ks.source == rs.source:
                    continue
                why = self._block(r, k, ks)
                if why:
                    report.blocked[why] = report.blocked.get(why, 0) + 1
                    continue
                out.append((r, k))
        return out

    def _block(self, r: ColumnSample, k: ColumnSample, ks: Shape) -> Optional[str]:
        fam = r.profile.family
        if fam == INT and k.profile.family == CODE:
            fam = CODE
        if fam == INT:
            # Only a declared single-column key is a counter something can point at.
            if not is_declared_key(ks, k.column):
                return "int: target not a declared key"
            lo, hi = self._range(ks, k.column)
            if lo is None or hi is None:
                return "int: empty key"
            if r.profile.vmax is not None and r.profile.vmax > hi:
                return "int: values above the key's range"
            return None
        if fam == CODE:
            km = set(k.profile.masks) or {value_mask(v) for v in k.profile.values}
            share = sum(1 for v in r.profile.values if value_mask(v) in km) / max(1, len(r.profile.values))
            if share < self.th.shape_overlap:
                return "code: shapes differ"
            return None
        return None                                # guid ↔ guid: only containment can tell

    def _range(self, shape: Shape, column: str) -> tuple[Optional[int], Optional[int]]:
        key = (shape.key, column.upper())
        if key not in self.ranges:
            lo, hi = None, None
            for t in shape.tables:
                try:
                    a, b = self.probe.key_range(t, column)
                except Exception as e:  # noqa: BLE001
                    log.debug("range failed %s: %s", t.table_name, e)
                    continue
                if a is not None:
                    lo = a if lo is None else min(lo, a)
                if b is not None:
                    hi = b if hi is None else max(hi, b)
            self.ranges[key] = (lo, hi)
        return self.ranges[key]

    # -- step 3: containment
    def contain(self, pairs: list[tuple[ColumnSample, ColumnSample]]) -> list[PairResult]:
        """One lookup per target table, with every referencing column's values batched into it."""
        by_key: dict[tuple[str, str, str], list[ColumnSample]] = {}
        for r, k in pairs:
            by_key.setdefault((k.shape, k.column, lookup_family(r, k)), []).append(r)
        results: list[PairResult] = []
        done = 0
        for (kshape, kcol, family), refs in sorted(by_key.items()):
            ks = self.shapes[kshape]
            values = sorted({v for r in refs for v in r.profile.values})
            hits_per_table: dict[str, set[str]] = {}
            for t in ks.tables:
                try:
                    hits_per_table[t.table_name] = self.probe.contained(t, kcol, values, family)
                except Exception as e:  # noqa: BLE001
                    log.debug("contain failed %s.%s: %s", t.table_name, kcol, e)
                    hits_per_table[t.table_name] = set()
            lo, hi = self.ranges.get((kshape, kcol.upper()), (None, None))
            rows = sum(t.row_count or 0 for t in ks.tables) / max(1, len(ks.tables))
            density = (rows / (hi - lo + 1)) if family == INT and lo is not None and hi is not None and hi >= lo else None
            for r in refs:
                rs = self.shapes[r.shape]
                vals = [fold(v) for v in r.profile.values]
                per = {tn: sum(1 for v in vals if v in hit) for tn, hit in hits_per_table.items()}
                union = set().union(*hits_per_table.values()) if hits_per_table else set()
                matched = sum(1 for v in vals if v in union)
                containment = matched / max(1, len(vals))
                res = PairResult(r.shape, rs.entity, r.column, kshape, ks.entity, kcol, family, "contain",
                                 sample_size=len(vals), sample_matched=matched, sample_containment=round(containment, 4),
                                 sample_per_table=per, key_density=round(density, 4) if density is not None else None,
                                 measured_at=_now())
                if containment < self.th.sample_containment:
                    res.reason = f"sample containment {containment:.2f} < {self.th.sample_containment}"
                elif family == INT and density is not None and containment < min(1.0, density + self.th.int_lift) \
                        and containment < 0.99:
                    res.reason = f"int containment {containment:.2f} not above key density {density:.2f}"
                else:
                    res.stage = "corroborate"
                results.append(res)
            done += 1
            if done % 50 == 0:
                self.progress(f"containment {done}/{len(by_key)} target columns")
        return results

    # -- step 4: corroboration
    def corroborate(self, results: list[PairResult]) -> None:
        live = [r for r in results if r.stage == "corroborate"]
        competing = Counter((r.ref_shape, r.ref_column) for r in live)
        for r in live:
            needed = r.family == INT or competing[(r.ref_shape, r.ref_column)] > 1
            ev = self._corroboration(r)
            r.corroboration = ev
            if needed and (ev is None or ev["pairs"] < self.th.corroboration_min_pairs
                           or ev["rate"] < self.th.corroboration_rate):
                r.reason = "no other attribute agrees across the joined rows" if ev else "corroboration unavailable"
                continue
            r.stage = "confirm"
        # Among competing targets of one referencing column, keep only the best-corroborated shape.
        by_ref: dict[tuple[str, str], list[PairResult]] = {}
        for r in live:
            if r.stage == "confirm":
                by_ref.setdefault((r.ref_shape, r.ref_column), []).append(r)
        for group in by_ref.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda x: (-(x.corroboration or {}).get("rate", 0), -(x.sample_containment or 0)))
            best = group[0]
            for other in group[1:]:
                if (other.corroboration or {}).get("rate", 0) < (best.corroboration or {}).get("rate", 0):
                    other.stage, other.reason = "corroborate", f"weaker than {best.key_entity}.{best.key_column}"

    def _text_columns(self, shape: Shape, exclude: str) -> list[str]:
        rep = shape.representative()
        return [c.name for c in rep.columns
                if not c.sensitive and c.name.upper() != exclude.upper()
                and (declared_family(c.data_type) == "text")]

    def _corroboration(self, r: PairResult) -> Optional[dict[str, Any]]:
        rs, ks = self.shapes[r.ref_shape], self.shapes[r.key_shape]
        sample = self.samples.get((r.ref_shape, r.ref_column.upper()))
        if not sample:
            return None
        values = sample.profile.values
        rcols, kcols = self._text_columns(rs, r.ref_column), self._text_columns(ks, r.key_column)
        if not rcols or not kcols:
            return None
        try:
            cache = (r.ref_shape, r.ref_column.upper())
            if cache not in self._ref_rows:
                ref_family = INT if declared_family(sample.declared) == INT else CODE
                self._ref_rows[cache] = self.probe.rows_by(rs.representative(), r.ref_column, values, ref_family, rcols)
            ref_rows = self._ref_rows[cache]
            best_table = max(r.sample_per_table.items(), key=lambda kv: kv[1])[0] if r.sample_per_table else None
            target = next((t for t in ks.tables if t.table_name == best_table), ks.representative())
            key_rows = self.probe.rows_by(target, r.key_column, values, r.family, kcols)
            key_rows = [x for x in key_rows if x.get(r.key_column) is not None]
        except Exception as e:  # noqa: BLE001
            log.debug("corroboration failed: %s", e)
            return None
        by_key: dict[str, dict[str, Any]] = {}
        for row in key_rows:
            by_key.setdefault(fold(row.get(r.key_column)), row)
        agree: Counter = Counter()
        compared: Counter = Counter()
        agreed_values: dict[tuple[str, str], set[str]] = {}
        for row in ref_rows:
            other = by_key.get(fold(row.get(r.ref_column)))
            if not other:
                continue
            for a in rcols:
                va = row.get(a)
                if va is None or not str(va).strip():
                    continue
                fa = fold(va)
                if len(fa) < 3:
                    continue                      # "1", "TR": equal by accident
                for b in kcols:
                    vb = other.get(b)
                    if vb is None or not str(vb).strip():
                        continue
                    compared[(a, b)] += 1
                    if fa == fold(vb):
                        agree[(a, b)] += 1
                        agreed_values.setdefault((a, b), set()).add(fa)
        # A column constant on both sides agrees trivially ("TR" = "TR"): the agreeing values must vary
        # as much as the rows do, or the agreement says nothing about *which* row was matched.
        scored = [((a, b), agree[(a, b)] / n, n) for (a, b), n in compared.items()
                  if n >= self.th.corroboration_min_pairs
                  and len(agreed_values.get((a, b), ())) >= 0.5 * agree[(a, b)]]
        if not scored:
            return {"pairs": max(compared.values(), default=0), "rate": 0.0, "columns": None, "table": target.table_name}
        (a, b), rate, n = max(scored, key=lambda x: (x[1], x[2]))
        # A column pair that is constant on both sides agrees trivially ("TR" = "TR"): require variety.
        return {"pairs": n, "rate": round(rate, 4), "columns": [a, b], "table": target.table_name}

    # -- step 5: confirmation
    def confirm(self, results: list[PairResult]) -> None:
        for r in [x for x in results if x.stage == "confirm"]:
            rs, ks = self.shapes[r.ref_shape], self.shapes[r.key_shape]
            rep = rs.representative()
            since = None
            if ks.is_periodic():
                start = min(str(t.time_window[0])[:10] for t in ks.tables if t.time_window)
                tcol = self.time_column(rep)
                if tcol:
                    since = (tcol, start)
            try:
                full = self.probe.coverage(rep, r.ref_column, r.family, ks.tables, r.key_column, None)
                windowed = self.probe.coverage(rep, r.ref_column, r.family, ks.tables, r.key_column, since) if since else None
                if is_declared_key(ks, r.key_column):
                    uniq = {"declared": True}
                else:
                    uniq = {t.table_name: dict(zip(("rows", "distinct"), self.probe.key_uniqueness(t, r.key_column))) for t in ks.tables}
            except Exception as e:  # noqa: BLE001
                r.reason = f"confirmation query failed: {str(e)[:200]}"
                continue
            r.coverage = {"all": full, "in_window": windowed, "window": {"column": since[0], "from": since[1]} if since else None}
            r.key_uniqueness = uniq
            basis = windowed or full
            cov = basis["matched"] / max(1, basis["distinct"])
            multi = full["multi_period"] / max(1, full["matched"])
            if len(ks.tables) > 1:
                r.period_semantics = ("periodic" if ks.is_periodic() and multi < 0.01 else
                                      "periodic-ambiguous" if ks.is_periodic() else "replicated")
            r.measured_at = _now()
            if basis["matched"] < self.th.min_matched:
                r.reason = f"only {basis['matched']} matched values"
            elif cov < self.th.confirmed_coverage:
                r.reason = f"coverage {cov:.3f} < {self.th.confirmed_coverage}"
            elif r.period_semantics == "periodic-ambiguous":
                r.reason = f"{multi:.1%} of matched values exist in more than one period table"
            else:
                r.stage, r.reason = "accepted", f"coverage {cov:.3f}"

    def run(self) -> DiscoveryReport:
        report = DiscoveryReport(started_at=_now(), thresholds=asdict(self.th))
        report.catalog = asdict(catalog_candidates(self.profiles))
        self.progress(f"catalog: {report.catalog['pairs']} type-compatible pairs")
        self.sample_all(report)
        pairs = self.blocked_pairs(report)
        self.progress(f"after value shapes/ranges: {len(pairs)} pairs")
        results = self.contain(pairs)
        self.corroborate(results)
        self.confirm(results)
        report.pairs = results
        report.queries = getattr(self.probe, "queries", 0)
        report.query_seconds = round(getattr(self.probe, "seconds", 0.0), 1)
        report.finished_at = _now()
        return report


# ------------------------------------------------------------------------------------------ apply plan

def relationship_of(pair: PairResult, shapes: dict[str, Shape]) -> dict[str, Any]:
    """The relationship dict the catalog stores on the referencing profile, with its evidence."""
    ks = shapes[pair.key_shape]
    rs = shapes[pair.ref_shape]
    ref_col = next((c for c in rs.representative().columns if c.name.upper() == pair.ref_column.upper()), None)
    key_col = next((c for c in ks.representative().columns if c.name.upper() == pair.key_column.upper()), None)
    ref_family = declared_family(ref_col.data_type if ref_col else "")
    key_family = declared_family(key_col.data_type if key_col else "")
    basis = (pair.coverage or {}).get("in_window") or (pair.coverage or {}).get("all") or {}
    confidence = basis.get("matched", 0) / max(1, basis.get("distinct", 0))
    return {
        "column": pair.ref_column,
        "ref_entity": pair.key_entity,
        "ref_column": pair.key_column,
        "source": LINK_SOURCE,
        "confidence": round(confidence, 4),
        "ref_schema": ks.schema_name,
        "ref_pattern": ks.pattern,
        "cross_source": True,
        "value_family": pair.family,
        # How the two sides must be compared in SQL: an integer stored as text needs a cast, and two
        # databases with different collations need one of them named or the comparison is an error.
        "join_cast": key_col.data_type if (ref_family != key_family and pair.family == INT and key_col) else None,
        "join_collate": pair.family in (CODE, GUID) and ref_family == "text",
        "period_semantics": pair.period_semantics,
        "evidence": {
            "measured_at": pair.measured_at,
            "sample": {"size": pair.sample_size, "matched": pair.sample_matched, "per_table": pair.sample_per_table},
            "coverage": pair.coverage,
            "key_uniqueness": pair.key_uniqueness,
            "corroboration": pair.corroboration,
            "key_density": pair.key_density,
        },
    }


def apply_plan(report: DiscoveryReport, profiles: list[SchemaProfile]) -> list[dict[str, Any]]:
    """What an apply step would write: one relationship per physical profile row of the referencing
    shape. Pure — nothing is written here."""
    shapes = {s.key: s for s in shapes_of(profiles)}
    plan = []
    for pair in report.accepted():
        rel = relationship_of(pair, shapes)
        for t in shapes[pair.ref_shape].tables:
            existing = [x for x in t.relationships if x.get("column", "").upper() == pair.ref_column.upper()]
            plan.append({"datasource_id": t.datasource_id, "schema_name": t.schema_name, "table_name": t.table_name,
                         "action": "replace" if existing else "add", "replaces": existing, "relationship": rel})
    return plan
