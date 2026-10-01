"""Kitaba sor hızlı yolu: kitap adı eşleşmesi, bağlam bütçesi ve ajana devretme işareti."""
import asyncio

import pytest

from editor import chat_params, quick_answer as QA


def _book(*names):
    return {"names": list(names)}


def test_norm_folds_turkish_and_extension():
    assert QA.norm("Böcekleri Seven Kadın") == "bocekleri seven kadin"
    assert QA.norm("Dilek Agaci.indd") == "dilek agaci"
    assert QA.norm("dedem-tekrar-cocuk-oldu") == "dedem tekrar cocuk oldu"


def test_mentioned_matches_record_and_publisher_titles_on_word_boundaries():
    anne = _book("anne-terligi", "Anne Terliği")
    dedem = _book("dedem-tekrar-cocuk-oldu", "Dedem Tekrar Çocuk Oldu")
    ask = _book("ask-terapi", "Aşk Terapi")
    q = "anne terliği ve dedem tekrar çocuk oldu kitaplarının ortak yönleri"
    assert QA.mentioned(q, [anne, dedem, ask]) == [anne, dedem]
    assert QA.mentioned("maske takmak", [_book("ask")]) == []


def test_fit_keeps_fixed_blocks_and_says_how_many_events_were_left_out(monkeypatch):
    monkeypatch.setattr(QA.budget, "estimate", lambda t, ratio=None: len(t))
    events = [f"- s.{i}: olay {i}" for i in range(50)]
    text = QA.fit(["KİTAP A", "KİTAP B"], [events, []], room=14 + 120)
    assert "KİTAP A" in text and "KİTAP B" in text
    kept = text.count("- s.")
    assert 0 < kept < 50
    assert f"{50 - kept} olay daha" in text


class _Resp:
    def __init__(self, content, finish="stop", status=200):
        self.status_code, self._c, self._f, self.text = status, content, finish, content

    def json(self):
        return {"choices": [{"message": {"content": self._c}, "finish_reason": self._f}], "usage": {}}


@pytest.fixture()
def fake(monkeypatch):
    sent = []

    async def ctx(q, t):
        return "KAYIT", [{"crm_title": None, "title": "anne-terligi"}]
    monkeypatch.setattr(QA, "context", ctx)

    def reply(content, **kw):
        async def post(path, req):
            sent.append(req)
            return _Resp(content, **kw)
        monkeypatch.setattr(QA.llm, "_post", post)
    return sent, reply


def test_answer_is_one_call_without_thinking(fake):
    sent, reply = fake
    reply("Hürdeniz [s.47].")
    out = asyncio.run(QA.answer("Karakterler kim?", "anne-terligi"))
    assert out["handled"] and out["answer"] == "Hürdeniz [s.47]." and len(sent) == 1
    assert sent[0]["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.parametrize("content,finish", [(QA.DEEPER, "stop"), ("yarım", "length"), ("", "stop")])
def test_deeper_or_broken_answer_is_handed_to_agent(fake, content, finish):
    _, reply = fake
    reply(content, finish=finish)
    assert asyncio.run(QA.answer("s.12'de ne oluyor?"))["handled"] is False


def test_not_found_is_flagged(fake):
    _, reply = fake
    reply(QA.NOT_FOUND + " Kapak tasarımcısı kayıtlarda yok.")
    assert asyncio.run(QA.answer("Kapak tasarımcısı kim?"))["not_found"] is True


def test_gateway_turns_thinking_off_unless_client_asked():
    p = {"messages": []}
    assert chat_params.without_thinking(p) and p["chat_template_kwargs"] == {"enable_thinking": False}
    keep = {"chat_template_kwargs": {"enable_thinking": True}}
    assert not chat_params.without_thinking(keep) and keep["chat_template_kwargs"]["enable_thinking"] is True
