import itertools,json,collections
from pathlib import Path
from datetime import date
from semantic_layer.tests.conftest import build_erp_sqlite,DS,TENANT
from semantic_layer.tests.test_runtime import catalog as fixture
from semantic_layer.profiler.connectors import SQLiteConnector
from semantic_layer.profiler.profiler import Profiler
from semantic_layer.store.catalog_store import open_store
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.compiler import DeterministicCompiler,CompilerRouter,default_filters_provider
c=build_erp_sqlite();profiles=Profiler(SQLiteConnector(conn=c),enum_max_distinct=16).profile(DS,"main","LG_411_%")
s=open_store("sqlite://");fixture.__wrapped__(s,profiles)
r=SemanticResolver(s,TENANT,DS,profiles)
router=CompilerRouter(DeterministicCompiler(profiles,{"n0":"411","n1":"01"},"sqlite",default_filters=default_filters_provider(s,TENANT,DS)),None)
counts=collections.Counter();failures=[];unique=set()
for period,qualifier,subject,suffix in itertools.product(["2026","2025","bu yıl","geçen yıl"],["en pahalı","en ucuz","en kârlı","avantajlı","iskonto verdiğimiz","iskonto aldığımız"],["ürünler","müşteriler","kitaplar"],[""," hangileri?"," listesini göster"," nelerdir?"," ilk 10"," ilk 20"]):
 q=f"{period} {qualifier} {subject}{suffix}";unique.add(q)
 sq=r.resolve(q,today=date(2026,9,9));a=router.compile(sq,s)
 status="unsafe_answer" if a.sql else a.compiler
 counts[status]+=1
 if a.sql:failures.append({"q":q,"sql":a.sql})
Path("artifacts/stress/ambiguous-summary.json").write_text(json.dumps({"scope":"deterministic resolver/router only; no LLM", "total":sum(counts.values()),"unique_questions":len(unique),"counts":dict(counts),"failures":failures},ensure_ascii=False,indent=2))
print(dict(counts))
