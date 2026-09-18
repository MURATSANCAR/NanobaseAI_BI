"""Immutable, source-supported preview retrieval; never publication authority.

Only current source spans underlying machine-reviewed claims are embedded.
An explicit human REJECT/NEEDS_REVIEW wins over every machine verdict. A missing
human decision permits a labelled preview, never an accepted/published answer.
"""
import hashlib
import math
import re
from collections import Counter
from pathlib import Path
import uuid

import httpx

from editor.semantic_acceptance import AXES, CITED_AXES, VERSION as REVIEW_VERSION, digest, source_regions

VERSION = 'source-preview-retrieval-v1'
SUPPORTED_PIPELINES = frozenset(('source-spans-v14', 'source-spans-v15', 'source-spans-v16'))
COLLECTION = 'editor_source_preview_1024_v1'
KINDS = ('evidence', 'layout_regions', 'source_spans', 'source_fragments',
         'page_claims', 'page_context_roles', 'semantic_reviews')
REVIEW_KINDS = KINDS + ('source_passages', 'source_index')
DEPENDENCIES = ('source_retrieval.py', 'semantic_acceptance.py', 'page_context.py',
                'source_unit_claims.py', 'source_pipeline.py', 'source_alignment.py',
                'text_attribution.py', 'retrieval.py')


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def code_identity():
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in DEPENDENCIES}


