"""Kitaba sor kapsam sınıflandırıcısı seçili kitabı görür (2026-10-01)."""
import json

from semantic_bridge import editorial_books as B


def _chat(intent, seen):
    def chat(messages, max_tokens=40):
        seen.append(messages)
        return json.dumps({"intent": intent})
    return chat


def test_selected_book_reaches_classifier():
    seen = []
    assert B.scope_reply("Shinil Binası'ndaki yangın ihbarı saat kaçta yapıldı?", _chat("BOOK", seen),
                         "Çiçekçi Kadın") is None
    user = json.loads(seen[0][1]["content"])
    assert user == {"message": "Shinil Binası'ndaki yangın ihbarı saat kaçta yapıldı?", "selectedBook": "Çiçekçi Kadın"}
    assert "selectedBook" in seen[0][0]["content"]


def test_no_book_sends_only_message():
    seen = []
    B.scope_reply("Yarın hava nasıl olacak?", _chat("OFF", seen))
    assert json.loads(seen[0][1]["content"]) == {"message": "Yarın hava nasıl olacak?"}


def test_off_and_self_replies_unchanged():
    assert B.scope_reply("Yarın hava nasıl?", _chat("OFF", []), "Çiçekçi Kadın") == B.OFF_REPLY
    assert B.scope_reply("merhaba", None) == B.SELF_REPLY
    assert B.scope_reply("Kim öldü?", _chat("UNKNOWN", []), "Çiçekçi Kadın") is None
