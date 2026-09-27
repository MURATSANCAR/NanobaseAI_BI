"""Son okuma bulgu metinleri (proofing/_messages): sade dil, tek yer, eski kayıtlar da yeni dille.

Bulgular gerçek kayıtların biçimindedir (alanlar ed.proof_finding'deki gibi); kitaba özel hiçbir şey yok."""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from editor.proofing import _messages as M  # noqa: E402
from editor.proofing._labels import labels  # noqa: E402

# Ana metinde ve öneride görünmemesi gereken teknik izler: standart adları, renk kodu, oran yazımı, kısaltmalar.
TECH = re.compile(r"WCAG|#[0-9a-fA-F]{6}|\d:1\b|\bpt\b|CRM|CCIP|TDK|U\+[0-9A-F]{4}|HUMAN_|_[A-Z]{2,}|[A-Z]{3,}_|"
                  r"Ateşman|Bezirci|kontrast|defter|replik|aday|yargıla")


def _f(check, details, page=12, severity="WARN", quote="örnek", suggestion=None, message=""):
    return {"check": check, "page": page, "severity": severity, "quote": quote, "suggestion": suggestion,
            "message": message, "details": details}


CASES = [
    _f("layout", {"rule": "contrast_low", "c_med": 2.4, "c_p10": 2.4, "color": "#f38aa5", "lines": 3,
                  "text_lum": 0.5, "bg_lum_sd": 0.2, "bg_lum_med": 0.9, "over_picture": True}),
    _f("layout", {"rule": "contrast_busy", "c_med": 3.5, "c_p10": 1.92, "color": "#ffffff", "lines": 1,
                  "text_lum": 1.0, "bg_lum_sd": 0.15, "bg_lum_med": 0.25, "over_picture": True}, severity="INFO"),
    _f("layout", {"rule": "leading", "leading": 19.0, "book_leading": 17.4}),
    _f("layout", {"rule": "margin_safe_zone", "mm": 4.9, "side": "bottom", "limit_mm": 5.0}),
    _f("layout", {"rule": "folio_sequence", "printed": 1, "expected": 122}, severity="ERROR", suggestion="122"),
    _f("layout", {"rule": "orphan", "next_page": 104}),
    _f("hyphenation", {"rule": "not_syllable_boundary", "word": "olanadım", "cut": 5, "syllables": "o-la-na-dım"},
       severity="ERROR", suggestion="ola- / nadım"),
    _f("hyphenation", {"rule": "lookalike_dash", "char": "U+2013"}, suggestion="ölüyor-"),
    _f("hyphenation", {"rule": "page_turn", "next_page": 54}),
    _f("spelling", {"kind": "bilinmeyen_kelime", "word": "İsranbul", "suggestions": ["İstanbul"]}, suggestion="İstanbul"),
    _f("spelling", {"kind": "ek_uyumu", "rule": "soru eki", "word": "mi", "previous": "muhal"}, suggestion="mı"),
    _f("spelling", {"kind": "tutarlılık", "used": "'", "style": "kesme_işareti", "book_majority": "’",
                    "book_counts": {"'": 30, "’": 156}}, suggestion="’"),
    _f("spelling", {"kind": "tırnak_içi_boşluk", "rule": "Kapanan tırnaktan önce boşluk konmaz."}),
    _f("name_spelling", {"kind": "ad_varyantı", "form": "Deniz", "book_form": "Denis", "book_form_count": 9,
                         "book_form_pages": [47, 88]}, suggestion="Denis"),
    _f("age_fit", {"kind": "LONG_SENTENCE", "words": 34, "band": [6, 10], "reference": "6-10", "threshold": 24}),
    _f("age_fit", {"kind": "SENSITIVE", "category": "DEATH_GRIEF", "probability": 0.86, "band": None,
                   "reason": "Ağır hastalık ayrıntılı anlatılıyor."}, severity="INFO"),
    _f("appearance", {"character": "Ayşe", "kind": "SAC_RENGI", "stable": True, "pages_a": [4],
                      "a": {"page": 4, "source": "TEXT", "value": "SARI", "quote": "sarı saçları"},
                      "b": {"page": 12, "source": "IMAGE", "value": "KAHVERENGI"}}, severity="ERROR"),
    _f("appearance", {"summary": {"characters": 3, "rows_text": 5, "rows_image": 7, "candidates": 2, "confirmed": 0}},
       page=None, severity="INFO"),
    _f("setting", {"kind": "TEXT_IMAGE", "aspect": "HAVA", "a": {"page": 12, "value": "KARLI", "quote": "kar"},
                   "b": {"page": 12, "source": "IMAGE", "seen": "YAGMURLU"}, "image": {"p_against": 0.74}}),
    _f("dialogue", {"rule": "A", "a": {"page": 12, "quote": "Ne?", "speaker": "Ali"},
                    "b": {"page": 12, "present": ["Ayşe", "Veli"], "events": []}}),
    _f("series_canon", {"character": "Anna", "other_book": "Öbür Kitap", "issue": "being_differs",
                        "being": "HUMAN_CHILD", "other_being": "HUMAN_ADULT"}),
    _f("edition_diff", {"op": "replace", "old": "eski", "new": "yeni", "old_page": 11, "sources": ["A", "A"]}),
    _f("imprint_crm", {"issue": "person_differs", "role": "ILLUSTRATOR", "crm": "Ada Yıl", "printed": "ADA YIL"}),
    _f("imprint_crm", {"issue": "page_count", "printed": 120, "crm": 128}, page=None),
    _f("word_variety", {"lemma": "fark", "sense": "farklı, ayrı", "idiom": "", "count": 2,
                        "forms": ["farklı", "farklıdır"], "pages": [85]}, suggestion="değişik, ayrı"),
    _f("word_overuse", {"lemma": "aslında", "count": 40, "per10k": 12.5, "corpus_per10k": 3.1, "ratio": 4.0,
                        "corpus_count": 90, "corpus_books": 25, "corpus_scope": "çocuk"}, page=None),
    _f("sentence_starts", {"count": 3, "lemma": "o", "passage_marked": "[[O]] geldi. [[O]] gitti. [[O]] durdu."}),
    _f("phrase_repeats", {"count": 2, "phrase": ["o", "arka", "bakmak"], "pages": [28, 175],
                          "occurrences": [{"page": 28, "text": "onların arkasından bakıp"}]}),
    _f("word_choice", {"kind": "foreign", "word": "enteresan", "alternative": "ilginç", "count": 1, "pages": [102]},
       suggestion="ilginç"),
    _f("text_contradictions", {"kind": "SAYI", "a": {"page": 3, "quote": "üç kardeş"},
                               "b": {"page": 12, "quote": "dört kardeş"}, "why": "Kardeş sayısı değişiyor."}),
    _f("timeline", {"kind": "MEVSIM", "a": {"page": 3, "quote": "kış geldi"}, "b": {"page": 12, "quote": "yaz sıcağı"},
                    "why": "kış sonra yaz"}),
    _f("props", {"rule": "A", "character": "Ali", "a": {"page": 11, "source": "TEXT", "state": "YANINDA", "item": "şemsiye"},
                 "b": {"page": 12, "source": "IMAGE", "state": "YOK", "item": "eşya yok"}}),
]


