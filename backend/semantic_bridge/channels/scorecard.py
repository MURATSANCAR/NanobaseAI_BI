"""M42 kanal karnesi, kanal detayı, kitap × kanal matrisi, hedef ↔ gerçekleşen ve iskonto simülasyonu.

Hesaplar önbellekten (Logo okuması, `refresh.py`) ve onaylı eşlemeden yapılır; model rakam üretmez.

**Tanımlar** (ekranda da yazılır)
- Net ciro = satış VATMATRAH − iade VATMATRAH (faturalı satır; KDV matrahı, dönem fatura tarihi). Kanala satış
  (sell-in); kanalın son tüketiciye sattığı değil.
- İade oranı = iade VATMATRAH ÷ satış VATMATRAH. İskonto oranı = satır iskontosu ÷ brüt satış (iskonto öncesi TOTAL).
- Brüt marj = 1 − maliyet ÷ maliyetli ciro; yalnız maliyeti girilmiş satış satırları (OUTCOST > 0). Maliyetsiz satır
  sayısı ve cirosu her zaman yanında yazılır (gizlenmez, marja sessizce katılmaz).
- İade sonrası marj (M46 tanımı): iade satırları eksi işaretle (maliyetli iade satırlarının cirosu ve maliyeti düşülür).
- M9 ile tamamlanan marj (yalnız kanal detayında): maliyetsiz satırların adedi × M9 birim maliyeti (onaylı analiz, yoksa
  Logo gerçekleşen); birim maliyeti bilinmeyen kitap yine dışarıda kalır ve sayılır.
- Ek kanal maliyeti (komisyon, kargo, reklam) Logo'da kanal bazında ayrışmıyor (ölçülecek, Soru 5): finansın girdiği oran
  varsa «katkı» = iade sonrası brüt kâr − net ciro × oran.
- Dönem: seçilen yılın Ocak'ından seçilen aya kadar. Veri ayın ortasında bitiyorsa geçen yılın aynı ayı gün oranıyla
  kıyaslanır (yarım aya yarım ay).
"""
from __future__ import annotations

import calendar
import json
import math
from collections import defaultdict
from datetime import date
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import hizli_bellek as HB
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import store as S
from semantic_bridge.channels.sources import BOOK_METRICS, KANAL_PREFIX, METRICS

PAGE = 100
AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
#: Marj görme yetkisi (`ozellik:kanal.marj`) olmayan kişiye gitmeyen alanlar.
MARGIN_KEYS = frozenset({"maliyet", "maliyetliCiro", "brutKar", "marj", "iadeSonrasiMarj", "iadeSonrasiBrutKar", "katki",
                         "katkiMarj", "ekMaliyetOrani", "m9", "maliyetKapsami", "marjFarki"})


class ChannelError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ ölçü


def zero() -> dict[str, float]:
    return {k: 0.0 for k in METRICS}


def add(a: dict[str, float], b: dict[str, Any], w: float = 1.0) -> dict[str, float]:
    for k in a:
        a[k] += float(b.get(k) or 0) * w
    return a


def _ratio(n: float, d: float) -> Optional[float]:
    return None if not d else n / d


def derive(m: dict[str, float], extra_cost: Optional[float] = None) -> dict[str, Any]:
    net = m["satis_ciro"] - m["iade_ciro"]
    brut_kar = m["maliyetli_ciro"] - m["maliyet"]
    ia_ciro = m["maliyetli_ciro"] - m["iade_maliyetli_ciro"]
    ia_kar = ia_ciro - (m["maliyet"] - m["iade_maliyet"])
    out = {
        "netCiro": round(net, 2), "netAdet": round(m["satis_adet"] - m["iade_adet"], 2),
        "satisCiro": round(m["satis_ciro"], 2), "iadeCiro": round(m["iade_ciro"], 2),
        "satisAdet": round(m["satis_adet"], 2), "iadeAdet": round(m["iade_adet"], 2),
        "brutSatis": round(m["brut_satis"], 2), "iskonto": round(m["iskonto"], 2),
        "iskontoOrani": _ratio(m["iskonto"], m["brut_satis"]),
        "iadeOrani": _ratio(m["iade_ciro"], m["satis_ciro"]),
        "iadeAdetOrani": _ratio(m["iade_adet"], m["satis_adet"]),
        "maliyet": round(m["maliyet"], 2), "maliyetliCiro": round(m["maliyetli_ciro"], 2),
        "brutKar": round(brut_kar, 2), "marj": _ratio(brut_kar, m["maliyetli_ciro"]),
        "maliyetKapsami": _ratio(m["maliyetli_ciro"], m["satis_ciro"]),
        "maliyetsizSatir": int(round(m["maliyetsiz_satir"])), "maliyetsizCiro": round(m["maliyetsiz_ciro"], 2),
        "iadeSonrasiBrutKar": round(ia_kar, 2), "iadeSonrasiMarj": _ratio(ia_kar, ia_ciro),
    }
    if extra_cost is not None:
        k = ia_kar - net * extra_cost
        out.update(ekMaliyetOrani=extra_cost, katki=round(k, 2), katkiMarj=_ratio(k, ia_ciro))
    return out


