"""M43 Depo ve stok yönetimi: iş kuralları, önbellek ve gece işi.

**Ne gösterir (ilk sürüm, analiz §9):** kitap stok listesi ve kitap stok kartı (Logo bakiyesi + ambar kırılımı, CRM raf
dağılımı, satış hızı, gün cinsinden yeterlilik, bekleyen sipariş, M12 açık üretim kartı), bitecekler, fazla/hareketsiz
stok, Logo–CRM farkı ve Logo'ya aktarılamamış hareketler, sipariş hazırlık hattı; güvenlik stoku önerisi + onayı ve
gece önerileri (K2). Logo'ya (`INVDEF` dahil), CRM'e ve T-soft'a yazılmaz.

**Hesaplar (rakamı model üretmez):**

- *Satış hızı* ve *tükenme süresi* Baskı Öneri (M11) ile birebir: aynı SQL dosyası, aynı DAX bölmesi ve öneri etiketi
  (`management.baski_oneri._dax_div`, `_marj_oneri`). Tek fark stok kaynağı: Baskı Öneri CRM stok adedini böler, burada
  Logo bakiyesi bölünür (analiz §14: `gun = bakiye / (satis_hizi / 30)`); ikisi de kartta yazılıdır.
- *Yeterlilik (gün)* = bakiye ÷ (aylık satış hızı ÷ 30). Satışı olmayan kitapta yeterlilik yoktur (boş), bakiye ≤ 0 ise 0.
- *Tükenme tarihi* = Logo verisinin bittiği gün + yeterlilik. Logo kopyası donmuşken «bugün» sayılmaz; veri günü her ekranda yazar.
- *Baskı süresi* = M12'nin ölçtüğü gerçekleşen sürelerin toplamı (matbaa belirleme → dosya → baskı → depo, ortanca);
  ölçüm yoksa ayar (`STOCK_LEAD_DAYS`) ya da 45 gün (ölçülecek). *Kritik* = yeterlilik ≤ baskı süresi + güvenlik günü
  (onaylı eşik yoksa `STOCK_SAFETY_DAYS`). Logo'da asgari seviye girilmemiş (ölçüm 2026-09-18); uydurma eşikle «kritik»
  denmez, kural ve kaynağı ekranda yazar.
- *Durum*: stokta yok (bakiye ≤ 0, satışı var) · bitecek (yeterlilik ≤ N gün ya da kritik) · hareketsiz (pencerede hiç
  hareket yok, Kural 17) · satışı yok (hareket var, satış hızı 0) · fazla (yeterlilik > `STOCK_EXCESS_DAYS`) · yeterli · pasif.
- *Logo–CRM farkı* = CRM raf kalanı − Logo bakiyesi; kök neden: Logo'ya aktarılmamış hareketin net miktarı farkı tam ya da
  kısmen açıklıyor mu, CRM'de raf kaydı var mı; açıklanamayan fark sayım adayıdır.

**Zeki AI (LLM kapısı, `rt.llm_for("stok", …)`; ekranda yalnız «Zeki AI»):** aktarım hata mesajını kapalı kümeye
sınıflar (`QueuedLlm.choose`, p ≥ eşik ve marj ≥ eşik), fazla stok için eritme yönü seçer (kampanya / set / bekle) ve sabah
bülteninin özet cümlelerini yazar (metindeki her sayı olgularda geçmeli, yoksa kural metni). Model sırası gece işinde
arka plan önceliğindedir; bitmeyen iş sonraki geceye kalır (sessiz tavan yok).

**Hız (2026-09-29):** Logo + CRM okuması 3–6 dakika sürer (test sunucusunda `X-Data-Refresh` ile 332 sn). Uçlar kaynağı
beklemez: son okuma portal tablosundadır (`semantic_stock_reads`; gece turu `run-due` ve arka plan tazelemesi yazar), istek
onu bellekten ya da tablodan alır. Okuma 5 dakikadan eskiyse ya da «Verileri yenile» (`X-Data-Refresh`) istendiyse yenisi
arka planda başlar (cevapta `yenileniyor`); biten okuma tabloya yazılır. Kaynak yalnız hiç okuma yokken beklenir.
"""
from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import statistics
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from semantic_bridge import stock_sources as src
from semantic_bridge import stock_store as store
from semantic_bridge.management import baski_oneri
from semantic_bridge.stock_store import PAGE_SIZE, StockError

log = logging.getLogger("semantic.stock")
TZ = ZoneInfo("Europe/Istanbul")
TTL = 300
#: M12 ölçümü ve ayar yoksa baskı süresi (gün). Ölçülecek: M12 gerçekleşen süreleri test sunucusunda.
FALLBACK_LEAD = 45

DEFAULTS: dict[str, str] = {
    "STOCK_RUNOUT_DAYS": "30",          # «bitecekler» listesinin varsayılan günü (ekranda değişir)
    "STOCK_SAFETY_DAYS": "15",          # onaylı eşik yoksa güvenlik günü
    "STOCK_LEAD_DAYS": "",              # boş: M12 ölçümü; o da yoksa 45
    "STOCK_EXCESS_DAYS": "730",         # yeterliliği bundan uzun kitap «fazla stok»
    "STOCK_DEAD_DAYS": "365",           # hareketsiz stok penceresi (Kural 17)
    "STOCK_EXCLUDE_PLANNED": "1",       # planlanan üretimden giriş fişi (PRODSTAT 1) bakiyeye girmez
    "STOCK_EXCLUDE_PREFIXES": "157",    # ticari ürün kodları (Baskı Öneri'nin depo stoku süzgeciyle aynı)
    "STOCK_MODEL": "1",                 # Zeki AI sınıflama, eritme yönü ve bülten metni
    "STOCK_MODEL_MIN_PROB": "0.70",
    "STOCK_MODEL_MIN_MARGIN": "0.30",
    "STOCK_MODEL_BUDGET_SEC": "1200",   # gece işinde model sırasına ayrılan süre; kalan iş sonraki geceye
    "STOCK_PICK_DAYS": "30",            # depo hattı aşama süreleri için geriye bakılan gün
    "STOCK_BULLETIN_RECIPIENTS": "",    # sabah bülteni (iç ekip)
}

STATES = {"stoksuz": "Stokta yok", "bitecek": "Bitecek", "yeterli": "Yeterli", "fazla": "Fazla stok",
          "olu": "Hareketsiz", "satissiz": "Satışı yok", "pasif": "Stok ve satış yok"}
