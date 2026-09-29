"""Kitap Maliyet Formu — TİMAŞ basım Excel'inin («BASIM EXCELLER», 222 satırlık «Kitap Maliyet Formu» şablonu)
birebir hesabı. Saf fonksiyonlar, veritabanı yok.

Excel'le paralel çalışır: aynı girdi ve aynı tarifeyle aynı sonucu verir (kabul: `scripts/acceptance/M9-maliyet-formu`,
37 gerçek sayfa). Satırların Excel'deki hücresi her kalemde yazılıdır (`excel`), ekran «i» penceresinde gösterir.

Excel'in hesap kuralları (şablondan okundu, 2026-09-29):
- **Kâğıt tabakası** = (adet + fire) × sayfa ÷ verim (iç), (adet + fire) ÷ verim (kapak ve ek parçalar). Fire adet
  cinsinden sabit bir paydır (iç 800, kapak 1000 …); oranı küçük baskıda büyür.
- **kg** = en × boy × gramaj ÷ 10.000 × tabaka ÷ 1.000. **₺/kg** = tarife fiyatı (€ ya da $ / ton) × (1 + vade farkı) × kur
  ÷ 1.000. Tabaka ya da adetle satılan malzemede (mukavva, cilt bezi, sticker) ₺/adet = fiyat × (1 + vade) × kur.
- **İç baskı** = ROUNDUP(sayfa ÷ forma sayfası) × renk kalıp; kalıp başına tarife (tek renk / renkli), 3.000 adedin
  üstünde her 1.000 adet için ek bedel. Kapak baskı, şömiz, ayraç, yan kâğıt aynı tarifeden.
- **Selofan** m² × birim (en az 250 ₺); **lak, gofre, yaldız** ilk 1.000 tabaka sabit + fazlası 1.000'de bir.
- **Cilt** adet başına (form başına işçilik × (forma + 2), en az 10 forma); toplam en az 1.000 ₺.
- **Telif** = kapak fiyatı × basılan adet × oran (Excel KDV düşmez). **Kapak/çizim ücreti** kaç baskıya bölünüyorsa o pay.
- **Dolaylı gider** = (matbaa + diğer giderler) × oran. **Birim maliyet** = genel toplam ÷ adet.
- **Satış fiyatı** = kapak fiyatı × (1 − yayınevi vadeli iskontosu); **kâr %** = toplam kâr ÷ genel toplam (maliyete göre).

Excel'in set/değerlendirme testi satırları (18–22) set adedi (B5) girilmeyen formlarda sıfırdır; 37 formun hiçbirinde
kullanılmadığı için hesaba alınmadı.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Optional

TARIFF_FILE = Path(__file__).with_name("form_tariff.json")

#: Excel'in cilt seçenekleri (L208:L218).
BINDINGS = (
    "CİLT YOK", "AMERİKAN CİLT", "AMERİKAN CİLT- (KULAKLI KAPAK)", "FLEKSİ KAPAK CİLT", "İPLİK+AMERİKAN CİLT",
    "İPLİK+AMERİKAN CİLT - (KULAKLI KAPAK)", "SERT KAPAK CİLT", "TEL DİKİŞ CİLT", "BOARD BOOK SIVAMA-PENCERESİZ",
    "BOARD BOOK SIVAMA-PENCERELİ", "BOARD BOOK SIVAMA-BRİSTOL+MUKAVVA+BRİSTOL+PENCERELİ",
)
LAMINATES = ("SELOFAN", "DİSPERSİYON LAK")
VARNISHES = ("Lokal Lak-50x70", "Kabartma Lak-50x70", "Simli Lak-50x70", "DİSPERSİYON LAK")

#: Ek kâğıt parçaları: anahtar → (Excel satırı, ad, varsayılan en, boy, gramaj, verim, fire, hesap türü).
#: «kg» satırları kg × ₺/kg, «tabaka» satırları tabaka × birim fiyat (Excel J14–J16).
EXTRAS = {
    "yanKagit": (11, "Yan kâğıt (forza)", 64, 90, 140, 4, 800, "kg"),
    "somiz": (12, "Şömiz kâğıdı", 70, 100, 170, 6, 800, "kg"),
    "ayrac": (13, "Ayraç / afiş kâğıdı", 64, 90, 90, 2, 1000, "kg"),
    "mukavva": (14, "Mukavva (sert kapak)", 70, 100, None, None, 700, "tabaka"),
    "ciltBezi": (15, "Cilt bezi", 68, 100, None, 8, 200, "tabaka"),
    "digerKagit": (16, "Diğer tabaka malzeme", 70, 100, None, 6, 1000, "tabaka"),
}


class FormError(ValueError):
    pass


def default_tariff() -> dict[str, Any]:
    return json.loads(TARIFF_FILE.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ yardımcılar

def _f(v: Any, default: Optional[float] = None) -> Optional[float]:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return float(v)
    try:
        x = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        raise FormError(f"Sayı bekleniyordu: {v!r}") from None
    if math.isnan(x) or math.isinf(x):
        raise FormError("Sayı geçersiz.")
    return x


def _roundup(x: float) -> float:
    """Excel ROUNDUP(x, 0): sıfırdan uzağa yukarı."""
    return float(math.ceil(x - 1e-12)) if x >= 0 else -float(math.ceil(-x - 1e-12))


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().upper().replace("İ", "I").replace(" ", "")


class _Prices:
    """Tarife + matbaa fiyat ayarı (Excel I1: kalıp, lak, cilt işçiliği ve ebat tablosu % ayarlanır; kâğıt değil)."""

    def __init__(self, tariff: dict, adjust_pct: float):
        self.t = tariff
        self.k = 1 + (adjust_pct or 0) / 100.0

    def m(self, key: str) -> float:
        """Birinci fiyat (Excel M sütunu, ayarlı)."""
        row = self.t["prices"].get(key)
        if row is None:
            raise FormError(f"Tarifede «{key}» yok.")
        return float(row.get("m") or 0) * self.k

    def n(self, key: str) -> float:
        """İkinci fiyat (Excel N sütunu, ayarlı): genelde 1.000 adet/tabaka başına ek bedel."""
        row = self.t["prices"].get(key) or {}
        return float(row.get("n") or 0) * self.k

    def p_raw(self, key: str) -> float:
        """Ayarsız ikinci fiyat (Excel P sütunu). Kapak baskısının 3.000 üstü ek bedeli ayarsız P43'ü kullanır."""
        row = self.t["prices"].get(key) or {}
        return float(row.get("n") or 0)

    def plate(self, colors: float) -> tuple[float, float]:
        key = "tekRenkKalip" if colors == 1 else "renkliKalip"
        return self.m(key), self.n(key)

    def trim(self, ebat: str) -> Optional[dict]:
        want = _norm(ebat)
        for r in self.t.get("trims") or []:
            if _norm(r["ebat"]) == want:
                return r
        return None


