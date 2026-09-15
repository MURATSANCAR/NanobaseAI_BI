"""Automatic approval: only a term measured to lead to its own field, and to take nothing away from a
question already asked, is approved without a person."""
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import Mapping
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.store import schema as S
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401
from semantic_layer.tests.test_vocabulary import SETTINGS, describe_city, reply, target
from semantic_layer import vocabulary as V
from semantic_layer import vocabulary_probe as P

TODAY = date(2026, 7, 20)


def real(profiles):
    return lambda store: SemanticResolver(store, TENANT, DS, profiles)


def propose(catalog, profiles, *terms, column="CITY"):
    V.generate_one(catalog, SETTINGS, FakeLlm(replies=[reply(*terms)]), profiles, target(catalog, profiles, column))
    return {r["term"]: r for r in V.existing(catalog, SETTINGS, "CLCARD", column)}


def test_a_term_that_leads_to_its_field_is_approved_and_becomes_resolvable(catalog, profiles):
    describe_city(profiles)
    propose(catalog, profiles, "vilayet")
    eng = EvidenceEngine(catalog, min_support=3)
    out = P.auto_decide(catalog, SETTINGS, profiles, eng, resolver_factory=real(profiles), today=TODAY)
    assert out["approved"] == 1, out
    row = next(r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY") if r["term"] == "vilayet")
    assert row["status"] == "APPROVED" and row["decided_by"] == P.AUTO and "yoklama" in row["reason"]
    after = SemanticResolver(catalog, TENANT, DS, profiles).resolve("vilayet bazında net ciro", today=TODAY)
    assert any(s.mapping and s.mapping.entity == "CLCARD" and s.mapping.column == "CITY" for s in after.group_by)


def test_a_term_proposed_for_two_fields_waits_for_a_person(catalog, profiles):
    describe_city(profiles)
    propose(catalog, profiles, "bölge")
    card = next(p for p in profiles if p.entity == "CLCARD")
    other = next(c for c in card.columns if c.name != "CITY")
    other.description = "Bölge bilgisi."
    propose(catalog, profiles, "bölge", column=other.name)
    eng = EvidenceEngine(catalog, min_support=3)
    out = P.auto_decide(catalog, SETTINGS, profiles, eng, resolver_factory=real(profiles), today=TODAY)
    assert out["approved"] == 0 and out["toPerson"] == 2, out
    rows = V.existing(catalog, SETTINGS, "CLCARD", "CITY")
    row = next(r for r in rows if r["term"] == "bölge")
    assert row["status"] == "PROPOSED" and row["reason"].startswith(P.PREFIX) and "farklı alana" in row["reason"]


def test_a_generator_ambiguity_is_never_decided_by_a_machine(catalog, profiles):
    describe_city(profiles)
    rows = propose(catalog, profiles, "vilayet")
    with catalog.engine.begin() as conn:
        conn.execute(S.sl_vocabulary.update().where(S.sl_vocabulary.c.id == rows["vilayet"]["id"]).values(reason="idari bölge de olabilir"))
    eng = EvidenceEngine(catalog, min_support=3)
    out = P.auto_decide(catalog, SETTINGS, profiles, eng, resolver_factory=real(profiles), today=TODAY)
    row = next(r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY") if r["term"] == "vilayet")
    assert out["approved"] == 0 and row["status"] == "PROPOSED" and row["reason"] == "idari bölge de olabilir"


class _Fake:
    """Resolves to a fixed meaning; with the probed term visible it resolves to another."""

    def __init__(self, store, plain, augmented):
        self.aug = isinstance(store, P._WithTerm)
        self.plain, self.augmented = plain, augmented

    def resolve(self, text, today=None):
        maps = self.augmented if self.aug else self.plain
        return SimpleNamespace(slots=[SimpleNamespace(mapping=Mapping("", e, e, column=c)) for e, c in maps], group_by=[])


def test_a_term_that_takes_meaning_away_from_an_asked_question_waits(catalog, profiles):
    describe_city(profiles)
    propose(catalog, profiles, "vilayet")
    now = datetime.now(timezone.utc)
    with catalog.engine.begin() as conn:
        conn.execute(S.sl_query_log.insert().values(id=uuid.uuid4().hex, tenant_id=TENANT, datasource_id=DS,
                                                    question="vilayet kanal ciro", normalized_question="vilayet kanal ciro",
                                                    resolved_json={}, created_at=now))
    # with the term: the example reaches CLCARD.CITY, but the asked question loses its INVOICE.CHANNEL meaning
    factory = lambda store: _Fake(store, plain=[("INVOICE", "CHANNEL")], augmented=[("CLCARD", "CITY")])
    eng = EvidenceEngine(catalog, min_support=3)
    out = P.auto_decide(catalog, SETTINGS, profiles, eng, resolver_factory=factory, today=TODAY)
    row = next(r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY") if r["term"] == "vilayet")
    assert out["approved"] == 0 and row["status"] == "PROPOSED" and "geçmiş bir sorunun" in row["reason"], out
    # a term that only adds meaning passes the same check
    factory = lambda store: _Fake(store, plain=[("INVOICE", "CHANNEL")], augmented=[("INVOICE", "CHANNEL"), ("CLCARD", "CITY")])
    out = P.auto_decide(catalog, SETTINGS, profiles, eng, resolver_factory=factory, today=TODAY, apply=False)
    assert out["approved"] == 1, out


def test_an_example_that_does_not_reach_the_field_waits(catalog, profiles):
    describe_city(profiles)
    propose(catalog, profiles, "vilayet")
    factory = lambda store: _Fake(store, plain=[], augmented=[("INVOICE", "CHANNEL")])
    eng = EvidenceEngine(catalog, min_support=3)
    out = P.auto_decide(catalog, SETTINGS, profiles, eng, resolver_factory=factory, today=TODAY)
    row = next(r for r in V.existing(catalog, SETTINGS, "CLCARD", "CITY") if r["term"] == "vilayet")
    assert out["approved"] == 0 and row["status"] == "PROPOSED" and "alana gitmedi" in row["reason"]
