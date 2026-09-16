"""Two servers, one question: the plan is checked before it runs and combined in memory."""
from __future__ import annotations

import json

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime import federated as F


def shipments():
    return SchemaProfile(
        datasource_id="d", table_name="new_sevkiyatBase", table_pattern="new_sevkiyatBase", entity="NEW_SEVKIYATBASE",
        schema_name="Timas_MSCRM.dbo", description="Sevkiyat", row_count=286_601,
        columns=[ColumnProfile(name="new_sevkiyatid"), ColumnProfile(name="new_faturanumarasi", data_type="nvarchar(100)"),
                 ColumnProfile(name="createdon", data_type="datetime")],
        relationships=[{"column": "NEW_FATURANUMARASI", "ref_entity": "INVOICE", "ref_column": "FICHENO",
                        "cross_source": True, "evidence": {"coverage": 0.73}}])


def invoices():
    return SchemaProfile(
        datasource_id="d", table_name="LG_411_01_INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", entity="INVOICE",
        schema_name="dbo", description="Fatura", row_count=81_760, context={"n0": "411", "n1": "01"},
        columns=[ColumnProfile(name="LOGICALREF"), ColumnProfile(name="FICHENO", data_type="varchar(32)"),
                 ColumnProfile(name="NETTOTAL", data_type="float")])


PROFILES = [shipments(), invoices()]

PLAN = {
    "readings": ["'kesilmemiş' → Logo'da aynı numaralı fatura yok"],
    "parts": [
        {"name": "sevk", "source": "TIMAS_MSCRM",
         "sql": "SELECT LTRIM(RTRIM(CAST(new_faturanumarasi AS NVARCHAR(100)))) AS fatura_no FROM Timas_MSCRM_dbo_new_sevkiyatBase"},
        {"name": "fatura", "source": "LOGO",
         "sql": "SELECT LTRIM(RTRIM(CAST(FICHENO AS NVARCHAR(100)))) AS fatura_no FROM INVOICE"},
    ],
    "links": [{"left": "sevk.fatura_no", "right": "fatura.fatura_no", "via": "NEW_SEVKIYATBASE.NEW_FATURANUMARASI=INVOICE.FICHENO"}],
    "final": "SELECT COUNT(*) AS adet FROM sevk s LEFT JOIN fatura f ON f.fatura_no = s.fatura_no WHERE f.fatura_no IS NULL",
}


def block(plan):
    return "Plan:\n```json\n" + json.dumps(plan, ensure_ascii=False) + "\n```"


def test_a_plan_is_read_from_the_models_answer():
    plan = F.parse_plan(block(PLAN))
    assert plan and [p.name for p in plan.parts] == ["sevk", "fatura"]
    assert plan.parts[1].source == "", "LOGO is the connection's own database"
    assert plan.readings == ["'kesilmemiş' → Logo'da aynı numaralı fatura yok"]
    assert F.parse_plan("```sql\nSELECT 1\n```") is None


def test_a_sound_plan_passes():
    assert F.check_plan(F.parse_plan(block(PLAN)), PROFILES, {}) == []


def test_a_part_that_reads_the_other_server_is_refused():
    bad = json.loads(json.dumps(PLAN))
    bad["parts"][1]["sql"] = "SELECT new_faturanumarasi AS fatura_no FROM Timas_MSCRM_dbo_new_sevkiyatBase"
    problems = F.check_plan(F.parse_plan(block(bad)), PROFILES, {})
    assert any("yalnız kendi kaynağının" in p for p in problems), problems


def test_a_join_the_catalog_never_measured_is_refused():
    bad = json.loads(json.dumps(PLAN))
    bad["links"][0]["via"] = "NEW_SEVKIYATBASE.NEW_SEVKIYATID=INVOICE.LOGICALREF"
    problems = F.check_plan(F.parse_plan(block(bad)), PROFILES, {})
    assert any("ölçülmüş" in p for p in problems), problems


def test_a_declared_link_the_final_query_does_not_use_is_refused():
    bad = json.loads(json.dumps(PLAN))
    bad["final"] = "SELECT COUNT(*) AS adet FROM sevk, fatura"
    problems = F.check_plan(F.parse_plan(block(bad)), PROFILES, {})
    assert any("eşitlik olarak kullanılmıyor" in p for p in problems), problems


def test_the_final_query_reads_only_the_parts():
    bad = json.loads(json.dumps(PLAN))
    bad["final"] = "SELECT COUNT(*) FROM sevk s JOIN fatura f ON f.fatura_no = s.fatura_no JOIN INVOICE i ON 1=1"
    problems = F.check_plan(F.parse_plan(block(bad)), PROFILES, {})
    assert any("yalnız parçaları" in p for p in problems), problems


