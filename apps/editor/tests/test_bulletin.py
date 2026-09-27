"""Kampüs sesli bülteni: metin parçalara doğru bölünür, istek kaydedilir, durum okunur (model çağrılmaz)."""
import pytest

from editor.production import bulletin as B
from editor.production import narration as N


def test_paragraphs_and_sentences_become_bounded_segments():
    text = ("Bu hafta yayın kurulunda 12 proje görüşüldü. Üçü onaylandı!\n\n"
            + "Uzun bir cümle " * 40 + ".\n\n   \n\nSon paragraf.")
    segs = B.segments_of(text)
    assert segs, "parça çıkmalı"
    assert all(0 < len(s["text"]) <= 1800 for s in segs)      # sunucu parça başına 2.000 karakter alır
    assert len(segs) >= 3                                    # uzun paragraf birden çok parçaya bölünür
    assert "on iki" in segs[0]["text"]                     # rakam okunuşa çevrilir
    assert segs[-1]["pause_ms"] == 0 and segs[-1]["text"].startswith("Son paragraf")
    assert any(s["pause_ms"] == B.PARAGRAPH_PAUSE for s in segs[:-1])


def test_empty_or_too_long_text_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "_root", lambda: tmp_path)
    with pytest.raises(ValueError):
        B.create("   ", "anlatici-kadin", "editor")
    with pytest.raises(ValueError):
        B.create("a" * (B.TEXT_MAX + 1), "anlatici-kadin", "editor")
    with pytest.raises(ValueError):
        B.create("Merhaba.", "boyle-bir-ses-yok", "editor")


def test_create_records_request_and_state(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "_root", lambda: tmp_path)
    st = B.create("Merhaba Timaş. Bu haftanın bülteni.", "anlatici-kadin", "editor", title="Deneme")
    assert B.BID.match(st["id"]) and st["status"] == "queued" and not st["ready"] and st["title"] == "Deneme"
    B.set_state(st["id"], status="done", duration=12.5)
    (B.audio_path(st["id"])).write_bytes(b"ID3xxx")
    again = B.state(st["id"])
    assert again["status"] == "done" and again["duration"] == 12.5 and again["ready"]
    with pytest.raises(KeyError):
        B.state("../../etc")
