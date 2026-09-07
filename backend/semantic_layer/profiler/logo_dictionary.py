"""Logo's own data dictionary, as a source of table and column meaning.

Logo (Tiger/Go/Unity) creates no foreign keys and writes no extended properties. A read of
INFORMATION_SCHEMA therefore returns bare identifiers — nearly nine thousand of them — with no
statement anywhere in the database about what any column holds or which tables join to which.
Every other source we profile carries at least comments; this one carries none.

What it does have is a dictionary the vendor publishes as a workbook, imported by
`backend/scripts/import_logo_ldds.py` into `configs/schemas/logo-ldds.json`. This module reads that
file and answers the two questions the database refuses to: what a table and column mean, and what
the join graph is.

The JSON file — not this module — is the contract: the schema indexer reads the same file through
its own loader, because it deploys as a standalone tool with its own import root.

Nothing here fabricates anything. A physical name the dictionary does not know, a source that is not
Logo, or a deployment that has not imported the workbook all yield nothing, and profiling proceeds
exactly as it did before.
"""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

#: `LG_411_01_STLINE` → prefix + base. The dictionary names a table once; a database holds one copy
#: per firm (`LG_<firm>_X`) and one per firm-period (`LG_<firm>_<period>_X`), plus the global `L_X`.
_PHYSICAL = re.compile(r"^(?P<prefix>L_|LG_(?P<firm>\d+)_(?:(?P<period>\d+)_)?)(?P<base>[A-Z][A-Z0-9_]*)$")


def parts(table_name: str) -> tuple[str, Optional[str], Optional[str]]:
    """(base, firm, period) for a physical Logo name; (name, None, None) for anything else."""
    m = _PHYSICAL.match((table_name or "").upper())
    if not m:
        return (table_name or "").upper(), None, None
    return m.group("base"), m.group("firm"), m.group("period")


