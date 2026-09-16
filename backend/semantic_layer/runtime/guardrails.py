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


#: the copy a row came from, carried through a union so joined rows only meet their own copy
_FIRM_COL = "__nb_firm"


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
            schemas.add(qual.replace(".", "_"))     # the prompt's single-identifier label
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


def _carry_tag_through_derived(out: exp.Expression, tagged: dict[str, str]) -> None:
    """A derived table over a tagged relation carries the tag out with it.

    A subquery that lists its columns (`SELECT DISTINCT id, tarih, cari FROM fatura`) does not carry
    the copy tag the union added to the relation it reads; the join outside it then met this year's
    documents with the earlier copy's payment plan on an identifier that merely coincided, and the
    answer was a payment term of minus 750 days. The tag is added to the projection (and the GROUP BY)
    of every subquery and CTE that reads a tagged relation, and the derived table — under the
    alias it is later read by — joins the tagged set, so the JOIN pass below binds it too. A
    derived table that aggregates without grouping is one row over all copies and stays untagged.
    """
    changed = True
    while changed:
        changed = False
        for node in list(out.find_all(exp.Subquery)) + list(out.find_all(exp.CTE)):
            alias = node.alias
            sel = node.this
            if not alias or alias.upper() in tagged or not isinstance(sel, exp.Select):
                continue
            sources: list[str] = []
            from_ = sel.args.get("from_") or sel.args.get("from")    # sqlglot 30 names the arg `from_`
            for src in ([from_.this] if from_ is not None else []) + [j.this for j in sel.args.get("joins") or []]:
                name = src.alias or (src.name if isinstance(src, exp.Table) else "")
                if name and name.upper() in tagged:
                    sources.append(tagged[name.upper()])
            if not sources:
                continue
            grouped = sel.args.get("group") is not None
            if not grouped and any(e.find(exp.AggFunc) is not None for e in sel.expressions):
                continue
            if any(isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star)) for e in sel.expressions):
                pass                                   # `*` already carries the tag column
            elif any((e.alias_or_name or "").lower() == _FIRM_COL for e in sel.expressions):
                pass
            else:
                sel.select(exp.alias_(exp.column(_FIRM_COL, table=sources[0]), _FIRM_COL), copy=False)
                if grouped:
                    sel.group_by(exp.column(_FIRM_COL, table=sources[0]), copy=False)
            tagged[alias.upper()] = alias
            changed = True
    # A CTE is read under the alias the model gave the reference (`FROM kapanan k`): the reference's
    # alias joins the tagged set so a JOIN on `k` finds its tag.
    for node in out.find_all(exp.Table):
        if node.name and node.name.upper() in tagged and node.alias and node.alias.upper() not in tagged:
            tagged[node.alias.upper()] = node.alias


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

    def foreign(x: SchemaProfile) -> int:
        # A table of another firm or period is not the one the deployment reads. Picked by rows, the
        # biggest copy of an entity won, and a question in logical terms was answered from firm 021.
        own = x.context or {}
        return int(any(k in own and str(own[k]) != str(v) for k, v in (context or {}).items()))

    for entity, group in tables_of.items():
        by_entity[entity] = min(group, key=lambda x: (foreign(x), source_rank(x.table_name, is_view=x.row_count is None),
                                                      -(x.row_count or 0), x.table_name))
    for p in profiles:
        # Every way a qualified name can reach this point: the prompt's label, a two- or three-part
        # reference, and a schema that carries a database ("Timas_MSCRM.dbo") read by the parser as
        # a database plus an underscored name.
        for name in {p.table_name, _spelling(p, {})}:
            by_table[_norm_key(p.schema_name, name)] = p
            by_table[f"{p.schema_name}_{name}".upper()] = p
            by_table[f"{p.schema_name}.{name}".upper()] = p

    def spread(prof: SchemaProfile) -> list[SchemaProfile]:
        """The tables of `prof`'s entity this period needs — one, unless the years span more.

        Never where the SQL already names more than one year of that pattern. A model told which
        table holds which year writes the UNION itself, and expanding each of its branches to the
        whole span again adds every year to itself: the answer comes back at twice the real figure
        with nothing about it looking wrong. Naming one table is the case this is for — the model
        picked a year and the question needs more than that one.
        """
        if already_spread.get(prof.table_pattern, 0) > 1:
            return [prof]
        same = [x for x in tables_of.get(prof.entity, []) if x.table_pattern == prof.table_pattern]
        if len(same) < 2:
            return [prof]
        if period is None:
            # No period from the question — but the statement itself may date its rows. Read the
            # years those literals ask for; failing that, the most recent table. The representative
            # (the biggest copy) is never the answer: a 2026 query was silently run against 2021–2025.
            start, end = _literal_period(tree)
            picked = periods.tables_for(same, start, end)
            return picked or [prof]
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
        found = by_table.get(_norm_key(node.catalog, node.db, node.name)) or by_table.get(node.name.upper())
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

    def resolve_prof(node: exp.Table):
        raw = node.name
        prof = by_table.get(_norm_key(node.catalog, node.db, raw)) or by_table.get(raw.upper())
        if prof is None:
            lt = logical_table(raw)
            prof = by_entity.get(lt.entity) if lt.table_pattern != lt.entity or lt.entity in by_entity else None
        return prof

    def wrote_physical(node: exp.Table) -> bool:
        """The model named an actual table (LG_411_01_INVOICE), not the entity. What it named, it meant."""
        return (by_table.get(_norm_key(node.catalog, node.db, node.name)) or by_table.get(node.name.upper())) is not None

    def is_dated(node: exp.Table, prof: SchemaProfile) -> bool:
        name_here = (node.alias or node.name or "").upper()
        return not dated_aliases or name_here in dated_aliases or prof.entity.upper() in dated_aliases

    # Which copies of the schema this statement reads. In this source every year is a separate
    # copy (firm 211 = 2021–2025, firm 411 = 2026) and an identifier is unique only inside one, so
    # the copies the dated relation spreads over decide the copies of *every* partitioned relation
    # beside it: the invoices of 2026 joined to the payment plan of 2021–2025 matched nothing, and
    # matched the wrong rows where a LOGICALREF happened to coincide.
    firms: list[str] = []
    for node in tree.find_all(exp.Table):
        if not node.name or node.name.upper() in cte_names:
            continue
        prof = resolve_prof(node)
        if prof is None or not is_dated(node, prof) or "{n0}" not in (prof.table_pattern or ""):
            continue
        if already_spread.get(prof.table_pattern, 0) > 1:
            continue                     # the model spread the years itself; its copies are its own
        for x in spread(prof):
            firm = str((x.context or {}).get("n0") or "")
            if firm and firm not in firms:
                firms.append(firm)
    tagged: dict[str, str] = {}       # upper-cased alias → alias as written, for relations carrying the tag

    def in_step(prof: SchemaProfile) -> list[SchemaProfile]:
        """A partitioned relation read from the same copies as the dated one, in the same order."""
        if not firms or "{n0}" not in (prof.table_pattern or ""):
            return []
        same = [x for x in tables_of.get(prof.entity, []) if x.table_pattern == prof.table_pattern]
        picked = [next((x for x in same if str((x.context or {}).get("n0") or "") == firm), None) for firm in firms]
        picked = [x for x in picked if x is not None]
        return picked

    def tx(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Table) and node.name:
            raw = node.name
            if raw.upper() in cte_names:
                return node
            prof = resolve_prof(node)
            if prof is None:
                return node
            lockstep = [] if wrote_physical(node) else in_step(prof)
            if lockstep:
                wanted = lockstep
            else:
                # Where the query says which relation carries the period, only that one is spread.
                wanted = spread(prof) if is_dated(node, prof) else [prof]
            if len(wanted) > 1:
                # One entity, several copies: read them as one relation so everything the model wrote
                # around it — the joins, the filters, the aggregate — is untouched. Each row carries the
                # copy it came from, so a join below only ever meets rows of its own copy.
                alias = node.alias or prof.entity
                parts = []
                for x in wanted:
                    firm = str((x.context or {}).get("n0") or "")
                    cols = [exp.alias_(exp.Literal.string(firm), _FIRM_COL), exp.Star()] if lockstep else [exp.Star()]
                    parts.append(exp.select(*cols).from_(_physical_table(x, context)))
                union: exp.Expression = parts[0]
                for nxt in parts[1:]:
                    union = exp.union(union, nxt, distinct=False)
                if lockstep:
                    tagged[alias.upper()] = alias
                return exp.Subquery(this=union, alias=exp.TableAlias(this=exp.to_identifier(alias)))
            new = _physical_table(wanted[0], context)
            # Without an alias the model qualifies columns by the name it wrote ("INVOICE.CLIENTREF").
            # Renaming the table and leaving that qualifier behind is a column the server cannot bind,
            # so the written name stays on as the alias.
            alias = node.alias or raw
            if alias.upper() != _spelling(wanted[0], context).upper():
                new.set("alias", exp.TableAlias(this=exp.to_identifier(alias)))
            return new
        return node

    out = tree.transform(tx)
    _carry_tag_through_derived(out, tagged)
    if len(tagged) > 1:
        # Two tagged relations meeting in a JOIN meet only within one copy.
        for join in out.find_all(exp.Join):
            on = join.args.get("on")
            if on is None:
                continue
            right = join.this.alias if isinstance(join.this, (exp.Subquery, exp.Table)) else None
            right = (right or "").upper()
            others = {c.table.upper() for c in on.find_all(exp.Column) if c.table and c.table.upper() in tagged and c.table.upper() != right}
            if right in tagged and others:
                left = sorted(others)[0]
                # aliases as the model wrote them: under a Turkish collation `I` is not the upper
                # case of `i`, so an upper-cased alias would name a relation that is not there
                join.set("on", exp.and_(on, exp.EQ(this=exp.column(_FIRM_COL, table=tagged[right]),
                                                    expression=exp.column(_FIRM_COL, table=tagged[left]))))
    # A column the model qualified by a name the rewrite no longer shows — the entity
    # ("NEW_PLANSORUMLULARIBASE.CreatedOn") while the table was written under its label, or the other
    # way round — cannot be bound by the server. When a relation of that entity appears exactly once,
    # the qualifier is pointed at the name it now carries.
    names_in_query: dict[str, list[str]] = {}
    prof_of_alias: dict[str, SchemaProfile] = {}
    for node in out.find_all(exp.Table, exp.Subquery):
        alias = node.alias_or_name if isinstance(node, exp.Table) else node.alias
        if not alias:
            continue
        prof = None
        if isinstance(node, exp.Table):
            prof = by_table.get(_norm_key(node.catalog, node.db, node.name)) or by_table.get(node.name.upper())
        else:
            prof = by_entity.get(alias.upper()) or by_table.get(alias.upper())
        if prof is None:
            continue
        prof_of_alias[alias.upper()] = prof
        for spelled in {prof.entity, prof.table_name, _spelling(prof, context),
                        f"{(prof.schema_name or '').replace('.', '_')}_{prof.table_name}"}:
            names_in_query.setdefault(spelled.upper(), []).append(alias)
    visible = {a.upper() for aliases in names_in_query.values() for a in aliases}
    for col in out.find_all(exp.Column):
        qual = (col.table or "").upper()
        if not qual or qual in visible:
            continue
        aliases = set(names_in_query.get(qual, []))
        if len(aliases) == 1:
            col.set("table", exp.to_identifier(next(iter(aliases))))
    # The column as the source spells it. The catalog and the compiler write names in upper case;
    # a server that compares identifiers case-sensitively (the CRM database) knows `statecode`, not
    # `STATECODE`. Where the qualifier names a profiled relation, the profile's spelling is used.
    for col in out.find_all(exp.Column):
        prof = prof_of_alias.get((col.table or "").upper())
        if prof is None or not col.name:
            continue
        real = next((c.name for c in prof.columns if c.name.upper() == col.name.upper()), None)
        if real and real != col.name:
            col.set("this", exp.to_identifier(real, quoted=col.this.quoted if isinstance(col.this, exp.Identifier) else False))
    # A CTE or table alias the model chose is a word, and a word can be a keyword: `WITH plan AS` is
    # a syntax error on SQL Server. Aliases are quoted; columns and real names stay as written.
    for cte in out.find_all(exp.CTE):
        if cte.alias:
            cte.args["alias"].set("this", exp.to_identifier(cte.alias, quoted=True))
    cte_upper = {c.alias.upper() for c in out.find_all(exp.CTE) if c.alias}
    for node in out.find_all(exp.Table):
        if node.name and node.name.upper() in cte_upper:
            node.set("this", exp.to_identifier(node.name, quoted=True))
        if node.alias:
            node.args["alias"].set("this", exp.to_identifier(node.alias, quoted=True))
    for sub in out.find_all(exp.Subquery):
        if sub.alias:
            sub.args["alias"].set("this", exp.to_identifier(sub.alias, quoted=True))
    return out.sql(dialect=dialect if dialect != "generic" else None)


