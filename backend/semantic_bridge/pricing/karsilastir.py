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
        row: dict[str, Any] = {
            "code": code, "name": b.get("name") or code, "author": b.get("author"), "publisher": b.get("publisher"),
            "library": b.get("library"), "firstPub": b.get("firstPub"), "firstPrint": pr[0]["date"] if pr else None,
            "lastPrint": pr[-1]["date"] if pr else None, "pages": D.book_pages(snap, code), "price": price,
            "new": _is_new(b, pr, since), "sold2y": s2["qty"], "net2y": s2["net"],
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
    return {"rows": rows, "dataEnd": end, "asOf": snap.get("asOf"), "since": since, "kur": kur,
            "targetMargin": defaults.get("targetMargin"), "seconds": round(time.monotonic() - t0, 1)}


def fingerprint(snap: dict, defaults: dict, tariff: dict, kur: Optional[dict], freelance: dict, market: dict) -> str:
    """Toplu hesabın girdilerinin özeti: biri değişince (veri yenilendi, varsayılan/fiyat listesi/kur değişti, pazar fiyatı
    ya da serbest çalışan işi eklendi) liste yeniden hesaplanır."""
    raw = json.dumps([snap.get("asOf"), snap.get("dataEnd"), {k: v for k, v in defaults.items() if k not in ("updatedAt", "updatedBy")},
                      {k: v for k, v in tariff.items() if k not in ("updatedAt", "updatedBy")}, kur, freelance, market],
                     sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class Cache:
    """Toplu hesabın süreç içi önbelleği. Hesap arka planda koşar; biterken girdiler değiştiyse bir tur daha."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: Optional[str] = None
        self._result: Optional[dict] = None
        self._running: Optional[str] = None
        self._error: Optional[str] = None
        self._started: Optional[float] = None

    def get(self, key: str, compute: Callable[[], dict]) -> dict[str, Any]:
        """Bu girdilerin sonucu hazırsa o; değilse hesap başlatılır ve (varsa) önceki sonuç «eski» diye döner."""
        with self._lock:
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
            with self._lock:
                self._key, self._result = key, res
        except Exception as e:  # noqa: BLE001 — hata ekranda düz cümleyle gösterilir, önceki sonuç kalır
            log.exception("pricing: eski kitap karşılaştırması hesaplanamadı")
            with self._lock:
                self._error = f"Karşılaştırma hesaplanamadı ({type(e).__name__})."
        finally:
            with self._lock:
                self._running = None


STATUS = ("zam", "yuksek", "esit", "hesaplanamadi")


def select(res: dict, *, q: str = "", status: str = "", new: bool = False, min_sold: float = 0.0,
           sort: str = "diffPct") -> dict[str, Any]:
    """Süzgeç + sıra + özet. Özet sayıları süzgeçten sonraki (durum hariç) kümeden: sekmeler durum başına sayıyı gösterir."""
    needle = D.fold((q or "").strip())
    base = []
    for r in res["rows"]:
        if not new and r["new"]:
            continue
        if (r.get("sold2y") or 0) < min_sold:
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
        "name": lambda r: D.fold(r["name"]),
    }
    rows.sort(key=keys.get(sort, keys["diffPct"]))
    priced = [r for r in base if r.get("diffPct") is not None]
    return {"rows": rows, "count": len(rows), "total": len(base), "counts": counts,
            "avgDiffPct": round(sum(r["diffPct"] for r in priced) / len(priced), 4) if priced else None,
            "newHidden": 0 if new else sum(1 for r in res["rows"] if r["new"])}
