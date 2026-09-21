"""Run only on nanobase-direct against the real authenticated API and independent CRM reads."""
import collections
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
from datetime import datetime
from decimal import Decimal
from semantic_layer.profiler.connectors import connector_from_file

for line in Path('/etc/nanobase/semantic-bridge.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1); os.environ[k]=v.strip().strip('"').strip("'")
headers={'X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN'],
         'Cookie':Path('/tmp/editorial-home-acceptance.cookie').read_text()}
base='http://127.0.0.1:8795/api/v1/editorial/'
def api(path, hdr=headers):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers=hdr),timeout=120) as r:
        return json.load(r)
checks=[]
def check(name, ok):
    checks.append({'name':name,'status':'PASS' if ok else 'FAIL'})
    if len(checks)%10==0:
        print(json.dumps({'completed':len(checks),'pass':sum(x['status']=='PASS' for x in checks),'fail':sum(x['status']=='FAIL' for x in checks),'unverified':0}),flush=True)

t0=time.perf_counter(); out=api('home'); latency=round((time.perf_counter()-t0)*1000,1)
Path('/tmp/editorial-home-response.json').write_text(json.dumps(out,ensure_ascii=False,default=str))
parts=out['parts']
check('all-six-persisted-parts-ready',not out['loading'] and all('data' in p and not p.get('error') for p in parts.values()))
check('five-minute-refresh-contract',out['refreshIntervalSeconds']==300)
check('warm-api-under-two-seconds',latency<2000)
check('snapshot-revision',out['revision']==hashlib.sha256(Path('backend/semantic_bridge/editorial_home.py').read_bytes()+Path('backend/semantic_bridge/editorial.py').read_bytes()).hexdigest())
for name,path in [('contracts','contracts/summary'),('board','board/summary'),('editors','editors'),('roles','contributors/roles'),('expiring','contracts?expiring=true&order=bitis&page=0')]:
    # Full wire payload equivalence supplements (does not replace) independent references below.
    old=api(path); new=parts[name]['data']
    check('complete-api-payload-'+name,{k:v for k,v in old.items() if k!='db'}=={k:v for k,v in new.items() if k!='db'})
check('scoped-desk-equals-existing-api',out['works']==api('works'))
for name,hdr in [('no-credentials',{}),('caller-without-user',{'X-Semantic-Caller':headers['X-Semantic-Caller']})]:
    try: api('home',hdr); status=200
    except urllib.error.HTTPError as exc: status=exc.code
    check(name+'-rejected',status==401)

crm=connector_from_file('/data/nanobaseai/bi/secrets/crm-mssql-connection.json')
def rows(sql):
    cols,records,cut=crm.execute(sql,100000)
    if cut: raise RuntimeError('Independent reference truncated')
    return records
# Independent row-level source: count/filter in Python, no application SQL builder or formatter.
raw=rows("SELECT statuscode,new_SozlesmeTipi AS kind,new_Telif AS royalty,new_suresizsozlesme AS unlimited,new_SozlesmeBitisTarihi AS ends FROM dbo.new_sozlesmeBase WHERE statecode=0")
today=rows('SELECT CONVERT(varchar(10),GETDATE(),23) AS today')[0]['today']
day=datetime.fromisoformat(today).date(); summary=parts['contracts']['data']
active=[r for r in raw if r['statuscode'] in (100000000,100000006,100000007)]
exp=[r for r in active if not r['unlimited'] and r['ends'] is not None and 0 <= (datetime.fromisoformat(str(r['ends'])[:10]).date()-day).days <= summary['warnDays']]
royalties=[Decimal(str(r['royalty'])) for r in active if r['royalty'] is not None and r['royalty']>0]
check('independent-contract-total',summary['total']==len(raw))
check('independent-contract-active',summary['active']==len(active))
check('independent-contract-renewal',summary['renewal']==sum(r['statuscode']==100000007 for r in raw))
check('independent-contract-expiring',summary['expiring']==len(exp))
check('independent-contract-royalty',summary['avgRoyaltyOver']==len(royalties) and (abs(Decimal(str(summary['avgRoyalty']))-sum(royalties)/len(royalties))<Decimal('0.00001') if royalties else summary['avgRoyalty'] is None))
for key,col in [('statuses','statuscode'),('kinds','kind')]:
    ref=collections.Counter(r[col] for r in raw if r[col] is not None)
    check('independent-contract-'+key,{x['code']:x['count'] for x in summary[key]}==dict(ref))
