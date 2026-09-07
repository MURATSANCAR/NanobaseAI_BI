"""No word of a question may disappear without a word said about it.

A term the catalog cannot place is a gap to report. A term read as grammar is a reading to justify.
What must never happen is the third case: a word that shaped nothing, was reported nowhere, and left
the user with an answer to a wider question than the one they asked.
"""

import re

from semantic_layer.history.question_facts import extract_question_facts
from semantic_layer.runtime.resolver import _asks_for_a_trend, _is_trend_cue


def test_a_brand_that_begins_with_a_cue_is_not_a_cue():
    # "trend" plus a few letters also spells a marketplace; only the morphology tells them apart
    assert not _is_trend_cue("trendyol")
    assert not _asks_for_a_trend("trendyol satışlarını getir")


def test_the_cue_itself_still_reads_as_one_however_it_is_inflected():
    for word in ("trend", "trendi", "artış", "artışı", "büyüme", "büyümesi", "gidişat", "gidişatı"):
        assert _is_trend_cue(word), word
    assert _asks_for_a_trend("satışların aylık gidişatı ne")
    assert _asks_for_a_trend("ay ay satışlar")


def test_a_column_named_in_lower_case_is_still_a_column():
    # people type lower case; the database spells its columns in capitals
    for q in ("speccode 5 satışları", "SPECCODE 5 satışları", "speccode: 5", "speccode = 5"):
        codes = extract_question_facts(q).explicit_codes
        assert ("SPECCODE", ("5",)) in codes, (q, codes)


def test_several_codes_after_a_column_are_all_kept():
    codes = extract_question_facts("trcode 7,8 ve 9 satışları").explicit_codes
    assert codes and codes[0][0] == "TRCODE" and set(codes[0][1]) == {"7", "8", "9"}
