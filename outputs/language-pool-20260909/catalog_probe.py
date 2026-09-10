import json
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_layer.catalog import one_entity_per_pattern
s=SemanticSettings.from_env(); store=open_store(s.store_dsn,create=False)
ps=one_entity_per_pattern(store.list_profiles(s.datasource_id),store.concept_entities(s.tenant_id,s.datasource_id))
print(json.dumps(sorted({p.entity for p in ps if any(x in p.entity for x in ['ORF','STLINE','INVOICE','CLCARD','ITEMS','PAYPLAN','SLSMAN'])})))

from semantic_layer.runtime.language_pool import schema_documents
import sys
sys.path.insert(0,"/tmp")
from build_language_pool import batches
for i,(job,ctx) in enumerate(batches(schema_documents(ps),["CLCARD","INVOICE","ITEMS","LG_ORFLINE","ORFICHE","PAYPLANS","SLSMAN","STLINE"],48)):
 if i>=8: break
 print(json.dumps({"root":next(iter(ctx)),"chars":len(json.dumps(ctx,ensure_ascii=False)),"columns":{e:len(d["columns"]) for e,d in ctx.items()}}))
