"""M1 Yeni kitap başvurusu, editoryal değerlendirme ve yayın kurulu — yazma tarafı.

CRM'de başvuru akışını taşıyan canlı bir kayıt yok (2026-09-28 ölçümü, CRM .28): `new_dosyabasvuruBase` 19 satır,
son kaydı 2024-05; 2024'ten beri açılan 2.751 projeden yalnız 1'inin kanalı «Web Başvurusu», 70'inin «Dosya
Başvurusu». Kurul kararları `new_yayinkurulutoplantilariBase`'te tutuluyor ama üye puanı/oyu yok. CRM'e yazma
yetkimiz de yok. Bu yüzden başvuru, editör değerlendirmesi, kurul oturumu, üye oyları ve karar **köprünün kendi
tablolarında** tutulur; CRM yalnız okunur (kategori = CRM «Kitaplık», benzer kitaplar, yazarın CRM geçmişi,
kabulden sonra CRM'de açılan proje kartının bağı).

Akış (iş tanımı «Aşama 1 / Aşama 2»):

    yeni ──(editör atanır)──▶ degerlendirmede ──(editör raporu tamam)──┬─▶ kurul_bekliyor ──▶ kurulda ──┬─▶ kabul
                                   ▲                                    ├─▶ revizyon (yazara revizyon yazısı) │
                                   └──────────── yeniden aç ◀───────────┼─▶ red (arşiv + red yazısı)         ├─▶ revizyon
                                                                        └─▶ geri_cekildi (arşiv)             ├─▶ red
                                                                                                             └─▶ ertele → kurul_bekliyor

Kurul oturumu: tarih, başkan, üyeler, gündem (kurula çıkan başvurular). Her üye gündemdeki her başvuruya kendi
üç eksen puanını (misyon, yayıncılık, ticari; 0–100) ve oyunu (kabul / revizyon / red / çekimser) girer. Toplam
karar skoru üç eksenin eşit ağırlıklı ortalamasıdır; skor eşikleri yönetim ekranından değişir. Kararı başkan ya da
«yayın kurulu yönetimi» yetkisi olan kişi kaydeder; oy çoğunluğu ve skor önerisi ekranda yanında durur, karar
insanındır. Oturum kapanınca karara bağlanmamış başvurular «ertelendi» olur ve kurul sırasına döner.

Gizlilik: üye oy verene kadar başkalarının oylarını görmez (etkilenmesin diye); adıyla oy ve not yalnız başkan,
yönetici ve «üye görüşleri» yetkisi olanlara açıktır; diğerleri dağılımı görür.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.editorial_applications")

_md = sa.MetaData()

APPS = sa.Table(
    "semantic_editorial_applications", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("no", sa.String(20), nullable=False),
    sa.Column("status", sa.String(20), nullable=False, index=True),
    sa.Column("round", sa.Integer, nullable=False, default=1),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("author_name", sa.String(200), nullable=False),
    sa.Column("author_email", sa.String(200)),
    sa.Column("author_phone", sa.String(60)),
    sa.Column("author_bio", sa.Text),
    sa.Column("author_expertise", sa.Text),
    sa.Column("author_history", sa.Text),
    sa.Column("agency_name", sa.String(200)),
    sa.Column("agency_contact", sa.String(200)),
    sa.Column("crm_contact_id", sa.String(40)),
    sa.Column("summary", sa.Text, nullable=False),
    sa.Column("audience", sa.String(20)),
    sa.Column("age_from", sa.Integer),
    sa.Column("age_to", sa.Integer),
    sa.Column("page_estimate", sa.Integer, nullable=False),
    sa.Column("genre", sa.String(120)),
    sa.Column("category_id", sa.String(40)),
    sa.Column("category_name", sa.String(200)),
    sa.Column("series", sa.String(300)),
    sa.Column("publisher_note", sa.Text),
    sa.Column("channel", sa.String(20), nullable=False),
    sa.Column("received_on", sa.Date, nullable=False),
    sa.Column("evaluator", sa.String(120)),
    sa.Column("evaluator_name", sa.String(200)),
    sa.Column("decision_note", sa.Text),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("crm_project_id", sa.String(40)),
    sa.Column("crm_project_name", sa.String(300)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "no", name="uq_editorial_application_no"),
)
FILES = sa.Table(
    "semantic_editorial_application_files", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("app_id", sa.String(32), nullable=False, index=True),
    sa.Column("kind", sa.String(20), nullable=False),              # dosya | ozgecmis | revizyon | diger
    sa.Column("round", sa.Integer, nullable=False, default=1),
    sa.Column("filename", sa.String(300), nullable=False),
    sa.Column("mime", sa.String(120), nullable=False),
    sa.Column("bytes", sa.Integer, nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("path", sa.String(600), nullable=False),
    sa.Column("uploaded_by", sa.String(120), nullable=False),
    sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
)
EVALS = sa.Table(
    "semantic_editorial_application_evals", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("app_id", sa.String(32), nullable=False, index=True),
    sa.Column("round", sa.Integer, nullable=False),
    sa.Column("evaluator", sa.String(120), nullable=False),
    sa.Column("evaluator_name", sa.String(200)),
    sa.Column("content_score", sa.Integer),
    sa.Column("mission", sa.Integer),
    sa.Column("publishing", sa.Integer),
    sa.Column("commercial", sa.Integer),
    sa.Column("recommendation", sa.String(12)),
    sa.Column("topic", sa.String(200)),
    sa.Column("genre", sa.String(120)),
    sa.Column("age_group", sa.String(120)),
    sa.Column("overlap_note", sa.Text),
    sa.Column("redline", sa.String(20)),
    sa.Column("redline_note", sa.Text),
    sa.Column("report", sa.Text),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("app_id", "round", name="uq_editorial_application_eval_round"),
)
LOG = sa.Table(
    "semantic_editorial_application_log", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("app_id", sa.String(32), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("actor", sa.String(120), nullable=False),
    sa.Column("actor_name", sa.String(200)),
    sa.Column("action", sa.String(24), nullable=False),
    sa.Column("detail", sa.Text),
)
LETTERS = sa.Table(
    "semantic_editorial_application_letters", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("app_id", sa.String(32), nullable=False, index=True),
    sa.Column("kind", sa.String(12), nullable=False),               # kabul | red | revizyon
    sa.Column("state", sa.String(12), nullable=False),              # taslak | onaylandi | gonderildi
    sa.Column("subject", sa.String(300), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_name", sa.String(200)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("sent_on", sa.Date),
    sa.Column("sent_channel", sa.String(20)),
    sa.Column("sent_by", sa.String(120)),
)
SESSIONS = sa.Table(
    "semantic_editorial_board_sessions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("meet_on", sa.Date, nullable=False),
    sa.Column("meet_at", sa.String(5)),
    sa.Column("place", sa.String(200)),
    sa.Column("chair", sa.String(120), nullable=False),
    sa.Column("chair_name", sa.String(200)),
    sa.Column("members_json", sa.Text, nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("state", sa.String(12), nullable=False),              # planli | kapandi
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("closed_by", sa.String(120)),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
)
AGENDA = sa.Table(
    "semantic_editorial_board_agenda", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("session_id", sa.String(32), nullable=False, index=True),
    sa.Column("app_id", sa.String(32), nullable=False, index=True),
    sa.Column("position", sa.Integer, nullable=False),
    sa.Column("decision", sa.String(12)),                           # kabul | revizyon | red | ertele | ertelendi
    sa.Column("decision_note", sa.Text),
    sa.Column("print_run", sa.Integer),
    sa.Column("price", sa.Numeric(12, 2)),
    sa.Column("royalty", sa.Numeric(5, 2)),
    sa.Column("publish_on", sa.Date),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_name", sa.String(200)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("added_by", sa.String(120), nullable=False),
    sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("session_id", "app_id", name="uq_editorial_board_agenda"),
)
VOTES = sa.Table(
    "semantic_editorial_board_votes", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("session_id", sa.String(32), nullable=False, index=True),
    sa.Column("app_id", sa.String(32), nullable=False),
    sa.Column("member", sa.String(120), nullable=False),
    sa.Column("member_name", sa.String(200)),
    sa.Column("mission", sa.Integer),
    sa.Column("publishing", sa.Integer),
    sa.Column("commercial", sa.Integer),
    sa.Column("vote", sa.String(12), nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("session_id", "app_id", "member", name="uq_editorial_board_vote"),
)
REPORTS = sa.Table(
    "semantic_editorial_application_reports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("app_id", sa.String(32), nullable=False, index=True),
    sa.Column("status", sa.String(16), nullable=False),             # hazirlaniyor | hazir | hata
    sa.Column("content_json", sa.Text),
    sa.Column("error", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)
MARKET = sa.Table(
    "semantic_editorial_market_cache", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("category_id", sa.String(40), primary_key=True),
    sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("content_json", sa.Text, nullable=False),
)

STATUSES = {
    "yeni": "Yeni başvuru",
    "degerlendirmede": "Editör değerlendirmesinde",
    "revizyon": "Yazardan revizyon bekleniyor",
    "kurul_bekliyor": "Kurula çıkacak",
    "kurulda": "Kurul gündeminde",
    "kabul": "Kabul edildi",
    "red": "Reddedildi",
    "geri_cekildi": "Geri çekildi",
}
QUEUE = ("yeni", "degerlendirmede", "revizyon", "kurul_bekliyor", "kurulda")
ARCHIVE = ("red", "geri_cekildi")
VIEWS = {"kuyruk": QUEUE, "kabul": ("kabul",), "arsiv": ARCHIVE, "hepsi": tuple(STATUSES)}

#: Geliş kanalı: CRM projesinin «Oluşturma kanalı» ve dosya başvurusunun «Geliş kaynağı» sözlüklerinin birleşimi.
CHANNELS = {
    "web": "Web başvurusu", "eposta": "E-posta", "posta": "Posta", "ajans": "Ajans / temsilci",
    "referans": "Referans ile", "mevcut_yazar": "Mevcut yazar", "fuar": "Fuar", "yurtdisi": "Yurt dışı", "diger": "Diğer",
}
#: Hedef kitle: CRM kitap kartının «Hedef kitle» seçenekleri.
AUDIENCES = {"cocuk": "Çocuk", "genc": "Genç", "yetiskin": "Yetişkin"}
FILE_KINDS = {"dosya": "Eser dosyası", "ozgecmis": "Özgeçmiş", "revizyon": "Revize dosya", "diger": "Diğer"}
FILE_EXT = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
}
#: İş tanımı: «PDF/DOCX upload • Max. 10 MB». Test sunucusu ve VM'deki nginx genel sınırı da 10 MB.
FILE_MAX = 10 * 1024 * 1024
RECOMMENDATIONS = {"kabul": "Kabul", "revizyon": "Revizyon", "red": "Red"}
REDLINES = {"temiz": "Sorun yok", "dikkat": "Dikkat gerektiriyor", "uygun_degil": "Yayın ilkelerine aykırı"}
VOTES_LABEL = {"kabul": "Kabul", "revizyon": "Revizyon", "red": "Red", "cekimser": "Çekimser"}
DECISIONS = {"kabul": "Kabul", "revizyon": "Revizyon", "red": "Red", "ertele": "Sonraki kurula ertelendi",
             "ertelendi": "Karar verilmeden ertelendi"}
LETTER_KINDS = {"kabul": "Kabul yazısı", "red": "Red yazısı", "revizyon": "Revizyon talebi"}
LETTER_STATES = {"taslak": "Taslak", "onaylandi": "Onaylandı", "gonderildi": "Gönderildi"}
SEND_CHANNELS = {"eposta": "E-posta", "posta": "Posta", "telefon": "Telefon", "elden": "Elden"}
#: Toplam karar skoru eşikleri (yönetim ekranından değişir): ≥ kabul → Kabul, ≥ revizyon → Revizyon, altı Red.
DEFAULT_ACCEPT, DEFAULT_REVISE = 70, 50

_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USER = re.compile(r"^[a-z0-9._\-]{1,120}$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

_ready: set[int] = set()
_lock = threading.Lock()


class ApplicationError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def reset_stale_reports(engine: sa.engine.Engine) -> int:
    """Köprü yeniden başlarken yarıda kalan rapor hazırlığı «hata» olur; ekran «yeniden üret» der."""
    with engine.begin() as c:
        return c.execute(sa.update(REPORTS).where(REPORTS.c.status == "hazirlaniyor").values(
            status="hata", error="Rapor hazırlanırken sunucu yeniden başladı; raporu yeniden üretin.", finished_at=_now())).rowcount


# ------------------------------------------------------------------------------------------------ yardımcılar

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new() -> str:
    return uuid.uuid4().hex


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v.isoformat() if isinstance(v, date) else str(v)


def _line(v: Any, n: int) -> Optional[str]:
    t = " ".join(str(v or "").split())
    return t[:n] or None


def _para(v: Any, n: int) -> Optional[str]:
    t = str(v or "").replace("\r\n", "\n").strip()
    return t[:n] or None


def _choice(v: Any, allowed: dict[str, str], what: str, *, required: bool = False) -> Optional[str]:
    t = str(v or "").strip()
    if not t:
        if required:
            raise ApplicationError(f"{what} seçilmeli.")
        return None
    if t not in allowed:
        raise ApplicationError(f"{what} geçerli değil.")
    return t


def _score(v: Any, what: str) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        n = int(round(float(str(v).replace(",", "."))))
    except ValueError:
        raise ApplicationError(f"{what} 0 ile 100 arasında bir sayı olmalı.") from None
    if not 0 <= n <= 100:
        raise ApplicationError(f"{what} 0 ile 100 arasında olmalı.")
    return n


def _int(v: Any, what: str, low: int, high: int) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        n = int(str(v).strip())
    except ValueError:
        raise ApplicationError(f"{what} tam sayı olmalı.") from None
    if not low <= n <= high:
        raise ApplicationError(f"{what} {low} ile {high:,} arasında olmalı.".replace(",", "."))
    return n


def _day(v: Any, what: str) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ApplicationError(f"{what} YYYY-AA-GG biçiminde olmalı.") from None


def _guid(v: Any, what: str) -> Optional[str]:
    t = str(v or "").strip().strip("{}")
    if not t:
        return None
    if not _GUID.match(t):
        raise ApplicationError(f"{what} geçerli değil.")
    return t.lower()


def _user(v: Any, what: str = "Kişi") -> str:
    t = str(v or "").strip().lower().rsplit("\\", 1)[-1]
    if not _USER.match(t):
        raise ApplicationError(f"{what} geçerli bir portal kullanıcısı değil.")
    return t


def _money(v: Any, what: str, high: float) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(" ", "").replace(",", "."))
    except ValueError:
        raise ApplicationError(f"{what} sayı olmalı.") from None
    if not 0 <= f <= high:
        raise ApplicationError(f"{what} 0 ile {high:g} arasında olmalı.")
    return round(f, 2)


def _log(c: Any, app_id: str, actor: str, actor_name: Optional[str], action: str, detail: Any = None) -> None:
    c.execute(LOG.insert().values(id=_new(), app_id=app_id, at=_now(), actor=actor, actor_name=actor_name,
                                  action=action, detail=json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None))


def _row(c: Any, tenant: str, app_id: str) -> Any:
    r = c.execute(sa.select(APPS).where(APPS.c.tenant_id == tenant, APPS.c.id == str(app_id or ""))).first()
    if r is None:
        raise ApplicationError("Başvuru bulunamadı.", 404)
    return r


def _next_no(c: Any, tenant: str, year: int) -> str:
    prefix = f"B-{year}-"
    last = c.execute(sa.select(sa.func.max(APPS.c.no)).where(APPS.c.tenant_id == tenant, APPS.c.no.like(prefix + "%"))).scalar()
    n = int(last.rsplit("-", 1)[-1]) + 1 if last else 1
    return f"{prefix}{n:04d}"


# ---------------------------------------------------------------------------------------------- başvuru

_FIELDS = {
    # anahtar (ekran) → (kolon, dönüştürücü)
    "title": ("title", lambda v: _line(v, 300)),
    "authorName": ("author_name", lambda v: _line(v, 200)),
    "authorEmail": ("author_email", lambda v: _line(v, 200)),
    "authorPhone": ("author_phone", lambda v: _line(v, 60)),
    "authorBio": ("author_bio", lambda v: _para(v, 8000)),
    "authorExpertise": ("author_expertise", lambda v: _para(v, 4000)),
    "authorHistory": ("author_history", lambda v: _para(v, 8000)),
    "agencyName": ("agency_name", lambda v: _line(v, 200)),
    "agencyContact": ("agency_contact", lambda v: _line(v, 200)),
    "crmContactId": ("crm_contact_id", lambda v: _guid(v, "CRM kişisi")),
    "summary": ("summary", lambda v: _para(v, 20000)),
    "audience": ("audience", lambda v: _choice(v, AUDIENCES, "Hedef kitle")),
    "ageFrom": ("age_from", lambda v: _int(v, "Yaş (en az)", 0, 120)),
    "ageTo": ("age_to", lambda v: _int(v, "Yaş (en çok)", 0, 120)),
    "pageEstimate": ("page_estimate", lambda v: _int(v, "Sayfa tahmini", 1, 20000)),
    "genre": ("genre", lambda v: _line(v, 120)),
    "categoryId": ("category_id", lambda v: _guid(v, "Kategori")),
    "categoryName": ("category_name", lambda v: _line(v, 200)),
    "series": ("series", lambda v: _line(v, 300)),
    "publisherNote": ("publisher_note", lambda v: _para(v, 8000)),
    "channel": ("channel", lambda v: _choice(v, CHANNELS, "Geliş kanalı")),
    "receivedOn": ("received_on", lambda v: _day(v, "Geliş tarihi")),
}


def _clean(body: dict[str, Any], partial: bool) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    for key, (col, fn) in _FIELDS.items():
        if key in body:
            vals[col] = fn(body.get(key))
    if not partial:
        vals.setdefault("channel", None)
        vals.setdefault("received_on", None)
    # Zorunlu alanlar (iş tanımı: «Zorunlu: Özet + Biyografi + Sayfa tahmini»; eser ve yazar adı olmadan kayıt olmaz).
    for col, what in (("title", "Eser adı"), ("author_name", "Yazar adı"), ("summary", "Eser özeti"),
                      ("author_bio", "Yazar biyografisi"), ("page_estimate", "Sayfa tahmini")):
        if (not partial or col in vals) and not vals.get(col):
            raise ApplicationError(f"{what} boş olamaz.")
    if vals.get("author_email") and not _EMAIL.match(vals["author_email"]):
        raise ApplicationError("E-posta adresi geçerli değil.")
    if not partial:
        vals["channel"] = vals.get("channel") or "diger"
        vals["received_on"] = vals.get("received_on") or _now().date()
    if "channel" in vals and not vals["channel"]:
        vals["channel"] = "diger"
    if "received_on" in vals and vals["received_on"] is None:
        raise ApplicationError("Geliş tarihi boş olamaz.")
    if vals.get("received_on") and vals["received_on"] > _now().date():
        raise ApplicationError("Geliş tarihi ileri bir gün olamaz.")
    if vals.get("category_id") and not vals.get("category_name"):
        raise ApplicationError("Kategori adı eksik; kategoriyi listeden seçin.")
    if "category_id" in vals and not vals["category_id"]:
        vals["category_name"] = None
    return vals


def create(engine: sa.engine.Engine, tenant: str, user: str, display: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _clean(body, partial=False)
    _ages(vals.get("age_from"), vals.get("age_to"))
    aid = _new()
    for attempt in range(3):
        try:
            with engine.begin() as c:
                no = _next_no(c, tenant, vals["received_on"].year)
                c.execute(APPS.insert().values(id=aid, tenant_id=tenant, no=no, status="yeni", round=1, created_by=user,
                                               created_at=_now(), **vals))
                _log(c, aid, user, display, "olusturuldu", {"no": no})
            break
        except sa.exc.IntegrityError:
            if attempt == 2:
                raise ApplicationError("Başvuru numarası verilemedi; yeniden deneyin.", 409) from None
    with engine.connect() as c:
        return _out(_row(c, tenant, aid))


def _ages(a: Optional[int], b: Optional[int]) -> None:
    if a is not None and b is not None and a > b:
        raise ApplicationError("Yaş aralığında «en az» «en çok»tan büyük olamaz.")


def update(engine: sa.engine.Engine, tenant: str, user: str, display: str, app_id: str,
           body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    vals = _clean(body, partial=True)
    with engine.begin() as c:
        r = _row(c, tenant, app_id)
        if r.status in ("kabul",) + ARCHIVE:
            raise ApplicationError("Kapanmış başvuru düzenlenmez; önce yeniden açın.", 409)
        _ages(vals.get("age_from", r.age_from), vals.get("age_to", r.age_to))
        diff = sorted(k for k, v in vals.items() if getattr(r, k) != v)
        if diff:
            c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(updated_by=user, updated_at=_now(), **vals))
            _log(c, r.id, user, display, "duzenlendi", {"alanlar": diff})
        return _out(_row(c, tenant, app_id)), diff


def _out(r: Any, *, evaluation: Any = None) -> dict[str, Any]:
    return {
        "id": r.id, "no": r.no, "status": r.status, "statusLabel": STATUSES.get(r.status, r.status), "round": r.round,
        "title": r.title, "authorName": r.author_name, "authorEmail": r.author_email, "authorPhone": r.author_phone,
        "authorBio": r.author_bio, "authorExpertise": r.author_expertise, "authorHistory": r.author_history,
        "agencyName": r.agency_name, "agencyContact": r.agency_contact, "crmContactId": r.crm_contact_id,
        "summary": r.summary, "audience": r.audience, "audienceLabel": AUDIENCES.get(r.audience or ""),
        "ageFrom": r.age_from, "ageTo": r.age_to, "pageEstimate": r.page_estimate, "genre": r.genre,
        "categoryId": r.category_id, "categoryName": r.category_name, "series": r.series, "publisherNote": r.publisher_note,
        "channel": r.channel, "channelLabel": CHANNELS.get(r.channel, r.channel), "receivedOn": _iso(r.received_on),
        "evaluator": r.evaluator, "evaluatorName": r.evaluator_name, "decisionNote": r.decision_note,
        "decidedBy": r.decided_by, "decidedAt": _iso(r.decided_at), "crmProjectId": r.crm_project_id,
        "crmProjectName": r.crm_project_name, "createdBy": r.created_by, "createdAt": _iso(r.created_at),
        "updatedAt": _iso(r.updated_at),
    }


def _fold(text: str) -> str:
    return str(text).replace("İ", "i").replace("I", "ı").lower()


def _waiting_days(r: Any, today: date) -> int:
    ref = r.updated_at or r.created_at
    ref = (ref if ref.tzinfo else ref.replace(tzinfo=timezone.utc)).date() if isinstance(ref, datetime) else today
    return max(0, (today - ref).days)


def listing(engine: sa.engine.Engine, tenant: str, user: str, *, view: str = "kuyruk", q: str = "", status: str = "",
            mine: bool = False) -> dict[str, Any]:
    """Başvuru kuyruğu / kabul edilenler / arşiv. Satır tavanı yok; sayaçlar her durum için ayrı."""
    if view not in VIEWS:
        raise ApplicationError("Görünüm geçerli değil.")
    with engine.connect() as c:
        counts = {s: 0 for s in STATUSES}
        for s, n in c.execute(sa.select(APPS.c.status, sa.func.count()).where(APPS.c.tenant_id == tenant).group_by(APPS.c.status)):
            counts[s] = int(n)
        cond = [APPS.c.tenant_id == tenant, APPS.c.status.in_(VIEWS[view])]
        if status:
            if status not in STATUSES:
                raise ApplicationError("Durum geçerli değil.")
            cond.append(APPS.c.status == status)
        if mine:
            cond.append(APPS.c.evaluator == user)
        rows = c.execute(sa.select(APPS).where(*cond).order_by(APPS.c.received_on.desc(), APPS.c.no.desc())).all()
        if q.strip():
            # Türkçe büyük/küçük harf veritabanına bırakılmaz (İ/ı): arama burada, aynı katlamayla yapılır.
            want = _fold(q.strip()[:80])
            rows = [r for r in rows if any(want in _fold(v) for v in (r.title, r.author_name, r.no, r.agency_name) if v)]
        ids = [r.id for r in rows]
        evals = {(e.app_id, e.round): e for e in c.execute(sa.select(EVALS).where(EVALS.c.app_id.in_(ids)))} if ids else {}
        files = dict(c.execute(sa.select(FILES.c.app_id, sa.func.count()).where(FILES.c.app_id.in_(ids)).group_by(FILES.c.app_id)).all()) if ids else {}
        sessions = _open_agenda(c, ids)
    today = _now().date()
    items = []
    for r in rows:
        e = evals.get((r.id, r.round))
        items.append({
            "id": r.id, "no": r.no, "status": r.status, "statusLabel": STATUSES.get(r.status, r.status), "title": r.title,
            "authorName": r.author_name, "agencyName": r.agency_name, "categoryName": r.category_name,
            "channelLabel": CHANNELS.get(r.channel, r.channel), "receivedOn": _iso(r.received_on),
            "pageEstimate": r.page_estimate, "evaluator": r.evaluator, "evaluatorName": r.evaluator_name,
            "mine": bool(user) and r.evaluator == user, "files": int(files.get(r.id, 0)),
            "evaluation": {"submitted": bool(e.submitted_at), "contentScore": e.content_score,
                           "recommendation": e.recommendation} if e is not None else None,
            "session": sessions.get(r.id), "waitingDays": _waiting_days(r, today) if r.status in QUEUE else None,
            "decidedAt": _iso(r.decided_at), "decisionNote": r.decision_note,
        })
    return {"items": items, "counts": counts, "view": view,
            "totals": {k: sum(counts[s] for s in v) for k, v in VIEWS.items()}}


def _open_agenda(c: Any, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Başvurunun kararı verilmemiş gündem kaydı (kurulda olanlar için oturum tarihi)."""
    if not ids:
        return {}
    q = (sa.select(AGENDA.c.app_id, SESSIONS.c.id, SESSIONS.c.title, SESSIONS.c.meet_on)
         .join(SESSIONS, SESSIONS.c.id == AGENDA.c.session_id)
         .where(AGENDA.c.app_id.in_(ids), AGENDA.c.decision.is_(None), SESSIONS.c.state == "planli"))
    return {r.app_id: {"id": r.id, "title": r.title, "date": _iso(r.meet_on)} for r in c.execute(q)}


