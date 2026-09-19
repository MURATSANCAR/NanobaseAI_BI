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

import re

from dataclasses import dataclass
from typing import Optional

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from semantic_layer.models import SchemaProfile
from semantic_layer.naming import logical_table

_NUMERIC = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "money", "smallmoney", "double", "number")
_INFLATABLE = (exp.Sum, exp.Avg)   # COUNT(*) over a fan-out is also inflated; COUNT(DISTINCT) is not


@dataclass(frozen=True)
class Finding:
    kind: str          # FANOUT | NON_NUMERIC | UNKNOWN_COLUMN | UNKNOWN_JOIN | RATIO_BASE
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


@dataclass(frozen=True)
class _Rel:
    """FROM'daki bir kaynak: temel tablo ya da CTE/alt sorgu.

    Fan-out muhakemesi için gereken tek şey, bir satırı tekilleştiren kolon kümesi. Temel tabloda bu
    birincil anahtar; bir CTE'de ise GROUP BY anahtarı — CTE de sonuçta bir tablodur ve kendi
    tanecikliği vardır. Kritik bunu bilmezse modelin en sevdiği kalıbı (önce CTE'de topla, sonra
    birleştir) hiç okuyamaz ve şişmiş toplam ağdan geçer."""

    entity: str
    keys: frozenset[str]                        # boş: tekilleştiren kolon bilinmiyor
    profile: Optional[SchemaProfile] = None     # yalnız temel tabloda
    aggregated: frozenset[str] = frozenset()    # CTE'de zaten toplanmış çıktı kolonları
    grain: str = ""                             # insana okunur taneciklik ("fatura", "fatura×ürün")


def _keys_of(prof: SchemaProfile) -> frozenset[str]:
    ks = {k.upper() for k in prof.primary_key}
    ks |= {c.name.upper() for c in prof.columns if c.is_primary_key}
    return frozenset(ks)


_ALIAS_WORD = re.compile(r"[a-zçğıöşü]+", re.IGNORECASE)


def _names_side(agg: exp.Expression, sides: list["_Rel"], names: Optional[dict[str, set[str]]] = None) -> bool:
    """COUNT(*) AS musteri_sayisi: takma ad bu tarafın adını (entity, tablo adı, açıklaması, sözlükteki
    adları) taşıyor mu? Takma ad yoksa bilinmez → False."""
    parent = agg.parent
    alias = parent.alias if isinstance(parent, exp.Alias) else ""
    if not alias:
        return False
    words = {_fold(w) for w in _ALIAS_WORD.findall(alias) if len(w) >= 4}
    words -= {"sayisi", "sayi", "adet", "adedi", "toplam", "count"}
    for rel in sides:
        text = " ".join(filter(None, [rel.entity, rel.grain,
                                      rel.profile.table_name if rel.profile else "",
                                      rel.profile.description if rel.profile else ""]))
        vocab = {_fold(w) for w in _ALIAS_WORD.findall(text) if len(w) >= 4}
        for term in (names or {}).get((rel.entity or "").upper(), ()):
            vocab |= {_fold(w) for w in _ALIAS_WORD.findall(term) if len(w) >= 4}
        if any(a == v or a[:5] == v[:5] for a in words for v in vocab):
            return True
    return False


def _fold(w: str) -> str:
    return w.lower().translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))


def _under_function(col: exp.Column, top: exp.Expression) -> bool:
    """AVG(DATEDIFF(day, fatura.DATE_, odeme.DATE_)): the dates are arguments of a function whose
    result is the number averaged — not columns being summed. Arithmetic (+ − × ÷) and parentheses
    still count as summing the column itself."""
    # `top` itself is looked at too: in SUM(TRY_CAST(x AS FLOAT)) the conversion *is* the aggregate's
    # argument, and stopping short of it called a converted text column "not numeric".
    p = col.parent
    while p is not None:
        if isinstance(p, (exp.Func, exp.Cast)) and not isinstance(p, exp.AggFunc):
            return True
        if p is top:
            break
        p = p.parent
    return False


def _used_outside_joins(select: exp.Select) -> set[str]:
    """Aliases whose columns this SELECT reads anywhere but a JOIN … ON: selected, filtered,
    grouped, ordered. A table joined and never read is there to be counted."""
    used: set[str] = set()
    for col in select.find_all(exp.Column):
        if not _in_scope(col, select):
            continue
        p = col.parent
        in_on = False
        while p is not None and p is not select:
            if isinstance(p, exp.Join):
                in_on = True
                break
            p = p.parent
        if not in_on and col.table:
            used.add(col.table.upper())
    return used


