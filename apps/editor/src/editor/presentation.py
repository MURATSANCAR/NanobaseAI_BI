"""Read-only book cards. Never generate outputs or treat legacy summaries as current."""
from pathlib import Path
from . import foundation
from .config import settings


def cards() -> list[dict]:
    with foundation.read_snapshot() as c:
        rows = c.execute("SELECT DISTINCT ON (b.id) b.id,b.title,g.id AS generation_id "
            "FROM ed.book b JOIN ed.book_version v ON v.book_id=b.id "
            "JOIN ed.generation g ON g.book_version_id=v.id ORDER BY b.id,g.created_at DESC,g.id DESC").fetchall()
        has_outputs = c.execute("SELECT to_regclass('ed.current_artifact') AS name").fetchone()['name'] is not None
        result = []
        for row in rows:
            artifact = c.execute("SELECT content,input_revision FROM ed.current_artifact "
                "WHERE generation_id=%s AND kind='catalog'", (row['generation_id'],)).fetchone() if has_outputs else None
            content = artifact['content'] if artifact else {}
            cover = c.execute("SELECT source,page_no FROM ed.book_cover WHERE book_id=%s AND is_current", (row['id'],)).fetchone()
            result.append({'id':str(row['id']), 'title':row['title'],
                'generationId':str(row['generation_id']), 'revision':artifact['input_revision'] if artifact else None,
                'authors':[x['claim'] for x in content.get('metadata',[]) if x.get('subject')=='AUTHOR'],
                'summary':content.get('summary',[]), 'themes':content.get('themes',[]),
                'cover': {'source':cover['source'], 'page':cover['page_no']} if cover else None,
                'contentAvailable': artifact is not None, 'semanticAcceptance':False})
    return result


def cover_path(book_id: str) -> tuple[Path,str]:
    with foundation.read_snapshot() as c:
        row=c.execute("SELECT file_path,source FROM ed.book_cover WHERE book_id=%s AND is_current",(book_id,)).fetchone()
    if not row: raise KeyError(book_id)
    path=Path(row['file_path']).resolve()
    if not path.is_relative_to(settings().storage.resolve()) or not path.is_file(): raise KeyError(book_id)
    return path,row['source']
