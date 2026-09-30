"""Editoryal masa: M3 Redaksiyon ve M5 Son Okuma. CRM'de karşılığı olmayan iki modülün kendi kayıtları.

Bir **eser dosyası** (work) bir kitabın masadaki işidir; isteğe bağlı olarak bir CRM projesine bağlanır.
- M3: metin dosyası (DOCX / TXT / PDF) yüklenir → kitabın kendi bölüm yapısına göre ayrılır (yapı bulunamazsa
  «parça»; editorial_desk_structure.py) → her bölümün ölçüleri hesaplanır
  (Ateşman okunabilirlik, cümle uzunluğu, hece/kelime…) → model yazım ve üslup önerisi çıkarır → editör
  öneriyi kabul/ret eder (kabul metne işlenir) → bölüm onaylanır. İlk hâl saklanır; fark ondan hesaplanır.
- M5: prova PDF'i yüklenir → otomatik ön kontrol (sayfa, ebat, yazı tipi gömme, görsel renk uzayı, ISBN
  sağlaması ve metinde geçmesi, forma) + elle işaretlenen kontrol listesi → adı yazılı imzacılar kendi
  oturumlarıyla, o PDF'in SHA-256'sına imza atar. Yeni prova imzaları sıfırlar.

Dosyalar diskte (`EDITORIAL_DIR`), kayıtlar `semantic_editorial_*` tablolarında. Erişim: eseri açan, üyeler,
imzacılar ve yöneticiler. Yükleme gövdesi belleğe alınmaz, diske akar (`receive`); dosya boyutu için sayı tavanı yoktur,
yalnız diskte yer kalmayacaksa reddedilir (ZEKI-26). Yanlış yüklenen dosya kaldırılır ama silinmez: kayıt ve dosya iz
olarak kalır (`removed_at`), etkin sürüm bir öncekine döner (ZEKI-45). Matbaaya/ERP'ye gönderim, InDesign yaması, e-imza/KEP yoktur; üretilmez.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional, Union
from xml.etree import ElementTree

import sqlalchemy as sa

from semantic_bridge import editorial_desk_structure as structure_mod

log = logging.getLogger("semantic.editorial_desk")
_md = sa.MetaData()


def _col_id() -> sa.Column:
    return sa.Column("id", sa.String(32), primary_key=True)


WORKS = sa.Table(
    "semantic_editorial_works", _md, _col_id(),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("author", sa.String(300)),
    sa.Column("crm_project_id", sa.String(40)),
    sa.Column("crm_project_name", sa.String(300)),
    sa.Column("isbn", sa.String(20)),
    sa.Column("members_json", sa.Text, nullable=False, default="[]"),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
FILES = sa.Table(
    "semantic_editorial_files", _md, _col_id(),
    sa.Column("work_id", sa.String(32), nullable=False, index=True),
    sa.Column("kind", sa.String(20), nullable=False),          # manuscript | proof
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("filename", sa.String(300), nullable=False),
    sa.Column("bytes", sa.BigInteger, nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("path", sa.String(500), nullable=False),
    sa.Column("report_json", sa.Text, nullable=False, default="{}"),
    sa.Column("uploaded_by", sa.String(120), nullable=False),
    sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    # Kaldırılan sürüm (ZEKI-45): kayıt ve dosya iz olarak kalır, etkin sürüm sayılmaz.
    sa.Column("removed_at", sa.DateTime(timezone=True)),
    sa.Column("removed_by", sa.String(120)),
)
CHAPTERS = sa.Table(
    "semantic_editorial_chapters", _md, _col_id(),
    sa.Column("work_id", sa.String(32), nullable=False, index=True),
    sa.Column("file_id", sa.String(32), nullable=False, index=True),
    sa.Column("no", sa.Integer, nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("original", sa.Text, nullable=False),
    sa.Column("current", sa.Text, nullable=False),
    sa.Column("status", sa.String(20), nullable=False, default="bekliyor"),   # bekliyor | islemde | onaylandi
    sa.Column("review_state", sa.String(20), nullable=False, default="yok"),  # yok | calisiyor | bitti | hata
    sa.Column("review_note", sa.String(500)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
)
SUGGESTIONS = sa.Table(
    "semantic_editorial_suggestions", _md, _col_id(),
    sa.Column("work_id", sa.String(32), nullable=False, index=True),
    sa.Column("chapter_id", sa.String(32), nullable=False, index=True),
    sa.Column("kind", sa.String(20), nullable=False),           # yazim | uslup
    sa.Column("original", sa.Text, nullable=False),
    sa.Column("suggestion", sa.Text, nullable=False),
    sa.Column("reason", sa.Text),
    sa.Column("status", sa.String(20), nullable=False, default="bekliyor"),   # bekliyor | kabul | red
    sa.Column("applied_text", sa.Text),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
CHECKS = sa.Table(
    "semantic_editorial_checks", _md, _col_id(),
    sa.Column("work_id", sa.String(32), nullable=False, index=True),
    sa.Column("file_id", sa.String(32), nullable=False, index=True),
    sa.Column("key", sa.String(60), nullable=False),
    sa.Column("label", sa.String(200), nullable=False),
    sa.Column("auto", sa.Boolean, nullable=False),
    sa.Column("passed", sa.Boolean),
    sa.Column("evidence", sa.Text),
    sa.Column("checked_by", sa.String(120)),
    sa.Column("checked_at", sa.DateTime(timezone=True)),
)
SIGNATURES = sa.Table(
    "semantic_editorial_signatures", _md, _col_id(),
    sa.Column("work_id", sa.String(32), nullable=False, index=True),
    sa.Column("role", sa.String(80), nullable=False),
    sa.Column("username", sa.String(120), nullable=False),
    sa.Column("display", sa.String(200)),
    sa.Column("file_id", sa.String(32)),
    sa.Column("sha256", sa.String(64)),
    sa.Column("signed_at", sa.DateTime(timezone=True)),
)

#: Elle işaretlenen son okuma maddeleri (iş tanımı: M5 Aşama 1–2).
MANUAL_CHECKS = (
    ("toc", "İçindekiler sayfa numaraları metinle tutarlı"),
    ("imprint", "Telif bloğu ve künye bilgileri eksiksiz"),
    ("cover", "Kapak ile iç kapak başlık, alt başlık ve yazar adı aynı"),
    ("barcode", "Barkod ve fiyat etiketi doğru"),
    ("layout", "Yetim/dul satır ve kırık hece kontrolü yapıldı"),
)

_ready: set[int] = set()
_lock = threading.Lock()


class DeskError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Incoming:
    """Diske akıtılmış yükleme (ZEKI-26): gövde belleğe alınmaz; boyut ve SHA-256 akarken hesaplanır. Kayıt olunca
    dosya yerine taşınır (`stored`); olmazsa `discard` geçici dosyayı siler."""

    def __init__(self, path: str, size: int, sha256: str):
        self.path, self.size, self.sha256 = path, size, sha256
        self.stored = False
        self._handles: list[Any] = []

    def open(self):
        f = open(self.path, "rb")
        self._handles.append(f)
        return f

    def read(self) -> bytes:
        with open(self.path, "rb") as f:
            return f.read()

    def discard(self) -> None:
        for f in self._handles:
            try:
                f.close()
            except OSError:
                pass
        self._handles.clear()
        if not self.stored:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass


Blob = Union[bytes, Incoming]


def _size(data: Blob) -> int:
    return data.size if isinstance(data, Incoming) else len(data)


def _sha(data: Blob) -> str:
    return data.sha256 if isinstance(data, Incoming) else hashlib.sha256(data).hexdigest()


def _incoming_dir() -> str:
    return os.path.join(_root(), ".incoming")


def _reserve_bytes() -> int:
    """Yükleme diske yazılırken sunucuda bırakılacak boş yer. Dosya boyutu sınırı değil: diskin dolup başka
    işlerin (veritabanı, günlük) durmasını önler."""
    try:
        return max(0, int(float(os.environ.get("EDITORIAL_DISK_RESERVE_MB", "2048")) * 1024 * 1024))
    except ValueError:
        return 2048 * 1024 * 1024


def _check_space(folder: str, coming: int) -> None:
    free = shutil.disk_usage(folder).free
    if free - coming < _reserve_bytes():
        raise DeskError("Sunucuda bu dosya için yer kalmadı; sistem yöneticisine bildirin.", 507)


def _sweep_incoming(folder: str) -> None:
    """Yarıda kalmış (bağlantısı kopmuş, servis yeniden başlamış) yüklemelerin bir günden eski artıkları."""
    limit = time.time() - 86400
    try:
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if name.endswith(".part") and os.path.getmtime(p) < limit:
                os.unlink(p)
    except OSError:
        pass


def _max_upload_bytes() -> int:
    """Tek dosyanın üst sınırı (Yönetim → `EDITORIAL_UPLOAD_MAX_MB`, varsayılan 300; 0 = sınır yok). Kullanıcı kararı
    2026-09-30 (ZEKI-26): PDF okunurken bellek dosya boyuyla büyür; müşteri VM'inin belleği 7 GB."""
    try:
        from semantic_bridge import admin as admin_mod
        mb = float(admin_mod.conf("EDITORIAL_UPLOAD_MAX_MB") or 300)
    except Exception:  # noqa: BLE001 — ayar okunamazsa varsayılan
        mb = 300.0
    return max(0, int(mb * 1_000_000))          # ondalık MB: bilgisayarın dosya boyutuyla aynı birim


