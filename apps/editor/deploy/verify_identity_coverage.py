"""Real tt-gpu API + ledger + original PDF acceptance; never run locally."""
import hashlib
import json
import os
import sys
import httpx
import pymupdf
from editor import db

GID=sys.argv[1]
checks=[]
def check(name,actual,expected):
    ok=actual==expected
    checks.append({'check':name,'passed':ok,**({} if ok else {'actual':actual,'expected':expected})})
    if len(checks)%10==0: print(json.dumps({'completed':len(checks),'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks)}),file=sys.stderr,flush=True)
from editor.config import settings
with db.tx() as c:
    c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    gen=c.execute('SELECT g.*,v.file_path,v.sha256 FROM ed.generation g JOIN ed.book_version v ON v.id=g.book_version_id WHERE g.id=%s',(GID,)).fetchone()
    mentions=c.execute('SELECT m.*,e.kind AS evidence_kind,e.quote_verified FROM ed.character_mention m JOIN ed.evidence e ON e.id=m.evidence_id AND e.generation_id=m.generation_id WHERE m.generation_id=%s ORDER BY m.id',(GID,)).fetchall()
    scans=c.execute('SELECT DISTINCT page_no FROM ed.page_scan WHERE generation_id=%s ORDER BY page_no',(GID,)).fetchall()
    chars=c.execute('SELECT * FROM ed.character WHERE generation_id=%s',(GID,)).fetchall()
    ocr=c.execute("SELECT page_no,text,model_call_id FROM ed.page_text WHERE generation_id=%s AND source='OCR' ORDER BY page_no",(GID,)).fetchall()
with open(gen['file_path'],'rb') as f: check('original PDF hash',hashlib.file_digest(f,'sha256').hexdigest(),gen['sha256'])
pdf=pymupdf.open(gen['file_path'])
with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+settings().gateway_internal_key},timeout=60) as client:
    r=client.get(f'/v1/generations/{GID}/identity/coverage');r.raise_for_status();coverage=r.json()
    check('physical pages vs original PDF',coverage['physical_pages'],len(pdf))
    check('scanned pages',coverage['scanned_pages'],len(scans))
    for via in ('TEXT','VISUAL','BOTH'):
        rows=[m for m in mentions if m['via']==via];v=coverage['mentions'][via]
        check(via+':total',v['total'],len(rows))
        check(via+':linked',v['linked'],sum(m['character_id'] is not None for m in rows))
        check(via+':resolved',v['resolved'],sum(m['resolution']=='RESOLVED' for m in rows))
        check(via+':confirmed identities',v['confirmed_identity'],sum(m['resolution']=='RESOLVED' and any(ch['id']==m['character_id'] and ch['identity_status']=='CONFIRMED' for ch in chars) for m in rows))
    for page in (4,10):
        r=client.get(f'/v1/generations/{GID}/source/pages/{page}');r.raise_for_status();v=r.json()
        row=next(x for x in ocr if x['page_no']==page)
        check(f'p{page}:actual OCR completion stored',row['model_call_id'] is not None,True)
        check(f'p{page}:original PDF no text',pdf[page-1].get_text().strip(),'')
        check(f'p{page}:no invented OCR words',row['text'],'')
        check(f'p{page}:empty OCR distinct from missing',v['ocr_status'],'COMPLETED_NO_TEXT')
        check(f'p{page}:not incorrectly missing','OCR_REQUIRED_MISSING' in v['issues'],False)
        check(f'p{page}:not semantic acceptance',v['semantic_acceptance'],False)
    # Explicit real-source expectations, not generated from application output.
    original_page6=pdf[5].get_text()
    check('p6 source names father and child separately','Baba Vombat' in original_page6 and 'Yavru Vombat' in original_page6,True)
    father=[ch for ch in chars if 'Baba Vombat' in [ch['canonical_name'],*ch['aliases']]]
    child=[ch for ch in chars if 'Yavru Vombat' in [ch['canonical_name'],*ch['aliases']]]
    check('father has unique identity',len(father),1)
    check('child has unique identity',len(child),1)
    if father and child:
        check('father not merged into child',father[0]['id']!=child[0]['id'],True)
        check('father animal not human',father[0]['kind'],'ANIMAL')
        check('child animal not human',child[0]['kind'],'ANIMAL')
        check('father individual',father[0]['traits'].get('entity_scope'),'INDIVIDUAL')
        check('child individual',child[0]['traits'].get('entity_scope'),'INDIVIDUAL')
    check('collectives not confirmed individuals',all(ch['identity_status']!='CONFIRMED' for ch in chars if ch['traits'].get('entity_scope')=='COLLECTIVE'),True)
    check('independent accuracy not overstated',coverage['identity_accuracy'],'NOT_INDEPENDENTLY_ACCEPTED')
print(json.dumps({'code_version':os.environ.get('EDITOR_CODE_VERSION'),'generation_code':gen['code_version'],'generation_id':GID,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'checks':checks,'coverage':coverage,'characters':[{'name':ch['canonical_name'],'aliases':ch['aliases'],'kind':ch['kind'],'traits':ch['traits'],'status':ch['identity_status']} for ch in chars]},ensure_ascii=False,default=str))
raise SystemExit(any(not x['passed'] for x in checks))
