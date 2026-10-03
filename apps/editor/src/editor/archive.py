"""Arşiv kipi: kitabı «Zeki'ye sor» (Kitaba sor) için okur; son okuma (redaksiyon) yapmaz.

Kullanıcı kararı 2026-10-02: GPU'daki `/data/kitaplar` arşivi (4.034 PDF: Cocuk/0-5, 6-9, 10-12, 13+;
Kurgu; Kurgu_Disi) sorulara cevap verecek kadar okunur. İş başına seçilir: `analysis_job.profile='archive'`.
Normal kip (`'full'`) olduğu gibi kalır.

Arşiv kipinde KOŞAN: hazırlık, sayfa manifesti, metin katmanı (font onarımlı), OCR (yalnız gereken sayfa),
görsel tarama YALNIZ GÖRSELİ OLAN SAYFALARDA (`visual_pages`), karakter/olay adayları, kimlik, olay kipleri +
birleştirme + önemli olay sayfaları, görsel kimlik, kim ne yaptı, duygu ve tema, künye, doğruluk denetimi
(critic), bölüm ve kitap özetleri, arama dizini, rapor (sohbetin okuduğu çıktı; model çağırmaz) ve katalog kartı.

KOŞMAYAN (redaksiyona açılınca `profile='redaction'` işiyle koşar, `open_for_redaction`): son okuma
denetimleri (`proofing`), metin–görsel tutarlılık teyidi (`confirm_text_visual`), karakter sürekliliği,
çelişki tespiti + editör kuyruğu. Redaksiyon raporu son okuma bulgularından üretildiği için o da o zaman.

Toplu kuyruk: `python -m editor.archive enqueue --root /data/kitaplar [--prescan ontarama.jsonl] --dry-run`.
Kuyruk sırası: portaldan gelen kitap arşivin önüne geçer (portal_books.QUEUE_ORDER).
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
import uuid
from pathlib import Path

PROFILE = "archive"
REDACTION = "redaction"
#: Toplu kuyruğun iş sahibi öneki (portal_books.retry_failed bunu da yeniden dener).
PREFIX = "arsiv:"
ROOT = Path(os.environ.get("EDITOR_ARCHIVE_ROOT", "/data/kitaplar"))

# ------------------------------------------------------------------ hangi sayfa görsel modele gider
#: Sayfa alanının bu payı resimse sayfa görseldir. %5, 13,5×21 cm sayfada ~3,8×3,8 cm'lik bir resim:
#: yayınevi logosu, bölüm başı süsü, sayfa numarası çerçevesi bunun altında kalır; en küçük metin içi
#: resim (çocuk kitabındaki ikon dizisi, bilgi kutusundaki fotoğraf) üstünde. Ön tarama (4.034 kitap)
#: bu ölçütle aynı: iki sayı birbirinden ayrılmasın diye burada tek yer.
IMAGE_SHARE = float(os.environ.get("EDITOR_ARCHIVE_IMAGE_SHARE", "0.05"))
#: Resim yoksa vektör çizim yolu sayısı. Düz metin sayfasında çizim yalnız çizgi/çerçeve/zemin
#: (birkaç ile yirmi arası yol); vektör çizilmiş resim, şema, harita yüzlercedir. 40 ikisinin arası.
MIN_DRAWINGS = int(os.environ.get("EDITOR_ARCHIVE_MIN_DRAWINGS", "40"))


def page_is_visual(image_share: float, drawings: int) -> bool:
    return image_share >= IMAGE_SHARE or drawings >= MIN_DRAWINGS


def measure_page(page) -> tuple[float, int]:
    """(resim alanı payı, çizim yolu sayısı). Çizimler yalnız resim payı eşiğin altındaysa sayılır (pahalı)."""
    area = (page.rect.width * page.rect.height) or 1.0
    img = 0.0
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        img += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    share = min(1.0, img / area)
    drawings = len(page.get_drawings()) if share < IMAGE_SHARE else 0
    return share, drawings


def select_visual(measures: list[tuple[float, int]]) -> list[int]:
    """Görsel taramaya girecek sayfalar (1'den): kapak (ilk sayfa) her zaman + resimli/çizimli sayfalar."""
    out = [n for n, (share, dr) in enumerate(measures, start=1) if n == 1 or page_is_visual(share, dr)]
    return out


def visual_pages(book_version_id: str) -> dict:
    """Kitabın görsel taramaya girecek sayfaları; düz metin sayfası görsel modele gitmez."""
    from . import document
    doc, _ = document._open_version(book_version_id, repair=False)
    measures = [measure_page(p) for p in doc]
    pages = select_visual(measures)
    return {"pages": pages, "page_count": len(measures), "visual": len(pages),
            "rule": {"image_share": IMAGE_SHARE, "min_drawings": MIN_DRAWINGS, "cover": 1}}


# ------------------------------------------------------------------ klasör → okur kitlesi / tür
#: Klasör adı → profil ipucu (book_type.profile CRM kaydı yoksa bunu kullanır; CRM gelirse CRM geçer).
#: forms: tür adayları (None = bütün türler, kitabın metni seçer); tek aday = tür kesin.
CATEGORIES: dict[str, dict] = {
    "Cocuk/0-5_yas": {"audience": "CHILD", "age_from": 0, "age_to": 5, "forms": None},
    "Cocuk/6-9_yas": {"audience": "CHILD", "age_from": 6, "age_to": 9, "forms": None},
    "Cocuk/10-12_yas": {"audience": "CHILD", "age_from": 10, "age_to": 12, "forms": None},
    "Cocuk/13+_yas": {"audience": "YOUNG", "age_from": 13, "age_to": None, "forms": None},
    "Kurgu": {"audience": "ADULT", "age_from": None, "age_to": None, "forms": ["FICTION"]},
    "Kurgu_Disi": {"audience": "ADULT", "age_from": None, "age_to": None,
                   "forms": ["NARRATIVE_NONFICTION", "EXPOSITORY", "ACTIVITY", "POETRY"]},
}


def hint_for(category: str) -> dict:
    """Kategori klasörünün profil ipucu; tanınmayan klasör okur kitlesini UNKNOWN bırakır."""
    base = CATEGORIES.get(category.strip("/"))
    if base is None:
        return {"category": category, "audience": None, "age_from": None, "age_to": None, "forms": None}
    return {"category": category, **base}


def age_group(h: dict) -> str | None:
    if h.get("age_from") is None:
        return None
    return f"{h['age_from']}-{h['age_to']}" if h.get("age_to") is not None else f"{h['age_from']}+"


# ------------------------------------------------------------------ ad anahtarı ve kesik parça
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
#: Dosya adında kitabı değil dosyanın hâlini anlatan sözcükler (baskı, özalit, tashih, kapak, iç…).
NOISE = frozenset({"baski", "baskii", "baskiii", "baskiconv", "sonbaski", "ozalit", "tashih", "kapak", "ic",
                   "son", "convert", "conv", "renkli", "alm", "hazir", "yeni", "icbaski", "baskiozalit"})
#: Bu kadar ya da daha az sayfalık dosya, aynı adın en az iki katı uzun sürümü varsa kesik parçadır.
FRAGMENT_MAX_PAGES = int(os.environ.get("EDITOR_ARCHIVE_FRAGMENT_PAGES", "12"))


def fold(s: str) -> str:
    t = unicodedata.normalize("NFKD", (s or "").translate(_TR))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def name_key(path: str) -> str:
    """Aynı kitabın dosyalarını eşleyen ad: sıra öneki («3-»), kopya eki «(2)», ölçü «135x210», forma «18f»,
    baskı numarası ve dosya hâli sözcükleri atılır; geri kalan sayılar kalır (seri numarası ayrı kitaptır)."""
    s = fold(Path(path).stem)
    s = re.sub(r"\(\d+\)", " ", s)
    s = re.sub(r"\d+([.,]\d+)?\s*x\s*\d+([.,]\d+)?", " ", s)
    s = re.sub(r"\b\d+([.,]\d+)?f\b", " ", s)
    s = re.sub(r"\d+\s*\.?\s*bask\w*", " ", s)
    s = re.sub(r"^\s*\d+\s*[-_.]\s*", "", s)
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in NOISE]
    return " ".join(toks)


