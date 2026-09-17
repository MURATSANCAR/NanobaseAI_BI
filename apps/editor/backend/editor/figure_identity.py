"""Evidence-scoped figure identity and bounded cross-page visual proposals.

Names only come from explicit OCR attribution. Visual similarity never creates a
name or merges characters. An ungrounded anchor remains ungrounded downstream.
"""
import base64
import hashlib
import json
import os

import httpx

from editor.source_alignment import valid_box
from editor.source_review import page_figures, speaker_candidates

VERSION = 'figure-identity-v1'


def contained(inner, outer):
    if not valid_box(inner) or not valid_box(outer):
        return False
    x, y, w, h = inner; a, b, c, d = outer
    return a <= x and b <= y and x+w <= a+c and y+h <= b+d


def resolve_page(layout, visual, spans, attribution):
    """Bind an explicit utterance to its own balloon, never a nearby name."""
    by_id = {str(r['id']): r['data'] for r in spans}
    page = layout.get('pdf_page')
    links = []
    for candidate in speaker_candidates(layout, visual):
        item = {**candidate, 'identity_method': VERSION, 'identity_evidence': [],
                'character_instance_id': None, 'visual_identity_verified': False}
        if candidate['local_figure_candidate']:
            matches = []
            for entry in attribution.get('attributions', []):
                if attribution.get('page_role') != 'NARRATIVE' or entry.get('status') != 'EXPLICIT_TEXT_ATTRIBUTION':
                    continue
                refs = entry.get('source_span_refs', [])
                quote_refs = entry.get('quote_span_refs', [])
                if not refs or not quote_refs or not set(quote_refs) <= set(refs):
                    continue
                if any(ref not in by_id or by_id[ref].get('pdf_page') != page
                       or by_id[ref].get('status') != 'TEXT_AGREED'
                       or by_id[ref].get('role') != 'TEXT' for ref in refs):
                    continue
                if len({by_id[ref].get('render_sha256') for ref in refs}) != 1:
                    continue
                if not all(contained(by_id[ref]['bbox'], candidate['bbox']) for ref in quote_refs):
                    continue
                # A quote spanning two balloons cannot identify either speaker.
                owners = [b for b in layout.get('balloon_candidates', [])
                          if all(contained(by_id[ref]['bbox'], b.get('bbox')) for ref in quote_refs)]
                if len(owners) == 1:
                    matches.append(entry)
            if len(matches) == 1 and not layout.get('balloons_truncated'):
                entry = matches[0]
                digest = hashlib.sha256(json.dumps([page, candidate['local_figure_candidate'],
                    sorted(entry['source_span_refs'])], separators=(',', ':')).encode()).hexdigest()
                item.update(speaker=entry['label'], character_instance_id=digest,
                    reason='EXPLICIT_UTTERANCE_AND_UNIQUE_TAIL',
                    verification_status='SOURCE_GROUNDED_LOCAL_IDENTITY',
                    visual_identity_verified=True,
                    identity_evidence=[{'kind':'EXPLICIT_TEXT_ATTRIBUTION',
                        'source_span_refs':entry['source_span_refs'], 'quote_span_refs':entry['quote_span_refs']},
                        {'kind':'UNIQUE_BALLOON_TAIL', 'figure_ref':candidate['local_figure_candidate'],
                         'tail_figure_hits':candidate['tail_figure_hits']}])
            elif len(matches) > 1:
                item['reason'] = 'AMBIGUOUS_EXPLICIT_ATTRIBUTION'
        # Local identity is not semantic approval or a global person identifier.
        item['eligible_for_synthesis'] = False
        links.append(item)
    return {'method':VERSION, 'pdf_page':page, 'links':links,
            'named_identity_count':sum(x['visual_identity_verified'] for x in links),
            'cross_page_identity_verified':False, 'semantic_acceptance':False}


