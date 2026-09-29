"""Ekran kabulünün indirdiği dosyaları karşılaştırır: her ekranda Excel ↔ CSV satır/başlık/hücre (kabul.compare, bağımsız
çözümleyici), dosya adı, dosya yapısı; telefon genişliğinde yatay taşma. Girdi: ekran_testi.mjs'in JSON satırları (stdin).
Kullanım: node ekran_testi.mjs | python ekran_karsilastir.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kabul as KB  # noqa: E402

for line in sys.stdin:
    line = line.strip()
    if not line.startswith("{"):
        continue
    r = json.loads(line)
    ad = r["ad"]
    if "hata" in r:
        veri_yok = "VERİ YOK" in r["hata"]
        KB.check(f"{ad} ekran", None if veri_yok else False, r["hata"].split("\n")[0][:300])
        continue
    KB.check(f"{ad} ekran açıldı, Excel düğmesi var", bool(r["ciftler"]), f"/{r['yol']} ({r['sn']} sn)")
    if r.get("hatalar"):
        KB.check(f"{ad} sayfa hatası", False, "; ".join(r["hatalar"])[:300])
    for c in r["ciftler"]:
        tag = f"{ad} «{c['excel']}»"
        if "xlsx" not in c:
            KB.check(tag, None, c.get("durum", "indirilmedi"))
            continue
        xb = Path(c["xlsx"]["dosya"]).read_bytes()
        name = c["xlsx"]["onerilenAd"]
        so, sd = KB.structure_ok(xb)
        KB.check(f"{tag} Excel dosyası", name.endswith(".xlsx") and so, f"«{name}», {len(xb):,} bayt, {sd}")
        if not so:
            continue
        if "csv" not in c:
            KB.check(f"{tag} CSV eşi", None, "yanında CSV düğmesi bulunamadı; yalnız Excel sınandı")
            continue
        cname = c["csv"]["onerilenAd"]
        KB.check(f"{tag} dosya adı CSV ile aynı", re.sub(r"\.xlsx$", "", name) == re.sub(r"\.csv$", "", cname), f"«{cname}» ↔ «{name}»")
        try:
            rep = KB.compare(Path(c["csv"]["dosya"]).read_bytes(), xb)
        except Exception as e:  # noqa: BLE001
            KB.check(f"{tag} karşılaştırma", False, str(e)[:200])
            continue
        KB.check(f"{tag} satır/başlık birebir", rep["csvRows"] == rep["xlsxRows"], f"{rep['csvRows'] - 1:,} veri satırı")
        KB.check(f"{tag} hücreler CSV ile aynı", not rep["bad"],
                 "; ".join(rep["bad"]) if rep["bad"] else f"{rep['num']:,} sayı, {rep['date']:,} tarih, {rep['text']:,} metin")
    t = r.get("telefonTasma")
    b = r.get("telefonDugme") or {}
    KB.check(f"{ad} telefon (390 px) yatay taşma yok", t is not None and t <= 0 and (not b or b.get("sag", 0) <= 390),
             f"taşma {t} px, düğme sağ kenarı {b.get('sag')} px")

ok = sum(1 for x in KB.results if x["durum"] == "GEÇTİ")
bad = sum(1 for x in KB.results if x["durum"] == "KALDI")
warn = sum(1 for x in KB.results if x["durum"] == "UYARI")
print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
