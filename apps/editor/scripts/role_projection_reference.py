"""Independent readonly reading-projection proof verifier; standard library only."""
import hashlib
import json
import math
import re


def sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def ordered(rows):
    bands = []
    for item in sorted(rows, key=lambda r: (r['bbox'][1], r['bbox'][0])):
        x, y, width, height = item['bbox']; candidates = []
        for number, band in enumerate(bands):
            by, bh, members = band
            intersection = min(y+height, by+bh)-max(y, by)
            delta = abs((y+height/2)-(by+bh/2))
            if max(0, intersection)/min(height, bh) >= .5 and delta <= .6*max(height, bh):
                candidates.append((delta, number))
        if not candidates:
            bands.append((y, height, [item]))
        else:
            bands[min(candidates)[1]][2].append(item)
    return [r['span_id'] for _, _, members in bands for r in sorted(members, key=lambda r: r['bbox'][0])]


def verify_projection(regions, reading_views, projection):
    assert isinstance(regions, list) and regions and isinstance(reading_views, list) and reading_views
    assert projection['version'] == 'role-reading-projection-v1'
    assert projection['source_sha256'] == sha(regions) and projection['views_sha256'] == sha(reading_views)
    assert projection['semantic_acceptance'] is False
    source = {}
    for r in regions:
        assert isinstance(r['span_id'], str) and r['span_id'] and r['span_id'] not in source
        assert isinstance(r['text'], str) and isinstance(r['render_sha256'], str)
        assert re.fullmatch('[0-9a-f]{64}', r['render_sha256'])
        b = r['bbox']; assert isinstance(b, (list, tuple)) and len(b) == 4
        assert all(type(v) in (int, float) and math.isfinite(v) for v in b)
        assert b[0] >= 0 and b[1] >= 0 and b[2] > 0 and b[3] > 0
        assert b[0]+b[2] <= 1.000001 and b[1]+b[3] <= 1.000001
        source[r['span_id']] = r
    assert len(projection['projected_regions']) == len(projection['mapping']) == len(reading_views)
    seen = set()
    for view, projected, audit in zip(reading_views, projection['projected_regions'], projection['mapping']):
        refs = view['span_refs']; assert refs and all(isinstance(r, str) and r in source for r in refs)
        assert len(set(refs)) == len(refs) and not seen.intersection(refs)
        seen.update(refs); rows = [source[r] for r in refs]
        assert len({r['render_sha256'] for r in rows}) == 1 and ordered(rows) == refs
        assert view['raw_text'] == '\n'.join(r['text'] for r in rows)
        joins = view['line_end_joins']; assert isinstance(joins, list)
        operations = {}; positions = []
        for edge in joins:
            assert set(edge) == {'left_span_ref', 'right_span_ref', 'operation'}
            left, right = edge['left_span_ref'], edge['right_span_ref']
            assert left in refs and right in refs and refs.index(right) == refs.index(left)+1
            assert left not in operations
            assert edge['operation'] in ('JOIN_VERIFIED_DROP_CAP_IN_READING_VIEW_ONLY', 'REMOVE_GEOMETRIC_LINE_END_HYPHEN_IN_READING_VIEW_ONLY')
            operations[left] = edge['operation']; positions.append(refs.index(left))
        assert positions == sorted(positions)
        # Preserve an independent origin tape, including inserted separators.
        tape = [(c, refs[0], i) for i, c in enumerate(rows[0]['text'])]; removed = []
        for index in range(1, len(rows)):
            left, right = rows[index-1], rows[index]
            suffix = [(c, refs[index], i) for i, c in enumerate(right['text'])]
            operation = operations.get(refs[index-1])
            if operation is None:
                tape += [('\n', None, None)] + suffix; continue
            ax, ay, aw, ah = left['bbox']; bx, by, bw, bh = right['bbox']
            if operation.startswith('JOIN_VERIFIED'):
                initial, body = left['text'].strip(), right['text'].lstrip()
                assert len(initial) == 1 and initial.isalpha() and initial.isupper() and body and body[0].islower()
                assert ah >= 1.4*bh and ax < bx and -.5*aw <= bx-(ax+aw) <= .15*bh
                assert max(0, min(ay+ah, by+bh)-max(ay, by)) >= .5*bh and ay+ah > by+bh
            else:
                assert re.search(r'\w-\s*$', left['text']) and re.match(r'^\s*\w', right['text'])
                assert by >= ay+.5*ah and by-(ay+ah) <= 2*max(ah, bh)
                assert max(0, min(ax+aw, bx+bw)-max(ax, bx)) >= .5*min(aw, bw)
            while tape and tape[-1][0].isspace(): removed.append(tape.pop())
            if operation.startswith('REMOVE_'):
                assert tape and tape[-1][0] == '-'; removed.append(tape.pop())
            while suffix and suffix[0][0].isspace(): removed.append(suffix.pop(0))
            tape += suffix
        text = ''.join(v[0] for v in tape)
        assert text == view['reading_text']
        identity = 'VIEW_' + sha({'version': projection['version'], 'regions': rows, 'view': view})
        assert projected == {'span_id': identity, 'text': text, 'source_span_refs': refs, 'render_sha256': rows[0]['render_sha256']}
        assert audit['span_id'] == identity and audit['line_end_joins'] == joins
        assert audit['removed_characters'] == [{'literal': c, 'source_span_id': r, 'source_offset': o} for c, r, o in removed]
        expected = {i: (r, o) for i, (c, r, o) in enumerate(tape) if not c.isspace()}
        actual = {}; origins = set(); previous = None
        for segment in audit['character_ranges']:
            assert set(segment) == {'projected_start', 'projected_end', 'source_span_id', 'source_start', 'source_end'}
            a, b, u, v = [segment[k] for k in ('projected_start','projected_end','source_start','source_end')]
            ref = segment['source_span_id']; assert ref in source
            assert all(type(n) is int for n in (a,b,u,v)) and 0 <= a < b <= len(text)
            assert 0 <= u < v <= len(source[ref]['text']) and b-a == v-u
            assert text[a:b] == source[ref]['text'][u:v] and not any(c.isspace() for c in text[a:b])
            if previous:
                assert a >= previous['projected_end']
                assert not (a == previous['projected_end'] and ref == previous['source_span_id'] and u == previous['source_end'])
            for offset in range(b-a):
                assert a+offset not in actual and (ref,u+offset) not in origins
                actual[a+offset] = (ref,u+offset); origins.add((ref,u+offset))
            previous = segment
        assert actual == expected
    assert seen == set(source)
    return projection['projected_regions']
