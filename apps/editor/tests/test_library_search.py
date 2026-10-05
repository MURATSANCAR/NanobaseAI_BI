"""Kütüphane geneli Kitaba sor (2026-10-05): kitap adı geçmeyen soruda aday kitap seçimi (anlamsal + sözcük + karakter
adı) ve bağlam. Arama ve model sahte; kitap kayıtları uydurma."""
import asyncio
import contextlib
import types

from editor import library_search as LS, quick_answer as QA


def _book(bid, title, *, summary=(), events=(), characters=(), gid=None):
    return {"book_id": bid, "generation_id": gid or f"g{bid}", "card_key": f"k{bid}", "title": title,
            "crm_title": None, "crm_authors": [], "page_count": 40, "metadata": [], "themes": [],
            "summary": [{"text": t, "pages": p} for t, p in summary],
            "events": [{"id": f"e{i}", "summary": t, "page_from": p, "merged_into": None}
                       for i, (t, p) in enumerate(events)],
            "characters": [{"canonical_name": n, "aliases": list(a), "identity_status": "CONFIRMED",
                            "first_page": 3, "description": d, "description_pages": [4]} for n, a, d in characters],
            "other_characters": [], "names": [title], "recommendation": None}


FOX = _book("1", "Orman Kitabı", summary=[("Tilki hasta kızın penceresine gelir.", [12])],
            characters=[("Bee", ["Arı"], "Hasta kız.")])
SHOP = _book("2", "Dükkân", summary=[("Kadın bir bitki dükkânı açar.", [7])],
             events=[("Kadın dükkâna çiçek dizer.", 9)])
GRAND = _book("3", "Büyükbaba", events=[("Dedem yaşlanınca çocuk gibi oyun oynar.", 15)])
BOOKS = [FOX, SHOP, GRAND]


def _prepared(books=BOOKS, keys=None):
    return LS.prepare(books, None) | {"keys": keys or {}}


def test_stems_fold_turkish_suffixes_and_drop_question_words():
    assert LS.stem("dedesinin") == LS.stem("dedem") == "dede"
    assert LS.stems("Tilkinin hasta kızla bağ kurduğu kitap hangisi?") >= {"tilk", "hast"}
    assert not LS.stems("hangi kitap") and "kita" not in LS.stems("kitabımız var mı")


def test_mentioned_ignores_titles_that_carry_no_name():
    generic = {"names": ["Kitap"]}
    second = {"names": ["2. Kitap"]}
    real = {"names": ["Gölge Tilki"]}
    q = "Bir tilkinin hasta bir kızla bağ kurduğu kitap hangisi? Gölge Tilki olabilir mi?"
    assert QA.mentioned(q, [generic, second, real]) == [real]
    assert QA.mentioned("Hangi kitap 2. kitap?", [generic, second]) == []


def test_short_series_name_in_a_library_question_keeps_the_library_search():
    series = {"crm_title": "Alparslan - Çift Başlı Kartallar", "title": "alparslan",
              "names": ["alparslan", "Alparslan - Çift Başlı Kartallar", "Alparslan"]}
    q = "Sultan Alparslan dönemini anlatan kitaplarımız hangileri?"
    assert QA.mentioned(q, [series]) == [series] and QA.library_intent(q) and QA.weak_mention(q, series)
    single = {"crm_title": "Pinokyo", "title": "pinokyo", "names": ["pinokyo", "Pinokyo"]}
    assert not QA.weak_mention("Pinokyo gibi kitaplarımız hangileri?", single)
    assert not QA.weak_mention("Alparslan Çift Başlı Kartallar kitabında kimler var?", series)
    assert not QA.library_intent("Alparslan kimdir?")


def test_title_genre_and_themes_are_searched():
    b = {**_book("9", "Güzel Ahlakım"), "themes": [{"claim": "Dürüstlük", "source_pages": [8]}],
         "recommendation": {"category": ["Çocuk", "Dini"]}}
    docs = {"9": LS.book_docs(b, None), **{x["book_id"]: LS.book_docs(x, None) for x in BOOKS}}
    out = LS.lexical("ahlak ve din kitapları", [b, *BOOKS], docs)
    assert list(out) == ["9"] and out["9"]["hits"][0]["kind"] == "kitap adı ve türü"
    assert {"kind": "tema", "text": "Dürüstlük", "pages": [8]} in [
        {k: d[k] for k in ("kind", "text", "pages")} for d in docs["9"]]


