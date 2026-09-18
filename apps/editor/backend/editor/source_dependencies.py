"""Read-only, bounded impact graph over immutable source records.

An edge identifies consumed evidence or a declared input scope, not causality or
editorial approval. CURRENT means checked structural links only. No model calls,
record writes, review decisions, or acceptance promotion are performed here.
"""
from collections import defaultdict, deque
import hashlib
import json
import os
from pathlib import Path

VERSION = 'source-dependency-impact-v1'
SOURCE_KINDS = ('evidence', 'layout_regions', 'source_spans', 'source_fragments',
                'page_claims', 'page_context_roles', 'semantic_reviews')
SUPPORTED = frozenset(SOURCE_KINDS + ('visual_observations', 'page_readings', 'page_checks',
    'character_evidence', 'figure_identity', 'figure_comparisons', 'semantic_synthesis',
    'fragment_checks', 'cross_page_attributions', 'source_passages', 'source_index', 'answers'))
MANY_REFS = frozenset(('evidence_refs', 'span_refs', 'source_span_refs', 'quote_span_refs',
    'support_span_refs', 'verified_support_span_refs', 'speaker_source_span_refs',
    'supported_quote_span_refs', 'input_span_ids', 'span_ids', 'source_span_ids',
    'dependency_refs', 'anchor_text_span_refs'))
ONE_REF = frozenset(('evidence_ref', 'span_id', 'record_id', 'parent_source_span_id',
                    'semantic_review_ref', 'page_claims_ref', 'passage_id'))