def paper_row(tariff: dict, name: Optional[str]) -> Optional[dict]:
    want = _norm(name)
    for r in tariff.get("papers") or []:
        if _norm(r["name"]) == want:
            return r
    return None


#: Tarife kâğıt adı → Logo kâğıt kartı adında aranan sözcük (Logo `15001…` kartları «57X88 3.HAMUR 60 GR KAĞIT» gibi).
LOGO_KEYWORDS = (
    ("KİTAP KAĞIDI", ("3.HAMUR",)),
    ("1.HAMUR", ("1.HAMUR",)),
    ("ÇİFT", ("BRİSTOL",)),
    ("BRİSTOL", ("BRİSTOL",)),
    ("KUŞE", ("KUŞE",)),
    ("IVORY", ("IVORY",)),
    ("ENSO", ("ENSO", "VİVİD", "VIVID")),
    ("ŞAMUA", ("ŞAMUA",)),
)


def logo_paper_price(snap_paper: Optional[dict], name: str, gsm: Optional[float]) -> Optional[dict]:
    """Tarife kâğıdının Logo'daki son 6 ay alış fiyatı (₺/kg, kg ağırlıklı). Önce aynı gramaj, yoksa aynı cins."""
    items = (snap_paper or {}).get("items") or []
    up = (name or "").upper()
    words = next((w for k, w in LOGO_KEYWORDS if k in up), None)
    if not words or not items:
        return None
    same = [i for i in items if any(w in (i.get("name") or "").upper() for w in words) and i.get("kg")]
    if not same:
        return None
    exact = [i for i in same if gsm and i.get("gsm") and abs(float(i["gsm"]) - float(gsm)) < 0.5]
    use = exact or same
    kg = sum(float(i["kg"]) for i in use)
    amount = sum(float(i["amount"]) for i in use)
    if kg <= 0:
        return None
    last = max((i.get("last") or "" for i in use), default="") or None
    return {"perKg": round(amount / kg, 4), "kg": round(kg, 2), "cards": len(use), "sameGsm": bool(exact),
            "last": last, "names": [i["name"] for i in sorted(use, key=lambda x: -float(x["kg"]))[:4]]}


def paper_price(tariff: dict, name: Optional[str], gsm: Optional[float], source: str,
                snap_paper: Optional[dict]) -> dict[str, Any]:
    """Bir malzemenin birim fiyatı: ₺/kg (ton fiyatlı kâğıt) ya da ₺/adet (tabaka/adet fiyatlı malzeme)."""
    row = paper_row(tariff, name)
    if row is None:
        raise FormError(f"«{name}» tarifede yok; tarifedeki kâğıtlardan birini seçin.")
    vade = float(tariff["vade"]["oran"]) * float(tariff["vade"]["ay"])
    cur = row.get("cur") or "EUR"
    kur = float(tariff["kur"][cur])
    base = float(row["base"]) * (1 + vade / 100.0)
    per_ton = row.get("unit", "ton") == "ton"
    tl = kur * base / 1000.0 if per_ton else kur * base
    out = {"name": row["name"], "unit": "kg" if per_ton else "adet", "tarife": round(tl, 6), "price": tl,
           "source": "tarife", "tarifeText": f"{row['base']:g} {cur}/{'ton' if per_ton else 'adet'} × (1 + %{vade:g} vade) × "
                                                 f"{kur:g} ₺" + (" ÷ 1.000" if per_ton else "")}
    if per_ton:
        lp = logo_paper_price(snap_paper, row["name"], gsm)
        out["logo"] = lp
        if source == "logo" and lp:
            out["price"] = lp["perKg"]
            out["source"] = "logo"
    return out


# ------------------------------------------------------------------ hesap