def test_one_server_is_not_a_plan():
    bad = json.loads(json.dumps(PLAN))
    bad["parts"][1]["source"] = "TIMAS_MSCRM"
    problems = F.check_plan(F.parse_plan(block(bad)), PROFILES, {})
    assert any("aynı kaynakta" in p for p in problems), problems


def test_the_plan_runs_in_memory_and_answers_an_absence():
    rows = {
        "sevk": [{"fatura_no": "A1"}, {"fatura_no": "A2"}, {"fatura_no": " A3 "}],
        "fatura": [{"fatura_no": "A1"}, {"fatura_no": "A3"}],
    }

    def fetch(part):
        yield [{"name": "fatura_no"}], []
        yield [{"name": "fatura_no"}], rows[part.name]

    cols, out = F.execute(F.parse_plan(block(PLAN)), fetch)
    assert [c["name"] for c in cols] == ["adet"]
    assert out == [{"adet": 1}], "only A2 has no invoice; surrounding spaces are not a difference"


def test_the_prompt_lists_only_measured_links():
    assert "NEW_SEVKIYATBASE.NEW_FATURANUMARASI=INVOICE.FICHENO" in F.links_block(PROFILES)
    assert "(yok)" in F.links_block([invoices()])


def test_the_bridge_runs_each_part_on_its_own_server_and_answers():
    """End to end through the bridge: parts go to the connection their tables live on."""
    import threading
    from types import SimpleNamespace
    from semantic_bridge.app import Runtime
    from semantic_bridge.result_files import ResultFiles
    from semantic_layer.models import CompiledQuery, SemanticQuery

    seen = {"crm": [], "logo": []}

    class Conn:
        def __init__(self, side, rows):
            self.side, self.rows = side, rows

        def batches(self, sql):
            seen[self.side].append(sql)
            yield [{"name": "fatura_no"}], []
            yield [{"name": "fatura_no"}], self.rows

    rt = Runtime.__new__(Runtime)
    rt.settings = SimpleNamespace(tenant_id="t", datasource_id="d", max_rows=1000)
    rt.connector = Conn("logo", [{"fatura_no": "A1"}])
    rt.crm_connector = Conn("crm", [{"fatura_no": "A1"}, {"fatura_no": "A2"}])
    rt._engine_lock = threading.RLock()
    rt._physical = lambda sql, period, **kw: sql
    rt.result_files = ResultFiles()
    rt.attach_widget = lambda result, question: None
    rt.remember_result = lambda *a, **k: None
    rt.summarize = lambda *a, **k: "1 sevkiyatın faturası yok"
    rt.thread_plans = {}
    logged = []
    rt.store = SimpleNamespace(log_query=lambda *a, **k: logged.append(k) or "q1")

    plan = F.parse_plan(block(PLAN))
    sq = SemanticQuery(question="faturası kesilmemiş sevkiyat sayısı", tenant_id="t", datasource_id="d")
    compiled = CompiledQuery(sql=plan.text(), compiler="existing_llm", plan=plan)
    out = rt._answer_plan(sq.question, sq, compiled, {}, [], "th", {}, 0.0, 50, {}, lambda stage: None, True)
    assert out["type"] == "TEXT_TO_SQL" and out["federated"], out
    assert out["records"] == [{"adet": 1}]
    assert len(seen["crm"]) == 1 and "sevkiyat" in seen["crm"][0].lower()
    assert len(seen["logo"]) == 1 and "INVOICE" in seen["logo"][0]
    assert logged and logged[-1]["executed"] is True


def test_a_rescan_keeps_the_links_to_the_other_database(tmp_path):
    from semantic_layer.store.catalog_store import open_store

    store = open_store(f"sqlite:///{tmp_path}/c.db")
    prof = shipments()
    store.upsert_profile(prof)
    rescanned = shipments()
    rescanned.relationships = [{"column": "OWNERID", "ref_entity": "SYSTEMUSERBASE", "ref_column": "SYSTEMUSERID"}]
    store.upsert_profile(rescanned)
    back = next(p for p in store.list_profiles("d") if p.table_name == "new_sevkiyatBase")
    kinds = {(r["ref_entity"], bool(r.get("cross_source"))) for r in back.relationships}
    assert ("INVOICE", True) in kinds and ("SYSTEMUSERBASE", False) in kinds, back.relationships
