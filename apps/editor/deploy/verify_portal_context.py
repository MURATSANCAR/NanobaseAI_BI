"""Run on nanobase-cm only, real authenticated portal and independent persisted DB rows."""
import json,os,time,hashlib,urllib.request,urllib.error
from pathlib import Path
import sqlalchemy as sa
root=Path('/tmp/editor-context-474cb2d9')
for l in Path('/etc/nanobase/semantic-bridge.env').read_text().splitlines():
 if '=' in l and not l.startswith('#'):
  k,v=l.split('=',1);os.environ[k]=v.strip().strip('"').strip("'")
headers={'Cookie':(root/'session.cookie').read_text().strip(),'Content-Type':'application/json','Origin':'https://portal.nanobase.ai'}
base='https://portal.nanobase.ai/timas/api/v1/editorial/ask'
def api(path='',body=None,auth=True):
 req=urllib.request.Request(base+path,data=json.dumps(body,ensure_ascii=False).encode() if body else None,headers=headers if auth else {})
 with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)
def finish(qid):
 deadline=time.monotonic()+600
 while time.monotonic()<deadline:
  r=api('/'+qid)
  if r['status'] not in ('bekliyor','calisiyor'):return r
  time.sleep(5)
 raise TimeoutError(qid)
checks=[]
def check(name,ok):
 checks.append({'name':name,'passed':bool(ok)})
 print(json.dumps(checks[-1]),flush=True)
start=api();assert start['running']==0,start['running']
book='Dünyanın En Korkak Hayvanı'
a=api(body={'question':'Yavru Vombat ile Baba Vombat aynı karakter mi? Kaynaktan kısa açıklama yap.','bookTitle':book})
a=finish(a['id']);(root/'first.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));check('first-real-answer',a['status']=='bitti')
b=api(body={'question':'Az önce hangi iki karakteri karşılaştırmanı istedim? Yalnız adlarını söyle.','bookTitle':book,'parentId':a['id']})
b=finish(b['id']);(root/'followup.json').write_text(json.dumps(b,ensure_ascii=False,indent=2));check('followup-real-answer',b['status']=='bitti')
check('followup-remembers-both-names',all(s in (b.get('answer') or '').lower() for s in ('yavru','baba','vombat')))
e=sa.create_engine(os.environ['SEMANTIC_STORE_DSN'])
with e.connect() as c:
 rows=c.execute(sa.text('select id,parent_id,username,tenant_id,book_title,question,answer,status from semantic_editorial_questions where id in (:a,:b)'),{'a':a['id'],'b':b['id']}).mappings().all()
ref={r['id']:dict(r) for r in rows}
check('persisted-parent-chain',ref[b['id']]['parent_id']==a['id'] and ref[a['id']]['parent_id'] is None)
check('same-user-tenant-book',all(ref[a['id']][k]==ref[b['id']][k] for k in ('username','tenant_id','book_title')))
check('wire-answers-equal-independent-db',all(ref[r['id']]['answer']==r['answer'] and ref[r['id']]['question']==r['question'] for r in (a,b)))
try:api(body={'question':'Peki babası?','bookTitle':'Ekrana Sığmayan Macera','parentId':a['id']});code=200
except urllib.error.HTTPError as exc:code=exc.code
check('cross-book-parent-rejected',code==409)
try:api('/'+a['id'],auth=False);code=200
except urllib.error.HTTPError as exc:code=exc.code
check('unauthenticated-read-rejected',code in (401,403))
files=['backend/semantic_bridge/app.py','backend/semantic_bridge/editorial_books.py','src/canvas/editorial/AskBox.tsx','src/canvas/engine.ts']
result={'environment':'nanobase-cm real portal + Hermes GPU relay + PostgreSQL','revision':'474cb2d9','api':base,'checks':checks,'answers':[a,b],'reference':list(ref.values()),'hashes':{f:hashlib.sha256(Path('/data/nanobaseai/bi/frontend',f).read_bytes()).hexdigest() for f in files}}
(root/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks)}),flush=True)