def test_character_name_matches_only_a_capitalised_exact_name():
    assert LS.name_matches("Kızın Bee diye çağrıldığı kitap hangisi?", BOOKS) == {"1": ["Bee"]}
    assert LS.name_matches("Bee'nin tilkisi", BOOKS) == {"1": ["Bee"]}
    assert LS.name_matches("bee diye bir sözcük", BOOKS) == {}        # küçük harfli: ad sayılmaz
    assert LS.name_matches("Arı ile tanışan kız", BOOKS) == {"1": ["Bee"]}   # diğer adı


def test_lexical_ranks_summary_events_and_characters_with_pages():
    docs = {b["book_id"]: LS.book_docs(b, None) for b in BOOKS}
    out = LS.lexical("Bir çocuğun dedesinin yaşlanıp çocuk gibi davrandığı kitap", BOOKS, docs)
    assert max(out, key=lambda k: out[k]["score"]) == "3"
    assert out["3"]["hits"][0] == {**out["3"]["hits"][0], "kind": "olay", "pages": [15]}
    out = LS.lexical("Bitki dükkânı açan kadın", BOOKS, docs)
    assert max(out, key=lambda k: out[k]["score"]) == "2" and out["2"]["hits"][0]["pages"] == [7]


def test_book_docs_reads_chapter_summaries(monkeypatch):
    QA_RM = LS.read_model
    monkeypatch.setattr(QA_RM, "artifact", lambda c, gid, kind: {"artifact": {"content": {"chapters": [
        {"title": "1", "sentences": [{"text": "Bölümde tilki kaçar.", "pages": [20, 21]}]}]}}})
    LS._DOCS.clear()
    docs = LS.book_docs(FOX, object())
    assert {"kind": "bölüm özeti", "text": "Bölümde tilki kaçar.", "pages": [20, 21]} in [
        {k: d[k] for k in ("kind", "text", "pages")} for d in docs]
    assert any(d["kind"] == "karakter" and d["text"].startswith("Bee, Arı: Hasta kız.") for d in docs)
    LS._DOCS.clear()


def test_candidates_fuse_semantic_lexical_and_names(monkeypatch):
    async def sem(question, keys, **kw):
        return {"g2": {"score": 0.8, "hits": [{"kind": "metin", "text": "Çiçekleri suladı.", "pages": [30]}]},
                "g3": {"score": 0.5, "hits": []}}
    monkeypatch.setattr(LS, "semantic", sem)
    found, stats = asyncio.run(LS.candidates("Bee adlı hasta kız ve tilki", BOOKS, _prepared(), top=2))
    assert found[0]["book"] is FOX and "karakter adı: Bee" in found[0]["reasons"]
    assert stats["name_books"] == 1 and stats["semantic_books"] == 2
    found, _ = asyncio.run(LS.candidates("bitki dükkânı", BOOKS, _prepared(), top=1))
    assert [x["book"] for x in found] == [SHOP]
    assert found[0]["hits"][0]["text"] == "Çiçekleri suladı." and found[0]["hits"][1]["kind"] in ("özet", "olay")


def test_candidates_survive_a_failed_semantic_search(monkeypatch):
    async def down(question, keys, **kw):
        raise RuntimeError("unknown model")
    monkeypatch.setattr(LS, "semantic", down)
    found, stats = asyncio.run(LS.candidates("dedesi yaşlanıp çocuk gibi olan", BOOKS, _prepared()))
    assert found[0]["book"] is GRAND and "unknown model" in stats["semantic_error"]


