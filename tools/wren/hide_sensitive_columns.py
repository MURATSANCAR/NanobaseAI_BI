#!/usr/bin/env python3
"""WrenAI'nin `is_hidden` mekanizmasını uygular (MDL referansı: kolon motor sembol tablosundan çıkarılır,
hiçbir istemci sorgulayamaz; cte_rewriter `isHidden` olanı atlar).

Yalnız gerçek kişisel veri ve teknik sır kolonları gizlenir. Coğrafi analiz kolonları (CITY, DISTRICT, TOWN,
POSTCODE) ve iş anlamı olan bayraklar AÇIK kalır — "kolon budama yok" kuralı korunur, bu bir gizlilik önlemidir.
Idempotent. Çalıştırdıktan sonra: wren context validate → build → memory index.
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

P = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/nanobaseai/bi/wren-project/logo_timas")
WREN = Path("/data/nanobaseai/bi/wren-venv/bin/wren")

# Gizlenecekler — ad kalıbı bazında, kategori etiketiyle (denetlenebilirlik için)
HIDE = [
    ("kredi kartı",      re.compile(r"^CREDITCARD(NO|NUM)$")),
    ("banka hesabı/IBAN", re.compile(r"^(BANKACCOUNTS|BANKIBANS|BANKCORRPACC)[0-9]$|^BANKACCREF$")),
    ("kimlik/vergi no",  re.compile(r"^(PASSPORTNO|TAXNR)$")),
    ("telefon/faks",     re.compile(r"^(TELNRS[0-9]|TELEXTNUMS[0-9]|CELLPHONE|FAXNR)$")),
    ("e-posta",          re.compile(r"^EMAILADDR[0-9]?$")),
    ("açık adres",       re.compile(r"^ADDR[0-9]$")),
    ("teknik sır/anahtar", re.compile(r"^(CYPHCODE|GUID|RECHASH)$")),
]
# AÇIK kalacaklar (coğrafi/iş anlamı var): CITY, DISTRICT, TOWN, POSTCODE, TAXOFFICE, INSTEADOFDESP


def category(name: str) -> str | None:
    for label, pat in HIDE:
        if pat.match(name):
            return label
    return None


def main() -> int:
    hidden: dict[str, list[tuple[str, str]]] = {}
    # Tek geçiş: re.sub geri çağırması — döngü içinde dizgeyi değiştirip eski konumları kullanmak
    # blokları bozar (ilk denemede bu oldu), bu yüzden tüm eşleşmeler tek sub içinde işlenir.
    block_re = re.compile(r'(  - name: "([A-Z][A-Z0-9_]*)"\n    type: "[^"]*"\n)((?:    (?!- name).*\n)*)')

    for f in sorted((P / "models").glob("*/metadata.yml")):
        model = f.parent.name

        def repl(m: re.Match) -> str:
            head, col, block = m.group(1), m.group(2), m.group(3)
            cat = category(col)
            if not cat or "is_hidden: true" in block:
                return m.group(0)
            hidden.setdefault(model, []).append((col, cat))
            tag = "[gizli:%s] " % cat
            if '"description": "' in block:
                block = block.replace('"description": "', '"description": "' + tag, 1)
            elif "    properties:\n" in block:
                block = block.replace("    properties:\n", '    properties:\n      "description": "%sGizlilik nedeniyle sorgulanamaz (is_hidden)."\n' % tag, 1)
            else:
                block = block + '    properties:\n      "description": "%sGizlilik nedeniyle sorgulanamaz (is_hidden)."\n' % tag
            return head + "    is_hidden: true\n" + block

        f.write_text(block_re.sub(repl, f.read_text(encoding="utf-8")), encoding="utf-8")

    total = sum(len(v) for v in hidden.values())
    print("gizlenen kolon: %d" % total)
    for model, cols in hidden.items():
        print("  %s → %d: %s" % (model, len(cols), ", ".join(c for c, _ in cols[:8]) + (" …" if len(cols) > 8 else "")))
    for step in (["context", "validate"], ["context", "build"], ["memory", "index", "--mdl", "target/mdl.json"]):
        r = subprocess.run([str(WREN), *step], cwd=P, capture_output=True, text=True)
        lines = [l for l in (r.stdout + r.stderr).strip().splitlines() if l.strip()]
        print("==", " ".join(step), "→", (lines[-1] if lines else "")[:130])
    man = json.loads((P / "target" / "mdl.json").read_text(encoding="utf-8"))
    n_hidden = sum(1 for mo in man["models"] for c in mo["columns"] if c.get("isHidden"))
    n_total = sum(len(mo["columns"]) for mo in man["models"])
    print("manifest: %d gizli / %d kolon" % (n_hidden, n_total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
