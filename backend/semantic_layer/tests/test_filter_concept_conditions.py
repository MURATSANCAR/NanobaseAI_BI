"""A certified filter concept's extra conditions must reach the rows, not only its main column."""
from semantic_layer.models import Mapping, ResolvedSlot, SemanticQuery
from semantic_layer.runtime.audit import unmet_obligations

T = "LG_411_01_ORFLINE"


def plan():
    m = Mapping("", "LG_ORFLINE", "LG_{n0}_{n1}_ORFLINE", column="CLOSED", operator="IN", values=["0"],
                extra={"conditions": ["LG_ORFLINE.LINETYPE IN (0)", "LG_ORFLINE.AMOUNT > (LG_ORFLINE.SHIPPEDAMOUNT)"]})
    return SemanticQuery(question="bekleyen sipariş tutarı", tenant_id="t", datasource_id="d",
                         slots=[ResolvedSlot("bekleyen sipariş", "DIMENSION_VALUE", "CERTIFIED", mapping=m)])


def _filters(sql):
    return [u for u in unmet_obligations(plan(), sql) if "koşulu" in u]


def test_every_condition_written_is_accepted():
    sql = f"SELECT SUM((o.AMOUNT - o.SHIPPEDAMOUNT) * o.PRICE) FROM {T} o WHERE o.CLOSED = 0 AND o.LINETYPE = 0 AND o.AMOUNT > o.SHIPPEDAMOUNT"
    assert _filters(sql) == []


def test_a_flipped_comparison_still_proves_the_condition():
    sql = f"SELECT SUM(o.AMOUNT) FROM {T} o WHERE o.CLOSED IN (0) AND o.LINETYPE IN (0) AND o.SHIPPEDAMOUNT < o.AMOUNT"
    assert _filters(sql) == []


def test_a_missing_line_type_is_refused_by_name():
    sql = f"SELECT SUM(o.AMOUNT) FROM {T} o WHERE o.CLOSED = 0 AND o.AMOUNT > o.SHIPPEDAMOUNT"
    out = _filters(sql)
    assert len(out) == 1 and "LINETYPE IN (0)" in out[0]


def test_a_missing_remainder_test_is_refused():
    sql = f"SELECT SUM(o.AMOUNT) FROM {T} o WHERE o.CLOSED = 0 AND o.LINETYPE = 0"
    assert any("SHIPPEDAMOUNT" in t for t in _filters(sql))


def test_a_second_source_table_named_in_the_yorum_is_recognised_under_its_qualified_name():
    """The yorum says NEW_SOZLESMEBASE; the statement reads Timas_MSCRM_dbo_NEW_SOZLESMEBASE. Same table."""
    sq = SemanticQuery(question="sözleşmeler", tenant_id="t", datasource_id="d", slots=[])
    sql = ("-- yorum: 'sozlesmeler' → NEW_SOZLESMEBASE.new_name, statecode=0\n"
           "SELECT s.new_name FROM Timas_MSCRM_dbo_NEW_SOZLESMEBASE s WHERE s.statecode = 0")
    assert not [u for u in unmet_obligations(sq, sql) if "okunmuyor" in u]


def test_a_filter_on_a_second_source_table_is_proven_under_its_qualified_name():
    m = Mapping("", "NEW_SOZLESMETARAFIBASE", "new_sozlesmetarafiBase", column="new_aracivarmi", operator="IN", values=["1"])
    sq = SemanticQuery(question="aracılı sözleşmeler", tenant_id="t", datasource_id="d",
                       slots=[ResolvedSlot("aracılı sözleşme", "DIMENSION_VALUE", "CERTIFIED", mapping=m)])
    sql = 'SELECT COUNT(DISTINCT t."new_sozlesmeid") FROM Timas_MSCRM_dbo_NEW_SOZLESMETARAFIBASE t WHERE t."statecode" = 0 AND t."new_aracivarmi" IN (1)'
    assert not [u for u in unmet_obligations(sq, sql) if "koşulu" in u]


def test_a_bare_entity_qualifier_is_read_as_the_table_it_names():
    from semantic_layer.runtime.audit import repair_qualifiers_sql
    sql = "-- yorum: 'x' → y\nSELECT SUM(NEW_SEVKIYATSATIRIBASE.new_adet) FROM Timas_MSCRM_dbo_NEW_SEVKIYATSATIRIBASE WHERE NEW_SEVKIYATSATIRIBASE.statecode = 0"
    out = repair_qualifiers_sql(sql)
    assert "Timas_MSCRM_dbo_NEW_SEVKIYATSATIRIBASE.statecode" in out.replace("[", "").replace("]", "") and out.startswith("-- yorum")
    plain = "SELECT s.a FROM T s WHERE s.b = 1"
    assert repair_qualifiers_sql(plain) == plain


def test_an_absence_subquery_must_correlate_by_a_reference_key():
    from semantic_layer.runtime.audit import gate_report
    sq = SemanticQuery(question="faturası kesilmemiş siparişler", tenant_id="t", datasource_id="d", slots=[])
    sq.shape = "ABSENCE"
    sq.modifiers = [{"decision": "ABSENCE", "absent_entity": "INVOICE"}]
    sources = {"LG_411_01_STLINE": {"refs": {"ORDFICHEREF": "ORFICHE", "INVOICEREF": "INVOICE"}},
               "LG_411_01_INVOICE": {"refs": {"CLIENTREF": "CLCARD"}}, "LG_411_01_ORFICHE": {"refs": {"CLIENTREF": "CLCARD"}}}
    bad = ("SELECT COUNT(*) FROM LG_411_01_ORFICHE o WHERE o.TRCODE = 1 AND NOT EXISTS ("
           "SELECT 1 FROM LG_411_01_INVOICE i WHERE i.CLIENTREF = o.CLIENTREF AND i.DATE_ >= o.DATE_)")
    good = ("SELECT COUNT(*) FROM LG_411_01_ORFICHE o WHERE o.TRCODE = 1 AND NOT EXISTS ("
            "SELECT 1 FROM LG_411_01_STLINE s JOIN LG_411_01_INVOICE i ON i.LOGICALREF = s.INVOICEREF WHERE s.ORDFICHEREF = o.LOGICALREF)")
    assert any("anahtarla bağlı değil" in u.text for u in gate_report(sq, bad, sources=sources))
    assert not any("anahtarla bağlı değil" in u.text for u in gate_report(sq, good, sources=sources))
