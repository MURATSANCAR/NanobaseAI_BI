"""Kitap okutma giden kutusu (Kitaba sor'un üstündeki yükleme alanı).

Yüklenen PDF önce köprünün diskine alınır (`EDITORIAL_DIR/book-reads/<kimlik>.pdf` + `.json`) ve kişi hemen
«Gönderiliyor» satırını görür; editör motoruna gönderim arkada, sırayla yapılır. Motor ya da GPU tüneli o an
ulaşılamıyorsa gönderim beklemede kalır ve kendiliğinden yeniden denenir (kişiye hata dönmez, satırda
«bağlantı bekleniyor» yazar). Yalnız dosyanın kendisi okunamıyorsa (PDF değil, bozuk, parolalı) motorun 422'si
kalıcıdır: satır «okunamadı» olur, yeniden gönderilmez.

Motorun listesi okunamazsa son başarılı liste (bellekte, kişi başına) gösterilir; ekran boş ya da hatalı kalmaz.
Aynı dosya iki kez gönderilse de motor içerik özetinden aynı kitabı bulur, ikinci okuma açılmaz.

Elle yeniden okuma (`retry`): kendini onarma denemeleri biten («okunamadı») kitabı kişi yeniden sıraya koyar; motor
aynı kipte yeni iş açar (çift iş açılmaz). Hata nedeni ekrana gitmez; kişi yalnız «okuma tamamlanamadı» görür.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("semantic.editorial_book_reads")

PDF_MAGIC = b"%PDF"
#: Gönderim denemeleri arası bekleme (sn): ilk hatalar hızlı, sonra dakikada bir.
BACKOFF = (5, 15, 30, 60)

_state_lock = threading.Lock()
_sender: Optional[threading.Thread] = None
_last_lists: dict[str, list[dict[str, Any]]] = {}


class Rejected(ValueError):
    """Dosyanın kendisi okutulamaz; kişiye olduğu gibi gösterilir."""


def folder() -> Path:
    root = Path(os.environ.get("EDITORIAL_DIR", "/data/nanobaseai/bi/var/editorial")) / "book-reads"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def _save(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_name("." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False))
    os.replace(tmp, path)


def _load(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


#: Kitap Eczanesi'nin arşiv kategorileri (editör `editor.archive.CATEGORIES` ile aynı klasör adları). Boş = yok.
ARCHIVE_CATEGORIES = ("Cocuk/0-5_yas", "Cocuk/6-9_yas", "Cocuk/10-12_yas", "Cocuk/13+_yas", "Kurgu", "Kurgu_Disi")


def read_mode(profile: str, category: str) -> dict[str, str]:
    """Okuma kipi: boş/`full` = tam okuma (Kitaba sor yükleme alanı), `archive` = Kitap Eczanesi (arşiv kipi,
    son okuma redaksiyona açılınca). Kategori yalnız arşivde ve yalnız tanınan klasör adıyla geçer."""
    p = (profile or "").strip().lower()
    if p in ("", "full"):
        return {}
    if p != "archive":
        raise Rejected("Okuma kipi geçersiz.")
    c = (category or "").strip()
    if c and c not in ARCHIVE_CATEGORIES:
        raise Rejected("Kategori geçersiz.")
    return {"profile": "archive", "category": c}


def accept(incoming: Any, filename: str, title: str, user: str, profile: str = "", category: str = "") -> dict[str, Any]:
    """Yüklemeyi giden kutusuna alır (taşıma, kopya yok) ve gönderimi tetikler. PDF değilse hemen reddeder.
    `profile='archive'`: Kitap Eczanesi'nden; kip ve kategori giden kutusu kaydında taşınır, motora iletilir."""
    mode = read_mode(profile, category)
    with open(incoming.path, "rb") as f:
        head = f.read(len(PDF_MAGIC))
    if not (filename or "").lower().endswith(".pdf"):
        raise Rejected("Yalnız PDF okutulabilir.")
    if head != PDF_MAGIC:
        raise Rejected("Dosyanın içeriği PDF değil.")
    item_id = uuid.uuid4().hex
    root = folder()
    os.replace(incoming.path, root / f"{item_id}.pdf")
    incoming.stored = True
    item = {"id": item_id, "filename": filename or "kitap.pdf", "title": (title or "").strip(), "user": user,
            "bytes": incoming.size, "sha256": incoming.sha256, "created_at": time.time(), "attempts": 0,
            "state": "gonderiliyor", "waiting": False, **mode}
    _save(root / f"{item_id}.json", item)
    kick()
    return public(item)


def public(item: dict[str, Any]) -> dict[str, Any]:
    """Ekrana giden satır (motor satırıyla aynı biçim)."""
    return {"id": "gonder-" + item["id"], "title": item["title"] or Path(item["filename"]).stem.replace("-", " ").replace("_", " "),
            "pages": None, "status": "SENDING", "state": item["state"], "waiting": bool(item.get("waiting")),
            "message": item.get("message"), "phase": {"n": 0, "of": 15, "label": "Gönderiliyor"}, "ahead": None,
            "attempt": 1, "attempts": 1, "failed": item["state"] == "okunamadi", "requested_by": item["user"],
            "created_at": _iso(item["created_at"]), "finished_at": None, "bytes": item.get("bytes"),
            "profile": item.get("profile") or "full", "category": item.get("category") or None}


def _iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def pending(user: Optional[str] = None) -> list[dict[str, Any]]:
    """Henüz motora geçmemiş (gönderiliyor) ya da motorun kalıcı olarak reddettiği satırlar."""
    out = []
    for p in folder().glob("*.json"):
        it = _load(p)
        if it and (user is None or it.get("user") == user):
            out.append(it)
    return sorted(out, key=lambda it: it["created_at"])