TRANSFER_KINDS = {1: "Üretimden giriş", 2: "Faturalı kabul", 3: "Sayım fazlası", 4: "İade", 5: "Raf transferi",
                  6: "Depolar arası sevk", 7: "İrsaliye", 8: "Sayım eksiği", 9: "Set işlemi"}
TRANSFER_STATUS = {100000000: "Taslak", 1: "Etkin", 2: "Etkin değil"}
#: Aktarım hata mesajının kapalı kümesi (analiz §13). Model yalnız bunlardan birini seçer.
ERROR_CLASSES = ["Cari ya da stok kartı yok", "Dönem kapalı", "Miktar yetersiz", "Bağlantı hatası", "Diğer"]
DIFF_CLASSES = {"aktarim": "Logo'ya aktarılmamış hareket açıklıyor", "kismen": "Aktarılmamış hareket kısmen açıklıyor",
                "crm_yok": "CRM'de raf kaydı yok", "logo_yok": "Logo'da hareket yok", "sayim": "Açıklanamayan — sayım adayı"}
#: Sipariş hazırlık hattı: CRM sipariş durumu → (anahtar, etiket, aşamanın başladığı tarih kolonu).
PICK_STAGES = [(100000011, "depoda", "Depoda bekliyor", "depoda"), (100000012, "toplaniyor", "Pusula alındı, toplanıyor", "pusula"),
               (100000013, "kutulaniyor", "Kutulanıyor", "pusula"), (100000014, "kutulandi", "Kutulandı", "kutulandi")]
PICK_SPANS = [("depoda", "pusula", "Depoya düşüş → pusula"), ("pusula", "kutulandi", "Pusula → kutulandı"),
              ("kutulandi", "sevk", "Kutulandı → sevk"), ("depoda", "sevk", "Depoya düşüş → sevk (toplam)")]
ERITME = {"kampanya": ("M35", "Kampanya (e-ticaret / backlist)"), "set": ("M53", "Set ya da hediye paketi"), "bekle": (None, "Bekle, izlemeye devam")}
LIST_SORTS = ("gun", "bakiye", "ad", "hiz")


def today() -> date:
    return datetime.now(TZ).date()


# ------------------------------------------------------------------ ayarlar


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    def raw(k: str) -> str:
        try:
            v = conf(k, DEFAULTS[k])
        except Exception:  # noqa: BLE001
            v = os.environ.get(k, DEFAULTS[k])
        return str(v if v not in (None, "") else DEFAULTS[k])

    def num(k: str, lo: float, hi: float) -> float:
        try:
            v = float(raw(k).replace(",", "."))
        except ValueError:
            v = float(DEFAULTS[k])
        return max(lo, min(hi, v))

    lead = raw("STOCK_LEAD_DAYS").strip()
    return {
        "runoutDays": int(num("STOCK_RUNOUT_DAYS", 1, 3650)), "safetyDays": int(num("STOCK_SAFETY_DAYS", 0, 365)),
        "leadDays": int(float(lead)) if re.fullmatch(r"\d{1,4}", lead) else None,
        "excessDays": int(num("STOCK_EXCESS_DAYS", 30, 36500)), "deadDays": int(num("STOCK_DEAD_DAYS", 30, 3650)),
        "excludePlanned": raw("STOCK_EXCLUDE_PLANNED").strip().lower() not in ("0", "false", "hayir", "no"),
        "excludePrefixes": [p.strip() for p in raw("STOCK_EXCLUDE_PREFIXES").split(",") if re.fullmatch(r"[0-9A-Za-z.]+", p.strip())],
        "model": raw("STOCK_MODEL").strip().lower() not in ("0", "false", "hayir", "no"),
        "minProb": num("STOCK_MODEL_MIN_PROB", 0, 1), "minMargin": num("STOCK_MODEL_MIN_MARGIN", 0, 1),
        "modelBudget": int(num("STOCK_MODEL_BUDGET_SEC", 0, 36000)), "pickDays": int(num("STOCK_PICK_DAYS", 1, 365)),
        "recipients": [x.strip() for x in raw("STOCK_BULLETIN_RECIPIENTS").replace(";", ",").split(",") if "@" in x],
    }


# ------------------------------------------------------------------ küçük hesaplar


def _f(v: Any) -> Optional[float]:
    return src.num(v)


def _day(v: Any) -> Optional[date]:
    return src.day(v)


