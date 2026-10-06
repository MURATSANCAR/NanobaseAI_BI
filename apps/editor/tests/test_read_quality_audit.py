"""Okuma kalite denetimi (editor.read_audit, 2026-10-06): her okuma bitince kitabın kendi denetimi, sınıfına göre
düzeltme, kalan bulgu «Gözden geçir»e.

- Her kontrolün eşiği sınır testiyle: eşiğin hemen altı bulgu değildir, eşik bulgudur (yanlış pozitif sınırları:
  «Editörün Notu» bölüm adı, 92 karakterlik roman bölüm adı, bütün başlıkları küçük harfli tasarım, künyedeki
  editörle aynı adı taşıyan gerçek yan karakter, kavram kitabında karakter olmaması, önsözde üç kez «Yayınları»).
- Düzeltme haritası: sınıf → eylem; denenmiş eylem yeniden seçilmez; yeniden okuma tek başına ve kitap sürümünde bir
  kez; çıktıları yeniden kurmak etkisizse (aynı kod, aynı bilgi) seçilmez.
- Tur sınırı: en çok iki düzeltme turu; bilgi değiştiren eylemden sonra çıktılar bir kez kurulur; kuru koşu yazmaz.
- İş akışı: `quality-audit-v1` çıktılar ve öneriden sonra, iş bitmeden; düzelttiği adım failures'tan düşer; hatası
  okumayı düşürmez; yeniden okuma iş SUCCEEDED kapandıktan sonra sıraya girer.

Hiçbir kitap, ad ya da sayfa numarası koddan okunmaz; buradaki metinler elle yazılmıştır. Model ve veritabanı yok."""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import time
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

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

from editor import read_audit as RA  # noqa: E402


def codes(findings):
    return [x["code"] for x in findings]


def base(**kw) -> dict:
    """Sorunsuz bir anlatı kitabının olguları."""
    f = {"generation_id": "g1", "book_id": "b1", "title": "Kitap Adı", "job_id": "j1", "book_version_id": "bv1",
         "profile": "archive", "sealed": False, "tracked": True, "read_code": "c1", "code_now": "c1",
         "failures": {}, "form": "FICTION", "not_a_book": False, "audience_trusted": None, "snapshot": True,
         "pages_n": 120, "unresolved_mentions": 0, "recommendation": {"status": "OK", "audience": "CHILD"},
         "recommend_expected": True, "snap_code": "c1", "unread_pages": [], "text": {"words": 30000,
         "bad_per_10k": 0.0, "vowelless_pct": 0.3}, "metadata": {"AUTHOR": "A B", "PUBLISHER": "Y", "ISBN": "978"},
         "metadata_flags": [], "people_elsewhere": False, "metadata_refill_possible": False, "imprint_names": [],
         "summary": {"status": "SOURCE_SUPPORTED_DRAFT", "n": 8, "first_pages": [9], "first_front_kind": None},
         "chapters": [{"title": "Birinci Bölüm", "page_from": 7}, {"title": "İkinci Bölüm", "page_from": 30}],
         "characters_n": 6, "duplicate_names": [], "characters_out_of_scope": [], "imprint_people": [],
         "events_n": 12, "events_out_of_scope": [], "events_on_imprint": [], "scope_writes": [],
         "index": {"expected": True, "build_key": "k", "indexed": 40, "count": 40}}
    f.update(kw)
    return f


# ------------------------------------------------------------------ temiz kitap
def test_a_sound_book_has_no_findings_and_is_clean():
    out = RA.evaluate(base())
    assert out == []
    assert RA.status_of(out, out, [], False) == "CLEAN"


# ------------------------------------------------------------------ 1. adım düşmesi
def test_failed_steps_are_findings_with_their_fix():
    f = base(failures={"identity": ["Heartbeat"], "deep_scan": [{"failed": 14, "error": "x"}, {"failed": 3}],
                       "recommend": ["kapalı"], "fast_scan": [], "quality_audit": ["eski"]})
    out = {x["key"]: x for x in RA.evaluate(f)}
    assert set(out) == {"step:identity", "step:deep_scan", "step:recommend"}       # boş liste ve kendisi sayılmaz
    assert out["step:identity"]["severity"] == "critical" and out["step:identity"]["fix"] == "identity"
    assert out["step:deep_scan"]["detail"]["pages"] == [3, 14] and out["step:deep_scan"]["fix"] == "rescan"
    assert "2 sayfa" in out["step:deep_scan"]["title"] and out["step:recommend"]["fix"] == "recommend"


def test_missing_outputs_stop_the_other_checks():
    out = RA.evaluate(base(snapshot=False))
    assert codes(out) == ["outputs_missing"] and out[0]["fix"] == "outputs"


