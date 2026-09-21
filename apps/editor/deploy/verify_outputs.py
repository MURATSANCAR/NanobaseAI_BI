"""Run only on tt-gpu: read-only real API / independent raw DB validation.
This does not simulate writes, crashes, races or model output with fixtures.
"""
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from editor import db
from editor.config import settings


def plain(value):
    return json.loads(json.dumps(value,default=str,ensure_ascii=False))


def request(path):
    req=urllib.request.Request('http://127.0.0.1:8000'+path,
        headers={'Authorization':'Bearer '+settings().gateway_internal_key})
    with urllib.request.urlopen(req,timeout=120) as r:
        assert r.status==200
        return json.load(r)


def state(c):
    tables=['claim','event','emotion','report','generation','evidence','model_call',
        'review_item','contradiction','regression_run','analysis_job','page_text',
        'generation_state','rebuild_request','derived_artifact','knowledge_snapshot','artifact_version']
    return {t:dict(c.execute(f"SELECT count(*) AS count,md5(string_agg(h,'' ORDER BY h)) AS md5 "
        f"FROM (SELECT md5(to_jsonb(t)::text) h FROM ed.{t} t) x").fetchone()) for t in tables}


def reference(c,gid):
    # Original tables only, not usable_* views or application snapshot helpers.
    pages={r['page_no'] for r in c.execute('SELECT p.page_no FROM ed.page p JOIN ed.generation g '
        'ON p.book_version_id=g.book_version_id WHERE g.id=%s',(gid,))}
    ev={r['id']:r for r in c.execute('SELECT * FROM ed.evidence WHERE generation_id=%s',(gid,))}
    regions={r['id'] for r in c.execute('SELECT id FROM ed.visual_region WHERE generation_id=%s',(gid,))}
    links={}
    for r in c.execute('SELECT ce.* FROM ed.claim_evidence ce JOIN ed.claim cl ON cl.id=ce.claim_id '
        'WHERE cl.generation_id=%s',(gid,)):
        links.setdefault(r['claim_id'],[]).append(r['evidence_id'])
    claims=[]
    for cl in c.execute('SELECT * FROM ed.claim WHERE generation_id=%s ORDER BY id',(gid,)):
        if cl['status'] not in {'VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED'} or cl['needs_editor_review']:
            continue
        if cl['kind'] in {'SUMMARY','ANSWER','AGE_GROUP','PUBLISHER_DECISION'}: continue
        if not set(cl['source_pages'])<=pages: continue
        es=[ev.get(eid) for eid in links.get(cl['id'],[])]
        if not es or any(e is None or e['page_no'] not in pages for e in es): continue
        if not any(e['quote_verified'] or (e['kind']=='VISUAL' and e['region_id'] in regions) for e in es): continue
        claims.append(cl)
    by_id={c['id']:c for c in claims}
    events=[e for e in c.execute('SELECT * FROM ed.event WHERE generation_id=%s ORDER BY page_from,id',(gid,))
        if e['claim_id'] in by_id and e['merged_into'] is None and e['summary']==by_id[e['claim_id']]['claim']]
    chars={r['id'] for r in c.execute('SELECT id FROM ed.character WHERE generation_id=%s',(gid,))}
    emotions=[]
    for e in c.execute('SELECT * FROM ed.emotion WHERE generation_id=%s ORDER BY page_no,id',(gid,)):
        cl=by_id.get(e['claim_id'])
        if cl and e['character_id'] in chars and cl['payload'].get('emotion')==e['emotion'] \
            and (cl['payload'].get('trigger') or '')==(e['trigger'] or '') and 'supersedes' not in cl['payload']:
            emotions.append(e)
    return plain({'claims':claims,'events':events,'emotions':emotions})


def main():
    assert request('/health')['maintenance'] is True
    results=[]
    with db.tx() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        c.execute("SET LOCAL statement_timeout='30s'")
        before=state(c)
        gens=c.execute('SELECT DISTINCT ON (book_version_id) id FROM ed.generation WHERE sealed_at IS NOT NULL '
            'ORDER BY book_version_id,sealed_at DESC').fetchall()
        for gen in gens:
            gid=str(gen['id'])
            plan=request(f'/v1/generations/{gid}/output-plan')
            snap=plan['snapshot']
            expected=reference(c,gid)
            for kind in ('claims','events','emotions'):
                assert snap[kind]==expected[kind],(gid,kind,'snapshot mismatch')
                results.append({'generation_id':gid,'check':kind,'count':len(expected[kind]),'status':'PASSED'})
            report=plan['report_preview']
            assert report['events']==expected['events'] and report['emotions']==expected['emotions']
            assert report['preview_only'] and report['summary_status']=='NOT_GENERATED'
            assert report['semantic_acceptance'] is False
            assert 'LEGACY_UNASSESSED' in report['blockers']
            assert plan['read_only'] and plan['model_calls']==0
            digest=hashlib.sha256(json.dumps(snap,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            assert digest==plan['input_digest']
            assert plan['order']==['chapter_summaries','book_summary','search_index','report','catalog']
            results.append({'generation_id':gid,'check':'report_snapshot_and_digest','status':'PASSED','sha256':digest})
            for kind in plan['order']:
                out=request(f'/v1/generations/{gid}/artifacts/{kind}')
                assert out['available'] is False and out['artifact'] is None and out['semantic_acceptance'] is False
                results.append({'generation_id':gid,'check':'no_current_'+kind,'status':'PASSED'})
                if len(results)%10==0:
                    print(json.dumps({'completed':len(results),'passed':len(results),'failed':0}),flush=True)
        names={r['tgname'] for r in c.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
            "AND tgrelid IN ('ed.event'::regclass,'ed.character'::regclass,'ed.generation_state'::regclass,"
            "'ed.knowledge_snapshot'::regclass,'ed.artifact_version'::regclass)")}
        assert {'reset_changed_event_actors','reset_changed_character_actors','output_validation_reset',
                'guard_output_version','immutable_snapshot','immutable_artifact'}<=names
        assert c.execute("SELECT count(*) n FROM ed.current_artifact").fetchone()['n']==0
    with db.tx() as c:
        c.execute('SET TRANSACTION READ ONLY')
        after=state(c)
    assert before==after,'Read-only verification mutated data'
    result={'code_version':os.environ.get('EDITOR_CODE_VERSION'),'api':'tt-gpu/editor-control:8000',
        'database':'tt-gpu/editor-postgres/editor/ed','books':len(gens),'passed':len(results),'failed':0,
        'results':results,'tables_unchanged':True,'table_state':after,'maintenance':True,
        'installed_trigger_definitions':sorted(names),
        'not_verified':['new workflow model execution','correction and automatic rebuild',
            'crash retry and concurrent correction fencing','Qdrant staged index publication',
            'full-book analytical acceptance']}
    Path('/tmp/output-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
