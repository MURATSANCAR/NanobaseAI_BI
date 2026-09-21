"""Controlled real-catalog acceptance; run inside the dedicated GPU MCP container.

No book-specific branching or expected answers. Stops on technical failure.
Semantic acceptance always requires independent source review afterwards.
"""
import asyncio, fcntl, hashlib, json, os
from pathlib import Path
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from editor import db
from editor.config import settings

ROOT=Path(os.environ['EDITOR_ACCEPTANCE_DIR'])
ROOT.mkdir(parents=True, exist_ok=True)
lock=(ROOT/'runner.lock').open('w')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
STATE=ROOT/'state.json'
def save(value):
 tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,default=str,indent=2));tmp.replace(STATE)
 print(json.dumps(value,ensure_ascii=False,default=str),flush=True)
def value(result):
 if result.is_error:raise RuntimeError(str(result.content))
 values=[json.loads(c.text) for c in result.content if c.type=='text']
 return values[0] if len(values)==1 else values
async def main():
 code=os.environ.get('EDITOR_CODE_VERSION')
 if STATE.exists():
  state=json.loads(STATE.read_text())
  if state['code_version']!=code:raise ValueError('Do not mix release versions in one acceptance run')
 else:
  if db.all_rows("SELECT id FROM analysis_job WHERE status IN ('RUNNING','QUEUED')"):
   raise ValueError('An analysis is already active; do not duplicate heavy runs')
  catalog=db.all_rows('SELECT bv.id,bv.sha256,bv.page_count,b.title FROM book_version bv JOIN book b ON b.id=bv.book_id ORDER BY bv.page_count,bv.id')
  inbox={hashlib.sha256(p.read_bytes()).hexdigest():p.name for p in settings().inbox.glob('*.pdf')}
  missing=[str(b['id']) for b in catalog if b['sha256'] not in inbox]
  if missing:raise ValueError('Original catalog PDF missing from inbox: '+str(missing))
  state={'code_version':code,'task_queue':settings().task_queue,'status':'RUNNING','semantic_acceptance':False,
   'books':[{'book_version_id':str(b['id']),'sha256':b['sha256'],'title':b['title'],'pages':b['page_count'],'file_name':inbox[b['sha256']],'status':'PENDING'} for b in catalog]}
  save(state)
 async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+os.environ['EDITOR_MCP_KEY']},timeout=120) as http:
  async with streamable_http_client('http://127.0.0.1:8000/jobs/mcp',http_client=http) as (read,write):
   async with ClientSession(read,write) as session:
    await session.initialize()
    for book in state['books']:
     if book['status']=='SUCCEEDED':continue
     if book['status'] in ('FAILED','CANCELLED'):
      state['status']='BLOCKED_TECHNICAL';save(state);return
     if not book.get('job_id'):
      result=value(await session.call_tool('start_analysis_job',{'file_name':book['file_name'],'title':book['title']}))
      if result.get('already_running'):raise ValueError('Existing job cannot be credited to this release')
      book['job_id']=result['job_id'];book['workflow_id']=result['workflow_id'];save(state)
     while True:
      status=value(await session.call_tool('get_job_status',{'job_id':book['job_id']}))
      old=(book.get('status'),book.get('step'))
      book.update({k:status.get(k) for k in ('status','step','generation_id','error')})
      if old!=(book['status'],book['step']):save(state)
      if book['status'] in ('SUCCEEDED','FAILED','CANCELLED'):break
      await asyncio.sleep(30)
     if book['status']!='SUCCEEDED':
      state['status']='BLOCKED_TECHNICAL';save(state);return
     book['analytical_status']='UNASSESSED';save(state)
    state['status']='TECHNICAL_RUNS_COMPLETE_SEMANTIC_REVIEW_REQUIRED';save(state)
asyncio.run(main())
