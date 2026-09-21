"""User reads of a validated revision; never fall back to historical outputs.

Producer candidate reads and editor review/audit reads are separate.
Available previews do not imply full-book semantic acceptance.
"""
from . import foundation, source

POLICY = 'current-usable-v1'


class Unavailable(ValueError):
    pass


def artifact(c, gid: str, kind: str) -> dict:
    state = c.execute('SELECT * FROM ed.generation_state WHERE generation_id=%s', (gid,)).fetchone()
    if state is None:
        raise KeyError(gid)
    row = c.execute('SELECT * FROM ed.current_artifact WHERE generation_id=%s AND kind=%s',
                    (gid, kind)).fetchone()
    return {'generation_id': gid, 'knowledge_revision': state['knowledge_revision'],
            'origin': state['origin'], 'policy': POLICY, 'complete_book': False,
            'semantic_acceptance': False, 'mode': 'source_supported_preview',
            'kind': kind, 'available': row is not None, 'artifact': row,
            'reason': None if row else 'MISSING_STALE_OR_UNVALIDATED'}


def snapshot(c, gid: str, required: bool = False):
    selected = artifact(c, gid, 'report')
    row = selected['artifact']
    if row is None:
        if required:
            raise Unavailable('Current validated revision unavailable; rebuild required')
        return selected, None
    snap = c.execute('SELECT content FROM ed.knowledge_snapshot WHERE generation_id=%s '
        'AND revision=%s AND input_digest=%s', (gid, row['input_revision'], row['input_digest'])).fetchone()
    return selected, snap['content']


def metadata(selected):
    return {k: v for k, v in selected.items() if k != 'artifact'}


def records(gid: str, kind: str, limit: int, offset: int) -> dict:
    if kind not in ('claims', 'events', 'emotions'):
        raise KeyError(kind)
    with foundation.read_snapshot() as c:
        selected, snap = snapshot(c, gid)
        rows = sorted(snap[kind], key=lambda r: r['id']) if snap else []
        return {**metadata(selected), 'total': len(rows) if snap else None, 'offset': offset,
                'truncated': offset + limit < len(rows), 'records': rows[offset:offset + limit]}


def report(gid: str, kind: str = 'ANALYSIS') -> dict:
    with foundation.read_snapshot() as c:
        selected = artifact(c, gid, 'report')
        row = selected.pop('artifact')
        if kind != 'ANALYSIS':
            return {**selected, 'kind': kind, 'available': False,
                    'reason': 'REPORT_KIND_NOT_GENERATED', 'markdown': None, 'content': None}
        return {**selected, 'kind': kind, 'id': row['build_key'] if row else None,
                'created_at': row['created_at'] if row else None,
                'markdown': row['content']['markdown'] if row else None,
                'content': row['content'] if row else None}


def timeline(gid: str) -> list[dict]:
    with foundation.read_snapshot() as c:
        selected, snap = snapshot(c, gid, required=True)
        rows = [e for e in snap['events'] if e['modality'] in ('REALIZED', 'MEMORY')]
        return [{**e, 'knowledge_revision': selected['knowledge_revision'], 'semantic_acceptance': False}
                for e in sorted(rows, key=lambda e: (e['story_order'] is None,
                    e['story_order'] or 0, e['page_from'], e['id']))]


def _actors(c, gid, snap):
    return c.execute('SELECT ea.*,ch.canonical_name,ch.identity_status FROM ed.event_actor ea '
        'JOIN ed.character ch ON ch.id=ea.character_id AND ch.generation_id=ea.generation_id '
        "WHERE ea.generation_id=%s AND ea.event_id=ANY(%s::uuid[]) AND ea.role<>'ABSENT' "
        'ORDER BY ea.event_id,ea.p_actor DESC,ea.character_id',
        (gid, [e['id'] for e in snap['events']])).fetchall()


def actors(gid: str) -> list[dict]:
    with foundation.read_snapshot() as c:
        selected, snap = snapshot(c, gid, required=True)
        pairs = _actors(c, gid, snap)
        return [{'event_id': e['id'], 'page_from': e['page_from'], 'page_to': e['page_to'],
                 'modality': e['modality'], 'summary': e['summary'],
                 'extractor_participants': e['participants'],
                 'knowledge_revision': selected['knowledge_revision'], 'semantic_acceptance': False,
                 'characters': [{'character_id': str(a['character_id']), 'character': a['canonical_name'],
                     'identity_status': a['identity_status'], 'role': a['role'],
                     'p_actor': round(a['p_actor'], 3), 'p_involved': round(a['p_involved'], 3)}
                    for a in pairs if str(a['event_id']) == e['id']]}
                for e in snap['events']]



def characters(snap: dict, ids=None) -> list[dict]:
    claims = {r['id']: r for r in snap['claims']}
    return [{k: ch[k] for k in ('id', 'canonical_name', 'aliases', 'identity_status', 'identity_confidence', 'first_page')} | {
        'description': claims[ch['claim_id']]['claim'] if ch.get('claim_id') in claims else None,
        'description_available': ch.get('claim_id') in claims}
        for ch in snap['characters'] if ids is None or ch['id'] in ids]


