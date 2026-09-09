"""Read-only SQL guardrails + physicalisation (model names → physical tables, dialect transpile)."""

from __future__ import annotations

import re
from typing import Optional

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import build_scope

from semantic_layer.models import SchemaProfile
from semantic_layer.naming import logical_table, physical_name, source_rank, strip_quotes
from semantic_layer.runtime import periods

_DENY = re.compile(r"(?i)\b(insert|update|delete|drop|alter|truncate|merge|exec|execute|grant|revoke|create|into|openrowset|openquery|opendatasource|xp_\w+|sp_\w+|bulk|shutdown|dbcc|waitfor|kill|backup|restore)\b")
_COMMENT = re.compile(r"--|/\*|\*/")


def strip_comments(sql: str) -> str:
    """Remove SQL comments outside string literals. They are stripped rather than rejected: a model
    routinely annotates its SQL, and a comment is also the classic place to hide a second statement."""
    out, i, n = [], 0, len(sql or "")
    in_str = False
    while i < n:
        ch = sql[i]
        if in_str:
            out.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    out.append(sql[i + 1]); i += 2; continue
                in_str = False
            i += 1
            continue
        if ch == "'":
            in_str = True; out.append(ch); i += 1; continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
            out.append(" ")
            continue
        out.append(ch); i += 1
    return "".join(out)


def allowed_tables(sql: str, profiles: list[SchemaProfile], context: dict[str, str], dialect: Optional[str] = "tsql") -> tuple[bool, str]:
    """Every table the statement reads must be one the catalog profiled. Without this the endpoint is a
    read-anything console over whatever the database login can reach."""
    known: set[str] = set()
    schemas: set[str] = set()
    for p in profiles:
        phys = physical_name(p.table_pattern, {**p.context, **(context or {})}).upper()
        known.update({p.entity.upper(), phys, p.table_name.upper()})
        if p.schema_name:
            qual = p.schema_name.upper()
            schemas.add(qual)
            # "Timas_MSCRM.dbo" is one qualifier and also two: a reference may spell either.
            for part in qual.split("."):
                if part:
                    schemas.add(part)
            known.update({f"{qual}.{phys}", f"{qual}.{p.table_name.upper()}"})
    names = _physical_references(sql, dialect)
    if names is None:
        # Unreadable is not harmless: a statement this cannot parse is one whose tables it cannot
        # name, and permitting it makes the check absent exactly where it is needed.
        return False, "sql could not be parsed for a table check"
    if not names:
        return False, "no table could be resolved from this statement"
    for name in names:
        raw = strip_quotes(name).upper()
        bare = raw.split(".")[-1]
        candidates = {raw, bare, logical_table(raw).entity.upper()}
        for schema in schemas | {"DBO", "PUBLIC", "MAIN"}:          # model spelling: <schema>_<table>
            if bare.startswith(schema + "_"):
                candidates.add(bare[len(schema) + 1:])
        if not (candidates & known):
            return False, f"table not in the catalog: {name}"
    return True, "ok"


def validate_sql(sql: str) -> tuple[bool, str]:
    s = strip_comments(sql or "").strip().rstrip(";").strip()
    if not s:
        return False, "empty"
    if not re.match(r"(?is)^\s*(with|select)\b", s):
        return False, "only SELECT/WITH allowed"
    if ";" in s:
        return False, "multiple statements"
    if _DENY.search(s):
        return False, f"denied keyword: {_DENY.search(s).group(0)}"
    return True, "ok"


