"""Headless editor workflow; operator-only pilot access, no public endpoints."""
import json
import os
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb
from editor.config import connection, RELEASE
from editor.book_store import ROOT, sha, source_for, save_record

router=APIRouter(prefix='/v1')
from editor.access import actor_id, idempotency_actor, principal, admin, require_write, write_scope, touched_works, ensure_work, visible_works


class Upload(BaseModel):
    expected_bytes:int=Field(gt=0,le=52428800)
    expected_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


@router.post('/editions/{edition}/uploads',status_code=201)
def upload_session(edition:uuid.UUID,body:Upload,idempotency_key:str=Header()):
    def action(db):
        e=db.execute('SELECT work_id FROM editor.editions WHERE id=%s',(edition,)).fetchone()
        if not e: raise HTTPException(404,'Kayıt bulunamadı')
        own_work(db,e['work_id']); rid=str(uuid.uuid4())
        db.execute('INSERT INTO editor.uploads(id,edition_id,expected_bytes,expected_sha256) VALUES (%s,%s,%s,%s)',(rid,edition,body.expected_bytes,body.expected_sha256))
        return {'id':rid,'upload_url':'/v1/uploads/'+rid+'/content'}
    return mutate('/editions/'+str(edition)+'/uploads',body,idempotency_key,action)


def authorized_upload(db,upload):
    row=db.execute('SELECT u.*,e.work_id FROM editor.uploads u JOIN editor.editions e ON e.id=u.edition_id WHERE u.id=%s',(upload,)).fetchone()
    if not row: raise HTTPException(404,'Kayıt bulunamadı')
    own_work(db,row['work_id']); return row


@router.put('/uploads/{upload}/content')
async def upload_bytes(upload:uuid.UUID,request:Request):
    with connection() as db:
        row=authorized_upload(db,upload)
        ensure_work(db,row['work_id'],write=True)
    if row['status']=='COMPLETED': return {'id':str(upload),'status':'COMPLETED'}
    if row['status'] not in ('CREATED','RECEIVED'): raise HTTPException(409,'UPLOAD_SEALED')
    directory=ROOT/'uploads'; directory.mkdir(exist_ok=True)
    temporary=directory/(str(upload)+'.'+str(uuid.uuid4())+'.part'); destination=directory/(str(upload)+'.pdf')
    size=0
    try:
        with temporary.open('xb') as stream:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>row['expected_bytes']: raise HTTPException(413,'SOURCE_LIMIT_EXCEEDED')
                stream.write(chunk)
        if size!=row['expected_bytes']: raise HTTPException(409,'INCOMPLETE_UPLOAD')
        if sha(temporary.read_bytes())!=row['expected_sha256']: raise HTTPException(409,'SOURCE_HASH_MISMATCH')
        with temporary.open('rb') as stream:
            if stream.read(5)!=b'%PDF-': raise HTTPException(415,'INVALID_PDF')
        with connection() as db:
            locked=db.execute('SELECT status FROM editor.uploads WHERE id=%s FOR UPDATE',(upload,)).fetchone()
            if locked['status'] not in ('CREATED','RECEIVED'): raise HTTPException(409,'UPLOAD_SEALED')
            temporary.replace(destination)
            db.execute("UPDATE editor.uploads SET status='RECEIVED' WHERE id=%s",(upload,))
    finally:
        temporary.unlink(missing_ok=True)
    return {'id':str(upload),'status':'RECEIVED','bytes':size}


class CompleteUpload(BaseModel):
    confirm:Literal[True]=True