def build_passages(generation, records, decisions, manifest):
    """Pure validation over an actual consistent PostgreSQL snapshot.

    No model, database or vector calls. Invalid/stale authority raises; absent
    authority and explicit human refusals yield no eligible passage.
    """
    from editor.book_store import identifier
    from editor.page_context import story_authority
    from editor.source_alignment import reading_order
    from editor.source_pipeline import quote_check, negation, quote_tokens, narrative_gate
    from editor.source_unit_claims import reading_segments, incomplete_word_refs
    from editor.text_attribution import extract, speaker_for_claim
    generation = str(uuid.UUID(str(generation)))
    require(manifest.get('pipeline_version') in SUPPORTED_PIPELINES, 'PREVIEW_PIPELINE_VERSION_MISMATCH')
    all_rows = {str(row['id']): row for kind in KINDS for row in records[kind]}
    require(len(all_rows) == sum(len(records[kind]) for kind in KINDS), 'PREVIEW_DUPLICATE_RECORD_ID')
    latest = {}
    denied_claims = set()
    index_denied = False
    for decision in decisions:
        if decision.get('target_kind') not in REVIEW_KINDS:
            continue
        target = str(decision['target_id'])
        require(target not in latest and decision['decision'] in ('ACCEPT', 'REJECT', 'NEEDS_REVIEW')
                and type(decision['version']) is int and decision['version'] > 0, 'PREVIEW_REVIEW_SNAPSHOT_INVALID')
        latest[target] = {'decision': decision['decision'], 'version': decision['version']}
        if decision['decision'] != 'ACCEPT':
            if decision.get('target_kind') == 'source_passages':
                denied_claims.update(decision.get('target_data', {}).get('claim_ids', []))
            if decision.get('target_kind') == 'source_index':
                index_denied = True
    denied = {target for target, decision in latest.items() if decision['decision'] != 'ACCEPT'}
    fingerprint = digest({'version': VERSION, 'generation': generation, 'code': code_identity(),
                          'manifest': manifest, 'records': records, 'reviews': latest})
    def by_page(kind):
        result = {row['data']['pdf_page']: row for row in records[kind]}
        require(len(result) == len(records[kind]), 'PREVIEW_DUPLICATE_PAGE_RECORD')
        return result
    evidence = by_page('evidence'); layouts = by_page('layout_regions')
    claims = by_page('page_claims'); reviews = by_page('semantic_reviews')
    contexts = by_page('page_context_roles')
    spans = records['source_spans']; spans_by_id = {str(row['id']): row for row in spans}
    bundles = [{'evidence': row, 'layout': layouts[page]['data'],
                'spans': [s for s in spans if s['data']['pdf_page'] == page],
                'fragments': [s for s in records['source_fragments'] if s['data']['pdf_page'] == page]}
               for page, row in sorted(evidence.items())]
    output = []
    require(not index_denied, 'PREVIEW_INDEX_EXPLICITLY_DENIED')
    for page, claim_row in sorted(claims.items()):
        review_row = reviews.get(page)
        if not review_row or not contexts.get(page):
            continue
        review = review_row['data']; page_claims = claim_row['data']
        require(review.get('version') == REVIEW_VERSION
                and review.get('input_page_claims_sha256') == digest(page_claims), 'PREVIEW_STALE_SEMANTIC_REVIEW')
        purpose = story_authority(page, bundles, contexts[page])
        require(review.get('page_purpose_gate') == purpose, 'PREVIEW_STALE_PAGE_PURPOSE')
        if purpose.get('passed') is not True:
            continue
        # Purpose classification consumes neighbouring source geometry/context.
        # A refusal on any such consumed record invalidates this page's authority.
        dependencies = {str(claim_row['id']), str(review_row['id']), str(contexts[page]['id'])}
        for kind in ('evidence', 'layout_regions', 'source_spans', 'source_fragments'):
            dependencies.update(str(r['id']) for r in records[kind] if abs(r['data']['pdf_page'] - page) <= 1)
        if dependencies & denied:
            continue
        page_spans = reading_order([row for row in spans if row['data']['pdf_page'] == page])
        allowed = {str(row['id']): row for row in page_spans
                   if row['data'].get('status') == 'TEXT_AGREED' and row['data'].get('role') == 'TEXT'}
        context = [{'span_id': str(row['id']) if str(row['id']) in allowed else None,
                    'can_cite': str(row['id']) in allowed,
                    'text': row['data']['text'] if str(row['id']) in allowed else '[UNVERIFIED_REGION]',
                    'bbox': row['data']['bbox']} for row in page_spans]
        require(review.get('source_context_sha256') == digest(context), 'PREVIEW_STALE_SOURCE_CONTEXT')
        candidates = page_claims.get('claims', []) + page_claims.get('blocked_claims', [])
        attributions = extract(page_spans, page_claims.get('page_role', 'UNKNOWN'))['attributions']
        seen = set()
        for verdict in review.get('claims', []):
            if verdict.get('eligible_for_synthesis') is not True:
                continue
            ordinal = verdict.get('candidate_ordinal')
            require(type(ordinal) is int and 0 <= ordinal < len(candidates) and ordinal not in seen,
                    'PREVIEW_INVALID_CANDIDATE_ORDINAL')
            seen.add(ordinal); candidate = candidates[ordinal]
            claim = {key: candidate.get(key) for key in ('kind', 'text', 'quote', 'span_refs', 'actor', 'speaker', 'narrative_mode', 'polarity')}
            claim_id = digest({'pdf_page': page, 'ordinal': ordinal, 'claim': claim})
            if claim_id in denied_claims:
                continue
            require(verdict.get('claim_id') == claim_id and verdict.get('candidate_sha256') == digest(candidate),
                    'PREVIEW_CANDIDATE_HASH_MISMATCH')
            refs = verdict.get('verified_support_span_refs', [])
            require(isinstance(refs, list) and refs and len(refs) == len(set(refs))
                    and all(ref in allowed for ref in refs) and set(candidate['span_refs']) <= set(refs),
                    'PREVIEW_SUPPORT_SCOPE_MISMATCH')
            require(candidate.get('evidence_refs') == [str(evidence[page]['id'])], 'PREVIEW_EVIDENCE_SCOPE_MISMATCH')
            regions = source_regions(refs, spans_by_id)
            require(regions == verdict.get('verified_support_regions'), 'PREVIEW_SUPPORT_REGION_MISMATCH')
            citation = verdict.get('citation_review', {})
            cited_payload = {'claim': claim, 'cited_source_regions': regions,
                             'source_reading_segments': reading_segments(page_spans, refs)}
            result = verdict.get('model_result', {})
            contextual_payload = {'page_role_candidate': page_claims.get('page_role'), 'source_regions': context,
                                  'source_reading_segments': reading_segments(page_spans), 'claim': claim}
            require(verdict.get('status') == 'MACHINE_SUPPORTED_CANDIDATE'
                    and verdict.get('source_gate') == 'MATCH'
                    and result.get('checks') == {axis: 'PASS' for axis in AXES}
                    and set(candidate['span_refs']) <= set(result.get('support_span_refs', [])) <= set(refs)
                    and verdict.get('response_sha256') == digest(result)
                    and verdict.get('input_sha256') == digest(contextual_payload)
                    and verdict.get('metrics', {}).get('finish_reason') == 'stop', 'PREVIEW_SEMANTIC_AUTHORITY_INVALID')
            require(citation.get('passed') is True and citation.get('source_sha256') == digest(regions)
                    and citation.get('input_sha256') == digest(cited_payload)
                    and citation.get('source_regions') == regions and citation.get('support_span_refs') == refs
                    and citation.get('source_reading_segments') == cited_payload['source_reading_segments']
                    and citation.get('model_result', {}).get('checks') == {axis: 'PASS' for axis in CITED_AXES}
                    and isinstance(citation.get('model_result', {}).get('reason'), str)
                    and bool(citation['model_result']['reason'].strip())
                    and bool(citation.get('model_result', {}).get('support_span_refs'))
                    and set(citation['model_result']['support_span_refs']) <= set(refs)
                    and citation.get('metrics', {}).get('finish_reason') == 'stop', 'PREVIEW_CITATION_AUTHORITY_INVALID')
            gate = quote_check(claim['quote'], [allowed[ref] for ref in claim['span_refs']], page_spans)
            require(narrative_gate(page_claims.get('page_role', 'UNKNOWN'), gate) == 'MATCH'
                    and bool(negation(claim['quote'])) == bool(negation(claim['text'])), 'PREVIEW_LITERAL_SOURCE_GATE_FAILED')
            # A stricter current completeness gate can exclude an old candidate
            # without disabling every independently valid passage in the book.
            # Stale hashes or mismatched authority above still raise.
            if incomplete_word_refs(page_spans, refs):
                continue
            # No new global identity authority. Only explicit page-local text is
            # reproducible here; external visual identity is deliberately excluded.
            actor_tokens = quote_tokens(claim.get('actor') or '')
            quote_words = quote_tokens('\n'.join(s['reading_text'] for s in reading_segments(page_spans, claim['span_refs'])))
            actor_ok = not actor_tokens or any(quote_words[i:i+len(actor_tokens)] == actor_tokens for i in range(len(quote_words)-len(actor_tokens)+1))
            attributed = speaker_for_claim(claim, attributions) if claim.get('speaker') else None
            speaker_ok = not claim.get('speaker') or (attributed is not None and quote_tokens(attributed['label']) == quote_tokens(claim['speaker']))
            if claim['kind'] == 'ENTITY' or not actor_ok or not speaker_ok:
                continue
            key = VERSION + ':' + fingerprint + ':' + claim_id
            data = {'version': VERSION, 'generation_id': generation, 'input_sha256': fingerprint,
                    'text': '\n'.join(region['text'] for region in regions), 'pdf_page': page,
                    'source_span_refs': refs, 'regions': regions, 'claim_ids': [claim_id],
                    'claim': claim, 'semantic_review_ref': str(review_row['id']),
                    'page_claims_ref': str(claim_row['id']), 'evidence_refs': candidate['evidence_refs'],
                    'dependency_refs': sorted(dependencies), 'source_regions_sha256': digest(regions),
                    'candidate_sha256': digest(candidate), 'citation_review_sha256': digest(citation),
                    'identity_scope': 'PAGE_LOCAL_TEXT_ONLY_NOT_CANONICAL_CHARACTER',
                    'preview_only': True, 'editorial_acceptance': False, 'complete_book': False}
            output.append({'id': str(identifier(generation, 'source_passages', key)), 'record_key': key, 'data': data})
    return {'version': VERSION, 'generation_id': generation, 'input_sha256': fingerprint,
            'code_identity': code_identity(), 'passages': output, 'preview_only': True}


