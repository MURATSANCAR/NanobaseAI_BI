import concurrent.futures,json,os,time,urllib.request,hashlib
from pathlib import Path
question='2026 yılında her ay için müşterileri net satış tutarına göre sırala ve her müşterinin önceki aya göre yüzde değişimini göster.'
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def probe(_):
 start=time.monotonic()
 req=urllib.request.Request('http://127.0.0.1:8795/api/v1/ask',data=json.dumps({'question':question}).encode(),headers=headers)
 with urllib.request.urlopen(req,timeout=180) as resp:a=json.load(resp)
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8795/api/v1/result/'+a['resultId'],headers=headers),timeout=180) as resp:b=json.load(resp)
 return {'type':a['type'],'rows':len(b['records']),'truncated':b['truncated'],'computedAt':b['computedAt'],'cached':a.get('cached'),'seconds':round(time.monotonic()-start,3),'hash':hashlib.sha256(json.dumps(b['records'],sort_keys=True).encode()).hexdigest()}
first=probe(0)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: simultaneous=list(pool.map(probe,range(3)))
report={'warmup':first,'simultaneous':simultaneous,'passed':all(x['rows']==5255 and not x['truncated'] and x['hash']==first['hash'] and x['computedAt']==first['computedAt'] for x in simultaneous)}
Path('/data/nanobaseai/bi/backups/product-quality-20260909/concurrency.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
