"""CRM süreç kayıtları (relational_process): sipariş, bekleyen ürün, satış hedefi, etkinlik, ziyaret yeri, kitap sınıflaması.

Sözlük CRM metadata'sından üretilip veriyle ölçüldü (2026-10-04). Sınanan: mevcut varlıkları ezmeden eklenmesi, kod listesinin
etiketiyle gösterilmesi, üst kaydın tutarının alt satırlarda çift sayılmaması ve yönlendirme kuralının modele gitmesi.
"""
from types import SimpleNamespace

import pytest

from semantic_bridge.finance_query.contracts import ContractError
from semantic_bridge.finance_query.executor import Executor
from semantic_bridge.finance_query.relational_contracts import ENTITY_REGISTRY, RELATION_REGISTRY
from semantic_bridge.finance_query.relational_executor import compile_relational_query, execute_relational_query
from semantic_bridge.finance_query.relational_plan import RELATIONAL_CAPABILITIES, validate_relational_query
from semantic_bridge.finance_query.relational_process import PROCESS_ENTITIES, PROCESS_RELATIONS

TYPES = {(e["table"].lower(), f["column"].lower()): f["sql_type"] for e in ENTITY_REGISTRY.values() for f in e["fields"].values()}


def plan(root, select, joins=(), filters=(), group_by=()):
    return {"root": root, "distinct": False, "joins": list(joins), "select": list(select), "filters": list(filters),
            "group_by": list(group_by), "order_by": [], "limit": None}


def ref(alias, field):
    return {"alias": alias, "field": field}


def test_process_records_join_the_registry_without_touching_existing_entities():
    assert {"crm_order", "crm_order_line", "pending_item", "sales_target", "crm_activity", "visit_place"} <= set(ENTITY_REGISTRY)
    assert ENTITY_REGISTRY["book"]["table"] == "new_kitapBase" and "book" not in PROCESS_ENTITIES
    for name, r in PROCESS_RELATIONS.items():
        target = ENTITY_REGISTRY[r["right_entity"]]
        assert r["right_field"] == target["primary_key"] and r["cardinality"] == "many_to_one", name
        assert r["left_field"] in ENTITY_REGISTRY[r["left_entity"]]["fields"], name


def test_a_code_list_field_is_shown_with_its_crm_label_and_grouped_by_its_code():
    p = plan("crm_order", [{"id": "tip", "op": "label", "field": ref("root", "siparis_tipi")},
                           {"id": "adet", "op": "count_records", "field": None}], group_by=[ref("root", "siparis_tipi")])
    sql, fields, numeric = compile_relational_query(p)
    assert "THEN N'B2B'" in sql and "GROUP BY [root].[new_siparistipi]" in sql
    assert fields == ["tip", "adet"] and numeric == ["adet"]
    assert RELATIONAL_CAPABILITIES["entities"]["crm_order"]["fields"]["siparis_tipi"]["codes"]


def test_label_needs_a_code_list():
    with pytest.raises(ContractError, match="kod listesi"):
        validate_relational_query(plan("crm_order", [{"id": "x", "op": "label", "field": ref("root", "siparis_tarihi")}]), "", None)


def test_a_parent_amount_is_not_summed_over_its_child_lines():
    joins = [{"relation": "crm_order_line_siparis_id_to_crm_order", "left_alias": "root", "alias": "j1", "kind": "inner"}]
    with pytest.raises(ContractError, match="kök kaydın"):
        validate_relational_query(plan("crm_order_line", [{"id": "t", "op": "sum", "field": ref("j1", "toplam_satis_tutari")}], joins), "", None)
    ok = validate_relational_query(plan("crm_order_line", [{"id": "t", "op": "sum", "field": ref("root", "toplam_tutar")}], joins), "", None)
    assert ok["select"][0]["op"] == "sum"


def test_rates_prices_and_code_lists_are_not_additive():
    order = PROCESS_ENTITIES["crm_order"]["fields"]
    assert order["toplam_satis_tutari"]["sum_allowed"] and not order["indirim_orani"]["sum_allowed"]
    target = PROCESS_ENTITIES["sales_target"]["fields"]
    assert target["toplam_hedef"]["sum_allowed"] and not target["yil"]["sum_allowed"] and not target["bolge"]["sum_allowed"]
    assert not PROCESS_ENTITIES["crm_order_line"]["fields"]["liste_birim_fiyati"]["sum_allowed"]


def test_personal_fields_never_enter_the_registry():
    visit = PROCESS_ENTITIES["visit_place"]["fields"]
    assert not any("telefon" in f or "adres" in f for f in visit)


class Crm:
    def __init__(self, declared):
        self.sql, self.declared = [], declared

    def execute(self, sql, limit):
        self.sql.append(sql)
        if "sys.tables" in sql:
            return ["name"], [], False                    # pasif kuralı uygulanacak tablo yok
        if "EntityView" in sql or "StringMapBase" in sql:
            return ["x"], [], False
        if "is_primary_key" in sql:
            return ["n"], [{"n": 1 if self.declared else 0}], False
        return [], [], False


@pytest.mark.parametrize("declared", [True, False])
def test_a_declared_primary_key_skips_the_full_uniqueness_scan(declared, monkeypatch):
    crm = Crm(declared)
    ex = Executor(SimpleNamespace(crm_connector=crm, connector=None, _check_data_scope=lambda sql: None))
    ex.verify_schema = lambda tables, source: {(t.lower(), c.lower()): TYPES.get((t.lower(), c.lower()), "nvarchar")
                                               for t, cols in tables.items() for c in cols}
    execute_relational_query(ex, plan("crm_order_line", [{"id": "n", "op": "count_records", "field": None}]))
    scans = [s for s in crm.sql if "HAVING COUNT_BIG(*)>1" in s]
    assert (not scans) if declared else scans


def test_the_planner_is_told_which_source_owns_process_and_which_owns_money():
    import inspect
    from semantic_bridge.finance_query import planner
    text = inspect.getsource(planner)
    assert "CRM süreçtir" in text and "CRM sipariş tutarı sipariş anındaki tutardır, ciro veya satış değildir" in text