def character_history(gid: str, name: str) -> dict:
    with foundation.read_snapshot() as c:
        selected, snap = snapshot(c, gid, required=True)
        # Name selects IDs, never joins facts. Wildcards are literal characters.
        matches = c.execute('SELECT id FROM ed.character WHERE generation_id=%s AND '
            '(lower(canonical_name)=lower(%s) OR EXISTS '
            '(SELECT 1 FROM unnest(aliases) a WHERE lower(a)=lower(%s)))', (gid, name, name)).fetchall()
        ids = {str(r['id']) for r in matches}
        chars = characters(snap, ids)
        confirmed = {ch['id'] for ch in chars if ch['identity_status'] == 'CONFIRMED'}
        mentions = c.execute('SELECT cm.id,cm.character_id,cm.page_no,cm.surface_name,cm.via,'
            'cm.resolution,cm.confidence,e.quote,e.kind,e.page_no AS evidence_page,e.source_refs,e.region_id FROM ed.character_mention cm JOIN ed.evidence e '
            'ON e.id=cm.evidence_id AND e.generation_id=cm.generation_id '
            'WHERE cm.generation_id=%s AND cm.character_id=ANY(%s::uuid[]) '
            "AND cm.resolution='RESOLVED' AND (e.quote_verified OR (e.kind='VISUAL' AND EXISTS "
            '(SELECT 1 FROM ed.visual_region vr WHERE vr.id=e.region_id AND vr.generation_id=cm.generation_id))) '
            'ORDER BY cm.page_no,cm.id', (gid, list(confirmed))).fetchall()
        spans = {p['page_no']: {s['span_id']: s for s in p['spans']} for p in snap['sources']}
        regions = {(str(r['id']), r['page_no']) for r in c.execute(
            'SELECT id,page_no FROM ed.visual_region WHERE generation_id=%s', (gid,))}
        def supported(m):
            if m['page_no'] != m['evidence_page']:
                return False
            if m['kind'] == 'VISUAL':
                return (str(m['region_id']), m['page_no']) in regions
            refs = m['source_refs'] or {}
            return refs.get('generation_id') == gid and refs.get('page_no') == m['page_no'] and any(
                (span := spans.get(m['page_no'], {}).get(ref.get('span_id'))) and
                span['source_sha256'] == ref.get('source_sha256') and source.key(m['quote']) and
                source.key(m['quote']) in source.key(span['text']) for ref in refs.get('spans', []))
        mentions = [{k: v for k, v in m.items() if k not in ('kind', 'evidence_page', 'source_refs', 'region_id')}
                    for m in mentions if supported(m)]
        pairs = [a for a in _actors(c, gid, snap) if str(a['character_id']) in confirmed
                 and a['role'] in ('ACTOR', 'INVOLVED')]
        event_ids = {str(a['event_id']) for a in pairs}
        return {**metadata(selected), 'characters': chars, 'ambiguous': len(chars) > 1,
            'mentions': mentions, 'emotions': [e for e in snap['emotions'] if e['character_id'] in confirmed],
            'events': [{**e, 'matched_character_ids': [str(a['character_id']) for a in pairs
                          if str(a['event_id']) == e['id']]}
                       for e in snap['events'] if e['id'] in event_ids]}


def latest(c, book_id):
    return c.execute('SELECT g.id FROM ed.generation g JOIN ed.book_version v ON v.id=g.book_version_id '
        'WHERE v.book_id=%s ORDER BY g.created_at DESC,g.id DESC LIMIT 1', (book_id,)).fetchone()


def card(c, book_id: str) -> dict | None:
    gen = latest(c, book_id)
    if gen is None:
        return None
    selected = artifact(c, str(gen['id']), 'catalog')
    row = selected.pop('artifact')
    content = row['content'] if row else {}
    identity = []
    if row:
        snap = c.execute('SELECT content FROM ed.knowledge_snapshot WHERE generation_id=%s AND revision=%s '
            'AND input_digest=%s', (gen['id'], row['input_revision'], row['input_digest'])).fetchone()['content']
        identity = characters(snap)
    return {**selected, 'book_id': book_id, 'card_id': row['build_key'] if row else None,
            'title': c.execute('SELECT title FROM ed.book WHERE id=%s', (book_id,)).fetchone()['title'],
            'created_at': row['created_at'] if row else None,
            'summary': content.get('summary', []), 'metadata': content.get('metadata', []),
            'themes': content.get('themes', []), 'key_events': content.get('events', []),
            'characters': identity, 'blockers': content.get('blockers', [])}


def cards() -> list[dict]:
    with foundation.read_snapshot() as c:
        books = c.execute('SELECT id FROM ed.book ORDER BY id').fetchall()
        return [r for b in books if (r := card(c, str(b['id']))) is not None]