def _in_scope(node: exp.Expression, select: exp.Select) -> bool:
    """Düğüm bu SELECT'e mi ait, yoksa içindeki bir alt sorguya mı. `find_all` alt sorgulara da
    iniyor; kapsam ayrımı yapılmazsa bir CTE'nin join'i dış sorgunun join'i sanılır."""
    p = node.parent
    while p is not None:
        if isinstance(p, exp.Select):
            return p is select
        p = p.parent
    return False


def _derived_rel(scope: "Scope", by_table: dict, by_entity: dict, cache: dict) -> Optional[_Rel]:
    """Bir CTE/alt sorgunun tanecikliği: GROUP BY anahtarı ve zaten toplanmış kolonları."""
    key = id(scope)
    if key in cache:
        return cache[key]
    cache[key] = None                                    # özyineleme kırıcı
    sel = scope.expression
    if not isinstance(sel, exp.Select):
        return None
    by_sql: dict[str, str] = {}
    aggregated: set[str] = set()
    for e in sel.expressions:
        name = (e.alias_or_name or "").upper()
        if not name:
            continue
        inner = e.this if isinstance(e, exp.Alias) else e
        by_sql[inner.sql()] = name
        if list(inner.find_all(exp.AggFunc)):
            aggregated.add(name)
    keys: set[str] = set()
    grain_label = ""
    group = sel.args.get("group")
    if group is not None:
        for g in group.expressions:
            nm = by_sql.get(g.sql()) or (g.name.upper() if isinstance(g, exp.Column) else "")
            if nm:
                keys.add(nm)
        # Gruplama kolonlarından biri kaynak tablonun birincil anahtarıysa tek başına süperanahtardır:
        # yanındaki YEAR(tarih) gibi ifadeler ona bağımlıdır, tanecikliği inceltmezler.
        for g in group.expressions:
            if not isinstance(g, exp.Column):
                continue
            src = _source_rel(scope, (g.table or ""), by_table, by_entity, cache)
            if src is not None and src.keys and {g.name.upper()} >= src.keys:
                nm = by_sql.get(g.sql()) or g.name.upper()
                keys = {nm}
                grain_label = src.entity          # "LOGICALREF seviyesinde" değil, "INVOICE seviyesinde"
                break
    rel = _Rel(entity=(scope.expression.parent.alias_or_name if isinstance(scope.expression.parent, exp.CTE) else "alt sorgu") or "alt sorgu",
               keys=frozenset(keys), aggregated=frozenset(aggregated),
               grain=grain_label or (", ".join(sorted(keys)) if keys else ""))
    cache[key] = rel
    return rel


def _source_rel(scope: "Scope", alias: str, by_table: dict, by_entity: dict, cache: dict) -> Optional[_Rel]:
    """Bu kapsamdaki takma adın arkasındaki ilişki — tablo ya da türetilmiş."""
    sources = {str(k).upper(): v for k, v in scope.sources.items()}
    src = sources.get(alias.upper()) if alias else (next(iter(scope.sources.values())) if len(scope.sources) == 1 else None)
    if src is None:
        return None
    if isinstance(src, exp.Table):
        prof = _resolve(src, by_table, by_entity)
        return None if prof is None else _Rel(prof.entity, _keys_of(prof), prof, grain=prof.entity)
    return _derived_rel(src, by_table, by_entity, cache)


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


def _bare_entity(name: str) -> str:
    return re.sub(r"^(?:DBO_)?(?:LG_)?", "", (name or "").upper())


def _side_aliases(node: exp.Expression) -> Optional[set[str]]:
    """The relations one side of a comparison reads. None: it reads a column nobody qualified, so
    which relation it belongs to is not written in the statement."""
    cols = list(node.find_all(exp.Column))
    if any(not c.table for c in cols):
        return None
    return {c.table.upper() for c in cols}