def compute(inputs: dict[str, Any], tariff: dict[str, Any], *, paper_source: str = "tarife",
            snap_paper: Optional[dict] = None) -> dict[str, Any]:
    """Formun bütün hesabı. `paper_source`: «tarife» (Excel'le birebir) ya da «logo» (kâğıdın Logo alış fiyatı)."""
    inp = inputs or {}
    t = tariff
    kur_in = inp.get("kur") or {}
    if any(_f(kur_in.get(c)) for c in ("USD", "EUR")):
        t = {**tariff, "kur": {c: (_f(kur_in.get(c)) or float(tariff["kur"][c])) for c in ("USD", "EUR")}}
    adet = _f(inp.get("adet"))
    sayfa = _f(inp.get("sayfa"))
    if not adet or adet <= 0:
        raise FormError("Baskı adedini girin.")
    if not sayfa or sayfa <= 0:
        raise FormError("Sayfa sayısını girin.")
    pr = _Prices(t, _f(inp.get("matbaaAyar"), 0.0) or 0.0)
    vade = float(t["vade"]["oran"]) * float(t["vade"]["ay"])
    lines: list[dict[str, Any]] = []
    warnings: list[str] = []
    prices_used: dict[str, dict] = {}

    def price_of(name: str, gsm: Optional[float]) -> dict:
        p = paper_price(t, name, gsm, paper_source, snap_paper)
        prices_used[f"{p['name']}|{gsm or ''}"] = {k: v for k, v in p.items() if k != "price"} | {"used": p["price"], "gsm": gsm}
        return p

    def line(key, group, name, excel, total, **kw):
        row = {"key": key, "group": group, "name": name, "excel": excel, "total": round(float(total or 0), 6),
               "perCopy": round(float(total or 0) / adet, 6)}
        row.update({k: v for k, v in kw.items() if v is not None})
        lines.append(row)
        return float(total or 0)

    # --- İç sayfalar: renkli grup (Excel satır 8/23) ve tek renk grup (7/24).
    ic = inp.get("ic") or {}
    rk = inp.get("renkli") or {}
    renkli_sayfa = _f(rk.get("sayfa"))
    d23 = renkli_sayfa if renkli_sayfa else None
    d24 = sayfa - d23 if d23 else sayfa
    e7 = _f(ic.get("verim"), 32.0)
    e8 = _f(rk.get("verim"), 32.0)
    if not e7:
        raise FormError("İç kâğıt verimini (bir tabakadan çıkan sayfa) girin.")
    e24 = e7 / 2.0
    e23 = e8 / 2.0 if e8 else 16.0
    forma = sayfa / e24

    def sheet_row(key, group, label, excel_row, part, qty_sheets, kind="kg"):
        name = part.get("kagit")
        if not name:
            return 0.0
        en, boy, gr = _f(part.get("en")), _f(part.get("boy")), _f(part.get("gr"))
        p = price_of(name, gr)
        if kind == "tabaka" or p["unit"] == "adet":
            total = qty_sheets * p["price"]
            return line(key, group, label, f"J{excel_row}", total, material=p["name"], sheets=round(qty_sheets, 4),
                        unitPrice=round(p["price"], 6), unit="₺/adet", priceSource=p["source"],
                        formula=f"{qty_sheets:,.2f} tabaka × {p['price']:,.4f} ₺")
        if not (en and boy and gr):
            raise FormError(f"{label}: tabaka eni, boyu ve gramajı gerekli.")
        kg = en * boy * gr / 10000.0 * qty_sheets / 1000.0
        total = kg * p["price"]
        return line(key, group, label, f"J{excel_row}", total, material=p["name"], sheets=round(qty_sheets, 4),
                    kg=round(kg, 4), unitPrice=round(p["price"], 6), unit="₺/kg", priceSource=p["source"],
                    formula=f"{en:g}×{boy:g} cm, {gr:g} gr × {qty_sheets:,.2f} tabaka = {kg:,.2f} kg × {p['price']:,.4f} ₺/kg")

    fdef = t.get("fire") or {}
    fire_ic = _f(ic.get("fire"), float(fdef.get("ic", 800)))
    j7 = sheet_row("icKagit", "kagit", "İç kâğıt", 7, ic, (adet + fire_ic) * (d24 / e7)) if ic.get("kagit") else 0.0
    j8 = 0.0
    if d23 and rk.get("kagit"):
        j8 = sheet_row("renkliKagit", "kagit", "Renkli sayfa kâğıdı", 8, rk, (adet + _f(rk.get("fire"), float(fdef.get("renkli", 800)))) * (d23 / e8))

    kp = inp.get("kapak") or {}
    e10 = _f(kp.get("verim"), 8.0)
    f10 = (adet + _f(kp.get("fire"), float(fdef.get("kapak", 1000)))) / e10 if kp.get("kagit") and e10 else 0.0
    j10 = sheet_row("kapakKagit", "kagit", "Kapak kartonu", 10, kp, f10) if f10 else 0.0

    ek = inp.get("ekler") or {}
    f_extra: dict[str, float] = {}
    j_extra: dict[str, float] = {}
    trim = pr.trim(inp.get("ebat") or "")
    for key, (row, label, *_rest, kind) in EXTRAS.items():
        part = ek.get(key) or {}
        if not part.get("kagit"):
            f_extra[key] = 0.0
            continue
        verim = _f(part.get("verim"))
        if key == "mukavva":
            verim = _f(part.get("verim")) or (float(trim["mukavvaVerim"]) if trim and trim.get("mukavvaVerim") else None)
        if not verim:
            raise FormError(f"{label}: bir tabakadan kaç parça çıktığını (verim) girin.")
        f = (adet + (_f(part.get("fire"), float(fdef.get(key, _rest[4]))))) / verim
        f_extra[key] = f
        j_extra[key] = sheet_row(key, "kagit", label, row, part, f, kind)

    # Kenar boyama (Excel satır 17): (adet + 150) × birim × (1 + vade).
    kb = _f(ek.get("kenarBoyama"))
    j17 = 0.0
    if kb:
        h17 = kb * (1 + vade / 100.0)
        j17 = line("kenarBoyama", "matbaa", "Kenar boyama", "J17", (adet + 150) * h17,
                   formula=f"({adet:,.0f} + 150) × {kb:g} × (1 + %{vade:g})")

    # --- Baskı kalıpları (Excel 23–24).
    def plate_cost(colors: float) -> tuple[float, float]:
        g, extra = pr.plate(colors)
        h = g if adet <= 3000 else g + (adet - 3000) / 1000.0 * extra
        return g, h

    j24 = j23 = 0.0
    renk_ic = _f(ic.get("renk"), 1.0) or 0.0
    if d24 and renk_ic:
        g24, h24 = plate_cost(renk_ic)
        n24 = _roundup(d24 / e24) * renk_ic
        j24 = line("icBaski", "matbaa", "İç sayfa baskı", "J24", n24 * h24, plates=n24, unitPrice=round(h24, 4),
                   formula=f"⌈{d24:g} sayfa ÷ {e24:g}⌉ × {renk_ic:g} renk = {n24:g} kalıp × {h24:,.2f} ₺"
                           + (" (3.000 üstü her 1.000 adet ek bedelle)" if adet > 3000 else ""))
    if d23:
        renk23 = _f(rk.get("renk"), 4.0) or 0.0
        g23, h23 = plate_cost(renk23)
        n23 = _roundup(d23 / e23) * renk23
        j23 = line("renkliBaski", "matbaa", "Renkli sayfa baskı", "J23", n23 * h23, plates=n23, unitPrice=round(h23, 4),
                   formula=f"⌈{d23:g} sayfa ÷ {e23:g}⌉ × {renk23:g} renk = {n23:g} kalıp × {h23:,.2f} ₺")

    j25 = j7 + j8 + j10 + sum(j_extra.values()) + j17 + j23 + j24

    # --- Diğer giderler (Excel 26–36).
    def plate_run(colors: Optional[float], sheets: float, extra_per_k: Optional[float] = None) -> float:
        """Ek parça baskısı: renk × kalıp, 3.000 tabakanın üstü ek bedel."""
        if not colors:
            return 0.0
        g, _ = pr.plate(colors)
        if sheets <= 3000:
            return colors * g
        if extra_per_k is None:
            return colors * g + (sheets - 3000) * (g / 1000.0)
        return colors * g + (sheets - 3000) / 1000.0 * extra_per_k

    f26 = 0.0
    isel = ek.get("icSelofan") or {}
    if isel.get("var") and ic.get("kagit"):
        tur = isel.get("tur") or "SELOFAN"
        g26 = pr.m(tur)
        f7 = (adet + fire_ic) * (d24 / e7)
        if tur == "SELOFAN":
            v = max(250.0, _f(ic.get("en")) * _f(ic.get("boy")) * f7 * g26 / 10000.0)
        else:
            v = g26 + (f7 - 1000) / 1000.0 * pr.n(tur) if f7 > 1000 else g26
        f26 = line("icSelofan", "matbaa", "İç sayfa selofan", "F26", v / 2.0, formula="İç tabaka alanı × selofan birim fiyatı ÷ 2")

    klise = kp.get("klise") or {}
    klise_adet = _f(klise.get("adet"), 0.0) or 0.0
    klise_ebat = klise.get("ebat") or "35x50"
    cl = (t.get("cliche") or {}).get(klise_ebat)
    j26 = 0.0
    if klise_adet:
        if not cl:
            raise FormError(f"Klişe ebatı «{klise_ebat}» tarifede yok.")
        j26 = line("klise", "matbaa", "Klişe", "J26", float(cl["price"]) * klise_adet,
                   formula=f"{klise_adet:g} klişe × {float(cl['price']):,.0f} ₺ ({klise_ebat})")

    f27 = 0.0
    kesim = kp.get("ozelKesim")
    if kesim and klise_adet and cl:
        src_f = {"icKagit": (adet + fire_ic) * (d24 / e7), "kapakKagit": f10, **f_extra}.get(kesim, 0.0)
        g27 = pr.n("ozelKesimTbk")
        v = max(g27, src_f * float(cl["pieces"]) / klise_adet * pr.m("ozelKesimTbk")) * klise_adet
        f27 = line("ozelKesim", "matbaa", "Özel kesim (TBK)", "F27", v, formula="Kesilen tabaka × parça ÷ klişe × birim; en az tarife tutarı")

    # İşçilikler (Excel J27–J31).
    def gren_cost() -> float:
        return pr.m("gren") if f10 * 2 < 1000 else adet / 1000.0 * pr.n("gren") + pr.m("gren")

    gren_n = int(_f(kp.get("gren"), 0.0) or 0)
    j_isc = 0.0
    if gren_n:
        j_isc += line("gren", "matbaa", "Gren uygulama", "J27", gren_cost() * gren_n)
    if (ek.get("somiz") or {}).get("iscilik"):
        j_isc += line("somizIscilik", "matbaa", "Şömiz işçilik", "J28", pr.m("somizIscilik") * (adet + 100),
                      formula=f"({adet:,.0f} + 100) × {pr.m('somizIscilik'):g} ₺")
    if ek.get("vakum"):
        j_isc += line("vakum", "matbaa", "Tekli vakumlu paket", "J29", pr.m("tekliVakum") * (adet + 100),
                      formula=f"({adet:,.0f} + 100) × {pr.m('tekliVakum'):g} ₺")
    if (ek.get("ayrac") or {}).get("iscilik"):
        j_isc += line("ayracIscilik", "matbaa", "Ayraç / afiş işçilik", "J31", pr.m("ayracIscilik") * (adet + 100),
                      formula=f"({adet:,.0f} + 100) × {pr.m('ayracIscilik'):g} ₺")

    def per_k(key: str, sheets_x: float) -> float:
        return pr.m(key) if sheets_x <= 1000 else (sheets_x - 1000) / 1000.0 * pr.n(key) + pr.m(key)

    f28 = line("gofre", "matbaa", "Gofre", "F28", per_k("gofre", f10 * 4)) if kp.get("gofre") else 0.0
    f29 = line("yaldiz", "matbaa", "Yaldız", "F29", per_k("yaldiz", f10 * 4)) if kp.get("yaldiz") else 0.0
    f30 = f31 = f32 = 0.0
    ayr = ek.get("ayrac") or {}
    if ayr.get("renk"):
        f30 = line("ayracBaski", "matbaa", "Ayraç / afiş baskı", "F30", plate_run(_f(ayr["renk"]), f_extra.get("ayrac", 0.0)))
    som = ek.get("somiz") or {}
    if som.get("renk"):
        f31 = line("somizBaski", "matbaa", "Şömiz baskı", "F31", plate_run(_f(som["renk"]), f_extra.get("somiz", 0.0)))
    yan = ek.get("yanKagit") or {}
    if yan.get("renk") and f_extra.get("yanKagit"):
        f32 = line("yanBaski", "matbaa", "Yan kâğıt baskı", "F32", plate_run(_f(yan["renk"]), f_extra["yanKagit"], 35.0))

    f33 = 0.0
    renk_kapak = _f(kp.get("renk"))
    if renk_kapak:
        g33, _ = pr.plate(renk_kapak)
        v = renk_kapak * g33 if f10 <= 3000 else renk_kapak * g33 + (f10 - 3000) / 1000.0 * pr.p_raw("renkliKalip")
        bolen = _f(kp.get("bolen"))
        f33 = line("kapakBaski", "matbaa", "Kapak baskı", "F33", v / bolen if bolen else v,
                   formula=f"{renk_kapak:g} renk × {g33:,.0f} ₺ kalıp" + (" (3.000 tabaka üstü ek bedelle)" if f10 > 3000 else "")
                           + (f" ÷ {bolen:g} (paylaşılan form)" if bolen else ""))

    f34 = 0.0
    sel = kp.get("selofan") or {}
    if sel.get("var"):
        tur = sel.get("tur") or "SELOFAN"
        g34 = pr.m(tur)
        if tur == "SELOFAN":
            v = max(250.0, (_f(kp.get("en"), 0.0) or 0.0) * (_f(kp.get("boy"), 0.0) or 0.0) * f10 * g34 / 10000.0)
            fx = f"{_f(kp.get('en')):g}×{_f(kp.get('boy')):g} cm × {f10:,.1f} tabaka = m² × {g34:g} ₺ (en az 250 ₺)"
        else:
            v = g34 + (f10 - 1000) / 1000.0 * pr.n(tur) if f10 > 1000 else g34
            fx = f"İlk 1.000 tabaka {g34:,.0f} ₺, fazlası 1.000'de {pr.n(tur):,.0f} ₺"
        bolen = _f(sel.get("bolen"))
        if bolen:
            v /= bolen
        if sel.get("ciftYuz"):
            v *= 2
            fx += " × 2 (iki yüz)"
        f34 = line("selofan", "matbaa", "Kapak selofan" if tur == "SELOFAN" else "Kapak dispersiyon lak", "F34", v, formula=fx)

    f35 = 0.0
    lak = kp.get("lak") or {}
    if lak.get("var"):
        tur = lak.get("tur") or "Lokal Lak-50x70"
        v = per_k(tur, f10 * 2)
        f35 = line("lak", "matbaa", tur.replace("-50x70", " (50x70)"), "F35", v,
                   formula=f"{f10 * 2:,.0f} tabaka (50x70): ilk 1.000 {pr.m(tur):,.0f} ₺, fazlası 1.000'de {pr.n(tur):,.0f} ₺")

    # Cilt (Excel satır 36 + L208:M218).
    cilt = inp.get("cilt") or {}
    tur = cilt.get("tur") or "AMERİKAN CİLT"
    e36 = _roundup(sayfa / e24)
    manual = _f(cilt.get("birim"))
    g36 = manual if manual is not None else binding_unit(pr, tur, e36, sayfa, inp.get("ebat"), warnings)
    f36 = 0.0
    if g36:
        f36 = 1000.0 if g36 * (adet + 100) < 1000 else g36 * adet
        f36 = line("cilt", "matbaa", f"Cilt — {tur.title()}", "F36", f36, unitPrice=round(g36, 4),
                   formula=f"{g36:,.4f} ₺/adet × {adet:,.0f} (en az 1.000 ₺)"
                           + ("" if manual is not None else f"; {e36:g} forma"))

    dg = inp.get("diger") or {}
    kapak_ucret = _f(dg.get("kapakUcreti"), 0.0) or 0.0
    kapak_bolen = _f(dg.get("kapakBolen"), 3.0) or 1.0
    j33 = 0.0
    if kapak_ucret:
        j33 = line("kapakUcreti", "diger", dg.get("kapakEtiket") or "Kapak / çizim ücreti", "J33", kapak_ucret / kapak_bolen,
                   formula=f"{kapak_ucret:,.0f} ₺ ÷ {kapak_bolen:g} baskı")
    j32 = line("nakliye", "diger", "Nakliye", "J32", _f(dg.get("nakliye"), 0.0)) if _f(dg.get("nakliye")) else 0.0
    j34 = line("mizanpaj", "diger", "İç mizanpaj", "J34", _f(dg.get("mizanpaj"), 0.0)) if _f(dg.get("mizanpaj")) else 0.0
    j36 = line("digerGider", "diger", "Diğer", "J36", _f(dg.get("diger"), 0.0)) if _f(dg.get("diger")) else 0.0

    fiyat = _f(inp.get("fiyat")) or _f(inp.get("simdikiFiyat")) or 0.0
    telif = _f(inp.get("telif"), 0.0) or 0.0
    j35 = 0.0
    if telif and fiyat:
        j35 = line("telif", "telif", "Telif", "J35", fiyat * adet * telif / 100.0,
                   formula=f"{fiyat:,.2f} ₺ kapak fiyatı × {adet:,.0f} basılan × %{telif:g}")

    j37 = f26 + f27 + f28 + f29 + f30 + f31 + f32 + f33 + f34 + f35 + f36 + j26 + j_isc + j32 + j33 + j34 + j35 + j36
    j40 = j25 + j37
    dolayli = _f(inp.get("dolayli"), 0.0) or 0.0
    j41 = j40 * dolayli / 100.0
    j42 = j40 + j41

    d40 = (j7 + j8 + j10 + sum(v for k, v in j_extra.items())) / adet
    d41 = (f36 + f35 + f34 + f33 + f28 + f29 + f30 + f26 + j24 + j23 + f32 + f31 + j26 + j_isc + j32 + f27 + j17) / adet
    d42 = j35 / adet

    oz = _f(inp.get("ozelIskonto"))
    pubs = t.get("publishers") or {}
    if oz is not None:
        iskonto = oz
    else:
        iskonto = next((float(v) for k, v in pubs.items() if _norm(k) == _norm(inp.get("yayinevi"))), None)
        if iskonto is None:
            iskonto = 0.0
            if inp.get("yayinevi"):
                warnings.append(f"«{inp.get('yayinevi')}» için vadeli iskonto tarifede yok; iskonto 0 sayıldı.")
            else:
                warnings.append("Yayınevi seçilmedi; vadeli iskonto 0 sayıldı.")
    j5 = fiyat * (1 - iskonto / 100.0)
    j46 = j42 / adet
    j48 = j5 - j46
    j49 = adet * j48
    j50 = j49 / j42 if j42 else None
    if not fiyat:
        warnings.append("Kapak fiyatı girilmedi: telif ve kâr hesaplanmadı.")
    fire_share = fire_ic / adet if adet else None
    if fire_share and fire_share > 0.25:
        warnings.append(f"İç kâğıtta fire payı basılan adedin %{fire_share * 100:.0f}'i ({fire_ic:,.0f} adet): küçük baskıda "
                        f"kâğıt maliyetini belirgin artırır.")

    summary = {
        "forma": round(forma, 4), "kagitAdet": round(d40, 6), "matbaaAdet": round(d41, 6), "telifAdet": round(d42, 6),
        "kitapMaliyeti": round(d40 + d41 + d42, 6), "kitapMaliyetiToplam": round((d40 + d41 + d42) * adet, 4),
        "matbaaToplam": round(j25, 4), "digerToplam": round(j37, 4), "toplam": round(j40, 4), "dolayliOran": dolayli,
        "dolayli": round(j41, 4), "genelToplam": round(j42, 4), "birimMaliyet": round(j46, 6), "iskonto": iskonto,
        "kapakFiyati": fiyat, "satisFiyati": round(j5, 6), "karAdet": round(j48, 6), "toplamKar": round(j49, 4),
        "karYuzde": None if j50 is None else round(j50, 6), "adet": adet, "sayfa": sayfa,
        "kapakPayi": round(j33 / adet, 6), "sayfaBasi": round((d40 + d41 + d42) / sayfa, 6),
    }
    return {"lines": lines, "summary": summary, "warnings": warnings, "paperSource": paper_source,
            "prices": list(prices_used.values()), "kur": t["kur"], "vade": vade,
            "fire": {"ic": fire_ic, "icPay": round(fire_ic / adet, 4)}}


