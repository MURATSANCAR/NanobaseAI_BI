"""Kitap Eczanesi — köprü uçları (ön yüz: src/canvas/editorial/pharmacy/).

Arşiv kipinde («Zeki'ye sor» için) okunan kitaplar: liste, tek kitap, son okuma raporu (kitap kimliğiyle) ve
kitabı redaksiyona açma. Editör veritabanına doğrudan erişim yok; hepsi kart servisinin uçları
(`apps/editor/src/editor/card_api.py`: `GET /v1/archive/books[/{id}]`, `GET /v1/books/{id}/proofing`,
`POST /v1/books/{id}/redaction`). Kitap yükleme mevcut kitap okutma yolundan gider (`PUT /api/v1/editorial/ask/read
?profile=archive`); EPUB, sesli kitap ve tasarım Kitap Tasarım Stüdyosu uçlarıdır (`/api/v1/editorial/studio/…`).
Son okuma kararı, Word çıktısı, kelime haritası ve karşılık önerileri Son okuma ekranıyla ortak uçlardır.

Sayfa yetkisi `sayfa:kitap-eczanesi` (access.py); redaksiyona açma ayrıca `ozellik:kitap-eczanesi.redaksiyon`
ister (GPU'da son okuma denetimlerini başlatır). Açan kişi oturumdan gelir (`X-Editor`), istemci adını yazamaz.

app.py'de `_books` tanımından sonra bağlanır:
    from semantic_bridge import editorial_pharmacy
    editorial_pharmacy.register(app, {"auth": _books, "audit": admin_mod.audit})
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

import httpx
from fastapi import HTTPException, Request

from semantic_bridge import editorial_cards
from semantic_bridge import sorgu_izi as _IZ  # noqa: E402 — sorgu bilgisi
from semantic_bridge.soru_kaynak import databases as _sk_dbs  # noqa: E402

log = logging.getLogger(__name__)

P = "/api/v1/editorial/pharmacy"


def _uuid(v: str) -> str:
    try:
        return str(uuid.UUID(v))
    except (TypeError, ValueError):
        raise HTTPException(404, "Kitap bulunamadı.") from None


def _engine_error(e: Exception, what: str):
    """Kart servisinin hatası kişiye sade cümleyle: 404/409/422 olduğu gibi (servisin metni), gerisi 502/503."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (404, 409, 422):
            try:
                detail = e.response.json().get("detail") or what
            except ValueError:
                detail = what
            if code == 404 and detail == "book not found":
                detail = "Kitap bulunamadı."
            raise HTTPException(code, str(detail)) from e
        raise HTTPException(503 if code == 503 else 502, what) from e
    if isinstance(e, ValueError):
        raise HTTPException(422, str(e)) from e
    log.warning("kitap eczanesi: %s", str(e)[:200])
    raise HTTPException(502, what) from e


