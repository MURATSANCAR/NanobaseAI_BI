"""M9 veri katmanı: Logo + CRM okumasından kalıcı anlık görüntü ve onun üstündeki saf hesaplar.

Anlık görüntü (`snapshot.json`) arka planda kurulur (açılışta ve `PRICING_REFRESH_SECONDS`, varsayılan 6 saatte bir;
ekrandan elle de). Ekran istekleri Logo'ya gitmez, görüntüden cevaplanır. Kurulum yarıda kalırsa önceki görüntü kalır.
Buradaki fonksiyonların hepsi görüntü sözlüğü üstünde çalışır; test yapay görüntüyle yapılır.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from semantic_bridge.pricing import model as M
from semantic_bridge.pricing import sources as SRC
from semantic_layer.firm_scope import firm_in_scope

log = logging.getLogger("semantic.pricing")

REFRESH_SECONDS = int(os.environ.get("PRICING_REFRESH_SECONDS", "21600"))
QUERY_TIMEOUT = int(os.environ.get("PRICING_QUERY_TIMEOUT_SEC", "900"))
MAX_ROWS = 2_000_000

#: Emsal penceresi: sayfa sayısı ±%20, son 12 ay baskı (enflasyonda eski baskı fiyatı bugünü anlatmaz).
PAGE_BAND = 0.20
COMPARABLE_MONTHS = 12
#: Fiziksel kâğıt hesabında fire (baskı ve kesim payı) — ölçülemediği için varsayım, ekranda değiştirilir.
PAPER_WASTE = 0.10
#: Kapak kartonunun alanı ≈ iki sayfa + sırt + kulak payı; iç sayfa alanının katı (varsayım).
COVER_AREA_FACTOR = 2.3
DEFAULT_TRIM = (13.5, 21.0)
DEFAULT_GSM = 60.0
COVER_GSM = 230.0

ROYALTY_BASIS = {1: "kapak", 2: "net", 3: "kapak"}                 # Brüt / Net / Değişken net-brüt
ROYALTY_ON = {1: "baski", 4: "baski", 5: "baski", 2: "satis", 6: "satis", 7: "satis", 8: "satis", 3: "tek"}


def cache_dir() -> Path:
    root = Path(os.environ.get("PRICING_DATA_DIR", "/data/nanobaseai/bi/var/pricing"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _save(path: Path, value: dict) -> None:
    tmp = path.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("x") as f:
            json.dump(value, f, ensure_ascii=False, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _i(v: Any) -> Optional[int]:
    x = _f(v)
    return None if x is None else int(round(x))


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _day(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    s = str(v)[:10]
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else None


def fold(text: Optional[str]) -> str:
    """Türkçe büyük/küçük harf duyarsız arama anahtarı (İ→i, I→ı)."""
    return (text or "").replace("İ", "i").replace("I", "ı").lower()


def _lower(rows: list[dict]) -> list[dict]:
    return [{str(k).lower(): v for k, v in r.items()} for r in rows]


# ------------------------------------------------------------------ anlık görüntü kurulumu

class Builder:
    """`run(connection, sql)` → satırlar. Bağlantı açma işini çağıran verir (köprüde salt okunur bağlantılar)."""

    def __init__(self, run: Callable[[str, str], list[dict]]):
        self.run = run
        self.stats: dict[str, dict] = {}
        self.warnings: list[str] = []

    def _q(self, sid: str, connection: str, sql: str, key: Optional[str] = None) -> list[dict]:
        t = time.monotonic()
        rows = _lower(self.run(connection, sql))
        st = self.stats.setdefault(key or sid, {"rows": 0, "ms": 0, "sql": []})
        st["rows"] += len(rows)
        st["ms"] += int((time.monotonic() - t) * 1000)
        st["sql"].append(sql)
        return rows

    def copies(self) -> list[dict]:
        """Logo yıl kopyaları, ölçülerek: fatura tarih aralığı START_YEAR'a değenler; örtüşen kopyadan faturası çok olan."""
        found = []
        for r in self._q("logo_kopya", "logo", SRC.LOGO_COPIES_SQL):
            firm = str(r.get("firma") or "")
            if not re.match(r"^\d{3}$", firm) or not firm_in_scope(firm):
                continue          # başka şirketin / test firmasının kopyası ölçülmez (SEMANTIC_FIRMS)
            rng = self._q("logo_kopya", "logo", SRC.LOGO_COPY_RANGE_SQL.format(f=firm))
            if not rng or not rng[0].get("son"):
                continue
            first, last = _day(rng[0]["ilk"]), _day(rng[0]["son"])
            if not first or not last or last < f"{SRC.START_YEAR}-01-01":
                continue
            found.append({"firm": firm, "first": first, "last": last, "invoices": _i(rng[0].get("fatura")) or 0})
        found.sort(key=lambda c: c["first"])
        chosen: list[dict] = []
        for c in found:
            if chosen and c["first"] <= chosen[-1]["last"]:
                keep = max(chosen[-1], c, key=lambda x: x["invoices"])
                drop = c if keep is chosen[-1] else chosen[-1]
                self.warnings.append(f"Logo'da {drop['firm']} ve {keep['firm']} kopyaları aynı dönemi taşıyor; "
                                     f"{keep['firm']} okundu (fatura sayısı fazla olan).")
                chosen[-1] = keep
            else:
                chosen.append(c)
        for c in chosen:
            c["from"] = max(c["first"], f"{SRC.START_YEAR}-01-01")
            c["to"] = (date.fromisoformat(c["last"]) + timedelta(days=1)).isoformat()
        return chosen

    def build(self) -> dict[str, Any]:
        started = time.time()
        copies = self.copies()
        if not copies:
            raise RuntimeError("Logo'da okunacak yıl kopyası bulunamadı.")
        data_end = max(c["last"] for c in copies)
        end_d = date.fromisoformat(data_end)
        ymd = lambda d: d.replace("-", "")  # noqa: E731

        prints: dict[str, list[dict]] = {}
        sales: dict[str, dict[str, dict]] = {}
        for c in copies:
            a, b = ymd(c["from"]), ymd(c["to"])
            for r in self._q("logo_baski", "logo", SRC.logo_sql("logo_baski", c["firm"], a, b)):
                code, qty, cost = _s(r.get("kod")), _f(r.get("adet")) or 0, _f(r.get("tutar")) or 0
                if not code or qty <= 0:
                    continue
                prints.setdefault(code, []).append({"date": _day(r.get("tarih")), "invoice": _s(r.get("fatura")),
                                                    "printer": _s(r.get("matbaa")), "qty": qty,
                                                    "cost": round(cost, 2), "unit": round(cost / qty, 4), "firm": c["firm"]})
            for r in self._q("logo_satis", "logo", SRC.logo_sql("logo_satis", c["firm"], a, b)):
                code, year = _s(r.get("kod")), _i(r.get("yil"))
                if not code or not year:
                    continue
                y = sales.setdefault(code, {}).setdefault(str(year), {"qty": 0.0, "net": 0.0, "gross": 0.0, "cogs": 0.0,
                                                                      "costedQty": 0.0, "soldQty": 0.0})
                for k, col in (("qty", "adet"), ("net", "net"), ("gross", "brut"), ("cogs", "maliyet"),
                               ("costedQty", "maliyetli_adet"), ("soldQty", "satis_adet")):
                    y[k] = round(y[k] + (_f(r.get(col)) or 0), 4)
        for rows in prints.values():
            rows.sort(key=lambda p: (p["date"] or "", p["invoice"] or ""))

        # Son 12 ay kanal iskontosu ve son 6 ay kâğıt fiyatı: pencere veri sonuna göre (donmuş kopyada da doğru pencere).
        ch_start = (end_d - timedelta(days=365)).isoformat()
        pp_start = (end_d - timedelta(days=183)).isoformat()
        chan: dict[str, dict] = {}
        paper_items: dict[str, dict] = {}
        freight = 0.0
        for c in copies:
            if c["to"] <= ch_start:
                continue
            a, b = ymd(max(c["from"], ch_start)), ymd(c["to"])
            for r in self._q("logo_kanal", "logo", SRC.logo_sql("logo_kanal", c["firm"], a, b)):
                k = _s(r.get("kanal")) or "Grup kodu boş"
                x = chan.setdefault(k, {"channel": k, "gross": 0.0, "net": 0.0, "qty": 0.0, "rows": 0})
                x["gross"] += _f(r.get("brut")) or 0
                x["net"] += _f(r.get("net")) or 0
                x["qty"] += _f(r.get("adet")) or 0
                x["rows"] += _i(r.get("satir")) or 0
            for r in self._q("logo_nakliye", "logo", SRC.logo_sql("logo_nakliye", c["firm"], a, b)):
                freight += _f(r.get("tutar")) or 0
            if c["to"] > pp_start:
                a2 = ymd(max(c["from"], pp_start))
                for r in self._q("logo_kagit", "logo", SRC.logo_sql("logo_kagit", c["firm"], a2, b)):
                    code = _s(r.get("kod"))
                    if not code:
                        continue
                    x = paper_items.setdefault(code, {"code": code, "name": _s(r.get("ad")), "qty": 0.0, "amount": 0.0,
                                                      "rows": 0, "last": None})
                    x["qty"] += _f(r.get("miktar")) or 0
                    x["amount"] += _f(r.get("tutar")) or 0
                    x["rows"] += _i(r.get("satir")) or 0
                    x["last"] = max(filter(None, [x["last"], _day(r.get("son"))]), default=None)
        kur: dict[str, Any] = {}
        try:
            for r in self._q("logo_kur", "logo", SRC.logo_sql("logo_kur", copies[-1]["firm"], "", ymd(copies[-1]["to"]))):
                cur = {1: "USD", 20: "EUR"}.get(_i(r.get("tur")) or 0)
                rate = _f(r.get("satis")) or _f(r.get("alis"))
                if cur and rate and rate > 0:
                    kur[cur] = {"rate": round(rate, 4), "date": _day(r.get("tarih"))}
        except Exception as e:  # noqa: BLE001 — kur tablosu yoksa maliyet formu tarifedeki kuru kullanır
            self.warnings.append(f"Logo günlük kur tablosu okunamadı ({type(e).__name__}); maliyet formu tarifedeki kuru kullanır.")
        channels = channel_table(list(chan.values()))
        net12 = sum(ch["net"] for ch in channels)

        labels: dict[str, dict[str, str]] = {}
        for r in self._q("crm_secenek", "crm", SRC.crm_sql("crm_secenek")):
            key = f"{r.get('varlik')}.{str(r.get('alan') or '').lower()}"
            labels.setdefault(key, {}).setdefault(str(_i(r.get("deger"))), _s(r.get("ad")) or "")

        books: dict[str, dict] = {}
        for r in self._q("crm_kitap", "crm", SRC.crm_sql("crm_kitap")):
            code = _s(r.get("kod"))
            if not code or code in books:
                continue
            books[code] = {
                "id": str(r.get("id") or "").lower() or None, "name": _s(r.get("ad")), "code": code,
                "pages": _i(r.get("sayfa")), "trim": _s(r.get("ebat")), "price": _f(r.get("fiyat")),
                "vat": _f(r.get("kdv")), "author": _s(r.get("yazar")), "publisher": _s(r.get("yayinevi")),
                "library": _s(r.get("kitaplik")), "firstPub": _day(r.get("ilk_yayin")),
                "royalty": royalty_of(r, labels),
            }
        crm_prints: dict[str, list[dict]] = {}
        for r in self._q("crm_baski", "crm", SRC.crm_sql("crm_baski")):
            code = _s(r.get("kod"))
            if not code:
                continue
            crm_prints.setdefault(code, []).append({
                "id": str(r.get("id") or "").lower() or None, "no": _i(r.get("baski_no")), "year": _i(r.get("yil")), "date": _day(r.get("tarih")) or _day(r.get("depo")),
                "qty": _i(r.get("adet")), "price": _f(r.get("fiyat")), "suggestedQty": _i(r.get("oneri_adet")),
                "pages": _i(r.get("sayfa")), "binding": _label(labels, "new_uretim.new_ciltlemesekli", r.get("cilt")),
                "type": _label(labels, "new_uretim.new_baskitipi", r.get("baski_tipi")), "gsm": _f(r.get("gramaj")),
                "colors": _f(r.get("renk")), "printer": _label(labels, "new_uretim.new_matbaa", r.get("matbaa"))})
        for rows in crm_prints.values():
            rows.sort(key=lambda p: ((p["no"] or 0), p["date"] or ""))

        return {
            "version": 1, "asOf": datetime.now(timezone.utc).isoformat(), "durationMs": int((time.time() - started) * 1000),
            "dataEnd": data_end, "copies": copies, "books": books, "prints": prints, "crmPrints": crm_prints,
            "sales": sales, "channels": channels, "paper": paper_table(list(paper_items.values())), "kur": kur,
            "distribution": {"freight": round(freight, 2), "net": round(net12, 2),
                             "rate": round(freight / net12, 4) if net12 > 0 else None, "from": ch_start, "to": data_end},
            "labels": labels, "sources": {k: {"rows": v["rows"], "ms": v["ms"]} for k, v in self.stats.items()},
            "sql": {k: v["sql"] for k, v in self.stats.items()}, "warnings": self.warnings,
        }