OPAQUE_FIELDS = frozenset(('metrics', 'verification_metrics', 'review_metrics', 'raw_model_result',
    'model_result', 'proposal', 'measurement', 'blocked_claims', 'blocked_statements',
    'rejected_model_candidates', 'stored_vectors', 'crop_image_base64', 'raw_response'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def limits():
    records=max(100,min(50000,int(os.environ.get('EDITOR_IMPACT_MAX_RECORDS','10000'))))
    size=max(1024*1024,min(256*1024*1024,int(os.environ.get('EDITOR_IMPACT_MAX_BYTES',str(64*1024*1024)))))
    edges=max(1000,min(1000000,int(os.environ.get('EDITOR_IMPACT_MAX_EDGES','200000'))))
    return records,size,edges


def load_snapshot(db, generation):
    """Caller must establish REPEATABLE READ/READ ONLY and scope ACL first."""
    maximum, byte_limit, _ = limits()
    size = db.execute('SELECT count(*) AS n,COALESCE(sum(octet_length(data::text)),0) AS bytes FROM editor.records WHERE generation_id=%s', (generation,)).fetchone()
    if size['n'] > maximum or size['bytes'] > byte_limit:
        raise RuntimeError('IMPACT_SNAPSHOT_LIMIT_EXCEEDED')
    rows = db.execute('SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s ORDER BY kind,record_key,id', (generation,)).fetchall()
    reviews = db.execute('SELECT DISTINCT ON(target_id) target_id,decision,version FROM editor.reviews WHERE generation_id=%s ORDER BY target_id,version DESC', (generation,)).fetchall()
    for row in rows:
        row['id'] = str(row['id'])
    return rows, {str(row['target_id']): {'decision': row['decision'], 'version': row['version']} for row in reviews}


def impact(generation, target_id, rows, reviews, manifest, source_sha256, offset=0, limit=50):
    """Build dependency edges only from the declared source-record contract."""
    maximum, _, edge_limit = limits()
    if len(rows) > maximum:
        raise RuntimeError('IMPACT_SNAPSHOT_LIMIT_EXCEEDED')
    by_id = {str(row['id']): row for row in rows}
    target_id = str(target_id)
    if target_id not in by_id:
        raise LookupError('IMPACT_TARGET_NOT_FOUND')
    by_kind = defaultdict(list); by_page = defaultdict(dict)
    for row in rows:
        by_kind[row['kind']].append(row)
        page = row['data'].get('pdf_page')
        if type(page) is int:
            by_page[row['kind']][page] = row
    reasons = defaultdict(set); stale = set(); unresolved = set(); dependencies = defaultdict(dict)
    followers = defaultdict(set); edge_count = 0
    def uncertain(rid, reason):
        unresolved.add(rid); reasons[rid].add(reason)
    def obsolete(rid, reason):
        stale.add(rid); reasons[rid].add(reason)
    def edge(rid, dependency, basis='EXPLICIT_REFERENCE'):
        nonlocal edge_count
        if not isinstance(dependency, str) or not dependency:
            uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED'); return
        if dependency == rid:
            return
        if dependency not in by_id:
            obsolete(rid, 'DEPENDENCY_REFERENCE_MISSING'); return
        if dependency not in dependencies[rid]:
            edge_count += 1
            if edge_count > edge_limit:
                raise RuntimeError('IMPACT_EDGE_LIMIT_EXCEEDED')
            dependencies[rid][dependency] = basis
            followers[dependency].add(rid)
    def compare(rid, actual, expected):
        if actual != expected:
            obsolete(rid, 'DEPENDENCY_HASH_MISMATCH')
    claim_owners = defaultdict(set)
    for row in by_kind['page_claims']:
        data = row['data']
        for ordinal, candidate in enumerate(data.get('claims', []) + data.get('blocked_claims', [])):
            if not isinstance(candidate, dict):
                continue
            claim = {key: candidate.get(key) for key in ('kind','text','quote','span_refs','actor','speaker','narrative_mode','polarity')}
            claim_owners[digest({'pdf_page':data.get('pdf_page'),'ordinal':ordinal,'claim':claim})].add(row['id'])
    for row in by_kind['semantic_reviews']:
        for claim in row['data'].get('claims', []):
            if isinstance(claim, dict) and claim.get('claim_id') in claim_owners:
                claim_owners[claim['claim_id']].add(row['id'])
    def walk(rid, value):
        if isinstance(value, list):
            for item in value:
                walk(rid, item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in OPAQUE_FIELDS:
                    continue
                if key in MANY_REFS and isinstance(item, list):
                    for reference in item:
                        edge(rid, reference)
                elif key in ONE_REF and item is not None:
                    edge(rid, item)
                elif key in ('claim_id', 'claim_ids', 'claim_refs'):
                    values = item if isinstance(item, list) else [item]
                    for claim_id in values:
                        owners = claim_owners.get(claim_id, ()) if isinstance(claim_id, str) else ()
                        if not owners:
                            uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED')
                        for owner in owners:
                            edge(rid, owner, 'CLAIM_OWNERSHIP')
                elif key == 'retrieved_passages' and isinstance(item, list):
                    for passage in item:
                        if isinstance(passage, dict):
                            edge(rid, passage.get('id'))
                else:
                    walk(rid, item)
    from editor.source_retrieval import VERSION as INDEX_VERSION, code_identity
    installed = code_identity()
    authority_reviews = {rid: decision for rid, decision in reviews.items()
                         if rid in by_id and by_id[rid]['kind'] in SOURCE_KINDS + ('source_passages', 'source_index')}
    source_records = {kind: [{key: row[key] for key in ('id','record_key','data')}
                            for row in sorted(by_kind[kind], key=lambda row: row['record_key'])] for kind in SOURCE_KINDS}
    current_input = digest({'version':INDEX_VERSION,'generation':str(generation),'code':installed,
                            'manifest':manifest,'records':source_records,'reviews':authority_reviews})
    indexes_by_hash = defaultdict(list)
    for row in by_kind['source_index']:
        indexes_by_hash[row['data'].get('input_sha256')].append(row)
    for row in rows:
        rid = row['id']; kind = row['kind']; data = row['data']; page = data.get('pdf_page')
        if kind not in SUPPORTED:
            uncertain(rid, 'UNSUPPORTED_RECORD_KIND'); continue
        walk(rid, data)
        decision = reviews.get(rid, {}).get('decision')
        if decision in ('REJECT','NEEDS_REVIEW'):
            obsolete(rid, 'HUMAN_REVIEW_REJECTED' if decision == 'REJECT' else 'HUMAN_REVIEW_REQUIRED')
        if kind == 'evidence':
            if data.get('source_sha256'):
                compare(rid, data['source_sha256'], source_sha256)
            else:
                uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED')
        elif kind in ('source_spans','source_fragments'):
            refs = data.get('evidence_refs', [])
            if len(refs) != 1 or refs[0] not in by_id:
                uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED')
            else:
                original = by_id[refs[0]]['data']
                compare(rid, (page,data.get('render_sha256')), (original.get('pdf_page'),original.get('ocr_render_sha256')))
            if data.get('status') != 'TEXT_AGREED':
                uncertain(rid, 'SOURCE_READING_REQUIRES_REVIEW')
            parent = data.get('parent_source_span_id')
            if parent in by_id:
                compare(rid, data.get('parent_record_sha256'), digest(by_id[parent]['data']))
        elif kind == 'semantic_reviews':
            original = by_page['page_claims'].get(page)
            if original:
                edge(rid, original['id'], 'SAME_PAGE_RECORD_SCOPE')
                compare(rid, data.get('input_page_claims_sha256'), digest(original['data']))
            else:
                uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED')
            gate = data.get('page_purpose_gate', {})
            if gate.get('record_id') in by_id:
                compare(rid, gate.get('record_sha256'), digest(by_id[gate['record_id']]['data']))
            if not gate.get('passed'):
                uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED')
        elif kind == 'page_context_roles':
            # This declared source stage consumes adjacent page context. The
            # exact classifier authority is not recomputed by the impact view.
            for source_kind in ('evidence','layout_regions','source_spans','source_fragments'):
                for source in by_kind[source_kind]:
                    if type(page) is int and abs(source['data'].get('pdf_page',-1000)-page) <= 1:
                        edge(rid, source['id'], 'INFERRED_PAGE_CONTEXT_INPUT')
            uncertain(rid, 'PAGE_CONTEXT_INPUT_INFERRED')
        elif kind == 'semantic_synthesis':
            pages=sorted(by_kind['page_claims'],key=lambda item:item['record_key'])
            review_map={item['record_key']:item for item in by_kind['semantic_reviews']}
            if all(item['record_key'] in review_map for item in pages):
                compare(rid,data.get('input_sha256'),digest({'pages':[item['data'] for item in pages],
                    'reviews':[review_map[item['record_key']]['data'] for item in pages]}))
                for item in pages:
                    edge(rid,item['id'],'CANONICAL_SNAPSHOT_INPUT')
                    edge(rid,review_map[item['record_key']]['id'],'CANONICAL_SNAPSHOT_INPUT')
            else:
                uncertain(rid,'AUTHORITY_NOT_ESTABLISHED')
        elif kind == 'source_passages':
            compare(rid, data.get('input_sha256'), current_input)
            refs = data.get('source_span_refs', [])
            if refs and all(ref in by_id for ref in refs):
                regions = [{'span_id':ref, **{key:by_id[ref]['data'].get(key) for key in ('text','bbox','render_sha256')}} for ref in refs]
                compare(rid, data.get('regions'), regions)
                compare(rid, data.get('source_regions_sha256'), digest(regions))
                compare(rid, data.get('text'), '\n'.join(region['text'] or '' for region in regions))
            else:
                uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED')
        elif kind == 'source_index':
            if data.get('code_identity') != installed:
                obsolete(rid, 'CODE_VERSION_CHANGED')
            compare(rid, data.get('input_sha256'), current_input)
            for passage, expected_hash in data.get('passage_hashes', {}).items():
                edge(rid, passage)
                if passage in by_id:
                    compare(rid, digest(by_id[passage]['data']), expected_hash)
        elif kind == 'answers':
            from editor.source_answers import VERSION as ANSWER_VERSION
            if data.get('version') != ANSWER_VERSION:
                obsolete(rid, 'CODE_VERSION_CHANGED')
            compare(rid, data.get('source_index_input_sha256'), current_input)
            for index in indexes_by_hash.get(data.get('source_index_input_sha256'), []):
                edge(rid, index['id'])
            for passage in data.get('retrieved_passages', []):
                if isinstance(passage,dict) and passage.get('id') in by_id:
                    compare(rid, passage.get('data'), by_id[passage['id']]['data'])
            if data.get('status') != 'PARTIAL':
                uncertain(rid, 'MODEL_OUTPUT_NOT_ACCEPTED')
        elif kind in ('visual_observations','figure_identity','figure_comparisons','character_evidence','cross_page_attributions'):
            uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED')
        elif not dependencies[rid]:
            uncertain(rid, 'AUTHORITY_NOT_ESTABLISHED')
    # Refusal/hash mismatches propagate only along explicit consumed-record links;
    # inference scopes identify potential impact without proving downstream stale.
    pending = deque(sorted(stale))
    while pending:
        source = pending.popleft()
        for child in followers[source]:
            if dependencies[child][source] == 'INFERRED_PAGE_CONTEXT_INPUT':
                uncertain(child, 'DEPENDENCY_UNRESOLVED')
            elif child not in stale:
                obsolete(child, 'DEPENDENCY_STALE'); pending.append(child)
    distances = {target_id:0}; traversal = deque([target_id]); paths = defaultdict(list)
    snapshot_dependents = [row['id'] for kind in ('source_passages','source_index') for row in by_kind[kind]]
    traversed_edges=0
    snapshot_scope_expanded=False
    while traversal:
        source = traversal.popleft()
        children = {child:dependencies[child][source] for child in followers[source]}
        # Full immutable snapshot hashes explicitly cover every source record.
        # Expand this scope lazily instead of allocating N*M permanent edges.
        if by_id[source]['kind'] in SOURCE_KINDS and not snapshot_scope_expanded:
            children.update({child:'CANONICAL_SNAPSHOT_INPUT' for child in snapshot_dependents if child != source and child not in children})
            # BFS's first source-snapshot node has minimum distance. Its scope
            # already reaches all these records; repeating N*M expansions adds
            # no shorter path and would needlessly exhaust the request budget.
            snapshot_scope_expanded=True
        for child,basis in sorted(children.items()):
            traversed_edges+=1
            if traversed_edges>edge_limit:
                raise RuntimeError('IMPACT_EDGE_LIMIT_EXCEEDED')
            distance = distances[source]+1
            if child not in distances:
                distances[child]=distance; traversal.append(child)
            if distances[child] == distance:
                paths[child].append({'record_id':source,'basis':basis})
    def describe(rid, distance=None):
        row=by_id[rid]; data=row['data']; pages=set()
        if type(data.get('pdf_page')) is int:
            pages.add(data['pdf_page'])
        pages.update(page for page in data.get('pdf_pages',[]) if type(page) is int)
        for dependency in dependencies[rid]:
            page=by_id[dependency]['data'].get('pdf_page')
            if type(page) is int:
                pages.add(page)
        state='STALE' if rid in stale else 'UNRESOLVED' if rid in unresolved else 'CURRENT'
        result={'id':rid,'kind':row['kind'],'record_key':row['record_key'],'pdf_pages':sorted(pages),
                'state':state,'reasons':sorted(reasons[rid]) or ['STRUCTURAL_REFERENCES_CURRENT']}
        if distance is not None:
            result.update(distance=distance,relations=paths[rid][:20],relations_truncated=len(paths[rid])>20)
        return result
    affected=sorted((rid for rid in distances if rid != target_id), key=lambda rid:(distances[rid],by_id[rid]['kind'],by_id[rid]['record_key'],rid))
    snapshot_sha256=digest({'generation_id':str(generation),'target_id':target_id,
        'records':[{key:row[key] for key in ('id','kind','record_key','data')} for row in rows],
        'reviews':reviews,'authority_code':installed,'manifest':manifest,'source_sha256':source_sha256,
        'impact_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'graph':[{'id':rid,'distance':distances[rid],'state':describe(rid)['state'],
                  'reasons':sorted(reasons[rid]),'dependencies':dependencies[rid]}
                 for rid in [target_id]+affected]})
    return {'generation_id':str(generation),'target':describe(target_id),'items':[describe(rid,distances[rid]) for rid in affected[offset:offset+limit]],
            'offset':offset,'limit':limit,'has_more':offset+limit<len(affected),'total':len(affected),
            'graph_scope':'SOURCE_DEPENDENCIES','complete':False,'semantic_acceptance':False,
            'version':VERSION,'snapshot_sha256':snapshot_sha256}