def detail(engine: sa.engine.Engine, tenant: str, user: str, app_id: str, *, can_see_names: bool) -> dict[str, Any]:
    with engine.connect() as c:
        r = _row(c, tenant, app_id)
        out = _out(r)
        out["files"] = [_file_out(f) for f in c.execute(sa.select(FILES).where(FILES.c.app_id == r.id).order_by(FILES.c.uploaded_at.desc()))]
        out["evaluations"] = [_eval_out(e) for e in c.execute(sa.select(EVALS).where(EVALS.c.app_id == r.id).order_by(EVALS.c.round.desc()))]
        cur = next((e for e in out["evaluations"] if e["round"] == r.round), None)
        out["evaluation"] = cur
        out["log"] = [{"at": _iso(x.at), "actor": x.actor, "actorName": x.actor_name or x.actor, "action": x.action,
                       "detail": json.loads(x.detail) if x.detail else None}
                      for x in c.execute(sa.select(LOG).where(LOG.c.app_id == r.id).order_by(LOG.c.at.desc()))]
        out["letters"] = [_letter_out(x) for x in c.execute(sa.select(LETTERS).where(LETTERS.c.app_id == r.id).order_by(LETTERS.c.created_at.desc()))]
        out["board"] = _board_history(c, r.id, user, can_see_names)
        rep = c.execute(sa.select(REPORTS.c.id, REPORTS.c.status, REPORTS.c.created_at, REPORTS.c.finished_at, REPORTS.c.error)
                        .where(REPORTS.c.app_id == r.id).order_by(REPORTS.c.created_at.desc()).limit(1)).first()
        out["report"] = {"id": rep.id, "status": rep.status, "createdAt": _iso(rep.created_at),
                         "finishedAt": _iso(rep.finished_at), "error": rep.error} if rep else None
    out["mine"] = bool(user) and r.evaluator == user
    return out


