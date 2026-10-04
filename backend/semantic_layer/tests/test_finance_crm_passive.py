"""Finans motoru: pasif CRM kaydı hiçbir okumada gelmez (kullanıcı kuralı 2026-09-29, 01.10 incelemesi).

Sahte CRM bağlantısıyla motorun ürettiği her CRM SELECT'i toplanır; her `statecode`lu tablo başvurusunda
(LEFT JOIN hedefi dahil) `statecode = 0` ve pasif durum nedeni olan tabloda `statuscode` koşulu aranır.
Motorun okuma kapısı eksik koşulu SOURCE_CONTRACT_VIOLATION ile durdurur; testler hem kapıyı hem üreticileri sınar.
"""
from __future__ import annotations

from types import SimpleNamespace
import re

import pytest

from semantic_layer.runtime import crm_active as ca
from semantic_bridge.finance_query.contracts import ContractError
from semantic_bridge.finance_query.executor import Executor
from semantic_bridge.finance_query.crm_reports import REPORTS, execute_crm_report
from semantic_bridge.finance_query.crm_query import execute_crm_plan
from semantic_bridge.finance_query.relational_contracts import ENTITY_REGISTRY
from semantic_bridge.finance_query.relational_executor import execute_relational_query

ELIGIBLE = ["new_kitapBase", "new_markaBase", "ContactBase", "AccountBase", "new_yaynevialtmarkaBase", "new_katilimcitipiBase",
            "new_eserkatilimBase", "new_kitapgecmisiBase", "new_sozlesmeBase", "new_dilBase", "new_blgeBase", "new_ulkeBase",
            "new_sozlesmetarafiBase", "new_sozlesmetaraftipiBase", "new_isplaniBase", "new_projeBase", "new_projeasamalariBase",
            "new_adresBase", "new_illerBase", "new_firmablgesiBase"]
PASSIVE = [("account", 100000001), ("contact", 100000000), ("new_kitap", 100000000), ("new_sozlesme", 100000004)]
YAZAR = "11111111-1111-1111-1111-111111111111"
TYPES = {(e["table"].lower(), f["column"].lower()): f["sql_type"] for e in ENTITY_REGISTRY.values() for f in e["fields"].values()}


class FakeCrm:
    def __init__(self):
        self.sql = []

    def execute(self, sql, limit):
        self.sql.append(sql)
        if "sys.objects" in sql:
            return ["name"], [{"name": t} for t in ELIGIBLE], False
        if "EntityView" in sql:
            return ["ent", "code"], [{"ent": e, "code": c} for e, c in PASSIVE], False
        if "StringMapBase" in sql:
            return ["code", "label"], [{"code": 1, "label": "Aktif"}, {"code": 2, "label": "Etkin"},
                                       {"code": 100000000, "label": "Aktif Müşteri"}], False
        if "new_katilimcitipiBase] r" in sql:
            return ["id", "name"], [{"id": YAZAR, "name": "Yazar"}], False
        return [], [], False


def executor():
    crm = FakeCrm()
    rt = SimpleNamespace(crm_connector=crm, connector=None, _check_data_scope=lambda sql: None)
    ex = Executor(rt)
    ex.verify_schema = lambda tables, source: {(t.lower(), c.lower()): TYPES.get((t.lower(), c.lower()), "nvarchar")
                                               for t, cols in tables.items() for c in cols}
    return ex, crm


def business_sql(crm):
    return [s for s in crm.sql if "sys.objects" not in s and "StringMapBase" not in s]


def assert_guarded(sqls):
    eligible = {t.lower() for t in ELIGIBLE}
    passive = {e + "base": (c,) for e, c in PASSIVE}
    seen = set()
    for sql in sqls:
        assert ca.missing(sql, eligible, passive) == [], sql
        seen |= {m.lower() for m in re.findall(r"\[?(\w+Base)\]?\s+(?:AS\s+)?\[?\w+\]?", sql)}
    return seen