# ------------------------------------------------------------------ 2. karakter 0
def test_zero_characters_only_in_a_narrative_book():
    assert codes(RA.evaluate(base(characters_n=0))) == ["characters_zero"]
    assert codes(RA.evaluate(base(characters_n=0, form="NARRATIVE_NONFICTION"))) == ["characters_zero"]
    for form in ("UNKNOWN", "ACTIVITY", "EXPOSITORY", "POETRY", None):          # kavram/etkinlik kitabı kusur değil
        assert "characters_zero" not in codes(RA.evaluate(base(characters_n=0, form=form))), form
    nb = RA.evaluate(base(characters_n=0, form="NOT_A_BOOK", not_a_book=True, recommendation=None))
    assert "characters_zero" not in codes(nb)
    # çözülmemiş anma yoksa kimliği yeniden okumak bir şey bulmaz: eylem yok, insana kalır
    x = RA.evaluate(base(characters_n=0, unresolved_mentions=0))[0]
    assert x["fix"] == "" and RA.evaluate(base(characters_n=0, unresolved_mentions=4))[0]["fix"] == "identity"


# ------------------------------------------------------------------ 3. son okuma denetimleri
def test_final_read_checks_must_be_complete_when_expected():
    assert "proofing_incomplete" not in codes(RA.evaluate(base(proof={"expected": True, "recorded": 19, "total": 19})))
    out = RA.evaluate(base(proof={"expected": True, "recorded": 18, "total": 19, "missing": ["age_fit"]}))
    assert codes(out) == ["proofing_incomplete"] and "18/19" in out[0]["title"]


# ------------------------------------------------------------------ 4. metin
def test_unread_pages_threshold_needs_both_count_and_share():
    assert RA.UNREAD_MIN == 3 and RA.UNREAD_SHARE == 0.10
    assert not RA.evaluate(base(pages_n=20, unread_pages=[1, 2]))                     # 2 sayfa < 3
    assert codes(RA.evaluate(base(pages_n=20, unread_pages=[1, 2, 3]))) == ["pages_unread"]
    assert not RA.evaluate(base(pages_n=200, unread_pages=list(range(1, 20))))       # 19/200 < %10
    out = RA.evaluate(base(pages_n=200, unread_pages=list(range(1, 21))))
    assert codes(out) == ["pages_unread"] and out[0]["fix"] == "reread" and "20/200" in out[0]["title"]


def test_garbled_text_measure_and_threshold():
    s = RA.text_stats(["Sabah erkenden kalktı ve kapıyı açtı.", "HJCJ CJMJN PMVS kalem"])
    assert s["words"] == 10 and s["vowelless_pct"] == 30.0 and s["bad_per_10k"] == 0.0
    assert RA.text_stats(["ab�cd"])["bad_per_10k"] > 0
    ok = {"words": 5000, "bad_per_10k": 4.99, "vowelless_pct": 2.99}
    assert not RA.evaluate(base(text=ok))
    assert codes(RA.evaluate(base(text={**ok, "vowelless_pct": 3.0}))) == ["text_garbled"]
    assert codes(RA.evaluate(base(text={**ok, "bad_per_10k": 5.0}))) == ["text_garbled"]
    assert not RA.evaluate(base(text={"words": 1999, "bad_per_10k": 50.0, "vowelless_pct": 40.0}))   # kısa metin


def test_garbled_text_is_read_again_only_when_the_reading_used_older_code():
    bad = {"words": 5000, "bad_per_10k": 0.0, "vowelless_pct": 12.0}
    assert RA.evaluate(base(text=bad))[0]["fix"] == ""                     # aynı kod aynı metni okur
    assert RA.evaluate(base(text=bad, read_code="eski"))[0]["fix"] == "reread"


# ------------------------------------------------------------------ 5. künye
def test_imprint_author_missing_is_review_only_when_nobody_else_is_named():
    out = RA.evaluate(base(metadata={"PUBLISHER": "Y", "ISBN": "1"}))
    assert codes(out) == ["metadata_missing"] and out[0]["fix"] == ""
    assert RA.evaluate(base(metadata={"PUBLISHER": "Y", "ISBN": "1"}, metadata_refill_possible=True))[0]["fix"] == \
        "metadata"
    soft = RA.evaluate(base(metadata={"PUBLISHER": "Y", "ISBN": "1"}, people_elsewhere=True))
    assert codes(soft) == ["metadata_author_elsewhere"] and not RA.blocking(soft)
    info = RA.evaluate(base(metadata={"AUTHOR": "A"}, metadata_flags=["SHARED_TITLE"]))
    assert set(codes(info)) == {"metadata_publisher_missing", "metadata_isbn_missing", "metadata_flagged"}
    assert not RA.blocking(info)                                            # bilgi «Gözden geçir»e düşürmez


