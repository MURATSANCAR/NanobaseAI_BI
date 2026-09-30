"""M28 Kurumsal ilişkiler: kanaat önderleri, kurum ilişkileri, hediye kitap programı ve kamu projeleri.

Analiz: `docs/analiz/kullanici-ihtiyaclari/M28-kanaat-onderleri-kurumsal-iliskiler.md` (§14 kodlama planı). CRM'de kişi
ve kurum çok (ContactBase, 68.713 ziyaret yeri) ama «kime ne zaman hangi kitap gitti, ne döndü, hangi projede ne söz
verildi» hiçbir yerde tutulmuyor. Bu defter onu tutar; CRM yalnız okunur ve kimlikle bağlanır (CRM'e yazma yok).

- **Kişi kartı** (`semantic_rel_people`): CRM kişisine bağlı ya da portalda yeni. Alan (yönetimce onaylı sabit liste,
  `semantic_rel_fields`), ilgi alanları, «kamu görevlisi» işareti, ilişki sahibi, öncelik (kritik/normal). Bir CRM
  kişisine en çok bir kart.
- **Kurum kartı** (`semantic_rel_orgs`): CRM ziyaret yerine (okul, üniversite, MEB, belediye, kaymakamlık, valilik) ya
  da cariye bağlı ya da portalda yeni (Diyanet, kütüphane, STK — CRM'de ayrı tipi yok).
- **Temas notu** (`semantic_rel_notes`): kişiye ya da kuruma; kanal, ton, not, sıradaki adım ve tarihi. «Yalnız ben ve
  katılımcılar» işaretli notun metni yalnız yazana, katılımcılara ve `ozellik:iliskiler.hassas` sahibine gider;
  varlığı ısıya yine sayılır (M7 ile aynı çekirdek: `relations_core`).
- **Isı ve temas zamanı**: ısı `relations_core.heat` (yalnız temas notundan). «Temas zamanı gelen»: son temastan bu yana
  gün sayısı kişinin önceliğine göre ayardaki sınırı (`REL_CRITICAL_DAYS`, `REL_CONTACT_DAYS`) geçen ya da hiç temas
  yazılmamış kritik kişi.
- **Hediye programı** (`semantic_rel_gifts`): ay × kişi × kitap, gerekçe, kişisel not taslağı, durum
  (öneri → onaylı → sevk → teslim → dönüş; iptal). Aynı kişiye aynı kitap (iptal dışında) ikinci kez yazılamaz. Onay
  açıkça verilen `ozellik:iliskiler.onay` ister; öneriyi yazan onaylayamaz (yönetici hariç). «Kamu görevlisi» işaretli
  kişiye hediye hukuk onayı işaretlenmeden onaylanmaz (Kamu Görevlileri Etik Davranış İlkeleri). Gönderim CRM tanıtım
  siparişiyle yapılır; satıra yazılan CRM sipariş numarasının durumu her gün CRM'den okunur (sevk tarihi → «sevk»).
- **Kamu projesi** (`semantic_rel_projects`, `semantic_rel_project_events`): fikir → ön görüşme → teklif → kurum onayı →
  uygulama → rapor → kapandı (ya da vazgeçildi). Her aşama değişikliği tarihli olay kaydıdır. Bütçesi olan proje bütçe
  onayı olmadan uygulamaya geçmez. Teklif dosyası taslağını Zeki AI yazar (amaç, kapsam, fayda, takvim); rakamlar
  (okul, öğrenci, kitap adedi) CRM'den kodla, mevzuat maddeleri `public_affairs_criteria.json`'dan aynen gelir — model
  rakam ve madde üretmez.
- **KVKK**: inanç, mezhep, cemaat, siyasi görüş, parti, etnik köken, sendika alanı ya da etiketi tutulmaz. Alan listesine
  ve kişinin ilgi alanlarına bu sözcükler yazılamaz (`BANNED_TERMS` + ayar `REL_BANNED_TERMS`); Zeki AI alan önerisini
  yalnız onaylı listeden seçer.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import relations_core as core
from semantic_bridge.relations_core import TZ, RelationError

log = logging.getLogger("semantic.public_affairs")
_md = sa.MetaData()

PEOPLE = sa.Table(
    "semantic_rel_people", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("crm_contact_id", sa.String(40)),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("name", sa.String(300), nullable=False),
    sa.Column("org_id", sa.String(32)),
    sa.Column("org_name", sa.String(300)),
    sa.Column("title", sa.String(300)),
    sa.Column("field_key", sa.String(40)),
    sa.Column("interests_json", sa.Text, nullable=False, default="[]"),
    sa.Column("is_public_official", sa.Boolean, nullable=False, default=False),
    sa.Column("priority", sa.String(10), nullable=False, default="normal"),
    sa.Column("owner", sa.String(120)),
    sa.Column("owner_display", sa.String(200)),
    sa.Column("email", sa.String(200)),
    sa.Column("phone", sa.String(60)),
    sa.Column("city", sa.String(120)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("archived_at", sa.DateTime(timezone=True)),
    sa.Column("archived_by", sa.String(120)),
    sa.Index("ux_semantic_rel_people_crm", "tenant_id", "crm_contact_id", unique=True,
             postgresql_where=sa.text("crm_contact_id IS NOT NULL"),
             sqlite_where=sa.text("crm_contact_id IS NOT NULL")),
)
ORGS = sa.Table(
    "semantic_rel_orgs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("crm_visit_place_id", sa.String(40)),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("name", sa.String(300), nullable=False),
    sa.Column("kind", sa.String(20), nullable=False),
    sa.Column("city", sa.String(120)),
    sa.Column("owner", sa.String(120)),
    sa.Column("owner_display", sa.String(200)),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("archived_at", sa.DateTime(timezone=True)),
    sa.Index("ux_semantic_rel_orgs_place", "tenant_id", "crm_visit_place_id", unique=True,
             postgresql_where=sa.text("crm_visit_place_id IS NOT NULL"),
             sqlite_where=sa.text("crm_visit_place_id IS NOT NULL")),
)
NOTES = sa.Table(
    "semantic_rel_notes", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("person_id", sa.String(32)),
    sa.Column("org_id", sa.String(32)),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("channel", sa.String(20), nullable=False),
    sa.Column("tone", sa.String(10)),
    sa.Column("topic", sa.String(300), nullable=False),
    sa.Column("text", sa.Text),
    sa.Column("private", sa.Boolean, nullable=False, default=False),
    sa.Column("participants_json", sa.Text, nullable=False, default="[]"),
    sa.Column("next_step", sa.String(500)),
    sa.Column("next_on", sa.Date),
    sa.Column("next_done", sa.Boolean, nullable=False, default=False),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_display", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Index("ix_semantic_rel_notes_person", "tenant_id", "person_id"),
    sa.Index("ix_semantic_rel_notes_org", "tenant_id", "org_id"),
)
GIFTS = sa.Table(
    "semantic_rel_gifts", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("month", sa.String(7), nullable=False),
    sa.Column("person_id", sa.String(32), nullable=False, index=True),
    sa.Column("crm_book_id", sa.String(40), nullable=False),
    sa.Column("book_name", sa.String(300)),
    sa.Column("stock_code", sa.String(60)),
    sa.Column("author", sa.String(300)),
    sa.Column("reason", sa.String(500)),
    sa.Column("note_text", sa.Text),
    sa.Column("status", sa.String(10), nullable=False),
    sa.Column("legal_ok_by", sa.String(120)),
    sa.Column("legal_ok_at", sa.DateTime(timezone=True)),
    sa.Column("crm_order_no", sa.String(40)),
    sa.Column("crm_order_id", sa.String(40)),
    sa.Column("crm_order_status", sa.Integer),
    sa.Column("crm_order_status_label", sa.String(120)),
    sa.Column("crm_order_type", sa.Integer),
    sa.Column("crm_book_in_order", sa.Boolean),
    sa.Column("crm_synced_at", sa.DateTime(timezone=True)),
    sa.Column("shipped_on", sa.Date),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("feedback", sa.Text),
    sa.Column("feedback_at", sa.DateTime(timezone=True)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
PROJECTS = sa.Table(
    "semantic_rel_projects", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("org_id", sa.String(32)),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("kind", sa.String(20), nullable=False),
    sa.Column("stage", sa.String(20), nullable=False),
    sa.Column("owner", sa.String(120)),
    sa.Column("owner_display", sa.String(200)),
    sa.Column("summary", sa.Text),
    sa.Column("budget", sa.Numeric(14, 2)),
    sa.Column("budget_approved_by", sa.String(120)),
    sa.Column("budget_approved_at", sa.DateTime(timezone=True)),
    sa.Column("books_json", sa.Text, nullable=False, default="[]"),
    sa.Column("places_json", sa.Text, nullable=False, default="[]"),
    sa.Column("orders_json", sa.Text, nullable=False, default="[]"),
    sa.Column("reach_schools", sa.Integer),
    sa.Column("reach_students", sa.Integer),
    sa.Column("reach_books", sa.Integer),
    sa.Column("reach_participants", sa.Integer),
    sa.Column("press_json", sa.Text, nullable=False, default="[]"),
    sa.Column("next_step", sa.String(500)),
    sa.Column("next_on", sa.Date),
    sa.Column("tender_ref", sa.String(80)),
    sa.Column("proposal_text", sa.Text),
    sa.Column("proposal_status", sa.String(12), nullable=False, default="yok"),
    sa.Column("proposal_at", sa.DateTime(timezone=True)),
    sa.Column("proposal_by", sa.String(120)),
    sa.Column("proposal_error", sa.String(500)),
    sa.Column("proposal_approved_by", sa.String(120)),
    sa.Column("proposal_approved_at", sa.DateTime(timezone=True)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
)
EVENTS = sa.Table(
    "semantic_rel_project_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("project_id", sa.String(32), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("user", sa.String(120), nullable=False),
    sa.Column("user_display", sa.String(200)),
    sa.Column("stage_from", sa.String(20)),
    sa.Column("stage_to", sa.String(20)),
    sa.Column("note", sa.Text),
    sa.Column("doc_ref", sa.String(500)),
)
FIELDS = sa.Table(
    "semantic_rel_fields", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(40), primary_key=True),
    sa.Column("label", sa.String(80), nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

#: Yönetim/hukuk onayı gelene kadar alan listesi yalnız kurum türüyle başlar (analiz §14 «Bağımlılık»).
FIELD_DEFAULTS = (("akademi", "Akademi"), ("egitim", "Eğitim"), ("medya", "Medya ve yayın"), ("stk", "Sivil toplum"),
                  ("kamu", "Kamu yönetimi"), ("diger", "Diğer"))
#: KVKK md. 6 özel nitelikli veriye götüren sınıflar. Kök (önek) ve tam sözcük olarak ayrı: «din» tam sözcük
#: yakalanır, «dinleme» yakalanmaz. Ayar `REL_BANNED_TERMS` listeyi genişletir, daraltamaz.
BANNED_STEMS = ("inanc", "inanis", "mezhep", "mezheb", "cemaat", "tarikat", "siyas", "partili", "partisi", "ideoloj",
                "etnik", "irkci", "sendika", "alevi", "sunni", "sii", "ateist", "muhafazakar", "laik", "milliyetci",
                "sosyalist", "komunist", "liberal", "dindar")
BANNED_WORDS = ("din", "dini", "dinci", "parti", "irk", "koken", "sol", "sag", "solcu", "sagci", "siyasi", "politik")

ORG_KINDS = {"meb": "Milli Eğitim", "okul": "Okul", "universite": "Üniversite", "belediye": "Belediye",
             "kaymakamlik": "Kaymakamlık", "valilik": "Valilik", "diyanet": "Diyanet", "kutuphane": "Kütüphane",
             "stk": "STK / vakıf", "diger": "Diğer"}
#: CRM ziyaret yeri kurum tipi → kurum türü.
PLACE_KIND = {1: "okul", 3: "universite", 5: "meb", 6: "belediye", 7: "kaymakamlik", 8: "valilik", 4: "diger"}
PRIORITIES = {"kritik": "Kritik", "normal": "Normal"}
GIFT_STATUS = {"oneri": "Öneri", "onayli": "Onaylı", "sevk": "Sevk edildi", "teslim": "Teslim edildi",
               "donus": "Dönüş alındı", "iptal": "İptal"}
#: Elle geçilebilen durumlar (onay ayrı uçtan; sevk CRM'den ya da elle).
GIFT_NEXT = {"oneri": {"iptal"}, "onayli": {"sevk", "iptal", "oneri"}, "sevk": {"teslim", "donus"},
             "teslim": {"donus"}, "donus": set(), "iptal": {"oneri"}}
PROJECT_KINDS = {"okuma": "Okuma kampanyası", "bagis": "Kütüphane bağışı", "materyal": "Eğitim materyali",
                 "etkinlik": "Ortak etkinlik", "diger": "Diğer"}
STAGES = {"fikir": "Fikir", "gorusme": "Ön görüşme", "teklif": "Teklif", "kurum_onayi": "Kurum onayı",
          "uygulama": "Uygulama", "rapor": "Rapor", "kapandi": "Kapandı", "vazgecildi": "Vazgeçildi"}
STAGE_ORDER = list(STAGES)
OPEN_STAGES = ("fikir", "gorusme", "teklif", "kurum_onayi", "uygulama", "rapor")
PROPOSAL_STATUS = {"yok": "Taslak yok", "hazirlaniyor": "Hazırlanıyor", "hazir": "Taslak hazır", "hata": "Hazırlanamadı"}
VISIBILITY = {"herkes": "Sayfayı gören herkes", "ozel": "Yalnız ben ve katılımcılar"}

CRITERIA_FILE = Path(__file__).with_name("public_affairs_criteria.json")

_ready: set[int] = set()
_lock = threading.Lock()
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_KEY = re.compile(r"^[a-z][a-z0-9-]{1,39}$")

DEFAULTS = {
    "REL_CONTACT_DAYS": "180", "REL_CRITICAL_DAYS": "90", "REL_GIFT_GAP_DAYS": "90", "REL_ORDER_TYPES": "12,15,10,11",
    "REL_ORDER_EXCLUDED_STATUS": "100000001,100000003", "REL_BANNED_TERMS": "", "REL_ALERT_RECIPIENTS": "",
    "REL_LLM_MIN_PROB": "0.70", "REL_LLM_MIN_MARGIN": "0.30", "REL_SHIPPED_STATUS": "100000000",
}


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def settings_from(conf: Callable[[str, str], str]) -> dict[str, Any]:
    def g(k: str) -> str:
        v = conf(k, "")
        return str(v if v not in (None, "") else DEFAULTS[k])

    def gi(k: str, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(float(g(k)))))
        except ValueError:
            return int(DEFAULTS[k])

    def gf(k: str) -> float:
        try:
            return float(g(k).replace(",", "."))
        except ValueError:
            return float(DEFAULTS[k])

    def ints(k: str) -> list[int]:
        return sorted({int(x) for x in re.findall(r"\d+", g(k))})

    return {
        "contactDays": gi("REL_CONTACT_DAYS", 7, 3650),
        "criticalDays": gi("REL_CRITICAL_DAYS", 7, 3650),
        "giftGapDays": gi("REL_GIFT_GAP_DAYS", 0, 3650),
        "orderTypes": ints("REL_ORDER_TYPES") or [12],
        "excludedStatus": ints("REL_ORDER_EXCLUDED_STATUS"),
        "shippedStatus": ints("REL_SHIPPED_STATUS"),
        "bannedExtra": [core.norm(x) for x in re.split(r"[,;\n]", conf("REL_BANNED_TERMS", "") or "") if core.norm(x)],
        "alertTo": [x.strip() for x in (conf("REL_ALERT_RECIPIENTS", "") or "").replace(";", ",").split(",") if "@" in x],
        "llmMinProb": gf("REL_LLM_MIN_PROB"),
        "llmMinMargin": gf("REL_LLM_MIN_MARGIN"),
        "company": (conf("CORP_COMPANY_NAME", "") or "Timaş Yayınları").strip(),
    }


# ------------------------------------------------------------------------------------------ KVKK


def banned_hit(text: Optional[str], extra: Iterable[str] = ()) -> Optional[str]:
    """Metinde özel nitelikli sınıfa götüren sözcük varsa o sözcük (sadeleştirilmiş), yoksa None."""
    words = core.norm(text or "").split()
    extra = [e for e in extra if e]
    for w in words:
        if w in BANNED_WORDS or any(w.startswith(s) for s in BANNED_STEMS):
            return w
        if any(w == e or (len(e) >= 4 and w.startswith(e)) for e in extra):
            return w
    joined = " ".join(words)
    for e in extra:
        if " " in e and e in joined:
            return e
    return None


def _check_banned(text: Optional[str], label: str, extra: Iterable[str]) -> None:
    hit = banned_hit(text, extra)
    if hit:
        raise RelationError(f"{label} kişisel veri kuralına takıldı («{hit}»): inanç, mezhep, cemaat, siyasi görüş, parti, "
                            "etnik köken ve sendika gibi özel nitelikli sınıflar portalda tutulmaz.", 422)


def kvkk_scan(engine: sa.engine.Engine, tenant: str, extra: Iterable[str] = ()) -> dict[str, Any]:
    """Kabul 6: alan listesinde ve kişi kartlarının alan/ilgi alanlarında yasak sözcük var mı."""
    extra = list(extra)
    hits: list[dict[str, Any]] = []
    with engine.connect() as c:
        for r in c.execute(sa.select(FIELDS).where(FIELDS.c.tenant_id == tenant)).fetchall():
            for t in (r.key, r.label):
                h = banned_hit(t, extra)
                if h:
                    hits.append({"where": "alan", "key": r.key, "hit": h})
        for r in c.execute(sa.select(PEOPLE.c.id, PEOPLE.c.field_key, PEOPLE.c.interests_json)
                           .where(PEOPLE.c.tenant_id == tenant)).fetchall():
            for t in [r.field_key or ""] + [str(x) for x in core.json_list(r.interests_json)]:
                h = banned_hit(t, extra)
                if h:
                    hits.append({"where": "kisi", "id": r.id, "hit": h})
    return {"hits": hits, "count": len(hits)}


# ------------------------------------------------------------------------------------------ alanlar


def _seed_fields(c: Any, tenant: str) -> None:
    if c.execute(sa.select(sa.func.count()).select_from(FIELDS).where(FIELDS.c.tenant_id == tenant)).scalar():
        return
    now = core.now()
    for i, (k, label) in enumerate(FIELD_DEFAULTS):   # sıra korunsun: listede «Diğer» en sonda
        c.execute(FIELDS.insert().values(tenant_id=tenant, key=k, label=label, active=True, created_by="sistem",
                                         created_at=now + timedelta(milliseconds=i)))


def list_fields(engine: sa.engine.Engine, tenant: str, *, active_only: bool = False) -> list[dict[str, Any]]:
    with engine.begin() as c:
        _seed_fields(c, tenant)
        rows = c.execute(sa.select(FIELDS).where(FIELDS.c.tenant_id == tenant).order_by(FIELDS.c.created_at, FIELDS.c.key)).fetchall()
    return [{"key": r.key, "label": r.label, "active": bool(r.active)} for r in rows if r.active or not active_only]


def add_field(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], extra: Iterable[str]) -> dict[str, Any]:
    label = core.text_field(body, "label", 80, "Alan adı", required=True)
    key = str(body.get("key") or core.norm(label).replace(" ", "-"))[:40]
    if not _KEY.match(key):
        raise RelationError("Alan anahtarı küçük harf, rakam ve tire olmalı (en az 2 karakter).")
    _check_banned(label, "Alan adı", extra)
    _check_banned(key, "Alan anahtarı", extra)
    with engine.begin() as c:
        _seed_fields(c, tenant)
        if c.execute(sa.select(FIELDS.c.key).where(FIELDS.c.tenant_id == tenant, FIELDS.c.key == key)).first():
            raise RelationError("Bu alan zaten var.", 409)
        c.execute(FIELDS.insert().values(tenant_id=tenant, key=key, label=label, active=True, created_by=user, created_at=core.now()))
    return {"key": key, "label": label, "active": True}


def update_field(engine: sa.engine.Engine, tenant: str, user: str, key: str, body: dict[str, Any], extra: Iterable[str]) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "label" in body:
        vals["label"] = core.text_field(body, "label", 80, "Alan adı", required=True)
        _check_banned(vals["label"], "Alan adı", extra)
    if "active" in body:
        vals["active"] = bool(body.get("active"))
    with engine.begin() as c:
        row = c.execute(sa.select(FIELDS).where(FIELDS.c.tenant_id == tenant, FIELDS.c.key == key)).first()
        if not row:
            raise RelationError("Alan bulunamadı.", 404)
        if vals:
            c.execute(FIELDS.update().where(FIELDS.c.tenant_id == tenant, FIELDS.c.key == key)
                      .values(updated_by=user, updated_at=core.now(), **vals))
        row = c.execute(sa.select(FIELDS).where(FIELDS.c.tenant_id == tenant, FIELDS.c.key == key)).first()
    return {"key": row.key, "label": row.label, "active": bool(row.active)}


def fields_stmt(tenant: str):
    return sa.select(FIELDS).where(FIELDS.c.tenant_id == tenant)


def _field_keys(c: Any, tenant: str) -> dict[str, str]:
    _seed_fields(c, tenant)
    return {r.key: r.label for r in c.execute(fields_stmt(tenant)).fetchall()}


# ------------------------------------------------------------------------------------------ yardımcılar


def _day(v: Any, label: str) -> Optional[date]:
    t = str(v or "").strip()
    if not t:
        return None
    try:
        return date.fromisoformat(t[:10])
    except ValueError:
        raise RelationError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


def _int(v: Any, label: str, lo: int = 0, hi: int = 100_000_000) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        n = int(str(v).replace(".", "").replace(" ", ""))
    except ValueError:
        raise RelationError(f"{label} tam sayı olmalı.") from None
    if not lo <= n <= hi:
        raise RelationError(f"{label} {lo} ile {hi} arasında olmalı.")
    return n


def _money(v: Any) -> Optional[Decimal]:
    if v in (None, ""):
        return None
    t = str(v).strip().replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        d = Decimal(t)
    except InvalidOperation:
        raise RelationError("Bütçe tutar olarak yazılmalı (ör. 125.000,50).") from None
    if d < 0 or d > Decimal("1e12"):
        raise RelationError("Bütçe 0 ile 1 trilyon arasında olmalı.")
    return d.quantize(Decimal("0.01"))


def _owner(body: dict[str, Any], out: dict[str, Any]) -> None:
    o = core.text_field(body, "owner", 120, "İlişki sahibi")
    out["owner"] = o.lower() if o else None
    out["owner_display"] = core.text_field(body, "ownerDisplay", 200, "İlişki sahibi adı") if o else None


def _dayiso(v: Optional[date]) -> Optional[str]:
    return v.isoformat() if v else None


def _num(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


def month_of(at: Optional[datetime] = None) -> str:
    return (at or core.now()).astimezone(TZ).strftime("%Y-%m")


# ------------------------------------------------------------------------------------------ kişiler


def _person_values(c: Any, tenant: str, body: dict[str, Any], *, partial: bool, extra: Iterable[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def has(k: str) -> bool:
        return not partial or k in body

    if has("name"):
        out["name"] = core.text_field(body, "name", 300, "Ad soyad", required=True)
    if has("title"):
        out["title"] = core.text_field(body, "title", 300, "Unvan / görev")
    if has("orgName"):
        out["org_name"] = core.text_field(body, "orgName", 300, "Kurum")
    if has("orgId"):
        v = body.get("orgId")
        if v:
            oid = core.cid(v, "Kurum kartı")
            if not c.execute(sa.select(ORGS.c.id).where(ORGS.c.id == oid, ORGS.c.tenant_id == tenant)).first():
                raise RelationError("Kurum kartı bulunamadı.", 404)
            out["org_id"] = oid
        else:
            out["org_id"] = None
    if has("fieldKey"):
        v = body.get("fieldKey")
        if v:
            if v not in _field_keys(c, tenant):
                raise RelationError("Alan onaylı listede yok.")
            out["field_key"] = str(v)
        else:
            out["field_key"] = None
    if has("interests"):
        items = core.str_list(body, "interests", 60, "İlgi alanları")
        for x in items:
            _check_banned(x, "İlgi alanı", extra)
        out["interests_json"] = json.dumps(items, ensure_ascii=False)
    if has("isPublicOfficial"):
        out["is_public_official"] = bool(body.get("isPublicOfficial"))
    if has("priority"):
        out["priority"] = core.choice(body, "priority", PRIORITIES, "Öncelik", "normal")
    if has("owner"):
        _owner(body, out)
    if has("email"):
        e = core.text_field(body, "email", 200, "E-posta")
        if e and not core.EMAIL_RE.match(e):
            raise RelationError("E-posta adresi geçerli değil.")
        out["email"] = e.lower() if e else None
    if has("phone"):
        p = core.text_field(body, "phone", 60, "Telefon")
        if p and not core.PHONE_RE.match(p):
            raise RelationError("Telefon yalnız rakam, boşluk ve + ( ) - içerebilir.")
        out["phone"] = p
    if has("city"):
        out["city"] = core.text_field(body, "city", 120, "Şehir")
    if has("crmContactId"):
        v = body.get("crmContactId")
        out["crm_contact_id"] = core.guid(v) if v else None
    if has("crmAccountId"):
        v = body.get("crmAccountId")
        out["crm_account_id"] = core.guid(v, "CRM kurum kimliği") if v else None
    return out


def _person(r: Any, fields: dict[str, str], orgs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    org = (orgs or {}).get(r.org_id) if r.org_id else None
    return {
        "id": r.id, "crmContactId": r.crm_contact_id, "crmAccountId": r.crm_account_id, "name": r.name,
        "orgId": r.org_id, "orgName": (org.name if org is not None else None) or r.org_name, "title": r.title,
        "fieldKey": r.field_key, "fieldLabel": fields.get(r.field_key or "", None),
        "interests": core.json_list(r.interests_json), "isPublicOfficial": bool(r.is_public_official),
        "priority": r.priority, "priorityLabel": PRIORITIES.get(r.priority, r.priority), "owner": r.owner,
        "ownerDisplay": r.owner_display, "email": r.email, "phone": r.phone, "city": r.city,
        "createdBy": r.created_by, "createdAt": core.iso(r.created_at), "updatedAt": core.iso(r.updated_at),
        "archived": r.archived_at is not None,
    }


def _get_person(c: Any, tenant: str, pid: str, *, lock: bool = False) -> Any:
    stmt = sa.select(PEOPLE).where(PEOPLE.c.id == core.cid(pid, "Kişi kartı"), PEOPLE.c.tenant_id == tenant)
    row = c.execute(stmt.with_for_update() if lock else stmt).first()
    if not row:
        raise RelationError("Kişi kartı bulunamadı.", 404)
    return row


def _person_by_crm(c: Any, tenant: str, contact_id: str) -> Any:
    return c.execute(sa.select(PEOPLE).where(PEOPLE.c.tenant_id == tenant, PEOPLE.c.crm_contact_id == contact_id)).first()


def create_person(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], extra: Iterable[str] = ()) -> dict[str, Any]:
    now = core.now()
    with engine.begin() as c:
        vals = _person_values(c, tenant, body, partial=False, extra=extra)
        if vals.get("crm_contact_id"):
            other = _person_by_crm(c, tenant, vals["crm_contact_id"])
            if other:
                raise RelationError(f"Bu CRM kişisinin kartı zaten var: {other.name}.", 409, personId=other.id)
        rid = uuid.uuid4().hex
        c.execute(PEOPLE.insert().values(id=rid, tenant_id=tenant, created_by=user, created_at=now, updated_by=user,
                                         updated_at=now, **vals))
        return _person(c.execute(sa.select(PEOPLE).where(PEOPLE.c.id == rid)).first(), _field_keys(c, tenant))


def update_person(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, pid: str, body: dict[str, Any],
                  extra: Iterable[str] = ()) -> tuple[dict[str, Any], dict[str, Any]]:
    """Kart ortak kayıttır: düzenleme yetkisi olan herkes düzeltir. Arşivleme açan, sahibi ya da yönetici işidir."""
    archive = body.get("archived")
    with engine.begin() as c:
        row = _get_person(c, tenant, pid, lock=True)
        vals = _person_values(c, tenant, body, partial=True, extra=extra)
        if archive is not None and bool(archive) != (row.archived_at is not None):
            if not (admin or user == row.created_by or user == (row.owner or "")):
                raise RelationError("Kartı yalnız açan kişi, ilişki sahibi ya da yönetici arşivler.", 403)
            vals["archived_at"] = core.now() if archive else None
            vals["archived_by"] = user if archive else None
        if vals.get("crm_contact_id") and vals["crm_contact_id"] != row.crm_contact_id:
            other = _person_by_crm(c, tenant, vals["crm_contact_id"])
            if other and other.id != row.id:
                raise RelationError(f"Bu CRM kişisinin kartı zaten var: {other.name}.", 409, personId=other.id)
        changed = {k: v for k, v in vals.items() if getattr(row, k) != v}
        if changed:
            c.execute(PEOPLE.update().where(PEOPLE.c.id == row.id).values(updated_by=user, updated_at=core.now(), **changed))
        diff = {k: {"before": getattr(row, k), "after": v} for k, v in changed.items() if k != "archived_by"}
        return _person(c.execute(sa.select(PEOPLE).where(PEOPLE.c.id == row.id)).first(), _field_keys(c, tenant)), diff


def person_for_crm(engine: sa.engine.Engine, tenant: str, user: str, contact: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """CRM kişisinin kartı; yoksa CRM'deki ad, unvan, kurum, il ve iş iletişim bilgisiyle açılır."""
    cid_ = core.guid(contact.get("crmContactId"))
    with engine.connect() as c:
        row = _person_by_crm(c, tenant, cid_)
        if row:
            return _person(row, _field_keys(c, tenant)), False
    body = {"name": contact.get("name"), "title": contact.get("title"), "orgName": contact.get("orgName"),
            "crmContactId": cid_, "crmAccountId": contact.get("crmAccountId") or None, "city": contact.get("city"),
            "email": contact.get("email") if contact.get("email") and core.EMAIL_RE.match(str(contact["email"])) else None,
            "phone": contact.get("phone") if contact.get("phone") and core.PHONE_RE.match(str(contact["phone"])) else None}
    try:
        return create_person(engine, tenant, user, {k: v for k, v in body.items() if v}), True
    except RelationError as e:
        if e.status == 409:   # aynı anda başka istek açtı
            with engine.connect() as c:
                return _person(_person_by_crm(c, tenant, cid_), _field_keys(c, tenant)), False
        raise