def snapshot(generation):
    from editor.config import connection
    generation = str(uuid.UUID(str(generation)))
    with connection() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        row = db.execute('SELECT manifest FROM editor.generations WHERE id=%s', (generation,)).fetchone()
        require(row is not None, 'PREVIEW_GENERATION_NOT_FOUND')
        records = {kind: db.execute('SELECT id,record_key,data FROM editor.records WHERE generation_id=%s AND kind=%s ORDER BY record_key',
                                   (generation, kind)).fetchall() for kind in KINDS}
        decisions = db.execute('''SELECT DISTINCT ON(rv.target_id) rv.target_id,rv.decision,rv.version,
          r.kind AS target_kind,r.data AS target_data FROM editor.reviews rv
          JOIN editor.records r ON r.id=rv.target_id AND r.generation_id=rv.generation_id
          WHERE rv.generation_id=%s AND r.kind=ANY(%s) ORDER BY rv.target_id,rv.version DESC''',
                               (generation, list(REVIEW_KINDS))).fetchall()
    # UUIDs are canonical strings in the digest, matching API record identities.
    for rows in records.values():
        for record in rows:
            record['id'] = str(record['id'])
    return build_passages(generation, records, decisions, row['manifest'])


def verified_passages(generation):
    return snapshot(generation)['passages']


