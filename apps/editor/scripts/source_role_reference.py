"""Independent literal/provenance and subject-edge acceptance; no product imports.

Model grammar remains a candidate. This proves integrity and bounded consistency,
not literary or complete grammatical correctness.
"""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _anchors(regions, prefix):
    result = []
    for region in regions:
        for word in re.finditer(r'\S+', region['text']):
            result.append(dict(id=f'{prefix}_{len(result)+1:04}', span_id=region['span_id'],
                               start=word.start(), end=word.end(), literal=word.group(),
                               region_sha256=digest(region)))
    return result


def _word(value):
    return value.translate(str.maketrans({'I': 'ı', 'İ': 'i'})).casefold().strip(".,!?;:\"“”()[]").strip("'‘’")


def _surface(mention, anchors):
    if mention['kind'] != 'NAME':
        return _word(' '.join(anchors[t]['literal'] for t in mention['token_ids']))
    words = [_word(anchors[t]['literal']) for t in mention['token_ids']]
    if mention['kind'] == 'NAME':
        words = [re.sub(r"['’](?:ın|in|un|ün|nın|nin|nun|nün|a|e|ya|ye|ı|i|u|ü|yı|yi|yu|yü|da|de|ta|te|dan|den|tan|ten)$", '', w) for w in words]
    return ' '.join(words)


def _graph(graph, anchors):
    assert isinstance(graph, dict) and set(graph) == {'mentions', 'clauses', 'reports'}, 'ROLE_GRAPH_SCHEMA'
    assert all(isinstance(graph[k], list) for k in ('mentions','clauses','reports'))
    assert all(isinstance(m,dict) and isinstance(m.get('id'),str) and m['id'] for m in graph['mentions'])
    assert all(isinstance(c,dict) and isinstance(c.get('id'),str) and c['id'] for c in graph['clauses'])
    mentions = {m['id']: m for m in graph['mentions']}
    clauses = {c['id']: c for c in graph['clauses']}
    assert len(mentions) == len(graph['mentions']) and len(clauses) == len(graph['clauses']) and clauses
    assert 'UNKNOWN' not in mentions
    order = {a['id']: n for n, a in enumerate(anchors)}
    def refs(ids, empty=False):
        assert isinstance(ids, list) and (ids or empty)
        assert all(isinstance(t,str) for t in ids)
        assert len(ids) == len(set(ids)) and all(t in order for t in ids)
        assert ids == sorted(ids, key=order.get)
    for m in mentions.values():
        assert set(m) == {'id', 'token_ids', 'kind', 'person'}
        assert m['kind'] in ('NAME', 'PRONOUN', 'NOMINAL', 'IMPLICIT', 'UNKNOWN')
        assert type(m['person']) is int and m['person'] in (0, 1, 2, 3)
        refs(m['token_ids'], m['kind'] in ('IMPLICIT', 'UNKNOWN'))
        assert m['kind'] != 'NAME' or m['person'] == 3, 'ROLE_NAME_PERSON'
    covered = set(); predicates = []
    for c in clauses.values():
        assert set(c) == {'id', 'token_ids', 'predicate_ids', 'subject_id', 'scope'}
        refs(c['token_ids']); refs(c['predicate_ids'], True)
        assert set(c['predicate_ids']) <= set(c['token_ids'])
        assert c['subject_id'] == 'UNKNOWN' or c['subject_id'] in mentions
        assert c['scope'] in ('NARRATION', 'DIRECT_SPEECH', 'EMBEDDED_SPEECH', 'UNKNOWN')
        literals = {a['id']: a['literal'] for a in anchors}
        words = [_word(literals[t]) for t in c['predicate_ids']]
        embedded = sum(re.search(r'(?:dığ|diğ|duğ|düğ|tığ|tiğ|tuğ|tüğ)[ıiuü](?:n[ıiuü])?$', w) is not None for w in words)
        finite_reports = {'belirtir', 'belirtti', 'belirtilir', 'belirtilmiştir', 'söyler', 'söyledi', 'söylenir', 'söylenmiştir', 'dedi', 'der', 'etti', 'eder', 'bağırdı', 'bağırır', 'says', 'said', 'states', 'stated', 'reported'}
        assert embedded <= 1 and not (embedded and any(w in finite_reports for w in words)), 'ROLE_REPORT_CONTENT_COLLAPSED'
        covered.update(c['token_ids']); predicates.extend(c['predicate_ids'])
    assert covered == set(order) and len(predicates) == len(set(predicates)), 'ROLE_TOKEN_COVERAGE'
    for a in anchors:
        if re.search(r'(?:dığ|diğ|duğ|düğ|tığ|tiğ|tuğ|tüğ)[ıiuü](?:n[ıiuü])?$', _word(a['literal'])):
            assert a['id'] in predicates, 'ROLE_EMBEDDED_PREDICATE_OMITTED'
    for anchor in anchors:
        literal = anchor['literal'].strip(".,!?;:\"“”()[]").strip("'‘’")
        person = 1 if literal == 'I' else {'ben': 1, 'biz': 1, 'sen': 2, 'siz': 2, 'we': 1, 'you': 2, 'i': 1}.get(_word(literal))
        if person:
            containing = [m for m in mentions.values() if anchor['id'] in m['token_ids']]
            assert containing and all(m['kind'] == 'PRONOUN' and m['person'] == person for m in containing), 'ROLE_PRONOUN_PERSON'
    return mentions, clauses