def _dt(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    try:
        return datetime.fromisoformat(str(v)[:19])
    except ValueError:
        return None


_TR = str.maketrans("İIıŞşĞğÜüÖöÇçÂâÎîÛû", "iiissgguuooccaaiiuu")


def fold(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").translate(_TR).lower()).strip()


def runout_date(data_end: Optional[date], gun: Optional[float]) -> Optional[str]:
    """Veri sonuna yeterlilik günü eklenmiş tarih. Hız çok küçükken gün takvimin taşıyabileceğinden büyük olabilir
    (ör. 13 milyar gün): o zaman tarih yok, gün sayısı ekranda kalır. 2026-09-28 gece işi bu yüzden bütünüyle düşüyordu
    («Python int too large to convert to C int»)."""
    if gun is None or not data_end:
        return None
    try:
        return (data_end + timedelta(days=int(gun))).isoformat()
    except (OverflowError, ValueError):
        return None


def days_of_cover(bakiye: Optional[float], hiz: Optional[float]) -> Optional[float]:
    """Gün cinsinden yeterlilik: bakiye ÷ (aylık hız ÷ 30). Satış yoksa boş, stok yoksa 0."""
    if hiz is None or hiz <= 0:
        return None
    if bakiye is None or bakiye <= 0:
        return 0.0
    return bakiye / (hiz / 30.0)


def baski_label(bakiye: Optional[float], hiz: Optional[float]) -> tuple[Any, Optional[str]]:
    """Baskı Öneri'nin tükenme süresi (ay) ve öneri etiketi — aynı DAX davranışıyla (içe aktarılır)."""
    tuk = baski_oneri._dax_div(bakiye, hiz)
    _, label = baski_oneri._marj_oneri(bakiye, hiz)
    return baski_oneri._out(tuk), label


def lead_days(cards: list[dict[str, Any]], setting: Optional[int]) -> tuple[int, str]:
    """Baskı süresi: ayar > M12 gerçekleşen sürelerin ortanca toplamı > varsayılan."""
    if setting is not None:
        return setting, "Yönetim ayarı"
    if cards:
        try:
            from semantic_bridge import production_plan as plan_mod

            leads = plan_mod.measure_leads(cards)
            parts = [(leads.get(f"{a}>{b}") or {}).get("days") for a, b in plan_mod.PAIRS]
            if parts and all(p is not None for p in parts):
                return int(sum(parts)), "Üretim kartlarında ölçülen süre (matbaa belirleme → depo girişi, ortanca)"
        except Exception as e:  # noqa: BLE001
            log.info("stock: M12 süresi ölçülemedi: %s", e)
    return FALLBACK_LEAD, "Varsayılan (üretim ölçümü yok)"


def classify_diff(logo: Optional[float], crm: Optional[float], pending: Optional[float]) -> Optional[tuple[str, float]]:
    """(sınıf, fark = CRM − Logo); fark yoksa None."""
    lg, cr = logo or 0.0, crm or 0.0
    fark = cr - lg
    if abs(fark) < 0.5:
        return None
    if crm is None:
        return "crm_yok", fark
    if logo is None:
        return "logo_yok", fark
    if pending and abs(fark - pending) < 0.5:
        return "aktarim", fark
    if pending and abs(fark - pending) < abs(fark):
        return "kismen", fark
    return "sayim", fark


def message_key(msg: Any) -> str:
    """Aynı hatanın fiş numarası/tutarı farklı kopyaları tek sınıflanır: rakam dizileri ve boşluk sadeleşir."""
    return re.sub(r"\d+", "#", " ".join(str(msg or "").split()))[:500]


def _excluded(code: str, prefixes: list[str]) -> bool:
    return any(code.startswith(p) for p in prefixes)


def _card(c: dict[str, Any]) -> dict[str, Any]:
    return {"kartId": c.get("id"), "ad": c.get("name"), "baskiNo": c.get("printNo"), "asama": c.get("stage"),
            "asamaEtiket": c.get("stageLabel"), "adet": c.get("qty"), "baskiPlan": (c.get("plan") or {}).get("baski"),
            "depoPlan": (c.get("plan") or {}).get("depo"), "tur": c.get("cardKind")}


OPEN_STAGES = ("hazirlik", "matbaa-secildi", "matbaada", "yolda")


def open_cards(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for c in cards or []:
        k = str(c.get("stockCode") or "").strip()
        if k and c.get("stage") in OPEN_STAGES:
            out.setdefault(k, []).append(c)
    for k in out:
        out[k].sort(key=lambda c: (c.get("created") or ""), reverse=True)
    return out


def forecast_window(fc: dict[str, Any], code: str) -> Optional[dict[str, Any]]:
    """Zeki AI aylık tahmininden 30/60/90 gün (ilk 1/2/3 ay, tahmin başlangıcından), p50."""
    p50 = (fc.get("p50") or {}).get(code)
    if not p50:
        return None
    return {"baslangic": fc.get("start"), "g30": round(sum(p50[:1])), "g60": round(sum(p50[:2])), "g90": round(sum(p50[:3]))}


def forecast_range(fc: dict[str, Any], code: str) -> Optional[dict[str, Any]]:
    """Aynı pencerelerin aralığı (tek istemci `forecast_client`): {"g30": {"p10","p50","p90","aralik"}, …}. Önbellekte
    p10/p90 yoksa `aralik` False ve yalnız p50 (aralık uydurulmaz)."""
    from semantic_bridge import forecast_client

    return forecast_client.window(fc, code)


# ------------------------------------------------------------------ model


def build(raw: dict[str, Any], s: dict[str, Any], thresholds: dict[str, dict[str, Any]], cards: list[dict[str, Any]],
          forecast: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Kaynak okuması → kitap satırları ve listeler. Saf işlev; okumayı bilmez."""
    data_end = _day(raw.get("dataEnd"))
    prefixes = s.get("excludePrefixes") or []
    balances: dict[str, dict[str, Any]] = raw.get("balances") or {}
    wh_names = {int(k): v for k, v in (raw.get("warehouses") or {}).items()}
    speeds: dict[str, dict[str, Any]] = raw.get("speeds") or {}
    movement: dict[str, dict[str, Any]] = raw.get("movement") or {}
    shelves_by: dict[str, list[dict[str, Any]]] = {}
    for r in raw.get("shelves") or []:
        shelves_by.setdefault(r["stokKodu"], []).append(r)
    pending_tr = raw.get("transferItems") or {}
    books = raw.get("books") or {}
    lead, lead_src = lead_days(cards, s.get("leadDays"))
    opens = open_cards(cards)
    fc = forecast or {}
    moved_known = raw.get("movement") is not None
    universe = set(balances) | set(speeds) | set(shelves_by)
    items: list[dict[str, Any]] = []
    for k in sorted(universe):
        if _excluded(k, prefixes):
            continue
        b = balances.get(k)
        bakiye = float(b["bakiye"]) if b else 0.0
        sp = speeds.get(k)
        hiz = _f(sp.get("satis_hizi")) if sp else None
        if sp and hiz is None:
            hiz = 0.0
        gun = days_of_cover(bakiye, hiz)
        tuk, oneri = baski_label(bakiye, hiz) if sp else (None, None)
        sh = shelves_by.get(k)
        crm = sum(x["adet"] for x in sh) if sh else None
        esik = thresholds.get(k)
        guv = int(esik["guvenlikGun"]) if esik else int(s["safetyDays"])
        kritik = lead + guv
        mv = movement.get(k)
        hz = hiz or 0.0
        if bakiye <= 0:
            durum = "stoksuz" if hz > 0 else "pasif"
        elif hz <= 0:
            durum = "olu" if moved_known and mv is None else "satissiz"
        elif gun is not None and (gun <= s["runoutDays"] or gun <= kritik):
            durum = "bitecek"
        elif moved_known and mv is None:
            durum = "olu"
        elif gun is not None and gun > s["excessDays"]:
            durum = "fazla"
        else:
            durum = "yeterli"
        bk = books.get(k) or {}
        wh = {int(n): float(q) for n, q in ((raw.get("warehouse") or {}).get(k) or {}).items()}
        cards_k = opens.get(k) or []
        rop = _f(esik.get("yenidenSiparisAdet")) if esik else None
        tr = pending_tr.get(k) or {}
        diff = classify_diff(bakiye if b else None, crm, _f(tr.get("net")))
        items.append({
            "stokKodu": k, "ad": bk.get("ad") or (b or {}).get("ad"), "yazar": bk.get("yazar"), "yayinevi": bk.get("yayinevi"),
            "kitaplik": bk.get("kitaplik"), "statu": bk.get("statu"),
            "bakiye": bakiye, "logoVar": bool(b),
            "ambarlar": [{"no": n, "ad": (wh_names.get(n) or {}).get("ad") or f"Ambar {n}", "adet": q}
                         for n, q in sorted(wh.items()) if abs(q) >= 0.5],
            "crmRaf": crm, "rafSayisi": len(sh or []),
            "satisHizi": hiz, "yillikSatis": _f(sp.get("yillik_toplam")) if sp else None,
            "gun": None if gun is None else round(gun, 1),
            "tukenmeTarihi": runout_date(data_end, gun),
            "tukenmeAy": tuk, "baskiOneri": oneri,
            "durum": durum, "durumEtiket": STATES[durum],
            "kritikGun": kritik, "baskiUyarisi": gun is not None and hz > 0 and gun <= kritik,
            "yenidenSiparisNoktasi": rop, "rspAltinda": rop is not None and bakiye <= rop,
            "esik": {"id": esik["id"], "guvenlikGun": esik["guvenlikGun"], "yenidenSiparisAdet": esik["yenidenSiparisAdet"],
                     "onaylayan": esik["onaylayan"], "onayTarihi": esik["onayTarihi"]} if esik else None,
            "bekleyenCrm": _f((raw.get("ordersCrm") or {}).get(k)),
            "bekleyenLogo": _f(((raw.get("ordersLogo") or {}).get(k) or {}).get("adet")),
            "bekleyenUrun": _f(((raw.get("waiting") or {}).get(k) or {}).get("adet")),
            "devirHizi": _f((raw.get("turnover") or {}).get(k)),
            "sonHareket": (_day(mv.get("son")).isoformat() if mv and _day(mv.get("son")) else None),
            "netSatis12": _f(mv.get("netSatis")) if mv else (0.0 if moved_known else None),
            "eosStok": _f((raw.get("eos") or {}).get(k)),
            "uretim": _card(cards_k[0]) if cards_k else None, "uretimSayisi": len(cards_k),
            "aktarimBekleyen": _f(tr.get("net")), "aktarimFis": int(_f(tr.get("fis")) or 0),
            "fark": diff[1] if diff else None, "farkSinif": diff[0] if diff else None,
            "farkEtiket": DIFF_CLASSES[diff[0]] if diff else None,
            "tahmin": forecast_window(fc, k),
            "tahminAralik": forecast_range(fc, k),
        })
    return {"items": items, "byCode": {i["stokKodu"]: i for i in items}, "dataEnd": data_end.isoformat() if data_end else None,
            "lead": lead, "leadSource": lead_src, "settings": s, "shelves": shelves_by,
            "warehouses": [{"no": n, "ad": v.get("ad") or f"Ambar {n}"} for n, v in sorted(wh_names.items())],
            "depots": raw.get("depots") or [], "transfers": raw.get("transfers") or [], "pick": raw.get("pick") or [],
            "warnings": list(raw.get("warnings") or []), "readAt": raw.get("at"), "readMs": raw.get("readMs"),
            "runs": raw.get("runs") or {},
            "forecastStart": fc.get("start")}


def page_of(rows: list[Any], page: int) -> dict[str, Any]:
    page = max(0, int(page or 0))
    return {"items": rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": len(rows), "page": page, "pageSize": PAGE_SIZE}


def _gun_key(i: dict[str, Any]) -> tuple:
    return (i["gun"] is None, i["gun"] if i["gun"] is not None else 0.0, i["ad"] or "")


def filter_items(model: dict[str, Any], *, q: str = "", yayinevi: str = "", depo: str = "", durum: str = "",
                 sira: str = "gun", dagitim: str = "") -> list[dict[str, Any]]:
    rows = model["items"]
    if dagitim:
        rows = [i for i in rows if (i.get("dagitim") or {}).get("isaret") == dagitim]
    if durum:
        wanted = set(durum.split(","))
        rows = [i for i in rows if i["durum"] in wanted]
    else:
        rows = [i for i in rows if i["durum"] != "pasif"]
    if yayinevi:
        rows = [i for i in rows if (i["yayinevi"] or "") == yayinevi]
    if depo:
        try:
            no = int(depo)
        except ValueError:
            raise StockError("Ambar numarası geçersiz.") from None
        rows = [i for i in rows if any(a["no"] == no and a["adet"] > 0 for a in i["ambarlar"])]
    if q:
        words = fold(q).split()
        rows = [i for i in rows if all(w in fold(f"{i['stokKodu']} {i['ad'] or ''} {i['yazar'] or ''} {i['yayinevi'] or ''}")
                                       for w in words)]
    if sira == "bakiye":
        rows = sorted(rows, key=lambda i: (-i["bakiye"], i["ad"] or ""))
    elif sira == "ad":
        rows = sorted(rows, key=lambda i: fold(i["ad"] or i["stokKodu"]))
    elif sira == "hiz":
        rows = sorted(rows, key=lambda i: (-(i["satisHizi"] or 0), i["ad"] or ""))
    else:
        rows = sorted(rows, key=_gun_key)
    return rows


def running_out(model: dict[str, Any], days: int) -> list[dict[str, Any]]:
    """Satışı olan ve yeterliliği ≤ gün olan, ya da baskı süresi + güvenlik gününün altına inen kitaplar (stoksuzlar 0 günle)."""
    rows = [i for i in model["items"] if (i["satisHizi"] or 0) > 0 and i["gun"] is not None
            and (i["gun"] <= days or i["baskiUyarisi"])]
    return sorted(rows, key=_gun_key)


def excess(model: dict[str, Any], tur: str = "") -> list[dict[str, Any]]:
    kinds = {"fazla", "olu", "satissiz"} if not tur else {tur}
    rows = [i for i in model["items"] if i["durum"] in kinds and i["bakiye"] > 0]
    return sorted(rows, key=lambda i: (-i["bakiye"], i["ad"] or ""))


def diff_rows(model: dict[str, Any], sinif: str = "") -> list[dict[str, Any]]:
    rows = [i for i in model["items"] if i["farkSinif"] and (not sinif or i["farkSinif"] == sinif)]
    return sorted(rows, key=lambda i: (-abs(i["fark"]), i["ad"] or ""))


def transfer_rows(model: dict[str, Any], classes: dict[str, Any], tur: str = "", now: Optional[date] = None) -> list[dict[str, Any]]:
    now = now or today()
    out = []
    for t in model["transfers"]:
        if tur == "hata" and not t["hata"] or tur == "bekliyor" and t["hata"]:
            continue
        fis, made = _day(t.get("fisTarihi")), _day(t.get("olusturma"))
        ref = fis or made
        cls = classes.get(message_key(t.get("mesaj"))) if t.get("hata") else None
        out.append({**{k: v for k, v in t.items() if k not in ("fisTarihi", "olusturma")},
                    "fisTarihi": fis.isoformat() if fis else None, "olusturma": made.isoformat() if made else None,
                    "yasGun": (now - ref).days if ref else None,
                    "islemTuruEtiket": TRANSFER_KINDS.get(t.get("islemTuru"), f"Tür {t.get('islemTuru')}"),
                    "islemTipiEtiket": {1: "Giriş", 2: "Çıkış"}.get(t.get("islemTipi")),
                    "durumEtiket": TRANSFER_STATUS.get(t.get("durum"), str(t.get("durum"))),
                    "mesaj": (t.get("mesaj") or "")[:1500] or None,
                    "sinif": (cls or {}).get("sinif"), "sinifOlasilik": (cls or {}).get("p")})
    out.sort(key=lambda t: (not t["hata"], -(t["yasGun"] or 0), t["fisNo"] or ""))
    return out


def pick_line(model: dict[str, Any], s: dict[str, Any], with_people: bool, now: Optional[datetime] = None) -> dict[str, Any]:
    """Aşama sayıları, açık siparişlerin aşamadaki yaşı, penceredeki aşama süreleri (ortanca, saat). Kişi bazlı
    toplama süresi yalnız `stok.depo-hatti` yetkisiyle."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    by_code = {code: (key, label, col) for code, key, label, col in PICK_STAGES}
    stages = {key: {"key": key, "label": label, "adet": 0, "yaslar": []} for _, key, label, _ in PICK_STAGES}
    open_rows = []
    since = now - timedelta(days=s["pickDays"])
    spans: dict[str, list[float]] = {f"{a}>{b}": [] for a, b, _ in PICK_SPANS}
    people: dict[str, list[float]] = {}
    for r in model["pick"]:
        st = by_code.get(r["durum"])
        if st:
            key, label, col = st
            start = _dt(r.get(col)) or _dt(r.get("depoda"))
            age = (now - start).total_seconds() / 3600 if start else None
            stages[key]["adet"] += 1
            if age is not None:
                stages[key]["yaslar"].append(age)
            row = {"id": r["id"], "no": r["no"], "asama": key, "asamaEtiket": label, "depo": r.get("depo"),
                   "oncelik": {1: "Acil", 2: "Öncelikli", 3: "Normal"}.get(r.get("oncelik")),
                   "asamaSaat": None if age is None else round(age, 1), "koli": r.get("koli"),
                   "depoyaDusus": _dt(r.get("depoda")).isoformat() if _dt(r.get("depoda")) else None}
            if with_people:
                row["toplayan"] = r.get("toplayan")
            open_rows.append(row)
        sevk = _dt(r.get("sevk"))
        if sevk and sevk >= since:
            for a, b, _ in PICK_SPANS:
                ta, tb = _dt(r.get(a)), _dt(r.get(b))
                if ta and tb and tb >= ta:
                    spans[f"{a}>{b}"].append((tb - ta).total_seconds() / 3600)
            tp, tk = _dt(r.get("pusula")), _dt(r.get("kutulandi"))
            if with_people and r.get("toplayan") and tp and tk and tk >= tp:
                people.setdefault(r["toplayan"], []).append((tk - tp).total_seconds() / 3600)

    def med(xs: list[float]) -> Optional[float]:
        return round(statistics.median(xs), 1) if xs else None

    out = {
        "asamalar": [{"key": v["key"], "label": v["label"], "adet": v["adet"], "ortancaSaat": med(v["yaslar"]),
                      "enEskiSaat": round(max(v["yaslar"]), 1) if v["yaslar"] else None} for v in stages.values()],
        "sureler": [{"from": a, "to": b, "label": lbl, "ortancaSaat": med(spans[f"{a}>{b}"]), "siparis": len(spans[f"{a}>{b}"])}
                    for a, b, lbl in PICK_SPANS],
        "acik": sorted(open_rows, key=lambda x: -(x["asamaSaat"] or 0)),
        "pencereGun": s["pickDays"],
    }
    if with_people:
        out["kisiler"] = sorted(({"toplayan": k, "siparis": len(v), "ortancaSaat": med(v)} for k, v in people.items()),
                                key=lambda x: -x["siparis"])
    return out


def threshold_proposal(item: dict[str, Any], lead: int, safety: int) -> Optional[dict[str, Any]]:
    """Güvenlik stoku önerisi: güvenlik günü = ayar; yeniden sipariş noktası = günlük hız × (baskı süresi + güvenlik günü).
    Rakam hesaptır, model üretmez. Satışı olmayan kitapta öneri yok."""
    hiz = item.get("satisHizi") or 0
    if hiz <= 0:
        return None
    rop = math.ceil(hiz / 30.0 * (lead + safety))
    return {"stokKodu": item["stokKodu"], "ad": item["ad"], "guvenlikGun": safety, "yenidenSiparisAdet": float(rop),
            "bakiye": item["bakiye"], "satisHizi": hiz, "gun": item["gun"], "baskiSuresi": lead,
            "gerekce": f"Aylık satış hızı {_tr(hiz, 1)} adet; baskı süresi {lead} gün + güvenlik {safety} gün = "
                       f"{lead + safety} günlük satış ≈ {_tr(rop)} adet. Stok bu adede inince baskı tekrarı başlatılmalı."}


def _tr(v: Optional[float], digits: int = 0) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{digits}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def overview(model: dict[str, Any], transfers: list[dict[str, Any]]) -> dict[str, Any]:
    items = model["items"]
    by = {k: 0 for k in STATES}
    for i in items:
        by[i["durum"]] += 1
    run = running_out(model, model["settings"]["runoutDays"])
    diffs = diff_rows(model)
    errors = [t for t in transfers if t["hata"]]
    return {
        "veriSonu": model["dataEnd"], "okuma": model["readAt"], "baskiSuresi": model["lead"], "baskiSuresiKaynak": model["leadSource"],
        "toplamStok": sum(i["bakiye"] for i in items if i["bakiye"] > 0),
        "stokluKitap": sum(1 for i in items if i["bakiye"] > 0),
        "stoksuzAktif": by["stoksuz"], "bitecek": len(run), "bitecekGun": model["settings"]["runoutDays"],
        "kartsizKritik": sum(1 for i in run if i["baskiUyarisi"] and not i["uretim"]),
        "aktarimHatasi": len(errors), "aktarimBekleyen": len(transfers) - len(errors),
        "farkliKitap": len(diffs), "fazla": by["fazla"], "hareketsiz": by["olu"], "satissiz": by["satissiz"],
        "durumlar": [{"key": k, "label": STATES[k], "adet": v} for k, v in by.items()],
        "bugun": {"bitecek": page_of(run, 0), "aktarim": page_of(errors, 0), "fark": page_of(diffs, 0)},
        "uyarilar": model["warnings"],
    }


# ------------------------------------------------------------------ Zeki AI


def _confident(res: Any, s: dict[str, Any]) -> bool:
    try:
        return bool(res.choice) and bool(res.confident(s["minProb"], s["minMargin"]))
    except Exception:  # noqa: BLE001
        return False


def classify_messages(llm: Any, messages: Iterable[str], known: dict[str, Any], s: dict[str, Any],
                      deadline: float) -> tuple[dict[str, Any], int]:
    """Yeni hata mesajlarını kapalı kümeye sınıflar. (güncel sınıflar, kalan mesaj sayısı)."""
    out = dict(known)
    todo = [m for m in dict.fromkeys(message_key(x) for x in messages if x) if m and m not in out]
    if llm is None or not hasattr(llm, "choose"):
        return out, len(todo)
    system = ("Bir yayınevinin depo sorumlusuna yardım edersin. Depo yazılımından muhasebe programına aktarılamayan bir "
              "stok hareketinin hata mesajını okuyup nedenini seçersin.")
    for i, m in enumerate(todo):
        if time.monotonic() > deadline:
            return out, len(todo) - i
        try:
            res = llm.choose(f"Hata mesajı:\n{m}\n\nBu hatanın nedeni hangisi?", list(ERROR_CLASSES), system=system)
        except Exception as e:  # noqa: BLE001 — model yok: sonraki gece
            log.warning("stock: mesaj sınıflanamadı: %s", e)
            return out, len(todo) - i
        out[m] = {"sinif": res.choice if _confident(res, s) else None, "p": round(float(res.probability or 0), 3)
                  if getattr(res, "probability", None) is not None else None}
    return out, 0


def excess_direction(llm: Any, item: dict[str, Any], s: dict[str, Any]) -> tuple[Optional[str], Optional[float], str]:
    """Fazla/hareketsiz stok için eritme yönü (kampanya / set / bekle). (yön, olasılık, kaynak)."""
    if llm is None or not hasattr(llm, "choose"):
        return None, None, "kural"
    prompt = (f"Kitap: {item['ad'] or item['stokKodu']} | yazar: {item['yazar'] or '-'} | yayınevi: {item['yayinevi'] or '-'} | "
              f"kitaplık: {item['kitaplik'] or '-'}\nDepodaki stok: {_tr(item['bakiye'])} adet. Aylık satış hızı: "
              f"{_tr(item['satisHizi'] or 0, 1)}. Son 12 ay net satış: {_tr(item['netSatis12'])}. Stok yeterliliği: "
              f"{'satış yok' if item['gun'] is None else _tr(item['gun']) + ' gün'}. Durum: {item['durumEtiket']}.\n"
              "Bu fazla stok için en uygun eritme yolu hangisi? kampanya = indirim/kampanya ile satış; set = başka kitaplarla "
              "set ya da hediye paketi; bekle = henüz müdahale gerekmez.")
    try:
        res = llm.choose(prompt, list(ERITME), system="Bir yayınevinin stok planlama yardımcısısın. Yalnız verilen seçeneklerden birini seçersin.")
    except Exception as e:  # noqa: BLE001
        log.warning("stock: eritme yönü seçilemedi: %s", e)
        raise
    p = float(res.probability) if getattr(res, "probability", None) is not None else None
    return (res.choice if _confident(res, s) else None), p, "model"


def bulletin(model: dict[str, Any], ov: dict[str, Any], llm: Any, use_model: bool) -> tuple[str, str]:
    """Sabah bülteni: olgular kural metniyle; Zeki AI yalnız sıralar ve bağlar (olgu dışı sayı varsa kural metni)."""
    from semantic_bridge.distribution import safe_model_text

    day = model["dataEnd"] or "—"
    facts = [f"Logo verisinin son günü: {day}.",
             f"{_tr(ov['bitecek'])} kitap {ov['bitecekGun']} gün içinde ya da baskı süresi ({ov['baskiSuresi']} gün) + güvenlik gününün altında bitiyor; "
             f"{_tr(ov['kartsizKritik'])} tanesinin açık üretim kartı yok.",
             f"Satışı olup stokta olmayan kitap: {_tr(ov['stoksuzAktif'])}.",
             f"Logo'ya aktarılamayan hareket (hata mesajlı): {_tr(ov['aktarimHatasi'])}; mesajsız bekleyen: {_tr(ov['aktarimBekleyen'])}.",
             f"Logo ile CRM raf stoğu farklı olan kitap: {_tr(ov['farkliKitap'])}.",
             f"Fazla stok: {_tr(ov['fazla'])} kitap; hareketsiz: {_tr(ov['hareketsiz'])} kitap."]
    top = ov["bugun"]["bitecek"]["items"][:5]
    if top:
        facts.append("En önce bitecekler: " + "; ".join(
            f"{i['ad'] or i['stokKodu']} ({_tr(i['gun'])} gün, stok {_tr(i['bakiye'])})" for i in top) + ".")
    rule = "\n".join(facts)
    if not use_model or llm is None:
        return rule, "kural"
    msg = [{"role": "system", "content": "Bir yayınevinin depo müdürüne sabah stok bültenini Türkçe, 5–8 cümleyle yazarsın. "
                                         "Yalnız verilen olgulardaki sayıları kullanırsın; yeni sayı, yüzde ya da tahmin yazmazsın. "
                                         "Önce acil olanı söylersin. Teknoloji ya da model adı yazmazsın."},
           {"role": "user", "content": "Olgular:\n" + rule + "\n\nBülteni yaz."}]
    try:
        text = str(llm.chat(msg, max_tokens=600, temperature=0.2) or "").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("stock: bülten metni yazılamadı: %s", e)
        return rule, "kural"
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    if not safe_model_text(text, rule):
        return rule, "kural"
    return text[:3000] + "\n\n— Olgular —\n" + rule, "model"


# ------------------------------------------------------------------ Excel


LISTS = {
    "stok": "Stok listesi", "bitecekler": "Bitecekler", "fazla": "Fazla ve hareketsiz stok", "fark": "Logo–CRM farkı",
    "aktarim": "Logo'ya aktarılamayan hareketler", "esik-onerileri": "Güvenlik stoku önerileri",
}


def export_xlsx(title: str, columns: list[tuple[str, str]], rows: list[dict[str, Any]], note: str) -> bytes:
    """Bütün satırlar (sayfalama yok). `columns` = (anahtar, başlık)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\[\]:*?/\\]", "-", title)[:31]
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = note
    hr = 4
    for i, (_, h) in enumerate(columns, 1):
        c = ws.cell(row=hr, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4B3FA8")
    for n, r in enumerate(rows, 1):
        for i, (k, _) in enumerate(columns, 1):
            v = r.get(k)
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            ws.cell(row=hr + n, column=i, value=v)
    for i, (k, h) in enumerate(columns, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(10, min(48, len(h) + 4 if k not in ("ad", "mesaj") else 42))
    ws.freeze_panes = f"A{hr + 1}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ servis


def _cache_path() -> Path:
    root = Path(os.environ.get("STOCK_CACHE_DIR", "/data/nanobaseai/bi/var/stock"))
    return root / "stock-raw.json"


class Service:
    """Kaynak okuması (Logo + CRM) → son okuma tablosu (`semantic_stock_reads`) → model.

    İstek kaynağı beklemez: bellekteki okuma yoksa tablodaki (o da yoksa eski disk dosyasındaki) son okuma alınır ve hemen
    döner. Okuma 5 dakikadan eskiyse ya da «Verileri yenile» (`fresh`) istendiyse yenisi arka planda başlar; biten okuma
    tabloya yazılır, sonraki istek onu görür. Kaynağın beklendiği iki durum: hiç okuma yok (kurulumdan sonraki ilk açılış,
    gece turu henüz koşmamış) ve gece turu (`wait=True`). Aynı anda tek okuma."""

    def __init__(self, logo_run: Callable[[], src.Runner], crm_run: Callable[[], src.Runner], schema: Callable[[], str],
                 settings: Callable[[], dict[str, Any]], m12_cards: Callable[[Any, str], list[dict[str, Any]]] = lambda e, t: [],
                 forecast: Callable[[], dict[str, Any]] = lambda: {}, cache: Callable[[], Path] = _cache_path,
                 m12_ready: Callable[[], bool] = lambda: True):
        self.logo_run, self.crm_run, self.schema = logo_run, crm_run, schema
        self.settings, self.m12_cards, self.forecast, self.cache = settings, m12_cards, forecast, cache
        self.m12_ready = m12_ready
        self._lock = threading.Lock()
        self._read_lock = threading.Lock()
        self._raw: Optional[dict[str, Any]] = None
        self._bg: Optional[threading.Thread] = None
        self._model: Optional[tuple[tuple, dict[str, Any]]] = None
        self.sql: dict[str, str] = {}

    # ---- okuma
    def read(self) -> dict[str, Any]:
        s = self.settings()
        started = time.monotonic()
        warnings: list[str] = []
        errors: dict[str, str] = {}
        logo = src.Logo(self.logo_run(), s["excludePlanned"])
        raw: dict[str, Any] = {"at": time.time()}
        balances, wh = logo.balances()           # çekirdek: okunamazsa ekran açılmaz (SourceError)
        raw["balances"], raw["warehouse"] = balances, wh
        raw["dataEnd"] = logo.data_end()

        def step(name: str, fn: Callable[[], Any], label: str) -> Any:
            try:
                return fn()
            except Exception as e:  # noqa: BLE001 — tek kaynak düşerse ekran yine açılır, eksik yazılır
                log.warning("stock: %s okunamadı: %s", name, e)
                errors[name] = str(e)[:300]
                warnings.append(f"{label} okunamadı; ilgili sütunlar boş.")
                return None

        base = raw["dataEnd"] or today()
        raw["warehouses"] = step("logo_ambarlar", logo.warehouses, "Logo ambar adları") or {}
        raw["speeds"] = step("logo_satis_hizi", lambda: logo.speeds(today()), "Satış hızı") or {}
        raw["eos"] = step("logo_depo_stok", logo.eos_stock, "Mevcut rapordaki depo stoku") or {}
        raw["turnover"] = step("logo_devir", logo.turnover, "Stok devir hızı") or {}
        a, b = src.movement_window(base, s["deadDays"])
        raw["movement"] = step("logo_hareket", lambda: logo.movement(a, b), "Hareket penceresi")
        raw["movementWindow"] = [a.isoformat(), (b - timedelta(days=1)).isoformat()]
        raw["ordersLogo"] = step("logo_orfline_bekleyen", logo.open_orders, "Logo bekleyen sipariş") or {}
        crm_sql: dict[str, str] = {}
        crm_runs: dict[str, dict[str, Any]] = {}
        try:
            crm = src.Crm(self.crm_run(), self.schema())
            raw["books"] = step("crm_kitap", crm.books, "CRM kitap kartı") or {}
            raw["ordersCrm"] = step("crm_bekleyen_siparis", crm.pending_orders, "CRM bekleyen sipariş") or {}
            raw["shelves"] = step("crm_raf_stok", crm.shelves, "CRM raf stoğu") or []
            raw["depots"] = step("crm_depo", crm.depots, "CRM depoları") or []
            raw["transfers"] = step("crm_aktarim_hatasi", crm.transfers, "Logo'ya aktarılmamış hareketler") or []
            raw["transferItems"] = step("crm_aktarim_urun", crm.transfer_items, "Aktarılmamış hareket (kitap başına)") or {}
            raw["waiting"] = step("crm_bekleyen_urun", crm.waiting_products, "Bekleyen ürün") or {}
            raw["pick"] = step("crm_depo_hatti", lambda: crm.pick_line(today() - timedelta(days=s["pickDays"])),
                               "Sipariş hazırlık hattı") or []
            crm_sql, crm_runs = crm.sql, crm.runs
        except Exception as e:  # noqa: BLE001
            log.warning("stock: CRM okunamadı: %s", e)
            warnings.append("CRM'e şu an ulaşılamıyor; raf stoğu, aktarım ve depo hattı boş.")
        if raw["dataEnd"] and (today() - raw["dataEnd"]).days > 3:
            d = raw["dataEnd"]
            warnings.append(f"Logo verisi {d.day:02d}.{d.month:02d}.{d.year} tarihinde bitiyor: bakiye ve tükenme o güne göredir, "
                            "«bugünkü stok» değildir.")
        raw["warnings"], raw["errors"] = warnings, errors
        raw["sql"] = {**logo.sql, **crm_sql}
        raw["runs"] = {**logo.runs, **crm_runs}   # sorgu bilgisi: çalışan metin + satır/süre/an (stock_kaynak.py)
        raw["readMs"] = int((time.monotonic() - started) * 1000)
        return raw

    def _persist(self, raw: dict[str, Any], engine: Any = None, tenant: Optional[str] = None) -> None:
        """Son okuma tabloya yazılır (uçlar oradan okur); tablo yazılamazsa eski disk dosyasına."""
        if engine is not None and tenant:
            try:
                store.read_put(engine, tenant, raw)
                return
            except Exception as e:  # noqa: BLE001 — okuma bellekte kalır, dosyaya düşülür
                log.warning("stock: son okuma tabloya yazılamadı: %s", e)
        try:
            p = self.cache()
            p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(raw, ensure_ascii=False, default=str))
            os.replace(tmp, p)
        except OSError as e:
            log.info("stock: önbellek dosyası yazılamadı: %s", e)

    def _load(self, engine: Any = None, tenant: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Tablodaki son okuma; tablo boşsa (bu sürümün ilk turundan önce) eski disk dosyası."""
        if engine is not None and tenant:
            try:
                raw = store.read_get(engine, tenant)
                if raw is not None:
                    return raw
            except Exception as e:  # noqa: BLE001
                log.info("stock: son okuma tablodan okunamadı: %s", e)
        try:
            return json.loads(self.cache().read_text())
        except (OSError, ValueError):
            return None

    def _adopt(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Tablodan gelen okumayı bellekteki yerine koyar (yalnız daha yeniyse)."""
        with self._lock:
            if self._raw is None or float(raw.get("at") or 0) > float(self._raw.get("at") or 0):
                self._raw, self._model = raw, None
                self.sql = raw.get("sql") or {}
            return self._raw

    def _refresh(self, since: float, engine: Any = None, tenant: Optional[str] = None) -> dict[str, Any]:
        """Tek okuma: başka bir istek bu istekten sonra başlamış bir okumayı bitirdiyse onu kullanır (aynı ağır okuma
        iki kez koşmaz)."""
        with self._read_lock:
            with self._lock:
                cur = self._raw
            if cur is not None and float(cur.get("_started") or 0) >= since:
                return cur
            started = time.time()
            raw = self.read()
            raw["_started"] = started
            with self._lock:
                self._raw, self._model = raw, None
            self.sql = raw.get("sql") or {}
            self._persist(raw, engine, tenant)
            return raw

    def _refresh_later(self, since: float, engine: Any = None, tenant: Optional[str] = None) -> None:
        with self._lock:
            if self._bg and self._bg.is_alive():
                return

            def bg() -> None:
                try:
                    self._refresh(since, engine, tenant)
                except Exception as e:  # noqa: BLE001 — eski okuma ekranda kalır
                    log.warning("stock: arka plan okuması başarısız: %s", e)
            self._bg = threading.Thread(target=bg, daemon=True, name="stock-refresh")
            self._bg.start()

    def raw(self, fresh: bool = False, *, wait: bool = False, engine: Any = None, tenant: Optional[str] = None) -> dict[str, Any]:
        """Son okuma, beklemeden. `fresh` («Verileri yenile»): yenisi arka planda başlar, bu istek eldekini alır.
        `wait` (gece turu): kaynak beklenerek okunur."""
        asked = time.time()
        with self._lock:
            cur = self._raw
        if cur is None:
            loaded = self._load(engine, tenant)
            cur = self._adopt(loaded) if loaded is not None else None
        if wait or cur is None:
            return self._refresh(asked, engine, tenant)
        stale = time.time() - float(cur.get("at") or 0) > TTL
        if stale and engine is not None and tenant and not self.refreshing():
            # Gece turu ya da başka bir köprü süreci daha yeni bir okuma yazdıysa önce o alınır.
            try:
                at = store.read_at(engine, tenant)
                if at is not None and at > float(cur.get("at") or 0):
                    newer = store.read_get(engine, tenant)
                    if newer is not None:
                        cur = self._adopt(newer)
                        stale = time.time() - float(cur.get("at") or 0) > TTL
            except Exception as e:  # noqa: BLE001
                log.info("stock: son okuma anı okunamadı: %s", e)
        if fresh or stale:
            self._refresh_later(asked, engine, tenant)
        return cur

    def refreshing(self) -> bool:
        return bool(self._bg and self._bg.is_alive())

    def invalidate(self) -> None:
        with self._lock:
            self._model = None

    def model(self, engine: Any, tenant: str, fresh: bool = False, wait: bool = False) -> dict[str, Any]:
        """Kitap satırları. Aynı okuma, aynı ayar ve aynı üretim kartı durumu için bir kez kurulur (eşik onayı
        `invalidate` ile düşürür). `fresh` modeli yeniden kurdurmaz: yeni okuma gelince model kendiliğinden yenilenir."""
        raw = self.raw(fresh, wait=wait, engine=engine, tenant=tenant)
        s = self.settings()
        try:
            ready = bool(self.m12_ready())
        except Exception:  # noqa: BLE001
            ready = True
        key = (raw.get("at"), ready, json.dumps(s, sort_keys=True, default=str))
        with self._lock:
            if self._model is not None and self._model[0] == key:
                return self._model[1]
        try:
            cards = self.m12_cards(engine, tenant) or []
        except Exception as e:  # noqa: BLE001
            log.info("stock: üretim kartları okunamadı: %s", e)
            cards = []
        try:
            fc = self.forecast() or {}
        except Exception:  # noqa: BLE001
            fc = {}
        m = build(raw, s, store.approved_thresholds(engine, tenant), cards, fc)
        m["movementWindow"] = raw.get("movementWindow")
        try:
            # M39 dağıtımcı katalogları (Başarı, D&R): kitap satırına `dagitim`; tablo boşsa satırlar None alır.
            from semantic_bridge import pazar_dagitim

            m["dagitim"] = pazar_dagitim.attach_stock(engine, tenant, m["items"])
        except Exception as e:  # noqa: BLE001 — dağıtımcı bilgisi stok ekranını düşürmez
            log.info("stock: dağıtımcı bilgisi eklenemedi: %s", e)
            m["dagitim"] = None
        with self._lock:
            self._model = (key, m)
        return m
