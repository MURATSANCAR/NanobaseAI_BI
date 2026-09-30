"""M37 Okuyucu topluluğu ve topluluk yönetimi: okur kitlesi envanteri ve izin sağlığı (yalnız sayı), onaylı segment
akışı, topluluk program takvimi (okuma kulübü, imza günü, anket, çevrim içi), cevapsız okur yorumlarına cevap taslağı.

**Okur çekirdeği H2'dedir.** Kimlik birleştirme, izin hesabı, ilgi alanı ve segment kuralının sayımı H2 okur veri
tabanının işidir; bu modül onları yeniden yazmaz. H2'ye tek bağlantı noktası `okur_sources.ReadersCore`'dur: H2 yoksa
her sayı ekranı «Okur çekirdeği bağlı değil» der, segment ölçülemez ve onaya gönderilemez.

**Bu modülün kendi işi:**
- Segmentin topluluk amacıyla onayı: amaç, süre, kanal; taslak → onay bekliyor → onaylandı | reddedildi | süresi doldu.
  Onay açıkça verilen `ozellik:topluluk.segment-onay` ister (KVKK sorumlusu); yazan ve onaya gönderen onaylayamaz. Onaylı
  segment değişirse taslağa döner, sürüm artar. Kişi listesi dışa aktarımı ikinci sürümdür (hukuk görüşünden sonra).
- Özel nitelikli çağrışım koruması (KVKK md. 6): her ilgi alanı «özel nitelikli çağrışım var / yok / bilinmiyor» diye
  işaretlenir (Zeki AI kapalı küme seçimi, sonra insan kararı). Varsayılan: yalnız «yok» işaretli ilgi alanı segmentte
  kullanılır; din/inanç çağrışımlı alanlar hukuk kararı (`OKUR_HASSAS_SEGMENT_ACIK=1`) olmadan kapalıdır. «Bilinmiyor»
  hiçbir durumda segmente girmez.
- Program takvimi ve Zeki AI duyuru taslağı; yorum cevap taslağı. Portal hiçbir iletiyi göndermez, T-soft'a ve CRM'e
  yazmaz; cevap sitede elle girilir.
- Gece anlık görüntüsü: H2'nin envanter ve izin sayıları günlük saklanır (aylık eğilim), segment büyüklükleri ölçülür.

**Kişi verisi tutulmaz:** tablolarda ad, e-posta, telefon, adres yoktur; H2'den gelen her cevap `scrub` ile kişi alanından
ve e-posta/telefon kalıbından arındırılır. Modele giden istemde de yoktur (`assert_no_personal`).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import zeki_text as Z

log = logging.getLogger("semantic.okur")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

INVENTORY = sa.Table(
    "semantic_okur_inventory", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("tarih", sa.String(10), primary_key=True),            # YYYY-MM-DD (İstanbul)
    sa.Column("kaynak", sa.String(80), primary_key=True),
    sa.Column("kayit_tipi", sa.String(120), primary_key=True),      # boşsa ""
    sa.Column("toplam", sa.Integer, nullable=False),
    sa.Column("kvkk_onayli", sa.Integer),
    sa.Column("iys_onayli", sa.Integer),
    sa.Column("eposta_izinli", sa.Integer),
    sa.Column("sms_izinli", sa.Integer),
    sa.Column("ilgi_alani_dolu", sa.Integer),
    sa.Column("silinebilir", sa.Integer),
    sa.Column("cocuk_olasi", sa.Integer),
)
CONSENT = sa.Table(
    "semantic_okur_consent_issues", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("tarih", sa.String(10), primary_key=True),
    sa.Column("tur", sa.String(80), primary_key=True),
    sa.Column("ad", sa.String(300)),
    sa.Column("sayi", sa.Integer, nullable=False),
)
SEGMENTS = sa.Table(
    "semantic_okur_segments", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("ad", sa.String(200), nullable=False),
    sa.Column("kural_json", sa.Text, nullable=False),               # H2 kural sözlüğünde; bu modül yorumlamaz
    sa.Column("kural_cumlesi", sa.Text),                            # H2'nin okunur açıklaması (varsa)
    sa.Column("amac", sa.Text),
    sa.Column("kanal", sa.String(10), nullable=False, default="eposta"),   # eposta | sms | ikisi | yok
    sa.Column("sure_bitis", sa.String(10)),
    sa.Column("durum", sa.String(16), nullable=False),
    sa.Column("surum", sa.Integer, nullable=False, default=1),
    sa.Column("ilgi_json", sa.Text),                                # kuraldaki ilgi alanı kimlikleri (koruma için)
    sa.Column("son_toplam", sa.Integer),
    sa.Column("son_izinli", sa.Integer),
    sa.Column("son_eposta", sa.Integer),
    sa.Column("son_sms", sa.Integer),
    sa.Column("son_olcum", sa.DateTime(timezone=True)),
    sa.Column("yazan", sa.String(120), nullable=False),
    sa.Column("yazma_zamani", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("gonderme_zamani", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("onay_notu", sa.Text),
)
SEGMENT_SIZES = sa.Table(
    "semantic_okur_segment_sizes", _md,
    sa.Column("segment_id", sa.String(32), primary_key=True),
    sa.Column("tarih", sa.String(10), primary_key=True),
    sa.Column("toplam", sa.Integer, nullable=False),
    sa.Column("izinli", sa.Integer),
    sa.Column("eposta", sa.Integer),
    sa.Column("sms", sa.Integer),
)
PROGRAMS = sa.Table(
    "semantic_okur_programs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(16), nullable=False),
    sa.Column("ad", sa.String(300), nullable=False),
    sa.Column("tarih", sa.String(10)),
    sa.Column("saat", sa.String(5)),
    sa.Column("sehir", sa.String(80)),
    sa.Column("yer", sa.String(300)),
    sa.Column("kitap_id", sa.String(64)),                           # CRM new_kitapId
    sa.Column("kitap_adi", sa.String(300)),
    sa.Column("yazar_adi", sa.String(300)),
    sa.Column("segment_id", sa.String(32)),
    sa.Column("durum", sa.String(12), nullable=False),
    sa.Column("duyuru_taslagi", sa.Text),
    sa.Column("duyuru_kaynak", sa.String(20)),                      # zeki | elle
    sa.Column("katilimci", sa.Integer),                             # gerçekleşen (elle; CRM etkinliği ayrı)
    sa.Column("sorumlu", sa.String(120)),
    sa.Column("notlar", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
REVIEW_STATUS = sa.Table(
    "semantic_okur_review_status", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("comment_id", sa.String(40), primary_key=True),       # T-soft yorum kimliği
    sa.Column("product_id", sa.String(40)),
    sa.Column("durum", sa.String(12), nullable=False),              # cevapsiz | taslak | cevaplandi
    sa.Column("taslak", sa.Text),                                   # cevap taslağı; yorum metni ve yorumcu saklanmaz
    sa.Column("taslak_kaynak", sa.String(10)),                      # zeki | elle
    sa.Column("yazan", sa.String(120)),
    sa.Column("tarih", sa.DateTime(timezone=True)),
)
INTEREST_FLAGS = sa.Table(
    "semantic_okur_interest_flags", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kategori_id", sa.String(120), primary_key=True),
    sa.Column("ad", sa.String(300)),
    sa.Column("isaret", sa.String(12), nullable=False),             # ozel | degil | bilinmiyor
    sa.Column("olasilik", sa.Float),
    sa.Column("kaynak", sa.String(8), nullable=False),              # zeki | insan
    sa.Column("karar_veren", sa.String(120)),
    sa.Column("gerekce", sa.Text),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_okur_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(120), primary_key=True),
    sa.Column("value", sa.Text),
    sa.Column("zaman", sa.DateTime(timezone=True)),
)

SEGMENT_STATES = {"taslak": "Taslak", "onay_bekliyor": "Onay bekliyor", "onaylandi": "Onaylandı",
                  "reddedildi": "Reddedildi", "suresi_doldu": "Süresi doldu"}
EDITABLE_STATES = ("taslak", "reddedildi", "suresi_doldu", "onaylandi")
CHANNELS = {"eposta": "E-posta", "sms": "SMS", "ikisi": "E-posta ve SMS", "yok": "İleti yok (yalnız etkinlik/sayım)"}
PROGRAM_TYPES = {"okuma_kulubu": "Okuma kulübü", "imza_gunu": "İmza günü", "anket": "Anket", "cevrimici": "Çevrim içi etkinlik"}
PROGRAM_STATES = {"taslak": "Taslak", "planlandi": "Planlandı", "tamamlandi": "Tamamlandı", "iptal": "İptal"}
REVIEW_STATES = {"cevapsiz": "Cevapsız", "taslak": "Taslak hazır", "cevaplandi": "Cevaplandı"}
FLAG_STATES = {"ozel": "Özel nitelikli çağrışım var", "degil": "Çağrışım yok", "bilinmiyor": "Sınıflanmadı / emin değil"}

#: Kapalı küme seçimi (KVKK md. 6). Sıra önemli değil; eşleme metne göre.
FLAG_CHOICES = ("Evet, özel nitelikli çağrışım var", "Hayır, çağrışım yok")

_lock = threading.Lock()
_ready: set[int] = set()


class OkurError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(key)


# ------------------------------------------------------------------ ayarlar


def _conf(key: str, default: str) -> str:
    try:
        from semantic_bridge import admin as admin_mod
        v = admin_mod.conf(key)
    except Exception:  # noqa: BLE001 — testte admin ayarı yok
        v = ""
    return v if v not in (None, "") else os.environ.get(key, default)


def _conf_float(key: str, default: float) -> float:
    try:
        return float(str(_conf(key, str(default))).replace(",", "."))
    except ValueError:
        return default


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "evet", "on")


def settings() -> dict[str, Any]:
    """Modülün ayarları (ekran > ortam > varsayılan). Ölçülmemiş varsayımlar buradadır."""
    return {
        # Hukuk kararı gelene kadar kapalı: «özel nitelikli çağrışım var» işaretli ilgi alanı segmentte kullanılmaz.
        "sensitiveOpen": _truthy(_conf("OKUR_HASSAS_SEGMENT_ACIK", "0")),
        # Zeki AI «çağrışım yok» derse ancak bu olasılık ve marjın üstünde kabul edilir; altı «bilinmiyor».
        "flagProb": _conf_float("OKUR_HASSAS_ESIK", 0.90),
        "flagMargin": _conf_float("OKUR_HASSAS_MARJ", 0.50),
        "segmentMaxDays": max(1, int(_conf_float("OKUR_SEGMENT_MAX_GUN", 365))),
        "purposeMin": max(1, int(_conf_float("OKUR_AMAC_EN_AZ", 15))),
        "programRemindDays": max(0, int(_conf_float("OKUR_PROGRAM_HATIRLATMA_GUN", 7))),
        # CRM etkinlik özeti: okul/cari ziyareti tipli kayıtlar (satış ziyareti) dışarıda; tipler boşsa hepsi.
        "eventsExcludeVisits": _truthy(_conf("OKUR_ETKINLIK_ZIYARET_HARIC", "1")),
        "eventTypes": [x.strip() for x in _conf("OKUR_ETKINLIK_TIPLERI", "").replace(";", ",").split(",") if x.strip()],
        "reviewCacheSeconds": max(0, int(_conf_float("OKUR_YORUM_ONBELLEK_SN", 600))),
    }


# ------------------------------------------------------------------ yardımcılar


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _load(s: Optional[str], default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except ValueError:
        return default


def _clean(v: Any, n: int = 300) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s[:n] or None


def _day(v: Any, field: str) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v).strip()[:10]
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        raise OkurError(f"{field} tarihi YYYY-AA-GG biçiminde olmalı.") from None


def _int(v: Any) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ kişi verisi süzgeci

#: Hiçbir cevapta ve modele giden hiçbir istemde bulunmayacak alan adları (küçük harf).
PERSONAL_KEYS = frozenset({
    "fullname", "firstname", "lastname", "middlename", "name_surname", "adsoyad", "ad_soyad", "adi_soyadi", "kisi_adi",
    "emailaddress1", "emailaddress2", "emailaddress3", "email", "eposta", "e_posta", "mail",
    "mobilephone", "telephone1", "telephone2", "telephone3", "phone", "telefon", "gsm", "cep",
    "address1_line1", "address1_line2", "address1_line3", "address1_composite", "address", "adres", "acikadres",
    "tckn", "tc_kimlik", "tckimlikno", "birthdate", "new_dogumtarihi", "dogum_tarihi",
    "customername", "customeremail", "customerphone", "membername", "memberemail", "username", "usermail",
})
#: Kalıplar ortak maskeden (`zeki_text`): e-posta ve sıkı Türkiye telefon kalıbı (+90 / 0 ile başlayan 10–11 hane;
#: yıl, adet ve öneksiz kodlara dokunmaz).
EMAIL_RX = Z.EMAIL
PHONE_RX = Z.PHONE_STRICT


def _personal_key(k: str) -> bool:
    low = str(k).lower()
    return low in PERSONAL_KEYS or low.startswith("address1_") or low.startswith("address2_")


def mask_text(s: str) -> str:
    """Metindeki e-posta ve telefonu maskeler (yorum metni, model çıktısı). Ortak maske: `zeki_text.mask_personal`."""
    return Z.mask_personal(s, kinds=("email", "phone"), labels=Z.LABELS_HIDDEN, phone="strict")


def scrub(v: Any) -> Any:
    """Kişi alanlarını atar, metindeki e-posta/telefonu maskeler. H2'den ve dış kaynaktan gelen her cevap buradan geçer."""
    if isinstance(v, dict):
        # «email»/«sms» gibi adlarla gelen sayaçlar (izinli kişi sayısı) kalır; metin ve büyük sayı (telefon) atılır.
        return {k: scrub(x) for k, x in v.items()
                if not _personal_key(k) or (isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 10**9)}
    if isinstance(v, (list, tuple)):
        return [scrub(x) for x in v]
    if isinstance(v, str):
        return mask_text(v)
    return v