def binding_unit(pr: _Prices, tur: str, e36: float, sayfa: float, ebat: Optional[str], warnings: list[str]) -> float:
    """Excel L208:M218 — adet başına cilt bedeli."""
    key = _norm(tur)
    amer = pr.m("amerikanCiltForma")
    iplik = pr.m("iplikDikis")
    if key == _norm("CİLT YOK"):
        return 0.0
    if key == _norm("AMERİKAN CİLT"):
        return 10 * amer if e36 < 10 else (e36 + 2) * amer
    if key == _norm("AMERİKAN CİLT- (KULAKLI KAPAK)"):
        return (10 * amer if e36 < 10 else (e36 + 2) * amer) * 1.5
    if key == _norm("İPLİK+AMERİKAN CİLT"):
        return 10 * (amer + iplik) if e36 < 10 else (e36 + 2) * (amer + iplik)
    if key == _norm("İPLİK+AMERİKAN CİLT - (KULAKLI KAPAK)"):
        return (10 * (amer + iplik) if e36 < 10 else (e36 + 2) * (amer + iplik)) * 1.5
    if key == _norm("TEL DİKİŞ CİLT"):
        tel = pr.m("telDikisForma")
        return 4 * tel if e36 < 3 else (e36 + 2) * tel
    if key in (_norm("SERT KAPAK CİLT"), _norm("FLEKSİ KAPAK CİLT")):
        tr = pr.trim(ebat or "")
        if not tr:
            raise FormError(f"«{ebat}» ebatı tarifenin ebat tablosunda yok: {tur.title()} için taslama ve kapak takma bedeli "
                            f"bulunamadı. Cilt birim fiyatını elle girin.")
        base = float(tr["taslama"]) * pr.k + float(tr["kapakTakma"]) * pr.k + (pr.m("sertKapakIplikDikis") + pr.m("sertKapakFormaHarman")) * (e36 + 2)
        return base * 0.9 if key == _norm("FLEKSİ KAPAK CİLT") else base
    for label, pkey in (("BOARD BOOK SIVAMA-PENCERESİZ", "boardPenceresiz"), ("BOARD BOOK SIVAMA-PENCERELİ", "boardPencereli"),
                        ("BOARD BOOK SIVAMA-BRİSTOL+MUKAVVA+BRİSTOL+PENCERELİ", "boardBristolMukavva")):
        if key == _norm(label):
            return sayfa * pr.m(pkey) + pr.n(pkey)
    raise FormError(f"Cilt türü tanınmadı: {tur}")