def fragments(rows: list[dict]) -> dict[str, dict]:
    """path → uzun sürümü: aynı ad anahtarında en az iki kat ve FRAGMENT_MAX_PAGES'ten uzun bir dosya varken
    FRAGMENT_MAX_PAGES ya da daha az sayfalık dosya kesik parçadır (özalit/tashih sayfası, kapak açılımı)."""
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        k = name_key(r["path"])
        if k:
            groups[k].append(r)
    out = {}
    for grp in groups.values():
        longest = max(grp, key=lambda r: r.get("pages") or 0)
        lp = longest.get("pages") or 0
        for r in grp:
            p = r.get("pages") or 0
            if r is not longest and 0 < p <= FRAGMENT_MAX_PAGES and lp > FRAGMENT_MAX_PAGES and lp >= 2 * p:
                out[r["path"]] = {"path": longest["path"], "pages": lp}
    return out


def clean_title(path: str) -> str:
    """ESKİ temizlik (2026-10-03'e kadar arşiv kitaplarının adı buydu): yalnız eski kayıtların adının dosya adından
    geldiğini tanımak için (book_title.legacy_file_derived). Yeni kitabın adı `book_title.from_file`'dan."""
    s = Path(path).stem
    s = re.sub(r"\(\d+\)", " ", s)
    s = re.sub(r"\d+([.,]\d+)?\s*[xX]\s*\d+([.,]\d+)?", " ", s)
    s = re.sub(r"\d+\s*\.?\s*bask\S*", " ", s, flags=re.I)
    s = re.sub(r"[_-]+", " ", s)
    words = [w for w in s.split() if fold(w).strip(".") not in NOISE and not re.fullmatch(r"\d+([.,]\d+)?f", w)]
    t = re.sub(r"\s+", " ", " ".join(words)).strip(" .")
    return t[:300] or Path(path).stem[:300]


