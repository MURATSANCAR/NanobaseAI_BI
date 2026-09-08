"""Independent row arithmetic; schema names, transaction codes and years vary."""
from datetime import date
import sqlite3
import pytest
from semantic_layer.models import SchemaProfile,ColumnProfile,Mapping,ResolvedSlot,SemanticQuery,TemporalSlot
from semantic_layer.runtime.compiler import DeterministicCompiler
from semantic_layer.conventions import Conventions

@pytest.mark.parametrize("entity,sale,refund,year",[("EVENTS",7,2,2022),("LEDGER",41,89,2031)])
@pytest.mark.parametrize("extra",["count","average","unrestricted"])
def test_each_metric_preserves_its_own_domain(entity,sale,refund,year,extra):
    profile=SchemaProfile("test",entity,entity,entity,columns=[ColumnProfile(c,t) for c,t in
        [("ID","int"),("KIND","int"),("VALUE","decimal"),("DAY","date"),("VOIDED","int")]])
    conventions=Conventions.from_profiles([profile]);conventions.time_hint[entity]="DAY"
    db=sqlite3.connect(":memory:")
    db.execute(f"CREATE TABLE {entity}(ID integer,KIND integer,VALUE real,DAY text,VOIDED integer)")
    records=[(1,sale,100,f"{year}-01-03",0),(1,sale,50,f"{year}-01-04",0),
             (2,refund,20,f"{year}-01-05",0),(3,999,999,f"{year}-01-06",0),
             (4,sale,500,f"{year}-01-07",1),(5,sale,100,f"{year-1}-01-08",0)]
    db.executemany(f"INSERT INTO {entity} VALUES(?,?,?,?,?)",records)
    def metric(name,formula,conditions):
        return ResolvedSlot(term=name,semantic_type="METRIC",status="CERTIFIED",mapping=Mapping(
            concept_id=name,entity=entity,table_pattern=entity,formula=formula,extra={"conditions":conditions}))
    net=metric("net",f"SUM(CASE WHEN {entity}.KIND IN ({sale}) THEN {entity}.VALUE ELSE -{entity}.VALUE END)",
               [f"{entity}.KIND IN ({sale},{refund})"])
    second=metric("other", {"count":f"COUNT(DISTINCT {entity}.ID)","average":f"AVG({entity}.VALUE)",
                            "unrestricted":f"SUM({entity}.VALUE)"}[extra],
                  [] if extra=="unrestricted" else [f"{entity}.KIND IN ({sale})"])
    period=TemporalSlot("year","YEAR",date(year,1,1),date(year+1,1,1))
    q=SemanticQuery("dynamic catalog request","test","test",slots=[net,second],temporal=[period])
    compiler=DeterministicCompiler([profile],{},"sqlite",conventions=conventions,
        default_filters=lambda e:[Mapping(concept_id="",entity=e,table_pattern=e,column="VOIDED",operator="=",values=["0"])])
    result=compiler.compile(q,None)
    assert result is not None
    actual=db.execute(result.sql).fetchone()
    eligible=[r for r in records if not r[4] and r[3].startswith(str(year))]
    sales=[r for r in eligible if r[1]==sale]
    expected_net=sum(r[2] if r[1]==sale else -r[2] for r in eligible if r[1] in (sale,refund))
    expected_other={"count":len({r[0] for r in sales}),"average":sum(r[2] for r in sales)/len(sales),
                    "unrestricted":sum(r[2] for r in eligible)}[extra]
    assert actual==pytest.approx((expected_net,expected_other))
    # Every combined value must also equal its separately compiled counterpart.
    for i,m in enumerate(q.slots):
        single=SemanticQuery("single","test","test",slots=[m],temporal=[period])
        assert db.execute(compiler.compile(single,None).sql).fetchone()[0]==pytest.approx(actual[i])
    # No data is not a zero sale, and an absent comparison period stays present.
    q.temporal.append(TemporalSlot("empty","YEAR",date(year+2,1,1),date(year+3,1,1)))
    compared=db.execute(compiler.compile(q,None).sql).fetchone()
    assert compared[0]==pytest.approx(expected_net) and compared[1] is None
    assert compared[2]==pytest.approx(expected_other)
    assert compared[3]==(0 if extra=="count" else None)
    from semantic_layer.runtime.audit import unmet_obligations
    q.comparison={"current":q.temporal[0].to_dict(),"reference":q.temporal[1].to_dict(),
                  "entity":entity,"dateColumn":"DAY"}
    compared_sql=compiler.compile(q,None).sql
    assert unmet_obligations(q,compared_sql)==[]
    # Losing the per-measure scope is not accepted as a valid comparison.
    import sqlglot
    from sqlglot import exp
    tree=sqlglot.parse_one(compared_sql,read="tsql")
    for predicate in tree.find_all(exp.In):
        if predicate.this.name=="KIND" and [x.this for x in predicate.expressions]==[str(sale)]:
            predicate.set("expressions",[exp.Literal.number(refund)])
    wrong=tree.sql(dialect="tsql")
    if extra!="unrestricted":
        assert unmet_obligations(q,wrong)
    db.close()


@pytest.mark.parametrize("formula",["EVENTS.VALUE", "MEDIAN(EVENTS.VALUE)", "SUM(EVENTS.VALUE) OVER ()", "SUM(EVENTS.VALUE) + EVENTS.KIND"])
def test_unsupported_scoping_is_not_silently_accepted(formula):
    from semantic_layer.runtime.compiler import _can_scope_formula
    assert not _can_scope_formula(formula)


@pytest.mark.parametrize("today",[date(2021,9,8),date(2024,2,29),date(2033,12,31)])
@pytest.mark.parametrize("phrase",["{year} yılbaşından bugüne","{year} yıl başından bugüne kadar","yılbaşından bu yana","{year} YTD"])
def test_compound_current_period_is_one_dynamic_interval(today,phrase):
    from datetime import timedelta
    from semantic_layer.runtime.temporal import parse_temporal
    periods,_=parse_temporal(phrase.format(year=today.year)+" toplam",today)
    assert len(periods)==1
    assert periods[0].start==date(today.year,1,1)
    assert periods[0].end==today+timedelta(days=1)
    assert not periods[0].ambiguous


def test_explicit_start_year_is_preserved_and_unknown_ytd_is_not_guessed():
    from semantic_layer.runtime.temporal import parse_temporal
    periods,_=parse_temporal("2023 yılbaşından bugüne",date(2024,3,1))
    assert len(periods)==1 and periods[0].start==date(2023,1,1) and periods[0].end==date(2024,3,2)
    periods,_=parse_temporal("2023 YTD",date(2024,3,1))
    assert len(periods)==1 and periods[0].ambiguous