def dismiss(item_id: str, user: str, is_admin: bool) -> bool:
    """Okunamadı satırını kişi kapatır (yalnız reddedilmiş satır; gönderimi süren satır kapatılmaz)."""
    p = folder() / f"{item_id}.json"
    it = _load(p)
    if not it or it.get("state") != "okunamadi" or (it.get("user") != user and not is_admin):
        return False
    p.unlink(missing_ok=True)
    (folder() / f"{item_id}.pdf").unlink(missing_ok=True)
    return True


def send_once(upload: Callable[..., dict[str, Any]]) -> int:
    """Bekleyen en eski dosyadan başlayarak motora gönderir; ulaşılamazsa durur (sonraki tur). Döner: gönderilen."""
    import httpx

    sent = 0
    for it in pending():
        if it.get("state") != "gonderiliyor":
            continue
        root = folder()
        pdf, meta = root / f"{it['id']}.pdf", root / f"{it['id']}.json"
        if time.time() < it.get("next_at", 0):
            return sent  # sırayı koru: en eski beklerken yenisi öne geçmez
        try:
            with pdf.open("rb") as f:
                extra = {"profile": it["profile"], "category": it.get("category") or ""} if it.get("profile") else {}
                upload(f, it["filename"], it["title"], it["user"], **extra)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 422:  # dosya okunamaz: kalıcı
                try:
                    msg = e.response.json().get("detail")
                except ValueError:
                    msg = None
                it.update(state="okunamadi", message=msg if isinstance(msg, str) else "PDF okunamadı.", waiting=False)
                _save(meta, it)
                pdf.unlink(missing_ok=True)
                continue
            _later(meta, it, e)
            return sent
        except FileNotFoundError:
            meta.unlink(missing_ok=True)
            continue
        except Exception as e:  # noqa: BLE001 — tünel/GPU/ağ: beklemede kalır
            _later(meta, it, e)
            return sent
        meta.unlink(missing_ok=True)
        pdf.unlink(missing_ok=True)
        sent += 1
    return sent


def _later(meta: Path, it: dict[str, Any], e: Exception) -> None:
    n = int(it.get("attempts", 0)) + 1
    it.update(attempts=n, waiting=True, next_at=time.time() + BACKOFF[min(n - 1, len(BACKOFF) - 1)])
    _save(meta, it)
    log.warning("kitap okutma gönderimi bekliyor (%s, %d. deneme): %s", it.get("filename"), n, str(e)[:200])


def kick() -> None:
    """Gönderici iş parçacığını (yoksa) başlatır; bekleyen kalmayınca kendiliğinden biter. Birden çok köprü süreci
    aynı klasörü paylaşırsa dosya kilidi tek göndericiye izin verir."""
    global _sender
    from semantic_bridge import editorial_cards

    with _state_lock:
        if _sender is not None and _sender.is_alive():
            return

        def run() -> None:
            with (folder() / "send.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
                while any(it.get("state") == "gonderiliyor" for it in pending()):
                    try:
                        send_once(editorial_cards.book_read_upload)
                    except Exception:  # noqa: BLE001
                        log.exception("kitap okutma gönderici turu")
                    time.sleep(2)

        _sender = threading.Thread(target=run, name="editorial-book-reads", daemon=True)
        _sender.start()


def listing(user: str, see_all: bool, engine_list: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Ekrandaki liste: giden kutusundakiler (en üstte) + motorun satırları. Motor okunamazsa son başarılı liste,
    `stale` işaretiyle; hata dönmez."""
    kick()
    key = "*" if see_all else user
    stale = False
    try:
        engine = engine_list().get("items") or []
        _last_lists[key] = engine
    except Exception as e:  # noqa: BLE001
        log.warning("okutulan kitaplar motordan alınamadı; son liste gösteriliyor: %s", str(e)[:200])
        engine = _last_lists.get(key, [])
        stale = True
    mine = [public(it) for it in reversed(pending(None if see_all else user))]
    return {"items": mine + engine, "stale": stale}


class RetryRefused(ValueError):
    """Yeniden okuma açılamadı; `status` köprünün döneceği kod, mesaj kişiye olduğu gibi gösterilir."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def retry(job_id: str, user: str) -> dict[str, Any]:
    """Motorun okuma işini (`job_id`, ekrandaki satırın kimliği) elle yeniden sıraya koyar. Giden kutusu satırı
    («gonder-…») motora hiç geçmemiştir, yeniden okunacak işi yoktur. Motorun 409'u (zaten sırada / düşmüş değil)
    ve 404'ü kişiye sade cümleyle; ulaşılamazsa 502."""
    import httpx

    from semantic_bridge import editorial_cards

    if job_id.startswith("gonder-"):
        raise RetryRefused("Bu kitap henüz okumaya gönderilmedi.", 409)
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise RetryRefused("Okuma bulunamadı.", 404) from None
    try:
        return editorial_cards.book_read_retry(job_id, user)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 409:
            try:
                detail = e.response.json().get("detail")
            except ValueError:
                detail = None
            raise RetryRefused(detail if isinstance(detail, str) else "Kitap şu an yeniden okutulamaz.", 409) from e
        if code == 404:
            raise RetryRefused("Okuma bulunamadı.", 404) from e
        log.warning("yeniden okuma motor hatası %s", code)
        raise RetryRefused("Kitap şu an yeniden sıraya alınamadı; birazdan tekrar deneyin.", 502) from e
    except Exception as e:  # noqa: BLE001 — tünel/GPU/ağ
        log.warning("yeniden okuma motora ulaşamadı: %s", str(e)[:200])
        raise RetryRefused("Kitap şu an yeniden sıraya alınamadı; birazdan tekrar deneyin.", 502) from e
