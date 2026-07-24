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
    "musteri_id": ColumnRole.FOREIGN_KEY,
    "fatura_id": ColumnRole.IDENTIFIER,
    "siparis_id": ColumnRole.FOREIGN_KEY,
    "invoice_date": ColumnRole.BUSINESS_DATE,
    "due_date": ColumnRole.DUE_DATE,
    "order_date": ColumnRole.BUSINESS_DATE,
    "payment_date": ColumnRole.BUSINESS_DATE,
    "fatura_tarihi": ColumnRole.BUSINESS_DATE,
    "siparis_tarihi": ColumnRole.BUSINESS_DATE,
    "odeme_tarihi": ColumnRole.BUSINESS_DATE,
    "vade_tarihi": ColumnRole.DUE_DATE,
    "tarih": ColumnRole.BUSINESS_DATE,
    "created_at": ColumnRole.CREATED_AT,
    "updated_at": ColumnRole.UPDATED_AT,
    "olusturma_tarihi": ColumnRole.CREATED_AT,
    "guncelleme_tarihi": ColumnRole.UPDATED_AT,
    "gross_amount": ColumnRole.AMOUNT,
    "remaining_amount": ColumnRole.AMOUNT,
    "amount": ColumnRole.AMOUNT,
    "unit_price": ColumnRole.AMOUNT,
    "tutar": ColumnRole.AMOUNT,
    "brut_tutar": ColumnRole.AMOUNT,
    "net_tutar": ColumnRole.AMOUNT,
    "kalan_tutar": ColumnRole.AMOUNT,
    "toplam_tutar": ColumnRole.AMOUNT,
    "ara_toplam": ColumnRole.AMOUNT,
    "genel_toplam": ColumnRole.AMOUNT,
    "satis_tutari": ColumnRole.AMOUNT,
    "alis_fiyat": ColumnRole.AMOUNT,
    "birim_fiyat": ColumnRole.AMOUNT,
    "bakiye": ColumnRole.AMOUNT,
    "currency": ColumnRole.CURRENCY,
    "currency_code": ColumnRole.CURRENCY,
    "para_birimi": ColumnRole.CURRENCY,
    "status": ColumnRole.STATUS,
    "durum": ColumnRole.STATUS,
    "customer_name": ColumnRole.NAME,
    "musteri_adi": ColumnRole.NAME,
    "ad": ColumnRole.NAME,
    "adi": ColumnRole.NAME,
    "city": ColumnRole.CATEGORY,
    "il": ColumnRole.CATEGORY,
    "sehir": ColumnRole.CATEGORY,
    "quantity": ColumnRole.QUANTITY,
    "miktar": ColumnRole.QUANTITY,
    "password": ColumnRole.SENSITIVE,
    "password_hash": ColumnRole.SENSITIVE,
    "iban": ColumnRole.SENSITIVE,
    "ssn": ColumnRole.SENSITIVE,
}

