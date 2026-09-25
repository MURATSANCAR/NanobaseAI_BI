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
    def __init__(self, lemma, pos, stem, sec=None, groups=(0,)):
        self.dict_item, self.stem, self.group_boundaries = _Item(lemma, pos, sec), stem, list(groups)


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
    cs = W.candidates([_A("göz", "Noun", "göz"), _A("Göz", "Noun", "göz", "Prop"), _A("göz", "Noun", "göz"),
                       _A("göz", "Noun", "göz", groups=(0, 2))])
    # tekrar eden çözümleme bir kez; türetme sayısı çekim grubu sınırlarından
    assert cs == [("göz", "Noun", 0, 3, False), ("göz", "Noun", 0, 3, True), ("göz", "Noun", 1, 3, False)]


# ------------------------------------------------------------- kök seçimi
# Adaylar sunucudaki gerçek Zemberek çözümlemelerinden (2026-09-25) alındı: (kök, tür, türetme, gövde, özel ad).
def test_choose_lemmas_prefers_fewest_derivations():
    form_cands = {
        "gözlük": [("gözlük", "Noun", 0, 6, False), ("göz", "Noun", 1, 3, False)],   # türetme kendi maddesi
        "yüzdü": [("yüzmek", "Verb", 0, 3, False), ("yüz", "Num", 1, 3, False), ("yüz", "Noun", 1, 3, False)],
        "gözüme": [("göz", "Noun", 0, 3, False)],
    }
    out = W.choose_lemmas(form_cands, {"gözlük": 1, "yüzdü": 1, "gözüme": 1})
    assert out["gözlük"] == ("gözlük", "Noun", False)
    assert out["yüzdü"] == ("yüzmek", "Verb", False)
    assert out["gözüme"] == ("göz", "Noun", False)


def test_rare_dictionary_item_loses_to_the_books_usage():
    # "göze": göz+yönelme, "göze" (pınar), "gözemek"; kitapta "gözüme", "gözü" varsa göz
    form_cands = {"göze": [("gözemek", "Verb", 0, 4, False), ("göz", "Noun", 0, 3, False), ("göze", "Noun", 0, 4, False)],
                  "gözüme": [("göz", "Noun", 0, 3, False)], "gözü": [("göz", "Noun", 0, 3, False)]}
    assert W.choose_lemmas(form_cands, {"göze": 1, "gözüme": 1, "gözü": 1})["göze"] == ("göz", "Noun", True)
    # kitapta başka ipucu yoksa kısa gövde (yalın kök)
    assert W.choose_lemmas({"göze": form_cands["göze"]}, {"göze": 1})["göze"][0] == "göz"
    koşa = [("koşa", "Adv", 0, 4, False), ("koşa", "Adj", 0, 4, False), ("koşmak", "Verb", 0, 3, False)]
    assert W.choose_lemmas({"koşa": koşa}, {"koşa": 1})["koşa"][0] == "koşmak"


def test_proper_reading_drops_when_a_common_one_exists():
    out = W.choose_lemmas({"mert": [("mert", "Adj", 0, 4, False), ("mert", "Noun", 0, 4, True)]}, {"mert": 1})
    assert out["mert"] == ("mert", "Adj", False)


def test_choose_lemmas_ambiguity_follows_the_books_own_usage():
    # "yüz" hem ad hem "yüzmek"in kökü; kitapta tek çözümlü "yüzdü", "yüzüyor" çoksa fiil seçilir
    form_cands = {"yüz": [("yüz", "Noun", 0, 3, False), ("yüzmek", "Verb", 0, 3, False)],
                  "yüzdü": [("yüzmek", "Verb", 0, 3, False)], "yüzüyor": [("yüzmek", "Verb", 0, 3, False)],
                  "yüzünü": [("yüz", "Noun", 0, 3, False)]}
    out = W.choose_lemmas(form_cands, {"yüz": 1, "yüzdü": 4, "yüzüyor": 2, "yüzünü": 1})
    assert out["yüz"] == ("yüzmek", "Verb", True)
    out = W.choose_lemmas(form_cands, {"yüz": 1, "yüzdü": 1, "yüzüyor": 1, "yüzünü": 5})
    assert out["yüz"] == ("yüz", "Noun", True)


