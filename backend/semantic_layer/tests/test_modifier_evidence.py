import pytest

from semantic_layer.models import ConceptStatus, Mapping, SemanticType, ValidatedPair
from semantic_layer.runtime.compiler import CompilerRouter
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.history.modifiers import ModifierHistory
from semantic_layer.normalize import tokenize


@pytest.fixture
def resolver(store):
    for term, kind, column in [("iskonto", SemanticType.METRIC, "discount"),
                               ("müşteriler", SemanticType.COLUMN, "customer"),
                               ("siparişler", SemanticType.COLUMN, "order_id"),
                               ("tedarikçiler", SemanticType.COLUMN, "supplier")]:
        store.upsert_concept("t", "d", term, kind, status=ConceptStatus.CERTIFIED,
                             mapping=Mapping(concept_id="", entity="orders", table_pattern="orders",
                                             column=column, formula="SUM(discount)" if kind == SemanticType.METRIC else None,
                                             operator="COLUMN"))
    return SemanticResolver(store, "t", "d", [])


@pytest.mark.parametrize("verb", ["veren", "verdiğimiz", "yaptığımız", "edilen", "aldığımız", "bekleyen"])
@pytest.mark.parametrize("frame", ["iskonto {} müşteriler", "{} siparişler", "sipariş {} tedarikçiler", "müşteriye {} siparişler"])
def test_no_morphology_or_position_can_certify_a_modifier(resolver, verb, frame):
    q = resolver.resolve(frame.format(verb))
    token = tokenize(verb)[0]
    assert token in q.unhandled
    assert token not in q.ignored
    assert q.clarification and not q.fully_resolved
    assert q.modifier_telemetry["silent_modifier_drop_rate"] == 0
    class NeverCompile:
        def compile(self, *args, **kwargs):
            pytest.fail("unknown modifier must ask before any compiler or LLM runs")
    answer = CompilerRouter(NeverCompile(), NeverCompile(), primary="existing").compile(q, resolver.store)
    assert answer.compiler == "clarification" and answer.sql == "" and answer.refusal is None


def test_full_certified_phrase_resolves_filter_and_records_it(resolver):
    resolver.store.upsert_concept("t", "d", "sipariş veren", SemanticType.DIMENSION_VALUE,
        status=ConceptStatus.CERTIFIED,
        mapping=Mapping(concept_id="", entity="orders", table_pattern="orders", column="direction", operator="IN", values=["outbound"]))
    q = resolver.resolve("sipariş veren tedarikçiler")
    assert not q.clarification
    assert q.filters[0].mapping.values == ["outbound"]
    assert q.modifiers[0]["decision"] == "SEMANTIC"
    assert q.modifier_telemetry["modifier_catalog_confirmed"] == 1


def pairs(approved=True, sql="SELECT SUM(discount) FROM orders GROUP BY customer", datasource="d"):
    return [ValidatedPair("original", "iskonto veren müşteriler", sql, datasource_id=datasource, human_verified=approved),
            ValidatedPair("control", "iskonto müşteriler", "SELECT SUM(discount) FROM orders GROUP BY customer", datasource_id=datasource, human_verified=approved)]


def test_independent_human_approvals_are_auditable_equivalence_evidence(resolver):
    resolver.modifier_history = ModifierHistory(pairs(), "d")
    q = resolver.resolve("iskonto veren müşteriler")
    assert not q.clarification
    assert q.modifiers[0]["decision"] == "GRAMMATICAL"
    assert q.modifiers[0]["pair_ids"] == ["control", "original"]
    assert "veren" not in q.ignored
    assert q.modifier_telemetry["modifier_historical_confirmed"] == 1
    assert resolver.resolve("sipariş veren tedarikçiler").clarification


@pytest.mark.parametrize("history", [pairs(False), pairs()[:1], pairs(datasource="other"),
    pairs(sql="SELECT SUM(discount) FROM orders WHERE status = 'pending' GROUP BY customer"),
    pairs() + [ValidatedPair("conflict", "iskonto veren müşteriler", "SELECT 1", human_verified=True)]])
def test_history_does_not_infer_equivalence_from_execution_or_missing_predicates(resolver, history):
    resolver.modifier_history = ModifierHistory(history, "d")
    assert resolver.resolve("iskonto veren müşteriler").clarification


def test_catalog_nouns_with_ambiguous_suffix_are_not_modifiers(resolver):
    resolver.store.upsert_concept("t", "d", "toptan", SemanticType.DIMENSION_VALUE,
        status=ConceptStatus.CERTIFIED, mapping=Mapping(concept_id="", entity="orders", table_pattern="orders", column="kind", operator="IN", values=["2"]))
    q = resolver.resolve("toptan iskonto müşteriler")
    assert not q.modifiers and not q.clarification


def test_bridge_returns_question_and_logs_modifier_without_calling_llm(resolver):
    from types import SimpleNamespace
    from semantic_bridge.app import Runtime

    runtime = Runtime.__new__(Runtime)
    runtime.settings = SimpleNamespace(tenant_id="t", datasource_id="d")
    runtime.threads = {}
    runtime.thread_plans = {}
    runtime.ensure_fresh = lambda: None
    runtime.language_pool = SimpleNamespace(search=lambda question: [], content_hash="")
    runtime.profiles = []
    runtime.resolver = resolver
    runtime.store = resolver.store
    runtime.router = CompilerRouter(None, None)
    runtime.llm = None
    out = runtime.ask("iskonto veren müşteriler", thread_id=None, sample_size=5)
    assert out["type"] == "CLARIFICATION" and out["needs_clarification"]
    assert out["queryId"]
    assert out["semantic"]["query"]["modifierTelemetry"]["modifier_unknown"] == 1
    assert len(runtime.threads[out["threadId"]]) == 2
