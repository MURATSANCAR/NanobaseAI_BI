"""Kitap Eczanesi köprü uçları: kart servisine giden çağrılar, kimlik biçimi, hata çevirisi ve denetim kaydı."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import editorial_cards, editorial_pharmacy

BID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    audits = []
    editorial_pharmacy.register(app, {"auth": lambda request: ("eng", "t", "ayse", False),
                                      "audit": lambda *a: audits.append(a)})
    c = TestClient(app)
    c.audits = audits
    return c


def _status(code, detail):
    req = httpx.Request("GET", "http://x")
    return httpx.HTTPStatusError(str(code), request=req, response=httpx.Response(code, json={"detail": detail}, request=req))


def test_list_passes_filters(client, monkeypatch):
    seen = {}

    def fake(q, category, state, sort, offset, limit, review, title_review):
        seen.update(q=q, category=category, state=state, sort=sort, offset=offset, limit=limit, review=review,
                    title_review=title_review)
        return {"items": [], "total": 0}

    monkeypatch.setattr(editorial_cards, "archive_books", fake)
    r = client.get("/api/v1/editorial/pharmacy/books", params={"q": "çalı", "category": "Kurgu", "state": "hazir", "offset": 50})
    assert r.status_code == 200 and r.json()["total"] == 0
    assert seen == {"q": "çalı", "category": "Kurgu", "state": "hazir", "sort": "title", "offset": 50, "limit": 50,
                    "review": False, "title_review": False}
    client.get("/api/v1/editorial/pharmacy/books", params={"review": "true"})
    assert seen["review"] is True and seen["title_review"] is False
    client.get("/api/v1/editorial/pharmacy/books", params={"title_review": "true", "state": "beklemede"})
    assert seen["title_review"] is True and seen["review"] is False and seen["state"] == "beklemede"


def test_archive_states_include_on_hold():
    """Bekletilen kitap (iş bilerek durduruldu) kendi süzgeciyle istenebilir; okunamadı ile karışmaz."""
    assert "beklemede" in editorial_cards.ARCHIVE_STATES and "okunamadi" in editorial_cards.ARCHIVE_STATES


def test_list_bad_filter_is_422_and_engine_down_is_502(client, monkeypatch):
    def bad(*a):
        raise ValueError("Durum geçersiz.")

    monkeypatch.setattr(editorial_cards, "archive_books", bad)
    assert client.get("/api/v1/editorial/pharmacy/books?state=x").status_code == 422

    def down(*a):
        raise httpx.ConnectError("tünel yok")

    monkeypatch.setattr(editorial_cards, "archive_books", down)
    r = client.get("/api/v1/editorial/pharmacy/books")
    assert r.status_code == 502 and "tünel" not in r.text


def test_book_and_proofing_need_a_book_id(client, monkeypatch):
    monkeypatch.setattr(editorial_cards, "archive_book", lambda bid: {"id": bid})
    monkeypatch.setattr(editorial_cards, "proofing_report_by_id", lambda bid, title: {"bookId": bid, "bookTitle": title})
    assert client.get("/api/v1/editorial/pharmacy/books/yok").status_code == 404
    assert client.get(f"/api/v1/editorial/pharmacy/books/{BID}").json() == {"id": BID}
    rep = client.get(f"/api/v1/editorial/pharmacy/books/{BID}/proofing?title=A").json()
    assert (rep["bookId"], rep["bookTitle"]) == (BID, "A")
    assert "kaynaklar" in rep            # sorgu bilgisi (ekrandaki «?» düğmesi) uçla birlikte gelir

    def gone(*a):
        raise _status(404, "book not found")

    monkeypatch.setattr(editorial_cards, "archive_book", gone)
    r = client.get(f"/api/v1/editorial/pharmacy/books/{BID}")
    assert r.status_code == 404 and r.json()["detail"] == "Kitap bulunamadı."


def test_redaction_carries_the_session_user_and_is_audited(client, monkeypatch):
    calls = []
    monkeypatch.setattr(editorial_cards, "open_redaction", lambda bid, user: calls.append((bid, user)) or {"job_id": "j", "already": None})
    r = client.post(f"/api/v1/editorial/pharmacy/books/{BID}/redaction")
    assert r.status_code == 200 and calls == [(BID, "ayse")]
    assert client.audits and client.audits[0][2] == "create"

    def full(*a):
        raise _status(409, "Bu okuma arşiv kipinde değil; son okuma adımları zaten koştu.")

    monkeypatch.setattr(editorial_cards, "open_redaction", full)
    r = client.post(f"/api/v1/editorial/pharmacy/books/{BID}/redaction")
    assert r.status_code == 409 and "arşiv kipinde değil" in r.json()["detail"]


def test_word_alternatives_body(client, monkeypatch):
    calls = []
    monkeypatch.setattr(editorial_cards, "word_alternatives", lambda bid, ids: calls.append((bid, ids)) or {"filled": 1})
    assert client.post("/api/v1/editorial/proofing/word-alternatives", json={"bookId": BID, "findingIds": [BID]}).json() == {"filled": 1}
    assert calls == [(BID, [BID])]
    assert client.post("/api/v1/editorial/proofing/word-alternatives", json={"bookId": BID, "findingIds": "x"}).status_code == 422
    assert client.post("/api/v1/editorial/proofing/word-alternatives", json={"bookId": "x"}).status_code == 404
    assert client.post("/api/v1/editorial/proofing/word-alternatives", json=[1]).status_code == 400


def test_reread_uses_the_books_read_job_and_is_audited(client, monkeypatch):
    from semantic_bridge import editorial_book_reads
    monkeypatch.setattr(editorial_cards, "archive_book", lambda bid: {"id": bid, "read": {"id": "job-1", "state": "okunamadi"}})
    calls = []
    monkeypatch.setattr(editorial_book_reads, "retry", lambda job, user: calls.append((job, user)) or {"job_id": "job-2", "retry_of": job})
    r = client.post(f"/api/v1/editorial/pharmacy/books/{BID}/reread")
    assert r.status_code == 200 and r.json()["job_id"] == "job-2"
    assert calls == [("job-1", "ayse")]
    assert client.audits and client.audits[-1][1] == "ayse" and client.audits[-1][3] == "editorial_book_read"


def test_reread_without_a_read_or_refused_is_409(client, monkeypatch):
    from semantic_bridge import editorial_book_reads
    monkeypatch.setattr(editorial_cards, "archive_book", lambda bid: {"id": bid, "read": None})
    assert client.post(f"/api/v1/editorial/pharmacy/books/{BID}/reread").status_code == 409
    monkeypatch.setattr(editorial_cards, "archive_book", lambda bid: {"id": bid, "read": {"id": "job-1"}})

    def busy(job, user):
        raise editorial_book_reads.RetryRefused("Kitap zaten sırada ya da okunuyor.", 409)
    monkeypatch.setattr(editorial_book_reads, "retry", busy)
    r = client.post(f"/api/v1/editorial/pharmacy/books/{BID}/reread")
    assert r.status_code == 409 and "sırada" in r.text
    assert client.post("/api/v1/editorial/pharmacy/books/yok/reread").status_code == 404
