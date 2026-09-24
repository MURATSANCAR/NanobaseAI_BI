"""Authenticated catalogue read service; independent of model workers and maintenance.

It also serves the editor review queue and takes decisions on it. That is the one write
this service does, and it is what makes review possible from a screen instead of a shell
on the GPU host. The deciding editor is never taken from the request body: the caller
(the portal bridge) puts its signed-in AD user in `X-Editor`, so a decision always carries
the name of a person.
"""
from pathlib import Path as FsPath
from uuid import UUID
import hmac
import os
import functools
import io
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Path
from fastapi.responses import FileResponse, Response
import psycopg
from .presentation import cards, cover_path, page_path
from . import db, foundation, graph, read_model
from . import review as review_mod
from .proofing._labels import label_of   # etiketler kaynak dosyadan; denetim modülleri yüklenmez
from .proofing import _decision            # editör kararı: saf doğrulama + isabet formülü

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

def _graphed_generation(c, book_id: str):
    """Karakter ağının okunacağı nesil: karakter kimliği tamamlanmış EN YENİ nesil; yoksa en yeni nesil.
    Yeniden analiz süren yeni nesilde henüz karakter yoktur; ağ o sırada boş görünmemeli."""
    row = c.execute(
        'SELECT g.id FROM ed.generation g JOIN ed.book_version v ON v.id=g.book_version_id '
        'WHERE v.book_id=%s AND EXISTS (SELECT 1 FROM ed.character ch WHERE ch.generation_id=g.id) '
        'ORDER BY g.created_at DESC, g.id DESC LIMIT 1', (book_id,)).fetchone()
    return row or read_model.latest(c, book_id)

@app.get('/v1/books/{book_id}/graph')
def book_graph(book_id: UUID):
    """Character network of the book's latest generation (fact events only). Edges point
    at node ids; each node counts the usable events the character takes part in."""
    with foundation.read_snapshot() as c:
        gen=_graphed_generation(c,str(book_id))
    if gen is None:
        raise HTTPException(404,'book not found')
    return {'book_id':str(book_id),**graph.network(str(gen['id']))}

def _decisions(c, gid: str, run_ids: list[str]):
    """Her bulgunun GEÇERLİ (en yeni) kararı ve her kuralın (ad+sürüm) BÜTÜN kitaplardaki isabeti.
    proof_decision tablosu yoksa (025 uygulanmadı) boş sözlükler: rapor yine gelir, karar alanı null."""
    try:
        cur=c.execute(
            'SELECT DISTINCT ON (finding_id) finding_id, verdict, reason_code, note, decided_by, created_at'
            ' FROM ed.proof_decision WHERE generation_id=%s ORDER BY finding_id, created_at DESC',(gid,)).fetchall()
        rules=c.execute(
            'SELECT check_name, check_version, verdict, count(*) AS n FROM ('
            '  SELECT DISTINCT ON (finding_id) check_name, check_version, verdict FROM ed.proof_decision'
            '  WHERE (check_name, check_version) IN (SELECT check_name, check_version FROM ed.proof_run WHERE id = ANY(%s))'
            '  ORDER BY finding_id, created_at DESC) d GROUP BY check_name, check_version, verdict',(run_ids,)).fetchall()
    except psycopg.errors.UndefinedTable:
        return {},{}
    counts={}
    for r in rules:
        k=counts.setdefault((r['check_name'],r['check_version']),[0,0])
        k[0 if r['verdict']=='ACCEPT' else 1]+=r['n']
    return {str(r['finding_id']):_decision.public(r) for r in cur},counts

def _proofed_generation(c, book_id: str):
    """Son okumanın gösterileceği nesil: denetimi koşmuş EN YENİ nesil; hiçbiri koşmadıysa en yeni nesil.
    Kitap yeniden analiz edilirken yeni nesil henüz denetlenmemiştir; en yeniyi körü körüne almak ekrandaki
    bütün bulguları ve editör kararlarını analiz bitene kadar kaybettiriyordu."""
    row = c.execute(
        'SELECT g.id FROM ed.generation g JOIN ed.book_version v ON v.id=g.book_version_id '
        'WHERE v.book_id=%s AND EXISTS (SELECT 1 FROM ed.proof_run r WHERE r.generation_id=g.id) '
        'ORDER BY g.created_at DESC, g.id DESC LIMIT 1', (book_id,)).fetchone()
    return row or read_model.latest(c, book_id)


@app.get('/v1/books/{book_id}/proofing')
def book_proofing(book_id: UUID):
    """Son okuma: kitabın son neslinde her denetimin EN YENİ koşusu ve o koşunun bulguları.
    Hiç koşu yoksa boş listeler (404 değil). Salt okuma; hiçbir denetimi başlatmaz.
    Her bulguya `id` ve editörün geçerli kararı (`decision`|null), her denetime kuralın isabeti
    (`precision`|null; aynı ad+sürüm için bütün kitaplardaki geçerli kararlardan) eklenir."""
    with foundation.read_snapshot() as c:
        gen=_proofed_generation(c,str(book_id))
        if gen is None:
            raise HTTPException(404,'book not found')
        gid=str(gen['id'])
        try:
            runs=c.execute(
                'SELECT DISTINCT ON (check_name) id, check_name, check_version, status, error, started_at, finished_at'
                ' FROM ed.proof_run WHERE generation_id=%s ORDER BY check_name, started_at DESC',(gid,)).fetchall()
            rows=c.execute(
                "SELECT id, check_name, page_no, severity, message, quote, suggestion, bbox,"
                " details->>'advisory' AS advisory FROM ed.proof_finding"
                ' WHERE run_id = ANY(%s) ORDER BY page_no NULLS FIRST, severity DESC, created_at',
                ([r['id'] for r in runs],)).fetchall() if runs else []
        except psycopg.errors.UndefinedTable:
            raise HTTPException(503,'proofing tables missing (db migration 023_proofing not applied)') from None
        decisions,counts=_decisions(c,gid,[r['id'] for r in runs]) if runs else ({},{})
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
                       'serious':by_check.get(r['check_name'],[0,0])[1],'error':r['error'],
                       'precision':_decision.precision(*counts.get((r['check_name'],r['check_version']),(0,0)))} for r in runs],
            'findings':[{'id':str(r['id']),'check':r['check_name'],'label':label_of(r['check_name']),'page':r['page_no'],
                         'severity':r['severity'],'message':r['message'],'quote':r['quote'],
                         'suggestion':r['suggestion'],'bbox':r['bbox'],
                         # set when the check's premise does not hold for this kind of book (proofing.as_advice)
                         'advisory':r['advisory'],
                         'decision':decisions.get(str(r['id']))} for r in rows]}