# ------------------------------------------------------------------ plan (kuru koşu ve gerçek koşu aynı)
def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


def _measure_file(path: Path) -> dict:
    """Ön tarama satırı yoksa aynı ölçüm burada (yalnız okuma)."""
    import pymupdf
    rec = {"bytes": path.stat().st_size, "sha256": _sha(path)}
    with pymupdf.open(path) as doc:
        ms = [measure_page(p) for p in doc]
        rec.update(pages=len(ms), visual_pages=sum(1 for s, d in ms if page_is_visual(s, d)),
                   cover_visual=int(bool(ms) and page_is_visual(*ms[0])),
                   text_chars=sum(len(p.get_text("text").strip()) for p in doc))
    return rec


def list_pdfs(root: Path) -> list[str]:
    return sorted(str(Path(d, f).relative_to(root)) for d, _, fs in os.walk(root) for f in fs
                  if f.lower().endswith(".pdf") and not f.startswith("._"))


def plan(root: Path, prescan: dict[str, dict] | None = None, known=None) -> dict:
    """Kuyruğa girecek kitaplar ve atlananlar. `prescan`: path → ön tarama satırı (yoksa dosya ölçülür).
    `known(sha_list)` → {sha: durum}: veritabanında zaten okunmuş/sırada/okunuyor olanlar (None: bakılmaz)."""
    rows = []
    for rel in list_pdfs(root):
        r = dict((prescan or {}).get(rel) or {})
        if not r.get("sha256") or not r.get("pages"):
            try:
                r.update(_measure_file(root / rel))
            except Exception as e:  # noqa: BLE001 — açılamayan dosya rapora girer, kuyruğu durdurmaz
                r["error"] = f"{type(e).__name__}: {e}"[:200]
        r["path"] = rel
        r["category"] = str(Path(rel).parent)
        rows.append(r)
    take, skipped = [], {"duplicate": [], "fragment": [], "unreadable": [], "already": []}
    seen: dict[str, str] = {}
    for r in rows:
        if r.get("error") or not r.get("pages"):
            skipped["unreadable"].append({"path": r["path"], "error": r.get("error") or "sayfasız"})
        elif r["sha256"] in seen:
            skipped["duplicate"].append({"path": r["path"], "same_as": seen[r["sha256"]]})
        else:
            seen[r["sha256"]] = r["path"]
            take.append(r)
    frag = fragments(take)
    for r in [r for r in take if r["path"] in frag]:
        skipped["fragment"].append({"path": r["path"], "pages": r["pages"], "long_version": frag[r["path"]]["path"],
                                    "long_pages": frag[r["path"]]["pages"]})
    take = [r for r in take if r["path"] not in frag]
    if known is not None and take:
        st = known([r["sha256"] for r in take])
        skipped["already"] = [{"path": r["path"], "status": st[r["sha256"]]} for r in take if r["sha256"] in st]
        take = [r for r in take if r["sha256"] not in st]
    return {"root": str(root), "files": len(rows), "take": take, "skipped": skipped, "summary": summarize(take, skipped)}


