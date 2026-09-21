"""Read-only real API/PG acceptance of page targets and bounded plot repairs."""
import json, os, sys
import httpx
from editor import db
from editor.config import settings
G=sys.argv[1]
with db.tx() as c:
 c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
 snap=c.execute("SELECT s.content FROM knowledge_snapshot s JOIN current_artifact a ON a.generation_id=s.generation_id AND a.input_digest=s.input_digest WHERE a.generation_id=%s AND a.kind='book_summary'",(G,)).fetchone()['content']
 book=c.execute("SELECT content FROM current_artifact WHERE generation_id=%s AND kind='book_summary'",(G,)).fetchone()['content']
 reviews=c.execute("SELECT r.id,r.page_role_page_no FROM review_item r JOIN page_role p ON p.generation_id=r.generation_id AND p.page_no=r.page_role_page_no WHERE r.generation_id=%s",(G,)).fetchall()
claims={c['id']:c for c in snap['claims'] if c['kind']=='EVENT'}
expected={p for c in claims.values() for p in c['source_pages']}
actual={p for s in book['sentences'] for p in s['pages']}
checks=[{'name':'plot uses only verified events','passed':bool(book['sentences']) and all(set(s['claim_ids'])<=claims.keys() for s in book['sentences'])},
 {'name':'first and last supported event retained','passed':bool(expected) and bool(actual) and min(expected)==min(actual) and max(expected)==max(actual)},
 {'name':'new summary policy','passed':snap['policy']=='validated-outputs-v9'},
 {'name':'all three page review targets','passed':{r['page_role_page_no'] for r in reviews}=={1,2,3}}]
# Fetch actual served artifact, not a re-execution of its production query.
s=settings()
with httpx.Client(base_url='http://editor-control:8000',headers={'Authorization':'Bearer '+s.gateway_internal_key},timeout=90) as client:
 r=client.get(f'/v1/generations/{G}/artifacts/book_summary');r.raise_for_status();response=r.json()
checks.append({'name':'served API summary equals immutable PG content','passed':response.get('available') is True and response.get('artifact',{}).get('content')==book})
print(json.dumps({'generation_id':G,'code_version':os.environ.get('EDITOR_CODE_VERSION'),'checks':checks,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'expected_event_pages':sorted(expected),'summary_pages':sorted(actual),'summary':book,'api':response},ensure_ascii=False,default=str))
