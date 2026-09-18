"""Cross-page dialogue links from literal OCR and separately measured tail geometry.

No model call, inferred name, fuzzy quote match or global character merge occurs.
Inputs are current-generation evidence-scoped page bundles, never free captions.
"""
import hashlib
import json
import re
import uuid
from collections import defaultdict

VERSION = 'cross-page-literal-attribution-v8'


def _hash(value):
    def scalar(item):
        # PostgreSQL returns UUID objects; HTTP returns their canonical strings.
        # Preserve the same hash at both boundaries without accepting arbitrary
        # non-JSON application objects through a broad default=str fallback.
        if isinstance(item, uuid.UUID):
            return str(item)
        raise TypeError('UNSUPPORTED_CROSS_PAGE_HASH_TYPE:'+type(item).__name__)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'),default=scalar).encode()).hexdigest()


def _overlap(a, b):
    return min(a[0]+a[2], b[0]+b[2]) > max(a[0], b[0]) and min(a[1]+a[3], b[1]+b[3]) > max(a[1], b[1])


def _prefix(value, word_count):
    words=list(re.finditer(r'[^\W_]+',value))
    if len(words)<word_count:return None
    end=words[word_count].start() if len(words)>word_count else len(value)
    prefix=value[:end].rstrip()
    return prefix,len(prefix)


def _punctuation(value):
    value=value.translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))
    count=0;signature=[]
    for token in re.findall(r'[^\W_]+|[^\w\s]',value):
        if token[0].isalnum():count+=1
        else:signature.append((count,token))
    return signature


