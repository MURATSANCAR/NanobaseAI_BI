"""Kitap kartı listesi ve kapaklar köprünün belleğinden (2026-09-29 hız işi).

Önce: `/ask/catalog` her açılışta kart servisinden bütün listeyi (9–10 sn), `/ask/covers/{id}` her kapak için tam boy
sayfa render'ını internet üzerinden (istek başına 4–5 sn, her istekte yeni TLS bağlantısı) okuyordu. Şimdi liste ve
küçük boy kapak diskte durur; eskiyen kayıt hemen döner ve arkada (kapakta koşullu istekle) doğrulanır.
Liste içeriği değişmez: bellekten dönen liste kart servisinin verdiği listenin aynısıdır.
"""
from __future__ import annotations

import io
import time
import uuid

import httpx
import pytest

from semantic_bridge import editorial_cards as C

B1 = str(uuid.UUID("11111111-1111-1111-1111-111111111111"))
B2 = str(uuid.UUID("22222222-2222-2222-2222-222222222222"))
CARDS = [
    {"id": B1, "title": "anne-terligi", "generationId": "g1", "revision": 3, "authors": ["A"], "summary": [],
     "cover": {"source": "PDF_PAGE", "page": 1}, "contentAvailable": True, "semanticAcceptance": False},
    {"id": B2, "title": "kapaksiz", "generationId": "g2", "revision": None, "authors": [], "summary": [],
     "cover": None, "contentAvailable": False, "semanticAcceptance": False},
]


def _png(width: int = 40, height: int = 60) -> bytes:
    try:
        from PIL import Image
    except ImportError:
        return b"\x89PNG\r\n\x1a\n" + b"0" * 64
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


class Upstream:
    """Kart servisinin yerine: istekleri sayar, kapakta ETag / If-None-Match uygular."""

    def __init__(self, cover: bytes):
        self.cover = cover
        self.calls: list[tuple[str, dict]] = []
        self.cards = [dict(c) for c in CARDS]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.url.path, dict(request.headers)))
        if request.url.path == "/v1/books/cards":
            return httpx.Response(200, json={"items": self.cards, "read_only": True})
        if request.url.path == f"/v1/books/{B1}/cover":
            if request.headers.get("if-none-match") == '"u1"':
                return httpx.Response(304, headers={"etag": '"u1"'})
            return httpx.Response(200, content=self.cover, headers={"content-type": "image/png", "etag": '"u1"'})
        return httpx.Response(404, json={"detail": "cover not found"})

    def count(self, path: str) -> int:
        return sum(1 for p, _ in self.calls if p == path)