def test_semantic_groups_by_book_and_drops_stale_index_points(monkeypatch):
    from editor import retrieval
    seen = {}

    def hit(gid, key, score, page):
        return types.SimpleNamespace(score=score, payload={"generation_id": gid, "build_key": key, "kind": "event",
                                                           "page_no": page, "text": f"olay {page}"})

    class Q:
        async def query_points_groups(self, coll, **kw):
            seen.update(kw)
            return types.SimpleNamespace(groups=[
                types.SimpleNamespace(id="g1", hits=[hit("g1", "new", 0.9, 5), hit("g1", "old", 0.95, 6)]),
                types.SimpleNamespace(id="g2", hits=[hit("g2", "old", 0.99, 1)])])

    async def vec(q):
        return [0.0]
    monkeypatch.setattr(retrieval, "qdrant", lambda: Q())
    monkeypatch.setattr(LS, "question_vector", vec)
    out = asyncio.run(LS.semantic("soru", {"g1": "new", "g2": "new"}))
    assert list(out) == ["g1"] and out["g1"]["hits"] == [{"kind": "olay", "text": "olay 5", "pages": [5]}]
    assert seen["group_by"] == "generation_id" and len(seen["query_filter"].should) == 2


def _library_ctx(monkeypatch, found):
    QA._CARDS.clear()
    books = [dict(b) for b in BOOKS]
    monkeypatch.setattr(QA.foundation, "read_snapshot", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(QA, "library", lambda c: books)
    monkeypatch.setattr(QA, "card_block", lambda b, c, full: (f"### KİTAP: {b['title']}\nÖzet: ...", []))
    monkeypatch.setattr(QA.budget, "estimate", lambda t, ratio=None: len(t) // 4)
    monkeypatch.setattr(QA.budget, "for_call", lambda alias, n: types.SimpleNamespace(input=100000))

    async def cands(question, bs, prepared, top=5, named=None):
        by = {b["book_id"]: b for b in bs}
        return [{"book": by[i], "score": 1.0, "reasons": ["içerik benzerliği"], "hits": h} for i, h in found], {}
    monkeypatch.setattr(LS, "candidates", cands)
    monkeypatch.setattr(LS, "prepare", lambda bs, c: {})
    return books


def test_library_context_puts_candidates_with_their_pages_and_names_the_rest(monkeypatch):
    _library_ctx(monkeypatch, [("1", [{"kind": "olay", "text": "Tilki kıza gelir.", "pages": [12]}])])
    ctx, books, full = asyncio.run(QA.context("Tilkinin kızla dost olduğu kitap hangisi?", None))
    assert not full and books[0]["book_id"] == "1" and books[0]["candidate"] and not books[1].get("candidate")
    assert QA.LIBRARY_NOTE in ctx
    assert ctx.index("### KİTAP: Orman Kitabı") < ctx.index("- [s.12] (olay) Tilki kıza gelir.")
    assert "### KİTAP: Dükkân" not in ctx and "yalnız adları" in ctx and "Dükkân" in ctx and "Büyükbaba" in ctx


def test_library_question_reads_deeper_when_candidates_exist(monkeypatch):
    _library_ctx(monkeypatch, [("1", [])])
    sent = []

    async def post(path, req, headers=None):
        sent.append(req)
        content = QA.NOT_FOUND if len(sent) == 1 else "«Orman Kitabı» [s.12]."
        return types.SimpleNamespace(status_code=200, text=content, json=lambda: {
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {}})

    async def more(question, keys, **kw):
        return {"g1": {"score": 0.7, "hits": [{"kind": "metin", "text": "Kız pencereyi açar.", "pages": [13]}]}}
    monkeypatch.setattr(QA.llm, "_post", post)
    monkeypatch.setattr(LS, "semantic", more)
    monkeypatch.setattr(LS, "index_keys", lambda c, gids: {g: "k" for g in gids})
    out = asyncio.run(QA.answer("Tilkinin kızla dost olduğu kitap hangisi?"))
    assert out["deep"] and out["answer"] == "«Orman Kitabı» [s.12]." and out["candidates"] == ["Orman Kitabı"]
    assert len(sent) == 2 and "- [s.13] (metin) Kız pencereyi açar." in sent[1]["messages"][1]["content"]