def _label(labels: dict, key: str, value: Any) -> Optional[str]:
    v = _i(value)
    if v is None:
        return None
    return (labels.get(key) or {}).get(str(v)) or f"Kod {v}"


def royalty_of(r: dict, labels: dict) -> Optional[dict]:
    rate = _f(r.get("telif"))
    kind = _i(r.get("telif_tipi"))
    basis = _i(r.get("telif_turu"))
    if rate is None and kind is None:
        return None
    on = ROYALTY_ON.get(kind or 0, "satis")
    cur_code = _i(r.get("avans_para"))
    # Para birimi seçeneği 1 = TL (CRM StringMap, 2026-09-28); boşsa da TL.
    cur = ((labels.get("new_sozlesme.new_sozlesmeparabirimi") or {}).get(str(cur_code))
           or ("TL" if cur_code in (None, 1) else f"Kod {cur_code}"))
    return {"rate": (rate or 0) / 100.0, "basis": ROYALTY_BASIS.get(basis or 0, "kapak"),
            "basisLabel": _label(labels, "new_sozlesme.new_telifturu", basis), "on": on,
            "kindLabel": _label(labels, "new_sozlesme.new_teliftipi", kind),
            "advance": _f(r.get("avans")) or 0.0, "currency": cur}


def channel_table(rows: list[dict]) -> list[dict]:
    total = sum(max(0.0, r["net"]) for r in rows)
    out = []
    for r in rows:
        if r["gross"] <= 0:
            continue
        out.append({**{k: round(v, 2) if isinstance(v, float) else v for k, v in r.items()},
                    "discount": round(1 - r["net"] / r["gross"], 4),
                    "share": round(max(0.0, r["net"]) / total, 4) if total else 0.0})
    out.sort(key=lambda x: -x["net"])
    return out


