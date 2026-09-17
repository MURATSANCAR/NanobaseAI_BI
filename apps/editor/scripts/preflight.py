#!/usr/bin/env python3
"""Host-side preflight. Run on the target Linux server, not a developer laptop."""
import json
import ipaddress
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[1]
os.chdir(root)
settings = dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines() if line and not line.startswith('#'))
errors = []
for name in ('db_admin','db_owner','db_app','api_token'):
    path = root/'secrets'/name
    if not path.is_file() or len(path.read_text().strip()) < 32:
        errors.append('Missing or too short installation secret: '+name)
if (root/'secrets').stat().st_mode & 0o077:
    errors.append('Secrets directory must be restricted to its owner (chmod 700 secrets).')
if platform.system() != 'Linux' or platform.machine() != 'x86_64':
    errors.append('This release is qualified for Linux x86_64 only.')
subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], check=True)
subprocess.run(['docker', 'compose', 'config', '--quiet'], check=True)
config = json.loads(subprocess.check_output(['docker','compose','config','--format','json']))
app_env = config['services']['api'].get('environment', {})
if app_env.get('EDITOR_MODEL_BACKEND') == 'vllm':
    for name in ('EDITOR_MODEL_BASE_URL', 'EDITOR_OCR_VL_BASE_URL'):
        value = app_env.get(name, '')
        endpoint = urlsplit(value)
        if (endpoint.scheme not in ('http', 'https') or not endpoint.hostname
                or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                or endpoint.path.rstrip('/')):
            errors.append(name+' must be an HTTP(S) runner root without credentials, path, query or fragment.')
        if endpoint.hostname in ('localhost', '127.0.0.1', '::1'):
            errors.append(name+' cannot use container loopback; configure an address reachable from Editor containers.')
    for name in ('EDITOR_MODEL_NAME','EDITOR_OCR_VL_MODEL','EDITOR_OCR_VL_REVISION'):
        if not app_env.get(name):
            errors.append('Missing external model identity: '+name)
    if config['services']['worker'].get('environment', {}) != app_env:
        # Compare only inference contract keys; unrelated worker settings may differ.
        worker_env = config['services']['worker'].get('environment', {})
        for name in ('EDITOR_MODEL_BACKEND','EDITOR_MODEL_BASE_URL','EDITOR_MODEL_NAME',
                     'EDITOR_OCR_VL_BASE_URL','EDITOR_OCR_VL_MODEL','EDITOR_OCR_VL_REVISION'):
            if worker_env.get(name) != app_env.get(name):
                errors.append('API/worker external model configuration differs: '+name)
if (root/'backend/editor/reread_queue.py').is_file():
    for service in ('reread-storage-init','reread-worker'):
        if service not in config['services']:
            errors.append('Automatic regional OCR requires compose.reread.yaml: missing '+service)
    mounts = config['services'].get('worker',{}).get('volumes',[])
    if not any(mount.get('target') == '/data/reread-queue' and not mount.get('read_only',False)
               for mount in mounts):
        errors.append('Analysis worker requires a writable regional OCR queue volume.')
networks = subprocess.check_output(['docker','network','ls','-q'],text=True).split()
owned_bridges = set()
occupied = []
if networks:
    for network in json.loads(subprocess.check_output(['docker','network','inspect',*networks])):
        if (network.get('Labels') or {}).get('com.docker.compose.project') == config['name']:
            owned_bridges.add('br-'+network['Id'][:12])
        else:
            for item in network.get('IPAM',{}).get('Config') or []:
                if ':' not in item.get('Subnet','') and item.get('Subnet'):
                    occupied.append(ipaddress.ip_network(item['Subnet']))
for route in json.loads(subprocess.check_output(['ip','-j','-4','route','show'])):
    if route.get('dst','default') != 'default' and route.get('dev') not in owned_bridges:
        occupied.append(ipaddress.ip_network(route['dst'],strict=False))
planned = [ipaddress.ip_network(config['networks'][name]['ipam']['config'][0]['subnet']) for name in ('private','ingress')]
if planned[0].overlaps(planned[1]):
    errors.append('Editor private and ingress networks overlap.')
for network in planned:
    for other in occupied:
        if network.overlaps(other):
            errors.append(f'Editor subnet {network} conflicts with host/VPN/Docker route {other}; choose another EDITOR_*_SUBNET.')
usage = shutil.disk_usage(root)
if usage.free < 20 * 1024**3:
    errors.append('At least 20 GiB free disk required for foundation images and initial artifacts; model space is additional.')
mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
if int(mem['MemAvailable'].split()[0]) < 8 * 1024**2:
    errors.append('At least 8 GiB available RAM required for the bounded document tooling.')
# Inspect resolved active services: GPU mode retains embedding/reranker under
# the models profile but deliberately excludes the CPU llm service.
if 'llm' in config['services']:
    if int(mem['MemAvailable'].split()[0]) < 48 * 1024**2:
        errors.append('The CPU model service needs 48 GiB available RAM including document and service headroom.')
for service_name in ('llm', 'embedding', 'reranker'):
    service = config['services'].get(service_name)
    if not service:
        continue
    command = service.get('command', [])
    if not isinstance(command, list):
        errors.append('Model command must be an argument list: '+service_name)
        continue
    for index, argument in enumerate(command):
        if argument not in ('--model', '--mmproj'):
            continue
        if index + 1 >= len(command):
            errors.append('Missing model path argument: '+service_name+' '+argument)
            continue
        model_path = Path(command[index + 1])
        mounts = [mount for mount in service.get('volumes', [])
                  if mount.get('type') == 'bind'
                  and model_path.is_relative_to(mount.get('target', '/__unmounted__'))]
        if not mounts:
            errors.append('Offline model is not supplied by a host bind mount: '+service_name+' '+str(model_path))
            continue
        mount = max(mounts, key=lambda item: len(item['target']))
        host_path = Path(mount['source']) / model_path.relative_to(mount['target'])
        if not host_path.is_file():
            errors.append('Missing offline model for '+service_name+': '+str(host_path))
running = subprocess.check_output(['docker', 'compose', 'ps', '-q'], text=True).strip()
if not running:
    for port in (int(settings['EDITOR_PORT']), int(settings['EDITOR_METRICS_PORT'])):
        with socket.socket() as sock:
            try:
                sock.bind((settings.get('EDITOR_BIND', '127.0.0.1'), port))
            except OSError:
                errors.append(f'Port {port} is already used.')
print(json.dumps({'host': platform.node(), 'architecture': platform.machine(), 'cpu_logical': os.cpu_count(),
                  'load': os.getloadavg(), 'disk_free_bytes': usage.free,
                  'memory_available_kib': int(mem['MemAvailable'].split()[0]), 'errors': errors}, indent=2))
sys.exit(bool(errors))
