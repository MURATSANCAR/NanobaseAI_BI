"""Redaksiyon araçlarının saf parçaları (sentetik): tik sözcük (G²), cümle başı dizileri, kalıp öbek,
sözcük seçimi istemleri, Word yorumunun metne bağlanması. Model, sözlük ve veritabanı yok. Çalıştır:

    python3 -m pytest apps/editor/tests/test_word_tools.py
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

from editor.proofing import _export_docx as X  # noqa: E402
from editor.proofing import _word_variety as W  # noqa: E402


# ------------------------------------------------------------- tik sözcük
def test_log_likelihood_known_value_and_symmetry():
    # a=10/1.000, b=10/10.000: beklenen 1,82 ve 18,18 → G² ≈ 22,1
    assert round(W.log_likelihood(10, 1000, 10, 10000), 1) == 22.1
    assert W.log_likelihood(0, 1000, 0, 10000) == 0.0
    assert W.log_likelihood(5, 1000, 50, 10000) < 0.01          # aynı oran: fark yok


def test_overused_keeps_only_significantly_more_frequent_words():
    book = {"aslında": 60, "gitmek": 20, "yavaşça": 4}
    corpus = {"aslında": 90, "gitmek": 2000, "yavaşça": 40}
    rows = W.overused(book, 10000, corpus, 1000000)
    assert [r["lemma"] for r in rows] == ["aslında"]            # 60/10k vs 0,9/10k
    r = rows[0]
    assert r["per10k"] == 60.0 and r["corpus_per10k"] == 0.9 and r["ratio"] == 66.7 and r["g2"] >= W.KEYNESS_G2
    # derlemde hiç geçmeyen ama kitapta sık olan da sayılır; oran yok
    only = W.overused({"sanki": 30}, 10000, {}, 1000000)
    assert only and only[0]["ratio"] is None
    # az kullanım (derlemden seyrek) asla bulgu değil
    assert W.overused({"gitmek": 1}, 10000, {"gitmek": 5000}, 1000000) == []


# ------------------------------------------------------------- cümle başı
def test_start_runs_scale_with_how_common_the_start_is():
    # «ben» cümlelerin yarısını başlatıyor: iki «ben» art arda olağan (0,5)
    common = ["ben", "o"] * 10 + ["ben", "ben", "o"]
    assert W.start_runs(common, 0.05) == []
    seq = ["sonra", "sonra", "o", "ben", "ben", "ben", "ben", "ben", "ama"] + ["x%d" % i for i in range(40)]
    runs = W.start_runs(seq, 0.05)
    got = {(i, j) for i, j, _ in runs}
    assert (0, 2) in got                     # seyrek «sonra» iki kez art arda: p = 2/49 < 0,05
    assert (3, 8) in got                     # «ben» beş kez: (5/49)^4
    assert all(p < 0.05 for _, _, p in runs)


def test_start_runs_ignores_single_and_chance_level_pairs():
    seq = ["ben", "ben"] + ["ben", "o"] * 10                       # «ben» %50: ikili dizi olağan
    assert W.start_runs(seq, 0.05) == []                            # üç «ben» bile (0,55²≈0,3) olağan
    assert W.start_runs([], 0.05) == [] and W.start_runs(["a"], 0.05) == []


# ------------------------------------------------------------- kalıp öbek
def _seq(sentences):
    out, idx = [], 0
    for sid, words in enumerate(sentences):
        for w in words:
            out.append((idx, sid, w.lstrip("*"), not w.startswith("*")))
            idx += 1
        idx += 1                            # cümle arası noktalama boşluğu
    return out


def test_repeated_phrase_found_once_at_full_length():
    # «kalp küt küt atmak» iki cümlede; «*ve» işlev sözcüğü
    s = _seq([["kalp", "küt", "küt", "atmak", "*ve", "koşmak"], ["ben", "gelmek"],
              ["sonra", "kalp", "küt", "küt", "atmak"]])
    got = W.repeated_phrases(s)
    assert len(got) == 1
    n, pos = got[0]
    assert n == 4 and [s[i][2] for i in range(pos[0], pos[0] + n)] == ["kalp", "küt", "küt", "atmak"]
    assert len(pos) == 2


def test_function_heavy_or_broken_phrases_are_not_reported():
    s = _seq([["*bir", "*gün", "gelmek"], ["*bir", "*gün", "gelmek"]])        # tek içerik sözcüğü
    assert W.repeated_phrases(s) == []
    # öbek bir özel ad (atlanan belirteç) yüzünden kopuyorsa bitişik değildir
    t = [(0, 0, "göz", True), (1, 0, "parlamak", True), (3, 0, "hemen", True),
         (10, 1, "göz", True), (11, 1, "parlamak", True), (12, 1, "hemen", True)]
    assert W.repeated_phrases(t) == []


def test_shorter_phrase_reported_when_it_has_an_extra_occurrence():
    s = _seq([["göz", "dolmak", "hemen"], ["göz", "dolmak", "hemen", "susmak"], ["göz", "dolmak", "hemen", "susmak"]])
    got = {(n, len(pos)) for n, pos in W.repeated_phrases(s)}
    assert (4, 2) in got and (3, 3) in got


# ------------------------------------------------------------- Word yorumu
def test_place_prefers_the_quote_then_the_repeated_form():
    paras = ["Kasabada yaşlı bir çınar ağacı var.", "Çınar ağacının gölgesinde çay bahçesi."]
    f = {"quote": "Çınar ağacının gölgesinde", "details": {}}
    assert X.place(paras, f) == (1, 0, 25)
    g = {"quote": "uzun bir pasaj ki metinde bu hâliyle yok", "details": {"forms": ["ağacı", "ağacının"]}}
    assert X.place(paras, g) == (1, 6, 14)
    assert X.place(paras, {"quote": "hiç yok", "details": {}}) is None


def test_cuts_split_text_for_overlapping_comments():
    parts = X.cuts("abcdefgh", [(2, 5, 0), (4, 7, 1)])
    assert parts == [("ab", []), ("cd", [0]), ("e", [0, 1]), ("fg", [1]), ("h", [])]
    assert X.cuts("abc", []) == [("abc", [])]


def test_comment_text_mentions_suggestion_and_unplaced():
    f = {"label": "Yakın tekrar", "message": "«göz» iki kez.", "suggestion": "bakış"}
    t = X.comment_text(f, False)
    assert t.startswith("Yakın tekrar: «göz» iki kez.") and "Öneri: bakış" in t and "bulunamadı" in t


def test_xml_safe_drops_control_characters_from_pdf_text():
    assert X.xml_safe("Ağaç\x00\x0b dalı\x1f\tkırık\n") == "Ağaç dalı\tkırık\n"
    assert X._norm("a\x02  b") == "a b"
    assert "\x01" not in X.comment_text({"label": "L", "message": "m\x01", "suggestion": "s\x02"}, True)


def test_duplicate_ocr_supplement_is_detected_by_page_layer_text():
    spans = [
        {"page": 22, "idx": 2, "text": "Çay bahçesindeki herkes bir tiyatro sahnesi izler gibi onu izliyordu. Ceyda teyze birden"},
        {"page": 22, "idx": 3, "text": "kafasını kaldırdı."},
        {"page": 22, "idx": 8, "supplement": True,
         "text": "Çay bahçesindeki herkes bir tiyatro sahnesi izler gibi onu izliyordu. Ceyda teyze birden kafasını kaldırdı."},
        {"page": 22, "idx": 9, "supplement": True, "text": "Resmin içindeki tabelada yazan: Dilek Ağacı"},
        {"page": 23, "idx": 1, "supplement": True, "text": "Çay bahçesindeki herkes bir tiyatro sahnesi izler gibi"},
    ]
    assert W.duplicate_supplements(spans) == {(22, 8)}     # katmanda olan ek; yeni metin taşıyan ek kalır


def test_spread_tells_scattered_habit_from_clustered_plot_word():
    from editor.proofing import word_overuse as O
    scattered = O.spread_of(list(range(1, 64, 6)), 64)
    clustered = O.spread_of([37, 37, 38, 41, 41], 64)
    assert "64 sayfasının 11 sayfasında" in scattered and "10/10" in scattered
    assert "5 sayfasında" not in clustered and "3 sayfasında" in clustered
    assert O.spread_of([], 64) == ""


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