def assert_no_personal(text: str) -> None:
    """Modele gidecek istemde e-posta ya da telefon kalıbı varsa istem gönderilmez."""
    if EMAIL_RX.search(text) or PHONE_RX.search(text):
        raise OkurError("Zeki AI'a gidecek metinde e-posta ya da telefon bulundu; istem gönderilmedi.", 422)


# ------------------------------------------------------------------ meta


def meta_stmt(tenant: str, key: str):
    return sa.select(META.c.value, META.c.zaman).where(META.c.tenant_id == tenant, META.c.key == key)


def meta_get(engine, tenant: str, key: str, default: Any = None) -> Any:
    with engine.connect() as c:
        v = c.execute(meta_stmt(tenant, key)).scalar()
    return _load(v, default)


def meta_set(engine, tenant: str, key: str, value: Any) -> None:
    with engine.begin() as c:
        c.execute(META.delete().where(META.c.tenant_id == tenant, META.c.key == key))
        c.execute(META.insert().values(tenant_id=tenant, key=key, value=_dump(value), zaman=_now()))


# ------------------------------------------------------------------ envanter ve izin anlık görüntüsü


def save_snapshot(engine, tenant: str, inventory: dict[str, Any], consent: list[dict[str, Any]], day: Optional[str] = None) -> dict[str, int]:
    """H2'nin bugünkü sayıları. Aynı gün ikinci koşuda üzerine yazılır."""
    d = day or today().isoformat()
    rows = []
    for r in inventory.get("satirlar") or []:
        rows.append(dict(tenant_id=tenant, tarih=d, kaynak=(r.get("kaynak") or "")[:80] or "-",
                         kayit_tipi=(r.get("kayitTipi") or "")[:120], toplam=int(r.get("toplam") or 0),
                         kvkk_onayli=r.get("kvkkOnayli"), iys_onayli=r.get("iysOnayli"), eposta_izinli=r.get("epostaIzinli"),
                         sms_izinli=r.get("smsIzinli"), ilgi_alani_dolu=r.get("ilgiAlaniDolu"),
                         silinebilir=r.get("silinebilir"), cocuk_olasi=r.get("cocukOlasi")))
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:  # aynı kaynak/tip iki kez gelirse toplanır (PK)
        k = (r["kaynak"], r["kayit_tipi"])
        if k not in merged:
            merged[k] = r
            continue
        for col in ("toplam", "kvkk_onayli", "iys_onayli", "eposta_izinli", "sms_izinli", "ilgi_alani_dolu", "silinebilir", "cocuk_olasi"):
            a, b = merged[k][col], r[col]
            merged[k][col] = None if a is None and b is None else (a or 0) + (b or 0)
    cons = {}
    for x in consent:
        t = (x.get("tur") or "")[:80]
        if t:
            cons[t] = dict(tenant_id=tenant, tarih=d, tur=t, ad=(x.get("ad") or t)[:300], sayi=int(x.get("sayi") or 0))
    with engine.begin() as c:
        c.execute(INVENTORY.delete().where(INVENTORY.c.tenant_id == tenant, INVENTORY.c.tarih == d))
        c.execute(CONSENT.delete().where(CONSENT.c.tenant_id == tenant, CONSENT.c.tarih == d))
        if merged:
            c.execute(INVENTORY.insert(), list(merged.values()))
        if cons:
            c.execute(CONSENT.insert(), list(cons.values()))
    return {"envanterSatiri": len(merged), "izinTuru": len(cons)}


