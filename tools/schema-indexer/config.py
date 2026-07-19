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
    max_tables: int = field(default_factory=lambda: int(_env("BI_SCHEMA_MAX_TABLES", "200") or "200"))
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

    def pg_connect_kwargs(self) -> dict[str, Any]:
        ds = self.datasource_id
        # Alias used in ChatGPT checklist → our reporting DB
        if ds in ("nanobase_test", "bi_reporting"):
            pw_path = self.secrets_root / "reporting-ro.password"
            pw = pw_path.read_text(encoding="utf-8").strip() if pw_path.is_file() else _env("REPORTING_RO_PASSWORD")
            return {
                "host": _env("REPORTING_HOST", "127.0.0.1"),
                "port": int(_env("REPORTING_PORT", "5435") or "5435"),
                "dbname": _env("REPORTING_DB", "bi_reporting"),
                "user": _env("REPORTING_RO_USER", "bi_reporting_ro"),
                "password": pw,
                "sslmode": "disable",
                "connect_timeout": 20,
            }

        neon_path = self.secrets_root / "neon-ro.datasources.json"
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