_PAPER = re.compile(r"(\d{2,3})\s*GR", re.I)


def paper_table(items: list[dict]) -> dict[str, Any]:
    """Kâğıt kartları → cins ve gramaj (kart adından), ₺/kg. Bandrol adet başına."""
    rows, bandrol = [], None
    for x in items:
        name = (x.get("name") or "").upper()
        if x["qty"] <= 0:
            continue
        unit = x["amount"] / x["qty"]
        if "BANDROL" in name:
            bandrol = {"code": x["code"], "name": x["name"], "unit": round(unit, 4), "qty": x["qty"], "last": x["last"]}
            continue
        m = _PAPER.search(name)
        kind = ("kapak" if any(w in name for w in ("BRİSTOL", "BRISTOL", "KUŞE", "KUSE")) else "ic")
        rows.append({"code": x["code"], "name": x["name"], "gsm": float(m.group(1)) if m else None, "kind": kind,
                     "kg": round(x["qty"], 2), "amount": round(x["amount"], 2), "perKg": round(unit, 4), "last": x["last"]})
    rows.sort(key=lambda r: -r["amount"])

    def avg(sel) -> Optional[float]:
        kg = sum(r["kg"] for r in sel)
        return round(sum(r["amount"] for r in sel) / kg, 4) if kg else None

    inner = [r for r in rows if r["kind"] == "ic"]
    by_gsm: dict[str, float] = {}
    for g in sorted({r["gsm"] for r in inner if r["gsm"]}):
        v = avg([r for r in inner if r["gsm"] == g])
        if v:
            by_gsm[str(int(g))] = v
    return {"items": rows, "innerPerKg": avg(inner), "innerByGsm": by_gsm,
            "coverPerKg": avg([r for r in rows if r["kind"] == "kapak"]), "bandrol": bandrol}


