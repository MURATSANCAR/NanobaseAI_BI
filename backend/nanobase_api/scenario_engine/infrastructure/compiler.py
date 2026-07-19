"""Logical plan → dialect SQL template with named bind parameters."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol

from nanobase_api.scenario_engine.domain.errors import ValidationError
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _qi(name: str) -> str:
    parts = name.replace('"', "").split(".")
    for p in parts:
        if not _IDENT.match(p):
            raise ValidationError(f"Invalid identifier: {name}")
    return ".".join(f'"{p}"' for p in parts)


def _col(table_alias: str, column_fqn_or_name: str) -> str:
    col = column_fqn_or_name.split(".")[-1]
    if not _IDENT.match(col):
        raise ValidationError(f"Invalid column: {column_fqn_or_name}")
    return f'{table_alias}."{col}"'


@dataclass
class CompileResult:
    sql_template: str
    dialect: str
    ast_fingerprint: str
    bind_params: list[str] = field(default_factory=list)
    logical_plan: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sqlTemplate": self.sql_template,
            "dialect": self.dialect,
            "astFingerprint": self.ast_fingerprint,
            "bindParams": list(self.bind_params),
            "logicalPlan": dict(self.logical_plan),
        }


class DialectCompiler(Protocol):
    dialect: str

    def compile(self, plan: LogicalPlan) -> CompileResult: ...


class PostgresLogicalPlanCompiler:
    """Compile logical scenarios to PostgreSQL SQL templates."""

    dialect = "postgres"

    def compile(self, plan: LogicalPlan) -> CompileResult:
        table = plan.physical_table or f"analytics.{plan.entity}s"
        alias = "i" if "invoice" in table else "t"
        binds: list[str] = []
        family = plan.family

        if family in ("LIST_ENTITY", "STATUS_FILTER", "AGING"):
            sql, binds = self._compile_list(plan, table, alias)
        elif family == "COUNT_ENTITY":
            sql, binds = self._compile_count(plan, table, alias)
        elif family == "SUM_MEASURE":
            sql, binds = self._compile_sum(plan, table, alias)
        elif family == "TOP_N":
            sql, binds = self._compile_top_n(plan, table, alias)
        elif family == "GROUP_MEASURE":
            sql, binds = self._compile_group(plan, table, alias)
        elif family == "TIME_TREND":
            sql, binds = self._compile_trend(plan, table, alias)
        elif family == "COMPARE_PERIOD":
            sql, binds = self._compile_compare(plan, table, alias)
        else:
            raise ValidationError(f"Unsupported family for postgres compile: {family}")

        # Fail-closed: sqlglot parse when available
        self._assert_parseable(sql)
        fp = "sha256:" + hashlib.sha256(sql.encode("utf-8")).hexdigest()
        return CompileResult(
            sql_template=sql,
            dialect=self.dialect,
            ast_fingerprint=fp,
            bind_params=binds,
            logical_plan=plan.to_dict(),
        )

    def _where_base(self, plan: LogicalPlan, alias: str) -> tuple[list[str], list[str]]:
        parts: list[str] = []
        binds: list[str] = []
        if plan.period and plan.date_column:
            dc = _col(alias, plan.date_column)
            parts.append(f"{dc} >= :period_start")
            parts.append(f"{dc} < :period_end")
            binds.extend(["period_start", "period_end"])
        if plan.mandatory_filters and "exclude_cancelled_invoices" in plan.mandatory_filters:
            if plan.status_filter != "cancelled":
                parts.append(f'{alias}."status" <> :cancelled_status')
                binds.append("cancelled_status")
        if plan.status_filter == "cancelled":
            parts.append(f'{alias}."status" = :status_value')
            binds.append("status_value")
        if plan.status_filter == "unpaid" or (plan.extra or {}).get("unpaid_predicate"):
            parts.append(f'{alias}."remaining_amount" > 0')
        if plan.family == "AGING" and plan.aging_bucket == "OVERDUE":
            # due_date before today start
            dc = _col(alias, plan.date_column or "due_date")
            parts.append(f"{dc} < :period_start")
            if "period_start" not in binds:
                binds.append("period_start")
        return parts, binds

    def _compile_list(self, plan: LogicalPlan, table: str, alias: str) -> tuple[str, list[str]]:
        cols = plan.projection or ["invoice_id", "invoice_date", "gross_amount", "status", "currency"]
        # Strip joined-only columns from base select unless join present
        base_cols = [c for c in cols if c != "customer_name"]
        select_cols = ", ".join(_col(alias, c) for c in base_cols)
        joins = self._join_sql(plan, alias)
        if "customer_name" in cols and joins:
            select_cols += ', c."customer_name"'
        where_parts, binds = self._where_base(plan, alias)
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        sort_field = plan.sort.field if plan.sort else base_cols[0]
        if sort_field == "metric":
            sort_field = base_cols[0]
        direction = (plan.sort.direction if plan.sort else "DESC").upper()
        order_sql = f' ORDER BY {_col(alias, sort_field)} {direction}'
        binds.append("fetch_limit")
        sql = (
            f"SELECT {select_cols}\n"
            f"FROM {_qi(table)} {alias}\n"
            f"{joins}"
            f"{where_sql}\n"
            f"{order_sql}\n"
            f"LIMIT :fetch_limit"
        )
        return sql.strip(), binds

    def _compile_count(self, plan: LogicalPlan, table: str, alias: str) -> tuple[str, list[str]]:
        where_parts, binds = self._where_base(plan, alias)
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        sql = f'SELECT COUNT(*) AS "row_count"\nFROM {_qi(table)} {alias}\n{where_sql}'
        return sql.strip(), binds

    def _compile_sum(self, plan: LogicalPlan, table: str, alias: str) -> tuple[str, list[str]]:
        metric = plan.metric_column or "gross_amount"
        where_parts, binds = self._where_base(plan, alias)
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        sql = (
            f'SELECT COALESCE(SUM({_col(alias, metric)}), 0) AS "total_amount"\n'
            f"FROM {_qi(table)} {alias}\n"
            f"{where_sql}"
        )
        return sql.strip(), binds

    def _compile_top_n(self, plan: LogicalPlan, table: str, alias: str) -> tuple[str, list[str]]:
        cols = plan.projection or ["invoice_id", "invoice_date", "gross_amount", "status", "currency"]
        select_cols = ", ".join(_col(alias, c) for c in cols if c != "customer_name")
        where_parts, binds = self._where_base(plan, alias)
        # TOP_N often has no period; still ok
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        metric = (plan.metric_column or "gross_amount").split(".")[-1]
        binds.append("fetch_limit")
        sql = (
            f"SELECT {select_cols}\n"
            f"FROM {_qi(table)} {alias}\n"
            f"{where_sql}\n"
            f'ORDER BY {_col(alias, metric)} DESC\n'
            f"LIMIT :fetch_limit"
        )
        return sql.strip(), binds

    def _compile_group(self, plan: LogicalPlan, table: str, alias: str) -> tuple[str, list[str]]:
        metric = plan.metric_column or "gross_amount"
        joins = self._join_sql(plan, alias)
        where_parts, binds = self._where_base(plan, alias)
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        dim_col = (plan.extra or {}).get("dimension_column", "analytics.customer_addresses.city")
        dim_alias = "a"
        sql = (
            f'SELECT {dim_alias}."city" AS "customer_city", '
            f'COALESCE(SUM({_col(alias, metric)}), 0) AS "total_amount"\n'
            f"FROM {_qi(table)} {alias}\n"
            f"{joins}"
            f"{where_sql}\n"
            f'GROUP BY {dim_alias}."city"\n'
            f'ORDER BY "total_amount" DESC\n'
            f"LIMIT :fetch_limit"
        )
        binds.append("fetch_limit")
        # ensure address alias join exists
        if "customer_addresses" not in joins:
            raise ValidationError("GROUP by city requires approved join to customer_addresses")
        _ = dim_col
        return sql.strip(), binds

    def _compile_trend(self, plan: LogicalPlan, table: str, alias: str) -> tuple[str, list[str]]:
        metric = plan.metric_column or "gross_amount"
        where_parts, binds = self._where_base(plan, alias)
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        dc = _col(alias, plan.date_column or "invoice_date")
        sql = (
            f"SELECT date_trunc('month', {dc}) AS \"month\", "
            f'COALESCE(SUM({_col(alias, metric)}), 0) AS "total_amount"\n'
            f"FROM {_qi(table)} {alias}\n"
            f"{where_sql}\n"
            f'GROUP BY date_trunc(\'month\', {dc})\n'
            f'ORDER BY "month" ASC\n'
            f"LIMIT :fetch_limit"
        )
        binds.append("fetch_limit")
        return sql.strip(), binds

    def _compile_compare(self, plan: LogicalPlan, table: str, alias: str) -> tuple[str, list[str]]:
        metric = plan.metric_column or "gross_amount"
        # Two bind pairs: current and previous — resolved at runtime into union
        sql = (
            f'SELECT \'current\' AS "period_label", '
            f'COALESCE(SUM({_col(alias, metric)}), 0) AS "total_amount"\n'
            f"FROM {_qi(table)} {alias}\n"
            f'WHERE {_col(alias, plan.date_column or "invoice_date")} >= :period_start\n'
            f'  AND {_col(alias, plan.date_column or "invoice_date")} < :period_end\n'
            f'  AND {alias}."status" <> :cancelled_status\n'
            f"UNION ALL\n"
            f'SELECT \'previous\' AS "period_label", '
            f'COALESCE(SUM({_col(alias, metric)}), 0) AS "total_amount"\n'
            f"FROM {_qi(table)} {alias}\n"
            f'WHERE {_col(alias, plan.date_column or "invoice_date")} >= :compare_start\n'
            f'  AND {_col(alias, plan.date_column or "invoice_date")} < :compare_end\n'
            f'  AND {alias}."status" <> :cancelled_status'
        )
        binds = ["period_start", "period_end", "compare_start", "compare_end", "cancelled_status"]
        return sql.strip(), binds

    def _join_sql(self, plan: LogicalPlan, alias: str) -> str:
        edges = (plan.extra or {}).get("join_edges") or []
        if not edges:
            return ""
        parts: list[str] = []
        alias_map = {plan.physical_table or "": alias, "": alias}
        # Deterministic aliases
        used = {alias}
        for e in edges:
            to_table = e["to"]
            from_table = e["from"]
            from_alias = alias_map.get(from_table)
            if from_alias is None:
                # reverse edge mid-path
                from_alias = alias
            to_alias = to_table.split(".")[-1][:1]
            if to_alias in used:
                to_alias = to_table.split(".")[-1][:3]
            # Prefer known aliases
            if "customer_addresses" in to_table:
                to_alias = "a"
            elif "customers" in to_table:
                to_alias = "c"
            elif "sales_orders" in to_table:
                to_alias = "o"
            used.add(to_alias)
            alias_map[to_table] = to_alias
            # If edge direction is reverse of FK (customers <- orders), still emit JOIN
            parts.append(
                f'JOIN {_qi(to_table)} {to_alias} ON {from_alias}."{e["from_col"]}" = {to_alias}."{e["to_col"]}"'
            )
            # Primary address filter
            if "customer_addresses" in to_table:
                parts[-1] += f' AND {to_alias}."is_primary" = TRUE'
        return ("\n".join(parts) + "\n") if parts else ""

    def _assert_parseable(self, sql: str) -> None:
        # Replace binds with literals for parse check
        probe = sql
        for name in (
            "period_start",
            "period_end",
            "fetch_limit",
            "cancelled_status",
            "status_value",
            "compare_start",
            "compare_end",
        ):
            probe = probe.replace(f":{name}", "NULL" if "status" in name or "limit" not in name else "1")
        probe = probe.replace(":fetch_limit", "1")
        probe = probe.replace(":cancelled_status", "'x'")
        probe = probe.replace(":status_value", "'x'")
        try:
            import sqlglot
            from sqlglot import exp

            parsed = sqlglot.parse(probe, read="postgres")
            if not parsed or parsed[0] is None:
                raise ValidationError("sqlglot failed to parse compiled SQL")
            if not isinstance(parsed[0], (exp.Select, exp.Union)):
                # WITH ... SELECT also ok
                if not any(isinstance(n, exp.Select) for n in parsed[0].walk()):
                    raise ValidationError("Compiled SQL must be SELECT")
        except ImportError:
            # sqlglot optional in unit env — structural checks only
            if not re.search(r"\bSELECT\b", sql, re.I):
                raise ValidationError("Compiled SQL must contain SELECT")
            if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b", sql, re.I):
                raise ValidationError("DML/DDL forbidden in compiled SQL")
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"SQL parse failed (fail-closed): {e}") from e


class OracleLogicalPlanCompiler:
    """Stub — filled in Faz 4."""

    dialect = "oracle"

    def compile(self, plan: LogicalPlan) -> CompileResult:
        raise ValidationError("Oracle dialect compiler not enabled in invoice vertical slice")


class HanaLogicalPlanCompiler:
    dialect = "hana"

    def compile(self, plan: LogicalPlan) -> CompileResult:
        raise ValidationError("HANA dialect compiler not enabled in invoice vertical slice")


class ODataLogicalPlanCompiler:
    dialect = "odata"

    def compile(self, plan: LogicalPlan) -> CompileResult:
        raise ValidationError("OData dialect compiler not enabled in invoice vertical slice")


def get_compiler(dialect: str = "postgres") -> DialectCompiler:
    d = (dialect or "postgres").lower()
    if d in ("postgres", "postgresql"):
        return PostgresLogicalPlanCompiler()
    if d == "oracle":
        return OracleLogicalPlanCompiler()
    if d in ("hana", "sap_hana"):
        return HanaLogicalPlanCompiler()
    if d == "odata":
        return ODataLogicalPlanCompiler()
    raise ValidationError(f"Unsupported dialect: {dialect}")


def render_sql(template: str, params: dict[str, object]) -> str:
    """Dev/test helper — production uses driver binds via Query Gateway."""
    sql = template
    for k, v in params.items():
        if isinstance(v, str):
            lit = "'" + v.replace("'", "''") + "'"
        elif v is None:
            lit = "NULL"
        else:
            lit = str(v)
        sql = sql.replace(f":{k}", lit)
    return sql