def test_every_check_has_a_template():
    assert set(labels()) <= set(M._RENDER), set(labels()) - set(M._RENDER)


def test_every_case_renders_plain_text_with_the_four_parts():
    for f in CASES:
        r = M.render(f["check"], f)
        assert r["fresh"], (f["check"], r)
        assert r["text"].endswith(".") and len(r["text"]) > 20, r
        assert not TECH.search(r["text"]), (f["check"], r["text"])
        assert not r["suggestion"] or not TECH.search(r["suggestion"]), (f["check"], r["suggestion"])
        if f["severity"] != "INFO" and f["page"] is not None:
            assert r["suggestion"], (f["check"], r)         # uyarı ve hatada ne yapılabileceği yazılı


def test_contrast_reads_like_the_editor_example():
    r = M.render("layout", CASES[0])
    assert r["text"].startswith("Açık pembe yazı arkadaki resmin üstünde zor okunuyor (3 satır).")
    assert "resmin sade bir yerine taşıyın" in r["suggestion"]
    assert r["detail"] == "Okunurluk oranı 2,4; en az 3, küçük yazıda en az 4,5 olmalı."
    w = M.word_comment({**r, "page": 12, "severity": "WARN"}, "Sayfa düzeni")
    assert w.startswith("Bakmanız önerilir — Sayfa düzeni\ns. 12 — Açık pembe yazı")
    assert w.endswith("(Okunurluk oranı 2,4; en az 3, küçük yazıda en az 4,5 olmalı.)")