def redact(obj: Any) -> Any:
    """Marj yetkisi yoksa maliyet/marj alanları her derinlikte çıkarılır."""
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items() if k not in MARGIN_KEYS}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def change(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or not prev:
        return None
    return cur / prev - 1


# ------------------------------------------------------------------ dönem


def period(engine: sa.engine.Engine, tenant: str, yil: Optional[int], ay: Optional[int]) -> dict[str, Any]:
    from semantic_bridge.channels.refresh import data_end

    end = data_end(engine, tenant)
    if yil is None:
        yil = end.year if end else date.today().year
    yil = int(yil)
    if not 2015 <= yil <= 2100:
        raise ChannelError("Yıl geçersiz.")
    last = 12
    share = 1.0
    if end and yil == end.year:
        last = end.month
        dim = calendar.monthrange(end.year, end.month)[1]
        share = end.day / dim
    elif end and yil > end.year:
        raise ChannelError(f"{yil} için Logo'da henüz veri yok (veri {end.isoformat()} tarihinde bitiyor).")
    if ay is not None:
        ay = int(ay)
        if not 1 <= ay <= 12:
            raise ChannelError("Ay 1–12 arası olmalı.")
        if ay < last:
            last, share = ay, 1.0
    return {"yil": yil, "ay": last, "ayAdi": AY[last - 1], "gunPayi": round(share, 4), "kismiAy": share < 1.0,
            "veriSonu": end.isoformat() if end else None}


def _read_years(engine: sa.engine.Engine, tenant: str) -> set[int]:
    return {int(k.split(":", 1)[1]) for k in S.meta_like(engine, tenant, "read:")}


def need_read(engine: sa.engine.Engine, tenant: str, years: Iterable[int]) -> None:
    have = _read_years(engine, tenant)
    miss = [y for y in years if y not in have]
    if miss:
        raise ChannelError(f"{', '.join(map(str, miss))} yılı henüz Logo'dan okunmadı; «Veriyi yenile» ile okunabilir.", 409)


# ------------------------------------------------------------------ gruplama


class Mapping:
    """Grup (cari kodu ya da '#K:<kanal kodu>') → platform. Onaysız aday sayılmaz; e-ticaret kodlu ama onaylanmamış cari
    «eşlenmemiş» sütunudur (karnede ayrı satır, toplamdan düşülmez)."""

    def __init__(self, engine: sa.engine.Engine, tenant: str):
        self.amap = S.approved_map(engine, tenant)
        self.kmap = M.kanal_map(engine, tenant)
        with engine.connect() as c:
            rows = c.execute(sa.select(S.ACCOUNTS.c.logo_cari_kodu, S.ACCOUNTS.c.unvan, S.ACCOUNTS.c.kanal, S.ACCOUNTS.c.logo_ref)
                             .where(S.ACCOUNTS.c.tenant_id == tenant)).all()
        self.cards = {r.logo_cari_kodu: {"unvan": r.unvan, "kanal": r.kanal, "ref": r.logo_ref} for r in rows}

    def platform(self, grup: str) -> str:
        if grup.startswith(KANAL_PREFIX):
            return self.kmap.get(grup[len(KANAL_PREFIX):]) or M.UNMAPPED
        return self.amap.get(grup) or M.UNMAPPED

    def label(self, grup: str) -> str:
        if grup.startswith(KANAL_PREFIX):
            return f"Kanal kodu {grup[len(KANAL_PREFIX):]} (bütün carileri)"
        return (self.cards.get(grup) or {}).get("unvan") or grup


def platform_label(key: str) -> str:
    return M.PLATFORMS.get(key) or ("Eşlenmemiş e-ticaret carileri" if key == M.UNMAPPED else key)


def _months(engine: sa.engine.Engine, tenant: str, table: sa.Table, years: Iterable[int]) -> list[Any]:
    with engine.connect() as c:
        return c.execute(sa.select(table).where(table.c.tenant_id == tenant, table.c.yil.in_(list(years)))).all()


def _window(p: dict[str, Any], yil: int) -> dict[int, float]:
    """Dönemin ay ağırlıkları: seçilen yılda 1..ay tam; geçen yıl kıyasında son ay gün oranıyla."""
    w = {m: 1.0 for m in range(1, p["ay"] + 1)}
    if yil != p["yil"] and p["kismiAy"]:
        w[p["ay"]] = p["gunPayi"]
    return w


def _elapsed(p: dict[str, Any]) -> dict[int, float]:
    """Hedefin bugüne düşen payı için ay ağırlıkları: geçen aylar tam, verinin bittiği ay gün oranıyla."""
    w = {m: 1.0 for m in range(1, p["ay"] + 1)}
    if p["kismiAy"]:
        w[p["ay"]] = p["gunPayi"]
    return w


def _sum(rows: Iterable[Any], key: Callable[[Any], Optional[str]], weights: dict[int, float]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(zero)
    for r in rows:
        w = weights.get(r.ay)
        if not w:
            continue
        k = key(r)
        if k is None:
            continue
        add(out[k], r._mapping, w)
    return out


# ------------------------------------------------------------------ karne


def scorecard(engine: sa.engine.Engine, tenant: str, yil: Optional[int] = None, ay: Optional[int] = None,
              dagitim: bool = False) -> dict[str, Any]:
    """`dagitim`: karne ekranı için «dağıtımcı ve perakende» bloğu (`dagitimci`) da kurulur; D2C, rapor ve e-ticaret
    özetleri yalnız platform toplamlarını kullandığı için kurmaz."""
    p = period(engine, tenant, yil, ay)
    y, ly = p["yil"], p["yil"] - 1
    need_read(engine, tenant, [y])
    has_ly = ly in _read_years(engine, tenant)
    mp = Mapping(engine, tenant)
    extra = M.extra_costs(engine, tenant)
    cari = _months(engine, tenant, S.CARI_MONTHS, [y, ly])
    kanal = _months(engine, tenant, S.KANAL_MONTHS, [y, ly])
    cur_rows = [r for r in cari if r.yil == y]
    ly_rows = [r for r in cari if r.yil == ly]
    w, wly = _window(p, y), _window(p, ly)
    month_only = {p["ay"]: 1.0}

    by_p = _sum(cur_rows, lambda r: mp.platform(r.grup), w)
    by_p_ly = _sum(ly_rows, lambda r: mp.platform(r.grup), wly) if has_ly else {}
    by_p_m = _sum(cur_rows, lambda r: mp.platform(r.grup), month_only)
    groups = defaultdict(set)
    for r in cur_rows:
        groups[mp.platform(r.grup)].add(r.grup)
    for code, plat in mp.amap.items():
        groups[plat].add(code)

    etic = zero()
    etic_ly = zero()
    for k, v in by_p.items():
        if k != "degil":
            add(etic, v)
    for k, v in by_p_ly.items():
        if k != "degil":
            add(etic_ly, v)
    sirket = _sum([r for r in kanal if r.yil == y], lambda r: "x", w).get("x", zero())
    sirket_ly = _sum([r for r in kanal if r.yil == ly], lambda r: "x", wly).get("x", zero()) if has_ly else zero()
    etic_d, sirket_d = derive(etic), derive(sirket)

    targets = targets_by_platform(engine, tenant, p, mp)
    items = []
    for key in M.CARD_PLATFORMS + [M.UNMAPPED]:
        if key not in by_p and key not in groups:
            continue
        cur = derive(by_p.get(key, zero()), extra.get(key))
        prev = derive(by_p_ly[key]) if key in by_p_ly else None
        items.append({
            "platform": key, "label": platform_label(key), "grupSayisi": len(groups.get(key, ())),
            "donem": cur, "buAy": derive(by_p_m.get(key, zero())), "gecenYil": prev,
            "degisim": change(cur["netCiro"], prev["netCiro"]) if prev else None,
            "marjFarki": (cur["marj"] - prev["marj"]) if prev and cur["marj"] is not None and prev["marj"] is not None else None,
            "payEticaret": _ratio(cur["netCiro"], etic_d["netCiro"]), "paySirket": _ratio(cur["netCiro"], sirket_d["netCiro"]),
            "hedef": targets.get(key),
        })
    items.sort(key=lambda x: (x["platform"] == M.UNMAPPED, -(x["donem"]["netCiro"] or 0)))

    kan_cur = _sum([r for r in kanal if r.yil == y], lambda r: r.kanal, w)
    benchmark = sorted(({"kanal": k, "donem": derive(v), "paySirket": _ratio(v["satis_ciro"] - v["iade_ciro"], sirket_d["netCiro"])}
                        for k, v in kan_cur.items()), key=lambda x: -x["donem"]["netCiro"])
    degil = by_p.get("degil")
    return {
        "period": p, "gecenYilOkundu": has_ly,
        "platforms": items,
        "toplam": {"eticaret": etic_d, "eticaretGecenYil": derive(etic_ly) if has_ly else None, "sirket": sirket_d,
                   "sirketGecenYil": derive(sirket_ly) if has_ly else None,
                   "eticaretPay": _ratio(etic_d["netCiro"], sirket_d["netCiro"]),
                   "d2cPay": next((x["payEticaret"] for x in items if x["platform"] == M.D2C), None)},
        "platformDisi": {"grupSayisi": len(groups.get("degil", ())), "donem": derive(degil) if degil else None},
        "kanallar": benchmark,
        **({"dagitimci": dagitimci(engine, tenant, p, by_p.get("dr"))} if dagitim else {}),
    }


# ------------------------------------------------------------------ dağıtımcı ve perakende: kanalda bekleyen stok


def period_days(p: dict[str, Any]) -> tuple[date, date]:
    """Dönemin gün aralığı [1 Ocak, son gün]: veri sonunun ayı seçiliyse veri sonu, değilse ayın son günü."""
    y, a = p["yil"], p["ay"]
    end = date(y, a, calendar.monthrange(y, a)[1])
    if p.get("veriSonu"):
        vs = date.fromisoformat(p["veriSonu"])
        if vs.year == y and vs.month == a:
            end = vs
    return date(y, 1, 1), end


def _dagitimci_satis(engine: sa.engine.Engine, tenant: str, p: dict[str, Any], code: Optional[str],
                     yil: int) -> Optional[dict[str, Any]]:
    """Dağıtımcı carisinin dönem sell-in'i (yıl okumasından); okunmamışsa ya da cari kodu değiştiyse None."""
    from semantic_bridge.channels.refresh import DAGITIMCI_META

    m = S.meta_get(engine, tenant, f"{DAGITIMCI_META}{yil}")
    if not code or m.get("cari") != code or "rows" not in m:
        return None
    acc = zero()
    w = _window(p, yil)
    for r in m["rows"]:
        wt = w.get(int(r.get("ay") or 0))
        if wt:
            add(acc, r, wt)
    return derive(acc)


def dagitimci(engine: sa.engine.Engine, tenant: str, p: dict[str, Any],
              dr_metrics: Optional[dict[str, float]] = None) -> dict[str, Any]:
    """Karnenin «dağıtımcı ve perakende» bloğu: kanala satış (Logo sell-in) yanında kanalda bekleyen stok (M39
    dağıtımcı katalogları, TİMAŞ grubu, son görüntü) ve Başarı deposundan çıkış (iki görüntü birikince).

    - Başarı Dağıtım: sell-in = ayardaki Başarı carisine faturalı satış − iade (kanal okumasında ayrıca okunur, platform
      toplamlarına girmez); stok = Başarı deposu.
    - D&R: sell-in = karnedeki D&R platformu; stok = Prefix B2B stoğu ve D&R + İdefix site stoğu.
    Stok kaynağı okunmamışsa ya da hata verirse karne düşmez; blok nedeni yazar."""
    from semantic_bridge.channels.sources import dagitimci_cari

    code = dagitimci_cari()
    kart = S.meta_get(engine, tenant, "dagitimci_kart")
    y = p["yil"]
    satis = _dagitimci_satis(engine, tenant, p, code, y)
    has_ly = (y - 1) in _read_years(engine, tenant)
    gecen = _dagitimci_satis(engine, tenant, p, code, y - 1) if has_ly else None
    bas, son = period_days(p)
    stok: Optional[dict[str, Any]] = None
    hata = None
    try:
        from semantic_bridge import pazar_dagitim as PD

        stok = PD.kanal_stok(engine, tenant, bas=bas, son=son)
    except Exception as e:  # noqa: BLE001 — dağıtımcı stoğu karneyi düşürmez
        hata = f"Dağıtımcı katalogları okunamadı: {str(e)[:160]}"
    dr_sell = derive(dr_metrics) if dr_metrics else None
    return {
        "basari": {"label": "Başarı Dağıtım", "cari": code, "unvan": kart.get("unvan") if kart.get("cari") == code else None,
                   "kanalaSatis": satis, "gecenYil": gecen,
                   "degisim": change(satis["netCiro"], gecen["netCiro"]) if satis and gecen else None,
                   "satisOkundu": satis is not None, "stok": (stok or {}).get("basari"),
                   "cikis": (stok or {}).get("cikis"), "cikisNot": (stok or {}).get("cikisNot")},
        "dr": {"label": platform_label("dr"), "platform": "dr", "kanalaSatis": dr_sell, "stok": (stok or {}).get("dr")},
        "donem": {"bas": bas.isoformat(), "son": son.isoformat()},
        "sonGoruntu": (stok or {}).get("sonGoruntu"), "hata": hata,
        "notlar": {"endeks": (stok or {}).get("not"), "timas": (stok or {}).get("timasNot"), "dr": (stok or {}).get("drNot")},
    }


# ------------------------------------------------------------------ kanal detayı


def _check_platform(platform: str) -> None:
    if platform not in M.PLATFORMS and platform != M.UNMAPPED:
        raise ChannelError("Bilinmeyen platform.", 404)


def channel(engine: sa.engine.Engine, tenant: str, platform: str, yil: Optional[int] = None, ay: Optional[int] = None,
            unit_costs: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]] = None) -> dict[str, Any]:
    _check_platform(platform)
    p = period(engine, tenant, yil, ay)
    y, ly = p["yil"], p["yil"] - 1
    need_read(engine, tenant, [y])
    has_ly = ly in _read_years(engine, tenant)
    mp = Mapping(engine, tenant)
    extra = M.extra_costs(engine, tenant).get(platform)
    cari = [r for r in _months(engine, tenant, S.CARI_MONTHS, [y, ly]) if mp.platform(r.grup) == platform]
    w, wly = _window(p, y), _window(p, ly)
    cur = _sum([r for r in cari if r.yil == y], lambda r: "x", w).get("x", zero())
    prev = _sum([r for r in cari if r.yil == ly], lambda r: "x", wly).get("x") if has_ly else None

    monthly = []
    by_m = defaultdict(zero)
    for r in cari:
        add(by_m[(r.yil, r.ay)], r._mapping)
    for m in range(1, 13):
        a = by_m.get((y, m))
        b = by_m.get((ly, m))
        monthly.append({"ay": m, "ayAdi": AY[m - 1], "buYil": derive(a) if a and m <= p["ay"] else None,
                        "gecenYil": derive(b) if b else None})

    per_group = _sum([r for r in cari if r.yil == y], lambda r: r.grup, w)
    orders = S.meta_get(engine, tenant, "crm_orders")
    groups = sorted(set(per_group) | {k for k, v in mp.amap.items() if v == platform})
    cariler = []
    for g in groups:
        card = mp.cards.get(g) or {}
        o = (orders.get("byRef") or {}).get(str(card.get("ref"))) if card.get("ref") is not None else None
        cariler.append({"grup": g, "ad": mp.label(g), "kanal": card.get("kanal"), "donem": derive(per_group.get(g, zero())),
                        "crmSiparis": o})
    cariler.sort(key=lambda x: -x["donem"]["netCiro"])

    out = {"platform": platform, "label": platform_label(platform), "period": p, "gecenYilOkundu": has_ly,
           "donem": derive(cur, extra), "gecenYil": derive(prev) if prev else None,
           "degisim": change(cur["satis_ciro"] - cur["iade_ciro"], (prev["satis_ciro"] - prev["iade_ciro"]) if prev else None),
           "aylik": monthly, "cariler": cariler, "crmSiparisGun": orders.get("days"),
           "hedef": targets_by_platform(engine, tenant, p, mp).get(platform)}
    if unit_costs is not None:
        out["donem"]["m9"] = m9_fill(engine, tenant, platform, p, mp, unit_costs)
    if platform == "dr":
        # D&R: kanalda bekleyen stok (Prefix B2B ve site stoğu, TİMAŞ grubu) sell-in'in yanında.
        try:
            from semantic_bridge import pazar_dagitim as PD

            ks = PD.kanal_stok(engine, tenant)
            out["dagitimStok"] = {"dr": ks.get("dr"), "sonGoruntu": ks.get("sonGoruntu"), "not": ks.get("drNot"),
                                  "timasNot": ks.get("timasNot"), "hata": None}
        except Exception as e:  # noqa: BLE001 — stok okunamazsa kanal detayı düşmez
            out["dagitimStok"] = {"dr": None, "hata": f"D&R kataloğu okunamadı: {str(e)[:160]}"}
    return out