# ---------------------------------------------------------------- kapının kendisi

E = frozenset({"new_sozlesmebase", "accountbase", "new_projebase"})
P = {"new_sozlesmebase": (100000004,), "accountbase": (100000001,)}


def test_guard_accepts_shared_predicate_in_where_on_and_exists():
    s = ca.predicate("new_sozlesmeBase", "s", P)
    a = ca.predicate("AccountBase", "[j1]", P)
    sql = (f"SELECT s.new_name FROM [Timas_MSCRM].[dbo].[new_sozlesmeBase] s LEFT JOIN [Timas_MSCRM].[dbo].[AccountBase] AS [j1]"
           f" ON [j1].AccountId=s.x AND ({a}) WHERE {s} AND EXISTS (SELECT 1 FROM [Timas_MSCRM].[dbo].new_projeBase p"
           f" WHERE p.new_projeId=s.y AND {ca.predicate('new_projeBase', 'p', P)})")
    assert ca.missing(sql, E, P) == []


def test_guard_rejects_statecode_only_on_table_with_passive_reasons():
    sql = "SELECT s.new_name FROM [Timas_MSCRM].[dbo].[new_sozlesmeBase] s WHERE s.statecode=0"
    assert ca.missing(sql, E, P) == ["new_sozlesmeBase s"]


def test_guard_rejects_left_target_filtered_only_in_where_or_inside_or():
    a = ca.predicate("AccountBase", "a", P)
    s = ca.predicate("new_sozlesmeBase", "s", P)
    in_where = f"SELECT 1 FROM new_sozlesmeBase s LEFT JOIN AccountBase a ON a.AccountId=s.x WHERE {s} AND {a}"
    assert ca.missing(in_where, E, P) == ["AccountBase a"]
    in_or = f"SELECT 1 FROM new_sozlesmeBase s WHERE ({s}) OR s.x=1"
    assert ca.missing(in_or, E, P) == ["new_sozlesmeBase s"]
    unfiltered = "SELECT 1 FROM new_projeBase j"
    assert ca.missing(unfiltered, E, P) == ["new_projeBase j"]


def test_guard_ignores_tables_without_statecode_and_wrapper_text_is_unchanged():
    assert ca.missing("SELECT 1 FROM TerritoryBase t JOIN new_new_sozlesme_new_kitapBase l ON 1=1", E, P) == []
    # crm_active sarmalı aynı kuralı alt sorguya yazar (eski davranış korunur)
    assert "WHERE statecode = 0 AND (statuscode IS NULL OR statuscode NOT IN (100000004))) s" in \
        ca.rewrite("SELECT s.x FROM new_sozlesmeBase s", E, P)


def test_executor_read_fails_closed_without_predicate():
    ex, crm = executor()
    with pytest.raises(ContractError) as err:
        ex.read("SELECT r.new_name FROM [Timas_MSCRM].[dbo].[new_sozlesmeBase] r WHERE r.statecode=0", source="crm")
    assert err.value.code == "SOURCE_CONTRACT_VIOLATION"
    assert not business_sql(crm)


# ---------------------------------------------------------------- motorun bütün CRM okumaları

@pytest.mark.parametrize("report", sorted(REPORTS))
def test_every_crm_report_read_applies_passive_rule(report):
    ex, crm = executor()
    dated = report in {"catalog_additions", "contract_expiry", "open_author_actions", "appointments_with_actions",
                       "book_change_history", "work_due", "work_due_missing"}
    execute_crm_report(ex, {"kind": "crm_report", "report": report, "start": "2026-01-01" if dated else None,
                            "end": "2026-10-01" if dated else None, "as_of": "2026-10-01", "limit": None})
    sqls = business_sql(crm)
    assert sqls
    assert_guarded(sqls)
    assert not any("new_new_proje_new_kitap" in s or "new_new_hak_new_sozlesme" in s for s in sqls)


