#!/usr/bin/env python3
"""Prepare a hash-pinned release for deploy-verified-release.py; never deploys.

From a git-archive tarball of a clean main commit and its source manifest this
creates the complete stage, builds the api/document images on top of the images
the live installation runs now (only /app is replaced, network disabled), proves
that every image byte under /app equals the staged backend, checks that the live
web image was built from exactly the staged frontend sources, writes build,
main-source and snapshot proofs, writes the deployment contract, and repeats the
deployment tool's pre-deployment assertions.  It starts no service and writes no
application data.  Qualification and cleanup proofs are existing files named on
the command line; this script does not create them.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tarfile

p = argparse.ArgumentParser()
p.add_argument('--tarball', type=Path, required=True)
p.add_argument('--main-sources', type=Path, required=True)
p.add_argument('--release', required=True)
p.add_argument('--qualification', type=Path, required=True)
p.add_argument('--cleanup', type=Path, required=True)
p.add_argument('--web-acceptance', type=Path, required=True)
a = p.parse_args()

root = Path('/data/nanobaseai/editor')
assert os.name == 'posix' and (root / 'secrets/api_token').is_file()
tag = a.release
stage = root / 'runtime' / ('deploy-' + tag + '-complete-stage')
evidence = root / 'evidence'
sha = lambda data: hashlib.sha256(data).hexdigest()
MANAGED = ['backend', 'deploy', 'frontend', 'gpu', 'ocr', 'ocr-vl', 'scripts', 'speech']


def run(*parts, **kw):
    return subprocess.run(parts, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw).stdout.decode()


def files(directory):
    out = {}
    for f in directory.rglob('*'):
        assert not f.is_symlink(), 'SYMLINK_SOURCE_REJECTED'
        if f.is_file():
            out[str(f.relative_to(directory))] = sha(f.read_bytes())
    return out


def image_files(image):
    cid = run('docker', 'create', image).strip()
    try:
        blob = subprocess.run(['docker', 'cp', cid + ':/app/.', '-'], check=True, stdout=subprocess.PIPE).stdout
    finally:
        run('docker', 'rm', cid)
    out = {}
    with tarfile.open(fileobj=io.BytesIO(blob)) as t:
        for m in t.getmembers():
            name = str(Path(m.name)).removeprefix('./')
            if m.isfile() and '__pycache__' not in Path(name).parts and not name.endswith('.pyc'):
                out[name] = sha(t.extractfile(m).read())
    return out


def write_once(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
    return {'path': str(path), 'sha256': sha(path.read_bytes())}


# 1. stage == clean main commit
main = json.loads(a.main_sources.read_bytes())
assert main['status'] == 'PASS' and main['branch'] == 'main' and main['clean'] is True and re.fullmatch('[0-9a-f]{40}', main['commit'])
assert a.tarball.name == 'editor-main-' + main['commit'] + '.tar', 'TARBALL_COMMIT_MISMATCH'
stage.mkdir(mode=0o700)
with tarfile.open(a.tarball) as t:
    members = [m for m in t.getmembers()]
    assert all(not m.issym() and not m.islnk() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
    t.extractall(stage, members=members)
staged = files(stage)
assert staged == main['source_files'], 'STAGE_NOT_EQUAL_TO_MAIN'
top_files = sorted(f.name for f in stage.iterdir() if f.is_file())
assert sorted(d.name for d in stage.iterdir() if d.is_dir()) == sorted(MANAGED), 'UNEXPECTED_STAGE_DIRECTORIES'
backend = files(stage / 'backend')
web_dir = stage / 'frontend'
web_paths = list((web_dir / 'src').rglob('*')) + [web_dir / n for n in ('package.json', 'package-lock.json', 'index.html', 'tsconfig.json', 'vite.config.ts')]
web_sources = {str(f.relative_to(web_dir)): sha(f.read_bytes()) for f in web_paths if f.is_file()}

# 2. live web image must be the build of exactly these frontend sources
env = dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
web_id = run('docker', 'image', 'inspect', '--format', '{{.Id}}', env['EDITOR_WEB_IMAGE']).strip()
def web_file(name):
    return subprocess.run(['docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                           '--entrypoint', 'cat', web_id, '/usr/share/nginx/html/editor/' + name], check=True, stdout=subprocess.PIPE).stdout
web_manifest = json.loads(web_file('build-manifest.json'))
assert web_manifest['sources'] == web_sources, 'WEB_IMAGE_NOT_BUILT_FROM_MAIN_FRONTEND'
assert all(sha(web_file(n)) == h for n, h in web_manifest['outputs'].items())

# 3. build api/document on the images the live installation runs now
live_backend = {str(f.relative_to(root / 'backend')): sha(f.read_bytes()) for f in (root / 'backend').rglob('*')
                if f.is_file() and '__pycache__' not in f.parts}
images = []
for role, prefix, container in (('api', 'nanobase-editor', 'nanobase-editor-api-1'),
                                ('document', 'nanobase-editor-document', 'nanobase-editor-parser-1')):
    base_id = run('docker', 'inspect', '--format', '{{.Image}}', container).strip()
    base_files = image_files(base_id)
    assert base_files == live_backend, 'LIVE_BASE_IMAGE_NOT_EQUAL_TO_LIVE_BACKEND:' + role
    assert not set(base_files) - set(backend), 'FILES_REMOVED_SINCE_LIVE_WOULD_REMAIN:' + role
    # BuildKit resolves a bare image ID in FROM as a registry name; pin it with a local tag.
    base_tag = prefix + ':' + tag + '-exact-base'
    run('docker', 'tag', base_id, base_tag)
    dockerfile = stage.parent / ('Dockerfile.' + tag + '.' + role)
    dockerfile.write_text('FROM ' + base_tag + '\nCOPY backend/ /app/\n')
    image = prefix + ':' + tag
    log = evidence / (tag + '-build-' + role + '.log')
    with log.open('x') as out:
        subprocess.run(['docker', 'build', '--network=none', '--pull=false', '-f', str(dockerfile), '-t', image, str(stage)],
                       stdout=out, stderr=subprocess.STDOUT, check=True)
    image_id = run('docker', 'image', 'inspect', image, '--format', '{{.Id}}').strip()
    built = image_files(image_id)
    assert built == backend, json.dumps({'role': role, 'extra': sorted(set(built) - set(backend)),
                                         'missing': sorted(set(backend) - set(built))})
    images.append({'role': role, 'image': image, 'image_id': image_id, 'base_image_id': base_id, 'base_tag': base_tag,
                   'image_source_manifest': built, 'exact_source_path_set': True, 'extra_python_files': [], 'log': str(log)})

# 4. proofs and contract
main_ref = write_once(evidence / (tag + '-main_sources.json'), main)
build_ref = write_once(evidence / (tag + '-build-proof.json'), {
    'git_head': main['commit'], 'backend_manifest': backend, 'backend_file_count': len(backend), 'images': images,
    'deployed': False, 'application_processes_started': 0, 'model_calls': 0, 'db_writes': 0, 'build_network': 'none'})
image_ids = {'api': images[0]['image_id'], 'document': images[1]['image_id'], 'web': web_id}
snapshot_ref = write_once(evidence / (tag + '-snapshot.json'), {
    'status': 'PASS', 'main_commit': main['commit'], 'release': tag, 'qualified_generation_id': json.loads(a.qualification.read_bytes())['generation_id'],
    'source_files': staged, 'images': image_ids, 'backend_files': backend, 'web_sources': web_sources,
    'backend_tree_sha256': sha(json.dumps(backend, sort_keys=True).encode()), 'p5_web_image_id': web_id})
ref = lambda path: {'path': str(path), 'sha256': sha(path.read_bytes())}
contract = {
    'root': str(root), 'stage': str(stage), 'remote_hostname': socket.gethostname(), 'release': tag,
    'previous_release': env['EDITOR_RELEASE'],
    'previous_backend_tree_sha256': sha(json.dumps(live_backend, sort_keys=True).encode()),
    'qualified_generation_id': json.loads(a.qualification.read_bytes())['generation_id'],
    'readiness_url': 'http://127.0.0.1:8810/health/ready', 'managed_directories': MANAGED, 'top_level_files': top_files,
    'images': image_ids,
    'proofs': {'cleanup': ref(a.cleanup), 'qualification': ref(a.qualification), 'backend_build': build_ref,
               'web_acceptance': ref(a.web_acceptance), 'snapshot': snapshot_ref, 'main_sources': main_ref}}
contract_path = root / 'runtime' / (tag + '-deployment-contract.json')
write_once(contract_path, contract)

# 5. repeat the deployment tool's pre-deployment assertions (no deployment)
cleanup, qualification = json.loads(a.cleanup.read_bytes()), json.loads(a.qualification.read_bytes())
web_proof = json.loads(a.web_acceptance.read_bytes())
checks = {
    'cleanup': cleanup['qualification_returncode'] == 0 and cleanup['temporary_proxy_removed'] and not cleanup['cleanup_errors'],
    'qualification': [s for s in qualification['steps'] if s['stage'] == 'qualification'][-1]['state'] == 'PASS'
                     and [s for s in qualification['steps'] if s['stage'] == 'target_services'][-1]['state'] == 'STOPPED',
    'web_acceptance': web_proof['status'] == 'PASS' and web_proof['semantic_acceptance'] is False
                      and web_proof['dependency_graph_reference_acceptance'] == 'PASS_SAME_SNAPSHOT_SEPARATE_INDEPENDENT_VERIFIER',
    'stage_equals_main': files(stage) == main['source_files'],
    'stage_roots': set(f.name for f in stage.iterdir()) == set(MANAGED) | set(top_files),
    'images_exact': all(i['image_source_manifest'] == backend for i in images),
}
assert all(checks.values()), json.dumps(checks)
print(json.dumps({'status': 'PREPARED_NOT_DEPLOYED', 'contract': str(contract_path), 'release': tag,
                  'previous_release': contract['previous_release'], 'main_commit': main['commit'],
                  'backend_files': len(backend), 'stage_files': len(staged), 'images': image_ids, 'checks': checks}, indent=1))
