"""Dijital baskı maliyet formu — TİMAŞ «TBK dijital» Excel'inin («Kitap Maliyet Formu», tek sayfa «TBK. dijital»,
59 satır) birebir hesabı. Saf fonksiyonlar, veritabanı yok. `form.compute` girdide `baski: "dijital"` görünce buraya gelir.

Ofset formundan farkı (Excel'den okundu, 2026-10-06, «AŞIKLARIN HALLERİ-TBK DİJİTAL-05102026.xlsx»):
- **İç baskı sayfa başına:** sayfa × (ebat × kâğıt tablosundaki sayfa fiyatı) × (1 + ek pay %) × adet. Kâğıt bu fiyatın
  içindedir; ayrı kâğıt satırı (Excel 7–12) hesaplanır ama toplama girmez. Renkli sayfa aynı kuralla, kendi kâğıdıyla.
- **Kapak** (Excel 28 «Kapak baskı + selofan + cilt»): adet × kapak birim fiyatı (BRİSTOL/KUŞE sütunu) × (1 + ek pay %).
- **Ek işlemler** (Excel 21–27) yalnız işaretlenince: ayraç atma, ayraç baskı, gofre, kulaklı kapak, kapak baskısı,
  selofan, lokal lak. Kapak tabakası = (adet + 600) ÷ 8 (Excel F10), eşikleri bu sayıdan.
- **Diğer giderler** elle: yan kâğıt, nakliye (adet başına), hediye, zayiat, reklam, diğer. **Telif** = fiyat × adet × oran.
- **Dolaylı gider** varsayılanı %40 (ofsette %90). **Satış fiyatı** = fiyat × (1 − yayınevi iskontosu); iskonto listesi
  dijital Excel'in kendi listesi (ofsetten farklı oranlar var: Mavi Kirpi %45, Timas Publishing %40).

Excel'de tablo `VLOOKUP(ebat; …)` yaklaşık eşleşmeyle ve 19X27 / 21,5X27,5 satırlarında bir satır kaymış aranıyor; burada
ebat birebir eşleşir. Fiyatı boş (0) hücrelerde Excel sessizce 0 ₺ hesaplar; burada elle birim fiyat istenir.
"""
from __future__ import annotations

from typing import Any, Optional


def _helpers():
    from semantic_bridge.pricing import form as F
    return F


def table_row(dt: dict, ebat: Optional[str]) -> Optional[dict]:
    F = _helpers()
    want = F._norm(ebat)
    return next((r for r in dt.get("tablo") or [] if F._norm(r["ebat"]) == want), None)


def page_price(dt: dict, ebat: Optional[str], kagit: Optional[str], adjust_pct: float) -> Optional[float]:
    """Ebat × kâğıt tablosundaki birim fiyat (matbaa fiyat ayarı % uygulanmış; Excel N3 = N38 × (1 + I1%)). Yoksa None."""
    F = _helpers()
    row = table_row(dt, ebat)
    if not row or not kagit:
        return None
    v = next((p for k, p in (row.get("fiyat") or {}).items() if F._norm(k) == F._norm(kagit)), None)
    if not v:
        return None
    return float(v) * (1 + (adjust_pct or 0) / 100.0)


def default_overhead(tariff: dict, yayinevi: Optional[str]) -> float:
    """Dijitalde dolaylı gider varsayılanı: yayınevinin oranı (Excel'lerde yayınevine göre değişiyor: Timaş İnanç/Tarih
    %70, Sufi %40), listede yoksa genel dijital oran. Kitap hesabında elle değiştirilebilir."""
    F = _helpers()
    dt = tariff.get("dijital") or {}
    by = dt.get("dolayliYayinevi") or {}
    v = next((float(x) for k, x in by.items() if F._norm(k) == F._norm(yayinevi)), None)
    return v if v is not None else float(dt.get("dolayli", 40))


