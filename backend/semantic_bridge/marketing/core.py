"""Pazarlama çekirdeği (M15–M18 ortak): plan, bütçe satırı, takvim, materyal, geçmiş, iş kuyruğu.

Bir **plan** tek bir pazarlama işinin kaydıdır: `kind='yeni'` yeni kitap planı (M15), `backlist` (M17), `aylik`
ay planı (M18, `donem='YYYY-MM'`). Her tabloda `tenant_id` ya da plana bağ vardır; tablolar ilk kullanımda kurulur
(`budget.py` gibi SQLAlchemy Core).

**Durum makinesi:** `taslak` → (gönder) `onayda` → (onay) `onayli` | (geri gönder, gerekçe zorunlu) `geri` →
(düzelt, yeniden gönder) `onayda`. `onayli` plan değiştirilmez; «Revize et» yeni sürümü (`surum+1`, `onceki_id`)
taslak olarak açar, o onaylanınca eskisi `arsiv`e geçer. Gönderen onaylayamaz (iki göz). Bütçe toplamı yönetim
ayarındaki eşiği (`MARKETING_UPPER_APPROVAL_THRESHOLD`) aşıyorsa pazarlama onayına ek olarak üst onay gerekir; iki
onay iki ayrı kişiden gelir, ikisi de gönderen olamaz. Eşik girilmemişse ikinci onay istenmez (sayı uydurulmaz).

**Materyal:** `taslak` → (editoryal onay) `editoryal-onayli` → (pazarlama onayı) `onayli`. Metin değişince sürüm
artar ve onay düşer. Onaylı materyaller «yayına hazır paket»tir; dışarıya hiçbir şey gönderilmez (kullanıcı kararı:
ilk sürümde otomatik dış gönderim yok).

Her plan değişikliği `semantic_mkt_events`e (plan geçmişi) ve uç katmanında `semantic_audit`e yazılır.
CRM'e, Logo'ya, T-soft'a yazılmaz; CRM'e işlenmesi gerekenler ayrı liste olarak verilir (`plans.crm_todo`).
"""
from __future__ import annotations

import json
import math
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

