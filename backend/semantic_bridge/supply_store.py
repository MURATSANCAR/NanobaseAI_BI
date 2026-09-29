"""M52 Tedarik ve baskı — portalın kendi kayıtları (CRM'e, Logo'ya ve matbaaya yazılmaz, gönderilmez).

- **Kapasite** (`semantic_supply_capacity`): matbaanın aylık kapasitesi (adet ve/veya forma). `ay` boşsa her ay için
  geçerlidir; belirli ayın kaydı onu ezer. Aynı matbaa + ay için geçerli olan en yeni kayıttır, eskiler geçmiştir.
  Kapasite girilmemiş matbaada ekran «kapasite tanımlı değil» yazar; geçmiş en yüksek ay yalnız referanstır.
- **Öneri ve taslak** (`semantic_supply_suggestions`): yük dengeleme (`yuk`), kağıt alım zamanı (`kagit`), matbaaya
  gecikme yazısı (`eskalasyon`) ve sipariş formu / teknik şartname (`sartname`) taslakları. Öneriyi kural hesabı üretir;
  Zeki AI yalnız gerekçe ya da yazı metnini yazar, rakam üretmez. Karar (kabul / ret) portal kaydıdır: CRM kartı ve M12
  kaydı değişmez, uygulama insanın işidir.
- **Fatura ↔ kart bağı** (`semantic_supply_invoice_links`): kuralın (M12: satır özel kodu = stok kodu) bağlayamadığı
  matbaa faturası satırı için aday; yöntem `kural` (matbaa + adet + tarih yakınlığı, tek aday), `zeki` (kapalı küme
  seçimi, olasılıkla) ya da `elle`. Yalnız onaylanan bağ hesaba girer.
- **Matbaa ↔ cari eşlemesi** (`semantic_supply_supplier_map`): CRM matbaa seçenek adı ↔ Logo cari kodu. Önerisi
  veriden (kartın matbaası ile faturayı kesen cari); elle girilen kayıt öneriyi ezer.
- **Son okuma** (`semantic_supply_reads`): kaynak okumasının kendisi, kiracı başına tek satır; uçlar yalnız bunu okur.

Silinen kayıt işaretlenir, satır kalır (değişiklik kaydı `semantic_audit`'te).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa

_md = sa.MetaData()

CAPACITY = sa.Table(
    "semantic_supply_capacity", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("matbaa", sa.String(200), nullable=False),          # CRM matbaa seçenek adı
    sa.Column("ay", sa.String(7)),                                 # YYYY-AA; boş = her ay
    sa.Column("kapasite_adet", sa.Numeric(18, 2)),
    sa.Column("kapasite_forma", sa.Numeric(18, 2)),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_display", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("deleted_by", sa.String(120)),
    sa.Column("deleted_at", sa.DateTime(timezone=True)),
)
SUGGESTIONS = sa.Table(
    "semantic_supply_suggestions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(20), nullable=False),              # yuk | kagit | eskalasyon | sartname
    sa.Column("anahtar", sa.String(300), nullable=False, index=True),   # aynı öneri her gece yeniden yazılmasın
    sa.Column("kart_id", sa.String(40)),                           # CRM new_UretimId (varsa)
    sa.Column("baslik", sa.String(400)),
    sa.Column("payload_json", sa.Text, nullable=False, default="{}"),
    sa.Column("model_gerekce", sa.Text),                           # Zeki AI'ın yazdığı metin (gerekçe ya da taslak)
    sa.Column("durum", sa.String(16), nullable=False),            # bekliyor | kabul | ret | taslak | eskidi
    sa.Column("karar_veren", sa.String(120)),
    sa.Column("karar_display", sa.String(200)),
    sa.Column("karar_tarihi", sa.DateTime(timezone=True)),
    sa.Column("karar_notu", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),      # «zeki» (gece işi) ya da kişi
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
INVOICE_LINKS = sa.Table(
    "semantic_supply_invoice_links", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("logo_firma", sa.String(3), nullable=False),
    sa.Column("invoice_ref", sa.String(40), nullable=False),      # baskı faturası satırının LOGICALREF'i
    sa.Column("fatura_no", sa.String(60)),
    sa.Column("kart_id", sa.String(40)),                          # boş = «hiçbir kartın değil» kararı
    sa.Column("yontem", sa.String(10), nullable=False),           # kural | zeki | elle
    sa.Column("olasilik", sa.Float),
    sa.Column("adaylar_json", sa.Text),
    sa.Column("durum", sa.String(10), nullable=False),            # oneri | onayli | ret
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_tarihi", sa.DateTime(timezone=True)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("deleted_at", sa.DateTime(timezone=True)),
)
SUPPLIER_MAP = sa.Table(
    "semantic_supply_supplier_map", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("crm_matbaa", sa.String(200), nullable=False),
    sa.Column("logo_cari_kodu", sa.String(60)),                   # boş = «Logo'da carisi yok» kararı
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_display", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("deleted_at", sa.DateTime(timezone=True)),
)
#: Son kaynak okuması (M12 kartları + CRM teknik alanlar + Logo tedarikçi/fatura), kiracı başına tek satır. Gece turu
#: (`run-due`) ve arka plan tazelemesi yazar; ekran uçları yalnız bunu okur. Gövde okumanın kendisidir (tarih, sayı
#: anahtarlı sözlük, Decimal, tuple ve `runs` = çalışan SQL / satır / süre / an aynen korunsun diye türleri koruyan JSON +
#: zlib, `typed_json`; pickle değil — tablodan yalnız veri çözülür, kod çalışmaz).
READS = sa.Table(
    "semantic_supply_reads", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("read_at", sa.Float, nullable=False),              # okumanın anı (snap["at"], epoch)
    sa.Column("payload", sa.LargeBinary, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

KINDS = {"yuk": "Yük dengeleme", "kagit": "Kağıt alım zamanı", "eskalasyon": "Matbaaya gecikme yazısı",
         "sartname": "Sipariş formu / teknik şartname"}
STATES = {"bekliyor": "Karar bekliyor", "kabul": "Kabul edildi", "ret": "Reddedildi", "taslak": "Taslak",
          "eskidi": "Durum değişti (geçersiz)"}
LINK_METHODS = {"kural": "Kural (matbaa, adet, tarih)", "zeki": "Zeki AI seçimi", "elle": "Elle"}
LINK_STATES = {"oneri": "Onay bekliyor", "onayli": "Onaylı", "ret": "Reddedildi"}

_ID = re.compile(r"^[0-9a-f]{32}$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_MONTH = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_ready: set[int] = set()
_lock = threading.Lock()


class SupplyError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ son okuma


def read_stmt(tenant: str) -> Any:
    """Uçların son okumayı aldığı ifade (sorgu bilgisi aynı ifadeyi gösterir)."""
    return sa.select(READS.c.payload).where(READS.c.tenant_id == tenant)


def read_at(engine: sa.engine.Engine, tenant: str) -> Optional[float]:
    """Tablodaki son okumanın anı (gövdesiz, ucuz)."""
    with engine.connect() as c:
        v = c.execute(sa.select(READS.c.read_at).where(READS.c.tenant_id == tenant)).scalar()
    return float(v) if v is not None else None


def read_get(engine: sa.engine.Engine, tenant: str) -> Optional[dict[str, Any]]:
    """Yalnız veri çözülür (türleri koruyan JSON); kod çalıştırılmaz. Çözülemeyen satır yok sayılır, kaynaktan okunur."""
    from semantic_bridge import typed_json

    with engine.connect() as c:
        v = c.execute(read_stmt(tenant)).scalar()
    if not v:
        return None
    out = typed_json.unpack(v)          # bozuk satırda hata: çağıran (supply.Source) yakalar ve kaynaktan okur
    return out if isinstance(out, dict) else None


def read_put(engine: sa.engine.Engine, tenant: str, snap: dict[str, Any]) -> None:
    from semantic_bridge import typed_json

    body = typed_json.pack(snap)
    with engine.begin() as c:
        c.execute(READS.delete().where(READS.c.tenant_id == tenant))
        c.execute(READS.insert().values(tenant_id=tenant, read_at=float(snap.get("at") or 0), payload=body, updated_at=_now()))


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).isoformat()


def rid(v: Any) -> str:
    s = str(v or "").strip()
    if not _ID.match(s):
        raise SupplyError("Kayıt bulunamadı.", 404)
    return s


def card_id(v: Any, required: bool = True) -> Optional[str]:
    s = str(v or "").strip()
    if not s and not required:
        return None
    if not _GUID.match(s):
        raise SupplyError("Üretim kartı bulunamadı.", 404)
    return s.lower()


def _text(v: Any, limit: int, label: str = "Metin") -> Optional[str]:
    s = re.sub(r"[ \t]+", " ", str(v or "")).strip()
    if len(s) > limit:
        raise SupplyError(f"{label} en çok {limit} karakter olabilir.")
    return s or None


def _amount(v: Any, label: str) -> Optional[float]:
    if v in (None, ""):
        return None
    s = str(v).replace(" ", "").strip()
    if "," in s:  # Türkçe yazım: binlik nokta, ondalık virgül
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # «2.000» = iki bin (binlik nokta), 2,0 değil
        s = s.replace(".", "")
    try:
        x = float(s)
    except ValueError:
        raise SupplyError(f"{label} sayı olmalı.") from None
    if x < 0:
        raise SupplyError(f"{label} eksi olamaz.")
    return x


def _num(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


# ------------------------------------------------------------------ kapasite


def capacity_values(body: dict[str, Any], printers: Optional[list[str]] = None) -> dict[str, Any]:
    printer = _text(body.get("matbaa"), 200, "Matbaa")
    if not printer:
        raise SupplyError("Matbaa seçilmeli.")
    if printers is not None and printer not in printers:
        raise SupplyError("Matbaa CRM'deki matbaa listesinde yok.")
    month = str(body.get("ay") or "").strip() or None
    if month and not _MONTH.match(month):
        raise SupplyError("Ay YYYY-AA biçiminde olmalı.")
    adet = _amount(body.get("kapasiteAdet"), "Aylık kapasite (adet)")
    forma = _amount(body.get("kapasiteForma"), "Aylık kapasite (forma)")
    if adet is None and forma is None and not body.get("kaldir"):
        raise SupplyError("Kapasite adet ya da forma olarak girilmeli.")
    return {"matbaa": printer, "ay": month, "kapasite_adet": adet, "kapasite_forma": forma,
            "note": _text(body.get("not"), 1000, "Not")}


def add_capacity(engine: sa.engine.Engine, tenant: str, user: str, display: str, body: dict[str, Any],
                 printers: Optional[list[str]] = None) -> dict[str, Any]:
    vals = capacity_values(body, printers)
    row = {"id": uuid.uuid4().hex, "tenant_id": tenant, **vals, "created_by": user, "created_display": display,
           "created_at": _now()}
    with engine.begin() as c:
        c.execute(CAPACITY.insert().values(**row))
    return _capacity(row)


def delete_capacity(engine: sa.engine.Engine, tenant: str, user: str, record: str) -> dict[str, Any]:
    record = rid(record)
    with engine.begin() as c:
        r = c.execute(sa.select(CAPACITY).where(CAPACITY.c.tenant_id == tenant, CAPACITY.c.id == record,
                                                CAPACITY.c.deleted_at.is_(None))).mappings().first()
        if r is None:
            raise SupplyError("Kapasite kaydı bulunamadı.", 404)
        c.execute(CAPACITY.update().where(CAPACITY.c.id == record).values(deleted_by=user, deleted_at=_now()))
    return _capacity(dict(r))


def _capacity(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": r["id"], "matbaa": r["matbaa"], "ay": r.get("ay"), "kapasiteAdet": _num(r.get("kapasite_adet")),
            "kapasiteForma": _num(r.get("kapasite_forma")), "not": r.get("note"), "by": r["created_by"],
            "byName": r.get("created_display") or r["created_by"], "at": _iso(r.get("created_at"))}


def capacity_stmt(tenant: str) -> Any:
    """Kapasite kayıtları okuması (uç ve sorgu bilgisi aynı ifade)."""
    return (sa.select(CAPACITY).where(CAPACITY.c.tenant_id == tenant, CAPACITY.c.deleted_at.is_(None))
            .order_by(CAPACITY.c.created_at.desc()))


def list_capacity(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    q = capacity_stmt(tenant)
    with engine.connect() as c:
        return [_capacity(dict(r)) for r in c.execute(q).mappings()]


def capacity_for(records: list[dict[str, Any]], printer: str, month: str) -> Optional[dict[str, Any]]:
    """Matbaanın o aydaki geçerli kapasitesi: önce o ayın, yoksa «her ay» kaydı; aynı düzeyde en yenisi (liste yeniden
    eskiye sıralı gelir)."""
    exact = next((r for r in records if r["matbaa"] == printer and r["ay"] == month), None)
    if exact:
        return exact
    return next((r for r in records if r["matbaa"] == printer and not r["ay"]), None)


# ------------------------------------------------------------------ öneriler ve taslaklar


def _suggestion(r: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(r.get("payload_json") or "{}")
    except ValueError:
        payload = {}
    return {"id": r["id"], "tur": r["tur"], "turAdi": KINDS.get(r["tur"], r["tur"]), "anahtar": r["anahtar"],
            "kartId": r.get("kart_id"), "baslik": r.get("baslik"), "veri": payload, "metin": r.get("model_gerekce"),
            "durum": r["durum"], "durumAdi": STATES.get(r["durum"], r["durum"]),
            "kararVeren": r.get("karar_display") or r.get("karar_veren"), "kararTarihi": _iso(r.get("karar_tarihi")),
            "kararNotu": r.get("karar_notu"), "olusturan": r["created_by"], "olusturma": _iso(r.get("created_at")),
            "guncelleme": _iso(r.get("updated_at"))}


def upsert_suggestion(engine: sa.engine.Engine, tenant: str, *, tur: str, anahtar: str, baslik: str,
                      payload: dict[str, Any], metin: Optional[str], kart: Optional[str] = None,
                      by: str = "zeki") -> tuple[dict[str, Any], bool]:
    """Gece işi: aynı anahtarlı bekleyen öneri varsa verisi tazelenir (karar verilmişe dokunulmaz); yoksa yeni.
    Dönüş: (öneri, yeni mi)."""
    if tur not in KINDS:
        raise SupplyError("Öneri türü geçersiz.")
    now = _now()
    with engine.begin() as c:
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.anahtar == anahtar)
                      .order_by(SUGGESTIONS.c.created_at.desc())).mappings().first()
        if r is not None and r["durum"] in ("bekliyor", "kabul", "ret"):
            if r["durum"] == "bekliyor":
                vals = {"payload_json": json.dumps(payload, ensure_ascii=False, default=str), "baslik": baslik[:400],
                        "updated_at": now}
                if metin:
                    vals["model_gerekce"] = metin
                c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == r["id"]).values(**vals))
                r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.id == r["id"])).mappings().first()
            return _suggestion(dict(r)), False
        row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "tur": tur, "anahtar": anahtar[:300], "kart_id": kart,
               "baslik": baslik[:400], "payload_json": json.dumps(payload, ensure_ascii=False, default=str),
               "model_gerekce": metin, "durum": "bekliyor", "created_by": by, "created_at": now, "updated_at": now}
        c.execute(SUGGESTIONS.insert().values(**row))
    return _suggestion(row), True


def expire_suggestions(engine: sa.engine.Engine, tenant: str, tur: str, keep: set[str]) -> int:
    """Durumu geçen (bu gece yeniden üretilmeyen) bekleyen öneriler «eskidi» olur; karar verilmişe dokunulmaz."""
    with engine.begin() as c:
        q = SUGGESTIONS.update().where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.tur == tur,
                                       SUGGESTIONS.c.durum == "bekliyor")
        if keep:
            q = q.where(SUGGESTIONS.c.anahtar.notin_(sorted(keep)))
        return int(c.execute(q.values(durum="eskidi", updated_at=_now())).rowcount or 0)


def add_draft(engine: sa.engine.Engine, tenant: str, user: str, *, tur: str, kart: Optional[str], baslik: str,
              payload: dict[str, Any], metin: str) -> dict[str, Any]:
    if tur not in ("eskalasyon", "sartname"):
        raise SupplyError("Taslak türü «eskalasyon» ya da «sartname» olmalı.")
    now = _now()
    row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "tur": tur, "anahtar": f"{tur}:{kart or '-'}:{uuid.uuid4().hex[:8]}",
           "kart_id": kart, "baslik": baslik[:400], "payload_json": json.dumps(payload, ensure_ascii=False, default=str),
           "model_gerekce": metin, "durum": "taslak", "created_by": user, "created_at": now, "updated_at": now}
    with engine.begin() as c:
        c.execute(SUGGESTIONS.insert().values(**row))
    return _suggestion(row)


def suggestions_stmt(tenant: str, tur: str = "", durum: str = "") -> Any:
    q = sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant)
    if tur:
        q = q.where(SUGGESTIONS.c.tur == tur)
    if durum:
        q = q.where(SUGGESTIONS.c.durum == durum)
    return q.order_by(SUGGESTIONS.c.created_at.desc())


def list_suggestions(engine: sa.engine.Engine, tenant: str, tur: str = "", durum: str = "") -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [_suggestion(dict(r)) for r in c.execute(suggestions_stmt(tenant, tur, durum)).mappings()]


def get_suggestion(engine: sa.engine.Engine, tenant: str, record: str) -> dict[str, Any]:
    record = rid(record)
    with engine.connect() as c:
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.id == record)).mappings().first()
    if r is None:
        raise SupplyError("Öneri bulunamadı.", 404)
    return _suggestion(dict(r))


def decide_suggestion(engine: sa.engine.Engine, tenant: str, user: str, display: str, record: str,
                      body: dict[str, Any]) -> dict[str, Any]:
    record = rid(record)
    karar = str(body.get("karar") or "")
    if karar not in ("kabul", "ret"):
        raise SupplyError("Karar «kabul» ya da «ret» olmalı.")
    note = _text(body.get("not"), 1000, "Not")
    if karar == "ret" and not note:
        raise SupplyError("Reddetme gerekçesini bir cümleyle yazın.")
    with engine.begin() as c:
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.id == record)).mappings().first()
        if r is None:
            raise SupplyError("Öneri bulunamadı.", 404)
        if r["durum"] != "bekliyor":
            raise SupplyError("Bu öneri için karar verilmiş ya da öneri geçersiz olmuş.", 409)
        c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == record).values(
            durum=karar, karar_veren=user, karar_display=display, karar_tarihi=_now(), karar_notu=note, updated_at=_now()))
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.id == record)).mappings().first()
    return _suggestion(dict(r))


# ------------------------------------------------------------------ fatura ↔ kart bağı


def _link(r: dict[str, Any]) -> dict[str, Any]:
    try:
        cands = json.loads(r.get("adaylar_json") or "[]")
    except ValueError:
        cands = []
    return {"id": r["id"], "firma": r["logo_firma"], "satirRef": r["invoice_ref"], "faturaNo": r.get("fatura_no"),
            "kartId": r.get("kart_id"), "yontem": r["yontem"], "yontemAdi": LINK_METHODS.get(r["yontem"], r["yontem"]),
            "olasilik": r.get("olasilik"), "adaylar": cands, "durum": r["durum"],
            "durumAdi": LINK_STATES.get(r["durum"], r["durum"]), "onaylayan": r.get("onaylayan"),
            "onayTarihi": _iso(r.get("onay_tarihi")), "olusturan": r["created_by"], "olusturma": _iso(r.get("created_at"))}


def links_stmt(tenant: str) -> Any:
    return (sa.select(INVOICE_LINKS).where(INVOICE_LINKS.c.tenant_id == tenant, INVOICE_LINKS.c.deleted_at.is_(None))
            .order_by(INVOICE_LINKS.c.created_at.desc()))


def list_links(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    q = links_stmt(tenant)
    with engine.connect() as c:
        return [_link(dict(r)) for r in c.execute(q).mappings()]


def upsert_link_proposal(engine: sa.engine.Engine, tenant: str, *, firma: str, satir: str, fatura_no: Optional[str],
                         kart: Optional[str], yontem: str, olasilik: Optional[float], adaylar: list[dict[str, Any]]) -> bool:
    """Gece işi: satır için bekleyen öneri yoksa yazar; onaylı/reddedilmiş satıra dokunmaz. Yeni yazıldıysa True."""
    with engine.begin() as c:
        cur = c.execute(sa.select(INVOICE_LINKS).where(
            INVOICE_LINKS.c.tenant_id == tenant, INVOICE_LINKS.c.logo_firma == firma, INVOICE_LINKS.c.invoice_ref == satir,
            INVOICE_LINKS.c.deleted_at.is_(None))).mappings().all()
        if any(r["durum"] in ("onayli",) for r in cur):
            return False
        pending = [r for r in cur if r["durum"] == "oneri"]
        rejected = {(r["kart_id"] or "") for r in cur if r["durum"] == "ret"}
        if (kart or "") in rejected:
            return False
        vals = {"kart_id": kart, "yontem": yontem, "olasilik": olasilik, "fatura_no": fatura_no,
                "adaylar_json": json.dumps(adaylar, ensure_ascii=False, default=str)}
        if pending:
            c.execute(INVOICE_LINKS.update().where(INVOICE_LINKS.c.id == pending[0]["id"]).values(**vals))
            return False
        c.execute(INVOICE_LINKS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, logo_firma=firma, invoice_ref=satir,
                                                durum="oneri", created_by="zeki", created_at=_now(), **vals))
    return True


def decide_link(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any],
                valid_cards: Optional[set[str]] = None) -> dict[str, Any]:
    """Elle bağ ya da öneri kararı. Gövde: {firma, satirRef, kartId|null, karar: onay|ret, oneriId?}."""
    firma = str(body.get("firma") or "")
    satir = str(body.get("satirRef") or "")
    if not re.match(r"^[0-9]{3}$", firma) or not re.match(r"^[0-9]{1,18}$", satir):
        raise SupplyError("Fatura satırı geçersiz.")
    karar = str(body.get("karar") or "onay")
    if karar not in ("onay", "ret"):
        raise SupplyError("Karar «onay» ya da «ret» olmalı.")
    kart = card_id(body.get("kartId"), required=False)
    if kart and valid_cards is not None and kart not in valid_cards:
        raise SupplyError("Kart geçmiş penceresinde bulunamadı.", 404)
    now = _now()
    with engine.begin() as c:
        cur = c.execute(sa.select(INVOICE_LINKS).where(
            INVOICE_LINKS.c.tenant_id == tenant, INVOICE_LINKS.c.logo_firma == firma, INVOICE_LINKS.c.invoice_ref == satir,
            INVOICE_LINKS.c.deleted_at.is_(None))).mappings().all()
        pending = next((r for r in cur if r["durum"] == "oneri" and (r["kart_id"] or None) == kart), None)
        if karar == "onay":
            # Aynı satırın önceki onaylı bağı ve diğer bekleyen önerileri kapanır: bir satır tek karta gider.
            for r in cur:
                if r["durum"] in ("onayli", "oneri") and (pending is None or r["id"] != pending["id"]):
                    c.execute(INVOICE_LINKS.update().where(INVOICE_LINKS.c.id == r["id"]).values(deleted_at=now))
            if pending:
                c.execute(INVOICE_LINKS.update().where(INVOICE_LINKS.c.id == pending["id"]).values(
                    durum="onayli", onaylayan=user, onay_tarihi=now))
                out_id = pending["id"]
            else:
                out_id = uuid.uuid4().hex
                c.execute(INVOICE_LINKS.insert().values(
                    id=out_id, tenant_id=tenant, logo_firma=firma, invoice_ref=satir, fatura_no=_text(body.get("faturaNo"), 60),
                    kart_id=kart, yontem="elle", olasilik=None, adaylar_json="[]", durum="onayli", onaylayan=user,
                    onay_tarihi=now, created_by=user, created_at=now))
        else:
            if pending is None:
                raise SupplyError("Reddedilecek öneri bulunamadı.", 404)
            c.execute(INVOICE_LINKS.update().where(INVOICE_LINKS.c.id == pending["id"]).values(
                durum="ret", onaylayan=user, onay_tarihi=now))
            out_id = pending["id"]
        r = c.execute(sa.select(INVOICE_LINKS).where(INVOICE_LINKS.c.id == out_id)).mappings().first()
    return _link(dict(r))


# ------------------------------------------------------------------ matbaa ↔ cari eşlemesi


def supplier_map_stmt(tenant: str) -> Any:
    return (sa.select(SUPPLIER_MAP).where(SUPPLIER_MAP.c.tenant_id == tenant, SUPPLIER_MAP.c.deleted_at.is_(None))
            .order_by(SUPPLIER_MAP.c.created_at.desc()))


def list_supplier_map(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    """CRM matbaa adı → geçerli (en yeni) elle eşleme."""
    q = supplier_map_stmt(tenant)
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for r in c.execute(q).mappings():
            out.setdefault(r["crm_matbaa"], {"id": r["id"], "cari": r.get("logo_cari_kodu"), "by": r["created_by"],
                                             "byName": r.get("created_display") or r["created_by"],
                                             "at": _iso(r.get("created_at"))})
    return out


def set_supplier_map(engine: sa.engine.Engine, tenant: str, user: str, display: str, body: dict[str, Any],
                     printers: Optional[list[str]] = None) -> dict[str, Any]:
    printer = _text(body.get("matbaa"), 200, "Matbaa")
    if not printer:
        raise SupplyError("Matbaa seçilmeli.")
    if printers is not None and printer not in printers:
        raise SupplyError("Matbaa CRM'deki matbaa listesinde yok.")
    code = _text(body.get("cari"), 60, "Cari kodu")
    if code and not re.match(r"^[0-9A-Za-z.\-_]{1,60}$", code):
        raise SupplyError("Cari kodu geçersiz.")
    now = _now()
    with engine.begin() as c:
        c.execute(SUPPLIER_MAP.update().where(SUPPLIER_MAP.c.tenant_id == tenant, SUPPLIER_MAP.c.crm_matbaa == printer,
                                              SUPPLIER_MAP.c.deleted_at.is_(None)).values(deleted_at=now))
        if not body.get("kaldir"):
            c.execute(SUPPLIER_MAP.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, crm_matbaa=printer,
                                                   logo_cari_kodu=code, created_by=user, created_display=display,
                                                   created_at=now))
    return {"matbaa": printer, "cari": None if body.get("kaldir") else code, "kaldirildi": bool(body.get("kaldir"))}


def month_key(d: Optional[date]) -> Optional[str]:
    return f"{d.year:04d}-{d.month:02d}" if d else None