# ------------------------------------------------------------------ 6. özet
def test_summary_checks():
    assert codes(RA.evaluate(base(summary={"status": "EXTRACTIVE_FALLBACK", "n": 5}))) == ["summary_fallback"]
    assert codes(RA.evaluate(base(summary={"status": None, "n": 0}))) == ["summary_missing"]
    assert not RA.evaluate(base(summary={"status": None, "n": 0}, events_n=0))           # olay yoksa özet beklenmez
    out = RA.evaluate(base(summary={"status": "X", "n": 3, "first_pages": [4], "first_front_kind": "ithaf"}))
    assert codes(out) == ["summary_front_matter"] and "ithaf" in out[0]["title"] and out[0]["fix"] == "scope"


def test_front_kind_reads_the_page_rules():
    texts = {4: "Annem ve babama,", 40: "Sabah erkenden kalktı ve dükkânın kepengini yavaşça kaldırdı, içeri serin"
             " bir koku doldu; sokak henüz uyanmamıştı ve martılar çatıların üstünde dönüp duruyordu."}
    assert RA.front_kind([4], texts, set(), 200) == "ithaf"
    assert RA.front_kind([40], texts, set(), 200) is None                 # gövde sayfası
    assert RA.front_kind([40], texts, {40}, 200) == "kitap dışı sayfa"    # işaretli ama çıktı eski
    assert RA.front_kind([], texts, set(), 200) is None


# ------------------------------------------------------------------ 7. bölümler
def test_single_chapter_only_in_a_long_book():
    one = [{"title": "Kitap", "page_from": 1}]
    assert not RA.evaluate(base(chapters=one, pages_n=79))
    assert codes(RA.evaluate(base(chapters=one, pages_n=80))) == ["chapters_single"]
    assert not RA.evaluate(base(chapters=[{"title": "Masal", "page_from": 1}], pages_n=200))


def test_repeated_chapter_title_from_three():
    two = [{"title": "Eğitimi", "page_from": p} for p in (3, 9)]
    assert not RA.evaluate(base(chapters=two + [{"title": "Son", "page_from": 20}]))
    out = RA.evaluate(base(chapters=two + [{"title": "EĞİTİMİ", "page_from": 15}]))
    assert codes(out) == ["chapters_repeated"] and "×3" in out[0]["title"]


def test_chapter_title_rules_and_their_false_positive_limits():
    P = RA.chapter_title_problems
    for t in ("Editörün Notu", "Yayınevinden", "Önsöz", "1. Bölüm: Josep K.’nın Tutuklanması – Bayan Grubach ile"
              " Konuşma – Bayan Bürstnerin", "MÜELLİFE (İBN TEYMİYYE) DAİR", "Darwin ve Osmanlılar", "GİRİŞ"):
        assert P(t, ["İbn Teymiyye"]) == [], t
    assert P("ISBN 978-605-08", []) == ["imprint"]
    assert P("İbn Teymiyye", ["İbn Teymiyye"]) == ["imprint"]                 # imza satırı
    assert P("K İ T A P", []) == ["spaced"]
    assert P("ve Eser", []) == ["midsentence"]
    assert P("Annesi geldi ve", []) == ["midsentence"]
    assert P("sahneden indim ve sahne- nin arkasında", [], lower_ok=True) == ["midsentence"]
    assert P("x" * 121, []) == ["midsentence"] and P("X" * 120, []) == []
    # bütün başlıkları küçük harfle dizilmiş kitap (tasarım) küçük harf yüzünden işaretlenmez
    styled = [{"title": t, "page_from": i} for i, t in enumerate(("önsöz", "birinci bölüm", "ikinci bölüm"))]
    assert not RA.evaluate(base(chapters=styled))
    few = [{"title": "Birinci", "page_from": 1}, {"title": "İkinci", "page_from": 2}, {"title": "Üçüncü", "page_from": 3},
           {"title": "Dördüncü", "page_from": 4}, {"title": "ama sonra", "page_from": 5}]
    assert codes(RA.evaluate(base(chapters=few))) == ["chapters_midsentence"]


# ------------------------------------------------------------------ 8. karakterler
def test_imprint_person_needs_a_role_word_and_no_body_mention():
    texts = {4: "EDİTÖR Ayşe Kaya KAPAK GÖRSELİ Mehmet Er Yayınları ISBN", 88: "kadı kızları Ayşe ve Leyla geldi"}
    kunye = {4}
    chars = [{"name": "Mehmet Er", "pages": {4}}, {"name": "Ayşe Kaya", "pages": {4, 88}},
             {"name": "Leyla", "pages": {88}}]
    assert RA.imprint_people(chars, texts, kunye, []) == ["Mehmet Er"]       # gövdede anılan gerçek karakter değil
    assert RA.imprint_people([{"name": "Ali Can", "pages": {2}}], {2: "Ali Can"}, {2}, ["Ali Can"]) == ["Ali Can"]
    assert RA.imprint_people([{"name": "Ali", "pages": {2}}], {2: "Editör: Ali"}, {2}, []) == []   # 5 harften kısa


