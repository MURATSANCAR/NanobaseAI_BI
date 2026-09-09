import json,os,urllib.request,decimal,time
from pathlib import Path
root=Path('/data/nanobaseai/bi/backups/default-questions-20260909')
refs=json.loads((root/'reference-results.json').read_text())
cases=[
(0,'2026 kanal bazında net ciro'),(0,'2026 net ciro kanal bazında'),(0,'2026 kanal bazında net ciro göster'),(0,'2026 kanal bazında net ciro nedir?'),(0,'2026 kanal bazında net ciro hesapla'),
(1,'İade tutarına göre ilk 10 müşteri'),(1,'2026 müşteri bazında iade tutarı ilk 10'),(1,'2026 iade tutarı müşteri bazında ilk 10'),(1,'2026 müşteri bazında iade tutarı ilk 10 göster'),(1,'2026 müşteri bazında iade tutarı top 10'),
(2,'Aylık iskonto oranı'),(2,'2026 aylık iskonto oranı'),(2,'2026 aylık iskonto oranı göster'),(2,'2026 aylık iskonto oranı nedir?'),(2,'2026 aylık iskonto oranı hesapla'),
(3,'En çok satan 10 kitap (adet)'),(3,'2026 kitap bazında satılan adet ilk 10'),(3,'2026 satılan adet kitap bazında ilk 10'),(3,'2026 kitap bazında satılan adet top 10'),(3,'En çok satan on kitap adet')]
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8795'+path,data=json.dumps(body).encode() if body else None,headers=headers)
 with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
def norm(v):return str(decimal.Decimal(str(v)).quantize(decimal.Decimal('0.00001'))) if v is not None else None
out=[]
for idx,(ref,q) in enumerate(cases,1):
 start=time.monotonic();row={'id':f'V{idx:02}','question':q,'reference':ref}
 try:
  a=call('/api/v1/ask',{'question':q});row['answer']=a;row['status']='FAIL'
  if a.get('type')=='TEXT_TO_SQL' and a.get('resultId'):
   b=call('/api/v1/result/'+a['resultId']);row['fullResult']=b
   cols=b['columns'];numbers=[c['name'] for c in cols if c['type'] in ['float','int','Decimal','decimal']];labels=[c['name'] for c in cols if c['name'] not in numbers]
   if len(cols)==2 and len(numbers)==1 and len(labels)==1:
    actual=sorted([(str(r[labels[0]]) if r[labels[0]] is not None else None,norm(r[numbers[0]])) for r in b['records']],key=str)
    expected=sorted([tuple(r) for r in refs[ref]['expected']],key=str)
    if actual==expected and not b['truncated'] and len(b['records'])==b['totalRows']:row['status']='LIVE_PASS'
 except Exception as e:row['status']='UNVERIFIED';row['error']=str(e)
 row['seconds']=round(time.monotonic()-start,3);out.append(row)
 with (root/'variants-accepted.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 print(json.dumps({'id':row['id'],'status':row['status'],'type':row.get('answer',{}).get('type'),'seconds':row['seconds']},ensure_ascii=False),flush=True)
 if idx%10==0:print(json.dumps({'completed':idx,'passed':sum(r['status']=='LIVE_PASS' for r in out),'failed':sum(r['status']=='FAIL' for r in out),'unverified':sum(r['status']=='UNVERIFIED' for r in out)}),flush=True)
