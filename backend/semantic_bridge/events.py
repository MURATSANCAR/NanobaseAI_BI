"""M27 Fuar, etkinlik ve ödül yönetimi: portal kayıtları ve hesaplar (kaynak okuması `events_sources.py`, uçlar
`events_api.py`).

**Ne tutulur (hepsi portalda, CRM'e yazılmaz):** fuar kartı (tarih, yer, stant, planlanan bütçe, sorumlu, katılım
kararı, bağlı CRM etkinlikleri ve fuar carileri), fuara götürülecek kitaplar ve adetler, görevler, giderler (fiş
fotoğrafı + tutar), yazar programı, CRM etkinlik tipi eşlemesi, ödül defteri ve başvurular, hatırlatmalar.

**Etkinlik tipi eşlemesi (ayar):** CRM'deki 371 etkinlik tipinin hangisinin fuar / imza günü / söyleşi / okul etkinliği
/ satış ziyareti / diğer olduğu insan kararıdır (`semantic_events_type_map.sinif`). Zeki AI yalnız öneri yazar (kapalı
küme seçimi, olasılıkla); öneri onaylanana kadar takvimde o tipin etkinlikleri «Sınıflanmamış» durur. Satış
ziyaretleri ve sınıflanmamışlar takvimde varsayılan gizlidir.

**Kitap/adet önerisi (K2, kural):** temel = geçen yılın aynı fuarının fuar kanalı satışı (bağlı önceki fuar kartı
varsa onun tarihleri ve carileri, yoksa aynı günlerin 364 gün öncesi). Önerilen adet = ⌈temel net adet × katsayı⌉
(`EVENTS_SUGGEST_FACTOR`). Temelde olmayan yeni çıkan kitap (ilk yayın son `EVENTS_NEW_BOOK_MONTHS` ay, stokta var):
⌈temeldeki satan kitapların ortanca adedi × `EVENTS_NEW_BOOK_FACTOR`⌉. Stok önerinin altındaysa işaretlenir (kısaltılmaz).
Rakamı model üretmez.

**Fuar sonucu (K1/K3):** fuar kanalı faturalı net satış (tarih aralığı + varsa fuar carileri), CRM fuar/etkinlik/imza
siparişleri (sipariş tarihi aralıkta), bağlı CRM etkinliklerinin katılımcı/satılan/gideri, portalda girilen gider,
bütçe, geçen yılla karşılaştırma, veri sonu tarihi. Yorum cümleleri rakamlardan kuralla yazılır.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import statistics
import threading
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

log = logging.getLogger("semantic.events")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

#: Etkinlik tipi sınıfları (CRM tip eşlemesi). Sıra model seçeneklerinin sırasıdır.
CLASSES: dict[str, str] = {"fuar": "Fuar", "imza": "İmza günü", "soylesi": "Söyleşi", "okul": "Okul etkinliği",
                           "satis": "Satış ziyareti", "diger": "Diğer"}
CLASS_HINTS: dict[str, str] = {
    "fuar": "kitap fuarı, festival standı, kitap günleri",
    "imza": "yazar imza günü",
    "soylesi": "yazar söyleşisi, panel, konferans, kitap tanıtım buluşması",
    "okul": "okulda öğrenci/öğretmen etkinliği, okul tanıtımı, okul ziyareti",
    "satis": "bayi, kitapçı ya da cari ziyareti, tahsilat, satış görüşmesi",
    "diger": "yukarıdakilerin hiçbiri",
}
FAIR_KINDS: dict[str, str] = {"stant": "Stant satışı fuarı", "hak": "Hak alım-satım fuarı", "festival": "Festival",
                              "imza": "İmza günü", "soylesi": "Söyleşi", "okul": "Okul etkinliği", "diger": "Diğer"}
FAIR_STATUSES: dict[str, str] = {"aday": "Aday (karar bekliyor)", "onayli": "Onaylı", "iptal": "İptal"}
PHASES: dict[str, str] = {"hazirlik": "Hazırlık", "suruyor": "Sürüyor", "bitti": "Bitti"}
COST_KINDS: dict[str, str] = {"stant": "Stant kirası", "konaklama": "Konaklama", "ulasim": "Ulaşım", "sevkiyat": "Sevkiyat",
                              "materyal": "Materyal", "yazar": "Yazar", "diger": "Diğer"}
ENTRY_STATUSES: dict[str, str] = {"aday": "Aday", "hazirlaniyor": "Hazırlanıyor", "gonderildi": "Gönderildi",
                                  "kisa-liste": "Kısa liste", "kazandi": "Kazandı", "kazanamadi": "Kazanamadı"}
RECEIPT_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/heic": ".heic",
                 "application/pdf": ".pdf"}

FAIRS = sa.Table(
    "semantic_events_fairs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(300), nullable=False),
    sa.Column("kind", sa.String(20), nullable=False),
    sa.Column("starts_on", sa.String(10), nullable=False),
    sa.Column("ends_on", sa.String(10), nullable=False),
    sa.Column("city", sa.String(120)),
    sa.Column("venue", sa.String(300)),
    sa.Column("stand_info", sa.Text),
    sa.Column("budget_planned", sa.Float),
    sa.Column("status", sa.String(12), nullable=False),
    sa.Column("owner_user", sa.String(120)),
    sa.Column("crm_event_ids_json", sa.Text),
    sa.Column("logo_client_codes_json", sa.Text),
    sa.Column("prev_fair_id", sa.String(32)),
    sa.Column("note", sa.Text),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("decision_note", sa.Text),
    sa.Column("result_json", sa.Text),
    sa.Column("result_at", sa.DateTime(timezone=True)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

BOOKS = sa.Table(
    "semantic_events_books", _md,
    sa.Column("fair_id", sa.String(32), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("crm_book_id", sa.String(40)),
    sa.Column("ad", sa.String(400)),
    sa.Column("qty_suggested", sa.Float),
    sa.Column("qty_planned", sa.Float),
    sa.Column("qty_sold", sa.Float),
    sa.Column("stock", sa.Float),
    sa.Column("basis_qty", sa.Float),
    sa.Column("featured", sa.Boolean, nullable=False, default=False),
    sa.Column("reason", sa.Text),
    sa.Column("source", sa.String(10), nullable=False),              # zeki | elle
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

TASKS = sa.Table(
    "semantic_events_tasks", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("fair_id", sa.String(32), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("due_on", sa.String(10)),
    sa.Column("owner_user", sa.String(120)),
    sa.Column("done_at", sa.DateTime(timezone=True)),
    sa.Column("done_by", sa.String(120)),
    sa.Column("sort", sa.Integer, nullable=False, default=0),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

COSTS = sa.Table(
    "semantic_events_costs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("fair_id", sa.String(32), nullable=False, index=True),
    sa.Column("kind", sa.String(20), nullable=False),
    sa.Column("amount", sa.Float, nullable=False),
    sa.Column("note", sa.String(400)),
    sa.Column("receipt_ref", sa.String(200)),                         # dosya adı (EVENTS_DIR/<fuar>/)
    sa.Column("receipt_type", sa.String(60)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

AUTHORS = sa.Table(
    "semantic_events_authors", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("fair_id", sa.String(32), nullable=False, index=True),
    sa.Column("crm_contact_id", sa.String(40)),
    sa.Column("name", sa.String(300), nullable=False),
    sa.Column("slot_start", sa.String(16)),                           # YYYY-MM-DDTHH:MM (İstanbul)
    sa.Column("slot_end", sa.String(16)),
    sa.Column("note", sa.String(400)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

TYPE_MAP = sa.Table(
    "semantic_events_type_map", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("crm_type_id", sa.String(40), primary_key=True),
    sa.Column("name", sa.String(300)),
    sa.Column("sinif", sa.String(12)),                                # insan kararı (takvim bunu kullanır)
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("suggested", sa.String(12)),                            # Zeki AI önerisi
    sa.Column("suggested_prob", sa.Float),
    sa.Column("suggested_margin", sa.Float),
    sa.Column("suggested_method", sa.String(12)),
    sa.Column("suggested_at", sa.DateTime(timezone=True)),
)

AWARDS = sa.Table(
    "semantic_awards", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(300), nullable=False),
    sa.Column("category", sa.String(200)),
    sa.Column("organizer", sa.String(300)),
    sa.Column("deadline", sa.String(10)),
    sa.Column("conditions", sa.Text),
    sa.Column("url", sa.String(600)),
    sa.Column("recurring", sa.Boolean, nullable=False, default=False),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

ENTRIES = sa.Table(
    "semantic_award_entries", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("award_id", sa.String(32), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("crm_book_id", sa.String(40)),
    sa.Column("book_name", sa.String(400), nullable=False),
    sa.Column("status", sa.String(12), nullable=False),
    sa.Column("text", sa.Text),
    sa.Column("submitted_at", sa.String(10)),
    sa.Column("result_at", sa.String(10)),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

REMINDERS = sa.Table(
    "semantic_events_reminders", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kind", sa.String(20), nullable=False),
    sa.Column("ref_id", sa.String(40), nullable=False),
    sa.Column("day_key", sa.String(40), nullable=False),
    sa.Column("target_user", sa.String(120)),
    sa.Column("message", sa.String(600), nullable=False),
    sa.Column("link", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "kind", "ref_id", "day_key", name="uq_events_reminder"),
)

_lock = threading.Lock()
_ready: set[int] = set()


class EventsError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        _md.create_all(engine, checkfirst=True)
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


def _conf_ints(key: str, default: str) -> list[int]:
    return [int(x) for x in re.findall(r"-?\d+", _conf(key, default) or "")]


DEFAULT_TASKS = [
    {"title": "Katılım kararı ve bütçe onayı", "days": -90},
    {"title": "Stant yeri ve kira sözleşmesi", "days": -60},
    {"title": "Yazar programı (imza günleri) netleşti", "days": -30},
    {"title": "Kitap ve adet listesi onaylandı", "days": -21},
    {"title": "Stant materyali (afiş, föy) onaylandı", "days": -14},
    {"title": "Sevkiyat listesi depoya verildi", "days": -10},
    {"title": "Personel ve vardiya planı", "days": -7},
    {"title": "Fuar sonrası stok iadesi ve sayım", "days": 3},
    {"title": "Fuar sonucu raporu yönetime", "days": 5},
]


def settings() -> dict[str, Any]:
    """Modülün ayarları (ekran > ortam > varsayılan). Ölçülmemiş varsayımlar buradadır, kodda sabit değil."""
    try:
        tpl = json.loads(_conf("EVENTS_TASK_TEMPLATE", "") or "null")
    except ValueError:
        tpl = None
    if not isinstance(tpl, list) or not all(isinstance(x, dict) and x.get("title") for x in tpl):
        tpl = DEFAULT_TASKS
    classes = [c for c in re.split(r"[,\s]+", _conf("EVENTS_DEFAULT_CLASSES", "fuar,imza,soylesi")) if c in CLASSES]
    return {
        "channel": (_conf("EVENTS_FAIR_CHANNEL", "FUAR") or "FUAR").strip(),
        "orderTypes": _conf_ints("EVENTS_ORDER_TYPES", "4,5,16") or [4, 5, 16],
        # İptal ve birleştirilen sipariş sayılmaz (birleşen sipariş hedef kayıtta ikinci kez sayılırdı) — ölçülecek.
        "orderExcluded": _conf_ints("EVENTS_ORDER_EXCLUDED_STATUS", "100000001,100000003"),
        "remindDays": sorted(set(_conf_ints("EVENTS_REMIND_DAYS", "60,30,14,7")), reverse=True) or [60, 30, 14, 7],
        "awardRemindDays": sorted(set(_conf_ints("EVENTS_AWARD_REMIND_DAYS", "30,7")), reverse=True) or [30, 7],
        "agendaDays": max(1, int(_conf_float("EVENTS_AGENDA_DAYS", 60))),
        "newBookMonths": max(0, int(_conf_float("EVENTS_NEW_BOOK_MONTHS", 12))),
        "newBookFactor": max(0.0, _conf_float("EVENTS_NEW_BOOK_FACTOR", 0.5)),
        "suggestFactor": max(0.0, _conf_float("EVENTS_SUGGEST_FACTOR", 1.0)),
        "resultTailDays": max(0, int(_conf_float("EVENTS_RESULT_TAIL_DAYS", 0))),
        "typeSuggestProb": _conf_float("EVENTS_TYPE_SUGGEST_PROB", 0.70),
        "typeSuggestMargin": _conf_float("EVENTS_TYPE_SUGGEST_MARGIN", 0.30),
        "defaultClasses": classes or ["fuar", "imza", "soylesi"],
        "receiptMaxMb": max(1, int(_conf_float("EVENTS_RECEIPT_MAX_MB", 10))),
        "taskTemplate": [{"title": str(x["title"])[:300], "days": int(x.get("days") or 0)} for x in tpl],
    }


def files_root() -> Path:
    return Path(os.environ.get("EVENTS_DIR", "/data/nanobaseai/bi/var/events"))


# ------------------------------------------------------------------ küçük yardımcılar


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


def _id() -> str:
    return uuid.uuid4().hex


def fold(v: Any) -> str:
    t = unicodedata.normalize("NFKD", str(v or "").replace("ı", "i").replace("İ", "i").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z]+", " ", t)).strip()


def _text(v: Any, n: int, label: str = "", required: bool = False) -> Optional[str]:
    t = re.sub(r"\s+", " ", str(v or "")).strip()
    if required and not t:
        raise EventsError(f"{label} boş olamaz.", 422)
    return t[:n] or None


def _long(v: Any, n: int = 20000) -> Optional[str]:
    t = str(v or "").strip()
    return t[:n] or None


def parse_day(v: Any, label: str, required: bool = False) -> Optional[date]:
    t = str(v or "").strip()[:10]
    if not t:
        if required:
            raise EventsError(f"{label} girilmeli.", 422)
        return None
    try:
        return date.fromisoformat(t)
    except ValueError:
        raise EventsError(f"{label} tarihi YYYY-AA-GG biçiminde olmalı.", 422) from None


def parse_slot(v: Any, label: str) -> Optional[str]:
    t = str(v or "").strip()[:16]
    if not t:
        return None
    try:
        return datetime.fromisoformat(t).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        raise EventsError(f"{label} YYYY-AA-GGTSS:DD biçiminde olmalı.", 422) from None


def parse_amount(v: Any, label: str, required: bool = False) -> Optional[float]:
    if v is None or v == "":
        if required:
            raise EventsError(f"{label} girilmeli.", 422)
        return None
    if isinstance(v, str):
        t = v.strip().replace(" ", "").replace("₺", "").replace("TL", "")
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):          # «250.000» Türkçe binlik ayracı
            t = t.replace(".", "")
        v = t
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise EventsError(f"{label} sayı olmalı.", 422) from None
    if n != n or n < 0:
        raise EventsError(f"{label} sıfır ya da artı olmalı.", 422)
    return round(n, 2)


def _user(v: Any) -> Optional[str]:
    t = str(v or "").strip().lower()
    t = t.rsplit("\\", 1)[-1].split("@", 1)[0]
    return t[:120] or None


def _json_list(v: Optional[str]) -> list:
    try:
        x = json.loads(v or "[]")
    except ValueError:
        return []
    return x if isinstance(x, list) else []


def phase(starts_on: str, ends_on: str, now: Optional[date] = None) -> str:
    d = (now or today()).isoformat()
    if d < starts_on:
        return "hazirlik"
    if d <= ends_on:
        return "suruyor"
    return "bitti"


def days_until(day: Optional[str], now: Optional[date] = None) -> Optional[int]:
    if not day:
        return None
    return (date.fromisoformat(day[:10]) - (now or today())).days


# ------------------------------------------------------------------ fuar kartı


def fair_stmt(tenant: str, fair_id: str):
    return sa.select(FAIRS).where(FAIRS.c.tenant_id == tenant, FAIRS.c.id == str(fair_id))


def _get_fair(c, tenant: str, fair_id: str) -> dict[str, Any]:
    r = c.execute(fair_stmt(tenant, fair_id)).mappings().first()
    if not r:
        raise EventsError("Fuar/etkinlik kartı bulunamadı.", 404)
    return dict(r)


def fair_row(engine: sa.engine.Engine, tenant: str, fair_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        return _get_fair(c, tenant, fair_id)


def _fair_fields(body: dict[str, Any], cur: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    creating = cur is None
    if creating or "name" in body:
        out["name"] = _text(body.get("name"), 300, "Ad", required=True)
    if creating or "kind" in body:
        kind = str(body.get("kind") or "stant")
        if kind not in FAIR_KINDS:
            raise EventsError("Tür geçersiz.", 422)
        out["kind"] = kind
    if creating or "startsOn" in body or "endsOn" in body:
        a = parse_day(body.get("startsOn", (cur or {}).get("starts_on")), "Başlangıç", required=True)
        b = parse_day(body.get("endsOn", (cur or {}).get("ends_on")) or a.isoformat(), "Bitiş", required=True)
        if b < a:
            raise EventsError("Bitiş başlangıçtan önce olamaz.", 422)
        out["starts_on"], out["ends_on"] = a.isoformat(), b.isoformat()
    for k, col, n in (("city", "city", 120), ("venue", "venue", 300)):
        if creating or k in body:
            out[col] = _text(body.get(k), n)
    if creating or "standInfo" in body:
        out["stand_info"] = _long(body.get("standInfo"), 4000)
    if creating or "note" in body:
        out["note"] = _long(body.get("note"), 4000)
    if creating or "budgetPlanned" in body:
        out["budget_planned"] = parse_amount(body.get("budgetPlanned"), "Planlanan bütçe")
    if creating or "ownerUser" in body:
        out["owner_user"] = _user(body.get("ownerUser"))
    if creating or "crmEventIds" in body:
        from semantic_bridge.events_sources import guids
        raw = body.get("crmEventIds") or []
        if not isinstance(raw, list):
            raise EventsError("CRM etkinlik listesi geçersiz.", 422)
        out["crm_event_ids_json"] = json.dumps(guids(raw))
    if creating or "logoClientCodes" in body:
        from semantic_bridge.events_sources import codes
        raw = body.get("logoClientCodes") or []
        if not isinstance(raw, list):
            raise EventsError("Cari kodu listesi geçersiz.", 422)
        out["logo_client_codes_json"] = json.dumps(codes(raw), ensure_ascii=False)
    if creating or "prevFairId" in body:
        out["prev_fair_id"] = _text(body.get("prevFairId"), 32)
    return out


def create_fair(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any],
                template: Optional[list[dict[str, Any]]] = None) -> str:
    vals = _fair_fields(body)
    vals["owner_user"] = vals.get("owner_user") or _user(user)
    now = _now()
    fid = _id()
    with engine.begin() as c:
        if vals.get("prev_fair_id"):
            _get_fair(c, tenant, vals["prev_fair_id"])
        c.execute(FAIRS.insert().values(id=fid, tenant_id=tenant, status="aday", created_by=user, created_at=now,
                                        updated_at=now, **vals))
        start = date.fromisoformat(vals["starts_on"])
        for i, t in enumerate(template if template is not None else settings()["taskTemplate"]):
            c.execute(TASKS.insert().values(id=_id(), fair_id=fid, title=t["title"], sort=i, created_by=user, created_at=now,
                                            due_on=(start + timedelta(days=int(t.get("days") or 0))).isoformat(),
                                            owner_user=vals["owner_user"]))
    return fid


def update_fair(engine: sa.engine.Engine, tenant: str, user: str, fair_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Kart alanları; `status: iptal` kartı iptal eder, `status: aday` iptali geri alır. Onay yalnız `approve` ile.
    Onaylı kartta tarih ya da bütçe değişirse karar yeniden gerekir (kart «aday»a döner)."""
    with engine.begin() as c:
        cur = _get_fair(c, tenant, fair_id)
        vals = _fair_fields(body, cur)
        if vals.get("prev_fair_id"):
            if vals["prev_fair_id"] == cur["id"]:
                raise EventsError("Kart kendisinin önceki fuarı olamaz.", 422)
            _get_fair(c, tenant, vals["prev_fair_id"])
        diff = {k: [cur.get(k), v] for k, v in vals.items() if cur.get(k) != v}
        if "status" in body:
            st = str(body["status"] or "")
            if st not in ("iptal", "aday"):
                raise EventsError("Durum yalnız iptal edilebilir ya da iptalden geri alınabilir; onay ayrı düğmeyle.", 422)
            if st == "aday" and cur["status"] != "iptal":
                raise EventsError("Yalnız iptal edilmiş kart geri alınabilir.", 409)
            if st != cur["status"]:
                vals["status"] = st
                diff["status"] = [cur["status"], st]
                if st == "aday":
                    vals.update(approved_by=None, approved_at=None)
        reopen = cur["status"] == "onayli" and any(k in diff for k in ("budget_planned", "starts_on", "ends_on"))
        if reopen and vals.get("status") != "iptal":
            vals.update(status="aday", approved_by=None, approved_at=None)
            diff["status"] = ["onayli", "aday"]
        if vals:
            vals["updated_at"] = _now()
            c.execute(FAIRS.update().where(FAIRS.c.id == cur["id"]).values(**vals))
    return {"diff": diff, "reopened": reopen}


