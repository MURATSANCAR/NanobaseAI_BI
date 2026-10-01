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
