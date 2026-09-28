"""M18 Aylık pazarlama planı: bir ayın yeni kitap + backlist + özel gün + B2B kampanyası takvimi, çakışmalar, yeni
kitap / backlist bütçe dağılımı, önceki ay özeti.

**Plan**: çekirdeğin `semantic_mkt_plans` satırı, `kind='aylik'`, `donem='YYYY-MM'`. Tenant + dönem için tek açık sürüm
vardır; onaylı ay planı değiştirilmez, «Revize et» yeni sürüm açar (çekirdeğin onay akışı: gönderen onaylayamaz, eşik
üstü bütçede üst onay). Ay kalemleri (`semantic_mkt_month_items`) ve bütçe payları (`semantic_mkt_month_budget`)
çekirdeğe `register_plan_table` ile bağlıdır: taslak silinince silinir, revizyonda kopyalanır. Bütçe payları
çekirdeğin bütçe satırlarına da yansıtılır (onay eşiği ve «CRM'e işlenecek» aynı satırlardan çalışır).

**Takvim kaynakları** (hepsi yalnız okuma; kaynak ve kimlik her kalemde yazılı):
- *Yeni kitap*: CRM'de yayın günü o aya düşen kitaplar (M15'teki yayın günü önceliğiyle; M15 planında elle girilmiş gün
  önce) + onaylı M15 planlarının o ayla kesişen kanal satırları.
- *Backlist*: onaylı M17 planlarının o ayla kesişen satırları. M17 henüz kurulmadıysa blok boş kalır ve ekran söyler.
- *Özel gün*: CRM özel günlerinin o aya düşen tarihleri (tarih yöntemi SEO sezon takvimiyle aynı) ve bağlı kitap sayısı.
- *B2B kampanyası*: CRM kampanyalarından o ayla kesişenler (mecra, ek iskonto, planlanan/gerçekleşen ciro).

Taslak yeniden kurulunca kaynaktan gelen kalemler tazelenir; elle düzeltilen (`elle`) ve kullanıcının eklediği kalem
korunur. Kaynaktan düşen elle düzeltilmiş kalem silinmez, «kaynakta yok» diye işaretlenir.

**Çakışma** (kural): (1) aynı hafta, aynı kitaplıkta (ayarla hedef kitle de eklenir) birden çok yeni kitap lansmanı;
(2) aynı kanalda tarihleri örtüşen kampanyalar (B2B kampanyası ya da «satış kampanyası» kanalındaki işler).

**Bütçe** (rakamı kod üretir, Zeki AI yalnız gerekçe yazar):
- Ay hedefi: M46 yürürlükteki planında o ayın `aylik[ay].ciro` toplamı, segment başına (yeni / backlist).
- Önceki ay oranı: M46'nın Logo gerçekleşme önbelleğinden (`semantic_budget_sales_actuals`: faturalı satır, net ciro =
  LINENET) önceki ayda o segmentin hedefli kitaplarının net cirosu ÷ aynı kitapların o ayki hedefi.
- Çerçeve: elle girilen > Yönetim ayarı «Aylık pazarlama bütçesi» > oran × ayın toplam hedef cirosu (oran M15'le aynı:
  ayar ya da son tam yılda pazarlama masraf merkezi gideri ÷ net ciro). Hiçbiri yoksa çerçeve boş, tutar sıfır.
- Segment ağırlığı = hedef payı × (1 + hedefin altında kalınan pay); önceki ayda hedefin %70'inde kalan segmentin
  ağırlığı 1,3 katına çıkar, hedefi tutturan segment kendi payında kalır. Kanal payı: o segmentin kitaplarına bağlı CRM
  pazarlama bütçe modülü harcamasının kanal dağılımı; kayıt yoksa şirket geneli (M15 ile aynı kural).

CRM «Satış Hedefleri» (bölge × kitap × ay, `new_satishedefleriBase`) yalnız bilgi olarak kalemde görünür; M46 esastır,
iki hedefin ilişkisi ölçülecek.
"""
from __future__ import annotations

import calendar
import logging
import threading
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import budget as B
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import guard as G
from semantic_bridge.marketing import plans as P
from semantic_bridge.marketing.sources import Crm, SourceError

log = logging.getLogger("semantic.marketing.monthly")

ITEMS = sa.Table(
    "semantic_mkt_month_items", C._md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("plan_id", sa.String(24), nullable=False, index=True),
    sa.Column("sira", sa.Integer, nullable=False, default=0),
    sa.Column("tur", sa.String(16), nullable=False),                   # yeni | backlist | ozel-gun | b2b-kampanya | set | diger
    sa.Column("kaynak", sa.String(16), nullable=False),                # crm-kitap | m15 | m17 | crm-ozel-gun | crm-kampanya | kullanici
    sa.Column("kaynak_ref", sa.String(80)),                            # stok kodu | plan:satır | özel gün id | kampanya id
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("baslik", sa.String(400), nullable=False),
    sa.Column("yayinevi", sa.String(200)),
    sa.Column("kitaplik", sa.String(200)),
    sa.Column("hedef_kitle", sa.String(120)),
    sa.Column("hafta", sa.String(10)),                                 # ISO hafta: 2026-W45 (başlangıç gününün haftası)
    sa.Column("baslangic", sa.String(10)),
    sa.Column("bitis", sa.String(10)),
    sa.Column("kanal", sa.String(24)),
    sa.Column("butce", sa.Float),
    sa.Column("aciklama", sa.Text),
    sa.Column("elle", sa.Boolean, nullable=False, default=False),
    sa.Column("detay_json", sa.Text),
    sa.Column("cakisma_json", sa.Text),
)
BUDGET = sa.Table(
    "semantic_mkt_month_budget", C._md,
    sa.Column("plan_id", sa.String(24), primary_key=True),
    sa.Column("segment", sa.String(12), primary_key=True),             # yeni | backlist
    sa.Column("kanal", sa.String(24), primary_key=True),
    sa.Column("oneri", sa.Float, nullable=False, default=0.0),
    sa.Column("onayli", sa.Float),                                     # müdürün düzelttiği tutar (boşsa öneri geçerli)
    sa.Column("hedef_payi", sa.Float),                                 # segmentin ay hedef cirosu payı (M46)
    sa.Column("onceki_ay_oran", sa.Float),
    sa.Column("gerekce", sa.Text),
)
C.register_plan_table(ITEMS)
C.register_plan_table(BUDGET)

TYPES = {"yeni": "Yeni kitap", "backlist": "Backlist", "ozel-gun": "Özel gün", "b2b-kampanya": "B2B kampanyası",
         "set": "Sezon seti", "diger": "Diğer"}
ITEM_SOURCES = {"crm-kitap": "CRM kitap kartı", "m15": "Yeni kitap planı", "m17": "Backlist planı",
                "crm-ozel-gun": "CRM özel günleri", "crm-kampanya": "CRM kampanyaları", "kullanici": "Elle eklendi"}
