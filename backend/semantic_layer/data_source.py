"""Which business system a table belongs to, as the screens show it.

Logo tables live in the ERP database's own schema (``dbo``); the CRM is a second database read over the
same connection, so its tables carry the database in their schema (``Timas_MSCRM.dbo``). That schema is
the only reliable signal — table names overlap in style and the scan does not record a system.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

LOGO = "logo"
CRM = "crm"


def data_source(schema_name: Optional[str]) -> str:
    return CRM if "MSCRM" in (schema_name or "").upper() else LOGO


def source_by_entity(profiles: Iterable[Any]) -> dict[str, str]:
    return {p.entity: data_source(getattr(p, "schema_name", None)) for p in profiles}