_SNAP_COLS = ("toplam", "kvkk_onayli", "iys_onayli", "eposta_izinli", "sms_izinli", "ilgi_alani_dolu", "silinebilir", "cocuk_olasi")
_SNAP_KEYS = {"toplam": "toplam", "kvkk_onayli": "kvkkOnayli", "iys_onayli": "iysOnayli", "eposta_izinli": "epostaIzinli",
              "sms_izinli": "smsIzinli", "ilgi_alani_dolu": "ilgiAlaniDolu", "silinebilir": "silinebilir", "cocuk_olasi": "cocukOlasi"}


def trend_stmts(tenant: str, since: Optional[str] = None, until: Optional[str] = None) -> tuple[Any, Any]:
    """Eğilim okumaları: (günlük envanter toplamları, günlük izin çelişkisi toplamı)."""
    q = sa.select(INVENTORY.c.tarih, *[sa.func.sum(getattr(INVENTORY.c, col)).label(col) for col in _SNAP_COLS]) \
        .where(INVENTORY.c.tenant_id == tenant).group_by(INVENTORY.c.tarih).order_by(INVENTORY.c.tarih)
    cq = sa.select(CONSENT.c.tarih, sa.func.sum(CONSENT.c.sayi).label("sayi")).where(CONSENT.c.tenant_id == tenant) \
        .group_by(CONSENT.c.tarih)
    if since:
        q = q.where(INVENTORY.c.tarih >= since)
        cq = cq.where(CONSENT.c.tarih >= since)
    if until:
        q = q.where(INVENTORY.c.tarih <= until)
        cq = cq.where(CONSENT.c.tarih <= until)
    return q, cq


def trend(engine, tenant: str, since: Optional[str] = None, until: Optional[str] = None) -> dict[str, Any]:
    """Günlük anlık görüntülerin toplamları ve izin çelişkisi toplamı (aylık eğilim için; tarih süzgeci isteğe bağlı)."""
    q, cq = trend_stmts(tenant, since, until)
    with engine.connect() as c:
        inv = c.execute(q).mappings().all()
        cons = {r["tarih"]: int(r["sayi"] or 0) for r in c.execute(cq).mappings()}
    points = []
    for r in inv:
        p = {"tarih": r["tarih"], **{_SNAP_KEYS[col]: (int(r[col]) if r[col] is not None else None) for col in _SNAP_COLS}}
        p["izinCeliskisi"] = cons.get(r["tarih"])
        points.append(p)
    for d, n in cons.items():  # envanteri olmayan günün izin sayısı da görünür
        if not any(p["tarih"] == d for p in points):
            points.append({"tarih": d, "izinCeliskisi": n})
    points.sort(key=lambda p: p["tarih"])
    return {"noktalar": points}


def consent_previous_stmt(tenant: str, before: str):
    """Verilen günden önceki son anlık görüntünün günü ve izin çelişkisi toplamı (tek okuma)."""
    last = sa.select(sa.func.max(CONSENT.c.tarih)).where(CONSENT.c.tenant_id == tenant, CONSENT.c.tarih < before) \
        .scalar_subquery()
    return sa.select(last.label("tarih"), sa.func.sum(CONSENT.c.sayi).label("sayi")) \
        .where(CONSENT.c.tenant_id == tenant, CONSENT.c.tarih == last)


def consent_previous(engine, tenant: str, before: str) -> Optional[int]:
    """Verilen günden önceki son anlık görüntünün izin çelişkisi toplamı."""
    with engine.connect() as c:
        r = c.execute(consent_previous_stmt(tenant, before)).first()
    if not r or not r[0]:
        return None
    return int(r[1] or 0)


# ------------------------------------------------------------------ ilgi alanı koruması (KVKK md. 6)


def flags_stmt(tenant: str):
    return sa.select(INTEREST_FLAGS).where(INTEREST_FLAGS.c.tenant_id == tenant)


