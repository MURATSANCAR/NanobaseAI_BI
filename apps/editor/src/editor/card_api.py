"""Authenticated catalogue read service; independent of model workers and maintenance."""
from uuid import UUID
import hmac
import os
import functools
import io
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Path
from fastapi.responses import FileResponse, Response
import psycopg
from .presentation import cards, cover_path, page_path
from . import foundation, graph, read_model
from .proofing._labels import label_of   # etiketler kaynak dosyadan; denetim modülleri yüklenmez

def authorize(authorization: str = Header(default='')):
    expected=os.environ.get('EDITOR_CARDS_KEY','')
    if not expected or not hmac.compare_digest(authorization.removeprefix('Bearer ').strip(),expected):
        raise HTTPException(401,'unauthorized')

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None,dependencies=[Depends(authorize)])

@app.get('/v1/books/cards')
def book_cards():
    return {'items':cards(),'read_only':True}

@app.get('/v1/books/{book_id}/cover')
def book_cover(book_id: UUID):
    try:
        path,source=cover_path(str(book_id))
        return FileResponse(path,headers={'Cache-Control':'private, no-cache','X-Cover-Source':source})
    except KeyError:
        raise HTTPException(404,'cover not found') from None

@functools.lru_cache(maxsize=512)
def _thumb(path: str, mtime_ns: int, width: int) -> bytes:
    """Sayfa render'ının en fazla `width` piksel genişlikte WebP kopyası. Depolama salt okunur bağlı olduğu
    için diske değil belleğe alınır (512 sayfa ≈ 25 MB); dosya değişirse mtime anahtarı yenisini üretir."""
    from PIL import Image
    with Image.open(path) as im:
        im=im.convert('RGB')
        if im.width>width:
            im=im.resize((width, max(1, round(im.height*width/im.width))), Image.LANCZOS)
        buf=io.BytesIO(); im.save(buf,'WEBP',quality=82,method=4)
    return buf.getvalue()

@app.get('/v1/books/{book_id}/pages/{page_no}')
def book_page(book_id: UUID, page_no: int = Path(ge=1), w: int = Query(0, ge=0, le=2000)):
    """Kitabın son neslinde bir sayfanın render'ı (PNG/JPEG/WebP). Sohbetteki sayfa rozetinin önizlemesi.
    `w` verilirse o genişliğe küçültülmüş WebP (önizleme; tam boy PNG ~1,4 MB, önizleme ~60 KB).
    Yalnız Editor storage altındaki dosya, en çok 15 MB; sayfa ya da render yoksa 404. Salt okuma."""
    try:
        path,mime=page_path(str(book_id),page_no)
    except KeyError:
        raise HTTPException(404,'page not found') from None
    if w:
        data=_thumb(str(path), path.stat().st_mtime_ns, w)
        return Response(content=data, media_type='image/webp', headers={'Cache-Control':'private, max-age=3600'})
    return FileResponse(path,media_type=mime,headers={'Cache-Control':'private, max-age=3600'})

@app.get('/v1/books/{book_id}/graph')
def book_graph(book_id: UUID):
    """Character network of the book's latest generation (fact events only). Edges point
    at node ids; each node counts the usable events the character takes part in."""
    with foundation.read_snapshot() as c:
        gen=read_model.latest(c,str(book_id))
    if gen is None:
        raise HTTPException(404,'book not found')
    return {'book_id':str(book_id),**graph.network(str(gen['id']))}

@app.get('/v1/books/{book_id}/proofing')
def book_proofing(book_id: UUID):
    """Son okuma: kitabın son neslinde her denetimin EN YENİ koşusu ve o koşunun bulguları.
    Hiç koşu yoksa boş listeler (404 değil). Salt okuma; hiçbir denetimi başlatmaz."""
    with foundation.read_snapshot() as c:
        gen=read_model.latest(c,str(book_id))
        if gen is None:
            raise HTTPException(404,'book not found')
        gid=str(gen['id'])
        try:
            runs=c.execute(
                'SELECT DISTINCT ON (check_name) id, check_name, check_version, status, error, started_at, finished_at'
                ' FROM ed.proof_run WHERE generation_id=%s ORDER BY check_name, started_at DESC',(gid,)).fetchall()
            rows=c.execute(
                'SELECT check_name, page_no, severity, message, quote, suggestion, bbox FROM ed.proof_finding'
                ' WHERE run_id = ANY(%s) ORDER BY page_no NULLS FIRST, severity DESC, created_at',
                ([r['id'] for r in runs],)).fetchall() if runs else []
        except psycopg.errors.UndefinedTable:
            raise HTTPException(503,'proofing tables missing (db migration 023_proofing not applied)') from None
    by_check={}
    for r in rows:
        n=by_check.setdefault(r['check_name'],[0,0])
        n[0]+=1
        n[1]+=r['severity']!='INFO'
    iso=lambda t: t.isoformat() if t else None
    return {'book_id':str(book_id),'generation_id':gid,
            'checks':[{'name':r['check_name'],'label':label_of(r['check_name']),'version':r['check_version'],
                       'status':r['status'],'started_at':iso(r['started_at']),'finished_at':iso(r['finished_at']),
                       'findings':by_check.get(r['check_name'],[0,0])[0],
                       'serious':by_check.get(r['check_name'],[0,0])[1],'error':r['error']} for r in runs],
            'findings':[{'check':r['check_name'],'label':label_of(r['check_name']),'page':r['page_no'],
                         'severity':r['severity'],'message':r['message'],'quote':r['quote'],
                         'suggestion':r['suggestion'],'bbox':r['bbox']} for r in rows]}