# ------------------------------------------------------------------------------------------ kurumlar


def _org_values(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def has(k: str) -> bool:
        return not partial or k in body

    if has("name"):
        out["name"] = core.text_field(body, "name", 300, "Kurum adı", required=True)
    if has("kind"):
        out["kind"] = core.choice(body, "kind", ORG_KINDS, "Kurum türü", "diger")
    if has("city"):
        out["city"] = core.text_field(body, "city", 120, "İl")
    if has("note"):
        out["note"] = core.long_field(body, "note", 4000, "Not")
    if has("owner"):
        _owner(body, out)
    if has("crmVisitPlaceId"):
        v = body.get("crmVisitPlaceId")
        out["crm_visit_place_id"] = core.guid(v, "CRM ziyaret yeri") if v else None
    if has("crmAccountId"):
        v = body.get("crmAccountId")
        out["crm_account_id"] = core.guid(v, "CRM kurum kimliği") if v else None
    return out


def _org(r: Any) -> dict[str, Any]:
    return {"id": r.id, "crmVisitPlaceId": r.crm_visit_place_id, "crmAccountId": r.crm_account_id, "name": r.name,
            "kind": r.kind, "kindLabel": ORG_KINDS.get(r.kind, r.kind), "city": r.city, "owner": r.owner,
            "ownerDisplay": r.owner_display, "note": r.note, "createdBy": r.created_by, "createdAt": core.iso(r.created_at),
            "updatedAt": core.iso(r.updated_at), "archived": r.archived_at is not None}


def _get_org(c: Any, tenant: str, oid: str) -> Any:
    row = c.execute(sa.select(ORGS).where(ORGS.c.id == core.cid(oid, "Kurum kartı"), ORGS.c.tenant_id == tenant)).first()
    if not row:
        raise RelationError("Kurum kartı bulunamadı.", 404)
    return row


def create_org(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _org_values(body, partial=False)
    now = core.now()
    with engine.begin() as c:
        if vals.get("crm_visit_place_id"):
            other = c.execute(sa.select(ORGS).where(ORGS.c.tenant_id == tenant,
                                                    ORGS.c.crm_visit_place_id == vals["crm_visit_place_id"])).first()
            if other:
                raise RelationError(f"Bu CRM kurumunun kartı zaten var: {other.name}.", 409, orgId=other.id)
        rid = uuid.uuid4().hex
        c.execute(ORGS.insert().values(id=rid, tenant_id=tenant, created_by=user, created_at=now, updated_by=user,
                                       updated_at=now, **vals))
        return _org(c.execute(sa.select(ORGS).where(ORGS.c.id == rid)).first())


def org_for_place(engine: sa.engine.Engine, tenant: str, user: str, place: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """CRM ziyaret yerinin kurum kartı; yoksa CRM'deki ad, tip ve ille açılır."""
    pid = core.guid(place.get("id"), "CRM ziyaret yeri")
    with engine.connect() as c:
        row = c.execute(sa.select(ORGS).where(ORGS.c.tenant_id == tenant, ORGS.c.crm_visit_place_id == pid)).first()
        if row:
            return _org(row), False
    kind = PLACE_KIND.get(int(place.get("kurumTipi") or 4), "diger")
    try:
        return create_org(engine, tenant, user, {"name": place.get("name") or "Adı kayıtlı değil", "kind": kind,
                                                 "city": place.get("city"), "crmVisitPlaceId": pid}), True
    except RelationError as e:
        if e.status == 409:
            with engine.connect() as c:
                return _org(c.execute(sa.select(ORGS).where(ORGS.c.tenant_id == tenant, ORGS.c.crm_visit_place_id == pid)).first()), False
        raise


def update_org(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, oid: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    vals = _org_values(body, partial=True)
    archive = body.get("archived")
    with engine.begin() as c:
        row = _get_org(c, tenant, oid)
        if archive is not None and bool(archive) != (row.archived_at is not None):
            if not (admin or user == row.created_by or user == (row.owner or "")):
                raise RelationError("Kurum kartını yalnız açan kişi, sahibi ya da yönetici arşivler.", 403)
            vals["archived_at"] = core.now() if archive else None
        changed = {k: v for k, v in vals.items() if getattr(row, k) != v}
        if changed:
            c.execute(ORGS.update().where(ORGS.c.id == row.id).values(updated_by=user, updated_at=core.now(), **changed))
        diff = {k: {"before": getattr(row, k), "after": v} for k, v in changed.items() if k != "note"}
        return _org(c.execute(sa.select(ORGS).where(ORGS.c.id == row.id)).first()), diff


# ------------------------------------------------------------------------------------------ temas notları


def _note_when(n: Any) -> datetime:
    return n.at


def person_heat(notes: Iterable[Any], at: Optional[datetime] = None) -> dict[str, Any]:
    """Temas notlarından ısı (her not yapılmış bir temastır; planlanan randevu M7'de, burada sıradaki adım)."""
    return core.heat(notes, at, done=lambda n: True, planned=lambda n: False, when=_note_when)


def _note_values(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def has(k: str) -> bool:
        return not partial or k in body

    if has("date") or has("time"):
        d = _day(body.get("date"), "Tarih") or core.now().astimezone(TZ).date()
        hhmm = str(body.get("time") or "12:00").strip()
        m = re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", hhmm)
        if not m:
            raise RelationError("Saat SS:DD biçiminde olmalı.")
        out["at"] = datetime(d.year, d.month, d.day, int(m.group(1)), int(m.group(2)), tzinfo=TZ).astimezone(timezone.utc)
    if has("channel"):
        out["channel"] = core.choice(body, "channel", core.CHANNELS, "Kanal", "telefon")
    if has("tone"):
        out["tone"] = core.choice(body, "tone", core.TONES, "Ton")
    if has("topic"):
        out["topic"] = core.text_field(body, "topic", 300, "Konu", required=True)
    if has("text"):
        out["text"] = core.long_field(body, "text", 20000, "Not")
    if has("visibility"):
        out["private"] = core.choice(body, "visibility", VISIBILITY, "Görünürlük", "herkes") == "ozel"
    if has("participants"):
        out["participants_json"] = json.dumps(core.participants(body.get("participants") or []), ensure_ascii=False)
    if has("nextStep"):
        out["next_step"] = core.text_field(body, "nextStep", 500, "Sıradaki adım")
    if has("nextOn"):
        out["next_on"] = _day(body.get("nextOn"), "Sıradaki adım tarihi")
    if has("nextDone"):
        out["next_done"] = bool(body.get("nextDone"))
    return out


def _note(r: Any, user: str, privileged: bool) -> dict[str, Any]:
    open_ = core.can_read(bool(r.private), r.created_by, r.participants_json, user, privileged)
    loc = core.utc(r.at).astimezone(TZ)
    return {
        "id": r.id, "personId": r.person_id, "orgId": r.org_id, "at": core.iso(r.at), "date": loc.date().isoformat(),
        "time": loc.strftime("%H:%M"), "channel": r.channel, "channelLabel": core.CHANNELS.get(r.channel, r.channel),
        "tone": r.tone if open_ else None, "toneLabel": core.TONES.get(r.tone or "") if open_ else None,
        "topic": r.topic if open_ else "Gizli not", "text": r.text if open_ else None,
        "visibility": "ozel" if r.private else "herkes", "hidden": not open_,
        "participants": core.json_list(r.participants_json) if open_ else [],
        "nextStep": r.next_step if open_ else None, "nextOn": _dayiso(r.next_on) if open_ else None,
        "nextDone": bool(r.next_done), "createdBy": r.created_by, "createdDisplay": r.created_display,
        "createdAt": core.iso(r.created_at), "canEdit": privileged or r.created_by == user,
    }


def create_note(engine: sa.engine.Engine, tenant: str, user: str, display: str, privileged: bool,
                body: dict[str, Any]) -> dict[str, Any]:
    vals = _note_values(body, partial=False)
    if vals["at"] > core.now() + timedelta(minutes=5):
        raise RelationError("İleri tarihli temas yazılmaz; ileri tarihi «sıradaki adım» olarak girin.")
    pid = core.cid(body["personId"], "Kişi kartı") if body.get("personId") else None
    oid = core.cid(body["orgId"], "Kurum kartı") if body.get("orgId") else None
    if not pid and not oid:
        raise RelationError("Notun kime ya da hangi kuruma ait olduğu gerekli.")
    now = core.now()
    with engine.begin() as c:
        if pid:
            p = _get_person(c, tenant, pid)
            if p.archived_at is not None:
                raise RelationError("Arşivdeki karta not yazılmaz; önce kartı arşivden çıkarın.")
            oid = oid or p.org_id
        if oid:
            _get_org(c, tenant, oid)
        rid = uuid.uuid4().hex
        c.execute(NOTES.insert().values(id=rid, tenant_id=tenant, person_id=pid, org_id=oid, created_by=user,
                                        created_display=(display or user)[:200], created_at=now, updated_by=user,
                                        updated_at=now, **vals))
        return _note(c.execute(sa.select(NOTES).where(NOTES.c.id == rid)).first(), user, privileged)


def update_note(engine: sa.engine.Engine, tenant: str, user: str, privileged: bool, nid: str,
                body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    with engine.begin() as c:
        row = c.execute(sa.select(NOTES).where(NOTES.c.id == core.cid(nid, "Not"), NOTES.c.tenant_id == tenant)).first()
        if not row:
            raise RelationError("Not bulunamadı.", 404)
        only_step = set(body) <= {"nextDone"}
        readable = core.can_read(bool(row.private), row.created_by, row.participants_json, user, privileged)
        if not (privileged or row.created_by == user or (only_step and readable)):
            raise RelationError("Notu yalnız yazan kişi değiştirir.", 403)
        vals = _note_values(body, partial=True)
        changed = {k: v for k, v in vals.items() if (core.utc(row.at) if k == "at" else getattr(row, k)) != v}
        if changed:
            c.execute(NOTES.update().where(NOTES.c.id == row.id).values(updated_by=user, updated_at=core.now(), **changed))
        diff = {k: {"before": str(getattr(row, k)) if getattr(row, k) is not None else None, "after": str(v) if v is not None else None}
                for k, v in changed.items() if k not in ("text", "participants_json")}
        if "text" in changed:
            diff["text"] = {"before": "…", "after": "…"}   # not metni değişiklik kaydına kopyalanmaz
        return _note(c.execute(sa.select(NOTES).where(NOTES.c.id == row.id)).first(), user, privileged), diff


def delete_note(engine: sa.engine.Engine, tenant: str, user: str, privileged: bool, nid: str) -> dict[str, Any]:
    with engine.begin() as c:
        row = c.execute(sa.select(NOTES).where(NOTES.c.id == core.cid(nid, "Not"), NOTES.c.tenant_id == tenant)).first()
        if not row:
            raise RelationError("Not bulunamadı.", 404)
        if not (privileged or row.created_by == user):
            raise RelationError("Notu yalnız yazan kişi siler.", 403)
        c.execute(NOTES.delete().where(NOTES.c.id == row.id))
    return {"id": row.id, "personId": row.person_id, "orgId": row.org_id}


# ------------------------------------------------------------------------------------------ temas zamanı


def due_days(priority: str, st: dict[str, Any]) -> int:
    return st["criticalDays"] if priority == "kritik" else st["contactDays"]


def is_due(p: Any, h: dict[str, Any], st: dict[str, Any]) -> bool:
    """Temas zamanı geldi mi: son temas sınırdan eski, ya da hiç temas yok ve kişi kritik (normal kişi ilk temas için
    listeye düşmez — yoksa CRM'den alınan her kişi ilk gün «zamanı geldi» olur)."""
    if h["daysSince"] is None:
        return p.priority == "kritik"
    return h["daysSince"] >= due_days(p.priority, st)


def people_stmts(tenant: str, archived: bool = False) -> tuple[Any, Any, Any, Any]:
    """Kişi listesi: (kişi kartları, kişi notları — ısı ve temas için, alanlar, kurumlar)."""
    stmt = sa.select(PEOPLE).where(PEOPLE.c.tenant_id == tenant)
    stmt = stmt.where(PEOPLE.c.archived_at.isnot(None) if archived else PEOPLE.c.archived_at.is_(None))
    return (stmt, sa.select(NOTES).where(NOTES.c.tenant_id == tenant, NOTES.c.person_id.isnot(None)), fields_stmt(tenant),
            orgs_stmt(tenant))


def orgs_stmt(tenant: str):
    return sa.select(ORGS).where(ORGS.c.tenant_id == tenant)


def last_gifts_stmt(tenant: str):
    return sa.select(GIFTS.c.person_id, GIFTS.c.book_name, GIFTS.c.month, GIFTS.c.status) \
        .where(GIFTS.c.tenant_id == tenant, GIFTS.c.status != "iptal").order_by(GIFTS.c.month)


def _people_with_notes(engine: sa.engine.Engine, tenant: str, *, archived: bool = False) -> tuple[list[Any], dict[str, list[Any]], dict[str, str], dict[str, Any]]:
    pq, nq, _fq, oq = people_stmts(tenant, archived)
    with engine.begin() as c:
        people = c.execute(pq).fetchall()
        notes = c.execute(nq).fetchall()
        fields = _field_keys(c, tenant)
        orgs = {r.id: r for r in c.execute(oq).fetchall()}
    by: dict[str, list[Any]] = {}
    for n in notes:
        by.setdefault(n.person_id, []).append(n)
    return people, by, fields, orgs


def _last_gifts(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    """Kişi → son hediye (iptal dışı): kitap adı ve ay."""
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for g in c.execute(last_gifts_stmt(tenant)).fetchall():
            out[g.person_id] = {"book": g.book_name, "month": g.month, "status": g.status}
    return out


def list_people(engine: sa.engine.Engine, tenant: str, user: str, st: dict[str, Any], *, q: str = "", field: str = "",
                priority: str = "", scope: str = "", org_id: str = "", archived: bool = False, order: str = "zaman",
                now: Optional[datetime] = None) -> dict[str, Any]:
    """Kişi listesi, ısı ve temas zamanıyla. Sessiz tavan yok: süzgece uyan her kart döner."""
    now = now or core.now()
    people, by, fields, orgs = _people_with_notes(engine, tenant, archived=archived)
    gifts = _last_gifts(engine, tenant)
    nq = core.norm(q)
    items = []
    for p in people:
        if field and p.field_key != field:
            continue
        if priority and p.priority != priority:
            continue
        if org_id and p.org_id != org_id:
            continue
        if scope == "benim" and user not in (p.owner or "", p.created_by):
            continue
        org = orgs.get(p.org_id) if p.org_id else None
        if nq and nq not in core.norm(" ".join(x for x in (p.name, p.title, p.org_name, org.name if org else None) if x)):
            continue
        ns = by.get(p.id, [])
        h = person_heat(ns, now)
        due = is_due(p, h, st)
        if scope == "zamani" and not due:
            continue
        items.append(dict(_person(p, fields, orgs), heat=h, due=due, dueDays=due_days(p.priority, st),
                          openSteps=sum(1 for n in ns if n.next_step and not n.next_done),
                          lastGift=gifts.get(p.id)))
    if order == "ad":
        items.sort(key=lambda x: x["name"].casefold())
    elif order == "sicak":
        items.sort(key=lambda x: (-x["heat"]["score"], x["name"].casefold()))
    else:
        # temas zamanı gelen önce, kritik önce, en uzun süredir aranmayan önce
        items.sort(key=lambda x: (not x["due"], x["priority"] != "kritik", -(x["heat"]["daysSince"] if x["heat"]["daysSince"] is not None else 10**6),
                                  x["name"].casefold()))
    counts = {"toplam": len(people), "zamani": 0, "kritik": 0}
    for p in people:
        h = person_heat(by.get(p.id, []), now)
        counts["zamani"] += int(is_due(p, h, st))
        counts["kritik"] += int(p.priority == "kritik")
    return {"items": items, "total": len(items), "counts": counts}


def person_stmts(tenant: str, pid: str) -> tuple[Any, Any, Any, Any]:
    """Kişi kartı: (kart, kurumlar, notları, hediyeleri)."""
    return (sa.select(PEOPLE).where(PEOPLE.c.id == pid, PEOPLE.c.tenant_id == tenant), orgs_stmt(tenant),
            sa.select(NOTES).where(NOTES.c.tenant_id == tenant, NOTES.c.person_id == pid).order_by(NOTES.c.at.desc()),
            sa.select(GIFTS).where(GIFTS.c.tenant_id == tenant, GIFTS.c.person_id == pid)
            .order_by(GIFTS.c.month.desc(), GIFTS.c.created_at.desc()))


def person_detail(engine: sa.engine.Engine, tenant: str, user: str, privileged: bool, pid: str, st: dict[str, Any]) -> dict[str, Any]:
    now = core.now()
    with engine.begin() as c:
        row = _get_person(c, tenant, pid)
        fields = _field_keys(c, tenant)
        _pq, oq, nq, gq = person_stmts(tenant, row.id)
        orgs = {r.id: r for r in c.execute(oq).fetchall()}
        ns = c.execute(nq).fetchall()
        gs = c.execute(gq).fetchall()
    h = person_heat(ns, now)
    return dict(_person(row, fields, orgs), heat=h, due=is_due(row, h, st), dueDays=due_days(row.priority, st),
                timeline=[_note(n, user, privileged) for n in ns], gifts=[_gift(g, {row.id: row}) for g in gs])


# ------------------------------------------------------------------------------------------ hediye programı


def _gift(g: Any, people: dict[str, Any]) -> dict[str, Any]:
    p = people.get(g.person_id)
    return {
        "id": g.id, "month": g.month, "personId": g.person_id, "personName": p.name if p is not None else None,
        "personTitle": p.title if p is not None else None,
        "isPublicOfficial": bool(p.is_public_official) if p is not None else False,
        "crmBookId": g.crm_book_id, "bookName": g.book_name, "stockCode": g.stock_code, "author": g.author,
        "reason": g.reason, "noteText": g.note_text, "status": g.status, "statusLabel": GIFT_STATUS.get(g.status, g.status),
        "legalOk": bool(g.legal_ok_by), "legalOkBy": g.legal_ok_by, "crmOrderNo": g.crm_order_no,
        "crmOrderStatus": g.crm_order_status, "crmOrderStatusLabel": g.crm_order_status_label,
        "crmOrderType": g.crm_order_type, "crmBookInOrder": g.crm_book_in_order, "crmSyncedAt": core.iso(g.crm_synced_at),
        "shippedOn": _dayiso(g.shipped_on), "approvedBy": g.approved_by, "approvedAt": core.iso(g.approved_at),
        "feedback": g.feedback, "feedbackAt": core.iso(g.feedback_at), "createdBy": g.created_by,
        "createdAt": core.iso(g.created_at),
    }


def _duplicate_gift(c: Any, tenant: str, person_id: str, book_id: str, exclude: Optional[str] = None) -> Any:
    stmt = sa.select(GIFTS).where(GIFTS.c.tenant_id == tenant, GIFTS.c.person_id == person_id,
                                  GIFTS.c.crm_book_id == book_id, GIFTS.c.status != "iptal")
    if exclude:
        stmt = stmt.where(GIFTS.c.id != exclude)
    return c.execute(stmt).first()


def add_gift(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    month = str(body.get("month") or month_of())
    if not _MONTH.match(month):
        raise RelationError("Ay YYYY-AA biçiminde olmalı.")
    book_id = core.guid(body.get("crmBookId"), "CRM kitap kimliği")
    now = core.now()
    with engine.begin() as c:
        p = _get_person(c, tenant, str(body.get("personId") or ""))
        if p.archived_at is not None:
            raise RelationError("Arşivdeki kişiye hediye yazılmaz.")
        dup = _duplicate_gift(c, tenant, p.id, book_id)
        if dup:
            raise RelationError(f"Bu kitap {p.name} için {dup.month} programında zaten var ({GIFT_STATUS.get(dup.status)}).",
                                409, giftId=dup.id)
        rid = uuid.uuid4().hex
        c.execute(GIFTS.insert().values(
            id=rid, tenant_id=tenant, month=month, person_id=p.id, crm_book_id=book_id,
            book_name=core.text_field(body, "bookName", 300, "Kitap adı"), stock_code=core.text_field(body, "stockCode", 60, "Stok kodu"),
            author=core.text_field(body, "author", 300, "Yazar"), reason=core.text_field(body, "reason", 500, "Gerekçe"),
            note_text=core.long_field(body, "noteText", 4000, "Kişisel not"), status="oneri",
            created_by=user, created_at=now, updated_by=user, updated_at=now))
        return _gift(c.execute(sa.select(GIFTS).where(GIFTS.c.id == rid)).first(), {p.id: p})


def update_gift(engine: sa.engine.Engine, tenant: str, user: str, gid: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Gerekçe, kişisel not, ay, CRM sipariş numarası, geri dönüş ve elle durum geçişi (onay ayrı uçtan)."""
    from semantic_bridge import public_affairs_sources as src

    with engine.begin() as c:
        g = c.execute(sa.select(GIFTS).where(GIFTS.c.id == core.cid(gid, "Hediye"), GIFTS.c.tenant_id == tenant)).first()
        if not g:
            raise RelationError("Hediye satırı bulunamadı.", 404)
        vals: dict[str, Any] = {}
        if "reason" in body:
            vals["reason"] = core.text_field(body, "reason", 500, "Gerekçe")
        if "noteText" in body:
            vals["note_text"] = core.long_field(body, "noteText", 4000, "Kişisel not")
        if "month" in body:
            m = str(body.get("month") or "")
            if not _MONTH.match(m):
                raise RelationError("Ay YYYY-AA biçiminde olmalı.")
            if g.status not in ("oneri", "onayli"):
                raise RelationError("Sevk edilmiş hediyenin ayı değişmez.")
            vals["month"] = m
        if "crmOrderNo" in body:
            v = body.get("crmOrderNo")
            if v:
                try:
                    vals["crm_order_no"] = src.order_no(v)
                except src.SourceError as e:
                    raise RelationError(str(e)) from None
            else:
                vals["crm_order_no"] = None
            if vals["crm_order_no"] != g.crm_order_no:
                vals.update(crm_order_id=None, crm_order_status=None, crm_order_status_label=None, crm_order_type=None,
                            crm_book_in_order=None, crm_synced_at=None)
        if "feedback" in body:
            vals["feedback"] = core.long_field(body, "feedback", 4000, "Geri dönüş")
            vals["feedback_at"] = core.now() if vals["feedback"] else None
        if "status" in body:
            to = core.choice(body, "status", GIFT_STATUS, "Durum")
            if to and to != g.status:
                if to not in GIFT_NEXT.get(g.status, set()):
                    raise RelationError(f"«{GIFT_STATUS[g.status]}» durumundan «{GIFT_STATUS[to]}» durumuna geçilmez.")
                if to == "oneri" and g.status == "iptal":
                    p = _get_person(c, tenant, g.person_id)
                    if _duplicate_gift(c, tenant, p.id, g.crm_book_id, exclude=g.id):
                        raise RelationError("Bu kitap bu kişi için başka bir satırda zaten var.", 409)
                vals["status"] = to
                if to == "oneri":
                    vals.update(approved_by=None, approved_at=None)
                if to == "sevk" and not g.shipped_on:
                    vals["shipped_on"] = core.now().astimezone(TZ).date()
        if vals.get("feedback") and g.status in ("sevk", "teslim") and "status" not in vals:
            vals["status"] = "donus"
        changed = {k: v for k, v in vals.items() if getattr(g, k) != v}
        if changed:
            c.execute(GIFTS.update().where(GIFTS.c.id == g.id).values(updated_by=user, updated_at=core.now(), **changed))
        out = c.execute(sa.select(GIFTS).where(GIFTS.c.id == g.id)).first()
        p = c.execute(sa.select(PEOPLE).where(PEOPLE.c.id == out.person_id)).first()
        diff = {k: {"before": str(getattr(g, k)) if getattr(g, k) is not None else None, "after": str(v) if v is not None else None}
                for k, v in changed.items() if k not in ("note_text", "feedback")}
        return _gift(out, {p.id: p} if p is not None else {}), diff


def approve_gifts(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, body: dict[str, Any]) -> dict[str, Any]:
    """Toplu onay (ya da geri çevirme: `decision: "geri"` → öneriye döner). Öneriyi yazan onaylayamaz (yönetici hariç);
    kamu görevlisine hediye `legalOk` işaretlenmeden onaylanmaz."""
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise RelationError("Onaylanacak hediye satırı seçilmedi.")
    decision = body.get("decision") or "onay"
    if decision not in ("onay", "geri"):
        raise RelationError("Karar «onay» ya da «geri» olmalı.")
    legal = set(str(x) for x in (body.get("legalOk") or []))
    done, skipped = [], []
    now = core.now()
    with engine.begin() as c:
        for gid in ids:
            g = c.execute(sa.select(GIFTS).where(GIFTS.c.id == core.cid(gid, "Hediye"), GIFTS.c.tenant_id == tenant)).first()
            if not g:
                skipped.append({"id": gid, "reason": "bulunamadı"})
                continue
            p = c.execute(sa.select(PEOPLE).where(PEOPLE.c.id == g.person_id)).first()
            if decision == "geri":
                if g.status != "onayli":
                    skipped.append({"id": g.id, "reason": "onaylı değil"})
                    continue
                c.execute(GIFTS.update().where(GIFTS.c.id == g.id).values(status="oneri", approved_by=None, approved_at=None,
                                                                          updated_by=user, updated_at=now))
                done.append(g.id)
                continue
            if g.status != "oneri":
                skipped.append({"id": g.id, "reason": f"durum {GIFT_STATUS.get(g.status)}"})
                continue
            if g.created_by == user and not admin:
                skipped.append({"id": g.id, "reason": "öneriyi yazan onaylayamaz"})
                continue
            legal_ok = g.legal_ok_by
            if p is not None and p.is_public_official and not legal_ok:
                if g.id not in legal:
                    skipped.append({"id": g.id, "reason": "kamu görevlisi: hukuk onayı işaretlenmedi"})
                    continue
                legal_ok = user
            c.execute(GIFTS.update().where(GIFTS.c.id == g.id).values(
                status="onayli", approved_by=user, approved_at=now, legal_ok_by=legal_ok,
                legal_ok_at=now if legal_ok and not g.legal_ok_by else g.legal_ok_at, updated_by=user, updated_at=now))
            done.append(g.id)
    return {"done": done, "skipped": skipped}


def gifts_stmts(tenant: str, month: str = "", status: str = "", person_id: str = "") -> tuple[Any, Any]:
    """Hediye programı: (hediye satırları, satırlardaki kişiler)."""
    cond = [GIFTS.c.tenant_id == tenant]
    if month:
        cond.append(GIFTS.c.month == month)
    if status:
        cond.append(GIFTS.c.status == status)
    if person_id:
        cond.append(GIFTS.c.person_id == person_id)
    return (sa.select(GIFTS).where(*cond).order_by(GIFTS.c.month.desc(), GIFTS.c.created_at),
            sa.select(PEOPLE).where(PEOPLE.c.id.in_(sa.select(GIFTS.c.person_id).where(*cond))))


def list_gifts(engine: sa.engine.Engine, tenant: str, *, month: str = "", status: str = "", person_id: str = "") -> dict[str, Any]:
    if month and not _MONTH.match(month):
        raise RelationError("Ay YYYY-AA biçiminde olmalı.")
    gq, pq = gifts_stmts(tenant, month, status, person_id)
    with engine.connect() as c:
        rows = c.execute(gq).fetchall()
        people = {p.id: p for p in c.execute(pq).fetchall()} if rows else {}
    items = [_gift(r, people) for r in rows]
    counts = {k: 0 for k in GIFT_STATUS}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {"items": items, "total": len(items), "counts": counts, "month": month or None,
            "books": len({r.crm_book_id for r in rows if r.status != "iptal"}),
            "people": len({r.person_id for r in rows if r.status != "iptal"})}


def sync_orders(engine: sa.engine.Engine, tenant: str, run: Callable[[str], list[dict[str, Any]]], schema: str,
                st: dict[str, Any], labels: Optional[dict[int, str]] = None) -> dict[str, Any]:
    """Hediye satırlarının CRM sipariş durumu: sipariş bulundu mu, tipi, durumu, kitabın stok kodu siparişte var mı, sevk
    tarihi. Sevk edilmiş sipariş (sevk tarihi dolu ya da durum `REL_SHIPPED_STATUS`) onaylı satırı «sevk»e geçirir."""
    from semantic_bridge import public_affairs_sources as src

    with engine.connect() as c:
        rows = c.execute(sa.select(GIFTS).where(GIFTS.c.tenant_id == tenant, GIFTS.c.crm_order_no.isnot(None),
                                                GIFTS.c.status.in_(("onayli", "sevk", "teslim", "donus")))).fetchall()
    if not rows:
        return {"checked": 0, "found": 0, "shipped": 0}
    orders = {}
    for r in src.lower_rows(run(src.orders_by_no_sql(schema, [g.crm_order_no for g in rows]))):
        orders[str(r.get("no") or "").strip()] = r
    lines: dict[str, set[str]] = {}
    ids = [src.lid(o.get("id")) for o in orders.values() if src.lid(o.get("id"))]
    if ids:
        for r in src.lower_rows(run(src.order_lines_sql(schema, ids))):
            lines.setdefault(src.lid(r.get("siparis")) or "", set()).add((src.s(r.get("stok_kodu")) or "").upper())
    labels = labels or {}
    now = core.now()
    found = shipped = 0
    with engine.begin() as c:
        for g in rows:
            o = orders.get(g.crm_order_no)
            if o is None:
                c.execute(GIFTS.update().where(GIFTS.c.id == g.id).values(crm_order_id=None, crm_order_status=None,
                                                                          crm_order_status_label="CRM'de bulunamadı",
                                                                          crm_book_in_order=None, crm_synced_at=now))
                continue
            found += 1
            oid = src.lid(o.get("id"))
            status = src.ival(o.get("durum"))
            ship = core.crm_day(o.get("sevk"))
            vals: dict[str, Any] = {
                "crm_order_id": oid, "crm_order_status": status,
                "crm_order_status_label": labels.get(status) if status is not None else None,
                "crm_order_type": src.ival(o.get("tip")),
                "crm_book_in_order": ((g.stock_code or "").upper() in lines.get(oid or "", set())) if g.stock_code else None,
                "crm_synced_at": now,
            }
            if ship and not g.shipped_on:
                vals["shipped_on"] = ship
            if g.status == "onayli" and (ship or (status is not None and status in st["shippedStatus"])):
                vals["status"] = "sevk"
                vals["shipped_on"] = vals.get("shipped_on") or ship or now.astimezone(TZ).date()
                shipped += 1
            c.execute(GIFTS.update().where(GIFTS.c.id == g.id).values(**vals))
    return {"checked": len(rows), "found": found, "shipped": shipped}


# ------------------------------------------------------------------------------------------ hediye önerisi (kural)

_STOP = {"ve", "ile", "icin", "bir", "bu", "da", "de", "the", "of", "and", "kitap", "kitabi", "kitaplar", "diger", "genel",
         "yayin", "yayinlari", "roman", "seri"}


def _stems(text: Optional[str]) -> dict[str, str]:
    """Sözcük kökü (ilk 5 harf) → ilk görülen biçim. Türkçe eklerle «tarih/tarihi/tarihçi» aynı köke düşer."""
    out: dict[str, str] = {}
    for w in core.norm(text or "").split():
        if len(w) < 4 or w in _STOP or w.isdigit():
            continue
        out.setdefault(w[:5], w)
    return out


def gifts_by_person(engine: sa.engine.Engine, tenant: str) -> dict[str, list[Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(GIFTS).where(GIFTS.c.tenant_id == tenant)).fetchall()
    out: dict[str, list[Any]] = {}
    for g in rows:
        out.setdefault(g.person_id, []).append(g)
    return out


def suggest(people: list[dict[str, Any]], books: list[dict[str, Any]], crm_tags: dict[str, list[str]],
            gifts_by_person: dict[str, list[Any]], st: dict[str, Any], *, include_all: bool = False,
            now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Kitap → kime gönderelim. Puan kuraldır, gerekçesi yazılır; model kullanılmaz:
    - kişinin alanı, ilgi alanları, CRM uzmanlık alanları ve unvanı × kitabın türleri, web kategorileri, adı ve arka kapak
      metni: ortak kök başına 20 (en çok 60);
    - kritik kişi +10; temas zamanı gelmiş +10;
    - son hediyesi `REL_GIFT_GAP_DAYS` günden yeni −20;
    - kitabı zaten almış (iptal dışı) kişi listeye girmez.
    Örtüşmesi olmayan kişi yalnız `include_all` ile döner (elle seçim için). Sessiz tavan yok."""
    now = now or core.now()
    today = now.astimezone(TZ).date()
    out: list[dict[str, Any]] = []
    for b in books:
        book_text = " ".join(x for x in (b.get("turler"), b.get("kategoriler"), b.get("ad"), b.get("ozet")) if x)
        bstems = _stems(book_text)
        for p in people:
            received = {g.crm_book_id for g in gifts_by_person.get(p["id"], []) if g.status != "iptal"}
            if b["id"] in received:
                continue
            ptext_parts = [p.get("fieldLabel"), " ".join(p.get("interests") or []), p.get("title")]
            ptext_parts += crm_tags.get(p.get("crmContactId") or "", [])
            pstems = _stems(" ".join(x for x in ptext_parts if x))
            common = [pstems[k] for k in pstems if k in bstems]
            score = min(60, 20 * len(common))
            why: list[str] = []
            if common:
                why.append("örtüşen konu: " + ", ".join(common[:4]))
            if p.get("priority") == "kritik":
                score += 10
                why.append("kritik kişi")
            if p.get("due"):
                score += 10
                why.append("temas zamanı geldi")
            last = max((g for g in gifts_by_person.get(p["id"], []) if g.status != "iptal"), key=lambda g: g.month, default=None)
            if last is not None:
                y, m = (int(x) for x in last.month.split("-"))
                days = (today - date(y, m, 1)).days
                if days < st["giftGapDays"]:
                    score -= 20
                    why.append(f"son hediye {last.month} ({last.book_name or 'kitap'})")
            if not common and not include_all:
                continue
            out.append({"bookId": b["id"], "bookName": b.get("ad"), "stockCode": b.get("stok_kodu"), "author": b.get("yazar"),
                        "personId": p["id"], "personName": p["name"], "personTitle": p.get("title"),
                        "orgName": p.get("orgName"), "fieldLabel": p.get("fieldLabel"),
                        "isPublicOfficial": bool(p.get("isPublicOfficial")), "score": score, "match": len(common),
                        "reason": "; ".join(why) or "konu örtüşmesi yok (elle seçim)"})
    out.sort(key=lambda x: (x["bookName"] or "", -x["score"], x["personName"].casefold()))
    return out


# ------------------------------------------------------------------------------------------ projeler


def _project_values(c: Any, tenant: str, body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def has(k: str) -> bool:
        return not partial or k in body

    if has("title"):
        out["title"] = core.text_field(body, "title", 300, "Proje adı", required=True)
    if has("kind"):
        out["kind"] = core.choice(body, "kind", PROJECT_KINDS, "Proje türü", "diger")
    if has("orgId"):
        v = body.get("orgId")
        if v:
            out["org_id"] = _get_org(c, tenant, str(v)).id
        else:
            out["org_id"] = None
    if has("summary"):
        out["summary"] = core.long_field(body, "summary", 8000, "Özet")
    if has("owner"):
        _owner(body, out)
    if has("budget"):
        out["budget"] = _money(body.get("budget"))
    if has("books"):
        books = body.get("books") or []
        if not isinstance(books, list):
            raise RelationError("Kitap listesi liste olmalı.")
        clean, seen = [], set()
        for b in books:
            if not isinstance(b, dict):
                continue
            bid = core.guid(b.get("id"), "CRM kitap kimliği")
            if bid in seen:
                continue
            seen.add(bid)
            clean.append({"id": bid, "name": str(b.get("name") or "")[:300] or None, "stockCode": str(b.get("stockCode") or "")[:60] or None,
                          "qty": _int(b.get("qty"), "Kitap adedi", 0, 10_000_000)})
        out["books_json"] = json.dumps(clean, ensure_ascii=False)
    if has("places"):
        ps = body.get("places") or []
        if not isinstance(ps, list):
            raise RelationError("Hedef kurum listesi liste olmalı.")
        out["places_json"] = json.dumps(sorted({core.guid(x, "CRM ziyaret yeri") for x in ps}), ensure_ascii=False)
    if has("orders"):
        from semantic_bridge import public_affairs_sources as src
        os_ = body.get("orders") or []
        if not isinstance(os_, list):
            raise RelationError("Sipariş listesi liste olmalı.")
        try:
            out["orders_json"] = json.dumps(sorted({src.order_no(x) for x in os_}), ensure_ascii=False)
        except src.SourceError as e:
            raise RelationError(str(e)) from None
    for k, col, label in (("reachSchools", "reach_schools", "Ulaşılan okul"), ("reachStudents", "reach_students", "Ulaşılan öğrenci"),
                          ("reachBooks", "reach_books", "Dağıtılan kitap"), ("reachParticipants", "reach_participants", "Katılımcı")):
        if has(k):
            out[col] = _int(body.get(k), label)
    if has("press"):
        links = core.str_list(body, "press", 500, "Basın yansıması")
        bad = [x for x in links if not core.URL_RE.match(x)]
        if bad:
            raise RelationError(f"Bağlantı http:// ya da https:// ile başlamalı: {bad[0]}")
        out["press_json"] = json.dumps(links, ensure_ascii=False)
    if has("nextStep"):
        out["next_step"] = core.text_field(body, "nextStep", 500, "Sıradaki adım")
    if has("nextOn"):
        out["next_on"] = _day(body.get("nextOn"), "Sıradaki adım tarihi")
    if has("tenderRef"):
        out["tender_ref"] = core.text_field(body, "tenderRef", 80, "İhale kaydı")
    if has("proposalText"):
        out["proposal_text"] = core.long_field(body, "proposalText", 60000, "Teklif metni")
    return out


def _project(r: Any, orgs: dict[str, Any], now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or core.now()
    today = now.astimezone(TZ).date()
    org = orgs.get(r.org_id) if r.org_id else None
    idx = STAGE_ORDER.index(r.stage) if r.stage in STAGE_ORDER else 0
    return {
        "id": r.id, "orgId": r.org_id, "orgName": org.name if org is not None else None,
        "orgKind": org.kind if org is not None else None, "title": r.title, "kind": r.kind,
        "kindLabel": PROJECT_KINDS.get(r.kind, r.kind), "stage": r.stage, "stageLabel": STAGES.get(r.stage, r.stage),
        "stageIndex": idx, "open": r.stage in OPEN_STAGES, "owner": r.owner, "ownerDisplay": r.owner_display,
        "summary": r.summary, "budget": _num(r.budget), "budgetApprovedBy": r.budget_approved_by,
        "budgetApprovedAt": core.iso(r.budget_approved_at), "books": core.json_list(r.books_json),
        "places": core.json_list(r.places_json), "orders": core.json_list(r.orders_json),
        "reachSchools": r.reach_schools, "reachStudents": r.reach_students, "reachBooks": r.reach_books,
        "reachParticipants": r.reach_participants, "press": core.json_list(r.press_json),
        "nextStep": r.next_step, "nextOn": _dayiso(r.next_on),
        "late": bool(r.stage in OPEN_STAGES and r.next_on and r.next_on < today),
        "tenderRef": r.tender_ref, "proposalText": r.proposal_text, "proposalStatus": r.proposal_status,
        "proposalStatusLabel": PROPOSAL_STATUS.get(r.proposal_status, r.proposal_status), "proposalAt": core.iso(r.proposal_at),
        "proposalError": r.proposal_error, "proposalApprovedBy": r.proposal_approved_by,
        "proposalApprovedAt": core.iso(r.proposal_approved_at), "createdBy": r.created_by, "createdAt": core.iso(r.created_at),
        "updatedAt": core.iso(r.updated_at), "closedAt": core.iso(r.closed_at),
    }


def _get_project(c: Any, tenant: str, pid: str, *, lock: bool = False) -> Any:
    stmt = sa.select(PROJECTS).where(PROJECTS.c.id == core.cid(pid, "Proje"), PROJECTS.c.tenant_id == tenant)
    row = c.execute(stmt.with_for_update() if lock else stmt).first()
    if not row:
        raise RelationError("Proje bulunamadı.", 404)
    return row


def _orgs(c: Any, tenant: str) -> dict[str, Any]:
    return {r.id: r for r in c.execute(orgs_stmt(tenant)).fetchall()}


def projects_stmts(tenant: str) -> tuple[Any, Any, Any]:
    """Projeler: (projeler, kurumlar, proje başına son olay)."""
    return (sa.select(PROJECTS).where(PROJECTS.c.tenant_id == tenant), orgs_stmt(tenant),
            sa.select(EVENTS.c.project_id, sa.func.max(EVENTS.c.at).label("at")).where(EVENTS.c.tenant_id == tenant)
            .group_by(EVENTS.c.project_id))


def project_stmts(tenant: str, pid: str) -> tuple[Any, Any, Any]:
    """Proje kartı: (proje, olayları, kurumlar)."""
    return (sa.select(PROJECTS).where(PROJECTS.c.id == pid, PROJECTS.c.tenant_id == tenant),
            sa.select(EVENTS).where(EVENTS.c.project_id == pid).order_by(EVENTS.c.at.desc()), orgs_stmt(tenant))


def orgs_list_stmts(tenant: str, archived: bool = False) -> tuple[Any, Any, Any]:
    """Kurum listesi: (kurum kartları, kurum başına etkin kişi, kurum başına açık proje)."""
    stmt = sa.select(ORGS).where(ORGS.c.tenant_id == tenant)
    stmt = stmt.where(ORGS.c.archived_at.isnot(None) if archived else ORGS.c.archived_at.is_(None))
    return (stmt,
            sa.select(PEOPLE.c.org_id, sa.func.count().label("n")).where(
                PEOPLE.c.tenant_id == tenant, PEOPLE.c.archived_at.is_(None), PEOPLE.c.org_id.isnot(None)).group_by(PEOPLE.c.org_id),
            sa.select(PROJECTS.c.org_id, sa.func.count().label("n")).where(
                PROJECTS.c.tenant_id == tenant, PROJECTS.c.stage.in_(OPEN_STAGES)).group_by(PROJECTS.c.org_id))


def org_notes_stmt(tenant: str, oid: str):
    return sa.select(NOTES).where(NOTES.c.tenant_id == tenant, NOTES.c.org_id == oid, NOTES.c.person_id.is_(None)) \
        .order_by(NOTES.c.at.desc())


def create_project(engine: sa.engine.Engine, tenant: str, user: str, display: str, body: dict[str, Any]) -> dict[str, Any]:
    now = core.now()
    with engine.begin() as c:
        vals = _project_values(c, tenant, body, partial=False)
        vals.pop("proposal_text", None)
        rid = uuid.uuid4().hex
        c.execute(PROJECTS.insert().values(id=rid, tenant_id=tenant, stage="fikir", proposal_status="yok", created_by=user,
                                           created_at=now, updated_by=user, updated_at=now, **vals))
        c.execute(EVENTS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, project_id=rid, at=now, user=user,
                                         user_display=(display or user)[:200], stage_from=None, stage_to="fikir",
                                         note="Proje açıldı"))
        return _project(c.execute(sa.select(PROJECTS).where(PROJECTS.c.id == rid)).first(), _orgs(c, tenant), now)


def update_project(engine: sa.engine.Engine, tenant: str, user: str, display: str, pid: str,
                   body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Alanları düzeltir; `stage` verilirse aşama olayı yazılır (`stageNote`, `docRef` ile). Bütçesi olan proje bütçe
    onayı olmadan «uygulama»ya geçmez; bütçe değişirse onay düşer."""
    now = core.now()
    with engine.begin() as c:
        row = _get_project(c, tenant, pid, lock=True)
        vals = _project_values(c, tenant, body, partial=True)
        if "budget" in vals and vals["budget"] != row.budget:
            vals.update(budget_approved_by=None, budget_approved_at=None)
        if "proposal_text" in vals and vals["proposal_text"] != row.proposal_text:
            vals.update(proposal_approved_by=None, proposal_approved_at=None)
            if vals["proposal_text"] and row.proposal_status in ("yok", "hata"):
                vals["proposal_status"] = "hazir"
        stage = body.get("stage")
        if stage is not None and stage != row.stage:
            if stage not in STAGES:
                raise RelationError("Aşama geçerli değil.")
            budget = vals.get("budget", row.budget)
            approved = vals.get("budget_approved_by", row.budget_approved_by)
            if STAGE_ORDER.index(stage) >= STAGE_ORDER.index("uygulama") and stage != "vazgecildi" and budget and not approved:
                raise RelationError("Bütçesi olan proje bütçe onayı olmadan uygulamaya geçmez.")
            vals["stage"] = stage
            vals["closed_at"] = now if stage in ("kapandi", "vazgecildi") else None
            c.execute(EVENTS.insert().values(
                id=uuid.uuid4().hex, tenant_id=tenant, project_id=row.id, at=now, user=user, user_display=(display or user)[:200],
                stage_from=row.stage, stage_to=stage, note=core.long_field(body, "stageNote", 4000, "Aşama notu"),
                doc_ref=core.text_field(body, "docRef", 500, "Belge")))
        elif body.get("stageNote"):
            c.execute(EVENTS.insert().values(
                id=uuid.uuid4().hex, tenant_id=tenant, project_id=row.id, at=now, user=user, user_display=(display or user)[:200],
                stage_from=row.stage, stage_to=row.stage, note=core.long_field(body, "stageNote", 4000, "Not"),
                doc_ref=core.text_field(body, "docRef", 500, "Belge")))
        changed = {k: v for k, v in vals.items() if getattr(row, k) != v}
        if changed:
            c.execute(PROJECTS.update().where(PROJECTS.c.id == row.id).values(updated_by=user, updated_at=now, **changed))
        diff = {k: {"before": str(getattr(row, k)) if getattr(row, k) is not None else None, "after": str(v) if v is not None else None}
                for k, v in changed.items() if k not in ("summary", "proposal_text", "books_json", "places_json", "orders_json")}
        return _project(c.execute(sa.select(PROJECTS).where(PROJECTS.c.id == row.id)).first(), _orgs(c, tenant), now), diff


def approve_project(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, pid: str, what: str,
                    decision: str = "onay") -> dict[str, Any]:
    """Bütçe (`what="budget"`) ya da teklif metni (`what="proposal"`) onayı; `decision="geri"` onayı kaldırır. Projeyi
    açan onaylayamaz (yönetici hariç)."""
    if what not in ("budget", "proposal") or decision not in ("onay", "geri"):
        raise RelationError("Onay türü geçerli değil.")
    now = core.now()
    with engine.begin() as c:
        row = _get_project(c, tenant, pid, lock=True)
        if decision == "onay" and row.created_by == user and not admin:
            raise RelationError("Projeyi açan kişi kendi projesini onaylayamaz.", 409)
        if what == "budget":
            if decision == "onay" and not row.budget:
                raise RelationError("Bütçe girilmemiş.")
            vals = {"budget_approved_by": user if decision == "onay" else None, "budget_approved_at": now if decision == "onay" else None}
        else:
            if decision == "onay" and not (row.proposal_text or "").strip():
                raise RelationError("Onaylanacak teklif metni yok.")
            vals = {"proposal_approved_by": user if decision == "onay" else None, "proposal_approved_at": now if decision == "onay" else None}
        c.execute(PROJECTS.update().where(PROJECTS.c.id == row.id).values(updated_by=user, updated_at=now, **vals))
        c.execute(EVENTS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, project_id=row.id, at=now, user=user,
                                         stage_from=row.stage, stage_to=row.stage,
                                         note=("Bütçe " if what == "budget" else "Teklif metni ") + ("onaylandı" if decision == "onay" else "onayı geri alındı")))
        return _project(c.execute(sa.select(PROJECTS).where(PROJECTS.c.id == row.id)).first(), _orgs(c, tenant), now)


def list_projects(engine: sa.engine.Engine, tenant: str, user: str, *, stage: str = "", kind: str = "", org_id: str = "",
                  q: str = "", scope: str = "", closed: bool = False) -> dict[str, Any]:
    now = core.now()
    pq, _oq, eq = projects_stmts(tenant)
    with engine.connect() as c:
        rows = c.execute(pq).fetchall()
        orgs = _orgs(c, tenant)
        last = {}
        for e in c.execute(eq).fetchall():
            last[e.project_id] = e.at
    nq = core.norm(q)
    month_ago = now - timedelta(days=30)
    items = []
    counts = {k: 0 for k in STAGES}
    for r in rows:
        counts[r.stage] = counts.get(r.stage, 0) + 1
        if not closed and r.stage not in OPEN_STAGES and not stage:
            continue
        if stage and r.stage != stage:
            continue
        if kind and r.kind != kind:
            continue
        if org_id and r.org_id != org_id:
            continue
        if scope == "benim" and user not in (r.owner or "", r.created_by):
            continue
        org = orgs.get(r.org_id) if r.org_id else None
        if nq and nq not in core.norm(" ".join(x for x in (r.title, org.name if org else None) if x)):
            continue
        at = last.get(r.id)
        items.append(dict(_project(r, orgs, now), lastEvent=core.iso(at),
                          quiet=bool(r.stage in OPEN_STAGES and (at is None or core.utc(at) < month_ago))))
    items.sort(key=lambda x: (not x["late"], x["stageIndex"], x["nextOn"] or "9999", x["title"].casefold()))
    return {"items": items, "total": len(items), "stages": counts}


def project_detail(engine: sa.engine.Engine, tenant: str, pid: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = _get_project(c, tenant, pid)
        evs = c.execute(project_stmts(tenant, row.id)[1]).fetchall()
        out = _project(row, _orgs(c, tenant))
    out["events"] = [{"id": e.id, "at": core.iso(e.at), "user": e.user, "userDisplay": e.user_display,
                      "stageFrom": e.stage_from, "stageTo": e.stage_to, "stageFromLabel": STAGES.get(e.stage_from or ""),
                      "stageToLabel": STAGES.get(e.stage_to or ""), "note": e.note, "docRef": e.doc_ref} for e in evs]
    return out


def set_proposal(engine: sa.engine.Engine, tenant: str, pid: str, *, status: str, user: Optional[str] = None,
                 text: Optional[str] = None, error: Optional[str] = None) -> None:
    vals: dict[str, Any] = {"proposal_status": status, "proposal_error": (error or None) and error[:500]}
    if status == "hazirlaniyor":
        vals["proposal_by"] = user
    if status == "hazir":
        vals.update(proposal_text=text, proposal_at=core.now(), proposal_approved_by=None, proposal_approved_at=None)
    with engine.begin() as c:
        c.execute(PROJECTS.update().where(PROJECTS.c.id == pid, PROJECTS.c.tenant_id == tenant).values(**vals))


def start_proposal(engine: sa.engine.Engine, tenant: str, pid: str, user: str) -> bool:
    """Taslak işini başlatır; zaten hazırlanıyorsa False (aynı proje için ikinci iş açılmaz)."""
    with engine.begin() as c:
        row = _get_project(c, tenant, pid, lock=True)
        if row.proposal_status == "hazirlaniyor":
            return False
        c.execute(PROJECTS.update().where(PROJECTS.c.id == row.id).values(proposal_status="hazirlaniyor", proposal_by=user,
                                                                          proposal_error=None))
    return True


# ------------------------------------------------------------------------------------------ teklif dosyası


def criteria() -> dict[str, Any]:
    try:
        return json.loads(CRITERIA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # pragma: no cover — dosya imajda yoksa madde bölümü boş kalır, ekranda yazar
        log.warning("public_affairs: ölçüt dosyası okunamadı: %s", e)
        return {"sources": {}, "items": [], "kinds": {}}


def criteria_for(kind: str) -> list[dict[str, Any]]:
    data = criteria()
    keys = set(data.get("kinds", {}).get(kind) or [])
    return [dict(it, sourceInfo=data.get("sources", {}).get(it["source"], {})) for it in data.get("items", []) if it["id"] in keys]


PROPOSAL_PROMPT = """Bir yayınevinin kurumsal ilişkiler sorumlusu adına bir kamu kurumuna sunulacak proje teklif dosyasının
metin bölümlerini yaz. Türkçe, resmî ve sade bir dille yaz.
Dört başlık yaz, her biri 1–2 kısa paragraf: «Amaç», «Kapsam», «Beklenen fayda», «Uygulama takvimi».
KESİNLİKLE rakam, sayı, tarih, tutar, yüzde, okul ya da öğrenci sayısı yazma: sayılar dosyada ayrı tabloda veriliyor.
Mevzuat maddesi, yönetmelik adı ya da madde numarası yazma: dayanak maddeleri dosyada ayrıca aynen alıntılanıyor.
Kitap adlarını verildiği gibi kullan; kitaplar hakkında listede olmayan bilgi uydurma. Başka kurum ya da kişi adı uydurma.
Başlıkları «## Amaç» biçiminde yaz.
Yayınevi: {company}
Kurum: {org} ({org_kind})
Proje: {title} — {kind}
Proje özeti (sorumlunun notu): {summary}
Kitaplar:
{books}
Metin:"""


def strip_numbers(text: str) -> str:
    """Model metninden rakam içeren satırlar atılır (başlıklar kalır): sayı yalnız koddan gelir."""
    keep = []
    for line in (text or "").splitlines():
        if line.lstrip().startswith("#") or not re.search(r"\d", line):
            keep.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


def reach_facts(project: dict[str, Any], places: list[dict[str, Any]], order_qty: Optional[int]) -> dict[str, Any]:
    """Proje kapsamının rakamları: hedef kurumlar CRM ziyaret yerlerinden (öğrenci/öğretmen metin kolonu, çevrilemeyen
    satır ayrıca sayılır), kitap adedi proje kitap listesinden, dağıtılan adet CRM siparişlerinden."""
    students = [p.get("ogrenci") for p in places]
    teachers = [p.get("ogretmen") for p in places]
    planned = [b.get("qty") for b in project.get("books") or []]
    return {
        "places": len(places),
        "students": sum(int(x) for x in students if x is not None),
        "studentsUnknown": sum(1 for x in students if x is None),
        "teachers": sum(int(x) for x in teachers if x is not None),
        "teachersUnknown": sum(1 for x in teachers if x is None),
        "bookTitles": len(project.get("books") or []),
        "booksPlanned": sum(int(x) for x in planned if x) if any(planned) else None,
        "booksDelivered": order_qty,
    }


def proposal_document(project: dict[str, Any], org: Optional[dict[str, Any]], model_text: str, facts: dict[str, Any],
                      books: list[dict[str, Any]], company: str) -> str:
    """Teklif dosyası (düz metin, başlıklar «##»): model bölümleri + koddan kapsam tablosu + kitap listesi + dayanak
    maddeleri (ölçüt dosyasından aynen, kaynaklı). Kaynağı olmayan madde yazılmaz."""
    lines = [f"# {project['title']}", "", f"{company} — {org['name'] if org else 'Kurum'} için proje teklifi ({project['kindLabel']})", ""]
    lines += [strip_numbers(model_text), ""]
    lines += ["## Kapsam (kaynak: CRM ve proje kaydı)", ""]
    if facts["places"]:
        lines.append(f"- Hedef kurum sayısı: {facts['places']}")
        lines.append(f"- Öğrenci sayısı (CRM ziyaret yerleri): {facts['students']}"
                     + (f" — {facts['studentsUnknown']} kurumda öğrenci sayısı kayıtlı değil" if facts["studentsUnknown"] else ""))
        if facts["teachers"] or facts["teachersUnknown"]:
            lines.append(f"- Öğretmen sayısı: {facts['teachers']}"
                         + (f" — {facts['teachersUnknown']} kurumda kayıtlı değil" if facts["teachersUnknown"] else ""))
    else:
        lines.append("- Hedef kurum henüz seçilmedi.")
    lines.append(f"- Kitap sayısı (başlık): {facts['bookTitles']}")
    if facts.get("booksPlanned"):
        lines.append(f"- Planlanan toplam adet: {facts['booksPlanned']}")
    lines.append("")
    if books:
        lines += ["## Kitap listesi", ""]
        for b in books:
            age = " · ".join(x for x in (b.get("hedefKitle"), b.get("yaslar")) if x)
            lines.append(f"- {b.get('name') or b.get('stockCode') or b['id']}" + (f" — {b['author']}" if b.get("author") else "")
                         + (f" ({age})" if age else "") + (f" · {b['qty']} adet" if b.get("qty") else ""))
        lines.append("")
    items = criteria_for(project["kind"])
    if items:
        lines += ["## Mevzuata uygunluk dayanakları", "",
                  "Aşağıdaki maddeler resmî kaynaklardan alınmıştır. Kitap listesinin bu maddelere uygunluğu teklif "
                  "kuruma verilmeden önce editör tarafından kontrol edilir.", ""]
        for it in items:
            info = it.get("sourceInfo") or {}
            lines.append(f"- {it['text']} ({info.get('short', it['source'])} {it['ref']})")
        lines.append("")
        srcs = {it["source"]: it.get("sourceInfo") or {} for it in items}
        lines.append("Kaynaklar: " + "; ".join(f"{info.get('title', k)} — {info.get('url', '')}" for k, info in srcs.items()))
    return "\n".join(lines).strip() + "\n"


# ------------------------------------------------------------------------------------------ ana sayfa ve rapor


def late_steps_stmt(tenant: str, now: datetime):
    """Günü geçmiş, yapılmamış «sıradaki adım» sayısı."""
    return sa.select(sa.func.count()).select_from(NOTES).where(
        NOTES.c.tenant_id == tenant, NOTES.c.next_step.isnot(None), NOTES.c.next_done.is_(False),
        NOTES.c.next_on.isnot(None), NOTES.c.next_on < now.astimezone(TZ).date())


def home(engine: sa.engine.Engine, tenant: str, user: str, st: dict[str, Any], *, now: Optional[datetime] = None) -> dict[str, Any]:
    """İlk açılış: temas zamanı gelen kişiler, açık projeler, bu ayın hediye programı (yalnız portal kaydı; CRM beklemez)."""
    now = now or core.now()
    people = list_people(engine, tenant, user, st, scope="zamani", now=now)
    projects = list_projects(engine, tenant, user)
    month = month_of(now)
    gifts = list_gifts(engine, tenant, month=month)
    with engine.connect() as c:
        steps = c.execute(late_steps_stmt(tenant, now)).scalar() or 0
    return {"due": people["items"], "dueTotal": people["total"], "peopleCounts": people["counts"],
            "projects": projects["items"], "projectStages": projects["stages"],
            "lateProjects": sum(1 for p in projects["items"] if p["late"]),
            "quietProjects": sum(1 for p in projects["items"] if p["quiet"]),
            "month": month, "gifts": gifts["counts"], "giftBooks": gifts["books"], "giftPeople": gifts["people"],
            "waitingApproval": gifts["counts"].get("oneri", 0), "lateSteps": int(steps)}


def report_stmts(tenant: str, year: int) -> tuple[Any, Any, Any, Any]:
    """Etki raporu: (etkin kişiler, yıldaki temas notları, yıldaki hediyeler, projeler)."""
    a = datetime(year, 1, 1, tzinfo=TZ).astimezone(timezone.utc)
    b = datetime(year + 1, 1, 1, tzinfo=TZ).astimezone(timezone.utc)
    return (sa.select(PEOPLE).where(PEOPLE.c.tenant_id == tenant, PEOPLE.c.archived_at.is_(None)),
            sa.select(NOTES.c.person_id, NOTES.c.org_id).where(NOTES.c.tenant_id == tenant, NOTES.c.at >= a, NOTES.c.at < b),
            sa.select(GIFTS).where(GIFTS.c.tenant_id == tenant, GIFTS.c.month >= f"{year}-01", GIFTS.c.month <= f"{year}-12"),
            sa.select(PROJECTS).where(PROJECTS.c.tenant_id == tenant))


def report(engine: sa.engine.Engine, tenant: str, user: str, st: dict[str, Any], year: int) -> dict[str, Any]:
    """Etki raporu (portal kısmı): temas, hediye, projeler ve erişim. CRM tanıtım toplamları API'de eklenir."""
    pq, nq, gq, jq = report_stmts(tenant, year)
    with engine.connect() as c:
        fields = _field_keys(c, tenant)
        people = c.execute(pq).fetchall()
        notes = c.execute(nq).fetchall()
        gifts = c.execute(gq).fetchall()
        projects = c.execute(jq).fetchall()
        orgs = _orgs(c, tenant)
    by_field: dict[str, int] = {}
    for p in people:
        k = fields.get(p.field_key or "", "Alan girilmemiş")
        by_field[k] = by_field.get(k, 0) + 1
    gstat = {k: 0 for k in GIFT_STATUS}
    for g in gifts:
        gstat[g.status] = gstat.get(g.status, 0) + 1
    sent = [g for g in gifts if g.status in ("sevk", "teslim", "donus")]
    active = [p for p in projects if p.stage != "vazgecildi"]
    return {
        "year": year,
        "people": {"total": len(people), "critical": sum(1 for p in people if p.priority == "kritik"),
                   "publicOfficials": sum(1 for p in people if p.is_public_official),
                   "byField": [{"label": k, "count": v} for k, v in sorted(by_field.items(), key=lambda x: -x[1])]},
        "contacts": {"notes": len(notes), "people": len({n.person_id for n in notes if n.person_id}),
                     "orgs": len({n.org_id for n in notes if n.org_id})},
        "gifts": {"byStatus": gstat, "sentBooks": len(sent), "sentPeople": len({g.person_id for g in sent}),
                  "feedback": sum(1 for g in gifts if g.status == "donus"),
                  "duplicates": _duplicate_count(gifts)},
        "projects": {"byStage": {k: sum(1 for p in projects if p.stage == k) for k in STAGES},
                     "items": [dict(_project(p, orgs)) for p in active],
                     "reach": {"schools": sum(p.reach_schools or 0 for p in active), "students": sum(p.reach_students or 0 for p in active),
                               "books": sum(p.reach_books or 0 for p in active),
                               "participants": sum(p.reach_participants or 0 for p in active)}},
    }


def _duplicate_count(gifts: Iterable[Any]) -> int:
    """Kabul 5: aynı kişiye aynı kitap (iptal dışı) birden çok satır."""
    seen: dict[tuple[str, str], int] = {}
    for g in gifts:
        if g.status != "iptal":
            seen[(g.person_id, g.crm_book_id)] = seen.get((g.person_id, g.crm_book_id), 0) + 1
    return sum(1 for v in seen.values() if v > 1)


def digest(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Haftalık iç özet: temas zamanı gelen kişiler (sahibine göre), geciken proje adımları, onay bekleyen hediye."""
    now = now or core.now()
    people = list_people(engine, tenant, "", st, scope="zamani", now=now)["items"]
    projects = [p for p in list_projects(engine, tenant, "")["items"] if p["late"] or p["quiet"]]
    waiting = list_gifts(engine, tenant, status="oneri")["total"]
    lines = [f"Temas zamanı gelen kişi: {len(people)}"]
    by_owner: dict[str, list[str]] = {}
    for p in people:
        by_owner.setdefault(p.get("ownerDisplay") or p.get("owner") or "Sahibi yok", []).append(
            f"{p['name']} ({'hiç temas yok' if p['heat']['daysSince'] is None else str(p['heat']['daysSince']) + ' gün'})")
    for o, names in sorted(by_owner.items()):
        lines.append(f"  {o}: " + ", ".join(names))
    lines.append(f"Adımı geciken ya da 30 gündür hareketsiz açık proje: {len(projects)}")
    for p in projects:
        lines.append(f"  {p['title']} — {p['stageLabel']}" + (f", adım tarihi {p['nextOn']}" if p["late"] else ", 30 gündür kayıt yok"))
    lines.append(f"Onay bekleyen hediye satırı: {waiting}")
    return {"due": len(people), "projects": len(projects), "waiting": waiting, "text": "\n".join(lines)}