def test_kunye_page_needs_distinct_words_at_the_edges():
    pre = "Bu çalışma X Yayınları, Y Yayınları ve Z Yayınları arasında"
    imp = "ISBN 978 © Tüm hakları saklıdır. 1. Baskı Matbaa"
    texts = {2: imp, 50: imp, 199: pre, 3: pre}
    assert RA.kunye_hits(pre) == 1 and RA.kunye_hits(imp) >= 3
    assert RA.kunye_pages_of(texts, set(), 200) == {2}                        # gövde (s.50) ve önsöz sayılmaz
    assert RA.kunye_pages_of(texts, {120}, 200) == {2, 120}


def test_people_record_findings():
    out = RA.evaluate(base(duplicate_names=["Ador"], characters_out_of_scope=["Seval"], imprint_people=["Seval Ak"]))
    assert codes(out) == ["characters_duplicate", "characters_out_of_scope", "characters_imprint_person"]
    assert [x["fix"] for x in out] == ["fold", "scope", "scope"]


# ------------------------------------------------------------------ 9. olaylar, 10. öneri, 11. dizin
def test_events_recommendation_and_index():
    assert codes(RA.evaluate(base(events_out_of_scope=[2], events_on_imprint=[3]))) == \
        ["events_out_of_scope", "events_on_imprint_page"]
    assert codes(RA.evaluate(base(recommendation=None))) == ["recommendation_missing"]
    assert codes(RA.evaluate(base(recommendation={"status": "FAILED"}))) == ["recommendation_missing"]
    nb = base(form="NOT_A_BOOK", not_a_book=True, characters_n=0, metadata={})
    assert codes(RA.evaluate({**nb, "recommendation": None})) == []
    assert codes(RA.evaluate({**nb, "recommendation": {"status": "OK"}})) == ["recommendation_not_a_book"]
    assert not RA.evaluate(base(audience_trusted="ADULT", recommendation={"status": "OK", "audience": "YOUNG"}))
    assert codes(RA.evaluate(base(audience_trusted="ADULT", recommendation={"status": "OK", "audience": "CHILD"}))) == \
        ["recommendation_conflict"]
    assert codes(RA.evaluate(base(index={"expected": True, "build_key": "k", "count": 0}))) == ["index_empty"]
    assert not RA.evaluate(base(index={"expected": True, "build_key": "k", "error": "bağlantı"}))  # sayılamadı ≠ 0


# ------------------------------------------------------------------ 12. Zeki'ye sor
def test_cited_pages_reads_every_citation_form():
    assert RA.cited_pages("ana karakter Deha [s.4,6,34] ve [s.10–12] ile [s. 7]") == {4, 6, 34, 10, 11, 12, 7}
    assert RA.cited_pages("sayfa yok") == set()


def test_judge_answer():
    q = {"kind": "main", "expect_names": ["Salsal", "Tırtık Tırtık"]}
    assert RA.judge_answer(q, "Ana karakter Salsal'dır [s.6].")["ok"] is True
    assert RA.judge_answer(q, "Ana karakter Bee [s.6].")["why"] == "ana karakter adı cevapta yok"
    assert RA.judge_answer(q, "Ana karakter Salsal.")["why"] == "kaynak sayfa yok"
    assert RA.judge_answer(q, "Kitapta bulunamadı. Kayıtlarda yok.")["why"] == "bulunamadı dedi"
    assert RA.judge_answer(q, None)["ok"] is None                            # model yok: bulgu değil
    nar = {"kind": "main", "expect_names": ["Annem"], "narrator": True}
    assert RA.judge_answer(nar, "Birinci tekil şahıs anlatıcı olan çocuk [s.5].")["ok"] is True
    ev = {"kind": "event", "expect_pages": [20, 21]}
    assert RA.judge_answer(ev, "Olay [s.22] sayfasında.")["ok"] is True
    assert RA.judge_answer(ev, "Olay [s.23] sayfasında.")["ok"] is False
    concept = {"kind": "main", "need_pages": False}
    assert RA.judge_answer(concept, "Zıt kavramları anlatıyor.")["ok"] is True
    assert codes(RA.evaluate(base(ask={"questions": [{"kind": "event", "ok": False, "why": "x"}, {"kind": "main",
                                                                                             "ok": None}]}))) == ["ask_failed"]


