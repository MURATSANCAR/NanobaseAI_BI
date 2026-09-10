import os,json,time,urllib.request,hashlib
from pathlib import Path
base="http://127.0.0.1:8795"
headers={"Content-Type":"application/json","X-Semantic-Caller":os.environ["SEMANTIC_CALLER_TOKEN"]}
checks=[("complex-preview","/api/v1/ask",{"question":"Ocak 2024 için müşteri, ürün, ödeme planı, satış temsilcisi, teslimat şehri ve birim bazında satılan adet göster.","sampleSize":50}), ("followup-complex","/api/v1/ask",{"question":"2026 yılında her ay için müşterileri net satış tutarına göre sırala ve her müşterinin önceki aya göre yüzde değişimini göster.","sampleSize":20})]
for name,path,body in checks:
 t=time.monotonic()
 try:
  req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers=headers)
  with urllib.request.urlopen(req,timeout=180) as f:a=json.load(f)
  a.pop("records",None)
  if a.get("resultId"):
   with urllib.request.urlopen(urllib.request.Request(base+"/api/v1/result/"+a["resultId"],headers=headers),timeout=30) as f:
    snap=json.load(f)
   a["storedResultCheck"]={k:v for k,v in snap.items() if k not in ("records","sql","physicalSql","question")}
  print(json.dumps({"check":name,"seconds":round(time.monotonic()-t,2),"response":a},ensure_ascii=False,default=str),flush=True)
 except Exception as e:print(json.dumps({"check":name,"error":str(e),"seconds":round(time.monotonic()-t,2)}),flush=True)
