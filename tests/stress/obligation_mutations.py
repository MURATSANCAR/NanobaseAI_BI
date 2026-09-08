"""Generated AST attacks with matched valid controls; no production queries."""
import json,collections,time
from pathlib import Path
from datetime import date
from semantic_layer.models import SemanticQuery,ResolvedSlot,Mapping,TemporalSlot
from semantic_layer.runtime.audit import unmet_obligations
out=Path("artifacts/stress");out.mkdir(exist_ok=True,parents=True)
counts=collections.Counter();failures=[];start=time.monotonic();unique=set()
for n in range(1000):
 c,i=f"c{n}",f"i{n}";value=f"city{n}"
 q=SemanticQuery(question=f"2026 {value}",tenant_id="t",datasource_id="d",slots=[ResolvedSlot(value,"DIMENSION_VALUE","CERTIFIED",mapping=Mapping("","CLCARD","LG_{n0}_CLCARD",column="CITY",operator="=",values=[value]))],temporal=[TemporalSlot("2026","YEAR",date(2026,1,1),date(2027,1,1))],temporal_binding={"entity":"INVOICE","column":"DATE_"})
 source=f"FROM LG_411_CLCARD {c} JOIN LG_411_01_INVOICE {i} ON {c}.LOGICALREF={i}.CLIENTREF"
 city=f"{c}.CITY='{value}'";dates=f"{i}.DATE_ >= '2026-01-01' AND {i}.DATE_ < '2027-01-01'"
 base=f"SELECT {c}.CODE {source} WHERE {city} AND {dates}"
 cases={"valid":base,"missing_city":f"SELECT {c}.CODE {source} WHERE {dates}",
 "or_widening":base+f" OR {c}.ACTIVE=1","wrong_city":base.replace(value,"other"),
 "unused_cte":f"WITH unused{n} AS ({base}) SELECT * FROM LG_411_CLCARD",
 "decorative_case":f"SELECT CASE WHEN {city} THEN 1 ELSE 0 END {source} WHERE {dates}",
 "missing_period":f"SELECT {c}.CODE {source} WHERE {city}",
 "wrong_period":base.replace("2026-01-01","2025-01-01"),
 "wrong_date_column":base.replace(f"{i}.DATE_",f"{i}.LOGICALREF")}
 for kind,sql in cases.items():
  unique.add(sql)
  try:
   issues=unmet_obligations(q,sql);passed=not issues if kind=="valid" else bool(issues)
  except Exception as e:passed=False;issues=[str(e)]
  counts[kind+ ("_pass" if passed else "_FAIL")]+=1
  if not passed and len(failures)<100:failures.append({"kind":kind,"sql":sql,"issues":issues})
summary={"total":sum(counts.values()),"unique_sql":len(unique),"counts":dict(counts),"failures":failures,"seconds":round(time.monotonic()-start,1)}
(out/"mutation-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!="failures"}))
