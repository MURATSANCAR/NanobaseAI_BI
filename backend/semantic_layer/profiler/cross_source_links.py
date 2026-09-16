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
    first_pass_values: int = 40          # values per column in the first, domain-finding containment pass
    sample_timeout: int = 60             # seconds a single sampled read may take before it is skipped


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

# SQL Server takes at most 2.100 parameters in one statement. Lists longer than this are split into as
# many statements as they need — never cut.
PARAM_CHUNK = 2000


def norm_key(value: Any, family: str) -> Optional[str]:
    """The form two sides are compared in, whatever each database stores: an integer kept as
    nvarchar on one side and as int on the other meets as the same digits; text meets trimmed, case-
    and accent-folded (a CI_AI collation compares that way); a guid meets without braces, upper-case."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.upper() == "NULL":
        return None
    if family == INT:
        m = re.fullmatch(r"(-?\d{1,18})(?:\.0+)?", s)
        return str(int(m.group(1))) if m else None
    if family == GUID:
        return s.strip("{}").upper()
    return fold(s)


def _chunks(values: list[Any], size: int = PARAM_CHUNK) -> Iterable[list[Any]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


class LinkProbe(Protocol):
    """The SQL this discovery needs, per table. A probe answers only for the tables of its own
    connection; :class:`RoutedProbe` sends each table to the connection that holds it. Nothing here
    joins two tables: what crosses from one database to the other travels as parameters."""

    def of(self, table: SchemaProfile) -> "LinkProbe": ...
    def sample(self, table: SchemaProfile, columns: list[str], rows: int) -> list[dict[str, Any]]: ...
    def key_range(self, table: SchemaProfile, column: str) -> tuple[Optional[int], Optional[int]]: ...
    def key_uniqueness(self, table: SchemaProfile, column: str) -> tuple[int, int]: ...
    def contained(self, table: SchemaProfile, column: str, values: list[str], family: str) -> set[str]: ...
    def contained_many(self, table: SchemaProfile, columns: dict[str, tuple[list[str], str]],
                       seek: set[str]) -> dict[str, set[str]]: ...
    def rows_by(self, table: SchemaProfile, column: str, values: list[str], family: str,
                columns: list[str]) -> list[dict[str, Any]]: ...
    def ref_values(self, table: SchemaProfile, column: str,
                   since: Optional[tuple[str, str]]) -> list[tuple[Any, int, int]]: ...
    def distinct_values(self, table: SchemaProfile, column: str) -> list[Any]: ...


class _SqlProbe:
    family_sql = "tsql"
    hint = " OPTION (MAXDOP 1)"
    count_fn = "COUNT_BIG"

    def __init__(self, connector: Any, *, timeout: Optional[int] = None, database: Optional[str] = None):
        self.c = connector
        self.database = database          # the database this connection is already in, when known
        self.queries = 0
        self.seconds = 0.0
        self.set_timeout(timeout)

    def of(self, table: SchemaProfile) -> "_SqlProbe":
        return self

    @property
    def timeout(self) -> Optional[int]:
        return getattr(self.c, "query_timeout", None)

    def set_timeout(self, seconds: Optional[int]) -> None:
        """Per-query budget. A sampled read of a view can execute the whole view; that is worth a
        minute, not an hour, and a table that cannot be sampled in time is reported, not waited for."""
        if not seconds or not hasattr(self.c, "query_timeout"):
            return
        self.c.query_timeout = seconds
        conn = getattr(self.c, "_conn", None)
        if conn is not None:
            try:
                conn.timeout = seconds
            except AttributeError:            # a driver without a per-query timeout (SQLite)
                pass

    # -- dialect bits
    def q(self, ident: str) -> str:
        return f"[{ident}]"

    def table(self, p: SchemaProfile) -> str:
        parts = [x for x in (p.schema_name or "").split(".") if x]
        return ".".join(self.q(x) for x in parts + [p.table_name])

    def as_text(self, expr: str) -> str:
        return f"CAST({expr} AS nvarchar(450))"

    def mark(self, table: SchemaProfile, column: str, family: str) -> str:
        """One parameter slot. Parameters arrive as unicode; against a non-unicode column that would
        turn a seek into a scan, so the value is converted once, on the parameter side."""
        if family != INT:
            col = next((c for c in table.columns if c.name.upper() == column.upper()), None)
            base = (col.data_type if col else "").lower().split("(")[0].strip()
            if base in ("varchar", "char"):
                return "CAST(? AS varchar(450))"
        return "?"

    def run(self, sql: str, limit: int = 1_000_000) -> list[dict[str, Any]]:
        t = time.monotonic()
        try:
            _, rows, _ = self.c.execute(sql, limit)
        finally:
            self.queries += 1
            self.seconds += time.monotonic() - t
        return rows

    def run_params(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        """Every row, parameters bound by the driver (``?`` for both pyodbc and sqlite3)."""
        t = time.monotonic()
        try:
            cols, rows = self.c._rows(sql, tuple(params))
        finally:
            self.queries += 1
            self.seconds += time.monotonic() - t
        return [dict(zip(cols, r)) for r in rows]

    @staticmethod
    def params(values: Iterable[Any], family: str) -> list[Any]:
        """Values bound as the family's type; a value the family cannot hold is dropped, not cast by
        the database (an nvarchar 'ABC' against an int key is a conversion error, not a miss)."""
        out = []
        for v in values:
            k = norm_key(v, family)
            if k is None:
                continue
            out.append(int(k) if family == INT else str(v).strip())
        return list(dict.fromkeys(out))

    # -- single-table reads
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

    def key_uniqueness(self, table, column):
        row = self.run(f"SELECT {self.count_fn}({self.q(column)}) AS n, COUNT(DISTINCT {self.q(column)}) AS d "
                       f"FROM {self.table(table)}{self.hint}", 1)[0]
        return int(row["n"] or 0), int(row["d"] or 0)

    def ref_values(self, table, column, since):
        """Every distinct stored value of a referencing column with its row count — and, when a
        window is given, how many of those rows fall inside it. One grouped read; the comparison
        form is made in Python, so the database's own collation never decides a match."""
        v = self.as_text(self.q(column))
        inside = f"SUM(CASE WHEN {self.q(since[0])} >= ? THEN 1 ELSE 0 END)" if since else f"{self.count_fn}(*)"
        rows = self.run_params(f"SELECT {v} AS v, {self.count_fn}(*) AS n, {inside} AS w FROM {self.table(table)} "
                               f"WHERE {self.q(column)} IS NOT NULL GROUP BY {v}{self.hint}",
                               [since[1]] if since else [])
        return [(r["v"], int(r["n"] or 0), int(r["w"] or 0)) for r in rows]

    def distinct_values(self, table, column):
        rows = self.run_params(f"SELECT DISTINCT {self.as_text(self.q(column))} AS v FROM {self.table(table)} "
                               f"WHERE {self.q(column)} IS NOT NULL{self.hint}", [])
        return [r["v"] for r in rows]

    # -- values from elsewhere, looked up here
    def contained(self, table, column, values, family):
        found: set[str] = set()
        m = self.mark(table, column, family)
        for chunk in _chunks(self.params(values, family)):
            rows = self.run_params(f"SELECT DISTINCT {self.as_text(self.q(column))} AS v FROM {self.table(table)} "
                                   f"WHERE {self.q(column)} IN ({', '.join([m] * len(chunk))}){self.hint}", chunk)
            found.update(k for k in (norm_key(r.get("v"), family) for r in rows) if k is not None)
        return found

    def contained_many(self, table, columns: dict[str, tuple[list[str], str]], seek: set[str]) -> dict[str, set[str]]:
        """Seek columns one by one; every other column of the table in one scan per chunk."""
        out: dict[str, set[str]] = {}
        scan = {c: v for c, v in columns.items() if c not in seek}
        for c in [c for c in columns if c in seek]:
            values, family = columns[c]
            out[c] = self.contained(table, c, values, family)
        if len(scan) <= 1:
            for c, (values, family) in scan.items():
                out[c] = self.contained(table, c, values, family)
            return out
        wanted = {c: {k for k in (norm_key(v, f) for v in values) if k is not None} for c, (values, f) in scan.items()}
        flat = [(c, p, f) for c, (values, f) in scan.items() for p in self.params(values, f)]
        for chunk in _chunks(flat):
            groups: dict[str, list[Any]] = {}
            fam = {}
            for c, p, f in chunk:
                groups.setdefault(c, []).append(p)
                fam[c] = f
            apply = ", ".join(f"({_lit(c)}, {self.as_text(self.q(c))})" for c in groups)
            where = " OR ".join(f"{self.q(c)} IN ({', '.join([self.mark(table, c, fam[c])] * len(v))})"
                                for c, v in groups.items())
            rows = self.run_params(f"SELECT DISTINCT x.c, x.v FROM {self.table(table)} "
                                   f"CROSS APPLY (VALUES {apply}) AS x(c, v) WHERE ({where}){self.hint}",
                                   [p for v in groups.values() for p in v])
            for row in rows:
                c = row.get("c")
                if c not in wanted:
                    continue
                k = norm_key(row.get("v"), fam.get(c, CODE))
                if k is not None and k in wanted[c]:
                    out.setdefault(c, set()).add(k)
        for c in scan:
            out.setdefault(c, set())
        return out

    def rows_by(self, table, column, values, family, columns):
        cols = ", ".join(f"{self.as_text(self.q(c))} AS {self.q(c)}" for c in dict.fromkeys([column] + columns))
        m = self.mark(table, column, family)
        out: list[dict[str, Any]] = []
        for chunk in _chunks(self.params(values, family)):
            out += self.run_params(f"SELECT {cols} FROM {self.table(table)} "
                                   f"WHERE {self.q(column)} IN ({', '.join([m] * len(chunk))}){self.hint}", chunk)
        return out


