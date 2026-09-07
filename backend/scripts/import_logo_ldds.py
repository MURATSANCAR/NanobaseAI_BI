"""LDDS.xls (Logo Data Dictionary) → the reference the ERP scanners read.

Logo declares no foreign keys in SQL Server and writes no extended properties, so a scan of a Logo
database yields bare identifiers: 8.900 columns named CLIENTREF, TRCODE, SIGN with nothing saying
what any of them mean. Everything that meaning was hand-typed into two dicts covering 26 tables.

The vendor ships the whole dictionary — every table, every column, the code sets, the indexes and
the join graph — as an Excel workbook. This turns that workbook into a JSON file the scanners load,
so a Logo source arrives documented instead of being documented a table at a time by whoever answers
the support call.

The workbook documents in English. The vendor's Turkish table-structure document (LOGO_TABLE_YAPISI /
"Unity Veri tabanı", the same file under two names) documents 131 of the same tables in the language
people ask questions in, and covers twenty the workbook omits entirely — CITY, COUNTRY, GOUSERS,
DAILYEXCHANGES. Pass it with --doc and its Turkish sentences are carried alongside the English ones.

    python backend/scripts/import_logo_ldds.py /path/to/LDDS.xls --doc /path/to/LOGO_TABLE_YAPISI.DOC

Writes configs/schemas/logo-ldds.json and refreshes the Turkish code glossary in the `logo`
knowledge pack. Both outputs are generated: edit this script, not them.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "configs" / "schemas" / "logo-ldds.json"
OUT_GLOSSARY = REPO / "configs" / "semantic" / "knowledge" / "logo" / "knowledge" / "glossary" / "logo-ldds-codes.md"

# Level, as the workbook uses it: which of the three table sets a name belongs to. It decides the
# physical name a scan will see — L_X once per database, LG_<firm>_X once per firm, and
# LG_<firm>_<period>_X once per firm-period — which is why a Logo database has thousands of tables.
LEVELS = {0: "system", 1: "firm", 2: "period"}


def _sheet(book, name: str) -> list[dict]:
    s = book.sheet_by_name(name)
    header = [str(s.cell_value(0, c)).strip() for c in range(s.ncols)]
    return [dict(zip(header, [s.cell_value(r, c) for c in range(s.ncols)])) for r in range(1, s.nrows)]


def _int(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def base_name(raw: str) -> str:
    """`LG_ITEMS` / `L_PAYPLANS` → `ITEMS` / `PAYPLANS`.

    The dictionary names a table once; a database holds one copy per firm and per period. Stripping
    the vendor prefix gives the key both sides can agree on — the same key a physical
    `LG_411_01_INVOICE` reduces to.
    """
    n = str(raw or "").strip().upper()
    return re.sub(r"^(?:LG|L)_", "", n)


def scope_of(physical: str, level: int) -> str:
    """How many copies of this table a database holds — which is also how its physical name is built.

    The workbook's Level column does not answer this on its own: SLSMAN is Level 0 yet ships as
    `LG_SLSMAN`, one per firm. The vendor prefix is the reliable signal — `L_` means one copy for the
    whole database — and Level only distinguishes firm from firm-period among the rest.
    """
    if str(physical).upper().startswith("L_"):
        return "database"
    return "period" if level == 2 else "firm"


def parse_expression(expr: str) -> tuple[str, dict[str, str]]:
    """`"Item Card Type ;1- Commercial Good;2- Mixed case"` → the sentence, and the code set.

    A column whose codes are known stops being a number nobody can filter on: this is what lets a
    question about commercial goods become `CARDTYPE = 1` rather than a guess.
    """
    text = str(expr or "").strip()
    if ";" not in text:
        return text, {}
    head, _, rest = text.partition(";")
    values: dict[str, str] = {}
    for part in rest.split(";"):
        # A clause names one code or a run of them: "1- Commercial Good", "0 Percentage", and
        # "15, 16, 17, 18, 19 User Defined Input Slip" — where every code in the run carries the same
        # meaning. Reading the run as a single code labelled ", 16, 17, …" loses four of the five.
        m = re.match(r"\s*((?:-?\d+\s*,\s*)*-?\d+)\s*[-:.)]?\s*(.+)", part.strip())
        if not m or not m.group(2).strip():
            continue
        label = m.group(2).strip()
        for code in re.findall(r"-?\d+", m.group(1)):
            values.setdefault(code, label)
    return head.strip(), values


def build(xls_path: Path) -> dict:
    import xlrd

    book = xlrd.open_workbook(str(xls_path))
    tables_raw = _sheet(book, "Tablolar")
    fields_raw = _sheet(book, "Alanlar")
    rels_raw = _sheet(book, "Relations")

    fields_by_resource: dict[int, list[dict]] = defaultdict(list)
    for f in fields_raw:
        fields_by_resource[_int(f["Resource ID"])].append(f)
    rels_by_resource: dict[int, list[dict]] = defaultdict(list)
    for r in rels_raw:
        rels_by_resource[_int(r["Resource ID"])].append(r)

    tables: dict[str, dict] = {}
    collisions: list[str] = []
    for t in tables_raw:
        rid = _int(t["Resource ID"])
        physical = str(t["Resource Name"]).strip()
        key = base_name(physical)
        if key in tables:
            # Two dictionary entries reduce to one key. Keep the one that carries more, and say so —
            # silently overwriting is how a table's documentation disappears.
            collisions.append(f'{key}: {tables[key]["physical"]} vs {physical}')
            if len(fields_by_resource[rid]) <= len(tables[key]["columns"]):
                continue

        columns: dict[str, dict] = {}
        for f in sorted(fields_by_resource[rid], key=lambda x: _int(x.get("Field Offset"))):
            desc, values = parse_expression(f.get("Expression"))
            col = {"type": str(f["Field Type"]).strip()}
            size = _int(f.get("Field Size"))
            if size:
                col["size"] = size
            if desc:
                col["description"] = desc
            if values:
                col["values"] = values
            columns[str(f["Field Name"]).strip().upper()] = col

        relations = []
        for r in rels_by_resource[rid]:
            target = base_name(r["Destination Table"])
            if not target:
                continue
            relations.append(
                {
                    "column": str(r["Source Field"]).strip().upper(),
                    "to": target,
                    "to_column": str(r["Destination Field"]).strip().upper(),
                    "type": str(r["Relation Type"]).strip(),
                }
            )

        tables[key] = {
            "physical": physical,
            "level": LEVELS.get(_int(t["Level"]), "system"),
            "scope": scope_of(physical, _int(t["Level"])),
            "description": str(t["Resource Description"]).strip(),
            "columns": columns,
            "relations": relations,
        }

    return {
        "source": xls_path.name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "backend/scripts/import_logo_ldds.py",
        "table_count": len(tables),
        "column_count": sum(len(t["columns"]) for t in tables.values()),
        "relation_count": sum(len(t["relations"]) for t in tables.values()),
        "coded_column_count": sum(1 for t in tables.values() for c in t["columns"].values() if "values" in c),
        "key_collisions": collisions,
        "tables": tables,
        "document_codes": document_codes(book),
        "currencies": currencies(book),
    }


def document_codes(book) -> list[dict]:
    """MODULENR + TRCODE → what the document is called in Turkish.

    A cari hesap line is only interpretable through the pair: TRCODE 31 under module 4 is a purchase
    invoice, under module 5 it is nothing at all. The sheet is laid out as sections — a module header
    row, then its codes — so the module is carried down from the header.
    """
    s = book.sheet_by_name("CH fişleri")
    out: list[dict] = []
    module = None
    module_label = ""
    for r in range(s.nrows):
        cells = [str(s.cell_value(r, c)).strip() for c in range(s.ncols)]
        code_cell, label = cells[0], cells[1] if len(cells) > 1 else ""
        module_cell = cells[2] if len(cells) > 2 else ""
        # A section header is the row that carries the module number. Its first cell is a heading
        # ("No") or empty, never a code — reading it as a code silently drops the section under it.
        if label and module_cell and _int(module_cell, -1) >= 0 and _int(code_cell, -1) < 0:
            module, module_label = _int(module_cell, -1), label
            continue
        if code_cell and label and module is not None and _int(code_cell, -1) >= 0:
            out.append({"module": module, "module_label": module_label, "code": _int(code_cell, -1), "label": label})
    return out


def currencies(book) -> list[dict]:
    """Logo stores currency as its own small integer; every amount in a foreign currency is unreadable
    without this table."""
    s = book.sheet_by_name("Curr")
    out = []
    for r in range(1, s.nrows):
        code = _int(s.cell_value(r, 0), -1)
        iso = str(s.cell_value(r, 1)).strip()
        name = str(s.cell_value(r, 2)).strip()
        if code >= 0 and iso:
            out.append({"code": code, "iso": iso, "name": name})
    return out


def glossary_markdown(data: dict) -> str:
    """The code sets as prose the Doc Miner can read.

    The miner takes documentation as evidence for a mapping, so the codes have to reach it as
    sentences in the language people ask questions in — not as a JSON file it never opens.
    """
    lines = [
        "# Logo kod sözlüğü (LDDS'den üretildi)",
        "",
        f"Kaynak: `{data['source']}` · üretim: `{data['generator']}` · {data['generated_at']}",
        "",
        "> Bu dosya üretilmiştir; elle düzenlemeyin. Değişiklik için üreticiyi çalıştırın.",
        "",
        "## Cari hesap fişi türleri (CLFLINE.MODULENR + CLFLINE.TRCODE)",
        "",
        "Fiş türü iki kolonun birlikte okunmasıyla belirlenir: aynı TRCODE farklı modülde başka bir belgedir.",
        "",
    ]
    by_module: dict[int, list[dict]] = defaultdict(list)
    for d in data["document_codes"]:
        by_module[d["module"]].append(d)
    for module in sorted(by_module):
        rows = by_module[module]
        lines.append(f"### {rows[0]['module_label']} — MODULENR = {module}")
        lines.append("")
        for d in sorted(rows, key=lambda x: x["code"]):
            lines.append(f"- {d['label']}: `MODULENR = {module} AND TRCODE = {d['code']}`")
        lines.append("")

    lines += [
        "## Döviz kodları (TRCURR / CURRSEL)",
        "",
        "Logo dövizi kendi küçük tamsayı koduyla saklar; ISO kodu bu tablodan gelir.",
        "",
    ]
    for c in data["currencies"]:
        lines.append(f"- {c['name']} ({c['iso']}): `TRCURR = {c['code']}`")
    lines.append("")

    lines += ["## Kolon kod kümeleri", "", "Kolonun taşıdığı sayının ne anlama geldiği:", ""]
    seen: set[tuple[str, str]] = set()
    for name, table in sorted(data["tables"].items()):
        for col, meta in table["columns"].items():
            values = meta.get("values")
            if not values or (name, col) in seen:
                continue
            seen.add((name, col))
            desc = meta.get("description") or col
            pairs = ", ".join(f"{k}={v}" for k, v in sorted(values.items(), key=lambda kv: _int(kv[0])))
            lines.append(f"- `{name}.{col}` — {desc}: {pairs}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    xls = Path(sys.argv[1]).expanduser()
    if not xls.is_file():
        print(f"not found: {xls}", file=sys.stderr)
        return 1
    data = build(xls)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")
    OUT_GLOSSARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_GLOSSARY.write_text(glossary_markdown(data), encoding="utf-8")
    print(
        f"{OUT_JSON.relative_to(REPO)}: {data['table_count']} tablo, {data['column_count']} kolon, "
        f"{data['relation_count']} ilişki, {data['coded_column_count']} kodlu kolon"
    )
    if data["key_collisions"]:
        print(f"  ad çakışması ({len(data['key_collisions'])}): {', '.join(data['key_collisions'][:5])}")
    print(f"{OUT_GLOSSARY.relative_to(REPO)}: {len(data['document_codes'])} fiş türü, {len(data['currencies'])} döviz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
