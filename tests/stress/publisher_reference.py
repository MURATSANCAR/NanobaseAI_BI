import json,os,urllib.request,time
from datetime import date,timedelta
from pathlib import Path
from semantic_bridge.app import build_runtime
r=build_runtime();today=date.today();year=today.year
start=f"{year}-01-01";end=(today+timedelta(days=1)).isoformat()
question=f"{year} yılbaşından bugüne yayınevi bazında net ciro ve satılan adet"
reference=f"""SELECT P.SPECODE AS ref_publisher,
SUM(CASE WHEN L.TRCODE IN (7,8) THEN L.LINENET ELSE -L.LINENET END) AS ref_net,
SUM(CASE WHEN L.TRCODE IN (7,8) THEN L.AMOUNT END) AS ref_units
FROM dbo.LG_411_01_STLINE L JOIN dbo.LG_411_ITEMS P ON L.STOCKREF=P.LOGICALREF
WHERE L.CANCELLED=0 AND L.LINETYPE=0 AND L.TRCODE IN (2,3,7,8)
AND L.DATE_ >= '{start}' AND L.DATE_ < '{end}' GROUP BY P.SPECODE"""
cols,rows,truncated=r.connector.execute(reference,1000)
expected=[[row.get(c["name"]) for c in cols] for row in rows]
request=urllib.request.Request("http://127.0.0.1:8795/api/v1/ask",data=json.dumps({"question":question,"sampleSize":1000}).encode(),headers={"Content-Type":"application/json","X-Semantic-Caller":os.environ["SEMANTIC_CALLER_TOKEN"]})
with urllib.request.urlopen(request,timeout=180) as response:a=json.load(response)
actual=a.get("records") or []
if actual and isinstance(actual[0],dict):actual=[[row.get(c["name"]) for c in a["columns"]] for row in actual]
def norm(rows):
 return sorted([tuple(round(float(v),3) if isinstance(v,(int,float)) or type(v).__name__=="Decimal" else v.strip() if isinstance(v,str) else v for v in row) for row in rows],key=repr)
result={"question":question,"type":a.get("type"),"correct":not truncated and a.get("type")=="TEXT_TO_SQL" and norm(expected)==norm(actual),"referenceRows":len(expected),"answerRows":len(actual),"columns":a.get("columns"),"referenceSql":reference,"sql":a.get("sql"),"explanation":a.get("explanation"),"semantic":a.get("semantic")}
Path("/tmp/publisher-reference.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ("semantic","referenceSql","sql")},ensure_ascii=False))
if result["correct"]:
 stored_request=urllib.request.Request("http://127.0.0.1:8795/api/v1/result/"+a["resultId"],headers={"X-Semantic-Caller":os.environ["SEMANTIC_CALLER_TOKEN"]})
 with urllib.request.urlopen(stored_request,timeout=30) as response:stored=json.load(response)
 assert stored["columns"]==a["columns"] and stored["records"]==a["records"]
 assert stored["totalRows"]==len(expected)
 result["snapshotMatches"]=True
 follow=f"Mart {year}"
 request=urllib.request.Request("http://127.0.0.1:8795/api/v1/ask",data=json.dumps({"question":follow,"threadId":a["threadId"],"sampleSize":1000}).encode(),headers={"Content-Type":"application/json","X-Semantic-Caller":os.environ["SEMANTIC_CALLER_TOKEN"]})
 with urllib.request.urlopen(request,timeout=180) as response:b=json.load(response)
 follow_reference=reference.replace(start,f"{year}-03-01").replace(end,f"{year}-04-01")
 cols,rows,truncated=r.connector.execute(follow_reference,1000)
 expected_follow=[[row.get(c["name"]) for c in cols] for row in rows]
 actual_follow=b.get("records") or []
 if actual_follow and isinstance(actual_follow[0],dict):actual_follow=[[row.get(c["name"]) for c in b["columns"]] for row in actual_follow]
 result["followup"]={"question":follow,"type":b.get("type"),"correct":not truncated and b.get("type")=="TEXT_TO_SQL" and norm(actual_follow)==norm(expected_follow),"referenceRows":len(expected_follow),"answerRows":len(actual_follow),"referenceSql":follow_reference,"sql":b.get("sql"),"explanation":b.get("explanation")}
 Path("/tmp/publisher-reference.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps({"snapshotMatches":True,"followup":{k:v for k,v in result["followup"].items() if k not in ("referenceSql","sql")}},ensure_ascii=False))
r.connector.close()