def _board_history(c: Any, app_id: str, user: str, can_see_names: bool) -> list[dict[str, Any]]:
    """Başvurunun girdiği bütün kurul oturumları: tarih, karar ve oy dağılımı."""
    out = []
    rows = c.execute(sa.select(AGENDA, SESSIONS.c.title, SESSIONS.c.meet_on, SESSIONS.c.state, SESSIONS.c.chair,
                               SESSIONS.c.members_json)
                     .join(SESSIONS, SESSIONS.c.id == AGENDA.c.session_id)
                     .where(AGENDA.c.app_id == app_id).order_by(SESSIONS.c.meet_on.desc())).all()
    for a in rows:
        votes = list(c.execute(sa.select(VOTES).where(VOTES.c.session_id == a.session_id, VOTES.c.app_id == app_id)))
        names = can_see_names or a.chair == user
        out.append({"sessionId": a.session_id, "title": a.title, "date": _iso(a.meet_on), "state": a.state,
                    "decision": a.decision, "decisionLabel": DECISIONS.get(a.decision or ""), "note": a.decision_note,
                    "printRun": a.print_run, "price": float(a.price) if a.price is not None else None,
                    "royalty": float(a.royalty) if a.royalty is not None else None, "publishOn": _iso(a.publish_on),
                    "decidedByName": a.decided_name, "decidedAt": _iso(a.decided_at),
                    "tally": tally(votes, len(_members(a.members_json))),
                    "votes": [_vote_out(v) for v in votes] if (names and a.decision) else None})
    return out


# -------------------------------------------------------------------------------------------------- dosyalar

def _file_out(f: Any) -> dict[str, Any]:
    return {"id": f.id, "kind": f.kind, "kindLabel": FILE_KINDS.get(f.kind, f.kind), "round": f.round, "filename": f.filename,
            "mime": f.mime, "bytes": f.bytes, "uploadedBy": f.uploaded_by, "uploadedAt": _iso(f.uploaded_at)}


def _root() -> str:
    return os.environ.get("EDITORIAL_APPLICATIONS_DIR", "/data/nanobaseai/bi/var/applications")


def _ext(filename: str) -> str:
    return re.sub(r"[^a-z0-9]", "", filename.lower().rsplit(".", 1)[-1])[:8] if "." in filename else ""


def _magic_ok(data: bytes, ext: str) -> bool:
    head = data[:8]
    if ext == "pdf":
        return head.startswith(b"%PDF")
    if ext == "docx":
        return head.startswith(b"PK\x03\x04")
    if ext == "doc":
        return head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    return False


