from datetime import date
from unittest.mock import Mock
import pytest
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.compiler import CompilerRouter, DeterministicCompiler, default_filters_provider
from semantic_layer.runtime.audit import unmet_obligations
from semantic_layer.tests.test_runtime import catalog
from semantic_layer.tests.conftest import TENANT, DS

@pytest.mark.parametrize("question", [
    "2026 net ciro (satış satırları eksi iade satırları), satılan",
    "2026 net ciro (satış eksi iade)",
    "2026 satış tutarı eksi iade tutarı",
    "2026 iade tutarı eksi satış tutarı",
    "2026 net ciro (satış eksi iade) eksi iskonto",
])
def test_operands_are_not_row_filters(catalog,profiles,question):
    sq=SemanticResolver(catalog,TENANT,DS,profiles).resolve(question,today=date(2026,7,20))
    assert sq.measure_expressions and sq.clarification
    assert not sq.filters and not sq.conflicts
    assert sq.to_dict()["measureExpressions"][0]["operator"]=="SUBTRACT"
    deterministic, fallback = Mock(), Mock()
    result=CompilerRouter(deterministic,fallback).compile(sq,catalog)
    assert result.compiler=="clarification" and not result.sql
    deterministic.compile.assert_not_called();fallback.compile.assert_not_called()
    # The requirement also survives a caller accidentally dropping UI clarification flags.
    sq.clarification.clear();sq.unhandled.clear()
    assert any("hesap ifadesi" in x for x in unmet_obligations(sq,"SELECT SUM(INVOICE.NETTOTAL) FROM INVOICE"))

def test_external_filter_keeps_its_scope(catalog,profiles):
    sq=SemanticResolver(catalog,TENANT,DS,profiles).resolve("2026 toptan net ciro (satış eksi iade)",today=date(2026,7,20))
    assert [f.mapping.values for f in sq.filters]==[["8"]]
    assert sq.clarification

def test_reference_numbers_for_non_arithmetic_controls(catalog,profiles,logo_db):
    resolver=SemanticResolver(catalog,TENANT,DS,profiles)
    compiler=DeterministicCompiler(profiles,{"n0":"411","n1":"01"},"sqlite",default_filters=default_filters_provider(catalog,TENANT,DS))
    for question,expected in [("2026 net ciro",1560),("2026 iade net ciro",-100),("2026 toptan satış tutarı",1500)]:
        sq=resolver.resolve(question,today=date(2026,7,20))
        assert not sq.measure_expressions
        result=compiler.compile(sq,catalog)
        assert result is not None
        assert logo_db.execute(result.sql).fetchone()[0]==pytest.approx(expected)
