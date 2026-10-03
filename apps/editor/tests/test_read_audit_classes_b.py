"""Okuma denetimi düzeltmeleri B (2026-10-03): künye, kimlik, özet, «Zeki'ye sor». Hiçbir kitap, ad ya da sayfa
numarası koddan okunmaz; buradaki adlar ve metinler elle yazılmıştır. Model, geçit ve veritabanı yok — taklit edilir.

K1. Kısmi künye: TITLE/AUTHOR/PUBLISHER eksikse yalnız eksik alanlar kapak + künye sayfalarından bir kez daha sorulur.
K3. Aynı adın çocuk ve yetişkin kaydı (büyüyen kişi) birleşir; adaşlar (aynı sayfa, sıra dışı, farklı sıra sayısı ya
    da baba adı) ve insan↔hayvan birleşmez.
K6. Yinelenen özet cümlesi denemeyi düşürmez: tek cümleye iner, referansları birleşir.
K7. Sayfa sorusu: sayfa metni bağlama girer; sayfa varsa «bulunamadı» yerine derin okuma, yoksa «Kitap N sayfa».
K8. Künyede yaş/tür yoksa içerikten önerilen kategori/yaş kartta; kütüphane geneli soruda yaş/kategori eşleşmesi.
Ek. Yeniden üretim kitap sürümü başına yalnız en son okunmuş nesli işler.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


def _missing(root: str) -> bool:
    try:
        return importlib.util.find_spec(root) is None
    except ValueError:
        return False


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx",
             "yaml", "pymupdf", "qdrant_client", "qdrant_client.models"):
    _root = _mod.split(".")[0]
    if _missing(_root) or _root in sys.modules and isinstance(sys.modules[_root], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))

from editor import catalog, identity, outputs, page_scope, quick_answer as QA  # noqa: E402

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "editor"


# ------------------------------------------------------------------ K1. kısmi künye
def test_missing_core_fields_and_cover_page():
    assert catalog.missing_fields([{"subject": "ISBN"}, {"subject": "EDITION"}]) == ["TITLE", "AUTHOR", "PUBLISHER"]
    assert catalog.missing_fields([{"subject": s} for s in ("TITLE", "AUTHOR", "PUBLISHER")]) == []
    assert catalog.with_cover({4, 2}, {}, True) == [1, 2, 4]
    # editör kapağı hikâye sayfası saydıysa kapak okunmaz; otomatik STORY rolü kapağı dışlamaz
    assert catalog.with_cover({2}, {1: {"role": "STORY", "source": "editor"}}, True) == [2]
    assert catalog.with_cover({2}, {1: {"role": "STORY", "source": "auto"}}, True) == [1, 2]
    assert catalog.with_cover(set(), {}, False) == []


def test_refill_keeps_only_the_asked_fields_with_verbatim_quote():
    class Idx:
        def matching_spans(self, page, quote):
            return [{"idx": 0}] if quote in {1: "Ayşe Yılmaz Kırmızı Kedi", 2: "Örnek Yayınları"}.get(page, "") else []
    fields = [{"field": "AUTHOR", "value": "Ayşe Yılmaz", "page": 1, "quote": "Ayşe Yılmaz"},
              {"field": "ISBN", "value": "978", "page": 2, "quote": "978"},
              {"field": "PUBLISHER", "value": "Örnek", "page": 2, "quote": "Uydurma Yayınevi"}]
    kept = catalog.keep_fields(fields, Idx(), only=["AUTHOR", "PUBLISHER"])
    assert [f["field"] for f in kept] == ["AUTHOR"]          # ISBN sorulmadı, PUBLISHER alıntısı sayfada yok


def _fake_catalog(monkeypatch, rows, refill_done, asked):
    fake_db = types.SimpleNamespace(one=lambda sql, *a: {"sealed_at": None}, tx=contextlib.nullcontext)
    monkeypatch.setattr(catalog, "db", fake_db)
    monkeypatch.setattr(catalog, "ledger", types.SimpleNamespace(
        PageIndex=types.SimpleNamespace(load=lambda c, gid: None),
        evidence_from_model=lambda *a, **k: [], save_claim=lambda *a, **k: None))
    monkeypatch.setattr(catalog, "_valid_pages", lambda c, gid: set())
    monkeypatch.setattr(catalog, "_metadata_rows", lambda gid: list(rows))
    monkeypatch.setattr(catalog, "_refill_done", lambda gid: refill_done)
    monkeypatch.setattr(catalog, "metadata_pages", lambda gid: [1, 2])

    async def ask(gid, pages, only=None):
        asked.append((pages, only))
        return [], 7
    monkeypatch.setattr(catalog, "_ask", ask)


def test_partial_imprint_is_asked_again_once_for_missing_fields_only(monkeypatch):
    rows = [{"subject": "ISBN", "claim": "978-1", "source_pages": [2], "id": "x"}]
    asked = []
    _fake_catalog(monkeypatch, rows, False, asked)
    got = asyncio.run(catalog.extract_metadata("g"))
    assert asked == [([1, 2], ["TITLE", "AUTHOR", "PUBLISHER"])]
    assert got == {"ISBN": [{"value": "978-1", "pages": [2], "claim_id": "x"}]}      # mevcut iddia korunur
    asked.clear()
    _fake_catalog(monkeypatch, rows, True, asked)                                    # ek çağrı yapılmış
    asyncio.run(catalog.extract_metadata("g"))
    assert asked == []
    full = rows + [{"subject": s, "claim": "v", "source_pages": [1], "id": s} for s in ("TITLE", "AUTHOR", "PUBLISHER")]
    _fake_catalog(monkeypatch, full, False, asked)
    asyncio.run(catalog.extract_metadata("g"))
    assert asked == []                                                               # eksik yok: model yok
    _fake_catalog(monkeypatch, [], False, asked)
    asyncio.run(catalog.extract_metadata("g"))
    assert asked == [([1, 2], None)]                                                 # künye yok: tam okuma


def test_rebuild_path_reads_missing_fields_without_new_imprint_pages(monkeypatch):
    calls = []

    async def extract_metadata(gid):
        calls.append(gid)
        return {"ISBN": [{}], "AUTHOR": [{}]}
    fake = types.ModuleType("editor.catalog")
    fake.extract_metadata = extract_metadata
    fake.needs_metadata = lambda gid: True
    monkeypatch.setitem(sys.modules, "editor.catalog", fake)
    import editor
    monkeypatch.setattr(editor, "catalog", fake, raising=False)
    got = asyncio.run(page_scope.metadata_after_scope("g", {"front_matter_written": []}))
    assert calls == ["g"] and got == {"fields": ["AUTHOR", "ISBN"], "pages": []}
    fake.needs_metadata = lambda gid: False
    assert asyncio.run(page_scope.metadata_after_scope("g", {"front_matter_written": []})) is None
    assert calls == ["g"]


def test_refill_prompt_exists_and_is_versioned():
    text = (SRC / "prompts" / "book_metadata_missing.md").read_text(encoding="utf-8")
    assert text.startswith("<!-- name: book_metadata_missing version: 1 -->")
    assert "{{pages_text}}" in text and "{{fields}}" in text


# ------------------------------------------------------------------ K3. çocuk/yetişkin
def _p(name, kind, pages, sex="MALE", aliases=(), windows=(), n=None):
    return {"name": name, "kind": kind, "sex": sex, "entity_scope": "INDIVIDUAL", "pages": set(pages),
            "windows": set(windows), "aliases": list(aliases), "n": n if n is not None else len(pages)}


def test_child_and_adult_kinds_are_life_stages_not_a_conflict():
    child, adult = {"kind": "HUMAN_CHILD"}, {"kind": "HUMAN_ADULT"}
    assert identity.incompatible([child], [adult]) == "KIND_CONFLICT"            # varsayılan katı
    assert identity.incompatible([child], [adult], life_stages=True) is None
    assert identity.incompatible([child], [{"kind": "ANIMAL"}], life_stages=True) == "KIND_CONFLICT"
    assert identity.incompatible([adult], [{"kind": "ROBOT_OR_MACHINE"}], life_stages=True) == "KIND_CONFLICT"
    assert identity.incompatible([{**child, "sex": "MALE"}], [{**adult, "sex": "FEMALE"}],
                                 life_stages=True) == "SEX_CONFLICT"


def test_growing_character_folds_into_one_record():
    units = [_p("Ali", "HUMAN_CHILD", range(3, 40), windows=[0, 1]), _p("Ali", "HUMAN_ADULT", range(60, 200),
                                                                        windows=[3, 4, 5])]
    clusters, refused = identity.same_name_plan(units, lambda n: True)
    assert clusters == [[1, 0]] and refused == []
    # çerçeve anlatı: yetişkin başta ve sonda, çocukluk arada
    frame = [_p("Ali", "HUMAN_ADULT", [1, 2, 150]), _p("Ali", "HUMAN_CHILD", range(10, 140))]
    assert identity.same_name_plan(frame, lambda n: True)[0] == [[1, 0]]
    # cinsiyet bilinmiyorsa engel değil
    units = [_p("Deniz", "HUMAN_CHILD", [5, 6], sex="UNKNOWN"), _p("Deniz", "HUMAN_ADULT", [80, 90])]
    assert identity.same_name_plan(units, lambda n: True)[0] == [[0, 1]]


def test_namesakes_are_not_folded():
    def plan(units):
        return identity.same_name_plan(units, lambda n: True)
    # aynı sayfada ikisi birden: iki kişi
    clusters, refused = plan([_p("Ali", "HUMAN_CHILD", [3, 50]), _p("Ali", "HUMAN_ADULT", [50, 90])])
    assert clusters == [] and refused[0]["reason"] == "SAME_PAGE"
    # dede ve adını taşıyan torun yan yana anlatılıyor: çocuk yetişkinin son sayfasından sonra da var
    clusters, refused = plan([_p("Ahmed", "HUMAN_ADULT", [5, 40, 100]), _p("Ahmed", "HUMAN_CHILD", [10, 70, 160])])
    assert clusters == [] and refused[0]["reason"] == "LIFE_STAGE_ORDER"
    # çocuk yetişkinden sonra başlıyor (oğul babanın adını almış)
    clusters, refused = plan([_p("Ahmed", "HUMAN_ADULT", [5, 40, 100]), _p("Ahmed", "HUMAN_CHILD", [20, 90])])
    assert clusters == [] and refused[0]["reason"] == "LIFE_STAGE_ORDER"
    # tarih kitabı: farklı sıra sayısı (aynı tür, ayrı sayfalar)
    clusters, refused = plan([_p("Abdülhamid", "HUMAN_ADULT", [3, 4], aliases=["I. Abdülhamid"]),
                              _p("Abdülhamid", "HUMAN_ADULT", [80, 81], aliases=["Sultan Abdülhamid II"])])
    assert clusters == [] and refused[0]["reason"] == "DIFFERENT_ORDINAL"
    # aynı sıra sayısı iki yazımla («II.» / «2.») birleşir
    clusters, _ = plan([_p("Abdülhamid", "HUMAN_CHILD", [3, 4], aliases=["II. Abdülhamid"]),
                        _p("Abdülhamid", "HUMAN_ADULT", [80, 81], aliases=["2. Abdülhamid"])])
    assert clusters == [[0, 1]]
    # farklı baba adı
    clusters, refused = plan([_p("Mehmed", "HUMAN_ADULT", [3], aliases=["Ahmed oğlu Mehmed"]),
                              _p("Mehmed", "HUMAN_ADULT", [90], aliases=["Mehmed bin Hasan"])])
    assert clusters == [] and refused[0]["reason"] == "DIFFERENT_FATHER"
    # insan ↔ hayvan aynen reddedilir
    clusters, refused = plan([_p("Pamuk", "HUMAN_CHILD", [3]), _p("Pamuk", "ANIMAL", [90])])
    assert clusters == [] and refused[0]["reason"] == "KIND_CONFLICT"


def test_cross_window_join_of_child_and_adult_needs_life_order():
    by_mid = {"m1": {"page_no": 5, "surface_name": "Ali"}, "m2": {"page_no": 120, "surface_name": "Ali"},
              "m3": {"page_no": 130, "surface_name": "Ali"}}
    child = [{"canonical_name": "Ali", "kind": "HUMAN_CHILD", "sex": "MALE", "mention_ids": ["m1"]}]
    adult = [{"canonical_name": "Ali", "kind": "HUMAN_ADULT", "sex": "MALE", "mention_ids": ["m2"]}]
    from editor import ledger
    book = ledger.norm("Küçük Ali büyüdü ve Ali öğretmen oldu.")
    assert identity.cross_guard(child, adult, {0}, {3}, "Ali büyüdü ve Ali öğretmen oldu", book, by_mid) is None
    late_child = [{**child[0], "mention_ids": ["m3"]}]
    early_adult = [{**adult[0], "mention_ids": ["m1"]}]
    assert identity.cross_guard(late_child, early_adult, {0}, {3}, "Ali büyüdü ve Ali öğretmen oldu", book,
                                by_mid) == "LIFE_STAGE_ORDER"


def test_identity_fold_uses_the_same_rule():
    src = (SRC / "identity_fold.py").read_text(encoding="utf-8")
    assert "from .identity import proper_name_test, same_name_plan" in src
    assert '"aliases": list(r["aliases"] or [])' in src


# ------------------------------------------------------------------ K6. yinelenen özet cümlesi
def _claims():
    claims = [{"id": "a", "kind": "EVENT", "claim": "Ali eve döndü.", "source_pages": [3], "payload": {}},
              {"id": "b", "kind": "EVENT", "claim": "Ali eve döndü.", "source_pages": [9], "payload": {}},
              {"id": "c", "kind": "EVENT", "claim": "Kapı açıktı.", "source_pages": [12], "payload": {}},
              {"id": "d", "kind": "EVENT", "claim": "Ayşe güldü.", "source_pages": [20], "payload": {}}]
    evidence = [{"claim_id": c["id"], "id": f"e{c['id']}", "quote_verified": True} for c in claims]
    return claims, evidence


def test_repeated_sentence_is_merged_not_rejected():
    claims, evidence = _claims()
    allowed = {c["id"]: c for c in claims}
    rows = outputs.bind_sentences({"sentences": [
        {"text": "Ali eve döndü.", "claim_ids": ["a"]}, {"text": "Ayşe güldü.", "claim_ids": ["d"]},
        {"text": "Ali eve döndü.", "claim_ids": ["b"]}, {"text": "Ali eve döndü.", "claim_ids": ["c"]}]},
        claims, evidence)
    got = outputs.merge_repeats(rows, allowed, evidence)
    assert [r["text"] for r in got] == ["Ali eve döndü.", "Ayşe güldü."]
    # kelimesi kelimesine kopya: yalnız kopyaladığı iddialar kalır (c'nin sayfası cümlenin söylemediğini anardı)
    assert got[0]["claim_ids"] == ["a", "b"] and got[0]["pages"] == [3, 9] and got[0]["evidence_ids"] == ["ea", "eb"]
    assert outputs.exact_copy(got[0]["text"], [allowed["a"], allowed["b"]])
    assert not outputs.exact_copy("Ali eve döndü.", [allowed["a"], allowed["c"]])
    # kopya olmayan yinelenen cümle: referanslar birleşir, eleştirmen karar verir
    rows = outputs.bind_sentences({"sentences": [{"text": "Ali döndü, kapı açıktı.", "claim_ids": ["a"]},
                                                 {"text": "Ali döndü, kapı açıktı.", "claim_ids": ["c"]}]},
                                  claims, evidence)
    got = outputs.merge_repeats(rows, allowed, evidence)
    assert len(got) == 1 and got[0]["claim_ids"] == ["a", "c"] and got[0]["pages"] == [3, 12]


def test_summary_with_a_repeat_is_accepted_on_the_first_attempt(monkeypatch):
    claims, evidence = _claims()
    snap = {"generation_id": "g", "claims": claims, "evidence": evidence,
            "events": [{"claim_id": c["id"], "importance": 0.5} for c in claims], "scope": {}}
    calls, critic_rows = [], []

    class FakeLlm:
        def __init__(self, gid):
            pass

        async def chat(self, alias, messages, **kw):
            calls.append(kw["prompt"].name)
            if kw["prompt"].name == "revision_summary":
                return {"sentences": [{"text": "Ali eve döndü.", "claim_ids": ["c0"]},
                                      {"text": "Ali eve döndü.", "claim_ids": ["c1"]},
                                      {"text": "Ayşe güldü.", "claim_ids": ["c3"]}]}, 1
            import json
            checks = json.loads(messages[0]["content"][len(outputs.JUDGE_PROMPT):])
            critic_rows.append(len(checks))
            return {"verdicts": [{"index": i, "reason": "", "supported": True} for i in range(len(checks))]}, 2

    import editor.llm as llm
    monkeypatch.setattr(llm, "Llm", FakeLlm)
    out = asyncio.run(outputs.summarize(snap, claims, "Özet"))
    assert out["status"] == "SOURCE_SUPPORTED_DRAFT" and out["attempts"] == 1 and out["rejected_attempts"] == []
    assert [s["text"] for s in out["sentences"]] == ["Ali eve döndü.", "Ayşe güldü."]
    assert out["sentences"][0]["claim_ids"] == ["a", "b"] and critic_rows == [2]
    assert out["sentences"][0]["support_check"] == "EXACT_VERIFIED_CLAIM"
    assert "repeats an identical sentence" not in (SRC / "outputs.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------ K7. sayfa sorusu
@pytest.mark.parametrize("q,pages", [
    ("45. sayfada ne anlatılıyor?", [45]),
    ("Sayfa 45'te ne oluyor", [45]),
    ("45-47. sayfalarda neler var", [45, 46, 47]),
    ("45 ile 47. sayfalar arası", [45, 46, 47]),
    ("s. 45 ne diyor", [45]),
    ("s.12'de ne oluyor?", [12]),
    ("45'inci sayfa", [45]),
    ("sayfa 10-12 özetle", [10, 11, 12]),
    ("12. sayfada 3 kişi var mı", [12]),
    ("Kitap kaç sayfa?", []),
    ("45 sayfalık bir kitap mı", []),
    ("3-6 yaş için kitap", []),
])
def test_page_refs(q, pages):
    assert QA.page_refs(q) == pages


def _qbook(**kw):
    return {"book_id": "b", "generation_id": "g", "title": "kitap", "crm_title": "Kitap", "page_count": 32,
            "summary": [{"text": "Ali eve döner.", "pages": [12]}],
            "events": [{"page_from": 11, "page_to": 13, "summary": "Ali kapıyı açar.", "merged_into": None},
                       {"page_from": 20, "page_to": 20, "summary": "Başka olay.", "merged_into": None}], **kw}


def test_page_block_puts_the_page_text_events_and_summary(monkeypatch):
    def load(c, gid, p):
        if p == 13:
            raise KeyError(p)
        return [{"page_no": p, "spans": [{"text": f"Sayfa {p} metni."}]}]
    monkeypatch.setattr(QA.source, "load", load)
    block, info = QA.page_block(_qbook(), None, [12, 13, 40, 41])
    assert "- s.12: Sayfa 12 metni." in block and "Ali kapıyı açar." in block and "Başka olay" not in block
    assert "Ali eve döner." in block
    assert info == {"present": [12], "missing": [13, 40, 41], "page_count": 32}
    assert "Kitap 32 sayfa; sorulan s.13, 40-41 kitapta yok." in block


def test_context_places_the_page_text_right_after_the_title(monkeypatch):
    monkeypatch.setattr(QA.foundation, "read_snapshot", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(QA, "library", lambda c: [_qbook(names=["Kitap"], metadata=[], themes=[], characters=[],
                                                         crm_authors=[])])
    monkeypatch.setattr(QA, "card_block", lambda b, c, full: ("### KİTAP: Kitap\nÖzet: uzun özet", []))
    monkeypatch.setattr(QA.source, "load", lambda c, gid, p: [{"page_no": p, "spans": [{"text": "Metin."}]}])

    async def ev(gid, q, k=QA.EVIDENCE_K):
        return []
    monkeypatch.setattr(QA, "_evidence", ev)
    monkeypatch.setattr(QA.budget, "estimate", lambda t, ratio=None: len(t))
    monkeypatch.setattr(QA.budget, "for_call", lambda alias, n: types.SimpleNamespace(input=100000))
    ctx, books, full = asyncio.run(QA.context("12. sayfada ne anlatılıyor?", "Kitap"))
    assert full
    assert ctx.index("### KİTAP") < ctx.index("- s.12: Metin.") < ctx.index("Özet: uzun özet")
    assert books[0]["asked_pages"]["present"] == [12]


class _Resp:
    def __init__(self, content):
        self.status_code, self._c, self.text = 200, content, content

    def json(self):
        return {"choices": [{"message": {"content": self._c}, "finish_reason": "stop"}], "usage": {}}


def _answer(monkeypatch, asked, *replies):
    sent = []

    async def ctx(q, t, deep=False):
        return ("DERIN" if deep else "KAYIT"), [{"crm_title": "Kitap", "title": "kitap", "asked_pages": asked}], True
    monkeypatch.setattr(QA, "context", ctx)

    async def post(path, req):
        sent.append(req)
        return _Resp(replies[min(len(sent), len(replies)) - 1])
    monkeypatch.setattr(QA.llm, "_post", post)
    return asyncio.run(QA.answer("45. sayfada ne anlatılıyor?", "Kitap")), sent


def test_missing_page_is_answered_with_the_page_count_without_a_model_call(monkeypatch):
    out, sent = _answer(monkeypatch, {"present": [], "missing": [45], "page_count": 32}, "x")
    assert sent == [] and out["handled"] and out["answer"] == "«Kitap» 32 sayfa; 45. sayfa kitapta yok."


def test_present_page_not_found_goes_to_the_deeper_read(monkeypatch):
    out, sent = _answer(monkeypatch, {"present": [45], "missing": [], "page_count": 120},
                        QA.NOT_FOUND + " Kayıtlarda yok.", "Ali kapıyı açar [s.45].")
    assert len(sent) == 2 and out["handled"] and out["deep"] and out["answer"].startswith("Ali kapıyı")
    assert "DERIN" in sent[1]["messages"][1]["content"]
    out, _ = _answer(monkeypatch, {"present": [45], "missing": [], "page_count": 120}, "Ali eve döner [s.45].")
    assert out["handled"] and out["answer"].startswith("Ali")


# ------------------------------------------------------------------ K8. yaş/tür önerisi
def test_card_shows_suggested_age_and_category_when_the_imprint_has_none():
    class Cur:
        def execute(self, sql, params=None):
            return type("R", (), {"fetchone": lambda _s: None, "fetchall": lambda _s: []})()
    b = _qbook(metadata=[], themes=[], characters=[], crm_authors=[],
               recommendation={"category": ["Çocuk", "Okul Öncesi", "Korku"], "audience": "CHILD",
                               "age_from": 3, "age_to": 6})
    head, _ = QA.card_block(b, Cur(), full=False)
    assert "Yaş (künyede yazmıyor; içerikten önerilen): 3-6" in head
    assert "Tür (künyede yazmıyor; içerikten önerilen): Çocuk > Okul Öncesi > Korku" in head
    b["metadata"] = [{"subject": "AGE_RANGE", "claim": "7-10 Yaş"}]
    head, _ = QA.card_block(b, Cur(), full=False)
    assert "Yaş: 7-10 Yaş" in head and "Yaş (künyede" not in head


@pytest.mark.parametrize("q,age", [("okul öncesi korku kitabı", (3, 6)), ("3-6 yaş için", (3, 6)),
                                   ("8+ yaş kitap", (8, None)), ("5 yaşındaki çocuğa", (5, 5)),
                                   ("ilkokul çocukları için", (7, 10)), ("macera romanı", None)])
def test_question_age(q, age):
    assert QA.question_age(q) == age


def test_library_question_matches_age_and_category_from_suggestion():
    def bk(bid, title, meta=(), rec=None):
        return {"book_id": bid, "title": title, "crm_title": None, "metadata": list(meta), "recommendation": rec}
    books = [bk("1", "Roman", rec={"category": ["Yetişkin", "Roman"], "age_from": 16, "age_to": None}),
             bk("2", "Gece Sesleri", rec={"category": ["Çocuk", "Okul Öncesi", "Korku"], "age_from": 3, "age_to": 6}),
             bk("3", "Renkler", meta=[{"subject": "AGE_RANGE", "claim": "3-6 Yaş"}]),
             bk("4", "Hayalet Okul", meta=[{"subject": "GENRE", "claim": "Korku"}],
                rec={"category": ["Çocuk", "Korku"], "age_from": 9, "age_to": 12})]
    ordered, lines = QA.library_match("okul öncesi korku kitabı var mı?", books)
    assert [b["book_id"] for b in ordered] == ["2", "3", "4", "1"]       # hiçbir kitap düşmez
    assert "Yaşı örtüşen kitaplar: Gece Sesleri, Renkler." in lines[0]
    assert "Gece Sesleri" in lines[1] and "Hayalet Okul" in lines[1] and "Roman" not in lines[1]
    assert lines[2] == "İkisi birden eşleşen kitaplar: Gece Sesleri."


def test_library_reads_the_latest_ok_suggestion(monkeypatch):
    QA._CARDS.clear()

    class Cur:
        def __init__(self):
            self.sql = []

        def execute(self, sql, params=None):
            self.sql.append(sql)
            rows = ([{"book_id": "b1", "generation_id": "g", "page_count": 24, "build_key": "k"}]
                    if "current_artifact" in sql else [{"ok": True}] if "to_regclass" in sql
                    else [{"book_id": "b1", "category": ["Çocuk", "Korku"], "audience": "CHILD", "age_from": 3,
                           "age_to": 6}] if "book_recommendation" in sql else [])
            return type("R", (), {"fetchall": lambda _s: rows, "fetchone": lambda _s: rows[0] if rows else None})()
    monkeypatch.setattr(QA.read_model, "card", lambda c, bid: {
        "available": True, "card_id": "k", "generation_id": "g", "title": "t", "metadata": [], "summary": [],
        "themes": [], "key_events": [], "characters": []})
    cur = Cur()
    books = QA.library(cur)
    assert books[0]["recommendation"] == {"category": ["Çocuk", "Korku"], "audience": "CHILD", "age_from": 3,
                                          "age_to": 6}
    assert any("status='OK'" in s for s in cur.sql)


# ------------------------------------------------------------------ Ek. yalnız en son nesil
def test_rebuild_takes_only_the_latest_generation_of_a_book_version():
    rows = [{"id": "g1", "book_version_id": "v1", "created_at": 1, "title": "A", "profile": "archive"},
            {"id": "g2", "book_version_id": "v1", "created_at": 3, "title": "A", "profile": "full"},
            {"id": "g3", "book_version_id": "v2", "created_at": 2, "title": "B", "profile": "archive"}]
    assert [r["id"] for r in page_scope.latest_per_version(rows)] == ["g2", "g3"]

    class Cur:
        def execute(self, sql, params=None):
            return type("R", (), {"fetchall": lambda _s: rows})()
    assert [g["id"] for g in page_scope.read_generations(Cur())] == ["g2", "g3"]
    assert [g["id"] for g in page_scope.read_generations(Cur(), "archive")] == ["g3"]   # eski arşiv nesli yok
    assert [g["id"] for g in page_scope.read_generations(Cur(), all_generations=True)] == ["g1", "g2", "g3"]