def dictionary_path() -> Path:
    env = os.environ.get("LOGO_LDDS_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "configs" / "schemas" / "logo-ldds.json"


@lru_cache(maxsize=1)
def dictionary() -> dict[str, Any]:
    path = dictionary_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.debug("Logo data dictionary unavailable (%s): %s", path, e)
        return {}
    log.info("Logo data dictionary: %d tables, %d columns, %d relations",
             data.get("table_count", 0), data.get("column_count", 0), data.get("relation_count", 0))
    return data


def _entry(table_name: str) -> dict[str, Any]:
    return (dictionary().get("tables") or {}).get(parts(table_name)[0]) or {}


def is_logo_schema(table_names: list[str]) -> bool:
    """Whether this looks like a Logo database at all — a quarter of the names being ones the
    dictionary knows is far past coincidence, and well under what a partial scope would match."""
    if not dictionary() or not table_names:
        return False
    known = sum(1 for n in table_names if _entry(n))
    return known >= max(3, len(table_names) // 4)


def _bilingual(entry: dict[str, Any]) -> str:
    """The vendor documents in both languages, and neither one alone is enough.

    Questions arrive in Turkish, so "Cari hesap kartları" is the text a question about cari hesap can
    match; the English is the text the column names themselves were built from, and the only thing
    that reads like `CLCARD`. Where the vendor gives both, both are kept.
    """
    tr = str(entry.get("description_tr") or "").strip()
    en = str(entry.get("description") or "").strip()
    if tr and en and tr.casefold() != en.casefold():
        return f"{tr} ({en})"
    return tr or en


def column_description(table_name: str, column: str) -> str:
    """What the column holds, with its code set when the vendor documented one.

    The codes are the part that changes an answer. A line-classification column described only as
    "line type" is unusable; the same column with its code set spelled out is the difference between
    summing the goods on an invoice and summing the goods plus the discount lines.
    """
    entry = (_entry(table_name).get("columns") or {}).get((column or "").upper())
    if not entry:
        return ""
    # Turkish labels first where the vendor wrote them: a question asking for indirim satırları has
    # to match "İndirim", not "Discount".
    values = entry.get("values_tr") or entry.get("values") or {}
    if not values:
        return _bilingual(entry)
    # With a code set the codes are the point, so the head stays to one language rather than two.
    head = str(entry.get("description_tr") or entry.get("description") or "").strip()
    codes = ", ".join(f"{k}={v}" for k, v in sorted(values.items(), key=lambda kv: int(kv[0])))
    return f"{head} ({codes})" if head else codes


def table_description(table_name: str) -> str:
    return _bilingual(_entry(table_name))


def primary_key(table_name: str, columns: list[str] | None = None) -> list[str]:
    """The primary key a Logo database does not declare.

    Logo enforces uniqueness in the application, not in SQL Server: the constraint query returns
    nothing for every table it owns, so profiling reports a schema in which no row is identifiable.
    The dictionary's index listing says which columns are unique, and the one that matters is the
    same everywhere — `LOGICALREF`, what every `*REF` column in the database points at.
    """
    indexes = _entry(table_name).get("indexes") or []
    present = {c.upper() for c in columns} if columns is not None else None
    unique = [ix for ix in indexes
              if ix.get("unique") and ix.get("columns")
              and (present is None or present.issuperset(ix["columns"]))]
    if not unique:
        return []
    # Shortest first, so a single-column key wins over a composite that also happens to be unique.
    unique.sort(key=lambda ix: (ix["columns"] != ["LOGICALREF"], len(ix["columns"])))
    return list(unique[0]["columns"])


def descriptions(table_names: list[str]) -> dict[tuple[str, Optional[str]], str]:
    """Every table and column the dictionary can speak for, in the shape a connector returns:
    (table, column) → text, with column None for the table itself."""
    out: dict[tuple[str, Optional[str]], str] = {}
    for name in table_names:
        entry = _entry(name)
        if not entry:
            continue
        if desc := table_description(name):
            out[(name, None)] = desc
        for column in entry.get("columns") or {}:
            if text := column_description(name, column):
                out[(name, column)] = text
    return out


def foreign_keys(table_names: list[str]) -> list[dict[str, str]]:
    """The join graph the database does not declare, resolved against the tables actually present.

    A relation is written once against a table; here it is resolved to the copies this database
    holds, which routinely means crossing from a period table to a firm-level one. A target that was
    not scanned is skipped — a join to a table nobody catalogued is worse than no join at all — and
    so is a relation the dictionary leaves without a target column.
    """
    tables = dictionary().get("tables") or {}
    if not tables:
        return []
    present = {(n or "").upper() for n in table_names}
    out: list[dict[str, str]] = []
    for name in table_names:
        entry = _entry(name)
        base, firm, period = parts(name)
        if not entry or firm is None:
            continue
        columns = entry.get("columns") or {}
        seen: set[str] = set()
        for rel in entry.get("relations") or []:
            column, target = rel.get("column", ""), rel.get("to", "")
            if not target or column in seen or column not in columns:
                continue
            ref_column = (rel.get("to_column") or "").strip()
            resolved = _resolve(target, tables, firm, period, present)
            if not resolved or not ref_column:
                continue
            seen.add(column)
            out.append({"table": name, "column": column, "ref_table": resolved, "ref_column": ref_column})
    return out


def _resolve(target: str, tables: dict, firm: str, period: Optional[str], present: set[str]) -> str:
    """The physical name a dictionary target takes in this database, or "" if it was not scanned.

    The workbook's own scope is tried first and the other shapes after it: some tables are listed as
    database-global yet ship once per firm, so the scan set is what settles it.
    """
    forms = {
        "period": f"LG_{firm}_{period}_{target}" if period else "",
        "firm": f"LG_{firm}_{target}",
        "database": f"L_{target}",
    }
    scope = (tables.get(target) or {}).get("scope", "firm")
    order = [scope] + [k for k in ("period", "firm", "database") if k != scope]
    for key in order:
        candidate = forms.get(key)
        if candidate and candidate in present:
            return candidate
    return ""
