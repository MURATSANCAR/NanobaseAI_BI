"""Add the line-grain sales measure using the already certified net-revenue line basis."""
import os,json
from dataclasses import asdict
from pathlib import Path
from semantic_bridge.app import build_runtime
from semantic_layer.models import Mapping,SemanticType
os.environ['SEMANTIC_REFRESH_SEC']='0'
r=build_runtime();s=r.store;t=r.settings.tenant_id;d=r.settings.datasource_id
p=Path('/data/nanobaseai/bi/backups/enduser-real-10000-20260909/line-sales-binding.json')
assert not p.exists()
concepts=s.find_concepts(t,d,limit=10000)
source=[(c,m) for c in concepts if c.term=='net ciro' and c.status=='CERTIFIED' for m in s.list_mappings(c.id) if m.entity=='STLINE']
assert len(source)==1
c,m=source[0]
assert 'STLINE.LINENET' in m.formula
before=[{'concept':asdict(c),'mappings':[asdict(m) for m in s.list_mappings(c.id)]} for c in concepts if c.normalized_term=='satis tutar']
change={'before':before,'source':asdict(m),'policy':'Product breakdown uses the existing certified LINENET line basis; sales exclude returns, net sales deduct returns. Invoice-only totals retain existing NETTOTAL definition.'}
p.write_text(json.dumps(change,ensure_ascii=False,default=str))
mapping=Mapping('', 'STLINE',m.table_pattern,formula='SUM(STLINE.LINENET)',extra={'func':'SUM','grain':'STLINE','conditions':['STLINE.LINETYPE = (0)','STLINE.TRCODE IN (7,8)'],'definition_source':'Positive-sales counterpart of certified net ciro '+c.id})
new,created=s.upsert_concept(t,d,'satis tutari',SemanticType.METRIC,mapping=mapping,status='CERTIFIED')
s.update_concept(new.id,status='CERTIFIED',bump_version=True)
change.update(concept_id=new.id,created=created);p.write_text(json.dumps(change,ensure_ascii=False,default=str));print(json.dumps({'concept_id':new.id,'created':created}))
