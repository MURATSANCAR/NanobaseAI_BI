"""M43 Depo ve stok: portalın kendi tabloları (`semantic_stock_*`, katalog veritabanı, ilk kullanımda kurulur).

Logo `INVDEF` (asgari/azami seviye) ve CRM'e yazılmaz; onaylanan eşik ve öneri kararı burada durur. Her yazma
`semantic_audit`'e düşer (uç katmanı yazar: `stock_threshold`, `stock_suggestion`, `stock_note`, `stock_run`).

- `semantic_stock_thresholds`: kitap (ve isteğe bağlı depo) başına güvenlik günü / yeniden sipariş adedi; taslak →
  onaylı | red, yeni onay eskisini arşive alır.
- `semantic_stock_suggestions`: gece üretilen öneri (bitecek → M12/M11, fazla stok → M35/M17 kampanya ya da M53 set).
  Diğer modüller `GET /api/v1/stock/suggestions?hedef=M12` ile okur (bağlantı noktası; onların tablosuna yazılmaz).
- `semantic_stock_snapshots`: gece fotoğrafı (gün × kitap: Logo bakiyesi, CRM raf, satış hızı). Satır sınırı yok.
- `semantic_stock_notes`: sayım/düzeltme notu.
- `semantic_stock_meta`: son koşu özeti, aktarım mesajı sınıfları (Zeki AI), model sırasında kalan iş.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

import sqlalchemy as sa

_md = sa.MetaData()

THRESHOLDS = sa.Table(
    "semantic_stock_thresholds", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(60), nullable=False, index=True),
    sa.Column("depo_no", sa.String(40)),                       # boş = bütün depolar
    sa.Column("guvenlik_gun", sa.Integer, nullable=False),
    sa.Column("yeniden_siparis_adet", sa.Float),
    sa.Column("kaynak", sa.String(8), nullable=False),         # oneri | elle
    sa.Column("durum", sa.String(8), nullable=False),          # taslak | onayli | red | arsiv
    sa.Column("gerekce", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_tarihi", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
SUGGESTIONS = sa.Table(
    "semantic_stock_suggestions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(8), nullable=False),            # bitecek | fazla | raf | esik
    sa.Column("stok_kodu", sa.String(60), nullable=False, index=True),
    sa.Column("payload_json", sa.Text, nullable=False),
    sa.Column("model_gerekce", sa.Text),
    sa.Column("durum", sa.String(10), nullable=False),         # acik | kabul | red | gecersiz
    sa.Column("karar_veren", sa.String(120)),
    sa.Column("karar_tarihi", sa.DateTime(timezone=True)),
    sa.Column("karar_notu", sa.Text),
    sa.Column("hedef_modul", sa.String(8)),                    # M11 | M12 | M17 | M35 | M53
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
SNAPSHOTS = sa.Table(
    "semantic_stock_snapshots", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("gun", sa.String(10), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("logo_bakiye", sa.Float),
    sa.Column("crm_raf", sa.Float),
    sa.Column("satis_hizi", sa.Float),
)
NOTES = sa.Table(
    "semantic_stock_notes", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(60), nullable=False, index=True),
    sa.Column("not_metni", sa.Text, nullable=False),
    sa.Column("yazan", sa.String(120), nullable=False),
    sa.Column("yazan_ad", sa.String(200)),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_stock_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

THRESHOLD_STATES = {"taslak": "Taslak", "onayli": "Onaylı", "red": "Reddedildi", "arsiv": "Arşiv"}
SUGGESTION_KINDS = {"bitecek": "Bitecek — baskı tekrarı değerlendirilsin", "fazla": "Fazla / ölü stok — eritme önerisi",
                    "raf": "Raf yerleşimi", "esik": "Güvenlik stoku"}
SUGGESTION_STATES = {"acik": "Karar bekliyor", "kabul": "Kabul edildi", "red": "Reddedildi", "gecersiz": "Koşul kalktı"}
TARGETS = {"M11": "Baskı tekrarı (M11)", "M12": "Üretim (M12)", "M17": "Backlist pazarlama (M17)",
           "M35": "E-ticaret kampanyası (M35)", "M53": "Set ve hediye (M53)"}
PAGE_SIZE = 50
_CODE = re.compile(r"^[0-9A-Za-z._\-/ ]{1,60}$")

_ready: set[int] = set()
_lock = threading.Lock()


class StockError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _j(v: Optional[str], default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def text(v: Any, limit: int) -> Optional[str]:
    s = " ".join(str(v or "").split())
    return s[:limit] or None


def code(v: Any) -> str:
    s = str(v or "").strip()
    if not _CODE.match(s):
        raise StockError("Stok kodu geçersiz.")
    return s


def _int(v: Any, label: str, lo: int, hi: int) -> int:
    try:
        n = float(str(v).replace(",", ".")) if v not in (None, "") else None
    except (TypeError, ValueError):
        n = None
    if n is None or n != int(n):
        raise StockError(f"{label} tam sayı olmalı.")
    if not lo <= n <= hi:
        raise StockError(f"{label} {lo}–{hi} arasında olmalı.")
    return int(n)


def _qty(v: Any, label: str) -> Optional[float]:
    if v in (None, ""):
        return None
    t = str(v).strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):   # Türkçe yazım: 1.500 ya da 1.500,0
        t = t.replace(".", "")
    try:
        n = float(t.replace(",", "."))
    except (TypeError, ValueError):
        raise StockError(f"{label} sayı olmalı.") from None
    if n != n or n < 0 or n != int(n):
        raise StockError(f"{label} eksi olmayan tam sayı olmalı.")
    return float(int(n))


# ------------------------------------------------------------------ meta


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return {**_j(row.value_json, {}), "_at": iso(row.updated_at)} if row else {}


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    t = now()
    with engine.begin() as c:
        cond = (META.c.tenant_id == tenant, META.c.key == key)
        value = {k: v for k, v in value.items() if k != "_at"}
        if c.execute(sa.select(META.c.key).where(*cond)).first():
            c.execute(META.update().where(*cond).values(value_json=dump(value), updated_at=t))
        else:
            c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=dump(value), updated_at=t))


# ------------------------------------------------------------------ eşikler


def _threshold(r: Any) -> dict[str, Any]:
    return {"id": r.id, "stokKodu": r.stok_kodu, "depoNo": r.depo_no, "guvenlikGun": r.guvenlik_gun,
            "yenidenSiparisAdet": r.yeniden_siparis_adet, "kaynak": r.kaynak, "durum": r.durum,
            "durumEtiket": THRESHOLD_STATES.get(r.durum, r.durum), "gerekce": r.gerekce, "olusturan": r.olusturan,
            "onaylayan": r.onaylayan, "onayTarihi": iso(r.onay_tarihi), "olusturma": iso(r.created_at)}


def thresholds(engine: sa.engine.Engine, tenant: str, durum: str = "", codes: Optional[Iterable[str]] = None) -> list[dict[str, Any]]:
    q = sa.select(THRESHOLDS).where(THRESHOLDS.c.tenant_id == tenant)
    if durum:
        q = q.where(THRESHOLDS.c.durum == durum)
    if codes is not None:
        codes = list(codes)
        if not codes:
            return []
        q = q.where(THRESHOLDS.c.stok_kodu.in_(codes))
    with engine.connect() as c:
        rows = c.execute(q.order_by(THRESHOLDS.c.created_at.desc())).all()
    return [_threshold(r) for r in rows]


def approved_thresholds(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    """Kitap başına yürürlükteki (onaylı, depo belirtilmemiş) eşik. Depo bazlı eşik ayrıca listelenir."""
    out: dict[str, dict[str, Any]] = {}
    for t in thresholds(engine, tenant, "onayli"):
        if not t["depoNo"] and t["stokKodu"] not in out:
            out[t["stokKodu"]] = t
    return out


def save_threshold(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    """Taslak eşik. Aynı kitap ve depo için açık taslak varsa onun yerini alır."""
    k = code(body.get("stokKodu") or body.get("stok_kodu"))
    depo = text(body.get("depoNo"), 40)
    gun = _int(body.get("guvenlikGun"), "Güvenlik günü", 0, 365)
    adet = _qty(body.get("yenidenSiparisAdet"), "Yeniden sipariş adedi")
    kaynak = "oneri" if str(body.get("kaynak") or "") == "oneri" else "elle"
    t = now()
    with engine.begin() as c:
        cond = [THRESHOLDS.c.tenant_id == tenant, THRESHOLDS.c.stok_kodu == k, THRESHOLDS.c.durum == "taslak",
                THRESHOLDS.c.depo_no.is_(None) if depo is None else THRESHOLDS.c.depo_no == depo]
        c.execute(THRESHOLDS.delete().where(*cond))
        rid = uuid.uuid4().hex
        c.execute(THRESHOLDS.insert().values(id=rid, tenant_id=tenant, stok_kodu=k, depo_no=depo, guvenlik_gun=gun,
                                             yeniden_siparis_adet=adet, kaynak=kaynak, durum="taslak",
                                             gerekce=text(body.get("gerekce"), 2000), olusturan=user, created_at=t))
        row = c.execute(sa.select(THRESHOLDS).where(THRESHOLDS.c.id == rid)).one()
    return _threshold(row)


def decide_threshold(engine: sa.engine.Engine, tenant: str, user: str, rid: str, approve: bool,
                     note: Any = None) -> dict[str, Any]:
    """Onay: kitabın (aynı depo) önceki onaylı eşiği arşive geçer. Ret gerekçe ister."""
    t = now()
    with engine.begin() as c:
        row = c.execute(sa.select(THRESHOLDS).where(THRESHOLDS.c.tenant_id == tenant, THRESHOLDS.c.id == str(rid)[:32])).first()
        if row is None:
            raise StockError("Eşik kaydı bulunamadı.", 404)
        if row.durum != "taslak":
            raise StockError("Yalnız taslak eşik onaylanır ya da reddedilir.", 409)
        reason = text(note, 2000)
        if not approve and not reason:
            raise StockError("Ret gerekçesi yazılmalı.")
        if approve:
            same_depot = THRESHOLDS.c.depo_no.is_(None) if row.depo_no is None else THRESHOLDS.c.depo_no == row.depo_no
            c.execute(THRESHOLDS.update().where(THRESHOLDS.c.tenant_id == tenant, THRESHOLDS.c.stok_kodu == row.stok_kodu,
                                                THRESHOLDS.c.durum == "onayli", same_depot).values(durum="arsiv"))
        values: dict[str, Any] = {"durum": "onayli" if approve else "red", "onaylayan": user, "onay_tarihi": t}
        if reason:
            values["gerekce"] = ((row.gerekce + " · ") if row.gerekce else "") + ("Onay notu: " if approve else "Ret: ") + reason
        c.execute(THRESHOLDS.update().where(THRESHOLDS.c.id == row.id).values(**values))
        row = c.execute(sa.select(THRESHOLDS).where(THRESHOLDS.c.id == row.id)).one()
    return _threshold(row)


# ------------------------------------------------------------------ öneriler


def _suggestion(r: Any) -> dict[str, Any]:
    return {"id": r.id, "tur": r.tur, "turEtiket": SUGGESTION_KINDS.get(r.tur, r.tur), "stokKodu": r.stok_kodu,
            "veri": _j(r.payload_json, {}), "gerekce": r.model_gerekce, "durum": r.durum,
            "durumEtiket": SUGGESTION_STATES.get(r.durum, r.durum), "hedef": r.hedef_modul,
            "hedefEtiket": TARGETS.get(r.hedef_modul or "", None), "kararVeren": r.karar_veren,
            "kararTarihi": iso(r.karar_tarihi), "kararNotu": r.karar_notu, "olusturma": iso(r.created_at),
            "guncelleme": iso(r.updated_at)}


def open_suggestions(engine: sa.engine.Engine, tenant: str, tur: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.tur == tur,
                                                      SUGGESTIONS.c.durum == "acik")).all()
    return {r.stok_kodu: _suggestion(r) for r in rows}


def decided_codes(engine: sa.engine.Engine, tenant: str, tur: str, since: datetime) -> set[str]:
    """Bu tarihten sonra karar verilmiş kitaplar: aynı öneri hemen yeniden açılmaz."""
    with engine.connect() as c:
        return {r.stok_kodu for r in c.execute(sa.select(SUGGESTIONS.c.stok_kodu).where(
            SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.tur == tur, SUGGESTIONS.c.durum.in_(("kabul", "red")),
            SUGGESTIONS.c.karar_tarihi >= since))}


def add_suggestion(engine: sa.engine.Engine, tenant: str, tur: str, stok: str, payload: dict[str, Any],
                   gerekce: Optional[str], hedef: Optional[str]) -> str:
    t = now()
    rid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(SUGGESTIONS.insert().values(id=rid, tenant_id=tenant, tur=tur, stok_kodu=stok, payload_json=dump(payload),
                                              model_gerekce=gerekce, durum="acik", hedef_modul=hedef, created_at=t, updated_at=t))
    return rid


def update_suggestion(engine: sa.engine.Engine, rid: str, payload: dict[str, Any], gerekce: Optional[str], hedef: Optional[str]) -> None:
    with engine.begin() as c:
        c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == rid, SUGGESTIONS.c.durum == "acik").values(
            payload_json=dump(payload), model_gerekce=gerekce, hedef_modul=hedef, updated_at=now()))


def expire_suggestions(engine: sa.engine.Engine, tenant: str, tur: str, keep: set[str]) -> int:
    """Koşulu kalkan açık öneri «gecersiz» olur (silinmez; kayıt kalır)."""
    with engine.begin() as c:
        res = c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.tur == tur,
                                                   SUGGESTIONS.c.durum == "acik",
                                                   ~SUGGESTIONS.c.stok_kodu.in_(list(keep) or [""]))
                        .values(durum="gecersiz", updated_at=now()))
        return int(res.rowcount or 0)


def list_suggestions(engine: sa.engine.Engine, tenant: str, *, tur: str = "", durum: str = "acik", hedef: str = "",
                     stok: str = "", page: int = 0) -> dict[str, Any]:
    q = sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant)
    if tur:
        q = q.where(SUGGESTIONS.c.tur == tur)
    if durum:
        q = q.where(SUGGESTIONS.c.durum == durum)
    if hedef:
        q = q.where(SUGGESTIONS.c.hedef_modul == hedef)
    if stok:
        q = q.where(SUGGESTIONS.c.stok_kodu == stok)
    page = max(0, int(page or 0))
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(q.subquery())).scalar() or 0
        rows = c.execute(q.order_by(SUGGESTIONS.c.created_at.desc(), SUGGESTIONS.c.id)
                         .offset(page * PAGE_SIZE).limit(PAGE_SIZE)).all()
    return {"items": [_suggestion(r) for r in rows], "total": int(total), "page": page, "pageSize": PAGE_SIZE}


def decide_suggestion(engine: sa.engine.Engine, tenant: str, user: str, rid: str, decision: Any, note: Any) -> dict[str, Any]:
    karar = str(decision or "")
    if karar not in ("kabul", "red"):
        raise StockError("Karar «kabul» ya da «red» olmalı.")
    reason = text(note, 2000)
    if karar == "red" and not reason:
        raise StockError("Ret gerekçesi yazılmalı.")
    with engine.begin() as c:
        row = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.id == str(rid)[:32])).first()
        if row is None:
            raise StockError("Öneri bulunamadı.", 404)
        if row.durum != "acik":
            raise StockError("Bu öneriye karar verilmiş.", 409)
        c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == row.id).values(
            durum=karar, karar_veren=user, karar_tarihi=now(), karar_notu=reason, updated_at=now()))
        row = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.id == row.id)).one()
    return _suggestion(row)


# ------------------------------------------------------------------ gece fotoğrafı


def write_snapshot(engine: sa.engine.Engine, tenant: str, day: date, rows: list[dict[str, Any]]) -> int:
    """Günün fotoğrafı: aynı gün yeniden koşarsa o günün satırları yenilenir (çift satır olmaz)."""
    g = day.isoformat()
    with engine.begin() as c:
        c.execute(SNAPSHOTS.delete().where(SNAPSHOTS.c.tenant_id == tenant, SNAPSHOTS.c.gun == g))
        for i in range(0, len(rows), 2000):
            part = rows[i:i + 2000]
            if part:
                c.execute(SNAPSHOTS.insert(), [{"tenant_id": tenant, "gun": g, "stok_kodu": r["stokKodu"],
                                                "logo_bakiye": r.get("bakiye"), "crm_raf": r.get("crmRaf"),
                                                "satis_hizi": r.get("satisHizi")} for r in part])
    return len(rows)


def snapshots(engine: sa.engine.Engine, tenant: str, stok: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(SNAPSHOTS).where(SNAPSHOTS.c.tenant_id == tenant, SNAPSHOTS.c.stok_kodu == stok)
                         .order_by(SNAPSHOTS.c.gun)).all()
    return [{"gun": r.gun, "bakiye": r.logo_bakiye, "crmRaf": r.crm_raf, "satisHizi": r.satis_hizi} for r in rows]


# ------------------------------------------------------------------ notlar


def _note(r: Any) -> dict[str, Any]:
    return {"id": r.id, "stokKodu": r.stok_kodu, "not": r.not_metni, "yazan": r.yazan, "yazanAd": r.yazan_ad,
            "tarih": iso(r.tarih)}


def notes(engine: sa.engine.Engine, tenant: str, stok: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(NOTES).where(NOTES.c.tenant_id == tenant, NOTES.c.stok_kodu == stok)
                         .order_by(NOTES.c.tarih.desc())).all()
    return [_note(r) for r in rows]


def add_note(engine: sa.engine.Engine, tenant: str, user: str, display: str, stok: str, body: dict[str, Any]) -> dict[str, Any]:
    k = code(stok)
    t = text(body.get("not"), 4000)
    if not t:
        raise StockError("Not boş olamaz.")
    rid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(NOTES.insert().values(id=rid, tenant_id=tenant, stok_kodu=k, not_metni=t, yazan=user,
                                        yazan_ad=text(display, 200), tarih=now()))
        row = c.execute(sa.select(NOTES).where(NOTES.c.id == rid)).one()
    return _note(row)


def delete_note(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, rid: str) -> dict[str, Any]:
    with engine.begin() as c:
        row = c.execute(sa.select(NOTES).where(NOTES.c.tenant_id == tenant, NOTES.c.id == str(rid)[:32])).first()
        if row is None:
            raise StockError("Not bulunamadı.", 404)
        if row.yazan != user and not admin:
            raise StockError("Yalnız kendi notunuzu silebilirsiniz.", 403)
        c.execute(NOTES.delete().where(NOTES.c.id == row.id))
    return _note(row)
