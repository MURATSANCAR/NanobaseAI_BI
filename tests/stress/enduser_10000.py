"""10,000 generated end-user questions, executed against an independent row oracle.

This is controlled acceptance data, not 10,000 unseen human questions or production
data accuracy. Uses the unmodified Runtime.ask path; --llm enables the actual model
fallback. Without it a fallback is explicitly recorded as untested, never a pass.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from semantic_layer.models import SchemaProfile, ColumnProfile, Mapping, SemanticType, ConceptStatus
from semantic_layer.store.catalog_store import open_store
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import SQLiteConnector

MONTHS = 'Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık'.split()
DIMS = {'müşteri': ('CLCARD', 'DEFINITION_', 'customer'),
        'ürün': ('ITEMS', 'NAME', 'product'),
        'ödeme planı': ('PAYPLANS', 'DEFINITION_', 'payment'),
        'satış temsilcisi': ('SLSMAN', 'DEFINITION_', 'salesperson'),
        'teslimat şehri': ('SHIPINFO', 'CITY', 'delivery'),
        'birim': ('UNITSETL', 'NAME', 'unit')}
METRICS = {
    'satılan adet': ('SUM(STLINE.AMOUNT)', 'quantity'),
    'satış tutarı': ('SUM(STLINE.LINENET)', 'amount'),
    'satış satırı sayısı': ('COUNT(STLINE.LOGICALREF)', 'count'),
    'net satış tutarı': ('SUM(CASE WHEN STLINE.TRCODE IN (2,3) THEN -STLINE.LINENET ELSE STLINE.LINENET END)', 'net'),
}


def corpus():
    cases = []
    combinations = list(itertools.product(range(2022, 2027), range(1, 13), METRICS, ('', 'toptan', 'perakende'), range(4)))
    balanced = [combinations[i * len(combinations) // 2000] for i in range(2000)]
    for level in range(1, 6):
        for i, (year, month, metric, kind, voice) in enumerate(balanced):
            dimensions = {1: [], 2: ['ürün'], 3: ['müşteri', 'ürün'],
                          4: ['müşteri', 'ürün', 'ödeme planı', 'satış temsilcisi'],
                          5: ['müşteri', 'ürün', 'ödeme planı', 'satış temsilcisi', 'teslimat şehri'] + (['birim'] if i % 2 else [])}[level]
            group = (', '.join(dimensions[:-1]) + ' ve ' + dimensions[-1] if len(dimensions) > 1 else ''.join(dimensions))
            by = group + ' bazında ' if group else ''
            core = ' '.join(x for x in (kind, metric) if x)
            period = f'{MONTHS[month - 1]} {year}'
            templates = [f'{period} {by}{core} nedir?',
                         f'{period} için {by}{core} göster.',
                         f'{by.capitalize()}{period} {core} hesapla.',
                         f'{period} dönemindeki {core} bilgisini {by}raporla.']
            tables = {'STLINE'} | {DIMS[d][0] for d in dimensions}
            if any(t in tables for t in ('CLCARD', 'PAYPLANS', 'SLSMAN', 'SHIPINFO')):
                tables.add('INVOICE')
            cases.append({'id': f'P{len(cases) + 1:05d}', 'level': level,
                          'prompt': templates[voice], 'year': year, 'month': month,
                          'metric': metric, 'kind': kind, 'dimensions': dimensions,
                          'expected_tables': sorted(tables), 'expected_table_count': len(tables),
                          'expected_joins': len(tables) - 1,
                          'family': f'L{level}-{METRICS[metric][1]}-{len(tables)}tables',
                          'origin': 'generated controlled matrix',
                          'live_status': 'NOT_LIVE_TESTED'})
    assert len(cases) == len({c['prompt'] for c in cases}) == 10000
    return cases


def fixture():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    schema = {
        'STLINE': [('LOGICALREF','INTEGER'),('INVOICEREF','INTEGER'),('STOCKREF','INTEGER'),('UOMREF','INTEGER'),('DATE_','DATE'),('TRCODE','INTEGER'),('CANCELLED','INTEGER'),('LINETYPE','INTEGER'),('AMOUNT','REAL'),('LINENET','REAL')],
        'INVOICE': [('LOGICALREF','INTEGER'),('CLIENTREF','INTEGER'),('PAYDEFREF','INTEGER'),('SALESMANREF','INTEGER'),('SHIPINFOREF','INTEGER')],
        'CLCARD': [('LOGICALREF','INTEGER'),('DEFINITION_','TEXT')],
        'ITEMS': [('LOGICALREF','INTEGER'),('NAME','TEXT')],
        'PAYPLANS': [('LOGICALREF','INTEGER'),('DEFINITION_','TEXT')],
        'SLSMAN': [('LOGICALREF','INTEGER'),('DEFINITION_','TEXT')],
        'SHIPINFO': [('LOGICALREF','INTEGER'),('CITY','TEXT')],
        'UNITSETL': [('LOGICALREF','INTEGER'),('NAME','TEXT')],
    }
    physical = {e: f'LG_411_01_{e}' if e in ('STLINE','INVOICE') else f'LG_411_{e}' for e in schema}
    edges = {'STLINE': [('INVOICEREF','INVOICE'),('STOCKREF','ITEMS'),('UOMREF','UNITSETL')],
             'INVOICE': [('CLIENTREF','CLCARD'),('PAYDEFREF','PAYPLANS'),('SALESMANREF','SLSMAN'),('SHIPINFOREF','SHIPINFO')]}
    labels = {}
    for entity, cols in schema.items():
        conn.execute(f'CREATE TABLE {physical[entity]} (' + ','.join(f'{n} {t}' + (' PRIMARY KEY' if n == 'LOGICALREF' else '') for n,t in cols) + ')')
    for term, (entity, col, key) in DIMS.items():
        labels[key] = {i: key + '-' + str(i) for i in range(1, 7)}
        conn.executemany(f'INSERT INTO {physical[entity]} VALUES (?,?)', labels[key].items())
    facts = []
    inv = line = 0
    for year, month, order in itertools.product(range(2022,2027),range(1,13),range(12)):
        inv += 1
        customer, payment, person, delivery = (order % 6 + 1, (order * 3 + month) % 6 + 1,
                                              (order + month) % 6 + 1, (order * 5 + year) % 6 + 1)
        conn.execute(f'INSERT INTO {physical["INVOICE"]} VALUES (?,?,?,?,?)', (inv,customer,payment,person,delivery))
        for offset in range(3):
            line += 1
            product, unit = (order + offset) % 6 + 1, (order + offset * 2) % 6 + 1
            code = (7,8,2,3)[(order + offset) % 4]
            cancelled = int(order == 11)
            line_type = int(order == 10 and offset == 2)
            qty = ((year - 2021) * 7 + month + order + offset) % 19 + 1
            amount = qty * (101 + product * 13 + unit * 3 + offset)
            conn.execute(f'INSERT INTO {physical["STLINE"]} VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (line,inv,product,unit,f'{year}-{month:02d}-15',code,cancelled,line_type,qty,amount))
            facts.append(dict(year=year,month=month,code=code,cancelled=cancelled,line_type=line_type,
                              quantity=qty,amount=amount,customer=labels['customer'][customer],
                              payment=labels['payment'][payment],salesperson=labels['salesperson'][person],
                              delivery=labels['delivery'][delivery],product=labels['product'][product],unit=labels['unit'][unit]))
    conn.commit()
    store = open_store('sqlite://')
    for entity, cols in schema.items():
        pattern = 'LG_{n0}_{n1}_' + entity if entity in ('STLINE','INVOICE') else 'LG_{n0}_' + entity
        profile = SchemaProfile('acceptance',physical[entity],pattern,entity,schema_name='main',
                                columns=[ColumnProfile(n,t,is_primary_key=n=='LOGICALREF') for n,t in cols],
                                primary_key=['LOGICALREF'],relationships=[{'column':c,'ref_entity':e,'ref_column':'LOGICALREF'} for c,e in edges.get(entity,[])],
                                context={'n0':'411','n1':'01'},time_window=('2022-01-01','2026-12-31') if entity=='STLINE' else None)
        store.upsert_profile(profile)
    def concept(term, stype, entity, **kw):
        pattern = next(p.table_pattern for p in store.list_profiles('acceptance') if p.entity == entity)
        store.upsert_concept('acceptance','acceptance',term,stype,status=ConceptStatus.CERTIFIED,
                             mapping=Mapping('',entity,pattern,**kw))
    for term,(formula,kind) in METRICS.items():
        codes='2,3,7,8' if kind=='net' else '7,8'
        concept(term,SemanticType.METRIC,'STLINE',formula=formula,extra={'conditions':[f'STLINE.TRCODE IN ({codes})']})
    for term,(entity,col,key) in DIMS.items():
        concept(term,SemanticType.COLUMN,entity,column=col,operator='COLUMN')
    for term,code in [('toptan','8'),('perakende','7')]:
        concept(term,SemanticType.DIMENSION_VALUE,'STLINE',column='TRCODE',operator='=',values=[code])
    for col in ('CANCELLED','LINETYPE'):
        concept('default '+col,SemanticType.DEFAULT_FILTER,'STLINE',column=col,operator='=',values=['0'])
    return conn, store, facts


def expected(case, facts):
    """Pure Python ground truth; does not inspect resolved slots or generated SQL."""
    groups = collections.defaultdict(float)
    metric = METRICS[case['metric']][1]
    for row in facts:
        if row['year'] != case['year'] or row['month'] != case['month'] or row['cancelled'] or row['line_type']:
            continue
        if case['kind'] and row['code'] != {'toptan':8,'perakende':7}[case['kind']]:
            continue
        if metric != 'net' and row['code'] not in (7,8):
            continue
        key = tuple(row[DIMS[d][2]] for d in case['dimensions'])
        value = row['quantity'] if metric=='quantity' else 1 if metric=='count' else row['amount']
        if metric=='net' and row['code'] in (2,3): value = -value
        groups[key] += value
    return [list(k)+[v] for k,v in groups.items()]


def canonical(rows):
    # Labels are namespaced by dimension. Preserve every label and every numeric value;
    # column aliases/order are not part of the user's requested mathematical result.
    return sorted([tuple(sorted(('number',round(float(v),6)) if isinstance(v,(int,float)) else ('label',str(v))
                                for v in row)) for row in rows])


class NoModel:
    calls = 0
    def chat(self, messages):
        self.calls += 1
        raise RuntimeError('MODEL_FALLBACK_NOT_TESTED')


def run(args):
    os.environ['SEMANTIC_REFRESH_SEC']='0'
    os.environ['SEMANTIC_TABLE_SELECTOR']='off'
    os.environ.pop('QDRANT_URL',None)  # production's index is not this isolated fixture
    from semantic_bridge.app import Runtime
    from semantic_layer.candidates.llm_client import LlmClient
    import sqlglot
    from sqlglot import exp
    conn, store, facts = fixture()
    settings = SemanticSettings(tenant_id='acceptance',datasource_id='acceptance',dialect='sqlite',
                                context={'n0':'411','n1':'01'},max_rows=10000,recall_enabled=False)
    model = LlmClient(os.environ['OPENAI_API_BASE'],os.environ['LLM_MODEL_NAME'],os.environ.get('OPENAI_API_KEY',''),120) if args.llm else NoModel()
    rt = Runtime(settings,store=store,connector=SQLiteConnector(conn=conn),llm=model)
    cases = corpus()
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'prompts.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
    selected = cases[args.start:args.start+args.limit] if args.limit else cases[args.start:]
    if args.ids:
        wanted=set(args.ids.split(','));selected=[c for c in cases if c['id'] in wanted]
    source_hash=hashlib.sha256((ROOT/'backend/semantic_layer/runtime/resolver.py').read_bytes()).hexdigest()
    counts=collections.Counter();started=time.monotonic()
    with (args.out/'results.jsonl').open('w') as stream:
        for case in selected:
            t=time.monotonic();truth=expected(case,facts)
            item={**case,'mode':'controlled_runtime_real_model_fallback' if args.llm else 'controlled_runtime_deterministic_preflight',
                  'expected_result':truth,'model_fallback_enabled':args.llm}
            try:
                answer=rt.ask(case['prompt'],thread_id=None,sample_size=10000)
                sql=answer.get('sql') or ''
                tables={t.name.split('_')[-1].upper() for t in sqlglot.parse_one(sql,read='sqlite').find_all(exp.Table)} if sql else set()
                rows=answer.get('records') or []
                values=[list(r.values()) for r in rows]
                correct=answer.get('type')=='TEXT_TO_SQL' and canonical(values)==canonical(truth)
                covered=tables==set(case['expected_tables'])
                status='PASS' if correct and covered else 'FAIL_WRONG_RESULT' if answer.get('type')=='TEXT_TO_SQL' else 'FAIL_'+str(answer.get('type'))
                if correct and not covered:status='FAIL_JOIN_COVERAGE'
                item.update(status=status,response_type=answer.get('type'),actual_result=values,sql=sql,
                            actual_tables=sorted(tables),actual_table_count=len(tables),
                            numeric_match=correct,join_coverage_match=covered,
                            reason=answer.get('explanation'),compiler=(answer.get('semantic') or {}).get('compiler'),
                            semantic_query=(answer.get('semantic') or {}).get('query'))
            except Exception as exc:
                item.update(status='NOT_TESTED_MODEL_FALLBACK' if 'MODEL_FALLBACK_NOT_TESTED' in str(exc) else 'FAIL_EXCEPTION',reason=str(exc)[:800])
            item['seconds']=round(time.monotonic()-t,4);counts[item['status']]+=1
            stream.write(json.dumps(item,ensure_ascii=False,default=str)+'\n');stream.flush()
            if sum(counts.values())%100==0:
                progress={'tested':sum(counts.values()),'counts':dict(counts),'seconds':round(time.monotonic()-started,1)}
                (args.out/'progress.json').write_text(json.dumps(progress));print(json.dumps(progress),flush=True)
    summary={'total':sum(counts.values()),'counts':dict(counts),'seconds':round(time.monotonic()-started,1),
             'fixture_rows':len(facts),'ground_truth':'independent Python row oracle',
             'scope':'generated controlled fixture, Runtime.ask with SQL execution; not production data accuracy',
             'source_sha256':source_hash}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--start',type=int,default=0);p.add_argument('--limit',type=int,default=0);p.add_argument('--ids');p.add_argument('--llm',action='store_true')
    logging.disable(logging.WARNING)
    run(p.parse_args())
