"""Remove certified quantity/ratio name collisions without changing measure formulas."""
import json
from dataclasses import asdict
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_layer.normalize import normalize_term

s=SemanticSettings.from_env();store=open_store(s.store_dsn,create=False)
backup=Path('/data/nanobaseai/bi/backups/default-questions-20260909/return-measure-names.before.json')
changes=[]
for c in store.find_concepts(s.tenant_id,s.datasource_id,limit=10000):
 if c.status!='CERTIFIED':continue
 maps=store.list_mappings(c.id)
 if normalize_term(c.term)==normalize_term('iade adedi') and any(m.entity=='STLINE' and (m.extra or {}).get('func')=='RATIO' and '/ NULLIF' in (m.formula or '') for m in maps):
  changes.append((c,maps,{'status':'DEPRECATED'}))
 elif normalize_term(c.term)==normalize_term('iade orani') and 'iade adet' in c.synonyms:
  changes.append((c,maps,{'synonyms':[name for name in c.synonyms if name!='iade adet']}))
if changes:
 if backup.exists():raise RuntimeError('Backup already exists; inspect previous run before changing catalog')
 backup.write_text(json.dumps([{'concept':asdict(c),'mappings':[asdict(m) for m in maps],'change':change} for c,maps,change in changes],ensure_ascii=False,indent=2,default=str))
 for c,maps,change in changes:store.update_concept(c.id,bump_version=True,**change)
print(json.dumps({'changed':len(changes),'policy':'Quantity names must not select the ratio formula; the correctly named ratio remains available.'}))
