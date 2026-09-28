"""M15 Yeni kitap pazarlama planı: plan bekleyen kitap listesi, kitap karnesi, kanal/bütçe önerisi, takvim, materyal
taslakları, «CRM'e işlenecek» listesi, günlük hatırlatma.

**Yayın günü** CRM'de üç yerde: kitap kartı ilk baskı tarihi, bağlı projenin yayın tarihi, ilk baskının üretim kartı
(depo girişi gerçekleşmişse o, yoksa dağılım planı). Esas alınan sıra Yönetim → Pazarlama → «Yayın günü önceliği»
(`MARKETING_PUBLISH_DATE_ORDER`, varsayılan `crm-kitap,crm-proje,uretim`): M46 hedefleri, M10 ilk baskı tahmini ve
Baskı Öneri aynı alanı (kitap kartı ilk yayın) okur; plan hedefle aynı günü görsün diye önce o. Üçü de ekranda
kaynağıyla görünür; plan sahibi elle değiştirebilir (kaynak «elle»).

**Karne rakamları** SQL'den ve mevcut veri kümelerinden gelir, model rakam üretmez:
- Emsaller: M10 İlk baskı tahmininin veri kümesi (CRM emsal bağı + M10'un benzerlik puanıyla seçtiği emsaller; ilk
  3/6/12 ay net adet, iade düşülmüş, Baskı Öneri ile aynı satış satırları). Bu modül emsal hesabını yeniden yazmaz.
- Yazar geçmişi ve yıllık satış: M46'nın Logo gerçekleşme önbelleği (`semantic_budget_sales_actuals`: faturalı satır,
  net adet, net ciro = LINENET).
- Hedef: M46 yürürlükteki planı (`budget.approved_targets`).

**Bütçe çerçevesi** (kitap bazlı pazarlama bütçesi M46'da yok): (1) plan sahibinin elle girdiği tutar; yoksa (2) CRM
proje kartındaki «Toplam Pazarlama Bütçesi» (önce kurul sonucu alanı); yoksa (3) oran × kitabın M46 hedef cirosu. Oran
Yönetim → Pazarlama «Kitap bütçesi oranı» (yüzde) girilmişse odur; girilmemişse veriden: son tam yılda pazarlama
masraf merkezlerinin Logo gideri ÷ aynı yılın şirket net cirosu (M46 gider/satış önbelleği). Hiçbiri yoksa çerçeve
boş kalır, satırlar sıfır tutarla gelir ve ekran «çerçeve yok» der (sayı uydurulmaz).

**Kanal payı**: emsal kitapların CRM «Pazarlama Bütçe Modülü» harcamasının kanal dağılımı; emsalde kayıt yoksa son
`MARKETING_CHANNEL_LOOKBACK_YEARS` yılın şirket geneli dağılımı; o da yoksa kanal önerilmez. Zeki AI yalnız gerekçe
cümlesini yazar.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import budget as B
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import guard as G
from semantic_bridge.marketing.sources import Crm, FIELD_LABELS, SourceError

log = logging.getLogger("semantic.marketing")

PAGE_SIZE = 100
DATE_KEYS = ("crm-kitap", "crm-proje", "uretim")
#: Kanal satırının varsayılan penceresi (yayın gününe göre gün); şablondur, satırda değiştirilir.
CHANNEL_WINDOW = {"basin": (-30, 30), "medya": (-14, 45), "promosyon": (0, 60), "sosyal-medya": (-21, 60),
                  "dijital": (-7, 60), "satis-kampanyasi": (0, 30), "etkinlik": (0, 90), "influencer": (-14, 30),
                  "diger": (-30, 60)}
#: Takvim şablonu: (yayın gününe göre gün, iş, kanal, materyal türü). Yönetim → Pazarlama → «Takvim şablonu» (JSON)
#: ile değiştirilir. Dış kanala gönderim/yayın işleri insanındır; sistem yalnız kaydeder.
DEFAULT_TASKS: list[tuple[int, str, Optional[str], Optional[str]]] = [
    (-60, "Pazarlama planını onaya gönder", None, None),
    (-45, "Tanıtım föyü metnini onayla", None, "foy"),
    (-45, "Kapak ve görsel brief'ini grafiğe ver", None, "kapak-brief"),
    (-30, "Basın bültenini onayla", "basin", "basin-bulteni"),
    (-30, "Satış ekibine plan özetini ilet (PDF)", "satis-kampanyasi", None),
    (-21, "Sosyal medya gönderi takvimini hazırla", "sosyal-medya", "sosyal"),
    (-14, "Basın listesine bülteni gönder (gönderimi ekip yapar)", "basin", "basin-bulteni"),
    (-14, "E-bülten konu satırını onayla", "dijital", "e-bulten-konu"),
    (-7, "Tanıtım videosu senaryosunu onayla", "sosyal-medya", "video-senaryo"),
    (0, "Yayın günü: onaylı sosyal gönderileri yayımla (yayını ekip yapar)", "sosyal-medya", "sosyal"),
    (7, "İlk hafta satışını değerlendir", None, None),
    (30, "İlk ay değerlendirmesi: plan tuttu mu", None, None),
]
#: CRM «Pazarlama Tipi» adı (katlanmış) → kanal.
TIP_TO_CHANNEL = {"basin": "basin", "medya": "medya", "promosyon": "promosyon", "sosyal medya": "sosyal-medya",
                  "dijital pazarlama": "dijital", "dijital": "dijital", "satis kampanyasi": "satis-kampanyasi",
                  "etkinlik": "etkinlik", "influencer": "influencer"}
EMSAL_CHOICES = ["Evet, emsal", "Hayır, emsal değil", "Belirsiz"]


# ------------------------------------------------------------------ ayarlar


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    def num(key: str, default: Optional[float]) -> Optional[float]:
        raw = (conf(key) or "").strip().replace(",", ".")
        if not raw:
            return default
        try:
            v = float(raw)
        except ValueError:
            return default
        return v if math.isfinite(v) else default

    def lst(key: str, default: str) -> list[str]:
        return [x.strip() for x in ((conf(key) or "").strip() or default).split(",") if x.strip()]

    order = [x for x in lst("MARKETING_PUBLISH_DATE_ORDER", ",".join(DATE_KEYS)) if x in DATE_KEYS]
    tasks = DEFAULT_TASKS
    raw = (conf("MARKETING_TASK_TEMPLATE") or "").strip()
    if raw:
        try:
            parsed = C.loads(raw, None)
            tasks = [(int(t[0]), str(t[1]), t[2] or None, t[3] or None) for t in parsed if len(t) >= 4] or DEFAULT_TASKS
        except (TypeError, ValueError, IndexError):
            tasks = DEFAULT_TASKS
    rate = num("MARKETING_BUDGET_RATE", None)
    return {
        "horizonDays": int(num("MARKETING_HORIZON_DAYS", 120) or 120),
        "noPlanDays": int(num("MARKETING_NO_PLAN_DAYS", 60) or 60),
        "remindDays": sorted({int(x) for x in lst("MARKETING_REMIND_DAYS", "60,30,14") if x.isdigit()}, reverse=True),
        "materialDays": int(num("MARKETING_MATERIAL_DAYS", 21) or 21),
        "requiredMaterials": [x for x in lst("MARKETING_REQUIRED_MATERIALS", "foy,basin-bulteni,sosyal") if x in C.MATERIALS_KINDS],
        "threshold": num("MARKETING_UPPER_APPROVAL_THRESHOLD", None),
        "rate": None if rate is None else rate / 100.0,
        "deptCenters": lst("MARKETING_DEPT_CENTERS", ""),
        "budgetAccounts": lst("MARKETING_BUDGET_ACCOUNTS", ""),
        "lookbackYears": int(num("MARKETING_CHANNEL_LOOKBACK_YEARS", 3) or 3),
        "dateOrder": order or list(DATE_KEYS),
        "recipients": [x.strip() for x in (conf("MARKETING_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x],
        "claims": lst("MARKETING_BANNED_CLAIMS", ""),
        "minProb": num("MARKETING_CHOICE_MIN_PROB", 0.70) or 0.70,
        "minMargin": num("MARKETING_CHOICE_MIN_MARGIN", 0.30) or 0.30,
        "tasks": tasks,
    }


# ------------------------------------------------------------------ yayın günü


def resolve_pub(tarihler: dict[str, Optional[str]], order: list[str]) -> tuple[Optional[str], Optional[str]]:
    for k in order:
        if k == "uretim":
            v = tarihler.get("uretim-depo") or tarihler.get("uretim-dagilim")
        else:
            v = tarihler.get(k)
        if v:
            return v, k
    return None, None


def _days_to(d: Optional[str], ref: date) -> Optional[int]:
    return (date.fromisoformat(d) - ref).days if d else None


# ------------------------------------------------------------------ hedef (M46)


def target_for(engine: Any, tenant: str, code: str, pub: Optional[str]) -> dict[str, Any]:
    """Yayın yılının yürürlükteki M46 planındaki kitap hedefi; yoksa `planId: None` ve neden."""
    if not pub:
        return {"year": None, "planId": None, "not": "Yayın tarihi yok; hedef yılı bilinmiyor."}
    year = int(pub[:4])
    B.ensure(engine)
    t = B.approved_targets(engine, tenant, year, codes=[code], with_actuals=False)
    if not t.get("plan"):
        return {"year": year, "planId": None, "not": f"{year} bütçesi henüz onaylanmadı."}
    it = (t.get("items") or [None])[0]
    base = {"year": year, "planId": t["plan"]["id"], "version": t["plan"]["version"], "planTitle": t["plan"]["title"]}
    if not it:
        return {**base, "adet": None, "ciro": None, "marj": None, "not": "Kitap yürürlükteki bütçe planında yok."}
    return {**base, "adet": it["hedef"]["adet"], "ciro": it["hedef"]["ciro"], "marj": it["hedef"]["marj"], "aylik": it["aylik"]}


def targets_many(engine: Any, tenant: str, codes_by_year: dict[int, list[str]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    B.ensure(engine)
    for y, codes in codes_by_year.items():
        t = B.approved_targets(engine, tenant, y, codes=codes, with_actuals=False)
        if not t.get("plan"):
            continue
        # Planda olmayan kitap için de yürürlükteki planın kimliği gerekir (hedefi «yok» olarak karşılaştırmak için).
        out[f"_plan:{y}"] = {"year": y, "planId": t["plan"]["id"], "version": t["plan"]["version"], "adet": None, "ciro": None, "marj": None}
        for it in t["items"]:
            out[f"{y}:{it['stokKodu']}"] = {"year": y, "planId": t["plan"]["id"], "version": t["plan"]["version"],
                                            "adet": it["hedef"]["adet"], "ciro": it["hedef"]["ciro"], "marj": it["hedef"]["marj"]}
    return out


def target_changed(saved: Optional[dict[str, Any]], current: Optional[dict[str, Any]]) -> bool:
    """Plandaki hedef anlık görüntüsü M46'nın yürürlükteki değerinden farklı mı (plan revize edildi / hedef değişti)."""
    if not saved or not saved.get("planId"):
        return bool(current and current.get("planId"))
    if not current or not current.get("planId"):
        return True
    if saved.get("planId") != current.get("planId") or saved.get("version") != current.get("version"):
        return True
    return any(round(float(saved.get(k) or 0), 2) != round(float(current.get(k) or 0), 2) for k in ("adet", "ciro"))