def test_questions_come_from_the_books_own_records():
    card = {"characters": [{"canonical_name": "Ben", "mentions": 50}, {"canonical_name": "Ayşe", "mentions": 30},
                           {"canonical_name": "Adam", "mentions": 99, "minor": True}],
            "key_events": [{"page_from": 5, "summary": "kuş uçtu"}, {"page_from": 40, "page_to": 41,
                                                                     "summary": "deniz kenarında buluştular"},
                           {"page_from": 90, "summary": "eve döndü"}], "summary": []}
    main, ev = RA.ask_questions(card, story=True)
    assert main["expect_names"] == ["Ayşe"] and main["narrator"] is True       # yan kişi ve «Ben» ad sayılmaz
    assert ev["expect_pages"] == [40, 41] and "deniz kenarında" in ev["q"]
    only = RA.ask_questions({"characters": [], "key_events": [], "summary": []}, story=False)
    assert len(only) == 1 and only[0]["need_pages"] is False


# ------------------------------------------------------------------ düzeltme haritası
def test_fix_map_order_and_once_only():
    found = [RA.finding("index_empty"), RA.finding("characters_duplicate"), RA.finding("chapters_single"),
             RA.finding("metadata_missing", fix="metadata"), RA.finding("characters_zero", fix="identity"),
             RA.finding("metadata_isbn_missing")]
    assert RA.plan_fixes(found, set()) == ["identity", "fold", "metadata", "outputs", "reindex"]
    assert RA.plan_fixes(found, {"identity", "fold"}) == ["metadata", "outputs", "reindex"]
    assert RA.plan_fixes(found, set(), rebuild_effective=False) == ["identity", "fold", "metadata", "reindex"]
    assert RA.plan_fixes([RA.finding("ask_failed"), RA.finding("recommendation_conflict")], set()) == []


def test_reread_goes_alone_and_only_when_allowed():
    found = [RA.finding("pages_unread"), RA.finding("characters_duplicate")]
    assert RA.plan_fixes(found, set()) == ["reread"]
    assert RA.plan_fixes(found, set(), reread_allowed=False) == ["fold"]


def test_status():
    crit = [RA.finding("index_empty")]
    assert RA.status_of(crit, [], [{"action": "reindex", "ok": True}], False) == "FIXED"
    assert RA.status_of(crit, crit, [{"action": "reindex", "ok": False}], False) == "REVIEW"
    assert RA.status_of(crit, crit, [], True) == "REREAD"
    assert RA.status_of([RA.finding("metadata_isbn_missing")], [RA.finding("metadata_isbn_missing")], [], False) == \
        "CLEAN"


# ------------------------------------------------------------------ turlar
def _run_with(monkeypatch, states, *, fix=True, failures=None, tried=(), reread_done=False, rebuild_effective=True):
    """`states`: her denetimde dönen olgular sırayla; uygulanan eylemler ve yazılan kayıt döner."""
    seq = iter(states)
    applied, stored = [], []

    async def facts(gid, failures_, profile):
        return {**next(seq)}

    async def act(a, ctx):
        applied.append(a)
        if a == "reread":
            ctx["reread"] = True
        return {"action": a, "ok": True, "changed": a in RA.KNOWLEDGE_ACTIONS, "built": a == "identity"}

    async def ask(gid, story):
        return {"questions": []}
    monkeypatch.setattr(RA, "_facts", facts)
    monkeypatch.setattr(RA, "apply_action", act)
    monkeypatch.setattr(RA, "ask_smoke", ask)
    monkeypatch.setattr(RA, "tried_before", lambda gid: set(tried))
    monkeypatch.setattr(RA, "reread_done", lambda bv: reread_done)
    monkeypatch.setattr(RA, "_rebuild_effective", lambda f: rebuild_effective)
    monkeypatch.setattr(RA, "store", lambda rec: stored.append(rec) or 7)
    rec = asyncio.run(RA.run("g1", fix=fix, failures=failures))
    return rec, applied, stored


def test_two_fix_rounds_at_most_and_each_action_once(monkeypatch):
    dup = base(duplicate_names=["Ador"])
    rec, applied, stored = _run_with(monkeypatch, [dup, dup, dup, dup])
    assert applied == ["fold", "outputs"]             # fold bir kez; bilgi değişti → çıktılar bir kez kuruldu
    assert rec["status"] == "REVIEW" and rec["rounds"] == 2 and stored and stored[0]["origin"] == "COMMAND"
    assert [x["code"] for x in RA.blocking(rec["remaining"])] == ["characters_duplicate"]