@app.post('/v1/books/{book_id}/proofing/findings/{finding_id}/decision')
def book_proofing_decision(book_id: UUID, finding_id: UUID, body: dict = Body(...)):
    """Editörün bulguya kararı: «Doğru» (ACCEPT) ya da «Yanlış alarm» (REJECT + gerekçe [+ not]).
    Servisin TEK yazma ucudur ve yazdığı şey kitap verisi değil, editörün (insanın) kaydıdır (docs/PORTAL-CARDS.md).
    Bulgu o kitabın SON nesline ait olmalı (eski nesle karar 404). Salt ekleme: yeni karar eskisini geçersiz
    kılar; geçerli karar döner. Kitabı düzeltmez, denetim koşturmaz."""
    try:
        v=_decision.validate(body)
    except _decision.DecisionError as e:
        raise HTTPException(422,str(e)) from None
    with foundation.read_snapshot() as c:
        gen=_proofed_generation(c,str(book_id))
    if gen is None:
        raise HTTPException(404,'book not found')
    gid=str(gen['id'])
    try:
        with db.tx() as c:
            f=c.execute(
                'SELECT f.id, f.check_name, r.check_version FROM ed.proof_finding f JOIN ed.proof_run r ON r.id=f.run_id'
                ' WHERE f.id=%s AND f.generation_id=%s',(str(finding_id),gid)).fetchone()
            if f is None:
                raise HTTPException(404,'finding not found in the proofed generation of this book')
            row=c.execute(
                'INSERT INTO ed.proof_decision(finding_id, generation_id, check_name, check_version, verdict, reason_code,'
                ' note, decided_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)'
                ' RETURNING verdict, reason_code, note, decided_by, created_at',
                (str(finding_id),gid,f['check_name'],f['check_version'],v['verdict'],v['reason_code'],v['note'],
                 v['decided_by'])).fetchone()
    except psycopg.errors.UndefinedTable:
        raise HTTPException(503,'proof_decision table missing (db migration 025_proof_decision not applied)') from None
    return {'book_id':str(book_id),'generation_id':gid,'finding_id':str(finding_id),'decision':_decision.public(row)}


def _msg(e: Exception) -> str:
    """The error's own sentence (a KeyError's str() would wrap it in quotes)."""
    return str(e.args[0]) if e.args else str(e)


def _editor(x_editor: str = Header(default='')) -> str:
    name=(x_editor or '').strip()
    if not name:
        raise HTTPException(400,'Kararı veren kişi (X-Editor) eksik.')
    return name[:200]


def _choice(body: dict) -> str:
    """The answer to the item's own question: yes / no / fix (the CLI's approve/reject/correct
    are still understood)."""
    return str(body.get('choice') or body.get('decision') or '')


def _png(path: FsPath) -> FileResponse:
    return FileResponse(path,media_type='image/png',headers={'Cache-Control':'private, no-cache'})


@app.get('/v1/books/{book_id}/review')
def book_review(book_id: UUID, status: str='OPEN', limit: int=200):
    try:
        return review_mod.queue(str(book_id),status,min(limit,500))
    except KeyError as e:
        raise HTTPException(404,_msg(e)) from None


@app.post('/v1/books/{book_id}/review/{item_id}/decide')
def book_review_decide(book_id: UUID, item_id: UUID, body: dict=Body(default={}),
                       editor: str=Depends(_editor)):
    try:
        # The book is in the path so a decision cannot be routed to another book's item.
        return review_mod.decide_many(str(book_id),[str(item_id)],_choice(body),editor,body.get('note'))
    except (KeyError,ValueError) as e:
        raise HTTPException(400,_msg(e)) from None


@app.post('/v1/books/{book_id}/review/decide-many')
def book_review_decide_many(book_id: UUID, body: dict=Body(default={}), editor: str=Depends(_editor)):
    items=[str(x) for x in (body.get('items') or [])]
    if not items:
        raise HTTPException(400,'Karar verilecek kayıt seçilmedi.')
    try:
        return review_mod.decide_many(str(book_id),items,_choice(body),editor,body.get('note'))
    except (KeyError,ValueError) as e:
        raise HTTPException(400,_msg(e)) from None


@app.get('/v1/books/{book_id}/pages/{page_no}/context')
def book_page_context(book_id: UUID, page_no: int=Path(ge=1)):
    try:
        return review_mod.page_context(str(book_id),page_no)
    except KeyError as e:
        raise HTTPException(404,_msg(e)) from None


@app.get('/v1/books/{book_id}/figures/{region_id}')
def book_figure_image(book_id: UUID, region_id: UUID):
    try:
        return _png(review_mod.figure_image(str(book_id),str(region_id)))
    except KeyError as e:
        raise HTTPException(404,_msg(e)) from None
