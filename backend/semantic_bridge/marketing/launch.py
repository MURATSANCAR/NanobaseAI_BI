"""M16 Lansman / yayın ayı pazarlama: onaylı M15 planından lansman paketi, kontrol listesi, ilk 7/30 gün izleme,
stok–talep uyarısı, etkinlik ve medya kaydı, D+7 / D+30 değerlendirmesi.

**Lansman** onaylı bir yeni kitap planından (M15, `kind='yeni'`, `durum='onayli'`) açılır: elle ya da yayına
`MARKETING_LAUNCH_OPEN_DAYS` gün kala zamanlayıcıyla (K1). Kimlik `ML-<yıl>-<sıra>`. Durum yayın gününe göre kendiliğinden
yürür: `hazirlik` (yayından önce) → `yayinda` (D0…D+6) → `izleme` (D+7…D+30) → `kapandi` (D+30 raporu hazırlandıktan
sonra ya da elle).

**Kontrol listesi** çekirdeğin `semantic_mkt_tasks` tablosundadır (yeni tablo yok): planın takvim işleri lansmana bağlanır
(`launch_id`), üstüne lansmana özgü şablon işleri (`kaynak='lansman'`, Yönetim → «Lansman kontrol listesi») eklenir.
Madde «yapıldı» işaretlendiğinde planın takviminde de yapılmış görünür (tek kayıt).

**İzleme** (`semantic_mkt_launch_daily`, lansman × gün): CRM sipariş sinyali ve dağılım (saatlik okuma aynı günün
satırını günceller), açık sipariş / bekleyen ürün ve depo stoku (okunduğu günün satırına; geçmiş günlere geriye dönük
yazılmaz), Logo faturalı net adet/ciro (günde bir; Logo verisinin bittiği günden sonrası boş kalır), M46 hedefinin
günlük payı (yürürlükteki planın aylık hedefi ÷ ayın gün sayısı — M46 izlemesinin gün oranı). Rakamı model üretmez.

**Yazma yok:** CRM'e, Logo'ya, T-soft'a ve hiçbir dış kanala gönderim yoktur. Sosyal medya/e-bülten/reklam işleri
kontrol listesinde hatırlatmadır; kişi yayınlar ve «yapıldı» + bağlantı ile işaretler. Portalda girilen etkinlik ve
medya kayıtları «CRM'e işlenecek» listesinde durur.
"""
from __future__ import annotations

import calendar
import threading
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.marketing import core as C

_md = sa.MetaData()

LAUNCHES = sa.Table(
    "semantic_mkt_launches", _md,
    sa.Column("id", sa.String(24), primary_key=True),                 # ML-<yıl>-<sıra>
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("plan_id", sa.String(24), nullable=False, index=True),   # M15 planı
    sa.Column("stok_kodu", sa.String(60), nullable=False, index=True),
    sa.Column("crm_kitap_id", sa.String(40)),
    sa.Column("baslik", sa.String(400), nullable=False),
    sa.Column("yayin_gunu", sa.String(10), nullable=False),
    sa.Column("yayin_gunu_kaynagi", sa.String(16), nullable=False),    # kitap|proje|uretim-depo|uretim-dagilim|uretim|elle
    sa.Column("durum", sa.String(12), nullable=False),                 # hazirlik | yayinda | izleme | kapandi
    sa.Column("elle_kapandi", sa.Boolean, nullable=False, default=False),
    sa.Column("sahip", sa.String(120)),
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
    sa.Column("kapanis", sa.DateTime(timezone=True)),
    sa.Column("ozet_json", sa.Text),                                   # son okumanın özeti, uyarılar, emsal, SQL
    sa.Column("okuma", sa.DateTime(timezone=True)),
)
DAILY = sa.Table(
    "semantic_mkt_launch_daily", _md,
    sa.Column("launch_id", sa.String(24), primary_key=True),
    sa.Column("gun", sa.String(10), primary_key=True),
    sa.Column("siparis_adet", sa.Float),                                # CRM, sayılmayan durumlar hariç
    sa.Column("siparis_satiri", sa.Float),
    sa.Column("dagilim_adet", sa.Float),                                # sipariş tipi 2
    sa.Column("sevk_adet", sa.Float),
    sa.Column("bekleyen_adet", sa.Float),                               # açık sipariş (Baskı Öneri tanımı), o günün okuması
    sa.Column("bekleyen_urun_adet", sa.Float),                          # CRM «Bekleyen Ürün», o günün okuması
    sa.Column("fatura_net_adet", sa.Float),                             # Logo faturalı satış
    sa.Column("fatura_net_ciro", sa.Float),
    sa.Column("depo_stok", sa.Float),                                   # Logo depo görünümü, o günün okuması
    sa.Column("hedef_payi_adet", sa.Float),                             # M46 aylık hedef ÷ ayın gün sayısı
    sa.Column("hedef_payi_ciro", sa.Float),
    sa.Column("veri_sonu_logo", sa.String(10)),
    sa.Column("okuma_zamani", sa.DateTime(timezone=True)),
)
EVENTS = sa.Table(
    "semantic_mkt_launch_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("launch_id", sa.String(24), nullable=False, index=True),
    sa.Column("kaynak", sa.String(60), nullable=False),                 # crm:<etkinlikId> (portalda düzeltilen) | elle
    sa.Column("ad", sa.String(400)),
    sa.Column("tur", sa.String(120)),
    sa.Column("tarih", sa.String(10)),
    sa.Column("yer", sa.String(400)),
    sa.Column("katilimci", sa.Float),
    sa.Column("satilan", sa.Float),
    sa.Column("gelir", sa.Float),
    sa.Column("gider", sa.Float),
    sa.Column("not_", sa.Text),
    sa.Column("giren", sa.String(120), nullable=False),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)
MEDIA = sa.Table(
    "semantic_mkt_launch_media", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("launch_id", sa.String(24), nullable=False, index=True),
    sa.Column("kaynak", sa.String(60), nullable=False),                 # elle (basın ve web kayıtları ayrıca okunur)
    sa.Column("mecra", sa.String(200)),
    sa.Column("baslik", sa.String(500), nullable=False),
    sa.Column("url", sa.String(1000)),
    sa.Column("tarih", sa.String(10)),
    sa.Column("ton", sa.String(8)),                                     # olumlu | olumsuz | notr
    sa.Column("giren", sa.String(120), nullable=False),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)