def _check_size(size: int) -> None:
    limit = _max_upload_bytes()
    if limit and size > limit:
        raise DeskError(f"Dosya {size / 1_000_000:,.0f} MB; bu kurulumda tek dosya için üst sınır "
                        f"{limit / 1_000_000:,.0f} MB. Dosyayı küçültün (ör. görselleri sıkıştırarak) ya da "
                        f"sistem yöneticisinden sınırı yükseltmesini isteyin.".replace(",", "."), 413)


async def receive(chunks: AsyncIterator[bytes], expected: int = 0) -> Incoming:
    """İstek gövdesini parça parça diske yazar (eser klasörüyle aynı disk: kayıtta kopyalanmaz, taşınır). Tek dosyanın
    üst sınırı `_max_upload_bytes` (bildirilen boy başta, gerçek boy akış sırasında); disk dolacaksa da durur."""
    folder = _incoming_dir()
    os.makedirs(folder, exist_ok=True)
    _sweep_incoming(folder)
    _check_size(max(0, expected))
    _check_space(folder, max(0, expected))
    fd, path = tempfile.mkstemp(dir=folder, suffix=".part")
    h, size, checked = hashlib.sha256(), 0, 0
    try:
        with os.fdopen(fd, "wb") as f:
            async for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                _check_size(size)
                f.write(chunk)
                h.update(chunk)
                if size - checked >= 256 * 1024 * 1024:
                    _check_space(folder, 0)
                    checked = size
    except BaseException:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        raise
    return Incoming(path, size, h.hexdigest())


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp

        def install() -> None:
            _md.create_all(engine, checkfirst=True)
            _add_missing_columns(engine)

        schema_stamp.run(engine, _md.sorted_tables, install, extra="files.removed")
        _ready.add(id(engine))


def _add_missing_columns(engine: sa.engine.Engine) -> None:
    """`create_all` var olan tabloya kolon eklemez; sonradan gelen kolonlar burada eklenir."""
    try:
        have = {c["name"] for c in sa.inspect(engine).get_columns(FILES.name)}
    except Exception:  # noqa: BLE001 — tablo henüz yoksa create_all zaten kurdu
        return
    for col in ("removed_at", "removed_by"):
        if col in have:
            continue
        ddl = FILES.c[col].type.compile(dialect=engine.dialect)
        try:
            with engine.begin() as conn:
                conn.execute(sa.text(f"ALTER TABLE {FILES.name} ADD COLUMN {col} {ddl}"))
        except Exception as e:  # noqa: BLE001 — yarışta başkası eklemiş olabilir
            log.warning("editorial files: %s kolonu eklenemedi: %s", col, e)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _new() -> str:
    return uuid.uuid4().hex


def _root() -> str:
    return os.environ.get("EDITORIAL_DIR", "/data/nanobaseai/bi/var/editorial")


# ---------------------------------------------------------------------------------------------- metin

_VOWELS = set("aeıioöuüAEIİOÖUÜâîûÂÎÛ")
_SENT = re.compile(r"[^.!?…]+[.!?…]+|[^.!?…]+$")
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
_HEADING = re.compile(r"^\s*(?:(?:\d{1,3}|[IVXLC]{1,7})\s*[.)\-–:]\s+\S.{0,80}|(?:BÖLÜM|Bölüm|KISIM|Kısım)\s+\S.{0,80}|(?:\d{1,3}|[IVXLC]{1,7})\.?)\s*$")


