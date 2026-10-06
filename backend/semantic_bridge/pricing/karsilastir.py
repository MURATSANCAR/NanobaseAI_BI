"""Eski kitaplar: CRM'deki güncel kapak fiyatı ↔ bizim hesapladığımız fiyat, bütün kitaplar için.

«Bizim hesap», «Kitap hesabı» sekmesinde bir kitap seçilince ekranın yaptığı zincirin aynısıdır; ekrandaki adımlar
burada sunucuda sırayla koşar, böylece iki sekme aynı kitap için aynı rakamı verir:

1. `data.book_detail` + `data.suggested_inputs`: CRM + Logo'dan kitap künyesi ve öneri girdileri (iskonto, dağıtım,
   KDV, avans).
2. `form.from_book` → `form.to_analysis`: basım Excel'indeki Kitap Maliyet Formu'nun hesabı (baskı, kâğıt, cilt,
   kapak, dolaylı gider, telif); kur fiyat listesindeki kur seçimine göre (Logo ya da elle).
3. M8 serbest çalışan tutarları (çeviri, redaksiyon) ve kitaba elle girilmiş pazar fiyatları.
4. `pricing.calculate`: hedef marja göre maliyet alt sınırı, emsal ortancası, önerilen kapak fiyatı.

Ekranın `CalcPane.tsx` (`fromSuggested` + maliyet formunun aktarımı) sırası değişirse burası da değişmelidir.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from semantic_bridge.pricing import data as D
from semantic_bridge.pricing import form as F
from semantic_bridge.pricing import store as S

log = logging.getLogger("semantic.pricing")

#: «Yeni kitap»: ilk yayını (CRM) ya da ilk matbaa faturası (Logo) son bu kadar ayda olan kitap.
NEW_MONTHS = 12


def binding_of(tur: Optional[str]) -> Optional[str]:
    """Maliyet formunun cilt adı → CRM cilt şekli (emsal süzgeci). Ekrandaki `bindingOf` ile aynı."""
    t = (tur or "").upper()
    if "SERT" in t:
        return "Sert Kapak"
    if "FLEKS" in t:
        return "Flexi Kapak Cilt"
    if "TEL" in t:
        return "Tel Dikiş"
    if "AMER" in t:
        return "Amerikan Cilt"
    return None


def book_inputs(snap: dict, code: str, *, defaults: dict, tariff: dict, kur: Optional[dict],
                freelance: dict[str, float], market: list[float], pool: list[dict]) -> dict[str, Any]:
    """Bir kitabın «Kitap hesabı» girdileri: ekranda kitap seçilip maliyet formu fiyat hesabına aktarıldığındaki hâl."""
    det = D.book_detail(snap, code)
    if not det:
        raise S.PricingError("Kitap bulunamadı.")
    sug = D.suggested_inputs(snap, det["spec"], defaults, pool=pool)
    cost = F.from_book(det, tariff, kur=kur)["inputs"]
    mapped = F.to_analysis(cost, tariff, paper_source="logo", snap_paper=snap.get("paper"))
    q = mapped["chosenQty"]
    qtys = sorted({*[int(x) for x in defaults["qtys"]], int(q)})
    inputs = {
        "printService": mapped["printService"], "paperPerCopy": mapped["paperPerCopy"], "printSetup": mapped["printSetup"],
        "overheadRate": mapped["overheadRate"],
        "fixed": {"avans": sug.get("advance") or 0, "ceviri": freelance.get("ceviri", 0), "grafik": mapped["fixed"]["grafik"],
                  "redaksiyon": freelance.get("redaksiyon", 0), "pazarlama": 0, "diger": mapped["fixed"]["diger"]},
        "royaltyRate": mapped["royaltyRate"], "royaltyBase": "kapak", "royaltyOn": "baski",
        "vat": sug.get("vat"), "discount": sug.get("discount") or 0,
        "variableRate": sug["variableRate"] if sug.get("variableRate") is not None else defaults.get("variableRate"),
        "sellThrough": defaults.get("sellThrough"), "targetMargin": defaults.get("targetMargin"),
        "qtys": qtys, "chosenQty": q, "price": mapped.get("price"),
    }
    inputs["printPerCopy"] = ((inputs["printService"] or 0) + (inputs["paperPerCopy"] or 0)) or None
    sp = det["spec"]
    spec = {**sp, "pages": cost.get("sayfa") if cost.get("sayfa") is not None else sp.get("pages"),
            "trim": cost.get("ebat") if cost.get("ebat") is not None else sp.get("trim"),
            "gsm": (cost.get("ic") or {}).get("gr") if (cost.get("ic") or {}).get("gr") is not None else sp.get("gsm"),
            "binding": binding_of((cost.get("cilt") or {}).get("tur")) or sp.get("binding")}
    return {"inputs": inputs, "spec": spec, "marketPrices": market, "detail": det}


def _is_new(b: dict, prints: list[dict], since: str) -> bool:
    first = b.get("firstPub") or ((prints[0].get("date") if prints else None) or "")
    return bool(first) and first[:10] >= since


def compare_all(snap: dict, *, defaults: dict, tariff: dict, kur: Optional[dict],
                freelance: dict[str, dict[str, float]], market: dict[str, list[float]],
                calculate: Callable[..., dict]) -> dict[str, Any]:
    """Fiyatı olan bütün kitaplar: güncel fiyat, bizim hesap, fark. Hesaplanamayan kitap listeden düşmez, nedeniyle döner.
    `freelance` ve `market` CRM kitap kimliğine (küçük harf) göre; `calculate` = `pricing.calculate`."""
    t0 = time.monotonic()
    end = snap.get("dataEnd") or date.today().isoformat()
    since = D._months_before(end, NEW_MONTHS)
    years = [end[:4], str(int(end[:4]) - 1)]
    pool = D.comparable_pool(snap)
    books = snap.get("books") or {}
    prints = snap.get("prints") or {}
    rows = []
    for code, b in books.items():
        price = b.get("price")
        if not price or price <= 0:
            continue
        pr = prints.get(code) or []
        bid = (b.get("id") or "").lower()
        s2 = D.sales_summary(snap, code, years)
        last = D.latest_crm_print(snap, code) or {}
        pages = D.book_pages(snap, code)
        pc = b.get("priceChange") or {}
        row: dict[str, Any] = {
            "code": code, "name": b.get("name") or code, "author": b.get("author"), "publisher": b.get("publisher"),
            "library": b.get("library"), "firstPub": b.get("firstPub"), "firstPrint": pr[0]["date"] if pr else None,
            "lastPrint": pr[-1]["date"] if pr else None, "pages": pages, "price": price,
            "new": _is_new(b, pr, since), "sold2y": s2["qty"], "net2y": s2["net"],
            "perPage": round(price / pages, 4) if pages else None, "stock": b.get("stock"),
            "trim": trim_of(b.get("trim")), "binding": last.get("binding") or b.get("bindingCard"),
            "color": color_of(last.get("colors")),
            "gsm": last.get("gsm"), "cover": b.get("coverNote"),
            "lastPrintDate": b.get("lastPrintDate") or last.get("date"),
            "lastPrintQty": b.get("lastPrintQty") or last.get("qty"),
            "priceChanged": pc.get("date"), "prevPrice": pc.get("prev"), "priceSince": pc.get("since"),
            "singlePay": b.get("singlePay"), "royalties": b.get("royalties") or {},
        }
        try:
            body = book_inputs(snap, code, defaults=defaults, tariff=tariff, kur=kur, freelance=freelance.get(bid, {}),
                               market=market.get(bid, []), pool=pool)
            out = calculate(snap, {k: body[k] for k in ("inputs", "spec", "marketPrices")}, pool=pool)
        except (F.FormError, S.PricingError) as e:
            rows.append({**row, "status": "hesaplanamadi", "reason": str(e)})
            continue
        rec, sm = out["recommendation"], out["summary"]
        ours = rec.get("price")
        row.update({"ours": ours, "floor": rec.get("floor"), "median": rec.get("median"), "band": rec.get("band"),
                    "unitCost": sm.get("unitCost"), "qty": sm.get("qty"), "margin": sm.get("margin"),
                    "targetMargin": sm.get("targetMargin"), "comparables": (out.get("comparables") or {}).get("count")})
        if not ours:
            rows.append({**row, "status": "hesaplanamadi", "reason": rec.get("floorReason") or "Önerilen fiyat çıkmadı."})
            continue
        diff = round(ours - price, 2)
        row.update({"diff": diff, "diffPct": round(ours / price - 1, 4),
                    "status": "zam" if diff > 0 else "yuksek" if diff < 0 else "esit"})
        rows.append(row)
    ladders = build_ladders(rows)
    for r in rows:
        r["group"] = group_key(r)
        r["ladder"] = ladder_step(ladders.get(r["group"]), r.get("pages"))
    return {"rows": rows, "dataEnd": end, "asOf": snap.get("asOf"), "since": since, "kur": kur,
            "targetMargin": defaults.get("targetMargin"), "seconds": round(time.monotonic() - t0, 1),
            "groups": [{"key": k, **g["label"], "steps": g["steps"], "books": g["books"]} for k, g in sorted(ladders.items())]}


def color_of(colors: Optional[float]) -> Optional[str]:
    """CRM üretim kaydındaki iç sayfa renk sayısı → Excel'deki «Renk» adı."""
    if colors is None:
        return None
    return "Tek renk" if colors <= 1 else "İki renk" if colors < 3 else "Renkli"


