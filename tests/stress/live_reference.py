import os,json,urllib.request,urllib.error,time
from pathlib import Path
from semantic_bridge.app import build_runtime
r=build_runtime()
cases=[("Mart 2026 toptan satış tutarı","2026-03-01","2026-04-01","8","sales"),
("Mayıs 2026 perakende satış tutarı","2026-05-01","2026-06-01","7","sales"),
("Şubat 2026 net ciro","2026-02-01","2026-03-01","2,3,7,8,9","net"),
("Nisan 2026 kanal bazında net ciro","2026-04-01","2026-05-01","2,3,7,8,9","group")]
out=[]
for q,start,end,codes,kind in cases:
 formula="SUM(I.NETTOTAL)" if kind=="sales" else "SUM(CASE WHEN I.TRCODE IN (7,8,9) THEN I.NETTOTAL ELSE -I.NETTOTAL END)"
 prefix="C.SPECODE2, " if kind=="group" else ""
 join=" JOIN dbo.LG_411_CLCARD C ON I.CLIENTREF=C.LOGICALREF" if kind=="group" else ""
 group=" GROUP BY C.SPECODE2" if kind=="group" else ""
 ref=f"SELECT {prefix}{formula} FROM dbo.LG_411_01_INVOICE I{join} WHERE I.CANCELLED=0 AND I.TRCODE IN ({codes}) AND I.DATE_ >= '{start}' AND I.DATE_ < '{end}'{group}"
 cols,rows,truncated=r.connector.execute(ref,1000)
 rows=[[row.get(col["name"]) for col in cols] for row in rows]
 req=urllib.request.Request("http://127.0.0.1:8795/api/v1/ask",data=json.dumps({"question":q,"sampleSize":1000}).encode(),headers={"Content-Type":"application/json","X-Semantic-Caller":os.environ["SEMANTIC_CALLER_TOKEN"]})
 t=time.monotonic()
 with urllib.request.urlopen(req,timeout=180) as resp:a=json.load(resp)
 def norm(records):
  return sorted([tuple(round(float(v),3) if isinstance(v,(int,float)) or type(v).__name__=="Decimal" else (v.strip() if isinstance(v,str) else v) for v in row) for row in records],key=repr)
 actual=a.get("records") or []
 if actual and isinstance(actual[0],dict):actual=[[row.get(c["name"]) for c in a["columns"]] for row in actual]
 correct=a.get("type")=="TEXT_TO_SQL" and norm(rows)==norm(actual)
 item={"q":q,"type":a.get("type"),"correct":correct,"referenceSql":ref,"generatedSql":a.get("sql"),"referenceRows":len(rows),"answerRows":len(actual),"explanation":a.get("explanation"),"trace":(a.get("semantic") or {}).get("query"),"seconds":round(time.monotonic()-t,1)}
 out.append(item);Path("/tmp/fresh-reference-results.json").write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in item.items() if k not in ["referenceSql","generatedSql","trace"]},ensure_ascii=False),flush=True)
if r.connector:r.connector.close()