def approve_fair(engine: sa.engine.Engine, tenant: str, user: str, fair_id: str, note: Any = None) -> dict[str, Any]:
    """Katılım kararı ve bütçe onayı: kartı açan onaylayamaz (iki göz)."""
    with engine.begin() as c:
        cur = _get_fair(c, tenant, fair_id)
        if cur["status"] != "aday":
            raise EventsError("Yalnız karar bekleyen kart onaylanır.", 409)
        if (cur["created_by"] or "").lower() == (user or "").lower():
            raise EventsError("Kartı açan kişi kendi kartını onaylayamaz.", 403)
        c.execute(FAIRS.update().where(FAIRS.c.id == cur["id"]).values(
            status="onayli", approved_by=user, approved_at=_now(), decision_note=_long(note, 2000), updated_at=_now()))
    return {"id": cur["id"], "name": cur["name"], "budget": cur["budget_planned"]}


def delete_fair(engine: sa.engine.Engine, tenant: str, fair_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        cur = _get_fair(c, tenant, fair_id)
        if cur["status"] == "onayli":
            raise EventsError("Onaylı kart silinemez; iptal edin.", 409)
        for t in (BOOKS, TASKS, COSTS, AUTHORS):
            c.execute(t.delete().where(t.c.fair_id == cur["id"]))
        c.execute(REMINDERS.delete().where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.ref_id == cur["id"]))
        c.execute(FAIRS.update().where(FAIRS.c.prev_fair_id == cur["id"]).values(prev_fair_id=None))
        c.execute(FAIRS.delete().where(FAIRS.c.id == cur["id"]))
    d = files_root() / cur["id"]
    if d.is_dir():
        for f in d.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
        try:
            d.rmdir()
        except OSError:
            pass
    return cur