def compare_figures(root, source_pages, target_page, anchor_page, target_figure, anchor_figure):
    """Compare actual crops without revealing names or expected answers to VLM."""
    from editor.analysis import model
    from editor.ocr_vl import crop_request
    crops = []
    with httpx.Client(timeout=60, trust_env=False) as client:
        for page, figure in ((target_page, target_figure), (anchor_page, anchor_figure)):
            raw = (root / f'page-{page:04}.png').read_bytes()
            if hashlib.sha256(raw).hexdigest() != source_pages[page]['render_sha256']:
                raise RuntimeError('IDENTITY_RENDER_SCOPE_MISMATCH')
            response = crop_request(client, {'image_base64':base64.b64encode(raw).decode(), 'bbox':figure['bbox']})
            response.raise_for_status(); crop = response.json()
            if crop['source_image_sha256'] != source_pages[page]['render_sha256']:
                raise RuntimeError('IDENTITY_CROP_SCOPE_MISMATCH')
            if hashlib.sha256(base64.b64decode(crop['image_base64'],validate=True)).hexdigest() != crop['crop_sha256']:
                raise RuntimeError('IDENTITY_CROP_HASH_MISMATCH')
            crops.append(crop)
    prompt = ('İki kırpımda işaretlenen figürlerin aynı karakter olması görsel olarak destekleniyor mu? '
              'İsim tahmin etme, yazı okuma, konuşmacı belirleme. Kıyafet rengi tek başına yeterli değil. '
              'Yüz, saç ve ayırt edici fiziksel ayrıntıları ayrı ayrı karşılaştır. Örtülme veya belirsizlikte UNKNOWN. '
              'JSON {"decision":"SAME_CANDIDATE|DIFFERENT|UNKNOWN","matching_features":["..."],'
              '"conflicting_features":["..."],"uncertainties":["..."]}. Bu bir kimlik kanıtı değil görsel adaydır.')
    answer, metrics = model([{'role':'user', 'content':[{'type':'text','text':prompt}] + [
        {'type':'image_url','image_url':{'url':'data:image/png;base64,'+c['image_base64']}} for c in crops]}],
        max_tokens=550, prompt_version=VERSION+'-cross-page-crops')
    if not isinstance(answer,dict) or any(not isinstance(answer.get(k),list)
            or any(not isinstance(x,str) for x in answer[k])
            for k in ('matching_features','conflicting_features','uncertainties')):
        raise RuntimeError('IDENTITY_MODEL_SCHEMA_INVALID')
    decision = answer.get('decision')
    if decision not in ('SAME_CANDIDATE','DIFFERENT','UNKNOWN'):
        decision = 'UNKNOWN'
    if answer.get('conflicting_features') or answer.get('uncertainties'):
        decision = 'UNKNOWN' if decision == 'SAME_CANDIDATE' else decision
    return {'decision':decision, 'raw_model_answer':answer, 'metrics':metrics,
            'target_page':target_page, 'anchor_page':anchor_page,
            'target_figure':target_figure['figure_ref'], 'anchor_figure':anchor_figure['figure_ref'],
            'crop_sha256':[c['crop_sha256'] for c in crops],
            'crop_image_base64':[c['image_base64'] for c in crops],
            'source_render_sha256':[source_pages[p]['render_sha256'] for p in (target_page,anchor_page)],
            'visual_identity_verified':False, 'eligible_for_synthesis':False,
            'reason':'VISUAL_SIMILARITY_IS_NOT_TEXT_IDENTITY'}