def test_second_round_takes_new_actions_then_stops(monkeypatch):
    a = base(duplicate_names=["Ador"])
    b = base(index={"expected": True, "build_key": "k", "count": 0})
    rec, applied, _ = _run_with(monkeypatch, [a, b, base(), base()])
    assert applied == ["fold", "outputs", "reindex"] and rec["status"] == "FIXED" and rec["rounds"] == 3


def test_previous_records_actions_are_not_repeated(monkeypatch):
    dup = base(duplicate_names=["Ador"])
    rec, applied, _ = _run_with(monkeypatch, [dup, dup], tried={"fold"})
    assert applied == [] and rec["status"] == "REVIEW"


def test_identity_builds_its_own_outputs(monkeypatch):
    z = base(characters_n=0, unresolved_mentions=3)
    rec, applied, _ = _run_with(monkeypatch, [z, base(), base()])
    assert applied == ["identity"] and rec["status"] == "FIXED"


def test_reread_stops_the_rounds(monkeypatch):
    u = base(pages_n=20, unread_pages=[1, 2, 3], duplicate_names=["Ador"])
    rec, applied, _ = _run_with(monkeypatch, [u])
    assert applied == ["reread"] and rec["status"] == "REREAD"
    rec, applied, _ = _run_with(monkeypatch, [u, u, u, u], reread_done=True)
    assert "reread" not in applied and rec["status"] == "REVIEW"


def test_dry_run_writes_nothing_and_plans(monkeypatch):
    dup = base(duplicate_names=["Ador"])
    rec, applied, stored = _run_with(monkeypatch, [dup, dup], fix=False)
    assert applied == [] and stored == [] and rec["planned"] == ["fold"] and rec["status"] == "REVIEW"


def test_sealed_generation_is_only_audited(monkeypatch):
    dup = base(duplicate_names=["Ador"], sealed=True)
    rec, applied, _ = _run_with(monkeypatch, [dup, dup])
    assert applied == [] and rec["status"] == "REVIEW"


def test_workflow_failures_that_were_repaired_are_cleared(monkeypatch):
    f = base(failures={"recommend": ["kapalı"]}, recommendation=None)

    async def act(a, ctx):
        ctx["cleared"].add("recommend")
        return {"action": a, "ok": True, "changed": True}
    seq = iter([f, base(), base()])

    async def facts(gid, failures_, profile):
        return next(seq)

    async def ask(gid, story):
        return {"questions": []}
    monkeypatch.setattr(RA, "_facts", facts)
    monkeypatch.setattr(RA, "apply_action", act)
    monkeypatch.setattr(RA, "ask_smoke", ask)
    monkeypatch.setattr(RA, "tried_before", lambda gid: set())
    monkeypatch.setattr(RA, "reread_done", lambda bv: False)
    monkeypatch.setattr(RA, "_rebuild_effective", lambda f: False)
    monkeypatch.setattr(RA, "store", lambda rec: 9)
    out = asyncio.run(RA.run_step("j1", "g1", "archive", {"recommend": ["kapalı"]}))
    assert out["status"] == "FIXED" and out["cleared"] == ["recommend"] and out["reread"] is False
    assert out["by"] == "ZEKİ AI" and out["audit_id"] == 9


# ------------------------------------------------------------------ kayıt ve ekran
class _Conn:
    def __init__(self, rows):
        self.rows, self.sql = rows, []

    def execute(self, sql, args=None):
        self.sql.append((sql, args))
        rows = self.rows
        if "to_regclass" in sql:
            rows = [{"ok": True}]
        return types.SimpleNamespace(fetchall=lambda: rows, fetchone=lambda: rows[0] if rows else None)


def test_listing_and_detail_speak_the_screens_language(monkeypatch):
    RA._HAS_TABLE.clear()
    rem = [RA.finding("chapters_single", {"pages": 200}), RA.finding("metadata_isbn_missing")]
    first = [RA.finding("index_empty"), *rem]
    c = _Conn([{"book_id": "b1", "status": "REVIEW", "remaining": rem, "findings": first,
                "fixes": [{"action": "reindex", "ok": True}], "created_at": "2026-10-06T10:00:00", "origin": "WORKFLOW"}])
    assert RA.listing(c, ["b1"]) == {"b1": {"status": "REVIEW", "label": "Gözden geçir", "open": 1}}
    d = RA.detail(c, "b1")
    assert d["open"] == 1 and [x["code"] for x in d["issues"]] == ["chapters_single"]
    assert [x["code"] for x in d["fixed"]] == ["index_empty"] and [x["code"] for x in d["notes"]] == \
        ["metadata_isbn_missing"]
    assert d["fixes"] == [{"text": "Arama dizini yeniden kuruldu", "ok": True}]
    assert d["issues"][0]["pages"] is None                                  # sayı sayfa listesi değil
    for x in d["issues"] + d["fixed"] + d["notes"]:
        assert not any(w in x["title"] for w in ("Qdrant", "Temporal", "vLLM", "SQL", "model"))


