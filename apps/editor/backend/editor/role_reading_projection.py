"""Validate explicit OCR reading joins without changing any original character.

Input scope must already be canonical agreed regions; this module cannot prove
that a caller omitted no outside region. Projection is not semantic acceptance.
"""
import hashlib
import json
import math
import re

VERSION = 'role-reading-projection-v1'
DROP = 'JOIN_VERIFIED_DROP_CAP_IN_READING_VIEW_ONLY'
HYPHEN = 'REMOVE_GEOMETRIC_LINE_END_HYPHEN_IN_READING_VIEW_ONLY'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise RuntimeError('ROLE_READING_PROJECTION_' + reason)


def reading_order(rows):
    lines = []
    for row in sorted(rows, key=lambda r: (r['bbox'][1], r['bbox'][0])):
        x, y, w, h = row['bbox']; compatible = []
        for index, line in enumerate(lines):
            ly, lh = line['y'], line['h']
            overlap = max(0, min(y+h, ly+lh)-max(y, ly))/min(h, lh)
            distance = abs(y+h/2-ly-lh/2)
            if overlap >= .5 and distance <= .6*max(h, lh):
                compatible.append((distance, index))
        if compatible:
            lines[min(compatible)[1]]['rows'].append(row)
        else:
            lines.append({'y': y, 'h': h, 'rows': [row]})
    return [row for line in lines for row in sorted(line['rows'], key=lambda r: r['bbox'][0])]


def project(regions, reading_views):
    require(isinstance(regions, list) and bool(regions) and isinstance(reading_views, list)
            and bool(reading_views), 'INPUT_REQUIRED')
    by_id = {}
    for row in regions:
        require(isinstance(row, dict) and isinstance(row.get('span_id'), str)
                and row['span_id'] and row['span_id'] not in by_id
                and isinstance(row.get('text'), str) and isinstance(row.get('render_sha256'), str)
                and re.fullmatch(r'[0-9a-f]{64}', row['render_sha256']) is not None, 'REGION_INVALID')
        box = row.get('bbox')
        require(isinstance(box, (list, tuple)) and len(box) == 4
                and all(type(v) in (int, float) and math.isfinite(v) for v in box)
                and box[0] >= 0 and box[1] >= 0 and box[2] > 0 and box[3] > 0
                and box[0]+box[2] <= 1.000001 and box[1]+box[3] <= 1.000001, 'BBOX_INVALID')
        by_id[row['span_id']] = row
    projected = []; mappings = []; covered = []
    for view in reading_views:
        require(isinstance(view, dict), 'VIEW_INVALID')
        refs = view.get('span_refs'); joins = view.get('line_end_joins')
        require(isinstance(refs, list) and bool(refs)
                and all(isinstance(ref, str) and ref in by_id for ref in refs)
                and len(set(refs)) == len(refs) and not set(refs).intersection(covered)
                and isinstance(joins, list), 'REF_COVERAGE_INVALID')
        rows = [by_id[ref] for ref in refs]
        require(len({r['render_sha256'] for r in rows}) == 1, 'RENDER_MISMATCH')
        require([r['span_id'] for r in reading_order(rows)] == refs, 'READING_ORDER_INVALID')
        require(view.get('raw_text') == '\n'.join(r['text'] for r in rows), 'RAW_TEXT_MISMATCH')
        edges = {}; edge_order = []
        for edge in joins:
            require(isinstance(edge, dict) and set(edge) == {'left_span_ref', 'right_span_ref', 'operation'}, 'EDGE_SCHEMA')
            left, right, operation = edge['left_span_ref'], edge['right_span_ref'], edge['operation']
            require(isinstance(left, str) and isinstance(right, str) and left in refs and right in refs
                    and refs.index(right) == refs.index(left)+1 and left not in edges
                    and operation in (DROP, HYPHEN), 'EDGE_INVALID')
            edges[left] = (right, operation); edge_order.append(refs.index(left))
        require(edge_order == sorted(edge_order), 'EDGE_ORDER_INVALID')
        def characters(row):
            return [(char, row['span_id'], offset) for offset, char in enumerate(row['text'])]
        chars = characters(rows[0]); removed = []
        for left, right in zip(rows, rows[1:]):
            edge = edges.get(left['span_id']); following = characters(right)
            if edge is None:
                chars.append(('\n', None, None)); chars.extend(following); continue
            x, y, w, h = left['bbox']; xx, yy, ww, hh = right['bbox']
            if edge[1] == DROP:
                glyph = left['text'].strip(); body = right['text'].lstrip()
                overlap = max(0, min(y+h, yy+hh)-max(y, yy))
                require(len(glyph) == 1 and glyph.isalpha() and glyph.isupper() and body and body[0].islower()
                        and h >= 1.4*hh and x < xx and -.5*w <= xx-(x+w) <= .15*hh
                        and overlap >= .5*hh and y+h > yy+hh, 'DROP_CAP_GEOMETRY')
            else:
                overlap = max(0, min(x+w, xx+ww)-max(x, xx))
                require(re.search(r'\w-\s*$', left['text']) and re.match(r'^\s*\w', right['text'])
                        and yy >= y+.5*h and yy-(y+h) <= 2*max(h, hh)
                        and overlap >= .5*min(w, ww), 'HYPHEN_GEOMETRY')
            while chars and chars[-1][0].isspace(): removed.append(chars.pop())
            if edge[1] == HYPHEN:
                require(chars and chars[-1][0] == '-', 'HYPHEN_LITERAL')
                removed.append(chars.pop())
            while following and following[0][0].isspace(): removed.append(following.pop(0))
            chars.extend(following)
        text = ''.join(char for char, _, _ in chars)
        require(text == view.get('reading_text'), 'READING_TEXT_MISMATCH')
        identifier = 'VIEW_' + digest({'version': VERSION, 'regions': rows, 'view': view})
        projected.append({'span_id': identifier, 'text': text, 'source_span_refs': list(refs),
                          'render_sha256': rows[0]['render_sha256']})
        ranges = []
        for index, (char, ref, offset) in enumerate(chars):
            if char.isspace():
                continue
            if (ranges and ranges[-1]['source_span_id'] == ref
                    and ranges[-1]['projected_end'] == index
                    and ranges[-1]['source_end'] == offset):
                ranges[-1]['projected_end'] += 1; ranges[-1]['source_end'] += 1
            else:
                ranges.append({'projected_start': index, 'projected_end': index+1,
                               'source_span_id': ref, 'source_start': offset, 'source_end': offset+1})
        mappings.append({'span_id': identifier, 'character_ranges': ranges,
                         'removed_characters': [{'literal': char, 'source_span_id': ref, 'source_offset': offset}
                                                for char, ref, offset in removed],
                         'line_end_joins': joins})
        covered.extend(refs)
    require(set(covered) == set(by_id) and len(covered) == len(by_id), 'REF_COVERAGE_INCOMPLETE')
    return {'version': VERSION, 'source_sha256': digest(regions), 'views_sha256': digest(reading_views),
            'projected_regions': projected, 'mapping': mappings, 'semantic_acceptance': False}