# ------------------------------------------------------------------ M10 veri kümesi


def m10_engine(state: Any) -> Any:
    """M10 İlk baskı tahmininin bellekteki motoru (veri kümesi + kalibrasyon); hazır değilse None."""
    store = getattr(getattr(state, "management_reports", None), "first_print", None)
    if store is None:
        return None
    try:
        _snap, eng = store.load()
    except Exception as e:  # noqa: BLE001 — karne M10'suz da açılır
        log.warning("marketing: M10 veri kümesi okunamadı: %s", e)
        return None
    return eng


def _m10_book(eng: Any, detail: dict[str, Any]) -> Any:
    from semantic_bridge.management import ilk_baski_model as M

    b = eng.ds.books.get(detail["stokKodu"])
    if b is not None:
        return b
    return M.Book(code=detail["stokKodu"], name=detail.get("ad") or "", publisher=detail.get("yayinevi") or "",
                  library=detail.get("kitaplik") or "", authors_text=detail.get("yazar") or "",
                  audience=detail.get("hedefKitle") or "", genre_text=detail.get("turler") or "",
                  pages=M.num(detail.get("sayfa")), price=M.num(detail.get("fiyat")), first_pub=detail.get("yayin")).finish()


def _sum_first(months: list[float], h: int) -> Optional[int]:
    return round(sum(months[:h])) if len(months) >= h else None