def test_store_records_actor_and_version(monkeypatch):
    from editor import db
    seen = {}
    monkeypatch.setattr(RA, "has_table", lambda c=None: True)
    monkeypatch.setattr(db, "J", lambda x: x, raising=False)
    monkeypatch.setattr(db, "one", lambda sql, *a: seen.update(sql=sql, args=a) or {"id": 5})
    rec = {"generation_id": "g", "job_id": "j", "book_id": "b", "origin": "WORKFLOW", "status": "FIXED", "rounds": 2,
           "checks": {}, "findings": [], "remaining": [], "fixes": [], "code_version": "c"}
    assert RA.store(rec) == 5
    assert "read_quality_audit" in seen["sql"] and RA.ACTOR in seen["args"] and RA.VERSION in seen["args"]


def test_reread_is_queued_once_per_book_version(monkeypatch):
    from editor import db
    calls = []
    monkeypatch.setattr(db, "J", lambda x: x, raising=False)
    job = {"book_version_id": "bv", "profile": "archive", "requested_by": "arsiv:x",
           "progress": {"archive": {"category": "Kurgu"}, "generation_id": "eski", "attempt": 3}}

    def one(sql, *a):
        calls.append((sql, a))
        if sql.startswith("SELECT book_version_id"):
            return job
        if "quality_reread_of' LIMIT" in sql or "? 'quality_reread_of'" in sql:
            return None
        return {"id": "new"}
    monkeypatch.setattr(db, "one", one)
    out = RA.queue_reread("j1")
    assert out == {"queued": True, "job_id": "new"}
    ins = [a for s, a in calls if s.startswith("INSERT")][0]
    assert ins[2] == "arsiv:x" and ins[3] == {"archive": {"category": "Kurgu"}, "attempt": 1, "quality_reread_of": "j1"}
    monkeypatch.setattr(RA, "reread_done", lambda bv: True)
    assert RA.queue_reread("j1")["queued"] is False


def test_pharmacy_quality_filter_and_facets():
    from editor import archive as A
    books = [{"id": i, "title": t, "category": None, "read": None, "redaction": None, "proofed": False,
              "quality": q} for i, t, q in (("1", "A", {"status": "CLEAN"}), ("2", "B", {"status": "REVIEW"}),
                                            ("3", "C", {"status": "REREAD"}), ("4", "D", None))]
    out = A.select(books, quality="gozden")
    assert [b["id"] for b in out["items"]] == ["2", "3"]
    assert out["facets"]["quality"] == {"temiz": 1, "duzeltildi": 0, "gozden": 2}
    assert A.select(books)["total"] == 4


# ------------------------------------------------------------------ etkinlik ve iş akışı
def test_audit_activity_keeps_the_loop_turning(monkeypatch):
    pytest.importorskip("temporalio")
    from editor.workflow import activities as A
    from test_activity_loop import BLOCK, MAX_GAP, Ticker
    assert A.quality_audit in A.ALL and A.quality_reread in A.ALL

    async def slow(job, gid, profile, failures):
        time.sleep(BLOCK)                         # kendi döngüsünde bloklar; işçinin döngüsü döner
        return {"status": "CLEAN"}
    monkeypatch.setattr(RA, "run_step", slow)

    async def main():
        with Ticker() as t:
            assert await A.quality_audit("j", "g", "archive", {}) == {"status": "CLEAN"}
        return t.max_gap
    assert asyncio.run(main()) < MAX_GAP


def _order(calls, *names):
    seen = [n for n, _ in calls]
    return [seen.index(n) for n in names]


def test_archive_reading_audits_after_outputs_and_suggestion():
    from test_step_retry import _finish, _run
    audit = {"status": "FIXED", "findings": 2, "remaining": 0, "fixes": [], "cleared": ["recommend"], "reread": False}
    out, calls, hist = _run("archive", {"quality_audit": lambda n, *a: audit,
                                        "archive_recommend": lambda n, gid: (_ for _ in ()).throw(
                                            __import__("test_step_retry")._app_error("kapalı", "ValueError"))})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "quality-audit-v1" in hist
    outputs, rec, qa, fin = _order(calls, "archive_outputs", "archive_recommend", "quality_audit", "finish_job")
    assert outputs < rec < qa < fin
    job, gid, profile, failures = [v for n, v in calls if n == "quality_audit"][0]
    assert (gid, profile) == ("g1", "archive") and "recommend" in failures
    assert "recommend" not in result["failures"]                       # denetim düzeltti
    assert result["quality_audit"]["status"] == "FIXED" and "cleared" not in result["quality_audit"]
    assert "quality_reread" not in [n for n, _ in calls]