def physicalize_sql(sql: str, profiles: list[SchemaProfile], context: dict[str, str], dialect: str = "tsql",
                    *, period: Optional[tuple] = None) -> str:
    """Rewrite model / logical table spellings to physical ones and transpile to the target dialect.

    A model spelling (schema_TABLE), a logical entity or a stale period name all resolve to the
    physical table of the profiled pattern under the given context; LIMIT → TOP, EXTRACT → DATEPART.

    With `period` given as (start, end), an entity whose rows are split across one table per year is
    resolved here rather than in the prompt. Until now the model was handed the year-to-table map and
    asked to write the UNION ALL itself — several hundred tokens of bookkeeping on every question,
    and a step where a model can pick the wrong year, union a duplicate copy and return double the
    real figure. The compiler already knows which tables a period needs and which copy to skip; doing
    it here makes that knowledge structural instead of advisory.

    Only tables of the representative's own pattern are unioned. The same entity can also exist as a
    view or a hand-made copy under another prefix, and those are not other years of it.
    """
    by_table = {p.table_name.upper(): p for p in profiles}
    tables_of: dict[str, list[SchemaProfile]] = {}
    for p in profiles:
        tables_of.setdefault(p.entity, []).append(p)
    # Which physical table stands for an entity when the model writes its logical name. Built from
    # a dict comprehension this was whichever profile happened to be last, so an entity that also
    # exists as a view or a hand-made copy could be represented by the copy — and every question
    # asked in logical terms would then be answered from it. Rank decides: a base table before a
    # view, a view before something whose name says it is a backup, and rows break the tie.
    by_entity: dict[str, SchemaProfile] = {}
    for entity, group in tables_of.items():
        by_entity[entity] = min(group, key=lambda x: (source_rank(x.table_name, is_view=x.row_count is None),
                                                      -(x.row_count or 0), x.table_name))
    for p in profiles:
        by_table[f"{p.schema_name}_{p.table_name}".upper()] = p
        by_table[f"{p.schema_name}.{p.table_name}".upper()] = p

    def spread(prof: SchemaProfile) -> list[SchemaProfile]:
        """The tables of `prof`'s entity this period needs — one, unless the years span more.

        Never where the SQL already names more than one year of that pattern. A model told which
        table holds which year writes the UNION itself, and expanding each of its branches to the
        whole span again adds every year to itself: the answer comes back at twice the real figure
        with nothing about it looking wrong. Naming one table is the case this is for — the model
        picked a year and the question needs more than that one.
        """
        if period is None or already_spread.get(prof.table_pattern, 0) > 1:
            return [prof]
        same = [x for x in tables_of.get(prof.entity, []) if x.table_pattern == prof.table_pattern]
        if len(same) < 2:
            return [prof]
        picked = periods.tables_for(same, period[0], period[1])
        return picked or [prof]
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        tree = sqlglot.parse_one(sql)
    cte_names = {c.alias.upper() for c in tree.find_all(exp.CTE) if c.alias}

    # How many distinct physical tables of each pattern the SQL already names, counted before
    # anything is rewritten: that is what says whether the model spread the years itself.
    already_spread: dict[str, int] = {}
    seen_tables: dict[str, set[str]] = {}
    for node in tree.find_all(exp.Table):
        if not node.name or node.name.upper() in cte_names:
            continue
        key = ((node.db + "_") if node.db else "") + node.name
        found = by_table.get(key.upper()) or by_table.get(node.name.upper())
        if found is not None:
            seen_tables.setdefault(found.table_pattern, set()).add(found.table_name)
    already_spread = {pattern: len(names) for pattern, names in seen_tables.items()}

    # Which relation the period actually constrains. A period is spread over the rows the question
    # dates, not over everything the query mentions: a reference table joined beside them holds the
    # same rows whichever year is asked, and its own measured window is the range of its creation
    # dates. Spread anyway, it is read once per period and every row it is joined to is matched more
    # than once — the figure comes back multiplied, and nothing about the query looks wrong.
    dated_aliases: set[str] = set()
    for cmp_ in tree.find_all(exp.Between, exp.GTE, exp.GT, exp.LTE, exp.LT):
        cols = [c for c in cmp_.find_all(exp.Column)]
        lits = [l for l in cmp_.find_all(exp.Literal) if l.is_string] + list(cmp_.find_all(exp.Cast))
        if not cols or not lits:
            continue
        for c in cols:
            if c.table:
                dated_aliases.add(c.table.upper())

    def tx(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Table) and node.name:
            raw = node.name
            key = ((node.db + "_") if node.db else "") + raw
            if raw.upper() in cte_names:
                return node
            prof = by_table.get(key.upper()) or by_table.get(raw.upper())
            if prof is None:
                lt = logical_table(raw)
                prof = by_entity.get(lt.entity) if lt.table_pattern != lt.entity or lt.entity in by_entity else None
            if prof is None:
                return node
            # Where the query says which relation carries the period, only that one is spread.
            name_here = (node.alias or node.name or "").upper()
            wanted = spread(prof) if (not dated_aliases or name_here in dated_aliases
                                      or prof.entity.upper() in dated_aliases) else [prof]
            if len(wanted) > 1:
                # One entity, several years: read them as one relation so everything the model wrote
                # around it — the joins, the filters, the aggregate — is untouched.
                parts = [exp.select(exp.Star()).from_(_physical_table(x, context)) for x in wanted]
                union: exp.Expression = parts[0]
                for nxt in parts[1:]:
                    union = exp.union(union, nxt, distinct=False)
                alias = node.alias or prof.entity
                return exp.Subquery(this=union, alias=exp.TableAlias(this=exp.to_identifier(alias)))
            new = _physical_table(wanted[0], context)
            if node.alias:
                new.set("alias", exp.TableAlias(this=exp.to_identifier(node.alias)))
            return new
        return node

    out = tree.transform(tx)
    return out.sql(dialect=dialect if dialect != "generic" else None)


