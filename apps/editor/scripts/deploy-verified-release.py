#!/usr/bin/env python3
"""Deploy a complete, hash-pinned remote release. Never starts analysis jobs.

Requires an explicit deployment contract and independent technical proof files.
No default release, image, source subset or successful placeholder is provided.
"""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.request
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('contract', type=Path)
args = parser.parse_args()
contract_bytes = args.contract.read_bytes()
c = json.loads(contract_bytes)
assert os.name == 'posix' and socket.gethostname() == c['remote_hostname']
root, stage = Path(c['root']).resolve(), Path(c['stage']).resolve()
assert root != stage and (root/'secrets/api_token').is_file()
os.chdir(root)
lock = (root/'evidence/release-deployment.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
sha = lambda data: hashlib.sha256(data).hexdigest()


def command(parts, **kwargs):
    result = subprocess.run(parts, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        raise RuntimeError('COMMAND_FAILED:' + parts[0] + ':' + str(result.returncode))
    return result.stdout


def proof(name):
    ref = c['proofs'][name]
    data = Path(ref['path']).read_bytes()
    assert sha(data) == ref['sha256'], 'PROOF_HASH_MISMATCH:' + name
    return json.loads(data)


def files(directory):
    result = {}
    for p in directory.rglob('*'):
        assert not p.is_symlink(), 'SYMLINK_SOURCE_REJECTED'
        if p.is_file():
            result[str(p.relative_to(directory))] = sha(p.read_bytes())
    return result


def idle():
    sql = "SELECT (SELECT count(*) FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')) + (SELECT count(*) FROM editor.uploads WHERE status='PARSING')"
    assert command(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',sql]).strip() == b'0', 'ACTIVE_WORK_BLOCKS_DEPLOYMENT'


cleanup, qualification = proof('cleanup'), proof('qualification')
assert cleanup['qualification_returncode'] == 0 and cleanup['temporary_proxy_removed'] and not cleanup['cleanup_errors']
assert qualification['generation_id'] == c['qualified_generation_id']
assert [s for s in qualification['steps'] if s['stage'] == 'qualification'][-1]['state'] == 'PASS'
assert [s for s in qualification['steps'] if s['stage'] == 'target_services'][-1]['state'] == 'STOPPED'
snapshot, main = proof('snapshot'), proof('main_sources')
assert snapshot['status'] == 'PASS' and main['status'] == 'PASS'
assert main['branch'] == 'main' and main['clean'] is True
assert re.fullmatch(r'[0-9a-f]{40}', main['commit'])
assert snapshot['main_commit'] == main['commit'] and snapshot['release'] == c['release']
assert snapshot['qualified_generation_id'] == c['qualified_generation_id']
assert snapshot['source_files'] == main['source_files'] == files(stage), 'FULL_MAIN_STAGE_MISMATCH'
managed = c['managed_directories']
assert {'backend','frontend','scripts','deploy','gpu'} <= set(managed)
assert all(re.fullmatch(r'[A-Za-z0-9_.-]+', name) for name in managed)
assert not {'secrets','runtime','evidence','.git'} & set(managed)
top_files = c['top_level_files']
assert all('/' not in name and name not in ('.env','secrets') and not name.startswith('.env.') for name in top_files if name != '.env.example')
assert set(p.name for p in stage.iterdir()) == set(managed) | set(top_files)
backend = files(stage/'backend')
assert backend and backend == snapshot['backend_files'], 'TRUSTED_BACKEND_MANIFEST_MISMATCH'
web = stage/'frontend'
web_paths = list((web/'src').rglob('*')) + [web/n for n in ('package.json','package-lock.json','index.html','tsconfig.json','vite.config.ts')]
web_sources = {str(p.relative_to(web)):sha(p.read_bytes()) for p in web_paths if p.is_file()}
assert web_sources and web_sources == snapshot['web_sources'], 'TRUSTED_WEB_MANIFEST_MISMATCH'
build, web_proof = proof('backend_build'), proof('web_acceptance')
assert web_proof['status'] == 'PASS' and web_proof['semantic_acceptance'] is False
assert web_proof['dependency_graph_reference_acceptance'] == 'PASS_SAME_SNAPSHOT_SEPARATE_INDEPENDENT_VERIFIER'
assert snapshot['images'] == c['images'] and snapshot['web_sources'] == web_sources
assert snapshot['backend_tree_sha256'] == sha(json.dumps(backend, sort_keys=True).encode())
expected_python = {Path(k).name:v for k,v in backend.items() if k.startswith('editor/') and k.endswith('.py')}
assert build['source_sha256'] == expected_python
for role in ('api','document'):
    row = next(r for r in build['images'] if r['role'] == role)
    assert row['image_id'] == c['images'][role]
    assert row['image_python_manifest'] == expected_python and not row['extra_python_files']
    assert command(['docker','image','inspect','--format','{{.Id}}',row['image']]).decode().strip() == row['image_id']
    cid = command(['docker','create',row['image_id']]).decode().strip()
    try:
        archive = command(['docker','cp',cid+':/app/.','-'])
        actual = {}
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for item in tar.getmembers():
                name = str(Path(item.name)).removeprefix('./')
                if item.isfile() and '__pycache__' not in Path(name).parts:
                    actual[name] = sha(tar.extractfile(item).read())
        assert actual == backend, 'ALL_BACKEND_IMAGE_BYTES_MISMATCH:' + role
    finally:
        command(['docker','rm',cid])
web_id = c['images']['web']
assert command(['docker','image','inspect','--format','{{.Id}}',web_id]).decode().strip() == web_id
assert snapshot['p5_web_image_id'] == web_id
def web_file(name):
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    return command(['docker','run','--rm','--pull','never','--network','none','--read-only','--cap-drop','ALL','--entrypoint','cat',web_id,'/usr/share/nginx/html/editor/'+name])
manifest = json.loads(web_file('build-manifest.json'))
assert manifest['sources'] == web_sources and 'index.html' in manifest['outputs']
assert all(sha(web_file(n)) == h for n,h in manifest['outputs'].items())
idle()
assert sha(json.dumps({str(p.relative_to(root/'backend')):sha(p.read_bytes()) for p in (root/'backend').rglob('*')
                      if p.is_file() and '__pycache__' not in p.parts}, sort_keys=True).encode()) == c['previous_backend_tree_sha256']
command(['python3','scripts/verify-release.py'],env={**os.environ,'EDITOR_VERIFY_WEB':'1'},timeout=600)
old = (root/'.env').read_text()
assert 'EDITOR_RELEASE='+c['previous_release'] in old.splitlines()
assert files(stage) == snapshot['source_files'], 'STAGE_CHANGED_DURING_PREFLIGHT'
backup = root/'runtime'/('before-'+c['release']+'-'+str(uuid.uuid4()))
backup.mkdir(mode=0o700)
paths = managed + top_files
present = {name:(root/name).exists() for name in paths}
for name in paths + ['.env']:
    p = root/name
    if p.exists():
        if p.is_dir(): shutil.copytree(p,backup/name)
        else: shutil.copy2(p,backup/name)
(backup/'.env').chmod(0o600)
services = ['api','worker','parser','reread-worker','gateway']
def start():
    command(['docker','compose','up','-d','--no-deps','--pull','never',*services], timeout=600)
def ready():
    for _ in range(60):
        try:
            with urllib.request.urlopen(c['readiness_url'],timeout=3) as response:
                if response.status == 200: return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError('READINESS_TIMEOUT')
def replace_tree(source, name):
    p = root/name
    if p.is_dir(): shutil.rmtree(p)
    elif p.exists(): p.unlink()
    if (source/name).is_dir(): shutil.copytree(source/name,p)
    elif (source/name).exists(): shutil.copy2(source/name,p)
report = {'release':c['release'],'contract_sha256':sha(contract_bytes),'backup':str(backup),'semantic_acceptance':False}
try:
    idle()
    for name in paths: replace_tree(stage,name)
    deployed = {}
    for name in paths:
        if (root/name).is_dir(): deployed.update({name+'/'+k:v for k,v in files(root/name).items()})
        else: deployed[name] = sha((root/name).read_bytes())
    assert deployed == snapshot['source_files'] == files(stage), 'FULL_SOURCE_CHANGED_DURING_COPY'
    values = {'EDITOR_RELEASE':c['release'],'EDITOR_IMAGE':c['images']['api'],'EDITOR_DOCUMENT_IMAGE':c['images']['document'],'EDITOR_WEB_IMAGE':web_id}
    lines = old.splitlines()
    for key in values: assert sum(line.startswith(key+'=') for line in lines) == 1
    updated = '\n'.join(next((key+'='+v for key,v in values.items() if line.startswith(key+'=')),line) for line in lines)+'\n'
    temporary = root/'.env.deploy.tmp'; temporary.write_text(updated); temporary.chmod(0o600); temporary.replace(root/'.env')
    config = json.loads(command(['docker','compose','config','--format','json']))
    for service in services:
        role = 'web' if service == 'gateway' else ('document' if service in ('parser','reread-worker') else 'api')
        assert config['services'][service]['image'] == c['images'][role], 'COMPOSE_OVERRIDE_IMAGE_MISMATCH'
    start(); ready()
    for name, script in [('release','verify-release.py'),('infrastructure','verify.py')]:
        with (backup/(name+'.log')).open('x') as log:
            result = subprocess.run(['python3','scripts/'+script],env={**os.environ,'EDITOR_VERIFY_WEB':'1'},stdout=log,stderr=subprocess.STDOUT,timeout=600)
        assert result.returncode == 0, 'REAL_VERIFICATION_FAILED:' + name
    report['status'] = 'PASS'
except Exception as exc:
    for name in paths: replace_tree(backup,name)
    shutil.copy2(backup/'.env',root/'.env')
    try: start(); ready(); report['rollback'] = 'READY'
    except Exception: report['rollback'] = 'FAILED'
    report['status'] = 'FAILED'; report['error_type'] = type(exc).__name__
finally:
    (backup/'deployment-result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
raise SystemExit(0 if report['status'] == 'PASS' else 1)
