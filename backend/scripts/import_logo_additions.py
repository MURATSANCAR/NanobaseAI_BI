"""Merge the reviewed additions file into the Logo dictionary.

Run after import_logo_ldds.py and import_logo_web.py. `configs/schemas/logo-column-additions.json` holds
what the 2026-10-03 survey learned (docs/analiz/kolon-eslestirme/): tables and columns that exist in the
customer's live Logo but neither the workbook nor the first web import described, each with its source,
and the codes confirmed against live data (confidence "verified").

Rules: a documented entry only fills what is empty; it never displaces text the vendor or a person
wrote. A verified code set replaces an undocumented or vendor code set, because it was read from the
customer's own data; the replaced labels stay in the audit. Re-running is a no-op.

    python backend/scripts/import_logo_additions.py [--check]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from import_logo_ldds import OUT_GLOSSARY, OUT_JSON, REPO, glossary_markdown

ADDITIONS = REPO / "configs" / "schemas" / "logo-column-additions.json"
FIELDS = ("description_tr", "description", "values_tr", "web_source", "confidence", "verified")


def merge(data: dict, additions: dict) -> dict:
    audit = {"tables_added": [], "columns_added": 0, "descriptions_filled": 0, "codes_verified": [], "replaced_codes": {}}
    tables = data.setdefault("tables", {})
    for name, add in sorted(additions.get("tables", {}).items()):
        table = tables.get(name)
        if table is None:
            table = tables[name] = {"physical": add["physical"], "level": add["scope"], "scope": add["scope"],
                                    "columns": {}, "source": "logo-column-additions"}
            for key in ("description_tr", "description", "web_source", "confidence"):
                if add.get(key):
                    table[key] = add[key]
            audit["tables_added"].append(name)
        elif add.get("description_tr") and not table.get("description_tr"):
            table["description_tr"] = add["description_tr"]
        columns = table.setdefault("columns", {})
        for col, entry in sorted(add.get("columns", {}).items()):
            current = columns.get(col)
            if current is None:
                columns[col] = {k: entry[k] for k in FIELDS if entry.get(k)} | {"source": "logo-column-additions"}
                audit["columns_added"] += 1
                continue
            if entry.get("confidence") == "verified":
                old = current.get("values_tr") or current.get("values")
                if entry.get("values_tr") and old != entry["values_tr"]:
                    if old:
                        audit["replaced_codes"][f"{name}.{col}"] = old
                    current["values_tr"] = entry["values_tr"]
                    current.pop("values", None)         # the vendor's English labels named the old codes
                    audit["codes_verified"].append(f"{name}.{col}")
                current["verified"] = entry["verified"]
                if not current.get("description_tr"):
                    current["description_tr"] = entry["description_tr"]
                    audit["descriptions_filled"] += 1
                continue
            for key in ("description_tr", "description"):
                if entry.get(key) and not current.get(key):
                    current[key] = entry[key]
                    current.setdefault("web_source", entry.get("web_source"))
                    audit["descriptions_filled"] += 1
            if entry.get("values_tr") and not (current.get("values_tr") or current.get("values")):
                current["values_tr"] = entry["values_tr"]
    data["additions_source"] = {"file": str(ADDITIONS.relative_to(REPO)), "generated_at": additions.get("generated_at")}
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    args = parser.parse_args()
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    audit = merge(data, json.loads(ADDITIONS.read_text(encoding="utf-8")))
    summary = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in audit.items()}
    if not args.check:
        data["table_count"] = len(data["tables"])
        data["column_count"] = sum(len(t.get("columns") or {}) for t in data["tables"].values())
        OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        OUT_GLOSSARY.write_text(glossary_markdown(data), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
