"""Read-only book cards. Never generate outputs or treat legacy summaries as current."""
from pathlib import Path
from . import foundation
from .config import settings


def cards() -> list[dict]:
    from . import read_model
    with foundation.read_snapshot() as c:
        books = c.execute('SELECT id FROM ed.book ORDER BY id').fetchall()
        result = []
        for book in books:
            row = read_model.card(c, str(book['id']))
            if row is None:
                continue
            cover = c.execute('SELECT source,page_no FROM ed.book_cover WHERE book_id=%s AND is_current',
                              (book['id'],)).fetchone()
            crm = c.execute('SELECT crm_title,matched_by,authors,illustrators,summary,isbn,first_publish_date'
                            ' FROM ed.book_crm_record WHERE book_id=%s', (book['id'],)).fetchone()
            verified = [x['claim'] for x in row['metadata'] if x.get('subject') == 'AUTHOR']
            # What kind of book it was read as (editor.book_type), from its newest reading: the
            # screen says whether the publisher's record named it or the model decided.
            prof = c.execute('SELECT p.form, p.form_source, p.form_detail, p.audience FROM ed.book_profile p'
                             ' JOIN ed.generation g ON g.id=p.generation_id JOIN ed.book_version v'
                             ' ON v.id=g.book_version_id WHERE v.book_id=%s ORDER BY p.created_at DESC LIMIT 1',
                             (book['id'],)).fetchone()
            result.append({'id': row['book_id'], 'title': row['title'],
                'generationId': row['generation_id'],
                'revision': row['knowledge_revision'] if row['available'] else None,
                # Verified in the book first; the publisher's CRM record stands in, labelled.
                'authors': verified or (crm['authors'] if crm else []),
                'authorsSource': 'BOOK' if verified else ('CRM' if crm and crm['authors'] else None),
                'publisher': {'source': 'CRM', 'title': crm['crm_title'], 'matchedBy': crm['matched_by'],
                              'authors': crm['authors'], 'illustrators': crm['illustrators'],
                              'summary': crm['summary'], 'isbn': crm['isbn'],
                              'firstPublishDate': str(crm['first_publish_date']) if crm['first_publish_date'] else None}
                             if crm else None,
                'summary': row['summary'], 'themes': row['themes'],
                'cover': {'source': cover['source'], 'page': cover['page_no']} if cover else None,
                'contentAvailable': row['available'], 'semanticAcceptance': False,
                'profile': profile_view(prof)})
    return result


def profile_view(p: dict | None) -> dict | None:
    """form, where it came from (CRM | MODEL | NONE), the CRM genre names it rested on and,
    when the model decided, the probability of its choice."""
    if not p:
        return None
    detail = p['form_detail'] or {}
    model = detail.get('model') or {}
    probs = model.get('probabilities') or {}
    return {'form': p['form'], 'source': p['form_source'], 'audience': p['audience'],
            'crmGenres': list((detail.get('crm') or {}).get('genres') or {}),
            'probability': probs.get(p['form']) if p['form_source'] == 'MODEL' else None}


def cover_path(book_id: str) -> tuple[Path,str]:
    with foundation.read_snapshot() as c:
        row=c.execute("SELECT file_path,source FROM ed.book_cover WHERE book_id=%s AND is_current",(book_id,)).fetchone()
    if not row: raise KeyError(book_id)
    path=Path(row['file_path']).resolve()
    if not path.is_relative_to(settings().storage.resolve()) or not path.is_file(): raise KeyError(book_id)
    return path,row['source']


PAGE_MEDIA={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}
PAGE_MAX_BYTES=15*1024*1024


def page_path(book_id: str, page_no: int) -> tuple[Path,str]:
    """Kitabın SON neslinin bir sayfasının render'ı (ed.page.render_path; storage/books/<id>/pages/pNNNN.png).
    Yalnız Editor storage altındaki, 15 MB'ı aşmayan görsel dosya sunulur; yoksa KeyError."""
    with foundation.read_snapshot() as c:
        row=c.execute(
            'SELECT p.render_path FROM ed.generation g JOIN ed.book_version v ON v.id=g.book_version_id'
            ' JOIN ed.page p ON p.book_version_id=v.id AND p.page_no=%s'
            ' WHERE v.book_id=%s ORDER BY g.created_at DESC, g.id DESC LIMIT 1',(page_no,book_id)).fetchone()
    if not row or not row['render_path']: raise KeyError(book_id)
    path=Path(row['render_path']).resolve()
    mime=PAGE_MEDIA.get(path.suffix.lower())
    if not mime or not path.is_relative_to(settings().storage.resolve()) or not path.is_file(): raise KeyError(book_id)
    if path.stat().st_size>PAGE_MAX_BYTES: raise KeyError(book_id)
    return path,mime