# ------------------------------------------------------------------ saf hesaplar

_TRIM = re.compile(r"(\d+(?:[.,]\d+)?)\s*[x*×X]\s*(\d+(?:[.,]\d+)?)")


def parse_trim(text: Optional[str]) -> Optional[tuple[float, float]]:
    m = _TRIM.search(text or "")
    if not m:
        return None
    w, h = (float(g.replace(",", ".")) for g in m.groups())
    if not (5 <= w <= 60 and 5 <= h <= 60):
        return None
    return (w, h)


def paper_cost(snap: dict, pages: float, trim: Optional[tuple[float, float]], gsm: Optional[float],
               waste: float = PAPER_WASTE) -> dict[str, Any]:
    """Bir kitabın kâğıt maliyeti (adet başına): iç kâğıt kg × ₺/kg + kapak kartonu + bandrol.
    kg = yaprak (sayfa/2) × sayfa alanı (m²) × gramaj (g/m²) / 1000 × (1 + fire)."""
    paper = snap.get("paper") or {}
    w, h = trim or DEFAULT_TRIM
    g = gsm or DEFAULT_GSM
    area = w * h / 10000.0
    inner_kg = (pages / 2.0) * area * g / 1000.0 * (1 + waste)
    per_kg = (paper.get("innerByGsm") or {}).get(str(int(g))) or paper.get("innerPerKg")
    cover_kg = area * COVER_AREA_FACTOR * COVER_GSM / 1000.0 * (1 + waste)
    cover_per = paper.get("coverPerKg")
    band = (paper.get("bandrol") or {}).get("unit")
    parts = {
        "inner": round(inner_kg * per_kg, 4) if per_kg else None,
        "cover": round(cover_kg * cover_per, 4) if cover_per else None,
        "bandrol": band,
    }
    known = [v for v in parts.values() if v is not None]
    return {"perCopy": round(sum(known), 4) if known else None, "parts": parts, "innerKg": round(inner_kg, 5),
            "coverKg": round(cover_kg, 5), "perKg": per_kg, "coverPerKg": cover_per, "gsm": g,
            "trim": [w, h], "waste": waste, "trimAssumed": trim is None, "gsmAssumed": gsm is None,
            "missing": [k for k, v in parts.items() if v is None]}


def _months_before(end: str, months: int) -> str:
    d = date.fromisoformat(end)
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, min(d.day, 28)).isoformat()


def book_pages(snap: dict, code: str) -> Optional[int]:
    cp = (snap.get("crmPrints") or {}).get(code) or []
    for p in reversed(cp):
        if p.get("pages"):
            return p["pages"]
    return ((snap.get("books") or {}).get(code) or {}).get("pages")


def latest_crm_print(snap: dict, code: str) -> Optional[dict]:
    cp = [p for p in (snap.get("crmPrints") or {}).get(code) or [] if p.get("qty") or p.get("price")]
    return cp[-1] if cp else None


