"""M52 Tedarik ve baskı yönetimi — portföy ve tedarikçi düzeyi.

M12 (Üretim yönetimi) tek kitabın tek baskısıdır: kart, takvim, matbaa ataması, teklif, gecikme. M52 kart açmaz,
matbaa atamaz, teklif girmez; M12'nin kartlarını **M12 modülünün kendi fonksiyonundan** okur (`production.Service.cards`,
HTTP değil) ve bütün baskıları toplar:

- **Baskı yükü** — açık kartlar (depoya girmemiş, baskıdan çıkmamış, iptal/eski olmayan) ay × matbaa: iş sayısı, adet,
  forma (CRM genel forma sayısı × adet). Ay = kartın M12 planındaki baskı ayı. Eşik: matbaanın portalda girilen aylık
  kapasitesi; girilmemişse geçmiş 12 ayın en yüksek aylık yükü **yalnız referanstır**, «kapasite» denmez.
- **Kağıt ihtiyacı** — açık kartların CRM kağıt alanları (parça başına net / brüt kg, kağıt cinsi, ebat), baskı ayı ×
  kağıt cinsi. Ölçü ayardan (`SUPPLY_PAPER_MEASURE`, varsayılan brüt = fire dahil).
- **Tedarikçi borç ve ödeme** — Logo 320 carileri: bakiye (alacak − borç, yıl başından), ödeme planı satırları FIFO
  yaklaşımıyla (Logo'da kapama yok): vadesi geçmiş kovalar, önümüzdeki 30/60/90 gün. Katalog «satici-borcu-*-fifo».
  Her çıktıda «FIFO yaklaşımı» notu vardır; kesin borç gibi sunulmaz.
- **Faturası görünmeyen baskı** — depoya girmiş ama M12 kuralıyla (satır özel kodu = stok kodu, kart penceresi) baskı
  faturası bağlanmamış kart; ve hiçbir karta bağlanmayan baskı faturası satırı. Bekleme süresi veriden (depo girişi →
  fatura gün farkının 3. çeyreği) ölçülür; yeterli örnek yoksa ayar.
- **Birim baskı maliyeti eğilimi** — M12'nin Logo'dan okuduğu adet başı baskı bedeli, ay × kırılım (cilt, sayfa bandı,
  baskı tipi, matbaa).
- **Plan girdisi** — Baskı Öneri raporunun (M11) Risk/Acil ve Kritik kitapları ile M10'un onaylı ilk baskı kararları
  arasında henüz üretim kartı açılmamış olanlar: aya/matbaaya dağıtılmamış gelecek yük.

Öneriler (K2) kural hesabıdır; Zeki AI yalnız gerekçe ve yazı metnini yazar. Karar portal kaydıdır; CRM'e, Logo'ya,
matbaaya yazılmaz ve gönderilmez.
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from semantic_bridge import supply_sources as src
from semantic_bridge import supply_store as store
from semantic_bridge.production_plan import add_months, parse_day

log = logging.getLogger("semantic.supply")
TZ = ZoneInfo("Europe/Istanbul")
TTL = 300

#: Yük sayılan M12 aşamaları: baskıdan henüz çıkmamış süren işler.
LOAD_STAGES = ("hazirlik", "matbaa-secildi", "matbaada")
#: Kağıt ihtiyacı sayılan aşamalar (baskı dosyası matbaadaysa kağıt çoğunlukla alınmıştır; yine gösterilir).
PAPER_STAGES = ("hazirlik", "matbaa-secildi", "matbaada")
NO_PRINTER = "Matbaa belirlenmedi"
OVERDUE = "gecikmis"      # planı geçmiş ama baskıdan çıkmamış
UNDATED = "tarihsiz"      # planında baskı ayı yok
FIFO_NOTE = ("Logo'da ödeme kapama kullanılmıyor: açık tutar FIFO yaklaşımıyla hesaplanır (bakiye en yeni vadeli "
             "satırlardan geriye dağıtılır). Sonuç yaklaşıktır, kesin borç değildir.")
REFERENCE_NOTE = ("Kapasite tanımlı değil: karşılaştırma matbaanın son 12 ayda baskıdan çıkan en yüksek aylık yüküyle "
                  "yapılır; bu kapasite değil, referanstır.")
MIN_SAMPLES = 20
AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def today() -> date:
    return datetime.now(TZ).date()


def mkey(d: Optional[date]) -> Optional[str]:
    return f"{d.year:04d}-{d.month:02d}" if d else None


def month_label(key: str) -> str:
    if key == OVERDUE:
        return "Planı geçmiş"
    if key == UNDATED:
        return "Tarihsiz"
    try:
        y, m = key.split("-")
        return f"{AY[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return key


def months_ahead(start: date, n: int) -> list[str]:
    first = date(start.year, start.month, 1)
    return [mkey(add_months(first, i)) for i in range(max(0, n))]


def months_back(end: date, n: int) -> list[str]:
    """`end`'in ayından önceki n tam ay, eskiden yeniye."""
    first = date(end.year, end.month, 1)
    return [mkey(add_months(first, -i)) for i in range(n, 0, -1)]


def _num(v: Any) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0.0
    return n if n == n else 0.0


def _day(v: Any) -> Optional[date]:
    return parse_day(v)


_TR = str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")


