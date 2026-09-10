"""Register documented reporting dimensions and repair global Logo references.

Run on the production host after deploying reference-contract support. Backs up
only the profiles/concepts it changes. No customer transaction is written.
"""
from __future__ import annotations
import json,os,re,time
from pathlib import Path
from dataclasses import asdict
os.environ['SEMANTIC_REFRESH_SEC']='0'
from semantic_bridge.app import build_runtime
from semantic_layer.models import Mapping,SemanticType
from semantic_layer.profiler.logo_dictionary import foreign_keys

r=build_runtime();store=r.store;tenant=r.settings.tenant_id;ds=r.settings.datasource_id
backup=Path('/data/nanobaseai/bi/backups/enduser-10000-dimensions-20260909');backup.mkdir(exist_ok=False)
profiles=store.list_profiles(ds);by_name={p.table_name:p for p in profiles}
changes={'profiles':[],'concepts':[],'created':[],'policy':{
 'payment':'line-specific plan when nonzero, otherwise invoice plan; unresolved reference retained as NULL',
 'salesperson':'invoice salesperson for invoice-based sales reporting',
 'customer':'invoice customer for invoice-based sales reporting',
 'source_payment':'https://www.sdmyazilim.com.tr/var/uploads/1500469815-finans.pdf',
 'source_salesperson':'https://www.sdmyazilim.com.tr/var/uploads/1500477553-fatura.pdf'}}
def save(): (backup/'changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2,default=str))
save()

def via(column,primary=None):
 rule={'via':'INVOICE','via_column':'INVOICEREF','via_key':'LOGICALREF','fallback_column':column,'target_column':'LOGICALREF'}
 if primary:rule.update(primary_column=primary,empty_value=0)
 return {'join_kind':'LEFT','reference_resolution':{'STLINE':rule}}
items=[
 ('müşteri','CLCARD','LG_411_CLCARD','DEFINITION_',via('CLIENTREF')),
 ('ödeme planı','PAYPLANS','LG_411_PAYPLANS','DEFINITION_',via('PAYDEFREF','PAYDEFREF')),
 ('fatura ödeme planı','PAYPLANS','LG_411_PAYPLANS','DEFINITION_',via('PAYDEFREF')),
 ('satış temsilcisi','SLSMAN','LG_SLSMAN','DEFINITION_',via('SALESMANREF')),
 ('teslimat şehri','SHIPINFO','LG_411_SHIPINFO','CITY',via('SHIPINFOREF')),
 ('birim','UNITSETL','LG_411_UNITSETL','NAME',{'join_kind':'LEFT'}),
]
# Validate all proposed bindings before the first metadata write.
from semantic_layer.normalize import normalize_term
old=store.find_concepts(tenant,ds,semantic_type=SemanticType.COLUMN,limit=10000)
for term,entity,physical,column,extra in items:
 p=by_name[physical]
 assert p.column(column) and p.primary_key, physical
 matches=[c for c in old if c.normalized_term==normalize_term(term)]
 assert len(matches)<=1, term
 if matches:
  existing=store.list_mappings(matches[0].id)
  assert len(existing)==1 and existing[0].column==column and existing[0].table_pattern==p.table_pattern,term
assert 'LG_SLSMAN' in by_name
# The workbook explicitly declares both SALESMANREF -> LG_SLSMAN relationships.
keys=foreign_keys(list(by_name))
for p in profiles:
 if not re.fullmatch(r'LG_\d+_\d+_(STLINE|INVOICE)',p.table_name):continue
 found=[k for k in keys if k['table']==p.table_name and k['column']=='SALESMANREF' and k['ref_table']=='LG_SLSMAN']
 if not found or not p.column('SALESMANREF'):continue
 edge={'column':'SALESMANREF','ref_entity':by_name['LG_SLSMAN'].entity,'ref_column':'LOGICALREF'}
 if edge in p.relationships:continue
 changes['profiles'].append(asdict(p));save()
 p.relationships=[e for e in p.relationships if e['column']!='SALESMANREF']+[edge]
 store.upsert_profile(p)

for term,entity,physical,column,extra in items:
 p=by_name[physical];assert p.column(column) and p.primary_key
 extra={**extra,'definition_source':changes['policy'],'registered_by':'enduser-10000-20260909'}
 mapping=Mapping('',entity,p.table_pattern,column=column,operator='COLUMN',extra=extra)
 old=store.find_concepts(tenant,ds,semantic_type=SemanticType.COLUMN,limit=10000)
 from semantic_layer.normalize import normalize_term
 matches=[c for c in old if c.normalized_term==normalize_term(term)]
 if matches:
  assert len(matches)==1, f'Ambiguous existing sense: {term}'
  c=matches[0];existing=store.list_mappings(c.id)
  assert len(existing)==1 and existing[0].column==column and existing[0].table_pattern==p.table_pattern,term
  changes['concepts'].append({'concept':asdict(c),'mappings':[asdict(m) for m in existing]});save()
  store.replace_mappings(c.id,[mapping]);store.update_concept(c.id,status='CERTIFIED',explain={'definition':changes['policy']},bump_version=True)
 else:
  c,_=store.upsert_concept(tenant,ds,term,SemanticType.COLUMN,mapping=mapping,status='CERTIFIED')
  changes['created'].append(c.id);save()
  store.update_concept(c.id,explain={'definition':changes['policy']},bump_version=True)
changes['completed_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z');save()
print(json.dumps({'profiles_updated':len(changes['profiles']),'concepts_created':len(changes['created']),'concepts_updated':len(changes['concepts']),'completed_at':changes['completed_at']}))