@router.post('/uploads/{upload}/complete',status_code=201)
def complete_upload(upload:uuid.UUID,body:CompleteUpload,idempotency_key:str=Header()):
    def action(db):
        authorized_upload(db,upload)
        db.execute('SELECT id FROM editor.uploads WHERE id=%s FOR UPDATE',(upload,))
        row=authorized_upload(db,upload)
        if row['status'] in ('FAILED','CANCELLED'):
            raise HTTPException(409,row['error_code'] or 'SOURCE_PARSE_CANCELLED')
        if row['status']=='COMPLETED':
            source=db.execute('SELECT manifest FROM editor.source_probes WHERE sha256=%s',(row['expected_sha256'],)).fetchone()
            return {'id':str(row['content_version_id']),'upload_id':str(upload),
                    'sha256':row['expected_sha256'],'pages':source['manifest']['pdf_pages']}
        path=ROOT/'uploads'/(str(upload)+'.pdf')
        if not path.exists() or path.stat().st_size!=row['expected_bytes']: raise HTTPException(409,'INCOMPLETE_UPLOAD')
        if sha(path.read_bytes())!=row['expected_sha256']: raise HTTPException(409,'SOURCE_HASH_MISMATCH')
        from editor.parse_contract import QUEUE, atomic_json
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('editor:parser-admission',0))")
        count=db.execute("SELECT count(*) AS n FROM editor.uploads WHERE status='PARSING' AND id!=%s",(upload,)).fetchone()['n']
        if count>=2: raise HTTPException(429,'SOURCE_PARSE_CAPACITY_FULL')
        request_path=QUEUE/(str(upload)+'.request.json')
        if not request_path.exists():
            atomic_json(request_path,{'sha256':row['expected_sha256'],'bytes':row['expected_bytes']})
        db.execute("UPDATE editor.uploads SET status='PARSING' WHERE id=%s AND status IN ('CREATED','RECEIVED')",(upload,))
        return {'id':str(upload),'job_id':str(upload),'status':'PARSING','status_url':'/v1/uploads/'+str(upload)}
    result=mutate('/uploads/'+str(upload)+'/complete',body,idempotency_key,action)
    return JSONResponse(result,status_code=202) if result.get('status')=='PARSING' else result


@router.get('/uploads/{upload}')
def upload_status(upload:uuid.UUID):
    with connection() as db: row=authorized_upload(db,upload)
    result={'id':str(upload),'status':row['status'],
            'work_id':str(row['work_id']),
            'content_version_id':str(row['content_version_id']) if row['content_version_id'] else None}
    if row['status']=='FAILED':
        result['error_code']=row['error_code']
    if row['status']=='PARSING':
        from editor.parse_contract import QUEUE
        path=QUEUE/(str(upload)+'.status.json')
        if path.exists(): result['progress']=json.loads(path.read_text())
    return result


@router.get('/uploads')
def recent_uploads(offset:int=0,limit:int=50):
    if offset<0 or not 1<=limit<=100: raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        rows=db.execute('''SELECT u.id,u.status,w.title FROM editor.uploads u
            JOIN editor.editions e ON e.id=u.edition_id JOIN editor.works w ON w.id=e.work_id
            WHERE w.id=ANY(%s::uuid[]) ORDER BY u.created_at DESC,u.id DESC LIMIT %s OFFSET %s''',(visible_works(db),limit+1,offset)).fetchall()
    return {'items':rows[:limit],'has_more':len(rows)>limit}


class Work(BaseModel):
    title: str=Field(min_length=1,max_length=300)


class Edition(BaseModel):
    work_id: uuid.UUID
    label: str=Field(min_length=1,max_length=200)


class Source(BaseModel):
    sha256: str=Field(pattern=r'^[a-f0-9]{64}$')


def mutate(path,body,key,fn):
    if path!='/questions': require_write()
    if not key or len(key)>200: raise HTTPException(400,'Idempotency-Key gerekli')
    fingerprint=sha((path+body.model_dump_json(exclude_none=True)).encode())
    with connection() as db:
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(idempotency_actor()+key,))
        old=db.execute('SELECT * FROM editor.idempotency WHERE actor_id=%s AND key=%s',(idempotency_actor(),key)).fetchone()
        if old:
            if old['request_hash']!=fingerprint: raise HTTPException(409,'IDEMPOTENCY_CONFLICT')
            for work in old['required_work_ids']:ensure_work(db,work,write=path!='/questions')
            return old['response']
        context=write_scope.set(path!='/questions')
        touched=touched_works.set(frozenset())
        try:
            result=fn(db)
            required=list(touched_works.get())
        finally:
            write_scope.reset(context)
            touched_works.reset(touched)
        db.execute('INSERT INTO editor.idempotency(actor_id,key,request_hash,response,required_work_ids) VALUES (%s,%s,%s,%s,%s)',(idempotency_actor(),key,fingerprint,Jsonb(result),required))
        return result