# table name (without schema) → logical entity code used in plans / grammar
_TABLE_ENTITY: dict[str, str] = {
    "invoices": "invoice",
    "faturalar": "invoice",
    "satis_faturalari": "invoice",
    "customers": "customer",
    "musteriler": "customer",
    "cariler": "customer",
    "sales_orders": "order",
    "siparisler": "order",
    "satis_siparisleri": "order",
    "products": "product",
    "urunler": "product",
    "payments": "payment",
    "odemeler": "payment",
    "tahsilatlar": "payment",
    "customer_addresses": "customer_address",
    "stoklar": "stock",
    "stok_bakiyeleri": "stock",
    "personel": "staff",
    "personeller": "staff",
    "subeler": "branch",
    "branches": "branch",
    "fatura_kalemleri": "invoice_line",
    "urun_kategorileri": "product_category",
    "markalar": "brand",
    "fiyat_listesi_kalemleri": "price_list_item",
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
        """Logical entity name → classified table (EN + TR ERP names)."""
        out: dict[str, ClassifiedTable] = {}
        for t in self.tables:
            code = entity_code_for_table(t.fqn)
            # Prefer first match; invoice/customer aliases win over generic table name
            if code not in out:
                out[code] = t
            # Also keep short aliases for vertical-slice planners
            name = t.fqn.split(".")[-1].lower()
            if name in ("invoices", "faturalar", "satis_faturalari"):
                out["invoice"] = t
            elif name in ("customers", "musteriler", "cariler"):
                out["customer"] = t
            elif name in ("sales_orders", "siparisler", "satis_siparisleri"):
                out["order"] = t
            elif name in ("customer_addresses",):
                out["customer_address"] = t
            elif name in ("payments", "odemeler", "tahsilatlar"):
                out["payment"] = t
            elif name in ("products", "urunler"):
                out["product"] = t
        return out

    def eligible_tables(self) -> list[ClassifiedTable]:
        return [t for t in self.tables if t.scenario_eligible]


def entity_code_for_table(fqn: str) -> str:
    name = fqn.split(".")[-1].lower()
    if name in _TABLE_ENTITY:
        return _TABLE_ENTITY[name]
    return name


def _classify_table_role(table: TableSnap) -> TableRole:
    if table.fqn in _TABLE_OVERRIDES:
        return _TABLE_OVERRIDES[table.fqn]
    if table.name in _TABLE_OVERRIDES:
        return _TABLE_OVERRIDES[table.name]
    if _TECHNICAL_TABLE_RE.search(table.fqn):
        return TableRole.TECHNICAL
    name = table.name.lower()
    if name.endswith("_log") or name.startswith("audit") or name.startswith("tmp_"):
        return TableRole.AUDIT
    if any(x in name for x in ("address", "adres", "city", "branch", "sube", "kategori", "marka")):
        return TableRole.DIMENSION
    # Transactional: has date + amount-like cols, or known TR txn names
    has_amount = any(
        any(k in c.name.lower() for k in ("amount", "tutar", "fiyat", "bakiye", "price", "total"))
        for c in table.columns
    )
    has_date = any(
        any(k in c.name.lower() for k in ("date", "tarih", "created", "updated"))
        for c in table.columns
    )
    if name.endswith(("lar", "ler", "s")) and (has_amount or has_date):
        if has_amount and has_date:
            return TableRole.TRANSACTION
        return TableRole.ENTITY
    if name.endswith("s") and any(c.name.endswith("_id") and c.is_pk for c in table.columns):
        if has_amount or has_date:
            return TableRole.TRANSACTION
        return TableRole.ENTITY
    return TableRole.ENTITY


def _classify_column_role(col: ColumnSnap) -> ColumnRole:
    if col.name in _COLUMN_OVERRIDES:
        return _COLUMN_OVERRIDES[col.name]
    n = col.name.lower()
    if col.is_fk or (n.endswith("_id") and not col.is_pk):
        return ColumnRole.FOREIGN_KEY
    if col.is_pk or n.endswith("_id"):
        return ColumnRole.IDENTIFIER
    if n.endswith(("_date", "_tarihi")) or n in ("date", "tarih"):
        if "due" in n or "vade" in n:
            return ColumnRole.DUE_DATE
        if "post" in n:
            return ColumnRole.POSTING_DATE
        if n in ("created_at", "olusturma_tarihi") or n.startswith("created"):
            return ColumnRole.CREATED_AT
        if n in ("updated_at", "guncelleme_tarihi") or n.startswith("updated"):
            return ColumnRole.UPDATED_AT
        return ColumnRole.DATE
    if any(
        k in n
        for k in (
            "amount",
            "price",
            "total",
            "toplam",
            "balance",
            "tutar",
            "fiyat",
            "bakiye",
            "ciro",
        )
    ):
        return ColumnRole.AMOUNT
    if "qty" in n or "quantity" in n or "miktar" in n:
        return ColumnRole.QUANTITY
    if "currency" in n or "para_birimi" in n:
        return ColumnRole.CURRENCY
    if n in ("status", "state", "durum"):
        return ColumnRole.STATUS
    if any(x in n for x in ("password", "secret", "token", "iban", "ssn", "salary", "maas")):
        return ColumnRole.SENSITIVE
    if col.data_type.lower() in ("bytea", "blob"):
        return ColumnRole.TECHNICAL
    dt = col.data_type.lower()
    if dt in ("date", "timestamp", "timestamp without time zone", "timestamp with time zone"):
        return ColumnRole.DATE
    if dt in ("numeric", "integer", "bigint", "double precision", "real", "money"):
        # unnamed numeric — keep DESCRIPTION unless clearly measure-ish
        pass
    return ColumnRole.NAME if ("name" in n or n in ("ad", "adi")) else ColumnRole.DESCRIPTION


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
            if c.name.endswith(("_date", "_tarihi")) or c.name == "tarih":
                dates["businessDate"] = fqn
    preferred = (
        "invoice_date",
        "order_date",
        "payment_date",
        "fatura_tarihi",
        "siparis_tarihi",
        "odeme_tarihi",
        "tarih",
    )
    for c in table.columns:
        if c.name in preferred and dates["businessDate"] is None:
            dates["businessDate"] = c.fqn
    if dates["businessDate"] is None and dates["createdAt"]:
        dates["businessDate"] = dates["createdAt"]
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