def _physical_table(prof: SchemaProfile, context: dict[str, str]) -> exp.Table:
    phys = physical_name(prof.table_pattern, {**prof.context, **context})
    # `schema_name` may be "database.schema" — a source whose tables live in more than one database
    # on one server. Written as two parts, the name resolves wherever the connection is pointed.
    parts = [x for x in (prof.schema_name or "").split(".") if x]
    node = exp.Table(this=exp.to_identifier(phys, quoted=True))
    if parts:
        node.set("db", exp.to_identifier(parts[-1], quoted=True))
    if len(parts) > 1:
        node.set("catalog", exp.to_identifier(parts[-2], quoted=True))
    return node


def strip_trailing_semicolon(sql: str) -> str:
    return (sql or "").strip().rstrip(";").strip()


def _physical_references(sql: str, dialect: Optional[str] = "tsql") -> Optional[list[str]]:
    """Every physical table this statement reads, or None when the statement cannot be read.

    Resolved per scope rather than by name. A common table expression is a name that exists only
    inside the statement, and the previous reading collected those names into one global set and
    excused *every* reference that matched — including a schema-qualified one, which can never be a
    CTE. `WITH X AS (SELECT 1) SELECT * FROM dbo.X` therefore reported no tables at all, and a check
    that sees no tables permits everything: the statement read `dbo.X` from the database with nothing
    in the catalog saying it could.

    `build_scope` resolves each source to what it actually is — a CTE reference becomes that CTE's
    scope, a real table stays a table — and it does so per scope, so a name defined in an inner
    query does not excuse a reference in an outer one. What comes back as a table is a table.
    """
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001
        try:
            tree = sqlglot.parse_one(sql)
        except Exception:  # noqa: BLE001
            return None
    try:
        root = build_scope(tree)
    except Exception:  # noqa: BLE001
        return None
    if root is None:
        return None
    out: list[str] = []
    for scope in root.traverse():
        for source in scope.sources.values():
            if isinstance(source, exp.Table) and source.name:
                out.append(((source.db + ".") if source.db else "") + source.name)
    return list(dict.fromkeys(out))


def referenced_tables(sql: str, dialect: Optional[str] = "tsql") -> list[str]:
    """The physical tables read, best effort. Callers deciding access must use `allowed_tables`,
    which refuses a statement this cannot read rather than reading it as "no tables"."""
    return _physical_references(sql, dialect) or []


# SQLSTATE class 08 is the standard "connection exception" class, and HYT00 is a connection timeout.
# Every ODBC/JDBC driver reports them the same way, so this is a protocol fact, not a driver quirk.
_CONNECTION_STATES = ("08S01", "08001", "08003", "08004", "08006", "08007", "HYT00", "HY000")
_CONNECTION_WORDS = (
    "communication link failure", "server is not found", "login timeout", "connection is closed",
    "connection refused", "broken pipe", "connection reset", "unable to connect", "not accessible",
)


def is_connection_error(error: object) -> bool:
    """Did the data source go away, or was the query wrong?

    They fail in the same place and mean opposite things: a wrong query can be rewritten, an
    unreachable database cannot. Asking a model to repair SQL that was already correct costs a wait
    and produces nothing, and telling a user their question was invalid when the connection dropped
    sends them looking in the wrong place.
    """
    text = str(error or "")
    if any(f"'{state}'" in text or f"[{state}]" in text for state in _CONNECTION_STATES):
        return True
    low = text.lower()
    return any(w in low for w in _CONNECTION_WORDS)