def own_work(db,work):
    ensure_work(db,work)


def scope(db,generation):
    row=db.execute('''SELECT g.*,w.id AS work_id FROM editor.generations g
      JOIN editor.content_versions cv ON cv.id=g.content_version_id JOIN editor.editions e ON e.id=cv.edition_id
      JOIN editor.works w ON w.id=e.work_id WHERE g.id=%s''',(generation,)).fetchone()
    if not row: raise HTTPException(404,'Kayıt bulunamadı')
    ensure_work(db,row['work_id'])
    return row


@router.post('/works',status_code=201)
def create_work(body:Work,idempotency_key:str=Header()):
    if principal().work_ids is not None: raise HTTPException(403,'Yeni kitap oluşturma kapsamı yok')
    def create(db):
        rid=str(uuid.uuid4()); db.execute('INSERT INTO editor.works(id,title,owner_id) VALUES (%s,%s,%s)',(rid,body.title,actor_id())); return {'id':rid,'title':body.title}
    return mutate('/works',body,idempotency_key,create)


@router.get('/works')
def list_works(offset:int=0,limit:int=50):
    if offset<0 or not 1<=limit<=100: raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        rows=db.execute('SELECT id,title FROM editor.works WHERE id=ANY(%s::uuid[]) ORDER BY title,id LIMIT %s OFFSET %s',
                        (visible_works(db),limit,offset)).fetchall()
        total=db.execute('SELECT count(*) AS n FROM editor.works WHERE id=ANY(%s::uuid[])',(visible_works(db),)).fetchone()['n']
    return {'items':rows,'total':total,'has_more':offset+len(rows)<total}


@router.get('/works/{work}/analyses')
def list_analyses(work:uuid.UUID,offset:int=0,limit:int=50):
    if offset<0 or not 1<=limit<=100: raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        own_work(db,work)
        rows=db.execute('''SELECT j.id,j.generation_id,j.status,j.created_at,e.label AS edition_label
          FROM editor.jobs j JOIN editor.generations g ON g.id=j.generation_id
          JOIN editor.content_versions cv ON cv.id=g.content_version_id JOIN editor.editions e ON e.id=cv.edition_id
          WHERE e.work_id=%s AND j.task='analysis' ORDER BY j.created_at DESC,j.id DESC LIMIT %s OFFSET %s''',
          (work,limit+1,offset)).fetchall()
    return {'items':rows[:limit],'has_more':len(rows)>limit}


@router.post('/editions',status_code=201)
def create_edition(body:Edition,idempotency_key:str=Header()):
    def create(db):
        own_work(db,body.work_id); rid=str(uuid.uuid4())
        db.execute('INSERT INTO editor.editions(id,work_id,label) VALUES (%s,%s,%s)',(rid,body.work_id,body.label)); return {'id':rid}
    return mutate('/editions',body,idempotency_key,create)


@router.post('/editions/{edition}/verified-sources',status_code=201)
def attach_source(edition:uuid.UUID,body:Source,idempotency_key:str=Header()):
    # Existing networkless parser output is attached only after original/hash verification.
    # An SHA guess must never grant another user's source to an editor's own book.
    admin()
    def create(db):
        e=db.execute('SELECT work_id FROM editor.editions WHERE id=%s',(edition,)).fetchone()
        if not e: raise HTTPException(404,'Kayıt bulunamadı')
        own_work(db,e['work_id'])
        row=db.execute('SELECT manifest FROM editor.source_probes WHERE sha256=%s',(body.sha256,)).fetchone()
        if not row or not row['manifest']['source_accounting_complete']: raise HTTPException(409,'SOURCE_NOT_READY')
        if sha((ROOT/body.sha256/'original.pdf').read_bytes())!=body.sha256: raise HTTPException(409,'SOURCE_HASH_MISMATCH')
        rid=str(uuid.uuid4())
        r=db.execute('''INSERT INTO editor.content_versions(id,edition_id,sha256) VALUES (%s,%s,%s)
          ON CONFLICT(edition_id,sha256) DO UPDATE SET sha256=excluded.sha256 RETURNING id''',(rid,edition,body.sha256)).fetchone()
        return {'id':str(r['id']),'sha256':body.sha256,'pages':row['manifest']['pdf_pages']}
    return mutate('/editions/'+str(edition)+'/verified-sources',body,idempotency_key,create)