def _lit(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


class TsqlLinkProbe(_SqlProbe):
    pass


class SqliteLinkProbe(_SqlProbe):
    """SQLite. A profile's database qualifier is an ATTACHed name — or, when it names the database
    this connection *is*, nothing (SQLite cannot refer to its own file by another name)."""

    hint = ""
    count_fn = "COUNT"

    def q(self, ident: str) -> str:
        return f'"{ident}"'

    def as_text(self, expr: str) -> str:
        return f"CAST({expr} AS TEXT)"

    def mark(self, table, column, family):
        return "?"

    def table(self, p):
        parts = [x for x in (p.schema_name or "").split(".") if x][:1]
        if parts and self.database and parts[0].upper() == self.database.upper():
            parts = []
        return ".".join(self.q(x) for x in parts + [p.table_name])

    def sample(self, table, columns, rows):
        cols = ", ".join(f"{self.as_text(self.q(c))} AS {self.q(c)}" for c in columns)
        return self.run(f"SELECT {cols} FROM {self.table(table)} ORDER BY random() LIMIT {int(rows)}", rows)

    def contained_many(self, table, columns, seek):
        return {c: self.contained(table, c, values, family) for c, (values, family) in columns.items()}


def probe_for(connector: Any, *, timeout: Optional[int] = None, database: Optional[str] = None) -> _SqlProbe:
    dialect = getattr(connector, "dialect", "tsql")
    cls = SqliteLinkProbe if dialect == "sqlite" else TsqlLinkProbe
    return cls(connector, timeout=timeout, database=database)


def database_of(connector: Any) -> Optional[str]:
    """The database a connection opens, from its own configuration."""
    cfg = getattr(connector, "cfg", None) or {}
    return str(cfg.get("database")) if cfg.get("database") else None


class RoutedProbe:
    """Several connections, one probe. A table goes to the connection of its source
    (:func:`source_of` — the database qualifier of its schema, or ``""`` for the default one)."""

    def __init__(self, probes: dict[str, _SqlProbe]):
        self.probes = {k.upper(): v for k, v in probes.items()}
        if not self.probes:
            raise ValueError("at least one connection is needed")

    @classmethod
    def from_connectors(cls, connectors: list[Any], *, timeout: Optional[int] = None) -> "RoutedProbe":
        """The first connection answers for unqualified schemas; each connection also answers for
        schemas qualified with the database it opens. Which database is which comes from the
        connection files, not from a list kept here."""
        probes: dict[str, _SqlProbe] = {}
        for i, c in enumerate(connectors):
            db = database_of(c)
            p = probe_for(c, timeout=timeout, database=db)
            if i == 0:
                probes[""] = p
            if db:
                probes.setdefault(db.upper(), p)
        return cls(probes)

    def _unique(self) -> list[_SqlProbe]:
        return list({id(p): p for p in self.probes.values()}.values())

    def of(self, table: SchemaProfile) -> _SqlProbe:
        src = source_of(table.schema_name)
        p = self.probes.get(src)
        if p is None and len(self._unique()) == 1:
            p = self._unique()[0]              # one connection that sees every database (ATTACH, same server)
        if p is None:
            raise LookupError(f"no connection holds {src or 'the default database'} ({table.schema_name}.{table.table_name})")
        return p

    @property
    def queries(self) -> int:
        return sum(p.queries for p in self._unique())

    @property
    def seconds(self) -> float:
        return sum(p.seconds for p in self._unique())

    @property
    def timeout(self) -> Optional[int]:
        return next((p.timeout for p in self._unique() if p.timeout), None)

    def set_timeout(self, seconds: Optional[int]) -> None:
        for p in self._unique():
            p.set_timeout(seconds)

    def sample(self, table, columns, rows):
        return self.of(table).sample(table, columns, rows)

    def key_range(self, table, column):
        return self.of(table).key_range(table, column)

    def key_uniqueness(self, table, column):
        return self.of(table).key_uniqueness(table, column)

    def contained(self, table, column, values, family):
        return self.of(table).contained(table, column, values, family)

    def contained_many(self, table, columns, seek):
        return self.of(table).contained_many(table, columns, seek)

    def rows_by(self, table, column, values, family, columns):
        return self.of(table).rows_by(table, column, values, family, columns)

    def ref_values(self, table, column, since):
        return self.of(table).ref_values(table, column, since)

    def distinct_values(self, table, column):
        return self.of(table).distinct_values(table, column)


def measure_coverage(probe: LinkProbe, ref: SchemaProfile, column: str, family: str, targets: list[SchemaProfile],
                     key: str, *, key_declared: bool, since: Optional[tuple[str, str]]) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    """Full distinct coverage of a referencing column over every copy of the target, overall and
    inside the target's window. The referencing values are read once on their own connection; each
    target copy is asked on its connection which of them it holds — by seek on a declared key or when
    one statement carries them all, otherwise by reading that copy's distinct values once (one scan
    instead of one scan per parameter chunk)."""
    raw = probe.ref_values(ref, column, since)
    inside: dict[str, bool] = {}
    rows_all = rows_win = 0
    for v, n, w in raw:
        rows_all += n
        rows_win += w
        k = norm_key(v, family)
        if k is not None:
            inside[k] = inside.get(k, False) or w > 0
    values = sorted(inside)
    hits: dict[str, set[str]] = {}
    for t in targets:
        if key_declared or len(values) <= PARAM_CHUNK:
            hits[t.table_name] = probe.contained(t, key, values, family)
        else:
            have = {k for k in (norm_key(v, family) for v in probe.distinct_values(t, key)) if k is not None}
            hits[t.table_name] = have & inside.keys()

    def summary(vals: set[str], ref_rows: int) -> dict[str, Any]:
        per = {tn: len(h & vals) for tn, h in hits.items()}
        counts = Counter(v for h in hits.values() for v in (h & vals))
        return {"distinct": len(vals), "matched": len(counts), "multi_period": sum(1 for n in counts.values() if n > 1),
                "per_table": per, "ref_rows": ref_rows, "ref_distinct_raw": len(raw)}

    full = summary(set(values), rows_all)
    windowed = summary({k for k, w in inside.items() if w}, rows_win) if since else None
    return full, windowed


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
    cost: dict[str, Any] = field(default_factory=dict)
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
    def sample_all(self, report: DiscoveryReport, *, cache: Optional[str] = None) -> None:
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
                self.progress(f"sampled {i + 1}/{len(wanted)} tables ({len(report.sample_failures)} unreadable)")
                if cache:
                    self.save_samples(cache)          # a run this long must not lose what it has read

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
            inside = sum(1 for v in r.profile.values if lo <= int(v) <= hi) / max(1, len(r.profile.values))
            if inside < self.th.sample_containment:
                return "int: values outside the key's range"
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
    def _lookup(self, requests: dict[tuple[str, str, str], set[str]]) -> dict[tuple[str, str, str], dict[str, set[str]]]:
        """Which of the requested values each target column holds, per physical table.

        Grouped by physical table: every undeclared (scanned) column of one table is looked up in a
        single pass, and declared keys are looked up by seek. The work is proportional to the tables
        read, not to the pairs being tested.
        """
        per_table: dict[str, tuple[SchemaProfile, dict[tuple[str, str], set[str]]]] = {}
        for (shape, column, family), values in requests.items():
            for t in self.shapes[shape].tables:
                per_table.setdefault(f"{t.schema_name}.{t.table_name}", (t, {}))[1].setdefault((column, family), set()).update(values)
        out: dict[tuple[str, str, str], dict[str, set[str]]] = {k: {} for k in requests}
        shape_of = {f"{t.schema_name}.{t.table_name}": sh.key for sh in self.shapes.values() for t in sh.tables}
        for i, (name, (table, cols)) in enumerate(sorted(per_table.items())):
            shape = self.shapes[shape_of[name]]
            try:
                hits = self.probe.contained_many(table, {c: (sorted(v), f) for (c, f), v in cols.items()},
                                                 seek={c for c, _ in cols if is_declared_key(shape, c)})
            except Exception as e:  # noqa: BLE001
                log.warning("containment failed on %s: %s", name, str(e)[:200])
                hits = {}
            for (column, family) in cols:
                out[(shape.key, column, family)][table.table_name] = hits.get(column, set())
            if (i + 1) % 100 == 0:
                self.progress(f"containment: {i + 1}/{len(per_table)} tables read")
        return out

    def contain(self, pairs: list[tuple[ColumnSample, ColumnSample]]) -> list[PairResult]:
        """Two passes. A small spread of each column's values first, to find the targets whose domain
        meets it at all; then the full sample, only against those. Every pair keeps its pass-1 figures
        when it stops there."""
        by_key: dict[tuple[str, str, str], list[ColumnSample]] = {}
        for r, k in pairs:
            by_key.setdefault((k.shape, k.column, lookup_family(r, k)), []).append(r)
        first_n = max(self.th.min_distinct, self.th.first_pass_values)
        first = {key: {v for r in refs for v in _spread(r.profile.values, first_n)} for key, refs in by_key.items()}
        self.progress(f"containment pass 1: {len(first)} target columns")
        hits1 = self._lookup(first)
        survivors: dict[tuple[str, str, str], list[ColumnSample]] = {}
        results: list[PairResult] = []
        for key, refs in by_key.items():
            for r in refs:
                res = self._judge(key, r, _spread(r.profile.values, first_n), hits1[key])
                if res.stage == "contain":
                    res.reason = "pass 1: " + res.reason
                    results.append(res)
                else:
                    survivors.setdefault(key, []).append(r)
        self.progress(f"containment pass 2: {sum(len(v) for v in survivors.values())} pairs on {len(survivors)} target columns")
        hits2 = self._lookup({key: {v for r in refs for v in r.profile.values} for key, refs in survivors.items()})
        for key, refs in survivors.items():
            for r in refs:
                results.append(self._judge(key, r, r.profile.values, hits2[key]))
        return results

    def _judge(self, key: tuple[str, str, str], r: ColumnSample, values: list[str],
               hits_per_table: dict[str, set[str]]) -> PairResult:
        kshape, kcol, family = key
        ks, rs = self.shapes[kshape], self.shapes[r.shape]
        lo, hi = self.ranges.get((kshape, kcol.upper()), (None, None))
        rows = sum(t.row_count or 0 for t in ks.tables) / max(1, len(ks.tables))
        density = (rows / (hi - lo + 1)) if family == INT and lo is not None and hi is not None and hi >= lo else None
        vals = [fold(v) for v in values]
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
        elif family == INT and density is not None and density + self.th.int_lift < 1.0 \
                and containment < density + self.th.int_lift:
            # A key with gaps is hit by chance at its density; a real reference does better.
            # Where the key has no gaps this cannot tell anything apart — corroboration will.
            res.reason = f"int containment {containment:.2f} not above key density {density:.2f}"
        else:
            res.stage = "corroborate"
        return res

    # -- step 4: corroboration
    def corroborate(self, results: list[PairResult]) -> None:
        live = [r for r in results if r.stage == "corroborate"]
        competing = Counter((r.ref_shape, r.ref_column) for r in live)
        for r in live:
            # An integer is a counter and proves nothing on its own; so is a code claimed by more than
            # one target. Anything else is left alone — the check costs two reads of the joined rows.
            needed = r.family == INT or competing[(r.ref_shape, r.ref_column)] > 1
            ev = self._corroboration(r) if needed else None
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
        return {"pairs": n, "rate": round(rate, 4), "columns": [a, b], "table": target.table_name}

    # -- step 5: confirmation
    def confirm(self, results: list[PairResult]) -> None:
        for r in [x for x in results if x.stage == "confirm"]:
            rs, ks = self.shapes[r.ref_shape], self.shapes[r.key_shape]
            rep = rs.representative()
            since = None
            starts = [str(t.time_window[0])[:10] for t in ks.tables if t.time_window]
            tcol = self.time_column(rep) if starts else None
            if tcol:
                # Rows older than anything the target holds cannot match and say nothing against the link.
                since = (tcol, min(starts))
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
                # Each matched value in exactly one copy: the copies hold disjoint keys and may all be
                # joined at once. The same values in several copies: either copies of the same rows
                # (windows overlap — read one) or one counter restarting per period (ambiguous).
                r.period_semantics = ("periodic" if multi < 0.01 else
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

    # -- persistence of the expensive half, so a re-run with other thresholds reads nothing twice
    def save_samples(self, path: str) -> None:
        import json
        data = {"samples": [{"shape": s.shape, "column": s.column, "declared": s.declared, "profile": asdict(s.profile)}
                            for s in self.samples.values()],
                "ranges": [[k[0], k[1], v[0], v[1]] for k, v in self.ranges.items()]}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)

    def load_samples(self, path: str, report: DiscoveryReport) -> bool:
        import json
        import os
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for row in data.get("samples", []):
            if row["shape"] not in self.shapes:
                continue
            vp = ValueProfile(**row["profile"])
            self.samples[(row["shape"], row["column"].upper())] = ColumnSample(row["shape"], row["column"], row["declared"], vp)
            if vp.family:
                report.column_families[vp.family] = report.column_families.get(vp.family, 0) + 1
        for shape, column, lo, hi in data.get("ranges", []):
            self.ranges[(shape, column)] = (lo, hi)
        report.sampled_tables = len({s.shape for s in self.samples.values()})
        return True

    def cost_of(self, pairs: list[tuple[ColumnSample, ColumnSample]]) -> dict[str, Any]:
        """What step 3 will read: seeks on declared keys, scans on everything else."""
        keys = {}
        for r, k in pairs:
            keys.setdefault((k.shape, k.column), set()).update(r.profile.values)
        seeks = scans = scan_rows = 0
        for (shape, column), values in keys.items():
            ks = self.shapes[shape]
            chunks = max(1, -(-len(values) // 1000))
            if is_declared_key(ks, column):
                seeks += chunks * len(ks.tables)
            else:
                scans += chunks * len(ks.tables)
                scan_rows += chunks * sum(t.row_count or 0 for t in ks.tables)
        return {"target_columns": len(keys), "seek_queries": seeks, "scan_queries": scans, "scan_rows": scan_rows}

    def run(self, *, samples_cache: Optional[str] = None, stop_after: Optional[str] = None) -> DiscoveryReport:
        report = DiscoveryReport(started_at=_now(), thresholds=asdict(self.th))
        report.catalog = asdict(catalog_candidates(self.profiles))
        self.progress(f"catalog: {report.catalog['pairs']} type-compatible pairs")
        if not (samples_cache and self.load_samples(samples_cache, report)):
            probe_timeout = getattr(self.probe, "c", None) and getattr(self.probe.c, "query_timeout", None)
            self.probe.set_timeout(self.th.sample_timeout)
            self.sample_all(report, cache=samples_cache)
            self.probe.set_timeout(probe_timeout)
        pairs = self.blocked_pairs(report)
        if samples_cache:
            self.save_samples(samples_cache)
        report.cost = self.cost_of(pairs)
        self.progress(f"after value shapes/ranges: {len(pairs)} pairs, step 3 cost {report.cost}")
        if stop_after == "block":
            report.finished_at = _now()
            return report
        results = self.contain(pairs)
        self.progress(f"containment done: {sum(1 for r in results if r.stage != 'contain')} of {len(results)} pass")
        self.corroborate(results)
        self.progress(f"corroboration done: {sum(1 for r in results if r.stage == 'confirm')} to confirm")
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
