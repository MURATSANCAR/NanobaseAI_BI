"""SAP S/4HANA OData + SAP HANA hardened adapters (Faz 9)."""

from __future__ import annotations

HANA_SQLGLOT_DIALECT = "postgres"  # sqlglot has no native HANA; fail-closed policy wraps it
DEFAULT_HANA_TABLES: set[str] | None = None

FORBIDDEN_RAW_SAP_TABLES = frozenset(
    {
        "ACDOCA",
        "BKPF",
        "BSEG",
        "VBAK",
        "VBAP",
        "EKKO",
        "EKPO",
        "MARA",
        "MARC",
        "KNA1",
        "LFA1",
    }
)

SOURCE_STATUSES = (
    "DISCOVERED",
    "TECHNICALLY_VALIDATED",
    "FUNCTIONALLY_VALIDATED",
    "APPROVED",
    "PUBLISHED",
    "DEPRECATED",
    "STALE",
    "REJECTED",
)

PUBLISHED_ONLY = "PUBLISHED"

__all__ = [
    "HANA_SQLGLOT_DIALECT",
    "DEFAULT_HANA_TABLES",
    "FORBIDDEN_RAW_SAP_TABLES",
    "SOURCE_STATUSES",
    "PUBLISHED_ONLY",
]