def payload(row):
    data = row['data']
    return {'version': VERSION, 'generation_id': data['generation_id'], 'input_sha256': data['input_sha256'],
            'passage_sha256': digest(data), 'source_regions_sha256': data['source_regions_sha256'],
            'source_span_refs': data['source_span_refs'], 'claim_ids': data['claim_ids'], 'preview_only': True}


def point_matches(point, row):
    vector = point.get('vector')
    require(str(point.get('id')) == row['id'] and point.get('payload') == payload(row), 'PREVIEW_VECTOR_PAYLOAD_MISMATCH')
    require(isinstance(vector, list) and len(vector) == 1024
            and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in vector)
            and sum(value*value for value in vector) > 0, 'PREVIEW_VECTOR_INVALID')
    return digest(vector)


def build_index(job):
    from editor.book_store import fence, save_record, get_records
    from editor.config import connection
    from editor.retrieval import embed
    current = snapshot(job['generation_id']); rows = current['passages']
    key = VERSION + ':' + current['input_sha256']
    if any(row['record_key'] == key for row in get_records(job['generation_id'], 'source_index')):
        saved, manifest = current_index(job['generation_id'])
        verify_vectors(saved, manifest)
        return manifest
    hashes = {}; stored_vectors = {}
    with httpx.Client(timeout=180, trust_env=False) as client:
        if rows:
            response = client.get(f'http://qdrant:6333/collections/{COLLECTION}')
            if response.status_code == 404:
                client.put(f'http://qdrant:6333/collections/{COLLECTION}', json={'vectors': {'size': 1024, 'distance': 'Dot'}}).raise_for_status()
            else:
                response.raise_for_status()
                space=response.json()['result']['config']['params']['vectors']
                require(space.get('size')==1024 and space.get('distance')=='Dot','PREVIEW_VECTOR_SPACE_MISMATCH')
        for row in rows:
            with connection() as db:
                fence(db, job)
                rid = save_record(db, job['generation_id'], 'source_passages', row['record_key'], row['data'], True)
                persisted = db.execute('SELECT data FROM editor.records WHERE id=%s', (rid,)).fetchone()
                require(persisted['data'] == row['data'], 'PREVIEW_IMMUTABLE_PASSAGE_MISMATCH')
            vector = embed(row['data']['text'])
            require(len(vector) == 1024 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in vector), 'PREVIEW_EMBEDDING_INVALID')
            norm = math.sqrt(sum(v*v for v in vector))
            require(norm > 0, 'PREVIEW_EMBEDDING_ZERO')
            vector = [v/norm for v in vector]
            with connection() as db:
                fence(db, job)
            client.put(f'http://qdrant:6333/collections/{COLLECTION}/points', params={'wait': 'true'},
                       json={'points': [{'id': row['id'], 'vector': vector, 'payload': payload(row)}]}).raise_for_status()
            response = client.post(f'http://qdrant:6333/collections/{COLLECTION}/points',
                                   json={'ids': [row['id']], 'with_payload': True, 'with_vector': True})
            response.raise_for_status(); points = response.json()['result']
            require(len(points) == 1, 'PREVIEW_VECTOR_READBACK_MISSING')
            stored = points[0].get('vector', [])
            require(len(stored) == len(vector) and all(math.isclose(a, b, abs_tol=2e-6, rel_tol=2e-5)
                    for a, b in zip(stored, vector)), 'PREVIEW_VECTOR_READBACK_DIFFERS')
            hashes[row['id']] = point_matches(points[0], row)
            stored_vectors[row['id']] = stored
            with connection() as db:
                fence(db, job)
                db.execute('UPDATE editor.outbox SET delivered_at=now() WHERE id=%s', (rid,))
        require(snapshot(job['generation_id'])['input_sha256'] == current['input_sha256'], 'PREVIEW_INPUT_CHANGED_DURING_INDEX')
        result = {key: value for key, value in current.items() if key != 'passages'}
        result.update(status='READY' if rows else 'EMPTY', collection=COLLECTION,
                      passage_hashes={row['id']: digest(row['data']) for row in rows}, vector_hashes=hashes,
                      stored_vectors=stored_vectors,vector_distance='Dot',
                      semantic_acceptance=False, editorial_acceptance=False)
        verify_vectors(current, result)
        with connection() as db:
            fence(db, job)
            rid = save_record(db, job['generation_id'], 'source_index', key, result)
            require(db.execute('SELECT data FROM editor.records WHERE id=%s', (rid,)).fetchone()['data'] == result,
                    'PREVIEW_IMMUTABLE_INDEX_MISMATCH')
    return result