class AnalysisRequest(BaseModel):
    purpose: Literal['validation']='validation'
    reuse_measurements_from: uuid.UUID|None=None


@router.post('/content-versions/{version}/analyses',status_code=202)
def start(version:uuid.UUID,body:AnalysisRequest,idempotency_key:str=Header()):
    def create(db):
        row=db.execute('SELECT e.work_id FROM editor.content_versions cv JOIN editor.editions e ON e.id=cv.edition_id WHERE cv.id=%s',(version,)).fetchone()
        if not row: raise HTTPException(404,'Kayıt bulunamadı')
        own_work(db,row['work_id'])
        if db.execute("SELECT id FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')").fetchone(): raise HTTPException(429,'ANALYSIS_CAPACITY_FULL')
        if body.reuse_measurements_from:
            parent=scope(db,body.reuse_measurements_from)
            if parent['content_version_id']!=version: raise HTTPException(409,'REUSED_CONTENT_VERSION_MISMATCH')
            if parent['manifest'].get('pipeline_version') not in ('source-spans-v1','source-spans-v2','source-spans-v3','source-spans-v4','source-spans-v5','source-spans-v6'):
                raise HTTPException(409,'REUSED_PIPELINE_UNSUPPORTED')
        gen=str(uuid.uuid4()); job=str(uuid.uuid4())
        from editor.source_pipeline import VERSION
        manifest={'release':RELEASE,'pipeline_version':VERSION,'mode':'validation','human_accepted':False,
          'reuse_measurements_from':str(body.reuse_measurements_from) if body.reuse_measurements_from else None,
          'model':'Qwen3.8-27B-Q4_K_M','image_max_tokens':int(os.environ.get('EDITOR_IMAGE_MAX_TOKENS','1024')),
          'context_tokens':8192,'temperature':0,'seed':17,'old_visual_reuse':False}
        db.execute('INSERT INTO editor.generations(id,content_version_id,manifest) VALUES (%s,%s,%s)',(gen,version,Jsonb(manifest)))
        db.execute('INSERT INTO editor.jobs(id,generation_id) VALUES (%s,%s)',(job,gen))
        return {'job_id':job,'generation_id':gen,'content_version_id':str(version)}
    return mutate('/content-versions/'+str(version)+'/analyses',body,idempotency_key,create)


@router.get('/jobs/{job_id}')
def job(job_id:uuid.UUID):
    with connection() as db:
        row=db.execute('SELECT * FROM editor.jobs WHERE id=%s',(job_id,)).fetchone()
        if not row:
            upload=upload_status(job_id)
            upload.update({'job_id':str(job_id),'task':'source_parse','generation_id':None,
                'status':('RUNNING' if upload.get('progress') else 'QUEUED') if upload['status']=='PARSING' else upload['status']})
            return upload
        generation=scope(db,row['generation_id'])
        counts=db.execute('SELECT kind,count(*) FROM editor.records WHERE generation_id=%s GROUP BY kind',(row['generation_id'],)).fetchall()
        sizes={c['kind']:c['count'] for c in counts}
        source=source_for(row['generation_id']); expected=source['manifest']['pdf_pages']
        row.pop('owner_id')
        row.update({'counts':counts,'processing_status':row['status'],
          'source_coverage':{'expected_pages':expected,'accounted_pages':sizes.get('evidence',0),
            'visual_read_pages':sizes.get('visuals',0)+sizes.get('visual_observations',0),'all_pages_accounted':sizes.get('evidence',0)==expected,
            'visual_read_complete':sizes.get('visuals',0)+sizes.get('visual_observations',0)==expected,
            'ocr_processed_pages':sizes.get('page_readings',0),'checked_pages':sizes.get('page_checks',0),
            'source_spans':sizes.get('source_spans',0)},
          'editorial_status':'ACCEPTED' if generation['status']=='ACTIVE' else 'PENDING'})
        return row