raw=rows('SELECT new_toplantitarihi AS happened,statuscode AS decision FROM dbo.new_yayinkurulutoplantilariBase WHERE statecode=0 AND new_toplantitarihi IS NOT NULL')
by_year=collections.defaultdict(list)
for r in raw: by_year[int(str(r['happened'])[:4])].append(r)
check('independent-board-full-years',set(by_year)=={x['year'] for x in parts['board']['data']['years']})
check('independent-board-full-values',all(x['total']==len(by_year[x['year']]) and x['sessions']==len({str(r['happened'])[:10] for r in by_year[x['year']]}) and x['last']==max(str(r['happened'])[:10] for r in by_year[x['year']]) and {d['code']:d['count'] for d in x['decisions']}==dict(collections.Counter(r['decision'] or 0 for r in by_year[x['year']])) for x in parts['board']['data']['years']))
# Contribution type rows are read first; unique people and contribution counts are independent Python groups.
raw=rows('SELECT t.new_name AS role,e.new_Katilimsaglayan AS person FROM dbo.new_eserkatilimBase e INNER JOIN dbo.new_katilimcitipiBase t ON e.new_katilimciTipi=t.new_katilimcitipiId WHERE e.statecode=0 AND e.new_Katilimsaglayan IS NOT NULL')
by_role=collections.defaultdict(list)
for r in raw:by_role[r['role'].strip() if r['role'] else None].append(str(r['person']))
check('independent-roles-all-values',{x['role']:(x['records'],x['people']) for x in parts['roles']['data']['items']}=={role:(len(v),len(set(v))) for role,v in by_role.items()})
editors=parts['editors']['data']
raw=rows(f"SELECT p.new_editoru AS editor,p.statuscode AS status,p.ModifiedOn AS modified,u.FullName AS name,u.IsDisabled AS disabled FROM dbo.new_projeBase p LEFT JOIN dbo.SystemUserBase u ON p.new_editoru=u.SystemUserId WHERE p.statecode=0 AND p.CreatedOn >= '{editors['sinceYear']}-01-01'")
assigned=collections.defaultdict(list)
for r in raw:
    if r['editor'] is not None and r['name'] is not None:assigned[str(r['editor']).lower()].append(r)
check('independent-editor-all-identities',set(assigned)=={x['id'].lower() for x in editors['items']})
check('independent-editor-all-values',all(x['total']==len(assigned[x['id'].lower()]) and x['name']==assigned[x['id'].lower()][0]['name'].strip() and x['disabled']==bool(assigned[x['id'].lower()][0]['disabled']) and x['last']==max(str(r['modified'])[:10] for r in assigned[x['id'].lower()]) and {v['code']:v['count'] for v in x['byStatus']}==dict(collections.Counter(r['status'] or 0 for r in assigned[x['id'].lower()])) for x in editors['items']))
check('independent-unassigned',{x['code']:x['count'] for x in editors['unassigned']}==dict(collections.Counter(r['status'] or 0 for r in raw if r['editor'] is None)))
check('editor-results-not-truncated',editors['truncated'] is False)
expiring=parts['expiring']['data']
check('expiring-total-and-page',expiring['total']==len(exp) and expiring['page']==0 and len(expiring['items'])==min(len(exp),expiring['pageSize']))
# Independently get all qualifying source identities and days, then compare the API's ordered first page.
raw=rows(f"SELECT new_sozlesmeId AS id,new_name AS name,new_SozlesmeBitisTarihi AS ends,DATEDIFF(day,CAST(GETDATE() AS date),new_SozlesmeBitisTarihi) AS days FROM dbo.new_sozlesmeBase WHERE statecode=0 AND statuscode IN (100000000,100000006,100000007) AND ISNULL(new_suresizsozlesme,0)=0 AND new_SozlesmeBitisTarihi>=CAST(GETDATE() AS date) AND new_SozlesmeBitisTarihi<DATEADD(day,{summary['warnDays']+1},CAST(GETDATE() AS date)) ORDER BY new_SozlesmeBitisTarihi,new_sozlesmeId")
check('independent-expiring-ordered-values',[(x['id'].lower(),x['no'],x['end'],x['daysLeft']) for x in expiring['items']]==[(str(r['id']).lower(),r['name'].strip() if r['name'] else None,str(r['ends'])[:10],r['days']) for r in raw[:expiring['pageSize']]])
# Independent Editor catalogue HTTP response; no model invocation or snapshot helper.
with urllib.request.urlopen(urllib.request.Request(os.environ['EDITOR_CATALOG_BASE'].rstrip('/')+'/v1/books/cards',headers={'Authorization':'Bearer '+os.environ['EDITOR_CATALOG_KEY']}),timeout=30) as response:
    catalogue=json.load(response)['items']
book_reference=list(dict.fromkeys(c['title'] for c in catalogue if c.get('contentAvailable') and c.get('title')))
check('readable-books-match-authoritative-catalogue',parts['readableBooks']['data']['items']==book_reference)
check('readable-books-route-matches-snapshot',api('ask/books')==parts['readableBooks']['data'])
second=api('home')
check('repeat-read-retains-data',second['parts']==out['parts'])
check('no-user-desk-in-shared-cache',all('works' not in p.get('data',{}) and 'user' not in p.get('data',{}) for p in parts.values()))
result={'environment':'nanobase-direct','api':base+'home','reference':'Independent read-only CRM SQL on 192.168.0.28 / Timas_MSCRM plus full original API payload equivalence','latencyMs':latency,'revision':out['revision'],'checks':checks,'passed':sum(c['status']=='PASS' for c in checks),'failed':sum(c['status']=='FAIL' for c in checks),'updatedAt':{k:v.get('updatedAt') for k,v in parts.items()},'sourceHashes':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['backend/semantic_bridge/app.py','backend/semantic_bridge/editorial_home.py','src/canvas/editorial/EditorialHome.tsx','src/canvas/editorial/homeQuery.ts','src/canvas/TimasSession.tsx','src/canvas/engine.ts','src/canvas/editorial/AskBox.tsx']}}
Path('/tmp/editorial-home-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False),flush=True)
