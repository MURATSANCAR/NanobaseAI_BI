"""Kitaba sor: kitap adı eşleşmesi, bağlam bütçesi, derin okuma (ikinci ve son çağrı)."""
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


class _Sent(list):
    pass


@pytest.fixture()
def fake(monkeypatch):
    sent = _Sent()

    full = {"v": True}
    deep_calls = []

    async def ctx(q, t, deep=False):
        deep_calls.append(deep)
        return ("DERIN" if deep else "KAYIT"), [{"crm_title": None, "title": "anne-terligi"}], full["v"]
    monkeypatch.setattr(QA, "context", ctx)

    def reply(*answers, **kw):
        queue = list(answers)

        async def post(path, req, headers=None):
            sent.append(req)
            a = queue.pop(0) if len(queue) > 1 else queue[0]
            return _Resp(*a) if isinstance(a, tuple) else _Resp(a, **kw)
        monkeypatch.setattr(QA.llm, "_post", post)
    sent.full, sent.deep = full, deep_calls
    return sent, reply


def test_answer_is_one_call_without_thinking(fake):
    sent, reply = fake
    reply("Hürdeniz [s.47].")
    out = asyncio.run(QA.answer("Karakterler kim?", "anne-terligi"))
    assert out["handled"] and out["answer"] == "Hürdeniz [s.47]." and len(sent) == 1
    assert sent[0]["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.parametrize("content,finish", [(QA.DEEPER, "stop"), ("yarım", "length"), ("", "stop"),
                                            (QA.NOT_FOUND + " Kayıtta yok.", "stop")])
def test_selected_book_gets_one_deep_read_call(fake, content, finish):
    sent, reply = fake
    reply((content, finish), ("Selen Demirtaş [s.2].", "stop"))
    out = asyncio.run(QA.answer("Kitabı kim çevirdi?", "anne-terligi"))
    assert out["handled"] and out["deep"] and out["answer"] == "Selen Demirtaş [s.2]."
    assert len(sent) == 2 and sent.deep == [False, True]
    assert sent[1]["max_tokens"] == QA.DEEP_ANSWER_TOKENS and sent[1]["messages"][0]["content"] == QA.DEEP_SYSTEM
    assert "DERIN" in sent[1]["messages"][1]["content"]


def test_deep_read_never_asks_for_a_third_call(fake):
    sent, reply = fake
    reply((QA.DEEPER, "stop"), (QA.DEEPER, "stop"))
    out = asyncio.run(QA.answer("Neden?", "anne-terligi"))
    assert out["handled"] and out["not_found"] and len(sent) == 2 and QA.DEEPER not in out["answer"]
    assert QA.DEEPER not in QA.DEEP_SYSTEM


def test_cut_deep_answer_is_kept_with_a_note(fake):
    sent, reply = fake
    reply(("", "length"), ("Uzun liste", "length"))
    out = asyncio.run(QA.answer("Karakterler kim?", "anne-terligi"))
    assert out["handled"] and out["answer"].startswith("Uzun liste") and QA.CUT_NOTE in out["answer"]


def test_library_question_does_not_deep_read(fake):
    sent, reply = fake
    sent.full["v"] = False
    reply((QA.DEEPER, "stop"))
    out = asyncio.run(QA.answer("Hangi kitapta deniz var?"))
    assert out["handled"] and out["answer"] == QA.LIBRARY_DEEPER and len(sent) == 1


def test_model_error_is_reported_not_answered(fake, monkeypatch):
    async def post(path, req, headers=None):
        return _Resp("bad gateway", status=502)
    monkeypatch.setattr(QA.llm, "_post", post)
    out = asyncio.run(QA.answer("Karakterler kim?", "anne-terligi"))
    assert out["handled"] is False and out["reason"] == "MODEL_UNAVAILABLE"