@router.get('/generations/{generation}')
def generation_detail(generation:uuid.UUID):
    with connection() as db: return scope(db,generation)


@router.post('/jobs/{job_id}/cancel')
def cancel(job_id:uuid.UUID,body:AnalysisRequest,idempotency_key:str=Header()):
    def action(db):
        row=db.execute('SELECT * FROM editor.jobs WHERE id=%s',(job_id,)).fetchone()
        if not row:
            upload=authorized_upload(db,job_id)
            locked=db.execute('SELECT status FROM editor.uploads WHERE id=%s FOR UPDATE',(job_id,)).fetchone()
            if locked['status']!='PARSING': raise HTTPException(409,'JOB_NOT_RUNNING')
            from editor.parse_contract import QUEUE, atomic_json
            atomic_json(QUEUE/(str(job_id)+'.cancel.json'),{'cancellation_requested':True})
            return {'job_id':str(job_id),'cancellation_requested':True}
        scope(db,row['generation_id'])
        db.execute("UPDATE editor.jobs SET cancellation_requested=true,status=CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE status END WHERE id=%s",(job_id,))
        return {'job_id':str(job_id),'cancellation_requested':True}
    return mutate('/jobs/'+str(job_id)+'/cancel',body,idempotency_key,action)


@router.get('/generations/{generation}/region-rereads')
def region_rereads(generation:uuid.UUID,pdf_page:int|None=None):
    if pdf_page is not None and not 1 <= pdf_page <= 100:
        raise HTTPException(400,'INVALID_PAGE')
    with connection() as db:
        scope(db,generation)
    source=source_for(generation)
    directory=ROOT/source['sha256']/'region-reread-v1'/str(generation)
    paths=([directory/f'page-{pdf_page:04}.json'] if pdf_page is not None
           else sorted(directory.glob('page-*.json')))
    items=[]
    for path in paths:
        if not path.exists():
            continue
        item=json.loads(path.read_text())
        if item['generation_id']!=str(generation) or item['source_sha256']!=source['sha256']:
            raise HTTPException(409,'REREAD_SOURCE_SCOPE_MISMATCH')
        items.append(item)
    return {'generation_id':str(generation),'items':items,
            'semantic_acceptance':False,'original_records_modified':False}


@router.get('/generations/{generation}/source-review')
def source_review_detail(generation:uuid.UUID,pdf_page:int|None=None):
    from editor.source_review import source_review,ocr_vl_measurement
    if pdf_page is not None and pdf_page < 1:
        raise HTTPException(400,'INVALID_PAGE')
    with connection() as db:
        scope(db,generation)
        rows=db.execute("""SELECT id,kind,record_key,data FROM editor.records
          WHERE generation_id=%s AND kind IN ('source_spans','layout_regions','visual_observations')
          AND (%s::integer IS NULL OR (data->>'pdf_page')::integer=%s)
          ORDER BY kind,record_key""",(generation,pdf_page,pdf_page)).fetchall()
    report=source_review(rows)
    rereads=region_rereads(generation,pdf_page)['items']
    measurements={region['source_span_id']:(page,region)
                  for page in rereads for region in page['regions']}
    source=source_for(generation)
    by_id={str(r['id']):r for r in rows if r['kind']=='source_spans'}
    for page in report['pages']:
        for region in page['regions']:
            region['ocr_vl']=ocr_vl_measurement(ROOT/source['sha256'],generation,
                                               by_id[region['span_id']],source['sha256'])
            if region['span_id'] in measurements:
                measurement,candidate=measurements[region['span_id']]
                region['reread']={'method':measurement['method'],
                                  'status':candidate['status'],
                                  'crop_sha256':candidate['crop_sha256'],
                                  'stable_reread':candidate['stable_reread']}
                region['next_action']='RECONCILE_READER_EVIDENCE'
    return {'generation_id':str(generation),**report}