def sales_summary(snap: dict, code: str, years: Optional[list[str]] = None) -> dict[str, Any]:
    ys = (snap.get("sales") or {}).get(code) or {}
    sel = {y: v for y, v in ys.items() if years is None or y in years}
    tot = {k: round(sum(v.get(k, 0) for v in sel.values()), 2) for k in ("qty", "net", "gross", "cogs", "costedQty", "soldQty")}
    tot["avgNet"] = round(tot["net"] / tot["qty"], 4) if tot["qty"] > 0 else None
    tot["unitCost"] = round(tot["cogs"] / tot["costedQty"], 4) if tot["costedQty"] > 0 else None
    tot["costCoverage"] = round(tot["costedQty"] / tot["soldQty"], 4) if tot["soldQty"] > 0 else None
    tot["profit"] = round(tot["net"] - tot["cogs"], 2) if tot["costedQty"] else None
    tot["discount"] = round(1 - tot["net"] / tot["gross"], 4) if tot["gross"] > 0 else None
    return tot


def comparables(snap: dict, pages: Optional[float], binding: Optional[str] = None, months: int = COMPARABLE_MONTHS,
                exclude: Optional[str] = None, band: float = PAGE_BAND) -> dict[str, Any]:
    """Emsal kitaplar: son `months` ayda Logo'da baskı faturası olan, sayfa sayısı ±band içinde (ve cilt şekli
    verildiyse aynı) kitaplar. Satırda son baskının adedi ve birim baskı bedeli, CRM'deki kapak fiyatı, Logo birim
    maliyeti. Özet: fiyat çeyrekleri, sayfa başına baskı bedeli eğrisi (adet → birim), birim maliyet çeyrekleri."""
    end = snap.get("dataEnd") or date.today().isoformat()
    since = _months_before(end, months)
    books = snap.get("books") or {}
    rows = []
    for code, pr in (snap.get("prints") or {}).items():
        if code == exclude:
            continue
        recent = [p for p in pr if (p.get("date") or "") >= since]
        if not recent:
            continue
        pg = book_pages(snap, code)
        if pages and (not pg or abs(pg - pages) > band * pages):
            continue
        crm = latest_crm_print(snap, code)
        if binding and (not crm or (crm.get("binding") or "") != binding):
            continue
        last = recent[-1]
        # Aynı faturada kitabın birden çok satırı birleşik geldi; aynı gün iki faturayı ayrı baskı saymayız.
        b = books.get(code) or {}
        price = (crm or {}).get("price") or b.get("price")
        s = sales_summary(snap, code, [end[:4]])
        rows.append({"code": code, "name": b.get("name") or code, "pages": pg, "binding": (crm or {}).get("binding"),
                     "printDate": last["date"], "printQty": last["qty"], "printUnit": last["unit"],
                     "printer": last.get("printer"), "price": price, "unitCost": s["unitCost"],
                     "publisher": b.get("publisher"), "library": b.get("library")})
    rows.sort(key=lambda r: r["printDate"] or "", reverse=True)
    prices = [r["price"] for r in rows if r["price"]]
    per_page = [(r["printQty"], r["printUnit"] / r["pages"]) for r in rows if r["pages"] and r["printUnit"]]
    curve = M.fit_print_curve(per_page)
    return {
        "since": since, "until": end, "pages": pages, "binding": binding, "band": band, "count": len(rows),
        "rows": rows,
        "price": {"p25": M.quantile(prices, 0.25), "median": M.quantile(prices, 0.5), "p75": M.quantile(prices, 0.75),
                  "n": len(prices)},
        "pricePerPage": M.quantile([r["price"] / r["pages"] for r in rows if r["price"] and r["pages"]], 0.5),
        "printCurvePerPage": curve,
        "unitCost": {"p25": M.quantile([r["unitCost"] for r in rows if r["unitCost"]], 0.25),
                     "median": M.quantile([r["unitCost"] for r in rows if r["unitCost"]], 0.5),
                     "p75": M.quantile([r["unitCost"] for r in rows if r["unitCost"]], 0.75)},
    }


def weighted_discount(snap: dict, mix: Optional[dict[str, float]] = None) -> Optional[float]:
    chans = snap.get("channels") or []
    if not chans:
        return None
    if mix:
        by = {c["channel"]: c for c in chans}
        use = [(by[k]["discount"], w) for k, w in mix.items() if k in by]
        tw = sum(w for _, w in use)
        return round(sum(d * w for d, w in use) / tw, 4) if tw else None
    gross = sum(c["gross"] for c in chans)
    net = sum(c["net"] for c in chans)
    return round(1 - net / gross, 4) if gross > 0 else None