def _task_view(r: dict[str, Any], now: date) -> dict[str, Any]:
    left = days_until(r["due_on"], now)
    return {"id": r["id"], "title": r["title"], "dueOn": r["due_on"], "owner": r["owner_user"], "done": r["done_at"] is not None,
            "doneAt": _iso(r["done_at"]), "doneBy": r["done_by"], "daysLeft": left,
            "late": r["done_at"] is None and left is not None and left < 0}


def fair_view(row: dict[str, Any], tasks: list[dict[str, Any]], costs: list[dict[str, Any]], now: Optional[date] = None,
              books_n: int = 0) -> dict[str, Any]:
    now = now or today()
    ts = [_task_view(t, now) for t in sorted(tasks, key=lambda t: (t["due_on"] or "9999", t["sort"] or 0))]
    done = sum(1 for t in ts if t["done"])
    cost = round(sum(float(x["amount"] or 0) for x in costs), 2)
    ph = phase(row["starts_on"], row["ends_on"], now)
    res = json.loads(row["result_json"]) if row.get("result_json") else None
    return {
        "id": row["id"], "name": row["name"], "kind": row["kind"], "kindLabel": FAIR_KINDS.get(row["kind"], row["kind"]),
        "startsOn": row["starts_on"], "endsOn": row["ends_on"], "city": row["city"], "venue": row["venue"],
        "standInfo": row["stand_info"], "note": row["note"], "budgetPlanned": row["budget_planned"],
        "status": row["status"], "statusLabel": FAIR_STATUSES.get(row["status"], row["status"]),
        "phase": ph, "phaseLabel": PHASES[ph], "daysLeft": days_until(row["starts_on"], now),
        "owner": row["owner_user"], "crmEventIds": _json_list(row["crm_event_ids_json"]),
        "logoClientCodes": _json_list(row["logo_client_codes_json"]), "prevFairId": row["prev_fair_id"],
        "approvedBy": row["approved_by"], "approvedAt": _iso(row["approved_at"]), "decisionNote": row["decision_note"],
        "createdBy": row["created_by"], "createdAt": _iso(row["created_at"]), "updatedAt": _iso(row["updated_at"]),
        "tasksTotal": len(ts), "tasksDone": done, "tasksLate": sum(1 for t in ts if t["late"]),
        "prep": (done / len(ts)) if ts else None, "costTotal": cost, "books": books_n,
        "resultAt": _iso(row["result_at"]),
        "resultSummary": ({k: res.get(k) for k in ("netCiro", "netAdet", "toplamGider", "roi")} if res else None),
    }


def fairs_stmts(tenant: str, year: Optional[int] = None) -> tuple[Any, Any, Any, Any]:
    """(kartlar, görevleri, giderleri, kart başına kitap sayısı); kart süzgeci alt sorguyla."""
    cond = [FAIRS.c.tenant_id == tenant]
    if year:
        cond += [FAIRS.c.starts_on < f"{year + 1}-01-01", FAIRS.c.ends_on >= f"{year}-01-01"]
    ids = sa.select(FAIRS.c.id).where(*cond)
    return (sa.select(FAIRS).where(*cond).order_by(FAIRS.c.starts_on, FAIRS.c.name),
            sa.select(TASKS).where(TASKS.c.fair_id.in_(ids)),
            sa.select(COSTS.c.fair_id, COSTS.c.amount).where(COSTS.c.fair_id.in_(ids)),
            sa.select(BOOKS.c.fair_id, sa.func.count()).where(BOOKS.c.fair_id.in_(ids)).group_by(BOOKS.c.fair_id))


def list_fairs(engine: sa.engine.Engine, tenant: str, year: Optional[int] = None, *, active_only: bool = False,
               now: Optional[date] = None) -> list[dict[str, Any]]:
    fq, tq, cq, bq = fairs_stmts(tenant, year)
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(fq).mappings()]
        ids = [r["id"] for r in rows]
        tasks: dict[str, list] = {i: [] for i in ids}
        costs: dict[str, list] = {i: [] for i in ids}
        books: dict[str, int] = {}
        if ids:
            for t in c.execute(tq).mappings():
                if t["fair_id"] in tasks:
                    tasks[t["fair_id"]].append(dict(t))
            for x in c.execute(cq).mappings():
                if x["fair_id"] in costs:
                    costs[x["fair_id"]].append(dict(x))
            for fid, n in c.execute(bq):
                books[fid] = int(n)
    out = [fair_view(r, tasks[r["id"]], costs[r["id"]], now, books.get(r["id"], 0)) for r in rows]
    if active_only:
        out = [f for f in out if f["status"] != "iptal"]
    return out


def fair_detail_stmts(tenant: str, fair_id: str) -> tuple[Any, Any, Any, Any, Any]:
    """Kart ekranı: (kart, görevler, giderler, kitaplar, yazar programı)."""
    fid = str(fair_id)
    return (fair_stmt(tenant, fid), sa.select(TASKS).where(TASKS.c.fair_id == fid),
            sa.select(COSTS).where(COSTS.c.fair_id == fid).order_by(COSTS.c.created_at),
            sa.select(BOOKS).where(BOOKS.c.fair_id == fid),
            sa.select(AUTHORS).where(AUTHORS.c.fair_id == fid).order_by(AUTHORS.c.slot_start))


def fair_detail(engine: sa.engine.Engine, tenant: str, fair_id: str, now: Optional[date] = None) -> dict[str, Any]:
    now = now or today()
    with engine.connect() as c:
        row = _get_fair(c, tenant, fair_id)
        _fq, tq, cq, bq, aq = fair_detail_stmts(tenant, row["id"])
        tasks = [dict(t) for t in c.execute(tq).mappings()]
        costs = [dict(x) for x in c.execute(cq).mappings()]
        books = [dict(b) for b in c.execute(bq).mappings()]
        authors = [dict(a) for a in c.execute(aq).mappings()]
        prev = None
        if row["prev_fair_id"]:
            p = c.execute(sa.select(FAIRS.c.id, FAIRS.c.name, FAIRS.c.starts_on, FAIRS.c.ends_on)
                          .where(FAIRS.c.tenant_id == tenant, FAIRS.c.id == row["prev_fair_id"])).mappings().first()
            prev = dict(p) if p else None
        clash = author_conflicts(c, [a for a in authors if a["crm_contact_id"]])
    v = fair_view(row, tasks, costs, now, len(books))
    v["tasks"] = [_task_view(t, now) for t in sorted(tasks, key=lambda t: (t["due_on"] or "9999", t["sort"] or 0))]
    v["costs"] = [{"id": x["id"], "kind": x["kind"], "kindLabel": COST_KINDS.get(x["kind"], x["kind"]), "amount": x["amount"],
                   "note": x["note"], "hasReceipt": bool(x["receipt_ref"]), "by": x["created_by"], "at": _iso(x["created_at"])}
                  for x in costs]
    v["costByKind"] = {k: round(sum(float(x["amount"]) for x in costs if x["kind"] == k), 2) for k in COST_KINDS
                       if any(x["kind"] == k for x in costs)}
    v["bookList"] = sorted((book_view(b) for b in books), key=lambda b: (not b["featured"], -(b["qtyPlanned"] or b["qtySuggested"] or 0), b["ad"] or ""))
    v["authors"] = [{"id": a["id"], "contactId": a["crm_contact_id"], "name": a["name"], "slotStart": a["slot_start"],
                     "slotEnd": a["slot_end"], "note": a["note"], "conflicts": clash.get(a["id"], [])} for a in authors]
    v["prev"] = ({"id": prev["id"], "name": prev["name"], "startsOn": prev["starts_on"], "endsOn": prev["ends_on"]} if prev else None)
    v["result"] = json.loads(row["result_json"]) if row.get("result_json") else None
    return v


def book_view(b: dict[str, Any]) -> dict[str, Any]:
    need = b["qty_planned"] if b["qty_planned"] is not None else b["qty_suggested"]
    return {"stokKodu": b["stok_kodu"], "crmBookId": b["crm_book_id"], "ad": b["ad"], "qtySuggested": b["qty_suggested"],
            "qtyPlanned": b["qty_planned"], "qtySold": b["qty_sold"], "stock": b["stock"], "basisQty": b["basis_qty"],
            "featured": bool(b["featured"]), "reason": b["reason"], "source": b["source"],
            "stockShort": b["stock"] is not None and need is not None and b["stock"] < need,
            "sellThrough": (b["qty_sold"] / b["qty_planned"]) if b["qty_sold"] is not None and b["qty_planned"] else None}


# ------------------------------------------------------------------ görevler, gider, yazar programı


def add_task(engine, tenant: str, user: str, fair_id: str, body: dict[str, Any]) -> dict[str, Any]:
    title = _text(body.get("title"), 300, "Görev", required=True)
    due = parse_day(body.get("dueOn"), "Son tarih")
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        n = c.execute(sa.select(sa.func.count()).select_from(TASKS).where(TASKS.c.fair_id == f["id"])).scalar() or 0
        tid = _id()
        c.execute(TASKS.insert().values(id=tid, fair_id=f["id"], title=title, due_on=due.isoformat() if due else None,
                                        owner_user=_user(body.get("owner")) or f["owner_user"], sort=int(n),
                                        created_by=user, created_at=_now()))
        c.execute(FAIRS.update().where(FAIRS.c.id == f["id"]).values(updated_at=_now()))
        return {"id": tid, "title": title, "fair": f["name"]}


def patch_task(engine, tenant: str, user: str, fair_id: str, task_id: str, body: dict[str, Any], can_edit: bool) -> dict[str, Any]:
    """Görevi işaretlemek görevin sahibine de açıktır; başlık/tarih/sahip değişikliği düzenleme yetkisi ister."""
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        t = c.execute(sa.select(TASKS).where(TASKS.c.fair_id == f["id"], TASKS.c.id == task_id)).mappings().first()
        if not t:
            raise EventsError("Görev bulunamadı.", 404)
        mine = (t["owner_user"] or "") == (user or "").lower()
        vals: dict[str, Any] = {}
        if any(k in body for k in ("title", "dueOn", "owner")) and not can_edit:
            raise EventsError("Görevi değiştirmek rolünüzde yok; yalnız size atanan görevi işaretleyebilirsiniz.", 403)
        if "done" in body and not (can_edit or mine):
            raise EventsError("Bu görev size atanmamış.", 403)
        if "title" in body:
            vals["title"] = _text(body.get("title"), 300, "Görev", required=True)
        if "dueOn" in body:
            d = parse_day(body.get("dueOn"), "Son tarih")
            vals["due_on"] = d.isoformat() if d else None
        if "owner" in body:
            vals["owner_user"] = _user(body.get("owner"))
        if "done" in body:
            if bool(body["done"]) and t["done_at"] is None:
                vals.update(done_at=_now(), done_by=user)
            elif not bool(body["done"]) and t["done_at"] is not None:
                vals.update(done_at=None, done_by=None)
        if vals:
            c.execute(TASKS.update().where(TASKS.c.id == t["id"]).values(**vals))
        return {"id": t["id"], "title": vals.get("title", t["title"]), "fair": f["name"],
                "diff": {k: str(v) for k, v in vals.items()}}