@router.get('/generations/{generation}/{kind}')
def records(generation:uuid.UUID,kind:Literal['entities','events','scenes','visuals','visual_corrections','evidence','literary','passages','validation','claims','relationships','event_merges','book_synthesis','source_spans','layout_regions','page_readings','visual_observations','page_claims','page_checks','character_evidence'],offset:int=0,limit:int=50,pdf_page:int|None=None):
    if offset<0 or not 1<=limit<=100: raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        g=scope(db,generation)
        if pdf_page is not None and pdf_page<1: raise HTTPException(400,'INVALID_PAGE')
        condition=' AND data->>\'pdf_page\'=%s' if pdf_page is not None else ''
        params=(generation,kind,str(pdf_page)) if pdf_page is not None else (generation,kind)
        rows=db.execute('SELECT id,record_key,data FROM editor.records WHERE generation_id=%s AND kind=%s'+condition+' ORDER BY record_key LIMIT %s OFFSET %s',params+(limit,offset)).fetchall()
        count=db.execute('SELECT count(*) AS n FROM editor.records WHERE generation_id=%s AND kind=%s'+condition,params).fetchone()['n']
    return {'generation_id':str(generation),'content_version_id':str(g['content_version_id']),'generation_status':g['status'],
            'items':rows,'total':count,'offset':offset,'limit':limit,'has_more':offset+len(rows)<count}


@router.get('/evidence/{record_id}')
def evidence(record_id:uuid.UUID):
    with connection() as db:
        row=db.execute("SELECT * FROM editor.records WHERE id=%s AND kind='evidence'",(record_id,)).fetchone()
        if not row: raise HTTPException(404,'Kayıt bulunamadı')
        scope(db,row['generation_id']); return row


@router.get('/visuals/{record_id}')
def visual(record_id:uuid.UUID):
    with connection() as db:
        row=db.execute("SELECT * FROM editor.records WHERE id=%s AND kind IN ('evidence','visuals')",(record_id,)).fetchone()
        if not row: raise HTTPException(404,'Kayıt bulunamadı')
        scope(db,row['generation_id'])
    source=source_for(row['generation_id']); n=row['data']['pdf_page']
    return FileResponse(ROOT/source['sha256']/f'page-{n:04}.png',media_type='image/png',headers={'Cache-Control':'no-store'})


@router.get('/reviews')
def reviews(generation_id:uuid.UUID,offset:int=0,limit:int=50):
    if offset<0 or not 1<=limit<=100: raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        scope(db,generation_id)
        rows=db.execute('''SELECT r.*,COALESCE(v.version,0) AS review_version,v.decision FROM editor.records r
          LEFT JOIN LATERAL(SELECT version,decision FROM editor.reviews WHERE target_id=r.id ORDER BY version DESC LIMIT 1)v ON true
          WHERE r.generation_id=%s AND r.kind!='passages' ORDER BY r.kind,r.record_key LIMIT %s OFFSET %s''',(generation_id,limit,offset)).fetchall()
    return {'generation_id':str(generation_id),'items':rows,'offset':offset,'limit':limit}


class Review(BaseModel):
    target_id:uuid.UUID
    expected_version:int=Field(ge=0)
    decision:Literal['ACCEPT','REJECT','NEEDS_REVIEW']
    reason:str=Field(min_length=1,max_length=2000)


class VisualCorrection(BaseModel):
    target_id:uuid.UUID
    expected_version:int=Field(ge=0)
    description:str=Field(min_length=10,max_length=2000)
    reason:str=Field(min_length=10,max_length=2000)
    provenance:Literal['operator_source_observation','codex_assisted_source_observation']


