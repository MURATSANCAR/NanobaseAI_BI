"""Kelime çeşitliliği denetiminin saf parçaları (sentetik): ad/sözcük ayrımı, kök seçimi, ikileme,
yakın tekrar kümesi, MTLD, anlam çağrısı planı, anlam cevabının doğrulanması, harita, pasaj.
Model, sözlük ve veritabanı yok. Çalıştır:

    python3 -m pytest apps/editor/tests/test_word_variety.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool"):
    sys.modules.setdefault(_mod, _Stub(_mod))

from editor.proofing import _word_variety as W  # noqa: E402


# ------------------------------------------------------------- yardımcılar
class _V:
    def __init__(self, v):
        self.value = v


class _Item:
    def __init__(self, lemma, pos, sec=None):
        self.lemma, self.primary_pos, self.secondary_pos = lemma, _V(pos), (_V(sec) if sec else None)


class _A:
    def __init__(self, lemma, pos, stem, sec=None):
        self.dict_item, self.stem = _Item(lemma, pos, sec), stem


def occ(idx, sent, lemma="göz", page=1, span=1, start=0, end=3, form=None, sense=None, pos="Noun"):
    o = W.Occ(idx, page, span, start, end, sent, form or lemma, form or lemma, lemma, pos)
    o.sense = sense
    return o


# ------------------------------------------------------------- belirteç sınıfı
def test_word_kind_names_and_words():
    assert W.word_kind("Mert", "'", False) == "name"          # kesmeli büyük harf
    assert W.word_kind("Mert", "", False) == "name"           # cümle ortasında büyük harf
    assert W.word_kind("Göz", "", True) == "word"             # cümle başı: sözlüğe bırakılır
    assert W.word_kind("GÖZÜNÜ", "", False) == "word"         # tamamı büyük: başlık/vurgu
    assert W.word_kind("O", "", True) == "word"
    assert W.word_kind("gözüme", "", False) == "word"


def test_candidates_read_zemberek_items():
    cs = W.candidates([_A("göz", "Noun", "göz"), _A("Göz", "Noun", "göz", "Prop"), _A("göz", "Noun", "göz")])
    assert cs == [("göz", "Noun", 3, False), ("göz", "Noun", 3, True)]      # tekrar eden çözümleme bir kez


# ------------------------------------------------------------- kök seçimi
def test_choose_lemmas_drops_proper_reading_and_prefers_longest_stem():
    form_cands = {
        "gül": [("gül", "Noun", 3, True), ("gül", "Noun", 3, False), ("gülmek", "Verb", 3, False)],
        "gözlük": [("gözlük", "Noun", 6, False), ("göz", "Noun", 3, False)],     # türetme kendi maddesi
        "gözüme": [("göz", "Noun", 3, False)],
    }
    out = W.choose_lemmas(form_cands, {"gül": 1, "gözlük": 1, "gözüme": 1})
    assert out["gözlük"] == ("gözlük", "Noun", False)
    assert out["gözüme"] == ("göz", "Noun", False)
    assert out["gül"][2] is True                                   # ad/fiil belirsiz, işaretli


def test_choose_lemmas_ambiguity_follows_the_books_own_usage():
    # "yüz" hem ad hem "yüzmek"in kökü; kitapta tek çözümlü "yüzdü", "yüzüyor" çoksa fiil seçilir
    form_cands = {"yüz": [("yüz", "Noun", 3, False), ("yüzmek", "Verb", 3, False)],
                  "yüzdü": [("yüzmek", "Verb", 3, False)], "yüzüyor": [("yüzmek", "Verb", 3, False)],
                  "yüzünü": [("yüz", "Noun", 3, False)]}
    out = W.choose_lemmas(form_cands, {"yüz": 1, "yüzdü": 4, "yüzüyor": 2, "yüzünü": 1})
    assert out["yüz"] == ("yüzmek", "Verb", True)
    out = W.choose_lemmas(form_cands, {"yüz": 1, "yüzdü": 1, "yüzüyor": 1, "yüzünü": 5})
    assert out["yüz"] == ("yüz", "Noun", True)


def test_same_lemma_several_pos_is_not_ambiguous():
    out = W.choose_lemmas({"güzel": [("güzel", "Adj", 5, False), ("güzel", "Adv", 5, False)]}, {"güzel": 1})
    assert out["güzel"] == ("güzel", "Adj", False)


def test_unanalysed_form_is_left_out():
    assert "zıbıdık" not in W.choose_lemmas({"zıbıdık": []}, {"zıbıdık": 2})


# ------------------------------------------------------------- konum
def test_sentence_ids_do_not_reset_at_page_break():
    assert W.sentence_ids([True, False, False, True, False, True]) == [0, 0, 0, 1, 1, 2]
    assert W.sentence_ids([False, False, True]) == [0, 0, 1]


def test_reduplication_is_not_a_repeat():
    kept, dropped = W.drop_reduplication([occ(4, 0, "yavaş"), occ(5, 0, "yavaş"), occ(12, 1, "yavaş")])
    assert [o.idx for o in kept] == [4, 12] and dropped == 1


def test_clusters_by_sentence_window():
    os_ = [occ(1, 0), occ(5, 0), occ(20, 2), occ(30, 3), occ(90, 9)]
    assert [[o.idx for o in c] for c in W.clusters(os_, 0)] == [[1, 5]]
    assert [[o.idx for o in c] for c in W.clusters(os_, 1)] == [[1, 5], [20, 30]]
    assert W.clusters([occ(1, 0)], 1) == []


# ------------------------------------------------------------- çeşitlilik
def test_mtld_rewards_variety_and_ignores_length():
    assert W.mtld([]) is None
    flat = ["a", "b"] * 50
    rich = [f"w{i}" for i in range(100)]
    assert W.mtld(rich) == 100.0
    assert W.mtld(flat) < 5
    assert abs(W.mtld(["a", "b", "c", "d"] * 25) - W.mtld(["a", "b", "c", "d"] * 100)) < 1


# ------------------------------------------------------------- anlam çağrıları
def test_rounds_cover_every_occurrence_once_and_respect_call_size():
    units = {"göz": [occ(i, i) for i in range(10)], "el": [occ(100 + i, i, "el") for i in range(3)],
             "dolap": [occ(200, 1, "dolap"), occ(201, 2, "dolap")]}
    plan = W.rounds(units, 4)
    assert len(plan) == 3                                           # göz: 4 + 4 + 2
    seen = [o.idx for rnd in plan for call in rnd for _, part in call for o in part]
    assert sorted(seen) == sorted(o.idx for v in units.values() for o in v)
    assert all(sum(len(p) for _, p in call) <= 4 for rnd in plan for call in rnd)
    # bir kökün parçaları farklı turlarda (sonraki parça önceki etiketlerle sorulur)
    for rnd in plan:
        for call in rnd:
            assert len({lem for lem, _ in call}) == len(call)


def test_the_three_eyes_are_three_senses():
    """«göze girdi», «gözüme toz kaçtı», «dolabın gözü»: üç ayrı anlam; yan yana olsalar da tekrar yok."""
    g = [occ(10, 0, form="göze"), occ(20, 1, form="gözüme"), occ(30, 2, form="gözü")]
    ctx = {10: "Öğretmenin [[göze]] girdi.", 20: "Rüzgârda [[gözüme]] toz kaçtı.", 30: "Dolabın [[gözü]] açık kaldı."}
    body, ids = W.sense_prompt([("göz", g)], ctx, {})
    assert "1. s.1: Öğretmenin [[göze]] girdi." in body and len(ids) == 3
    senses: dict = {}
    missing = W.merge_senses({"sozcukler": [{"sozcuk": "göz", "anlamlar": [
        {"etiket": "beğenilmek", "deyim": "göze girmek", "numaralar": [1]},
        {"etiket": "organ, görme", "deyim": "", "numaralar": [2]},
        {"etiket": "bölme, çekmece", "deyim": "", "numaralar": [3]}]}]}, ids, senses)
    assert missing == []
    assert [s["label"] for s in senses["göz"]] == ["beğenilmek", "organ, görme", "bölme, çekmece"]
    assert [o.sense for o in g] == [0, 1, 2]
    # aynı anlamlı küme yok: hiçbir anlamda ≥2 geçiş
    by = {}
    for o in g:
        by.setdefault(o.sense, []).append(o)
    assert all(W.clusters(v, 1) == [] for v in by.values())
    # ama kök düzeyinde yakınlar: «farklı anlamda yakın geçiş» olarak sayılır
    assert len(W.clusters(g, 1)) == 1


def test_merge_senses_validates_the_answer():
    a = [occ(1, 0), occ(2, 1)]
    b = [occ(3, 0, "el"), occ(4, 5, "el")]
    _, ids = W.sense_prompt([("göz", a), ("el", b)], {1: "x", 2: "x", 3: "x", 4: "x"}, {})
    senses: dict = {}
    missing = W.merge_senses({"sozcukler": [{"sozcuk": "karışık", "anlamlar": [
        {"etiket": "organ", "deyim": "", "numaralar": [1, 3, 99, 1]},        # 99 yok, 1 iki kez, 3 başka kök
        {"etiket": "ikinci", "deyim": "", "numaralar": [1]}]}]}, ids, senses)
    assert missing == [2, 4]                                        # atlananlar yeniden sorulur
    assert a[0].sense == 0 and b[0].sense == 0 and a[1].sense is None
    assert senses == {"göz": [{"label": "organ", "idiom": ""}], "el": [{"label": "organ", "idiom": ""}]}


def test_later_round_reuses_labels_and_idioms():
    senses = {"göz": [{"label": "organ, görme", "idiom": ""}, {"label": "beğenilmek", "idiom": "göze girmek"}]}
    later = [occ(50, 7), occ(60, 8)]
    body, ids = W.sense_prompt([("göz", later)], {50: "a", 60: "b"}, senses)
    assert "«organ, görme»" in body and "deyim: göze girmek" in body
    W.merge_senses({"sozcukler": [{"sozcuk": "göz", "anlamlar": [
        {"etiket": "Organ, görme.", "deyim": "", "numaralar": [1]},
        {"etiket": "sevilmek", "deyim": "Göze girmek", "numaralar": [2]}]}]}, ids, senses)
    assert [o.sense for o in later] == [0, 1] and len(senses["göz"]) == 2


def test_schema_bounds_follow_the_call():
    s = W.sense_schema(2, 7)
    word = s["properties"]["sozcukler"]["items"]
    nums = word["properties"]["anlamlar"]["items"]["properties"]["numaralar"]
    assert nums["maxItems"] == 7 and nums["items"]["maximum"] == 7


# ------------------------------------------------------------- harita ve pasaj
def test_build_map_keeps_every_lemma_and_shows_unassigned():
    g = [occ(1, 0, form="göze", sense=0, page=3), occ(2, 1, form="gözüme", sense=1, page=3),
         occ(3, 5, form="gözüme", sense=1, page=9), occ(4, 6, form="göz", sense=None, page=9)]
    one = [occ(9, 9, "dolap", page=4)]
    senses = {"göz": [{"label": "beğenilmek", "idiom": "göze girmek"}, {"label": "organ", "idiom": ""}]}
    m = W.build_map(g + one, senses, {1: "c1", 2: "c2", 4: "c4"})
    assert [r["lemma"] for r in m] == ["göz", "dolap"]
    goz = m[0]
    assert goz["count"] == 4 and goz["forms"] == {"gözüme": 2, "göze": 1, "göz": 1} and goz["pages"] == [3, 9]
    assert [(s["label"], s["count"]) for s in goz["senses"]] == [("organ", 2), ("beğenilmek", 1),
                                                                  ("belirsiz (model atamadı)", 1)]
    assert goz["senses"][1]["idiom"] == "göze girmek" and "senses" not in m[1]


def test_passage_marks_every_occurrence_across_spans():
    keys = [(1, 1), (1, 2), (2, 1)]
    text = {(1, 1): "Gözü  doldu.", (1, 2): "Sonra   yürüdü.", (2, 1): "Gözü yine doldu."}
    plain, marked = W.passage(keys, text, [occ(1, 0, page=1, span=1, start=0, end=4),
                                           occ(9, 2, page=2, span=1, start=0, end=4)])
    assert plain == "Gözü doldu. Sonra yürüdü. Gözü yine doldu."
    assert marked == "[[Gözü]] doldu. Sonra yürüdü. [[Gözü]] yine doldu."


def test_marked_context_and_flaw_prompt():
    t = "Kapıyı açtı ve gözüme toz kaçtı, sonra durdu."
    s = t.index("gözüme")
    assert W.marked_context(t, s, s + 6, 8) == "…açtı ve [[gözüme]] toz kaç…"
    p = W.flaw_prompt("göz", {"label": "organ", "idiom": ""}, "x [[göz]] y [[göz]]", W.FLAW, W.FINE)
    assert "«göz» (anlamı: organ)" in p and p.endswith("Yalnız A ya da B yaz.")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
