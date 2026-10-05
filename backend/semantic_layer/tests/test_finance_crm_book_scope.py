"""CRM kitap kümesi × Logo satışı (crm_book_scope).

Kitaplar CRM'de kayıtlı ilişki sözlüğüyle seçilir (yaş grubu, kategori, sözleşme bitişi, satış hedefi), satış Logo'dan
aynı ölçüyle hesaplanır; bağ yalnız stok kodudur. Sınanan: plan doğrulaması (stok kodu zorunlu, CRM sayısının kimliği ve
grubu), kümenin satışı daraltması, çok değerli kitabın her değerde sayılması, CRM sayısının kitap başına bir kez toplanması
ve satışsız kitabın 0 satışla korunması. Veri tabanı yok: CRM kümesi ve Logo satırları sahte.
"""
import re
from decimal import Decimal

import pytest

from semantic_bridge.finance_query import crm_book_scope
from semantic_bridge.finance_query.contracts import ContractError
from semantic_bridge.finance_query.executor import Executor
from semantic_bridge.finance_query.model_schema import PLAN_SCHEMA
from semantic_bridge.finance_query.planner import Plan, build, plan_from_dict
from semantic_bridge.finance_query.plan_types import DerivedMetric, MetricPredicate

YEAR = (("2026-01-01", "2026-10-06"),)
COLUMNS = "CANCELLED DATE_ TRCODE LOGICALREF CLIENTREF CODE DEFINITION_ SPECODE2 LINETYPE INVOICEREF STOCKREF VATMATRAH AMOUNT NAME UINFO1 UINFO2".split()


def ref(alias, field):
    return {"alias": alias, "field": field}


def age_query():
    return {"root": "book_age_link", "distinct": False,
            "joins": [{"relation": "book_age_link_book_id_to_book", "left_alias": "root", "alias": "j1", "kind": "inner"},
                      {"relation": "book_age_link_age_group_id_to_age_group", "left_alias": "root", "alias": "j2", "kind": "inner"}],
            "select": [{"id": "book_code", "op": "field", "field": ref("j1", "book_code")},
                       {"id": "yas", "op": "field", "field": ref("j2", "yas")}],
            "filters": [], "group_by": [], "order_by": [], "limit": None}


def target_query():
    return {"root": "sales_target", "distinct": False, "joins": [],
            "select": [{"id": "book_code", "op": "field", "field": ref("root", "stok_kodu")},
                       {"id": "crm_value", "op": "sum", "field": ref("root", "toplam_hedef")}],
            "filters": [], "group_by": [ref("root", "stok_kodu")], "order_by": [], "limit": None}


def test_the_set_needs_a_stock_code_column_because_logo_is_joined_only_by_code():
    q = age_query()
    q["select"][0] = {"id": "kod", "op": "field", "field": ref("j1", "book_code")}
    with pytest.raises(ContractError, match="stok kodu"):
        crm_book_scope.validate(q, "", None)
    q = age_query()
    q["select"][0] = {"id": "book_code", "op": "field", "field": ref("j1", "book_name")}
    with pytest.raises(ContractError, match="stok kodu"):
        crm_book_scope.validate(q, "", None)


def test_a_crm_number_has_a_fixed_id_and_is_grouped_by_the_stock_code_only():
    scope = crm_book_scope.validate(target_query(), "", None)
    assert scope["values"] == ["crm_value"] and scope["attributes"] == []
    q = target_query()
    q["select"][1]["id"] = "hedef"
    with pytest.raises(ContractError, match="crm_value"):
        crm_book_scope.validate(q, "", None)


def test_attribute_columns_must_be_asked_as_a_breakdown_and_numbers_only_with_book_rows():
    scope = crm_book_scope.validate(age_query(), "", None)
    assert scope["attributes"] == ["yas"]
    with pytest.raises(ContractError, match="kırılım istenmeden"):
        crm_book_scope.check_plan(scope, ("net_sales",), (), {"sales"}, None)
    crm_book_scope.check_plan(scope, ("net_sales",), ("crm_attribute",), {"sales"}, None)
    with pytest.raises(ContractError, match="satış satırı"):
        crm_book_scope.check_plan(scope, ("invoice_count",), ("crm_attribute",), {"invoice"}, None)
    targets = crm_book_scope.validate(target_query(), "", None)
    with pytest.raises(ContractError, match="yalnız kitap"):
        crm_book_scope.check_plan(targets, ("sold_quantity",), ("month",), {"sales"}, None)


def test_the_model_schema_offers_the_set_only_beside_a_sales_metric():
    variants = PLAN_SCHEMA["anyOf"]
    metric = [v for v in variants if v["properties"]["metrics"].get("minItems") == 1]
    others = [v for v in variants if v not in metric]
    assert metric and all("anyOf" in v["properties"]["crm_books"] for v in metric)
    assert all(v["properties"]["crm_books"] == {"type": "null"} for v in others)
    derived = metric[0]["properties"]["derived"]["items"]["properties"]
    assert "crm_value" in derived["left"]["enum"] and "crm_value_2" in derived["right"]["enum"]