def summarize(take: list[dict], skipped: dict) -> dict:
    by = collections.OrderedDict()
    for r in sorted(take, key=lambda r: r["category"]):
        c = by.setdefault(r["category"], {"books": 0, "pages": 0, "visual_pages": 0, "text_only_pages": 0,
                                          "over_1gb": 0, "low_text": 0, "audience": hint_for(r["category"])["audience"]})
        # görsel taramaya giren: resimli/çizimli sayfalar + kapak (resimsiz olsa da)
        sel = int(r.get("visual_pages") or 0) + (0 if r.get("cover_visual") else 1)
        c["books"] += 1
        c["pages"] += int(r["pages"])
        c["visual_pages"] += min(sel, int(r["pages"]))
        c["over_1gb"] += int((r.get("bytes") or 0) > 1 << 30)
        # metin katmanı neredeyse yok: OCR yolu (sayfa başına 20 karakterden az)
        c["low_text"] += int((r.get("text_chars") or 0) < max(200, 20 * int(r["pages"])))
    for c in by.values():
        c["text_only_pages"] = c["pages"] - c["visual_pages"]
    tot = {k: sum(c[k] for c in by.values()) for k in ("books", "pages", "visual_pages", "text_only_pages",
                                                      "over_1gb", "low_text")}
    return {"by_category": by, "total": tot, "skipped": {k: len(v) for k, v in skipped.items()}}


# ------------------------------------------------------------------ veritabanı (yalnız gerçek koşuda yazar)
def known_in_db(shas: list[str]) -> dict[str, str]:
    """Aynı içerik zaten okunmuş / sırada / okunuyorsa durumu (yalnız okuma)."""
    from . import db
    rows = db.all_rows(
        "SELECT DISTINCT ON (bv.sha256) bv.sha256, j.status FROM book_version bv JOIN analysis_job j"
        " ON j.book_version_id=bv.id WHERE bv.sha256 = ANY(%s) AND j.status IN ('QUEUED','RUNNING','SUCCEEDED')"
        " ORDER BY bv.sha256, j.created_at DESC", shas)
    return {r["sha256"]: r["status"] for r in rows}


