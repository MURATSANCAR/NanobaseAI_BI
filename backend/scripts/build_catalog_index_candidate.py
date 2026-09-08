"""Build a new, verified Qdrant collection without deleting the current one.

Deduplicates identical entity/column meanings across fiscal copies. Reuses vectors for
exact text matches from the previous collection; all other texts are embedded afresh.
"""
from __future__ import annotations
import argparse
import json
import math
import gzip
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from index_catalog_qdrant import _http_json, points_for, embed, QDRANT_URL, VECTOR_SIZE, Point
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store


def catalog_points(profiles):
    unique={}
    generated=points_for(profiles)
    for profile in profiles:
        for col in profile.columns:
            if not (col.meaning() or '').strip():
                generated.append(Point(0,profile.entity,profile.table_name,col.name,
                                       f'{profile.entity}.{col.name} — SQL tipi: {col.data_type}'))
    for point in generated:
        # Column text already includes entity. Keep table points from each physical copy,
        # since columns present can differ by year. Identical column meanings need one vector.
        unique.setdefault((point.entity,point.column,point.text),point)
    points=list(unique.values())
    expected={(p.entity,c.name) for p in profiles for c in p.columns}
    represented={(p.entity,p.column) for p in points if p.column}
    if not expected.issubset(represented):raise RuntimeError('Unindexed catalog columns')
    for i,point in enumerate(points,1):point.id=i
    if not points:raise SystemExit('Empty candidate')
    return points,expected


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collection',required=True)
    p.add_argument('--previous',required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    existing=_http_json('GET',QDRANT_URL+'/collections')['result']['collections']
    present=args.collection in {c['name'] for c in existing}
    if present and _http_json('GET',QDRANT_URL+'/collections/'+args.collection)['result']['points_count']:
        raise SystemExit('Candidate already has points; choose a fresh collection name')
    s=SemanticSettings.from_env();store=open_store(s.store_dsn,create=False)
    profiles=one_entity_per_pattern(store.list_profiles(s.datasource_id),store.concept_entities(s.tenant_id,s.datasource_id))
    points,expected=catalog_points(profiles)
    cached={};offset=None
    while True:
        body={'limit':256,'with_payload':True,'with_vector':True}
        if offset is not None:body['offset']=offset
        result=_http_json('POST',QDRANT_URL+'/collections/'+args.previous+'/points/scroll',body)['result']
        for row in result['points']:
            vector=row.get('vector');text=row.get('payload',{}).get('text')
            if text and isinstance(vector,list) and len(vector)==VECTOR_SIZE:cached[text]=vector
        offset=result.get('next_page_offset')
        if offset is None:break
    # A matching text is reusable only when the current embedding model agrees with the old one.
    sample=list(cached)[:3]
    key=os.environ.get('BI_EMBED_API_KEY') or os.environ.get('CONTRACT_API_KEY','')
    if sample:
        checked=embed(sample,key)
        def cosine(a,b):
            return sum(x*y for x,y in zip(a,b))/(math.sqrt(sum(x*x for x in a))*math.sqrt(sum(y*y for y in b)))
        if len(checked)!=len(sample) or any(cosine(cached[t],v)<0.999 for t,v in zip(sample,checked)):
            cached.clear()
    missing=list(dict.fromkeys(p.text for p in points if p.text not in cached))
    missing_set=set(missing)
    print(json.dumps({'points':len(points),'reuse':len(points)-sum(p.text in missing_set for p in points),'new_texts':len(missing)}),flush=True)
    checkpoint=args.out.with_suffix('.vectors.json.gz')
    if checkpoint.exists():
        with gzip.open(checkpoint,'rt') as f: saved=json.load(f)
        cached.update(saved)
        missing=list(dict.fromkeys(p.text for p in points if p.text not in cached))
    fresh=embed(missing,os.environ.get('BI_EMBED_API_KEY') or os.environ.get('CONTRACT_API_KEY',''))
    if len(fresh)!=len(missing) or any(len(v)!=VECTOR_SIZE for v in fresh):raise RuntimeError('Incomplete embedding response')
    cached.update(zip(missing,fresh))
    with gzip.open(checkpoint,'wt',compresslevel=1) as f:json.dump({p.text:cached[p.text] for p in points},f)
    if not present:
        _http_json('PUT',QDRANT_URL+'/collections/'+args.collection,{'vectors':{'size':VECTOR_SIZE,'distance':'Cosine'}})
    for i in range(0,len(points),256):
        batch=[{'id':p.id,'vector':cached[p.text],'payload':{'entity':p.entity,'table':p.table,'column':p.column,'text':p.text}} for p in points[i:i+256]]
        _http_json('PUT',QDRANT_URL+'/collections/'+args.collection+'/points?wait=true',{'points':batch})
    info=_http_json('GET',QDRANT_URL+'/collections/'+args.collection)['result']
    if info['points_count']!=len(points):raise RuntimeError('Point count mismatch')
    result={'collection':args.collection,'points':len(points),'entities':len({p.entity for p in points}),'column_pairs':len(expected),'unindexed_columns':len(expected-represented),'new_texts':len(missing),'status':info['status']}
    args.out.write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()
