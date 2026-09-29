"""Kaynak seçimi yardımcıları (2026-09-29): zaman ifadesi konumu, sorunun öznesi, terimin başı, plan/tahmin kolonu."""
from __future__ import annotations

from types import SimpleNamespace

from semantic_layer.runtime.resolver import _PLANNED_FIGURE, _subject_position, _temporal_positions, _term_head


def test_time_words_are_found_by_position():
    toks = ["suresi", "bu", "yil", "icinde", "dolacak", "telif", "sozlesmeleri", "hangileri"]
    assert _temporal_positions(toks, [SimpleNamespace(text="bu yil")]) == {1, 2}
    assert _temporal_positions(toks, []) == set()


def test_the_subject_is_the_last_content_word():
    assert _subject_position(["suresi", "bu", "yil", "icinde", "dolacak", "telif", "sozlesmeleri", "hangileri"]) == 6
    assert _subject_position(["isbn", "listesinde", "stok", "kartiyla", "eslesmemis", "yayin", "numaralari", "var", "mi"]) == 6
    assert _subject_position(["mi", "var"]) == -1


def test_a_modifier_is_not_the_head_of_a_term():
    assert _term_head("kac kez okunt") == "okunt"
    assert _term_head("telif sozlesme") == "sozlesme"


def test_planned_figures_are_told_apart_from_actuals():
    assert _PLANNED_FIGURE.search("new_potansiyelnetsatisonikiay")
    assert _PLANNED_FIGURE.search("new_ongorulensatis")
    assert not _PLANNED_FIGURE.search("new_toplametkinlikgideri")