def metrics(text: str) -> dict[str, Any]:
    """Ateşman okunabilirlik ve dayandığı sayılar. Türkçede hece sayısı ünlü sayısıdır."""
    words = _WORD.findall(text)
    sentences = [s.strip() for p in text.split("\n") for s in _SENT.findall(p) if _WORD.search(s)]
    n_w, n_s = len(words), len(sentences)
    if not n_w or not n_s:
        return {"words": n_w, "sentences": n_s, "paragraphs": 0, "atesman": None, "syllablesPerWord": None,
                "wordsPerSentence": None, "longSentences": []}
    syll = sum(sum(1 for ch in w if ch in _VOWELS) for w in words)
    spw, wps = syll / n_w, n_w / n_s
    lengths = [(len(_WORD.findall(s)), s) for s in sentences]
    long_limit = max(25, round(wps * 2.5))
    return {
        "words": n_w, "sentences": n_s, "paragraphs": sum(1 for p in text.split("\n") if p.strip()),
        "atesman": round(198.825 - 40.175 * spw - 2.610 * wps, 1),
        "syllablesPerWord": round(spw, 2), "wordsPerSentence": round(wps, 1), "longLimit": long_limit,
        "longSentences": [{"words": n, "text": s[:400]} for n, s in sorted(lengths, reverse=True) if n >= long_limit][:20],
    }