def _book_rows(engine: sa.engine.Engine, tenant: str, yil: int, groups: Optional[list[str]] = None,
               months: Optional[Iterable[int]] = None) -> list[Any]:
    """Grup × kitap × ay önbelleği. `groups` verilirse yalnız o grupların satırları, `months` verilirse yalnız o aylar
    (hız, 2026-09-29: tek platformun kitap listesi yılın bütün e-ticaret satırlarını okuyup Python'da süzüyordu, Amazon
    kitap listesi 4,3 sn). Süzgeç hesabın zaten atladığı satırları okumaz; sonuç aynı."""
    t = S.BOOK_MONTHS
    q = sa.select(t).where(t.c.tenant_id == tenant, t.c.yil == yil)
    if months is not None:
        q = q.where(t.c.ay.in_(sorted({int(m) for m in months})))
    with engine.connect() as c:
        if groups is None:
            return c.execute(q).all()
        out: list[Any] = []
        for i in range(0, len(groups), 500):
            out += c.execute(q.where(t.c.grup.in_(groups[i:i + 500]))).all()
        return out


def _platform_groups(mp: Mapping, platform: str) -> Optional[list[str]]:
    """`mp.platform(grup) == platform` olan gruplar: onaylı cari kodları ve platforma eşlenen kanal kodları
    (`#K:<kod>`). Eşlenmemiş sütun (onaysız her grup) önceden sayılamaz: None → bütün satırlar okunur, Python süzer."""
    if platform == M.UNMAPPED:
        return None
    out = {g for g, p in mp.amap.items() if p == platform and not g.startswith(KANAL_PREFIX)}
    out |= {KANAL_PREFIX + k for k, p in mp.kmap.items() if p == platform}
    return sorted(out)


