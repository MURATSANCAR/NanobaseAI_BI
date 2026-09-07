from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _reporting_datasource_id() -> str:
    return _env("REPORTING_DATASOURCE_ID", "bi_reporting") or "bi_reporting"


# bi_reporting carries two generations of the same sales domain: the original
# Phase-1 seed (orders/order_items, analytics + public alias) and the later
# "rich" schema (sales_orders/sales_order_items/invoices/...). Both are live
# tables with real (different) rows, so retrieval — once it actually works —
# finds and answers from either one. docs/architecture/locked-architecture.md
# already calls the original pair "legacy orders" when describing the rich
# schema; this excludes them from the retrieval index so generated SQL
# consistently targets the canonical sales_orders/sales_order_items model
# instead of silently answering from whichever layer scored higher.
# customers/products are shared master data used by BOTH generations — kept.
LEGACY_TABLES: dict[str, frozenset[tuple[str, str]]] = {
    "bi_reporting": frozenset(
        {
            ("analytics", "orders"),
            ("analytics", "order_items"),
            ("analytics", "v_order_revenue"),
            ("public", "orders"),
            ("public", "order_items"),
            ("public", "v_order_revenue"),
        }
    ),
}


@dataclass
class IndexerConfig:
    datasource_id: str = field(default_factory=_reporting_datasource_id)
    collection: str | None = None
    schemas: tuple[str, ...] = ("analytics", "public")
    secrets_root: Path = field(
        default_factory=lambda: Path(_env("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
    )
    qdrant_url: str = field(default_factory=lambda: _env("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/"))
    embed_url: str = field(
        default_factory=lambda: _env("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
    )
    vector_size: int = field(default_factory=lambda: int(_env("BI_EMBED_DIM", "1024") or "1024"))
    embed_batch: int = 8
    # No cap. A scan reports on the database it was pointed at, all of it: a count limit makes the
    # catalogue disagree with the database, and planning and reporting are then done against a number
    # nobody can reconcile. Scope is expressed as scope — `table_patterns` — never as "the first N".
    # BI_SCHEMA_MAX_TABLES stays available for an operator who deliberately wants a bounded run;
    # 0 (the default) means every matching table.
    max_tables: int = field(default_factory=lambda: int(_env("BI_SCHEMA_MAX_TABLES", "0") or "0"))
    # Filled in by the scanner so the run can say what it saw and what it left out. A cap that
    # drops tables silently is indistinguishable, from the outside, from a database that does
    # not have them.
    discovered_tables: int = 0
    truncated_tables: list[str] = field(default_factory=list)
    skip_samples: bool = False
    skip_profile: bool = False
    recreate_collection: bool = False
    out_dir: Path = field(
        default_factory=lambda: Path(
            _env("PHASE2_OUT_DIR", "/data/nanobaseai/bi/frontend/docs/architecture")
        )
    )

    def resolved_collection(self) -> str:
        return self.collection or f"bi_schema_{self.datasource_id}"

    # --- driver detection (postgres default; mssql via secrets map) ---------

    def _mssql_map_entry(self) -> dict[str, Any] | None:
        path = self.secrets_root / "mssql-ro.datasources.json"
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        cfg = (raw.get("sources") or raw).get(self.datasource_id)
        return cfg if isinstance(cfg, dict) and cfg.get("host") else None

    @property
    def driver(self) -> str:
        return "mssql" if self._mssql_map_entry() else "postgres"

    def mssql_connect_cfg(self) -> dict[str, Any]:
        cfg = self._mssql_map_entry()
        if not cfg:
            raise SystemExit(f"datasource not found in mssql-ro map: {self.datasource_id}")
        pw = cfg.get("password") or ""
        if not pw and cfg.get("password_file"):
            pw = Path(cfg["password_file"]).read_text(encoding="utf-8").strip()
        if not pw and cfg.get("secret_ref", "").startswith("file:"):
            pw = Path(cfg["secret_ref"][5:]).read_text(encoding="utf-8").strip()
        return {
            "host": cfg["host"],
            "port": int(cfg.get("port") or 1433),
            "database": cfg.get("database") or "master",
            "user": cfg.get("user") or cfg.get("username") or "",
            "password": pw,
            "tds_version": cfg.get("tds_version") or "7.4",
            "table_patterns": list(cfg.get("table_patterns") or []),
            "allowed_schemas": list(cfg.get("allowed_schemas") or ["dbo"]),
        }

    def pg_connect_kwargs(self) -> dict[str, Any]:
        ds = self.datasource_id
        reporting_id = _reporting_datasource_id()
        # Legacy checklist alias → configured reporting id
        if ds == "nanobase_test":
            ds = reporting_id
        if ds == reporting_id:
            pw_path = self.secrets_root / "reporting-ro.password"
            pw = pw_path.read_text(encoding="utf-8").strip() if pw_path.is_file() else _env("REPORTING_RO_PASSWORD")
            return {
                "host": _env("REPORTING_HOST", "127.0.0.1"),
                "port": int(_env("REPORTING_PORT", "5435") or "5435"),
                "dbname": _env("REPORTING_DB", reporting_id),
                "user": _env("REPORTING_RO_USER", f"{reporting_id}_ro"),
                "password": pw,
                "sslmode": "disable",
                "connect_timeout": 20,
            }

        neon_path = self.secrets_root / "neon-ro.datasources.json"
        if not neon_path.is_file():
            raise SystemExit(f"datasource not found: {ds} (no neon-ro map)")
        neon = json.loads(neon_path.read_text(encoding="utf-8"))
        cfg = (neon.get("sources") or {}).get(ds)
        if not isinstance(cfg, dict):
            raise SystemExit(f"datasource not found: {ds}")
        pw = cfg.get("password") or ""
        if not pw and cfg.get("password_file"):
            pw = Path(cfg["password_file"]).read_text(encoding="utf-8").strip()
        return {
            "host": cfg["host"],
            "port": int(cfg.get("port") or 5432),
            "dbname": cfg.get("database") or "neondb",
            "user": cfg["user"],
            "password": pw,
            "sslmode": cfg.get("sslmode") or "require",
            "connect_timeout": 20,
        }


# Low-cardinality columns allowed for DISTINCT samples / status profiling
SAMPLE_ALLOWLIST = frozenset(
    {
        "status",
        "city",
        "country",
        "currency",
        "currency_code",
        "invoice_type",
        "payment_status",
        "segment",
        "category",
        "order_status",
        "invoice_status",
        "code",
    }
)

# Never sample these (PII / free text)
SAMPLE_BLOCKLIST = frozenset(
    {
        "name",
        "email",
        "phone",
        "identity_number",
        "iban",
        "address",
        "description",
        "free_text",
        "password",
        "token",
        "line1",
        "customer_name",
        "product_name",
        "company_name",
        "notes",
        "comment",
        "comments",
    }
)

# Heuristic Turkish descriptions (override empty PG comments)
TABLE_DESCRIPTIONS: dict[str, str] = {
    "customers": "Müşteri master kaydı",
    "products": "Ürün / SKU kataloğu",
    "orders": "Satış siparişleri",
    "order_items": "Sipariş kalemleri",
    "invoices": "Müşterilere kesilen faturalar",
    "payments": "Fatura tahsilat / ödeme kayıtları",
    "sales_orders": "Satış siparişleri (zengin şema)",
    "sales_order_items": "Satış sipariş kalemleri",
    "customer_addresses": "Müşteri adresleri",
    "companies": "Şirket / tüzel kişi kayıtları",
    "branches": "Şube / lokasyon kayıtları",
    "currency_rates": "Döviz kurları",
    "returns": "İade kayıtları",
    "v_order_revenue": "Sipariş bazlı gelir görünümü",
    "v_invoice_aging": "Fatura yaşlandırma görünümü",
}

COLUMN_DESCRIPTIONS: dict[tuple[str, str], str] = {
    ("invoices", "remaining_amount"): "Faturanın henüz tahsil edilmemiş tutarı",
    ("invoices", "gross_amount"): "Fatura brüt tutarı",
    ("invoices", "status"): "Fatura durumu (open/partial/paid/overdue/cancelled)",
    ("invoices", "invoice_date"): "Fatura kesim tarihi",
    ("invoices", "due_date"): "Fatura vade tarihi",
    ("customers", "segment"): "Müşteri segmenti (Enterprise/SMB/...)",
    ("customers", "country"): "Müşteri ülkesi",
    ("orders", "status"): "Sipariş durumu",
    ("products", "unit_price"): "Ürün birim fiyatı",
    ("products", "category"): "Ürün kategorisi",
}