def _links_two_relations(eq: exp.EQ) -> bool:
    """`o2.ay = DATEADD(MONTH, -1, o1.ay)`, `LTRIM(RTRIM(CAST(T.KOD AS NVARCHAR(100)))) = G.kod`: a
    join key is a key whether or not it is written bare. What makes an equality a link between two
    relations is that its two sides read *different* relations — not that each side is a naked column.
    A side that reads nothing (`1 = 1`, `x.a = 5`) links nothing."""
    l, r = _side_aliases(eq.left), _side_aliases(eq.right)
    if l is None or r is None:
        # Unqualified columns on a side that does read columns: the reviewer cannot say it is NOT a
        # key. Fail open, as everywhere else here — provided both sides read something.
        return bool(list(eq.left.find_all(exp.Column))) and bool(list(eq.right.find_all(exp.Column)))
    return bool(l) and bool(r) and any(a != b for a in l for b in r)


def _lossy(node: exp.Expression) -> dict[tuple[str, str], exp.Expression]:
    """Columns read through a conversion that answers NULL when the value cannot be read (TRY_CAST,
    TRY_CONVERT, TRY_PARSE). The author wrote TRY_ because some rows are expected to fail; an
    aggregate silently leaves those rows out."""
    out: dict[tuple[str, str], exp.Expression] = {}
    for t in node.find_all((exp.TryCast, exp.Convert, exp.Anonymous)):
        if isinstance(t, exp.Anonymous) and not str(t.name or "").upper().startswith("TRY_"):
            continue
        if isinstance(t, exp.Convert) and not t.args.get("safe"):
            continue                                   # CONVERT fails loudly; only TRY_CONVERT answers NULL
        for c in t.find_all(exp.Column):
            out.setdefault(((c.table or "").upper(), c.name.upper()), t)
    return out


def _leg_aggregates(leg: exp.Expression, scope: "Scope") -> tuple[list[exp.AggFunc], Optional[exp.Select]]:
    """The aggregates one leg of a division is made of, and the SELECT they are computed in. A leg
    written as a column of a CTE/subquery (`t.tutar / t.adet`) is followed one level into it. Legs
    whose aggregates live in different SELECTs come back with home=None: two separately computed
    totals are different row sets on purpose (iade / satış) and are not this check's business."""
    direct = [a for a in leg.find_all(exp.AggFunc) if not a.find_ancestor(exp.Window)]
    if direct:
        return direct, scope.expression if isinstance(scope.expression, exp.Select) else None
    aggs: list[exp.AggFunc] = []
    homes: set[int] = set()
    home: Optional[exp.Select] = None
    sources = {str(k).upper(): v for k, v in scope.sources.items()}
    for c in leg.find_all(exp.Column):
        src = sources.get((c.table or "").upper()) if c.table else (next(iter(sources.values())) if len(sources) == 1 else None)
        if not isinstance(src, Scope) or not isinstance(src.expression, exp.Select):
            continue
        for e in src.expression.expressions:
            if (e.alias_or_name or "").upper() == c.name.upper():
                found = [a for a in e.find_all(exp.AggFunc) if not a.find_ancestor(exp.Window)]
                if found:
                    aggs += found
                    homes.add(id(src.expression))
                    home = src.expression
    return aggs, (home if len(homes) == 1 else None)


