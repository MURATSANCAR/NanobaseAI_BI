"""Probes may only contradict the catalog with an answer they actually have."""

from __future__ import annotations

from semantic_layer.evidence.probe import ValueProbe, probe_catalog
from semantic_layer.models import ConceptStatus, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.profiler.connectors import ModelFileConnector
from semantic_layer.tests.conftest import DS, PROJECT, TENANT


class TruncatedConnector:
    """A database whose value inventory is cut off at the limit — the classic false 'missing value'."""

    dialect = "sqlite"
    supports_execution = True
    quote_l = quote_r = '"'
    default_schema = "main"

    def __init__(self, limit_hit: bool):
        self.limit_hit = limit_hit

    def q(self, ident):
        return f'"{ident}"'

    def top_values(self, schema, table, column, limit):
        if self.limit_hit:
            return [(str(i), 10) for i in range(limit)]        # exactly `limit` rows → truncated
        return [("7", 100), ("8", 50)]                          # a complete, small inventory

    def execute(self, sql, limit):
        return [], [{"v": 1.0}], False


def _candidate(store, profiles, term, values):
    prof = next(p for p in profiles if p.entity == "INVOICE")
    c, _ = store.upsert_concept(TENANT, DS, term, SemanticType.DIMENSION_VALUE,
                                mapping=Mapping(concept_id="", entity="INVOICE", table_pattern=prof.table_pattern, column="TRCODE", operator="IN", values=values),
                                status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=3, payload={"pairs": ["a", "b", "c"], "precision": 1.0}))
    return c


def test_a_truncated_inventory_never_rejects(store, synthetic_profiles):
    c = _candidate(store, synthetic_profiles, "bilinmeyen", ["9999"])
    report = probe_catalog(store, TENANT, DS, synthetic_profiles, TruncatedConnector(limit_hit=True))
    assert report.values_rejected == 0
    assert not store.list_counter_evidence(c.id), "an incomplete answer was treated as a contradiction"


def test_a_complete_inventory_does_reject_a_value_that_is_not_there(store, synthetic_profiles):
    c = _candidate(store, synthetic_profiles, "hayali", ["9999"])
    report = probe_catalog(store, TENANT, DS, synthetic_profiles, TruncatedConnector(limit_hit=False))
    assert report.values_rejected == 1
    kinds = {x.conflict_type for x in store.list_counter_evidence(c.id)}
    assert kinds == {"VALUE_MISMATCH"}


def test_an_offline_connector_is_never_probed(store, synthetic_profiles):
    """A file-backed source can describe a schema but not answer questions about the data."""
    if not PROJECT.exists():
        return
    connector = ModelFileConnector(PROJECT)
    assert connector.supports_execution is False
    c = _candidate(store, synthetic_profiles, "toptan", ["8"])
    from semantic_layer.pipeline import run_pipeline  # the guard lives in the pipeline
    import inspect

    assert 'getattr(connector, "supports_execution", False)' in inspect.getsource(run_pipeline)
    assert not store.list_counter_evidence(c.id)


def test_a_measure_that_times_out_is_not_a_measure_that_failed(store, profiles):
    """A timeout says how much data there is; a dropped connection says something about the network.
    Neither says the definition is wrong, and counting them against it decertifies correct knowledge
    the moment a table grows."""
    from semantic_layer.evidence.probe import probe_catalog
    from semantic_layer.models import Evidence, EvidenceType, Mapping, SemanticType
    from semantic_layer.store.catalog_store import ConceptStatus

    for p in profiles:
        store.upsert_profile(p)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    c, _ = store.upsert_concept(TENANT, DS, "ciro", SemanticType.METRIC,
                                mapping=Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, formula="SUM(INVOICE.NETTOTAL)"),
                                status=ConceptStatus.CERTIFIED)
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=3, payload={"pairs": ["a", "b", "c"]}))

    class _Slow:
        dialect = "sqlite"
        supports_execution = True

        def execute(self, sql, limit):
            raise RuntimeError("('HYT00', '[HYT00] [FreeTDS][SQL Server]Timeout expired (0)')")

    report = probe_catalog(store, TENANT, DS, profiles, _Slow(), context={"n0": "411", "n1": "01"}, dialect="sqlite")
    assert not store.list_counter_evidence(c.id), "a check that could not run is not a failed check"
    assert any("doğrulanamadı" in e for e in report.errors), report.errors
