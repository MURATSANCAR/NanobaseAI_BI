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
