"""A term the catalog knows is found however the question inflects it."""
from __future__ import annotations

from semantic_layer.runtime.resolver import _rooted
from semantic_layer.tests.test_runtime import catalog  # noqa: F401 — the certified fixture lives there


def test_a_word_and_its_inflections_reduce_to_one_root():
    """Turkish inflects heavily and a question rarely uses the bare form. Nothing here is written
    down per language: the root function is the one the rest of the resolver already uses."""
    for form in ("kanal", "kanala", "kanallara", "kanalda"):
        assert _rooted(form) == "kanal", form
    for form in ("satis", "satisi", "satislar"):
        assert _rooted(form) == "satis", form


def test_a_phrase_reduces_word_by_word():
    assert _rooted("iade orani") == _rooted("iade oran")


def _resolver(store, profiles):
    from semantic_layer.runtime.resolver import SemanticResolver
    from semantic_layer.tests.conftest import DS, TENANT
    return SemanticResolver(store, TENANT, DS, profiles)


def test_the_same_question_asked_two_ways_resolves_the_same(catalog, profiles):
    """"Kanal bazında ciro" resolved and "kanala göre ciro" did not — the question reaching the
    lookup has already been stemmed, and stemming an inflected word does not land where stemming its
    root does ("kanal" → "kanal", "kanala" → "kana"), so the two never met."""
    r = _resolver(catalog, profiles)
    duz = r.resolve("2026 toptan satış tutarı")
    egik = r.resolve("2026 toptan satışı ne kadar")
    assert duz.state == "RESOLVED", duz.unresolved
    assert egik.state == duz.state, egik.unresolved
    assert not egik.unresolved


def test_a_root_two_different_terms_share_is_not_guessed_at(catalog, profiles):
    """"One of these two, and I picked" is the silent decision this system exists to avoid."""
    r = _resolver(catalog, profiles)
    index = catalog.certified_index(*_ids())
    roots = r._by_root(index)
    for root, senses in roots.items():
        sharing = [k for k in index if _rooted(k) == root]
        assert root in sharing or len(sharing) == 1, (root, sharing)


def _ids():
    from semantic_layer.tests.conftest import DS, TENANT
    return TENANT, DS