# ------------------------------------------------------------------ fiyat analizine aktarım

def to_analysis(inputs: dict, tariff: dict, *, paper_source: str = "tarife", snap_paper: Optional[dict] = None) -> dict:
    """Formu M9 fiyat analizinin girdilerine çevirir: baskı bedeli c(Q) = a + b/Q iki adette hesaplanıp ayrılır
    (fire, kalıp ve en az bedeller adetten bağımsız kısımda). Telif Excel'deki gibi basılan adet üzerinden, KDV dahil
    kapak fiyatı tabanında; dolaylı gider «genel gider payı» olur (analizde yalnız baskı ve kâğıda eklenir)."""
    base = compute(inputs, tariff, paper_source=paper_source, snap_paper=snap_paper)
    q = float(base["summary"]["adet"])
    two = copy.deepcopy(inputs)
    two["adet"] = q * 2
    other = compute(two, tariff, paper_source=paper_source, snap_paper=snap_paper)

    def split(key_sum: str) -> tuple[float, float]:
        c1, c2 = base["summary"][key_sum], other["summary"][key_sum]
        a = 2 * c2 - c1
        b = (c1 - a) * q
        return a, b

    ka, kb = split("kagitAdet")
    ma, mb = split("matbaaAdet")
    if ka < 0 or ma < 0:  # adetle düşmeyen bir yapı: adet başına bedel olduğu gibi
        ka, kb, ma, mb = base["summary"]["kagitAdet"], 0.0, base["summary"]["matbaaAdet"], 0.0
    kapak = next((ln for ln in base["lines"] if ln["key"] == "kapakUcreti"), None)
    extra = sum(ln["total"] for ln in base["lines"] if ln["key"] in ("nakliye", "mizanpaj", "digerGider"))
    return {
        "printService": round(ma, 4), "paperPerCopy": round(ka, 4), "printSetup": round(mb + kb, 2),
        "overheadRate": (base["summary"]["dolayliOran"] or 0) / 100.0,
        "royaltyRate": (float(inputs.get("telif") or 0)) / 100.0, "royaltyBase": "kapak", "royaltyOn": "baski",
        "chosenQty": int(q), "price": base["summary"]["kapakFiyati"] or None,
        "fixed": {"grafik": round(kapak["total"], 2) if kapak else 0.0, "diger": round(extra, 2)},
        "note": "Maliyet formundan: baskı bedeli iki adette hesaplanıp adet başı + baskı başı diye ayrıldı.",
    }


