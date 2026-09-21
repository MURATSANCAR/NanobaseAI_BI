"""Bounded, coalescing output rebuilds. Maintenance blocks all consumption.

A session lock serializes consumers. Atomic pointer publication compares the
captured revision; stale builds cannot acknowledge a newer queued revision.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import uuid

from . import db, foundation, outputs

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def code_version():
    return os.environ.get('EDITOR_CODE_VERSION','unknown')


class Superseded(RuntimeError):
    pass


def ensure_open(c, gid):
    foundation.assert_enabled(c)
    state = c.execute("SELECT s.*,g.sealed_at FROM ed.generation_state s JOIN ed.generation g "
        "ON g.id=s.generation_id WHERE s.generation_id=%s FOR UPDATE OF s", (gid,)).fetchone()
    if not state: raise KeyError(gid)
    if state['origin']!='TRACKED' or state['sealed_at'] is not None:
        raise ValueError('Legacy or sealed generation requires a new analysis generation')
    return state


def activate(gid: str):
    with db.tx() as c:
        state=ensure_open(c,gid)
        if state['producer_completed']:
            return
        c.execute("UPDATE ed.generation_state SET producer_completed=true WHERE generation_id=%s",(gid,))
        c.execute("INSERT INTO ed.rebuild_request(generation_id,requested_revision,reason) VALUES(%s,%s,'producers_completed') "
            "ON CONFLICT(generation_id) DO UPDATE SET requested_revision=EXCLUDED.requested_revision,"
            "completed_revision=LEAST(ed.rebuild_request.completed_revision,EXCLUDED.requested_revision-1),"
            "updated_at=now()",(gid,state['knowledge_revision']))


async def validate(gid: str) -> dict:
    from . import knowledge, quality
    token=str(uuid.uuid4())
    context=db.validation_token.set(token)
    try:
        start=db.one("SELECT knowledge_revision FROM ed.generation_state WHERE generation_id=%s",gid)['knowledge_revision']
        # Identity and visual work is performed before activate in the full workflow.
        # Repairs invalidate actor readings in the same transaction.
        critic=await quality.critic_pass(gid, recheck=True)
        actors=await knowledge.attribute_event_actors(gid)
        contradictions=await knowledge.detect_contradictions(gid)
        queued=await asyncio.to_thread(quality.contradictions_to_queue,gid)
        regression=await asyncio.to_thread(quality.run_regression_suite,gid)
        return {'critic':critic,'actors':actors,'contradictions':contradictions,'queued':queued,
                'regression_passed':regression['passed'],'writer_token':token,'start_revision':start}
    finally:
        db.validation_token.reset(context)


def freeze(gid: str, validation: dict) -> tuple[dict,str]:
    with db.tx() as c:
        state=ensure_open(c,gid)
        if not state['producer_completed']: raise ValueError('Canonical producers have not completed')
        external=c.execute("SELECT 1 FROM ed.knowledge_change WHERE generation_id=%s AND revision>%s "
            "AND writer_token IS DISTINCT FROM %s LIMIT 1",
            (gid,validation['start_revision'],validation['writer_token'])).fetchone()
        if external:
            raise Superseded('Concurrent correction during validation; validate the new revision again')
        snap=outputs.capture(c,gid)
        digest=foundation.digest_inputs(snap)
        c.execute("INSERT INTO ed.knowledge_snapshot(generation_id,revision,input_digest,content,validation) "
            "VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (gid,snap['revision'],digest,db.J(snap),db.J(validation)))
        c.execute("UPDATE ed.generation_state SET validated_revision=%s,publication_status='BLOCKED',"
            "coverage_status=%s,semantic_status='NEEDS_REVIEW' WHERE generation_id=%s",
            (snap['revision'],'PARTIAL' if any(b in snap['blockers'] for b in ('SOURCE_ISSUES','PAGE_ROLES_UNASSESSED')) else 'PASSED',gid))
        return snap,digest


def key_for(snap, digest, kind):
    return foundation.digest_inputs({'policy':outputs.POLICY,'snapshot':digest,'kind':kind,
        'revision':snap['revision'],'summary_prompt':outputs.SUMMARY_PROMPT,'critic_prompt':outputs.JUDGE_PROMPT})


def begin(snap: dict, digest: str, kind: str, key: str) -> dict | None:
    gid=snap['generation_id']
    with db.tx() as c:
        state=ensure_open(c,gid)
        if state['knowledge_revision']!=snap['revision'] or state['validated_revision']!=snap['revision']:
            raise Superseded('Knowledge changed before output build')
        old=c.execute("SELECT content FROM ed.artifact_version WHERE generation_id=%s AND kind=%s AND build_key=%s",
            (gid,kind,key)).fetchone()
        c.execute("UPDATE ed.derived_artifact SET state='BUILDING',input_revision=%s,build_key=%s,"
            "output_reference=NULL,updated_at=now() WHERE generation_id=%s AND kind=%s",
            (snap['revision'],key,gid,kind))
        return old['content'] if old else None


def publish(snap: dict, digest: str, kind: str, key: str, content: dict):
    gid=snap['generation_id']
    with db.tx() as c:
        state=ensure_open(c,gid)
        if state['knowledge_revision']!=snap['revision'] or state['validated_revision']!=snap['revision']:
            raise Superseded('Knowledge changed during output build; discarded')
        deps=c.execute("SELECT depends_on FROM ed.artifact_definition WHERE kind=%s",(kind,)).fetchone()['depends_on']
        for dep in deps:
            if dep=='knowledge': continue
            if c.execute("SELECT 1 FROM ed.current_artifact WHERE generation_id=%s AND kind=%s AND input_digest=%s",
                (gid,dep,digest)).fetchone() is None:
                raise Superseded('Dependency changed or is unavailable: '+dep)
        # Pointer replacement and downstream invalidation are one transaction.
        foundation.invalidate_dependents(c,gid,kind)
        c.execute("INSERT INTO ed.artifact_version(generation_id,kind,build_key,input_revision,input_digest,content) "
            "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (gid,kind,key,snap['revision'],digest,db.J(outputs.plain(content))))
        updated=c.execute("UPDATE ed.derived_artifact SET state='READY',input_revision=%s,build_key=%s,"
            "output_reference=%s,updated_at=now() WHERE generation_id=%s AND kind=%s AND build_key=%s",
            (snap['revision'],key,db.J({'build_key':key,'input_digest':digest}),gid,kind,key))
        if updated.rowcount != 1:
            raise Superseded('Output build token no longer owns the pointer')


def finish(snap,digest):
    gid=snap['generation_id']
    with db.tx() as c:
        state=ensure_open(c,gid)
        rows=c.execute("SELECT kind,input_revision,input_digest FROM ed.current_artifact WHERE generation_id=%s",(gid,)).fetchall()
        if state['knowledge_revision']!=snap['revision'] or {r['kind'] for r in rows}!=set(outputs.ORDER) \
                or any(r['input_digest']!=digest for r in rows):
            raise Superseded('Output set is incomplete or superseded')
        c.execute("UPDATE ed.rebuild_request SET completed_revision=%s,attempts=0,last_error=NULL,retry_after=NULL,"
            "updated_at=now() WHERE generation_id=%s AND requested_revision=%s",
            (snap['revision'],gid,snap['revision']))
        # Technical completion is not independent semantic acceptance — but a rebuild of a
        # revision an editor already accepted must not take that acceptance back.
        c.execute("UPDATE ed.generation_state SET publication_status='BLOCKED',semantic_status='NEEDS_REVIEW' "
            "WHERE generation_id=%s AND NOT EXISTS (SELECT 1 FROM ed.semantic_acceptance a WHERE "
            "a.generation_id=%s AND a.revision=%s)",(gid,gid,snap['revision']))
    return {'generation_id':gid,'revision':snap['revision'],'technical_status':'SUCCEEDED',
        'analytical_status':'NEEDS_REVIEW','accepted':False,'blockers':snap['blockers'],
        'artifacts':list(outputs.ORDER)}


def failed(gid,error):
    with db.tx() as c:
        c.execute("UPDATE ed.derived_artifact SET state='FAILED',updated_at=now() WHERE generation_id=%s AND state='BUILDING'",(gid,))
        c.execute("UPDATE ed.rebuild_request r SET attempts=CASE WHEN EXISTS (SELECT 1 FROM ed.knowledge_change k "
            "WHERE k.generation_id=r.generation_id AND k.revision>r.attempted_revision AND k.writer_token IS NULL) "
            "THEN 0 ELSE r.attempts END,last_error=%s,attempted_revision=requested_revision,"
            "retry_after=now()+interval '5 minutes',updated_at=now() "
            "WHERE generation_id=%s",(str(error)[:2000],gid))


async def build(kind,snap,built,key):
    if kind=='chapter_summaries':
        chapters=[]
        for ch in snap['chapters']:
            claims=[c for c in snap['claims'] if any(ch['page_from']<=p<=ch['page_to'] for p in c['source_pages'])]
            value=await outputs.summarize(snap,claims,ch['title'])
            chapters.append({**ch,**value})
        return {'chapters':chapters,'semantic_acceptance':False}
    if kind=='book_summary':
        # Chapter selection may omit late events. The book plot consumes the
        # complete verified event set of the same immutable revision.
        return await outputs.summarize(snap,snap['claims'],'Kitabın olay örgüsü özeti',plot_only=True)
    if kind=='search_index':
        from . import retrieval
        return await retrieval.embed_snapshot(snap,key)
    if kind=='report':
        return outputs.render_report(snap,built['chapter_summaries'],built['book_summary'])
    if kind=='catalog':
        return {'title':snap['title'],'generation_id':snap['generation_id'],'revision':snap['revision'],
            'summary':built['book_summary']['sentences'],
            'metadata':[c for c in snap['claims'] if c['kind']=='METADATA'],
            'themes':[c for c in snap['claims'] if c['kind']=='THEME'],
            'characters':snap['characters'],'events':snap['events'],
            'blockers':snap['blockers'],'semantic_acceptance':False}
    raise KeyError(kind)


async def run(gid: str) -> dict:
    # Kept on a dedicated connection for the whole async build; a process crash
    # releases it. Duplicate Temporal/daemon deliveries therefore cannot overlap.
    with db.pool().connection() as lock:
        acquired=lock.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok",('outputs:'+gid,)).fetchone()['ok']
        owner=lock.execute("SELECT pid,backend_start FROM pg_stat_activity WHERE pid=pg_backend_pid()").fetchone()
        lock.commit()
        if not acquired: return {'generation_id':gid,'technical_status':'BUSY'}
        try:
            with db.tx() as c:
                state=ensure_open(c,gid)
                if not state['producer_completed']: raise ValueError('Producers still running')
                request=c.execute("SELECT * FROM ed.rebuild_request WHERE generation_id=%s FOR UPDATE",(gid,)).fetchone()
                if request is None: raise ValueError('Missing rebuild request')
                if request['completed_revision']==state['knowledge_revision'] and state['validated_revision']==state['knowledge_revision'] and c.execute("SELECT count(*) AS n FROM ed.current_artifact a JOIN ed.knowledge_snapshot s ON s.generation_id=a.generation_id AND s.input_digest=a.input_digest WHERE a.generation_id=%s AND s.content->>'code_version'=%s AND s.content->>'policy'=%s",(gid,code_version(),outputs.POLICY)).fetchone()['n']==len(outputs.ORDER):
                    return {'generation_id':gid,'technical_status':'ALREADY_CURRENT','accepted':False}
                if request['attempted_revision']==state['knowledge_revision'] and request['attempted_code_version']==code_version() and request['attempts']>=MAX_ATTEMPTS:
                    raise ValueError('Rebuild retry budget exhausted')
                c.execute("UPDATE ed.rebuild_request SET consumer_backend_pid=%s,consumer_backend_start=%s WHERE generation_id=%s",
                    (owner['pid'],owner['backend_start'],gid))
                c.execute("UPDATE ed.rebuild_request SET attempts=CASE WHEN attempted_revision=%s AND attempted_code_version=%s "
                    "THEN attempts+1 ELSE 1 END,attempted_revision=%s,attempted_code_version=%s WHERE generation_id=%s",
                    (state['knowledge_revision'],code_version(),state['knowledge_revision'],code_version(),gid))
            # Model upgrades require an explicit new analysis generation. Never
            # silently rebuild a recorded profile using a different model revision.
            from .llm import aliases
            actual=await aliases()
            declared=db.one("SELECT model_manifest FROM ed.generation WHERE id=%s",gid)['model_manifest']
            for alias in ('book-director','book-embedding'):
                if any(actual.get(alias,{}).get(k)!=declared.get(alias,{}).get(k) for k in ('real_model','revision')):
                    raise ValueError('Model profile changed; create a new generation: '+alias)
            # On an artifact-only retry the verified immutable input remains usable.
            existing=db.one("SELECT s.content,s.input_digest FROM ed.knowledge_snapshot s JOIN ed.generation_state g "
                "ON g.generation_id=s.generation_id AND g.validated_revision=s.revision "
                "WHERE s.generation_id=%s AND g.knowledge_revision=s.revision ORDER BY s.created_at DESC LIMIT 1",gid)
            if existing and existing['content']['code_version']==os.environ.get('EDITOR_CODE_VERSION','unknown'):
                snap,digest=existing['content'],existing['input_digest']
            else:
                validation=await validate(gid)
                snap,digest=await asyncio.to_thread(freeze,gid,validation)
                # Validator writes may advance the revision. Charge retries to its
                # final revision too, so repeated model failures have a finite budget.
                db.one("UPDATE ed.rebuild_request SET attempted_revision=%s WHERE generation_id=%s RETURNING generation_id",snap['revision'],gid)
            built={}
            for kind in outputs.ORDER:
                key=key_for(snap,digest,kind)
                cached=await asyncio.to_thread(begin,snap,digest,kind,key)
                if cached is None:
                    cached=await build(kind,snap,built,key)
                await asyncio.to_thread(publish,snap,digest,kind,key,cached)
                built[kind]=cached
            return await asyncio.to_thread(finish,snap,digest)
        except Superseded as exc:
            # Queue already contains the newer revision; never mark it completed.
            return {'generation_id':gid,'technical_status':'SUPERSEDED','reason':str(exc),'accepted':False}
        except Exception as exc:
            await asyncio.to_thread(failed,gid,exc)
            raise
        finally:
            # Operational lease only; never touches book facts or model results.
            try:
                db.one("UPDATE ed.rebuild_request SET consumer_backend_pid=NULL,consumer_backend_start=NULL "
                    "WHERE generation_id=%s AND consumer_backend_pid=%s RETURNING generation_id",gid,owner['pid'])
            finally:
                lock.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))",('outputs:'+gid,))
                lock.commit()


def pending():
    with foundation.read_snapshot() as c:
        if c.execute("SELECT maintenance FROM ed.runtime_control WHERE singleton").fetchone()['maintenance']:
            return []
        return [str(r['generation_id']) for r in c.execute("SELECT r.generation_id FROM ed.rebuild_request r "
            "JOIN ed.generation_state s USING(generation_id) JOIN ed.generation g ON g.id=r.generation_id "
            "JOIN ed.analysis_job j ON j.id=g.job_id WHERE r.completed_revision<r.requested_revision "
            "AND s.origin='TRACKED' AND s.producer_completed AND g.sealed_at IS NULL "
            "AND j.status NOT IN ('QUEUED','RUNNING') AND (r.attempted_code_version IS DISTINCT FROM %s "
            "OR r.attempted_revision IS DISTINCT FROM r.requested_revision "
            "OR (r.attempts<%s AND (r.retry_after IS NULL OR r.retry_after<=now()))) ORDER BY r.updated_at LIMIT 1",(code_version(),MAX_ATTEMPTS))]


async def consume():
    while True:
        for gid in await asyncio.to_thread(pending):
            try: await run(gid)
            except Exception: log.exception('Output rebuild failed for %s',gid)
        await asyncio.sleep(15)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['consume','once'])
    parser.add_argument('--generation')
    args=parser.parse_args()
    if args.command=='consume': asyncio.run(consume())
    elif args.generation: print(json.dumps(asyncio.run(run(args.generation)),ensure_ascii=False))
    else: parser.error('--generation is required for once')


if __name__=='__main__': main()
