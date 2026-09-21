"""Run only on tt-gpu: actual HTTP/MCP reads vs independent real ledger references."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

import httpx
from editor import db
from editor.config import settings

GID = '3a987c80-95ba-48ce-a08e-820425cf438d'
checks, responses = [], {}


def plain(x):
    return json.loads(json.dumps(x, default=str, ensure_ascii=False))


def check(label, actual, expected):
    checks.append({'check': label, 'passed': plain(actual) == plain(expected)})
    if not checks[-1]['passed']:
        checks[-1].update(actual=plain(actual), expected=plain(expected))
    if len(checks) % 10 == 0:
        print(json.dumps({'completed': len(checks), 'passed': sum(x['passed'] for x in checks),
                          'failed': sum(not x['passed'] for x in checks)}), file=sys.stderr, flush=True)


with db.tx() as c:
    c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    gens = c.execute('SELECT DISTINCT ON (v.book_id) g.*,v.book_id FROM ed.generation g '
        'JOIN ed.book_version v ON v.id=g.book_version_id ORDER BY v.book_id,g.created_at DESC,g.id DESC').fetchall()
    state = c.execute('SELECT * FROM ed.generation_state WHERE generation_id=%s', (GID,)).fetchone()
    pointers = c.execute('SELECT * FROM ed.derived_artifact WHERE generation_id=%s', (GID,)).fetchall()
    versions = {r['kind']: r for r in c.execute('SELECT v.* FROM ed.artifact_version v '
        'JOIN ed.derived_artifact a ON (a.generation_id,a.kind,a.build_key)=(v.generation_id,v.kind,v.build_key) '
        "WHERE v.generation_id=%s AND a.state='READY' AND a.input_revision=%s AND v.input_revision=%s",
        (GID, state['knowledge_revision'], state['knowledge_revision']))}
    check('validated revision equals knowledge', state['validated_revision'], state['knowledge_revision'])
    snap = c.execute('SELECT content FROM ed.knowledge_snapshot WHERE generation_id=%s AND revision=%s '
        'AND input_digest=%s', (GID,state['knowledge_revision'],versions['report']['input_digest'])).fetchone()['content']
    claims = c.execute('SELECT * FROM ed.claim WHERE generation_id=%s ORDER BY id', (GID,)).fetchall()
    events = c.execute('SELECT * FROM ed.event WHERE generation_id=%s ORDER BY id', (GID,)).fetchall()
    emotions = c.execute('SELECT * FROM ed.emotion WHERE generation_id=%s ORDER BY id', (GID,)).fetchall()
    chars = c.execute('SELECT * FROM ed.character WHERE generation_id=%s ORDER BY id', (GID,)).fetchall()
    actors = c.execute('SELECT * FROM ed.event_actor WHERE generation_id=%s ORDER BY event_id,p_actor DESC,character_id', (GID,)).fetchall()
    mentions = c.execute('SELECT cm.*,e.quote,e.kind,e.source_refs,e.page_no AS evidence_page,e.region_id,e.quote_verified '
        'FROM ed.character_mention cm JOIN ed.evidence e ON e.id=cm.evidence_id '
        'WHERE cm.generation_id=%s AND e.generation_id=cm.generation_id ORDER BY cm.page_no,cm.id', (GID,)).fetchall()
    regions = {(str(r['id']),r['page_no']) for r in c.execute('SELECT id,page_no FROM ed.visual_region WHERE generation_id=%s',(GID,))}
    old_reports = c.execute('SELECT generation_id,count(*) n FROM ed.report GROUP BY generation_id').fetchall()
    before_calls = c.execute('SELECT count(*) n FROM ed.model_call').fetchone()['n']

allowed = {r['id'] for r in snap['claims']}
check('snapshot statuses and review flags', all(str(r['id']) not in allowed or
    (r['status'] in ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED') and not r['needs_editor_review']) for r in claims), True)
canonical_events = [plain(e) for e in events if str(e['claim_id']) in allowed and not e['merged_into']
    and any(cl['id'] == e['claim_id'] and cl['claim'] == e['summary'] for cl in claims)]
canonical_emotions = [plain(e) for e in emotions if str(e['claim_id']) in allowed and any(
    cl['id'] == e['claim_id'] and cl['payload'].get('emotion') == e['emotion'] and
    (cl['payload'].get('trigger') or '') == (e['trigger'] or '') and 'supersedes' not in cl['payload'] for cl in claims)
    and any(ch['id'] == e['character_id'] for ch in chars)]
check('snapshot events vs canonical base rows', sorted(snap['events'], key=lambda r:r['id']),canonical_events)
check('snapshot emotions vs canonical base rows', sorted(snap['emotions'],key=lambda r:r['id']),canonical_emotions)

with httpx.Client(base_url='http://127.0.0.1:8000', timeout=60,
                  headers={'Authorization':'Bearer '+settings().gateway_internal_key}) as client:
    def get(path, **params):
        r = client.get(path, params=params)
        responses[path + '?' + json.dumps(params,sort_keys=True)] = {'status':r.status_code,'body':r.json()}
        return r
    prefix=f'/v1/generations/{GID}'
    for kind in ('claims','events','emotions'):
        rows = sorted(snap[kind], key=lambda r:r['id'])
        collected=[]
        for offset in range(0,max(len(rows),1),25):
            v=get(prefix+'/records/'+kind,limit=25,offset=offset).json()
            check(f'{kind}:{offset}:page',v['records'],rows[offset:offset+25])
            check(f'{kind}:{offset}:total',v['total'],len(rows))
            check(f'{kind}:{offset}:truncated',v['truncated'],offset+len(v['records'])<len(rows))
            collected+=v['records']
        check(kind+':complete answer',collected,rows)
    report=get(prefix+'/report').json()
    check('report full content',report['content'],versions['report']['content'])
    check('report markdown',report['markdown'],versions['report']['content']['markdown'])
    check('unsupported report kind',get(prefix+'/report',kind='PUBLISHER').json()['available'],False)
    tl=get(prefix+'/timeline').json()
    expected_tl=[{**e,'knowledge_revision':state['knowledge_revision'],'semantic_acceptance':False} for e in sorted(
        [e for e in canonical_events if e['modality'] in ('REALIZED','MEMORY')],
        key=lambda e:(e['story_order'] is None,e['story_order'] or 0,e['page_from'],e['id']))]
    check('timeline full result',tl,expected_tl)
    expected_actors=[]
    for e in snap['events']:
        pairs=[]
        for a in actors:
            if str(a['event_id'])!=e['id'] or a['role']=='ABSENT': continue
            ch=next(ch for ch in chars if ch['id']==a['character_id'])
            pairs.append({'character_id':str(ch['id']),'character':ch['canonical_name'],
                'identity_status':ch['identity_status'],'role':a['role'],
                'p_actor':round(a['p_actor'],3),'p_involved':round(a['p_involved'],3)})
        expected_actors.append({'event_id':e['id'],'page_from':e['page_from'],'page_to':e['page_to'],
            'modality':e['modality'],'summary':e['summary'],'extractor_participants':e['participants'],
            'knowledge_revision':state['knowledge_revision'],'semantic_acceptance':False,'characters':pairs})
    check('actor full result',get(prefix+'/actors').json(),expected_actors)
    # Independent exact source comparison uses stored PDF/OCR spans in the validated source snapshot.
    import unicodedata
    def norm(t):
        import re
        t=unicodedata.normalize('NFKC',t or '').translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"'}))
        t=re.sub(r'(\w)[-\u00ad]\s+(\w)',r'\1\2',t)
        return ' '.join(t.split()).casefold()
    for ch in chars:
        v=get(prefix+'/characters/history',name=ch['canonical_name']).json()
        selected=[x for x in chars if x['canonical_name'].lower()==ch['canonical_name'].lower() or
                  ch['canonical_name'].lower() in [a.lower() for a in x['aliases']]]
        ids={str(x['id']) for x in selected if x['identity_status']=='CONFIRMED'}
        check(ch['canonical_name']+':identity ids',sorted(x['id'] for x in v['characters']),sorted(str(x['id']) for x in selected))
        check(ch['canonical_name']+':emotions',v['emotions'],[e for e in snap['emotions'] if e['character_id'] in ids])
        expected=[]
        for e in snap['events']:
            linked=[str(a['character_id']) for a in actors if str(a['event_id'])==e['id'] and
                    str(a['character_id']) in ids and a['role'] in ('ACTOR','INVOLVED')]
            if linked: expected.append({**e,'matched_character_ids':linked})
        check(ch['canonical_name']+':events',v['events'],expected)
        eligible_mentions=[]
        for m in mentions:
            if str(m['character_id']) not in ids or m['resolution']!='RESOLVED' or m['page_no']!=m['evidence_page']:continue
            refs=m['source_refs'] or {}
            ok=m['kind']=='VISUAL' and (str(m['region_id']),m['page_no']) in regions
            if m['kind']!='VISUAL' and m['quote_verified'] and refs.get('generation_id')==GID and refs.get('page_no')==m['page_no']:
                page=next(p for p in snap['sources'] if p['page_no']==m['page_no'])
                ok=any(s['span_id']==r.get('span_id') and s['source_sha256']==r.get('source_sha256') and
                    norm(m['quote']) and norm(m['quote']) in norm(s['text']) for s in page['spans'] for r in refs.get('spans',[]))
            if ok: eligible_mentions.append({k:m[k] for k in ('id','character_id','page_no','surface_name','via','resolution','confidence','quote')})
        check(ch['canonical_name']+':mentions',v['mentions'],eligible_mentions)
    check('name wildcards do not match identities',get(prefix+'/characters/history',name='%').json()['characters'],[])
    for gen in gens:
        gid=str(gen['id']);book_id=str(gen['book_id'])
        card=get(f'/v1/books/{book_id}/card').json()
        check(book_id+':latest generation',card['generation_id'],gid)
        if gid==GID:
            check('card summary full',card['summary'],versions['catalog']['content']['summary'])
            check('card events full',card['key_events'],versions['catalog']['content']['events'])
            check('card character ids',sorted(x['id'] for x in card['characters']),sorted(str(x['id']) for x in chars))
            for ch in card['characters']:
                original=next(x for x in chars if str(x['id'])==ch['id'])
                desc=next((cl['claim'] for cl in claims if cl['id']==original['claim_id'] and str(cl['id']) in allowed),None)
                check(ch['canonical_name']+':card description quality',ch['description'],desc)
        else:
            check(book_id+':legacy card unavailable',card['available'],False)
            check(book_id+':no old summary',card['summary'],[])
            check(gid+':legacy report unavailable',get(f'/v1/generations/{gid}/report').json()['available'],False)
            for route in ('timeline','actors','characters/history'):
                check(gid+':'+route+':not empty success',get(f'/v1/generations/{gid}/'+route,**({'name':'Vombat'} if route.endswith('history') else {})).status_code,409)
            for kind in ('claims','events','emotions'):
                r=get(f'/v1/generations/{gid}/records/{kind}').json()
                check(gid+':'+kind+':unavailable', [r['available'],r['total'],r['records']],[False,None,[]])
    # Real previous generation has reports but must never become fallback.
    old='3c63c8ea-7f72-42ad-8c60-186d2462a171'
    check('historical real report exists',any(str(r['generation_id'])==old and r['n'] for r in old_reports),True)
    check('historical real report blocked',get(f'/v1/generations/{old}/report').json()['available'],False)

with db.tx() as c:
    check('read endpoints create no model calls',c.execute('SELECT count(*) n FROM ed.model_call').fetchone()['n'],before_calls)

result={'code_version':os.environ.get('EDITOR_CODE_VERSION'),'generation_id':GID,'revision':state['knowledge_revision'],
        'environment':'tt-gpu / editor-control HTTP / real Editor PostgreSQL',
        'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),
        'checks':checks,'responses':responses}
print(json.dumps(plain(result),ensure_ascii=False))
sys.exit(bool(result['failed']))
