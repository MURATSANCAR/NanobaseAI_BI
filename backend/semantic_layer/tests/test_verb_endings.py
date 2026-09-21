"""One verb, several endings: "tahsil edilen" / "edildi" / "edilmiş" / "ettiğimiz" meet at lookup time.

The stored normalized keys are not touched (`normalize_term` is unchanged); the equivalence is made by
the resolver when it looks a phrase up. These tests pin the three guards that keep it from inventing a
match: same root letters, a different ending, one reading.
"""
from __future__ import annotations

from semantic_layer.models import Concept, ConceptStatus, Mapping, SemanticType
from semantic_layer.normalize import argument_core, normalize_term, tokenize, verb_aspect_keys


def _aspects(word: str) -> set[str]:
    return {k for k, _ in verb_aspect_keys(word)}


def test_endings_of_one_finished_event_share_a_key():
    for form in ("edilen", "edildi", "edilmiş", "edilmişlerin", "edilenlerin", "edilmiştir"):
        assert _aspects(form) == {"edil|R"}, form
    for form in ("ödenen", "ödenmiş", "ödendi"):
        assert _aspects(form) == {"oden|R"}, form
    for form in ("olan", "olmuş", "oldu"):
        assert _aspects(form) == {"ol|R"}, form


def test_the_dik_relative_of_an_active_verb_meets_the_passive():
    """"tahsile verdiğimiz çek" is the cheque that was given for collection: "tahsile verilen çek"."""
    assert "veril|R" in _aspects("verdiğimiz") and "veril|R" in _aspects("verilen")
    assert "edil|R" in _aspects("ettiğimiz")
    assert "oden|R" in _aspects("ödediğimiz")
    assert "kesil|R" in _aspects("kestiğimiz")
    assert "alin|R" in _aspects("aldığımız") and "alin|R" in _aspects("alınan")


def test_future_and_negation_stay_apart():
    assert _aspects("edilecek") == {"edil|F"}                    # still to come ≠ done
    assert "edil|R" not in _aspects("edilmemiş")                   # not collected ≠ collected
    assert "edilme|R" in _aspects("edilmemiş") and "edilme|R" in _aspects("edilmeyen")


def test_vowel_harmony_is_required():
    """Folded text keeps rounding (i/u) and a/e, so a disharmonic ending is not a verb ending."""
    assert _aspects("olmis") == set()        # "ol" + mİş: rounding says "olmuş"
    assert _aspects("edilmus") == set()
    assert _aspects("gelan") == set()        # front root, back ending


def test_homographs_of_the_stem_function_are_not_verbs():
    """`stem` makes "çeviri" and "çevir", "basın" and "bas" collide; the verb reading does not."""
    for word in ("çeviri", "çevir", "basın", "bas", "protesto", "tahsile", "kanal", "fatura", "plan"):
        assert _aspects(word) == set(), word


def test_the_governed_noun_keeps_its_case():
    assert argument_core("limitini") == argument_core("limit")
    assert argument_core("faturası") == argument_core("fatura")
    assert argument_core("stoğa") != argument_core("stoktan")      # into stock ≠ out of stock
    assert argument_core("tahsile") != argument_core("tahsil")


def _concept(term: str, synonyms=(), cid=None) -> Concept:
    c = Concept(tenant_id="t", datasource_id="d", term=term, normalized_term=normalize_term(term),
                semantic_type=SemanticType.DIMENSION_VALUE, status=ConceptStatus.CERTIFIED, confidence=1.0,
                synonyms=list(synonyms))
    if cid:
        c.id = cid
    return c


def _index(*concepts: Concept) -> dict:
    index: dict = {}
    for c in concepts:
        m = Mapping(concept_id=c.id, entity="CSCARD", table_pattern="LG_{n0}_CSCARD", column="CURRSTAT", operator="IN", values=["8"])
        for k in dict.fromkeys([c.normalized_term, *(normalize_term(s) for s in c.synonyms)]):
            index.setdefault(k, []).append((c, [m]))
    return index


def _lookup(index: dict, phrase: str):
    from semantic_layer.runtime.resolver import SemanticResolver
    r = object.__new__(SemanticResolver)
    r._aspects_for, r._aspects = None, {}
    return r._by_verb_ending(index, tokenize(phrase))


def test_the_resolver_finds_the_stored_ending():
    index = _index(_concept("tahsil edilen çek", ["tahsil edildi"]), _concept("tahsile verilen çek", ["tahsile verildi"]))
    assert _lookup(index, "tahsil edilmiş çeklerin") == normalize_term("tahsil edilen çek")
    assert _lookup(index, "tahsile verdiğimiz çekler") == normalize_term("tahsile verilen çek")
    # the two verbs are different words ("tahsil etmek" / "tahsile vermek") and never meet
    assert _lookup(index, "tahsil edilmiş") in (normalize_term("tahsil edildi"), normalize_term("tahsil edilen çek"), None)
    assert _lookup(index, "tahsile verilmiş") == normalize_term("tahsile verildi")


def test_no_match_without_a_noun_before_the_verb_or_for_one_word():
    index = _index(_concept("tahsil edilen çek"))
    assert _lookup(index, "edilmiş çek") is None
    assert _lookup(index, "edilmiş") is None


def test_future_negation_and_same_ending_do_not_match():
    index = _index(_concept("tahsil edilen çek"))
    assert _lookup(index, "tahsil edilecek çek") is None
    assert _lookup(index, "tahsil edilmemiş çek") is None
    assert _lookup(index, "tahsil edilen çek") is None          # same ending: the exact lookup's job


def test_a_shape_two_concepts_share_is_not_guessed_at():
    index = _index(_concept("tahsil edilen", cid="a"), _concept("tahsil edildi", cid="b"))
    assert _lookup(index, "tahsil edilmiş") is None


def test_case_of_the_governed_noun_must_agree():
    index = _index(_concept("stoktan düşen"))
    assert _lookup(index, "stoğa düşmüş") is None
    assert _lookup(index, "stoktan düşmüş") == normalize_term("stoktan düşen")
