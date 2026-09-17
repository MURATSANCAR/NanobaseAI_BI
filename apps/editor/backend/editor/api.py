import hmac
import json
import time
import uuid
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from editor.config import connection, secret, RELEASE
from editor.access import authorize, admin, principal, visible_works

app = FastAPI(title='Nanobase Editör — Altyapı API', version=RELEASE,
              docs_url=None, redoc_url=None, openapi_url=None)
requests = Counter('editor_http_requests_total', 'Requests', ['status'])
latency = Histogram('editor_http_duration_seconds', 'Request duration')


@app.middleware('http')
async def request_metadata(request, call_next):
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    response = await call_next(request)
    requests.labels(status=str(response.status_code)).inc()
    latency.observe(time.monotonic() - started)
    response.headers['X-Request-ID'] = request_id
    response.headers['Cache-Control'] = 'no-store'
    return response


def infrastructure():
    checks = {}
    details = {}
    try:
        with connection() as db:
            details['schema_revision'] = db.execute('SELECT version_num FROM editor.alembic_version').fetchone()['version_num']
            details['deployments'] = db.execute('SELECT release FROM editor.deployments ORDER BY release').fetchall()
            details['source_probes'] = db.execute("SELECT sha256, (manifest->>'bytes')::bigint AS bytes, (manifest->>'pdf_pages')::integer AS pages FROM editor.source_probes ORDER BY sha256").fetchall()
            row = db.execute("SELECT extract(epoch from (now()-seen_at)) AS age, mode FROM editor.worker_heartbeats WHERE worker_id='foundation'").fetchone()
            checks['postgres'] = True
            checks['worker'] = bool(row and row['age'] < 40)
            details['worker_mode'] = row['mode'] if row else 'starting'
            checks['checkpoint_schema'] = db.execute("SELECT to_regclass('checkpoints.checkpoints') IS NOT NULL AS present").fetchone()['present']
    except Exception:
        checks['postgres'] = False
    try:
        result = httpx.get('http://qdrant:6333/collections', timeout=3, trust_env=False)
        result.raise_for_status()
        checks['qdrant'] = result.json().get('status') == 'ok'
    except Exception:
        checks['qdrant'] = False
    checks['source_storage'] = Path('/data/artifacts').is_dir()
    try:
        stamp=json.loads(Path('/data/artifacts/parse-queue/heartbeat.json').read_text())['at']
        checks['parser']=0 <= time.time()-stamp < 45
    except (OSError,ValueError,KeyError):
        checks['parser']=False
    return {'release': RELEASE, 'infrastructure_ready': all(checks.values()), 'checks': checks,
            'details': details, 'pilot_ready': False,
            'pending': ['reference_books', 'model_and_visual_qualification', 'book_pipeline',
                        'editor_authorization_and_ui', 'shared_load_acceptance']}


@app.get('/health/live')
def live():
    return {'status': 'ok'}


@app.get('/health/ready')
def ready():
    state = infrastructure()
    return JSONResponse({'status': 'ready' if state['infrastructure_ready'] else 'not_ready'},
                        status_code=200 if state['infrastructure_ready'] else 503)


@app.get('/v1/system', dependencies=[Depends(authorize)])
def system():
    admin()
    return infrastructure()


@app.get('/v1/source-probes/{sha256}', dependencies=[Depends(authorize)])
def source_probe(sha256: str):
    with connection() as db:
        p=principal()
        if not (p.role=='ADMIN' and p.system_role=='ADMIN' and p.work_ids is None):
            allowed=db.execute('SELECT 1 FROM editor.content_versions cv JOIN editor.editions e ON e.id=cv.edition_id WHERE cv.sha256=%s AND e.work_id=ANY(%s::uuid[]) LIMIT 1',(sha256,visible_works(db))).fetchone()
            if not allowed:raise HTTPException(404,'Kayıt bulunamadı')
        row = db.execute('SELECT manifest FROM editor.source_probes WHERE sha256=%s', (sha256,)).fetchone()
    if not row:
        raise HTTPException(404, 'Kayıt bulunamadı')
    return row['manifest']


@app.get('/metrics', dependencies=[Depends(authorize)])
def metrics():
    admin()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get('/v1/model-services', dependencies=[Depends(authorize)])
def model_services():
    admin()
    services = {}
    with httpx.Client(timeout=3, trust_env=False) as client:
        for name in ('llm', 'embedding', 'reranker'):
            try:
                response = client.get(f'http://{name}:8080/health')
                services[name] = {'ready': response.status_code == 200}
            except Exception:
                services[name] = {'ready': False}
    return {'services': services, 'semantic_qualification': 'PENDING', 'pilot_ready': False}


from editor.book_api import router as book_router
app.include_router(book_router, dependencies=[Depends(authorize)])
from editor.access_api import router as access_router
app.include_router(access_router, dependencies=[Depends(authorize)])
