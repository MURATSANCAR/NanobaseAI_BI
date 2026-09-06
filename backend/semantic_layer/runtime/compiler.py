"""Compilers: SemanticQuery → SQL.

DeterministicCompiler — no LLM; only when every slot is CERTIFIED and the query shape is
                        metric [+ dimension filters] [+ temporal] [+ group by column/grain] [+ limit/order].
ExistingCompiler      — the production LLM prompt (rules + recalled pairs + schema context) **plus**
                        certified catalog facts as hard constraints. Keeps 20/20 on complex questions.
CompilerRouter        — deterministic first, else LLM. SEMANTIC_STRICT_MISS refuses unresolved value terms.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from semantic_layer.models import CompiledQuery, ConceptStatus, Mapping, ResolvedSlot, SchemaProfile, SemanticQuery, SemanticType, TemporalSlot
from semantic_layer.naming import physical_name
from semantic_layer.normalize import fold
from semantic_layer.store.catalog_store import CatalogStore

log = logging.getLogger(__name__)


class SemanticQueryCompiler(Protocol):
    name: str

    def compile(self, query: SemanticQuery, catalog: CatalogStore) -> Optional[CompiledQuery]: ...


# ---------------------------------------------------------------------- dialect helpers

class Dialect:
    """Per-engine SQL shapes. Unknown engines fall back to the standard-SQL family (date_trunc/LIMIT),
    which is what every non-SQL-Server target this product connects to speaks."""

    def __init__(self, name: str):
        self.name = (name or "").lower() or "generic"

    @property
    def family(self) -> str:
        if self.name in ("tsql", "mssql", "sqlserver"):
            return "tsql"
        if self.name in ("sqlite",):
            return "sqlite"
        return "standard"

    def q(self, ident: str) -> str:
        return f"[{ident}]" if self.family == "tsql" else f'"{ident}"'

    def table(self, schema: str, name: str) -> str:
        return f"{self.q(schema)}.{self.q(name)}" if schema and self.family != "sqlite" else self.q(name)

    def bucket(self, col: str, grain: str) -> str:
        if self.family == "tsql":
            return {
                "DAY": f"CAST({col} AS DATE)",
                "WEEK": f"DATEADD(DAY, 1 - DATEPART(WEEKDAY, {col}), CAST({col} AS DATE))",
                "MONTH": f"DATEFROMPARTS(YEAR({col}), MONTH({col}), 1)",
                "QUARTER": f"DATEFROMPARTS(YEAR({col}), ((MONTH({col}) - 1) / 3) * 3 + 1, 1)",
                "YEAR": f"YEAR({col})",
            }[grain]
        if self.family == "sqlite":
            return {
                "DAY": f"date({col})",
                "WEEK": f"strftime('%Y-%W', {col})",
                "MONTH": f"strftime('%Y-%m-01', {col})",
                "QUARTER": f"(strftime('%Y', {col}) || '-Q' || ((cast(strftime('%m', {col}) as integer) + 2) / 3))",
                "YEAR": f"cast(strftime('%Y', {col}) as integer)",
            }[grain]
        return {
            "DAY": f"date_trunc('day', {col})",
            "WEEK": f"date_trunc('week', {col})",
            "MONTH": f"date_trunc('month', {col})",
            "QUARTER": f"date_trunc('quarter', {col})",
            "YEAR": f"date_trunc('year', {col})",
        }[grain]

    def limit(self, sql_select: str, n: int) -> str:
        if self.family == "tsql":
            return sql_select.replace("SELECT ", f"SELECT TOP {int(n)} ", 1)
        return sql_select + f"\nLIMIT {int(n)}"

    def null_div(self, a: str, b: str) -> str:
        return f"{a} / NULLIF({b}, 0)"


_ADDITIVE = re.compile(r"\b(SUM|AVG)\s*\(", re.I)


def _is_additive(formula: Optional[str]) -> bool:
    """Does this measure add up rows? COUNT(DISTINCT key) survives a fan-out; SUM(amount) does not."""
    f = formula or ""
    if not _ADDITIVE.search(f):
        return False
    return True


def _snake(term: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", fold(term)).strip("_")
    return s or "deger"


def _alias_of(slot: ResolvedSlot) -> str:
    """Stable alias from the catalog key (perakende_satis), not from the surface form (satislari)."""
    return _snake(str(slot.explain.get("normalized") or slot.term))


def _lit(v: str) -> str:
    try:
        float(v)
        return v
    except ValueError:
        return "'" + v.replace("'", "''") + "'"


def _pred_sql(alias: str, m: Mapping, d: Dialect) -> str:
    col = f"{alias}.{d.q(m.column)}"
    op = (m.operator or "IN").upper()
    if op in ("IN", "NOT IN"):
        return f"{col} {op} ({', '.join(_lit(v) for v in m.values)})"
    if op == "BETWEEN" and len(m.values) == 2:
        return f"{col} BETWEEN {_lit(m.values[0])} AND {_lit(m.values[1])}"
    if op == "=" and len(m.values) > 1:
        return f"{col} IN ({', '.join(_lit(v) for v in m.values)})"
    return f"{col} {op} {_lit(m.values[0])}"


def _pred_key_sql(entity: str, key: str, d: Dialect) -> Optional[str]:
    """'INVOICE.TRCODE IN (7,8,9)' (Predicate.key) → SQL over alias."""
    m = re.match(r"^(\w+)\.(\w+)\s+(IN|NOT IN|=|<>|>=|<=|>|<|BETWEEN)\s+\((.*)\)$", key)
    if not m:
        return None
    ent, col, op, vals = m.groups()
    if ent != entity:
        return None
    values = [v.strip() for v in vals.split(",") if v.strip()]
    return _pred_sql(entity, Mapping(concept_id="", entity=ent, table_pattern="", column=col, operator=op, values=values), d)


def _wrap_condition(formula_sql: str, pred: str) -> str:
    """SUM(x) → SUM(CASE WHEN pred THEN x ELSE 0 END) for every aggregate in the formula (sqlglot)."""
    import sqlglot
    from sqlglot import exp

    try:
        tree = sqlglot.parse_one(formula_sql, read="tsql")
        cond = sqlglot.parse_one(pred, read="tsql")
    except Exception:  # noqa: BLE001
        return formula_sql

    def tx(node: exp.Expression) -> exp.Expression:
        if isinstance(node, (exp.Sum, exp.Avg, exp.Min, exp.Max)):
            inner = node.this
            return type(node)(this=exp.Case(ifs=[exp.If(this=cond.copy(), true=inner)], default=exp.Literal.number(0)))
        if isinstance(node, exp.Count):
            inner = node.this
            if isinstance(inner, exp.Star):
                return exp.Sum(this=exp.Case(ifs=[exp.If(this=cond.copy(), true=exp.Literal.number(1))], default=exp.Literal.number(0)))
            return exp.Count(this=exp.Case(ifs=[exp.If(this=cond.copy(), true=inner)]))
        return node

    return tree.transform(tx).sql(dialect="tsql").replace("[", "[").replace("]", "]")


# ---------------------------------------------------------------------- deterministic

@dataclass
class _Plan:
    entity: str
    metrics: list[ResolvedSlot]
    filters: list[ResolvedSlot]
    group_cols: list[ResolvedSlot]
    joins: list[tuple[str, str, str, str]] = field(default_factory=list)   # (entity, column, ref_entity, ref_column)
    date_column: Optional[str] = None


class DeterministicCompiler:
    name = "deterministic"

    def __init__(self, profiles: list[SchemaProfile], context: dict[str, str], dialect: str = "tsql", *, default_filters: Optional[Callable[[str], list[Mapping]]] = None, conventions: Any = None):
        from semantic_layer.conventions import Conventions

        self.profiles = profiles
        self.by_entity = {p.entity: p for p in profiles}
        self.context = context
        self.d = Dialect(dialect)
        self._default_filters = default_filters or (lambda entity: [])
        self.conventions = conventions or Conventions.from_profiles(profiles)

    # -- capability check
    def plan(self, q: SemanticQuery) -> tuple[Optional[_Plan], str]:
        if q.unresolved:
            return None, "unresolved terms: " + ", ".join(q.unresolved)
        if any(t.ambiguous for t in q.temporal):
            return None, "ambiguous temporal term"
        if q.conflicts:
            return None, "conflicting filters on " + ", ".join(q.conflicts)
        if q.out_of_scope:
            return None, "period outside the data window: " + ", ".join(q.out_of_scope)
        if q.unhandled:
            return None, "qualifiers with no certified meaning: " + ", ".join(q.unhandled)
        if q.shape:
            return None, f"question asks for a {q.shape.lower()} this compiler cannot express"
        metrics = [s for s in q.metrics if s.mapping and s.mapping.formula]
        if not metrics:
            return None, "no certified metric"
        entities = {s.mapping.entity for s in metrics}
        if len(entities) != 1:
            return None, "metrics span multiple entities"
        entity = next(iter(entities))
        prof = self.by_entity.get(entity)
        if prof is None:
            return None, f"entity {entity} not profiled"
        filters = [s for s in q.filters if s.mapping]
        joins: list[tuple[str, str, str, str]] = []
        for s in filters:
            if s.mapping.entity != entity:
                j = self._join(entity, s.mapping.entity)
                if j is None:
                    return None, f"filter on {s.mapping.entity} cannot be joined to {entity}"
                if j not in joins:
                    joins.append(j)
        group_cols = [s for s in q.group_by if s.mapping and s.mapping.column]
        for s in group_cols:
            if s.mapping.entity != entity:
                j = self._join(entity, s.mapping.entity)
                if j is None:
                    return None, f"group column on {s.mapping.entity} cannot be joined to {entity}"
                if j not in joins:
                    joins.append(j)
        # A measure kept on the "one" side of a join is repeated once per row on the "many" side, so a
        # header total broken down by a line-level column silently multiplies. Refuse and say so; the
        # honest answer needs a pre-aggregate, not a bigger number.
        fanning = [j for j in joins if j[2] == entity]
        if fanning and any(_is_additive(s.mapping.formula) for s in metrics):
            others = ", ".join(sorted({j[0] for j in fanning}))
            return None, f"additive measure on {entity} would be multiplied by the join to {others}"
        # unresolved metric-like or column slots that are not group-by → we cannot express projections yet
        extra_cols = [s for s in q.slots if s.semantic_type == SemanticType.COLUMN and s not in group_cols]
        if extra_cols:
            return None, "column projections without group-by are not supported deterministically"
        date_col = self.conventions.time_column(entity)
        if (q.temporal or q.grain) and not date_col:
            return None, f"no date column on {entity}"
        return _Plan(entity, metrics, filters, group_cols, joins, date_col), "ok"

    def compile(self, q: SemanticQuery, catalog: CatalogStore) -> Optional[CompiledQuery]:
        plan, reason = self.plan(q)
        if plan is None:
            log.debug("deterministic compile refused: %s", reason)
            return None
        d = self.d
        prof = self.by_entity[plan.entity]
        alias = plan.entity
        select: list[str] = []
        group: list[str] = []
        order: list[str] = []
        explain: list[str] = []
        # bucket
        if q.grain and plan.date_column:
            b = d.bucket(f"{alias}.{d.q(plan.date_column)}", q.grain)
            select.append(f"{b} AS {_snake(q.grain.lower() if q.grain != 'MONTH' else 'ay')}")
            group.append(b)
            order.append(b)
            explain.append(f"kırılım: {q.grain} ({plan.date_column})")
        for s in plan.group_cols:
            col = f"{s.mapping.entity}.{d.q(s.mapping.column)}"
            select.append(f"{col} AS {_alias_of(s)}")
            group.append(col)
            explain.append(f"grup: '{s.term}' → {s.mapping.entity}.{s.mapping.column}")
        metric_aliases = []
        # pivot: several values on the same column ("perakende ile toptan … karşılaştır") → one conditional aggregate each
        by_col: dict[tuple[str, str], list[ResolvedSlot]] = {}
        for s in plan.filters:
            by_col.setdefault((s.mapping.entity, (s.mapping.column or "").upper()), []).append(s)
        pivots = [grp for grp in by_col.values() if len(grp) > 1]
        pivot_slots = {id(s) for grp in pivots for s in grp}
        for s in plan.metrics:
            formula = self._formula_sql(s.mapping.formula, plan.entity)
            malias = _alias_of(s)
            if pivots:
                for grp in pivots:
                    for f in grp:
                        pred = _pred_sql(f.mapping.entity, f.mapping, d)
                        palias = f"{_alias_of(f)}_{malias}"
                        select.append(f"{_wrap_condition(formula, pred)} AS {palias}")
                        metric_aliases.append(palias)
                        explain.append(f"pivot: '{f.term}' → {pred} için '{s.term}'")
            else:
                metric_aliases.append(malias)
                select.append(f"{formula} AS {malias}")
            explain.append(f"ölçü: '{s.term}' → {s.mapping.formula}")
        where: list[str] = []
        for m in self._default_filters(plan.entity):
            where.append(_pred_sql(alias, m, d))
            explain.append(f"varsayılan filtre: {m.entity}.{m.column} {m.operator} {m.values}")
        for s in plan.metrics:
            for key in (s.mapping.extra or {}).get("conditions") or []:
                p = _pred_key_sql(plan.entity, key, d)
                if p and p not in where:
                    where.append(p)
                    explain.append(f"ölçü kapsamı: {key}")
        for s in plan.filters:
            if id(s) in pivot_slots:
                continue
            p = _pred_sql(s.mapping.entity, s.mapping, d)
            if p not in where:
                where.append(p)
                explain.append(f"filtre: '{s.term}' → {p}")
        for grp in pivots:
            ent, col = grp[0].mapping.entity, grp[0].mapping.column
            vals = sorted({v for f in grp for v in f.mapping.values}, key=lambda v: (0, float(v)) if v.replace('.', '').lstrip('-').isdigit() else (1, v))
            where.append(_pred_sql(ent, Mapping(concept_id="", entity=ent, table_pattern="", column=col, operator="IN", values=vals), d))
        for t in q.temporal:
            if t.start and t.end and plan.date_column:
                col = f"{alias}.{d.q(plan.date_column)}"
                where.append(f"{col} >= '{t.start.isoformat()}' AND {col} < '{t.end.isoformat()}'")
                explain.append(f"dönem: {t.primitive} [{t.start}, {t.end})")
        sql = "SELECT " + ", ".join(select)
        sql += f"\nFROM {d.table(prof.schema_name, physical_name(prof.table_pattern, {**prof.context, **self.context}))} AS {alias}"
        for ent, col, ref_ent, ref_col in plan.joins:
            joined = ref_ent if ref_ent != plan.entity else ent
            rp = self.by_entity[joined]
            sql += f"\nJOIN {d.table(rp.schema_name, physical_name(rp.table_pattern, {**rp.context, **self.context}))} AS {joined} ON {ent}.{d.q(col)} = {ref_ent}.{d.q(ref_col)}"
        if where:
            sql += "\nWHERE " + "\n  AND ".join(where)
        if group:
            sql += "\nGROUP BY " + ", ".join(group)
        if plan.group_cols and not q.grain:
            order = [f"{metric_aliases[0]} {'DESC' if q.order_desc else 'ASC'}"]
        if order:
            sql += "\nORDER BY " + ", ".join(order)
        if q.limit:
            sql = d.limit(sql, q.limit)
        tables = [prof.table_name] + [self.by_entity[j[2] if j[2] != plan.entity else j[0]].table_name for j in plan.joins]
        return CompiledQuery(sql=sql, compiler=self.name, tables=tables, catalog_version=q.catalog_version, explain=explain, certified=True)

    # -- helpers
    def _join(self, entity: str, other: str) -> Optional[tuple[str, str, str, str]]:
        return self.conventions.join_path(entity, other)

    def _formula_sql(self, formula: str, entity: str) -> str:
        d = self.d
        def repl(m: re.Match) -> str:
            ent, col = m.group(1), m.group(2)
            return f"{ent}.{d.q(col)}"
        out = re.sub(r"\b([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\b", repl, formula)
        return out


# ---------------------------------------------------------------------- existing (LLM) compiler

SYSTEM_PROMPT = """Sen NanobaseAI BI'ın SQL üreticisisin. Görevin: kullanıcının Türkçe iş sorusunu, aşağıdaki fiziksel tablolar üzerinde çalışan TEK bir SELECT sorgusuna çevirmek.
Kurallar:
- Yalnız "## Tablolar" bölümündeki adları, verildikleri yazımla kullan; kolon adlarını çift tırnak içinde yaz.
- SQL lehçesi ve tarih kırılımı örnekleri "## Lehçe" bölümündedir; oradaki kalıpları kullan.
- SERTİFİKALI KATALOG bloğundaki eşlemeler kesindir: bir terim için verilen kolon/değer kümesini AYNEN kullan, başka değer uydurma.
- "## İş kuralları" bölümündeki varsayılan filtrelere ve tanımlara mutlaka uy.
- Yalnız SELECT üret; DML/DDL yok. Sonuç satır sayısını makul tut (TOP 50 gibi).
- ÇÖZÜMLENEMEYEN TERİMLER bloğundaki bir terimin fiziksel karşılığını kurallardan ve şemadan çıkaramıyorsan SQL yazma; tek satır: NO_SQL: <terim> anlamı katalogda tanımlı değil.
- KAPSAM DIŞI DÖNEM bloğu doluysa SQL yazma; tek satır: NO_SQL: <dönem> bu veri kaynağında yok.
- KARŞILANAMAYAN NİTELEYİCİLER bloğundaki sözcük konuyu daraltır ("bekleyen siparişler", "satmayan ürünler"). Şemadan karşılığını kesin olarak çıkaramıyorsan onu yok sayıp daha geniş bir soruyu cevaplama; tek satır: NO_SQL: '<niteleyici>' koşulu veride tanımlı değil.
- Bir eşlemenin yanında [baz — ...] yazıyorsa o rakamın hangi temelde tutulduğudur (KDV dahil/hariç, birim/toplam). Farklı bazdaki kolonları tek bir toplamda birleştirme; soru o bazı açıkça istemiyorsa bazı değiştirme.\n- İSTENEN BİÇİM oran ise tek bir toplam döndürme: payı, paydayı ve oranı birlikte ver.
- Çıktı biçimi: sadece ```sql ... ``` bloğu, başka açıklama yazma."""

_SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)
_VIEW_LINES = re.compile(r"(?i)(v_monthly_sales|v_channel_net|v_imprint_perf|sales_cube|line_cube|orders_cube|küp|cube|görünüm)")


def extract_sql(text: str) -> Optional[str]:
    m = _SQL_BLOCK.search(text or "")
    sql = (m.group(1) if m else (text or "")).strip().rstrip(";").strip()
    if not sql or sql.upper().startswith("NO_SQL"):
        return None
    if not re.match(r"(?is)^\s*(with|select)\b", sql):
        return None
    return sql


def clean_rules(text: str) -> str:
    """Drop guidance about objects this engine does not serve (materialised views / cubes of the
    previous stack); the remaining business rules are passed through untouched."""
    return "\n".join(line for line in (text or "").splitlines() if not _VIEW_LINES.search(line))


_DIALECT_NOTES = {
    "tsql": ('Hedef veritabanı SQL Server (T-SQL). LIMIT yerine TOP kullan; GROUP BY içinde takma ad veya sıra numarası kullanma, ifadeyi tekrar yaz. '
             'Ay kırılımı DATEFROMPARTS(YEAR(<tarih>), MONTH(<tarih>), 1); gün kırılımı CAST(<tarih> AS DATE).'),
    "postgres": ('Hedef veritabanı PostgreSQL. Ay kırılımı date_trunc(\'month\', <tarih>); gün kırılımı <tarih>::date; satır sınırı LIMIT.'),
    "sqlite": ("Hedef veritabanı SQLite. Ay kırılımı strftime('%Y-%m-01', <tarih>); satır sınırı LIMIT."),
}


class ExistingCompiler:
    name = "existing_llm"

    def __init__(self, llm, profiles: list[SchemaProfile], context: dict[str, str], *, rules_text: str = "", recall: Optional[Callable[[str], list[dict[str, str]]]] = None, model_naming: str = "mdl", dialect: str = "tsql", conventions: Any = None):
        from semantic_layer.conventions import Conventions

        self.llm = llm
        self.profiles = profiles
        self.context = context
        self.rules_text = clean_rules(rules_text)
        self.recall = recall
        self.model_naming = model_naming
        self.dialect = dialect
        self.conventions = conventions or Conventions.from_profiles(profiles)
        self.by_entity = {p.entity: p for p in profiles}
        # A local model has a fixed context; a schema does not. These bound what the prompt may carry.
        self.max_prompt_tables = int(os.environ.get("SEMANTIC_PROMPT_TABLES", "12"))
        self.max_prompt_columns = int(os.environ.get("SEMANTIC_PROMPT_COLUMNS", "60"))
        self.catalog_entities: set[str] = set()

    def table_label(self, p: SchemaProfile) -> str:
        phys = physical_name(p.table_pattern, {**p.context, **self.context})
        return f"{p.schema_name}_{phys}" if self.model_naming == "mdl" else f"{p.schema_name}.{phys}"

    def relevant_entities(self, q: SemanticQuery, recalled: list[dict[str, str]]) -> set[str]:
        """Which tables this question can possibly need.

        A schema of three hundred tables does not fit in a prompt, and sending it would drown the few
        that matter. The set is built from evidence, never from a list of names: the entities the
        resolver placed, the entities any certified concept maps to (the vocabulary someone has already
        written down), the tables a recalled example query used, and one join hop out from those.
        """
        wanted = {s.mapping.entity for s in q.slots if s.mapping}
        wanted |= set(self.catalog_entities)
        for r in recalled:
            for p in self.profiles:
                if self.table_label(p) in (r.get("sql") or ""):
                    wanted.add(p.entity)
        for entity in list(wanted):
            for other in self.by_entity:
                if other not in wanted and self.conventions.join_path(entity, other):
                    wanted.add(other)
        if not wanted:
            # nothing certified yet and nothing resolved: fall back to the biggest tables, which is what
            # a person opening this schema for the first time would look at
            ranked = sorted(self.profiles, key=lambda p: -(p.row_count or 0))
            wanted = {p.entity for p in ranked[: self.max_prompt_tables]}
        return wanted

    def model_index(self, entities: Optional[set[str]] = None) -> str:
        shown = [p for p in self.profiles if entities is None or p.entity in entities]
        lines = ["### Tablolar"]
        left_out = len(self.profiles) - len(shown)
        for p in shown:
            pk = ", ".join(p.primary_key) or "-"
            rels = "; ".join(f'{r["column"]} → {r["ref_entity"]}.{r["ref_column"]}' for r in p.relationships[:6])
            line = f'- {self.table_label(p)} ({p.entity}) · pk {pk} · {len(p.columns)} kolon'
            if p.description:
                line += f" — {p.description[:160]}"
            if rels:
                line += f" · ilişkiler: {rels}"
            lines.append(line)
        if left_out > 0:
            # never a silent cap: the model must know the schema it was shown is not the whole schema
            lines.append(f"- (bu soruyla ilgisi kurulamayan {left_out} tablo listelenmedi; burada olmayan bir tabloyu varsayma)")
        return "\n".join(lines)

    def schema_context(self, q: SemanticQuery, recalled: list[dict[str, str]], entities: Optional[set[str]] = None) -> str:
        wanted = entities if entities is not None else self.relevant_entities(q, recalled)
        lines = []
        for p in self.profiles:
            if p.entity not in wanted:
                continue
            cols = []
            for c in p.columns:
                desc = ""
                if c.sensitive:
                    desc = " [kişisel veri — seçme/gruplama, değerleri istemde yok]"
                elif c.is_enum() and c.meaningful_values():
                    desc = " {" + ", ".join(v for v, _ in c.meaningful_values()[:10]) + "}"
                elif c.ref_entity:
                    desc = f" → {c.ref_entity}.{c.ref_column}"
                if c.sentinel_values and not c.sensitive:
                    desc += f" [{', '.join(c.sentinel_values)} = değer yok]"
                cols.append(f'"{c.name}" {c.data_type}{desc}')
            lines.append(f"{self.table_label(p)}: " + ", ".join(cols[: self.max_prompt_columns]) +
                         (f" … (+{len(cols) - self.max_prompt_columns} kolon)" if len(cols) > self.max_prompt_columns else ""))
        return "\n".join(lines)

    def catalog_block(self, q: SemanticQuery) -> str:
        lines = []
        for s in q.slots:
            m = s.mapping
            if not m:
                continue
            if m.formula:
                cond = "; ".join((m.extra or {}).get("conditions") or [])
                lines.append(f"- ölçü '{s.term}' = {m.formula}" + (f" (kapsam: {cond})" if cond else "") + self._basis(m.formula))
            elif m.values:
                lines.append(f"- '{s.term}' = {m.entity}.{m.column} {m.operator} ({', '.join(m.values)}) [{s.status}]")
            elif m.column:
                lines.append(f"- '{s.term}' = {m.entity}.{m.column} kolonu" + self._basis(f"{m.entity}.{m.column}"))
        for t in q.temporal:
            if t.start and t.end:
                lines.append(f"- dönem '{t.text}' = DATE_ >= '{t.start.isoformat()}' AND DATE_ < '{t.end.isoformat()}'")
        return "\n".join(lines) or "(yok)"

    def _basis(self, expression: str) -> str:
        """Documented basis of every column the expression touches ("KDV hariç", "birim maliyet").

        A figure's basis decides whether two numbers may be added at all. It is written down by whoever
        documented the column, so it belongs beside the mapping instead of being rediscovered each time.
        """
        found: list[str] = []
        for prof in self.profiles:
            for col in prof.columns:
                if not col.unit:
                    continue
                if re.search(rf"\b{re.escape(prof.entity)}\.{re.escape(col.name)}\b", expression or ""):
                    note = f"{prof.entity}.{col.name}: {col.unit}"
                    if note not in found:
                        found.append(note)
        return f" [baz — {'; '.join(found)}]" if found else ""

    def build_messages(self, q: SemanticQuery, thread: list[dict[str, str]], *, recall: Optional[Callable[[str], list[dict[str, str]]]] = None) -> list[dict[str, str]]:
        """`recall` overrides the shared one for this call only — the compiler object is shared by every
        concurrent request and must never be mutated per request."""
        recall_fn = recall or self.recall
        recalled = recall_fn(q.question) if recall_fn else []
        examples = "\n\n".join(f"Soru: {r.get('nl')}\nSQL:\n{r.get('sql')}" for r in recalled if r.get("sql"))
        entities = self.relevant_entities(q, recalled)
        ctx = [
            "## Tablolar\n" + self.model_index(entities),
            "## Lehçe\n" + _DIALECT_NOTES.get(self.dialect, f"Hedef SQL lehçesi: {self.dialect}."),
            "## İş kuralları\n" + (self.rules_text or "(yok)"),
            "## SERTİFİKALI KATALOG (kesin eşlemeler)\n" + self.catalog_block(q),
            "## ÇÖZÜMLENEMEYEN TERİMLER\n" + (", ".join(q.unresolved) if q.unresolved else "(yok)"),
            "## KAPSAM DIŞI DÖNEM\n" + ("; ".join(q.explanation and [e for e in q.explanation if "kapsamı dışında" in e]) if q.out_of_scope else "(yok)"),
            "## KARŞILANAMAYAN NİTELEYİCİLER\n" + (", ".join(q.unhandled) if q.unhandled else "(yok)"),
            "## İSTENEN BİÇİM\n" + (
                "oran/pay — payı ve paydayı ayrı ayrı seç, oranı yüzde olarak göster; paydayı sorudan çıkar "
                "(kırılım varsa genel toplam, yoksa aynı ölçünün filtresiz hali)." if q.shape == "RATIO" else "(serbest)"
            ),
            "## Doğrulanmış örnek soru→SQL çiftleri\n" + (examples or "(yok)"),
            "## Şema bağlamı\n" + self.schema_context(q, recalled, entities),
        ]
        msgs = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + "\n\n".join(ctx)}]
        msgs.extend(thread[-6:])
        msgs.append({"role": "user", "content": q.question})
        return msgs

    def compile(self, q: SemanticQuery, catalog: CatalogStore, thread: Optional[list[dict[str, str]]] = None, *, recall: Optional[Callable[[str], list[dict[str, str]]]] = None) -> Optional[CompiledQuery]:
        t0 = time.perf_counter()
        messages = self.build_messages(q, thread or [], recall=recall)
        text = self.llm.chat(messages)
        ms = int((time.perf_counter() - t0) * 1000)
        sql = extract_sql(text)
        if not sql:
            reason = (text or "").strip().replace("NO_SQL:", "").strip()[:300]
            return CompiledQuery(sql="", compiler=self.name, catalog_version=q.catalog_version, explain=[f"NO_SQL: {reason}"], llm_ms=ms, certified=False)
        certified = not q.unresolved and all(s.status in ("CERTIFIED", "EXPLICIT") for s in q.slots)
        return CompiledQuery(sql=sql, compiler=self.name, catalog_version=q.catalog_version, explain=["LLM derledi; katalog gerçekleri istemde sert kısıt olarak verildi"], llm_ms=ms, certified=certified)

    def repair(self, q: SemanticQuery, sql: str, error: str, thread: Optional[list[dict[str, str]]] = None, *, recall: Optional[Callable[[str], list[dict[str, str]]]] = None) -> Optional[str]:
        messages = self.build_messages(q, thread or [], recall=recall)
        messages.append({"role": "assistant", "content": f"```sql\n{sql}\n```"})
        messages.append({"role": "user", "content": f"Bu sorgu veritabanı doğrulamasından geçmedi. Hata: {error}\nSorguyu düzelt, yalnız ```sql``` bloğu döndür."})
        return extract_sql(self.llm.chat(messages))


# ---------------------------------------------------------------------- router

class CompilerRouter:
    """Deterministic first, then the LLM. `primary` pins one compiler for a controlled experiment;
    `shadow` compilers run for measurement only and never change the answer."""

    def __init__(self, deterministic: Optional[DeterministicCompiler], existing: Optional[ExistingCompiler], *, strict_miss: bool = False, primary: str = "", shadow: Optional[list[Any]] = None, alternates: Optional[dict[str, Any]] = None):
        self.deterministic = deterministic
        self.existing = existing
        self.strict_miss = strict_miss
        self.primary = (primary or "").strip().lower()
        self.shadow = list(shadow or [])
        self.alternates = dict(alternates or {})
        self.shadow_results: list[dict[str, Any]] = []

    def _run_shadow(self, q: SemanticQuery, catalog: CatalogStore, chosen: CompiledQuery) -> None:
        for comp in self.shadow:
            try:
                out = comp.compile(q, catalog)
            except Exception as e:  # noqa: BLE001
                log.warning("shadow compiler %s failed: %s", getattr(comp, "name", comp), e)
                continue
            if out is None:
                continue
            self.shadow_results.append({"compiler": out.compiler, "sql": out.sql, "ms": out.llm_ms, "same_as_primary": out.sql.strip() == chosen.sql.strip(), "explain": out.explain})
            del self.shadow_results[:-50]

    def compile(self, q: SemanticQuery, catalog: CatalogStore, thread: Optional[list[dict[str, str]]] = None, *, recall: Optional[Callable[[str], list[dict[str, str]]]] = None) -> CompiledQuery:
        if self.primary:
            comp = {"deterministic": self.deterministic, "existing_llm": self.existing, "existing": self.existing}.get(self.primary) or self.alternates.get(self.primary)
            if comp is not None:
                out = comp.compile(q, catalog, thread, recall=recall) if getattr(comp, "name", "") == "existing_llm" else comp.compile(q, catalog)
                if out is not None:
                    self._run_shadow(q, catalog, out)
                    return out
        if self.deterministic is not None:
            out = self.deterministic.compile(q, catalog)
            if out is not None:
                self._run_shadow(q, catalog, out)
                return out
        if self.strict_miss and q.unresolved:
            return CompiledQuery(sql="", compiler="refused", catalog_version=q.catalog_version, explain=["strict mode: " + ", ".join(q.unresolved) + " katalogda tanımlı değil"], certified=False)
        if self.existing is None:
            for comp in self.alternates.values():
                out = comp.compile(q, catalog)
                if out is not None:
                    return out
            return CompiledQuery(sql="", compiler="none", catalog_version=q.catalog_version, explain=["no LLM compiler configured"], certified=False)
        out = self.existing.compile(q, catalog, thread, recall=recall)
        self._run_shadow(q, catalog, out)
        return out


def default_filters_provider(store: CatalogStore, tenant_id: str, datasource_id: str) -> Callable[[str], list[Mapping]]:
    def _get(entity: str) -> list[Mapping]:
        out = []
        for c in store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.DEFAULT_FILTER, status=ConceptStatus.CERTIFIED, limit=1000):
            for m in store.list_mappings(c.id):
                if m.entity == entity:
                    out.append(m)
        return out
    return _get


# ---------------------------------------------------------------------- summaries

def fast_summary(question: str, columns: list[str], rows: list[dict[str, Any]], total: int) -> str:
    """Deterministic Turkish summary — no LLM round-trip (saves ~10 s per question)."""
    def fmt(v: Any) -> str:
        if isinstance(v, bool):
            return "evet" if v else "hayır"
        if isinstance(v, int):
            return f"{v:,}".replace(",", ".")
        if isinstance(v, float):
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return str(v)
    if total == 0:
        return "Sorgu sonuç döndürmedi."
    if total == 1 and len(columns) == 1:
        return f"{columns[0]}: {fmt(rows[0][columns[0]])}"
    if total == 1:
        return "; ".join(f"{c}: {fmt(rows[0].get(c))}" for c in columns[:6])
    head = rows[:3]
    parts = []
    for r in head:
        parts.append(", ".join(f"{c}={fmt(r.get(c))}" for c in columns[:4]))
    return f"{total} satır döndü. İlk satırlar: " + " | ".join(parts)


__all__ = ["SemanticQueryCompiler", "DeterministicCompiler", "ExistingCompiler", "CompilerRouter", "Dialect", "default_filters_provider", "fast_summary", "extract_sql", "SYSTEM_PROMPT", "TemporalSlot"]
