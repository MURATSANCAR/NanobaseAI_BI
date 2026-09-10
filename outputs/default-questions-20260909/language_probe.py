import json,os,urllib.request,time
from pathlib import Path
questions=['En çok iade alan 10 müşteri','iptal edilen kaç sipariş var','kitap olmayanlardan en çok 10 satılan ürün','En çok satan 10 kitap','2026 brüt kâr marjı','test','sen kimsin?']
out=[]
for q in questions:
 row={'question':q,'status':'DOĞRULANAMADI'}
 try:
  req=urllib.request.Request('http://127.0.0.1:8795/api/v1/ask',data=json.dumps({'question':q,'sampleSize':20}).encode(),headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']})
  with urllib.request.urlopen(req,timeout=180) as res:a=json.load(res)
  row['answer']=a;row['responseType']=a.get('type')
  if a.get('type')=='TEXT_TO_SQL':row['note']='SQL response; no independent business oracle for this ambiguous wording.'
  else:row['note']='Non-SQL response; not counted as semantic answer success.'
 except Exception as e:row['error']=str(e)
 out.append(row);print(json.dumps({'question':q,'type':row.get('responseType'),'status':row['status']},ensure_ascii=False),flush=True)
 Path('/data/nanobaseai/bi/backups/default-questions-20260909/language-probe.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