def suggested_inputs(snap: dict, spec: dict, defaults: dict) -> dict[str, Any]:
    """Bir kitabın hesap girdileri için veriden öneri. Her alanın yanında nereden geldiği (`origin`) yazılır."""
    pages = _f(spec.get("pages"))
    trim = parse_trim(spec.get("trim")) if spec.get("trim") else None
    gsm = _f(spec.get("gsm"))
    comp = comparables(snap, pages, spec.get("binding") or None, exclude=spec.get("code"))
    paper = paper_cost(snap, pages or 0, trim, gsm) if pages else None
    curve = comp.get("printCurvePerPage")
    a = b = None
    if curve and pages:
        a, b = curve["a"] * pages, curve["b"] * pages
    code = spec.get("code")
    book = (snap.get("books") or {}).get(code) if code else None
    roy = (book or {}).get("royalty") or {}
    vat = _f(spec.get("vat"))
    if vat is None:
        v = (book or {}).get("vat")
        vat = (v / 100.0 if v and v > 1 else v) if v is not None else 0.0
    disc = weighted_discount(snap, defaults.get("channelMix"))
    dist = (snap.get("distribution") or {}).get("rate")
    out = {
        "printPerCopy": round((a or 0) + ((paper or {}).get("perCopy") or 0), 4) if (a or paper) else None,
        "printService": None if a is None else round(a, 4),
        "printSetup": None if b is None else round(b, 2),
        "paper": paper,
        "royaltyRate": roy.get("rate") if roy.get("on") != "tek" else 0.0,
        "royaltyBase": roy.get("basis") or "kapak",
        "royaltyOn": roy.get("on") if roy.get("on") in ("satis", "baski") else "satis",
        "advance": roy.get("advance") if (roy.get("currency") or "TL") == "TL" else 0.0,
        "advanceForeign": None if (roy.get("currency") or "TL") == "TL" else {"amount": roy.get("advance"),
                                                                              "currency": roy.get("currency")},
        "vat": vat,
        "discount": disc,
        "variableRate": dist if dist is not None else defaults.get("variableRate"),
        "sellThrough": defaults.get("sellThrough"),
        "targetMargin": defaults.get("targetMargin"),
        "origin": {
            "printService": f"{comp['count']} emsal kitabın son {COMPARABLE_MONTHS} aydaki matbaa faturası (sayfa başına, adede göre eğri)"
            if curve else "Emsal baskı faturası yok — elle girin",
            "paper": "Kâğıt: sayfa × ebat × gramaj, son 6 ayın Logo kâğıt alış fiyatı (₺/kg); fire ve kapak payı varsayım"
            if paper and paper.get("perCopy") else "Kâğıt fiyatı ölçülemedi — elle girin",
            "royalty": f"CRM sözleşmesi: {roy.get('kindLabel') or '—'}, {roy.get('basisLabel') or '—'}" if roy else "Sözleşme yok — elle girin",
            "discount": "Son 12 ayın Logo kitap satışı, kanal karmasına göre ağırlıklı iskonto" if disc is not None else "Ölçülemedi",
            "variableRate": "Son 12 ayın satış nakliye gideri ÷ kitap net satışı" if dist is not None else "Varsayılan",
            "vat": "CRM kitap kartındaki KDV oranı" if book else "Elle",
        },
        "comparables": comp,
    }
    return out


def actuals(snap: dict, *, q: str = "", since_year: Optional[int] = None, sort: str = "net") -> dict[str, Any]:
    """Gerçekleşen (Logo): kitap başına basılan adet ve baskı bedeli, satılan adet, net satış, Logo birim maliyeti,
    brüt kâr ve marj; CRM'deki güncel kapak fiyatı ve son baskı birim bedelinin fiyata oranı."""
    books = snap.get("books") or {}
    prints = snap.get("prints") or {}
    years = None if not since_year else [str(y) for y in range(int(since_year), 2100)]
    needle = fold((q or "").strip())
    rows = []
    for code in set(prints) | set(snap.get("sales") or {}):
        b = books.get(code) or {}
        name = b.get("name") or code
        if needle and needle not in fold(name) and needle not in fold(code):
            continue
        pr = [p for p in prints.get(code, []) if not years or (p.get("date") or "")[:4] in years]
        s = sales_summary(snap, code, years)
        if not pr and not s["qty"]:
            continue
        printed = sum(p["qty"] for p in pr)
        pcost = sum(p["cost"] for p in pr)
        last = (prints.get(code) or [None])[-1]
        price = b.get("price")
        vat = b.get("vat") or 0
        vat = vat / 100.0 if vat > 1 else vat
        net_price = price / (1 + vat) if price else None
        rows.append({
            "code": code, "name": name, "publisher": b.get("publisher"), "printed": printed, "printCost": round(pcost, 2),
            "printUnit": round(pcost / printed, 4) if printed else None, "lastPrintUnit": (last or {}).get("unit"),
            "lastPrintDate": (last or {}).get("date"), "sold": s["qty"], "net": s["net"], "avgNet": s["avgNet"],
            "unitCost": s["unitCost"], "cogs": s["cogs"], "profit": s["profit"],
            "margin": round(s["profit"] / s["net"], 4) if s["profit"] is not None and s["net"] > 0 else None,
            "costCoverage": s["costCoverage"], "discount": s["discount"], "price": price,
            "costToPrice": round(s["unitCost"] / net_price, 4) if s["unitCost"] and net_price else None,
        })
    key = {"net": lambda r: -(r["net"] or 0), "margin": lambda r: (r["margin"] if r["margin"] is not None else 9),
           "printed": lambda r: -(r["printed"] or 0), "costToPrice": lambda r: -(r["costToPrice"] or 0)}.get(sort)
    rows.sort(key=key or (lambda r: -(r["net"] or 0)))
    tot_net = sum(r["net"] for r in rows)
    tot_cogs = sum(r["cogs"] for r in rows if r["unitCost"])
    tot_net_costed = sum(r["net"] for r in rows if r["unitCost"])
    return {"rows": rows, "count": len(rows), "net": round(tot_net, 2), "printCost": round(sum(r["printCost"] for r in rows), 2),
            "printed": sum(r["printed"] for r in rows), "sold": round(sum(r["sold"] for r in rows), 2),
            "margin": round(1 - tot_cogs / tot_net_costed, 4) if tot_net_costed > 0 else None,
            "sinceYear": since_year, "dataEnd": snap.get("dataEnd")}