def emsal_section(eng: Any, detail: dict[str, Any], pub: Optional[str]) -> dict[str, Any]:
    """CRM emsalleri + M10'un seçtiği emsaller, ilk 3/6/12 ay net adet (M10 veri kümesi). Tavan yok: CRM'deki bütün
    emsaller ve M10'un kullandığı bütün emsaller."""
    from semantic_bridge.management import ilk_baski as IB
    from semantic_bridge.management import ilk_baski_model as M

    if eng is None:
        return {"hazir": False, "not": "İlk baskı tahmini veri kümesi henüz hazır değil; emsaller o hazırlanınca görünür.",
                "items": [], "tahmin": None}
    ds = eng.ds
    code = detail["stokKodu"]
    b = _m10_book(eng, {**detail, "yayin": pub})
    launched = code in ds.outcomes and b.launch is not None
    launch = b.launch if launched else max(M.month_of(pub) or ds.end + 1, ds.end + 1)
    cutoff = launch - IB.GAP if launched else None
    full = None
    try:
        full = eng.full(b, launch, cutoff=cutoff)
    except Exception as e:  # noqa: BLE001
        log.warning("marketing: M10 tahmini kurulamadı (%s): %s", code, e)
    rows: dict[str, dict[str, Any]] = {}
    for c in ds.emsal.get(code, []):
        rows[c] = {"kaynak": ["CRM emsali"], "benzerlik": None, "nedenler": []}
    if full:
        hz = full["horizons"].get("12") or full["horizons"].get("6") or {}
        for a in hz.get("analogs") or []:
            r = rows.setdefault(a["code"], {"kaynak": [], "benzerlik": None, "nedenler": []})
            r["kaynak"].append("İlk baskı tahmini")
            r["benzerlik"] = a.get("score")
            r["nedenler"] = a.get("reasons") or []
    items = []
    for c, info in rows.items():
        bk = ds.books.get(c)
        o = ds.outcomes.get(c)
        months = list(o.months) if o else []
        items.append({"stokKodu": c, "ad": bk.name if bk else None, "yazar": (bk.authors_text or None) if bk else None,
                      "yayinevi": (bk.publisher or None) if bk else None, "kitaplik": (bk.library or None) if bk else None,
                      "lansman": M.ms(bk.launch) if bk and bk.launch is not None else None,
                      "ilk3": _sum_first(months, 3), "ilk6": _sum_first(months, 6), "ilk12": _sum_first(months, 12),
                      "ilk6NetTutar": round(o.net, 2) if o and len(months) >= 6 else None,
                      "gozlenenAy": len(months), **info})
    items.sort(key=lambda x: (x["ilk12"] is None, -(x["ilk12"] or 0), -(x["ilk6"] or 0), x["stokKodu"]))
    tahmin = None
    if full:
        h6, h12 = full["horizons"].get("6"), full["horizons"].get("12")
        tahmin = {"ay": full.get("launch"), "guven": h6["tier"] if h6 else None,
                  "baz6": h6["scenarios"][1]["units"] if h6 else None, "bant6": h6["band"] if h6 else None,
                  "baz12": h12["scenarios"][1]["units"] if h12 else None, "ilkBaski": (full.get("recommendation") or {}).get("units"),
                  "kanallar": (h6 or {}).get("channels") or []}
    actual = None
    if launched:
        o = ds.outcomes[code]
        actual = {"lansman": M.ms(b.launch), "aylar": [round(x) for x in o.months]}
    return {"hazir": True, "veriSonuAy": M.ms(ds.end), "crmEmsalSayisi": len(ds.emsal.get(code, [])), "items": items,
            "tahmin": tahmin, "gerceklesen": actual,
            "kaynak": "İlk baskı tahmini veri kümesi: CRM emsal bağı ve Logo aylık net satış (iade düşülmüş)."}


def author_section(engine: Any, eng: Any, detail: dict[str, Any]) -> dict[str, Any]:
    """Yazarın diğer kitapları: ilk 12 ay (M10) ve yıllık net adet/ciro (M46 Logo önbelleği)."""
    from semantic_bridge.management import ilk_baski_model as M

    want = M.parts(detail.get("yazar"))
    code = detail["stokKodu"]
    if not want:
        return {"yazar": detail.get("yazar"), "items": [], "yillar": [], "not": "CRM'de yazar yazılı değil."}
    books: dict[str, dict[str, Any]] = {}
    if eng is not None:
        for b in eng.ds.books.values():
            if b.code != code and b.authors & want:
                o = eng.ds.outcomes.get(b.code)
                books[b.code] = {"stokKodu": b.code, "ad": b.name, "ilkYayin": b.first_pub,
                                 "lansman": M.ms(b.launch) if b.launch is not None else None,
                                 "ilk12": _sum_first(list(o.months), 12) if o else None}
    B.ensure(engine)
    with engine.connect() as c:
        for r in c.execute(sa.select(B.BOOKINFO)).all():
            if r.stok_kodu != code and r.stok_kodu not in books and M.parts(r.yazar) & want:
                books[r.stok_kodu] = {"stokKodu": r.stok_kodu, "ad": r.ad, "ilkYayin": r.ilk_yayin, "lansman": None, "ilk12": None}
        codes = list(books)
        yearly: dict[str, dict[int, dict[str, float]]] = defaultdict(dict)
        if codes:
            q = (sa.select(B.SALES.c.stok_kodu, B.SALES.c.year, sa.func.sum(B.SALES.c.adet), sa.func.sum(B.SALES.c.ciro))
                 .where(B.SALES.c.stok_kodu.in_(codes)).group_by(B.SALES.c.stok_kodu, B.SALES.c.year))
            for s, y, a, ci in c.execute(q).all():
                yearly[s][int(y)] = {"adet": round(float(a or 0), 2), "ciro": round(float(ci or 0), 2)}
    years = sorted({y for v in yearly.values() for y in v})
    items = []
    for k, v in books.items():
        items.append({**v, "yillik": {str(y): yearly[k].get(y) for y in years}})
    items.sort(key=lambda x: (x.get("ilkYayin") or "", x["stokKodu"]), reverse=True)
    totals = [{"yil": y, "adet": round(sum((yearly[k].get(y) or {}).get("adet", 0) for k in books), 2),
               "ciro": round(sum((yearly[k].get(y) or {}).get("ciro", 0) for k in books), 2)} for y in years]
    return {"yazar": detail.get("yazar"), "items": items, "yillar": totals,
            "kaynak": "Logo faturalı satış (net adet, net ciro = satır net tutarı), bütçe modülünün yıllık önbelleği.",
            "sql": ("SELECT stok_kodu, year, SUM(adet), SUM(ciro) FROM semantic_budget_sales_actuals "
                    f"WHERE stok_kodu IN ({', '.join(repr(x) for x in codes)}) GROUP BY stok_kodu, year") if codes else None}


def special_days_section(days: list[dict[str, Any]], pub: Optional[str]) -> list[dict[str, Any]]:
    """Özel günün yayın gününden sonraki (ya da süren) ilk tarihi — SEO sezon takviminin tarih yöntemi."""
    from semantic_bridge.seo_geo import seasons as S

    ref = date.fromisoformat(pub) if pub else C.today()
    out = []
    for d in days:
        how = S.resolve({"name": d.get("ad"), "weekFrom": d.get("hafta1"), "weekTo": d.get("hafta2"),
                         "fixedDate": d["tarih"][5:10] if d.get("tarih") else None})
        occ = S.next_occurrence(how, ref - timedelta(days=30)) if how["method"] != "unknown" else None
        out.append({"ad": d.get("ad"), "baslangic": occ[0].isoformat() if occ else None, "bitis": occ[1].isoformat() if occ else None,
                    "yontem": how.get("why"), "kesinlik": how.get("precision")})
    out.sort(key=lambda x: (x["baslangic"] is None, x["baslangic"] or ""))
    return out


