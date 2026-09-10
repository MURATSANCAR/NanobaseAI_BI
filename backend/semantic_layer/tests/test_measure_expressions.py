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


def test_clarification_does_not_improve_acceptance_score(catalog,profiles):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location("golden_eval",Path(__file__).resolve().parents[3]/"tests/text2sql/golden-eval.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sq=SemanticResolver(catalog,TENANT,DS,profiles).resolve("2026 net ciro (satış eksi iade)",today=date(2026,7,20))
    assert sq.refusal_reason is None
    assert module.answer_block_reason(sq)=="CLARIFICATION"


@pytest.mark.parametrize("declared",[False,True])
def test_return_filter_uses_only_declared_metric_binding(catalog,profiles,logo_db,declared):
    from semantic_layer.conventions import Conventions
    from semantic_layer.store import schema as S
    from semantic_layer.normalize import stem
    concept,mappings=catalog.certified_index(TENANT,DS)[stem("iade")][0]
    with catalog.engine.begin() as conn:
        conn.execute(S.sl_mapping.update().where(S.sl_mapping.c.concept_id==concept.id).values(entity="STLINE",table_pattern="LG_{n0}_{n1}_STLINE"))
    catalog._invalidate(TENANT,DS)
    conventions=Conventions.from_profiles(profiles)
    if declared:
        conventions.filter_equivalences=[{"left":{"entity":"STLINE","column":"TRCODE"},
            "right":{"entity":"INVOICE","column":"TRCODE"},"operator":"IN","values":["2","3"],
            "join":["STLINE","INVOICEREF","INVOICE","LOGICALREF"],"reason":"Fixture certified return equivalence"}]
    sq=SemanticResolver(catalog,TENANT,DS,profiles,conventions=conventions).resolve("2026 iade net ciro",today=date(2026,7,20))
    assert sq.filters[0].mapping.entity==("INVOICE" if declared else "STLINE")
    if declared:
        assert sq.filters[0].explain["binding_substitution"]["source"]=="declared_business_filter"
        compiler=DeterministicCompiler(profiles,{"n0":"411","n1":"01"},"sqlite",default_filters=default_filters_provider(catalog,TENANT,DS),conventions=conventions)
        result=compiler.compile(sq,catalog)
        assert result is not None
        assert not unmet_obligations(sq,result.sql)
        assert logo_db.execute(result.sql).fetchone()[0]==-100
