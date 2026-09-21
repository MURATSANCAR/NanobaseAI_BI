"""Bounded, read-only views for conversational clients.

No producer/model mutations, delegation, or inaccessible spillover files. Every
page names its revision and continuation offset; raw source excerpts stay exact.
"""
import json
from . import foundation, jobs, read_model, source

MAX_CHARS = 18000


def page(rows, offset=0, limit=8):
    if offset < 0 or not 1 <= limit <= 20:
        raise ValueError('offset >= 0 and 1 <= limit <= 20 required')
    selected, size = [], 0
    for row in rows[offset:offset+limit]:
        encoded = json.dumps(row, ensure_ascii=False, default=str)
        if len(encoded) > MAX_CHARS:
            # Never silently discard an oversized record or invent a file path.
            row = {'record_too_large': True, 'id': row.get('id'),
                   'reason': 'Use read_source_page for bounded original excerpts'}
            encoded = json.dumps(row)
        if selected and size + len(encoded) > MAX_CHARS:
            break
        selected.append(row)
        size += len(encoded)
    nxt = offset + len(selected)
    return {'records': selected, 'total': len(rows), 'offset': offset,
            'next_offset': nxt if nxt < len(rows) else None,
            'truncated': nxt < len(rows)}


def books(offset=0, limit=8):
    return page(jobs.list_books(), offset, limit)


def status(book_id):
    with foundation.read_snapshot() as c:
        gen = read_model.latest(c, book_id)
        if gen is None:
            return {'available': False, 'reason': 'NO_ANALYSIS', 'book_id': book_id}
        gid = str(gen['id'])
        selected = read_model.artifact(c, gid, 'report')
        row = c.execute('SELECT job_id FROM ed.generation WHERE id=%s', (gid,)).fetchone()
        job = c.execute('SELECT status,step,error FROM ed.analysis_job WHERE id=%s',
                        (row['job_id'],)).fetchone()
        return {**read_model.metadata(selected), 'book_id': book_id,
                'job_id': str(row['job_id']), 'job': job,
                'maintenance': c.execute('SELECT maintenance FROM ed.runtime_control WHERE singleton').fetchone()['maintenance']}


def section(gid, section='summary', offset=0, limit=8):
    with foundation.read_snapshot() as c:
        selected, snap = read_model.snapshot(c, gid)
        if snap is None:
            return read_model.metadata(selected)
        report = selected['artifact']['content']
        if section == 'summary': rows = report['book_summary']
        elif section == 'characters': rows = read_model.characters(snap)
        elif section in ('events', 'emotions', 'claims', 'reviews', 'contradictions'):
            rows = snap[section]
        elif section == 'blockers': rows = [{'reason': x} for x in snap['blockers']]
        else: raise ValueError('Unknown read section')
        return {**read_model.metadata(selected), 'section': section, **page(rows, offset, limit)}


def source_page(gid, page_no, offset=0, limit=8):
    with foundation.read_snapshot() as c:
        selected, snap = read_model.snapshot(c, gid)
        if snap is None: return read_model.metadata(selected)
        p = next((p for p in snap['sources'] if p['page_no'] == page_no), None)
        if p is None: raise ValueError('Page is not in this generation')
        rows = []
        for s in p['spans']:
            for start in range(0, len(s['text']), 1600):
                rows.append({'span_id': s['span_id'], 'source': s['source'],
                    'paragraph': s['idx'], 'start': s['start'] + start,
                    'end': s['start'] + min(start + 1600, len(s['text'])),
                    'text': s['text'][start:start+1600], 'source_sha256': s['source_sha256']})
        return {**read_model.metadata(selected), 'page_no': page_no,
                'issues': p['issues'], 'page_role': p['page_role'], **page(rows, offset, limit)}


def find(gid, query, offset=0, limit=8):
    """Exact normalized source/claim recall; deterministic and GPU-free.

    This is explicitly lexical, not a replacement for semantic retrieval.
    A miss is not evidence of absence; clients can inspect source pages.
    """
    needle = source.key(query)
    if not 2 <= len(needle) <= 200: raise ValueError('Query length must be 2..200')
    with foundation.read_snapshot() as c:
        selected, snap = read_model.snapshot(c, gid)
        if snap is None: return read_model.metadata(selected)
        rows = [{'id': r['id'], 'text': r['claim'], 'kind': r['kind'],
                 'pages': r['source_pages'], 'status': r['status']}
                for r in snap['claims'] if needle in source.key(r['claim'])]
        return {**read_model.metadata(selected), 'retrieval_mode': 'EXACT_NORMALIZED_CLAIM',
                'absence_not_proven': True, **page(rows, offset, limit)}