def trim_of(t: Optional[str]) -> Optional[str]:
    """CRM ebat yazımını birleştirir: «13,5*21», «13,5 X 21» → «13,5x21»."""
    if not t:
        return None
    return "x".join(p.strip() for p in t.replace("*", "x").replace("X", "x").replace("×", "x").split("x")) or None


def binding_group(name: Optional[str]) -> Optional[str]:
    """Emsal grubunda cilt: üretim kaydı ile kitap kartının farklı adları (Amerikan Cilt, SIVAMA AMERİKAN CİLT…) aynı
    cilt ailesinde birleşir. Ad tanınmazsa kendisi."""
    t = (name or "").upper().replace("İ", "I")
    if not t:
        return None
    if "SERT" in t or "BEZ" in t:
        return "Sert kapak"
    if "FLEK" in t or "FLEX" in t:
        return "Fleksi kapak"
    if "AMER" in t:
        return "Amerikan cilt"
    if "TEL" in t:
        return "Tel dikiş"
    if "IPLIK" in t:
        return "İplik dikiş"
    return name


def group_key(r: dict) -> str:
    return " · ".join(str(x or "—") for x in (r.get("publisher"), r.get("trim"), r.get("color"), binding_group(r.get("binding"))))


def build_ladders(rows: list[dict]) -> dict[str, dict]:
    """Emsal merdiveni, Fiyat Çalışması Excel'indeki «Mak Fiyat» pivotunun aynısı: yayınevi × ebat × renk × cilt grubunda
    sayfa sayısı başına en yüksek güncel kapak fiyatı (gruptaki bütün kitaplar). Basamağın kâr oranı bizim hesaptan."""
    out: dict[str, dict] = {}
    for r in rows:
        if not r.get("pages"):
            continue
        k = group_key(r)
        g = out.setdefault(k, {"label": {"publisher": r.get("publisher"), "trim": r.get("trim"), "color": r.get("color"),
                                         "binding": binding_group(r.get("binding"))}, "byPages": {}, "books": 0})
        g["books"] += 1
        cur = g["byPages"].get(r["pages"])
        if not cur or r["price"] > cur["price"]:
            g["byPages"][r["pages"]] = {"pages": r["pages"], "price": r["price"], "code": r["code"], "name": r["name"],
                                        "margin": r.get("margin"), "firstPub": (r.get("firstPub") or r.get("firstPrint") or "")[:10] or None}
    for g in out.values():
        g["steps"] = [g["byPages"][p] for p in sorted(g["byPages"])]
        del g["byPages"]
    return out