@router.post('/visual-corrections',status_code=201)
def visual_correction(body:VisualCorrection,idempotency_key:str=Header()):
    def action(db):
        row=db.execute("SELECT * FROM editor.records WHERE id=%s AND kind='visuals'",(body.target_id,)).fetchone()
        if not row: raise HTTPException(404,'Kayıt bulunamadı')
        g=scope(db,row['generation_id'])
        jobs=db.execute('SELECT status FROM editor.jobs WHERE generation_id=%s FOR UPDATE',(row['generation_id'],)).fetchall()
        if any(j['status'] in ('QUEUED','RUNNING') for j in jobs):
            raise HTTPException(409,'PAUSE_ANALYSIS_BEFORE_SOURCE_CORRECTION')
        db.execute('SELECT id FROM editor.records WHERE id=%s FOR UPDATE',(body.target_id,))
        if g['status']!='BUILDING' or db.execute("SELECT id FROM editor.records WHERE generation_id=%s AND kind='scenes' LIMIT 1",(row['generation_id'],)).fetchone():
            raise HTTPException(409,'CORRECTION_REQUIRES_NEW_GENERATION')
        version=db.execute('SELECT COALESCE(max(version),0) AS v FROM editor.reviews WHERE target_id=%s',(body.target_id,)).fetchone()['v']
        if version!=body.expected_version: raise HTTPException(409,'REVIEW_VERSION_CONFLICT')
        corrected={k:row['data'][k] for k in ('pdf_page','render_sha256','evidence_refs','bbox')}
        corrected.update({'description':body.description,'target_id':str(body.target_id),
            'review_version':version+1,'provenance':body.provenance,'reason':body.reason,
            'verification_status':'OPERATOR_SOURCE_OBSERVATION','review_status':'PENDING',
            'human_accepted':False})
        rid=save_record(db,row['generation_id'],'visual_corrections',row['record_key']+f':{version+1:04}',corrected)
        db.execute('INSERT INTO editor.reviews(id,generation_id,target_id,actor_id,decision,reason,version) VALUES (%s,%s,%s,%s,%s,%s,%s)',
          (str(uuid.uuid4()),row['generation_id'],body.target_id,actor_id(),'REJECT',body.reason,version+1))
        return {'id':rid,'target_id':str(body.target_id),'version':version+1,'human_accepted':False}
    return mutate('/visual-corrections',body,idempotency_key,action)


@router.post('/reviews',status_code=201)
def review(body:Review,idempotency_key:str=Header()):
    def action(db):
        row=db.execute('SELECT * FROM editor.records WHERE id=%s FOR UPDATE',(body.target_id,)).fetchone()
        if not row: raise HTTPException(404,'Kayıt bulunamadı')
        scope(db,row['generation_id'])
        version=db.execute('SELECT COALESCE(max(version),0) AS v FROM editor.reviews WHERE target_id=%s',(body.target_id,)).fetchone()['v']
        if version!=body.expected_version: raise HTTPException(409,'REVIEW_VERSION_CONFLICT')
        rid=str(uuid.uuid4())
        db.execute('INSERT INTO editor.reviews(id,generation_id,target_id,actor_id,decision,reason,version) VALUES (%s,%s,%s,%s,%s,%s,%s)',
          (rid,row['generation_id'],body.target_id,actor_id(),body.decision,body.reason,version+1))
        return {'id':rid,'version':version+1,'decision':body.decision}
    return mutate('/reviews',body,idempotency_key,action)


@router.post('/generations/{generation}/activate')
def activate(generation:uuid.UUID,body:AnalysisRequest,idempotency_key:str=Header()):
    def action(db):
        g=scope(db,generation)
        if g['status']!='VALIDATED': raise HTTPException(409,'GENERATION_NOT_VALIDATED')
        unresolved=db.execute('''SELECT count(*) AS n FROM editor.records r WHERE generation_id=%s AND kind!='passages'
          AND COALESCE((SELECT decision FROM editor.reviews WHERE target_id=r.id ORDER BY version DESC LIMIT 1),'PENDING')!='ACCEPT' ''',(generation,)).fetchone()['n']
        if unresolved: raise HTTPException(409,{'code':'EDITOR_REVIEW_REQUIRED','unresolved':unresolved})
        db.execute("UPDATE editor.generations SET status='RETIRED' WHERE content_version_id=%s AND status='ACTIVE'",(g['content_version_id'],))
        db.execute("UPDATE editor.generations SET status='ACTIVE' WHERE id=%s",(generation,))
        return {'generation_id':str(generation),'status':'ACTIVE'}
    return mutate('/generations/'+str(generation)+'/activate',body,idempotency_key,action)


