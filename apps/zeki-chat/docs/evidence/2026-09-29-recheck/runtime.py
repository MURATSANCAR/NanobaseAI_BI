import json, subprocess, datetime
from pathlib import Path
d=Path('/tmp/codex-zeki-recheck')
def run(*args,timeout=20):
 p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
 return {'status':p.returncode,'output':p.stdout.strip(),'error':p.stderr.strip()}
containers={}
for name in ['zeki-chat','zeki-mongo','zeki-ingress']:
 c=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
 containers[name]={'image':c['Config']['Image'],'dns':c['HostConfig']['Dns'],'networks':list(c['NetworkSettings']['Networks']),'running':c['State']['Running']}
 assert containers[name]['dns']==['127.0.0.1'] and containers[name]['running']
gateway=json.loads(subprocess.check_output(['docker','network','inspect','zeki-local'],text=True))[0]['IPAM']['Config'][0]['Gateway']
subprocess.run(['docker','cp',str(d/'verify-network.cjs'),'zeki-chat:/tmp/zeki-recheck-network.cjs'],check=True)
try:
 p=run('docker','exec','-e','ZEKI_PROBE_GATEWAY='+gateway,'zeki-chat','node','/tmp/zeki-recheck-network.cjs',timeout=45)
 network=json.loads(p['output']);assert p['status']==0 and network['allPassed']
 (d/'network-evidence.json').write_text(json.dumps(network,indent=2))
finally: subprocess.run(['docker','exec','--user','0','zeki-chat','rm','-f','/tmp/zeki-recheck-network.cjs'],check=True)
mongo=run('docker','exec','zeki-mongo','mongosh','--quiet','zeki','--eval',"(async () => { try { await require('node:dns').promises.lookup('cloud.rocket.chat'); print('EXTERNAL_DNS_OPEN'); quit(1); } catch(e) { print('EXTERNAL_DNS_BLOCKED:'+e.code); } })()")
assert mongo['status']==0 and 'EXTERNAL_DNS_BLOCKED' in mongo['output']
inside=run('docker','exec','zeki-ingress','nslookup','zeki-chat')
outside=run('docker','exec','zeki-ingress','nslookup','cloud.rocket.chat')
http=run('docker','exec','zeki-ingress','wget','-T','4','-O','/dev/null','http://1.1.1.1')
assert inside['status']==0 and outside['status']!=0 and http['status']!=0
rules={}
for tool in ['iptables','ip6tables']:
 rules[tool]={}
 for chain in ['ZEKI-LOCAL-HOST','ZEKI-LOCAL-EGRESS']:
  p=run('sudo','-n',tool,'-S',chain);assert p['status']==0
  lines=p['output'].splitlines();returns=[x for x in lines if '-j RETURN' in x]
  assert len(returns)==1 and '--ctdir REPLY' in returns[0] and any('-j REJECT' in x for x in lines)
  rules[tool][chain]=lines
ordering=run('systemctl','show','zeki-local-egress.service','-p','After','-p','Before','-p','ActiveState','-p','UnitFileState')
assert 'ActiveState=active' in ordering['output'] and 'ufw.service' in ordering['output'] and 'docker.service' in ordering['output']
r={'observedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'containers':containers,'mongoExternalDns':mongo,'ingressInternalDns':inside,'ingressExternalDns':outside,'ingressExternalHttp':http,'rules':rules,'service':ordering,'allPassed':True}
(d/'runtime-evidence.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