def test_old_record_renders_in_new_words_and_kind_ignores_the_text():
    old = _f("layout", CASES[0]["details"], message="Metin rengi (#f38aa5) ile zeminin arasında kontrast düşük: "
                                                    "2.4:1 (WCAG en az 3:1, küçük metinde 4.5:1); 3 satır.")
    assert M.render("layout", old)["text"] == M.render("layout", CASES[0])["text"]
    assert M.kind_of("layout", old) == M.kind_of("layout", CASES[0]) == "layout:contrast_low"


def test_old_summaries_and_imprint_rows_are_read_from_their_own_old_text():
    s = _f("props", {}, page=None, severity="INFO",
           message="Eşya sürekliliği: 4 defter ve 2 metin durum kaydı, 6 sahne; 3 aday yargılandı, 1 bulgu. "
                   "Eşikler henüz gerçek kitapta ölçülmedi.")
    r = M.render("props", s)
    assert r["fresh"] and "6 sahne, 1 tutarsızlık" in r["text"]
    i = _f("imprint_crm", {"printed": "5", "crm": 7}, message="Künyede dizi numarası 5; CRM'de 7.")
    assert M.kind_of("imprint_crm", i) == "imprint_crm:series_no_differs"
    assert "dizi numarası (5)" in M.render("imprint_crm", i)["text"]
    old_sens = _f("age_fit", {"kind": "SENSITIVE", "category": "VIOLENCE", "probability": 0.9, "band": [6, 10]},
                  message="6-10 yaş için hassas içerik adayı (şiddet): Kavga ayrıntılı anlatılıyor.")
    assert "Kavga ayrıntılı anlatılıyor." in M.render("age_fit", old_sens)["text"]


def test_missing_field_falls_back_to_the_stored_text_and_names_the_field():
    r = M.render("layout", _f("layout", {"rule": "body_size"}, message="eski metin"))
    assert not r["fresh"] and r["text"] == "eski metin" and r["missing"] == ["size"]


def test_numbers_colours_and_pages_in_turkish():
    assert (M.num(2.4), M.num(27748, 0), M.num(19.0), M.num(0.25, 2)) == ("2,4", "27.748", "19", "0,25")
    assert M.pct(0.099) == "%10"
    assert [M.color_name(c) for c in ("#f38aa5", "#f37121", "#ffffff", "#000000", "#8b5a2b")] == \
        ["açık pembe", "turuncu", "beyaz", "siyah", "kahverengi"]
    assert M.pages_txt([126, 24, 42]) == "s. 24, 42 ve 126" and M.pages_txt([5]) == "s. 5"


def test_checks_write_the_same_text_the_screen_shows():
    f = {**CASES[2], "message": ""}
    M.put("layout", f)
    assert f["message"] == M.render("layout", f)["text"]
    g = {k: v for k, v in CASES[16].items() if k != "message"}
    M.put("appearance", g, advice=True)
    assert g["suggestion"] == M.render("appearance", g)["suggestion"]