def add_file(engine: sa.engine.Engine, tenant: str, user: str, display: str, app_id: str, filename: str, kind: str,
             data: bytes) -> dict[str, Any]:
    name = os.path.basename(str(filename or "").replace("\\", "/")).strip()[:300]
    ext = _ext(name)
    if ext not in FILE_EXT:
        raise ApplicationError("Dosya PDF, DOCX ya da DOC olmalı.")
    kind = _choice(kind or "dosya", FILE_KINDS, "Dosya türü") or "dosya"
    if not data:
        raise ApplicationError("Dosya boş.")
    if len(data) > FILE_MAX:
        raise ApplicationError("Dosya 10 MB sınırını aşıyor.", 413)
    if not _magic_ok(data, ext):
        raise ApplicationError("Dosyanın içeriği uzantısıyla uyuşmuyor.")
    with engine.connect() as c:
        r = _row(c, tenant, app_id)
    fid = _new()
    folder = os.path.join(_root(), tenant, r.id)
    path = os.path.join(folder, f"{fid}.{ext}")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as e:
        log.error("başvuru dosyası yazılamadı (%s): %s", path, e)
        raise ApplicationError("Dosya sunucuya kaydedilemedi; yöneticiye bildirin.", 503) from e
    row = {"id": fid, "app_id": r.id, "kind": kind, "round": r.round, "filename": name, "mime": FILE_EXT[ext],
           "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "path": path, "uploaded_by": user,
           "uploaded_at": _now()}
    with engine.begin() as c:
        c.execute(FILES.insert().values(**row))
        _log(c, r.id, user, display, "dosya", {"ad": name, "tur": FILE_KINDS[kind]})
    return _file_out(_Obj(row))


class _Obj:
    def __init__(self, d: dict[str, Any]):
        self.__dict__.update(d)


def file_for(engine: sa.engine.Engine, tenant: str, file_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        f = c.execute(sa.select(FILES, APPS.c.tenant_id).join(APPS, APPS.c.id == FILES.c.app_id)
                      .where(FILES.c.id == str(file_id or ""), APPS.c.tenant_id == tenant)).first()
    if f is None or not os.path.isfile(f.path):
        raise ApplicationError("Dosya bulunamadı.", 404)
    return {"path": f.path, "filename": f.filename, "mime": f.mime, "appId": f.app_id}


def delete_file(engine: sa.engine.Engine, tenant: str, user: str, display: str, file_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        f = c.execute(sa.select(FILES).join(APPS, APPS.c.id == FILES.c.app_id)
                      .where(FILES.c.id == str(file_id or ""), APPS.c.tenant_id == tenant)).first()
        if f is None:
            raise ApplicationError("Dosya bulunamadı.", 404)
        app = _row(c, tenant, f.app_id)
        if app.status in ("kabul",) + ARCHIVE:
            raise ApplicationError("Kapanmış başvurunun dosyası silinmez.", 409)
        c.execute(FILES.delete().where(FILES.c.id == f.id))
        _log(c, f.app_id, user, display, "dosya_silindi", {"ad": f.filename})
    try:
        os.remove(f.path)
    except OSError as e:
        log.warning("başvuru dosyası diskten silinemedi (%s): %s", f.path, e)
    return {"id": f.id, "appId": f.app_id, "filename": f.filename}


# ------------------------------------------------------------------------------------ editör değerlendirmesi

def _eval_out(e: Any) -> dict[str, Any]:
    axes = [x for x in (e.mission, e.publishing, e.commercial) if x is not None]
    return {"id": e.id, "round": e.round, "evaluator": e.evaluator, "evaluatorName": e.evaluator_name or e.evaluator,
            "contentScore": e.content_score, "mission": e.mission, "publishing": e.publishing, "commercial": e.commercial,
            "total": round(sum(axes) / 3) if len(axes) == 3 else None,
            "recommendation": e.recommendation, "recommendationLabel": RECOMMENDATIONS.get(e.recommendation or ""),
            "topic": e.topic, "genre": e.genre, "ageGroup": e.age_group, "overlapNote": e.overlap_note,
            "redline": e.redline, "redlineLabel": REDLINES.get(e.redline or ""), "redlineNote": e.redline_note,
            "report": e.report, "submitted": e.submitted_at is not None, "submittedAt": _iso(e.submitted_at),
            "updatedBy": e.updated_by, "updatedAt": _iso(e.updated_at)}


def assign(engine: sa.engine.Engine, tenant: str, user: str, display: str, app_id: str, evaluator: str,
           evaluator_name: Optional[str], *, manager: bool) -> dict[str, Any]:
    who = _user(evaluator, "Değerlendirecek editör")
    if who != user and not manager:
        raise ApplicationError("Başvuruyu başkasına atamak «başvuru yönetimi» yetkisi ister; kendinize alabilirsiniz.", 403)
    with engine.begin() as c:
        r = _row(c, tenant, app_id)
        if r.status not in ("yeni", "degerlendirmede"):
            raise ApplicationError(f"«{STATUSES[r.status]}» durumundaki başvurunun editörü değiştirilmez.", 409)
        if r.evaluator and r.evaluator != user and not manager:
            raise ApplicationError("Başvuru başka bir editörde; yeniden atamayı yönetici yapar.", 403)
        c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(
            evaluator=who, evaluator_name=_line(evaluator_name, 200) or who, status="degerlendirmede",
            updated_by=user, updated_at=_now()))
        _log(c, r.id, user, display, "atandi", {"editor": _line(evaluator_name, 200) or who})
        return _out(_row(c, tenant, app_id))


def save_evaluation(engine: sa.engine.Engine, tenant: str, user: str, display: str, app_id: str, body: dict[str, Any], *,
                    manager: bool) -> dict[str, Any]:
    vals = {
        "content_score": _score(body.get("contentScore"), "İçerik skoru"),
        "mission": _score(body.get("mission"), "Misyon değeri"),
        "publishing": _score(body.get("publishing"), "Yayıncılık değeri"),
        "commercial": _score(body.get("commercial"), "Ticari değer"),
        "recommendation": _choice(body.get("recommendation"), RECOMMENDATIONS, "Öneri"),
        "topic": _line(body.get("topic"), 200), "genre": _line(body.get("genre"), 120),
        "age_group": _line(body.get("ageGroup"), 120), "overlap_note": _para(body.get("overlapNote"), 8000),
        "redline": _choice(body.get("redline"), REDLINES, "Yayın ilkeleri kontrolü"),
        "redline_note": _para(body.get("redlineNote"), 4000), "report": _para(body.get("report"), 40000),
    }
    submit = bool(body.get("submit"))
    if submit:
        missing = [what for col, what in (("content_score", "içerik skoru"), ("mission", "misyon değeri"),
                                          ("publishing", "yayıncılık değeri"), ("commercial", "ticari değer"),
                                          ("recommendation", "öneri"), ("redline", "yayın ilkeleri kontrolü"),
                                          ("report", "rapor metni")) if vals[col] in (None, "")]
        if missing:
            raise ApplicationError("Raporu tamamlamak için eksik: " + ", ".join(missing) + ".")
        if vals["redline"] != "temiz" and not vals["redline_note"]:
            raise ApplicationError("Yayın ilkeleri kontrolünde sorun işaretlendiyse açıklaması yazılmalı.")
    with engine.begin() as c:
        r = _row(c, tenant, app_id)
        if r.status != "degerlendirmede":
            raise ApplicationError("Editör raporu yalnız «editör değerlendirmesinde» olan başvuruya yazılır.", 409)
        if r.evaluator != user and not manager:
            raise ApplicationError("Bu başvurunun raporunu atanan editör yazar.", 403)
        e = c.execute(sa.select(EVALS).where(EVALS.c.app_id == r.id, EVALS.c.round == r.round)).first()
        stamp = {"updated_by": user, "updated_at": _now()}
        if submit and (e is None or e.submitted_at is None):
            stamp["submitted_at"] = _now()
        if e is None:
            c.execute(EVALS.insert().values(id=_new(), app_id=r.id, round=r.round, evaluator=r.evaluator or user,
                                            evaluator_name=r.evaluator_name or display, **vals, **stamp))
        else:
            if e.submitted_at is not None:
                # Tamamlanmış rapor düzeltilebilir ama eksik bırakılamaz.
                for col in ("content_score", "mission", "publishing", "commercial", "recommendation", "redline", "report"):
                    if vals[col] in (None, ""):
                        raise ApplicationError("Tamamlanmış raporda puan, öneri, ilke kontrolü ve rapor metni boşaltılamaz.")
            c.execute(sa.update(EVALS).where(EVALS.c.id == e.id).values(**vals, **stamp))
        if submit and (e is None or e.submitted_at is None):
            _log(c, r.id, user, display, "rapor_tamamlandi", {"oneri": RECOMMENDATIONS.get(vals["recommendation"] or "")})
        e = c.execute(sa.select(EVALS).where(EVALS.c.app_id == r.id, EVALS.c.round == r.round)).first()
        return _eval_out(e)


EDITOR_ACTIONS = {"kurula": "kurul_bekliyor", "revizyon": "revizyon", "red": "red", "geri_cekildi": "geri_cekildi"}


def editor_decision(engine: sa.engine.Engine, tenant: str, user: str, display: str, app_id: str, action: str,
                    note: Any, *, manager: bool) -> dict[str, Any]:
    """Aşama 1 kararı: kurula çıkar, yazardan revizyon iste, reddet (arşiv), ya da yazar geri çekti."""
    if action not in EDITOR_ACTIONS:
        raise ApplicationError("Karar geçerli değil.")
    text = _para(note, 8000)
    with engine.begin() as c:
        r = _row(c, tenant, app_id)
        if r.evaluator != user and not manager:
            raise ApplicationError("Bu kararı atanan editör ya da başvuru yöneticisi verir.", 403)
        if action == "geri_cekildi":
            if r.status not in ("yeni", "degerlendirmede", "revizyon", "kurul_bekliyor"):
                raise ApplicationError("Kurul gündemindeki başvuru önce gündemden çıkarılmalı.", 409)
            if not text:
                raise ApplicationError("Geri çekilme notu yazılmalı (yazar ne zaman, nasıl bildirdi).")
        else:
            if r.status != "degerlendirmede":
                raise ApplicationError("Bu karar yalnız «editör değerlendirmesinde» olan başvuruya verilir.", 409)
            e = c.execute(sa.select(EVALS).where(EVALS.c.app_id == r.id, EVALS.c.round == r.round)).first()
            if e is None or e.submitted_at is None:
                raise ApplicationError("Önce editör raporu tamamlanmalı.", 409)
            if action in ("red", "revizyon") and not text:
                raise ApplicationError("Red ve revizyon kararında gerekçe yazılmalı; yazara gidecek yazının temeli budur.")
        new = EDITOR_ACTIONS[action]
        closing = new in ARCHIVE
        c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(
            status=new, decision_note=text, decided_by=user if closing else None, decided_at=_now() if closing else None,
            updated_by=user, updated_at=_now()))
        _log(c, r.id, user, display, f"karar_{action}", {"not": text})
        return _out(_row(c, tenant, app_id))


