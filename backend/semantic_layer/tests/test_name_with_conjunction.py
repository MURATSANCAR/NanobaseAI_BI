from semantic_layer.history.question_facts import extract_question_facts
from semantic_layer.normalize import normalize_term
from semantic_layer.runtime.resolver import SemanticResolver as Resolver


def test_name_carrying_ve_forms_one_key():
    qf = extract_question_facts("Ödenecek vergi ve fonlar hesabında ne kadar tutar var?", n_max=4)
    assert normalize_term("ödenecek vergi ve fonlar") in {t[2] for t in qf.terms}


def test_ve_at_an_edge_does_not_join():
    qf = extract_question_facts("Satış ve iade toplamı", n_max=4)
    assert not any(t[2].startswith("ve ") or t[2].endswith(" ve") for t in qf.terms)


def test_balance_side_word_belongs_to_the_balance():
    toks = ["alicilar", "hesabinin", "borc", "bakiyesi", "ne"]
    assert Resolver._balance_word(toks, 3) and Resolver._balance_word(toks, 2)
    assert not Resolver._balance_word(["borc", "toplami"], 0)
