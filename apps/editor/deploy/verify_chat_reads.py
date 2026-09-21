"""Run on tt-gpu against the real MCP and immutable DB snapshot; never locally."""
import asyncio,json,os,sys
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from editor import db
G=sys.argv[1];checks=[];responses={}
def check(name,ok):
 checks.append({'name':name,'passed':bool(ok)})
 if len(checks)%10==0:print(json.dumps({'completed':len(checks),'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks)}),file=sys.stderr,flush=True)
async def main():
 with db.tx() as c:
  c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
  ref=c.execute("SELECT content FROM current_artifact WHERE generation_id=%s AND kind='report'",(G,)).fetchone()['content']
  book_id=str(c.execute('SELECT bv.book_id FROM generation g JOIN book_version bv ON bv.id=g.book_version_id WHERE g.id=%s',(G,)).fetchone()['book_id'])
  state=c.execute('SELECT * FROM generation_state WHERE generation_id=%s',(G,)).fetchone()
  ready={r['kind'] for r in c.execute('SELECT kind FROM current_artifact WHERE generation_id=%s',(G,))}
  snap=c.execute('SELECT content FROM knowledge_snapshot WHERE generation_id=%s AND revision=%s ORDER BY created_at DESC LIMIT 1',(G,ref['revision'])).fetchone()['content']
 async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+os.environ['EDITOR_MCP_KEY']},timeout=90) as http:
  async with streamable_http_client('http://editor-mcp:8000/chat/mcp',http_client=http) as (read,write):
   async with ClientSession(read,write) as s:
    await s.initialize()
    names={t.name for t in (await s.list_tools()).tools}
    check('only seven bounded read tools',names=={'list_books','get_book_status','read_book_section','read_source_page','find_book_claims','search_book_evidence','get_book_summary'})
    async def call(name,args):
     r=await s.call_tool(name,args);check(name+' transport',not r.is_error)
     if r.is_error:raise RuntimeError(str(r.content))
     value=r.structured_content
     if value is None:value=json.loads(r.content[0].text)
     value=value.get('result',value)
     check(name+' payload bounded',len(json.dumps(value,ensure_ascii=False))<(32000 if name=='get_book_summary' else 20000))
     responses[name+json.dumps(args,sort_keys=True)]=value
     return value
    status=await call('get_book_status',{'book_id':book_id})
    check('status current ready kinds',set(status['current_outputs']['ready'])==ready)
    check('status current revision validation',status['current_outputs']['validation_complete']==(state['knowledge_revision']==state['validated_revision']))
    check('status analytical distinct from technical',status['current_outputs']['analytical_status']==state['semantic_status'] and status['semantic_acceptance'] is False)
    summary=await call('get_book_summary',{'generation_id':G})
    check('whole summary present',summary['sentences']==[{'text':x['text'],'pages':x['pages']} for x in ref['book_summary']])
    check('complete summary is not analytical acceptance',summary['stored_summary_complete'] and summary['semantic_acceptance'] is False)
    for section,expected in [('summary',ref['book_summary']),('events',snap['events']),('claims',snap['claims'])]:
     rows=[];offset=0
     while True:
      v=await call('read_book_section',{'generation_id':G,'section':section,'limit':3,'offset':offset})
      check(section+' same revision',v['knowledge_revision']==ref['revision'])
      check(section+' not overstated acceptance',v['semantic_acceptance'] is False)
      rows+=v['records']
      if v['next_offset'] is None:break
      check(section+' advancing cursor',v['next_offset']>offset)
      offset=v['next_offset']
     check(section+' all rows exactly match independent snapshot',rows==expected)
    for page in (6,23,32):
     offset=0;rows=[]
     while True:
      v=await call('read_source_page',{'generation_id':G,'page_no':page,'offset':offset,'limit':3});rows+=v['records']
      if v['next_offset'] is None:break
      offset=v['next_offset']
     check('text source does not deny visuals',v['scope']=='TEXT_SOURCE_ONLY' and v['visual_records_included'] is False)
     spans=next(p for p in snap['sources'] if p['page_no']==page)['spans']
     for span in spans:
      got=[r for r in rows if r['span_id']==span['span_id']]
      check('p'+str(page)+' exact source text',''.join(r['text'] for r in got)==span['text'])
    for query in ('Baba Vombat','Yavru Vombat'):
     v=await call('find_book_claims',{'generation_id':G,'query':query})
     check(query+' real matches',v['total']>0)
    bad=await s.call_tool('read_book_section',{'generation_id':G,'limit':100000})
    check('oversized request rejected',bad.is_error)
 print(json.dumps({'generation_id':G,'code_version':os.environ.get('EDITOR_CODE_VERSION'),'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'checks':checks,'responses':responses},ensure_ascii=False,default=str))
 raise SystemExit(any(not c['passed'] for c in checks))
asyncio.run(main())