def _ratio_base(select: exp.Select, scope: "Scope", rels: dict[str, "_Rel"], tables: dict[str, SchemaProfile],
                narrowed: dict[str, set[str]], by_table: dict, by_entity: dict, cache: dict, dialect: str) -> list[Finding]:
    """A ratio whose numerator and denominator are not fed by the same rows.

    What can be read off the statement, and only that:
      1. NULL leg — one leg aggregates TRY_CAST(x) and the other never looks at x: rows where x cannot
         be read leave one leg and stay in the other. Always a bias when such rows exist; refused,
         with the rewrite that fixes it.
      2. Parent counted through its child — the denominator is COUNT(DISTINCT child.fk) and the table
         fk points at (catalog relationship) is not read, or is read through a join that drops parents
         without children. Whether "all parents" or "parents that have a child row" was meant is the
         question's reading, not the statement's; said, not refused.
    What it cannot see: which of two dates defines the period, whether a filter belongs to both legs
    by intent, anything behind a view or more than one CTE level away."""
    out: list[Finding] = []
    for div in select.find_all(exp.Div):
        if not _in_scope(div, select):
            continue
        n_aggs, n_home = _leg_aggregates(div.this, scope)
        d_aggs, d_home = _leg_aggregates(div.expression, scope)
        if not n_aggs or not d_aggs or n_home is None or d_home is None or n_home is not d_home:
            continue
        home_where = n_home.args.get("where")
        guarded = set(_lossy(home_where)) if home_where is not None else set()
        n_lossy: dict = {}
        d_lossy: dict = {}
        for a in n_aggs:
            n_lossy.update(_lossy(a))
        for a in d_aggs:
            d_lossy.update(_lossy(a))
        for mine, other, leg, other_leg in ((n_lossy, d_lossy, "pay", "payda"), (d_lossy, n_lossy, "payda", "pay")):
            missing = [k for k in mine if k not in other and k not in guarded]
            if missing:
                conv = mine[missing[0]].sql(dialect=dialect)
                out.append(Finding("RATIO_BASE", "block",
                    f"{div.sql(dialect=dialect)[:160]}: pay ve payda aynı kayıt kümesinden gelmiyor. {conv} okunamayan "
                    f"(NULL dönen) satırlar {leg} tarafından düşüyor ama {other_leg} tarafında sayılmaya devam ediyor; oran yanlı çıkar. "
                    f"İki tarafı da aynı satırlarla sınırla: {other_leg} toplamını CASE WHEN {conv} IS NOT NULL THEN … END içine al "
                    f"(ya da koşulu WHERE'e yaz)."))
        if n_home is not select:
            continue                                   # the parent/child reading below needs this scope's relations
        if not all(isinstance(a, exp.Count) for a in n_aggs):
            # "ciro / müşteri sayısı": a total per entity that has rows is the ordinary meaning. Only a
            # count over a count is a share *of the entities*, where the missing ones change the answer.
            continue
        for a in d_aggs:
            inner = a.this
            if not (isinstance(a, exp.Count) and isinstance(inner, exp.Distinct) and len(inner.expressions) == 1
                    and isinstance(inner.expressions[0], exp.Column)):
                continue
            col = inner.expressions[0]
            alias = (col.table or "").upper() if col.table else (next(iter(tables)) if len(tables) == 1 else "")
            prof = tables.get(alias)
            if prof is None:
                continue
            if _is_pk(prof, col.name):
                dropped = narrowed.get(alias)
                if dropped:
                    who = ", ".join(sorted(rels[x].entity for x in dropped if x in rels))
                    out.append(Finding("RATIO_BASE", "warn",
                        f"Oranın paydası yalnız {who} tarafında karşılığı olan {prof.entity} kayıtlarını sayıyor; "
                        f"karşılığı olmayan {prof.entity} kayıtları birleştirmede düştüğü için paydada yok."))
                continue
            parents = {_bare_entity(r.get("ref_entity") or "") for r in (prof.relationships or [])
                       if str(r.get("column") or "").upper() == col.name.upper() and r.get("ref_entity")}
            parents.discard(_bare_entity(prof.entity))
            if not parents:
                continue
            present = {x for x, rel in rels.items() if _bare_entity(rel.entity) in parents}
            if present and not any(narrowed.get(x) for x in present):
                # The parent is read and keeps its rows (LEFT JOIN from it): the statement could have
                # counted it directly, and counting the child's key is then a choice, not a loss.
                continue
            parent = ", ".join(sorted(parents))
            out.append(Finding("RATIO_BASE", "warn",
                f"Oranın paydası {parent} kayıtlarını {prof.entity} satırları üzerinden sayıyor; "
                f"{prof.entity} tablosunda hiç satırı olmayan {parent} kayıtları paydaya girmiyor. "
                f"Bütün {parent} kayıtlarına oran isteniyorsa payda {parent} tablosundan sayılmalı."))
    return out


