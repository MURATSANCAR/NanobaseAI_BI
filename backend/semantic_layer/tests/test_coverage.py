"""A source copy's period is declared by a person and contested by the data — never read off a
min/max, which forward-dated rows push years past the truth."""
from datetime import date
from pathlib import Path

import pytest

from semantic_layer import coverage as C
from semantic_layer.config import SemanticSettings
from semantic_layer.conventions import Conventions
from semantic_layer.models import Mapping, ResolvedSlot, SemanticQuery, TemporalSlot
from semantic_layer.runtime import periods
from semantic_layer.runtime.audit import sources_from, unmet_obligations
from semantic_layer.tests.conftest import DS, TENANT

SETTINGS = SemanticSettings(store_dsn="sqlite://", tenant_id=TENANT, datasource_id=DS)


def rules_file(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "coverage.yml"
    p.write_text(body, encoding="utf-8")
    return p


GOOD = """
coverage:
  - context: {n0: "411"}
    from: 2026-01-01
    to: 2027-01-01
    verified_by: ayşe
    reason: canlı firma
"""


def test_a_declaration_needs_an_owner_and_may_not_overlap(tmp_path):
    assert C.load_rules(rules_file(tmp_path, GOOD))[0]["context"] == {"n0": "411"}
    with pytest.raises(ValueError, match="verified_by"):
        C.load_rules(rules_file(tmp_path, GOOD.replace("    verified_by: ayşe\n", "")))
    twice = GOOD + """  - context: {n0: "411"}
    from: 2026-06-01
    to: 2028-01-01
    verified_by: ayşe
    reason: ikinci iddia
"""
    with pytest.raises(ValueError, match="örtüşen"):
        C.load_rules(rules_file(tmp_path, twice))
    with pytest.raises(ValueError, match="from < to"):
        C.load_rules(rules_file(tmp_path, GOOD.replace("to: 2027-01-01", "to: 2025-01-01")))


def test_the_data_contests_a_declaration_it_does_not_fit(store, profiles, logo_connector, tmp_path):
    for p in profiles:
        store.upsert_profile(p)
    rules = C.load_rules(rules_file(tmp_path, GOOD))
    conv = Conventions.from_profiles(profiles)
    out = C.refresh(store, SETTINGS, profiles, rules, logo_connector, conv, entities={"INVOICE", "STLINE"})
    by = {r["table"]: r for r in out["rows"]}
    # the fixture's invoice table carries one 2025 row: the 2026 claim is contested, not believed
    assert by["LG_411_01_INVOICE"]["status"] == C.CONTESTED and by["LG_411_01_INVOICE"]["spill"] == 1
    assert by["LG_411_01_STLINE"]["status"] == C.DECLARED and by["LG_411_01_STLINE"]["spill"] == 0
    assert C.apply(profiles, store, SETTINGS) == 1
    stl = next(p for p in profiles if p.entity == "STLINE")
    inv = next(p for p in profiles if p.entity == "INVOICE")
    assert stl.declared_window == ("2026-01-01", "2027-01-01") and inv.declared_window is None
    # the period chooser reads the declaration, not the statistic
    assert periods._window(stl) == (date(2026, 1, 1), date(2026, 12, 31))
    # the gate: a declared table answers for its period without a date filter; a contested one does not
    def plan(entity, column):
        return SemanticQuery(question="x", tenant_id=TENANT, datasource_id=DS, slots=[],
                             temporal=[TemporalSlot("2026", "YEAR", date(2026, 1, 1), date(2027, 1, 1))],
                             temporal_binding={"entity": entity, "column": column, "alternatives": []})
    src = sources_from(profiles)
    assert unmet_obligations(plan("STLINE", "DATE_"), "SELECT SUM(AMOUNT) FROM LG_411_01_STLINE", sources=src) == []
    assert unmet_obligations(plan("INVOICE", "DATE_"), "SELECT SUM(NETTOTAL) FROM LG_411_01_INVOICE", sources=src)
    # a declared 2026 table cannot answer for 2025
    q25 = plan("STLINE", "DATE_")
    q25.temporal = [TemporalSlot("2025", "YEAR", date(2025, 1, 1), date(2026, 1, 1))]
    assert unmet_obligations(q25, "SELECT SUM(AMOUNT) FROM LG_411_01_STLINE WHERE DATE_ >= '2025-01-01' AND DATE_ < '2026-01-01'", sources=src)
