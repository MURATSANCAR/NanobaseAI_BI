"""The vendor dictionary as a schema our own system can hold — every table, not the seven we profiled.

`configs/schemas/logo-ldds.json` documents 330 logical tables and 9.303 columns. The knowledge pack
carried model files for seven of them, so a catalog built here showed seven tables and a question
about anything else had nowhere to land. The physical database is those 330 multiplied out — one copy
per firm and per firm-period, which is how a customer arrives at eight thousand tables — but the
meanings are written once, and once is what has to reach the catalog.

This writes a model file per table. Deliberately thin: the name, and the columns with their types.
Everything else — what a table means, what a column holds, what its codes are, which columns are
unique, what joins to what — the offline connector already reads from the dictionary at load time,
so duplicating it here would be a second copy to keep in step.

    python backend/scripts/export_dictionary_models.py            # firm 411, period 01
    python backend/scripts/export_dictionary_models.py --firm 211 --period 05

Model files already in the pack are left alone: those are real profiles of real data, with value
distributions and units this cannot produce. Generated files carry `generated: true`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DICTIONARY = REPO / "configs" / "schemas" / "logo-ldds.json"
PACK = REPO / "configs" / "semantic" / "knowledge" / "logo"

#: The dictionary writes the vendor's own storage types. A profile is read as SQL, so they arrive as
#: the type names the rest of the pack uses — the mapping is by storage width, not by guesswork.
TYPES = {
    "LONGINT": "INTEGER", "INTEGER": "SMALLINT", "BYTE": "SMALLINT", "WORD": "INTEGER",
    "DOUBLE": "FLOAT8", "FLOAT": "FLOAT8", "REAL": "FLOAT8",
    "ZSTRING": "TEXT", "PSTRING": "TEXT", "STRING": "TEXT", "CHAR": "TEXT",
    "RECORD": "BYTEA", "IMAGE": "BYTEA", "BLOB": "BYTEA",
    "DATE": "TIMESTAMP", "TIME": "TIMESTAMP", "DATETIME": "TIMESTAMP",
}


def sql_type(vendor: str, size: int | None) -> str:
    name = TYPES.get(str(vendor or "").strip().upper(), "")
    if not name:
        return str(vendor or "TEXT").upper()
    if name == "TEXT" and size:
        return f"VARCHAR({size})"
    return name


def physical(table: str, scope: str, firm: str, period: str) -> str:
    """One dictionary entry names one table; a database holds a copy per firm and per period."""
    if scope == "database":
        return f"L_{table}"
    if scope == "period":
        return f"LG_{firm}_{period}_{table}"
    return f"LG_{firm}_{table}"


def yaml_quote(text: str) -> str:
    return '"' + str(text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip() + '"'


def model_file(table: str, entry: dict, firm: str, period: str) -> tuple[str, str]:
    name = physical(table, entry.get("scope", "firm"), firm, period)
    lines = [
        "# Generated from the vendor data dictionary by backend/scripts/export_dictionary_models.py.",
        "# Column meanings, code sets, keys and joins are read from configs/schemas/logo-ldds.json at",
        "# load time and are deliberately not copied here. Do not edit; re-run the generator.",
        "generated: true",
        f"name: {yaml_quote('dbo_' + name)}",
        "table_reference:",
        '  catalog: "LOGO_DB"',
        '  schema: "dbo"',
        f"  table: {yaml_quote(name)}",
        "properties:",
        f"  \"displayName\": {yaml_quote('dbo.' + name)}",
        "columns:",
    ]
    for column, meta in entry.get("columns", {}).items():
        lines.append(f"  - name: {yaml_quote(column)}")
        lines.append(f"    type: {yaml_quote(sql_type(meta.get('type'), meta.get('size')))}")
    return f"dbo_{name}", "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firm", default="411", help="firm number the generated names carry (default 411)")
    ap.add_argument("--period", default="01", help="period number for period-scoped tables (default 01)")
    ap.add_argument("--pack", default=str(PACK), help="knowledge pack to write into")
    args = ap.parse_args(argv)

    data = json.loads(DICTIONARY.read_text(encoding="utf-8"))
    models = Path(args.pack) / "models"
    models.mkdir(parents=True, exist_ok=True)

    written, kept = 0, []
    for table, entry in sorted(data["tables"].items()):
        if not entry.get("columns"):
            continue
        directory, text = model_file(table, entry, args.firm, args.period)
        target = models / directory / "metadata.yml"
        if target.exists() and "generated: true" not in target.read_text(encoding="utf-8"):
            kept.append(directory)          # a real profile of real data — never overwritten
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written += 1

    columns = sum(len(t.get("columns") or {}) for t in data["tables"].values())
    print(f"{models.relative_to(REPO)}: {written} tablo yazıldı, {len(kept)} gerçek profil korundu "
          f"({', '.join(sorted(kept)) if kept else '—'})")
    print(f"sözlükteki toplam: {data['table_count']} tablo, {columns} kolon")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