def run(job, root):
    """Post-reading pass: all pages available before selecting bounded candidates.

    Saves separate immutable identity and comparison records; no source edits.
    A repeated pass resumes completed pairs. An explicit limit is reported, not
    silently treated as full-book identity coverage.
    """
    from editor.book_store import get_records, fence
    from editor.config import connection
    from editor.source_pipeline import save
    gen = job['generation_id']
    by_kind = {k:get_records(gen,k) for k in ('evidence','layout_regions','visual_observations',
                                           'source_spans','character_evidence')}
    pages = {r['data']['pdf_page']:r['data'] for r in by_kind['evidence']}
    layouts = {r['data']['pdf_page']:r['data'] for r in by_kind['layout_regions']}
    visuals = {r['data']['pdf_page']:r['data'] for r in by_kind['visual_observations']}
    attrs = {r['data']['pdf_page']:r for r in by_kind['character_evidence']}
    prior_comparisons = get_records(gen,'figure_comparisons')
    done_pages = {r['data']['pdf_page'] for r in get_records(gen,'figure_identity')}
    resolved = {}
    for page, row in sorted(attrs.items()):
        spans = [r for r in by_kind['source_spans'] if r['data']['pdf_page'] == page]
        resolved[page] = resolve_page(layouts.get(page,{}), visuals.get(page,{}), spans, row['data'])
    # Text-attributed pages supply candidate anchors even when their local visual
    # grounding is missing. Such anchors can never transfer a name automatically.
    distance = max(0,min(2,int(os.environ.get('EDITOR_IDENTITY_ANCHOR_PAGE_DISTANCE','1'))))
    anchors = [(text_page, image_page, figure)
               for text_page,row in sorted(attrs.items()) if row['data'].get('attributions')
               for image_page in sorted(visuals) if abs(image_page-text_page) <= distance
               for figure in page_figures(visuals[image_page])]
    limit = max(0, min(200, int(os.environ.get('EDITOR_IDENTITY_MAX_PAIRS','12'))))
    used = len(prior_comparisons)
    for page, row in sorted(attrs.items()):
        if page in done_pages: continue
        identity = resolved[page]
        comparisons = [r['data'] for r in prior_comparisons if r['data'].get('target_page')==page]
        proposed = []
        targets = {x['local_figure_candidate'] for x in identity['links']
                   if x['local_figure_candidate'] and not x['visual_identity_verified']}
        for figure in page_figures(visuals.get(page,{})):
            if figure['figure_ref'] not in targets: continue
            for text_page, anchor_page, anchor in anchors:
                if anchor_page != page:
                    proposed.append((figure,text_page,anchor_page,anchor))
        for figure, text_page, anchor_page, anchor in proposed:
            if any(x['target_figure']==figure['figure_ref'] and x['anchor_page']==anchor_page
                   and x['anchor_figure']==anchor['figure_ref'] and x.get('anchor_text_page')==text_page
                   for x in comparisons): continue
            if used >= limit: break
            with connection() as db:
                fence(db,job)
            comparison = compare_figures(root,pages,page,anchor_page,figure,anchor)
            comparison['anchor_text_page'] = text_page
            comparison['anchor_text_span_refs'] = sorted({ref for a in attrs[text_page]['data']['attributions']
                                                         for ref in a['source_span_refs']})
            comparison['anchor_identity_verified'] = anchor_page == text_page and any(x['visual_identity_verified']
                and x['local_figure_candidate']==anchor['figure_ref'] for x in resolved[anchor_page]['links'])
            comparison['anchor_text_link_status'] = ('LOCAL_GROUNDED' if comparison['anchor_identity_verified']
                                                       else 'PROXIMITY_ONLY_NOT_IDENTITY')
            pair_key = hashlib.sha256(json.dumps([page,figure['figure_ref'],text_page,anchor_page,
                                                  anchor['figure_ref']],separators=(',',':')).encode()).hexdigest()
            comparison.update(pdf_page=page, method=VERSION)
            save(job,'figure_comparisons',pair_key,comparison)
            comparisons.append(comparison); used += 1
        identity.update(cross_page_candidates=[{k:v for k,v in x.items() if k!='crop_image_base64'} for x in comparisons], candidate_pairs=len(proposed),
                        unprocessed_pairs=max(0,len(proposed)-len(comparisons)), configured_pair_limit=limit,
                        configured_anchor_page_distance=distance)
        save(job,'figure_identity',row['record_key'],identity)