# ------------------------------------------------------------------ yeni form ve kitaptan doldurma

def _pick_paper(gsm: Optional[float]) -> str:
    g = gsm or 60
    if g >= 120:
        return "1.HAMUR-120-140-150-170-200"
    if g >= 90:
        return "1.HAMUR-70-80-90-100-110"
    return "KİTAP KAĞIDI-60-70-80" if g in (70, 80) else "KİTAP KAĞIDI-52-55-65"


def _pick_binding(name: Optional[str]) -> Optional[str]:
    n = _norm(name)
    if not n:
        return None
    for key, val in (("IPLIK", "İPLİK+AMERİKAN CİLT"), ("SERT", "SERT KAPAK CİLT"), ("FLEX", "FLEKSİ KAPAK CİLT"),
                     ("FLEKS", "FLEKSİ KAPAK CİLT"), ("TEL", "TEL DİKİŞ CİLT"), ("AMER", "AMERİKAN CİLT")):
        if key in n:
            return val
    return None


def blank_inputs(tariff: dict, *, kur: Optional[dict] = None) -> dict[str, Any]:
    """Yeni kitap için başlangıç formu: basım Excel'lerinde en sık görülen seçimler (13,5x21, 3. hamur 60 gr, 57x88
    tabaka, tek renk iç, 4 renk bristol kapak, selofan + lokal lak, Amerikan cilt)."""
    fire = tariff.get("fire") or {}
    return {
        "yayinevi": None, "kitap": "", "yazar": "", "sayfa": None, "adet": 3000, "ebat": "13,5x21",
        "fiyat": None, "ozelIskonto": None, "matbaaAyar": None,
        "kur": {c: (kur or {}).get(c) for c in ("USD", "EUR")} if kur else None,
        "ic": {"kagit": "KİTAP KAĞIDI-52-55-65", "en": 57, "boy": 88, "gr": 60, "verim": 32, "renk": 1, "fire": fire.get("ic", 800)},
        "renkli": {"sayfa": None, "kagit": "KİTAP KAĞIDI-60-70-80", "en": 57, "boy": 88, "gr": 60, "verim": 32, "renk": 4,
                   "fire": fire.get("renkli", 800)},
        "kapak": {"kagit": "BRİSTOL", "en": 70, "boy": 100, "gr": 230, "verim": 8, "fire": fire.get("kapak", 1000), "renk": 4,
                  "selofan": {"var": True, "tur": "SELOFAN", "ciftYuz": False}, "lak": {"var": True, "tur": "Lokal Lak-50x70"},
                  "yaldiz": False, "gofre": False, "gren": 0, "klise": {"adet": None, "ebat": "35x50"}},
        "ekler": {k: {"kagit": None, "en": v[2], "boy": v[3], "gr": v[4], "verim": v[5], "fire": fire.get(k, v[6])}
                  for k, v in EXTRAS.items()} | {"kenarBoyama": None, "vakum": False, "icSelofan": {"var": False, "tur": "SELOFAN"}},
        "cilt": {"tur": "AMERİKAN CİLT", "birim": None},
        "diger": {"kapakUcreti": None, "kapakBolen": tariff.get("kapakBolen", 3), "kapakEtiket": "Kapak", "nakliye": None,
                  "mizanpaj": None, "diger": None},
        "telif": None, "dolayli": tariff.get("dolayli", 90),
    }