SEGMENTS = {"yeni": "Yeni kitap", "backlist": "Backlist"}
MECRA = {1: "CRM", 2: "B2B", 3: "CRM ve B2B"}
CAMPAIGN_TIP = {1: "Kampanya", 2: "Anlaşma"}
#: Takvim ızgarasında kanalı olmayan kalemlerin satırı.
ROW_LAUNCH, ROW_DAY = "_lansman", "_ozel-gun"

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    C.ensure(engine)
    with _lock:
        if id(engine) in _ready:
            return
        for t in (ITEMS, BUDGET):
            t.create(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ dönem


def parse_donem(v: Any) -> str:
    s = str(v or "").strip()
    try:
        y, m = int(s[:4]), int(s[5:7])
        if len(s) != 7 or s[4] != "-" or not (2000 <= y <= 2100 and 1 <= m <= 12):
            raise ValueError
    except ValueError:
        raise C.MarketingError("Dönem YYYY-AA biçiminde olmalı (ör. 2026-11).") from None
    return f"{y:04d}-{m:02d}"


def bounds(donem: str) -> tuple[date, date]:
    y, m = int(donem[:4]), int(donem[5:7])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def shift(donem: str, n: int) -> str:
    y, m = int(donem[:4]), int(donem[5:7])
    i = y * 12 + (m - 1) + n
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def of_day(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def default_donem(today: date, draft_day: int) -> str:
    """İçinde bulunulan ay; taslak gününden (15) sonra gelecek ay önerilir."""
    return shift(of_day(today), 1) if today.day >= draft_day else of_day(today)


def label(donem: str) -> str:
    return f"{B.AY[int(donem[5:7]) - 1]} {donem[:4]}"


def iso_week(d: str | date | None) -> Optional[str]:
    if not d:
        return None
    x = date.fromisoformat(d) if isinstance(d, str) else d
    y, w, _ = x.isocalendar()
    return f"{y}-W{w:02d}"


def weeks(donem: str) -> list[dict[str, Any]]:
    """Ayın haftaları (pazartesi başlar): anahtar, ayın içinde kalan ilk ve son gün."""
    first, last = bounds(donem)
    out: list[dict[str, Any]] = []
    d = first
    while d <= last:
        end = min(last, d + timedelta(days=6 - d.weekday()))
        out.append({"hafta": iso_week(d), "baslangic": d.isoformat(), "bitis": end.isoformat()})
        d = end + timedelta(days=1)
    return out


def _overlaps(a0: Optional[str], a1: Optional[str], b0: str, b1: str) -> bool:
    if not a0:
        return False
    return a0 <= b1 and (a1 or a0) >= b0


def nth_workday(y: int, m: int, n: int) -> date:
    """Ayın n'inci iş günü (pazartesi–cuma; resmî tatiller sayılmaz — ölçülecek, ayarla değiştirilir)."""
    d, k = date(y, m, 1), 0
    while True:
        if d.weekday() < 5:
            k += 1
            if k >= n:
                return d
        d += timedelta(days=1)


# ------------------------------------------------------------------ ayarlar


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    base = P.settings(conf)

    def num(key: str, default: Optional[float]) -> Optional[float]:
        raw = (conf(key) or "").strip()
        if "," in raw:  # «1.250.000,50» Türkçe yazım
            raw = raw.replace(".", "").replace(",", ".")
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    keys = [x.strip() for x in (conf("MARKETING_CONFLICT_KEYS") or "kitaplik").split(",") if x.strip() in ("kitaplik", "hedef-kitle")]
    return {
        **base,
        "draftDay": int(num("MARKETING_MONTH_DRAFT_DAY", 15) or 15),
        "foyRemindDay": int(num("MARKETING_FOY_REMIND_DAY", 20) or 20),
        "summaryWorkday": int(num("MARKETING_MONTH_SUMMARY_WORKDAY", 3) or 3),
        "monthlyBudget": num("MARKETING_MONTHLY_BUDGET", None),
        "conflictKeys": keys or ["kitaplik"],
        "campaignTypes": [int(x) for x in (conf("MARKETING_B2B_CAMPAIGN_TYPES") or "").split(",") if x.strip().isdigit()],
    }


# ------------------------------------------------------------------ plan bulma / açma


def find_plan(engine: sa.engine.Engine, tenant: str, donem: str, *, approved: bool = False) -> Optional[dict[str, Any]]:
    """Dönemin geçerli ay planı: en yüksek sürümlü arşiv dışı plan (`approved`: yalnız onaylı)."""
    heads = C.list_plans(engine, tenant, kind="aylik", donem=donem, durum="onayli" if approved else "")
    return max(heads, key=lambda h: h["surum"]) if heads else None


def _open_plan(engine: sa.engine.Engine, tenant: str, user: str, donem: str) -> str:
    cur = find_plan(engine, tenant, donem)
    if cur:
        if cur["durum"] not in C.EDITABLE:
            raise C.MarketingError(f"{label(donem)} planı {cur['durumAdi'].lower()}; değiştirmek için revize edin.", 409)
        return cur["id"]
    return C.create_plan(engine, tenant, user, kind="aylik", baslik=f"{label(donem)} pazarlama planı", donem=donem, sahip=user)


# ------------------------------------------------------------------ kaynaklardan kalemler


def _pub_rows(engine: Any, tenant: str, crm: Crm, st: dict[str, Any], first: date, last: date, fresh: bool) -> list[dict[str, Any]]:
    """Yayın günü aya düşen CRM kitapları (M15'teki öncelik; M15 planında elle girilen gün önce)."""
    books = crm.new_books(first, last, fresh=fresh)
    codes = [b["stokKodu"] for b in books]
    manual: dict[str, dict[str, Any]] = {}
    for h in C.list_plans(engine, tenant, kind="yeni", stok=codes) if codes else []:
        cur = manual.get(h["stokKodu"])
        if cur is None or h["surum"] > cur["surum"]:
            manual[h["stokKodu"]] = h
    out = []
    for b in books:
        pub, src = P.resolve_pub(b["tarihler"], st["dateOrder"])
        plan = manual.get(b["stokKodu"])
        if plan and plan.get("yayinTarihiKaynagi") == "elle" and plan.get("yayinTarihi"):
            pub, src = plan["yayinTarihi"], "elle"
        if pub and first.isoformat() <= pub <= last.isoformat():
            out.append({**b, "yayinTarihi": pub, "yayinKaynagi": src, "plan": plan})
    return sorted(out, key=lambda r: (r["yayinTarihi"], r.get("ad") or ""))


def _plan_lines(engine: Any, tenant: str, kind: str, first: date, last: date) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for h in C.list_plans(engine, tenant, kind=kind, durum="onayli"):
        full = C.plan_full(engine, tenant, h["id"])
        for ln in full["lines"]:
            b0 = ln.get("baslangic") or full.get("yayinTarihi")
            b1 = ln.get("bitis") or b0
            if _overlaps(b0, b1, first.isoformat(), last.isoformat()):
                out.append((full, {**ln, "baslangic": b0, "bitis": b1}))
    return out


def special_days_in(days: list[dict[str, Any]], first: date, last: date) -> list[dict[str, Any]]:
    from semantic_bridge.seo_geo import seasons as S

    out = []
    for d in days:
        how = S.resolve({"name": d.get("ad"), "weekFrom": d.get("hafta1"), "weekTo": d.get("hafta2"),
                         "fixedDate": d["tarih"][5:10] if d.get("tarih") else None})
        if how["method"] == "unknown":
            continue
        seen = set()
        for y in (first.year - 1, first.year, first.year + 1):
            for a, b in S.occurrences(how, y):
                if a <= last and b >= first and (a, b) not in seen:
                    seen.add((a, b))
                    out.append({**d, "baslangic": a.isoformat(), "bitis": b.isoformat(), "yontem": how.get("why"),
                                "kesinlik": how.get("precision")})
    return sorted(out, key=lambda x: (x["baslangic"], x.get("ad") or ""))


def collect(engine: Any, tenant: str, crm: Crm, st: dict[str, Any], donem: str, *, fresh: bool = False) -> dict[str, Any]:
    """Ayın kaynak kalemleri: yeni kitap, M15/M17 onaylı plan satırları, özel gün, CRM kampanyası. CRM okunamazsa ilgili
    blok boş kalır ve neden `notlar`a yazılır (sessizce eksik kalmaz)."""
    first, last = bounds(donem)
    items: list[dict[str, Any]] = []
    notes: list[str] = []
    try:
        pubs = _pub_rows(engine, tenant, crm, st, first, last, fresh)
    except SourceError as e:
        pubs, _ = [], notes.append(f"CRM yeni kitapları okunamadı: {e}")
    for b in pubs:
        p = b.get("plan")
        items.append({"tur": "yeni", "kaynak": "crm-kitap", "kaynak_ref": b["stokKodu"], "stok_kodu": b["stokKodu"],
                      "baslik": b.get("ad") or b["stokKodu"], "yayinevi": b.get("yayinevi"), "kitaplik": b.get("kitaplik"),
                      "hedef_kitle": b.get("hedefKitle"), "baslangic": b["yayinTarihi"], "bitis": b["yayinTarihi"], "kanal": None,
                      "butce": None, "aciklama": None,
                      "detay": {"yazar": b.get("yazar"), "yayinKaynagi": b["yayinKaynagi"], "sorumlu": b.get("sorumlu"),
                                "sorumluHesap": b.get("sorumluHesap"),
                                "plan": {"id": p["id"], "durum": p["durum"], "durumAdi": p["durumAdi"]} if p else None}})
    for full, ln in _plan_lines(engine, tenant, "yeni", first, last):
        items.append({"tur": "yeni", "kaynak": "m15", "kaynak_ref": f"{full['id']}:{ln['id']}"[:80], "stok_kodu": full.get("stokKodu"),
                      "baslik": f"{full['baslik'].split(' · ')[0]} · {ln['kanalAdi']}", "yayinevi": None, "kitaplik": None,
                      "hedef_kitle": None, "baslangic": ln["baslangic"], "bitis": ln["bitis"], "kanal": ln["kanal"],
                      "butce": ln.get("tutar"), "aciklama": ln.get("aciklama") or ln.get("altKanal"),
                      "detay": {"plan": {"id": full["id"], "durum": full["durum"], "durumAdi": full["durumAdi"]},
                                "yayinTarihi": full.get("yayinTarihi")}})
    backlist = _plan_lines(engine, tenant, "backlist", first, last)
    if not backlist:
        notes.append("Bu ay için onaylı backlist planı yok; backlist blokları backlist planları onaylandıkça dolar.")
    for full, ln in backlist:
        items.append({"tur": "backlist", "kaynak": "m17", "kaynak_ref": f"{full['id']}:{ln['id']}"[:80], "stok_kodu": full.get("stokKodu"),
                      "baslik": f"{full['baslik'].split(' · ')[0]} · {ln['kanalAdi']}", "yayinevi": None, "kitaplik": None,
                      "hedef_kitle": None, "baslangic": ln["baslangic"], "bitis": ln["bitis"], "kanal": ln["kanal"],
                      "butce": ln.get("tutar"), "aciklama": ln.get("aciklama") or ln.get("altKanal"),
                      "detay": {"plan": {"id": full["id"], "durum": full["durum"], "durumAdi": full["durumAdi"]}}})
    try:
        days = special_days_in(crm.all_special_days(fresh=fresh), first, last)
    except SourceError as e:
        days, _ = [], notes.append(f"CRM özel günleri okunamadı: {e}")
    for d in days:
        items.append({"tur": "ozel-gun", "kaynak": "crm-ozel-gun", "kaynak_ref": f"{d['id']}:{d['baslangic']}"[:80], "stok_kodu": None,
                      "baslik": d.get("ad") or "Özel gün", "yayinevi": None, "kitaplik": None, "hedef_kitle": None,
                      "baslangic": d["baslangic"], "bitis": d["bitis"], "kanal": None, "butce": None, "aciklama": None,
                      "detay": {"kitapSayisi": d.get("kitapSayisi"), "yontem": d.get("yontem"), "kesinlik": d.get("kesinlik")}})
    try:
        camps = crm.campaigns(first, last, fresh=fresh)
    except SourceError as e:
        camps, _ = [], notes.append(f"CRM kampanyaları okunamadı: {e}")
    for k in camps:
        if st.get("campaignTypes") and k.get("tip") not in st["campaignTypes"]:
            continue
        items.append({"tur": "b2b-kampanya", "kaynak": "crm-kampanya", "kaynak_ref": k["id"], "stok_kodu": None,
                      "baslik": k.get("ad") or "Kampanya", "yayinevi": None, "kitaplik": None, "hedef_kitle": None,
                      "baslangic": k.get("baslangic"), "bitis": k.get("bitis") or k.get("baslangic"), "kanal": "satis-kampanyasi",
                      "butce": None, "aciklama": None,
                      "detay": {"mecra": MECRA.get(k.get("mecra") or 0), "tip": CAMPAIGN_TIP.get(k.get("tip") or 0),
                                "ekIskonto": k.get("ekIskonto"), "netIskonto": k.get("netIskonto"),
                                "planlananCiro": k.get("planlananCiro"), "gerceklesenCiro": k.get("gerceklesenCiro"),
                                "urunSayisi": k.get("urunSayisi")}})
    return {"items": items, "notlar": notes}


# ------------------------------------------------------------------ çakışma


def conflicts(items: list[dict[str, Any]], keys: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Kalem kimliği → çakışmalar. Kural 1: aynı hafta + aynı kitaplık (ve/veya hedef kitle) birden çok yeni kitap
    lansmanı (CRM yayın günü kalemi). Kural 2: aynı kanalda tarihleri örtüşen kampanyalar."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    launches = [x for x in items if x["tur"] == "yeni" and x["kaynak"] == "crm-kitap" and x.get("hafta")]
    for key in keys:
        col = "kitaplik" if key == "kitaplik" else "hedef_kitle"
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for x in launches:
            v = (x.get(col) or "").strip()
            if v:
                groups[(x["hafta"], G.fold(v))].append(x)
        for (hafta, _v), xs in groups.items():
            if len(xs) < 2:
                continue
            why = ("Aynı hafta aynı kitaplıkta" if col == "kitaplik" else "Aynı hafta aynı hedef kitlede") + f" {len(xs)} lansman"
            for x in xs:
                out[x["id"]].append({"kural": "ayni-hafta-" + ("kitaplik" if col == "kitaplik" else "hedef-kitle"), "neden": why,
                                     "deger": x.get(col), "hafta": hafta, "ile": [y["id"] for y in xs if y["id"] != x["id"]],
                                     "ileAd": [y["baslik"] for y in xs if y["id"] != x["id"]]})
    camps = [x for x in items if (x["tur"] == "b2b-kampanya" or x.get("kanal") == "satis-kampanyasi") and x.get("baslangic")]
    for i, a in enumerate(camps):
        for b in camps[i + 1:]:
            if (a.get("kanal") or "") != (b.get("kanal") or ""):
                continue
            if a["tur"] == "b2b-kampanya" and b["tur"] == "b2b-kampanya" and \
                    (a.get("detay") or {}).get("mecra") != (b.get("detay") or {}).get("mecra"):
                continue
            if _overlaps(a["baslangic"], a.get("bitis"), b["baslangic"], b.get("bitis") or b["baslangic"]):
                for x, y in ((a, b), (b, a)):
                    out[x["id"]].append({"kural": "ust-uste-kampanya", "neden": "Aynı kanalda tarihleri örtüşen kampanya",
                                         "ile": [y["id"]], "ileAd": [y["baslik"]]})
    return dict(out)


def _refresh_conflicts(c: Any, plan_id: str, keys: list[str]) -> int:
    rows = [_item(r) for r in c.execute(sa.select(ITEMS).where(ITEMS.c.plan_id == plan_id)).all()]
    found = conflicts([{**x, "kaynak_ref": x["kaynakRef"], "hedef_kitle": x["hedefKitle"]} for x in rows], keys)
    for x in rows:
        v = found.get(x["id"])
        c.execute(ITEMS.update().where(ITEMS.c.id == x["id"]).values(cakisma_json=C.dump(v) if v else None))
    return len(found)


# ------------------------------------------------------------------ kalem okuma / yazma


def _item(r: Any) -> dict[str, Any]:
    return {"id": r.id, "sira": r.sira, "tur": r.tur, "turAdi": TYPES.get(r.tur, r.tur), "kaynak": r.kaynak,
            "kaynakAdi": ITEM_SOURCES.get(r.kaynak, r.kaynak), "kaynakRef": r.kaynak_ref, "stok_kodu": r.stok_kodu,
            "stokKodu": r.stok_kodu, "baslik": r.baslik, "yayinevi": r.yayinevi, "kitaplik": r.kitaplik,
            "hedefKitle": r.hedef_kitle, "hafta": r.hafta, "baslangic": r.baslangic, "bitis": r.bitis, "kanal": r.kanal,
            "kanalAdi": C.CHANNELS.get(r.kanal or "", None), "butce": r.butce, "aciklama": r.aciklama, "elle": bool(r.elle),
            "detay": C.loads(r.detay_json, {}), "cakisma": C.loads(r.cakisma_json, [])}


def items_stmt(plan_id: str):
    """Ay planının kalemleri (aynı ifade sorgu bilgisinde gösterilir)."""
    return sa.select(ITEMS).where(ITEMS.c.plan_id == plan_id).order_by(ITEMS.c.baslangic, ITEMS.c.sira, ITEMS.c.id)


def items_of(engine: sa.engine.Engine, plan_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(items_stmt(plan_id)).all()
    out = [_item(r) for r in rows]
    for x in out:
        x.pop("stok_kodu", None)
    return out


def sync_items(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, found: list[dict[str, Any]],
               st: dict[str, Any]) -> dict[str, int]:
    """Kaynak kalemlerini plana yazar. Anahtar (tür, kaynak, kaynak kimliği). Elle düzeltilen kalem olduğu gibi kalır
    (kaynaktan düşerse «kaynakta yok»); kullanıcının eklediği kalem korunur."""
    stats = {"eklenen": 0, "guncellenen": 0, "silinen": 0, "korunan": 0}
    with engine.begin() as c:
        r = C._row(c, tenant, plan_id, lock=True)
        C.editable(r)
        cur = {(x.tur, x.kaynak, x.kaynak_ref): x for x in c.execute(sa.select(ITEMS).where(ITEMS.c.plan_id == r.id)).all()}
        seen = set()
        for i, it in enumerate(found):
            key = (it["tur"], it["kaynak"], it["kaynak_ref"])
            if key in seen:
                continue
            seen.add(key)
            vals = {k: it.get(k) for k in ("tur", "kaynak", "kaynak_ref", "stok_kodu", "yayinevi", "kitaplik", "hedef_kitle",
                                           "baslangic", "bitis", "kanal", "butce", "aciklama")}
            vals["baslik"] = C.one_line(it.get("baslik"), 400) or "—"
            vals["hafta"] = iso_week(it.get("baslangic"))
            vals["detay_json"] = C.dump(it.get("detay") or {})
            prev = cur.get(key)
            if prev is None:
                c.execute(ITEMS.insert().values(id=C._uid(), plan_id=r.id, sira=i, elle=False, **vals))
                stats["eklenen"] += 1
            elif prev.elle:
                d = C.loads(prev.detay_json, {})
                d.update({"kaynak": it.get("detay") or {}, "kaynaktaYok": False})
                c.execute(ITEMS.update().where(ITEMS.c.id == prev.id).values(detay_json=C.dump(d)))
                stats["korunan"] += 1
            else:
                c.execute(ITEMS.update().where(ITEMS.c.id == prev.id).values(sira=i, **vals))
                stats["guncellenen"] += 1
        for key, prev in cur.items():
            if key in seen or prev.kaynak == "kullanici":
                continue
            if prev.elle:
                d = C.loads(prev.detay_json, {})
                d["kaynaktaYok"] = True
                c.execute(ITEMS.update().where(ITEMS.c.id == prev.id).values(detay_json=C.dump(d)))
            else:
                c.execute(ITEMS.delete().where(ITEMS.c.id == prev.id))
                stats["silinen"] += 1
        stats["cakisma"] = _refresh_conflicts(c, r.id, st["conflictKeys"])
        c.execute(C.PLANS.update().where(C.PLANS.c.id == r.id).values(guncelleyen=user, guncelleme=C.now()))
        C.event(c, r.id, user, "ay-kuruldu", None, stats)
    return stats


def _clean_item(body: dict[str, Any], donem: str) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    first, last = bounds(donem)
    if "baslangic" in body:
        vals["baslangic"] = C.day(body.get("baslangic"), "Başlangıç")
    if "bitis" in body:
        vals["bitis"] = C.day(body.get("bitis"), "Bitiş")
    if "kanal" in body:
        k = str(body.get("kanal") or "") or None
        if k and k not in C.CHANNELS:
            raise C.MarketingError("Kanal tanınmıyor.")
        vals["kanal"] = k
    if "butce" in body:
        v = C.number(body.get("butce"), "Bütçe", allow_none=True)
        vals["butce"] = None if v is None else round(v, 2)
    if "aciklama" in body:
        vals["aciklama"] = C.text(body.get("aciklama"), 4000)
    if "baslik" in body:
        b = C.one_line(body.get("baslik"), 400)
        if not b:
            raise C.MarketingError("Başlık boş olamaz.")
        vals["baslik"] = b
    if vals.get("baslangic") and vals.get("bitis") and vals["bitis"] < vals["baslangic"]:
        raise C.MarketingError("Bitiş başlangıçtan önce olamaz.")
    if vals.get("baslangic") and not _overlaps(vals["baslangic"], vals.get("bitis"), first.isoformat(), last.isoformat()):
        raise C.MarketingError(f"Kalem {label(donem)} ile kesişmeli.")
    if "baslangic" in vals:
        vals["hafta"] = iso_week(vals["baslangic"])
    return vals


def update_item(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, donem: str, item_id: str, body: dict[str, Any],
                st: dict[str, Any]) -> dict[str, Any]:
    vals = _clean_item(body, donem)
    if not vals:
        raise C.MarketingError("Değiştirilecek alan yok.")
    with engine.begin() as c:
        r = C._row(c, tenant, plan_id, lock=True)
        C.editable(r)
        it = c.execute(sa.select(ITEMS).where(ITEMS.c.plan_id == r.id, ITEMS.c.id == str(item_id)[:32])).first()
        if not it:
            raise C.MarketingError("Kalem bulunamadı.", 404)
        bas, bit = vals.get("baslangic", it.baslangic), vals.get("bitis", it.bitis)
        if "baslangic" in vals and "bitis" not in vals and bas and it.baslangic and it.bitis and bit < bas:
            # Yalnız başlangıç kaydırıldıysa kalemin süresi korunur (tek günlük kalemde bitiş de aynı güne gelir).
            try:
                bit = bas + (it.bitis - it.baslangic)
            except TypeError:
                bit = bas
            vals["bitis"] = bit
        if bas and bit and bit < bas:
            raise C.MarketingError("Bitiş başlangıçtan önce olamaz.")
        old = {k: getattr(it, k) for k in vals}
        c.execute(ITEMS.update().where(ITEMS.c.id == it.id).values(elle=True, **vals))
        _refresh_conflicts(c, r.id, st["conflictKeys"])
        C.event(c, r.id, user, "ay-kalem", {"id": it.id, **old}, {"id": it.id, **vals})
    return _item_row(engine, item_id)


def add_item(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, donem: str, body: dict[str, Any],
             st: dict[str, Any]) -> dict[str, Any]:
    tur = str(body.get("tur") or "diger")
    if tur not in TYPES:
        raise C.MarketingError("Kalem türü tanınmıyor.")
    vals = _clean_item({"baslik": body.get("baslik"), **{k: body[k] for k in ("baslangic", "bitis", "kanal", "butce", "aciklama")
                                                         if k in body}}, donem)
    if not vals.get("baslangic"):
        raise C.MarketingError("Başlangıç tarihi gerekli.")
    stok = C.one_line(body.get("stokKodu"), 60)
    iid = C._uid()
    with engine.begin() as c:
        r = C._row(c, tenant, plan_id, lock=True)
        C.editable(r)
        n = c.execute(sa.select(sa.func.count()).select_from(ITEMS).where(ITEMS.c.plan_id == r.id)).scalar() or 0
        c.execute(ITEMS.insert().values(id=iid, plan_id=r.id, sira=int(n), tur=tur, kaynak="kullanici", kaynak_ref=iid,
                                        stok_kodu=stok, elle=True, detay_json=C.dump({"ekleyen": user}), **vals))
        _refresh_conflicts(c, r.id, st["conflictKeys"])
        C.event(c, r.id, user, "ay-kalem-ekle", None, {"id": iid, "tur": tur, "baslik": vals.get("baslik")})
    return _item_row(engine, iid)


def delete_item(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, item_id: str, st: dict[str, Any]) -> dict[str, Any]:
    """Yalnız elle eklenen kalem silinir; kaynaktan gelen kalem kaynağında (CRM, M15, M17) değişir."""
    with engine.begin() as c:
        r = C._row(c, tenant, plan_id, lock=True)
        C.editable(r)
        it = c.execute(sa.select(ITEMS).where(ITEMS.c.plan_id == r.id, ITEMS.c.id == str(item_id)[:32])).first()
        if not it:
            raise C.MarketingError("Kalem bulunamadı.", 404)
        if it.kaynak != "kullanici":
            raise C.MarketingError("Kaynaktan gelen kalem silinmez; kaynağında (CRM ya da ilgili plan) değiştirin.", 409)
        c.execute(ITEMS.delete().where(ITEMS.c.id == it.id))
        _refresh_conflicts(c, r.id, st["conflictKeys"])
        C.event(c, r.id, user, "ay-kalem-sil", {"id": it.id, "baslik": it.baslik}, None)
    return {"id": it.id, "baslik": it.baslik}


def _item_row(engine: sa.engine.Engine, item_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(ITEMS).where(ITEMS.c.id == str(item_id)[:32])).one()
    out = _item(r)
    out.pop("stok_kodu", None)
    return out


# ------------------------------------------------------------------ M46: hedef, gerçekleşen, sapma


def month_targets(engine: Any, tenant: str, donem: str) -> dict[str, Any]:
    """M46 yürürlükteki planından ayın hedefi: segment başına ciro/adet ve kitap başına ay hedefi."""
    y, m = int(donem[:4]), int(donem[5:7])
    t = P.budget_read(engine, lambda: B.approved_targets(engine, tenant, y, with_actuals=False), None, "ay hedefi")
    if t is None:
        return {"year": y, "planId": None, "not": "Bütçe ve hedefler modülü bu kurulumda okunamıyor; hedef yok.",
                "segment": {}, "kitap": {}}
    if not t.get("plan"):
        return {"year": y, "planId": None, "not": f"{y} bütçesi henüz onaylanmadı; ay hedefi yok.", "segment": {}, "kitap": {}}
    seg: dict[str, dict[str, float]] = {s: {"ciro": 0.0, "adet": 0.0, "kitap": 0} for s in SEGMENTS}
    books: dict[str, dict[str, Any]] = {}
    for it in t["items"]:
        a = it["aylik"][m - 1]
        s = seg.setdefault(it["segment"], {"ciro": 0.0, "adet": 0.0, "kitap": 0})
        s["ciro"] += a["ciro"]
        s["adet"] += a["adet"]
        s["kitap"] += 1
        books[it["stokKodu"]] = {"segment": it["segment"], "ciro": a["ciro"], "adet": a["adet"]}
    for s in seg.values():
        s["ciro"], s["adet"] = round(s["ciro"], 2), round(s["adet"], 2)
    return {"year": y, "planId": t["plan"]["id"], "version": t["plan"]["version"], "planTitle": t["plan"]["title"],
            "segment": seg, "kitap": books,
            "kaynak": "Bütçe ve hedefler modülünün yürürlükteki planı: kitap hedeflerinin bu aya düşen payı (aylık dağılım)."}


def month_actuals_stmt(y: int, m: int):
    """Ayın Logo gerçekleşmesi okuması (bütçe modülünün önbelleği, kitap × ay)."""
    return sa.select(B.SALES.c.stok_kodu, B.SALES.c.adet, B.SALES.c.ciro).where(B.SALES.c.year == y, B.SALES.c.month == m)


def month_actuals(engine: Any, donem: str) -> dict[str, Any]:
    """Logo gerçekleşmesi (M46 önbelleği) o ay: kitap başına net ciro/adet, şirket toplamı (157 ticari ürün hariç)."""
    y, m = int(donem[:4]), int(donem[5:7])

    def read() -> dict[str, Any]:
        with engine.connect() as c:
            rows = c.execute(month_actuals_stmt(y, m)).all()
        return {"kitap": {r.stok_kodu: {"ciro": float(r.ciro or 0), "adet": float(r.adet or 0)} for r in rows}}

    out = P.budget_read(engine, read, None, "ay gerçekleşmesi")
    end = P.data_end(engine)
    first, last = bounds(donem)
    if out is None:
        return {"hazir": False, "kitap": {}, "sirketCiro": None, "veriSonu": end.isoformat() if end else None,
                "not": "Bütçe modülünün Logo satış önbelleği okunamadı."}
    ciro = round(sum(v["ciro"] for k, v in out["kitap"].items() if not B._is_trade(k)), 2)
    partial = end is None or end < last
    return {"hazir": True, "kitap": out["kitap"], "sirketCiro": ciro if end and end >= first else None,
            "veriSonu": end.isoformat() if end else None, "kismi": partial,
            "not": None if not partial else (f"Logo verisi {end.strftime('%d.%m.%Y')} tarihinde bitiyor; ay tam değil." if end
                                             else "Logo gerçekleşmesi henüz okunmadı."),
            "kaynak": "Logo faturalı satış (net ciro = satır net tutarı, iade düşülmüş), bütçe modülünün aylık önbelleği; "
                      "157 ile başlayan ticari ürünler hariç."}


def segment_ratios(targets: dict[str, Any], actuals: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Segment başına hedefli kitapların gerçekleşeni ÷ hedefi (aynı kitap kümesi)."""
    out: dict[str, dict[str, Any]] = {}
    if not targets.get("planId") or not actuals.get("hazir"):
        return out
    for s in SEGMENTS:
        codes = [k for k, v in targets["kitap"].items() if v["segment"] == s]
        hedef = sum(targets["kitap"][k]["ciro"] for k in codes)
        gercek = sum((actuals["kitap"].get(k) or {}).get("ciro", 0.0) for k in codes)
        out[s] = {"hedef": round(hedef, 2), "gercek": round(gercek, 2), "oran": round(gercek / hedef, 4) if hedef > 0 else None,
                  "kitap": len(codes)}
    return out


def open_deviations(engine: Any, tenant: str, year: int) -> dict[str, dict[str, Any]]:
    """M46'nın açık kitap sapma uyarıları (M18'e açılmış olanlar): stok kodu → oran, eksik ciro."""
    res = P.budget_read(engine, lambda: B.deviations(engine, tenant, year, status="acik", scope="kitap", module="M18"), None,
                        "sapma")
    out: dict[str, dict[str, Any]] = {}
    if not res:
        return out
    page = 0
    while True:
        for a in res["items"]:
            out[a["key"]] = {"oran": a["ratio"], "eksik": a["gap"], "ad": a["label"]}
        if (page + 1) * res["pageSize"] >= res["total"]:
            break
        page += 1
        res = B.deviations(engine, tenant, year, status="acik", scope="kitap", module="M18", page=page)
    return out


def task_stats_stmt(tenant: str, donem: str):
    """Onaylı planların o aya düşen işleri, durum × kanal sayısı (aynı ifade sorgu bilgisinde)."""
    first, last = bounds(donem)
    return (sa.select(C.TASKS.c.durum, C.TASKS.c.kanal, sa.func.count()).select_from(
        C.TASKS.join(C.PLANS, C.PLANS.c.id == C.TASKS.c.plan_id)).where(
        C.PLANS.c.tenant_id == tenant, C.PLANS.c.durum == "onayli",
        C.TASKS.c.tarih >= first.isoformat(), C.TASKS.c.tarih <= last.isoformat()).group_by(C.TASKS.c.durum, C.TASKS.c.kanal))


def task_stats(engine: Any, tenant: str, donem: str) -> dict[str, Any]:
    """Onaylı (ve arşivdeki eski onaylı) planların o aya düşen işleri: yapılan / atlanan / bekleyen."""
    with engine.connect() as c:
        rows = c.execute(task_stats_stmt(tenant, donem)).all()
    tot: dict[str, int] = {"bekliyor": 0, "yapildi": 0, "atlandi": 0}
    kanal: dict[str, dict[str, int]] = defaultdict(lambda: {"bekliyor": 0, "yapildi": 0, "atlandi": 0})
    for d, k, n in rows:
        tot[d] = tot.get(d, 0) + int(n)
        kanal[k or "_"][d] = kanal[k or "_"].get(d, 0) + int(n)
    n = sum(tot.values())
    return {"toplam": n, **tot, "oran": round(tot["yapildi"] / n, 4) if n else None,
            "kanal": {k: v for k, v in kanal.items()}}


# ------------------------------------------------------------------ bütçe önerisi


def frame_of(engine: Any, plan: dict[str, Any], targets: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    src = plan.get("butceCerceveKaynak") or {}
    if src.get("kaynak") == "elle" and plan.get("butceCerceve") is not None:
        return {"tutar": plan["butceCerceve"], "kaynak": "elle", "gerekce": "Pazarlama müdürü elle girdi."}
    if st.get("monthlyBudget"):
        return {"tutar": round(float(st["monthlyBudget"]), 2), "kaynak": "ayar",
                "gerekce": "Yönetim → Pazarlama planları → Aylık pazarlama bütçesi."}
    total = sum(v["ciro"] for v in (targets.get("segment") or {}).values())
    if st.get("rate") is not None:
        rate, basis = st["rate"], {"kaynak": "ayar"}
    else:
        dr = P.dept_ratio(engine, st)
        rate, basis = (dr["oran"], {"kaynak": "veri", **dr}) if dr else (None, None)
    if rate is None:
        return {"tutar": None, "kaynak": None, "gerekce": "Bütçe çerçevesi yok: aylık bütçe ve oran ayarı boş, Logo'da pazarlama "
                "masraf merkezi gideri okunamadı. Tutarları elle girin."}
    if total <= 0:
        return {"tutar": None, "kaynak": None, "oran": {**basis, "oran": rate},
                "gerekce": "Bütçe çerçevesi yok: bu ay için onaylı satış hedefi yok (oran ay hedef cirosuna uygulanır)."}
    pct = f"%{rate * 100:.2f}".replace(".", ",")
    why = f"Ayın hedef cirosu × {pct}. Oran " + ("yönetim ayarından." if basis["kaynak"] == "ayar" else
                                                f"{basis['yil']} yılı pazarlama masraf merkezi gideri ÷ şirket net cirosu.")
    return {"tutar": round(total * rate, 2), "kaynak": "oran", "oran": {**basis, "oran": rate}, "gerekce": why}


def segment_weights(targets: dict[str, Any], ratios: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Ağırlık = hedef payı × (1 + hedefin altında kalınan pay). Önceki ay oranı yoksa yalnız hedef payı."""
    seg = targets.get("segment") or {}
    total = sum(seg.get(s, {}).get("ciro", 0.0) for s in SEGMENTS)
    if total <= 0:
        return {}
    raw: dict[str, dict[str, Any]] = {}
    for s in SEGMENTS:
        pay = seg.get(s, {}).get("ciro", 0.0) / total
        oran = (ratios.get(s) or {}).get("oran")
        boost = 1 + max(0.0, 1 - oran) if oran is not None else 1.0
        raw[s] = {"hedefPayi": round(pay, 6), "oncekiAyOran": oran, "carpan": round(boost, 4), "w": pay * boost}
    wsum = sum(v["w"] for v in raw.values())
    for v in raw.values():
        v["pay"] = round(v.pop("w") / wsum, 6) if wsum > 0 else 0.0
    return raw


def suggest_budget(engine: Any, crm: Crm, plan: dict[str, Any], targets: dict[str, Any], ratios: dict[str, dict[str, Any]],
                   st: dict[str, Any]) -> dict[str, Any]:
    frame = frame_of(engine, plan, targets, st)
    weights = segment_weights(targets, ratios)
    rows: list[dict[str, Any]] = []
    shares_by: dict[str, Any] = {}
    for s, w in weights.items():
        if not w.get("pay"):
            continue                                   # bu ay hedefi olmayan segmente sıfır tutarlı satır açılmaz
        codes = [k for k, v in (targets.get("kitap") or {}).items() if v["segment"] == s]
        try:
            sh = P.channel_shares(crm, codes, st)
        except SourceError as e:
            sh = {"paylar": {}, "taban": {"kaynak": None, "hata": str(e)}}
        shares_by[s] = sh
        seg_amount = (frame.get("tutar") or 0.0) * w["pay"]
        paylar = sh.get("paylar") or {}
        for k, share in paylar.items():
            pct, spct = f"%{share * 100:.1f}".replace(".", ","), f"%{w['pay'] * 100:.1f}".replace(".", ",")
            taban = sh.get("taban") or {}
            base = ("bu segmentin kitaplarına bağlı CRM pazarlama harcaması" if taban.get("kaynak") == "emsal"
                    else f"son {taban.get('yil')} yılın şirket geneli CRM pazarlama harcaması")
            rows.append({"segment": s, "kanal": k, "oneri": float(round(seg_amount * share)), "hedef_payi": w["hedefPayi"],
                         "onceki_ay_oran": w["oncekiAyOran"],
                         "gerekce": f"{SEGMENTS[s]} payı {spct} (hedef payı × önceki ay açığı), kanal payı {pct}: {base}."})
    total = frame.get("tutar")
    if total and rows:
        diff = round(total - sum(r["oneri"] for r in rows), 2)
        if diff:
            rows[0]["oneri"] = round(rows[0]["oneri"] + diff, 2)
    return {"cerceve": frame, "agirlik": weights, "kanalPaylari": {s: {"paylar": v.get("paylar"), "taban": v.get("taban")}
                                                                 for s, v in shares_by.items()}, "satirlar": rows}


def budget_stmt(plan_id: str):
    return sa.select(BUDGET).where(BUDGET.c.plan_id == plan_id).order_by(BUDGET.c.segment, BUDGET.c.oneri.desc())


def _budget_rows(c: Any, plan_id: str) -> list[Any]:
    return c.execute(budget_stmt(plan_id)).all()


def _mirror_lines(c: Any, plan_id: str, donem: str) -> float:
    """Bütçe payları → çekirdeğin bütçe satırları (onay eşiği, CSV/PDF ve «CRM'e işlenecek» aynı satırlardan çalışır)."""
    first, last = bounds(donem)
    c.execute(C.LINES.delete().where(C.LINES.c.plan_id == plan_id))
    for i, b in enumerate(_budget_rows(c, plan_id)):
        tutar = b.onayli if b.onayli is not None else b.oneri
        c.execute(C.LINES.insert().values(
            id=C._uid(), plan_id=plan_id, sira=i, kanal=b.kanal, alt_kanal=SEGMENTS.get(b.segment, b.segment),
            aciklama=None, tutar=round(float(tutar or 0), 2), baslangic=first.isoformat(), bitis=last.isoformat(),
            kpi_json=None, kaynak="kullanici" if b.onayli is not None else "zeki", gerekce=b.gerekce,
            elle_duzeltildi=b.onayli is not None))
    total = C._total(c, plan_id)
    c.execute(C.PLANS.update().where(C.PLANS.c.id == plan_id).values(butce_toplam=total))
    return total


def put_suggestion(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, donem: str, sug: dict[str, Any]) -> None:
    """Öneri satırları yazılır; müdürün düzelttiği tutar (`onayli`) aynı segment × kanalda korunur."""
    with engine.begin() as c:
        r = C._row(c, tenant, plan_id, lock=True)
        C.editable(r)
        keep = {(b.segment, b.kanal): b.onayli for b in _budget_rows(c, r.id) if b.onayli is not None}
        c.execute(BUDGET.delete().where(BUDGET.c.plan_id == r.id))
        seen = set()
        for x in sug["satirlar"]:
            key = (x["segment"], x["kanal"])
            seen.add(key)
            c.execute(BUDGET.insert().values(plan_id=r.id, segment=x["segment"], kanal=x["kanal"], oneri=x["oneri"],
                                             onayli=keep.get(key), hedef_payi=x["hedef_payi"], onceki_ay_oran=x["onceki_ay_oran"],
                                             gerekce=x["gerekce"]))
        for key, v in keep.items():
            if key not in seen:
                c.execute(BUDGET.insert().values(plan_id=r.id, segment=key[0], kanal=key[1], oneri=0.0, onayli=v,
                                                 gerekce="Elle girildi; öneride bu kanal yok."))
        frame = sug["cerceve"]
        vals: dict[str, Any] = {"butce_cerceve_json": C.dump({**frame, "agirlik": sug["agirlik"]})}
        if frame.get("kaynak") != "elle":
            vals["butce_cerceve"] = frame.get("tutar")
        c.execute(C.PLANS.update().where(C.PLANS.c.id == r.id).values(**vals))
        total = _mirror_lines(c, r.id, donem)
        C.event(c, r.id, user, "oneri-butce", None, {"toplam": total, "cerceve": frame.get("kaynak"), "korunan": len(keep)})


def put_budget(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, donem: str, body: dict[str, Any]) -> float:
    """Müdürün düzeltmesi: `items` [{segment, kanal, onayli}] (boş = öneriye dön), isteğe bağlı `cerceve`."""
    items = body.get("items")
    if items is not None and not isinstance(items, list):
        raise C.MarketingError("Bütçe satırları liste olmalı.")
    with engine.begin() as c:
        r = C._row(c, tenant, plan_id, lock=True)
        C.editable(r)
        old = {(b.segment, b.kanal): (b.onayli, b.oneri) for b in _budget_rows(c, r.id)}
        for i, x in enumerate(items or []):
            seg, kanal = str(x.get("segment") or ""), str(x.get("kanal") or "")
            if seg not in SEGMENTS or kanal not in C.CHANNELS:
                raise C.MarketingError(f"{i + 1}. satır: segment ya da kanal tanınmıyor.")
            v = C.number(x.get("onayli"), f"{i + 1}. satırın tutarı", allow_none=True)
            v = None if v is None else round(v, 2)
            if (seg, kanal) in old:
                c.execute(BUDGET.update().where(BUDGET.c.plan_id == r.id, BUDGET.c.segment == seg, BUDGET.c.kanal == kanal)
                          .values(onayli=v))
            elif v is not None:
                c.execute(BUDGET.insert().values(plan_id=r.id, segment=seg, kanal=kanal, oneri=0.0, onayli=v,
                                                 gerekce="Elle eklendi."))
        if "cerceve" in body:
            v = C.number(body.get("cerceve"), "Aylık bütçe çerçevesi", allow_none=True)
            c.execute(C.PLANS.update().where(C.PLANS.c.id == r.id).values(
                butce_cerceve=None if v is None else round(v, 2),
                butce_cerceve_json=C.dump({"kaynak": "elle", "gerekce": C.text(body.get("not"), 2000) or "Pazarlama müdürü elle girdi.",
                                           "kim": user}) if v is not None else None))
        total = _mirror_lines(c, r.id, donem)
        c.execute(C.PLANS.update().where(C.PLANS.c.id == r.id).values(guncelleyen=user, guncelleme=C.now()))
        C.event(c, r.id, user, "butce", {"satir": len(old)}, {"toplam": total, "degisen": len(items or []),
                                                               "not": C.text(body.get("not"), 2000)})
    return total


def budget_of(engine: sa.engine.Engine, plan_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = _budget_rows(c, plan_id)
    return [{"segment": b.segment, "segmentAdi": SEGMENTS.get(b.segment, b.segment), "kanal": b.kanal,
             "kanalAdi": C.CHANNELS.get(b.kanal, b.kanal), "oneri": b.oneri, "onayli": b.onayli,
             "tutar": b.onayli if b.onayli is not None else b.oneri, "hedefPayi": b.hedef_payi,
             "oncekiAyOran": b.onceki_ay_oran, "gerekce": b.gerekce} for b in rows]


# ------------------------------------------------------------------ kurma


def build(engine: sa.engine.Engine, tenant: str, user: str, crm: Crm, st: dict[str, Any], donem: str, *,
          fresh: bool = True) -> dict[str, Any]:
    """Taslağı kurar ya da yeniden kurar: kalemler kaynaklardan, bütçe önerisi M46'dan. Elle düzeltilenler korunur."""
    donem = parse_donem(donem)
    ensure(engine)
    pid = _open_plan(engine, tenant, user, donem)
    found = collect(engine, tenant, crm, st, donem, fresh=fresh)
    targets = month_targets(engine, tenant, donem)
    for it in found["items"]:
        if it["tur"] == "yeni" and it["kaynak"] == "crm-kitap":
            t = targets["kitap"].get(it["stok_kodu"])
            it["detay"]["hedefAy"] = {"ciro": t["ciro"], "adet": t["adet"], "segment": t["segment"]} if t else None
    y, m = int(donem[:4]), int(donem[5:7])
    codes = [it["stok_kodu"] for it in found["items"] if it["tur"] == "yeni" and it["kaynak"] == "crm-kitap"]
    try:
        region = crm.region_targets(y, m, codes)
    except SourceError as e:
        region, _ = None, found["notlar"].append(f"CRM bölge satış hedefleri okunamadı: {e}")
    if region is not None:
        for it in found["items"]:
            if it["tur"] == "yeni" and it["kaynak"] == "crm-kitap":
                it["detay"]["crmBolgeHedefi"] = region.get(it["stok_kodu"])
    dev = open_deviations(engine, tenant, y)
    for it in found["items"]:
        if it.get("stok_kodu") and it["stok_kodu"] in dev:
            it["detay"]["sapma"] = dev[it["stok_kodu"]]
    stats = sync_items(engine, tenant, user, pid, found["items"], st)
    prev = shift(donem, -1)
    ratios = segment_ratios(month_targets(engine, tenant, prev), month_actuals(engine, prev))
    plan = C.plan_full(engine, tenant, pid)
    sug = suggest_budget(engine, crm, plan, targets, ratios, st)
    put_suggestion(engine, tenant, user, pid, donem, sug)
    z = dict(plan.get("zeki") or {})
    z.update({"notlar": found["notlar"], "kuruldu": C.iso(C.now()), "kuran": user})
    C.set_fields(engine, pid, zeki_json=C.dump(z), hedef_json=C.dump({k: v for k, v in targets.items() if k != "kitap"}))
    return {"planId": pid, "donem": donem, "stats": stats, "notlar": found["notlar"]}


# ------------------------------------------------------------------ görünüm


def view(engine: sa.engine.Engine, tenant: str, donem: str, st: dict[str, Any], *, plan_id: Optional[str] = None) -> dict[str, Any]:
    """Ay ekranı: plan başlığı, kalemler (takvim), haftalar, bütçe, hedef, önceki ay özeti. Föy özeti uç katmanında eklenir."""
    donem = parse_donem(donem)
    ensure(engine)
    head = C.plan_full(engine, tenant, plan_id) if plan_id else None
    if head is None:
        h = find_plan(engine, tenant, donem)
        head = C.plan_full(engine, tenant, h["id"]) if h else None
    prev = shift(donem, -1)
    targets = month_targets(engine, tenant, donem)
    prev_targets = month_targets(engine, tenant, prev)
    prev_actuals = month_actuals(engine, prev)
    ratios = segment_ratios(prev_targets, prev_actuals)
    prev_plan = find_plan(engine, tenant, prev, approved=True)
    items = items_of(engine, head["id"]) if head else []
    seg = targets.get("segment") or {}
    total_target = sum(v["ciro"] for v in seg.values()) if seg else None
    hedefli = sum(v["hedef"] for v in ratios.values()) if ratios else None
    gercek = sum(v["gercek"] for v in ratios.values()) if ratios else None
    return {
        "donem": donem, "donemAdi": label(donem), "onceki": prev, "sonraki": shift(donem, 1),
        "plan": head, "items": items, "weeks": weeks(donem),
        "budget": budget_of(engine, head["id"]) if head else [],
        "hedef": {**{k: v for k, v in targets.items() if k != "kitap"},
                  "toplamCiro": round(total_target, 2) if total_target is not None else None,
                  "paylar": {s: (round(v["ciro"] / total_target, 4) if total_target else None) for s, v in seg.items()}},
        "oncekiAy": {"donem": prev, "donemAdi": label(prev), "hedef": round(hedefli, 2) if hedefli is not None else None,
                     "gercek": round(gercek, 2) if gercek is not None else None,
                     "oran": round(gercek / hedefli, 4) if hedefli else None, "segment": ratios,
                     "sirketCiro": prev_actuals.get("sirketCiro"), "veriSonu": prev_actuals.get("veriSonu"),
                     "not": prev_actuals.get("not") or (prev_targets.get("not") if not prev_targets.get("planId") else None),
                     "kaynak": prev_actuals.get("kaynak"),
                     "isler": task_stats(engine, tenant, prev),
                     "plan": {"id": prev_plan["id"], "durumAdi": prev_plan["durumAdi"]} if prev_plan else None},
        "cakismaSayisi": sum(1 for x in items if x["cakisma"]),
        "sayilar": {t: sum(1 for x in items if x["tur"] == t) for t in TYPES},
    }


def redact(v: dict[str, Any]) -> dict[str, Any]:
    """Bütçe görme yetkisi olmayan kişi: tutarlar, hedef cirolar ve gerçekleşen ciro boş (oranlar kalır)."""
    out = {**v, "budget": [{**b, "oneri": None, "onayli": None, "tutar": None} for b in v.get("budget") or []]}
    if v.get("plan"):
        p = dict(v["plan"])
        p.update({"butceToplam": None, "butceCerceve": None, "butceCerceveKaynak": None,
                  "lines": [{**ln, "tutar": None} for ln in p.get("lines") or []]})
        out["plan"] = p
    out["items"] = [{**x, "butce": None, "detay": {**x["detay"], "hedefAy": ({**x["detay"]["hedefAy"], "ciro": None}
                                                                             if x["detay"].get("hedefAy") else None),
                                                   "planlananCiro": None, "gerceklesenCiro": None}}
                    for x in v.get("items") or []]
    h = dict(v.get("hedef") or {})
    h["toplamCiro"] = None
    h["segment"] = {s: {**x, "ciro": None} for s, x in (h.get("segment") or {}).items()}
    out["hedef"] = h
    o = dict(v.get("oncekiAy") or {})
    o.update({"hedef": None, "gercek": None, "sirketCiro": None,
              "segment": {s: {**x, "hedef": None, "gercek": None} for s, x in (o.get("segment") or {}).items()}})
    out["oncekiAy"] = o
    return out


# ------------------------------------------------------------------ Zeki AI gerekçe ve ay özeti


def _facts(v: dict[str, Any]) -> list[str]:
    f: list[str] = []
    for s, p in (v["hedef"].get("paylar") or {}).items():
        if p is not None:
            f.append(f"{SEGMENTS.get(s, s)} ay hedef payı: %{p * 100:.1f}".replace(".", ","))
    for s, x in (v["oncekiAy"].get("segment") or {}).items():
        if x.get("oran") is not None:
            f.append(f"{SEGMENTS.get(s, s)} önceki ay hedefe oranı: %{x['oran'] * 100:.1f}".replace(".", ","))
    tot = sum(b["tutar"] or 0 for b in v["budget"])
    by: dict[str, float] = defaultdict(float)
    for b in v["budget"]:
        by[b["segment"]] += b["tutar"] or 0
    for s, a in by.items():
        if tot > 0:
            f.append(f"{SEGMENTS.get(s, s)} bütçe payı: %{a / tot * 100:.1f}".replace(".", ","))
    n = v.get("sayilar") or {}
    f.append(f"Yeni kitap kalemi: {n.get('yeni', 0)}; backlist kalemi: {n.get('backlist', 0)}; özel gün: {n.get('ozel-gun', 0)}; "
             f"B2B kampanyası: {n.get('b2b-kampanya', 0)}; çakışma: {v.get('cakismaSayisi', 0)}")
    isler = v["oncekiAy"].get("isler") or {}
    if isler.get("toplam"):
        f.append(f"Önceki ay planlanan iş: {isler['toplam']}; yapılan: {isler['yapildi']}")
    if v["oncekiAy"].get("oran") is not None:
        f.append(f"Önceki ay hedefli kitapların hedefe oranı: %{v['oncekiAy']['oran'] * 100:.1f}".replace(".", ","))
    return f


def explain(llm: Any, v: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    """Bütçe dağılımının gerekçesi ve genel müdüre üç paragraf ay özeti. Rakamlar olgu listesinden; denetimden geçmeyen
    cümle düşer."""
    facts = _facts(v)
    titles = [x["baslik"] for x in v["items"] if x["tur"] in ("yeni", "ozel-gun", "b2b-kampanya")]
    src = titles + facts
    base = ("Olgu listesi (yazabileceğin sayılar yalnız bunlar):\n" + "\n".join(facts) +
            "\n\nAyın kalemleri (adlar):\n" + "\n".join(f"- {t}" for t in titles[:400]))
    p1 = ("Pazarlama müdürüne, bu ayın pazarlama bütçesinin yeni kitap ve backlist arasında neden bu oranda dağıtıldığını "
          "üç dört cümleyle anlat. Dağılım kodla hesaplandı: segment payı = ayın satış hedefindeki payı × önceki ay hedefin "
          "altında kalındıysa açık kadar artış. Yeni sayı üretme.\n\n" + base)
    p2 = (f"{v['donemAdi']} pazarlama planını genel müdüre üç kısa paragrafta özetle: ayın ana işleri, bütçenin dağılımı "
          "ve dikkat edilecek çakışma ya da riskler. Yeni sayı üretme.\n\n" + base)
    out: dict[str, Any] = {}
    for key, prompt, n in (("butceGerekce", p1, 600), ("ozet", p2, 900)):
        raw = str(llm.chat([{"role": "system", "content": P.SYSTEM}, {"role": "user", "content": prompt}], max_tokens=n) or "")
        res = G.check(raw, src, facts, st.get("claims") or ())
        out[key] = res["metin"] or None
        out[key + "Dusen"] = res["dusenSayisi"]
    return out


# ------------------------------------------------------------------ sözleşme (M22/M24/M30/M32 okur)


def contract(engine: sa.engine.Engine, tenant: str, donem: str) -> dict[str, Any]:
    donem = parse_donem(donem)
    ensure(engine)
    h = find_plan(engine, tenant, donem, approved=True)
    if not h:
        return {"donem": donem, "plan": None, "items": [], "not": f"{label(donem)} için onaylı ay planı yok."}
    full = C.plan_full(engine, tenant, h["id"])
    full.pop("zeki", None)
    return {"donem": donem, "plan": {k: full[k] for k in ("id", "baslik", "surum", "durum", "onaylayan", "onayZamani", "butceToplam")},
            "items": items_of(engine, h["id"]), "budget": budget_of(engine, h["id"])}
