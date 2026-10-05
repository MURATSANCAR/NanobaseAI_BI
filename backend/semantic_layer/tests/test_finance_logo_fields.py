"""Logo kart alanı kırılımları (configs/finance/logo-fields.json, gerçek veriden seçildi 2026-10-05).

Önce: «vilayet bazında satışları getir» → «henüz doğrulanmış bir hesap tanımı yok»; il, ilçe, temsilci, ödeme planı,
taşıyıcı gibi Logo'da hazır alanlar sözleşmede olmadığı için reddediliyordu.
"""
import json

import pytest

from semantic_bridge.finance_query.contracts import DIMENSIONS, FIELD_DIMENSIONS, ContractError
from semantic_bridge.finance_query.logo_fields import FIELDS
from semantic_bridge.finance_query.model_schema import PLAN_SCHEMA


class _ReviewSpy:
    def complete(self, messages, **kw):
        assert kw["body"]["response_format"]["json_schema"]["name"] == "finance_review"
        return {"message": {"content": '{"ok": true, "missing": []}'}, "finish_reason": "stop"}


def _enums(node):
    if isinstance(node, dict):
        if isinstance(node.get("enum"), list):
            yield node["enum"]
        for v in node.values():
            yield from _enums(v)
    elif isinstance(node, list):
        for v in node:
            yield from _enums(v)


def _plan(**extra):
    data = {"metrics": ["sales_amount"], "dimensions": [], "sale_kind": "all", "filters": [], "limit": None,
            "order_by": None, "descending": True, "derived": [], "having": [], "comparison": None, "crm": None,
            "logo_report": None, "crm_report": None, "relational_query": None, "analytics": [], "sections": [],
            "gaps": [], "coverage": [], "uncovered": [], "clarification": ""}
    data.update(extra)
    return data


def test_fields_are_contract_dimensions_and_model_choices():
    assert {"client_city", "client_town", "payplan_name", "salesman_name", "ship_city"} <= set(FIELDS)
    assert set(FIELD_DIMENSIONS) <= set(DIMENSIONS)
    enums = [e for e in _enums(PLAN_SCHEMA) if "channel" in e]
    assert enums and all("client_city" in e for e in enums)          # kırılım ve süzgeç seçeneklerinin hepsinde
    # Model kolonun ne tuttuğunu örnek değerlerden görür.
    assert "İstanbul" in DIMENSIONS["client_city"]
    # Elle seçilmiş liste değil: kimlik tekrarı yok, var olan kırılımı ezmez.
    assert DIMENSIONS["channel"].startswith("Logo müşteri kartı SPECODE2")


def test_text_values_group_and_filter_without_case_or_turkish_letter_difference():
    city = FIELDS["client_city"]
    assert "COLLATE Latin1_General_CI_AI" in city.expression("c")
    assert "(girilmemiş)" in city.expression("c")
    assert city.predicate("c", "eq", "Ankara").endswith("=N'Ankara'")
    assert "LIKE N'%Kadı~_köy%'" in city.predicate("c", "contains", "Kadı_köy")
    assert "''" in city.predicate("c", "eq", "O'Neil")             # tırnak kaçışı


def test_lookup_cards_join_from_the_invoice_header():
    from semantic_bridge.finance_query import logo_fields
    fs = [FIELDS["payplan_name"], FIELDS["salesman_name"], FIELDS["ship_city"]]
    joins = "".join(logo_fields.joins(fs, "sales", "411", "01"))
    assert "LG_411_PAYPLANS] lp ON lp.LOGICALREF=h.PAYDEFREF" in joins
    assert "LG_SLSMAN] ls ON ls.LOGICALREF=h.SALESMANREF" in joins
    assert "LG_411_SHIPINFO] lx ON lx.LOGICALREF=h.SHIPINFOREF" in joins
    assert "f.PAYDEFREF" in "".join(logo_fields.joins(fs[:1], "invoice", "411", "01"))   # fatura ailesinde başlık f


def test_planner_accepts_a_city_breakdown():
    from semantic_bridge.finance_query.planner import build
    plan = build("2026 vilayet bazında satış tutarı", _ReviewSpy(), _data=_plan(dimensions=["client_city"]))
    assert plan.dimensions == ("client_city",)


def test_planner_requires_the_filter_value_in_the_question():
    from semantic_bridge.finance_query.planner import build
    plan = build("2026 Ankara satış tutarı", _ReviewSpy(),
                 _data=_plan(filters=[{"dimension": "client_city", "op": "eq", "value": "Ankara"}]))
    assert plan.filters == (("client_city", "eq", "Ankara"),)
    with pytest.raises(ContractError):
        build("2026 satış tutarı", _ReviewSpy(),
              _data=_plan(filters=[{"dimension": "client_city", "op": "eq", "value": "İzmir"}]))


@pytest.mark.parametrize("metric, dim", [("collections", "salesman_name"), ("collections", "item_specode"),
                                         ("invoice_count", "item_specode")])
def test_field_not_on_the_record_level_is_refused(metric, dim):
    from semantic_bridge.finance_query.planner import build
    with pytest.raises(ContractError):
        build("2026 tahsilat ve fatura", _ReviewSpy(), _data=_plan(metrics=[metric], dimensions=[dim]))


def test_screen_labels_have_no_table_names():
    from semantic_bridge.finance_query.result_metadata import describe_columns
    from types import SimpleNamespace
    plan = SimpleNamespace(metrics=("sales_amount",), derived=(), comparison=None, analytics=(), relational_query=None,
                           dimensions=("client_city",))
    col = next(c for c in describe_columns(plan, ["client_city", "sales_amount"], {"sales_amount"}) if c["name"] == "client_city")
    assert col["label"].startswith("Müşteri kartı")
    assert "CLCARD" not in json.dumps(col, ensure_ascii=False)
