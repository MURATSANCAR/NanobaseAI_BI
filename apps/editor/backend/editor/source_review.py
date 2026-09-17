"""Explain unresolved measurements without editing or accepting source records.

Figure boxes are crop-relative; balloon tips are page-relative. A geometric
candidate is not a named speaker and cannot serve as an accepted claim source.
"""
from collections import Counter
import math

from editor.source_alignment import valid_box


def point_valid(point):
    return (isinstance(point, (list, tuple)) and len(point) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) and 0 <= v <= 1 for v in point))


def page_figures(visual):
    result = []
    for oi, observation in enumerate(visual.get('observations', [])):
        crop = observation.get('region_bbox')
        if not valid_box(crop):
            continue
        for fi, figure in enumerate(observation.get('figures', [])):
            box = figure.get('bbox')
            if not valid_box(box):
                continue
            x, y, w, h = crop
            fx, fy, fw, fh = box
            result.append({'figure_ref': f'observation-{oi}/figure-{fi}',
                           'local_id': figure.get('local_id'),
                           'bbox': [x+fx*w, y+fy*h, fw*w, fh*h]})
    return result


def speaker_candidates(layout, visual):
    figures = page_figures(visual)
    result = []
    for bi, balloon in enumerate(layout.get('balloon_candidates', [])):
        tips = balloon.get('tail_tip_candidates', [])
        valid_tips = [t for t in tips if point_valid(t)]
        hits = []
        for tip in valid_tips:
            for f in figures:
                x, y, w, h = f['bbox']
                if x <= tip[0] <= x+w and y <= tip[1] <= y+h:
                    hits.append({'tip': tip, **f})
        refs = sorted({h['figure_ref'] for h in hits})
        reason = ('INVALID_BALLOON_GEOMETRY' if not valid_box(balloon.get('bbox'))
                  else 'INVALID_TAIL_GEOMETRY' if len(valid_tips) != len(tips)
                  else 'NO_TAIL_DETECTED' if not valid_tips
                  else 'NO_FIGURE_AT_TAIL' if not refs
                  else 'AMBIGUOUS_TAIL_OR_FIGURE' if len(valid_tips) != 1 or len(refs) != 1
                  else 'CHARACTER_IDENTITY_NOT_GROUNDED')
        result.append({'balloon_index': bi, 'bbox': balloon.get('bbox'),
                       'text_line_indices': balloon.get('text_line_indices', []),
                       'tail_figure_hits': hits, 'reason': reason,
                       'local_figure_candidate': refs[0] if reason == 'CHARACTER_IDENTITY_NOT_GROUNDED' else None,
                       'speaker': None, 'verification_status': 'NEEDS_REVIEW',
                       'eligible_for_synthesis': False})
    return result


def source_review(rows):
    pages = {}
    for row in rows:
        d = row['data']; page = d.get('pdf_page')
        if page is None:
            continue
        item = pages.setdefault(page, {'pdf_page': page, 'spans': [], 'layout': {}, 'visual': {}})
        if row['kind'] == 'source_spans':
            item['spans'].append(row)
        elif row['kind'] == 'layout_regions':
            item['layout'] = d
        elif row['kind'] == 'visual_observations':
            item['visual'] = d
    results = []; issues = Counter(); total = agreed = 0
    for page, item in sorted(pages.items()):
        unresolved = []
        for row in item['spans']:
            d = row['data']; total += 1
            if d['status'] == 'TEXT_AGREED':
                agreed += 1
                continue
            issues.update(d.get('issues', []))
            # Missing reader and conflicting reader require different follow-up.
            readers = {
                'native_pdf': 'UNUSABLE_OR_MISSING' if not d.get('pdf_usable') else 'AVAILABLE',
                'tesseract': 'AVAILABLE' if d.get('secondary_text', '').strip() else 'MISSING',
                'regional_paddle': 'AVAILABLE' if (d.get('region_text') or '').strip() else 'MISSING',
            }
            unresolved.append({'span_id': str(row['id']), 'bbox': d['bbox'],
                               'issues': d.get('issues', []), 'readers': readers,
                               'next_action': 'REGION_READING_REQUIRED',
                               'status': 'NEEDS_REVIEW'})
        results.append({'pdf_page': page, 'span_count': len(item['spans']),
                        'review_spans': len(unresolved), 'regions': unresolved,
                        'speakers': speaker_candidates(item['layout'], item['visual']),
                        'speaker_coverage': 'CANDIDATES_ONLY',
                        'missing_layout': not bool(item['layout']),
                        'missing_visual_observations': not bool(item['visual'])})
    return {'method': 'source-review-v1', 'source_spans': total, 'agreed_spans': agreed,
            'review_spans': total-agreed, 'issue_counts': dict(issues), 'pages': results,
            'semantic_acceptance': False, 'application_writes': 0}