def test_pos_function_reading_wins_for_function_words():
    bir = [("bir", "Det", 0, 3, False), ("bir", "Adj", 0, 3, False), ("bir", "Num", 0, 3, False), ("bir", "Adv", 0, 3, False)]
    güzel = [("güzel", "Adv", 0, 5, False), ("güzel", "Adj", 0, 5, False), ("güzel", "Noun", 0, 5, False)]
    yüz = [("yüz", "Num", 0, 3, False), ("yüz", "Noun", 0, 3, False)]
    out = W.choose_lemmas({"bir": bir, "güzel": güzel, "yüzünü": yüz}, {"bir": 1, "güzel": 1, "yüzünü": 1})
    assert out["bir"] == ("bir", "Det", False)                   # işlev sözcüğü: tekrar adayı olmaz
    assert out["güzel"] == ("güzel", "Adj", False)               # aynı kökün birden çok türü belirsizlik değil
    assert out["yüzünü"] == ("yüz", "Noun", False)               # sayı tek başına işlev saymaz


def test_closed_class_bare_form_wins():
    # sunucudaki gerçek çözümlemeler: "de" demek'in emri, "ile" il+e, "için" iç+in, "o" sıfat da olabilir
    cands = {"de": [("de", "Conj", 0, 2, False), ("demek", "Verb", 0, 2, False), ("de", "Noun", 0, 2, False)],
             "ile": [("ile", "Postp", 0, 3, False), ("ile", "Conj", 0, 3, False), ("ilmek", "Verb", 0, 2, False),
                     ("il", "Noun", 0, 2, False)],
             "için": [("için", "Postp", 0, 4, False), ("içmek", "Verb", 0, 2, False), ("iç", "Noun", 0, 2, False)],
             "o": [("o", "Det", 0, 1, False), ("o", "Interj", 0, 1, False), ("o", "Adj", 0, 1, False), ("o", "Pron", 0, 1, False)],
             "dedi": [("demek", "Verb", 0, 2, False)], "ilde": [("il", "Noun", 0, 2, False)]}
    out = W.choose_lemmas(cands, {k: 1 for k in cands})
    assert out["de"] == ("de", "Conj", False)
    assert out["ile"][0] == "ile" and out["ile"][1] in W.FUNCTION_POS
    assert out["için"] == ("için", "Postp", False)
    assert out["o"][0] == "o" and out["o"][1] in W.FUNCTION_POS
    assert out["dedi"] == ("demek", "Verb", False) and out["ilde"] == ("il", "Noun", False)   # ekli biçim etkilenmez


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
    assert "kitabın tamamında 14 kez" in W.flaw_prompt("göz", None, "x", W.FLAW, W.FINE, 14)


# ------------------------------------------------------------- sayfadaki yer ve öneri
def test_norm_word_strips_punctuation_and_lowercases_turkish():
    assert W.norm_word("«Ağacı,") == "ağacı"
    assert W.norm_word("–IŞIK!") == "ışık"
    assert W.norm_word("Mert’in") == "mert'in"


def test_pick_box_matches_by_order_only_when_counts_agree():
    words = [("ağaç", [1, 1, 2, 2]), ("ve", [3, 3, 4, 4]), ("ağaç", [5, 5, 6, 6])]
    assert W.pick_box(words, "Ağaç", 1, 2) == [5, 5, 6, 6]
    assert W.pick_box(words, "ağaç", 0, 3) is None                  # metinde 3, sayfada 2: sıra güvenilmez
    assert W.pick_box([("dut", [7, 7, 8, 8])], "Dut", 0, 1) == [7, 7, 8, 8]
    assert W.pick_box([], "dut", 0, 1) is None                       # metin katmanı yok (OCR sayfası)


def test_to1000_uses_the_page_rect():
    assert W.to1000((50, 100, 150, 200), (0, 0, 500, 1000)) == [100, 100, 300, 200]
    assert W.to1000((60, 110, 160, 210), (10, 10, 510, 1010)) == [100, 100, 300, 200]


def test_valid_suggestion_needs_every_word_in_the_dictionary():
    known = {"anlasaydı", "fark", "etseydi", "gövdesine"}
    ok = lambda w: w in known
    assert W.valid_suggestion("anlasaydı", ok)
    assert W.valid_suggestion("fark etseydi", ok)
    assert not W.valid_suggestion("anlasayd", ok)
    assert not W.valid_suggestion("   ", ok)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
