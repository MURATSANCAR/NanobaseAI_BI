"""Kitabın içeriğine soru sorma: portal → Hermes (editör motoru) → kanıtlı cevap.

Editör motoru ayrı bir yığındır (TT GPU, kendi Postgres/Qdrant/modelleri). Köprü onun veritabanına
dokunmaz; yalnız OpenAI uyumlu API'sinden (`EDITOR_API_BASE`, ters tünelle `127.0.0.1:18887`) sorar.
Hermes bir ajandır: soruyu kendi araçlarıyla (kanıt arama, karakter/olay geçmişi, rapor) yanıtlar.

**Neden iş, neden anlık değil:** motor modeli istendiğinde açar ve GPU kitap analiziyle paylaşılır.
Kart yer açana kadar soru bekler. Bu yüzden soru bir kayıt olarak açılır, arka planda sorulur, cevap
geldiğinde kaydedilir; ekran durumu izler. Hiçbir cevap uydurulmaz: motor cevap vermezse hata yazılır.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import sqlalchemy as sa

log = logging.getLogger("semantic.editorial_books")
_md = sa.MetaData()

QUESTIONS = sa.Table(
    "semantic_editorial_questions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("username", sa.String(120), nullable=False, index=True),
    sa.Column("book_key", sa.String(200), nullable=False, index=True),
    sa.Column("book_title", sa.String(300)),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("status", sa.String(20), nullable=False, default="bekliyor"),  # bekliyor | calisiyor | bitti | hata
    sa.Column("answer", sa.Text),
    sa.Column("not_found", sa.Boolean),
    sa.Column("error", sa.String(600)),
    sa.Column("elapsed_ms", sa.Integer),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)

#: Aynı anda motora giden tek soru: motor tek modelle çalışır, ikinci soru sırada bekler.
_gate = threading.Semaphore(1)
_ready: set[int] = set()
_lock = threading.Lock()

MAX_QUESTION = 2000
#: Motor modeli açana ve araçlarını koşturana kadar geçen süre dakikalarla ölçülür.
TIMEOUT_SEC = float(os.environ.get("EDITOR_ASK_TIMEOUT_SEC", "1800"))

#: Bulunamayan bilgi bu cümleyle başlar; ekran bunu tanıyıp sakin bir bilgi kartı olarak gösterir.
NOT_FOUND = "Kitapta bulunamadı."

SYSTEM = (
    "Sen Timaş'ın editör asistanısın. Yalnız analiz edilmiş kitapların metninden ve o metinden çıkarılmış "
    "kayıtlardan cevap verirsin. Önce ilgili kitabı ve nesli bul, sonra kanıt arama araçlarını kullan. "
    "Her iddiayı hangi sayfaya dayandığını yazarak ver (örnek: «s. 14»). Cevabı Türkçe, kısa ve sıcak bir "
    "dille yaz; «kanıt defteri», «generation», «claim» gibi iç terimleri kullanma.\n"
    f"Sorulan şey kitapta yoksa cevabına birebir «{NOT_FOUND}» cümlesiyle başla, sonra tek cümleyle nereye "
    "baktığını ve varsa en yakın bilgiyi sayfasıyla söyle. Asla uydurma.\n"
    "Sorulan kitap hiç analiz edilmemişse bunu açıkça söyle ve hangi kitapların analiz edildiğini yaz."
)


#: Okunmuş kitapların listesi: motora sorulur, kısa süre bellekte tutulur (her açılışta model çağırmayalım).
_BOOKS_TTL = 600.0
_books_cache: dict[str, Any] = {"at": 0.0, "items": [], "busy": False}
_books_lock = threading.Lock()

BOOKS_SYSTEM = (
    "Analiz edilmiş kitapların listesini ver. Yalnız bir JSON dizisi döndür, başka hiçbir şey yazma: "
    '["Kitap Adı", "Kitap Adı"]. Kitap adlarını okunur biçimde yaz (kısa ad değil, gerçek adı).'
)


class BookAskError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _add_missing_columns(engine)
        _ready.add(id(engine))


def _add_missing_columns(engine: sa.engine.Engine) -> None:
    """`create_all` var olan tabloya kolon eklemez; sonradan gelen kolonlar burada eklenir."""
    try:
        have = {c["name"] for c in sa.inspect(engine).get_columns(QUESTIONS.name)}
    except Exception:  # noqa: BLE001 — tablo henüz yoksa create_all zaten kurdu
        return
    for col, ddl in (("not_found", "BOOLEAN"),):
        if col not in have:
            try:
                with engine.begin() as conn:
                    conn.execute(sa.text(f"ALTER TABLE {QUESTIONS.name} ADD COLUMN {col} {ddl}"))
            except Exception as e:  # noqa: BLE001 — yarışta başkası eklemiş olabilir
                log.warning("editorial questions: %s kolonu eklenemedi: %s", col, e)


def configured() -> bool:
    return bool(os.environ.get("EDITOR_API_BASE") and os.environ.get("EDITOR_API_KEY"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _row(r: Any) -> dict[str, Any]:
    return {"id": r.id, "bookKey": r.book_key, "bookTitle": r.book_title, "question": r.question,
            "status": r.status, "answer": r.answer, "notFound": bool(r.not_found), "error": r.error, "elapsedMs": r.elapsed_ms,
            "username": r.username, "createdAt": _iso(r.created_at), "finishedAt": _iso(r.finished_at)}


def reset_stale(engine: sa.engine.Engine) -> None:
    """Servis yeniden başladıysa yarıda kalan soru «çalışıyor» diye asılı kalmasın."""
    with engine.begin() as conn:
        conn.execute(sa.update(QUESTIONS).where(QUESTIONS.c.status.in_(("bekliyor", "calisiyor")))
                     .values(status="hata", error="Servis yeniden başladı; soruyu tekrar sorun.", finished_at=_now()))


def ask_engine(question: str, book_title: Optional[str], *, system: Optional[str] = None) -> str:
    """Motora tek çağrı. Cevap boş gelirse hata; sessizce boş cevap dönmez."""
    base = (os.environ.get("EDITOR_API_BASE") or "").rstrip("/")
    key = os.environ.get("EDITOR_API_KEY") or ""
    model = os.environ.get("EDITOR_MODEL") or "book-director"
    if not base or not key:
        raise BookAskError("Editör motoru bu kurulumda tanımlı değil.", 503)
    user = question if not book_title else f"Kitap: «{book_title}». Soru: {question}"
    payload = {"model": model, "stream": False,
               "messages": [{"role": "system", "content": system or SYSTEM}, {"role": "user", "content": user}]}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # Motora internet üzerinden gidiliyorsa nginx ikinci bir gizli başlık ister; ad:değer olarak verilir.
    extra = (os.environ.get("EDITOR_EXTRA_HEADER") or "").strip()
    if ":" in extra:
        name, _, value = extra.partition(":")
        headers[name.strip()] = value.strip()
    # Kendi imzalı sertifika: dosya verilmişse ona göre doğrulanır (doğrulama kapatılmaz).
    ca = (os.environ.get("EDITOR_CA_FILE") or "").strip()
    verify: Any = ca if ca and os.path.isfile(ca) else True
    with httpx.Client(timeout=httpx.Timeout(TIMEOUT_SEC, connect=15.0), verify=verify) as client:
        r = client.post(f"{base}/chat/completions", json=payload, headers=headers)
    if r.status_code >= 400:
        detail = r.text[:300]
        raise BookAskError(f"Editör motoru {r.status_code}: {detail}", 502)
    try:
        text = (r.json()["choices"][0]["message"]["content"] or "").strip()
    except (ValueError, KeyError, IndexError) as e:
        raise BookAskError("Editör motorundan beklenen biçimde cevap gelmedi.", 502) from e
    if not text:
        raise BookAskError("Editör motoru boş cevap döndü.", 502)
    return text


def readable_books(*, fresh: bool = False) -> dict[str, Any]:
    """Soru sorulabilen kitaplar. **Beklemez:** elde ne varsa onu döner, gerekiyorsa arka planda tazeler.
    Motor modeli kapalıysa liste ilk seferde boş gelir ve birkaç saniye sonra dolar; ekran sayfayı bekletmez."""
    import time as _time
    if not configured():
        return {"items": [], "at": None, "configured": False, "loading": False}
    with _books_lock:
        age = _time.time() - float(_books_cache["at"])
        items = list(_books_cache["items"])
        busy = bool(_books_cache.get("busy"))
        stale = fresh or age >= _BOOKS_TTL or not items
        if stale and not busy:
            _books_cache["busy"] = True
            threading.Thread(target=_refresh_books, name="editorial-books", daemon=True).start()
            busy = True
    return {"items": items, "at": _books_cache["at"] or None, "configured": True, "loading": busy and not items}


def _refresh_books() -> None:
    import time as _time
    items: list[str] = []
    try:
        raw = ask_engine("Hangi kitaplar okundu?", None, system=BOOKS_SYSTEM)
        m = re.search(r"\[.*\]", raw, re.S)
        if m:
            items = [str(x).strip() for x in json.loads(m.group(0)) if str(x).strip()][:50]
    except Exception as e:  # noqa: BLE001 — liste bir kolaylıktır, soru sormayı engellemez
        log.warning("editorial readable books failed: %s", e)
    with _books_lock:
        if items:
            _books_cache["items"], _books_cache["at"] = items, _time.time()
        _books_cache["busy"] = False


def ask(engine: sa.engine.Engine, tenant: str, user: str, question: str, *,
        book_key: str = "", book_title: Optional[str] = None) -> dict[str, Any]:
    q = (question or "").strip()
    if not q:
        raise BookAskError("Soru yazılmadı.")
    if len(q) > MAX_QUESTION:
        raise BookAskError(f"Soru {MAX_QUESTION} karakteri aşamaz.")
    if not configured():
        raise BookAskError("Editör motoru bu kurulumda tanımlı değil.", 503)
    qid = uuid.uuid4().hex
    row = {"id": qid, "tenant_id": tenant, "username": user, "book_key": (book_key or "")[:200],
           "book_title": (book_title or None), "question": q, "status": "bekliyor", "created_at": _now()}
    with engine.begin() as conn:
        conn.execute(sa.insert(QUESTIONS).values(**row))

    def run() -> None:
        started = _now()
        # Motor tek modelle çalışır; sıraya girilir. Bekleyen soru «bekliyor» kalır, koşan «çalışıyor».
        with _gate:
            with engine.begin() as conn:
                conn.execute(sa.update(QUESTIONS).where(QUESTIONS.c.id == qid).values(status="calisiyor"))
            started = _now()
            try:
                answer, err = ask_engine(q, book_title), None
            except Exception as e:  # noqa: BLE001
                log.warning("editorial book ask failed: %s", e)
                answer, err = None, str(e)[:580]
            done = _now()
            with engine.begin() as conn:
                conn.execute(sa.update(QUESTIONS).where(QUESTIONS.c.id == qid).values(
                    status="bitti" if answer else "hata", answer=answer, error=err,
                    not_found=bool(answer and answer.lstrip().startswith(NOT_FOUND)),
                    elapsed_ms=int((done - started).total_seconds() * 1000), finished_at=done))

    threading.Thread(target=run, name=f"editorial-ask-{qid[:8]}", daemon=True).start()
    return {"id": qid, "status": "bekliyor"}


def one(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, qid: str) -> dict[str, Any]:
    with engine.connect() as conn:
        r = conn.execute(sa.select(QUESTIONS).where(QUESTIONS.c.id == qid, QUESTIONS.c.tenant_id == tenant)).first()
    if r is None:
        raise BookAskError("Soru bulunamadı.", 404)
    if not admin and r.username.lower() != user.lower():
        raise BookAskError("Bu soru size ait değil.", 403)
    return _row(r)


def recent(engine: sa.engine.Engine, tenant: str, user: str, *, book_key: str = "", limit: int = 20) -> dict[str, Any]:
    where = [QUESTIONS.c.tenant_id == tenant, sa.func.lower(QUESTIONS.c.username) == user.lower()]
    if book_key:
        where.append(QUESTIONS.c.book_key == book_key[:200])
    with engine.connect() as conn:
        rows = conn.execute(sa.select(QUESTIONS).where(*where)
                            .order_by(QUESTIONS.c.created_at.desc()).limit(max(1, min(int(limit), 50)))).all()
        running = conn.execute(sa.select(sa.func.count()).where(QUESTIONS.c.status.in_(("bekliyor", "calisiyor")))).scalar_one()
    return {"items": [_row(r) for r in rows], "running": int(running), "configured": configured()}
