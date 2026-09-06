#!/usr/bin/env python3
"""Logo/TİMAŞ projesinde WrenAI'nin kalan mekanizmalarını uygular:
  1. wren utils parse-types  → MDL tiplerini kanonik hale getir (rapor + düzeltme)
  2. enrich-context Step 4.5 → canlı DB'den enum/sentinel/zaman-grain keşfi, [enum] etiketleri
  3. wren memory dump        → doğrulanmış NL→SQL çiftlerini taşınabilir YAML'a
  4. validate / build / index
Çıktı: /data/nanobaseai/bi/logs/apply-all.json (denetim listesi)
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

P = Path("/data/nanobaseai/bi/wren-project/logo_timas")
VENV = Path("/data/nanobaseai/bi/wren-venv/bin")
WREN = VENV / "wren"
LOGS = Path("/data/nanobaseai/bi/logs")
audit: dict = {"parse_types": {}, "enum_probe": [], "dump": {}, "notes": []}


def wren(*a: str) -> str:
    r = subprocess.run([str(WREN), *a], cwd=P, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


# ---------------------------------------------------------------- 1. parse-types
def normalize_types() -> None:
    from wren.type_mapping import parse_types  # WrenAI'nin kendi tip haritası
    manifest = json.loads((P / "target" / "mdl.json").read_text(encoding="utf-8"))
    changed_total = 0
    for m in manifest.get("models", []):
        cols = [{"column": c["name"], "raw_type": c.get("type") or "VARCHAR"} for c in m.get("columns", []) if not c.get("isCalculated") and not c.get("relationship")]
        try:
            out = parse_types(cols, dialect="mssql")
        except Exception as e:  # noqa: BLE001
            audit["parse_types"]["error"] = str(e)[:200]
            return
        diffs = {c["column"]: (c["raw_type"], o.get("type")) for c, o in zip(cols, out) if o.get("type") and o["type"] != c["raw_type"]}
        if not diffs:
            continue
        f = P / "models" / m["name"] / "metadata.yml"
        s = f.read_text(encoding="utf-8")
        for col, (old, new) in diffs.items():
            pat = re.compile(r'(  - name: "%s"\n    type: )"%s"' % (re.escape(col), re.escape(old)))
            s2 = pat.sub(lambda mm: mm.group(1) + '"%s"' % new, s, count=1)
            if s2 != s:
                s = s2
                changed_total += 1
        f.write_text(s, encoding="utf-8")
        audit["parse_types"][m["name"]] = {k: list(v) for k, v in list(diffs.items())[:12]}
    audit["parse_types"]["_changed"] = changed_total
    print("parse-types: %d kolon tipi kanonikleştirildi" % changed_total)


# ---------------------------------------------------------------- 2. enum probe
PROBE = {
    "dbo_LG_411_01_INVOICE": ["TRCODE", "CANCELLED", "TRCURR", "GRPCODE", "SPECODE", "DOCTRACKINGNR", "PAYDEFREF", "STATUS", "SHIPINFOREF", "DEPARTMENT", "DIVISION", "BRANCH", "EINVOICE", "PROFILEID"],
    "dbo_LG_411_01_STLINE": ["LINETYPE", "TRCODE", "CANCELLED", "IOCODE", "UOMREF", "BILLED", "LINEEXP", "PRCURR", "VAT", "DISCPER"],
    "dbo_LG_411_CLCARD": ["SPECODE2", "SPECODE", "CARDTYPE", "ACCOUNTTYPE", "ISPERSCOMP", "BLOCKED", "CITY", "COUNTRY", "PAYMENTPROC", "SECTORMAINID"],
    "dbo_LG_411_ITEMS": ["SPECODE", "CARDTYPE", "ACTIVE", "CLASSTYPE", "UNITSETREF", "PRODUCERCODE", "SPECODE2", "STGRPCODE"],
    "dbo_LG_411_01_ORFICHE": ["TRCODE", "CANCELLED", "STATUS", "DEPARTMENT", "BRANCH"],
    "dbo_LG_411_01_ORFLINE": ["LINETYPE", "TRCODE", "CANCELLED", "CLOSED", "STATUS"],
    "dbo_LG_411_01_CLFLINE": ["TRCODE", "SIGN", "CANCELLED", "MODULENR", "PAIDINCASH"],
}
MAX_DISTINCT = 30


def probe_enums() -> dict[str, dict[str, list]]:
    import pyodbc
    c = json.loads(Path("/data/nanobaseai/bi/secrets/wren-logo-connection.json").read_text())
    cs = "DRIVER=FreeTDS;SERVER=%s,%s;DATABASE=%s;UID=%s;PWD=%s;TDS_Version=7.4;ClientCharset=UTF-8" % (c["host"], c["port"], c["database"], c["user"], c["password"])
    con = pyodbc.connect(cs, timeout=30); cur = con.cursor()
    found: dict[str, dict[str, list]] = {}
    for model, cols in PROBE.items():
        table = "dbo." + model.replace("dbo_", "", 1)
        for col in cols:
            try:
                cur.execute("SELECT TOP %d [%s], COUNT(*) n FROM %s GROUP BY [%s] ORDER BY n DESC" % (MAX_DISTINCT + 1, col, table, col))
                rows = [(r[0], int(r[1])) for r in cur.fetchall()]
            except Exception:
                continue
            if not rows or len(rows) > MAX_DISTINCT:
                continue  # yüksek kardinalite → enum değil
            vals = [(("" if v is None else str(v).strip()), n) for v, n in rows]
            found.setdefault(model, {})[col] = vals
            audit["enum_probe"].append({"model": model, "column": col, "distinct": len(vals), "top": vals[:6]})
    con.close()
    return found


TR_MEANING = {
    ("dbo_LG_411_01_INVOICE", "TRCODE"): {"1": "mal alım", "2": "perakende satış iadesi", "3": "toptan satış iadesi", "4": "alınan hizmet", "6": "alım iadesi", "7": "perakende satış", "8": "toptan satış", "9": "verilen hizmet"},
    ("dbo_LG_411_01_STLINE", "LINETYPE"): {"0": "malzeme satırı", "1": "promosyon", "2": "iskonto satırı", "3": "masraf", "4": "hizmet", "8": "sabit kıymet"},
    ("dbo_LG_411_01_STLINE", "TRCODE"): {"1": "mal alım", "2": "perakende satış iadesi", "3": "toptan satış iadesi", "7": "perakende satış", "8": "toptan satış"},
    ("dbo_LG_411_01_CLFLINE", "SIGN"): {"0": "borç", "1": "alacak"},
    ("dbo_LG_411_01_INVOICE", "CANCELLED"): {"0": "geçerli belge", "1": "iptal"},
    ("dbo_LG_411_01_STLINE", "CANCELLED"): {"0": "geçerli satır", "1": "iptal"},
    ("dbo_LG_411_01_INVOICE", "TRCURR"): {"0": "TL (yerel para)"},
}


def write_enum_tags(found: dict[str, dict[str, list]]) -> int:
    written = 0
    for model, cols in found.items():
        f = P / "models" / model / "metadata.yml"
        if not f.exists():
            continue
        s = f.read_text(encoding="utf-8")
        for col, vals in cols.items():
            meaning = TR_MEANING.get((model, col), {})
            parts = []
            for v, n in vals[:14]:
                label = meaning.get(v)
                shown = v if v != "" else "(boş)"
                parts.append("%s=%s" % (shown, label) if label else shown)
            tag = "[enum] " + ", ".join(parts) + (" · %d farklı değer" % len(vals))
            pat = re.compile(r'(  - name: "%s"\n    type: "[^"]*"\n)((?:    (?!- name).*\n)*)' % re.escape(col))
            m = pat.search(s)
            if not m or "[enum]" in m.group(2):
                continue
            block = m.group(2)
            dm = re.search(r'(      "description": ")([^"]*)(")', block)
            if dm:
                block = block[: dm.start(2)] + (dm.group(2) + " " + tag).replace('"', "'") + block[dm.end(2):]
            elif "    properties:" in block:
                block = block.replace("    properties:\n", '    properties:\n      "description": %s\n' % json.dumps(tag, ensure_ascii=False), 1)
            else:
                block = block + '    properties:\n      "description": %s\n' % json.dumps(tag, ensure_ascii=False)
            s = s[: m.start()] + m.group(1) + block + s[m.end():]
            written += 1
        f.write_text(s, encoding="utf-8")
    print("enum etiketi yazılan kolon: %d" % written)
    return written


# ---------------------------------------------------------------- 3. dump
def dump_pairs() -> None:
    out = P / "knowledge" / "pairs-export.yml"
    txt = wren("memory", "dump", "--output", str(out))
    audit["dump"]["cmd"] = txt[:300]
    if out.exists():
        audit["dump"]["bytes"] = out.stat().st_size
        audit["dump"]["pairs"] = out.read_text(encoding="utf-8").count("nl:")
    print("dump:", audit["dump"])


if __name__ == "__main__":
    normalize_types()
    found = probe_enums()
    write_enum_tags(found)
    print("== validate"); v = wren("context", "validate"); print("\n".join(v.splitlines()[-3:]))
    if "0 errors" not in v and "Valid" not in v:
        audit["notes"].append("validate FAILED: " + v[-300:])
    print("== build"); print(wren("context", "build").splitlines()[0])
    dump_pairs()
    print("== index"); print("\n".join(wren("memory", "index", "--mdl", "target/mdl.json").splitlines()[-2:]))
    (LOGS / "apply-all.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
    print("audit →", LOGS / "apply-all.json")
