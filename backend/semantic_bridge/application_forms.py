"""Yazar başvurusu Google Formları → Başvurular (M1). Yalnız okuma (kullanıcı isteği 2026-09-29).

TİMAŞ yazar başvurularını yaş grubuna göre üç Google Formuyla alıyor (Çocuk 0-9, İlk Gençlik 9-11, Genç 11-14);
her formun yanıtları `basvuru@timas.com.tr`'nin bir Google E-Tablosunda. Bu modül tabloları servis hesabıyla okur ve
her yanıtı Başvurular'da «Yeni başvuru» olarak açar. Google tarafına hiçbir şey yazılmaz.

- Hangi tablolar: Yönetim → Başvuru formları (`BASVURU_FORM_SHEETS`, satır başına tablo bağlantısı ya da kimliği).
  Tablo servis hesabıyla (Görüntüleyici) paylaşılmış olmalı; paylaşılmamışsa o tablo hata olarak raporlanır, diğerleri
  okunur.
- Sütunlar başlık adıyla eşlenir (sıra değişse de kayma olmaz). 2026-09-29'da Genç tablosunda ölçüldü: 21 soru,
  277 yanıt, «Form ID» her satırda dolu ve tekil → tekrar önleme anahtarı (tablo + Form ID).
- Hedef kitle ve yaş aralığı yanıttaki «Hedef Okur Kitlesi»nden okunur («Genç (11-14 Yaş)» → genç, 11–14); tabloya
  özel ayar yoktur.
- Formun sormadığı alanlar boş kalır (sayfa tahmini, biyografi); editör sonra girer. Formun bütün cevapları (adres,
  konu, öne çıkan yönler, referanslar, CV ve eser dosyası bağlantıları) başvurunun «Form yanıtları» bölümünde durur.
- Bir yanıt bir kez açılır. Tabloda sonradan değişen yanıt yalnız «Form yanıtları»nı günceller; başvurunun portaldaki
  alanlarına dokunulmaz (editör düzeltmiş olabilir).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import quote

import sqlalchemy as sa

from semantic_bridge import editorial_applications as apps

log = logging.getLogger("semantic.application_forms")

#: Değişiklik kaydında işi yapan (bellek: audit-actor-zeki-ai).
ACTOR = "ZEKİ AI"
SCOPES = "https://www.googleapis.com/auth/spreadsheets.readonly"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"

_md = sa.MetaData()

ANSWERS = sa.Table(
    "semantic_editorial_application_forms", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("sheet_id", sa.String(80), nullable=False),
    sa.Column("sheet_title", sa.String(300)),
    sa.Column("form_row_id", sa.String(120), nullable=False),
    sa.Column("app_id", sa.String(32), nullable=False, index=True),
    sa.Column("answers_json", sa.Text, nullable=False),
    sa.Column("received_at", sa.DateTime(timezone=True)),
    sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "sheet_id", "form_row_id", name="uq_editorial_application_form_row"),
)
RUNS = sa.Table(
    "semantic_editorial_application_form_runs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("actor", sa.String(120), nullable=False),
    sa.Column("result_json", sa.Text, nullable=False),
)

_ready: set[int] = set()
_lock = threading.Lock()
_run_lock = threading.Lock()


class FormError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        apps.ensure(engine)
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------------------------------ başlık eşleme

def _fold(text: Any) -> str:
    """Başlık karşılaştırması: Türkçe harfler sadeleşir, noktalama ve fazla boşluk düşer."""
    t = str(text or "").replace("İ", "i").replace("I", "ı").lower()
    t = t.translate(str.maketrans("çğıöşü", "cgiosu"))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


#: Alan → başlıkta aranan kalıplar (katlanmış metin; ilk eşleşen alır). Sıra önemli: «soyadiniz» «adiniz»dan önce.
FIELDS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("formId", ("form id",), "Form kimliği"),
    ("timestamp", ("zaman damgasi", "timestamp"), "Gönderim zamanı"),
    ("lastName", ("soyadiniz", "soyadi"), "Soyadı"),
    ("firstName", ("adiniz",), "Adı"),
    ("email", ("e posta", "eposta", "email"), "E-posta"),
    ("phone", ("telefon",), "Telefon"),
    ("occupation", ("meslek", "meslegi"), "Meslek"),  # «Mesleğiniz» → «mesleginiz»
    ("country", ("ulke",), "Ülke"),
    ("city", ("il sehir", "sehir"), "İl / şehir"),
    ("district", ("ilce",), "İlçe"),
    ("address", ("acik adres", "adresiniz"), "Açık adres"),
    ("cv", ("ozgecmis", "cv"), "Özgeçmiş (CV)"),
    ("title", ("eserinizin adi", "eser adi"), "Eserin adı"),
    ("genre", ("eserinizin turu", "eser turu"), "Eserin türü"),
    ("topic", ("eserinizin konusu", "konusu"), "Eserin konusu"),
    ("synopsis", ("ozeti", "sinopsis"), "Özet (sinopsis)"),
    ("audience", ("hedef okur",), "Hedef okur kitlesi"),
    ("highlights", ("one cikan",), "Öne çıkan yönleri"),
    ("references", ("referans",), "Referanslar"),
    ("workFile", ("eser dosya",), "Eser dosyası"),
    ("consent", ("basvuru kosul", "onayliyorum"), "Başvuru koşulları onayı"),
)
LABELS = {k: label for k, _, label in FIELDS}
REQUIRED = ("formId", "title", "firstName")


def map_header(header: list[Any]) -> dict[str, int]:
    """Başlık satırı → {alan: sütun sırası}. Eşleşmeyen başlık yok sayılır; aynı alana ikinci sütun bağlanmaz."""
    out: dict[str, int] = {}
    used: set[int] = set()
    folded = [_fold(h) for h in header]
    for key, patterns, _ in FIELDS:
        for i, h in enumerate(folded):
            if i in used or not h:
                continue
            if any(h == p or h.startswith(p + " ") or f" {p}" in f" {h}" for p in patterns):
                out[key] = i
                used.add(i)
                break
    return out


# ------------------------------------------------------------------------------------------ satır → başvuru

_TS = re.compile(r"^\s*(\d{1,2})[./](\d{1,2})[./](\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?")
_AGES = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})")


def parse_timestamp(v: Any) -> Optional[datetime]:
    """Google Formlarının Türkçe zaman damgası «26.09.2026 14:03:11» (İstanbul saati, UTC+3)."""
    m = _TS.match(str(v or ""))
    if not m:
        return None
    d, mo, y, h, mi, s = (int(x) if x else 0 for x in m.groups())
    try:
        local = datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None
    from zoneinfo import ZoneInfo
    return local.replace(tzinfo=ZoneInfo("Europe/Istanbul")).astimezone(timezone.utc)


def parse_audience(v: Any) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """«Genç (11-14 Yaş)» → ("genc", 11, 14); «Çocuk (0-9 Yaş)» → ("cocuk", 0, 9); «İlk Gençlik (9-11 Yaş)» → genç.
    Hedef kitle CRM kitap kartının üç seçeneğinden biridir (çocuk / genç / yetişkin)."""
    t = _fold(v)
    kind = "cocuk" if "cocuk" in t else "genc" if "genc" in t else "yetiskin" if "yetiskin" in t else None
    m = _AGES.search(str(v or ""))
    lo, hi = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    return kind, lo, hi


def _cell(row: list[Any], cols: dict[str, int], key: str) -> str:
    i = cols.get(key)
    if i is None or i >= len(row):
        return ""
    return str(row[i] or "").strip()


def answers_of(row: list[Any], header: list[Any], cols: dict[str, int]) -> list[dict[str, str]]:
    """Formun bütün cevapları, formdaki sırayla: eşlenen alanlar kendi adıyla, eşlenmeyen sütunlar başlığıyla."""
    by_col = {i: k for k, i in cols.items()}
    out = []
    for i, h in enumerate(header):
        v = str(row[i]).strip() if i < len(row) and row[i] is not None else ""
        key = by_col.get(i)
        if key in ("formId",):
            continue
        out.append({"key": key or f"col{i + 1}", "label": LABELS.get(key or "", str(h).strip() or f"Sütun {i + 1}"),
                    "value": v})
    return out


def application_of(row: list[Any], cols: dict[str, int]) -> dict[str, Any]:
    """Portal başvuru kolonları (editorial_applications.APPS). Formun sormadığı zorunlu alanlar boş bırakılır."""
    first, last = _cell(row, cols, "firstName"), _cell(row, cols, "lastName")
    title = _cell(row, cols, "title")
    received = parse_timestamp(_cell(row, cols, "timestamp"))
    kind, lo, hi = parse_audience(_cell(row, cols, "audience"))
    summary = _cell(row, cols, "synopsis") or _cell(row, cols, "topic")
    email = _cell(row, cols, "email")
    return {
        "title": (title or "Adsız eser")[:300],
        "author_name": (" ".join(x for x in (first, last) if x) or "Adı yazılmamış")[:200],
        "author_email": email[:200] if email and apps._EMAIL.match(email) else None,
        "author_phone": _cell(row, cols, "phone")[:60] or None,
        "author_expertise": _cell(row, cols, "occupation")[:4000] or None,
        "author_history": _cell(row, cols, "references")[:8000] or None,
        "summary": (summary or "Formda özet yazılmamış.")[:20000],
        "audience": kind, "age_from": lo, "age_to": hi,
        "genre": _cell(row, cols, "genre")[:120] or None,
        "channel": "web",
        "received_on": (received.astimezone(_ist()).date() if received else datetime.now(timezone.utc).date()),
    }


def _ist():
    from zoneinfo import ZoneInfo
    return ZoneInfo("Europe/Istanbul")


# ------------------------------------------------------------------------------------------ ayar ve okuma

_SHEET_ID = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})|^([A-Za-z0-9_-]{20,})$")


def sheet_ids(setting: str) -> list[str]:
    """Ayar metni (satır ya da virgülle ayrılmış bağlantı/kimlik) → tablo kimlikleri, sırayla, tekrarsız."""
    out: list[str] = []
    for part in re.split(r"[\s,;]+", setting or ""):
        m = _SHEET_ID.search(part.strip())
        sid = (m.group(1) or m.group(2)) if m else None
        if sid and sid not in out:
            out.append(sid)
    return out


def read_sheet(sheet_id: str, http_get: Callable[[str, dict[str, Any]], dict[str, Any]]) -> tuple[str, list[list[Any]]]:
    """(tablo adı, satırlar). İlk sayfa okunur (formların yanıt sayfası)."""
    meta = http_get(f"{SHEETS_API}/{sheet_id}", {"fields": "properties(title),sheets(properties(title))"})
    sheets = meta.get("sheets") or []
    if not sheets:
        raise FormError("Tabloda sayfa yok.")
    first = sheets[0]["properties"]["title"]
    rng = quote(f"'{first}'", safe="")
    vals = http_get(f"{SHEETS_API}/{sheet_id}/values/{rng}", {"valueRenderOption": "FORMATTED_VALUE"})
    return str((meta.get("properties") or {}).get("title") or sheet_id), vals.get("values") or []


def google_getter(token_fn: Callable[[str], str]) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    import httpx

    def get(url: str, params: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=60) as c:
            r = c.get(url, params=params, headers={"Authorization": f"Bearer {token_fn(SCOPES)}"})
        if r.status_code in (403, 404):
            raise FormError("Tablo servis hesabıyla paylaşılmamış (Görüntüleyici olarak eklenmeli).", 403)
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message")
            except ValueError:
                msg = None
            raise FormError(f"Google {r.status_code}: {(msg or r.text)[:200]}", 502)
        return r.json()

    return get


# ------------------------------------------------------------------------------------------ aktarım

def _now() -> datetime:
    return datetime.now(timezone.utc)


def import_sheet(engine: sa.engine.Engine, tenant: str, sheet_id: str, title: str, rows: list[list[Any]]) -> dict[str, Any]:
    """Bir tablonun satırlarını aktarır. Dönen: yeni, var olan, güncellenen, atlanan (gerekçesiyle) sayıları."""
    res: dict[str, Any] = {"sheetId": sheet_id, "title": title, "rows": max(0, len(rows) - 1), "new": 0,
                           "existing": 0, "updated": 0, "skipped": 0, "problems": []}
    if not rows:
        res["problems"].append("Tablo boş.")
        return res
    header, data = rows[0], rows[1:]
    cols = map_header(header)
    missing = [LABELS[k] for k in REQUIRED if k not in cols]
    if missing:
        res["problems"].append("Başlıkta bulunamadı: " + ", ".join(missing))
        res["skipped"] = len(data)
        return res
    with engine.connect() as c:
        known = {r.form_row_id: r for r in c.execute(sa.select(ANSWERS.c.form_row_id, ANSWERS.c.answers_json, ANSWERS.c.id)
                                                     .where(ANSWERS.c.tenant_id == tenant, ANSWERS.c.sheet_id == sheet_id))}
    for row in data:
        fid = _cell(row, cols, "formId")
        if not fid:
            res["skipped"] += 1
            continue
        answers = json.dumps(answers_of(row, header, cols), ensure_ascii=False)
        prev = known.get(fid)
        if prev is not None:
            res["existing"] += 1
            if prev.answers_json != answers:
                with engine.begin() as c:
                    c.execute(ANSWERS.update().where(ANSWERS.c.id == prev.id).values(answers_json=answers, updated_at=_now()))
                res["updated"] += 1
            continue
        vals = application_of(row, cols)
        received = parse_timestamp(_cell(row, cols, "timestamp"))
        aid = uuid.uuid4().hex
        for attempt in range(3):
            try:
                with engine.begin() as c:
                    no = apps._next_no(c, tenant, vals["received_on"].year)
                    c.execute(apps.APPS.insert().values(id=aid, tenant_id=tenant, no=no, status="yeni", round=1,
                                                        page_estimate=None, created_by=ACTOR, created_at=_now(), **vals))
                    c.execute(ANSWERS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, sheet_id=sheet_id,
                                                      sheet_title=title[:300], form_row_id=fid[:120], app_id=aid,
                                                      answers_json=answers, received_at=received, imported_at=_now()))
                    apps._log(c, aid, ACTOR, ACTOR, "formdan", {"no": no, "tablo": title, "form": fid})
                break
            except sa.exc.IntegrityError:
                if attempt == 2:
                    raise
        res["new"] += 1
    return res


def sync(engine: sa.engine.Engine, tenant: str, setting: str, token_fn: Callable[[str], str], *,
         actor: str = ACTOR, http_get: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None) -> dict[str, Any]:
    """Ayardaki bütün tabloları okur ve aktarır. Aynı anda tek koşu; bir tablonun hatası öbürlerini durdurmaz."""
    ensure(engine)
    ids = sheet_ids(setting)
    if not ids:
        raise FormError("Başvuru formu tablosu tanımlı değil (Yönetim → Başvuru formları).", 409)
    if not _run_lock.acquire(blocking=False):
        raise FormError("Formlar şu an okunuyor; birazdan yeniden deneyin.", 409)
    try:
        get = http_get or google_getter(token_fn)
        sheets = []
        for sid in ids:
            try:
                title, rows = read_sheet(sid, get)
                sheets.append(import_sheet(engine, tenant, sid, title, rows))
            except FormError as e:
                sheets.append({"sheetId": sid, "title": None, "error": str(e)})
            except Exception as e:  # noqa: BLE001 — bir tablo düşerse öbürleri okunur; ayrıntı günlükte
                log.exception("başvuru formu okunamadı: %s", sid)
                sheets.append({"sheetId": sid, "title": None, "error": f"Okunamadı: {type(e).__name__}"})
        result = {"at": _now().isoformat(), "sheets": sheets,
                  "new": sum(s.get("new", 0) for s in sheets), "errors": sum(1 for s in sheets if s.get("error"))}
        with engine.begin() as c:
            c.execute(RUNS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, at=_now(), actor=actor[:120],
                                           result_json=json.dumps(result, ensure_ascii=False)))
        return result
    finally:
        _run_lock.release()


def status(engine: sa.engine.Engine, tenant: str, setting: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        last = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant).order_by(RUNS.c.at.desc()).limit(1)).first()
        counts = {r.sheet_id: {"title": r.baslik, "applications": int(r.n)} for r in c.execute(
            sa.select(ANSWERS.c.sheet_id, sa.func.max(ANSWERS.c.sheet_title).label("baslik"), sa.func.count().label("n"))
            .where(ANSWERS.c.tenant_id == tenant).group_by(ANSWERS.c.sheet_id))}
    ids = sheet_ids(setting)
    return {"configured": len(ids), "sheets": [{"sheetId": s, **counts.get(s, {"title": None, "applications": 0})} for s in ids],
            "lastRun": json.loads(last.result_json) if last else None, "lastRunBy": last.actor if last else None}


def answers_for(engine: sa.engine.Engine, tenant: str, app_id: str) -> Optional[dict[str, Any]]:
    """Başvurunun geldiği form yanıtı (formdan gelmediyse None)."""
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(ANSWERS).where(ANSWERS.c.tenant_id == tenant, ANSWERS.c.app_id == app_id)).first()
    if not r:
        return None
    return {"sheetTitle": r.sheet_title, "formRowId": r.form_row_id, "answers": json.loads(r.answers_json),
            "receivedAt": apps._iso(r.received_at), "importedAt": apps._iso(r.imported_at),
            "updatedAt": apps._iso(r.updated_at),
            "sheetUrl": f"https://docs.google.com/spreadsheets/d/{r.sheet_id}/edit"}