def _place(src: Path, dest: Path) -> str:
    """Kaynak PDF kitap klasörüne: aynı dosya sisteminde sert bağ (yer kaplamaz), olmazsa kopya."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return "exists"
    try:
        os.link(src, dest)
        return "link"
    except OSError:
        tmp = dest.with_suffix(".part")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
        return "copy"


def intake(root: Path, r: dict) -> dict:
    """Bir arşiv kitabı: kitap kaydı → içerik sürümü → okuma işi (QUEUED, profile='archive')."""
    import pymupdf
    from . import db
    from .config import settings
    src = (root / r["path"]).resolve()
    if root.resolve() not in src.parents or not src.is_file():
        raise FileNotFoundError(f"{r['path']}: arşiv kökünün dışında ya da yok")
    sha = _sha(src)
    hint = {**hint_for(r["category"]), "path": r["path"]}
    with pymupdf.open(src) as doc:
        meta = {k: v for k, v in (doc.metadata or {}).items() if v}
        pages = doc.page_count
    dest = settings().storage / "books" / sha[:16] / "source.pdf"
    how = _place(src, dest)
    from . import book_title
    with db.tx() as c:
        bv = c.execute("SELECT id FROM book_version WHERE sha256=%s ORDER BY created_at LIMIT 1", (sha,)).fetchone()
        if bv is None:
            # Arşivde ad tekrarı kitap birleştirmez: farklı içerik = ayrı kitap (aynı adlı «1.kitap» iki klasörde).
            # Ad temizlenmiş dosya adı (kaynak «file», gözden geçir işaretli); okuma bitince site ve künyeyle
            # yeniden çözülür (book_title.after_reading).
            name = Path(r["path"]).name
            book = c.execute("INSERT INTO book(title, age_group) VALUES (%s,%s) RETURNING id",
                             (book_title.from_file(name)["title"], age_group(hint))).fetchone()
            book_title.set_on_intake(c, str(book["id"]), None, name)
            bv = c.execute("INSERT INTO book_version(book_id, sha256, file_path, file_bytes, page_count, pdf_meta)"
                           " VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                           (book["id"], sha, str(dest), src.stat().st_size, pages,
                            db.J({**meta, "archive_path": r["path"]}))).fetchone()
        job = c.execute("SELECT id, status FROM analysis_job WHERE book_version_id=%s AND status IN"
                        " ('QUEUED','RUNNING','SUCCEEDED') ORDER BY created_at DESC LIMIT 1", (bv["id"],)).fetchone()
        if job:
            return {"job_id": str(job["id"]), "already": job["status"], "file": how}
        job = c.execute("INSERT INTO analysis_job(book_version_id, profile, requested_by, progress)"
                        " VALUES (%s,%s,%s,%s) RETURNING id",
                        (bv["id"], PROFILE, PREFIX + r["category"][:180],
                         db.J({"attempt": 1, "archive": hint}))).fetchone()
    return {"job_id": str(job["id"]), "already": None, "file": how}


def hint_of_generation(generation_id: str) -> dict | None:
    """Okunan neslin arşiv ipucu (işin progress.archive); arşiv işi değilse None."""
    from . import db
    row = db.one("SELECT j.progress->'archive' AS hint FROM generation g JOIN analysis_job j ON j.id=g.job_id"
                 " WHERE g.id=%s", generation_id)
    h = (row or {}).get("hint")
    return h if isinstance(h, dict) else None


def open_for_redaction(generation_id: str, who: str) -> dict:
    """Arşivde okunmuş kitabı redaksiyona açar: aynı nesil üstünde, arşivde koşmayan adımları koşturacak
    `profile='redaction'` işi sıraya girer (BookFullAnalysis._run_redaction). Aynı nesil için sırada/süren
    redaksiyon işi varsa yenisi açılmaz."""
    from . import db
    g = db.one("SELECT g.id, g.book_version_id, j.profile FROM generation g JOIN analysis_job j ON j.id=g.job_id"
               " WHERE g.id=%s", generation_id)
    if g is None:
        raise KeyError(generation_id)
    if g["profile"] != PROFILE:
        raise ValueError("Bu okuma arşiv kipinde değil; son okuma adımları zaten koştu.")
    row = db.one("SELECT id, status FROM analysis_job WHERE profile=%s AND progress->>'generation_id'=%s"
                 " AND status IN ('QUEUED','RUNNING') ORDER BY created_at DESC LIMIT 1", REDACTION, str(g["id"]))
    if row:
        return {"job_id": str(row["id"]), "already": row["status"]}
    job = db.one("INSERT INTO analysis_job(book_version_id, profile, requested_by, progress) VALUES (%s,%s,%s,%s)"
                 " RETURNING id", g["book_version_id"], REDACTION, "portal:" + who[:200],
                 db.J({"attempt": 1, "generation_id": str(g["id"]), "from_profile": g["profile"]}))
    return {"job_id": str(job["id"]), "already": None}


# ------------------------------------------------------------------ Kitap Eczanesi listesi (kart servisi /v1/archive/books)
#: Okuma durumu (portal_books.item ile aynı sözlük) + «redaksiyon»: son okuması açılmış ya da koşmuş kitaplar.
LIST_STATES = ("sirada", "okunuyor", "hazir", "yeniden", "okunamadi", "redaksiyon")
SORTS = ("title", "recent")


def listing_data(c, book_id: str | None = None) -> tuple[list[dict], set[str], list[str]]:
    """Salt okuma (kart servisinin anlık görüntüsünde): arşiv kipinde okunan kitapların kitap × kip (archive |
    redaction) başına SON işi, son okuması koşmuş kitaplar ve kuyrukta bekleyen işlerin sırası.
    `book_id` verilirse yalnız o kitap."""
    from . import book_title
    from . import portal_books as PB
    one = " AND bv.book_id=%s" if book_id else ""
    tcols = ("b.title_source, b.title_review" if book_title.has_columns(c)
             else "NULL::text AS title_source, '{}'::text[] AS title_review")
    rows = c.execute(
        "SELECT DISTINCT ON (bv.book_id, j.profile) bv.book_id, b.title, " + tcols + ", j.id, j.profile, j.status, j.step,"
        " j.workflow_id, j.requested_by, j.created_at, j.finished_at, coalesce((j.progress->>'attempt')::int, 1)"
        " AS attempt, j.progress->'archive'->>'category' AS category, bv.page_count,"
        " min(j.created_at) OVER (PARTITION BY bv.book_id, j.profile) AS submitted_at"
        " FROM ed.analysis_job j JOIN ed.book_version bv ON bv.id=j.book_version_id JOIN ed.book b ON b.id=bv.book_id"
        " WHERE j.profile IN ('archive','redaction')" + one +
        " ORDER BY bv.book_id, j.profile, j.created_at DESC, j.id DESC", (book_id,) if book_id else ()).fetchall()
    ids = list({str(r["book_id"]) for r in rows})
    proofed = {str(r["book_id"]) for r in c.execute(
        "SELECT DISTINCT v.book_id FROM ed.proof_run r JOIN ed.generation g ON g.id=r.generation_id"
        " JOIN ed.book_version v ON v.id=g.book_version_id WHERE v.book_id::text = ANY(%s)", (ids,)).fetchall()} if ids else set()
    waiting = [str(r["id"]) for r in c.execute(
        "SELECT id FROM ed.analysis_job WHERE status='QUEUED' AND workflow_id IS NULL ORDER BY " + PB.QUEUE_ORDER,
        ()).fetchall()]
    return rows, proofed, waiting


class _Positions(list):
    """Kuyruk sırası listesi, sabit sürede `index`/`in` ile (portal_books.item satır başına sorar; arşivde binlerce
    iş sıradayken liste taraması kitap sayısının karesi kadar sürerdi)."""

    def __init__(self, items):
        super().__init__(items)
        self._at = {v: i for i, v in enumerate(self)}

    def index(self, v, *a):  # noqa: D401 — list.index ile aynı sözleşme (yoksa ValueError)
        try:
            return self._at[v]
        except KeyError:
            raise ValueError(v) from None

    def __contains__(self, v):
        return v in self._at


def shape(rows: list[dict], proofed: set[str], waiting: list[str], busy: int) -> list[dict]:
    """Kitap başına tek satır: okuma (arşiv kipi) ve redaksiyonun durumu portal satırının diliyle (sirada,
    okunuyor, hazir, yeniden, okunamadi; aşama adı teknik ad taşımaz). Redaksiyon işi yoksa `redaction` None;
    son okuması koşmuşsa `proofed`."""
    from . import portal_books as PB
    waiting = _Positions(waiting)
    by: dict[str, dict] = {}
    for r in rows:
        bid = str(r["book_id"])
        b = by.setdefault(bid, {"id": bid, "title": r["title"], "title_source": r.get("title_source"),
                                "title_review": list(r.get("title_review") or []), "category": None,
                                "pages": r["page_count"], "read": None, "redaction": None, "proofed": bid in proofed,
                                "bulk": False})
        it = PB.item(r, waiting, busy)
        who = r.get("requested_by") or ""
        it["requested_by"] = None if who.startswith(PREFIX) else it["requested_by"]
        if r["profile"] == PROFILE:
            b["read"] = it
            b["category"] = r.get("category")
            b["bulk"] = who.startswith(PREFIX)
            b["pages"] = r["page_count"] or b["pages"]
        else:
            b["redaction"] = it
    # Redaksiyon işi olan ama arşiv okuması bu listede görünmeyen kitap olmaz (redaksiyon arşiv neslinden açılır);
    # yine de okuma satırı yoksa kitap gösterilir, okuma durumu bilinmez (None).
    return list(by.values())


def _stamp(b: dict) -> str:
    xs = [x.get("finished_at") or x.get("created_at") or "" for x in (b.get("read"), b.get("redaction")) if x]
    return max(xs) if xs else ""


def _state_of(b: dict) -> str | None:
    return (b.get("read") or {}).get("state")


def _review(b: dict) -> bool:
    return bool((b.get("review") or {}).get("review"))


def select(books: list[dict], q: str = "", category: str = "", state: str = "", sort: str = "title",
           offset: int = 0, limit: int = 50, review: bool = False) -> dict:
    """Arama (Türkçe harf ve büyük/küçük harf farkı gözetmez) → kategori → durum süzgeci, sıralama ve sayfa.
    `facets`: aramaya uyan kitapların kategori sayıları ve (kategori süzgeciyle) durum sayıları; ekran süzgeç
    düğmelerinde gösterir. `total` süzülmüş kitap sayısı; hiçbir kitap kesilmez, sayfalar `offset` ile gezilir.
    `review`: yalnız sitedeki kategori ile Zeki AI önerisi ayrışan kitaplar («gözden geçir»; editor.recommend);
    `facets.review` süzgeçlerden sonra kaç kitabın gözden geçirileceğini söyler."""
    key = fold(q).strip()
    hit = [b for b in books if not key or key in fold(b["title"] or "")]
    cats: dict[str, int] = collections.Counter((b["category"] or "") for b in hit)
    in_cat = [b for b in hit if not category or (b["category"] or "") == ("" if category == "-" else category)]
    states: dict[str, int] = collections.Counter(_state_of(b) or "" for b in in_cat)
    states["redaksiyon"] = sum(1 for b in in_cat if b["redaction"] or b["proofed"])
    if state == "redaksiyon":
        out = [b for b in in_cat if b["redaction"] or b["proofed"]]
    elif state:
        out = [b for b in in_cat if _state_of(b) == state]
    else:
        out = in_cat
    to_review = sum(1 for b in out if _review(b))
    if review:
        out = [b for b in out if _review(b)]
    if sort == "recent":
        out = sorted(out, key=lambda b: (_stamp(b), b["id"]), reverse=True)
    else:
        out = sorted(out, key=lambda b: (fold(b["title"] or ""), b["id"]))
    page = out[offset:offset + limit]
    return {"items": page, "total": len(out), "offset": offset, "limit": limit, "all": len(books),
            "facets": {"categories": dict(cats), "states": {k: v for k, v in states.items() if k},
                       "review": to_review}}


# ------------------------------------------------------------------ arşiv çıktıları (rebuild.run'ın arşiv eşi)
async def validate(gid: str) -> dict:
    """rebuild.validate'in arşiv eşi: doğruluk denetimi (critic) + kim ne yaptı + regresyon. Çelişki tespiti ve
    editör kuyruğu YOK (redaksiyona açılınca). Yazanın jetonu aynı: dondurma eşzamanlı düzeltmeyi yakalar."""
    from . import db, knowledge, quality
    token = str(uuid.uuid4())
    ctx = db.validation_token.set(token)
    try:
        start = db.one("SELECT knowledge_revision FROM ed.generation_state WHERE generation_id=%s", gid)["knowledge_revision"]
        # Künye, iç kapak, yazar tanıtımı, içindekiler, yayınevi tanıtımı: metni öyle olan sayfa editör onayı
        # beklemeden kapsam dışı (editor.page_scope; editör sonradan geri alabilir). Bütün kitap üstünden: okuma
        # sırasında parçalar yan yana koştuğu için eksik kalanı burada tamamlanır.
        from . import page_scope
        scope = await asyncio.to_thread(page_scope.ensure, gid)
        scope["metadata"] = await page_scope.metadata_after_scope(gid, scope)
        critic = await quality.critic_pass(gid, recheck=True)
        actors = await knowledge.attribute_event_actors(gid)
        regression = await asyncio.to_thread(quality.run_regression_suite, gid)
        return {"critic": critic, "actors": actors, "contradictions": None, "queued": None,
                "regression_passed": regression["passed"], "writer_token": token, "start_revision": start,
                "profile": PROFILE, "deferred": ["detect_contradictions", "contradictions_to_queue"],
                "page_scope": scope}
    finally:
        db.validation_token.reset(ctx)


def _quiet(gid: str) -> None:
    """Arsiv neslinin çıktılarını yalnız iş akışı kurar: arka plandaki yeniden kurucu (editor-rebuild) bu nesli
    almaz, yoksa tam doğrulamayla (çelişki tespiti + kuyruk) kurardı. Editör sonradan bilgi düzeltirse istek
    yeniden açılır ve normal yoldan kurulur — bu doğru: kitap artık elden geçiyor."""
    from . import db
    db.one("UPDATE ed.rebuild_request SET completed_revision=requested_revision, updated_at=now()"
           " WHERE generation_id=%s RETURNING generation_id", gid)


async def run_outputs(gid: str) -> dict:
    """Özet, arama dizini, rapor ve katalog kartı: rebuild.run ile aynı sözleşme (kilit, dondurma, sürümlü
    yayın, aynı dönüş durumları: SUCCEEDED | ALREADY_CURRENT | BUSY | CAPACITY_WAIT | SUPERSEDED)."""
    from . import db, outputs, rebuild
    await asyncio.to_thread(rebuild.activate, gid)
    await asyncio.to_thread(_quiet, gid)
    with db.pool().connection() as lock:
        got = lock.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", ("outputs:" + gid,)).fetchone()["ok"]
        lock.commit()
        if not got:
            return {"generation_id": gid, "technical_status": "BUSY"}
        try:
            with db.tx() as c:
                state = rebuild.ensure_open(c, gid)
                n = c.execute("SELECT count(*) AS n FROM ed.current_artifact a JOIN ed.knowledge_snapshot s ON"
                              " s.generation_id=a.generation_id AND s.input_digest=a.input_digest WHERE"
                              " a.generation_id=%s AND s.content->>'code_version'=%s AND s.content->>'policy'=%s",
                              (gid, rebuild.code_version(), outputs.POLICY)).fetchone()["n"]
                if state["validated_revision"] == state["knowledge_revision"] and n == len(outputs.ORDER):
                    return {"generation_id": gid, "technical_status": "ALREADY_CURRENT", "accepted": False}
            from .llm import aliases
            actual = await aliases()
            declared = db.one("SELECT model_manifest FROM ed.generation WHERE id=%s", gid)["model_manifest"]
            for alias in ("book-director", "book-embedding"):
                if any(actual.get(alias, {}).get(k) != declared.get(alias, {}).get(k) for k in ("real_model", "revision")):
                    raise ValueError("Model profile changed; create a new generation: " + alias)
            existing = db.one("SELECT s.content,s.input_digest FROM ed.knowledge_snapshot s JOIN ed.generation_state g"
                              " ON g.generation_id=s.generation_id AND g.validated_revision=s.revision"
                              " WHERE s.generation_id=%s AND g.knowledge_revision=s.revision"
                              " ORDER BY s.created_at DESC LIMIT 1", gid)
            if existing and existing["content"]["code_version"] == rebuild.code_version():
                snap, digest = existing["content"], existing["input_digest"]
            else:
                snap, digest = await asyncio.to_thread(rebuild.freeze, gid, await validate(gid))
            built = {}
            for kind in outputs.ORDER:
                key = rebuild.key_for(snap, digest, kind)
                cached = await asyncio.to_thread(rebuild.begin, snap, digest, kind, key)
                if cached is None:
                    cached = await rebuild.build(kind, snap, built, key)
                await asyncio.to_thread(rebuild.publish, snap, digest, kind, key, cached)
                built[kind] = cached
            return {**await asyncio.to_thread(rebuild.finish, snap, digest), "profile": PROFILE}
        except rebuild.Superseded as exc:
            await asyncio.to_thread(_quiet, gid)
            return {"generation_id": gid, "technical_status": "SUPERSEDED", "reason": str(exc), "accepted": False}
        except Exception as exc:
            await asyncio.to_thread(rebuild.failed, gid, exc)
            await asyncio.to_thread(_quiet, gid)
            if rebuild.is_capacity_error(exc):
                return {"generation_id": gid, "technical_status": "CAPACITY_WAIT", "reason": str(exc)[:500],
                        "accepted": False}
            raise
        finally:
            lock.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", ("outputs:" + gid,))
            lock.commit()


# ------------------------------------------------------------------ komut
def _load_prescan(path: str | None) -> dict[str, dict]:
    if not path:
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out[r["path"]] = r
    return out


def report_text(p: dict) -> str:
    s = p["summary"]
    lines = [f"Kök: {p['root']} — {p['files']} PDF", "",
             f"{'kategori':<18}{'kitap':>7}{'sayfa':>10}{'görselli':>10}{'düz metin':>11}{'>1GB':>6}{'az metin':>10}  okur"]
    for cat, c in s["by_category"].items():
        lines.append(f"{cat:<18}{c['books']:>7}{c['pages']:>10}{c['visual_pages']:>10}{c['text_only_pages']:>11}"
                     f"{c['over_1gb']:>6}{c['low_text']:>10}  {c['audience'] or 'UNKNOWN'}")
    t = s["total"]
    lines.append(f"{'TOPLAM':<18}{t['books']:>7}{t['pages']:>10}{t['visual_pages']:>10}{t['text_only_pages']:>11}"
                 f"{t['over_1gb']:>6}{t['low_text']:>10}")
    lines += ["", "Atlanan: " + ", ".join(f"{k} {v}" for k, v in s["skipped"].items())]
    for f in p["skipped"]["fragment"]:
        lines.append(f"  kesik parça: {f['path']} ({f['pages']} s.) — uzun sürümü {f['long_version']} ({f['long_pages']} s.)")
    for f in p["skipped"]["duplicate"]:
        lines.append(f"  kopya: {f['path']} = {f['same_as']}")
    for f in p["skipped"]["unreadable"]:
        lines.append(f"  açılamadı: {f['path']} ({f['error']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m editor.archive")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enqueue", help="arşiv PDF'lerini arşiv kipinde okuma kuyruğuna al")
    e.add_argument("--root", default=str(ROOT))
    e.add_argument("--prescan", help="ön tarama jsonl (path, pages, visual_pages, cover_visual, text_chars, sha256)")
    e.add_argument("--dry-run", action="store_true", help="hiçbir şey yazma; kaç kitap alınacağını raporla")
    e.add_argument("--no-db", action="store_true", help="kuru koşuda veritabanına hiç bakma")
    e.add_argument("--json", help="planı bu dosyaya yaz")
    r = sub.add_parser("redaction", help="arşivde okunmuş kitabı redaksiyona aç (atlanan adımlar koşar)")
    r.add_argument("--generation", required=True)
    r.add_argument("--by", default="editor")
    a = ap.parse_args(argv)
    if a.cmd == "redaction":
        print(json.dumps(open_for_redaction(a.generation, a.by), ensure_ascii=False))
        return 0
    root = Path(a.root)
    p = plan(root, _load_prescan(a.prescan), None if (a.dry_run and a.no_db) else known_in_db)
    if a.json:
        Path(a.json).write_text(json.dumps(p, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(report_text(p))
    if a.dry_run:
        print("\nKuru koşu: hiçbir şey yazılmadı.")
        return 0
    done = collections.Counter()
    for r_ in p["take"]:
        try:
            res = intake(root, r_)
            done["already" if res["already"] else "queued"] += 1
            done["file_" + res["file"]] += 1
        except Exception as ex:  # noqa: BLE001 — bir dosya kuyruğun geri kalanını durdurmaz
            done["failed"] += 1
            print(f"alınamadı: {r_['path']}: {ex}", file=sys.stderr)
    print(json.dumps(dict(done), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