def reopen(engine: sa.engine.Engine, tenant: str, user: str, display: str, app_id: str, note: Any, *,
           manager: bool) -> dict[str, Any]:
    """Revize dosya geldi ya da arşivdeki başvuru yeniden ele alınıyor: yeni tur, değerlendirmeye döner."""
    text = _para(note, 4000)
    if not text:
        raise ApplicationError("Yeniden açma gerekçesi yazılmalı.")
    with engine.begin() as c:
        r = _row(c, tenant, app_id)
        if r.status not in ("revizyon",) + ARCHIVE:
            raise ApplicationError("Yalnız revizyon bekleyen ya da arşivdeki başvuru yeniden açılır.", 409)
        if r.evaluator != user and not manager:
            raise ApplicationError("Yeniden açmayı atanan editör ya da başvuru yöneticisi yapar.", 403)
        c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(
            status="degerlendirmede" if r.evaluator else "yeni", round=r.round + 1, decision_note=None, decided_by=None,
            decided_at=None, updated_by=user, updated_at=_now()))
        _log(c, r.id, user, display, "yeniden_acildi", {"not": text, "tur": r.round + 1})
        return _out(_row(c, tenant, app_id))


def link_crm_project(engine: sa.engine.Engine, tenant: str, user: str, display: str, app_id: str, project_id: Any,
                     project_name: Optional[str]) -> dict[str, Any]:
    pid = _guid(project_id, "CRM proje kimliği")
    with engine.begin() as c:
        r = _row(c, tenant, app_id)
        if r.status != "kabul":
            raise ApplicationError("CRM proje kartı yalnız kabul edilen başvuruya bağlanır.", 409)
        c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(
            crm_project_id=pid, crm_project_name=_line(project_name, 300) if pid else None, updated_by=user, updated_at=_now()))
        _log(c, r.id, user, display, "crm_baglandi" if pid else "crm_bag_kaldirildi", {"proje": project_name} if pid else None)
        return _out(_row(c, tenant, app_id))


# ------------------------------------------------------------------------------------------------ yazışma

def _letter_out(x: Any) -> dict[str, Any]:
    return {"id": x.id, "kind": x.kind, "kindLabel": LETTER_KINDS.get(x.kind, x.kind), "state": x.state,
            "stateLabel": LETTER_STATES.get(x.state, x.state), "subject": x.subject, "body": x.body,
            "createdBy": x.created_by, "createdAt": _iso(x.created_at), "updatedAt": _iso(x.updated_at),
            "approvedBy": x.approved_by, "approvedName": x.approved_name, "approvedAt": _iso(x.approved_at),
            "sentOn": _iso(x.sent_on), "sentChannel": x.sent_channel,
            "sentChannelLabel": SEND_CHANNELS.get(x.sent_channel or "")}


def letter_template(kind: str, r: Any, signer: str, note: Optional[str], extra: Optional[dict[str, Any]] = None) -> tuple[str, str]:
    """Yazının taslağı. Kurumun sesi: kısa, saygılı, gerekçeyi yazarın anlayacağı dille verir. Editör düzeltir,
    onaylayan kişi kaydedilir; portal yazıyı kendiliğinden göndermez."""
    who = r.author_name
    title = r.title
    gerekce = (note or "").strip()
    if kind == "kabul":
        subject = f"«{title}» — yayın kurulu kararı"
        lines = [f"Sayın {who},", "",
                 f"«{title}» başlıklı çalışmanız editörlerimiz ve yayın kurulumuzca değerlendirildi. Çalışmanızı yayın "
                 "programımıza almaktan memnuniyet duyduğumuzu bildiririz.", ""]
        if gerekce:
            lines += [gerekce, ""]
        if extra and extra.get("publishOn"):
            lines += [f"Kurulumuzun öngördüğü yayın dönemi: {extra['publishOn']}.", ""]
        lines += ["Sözleşme ve yayın sürecinin sonraki adımları için editörümüz sizinle ayrıca iletişime geçecektir.", ""]
    elif kind == "revizyon":
        subject = f"«{title}» — değerlendirme ve revizyon talebi"
        lines = [f"Sayın {who},", "",
                 f"«{title}» başlıklı çalışmanızı dikkatle okuduk. Çalışmanızın yayın programımız için değerlendirilmeye "
                 "devam edebilmesi için aşağıdaki noktalar üzerinde yeniden çalışmanızı rica ediyoruz:", "",
                 gerekce or "(Revizyon beklenen noktalar)", "",
                 "Revize ettiğiniz dosyayı bize ulaştırdığınızda değerlendirmemizi yeniden yapacağız.", ""]
    else:
        subject = f"«{title}» — değerlendirme sonucu"
        lines = [f"Sayın {who},", "",
                 f"«{title}» başlıklı çalışmanızı yayınevimize gönderdiğiniz için teşekkür ederiz. Dosyanız "
                 "editörlerimizce dikkatle değerlendirildi; çalışmanızı yayın programımıza alamayacağımızı üzülerek "
                 "bildiririz.", ""]
        if gerekce:
            lines += [gerekce, ""]
        lines += ["İlginiz için yeniden teşekkür eder, çalışmalarınızda başarılar dileriz.", ""]
    lines += ["Saygılarımızla,", signer, "Timaş Yayınları"]
    return subject, "\n".join(lines)


def _letter_kind_for(status: str) -> Optional[str]:
    return {"kabul": "kabul", "red": "red", "revizyon": "revizyon"}.get(status)


def create_letter(engine: sa.engine.Engine, tenant: str, user: str, display: str, app_id: str,
                  kind: Optional[str] = None, *, if_missing: bool = False) -> dict[str, Any]:
    """Kararın yazısını taslak olarak hazırlar. `if_missing`: aynı türde taslak zaten varsa onu döner (karar
    yeniden kaydedilince ikinci taslak açılmaz)."""
    with engine.begin() as c:
        r = _row(c, tenant, app_id)
        want = kind or _letter_kind_for(r.status)
        if want not in LETTER_KINDS:
            raise ApplicationError("Yazı yalnız kabul, red ya da revizyon kararından sonra hazırlanır.", 409)
        if _letter_kind_for(r.status) != want:
            raise ApplicationError(f"Başvurunun durumu «{STATUSES[r.status]}»; {LETTER_KINDS[want].lower()} hazırlanmaz.", 409)
        if if_missing:
            old = c.execute(sa.select(LETTERS).where(LETTERS.c.app_id == r.id, LETTERS.c.kind == want,
                                                     LETTERS.c.state == "taslak")).first()
            if old is not None:
                return _letter_out(old)
        extra = None
        if want == "kabul":
            a = c.execute(sa.select(AGENDA).where(AGENDA.c.app_id == r.id, AGENDA.c.decision == "kabul")
                          .order_by(AGENDA.c.decided_at.desc())).first()
            if a is not None and a.publish_on:
                extra = {"publishOn": a.publish_on.strftime("%d.%m.%Y")}
        subject, body = letter_template(want, r, display or user, r.decision_note, extra)
        lid = _new()
        c.execute(LETTERS.insert().values(id=lid, app_id=r.id, kind=want, state="taslak", subject=subject, body=body,
                                          created_by=user, created_at=_now()))
        _log(c, r.id, user, display, "yazi_hazirlandi", {"tur": LETTER_KINDS[want]})
        return _letter_out(c.execute(sa.select(LETTERS).where(LETTERS.c.id == lid)).first())


def _letter(c: Any, tenant: str, letter_id: str) -> tuple[Any, Any]:
    x = c.execute(sa.select(LETTERS).where(LETTERS.c.id == str(letter_id or ""))).first()
    if x is None:
        raise ApplicationError("Yazı bulunamadı.", 404)
    return x, _row(c, tenant, x.app_id)


