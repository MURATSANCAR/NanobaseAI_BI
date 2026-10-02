"""Kitap okutma giden kutusu: dosya kabulü, sıralı gönderim, ulaşılamayan motor ve kalıcı ret."""
import httpx
import pytest

from semantic_bridge import editorial_book_reads as R


class FakeIncoming:
    def __init__(self, path, data):
        path.write_bytes(data)
        self.path, self.size, self.sha256, self.stored = str(path), len(data), "x", False


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path / "editorial"))
    monkeypatch.setattr(R, "kick", lambda: None)
    return tmp_path


def _take(box, name="kitap.pdf", data=b"%PDF-1.7 x", title="", user="ayse"):
    return R.accept(FakeIncoming(box / ("up-" + name), data), name, title, user)


def test_accept_moves_file_and_shows_sending(box):
    out = _take(box, "Anne_Terligi.pdf")
    assert out["state"] == "gonderiliyor" and out["status"] == "SENDING"
    assert out["title"] == "Anne Terligi"
    assert [p.suffix for p in sorted(R.folder().iterdir())] == [".json", ".pdf"]


@pytest.mark.parametrize("name,data,msg", [("kitap.docx", b"%PDF", "Yalnız PDF"), ("kitap.pdf", b"PK\x03\x04", "PDF değil")])
def test_accept_rejects_non_pdf(box, name, data, msg):
    with pytest.raises(R.Rejected, match=msg):
        _take(box, name, data)
    assert list(R.folder().glob("*.json")) == []


def test_send_in_order_and_clear_on_success(box):
    _take(box, "a.pdf")
    _take(box, "b.pdf")
    sent = []
    assert R.send_once(lambda f, name, title, user: sent.append(name)) == 2
    assert sent == ["a.pdf", "b.pdf"]
    assert list(R.folder().glob("*.json")) == []


def test_unreachable_engine_keeps_item_waiting_and_order(box):
    _take(box, "a.pdf")
    _take(box, "b.pdf")

    def down(*_):
        raise httpx.ConnectError("tünel yok")

    assert R.send_once(down) == 0
    items = R.pending()
    assert [it["filename"] for it in items] == ["a.pdf", "b.pdf"]
    assert items[0]["waiting"] and items[0]["attempts"] == 1 and items[1]["attempts"] == 0
    # beklerken sıra korunur: b, a'nın önüne geçmez
    assert R.send_once(lambda *a: None) == 0


def test_engine_422_is_final_and_dismissable(box):
    _take(box, "bozuk.pdf")
    req = httpx.Request("POST", "http://x/v1/books/read")

    def bad(*_):
        raise httpx.HTTPStatusError("422", request=req, response=httpx.Response(422, json={"detail": "PDF açılamadı."}, request=req))

    R.send_once(bad)
    (it,) = R.pending()
    assert it["state"] == "okunamadi" and it["message"] == "PDF açılamadı."
    assert not (R.folder() / f"{it['id']}.pdf").exists()
    assert R.dismiss(it["id"], "baskasi", False) is False
    assert R.dismiss(it["id"], "ayse", False) is True
    assert R.pending() == []


def test_listing_falls_back_to_last_engine_list(box):
    _take(box, "a.pdf")
    first = R.listing("ayse", False, lambda: {"items": [{"id": "j1", "title": "Eski"}]})
    assert [i["title"] for i in first["items"]] == ["a", "Eski"] and not first["stale"]

    def down():
        raise httpx.ConnectError("yok")

    second = R.listing("ayse", False, down)
    assert second["stale"] and [i["title"] for i in second["items"]] == ["a", "Eski"]


def test_archive_mode_travels_to_the_engine(box):
    """Kitap Eczanesi: kip ve kategori giden kutusu kaydında durur, motora form alanı olarak gider; tam okumada
    alan hiç gönderilmez (eski kart servisi de kabul eder)."""
    out = R.accept(FakeIncoming(box / "up-a.pdf", b"%PDF-1.7 x"), "a.pdf", "", "ayse", "archive", "Cocuk/6-9_yas")
    assert out["profile"] == "archive" and out["category"] == "Cocuk/6-9_yas"
    _take(box, "b.pdf")
    sent = []
    assert R.send_once(lambda f, name, title, user, **kw: sent.append((name, kw))) == 2
    assert sent == [("a.pdf", {"profile": "archive", "category": "Cocuk/6-9_yas"}), ("b.pdf", {})]


@pytest.mark.parametrize("profile,category", [("redaction", ""), ("archive", "../etc"), ("archive", "Roman")])
def test_archive_mode_rejects_unknown_values(box, profile, category):
    with pytest.raises(R.Rejected):
        R.accept(FakeIncoming(box / "up-a.pdf", b"%PDF-1.7 x"), "a.pdf", "", "ayse", profile, category)
    assert list(R.folder().glob("*.json")) == []
    assert R.read_mode("", "") == {} and R.read_mode("archive", "") == {"profile": "archive", "category": ""}


JOB = "00000000-0000-0000-0000-0000000000aa"


def _engine_status(code, detail=None):
    req = httpx.Request("POST", "http://x")
    return httpx.HTTPStatusError(str(code), request=req, response=httpx.Response(code, json={"detail": detail}, request=req))


def test_retry_passes_the_session_user_and_maps_engine_answers(monkeypatch):
    from semantic_bridge import editorial_cards
    seen = []
    monkeypatch.setattr(editorial_cards, "book_read_retry",
                        lambda job, user: seen.append((job, user)) or {"job_id": "new", "retry_of": job})
    assert R.retry(JOB, "ayse") == {"job_id": "new", "retry_of": JOB} and seen == [(JOB, "ayse")]

    def busy(job, user):
        raise _engine_status(409, "Kitap zaten sırada ya da okunuyor.")
    monkeypatch.setattr(editorial_cards, "book_read_retry", busy)
    with pytest.raises(R.RetryRefused) as e:
        R.retry(JOB, "ayse")
    assert e.value.status == 409 and "sırada" in str(e.value)

    def down(job, user):
        raise httpx.ConnectError("tünel yok")
    monkeypatch.setattr(editorial_cards, "book_read_retry", down)
    with pytest.raises(R.RetryRefused) as e:
        R.retry(JOB, "ayse")
    assert e.value.status == 502 and "tünel" not in str(e.value)


def test_retry_refuses_outbox_rows_and_bad_ids():
    with pytest.raises(R.RetryRefused) as e:
        R.retry("gonder-abc", "ayse")
    assert e.value.status == 409
    with pytest.raises(R.RetryRefused) as e:
        R.retry("../x", "ayse")
    assert e.value.status == 404