@pytest.fixture
def up(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_CATALOG_BASE", "http://cards.test")
    monkeypatch.setenv("EDITOR_CATALOG_KEY", "k")
    monkeypatch.setenv("EDITORIAL_CARDS_CACHE_DIR", str(tmp_path))
    u = Upstream(_png())
    monkeypatch.setattr(C, "_clients", {"": httpx.Client(transport=httpx.MockTransport(u), base_url="http://cards.test")})
    monkeypatch.setattr(C, "_catalogue_cache", {"items": None, "at": 0.0})
    monkeypatch.setattr(C, "_covers_mem", {})
    monkeypatch.setattr(C, "_cover_pending", set())
    return u


def _drain():
    C._cover_queue.join()


def test_katalog_bir_kez_okunur_icerik_aynidir(up):
    first = C.catalogue_snapshot()
    assert first == CARDS and up.count("/v1/books/cards") == 1
    _drain()
    again = C.catalogue_snapshot()
    assert again == CARDS and up.count("/v1/books/cards") == 1          # bellekten, kart servisine gidilmedi
    # ekrana giden alanlar değişmedi
    assert [C.public_card(c) for c in again] == [C.public_card(c) for c in CARDS]


def test_katalog_yeniden_baslatmada_diskten_gelir(up, monkeypatch):
    C.catalogue_snapshot()
    _drain()
    monkeypatch.setattr(C, "_catalogue_cache", {"items": None, "at": 0.0})    # köprü yeniden başladı
    assert C.catalogue_snapshot() == CARDS and up.count("/v1/books/cards") == 1


def test_eski_katalog_hemen_doner_arkada_tazelenir(up, monkeypatch):
    C.catalogue_snapshot()
    _drain()
    C._catalogue_cache["at"] = time.time() - 3600
    up.cards = up.cards + [{**CARDS[1], "id": str(uuid.uuid4()), "title": "yeni"}]
    assert C.catalogue_snapshot() == CARDS                          # beklemeden eldeki
    for _ in range(100):
        if up.count("/v1/books/cards") == 2 and len(C._catalogue_cache["items"] or []) == 3:
            break
        time.sleep(0.02)
    assert len(C.catalogue_snapshot()) == 3


def test_yenile_kart_servisini_bekler(up):
    C.catalogue_snapshot()
    C.catalogue_snapshot(fresh=True)
    assert up.count("/v1/books/cards") == 2


def test_kapak_bir_kez_cekilir_sonra_diskten(up):
    data, mime, etag = C.cover_thumb(B1)
    assert data and mime in ("image/png", "image/webp", "image/jpeg") and etag.startswith('"')
    assert up.count(f"/v1/books/{B1}/cover") == 1
    again = C.cover_thumb(B1)
    assert again == (data, mime, etag) and up.count(f"/v1/books/{B1}/cover") == 1


def test_eski_kapak_kosullu_istekle_dogrulanir(up):
    data, mime, etag = C.cover_thumb(B1)
    meta_path, _ = C._cover_paths(B1)
    import json
    meta = json.loads(meta_path.read_text())
    meta["checkedAt"] = time.time() - 3600
    meta_path.write_text(json.dumps(meta))
    assert C.cover_thumb(B1) == (data, mime, etag)                  # beklemeden eldeki
    _drain()
    assert up.count(f"/v1/books/{B1}/cover") == 2
    assert up.calls[-1][1].get("if-none-match") == '"u1"'           # 304: bayt yeniden inmedi
    assert json.loads(meta_path.read_text())["checkedAt"] > time.time() - 60


def test_katalogda_kapagi_olmayan_kitap_icin_servise_gidilmez(up):
    C.catalogue_refresh()
    _drain()
    with pytest.raises(KeyError):
        C.cover_thumb(B2)
    assert up.count(f"/v1/books/{B2}/cover") == 0
    # kapağı olan kitap tur sırasında arkada hazırlandı
    assert up.count(f"/v1/books/{B1}/cover") == 1
    C.cover_thumb(B1)
    assert up.count(f"/v1/books/{B1}/cover") == 1


def test_bulunamayan_kapak_kaydedilir(up):
    other = str(uuid.uuid4())
    with pytest.raises(KeyError):
        C.cover_thumb(other)
    with pytest.raises(KeyError):
        C.cover_thumb(other)
    assert up.count(f"/v1/books/{other}/cover") == 1


def test_kapak_kucuk_boya_iner():
    pytest.importorskip("PIL")
    from PIL import Image

    big = _png(1200, 1800)
    small, mime = C.shrink_cover(big, "image/png", 360)
    with Image.open(io.BytesIO(small)) as im:
        assert im.width == 360 and im.height == 540
    assert len(small) < len(big) and mime in ("image/webp", "image/jpeg")


def test_kapak_ucu_etag_ile_304_doner(up, monkeypatch):
    from fastapi import FastAPI, Request, Response
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/c/{book_id}")
    def cover(book_id: str, request: Request):
        data, mime, etag = C.cover_thumb(book_id)
        if etag in [t.strip() for t in request.headers.get("if-none-match", "").split(",")]:
            return Response(status_code=304, headers={"ETag": etag})
        return Response(content=data, media_type=mime, headers={"ETag": etag})

    client = TestClient(app)
    r = client.get(f"/c/{B1}")
    assert r.status_code == 200 and r.headers["etag"]
    r2 = client.get(f"/c/{B1}", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304 and not r2.content
