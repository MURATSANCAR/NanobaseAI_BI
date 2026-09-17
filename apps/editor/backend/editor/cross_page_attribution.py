"""Cross-page dialogue links from literal OCR and separately measured tail geometry.

No model call, inferred name, fuzzy quote match or global character merge occurs.
Inputs are current-generation evidence-scoped page bundles, never free captions.
"""
import hashlib
import json
from collections import defaultdict

VERSION = 'cross-page-literal-attribution-v2'


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def _overlap(a, b):
    return min(a[0]+a[2], b[0]+b[2]) > max(a[0], b[0]) and min(a[1]+a[3], b[1]+b[3]) > max(a[1], b[1])


def resolve(pages, minimum_quote_tokens=4, max_page_distance=1):
    from editor.source_alignment import valid_box, reading_order
    from editor.source_pipeline import quote_tokens, negation
    from editor.text_attribution import extract
    from editor.source_review import speaker_candidates
    from editor.figure_identity import contained
    if not isinstance(minimum_quote_tokens, int) or isinstance(minimum_quote_tokens, bool) or minimum_quote_tokens < 1:
        raise ValueError('INVALID_MINIMUM_QUOTE_TOKENS')
    if not isinstance(max_page_distance, int) or isinstance(max_page_distance, bool) or max_page_distance < 1:
        raise ValueError('INVALID_MAX_PAGE_DISTANCE')
    attributions = defaultdict(list)
    balloons = []
    scope_errors = []
    source_hashes = {p['evidence']['data'].get('source_sha256') for p in pages}
    if len(source_hashes) != 1 or not next(iter(source_hashes), None):
        raise ValueError('CROSS_PAGE_SOURCE_SCOPE_MISMATCH')
    if len({p['evidence']['data']['pdf_page'] for p in pages}) != len(pages):
        raise ValueError('DUPLICATE_PAGE_SCOPE')
    for bundle in pages:
        evidence = bundle['evidence']; ed = evidence['data']; page = ed['pdf_page']
        eid = str(evidence['id']); layout = bundle['layout']; visual = bundle['visual']; spans = bundle['spans']
        scoped = (bool(ed.get('render_sha256')) and bool(ed.get('ocr_render_sha256'))
            and all(x.get('pdf_page') == page and x.get('evidence_refs') == [eid] for x in (layout, visual))
            and all(s['data'].get('pdf_page') == page and s['data'].get('evidence_refs') == [eid]
                    and s['data'].get('render_sha256') == ed['ocr_render_sha256']
                    and valid_box(s['data'].get('bbox')) for s in spans))
        if not scoped:
            scope_errors.append({'pdf_page':page, 'reason':'SOURCE_RENDER_OR_GEOMETRY_SCOPE_MISMATCH'})
            continue
        extracted = extract(spans, bundle.get('page_role', 'UNKNOWN'))
        for entry in extracted['attributions']:
            tokens = tuple(quote_tokens(entry['quote']))
            if len(tokens) >= minimum_quote_tokens:
                attributions[tokens].append({'pdf_page':page, 'evidence_ref':eid, 'entry':entry,
                    'render_sha256':ed['ocr_render_sha256']})
        for candidate in speaker_candidates(layout, visual):
            box = candidate.get('bbox')
            item = {**candidate, 'pdf_page':page, 'page_role':bundle.get('page_role', 'UNKNOWN'), 'method':VERSION, 'speaker':None,
                    'character_instance_id':None, 'visual_identity_verified':False,
                    'verification_status':'UNKNOWN', 'identity_evidence':[], 'eligible_for_synthesis':False,
                    'source_sha256':ed['source_sha256'], 'evidence_ref':eid,
                    'ocr_render_sha256':ed['ocr_render_sha256'], 'visual_render_sha256':ed['render_sha256']}
            balloons.append(item)
            if not valid_box(box):continue
            intersecting = [s for s in spans if _overlap(s['data']['bbox'], box)]
            if (not intersecting or any(s['data'].get('status') != 'TEXT_AGREED'
                    or s['data'].get('role') != 'TEXT' or not contained(s['data']['bbox'], box) for s in intersecting)):
                item['reason']='BALLOON_TEXT_NOT_FULLY_SOURCE_AGREED'
                continue
            owners = [b for b in layout.get('balloon_candidates', [])
                      if all(contained(s['data']['bbox'], b.get('bbox')) for s in intersecting)]
            if len(owners) != 1 or layout.get('balloons_truncated'):
                item['reason']='AMBIGUOUS_OR_TRUNCATED_BALLOON_SCOPE'
                continue
            item['quote']='\n'.join(s['data']['text'] for s in reading_order(intersecting))
            item['quote_span_refs']=[str(s['id']) for s in reading_order(intersecting)]
            item['_tokens']=tuple(quote_tokens(item['quote']))
            observations=visual.get('observations',[])
            if (any(o.get('figure_limit_reached') or o.get('discarded_figure_candidates',0) for o in observations)
                    or visual.get('omitted_regions')):
                item['reason']='FIGURE_COVERAGE_INCOMPLETE'
                item['local_figure_candidate']=None
    occurrences=defaultdict(list)
    for item in balloons:
        if '_tokens' in item:occurrences[item['_tokens']].append(item)
    for item in balloons:
        tokens=item.pop('_tokens',None)
        if not tokens or len(tokens)<minimum_quote_tokens:
            continue
        matches=attributions.get(tokens,[])
        if len(matches)!=1 or len(occurrences[tokens])!=1:
            item['reason']='AMBIGUOUS_OR_REPEATED_UTTERANCE' if matches else 'NO_EXPLICIT_NARRATION_ATTRIBUTION'
            continue
        match=matches[0];entry=match['entry']
        if match['pdf_page']==item['pdf_page']:
            item['reason']='SAME_PAGE_REQUIRES_LOCAL_ATTRIBUTION_GATE'
            continue
        if abs(match['pdf_page'] - item['pdf_page']) > max_page_distance:
            item['reason']='NARRATIVE_CONTINUITY_OUTSIDE_CONFIGURED_PAGE_DISTANCE'
            item['candidate_attribution_page']=match['pdf_page']
            continue
        if item['page_role'] not in ('NARRATIVE', 'MIXED'):
            item['reason']='TARGET_PAGE_NOT_NARRATIVE'
            continue
        if not item.get('local_figure_candidate'):
            continue
        if quote_tokens(' '.join(negation(entry['quote']))) != quote_tokens(' '.join(negation(item['quote']))):
            item['reason']='NEGATION_MISMATCH'
            continue
        item.update(speaker=entry['label'],verification_status='SOURCE_GROUNDED_CROSS_PAGE_DIALOGUE',
            reason='EXACT_UNIQUE_UTTERANCE_EXPLICIT_NARRATOR_AND_UNIQUE_TAIL',visual_identity_verified=True,
            character_instance_id=_hash([item['source_sha256'],item['pdf_page'],item['local_figure_candidate'],
                                         item['quote_span_refs'],entry['source_span_refs']]),
            identity_scope='TARGET_PAGE_FIGURE_ONLY_NOT_GLOBAL_CHARACTER_MERGE',
            identity_evidence=[{'kind':'EXPLICIT_NARRATION_ATTRIBUTION','pdf_page':match['pdf_page'],
                'source_span_refs':entry['source_span_refs'],'quote_span_refs':entry['quote_span_refs'],
                'evidence_ref':match['evidence_ref'],'render_sha256':match['render_sha256']},
                {'kind':'EXACT_BALLOON_OCR_QUOTE','source_span_refs':item['quote_span_refs'],
                 'evidence_ref':item['evidence_ref'],'render_sha256':item['ocr_render_sha256']},
                {'kind':'UNIQUE_BALLOON_TAIL','figure_ref':item['local_figure_candidate'],
                 'tail_figure_hits':item['tail_figure_hits'],'render_sha256':item['visual_render_sha256']}])
    return {'version':VERSION,'links':balloons,'scope_errors':scope_errors,
            'input_pages':sorted(p['evidence']['data']['pdf_page'] for p in pages),
            'named_identity_count':sum(x['visual_identity_verified'] for x in balloons),
            'minimum_quote_tokens':minimum_quote_tokens,'max_page_distance':max_page_distance,
            'narrative_continuity_verified':False,'input_sha256':_hash(pages),
            'requires_recheck_when_source_coverage_changes':True,
            'semantic_acceptance':False,'global_character_merge':False}
