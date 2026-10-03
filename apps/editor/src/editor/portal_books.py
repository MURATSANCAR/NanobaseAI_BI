"""Portaldan kitap okutma: editörün yüklediği PDF gelen kutusuna yazılır ve okuma kuyruğuna girer.

Okuma, `editorctl analyze` ile aynı iştir (BookFullAnalysis); yalnız dosya kabuğa değil portala yüklenir ve iş
hemen başlamaz: `analysis_job` satırı QUEUED ve iş akışı kimliksiz açılır, `consume` (editor-book-queue servisi)
GPU'da boş okuma yeri varsa sıradaki kitabı başlatır. Aynı anda en çok `EDITOR_READ_PARALLEL` kitap okunur
(varsayılan 2, kullanıcı kararı 2026-10-01: GPU 1'de iki kitap; BI'ın GPU 0'ına dokunulmaz); toplu yükleme sırayı
bekler. İki okuma farklı model isterse model kapısı (gateway) kullanımdaki modeli kapatmaz, ikinci istek bekler.
Aynı dosya (içerik özeti) daha önce okunduysa yeni kitap açılmaz, var olan kayıt döner. İsteyen, `requested_by`
alanında `portal:<AD kullanıcısı>` olarak durur; liste bu önekle süzülür.

Kendini onarma: okuması düşen kitap `EDITOR_READ_ATTEMPTS` (varsayılan 3) denemeye kadar kendiliğinden yeniden
kuyruğa girer (yeni iş satırı, `progress.attempt`); iş akışı kapanmış ama iş RUNNING kalmışsa (işçi öldü) iş
düşmüş sayılır ve aynı yoldan yeniden denenir. Kuyruk takılmaz. Denemeler bitince kitap «okunamadı» kalır; kişi
portaldan «Yeniden okut» ile (`reread`) aynı sürüm için yeni iş açar: deneme sayacı baştan, isteyen o kişi.

Ekrana adım adı değil aşama gider: iş akışının adım etiketleri teknik ad taşır (OCR, manifest), aşama adı taşımaz.
Hata metni de ekrana gitmez.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import unicodedata
import uuid
from pathlib import Path
from typing import BinaryIO

PREFIX = "portal:"
ATTEMPTS = max(1, int(os.environ.get("EDITOR_READ_ATTEMPTS", "3") or 3))
PARALLEL = max(1, int(os.environ.get("EDITOR_READ_PARALLEL", "2") or 2))
POLL_SEC = 15.0
STEPS = 15
PDF_MAGIC = b"%PDF"

#: Adım numarası (iş akışının «n/15 etiket» biçimi) → ekranda görünen aşama.
PHASES = ((2, "Hazırlanıyor"), (4, "Metin okunuyor"), (6, "Resimler inceleniyor"),
          (9, "Karakterler ve olaylar çıkarılıyor"), (10, "Duygu, tema ve son okuma"), (STEPS, "Özet ve künye hazırlanıyor"))

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


class UploadError(ValueError):
    """Dosyanın kendisiyle ilgili, editöre olduğu gibi gösterilecek hata."""


def slug(name: str) -> str:
    """Gelen kutusu dosya adı: Türkçe harfler sadeleşir, küçük harf, tire; boşsa «kitap»."""
    t = unicodedata.normalize("NFKD", (name or "").translate(_TR))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80].strip("-") or "kitap"


def title_of(given: str, filename: str) -> str:
    """Kitabın adı: editör yazdıysa o (olduğu gibi); yoksa temizlenmiş dosya adı (editor.book_title: baştaki sıra
    numarası, ölçü, baskı eki atılır, Türkçe başlık yazımı). Okuma bitince site ve künyeyle yeniden çözülür."""
    t = re.sub(r"\s+", " ", given or "").strip()
    if t:
        return t[:300]
    from . import book_title
    return book_title.from_file(Path(filename or "").name or "kitap.pdf")["title"]


def phase(step: str | None, status: str) -> dict:
    """«7/15 Karakter ve olay adayları» → {'n': 7, 'of': 15, 'label': 'Karakterler ve olaylar çıkarılıyor'}."""
    if status == "SUCCEEDED":
        return {"n": STEPS, "of": STEPS, "label": "Hazır"}
    if status == "QUEUED" or not step:
        return {"n": 0, "of": STEPS, "label": "Sırada"}
    m = re.match(r"\s*(\d+)\s*/", step)
    n = min(int(m.group(1)), STEPS) if m else 0
    label = next((lab for last, lab in PHASES if n <= last), PHASES[-1][1])
    return {"n": n, "of": STEPS, "label": label}


def save(src: BinaryIO, inbox: Path, filename: str, title: str) -> tuple[str, int]:
    """Yüklemeyi gelen kutusuna yazar: önce geçici ada, doğrulanınca asıl ada. Aynı adda farklı içerik varsa
    ad «-2», «-3» alır; aynı içerik varsa var olan dosya kullanılır. Döner: (dosya adı, bayt)."""
    if Path(filename or "").suffix.lower() != ".pdf":
        raise UploadError("Yalnız PDF okutulabilir.")
    inbox.mkdir(parents=True, exist_ok=True)
    base = slug(title if title.strip() else Path(filename).stem)
    tmp = inbox / f".yukleniyor-{uuid.uuid4().hex}.part"   # .pdf değil: kuyruk komutu yarım dosyayı görmez
    digest = hashlib.sha256()
    size = 0
    try:
        with tmp.open("wb") as out:
            head = src.read(len(PDF_MAGIC))
            if head != PDF_MAGIC:
                raise UploadError("Dosyanın içeriği PDF değil." if head else "Dosya boş.")
            out.write(head)
            digest.update(head)
            size += len(head)
            while chunk := src.read(1 << 20):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        sha = digest.hexdigest()
        for n in range(1, 1000):
            name = f"{base}.pdf" if n == 1 else f"{base}-{n}.pdf"
            dest = inbox / name
            if not dest.exists():
                shutil.move(str(tmp), dest)
                return name, size
            if _sha(dest) == sha:
                return name, size
        raise UploadError("Gelen kutusunda bu adda çok fazla dosya var; kitaba başka bir ad verin.")
    finally:
        tmp.unlink(missing_ok=True)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ kuyruk (veritabanı + iş akışı)
#: Portaldan seçilebilen okuma kipleri: tam okuma (son okuma dahil) ya da Kitap Eczanesi'nin arşiv kipi.
PROFILES = ("full", "archive")


def job_settings(profile: str, category: str) -> tuple[str, dict]:
    """(kip, işin `progress` başlangıcı). Arşiv kipinde kategori klasörünün okur kitlesi ipucu işe yazılır (toplu
    kuyrukla aynı biçim: `progress.archive`); tanınmayan ya da boş kategoride ipucu boş kalır, okur kitlesini kitabın
    metni belirler. Geçersiz kip `UploadError` (köprü 422 olarak kişiye gösterir)."""
    profile = (profile or "full").strip().lower()
    if profile not in PROFILES:
        raise UploadError("Okuma kipi geçersiz.")
    progress: dict = {"attempt": 1}
    if profile == "archive":
        from . import archive
        cat = (category or "").strip().strip("/")
        hint = archive.hint_for(cat) if cat in archive.CATEGORIES else {**archive.hint_for(""), "category": None}
        progress["archive"] = {**hint, "source": "portal"}
    return profile, progress


def enqueue(file_name: str, title: str, who: str, profile: str = "full", category: str = "",
            given: str | None = None, original_name: str | None = None) -> dict:
    """Kitabı kaydeder (içerik sürümü) ve sıraya koyar. Aynı sürüm okunmuş, sırada ya da okunuyorsa yeni iş
    açılmaz: {'job_id', 'already': 'SUCCEEDED'|'QUEUED'|'RUNNING'|None}. `profile='archive'` (Kitap Eczanesi):
    kitap «Zeki'ye sor» için okunur; son okuma adımları kitap redaksiyona açılınca koşar (editor.archive).
    `given`: kişinin yazdığı ad (varsa kaynak «user», hiçbir otomatik çözüm ezmez); `original_name`: yüklenen
    dosyanın özgün adı (adın kaynağı «file» olarak kaydedilir). İkisi de verilmezse (eski çağıran) ad kaynağı
    yazılmaz ve aynı adlı kitap varsa sürüm ona eklenir (önceki davranış)."""
    from . import book_title, db, document
    profile, progress = job_settings(profile, category)
    provenance = given is not None or original_name is not None
    # Dosya adından gelen ad başka bir kitabın adıyla çakışabilir («Cezeri»): o zaman kitaplar birleşmez.
    info = document.inspect_book(file_name, title=title,
                                 merge_by_title=not provenance or bool((given or "").strip()))
    if provenance:
        with db.tx() as c:
            book_title.set_on_intake(c, info["book_id"], given, original_name or file_name)
    bv = info["book_version_id"]
    row = db.one("SELECT id, status FROM analysis_job WHERE book_version_id=%s AND status IN"
                 " ('QUEUED','RUNNING','SUCCEEDED') ORDER BY created_at DESC LIMIT 1", bv)
    if row:
        return {"job_id": str(row["id"]), "already": row["status"]}
    job = db.one("INSERT INTO analysis_job(book_version_id, profile, requested_by, progress) VALUES (%s,%s,%s,%s)"
                 " RETURNING id", bv, profile, PREFIX + who[:200], db.J(progress))
    return {"job_id": str(job["id"]), "already": None}


#: Kuyruk sırası: arşivin toplu okuması (editor.archive, `arsiv:` önekli binlerce kitap) portaldan gelen kitabı
#: bekletmez. Kitap Eczanesi'nden arşiv kipinde yüklenen kitap da portal kitabıdır, toplu kuyruğun önüne geçer.
QUEUE_ORDER = "(requested_by LIKE 'arsiv:%%'), created_at, id"
#: İşin profil dışında taşıdığı, yeniden denemede aynen geçen alanlar (arşiv ipucu, redaksiyonun nesli).
CARRIED = ("archive", "generation_id", "from_profile")


def retry_failed() -> int:
    """Portaldan (ya da arşiv toplu kuyruğundan) gelen ve düşen kitabın son işi deneme hakkı kaldıysa aynı sürüm
    için yeni iş sıraya girer; işin kipi (profile) ve kipin bilgisi aynen geçer."""
    from . import archive, db
    rows = db.all_rows(
        "SELECT j.id, j.book_version_id, j.requested_by, j.profile, j.progress,"
        " coalesce((j.progress->>'attempt')::int, 1) AS attempt"
        " FROM analysis_job j WHERE j.status='FAILED' AND (j.requested_by LIKE %s OR j.requested_by LIKE %s)"
        " AND NOT EXISTS (SELECT 1 FROM analysis_job k WHERE k.book_version_id=j.book_version_id AND k.created_at>j.created_at)"
        " AND coalesce((j.progress->>'attempt')::int, 1) < %s", PREFIX + "%", archive.PREFIX + "%", ATTEMPTS)
    for r in rows:
        kept = {k: v for k, v in (r.get("progress") or {}).items() if k in CARRIED}
        db.one("INSERT INTO analysis_job(book_version_id, profile, requested_by, progress) VALUES (%s,%s,%s,%s)"
               " RETURNING id", r["book_version_id"], r.get("profile") or "full", r["requested_by"],
               db.J({**kept, "attempt": r["attempt"] + 1, "retry_of": str(r["id"])}))
    return len(rows)


class RereadRefused(ValueError):
    """Elle yeniden okuma açılamaz (iş sürüyor ya da okuma düşmüş değil); köprü 409 olarak kişiye gösterir."""


#: Elle yeniden okumada iş hiç açılmamışsa (aynı sürümde süren iş yoksa) eklenir; tek SQL cümlesi: iki tık aynı
#: anda gelse de ikinci cümle birincinin işini görür ve satır eklemez (aynı işlemde değil, ama aralık milisaniye).
_REREAD_SQL = ("INSERT INTO analysis_job(book_version_id, profile, requested_by, progress)"
               " SELECT %s, %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM analysis_job"
               " WHERE book_version_id=%s AND status IN ('QUEUED','RUNNING')) RETURNING id")


def reread(job_id: str, who: str) -> dict:
    """Okuması düşmüş kitabı elle yeniden sıraya koyar. `job_id`: ekrandaki satırın işi (kitap sürümünün herhangi
    bir işi olabilir; kararı o sürümün o kipteki SON işi verir). Son iş FAILED olmalı; sürümde QUEUED/RUNNING iş varsa
    çift iş açılmaz (`RereadRefused`). Yeni iş aynı kipte (tam okuma ya da arşiv), korunan alanlar (`CARRIED`)
    `retry_failed`'deki gibi aynen geçer; deneme sayacı 1'den başlar (kendini onarma yeniden çalışır), isteyen
    `portal:<kişi>` (portal kitabı olarak toplu arşiv kuyruğunun önüne geçer). İş yoksa `LookupError`.
    Döner: {'job_id', 'retry_of'}."""
    from . import db
    who = (who or "").strip()
    if not who:
        raise ValueError("Yeniden okutan kişi eksik.")
    r = db.one("SELECT book_version_id, profile FROM analysis_job WHERE id=%s", job_id)
    if not r:
        raise LookupError("job not found")
    bv, profile = r["book_version_id"], r.get("profile") or "full"
    if profile not in PROFILES:
        raise RereadRefused("Bu iş yeniden okutulamaz.")
    if db.one("SELECT 1 AS x FROM analysis_job WHERE book_version_id=%s AND status IN ('QUEUED','RUNNING') LIMIT 1", bv):
        raise RereadRefused("Kitap zaten sırada ya da okunuyor.")
    last = db.one("SELECT id, status, progress FROM analysis_job WHERE book_version_id=%s AND profile=%s"
                  " ORDER BY created_at DESC, id DESC LIMIT 1", bv, profile)
    if not last or last["status"] != "FAILED":
        raise RereadRefused("Kitabın okuması düşmüş değil; yeniden okutulacak bir şey yok.")
    kept = {k: v for k, v in (last.get("progress") or {}).items() if k in CARRIED}
    progress = {**kept, "attempt": 1, "retry_of": str(last["id"]), "manual_retry": True}
    job = db.one(_REREAD_SQL, bv, profile, PREFIX + who[:200], db.J(progress), bv)
    if not job:
        raise RereadRefused("Kitap zaten sırada ya da okunuyor.")
    return {"job_id": str(job["id"]), "retry_of": str(last["id"])}


async def reap() -> int:
    """İş akışı kapanmış (ya da hiç yok) ama işi QUEUED/RUNNING kalan satırları düşmüş sayar; kuyruk takılmaz."""
    from temporalio.client import WorkflowExecutionStatus
    from temporalio.service import RPCError
    from . import db, jobs
    client = await jobs.temporal()
    n = 0
    for r in db.all_rows("SELECT id, workflow_id FROM analysis_job WHERE status IN ('QUEUED','RUNNING')"
                         " AND workflow_id IS NOT NULL"):
        try:
            desc = await client.get_workflow_handle(r["workflow_id"]).describe()
            if desc.status == WorkflowExecutionStatus.RUNNING:
                continue
        except RPCError:
            pass  # iş akışı Temporal'da yok
        db.one("UPDATE analysis_job SET status='FAILED', finished_at=now(), error=coalesce(error,'iş akışı yarıda kaldı')"
               " WHERE id=%s AND status IN ('QUEUED','RUNNING') RETURNING id", r["id"])
        n += 1
    return n


async def dispatch_once() -> str | None:
    """Okuma yeri boşsa (süren okuma < PARALLEL) sıradaki (en eski) kitabın iş akışını başlatır; turda en çok bir
    kitap başlar. Başlatılan işin kimliği ya da None."""
    from temporalio.exceptions import WorkflowAlreadyStartedError
    from . import db, foundation, jobs
    from .config import settings
    await reap()
    retry_failed()
    if busy_count() >= PARALLEL:
        return None
    try:
        foundation.assert_enabled()
    except RuntimeError:
        return None  # bakım: kuyruk bekler
    nxt = db.one("SELECT id FROM analysis_job WHERE status='QUEUED' AND workflow_id IS NULL ORDER BY "
                 + QUEUE_ORDER + " LIMIT 1")
    if not nxt:
        return None
    job_id = str(nxt["id"])
    wf_id = f"book-analysis-{job_id}"
    try:
        await (await jobs.temporal()).start_workflow(jobs.WORKFLOW, job_id, id=wf_id, task_queue=settings().task_queue)
    except WorkflowAlreadyStartedError:
        pass  # önceki tur başlatmış, kimlik yazılamamıştı
    db.one("UPDATE analysis_job SET workflow_id=%s WHERE id=%s RETURNING id", wf_id, job_id)
    return job_id


def busy_count() -> int:
    """Süren okuma: iş akışı başlamış (RUNNING ya da kimliği yazılmış QUEUED) işler."""
    from . import db
    return db.one("SELECT count(*) AS n FROM analysis_job WHERE status='RUNNING' OR (status='QUEUED' AND workflow_id IS NOT NULL)")["n"]


async def consume(poll_sec: float = POLL_SEC) -> None:
    """Kuyruk servisi: her turda düşeni yeniden sıraya koyar, boşsa sıradakini başlatır. Hata turu atlar, servis durmaz."""
    while True:
        try:
            started = await dispatch_once()
            if started:
                print(f"okuma başladı {started}", flush=True)
        except Exception as e:  # noqa: BLE001 — veritabanı/Temporal geçici olarak yoksa bir sonraki tur dener
            print(f"kuyruk turu atlandı: {e}", flush=True)
        await asyncio.sleep(poll_sec)


def listing(requested_by: str = "") -> list[dict]:
    """Portaldan okutulan kitaplar: kitap sürümü başına son iş (yeniden denemeler tek satır), ilk gönderim sırasıyla
    yeniden eskiye. `requested_by` verilirse o kişinin okuttuğu sürümler; satır sürümün son portal işidir (kitabı
    başkası elle yeniden okuttuysa kişi yine kendi kitabının güncel durumunu görür). Sırada bekleyenin önünde kaç kitap olduğu bütün kuyruğa göre (başka kaynaktan gelen işler dahil)."""
    from . import db
    who = requested_by.strip()
    rows = db.all_rows(
        "SELECT DISTINCT ON (j.book_version_id) j.id, j.status, j.step, j.workflow_id, j.requested_by, j.created_at,"
        " j.finished_at, coalesce((j.progress->>'attempt')::int, 1) AS attempt, j.progress->>'hold' AS hold, b.title, bv.page_count,"
        " min(j.created_at) OVER (PARTITION BY j.book_version_id) AS submitted_at"
        " FROM analysis_job j JOIN book_version bv ON bv.id=j.book_version_id JOIN book b ON b.id=bv.book_id"
        " WHERE j.requested_by LIKE %s" +
        (" AND j.book_version_id IN (SELECT book_version_id FROM analysis_job WHERE requested_by = %s)" if who else "") +
        " ORDER BY j.book_version_id, j.created_at DESC", PREFIX + "%", *((PREFIX + who,) if who else ()))
    waiting = [str(r["id"]) for r in db.all_rows(
        "SELECT id FROM analysis_job WHERE status='QUEUED' AND workflow_id IS NULL ORDER BY " + QUEUE_ORDER)]
    busy = busy_count()
    rows.sort(key=lambda r: r["submitted_at"], reverse=True)
    return [item(r, waiting, busy) for r in rows]


def item(r: dict, waiting: list[str], busy: int) -> dict:
    """Ekrana giden satır. Durum: sirada | okunuyor | hazir | yeniden (düştü, deneme hakkı var) | beklemede (iş bilerek
    durduruldu: CANCELLED, çoğu `progress.hold` etiketiyle — ör. arşiv pilotu dışında bekletilen kitaplar; okuma
    hatası değil) | okunamadi (yalnız FAILED ve deneme hakkı bitmiş: dosya açılamadı ya da her deneme düştü).
    `hold`: bekletme etiketi (satırda varsa)."""
    iso = lambda t: t.isoformat() if t else None
    jid = str(r["id"])
    st = r["status"]
    if st == "SUCCEEDED":
        state = "hazir"
    elif st == "RUNNING" or (st == "QUEUED" and r.get("workflow_id")):
        state = "okunuyor"
    elif st == "QUEUED":
        state = "sirada"
    elif st == "FAILED" and r["attempt"] < ATTEMPTS:
        state = "yeniden"
    elif st == "CANCELLED":
        state = "beklemede"
    else:
        state = "okunamadi"
    # Önünde kaç kitap var: sırada ondan önce bekleyenler + şu an okunanlar.
    ahead = (waiting.index(jid) + busy) if state == "sirada" and jid in waiting else None
    return {"id": jid, "title": r["title"], "pages": r["page_count"], "status": st, "state": state,
            "phase": phase(r["step"], "QUEUED" if state == "sirada" else st), "ahead": ahead,
            "attempt": r["attempt"], "attempts": ATTEMPTS, "failed": state == "okunamadi",
            "hold": (r.get("hold") or None) if state == "beklemede" else None,
            "requested_by": (r["requested_by"] or "").removeprefix(PREFIX),
            "created_at": iso(r.get("submitted_at") or r["created_at"]), "finished_at": iso(r["finished_at"])}


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["consume"]:
        asyncio.run(consume())
    else:
        raise SystemExit("kullanım: python -m editor.portal_books consume")