def _resolved_reports(graph, anchors, mentions, clauses):
    """Independently derive report authority; model reporter enums are not proof."""
    by_token={a['id']:a for a in anchors}
    passive={'belirtilir','belirtilmiştir','söylenir','söylenmiştir'}
    vocabulary=passive | {'belirtir','belirtti','söyler','söyledi','dedi','der','ifade','etti','eder',
                           'bağırdı','bağırır','says','said','states','stated','reported'}
    generic={'konuşmacı','konuşan kişi','the speaker'}
    def words(clause):return [_word(by_token[t]['literal']) for t in clause['predicate_ids']]
    raw=graph['reports'];assert isinstance(raw,list)
    chosen=list(raw)
    if not chosen:
        possible=[c for c in clauses.values() if c['subject_id']=='UNKNOWN'
                  and len(c['predicate_ids'])==1 and words(c)[0] in passive
                  and c['predicate_ids'][-1]==anchors[-1]['id']]
        if len(possible)==1:
            wrapper=possible[0];children=[c for c in clauses.values() if c['id']!=wrapper['id']]
            if children and all(c['predicate_ids'] and re.search(
                    r'(?:dığ|diğ|duğ|düğ|tığ|tiğ|tuğ|tüğ)[ıiuü](?:n[ıiuü])?$',words(c)[-1]) for c in children):
                chosen=[{'wrapper_clause_id':wrapper['id'],
                         'content_clause_ids':[c['id'] for c in children],'reporter_kind':'ANONYMOUS'}]
    resolved=[];edges={};seen_wrappers=set()
    for item in chosen:
        assert isinstance(item,dict) and set(item)=={'wrapper_clause_id','content_clause_ids','reporter_kind'}
        wid=item['wrapper_clause_id'];children=item['content_clause_ids']
        assert isinstance(wid,str) and wid in clauses and wid not in seen_wrappers
        assert item['reporter_kind'] in ('ANONYMOUS','NAMED','UNRESOLVED')
        assert isinstance(children,list) and children and all(isinstance(c,str) and c in clauses for c in children)
        assert len(children)==len(set(children))
        wrapper=clauses[wid];predicate=words(wrapper);subject=mentions.get(wrapper['subject_id'])
        is_report=(bool(predicate) and all(w in vocabulary for w in predicate)
                   and (not set(predicate)&{'ifade','etti','eder'} or predicate in (['ifade','etti'],['ifade','eder'])))
        anonymous=((wrapper['subject_id']=='UNKNOWN' and len(predicate)==1 and predicate[0] in passive)
                   or (subject is not None and subject['kind']!='NAME'
                       and _word(' '.join(by_token[t]['literal'] for t in subject['token_ids'])) in generic))
        kind='UNRESOLVED'
        if is_report:
            if anonymous:kind='ANONYMOUS'
            elif subject is not None and subject['kind']=='NAME':kind='NAMED'
        report={'wrapper_clause_id':wid,'content_clause_ids':children,'reporter_kind':kind}
        resolved.append(report);seen_wrappers.add(wid)
        for child in children:
            assert child!=wid and child not in edges,'ROLE_REPORT_EDGE_COLLISION'
            assert clauses[child]['predicate_ids'] or clauses[child]['scope']=='DIRECT_SPEECH'
            edges[child]=report
    for child in edges:
        path=set();node=child
        while node in edges:
            assert node not in path,'ROLE_REPORT_CYCLE'
            path.add(node);node=edges[node]['wrapper_clause_id']
    return resolved,edges