def test_not_found_is_flagged(fake):
    _, reply = fake
    reply(QA.NOT_FOUND + " Kapak tasarımcısı kayıtlarda yok.")
    assert asyncio.run(QA.answer("Kapak tasarımcısı kim?"))["not_found"] is True


def test_gateway_turns_thinking_off_unless_client_asked():
    p = {"messages": []}
    assert chat_params.without_thinking(p) and p["chat_template_kwargs"] == {"enable_thinking": False}
    keep = {"chat_template_kwargs": {"enable_thinking": True}}
    assert not chat_params.without_thinking(keep) and keep["chat_template_kwargs"]["enable_thinking"] is True


# --- 2026-10-02: kitap listesi ve kart, portal kartıyla aynı kaynaktan (güncel `catalog` çıktısı) ---------------
class _Cur:
    """Sorguya göre cevap veren sahte bağlantı; eski ed.book_card tablosu sorulursa test düşer."""

    def __init__(self, latest, crm=(), state=None):
        self.latest, self.crm, self.state, self.sql = latest, list(crm), state, []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        assert "book_card" not in sql, "eski tablo okunmamalı"
        rows = (self.latest if "current_artifact" in sql else self.crm if "book_crm_record" in sql
                else [self.state] if self.state else [])
        return type("R", (), {"fetchall": lambda _s: rows, "fetchone": lambda _s: rows[0] if rows else None})()


def _card(bid, key, **kw):
    return {"available": True, "card_id": key, "generation_id": f"g-{bid}", "title": kw.get("title", bid),
            "metadata": kw.get("metadata", []), "summary": [{"text": "Özet cümlesi.", "pages": [3]}],
            "themes": kw.get("themes", []), "key_events": kw.get("events", []),
            "characters": kw.get("characters", [])}


def test_library_reads_current_catalog_cards_not_legacy_table(monkeypatch):
    QA._CARDS.clear()
    calls = []

    def card(c, bid):
        calls.append(bid)
        return _card(bid, "k1", title="cicekci-kadin") if bid == "b1" else None

    monkeypatch.setattr(QA.read_model, "card", card)
    cur = _Cur([{"book_id": "b1", "generation_id": "g-b1", "page_count": 32, "build_key": "k1"}],
               crm=[{"book_id": "b1", "crm_title": "Çiçekçi Kadın", "authors": ["Yazar A"]}])
    books = QA.library(cur)
    assert [b["crm_title"] for b in books] == ["Çiçekçi Kadın"] and books[0]["page_count"] == 32
    assert QA.mentioned("çiçekçi kadın kimdir", books) == books
    QA.library(cur)
    assert calls == ["b1"]                      # aynı build_key: kart önbellekten


def test_library_skips_books_whose_latest_reading_has_no_current_card(monkeypatch):
    QA._CARDS.clear()
    monkeypatch.setattr(QA.read_model, "card", lambda c, bid: {**_card(bid, "k"), "available": False})
    assert QA.library(_Cur([{"book_id": "b1", "generation_id": "g", "page_count": 1, "build_key": "k"}])) == []
    assert QA.library(_Cur([])) == []