class Question(BaseModel):
    generation_id:uuid.UUID
    question:str=Field(min_length=3,max_length=1000)
    mode:Literal['editor_preview','published']='published'


@router.post('/questions',status_code=202)
def question(body:Question,idempotency_key:str=Header()):
    if body.mode=='editor_preview':require_write()
    def action(db):
        g=scope(db,body.generation_id)
        if g['status'] not in ('VALIDATED','ACTIVE','RETIRED'): raise HTTPException(409,'GENERATION_NOT_READY')
        if body.mode=='published' and g['status']!='ACTIVE': raise HTTPException(409,'EDITOR_REVIEW_REQUIRED')
        rid=str(uuid.uuid4())
        db.execute("INSERT INTO editor.jobs(id,generation_id,task,payload) VALUES (%s,%s,'question',%s)",(rid,body.generation_id,Jsonb(body.model_dump(mode='json'))))
        return {'job_id':rid,'generation_id':str(body.generation_id),'mode':body.mode}
    return mutate('/questions',body,idempotency_key,action)


@router.get('/answers/{job_id}')
def answer(job_id:uuid.UUID):
    with connection() as db:
        job=db.execute("SELECT * FROM editor.jobs WHERE id=%s AND task='question'",(job_id,)).fetchone()
        if not job: raise HTTPException(404,'Kayıt bulunamadı')
        scope(db,job['generation_id'])
        row=db.execute("SELECT data FROM editor.records WHERE generation_id=%s AND kind='answers' AND record_key=%s",(job['generation_id'],str(job_id))).fetchone()
        return {'job_id':str(job_id),'job_status':job['status'],'generation_id':str(job['generation_id']),'answer':row['data'] if row else None}


@router.get('/question-jobs')
def question_jobs(generation_id:uuid.UUID,offset:int=0,limit:int=50):
    if offset<0 or not 1<=limit<=100: raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        scope(db,generation_id)
        rows=db.execute('''SELECT j.id,j.status,j.payload->>'question' AS question,j.error_code,r.data AS answer
          FROM editor.jobs j LEFT JOIN editor.records r ON r.generation_id=j.generation_id
          AND r.kind='answers' AND r.record_key=j.id::text
          WHERE j.generation_id=%s AND j.task='question' ORDER BY j.created_at,j.id LIMIT %s OFFSET %s''',
          (generation_id,limit+1,offset)).fetchall()
    return {'items':rows[:limit],'has_more':len(rows)>limit}


class RetryRequest(AnalysisRequest):
    reason:str|None=Field(default=None,min_length=10,max_length=2000)


@router.post('/jobs/{job_id}/retry',status_code=202)
def retry(job_id:uuid.UUID,body:RetryRequest,idempotency_key:str=Header()):
    def action(db):
        row=db.execute('SELECT * FROM editor.jobs WHERE id=%s FOR UPDATE',(job_id,)).fetchone()
        if not row: raise HTTPException(404,'Kayıt bulunamadı')
        scope(db,row['generation_id'])
        if row['status']!='FAILED': raise HTTPException(409,'JOB_NOT_RETRYABLE')
        if row['attempt_no']>=row['max_attempts'] and not body.reason:
            raise HTTPException(409,'OPERATOR_RECOVERY_REASON_REQUIRED')
        history=row['payload'].get('operator_retries',[])
        history.append({'after_attempt':row['attempt_no'],'previous_error':row['error_code'],
                        'reason':body.reason,'actor':actor_id()})
        db.execute("UPDATE editor.jobs SET status='QUEUED',error_code=NULL,finished_at=NULL,max_attempts=GREATEST(max_attempts,attempt_no+1),payload=payload || %s WHERE id=%s",(Jsonb({'operator_retries':history}),job_id))
        return {'job_id':str(job_id),'status':'QUEUED'}
    return mutate('/jobs/'+str(job_id)+'/retry',body,idempotency_key,action)
