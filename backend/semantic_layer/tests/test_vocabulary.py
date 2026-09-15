"""Everyday names for fields: generated from descriptions, never over a person's word, resolvable
only after a person's yes."""
from datetime import date

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.config import SemanticSettings
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, SemanticType
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401
from semantic_layer import vocabulary as V

SETTINGS = SemanticSettings(store_dsn="sqlite://", tenant_id=TENANT, datasource_id=DS)


def describe_city(profiles, text="Şehir. Cari kartın bulunduğu il."):
    card = next(p for p in profiles if p.entity == "CLCARD")
    col = card.column("CITY")
    col.description = text
    return card


def reply(*terms):
    return '{"terms": [' + ", ".join(
        '{"term": "%s", "examples": ["%s bazında ciro", "Ankara %s", "%si de göster"], "ambiguous": ""}' % (t, t, t, t) for t in terms) + "]}"


def target(catalog, profiles, column="CITY"):
    return next(t for t in V.targets(catalog, SETTINGS, profiles) if t["entity"] == "CLCARD" and t["column"] == column)


def test_generation_proposes_from_the_description_and_refutes_collisions(catalog, profiles):
    describe_city(profiles)
    llm = FakeLlm(replies=[reply("il", "vilayet", "şehir", "kanal", "CITY")])
    out = V.generate_one(catalog, SETTINGS, llm, profiles, target(catalog, profiles))
    rows = {r["term"]: r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY")}
    assert out["proposed"] == 3 and rows["il"]["status"] == "PROPOSED" and rows["vilayet"]["status"] == "PROPOSED"
    # "kanal" is a certified name for another column; "CITY" is the column's own technical name
    assert rows["kanal"]["status"] == "DROPPED" and "çakışma" in rows["kanal"]["reason"]
    assert rows["CITY"]["status"] == "DROPPED" and "teknik" in rows["CITY"]["reason"]


def test_an_unchanged_description_costs_no_model_call(catalog, profiles):
    describe_city(profiles)
    llm = FakeLlm(replies=[reply("il")])
    V.generate_one(catalog, SETTINGS, llm, profiles, target(catalog, profiles))
    again = V.maintain(catalog, SETTINGS, llm, profiles, only=[("CLCARD", "CITY")])
    assert again["calls"] == 0 and again["skipped"] == 1 and len(llm.calls) == 1


def test_a_persons_word_is_never_overwritten_and_a_rejection_never_returns(catalog, profiles):
    describe_city(profiles)
    eng = EvidenceEngine(catalog, min_support=3)
    V.add_human(catalog, SETTINGS, profiles, eng, "CLCARD", "CITY", "memleket", "ayşe")
    llm = FakeLlm(replies=[reply("memleket", "vilayet", "il"), reply("memleket", "vilayet", "il", "kent")])
    V.generate_one(catalog, SETTINGS, llm, profiles, target(catalog, profiles))
    rows = {r["term"]: r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY")}
    assert rows["memleket"]["source"] == "human" and rows["memleket"]["status"] == "APPROVED"
    V.decide(catalog, SETTINGS, profiles, eng, rows["vilayet"]["id"], "REJECT", "ayşe", "bizde kullanılmaz")
    # the description changes: generation runs again and proposes "kent"; the human word and the
    # rejection stand, the stale proposal "il" is dropped and re-proposed under the new text
    describe_city(profiles, "Şehir. Cari kartın il bilgisi (yeni açıklama).")
    V.generate_one(catalog, SETTINGS, llm, profiles, target(catalog, profiles))
    rows = {r["term"]: r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY")}
    assert rows["memleket"]["status"] == "APPROVED" and rows["memleket"]["source"] == "human"
    assert rows["vilayet"]["status"] == "REJECTED"
    assert rows["kent"]["status"] == "PROPOSED" and rows["il"]["status"] == "PROPOSED"


def test_approval_makes_the_word_resolvable_as_a_breakdown(catalog, profiles):
    describe_city(profiles)
    eng = EvidenceEngine(catalog, min_support=3)
    llm = FakeLlm(replies=[reply("vilayet")])
    V.generate_one(catalog, SETTINGS, llm, profiles, target(catalog, profiles))
    row = next(r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY") if r["term"] == "vilayet")
    before = SemanticResolver(catalog, TENANT, DS, profiles).resolve("vilayet bazında net ciro", today=date(2026, 7, 20))
    assert not any(s.term == "vilayet" for s in before.group_by)
    out = V.decide(catalog, SETTINGS, profiles, eng, row["id"], "APPROVE", "ayşe")
    c = catalog.get_concept(out["conceptId"])
    assert c.status == "CERTIFIED" and c.explain.get("human_certified_by") == "ayşe" and c.semantic_type == SemanticType.COLUMN
    after = SemanticResolver(catalog, TENANT, DS, profiles).resolve("vilayet bazında net ciro", today=date(2026, 7, 20))
    assert any(s.mapping and s.mapping.entity == "CLCARD" and s.mapping.column == "CITY" for s in after.group_by), after.to_dict()
    # a second approval on the same field joins the same concept as a synonym
    llm2 = FakeLlm(replies=[reply("il")])
    describe_city(profiles, "Şehir / il.")
    V.generate_one(catalog, SETTINGS, llm2, profiles, target(catalog, profiles))
    row2 = next(r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY") if r["term"] == "il")
    out2 = V.decide(catalog, SETTINGS, profiles, eng, row2["id"], "APPROVE", "ayşe")
    assert out2["conceptId"] == out["conceptId"] and "il" in catalog.get_concept(out["conceptId"]).synonyms


def test_gaps_list_the_fields_nobody_described(catalog, profiles):
    items = V.gaps(catalog, SETTINGS, profiles, entities=["CLCARD"])
    assert any(g["column"] == "CITY" for g in items)
    describe_city(profiles)
    assert not any(g["column"] == "CITY" for g in V.gaps(catalog, SETTINGS, profiles, entities=["CLCARD"]))


def test_english_terms_are_refuted_and_pending_english_rows_are_dropped(catalog, profiles):
    """Sözlük Türkçe: model İngilizce terim önerse de düşer; önceden bekleyen İngilizce öneriler bakımda düşer,
    insanın kararı olduğu gibi kalır. Kısaltmalar (KDV) İngilizce sayılmaz."""
    describe_city(profiles)
    llm = FakeLlm(replies=[reply("il", "city name", "KDV bölgesi")])
    V.generate_one(catalog, SETTINGS, llm, profiles, target(catalog, profiles))
    rows = {r["term"]: r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY")}
    assert rows["il"]["status"] == "PROPOSED" and rows["KDV bölgesi"]["status"] == "PROPOSED"
    assert rows["city name"]["status"] == "DROPPED" and "İngilizce" in rows["city name"]["reason"]

    # Talimat değişmeden önce üretilmiş bekleyen İngilizce öneri ve ona insanın verdiği bir onay
    from semantic_layer.store import schema as S
    with catalog.engine.begin() as conn:
        conn.execute(S.sl_vocabulary.update().where(S.sl_vocabulary.c.id == rows["il"]["id"]).values(term="document type"))
    eng = EvidenceEngine(catalog, min_support=3)
    V.add_human(catalog, SETTINGS, profiles, eng, "CLCARD", "CITY", "city", "ayşe")
    assert V.drop_english(catalog, SETTINGS) == 1
    after = {r["term"]: r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY")}
    assert after["document type"]["status"] == "DROPPED"
    assert after["city"]["source"] == "human" and after["city"]["status"] == "APPROVED"