REVIEWS = sa.Table(
    "semantic_mkt_launch_reviews", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("launch_id", sa.String(24), nullable=False, index=True),
    sa.Column("gun", sa.Integer, nullable=False),                       # 7 | 30
    sa.Column("rakam_json", sa.Text, nullable=False),                   # SQL sonuçları ve SQL metinleri
    sa.Column("ozet", sa.Text),                                         # Zeki AI (denetimden geçen)
    sa.Column("oneriler_json", sa.Text),
    sa.Column("dogrulama_json", sa.Text),
    sa.Column("durum", sa.String(12), nullable=False),                  # rakam | hazir | karar
    sa.Column("karar", sa.String(8)),                                   # artir | koru | kes | diger
    sa.Column("gerekce", sa.Text),
    sa.Column("karar_veren", sa.String(120)),
    sa.Column("karar_zamani", sa.DateTime(timezone=True)),
    sa.Column("hazirlayan", sa.String(120), nullable=False),
    sa.Column("hazirlama", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("launch_id", "gun", name="uq_mkt_launch_review_day"),
)

STATUSES = {"hazirlik": "Hazırlık", "yayinda": "Yayın haftası", "izleme": "İlk ay izleme", "kapandi": "Kapandı"}
ACTIVE = ("hazirlik", "yayinda", "izleme")
DATE_SOURCES = {"kitap": "CRM kitap kartı (ilk baskı tarihi)", "proje": "CRM proje kartı (yayın tarihi)",
                "uretim": "CRM üretim kartı", "uretim-depo": "Üretim: depo girişi", "uretim-dagilim": "Üretim: dağılım planı",
                "elle": "Elle girildi"}
PLAN_TO_LAUNCH_SOURCE = {"crm-kitap": "kitap", "crm-proje": "proje", "uretim": "uretim", "elle": "elle"}
DECISIONS = {"artir": "Bütçeyi artır", "koru": "Aynı kalsın", "kes": "Bütçeyi kes", "diger": "Diğer"}
TONES = {"olumlu": "Olumlu", "olumsuz": "Olumsuz", "notr": "Nötr"}
REVIEW_DAYS = (7, 30)
#: Lansmana özgü kontrol listesi (yayın gününe göre gün, iş, kanal, materyal türü). Planın takvimi (D−60 … D+30)
#: zaten lansmana bağlanır; burada yalnız lansman haftasının ek işleri. Yönetim → «Lansman kontrol listesi» (JSON).
#: Dış kanala gönderim/yayın insanındır: sistem hatırlatır, kişi yapar ve «yapıldı» + bağlantıyla işaretler.
DEFAULT_TASKS: list[tuple[int, str, Optional[str], Optional[str]]] = [
    (-7, "Depo girişini ve ilk baskı adedini üretimle teyit et", None, None),
    (-7, "Dağılım siparişlerinin çıktığını satışla teyit et", "satis-kampanyasi", None),
    (-5, "E-ticaret ürün sayfasını kontrol et: fiyat, görsel, açıklama (düzeltmeyi e-ticaret ekibi yapar)", "dijital", None),
    (-3, "Basın lansmanı ve yazar etkinlik takvimini kesinleştir", "etkinlik", None),
    (0, "Yayın günü: stok, dağılım ve açık siparişi kontrol et", None, None),
    (1, "Yayın günü gönderilerinin bağlantılarını kanıt olarak ekle", "sosyal-medya", "sosyal"),
    (3, "İlk basın yansımalarını Medya sekmesine ekle", "basin", None),
    (14, "Yazar etkinliklerinin sonucunu (katılımcı, satılan kitap) gir", "etkinlik", None),
]

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    C.ensure(engine)
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def _uid() -> str:
    return uuid.uuid4().hex


# ------------------------------------------------------------------ ayarlar


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    from semantic_bridge.marketing import plans as P

    base = P.settings(conf)

    def num(key: str, default: int, lo: int, hi: int) -> int:
        raw = (conf(key) or "").strip()
        try:
            return max(lo, min(hi, int(float(raw.replace(",", "."))))) if raw else default
        except ValueError:
            return default

    excluded = [int(x) for x in (conf("MARKETING_LAUNCH_ORDER_EXCLUDE") or "1,100000001").replace(";", ",").split(",")
                if x.strip().lstrip("-").isdigit()]
    tasks = DEFAULT_TASKS
    raw = (conf("MARKETING_LAUNCH_TASKS") or "").strip()
    if raw:
        try:
            parsed = [(int(t[0]), str(t[1]), t[2] or None, t[3] or None) for t in C.loads(raw, []) if len(t) >= 4]
            tasks = parsed or DEFAULT_TASKS
        except (TypeError, ValueError, IndexError):
            tasks = DEFAULT_TASKS
    return {
        "openDays": num("MARKETING_LAUNCH_OPEN_DAYS", 14, 0, 365),
        "preDays": num("MARKETING_LAUNCH_PRE_DAYS", 14, 0, 120),
        "alertRatio": num("MARKETING_LAUNCH_ALERT_RATIO", 80, 1, 100) / 100.0,
        "dailyHour": num("MARKETING_LAUNCH_DAILY_HOUR", 7, 0, 23),
        "orderExclude": excluded or [1, 100000001],
        "recipients": base["recipients"],
        "stockRecipients": [x.strip() for x in (conf("MARKETING_LAUNCH_STOCK_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x],
        "claims": base["claims"],
        "tasks": tasks,
    }


# ------------------------------------------------------------------ yardımcılar


def phase(pub: Optional[str], today: date, closed: bool = False) -> str:
    if closed:
        return "kapandi"
    if not pub:
        return "hazirlik"
    d = (today - date.fromisoformat(pub)).days
    if d < 0:
        return "hazirlik"
    return "yayinda" if d < 7 else "izleme"


def day_of(pub: Optional[str], today: date) -> Optional[int]:
    return (today - date.fromisoformat(pub)).days if pub else None


def window(pub: str, pre_days: int, today: Optional[date] = None, horizon: int = 30) -> tuple[date, date]:
    """İzleme penceresi: yayından `pre_days` gün önce … D+`horizon`−1; bugünden ileri gidilmez."""
    p = date.fromisoformat(pub)
    end = p + timedelta(days=horizon - 1)
    if today is not None:
        end = min(end, today)
    return p - timedelta(days=pre_days), end


def days_between(a: date, b: date) -> list[str]:
    return [(a + timedelta(days=i)).isoformat() for i in range(max(0, (b - a).days + 1))]


def daily_target(aylik: Optional[list[dict[str, Any]]], d: date, field: str = "adet") -> Optional[float]:
    """M46 aylık hedefinin o güne düşen payı: ayın hedefi ÷ ayın gün sayısı (M46 izlemesinin gün oranı)."""
    if not aylik:
        return None
    m = next((x for x in aylik if int(x.get("ay") or 0) == d.month), None)
    if m is None or m.get(field) is None:
        return None
    return float(m[field]) / calendar.monthrange(d.year, d.month)[1]


def next_id(c: Any, tenant: str, year: int) -> str:
    prefix = f"ML-{year}-"
    ids = c.execute(sa.select(LAUNCHES.c.id).where(LAUNCHES.c.tenant_id == tenant, LAUNCHES.c.id.like(prefix + "%"))).scalars().all()
    n = max((int(i[len(prefix):]) for i in ids if i[len(prefix):].isdigit()), default=0) + 1
    return f"{prefix}{n:04d}"


# Okuma ifadeleri ayrı kurulur: aynı ifade hem çalıştırılır hem sorgu bilgisinde gösterilir (kaynak_lansman.py).


def launch_stmt(tenant: str, lid: str):
    return sa.select(LAUNCHES).where(LAUNCHES.c.tenant_id == tenant, LAUNCHES.c.id == str(lid)[:24])


def launch_tasks_stmt(lid: str, plan_id: str):
    return (sa.select(C.TASKS).where(C.TASKS.c.launch_id == lid, C.TASKS.c.plan_id == plan_id)
            .order_by(C.TASKS.c.tarih, C.TASKS.c.id))


def launch_plan_stmt(plan_id: str):
    return sa.select(C.PLANS.c.durum, C.PLANS.c.baslik, C.PLANS.c.hedef_json).where(C.PLANS.c.id == plan_id)


def reviews_stmt(lid: str):
    return sa.select(REVIEWS).where(REVIEWS.c.launch_id == lid).order_by(REVIEWS.c.gun)


def days_stmt(lid: str):
    return sa.select(DAILY).where(DAILY.c.launch_id == lid).order_by(DAILY.c.gun)


def events_stmt(lid: str):
    return sa.select(EVENTS).where(EVENTS.c.launch_id == lid).order_by(EVENTS.c.tarih, EVENTS.c.zaman)


def media_stmt(lid: str):
    return sa.select(MEDIA).where(MEDIA.c.launch_id == lid).order_by(MEDIA.c.tarih.desc(), MEDIA.c.zaman.desc())


def list_stmt(tenant: str, *, frm: Optional[str] = None, to: Optional[str] = None, durum: str = "", sahip: str = ""):
    cond = [LAUNCHES.c.tenant_id == tenant]
    if frm:
        cond.append(LAUNCHES.c.yayin_gunu >= frm)
    if to:
        cond.append(LAUNCHES.c.yayin_gunu <= to)
    if durum:
        cond.append(LAUNCHES.c.durum.in_([d for d in durum.split(",") if d]))
    if sahip:
        cond.append(sa.func.lower(LAUNCHES.c.sahip) == sahip.lower())
    return sa.select(LAUNCHES).where(*cond).order_by(LAUNCHES.c.yayin_gunu, LAUNCHES.c.id)


def overdue_stmt(ids: list[str], today: str):
    """Lansman başına geciken (bugünden önceki, bekleyen) kontrol listesi maddesi sayısı."""
    return (sa.select(C.TASKS.c.launch_id, sa.func.count()).where(
        C.TASKS.c.launch_id.in_(ids or ["-"]), C.TASKS.c.durum == "bekliyor", C.TASKS.c.tarih < today)
        .group_by(C.TASKS.c.launch_id))


def today_stmt(tenant: str, today: str):
    return (sa.select(C.TASKS, LAUNCHES.c.baslik.label("lansman_baslik"), LAUNCHES.c.sahip.label("lansman_sahip"),
                      LAUNCHES.c.yayin_gunu, LAUNCHES.c.stok_kodu)
            .select_from(C.TASKS.join(LAUNCHES, sa.and_(LAUNCHES.c.id == C.TASKS.c.launch_id,
                                                        LAUNCHES.c.plan_id == C.TASKS.c.plan_id)))
            .where(LAUNCHES.c.tenant_id == tenant, LAUNCHES.c.durum.in_(ACTIVE), C.TASKS.c.durum == "bekliyor",
                   C.TASKS.c.tarih <= today)
            .order_by(C.TASKS.c.tarih, LAUNCHES.c.yayin_gunu))


def _row(c: Any, tenant: str, lid: str) -> Any:
    r = c.execute(launch_stmt(tenant, lid)).first()
    if not r:
        raise C.MarketingError("Lansman bulunamadı.", 404)
    return r


def head(r: Any, today: Optional[date] = None) -> dict[str, Any]:
    today = today or C.today()
    oz = C.loads(r.ozet_json, {})
    return {
        "id": r.id, "planId": r.plan_id, "stokKodu": r.stok_kodu, "crmKitapId": r.crm_kitap_id, "baslik": r.baslik,
        "yayinGunu": r.yayin_gunu, "yayinGunuKaynagi": r.yayin_gunu_kaynagi,
        "yayinGunuKaynakAdi": DATE_SOURCES.get(r.yayin_gunu_kaynagi, r.yayin_gunu_kaynagi),
        "durum": r.durum, "durumAdi": STATUSES.get(r.durum, r.durum), "gun": day_of(r.yayin_gunu, today),
        "sahip": r.sahip, "olusturan": r.olusturan, "olusturma": C.iso(r.olusturma), "guncelleme": C.iso(r.guncelleme),
        "kapanis": C.iso(r.kapanis), "okuma": C.iso(r.okuma), "renk": oz.get("renk"), "sinyal": oz.get("sinyal"),
        "uyarilar": oz.get("uyarilar") or [], "kapak": oz.get("kapak"),
    }


# ------------------------------------------------------------------ açma


def create(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, st: dict[str, Any], *,
           book_name: Optional[str] = None, kapak: Optional[str] = None) -> str:
    """Onaylı M15 planından lansman paketi: planın takvimi lansmana bağlanır, lansman şablonu eklenir."""
    ensure(engine)
    plan = C.plan_full(engine, tenant, plan_id)
    if plan["kind"] != "yeni":
        raise C.MarketingError("Lansman yalnız yeni kitap planından açılır.", 409)
    if plan["durum"] != "onayli":
        raise C.MarketingError("Lansman yalnız onaylı plandan açılır; plan önce onaylanmalı.", 409)
    if not plan.get("yayinTarihi"):
        raise C.MarketingError("Planda yayın tarihi yok.", 409)
    if not plan.get("stokKodu"):
        raise C.MarketingError("Planda stok kodu yok.", 409)
    pub = plan["yayinTarihi"]
    p = date.fromisoformat(pub)
    with engine.begin() as c:
        dup = c.execute(sa.select(LAUNCHES.c.id).where(
            LAUNCHES.c.tenant_id == tenant,
            sa.or_(LAUNCHES.c.plan_id == plan_id,
                   sa.and_(LAUNCHES.c.stok_kodu == plan["stokKodu"], LAUNCHES.c.durum.in_(ACTIVE))))).first()
        if dup:
            raise C.MarketingError(f"Bu kitabın lansmanı zaten açık ({dup.id}).", 409)
        lid = next_id(c, tenant, C.today().year)
        t = C.now()
        name = book_name or plan["baslik"].split(" · ")[0]
        c.execute(LAUNCHES.insert().values(
            id=lid, tenant_id=tenant, plan_id=plan_id, stok_kodu=plan["stokKodu"], crm_kitap_id=plan.get("crmKitapId"),
            baslik=(name or plan["stokKodu"])[:400], yayin_gunu=pub,
            yayin_gunu_kaynagi=PLAN_TO_LAUNCH_SOURCE.get(plan.get("yayinTarihiKaynagi") or "", "kitap"),
            durum=phase(pub, C.today()), elle_kapandi=False, sahip=(plan.get("sahip") or user)[:120], olusturan=user,
            olusturma=t, guncelleme=t, ozet_json=C.dump({"kapak": kapak}) if kapak else None))
        c.execute(C.TASKS.update().where(C.TASKS.c.plan_id == plan_id, C.TASKS.c.launch_id.is_(None)).values(launch_id=lid))
        for g, is_, kanal, mat in st["tasks"]:
            c.execute(C.TASKS.insert().values(**{
                "id": _uid(), "plan_id": plan_id, "launch_id": lid, "tarih": (p + timedelta(days=g)).isoformat(),
                "gun_farki": g, "is": is_[:400], "kanal": kanal if kanal in C.CHANNELS else None, "sorumlu": None,
                "durum": "bekliyor", "kanit_url": None, "materyal_id": None,
                "materyal_tur": mat if mat in C.MATERIALS_KINDS else None, "kaynak": "lansman"}))
        C.event(c, plan_id, user, "lansman-acildi", None, {"lansman": lid, "yayin": pub})
    return lid


def plans_due(engine: sa.engine.Engine, tenant: str, today: date, open_days: int, back_days: int = 30) -> list[dict[str, Any]]:
    """Kendiliğinden açılacaklar: onaylı yeni kitap planı, yayın günü [bugün−back_days, bugün+open_days], lansmanı yok."""
    ensure(engine)
    lo, hi = (today - timedelta(days=back_days)).isoformat(), (today + timedelta(days=open_days)).isoformat()
    with engine.connect() as c:
        taken = set(c.execute(sa.select(LAUNCHES.c.plan_id).where(LAUNCHES.c.tenant_id == tenant)).scalars().all())
        stocks = set(c.execute(sa.select(LAUNCHES.c.stok_kodu).where(LAUNCHES.c.tenant_id == tenant,
                                                                      LAUNCHES.c.durum.in_(ACTIVE))).scalars().all())
    out = []
    for p in C.list_plans(engine, tenant, kind="yeni", durum="onayli"):
        if p["id"] in taken or not p.get("yayinTarihi") or not p.get("stokKodu") or p["stokKodu"] in stocks:
            continue
        if lo <= p["yayinTarihi"] <= hi:
            out.append(p)
    return out


# ------------------------------------------------------------------ okuma


def get(engine: sa.engine.Engine, tenant: str, lid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = _row(c, tenant, lid)
    return head(r)


def get_full(engine: sa.engine.Engine, tenant: str, lid: str) -> dict[str, Any]:
    """Lansman + kontrol listesi + planın onaylı materyalleri (gönderi günü telefonda metni göstermek için)."""
    ensure(engine)
    with engine.connect() as c:
        r = _row(c, tenant, lid)
        tasks = c.execute(launch_tasks_stmt(r.id, r.plan_id)).all()
        mats = c.execute(sa.select(C.MATERIALS).where(C.MATERIALS.c.plan_id == r.plan_id, C.MATERIALS.c.durum == "onayli")
                         .order_by(C.MATERIALS.c.tur)).all()
        plan = c.execute(launch_plan_stmt(r.plan_id)).first()
        reviews = c.execute(reviews_stmt(r.id)).all()
    out = head(r)
    out["tasks"] = [C._task(t) for t in tasks]
    out["materials"] = [{"id": m.id, "tur": m.tur, "turAdi": C.MATERIALS_KINDS.get(m.tur, (m.tur, None))[0], "metin": m.metin,
                         "surum": m.surum} for m in mats]
    out["plan"] = {"id": r.plan_id, "durum": plan.durum if plan else None, "durumAdi": C.STATUSES.get(plan.durum) if plan else None,
                   "baslik": plan.baslik if plan else None, "hedef": C.loads(plan.hedef_json, None) if plan else None}
    out["reviews"] = [review_dict(x) for x in reviews]
    out["ozet"] = C.loads(r.ozet_json, {})
    return out


def list_launches(engine: sa.engine.Engine, tenant: str, *, frm: Optional[str] = None, to: Optional[str] = None,
                  durum: str = "", sahip: str = "") -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(list_stmt(tenant, frm=frm, to=to, durum=durum, sahip=sahip)).all()
        counts = dict(c.execute(overdue_stmt([r.id for r in rows], C.today().isoformat())).all())
    today = C.today()
    return [{**head(r, today), "gecikenMadde": int(counts.get(r.id, 0))} for r in rows]


def today_tasks(engine: sa.engine.Engine, tenant: str, user: str, *, mine: bool) -> list[dict[str, Any]]:
    """Bugün ve geciken bekleyen maddeler, bütün açık lansmanlarda. `mine`: sorumlusu ben ya da sorumlusuz ve lansman
    sahibi benim."""
    ensure(engine)
    today = C.today().isoformat()
    with engine.connect() as c:
        rows = c.execute(today_stmt(tenant, today)).all()
    out = []
    u = (user or "").lower()
    for r in rows:
        owner = (r.sorumlu or r.lansman_sahip or "").lower()
        if mine and owner != u:
            continue
        out.append({**C._task(r), "lansman": r.launch_id, "lansmanBaslik": r.lansman_baslik, "yayinGunu": r.yayin_gunu,
                    "stokKodu": r.stok_kodu, "sorumluEtkin": r.sorumlu or r.lansman_sahip, "gecikti": r.tarih < today})
    return out


# ------------------------------------------------------------------ yazma


def update(engine: sa.engine.Engine, tenant: str, user: str, lid: str, body: dict[str, Any]) -> dict[str, Any]:
    """`sahip`; `yayinGunu` (elle); `yayinGunuKaynagi` (okunan adaylardan biri: uretim-depo, uretim-dagilim, kitap,
    proje); `durum` = kapandi (elle kapat) ya da `acik` (yeniden aç). Yayın günü değişince lansmanın bekleyen şablon
    işleri yeni güne göre kayar."""
    ensure(engine)
    with engine.begin() as c:
        r = _row(c, tenant, lid)
        vals: dict[str, Any] = {}
        old: dict[str, Any] = {}
        if "sahip" in body:
            vals["sahip"] = C.one_line(body.get("sahip"), 120)
        new_pub, new_src = None, None
        if body.get("yayinGunuKaynagi"):
            k = str(body["yayinGunuKaynagi"])
            cand = (C.loads(r.ozet_json, {}).get("adaylar") or {}).get(k)
            if k not in DATE_SOURCES or k == "elle" or not cand:
                raise C.MarketingError("Bu kaynakta okunmuş bir yayın günü yok.")
            new_pub, new_src = cand, k
        if "yayinGunu" in body:
            new_pub = C.day(body.get("yayinGunu"), "Yayın günü", allow_none=False)
            new_src = "elle"
        if new_pub and (new_pub != r.yayin_gunu or new_src != r.yayin_gunu_kaynagi):
            old.update(yayin_gunu=r.yayin_gunu, yayin_gunu_kaynagi=r.yayin_gunu_kaynagi)
            vals.update(yayin_gunu=new_pub, yayin_gunu_kaynagi=new_src)
        if "durum" in body:
            d = str(body.get("durum") or "")
            if d == "kapandi":
                vals.update(durum="kapandi", elle_kapandi=True, kapanis=C.now())
            elif d == "acik":
                vals.update(elle_kapandi=False, kapanis=None, durum=phase(vals.get("yayin_gunu") or r.yayin_gunu, C.today()))
            else:
                raise C.MarketingError("Durum kapandi ya da acik olmalı.")
        if not vals:
            raise C.MarketingError("Değiştirilecek alan yok.")
        if "yayin_gunu" in vals and "durum" not in vals and not r.elle_kapandi:
            vals["durum"] = phase(vals["yayin_gunu"], C.today())
        vals["guncelleme"] = C.now()
        c.execute(LAUNCHES.update().where(LAUNCHES.c.id == r.id).values(**vals))
        moved = 0
        if "yayin_gunu" in vals:
            p = date.fromisoformat(vals["yayin_gunu"])
            for t in c.execute(sa.select(C.TASKS).where(C.TASKS.c.launch_id == r.id, C.TASKS.c.plan_id == r.plan_id,
                                                        C.TASKS.c.durum == "bekliyor", C.TASKS.c.gun_farki.isnot(None),
                                                        C.TASKS.c.kaynak.in_(("sablon", "lansman")))).all():
                c.execute(C.TASKS.update().where(C.TASKS.c.id == t.id).values(tarih=(p + timedelta(days=t.gun_farki)).isoformat()))
                moved += 1
        C.event(c, r.plan_id, user, "lansman-duzenle", old or None,
                {**{k: v for k, v in vals.items() if k in ("sahip", "yayin_gunu", "yayin_gunu_kaynagi", "durum")},
                 "lansman": r.id, "tasinan": moved})
    return get_full(engine, tenant, lid)


def set_task(engine: sa.engine.Engine, tenant: str, user: str, lid: str, tid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Maddenin durumu, kanıt bağlantısı ya da sorumlusu. Plan onaylı olsa da madde işaretlenir (iş yapıldıkça)."""
    ensure(engine)
    with engine.begin() as c:
        r = _row(c, tenant, lid)
        t = c.execute(sa.select(C.TASKS).where(C.TASKS.c.id == str(tid)[:32], C.TASKS.c.launch_id == r.id,
                                               C.TASKS.c.plan_id == r.plan_id)).first()
        if not t:
            raise C.MarketingError("Madde bulunamadı.", 404)
        vals: dict[str, Any] = {}
        if "durum" in body:
            d = str(body.get("durum") or "")
            if d not in C.TASK_STATUSES:
                raise C.MarketingError("Durum bekliyor, yapildi ya da atlandi olmalı.")
            vals["durum"] = d
        if "kanitUrl" in body:
            url = C.one_line(body.get("kanitUrl"), 1000)
            if url and not url.lower().startswith(("http://", "https://")):
                raise C.MarketingError("Kanıt bağlantısı http:// ya da https:// ile başlamalı.")
            vals["kanit_url"] = url
        if "sorumlu" in body:
            vals["sorumlu"] = C.one_line(body.get("sorumlu"), 120)
        if not vals:
            raise C.MarketingError("Değiştirilecek alan yok.")
        c.execute(C.TASKS.update().where(C.TASKS.c.id == t.id).values(**vals))
        C.event(c, r.plan_id, user, "lansman-madde", {"id": t.id, "durum": t.durum, "kanit": t.kanit_url},
                {"id": t.id, "lansman": r.id, **{k: v for k, v in vals.items()}})
        return C._task(c.execute(sa.select(C.TASKS).where(C.TASKS.c.id == t.id)).one())


def add_task(engine: sa.engine.Engine, tenant: str, user: str, lid: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    is_ = C.one_line(body.get("is"), 400)
    if not is_:
        raise C.MarketingError("Madde açıklaması gerekli.")
    tarih = C.day(body.get("tarih"), "Tarih", allow_none=False)
    kanal = str(body.get("kanal") or "") or None
    if kanal and kanal not in C.CHANNELS:
        raise C.MarketingError("Kanal tanınmıyor.")
    with engine.begin() as c:
        r = _row(c, tenant, lid)
        tid = _uid()
        c.execute(C.TASKS.insert().values(**{
            "id": tid, "plan_id": r.plan_id, "launch_id": r.id, "tarih": tarih,
            "gun_farki": (date.fromisoformat(tarih) - date.fromisoformat(r.yayin_gunu)).days, "is": is_, "kanal": kanal,
            "sorumlu": C.one_line(body.get("sorumlu"), 120), "durum": "bekliyor", "kanit_url": None, "materyal_id": None,
            "materyal_tur": None, "kaynak": "kullanici"}))
        C.event(c, r.plan_id, user, "lansman-madde-ekle", None, {"id": tid, "lansman": r.id, "is": is_, "tarih": tarih})
        return C._task(c.execute(sa.select(C.TASKS).where(C.TASKS.c.id == tid)).one())


# ------------------------------------------------------------------ günlük seri


def upsert_days(engine: sa.engine.Engine, lid: str, rows: dict[str, dict[str, Any]]) -> int:
    """Gün satırlarını yazar; verilen alanlar değişir, verilmeyenler olduğu gibi kalır (saatlik sipariş okuması günlük
    Logo alanlarını silmez)."""
    if not rows:
        return 0
    t = C.now()
    with engine.begin() as c:
        have = set(c.execute(sa.select(DAILY.c.gun).where(DAILY.c.launch_id == lid, DAILY.c.gun.in_(list(rows)))).scalars().all())
        for g, vals in rows.items():
            v = {k: (None if x is None else (round(float(x), 4) if not isinstance(x, str) else x)) for k, x in vals.items()}
            if g in have:
                c.execute(DAILY.update().where(DAILY.c.launch_id == lid, DAILY.c.gun == g).values(**v, okuma_zamani=t))
            else:
                c.execute(DAILY.insert().values(launch_id=lid, gun=g, **v, okuma_zamani=t))
    return len(rows)


def days_of(engine: sa.engine.Engine, lid: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(days_stmt(lid)).all()
    return [{k: (C.iso(v) if isinstance(v, datetime) else v) for k, v in dict(r._mapping).items()} for r in rows]


def set_summary(engine: sa.engine.Engine, lid: str, ozet: dict[str, Any], *, durum: Optional[str] = None) -> None:
    vals: dict[str, Any] = {"ozet_json": C.dump(ozet), "okuma": C.now()}
    if durum:
        vals["durum"] = durum
        if durum == "kapandi":
            vals["kapanis"] = C.now()
    with engine.begin() as c:
        c.execute(LAUNCHES.update().where(LAUNCHES.c.id == lid).values(**vals))


def _sum(days: Iterable[dict[str, Any]], field: str) -> Optional[float]:
    vals = [d.get(field) for d in days if d.get(field) is not None]
    return round(sum(vals), 2) if vals else None


def last_snapshot(days: list[dict[str, Any]], field: str) -> tuple[Optional[float], Optional[str]]:
    for d in reversed(days):
        if d.get(field) is not None:
            return d[field], d["gun"]
    return None, None


def depot_choice(logo: Optional[float], logo_end: Optional[str], crm: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Depo stoku: CRM'deki en son sipariş anındaki stok Logo verisinin bittiği günden yeniyse o (Logo kopyası donmuşken
    tek güncel sinyal), değilse Logo depo görünümü."""
    crm_day = (crm or {}).get("zaman", "")[:10] if crm else None
    if crm and crm.get("stok") is not None and (logo is None or not logo_end or (crm_day and crm_day > logo_end)):
        return {"deger": crm["stok"], "kaynak": "crm", "kaynakAdi": "CRM: en son siparişteki depo stoku", "tarih": crm_day}
    if logo is not None:
        return {"deger": logo, "kaynak": "logo", "kaynakAdi": "Logo depo stoku", "tarih": logo_end}
    return {"deger": None, "kaynak": None, "kaynakAdi": None, "tarih": None}


def evaluate(pub: str, days: list[dict[str, Any]], tasks: list[dict[str, Any]], ozet: dict[str, Any], st: dict[str, Any],
             today: date) -> dict[str, Any]:
    """Sinyaller ve durum rengi (kural; model yok).

    - Stok–talep: açık sipariş > depo stoku (ya da yayından sonra hiç dağılım siparişi yok) → kırmızı.
    - Hedef payı: yayından bu yana birikmiş hedef payına oran; esas Logo faturası (veri sonuna kadar), Logo verisi
      yayın gününden önce bittiyse CRM siparişi (etiketiyle). Eşik altı (varsayılan %80, M46 kuralı) kırmızı; eşik ile
      %100 arası sarı.
    - Geciken madde (bugünden önceki bekleyen) → sarı."""
    p = date.fromisoformat(pub)
    g = (today - p).days
    after = [d for d in days if d["gun"] >= pub and d["gun"] <= today.isoformat()]
    logo_end = next((d.get("veri_sonu_logo") for d in reversed(days) if d.get("veri_sonu_logo")), None)
    hedef_all = _sum(after, "hedef_payi_adet")
    siparis = _sum(after, "siparis_adet")
    covered = [d for d in after if logo_end and d["gun"] <= logo_end]
    fatura = _sum(covered, "fatura_net_adet")
    hedef_cov = _sum(covered, "hedef_payi_adet")
    r_fat = (fatura / hedef_cov) if (fatura is not None and hedef_cov) else None
    r_sip = (siparis / hedef_all) if (siparis is not None and hedef_all) else None
    basis = "fatura" if covered else "siparis"
    ratio = r_fat if basis == "fatura" else r_sip
    bekleyen, bek_gun = last_snapshot(days, "bekleyen_adet")
    depo_logo, depo_logo_gun = last_snapshot(days, "depo_stok")
    bekleyen_urun, _ = last_snapshot(days, "bekleyen_urun_adet")
    # Seçilen değerin yanında Logo görünümünün son okuması da döner (CRM sinyali seçildiğinde karşılaştırma için).
    depo = {**depot_choice(depo_logo, logo_end, ozet.get("crmStok")), "logo": depo_logo, "logoGun": depo_logo_gun}
    dist = (ozet.get("dagilim") or {}).get("adet")
    conflict = bool(bekleyen is not None and depo["deger"] is not None and bekleyen > depo["deger"])
    no_dist = g >= 0 and dist is not None and dist <= 0
    overdue = [t for t in tasks if t.get("durum") == "bekliyor" and t.get("tarih") and t["tarih"] < today.isoformat()]
    below = g >= 1 and ratio is not None and ratio < st["alertRatio"]
    warn: list[str] = []
    if conflict:
        warn.append(f"Açık sipariş ({bekleyen:,.0f}) depo stokunun ({depo['deger']:,.0f}) üstünde.".replace(",", "."))
    if no_dist:
        warn.append("Yayın günü geçti, dağılım siparişi görünmüyor.")
    if below:
        warn.append(("Faturalı satış" if basis == "fatura" else "Sipariş") + f" hedef payının %{ratio * 100:.0f}'inde "
                    f"(eşik %{st['alertRatio'] * 100:.0f}).")
    if overdue:
        warn.append(f"{len(overdue)} madde gecikti.")
    if logo_end and g >= 0 and logo_end < today.isoformat():
        warn.append(f"Faturalı satış verisi {logo_end} tarihinde bitiyor; sonrası yalnız sipariş sinyali.")
    warn += list(ozet.get("tarihUyarilari") or [])
    renk = "kirmizi" if (conflict or no_dist or below) else ("sari" if (overdue or (ratio is not None and g >= 1 and ratio < 1)) else "yesil")
    return {
        "renk": renk, "uyarilar": warn,
        "sinyal": {"gun": g, "siparis": siparis, "fatura": fatura, "hedef": hedef_all, "hedefKapsanan": hedef_cov,
                   "oranFatura": r_fat, "oranSiparis": r_sip, "oranEsas": basis, "oran": ratio, "bekleyen": bekleyen,
                   "bekleyenGun": bek_gun, "bekleyenUrun": bekleyen_urun, "depo": depo, "dagilim": ozet.get("dagilim"), "stokCatismasi": conflict,
                   "dagilimYok": no_dist, "hedefAltinda": below, "gecikenMadde": len(overdue), "veriSonuLogo": logo_end},
    }


def tracking(engine: sa.engine.Engine, tenant: str, lid: str, gun: int, show_money: bool) -> dict[str, Any]:
    """İzleme sekmesi: D−ön gün … D+gün−1 gün gün seri (birikimli), emsal ortalaması, hedef payı, SQL'ler."""
    full = get_full(engine, tenant, lid)
    pub = full["yayinGunu"]
    p = date.fromisoformat(pub)
    rows = {d["gun"]: d for d in days_of(engine, lid)}
    oz = full["ozet"]
    pre = int(oz.get("onGun") or 0)
    today = C.today()
    emsal_curve = (oz.get("emsal") or {}).get("egri") or []
    out_rows = []
    acc = {"siparis": 0.0, "fatura": 0.0, "hedef": 0.0, "ciro": 0.0, "hedefCiro": 0.0}
    logo_end = None
    for i in range(-pre, gun):
        dd = p + timedelta(days=i)
        g = dd.isoformat()
        d = rows.get(g, {})
        logo_end = d.get("veri_sonu_logo") or logo_end
        future = dd > today
        if i >= 0 and not future:
            acc["siparis"] += d.get("siparis_adet") or 0.0
            if d.get("fatura_net_adet") is not None:
                acc["fatura"] += d["fatura_net_adet"]
                acc["ciro"] += d.get("fatura_net_ciro") or 0.0
        if i >= 0 and d.get("hedef_payi_adet") is not None:
            acc["hedef"] += d["hedef_payi_adet"]
            acc["hedefCiro"] += d.get("hedef_payi_ciro") or 0.0
        out_rows.append({
            "gun": g, "d": i, "gelecek": future,
            "siparis": d.get("siparis_adet"), "dagilim": d.get("dagilim_adet"), "sevk": d.get("sevk_adet"),
            "fatura": d.get("fatura_net_adet"), "ciro": d.get("fatura_net_ciro") if show_money else None,
            "hedef": d.get("hedef_payi_adet") if i >= 0 else None,
            "bekleyen": d.get("bekleyen_adet"), "bekleyenUrun": d.get("bekleyen_urun_adet"), "depo": d.get("depo_stok"),
            "siparisKum": round(acc["siparis"], 2) if i >= 0 and not future else None,
            "faturaKum": round(acc["fatura"], 2) if i >= 0 and d.get("fatura_net_adet") is not None else None,
            "hedefKum": round(acc["hedef"], 2) if i >= 0 and d.get("hedef_payi_adet") is not None else None,
            "emsalKum": round(sum(emsal_curve[: i + 1]), 2) if i >= 0 and i < len(emsal_curve) else None,
        })
    em = oz.get("emsal") or {}
    return {
        "lansman": {k: full[k] for k in ("id", "baslik", "stokKodu", "yayinGunu", "durum", "durumAdi", "gun", "renk")},
        "gun": gun, "seri": out_rows, "sinyal": full.get("sinyal"), "uyarilar": full.get("uyarilar"),
        "toplam": {"siparis": round(acc["siparis"], 2), "fatura": round(acc["fatura"], 2), "hedef": round(acc["hedef"], 2),
                   "ciro": round(acc["ciro"], 2) if show_money else None,
                   "hedefCiro": round(acc["hedefCiro"], 2) if show_money else None,
                   "emsal7": em.get("ort7"), "emsal30": em.get("ort30")},
        "dagilim": oz.get("dagilim"), "depo": (full.get("sinyal") or {}).get("depo"),
        "emsal": {"items": em.get("items") or [], "ort7": em.get("ort7"), "ort30": em.get("ort30"), "not": em.get("not")},
        "hedef": oz.get("hedef"), "veriSonu": {"logo": logo_end or oz.get("veriSonuLogo"), "crm": full.get("okuma")},
        "sql": oz.get("sql") or {}, "okumaHatalari": oz.get("hatalar") or [],
    }


# ------------------------------------------------------------------ etkinlik ve medya


def _event_dict(r: Any) -> dict[str, Any]:
    return {"id": r.id, "kaynak": r.kaynak, "crmId": r.kaynak[4:] if r.kaynak.startswith("crm:") else None, "ad": r.ad,
            "tur": r.tur, "tarih": r.tarih, "yer": r.yer, "katilimci": r.katilimci, "satilan": r.satilan, "gelir": r.gelir,
            "gider": r.gider, "not": r.not_, "giren": r.giren, "zaman": C.iso(r.zaman)}


def portal_events(engine: sa.engine.Engine, lid: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(events_stmt(lid)).all()
    return [_event_dict(r) for r in rows]


def merge_events(crm_rows: list[dict[str, Any]], portal: list[dict[str, Any]]) -> dict[str, Any]:
    """CRM etkinlikleri + portalda girilen sonuç (katılımcı, satılan…) + elle eklenenler. Toplamlar tamamlanan
    etkinliklerden (CRM durumu «Tamamlandı» ya da elle kayıt)."""
    from semantic_bridge.marketing.launch_sources import EVENT_CANCELLED, EVENT_DONE

    over = {e["crmId"]: e for e in portal if e.get("crmId")}
    items = []
    for r in crm_rows:
        o = over.get(r["crmId"])
        item = {**r, "kaynak": "crm", "id": None, "portal": None}
        if o:
            item["portal"] = {k: o[k] for k in ("id", "katilimci", "satilan", "gelir", "gider", "not", "giren", "zaman")}
            for k in ("katilimci", "satilan", "gelir", "gider"):
                if o.get(k) is not None:
                    item[k] = o[k]
        items.append(item)
    for e in portal:
        if not e.get("crmId"):
            items.append({**e, "kaynak": "elle", "durum": None, "durumAdi": "Portalda girildi", "portal": None})
    items.sort(key=lambda x: (x.get("tarih") or "", x.get("ad") or ""))
    done = [x for x in items if x["kaynak"] == "elle" or x.get("durum") == EVENT_DONE]
    tot = {"etkinlik": len([x for x in items if x.get("durum") != EVENT_CANCELLED]), "tamamlanan": len(done),
           "katilimci": round(sum(x.get("katilimci") or 0 for x in done), 2), "satilan": round(sum(x.get("satilan") or 0 for x in done), 2),
           "gelir": round(sum(x.get("gelir") or 0 for x in done), 2), "gider": round(sum(x.get("gider") or 0 for x in done), 2)}
    return {"items": items, "toplam": tot}


def save_event(engine: sa.engine.Engine, tenant: str, user: str, lid: str, body: dict[str, Any], eid: Optional[str] = None) -> dict[str, Any]:
    """Elle etkinlik ya da CRM etkinliğinin portal sonucu (`crmId`). Katılımcı kişisel verisi alınmaz, yalnız sayı."""
    ensure(engine)
    crm_id = C.one_line(body.get("crmId"), 40)
    if crm_id:
        from semantic_bridge.marketing.sources import guid
        crm_id = guid(crm_id).lower()
    # Yalnız gönderilen alanlar değişir (bütçe görme yetkisi olmayan kişi gelir/gideri göndermez, silinmez).
    labels = {"katilimci": "Katılımcı", "satilan": "Satılan kitap", "gelir": "Gelir", "gider": "Gider"}
    vals: dict[str, Any] = {k: C.number(body.get(k), lab, allow_none=True) for k, lab in labels.items() if k in body}
    if "not" in body:
        vals["not_"] = C.text(body.get("not"), 4000)
    if not crm_id:
        ad = C.one_line(body.get("ad"), 400)
        if not ad:
            raise C.MarketingError("Etkinlik adı gerekli.")
        vals.update(ad=ad, tur=C.one_line(body.get("tur"), 120), tarih=C.day(body.get("tarih"), "Tarih", allow_none=False),
                    yer=C.one_line(body.get("yer"), 400))
    with engine.begin() as c:
        r = _row(c, tenant, lid)
        cond = None
        if eid:
            cond = sa.and_(EVENTS.c.id == str(eid)[:32], EVENTS.c.launch_id == r.id)
        elif crm_id:
            cond = sa.and_(EVENTS.c.launch_id == r.id, EVENTS.c.kaynak == f"crm:{crm_id}")
        prev = c.execute(sa.select(EVENTS).where(cond)).first() if cond is not None else None
        if eid and not prev:
            raise C.MarketingError("Kayıt bulunamadı.", 404)
        if prev:
            c.execute(EVENTS.update().where(EVENTS.c.id == prev.id).values(**vals, giren=user, zaman=C.now()))
            out_id = prev.id
        else:
            out_id = _uid()
            c.execute(EVENTS.insert().values(id=out_id, launch_id=r.id, kaynak=f"crm:{crm_id}" if crm_id else "elle", giren=user,
                                             zaman=C.now(), **vals))
        C.event(c, r.plan_id, user, "lansman-etkinlik", None, {"lansman": r.id, "id": out_id, "crm": crm_id})
        return _event_dict(c.execute(sa.select(EVENTS).where(EVENTS.c.id == out_id)).one())


def delete_entry(engine: sa.engine.Engine, tenant: str, user: str, lid: str, table: str, eid: str) -> dict[str, Any]:
    t = EVENTS if table == "events" else MEDIA
    with engine.begin() as c:
        r = _row(c, tenant, lid)
        prev = c.execute(sa.select(t).where(t.c.id == str(eid)[:32], t.c.launch_id == r.id)).first()
        if not prev:
            raise C.MarketingError("Kayıt bulunamadı.", 404)
        c.execute(t.delete().where(t.c.id == prev.id))
        C.event(c, r.plan_id, user, f"lansman-{'etkinlik' if table == 'events' else 'medya'}-sil", {"id": prev.id}, {"lansman": r.id})
    return {"ok": True}


def _media_dict(r: Any) -> dict[str, Any]:
    return {"id": r.id, "kaynak": r.kaynak, "mecra": r.mecra, "baslik": r.baslik, "url": r.url, "tarih": r.tarih, "ton": r.ton,
            "tonAdi": TONES.get(r.ton or "", None), "giren": r.giren, "zaman": C.iso(r.zaman)}


def portal_media(engine: sa.engine.Engine, lid: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(media_stmt(lid)).all()
    return [_media_dict(r) for r in rows]


def save_media(engine: sa.engine.Engine, tenant: str, user: str, lid: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    baslik = C.one_line(body.get("baslik"), 500)
    if not baslik:
        raise C.MarketingError("Başlık gerekli.")
    url = C.one_line(body.get("url"), 1000)
    if url and not url.lower().startswith(("http://", "https://")):
        raise C.MarketingError("Bağlantı http:// ya da https:// ile başlamalı.")
    ton = str(body.get("ton") or "") or None
    if ton and ton not in TONES:
        raise C.MarketingError("Ton olumlu, olumsuz ya da notr olmalı.")
    with engine.begin() as c:
        r = _row(c, tenant, lid)
        mid = _uid()
        c.execute(MEDIA.insert().values(id=mid, launch_id=r.id, kaynak="elle", mecra=C.one_line(body.get("mecra"), 200), baslik=baslik,
                                        url=url, tarih=C.day(body.get("tarih"), "Tarih"), ton=ton, giren=user, zaman=C.now()))
        C.event(c, r.plan_id, user, "lansman-medya", None, {"lansman": r.id, "id": mid})
        return _media_dict(c.execute(sa.select(MEDIA).where(MEDIA.c.id == mid)).one())


def crm_todo(events: dict[str, Any], media: list[dict[str, Any]], launch: dict[str, Any]) -> list[dict[str, Any]]:
    """CRM'e yazma yok: portalda girilen etkinlik sonuçları ve elle kayıtlar CRM'e elle işlenecekler listesidir."""
    out = []
    for e in events["items"]:
        if e["kaynak"] == "elle":
            out.append({"nereye": "CRM › Etkinlik (yeni kayıt)", "ne": e.get("ad"), "tarih": e.get("tarih"),
                        "alanlar": {"İlgili kitap": launch["baslik"], "Katılımcı sayısı": e.get("katilimci"),
                                    "Satılan kitap adedi": e.get("satilan"), "Etkinlik geliri": e.get("gelir"),
                                    "Toplam etkinlik gideri": e.get("gider")}})
        elif e.get("portal"):
            po = e["portal"]
            diff = {lab: po.get(k) for k, lab in (("katilimci", "Katılımcı sayısı"), ("satilan", "Satılan kitap adedi"),
                                                  ("gelir", "Etkinlik geliri"), ("gider", "Toplam etkinlik gideri")) if po.get(k) is not None}
            if diff:
                out.append({"nereye": "CRM › Etkinlik (mevcut kayıt)", "ne": e.get("ad"), "tarih": e.get("tarih"), "alanlar": diff,
                            "crmId": e.get("crmId")})
    for m in media:
        if m["kaynak"] == "elle":
            out.append({"nereye": "CRM › Haber / medya yansıması", "ne": m["baslik"], "tarih": m.get("tarih"),
                        "alanlar": {"Mecra": m.get("mecra"), "Bağlantı": m.get("url"), "Ton": m.get("tonAdi")}})
    return out


# ------------------------------------------------------------------ değerlendirme


def review_dict(r: Any) -> dict[str, Any]:
    return {"id": r.id, "gun": r.gun, "rakam": C.loads(r.rakam_json, {}), "ozet": r.ozet, "oneriler": C.loads(r.oneriler_json, []),
            "dogrulama": C.loads(r.dogrulama_json, None), "durum": r.durum, "karar": r.karar,
            "kararAdi": DECISIONS.get(r.karar or "", None), "gerekce": r.gerekce, "kararVeren": r.karar_veren,
            "kararZamani": C.iso(r.karar_zamani), "hazirlayan": r.hazirlayan, "hazirlama": C.iso(r.hazirlama)}


def review_get(engine: sa.engine.Engine, lid: str, gun: int) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(REVIEWS).where(REVIEWS.c.launch_id == lid, REVIEWS.c.gun == int(gun))).first()
    return review_dict(r) if r else None


def review_put_numbers(engine: sa.engine.Engine, lid: str, gun: int, rakam: dict[str, Any], user: str) -> dict[str, Any]:
    """Rakam tablosu yazılır; yeniden hesaplanınca eski özet silinir (özet rakama bağlıdır). Karar verilmişse rakam
    değişmez: karar hangi rakama verildiyse o kalır."""
    if int(gun) not in REVIEW_DAYS:
        raise C.MarketingError("Değerlendirme günü 7 ya da 30 olmalı.")
    with engine.begin() as c:
        prev = c.execute(sa.select(REVIEWS).where(REVIEWS.c.launch_id == lid, REVIEWS.c.gun == int(gun))).first()
        if prev and prev.durum == "karar":
            raise C.MarketingError("Bu değerlendirmede karar verilmiş; rakamlar karar anındaki haliyle kalır.", 409)
        if prev:
            c.execute(REVIEWS.update().where(REVIEWS.c.id == prev.id).values(rakam_json=C.dump(rakam), ozet=None, oneriler_json=None,
                                                                             dogrulama_json=None, durum="rakam", hazirlayan=user,
                                                                             hazirlama=C.now()))
            rid = prev.id
        else:
            rid = _uid()
            c.execute(REVIEWS.insert().values(id=rid, launch_id=lid, gun=int(gun), rakam_json=C.dump(rakam), durum="rakam",
                                              hazirlayan=user, hazirlama=C.now()))
        return review_dict(c.execute(sa.select(REVIEWS).where(REVIEWS.c.id == rid)).one())


def review_put_text(engine: sa.engine.Engine, lid: str, gun: int, ozet: Optional[str], oneriler: list[str], dogrulama: Any) -> None:
    with engine.begin() as c:
        c.execute(REVIEWS.update().where(REVIEWS.c.launch_id == lid, REVIEWS.c.gun == int(gun), REVIEWS.c.durum != "karar").values(
            ozet=ozet, oneriler_json=C.dump(oneriler), dogrulama_json=C.dump(dogrulama), durum="hazir"))


def review_decide(engine: sa.engine.Engine, tenant: str, user: str, lid: str, gun: int, karar: str, gerekce: Any) -> dict[str, Any]:
    if karar not in DECISIONS:
        raise C.MarketingError("Karar artir, koru, kes ya da diger olmalı.")
    why = C.text(gerekce, 4000)
    if not why:
        raise C.MarketingError("Kararın gerekçesini yazın.")
    with engine.begin() as c:
        r = _row(c, tenant, lid)
        rv = c.execute(sa.select(REVIEWS).where(REVIEWS.c.launch_id == r.id, REVIEWS.c.gun == int(gun))).first()
        if not rv:
            raise C.MarketingError("Önce değerlendirme raporu hazırlanmalı.", 409)
        c.execute(REVIEWS.update().where(REVIEWS.c.id == rv.id).values(karar=karar, gerekce=why, karar_veren=user,
                                                                       karar_zamani=C.now(), durum="karar"))
        # Bütçe revizyonu kararı plan geçmişine (M15 planı; M46 bilgisi için).
        C.event(c, r.plan_id, user, "lansman-karar", {"karar": rv.karar} if rv.karar else None,
                {"lansman": r.id, "gun": int(gun), "karar": karar, "kararAdi": DECISIONS[karar], "gerekce": why})
        return review_dict(c.execute(sa.select(REVIEWS).where(REVIEWS.c.id == rv.id)).one())
