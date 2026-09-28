"""M42 kanal paketi depo katmanı: tablolar (`semantic_channel_*`), ayarlar, önbellek ve durum kayıtları.

Kalıcı iş kayıtları (kullanıcının onayı, öneri kararı, yüklenen panel dosyası) ile yeniden okunabilen önbellek (Logo/CRM
özetleri) ayrı tablolardadır. Önbellek her okumada yıl bazında silinip yeniden yazılır; iş kayıtlarına dokunulmaz.

Analizdeki `semantic_channel_scorecards` (platform × ay) yerine önbellek **cari (grup) × ay** tutulur ve platform okuma
anında eşlemeyle toplanır: eşleme onaylanınca karne yeniden okuma beklemeden değişir ve «platform toplamı = eşlenmiş
carilerin toplamı» her zaman birebir tutar (kabul 7).
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.channels.sources import BOOK_METRICS, METRICS

_md = sa.MetaData()


def _metric_cols() -> list[sa.Column]:
    return [sa.Column(k, sa.Float, nullable=False, default=0.0) for k in METRICS]


#: Cari ↔ platform eşlemesi (M40/M41 de kullanır) + eşleme ekranının kart bilgisi. Bir satır = bir Logo carisi.
ACCOUNTS = sa.Table(
    "semantic_channel_accounts", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("logo_cari_kodu", sa.String(80), primary_key=True),
    sa.Column("platform", sa.String(30)),                     # onaylı ya da aday platform; None = henüz yok
    sa.Column("durum", sa.String(12), nullable=False),        # bekliyor | aday | onayli
    sa.Column("yontem", sa.String(8)),                        # ad | zeki | elle
    sa.Column("olasilik", sa.Float),
    sa.Column("aday_json", sa.Text),                          # Zeki AI seçimi ve olasılıkları (kanıt)
    sa.Column("aday_zamani", sa.DateTime(timezone=True)),
    sa.Column("unvan", sa.String(300)),
    sa.Column("kanal", sa.String(60)),                        # Logo özel kod 2
    sa.Column("logo_ref", sa.Integer),
    sa.Column("logo_firma", sa.String(3)),
    sa.Column("crm_account_id", sa.String(60)),
    sa.Column("crm_ad", sa.String(300)),
    sa.Column("crm_kanal", sa.String(40)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_tarihi", sa.DateTime(timezone=True)),
    sa.Column("notu", sa.String(500)),
    sa.Column("guncellendi", sa.DateTime(timezone=True)),
)

#: Öneriler: iskonto, stok payı, D2C set/sadakat (M40/M41: vitrin, sponsorlu, metin, pazar). Onay portal kaydıdır.
SUGGESTIONS = sa.Table(
    "semantic_channel_suggestions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("platform", sa.String(30), nullable=False),
    sa.Column("tur", sa.String(20), nullable=False),
    sa.Column("baslik", sa.String(300), nullable=False),
    sa.Column("payload_json", sa.Text, nullable=False),
    sa.Column("model_gerekce", sa.Text),
    sa.Column("durum", sa.String(10), nullable=False),         # taslak | onayli | red
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("karar_veren", sa.String(120)),
    sa.Column("karar_tarihi", sa.DateTime(timezone=True)),
    sa.Column("karar_notu", sa.String(1000)),
)

#: Önbellek: kanal (özel kod 2) × ay, bütün cariler — kanallar arası kıyas ve şirket toplamı.
KANAL_MONTHS = sa.Table(
    "semantic_channel_kanal_months", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yil", sa.Integer, primary_key=True),
    sa.Column("ay", sa.Integer, primary_key=True),
    sa.Column("kanal", sa.String(60), primary_key=True),
    *_metric_cols(),
)

#: Önbellek: grup (cari kodu ya da '#K:<kanal kodu>') × ay, kapsamdaki cariler.
CARI_MONTHS = sa.Table(
    "semantic_channel_cari_months", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yil", sa.Integer, primary_key=True),
    sa.Column("ay", sa.Integer, primary_key=True),
    sa.Column("grup", sa.String(80), primary_key=True),
    *_metric_cols(),
)

#: Önbellek: grup × kitap × ay.
BOOK_MONTHS = sa.Table(
    "semantic_channel_book_months", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yil", sa.Integer, primary_key=True),
    sa.Column("ay", sa.Integer, primary_key=True),
    sa.Column("grup", sa.String(80), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    *[sa.Column(k, sa.Float, nullable=False, default=0.0) for k in BOOK_METRICS],
)

BOOKS = sa.Table(
    "semantic_channel_books", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("ad", sa.String(400)),
)

BARCODES = sa.Table(
    "semantic_channel_barcodes", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("barkod", sa.String(40), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), nullable=False),
)

#: CRM satış hedefi (bölge × ay, adet) — yıl başına.
TARGETS = sa.Table(
    "semantic_channel_crm_targets", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yil", sa.Integer, primary_key=True),
    sa.Column("bolge", sa.String(20), primary_key=True),
    sa.Column("bolge_ad", sa.String(120)),
    sa.Column("satir", sa.Integer, nullable=False),
    sa.Column("toplam", sa.Float, nullable=False),
    sa.Column("aylar_json", sa.Text, nullable=False),
)

SETTINGS = sa.Table(
    "semantic_channel_settings", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("anahtar", sa.String(120), primary_key=True),
    sa.Column("deger", sa.Text, nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncellendi", sa.DateTime(timezone=True)),
)

META = sa.Table(
    "semantic_channel_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

#: Panel dışa aktarımı yüklemeleri (kanalın son tüketiciye sattığı adet ve kanal stoğu; kişisel veri yok).
IMPORTS = sa.Table(
    "semantic_channel_imports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("platform", sa.String(30), nullable=False),
    sa.Column("tur", sa.String(20), nullable=False),           # sell-through
    sa.Column("dosya_adi", sa.String(300)),
    sa.Column("donem_bas", sa.String(10)),
    sa.Column("donem_bit", sa.String(10)),
    sa.Column("satir", sa.Integer, nullable=False),
    sa.Column("eslesen", sa.Integer, nullable=False),
    sa.Column("atlanan_kolonlar", sa.Text),                    # içeri alınmayan (kişisel olabilecek) kolon adları
    sa.Column("yukleyen", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
    sa.Column("hata", sa.Text),
)

IMPORT_ROWS = sa.Table(
    "semantic_channel_import_rows", _md,
    sa.Column("import_id", sa.String(32), primary_key=True),
    sa.Column("sira", sa.Integer, primary_key=True),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("barkod", sa.String(40)),
    sa.Column("ad", sa.String(400)),
    sa.Column("adet", sa.Float),
    sa.Column("tutar", sa.Float),
    sa.Column("kanal_stok", sa.Float),
)

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(key)


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def jload(s: Optional[str], default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except ValueError:
        return default


def new_id() -> str:
    return uuid.uuid4().hex


# ------------------------------------------------------------------ meta ve ayarlar


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    if not row:
        return {}
    out = jload(row.value_json, {})
    out["_at"] = iso(row.updated_at)
    return out


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    body = json.dumps({k: v for k, v in value.items() if k != "_at"}, ensure_ascii=False, default=str)
    with engine.begin() as c:
        c.execute(META.delete().where(META.c.tenant_id == tenant, META.c.key == key))
        c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=body, updated_at=now()))


def meta_like(engine: sa.engine.Engine, tenant: str, prefix: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(META).where(META.c.tenant_id == tenant, META.c.key.like(prefix + "%"))).all()
    return {r.key: {**jload(r.value_json, {}), "_at": iso(r.updated_at)} for r in rows}


def settings_all(engine: sa.engine.Engine, tenant: str) -> dict[str, str]:
    with engine.connect() as c:
        return {r.anahtar: r.deger for r in c.execute(sa.select(SETTINGS).where(SETTINGS.c.tenant_id == tenant)).all()}


def setting_set(engine: sa.engine.Engine, tenant: str, key: str, value: Optional[str], user: str) -> None:
    with engine.begin() as c:
        c.execute(SETTINGS.delete().where(SETTINGS.c.tenant_id == tenant, SETTINGS.c.anahtar == key))
        if value is not None and value != "":
            c.execute(SETTINGS.insert().values(tenant_id=tenant, anahtar=key, deger=str(value), guncelleyen=user, guncellendi=now()))


# ------------------------------------------------------------------ önbellek yazımı


def replace_year(engine: sa.engine.Engine, tenant: str, table: sa.Table, year: int, rows: list[dict[str, Any]]) -> None:
    """Bir yılın önbelleğini tek işlemde değiştirir (okuma yarıda kalırsa eski veri durur)."""
    with engine.begin() as c:
        c.execute(table.delete().where(table.c.tenant_id == tenant, table.c.yil == year))
        for i in range(0, len(rows), 5000):
            c.execute(table.insert(), [{**r, "tenant_id": tenant} for r in rows[i:i + 5000]])


def replace_all(engine: sa.engine.Engine, tenant: str, table: sa.Table, rows: list[dict[str, Any]]) -> None:
    with engine.begin() as c:
        c.execute(table.delete().where(table.c.tenant_id == tenant))
        for i in range(0, len(rows), 5000):
            c.execute(table.insert(), [{**r, "tenant_id": tenant} for r in rows[i:i + 5000]])


def upsert_books(engine: sa.engine.Engine, tenant: str, names: dict[str, str]) -> None:
    if not names:
        return
    with engine.begin() as c:
        have = {r[0] for r in c.execute(sa.select(BOOKS.c.stok_kodu).where(BOOKS.c.tenant_id == tenant)).all()}
        new = [{"tenant_id": tenant, "stok_kodu": k, "ad": v} for k, v in names.items() if k not in have]
        for i in range(0, len(new), 5000):
            c.execute(BOOKS.insert(), new[i:i + 5000])
        for k, v in names.items():
            if k in have:
                c.execute(BOOKS.update().where(BOOKS.c.tenant_id == tenant, BOOKS.c.stok_kodu == k).values(ad=v))


def book_names(engine: sa.engine.Engine, tenant: str, codes: Optional[Iterable[str]] = None) -> dict[str, str]:
    stmt = sa.select(BOOKS.c.stok_kodu, BOOKS.c.ad).where(BOOKS.c.tenant_id == tenant)
    want = list(codes) if codes is not None else None
    if want is not None:
        if not want:
            return {}
        out: dict[str, str] = {}
        with engine.connect() as c:
            for i in range(0, len(want), 900):
                for k, v in c.execute(stmt.where(BOOKS.c.stok_kodu.in_(want[i:i + 900]))).all():
                    out[k] = v or ""
        return out
    with engine.connect() as c:
        return {k: v or "" for k, v in c.execute(stmt).all()}


# ------------------------------------------------------------------ cari kartları (eşleme tablosu)


def sync_accounts(engine: sa.engine.Engine, tenant: str, cards: list[dict[str, Any]], crm: dict[int, dict[str, Any]]) -> dict[str, int]:
    """Logo cari kartlarını eşleme tablosuna işler: yeni cari «bekliyor» olarak eklenir, var olanın kart bilgisi güncellenir;
    eşleme (platform/durum/onay) korunur."""
    added = updated = 0
    with engine.begin() as c:
        have = {r.logo_cari_kodu: r for r in c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant)).all()}
        for card in cards:
            info = crm.get(card.get("ref")) if card.get("ref") is not None else None
            vals = {"unvan": card.get("unvan"), "kanal": card.get("kanal"), "logo_ref": card.get("ref"), "logo_firma": card.get("firma"),
                    "crm_account_id": (info or {}).get("crm_id"), "crm_ad": ((info or {}).get("ad") or None),
                    "crm_kanal": str((info or {}).get("firma_kanal")) if (info or {}).get("firma_kanal") is not None else None}
            if card["cari_kodu"] in have:
                c.execute(ACCOUNTS.update().where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.logo_cari_kodu == card["cari_kodu"])
                          .values(**vals, guncellendi=now()))
                updated += 1
            else:
                c.execute(ACCOUNTS.insert().values(tenant_id=tenant, logo_cari_kodu=card["cari_kodu"], durum="bekliyor", guncellendi=now(), **vals))
                added += 1
    return {"yeni": added, "guncellenen": updated}


def accounts(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant).order_by(ACCOUNTS.c.logo_cari_kodu)).all()
    return [account_view(r) for r in rows]


def account_view(r: Any) -> dict[str, Any]:
    return {"cariKodu": r.logo_cari_kodu, "platform": r.platform, "durum": r.durum, "yontem": r.yontem, "olasilik": r.olasilik,
            "aday": jload(r.aday_json, None), "adayZamani": iso(r.aday_zamani), "unvan": r.unvan, "kanal": r.kanal,
            "logoRef": r.logo_ref, "logoFirma": r.logo_firma, "crmId": r.crm_account_id, "crmAd": r.crm_ad, "crmKanal": r.crm_kanal,
            "onaylayan": r.onaylayan, "onayTarihi": iso(r.onay_tarihi), "not": r.notu}


def account_get(engine: sa.engine.Engine, tenant: str, code: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.logo_cari_kodu == code)).first()
    return account_view(r) if r else None


def approved_map(engine: sa.engine.Engine, tenant: str) -> dict[str, str]:
    """Onaylı cari → platform ('degil' dahil)."""
    with engine.connect() as c:
        return {r.logo_cari_kodu: r.platform for r in c.execute(
            sa.select(ACCOUNTS.c.logo_cari_kodu, ACCOUNTS.c.platform)
            .where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.durum == "onayli", ACCOUNTS.c.platform.isnot(None))).all()}


# ------------------------------------------------------------------ öneriler


def suggestion_view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "platform": r.platform, "tur": r.tur, "baslik": r.baslik, "payload": jload(r.payload_json, {}),
            "gerekce": r.model_gerekce, "durum": r.durum, "olusturan": r.olusturan, "olusturma": iso(r.olusturma),
            "kararVeren": r.karar_veren, "kararTarihi": iso(r.karar_tarihi), "kararNotu": r.karar_notu}


def suggestion_add(engine: sa.engine.Engine, tenant: str, user: str, platform: str, tur: str, baslik: str,
                   payload: dict[str, Any], gerekce: Optional[str]) -> dict[str, Any]:
    sid = new_id()
    with engine.begin() as c:
        c.execute(SUGGESTIONS.insert().values(id=sid, tenant_id=tenant, platform=platform, tur=tur, baslik=baslik[:300],
                                              payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                                              model_gerekce=gerekce, durum="taslak", olusturan=user, olusturma=now()))
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.id == sid)).first()
    return suggestion_view(r)


def suggestions(engine: sa.engine.Engine, tenant: str, *, platform: str = "", tur: str = "", durum: str = "") -> list[dict[str, Any]]:
    stmt = sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant)
    if platform:
        stmt = stmt.where(SUGGESTIONS.c.platform == platform)
    if tur:
        stmt = stmt.where(SUGGESTIONS.c.tur == tur)
    if durum:
        stmt = stmt.where(SUGGESTIONS.c.durum == durum)
    with engine.connect() as c:
        return [suggestion_view(r) for r in c.execute(stmt.order_by(SUGGESTIONS.c.olusturma.desc())).all()]


def suggestion_get(engine: sa.engine.Engine, tenant: str, sid: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.id == sid)).first()
    return suggestion_view(r) if r else None


def suggestion_decide(engine: sa.engine.Engine, tenant: str, sid: str, user: str, durum: str, note: Optional[str]) -> None:
    with engine.begin() as c:
        c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.id == sid)
                  .values(durum=durum, karar_veren=user, karar_tarihi=now(), karar_notu=(note or None)))