def flags(engine, tenant: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(flags_stmt(tenant)).mappings().all()
    return {r["kategori_id"]: {"isaret": r["isaret"], "olasilik": r["olasilik"], "kaynak": r["kaynak"],
                               "kararVeren": r["karar_veren"], "gerekce": r["gerekce"], "zaman": _iso(r["zaman"]), "ad": r["ad"]}
            for r in rows}


def interest_view(engine, tenant: str, interests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """H2'nin ilgi alanları + bu modülün çağrışım işareti ve segmentte kullanılabilirliği."""
    fl = flags(engine, tenant)
    open_ = settings()["sensitiveOpen"]
    out = []
    for it in interests:
        f = fl.get(str(it["id"])) or {"isaret": "bilinmiyor", "kaynak": None}
        usable = f["isaret"] == "degil" or (f["isaret"] == "ozel" and open_)
        out.append({**it, "isaret": f["isaret"], "isaretAdi": FLAG_STATES[f["isaret"]], "olasilik": f.get("olasilik"),
                    "isaretKaynak": f.get("kaynak"), "kararVeren": f.get("kararVeren"), "gerekce": f.get("gerekce"),
                    "kullanilabilir": usable})
    return out


def classify_prompt(name: str) -> str:
    return (
        "Bir yayınevi okurlarını kitap ilgi alanlarına göre gruplamak istiyor. Türkiye'de KVKK 6. madde özel nitelikli "
        "kişisel veriyi sayar: din, mezhep ya da başka inanç, felsefi inanç, siyasi düşünce, dernek/vakıf/sendika üyeliği, "
        "sağlık, etnik köken, cinsel hayat, ceza mahkûmiyeti, biyometrik ve genetik veri.\n"
        f"İlgi alanı: «{name}»\n"
        "Bir kişinin bu ilgi alanıyla işaretlenmesi, o kişinin yukarıdaki özelliklerinden biri hakkında çıkarım "
        "yapılmasına yol açabilir mi? Emin değilsen «Evet» seç."
    )


def classify_interest(name: str, choose: Callable[[str, list[str]], Any], cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Tek ilgi alanı adı → {isaret, olasilik}. «Çağrışım yok» yalnız eşik üstünde; model belirsizse «bilinmiyor»."""
    cfg = cfg or settings()
    prompt = classify_prompt(name)
    assert_no_personal(prompt)
    res = choose(prompt, list(FLAG_CHOICES))
    ch = getattr(res, "choice", None)
    p = getattr(res, "probability", None)
    if ch == FLAG_CHOICES[0]:
        return {"isaret": "ozel", "olasilik": p}
    if ch == FLAG_CHOICES[1]:
        conf = getattr(res, "confident", None)
        ok = conf(cfg["flagProb"], cfg["flagMargin"]) if callable(conf) else False
        return {"isaret": "degil" if ok else "bilinmiyor", "olasilik": p}
    return {"isaret": "bilinmiyor", "olasilik": p}


def set_flag(engine, tenant: str, kategori_id: str, ad: Optional[str], isaret: str, *, olasilik: Optional[float] = None,
             kaynak: str = "zeki", karar_veren: Optional[str] = None, gerekce: Optional[str] = None) -> dict[str, Any]:
    if isaret not in FLAG_STATES:
        raise OkurError("İşaret ozel, degil ya da bilinmiyor olmalı.")
    if kaynak == "insan" and not (gerekce or "").strip():
        raise OkurError("İnsan kararında gerekçe zorunlu (KVKK kaydı).")
    kid = str(kategori_id)[:120]
    with engine.begin() as c:
        cur = c.execute(sa.select(INTEREST_FLAGS).where(INTEREST_FLAGS.c.tenant_id == tenant,
                                                        INTEREST_FLAGS.c.kategori_id == kid)).mappings().first()
        if cur and cur["kaynak"] == "insan" and kaynak == "zeki":
            return dict(cur)  # insan kararı modelle ezilmez
        c.execute(INTEREST_FLAGS.delete().where(INTEREST_FLAGS.c.tenant_id == tenant, INTEREST_FLAGS.c.kategori_id == kid))
        c.execute(INTEREST_FLAGS.insert().values(tenant_id=tenant, kategori_id=kid, ad=_clean(ad), isaret=isaret, olasilik=olasilik,
                                                 kaynak=kaynak, karar_veren=karar_veren, gerekce=_clean(gerekce, 2000), zaman=_now()))
    return {"kategoriId": kid, "isaret": isaret, "kaynak": kaynak}


def classify_missing(engine, tenant: str, interests: list[dict[str, Any]], choose, progress: Optional[Callable[[int], None]] = None) -> dict[str, int]:
    """İşareti olmayan ya da «bilinmiyor» kalmış (modelin) ilgi alanlarını sınıflar. İnsan kararına dokunmaz."""
    fl = flags(engine, tenant)
    cfg = settings()
    out = {"sorulan": 0, "ozel": 0, "degil": 0, "bilinmiyor": 0, "hata": 0}
    for it in interests:
        kid = str(it["id"])
        f = fl.get(kid)
        if f and (f["kaynak"] == "insan" or f["isaret"] != "bilinmiyor"):
            continue
        try:
            r = classify_interest(str(it.get("ad") or kid), choose, cfg)
        except Exception as e:  # noqa: BLE001 — model yoksa sonraki gece
            log.warning("okur: ilgi alanı sınıflanamadı (%s): %s", kid, e)
            out["hata"] += 1
            continue
        set_flag(engine, tenant, kid, it.get("ad"), r["isaret"], olasilik=r["olasilik"], kaynak="zeki")
        out["sorulan"] += 1
        out[r["isaret"]] += 1
        if progress:
            progress(out["sorulan"])
    return out


def rule_interest_ids(rule: Any) -> list[str]:
    """Kural JSON'unda geçen ilgi alanı kimlikleri (H2 kendi çıkarıcısını vermezse). Anahtar adı ilgi/interest/kategori/
    category/node/dugum içeren her alanın değerleri toplanır; iç içe yapı gezilir."""
    keys = re.compile(r"ilgi|interest|kategori|category|node|dugum|düğüm", re.I)
    found: list[str] = []

    def take(v: Any) -> None:
        if isinstance(v, (str, int)) and not isinstance(v, bool):
            s = str(v).strip()
            if s:
                found.append(s)
        elif isinstance(v, (list, tuple)):
            for x in v:
                take(x)
        elif isinstance(v, dict):
            for k in ("id", "value", "deger", "degerler", "values"):
                if k in v:
                    take(v[k])
            walk(v)

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            field = o.get("alan") or o.get("field")
            if isinstance(field, str) and keys.search(field):
                for k in ("deger", "degerler", "value", "values", "in"):
                    if k in o:
                        take(o[k])
            for k, v in o.items():
                if keys.search(str(k)):
                    take(v)
                else:
                    walk(v)
        elif isinstance(o, (list, tuple)):
            for x in o:
                walk(x)

    walk(rule)
    return list(dict.fromkeys(found))


def guard_rule(engine, tenant: str, interest_ids: Iterable[str], names: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Kuraldaki ilgi alanlarının çağrışım denetimi. {ok, engel: [..], uyari: [..]}."""
    fl = flags(engine, tenant)
    open_ = settings()["sensitiveOpen"]
    names = names or {}
    blocked, warn = [], []
    for kid in interest_ids:
        f = fl.get(str(kid))
        isaret = f["isaret"] if f else "bilinmiyor"
        ad = names.get(str(kid)) or (f or {}).get("ad") or str(kid)
        if isaret == "degil":
            continue
        if isaret == "ozel" and open_:
            warn.append({"id": str(kid), "ad": ad, "isaret": isaret,
                         "mesaj": f"«{ad}» özel nitelikli çağrışım taşıyor; hukuk kararıyla açık, ayrı açık rıza gerekir."})
            continue
        blocked.append({"id": str(kid), "ad": ad, "isaret": isaret,
                        "mesaj": (f"«{ad}» özel nitelikli (din/inanç vb.) çağrışım taşıyor; hukuk kararı olmadan segmentte kullanılamaz."
                                  if isaret == "ozel" else
                                  f"«{ad}» için çağrışım sınıflaması yok; önce sınıflanmalı ya da KVKK sorumlusu karar vermeli.")})
    return {"ok": not blocked, "engel": blocked, "uyari": warn}


# ------------------------------------------------------------------ segmentler


def _segment_row(r: dict[str, Any], sizes: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    out = {
        "id": r["id"], "ad": r["ad"], "kural": _load(r["kural_json"], {}), "kuralCumlesi": r["kural_cumlesi"],
        "amac": r["amac"], "kanal": r["kanal"], "kanalAdi": CHANNELS.get(r["kanal"], r["kanal"]), "sureBitis": r["sure_bitis"],
        "durum": r["durum"], "durumAdi": SEGMENT_STATES.get(r["durum"], r["durum"]), "surum": r["surum"],
        "ilgiAlanlari": _load(r["ilgi_json"], []),
        "sonOlcum": {"toplam": r["son_toplam"], "izinli": r["son_izinli"], "eposta": r["son_eposta"], "sms": r["son_sms"],
                     "zaman": _iso(r["son_olcum"])} if r["son_olcum"] else None,
        "yazan": r["yazan"], "yazmaZamani": _iso(r["yazma_zamani"]), "guncelleyen": r["guncelleyen"],
        "guncelleme": _iso(r["guncelleme"]), "gonderen": r["gonderen"], "gondermeZamani": _iso(r["gonderme_zamani"]),
        "onaylayan": r["onaylayan"], "onayZamani": _iso(r["onay_zamani"]), "onayNotu": r["onay_notu"],
    }
    if sizes is not None:
        out["olcumler"] = sizes
    return out


def segment_stmt(tenant: str, sid: str):
    return sa.select(SEGMENTS).where(SEGMENTS.c.id == sid, SEGMENTS.c.tenant_id == tenant)


def segment_sizes_stmt(sid: str):
    return sa.select(SEGMENT_SIZES).where(SEGMENT_SIZES.c.segment_id == sid).order_by(SEGMENT_SIZES.c.tarih)


def segment_programs_stmt(tenant: str, sid: str):
    return sa.select(PROGRAMS.c.id, PROGRAMS.c.ad, PROGRAMS.c.tarih, PROGRAMS.c.durum) \
        .where(PROGRAMS.c.tenant_id == tenant, PROGRAMS.c.segment_id == sid)


def segments_stmt(tenant: str, durum: str = ""):
    q = sa.select(SEGMENTS).where(SEGMENTS.c.tenant_id == tenant)
    if durum:
        q = q.where(SEGMENTS.c.durum == durum)
    return q.order_by(SEGMENTS.c.yazma_zamani.desc())


def segment_counts_stmt(tenant: str):
    return sa.select(SEGMENTS.c.durum, sa.func.count().label("sayi")).where(SEGMENTS.c.tenant_id == tenant) \
        .group_by(SEGMENTS.c.durum)


def _get_segment(c, tenant: str, sid: str) -> dict[str, Any]:
    r = c.execute(segment_stmt(tenant, sid)).mappings().first()
    if not r:
        raise OkurError("Segment bulunamadı.", 404)
    return dict(r)


def list_segments(engine, tenant: str, durum: str = "") -> dict[str, Any]:
    if durum and durum not in SEGMENT_STATES:
        raise OkurError("Bilinmeyen segment durumu.")
    with engine.connect() as c:
        rows = c.execute(segments_stmt(tenant, durum)).mappings().all()
        counts = {k: int(n) for k, n in c.execute(segment_counts_stmt(tenant)).all()}
    return {"items": [_segment_row(dict(r)) for r in rows], "total": len(rows), "durumSayilari": counts}


def segment_detail(engine, tenant: str, sid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _get_segment(c, tenant, sid)
        sizes = [{"tarih": s["tarih"], "toplam": s["toplam"], "izinli": s["izinli"], "eposta": s["eposta"], "sms": s["sms"]}
                 for s in c.execute(segment_sizes_stmt(sid)).mappings()]
        progs = [{"id": p["id"], "ad": p["ad"], "tarih": p["tarih"], "durum": p["durum"]}
                 for p in c.execute(segment_programs_stmt(tenant, sid)).mappings()]
    out = _segment_row(r, sizes)
    out["programlar"] = progs
    return out


def _segment_fields(body: dict[str, Any], partial: bool) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if not partial or "ad" in body:
        ad = _clean(body.get("ad"), 200)
        if not ad:
            raise OkurError("Segment adı zorunlu.")
        vals["ad"] = ad
    if not partial or "kural" in body:
        rule = body.get("kural")
        if not isinstance(rule, dict) or not rule:
            raise OkurError("Segment kuralı boş olamaz (okur çekirdeğinin kural biçiminde bir nesne).")
        text = _dump(rule)
        if len(text) > 20000:
            raise OkurError("Segment kuralı çok uzun.")
        if EMAIL_RX.search(text) or PHONE_RX.search(text):
            raise OkurError("Segment kuralında e-posta ya da telefon kullanılamaz; segment kişiyle değil ölçütle kurulur.")
        vals["kural_json"] = text
    if "amac" in body:
        vals["amac"] = _clean(body.get("amac"), 2000)
    if "kanal" in body or not partial:
        k = str(body.get("kanal") or "eposta")
        if k not in CHANNELS:
            raise OkurError("Kanal eposta, sms, ikisi ya da yok olmalı.")
        vals["kanal"] = k
    if "sureBitis" in body:
        vals["sure_bitis"] = _day(body.get("sureBitis"), "Süre bitiş")
    return vals


def create_segment(engine, tenant: str, user: str, body: dict[str, Any], interest_ids: list[str],
                   rule_text: Optional[str] = None) -> dict[str, Any]:
    vals = _segment_fields(body, partial=False)
    sid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(SEGMENTS.insert().values(id=sid, tenant_id=tenant, durum="taslak", surum=1, yazan=user, yazma_zamani=_now(),
                                           ilgi_json=_dump(interest_ids), kural_cumlesi=_clean(rule_text, 4000), **vals))
    return segment_detail(engine, tenant, sid)


def update_segment(engine, tenant: str, user: str, sid: str, body: dict[str, Any], interest_ids: Optional[list[str]] = None,
                   rule_text: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Taslak, reddedilmiş ya da süresi dolmuş segment düzenlenir. Onaylı segment düzenlenirse taslağa döner (yeni sürüm);
    onay bekleyen önce geri çekilmeli."""
    vals = _segment_fields(body, partial=True)
    with engine.begin() as c:
        cur = _get_segment(c, tenant, sid)
        if cur["durum"] == "onay_bekliyor":
            raise OkurError("Onay bekleyen segment düzenlenemez; önce geri çekin.", 409)
        diff = {k: {"once": cur.get(k), "sonra": v} for k, v in vals.items() if cur.get(k) != v}
        if not diff:
            return _segment_row(cur), {}
        upd = dict(vals, guncelleyen=user, guncelleme=_now())
        if "kural_json" in vals:
            upd["ilgi_json"] = _dump(interest_ids or [])
            upd["kural_cumlesi"] = _clean(rule_text, 4000)
            upd.update(son_toplam=None, son_izinli=None, son_eposta=None, son_sms=None, son_olcum=None)
        if cur["durum"] != "taslak":
            upd.update(durum="taslak", surum=int(cur["surum"] or 1) + 1, onaylayan=None, onay_zamani=None, onay_notu=None,
                       gonderen=None, gonderme_zamani=None)
            diff["durum"] = {"once": cur["durum"], "sonra": "taslak"}
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(**upd))
    return segment_detail(engine, tenant, sid), diff


def delete_segment(engine, tenant: str, sid: str) -> dict[str, Any]:
    with engine.begin() as c:
        cur = _get_segment(c, tenant, sid)
        if cur["durum"] in ("onay_bekliyor", "onaylandi"):
            raise OkurError("Onay bekleyen ya da onaylı segment silinmez; önce düzenleyip taslağa alın.", 409)
        c.execute(PROGRAMS.update().where(PROGRAMS.c.tenant_id == tenant, PROGRAMS.c.segment_id == sid).values(segment_id=None))
        c.execute(SEGMENT_SIZES.delete().where(SEGMENT_SIZES.c.segment_id == sid))
        c.execute(SEGMENTS.delete().where(SEGMENTS.c.id == sid))
    return {"ad": cur["ad"]}


def record_size(engine, tenant: str, sid: str, size: dict[str, Any], day: Optional[str] = None) -> None:
    d = day or today().isoformat()
    with engine.begin() as c:
        _get_segment(c, tenant, sid)
        c.execute(SEGMENT_SIZES.delete().where(SEGMENT_SIZES.c.segment_id == sid, SEGMENT_SIZES.c.tarih == d))
        c.execute(SEGMENT_SIZES.insert().values(segment_id=sid, tarih=d, toplam=int(size.get("toplam") or 0),
                                                izinli=size.get("izinli"), eposta=size.get("eposta"), sms=size.get("sms")))
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(
            son_toplam=int(size.get("toplam") or 0), son_izinli=size.get("izinli"), son_eposta=size.get("eposta"),
            son_sms=size.get("sms"), son_olcum=_now()))


def submit_segment(engine, tenant: str, user: str, sid: str, guard: dict[str, Any]) -> dict[str, Any]:
    cfg = settings()
    with engine.begin() as c:
        cur = _get_segment(c, tenant, sid)
        if cur["durum"] not in ("taslak", "reddedildi", "suresi_doldu"):
            raise OkurError(f"Segment «{SEGMENT_STATES.get(cur['durum'])}» durumunda; onaya gönderilemez.", 409)
        amac = (cur["amac"] or "").strip()
        if len(amac) < cfg["purposeMin"]:
            raise OkurError(f"Amaç en az {cfg['purposeMin']} karakter olmalı (ör. «Kasım okuma kulübü duyurusu»); KVKK kaydı için zorunlu.")
        if not cur["sure_bitis"]:
            raise OkurError("Süre bitiş tarihi zorunlu; segment süresiz onaylanmaz.")
        end = date.fromisoformat(cur["sure_bitis"])
        if end <= today():
            raise OkurError("Süre bitiş tarihi bugünden sonra olmalı.")
        if (end - today()).days > cfg["segmentMaxDays"]:
            raise OkurError(f"Segment en çok {cfg['segmentMaxDays']} gün için onaylanır.")
        if cur["son_olcum"] is None:
            raise OkurError("Onaya göndermeden önce segmentin büyüklüğünü ölçün (okur çekirdeği bağlı olmalı).", 409)
        if not guard.get("ok"):
            raise OkurError(" ".join(x["mesaj"] for x in guard.get("engel") or []) or "Segment KVKK denetiminden geçmedi.", 409)
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(durum="onay_bekliyor", gonderen=user, gonderme_zamani=_now(),
                                                                      onaylayan=None, onay_zamani=None, onay_notu=None))
    return segment_detail(engine, tenant, sid)


def withdraw_segment(engine, tenant: str, user: str, sid: str) -> dict[str, Any]:
    with engine.begin() as c:
        cur = _get_segment(c, tenant, sid)
        if cur["durum"] != "onay_bekliyor":
            raise OkurError("Yalnız onay bekleyen segment geri çekilir.", 409)
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(durum="taslak", guncelleyen=user, guncelleme=_now()))
    return segment_detail(engine, tenant, sid)


def decide_segment(engine, tenant: str, user: str, sid: str, approve: bool, note: Optional[str], guard: dict[str, Any]) -> dict[str, Any]:
    """KVKK onayı (iki göz): yazan ve onaya gönderen onaylayamaz; ret gerekçesiz olmaz."""
    note = _clean(note, 2000)
    with engine.begin() as c:
        cur = _get_segment(c, tenant, sid)
        if cur["durum"] != "onay_bekliyor":
            raise OkurError("Onay bekleyen segment yok.", 409)
        if user.lower() in {(cur["yazan"] or "").lower(), (cur["gonderen"] or "").lower()}:
            raise OkurError("Segmenti yazan ya da onaya gönderen onaylayamaz (iki göz).", 403)
        if not approve and not note:
            raise OkurError("Ret gerekçesi zorunlu.")
        if approve:
            if not guard.get("ok"):
                raise OkurError(" ".join(x["mesaj"] for x in guard.get("engel") or []), 409)
            if cur["sure_bitis"] and date.fromisoformat(cur["sure_bitis"]) <= today():
                raise OkurError("Segmentin süresi dolmuş; yeni tarihle yeniden gönderilmeli.", 409)
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(
            durum="onaylandi" if approve else "reddedildi", onaylayan=user, onay_zamani=_now(), onay_notu=note))
    return segment_detail(engine, tenant, sid)


def expire_segments(engine, tenant: str) -> list[dict[str, Any]]:
    d = today().isoformat()
    with engine.begin() as c:
        rows = c.execute(sa.select(SEGMENTS.c.id, SEGMENTS.c.ad).where(
            SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.durum.in_(("onaylandi", "onay_bekliyor")),
            SEGMENTS.c.sure_bitis.isnot(None), SEGMENTS.c.sure_bitis < d)).mappings().all()
        if rows:
            c.execute(SEGMENTS.update().where(SEGMENTS.c.id.in_([r["id"] for r in rows])).values(durum="suresi_doldu"))
    return [dict(r) for r in rows]


def approved_segments(engine, tenant: str) -> list[dict[str, Any]]:
    """Sözleşme: onaylı ve süresi dolmamış segmentler (M24 bülten, M35 kampanya okur). Kişi listesi yok."""
    d = today().isoformat()
    with engine.connect() as c:
        rows = c.execute(sa.select(SEGMENTS).where(SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.durum == "onaylandi",
                                                   sa.or_(SEGMENTS.c.sure_bitis.is_(None), SEGMENTS.c.sure_bitis >= d))
                         .order_by(SEGMENTS.c.onay_zamani.desc())).mappings().all()
    return [{k: v for k, v in _segment_row(dict(r)).items() if k not in ("yazan", "guncelleyen", "gonderen")} for r in rows]


# ------------------------------------------------------------------ programlar


def _program_row(r: dict[str, Any], seg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    d = r["tarih"]
    left = (date.fromisoformat(d) - today()).days if d else None
    return {"id": r["id"], "tur": r["tur"], "turAdi": PROGRAM_TYPES.get(r["tur"], r["tur"]), "ad": r["ad"], "tarih": d,
            "saat": r["saat"], "kalanGun": left, "sehir": r["sehir"], "yer": r["yer"], "kitapId": r["kitap_id"],
            "kitapAdi": r["kitap_adi"], "yazarAdi": r["yazar_adi"], "segmentId": r["segment_id"],
            "segment": seg, "durum": r["durum"], "durumAdi": PROGRAM_STATES.get(r["durum"], r["durum"]),
            "duyuruTaslagi": r["duyuru_taslagi"], "duyuruKaynak": r["duyuru_kaynak"], "katilimci": r["katilimci"],
            "sorumlu": r["sorumlu"], "notlar": r["notlar"], "olusturan": r["created_by"], "olusturma": _iso(r["created_at"]),
            "guncelleyen": r["updated_by"], "guncelleme": _iso(r["updated_at"])}


def seg_brief_stmt(tenant: str, ids: Iterable[str]):
    """Programa bağlı segmentlerin adı, durumu ve son ölçümü."""
    return sa.select(SEGMENTS.c.id, SEGMENTS.c.ad, SEGMENTS.c.durum, SEGMENTS.c.son_toplam, SEGMENTS.c.son_izinli) \
        .where(SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.id.in_(sorted({i for i in ids if i})))


def programs_stmt(tenant: str, since: str = "", until: str = "", durum: str = "", tur: str = ""):
    """Program takvimi okuması (süzgeç değerleri doğrulanmış olarak gelir)."""
    q = sa.select(PROGRAMS).where(PROGRAMS.c.tenant_id == tenant)
    if since:
        q = q.where(PROGRAMS.c.tarih >= since)
    if until:
        q = q.where(PROGRAMS.c.tarih <= until)
    if durum:
        q = q.where(PROGRAMS.c.durum == durum)
    if tur:
        q = q.where(PROGRAMS.c.tur == tur)
    return q


def program_stmt(tenant: str, pid: str):
    return sa.select(PROGRAMS).where(PROGRAMS.c.id == pid, PROGRAMS.c.tenant_id == tenant)


def _seg_brief(c, tenant: str, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    rows = c.execute(seg_brief_stmt(tenant, ids)).mappings().all()
    return {r["id"]: {"id": r["id"], "ad": r["ad"], "durum": r["durum"], "durumAdi": SEGMENT_STATES.get(r["durum"]),
                      "onayli": r["durum"] == "onaylandi", "toplam": r["son_toplam"], "izinli": r["son_izinli"]} for r in rows}


def program_filters(since: str = "", until: str = "", durum: str = "", tur: str = "") -> tuple[str, str, str, str]:
    """Takvim süzgecini doğrular: (başlangıç, bitiş, durum, tür)."""
    if durum and durum not in PROGRAM_STATES:
        raise OkurError("Bilinmeyen program durumu.")
    if tur and tur not in PROGRAM_TYPES:
        raise OkurError("Bilinmeyen program türü.")
    return (_day(since, "Başlangıç") if since else "", _day(until, "Bitiş") if until else "", durum, tur)


def list_programs(engine, tenant: str, since: str = "", until: str = "", durum: str = "", tur: str = "") -> dict[str, Any]:
    q = programs_stmt(tenant, *program_filters(since, until, durum, tur))
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(q).mappings()]
        segs = _seg_brief(c, tenant, (r["segment_id"] for r in rows))
    rows.sort(key=lambda r: (r["tarih"] is None, r["tarih"] or "", r["saat"] or ""))
    return {"items": [_program_row(r, segs.get(r["segment_id"])) for r in rows], "total": len(rows)}


def program_detail(engine, tenant: str, pid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(program_stmt(tenant, pid)).mappings().first()
        if not r:
            raise OkurError("Program bulunamadı.", 404)
        segs = _seg_brief(c, tenant, [r["segment_id"]])
    return _program_row(dict(r), segs.get(r["segment_id"]))


def _program_fields(engine, tenant: str, body: dict[str, Any], partial: bool) -> dict[str, Any]:
    v: dict[str, Any] = {}
    if not partial or "tur" in body:
        t = str(body.get("tur") or "")
        if t not in PROGRAM_TYPES:
            raise OkurError("Program türü okuma_kulubu, imza_gunu, anket ya da cevrimici olmalı.")
        v["tur"] = t
    if not partial or "ad" in body:
        ad = _clean(body.get("ad"))
        if not ad:
            raise OkurError("Program adı zorunlu.")
        v["ad"] = ad
    if "tarih" in body:
        v["tarih"] = _day(body.get("tarih"), "Program")
    if "saat" in body:
        s = str(body.get("saat") or "").strip()
        if s and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s):
            raise OkurError("Saat SS:DD biçiminde olmalı.")
        v["saat"] = s or None
    for k, col, n in (("sehir", "sehir", 80), ("yer", "yer", 300), ("kitapId", "kitap_id", 64), ("kitapAdi", "kitap_adi", 300),
                      ("yazarAdi", "yazar_adi", 300), ("sorumlu", "sorumlu", 120)):
        if k in body:
            v[col] = _clean(body.get(k), n)
    if "notlar" in body:
        v["notlar"] = _clean(body.get("notlar"), 4000)
    if "duyuruTaslagi" in body:
        txt = str(body.get("duyuruTaslagi") or "").strip()
        v["duyuru_taslagi"] = mask_text(txt)[:8000] or None
        v["duyuru_kaynak"] = "elle" if txt else None
    if "katilimci" in body:
        n = _int(body.get("katilimci"))
        if n is not None and n < 0:
            raise OkurError("Katılımcı sayısı eksi olamaz.")
        v["katilimci"] = n
    if "durum" in body or not partial:
        d = str(body.get("durum") or "taslak")
        if d not in PROGRAM_STATES:
            raise OkurError("Bilinmeyen program durumu.")
        v["durum"] = d
    if "segmentId" in body:
        sid = body.get("segmentId") or None
        if sid:
            with engine.connect() as c:
                _get_segment(c, tenant, str(sid))
        v["segment_id"] = sid
    return v


def create_program(engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    v = _program_fields(engine, tenant, body, partial=False)
    pid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(PROGRAMS.insert().values(id=pid, tenant_id=tenant, created_by=user, created_at=_now(), **v))
    return program_detail(engine, tenant, pid)


def update_program(engine, tenant: str, user: str, pid: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    v = _program_fields(engine, tenant, body, partial=True)
    with engine.begin() as c:
        cur = c.execute(sa.select(PROGRAMS).where(PROGRAMS.c.id == pid, PROGRAMS.c.tenant_id == tenant)).mappings().first()
        if not cur:
            raise OkurError("Program bulunamadı.", 404)
        diff = {k: {"once": cur[k], "sonra": x} for k, x in v.items() if cur[k] != x and k != "duyuru_taslagi"}
        if "duyuru_taslagi" in v and cur["duyuru_taslagi"] != v["duyuru_taslagi"]:
            diff["duyuru_taslagi"] = "değişti"
        if diff:
            c.execute(PROGRAMS.update().where(PROGRAMS.c.id == pid).values(updated_by=user, updated_at=_now(), **v))
    return program_detail(engine, tenant, pid), diff


def delete_program(engine, tenant: str, pid: str) -> dict[str, Any]:
    with engine.begin() as c:
        cur = c.execute(sa.select(PROGRAMS.c.ad).where(PROGRAMS.c.id == pid, PROGRAMS.c.tenant_id == tenant)).scalar()
        if cur is None:
            raise OkurError("Program bulunamadı.", 404)
        c.execute(PROGRAMS.delete().where(PROGRAMS.c.id == pid))
    return {"ad": cur}


def set_announcement(engine, tenant: str, user: str, pid: str, text: str) -> dict[str, Any]:
    with engine.begin() as c:
        c.execute(PROGRAMS.update().where(PROGRAMS.c.id == pid, PROGRAMS.c.tenant_id == tenant).values(
            duyuru_taslagi=mask_text(text)[:8000], duyuru_kaynak="zeki", updated_by=user, updated_at=_now()))
    return program_detail(engine, tenant, pid)


def announcement_messages(p: dict[str, Any], book: Optional[dict[str, Any]], segment: Optional[dict[str, Any]]) -> list[dict[str, str]]:
    """Duyuru taslağı istemi. Kişi verisi yok: program alanları, kitabın spotu ve segmentin amacı (kişi listesi değil)."""
    facts = [f"Etkinlik türü: {PROGRAM_TYPES.get(p['tur'], p['tur'])}", f"Etkinlik adı: {p['ad']}"]
    if p.get("tarih"):
        facts.append(f"Tarih: {p['tarih']}" + (f" saat {p['saat']}" if p.get("saat") else ""))
    if p.get("sehir") or p.get("yer"):
        facts.append(f"Yer: {', '.join(x for x in (p.get('yer'), p.get('sehir')) if x)}")
    if p.get("kitapAdi"):
        facts.append(f"Kitap: {p['kitapAdi']}")
    if p.get("yazarAdi"):
        facts.append(f"Yazar: {p['yazarAdi']}")
    if book and book.get("spot"):
        facts.append(f"Kitabın tanıtım metni: {book['spot'][:1500]}")
    if segment and segment.get("amac"):
        facts.append(f"Duyurunun amacı: {segment['amac'][:500]}")
    user = ("Aşağıdaki bilgilerle Timaş Yayınları okurlarına gidecek kısa bir duyuru/davet metni taslağı yaz. "
            "Başlık satırı, 2–3 kısa paragraf ve katılım çağrısı olsun. Yalnız verilen bilgileri kullan; tarih, yer, "
            "ücret, hediye ya da indirim uydurma. Okurdan kişisel bilgi isteme. Metnin sonunda Timaş Yayınları adı geçsin.\n\n"
            + "\n".join(facts))
    assert_no_personal(user)
    return [{"role": "system", "content": "Sen Timaş Yayınları'nın okur ilişkileri ekibi için Türkçe metin taslağı hazırlayan "
                                          "yardımcısın. Sıcak, sade ve abartısız yazarsın."},
            {"role": "user", "content": user}]


def due_programs_stmt(tenant: str, days: int):
    """Bugünden `days` gün sonrasına kadar taslak ya da planlanmış programlar."""
    d0, d1 = today().isoformat(), (today() + timedelta(days=days)).isoformat()
    return sa.select(PROGRAMS).where(PROGRAMS.c.tenant_id == tenant, PROGRAMS.c.durum.in_(("taslak", "planlandi")),
                                     PROGRAMS.c.tarih >= d0, PROGRAMS.c.tarih <= d1).order_by(PROGRAMS.c.tarih)


def due_programs(engine, tenant: str, days: int) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(due_programs_stmt(tenant, days)).mappings().all()
    return [_program_row(dict(r)) for r in rows]


# ------------------------------------------------------------------ yorumlar


def review_status_stmt(tenant: str):
    return sa.select(REVIEW_STATUS).where(REVIEW_STATUS.c.tenant_id == tenant)


def review_status(engine, tenant: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(review_status_stmt(tenant)).mappings().all()
    return {r["comment_id"]: {"durum": r["durum"], "taslak": r["taslak"], "taslakKaynak": r["taslak_kaynak"],
                              "yazan": r["yazan"], "tarih": _iso(r["tarih"])} for r in rows}


def merge_reviews(comments: list[dict[str, Any]], status: dict[str, dict[str, Any]], names: dict[str, str]) -> list[dict[str, Any]]:
    """T-soft yorumları (anlık, kişisel alansız) + portal durumu. Sitede cevabı olan yorum «cevaplandı» sayılır."""
    out = []
    for cm in comments:
        st = status.get(cm["id"]) or {}
        durum = "cevaplandi" if cm.get("sitedeCevap") else (st.get("durum") or "cevapsiz")
        out.append({**cm, "urun": names.get(cm.get("productId") or "") or cm.get("urun"), "durum": durum,
                    "durumAdi": REVIEW_STATES[durum], "taslak": st.get("taslak"), "taslakKaynak": st.get("taslakKaynak"),
                    "taslakYazan": st.get("yazan"), "taslakTarih": st.get("tarih")})
    out.sort(key=lambda r: str(r.get("tarih") or ""), reverse=True)  # en yeni üstte
    return out


def review_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    out = {k: 0 for k in REVIEW_STATES}
    for r in items:
        out[r["durum"]] = out.get(r["durum"], 0) + 1
    out["toplam"] = len(items)
    return out


def set_review(engine, tenant: str, user: str, comment_id: str, product_id: Optional[str], durum: str,
               taslak: Optional[str] = None, kaynak: Optional[str] = None) -> dict[str, Any]:
    if durum not in REVIEW_STATES:
        raise OkurError("Durum cevapsiz, taslak ya da cevaplandi olmalı.")
    cid = str(comment_id)[:40]
    with engine.begin() as c:
        cur = c.execute(sa.select(REVIEW_STATUS).where(REVIEW_STATUS.c.tenant_id == tenant, REVIEW_STATUS.c.comment_id == cid)).mappings().first()
        text = mask_text(taslak)[:4000] if taslak is not None else (cur["taslak"] if cur else None)
        src = kaynak or (cur["taslak_kaynak"] if cur else None)
        c.execute(REVIEW_STATUS.delete().where(REVIEW_STATUS.c.tenant_id == tenant, REVIEW_STATUS.c.comment_id == cid))
        c.execute(REVIEW_STATUS.insert().values(tenant_id=tenant, comment_id=cid, product_id=(product_id or (cur["product_id"] if cur else None)),
                                                durum=durum, taslak=text, taslak_kaynak=src, yazan=user, tarih=_now()))
    return {"id": cid, "durum": durum, "durumAdi": REVIEW_STATES[durum], "taslak": text, "taslakKaynak": src}


def review_messages(product: Optional[str], rate: Optional[int], text: str, title: Optional[str] = None) -> list[dict[str, str]]:
    """Yorum cevabı istemi. Yorumcu adı okunmaz; metindeki e-posta/telefon maskelenmiştir."""
    body = mask_text(text or "")[:3000]
    parts = [f"Kitap: {product or 'bilinmiyor'}", f"Puan: {rate if rate else 'verilmemiş'} / 5"]
    if title:
        parts.append(f"Yorum başlığı: {mask_text(title)[:200]}")
    parts.append(f"Yorum: {body}")
    user = ("Timaş Yayınları adına bu okur yorumuna sitede yayımlanacak kısa (2–4 cümle), nazik bir cevap taslağı yaz. "
            "Okura adıyla hitap etme. Olumsuz yorumda anlayış göster, özür dile; iade, indirim, hediye ya da yeni baskı "
            "sözü verme, tarih verme. Kişisel bilgi isteme; gerekiyorsa sitedeki iletişim kanalına yönlendir. Yalnız cevap "
            "metnini yaz.\n\n" + "\n".join(parts))
    assert_no_personal(user)
    return [{"role": "system", "content": "Sen Timaş Yayınları'nın okur ilişkileri ekibi için Türkçe cevap taslağı hazırlayan yardımcısın."},
            {"role": "user", "content": user}]


def clean_model_text(text: str) -> str:
    """Model çıktısı: e-posta/telefon maskelenir, düşünme bloğu ve baş/son tırnak atılır."""
    t = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S).strip().strip('"“”').strip()
    return mask_text(t)


# ------------------------------------------------------------------ gece özeti


def summary_text(pending: list[dict[str, Any]], consent_now: Optional[int], consent_before: Optional[int],
                 new_reviews: int, unanswered: Optional[int], programs: list[dict[str, Any]], expired: list[dict[str, Any]],
                 link: str) -> str:
    lines = ["Okur topluluğu günlük özeti (yalnız sayılar; kişi listesi yoktur).", ""]
    if pending:
        lines.append(f"Onay bekleyen segment: {len(pending)}")
        lines += [f"  - {s['ad']} (gönderen {s.get('gonderen') or '-'})" for s in pending]
    if consent_now is not None and consent_before is not None and consent_now > consent_before:
        lines.append(f"İzin çelişkisi arttı: {consent_before} → {consent_now}. Düzeltme CRM'de yapılır.")
    if new_reviews:
        lines.append(f"Yeni cevapsız okur yorumu: {new_reviews} (toplam cevapsız {unanswered if unanswered is not None else '-'})")
    if programs:
        lines.append("Yaklaşan programlar:")
        lines += [f"  - {p['tarih']} {p['turAdi']}: {p['ad']}" for p in programs]
    if expired:
        lines.append("Süresi dolan segment: " + ", ".join(s["ad"] for s in expired))
    if link:
        lines += ["", link]
    lines += ["", "Bu e-posta yalnız iç ekibe gider; portal okura ileti göndermez."]
    return "\n".join(lines)


def pending_segments(engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(SEGMENTS.c.id, SEGMENTS.c.ad, SEGMENTS.c.gonderen).where(
            SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.durum == "onay_bekliyor")).mappings().all()
    return [dict(r) for r in rows]


def measurable_segments(engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(SEGMENTS.c.id, SEGMENTS.c.ad, SEGMENTS.c.kural_json).where(
            SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.durum.in_(("onay_bekliyor", "onaylandi")))).mappings().all()
    return [{"id": r["id"], "ad": r["ad"], "kural": _load(r["kural_json"], {})} for r in rows]


def meta() -> dict[str, Any]:
    cfg = settings()
    return {"segmentDurumlari": SEGMENT_STATES, "kanallar": CHANNELS, "programTurleri": PROGRAM_TYPES,
            "programDurumlari": PROGRAM_STATES, "yorumDurumlari": REVIEW_STATES, "isaretler": FLAG_STATES,
            "ayarlar": {k: cfg[k] for k in ("sensitiveOpen", "flagProb", "segmentMaxDays", "purposeMin", "programRemindDays",
                                            "eventsExcludeVisits", "eventTypes")}}