def fold(s: Optional[str]) -> str:
    return " ".join((s or "").translate(_TR).lower().split())


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Ayarlar ekran/ortamdan (`admin.conf`), yoksa varsayılan. Ölçülmemiş varsayımlar buradadır (kabul listesinde
    «ölçülecek»)."""
    def num(key: str, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(str(conf(key, str(default)) or default).replace(",", "."))))
        except ValueError:
            return default

    measure = (conf("SUPPLY_PAPER_MEASURE", "brut") or "brut").strip().lower()
    buyer = (conf("SUPPLY_PAPER_BUYER", "karisik") or "karisik").strip().lower()
    bands = []
    for x in (conf("SUPPLY_PAGE_BANDS", "96,160,256,400") or "").split(","):
        try:
            bands.append(int(x.strip()))
        except ValueError:
            continue
    return {
        "printerSpecodes": src.specodes(conf("SUPPLY_PRINTER_SPECODES", "MATBAALAR") or "MATBAALAR"),
        "paperSpecodes": src.specodes(conf("SUPPLY_PAPER_SPECODES", "KAĞITÇILAR") or "KAĞITÇILAR"),
        "supplierPrefix": (conf("SUPPLY_SUPPLIER_PREFIX", "320") or "320").strip(),
        "loadMonths": int(num("SUPPLY_LOAD_MONTHS", 6, 1, 24)),
        "paperMonths": int(num("SUPPLY_PAPER_MONTHS", 3, 1, 12)),
        "paperMeasure": measure if measure in ("brut", "net") else "brut",
        "paperLeadDays": int(num("SUPPLY_PAPER_LEAD_DAYS", 30, 0, 180)),
        "paperBuyer": buyer if buyer in ("timas", "matbaa", "karisik") else "karisik",
        "overloadRatio": num("SUPPLY_OVERLOAD_RATIO", 1.0, 0.5, 3.0),
        "unbilledGraceDays": int(num("SUPPLY_UNBILLED_GRACE_DAYS", 30, 0, 365)),
        "matchQtyTolerance": num("SUPPLY_MATCH_QTY_TOL", 0.15, 0.0, 1.0),
        "matchDays": int(num("SUPPLY_MATCH_DAYS", 60, 1, 365)),
        "matchSuggestProb": num("SUPPLY_MATCH_SUGGEST_PROB", 0.70, 0.0, 1.0),
        "matchSuggestMargin": num("SUPPLY_MATCH_SUGGEST_MARGIN", 0.30, 0.0, 1.0),
        "mapMinShare": num("SUPPLY_MAP_MIN_SHARE", 0.6, 0.3, 1.0),
        "mapMinJobs": int(num("SUPPLY_MAP_MIN_JOBS", 3, 1, 100)),
        "trendMonths": int(num("SUPPLY_TREND_MONTHS", 24, 6, 60)),
        "pageBands": sorted(set(b for b in bands if b > 0)) or [96, 160, 256, 400],
        "agingAsOf": (conf("SUPPLY_AGING_ASOF", "bugun") or "bugun").strip().lower(),
    }


# ============================================================ baskı yükü


def plan_month(card: dict[str, Any]) -> Optional[str]:
    return mkey(_day((card.get("plan") or {}).get("baski")))


def actual_month(card: dict[str, Any]) -> Optional[str]:
    """Baskıdan çıkış ayı (Logo'daki ilk gerçek giriş; yoksa depo girişi)."""
    act = card.get("actual") or {}
    d = _day((act.get("baski") or {}).get("day")) or _day((act.get("depo") or {}).get("day"))
    return mkey(d)


def forma_load(card: dict[str, Any], tech: dict[str, dict[str, Any]]) -> Optional[float]:
    """Forma-baskı yükü = genel forma sayısı × adet (ikisi de varsa)."""
    t = tech.get(card.get("id") or "") or {}
    f, q = t.get("forma"), card.get("qty")
    return round(float(f) * float(q), 2) if f and q else None


def history_load(cards: Iterable[dict[str, Any]], tech: dict[str, dict[str, Any]], now: date,
                 months: int = 12) -> dict[str, dict[str, dict[str, float]]]:
    """Matbaa → ay → {jobs, adet, forma}: son `months` tam ayda baskıdan çıkan kartlar (iptal hariç)."""
    window = set(months_back(now, months))
    out: dict[str, dict[str, dict[str, float]]] = {}
    for c in cards:
        if c.get("stage") == "iptal":
            continue
        m = actual_month(c)
        if m not in window:
            continue
        p = c.get("printer") or NO_PRINTER
        cell = out.setdefault(p, {}).setdefault(m, {"jobs": 0, "adet": 0.0, "forma": 0.0})
        cell["jobs"] += 1
        cell["adet"] += _num(c.get("qty"))
        cell["forma"] += forma_load(c, tech) or 0.0
    return out


def last_year_same_month(cards: Iterable[dict[str, Any]], months: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    """Ay → matbaa → {jobs, adet}: geçen yılın aynı ayında baskıdan çıkan kartlar (karşılaştırma sütunu)."""
    want: dict[str, str] = {}
    for m in months:
        try:
            y, mm = m.split("-")
            want[f"{int(y) - 1:04d}-{mm}"] = m
        except ValueError:
            continue
    out: dict[str, dict[str, dict[str, float]]] = {}
    for c in cards:
        if c.get("stage") == "iptal":
            continue
        am = actual_month(c)
        if am not in want:
            continue
        cell = out.setdefault(want[am], {}).setdefault(c.get("printer") or NO_PRINTER, {"jobs": 0, "adet": 0.0})
        cell["jobs"] += 1
        cell["adet"] += _num(c.get("qty"))
    return out


def reference(history: dict[str, dict[str, dict[str, float]]]) -> dict[str, dict[str, Any]]:
    """Matbaa → son 12 ayın en yüksek aylık yükü (adet, iş, forma) ve ayı. Kapasite değildir."""
    out: dict[str, dict[str, Any]] = {}
    for p, months in history.items():
        if not months:
            continue
        top = max(months.items(), key=lambda kv: kv[1]["adet"])
        out[p] = {"adet": round(top[1]["adet"], 2), "jobs": max(v["jobs"] for v in months.values()),
                  "forma": round(max(v["forma"] for v in months.values()), 2), "ay": top[0], "aylar": len(months)}
    return out


def load_bucket(card: dict[str, Any], now: date) -> str:
    m = plan_month(card)
    if not m:
        return UNDATED
    return OVERDUE if m < mkey(now) else m


def card_brief(c: dict[str, Any], tech: dict[str, dict[str, Any]], with_cost: bool = False) -> dict[str, Any]:
    t = tech.get(c.get("id") or "") or {}
    out = {"id": c.get("id"), "kitap": c.get("bookTitle") or c.get("name"), "stokKodu": c.get("stockCode"),
           "baskiNo": c.get("printNo"), "ilkBaski": c.get("firstPrint"), "urunTipi": c.get("kind"), "matbaa": c.get("printer"),
           "adet": c.get("qty"), "forma": t.get("forma"), "formaYuku": forma_load(c, tech), "sayfa": t.get("sayfa"),
           "oncelik": c.get("priority"), "bekleme": c.get("waiting"), "asama": c.get("stage"), "asamaAdi": c.get("stageLabel"),
           "planBaski": (c.get("plan") or {}).get("baski"), "planDosya": (c.get("plan") or {}).get("dosya"),
           "planDepo": (c.get("plan") or {}).get("depo"), "yayin": c.get("publication"),
           "gecikme": max((d.get("days") or 0 for d in c.get("delays") or []), default=0),
           "onay": c.get("approval")}
    if with_cost:
        out.update(birimFiyat=c.get("unitPrice"), faturaTutari=c.get("price"))
    return out


def cell_state(adet: float, forma: float, cap: Optional[dict[str, Any]], ref: Optional[dict[str, Any]],
               ratio: float) -> tuple[str, Optional[float]]:
    """(durum, oran). Kapasite varsa: adet ya da forma kapasiteyi aşarsa «asim». Yoksa referansın `ratio` katını
    aşarsa «referans-ustu»; referans da yoksa «olculemedi». Boş hücre «bos»."""
    if adet <= 0 and forma <= 0:
        return "bos", None
    if cap and (cap.get("kapasiteAdet") or cap.get("kapasiteForma")):
        rates = []
        if cap.get("kapasiteAdet"):
            rates.append(adet / float(cap["kapasiteAdet"]))
        if cap.get("kapasiteForma") and forma:
            rates.append(forma / float(cap["kapasiteForma"]))
        r = max(rates) if rates else None
        if r is None:
            return "olculemedi", None
        return ("asim" if r > 1 else "normal"), round(r, 4)
    if ref and ref.get("adet"):
        r = adet / (float(ref["adet"]) * ratio)
        return ("referans-ustu" if r > 1 else "normal"), round(adet / float(ref["adet"]), 4)
    return "olculemedi", None


def load_table(cards: list[dict[str, Any]], tech: dict[str, dict[str, Any]], capacity: list[dict[str, Any]],
               now: date, months: int, ratio: float = 1.0, with_cost: bool = False) -> dict[str, Any]:
    """Ay × matbaa yük tablosu. Sütunlar: planı geçmiş + bu aydan itibaren `months` ay + tarihsiz."""
    cols = [OVERDUE] + months_ahead(now, months) + [UNDATED]
    horizon = set(cols)
    hist = history_load(cards, tech, now)
    ref = reference(hist)
    ly = last_year_same_month(cards, cols)
    rows: dict[str, dict[str, dict[str, Any]]] = {}
    beyond = 0
    for c in cards:
        if c.get("stage") not in LOAD_STAGES:
            continue
        b = load_bucket(c, now)
        if b not in horizon:
            beyond += 1
            continue
        p = c.get("printer") or NO_PRINTER
        cell = rows.setdefault(p, {}).setdefault(b, {"jobs": 0, "adet": 0.0, "forma": 0.0, "cards": []})
        cell["jobs"] += 1
        cell["adet"] += _num(c.get("qty"))
        cell["forma"] += forma_load(c, tech) or 0.0
        cell["cards"].append(card_brief(c, tech, with_cost))
    out_rows = []
    totals = {k: {"jobs": 0, "adet": 0.0, "forma": 0.0} for k in cols}
    for p in sorted(rows, key=lambda x: (x == NO_PRINTER, -sum(v["adet"] for v in rows[x].values()), x)):
        cells = {}
        for k in cols:
            v = rows[p].get(k) or {"jobs": 0, "adet": 0.0, "forma": 0.0, "cards": []}
            cap = store.capacity_for(capacity, p, k) if k not in (OVERDUE, UNDATED) and p != NO_PRINTER else None
            r = ref.get(p) if p != NO_PRINTER else None
            state, rate = (cell_state(v["adet"], v["forma"], cap, r, ratio)
                           if k not in (OVERDUE, UNDATED) and p != NO_PRINTER else (("bos" if not v["jobs"] else "normal"), None))
            last = (ly.get(k) or {}).get(p)
            v["cards"].sort(key=lambda x: (x.get("planBaski") or "", x.get("kitap") or ""))
            cells[k] = {"jobs": v["jobs"], "adet": round(v["adet"], 2), "forma": round(v["forma"], 2), "cards": v["cards"],
                        "kapasite": cap, "durum": state, "oran": rate,
                        "gecenYil": {"jobs": last["jobs"], "adet": round(last["adet"], 2)} if last else None}
            t = totals[k]
            t["jobs"] += v["jobs"]
            t["adet"] += v["adet"]
            t["forma"] += v["forma"]
        out_rows.append({"matbaa": p, "referans": ref.get(p), "kapasiteVar": any(r["matbaa"] == p for r in capacity),
                         "hucreler": cells})
    ly_tot = {k: {"jobs": sum(x["jobs"] for x in (ly.get(k) or {}).values()),
                  "adet": round(sum(x["adet"] for x in (ly.get(k) or {}).values()), 2)} for k in cols}
    return {"aylar": [{"key": k, "label": month_label(k)} for k in cols], "satirlar": out_rows,
            "toplam": {k: {"jobs": v["jobs"], "adet": round(v["adet"], 2), "forma": round(v["forma"], 2),
                           "gecenYil": ly_tot[k] if k not in (OVERDUE, UNDATED) else None} for k, v in totals.items()},
            "ufukDisi": beyond, "oranEsigi": ratio, "referansNotu": REFERENCE_NOTE}


def conflicts(table: dict[str, Any]) -> list[dict[str, Any]]:
    """Eşiği aşan ay × matbaa hücreleri (kapasite aşımı önce), iş listesiyle."""
    out = []
    for row in table["satirlar"]:
        for k, cell in row["hucreler"].items():
            if cell["durum"] in ("asim", "referans-ustu"):
                out.append({"matbaa": row["matbaa"], "ay": k, "ayAdi": month_label(k), "durum": cell["durum"],
                            "oran": cell["oran"], "jobs": cell["jobs"], "adet": cell["adet"], "forma": cell["forma"],
                            "kapasite": cell["kapasite"], "referans": row["referans"], "cards": cell["cards"]})
    out.sort(key=lambda x: (x["durum"] != "asim", -(x["oran"] or 0), x["ay"], x["matbaa"]))
    return out


# ============================================================ kağıt ihtiyacı


def paper_need(cards: list[dict[str, Any]], tech: dict[str, dict[str, Any]], names: dict[str, dict[str, Any]],
               now: date, months: int, measure: str = "brut") -> dict[str, Any]:
    """Baskı ayı × kağıt cinsi: kg (seçilen ölçü), öbür ölçü, CRM «toplam» kolonu (birimi ölçülecek), kart ve parça.
    Kağıt alanı hiç dolu olmayan açık kart ayrıca sayılır (kapsam)."""
    cols = [OVERDUE] + months_ahead(now, months) + [UNDATED]
    horizon = set(cols)
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    covered = missing = 0
    missing_cards: list[dict[str, Any]] = []
    other = "net" if measure == "brut" else "brut"
    for c in cards:
        if c.get("stage") not in PAPER_STAGES:
            continue
        b = load_bucket(c, now)
        if b not in horizon:
            continue
        t = tech.get(c.get("id") or "")
        parts = (t or {}).get("parts") or []
        if not any((p.get(measure) or p.get(other)) for p in parts):
            missing += 1
            missing_cards.append(card_brief(c, tech))
            continue
        covered += 1
        for p in parts:
            kg, alt = p.get(measure), p.get(other)
            if not (kg or alt or p.get("toplam")):
                continue
            cid = p.get("cins") or "-"
            key = (b, cid)
            cell = cells.setdefault(key, {"ay": b, "cins": cid, "kg": 0.0, "digerKg": 0.0, "toplam": 0.0, "kartlar": set(),
                                          "parcalar": {}, "ebatlar": {}, "eksikOlcu": 0})
            if kg:
                cell["kg"] += kg
            else:
                cell["eksikOlcu"] += 1   # seçilen ölçü boş, öbürü dolu: toplamda sayılmadı, ayrıca yazılır
            cell["digerKg"] += alt or 0.0
            cell["toplam"] += p.get("toplam") or 0.0
            cell["kartlar"].add(c.get("id"))
            cell["parcalar"][p["label"]] = cell["parcalar"].get(p["label"], 0.0) + (kg or 0.0)
            e = p.get("ebat")
            if e:
                en = (names.get(e) or {}).get("ad") or "?"
                cell["ebatlar"][en] = cell["ebatlar"].get(en, 0.0) + (kg or 0.0)
    rows = []
    for (b, cid), v in cells.items():
        n = names.get(cid) or {}
        rows.append({"ay": b, "ayAdi": month_label(b), "cins": cid if cid != "-" else None,
                     "cinsAdi": n.get("ad") or ("Kağıt cinsi girilmemiş" if cid == "-" else "Bilinmeyen kağıt cinsi"),
                     "gramaj": n.get("gramaj"), "kg": round(v["kg"], 2), "digerKg": round(v["digerKg"], 2),
                     "toplam": round(v["toplam"], 2), "kart": len(v["kartlar"]), "eksikOlcu": v["eksikOlcu"],
                     "parcalar": {k: round(x, 2) for k, x in v["parcalar"].items()},
                     "ebatlar": {k: round(x, 2) for k, x in v["ebatlar"].items()}})
    order = {k: i for i, k in enumerate(cols)}
    rows.sort(key=lambda r: (order.get(r["ay"], 99), -r["kg"], r["cinsAdi"]))
    by_kind: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = r["cins"] or "-"
        x = by_kind.setdefault(k, {"cins": r["cins"], "cinsAdi": r["cinsAdi"], "gramaj": r["gramaj"], "kg": 0.0, "aylar": {}})
        x["kg"] = round(x["kg"] + r["kg"], 2)
        x["aylar"][r["ay"]] = round(x["aylar"].get(r["ay"], 0.0) + r["kg"], 2)
    kinds = sorted(by_kind.values(), key=lambda x: -x["kg"])
    missing_cards.sort(key=lambda x: (x.get("planBaski") or "9999", x.get("kitap") or ""))
    return {"aylar": [{"key": k, "label": month_label(k)} for k in cols], "satirlar": rows, "cinsler": kinds,
            "olcu": measure, "kapsam": {"dolu": covered, "bos": missing}, "kagitsizKartlar": missing_cards,
            "toplamKg": round(sum(r["kg"] for r in rows), 2)}


# ============================================================ tedarikçi borç ve ödeme (FIFO)


def fifo_open(bakiye: float, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sertifikalı FIFO: satır en yeni vadeden geriye birikimli (`kumulatif`); bakiye ≥ birikimli → satır tümüyle açık;
    bakiye birikimlinin önceki değerinden büyükse kalan kısmı açık; değilse ödenmiş sayılır."""
    out = []
    for ln in lines:
        tut, kum = float(ln["tutar"]), float(ln["kumulatif"])
        if bakiye >= kum:
            acik = tut
        elif bakiye > kum - tut:
            acik = bakiye - (kum - tut)
        else:
            acik = 0.0
        if acik > 0:
            out.append(dict(ln, acik=round(acik, 2)))
    return out


PAST = [("k_1_30", 1, 30), ("k_31_60", 31, 60), ("k_61_90", 61, 90), ("k_90p", 91, None)]
AHEAD = [("g_0_30", 0, 30), ("g_31_60", 31, 60), ("g_61_90", 61, 90), ("g_90p", 91, None)]


def aging(bakiye: float, lines: list[dict[str, Any]], asof: date) -> dict[str, Any]:
    """Tek cari: vadesi geçmiş kovalar (gün = bugün − vade), gelecek kovalar (gün = vade − bugün), vadesi gelmemiş
    toplam, vade planına dağıtılamayan bakiye (plansız) ve katalogdaki «vadesi geçmiş» = max(0, bakiye − gelmemiş)."""
    b = round(float(bakiye), 2)
    out = {k: 0.0 for k, _, _ in PAST + AHEAD}
    out.update(bakiye=b, gelmemis=0.0, acikSatir=[])
    if b <= 0:
        out.update(vadesiGecmis=0.0, plansiz=0.0, katalogVadesiGecmis=0.0)
        return out
    open_ = fifo_open(b, lines)
    for ln in open_:
        v = ln.get("vade")
        if not v:
            continue
        gun = (asof - v).days
        if gun <= 0:
            out["gelmemis"] += ln["acik"]
            ahead = -gun
            for k, lo, hi in AHEAD:
                if ahead >= lo and (hi is None or ahead <= hi):
                    out[k] += ln["acik"]
                    break
        else:
            for k, lo, hi in PAST:
                if gun >= lo and (hi is None or gun <= hi):
                    out[k] += ln["acik"]
                    break
        out["acikSatir"].append({"vade": v.isoformat(), "tutar": round(ln["tutar"], 2), "acik": ln["acik"], "gun": gun,
                                 "faturaNo": ln.get("faturaNo"),
                                 "faturaTarihi": ln["faturaTarihi"].isoformat() if ln.get("faturaTarihi") else None})
    for k in list(out):
        if isinstance(out[k], float):
            out[k] = round(out[k], 2)
    past = round(sum(out[k] for k, _, _ in PAST), 2)
    out["plansiz"] = round(max(0.0, b - past - out["gelmemis"]), 2)
    out["vadesiGecmis"] = round(past + out["plansiz"], 2)
    # Katalog tanımı (satici-borcu-vadesi-gecmis-fifo): bakiye − vadesi gelmemiş plan satırları, eksi ise 0. FIFO
    # dağıtımında gelmemiş satırlar en yeni satırlardır; ikisi aynı sonucu verir (kabul testi 4 bunu denetler).
    fut_total = sum(float(ln["tutar"]) for ln in lines if ln.get("vade") and ln["vade"] >= asof)
    out["katalogVadesiGecmis"] = round(max(0.0, b - fut_total), 2)
    out["acikSatir"].sort(key=lambda x: x["vade"])
    return out


def classify(suppliers: list[dict[str, Any]], printer_codes: list[str], paper_codes: list[str],
             invoice_codes: set[str]) -> dict[str, dict[str, str]]:
    """Cari kodu → {tur: matbaa|kagit|diger, kaynak}. Özel kod önce; özel kodu yoksa baskı faturası kesmiş cari matbaa.
    Özel kod Türkçe harf ve büyük/küçük harf farkı gözetilmeden karşılaştırılır (KAĞITÇILAR = kağıtçılar = KAGITCILAR)."""
    pc = {fold(x) for x in printer_codes}
    kc = {fold(x) for x in paper_codes}
    out: dict[str, dict[str, str]] = {}
    for s in suppliers:
        oz = fold(s.get("ozelKod"))
        if oz and oz in pc:
            out[s["kod"]] = {"tur": "matbaa", "kaynak": "ozel-kod"}
        elif oz and oz in kc:
            out[s["kod"]] = {"tur": "kagit", "kaynak": "ozel-kod"}
        elif s["kod"] in invoice_codes:
            out[s["kod"]] = {"tur": "matbaa", "kaynak": "baski-faturasi"}
        else:
            out[s["kod"]] = {"tur": "diger", "kaynak": ""}
    return out


def purchases_by_supplier(rows: list[dict[str, Any]], now: date) -> dict[str, dict[str, Any]]:
    """Cari kodu → bu yıl, son 12 tam ay ve aylık seri (KDV dahil NETTOTAL)."""
    last12 = set(months_back(now, 12)) | {mkey(now)}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = f"{r['yil']:04d}-{r['ay']:02d}"
        x = out.setdefault(r["cariKod"], {"buYil": 0.0, "son12": 0.0, "fatura12": 0, "aylik": {}})
        if r["yil"] == now.year:
            x["buYil"] += r["tutar"]
        if k in last12:
            x["son12"] += r["tutar"]
            x["fatura12"] += r["fatura"]
        x["aylik"][k] = round(x["aylik"].get(k, 0.0) + r["tutar"], 2)
    for x in out.values():
        x["buYil"], x["son12"] = round(x["buYil"], 2), round(x["son12"], 2)
    return out


# ============================================================ matbaa ↔ cari eşlemesi


def printer_code_votes(raw_cards: list[dict[str, Any]], built: list[dict[str, Any]], invoices: list[dict[str, Any]],
                       match_costs: Callable[..., dict[str, list[dict]]]) -> dict[str, dict[str, int]]:
    """CRM matbaa adı → Logo cari kodu → kaç kartta faturayı o cari kesti. Kartla fatura M12 kuralıyla bağlanır
    (`production.match_costs`: satır özel kodu = stok kodu, kartın zaman penceresi)."""
    matched = match_costs(raw_cards, [dict(x, tarih=x.get("tarih")) for x in invoices if x.get("stok")])
    printer_of = {c["id"]: c.get("printer") for c in built}
    votes: dict[str, dict[str, int]] = {}
    for cid, rows in matched.items():
        p = printer_of.get(cid)
        if not p:
            continue
        codes = {r.get("cariKod") for r in rows if r.get("cariKod")}
        for code in codes:
            votes.setdefault(p, {})[code] = votes.setdefault(p, {}).get(code, 0) + 1
    return votes


def supplier_map(votes: dict[str, dict[str, int]], manual: dict[str, dict[str, Any]], min_share: float,
                 min_jobs: int) -> dict[str, dict[str, Any]]:
    """CRM matbaa adı → {cari, kaynak: elle|veri, pay, is}. Elle kayıt öneriyi ezer; veri önerisi en çok faturayı kesen
    cari, payı `min_share` ve iş sayısı `min_jobs` üstündeyse."""
    out: dict[str, dict[str, Any]] = {}
    for p, codes in votes.items():
        total = sum(codes.values())
        code, n = max(codes.items(), key=lambda kv: (kv[1], kv[0]))
        if total >= min_jobs and n / total >= min_share:
            out[p] = {"cari": code, "kaynak": "veri", "pay": round(n / total, 4), "is": total,
                      "adaylar": sorted(({"cari": k, "is": v} for k, v in codes.items()), key=lambda x: -x["is"])}
        else:
            out[p] = {"cari": None, "kaynak": "belirsiz", "pay": round(n / total, 4) if total else None, "is": total,
                      "adaylar": sorted(({"cari": k, "is": v} for k, v in codes.items()), key=lambda x: -x["is"])}
    for p, m in manual.items():
        out[p] = {**(out.get(p) or {"adaylar": [], "is": 0, "pay": None}), "cari": m.get("cari"), "kaynak": "elle",
                  "by": m.get("byName"), "at": m.get("at")}
    return out


# ============================================================ faturası görünmeyen baskı


def invoice_lag(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Depo girişinden ilk baskı faturasına gün farkı (fatura önce kesilmişse eksi). Yeterli örnekte 3. çeyrek bekleme
    süresidir."""
    lags = []
    for c in cards:
        d = _day(((c.get("actual") or {}).get("depo") or {}).get("day"))
        rows = c.get("costRows") or []
        first = min((x for x in (_day(r.get("tarih")) for r in rows) if x), default=None)
        if d and first:
            lags.append((first - d).days)
    if len(lags) < MIN_SAMPLES:
        return {"gun": None, "ortanca": None, "ornek": len(lags)}
    q = statistics.quantiles(lags, n=4)
    return {"gun": max(0, int(round(q[2]))), "ortanca": int(round(statistics.median(lags))), "ornek": len(lags)}


def unbilled(cards: list[dict[str, Any]], tech: dict[str, dict[str, Any]], linked_cards: set[str], now: date,
             grace: int, since: date) -> list[dict[str, Any]]:
    """Depoya girmiş, bekleme süresi geçmiş, M12 kuralıyla ya da onaylı bağla faturası görünmeyen kitap kartları."""
    out = []
    for c in cards:
        if c.get("stage") != "tamam":
            continue
        d = _day(((c.get("actual") or {}).get("depo") or {}).get("day"))
        if not d or d < since or (now - d).days <= grace:
            continue
        if c.get("costRows") or c.get("id") in linked_cards:
            continue
        b = card_brief(c, tech)
        b.update(depo=d.isoformat(), bekleyenGun=(now - d).days)
        out.append(b)
    out.sort(key=lambda x: (-x["bekleyenGun"], x.get("kitap") or ""))
    return out


def unmatched_invoices(raw_cards: list[dict[str, Any]], invoices: list[dict[str, Any]],
                       match_costs: Callable[..., dict[str, list[dict]]], linked: dict[tuple[str, str], dict[str, Any]],
                       since: date) -> list[dict[str, Any]]:
    """Baskı faturası satırı M12 kuralıyla hiçbir karta bağlanmıyor ve onaylı bağı yok (son pencerede)."""
    matched = match_costs(raw_cards, [x for x in invoices if x.get("stok")])
    used = {(r["firma"], r["satirRef"]) for rows in matched.values() for r in rows}
    out = []
    for x in invoices:
        d = src.day(x.get("tarih"))
        if not d or d < since:
            continue
        key = (x["firma"], x["satirRef"])
        if key in used:
            continue
        link = linked.get((x["firma"], str(x["satirRef"])))
        if link and link["durum"] == "onayli":
            continue
        out.append({"firma": x["firma"], "satirRef": str(x["satirRef"]), "faturaNo": x.get("no"), "tarih": d.isoformat(),
                    "cariKod": x.get("cariKod"), "cari": x.get("cari"), "stok": x.get("stok"), "adet": x.get("adet"),
                    "tutar": round(x.get("tutar") or 0.0, 2), "oneri": link})
    out.sort(key=lambda r: r["tarih"], reverse=True)
    return out


def match_candidates(line: dict[str, Any], cards: list[dict[str, Any]], unbilled_ids: set[str],
                     code_of_printer: dict[str, Optional[str]], tol: float, days: int) -> list[dict[str, Any]]:
    """Kuralın bağlayamadığı fatura satırı için aday kartlar: (a) aynı stok kodlu kart (penceresi dışında kalmış), ya da
    (b) faturası görünmeyen, matbaası bu cariye eşlenmiş, adedi ±`tol`, depo girişi ±`days` gün içinde olan kart.
    Puan: stok kodu 2, adet yakınlığı ve tarih yakınlığı 0–1."""
    d = _day(line.get("tarih"))
    qty = _num(line.get("adet"))
    stok = (line.get("stok") or "").strip().upper()
    out = []
    for c in cards:
        if c.get("stage") in ("iptal",):
            continue
        same_code = bool(stok) and (c.get("stockCode") or "").strip().upper() == stok
        mapped = code_of_printer.get(c.get("printer") or "") == line.get("cariKod")
        if not same_code and not (c.get("id") in unbilled_ids and mapped):
            continue
        cq = _num(c.get("qty"))
        dd = _day(((c.get("actual") or {}).get("depo") or {}).get("day")) or _day((c.get("plan") or {}).get("baski"))
        qfit = 1 - min(1.0, abs(cq - qty) / qty) if qty and cq else 0.0
        dfit = 1 - min(1.0, abs((dd - d).days) / days) if dd and d else 0.0
        if not same_code and (qfit < 1 - tol or dfit <= 0):
            continue
        out.append({"kartId": c.get("id"), "kitap": c.get("bookTitle") or c.get("name"), "baskiNo": c.get("printNo"),
                    "stokKodu": c.get("stockCode"), "matbaa": c.get("printer"), "adet": c.get("qty"),
                    "depo": dd.isoformat() if dd else None, "puan": round((2 if same_code else 0) + qfit + dfit, 4)})
    out.sort(key=lambda x: -x["puan"])
    return out


def monthly_billing(cards: list[dict[str, Any]], invoices: list[dict[str, Any]], code_of_printer: dict[str, Optional[str]],
                    months: list[str]) -> list[dict[str, Any]]:
    """Matbaa × ay: depoya giren adet (M12) ile faturalanan adet (Logo baskı faturası, eşlenmiş cari). Eşleme kuralı
    netleşene kadar kaba karşılaştırma (analiz §9)."""
    want = set(months)
    by: dict[tuple[str, str], dict[str, float]] = {}
    for c in cards:
        m = mkey(_day(((c.get("actual") or {}).get("depo") or {}).get("day")))
        if m in want and c.get("printer"):
            x = by.setdefault((c["printer"], m), {"depo": 0.0, "fatura": 0.0})
            x["depo"] += _num(c.get("qty"))
    printer_of_code = {v: k for k, v in code_of_printer.items() if v}
    for ln in invoices:
        m = mkey(src.day(ln.get("tarih")))
        p = printer_of_code.get(ln.get("cariKod") or "")
        if m in want and p:
            x = by.setdefault((p, m), {"depo": 0.0, "fatura": 0.0})
            x["fatura"] += _num(ln.get("adet"))
    out = [{"matbaa": p, "ay": m, "ayAdi": month_label(m), "depoAdet": round(v["depo"], 2), "faturaAdet": round(v["fatura"], 2),
            "fark": round(v["depo"] - v["fatura"], 2)} for (p, m), v in by.items()]
    out.sort(key=lambda r: (r["ay"], r["matbaa"]), reverse=True)
    return out


# ============================================================ birim maliyet eğilimi


def page_band(pages: Optional[float], bands: list[int]) -> str:
    if not pages:
        return "Sayfa sayısı yok"
    lo = 1
    for b in bands:
        if pages <= b:
            return f"{lo}–{b} sayfa"
        lo = b + 1
    return f"{lo}+ sayfa"


def cost_trend(cards: list[dict[str, Any]], tech: dict[str, dict[str, Any]], options: dict[str, dict[int, str]],
               now: date, months: int, kirilim: str, bands: list[int]) -> dict[str, Any]:
    """Ay (ilk baskı faturası ayı) × kırılım: ağırlıklı birim (Σ tutar ÷ Σ adet), ortanca birim, 100 sayfa başı ortanca,
    iş sayısı. Birim = Logo'daki matbaa baskı faturasında adet başı bedel (M12)."""
    window = months_back(now, months) + [mkey(now)]
    want = set(window)

    def group_of(c: dict[str, Any]) -> str:
        t = tech.get(c.get("id") or "") or {}
        if kirilim == "cilt":
            return (options.get("new_ciltlemesekli") or {}).get(t.get("cilt") or -1) or ("Kod " + str(t["cilt"]) if t.get("cilt") else "Cilt bilgisi yok")
        if kirilim == "sayfa":
            return page_band(t.get("sayfa"), bands)
        if kirilim == "baski-tipi":
            return (options.get("new_baskitipi") or {}).get(t.get("baskiTipi") or -1) or ("Kod " + str(t["baskiTipi"]) if t.get("baskiTipi") else "Baskı tipi yok")
        if kirilim == "matbaa":
            return c.get("printer") or NO_PRINTER
        return "Bütün baskılar"

    acc: dict[tuple[str, str], dict[str, Any]] = {}
    for c in cards:
        rows = c.get("costRows") or []
        qty = sum(_num(r.get("adet")) for r in rows)
        tot = sum(_num(r.get("tutar")) for r in rows)
        if qty <= 0 or tot <= 0:
            continue
        first = min((x for x in (_day(r.get("tarih")) for r in rows) if x), default=None)
        m = mkey(first)
        if m not in want:
            continue
        g = group_of(c)
        x = acc.setdefault((g, m), {"adet": 0.0, "tutar": 0.0, "birim": [], "sayfa100": []})
        x["adet"] += qty
        x["tutar"] += tot
        unit = tot / qty
        x["birim"].append(unit)
        pages = (tech.get(c.get("id") or "") or {}).get("sayfa")
        if pages:
            x["sayfa100"].append(unit / float(pages) * 100)
    groups: dict[str, dict[str, Any]] = {}
    for (g, m), x in acc.items():
        s = groups.setdefault(g, {"grup": g, "aylar": {}, "adet": 0.0, "tutar": 0.0, "is": 0})
        s["aylar"][m] = {"agirlikliBirim": round(x["tutar"] / x["adet"], 4), "ortancaBirim": round(statistics.median(x["birim"]), 4),
                         "sayfa100": round(statistics.median(x["sayfa100"]), 4) if x["sayfa100"] else None,
                         "is": len(x["birim"]), "adet": round(x["adet"], 2), "tutar": round(x["tutar"], 2)}
        s["adet"] += x["adet"]
        s["tutar"] += x["tutar"]
        s["is"] += len(x["birim"])
    out = []
    half = len(window) // 2
    for s in groups.values():
        recent = [s["aylar"][m] for m in window[half:] if m in s["aylar"]]
        old = [s["aylar"][m] for m in window[:half] if m in s["aylar"]]

        def wavg(xs: list[dict[str, Any]]) -> Optional[float]:
            a = sum(v["adet"] for v in xs)
            return round(sum(v["tutar"] for v in xs) / a, 4) if a else None

        r, o = wavg(recent), wavg(old)
        out.append({"grup": s["grup"], "is": s["is"], "adet": round(s["adet"], 2),
                    "agirlikliBirim": round(s["tutar"] / s["adet"], 4) if s["adet"] else None,
                    "sonDonem": r, "oncekiDonem": o, "egilim": round((r - o) / o, 4) if r is not None and o else None,
                    "aylar": s["aylar"]})
    out.sort(key=lambda x: -x["is"])
    return {"kirilim": kirilim, "aylar": [{"key": m, "label": month_label(m)} for m in window], "gruplar": out,
            "yarilar": {"son": window[half:], "onceki": window[:half]}}


def paper_price_trend(rows: list[dict[str, Any]], now: date, months: int) -> list[dict[str, Any]]:
    """Kağıt malzemesi × ay: birim fiyat (Σ tutar ÷ Σ miktar, KDV hariç), birim ayrı tutulur (kg / tabaka karışmaz)."""
    window = months_back(now, months) + [mkey(now)]
    want = set(window)
    acc: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        m = mkey(r.get("tarih"))
        if m not in want or r["miktar"] <= 0:
            continue
        key = (r["kod"], r["birim"], m)
        x = acc.setdefault(key, {"miktar": 0.0, "tutar": 0.0, "ad": r["ad"]})
        x["miktar"] += r["miktar"]
        x["tutar"] += r["tutar"]
    items: dict[tuple[str, str], dict[str, Any]] = {}
    for (kod, birim, m), x in acc.items():
        it = items.setdefault((kod, birim), {"kod": kod, "ad": x["ad"], "birim": birim, "aylar": {}, "miktar": 0.0, "tutar": 0.0})
        it["aylar"][m] = {"birimFiyat": round(x["tutar"] / x["miktar"], 4), "miktar": round(x["miktar"], 2)}
        it["miktar"] += x["miktar"]
        it["tutar"] += x["tutar"]
    out = []
    for it in items.values():
        seq = [it["aylar"][m]["birimFiyat"] for m in window if m in it["aylar"]]
        out.append({"kod": it["kod"], "ad": it["ad"], "birim": it["birim"], "miktar": round(it["miktar"], 2),
                    "tutar": round(it["tutar"], 2), "ortalama": round(it["tutar"] / it["miktar"], 4) if it["miktar"] else None,
                    "ilk": seq[0] if seq else None, "son": seq[-1] if seq else None,
                    "degisim": round((seq[-1] - seq[0]) / seq[0], 4) if len(seq) > 1 and seq[0] else None,
                    "aylar": it["aylar"]})
    out.sort(key=lambda x: -x["tutar"])
    return out


# ============================================================ plan girdisi (M11 Baskı Öneri, M10 ilk baskı)


def report_rows(data: Optional[dict[str, Any]], view_id: str) -> list[dict[str, Any]]:
    """Baskı Öneri önbelleğinden bir görünümün satırları (satırlar kolon sırasında dizi)."""
    for v in (data or {}).get("views") or []:
        if v.get("id") == view_id:
            keys = [c["key"] for c in v.get("columns") or []]
            return [dict(zip(keys, r)) for r in v.get("rows") or []]
    return []


def demand_inputs(reprint_rows: list[dict[str, Any]], decisions: list[dict[str, Any]], cards: list[dict[str, Any]],
                  levels: tuple[str, ...] = ("Risk/Acil", "Kritik")) -> dict[str, Any]:
    """Kartı açılmamış gelecek baskı ihtiyacı. Baskı Öneri: öneri seviyesi `levels` olan ve açık (baskıdan çıkmamış)
    kartı olmayan kitaplar, CRM'deki önerilen adet ve tükenme süresiyle. M10: onaylı ilk baskı kararı olup hiç kartı
    olmayan kitaplar, karar adedi ve yayın ayıyla."""
    open_codes = {(c.get("stockCode") or "").strip().upper() for c in cards
                  if c.get("stage") in LOAD_STAGES and c.get("stockCode")}
    all_codes = {(c.get("stockCode") or "").strip().upper() for c in cards if c.get("stockCode")}
    reprint = []
    for r in reprint_rows:
        code = (str(r.get("stok_kodu") or "")).strip().upper()
        if not code or r.get("oneri") not in levels or code in open_codes:
            continue
        tuk = r.get("tukenme_suresi")
        reprint.append({"stokKodu": code, "kitap": r.get("urun_adi"), "oneri": r.get("oneri"),
                        "oneriAdet": r.get("oneri_adet"), "tukenme": tuk if isinstance(tuk, (int, float)) else None,
                        "stok": r.get("stok_adedi"), "hiz": r.get("ort_satis_hizi"), "yayinevi": r.get("yayinevi")})
    reprint.sort(key=lambda x: (x["tukenme"] if x["tukenme"] is not None else 1e9, x["kitap"] or ""))
    first = []
    for d in decisions:
        code = (d.get("code") or "").strip().upper()
        if d.get("status") != "onaylandi" or (code and code in all_codes):
            continue
        first.append({"stokKodu": code or None, "kitap": d.get("title"), "adet": d.get("units"), "yayinAyi": d.get("launch")})
    first.sort(key=lambda x: (x["yayinAyi"] or "9999", x["kitap"] or ""))
    return {"baskiOneri": reprint, "ilkBaski": first,
            "baskiOneriAdet": round(sum(_num(x["oneriAdet"]) for x in reprint), 2),
            "ilkBaskiAdet": round(sum(_num(x["adet"]) for x in first), 2), "seviyeler": list(levels)}


# ============================================================ depo uyumu (M43 bağlantı noktası)


def incoming(cards: list[dict[str, Any]], receipts: dict[str, dict[str, float]], now: date, ahead: int,
             back: int) -> dict[str, Any]:
    """Aylık depo girişi: geçmiş `back` ay Logo'da gerçekleşen (üretimden giriş), bu aydan `ahead` ay açık kartların
    planlanan depo girişi (M12 planı; baskıdan çıkmış kartlar dahil)."""
    fut = months_ahead(now, ahead)
    want = set(fut)
    plan: dict[str, dict[str, float]] = {k: {"adet": 0.0, "is": 0} for k in fut}
    undated = {"adet": 0.0, "is": 0}
    for c in cards:
        if c.get("stage") not in LOAD_STAGES + ("yolda",):
            continue
        d = _day((c.get("plan") or {}).get("depo")) or _day((c.get("plan") or {}).get("baski"))
        m = mkey(d)
        if m is None or m < mkey(now):
            # planı geçmiş ya da tarihsiz: bu ay girecek sayılmaz, ayrıca yazılır
            undated["adet"] += _num(c.get("qty"))
            undated["is"] += 1
            continue
        if m in want:
            plan[m]["adet"] += _num(c.get("qty"))
            plan[m]["is"] += 1
    past = months_back(now, back) + [mkey(now)]
    return {"gecmis": [{"ay": m, "ayAdi": month_label(m), "adet": round((receipts.get(m) or {}).get("adet", 0.0), 2),
                        "fis": int((receipts.get(m) or {}).get("fis", 0))} for m in past],
            "plan": [{"ay": m, "ayAdi": month_label(m), "adet": round(v["adet"], 2), "is": int(v["is"])} for m, v in plan.items()],
            "planiGecmis": {"adet": round(undated["adet"], 2), "is": int(undated["is"])}}


#: M43 (depo ve stok) kapasiteyi kaydettiğinde buraya bağlanır: fn() → {"kapasiteAdet": float|None, "stokAdet":
#: float|None, "kaynak": str}. Bağlanmadıysa ekran «depo kapasitesi tanımlı değil» yazar.
_depot_capacity: list[Callable[[], Optional[dict[str, Any]]]] = []


def register_depot_capacity(fn: Callable[[], Optional[dict[str, Any]]]) -> None:
    _depot_capacity[:] = [fn]


def depot_capacity() -> Optional[dict[str, Any]]:
    if not _depot_capacity:
        return None
    try:
        return _depot_capacity[0]()
    except Exception as e:  # noqa: BLE001 — depo modülü düşerse tedarik ekranı açılır
        log.info("supply: depo kapasitesi okunamadı: %s", e)
        return None


# ============================================================ kaynak okuma (önbellekli)


class Source:
    """M12 kartları + CRM teknik alanları + Logo tedarikçi/fatura okuması. Bağlantılar okuma başına açılır; aynı anda tek
    okuma; sonuç 5 dakika bellekte. Logo düşerse CRM/M12 ile devam edilir, ekranda söylenir."""

    def __init__(self, production: Any, logo_file: Callable[[], str], crm_file: Callable[[], str], schema: Callable[[], str],
                 settings: Callable[[], dict[str, Any]]):
        self.production = production
        self._logo_file = logo_file
        self._crm_file = crm_file
        self._schema = schema
        self._settings = settings
        self._lock = threading.Lock()
        self._snap: Optional[dict[str, Any]] = None
        self._at = 0.0

    def logo_runner(self) -> src.Run:
        return src.runner(self._logo_file())

    def snapshot(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        with self._lock:
            if not fresh and self._snap is not None and time.time() - self._at < TTL:
                return self._snap
            snap = self.read(engine, tenant, fresh, now)
            self._snap, self._at = snap, time.time()
            return snap

    def read(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        s = self._settings()
        warnings: list[str] = []
        t0 = time.monotonic()
        cards, psnap = self.production.cards(engine, tenant, fresh, now)
        since = parse_day(psnap.get("since")) or date(now.year - 2, 1, 1)
        m12_ms = int((time.monotonic() - t0) * 1000)
        warnings += [w for w in psnap.get("warnings") or []]

        t1 = time.monotonic()
        tech: dict[str, dict[str, Any]] = {}
        names: dict[str, dict[str, Any]] = {}
        options: dict[str, dict[int, str]] = {}
        changes: list[dict[str, Any]] = []
        try:
            crm = src.runner(self._crm_file())
            schema = self._schema()
            tech = src.read_card_tech(crm, schema, since)
            names = src.read_paper_names(crm, schema)
            try:
                options = src.read_options(crm, schema)
            except src.SourceError as e:
                log.info("supply: CRM seçenek adları okunamadı: %s", e)
            try:
                changes = src.read_plan_changes(crm, schema, since)
            except src.SourceError as e:
                log.info("supply: plan değişiklikleri okunamadı: %s", e)
                warnings.append("CRM plan değişikliği kayıtları okunamadı.")
        except src.SourceError as e:
            log.warning("supply: CRM teknik alanlar okunamadı: %s", e)
            warnings.append("CRM üretim kartının kağıt ve teknik alanları şu an okunamıyor; kağıt ihtiyacı ve forma yükü boş.")
        options.setdefault("new_degisikliksebebi", dict(src.CHANGE_REASONS))
        crm_ms = int((time.monotonic() - t1) * 1000)

        t2 = time.monotonic()
        logo: dict[str, Any] = {"ok": False}
        try:
            run = src.runner(self._logo_file())
            firms = src.firms_for(run)
            firm, year = src.current_firm(firms, now)
            if year != now.year:
                warnings.append(f"Logo'da {now.year} dönemi yok; tedarikçi bakiyesi {year} firmasından okunuyor.")
            back = src.window_start(now, s["trendMonths"])
            win = min(back, since)
            win_firms = src.firms_between(firms, win, now)
            suppliers = src.read_suppliers(run, firm, year, s["supplierPrefix"])
            plan_lines = src.read_plan_lines(run, firm, year, s["supplierPrefix"])
            specodes = src.read_specode_counts(run, firm, s["supplierPrefix"])
            invoices = src.read_print_invoices(run, win_firms, win)
            purchases = src.read_purchases(run, src.firms_between(firms, src.window_start(now, 24), now),
                                           src.window_start(now, 24), s["supplierPrefix"])
            receipts = src.read_production_receipts(run, src.firms_between(firms, src.window_start(now, 24), now),
                                                    src.window_start(now, 24))
            kinds = classify(suppliers, s["printerSpecodes"], s["paperSpecodes"], {x["cariKod"] for x in invoices if x.get("cariKod")})
            paper_codes = [k for k, v in kinds.items() if v["tur"] == "kagit"]
            paper_rows: list[dict[str, Any]] = []
            if paper_codes:
                try:
                    paper_rows = src.read_paper_purchases(run, win_firms, paper_codes, back)
                except src.SourceError as e:
                    log.info("supply: kağıt alış satırları okunamadı: %s", e)
                    warnings.append("Kağıt alış satırları okunamadı; kağıt fiyat eğilimi boş.")
            if not any(v["kaynak"] == "ozel-kod" for v in kinds.values()):
                warnings.append("Logo'da ayardaki matbaa / kağıtçı özel koduyla tedarikçi bulunamadı: özel kodun yazımı "
                                "«Tedarikçiler» sayfasındaki dağılımdan seçilip ayara yazılmalı. Matbaalar şimdilik baskı "
                                "faturası kesmiş carilerden bulunuyor.")
            logo = {"ok": True, "firm": firm, "year": year, "firms": {str(k): v for k, v in firms.items()},
                    "dataEnd": (src.read_data_end(run, firms) or None), "suppliers": suppliers, "planLines": plan_lines,
                    "specodes": specodes, "invoices": invoices, "purchases": purchases, "receipts": receipts,
                    "paperRows": paper_rows, "kinds": kinds}
        except src.SourceError as e:
            log.warning("supply: Logo okunamadı: %s", e)
            warnings.append("Logo'ya şu an ulaşılamıyor; tedarikçi borcu, fatura eşleşmesi ve alış eğilimi gösterilemiyor.")
        logo_ms = int((time.monotonic() - t2) * 1000)
        de = logo.get("dataEnd")
        if isinstance(de, date) and (now - de).days > 10:
            warnings.append(f"Logo'daki son satış faturası {de.day:02d}.{de.month:02d}.{de.year}: bu tarihten sonraki fatura, "
                            "ödeme ve depo girişleri Logo kopyasına henüz gelmedi.")
        return {"at": time.time(), "today": now.isoformat(), "since": since.isoformat(), "cards": cards,
                "rawCards": psnap.get("cards") or [], "tech": tech, "paperNames": names, "options": options,
                "planChanges": changes, "logo": logo, "warnings": warnings,
                "db": {"m12Ms": m12_ms, "crmMs": crm_ms, "logoMs": logo_ms}}


# ============================================================ servis


class Service:
    """Ekranın uçları: kaynak okuması + portal kayıtları → tablolar. Yetkiye göre alan çıkarma uç katmanındadır."""

    def __init__(self, source: Source, settings: Callable[[], dict[str, Any]], *,
                 match_costs: Callable[..., dict[str, list[dict]]],
                 printer_stats: Callable[[list[dict[str, Any]], date], list[dict[str, Any]]],
                 report_data: Optional[Callable[[], Optional[dict[str, Any]]]] = None,
                 decisions: Optional[Callable[[Any, str], list[dict[str, Any]]]] = None,
                 unit_costs: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]] = None):
        self.source = source
        self.settings = settings
        self.match_costs = match_costs
        self.printer_stats = printer_stats
        self.report_data = report_data
        self.decisions = decisions
        self.unit_costs = unit_costs

    # ---- ortak
    def snap(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        return self.source.snapshot(engine, tenant, fresh, now)

    def mapping(self, engine: Any, tenant: str, snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
        s = self.settings()
        inv = (snap["logo"].get("invoices") or []) if snap["logo"].get("ok") else []
        votes = printer_code_votes(snap["rawCards"], snap["cards"], inv, self.match_costs) if inv else {}
        return supplier_map(votes, store.list_supplier_map(engine, tenant), s["mapMinShare"], s["mapMinJobs"])

    @staticmethod
    def code_of_printer(mapping: dict[str, dict[str, Any]]) -> dict[str, Optional[str]]:
        return {p: m.get("cari") for p, m in mapping.items()}

    def linked(self, engine: Any, tenant: str) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str]]:
        links = store.list_links(engine, tenant)
        by: dict[tuple[str, str], dict[str, Any]] = {}
        for ln in links:
            key = (ln["firma"], ln["satirRef"])
            if key not in by or ln["durum"] == "onayli":
                by[key] = ln
        cards = {ln["kartId"] for ln in links if ln["durum"] == "onayli" and ln.get("kartId")}
        return by, cards

    # ---- yük
    def load(self, engine: Any, tenant: str, months: Optional[int] = None, fresh: bool = False, with_cost: bool = False,
             now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        s = self.settings()
        snap = self.snap(engine, tenant, fresh, now)
        table = load_table(snap["cards"], snap["tech"], store.list_capacity(engine, tenant), now,
                           int(months or s["loadMonths"]), s["overloadRatio"], with_cost)
        table["cakismalar"] = conflicts(table)
        table["plan"] = self.demand(engine, tenant, snap)
        table["degisiklikler"] = plan_change_summary(snap["planChanges"], snap["cards"], snap["options"], now)
        table["uyarilar"] = snap["warnings"]
        table["asOf"] = datetime.fromtimestamp(snap["at"], TZ).isoformat(timespec="seconds")
        if with_cost and self.unit_costs:
            codes = sorted({c["stokKodu"] for row in table["satirlar"] for cell in row["hucreler"].values()
                            for c in cell["cards"] if c.get("stokKodu")})
            costs = self._unit_costs(codes)
            for row in table["satirlar"]:
                for cell in row["hucreler"].values():
                    for c in cell["cards"]:
                        c["m9Maliyet"] = costs.get(c.get("stokKodu") or "")
        return table

    def _unit_costs(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        if not codes or not self.unit_costs:
            return {}
        try:
            raw = self.unit_costs(codes)
        except Exception as e:  # noqa: BLE001 — fiyatlama modülü düşerse yük tablosu açılır
            log.info("supply: M9 birim maliyeti okunamadı: %s", e)
            return {}
        return {k: {"maliyet": float(v["maliyet"]) if v.get("maliyet") is not None else None, "kaynak": v.get("kaynak"),
                    "tarih": v.get("tarih")} for k, v in raw.items()}

    _report: tuple[float, list[dict[str, Any]]] = (0.0, [])

    def demand(self, engine: Any, tenant: str, snap: dict[str, Any]) -> dict[str, Any]:
        rows, err = [], None
        if self.report_data:
            at, cached = self._report
            if time.time() - at < TTL:
                rows = cached
            else:
                try:
                    rows = report_rows(self.report_data(), "tekrar")
                    self._report = (time.time(), rows)
                except Exception as e:  # noqa: BLE001
                    log.info("supply: baskı önerisi okunamadı: %s", e)
                    err = "Baskı önerisi raporu okunamadı."
        decisions: list[dict[str, Any]] = []
        if self.decisions:
            try:
                decisions = self.decisions(engine, tenant)
            except Exception as e:  # noqa: BLE001
                log.info("supply: ilk baskı kararları okunamadı: %s", e)
        out = demand_inputs(rows, decisions, snap["cards"])
        out["hata"] = err
        out["raporVar"] = bool(rows)
        return out

    # ---- kağıt
    def paper(self, engine: Any, tenant: str, months: Optional[int] = None, fresh: bool = False,
              now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        s = self.settings()
        snap = self.snap(engine, tenant, fresh, now)
        out = paper_need(snap["cards"], snap["tech"], snap["paperNames"], now, int(months or s["paperMonths"]), s["paperMeasure"])
        out["fiyat"] = paper_price_trend(snap["logo"].get("paperRows") or [], now, 12) if snap["logo"].get("ok") else []
        out["alici"] = s["paperBuyer"]
        out["uyarilar"] = snap["warnings"]
        return out

    # ---- tedarikçiler
    def suppliers(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        s = self.settings()
        snap = self.snap(engine, tenant, fresh, now)
        lg = snap["logo"]
        mapping = self.mapping(engine, tenant, snap)
        stats = {x["printer"]: x for x in self.printer_stats(snap["cards"], now)}
        printer_of_code: dict[str, list[str]] = {}
        for p, m in mapping.items():
            if m.get("cari"):
                printer_of_code.setdefault(m["cari"], []).append(p)
        open_jobs: dict[str, int] = {}
        for c in snap["cards"]:
            if c.get("stage") in LOAD_STAGES and c.get("printer"):
                open_jobs[c["printer"]] = open_jobs.get(c["printer"], 0) + 1
        items = []
        if lg.get("ok"):
            asof = self.asof(snap, now)
            lines_by: dict[int, list[dict[str, Any]]] = {}
            for ln in lg["planLines"]:
                lines_by.setdefault(ln["ref"], []).append(ln)
            buys = purchases_by_supplier(lg["purchases"], now)
            for sp in lg["suppliers"]:
                kind = lg["kinds"].get(sp["kod"]) or {"tur": "diger", "kaynak": ""}
                ag = aging(sp["bakiye"], lines_by.get(sp["ref"], []), asof)
                b = buys.get(sp["kod"]) or {"buYil": 0.0, "son12": 0.0, "fatura12": 0, "aylik": {}}
                printers = printer_of_code.get(sp["kod"], [])
                if kind["tur"] == "diger" and not printers and not ag["bakiye"] and not b["son12"]:
                    continue
                items.append({"kod": sp["kod"], "unvan": sp["unvan"], "ozelKod": sp["ozelKod"],
                              "tur": "matbaa" if printers and kind["tur"] == "diger" else kind["tur"],
                              "turKaynak": kind["kaynak"] or ("eslesme" if printers else ""),
                              "crmMatbaa": printers, "acikIs": sum(open_jobs.get(p, 0) for p in printers),
                              "karne": [stats[p] for p in printers if p in stats],
                              "bakiye": ag["bakiye"], "vadesiGecmis": ag["vadesiGecmis"], "plansiz": ag["plansiz"],
                              "gelmemis": ag["gelmemis"], "kovalar": {k: ag[k] for k, _, _ in PAST},
                              "gelecek": {k: ag[k] for k, _, _ in AHEAD}, "katalogVadesiGecmis": ag["katalogVadesiGecmis"],
                              "alisBuYil": b["buYil"], "alis12": b["son12"], "fatura12": b["fatura12"]})
        items.sort(key=lambda x: ({"matbaa": 0, "kagit": 1}.get(x["tur"], 2), -x["bakiye"], x["unvan"]))
        unmapped = [{"matbaa": p, **m} for p, m in mapping.items() if not m.get("cari")]
        return {"items": items, "eslesme": mapping, "eslesmeyen": unmapped,
                "ozelKodlar": lg.get("specodes") or [], "ayar": {"matbaa": s["printerSpecodes"], "kagit": s["paperSpecodes"],
                                                                  "onEk": s["supplierPrefix"]},
                "logo": self.logo_meta(snap, now), "fifoNotu": FIFO_NOTE, "uyarilar": snap["warnings"]}

    def asof(self, snap: dict[str, Any], now: date) -> date:
        de = snap["logo"].get("dataEnd")
        if self.settings()["agingAsOf"] == "veri-sonu" and isinstance(de, date):
            return de
        return now

    def logo_meta(self, snap: dict[str, Any], now: date) -> Optional[dict[str, Any]]:
        lg = snap["logo"]
        if not lg.get("ok"):
            return None
        de = lg.get("dataEnd")
        return {"firma": lg["firm"], "yil": lg["year"], "veriSonu": de.isoformat() if isinstance(de, date) else None,
                "yaslandirmaTarihi": self.asof(snap, now).isoformat()}

    def supplier(self, engine: Any, tenant: str, code: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        snap = self.snap(engine, tenant, fresh, now)
        lg = snap["logo"]
        if not lg.get("ok"):
            raise store.SupplyError("Logo'ya şu an ulaşılamıyor; tedarikçi sayfası açılamıyor.", 503)
        sp = next((x for x in lg["suppliers"] if x["kod"] == code), None)
        if sp is None:
            raise store.SupplyError("Tedarikçi carisi bulunamadı.", 404)
        mapping = self.mapping(engine, tenant, snap)
        printers = [p for p, m in mapping.items() if m.get("cari") == code]
        ag = aging(sp["bakiye"], [x for x in lg["planLines"] if x["ref"] == sp["ref"]], self.asof(snap, now))
        jobs = [card_brief(c, snap["tech"], True) for c in snap["cards"]
                if c.get("printer") in printers and c.get("stage") in LOAD_STAGES + ("yolda",)]
        jobs.sort(key=lambda x: (x.get("planBaski") or "9999", x.get("kitap") or ""))
        done = [dict(card_brief(c, snap["tech"], True), depo=((c.get("actual") or {}).get("depo") or {}).get("day"))
                for c in snap["cards"] if c.get("printer") in printers and c.get("stage") == "tamam"]
        done.sort(key=lambda x: x.get("depo") or "", reverse=True)
        stats = [x for x in self.printer_stats(snap["cards"], now) if x["printer"] in printers]
        firms = src.firms_between({int(k): v for k, v in lg["firms"].items()}, src.window_start(now, 12), now)
        try:
            invoices = src.read_supplier_invoices(self.source.logo_runner(), firms, code, src.window_start(now, 12))
        except src.SourceError as e:
            log.warning("supply: tedarikçi faturaları okunamadı: %s", e)
            invoices = []
        buys = purchases_by_supplier([x for x in lg["purchases"] if x["cariKod"] == code], now).get(code)
        kind = lg["kinds"].get(code) or {"tur": "diger", "kaynak": ""}
        return {"kod": code, "unvan": sp["unvan"], "ozelKod": sp["ozelKod"], "tur": kind["tur"], "turKaynak": kind["kaynak"],
                "crmMatbaa": printers, "yaslandirma": ag, "alis": buys, "faturalar": invoices, "acikIsler": jobs,
                "bitenIsler": done, "karne": stats, "logo": self.logo_meta(snap, now), "fifoNotu": FIFO_NOTE}

    def payments(self, engine: Any, tenant: str, days: int, kind: str = "", fresh: bool = False,
                 now: Optional[date] = None) -> dict[str, Any]:
        """Önümüzdeki `days` gün içinde vadesi gelen açık (FIFO) ödeme satırları ve vadesi geçmiş toplam."""
        now = now or today()
        snap = self.snap(engine, tenant, fresh, now)
        lg = snap["logo"]
        if not lg.get("ok"):
            raise store.SupplyError("Logo'ya şu an ulaşılamıyor; ödeme listesi hazırlanamıyor.", 503)
        asof = self.asof(snap, now)
        mapping = self.mapping(engine, tenant, snap)
        mapped_codes = {m["cari"] for m in mapping.values() if m.get("cari")}
        lines_by: dict[int, list[dict[str, Any]]] = {}
        for ln in lg["planLines"]:
            lines_by.setdefault(ln["ref"], []).append(ln)
        rows, overdue = [], []
        for sp in lg["suppliers"]:
            k = (lg["kinds"].get(sp["kod"]) or {}).get("tur", "diger")
            if k == "diger" and sp["kod"] in mapped_codes:
                k = "matbaa"
            if kind and k != kind:
                continue
            ag = aging(sp["bakiye"], lines_by.get(sp["ref"], []), asof)
            for ln in ag["acikSatir"]:
                if ln["gun"] <= 0 and -ln["gun"] <= days:
                    rows.append({"kod": sp["kod"], "unvan": sp["unvan"], "tur": k, **ln})
            if ag["vadesiGecmis"] > 0:
                overdue.append({"kod": sp["kod"], "unvan": sp["unvan"], "tur": k, "vadesiGecmis": ag["vadesiGecmis"],
                                "plansiz": ag["plansiz"], "kovalar": {x: ag[x] for x, _, _ in PAST}})
        rows.sort(key=lambda r: (r["vade"], r["unvan"]))
        overdue.sort(key=lambda r: -r["vadesiGecmis"])
        by_week: dict[str, float] = {}
        for r in rows:
            v = date.fromisoformat(r["vade"])
            wk = (v - timedelta(days=v.weekday())).isoformat()
            by_week[wk] = round(by_week.get(wk, 0.0) + r["acik"], 2)
        return {"gun": days, "tur": kind or None, "satirlar": rows, "toplam": round(sum(r["acik"] for r in rows), 2),
                "haftalik": [{"hafta": k, "tutar": v} for k, v in sorted(by_week.items())],
                "vadesiGecmis": overdue, "vadesiGecmisToplam": round(sum(r["vadesiGecmis"] for r in overdue), 2),
                "logo": self.logo_meta(snap, now), "fifoNotu": FIFO_NOTE}

    # ---- faturası görünmeyen
    def unbilled(self, engine: Any, tenant: str, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        s = self.settings()
        snap = self.snap(engine, tenant, fresh, now)
        lg = snap["logo"]
        since = parse_day(snap["since"]) or date(now.year - 2, 1, 1)
        lag = invoice_lag(snap["cards"])
        grace = lag["gun"] if lag["gun"] is not None else s["unbilledGraceDays"]
        by_line, linked_cards = self.linked(engine, tenant)
        cards = unbilled(snap["cards"], snap["tech"], linked_cards, now, grace, since + timedelta(days=60))
        out: dict[str, Any] = {"kartlar": cards, "bekleme": {"gun": grace, "kaynak": "veri" if lag["gun"] is not None else "ayar",
                                                           **lag}, "logo": self.logo_meta(snap, now), "uyarilar": snap["warnings"]}
        if lg.get("ok"):
            mapping = self.mapping(engine, tenant, snap)
            win = src.window_start(now, 12)
            out["faturalar"] = unmatched_invoices(snap["rawCards"], lg["invoices"], self.match_costs, by_line, win)
            out["aylik"] = monthly_billing(snap["cards"], lg["invoices"], self.code_of_printer(mapping), months_back(now, 6) + [mkey(now)])
        else:
            out["faturalar"], out["aylik"] = [], []
        return out

    # ---- maliyet
    def cost(self, engine: Any, tenant: str, kirilim: str = "", fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        s = self.settings()
        snap = self.snap(engine, tenant, fresh, now)
        k = kirilim if kirilim in ("cilt", "sayfa", "baski-tipi", "matbaa") else "hepsi"
        out = cost_trend(snap["cards"], snap["tech"], snap["options"], now, s["trendMonths"], k, s["pageBands"])
        out["kagit"] = paper_price_trend(snap["logo"].get("paperRows") or [], now, s["trendMonths"]) if snap["logo"].get("ok") else []
        out["uyarilar"] = snap["warnings"]
        return out

    # ---- depo uyumu
    def incoming(self, engine: Any, tenant: str, months: int = 6, fresh: bool = False, now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        snap = self.snap(engine, tenant, fresh, now)
        out = incoming(snap["cards"], (snap["logo"].get("receipts") or {}) if snap["logo"].get("ok") else {}, now, months, 12)
        out["depo"] = depot_capacity()
        return out

    # ---- özet
    def overview(self, engine: Any, tenant: str, *, debt: bool, cost: bool, fresh: bool = False,
                 now: Optional[date] = None) -> dict[str, Any]:
        now = now or today()
        s = self.settings()
        snap = self.snap(engine, tenant, fresh, now)
        table = load_table(snap["cards"], snap["tech"], store.list_capacity(engine, tenant), now, s["loadMonths"],
                           s["overloadRatio"])
        conf_ = conflicts(table)
        paper = paper_need(snap["cards"], snap["tech"], snap["paperNames"], now, 1, s["paperMeasure"])
        this_month = mkey(now)
        out: dict[str, Any] = {
            "asOf": datetime.fromtimestamp(snap["at"], TZ).isoformat(timespec="seconds"), "today": now.isoformat(),
            "yuk": {"aylar": table["aylar"], "toplam": table["toplam"],
                    "satirlar": [{"matbaa": r["matbaa"], "referans": r["referans"], "kapasiteVar": r["kapasiteVar"],
                                  "hucreler": {k: {kk: vv for kk, vv in v.items() if kk != "cards"} for k, v in r["hucreler"].items()}}
                                 for r in table["satirlar"]],
                    "acikIs": sum(v["jobs"] for v in table["toplam"].values()),
                    "acikAdet": round(sum(v["adet"] for v in table["toplam"].values()), 2)},
            "cakisma": len(conf_), "cakismaAsim": sum(1 for c in conf_ if c["durum"] == "asim"),
            "kagit": {"buAyKg": round(sum(r["kg"] for r in paper["satirlar"] if r["ay"] in (this_month, OVERDUE)), 2),
                      "olcu": paper["olcu"], "kapsam": paper["kapsam"]},
            "plan": self.demand(engine, tenant, snap),
            "oneri": sum(1 for x in store.list_suggestions(engine, tenant, durum="bekliyor")),
            "logo": self.logo_meta(snap, now), "uyarilar": snap["warnings"], "db": snap["db"],
        }
        if debt and snap["logo"].get("ok"):
            p = self.payments(engine, tenant, 30, "", False, now)
            focus = [r for r in p["satirlar"] if r["tur"] in ("matbaa", "kagit")]
            out["odeme30"] = {"toplam": round(sum(r["acik"] for r in focus), 2), "satir": len(focus),
                              "vadesiGecmis": round(sum(r["vadesiGecmis"] for r in p["vadesiGecmis"] if r["tur"] in ("matbaa", "kagit")), 2),
                              "fifoNotu": FIFO_NOTE}
            ub = self.unbilled(engine, tenant, False, now)
            out["faturasiz"] = {"kart": len(ub["kartlar"]), "fatura": len(ub["faturalar"])}
        if cost:
            ct = cost_trend(snap["cards"], snap["tech"], snap["options"], now, 12, "hepsi", s["pageBands"])
            g = ct["gruplar"][0] if ct["gruplar"] else None
            out["maliyet"] = {"aylar": ct["aylar"], "seri": (g or {}).get("aylar") or {}, "egilim": (g or {}).get("egilim"),
                              "sonDonem": (g or {}).get("sonDonem"), "oncekiDonem": (g or {}).get("oncekiDonem")}
        return out


def plan_change_summary(changes: list[dict[str, Any]], cards: list[dict[str, Any]], options: dict[str, dict[int, str]],
                        now: date) -> dict[str, Any]:
    """Son 12 ayın baskı planı değişiklikleri: sebep dağılımı, açık kart başına değişiklik sayısı, karta bağlanamayan."""
    since = src.window_start(now, 12)
    open_ids = {c["id"] for c in cards if c.get("stage") in LOAD_STAGES}
    reasons: dict[str, int] = {}
    per_card: dict[str, int] = {}
    unlinked = total = 0
    labels = options.get("new_degisikliksebebi") or src.CHANGE_REASONS
    for ch in changes:
        d = src.day(ch.get("tarih"))
        if not d or d < since:
            continue
        total += 1
        label = labels.get(ch.get("sebep") or -1) or ("Sebep girilmemiş" if ch.get("sebep") is None else f"Kod {ch['sebep']}")
        reasons[label] = reasons.get(label, 0) + 1
        if ch.get("kart") in open_ids:
            per_card[ch["kart"]] = per_card.get(ch["kart"], 0) + 1
        elif not ch.get("kart"):
            unlinked += 1
    return {"toplam": total, "sebepler": sorted(({"sebep": k, "adet": v} for k, v in reasons.items()), key=lambda x: -x["adet"]),
            "acikKartDegisiklik": per_card, "kartsiz": unlinked}