def delete_task(engine, tenant: str, fair_id: str, task_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        t = c.execute(sa.select(TASKS).where(TASKS.c.fair_id == f["id"], TASKS.c.id == task_id)).mappings().first()
        if not t:
            raise EventsError("Görev bulunamadı.", 404)
        c.execute(TASKS.delete().where(TASKS.c.id == t["id"]))
        c.execute(REMINDERS.delete().where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.ref_id == t["id"]))
        return {"id": t["id"], "title": t["title"], "fair": f["name"]}


def add_cost(engine, tenant: str, user: str, fair_id: str, body: dict[str, Any], max_mb: int = 10) -> dict[str, Any]:
    """Gider: tür + tutar yeter; fiş fotoğrafı isteğe bağlı (`receipt: {type, dataBase64}`)."""
    import base64

    kind = str(body.get("kind") or "diger")
    if kind not in COST_KINDS:
        raise EventsError("Gider türü geçersiz.", 422)
    amount = parse_amount(body.get("amount"), "Tutar", required=True)
    if not amount:
        raise EventsError("Tutar sıfırdan büyük olmalı.", 422)
    rec = body.get("receipt") or None
    data: Optional[bytes] = None
    ctype = None
    if rec:
        ctype = str(rec.get("type") or "").lower()
        if ctype not in RECEIPT_TYPES:
            raise EventsError("Fiş yalnız fotoğraf (JPEG, PNG, WEBP, HEIC) ya da PDF olabilir.", 415)
        try:
            data = base64.b64decode(str(rec.get("dataBase64") or ""), validate=True)
        except ValueError:
            raise EventsError("Fiş dosyası okunamadı.", 422) from None
        if not data:
            raise EventsError("Fiş dosyası boş.", 422)
        if len(data) > max_mb * 1024 * 1024:
            raise EventsError(f"Fiş dosyası {max_mb} MB'tan büyük olamaz.", 413)
    cid = _id()
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        ref = None
        if data is not None:
            d = files_root() / f["id"]
            d.mkdir(parents=True, exist_ok=True)
            ref = cid + RECEIPT_TYPES[ctype]
            (d / ref).write_bytes(data)
        c.execute(COSTS.insert().values(id=cid, fair_id=f["id"], kind=kind, amount=amount, note=_text(body.get("note"), 400),
                                        receipt_ref=ref, receipt_type=ctype, created_by=user, created_at=_now()))
        c.execute(FAIRS.update().where(FAIRS.c.id == f["id"]).values(updated_at=_now()))
    return {"id": cid, "fair": f["name"], "kind": kind, "amount": amount, "receipt": bool(ref)}