def test_card_block_uses_snapshot_characters_events_and_merges_chunk_themes():
    b = {"generation_id": "g", "title": "anne-terligi", "crm_title": "Anne Terliği", "crm_authors": ["Y"],
         "page_count": 24, "metadata": [{"subject": "AUTHOR", "claim": "Kitaptaki Yazar"}],
         "summary": [{"text": "Bir çocuk terliği arar.", "pages": [2, 5]}],
         "themes": [{"claim": "Aile", "source_pages": [3], "payload": {"level": "chunk"}},
                    {"claim": "aile", "source_pages": [9], "payload": {"level": "chunk"}}],
         "characters": [{"canonical_name": "Ece", "aliases": [], "identity_status": "CONFIRMED", "first_page": 2,
                         "description": "Ece: küçük kız.", "description_pages": [4]},
                        {"canonical_name": "Gölge", "aliases": [], "identity_status": "UNCERTAIN", "first_page": 1,
                         "description": "x", "description_pages": []}],
         "events": [{"id": "e2", "page_from": 7, "page_to": 8, "summary": "Terliği bulur.", "modality": "REALIZED",
                     "narrative_role": "RESOLUTION", "story_order": 2, "merged_into": None},
                    {"id": "e1", "page_from": 2, "page_to": 2, "summary": "Terlik kaybolur.", "modality": "REALIZED",
                     "narrative_role": "ORDINARY", "story_order": 1, "merged_into": None},
                    {"id": "e0", "page_from": 1, "page_to": 1, "summary": "birleşmiş", "modality": "REALIZED",
                     "narrative_role": None, "story_order": 0, "merged_into": "e1"}]}
    cur = _Cur([], state={"coverage_status": "PASSED", "semantic_status": "NEEDS_REVIEW"})
    head, lines = QA.card_block(b, cur, full=True)
    assert "### KİTAP: Anne Terliği" in head and "Yazar: Kitaptaki Yazar" in head and "Sayfa sayısı: 24" in head
    assert "Temalar: Aile [s.3,9]" in head and "kaynaklı taslak" in head
    assert "- Ece [adı ilk s.2]: Ece: küçük kız. [s.4]" in head and "Gölge" not in head
    assert lines == ["- s.2: Terlik kaybolur.", "- s.7-8 [resolution]: Terliği bulur."]
    head, lines = QA.card_block(b, cur, full=False)
    assert lines == [] and "Kilit olaylar: Terliği bulur. [s.7]" in head


def test_evidence_search_is_interactive_and_bounded(monkeypatch):
    from editor import retrieval
    seen = {}

    async def slow(gid, q, k, interactive=False):
        seen["interactive"] = interactive
        await asyncio.sleep(5)

    monkeypatch.setattr(retrieval, "search_book_evidence", slow)
    monkeypatch.setattr(QA, "EVIDENCE_TIMEOUT", 0.05)
    assert asyncio.run(QA._evidence("g", "soru")) == [] and seen["interactive"] is True


def test_fit_shares_room_when_cards_alone_do_not_fit(monkeypatch):
    monkeypatch.setattr(QA.budget, "estimate", lambda t, ratio=None: len(t))
    cards = ["\n".join(f"KİTAP {k} satır {i}" for i in range(40)) for k in "AB"]
    text = QA.fit(cards, [[], []], room=400)
    assert "KİTAP A satır 0" in text and "KİTAP B satır 0" in text
    assert text.count("satır daha alınmadı") == 2 and len(text) < 600


def test_deep_read_blocks_carry_imprint_pages_and_chapters(monkeypatch):
    from editor import catalog
    monkeypatch.setattr(catalog, "metadata_pages", lambda gid: [1, 2])
    monkeypatch.setattr(QA.source, "load", lambda c, gid, p: [{"spans": [{"text": "ÇEVİRİ Selen Demirtaş"}]}]
                        if p == 2 else [{"spans": []}])
    monkeypatch.setattr(QA.read_model, "artifact", lambda c, gid, kind: {"artifact": {"content": {"chapters": [
        {"title": "BÖReKlEr, KrEdİ KaRtI", "page_from": 7, "page_to": 30}, {"title": "Son", "page_from": 31,
                                                                          "page_to": 40}, "bozuk"]}}})
    b = {"generation_id": "g"}
    assert QA.front_block(b, None) == "KÜNYE SAYFALARI:\n- s.2: ÇEVİRİ Selen Demirtaş"
    ch = QA.chapter_block(b, None).split("\n")
    assert ch[0] == "BÖLÜMLER (sırasıyla):" and ch[1].startswith("- Börekler") and ch[2] == "- Son [s.31-40]"
    monkeypatch.setattr(QA.read_model, "artifact", lambda c, gid, kind: {"artifact": None})
    assert QA.chapter_block(b, None) == ""
