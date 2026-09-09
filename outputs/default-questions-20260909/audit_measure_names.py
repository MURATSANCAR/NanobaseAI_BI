import json,collections
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_layer.normalize import normalize_term
s=SemanticSettings.from_env();store=open_store(s.store_dsn,create=False);names=collections.defaultdict(list)
for c in store.find_concepts(s.tenant_id,s.datasource_id,limit=10000):
 if c.status!='CERTIFIED' or c.semantic_type!='METRIC':continue
 maps=store.list_mappings(c.id)
 signature=sorted([(m.entity,m.column,m.formula,json.dumps(m.extra or {},sort_keys=True)) for m in maps],key=str)
 for name in set([c.term]+c.synonyms):
  names[normalize_term(name)].append({'id':c.id,'term':c.term,'version':c.version,'signature':signature})
out=[{'name':name,'senses':list({x['id']:x for x in senses}.values())} for name,senses in names.items() if len({json.dumps(x['signature'],sort_keys=True) for x in senses})>1]
Path('/data/nanobaseai/bi/backups/default-questions-20260909/measure-name-collisions.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False))