def update_letter(engine: sa.engine.Engine, tenant: str, user: str, letter_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        x, _ = _letter(c, tenant, letter_id)
        if x.state != "taslak":
            raise ApplicationError("Onaylanmış yazı değiştirilmez; onayı geri alın.", 409)
        vals = {}
        if "subject" in body:
            vals["subject"] = _line(body.get("subject"), 300)
            if not vals["subject"]:
                raise ApplicationError("Konu boş olamaz.")
        if "body" in body:
            vals["body"] = _para(body.get("body"), 20000)
            if not vals["body"]:
                raise ApplicationError("Yazı metni boş olamaz.")
        if vals:
            c.execute(sa.update(LETTERS).where(LETTERS.c.id == x.id).values(updated_by=user, updated_at=_now(), **vals))
        return _letter_out(c.execute(sa.select(LETTERS).where(LETTERS.c.id == x.id)).first())


def letter_state(engine: sa.engine.Engine, tenant: str, user: str, display: str, letter_id: str, action: str,
                 body: dict[str, Any]) -> dict[str, Any]:
    """approve (insan onayı) · unapprove · sent (gönderildi: tarih + kanal) · delete (yalnız taslak)."""
    with engine.begin() as c:
        x, r = _letter(c, tenant, letter_id)
        if action == "approve":
            if x.state != "taslak":
                raise ApplicationError("Yazı zaten onaylı.", 409)
            c.execute(sa.update(LETTERS).where(LETTERS.c.id == x.id).values(
                state="onaylandi", approved_by=user, approved_name=display or user, approved_at=_now()))
            _log(c, r.id, user, display, "yazi_onaylandi", {"tur": LETTER_KINDS.get(x.kind)})
        elif action == "unapprove":
            if x.state != "onaylandi":
                raise ApplicationError("Yalnız onaylı ve gönderilmemiş yazının onayı geri alınır.", 409)
            c.execute(sa.update(LETTERS).where(LETTERS.c.id == x.id).values(state="taslak", approved_by=None,
                                                                            approved_name=None, approved_at=None))
            _log(c, r.id, user, display, "yazi_onayi_geri", {"tur": LETTER_KINDS.get(x.kind)})
        elif action == "sent":
            if x.state != "onaylandi":
                raise ApplicationError("Yalnız onaylanmış yazı gönderildi olarak işaretlenir.", 409)
            on = _day(body.get("on"), "Gönderim tarihi") or _now().date()
            if on > _now().date():
                raise ApplicationError("Gönderim tarihi ileri bir gün olamaz.")
            ch = _choice(body.get("channel") or "eposta", SEND_CHANNELS, "Gönderim kanalı")
            c.execute(sa.update(LETTERS).where(LETTERS.c.id == x.id).values(state="gonderildi", sent_on=on, sent_channel=ch,
                                                                            sent_by=user))
            _log(c, r.id, user, display, "yazi_gonderildi", {"tur": LETTER_KINDS.get(x.kind), "kanal": SEND_CHANNELS[ch],
                                                             "tarih": on.isoformat()})
        elif action == "delete":
            if x.state != "taslak":
                raise ApplicationError("Yalnız taslak yazı silinir.", 409)
            c.execute(LETTERS.delete().where(LETTERS.c.id == x.id))
            _log(c, r.id, user, display, "yazi_silindi", {"tur": LETTER_KINDS.get(x.kind)})
            return {"id": x.id, "deleted": True}
        else:
            raise ApplicationError("İşlem geçerli değil.")
        return _letter_out(c.execute(sa.select(LETTERS).where(LETTERS.c.id == x.id)).first())


# ------------------------------------------------------------------------------------------- kurul oturumu

def _members(raw: Optional[str]) -> list[dict[str, str]]:
    try:
        v = json.loads(raw or "[]")
    except ValueError:
        return []
    return [m for m in v if isinstance(m, dict) and m.get("username")] if isinstance(v, list) else []


def _clean_members(items: Any, chair: str, chair_name: str) -> list[dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for m in items if isinstance(items, list) else []:
        u = _user(m.get("username") if isinstance(m, dict) else m, "Kurul üyesi")
        out[u] = {"username": u, "display": _line(m.get("display") if isinstance(m, dict) else None, 200) or u}
    out.setdefault(chair, {"username": chair, "display": chair_name or chair})
    return sorted(out.values(), key=lambda m: (m["username"] != chair, m["display"].lower()))


def _session_row(c: Any, tenant: str, sid: str) -> Any:
    s = c.execute(sa.select(SESSIONS).where(SESSIONS.c.tenant_id == tenant, SESSIONS.c.id == str(sid or ""))).first()
    if s is None:
        raise ApplicationError("Kurul oturumu bulunamadı.", 404)
    return s


def _can_run(s: Any, user: str, manager: bool) -> bool:
    return manager or s.chair == user


def create_session(engine: sa.engine.Engine, tenant: str, user: str, display: str, body: dict[str, Any]) -> dict[str, Any]:
    on = _day(body.get("date"), "Oturum tarihi")
    if on is None:
        raise ApplicationError("Oturum tarihi seçilmeli.")
    at = str(body.get("time") or "").strip() or None
    if at and not _TIME.match(at):
        raise ApplicationError("Saat SS:DD biçiminde olmalı.")
    chair = _user(body.get("chair") or user, "Kurul başkanı")
    chair_name = _line(body.get("chairName"), 200) or (display if chair == user else chair)
    members = _clean_members(body.get("members"), chair, chair_name)
    title = _line(body.get("title"), 200) or f"Yayın kurulu · {on.strftime('%d.%m.%Y')}"
    sid = _new()
    with engine.begin() as c:
        c.execute(SESSIONS.insert().values(id=sid, tenant_id=tenant, title=title, meet_on=on, meet_at=at,
                                           place=_line(body.get("place"), 200), chair=chair, chair_name=chair_name,
                                           members_json=json.dumps(members, ensure_ascii=False), note=_para(body.get("note"), 4000),
                                           state="planli", created_by=user, created_at=_now()))
        s = _session_row(c, tenant, sid)
    return _session_head(s)


def update_session(engine: sa.engine.Engine, tenant: str, user: str, display: str, sid: str, body: dict[str, Any], *,
                   manager: bool) -> tuple[dict[str, Any], list[str]]:
    with engine.begin() as c:
        s = _session_row(c, tenant, sid)
        if not _can_run(s, user, manager):
            raise ApplicationError("Oturumu başkan ya da yayın kurulu yöneticisi düzenler.", 403)
        if s.state != "planli":
            raise ApplicationError("Kapanmış oturum düzenlenmez.", 409)
        vals: dict[str, Any] = {}
        if "date" in body:
            vals["meet_on"] = _day(body.get("date"), "Oturum tarihi")
            if vals["meet_on"] is None:
                raise ApplicationError("Oturum tarihi boş olamaz.")
        if "time" in body:
            at = str(body.get("time") or "").strip() or None
            if at and not _TIME.match(at):
                raise ApplicationError("Saat SS:DD biçiminde olmalı.")
            vals["meet_at"] = at
        if "title" in body:
            vals["title"] = _line(body.get("title"), 200) or s.title
        if "place" in body:
            vals["place"] = _line(body.get("place"), 200)
        if "note" in body:
            vals["note"] = _para(body.get("note"), 4000)
        chair, chair_name = s.chair, s.chair_name
        if "chair" in body:
            chair = _user(body.get("chair"), "Kurul başkanı")
            chair_name = _line(body.get("chairName"), 200) or chair
            vals.update(chair=chair, chair_name=chair_name)
        if "members" in body or "chair" in body:
            members = _clean_members(body.get("members") if "members" in body else _members(s.members_json), chair, chair_name)
            voted = {v.member for v in c.execute(sa.select(VOTES.c.member).where(VOTES.c.session_id == s.id))}
            gone = voted - {m["username"] for m in members}
            if gone:
                raise ApplicationError("Oy vermiş üye oturumdan çıkarılamaz: " + ", ".join(sorted(gone)) + ".", 409)
            vals["members_json"] = json.dumps(members, ensure_ascii=False)
        diff = sorted(k for k, v in vals.items() if getattr(s, k) != v)
        if diff:
            c.execute(sa.update(SESSIONS).where(SESSIONS.c.id == s.id).values(updated_by=user, updated_at=_now(), **vals))
        return _session_head(_session_row(c, tenant, sid)), diff


def _session_head(s: Any, counts: Optional[dict[str, int]] = None) -> dict[str, Any]:
    members = _members(s.members_json)
    return {"id": s.id, "title": s.title, "date": _iso(s.meet_on), "time": s.meet_at, "place": s.place, "chair": s.chair,
            "chairName": s.chair_name or s.chair, "members": members, "note": s.note, "state": s.state,
            "stateLabel": {"planli": "Hazırlanıyor", "kapandi": "Kapandı"}.get(s.state, s.state),
            "createdBy": s.created_by, "createdAt": _iso(s.created_at), "closedAt": _iso(s.closed_at),
            **({"agenda": counts} if counts is not None else {})}


def sessions(engine: sa.engine.Engine, tenant: str, user: str, *, state: str = "") -> dict[str, Any]:
    with engine.connect() as c:
        cond = [SESSIONS.c.tenant_id == tenant]
        if state:
            if state not in ("planli", "kapandi"):
                raise ApplicationError("Oturum durumu geçerli değil.")
            cond.append(SESSIONS.c.state == state)
        rows = c.execute(sa.select(SESSIONS).where(*cond).order_by(SESSIONS.c.meet_on.desc(), SESSIONS.c.created_at.desc())).all()
        ids = [s.id for s in rows]
        agenda: dict[str, dict[str, int]] = {i: {"items": 0, "decided": 0} for i in ids}
        if ids:
            for a in c.execute(sa.select(AGENDA.c.session_id, AGENDA.c.decision).where(AGENDA.c.session_id.in_(ids))):
                agenda[a.session_id]["items"] += 1
                agenda[a.session_id]["decided"] += 1 if a.decision else 0
        mine_votes: dict[str, int] = {}
        if ids:
            for sid, n in c.execute(sa.select(VOTES.c.session_id, sa.func.count()).where(VOTES.c.session_id.in_(ids), VOTES.c.member == user)
                                    .group_by(VOTES.c.session_id)):
                mine_votes[sid] = int(n)
    out = []
    for s in rows:
        h = _session_head(s, agenda[s.id])
        h["isMember"] = any(m["username"] == user for m in h["members"])
        h["myVotes"] = mine_votes.get(s.id, 0)
        out.append(h)
    return {"items": out}


def tally(votes: Iterable[Any], member_count: int, *, accept: int = DEFAULT_ACCEPT, revise: int = DEFAULT_REVISE) -> dict[str, Any]:
    """Oy dağılımı, eksen ortalamaları, toplam karar skoru ve iki öneri (oy çoğunluğu, skor eşiği)."""
    vs = list(votes)
    counts = {k: 0 for k in VOTES_LABEL}
    for v in vs:
        counts[v.vote] = counts.get(v.vote, 0) + 1
    axes = {}
    for ax in ("mission", "publishing", "commercial"):
        xs = [getattr(v, ax) for v in vs if getattr(v, ax) is not None]
        axes[ax] = round(sum(xs) / len(xs), 1) if xs else None
    total = round(sum(axes.values()) / 3, 1) if all(x is not None for x in axes.values()) else None
    ranked = sorted(((counts[k], k) for k in ("kabul", "revizyon", "red")), reverse=True)
    majority = ranked[0][1] if ranked[0][0] > 0 and ranked[0][0] > ranked[1][0] else None
    by_score = None if total is None else ("kabul" if total >= accept else "revizyon" if total >= revise else "red")
    return {"voted": len(vs), "members": member_count, "counts": counts, "axes": axes, "total": total,
            "majority": majority, "majorityLabel": VOTES_LABEL.get(majority or ""),
            "tie": ranked[0][0] > 0 and ranked[0][0] == ranked[1][0], "byScore": by_score,
            "byScoreLabel": RECOMMENDATIONS.get(by_score or ""), "thresholds": {"accept": accept, "revise": revise}}


def _vote_out(v: Any) -> dict[str, Any]:
    return {"member": v.member, "memberName": v.member_name or v.member, "mission": v.mission, "publishing": v.publishing,
            "commercial": v.commercial, "vote": v.vote, "voteLabel": VOTES_LABEL.get(v.vote, v.vote), "note": v.note,
            "updatedAt": _iso(v.updated_at)}


def session_detail(engine: sa.engine.Engine, tenant: str, user: str, sid: str, *, manager: bool, can_see_names: bool,
                   accept: int = DEFAULT_ACCEPT, revise: int = DEFAULT_REVISE) -> dict[str, Any]:
    with engine.connect() as c:
        s = _session_row(c, tenant, sid)
        head = _session_head(s)
        members = head["members"]
        is_member = any(m["username"] == user for m in members)
        runs = _can_run(s, user, manager)
        names = runs or can_see_names
        agenda = c.execute(sa.select(AGENDA, APPS.c.no, APPS.c.title, APPS.c.author_name, APPS.c.category_name,
                                     APPS.c.status, APPS.c.evaluator_name, APPS.c.page_estimate, APPS.c.round)
                           .join(APPS, APPS.c.id == AGENDA.c.app_id)
                           .where(AGENDA.c.session_id == s.id).order_by(AGENDA.c.position)).all()
        app_ids = [a.app_id for a in agenda]
        votes: dict[str, list[Any]] = {i: [] for i in app_ids}
        if app_ids:
            for v in c.execute(sa.select(VOTES).where(VOTES.c.session_id == s.id)):
                votes.setdefault(v.app_id, []).append(v)
        evals = {}
        if app_ids:
            for e in c.execute(sa.select(EVALS).where(EVALS.c.app_id.in_(app_ids))):
                evals[(e.app_id, e.round)] = e
        reports = {}
        if app_ids:
            for rep in c.execute(sa.select(REPORTS.c.app_id, REPORTS.c.status, REPORTS.c.created_at)
                                 .where(REPORTS.c.app_id.in_(app_ids)).order_by(REPORTS.c.created_at)):
                reports[rep.app_id] = rep.status
    items = []
    for a in agenda:
        vs = votes.get(a.app_id, [])
        mine = next((v for v in vs if v.member == user), None)
        t = tally(vs, len(members), accept=accept, revise=revise)
        # Oy gizliliği: üye kendi oyunu vermeden dağılımı görmez; adıyla oylar yalnız yöneten/yetkili kişiye.
        see_tally = runs or can_see_names or bool(a.decision) or mine is not None or s.state == "kapandi"
        e = evals.get((a.app_id, a.round))
        items.append({
            "appId": a.app_id, "no": a.no, "title": a.title, "authorName": a.author_name, "categoryName": a.category_name,
            "evaluatorName": a.evaluator_name, "pageEstimate": a.page_estimate, "appStatus": a.status,
            "position": a.position, "decision": a.decision, "decisionLabel": DECISIONS.get(a.decision or ""),
            "decisionNote": a.decision_note, "printRun": a.print_run,
            "price": float(a.price) if a.price is not None else None,
            "royalty": float(a.royalty) if a.royalty is not None else None, "publishOn": _iso(a.publish_on),
            "decidedByName": a.decided_name, "decidedAt": _iso(a.decided_at),
            "editor": {"contentScore": e.content_score, "mission": e.mission, "publishing": e.publishing,
                       "commercial": e.commercial, "recommendation": e.recommendation,
                       "recommendationLabel": RECOMMENDATIONS.get(e.recommendation or ""),
                       "redline": e.redline, "redlineLabel": REDLINES.get(e.redline or "")} if e is not None and e.submitted_at else None,
            "report": reports.get(a.app_id),
            "myVote": _vote_out(mine) if mine else None,
            "tally": t if see_tally else {"voted": t["voted"], "members": t["members"], "hidden": True},
            "votes": [_vote_out(v) for v in vs] if names else None,
        })
    return {**head, "isMember": is_member, "canRun": runs, "canSeeNames": names, "items": items,
            "thresholds": {"accept": accept, "revise": revise}}


def add_to_agenda(engine: sa.engine.Engine, tenant: str, user: str, display: str, sid: str, app_id: str, *,
                  manager: bool) -> dict[str, Any]:
    with engine.begin() as c:
        s = _session_row(c, tenant, sid)
        if not _can_run(s, user, manager):
            raise ApplicationError("Gündemi başkan ya da yayın kurulu yöneticisi hazırlar.", 403)
        if s.state != "planli":
            raise ApplicationError("Kapanmış oturumun gündemi değişmez.", 409)
        r = _row(c, tenant, app_id)
        if r.status != "kurul_bekliyor":
            raise ApplicationError(f"Gündeme yalnız «Kurula çıkacak» başvuru eklenir (bu başvuru: {STATUSES[r.status]}).", 409)
        pos = (c.execute(sa.select(sa.func.max(AGENDA.c.position)).where(AGENDA.c.session_id == s.id)).scalar() or 0) + 1
        if c.execute(sa.select(AGENDA.c.id).where(AGENDA.c.session_id == s.id, AGENDA.c.app_id == r.id)).first():
            raise ApplicationError("Başvuru bu oturumun gündeminde zaten var.", 409)
        c.execute(AGENDA.insert().values(id=_new(), session_id=s.id, app_id=r.id, position=pos, added_by=user, added_at=_now()))
        c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(status="kurulda", updated_by=user, updated_at=_now()))
        _log(c, r.id, user, display, "gundeme_alindi", {"oturum": s.title})
    return {"ok": True, "title": r.title, "session": s.title}


def remove_from_agenda(engine: sa.engine.Engine, tenant: str, user: str, display: str, sid: str, app_id: str, *,
                       manager: bool) -> dict[str, Any]:
    with engine.begin() as c:
        s = _session_row(c, tenant, sid)
        if not _can_run(s, user, manager):
            raise ApplicationError("Gündemi başkan ya da yayın kurulu yöneticisi hazırlar.", 403)
        if s.state != "planli":
            raise ApplicationError("Kapanmış oturumun gündemi değişmez.", 409)
        a = c.execute(sa.select(AGENDA).where(AGENDA.c.session_id == s.id, AGENDA.c.app_id == str(app_id))).first()
        if a is None:
            raise ApplicationError("Başvuru bu oturumun gündeminde değil.", 404)
        if a.decision:
            raise ApplicationError("Kararı kaydedilmiş başvuru gündemden çıkarılmaz; önce kararı geri alın.", 409)
        if c.execute(sa.select(VOTES.c.id).where(VOTES.c.session_id == s.id, VOTES.c.app_id == a.app_id)).first():
            raise ApplicationError("Oy verilmiş başvuru gündemden çıkarılmaz.", 409)
        c.execute(AGENDA.delete().where(AGENDA.c.id == a.id))
        r = _row(c, tenant, a.app_id)
        c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(status="kurul_bekliyor", updated_by=user, updated_at=_now()))
        _log(c, r.id, user, display, "gundemden_cikti", {"oturum": s.title})
    return {"ok": True, "title": r.title}