def current_index(generation):
    from editor.book_store import get_records
    from editor.config import connection
    current = snapshot(generation)
    manifests = [row['data'] for row in get_records(generation, 'source_index')
                 if row['record_key'] == VERSION + ':' + current['input_sha256']]
    require(len(manifests) == 1, 'PREVIEW_INDEX_NOT_READY_OR_STALE')
    manifest = manifests[0]
    expected = {row['id']: digest(row['data']) for row in current['passages']}
    require(manifest.get('passage_hashes') == expected and manifest.get('code_identity') == current['code_identity']
            and manifest.get('version') == VERSION and manifest.get('generation_id') == current['generation_id']
            and manifest.get('preview_only') is True and manifest.get('editorial_acceptance') is False
            and manifest.get('semantic_acceptance') is False
            and manifest.get('input_sha256') == current['input_sha256'] and manifest.get('collection') == COLLECTION
            and manifest.get('status') == ('READY' if expected else 'EMPTY')
            and manifest.get('vector_distance')=='Dot'
            and set(manifest.get('vector_hashes', {})) == set(expected)
            and set(manifest.get('stored_vectors', {})) == set(expected), 'PREVIEW_INDEX_MANIFEST_MISMATCH')
    for rid,vector in manifest['stored_vectors'].items():
        require(isinstance(vector,list) and len(vector)==1024
                and all(type(v) in (int,float) and math.isfinite(v) for v in vector)
                and digest(vector)==manifest['vector_hashes'][rid], 'PREVIEW_BACKUP_VECTOR_MISMATCH')
    persisted = {str(row['id']): row for row in get_records(generation, 'source_passages')}
    require(all(rid in persisted and digest(persisted[rid]['data']) == sha for rid, sha in expected.items()), 'PREVIEW_POSTGRES_PASSAGE_MISMATCH')
    if expected:
        with connection() as db:
            delivered = db.execute('SELECT id FROM editor.outbox WHERE generation_id=%s AND id=ANY(%s::uuid[]) AND delivered_at IS NOT NULL',
                                   (generation, list(expected))).fetchall()
        require({str(row['id']) for row in delivered} == set(expected), 'PREVIEW_OUTBOX_NOT_DELIVERED')
    return current, manifest


def scope_filter(current):
    return {'must': [{'key': 'generation_id', 'match': {'value': current['generation_id']}},
                     {'key': 'input_sha256', 'match': {'value': current['input_sha256']}},
                     {'key': 'version', 'match': {'value': VERSION}}]}


def verify_vectors(current, manifest):
    """Check every expected payload/vector plus exact filtered set size."""
    rows = current['passages']
    if not rows:
        return
    with httpx.Client(timeout=180, trust_env=False) as client:
        configuration=client.get(f'http://qdrant:6333/collections/{COLLECTION}')
        configuration.raise_for_status()
        space=configuration.json()['result']['config']['params']['vectors']
        require(space.get('size')==1024 and space.get('distance')=='Dot', 'PREVIEW_VECTOR_SPACE_MISMATCH')
        response = client.post(f'http://qdrant:6333/collections/{COLLECTION}/points/count',
                               json={'exact': True, 'filter': scope_filter(current)})
        response.raise_for_status()
        require(response.json()['result']['count'] == len(rows), 'PREVIEW_VECTOR_SET_SIZE_MISMATCH')
        for start in range(0, len(rows), 64):
            batch = {row['id']: row for row in rows[start:start+64]}
            response = client.post(f'http://qdrant:6333/collections/{COLLECTION}/points',
                                   json={'ids': list(batch), 'with_payload': True, 'with_vector': True})
            response.raise_for_status(); points = response.json()['result']
            require(len(points) == len(batch) and {str(p['id']) for p in points} == set(batch),
                    'PREVIEW_VECTOR_ID_SET_MISMATCH')
            for point in points:
                rid = str(point['id'])
                require(point_matches(point, batch[rid]) == manifest['vector_hashes'].get(rid), 'PREVIEW_VECTOR_CHANGED')
                require(point['vector']==manifest['stored_vectors'][rid], 'PREVIEW_BACKUP_VECTOR_MISMATCH')


