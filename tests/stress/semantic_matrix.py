"""Exhaustive synthetic questions with an independent Python row oracle.

No LLM, no production load, no success claim for unseen real user language.
Run: PYTHONPATH=backend python tests/stress/semantic_matrix.py
"""
import itertools,json,time,collections,hashlib
from pathlib import Path
from datetime import date
from semantic_layer.tests.conftest import build_erp_sqlite,DS,TENANT
from semantic_layer.tests.test_runtime import catalog as catalog_fixture
from semantic_layer.profiler.connectors import SQLiteConnector
from semantic_layer.profiler.profiler import Profiler
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import Mapping,SemanticType,ConceptStatus,ColumnProfile
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.compiler import DeterministicCompiler,default_filters_provider
from semantic_layer.runtime.audit import unmet_obligations

OUT=Path("artifacts/stress");OUT.mkdir(parents=True,exist_ok=True)
c=build_erp_sqlite()
c.execute("DELETE FROM LG_411_01_STLINE");c.execute("DELETE FROM LG_411_01_INVOICE");c.execute("DELETE FROM LG_411_CLCARD")
cities=["Ankara","İstanbul","İzmir","Bursa","Konya"]
channels=["internet","magaza","dagitici","kurumsal"]
months="ocak subat mart nisan mayis haziran temmuz agustos eylul ekim kasim aralik".split()
customers={}; cid=0
for city,channel in itertools.product(cities,channels):
 cid+=1;customers[city,channel]=cid
 c.execute("INSERT INTO LG_411_CLCARD VALUES (?,?,?,?,?,?)",(cid,str(cid),"Customer "+str(cid),channel,city,1))
rows=[];iid=0
for year,month,city,channel,kind,cancel in itertools.product(range(2024,2027),range(1,13),cities,channels,[2,3,7,8,9],[0,1]):
 iid+=1;amount=(year-2023)*100003+month*1009+customers[city,channel]*31+kind*7+cancel*999999
 day=f"{year}-{month:02d}-15"
 c.execute("INSERT INTO LG_411_01_INVOICE VALUES (?,?,?,?,?,?,?,?)",(iid,kind,cancel,customers[city,channel],day,amount,amount,0))
 rows.append((year,month,city,channel,kind,cancel,amount))
c.commit()
profiles=Profiler(SQLiteConnector(conn=c),enum_max_distinct=16).profile(DS,"main","LG_411_%")
# Wide-schema distractors reproduce production month-name columns. They must
# never turn a parsed month/year into an unrelated physical-code restriction.
for profile in profiles:
 if profile.entity == "ITEMS":
  profile.columns.extend(ColumnProfile(name=m.upper(),data_type="int") for m in months)
store=open_store("sqlite://")
catalog_fixture.__wrapped__(store,profiles)
for term,entity,column in [(v,"CLCARD","CITY") for v in cities]+[(v,"CLCARD","SPECODE2") for v in channels]:
 store.upsert_concept(TENANT,DS,term,SemanticType.DIMENSION_VALUE,status=ConceptStatus.CERTIFIED,
  mapping=Mapping("",entity,"LG_{n0}_CLCARD",column=column,operator="=",values=[term]))
store.upsert_concept(TENANT,DS,"fatura sayisi",SemanticType.METRIC,status=ConceptStatus.CERTIFIED,
 mapping=Mapping("","INVOICE","LG_{n0}_{n1}_INVOICE",formula="COUNT(INVOICE.LOGICALREF)"))
r=SemanticResolver(store,TENANT,DS,profiles)
compiler=DeterministicCompiler(profiles,{"n0":"411","n1":"01"},"sqlite",default_filters=default_filters_provider(store,TENANT,DS))
# Independent row oracle: it does not read generated SQL or resolved slots.
oracle={}
for year,month,city,channel,kind_label,metric in itertools.product(range(2024,2027),range(1,13),cities,channels,["","toptan","perakende"],["net ciro","satis tutari","ciro","fatura sayisi"]):
 selected=[x for x in rows if x[:4]==(year,month,city,channel) and x[5]==0 and
           (not kind_label or x[4]=={"toptan":8,"perakende":7}[kind_label]) and
           (metric in ("net ciro","fatura sayisi") or x[4] in (7,8,9))]
 val=len(selected) if metric=="fatura sayisi" else sum((-x[6] if metric=="net ciro" and x[4] in (2,3) else x[6]) for x in selected)
 oracle[year,month,city,channel,kind_label,metric]=val
counts=collections.Counter(); examples=collections.defaultdict(list);start=time.monotonic();seen=set()
with (OUT/"matrix-failures.jsonl").open("w") as failed:
 for key,expected in oracle.items():
  year,month,city,channel,kind,metric=key
  core=f"{months[month-1]} {year} {city} {channel} {kind} {metric}"
  for question in [core,core+" nedir?",f"{city} {channel} {months[month-1]} {year} {kind} {metric}"]:
   seen.add(question)
   try:
    sq=r.resolve(question,today=date(2027,1,1));out=compiler.compile(sq,store)
    if not out:status="refused";detail={"reason":compiler.plan(sq)[1]}
    else:
     issues=unmet_obligations(sq,out.sql)
     if issues:status="guard_rejected";detail={"issues":issues}
     else:
      actual=c.execute(out.sql).fetchall()
      status="correct" if actual==[(expected,)] else "wrong_answer"
      detail={"expected":expected,"actual":actual,"sql":out.sql} if status!="correct" else {}
   except Exception as exc:status="error";detail={"error":str(exc)}
   counts[status]+=1
   if status!="correct":
    item={"q":question,"status":status,**detail};failed.write(json.dumps(item,ensure_ascii=False)+"\n")
    if len(examples[status])<10:examples[status].append(item)
   total=sum(counts.values())
   if total%1000==0:
    snapshot={"total":total,"unique_questions":len(seen),"counts":dict(counts),"seconds":round(time.monotonic()-start,1)}
    (OUT/"matrix-progress.json").write_text(json.dumps(snapshot,indent=2));print(json.dumps(snapshot),flush=True)
summary={"kind":"synthetic controlled matrix; not unseen production language", "total":sum(counts.values()),"unique_questions":len(seen),"source_rows":len(rows),"counts":dict(counts),"examples":dict(examples),"seconds":round(time.monotonic()-start,1)}
(OUT/"matrix-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!="examples"}),flush=True)