def delete_cost(engine, tenant: str, fair_id: str, cost_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        x = c.execute(sa.select(COSTS).where(COSTS.c.fair_id == f["id"], COSTS.c.id == cost_id)).mappings().first()
        if not x:
            raise EventsError("Gider bulunamadı.", 404)
        c.execute(COSTS.delete().where(COSTS.c.id == x["id"]))
    if x["receipt_ref"]:
        try:
            (files_root() / f["id"] / x["receipt_ref"]).unlink()
        except OSError:
            pass
    return {"id": x["id"], "fair": f["name"], "kind": x["kind"], "amount": x["amount"]}


def receipt(engine, tenant: str, fair_id: str, cost_id: str) -> tuple[bytes, str, str]:
    with engine.connect() as c:
        f = _get_fair(c, tenant, fair_id)
        x = c.execute(sa.select(COSTS).where(COSTS.c.fair_id == f["id"], COSTS.c.id == cost_id)).mappings().first()
    if not x or not x["receipt_ref"]:
        raise EventsError("Bu giderin fişi yok.", 404)
    p = files_root() / f["id"] / x["receipt_ref"]
    if not p.is_file():
        raise EventsError("Fiş dosyası sunucuda bulunamadı.", 404)
    return p.read_bytes(), x["receipt_type"] or "application/octet-stream", x["receipt_ref"]


def author_conflicts(c, authors: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Aynı yazarın başka bir kartta (iptal olmayan) çakışan saati: kayıt kimliği → çakışan kayıtlar."""
    ids = sorted({a["crm_contact_id"] for a in authors if a["crm_contact_id"] and a["slot_start"]})
    if not ids:
        return {}
    others = [dict(r) for r in c.execute(
        sa.select(AUTHORS, FAIRS.c.name.label("fair_name"), FAIRS.c.status)
        .join(FAIRS, FAIRS.c.id == AUTHORS.c.fair_id)
        .where(AUTHORS.c.crm_contact_id.in_(ids), AUTHORS.c.slot_start.isnot(None), FAIRS.c.status != "iptal")).mappings()]
    out: dict[str, list[dict[str, Any]]] = {}
    for a in authors:
        if not a["slot_start"]:
            continue
        a_end = a["slot_end"] or a["slot_start"]
        for o in others:
            if o["id"] == a["id"] or o["crm_contact_id"] != a["crm_contact_id"]:
                continue
            o_end = o["slot_end"] or o["slot_start"]
            if o["slot_start"] <= a_end and a["slot_start"] <= o_end:
                out.setdefault(a["id"], []).append({"fair": o["fair_name"], "fairId": o["fair_id"], "slotStart": o["slot_start"],
                                                    "slotEnd": o["slot_end"]})
    return out


def add_author(engine, tenant: str, user: str, fair_id: str, body: dict[str, Any]) -> dict[str, Any]:
    from semantic_bridge.events_sources import guids

    name = _text(body.get("name"), 300, "Yazar adı", required=True)
    contact = (guids([body.get("contactId")]) or [None])[0]
    a, b = parse_slot(body.get("slotStart"), "Başlangıç saati"), parse_slot(body.get("slotEnd"), "Bitiş saati")
    if a and b and b < a:
        raise EventsError("Bitiş saati başlangıçtan önce olamaz.", 422)
    aid = _id()
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        c.execute(AUTHORS.insert().values(id=aid, fair_id=f["id"], crm_contact_id=contact, name=name, slot_start=a, slot_end=b,
                                          note=_text(body.get("note"), 400), created_by=user, created_at=_now()))
        clash = author_conflicts(c, [{"id": aid, "crm_contact_id": contact, "slot_start": a, "slot_end": b}])
    return {"id": aid, "name": name, "fair": f["name"], "conflicts": clash.get(aid, [])}


def delete_author(engine, tenant: str, fair_id: str, author_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        a = c.execute(sa.select(AUTHORS).where(AUTHORS.c.fair_id == f["id"], AUTHORS.c.id == author_id)).mappings().first()
        if not a:
            raise EventsError("Yazar programı kaydı bulunamadı.", 404)
        c.execute(AUTHORS.delete().where(AUTHORS.c.id == a["id"]))
    return {"id": a["id"], "name": a["name"], "fair": f["name"]}


# ------------------------------------------------------------------ kitap ve adet önerisi


def basis_window(fair: dict[str, Any], prev: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Önerinin ve karşılaştırmanın temeli: bağlı önceki fuar kartı, yoksa aynı günlerin 364 gün öncesi (haftanın
    aynı günü). Cari kodları önceki kartınki, yoksa bu kartınki."""
    if prev:
        return {"from": prev["starts_on"], "to": prev["ends_on"], "codes": _json_list(prev["logo_client_codes_json"])
                or _json_list(fair["logo_client_codes_json"]), "label": f"önceki fuar «{prev['name']}»", "prevId": prev["id"]}
    a = date.fromisoformat(fair["starts_on"]) - timedelta(days=364)
    b = date.fromisoformat(fair["ends_on"]) - timedelta(days=364)
    return {"from": a.isoformat(), "to": b.isoformat(), "codes": _json_list(fair["logo_client_codes_json"]),
            "label": "geçen yılın aynı günleri", "prevId": None}


def aggregate_books(sales_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in sales_rows:
        code = (r.get("stokKodu") or "").strip()
        if not code:
            continue
        cur = out.setdefault(code.upper(), {"stokKodu": code, "ad": r.get("ad"), "adet": 0.0, "ciro": 0.0})
        cur["adet"] += float(r.get("adet") or 0)
        cur["ciro"] += float(r.get("ciro") or 0)
        if not cur["ad"] and r.get("ad"):
            cur["ad"] = r["ad"]
    return out


def suggest_books(basis_rows: list[dict[str, Any]], stock: Optional[dict[str, float]], books: dict[str, dict[str, Any]],
                  st: dict[str, Any], starts_on: str, basis_label: str) -> list[dict[str, Any]]:
    """Kurala dayalı öneri (bkz. modül açıklaması). Her satırda gerekçe; stok eksikse işaret. Stok bilinmiyorsa (Logo
    okunamadı) yeni çıkanlar stok şartı aranmadan girer."""
    basis = aggregate_books(basis_rows)
    out: list[dict[str, Any]] = []
    sold = [b["adet"] for b in basis.values() if b["adet"] > 0]
    factor = float(st["suggestFactor"])
    for key, b in sorted(basis.items(), key=lambda kv: -kv[1]["adet"]):
        if b["adet"] <= 0:
            continue
        q = math.ceil(round(b["adet"] * factor, 6))
        card = books.get(key) or {}
        s = (stock or {}).get(key) if stock is not None else None
        reason = f"{basis_label}: {_n(b['adet'])} adet net satış"
        if factor != 1.0:
            reason += f" × {str(factor).replace('.', ',')}"
        if s is not None and s < q:
            reason += f"; stok {_n(s)} adet, önerinin altında"
        out.append({"stokKodu": b["stokKodu"], "crmBookId": card.get("id"), "ad": card.get("ad") or b["ad"], "qty": q,
                    "basisQty": round(b["adet"], 2), "stock": s, "reason": reason, "kind": "gecmis"})
    months = int(st["newBookMonths"])
    if months > 0:
        start = date.fromisoformat(starts_on)
        since = (start - timedelta(days=round(months * 30.44))).isoformat()
        med = statistics.median(sold) if sold else None
        nf = float(st["newBookFactor"])
        for key, card in sorted(books.items(), key=lambda kv: kv[1].get("ilkYayin") or "", reverse=True):
            ilk = card.get("ilkYayin")
            if not ilk or ilk < since or ilk > starts_on or key in basis:
                continue
            s = (stock or {}).get(key) if stock is not None else None
            if stock is not None and (s is None or s <= 0):
                continue
            q = math.ceil(round(med * nf, 6)) if med is not None else None
            reason = f"yeni çıkan (ilk yayın {_tr_day(ilk)})"
            reason += (f"; adet = temeldeki satan kitapların ortancası {_n(med)} × {str(nf).replace('.', ',')}" if q is not None
                       else "; temelde satış olmadığı için adet elle girilmeli")
            if s is not None and q is not None and s < q:
                reason += f"; stok {_n(s)} adet, önerinin altında"
            out.append({"stokKodu": card.get("stokKodu") or key, "crmBookId": card.get("id"), "ad": card.get("ad"), "qty": q,
                        "basisQty": None, "stock": s, "reason": reason, "kind": "yeni"})
    return out


def save_suggestions(engine, tenant: str, user: str, fair_id: str, items: list[dict[str, Any]]) -> dict[str, int]:
    """Öneriyi kitap listesine yazar: elle planlanmış adet ve «öne çıkar» işareti korunur; öneride artık olmayan
    Zeki satırı (elle planlanmamışsa) silinir."""
    now = _now()
    added = updated = removed = 0
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        cur = {r["stok_kodu"].upper(): dict(r) for r in c.execute(sa.select(BOOKS).where(BOOKS.c.fair_id == f["id"])).mappings()}
        seen = set()
        for it in items:
            code = str(it["stokKodu"])[:60]
            key = code.upper()
            seen.add(key)
            vals = {"qty_suggested": it["qty"], "stock": it["stock"], "basis_qty": it["basisQty"], "reason": it["reason"][:2000],
                    "crm_book_id": it.get("crmBookId"), "ad": (it.get("ad") or "")[:400] or None, "updated_at": now}
            if key in cur:
                c.execute(BOOKS.update().where(BOOKS.c.fair_id == f["id"], BOOKS.c.stok_kodu == cur[key]["stok_kodu"]).values(**vals))
                updated += 1
            else:
                c.execute(BOOKS.insert().values(fair_id=f["id"], stok_kodu=code, featured=False, source="zeki", updated_by=user, **vals))
                added += 1
        for key, r in cur.items():
            if key not in seen and r["source"] == "zeki" and r["qty_planned"] is None and not r["featured"]:
                c.execute(BOOKS.delete().where(BOOKS.c.fair_id == f["id"], BOOKS.c.stok_kodu == r["stok_kodu"]))
                removed += 1
            elif key not in seen and r["source"] == "zeki":
                c.execute(BOOKS.update().where(BOOKS.c.fair_id == f["id"], BOOKS.c.stok_kodu == r["stok_kodu"])
                          .values(qty_suggested=None, reason="son öneride yok (elle tutuldu)", updated_at=now))
        c.execute(FAIRS.update().where(FAIRS.c.id == f["id"]).values(updated_at=now))
    return {"added": added, "updated": updated, "removed": removed}


def put_books(engine, tenant: str, user: str, fair_id: str, items: Any, books: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    """Planlanan adet ve «öne çıkar» işareti. Listede olmayan elle satır silinir; Zeki satırında yalnız plan boşalır.
    Yeni kitap eklemek için stok kodu yeter (kitap kartı CRM'den)."""
    if not isinstance(items, list):
        raise EventsError("Kitap listesi geçersiz.", 422)
    now = _now()
    diff = []
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        cur = {r["stok_kodu"].upper(): dict(r) for r in c.execute(sa.select(BOOKS).where(BOOKS.c.fair_id == f["id"])).mappings()}
        seen = set()
        for it in items:
            if not isinstance(it, dict):
                raise EventsError("Kitap satırı geçersiz.", 422)
            code = _text(it.get("stokKodu"), 60, "Stok kodu", required=True)
            key = code.upper()
            if key in seen:
                raise EventsError(f"{code} listede iki kez var.", 422)
            seen.add(key)
            qty = parse_amount(it.get("qtyPlanned"), f"{code} adedi")
            feat = bool(it.get("featured"))
            if key in cur:
                r = cur[key]
                if r["qty_planned"] != qty or bool(r["featured"]) != feat:
                    diff.append({"stok": code, "adet": [r["qty_planned"], qty], "one": [bool(r["featured"]), feat]})
                    c.execute(BOOKS.update().where(BOOKS.c.fair_id == f["id"], BOOKS.c.stok_kodu == r["stok_kodu"])
                              .values(qty_planned=qty, featured=feat, updated_by=user, updated_at=now))
            else:
                card = (books or {}).get(key)
                if books is not None and not card:
                    raise EventsError(f"{code} CRM kitap kartlarında yok.", 422)
                diff.append({"stok": code, "adet": [None, qty], "yeni": True})
                c.execute(BOOKS.insert().values(fair_id=f["id"], stok_kodu=(card or {}).get("stokKodu") or code,
                                                crm_book_id=(card or {}).get("id"), ad=(card or {}).get("ad") or it.get("ad"),
                                                qty_planned=qty, featured=feat, source="elle", reason="elle eklendi",
                                                updated_by=user, updated_at=now))
        for key, r in cur.items():
            if key in seen:
                continue
            if r["source"] == "elle":
                c.execute(BOOKS.delete().where(BOOKS.c.fair_id == f["id"], BOOKS.c.stok_kodu == r["stok_kodu"]))
                diff.append({"stok": r["stok_kodu"], "silindi": True})
            elif r["qty_planned"] is not None or r["featured"]:
                c.execute(BOOKS.update().where(BOOKS.c.fair_id == f["id"], BOOKS.c.stok_kodu == r["stok_kodu"])
                          .values(qty_planned=None, featured=False, updated_by=user, updated_at=now))
                diff.append({"stok": r["stok_kodu"], "adet": [r["qty_planned"], None]})
        c.execute(FAIRS.update().where(FAIRS.c.id == f["id"]).values(updated_at=now))
    return {"fair": f["name"], "diff": diff}


# ------------------------------------------------------------------ fuar sonucu


def result_window(fair: dict[str, Any], tail_days: int) -> tuple[date, date]:
    """[başlangıç, bitiş + 1 + kuyruk) — Logo ve CRM okumasında üst sınır hariç."""
    a = date.fromisoformat(fair["starts_on"])
    b = date.fromisoformat(fair["ends_on"]) + timedelta(days=1 + max(0, tail_days))
    return a, b


def compute_result(fair: dict[str, Any], *, sales: dict[str, Any], prev_sales: Optional[dict[str, Any]], basis: dict[str, Any],
                   orders: list[dict[str, Any]], crm_events: list[dict[str, Any]], costs: list[dict[str, Any]],
                   planned: list[dict[str, Any]], data_end: Optional[str], tail_days: int, logo_error: Optional[str] = None,
                   crm_error: Optional[str] = None) -> dict[str, Any]:
    """Fuar sonucu (saf hesap). `sales`/`prev_sales` = `Source.fair_sales` çıktısı; satırlar tam gelir, kesilmez."""
    a, b = result_window(fair, tail_days)
    books = aggregate_books(sales.get("rows") or [])
    clients: dict[str, dict[str, Any]] = {}
    for r in sales.get("rows") or []:
        k = r.get("cariKodu") or "—"
        cur = clients.setdefault(k, {"kod": k, "ad": r.get("cariAdi"), "adet": 0.0, "ciro": 0.0})
        cur["adet"] += float(r.get("adet") or 0)
        cur["ciro"] += float(r.get("ciro") or 0)
    net_ciro = round(sum(x["ciro"] for x in books.values()), 2)
    net_adet = round(sum(x["adet"] for x in books.values()), 2)
    prev_books = aggregate_books((prev_sales or {}).get("rows") or []) if prev_sales else {}
    prev_ciro = round(sum(x["ciro"] for x in prev_books.values()), 2) if prev_sales else None
    prev_adet = round(sum(x["adet"] for x in prev_books.values()), 2) if prev_sales else None
    plan = {p["stok_kodu"].upper(): p for p in planned}
    book_rows = []
    for key, x in sorted(books.items(), key=lambda kv: -kv[1]["ciro"]):
        p = plan.get(key)
        book_rows.append({"stokKodu": x["stokKodu"], "ad": (p or {}).get("ad") or x["ad"], "adet": round(x["adet"], 2),
                          "ciro": round(x["ciro"], 2), "gecenYilAdet": round(prev_books[key]["adet"], 2) if key in prev_books else None,
                          "planlanan": (p or {}).get("qty_planned")})
    unsold = [{"stokKodu": p["stok_kodu"], "ad": p["ad"], "planlanan": p["qty_planned"]}
              for k, p in plan.items() if p["qty_planned"] and k not in books]
    by_type: dict[str, dict[str, Any]] = {}
    for o in orders:
        t = by_type.setdefault(str(o["tip"]), {"tip": o["tip"], "ad": o.get("tipAdi"), "adet": 0, "tutar": 0.0})
        t["adet"] += 1
        t["tutar"] += float(o.get("tutar") or 0)
    ev = [e for e in crm_events if not e.get("iptal")]
    crm_cost = round(sum(float(e.get("gider") or 0) for e in ev), 2)
    portal_cost = round(sum(float(x["amount"] or 0) for x in costs), 2)
    by_kind = {COST_KINDS.get(k, k): round(sum(float(x["amount"]) for x in costs if x["kind"] == k), 2)
               for k in dict.fromkeys(x["kind"] for x in costs)}
    total_cost = round(portal_cost + crm_cost, 2)
    planned_total = sum(float(p["qty_planned"] or 0) for p in planned)
    sold_planned = sum(books[k]["adet"] for k in plan if k in books and plan[k]["qty_planned"])
    last_day = (b - timedelta(days=1)).isoformat()
    warnings = list(sales.get("warnings") or [])
    if logo_error:
        warnings.append(f"Logo okunamadı: {logo_error}")
    if crm_error:
        warnings.append(f"CRM okunamadı: {crm_error}")
    if data_end and data_end < last_day:
        warnings.append(f"Satış verisi {_tr_day(data_end)} tarihine kadar; fuarın {_tr_day(max(data_end, a.isoformat()))} "
                        "sonrasındaki satışı rapora girmedi.")
    if not fair["logo_client_codes_json"] or not _json_list(fair["logo_client_codes_json"]):
        warnings.append("Fuara Logo carisi bağlanmadı: aynı günlerde bütün fuar kanalı satışı sayıldı (aynı anda başka "
                        "fuar varsa ikisi birlikte).")
    if not costs and not crm_cost:
        warnings.append("Gider girilmedi; maliyet–getiri hesaplanamadı.")
    out = {
        "window": {"from": a.isoformat(), "to": last_day, "tailDays": tail_days},
        "dataEnd": data_end, "channel": sales.get("channel"), "clientCodes": _json_list(fair["logo_client_codes_json"]),
        "netCiro": net_ciro, "netAdet": net_adet, "kitapSayisi": len([x for x in books.values() if x["adet"] > 0]),
        "books": book_rows, "clients": sorted(clients.values(), key=lambda x: -x["ciro"]),
        "unsoldPlanned": unsold, "plannedTotal": planned_total or None,
        "sellThrough": (sold_planned / planned_total) if planned_total else None,
        "prev": ({"label": basis["label"], "from": basis["from"], "to": basis["to"], "netCiro": prev_ciro, "netAdet": prev_adet,
                  "degisim": ((net_ciro - prev_ciro) / prev_ciro) if prev_ciro else None} if prev_sales is not None else None),
        "orders": sorted(by_type.values(), key=lambda x: x["tip"] or 0),
        "orderCount": len(orders), "orderTotal": round(sum(float(o.get("tutar") or 0) for o in orders), 2),
        "crmEvents": [{"id": e["id"], "ad": e["ad"], "baslangic": e["baslangic"], "katilimci": e.get("katilimci"),
                       "satilan": e.get("satilan"), "gider": e.get("gider"), "durum": e.get("durumAdi")} for e in crm_events],
        "katilimci": sum(int(e.get("katilimci") or 0) for e in ev) or None,
        "crmSatilan": sum(int(e.get("satilan") or 0) for e in ev) or None,
        "costs": {"portal": portal_cost, "crm": crm_cost, "byKind": by_kind},
        "toplamGider": total_cost, "butce": fair["budget_planned"],
        "butceFarki": (round(total_cost - fair["budget_planned"], 2) if fair["budget_planned"] is not None else None),
        "roi": (net_ciro / total_cost) if total_cost > 0 else None,
        "warnings": warnings, "sql": sales.get("sql") or [],
        "computedAt": _now().isoformat(),
    }
    out["summary"] = summary_sentences(fair, out)
    return out


def summary_sentences(fair: dict[str, Any], r: dict[str, Any]) -> list[str]:
    """Rakamlardan kuralla yazılan yorum (model üretmez)."""
    s = [f"{_tr_day(r['window']['from'])}–{_tr_day(r['window']['to'])} arasında fuar kanalından {_money(r['netCiro'])} net satış, "
         f"{_n(r['netAdet'])} adet ({_n(r['kitapSayisi'])} farklı kitap)."]
    p = r.get("prev")
    if p and p.get("netCiro") is not None:
        if p["netCiro"]:
            yon = "arttı" if r["netCiro"] >= p["netCiro"] else "azaldı"
            pct = f"{abs(p.get('degisim') or 0) * 100:.1f}".replace(".", ",")
            s.append(f"Temel dönem ({p['label']}) {_money(p['netCiro'])}; net satış %{pct} {yon}.")
        else:
            s.append(f"Temel dönemde ({p['label']}) fuar kanalı satışı yok.")
    if r["orderCount"]:
        s.append(f"CRM'de bu günlerde {r['orderCount']} fuar/etkinlik/imza siparişi, toplam {_money(r['orderTotal'])}.")
    if r["toplamGider"] > 0:
        roi = f"{r['roi']:.2f}".replace(".", ",") if r.get("roi") is not None else None
        s.append(f"Toplam gider {_money(r['toplamGider'])}" + (f"; her 1 TL gidere {roi} TL net satış." if roi else "."))
    else:
        s.append("Gider girilmediği için maliyet–getiri hesaplanamadı.")
    if r.get("sellThrough") is not None:
        s.append(f"Götürülen planlı adedin %{r['sellThrough'] * 100:.0f}'i satıldı; {len(r['unsoldPlanned'])} planlı kitap hiç satılmadı.")
    return s


def save_result(engine, tenant: str, fair_id: str, result: dict[str, Any]) -> None:
    sold = {b["stokKodu"].upper(): b["adet"] for b in result.get("books") or []}
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        c.execute(FAIRS.update().where(FAIRS.c.id == f["id"]).values(result_json=json.dumps(result, ensure_ascii=False, default=str),
                                                                     result_at=_now()))
        for r in c.execute(sa.select(BOOKS.c.stok_kodu).where(BOOKS.c.fair_id == f["id"])).scalars().all():
            c.execute(BOOKS.update().where(BOOKS.c.fair_id == f["id"], BOOKS.c.stok_kodu == r)
                      .values(qty_sold=sold.get(r.upper(), 0.0)))


def planned_books_stmt(fair_id: str):
    return sa.select(BOOKS).where(BOOKS.c.fair_id == fair_id)


def fair_costs_stmt(fair_id: str):
    return sa.select(COSTS).where(COSTS.c.fair_id == fair_id)


def planned_books(engine, fair_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [dict(r) for r in c.execute(planned_books_stmt(fair_id)).mappings()]


def fair_costs(engine, fair_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [dict(r) for r in c.execute(fair_costs_stmt(fair_id)).mappings()]


# ------------------------------------------------------------------ CRM etkinlik tipi eşlemesi


def type_map_stmt(tenant: str):
    return sa.select(TYPE_MAP).where(TYPE_MAP.c.tenant_id == tenant)


def type_map(engine, tenant: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        return {r["crm_type_id"]: dict(r) for r in c.execute(type_map_stmt(tenant)).mappings()}


def type_rows(types: list[dict[str, Any]], tmap: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for t in types:
        m = tmap.get(t["id"]) or {}
        out.append({"id": t["id"], "name": t["ad"], "active": t["etkin"], "count": t["adet"], "last": t["son"],
                    "class": m.get("sinif"), "decidedBy": m.get("decided_by"), "decidedAt": _iso(m.get("decided_at")),
                    "suggested": m.get("suggested"), "suggestedProb": m.get("suggested_prob"),
                    "suggestedMargin": m.get("suggested_margin"), "suggestedMethod": m.get("suggested_method")})
    out.sort(key=lambda x: (x["class"] is not None, -x["count"], fold(x["name"])))
    return out


def set_types(engine, tenant: str, user: str, items: Any, names: dict[str, str]) -> list[dict[str, Any]]:
    """İnsan kararı: `[{id, class}]`; `class: null` kararı kaldırır (öneri kalır)."""
    from semantic_bridge.events_sources import guids

    if not isinstance(items, list) or not items:
        raise EventsError("Eşleme listesi boş.", 422)
    diff = []
    now = _now()
    with engine.begin() as c:
        cur = {r["crm_type_id"]: dict(r) for r in c.execute(sa.select(TYPE_MAP).where(TYPE_MAP.c.tenant_id == tenant)).mappings()}
        for it in items:
            if not isinstance(it, dict):
                raise EventsError("Eşleme satırı geçersiz.", 422)
            tid = (guids([it.get("id")]) or [None])[0]
            if not tid:
                raise EventsError("Etkinlik tipi kimliği geçersiz.", 422)
            if names and tid not in names:
                raise EventsError("Bu etkinlik tipi CRM'de yok.", 404)
            cls = it.get("class")
            if cls is not None and cls not in CLASSES:
                raise EventsError("Sınıf geçersiz.", 422)
            old = cur.get(tid)
            if old and old["sinif"] == cls:
                continue
            vals = {"sinif": cls, "decided_by": user if cls else None, "decided_at": now if cls else None,
                    "name": (names or {}).get(tid) or (old or {}).get("name")}
            if old:
                c.execute(TYPE_MAP.update().where(TYPE_MAP.c.tenant_id == tenant, TYPE_MAP.c.crm_type_id == tid).values(**vals))
            else:
                c.execute(TYPE_MAP.insert().values(tenant_id=tenant, crm_type_id=tid, **vals))
            diff.append({"id": tid, "name": vals["name"], "class": [(old or {}).get("sinif"), cls]})
    return diff


def save_type_suggestion(engine, tenant: str, tid: str, name: str, choice: Any) -> None:
    label_to_key = {v: k for k, v in CLASSES.items()}
    key = label_to_key.get(getattr(choice, "choice", None) or "")
    vals = {"suggested": key, "suggested_prob": getattr(choice, "probability", None),
            "suggested_margin": getattr(choice, "margin", None), "suggested_method": str(getattr(choice, "method", "") or "")[:12],
            "suggested_at": _now(), "name": name}
    with engine.begin() as c:
        ex = c.execute(sa.select(TYPE_MAP.c.crm_type_id).where(TYPE_MAP.c.tenant_id == tenant, TYPE_MAP.c.crm_type_id == tid)).first()
        if ex:
            c.execute(TYPE_MAP.update().where(TYPE_MAP.c.tenant_id == tenant, TYPE_MAP.c.crm_type_id == tid).values(**vals))
        else:
            c.execute(TYPE_MAP.insert().values(tenant_id=tenant, crm_type_id=tid, **vals))


def type_prompt(name: str, count: int, samples: list[str]) -> str:
    hints = "\n".join(f"- {v}: {CLASS_HINTS[k]}" for k, v in CLASSES.items())
    ex = ("\nBu tipteki etkinliklerden örnek adlar: " + "; ".join(samples[:5])) if samples else ""
    return (f"Bir yayınevinin müşteri kayıt sisteminde «{name}» adlı bir etkinlik tipi var ({count} etkin kayıt).{ex}\n"
            f"Bu tip hangi sınıfa girer?\n{hints}")


def classify_types(engine, tenant: str, types: list[dict[str, Any]], choose: Callable[[str, list[str]], Any],
                   samples: dict[str, list[str]], *, only_missing: bool = True, cancel: Optional[threading.Event] = None,
                   progress: Optional[Callable[[int, int], None]] = None) -> dict[str, int]:
    """Kararı olmayan (ve `only_missing` ise önerisi de olmayan) tipleri Zeki AI'a kapalı küme seçimiyle sorar.
    Öneri kaydedilir; takvim onaylanana kadar kullanmaz. Model cevap veremezse istisna yükselir (sonra denenir)."""
    tmap = type_map(engine, tenant)
    todo = [t for t in types if not (tmap.get(t["id"]) or {}).get("sinif")
            and not (only_missing and (tmap.get(t["id"]) or {}).get("suggested"))]
    labels = list(CLASSES.values())
    done = unsure = 0
    for i, t in enumerate(todo):
        if cancel is not None and cancel.is_set():
            break
        ch = choose(type_prompt(t["ad"], t["adet"], samples.get(t["id"], [])), labels)
        save_type_suggestion(engine, tenant, t["id"], t["ad"], ch)
        done += 1
        if getattr(ch, "choice", None) is None:
            unsure += 1
        if progress:
            progress(i + 1, len(todo))
    return {"asked": done, "unsure": unsure, "total": len(todo)}


def classify_events(events: list[dict[str, Any]], tmap: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Her CRM etkinliğine eşlemedeki sınıfı ekler: `sinif` (onaylı) ya da None; `sinifOneri` (Zeki, onaysız)."""
    out = []
    for e in events:
        m = tmap.get(e.get("tipId") or "") or {}
        out.append({**e, "sinif": m.get("sinif"), "sinifOneri": None if m.get("sinif") else m.get("suggested")})
    return out


# ------------------------------------------------------------------ takvim, yaklaşanlar, ajanda


def calendar(fairs: list[dict[str, Any]], events: list[dict[str, Any]], year: int, classes: list[str],
             include_unmapped: bool = False) -> dict[str, Any]:
    """Yılın ay şeridi: portal kartları + seçilen sınıflardaki CRM etkinlikleri. Her ayın sınıf sayıları da döner
    (gizli sınıflar dahil) ki kişi neyin gizlendiğini görsün."""
    months: list[dict[str, Any]] = [{"month": m, "counts": {}, "fairs": [], "events": []} for m in range(1, 13)]
    for f in fairs:
        a, b = f["startsOn"], f["endsOn"]
        for m in range(1, 13):
            ms, me = f"{year}-{m:02d}-01", (date(year + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).isoformat()
            if a <= me and b >= ms:
                months[m - 1]["fairs"].append(f["id"])
    shown = set(classes)
    visible = []
    for e in events:
        if not e.get("baslangic") or not e["baslangic"].startswith(str(year)):
            continue
        m = int(e["baslangic"][5:7])
        key = e.get("sinif") or "yok"
        months[m - 1]["counts"][key] = months[m - 1]["counts"].get(key, 0) + 1
        if (e.get("sinif") in shown) or (include_unmapped and not e.get("sinif")):
            visible.append(e)
            months[m - 1]["events"].append(e["id"])
    totals: dict[str, int] = {}
    for mo in months:
        for k, v in mo["counts"].items():
            totals[k] = totals.get(k, 0) + v
    return {"year": year, "months": months, "fairs": fairs, "events": sorted(visible, key=lambda e: (e["baslangic"], e["ad"] or "")),
            "totals": totals, "classes": classes}


def upcoming_stmts(tenant: str, now: date) -> tuple[Any, Any, Any, Any]:
    """Yaklaşanlar: (son tarihi gelmemiş ödüller, ödül başına başvuru, son 14 gün hatırlatmaları, geciken görevler)."""
    return (sa.select(AWARDS).where(AWARDS.c.tenant_id == tenant, AWARDS.c.deadline >= now.isoformat()).order_by(AWARDS.c.deadline),
            sa.select(ENTRIES.c.award_id, sa.func.count()).group_by(ENTRIES.c.award_id),
            sa.select(REMINDERS).where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.created_at >= _now() - timedelta(days=14))
            .order_by(REMINDERS.c.created_at.desc()),
            sa.select(TASKS, FAIRS.c.name.label("fair_name")).join(FAIRS, FAIRS.c.id == TASKS.c.fair_id)
            .where(FAIRS.c.tenant_id == tenant, FAIRS.c.status != "iptal", TASKS.c.done_at.is_(None),
                   TASKS.c.due_on < now.isoformat()).order_by(TASKS.c.due_on))


def upcoming(engine, tenant: str, now: Optional[date] = None) -> dict[str, Any]:
    now = now or today()
    fairs = [f for f in list_fairs(engine, tenant, active_only=True, now=now) if f["endsOn"] >= now.isoformat()]
    fairs.sort(key=lambda f: f["startsOn"])
    aq, nq, rq, lq = upcoming_stmts(tenant, now)
    with engine.connect() as c:
        awards = [dict(r) for r in c.execute(aq).mappings()]
        n_entries = dict(c.execute(nq).all())
        rem = [dict(r) for r in c.execute(rq).mappings()]
        late = [dict(r) for r in c.execute(lq).mappings()]
    return {
        "today": now.isoformat(), "fairs": fairs,
        "awards": [{"id": a["id"], "name": a["name"], "category": a["category"], "deadline": a["deadline"],
                    "daysLeft": days_until(a["deadline"], now), "entries": int(n_entries.get(a["id"], 0))} for a in awards],
        "lateTasks": [{"id": t["id"], "fairId": t["fair_id"], "fair": t["fair_name"], "title": t["title"], "dueOn": t["due_on"],
                       "owner": t["owner_user"], "daysLate": -(days_until(t["due_on"], now) or 0)} for t in late],
        "reminders": [{"id": r["id"], "kind": r["kind"], "message": r["message"], "link": r["link"], "target": r["target_user"],
                       "at": _iso(r["created_at"])} for r in rem],
    }


def agenda(engine, tenant: str, user: str, crm_events: list[dict[str, Any]], now: Optional[date] = None, days: int = 60) -> dict[str, Any]:
    """Kampüs «Ajanda»: sorumlusu ben olan portal kartları ve görevleri + CRM'de sorumlusu ben olan yaklaşan
    etkinlikler (bugün ve sonrası, `days` gün). Yalnız kişinin kendi kayıtları."""
    now = now or today()
    until = (now + timedelta(days=days)).isoformat()
    me = (user or "").lower()
    items: list[dict[str, Any]] = []
    with engine.connect() as c:
        for f in c.execute(sa.select(FAIRS).where(FAIRS.c.tenant_id == tenant, FAIRS.c.owner_user == me, FAIRS.c.status != "iptal",
                                                  FAIRS.c.ends_on >= now.isoformat(), FAIRS.c.starts_on <= until)).mappings():
            items.append({"kind": "fuar", "id": f["id"], "title": f["name"], "day": max(f["starts_on"], now.isoformat()),
                          "startsOn": f["starts_on"], "endsOn": f["ends_on"], "where": ", ".join(x for x in (f["venue"], f["city"]) if x) or None,
                          "daysLeft": days_until(f["starts_on"], now), "link": f"/etkinlikler/fuar/{f['id']}", "status": f["status"]})
        for t in c.execute(sa.select(TASKS, FAIRS.c.name.label("fair_name")).join(FAIRS, FAIRS.c.id == TASKS.c.fair_id)
                           .where(FAIRS.c.tenant_id == tenant, FAIRS.c.status != "iptal", TASKS.c.owner_user == me,
                                  TASKS.c.done_at.is_(None), TASKS.c.due_on.isnot(None), TASKS.c.due_on <= until)).mappings():
            items.append({"kind": "gorev", "id": t["id"], "title": t["title"], "day": t["due_on"], "where": t["fair_name"],
                          "daysLeft": days_until(t["due_on"], now), "late": t["due_on"] < now.isoformat(),
                          "link": f"/etkinlikler/fuar/{t['fair_id']}?sekme=gorevler"})
    for e in crm_events:
        if e.get("sorumlu") != me or e.get("iptal") or not e.get("baslangic"):
            continue
        if e["baslangic"] < now.isoformat() or e["baslangic"] > until:
            continue
        items.append({"kind": "crm", "id": e["id"], "title": e["ad"] or e.get("tip") or "Etkinlik", "day": e["baslangic"],
                      "time": (e.get("saat") or "")[11:16] or None, "where": ", ".join(x for x in (e.get("yer"), e.get("il")) if x) or None,
                      "type": e.get("tip"), "daysLeft": days_until(e["baslangic"], now), "link": None})
    items.sort(key=lambda x: (x["day"], 0 if x["kind"] == "fuar" else 1, x["title"] or ""))
    return {"today": now.isoformat(), "until": until, "items": items, "total": len(items)}


# ------------------------------------------------------------------ ödül defteri


def _get_award(c, tenant: str, award_id: str) -> dict[str, Any]:
    r = c.execute(sa.select(AWARDS).where(AWARDS.c.tenant_id == tenant, AWARDS.c.id == str(award_id))).mappings().first()
    if not r:
        raise EventsError("Ödül bulunamadı.", 404)
    return dict(r)


def _award_fields(body: dict[str, Any], creating: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if creating or "name" in body:
        out["name"] = _text(body.get("name"), 300, "Ödül adı", required=True)
    for k, col, n in (("category", "category", 200), ("organizer", "organizer", 300), ("url", "url", 600)):
        if creating or k in body:
            out[col] = _text(body.get(k), n)
    if out.get("url") and not re.match(r"^https?://", out["url"]):
        raise EventsError("Bağlantı http:// ya da https:// ile başlamalı.", 422)
    if creating or "deadline" in body:
        d = parse_day(body.get("deadline"), "Son başvuru")
        out["deadline"] = d.isoformat() if d else None
    if creating or "conditions" in body:
        out["conditions"] = _long(body.get("conditions"), 8000)
    if creating or "note" in body:
        out["note"] = _long(body.get("note"), 4000)
    if creating or "recurring" in body:
        out["recurring"] = bool(body.get("recurring"))
    return out


def create_award(engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _award_fields(body, True)
    aid = _id()
    now = _now()
    with engine.begin() as c:
        c.execute(AWARDS.insert().values(id=aid, tenant_id=tenant, created_by=user, created_at=now, updated_at=now, **vals))
    return {"id": aid, "name": vals["name"]}


def update_award(engine, tenant: str, user: str, award_id: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _award_fields(body, False)
    with engine.begin() as c:
        cur = _get_award(c, tenant, award_id)
        diff = {k: [cur.get(k), v] for k, v in vals.items() if cur.get(k) != v}
        if vals:
            c.execute(AWARDS.update().where(AWARDS.c.id == cur["id"]).values(updated_at=_now(), **vals))
    return {"id": cur["id"], "name": vals.get("name", cur["name"]), "diff": diff}


def delete_award(engine, tenant: str, award_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        cur = _get_award(c, tenant, award_id)
        ids = [r for r in c.execute(sa.select(ENTRIES.c.id).where(ENTRIES.c.award_id == cur["id"])).scalars()]
        c.execute(ENTRIES.delete().where(ENTRIES.c.award_id == cur["id"]))
        c.execute(REMINDERS.delete().where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.ref_id.in_([cur["id"], *ids])))
        c.execute(AWARDS.delete().where(AWARDS.c.id == cur["id"]))
    return {"id": cur["id"], "name": cur["name"], "entries": len(ids)}


def _entry_view(e: dict[str, Any]) -> dict[str, Any]:
    return {"id": e["id"], "awardId": e["award_id"], "stokKodu": e["stok_kodu"], "crmBookId": e["crm_book_id"],
            "bookName": e["book_name"], "status": e["status"], "statusLabel": ENTRY_STATUSES.get(e["status"], e["status"]),
            "text": e["text"], "submittedAt": e["submitted_at"], "resultAt": e["result_at"], "note": e["note"],
            "by": e["created_by"], "updatedAt": _iso(e["updated_at"])}


def awards_stmts(tenant: str) -> tuple[Any, Any]:
    """(ödüller, başvuruları)."""
    return (sa.select(AWARDS).where(AWARDS.c.tenant_id == tenant),
            sa.select(ENTRIES).where(ENTRIES.c.award_id.in_(sa.select(AWARDS.c.id).where(AWARDS.c.tenant_id == tenant)))
            .order_by(ENTRIES.c.created_at))


def list_awards(engine, tenant: str, now: Optional[date] = None) -> dict[str, Any]:
    now = now or today()
    aq, eq = awards_stmts(tenant)
    with engine.connect() as c:
        awards = [dict(r) for r in c.execute(aq).mappings()]
        ids = [a["id"] for a in awards]
        entries: dict[str, list] = {i: [] for i in ids}
        if ids:
            for e in c.execute(eq).mappings():
                if e["award_id"] in entries:
                    entries[e["award_id"]].append(_entry_view(dict(e)))
    items = [{"id": a["id"], "name": a["name"], "category": a["category"], "organizer": a["organizer"], "deadline": a["deadline"],
              "daysLeft": days_until(a["deadline"], now), "conditions": a["conditions"], "url": a["url"], "recurring": bool(a["recurring"]),
              "note": a["note"], "by": a["created_by"], "entries": entries[a["id"]]} for a in awards]
    items.sort(key=lambda a: ((a["daysLeft"] is None) or a["daysLeft"] < 0, a["deadline"] or "9999", fold(a["name"])))
    return {"items": items, "statuses": ENTRY_STATUSES, "today": now.isoformat()}


def add_entry(engine, tenant: str, user: str, award_id: str, body: dict[str, Any],
              books: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    code = _text(body.get("stokKodu"), 60)
    card = (books or {}).get(code.upper()) if code else None
    if code and books is not None and not card:
        raise EventsError(f"{code} CRM kitap kartlarında yok.", 422)
    name = (card or {}).get("ad") or _text(body.get("bookName"), 400, "Kitap", required=True)
    st = str(body.get("status") or "aday")
    if st not in ENTRY_STATUSES:
        raise EventsError("Başvuru durumu geçersiz.", 422)
    eid = _id()
    now = _now()
    with engine.begin() as c:
        a = _get_award(c, tenant, award_id)
        c.execute(ENTRIES.insert().values(id=eid, award_id=a["id"], stok_kodu=(card or {}).get("stokKodu") or code,
                                          crm_book_id=(card or {}).get("id"), book_name=name, status=st,
                                          text=_long(body.get("text")), note=_long(body.get("note"), 4000),
                                          created_by=user, created_at=now, updated_at=now))
    return {"id": eid, "award": a["name"], "book": name}


def patch_entry(engine, tenant: str, user: str, entry_id: str, body: dict[str, Any]) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "status" in body:
        st = str(body["status"] or "")
        if st not in ENTRY_STATUSES:
            raise EventsError("Başvuru durumu geçersiz.", 422)
        vals["status"] = st
    for k, col in (("submittedAt", "submitted_at"), ("resultAt", "result_at")):
        if k in body:
            d = parse_day(body.get(k), "Tarih")
            vals[col] = d.isoformat() if d else None
    if "text" in body:
        vals["text"] = _long(body.get("text"))
    if "note" in body:
        vals["note"] = _long(body.get("note"), 4000)
    with engine.begin() as c:
        e = c.execute(sa.select(ENTRIES, AWARDS.c.name.label("award_name")).join(AWARDS, AWARDS.c.id == ENTRIES.c.award_id)
                      .where(ENTRIES.c.id == entry_id, AWARDS.c.tenant_id == tenant)).mappings().first()
        if not e:
            raise EventsError("Başvuru bulunamadı.", 404)
        if vals.get("status") == "gonderildi" and not e["submitted_at"] and "submitted_at" not in vals:
            vals["submitted_at"] = today().isoformat()
        if vals.get("status") in ("kazandi", "kazanamadi") and not e["result_at"] and "result_at" not in vals:
            vals["result_at"] = today().isoformat()
        diff = {k: [e.get(k), v] for k, v in vals.items() if e.get(k) != v and k != "text"}
        if vals:
            c.execute(ENTRIES.update().where(ENTRIES.c.id == e["id"]).values(updated_at=_now(), **vals))
    return {"id": e["id"], "award": e["award_name"], "book": e["book_name"], "diff": diff}


def delete_entry(engine, tenant: str, entry_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        e = c.execute(sa.select(ENTRIES, AWARDS.c.name.label("award_name")).join(AWARDS, AWARDS.c.id == ENTRIES.c.award_id)
                      .where(ENTRIES.c.id == entry_id, AWARDS.c.tenant_id == tenant)).mappings().first()
        if not e:
            raise EventsError("Başvuru bulunamadı.", 404)
        c.execute(ENTRIES.delete().where(ENTRIES.c.id == e["id"]))
    return {"id": e["id"], "award": e["award_name"], "book": e["book_name"]}


# ------------------------------------------------------------------ hatırlatmalar (zamanlayıcı)


def _remind(c, tenant: str, kind: str, ref: str, key: str, target: Optional[str], message: str, link: Optional[str]) -> bool:
    ex = c.execute(sa.select(REMINDERS.c.id).where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.kind == kind,
                                                   REMINDERS.c.ref_id == ref, REMINDERS.c.day_key == key)).first()
    if ex:
        return False
    c.execute(REMINDERS.insert().values(id=_id(), tenant_id=tenant, kind=kind, ref_id=ref, day_key=key, target_user=target,
                                        message=message[:600], link=link, created_at=_now()))
    return True


def run_reminders(engine, tenant: str, now: Optional[date] = None, st: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Günlük: fuar geri sayımı (ayardaki günlerde), geciken görev, ödül son tarihi, önerinin altında kalan stok.
    Aynı hatırlatma bir kez yazılır; dış gönderim yok, ekranda ve Kampüs ajandasında görünür."""
    now = now or today()
    st = st or settings()
    made = {"geri-sayim": 0, "geciken-gorev": 0, "odul": 0, "stok": 0}
    with engine.begin() as c:
        fairs = [dict(r) for r in c.execute(sa.select(FAIRS).where(FAIRS.c.tenant_id == tenant, FAIRS.c.status != "iptal",
                                                                   FAIRS.c.ends_on >= (now - timedelta(days=30)).isoformat())).mappings()]
        for f in fairs:
            left = days_until(f["starts_on"], now)
            link = f"/etkinlikler/fuar/{f['id']}"
            if left is not None and left in st["remindDays"]:
                t = c.execute(sa.select(TASKS.c.done_at).where(TASKS.c.fair_id == f["id"])).all()
                prep = (sum(1 for x in t if x[0] is not None) / len(t)) if t else None
                msg = f"«{f['name']}» fuarına {left} gün kaldı" + (f"; hazırlık %{prep * 100:.0f}." if prep is not None else ".")
                if f["status"] == "aday":
                    msg += " Katılım kararı henüz verilmedi."
                made["geri-sayim"] += _remind(c, tenant, "geri-sayim", f["id"], str(left), f["owner_user"], msg, link)
            for t in c.execute(sa.select(TASKS).where(TASKS.c.fair_id == f["id"], TASKS.c.done_at.is_(None),
                                                      TASKS.c.due_on < now.isoformat())).mappings().all():
                made["geciken-gorev"] += _remind(c, tenant, "geciken-gorev", t["id"], t["due_on"], t["owner_user"] or f["owner_user"],
                                                 f"«{f['name']}»: «{t['title']}» görevi {_tr_day(t['due_on'])} tarihinde bitmeliydi.",
                                                 link + "?sekme=gorevler")
            if f["starts_on"] >= now.isoformat():
                short = [b for b in c.execute(sa.select(BOOKS).where(BOOKS.c.fair_id == f["id"])).mappings()
                         if b["stock"] is not None and (b["qty_planned"] if b["qty_planned"] is not None else b["qty_suggested"]) is not None
                         and b["stock"] < (b["qty_planned"] if b["qty_planned"] is not None else b["qty_suggested"])]
                if short:
                    made["stok"] += _remind(c, tenant, "stok", f["id"], now.isoformat()[:7], f["owner_user"],
                                            f"«{f['name']}»: {len(short)} kitapta stok planlanan adedin altında.", link + "?sekme=kitaplar")
        for a in c.execute(sa.select(AWARDS).where(AWARDS.c.tenant_id == tenant, AWARDS.c.deadline >= now.isoformat())).mappings().all():
            left = days_until(a["deadline"], now)
            if left in st["awardRemindDays"]:
                made["odul"] += _remind(c, tenant, "odul", a["id"], str(left), a["created_by"],
                                        f"«{a['name']}» son başvuru tarihine {left} gün kaldı ({_tr_day(a['deadline'])}).",
                                        "/etkinlikler/oduller")
    return made


def fairs_needing_result(engine, tenant: str, now: Optional[date] = None) -> list[str]:
    """Bitmiş (bitişten sonraki gün ve sonrası), iptal olmayan, sonucu hiç hesaplanmamış ya da bitişten önce
    hesaplanmış kartlar: zamanlayıcı sonucu ön hesaplar."""
    now = now or today()
    out = []
    with engine.connect() as c:
        for f in c.execute(sa.select(FAIRS.c.id, FAIRS.c.ends_on, FAIRS.c.result_at).where(
                FAIRS.c.tenant_id == tenant, FAIRS.c.status != "iptal", FAIRS.c.ends_on < now.isoformat())).mappings():
            ra = f["result_at"]
            if ra is not None and ra.tzinfo is None:
                ra = ra.replace(tzinfo=timezone.utc)
            if ra is None or ra.astimezone(TZ).date().isoformat() <= f["ends_on"]:
                out.append(f["id"])
    return out


def note_result(engine, tenant: str, fair_id: str) -> None:
    with engine.begin() as c:
        f = _get_fair(c, tenant, fair_id)
        _remind(c, tenant, "sonuc", f["id"], f["ends_on"], f["owner_user"], f"«{f['name']}» sonuç raporu hazır.",
                f"/etkinlikler/fuar/{f['id']}/sonuc")


# ------------------------------------------------------------------ biçim


def _n(v: Any) -> str:
    if v is None:
        return "—"
    x = float(v)
    s = f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.1f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _money(v: Any) -> str:
    return "—" if v is None else f"{_n(round(float(v)))} TL"


def _tr_day(v: Optional[str]) -> str:
    if not v:
        return "—"
    d = date.fromisoformat(v[:10])
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def result_pdf(fair: dict[str, Any], r: dict[str, Any], user: str = "") -> bytes:
    """Tek sayfalık (gerekirse devam eden) fuar sonucu: özet, rakamlar, kitaplar, siparişler, gider, uyarılar."""
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise EventsError("PDF üretici sunucuda kurulu değil.", 503) from e
    from semantic_bridge.editorial_export import _fold, _resolve_fonts

    regular, bold = _resolve_fonts()
    fam = "Body" if regular else "Helvetica"
    T = (lambda s: str(s or "")) if regular else (lambda s: _fold(str(s or "")))
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_title(T(f"{fair['name']} — fuar sonucu"))
    pdf.set_author("Zeki AI")
    pdf.set_creator("Zeki AI")
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=14)
    if regular:
        pdf.add_font(fam, "", str(regular))
        pdf.add_font(fam, "B", str(bold or regular))
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    def para(s: str, size: float = 9.5, style: str = "", gap: float = 1.5) -> None:
        pdf.set_font(fam, style, size)
        pdf.multi_cell(W, size * 0.5, T(s), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    def head(s: str) -> None:
        pdf.ln(2)
        para(s, 12, "B", 1)

    def row(cells: list[tuple[str, float]], style: str = "") -> None:
        pdf.set_font(fam, style, 8.5)
        for txt, w in cells:
            t = T(txt)
            while pdf.get_string_width(t) > w - 1.5 and len(t) > 1:
                t = t[:-2] + "…" if len(t) > 2 else t[:-1]
            pdf.cell(w, 5.5, t, border="B")
        pdf.ln(5.5)

    para("Timaş Yayınları · Fuar sonucu", 8.5)
    para(fair["name"], 15, "B", 1)
    para(f"{_tr_day(fair['starts_on'])} – {_tr_day(fair['ends_on'])} · {', '.join(x for x in (fair.get('venue'), fair.get('city')) if x) or '—'}"
         f" · {FAIR_KINDS.get(fair['kind'], fair['kind'])}")
    para(f"Hesaplandı: {r.get('computedAt', '')[:16].replace('T', ' ')} UTC · satış verisi sonu {_tr_day(r.get('dataEnd'))}"
         + (f" · hazırlayan {user}" if user else ""), 8)
    head("Özet")
    for s in r.get("summary") or []:
        para("• " + s)
    head("Rakamlar")
    p = r.get("prev") or {}
    for k, v in (("Net satış (fuar kanalı)", _money(r["netCiro"])), ("Net adet", _n(r["netAdet"])),
                 ("Temel dönem net satış", _money(p.get("netCiro")) if p else "—"),
                 ("CRM fuar/etkinlik/imza siparişi", f"{r['orderCount']} adet · {_money(r['orderTotal'])}"),
                 ("Katılımcı (CRM)", _n(r.get("katilimci"))), ("Gider (portal + CRM)", _money(r["toplamGider"])),
                 ("Planlanan bütçe", _money(r.get("butce"))),
                 ("Her 1 TL gidere net satış", f"{r['roi']:.2f}".replace(".", ",") if r.get("roi") is not None else "—")):
        row([(k, W * 0.6), (v, W * 0.4)])
    books = r.get("books") or []
    if books:
        head(f"Kitaplar ({len(books)})")
        row([("Stok kodu", 30), ("Kitap", W - 30 - 20 - 26 - 22), ("Adet", 20), ("Net satış", 26), ("Geçen yıl", 22)], "B")
        for b in books:
            row([(b["stokKodu"], 30), (b.get("ad") or "", W - 30 - 20 - 26 - 22), (_n(b["adet"]), 20), (_money(b["ciro"]), 26),
                 (_n(b.get("gecenYilAdet")), 22)])
    if r.get("orders"):
        head("CRM siparişleri")
        for o in r["orders"]:
            row([(o.get("ad") or str(o["tip"]), W * 0.5), (f"{o['adet']} sipariş", W * 0.2), (_money(o["tutar"]), W * 0.3)])
    by = (r.get("costs") or {}).get("byKind") or {}
    if by or (r.get("costs") or {}).get("crm"):
        head("Gider")
        for k, v in by.items():
            row([(k, W * 0.6), (_money(v), W * 0.4)])
        if (r.get("costs") or {}).get("crm"):
            row([("CRM etkinlik kayıtlarındaki gider", W * 0.6), (_money(r["costs"]["crm"]), W * 0.4)])
    if r.get("warnings"):
        head("Uyarılar")
        for w in r["warnings"]:
            para("• " + w, 8.5)
    return bytes(pdf.output())
