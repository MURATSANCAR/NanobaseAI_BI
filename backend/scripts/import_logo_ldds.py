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
import subprocess
import sys
import tempfile
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


# --- the vendor's Turkish table-structure document -------------------------------------------

#: `LG_XXX_ITEMS`, `LG_XXX_XX_STLINE`, `L_CAPIDEF` — a heading on a line of its own. `XXX` is the
#: firm and the inner `XX` the period, the same two placeholders the workbook writes as prefixes.
_DOC_HEADING = re.compile(r"^(?:LG_XXX_\s*(?P<period>XX_)?|(?P<db>L_))(?P<base>[A-Z][A-Z0-9_]*)\s*$")

#: The document was written in Word with a Wingdings arrow, which survives conversion as a private-use
#: codepoint. "Muhasebe hesabı referansı EMUHACC" is the vendor naming a foreign key.
_DOC_ARROW = "\uf0e0"

#: Lines that are table furniture, not a Turkish name for the table above them.
_DOC_FURNITURE = {"Adı", "İndeksler", "İndeks sayısı", "Alan", "Tipi", "Açıklama", "No", "Uzunluk", "Özellik"}


def doc_text(path: Path) -> str:
    """The .DOC as text. Word 97 binary, so it goes through the converter macOS ships."""
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "doc.txt"
        try:
            subprocess.run(
                ["textutil", "-convert", "txt", "-encoding", "UTF-8", "-output", str(out), str(path)],
                check=True, capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as e:
            raise SystemExit(
                f"cannot read {path}: needs `textutil` (macOS) or a .txt export of the document.\n{e}"
            ) from e
        return out.read_text(encoding="utf-8", errors="replace")


def parse_structure_doc(text: str) -> dict[str, dict]:
    """Turkish names for the tables and their columns, plus the foreign keys the arrows name.

    The document is one long Word table flattened to a line per cell, in two passes over the same
    headings: a list that gives each table its Turkish name, then a section per table that gives its
    indexes and its columns as `field / type / Turkish sentence` triples.
    """
    lines = [l.rstrip() for l in text.split("\n")]
    # The table of contents repeats every heading as a HYPERLINK field. Reading it as content would
    # give each table a "description" that is the page number of the section it points at.
    toc = [i for i, l in enumerate(lines) if "HYPERLINK" in l]
    body = lines[max(toc) + 1:] if toc else lines

    out: dict[str, dict] = {}
    current = None
    i = 0
    while i < len(body):
        line = body[i].strip()
        if m := _DOC_HEADING.match(line):
            current = m.group("base")
            entry = out.setdefault(current, {"columns": {}, "relations": []})
            entry.setdefault("scope", "database" if m.group("db") else "period" if m.group("period") else "firm")
            entry.setdefault("physical", line)
            nxt = body[i + 1].strip() if i + 1 < len(body) else ""
            # In the naming list the heading is followed by its Turkish name; in the detail section
            # by the index count. A digit is the detail section, not a name.
            if nxt and "description" not in entry and not _DOC_HEADING.match(nxt) and nxt not in _DOC_FURNITURE:
                if not nxt[0].isdigit() and len(nxt) <= 90:
                    entry["description"] = nxt
            i += 1
            continue

        if line == "Alan" and body[i + 1 : i + 3] and [b.strip() for b in body[i + 1 : i + 3]] == ["Tipi", "Açıklama"]:
            i = _read_column_block(body, i + 3, out.get(current))
            continue
        i += 1
    return out


def _read_column_block(body: list[str], start: int, entry: dict | None) -> int:
    """The `field / type / Turkish sentence` triples under one Alan/Tipi/Açıklama header."""
    i = start
    while i + 2 < len(body):
        name, ftype, desc = (body[i].strip(), body[i + 1].strip(), body[i + 2].strip())
        if not name or _DOC_HEADING.match(name) or name in _DOC_FURNITURE:
            break
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or not ftype:
            break
        if entry is not None:
            target = ""
            if _DOC_ARROW in desc:
                desc, _, tail = desc.partition(_DOC_ARROW)
                m = re.search(r"[A-Z][A-Z0-9_]*", tail)
                target = m.group() if m else ""
            desc = desc.strip()
            if desc:
                entry["columns"][name] = desc
            if target:
                entry["relations"].append({"column": name, "to": target})
        i += 3
    return i


def merge_doc(data: dict, doc: dict[str, dict]) -> dict:
    """Turkish alongside English, and the tables only the document knows.

    Nothing is overwritten: the workbook stays the structural truth — types, sizes, offsets, code
    sets — and the document adds the sentence a Turkish question can actually match against. A table
    the workbook never mentions is carried in with what the document has and marked as such, so a
    consumer can tell a documented column from an undocumented one.
    """
    tables = data["tables"]
    added, tr_tables, tr_columns, unmatched, hinted = [], 0, 0, 0, 0
    for base, entry in sorted(doc.items()):
        target = tables.get(base)
        if target is None:
            tables[base] = target = {
                "physical": entry.get("physical", base),
                "level": {"database": "system", "period": "period"}.get(entry.get("scope", "firm"), "firm"),
                "scope": entry.get("scope", "firm"),
                "description": "",
                "columns": {},
                "relations": [],
                "indexes": [],
                "source": "structure-doc",
            }
            added.append(base)
        if desc := entry.get("description"):
            target["description_tr"] = desc
            tr_tables += 1
        for column, text in entry["columns"].items():
            col = target["columns"].get(column)
            if col is None:
                # The document names a column the workbook does not. It is a real column of an older
                # release; recorded without a type, because the document does not give one we trust.
                col = target["columns"][column] = {"type": "", "source": "structure-doc"}
                unmatched += 1
            col["description_tr"] = text
            tr_columns += 1
        known = {(r["column"], r["to"]) for r in target["relations"]}
        for hint in entry["relations"]:
            if hint["to"] in tables and (hint["column"], hint["to"]) not in known:
                target["relations"].append(
                    {"column": hint["column"], "to": hint["to"], "to_column": "LOGICALREF",
                     "type": "one-to-many", "source": "structure-doc"}
                )
                hinted += 1

    data["table_count"] = len(tables)
    data["column_count"] = sum(len(t["columns"]) for t in tables.values())
    data["relation_count"] = sum(len(t["relations"]) for t in tables.values())
    data["doc_tables_added"] = added
    data["tr_table_count"] = tr_tables
    data["tr_column_count"] = tr_columns
    data["doc_only_column_count"] = unmatched
    data["doc_relation_count"] = hinted
    return data


def index_segments(rows: list[dict]) -> dict[int, list[dict]]:
    """The workbook's index sheet, one row per segment, folded into one entry per index.

    Two things here change a generated query. The unique single-column index on LOGICALREF is the
    primary key a Logo database never declares, so without it every join the planner writes is
    against a column it believes could repeat. And the leading column of each index is the filter
    the vendor built the table to be searched by — the difference between a scan of a period's
    STLINE and a seek.

    Segments arrive in their own rows, ordered by `Segment No` under a repeated index name.
    """
    by_resource: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        name = str(r.get("Index Name") or "").strip()
        column = str(r.get("Segment Field") or "").strip().upper()
        if not name or not column:
            continue
        attrs = str(r.get("Attributes") or "").strip()
        entry = by_resource[_int(r["Resource ID"])].setdefault(
            name,
            {
                "name": name,
                "unique": attrs.lower().startswith("unique"),
                "nullable": "allow null" in attrs.lower(),
                "segments": [],
            },
        )
        entry["segments"].append((_int(r.get("Segment No")), column, str(r.get("Sense") or "").strip()))

    out: dict[int, list[dict]] = {}
    for rid, named in by_resource.items():
        built = []
        for entry in named.values():
            segments = sorted(entry.pop("segments"))
            entry["columns"] = [c for _, c, _ in segments]
            # Descending appears once in the whole dictionary. Recording it only where it occurs
            # keeps the common entry small without losing the one index that is not ascending.
            if descending := [c for _, c, sense in segments if sense.lower().startswith("desc")]:
                entry["descending"] = descending
            built.append(entry)
        out[rid] = built
    return out


def build(xls_path: Path) -> dict:
    import xlrd

    book = xlrd.open_workbook(str(xls_path))
    tables_raw = _sheet(book, "Tablolar")
    fields_raw = _sheet(book, "Alanlar")
    rels_raw = _sheet(book, "Relations")
    index_raw = _sheet(book, "Indexler")

    fields_by_resource: dict[int, list[dict]] = defaultdict(list)
    for f in fields_raw:
        fields_by_resource[_int(f["Resource ID"])].append(f)
    rels_by_resource: dict[int, list[dict]] = defaultdict(list)
    for r in rels_raw:
        rels_by_resource[_int(r["Resource ID"])].append(r)
    indexes_by_resource = index_segments(index_raw)

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
            name = str(f["Field Name"]).strip().upper()
            # One row in the workbook (SATIFILTER, offset 181, "Internal Usage") names no field.
            # Kept, it becomes a column called "" that every consumer has to special-case.
            if not name:
                continue
            desc, values = parse_expression(f.get("Expression"))
            col = {"type": str(f["Field Type"]).strip()}
            size = _int(f.get("Field Size"))
            if size:
                col["size"] = size
            if desc:
                col["description"] = desc
            if values:
                col["values"] = values
            columns[name] = col

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
            "indexes": indexes_by_resource.get(rid, []),
        }

    return {
        "source": xls_path.name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "backend/scripts/import_logo_ldds.py",
        "table_count": len(tables),
        "column_count": sum(len(t["columns"]) for t in tables.values()),
        "relation_count": sum(len(t["relations"]) for t in tables.values()),
        "index_count": sum(len(t["indexes"]) for t in tables.values()),
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

    # The Turkish sentences, when the structure document was supplied. The Doc Miner matches a
    # question against this text, and a question about "cari hesap" matches "Cari hesap kartları",
    # never "Current Account Cards".
    tr = {n: t for n, t in sorted(data["tables"].items())
          if t.get("description_tr") or any("description_tr" in c for c in t["columns"].values())}
    if tr:
        lines += [
            f"## Tablo ve kolon açıklamaları (Türkçe — `{data.get('structure_doc', 'yapı dökümanı')}`)",
            "",
            "Logo'nun Türkçe tablo yapısı dökümanından; İngilizce açıklamaların Türkçe karşılığı.",
            "",
        ]
        for name, table in tr.items():
            head = table.get("description_tr") or table.get("description") or name
            lines.append(f"### {name} — {head}")
            lines.append("")
            for col, meta in table["columns"].items():
                if text := meta.get("description_tr"):
                    lines.append(f"- `{col}` — {text}")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--doc"]
    doc_path = None
    if "--doc" in argv:
        idx = argv.index("--doc")
        if idx + 1 >= len(argv):
            print("--doc needs a path", file=sys.stderr)
            return 2
        doc_path = Path(argv[idx + 1]).expanduser()
        args = [a for a in args if a != argv[idx + 1]]
    if not args:
        print(__doc__)
        return 2
    xls = Path(args[0]).expanduser()
    if not xls.is_file():
        print(f"not found: {xls}", file=sys.stderr)
        return 1
    data = build(xls)
    if doc_path is not None:
        if not doc_path.is_file():
            print(f"not found: {doc_path}", file=sys.stderr)
            return 1
        data["structure_doc"] = doc_path.name
        merge_doc(data, parse_structure_doc(doc_text(doc_path)))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")
    OUT_GLOSSARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_GLOSSARY.write_text(glossary_markdown(data), encoding="utf-8")
    print(
        f"{OUT_JSON.relative_to(REPO)}: {data['table_count']} tablo, {data['column_count']} kolon, "
        f"{data['relation_count']} ilişki, {data['index_count']} indeks, "
        f"{data['coded_column_count']} kodlu kolon"
    )
    if data["key_collisions"]:
        print(f"  ad çakışması ({len(data['key_collisions'])}): {', '.join(data['key_collisions'][:5])}")
    if doc_path is not None:
        print(
            f"  {doc_path.name}: {data['tr_table_count']} tablo açıklaması, "
            f"{data['tr_column_count']} kolon açıklaması (Türkçe), "
            f"{len(data['doc_tables_added'])} yeni tablo, {data['doc_relation_count']} yeni ilişki"
        )
        if data["doc_tables_added"]:
            print(f"  yalnız dökümanda olan tablolar: {', '.join(data['doc_tables_added'])}")
    print(f"{OUT_GLOSSARY.relative_to(REPO)}: {len(data['document_codes'])} fiş türü, {len(data['currencies'])} döviz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