def _mismatched_keys(tree: exp.Expression, by_table: dict, by_entity: dict, dialect: str) -> list[Finding]:
    """`PRCLIST.CARDREF = INVOICE.CLIENTREF`: two foreign keys that the catalog measured to point at
    different tables (items, customers) set equal — a join that matches rows by coincidence of
    numbers. Found wherever it is written, in a JOIN or a correlated WHERE, and refused with the
    relationships the catalog does know, so the repair goes through the right table."""
    alias_prof: dict[str, SchemaProfile] = {}
    for node in tree.find_all(exp.Table):
        if not node.name:
            continue
        prof = by_table.get(node.name.upper()) or by_entity.get(node.name.upper()) or by_entity.get(_bare_entity(node.name)) \
            or by_entity.get("LG_" + _bare_entity(node.name))
        if prof is not None:
            alias_prof[(node.alias or node.name).upper()] = prof
            alias_prof.setdefault(node.name.upper(), prof)

    def targets(prof: SchemaProfile, column: str) -> set[str]:
        return {_bare_entity(r.get("ref_entity") or "") for r in (prof.relationships or [])
                if str(r.get("column") or "").upper() == column.upper() and r.get("ref_entity")}

    out: list[Finding] = []
    seen: set[str] = set()
    for eq in tree.find_all(exp.EQ):
        l, r = eq.left, eq.right
        if not (isinstance(l, exp.Column) and isinstance(r, exp.Column)) or not l.table or not r.table:
            continue
        pl, pr = alias_prof.get(l.table.upper()), alias_prof.get(r.table.upper())
        if pl is None or pr is None or pl is pr:
            continue
        tl, tr = targets(pl, l.name), targets(pr, r.name)
        if not tl or not tr:
            continue                                   # a key against a non-key: the join checks above judge it
        if tl & tr or _bare_entity(pr.entity) in tl or _bare_entity(pl.entity) in tr:
            continue                                   # the same target, or one side is the other's target
        key = f"{pl.entity}.{l.name}={pr.entity}.{r.name}"
        if key in seen:
            continue
        seen.add(key)
        known = "; ".join(f"{pl.entity}.{l.name} → {', '.join(sorted(tl))}" for _ in [0]) + "; " + \
                "; ".join(f"{pr.entity}.{r.name} → {', '.join(sorted(tr))}" for _ in [0])
        out.append(Finding("UNKNOWN_JOIN", "block",
            f"{eq.sql(dialect=dialect)}: iki kolon katalogda farklı tablolara giden anahtarlar ({known}); "
            f"eşitlenmeleri satırları rastlantıyla eşler. Bağlantıyı bu anahtarların gerçek hedefi üzerinden kur."))
    return out


