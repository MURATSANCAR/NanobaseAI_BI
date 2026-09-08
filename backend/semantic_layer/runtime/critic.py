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
from sqlglot.optimizer.scope import Scope, build_scope

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
        for join in select.args.get("joins") or []:
            on = join.args.get("on")
            if on is None or not _in_scope(join, select):
                continue
            # Columns each side is joined on, gathered across the whole ON clause: a composite key
            # is only covered when every one of its columns is in the join, and a join that covers
            # half of one does not keep that side's rows unique.
            cols_by_alias: dict[str, set[str]] = {}
            for eq in on.find_all(exp.EQ):
                l, r = eq.left, eq.right
                if not (isinstance(l, exp.Column) and isinstance(r, exp.Column)):
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
            elif sides and not keyed:
                uncertain.update(sides)

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
                    else:
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

    order = {"block": 0, "warn": 1}
    seen: set[tuple] = set()
    out = []
    for f in sorted(findings, key=lambda f: order[f.severity]):
        if (f.kind, f.message) not in seen:
            seen.add((f.kind, f.message))
            out.append(f)
    return out
