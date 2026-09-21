"""Real MCP transport acceptance on tt-gpu; two bounded model queries, no book scan."""
import asyncio
import json
import os
import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from editor import db
from editor.config import settings

GID='3a987c80-95ba-48ce-a08e-820425cf438d'
OLD='3c63c8ea-7f72-42ad-8c60-186d2462a171'
BOOK='d2d4a6f1-e5b3-4415-9d68-48f8fe768c03'
checks=[]; answers={}

def normalized(x):
    # MCP encodes UTC as Z; FastAPI uses +00:00. Compare the same instant, all other values unchanged.
    from datetime import datetime
    if isinstance(x, list): return [normalized(v) for v in x]
    if isinstance(x, dict):
        return {k: datetime.fromisoformat(v.replace('Z','+00:00')).isoformat()
                if k == 'created_at' and isinstance(v,str) else normalized(v) for k,v in x.items()}
    return x


def check(name,ok):
    checks.append({'check':name,'passed':bool(ok)})

async def call(server,name,args):
    async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+os.environ['EDITOR_MCP_KEY']},timeout=900) as http:
        async with streamable_http_client(f'http://editor-mcp:8000/{server}/mcp',http_client=http) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                r=await session.call_tool(name,args)
                answers[name+json.dumps(args,sort_keys=True)] = r.model_dump(mode='json')
                return r

def value(r):
    x=r.structured_content
    if x is not None:
        return x.get('result',x) if isinstance(x,dict) else x
    texts=[json.loads(t.text) for t in r.content if t.type=='text']
    return texts[0] if len(texts)==1 else texts

async def main():
    with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+settings().gateway_internal_key}) as http:
        for server,name,args,path,params in [
            ('jobs','get_report',{'generation_id':GID},f'/v1/generations/{GID}/report',{}),
            ('knowledge','build_timeline',{'generation_id':GID},f'/v1/generations/{GID}/timeline',{}),
            ('knowledge','get_event_actors',{'generation_id':GID},f'/v1/generations/{GID}/actors',{}),
            ('retrieval','search_character_history',{'generation_id':GID,'name':'Yavru Vombat'},f'/v1/generations/{GID}/characters/history',{'name':'Yavru Vombat'}),
            ('retrieval','get_book_card',{'book_id':BOOK},f'/v1/books/{BOOK}/card',{}),
        ]:
            r=await call(server,name,args)
            check(name+':transport',not r.is_error)
            check(name+':same full HTTP answer',normalized(value(r))==normalized(http.get(path,params=params).json()))
        for server,name in [('knowledge','build_timeline'),('knowledge','get_event_actors'),('retrieval','search_book_evidence')]:
            args={'generation_id':OLD}
            if name=='search_book_evidence':args['query']='Bilim Vombatı'
            r=await call(server,name,args)
            check(name+':legacy blocked',r.is_error)
        r=await call('jobs','get_report',{'generation_id':OLD})
        check('legacy report explicitly unavailable',not r.is_error and value(r)['available'] is False)
    old=db.one('SELECT maintenance,reason FROM runtime_control WHERE singleton')
    try:
        # No worker/rebuild is running. Only this bounded search acceptance opens model calls.
        db.one("UPDATE runtime_control SET maintenance=false,reason='Bounded read search acceptance; workers stopped',updated_at=now() WHERE singleton RETURNING singleton")
        r=await call('retrieval','search_books',{'query':'Merak edip araştıran bir yavrunun bilimle tanışması','k':5})
        check('catalog search transport',not r.is_error)
        rows=value(r) if not r.is_error else []
        check('catalog search real available book',bool(rows) and all(x['book_id']==BOOK and x['generation_id']==GID for x in rows))
        for row in rows:
            ref=db.one("SELECT v.content,v.build_key FROM artifact_version v JOIN derived_artifact a USING(generation_id,kind,build_key) JOIN generation_state s USING(generation_id) WHERE v.generation_id=%s AND v.kind='catalog' AND a.state='READY' AND v.input_revision=s.knowledge_revision AND s.validated_revision=s.knowledge_revision",GID)
            check('catalog search current pointer',row['card_id']==ref['build_key'])
            check('catalog search full summary',row['summary']==ref['content']['summary'])
            check('catalog search full events',row['key_events']==ref['content']['events'])
        r=await call('retrieval','search_book_evidence',{'generation_id':GID,'query':'Yavru Vombat annesi Bilim Vombatı tanımı','k':8,'kinds':['event']})
        check('book evidence search transport',not r.is_error)
        rows=value(r) if not r.is_error else []
        ref=db.all_rows("SELECT e.id,e.summary,e.page_from FROM event e JOIN claim c ON c.id=e.claim_id WHERE e.generation_id=%s AND c.status IN ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED') AND NOT c.needs_editor_review AND e.summary=c.claim AND e.merged_into IS NULL",GID)
        byid={str(x['id']):x for x in ref}
        check('every search passage current canonical text',bool(rows) and all(x['ref'].removeprefix('event:') in byid and x['text']==byid[x['ref'].removeprefix('event:')]['summary'] and x['page']==byid[x['ref'].removeprefix('event:')]['page_from'] for x in rows))
        check('corrected mother event retrieved',any(x['ref']=='event:edbb7da8-9435-467a-bf78-88a189936ddb' for x in rows))
    finally:
        db.one('UPDATE runtime_control SET maintenance=%s,reason=%s,updated_at=now() WHERE singleton RETURNING singleton',old['maintenance'],old['reason'])
    return {'code_version':os.environ.get('EDITOR_CODE_VERSION'),'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'checks':checks,'answers':answers}

result=asyncio.run(main())
print(json.dumps(result,ensure_ascii=False,default=str))
raise SystemExit(bool(result['failed']))