def _norm_key(*parts: Optional[str]) -> str:
    """One spelling for a qualified table name, whatever separator put it together.

    "Timas_MSCRM.dbo_NEW_X", "[Timas_MSCRM].[dbo].[NEW_X]" and "Timas_MSCRM_dbo_NEW_X" are the same
    table; a lookup that only knew one of them sent the other to the server unchanged.
    """
    joined = "_".join(str(x) for x in parts if x)
    return joined.replace(".", "_").upper()


def _literal_period(tree) -> tuple:
    """[start, end) as the statement's own date literals bound it: the smallest lower bound and the
    largest upper bound written against a column. None, None when it writes none."""
    from datetime import date as _date
    lows, highs = [], []
    for node in tree.find_all(exp.GTE, exp.GT, exp.LT, exp.LTE):
        lit = node.right if isinstance(node.right, exp.Literal) else None
        if lit is None or not lit.is_string or not isinstance(node.left, exp.Column):
            continue
        text = lit.this[:10]
        try:
            d = _date.fromisoformat(text)
        except ValueError:
            continue
        (lows if isinstance(node, (exp.GTE, exp.GT)) else highs).append(d)
    if not lows and not highs:
        return None, None
    start = min(lows) if lows else None
    end = max(highs) if highs else None
    return start, end