def test_full_reading_audits_too_and_rereads_after_the_job_ends():
    from test_step_retry import _finish, _run
    out, calls, hist = _run("full", {"quality_audit": lambda n, *a: {"status": "REREAD", "reread": True}})
    status, result = _finish(calls)
    assert status == "SUCCEEDED"
    outputs, qa, fin, rr = _order(calls, "rebuild_outputs", "quality_audit", "finish_job", "quality_reread")
    assert outputs < qa < fin < rr
    assert [v for n, v in calls if n == "quality_audit"][0][2] == "full"


def test_audit_failure_never_fails_the_reading():
    from test_step_retry import _app_error, _finish, _run

    def boom(n, *a):
        raise _app_error("denetim kırıldı", "ValueError")
    out, calls, hist = _run("archive", {"quality_audit": boom})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "denetim kırıldı" in result["failures"]["quality_audit"][0]
    assert "quality_audit" not in result


def test_redaction_is_not_audited():
    from test_step_retry import _finish, _run
    out, calls, hist = _run("redaction", {})
    assert "quality_audit" not in [n for n, _ in calls]


# ------------------------------------------------------------------ K20–K23 ve olgusuz özet
def test_k20_production_note_and_foreign_line_in_chapter_titles():
    for t in ("Pencere açıldığında görünen kısım BIÇAK", "BIÇAK", "EBAT: 22 X 30", "KAPAK İÇİ içine baskı",
              "Wo versteckt sich der gelbe Schmetterling?"):
        assert RA.production_note(t), t
    for t in ("Bıçaklı Adam", "Kapak", "Ebatlar ve Ölçüler", "Birinci Bölüm", "Der Engel", "Pencere"):
        assert not RA.production_note(t), t
    out = RA.evaluate(base(chapters=[{"title": "Giriş", "page_from": 3}, {"title": "EBAT: 22 X 30", "page_from": 9}]))
    assert codes(out) == ["chapters_production_note"]


def test_k21_body_sentences_as_chapters_only_in_a_short_book():
    sent = ["Çengel zıplaya zıplaya geldi", "Atlar alçalıp yükseldi, bulutlar kaçtı", "Kedi bahçede uyuyordu sessizce",
            "Sonra hep birlikte eve döndüler"]
    chs = [{"title": t, "page_from": i * 6} for i, t in enumerate(sent)]
    assert RA.body_sentence_chapters(chs, 32)
    assert not RA.body_sentence_chapters(chs, 49)                         # uzun kitap
    assert not RA.body_sentence_chapters(chs[:3], 32)                     # az bölüm
    named = [{"title": t, "page_from": i} for i, t in enumerate(("Orman", "Deniz Kenarı", "Kar Yağınca", "Eve Dönüş"))]
    assert not RA.body_sentence_chapters(named, 32)
    assert codes(RA.evaluate(base(chapters=chs, pages_n=32))) == ["chapters_body_sentence"]


def test_k22_summary_opens_with_an_author_biography():
    bio = "Yazar 1975 yılında İstanbul'da doğmuş, edebiyat bölümünden mezun olmuş."
    assert RA.bio_sentence(bio) and not RA.bio_sentence("Ali sabah okula gitti ve arkadaşlarıyla oynadı.")
    s = {"status": "SOURCE_SUPPORTED_DRAFT", "n": 4, "first_pages": [2], "first_text": bio}
    assert codes(RA.evaluate(base(summary=s))) == ["summary_author_bio"]
    # sayfa kuralı zaten kitap dışı dediyse tek bulgu (summary_front_matter)
    assert codes(RA.evaluate(base(summary={**s, "first_front_kind": "yazar tanıtımı"}))) == ["summary_front_matter"]


def test_k23_duplicate_book_record():
    c = _Conn([{"id": "b2", "title": "Gizemli Ada", "page_count": 129}])
    assert RA.duplicate_books(c, "b1", "Gizemli Ada", 128) == [{"book_id": "b2", "pages": 129}]
    assert RA.duplicate_books(c, "b1", "Kitap", 128) == []                # ad taşımayan ad
    assert RA.duplicate_books(c, "b1", "Gizemli Ada", None) == []
    assert codes(RA.evaluate(base(duplicate_books=[{"book_id": "b2", "pages": 129}]))) == ["duplicate_book_record"]


def test_no_facts_without_a_not_a_book_mark_goes_to_review():
    s = {"status": "NO_VERIFIED_FACTS", "n": 0}
    assert codes(RA.evaluate(base(summary=s, events_n=0))) == ["summary_no_facts"]
    assert not RA.evaluate(base(summary=s, events_n=0, form="NOT_A_BOOK", not_a_book=True, characters_n=0,
                                metadata={}, recommendation=None))