def compute(inp: dict[str, Any], tariff: dict[str, Any]) -> dict[str, Any]:
    F = _helpers()
    f = F._f
    dt = tariff.get("dijital") or {}
    if not dt.get("tablo"):
        raise F.FormError("Fiyat listesinde dijital baskı tablosu yok.")
    dj = inp.get("dijital") or {}
    adet, sayfa = f(inp.get("adet")), f(inp.get("sayfa"))
    if not adet or adet <= 0:
        raise F.FormError("Baskı adedini girin.")
    if not sayfa or sayfa <= 0:
        raise F.FormError("Sayfa sayısını girin.")
    ebat = inp.get("ebat")
    ayar = f(inp.get("matbaaAyar"), 0.0) or 0.0
    pay = f(dj.get("pay"), float(dt.get("pay", 25)))
    k = 1 + (pay or 0) / 100.0
    lines: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not table_row(dt, ebat):
        warnings.append(f"«{ebat}» ebatı dijital fiyat tablosunda yok; birim fiyatları elle girin.")

    def line(key, group, name, excel, total, **kw):
        row = {"key": key, "group": group, "name": name, "excel": excel, "total": round(float(total or 0), 6),
               "perCopy": round(float(total or 0) / adet, 6)}
        row.update({a: b for a, b in kw.items() if b is not None})
        lines.append(row)
        return float(total or 0)

    def unit(kagit: Optional[str], manual: Any, what: str) -> tuple[float, str]:
        m = f(manual)
        if m is not None and m > 0:
            return m, "elle"
        p = page_price(dt, ebat, kagit, ayar)
        if p is None:
            raise F.FormError(f"{what}: «{ebat}» ebatında «{(kagit or '').strip()}» için fiyat listesinde fiyat yok. "
                              f"Birim fiyatı elle girin ya da Veri ve varsayımlar'da tabloya ekleyin.")
        return p, "tarife"

    # --- İç baskı (Excel 17–18): renkli sayfalar ve kalanı.
    renkli = f(dj.get("renkliSayfa"))
    if renkli and renkli >= sayfa:
        raise F.FormError("Renkli sayfa sayısı toplam sayfadan az olmalı.")
    j17 = 0.0
    if renkli:
        e17, src = unit(dj.get("renkliKagit"), dj.get("renkliBirim"), "Renkli sayfa")
        j17 = line("renkliBaski", "matbaa", "Renkli sayfa baskı", "J17", e17 * renkli * k * adet, unitPrice=round(e17, 6),
                   priceSource=src, material=(dj.get("renkliKagit") or "").strip() or None,
                   formula=f"{renkli:g} sayfa × {e17:,.4f} ₺ × (1 + %{pay:g}) × {adet:,.0f} adet")
    b18 = sayfa - (renkli or 0)
    e18, src = unit(dj.get("icKagit"), dj.get("icBirim"), "İç sayfa")
    j18 = line("icBaski", "matbaa", "İç sayfa baskı (kâğıt dahil)", "J18", e18 * b18 * k * adet, unitPrice=round(e18, 6),
               priceSource=src, material=(dj.get("icKagit") or "").strip() or None,
               formula=f"{b18:g} sayfa × {e18:,.4f} ₺ × (1 + %{pay:g}) × {adet:,.0f} adet")
    j19 = j17 + j18

    # --- Kapak (Excel 28) ve ek işlemler (21–27).
    e28, src = unit(dj.get("kapakKagit") or "BRİSTOL", dj.get("kapakBirim"), "Kapak")
    f28 = line("kapak", "matbaa", "Kapak baskı + selofan + cilt", "F28", adet * e28 * k, unitPrice=round(e28 * k, 6),
               priceSource=src, material=dj.get("kapakKagit") or "BRİSTOL",
               formula=f"{adet:,.0f} adet × {e28:,.4f} ₺ × (1 + %{pay:g})")
    kal = dt.get("kalemler") or {}

    def km(key: str, col: str = "m") -> float:
        """Ek işlem fiyatı (Excel G21–G27 sabitleri; matbaa fiyat ayarı bunlara uygulanmaz)."""
        return float((kal.get(key) or {}).get(col) or 0)

    kc = dt.get("kapak") or {}
    f10 = (adet + float((dt.get("fire") or {}).get("kapak", 600))) / float(kc.get("verim") or 8)
    ex = dj.get("ekler") or {}
    extra = 0.0
    if ex.get("ayracAtma"):
        g21 = km("ayracAtma") if adet <= 5000 else km("ayracAtma", "n")
        extra += line("ayracAtma", "matbaa", "Ayraç kitabın içine atma işçilik", "F21", (adet + 170) * g21,
                      formula=f"({adet:,.0f} + 170) × {g21:g} ₺")

    def per_color(key: str, colors: float, label: str, cell: str) -> float:
        g = km(key)
        v = colors * g if f10 <= 3000 else colors * g + (f10 - 3000) * (g / 1000.0)
        return line(key, "matbaa", label, cell, v, formula=f"{colors:g} renk × {g:g} ₺"
                    + (f" + 3.000 üstü {f10 - 3000:,.0f} tabaka" if f10 > 3000 else ""))

    if f(ex.get("ayracRenk")):
        extra += per_color("ayracBaski", f(ex["ayracRenk"]), "Ayraç baskı", "F22")
    if ex.get("gofre"):
        g23 = km("gofre")
        # Excel: tam 1.000 tabakada iki koşul da yanlış → 0 (aynen korunur).
        v = g23 if f10 * 2 < 1000 else ((adet / 1000.0) * km("gofre", "n") + g23 if f10 * 2 > 1000 else 0.0)
        extra += line("gofre", "matbaa", "Gofre", "F23", v)
    if ex.get("kulakli"):
        extra += line("kulakli", "matbaa", "Kulaklı kapak", "F24", adet / 1000.0 * km("kulakli"),
                      formula=f"{adet:,.0f} ÷ 1.000 × {km('kulakli'):g} ₺")
    if f(ex.get("kapakRenk")):
        extra += per_color("kapakBaski", f(ex["kapakRenk"]), "Kapak baskısı (ek)", "F25")
    if ex.get("selofan"):
        g26 = km("selofan")
        v = max(250.0, f10 * float(kc.get("en") or 70) * float(kc.get("boy") or 100) * g26 / 10000.0)
        extra += line("selofan", "matbaa", "Kapak selofan (ek)", "F26", v, formula=f"{f10:,.1f} tabaka × m² × {g26:g} ₺ (en az 250 ₺)")
    if ex.get("lokalLak"):
        g27 = km("lokalLak")
        extra += line("lokalLak", "matbaa", "Lokal lak", "F27", g27 * k, formula=f"{g27:,.0f} ₺ × (1 + %{pay:g})")

    # --- Diğer giderler (Excel J20–J28).
    dg = inp.get("diger") or {}
    other = 0.0
    for key, label, cell in (("yanKagit", "Yan kâğıdı", "J20"), ("hediye", "Hediye", "J22"), ("zayiat", "Zayiat", "J23"),
                             ("reklam", "Reklam", "J24"), ("diger", "Diğer", "J28")):
        v = f(dg.get(key))
        if v:
            other += line(key if key != "diger" else "digerGider", "diger", label, cell, v)
    nak = f(dg.get("nakliyeAdet"))
    if nak:
        other += line("nakliye", "diger", "Nakliye", "J21", nak * adet, formula=f"{nak:g} ₺ × {adet:,.0f} adet")

    fiyat = f(inp.get("fiyat")) or f(inp.get("simdikiFiyat")) or 0.0
    telif = f(inp.get("telif"), 0.0) or 0.0
    j27 = 0.0
    if telif and fiyat:
        j27 = line("telif", "telif", "Telif", "J27", fiyat * adet * telif / 100.0,
                   formula=f"{fiyat:,.2f} ₺ × {adet:,.0f} basılan × %{telif:g}")

    j29 = f28 + extra + other + j27
    j32 = j19 + j29
    dolayli = f(inp.get("dolayli"), default_overhead(tariff, inp.get("yayinevi")))
    dolayli = 0.0 if dolayli is None else dolayli
    j33 = j32 * dolayli / 100.0
    j34 = j32 + j33
    d33 = (f28 + extra + j17 + j18) / adet
    d34 = j27 / adet

    oz = f(inp.get("ozelIskonto"))
    if oz is not None:
        iskonto = oz
    else:
        pubs = {**(tariff.get("publishers") or {}), **(dt.get("publishers") or {})}
        iskonto = next((float(v) for kk, v in pubs.items() if F._norm(kk) == F._norm(inp.get("yayinevi"))), None)
        if iskonto is None:
            iskonto = 0.0
            warnings.append(f"«{inp.get('yayinevi')}» için iskonto listede yok; iskonto 0 sayıldı." if inp.get("yayinevi")
                            else "Yayınevi seçilmedi; iskonto 0 sayıldı.")
    j5 = fiyat * (1 - iskonto / 100.0)
    j38 = j34 / adet
    j40 = j5 - j38
    j41 = adet * j40
    j42 = j41 / j34 if j34 else None
    if not fiyat:
        warnings.append("Kapak fiyatı girilmedi: telif ve kâr hesaplanmadı.")

    summary = {
        "forma": round(sayfa / 16.0, 4), "kagitAdet": 0.0, "matbaaAdet": round(d33, 6), "telifAdet": round(d34, 6),
        "kitapMaliyeti": round(d33 + d34, 6), "kitapMaliyetiToplam": round((d33 + d34) * adet, 4),
        "matbaaToplam": round(j19, 4), "digerToplam": round(j29, 4), "toplam": round(j32, 4), "dolayliOran": dolayli,
        "dolayli": round(j33, 4), "genelToplam": round(j34, 4), "birimMaliyet": round(j38, 6), "iskonto": iskonto,
        "kapakFiyati": fiyat, "satisFiyati": round(j5, 6), "karAdet": round(j40, 6), "toplamKar": round(j41, 4),
        "karYuzde": None if j42 is None else round(j42, 6), "adet": adet, "sayfa": sayfa, "kapakPayi": 0.0,
        "sayfaBasi": round((d33 + d34) / sayfa, 6), "baski": "dijital", "ekPay": pay, "kapakTabaka": round(f10, 4),
    }
    return {"lines": lines, "summary": summary, "warnings": warnings, "paperSource": "dijital", "prices": [],
            "kur": tariff.get("kur"), "vade": None, "fire": {"ic": 0, "icPay": 0}, "baski": "dijital",
            "tabloTarihi": dt.get("guncelleme")}


def blank(tariff: dict) -> dict[str, Any]:
    dt = tariff.get("dijital") or {}
    return {"icKagit": "1/1- 60gr KİTAP KAĞIDI", "icBirim": None, "renkliSayfa": None,
            "renkliKagit": "4/4- 115gr KUŞE-KALİTELİ", "renkliBirim": None, "kapakKagit": "BRİSTOL", "kapakGr": 230,
            "kapakBirim": None, "pay": dt.get("pay", 25),
            "ekler": {"ayracAtma": False, "ayracRenk": None, "gofre": False, "kulakli": False, "kapakRenk": None,
                      "selofan": False, "lokalLak": False}}