def verify_role_bindings(claim, regions, review):
    assert review['version'] == 'source-role-bindings-v8', 'ROLE_VERSION'
    assert review['passed'] is True and review['status'] == 'STRUCTURAL_CANDIDATE'
    assert review['reason'] == 'ROLE_BINDINGS_STRUCTURALLY_SUPPORTED' and review['diagnostics'] == []
    assert review['semantic_acceptance'] is False and review['complete'] is False
    assert review['predicate_coverage_proven'] is False and 'reuse' not in review
    assert review['claim_sha256'] == digest(claim['text']) and review['source_sha256'] == digest(regions)
    assert regions and all(isinstance(r.get('text'),str) and isinstance(r.get('span_id'),str) for r in regions)
    assert len({r['span_id'] for r in regions})==len(regions),'ROLE_DUPLICATE_SOURCE'
    assert isinstance(claim.get('text'),str) and claim['text'].strip()
    from role_projection_reference import verify_projection
    projected = verify_projection(regions, review['reading_views'], review['source_projection'])
    source = _anchors(projected, 'SOURCE'); target = _anchors([{'span_id': 'claim', 'text': claim['text']}], 'CLAIM')
    assert source == review['source_tokens'] and target == review['claim_tokens'], 'ROLE_LITERAL_PROVENANCE'
    assert 0 < len(source) <= 512 and 0 < len(target) <= 128
    sg, cg = review['source_graph'], review['claim_graph']
    sm, sc = _graph(sg, source); cm, cc = _graph(cg, target)
    attempts = review['attempts']; assert len(attempts) == review['model_calls'] == 3
    source_input = [{'id': a['id'], 'literal': a['literal']} for a in source]
    claim_input = [{'id': a['id'], 'literal': a['literal']} for a in target]
    payloads = [source_input, claim_input, {'source_graph': sg, 'source_tokens': source_input, 'claim_graph': cg, 'claim_tokens': claim_input}]
    for call, stage, payload, output in zip(attempts, ('source', 'claim', 'alignment'), payloads, (sg, cg, review['alignment'])):
        assert call['stage'] == stage and call['input_sha256'] == digest(payload) and call['output'] == output
        assert call['metrics']['finish_reason'] == 'stop', 'ROLE_INCOMPLETE_MODEL_CALL'
    assert isinstance(review['alignment'],dict) and set(review['alignment']) == {'bindings'}
    bindings = review['alignment']['bindings']
    assert isinstance(bindings,list) and all(isinstance(b,dict) for b in bindings)
    assert all(isinstance(b.get('source_clause_id'),str) for b in bindings)
    assert [b['claim_clause_id'] for b in bindings] == list(cc)
    assert all(set(b) == {'claim_clause_id', 'source_clause_id'} for b in bindings)
    bound = {b['claim_clause_id']: sc.get(b['source_clause_id']) for b in bindings}
    sa = {a['id']: a for a in source}; ca = {a['id']: a for a in target}
    generic = {'konuşmacı', 'konuşan kişi', 'the speaker'}
    passive = {'belirtilir', 'belirtilmiştir', 'söylenir', 'söylenmiştir'}
    def nominal(c):
        return bool(c['predicate_ids']) and re.search(r'(?:dığ|diğ|duğ|düğ|tığ|tiğ|tuğ|tüğ)[ıiuü](?:n[ıiuü])?$', _word(ca[c['predicate_ids'][-1]]['literal']))
    source_reports,source_edges=_resolved_reports(sg,source,sm,sc)
    reports,edges=_resolved_reports(cg,target,cm,cc)
    assert review['resolved_claim_reports']==reports,'ROLE_RESOLVED_REPORT_MISMATCH'
    wrappers={r['wrapper_clause_id']:r for r in reports}
    for report in reports:
        if report['reporter_kind']=='ANONYMOUS':
            assert all(bound[child] is not None and bound[child]['scope']=='DIRECT_SPEECH'
                       for child in report['content_clause_ids']),'ROLE_ANONYMOUS_CONTENT_SCOPE'
        elif report['reporter_kind']=='NAMED':
            original_wrapper=bound[report['wrapper_clause_id']]
            assert original_wrapper is not None,'ROLE_REPORT_WRAPPER_MISSING'
            for child in report['content_clause_ids']:
                original=bound[child];assert original is not None
                edge=source_edges.get(original['id'])
                assert edge and edge['reporter_kind']=='NAMED' and edge['wrapper_clause_id']==original_wrapper['id'], 'ROLE_REPORT_SPEAKER_EDGE'
    shared = {}
    for identifier, clause in cc.items():
        if identifier in wrappers and wrappers[identifier]['reporter_kind'] == 'ANONYMOUS':
            continue
        original = bound[identifier]; assert original is not None
        subject = cm.get(clause['subject_id'])
        literal_target = ' '.join(ca[t]['literal'] for t in clause['token_ids']).strip("\"“”‘’'")
        literal_source = ' '.join(sa[t]['literal'] for t in original['token_ids']).strip("\"“”‘’'")
        if clause['scope'] == original['scope'] == 'DIRECT_SPEECH' and (subject is None or subject['kind'] != 'NAME') and literal_target == literal_source:
            continue
        if (clause['scope'] == original['scope'] == 'NARRATION'
                and original['subject_id'] == 'UNKNOWN'
                and subject and subject['kind'] == 'NOMINAL' and subject['token_ids']
                and set(subject['token_ids']) <= set(clause['token_ids'])
                and sum(c['subject_id'] == subject['id'] for c in cc.values()) == 1
                and ' '.join(ca[t]['literal'] for t in clause['token_ids'])
                    == ' '.join(sa[t]['literal'] for t in original['token_ids'])):
            continue
        assert clause['predicate_ids'] and original['predicate_ids']
        edge = edges.get(identifier)
        if subject is None and edge and edge['reporter_kind'] == 'ANONYMOUS':
            pointer = cm.get(cc[edge['wrapper_clause_id']]['subject_id'])
            assert pointer and len(cm) == 1 and pointer['kind'] != 'NAME' and _surface(pointer, ca) in generic and nominal(clause)
            subject = pointer
        assert subject is not None and original['subject_id'] in sm
        authority = sm[original['subject_id']]
        assert 'UNKNOWN' not in (clause['scope'], original['scope'])
        indirect = edge and edge['reporter_kind'] in ('ANONYMOUS','NAMED') and original['scope'] == 'DIRECT_SPEECH' and clause['scope'] in ('NARRATION', 'EMBEDDED_SPEECH')
        assert clause['scope'] == original['scope'] or indirect
        anonymous = indirect and edge['reporter_kind'] == 'ANONYMOUS' and subject['kind'] != 'NAME' and _surface(subject, ca) in generic and authority['person'] == 1 and authority['kind'] in ('PRONOUN', 'IMPLICIT')
        if not anonymous:
            assert subject['person'] == authority['person'] and subject['person'] in (1, 2, 3), 'ROLE_PERSON_TRANSFER'
            assert 'UNKNOWN' not in (subject['kind'], authority['kind'])
            equivalent = subject['person'] == 3 and {subject['kind'], authority['kind']} <= {'NOMINAL', 'PRONOUN'} and _surface(subject, ca)
            assert subject['kind'] == authority['kind'] or equivalent
            assert _surface(subject, ca) == _surface(authority, sa), 'ROLE_NAMED_IDENTITY'
        assert shared.setdefault(subject['id'], authority['id']) == authority['id'], 'ROLE_SUBJECT_MERGE'