class Review:
    def complete(self, messages, **kw):
        return {"message": {"content": '{"ok": true, "missing": []}'}, "finish_reason": "stop"}


def data(metrics, dims, crm_books, **extra):
    base = {"metrics": metrics, "dimensions": dims, "sale_kind": "all", "filters": [], "limit": None,
            "order_by": None, "descending": True, "derived": [], "having": [], "comparison": None, "crm": None,
            "logo_report": None, "crm_report": None, "relational_query": None, "crm_books": crm_books, "analytics": [],
            "sections": [], "gaps": [], "coverage": [], "uncovered": [], "clarification": ""}
    return {**base, **extra}


def test_planner_carries_the_set_and_lets_a_crm_number_be_an_operand():
    plan = build("Bu yıl yaş grubuna göre satış", Review(), _data=data(["net_sales"], ["crm_attribute"], age_query()))
    assert plan.crm_books["attributes"] == ["yas"] and plan_from_dict(plan.to_dict()).crm_books == plan.crm_books
    met = data(["sold_quantity"], ["book"], target_query(),
               derived=[{"id": "fark", "op": "difference", "left": "sold_quantity", "right": "crm_value", "scale": 1}],
               having=[{"metric": "fark", "op": "gte", "value": "0"}])
    plan = build("Bu yıl hedefini tutturan kitaplar hangileri", Review(), _data=met)
    assert plan.derived[0].right == "crm_value" and plan.having[0].metric == "fark"
    with pytest.raises(ContractError, match="CRM kitap kümesi olmadan"):
        build("Bu yıl yaş grubuna göre satış", Review(), _data=data(["net_sales"], ["crm_attribute"], None))


class Connector:
    def __init__(self, rows):
        self.rows, self.sql = rows, []

    def execute(self, sql, max_rows):
        if "L_CAPIPERIOD" in sql:
            rows = [{"FIRMNR": 411, "NR": 1, "BEGDATE": "2026-01-01", "ENDDATE": "2026-12-31"}]
        elif "INFORMATION_SCHEMA" in sql:
            tables = re.findall(r"N'([^']+)'", sql)
            rows = [{"TABLE_NAME": t, "COLUMN_NAME": c, "DATA_TYPE": "float"} for t in tables for c in COLUMNS]
        else:
            self.sql.append(sql)
            rows = [dict(r) for r in self.rows] if "STLINE" in sql and "GROUP BY" in sql else [{"discount": 0}]
        return list(rows[0]) if rows else [], rows, False


class Runtime:
    def __init__(self, rows):
        self.connector, self.crm_connector = Connector(rows), None

    def _check_data_scope(self, sql):
        return None


@pytest.fixture(autouse=True)
def firms(monkeypatch):
    monkeypatch.setenv("SEMANTIC_FIRMS", "411")
    monkeypatch.delenv("SEMANTIC_EXCLUDE_CONTEXT", raising=False)


SALES = [{"book_code": "A1", "book_name": "Masal", "net_sales": 100, "sold_quantity": 10},
         {"book_code": "B2", "book_name": "Roman", "net_sales": 50, "sold_quantity": 5},
         {"book_code": "Z9", "book_name": "Kümede yok", "net_sales": 999, "sold_quantity": 99}]


def run(plan, books):
    engine = Executor(Runtime(SALES))
    import semantic_bridge.finance_query.crm_book_scope as scope_module
    original = scope_module.run
    scope_module.run = lambda executor, scope: books
    try:
        rows = engine.execute(plan)
    finally:
        scope_module.run = original
    return engine, rows


def book(code, name=None, attributes=(), values=None):
    return {"code": code, "name": name, "attributes": set(attributes), "values": values or {}}


def test_the_set_narrows_sales_and_a_multi_valued_book_counts_in_every_value():
    scope = crm_book_scope.validate(age_query(), "", None)
    plan = Plan(("net_sales",), ("crm_attribute",), YEAR, crm_books=scope, order_by="net_sales")
    books = {"a1": book("A1", attributes={("7-9",), ("9-12",)}), "b2": book("B2", attributes={("7-9",)})}
    engine, rows = run(plan, books)
    got = {r["yas"]: r["net_sales"] for r in rows}
    assert got == {"7-9": 150.0, "9-12": 100.0}                 # Z9 kümede değil
    assert any("birden çok değere" in n for n in engine.notes)
    assert any("2 kitap bulundu; 2 tanesinin" in n for n in engine.notes)
    assert "STOCKREF" in engine.rt.connector.sql[0] or "i.CODE" in " ".join(engine.rt.connector.sql)


