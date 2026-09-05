"""PostgreSQL metric compiler — logical plan → deterministic SQL."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.domain.filter_rule import FilterRule
from nanobase_api.semantic_catalog.domain.join_rule import JoinRule
from nanobase_api.semantic_catalog.domain.metric import Metric

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

TimeGrain = str  # "day" | "week" | "month" | "quarter" | "year"
TIME_GRAINS: tuple[str, ...] = ("day", "week", "month", "quarter", "year")
_ORACLE_TRUNC_FMT = {"day": "DD", "week": "IW", "month": "MM", "quarter": "Q", "year": "YYYY"}
PERIOD_ALIAS = "period"


def _quote_ident(parts: str, *, dialect: str = "postgres") -> str:
    """Quote schema.table or column — Postgres quoted; Oracle unquoted uppercase."""
    if not _IDENT.match(parts.replace('"', "")):
        raise ValidationError(f"Geçersiz identifier: {parts}")
    bits = parts.replace('"', "").split(".")
    if dialect == "oracle":
        return ".".join(b.upper() for b in bits)
    return ".".join(f'"{b}"' for b in bits)


def _alias_for(table: str, *, dialect: str = "postgres") -> str:
    # Deterministic short alias from last segment
    name = table.split(".")[-1]
    alias = name[:1].lower() if name else "t"
    if dialect == "oracle":
        return alias.upper()
    return alias


@dataclass
class CompileRequest:
    metric: Metric
    filters: list[FilterRule] = field(default_factory=list)
    joins: list[JoinRule] = field(default_factory=list)
    period: dict[str, str] | None = None
    dimension_filters: dict[str, Any] = field(default_factory=dict)
    # Plain column names on metric.source.table to GROUP BY (breakdown
    # questions: "segmentlere göre ciro"). Deliberately NOT a join/dimension
    # object — every dimension this compiler groups by must already be a
    # column on the metric's own source (a pre-joined view), same constraint
    # as metric.source itself. Validated against ALLOWED_IDENT (no arbitrary
    # SQL) before use.
    group_by: list[str] = field(default_factory=list)
    # Ranking questions ("ilk 3 müşteri", "en çok satılan ürün"): order by the
    # aggregate value and cap the row count. limit=None means an unranked full
    # breakdown (still ordered by the aggregate, descending, for readability).
    limit: int | None = None
    order_desc: bool = True
    # Time-series questions ("aylık ciro", forecasting history): bucket the
    # metric's own time field with date_trunc and ORDER BY period ASC.
    # Requires metric.time. Rows come back oldest→newest, one per bucket
    # (buckets with no rows are absent — SeriesBundleBuilder fills them).
    time_grain: TimeGrain | None = None
    dialect: str = "postgres"


@dataclass
class CompileResult:
    sql: str
    logical_plan: dict[str, Any]
    ast_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "logicalPlan": self.logical_plan,
            "astFingerprint": self.ast_fingerprint,
        }


class MetricCompiler:
    """Compile logical metrics to Postgres or Oracle SQL (Query Gateway compatible)."""

    def compile(self, req: CompileRequest) -> CompileResult:
        dialect = (req.dialect or "postgres").lower()
        if dialect in ("postgresql", "postgres"):
            dialect = "postgres"
        elif dialect != "oracle":
            raise ValidationError(f"Desteklenmeyen dialect: {req.dialect}")

        metric = req.metric
        table = metric.source.table
        alias = _alias_for(table, dialect=dialect)
        col = metric.source.column.split(".")[-1]

        if dialect == "oracle":
            col_sql = f"{alias}.{col.upper()}"
            if metric.null_policy == "ZERO":
                expr = f"NVL({col_sql}, 0)"
            else:
                expr = col_sql
            agg = metric.aggregation.upper()
            select_expr = f"{agg}({expr}) AS {metric.code.upper()}"
            from_sql = f"FROM {_quote_ident(table, dialect=dialect)} {alias}"
        else:
            col_sql = f'{alias}."{col}"'
            if metric.null_policy == "ZERO":
                expr = f"COALESCE({col_sql}, 0)"
            else:
                expr = col_sql
            agg = metric.aggregation.upper()
            select_expr = f'{agg}({expr}) AS "{metric.code}"'
            from_sql = f"FROM {_quote_ident(table, dialect=dialect)} {alias}"

        join_sql_parts: list[str] = []
        for j in sorted(req.joins, key=lambda x: x.code):
            if j.from_table != table and j.to_table != table:
                continue
            other = j.to_table if j.from_table == table else j.from_table
            other_alias = _alias_for(other, dialect=dialect)
            conds = []
            for c in j.conditions:
                left = self._qualify(c.left, {table: alias, other: other_alias}, dialect=dialect)
                right = self._qualify(c.right, {table: alias, other: other_alias}, dialect=dialect)
                conds.append(f"{left} {c.operator} {right}")
            join_sql_parts.append(
                f"{j.join_type} JOIN {_quote_ident(other, dialect=dialect)} {other_alias} "
                f"ON {' AND '.join(conds)}"
            )

        where_parts: list[str] = []
        filter_by_code = {f.code: f for f in req.filters}
        for code in sorted(metric.default_filter_codes):
            fr = filter_by_code.get(code)
            if fr is None:
                raise ValidationError(f"Filter bulunamadı: {code}")
            where_parts.append(self._compile_filter(fr, {table: alias}, dialect=dialect))

        for fr in sorted(req.filters, key=lambda x: x.code):
            if fr.mandatory and fr.code not in metric.default_filter_codes:
                where_parts.append(self._compile_filter(fr, {table: alias}, dialect=dialect))

        if req.period and metric.time:
            tf = metric.time.time_field
            col_name = tf.split(".")[-1]
            if dialect == "oracle":
                time_sql = f"{alias}.{col_name.upper()}"
                if req.period.get("from"):
                    where_parts.append(f"{time_sql} >= :PERIOD_START")
                if req.period.get("to"):
                    where_parts.append(f"{time_sql} < :PERIOD_END")
            else:
                time_sql = f'{alias}."{col_name}"'
                if req.period.get("from"):
                    where_parts.append(f"{time_sql} >= '{req.period['from']}'")
                if req.period.get("to"):
                    where_parts.append(f"{time_sql} < '{req.period['to']}'")

        for dim_code, value in sorted(req.dimension_filters.items()):
            if "." in dim_code:
                parts = dim_code.split(".")
                cname = parts[-1]
            else:
                cname = dim_code
            if dialect == "oracle":
                where_parts.append(f"{alias}.{cname.upper()} = {_sql_literal(value)}")
            else:
                where_parts.append(f'{alias}."{cname}" = {_sql_literal(value)}')

        # GROUP BY dimension columns — plain columns on the metric's own
        # source table (a pre-joined view), same constraint as metric.source.
        # _quote_ident's identifier regex rejects anything that isn't a bare
        # column/qualified-column name, so this can't become injection even
        # if a caller ever passed something other than the resolver's
        # hardcoded dimension-code → column mapping.
        group_cols_sql: list[str] = []
        for col in req.group_by:
            cname = col.split(".")[-1].replace('"', "")
            # _quote_ident already returns the fully quoted/uppercased form
            # for the target dialect ("segment" / SEGMENT) — do not re-wrap it.
            group_cols_sql.append(f"{alias}.{_quote_ident(cname, dialect=dialect)}")

        # Time grain (series): bucket expression comes first in SELECT/GROUP BY
        # and dictates ORDER BY period ASC — time order, never rank order.
        period_expr: str | None = None
        if req.time_grain is not None:
            grain = str(req.time_grain).lower()
            if grain not in TIME_GRAINS:
                raise ValidationError(f"Geçersiz time_grain: {req.time_grain}")
            if not metric.time or not metric.time.time_field:
                raise ValidationError("time_grain için metric.time.time_field zorunludur.")
            tcol = metric.time.time_field.split(".")[-1]
            if dialect == "oracle":
                period_expr = f"TRUNC({alias}.{tcol.upper()}, '{_ORACLE_TRUNC_FMT[grain]}')"
                period_select = f"{period_expr} AS {PERIOD_ALIAS.upper()}"
            else:
                period_expr = f"date_trunc('{grain}', {alias}.\"{tcol}\")"
                period_select = f'{period_expr} AS "{PERIOD_ALIAS}"'
            select_cols = [period_select] + list(group_cols_sql) + [select_expr]
            group_sql_cols = [period_expr] + list(group_cols_sql)
        else:
            select_cols = list(group_cols_sql) + [select_expr]
            group_sql_cols = list(group_cols_sql)
        sql_parts = [f"SELECT\n    " + ",\n    ".join(select_cols), from_sql]
        if join_sql_parts:
            sql_parts.extend(join_sql_parts)
        if where_parts:
            sql_parts.append("WHERE " + "\n  AND ".join(where_parts))
        if group_sql_cols:
            sql_parts.append("GROUP BY " + ", ".join(group_sql_cols))
        if period_expr is not None:
            order_parts = [f"{period_expr} ASC"] + [f"{g} ASC" for g in group_cols_sql]
            sql_parts.append("ORDER BY " + ", ".join(order_parts))
        # Rank/breakdown ordering: by the aggregate value, not a dimension —
        # "en yüksek"/"ilk N" questions mean "highest metric value first".
        # A tie-break on the first group-by column is required for genuine
        # determinism: Postgres makes no ordering guarantee among rows with
        # an equal aggregate value without a secondary sort key, and "same
        # logical plan in, byte-identical rows out" is the entire point of
        # compiling this instead of asking the LLM.
        elif group_cols_sql or req.limit is not None:
            order_dir = "DESC" if req.order_desc else "ASC"
            order_parts = [f"{agg}({expr}) {order_dir}"]
            if group_cols_sql:
                order_parts.append(f"{group_cols_sql[0]} ASC")
            sql_parts.append("ORDER BY " + ", ".join(order_parts))
        if req.limit is not None:
            limit_n = int(req.limit)
            if dialect == "oracle":
                sql_parts.append(f"FETCH FIRST {limit_n} ROWS ONLY")
            else:
                sql_parts.append(f"LIMIT {limit_n}")

        sql = "\n".join(sql_parts)
        if dialect != "oracle":
            sql += ";"

        logical = metric.to_logical_plan()
        if req.period:
            logical["period"] = dict(req.period)
        if req.dimension_filters:
            logical["dimensionFilters"] = dict(req.dimension_filters)
        if req.group_by:
            logical["groupBy"] = list(req.group_by)
        if req.limit is not None:
            logical["limit"] = req.limit
            logical["orderDesc"] = req.order_desc
        if req.time_grain is not None:
            logical["timeGrain"] = str(req.time_grain).lower()
            logical["periodAlias"] = PERIOD_ALIAS
        logical["dialect"] = dialect

        fingerprint = self.ast_fingerprint(sql, dialect=dialect)
        return CompileResult(sql=sql, logical_plan=logical, ast_fingerprint=fingerprint)

    def _qualify(self, expr: str, aliases: dict[str, str], *, dialect: str = "postgres") -> str:
        bits = expr.replace('"', "").split(".")
        if len(bits) >= 2:
            table = ".".join(bits[:-1])
            col = bits[-1]
            a = aliases.get(table) or aliases.get(bits[-2]) or _alias_for(table, dialect=dialect)
            if dialect == "oracle":
                return f"{a}.{col.upper()}"
            return f'{a}."{col}"'
        return _quote_ident(expr, dialect=dialect)

    def _compile_filter(
        self, fr: FilterRule, aliases: dict[str, str], *, dialect: str = "postgres"
    ) -> str:
        field = self._qualify(fr.expression.field, aliases, dialect=dialect)
        op = fr.expression.operator.upper()
        vals = fr.expression.values
        if op == "NOT_IN":
            lit = ", ".join(_sql_literal(v) for v in vals)
            return f"{field} NOT IN ({lit})"
        if op == "IN":
            lit = ", ".join(_sql_literal(v) for v in vals)
            return f"{field} IN ({lit})"
        if op in ("=", "!=", "<>", ">", "<", ">=", "<="):
            return f"{field} {op} {_sql_literal(vals[0] if vals else None)}"
        if op == "IS_NULL":
            return f"{field} IS NULL"
        if op == "IS_NOT_NULL":
            return f"{field} IS NOT NULL"
        raise ValidationError(f"Desteklenmeyen filter operator: {op}")

    @staticmethod
    def ast_fingerprint(sql: str, *, dialect: str = "postgres") -> str:
        """Normalize via sqlglot when available; else whitespace-normalized hash."""
        normalized = sql
        read_dialect = "oracle" if dialect == "oracle" else "postgres"
        try:
            import sqlglot

            parsed = sqlglot.parse_one(sql, read=read_dialect)
            normalized = parsed.sql(dialect=read_dialect)
        except Exception:
            normalized = re.sub(r"\s+", " ", sql).strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("'", "''")
    return f"'{s}'"


def compile_unpaid_invoice_amount(
    *,
    metric: Metric,
    exclude_cancelled: FilterRule,
    period: dict[str, str] | None = None,
    dialect: str = "postgres",
) -> CompileResult:
    """Vertical slice helper."""
    return MetricCompiler().compile(
        CompileRequest(
            metric=metric,
            filters=[exclude_cancelled],
            period=period,
            dialect=dialect,
        )
    )
