"""Table/column semantic role classifier + business date selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from nanobase_api.scenario_engine.domain.roles import (
    BLOCKED_COLUMN_ROLES,
    ColumnRole,
    NON_SCENARIO_TABLE_ROLES,
    TableRole,
)
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import (
    ColumnSnap,
    SchemaSnapshot,
    TableSnap,
)

_TABLE_OVERRIDES: dict[str, TableRole] = {
    "analytics.invoices": TableRole.TRANSACTION,
    "analytics.sales_orders": TableRole.TRANSACTION,
    "analytics.customers": TableRole.ENTITY,
    "analytics.customer_addresses": TableRole.DIMENSION,
    "analytics.payments": TableRole.TRANSACTION,
    "analytics.products": TableRole.ENTITY,
    "analytics.companies": TableRole.ENTITY,
    "analytics.branches": TableRole.DIMENSION,
    "flyway_schema_history": TableRole.TECHNICAL,
    "public.flyway_schema_history": TableRole.TECHNICAL,
}

_COLUMN_OVERRIDES: dict[str, ColumnRole] = {
    "invoice_id": ColumnRole.IDENTIFIER,
    "order_id": ColumnRole.FOREIGN_KEY,
    "customer_id": ColumnRole.FOREIGN_KEY,
    "invoice_date": ColumnRole.BUSINESS_DATE,
    "due_date": ColumnRole.DUE_DATE,
    "order_date": ColumnRole.BUSINESS_DATE,
    "payment_date": ColumnRole.BUSINESS_DATE,
    "created_at": ColumnRole.CREATED_AT,
    "updated_at": ColumnRole.UPDATED_AT,
    "gross_amount": ColumnRole.AMOUNT,
    "remaining_amount": ColumnRole.AMOUNT,
    "amount": ColumnRole.AMOUNT,
    "unit_price": ColumnRole.AMOUNT,
    "currency": ColumnRole.CURRENCY,
    "currency_code": ColumnRole.CURRENCY,
    "status": ColumnRole.STATUS,
    "customer_name": ColumnRole.NAME,
    "city": ColumnRole.CATEGORY,
    "quantity": ColumnRole.QUANTITY,
    "password": ColumnRole.SENSITIVE,
    "password_hash": ColumnRole.SENSITIVE,
    "iban": ColumnRole.SENSITIVE,
    "ssn": ColumnRole.SENSITIVE,
}

_TECHNICAL_TABLE_RE = re.compile(
    r"(flyway|alembic|schema_history|pg_|information_schema|audit_log)", re.I
)


@dataclass
class ClassifiedColumn:
    name: str
    fqn: str
    role: ColumnRole
    data_type: str


@dataclass
class ClassifiedTable:
    fqn: str
    role: TableRole
    columns: list[ClassifiedColumn] = field(default_factory=list)
    dates: dict[str, str | None] = field(default_factory=dict)

    @property
    def business_date(self) -> str | None:
        return self.dates.get("businessDate")

    @property
    def scenario_eligible(self) -> bool:
        return self.role not in NON_SCENARIO_TABLE_ROLES


@dataclass
class ClassificationResult:
    tables: list[ClassifiedTable]
    schema_version: str

    def table(self, fqn: str) -> ClassifiedTable | None:
        for t in self.tables:
            if t.fqn == fqn or t.fqn.endswith("." + fqn):
                return t
        return None

    def entity_map(self) -> dict[str, ClassifiedTable]:
        """Logical entity name → classified table for vertical slice."""
        out: dict[str, ClassifiedTable] = {}
        for t in self.tables:
            if t.fqn.endswith(".invoices"):
                out["invoice"] = t
            elif t.fqn.endswith(".customers"):
                out["customer"] = t
            elif t.fqn.endswith(".sales_orders"):
                out["order"] = t
            elif t.fqn.endswith(".customer_addresses"):
                out["customer_address"] = t
            elif t.fqn.endswith(".payments"):
                out["payment"] = t
            elif t.fqn.endswith(".products"):
                out["product"] = t
        return out


def _classify_table_role(table: TableSnap) -> TableRole:
    if table.fqn in _TABLE_OVERRIDES:
        return _TABLE_OVERRIDES[table.fqn]
    if table.name in _TABLE_OVERRIDES:
        return _TABLE_OVERRIDES[table.name]
    if _TECHNICAL_TABLE_RE.search(table.fqn):
        return TableRole.TECHNICAL
    name = table.name.lower()
    if name.endswith("_log") or name.startswith("audit"):
        return TableRole.AUDIT
    if "address" in name or "city" in name or "branch" in name:
        return TableRole.DIMENSION
    if name.endswith("s") and any(c.name.endswith("_id") and c.is_pk for c in table.columns):
        # crude: plural transactional names
        if any("amount" in c.name or "date" in c.name for c in table.columns):
            return TableRole.TRANSACTION
        return TableRole.ENTITY
    return TableRole.ENTITY


def _classify_column_role(col: ColumnSnap) -> ColumnRole:
    if col.name in _COLUMN_OVERRIDES:
        return _COLUMN_OVERRIDES[col.name]
    n = col.name.lower()
    if col.is_fk or n.endswith("_id") and not col.is_pk:
        return ColumnRole.FOREIGN_KEY
    if col.is_pk or n.endswith("_id"):
        return ColumnRole.IDENTIFIER
    if n.endswith("_date") or n == "date":
        if "due" in n:
            return ColumnRole.DUE_DATE
        if "post" in n:
            return ColumnRole.POSTING_DATE
        return ColumnRole.DATE
    if "amount" in n or "price" in n or "total" in n or "balance" in n:
        return ColumnRole.AMOUNT
    if "qty" in n or "quantity" in n:
        return ColumnRole.QUANTITY
    if "currency" in n:
        return ColumnRole.CURRENCY
    if n in ("status", "state"):
        return ColumnRole.STATUS
    if any(x in n for x in ("password", "secret", "token", "iban", "ssn", "salary")):
        return ColumnRole.SENSITIVE
    if col.data_type.lower() in ("bytea", "blob"):
        return ColumnRole.TECHNICAL
    return ColumnRole.NAME if "name" in n else ColumnRole.DESCRIPTION


def _pick_business_dates(table: ClassifiedTable) -> dict[str, str | None]:
    dates: dict[str, str | None] = {
        "businessDate": None,
        "postingDate": None,
        "createdAt": None,
        "dueDate": None,
    }
    for c in table.columns:
        fqn = c.fqn
        if c.role == ColumnRole.BUSINESS_DATE and dates["businessDate"] is None:
            dates["businessDate"] = fqn
        elif c.role == ColumnRole.POSTING_DATE:
            dates["postingDate"] = fqn
        elif c.role == ColumnRole.CREATED_AT:
            dates["createdAt"] = fqn
        elif c.role == ColumnRole.DUE_DATE:
            dates["dueDate"] = fqn
        elif c.role == ColumnRole.DATE and dates["businessDate"] is None:
            # Prefer *invoice_date* / *order_date* style over generic
            if c.name.endswith("_date") and c.name not in ("updated_at",):
                dates["businessDate"] = fqn
    # Prefer explicit invoice_date naming
    for c in table.columns:
        if c.name in ("invoice_date", "order_date", "payment_date") and dates["businessDate"] is None:
            dates["businessDate"] = c.fqn
    return dates


def classify_schema(snapshot: SchemaSnapshot) -> ClassificationResult:
    tables: list[ClassifiedTable] = []
    for t in snapshot.tables:
        role = _classify_table_role(t)
        cols = [
            ClassifiedColumn(
                name=c.name,
                fqn=f"{t.fqn}.{c.name}",
                role=_classify_column_role(c),
                data_type=c.data_type,
            )
            for c in t.columns
        ]
        ct = ClassifiedTable(fqn=t.fqn, role=role, columns=cols)
        ct.dates = _pick_business_dates(ct)
        tables.append(ct)
    return ClassificationResult(tables=tables, schema_version=snapshot.fingerprint())


def projectable_columns(table: ClassifiedTable) -> list[ClassifiedColumn]:
    return [c for c in table.columns if c.role not in BLOCKED_COLUMN_ROLES]


def measure_columns(table: ClassifiedTable) -> list[ClassifiedColumn]:
    return [c for c in table.columns if c.role == ColumnRole.AMOUNT]