def test_crm_number_is_summed_once_per_book_and_an_unsold_book_stays_with_zero_sales():
    scope = crm_book_scope.validate(target_query(), "", None)
    plan = Plan(("sold_quantity",), ("book",), YEAR, crm_books=scope, order_by="sold_quantity",
                derived=(DerivedMetric("fark", "difference", "sold_quantity", "crm_value"),),
                having=(MetricPredicate("fark", "gte", "0"),))
    books = {"a1": book("A1", values={"crm_value": Decimal(8)}), "b2": book("B2", values={"crm_value": Decimal(20)}),
             "c3": book("C3", "Satışsız", values={"crm_value": Decimal(4)})}
    engine, rows = run(plan, books)
    assert [(r["book_code"], r["sold_quantity"], r["crm_value"], r["fark"]) for r in rows] == [("A1", 10.0, 8.0, 2.0)]
    total = Plan(("sold_quantity",), (), YEAR, crm_books=scope, order_by="sold_quantity")
    engine, rows = run(total, books)
    assert rows == [{"sold_quantity": 15.0, "crm_value": 32.0}]   # hedef: üç kitabın toplamı, satışsız C3 dahil
    assert "crm_value" in engine.numeric_fields and engine.output_fields == ["sold_quantity", "crm_value"]


def test_a_set_grouped_by_its_stock_code_means_the_same_distinct_set():
    q = age_query()
    q["group_by"] = [ref("j1", "book_code")]
    scope = crm_book_scope.validate(q, "", None)
    assert scope["plan"]["distinct"] is True and scope["plan"]["group_by"] == []


def test_a_target_in_units_is_not_divided_by_a_lira_amount_and_is_not_a_metric():
    tl = data(["sales_amount", "crm_value"], ["book"], target_query(),
              derived=[{"id": "oran", "op": "ratio", "left": "sales_amount", "right": "crm_value", "scale": 100}])
    with pytest.raises(ContractError, match="adet biriminde"):
        build("Bu yıl hedefin neresindeyiz", Review(), _data=tl)
    ok = data(["sold_quantity", "crm_value", "sold_quantity"], [], target_query(),
              derived=[{"id": "oran", "op": "ratio", "left": "sold_quantity", "right": "crm_value", "scale": 100}])
    plan = build("Bu yıl hedefin neresindeyiz", Review(), _data=ok)
    assert plan.metrics == ("sold_quantity",) and plan.derived[0].right == "crm_value"


def test_pending_items_reach_logo_through_the_product_code():
    q = {"root": "pending_item", "distinct": False,
         "joins": [{"relation": "pending_item_urun_id_to_crm_product", "left_alias": "root", "alias": "j1", "kind": "inner"}],
         "select": [{"id": "book_code", "op": "field", "field": ref("j1", "urun_kimligi")},
                    {"id": "crm_value", "op": "sum", "field": ref("root", "adet")}],
         "filters": [], "group_by": [ref("j1", "urun_kimligi")], "order_by": [], "limit": None}
    scope = crm_book_scope.validate(q, "", None)
    assert crm_book_scope.unit(scope, "crm_value") == "adet"


def test_an_age_range_in_the_question_admits_each_recorded_age_inside_it():
    from semantic_bridge.finance_query.relational_plan import in_numeric_range
    q = "7-9 yaş kitaplarından bu yıl ne kadar sattık"
    assert all(in_numeric_range(v, q) for v in ("7 Yaş", "8 Yaş", "9 Yaş"))
    assert not in_numeric_range("10 Yaş", q) and not in_numeric_range("8 Ay", q) and not in_numeric_range("Masal", q)


def test_a_condition_on_a_books_crm_number_selects_books_not_the_total():
    q = {"root": "participation", "distinct": False,
         "joins": [{"relation": "participation_book_id_to_book", "left_alias": "root", "alias": "j1", "kind": "inner"}],
         "select": [{"id": "book_code", "op": "field", "field": ref("j1", "book_code")},
                    {"id": "crm_value", "op": "count_records", "field": None}],
         "filters": [], "group_by": [ref("j1", "book_code")], "order_by": [], "limit": None}
    scope = crm_book_scope.validate(q, "", None)
    plan = Plan(("net_sales",), (), YEAR, crm_books=scope, order_by="net_sales",
                having=(MetricPredicate("crm_value", "gte", "2"),))
    books = {"a1": book("A1", values={"crm_value": Decimal(2)}), "b2": book("B2", values={"crm_value": Decimal(1)})}
    engine, rows = run(plan, books)
    assert rows == [{"net_sales": 100.0, "crm_value": 2.0}]      # yalnız iki yazarlı A1


def test_a_crm_number_is_always_grouped_by_the_selected_stock_code():
    q = target_query()
    q["group_by"] = []
    scope = crm_book_scope.validate(q, "", None)
    assert scope["plan"]["group_by"] == [ref("root", "stok_kodu")]
