#!/usr/bin/env python3
"""Two-page real-source calibration, isolated from analysis records and model service.

No expected answer, correction or review is supplied. The request body must match
the recorded baseline exactly. CPU/slot configuration is reported separately.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[1]; os.chdir(root)
gen = str(uuid.UUID(sys.argv[1]))
pages = [int(x) for x in sys.argv[2].split(',')]
if len(pages) != 2 or len(set(pages)) != 2 or min(pages) < 1:
    raise SystemExit('Specify exactly two distinct real PDF pages')
config = json.loads(subprocess.check_output(['docker', 'compose', 'config', '--format', 'json']))
service = config['services']['llm']; name = config['name'] + '-vision-budget-probe'
command = list(service['command'])
for flag, value in {'--ctx-size': '8192', '--threads': '8', '--threads-batch': '8',
                    '--parallel': '1', '--image-max-tokens': '1024'}.items():
    command[command.index(flag) + 1] = value
models = next(v['source'] for v in service['volumes'] if v['target'] == '/models')
subprocess.run(['docker', 'run', '-d', '--name', name, '--network', config['networks']['private']['name'],
    '--user', '10001:10001', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
    '--tmpfs', '/tmp:size=64m,mode=1777', '--cpus', '8', '--cpu-shares', '64', '--memory', '32g',
    '--pids-limit', '256', '--log-opt', 'max-size=10m', '--log-opt', 'max-file=2',
    '-v', models + ':/models:ro', service['image'], *command], check=True, stdout=subprocess.DEVNULL)
code = r'''
import base64,json,time,sys
import httpx
from editor.analysis import SYSTEM,sha
from editor.book_store import get_records,ROOT,source_for
gen,host,page_arg=sys.argv[1:]; pages=[int(p) for p in page_arg.split(',')]
visuals={r['data']['pdf_page']:r for r in get_records(gen,'visuals')}
source=source_for(gen); started=time.monotonic()
with httpx.Client(timeout=5,trust_env=False) as client:
 while time.monotonic()-started<600:
  try:
   if client.get('http://'+host+':8080/health').status_code==200: break
  except httpx.HTTPError: pass
  time.sleep(2)
 else: raise RuntimeError('PROBE_MODEL_NOT_READY')
print(json.dumps({'probe_ready_seconds':round(time.monotonic()-started,3)}),flush=True)
prompt=('Sayfanın görünür kompozisyonunu Türkçe kısaca betimle. Kişileri görünüşleriyle, '
        'nesneleri ve eylemi belirt. Görünen konuşma balonunu aynen oku; okunamıyorsa söyle. '
        'Hayal/etkinlik işaretlerini belirt. İsim veya göz rengi gibi belirsiz küçük ayrıntıları tahmin etme. '
        'Metindeki olayları özetleme; olay çıkarımı ayrı aşamadadır. Görünür olmayan anlam ekleme. '
        'En fazla 100 kelime.')
for page in pages:
 baseline=visuals[page]; raw=(ROOT/source['sha256']/f'page-{page:04}.png').read_bytes()
 assert sha(raw)==baseline['data']['render_sha256']
 body={'model':'editor-qwen38','temperature':0,'seed':17,'max_tokens':384,
       'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':[
       {'type':'text','text':prompt},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(raw).decode()}}]}]}
 digest=sha(json.dumps(body,ensure_ascii=False).encode())
 assert digest==baseline['data']['metrics']['request_sha256'], 'PROBE_REQUEST_DIFFERS_FROM_BASELINE'
 started=time.monotonic()
 with httpx.Client(timeout=1800,trust_env=False) as client:
  response=client.post('http://'+host+':8080/v1/chat/completions',json=body);response.raise_for_status()
 result=response.json()
 print(json.dumps({'generation_id':gen,'pdf_page':page,'baseline_record_id':str(baseline['id']),
       'request_sha256':digest,'identical_request':True,'image_max_tokens':1024,'cpu_threads':8,
       'seconds':round(time.monotonic()-started,3),'result':result,'application_writes':0},ensure_ascii=False),flush=True)
'''
out = root / 'evidence' / 'visual-budget-probe.jsonl'
try:
    with out.open('x') as stream:
        out.chmod(0o600)
        stream.write(json.dumps({'image': service['image'], 'command': command,
                                'cpu_limit': 8, 'memory_limit_gib': 32, 'pages': pages}) + '\n')
        stream.flush()
        subprocess.run(['docker', 'compose', 'exec', '-T', 'api', 'python', '-c', code,
                        gen, name, ','.join(map(str, pages))], stdout=stream, check=True, timeout=4200)
    print(json.dumps({'probe_complete': True, 'output': str(out), 'application_writes': 0}), flush=True)
finally:
    subprocess.run(['docker', 'rm', '-f', name], check=True, stdout=subprocess.DEVNULL)
