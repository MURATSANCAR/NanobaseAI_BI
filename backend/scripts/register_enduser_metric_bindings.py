import json
from dataclasses import asdict
from pathlib import Path
from semantic_bridge.app import build_runtime
from semantic_layer.models import Mapping,SemanticType
from semantic_layer.normalize import normalize_term
r=build_runtime();s=r.store;t=r.settings.tenant_id;d=r.settings.datasource_id
p=Path('/data/nanobaseai/bi/backups/enduser-10000-dimensions-20260909/metric-bindings.json')
if p.exists():
 prior=json.loads(p.read_text());assert not prior.get('created') and 'before' not in prior
changes={'created':[],'definition':'Sold item sales lines exclude cancellations, discounts/services and returns. Retail sales code is 7; wholesale is 8.'}
p.write_text(json.dumps(changes))
items=[('satış satırı sayısı',SemanticType.METRIC,Mapping('','STLINE','DBO_LG_{n0}_{n1}_STLINE',formula='COUNT(STLINE.LOGICALREF)',extra={'func':'COUNT','conditions':['STLINE.LINETYPE = (0)','STLINE.TRCODE IN (7,8)'],'definition_source':'Logo STLINE dictionary; count of sold material rows, returns excluded'})),
('perakende',SemanticType.DIMENSION_VALUE,Mapping('','STLINE','DBO_LG_{n0}_{n1}_STLINE',column='TRCODE',operator='IN',values=['7'])),
('perakende',SemanticType.DIMENSION_VALUE,Mapping('','INVOICE','DBO_LG_{n0}_{n1}_INVOICE',column='TRCODE',operator='IN',values=['7']))]
changes['before']=[{'concept':asdict(c),'mappings':[asdict(z) for z in s.list_mappings(c.id)]} for c in s.find_concepts(t,d,limit=10000) if c.normalized_term in {normalize_term(term) for term,typ,m in items}]
p.write_text(json.dumps(changes,ensure_ascii=False,default=str))
for term,typ,m in items:
 c,_=s.upsert_concept(t,d,term,typ,mapping=m,status='CERTIFIED')
 s.update_concept(c.id,status='CERTIFIED',bump_version=True)
 changes['created'].append({'concept':asdict(c),'mapping':asdict(m)});p.write_text(json.dumps(changes,ensure_ascii=False,default=str))
print(json.dumps({'created':len(changes['created'])}))
