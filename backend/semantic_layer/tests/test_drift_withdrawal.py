"""Drift is a claim about a moment, and a moment passes.

A scan that cannot see a table records BLOCKING counter-evidence: the table is gone, decertify what
depends on it. That is right when the table really went away, and wrong the moment it comes back —
the claim stays attached, and every later run reads it as a live objection. On this deployment that
is what quietly took "ciro", "kanal" and the customer joins out of the certified vocabulary hours
after the narrow scan that mislaid them.

So the engine must be able to withdraw its own claim: when the mapping points at something that is
there again, the drift objection goes.
"""

from __future__ import annotations

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import (ColumnProfile, Concept, ConceptStatus, CounterEvidence, Evidence,
                                   EvidenceType, Mapping, SchemaProfile)

TENANT, DS = "t1", "logo"


def _profile(trcode_distinct: int = 8) -> SchemaProfile:
    """`trcode_distinct` matters: a top-values list is only the whole truth when it covers every
    distinct value, and both the detector and the withdrawal respect that."""
    return SchemaProfile(
        datasource_id=DS, table_name="LG_411_01_INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
        entity="INVOICE", schema_name="dbo", row_count=1000,
        columns=[ColumnProfile(name="NETTOTAL", data_type="decimal", distinct_count=900),
                 ColumnProfile(name="TRCODE", data_type="int", distinct_count=trcode_distinct,
                               top_values=[("7", 500), ("8", 300)])],
    )


def _certified(store, term="ciro", column="NETTOTAL", values=None):
    m = Mapping("", "INVOICE", "LG_{n0}_{n1}_INVOICE", column=column, values=values or [])
    c, _ = store.upsert_concept(TENANT, DS, term, "COLUMN", mapping=m, status=ConceptStatus.CERTIFIED)
    store.add_evidence(Evidence(c.id, EvidenceType.DOC, "logo:dict", support_count=1, weight=0.5))
    return c


def test_a_table_that_came_back_withdraws_the_drift_objection(store):
    c = _certified(store)
    store.add_counter_evidence(CounterEvidence(c.id, "drift:table", "DRIFT",
                                               payload={"missing_table": "LG_{n0}_{n1}_INVOICE"}, severity="BLOCKING"))
    store.update_concept(c.id, explain={"schema_drift": "table LG_{n0}_{n1}_INVOICE missing"})
    eng = EvidenceEngine(store, min_support=3, threshold=0.6)
    eng.detect_drift(TENANT, DS, {"INVOICE": _profile()}, scoped=False)
    assert not [x for x in store.list_counter_evidence(c.id) if x.conflict_type == "DRIFT"]
    # the note the detector left is part of the objection: the gate reads it directly
    assert not store.get_concept(c.id).explain.get("schema_drift")


def test_a_table_still_missing_keeps_it(store):
    c = _certified(store)
    store.add_counter_evidence(CounterEvidence(c.id, "drift:table", "DRIFT",
                                               payload={"missing_table": "LG_{n0}_{n1}_INVOICE"}, severity="BLOCKING"))
    eng = EvidenceEngine(store, min_support=3, threshold=0.6)
    eng.detect_drift(TENANT, DS, {}, scoped=False)
    assert [x for x in store.list_counter_evidence(c.id) if x.conflict_type == "DRIFT"]


def test_a_value_that_is_gone_is_not_withdrawn(store):
    """Withdrawal is per-claim, not a blanket amnesty: the column is there, the value is not."""
    c = _certified(store, term="iade", column="TRCODE", values=["2", "3"])
    store.add_counter_evidence(CounterEvidence(c.id, "drift:values", "DRIFT",
                                               payload={"values_gone": ["2", "3"]}, severity="BLOCKING"))
    eng = EvidenceEngine(store, min_support=3, threshold=0.6)
    eng.detect_drift(TENANT, DS, {"INVOICE": _profile(trcode_distinct=2)}, scoped=False)
    assert [x for x in store.list_counter_evidence(c.id) if x.conflict_type == "DRIFT"]


def test_certification_survives_the_full_run_once_the_table_is_back(store):
    """The whole point: a concept the data supports must not come out of a run decertified by an
    objection the same run could see was false."""
    c = _certified(store)
    store.add_counter_evidence(CounterEvidence(c.id, "drift:table", "DRIFT",
                                               payload={"missing_table": "LG_{n0}_{n1}_INVOICE"}, severity="BLOCKING"))
    eng = EvidenceEngine(store, min_support=3, threshold=0.6)
    eng.run(TENANT, DS, [_profile()], scoped=False)
    assert store.get_concept(c.id).status != ConceptStatus.REJECTED