def test_contract_reports_read_previously_unfiltered_tables_with_rule():
    ex, crm = executor()
    out = execute_crm_report(ex, {"kind": "crm_report", "report": "contract_author_roles", "start": None, "end": None,
                                  "as_of": "2026-10-01", "limit": None})
    sqls = business_sql(crm)
    contract = next(s for s in sqls if "[new_sozlesmeBase] r" in s and "new_SozlesmeTipi" in s)
    assert "r.statuscode NOT IN (100000004)" in contract and "new_EKitap" in contract
    party_account = next(s for s in sqls if "[AccountBase] r" in s and "AS [account_name]" in s)
    assert "r.statuscode NOT IN (100000001)" in party_account
    # Bölge kapsamı kaynakta hiç girilmemişse kolon sessizce boş kalmaz.
    assert any("Bölge kapsamı" in g["reason"] for g in out["gaps"])


def test_customer_city_reads_adres_entity_with_rule():
    ex, crm = executor()
    execute_crm_report(ex, {"kind": "crm_report", "report": "customer_geography", "start": None, "end": None,
                            "as_of": "2026-10-01", "limit": None})
    sqls = business_sql(crm)
    adres = next(s for s in sqls if "[new_adresBase] r" in s)
    assert "r.statecode = 0" in adres and "c.statuscode IN" in adres
    assert any("[new_illerBase] r" in s for s in sqls)


def test_work_reports_use_card_lookups_not_nn():
    ex, crm = executor()
    execute_crm_report(ex, {"kind": "crm_report", "report": "work_due", "start": "2026-09-30", "end": "2026-10-30",
                            "as_of": "2026-10-01", "limit": None})
    sqls = business_sql(crm)
    assert any("new_stakkarti" in s and "[new_projeBase] r" in s for s in sqls)
    plans = next(s for s in sqls if "[new_isplaniBase] r" in s)
    assert plans.count("r.statecode = 0") == 1


def test_author_group_enrichment_reads_participation_with_rule():
    ex, crm = executor()
    ex.crm_dimension_books(SimpleNamespace(dimensions=("author_group",), filters=()))
    sqls = business_sql(crm)
    broken = next(s for s in sqls if "L.new_Kitap AS book_id" in s)
    assert "R.statecode = 0" in broken and "L.statecode = 0" in broken
    assert_guarded(sqls)


@pytest.mark.parametrize("entity,fields", [("book", ["book_name", "publisher"]), ("author", ["person_name"]),
                                           ("customer", ["customer_name"])])
def test_crm_query_plans_apply_rule(entity, fields):
    ex, crm = executor()
    execute_crm_plan(ex, {"kind": "crm", "entity": entity, "mode": "list", "fields": fields + (["publisher_id"] if "publisher" in fields else []),
                          "group_by": [], "filters": [], "having_min_count": None, "order_by": None, "descending": False, "limit": None})
    assert_guarded(business_sql(crm))


def _relational(root, joins, select):
    return {"root": root, "distinct": False, "joins": joins, "select": select, "filters": [], "group_by": [], "order_by": [], "limit": None}


def test_relational_left_targets_get_rule_in_on():
    ex, crm = executor()
    plan = _relational("contract_party", [
        {"relation": "contract_party_account_id_to_account", "left_alias": "root", "alias": "j1", "kind": "left"},
        {"relation": "contract_party_contract_id_to_contract", "left_alias": "root", "alias": "j2", "kind": "left"}],
        [{"id": "party", "op": "field", "field": {"alias": "root", "field": "party_id"}},
         {"id": "account", "op": "field", "field": {"alias": "j1", "field": "name"}},
         {"id": "contract", "op": "field", "field": {"alias": "j2", "field": "contract_number"}}])
    execute_relational_query(ex, plan)
    sqls = business_sql(crm)
    assert_guarded(sqls)
    main = sqls[-1]
    on_account = main.split("AS [j1] ON ")[1].split(" LEFT JOIN ")[0]
    # Registry said '1=1' for account; the shared rule still removes passive organizations.
    assert "[j1].statecode = 0" in on_account and "[j1].statuscode NOT IN (100000001)" in on_account
    assert "[j2].statuscode NOT IN (100000004)" in main


