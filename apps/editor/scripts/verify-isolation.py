#!/usr/bin/env python3
"""Inspect actual deployed resource/network boundaries without changing user data."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request

root = Path(__file__).resolve().parents[1]
os.chdir(root)
compose = ['docker','compose']
config = json.loads(subprocess.check_output(compose+['config','--format','json']))
ids = subprocess.check_output(compose+['ps','-q'],text=True).split()
containers = json.loads(subprocess.check_output(['docker','inspect',*ids]))
report = {'containers':[]}
for container in containers:
    service = container['Config']['Labels']['com.docker.compose.service']
    host = container['HostConfig']
    networks = list(container['NetworkSettings']['Networks'])
    if service == 'parser':
        assert host['NetworkMode'] == 'none' and networks == ['none'], (service,networks)
        assert host['ReadonlyRootfs'] and host['CapDrop'] == ['ALL']
        assert not host.get('PortBindings')
        assert not any(m['Destination'].startswith('/run/secrets') or 'docker.sock' in m['Destination'] for m in container['Mounts'])
    elif service not in ('gateway',):
        assert len(networks)==1 and networks[0].endswith('_private'), (service,networks)
        assert not host.get('PortBindings'), service+' unexpectedly publishes a port'
    assert host['Memory'] > 0 and host['NanoCpus'] > 0, service+' has no resource bounds'
    report['containers'].append({'service':service,'image_id':container['Image'],
        'cpu_limit':host['NanoCpus']/1e9,'memory_bytes':host['Memory'],'networks':networks,
        'read_only_root':host['ReadonlyRootfs']})
code = '''import socket,json
try:
 socket.create_connection(('1.1.1.1',443),timeout=2)
 print(json.dumps({'external_tcp_blocked':False}))
except OSError:
 print(json.dumps({'external_tcp_blocked':True}))'''
report['runtime_egress'] = json.loads(subprocess.check_output(compose+['exec','-T','api','python','-c',code]))
assert report['runtime_egress']['external_tcp_blocked']
query = "SELECT json_build_object('superuser',rolsuper,'create_role',rolcreaterole,'create_database',rolcreatedb,'create_in_editor',has_schema_privilege('editor_app','editor','CREATE')) FROM pg_roles WHERE rolname='editor_app'"
report['application_role'] = json.loads(subprocess.check_output(compose+['exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query]))
assert all(value is False for value in report['application_role'].values())
settings = dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if line and not line.startswith('#'))
with urllib.request.urlopen('http://127.0.0.1:'+settings['EDITOR_METRICS_PORT']+'/api/v1/targets',timeout=10) as response:
    targets = json.load(response)['data']['activeTargets']
assert targets and all(target['health']=='up' for target in targets)
report['monitoring'] = [{'health':target['health'],'last_error':target['lastError']} for target in targets]
print(json.dumps(report,indent=2))
