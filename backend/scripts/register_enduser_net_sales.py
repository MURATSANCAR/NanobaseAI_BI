"""Bind net-sales phrases to the existing certified invoice/line net-revenue definitions."""
import json,os
from dataclasses import asdict,replace
from pathlib import Path
from semantic_bridge.app import build_runtime
from semantic_layer.models import Mapping,SemanticType
os.environ['SEMANTIC_REFRESH_SEC']='0'
r=build_runtime();s=r.store;t=r.settings.tenant_id;d=r.settings.datasource_id
backup=Path('/data/nanobaseai/bi/backups/enduser-real-10000-20260909/net-sales-bindings.json')
assert not backup.exists(), 'This metadata release already has a backup'
concepts=s.find_concepts(t,d,limit=10000)
source=[c for c in concepts if c.term=='net ciro' and c.status=='CERTIFIED']
assert len(source)==2
bindings=[(c,m) for c in source for m in s.list_mappings(c.id)]
assert {m.entity for c,m in bindings}=={'INVOICE','STLINE'}
change={'before':[{'concept':asdict(c),'mappings':[asdict(m) for m in s.list_mappings(c.id)]} for c in concepts if c.term in ('net ciro','net satış tutarı','toptan net satış tutarı','perakende net satış tutarı','satis tutari')], 'created':[], 'policy':'Existing certified net ciro: returns deducted; invoice grain for totals, existing LINENET line grain for product breakdowns. Retail returns code 2, wholesale returns code 3.'}
backup.write_text(json.dumps(change,ensure_ascii=False,default=str))
for c,m in bindings:
 for term,codes in [('net satış tutarı',None),('toptan net satış tutarı','3,8'),('perakende net satış tutarı','2,7')]:
  extra=dict(m.extra)
  if codes:
   extra['conditions']=[x for x in extra.get('conditions',[]) if '.TRCODE ' not in x]+[f'{m.entity}.TRCODE IN ({codes})']
  extra['definition_source']='Existing certified net ciro '+c.id
  fields=asdict(m);fields.pop('id');fields.update(concept_id='',extra=extra)
  fresh=Mapping(**fields)
  new,_=s.upsert_concept(t,d,term,SemanticType.METRIC,mapping=fresh,status='CERTIFIED')
  s.update_concept(new.id,status='CERTIFIED',bump_version=True)
  change['created'].append(new.id);backup.write_text(json.dumps(change,ensure_ascii=False,default=str))
print(json.dumps({'bindings':len(change['created'])}))