def ladder_step(g: Optional[dict], pages: Optional[int]) -> Optional[dict]:
    """Kitabın merdivendeki yeri: sayfa sayısı ≤ kitabınki olan en yakın basamak (yoksa ilk basamak) ve bir üstü."""
    if not g or not g.get("steps") or not pages:
        return None
    steps = g["steps"]
    below = [s for s in steps if s["pages"] <= pages]
    at = below[-1] if below else steps[0]
    above = next((s for s in steps if s["pages"] > at["pages"]), None)
    return {"pages": at["pages"], "price": at["price"], "code": at["code"],
            "nextPages": above["pages"] if above else None, "nextPrice": above["price"] if above else None}


#: Sonuç satırının biçimi değişince artar: diskteki eski sonuç yeni kodda «hazır» sayılmaz.
RESULT_VERSION = 4


def fingerprint(snap: dict, defaults: dict, tariff: dict, kur: Optional[dict], freelance: dict, market: dict) -> str:
    """Toplu hesabın girdilerinin özeti: biri değişince (veri yenilendi, varsayılan/fiyat listesi/kur değişti, pazar fiyatı
    ya da serbest çalışan işi eklendi) liste yeniden hesaplanır."""
    raw = json.dumps([RESULT_VERSION, snap.get("asOf"), snap.get("dataEnd"), {k: v for k, v in defaults.items() if k not in ("updatedAt", "updatedBy")},
                      {k: v for k, v in tariff.items() if k not in ("updatedAt", "updatedBy")}, kur, freelance, market],
                     sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class Cache:
    """Toplu hesabın süreç içi önbelleği. Hesap arka planda koşar; biterken girdiler değiştiyse bir tur daha."""

    def __init__(self, path: Optional[Callable[[], Path]] = None) -> None:
        self._lock = threading.Lock()
        self._key: Optional[str] = None
        self._result: Optional[dict] = None
        self._running: Optional[str] = None
        self._error: Optional[str] = None
        self._started: Optional[float] = None
        self._path = path
        self._mtime = 0.0

    def _load(self) -> None:
        """Diskteki son sonuç (köprü yeniden başlayınca liste beklemeden gelsin; ikinci işçi de aynı sonucu görsün)."""
        if not self._path:
            return
        try:
            p = self._path()
            m = p.stat().st_mtime
            if m == self._mtime:
                return
            got = json.loads(p.read_text())
            self._key, self._result, self._mtime = got.get("key"), got.get("result"), m
        except (OSError, ValueError):
            return

    def _save(self, key: str, res: dict) -> None:
        if not self._path:
            return
        try:
            D._save(self._path(), {"key": key, "result": res})
        except OSError:
            log.warning("pricing: eski kitap karşılaştırması diske yazılamadı")

    def get(self, key: str, compute: Callable[[], dict]) -> dict[str, Any]:
        """Bu girdilerin sonucu hazırsa o; değilse hesap başlatılır ve (varsa) önceki sonuç «eski» diye döner."""
        with self._lock:
            if self._running is None:
                self._load()
            if self._key == key and self._result is not None:
                return {"ready": True, "stale": False, "result": self._result}
            if self._running is None:
                self._running = key
                self._started = time.time()
                self._error = None
                threading.Thread(target=self._run, args=(key, compute), name="pricing-compare", daemon=True).start()
            return {"ready": False, "stale": self._result is not None, "result": self._result, "error": self._error,
                    "startedAt": self._started}

    def _run(self, key: str, compute: Callable[[], dict]) -> None:
        try:
            res = compute()
            self._save(key, res)
            with self._lock:
                self._key, self._result = key, res
                try:
                    self._mtime = self._path().stat().st_mtime if self._path else 0.0
                except OSError:
                    pass
        except Exception as e:  # noqa: BLE001 — hata ekranda düz cümleyle gösterilir, önceki sonuç kalır
            log.exception("pricing: eski kitap karşılaştırması hesaplanamadı")
            with self._lock:
                self._error = f"Karşılaştırma hesaplanamadı ({type(e).__name__})."
        finally:
            with self._lock:
                self._running = None


STATUS = ("zam", "yuksek", "esit", "hesaplanamadi")


def with_manual(r: dict, m: Optional[dict]) -> dict:
    """Satıra kullanıcının yazdığı yeni fiyat: artış oranı, sayfa başı yeni fiyat (Excel'deki «Zamlı Birim Fiyat»)."""
    if not m:
        return r
    p = m["price"]
    return {**r, "newPrice": p, "newPct": round(p / r["price"] - 1, 4) if r.get("price") else None,
            "newPerPage": round(p / r["pages"], 4) if r.get("pages") else None, "newBy": m.get("by"), "newAt": m.get("at")}


def select(res: dict, *, q: str = "", status: str = "", new: bool = False, min_sold: float = 0.0,
           sort: str = "diffPct", manual: Optional[dict[str, dict]] = None, entered: bool = False,
           group: str = "") -> dict[str, Any]:
    """Süzgeç + sıra + özet. Özet sayıları süzgeçten sonraki (durum hariç) kümeden: sekmeler durum başına sayıyı gösterir.
    `manual`: stok kodu → elle yeni fiyat; `entered` yalnız yeni fiyatı yazılmış kitaplar; `group` emsal grubu."""
    needle = D.fold((q or "").strip())
    manual = manual or {}
    base = []
    for r0 in res["rows"]:
        r = with_manual(r0, manual.get(r0["code"]))
        if entered and r.get("newPrice") is None:
            continue
        if group and r.get("group") != group:
            continue
        if not new and r["new"]:
            continue
        # İadesi satışından çok olan kitabın 2 yıllık adedi eksi olabilir; süzgeç yalnız yazıldığında uygulanır.
        if min_sold > 0 and (r.get("sold2y") or 0) < min_sold:
            continue
        if needle and needle not in D.fold(r["name"]) and needle not in D.fold(r["code"]) and needle not in D.fold(r.get("author")):
            continue
        base.append(r)
    counts = {s: sum(1 for r in base if r["status"] == s) for s in STATUS}
    rows = [r for r in base if not status or r["status"] == status]
    keys = {
        "diffPct": lambda r: (r.get("diffPct") is None, -(r.get("diffPct") or 0)),
        "diffPctAsc": lambda r: (r.get("diffPct") is None, r.get("diffPct") or 0),
        "sold": lambda r: -(r.get("sold2y") or 0),
        "stock": lambda r: -(r.get("stock") or 0),
        "pages": lambda r: (r.get("pages") is None, r.get("pages") or 0),
        "newPct": lambda r: (r.get("newPct") is None, -(r.get("newPct") or 0)),
        "priceChanged": lambda r: (r.get("priceChanged") or r.get("priceSince") or "9999"),
        "name": lambda r: D.fold(r["name"]),
    }
    rows.sort(key=keys.get(sort, keys["diffPct"]))
    priced = [r for r in base if r.get("diffPct") is not None]
    typed = [r for r in base if r.get("newPrice") is not None]
    return {"rows": rows, "count": len(rows), "total": len(base), "counts": counts, "entered": len(typed),
            "avgNewPct": round(sum(r["newPct"] for r in typed if r.get("newPct") is not None) / len(typed), 4) if typed else None,
            "avgDiffPct": round(sum(r["diffPct"] for r in priced) / len(priced), 4) if priced else None,
            "newHidden": 0 if new else sum(1 for r in res["rows"] if r["new"])}