def build_card(engine: Any, tenant: str, crm: Crm, eng: Any, stok: str, st: dict[str, Any], *, fresh: bool = False) -> dict[str, Any]:
    detail = crm.book(stok, fresh=fresh)
    if detail is None:
        raise C.MarketingError("Bu stok kodunda etkin CRM kitap kartı yok.", 404)
    pub, src = resolve_pub(detail["tarihler"], st["dateOrder"])
    warnings: list[str] = []
    try:
        rivals = crm.rivals(detail["kitapId"]) if detail.get("kitapId") else []
    except SourceError as e:
        rivals, _ = [], warnings.append(f"Rakip kitaplar okunamadı: {e}")
    try:
        days = special_days_section(crm.special_days(detail["kitapId"]), pub) if detail.get("kitapId") else []
    except SourceError as e:
        days, _ = [], warnings.append(f"Özel günler okunamadı: {e}")
    emsal = emsal_section(eng, detail, pub)
    if not emsal["hazir"]:
        warnings.append(emsal["not"])
    end = B.data_end(engine)
    metinler = [{"alan": f, "ad": FIELD_LABELS.get(f, f), "metin": v} for f, v in detail["metinler"].items() if v]
    card = {
        "kitap": {k: v for k, v in detail.items() if k not in ("metinler", "proje")},
        "yayin": {"tarih": pub, "kaynak": src, "kaynakAdi": C.DATE_SOURCES.get(src or "", None), "tarihler": detail["tarihler"],
                  "oncelik": st["dateOrder"]},
        "hedef": target_for(engine, tenant, stok, pub),
        "emsal": emsal,
        "yazar": author_section(engine, eng, detail),
        "rakipler": rivals,
        "ozelGunler": days,
        "crmButce": detail.get("proje") or {},
        "metinler": metinler,
        "veriSonu": {"logo": end.isoformat() if end else None, "emsalAy": emsal.get("veriSonuAy")},
        "uyarilar": warnings,
        "kaynaklar": {
            "crm": "CRM kitap kartı, bağlı proje kartı, ilk baskının üretim kartı, rakip kitap ve özel gün bağları.",
            "hedef": "Bütçe ve hedefler modülünün yürürlükteki planı.",
        },
    }
    C.card_put(engine, tenant, stok, card, end.isoformat() if end else None)
    return C.card_get(engine, tenant, stok) or card


def card(engine: Any, tenant: str, crm: Crm, eng: Any, stok: str, st: dict[str, Any], *, fresh: bool = False) -> dict[str, Any]:
    if not fresh:
        hit = C.card_get(engine, tenant, stok)
        if hit:
            return hit
    return build_card(engine, tenant, crm, eng, stok, st, fresh=fresh)


# ------------------------------------------------------------------ bütçe önerisi (kod; model rakam üretmez)