def _platform_book_rows(engine: sa.engine.Engine, tenant: str, yil: int, mp: Mapping, platform: str,
                        weights: dict[int, float]) -> list[Any]:
    """Platformun, ağırlığı olan aylardaki kitap satırları (`_book_sum` ağırlıksız ayı ve başka platformu zaten atlar)."""
    return _book_rows(engine, tenant, yil, _platform_groups(mp, platform), [m for m, w in weights.items() if w])


def _book_sum(rows: Iterable[Any], weights: dict[int, float], keep: Callable[[Any], bool]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: {k: 0.0 for k in BOOK_METRICS})
    for r in rows:
        wt = weights.get(r.ay)
        if not wt or not keep(r):
            continue
        d = out[r.stok_kodu]
        for k in BOOK_METRICS:
            d[k] += float(getattr(r, k) or 0) * wt
    return out


def _book_view(code: str, m: dict[str, float], name: str) -> dict[str, Any]:
    net_c = m["satis_ciro"] - m["iade_ciro"]
    kar = m["maliyetli_ciro"] - m["maliyet"]
    return {"stokKodu": code, "ad": name, "satisAdet": round(m["satis_adet"], 2), "iadeAdet": round(m["iade_adet"], 2),
            "netAdet": round(m["satis_adet"] - m["iade_adet"], 2), "netCiro": round(net_c, 2),
            "iadeOrani": _ratio(m["iade_adet"], m["satis_adet"]), "brutKar": round(kar, 2),
            "marj": _ratio(kar, m["maliyetli_ciro"]), "maliyetsizAdet": round(m["maliyetsiz_adet"], 2)}