def ready(generation):
    try:
        current, manifest = current_index(generation)
        verify_vectors(current, manifest)
        return True
    except (RuntimeError, KeyError, TypeError, ValueError, httpx.HTTPError):
        return False


def search(generation, question):
    from editor.retrieval import embed
    current, manifest = current_index(generation)
    verify_vectors(current, manifest)
    rows = {row['id']: row for row in current['passages']}
    if not rows:
        return []
    require(isinstance(question, str) and 3 <= len(question.strip()) <= 1000, 'PREVIEW_INVALID_QUESTION')
    with httpx.Client(timeout=180, trust_env=False) as client:
        response = client.post(f'http://qdrant:6333/collections/{COLLECTION}/points/search', json={
            'vector': embed(question), 'limit': 12, 'with_payload': True, 'with_vector': True,
            'filter': scope_filter(current)})
        response.raise_for_status(); dense = []
        for point in response.json()['result']:
            rid = str(point['id']); require(rid in rows, 'PREVIEW_RETRIEVED_OUT_OF_SCOPE_PASSAGE')
            require(point_matches(point, rows[rid]) == manifest['vector_hashes'].get(rid), 'PREVIEW_VECTOR_CHANGED')
            dense.append(rid)
        # Lexical and vector retrieval consume the same verified passage set.
        # The legacy whole-page OCR collection is never queried or merged here.
        terms = re.findall(r'\w+', question.casefold())
        counts = {rid: Counter(re.findall(r'\w+', row['data']['text'].casefold())) for rid, row in rows.items()}
        average = sum(sum(c.values()) for c in counts.values()) / len(counts)
        sparse = []
        for rid, count in counts.items():
            score = 0.0
            for term in terms:
                frequency = count[term]
                document_frequency = sum(term in other for other in counts.values())
                inverse = math.log(1 + (len(rows) - document_frequency + .5) / (document_frequency + .5))
                score += inverse * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * sum(count.values()) / max(1, average)))
            if score > 0:
                sparse.append((rid, score))
        ranking = Counter()
        for ordered in (dense, [rid for rid, _ in sorted(sparse, key=lambda item: (-item[1], item[0]))[:12]]):
            for rank, rid in enumerate(ordered):
                ranking[rid] += 1 / (60 + rank + 1)
        candidates = [rows[rid] for rid, _ in ranking.most_common(12)]
        result = []
        if candidates:
            response = client.post('http://reranker:8080/v1/rerank', json={
                'model': 'editor-reranker', 'query': question,
                'documents': [row['data']['text'] for row in candidates]})
            response.raise_for_status(); body = response.json()
            ranked = body.get('results', body.get('data', [])) if isinstance(body, dict) else None
            require(isinstance(ranked, list) and len(ranked) == len(candidates), 'PREVIEW_RERANKER_SCHEMA_INVALID')
            seen = set(); scored = []
            for item in ranked:
                index = item.get('index') if isinstance(item, dict) else None
                score = item.get('relevance_score', item.get('score')) if isinstance(item, dict) else None
                require(type(index) is int and 0 <= index < len(candidates) and index not in seen
                        and isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score),
                        'PREVIEW_RERANKER_SCHEMA_INVALID')
                seen.add(index); scored.append((index, score))
            result = [candidates[index] for index, _ in sorted(scored, key=lambda item: (-item[1], item[0]))[:5]]
    require(snapshot(generation)['input_sha256'] == current['input_sha256'], 'PREVIEW_REVIEW_CHANGED_DURING_SEARCH')
    return result
