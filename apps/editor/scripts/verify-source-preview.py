#!/usr/bin/env python3
"""Remote, read-only API/PostgreSQL/Qdrant preview acceptance; no model calls.

Run after real editor-preview question jobs complete. Independently reconstructs
record hashes and vector payloads; never imports production validation helpers.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
from urllib.parse import urlparse
import uuid
import unicodedata


def verify_surface_references(claim,views,gate):
    assert gate['version']=='surface-reference-v1' and gate['passed'] is True
    assert gate['semantic_acceptance'] is False and gate['missing_terms']==[]
    def words(text):
        value=unicodedata.normalize('NFKC',text).replace('İ','i').replace('I','ı').lower()
        return re.findall(r'[^\W_]+',value)
    cited=set(words('\n'.join(view['reading_text'] for view in views)))
    text=unicodedata.normalize('NFC',claim['text']);expected=[]
    for match in re.finditer(r"[^\W\d_]+(?:['’ʼ][^\W\d_]+)?",text):
        token=match.group();root=re.split("['’ʼ]",token,maxsplit=1)[0]
        if len(root)<2 or not root[0].isupper():continue
        before=text[:match.start()].rstrip().rstrip('"“”\'‘’(').rstrip()
        if (not before or before[-1] in '.!?…:') and token==root:continue
        normalized=words(root)
        if len(normalized)!=1:continue
        assert normalized[0] in cited,'NAMED_REFERENCE_NOT_IN_CITED_SOURCE'
        expected.append({'term':root,'normalized_root':normalized[0],'present_in_cited_source':True})
    assert gate['checked']==expected,'NAMED_REFERENCE_GATE_COVERAGE_MISMATCH'

def require(condition, message):
    if not condition:
        raise RuntimeError(message)


require(sys.platform.startswith('linux') and os.environ.get('EDITOR_VERIFY_REMOTE_HOST') == socket.gethostname(),
        'Explicit remote Linux host required; local execution forbidden')
root = Path(os.environ.get('EDITOR_VERIFY_ROOT', Path(__file__).resolve().parents[1])).resolve()
generation = str(uuid.UUID(os.environ['EDITOR_VERIFY_GENERATION_ID']))
job_ids = [str(uuid.UUID(value.strip())) for value in os.environ['EDITOR_VERIFY_QUESTION_JOB_IDS'].split(',') if value.strip()]
require(job_ids and len(set(job_ids)) == len(job_ids), 'Explicit distinct completed real question jobs required')
base = os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
require(urlparse(base).hostname in ('localhost', '127.0.0.1', '::1'), 'Use the remote-host loopback API')
token = (root/'secrets/api_token').read_text().strip()
headers = {'Authorization': 'Bearer '+token}
output = root/'evidence'/('source-preview-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
report = {'status': 'RUNNING', 'generation_id': generation, 'question_jobs': job_ids,
          'host': socket.gethostname(), 'api': base, 'root': str(root),
          'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'source_or_review_writes': 0, 'model_calls': 0, 'semantic_acceptance': False, 'complete_book': False}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def command(args):
    try:
        return subprocess.check_output(args, cwd=root, text=True, stderr=subprocess.PIPE).strip()
    except subprocess.CalledProcessError as error:
        raise RuntimeError('Reference command failed; raw subprocess stderr suppressed') from None


def pg(query):
    raw = command(['docker', 'compose', 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query])
    return json.loads(raw) if raw else None


def get(route):
    with urllib.request.urlopen(urllib.request.Request(base+'/v1'+route, headers=headers), timeout=180) as response:
        return json.load(response)


def api_records(kind):
    result = []
    while True:
        batch = get(f'/generations/{generation}/{kind}?offset={len(result)}&limit=100')
        result.extend(batch['items'])
        if not batch['has_more']:
            break
        require(batch['items'], 'API_PAGINATION_STALLED')
    independent = pg(f"SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='{generation}' AND kind='{kind}'")
    require(sorted(result, key=lambda row: row['record_key']) == independent, 'API_PG_DIFFER:'+kind)
    return independent


def qdrant(collection, operation, body):
    # Read-only POST endpoints; no upsert, collection creation or model endpoint.
    require(collection == 'editor_source_preview_1024_v1' and operation in ('collection', 'points', 'points/count'), 'Unexpected vector operation')
    if operation == 'collection':
        require(body is None, 'Collection metadata GET cannot have request body')
        script = ('import urllib.request; print(urllib.request.urlopen(' +
                  repr('http://qdrant:6333/collections/'+collection) + ',timeout=120).read().decode())')
    else:
        script = ('import json,urllib.request; body=json.loads(' + repr(json.dumps(body)) + '); '
                  'req=urllib.request.Request(' + repr('http://qdrant:6333/collections/'+collection+'/'+operation) +
                  ',data=json.dumps(body).encode(),headers={"Content-Type":"application/json"}); '
                  'print(urllib.request.urlopen(req,timeout=120).read().decode())')
    return json.loads(command(['docker', 'compose', 'exec', '-T', 'api', 'python', '-c', script]))['result']


def latest_reviews():
    # Independent explicit source-authority scope; answer reviews must not alter
    # the source index fingerprint. Their visibility is checked separately.
    return pg(f"SELECT COALESCE(json_agg(row_to_json(r)),'[]'::json) FROM (SELECT DISTINCT ON(rv.target_id) rv.target_id,rv.decision,rv.version FROM editor.reviews rv JOIN editor.records r ON r.id=rv.target_id AND r.generation_id=rv.generation_id WHERE rv.generation_id='{generation}' AND r.kind IN ('evidence','layout_regions','source_spans','source_fragments','page_claims','page_context_roles','semantic_reviews','source_passages','source_index') ORDER BY rv.target_id,rv.version DESC) r")


def verify_word_closure(page_rows, refs):
    """Independently reconstruct baseline order; never skip an intervening row.

    A later overlapping line is not a word continuation merely because the
    immediate next region fails the horizontal geometry threshold.
    """
    selected=set(refs);baselines=[]
    for row in sorted(page_rows,key=lambda r:(r['data']['bbox'][1],r['data']['bbox'][0])):
        x,y,w,h=row['data']['bbox'];matches=[]
        for index,line in enumerate(baselines):
            yy,hh=line['y'],line['h']
            overlap=max(0,min(y+h,yy+hh)-max(y,yy))/min(h,hh)
            distance=abs(y+h/2-yy-hh/2)
            if overlap>=.5 and distance<=.6*max(h,hh):matches.append((distance,index))
        if matches:baselines[min(matches)[1]]['rows'].append(row)
        else:baselines.append({'y':y,'h':h,'rows':[row]})
    ordered=[r for line in baselines for r in sorted(line['rows'],key=lambda r:r['data']['bbox'][0])]
    def agreed(row):
        return row['data'].get('status')=='TEXT_AGREED' and row['data'].get('role')=='TEXT'
    for index,left in enumerate(ordered):
        a=left['data'];x,y,w,h=a['bbox'];text=a.get('text','').strip()
        right=ordered[index+1] if index+1<len(ordered) else None
        b=right['data'] if right else None
        if re.search(r'\w-$',text):
            required={left['id']};readable=False
            if right:
                xx,yy,ww,hh=b['bbox']
                compatible=(a['pdf_page']==b['pdf_page'] and a['render_sha256']==b['render_sha256']
                            and yy>=y+.5*h and yy-(y+h)<=2*max(h,hh)
                            and max(0,min(x+w,xx+ww)-max(x,xx))>=.5*min(w,ww))
                if compatible:
                    required.add(right['id'])
                    readable=agreed(left) and agreed(right) and bool(re.match(r'^\s*\w',b.get('text','')))
            if selected&required:
                require(readable and required<=selected,'Passage exposes a partial hyphenated word')
        if right and len(text)==1 and text.isalnum():
            body=b.get('text','').lstrip();xx,yy,ww,hh=b['bbox']
            vertical_overlap=max(0,min(y+h,yy+hh)-max(y,yy))
            if (a['pdf_page']==b['pdf_page'] and a['render_sha256']==b['render_sha256']
                    and body and body[0].islower() and h>=1.4*hh and x<xx
                    and -.5*w<=xx-(x+w)<=.15*hh and vertical_overlap>=.5*hh and y+h>yy+hh):
                required={left['id'],right['id']}
                if selected&required:
                    require(required<=selected and agreed(left) and agreed(right) and text.isalpha() and text.isupper(),
                            'Passage exposes an incomplete separate initial glyph')


try:
    input_kinds = ('evidence', 'layout_regions', 'source_spans', 'source_fragments', 'page_claims', 'page_context_roles', 'semantic_reviews')
    records = {kind: api_records(kind) for kind in (*input_kinds, 'source_passages', 'source_index')}
    generation_row = pg(f"SELECT row_to_json(r) FROM (SELECT status,manifest FROM editor.generations WHERE id='{generation}') r")
    decisions = latest_reviews()
    latest = {row['target_id']: {'decision': row['decision'], 'version': row['version']} for row in decisions}
    denied = {target for target, decision in latest.items() if decision['decision'] != 'ACCEPT'}
    denied_claims = {claim for row in records['source_passages'] if row['id'] in denied for claim in row['data']['claim_ids']}
    require(not any(row['id'] in denied for row in records['source_index']), 'Explicit index refusal exists')
    # Establish installed authority first. A historical manifest's own code hash
    # can validate its historical inputs, but cannot identify the current index.
    code_names = ('source_retrieval.py','semantic_acceptance.py','page_context.py',
                  'source_unit_claims.py','source_pipeline.py','source_alignment.py',
                  'text_attribution.py','retrieval.py')
    script = 'import json,hashlib; from pathlib import Path; import editor; p=Path(editor.__file__).parent; print(json.dumps({name:hashlib.sha256((p/name).read_bytes()).hexdigest() for name in '+repr(list(code_names))+'}))'
    installed_hashes = json.loads(command(['docker', 'compose', 'exec', '-T', 'api', 'python', '-c', script]))
    report['code_identity'] = installed_hashes
    manifests = []
    historical_code_count = 0
    # Choose the exact CURRENT hash, never whichever manifest sorts last.
    for row in records['source_index']:
        data = row['data']
        if data.get('code_identity') != installed_hashes:
            historical_code_count += 1
            continue
        expected_hash = digest({'version': data['version'], 'generation': generation,
                                'code': installed_hashes, 'manifest': generation_row['manifest'],
                                'records': {kind: records[kind] for kind in input_kinds}, 'reviews': latest})
        if data.get('input_sha256') == expected_hash:
            manifests.append(row)
    report['index_manifest_candidates'] = {'total':len(records['source_index']),
        'historical_code':historical_code_count,'current_code':len(records['source_index'])-historical_code_count,
        'current_code_and_input':len(manifests)}
    require(len(manifests) == 1, 'Exactly one current source_index required')
    index_row = manifests[0]; manifest = index_row['data']
    require(index_row['id'] not in denied and manifest['version'] == 'source-preview-retrieval-v1'
            and manifest['preview_only'] is True and manifest['editorial_acceptance'] is False
            and manifest['semantic_acceptance'] is False, 'Index authority mismatch')
    require(installed_hashes == manifest['code_identity'], 'Installed code differs from index authority')
    api_container = command(['docker', 'compose', 'ps', '-q', 'api'])
    report['api_image_id'] = command(['docker', 'inspect', '--format', '{{.Image}}', api_container])
    passages = {row['id']: row for row in records['source_passages'] if row['data']['input_sha256'] == manifest['input_sha256']}
    require(manifest['passage_hashes'] == {key: digest(row['data']) for key, row in passages.items()}, 'Manifest passage hashes differ from actual PG')
    require(set(manifest['vector_hashes']) == set(passages), 'Vector and passage ID sets differ')
    require(manifest.get('vector_distance') == 'Dot' and isinstance(manifest.get('stored_vectors'), dict)
            and set(manifest['stored_vectors']) == set(passages), 'Immutable Dot backup vector contract absent')
    for rid, vector in manifest['stored_vectors'].items():
        require(isinstance(vector, list) and len(vector) == 1024
                and all(type(value) in (float, int) and math.isfinite(value) for value in vector)
                and sum(value*value for value in vector)>0 and digest(vector)==manifest['vector_hashes'][rid],
                'Stored backup vector hash/dimension/values invalid')
    require(manifest['status'] == ('READY' if passages else 'EMPTY'), 'Index status differs from source availability')
    all_rows = {row['id']: row for kind in input_kinds for row in records[kind]}
    span_rows = {row['id']: row for row in records['source_spans']}
    def source_regions(refs):
        require(refs and all(ref in span_rows for ref in refs), 'Source span absent')
        return [{'span_id': ref, **{key: span_rows[ref]['data'][key] for key in ('text', 'bbox', 'render_sha256')}} for ref in refs]
    def cited_support(review, refs, regions, claim):
        require(review.get('passed') is True and review['source_sha256'] == digest(regions)
                and review['source_regions'] == regions and review['support_span_refs'] == refs
                and review['metrics']['finish_reason'] == 'stop', 'Citation support scope/hash incomplete')
        verdict = review['model_result']
        axes=('entailment', 'actor', 'speaker', 'polarity', 'narrative_mode')
        if review.get('version')=='source-semantic-review-v6-cited-support':
            axes+=('epistemic_strength',)
            verify_surface_references(claim,review['source_reading_segments'],review['surface_reference_gate'])
        require(verdict['checks'] == {key: 'PASS' for key in axes}
                and verdict['reason'].strip() and verdict['support_span_refs']
                and set(verdict['support_span_refs']) <= set(refs), 'Citation axes/references failed')
    for rid, row in passages.items():
        data = row['data']; page = data['pdf_page']; refs = data['source_span_refs']
        require(rid not in denied and not set(data['dependency_refs']) & denied, 'Explicit refusal leaked into preview')
        require(not set(data['claim_ids']) & denied_claims, 'Rejected earlier passage claim resurfaced')
        require(set(data['dependency_refs']) <= set(all_rows), 'Out-of-generation dependency')
        require(all(span_rows[ref]['data']['status'] == 'TEXT_AGREED' and span_rows[ref]['data']['role'] == 'TEXT'
                    and span_rows[ref]['data']['pdf_page'] == page for ref in refs), 'Unagreed/wrong-page source')
        verify_word_closure([row for row in records['source_spans'] if row['data']['pdf_page']==page], refs)
        regions = source_regions(refs)
        require(data['regions'] == regions and data['source_regions_sha256'] == digest(regions)
                and data['text'] == '\n'.join(region['text'] for region in regions), 'Passthrough source text/geometry changed')
        page_row = all_rows[data['page_claims_ref']]; review_row = all_rows[data['semantic_review_ref']]
        review = review_row['data']; page_claims = page_row['data']
        require(review['input_page_claims_sha256'] == digest(page_claims), 'Stale page claim review')
        verdicts = [verdict for verdict in review['claims'] if verdict['claim_id'] in data['claim_ids']]
        require(len(verdicts) == 1 and len(data['claim_ids']) == 1, 'Expected one immutable reviewed claim')
        verdict = verdicts[0]; candidate = (page_claims['claims']+page_claims['blocked_claims'])[verdict['candidate_ordinal']]
        require(verdict['eligible_for_synthesis'] is True and verdict['candidate_sha256'] == data['candidate_sha256'] == digest(candidate)
                and verdict['verified_support_span_refs'] == refs and verdict['verified_support_regions'] == regions,
                'Passage is not the exact eligible claim support')
        claim = {key: candidate.get(key) for key in ('kind','text','quote','span_refs','actor','speaker','narrative_mode','polarity')}
        require(data['claim'] == claim and verdict['claim_id'] == digest({'pdf_page': page, 'ordinal': verdict['candidate_ordinal'], 'claim': claim}), 'Claim identity mismatch')
        cited_support(verdict['citation_review'], refs, regions, claim)
        require(data['citation_review_sha256'] == digest(verdict['citation_review']), 'Citation record changed')
        purpose = review['page_purpose_gate']; context = all_rows[purpose['record_id']]['data']
        require(purpose['passed'] is True and purpose['record_sha256'] == digest(context)
                and purpose['input_sha256'] == context['input_sha256'] and context['content_scope'] == 'STORY_WORLD', 'Page-purpose authority differs')
        expected_dependencies = {page_row['id'], review_row['id'], purpose['record_id']}
        expected_dependencies.update(row['id'] for kind in ('evidence','layout_regions','source_spans','source_fragments') for row in records[kind]
                                     if abs(row['data']['pdf_page']-page) <= 1)
        require(set(data['dependency_refs']) == expected_dependencies, 'Consumed context dependencies omitted')
    if passages:
        collection = manifest['collection']
        space = qdrant(collection, 'collection', None)['config']['params']['vectors']
        require(space.get('size') == 1024 and space.get('distance') == 'Dot', 'Actual Qdrant vector space differs from immutable contract')
        report['qdrant_vector_space'] = {'size':space['size'],'distance':space['distance']}
        scope = {'must': [{'key':'generation_id','match':{'value':generation}},
                          {'key':'input_sha256','match':{'value':manifest['input_sha256']}},
                          {'key':'version','match':{'value':manifest['version']}}]}
        require(qdrant(collection, 'points/count', {'exact':True,'filter':scope})['count'] == len(passages), 'Vector scope count differs')
        ids = list(passages)
        for offset in range(0, len(ids), 64):
            batch = ids[offset:offset+64]
            points = qdrant(collection, 'points', {'ids':batch,'with_payload':True,'with_vector':True})
            require(len(points) == len(batch) and {str(point['id']) for point in points} == set(batch), 'Vector exact ID set differs')
            for point in points:
                rid = str(point['id']); data = passages[rid]['data']; vector = point['vector']
                expected = {'version':manifest['version'],'generation_id':generation,'input_sha256':manifest['input_sha256'],
                            'passage_sha256':digest(data),'source_regions_sha256':data['source_regions_sha256'],
                            'source_span_refs':data['source_span_refs'],'claim_ids':data['claim_ids'],'preview_only':True}
                require(point['payload'] == expected, 'Independent Qdrant payload differs')
                require(isinstance(vector,list) and len(vector)==1024 and all(type(value) in (float,int) and math.isfinite(value) for value in vector)
                        and sum(value*value for value in vector)>0 and digest(vector)==manifest['vector_hashes'][rid], 'Independent vector hash/values differ')
                require(vector == manifest['stored_vectors'][rid], 'Actual vector differs from immutable backup values')
        delivered = pg(f"SELECT COALESCE(json_agg(id),'[]'::json) FROM editor.outbox WHERE generation_id='{generation}' AND delivered_at IS NOT NULL")
        require(set(passages) <= set(delivered), 'Passage outbox not delivered')
    report['answers'] = []
    for job in job_ids:
        response = get('/answers/'+job)
        db_job = pg(f"SELECT row_to_json(r) FROM (SELECT status,generation_id,payload FROM editor.jobs WHERE id='{job}' AND task='question') r")
        answer = pg(f"SELECT data FROM editor.records WHERE generation_id='{generation}' AND kind='answers' AND record_key='{job}'")
        require(response['generation_id'] == db_job['generation_id'] == generation and response['job_status'] == db_job['status'] == 'COMPLETED'
                and response['answer'] == answer, 'Delivered answer API/PG differs or unfinished')
        require(answer['version']=='source-answer-preview-v2' and answer['mode']=='editor_preview'
                and answer['semantic_acceptance'] is False and answer['complete_book'] is False and answer['is_final'] is False,
                'Answer incorrectly promoted')
        require(answer.get('source_index_input_sha256')==manifest['input_sha256'], 'Answer belongs to stale or unrecorded index snapshot')
        answer_review = pg(f"SELECT to_json(rv.decision) FROM editor.reviews rv JOIN editor.records r ON r.id=rv.target_id WHERE r.generation_id='{generation}' AND r.kind='answers' AND r.record_key='{job}' ORDER BY rv.version DESC LIMIT 1")
        require(answer_review not in ('REJECT','NEEDS_REVIEW'), 'Explicitly refused answer was returned as current')
        require(answer['question']==db_job['payload']['question'] and answer['answer']=='\n'.join(claim['text'] for claim in answer['claims']), 'Free-form answer bypass or different question')
        require(answer['status']==('PARTIAL' if answer['claims'] else 'INSUFFICIENT_EVIDENCE'), 'Answer scope mismatch')
        retrieved={row['id']:row for row in answer['retrieved_passages']}
        require(len(retrieved)<=5 and all(rid in passages and row==passages[rid] for rid,row in retrieved.items()), 'Retrieved source changed or outside current index')
        for claim in answer['claims']:
            require(claim['passage_id'] in retrieved, 'Answer cites unretrieved passage')
            data = passages[claim['passage_id']]['data']; regions=source_regions(data['source_span_refs'])
            for field in ('actor','speaker'):
                proposed_label=claim.get(field)
                if proposed_label is not None:
                    authority_label=data['claim'].get(field)
                    require(isinstance(proposed_label,str) and isinstance(authority_label,str), 'Answer introduced identity without passage authority')
                    proposed_normalized=' '.join(unicodedata.normalize('NFC',proposed_label).split())
                    authority_normalized=' '.join(unicodedata.normalize('NFC',authority_label).split())
                    require(bool(proposed_normalized) and proposed_normalized==authority_normalized,
                            'Answer actor/speaker label exceeds exact passage identity authority')
            require(claim['span_refs']==data['source_span_refs'] and claim['source_regions']==regions
                    and claim['evidence_refs']==data['evidence_refs'] and claim['pdf_page']==data['pdf_page']
                    and claim['passage_input_sha256']==manifest['input_sha256'], 'Answer changed cited source')
            cited_support(claim['citation_review'],data['source_span_refs'],regions,claim)
            checked_claim = {key:claim.get(key) for key in ('text','actor','speaker','narrative_mode','polarity')}
            checked_claim.update(kind='STATEMENT',span_refs=data['source_span_refs'],quote=data['text'])
            checked_payload = {'claim':checked_claim,'cited_source_regions':regions,
                               'source_reading_segments':claim['citation_review']['source_reading_segments']}
            require(claim['citation_review']['input_sha256']==digest(checked_payload), 'Citation judgment belonged to different answer claim')
            require(answer['metrics']['finish_reason']=='stop' and any(
                all(proposed.get(key)==claim.get(key) for key in ('text','passage_id','actor','speaker','narrative_mode','polarity'))
                for proposed in answer['raw_model_result']['claims']), 'Answer claim absent from completed proposal')
            relevance=claim['relevance_review']
            require(relevance['model_result'].get('relevant') is True and relevance['model_result']['reason'].strip()
                    and relevance['metrics']['finish_reason']=='stop', 'Answer relevance not supported')
        report['answers'].append({'job_id':job,'status':answer['status'],'claims':len(answer['claims']),'blocked_claims':len(answer['blocked_claims']),
                                  'retrieved_passages':len(retrieved),'answer_sha256':digest(answer),'api_pg_equal':True})
    capability=get('/generations/'+generation+'/source-preview')
    require(capability['ready'] is True and capability['eligible_passages']==len(passages)
            and capability['complete_book'] is False and capability['semantic_acceptance'] is False,'Delivered capability disagrees')
    require(latest_reviews()==decisions,'Human review changed during verification; rerun on stable snapshot')
    # Re-read every immutable source kind independently to reject concurrent drift.
    for kind in input_kinds:
        require(api_records(kind)==records[kind],'Source changed during verification:'+kind)
    report.update(status='PASS',passages=len(passages),index_record_id=index_row['id'],input_sha256=manifest['input_sha256'],
                  independent_api_pg_equal=True,independent_vectors_verified=len(passages),capability=capability)
except Exception as error:
    report.update(status='FAILED',reason=str(error).replace(token,'[REDACTED]'),error_type=type(error).__name__)
finally:
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({key:report[key] for key in ('status','passages','reason','error_type') if key in report}|{'evidence':str(output)},ensure_ascii=False))
if report['status']!='PASS':
    raise SystemExit(1)