def register(app, deps: dict[str, Any] | Any) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)` → (engine, tenant, user, is_admin); `deps["audit"]`:
    `admin_mod.audit(engine, user, action, kind, obj, what, detail)`."""
    auth: Callable[[Request], Any] = deps["auth"] if isinstance(deps, dict) else deps.auth
    audit: Callable[..., Any] | None = deps.get("audit") if isinstance(deps, dict) else getattr(deps, "audit", None)

    @app.get(P + "/books")
    @_IZ.izlenir('portal.eczane.kitaplar', 'Kitap Eczanesi kitapları',
                 'Arşivde okunan kitaplar: okuma ve redaksiyon durumu, kategori, sayfa sayısı editörün okuma kuyruğu '
                 'kaydından (kitap başına son iş); sayılar kayıtların sayımıdır.', engine=None, dbs=_sk_dbs,
                 dis_adi='Editör kart servisi (okuma kuyruğu)')
    def pharmacy_books(request: Request, q: str = "", category: str = "", state: str = "", sort: str = "title",
                       offset: int = 0, limit: int = 50, review: bool = False) -> dict[str, Any]:
        """Sayfa sayfa liste; arama, kategori («-» = kategorisiz), durum ve «gözden geçir» süzgeci (sitedeki kategori
        ile Zeki AI önerisi ayrışanlar). `total` süzülmüş sayı."""
        auth(request)
        try:
            return editorial_cards.archive_books(q, category, state, sort, offset, limit, review)
        except Exception as e:  # noqa: BLE001
            _engine_error(e, "Kitap listesi şu an alınamadı.")

    @app.get(P + "/books/{book_id}")
    def pharmacy_book(book_id: str, request: Request) -> dict[str, Any]:
        """Tek kitabın satırı: ayrıntı alanı okuma/redaksiyon ilerlerken bunu yoklar (bütün listeyi değil)."""
        auth(request)
        try:
            return editorial_cards.archive_book(_uuid(book_id))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            _engine_error(e, "Kitap şu an okunamadı.")

    @app.get(P + "/books/{book_id}/proofing")
    @_IZ.izlenir('portal.eczane.sonokuma', 'Kitap Eczanesi son okuma',
                 'Son okuma bulguları: uyarı ve hata sayısı denetim servisinin raporundan (bulgu başına bir satır); '
                 'sayılar raporun kendisidir, model sayı üretmez.', engine=None, dbs=_sk_dbs,
                 dis_adi='Son okuma denetim servisi (kitap başına rapor)')
    def pharmacy_proofing(book_id: str, request: Request, title: str = "") -> dict[str, Any]:
        """Son okuma raporu kitap kimliğiyle (Son okuma ekranındakiyle aynı biçim). Kitap redaksiyona açılmadıysa
        denetim listesi boştur."""
        auth(request)
        try:
            return editorial_cards.proofing_report_by_id(_uuid(book_id), (title or None))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            _engine_error(e, "Son okuma raporu şu an alınamadı.")

    @app.post(P + "/books/{book_id}/redaction")
    def pharmacy_redaction(book_id: str, request: Request) -> dict[str, Any]:
        """Arşivde okunmuş kitabı redaksiyona açar: son okuma denetimleri, metin–görsel teyidi, süreklilik ve
        çelişki tespiti okuma kuyruğuna girer. Sırada ya da sürüyorsa yenisi açılmaz (servis aynı işi döner)."""
        engine, _tenant, user, _ = auth(request)
        bid = _uuid(book_id)
        try:
            out = editorial_cards.open_redaction(bid, user)
        except Exception as e:  # noqa: BLE001
            _engine_error(e, "Kitap redaksiyona açılamadı.")
        if audit is not None:
            try:
                audit(engine, user, "create", "editorial_redaction", bid, "kitap redaksiyona açıldı",
                      {"jobId": out.get("job_id"), "already": out.get("already")})
            except Exception:  # noqa: BLE001 — denetim kaydı düşerse işlem geri alınmaz
                log.exception("kitap eczanesi denetim kaydı")
        return out

    @app.post("/api/v1/editorial/proofing/word-alternatives")
    async def proofing_word_alternatives(request: Request) -> dict[str, Any]:
        """Yakın tekrar bulgularının karşılık önerileri: editör bulgu grubunu açınca istenir (Son okuma ve Kitap
        Eczanesi ortak). Gövde {bookId, findingIds?}; önerisi hazır bulgu yeniden sorulmaz. Sonra rapor yeniden
        okunur (öneri bulgunun `suggestion` alanında gelir)."""
        auth(request)
        try:
            b = await request.json()
        except Exception:  # noqa: BLE001
            b = None
        if not isinstance(b, dict):
            raise HTTPException(400, "Gövde bir nesne olmalı.")
        ids = b.get("findingIds")
        if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, str) for i in ids)):
            raise HTTPException(422, "Bulgu kimlikleri liste olmalı.")
        bid = _uuid(str(b.get("bookId") or ""))
        from starlette.concurrency import run_in_threadpool
        try:
            return await run_in_threadpool(editorial_cards.word_alternatives, bid, ids)
        except Exception as e:  # noqa: BLE001
            _engine_error(e, "Karşılık önerileri şu an hazırlanamadı.")