PLANS = sa.Table(
    "semantic_mkt_plans", _md,
    sa.Column("id", sa.String(24), primary_key=True),                 # MP-<yıl>-<sıra>
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kind", sa.String(12), nullable=False),                  # yeni | backlist | aylik
    sa.Column("stok_kodu", sa.String(60), index=True),
    sa.Column("crm_kitap_id", sa.String(40)),
    sa.Column("crm_proje_id", sa.String(40)),
    sa.Column("baslik", sa.String(400), nullable=False),
    sa.Column("durum", sa.String(12), nullable=False),                 # taslak | onayda | onayli | geri | arsiv
    sa.Column("surum", sa.Integer, nullable=False),
    sa.Column("onceki_id", sa.String(24)),
    sa.Column("sahip", sa.String(120)),                                # AD hesabı
    sa.Column("yayin_tarihi", sa.String(10)),
    sa.Column("yayin_tarihi_kaynagi", sa.String(16)),                  # crm-kitap | crm-proje | uretim | elle
    sa.Column("hedef_json", sa.Text),                                  # M46 plan.id/version, hedef adet/ciro/marj, aylık
    sa.Column("butce_cerceve", sa.Float),                              # plan için önerilen/elle girilen çerçeve
    sa.Column("butce_cerceve_json", sa.Text),                          # çerçevenin kaynağı ve gerekçesi
    sa.Column("butce_toplam", sa.Float, nullable=False, default=0.0),
    sa.Column("donem", sa.String(7)),                                  # M18: YYYY-MM
    sa.Column("zeki_json", sa.Text),                                   # Zeki AI önerisinin gerekçesi, emsal kontrolü
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("gonderme", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("ust_onaylayan", sa.String(120)),
    sa.Column("ust_onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("gerekce", sa.Text),                                     # geri gönderme / revizyon gerekçesi
    sa.Index("ix_semantic_mkt_plans_kind", "tenant_id", "kind", "durum"),
)
LINES = sa.Table(
    "semantic_mkt_plan_lines", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("plan_id", sa.String(24), nullable=False, index=True),
    sa.Column("sira", sa.Integer, nullable=False, default=0),
    sa.Column("kanal", sa.String(24), nullable=False),
    sa.Column("alt_kanal", sa.String(200)),
    sa.Column("aciklama", sa.Text),
    sa.Column("tutar", sa.Float, nullable=False, default=0.0),
    sa.Column("baslangic", sa.String(10)),
    sa.Column("bitis", sa.String(10)),
    sa.Column("kpi_json", sa.Text),
    sa.Column("kaynak", sa.String(12), nullable=False),                # zeki | kullanici | crm
    sa.Column("gerekce", sa.Text),
    sa.Column("elle_duzeltildi", sa.Boolean, nullable=False, default=False),
)
TASKS = sa.Table(
    "semantic_mkt_tasks", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("plan_id", sa.String(24), nullable=False, index=True),
    sa.Column("launch_id", sa.String(24)),                             # M16 lansman bağı (ileride)
    sa.Column("tarih", sa.String(10)),
    sa.Column("gun_farki", sa.Integer),                                # yayın gününe göre (D-n / D+n)
    sa.Column("is", sa.String(400), nullable=False),
    sa.Column("kanal", sa.String(24)),
    sa.Column("sorumlu", sa.String(120)),
    sa.Column("durum", sa.String(10), nullable=False),                 # bekliyor | yapildi | atlandi
    sa.Column("kanit_url", sa.String(1000)),
    sa.Column("materyal_id", sa.String(32)),
    sa.Column("materyal_tur", sa.String(24)),
    sa.Column("kaynak", sa.String(16)),                                # sablon | ozel-gun | kullanici
)
MATERIALS = sa.Table(
    "semantic_mkt_materials", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("plan_id", sa.String(24), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("tur", sa.String(24), nullable=False),
    sa.Column("metin", sa.Text, nullable=False),
    sa.Column("kaynak", sa.String(80), nullable=False),                # crm:<alan> | studio:<iş> | zeki | kullanici
    sa.Column("durum", sa.String(20), nullable=False),                 # taslak | editoryal-onayli | onayli
    sa.Column("editoryal_onaylayan", sa.String(120)),
    sa.Column("editoryal_onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("surum", sa.Integer, nullable=False, default=1),
    sa.Column("dogrulama_json", sa.Text),                              # alıntı/rakam/iddia denetimi
    sa.Column("olusturan", sa.String(120)),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
)
CARDS = sa.Table(
    "semantic_mkt_book_cards", _md,
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("veri_json", sa.Text, nullable=False),
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
    sa.Column("veri_sonu", sa.String(10)),
)
EVENTS = sa.Table(
    "semantic_mkt_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("plan_id", sa.String(24), nullable=False, index=True),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
    sa.Column("kim", sa.String(120), nullable=False),
    sa.Column("ne", sa.String(40), nullable=False),
    sa.Column("eski_json", sa.Text),
    sa.Column("yeni_json", sa.Text),
)
JOBS = sa.Table(
    "semantic_mkt_jobs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("plan_id", sa.String(24), nullable=False, index=True),
    sa.Column("tur", sa.String(24), nullable=False),                   # suggest | material
    sa.Column("hedef_json", sa.Text),
    sa.Column("durum", sa.String(12), nullable=False),                 # bekliyor | calisiyor | bitti | hata
    sa.Column("adim", sa.String(200)),
    sa.Column("hata", sa.Text),
    sa.Column("sonuc_json", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("bitis", sa.DateTime(timezone=True)),
)
META = sa.Table(
    "semantic_mkt_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

KINDS = {"yeni": "Yeni kitap", "backlist": "Backlist", "aylik": "Aylık plan"}
STATUSES = {"taslak": "Taslak", "onayda": "Onay bekliyor", "onayli": "Onaylı", "geri": "Geri gönderildi", "arsiv": "Arşiv"}
EDITABLE = ("taslak", "geri")
#: CRM «Pazarlama Tipi» kümesi (`new_pazarlamamodulu.new_pazarlamatipi`) + etkinlik/influencer + diğer.
CHANNELS = {
    "basin": "Basın", "medya": "Medya", "promosyon": "Promosyon", "sosyal-medya": "Sosyal medya",
    "dijital": "Dijital pazarlama", "satis-kampanyasi": "Satış kampanyası", "etkinlik": "Etkinlik",
    "influencer": "Influencer", "diger": "Diğer",
}
LINE_SOURCES = ("zeki", "kullanici", "crm")
TASK_STATUSES = {"bekliyor": "Bekliyor", "yapildi": "Yapıldı", "atlandi": "Atlandı"}
DATE_SOURCES = {"crm-kitap": "CRM kitap kartı (ilk baskı tarihi)", "crm-proje": "CRM proje kartı (yayın tarihi)",
                "uretim": "CRM üretim kartı (dağılım / depo girişi)", "elle": "Elle girildi"}
#: Materyal türü → (ad, CRM kitap kartındaki karşılığı; yoksa None).
MATERIALS_KINDS: dict[str, tuple[str, Optional[str]]] = {
    "foy": ("Tanıtım föyü", "new_TantmFyMetni"),
    "arka-kapak": ("Arka kapak metni", "new_ozet"),
    "basin-bulteni": ("Basın bülteni", "new_BasnBlteni"),
    "sosyal": ("Sosyal medya metni", "new_sosyalmedyametni"),
    "e-bulten-konu": ("E-bülten konu satırı", None),
    "video-senaryo": ("Video senaryosu (30–60 sn)", None),
    "kapak-brief": ("Kapak ve görsel brief'i", None),
    "influencer-brief": ("Influencer brief'i", None),
}
MATERIAL_STATUSES = {"taslak": "Taslak", "editoryal-onayli": "Editoryal onaylı", "onayli": "Onaylı"}

_ready: set[int] = set()
_lock = threading.Lock()


class MarketingError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ yardımcılar


def now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def loads(v: Optional[str], default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def text(v: Any, limit: int) -> Optional[str]:
    s = str(v or "").strip()
    return s[:limit] or None


def one_line(v: Any, limit: int) -> Optional[str]:
    s = " ".join(str(v or "").split())
    return s[:limit] or None


def number(v: Any, label: str, *, allow_none: bool = False, minimum: Optional[float] = 0.0) -> Optional[float]:
    if v is None or v == "":
        if allow_none:
            return None
        raise MarketingError(f"{label} boş olamaz.")
    try:
        n = float(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) and "," in v else float(v)
    except (TypeError, ValueError):
        raise MarketingError(f"{label} sayı olmalı.") from None
    if math.isnan(n) or math.isinf(n):
        raise MarketingError(f"{label} sayı olmalı.")
    if minimum is not None and n < minimum:
        raise MarketingError(f"{label} {minimum:g} değerinden küçük olamaz.")
    return n


def day(v: Any, label: str, *, allow_none: bool = True) -> Optional[str]:
    if v is None or v == "":
        if allow_none:
            return None
        raise MarketingError(f"{label} boş olamaz.")
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise MarketingError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


def _uid() -> str:
    return uuid.uuid4().hex


# ------------------------------------------------------------------ meta


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return {**loads(row.value_json, {}), "_at": iso(row.updated_at)} if row else {}


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    with engine.begin() as c:
        cond = (META.c.tenant_id == tenant, META.c.key == key)
        if c.execute(sa.select(META.c.key).where(*cond)).first():
            c.execute(META.update().where(*cond).values(value_json=dump(value), updated_at=now()))
        else:
            c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=dump(value), updated_at=now()))


# ------------------------------------------------------------------ geçmiş


def event(c: Any, plan_id: str, who: str, what: str, old: Any = None, new: Any = None) -> None:
    c.execute(EVENTS.insert().values(id=_uid(), plan_id=plan_id, zaman=now(), kim=(who or "sistem")[:120], ne=what[:40],
                                     eski_json=None if old is None else dump(old)[:20000],
                                     yeni_json=None if new is None else dump(new)[:20000]))


def events(engine: sa.engine.Engine, plan_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(EVENTS).where(EVENTS.c.plan_id == plan_id).order_by(EVENTS.c.zaman.desc())).all()
    return [{"id": r.id, "zaman": iso(r.zaman), "kim": r.kim, "ne": r.ne, "eski": loads(r.eski_json, None),
             "yeni": loads(r.yeni_json, None)} for r in rows]


# ------------------------------------------------------------------ plan okuma


def _row(c: Any, tenant: str, plan_id: str, *, lock: bool = False) -> Any:
    q = sa.select(PLANS).where(PLANS.c.tenant_id == tenant, PLANS.c.id == str(plan_id)[:24])
    if lock and c.engine.dialect.name == "postgresql":
        q = q.with_for_update()
    row = c.execute(q).first()
    if not row:
        raise MarketingError("Plan bulunamadı.", 404)
    return row


def _line(r: Any) -> dict[str, Any]:
    return {"id": r.id, "sira": r.sira, "kanal": r.kanal, "kanalAdi": CHANNELS.get(r.kanal, r.kanal), "altKanal": r.alt_kanal,
            "aciklama": r.aciklama, "tutar": r.tutar, "baslangic": r.baslangic, "bitis": r.bitis,
            "kpi": loads(r.kpi_json, None), "kaynak": r.kaynak, "gerekce": r.gerekce, "elleDuzeltildi": bool(r.elle_duzeltildi)}


def _task(r: Any) -> dict[str, Any]:
    return {"id": r.id, "tarih": r.tarih, "gunFarki": r.gun_farki, "is": r._mapping["is"],
            "kanal": r.kanal, "sorumlu": r.sorumlu, "durum": r.durum, "kanitUrl": r.kanit_url, "materyalId": r.materyal_id,
            "materyalTur": r.materyal_tur, "kaynak": r.kaynak, "launchId": r.launch_id}


def material_dict(r: Any) -> dict[str, Any]:
    kind = MATERIALS_KINDS.get(r.tur, (r.tur, None))
    return {"id": r.id, "planId": r.plan_id, "stokKodu": r.stok_kodu, "tur": r.tur, "turAdi": kind[0], "crmAlani": kind[1],
            "metin": r.metin, "kaynak": r.kaynak, "durum": r.durum, "durumAdi": MATERIAL_STATUSES.get(r.durum, r.durum),
            "editoryalOnaylayan": r.editoryal_onaylayan, "editoryalOnayZamani": iso(r.editoryal_onay_zamani),
            "onaylayan": r.onaylayan, "onayZamani": iso(r.onay_zamani), "surum": r.surum,
            "dogrulama": loads(r.dogrulama_json, None), "olusturan": r.olusturan, "guncelleme": iso(r.guncelleme)}


def plan_head(r: Any) -> dict[str, Any]:
    return {
        "id": r.id, "kind": r.kind, "kindAdi": KINDS.get(r.kind, r.kind), "stokKodu": r.stok_kodu, "crmKitapId": r.crm_kitap_id,
        "crmProjeId": r.crm_proje_id, "baslik": r.baslik, "durum": r.durum, "durumAdi": STATUSES.get(r.durum, r.durum),
        "surum": r.surum, "oncekiId": r.onceki_id, "sahip": r.sahip, "yayinTarihi": r.yayin_tarihi,
        "yayinTarihiKaynagi": r.yayin_tarihi_kaynagi, "yayinTarihiKaynakAdi": DATE_SOURCES.get(r.yayin_tarihi_kaynagi or "", None),
        "hedef": loads(r.hedef_json, None), "butceCerceve": r.butce_cerceve, "butceCerceveKaynak": loads(r.butce_cerceve_json, None),
        "butceToplam": r.butce_toplam, "donem": r.donem, "zeki": loads(r.zeki_json, None),
        "olusturan": r.olusturan, "olusturma": iso(r.olusturma), "guncelleyen": r.guncelleyen, "guncelleme": iso(r.guncelleme),
        "gonderen": r.gonderen, "gonderme": iso(r.gonderme), "onaylayan": r.onaylayan, "onayZamani": iso(r.onay_zamani),
        "ustOnaylayan": r.ust_onaylayan, "ustOnayZamani": iso(r.ust_onay_zamani), "gerekce": r.gerekce,
    }


def plan_full(engine: sa.engine.Engine, tenant: str, plan_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _row(c, tenant, plan_id)
        lines = c.execute(sa.select(LINES).where(LINES.c.plan_id == r.id).order_by(LINES.c.sira, LINES.c.id)).all()
        tasks = c.execute(sa.select(TASKS).where(TASKS.c.plan_id == r.id).order_by(TASKS.c.tarih, TASKS.c.id)).all()
        mats = c.execute(sa.select(MATERIALS).where(MATERIALS.c.plan_id == r.id).order_by(MATERIALS.c.tur, MATERIALS.c.guncelleme)).all()
    return {**plan_head(r), "lines": [_line(x) for x in lines], "tasks": [_task(x) for x in tasks],
            "materials": [material_dict(x) for x in mats]}


def list_plans(engine: sa.engine.Engine, tenant: str, *, kind: str = "", durum: str = "", sahip: str = "", donem: str = "",
               stok: Iterable[str] | None = None, include_archive: bool = False) -> list[dict[str, Any]]:
    cond = [PLANS.c.tenant_id == tenant]
    if kind:
        cond.append(PLANS.c.kind == kind)
    if durum:
        cond.append(PLANS.c.durum.in_([d for d in durum.split(",") if d]))
    elif not include_archive:
        cond.append(PLANS.c.durum != "arsiv")
    if sahip:
        cond.append(sa.func.lower(PLANS.c.sahip) == sahip.lower())
    if donem:
        cond.append(PLANS.c.donem == donem)
    codes = [s for s in (stok or []) if s]
    if codes:
        cond.append(PLANS.c.stok_kodu.in_(codes))
    with engine.connect() as c:
        rows = c.execute(sa.select(PLANS).where(*cond).order_by(PLANS.c.yayin_tarihi, PLANS.c.id)).all()
    return [plan_head(r) for r in rows]


def material_row(engine: sa.engine.Engine, tenant: str, mid: str) -> tuple[dict[str, Any], dict[str, Any]]:
    with engine.connect() as c:
        m = c.execute(sa.select(MATERIALS).where(MATERIALS.c.id == str(mid)[:32])).first()
        if not m:
            raise MarketingError("Materyal bulunamadı.", 404)
        p = _row(c, tenant, m.plan_id)
    return material_dict(m), plan_head(p)


# ------------------------------------------------------------------ plan yazma


def next_id(c: Any, tenant: str, year: int) -> str:
    prefix = f"MP-{year}-"
    ids = c.execute(sa.select(PLANS.c.id).where(PLANS.c.tenant_id == tenant, PLANS.c.id.like(prefix + "%"))).scalars().all()
    n = max((int(i[len(prefix):]) for i in ids if i[len(prefix):].isdigit()), default=0) + 1
    return f"{prefix}{n:04d}"


def create_plan(engine: sa.engine.Engine, tenant: str, user: str, *, kind: str, baslik: str, stok_kodu: Optional[str] = None,
                crm_kitap_id: Optional[str] = None, crm_proje_id: Optional[str] = None, yayin_tarihi: Optional[str] = None,
                yayin_kaynagi: Optional[str] = None, hedef: Any = None, donem: Optional[str] = None,
                sahip: Optional[str] = None) -> str:
    if kind not in KINDS:
        raise MarketingError("Plan türü yeni, backlist ya da aylik olmalı.")
    if not one_line(baslik, 400):
        raise MarketingError("Plan başlığı gerekli.")
    with engine.begin() as c:
        if stok_kodu and kind == "yeni":
            open_ = c.execute(sa.select(PLANS.c.id).where(
                PLANS.c.tenant_id == tenant, PLANS.c.kind == kind, PLANS.c.stok_kodu == stok_kodu,
                PLANS.c.durum.in_(("taslak", "onayda", "geri", "onayli")))).first()
            if open_:
                raise MarketingError(f"Bu kitabın planı zaten var ({open_.id}); onu açın ya da revize edin.", 409)
        pid = next_id(c, tenant, today().year)
        t = now()
        c.execute(PLANS.insert().values(
            id=pid, tenant_id=tenant, kind=kind, stok_kodu=stok_kodu, crm_kitap_id=crm_kitap_id, crm_proje_id=crm_proje_id,
            baslik=one_line(baslik, 400), durum="taslak", surum=1, sahip=(sahip or user)[:120], yayin_tarihi=yayin_tarihi,
            yayin_tarihi_kaynagi=yayin_kaynagi, hedef_json=None if hedef is None else dump(hedef), butce_toplam=0.0,
            donem=donem, olusturan=user, olusturma=t, guncelleyen=user, guncelleme=t))
        event(c, pid, user, "olusturuldu", None, {"kind": kind, "stok": stok_kodu, "yayin": yayin_tarihi, "kaynak": yayin_kaynagi})
    return pid


def editable(r: Any) -> None:
    if r.durum not in EDITABLE:
        raise MarketingError("Yalnız taslak ya da geri gönderilmiş plan değiştirilir; onaylı planı «Revize et» ile yeni sürüme alın.", 409)


def update_plan(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, body: dict[str, Any]) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "baslik" in body:
        b = one_line(body.get("baslik"), 400)
        if not b:
            raise MarketingError("Plan başlığı boş olamaz.")
        vals["baslik"] = b
    if "yayinTarihi" in body:
        vals["yayin_tarihi"] = day(body.get("yayinTarihi"), "Yayın tarihi")
        vals["yayin_tarihi_kaynagi"] = "elle" if vals["yayin_tarihi"] else None
    if "sahip" in body:
        vals["sahip"] = one_line(body.get("sahip"), 120)
    if "butceCerceve" in body:
        v = number(body.get("butceCerceve"), "Bütçe çerçevesi", allow_none=True)
        vals["butce_cerceve"] = None if v is None else round(v, 2)
        vals["butce_cerceve_json"] = dump({"kaynak": "elle", "gerekce": "Plan sahibi elle girdi.", "kim": user})
    if not vals:
        raise MarketingError("Değiştirilecek alan yok.")
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        if r.durum == "arsiv":
            raise MarketingError("Arşivdeki plan değiştirilemez.", 409)
        if set(vals) - {"sahip"}:
            editable(r)
        old = {k: getattr(r, k) for k in vals}
        vals.update(guncelleyen=user, guncelleme=now())
        c.execute(PLANS.update().where(PLANS.c.id == r.id).values(**vals))
        event(c, r.id, user, "duzenlendi", old, {k: v for k, v in vals.items() if k not in ("guncelleyen", "guncelleme")})
    return plan_full(engine, tenant, plan_id)


def reschedule(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str) -> int:
    """Yayın günü değişince şablondan gelen bekleyen işlerin tarihi yayın gününe göre yeniden hesaplanır. Özel gün ve
    kullanıcı işleri kendi tarihinde kalır; yalnız gün farkları yeniden yazılır."""
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        if not r.yayin_tarihi:
            return 0
        pub = date.fromisoformat(r.yayin_tarihi)
        n = 0
        for t in c.execute(sa.select(TASKS).where(TASKS.c.plan_id == r.id)).all():
            if t.kaynak == "sablon" and t.durum == "bekliyor" and t.gun_farki is not None:
                c.execute(TASKS.update().where(TASKS.c.id == t.id).values(
                    tarih=date.fromordinal(pub.toordinal() + t.gun_farki).isoformat()))
                n += 1
            elif t.tarih:
                c.execute(TASKS.update().where(TASKS.c.id == t.id).values(gun_farki=(date.fromisoformat(t.tarih) - pub).days))
        if n:
            event(c, r.id, user, "takvim-kaydi", None, {"yayin": r.yayin_tarihi, "tasinan": n})
    return n


def set_fields(engine: sa.engine.Engine, plan_id: str, **vals: Any) -> None:
    """Sistem alanları (hedef, çerçeve, Zeki AI gerekçesi): geçmişe ayrıca yazılır."""
    with engine.begin() as c:
        c.execute(PLANS.update().where(PLANS.c.id == plan_id).values(**vals))


def delete_plan(engine: sa.engine.Engine, tenant: str, plan_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        if r.durum != "taslak":
            raise MarketingError("Yalnız taslak plan silinebilir.", 409)
        for t in (LINES, TASKS, MATERIALS, EVENTS, JOBS):
            c.execute(t.delete().where(t.c.plan_id == r.id))
        c.execute(PLANS.delete().where(PLANS.c.id == r.id))
    return {"id": r.id, "baslik": r.baslik}


def _total(c: Any, plan_id: str) -> float:
    v = c.execute(sa.select(sa.func.coalesce(sa.func.sum(LINES.c.tutar), 0.0)).where(LINES.c.plan_id == plan_id)).scalar()
    return round(float(v or 0.0), 2)


def _clean_line(x: dict[str, Any], i: int) -> dict[str, Any]:
    kanal = str(x.get("kanal") or "").strip()
    if kanal not in CHANNELS:
        raise MarketingError(f"{i + 1}. satır: kanal tanınmıyor ({kanal or 'boş'}).")
    tutar = number(x.get("tutar", 0) if x.get("tutar") is not None else 0, f"{i + 1}. satırın tutarı")
    bas, bit = day(x.get("baslangic"), "Başlangıç"), day(x.get("bitis"), "Bitiş")
    if bas and bit and bit < bas:
        raise MarketingError(f"{i + 1}. satır: bitiş başlangıçtan önce olamaz.")
    kpi = x.get("kpi")
    return {"kanal": kanal, "alt_kanal": one_line(x.get("altKanal"), 200), "aciklama": text(x.get("aciklama"), 4000),
            "tutar": round(float(tutar or 0), 2), "baslangic": bas, "bitis": bit,
            "kpi_json": dump(kpi) if isinstance(kpi, (dict, list)) else None}


def replace_lines(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Satırların tamamı gönderilir. Zeki AI satırında tutar/tarih değişirse satır «elle düzeltildi» olur ve yeniden
    öneride korunur; yeni satır kullanıcınındır."""
    if not isinstance(items, list):
        raise MarketingError("Satır listesi gerekli.")
    clean = [(_clean_line(x, i), x) for i, x in enumerate(items)]
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        editable(r)
        cur = {x.id: x for x in c.execute(sa.select(LINES).where(LINES.c.plan_id == r.id)).all()}
        old_total = r.butce_toplam
        c.execute(LINES.delete().where(LINES.c.plan_id == r.id))
        for i, (v, raw) in enumerate(clean):
            prev = cur.get(str(raw.get("id") or ""))
            if prev is not None:
                changed = any(getattr(prev, k) != v[k] for k in ("kanal", "tutar", "baslangic", "bitis"))
                kaynak = prev.kaynak
                elle = bool(prev.elle_duzeltildi) or (changed and prev.kaynak != "kullanici")
                gerekce = prev.gerekce
                lid = prev.id
            else:
                kaynak, elle, gerekce, lid = "kullanici", False, None, _uid()
            c.execute(LINES.insert().values(id=lid, plan_id=r.id, sira=i, kaynak=kaynak, elle_duzeltildi=elle, gerekce=gerekce, **v))
        total = _total(c, r.id)
        c.execute(PLANS.update().where(PLANS.c.id == r.id).values(butce_toplam=total, guncelleyen=user, guncelleme=now()))
        event(c, r.id, user, "butce", {"toplam": old_total, "satir": len(cur)}, {"toplam": total, "satir": len(clean)})
    return plan_full(engine, tenant, plan_id)


def put_suggested_lines(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, lines: list[dict[str, Any]]) -> None:
    """Zeki AI önerisi: elle düzeltilmiş ve kullanıcının eklediği satırlar korunur, yalnız dokunulmamış öneri satırları
    yenilenir. Korunan satırın kanalına yeni öneri satırı eklenmez."""
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        editable(r)
        keep = c.execute(sa.select(LINES).where(LINES.c.plan_id == r.id, sa.or_(LINES.c.elle_duzeltildi.is_(True),
                                                                               LINES.c.kaynak != "zeki"))).all()
        kept_channels = {x.kanal for x in keep}
        c.execute(LINES.delete().where(LINES.c.plan_id == r.id, LINES.c.elle_duzeltildi.is_(False), LINES.c.kaynak == "zeki"))
        n = len(keep)
        for ln in lines:
            if ln["kanal"] in kept_channels:
                continue
            c.execute(LINES.insert().values(
                id=_uid(), plan_id=r.id, sira=n, kanal=ln["kanal"], alt_kanal=ln.get("alt_kanal"), aciklama=ln.get("aciklama"),
                tutar=round(float(ln.get("tutar") or 0), 2), baslangic=ln.get("baslangic"), bitis=ln.get("bitis"),
                kpi_json=None, kaynak="zeki", gerekce=ln.get("gerekce"), elle_duzeltildi=False))
            n += 1
        total = _total(c, r.id)
        c.execute(PLANS.update().where(PLANS.c.id == r.id).values(butce_toplam=total, guncelleyen=user, guncelleme=now()))
        event(c, r.id, user, "oneri-butce", None, {"toplam": total, "korunan": len(keep)})


def _clean_task(x: dict[str, Any], i: int, pub: Optional[str]) -> dict[str, Any]:
    is_ = one_line(x.get("is"), 400)
    if not is_:
        raise MarketingError(f"{i + 1}. iş: açıklama boş olamaz.")
    durum = str(x.get("durum") or "bekliyor")
    if durum not in TASK_STATUSES:
        raise MarketingError(f"{i + 1}. iş: durum bekliyor, yapildi ya da atlandi olmalı.")
    kanal = str(x.get("kanal") or "") or None
    if kanal and kanal not in CHANNELS:
        raise MarketingError(f"{i + 1}. iş: kanal tanınmıyor.")
    tarih = day(x.get("tarih"), "İş tarihi")
    gun = x.get("gunFarki")
    if tarih and pub:
        gun = (date.fromisoformat(tarih) - date.fromisoformat(pub)).days
    elif gun is not None and pub and not tarih:
        gun = int(gun)
        tarih = date.fromordinal(date.fromisoformat(pub).toordinal() + gun).isoformat()
    mt = str(x.get("materyalTur") or "") or None
    if mt and mt not in MATERIALS_KINDS:
        mt = None
    return {"tarih": tarih, "gun_farki": None if gun is None else int(gun), "is": is_, "kanal": kanal,
            "sorumlu": one_line(x.get("sorumlu"), 120), "durum": durum, "kanit_url": one_line(x.get("kanitUrl"), 1000),
            "materyal_id": one_line(x.get("materyalId"), 32), "materyal_tur": mt,
            "kaynak": x.get("kaynak") if x.get("kaynak") in ("sablon", "ozel-gun", "kullanici") else "kullanici"}


def replace_tasks(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, items: list[dict[str, Any]],
                  *, system: bool = False) -> dict[str, Any]:
    """Takvimin tamamı. Onaylı planda yalnız durum/kanıt değişebilir (iş yapıldıkça işaretlenir)."""
    if not isinstance(items, list):
        raise MarketingError("İş listesi gerekli.")
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        if r.durum == "arsiv":
            raise MarketingError("Arşivdeki plan değiştirilemez.", 409)
        cur = {x.id: x for x in c.execute(sa.select(TASKS).where(TASKS.c.plan_id == r.id)).all()}
        if r.durum not in EDITABLE and not system:
            done = 0
            for x in items:
                t = cur.get(str(x.get("id") or ""))
                if t is None:
                    raise MarketingError("Onaylı planın takvimine iş eklenemez; revize edin.", 409)
                d = str(x.get("durum") or t.durum)
                if d not in TASK_STATUSES:
                    raise MarketingError("Durum bekliyor, yapildi ya da atlandi olmalı.")
                url = one_line(x.get("kanitUrl"), 1000) if "kanitUrl" in x else t.kanit_url
                if d != t.durum or url != t.kanit_url:
                    c.execute(TASKS.update().where(TASKS.c.id == t.id).values(durum=d, kanit_url=url))
                    done += 1
            event(c, r.id, user, "takvim-durum", None, {"degisen": done})
        else:
            clean = [(_clean_task(x, i, r.yayin_tarihi), x) for i, x in enumerate(items)]
            c.execute(TASKS.delete().where(TASKS.c.plan_id == r.id))
            for v, raw in clean:
                tid = str(raw.get("id") or "") if str(raw.get("id") or "") in cur else _uid()
                c.execute(TASKS.insert().values(id=tid, plan_id=r.id, **v))
            event(c, r.id, user, "takvim", {"is": len(cur)}, {"is": len(clean)})
        c.execute(PLANS.update().where(PLANS.c.id == r.id).values(guncelleyen=user, guncelleme=now()))
    return plan_full(engine, tenant, plan_id)


# ------------------------------------------------------------------ materyal


def add_material(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, tur: str, metin: str, kaynak: str,
                 dogrulama: Any = None, *, replace_draft: bool = False) -> dict[str, Any]:
    """Yeni materyal. `replace_draft`: aynı türün aynı kaynaktan (Zeki AI) taslağı varsa onun metni yenilenir."""
    if tur not in MATERIALS_KINDS:
        raise MarketingError("Materyal türü tanınmıyor.")
    body = text(metin, 60000)
    if not body:
        raise MarketingError("Materyal metni boş.")
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        if r.durum == "arsiv":
            raise MarketingError("Arşivdeki plana materyal eklenemez.", 409)
        t = now()
        if replace_draft:
            prev = c.execute(sa.select(MATERIALS).where(MATERIALS.c.plan_id == r.id, MATERIALS.c.tur == tur,
                                                        MATERIALS.c.kaynak == kaynak, MATERIALS.c.durum == "taslak")).first()
            if prev:
                c.execute(MATERIALS.update().where(MATERIALS.c.id == prev.id).values(
                    metin=body, surum=prev.surum + 1, dogrulama_json=None if dogrulama is None else dump(dogrulama),
                    olusturan=user, guncelleme=t))
                event(c, r.id, user, "materyal", {"id": prev.id, "surum": prev.surum}, {"id": prev.id, "tur": tur, "kaynak": kaynak})
                return material_dict(c.execute(sa.select(MATERIALS).where(MATERIALS.c.id == prev.id)).one())
        mid = _uid()
        c.execute(MATERIALS.insert().values(
            id=mid, plan_id=r.id, stok_kodu=r.stok_kodu, tur=tur, metin=body, kaynak=kaynak[:80], durum="taslak", surum=1,
            dogrulama_json=None if dogrulama is None else dump(dogrulama), olusturan=user, guncelleme=t))
        event(c, r.id, user, "materyal", None, {"id": mid, "tur": tur, "kaynak": kaynak})
        return material_dict(c.execute(sa.select(MATERIALS).where(MATERIALS.c.id == mid)).one())


def update_material(engine: sa.engine.Engine, tenant: str, user: str, mid: str, metin: Any, dogrulama: Any = None) -> dict[str, Any]:
    body = text(metin, 60000)
    if not body:
        raise MarketingError("Materyal metni boş olamaz.")
    with engine.begin() as c:
        m = c.execute(sa.select(MATERIALS).where(MATERIALS.c.id == str(mid)[:32])).first()
        if not m:
            raise MarketingError("Materyal bulunamadı.", 404)
        r = _row(c, tenant, m.plan_id, lock=True)
        if r.durum == "arsiv":
            raise MarketingError("Arşivdeki planın materyali değiştirilemez.", 409)
        if body == m.metin:
            return material_dict(m)
        c.execute(MATERIALS.update().where(MATERIALS.c.id == m.id).values(
            metin=body, surum=m.surum + 1, durum="taslak", kaynak="kullanici" if not m.kaynak.startswith("kullanici") else m.kaynak,
            editoryal_onaylayan=None, editoryal_onay_zamani=None, onaylayan=None, onay_zamani=None,
            dogrulama_json=None if dogrulama is None else dump(dogrulama), olusturan=user, guncelleme=now()))
        event(c, r.id, user, "materyal-duzenle", {"id": m.id, "surum": m.surum, "durum": m.durum, "kaynak": m.kaynak},
              {"id": m.id, "surum": m.surum + 1})
        return material_dict(c.execute(sa.select(MATERIALS).where(MATERIALS.c.id == m.id)).one())


def approve_material(engine: sa.engine.Engine, tenant: str, user: str, mid: str, seviye: str) -> dict[str, Any]:
    """Editoryal onay önce; pazarlama onayı editoryal onaylı materyale verilir. Aynı kişi iki onayı birden veremez."""
    if seviye not in ("editoryal", "pazarlama"):
        raise MarketingError("Onay seviyesi editoryal ya da pazarlama olmalı.")
    with engine.begin() as c:
        m = c.execute(sa.select(MATERIALS).where(MATERIALS.c.id == str(mid)[:32])).first()
        if not m:
            raise MarketingError("Materyal bulunamadı.", 404)
        r = _row(c, tenant, m.plan_id, lock=True)
        if r.durum == "arsiv":
            raise MarketingError("Arşivdeki planın materyali onaylanamaz.", 409)
        t = now()
        if seviye == "editoryal":
            if m.durum != "taslak":
                raise MarketingError("Materyal editoryal onay beklemiyor.", 409)
            c.execute(MATERIALS.update().where(MATERIALS.c.id == m.id).values(
                durum="editoryal-onayli", editoryal_onaylayan=user, editoryal_onay_zamani=t))
        else:
            if m.durum != "editoryal-onayli":
                raise MarketingError("Önce editoryal onay verilmeli.", 409)
            if (m.editoryal_onaylayan or "").lower() == user.lower():
                raise MarketingError("Editoryal onayı veren kişi pazarlama onayını veremez; başka bir yetkili onaylamalı.", 409)
            c.execute(MATERIALS.update().where(MATERIALS.c.id == m.id).values(durum="onayli", onaylayan=user, onay_zamani=t))
        event(c, r.id, user, f"materyal-onay-{seviye}", {"id": m.id, "durum": m.durum}, {"id": m.id, "surum": m.surum})
        return material_dict(c.execute(sa.select(MATERIALS).where(MATERIALS.c.id == m.id)).one())


# ------------------------------------------------------------------ onay akışı


def needs_upper(total: float, threshold: Optional[float]) -> bool:
    return threshold is not None and threshold > 0 and (total or 0) > threshold


def submit(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        if r.durum not in EDITABLE:
            raise MarketingError("Yalnız taslak ya da geri gönderilmiş plan onaya gönderilir.", 409)
        if r.kind == "yeni" and not r.yayin_tarihi:
            raise MarketingError("Planda yayın tarihi yok; önce yayın tarihini girin.")
        n = c.execute(sa.select(sa.func.count()).select_from(LINES).where(LINES.c.plan_id == r.id)).scalar()
        if not n:
            raise MarketingError("Planda kanal ve bütçe satırı yok.")
        c.execute(PLANS.update().where(PLANS.c.id == r.id).values(
            durum="onayda", gonderen=user, gonderme=now(), onaylayan=None, onay_zamani=None, ust_onaylayan=None,
            ust_onay_zamani=None, guncelleyen=user, guncelleme=now()))
        event(c, r.id, user, "onaya-gonderildi", {"durum": r.durum}, {"durum": "onayda", "butce": r.butce_toplam})
    return plan_full(engine, tenant, plan_id)


def withdraw(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        if r.durum != "onayda":
            raise MarketingError("Plan onayda değil.", 409)
        c.execute(PLANS.update().where(PLANS.c.id == r.id).values(durum="taslak", onaylayan=None, onay_zamani=None,
                                                                   ust_onaylayan=None, ust_onay_zamani=None,
                                                                   guncelleyen=user, guncelleme=now()))
        event(c, r.id, user, "onaydan-cekildi", {"durum": "onayda"}, {"durum": "taslak"})
    return plan_full(engine, tenant, plan_id)


def decide(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, approve: bool, note: Any,
           *, level: str, threshold: Optional[float]) -> dict[str, Any]:
    """`level`: pazarlama (plan-onay) ya da ust (butce-ust-onay). Eşik üstü planda iki onay tamamlanınca `onayli`.
    Önceki onaylı sürüm (revizyon zinciri) onayda arşive geçer."""
    note_t = text(note, 4000)
    if not approve and not note_t:
        raise MarketingError("Geri gönderme gerekçesi yazın.")
    if level not in ("pazarlama", "ust"):
        raise MarketingError("Onay türü tanınmıyor.")
    archived = None
    with engine.begin() as c:
        r = _row(c, tenant, plan_id, lock=True)
        if r.durum != "onayda":
            raise MarketingError("Plan onay beklemiyor.", 409)
        if (r.gonderen or "").lower() == user.lower():
            raise MarketingError("Onaya gönderen kişi aynı planı onaylayamaz; başka bir yetkili onaylamalı.", 409)
        upper = needs_upper(r.butce_toplam, threshold)
        t = now()
        if not approve:
            c.execute(PLANS.update().where(PLANS.c.id == r.id).values(
                durum="geri", gerekce=note_t, onaylayan=None, onay_zamani=None, ust_onaylayan=None, ust_onay_zamani=None,
                guncelleyen=user, guncelleme=t))
            event(c, r.id, user, "geri-gonderildi", {"durum": "onayda"}, {"durum": "geri", "gerekce": note_t, "seviye": level})
        else:
            if level == "ust" and not upper:
                raise MarketingError("Bu planın bütçesi eşiğin altında; üst onay gerekmiyor.", 409)
            vals: dict[str, Any] = {}
            if level == "pazarlama":
                if r.onaylayan:
                    raise MarketingError("Pazarlama onayı zaten verilmiş.", 409)
                if (r.ust_onaylayan or "").lower() == user.lower():
                    raise MarketingError("İki onay iki ayrı kişiden gelmeli; üst onayı siz verdiniz.", 409)
                vals.update(onaylayan=user, onay_zamani=t)
                done = (not upper) or bool(r.ust_onaylayan)
            else:
                if r.ust_onaylayan:
                    raise MarketingError("Üst onay zaten verilmiş.", 409)
                if (r.onaylayan or "").lower() == user.lower():
                    raise MarketingError("İki onay iki ayrı kişiden gelmeli; pazarlama onayını siz verdiniz.", 409)
                vals.update(ust_onaylayan=user, ust_onay_zamani=t)
                done = bool(r.onaylayan)
            if done:
                vals["durum"] = "onayli"
                if r.onceki_id:
                    prev = c.execute(sa.select(PLANS).where(PLANS.c.tenant_id == tenant, PLANS.c.id == r.onceki_id)).first()
                    if prev and prev.durum == "onayli":
                        c.execute(PLANS.update().where(PLANS.c.id == prev.id).values(durum="arsiv", guncelleyen=user, guncelleme=t))
                        event(c, prev.id, user, "arsivlendi", {"durum": "onayli"}, {"durum": "arsiv", "yerine": r.id})
                        archived = prev.id
            c.execute(PLANS.update().where(PLANS.c.id == r.id).values(**vals, gerekce=note_t or r.gerekce,
                                                                       guncelleyen=user, guncelleme=t))
            event(c, r.id, user, "onay-" + level, {"durum": "onayda"},
                  {"durum": vals.get("durum", "onayda"), "not": note_t, "ustOnayGerekli": upper})
    out = plan_full(engine, tenant, plan_id)
    out["archived"] = archived
    return out


def revise(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, reason: Any) -> dict[str, Any]:
    why = text(reason, 4000)
    if not why:
        raise MarketingError("Revizyon gerekçesi yazın.")
    with engine.begin() as c:
        r = _row(c, tenant, plan_id)
        if r.durum != "onayli":
            raise MarketingError("Yalnız onaylı plan revize edilir.", 409)
        open_ = c.execute(sa.select(PLANS.c.id).where(PLANS.c.tenant_id == tenant, PLANS.c.onceki_id == r.id,
                                                      PLANS.c.durum.in_(EDITABLE + ("onayda",)))).first()
        if open_:
            raise MarketingError(f"Bu planın açık bir revizyonu var ({open_.id}).", 409)
        pid = next_id(c, tenant, today().year)
        t = now()
        vals = {k: getattr(r, k) for k in ("kind", "stok_kodu", "crm_kitap_id", "crm_proje_id", "baslik", "sahip", "yayin_tarihi",
                                          "yayin_tarihi_kaynagi", "hedef_json", "butce_cerceve", "butce_cerceve_json",
                                          "butce_toplam", "donem", "zeki_json")}
        c.execute(PLANS.insert().values(id=pid, tenant_id=tenant, durum="taslak", surum=r.surum + 1, onceki_id=r.id,
                                        gerekce=why, olusturan=user, olusturma=t, guncelleyen=user, guncelleme=t, **vals))
        for ln in c.execute(sa.select(LINES).where(LINES.c.plan_id == r.id)).all():
            c.execute(LINES.insert().values(**{**dict(ln._mapping), "id": _uid(), "plan_id": pid}))
        for tk in c.execute(sa.select(TASKS).where(TASKS.c.plan_id == r.id)).all():
            c.execute(TASKS.insert().values(**{**dict(tk._mapping), "id": _uid(), "plan_id": pid}))
        for m in c.execute(sa.select(MATERIALS).where(MATERIALS.c.plan_id == r.id)).all():
            c.execute(MATERIALS.insert().values(**{**dict(m._mapping), "id": _uid(), "plan_id": pid}))
        event(c, pid, user, "revizyon", {"onceki": r.id, "surum": r.surum}, {"surum": r.surum + 1, "gerekce": why})
        event(c, r.id, user, "revizyon-acildi", None, {"yeni": pid, "gerekce": why})
    return plan_full(engine, tenant, pid)


# ------------------------------------------------------------------ iş kuyruğu (Zeki AI)


def job_create(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, tur: str, target: Any) -> dict[str, Any]:
    with engine.begin() as c:
        _row(c, tenant, plan_id)
        running = c.execute(sa.select(JOBS.c.id).where(JOBS.c.plan_id == plan_id, JOBS.c.tur == tur,
                                                       JOBS.c.durum.in_(("bekliyor", "calisiyor")))).first()
        if running:
            raise MarketingError("Bu plan için aynı iş zaten sürüyor; bitince yeniden deneyin.", 409)
        jid = _uid()
        c.execute(JOBS.insert().values(id=jid, tenant_id=tenant, plan_id=plan_id, tur=tur, hedef_json=dump(target),
                                       durum="bekliyor", olusturan=user, olusturma=now()))
    return job_get(engine, jid)


def job_update(engine: sa.engine.Engine, jid: str, **vals: Any) -> None:
    if "sonuc" in vals:
        vals["sonuc_json"] = dump(vals.pop("sonuc"))
    if vals.get("durum") in ("bitti", "hata"):
        vals["bitis"] = now()
    with engine.begin() as c:
        c.execute(JOBS.update().where(JOBS.c.id == jid).values(**vals))


def job_get(engine: sa.engine.Engine, jid: str) -> dict[str, Any]:
    with engine.connect() as c:
        j = c.execute(sa.select(JOBS).where(JOBS.c.id == jid)).first()
    if not j:
        raise MarketingError("İş bulunamadı.", 404)
    return _job(j)


def _job(j: Any) -> dict[str, Any]:
    return {"id": j.id, "planId": j.plan_id, "tur": j.tur, "hedef": loads(j.hedef_json, None), "durum": j.durum, "adim": j.adim,
            "hata": j.hata, "sonuc": loads(j.sonuc_json, None), "olusturan": j.olusturan, "olusturma": iso(j.olusturma),
            "bitis": iso(j.bitis)}


def jobs_of(engine: sa.engine.Engine, plan_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(JOBS).where(JOBS.c.plan_id == plan_id).order_by(JOBS.c.olusturma.desc())).all()
    return [_job(j) for j in rows]


def fail_stale_jobs(engine: sa.engine.Engine) -> int:
    """Köprü yeniden başlayınca yarım kalan işler: sonsuza kadar «sürüyor» görünmesin."""
    with engine.begin() as c:
        res = c.execute(JOBS.update().where(JOBS.c.durum.in_(("bekliyor", "calisiyor"))).values(
            durum="hata", hata="Servis yeniden başladı; iş yarıda kaldı. Yeniden başlatın.", bitis=now()))
    return int(res.rowcount or 0)


# ------------------------------------------------------------------ karne önbelleği


def card_get(engine: sa.engine.Engine, tenant: str, code: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(CARDS).where(CARDS.c.tenant_id == tenant, CARDS.c.stok_kodu == code)).first()
    if not r:
        return None
    return {**loads(r.veri_json, {}), "asof": iso(r.asof), "veriSonu": r.veri_sonu}


def card_put(engine: sa.engine.Engine, tenant: str, code: str, data: dict[str, Any], veri_sonu: Optional[str]) -> None:
    with engine.begin() as c:
        cond = (CARDS.c.tenant_id == tenant, CARDS.c.stok_kodu == code)
        vals = {"veri_json": dump(data), "asof": now(), "veri_sonu": veri_sonu}
        if c.execute(sa.select(CARDS.c.stok_kodu).where(*cond)).first():
            c.execute(CARDS.update().where(*cond).values(**vals))
        else:
            c.execute(CARDS.insert().values(stok_kodu=code, tenant_id=tenant, **vals))


# ------------------------------------------------------------------ sözleşme (M16, M18, M19, M20–M23 okur)


def contract(engine: sa.engine.Engine, tenant: str, *, stok: str = "", kind: str = "", durum: str = "onayli",
             donem: str = "") -> dict[str, Any]:
    """Onaylı planların satırları, takvimi ve yalnız onaylı materyalleri. Taslak materyal dışarı verilmez."""
    heads = list_plans(engine, tenant, kind=kind, durum=durum or "onayli", donem=donem,
                       stok=[s.strip() for s in stok.split(",")] if stok else None)
    items = []
    for h in heads:
        full = plan_full(engine, tenant, h["id"])
        full["materials"] = [m for m in full["materials"] if m["durum"] == "onayli"]
        full.pop("zeki", None)
        items.append(full)
    return {"items": items, "total": len(items)}