def vote(engine: sa.engine.Engine, tenant: str, user: str, display: str, sid: str, app_id: str,
         body: dict[str, Any]) -> dict[str, Any]:
    choice = _choice(body.get("vote"), VOTES_LABEL, "Oy", required=True)
    scores = {ax: _score(body.get(key), what) for ax, key, what in (("mission", "mission", "Misyon değeri"),
                                                                     ("publishing", "publishing", "Yayıncılık değeri"),
                                                                     ("commercial", "commercial", "Ticari değer"))}
    if choice != "cekimser" and any(v is None for v in scores.values()):
        raise ApplicationError("Üç eksenin puanı girilmeli (çekimser oyda puan isteğe bağlı).")
    note = _para(body.get("note"), 4000)
    if choice in ("red", "revizyon") and not note:
        raise ApplicationError("Red ve revizyon oyunda kısa bir gerekçe yazılmalı.")
    with engine.begin() as c:
        s = _session_row(c, tenant, sid)
        if s.state != "planli":
            raise ApplicationError("Oturum kapandı; oy verilmez.", 409)
        if not any(m["username"] == user for m in _members(s.members_json)):
            raise ApplicationError("Bu oturumun üyesi değilsiniz; oy veremezsiniz.", 403)
        a = c.execute(sa.select(AGENDA).where(AGENDA.c.session_id == s.id, AGENDA.c.app_id == str(app_id))).first()
        if a is None:
            raise ApplicationError("Başvuru bu oturumun gündeminde değil.", 404)
        if a.decision:
            raise ApplicationError("Bu başvurunun kararı kaydedildi; oy değişmez.", 409)
        old = c.execute(sa.select(VOTES).where(VOTES.c.session_id == s.id, VOTES.c.app_id == a.app_id, VOTES.c.member == user)).first()
        vals = dict(vote=choice, note=note, member_name=display or user, updated_at=_now(), **scores)
        if old is None:
            c.execute(VOTES.insert().values(id=_new(), session_id=s.id, app_id=a.app_id, member=user, **vals))
        else:
            c.execute(sa.update(VOTES).where(VOTES.c.id == old.id).values(**vals))
        _log(c, a.app_id, user, display, "oy", {"oturum": s.title})
        v = c.execute(sa.select(VOTES).where(VOTES.c.session_id == s.id, VOTES.c.app_id == a.app_id, VOTES.c.member == user)).first()
    return _vote_out(v)


BOARD_TO_STATUS = {"kabul": "kabul", "revizyon": "revizyon", "red": "red", "ertele": "kurul_bekliyor"}


