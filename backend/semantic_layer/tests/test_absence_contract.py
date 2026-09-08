from datetime import date
from pathlib import Path
import pytest
from semantic_layer.conventions import Conventions
from semantic_layer.models import SemanticQuery, ResolvedSlot, Mapping, TemporalSlot
from semantic_layer.runtime.compiler import DeterministicCompiler
from semantic_layer.runtime.audit import unmet_obligations


def plan(profiles):
    c = Conventions.from_profiles(profiles)
    c.load_equivalences(Path(__file__).resolve().parents[3] / "configs/semantic/knowledge/logo/equivalences.yml")
    q = SemanticQuery(question="2026 hiç satmayan ürünler",tenant_id="t",datasource_id="logo",
        shape="ABSENCE",slots=[ResolvedSlot("ürünler","COLUMN","CERTIFIED",mapping=Mapping("p","ITEMS","LG_{n0}_ITEMS",column="NAME"))],
        modifiers=[{"decision":"ABSENCE","verb_root":"sat"}],
        temporal=[TemporalSlot("2026","YEAR",date(2026,1,1),date(2027,1,1))])
    return q, DeterministicCompiler(profiles,{"n0":"411","n1":"01"},"sqlite",conventions=c)


def test_absence_counts_occurrence_not_returns_or_purchase(logo_db,profiles):
    for i in range(12,17):
        logo_db.execute("INSERT INTO LG_411_ITEMS VALUES (?,?,?,?,?)",(i,str(i),str(i),"x",1))
    # 12 never moved, 13 purchase only, 14 cancelled sale only, 15 return only, 16 last year only.
    for i,invoice in [(13,8),(14,9),(15,7),(16,10)]:
        logo_db.execute("INSERT INTO LG_411_01_STLINE(LOGICALREF,STOCKREF,INVOICEREF,CANCELLED,LINETYPE) VALUES (?,?,?,0,0)",(i,i,invoice))
    q,c=plan(profiles);out=c.compile(q,None)
    assert out is not None
    assert unmet_obligations(q,out.sql)==[]
    assert [r[0] for r in logo_db.execute(out.sql)]==[12,13,14,15,16]
    # Product 10 was sold and returned; it must remain excluded.


@pytest.mark.parametrize("old,new",[("NOT EXISTS","EXISTS"),("'2026-01-01'","'2025-01-01'"),("STOCKREF","INVOICEREF"),("7, 8, 9","1")])
def test_changed_absence_sql_cannot_pass(profiles,old,new):
    q,c=plan(profiles);out=c.compile(q,None)
    assert out is not None
    mutated=out.sql.replace(old,new)
    assert mutated!=out.sql
    assert unmet_obligations(q,mutated)


def test_no_business_declaration_no_absence_proof(profiles):
    q,c=plan(profiles);c.conventions.absence_rules=[]
    assert c.compile(q,None) is None
    assert unmet_obligations(q,"SELECT * FROM LG_411_ITEMS")