def atesman_band(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    for limit, name in ((90, "Çok kolay"), (70, "Kolay"), (50, "Orta güçlükte"), (30, "Zor")):
        if score >= limit:
            return name
    return "Çok zor"


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_paragraphs(data: "Blob") -> list[tuple[str, bool]]:
    """(metin, başlık mı) çiftleri. Başlık: Word'ün başlık stili (Heading/Başlık/Title)."""
    try:
        with zipfile.ZipFile(data.path if isinstance(data, Incoming) else io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise DeskError("DOCX dosyası okunamadı.") from e
    out = []
    for p in ElementTree.fromstring(xml).iter(f"{_W}p"):
        style = p.find(f"{_W}pPr/{_W}pStyle")
        name = (style.get(f"{_W}val") if style is not None else "") or ""
        text = "".join(t.text or "" for t in p.iter(f"{_W}t")).strip()
        if text:
            out.append((text, bool(re.match(r"(?i)(heading|balk|başlık|baslik|title)", name))))
    return out


def _pdf_reader(data: "Blob"):
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise DeskError("PDF okuyucu sunucuda kurulu değil.", 503) from e
    try:
        # Diske akmış yüklemede dosya tanıtıcısı verilir: okuyucu sayfaları gerektikçe okur, dosyanın tamamı belleğe alınmaz.
        return PdfReader(data.open() if isinstance(data, Incoming) else io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise DeskError("PDF dosyası okunamadı.") from e


def structure_of(filename: str, data: "Blob") -> "structure_mod.Structure":
    """Metnin bölümleri, kitabın kendi yapısından (editorial_desk_structure.py). Parça adlandırması yapı yoksa."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "docx":
        try:
            return structure_mod.docx_structure(data.path if isinstance(data, Incoming) else data)
        except (zipfile.BadZipFile, ValueError, ElementTree.ParseError) as e:
            raise DeskError("DOCX dosyası okunamadı.") from e
    if ext == "pdf":
        return structure_mod.pdf_structure(_pdf_reader(data))
    if ext in ("txt", "md"):
        raw = data.read() if isinstance(data, Incoming) else data
        return structure_mod.text_structure(raw.decode("utf-8-sig", errors="replace"), _HEADING)
    raise DeskError("Metin dosyası DOCX, TXT ya da PDF olmalı.")


def diff_ops(a: str, b: str) -> list[dict[str, str]]:
    """Kelime düzeyinde fark: eşit / silindi / eklendi parçaları, okunacak sırada."""
    ta, tb = re.findall(r"\S+|\s+", a), re.findall(r"\S+|\s+", b)
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=ta, b=tb, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"op": "eq", "text": "".join(ta[i1:i2])})
        else:
            if i2 > i1:
                ops.append({"op": "del", "text": "".join(ta[i1:i2])})
            if j2 > j1:
                ops.append({"op": "ins", "text": "".join(tb[j1:j2])})
    return ops


# ---------------------------------------------------------------------------------------------- erişim

def _members(row: Any) -> list[str]:
    try:
        return [str(m).lower() for m in json.loads(row.members_json or "[]")]
    except ValueError:
        return []


def _work(conn: sa.Connection, tenant: str, work_id: str, user: str, admin: bool) -> Any:
    row = conn.execute(sa.select(WORKS).where(WORKS.c.id == work_id, WORKS.c.tenant_id == tenant)).first()
    if row is None:
        raise DeskError("Eser dosyası bulunamadı.", 404)
    if admin or row.created_by.lower() == user.lower() or user.lower() in _members(row):
        return row
    signer = conn.execute(sa.select(SIGNATURES.c.id).where(SIGNATURES.c.work_id == work_id,
                                                         sa.func.lower(SIGNATURES.c.username) == user.lower())).first()
    if signer is None:
        raise DeskError("Bu eser dosyasına erişiminiz yok.", 403)
    return row


def _latest(conn: sa.Connection, work_id: str, kind: str) -> Any:
    """Etkin (kaldırılmamış) son sürüm."""
    return conn.execute(sa.select(FILES).where(FILES.c.work_id == work_id, FILES.c.kind == kind, FILES.c.removed_at.is_(None))
                        .order_by(FILES.c.version.desc())).first()


def _next_version(conn: sa.Connection, work_id: str, kind: str) -> int:
    """Sürüm numarası kaldırılanlar dahil artar: kaldırılan sürümün dosyası ve adı yerinde kalır, üstüne yazılmaz."""
    top = conn.execute(sa.select(sa.func.max(FILES.c.version)).where(FILES.c.work_id == work_id, FILES.c.kind == kind)).scalar()
    return int(top or 0) + 1


def _store(work_id: str, kind: str, version: int, filename: str, data: Blob) -> str:
    if not _size(data):
        raise DeskError("Dosya boş.")
    ext = re.sub(r"[^a-z0-9]", "", filename.lower().rsplit(".", 1)[-1])[:8] if "." in filename else "bin"
    folder = os.path.join(_root(), work_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{kind}-v{version}.{ext}")
    if isinstance(data, Incoming):
        os.replace(data.path, path)          # aynı disk: kopya yok
        data.path, data.stored = path, True
    else:
        with open(path, "wb") as f:
            f.write(data)
    return path


# ---------------------------------------------------------------------------------------------- eserler

def create_work(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    title = str(body.get("title") or "").strip()
    if not title:
        raise DeskError("Eser adı gerekli.")
    members = sorted({str(m).strip().lower() for m in body.get("members") or [] if str(m).strip()})
    row = {"id": _new(), "tenant_id": tenant, "title": title[:300], "author": (str(body.get("author") or "").strip() or None),
           "crm_project_id": (str(body.get("projectId") or "").strip() or None),
           "crm_project_name": (str(body.get("projectName") or "").strip() or None),
           "isbn": None, "members_json": json.dumps(members), "created_by": user, "created_at": _now()}
    with engine.begin() as conn:
        conn.execute(sa.insert(WORKS).values(**row))
    return {"id": row["id"], "title": row["title"]}


def title_from_filename(filename: str) -> str:
    """Dosya adından okunur eser adı: uzantı düşer, alt çizgi/tire boşluğa döner. Arayüzdeki
    `titleFromFilename` (src/canvas/components/fileDropRules.ts) ile aynı kural."""
    base = re.split(r"[\\/]", str(filename or ""))[-1]
    stem = base[: base.rfind(".")] if "." in base else base
    t = re.sub(r"\s+", " ", re.sub(r"\s+-\s+|-+", " ", re.sub(r"_+", " ", stem))).strip()
    return (t or base.strip())[:300]


def delete_empty_work(engine: sa.engine.Engine, tenant: str, work_id: str) -> None:
    """Dosyadan açılıp yüklemesi başarısız olan eseri geri alır; yalnız hiç dosyası olmayan eser silinir."""
    with engine.begin() as conn:
        if conn.execute(sa.select(FILES.c.id).where(FILES.c.work_id == work_id).limit(1)).first() is not None:
            return
        conn.execute(sa.delete(SIGNATURES).where(SIGNATURES.c.work_id == work_id))
        conn.execute(sa.delete(WORKS).where(WORKS.c.id == work_id, WORKS.c.tenant_id == tenant))
    shutil.rmtree(os.path.join(_root(), work_id), ignore_errors=True)


def create_from_file(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, kind: str,
                     filename: str, data: Blob) -> dict[str, Any]:
    """Tek adımda yeni eser + ilk dosya: eser adı dosya adından gelir (sonra düzeltilir). Yükleme reddedilirse
    (okunamayan metin, PDF olmayan prova, boş dosya) açılan eser geri alınır; yarım kayıt kalmaz."""
    if kind not in ("manuscript", "proof"):
        raise DeskError("Dosya türü manuscript ya da proof olmalı.")
    if not str(filename or "").strip():
        raise DeskError("Dosya adı gerekli.")
    if not _size(data):
        raise DeskError("Dosya boş.")
    work = create_work(engine, tenant, user, {"title": title_from_filename(filename)})
    try:
        fn = upload_manuscript if kind == "manuscript" else upload_proof
        out = fn(engine, tenant, user, admin, work["id"], filename, data)
    except Exception:
        delete_empty_work(engine, tenant, work["id"])
        raise
    return {**out, "workId": work["id"], "title": work["title"]}


def update_work(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, work_id: str, body: dict[str, Any]) -> None:
    with engine.begin() as conn:
        _work(conn, tenant, work_id, user, admin)
        values: dict[str, Any] = {}
        if "isbn" in body:
            values["isbn"] = re.sub(r"[^0-9Xx]", "", str(body.get("isbn") or ""))[:13] or None
        if "members" in body:
            values["members_json"] = json.dumps(sorted({str(m).strip().lower() for m in body.get("members") or [] if str(m).strip()}))
        if "title" in body and str(body["title"]).strip():
            values["title"] = str(body["title"]).strip()[:300]
        if "author" in body:
            values["author"] = str(body.get("author") or "").strip()[:300] or None
        if values:
            conn.execute(sa.update(WORKS).where(WORKS.c.id == work_id).values(**values))
        if "isbn" in values:
            proof = _latest(conn, work_id, "proof")
            if proof is not None:
                _write_auto_checks(conn, work_id, proof, values["isbn"])


def list_works(engine: sa.engine.Engine, tenant: str, user: str, admin: bool,
               title: Optional[str] = None) -> list[dict[str, Any]]:
    """Kişinin gördüğü eserler. `title` verilirse yalnız bu adı taşıyanlar (büyük/küçük harf ve baştaki/sondaki
    boşluk farkı hariç, Python'un kuralıyla); özet (dosya, bölüm, imza okumaları) yalnız onlar için kurulur.
    Kitap 360 bunu kullanır: bütün eserlerin özetini kurup sonra süzmek eser başına dört okuma demekti."""
    wanted = title.strip().lower() if title is not None else None
    with engine.connect() as conn:
        rows = conn.execute(sa.select(WORKS).where(WORKS.c.tenant_id == tenant).order_by(WORKS.c.created_at.desc())).all()
        if wanted is not None:
            rows = [w for w in rows if wanted and (w.title or "").strip().lower() == wanted]
            if not rows:
                return []
        signer_of = {r.work_id for r in conn.execute(sa.select(SIGNATURES.c.work_id).where(
            sa.func.lower(SIGNATURES.c.username) == user.lower())).all()}
        out = []
        for w in rows:
            if not (admin or w.created_by.lower() == user.lower() or user.lower() in _members(w) or w.id in signer_of):
                continue
            out.append(_work_summary(conn, w))
        return out


def _work_summary(conn: sa.Connection, w: Any) -> dict[str, Any]:
    ms, proof = _latest(conn, w.id, "manuscript"), _latest(conn, w.id, "proof")
    chapters = conn.execute(sa.select(CHAPTERS.c.status, sa.func.count()).where(
        CHAPTERS.c.file_id == (ms.id if ms is not None else "")).group_by(CHAPTERS.c.status)).all()
    by = {s: int(n) for s, n in chapters}
    sigs = conn.execute(sa.select(SIGNATURES).where(SIGNATURES.c.work_id == w.id)).all()
    signed = sum(1 for s in sigs if proof is not None and s.file_id == proof.id and s.signed_at is not None)
    return {
        "id": w.id, "title": w.title, "author": w.author, "projectId": w.crm_project_id, "projectName": w.crm_project_name,
        "isbn": w.isbn, "createdBy": w.created_by, "createdAt": _iso(w.created_at), "members": _members(w),
        "manuscript": _file(ms), "proof": _file(proof),
        "chapters": {"total": sum(by.values()), "approved": by.get("onaylandi", 0), "inProgress": by.get("islemde", 0)},
        "signatures": {"total": len(sigs), "signed": signed},
    }


def _file(f: Any) -> Optional[dict[str, Any]]:
    if f is None:
        return None
    return {"id": f.id, "version": f.version, "filename": f.filename, "bytes": int(f.bytes), "sha256": f.sha256,
            "uploadedBy": f.uploaded_by, "uploadedAt": _iso(f.uploaded_at), "report": json.loads(f.report_json or "{}"),
            "removedAt": _iso(f.removed_at), "removedBy": f.removed_by}


# ---------------------------------------------------------------------------------------------- M3

def upload_manuscript(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, work_id: str,
                      filename: str, data: Blob) -> dict[str, Any]:
    if not _size(data):
        raise DeskError("Dosya boş.")
    found = structure_of(filename, data)
    chapters = found.chapters
    if not chapters:
        raise DeskError("Dosyada okunabilir metin bulunamadı.")
    sha = _sha(data)
    with engine.begin() as conn:
        _work(conn, tenant, work_id, user, admin)
        prev = _latest(conn, work_id, "manuscript")
        if prev is not None and prev.sha256 == sha:
            raise DeskError("Bu dosya son sürümle aynı; yeni sürüm açılmadı.", 409)
        version = _next_version(conn, work_id, "manuscript")
        path = _store(work_id, "manuscript", version, filename, data)
        total = metrics("\n".join(body for _, body in chapters))
        file_id = _new()
        conn.execute(sa.insert(FILES).values(
            id=file_id, work_id=work_id, kind="manuscript", version=version, filename=filename[:300], bytes=_size(data),
            sha256=sha, path=path, uploaded_by=user, uploaded_at=_now(),
            report_json=json.dumps({"chapters": len(chapters), "words": total["words"], "atesman": total["atesman"],
                                    **found.report()})))
        for i, (title, body) in enumerate(chapters, 1):
            conn.execute(sa.insert(CHAPTERS).values(id=_new(), work_id=work_id, file_id=file_id, no=i, title=title,
                                                    original=body, current=body, status="bekliyor", review_state="yok"))
    return {"fileId": file_id, "version": version, "chapters": len(chapters), "unit": found.unit, "structure": found.source}


def remove_file(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, file_id: str) -> dict[str, Any]:
    """Yüklenen sürümü kaldırır (ZEKI-45): kayıt, dosya, bölümler ve kararlar iz olarak kalır; etkin sürüm bir
    öncekine döner (yoksa eser «metin yüklenmedi» olur). Prova kaldırılırsa o provaya atılan imzalar düşer."""
    with engine.begin() as conn:
        f = conn.execute(sa.select(FILES).where(FILES.c.id == file_id).with_for_update()).first()
        if f is None:
            raise DeskError("Dosya bulunamadı.", 404)
        _work(conn, tenant, f.work_id, user, admin)
        if f.removed_at is not None:
            raise DeskError("Bu sürüm zaten kaldırılmış.", 409)
        conn.execute(sa.update(FILES).where(FILES.c.id == file_id).values(removed_at=_now(), removed_by=user))
        if f.kind == "proof":
            conn.execute(sa.update(SIGNATURES).where(SIGNATURES.c.file_id == file_id)
                         .values(file_id=None, sha256=None, signed_at=None))
        now = _latest(conn, f.work_id, f.kind)
        return {"workId": f.work_id, "kind": f.kind, "version": f.version, "filename": f.filename,
                "activeVersion": now.version if now is not None else None}


def chapters(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, work_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        w = _work(conn, tenant, work_id, user, admin)
        ms = _latest(conn, work_id, "manuscript")
        rows = conn.execute(sa.select(CHAPTERS).where(CHAPTERS.c.file_id == (ms.id if ms is not None else ""))
                            .order_by(CHAPTERS.c.no)).all()
        counts = {(cid, st): int(n) for cid, st, n in conn.execute(
            sa.select(SUGGESTIONS.c.chapter_id, SUGGESTIONS.c.status, sa.func.count())
            .where(SUGGESTIONS.c.work_id == work_id).group_by(SUGGESTIONS.c.chapter_id, SUGGESTIONS.c.status)).all()}
        items = []
        for c in rows:
            m = metrics(c.current)
            items.append({"id": c.id, "no": c.no, "title": c.title, "status": c.status, "reviewState": c.review_state,
                          "reviewNote": c.review_note, "words": m["words"], "atesman": m["atesman"],
                          "pending": counts.get((c.id, "bekliyor"), 0), "accepted": counts.get((c.id, "kabul"), 0),
                          "rejected": counts.get((c.id, "red"), 0), "changed": c.current != c.original})
        files = conn.execute(sa.select(FILES).where(FILES.c.work_id == work_id, FILES.c.kind == "manuscript")
                             .order_by(FILES.c.version.desc())).all()
        return {"work": _work_summary(conn, w), "chapters": items, "versions": [_file(f) for f in files],
                "activeFileId": ms.id if ms is not None else None}


def chapter(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, chapter_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        c = conn.execute(sa.select(CHAPTERS).where(CHAPTERS.c.id == chapter_id)).first()
        if c is None:
            raise DeskError("Bölüm bulunamadı.", 404)
        _work(conn, tenant, c.work_id, user, admin)
        sugg = conn.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.chapter_id == chapter_id)
                            .order_by(SUGGESTIONS.c.created_at, SUGGESTIONS.c.id)).all()
        m = metrics(c.current)
        m["band"] = atesman_band(m["atesman"])
        return {
            "id": c.id, "workId": c.work_id, "no": c.no, "title": c.title, "status": c.status, "text": c.current,
            "reviewState": c.review_state, "reviewNote": c.review_note, "approvedBy": c.approved_by,
            "approvedAt": _iso(c.approved_at), "metrics": m, "originalMetrics": metrics(c.original),
            "diff": diff_ops(c.original, c.current) if c.current != c.original else [],
            "suggestions": [{"id": s.id, "kind": s.kind, "original": s.original, "suggestion": s.suggestion, "reason": s.reason,
                             "status": s.status, "appliedText": s.applied_text, "decidedBy": s.decided_by,
                             "decidedAt": _iso(s.decided_at)} for s in sugg],
        }


def decide(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, suggestion_id: str, body: dict[str, Any]) -> None:
    decision = str(body.get("decision") or "")
    if decision not in ("kabul", "red"):
        raise DeskError("Karar «kabul» ya da «red» olmalı.")
    with engine.begin() as conn:
        s = conn.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.id == suggestion_id).with_for_update()).first()
        if s is None:
            raise DeskError("Öneri bulunamadı.", 404)
        _work(conn, tenant, s.work_id, user, admin)
        if s.status != "bekliyor":
            raise DeskError("Bu öneri için karar verilmiş.", 409)
        c = conn.execute(sa.select(CHAPTERS).where(CHAPTERS.c.id == s.chapter_id).with_for_update()).first()
        if c.status == "onaylandi":
            raise DeskError("Bölüm onaylı; önce onayı geri alın.", 409)
        applied = None
        if decision == "kabul":
            applied = str(body.get("text") or "").strip() or s.suggestion
            if s.original not in c.current:
                raise DeskError("Özgün ifade metinde artık yok; öneri uygulanamadı.", 409)
            conn.execute(sa.update(CHAPTERS).where(CHAPTERS.c.id == c.id)
                         .values(current=c.current.replace(s.original, applied, 1), status="islemde"))
        elif c.status == "bekliyor":
            conn.execute(sa.update(CHAPTERS).where(CHAPTERS.c.id == c.id).values(status="islemde"))
        conn.execute(sa.update(SUGGESTIONS).where(SUGGESTIONS.c.id == s.id)
                     .values(status=decision, applied_text=applied, decided_by=user, decided_at=_now()))


def set_approval(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, chapter_id: str, approve: bool) -> None:
    with engine.begin() as conn:
        c = conn.execute(sa.select(CHAPTERS).where(CHAPTERS.c.id == chapter_id).with_for_update()).first()
        if c is None:
            raise DeskError("Bölüm bulunamadı.", 404)
        _work(conn, tenant, c.work_id, user, admin)
        if approve:
            pending = conn.execute(sa.select(sa.func.count()).where(SUGGESTIONS.c.chapter_id == chapter_id,
                                                                   SUGGESTIONS.c.status == "bekliyor")).scalar_one()
            if pending:
                raise DeskError(f"{pending} öneri karar bekliyor; bölüm onaylanamaz.", 409)
            conn.execute(sa.update(CHAPTERS).where(CHAPTERS.c.id == chapter_id)
                         .values(status="onaylandi", approved_by=user, approved_at=_now()))
        else:
            conn.execute(sa.update(CHAPTERS).where(CHAPTERS.c.id == chapter_id)
                         .values(status="islemde", approved_by=None, approved_at=None))


REVIEW_SYSTEM = (
    "Türkçe yayın editörüsün. Sana bir kitap bölümünden bir parça verilecek. Yalnız gerçek sorunları bildir: "
    "TDK yazım ve noktalama hataları (tur: yazim) ile anlatımı bozan üslup sorunları — gereksiz tekrar, anlatım "
    "bozukluğu, hedef okura göre ağır ya da bürokratik ifade (tur: uslup). Doğru olan yere dokunma; yazarın "
    "sesini değiştirme. Cevabın yalnız bir JSON dizisi olsun, başka hiçbir şey yazma. Her öğe: "
    '{"tur": "yazim" | "uslup", "ozgun": "<metinden birebir kopyalanmış, en çok 25 kelimelik ifade>", '
    '"oneri": "<yerine yazılacak ifade>", "gerekce": "<bir cümle>"}. '
    "«ozgun» metinde harfi harfine geçmeli. Sorun yoksa [] döndür."
)


def _chunks(text: str, words: int = 900) -> list[str]:
    out, cur, n = [], [], 0
    for p in text.split("\n"):
        k = len(p.split())
        if cur and n + k > words:
            out.append("\n".join(cur))
            cur, n = [], 0
        cur.append(p)
        n += k
    if cur:
        out.append("\n".join(cur))
    return out


def _parse_suggestions(answer: str) -> list[dict[str, str]]:
    m = re.search(r"\[.*\]", answer or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict)]


def start_review(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, chapter_id: str,
                 chat: Optional[Callable[[list[dict[str, str]]], str]]) -> None:
    """Bölümü modele okutur; arka planda çalışır, durum bölüm kaydına yazılır."""
    if chat is None:
        raise DeskError("Model bağlantısı tanımlı değil.", 503)
    with engine.begin() as conn:
        c = conn.execute(sa.select(CHAPTERS).where(CHAPTERS.c.id == chapter_id).with_for_update()).first()
        if c is None:
            raise DeskError("Bölüm bulunamadı.", 404)
        _work(conn, tenant, c.work_id, user, admin)
        if c.status == "onaylandi":
            raise DeskError("Bölüm onaylı; önce onayı geri alın.", 409)
        if c.review_state == "calisiyor":
            raise DeskError("Bu bölüm şu an denetleniyor.", 409)
        conn.execute(sa.update(CHAPTERS).where(CHAPTERS.c.id == chapter_id).values(review_state="calisiyor", review_note=None))
        text, work_id = c.current, c.work_id

    def run() -> None:
        found, skipped, state, note = 0, 0, "bitti", None
        try:
            seen: set[tuple[str, str]] = set()
            for part in _chunks(text):
                for d in _parse_suggestions(chat([{"role": "system", "content": REVIEW_SYSTEM}, {"role": "user", "content": part}])):
                    orig, new = str(d.get("ozgun") or "").strip(), str(d.get("oneri") or "").strip()
                    # Kanıt kuralı: özgün ifade metinde birebir yoksa öneri yazılmaz.
                    if not orig or not new or orig == new or orig not in text or (orig, new) in seen:
                        skipped += 1
                        continue
                    seen.add((orig, new))
                    with engine.begin() as conn:
                        dup = conn.execute(sa.select(SUGGESTIONS.c.id).where(
                            SUGGESTIONS.c.chapter_id == chapter_id, SUGGESTIONS.c.original == orig,
                            SUGGESTIONS.c.suggestion == new)).first()
                        if dup is None:
                            conn.execute(sa.insert(SUGGESTIONS).values(
                                id=_new(), work_id=work_id, chapter_id=chapter_id,
                                kind="yazim" if str(d.get("tur")) == "yazim" else "uslup", original=orig, suggestion=new,
                                reason=str(d.get("gerekce") or "").strip()[:1000] or None, status="bekliyor", created_at=_now()))
                            found += 1
            note = f"{found} yeni öneri" + (f", {skipped} öneri metinde doğrulanamadığı için atıldı" if skipped else "")
        except Exception as e:  # noqa: BLE001
            log.exception("editorial review failed")
            state, note = "hata", str(e)[:480]
        with engine.begin() as conn:
            conn.execute(sa.update(CHAPTERS).where(CHAPTERS.c.id == chapter_id).values(review_state=state, review_note=note))

    threading.Thread(target=run, name=f"editorial-review-{chapter_id[:8]}", daemon=True).start()


def reset_stale_reviews(engine: sa.engine.Engine) -> None:
    """Servis yeniden başladıysa yarıda kalan denetim 'çalışıyor' diye asılı kalmasın."""
    with engine.begin() as conn:
        conn.execute(sa.update(CHAPTERS).where(CHAPTERS.c.review_state == "calisiyor")
                     .values(review_state="hata", review_note="Servis yeniden başladı; denetimi yeniden başlatın."))


# ---------------------------------------------------------------------------------------------- M5

def isbn13_ok(isbn: str) -> bool:
    d = re.sub(r"[^0-9]", "", isbn or "")
    return len(d) == 13 and (10 - sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(d[:12])) % 10) % 10 == int(d[12])


def preflight(data: Blob) -> dict[str, Any]:
    """PDF'ten okunabilen baskı öncesi gerçekler. Ölçülemeyen şey (yerleşik DPI, taşma, yetim satır) raporlanmaz."""
    reader = _pdf_reader(data)
    sizes: dict[str, int] = {}
    fonts, unembedded, images, rgb_images, text_hashes, isbns = set(), set(), 0, 0, [], set()
    trim_missing = 0
    for page in reader.pages:
        box = page.trimbox if "/TrimBox" in page else page.mediabox
        if "/TrimBox" not in page:
            trim_missing += 1
        w, h = float(box.width) / 72 * 25.4, float(box.height) / 72 * 25.4
        key = f"{w:.1f} × {h:.1f} mm"
        sizes[key] = sizes.get(key, 0) + 1
        res = page.get("/Resources") or {}
        for name, ref in (res.get("/Font") or {}).items():
            try:
                f = ref.get_object()
                base = str(f.get("/BaseFont") or name).lstrip("/")
                fonts.add(base)
                desc = f.get("/FontDescriptor")
                if desc is None and "/DescendantFonts" in f:
                    desc = f["/DescendantFonts"][0].get_object().get("/FontDescriptor")
                d = desc.get_object() if desc is not None else {}
                if not any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3")) and f.get("/Subtype") != "/Type3":
                    unembedded.add(base)
            except Exception:  # noqa: BLE001
                continue
        for ref in (res.get("/XObject") or {}).values():
            try:
                x = ref.get_object()
                if x.get("/Subtype") == "/Image":
                    images += 1
                    cs = x.get("/ColorSpace")
                    cs_name = str(cs[0] if isinstance(cs, list) else cs)
                    if "RGB" in cs_name:
                        rgb_images += 1
            except Exception:  # noqa: BLE001
                continue
        text = page.extract_text() or ""
        text_hashes.append(hashlib.sha1(re.sub(r"\s+", " ", text).strip().encode()).hexdigest())
        for m in re.finditer(r"97[89][\d\- ]{9,16}\d", text):   # 978 + 9 ara + 1 = 13 hane
            digits = re.sub(r"[^0-9]", "", m.group(0))
            if len(digits) == 13:
                isbns.add(digits)
    n = len(reader.pages)
    return {"pages": n, "sizes": sizes, "trimBoxMissing": trim_missing, "fonts": sorted(fonts), "unembeddedFonts": sorted(unembedded),
            "images": images, "rgbImages": rgb_images, "isbnsInText": sorted(isbns), "pageHashes": text_hashes,
            "signatures16": round(n / 16, 2), "fullSignatures": n % 16 == 0}


def _auto_checks(report: dict[str, Any], isbn: Optional[str]) -> list[tuple[str, str, Optional[bool], str]]:
    sizes = report.get("sizes") or {}
    out = [
        ("size", "Bütün sayfalar aynı ebatta", len(sizes) == 1, ", ".join(f"{k}: {v} sayfa" for k, v in sizes.items())),
        ("fonts", "Bütün yazı tipleri gömülü", not report.get("unembeddedFonts"),
         "Gömülü olmayan: " + ", ".join(report.get("unembeddedFonts") or []) if report.get("unembeddedFonts")
         else f"{len(report.get('fonts') or [])} yazı tipi gömülü"),
        ("rgb", "RGB görsel yok", not report.get("rgbImages"),
         f"{report.get('images', 0)} görselin {report.get('rgbImages', 0)} tanesi RGB"),
        ("signatures", "Sayfa sayısı 16'lık formaya tam bölünüyor", bool(report.get("fullSignatures")),
         f"{report.get('pages')} sayfa = {report.get('signatures16')} forma"),
    ]
    if isbn:
        found = report.get("isbnsInText") or []
        out.append(("isbn", "ISBN sağlaması doğru", isbn13_ok(isbn), f"ISBN {isbn}"))
        out.append(("isbn_text", "ISBN prova metninde geçiyor", isbn in found,
                    "Metinde bulunan: " + (", ".join(found) if found else "yok")))
    else:
        out.append(("isbn", "ISBN sağlaması doğru", None, "Eser kartına ISBN girilmedi"))
    return out


def _write_auto_checks(conn: sa.Connection, work_id: str, proof: Any, isbn: Optional[str]) -> None:
    conn.execute(sa.delete(CHECKS).where(CHECKS.c.file_id == proof.id, CHECKS.c.auto.is_(True)))
    for key, label, passed, evidence in _auto_checks(json.loads(proof.report_json or "{}"), isbn):
        conn.execute(sa.insert(CHECKS).values(id=_new(), work_id=work_id, file_id=proof.id, key=key, label=label, auto=True,
                                              passed=passed, evidence=evidence))


def upload_proof(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, work_id: str, filename: str, data: Blob) -> dict[str, Any]:
    if not filename.lower().endswith(".pdf"):
        raise DeskError("Prova dosyası PDF olmalı.")
    if not _size(data):
        raise DeskError("Dosya boş.")
    report = preflight(data)
    sha = _sha(data)
    with engine.begin() as conn:
        w = _work(conn, tenant, work_id, user, admin)
        prev = _latest(conn, work_id, "proof")
        if prev is not None and prev.sha256 == sha:
            raise DeskError("Bu dosya son provayla aynı; yeni sürüm açılmadı.", 409)
        version = _next_version(conn, work_id, "proof")
        path = _store(work_id, "proof", version, filename, data)
        if prev is not None:
            old = json.loads(prev.report_json or "{}")
            a, b = old.get("pageHashes") or [], report["pageHashes"]
            report["versus"] = {"version": prev.version, "pageDelta": report["pages"] - int(old.get("pages") or 0),
                                "changedPages": [i + 1 for i in range(min(len(a), len(b))) if a[i] != b[i]]}
        file_id = _new()
        conn.execute(sa.insert(FILES).values(id=file_id, work_id=work_id, kind="proof", version=version, filename=filename[:300],
                                             bytes=_size(data), sha256=sha, path=path, report_json=json.dumps(report),
                                             uploaded_by=user, uploaded_at=_now()))
        proof = conn.execute(sa.select(FILES).where(FILES.c.id == file_id)).first()
        _write_auto_checks(conn, work_id, proof, w.isbn)
        for key, label in MANUAL_CHECKS:
            conn.execute(sa.insert(CHECKS).values(id=_new(), work_id=work_id, file_id=file_id, key=key, label=label, auto=False))
        # Yeni prova: imzalar bu dosya için yeniden beklenir.
        conn.execute(sa.update(SIGNATURES).where(SIGNATURES.c.work_id == work_id).values(file_id=None, sha256=None, signed_at=None))
    return {"fileId": file_id, "version": version, "pages": report["pages"]}


def proof_state(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, work_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        w = _work(conn, tenant, work_id, user, admin)
        files = conn.execute(sa.select(FILES).where(FILES.c.work_id == work_id, FILES.c.kind == "proof")
                             .order_by(FILES.c.version.desc())).all()
        proof = next((f for f in files if f.removed_at is None), None)
        checks = conn.execute(sa.select(CHECKS).where(CHECKS.c.file_id == (proof.id if proof is not None else ""))
                              .order_by(CHECKS.c.auto.desc(), CHECKS.c.label)).all()
        sigs = conn.execute(sa.select(SIGNATURES).where(SIGNATURES.c.work_id == work_id).order_by(SIGNATURES.c.role)).all()
        versions = []
        for f in files:
            if f.removed_at is not None:
                continue        # son okuma ekranı versions[0]'ı etkin prova sayar; kaldırılan sürüm listelenmez
            item = _file(f)
            item["report"].pop("pageHashes", None)
            versions.append(item)
        failed = [c for c in checks if c.passed is False]
        open_ = [c for c in checks if c.passed is None]
        signed = [s for s in sigs if proof is not None and s.file_id == proof.id and s.signed_at is not None]
        return {
            "work": _work_summary(conn, w), "versions": versions,
            "checks": [{"id": c.id, "key": c.key, "label": c.label, "auto": bool(c.auto), "passed": c.passed,
                        "evidence": c.evidence, "checkedBy": c.checked_by, "checkedAt": _iso(c.checked_at)} for c in checks],
            "signatures": [{"id": s.id, "role": s.role, "username": s.username, "display": s.display,
                            "signedAt": _iso(s.signed_at) if proof is not None and s.file_id == proof.id else None,
                            "sha256": s.sha256 if proof is not None and s.file_id == proof.id else None,
                            "mine": s.username.lower() == user.lower()} for s in sigs],
            "approved": bool(proof is not None and sigs and len(signed) == len(sigs) and not failed and not open_),
            "blocking": {"failed": len(failed), "open": len(open_), "unsigned": len(sigs) - len(signed)},
        }


def set_check(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, check_id: str, body: dict[str, Any]) -> None:
    with engine.begin() as conn:
        c = conn.execute(sa.select(CHECKS).where(CHECKS.c.id == check_id).with_for_update()).first()
        if c is None:
            raise DeskError("Kontrol maddesi bulunamadı.", 404)
        _work(conn, tenant, c.work_id, user, admin)
        if c.auto:
            raise DeskError("Bu madde dosyadan otomatik ölçülür; elle değiştirilemez.", 409)
        passed = body.get("passed")
        if passed not in (True, False, None):
            raise DeskError("Geçersiz değer.")
        conn.execute(sa.update(CHECKS).where(CHECKS.c.id == check_id).values(
            passed=passed, evidence=str(body.get("note") or "").strip()[:1000] or None,
            checked_by=None if passed is None else user, checked_at=None if passed is None else _now()))


def set_signers(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, work_id: str, signers: list[dict[str, Any]]) -> None:
    clean = []
    for s in signers:
        role, username = str(s.get("role") or "").strip()[:80], str(s.get("username") or "").strip().lower()[:120]
        if role and username:
            clean.append((role, username, str(s.get("display") or "").strip()[:200] or None))
    if len({(r, u) for r, u, _ in clean}) != len(clean):
        raise DeskError("Aynı kişi aynı rolle iki kez yazılamaz.")
    with engine.begin() as conn:
        w = _work(conn, tenant, work_id, user, admin)
        if not (admin or w.created_by.lower() == user.lower()):
            raise DeskError("İmzacıları yalnız eseri açan kişi ya da yönetici belirler.", 403)
        old = {(s.role, s.username.lower()): s for s in conn.execute(sa.select(SIGNATURES).where(SIGNATURES.c.work_id == work_id)).all()}
        keep = set()
        for role, username, display in clean:
            keep.add((role, username))
            if (role, username) not in old:
                conn.execute(sa.insert(SIGNATURES).values(id=_new(), work_id=work_id, role=role, username=username, display=display))
        for key, s in old.items():
            if key not in keep:
                conn.execute(sa.delete(SIGNATURES).where(SIGNATURES.c.id == s.id))


def sign(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, work_id: str) -> dict[str, Any]:
    with engine.begin() as conn:
        _work(conn, tenant, work_id, user, admin)
        proof = _latest(conn, work_id, "proof")
        if proof is None:
            raise DeskError("İmzalanacak prova yok.", 409)
        mine = conn.execute(sa.select(SIGNATURES).where(SIGNATURES.c.work_id == work_id,
                                                        sa.func.lower(SIGNATURES.c.username) == user.lower()).with_for_update()).all()
        if not mine:
            raise DeskError("Bu eserde imzacı değilsiniz.", 403)
        failed = conn.execute(sa.select(sa.func.count()).where(CHECKS.c.file_id == proof.id, CHECKS.c.passed.is_(False))).scalar_one()
        if failed:
            raise DeskError(f"{failed} kontrol maddesi başarısız; prova imzalanamaz.", 409)
        conn.execute(sa.update(SIGNATURES).where(SIGNATURES.c.id.in_([s.id for s in mine]))
                     .values(file_id=proof.id, sha256=proof.sha256, signed_at=_now()))
        return {"sha256": proof.sha256, "version": proof.version}


def file_path(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, file_id: str) -> tuple[str, str]:
    with engine.connect() as conn:
        f = conn.execute(sa.select(FILES).where(FILES.c.id == file_id)).first()
        if f is None:
            raise DeskError("Dosya bulunamadı.", 404)
        _work(conn, tenant, f.work_id, user, admin)
        if not os.path.isfile(f.path):
            raise DeskError("Dosya diskte bulunamadı.", 410)
        return f.path, f.filename