def dept_ratio(engine: Any, st: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Son tam yılda pazarlama masraf merkezlerinin gideri ÷ şirket net cirosu (M46 önbelleği)."""
    B.ensure(engine)
    end = B.data_end(engine)
    if end is None:
        return None
    with engine.connect() as c:
        exp_years = {int(y) for y in c.execute(sa.select(sa.distinct(B.EXPENSES.c.year))).scalars().all()}
        sale_years = {int(y) for y in c.execute(sa.select(sa.distinct(B.SALES.c.year))).scalars().all()}
        full = sorted(y for y in exp_years & sale_years if y < end.year)
        if not full:
            return None
        y = full[-1]
        rows = c.execute(sa.select(B.EXPENSES).where(B.EXPENSES.c.year == y)).all()
        ciro = float(c.execute(sa.select(sa.func.coalesce(sa.func.sum(B.SALES.c.ciro), 0.0)).where(B.SALES.c.year == y)).scalar() or 0)
    centers = {x.upper() for x in st["deptCenters"]}
    accounts = tuple(st["budgetAccounts"])
    used: dict[str, str] = {}
    gider = 0.0
    for r in rows:
        match = (r.merkez_kodu.upper() in centers) if centers else ("pazarlama" in G.fold(r.merkez_adi))
        if not match or (accounts and not str(r.hesap).startswith(accounts)):
            continue
        used[r.merkez_kodu] = r.merkez_adi or r.merkez_kodu
        gider += float(r.tutar or 0)
    if gider <= 0 or ciro <= 0:
        return None
    return {"oran": gider / ciro, "yil": y, "gider": round(gider, 2), "ciro": round(ciro, 2),
            "merkezler": [{"kod": k, "ad": v} for k, v in sorted(used.items())], "hesaplar": list(accounts) or None}


def budget_frame(engine: Any, card_: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    pj = card_.get("crmButce") or {}
    for key, label in (("toplamKurul", "CRM proje kartı · Toplam pazarlama bütçesi (kurul sonucu)"),
                       ("toplam", "CRM proje kartı · Toplam pazarlama bütçesi")):
        if (pj.get(key) or 0) > 0:
            return {"tutar": round(float(pj[key]), 2), "kaynak": "crm-proje", "gerekce": f"{label}: yayın kurulunda girilen tutar."}
    hedef = card_.get("hedef") or {}
    ciro = hedef.get("ciro")
    if st.get("rate") is not None:
        rate, basis = st["rate"], {"kaynak": "ayar", "not": "Yönetim → Pazarlama → Kitap bütçesi oranı"}
    else:
        dr = dept_ratio(engine, st)
        rate, basis = (dr["oran"], {"kaynak": "veri", **dr}) if dr else (None, None)
    if rate is None:
        return {"tutar": None, "kaynak": None, "gerekce": "Bütçe çerçevesi yok: CRM proje kartında pazarlama bütçesi girilmemiş, "
                "oran ayarı boş ve Logo'da pazarlama masraf merkezi gideri okunamadı. Tutarları elle girin."}
    if not ciro:
        return {"tutar": None, "kaynak": None, "oran": basis | {"oran": rate},
                "gerekce": "Bütçe çerçevesi yok: kitabın yürürlükte onaylı satış hedefi yok (oran hedef ciroya uygulanır)."}
    pct = f"%{rate * 100:.2f}".replace(".", ",")
    why = (f"Kitabın hedef cirosu × {pct}. Oran " + ("yönetim ayarından." if basis["kaynak"] == "ayar" else
           f"{basis['yil']} yılı pazarlama masraf merkezi gideri ÷ şirket net cirosu."))
    return {"tutar": round(ciro * rate, 2), "kaynak": "oran", "oran": {**basis, "oran": rate}, "gerekce": why}


#: CRM seçenek değeri → kanal (tablo sözlüğü, 2026-09-09 dökümü: 1 Basın … 6 Satış Kampanyası).
TIP_CODE = {1: "basin", 2: "medya", 3: "promosyon", 4: "sosyal-medya", 5: "dijital", 6: "satis-kampanyasi"}


def channel_of(tip: Any, tip_adi: Optional[str]) -> str:
    try:
        if tip is not None and int(tip) in TIP_CODE:
            return TIP_CODE[int(tip)]
    except (TypeError, ValueError):
        pass
    return TIP_TO_CHANNEL.get(G.fold(tip_adi), "diger") if tip_adi else "diger"


def channel_shares(crm: Crm, emsal_codes: list[str], st: dict[str, Any], *, fresh: bool = False) -> dict[str, Any]:
    since = date(C.today().year - st["lookbackYears"], 1, 1)
    rows = crm.spend(since, fresh=fresh)
    want = set(emsal_codes)
    emsal_rows = [r for r in rows if r.get("stokKodu") in want]
    if emsal_rows:
        base, basis = emsal_rows, {"kaynak": "emsal", "kitap": len({r["stokKodu"] for r in emsal_rows}),
                                   "kayit": len({r["id"] for r in emsal_rows})}
    else:
        seen: dict[str, dict[str, Any]] = {}
        for r in rows:
            seen.setdefault(r["id"], r)
        base, basis = list(seen.values()), {"kaynak": "sirket", "kayit": len(seen), "yil": st["lookbackYears"],
                                            "baslangic": since.isoformat()}
    acc: dict[str, float] = defaultdict(float)
    for r in base:
        if (r.get("tutar") or 0) > 0:
            acc[channel_of(r.get("tip"), r.get("tipAdi"))] += float(r["tutar"])
    total = sum(acc.values())
    if total <= 0:
        return {"paylar": {}, "taban": basis | {"kayit": 0}}
    return {"paylar": {k: v / total for k, v in sorted(acc.items(), key=lambda x: -x[1])}, "taban": basis,
            "tutarlar": {k: round(v, 2) for k, v in acc.items()}}


def suggest_lines(frame: dict[str, Any], shares: dict[str, Any], pub: Optional[str]) -> list[dict[str, Any]]:
    paylar = shares.get("paylar") or {}
    if not paylar:
        return []
    total = frame.get("tutar")
    taban = shares.get("taban") or {}
    src = (f"{taban.get('kitap')} emsal kitabın CRM pazarlama bütçe kayıtları" if taban.get("kaynak") == "emsal"
           else f"son {taban.get('yil')} yılın şirket geneli CRM pazarlama bütçe kayıtları")
    lines = []
    for k, share in paylar.items():
        w = CHANNEL_WINDOW.get(k, (-30, 60))
        p = date.fromisoformat(pub) if pub else None
        amount = round(total * share) if total else 0.0
        pct = f"%{share * 100:.1f}".replace(".", ",")
        lines.append({"kanal": k, "tutar": float(amount), "baslangic": (p + timedelta(days=w[0])).isoformat() if p else None,
                      "bitis": (p + timedelta(days=w[1])).isoformat() if p else None,
                      "gerekce": f"Kanal payı {pct}: {src}." + ("" if total else " Bütçe çerçevesi olmadığı için tutar boş.")})
    if total:
        diff = round(total - sum(x["tutar"] for x in lines), 2)
        if lines and diff:
            lines[0]["tutar"] = round(lines[0]["tutar"] + diff, 2)
    return lines


# ------------------------------------------------------------------ takvim ve CRM metinleri


def template_tasks(pub: Optional[str], st: dict[str, Any], days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not pub:
        return []
    p = date.fromisoformat(pub)
    out = [{"gunFarki": g, "tarih": (p + timedelta(days=g)).isoformat(), "is": is_, "kanal": k, "materyalTur": m,
            "durum": "bekliyor", "kaynak": "sablon"} for g, is_, k, m in st["tasks"]]
    for d in days:
        if d.get("baslangic") and p - timedelta(days=30) <= date.fromisoformat(d["baslangic"]) <= p + timedelta(days=180):
            out.append({"tarih": d["baslangic"], "gunFarki": (date.fromisoformat(d["baslangic"]) - p).days,
                        "is": f"Özel gün: {d['ad']} — kitapla ilgili paylaşımı hazırla", "kanal": "sosyal-medya",
                        "materyalTur": "sosyal", "durum": "bekliyor", "kaynak": "ozel-gun"})
    return sorted(out, key=lambda x: x["tarih"])


def crm_materials(metinler: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """CRM kitap kartında yazılı metinler → (tür, metin, kaynak). Föyde önce tek satırlık alan, yoksa uzun alan."""
    by = {m["alan"]: m["metin"] for m in metinler}
    out = []
    for tur, (_label, field) in C.MATERIALS_KINDS.items():
        if not field:
            continue
        if by.get(field):
            out.append((tur, by[field], f"crm:{field}"))
        elif tur == "foy" and by.get("new_tanitimfoymetni"):
            out.append((tur, by["new_tanitimfoymetni"], "crm:new_tanitimfoymetni"))
    return out


# ------------------------------------------------------------------ plan oluşturma


def create_new_book_plan(engine: Any, tenant: str, user: str, crm: Crm, eng: Any, st: dict[str, Any],
                         body: dict[str, Any]) -> str:
    stok = str(body.get("stok_kodu") or body.get("stokKodu") or "").strip()
    if not stok:
        raise C.MarketingError("Stok kodu gerekli.")
    card_ = build_card(engine, tenant, crm, eng, stok, st, fresh=True)
    k = card_["kitap"]
    pub, src = card_["yayin"]["tarih"], card_["yayin"]["kaynak"]
    sahip = k.get("sorumluHesap") or user
    pid = C.create_plan(engine, tenant, user, kind="yeni", baslik=f"{k.get('ad') or stok} · yeni kitap pazarlama planı",
                        stok_kodu=stok, crm_kitap_id=k.get("kitapId"), crm_proje_id=k.get("projeId"), yayin_tarihi=pub,
                        yayin_kaynagi=src, hedef=card_["hedef"], sahip=sahip)
    frame = budget_frame(engine, card_, st)
    C.set_fields(engine, pid, butce_cerceve=frame.get("tutar"), butce_cerceve_json=C.dump(frame))
    tasks = template_tasks(pub, st, card_.get("ozelGunler") or [])
    if tasks:
        C.replace_tasks(engine, tenant, user, pid, tasks, system=True)
    for tur, metin, kaynak in crm_materials(card_.get("metinler") or []):
        C.add_material(engine, tenant, user, pid, tur, metin, kaynak)
    return pid


def apply_budget_suggestion(engine: Any, tenant: str, user: str, crm: Crm, plan: dict[str, Any], card_: dict[str, Any],
                            st: dict[str, Any]) -> dict[str, Any]:
    """Kural + emsal oranıyla kanal/bütçe satırları (elle düzeltilenler korunur). Dönen: çerçeve ve paylar."""
    frame = budget_frame(engine, card_, st) if (plan.get("butceCerceveKaynak") or {}).get("kaynak") != "elle" \
        else {**plan["butceCerceveKaynak"], "tutar": plan.get("butceCerceve")}
    emsal_codes = [x["stokKodu"] for x in (card_.get("emsal") or {}).get("items") or []]
    shares = channel_shares(crm, emsal_codes, st)
    lines = suggest_lines(frame, shares, plan.get("yayinTarihi"))
    C.put_suggested_lines(engine, tenant, user, plan["id"], lines)
    if frame.get("kaynak") != "elle":
        C.set_fields(engine, plan["id"], butce_cerceve=frame.get("tutar"), butce_cerceve_json=C.dump(frame))
    return {"cerceve": frame, "paylar": shares}


# ------------------------------------------------------------------ Zeki AI metinleri


def _pct(v: float) -> str:
    return f"%{v * 100:.1f}".replace(".", ",")


def _tr_day(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    x = date.fromisoformat(d)
    return f"{x.day} {B.AY[x.month - 1]} {x.year}"


def sources_of(card_: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    k = card_.get("kitap") or {}
    out = [m["metin"] for m in card_.get("metinler") or []]
    out += [x for x in (k.get("ad"), k.get("yazar"), k.get("yayinevi"), k.get("kitaplik"), k.get("hedefKitle"), k.get("turler")) if x]
    out += [m["metin"] for m in plan.get("materials") or [] if m["durum"] == "onayli"]
    return out


def facts_of(card_: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    k = card_.get("kitap") or {}
    f = []
    if plan.get("yayinTarihi"):
        f.append(f"Yayın tarihi: {_tr_day(plan['yayinTarihi'])}")
    if k.get("fiyat"):
        f.append(f"Kapak fiyatı: {k['fiyat']:g} TL")
    if k.get("sayfa"):
        f.append(f"Sayfa sayısı: {int(k['sayfa'])}")
    yas = [x for x in (k.get("yas") or []) if x]
    if len(yas) == 2:
        f.append(f"Hedef yaş: {yas[0]}–{yas[1]}")
    return f


def _book_brief(card_: dict[str, Any]) -> str:
    k = card_.get("kitap") or {}
    parts = [f"Kitap: {k.get('ad')}", f"Yazar: {k.get('yazar') or '—'}", f"Yayınevi: {k.get('yayinevi') or '—'}",
             f"Kitaplık: {k.get('kitaplik') or '—'}", f"Hedef kitle: {k.get('hedefKitle') or '—'}", f"Türler: {k.get('turler') or '—'}"]
    for m in card_.get("metinler") or []:
        parts.append(f"\n[{m['ad']}]\n{m['metin'][:4000]}")
    em = [x for x in (card_.get("emsal") or {}).get("items") or [] if x.get("ad")]
    if em:
        parts.append("\nEmsal kitaplar (yalnız adları): " + "; ".join(x["ad"] for x in em))
    return "\n".join(parts)


SYSTEM = ("Sen TİMAŞ Yayınları'nın pazarlama ekibine taslak yazan Zeki AI'sın. Kurallar: Türkçe yaz. Yalnız sana verilen "
          "bilgileri kullan, kitap hakkında bilgi uydurma. Verilen olgu listesinde olmayan hiçbir sayı yazma (satış, takipçi, "
          "yüzde, sıra, tarih dahil). Kitaptan alıntıyı yalnız verilen metinlerde birebir geçen cümlelerden, « » içinde yaz; "
          "emin değilsen alıntı yapma. «En çok satan», «bir numara», «rekor», «eşsiz» gibi kanıtsız üstünlük iddiası yazma. "
          "Hiçbir teknoloji, model ya da yazılım adı yazma. Başlık ve açıklama cümlesi ekleme; yalnız istenen metni ver.")

MATERIAL_PROMPTS = {
    "foy": "Satış ekibine giden tek sayfalık tanıtım föyü yaz: bir cümlelik konumlama, satış için 3–5 madde, hedef okur "
           "ve «bu kitabı kimlere önerirsiniz» cümlesi (emsal kitap adlarını kullanabilirsin).",
    "arka-kapak": "Arka kapak metni yaz: merak uyandıran, kitabın konusunu ve vaadini anlatan tek parça metin.",
    "basin-bulteni": "Basın bülteni yaz: başlık, bir paragraflık spot, kitabı ve yazarı anlatan iki üç paragraf, sonunda "
                     "künye (yalnız verilen yayınevi, sayfa sayısı, fiyat ve yayın tarihi).",
    "sosyal": "Üç ayrı sosyal medya gönderisi yaz; her birinin başına platform adını koy: Instagram, X, Facebook. "
              "Instagram gönderisinin sonuna konuya uygun birkaç etiket ekle (etiketlerde sayı kullanma).",
    "e-bulten-konu": "E-bülten için beş farklı konu satırı seçeneği yaz, her biri kısa ve ayrı satırda.",
    "video-senaryo": "Kısa tanıtım videosu senaryosu yaz: sahne sahne görüntü ve seslendirme metni, açılış cümlesi ve "
                     "kapanış çağrısı.",
    "kapak-brief": "Grafik ekibine kapak ve tanıtım görselleri brief'i yaz: hedef okur, ton, görsel fikirler, kaçınılacaklar.",
    "influencer-brief": "Kitabı tanıtacak içerik üreticisine brief yaz: kitabın özü, hedef kitle, iletilecek ana mesajlar, "
                        "yapılmaması gerekenler. Ücret ya da sayı yazma.",
}


def _chat(llm: Any, prompt: str, max_tokens: int = 1800) -> str:
    return str(llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=max_tokens) or "").strip()


def draft_material(llm: Any, card_: dict[str, Any], plan: dict[str, Any], tur: str, st: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    facts = facts_of(card_, plan)
    prompt = (f"{MATERIAL_PROMPTS[tur]}\n\nOlgu listesi (yazabileceğin sayılar yalnız bunlar):\n" + ("\n".join(facts) or "—") +
              f"\n\nKitap bilgisi ve CRM'deki metinler:\n{_book_brief(card_)}")
    raw = _chat(llm, prompt)
    res = G.check(raw, sources_of(card_, plan), facts, st.get("claims") or ())
    return res["metin"], {"dusen": res["dusen"], "sayac": res["sayac"], "dusenSayisi": res["dusenSayisi"], "tur": tur}


def explain_channels(llm: Any, card_: dict[str, Any], plan: dict[str, Any], sug: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    paylar = (sug.get("paylar") or {}).get("paylar") or {}
    if not paylar:
        return {"metin": None, "dusenSayisi": 0}
    facts = [f"{C.CHANNELS.get(k, k)}: {_pct(v)}" for k, v in paylar.items()]
    taban = (sug.get("paylar") or {}).get("taban") or {}
    basis = ("emsal kitapların geçmiş pazarlama harcaması" if taban.get("kaynak") == "emsal" else "şirketin son yıllardaki pazarlama harcaması")
    prompt = ("Aşağıdaki kanal payları kodla hesaplandı. Pazarlama müdürüne, bu kitap için kanal önceliğinin gerekçesini "
              "üç dört cümleyle anlat. Payları yeniden hesaplama, yeni sayı yazma; payı söylemen gerekirse listedekini aynen kullan. "
              f"Payların dayanağı: {basis}.\nKanal payları:\n" + "\n".join(facts) + f"\n\nKitap:\n{_book_brief(card_)[:6000]}")
    res = G.check(_chat(llm, prompt, 600), sources_of(card_, plan), facts, st.get("claims") or ())
    return {"metin": res["metin"] or None, "dusenSayisi": res["dusenSayisi"], "dusen": res["dusen"]}


def positioning(llm: Any, card_: dict[str, Any], plan: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    prompt = ("Bu kitabın hedef okurunu ve konumlamasını üç dört cümleyle özetle. Yalnız verilen alanlara dayan.\n\n"
              + _book_brief(card_)[:8000])
    res = G.check(_chat(llm, prompt, 500), sources_of(card_, plan), facts_of(card_, plan), st.get("claims") or ())
    return {"metin": res["metin"] or None, "dusenSayisi": res["dusenSayisi"], "dusen": res["dusen"]}


def check_emsal(llm: Any, card_: dict[str, Any], st: dict[str, Any]) -> list[dict[str, Any]]:
    """CRM'de emsal girilmemişse M10'un seçtiği her aday için kapalı küme karar (evet / hayır / belirsiz) ve olasılık."""
    em = card_.get("emsal") or {}
    if not em.get("hazir") or em.get("crmEmsalSayisi") or not hasattr(llm, "choose"):
        return []
    k = card_.get("kitap") or {}
    head = (f"Yeni kitap: {k.get('ad')} · yazar {k.get('yazar') or '—'} · kitaplık {k.get('kitaplik') or '—'} · "
            f"hedef kitle {k.get('hedefKitle') or '—'} · türler {k.get('turler') or '—'}")
    spot = next((m["metin"][:800] for m in card_.get("metinler") or [] if m["alan"] in ("new_ozet", "new_kitapspotu")), "")
    out = []
    for a in em.get("items") or []:
        q = (f"{head}\nKonu: {spot}\n\nAday emsal: {a.get('ad')} · yazar {a.get('yazar') or '—'} · kitaplık "
             f"{a.get('kitaplik') or '—'} · benzerlik nedenleri: {', '.join(a.get('nedenler') or []) or '—'}\n\n"
             "Aday kitap, yeni kitabın pazarlama planında emsal (benzer okur kitlesine hitap eden, karşılaştırılabilir) "
             "kitap olarak kullanılabilir mi?")
        ch = llm.choose(q, EMSAL_CHOICES)
        ok = ch.confident(st["minProb"], st["minMargin"])
        karar = {"Evet, emsal": "emsal", "Hayır, emsal değil": "degil"}.get(ch.choice or "", "belirsiz") if ok else "belirsiz"
        out.append({"stokKodu": a["stokKodu"], "ad": a.get("ad"), "karar": karar, "olasilik": ch.probability,
                    "marj": ch.margin, "yontem": ch.method})
    return out


# ------------------------------------------------------------------ liste


def _missing_materials(plan: dict[str, Any], required: list[str]) -> list[str]:
    ok = {m["tur"] for m in plan.get("materials") or [] if m["durum"] == "onayli"}
    return [t for t in required if t not in ok]


def new_books(engine: Any, tenant: str, user: str, crm: Crm, st: dict[str, Any], *, frm: date, to: date, durum: str = "",
              yayinevi: str = "", sahip: str = "", q: str = "", page: int = 0, fresh: bool = False,
              can_approve: bool = False) -> dict[str, Any]:
    ref = C.today()
    books = crm.new_books(frm, to, fresh=fresh)
    codes = [b["stokKodu"] for b in books]
    plans_by: dict[str, dict[str, Any]] = {}
    for h in C.list_plans(engine, tenant, kind="yeni", stok=codes) if codes else []:
        cur = plans_by.get(h["stokKodu"])
        if cur is None or h["surum"] > cur["surum"]:
            plans_by[h["stokKodu"]] = h
    rows = []
    by_year: dict[int, list[str]] = defaultdict(list)
    for b in books:
        plan = plans_by.get(b["stokKodu"])
        pub, src = resolve_pub(b["tarihler"], st["dateOrder"])
        if plan and plan.get("yayinTarihiKaynagi") == "elle" and plan.get("yayinTarihi"):
            pub, src = plan["yayinTarihi"], "elle"
        if not pub or not (frm.isoformat() <= pub <= to.isoformat()):
            continue
        by_year[int(pub[:4])].append(b["stokKodu"])
        rows.append({**b, "yayinTarihi": pub, "yayinKaynagi": src, "kalanGun": _days_to(pub, ref), "plan": plan})
    tg = targets_many(engine, tenant, dict(by_year))
    full_plans = {p["id"]: C.plan_full(engine, tenant, p["id"]) for p in plans_by.values()} if plans_by else {}
    kpi = {"plansiz": 0, "onayda": 0, "materyalEksik": 0, "hedefDegisti": 0}
    for r in rows:
        cur = tg.get(f"{r['yayinTarihi'][:4]}:{r['stokKodu']}")
        r["hedef"] = {"adet": cur["adet"], "ciro": cur["ciro"], "marj": cur["marj"]} if cur else None
        cur = cur or tg.get(f"_plan:{r['yayinTarihi'][:4]}")
        p = r.pop("plan")
        if p:
            full = full_plans[p["id"]]
            miss = _missing_materials(full, st["requiredMaterials"])
            changed = target_changed(p.get("hedef"), cur) if p["durum"] != "arsiv" else False
            r["plan"] = {"id": p["id"], "durum": p["durum"], "durumAdi": p["durumAdi"], "butce": p["butceToplam"], "sahip": p["sahip"],
                         "gonderen": p["gonderen"], "surum": p["surum"], "eksikMateryal": miss, "hedefDegisti": changed,
                         "ustOnayGerekli": C.needs_upper(p["butceToplam"], st["threshold"])}
            if p["durum"] == "onayda":
                kpi["onayda"] += 1
            if miss and r["kalanGun"] is not None and r["kalanGun"] <= st["materialDays"]:
                kpi["materyalEksik"] += 1
            if changed:
                kpi["hedefDegisti"] += 1
        else:
            r["plan"] = None
            if r["kalanGun"] is not None and 0 <= r["kalanGun"] <= st["noPlanDays"]:
                kpi["plansiz"] += 1
    publishers = sorted({r["yayinevi"] for r in rows if r.get("yayinevi")})
    needle = G.fold(q)
    me = (user or "").lower()

    def keep(r: dict[str, Any]) -> bool:
        p = r["plan"]
        if yayinevi and r.get("yayinevi") != yayinevi:
            return False
        if needle and needle not in G.fold(" ".join(str(x or "") for x in (r["stokKodu"], r.get("ad"), r.get("yazar")))):
            return False
        if durum == "plansiz" and p is not None:
            return False
        if durum in C.STATUSES and (p is None or p["durum"] != durum):
            return False
        if durum == "materyal" and not (p and p["eksikMateryal"] and (r["kalanGun"] or 0) <= st["materialDays"]):
            return False
        if durum == "hedef" and not (p and p["hedefDegisti"]):
            return False
        if sahip == "ben":
            mine = (r.get("sorumluHesap") or "") == me or (p and (p.get("sahip") or "").lower() == me)
            waiting = p and p["durum"] == "onayda" and can_approve and (p.get("gonderen") or "").lower() != me
            if not (mine or waiting):
                return False
        return True

    shown = sorted((r for r in rows if keep(r)), key=lambda r: (r["kalanGun"] if r["kalanGun"] is not None else 10**6, r.get("ad") or ""))
    page = max(0, int(page))
    return {"items": shown[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": len(shown), "page": page, "pageSize": PAGE_SIZE,
            "kpi": kpi, "window": {"from": frm.isoformat(), "to": to.isoformat()}, "yayinevleri": publishers,
            "hepsi": len(rows)}


# ------------------------------------------------------------------ CRM'e işlenecek


def crm_todo(plan: dict[str, Any], card_: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Portalda onaylanan ama CRM'de olmayan / farklı olan bilgiler. CRM'e bu modül yazmaz; müşterinin kullanıcıları işler."""
    items: list[dict[str, Any]] = []
    crm_text = {m["alan"]: m["metin"] for m in (card_ or {}).get("metinler") or []}
    for m in plan.get("materials") or []:
        field = m.get("crmAlani")
        if m["durum"] != "onayli" or not field:
            continue
        cur = crm_text.get(field)
        if G.fold(cur) != G.fold(m["metin"]):
            items.append({"tur": "kitap-alani", "hedef": f"Kitap kartı › {FIELD_LABELS.get(field, field)}", "alan": field,
                          "deger": m["metin"], "crmDeger": cur, "materyalId": m["id"]})
    for ln in plan.get("lines") or []:
        items.append({"tur": "butce-satiri", "hedef": "Pazarlama Bütçe Modülü › yeni kayıt", "tip": ln["kanalAdi"],
                      "altTip": ln.get("altKanal"), "tutar": ln["tutar"], "baslangic": ln.get("baslangic"),
                      "bitis": ln.get("bitis"), "kitap": plan.get("stokKodu"), "aciklama": ln.get("aciklama")})
    pj = (card_ or {}).get("crmButce") or {}
    if plan.get("crmProjeId") and round(float(pj.get("toplam") or 0), 2) != round(float(plan.get("butceToplam") or 0), 2):
        items.append({"tur": "proje-alani", "hedef": "Proje kartı › Toplam Pazarlama Bütçesi", "alan": "new_toplampazarlamabutcesi",
                      "deger": plan.get("butceToplam"), "crmDeger": pj.get("toplam")})
    for it in items:
        it["planOnayli"] = plan.get("durum") == "onayli"
    return items


# ------------------------------------------------------------------ günlük hatırlatma


def digest(rows: list[dict[str, Any]], st: dict[str, Any]) -> dict[str, Any]:
    """Günlük özetin içeriği: yayına N gün kala onaylı planı olmayan, materyali eksik, hedefi değişen, onay bekleyen."""
    buckets: dict[int, list[dict[str, Any]]] = {d: [] for d in st["remindDays"]}
    for r in rows:
        k = r.get("kalanGun")
        p = r.get("plan")
        if k is None or k < 0 or (p and p["durum"] == "onayli"):
            continue
        for d in sorted(st["remindDays"]):
            if k <= d:
                buckets[d].append(r)
                break
    mat = [r for r in rows if r.get("plan") and r["plan"]["eksikMateryal"] and r.get("kalanGun") is not None
           and 0 <= r["kalanGun"] <= st["materialDays"]]
    tgt = [r for r in rows if r.get("plan") and r["plan"]["hedefDegisti"]]
    wait = [r for r in rows if r.get("plan") and r["plan"]["durum"] == "onayda"]
    return {"yayinaKalan": {str(d): v for d, v in buckets.items()}, "materyalEksik": mat, "hedefDegisti": tgt, "onayBekleyen": wait}


def digest_text(dg: dict[str, Any], link: str) -> Optional[str]:
    def ln(r: dict[str, Any]) -> str:
        p = r.get("plan")
        return f"  - {r.get('ad') or r['stokKodu']} ({r['stokKodu']}), yayın {_tr_day(r['yayinTarihi'])}, {r['kalanGun']} gün · " + \
               (p["durumAdi"] if p else "plan yok")
    lines: list[str] = []
    for d, rows in sorted(dg["yayinaKalan"].items(), key=lambda x: int(x[0])):
        if rows:
            lines += [f"Yayına {d} gün ya da daha az kalan, planı onaylı olmayan kitaplar ({len(rows)}):"] + [ln(r) for r in rows] + [""]
    if dg["materyalEksik"]:
        lines += [f"Onaylı materyali eksik planlar ({len(dg['materyalEksik'])}):"] + \
                 [ln(r) + " · eksik: " + ", ".join(C.MATERIALS_KINDS[t][0] for t in r["plan"]["eksikMateryal"]) for r in dg["materyalEksik"]] + [""]
    if dg["hedefDegisti"]:
        lines += [f"Satış hedefi değişen planlar ({len(dg['hedefDegisti'])}):"] + [ln(r) for r in dg["hedefDegisti"]] + [""]
    if dg["onayBekleyen"]:
        lines += [f"Onay bekleyen planlar ({len(dg['onayBekleyen'])}):"] + [ln(r) for r in dg["onayBekleyen"]] + [""]
    if not lines:
        return None
    lines.append(f"Ayrıntı: {link}" if link else "Ayrıntı: Pazarlama › Planlama › Yeni kitap planı")
    return "\n".join(lines)