def review(sql: str, profiles: list[SchemaProfile], dialect: str = "tsql",
           names: Optional[dict[str, set[str]]] = None) -> list[Finding]:
    """Findings about `sql`, most serious first. Empty when there is nothing to say or nothing to read.
    `names`: entity → the words the business calls it by (catalog vocabulary), for reading aliases."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001
        try:
            tree = sqlglot.parse_one(sql)
        except Exception:  # noqa: BLE001
            return []
    by_table, by_entity = _profiles_by_name(profiles)
    findings: list[Finding] = []
    try:
        root = build_scope(tree)
    except Exception:  # noqa: BLE001
        root = None
    if root is None:
        return []
    cache: dict[int, Optional[_Rel]] = {}

    for scope in root.traverse():
        select = scope.expression
        if not isinstance(select, exp.Select):
            continue
        # Which alias names which relation, within this scope. A CTE is a relation too.
        rels: dict[str, _Rel] = {}
        for alias in scope.sources:
            rel = _source_rel(scope, str(alias), by_table, by_entity, cache)
            if rel is not None:
                rels[str(alias).upper()] = rel
        tables: dict[str, SchemaProfile] = {a: r.profile for a, r in rels.items() if r.profile is not None}
        if not rels:
            continue

        # Each join: which side keeps its rows and which side gets repeated. The side whose join
        # column is its own primary key matches at most one row per row of the other side, so the
        # other side's rows are preserved and *this* side's rows are repeated once per match.
        repeated: set[str] = set()           # aliases whose rows are multiplied by a join
        uncertain: set[str] = set()          # neither side keyed: could go either way
        many_of: dict[str, set[str]] = {}    # keyed alias → the many-sided aliases joined to it
        chasm: set[str] = set()              # many-sided aliases multiplied by a sibling many-side
        narrowed: dict[str, set[str]] = {}   # keyed alias → the aliases whose join drops its unmatched rows
        for join in select.args.get("joins") or []:
            on = join.args.get("on")
            if on is None or not _in_scope(join, select):
                continue
            # `JOIN x ON 1 = 1`: every row of one side against every row of the other. Nothing keyed,
            # nothing meant — a cross product wearing a JOIN. Refused before any aggregate is looked at.
            if not any((isinstance(eq.left, exp.Column) and isinstance(eq.right, exp.Column)) or _links_two_relations(eq)
                       for eq in on.find_all(exp.EQ)):
                findings.append(Finding("FANOUT", "block",
                    f"{join.sql(dialect=dialect)[:80]}: iki tabloyu bağlayan kolon eşitliği yok (çapraz birleştirme); "
                    f"her satır diğer tablonun her satırıyla çoğalıyor. JOIN'i ilişki kolonları üzerinden yaz."))
                continue
            # Columns each side is joined on, gathered across the whole ON clause: a composite key
            # is only covered when every one of its columns is in the join, and a join that covers
            # half of one does not keep that side's rows unique.
            cols_by_alias: dict[str, set[str]] = {}
            for eq in on.find_all(exp.EQ):
                l, r = eq.left, eq.right
                if not (isinstance(l, exp.Column) and isinstance(r, exp.Column)):
                    # A key written inside a function (`o2.ay = DATEADD(MONTH, -1, o1.ay)`). The bare
                    # side is joined on that column as written. The wrapped side takes part in the
                    # join but covers no key: a function can send two rows to one value, so it proves
                    # nothing about that side's uniqueness.
                    ls, rs = _side_aliases(l), _side_aliases(r)
                    if ls and rs and len(ls) == 1 and len(rs) == 1 and ls != rs:
                        (wa,), (wb,) = tuple(ls), tuple(rs)
                        if wa in rels and wb in rels:
                            for side_alias, node in ((wa, l), (wb, r)):
                                cols = cols_by_alias.setdefault(side_alias, set())
                                if isinstance(node, exp.Column):
                                    cols.add(node.name.upper())
                    continue
                la, ra = (l.table or "").upper(), (r.table or "").upper()
                if la == ra or la not in rels or ra not in rels:
                    continue
                cols_by_alias.setdefault(la, set()).add(l.name.upper())
                cols_by_alias.setdefault(ra, set()).add(r.name.upper())
                # A join the catalog has no relationship for — only said where the catalog has
                # relationships for these tables at all, so a graph still being filled in stays quiet.
                lp, rp = tables.get(la), tables.get(ra)
                if lp is None or rp is None:
                    continue
                known = [(x["column"].upper(), x["ref_entity"], (x.get("ref_column") or "").upper())
                         for x in (lp.relationships or []) + (rp.relationships or [])]
                if known:
                    pairs = {(l.name.upper(), rp.entity, r.name.upper()), (r.name.upper(), lp.entity, l.name.upper())}
                    if not any((c, e, rc) in pairs or (c, e) in {(a, b) for a, b, _ in pairs} for c, e, rc in known):
                        findings.append(Finding("UNKNOWN_JOIN", "warn",
                            f"{lp.entity}.{l.name} = {rp.entity}.{r.name} bağlantısı katalogdaki ilişkilerde yok; "
                            f"bu iki tablo bu kolonlar üzerinden birleşmeyebilir."))
            sides = set(cols_by_alias)
            keyed = {a for a in sides if rels[a].keys and rels[a].keys <= cols_by_alias[a]}
            if keyed and (sides - keyed):
                # The keyed side matches at most one row per row of the other side, so *its* rows are
                # the ones repeated — once per matching row on the other side.
                repeated.update(keyed)
                for k in keyed:
                    many_of.setdefault(k, set()).update(sides - keyed)
                # …and unless the join keeps them, its rows without a match are gone: a parent with no
                # child row does not survive an INNER JOIN to the child, nor a WHERE on the child.
                joined = (join.this.alias_or_name or "").upper()
                side = (join.side or "").upper()
                where = select.args.get("where")
                for k in keyed:
                    kept = side == "FULL" or (side == "LEFT" and joined != k) or (side == "RIGHT" and joined == k)
                    if kept and where is not None:
                        kept = not any((c.table or "").upper() in (sides - keyed) and not isinstance(c.parent, exp.Is)
                                       for c in where.find_all(exp.Column) if _in_scope(c, select))
                    if not kept:
                        narrowed.setdefault(k, set()).update(sides - keyed)
            elif sides and not keyed:
                uncertain.update(sides)
        # Two many-sided relations hung off the same key (items ← order lines, items ← stock lines):
        # every order line meets every stock line of its item, and a sum on either side is multiplied
        # by the other's row count. Neither side is keyed, so the rule above sees nothing — this is
        # the join shape that returned 2.000 pending postcards for an order of 100.
        for k, manys in many_of.items():
            if len(manys) > 1:
                repeated.update(manys)
                chasm.update(manys)

        for agg in select.find_all(exp.AggFunc):
            if not _in_scope(agg, select):
                continue
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
                    who = ", ".join(sorted(rels[a].entity for a in aliases if a in rels))
                    idle = {a for a in aliases if a not in _used_outside_joins(select)}
                    if not cols and not idle and not _names_side(agg, [rels[a] for a in aliases if a in rels], names):
                        # COUNT(*) over a join made on the other side's key counts the rows of the
                        # fine-grained side — one per match, nothing repeated — and that is the figure
                        # asked for ("kapanan kalem" per customer group, grouped by a CLCARD column).
                        # It is inflated only when the count is meant to be *of* the keyed entity, and
                        # two things say so: the alias names it ("musteri_sayisi" over CLCARD), or the
                        # keyed table is joined and then used nowhere — a join that contributes no
                        # column exists only to be counted. Both still block. Logo declares no keys, so
                        # blocking every lookup join here sent correct queries back for repair.
                        findings.append(Finding("FANOUT", "warn",
                            f"{agg.sql(dialect=dialect)} ince tarafın satırlarını sayıyor; {who} sayısı isteniyorsa "
                            f"COUNT(DISTINCT {who}.<anahtar>) kullan."))
                        continue
                    # Summing a column a CTE already aggregated is the same fault one level up, and
                    # worth naming as such: the figure was correct at its own grain and is being
                    # re-added once per row of the finer table it was joined to.
                    twice = [c for c in (hit if cols else []) if c is not None
                             and c.name.upper() in rels.get((c.table or "").upper(), _Rel("", frozenset())).aggregated]
                    if twice:
                        c0 = twice[0]
                        r0 = rels[(c0.table or "").upper()]
                        findings.append(Finding("FANOUT", "block",
                            f"{agg.sql(dialect=dialect)} şişirilmiş: {c0.name} zaten {r0.grain or r0.entity} seviyesinde "
                            f"toplanmış bir tutar ve join onu daha ince taneli tarafın her satırında bir daha sayıyor. "
                            f"Toplamı tek bir taneciklikte al: ya kendi seviyesinde topla, ya da ince tarafta tutulan "
                            f"satır tutarını kullan."))
                    elif isinstance(agg, (exp.Avg, exp.Min, exp.Max)):
                        # An average is not multiplied by repetition, it is weighted by it: the mean
                        # payment term over plan lines repeats each invoice's date once per line, and
                        # that per-line mean is the figure asked for. Said, not refused.
                        findings.append(Finding("FANOUT", "warn",
                            f"{agg.sql(dialect=dialect)}: {who} satırları join'de tekrarlanıyor; ortalama ince "
                            f"tarafın satır sayısıyla ağırlıklı. {who} başına ortalama isteniyorsa önce o seviyede topla."))
                    elif aliases & chasm:
                        others = ", ".join(sorted(rels[a].entity for a in (chasm - aliases) if a in rels)) or "diğer ilişki"
                        findings.append(Finding("FANOUT", "block",
                            f"{agg.sql(dialect=dialect)} şişirilmiş: {who} satırları aynı anahtara bağlı ikinci bir "
                            f"çoklu ilişkinin ({others}) satır sayısıyla çarpılıyor. Her çoklu ilişkiyi kendi alt "
                            f"sorgusunda (anahtar bazında) topla, sonra anahtar üzerinden birleştir."))
                    else:
                        findings.append(Finding("FANOUT", "block",
                            f"{agg.sql(dialect=dialect)} şişirilmiş: {who} tablosunun satırları join yüzünden "
                            f"tekrarlanıyor ve toplama her tekrarı bir daha sayıyor. Toplamı tekrarlanmayan tarafta al, "
                            f"ya da önce alt sorguda tekilleştir."))
                elif cols and any((c.table or "").upper() in uncertain for c in cols):
                    findings.append(Finding("FANOUT", "warn",
                        f"{agg.sql(dialect=dialect)}: join'in iki tarafı da anahtar değil; satırlar çoğalıyor olabilir."))
            if isinstance(agg, (exp.Sum, exp.Avg)):
                # A column inside a CASE's WHEN is a condition, not a summed value:
                # SUM(CASE WHEN tarih >= '…' THEN tutar END) sums an amount and tests a date. Counted
                # among the summed columns, the date made every conditional aggregate look like a sum
                # over a non-numeric column — and a period comparison is written exactly this way.
                tested = {id(col) for pred in (inner.find_all(exp.Predicate) if isinstance(inner, exp.Expression) else [])
                          for col in pred.find_all(exp.Column)}
                for c in [x for x in cols if id(x) not in tested and not _under_function(x, inner)]:
                    prof = tables.get((c.table or "").upper()) if c.table else (next(iter(tables.values())) if len(tables) == 1 else None)
                    if prof is None:
                        continue
                    num = _is_numeric(prof, c.name)
                    if num is False:
                        findings.append(Finding("NON_NUMERIC", "block",
                            f"{agg.sql(dialect=dialect)}: {prof.entity}.{c.name} sayısal değil "
                            f"({prof.column(c.name).data_type}); bu kolon toplanamaz."))

        findings += _ratio_base(select, scope, rels, tables, narrowed, by_table, by_entity, cache, dialect)

        # Two figures kept on different bases, added together. The catalog records the basis a
        # column is on ("KDV dahil", "satır brüt") because mixing them produces a total that is
        # arithmetically fine and means nothing — and no error, no empty result and no odd-looking
        # number gives it away.
        for agg in select.find_all((exp.Sum, exp.Avg)):
            if not _in_scope(agg, select):
                continue
            bases: dict[str, list[str]] = {}
            for col in agg.find_all(exp.Column):
                prof = tables.get((col.table or "").upper()) if col.table else (next(iter(tables.values())) if len(tables) == 1 else None)
                c = prof.column(col.name) if prof else None
                if c is not None and c.unit:
                    bases.setdefault(c.unit, []).append(f"{prof.entity}.{c.name}")
            if len(bases) > 1:
                pairs = "; ".join(f"{', '.join(v)} = {k}" for k, v in sorted(bases.items()))
                findings.append(Finding("MIXED_BASIS", "block",
                    f"{agg.sql(dialect=dialect)}: farklı bazdaki tutarlar toplanıyor ({pairs}). "
                    f"Aynı toplamda birleştirilemezler."))

        # A value compared against a column whose complete value set the catalog holds. Filtering on
        # something that is not in it returns nothing, and an empty result reads as "none this month"
        # rather than as a filter that could never have matched.
        for eq in select.find_all(exp.EQ):
            if not _in_scope(eq, select):
                continue
            for col, lit in ((eq.left, eq.right), (eq.right, eq.left)):
                if not (isinstance(col, exp.Column) and isinstance(lit, exp.Literal)):
                    continue
                prof = tables.get((col.table or "").upper()) if col.table else (next(iter(tables.values())) if len(tables) == 1 else None)
                c = prof.column(col.name) if prof else None
                if c is None or c.sensitive or not c.is_enum():
                    continue
                known = {str(v) for v, _ in c.top_values}
                asked = str(lit.this)
                if known and asked not in known:
                    findings.append(Finding("UNKNOWN_VALUE", "warn",
                        f"{prof.entity}.{c.name} = {asked}: bu kolonda böyle bir değer ölçülmedi "
                        f"(görülenler: {', '.join(sorted(known)[:8])}). Sonuç boş dönebilir."))

        # A table this deployment holds and has never loaded a row into. The query is valid and its
        # result will be empty; that is worth saying, because an empty result otherwise reads as a
        # fact about the business rather than about the deployment.
        for alias, prof in tables.items():
            if prof.row_count == 0:
                findings.append(Finding("EMPTY_TABLE", "warn",
                    f"{prof.entity} tablosu bu kurulumda boş — hiç kayıt yok; sonuç boş dönecek."))

        # A column the catalog says the table does not have.
        for c in select.find_all(exp.Column):
            if not c.table or not _in_scope(c, select):
                continue
            prof = tables.get(c.table.upper())
            if prof is None or not prof.columns or c.name == "*":
                continue
            if prof.column(c.name) is None:
                findings.append(Finding("UNKNOWN_COLUMN", "block",
                    f"{prof.entity} tablosunda {c.name} adında kolon yok."))

    findings += _mismatched_keys(tree, by_table, by_entity, dialect)
    order = {"block": 0, "warn": 1}
    seen: set[tuple] = set()
    out = []
    for f in sorted(findings, key=lambda f: order[f.severity]):
        if (f.kind, f.message) not in seen:
            seen.add((f.kind, f.message))
            out.append(f)
    return out