def resolve(pages, minimum_quote_tokens=4, max_page_distance=1):
    from editor.source_alignment import valid_box, reading_order
    from editor.source_pipeline import quote_tokens, negation
    from editor.text_attribution import extract
    from editor.source_review import speaker_candidates
    from editor.figure_identity import contained
    from editor.visual_coverage import coverage
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
        original_role=bundle.get('page_role','UNKNOWN'); effective_role=original_role
        role_authority=None
        contextual=bundle.get('context_role')
        if original_role not in ('NARRATIVE','MIXED') and contextual and contextual.get('eligible_for_identity_context') is True:
            from editor.page_context import build_context, digest as context_digest, VERSION as CONTEXT_VERSION
            payload,allowed_context=build_context(page,pages)
            refs=contextual.get('source_span_refs',[])
            context_valid=(contextual.get('version')==CONTEXT_VERSION
                and contextual.get('pdf_page')==page and contextual.get('input_sha256')==context_digest(payload)
                and contextual.get('eligible_for_identity_context') is True
                and contextual.get('page_role') in ('NARRATIVE','MIXED')
                and contextual.get('review',{}).get('supported') is True
                and contextual.get('metrics',{}).get('finish_reason')=='stop'
                and contextual.get('review_metrics',{}).get('finish_reason')=='stop'
                and contextual.get('uncertainty_review_complete') is True
                and contextual.get('blocking_uncertainties')==[]
                and isinstance(refs,list) and bool(refs)
                and all(isinstance(ref,str) and ref in allowed_context for ref in refs)
                and page in {allowed_context[ref] for ref in refs})
            if context_valid:
                effective_role=contextual['page_role']
                role_authority={'kind':'SOURCE_CONTEXT_REVIEW','record_id':bundle.get('context_role_record_id'),
                    'input_sha256':contextual['input_sha256'],'source_span_refs':refs,
                    'review_method':contextual.get('review_method'),'editorial_acceptance':False}
            else:
                scope_errors.append({'pdf_page':page,'reason':'CONTEXT_ROLE_SCOPE_OR_REVIEW_INVALID'})
        extracted = extract(spans, effective_role)
        fragment_parents = {}
        by_id = {str(row['id']):row for row in spans}
        for fragment in bundle.get('fragments', []):
            fd = fragment['data']; parent = by_id.get(fd.get('parent_source_span_id'))
            proof = fd.get('measurement', {})
            valid_fragment = (parent is not None and parent['data'].get('status') == 'NEEDS_REVIEW'
                and fd.get('status') in ('TEXT_AGREED','NEEDS_REVIEW')
                and fd.get('role') == 'TEXT' and fd.get('pdf_page') == page
                and fd.get('evidence_refs') == [eid] and fd.get('render_sha256') == ed['ocr_render_sha256']
                and contained(fd.get('bbox'), parent['data'].get('bbox'))
                and fd.get('parent_record_sha256', fragment.get('parent_record_sha256')) == _hash(parent['data'])
                and proof.get('parent_source_span_id') == str(parent['id'])
                and proof.get('parent_render_sha256') == ed['ocr_render_sha256']
                and proof.get('bbox') == fd['bbox'] and isinstance(proof.get('blockers'),list)
                and proof.get('selected_text_is_unmodified_reader_output') is True)
            if fd.get('status') == 'TEXT_AGREED' and proof.get('blockers'):
                valid_fragment = False
            if not valid_fragment:
                scope_errors.append({'pdf_page':page,'fragment_id':str(fragment['id']),
                                     'reason':'FRAGMENT_PARENT_OR_MEASUREMENT_SCOPE_MISMATCH'})
                continue
            if fd['status'] != 'TEXT_AGREED':
                # A legitimate rejected reading is not corrupt provenance and
                # must not invalidate independently supported dialogue elsewhere.
                continue
            # Never concatenate across its unresolved parent or another fragment.
            extracted['attributions'].extend(extract([fragment], effective_role)['attributions'])
            fragment_parents[str(fragment['id'])] = str(parent['id'])
        seen_attributions = set()
        for entry in extracted['attributions']:
            tokens = tuple(quote_tokens(entry['quote']))
            refs = tuple(sorted(fragment_parents.get(r,r) for r in entry['source_span_refs']))
            fingerprint = (tokens,entry['label_key'],refs)
            if tokens and fingerprint not in seen_attributions:
                seen_attributions.add(fingerprint)
                attributions[tokens].append({'pdf_page':page, 'evidence_ref':eid, 'entry':entry,
                    'render_sha256':ed['ocr_render_sha256'],
                    'fragment_parent_refs':{r:fragment_parents[r] for r in entry['source_span_refs'] if r in fragment_parents}})
        for candidate in speaker_candidates(layout, visual):
            box = candidate.get('bbox')
            item = {**candidate, 'pdf_page':page, 'page_role':effective_role, 'original_page_role':original_role,
                    'context_role_authority':role_authority,
                    'context_role_reason':contextual.get('reason') if contextual else None, 'method':VERSION, 'speaker':None,
                    'character_instance_id':None, 'visual_identity_verified':False, 'dialogue_link_verified':False,
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
            item['_span_ranges']=[];offset=0
            for row in reading_order(intersecting):
                text=row['data']['text']
                item['_span_ranges'].append({'span_id':str(row['id']),'start':offset,'end':offset+len(text)})
                offset+=len(text)+1
            observations=visual.get('observations',[])
            missing_regions=[r for r in coverage(layout, observations)['regions'] if r['status']=='UNOBSERVED']
            relevant_boxes = [box] + [hit['bbox'] for hit in candidate['tail_figure_hits']]
            def relevant(region):
                rb = region.get('bbox', region.get('region_bbox')) if isinstance(region,dict) else region
                # Unknown geometry cannot establish irrelevance.
                return not valid_box(rb) or any(_overlap(rb, target) for target in relevant_boxes)
            if (any((o.get('figure_limit_reached') or o.get('discarded_figure_candidates',0))
                    and relevant(o) for o in observations)
                    or any(relevant(r) for r in missing_regions)):
                item['reason']='FIGURE_COVERAGE_INCOMPLETE'
                item['local_figure_candidate']=None
    occurrences=defaultdict(list)
    for item in balloons:
        if '_tokens' in item:occurrences[item['_tokens']].append(item)
    for item in balloons:
        tokens=item.pop('_tokens',None)
        if not tokens:
            continue
        short_quote = len(tokens) < minimum_quote_tokens
        matches=attributions.get(tokens,[])
        partial_quote=False;support_tokens=tokens
        if not matches:
            prefix_matches=[]
            for narrated,entries in attributions.items():
                if len(narrated)<len(tokens) and tokens[:len(narrated)]==narrated:
                    prefix_info=_prefix(item['quote'],len(narrated))
                    for entry in entries:
                        if prefix_info and _punctuation(prefix_info[0])==_punctuation(entry['entry']['quote']):
                            prefix_matches.append((narrated,entry,prefix_info))
            if len(prefix_matches)==1:
                support_tokens,matched,prefix_info=prefix_matches[0]
                matches=[matched];partial_quote=True
                item['support_scope']='EXACT_QUOTED_PREFIX_ONLY_NOT_WHOLE_BALLOON'
                item['supported_quote']=prefix_info[0]
                item['supported_quote_span_ranges']=[{'span_id':r['span_id'],'start':0,
                    'end':min(r['end'],prefix_info[1])-r['start']}
                    for r in item.get('_span_ranges',[]) if r['start']<prefix_info[1]]
                item['supported_quote_span_refs']=[r['span_id'] for r in item['supported_quote_span_ranges']]
            elif len(prefix_matches)>1:
                item['reason']='AMBIGUOUS_EXPLICIT_QUOTED_PREFIX'
                continue
        matching_balloons=[other for other_tokens,group in occurrences.items()
            if (other_tokens[:len(support_tokens)]==support_tokens if partial_quote else other_tokens==support_tokens)
            for other in group]
        if len(matches)!=1 or len(matching_balloons)!=1:
            item['reason']='AMBIGUOUS_OR_REPEATED_UTTERANCE' if matches else 'NO_EXPLICIT_NARRATION_ATTRIBUTION'
            continue
        match=matches[0];entry=match['entry']
        short_quote=len(support_tokens)<minimum_quote_tokens
        item['candidate_attribution_page']=match['pdf_page']
        if match['pdf_page']==item['pdf_page']:
            item['reason']='SAME_PAGE_REQUIRES_LOCAL_ATTRIBUTION_GATE'
            continue
        if abs(match['pdf_page'] - item['pdf_page']) > max_page_distance:
            item['reason']='NARRATIVE_CONTINUITY_OUTSIDE_CONFIGURED_PAGE_DISTANCE'
            item['candidate_attribution_page']=match['pdf_page']
            continue
        if item['page_role'] not in ('NARRATIVE', 'MIXED'):
            item['reason']='SOURCE_CONTEXT_PAGE_ROLE_REQUIRED' if item['page_role']=='UNKNOWN' else 'TARGET_PAGE_NOT_NARRATIVE'
            continue
        if not item.get('local_figure_candidate'):
            continue
        if short_quote:
            if abs(match['pdf_page'] - item['pdf_page']) != 1:
                item['reason']='SHORT_QUOTE_REQUIRES_ADJACENT_PAGE'
                continue
            if _punctuation(entry['quote']) != _punctuation(item.get('supported_quote',item['quote'])):
                item['reason']='SHORT_QUOTE_PUNCTUATION_MISMATCH'
                continue
            local_balloon_coverage=[other for other in balloons
                if abs(other['pdf_page']-match['pdf_page'])<=max_page_distance]
            item['balloon_coverage_scope_pages']=sorted({other['pdf_page'] for other in local_balloon_coverage})
            # This is an adjacent-page dialogue link, never a global identity.
            # An unread balloon in a distant scene cannot be a candidate for
            # this narration under the configured page-distance contract.
            if scope_errors or any('quote' not in other for other in local_balloon_coverage):
                item['reason']='SHORT_QUOTE_BALLOON_COVERAGE_INCOMPLETE'
                continue
        if quote_tokens(' '.join(negation(entry['quote']))) != quote_tokens(' '.join(negation(item.get('supported_quote',item['quote'])))):
            item['reason']='NEGATION_MISMATCH'
            continue
        item.update(speaker=entry['label'],verification_status='SOURCE_GROUNDED_CROSS_PAGE_DIALOGUE',
            reason='EXACT_UNIQUE_UTTERANCE_EXPLICIT_NARRATOR_AND_UNIQUE_TAIL',
            visual_identity_verified=not short_quote and not partial_quote, dialogue_link_verified=True,
            short_quote_policy='ADJACENT_EXACT_PUNCTUATION_UNIQUE_MEASURED_DIALOGUE' if short_quote else None,
            character_instance_id=_hash([item['source_sha256'],item['pdf_page'],item['local_figure_candidate'],
                                         item['quote_span_refs'],entry['source_span_refs']]),
            identity_scope='TARGET_PAGE_FIGURE_ONLY_NOT_GLOBAL_CHARACTER_MERGE',
            identity_evidence=[{'kind':'EXPLICIT_NARRATION_ATTRIBUTION','pdf_page':match['pdf_page'],
                'source_span_refs':entry['source_span_refs'],'quote_span_refs':entry['quote_span_refs'],
                'fragment_parent_refs':match['fragment_parent_refs'],
                'evidence_ref':match['evidence_ref'],'render_sha256':match['render_sha256']},
                {'kind':'EXACT_BALLOON_OCR_QUOTE','source_span_refs':item.get('supported_quote_span_refs',item['quote_span_refs']),
                 'support_scope':item.get('support_scope','FULL_BALLOON_QUOTE'),
                 'span_text_ranges':item.get('supported_quote_span_ranges'),
                 'evidence_ref':item['evidence_ref'],'render_sha256':item['ocr_render_sha256']},
                {'kind':'UNIQUE_BALLOON_TAIL','figure_ref':item['local_figure_candidate'],
                 'tail_figure_hits':item['tail_figure_hits'],'render_sha256':item['visual_render_sha256']}])
    for item in balloons:item.pop('_span_ranges',None)
    return {'version':VERSION,'links':balloons,'scope_errors':scope_errors,
            'input_pages':sorted(p['evidence']['data']['pdf_page'] for p in pages),
            'named_identity_count':sum(x['visual_identity_verified'] for x in balloons),
            'grounded_dialogue_link_count':sum(x['dialogue_link_verified'] for x in balloons),
            'minimum_quote_tokens':minimum_quote_tokens,'max_page_distance':max_page_distance,
            'narrative_continuity_verified':False,'input_sha256':_hash(pages),
            'requires_recheck_when_source_coverage_changes':True,
            'semantic_acceptance':False,'global_character_merge':False}


def run(job):
    """Persist only derived dialogue links from this generation's scoped records."""
    from editor.book_store import get_records, fence
    from editor.config import connection
    from editor.source_pipeline import save
    gen=job['generation_id']
    rows={kind:get_records(gen,kind) for kind in
          ('evidence','source_spans','layout_regions','visual_observations','page_claims','source_fragments','page_context_roles')}
    indexes={kind:{r['data']['pdf_page']:r for r in items} for kind,items in rows.items()
             if kind not in ('source_spans','source_fragments','page_context_roles')}
    context_roles={r['data']['pdf_page']:r for r in rows['page_context_roles']}
    pages=[]
    ready=set.intersection(*(set(index) for index in indexes.values()))
    for page in sorted(ready):
        pages.append({'evidence':indexes['evidence'][page],
            'layout':indexes['layout_regions'][page]['data'],
            'visual':indexes['visual_observations'][page]['data'],
            'page_role':indexes['page_claims'][page]['data']['page_role'],
            'spans':[r for r in rows['source_spans'] if r['data']['pdf_page']==page],
            'fragments':[r for r in rows['source_fragments'] if r['data']['pdf_page']==page],
            'context_role':context_roles[page]['data'] if page in context_roles else None,
            'context_role_record_id':str(context_roles[page]['id']) if page in context_roles else None})
    fingerprint=_hash(pages)
    previous=get_records(gen,'cross_page_attributions')
    if previous:
        if (len(previous)!=1 or previous[0]['data'].get('input_sha256')!=fingerprint
                or previous[0]['data'].get('version')!=VERSION):
            raise RuntimeError('CROSS_PAGE_CHECKPOINT_CHANGED_NEW_GENERATION_REQUIRED')
        return previous[0]['data']
    with connection() as db:fence(db,job)
    if pages:
        result=resolve(pages)
    else:
        result={'version':VERSION,'input_sha256':fingerprint,'links':[],
                'named_identity_count':0,'grounded_dialogue_link_count':0,'scope_errors':[],
                'input_pages':[],'reason':'NO_COMPLETE_SOURCE_PAGES','semantic_acceptance':False}
    result['expected_pages']=len(indexes['evidence'])
    result['source_page_coverage_complete']=len(ready)==len(indexes['evidence']) and bool(ready)
    result['global_character_merge']=False
    save(job,'cross_page_attributions','book',result)
    return result