def backlist(snap: dict, *, target_ratio: Optional[float] = None, min_sold: float = 1.0, months: int = 12) -> dict[str, Any]:
    """Fiyat revizyonu adayları: son baskının Logo birim bedeli + güncel kâğıt, kapak fiyatına (KDV hariç) oranı.
    Hedef oran verilmezse son `months` ayda ilk baskısı yapılan kitapların ortanca oranı alınır (bugünkü
    fiyatlama pratiği). Oranı hedefin üstünde olan kitaba hedefi tutturan fiyat önerilir (5 ₺'ye yukarı)."""
    end = snap.get("dataEnd") or date.today().isoformat()
    since = _months_before(end, months)
    books = snap.get("books") or {}
    cands = []
    for code, pr in (snap.get("prints") or {}).items():
        b = books.get(code)
        if not b or not b.get("price") or not pr:
            continue
        last = pr[-1]
        pages = book_pages(snap, code)
        crm = latest_crm_print(snap, code)
        paper = paper_cost(snap, pages, parse_trim(b.get("trim")), (crm or {}).get("gsm")) if pages else None
        unit = last["unit"] + ((paper or {}).get("perCopy") or 0)
        vat = b.get("vat") or 0
        vat = vat / 100.0 if vat > 1 else vat
        net_price = b["price"] / (1 + vat)
        first_print = pr[0]["date"] or ""
        s12 = sales_summary(snap, code, [end[:4], str(int(end[:4]) - 1)])
        cands.append({"code": code, "name": b.get("name"), "publisher": b.get("publisher"), "price": b["price"],
                      "vat": vat, "pages": pages, "lastPrintDate": last["date"], "lastPrintQty": last["qty"],
                      "printUnit": last["unit"], "paperUnit": (paper or {}).get("perCopy"), "unit": round(unit, 4),
                      "ratio": round(unit / net_price, 4) if net_price else None, "new": first_print >= since,
                      "sold2y": s12["qty"], "avgNet": s12["avgNet"]})
    fresh = [c["ratio"] for c in cands if c["new"] and c["ratio"]]
    measured = M.quantile(fresh, 0.5)
    target = target_ratio if target_ratio else measured
    rows = []
    if target:
        for c in cands:
            if c["new"] or not c["ratio"] or c["ratio"] <= target or (c["sold2y"] or 0) < min_sold:
                continue
            proposed = M.round_price(c["unit"] / target * (1 + c["vat"]))
            if proposed <= c["price"]:
                continue
            rows.append({**c, "proposed": proposed, "increase": round(proposed / c["price"] - 1, 4)})
    rows.sort(key=lambda r: -(r["ratio"] or 0))
    return {"rows": rows, "count": len(rows), "target": target, "measuredTarget": measured, "freshBooks": len(fresh),
            "candidates": len(cands), "since": since, "dataEnd": end}


def book_detail(snap: dict, code: str) -> Optional[dict]:
    b = (snap.get("books") or {}).get(code)
    pr = (snap.get("prints") or {}).get(code) or []
    if not b and not pr:
        return None
    ys = (snap.get("sales") or {}).get(code) or {}
    by_year = [{"year": y, **v, "avgNet": round(v["net"] / v["qty"], 4) if v["qty"] > 0 else None,
                "unitCost": round(v["cogs"] / v["costedQty"], 4) if v["costedQty"] > 0 else None}
               for y, v in sorted(ys.items())]
    crm = (snap.get("crmPrints") or {}).get(code) or []
    last = latest_crm_print(snap, code)
    return {"book": b or {"code": code, "name": code}, "prints": pr, "crmPrints": crm, "salesByYear": by_year,
            "total": sales_summary(snap, code),
            "spec": {"code": code, "pages": book_pages(snap, code), "trim": (b or {}).get("trim"),
                     "gsm": (last or {}).get("gsm"), "binding": (last or {}).get("binding"),
                     "vat": ((b or {}).get("vat") or 0) / (100.0 if ((b or {}).get("vat") or 0) > 1 else 1.0)}}