def _spelling(prof: SchemaProfile, context: dict[str, str]) -> str:
    """The name as the database spells it.

    A pattern is upper-cased so one shape matches across periods, and for a source whose tables are
    already upper case that costs nothing. Elsewhere it does: under a Turkish collation `I` is the
    capital of `ı`, not of `i`, so an ASCII upper-case of `new_siparisBase` names a table the server
    does not have. Where the pattern carries no placeholder there is nothing to substitute, and the
    stored name is the truth.
    """
    if "{" not in (prof.table_pattern or ""):
        return prof.table_name or prof.table_pattern
    # A view or a copy can carry the pattern of a real firm table. If the pattern, filled with the
    # profile's own context, does not give back the name the profile was read from, the pattern
    # describes some other table and the stored name is the truth.
    if prof.table_name and physical_name(prof.table_pattern, prof.context or {}).upper() != prof.table_name.upper():
        return prof.table_name
    return physical_name(prof.table_pattern, {**prof.context, **context})


def _physical_table(prof: SchemaProfile, context: dict[str, str]) -> exp.Table:
    phys = _spelling(prof, context)
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
# HYT00 is the *query* timeout: the server was reached and worked until the driver gave up. Listed
# here it turned a slow question into "veri kaynağına ulaşılamıyor" — a correct query, a reachable
# database, and a message that sent people to check the network. It is a timeout, reported as one.
_CONNECTION_STATES = ("08S01", "08001", "08003", "08004", "08006", "08007", "HY000")
_TIMEOUT_STATES = ("HYT00", "HYT01")


def is_query_timeout(error: object) -> bool:
    text = str(error or "")
    return any(f"'{state}'" in text or f"[{state}]" in text for state in _TIMEOUT_STATES) or "timeout expired" in text.lower()
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