def from_book(detail: dict, tariff: dict, *, kur: Optional[dict] = None) -> dict[str, Any]:
    """Kitaptan doldurulmuş form: CRM kitap kartı (sayfa, ebat, kapak fiyatı, yayınevi, telif) ve son CRM üretim kaydı
    (adet, iç kâğıt gramajı, renk, cilt). Her alanın nereden geldiği `origin`de."""
    b = detail.get("book") or {}
    last = (detail.get("crmPrints") or [None])[-1] or {}
    inp = blank_inputs(tariff, kur=kur)
    origin: dict[str, str] = {}
    inp["kitap"] = b.get("name") or b.get("code") or ""
    inp["yazar"] = b.get("author") or ""
    if b.get("pages") or last.get("pages"):
        inp["sayfa"] = b.get("pages") or last.get("pages")
        origin["sayfa"] = "CRM kitap kartı" if b.get("pages") else "Son CRM üretim kaydı"
    if b.get("trim"):
        inp["ebat"] = str(b["trim"]).replace(".", ",").replace(" ", "").lower()
        origin["ebat"] = "CRM kitap kartı"
        tr = _Prices(tariff, 0).trim(inp["ebat"])
        if tr and tr.get("icEn") and tr.get("icBoy") and tr.get("icVerim"):
            inp["ic"].update(en=tr["icEn"], boy=tr["icBoy"], verim=tr["icVerim"])
            origin["ic"] = "Tarifedeki ebat tablosu (iç tabaka ve verim)"
    if b.get("price"):
        inp["fiyat"] = b["price"]
        origin["fiyat"] = "CRM kitap kartı (KDV dahil kapak fiyatı)"
    pub = next((k for k in (tariff.get("publishers") or {}) if _norm(k) == _norm(b.get("publisher"))), None)
    if pub:
        inp["yayinevi"] = pub
        origin["yayinevi"] = "CRM kitap kartındaki yayınevi"
    roy = b.get("royalty") or {}
    if roy.get("rate") is not None and roy.get("on") != "tek":
        inp["telif"] = round(float(roy["rate"]) * 100, 4)
        origin["telif"] = f"CRM yürürlükteki sözleşme ({roy.get('kindLabel') or ''} {roy.get('basisLabel') or ''})".strip()
    if last.get("qty"):
        inp["adet"] = last["qty"]
        origin["adet"] = f"Son CRM üretim kaydı ({last.get('no') or '?'}. baskı)"
    if last.get("gsm"):
        inp["ic"].update(gr=last["gsm"], kagit=_pick_paper(last["gsm"]))
        origin["icGr"] = "Son CRM üretim kaydı (iç sayfa gramajı)"
    if last.get("colors"):
        inp["ic"]["renk"] = last["colors"]
        origin["icRenk"] = "Son CRM üretim kaydı (iç sayfa renk sayısı)"
    bind = _pick_binding(last.get("binding"))
    if bind:
        inp["cilt"]["tur"] = bind
        origin["cilt"] = f"Son CRM üretim kaydı ({last.get('binding')})"
    return {"inputs": inp, "origin": origin}