def search_books(snap: dict, q: str, limit: int = 30) -> dict[str, Any]:
    needle = fold((q or "").strip())
    books = snap.get("books") or {}
    hits = []
    if needle:
        for code, b in books.items():
            name = fold(b.get("name"))
            if needle in name or needle in fold(code) or needle in fold(b.get("author")):
                hits.append((0 if name.startswith(needle) else 1, b.get("name") or "", code))
    hits.sort()
    items = [{"code": c, "name": books[c].get("name"), "author": books[c].get("author"),
              "publisher": books[c].get("publisher"), "price": books[c].get("price"), "pages": books[c].get("pages"),
              "prints": len((snap.get("prints") or {}).get(c) or [])} for _, _, c in hits[:limit]]
    return {"items": items, "total": len(hits)}


class Store:
    """Görüntünün diskteki kalıcı kopyası + arka plan yenileme. Tek süreçte tek kurucu (dosya kilidi)."""

    def __init__(self, connect: Callable[[str], Any]):
        self._connect = connect
        self._snap: Optional[dict] = None
        self._mtime = 0.0
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.stopping = threading.Event()
        self.started_at: Optional[float] = None
        self._dir_error: Optional[str] = None

    @property
    def path(self) -> Path:
        return cache_dir() / "snapshot.json"

    @property
    def meta_path(self) -> Path:
        return cache_dir() / "status.json"

    def status(self) -> dict:
        running = bool(self._thread and self._thread.is_alive())
        try:
            st = json.loads(self.meta_path.read_text())
        except FileNotFoundError:
            st = {}
        except (OSError, ValueError) as e:
            # Klasör köprü kullanıcısına yazılamıyorsa ekran nedenini düz cümleyle söyler.
            st = {"error": f"Fiyatlama veri klasörü okunamıyor ya da yazılamıyor ({type(e).__name__})."}
        if self._dir_error and not running:
            st = {**st, "error": self._dir_error}
        return {**st, "refreshing": running, "refreshStartedAt": self.started_at if running else None}

    def get(self) -> Optional[dict]:
        try:
            m = self.path.stat().st_mtime
        except OSError:
            return self._snap
        if self._snap is None or m != self._mtime:
            try:
                self._snap = json.loads(self.path.read_text())
                self._mtime = m
            except (OSError, ValueError):
                log.warning("pricing snapshot okunamadı")
        return self._snap

    def refresh(self) -> None:
        try:
            self._refresh()
            self._dir_error = None
        except OSError as e:  # veri klasörü yok/yazılamıyor: görüntü kurulamaz, ekran nedenini söyler
            log.warning("pricing: veri klasörü kullanılamıyor: %s", e)
            self._dir_error = (f"Fiyatlama veri klasörü yazılamıyor ({os.environ.get('PRICING_DATA_DIR', '/data/nanobaseai/bi/var/pricing')}); "
                               "sunucu yöneticisi klasörü köprünün kullanıcısına açmalı.")

    def _refresh(self) -> None:
        import fcntl
        with (cache_dir() / "snapshot.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            started = time.time()
            conns: dict[str, Any] = {}

            def run(name: str, sql: str) -> list[dict]:
                if name not in conns:
                    conns[name] = self._connect(name)
                _, rows, truncated = conns[name].execute(sql, MAX_ROWS)
                if truncated:
                    raise RuntimeError("Kaynak sorgusu satır sınırını aştı; görüntü eksik kalırdı.")
                return rows

            prev = self.status()
            try:
                snap = Builder(run).build()
                _save(self.path, snap)
                _save(self.meta_path, {"updatedAt": time.time(), "startedAt": started, "error": None,
                                       "durationMs": snap["durationMs"], "dataEnd": snap["dataEnd"]})
            except Exception as exc:  # noqa: BLE001 — önceki görüntü kalır
                log.warning("pricing snapshot kurulamadı: %s", exc)
                msg = str(exc)
                state = str(getattr(exc, "args", [""])[0])
                if state in ("08S01", "08001"):
                    msg = "Logo ya da CRM veritabanına şu an ulaşılamıyor."
                elif state in ("HYT00", "HYT01"):
                    msg = f"Kaynak sorgusu {QUERY_TIMEOUT} saniyede bitmedi."
                _save(self.meta_path, {**{k: prev.get(k) for k in ("updatedAt", "durationMs", "dataEnd")},
                                       "startedAt": started, "failedAt": time.time(),
                                       "error": f"Veriler yenilenemedi: {msg[:300]}"})
            finally:
                for c in conns.values():
                    try:
                        c.close()
                    except Exception:  # noqa: BLE001
                        pass

    def start_refresh(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self.started_at = time.time()
            self._thread = threading.Thread(target=self.refresh, daemon=True, name="pricing-snapshot")
            self._thread.start()
            return True

    def start(self) -> None:
        def loop():
            while not self.stopping.is_set():
                st = self.status()
                last = max(st.get("updatedAt") or 0, st.get("failedAt") or 0)
                wait = REFRESH_SECONDS if not st.get("failedAt") or (st.get("updatedAt") or 0) > (st.get("failedAt") or 0) \
                    else min(REFRESH_SECONDS, 1800)
                if time.time() - last >= wait:
                    self.start_refresh()
                self.stopping.wait(60)
        threading.Thread(target=loop, daemon=True, name="pricing-scheduler").start()
