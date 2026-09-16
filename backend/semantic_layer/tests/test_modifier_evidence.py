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


def _left_to_model(q, token):
    """The word was not certified by anything: it is handed to the model, not treated as grammar."""
    return token in [m["token"] for m in q.model_qualifiers] and not any(
        m["token"] == token and m["decision"] in ("GRAMMATICAL", "SEMANTIC") for m in q.modifiers)


@pytest.mark.parametrize("verb", ["veren", "verdiğimiz", "yaptığımız", "edilen", "aldığımız", "bekleyen"])
@pytest.mark.parametrize("frame", ["iskonto {} müşteriler", "{} siparişler", "sipariş {} tedarikçiler", "müşteriye {} siparişler"])
def test_no_morphology_or_position_can_certify_a_modifier(resolver, verb, frame):
    """An unexplained modifier is never certified and never dropped.

    Until 2026-09-16 it was put back to the person before any compiler ran. Measured on 500 real
    questions that turned away almost half of them, and the owner decided the word goes to the model
    instead — as an explicit obligation the gate checks, on an answer that is never certified.
    """
    q = resolver.resolve(frame.format(verb))
    token = tokenize(verb)[0]
    assert token in [m["token"] for m in q.model_qualifiers]
    assert token not in q.ignored and token not in q.unhandled
    assert not any(token in c for c in q.clarification)
    assert q.modifier_telemetry["silent_modifier_drop_rate"] == 0
    decisions = {m["token"]: m["decision"] for m in q.modifiers}
    assert decisions.get(token) == "MODEL"

    calls = []

    class Deterministic:
        def compile(self, *args, **kwargs):
            return None

    class Model:
        name = "existing_llm"

        def compile(self, q, catalog, thread=None, recall=None):
            calls.append(q.question)
            from semantic_layer.runtime.compiler import CompiledQuery
            return CompiledQuery(sql="", compiler="existing_llm", catalog_version=q.catalog_version,
                                 explain=["model yazmadı"], certified=False)

    answer = CompilerRouter(Deterministic(), Model(), primary="existing").compile(q, resolver.store)
    assert calls, "the model is asked, not the person"
    assert answer.certified is False


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
    assert _left_to_model(resolver.resolve("sipariş veren tedarikçiler"), "veren")


@pytest.mark.parametrize("history", [pairs(False), pairs()[:1], pairs(datasource="other"),
    pairs(sql="SELECT SUM(discount) FROM orders WHERE status = 'pending' GROUP BY customer"),
    pairs() + [ValidatedPair("conflict", "iskonto veren müşteriler", "SELECT 1", human_verified=True)]])
def test_history_does_not_infer_equivalence_from_execution_or_missing_predicates(resolver, history):
    resolver.modifier_history = ModifierHistory(history, "d")
    assert _left_to_model(resolver.resolve("iskonto veren müşteriler"), "veren")


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
    # No model configured: the word cannot be interpreted, and the answer says so instead of widening.
    assert out["type"] != "TEXT_TO_SQL" and not out.get("sql")
    assert out["queryId"]
    assert out["type"] == "NON_SQL_QUERY"
    assert [m["token"] for m in out["semantic"]["query"]["modelQualifiers"]] == ["veren"]