def m9_fill(engine: sa.engine.Engine, tenant: str, platform: str, p: dict[str, Any], mp: Mapping,
            unit_costs: Callable[[list[str]], dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Maliyetsiz satırları M9 birim maliyetiyle tamamlar. Birim maliyeti bilinmeyen kitap dışarıda kalır ve sayılır."""
    w = _window(p, p["yil"])
    books = _book_sum(_platform_book_rows(engine, tenant, p["yil"], mp, platform, w), w, lambda r: mp.platform(r.grup) == platform)
    need = sorted(k for k, v in books.items() if v["maliyetsiz_adet"] > 0)
    costs = unit_costs(need) if need else {}
    base_c = sum(v["maliyetli_ciro"] for v in books.values())
    base_m = sum(v["maliyet"] for v in books.values())
    add_c = add_m = 0.0
    unknown_c = 0.0
    unknown_n = 0
    sources: dict[str, int] = defaultdict(int)
    for code in need:
        v = books[code]
        hit = costs.get(code) or {}
        unit = hit.get("maliyet")
        if unit is None:
            unknown_c += v["maliyetsiz_ciro"]
            unknown_n += 1
            continue
        add_c += v["maliyetsiz_ciro"]
        add_m += v["maliyetsiz_adet"] * float(unit)
        sources[str(hit.get("kaynak") or "")] += 1
    tot_c, tot_m = base_c + add_c, base_m + add_m
    return {"tamamlananCiro": round(add_c, 2), "tamamlananMaliyet": round(add_m, 2), "marj": _ratio(tot_c - tot_m, tot_c),
            "kapsam": _ratio(tot_c, sum(v["satis_ciro"] for v in books.values())),
            "bilinmeyenKitap": unknown_n, "bilinmeyenCiro": round(unknown_c, 2), "kaynaklar": dict(sources)}


def books(engine: sa.engine.Engine, tenant: str, platform: str, yil: Optional[int] = None, ay: Optional[int] = None,
          q: str = "", sort: str = "netCiro", page: int = 0, size: int = PAGE) -> dict[str, Any]:
    _check_platform(platform)
    p = period(engine, tenant, yil, ay)
    need_read(engine, tenant, [p["yil"]])
    mp = Mapping(engine, tenant)
    w = _window(p, p["yil"])
    agg = _book_sum(_platform_book_rows(engine, tenant, p["yil"], mp, platform, w), w, lambda r: mp.platform(r.grup) == platform)
    names = S.book_names(engine, tenant, list(agg))
    rows = [_book_view(k, v, names.get(k, "")) for k, v in agg.items()]
    rows = _search(rows, q)
    key = sort if sort in ("netCiro", "netAdet", "iadeAdet", "iadeOrani", "satisAdet", "marj") else "netCiro"
    rows.sort(key=lambda r: (-(r[key] if r[key] is not None else -math.inf), r["stokKodu"]))
    return _page(rows, page, {"period": p, "platform": platform, "sort": key}, size)


def returns(engine: sa.engine.Engine, tenant: str, platform: str, yil: Optional[int] = None, ay: Optional[int] = None,
            months: int = 3, page: int = 0, size: int = PAGE) -> dict[str, Any]:
    """Son `months` ayda (seçilen ay dahil) en çok iade edilen kitaplar."""
    _check_platform(platform)
    p = period(engine, tenant, yil, ay)
    months = max(1, min(24, int(months)))
    idx = p["yil"] * 12 + p["ay"] - 1
    span = [((i // 12), (i % 12) + 1) for i in range(idx - months + 1, idx + 1)]
    years = sorted({y for y, _ in span})
    need_read(engine, tenant, years)
    mp = Mapping(engine, tenant)
    agg: dict[str, dict[str, float]] = {}
    for yy in years:
        wts = {m: 1.0 for (y2, m) in span if y2 == yy}
        part = _book_sum(_platform_book_rows(engine, tenant, yy, mp, platform, wts), wts, lambda r: mp.platform(r.grup) == platform)
        for k, v in part.items():
            cur = agg.setdefault(k, {kk: 0.0 for kk in BOOK_METRICS})
            for kk in BOOK_METRICS:
                cur[kk] += v[kk]
    names = S.book_names(engine, tenant, list(agg))
    rows = [_book_view(k, v, names.get(k, "")) for k, v in agg.items() if v["iade_adet"] > 0]
    rows.sort(key=lambda r: (-r["iadeAdet"], r["stokKodu"]))
    first = span[0]
    return _page(rows, page, {"period": p, "platform": platform, "aralik": {"bas": f"{first[0]}-{first[1]:02d}",
                                                                           "bit": f"{p['yil']}-{p['ay']:02d}", "ay": months}}, size)


def _search(rows: list[dict[str, Any]], q: str) -> list[dict[str, Any]]:
    words = M.fold(q).split()
    if not words:
        return rows
    return [r for r in rows if all(w in M.fold(f"{r['stokKodu']} {r.get('ad') or ''}") for w in words)]


def _page(rows: list[dict[str, Any]], page: int, extra: dict[str, Any], size: int = PAGE) -> dict[str, Any]:
    """Sayfa; `size` dışa aktarımda bütün satırlar için büyütülür (kesme yok, toplam her zaman yazılır)."""
    page = max(0, int(page))
    size = max(1, int(size))
    return {**extra, "items": rows[page * size:(page + 1) * size], "total": len(rows), "page": page, "pageSize": size}


# ------------------------------------------------------------------ kitap × kanal matrisi


def matrix(engine: sa.engine.Engine, tenant: str, yil: Optional[int] = None, ay: Optional[int] = None, q: str = "",
           page: int = 0, sort: str = "", size: int = PAGE) -> dict[str, Any]:
    """Satır = kitap, sütun = platform; hücre = net adet, alım (satış) adedi, iade adedi. Sıralama toplam net adede ya da
    bir platformun net adedine göre. Sayfa 100 satır; hepsi sayfalanarak görülür (sessiz tavan yok)."""
    p = period(engine, tenant, yil, ay)
    need_read(engine, tenant, [p["yil"]])
    key = (id(engine), tenant, p["yil"], p["ay"], p["gunPayi"], _girdi_damgasi(engine, tenant, p["yil"]))
    base = _MATRIS.al(key, lambda: _matrix_base(engine, tenant, p))
    Y.aktar(base["queries"])                     # sorgu bilgisi: matrisi kuran okumalar (bellekten gelse de)
    words = M.fold(q).split()
    rows = [r for r, t in zip(base["rows"], base["fold"]) if all(w in t for w in words)] if words else list(base["rows"])
    cols = [c["platform"] for c in base["columns"]]
    if sort and sort in cols:
        rows.sort(key=lambda r: (-(r["kanallar"].get(sort, {}).get("net", 0.0)), r["stokKodu"]))
    return _page(rows, page, {"period": p, "columns": base["columns"], "sort": sort if sort in cols else ""}, size)


#: Matris hesabı (hız 4. tur, 2026-09-29): yılın kitap × grup × ay satırları (≈46 bin) her açılışta okunup platformlara
#: dağıtılıyordu (tek başına 0,8–1 sn, eşzamanlı açılışta 3–10 sn). Sonuç girdilerin damgasına bağlı süreçte tutulur;
#: arama, sıralama ve sayfa istekte. Damga değişmedikçe aynı girdi aynı matrisi verir; değişince ilk istek yeniden kurar.
_MATRIS = HB.Bellek("kanal.matris", taze=float("inf"), en_cok=16)


def _girdi_damgasi(engine: sa.engine.Engine, tenant: str, yil: int) -> str:
    """Matrise giren tabloların tek sorguda damgası: Logo okuma kaydı (meta: okuma turu, veri sonu), eşleme ayarları
    (kanal kodu → platform), onaylı cari eşlemesi, yılın kitap satırı sayısı ve kitap adları. Okuma turu meta'yı, eşleme
    kararı onaylı cariyi (onay anı / sayı) ya da ayarı günceller. Onaysız aday satırları (Zeki AI önerisi, sürekli
    yazılır) matrise girmediği için damgaya da girmez."""
    def cnt(t: sa.Table, *cond: Any) -> Any:
        return sa.select(sa.func.count()).select_from(t).where(t.c.tenant_id == tenant, *cond).scalar_subquery()

    def mx(col: Any, t: sa.Table, *cond: Any) -> Any:
        return sa.select(sa.func.max(col)).where(t.c.tenant_id == tenant, *cond).scalar_subquery()

    A = S.ACCOUNTS
    ok = A.c.durum == "onayli"
    stmt = sa.select(cnt(S.META), mx(S.META.c.updated_at, S.META), cnt(S.SETTINGS), mx(S.SETTINGS.c.guncellendi, S.SETTINGS),
                     cnt(A, ok), mx(A.c.onay_tarihi, A, ok), mx(A.c.platform, A, ok),
                     cnt(S.BOOK_MONTHS, S.BOOK_MONTHS.c.yil == yil), cnt(S.BOOKS))
    with Y.ayri(), engine.connect() as c:          # damga okuması sorgu bilgisine girmez (rakam üretmez)
        row = c.execute(stmt).first()
    return json.dumps([str(v) for v in (row or ())])


def _matrix_base(engine: sa.engine.Engine, tenant: str, p: dict[str, Any]) -> dict[str, Any]:
    with Y.ayri(engine) as yq:
        base = _matrix_rows(engine, tenant, p)
    base["queries"] = list(yq.queries)
    return base


def _matrix_rows(engine: sa.engine.Engine, tenant: str, p: dict[str, Any]) -> dict[str, Any]:
    mp = Mapping(engine, tenant)
    w = _window(p, p["yil"])
    cells: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for r in _book_rows(engine, tenant, p["yil"]):
        wt = w.get(r.ay)
        if not wt:
            continue
        plat = mp.platform(r.grup)
        if plat == "degil":
            continue
        c = cells[r.stok_kodu][plat]
        c[0] += float(r.satis_adet or 0) * wt
        c[1] += float(r.iade_adet or 0) * wt
    totals: dict[str, float] = defaultdict(float)
    for per in cells.values():
        for plat, (s, i) in per.items():
            totals[plat] += s - i
    cols = [k for k in M.CARD_PLATFORMS + [M.UNMAPPED] if k in totals]
    cols.sort(key=lambda k: (k == M.UNMAPPED, -totals[k]))
    names = S.book_names(engine, tenant, list(cells))
    rows = []
    for code, per in cells.items():
        vals = {k: {"alim": round(s, 2), "iade": round(i, 2), "net": round(s - i, 2)} for k, (s, i) in per.items()}
        total = sum(v["net"] for v in vals.values())
        rows.append({"stokKodu": code, "ad": names.get(code, ""), "toplam": round(total, 2), "kanallar": vals})
    rows.sort(key=lambda r: (-r["toplam"], r["stokKodu"]))          # varsayılan sıra; platform sırası istekte
    return {"rows": rows, "fold": [M.fold(f"{r['stokKodu']} {r.get('ad') or ''}") for r in rows],
            "columns": [{"platform": k, "label": platform_label(k), "net": round(totals[k], 2)} for k in cols]}


# ------------------------------------------------------------------ hedef ↔ gerçekleşen


def targets_by_platform(engine: sa.engine.Engine, tenant: str, p: dict[str, Any], mp: Optional[Mapping] = None) -> dict[str, dict[str, Any]]:
    """CRM bölge hedefi (adet) → platform. Beklenen = yıllık hedefin geçen aylara düşen payı (son ay gün oranıyla);
    gerçekleşen = platformun net adedi."""
    rmap = M.region_map(engine, tenant)
    if not rmap:
        return {}
    with engine.connect() as c:
        rows = c.execute(sa.select(S.TARGETS).where(S.TARGETS.c.tenant_id == tenant, S.TARGETS.c.yil == p["yil"])).all()
    if not rows:
        return {}
    mp = mp or Mapping(engine, tenant)
    months: dict[str, list[float]] = defaultdict(lambda: [0.0] * 12)
    regions: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        plat = rmap.get(r.bolge)
        if not plat:
            continue
        for i, v in enumerate(S.jload(r.aylar_json, [0.0] * 12)):
            months[plat][i] += float(v or 0)
        regions[plat].append(r.bolge_ad or r.bolge)
    actual: dict[str, list[float]] = defaultdict(lambda: [0.0] * 12)
    for r in _months(engine, tenant, S.CARI_MONTHS, [p["yil"]]):
        actual[mp.platform(r.grup)][r.ay - 1] += float(r.satis_adet or 0) - float(r.iade_adet or 0)
    w = _elapsed(p)
    out = {}
    for plat, m in months.items():
        expected = sum(m[i - 1] * wt for i, wt in w.items())
        got = sum(actual[plat][i - 1] for i in w)
        out[plat] = {"kaynak": "CRM satış hedefi (adet)", "bolgeler": regions[plat], "yillik": round(sum(m), 2),
                     "beklenen": round(expected, 2), "gerceklesen": round(got, 2), "oran": _ratio(got, expected),
                     "aylik": [{"ay": i + 1, "hedef": round(m[i], 2), "gercek": round(actual[plat][i], 2) if i + 1 <= p["ay"] else None}
                               for i in range(12)]}
    return out


def targets(engine: sa.engine.Engine, tenant: str, yil: Optional[int] = None,
            m46: Optional[Callable[[int], dict[str, Any]]] = None) -> dict[str, Any]:
    """Hedef ↔ gerçekleşen: CRM bölge hedefi (adet) ve M46 onaylı kitap hedefinden türetilen kanal hedefi.

    M46 türetmesi: kitabın onaylı hedefi × kanalın geçen yıl o kitaptaki net adet payı (kitap geçen yıl kanalda yoksa
    kanalın şirket içindeki genel payı). Yöntem ekranda yazılır; M46'da kanal kırılımı yoktur, bu bir paylaştırmadır."""
    p = period(engine, tenant, yil, None)
    need_read(engine, tenant, [p["yil"]])
    mp = Mapping(engine, tenant)
    crm = targets_by_platform(engine, tenant, p, mp)
    lab = S.meta_get(engine, tenant, "target_labels")
    rmap = M.region_map(engine, tenant)
    with engine.connect() as c:
        trows = c.execute(sa.select(S.TARGETS).where(S.TARGETS.c.tenant_id == tenant, S.TARGETS.c.yil == p["yil"])).all()
    bolgeler = [{"kod": r.bolge, "ad": r.bolge_ad or r.bolge, "yillik": r.toplam, "satir": r.satir, "platform": rmap.get(r.bolge)}
                for r in trows]
    out: dict[str, Any] = {"period": p, "crm": crm, "bolgeler": sorted(bolgeler, key=lambda b: -b["yillik"]),
                           "crmYilKodu": (lab.get("years") or {}).get(str(p["yil"])), "m46": None}
    if m46 is not None:
        out["m46"] = _m46_targets(engine, tenant, p, mp, m46)
    return out


def _m46_targets(engine: sa.engine.Engine, tenant: str, p: dict[str, Any], mp: Mapping,
                 m46: Callable[[int], dict[str, Any]]) -> Optional[dict[str, Any]]:
    try:
        plan = m46(p["yil"])
    except Exception as e:  # noqa: BLE001 — M46 okunamazsa bu blok boş kalır, CRM hedefi yine gösterilir
        return {"hata": str(e)[:200]}
    if not plan or not plan.get("plan"):
        return {"plan": None}
    ly = p["yil"] - 1
    if ly not in _read_years(engine, tenant):
        return {"plan": plan["plan"], "hata": f"{ly} kanal satışları okunmadı; pay hesaplanamıyor."}
    # Geçen yıl: kitap × platform net adet (kanal önbelleği) ve kitabın şirket net adedi (M46 önbelleği).
    from semantic_bridge import budget as B

    plat_book: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in _book_rows(engine, tenant, ly):
        plat_book[mp.platform(r.grup)][r.stok_kodu] += float(r.satis_adet or 0) - float(r.iade_adet or 0)
    with engine.connect() as c:
        comp = {k: float(v or 0) for k, v in c.execute(sa.select(B.SALES.c.stok_kodu, sa.func.sum(B.SALES.c.adet))
                                                      .where(B.SALES.c.year == ly).group_by(B.SALES.c.stok_kodu)).all()}
    comp_total = sum(comp.values())
    w = _elapsed(p)
    res = {}
    for plat in [k for k in M.CARD_PLATFORMS if k in plat_book]:
        overall = _ratio(sum(plat_book[plat].values()), comp_total) or 0.0
        hedef_adet = hedef_ciro = beklenen = 0.0
        for it in plan.get("items") or []:
            code = it["stokKodu"]
            share = (plat_book[plat].get(code, 0.0) / comp[code]) if comp.get(code) else overall
            share = max(0.0, min(1.0, share))
            hedef_adet += (it["hedef"]["adet"] or 0) * share
            hedef_ciro += (it["hedef"]["ciro"] or 0) * share
            beklenen += sum((m["adet"] or 0) * w.get(m["ay"], 0.0) for m in it.get("aylik") or []) * share
        res[plat] = {"hedefAdet": round(hedef_adet, 2), "hedefCiro": round(hedef_ciro, 2), "beklenenAdet": round(beklenen, 2),
                     "genelPay": overall}
    # Gerçekleşen net adet (verinin bittiği güne kadar; önbellek aylık olduğundan son ay bütünüyle sayılır).
    got: dict[str, float] = defaultdict(float)
    for r in _months(engine, tenant, S.CARI_MONTHS, [p["yil"]]):
        if w.get(r.ay):
            got[mp.platform(r.grup)] += float(r.satis_adet or 0) - float(r.iade_adet or 0)
    for plat, v in res.items():
        v["gerceklesenAdet"] = round(got.get(plat, 0.0), 2)
        v["oran"] = _ratio(v["gerceklesenAdet"], v["beklenenAdet"])
    return {"plan": plan["plan"], "yontem": f"Kitap hedefi × kanalın {ly} yılındaki kitap payı (kitap o yıl kanalda yoksa kanalın genel payı)",
            "platformlar": res}


# ------------------------------------------------------------------ iskonto simülasyonu


def simulate(engine: sa.engine.Engine, tenant: str, body: dict[str, Any]) -> dict[str, Any]:
    """«Bu kanalın iskontosunu Δ puan değiştirirsem marj ne olur». Hiçbir yere yazmaz.

    Taban: seçilen dönemin kanal ölçüleri. Yeni iskonto = brüt satış × Δ/100 kadar artar (net satış o kadar düşer); adet
    değişimi (isteğe bağlı, %) brüt satışı, net satışı ve maliyeti aynı oranda değiştirir; iade oranı sabit varsayılır.
    Marj yalnız maliyetli satırlar üzerinden hesaplanır (maliyetli kısmın brüt satışı, net satış payıyla bulunur).
    Başabaş: aynı brüt kârı korumak için gereken adet değişimi."""
    platform = str(body.get("platform") or "")
    _check_platform(platform)
    try:
        delta = float(body.get("iskontoPuan"))
    except (TypeError, ValueError):
        raise ChannelError("İskonto değişimi (puan) sayı olmalı.") from None
    try:
        vol = float(body.get("hacimYuzde") or 0)
    except (TypeError, ValueError):
        raise ChannelError("Adet değişimi (%) sayı olmalı.") from None
    if not -50 <= delta <= 50 or not -90 <= vol <= 500:
        raise ChannelError("Değişim makul aralıkta değil (iskonto ±50 puan, adet −%90 … +%500).")
    ch = channel(engine, tenant, platform, body.get("yil"), body.get("ay"))
    d = ch["donem"]
    B, N, R = d["brutSatis"], d["satisCiro"], d["iadeCiro"]
    Nc, C = d["maliyetliCiro"], d["maliyet"]
    if B <= 0 or N <= 0:
        raise ChannelError("Bu dönemde kanalın satışı yok; simülasyon yapılamaz.")
    Bc = B * (Nc / N) if N else 0.0
    f = 1 + vol / 100
    iade_orani = R / N if N else 0.0
    N2 = (N - B * delta / 100) * f
    Nc2 = (Nc - Bc * delta / 100) * f
    C2 = C * f
    kar1, kar2 = Nc - C, Nc2 - C2
    unit_margin = Nc - Bc * delta / 100 - C
    breakeven = (kar1 / unit_margin - 1) if unit_margin > 0 else None

    def row(n: float, nc: float, cst: float, disc: float, gross: float) -> dict[str, Any]:
        return {"brutSatis": round(gross, 2), "iskonto": round(disc, 2), "iskontoOrani": _ratio(disc, gross),
                "netSatis": round(n, 2), "iade": round(n * iade_orani, 2), "netCiro": round(n * (1 - iade_orani), 2),
                "maliyetliCiro": round(nc, 2), "maliyet": round(cst, 2), "brutKar": round(nc - cst, 2), "marj": _ratio(nc - cst, nc)}

    return {"platform": platform, "label": ch["label"], "period": ch["period"], "iskontoPuan": delta, "hacimYuzde": vol,
            "once": row(N, Nc, C, d["iskonto"], B),
            "sonra": row(N2, Nc2, C2, (d["iskonto"] + B * delta / 100) * f, B * f),
            "fark": {"brutKar": round(kar2 - kar1, 2), "netCiro": round((N2 - N) * (1 - iade_orani), 2),
                     "marjPuan": ((_ratio(kar2, Nc2) or 0) - (_ratio(kar1, Nc) or 0)) * 100 if Nc2 and Nc else None},
            "basabasHacim": breakeven, "maliyetKapsami": d["maliyetKapsami"], "maliyetsizCiro": d["maliyetsizCiro"],
            "varsayim": "İade oranı ve maliyet yapısı dönem ortalamasında sabit; marj yalnız maliyeti girilmiş satırlarda."}


def facts_text(sim: dict[str, Any]) -> str:
    """Model yorumu için hesap özeti (rakamlar hesaptan)."""
    o, s = sim["once"], sim["sonra"]

    def pct(x: Optional[float]) -> str:
        return "—" if x is None else f"%{x * 100:.1f}".replace(".", ",")

    return (f"Kanal: {sim['label']}. Dönem: {sim['period']['yil']} Ocak–{sim['period']['ayAdi']}. "
            f"İskonto değişimi: {sim['iskontoPuan']:+.1f} puan; adet değişimi: %{sim['hacimYuzde']:+.1f}. "
            f"İskonto oranı {pct(o['iskontoOrani'])} → {pct(s['iskontoOrani'])}; brüt marj {pct(o['marj'])} → {pct(s['marj'])}. "
            f"Brüt kâr değişimi {sim['fark']['brutKar']:,.0f} TL. "
            + (f"Aynı brüt kâr için gereken adet değişimi {pct(sim['basabasHacim'])}." if sim["basabasHacim"] is not None else ""))


def as_json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def sell_in_books(engine: sa.engine.Engine, tenant: str, platform: str, months: list[tuple[int, int]]) -> dict[str, float]:
    """Platforma verilen aylarda kitap başına net adet (kanala satış − kanaldan iade)."""
    mp = Mapping(engine, tenant)
    out: dict[str, float] = defaultdict(float)
    for yy in sorted({y for y, _ in months}):
        wts = {m: 1.0 for (y2, m) in months if y2 == yy}
        for code, v in _book_sum(_platform_book_rows(engine, tenant, yy, mp, platform, wts), wts,
                                 lambda r: mp.platform(r.grup) == platform).items():
            out[code] += v["satis_adet"] - v["iade_adet"]
    return dict(out)


def months_between(bas: str, bit: str) -> list[tuple[int, int]]:
    y1, m1 = int(bas[:4]), int(bas[5:7])
    y2, m2 = int(bit[:4]), int(bit[5:7])
    out = []
    i, j = y1 * 12 + m1 - 1, y2 * 12 + m2 - 1
    for k in range(i, j + 1):
        out.append((k // 12, k % 12 + 1))
    return out
