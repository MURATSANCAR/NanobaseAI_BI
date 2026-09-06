"""Logical ↔ physical naming for Logo-style period tables.

Physical  : dbo.LG_411_01_INVOICE, dbo_LG_411_01_INVOICE (MDL model name), [dbo].[LG_411_01_INVOICE]
Logical   : entity=INVOICE, table_pattern=LG_{firm}_{period}_INVOICE, context={firm: 411, period: 01}

The catalog never stores LG_411_01_*; mappings are defined on entity.column and instantiated with a
context at compile time, so LG_002_01 / LG_003_02 environments share the same semantics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PERIOD = re.compile(r"^LG_(\d{3})_(\d{2})_([A-Z0-9_]+)$", re.I)
_FIRM = re.compile(r"^LG_(\d{3})_([A-Z0-9_]+)$", re.I)
_SCHEMA_PREFIX = re.compile(r"^(?:\[?dbo\]?[._])", re.I)


@dataclass(frozen=True)
class LogicalTable:
    entity: str
    table_pattern: str
    context: dict[str, str]
    schema_name: str = "dbo"

    def physical(self, context: dict[str, str] | None = None) -> str:
        ctx = dict(self.context)
        ctx.update(context or {})
        out = self.table_pattern
        for k, v in ctx.items():
            out = out.replace("{" + k + "}", str(v))
        return out


def strip_quotes(name: str) -> str:
    return (name or "").strip().strip('"').strip("[]").strip("`")


def logical_table(name: str, schema_name: str = "dbo") -> LogicalTable:
    """Any physical / MDL spelling → logical table. Unknown patterns map onto themselves."""
    raw = strip_quotes(name)
    if "." in raw:
        parts = [strip_quotes(p) for p in raw.split(".")]
        if len(parts) >= 2 and parts[-2]:
            schema_name = parts[-2]
        raw = parts[-1]
    else:
        m = _SCHEMA_PREFIX.match(raw)
        if m:
            raw = raw[m.end():]
    up = raw.upper()
    m = _PERIOD.match(up)
    if m:
        firm, period, entity = m.groups()
        return LogicalTable(entity, f"LG_{{firm}}_{{period}}_{entity}", {"firm": firm, "period": period}, schema_name)
    m = _FIRM.match(up)
    if m:
        firm, entity = m.groups()
        return LogicalTable(entity, f"LG_{{firm}}_{entity}", {"firm": firm}, schema_name)
    return LogicalTable(up, up, {}, schema_name)


def physical_name(table_pattern: str, context: dict[str, str]) -> str:
    out = table_pattern
    for k, v in (context or {}).items():
        out = out.replace("{" + k + "}", str(v))
    return out


def mdl_model_name(table_pattern: str, context: dict[str, str], schema_name: str = "dbo") -> str:
    """Model spelling used by the legacy WrenAI pairs: dbo_LG_411_01_INVOICE."""
    return f"{schema_name}_{physical_name(table_pattern, context)}"


def entity_of(name: str) -> str:
    return logical_table(name).entity


# Logo ERP reference-column conventions (used when FK constraints are absent, which is the norm).
LOGO_REF_TARGETS: dict[str, str] = {
    "CLIENTREF": "CLCARD",
    "STOCKREF": "ITEMS",
    "INVOICEREF": "INVOICE",
    "ORDFICHEREF": "ORFICHE",
    "STFICHEREF": "STFICHE",
    "SALESMANREF": "SLSMAN",
    "PROJECTREF": "PROJECT",
    "PAYMENTREF": "PAYPLANS",
    "UOMREF": "UNITSETL",
    "ACCOUNTREF": "EMUHACC",
    "BANKACCREF": "BANKACC",
}


def infer_ref_target(column: str) -> tuple[str, str] | None:
    """*REF column → (entity, key column) via Logo naming; None when unknown."""
    col = (column or "").upper()
    if col in LOGO_REF_TARGETS:
        return LOGO_REF_TARGETS[col], "LOGICALREF"
    if col.endswith("REF") and len(col) > 3:
        return col[:-3], "LOGICALREF"
    return None