def test_relational_project_book_uses_stock_card_relation():
    ex, crm = executor()
    plan = _relational("project", [{"relation": "project_stock_card_id_to_book", "left_alias": "root", "alias": "j1", "kind": "inner"}],
                       [{"id": "project", "op": "field", "field": {"alias": "root", "field": "project_name"}},
                        {"id": "book", "op": "field", "field": {"alias": "j1", "field": "book_name"}}])
    execute_relational_query(ex, plan)
    main = business_sql(crm)[-1]
    assert "[root].[new_stakkarti]=[j1].[new_kitapId]" in main
    assert "project_book" not in ENTITY_REGISTRY


# ---------------------------------------------------------------- açık pasif isteği: yalnız sayı (karar 2026-10-01)

from semantic_bridge.finance_query import planner as PL


class NoModel:
    def complete(self, *a, **kw):
        raise AssertionError("pasif sayımı için model planı çağrılmaz")


@pytest.mark.parametrize("question,kind", [
    ("pasif müşteriler kaç tane", "customer"),
    ("pasife alınmış carileri listele", "customer"),
    ("inaktif yazar sayısı", "author"),
    ("pasif sözleşmeler", "contract"),
    ("kaç pasif kitap var", "book"),
])
def test_explicit_passive_request_becomes_a_count_plan_without_a_model_call(question, kind):
    plan = PL.build(question, NoModel())
    assert plan.passive_count == kind and plan.metrics == () and plan.dimensions == ()


def test_passive_request_without_a_record_kind_asks_which_one():
    with pytest.raises(ContractError) as e:
        PL.build("pasif kayıtları göster", NoModel())
    assert e.value.code == "NEEDS_CLARIFICATION" and "listelenmez" in str(e.value)


def test_passive_exclusions_are_not_passive_requests():
    assert not PL.requests_passive_records("pasif olmayan müşteri sayısı")
    assert not PL.requests_passive_records("pasif müşterileri hariç tut, aktif müşteri sayısı")


def test_passive_count_reads_only_one_number_with_the_inverse_rule():
    ex, crm = executor()
    rows = ex.passive_count("author")
    assert rows and set(rows[0]) == {"passive_records"} and ex.output_fields == ["passive_records"]
    sql = business_sql(crm)[-1]
    assert sql.startswith("SELECT COUNT_BIG(*) AS [passive_records]") and "[ContactBase] r WHERE NOT (" in sql
    assert "r.statecode = 0" in sql and "r.new_yazarmi=1" in sql
    assert "listelenmez" in ex.notes[-1]


def test_passive_exemption_refuses_anything_but_a_single_count():
    ex, crm = executor()
    with pytest.raises(ContractError) as e:
        ex.read("SELECT r.name FROM [Timas_MSCRM].[dbo].[AccountBase] r WHERE r.statecode = 1", source="crm", passive_count=True)
    assert e.value.code == "SOURCE_CONTRACT_VIOLATION"
    with pytest.raises(ContractError):
        ex.read("SELECT COUNT(*) n, MAX(r.name) m FROM [Timas_MSCRM].[dbo].[AccountBase] r", source="crm", passive_count=True)
    with pytest.raises(ContractError):
        ex.read("SELECT COUNT(*) n FROM [Timas_MSCRM].[dbo].[AccountBase] r JOIN [Timas_MSCRM].[dbo].[ContactBase] c ON 1=1",
                source="crm", passive_count=True)
    assert business_sql(crm) == [], "reddedilen sorgu kaynağa gitmez"
