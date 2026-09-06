#!/usr/bin/env python3
"""MDL'e ilişki kolonları (join handle) ekler: modeller arası gezinme LLM'in elle JOIN yazmasını gerektirmez.
Örn. dbo_LG_411_01_INVOICE üzerinde `cari` kolonu → SELECT "cari"."DEFINITION_" FROM dbo_LG_411_01_INVOICE
Kaynak: WrenAI MDL referansı, "Relationship columns" bölümü. Idempotent."""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

P = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/nanobaseai/bi/wren-project/logo_timas")
WREN = Path("/data/nanobaseai/bi/wren-venv/bin/wren")

# ilişki adı → (kaynak model, kolon adı, hedef model, açıklama)
HANDLES = {
    "Dbo.lg_411_01_invoiceClientrefDbo.lg_411_clcardLogicalref":
        ("dbo_LG_411_01_INVOICE", "cari", "dbo_LG_411_CLCARD", "Faturanın cari kartı; \"cari\".\"DEFINITION_\" unvan, \"cari\".\"SPECODE2\" satış kanalı"),
    "Dbo.lg_411_01_stlineInvoicerefDbo.lg_411_01_invoiceLogicalref":
        ("dbo_LG_411_01_STLINE", "fatura", "dbo_LG_411_01_INVOICE", "Satırın bağlı olduğu fatura başlığı; \"fatura\".\"TRCODE\", \"fatura\".\"DATE_\""),
    "Dbo.lg_411_01_stlineStockrefDbo.lg_411_itemsLogicalref":
        ("dbo_LG_411_01_STLINE", "malzeme", "dbo_LG_411_ITEMS", "Satırın malzeme (kitap) kartı; \"malzeme\".\"NAME\" kitap adı, \"malzeme\".\"SPECODE\" yayınevi"),
    "Dbo.lg_411_01_stlineClientrefDbo.lg_411_clcardLogicalref":
        ("dbo_LG_411_01_STLINE", "cari", "dbo_LG_411_CLCARD", "Satırın cari kartı (fatura carisiyle aynıdır)"),
    "Dbo.lg_411_01_orflineOrdficherefDbo.lg_411_01_orficheLogicalref":
        ("dbo_LG_411_01_ORFLINE", "siparis_fisi", "dbo_LG_411_01_ORFICHE", "Sipariş satırının fişi; sayım daima fişten yapılır"),
    "Dbo.lg_411_01_orflineStockrefDbo.lg_411_itemsLogicalref":
        ("dbo_LG_411_01_ORFLINE", "malzeme", "dbo_LG_411_ITEMS", "Sipariş satırının malzeme kartı"),
    "Dbo.lg_411_01_orficheClientrefDbo.lg_411_clcardLogicalref":
        ("dbo_LG_411_01_ORFICHE", "cari", "dbo_LG_411_CLCARD", "Sipariş fişinin cari kartı"),
    "Dbo.lg_411_01_clflineClientrefDbo.lg_411_clcardLogicalref":
        ("dbo_LG_411_01_CLFLINE", "cari", "dbo_LG_411_CLCARD", "Cari hareketin cari kartı"),
}


def main() -> int:
    rels = {r for r in re.findall(r'^  - name: "([^"]+)"', (P / "relationships.yml").read_text(encoding="utf-8"), re.M)}
    added = []
    for rel, (model, col, target, desc) in HANDLES.items():
        if rel not in rels:
            print("  ! ilişki yok, atlandı:", rel[:50]); continue
        f = P / "models" / model / "metadata.yml"
        s = f.read_text(encoding="utf-8")
        if '  - name: "%s"' % col in s:
            continue
        s = s.rstrip("\n") + "\n  - name: %s\n    type: %s\n    relationship: %s\n    properties:\n      \"description\": %s\n" % (
            json.dumps(col), json.dumps(target), json.dumps(rel), json.dumps(desc, ensure_ascii=False))
        f.write_text(s, encoding="utf-8")
        added.append("%s.%s → %s" % (model, col, target))
    print("eklenen ilişki kolonu: %d" % len(added))
    for a in added:
        print("  +", a)
    for step in (["context", "validate"], ["context", "build"], ["memory", "index", "--mdl", "target/mdl.json"]):
        r = subprocess.run([str(WREN), *step], cwd=P, capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip().splitlines()
        print("== wren", " ".join(step), "→", (out[-1] if out else "")[:150])
    return 0


if __name__ == "__main__":
    sys.exit(main())
