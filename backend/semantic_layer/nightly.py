"""Stage catalog changes privately, publish atomically, and recover failed releases.

Query logs, annotations and other tenants are never replaced by a rollback.
A durable journal makes an interrupted publication recoverable on the next run.
"""
from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import sqlalchemy as sa
from semantic_layer.store import schema as S
from semantic_layer.store.catalog_store import open_store
from semantic_layer.models import utcnow

MUTABLE = [S.sl_concept, S.sl_mapping, S.sl_evidence, S.sl_counter_evidence,
           S.sl_candidate, S.sl_schema_profile, S.sl_suggestion]
GUARD = MUTABLE + [S.sl_schema_annotation, S.sl_catalog_version]
INPUTS = GUARD + [S.sl_query_log]


def encode(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    raise TypeError(type(value).__name__)


def digest(snapshot, tables=GUARD):
    return hashlib.sha256(json.dumps({t.name: snapshot[t.name] for t in tables},
                         sort_keys=True, default=encode, ensure_ascii=False).encode()).hexdigest()


def scope(table, tenant, datasource):
    if "concept_id" in table.c:
        return table.c.concept_id.in_(sa.select(S.sl_concept.c.id).where(
            S.sl_concept.c.tenant_id == tenant, S.sl_concept.c.datasource_id == datasource))
    clauses = [table.c.datasource_id == datasource]
    if "tenant_id" in table.c:
        clauses.append(table.c.tenant_id == tenant)
    return sa.and_(*clauses)


def capture(conn, tenant, datasource, tables=INPUTS):
    return {t.name: [dict(r) for r in conn.execute(sa.select(t).where(scope(t,tenant,datasource)).order_by(t.c.id)).mappings()]
            for t in tables}


def lock(conn):
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
        conn.execute(sa.text("LOCK TABLE " + ", ".join(t.name for t in GUARD) + " IN SHARE ROW EXCLUSIVE MODE"))


def insert(conn, table, rows):
    for offset in range(0,len(rows),500):
        batch=[]
        for row in rows[offset:offset+500]:
            row=dict(row)
            for col in table.c:
                if isinstance(col.type,sa.DateTime) and isinstance(row.get(col.name),str):
                    row[col.name]=datetime.fromisoformat(row[col.name])
            batch.append(row)
        conn.execute(table.insert(),batch)


def replace(conn, snapshot, tenant, datasource):
    for t in reversed(MUTABLE):
        conn.execute(t.delete().where(scope(t,tenant,datasource)))
    for t in MUTABLE:
        insert(conn,t,snapshot[t.name])


def version(conn, tenant, datasource, note):
    n=conn.execute(sa.select(sa.func.max(S.sl_catalog_version.c.version)).where(
        S.sl_catalog_version.c.tenant_id==tenant,S.sl_catalog_version.c.datasource_id==datasource)).scalar() or 0
    rows=conn.execute(sa.select(S.sl_concept).where(scope(S.sl_concept,tenant,datasource),S.sl_concept.c.status=="CERTIFIED")).mappings()
    certified=sorted(f"{r['semantic_type']}:{r['normalized_term']}#{r['sense_id']}" for r in rows)
    conn.execute(S.sl_catalog_version.insert().values(id="cv_"+uuid.uuid4().hex,tenant_id=tenant,datasource_id=datasource,
        version=n+1,certified_count=len(certified),snapshot_json={"certified":certified,"certified_count":len(certified)},
        note=note,created_at=utcnow()))


def save(path, data):
    temp=path.with_suffix(".tmp")
    with temp.open("w") as f:
        os.chmod(temp,0o600)
        json.dump(data,f,default=encode,ensure_ascii=False)
        f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


class Conflict(RuntimeError): pass


class Release:
    def __init__(self, store, tenant, datasource, journal):
        self.store,self.tenant,self.datasource,self.journal=store,tenant,datasource,Path(journal)

    def prepare(self, stage_dsn):
        with self.store.engine.begin() as conn:
            lock(conn);before=capture(conn,self.tenant,self.datasource)
        data={"id":uuid.uuid4().hex,"state":"prepared","tenant":self.tenant,"datasource":self.datasource,"before":before}
        save(self.journal,data)
        stage=open_store(stage_dsn)
        with stage.engine.begin() as conn:
            for table in INPUTS:insert(conn,table,before[table.name])
        return stage

    def publish(self, stage):
        data=json.loads(self.journal.read_text())
        with stage.engine.connect() as conn:candidate=capture(conn,self.tenant,self.datasource,tables=MUTABLE)
        data.update(state="publishing",candidate=candidate);save(self.journal,data)
        with self.store.engine.begin() as conn:
            lock(conn)
            current=capture(conn,self.tenant,self.datasource,tables=GUARD)
            if digest(current)!=digest(data["before"]):raise Conflict("catalog changed while candidate was evaluated")
            replace(conn,candidate,self.tenant,self.datasource)
            version(conn,self.tenant,self.datasource,"nightly:"+data["id"])
        data["state"]="published";save(self.journal,data)

    def rollback(self):
        data=json.loads(self.journal.read_text())
        if data["state"] not in ("publishing","published"):
            return False
        with self.store.engine.begin() as conn:
            lock(conn);current=capture(conn,self.tenant,self.datasource,tables=GUARD)
            if digest(current)==digest(data["before"]):
                data["state"]="aborted";save(self.journal,data);return False
            latest=max(current[S.sl_catalog_version.name],key=lambda r:r["version"],default={})
            if latest.get("note")=="rollback:"+data["id"] and digest(current,MUTABLE)==digest(data["before"],MUTABLE):
                data["state"]="rolled_back";save(self.journal,data);return True
            if (latest.get("note")!="nightly:"+data["id"] or digest(current,MUTABLE)!=digest(data["candidate"],MUTABLE)
                or digest(current,[S.sl_schema_annotation])!=digest(data["before"],[S.sl_schema_annotation])):
                raise Conflict("concurrent catalog edit; automatic rollback must not overwrite it")
            replace(conn,data["before"],self.tenant,self.datasource)
            version(conn,self.tenant,self.datasource,"rollback:"+data["id"])
        data["state"]="rolled_back";save(self.journal,data);return True

    def finish(self):
        data=json.loads(self.journal.read_text());data["state"]="complete";save(self.journal,data)


def execute_release(release, stage_dsn, build, gate, reload):
    stage=release.prepare(stage_dsn)
    try:
        build(stage_dsn)
        gate(stage_dsn)
        release.publish(stage)
        reload()
        gate(None)
        release.finish()
    except BaseException:
        if release.rollback():
            reload()  # a failed recovery reload is itself an error, never a success
        raise
    finally:
        stage.engine.dispose()


def main():
    from semantic_layer.config import SemanticSettings
    settings=SemanticSettings.from_env()
    root=Path(os.environ.get("SEMANTIC_NIGHTLY_ROOT",Path(__file__).resolve().parents[2]))
    state=Path(os.environ.get("SEMANTIC_NIGHTLY_STATE","/data/nanobaseai/bi/nightly-state"))
    state.mkdir(mode=0o700,parents=True,exist_ok=True)
    scope_id=hashlib.sha256((settings.tenant_id+":"+settings.datasource_id).encode()).hexdigest()[:16]
    guard=(state/(scope_id+".lock")).open("a")
    try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit("another nightly job owns this catalog")
    token=os.environ.get("SEMANTIC_ADMIN_TOKEN")
    if not token:raise SystemExit("SEMANTIC_ADMIN_TOKEN is required")
    baseline=root/"tests/text2sql/quality-baseline-golden.json"
    if not baseline.is_file():raise SystemExit("quality baseline missing; nightly cannot create one")
    store=open_store(settings.store_dsn,create=False)
    def reload():
        req=urllib.request.Request(os.environ.get("SEMANTIC_BRIDGE_URL","http://127.0.0.1:8795")+"/api/v1/semantic/reload",
            data=b"{}",headers={"X-Semantic-Admin":token,"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=30) as response:
            if not json.load(response).get("ok"):raise RuntimeError("bridge rejected reload")
    def command(args,dsn=None):
        env=dict(os.environ,SEMANTIC_CHANGED_ONLY="1",SEMANTIC_SKIP_EMPTY="1",SEMANTIC_SKIP_SHADOW="1")
        if dsn:env["SEMANTIC_STORE_DSN"]=dsn
        subprocess.run([sys.executable,*args],cwd=root,env=env,check=True)
    def gate(dsn):command(["tests/text2sql/quality-gate.py","--out",str(run/(("candidate" if dsn else "published")+"-quality.json"))],dsn)
    def build(dsn):
        for step in ("profile","mine","docs","certify"):command(["-m","semantic_layer.cli",step],dsn)
    # An unfinished commit is recovered before any fresh mutation is started.
    for old in sorted(state.glob(scope_id+"-*/journal.json")):
        prior=Release(store,settings.tenant_id,settings.datasource_id,old)
        if prior.rollback() or json.loads(old.read_text())["state"]=="rolled_back":
            reload()
            data=json.loads(old.read_text());data["state"]="recovered";save(old,data)
    run=state/(scope_id+"-"+uuid.uuid4().hex);run.mkdir(mode=0o700)
    def interrupted(signum,frame):raise RuntimeError(f"nightly interrupted by signal {signum}")
    signal.signal(signal.SIGTERM,interrupted)
    execute_release(Release(store,settings.tenant_id,settings.datasource_id,run/"journal.json"),
                    "sqlite:///"+str(run/"candidate.sqlite"),build,gate,reload)
    print("nightly publication and quality checks completed")

if __name__=="__main__":main()