def decide(engine: sa.engine.Engine, tenant: str, user: str, display: str, sid: str, app_id: str, body: dict[str, Any], *,
           manager: bool) -> dict[str, Any]:
    """Kurul kararı: başvurunun durumu kararla birlikte değişir. `decision` boşsa karar geri alınır."""
    choice = str(body.get("decision") or "").strip()
    undo = choice == ""
    if not undo and choice not in BOARD_TO_STATUS:
        raise ApplicationError("Karar geçerli değil.")
    note = _para(body.get("note"), 8000)
    if choice in ("red", "revizyon") and not note:
        raise ApplicationError("Red ve revizyon kararında gerekçe yazılmalı; yazara gidecek yazının temeli budur.")
    extra = {
        "print_run": _int(body.get("printRun"), "İlk baskı adedi", 1, 10_000_000),
        "price": _money(body.get("price"), "Fiyat önerisi", 1_000_000),
        "royalty": _money(body.get("royalty"), "Telif oranı", 100),
        "publish_on": _day(body.get("publishOn"), "Önerilen yayın tarihi"),
    }
    with engine.begin() as c:
        s = _session_row(c, tenant, sid)
        if not _can_run(s, user, manager):
            raise ApplicationError("Kurul kararını başkan ya da yayın kurulu yöneticisi kaydeder.", 403)
        if s.state != "planli":
            raise ApplicationError("Kapanmış oturumun kararı değişmez.", 409)
        a = c.execute(sa.select(AGENDA).where(AGENDA.c.session_id == s.id, AGENDA.c.app_id == str(app_id))).first()
        if a is None:
            raise ApplicationError("Başvuru bu oturumun gündeminde değil.", 404)
        r = _row(c, tenant, a.app_id)
        if undo:
            if not a.decision:
                raise ApplicationError("Geri alınacak karar yok.", 409)
            if r.status != BOARD_TO_STATUS[a.decision] and not (a.decision == "ertele" and r.status == "kurul_bekliyor"):
                raise ApplicationError("Başvuru karardan sonra ilerlemiş; karar burada geri alınmaz.", 409)
            sent = c.execute(sa.select(LETTERS.c.id).where(LETTERS.c.app_id == r.id, LETTERS.c.state != "taslak",
                                                           LETTERS.c.created_at >= a.decided_at)).first()
            if sent:
                raise ApplicationError("Kararın yazısı onaylanmış; önce yazının onayını geri alın.", 409)
            # Kararla birlikte hazırlanan taslak yazı da geri alınır (onaylı/gönderilmiş yazı varsa yukarıda durdu).
            c.execute(LETTERS.delete().where(LETTERS.c.app_id == r.id, LETTERS.c.state == "taslak",
                                             LETTERS.c.created_at >= a.decided_at))
            c.execute(sa.update(AGENDA).where(AGENDA.c.id == a.id).values(
                decision=None, decision_note=None, print_run=None, price=None, royalty=None, publish_on=None,
                decided_by=None, decided_name=None, decided_at=None))
            c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(status="kurulda", decision_note=None, decided_by=None,
                                                                      decided_at=None, updated_by=user, updated_at=_now()))
            _log(c, r.id, user, display, "kurul_karari_geri", {"oturum": s.title})
            return {"ok": True, "decision": None}
        if a.decision and a.decision != choice:
            if r.status != BOARD_TO_STATUS[a.decision]:
                raise ApplicationError("Başvuru karardan sonra ilerlemiş; karar değiştirilemez.", 409)
            if c.execute(sa.select(LETTERS.c.id).where(LETTERS.c.app_id == r.id, LETTERS.c.state != "taslak",
                                                       LETTERS.c.created_at >= a.decided_at)).first():
                raise ApplicationError("Önceki kararın yazısı onaylanmış; önce yazının onayını geri alın.", 409)
            c.execute(LETTERS.delete().where(LETTERS.c.app_id == r.id, LETTERS.c.state == "taslak",
                                             LETTERS.c.created_at >= a.decided_at))
        now = _now()
        c.execute(sa.update(AGENDA).where(AGENDA.c.id == a.id).values(
            decision=choice, decision_note=note, decided_by=user, decided_name=display or user, decided_at=now, **extra))
        closing = choice in ("kabul", "red")
        c.execute(sa.update(APPS).where(APPS.c.id == r.id).values(
            status=BOARD_TO_STATUS[choice], decision_note=note, decided_by=user if closing else None,
            decided_at=now if closing else None, updated_by=user, updated_at=now))
        _log(c, r.id, user, display, f"kurul_{choice}", {"oturum": s.title, "not": note,
                                                          **{k: v for k, v in extra.items() if v is not None}})
    return {"ok": True, "decision": choice, "status": BOARD_TO_STATUS[choice]}


def close_session(engine: sa.engine.Engine, tenant: str, user: str, display: str, sid: str, *, manager: bool) -> dict[str, Any]:
    """Oturumu kapatır. Kararı kaydedilmemiş başvurular «karar verilmeden ertelendi» olur ve kurul sırasına döner."""
    with engine.begin() as c:
        s = _session_row(c, tenant, sid)
        if not _can_run(s, user, manager):
            raise ApplicationError("Oturumu başkan ya da yayın kurulu yöneticisi kapatır.", 403)
        if s.state != "planli":
            raise ApplicationError("Oturum zaten kapalı.", 409)
        pending = c.execute(sa.select(AGENDA).where(AGENDA.c.session_id == s.id, AGENDA.c.decision.is_(None))).all()
        now = _now()
        for a in pending:
            c.execute(sa.update(AGENDA).where(AGENDA.c.id == a.id).values(decision="ertelendi", decided_by=user,
                                                                          decided_name=display or user, decided_at=now))
            c.execute(sa.update(APPS).where(APPS.c.id == a.app_id, APPS.c.status == "kurulda").values(
                status="kurul_bekliyor", updated_by=user, updated_at=now))
            _log(c, a.app_id, user, display, "kurul_ertelendi", {"oturum": s.title})
        c.execute(sa.update(SESSIONS).where(SESSIONS.c.id == s.id).values(state="kapandi", closed_by=user, closed_at=now))
    return {"ok": True, "postponed": len(pending)}


def delete_session(engine: sa.engine.Engine, tenant: str, user: str, sid: str, *, manager: bool) -> dict[str, Any]:
    with engine.begin() as c:
        s = _session_row(c, tenant, sid)
        if not _can_run(s, user, manager):
            raise ApplicationError("Oturumu başkan ya da yayın kurulu yöneticisi siler.", 403)
        if c.execute(sa.select(AGENDA.c.id).where(AGENDA.c.session_id == s.id)).first():
            raise ApplicationError("Gündemi olan oturum silinmez; önce başvuruları gündemden çıkarın.", 409)
        c.execute(SESSIONS.delete().where(SESSIONS.c.id == s.id))
    return {"id": s.id, "title": s.title}


# ---------------------------------------------------------------------------------------- kurul raporu kaydı

def start_report(engine: sa.engine.Engine, tenant: str, user: str, app_id: str) -> Optional[str]:
    """Yeni rapor kaydı açar; aynı başvuruda süren hazırlık varsa None döner (ikinci iş başlatılmaz)."""
    with engine.begin() as c:
        r = _row(c, tenant, app_id)
        running = c.execute(sa.select(REPORTS.c.id).where(REPORTS.c.app_id == r.id, REPORTS.c.status == "hazirlaniyor")).first()
        if running:
            return None
        rid = _new()
        c.execute(REPORTS.insert().values(id=rid, app_id=r.id, status="hazirlaniyor", created_by=user, created_at=_now()))
    return rid


def finish_report(engine: sa.engine.Engine, report_id: str, content: Optional[dict[str, Any]], error: Optional[str]) -> None:
    with engine.begin() as c:
        c.execute(sa.update(REPORTS).where(REPORTS.c.id == report_id).values(
            status="hata" if error else "hazir", error=error,
            content_json=json.dumps(content, ensure_ascii=False, default=str) if content is not None else None,
            finished_at=_now()))


def report(engine: sa.engine.Engine, tenant: str, app_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _row(c, tenant, app_id)
        rep = c.execute(sa.select(REPORTS).where(REPORTS.c.app_id == r.id).order_by(REPORTS.c.created_at.desc()).limit(1)).first()
        # Yeniden üretim sürerken ya da düşmüşse son hazır rapor ekranda kalır.
        ready = rep if rep is not None and rep.content_json else c.execute(
            sa.select(REPORTS).where(REPORTS.c.app_id == r.id, REPORTS.c.status == "hazir")
            .order_by(REPORTS.c.created_at.desc()).limit(1)).first()
    if rep is None:
        return {"status": None}
    return {"id": rep.id, "status": rep.status, "error": rep.error, "createdBy": rep.created_by,
            "createdAt": _iso(rep.created_at), "finishedAt": _iso(ready.finished_at if ready is not None else rep.finished_at),
            "content": json.loads(ready.content_json) if ready is not None and ready.content_json else None}


def snapshot(engine: sa.engine.Engine, tenant: str, app_id: str) -> dict[str, Any]:
    """Rapor için başvurunun ve güncel editör raporunun o anki hâli."""
    with engine.connect() as c:
        r = _row(c, tenant, app_id)
        e = c.execute(sa.select(EVALS).where(EVALS.c.app_id == r.id, EVALS.c.round == r.round)).first()
    return {"app": _out(r), "evaluation": _eval_out(e) if e is not None and e.submitted_at else None}


def market_cached(engine: sa.engine.Engine, tenant: str, category_id: str, max_age_hours: float) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        m = c.execute(sa.select(MARKET).where(MARKET.c.tenant_id == tenant, MARKET.c.category_id == category_id)).first()
    if m is None:
        return None
    at = m.computed_at if m.computed_at.tzinfo else m.computed_at.replace(tzinfo=timezone.utc)
    if (_now() - at).total_seconds() > max_age_hours * 3600:
        return None
    return json.loads(m.content_json)


def market_store(engine: sa.engine.Engine, tenant: str, category_id: str, content: dict[str, Any]) -> None:
    with engine.begin() as c:
        c.execute(MARKET.delete().where(MARKET.c.tenant_id == tenant, MARKET.c.category_id == category_id))
        c.execute(MARKET.insert().values(tenant_id=tenant, category_id=category_id, computed_at=_now(),
                                         content_json=json.dumps(content, ensure_ascii=False, default=str)))


def meta(accept: int = DEFAULT_ACCEPT, revise: int = DEFAULT_REVISE) -> dict[str, Any]:
    def opts(d: dict[str, str]) -> list[dict[str, str]]:
        return [{"value": k, "label": v} for k, v in d.items()]
    return {"statuses": opts(STATUSES), "channels": opts(CHANNELS), "audiences": opts(AUDIENCES),
            "fileKinds": opts(FILE_KINDS), "recommendations": opts(RECOMMENDATIONS), "redlines": opts(REDLINES),
            "votes": opts(VOTES_LABEL), "decisions": opts({k: v for k, v in DECISIONS.items() if k != "ertelendi"}),
            "letterKinds": opts(LETTER_KINDS), "sendChannels": opts(SEND_CHANNELS),
            "thresholds": {"accept": accept, "revise": revise}, "fileMaxMb": FILE_MAX // (1024 * 1024)}
