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
                'contentAvailable': row['available'], 'semanticAcceptance': False})
    return result


def cover_path(book_id: str) -> tuple[Path,str]:
    with foundation.read_snapshot() as c:
        row=c.execute("SELECT file_path,source FROM ed.book_cover WHERE book_id=%s AND is_current",(book_id,)).fetchone()
    if not row: raise KeyError(book_id)
    path=Path(row['file_path']).resolve()
    if not path.is_relative_to(settings().storage.resolve()) or not path.is_file(): raise KeyError(book_id)
    return path,row['source']
