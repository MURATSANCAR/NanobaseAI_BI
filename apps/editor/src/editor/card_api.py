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
from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Query, Path, UploadFile
from fastapi.responses import FileResponse, Response
import psycopg
from .presentation import cards, cover_path, page_path
from . import db, foundation, graph, read_model
from . import review as review_mod
from .proofing._labels import label_of   # etiketler kaynak dosyadan; denetim modülleri yüklenmez
from .proofing import _decision            # editör kararı: saf doğrulama + isabet formülü
from .proofing import _messages as proof_text  # bulgu metni: kayıtlı alanlardan, okunurken (eski raporlar da yeni dille)
from .proofing import _carry               # aynı kitabın önceki okumasındaki kararı taşıma (saf eşleme)

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

def _has_carry(c) -> bool:
    """028 uygulandı mı (proof_decision.carried_from + CLEAR)? Uygulanmadıysa isabet eski sorguyla sayılır."""
    return c.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='ed'"
                     " AND table_name='proof_decision' AND column_name='carried_from'").fetchone() is not None

def _decisions(c, gid: str, run_ids: list[str]):
    """Her bulgunun GEÇERLİ (en yeni) kararı ve her kuralın (ad+sürüm) BÜTÜN kitaplardaki isabeti.
    Karar sözlüğünde «geri al» (CLEAR) denmiş bulgu None ile durur: kararı yok ve önceki okumadan karar almaz.
    İsabet: CLEAR sayılmaz; editörün taşınan kararı onaylayan/değiştiren kararı varken aynı kuralın (ad+sürüm)
    kaynak kararı ikinci kez sayılmaz (028; docs/son-okuma/README.md).
    proof_decision tablosu yoksa (025 uygulanmadı) boş sözlükler: rapor yine gelir, karar alanı null."""
    try:
        cur=c.execute(
            'SELECT DISTINCT ON (finding_id) finding_id, verdict, reason_code, note, decided_by, created_at'
            ' FROM ed.proof_decision WHERE generation_id=%s ORDER BY finding_id, created_at DESC',(gid,)).fetchall()
        rule_scope=('SELECT DISTINCT ON (finding_id) id, check_name, check_version, verdict{cf} FROM ed.proof_decision'
                    ' WHERE (check_name, check_version) IN (SELECT check_name, check_version FROM ed.proof_run WHERE id = ANY(%s))'
                    ' ORDER BY finding_id, created_at DESC')
        if _has_carry(c):
            rules=c.execute(
                'WITH d AS (' + rule_scope.format(cf=', carried_from') + ')'
                " SELECT check_name, check_version, verdict, count(*) AS n FROM d x WHERE verdict IN ('ACCEPT','REJECT')"
                ' AND NOT EXISTS (SELECT 1 FROM d y WHERE y.carried_from = x.id AND y.check_name = x.check_name'
                "   AND y.check_version = x.check_version AND y.verdict IN ('ACCEPT','REJECT'))"
                ' GROUP BY check_name, check_version, verdict',(run_ids,)).fetchall()
        else:
            rules=c.execute(
                'SELECT check_name, check_version, verdict, count(*) AS n FROM (' + rule_scope.format(cf='') + ') d'
                ' GROUP BY check_name, check_version, verdict',(run_ids,)).fetchall()
    except psycopg.errors.UndefinedTable:
        return {},{}
    counts={}
    for r in rules:
        k=counts.setdefault((r['check_name'],r['check_version']),[0,0])
        k[0 if r['verdict']=='ACCEPT' else 1]+=r['n']
    return {str(r['finding_id']):_decision.public(r) for r in cur},counts

_IDENT_SQL='jsonb_build_object(' + ','.join(f"'{k}',details->'{k}'" for k in _carry.ID_FIELDS) + ')'

def _carried(c, book_id: str, gid: str, run_ids: list[str], rows: list[dict], own: dict) -> dict:
    """Aynı kitabın ÖNCEKİ okumalarındaki (eski nesiller ve aynı nesilde eski koşular) geçerli kararların bugünkü
    bulgulara taşınması — {bulgu_id: ekrana giden karar (inherited)}. Yalnız okur, hiçbir şey yazmaz: taşınan karar
    editör onaylayana ya da değiştirene kadar bir gösterimdir ve isabete girmez. Kendi kararı (CLEAR dahil) olan
    bulgu karar almaz. `rows`: bugünkü bulgular (id, check_name, page_no, quote, bbox, ident)."""
    try:
        dec=c.execute(
            'SELECT DISTINCT ON (d.finding_id) d.id, d.finding_id, d.verdict, d.reason_code, d.note, d.decided_by,'
            ' d.created_at, d.check_version, f.run_id FROM ed.proof_decision d JOIN ed.proof_finding f ON f.id=d.finding_id'
            ' JOIN ed.generation g ON g.id=f.generation_id JOIN ed.book_version v ON v.id=g.book_version_id'
            ' WHERE v.book_id=%s AND NOT (f.run_id = ANY(%s)) ORDER BY d.finding_id, d.created_at DESC',
            (book_id,run_ids)).fetchall()
    except psycopg.errors.UndefinedTable:
        return {}
    checks={r['check_name'] for r in rows}
    if not dec or not checks:
        return {}
    by_finding={str(d['finding_id']):d for d in dec}
    src=c.execute(
        'SELECT f.id, f.run_id, f.generation_id, f.check_name, f.page_no, f.quote, f.bbox, '+_IDENT_SQL+' AS ident,'
        ' r.started_at FROM ed.proof_finding f JOIN ed.proof_run r ON r.id=f.run_id'
        ' WHERE f.run_id = ANY(%s) AND f.check_name = ANY(%s)',
        (list({d['run_id'] for d in dec}),list(checks))).fetchall()
    sources=[]
    for r in src:
        d=by_finding.get(str(r['id']))
        sources.append({'id':str(r['id']),'run_id':str(r['run_id']),'generation_id':str(r['generation_id']),
                        'check':r['check_name'],'page':r['page_no'],'quote':r['quote'],'bbox':r['bbox'],'ident':r['ident'],
                        'decision':{**d,'read_at':r['started_at']} if d else None})
    current=[{'id':str(r['id']),'check':r['check_name'],'page':r['page_no'],'quote':r['quote'],'bbox':r['bbox'],
              'ident':r['ident'],'blocked':str(r['id']) in own} for r in rows]
    out,_=_carry.carry(current,sources,gid)
    return {fid:_carry.public(v,gid) for fid,v in out.items()}

def _with_carried(c, book_id: str, gid: str, run_ids: list[str], rows: list[dict], own: dict) -> dict:
    """Bulgunun ekrandaki kararı: kendi kararı; yoksa önceki okumadan taşınan (CLEAR denmiş bulgu karar almaz)."""
    carried=_carried(c,book_id,gid,run_ids,rows,own) if run_ids else {}
    return {**carried,**{k:v for k,v in own.items() if v is not None}}

def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None

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
                "SELECT id, check_name, page_no, severity, message, quote, suggestion, bbox, details,"
                " details->>'advisory' AS advisory, details->>'group' AS grp, details->>'confidence' AS confidence,"
                " details->'marks' AS marks, "+_IDENT_SQL+" AS ident FROM ed.proof_finding"
                ' WHERE run_id = ANY(%s) ORDER BY page_no NULLS FIRST, severity DESC, created_at',
                ([r['id'] for r in runs],)).fetchall() if runs else []
        except psycopg.errors.UndefinedTable:
            raise HTTPException(503,'proofing tables missing (db migration 023_proofing not applied)') from None
        decisions,counts=_decisions(c,gid,[r['id'] for r in runs]) if runs else ({},{})
        decisions=_with_carried(c,str(book_id),gid,[r['id'] for r in runs],rows,decisions)
    # Sayaçlar önceki okumada «yanlış alarm» denmiş (taşınan) bulguları saymaz; kaçı gizlendi ayrıca verilir.
    by_check={}
    for r in rows:
        n=by_check.setdefault(r['check_name'],[0,0,0])
        d=decisions.get(str(r['id']))
        if d and d.get('inherited') and d['verdict']=='REJECT':
            n[2]+=1
            continue
        n[0]+=1
        n[1]+=r['severity']!='INFO'
    iso=lambda t: t.isoformat() if t else None
    # sade metin (ne sorun + nerede + neden + öneri; sayısal ayrıntı ayrı): kayıtlı alanlardan okunurken üretilir
    plain={str(r['id']):proof_text.render(r['check_name'],{'page':r['page_no'],'severity':r['severity'],'quote':r['quote'],
           'suggestion':r['suggestion'],'message':r['message'],'details':r['details'] or {}}) for r in rows}
    return {'book_id':str(book_id),'generation_id':gid,
            'checks':[{'name':r['check_name'],'label':label_of(r['check_name']),'version':r['check_version'],
                       'status':r['status'],'started_at':iso(r['started_at']),'finished_at':iso(r['finished_at']),
                       'findings':by_check.get(r['check_name'],[0,0,0])[0],
                       'serious':by_check.get(r['check_name'],[0,0,0])[1],
                       # önceki okumada «yanlış alarm» denip taşındığı için sayılmayan bulgular
                       'hidden':by_check.get(r['check_name'],[0,0,0])[2],'error':r['error'],
                       'precision':_decision.precision(*counts.get((r['check_name'],r['check_version']),(0,0)))} for r in runs],
            'findings':[{'id':str(r['id']),'check':r['check_name'],'label':label_of(r['check_name']),'page':r['page_no'],
                         'severity':r['severity'],'message':plain[str(r['id'])]['text'],'quote':r['quote'],
                         'suggestion':plain[str(r['id'])]['suggestion'],'detail':plain[str(r['id'])]['detail'],
                         'bbox':r['bbox'],
                         # set when the check's premise does not hold for this kind of book (proofing.as_advice)
                         'advisory':r['advisory'],
                         # optional, set by checks that need them (word_variety): a group key for deciding
                         # related findings together, the model's confidence, extra boxes on the same page
                         'group':r['grp'],'confidence':_num(r['confidence']),'marks':r['marks'],
                         'decision':decisions.get(str(r['id']))} for r in rows]}

# ------------------------------------------------------------------ portal belge okuma (editor.portal_read)
@app.post('/v1/read')
async def portal_document_read(file: UploadFile = File(...), ocr: str = Form(default='auto'), pages: str = Form(default='')):
    """Portalın yüklediği belgenin (PDF ya da görüntü) sayfa sayfa metni: metin katmanı varsa o, yoksa OCR.
    Sayfa: {page, text, source: text|ocr|none, confidence, reasons}. Dosya diske yazılmaz, model defterine
    içerik yazılmaz (özgeçmiş gibi kişisel belge). `ocr=off`: yalnız katman. `pages`: OCR yalnız bu sayfalarda (1,3,7)."""
    from . import portal_read as PR
    data=await file.read()
    try:
        only=[int(x) for x in pages.split(',') if x.strip()] if pages.strip() else None
    except ValueError:
        raise HTTPException(422,'pages: virgülle ayrılmış sayfa numaraları olmalı') from None
    try:
        return await PR.read(data,file.filename or 'belge',ocr=(ocr or 'auto').lower()!='off',only_pages=only)
    except PR.ReadError as e:
        raise HTTPException(422,str(e)) from None

# ------------------------------------------------------------------ belge incelemesi (editor.document_review)
@app.post('/v1/documents')
async def document_upload(file: UploadFile = File(...), title: str = Form(default=''), audience: str = Form(default=''),
                          age_from: int | None = Form(default=None), age_to: int | None = Form(default=None),
                          x_editor: str = Header(default='')):
    """Editörün yüklediği belge (doc, docx, pdf, odt, rtf, txt, md): metni çıkarılır, sayfalanır, kuyruğa girer
    (QUEUED); metin denetimleri `document-review` servisinde koşar. Yükleyen = X-Editor (köprü oturumdan verir).
    Okur kitlesi/yaş isteğe bağlı: verilirse yaşa ağır sözcük denetimi de koşar."""
    from . import document_review as DR
    who=(x_editor or '').strip()
    if not who:
        raise HTTPException(400,'Yükleyen (X-Editor) eksik.')
    data=await file.read()
    try:
        row=DR.create(data,file.filename or 'belge',title,who,audience or None,age_from,age_to)
    except DR.DocumentError as e:
        raise HTTPException(422,str(e)) from None
    return {**row,'id':str(row['id']),'created_at':row['created_at'].isoformat()}

@app.get('/v1/documents')
def document_list(uploaded_by: str = Query(default='')):
    """Yüklenen belgeler (yeniden eskiye); `uploaded_by` verilirse yalnız onunkiler. Metin döndürülmez."""
    with foundation.read_snapshot() as c:
        rows=c.execute("SELECT id, title, file_name, format, page_kind, words, status, error, uploaded_by, created_at, finished_at,"
                       " (SELECT count(*) FROM ed.document_finding f WHERE f.document_id=d.id AND f.severity<>'INFO'"
                       "  AND f.run_id IN (SELECT DISTINCT ON (check_name) id FROM ed.document_run r WHERE r.document_id=d.id"
                       "  ORDER BY check_name, started_at DESC)) AS serious"
                       " FROM ed.document_review d WHERE (%s='' OR uploaded_by=%s) ORDER BY created_at DESC",
                       (uploaded_by,uploaded_by)).fetchall()
    iso=lambda t: t.isoformat() if t else None
    return {'items':[{**r,'id':str(r['id']),'created_at':iso(r['created_at']),'finished_at':iso(r['finished_at'])} for r in rows]}

@app.get('/v1/documents/{doc_id}')
def document_report(doc_id: UUID):
    """Belgenin durumu, denetimleri ve bulguları (son okuma raporuyla aynı biçim; karar yok)."""
    from . import document_review as DR
    with foundation.read_snapshot() as c:
        r=DR.report(c,str(doc_id))
    if r is None:
        raise HTTPException(404,'document not found')
    return r

@app.get('/v1/documents/{doc_id}/word-map')
def document_word_map(doc_id: UUID):
    """Belgenin kelime haritası: word_variety koşusunun `stats`'ı (kitaptakiyle aynı biçim)."""
    with foundation.read_snapshot() as c:
        d=c.execute('SELECT id FROM ed.document_review WHERE id=%s',(str(doc_id),)).fetchone()
        if d is None:
            raise HTTPException(404,'document not found')
        run=c.execute("SELECT check_version, stats, finished_at FROM ed.document_run WHERE document_id=%s"
                      " AND check_name='word_variety' AND status='SUCCEEDED' ORDER BY started_at DESC LIMIT 1",
                      (str(doc_id),)).fetchone()
    return {'document_id':str(doc_id),'label':label_of('word_variety'),'version':run['check_version'] if run else None,
            'finished_at':run['finished_at'].isoformat() if run and run['finished_at'] else None,
            'stats':run['stats'] if run else None}

@app.get('/v1/documents/{doc_id}/export.docx')
def document_docx(doc_id: UUID, info: bool = Query(default=False)):
    """Belgenin metni, bulgular Word yorumu olarak (kitaptaki Word'e aktarımla aynı)."""
    from . import document_review as DR
    from .proofing import _export_docx
    with foundation.read_snapshot() as c:
        d=c.execute('SELECT title, pages FROM ed.document_review WHERE id=%s',(str(doc_id),)).fetchone()
        r=DR.report(c,str(doc_id)) if d else None
    if d is None:
        raise HTTPException(404,'document not found')
    findings=[f for f in r['findings'] if info or f['severity']!='INFO']
    body=_export_docx.build(d['title'],d['pages'],findings)
    safe=''.join(ch if ch.isascii() and (ch.isalnum() or ch in '-_') else '-' for ch in d['title']).strip('-') or 'belge'
    from urllib.parse import quote as _q
    return Response(body,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition':f"attachment; filename=\"inceleme-{safe}.docx\"; filename*=UTF-8''"
                             + _q(f"inceleme-{d['title']}.docx")})

@app.get('/v1/catalog/cover-requests')
def catalog_cover_requests():
    """CRM bağlayıcısı için editörün bütün kitapları (başlık, doğrulanmış ISBN ve yazar). Bağlayıcı CRM'e erişen
    test sunucusunda zamanlayıcıyla koşar ve kart servisine yalnız o sunucunun tüneliyle ulaşır (köprü ve VM
    nginx'i bu yolları geçirmez). Salt okuma."""
    from . import catalog
    return {'books':catalog.cover_requests()}

@app.post('/v1/catalog/crm-lookups')
def catalog_crm_lookup(body: dict = Body(...)):
    """Bağlayıcının bir kitap için CRM eşleşmesi: yayınevi kaydı (yazar, özet, okur kitlesi, yaş, tür) ve kapak
    sonucu. Kart servisinin ikinci yazma ucudur; yazdığı kitabın metni değil, yayınevinin kendi kaydıdır
    (editor.catalog.store_crm_lookup — MCP'deki /catalog/covers ile aynı işlev)."""
    from . import catalog
    if not isinstance(body,dict) or not body.get('book_id') or not body.get('outcome'):
        raise HTTPException(422,'book_id ve outcome gerekli')
    try:
        UUID(str(body['book_id']))
    except ValueError:
        raise HTTPException(422,'book_id geçersiz') from None
    return catalog.store_crm_lookup(body)

def _plain_for_word(r):
    """Word yorumunun metni: ekrandakiyle aynı sade metin, öneri ve ayrıntı (kayıtlı alanlardan)."""
    p=proof_text.render(r['check_name'],{'page':r['page_no'],'severity':r['severity'],'quote':r['quote'],
                        'suggestion':r['suggestion'],'message':r['message'],'details':r['details'] or {}})
    return {'message':p['text'],'suggestion':p['suggestion'],'detail':p['detail']}

@app.get('/v1/books/{book_id}/proofing/export.docx')
def book_proofing_docx(book_id: UUID, info: bool = Query(default=False)):
    """Son okuma bulguları kitabın metnine Word yorumu olarak işlenmiş .docx (redaksiyon Word'de yapılır).
    Son okunan neslin her denetiminin en yeni koşusu; uyarı ve hata düzeyi (`info=true` ile bilgi düzeyi de —
    denetimlerin özet satırları ve öneri olarak gelenler); editörün «yanlış alarm» dediği bulgu hariç, geri
    kalan hiçbir bulgu düşmez (yeri bulunamayan sayfa başlığına bağlanır). Önceki okumadan taşınan «yanlış alarm»
    da hariç (ekranda gizlenen bulgu Word'e de gitmez). Salt okuma."""
    from . import source
    from .proofing import _export_docx
    with foundation.read_snapshot() as c:
        gen=_proofed_generation(c,str(book_id))
        if gen is None:
            raise HTTPException(404,'book not found')
        gid=str(gen['id'])
        title=(c.execute('SELECT b.title FROM ed.book b WHERE b.id=%s',(str(book_id),)).fetchone() or {}).get('title') or 'kitap'
        try:
            runs=c.execute('SELECT DISTINCT ON (check_name) id FROM ed.proof_run WHERE generation_id=%s'
                           ' ORDER BY check_name, started_at DESC',(gid,)).fetchall()
            rows=c.execute('SELECT id, check_name, page_no, severity, message, quote, suggestion, details, bbox,'
                           ' '+_IDENT_SQL+' AS ident FROM ed.proof_finding'
                           ' WHERE run_id = ANY(%s) ORDER BY page_no NULLS FIRST, severity DESC, created_at',
                           ([r['id'] for r in runs],)).fetchall() if runs else []
        except psycopg.errors.UndefinedTable:
            raise HTTPException(503,'proofing tables missing (db migration 023_proofing not applied)') from None
        decisions,_=_decisions(c,gid,[r['id'] for r in runs]) if runs else ({},{})
        # önceki okumada «yanlış alarm» denmiş (taşınan) bulgu da aktarılmaz
        decisions=_with_carried(c,str(book_id),gid,[r['id'] for r in runs],rows,decisions)
    findings=[{'page':r['page_no'],'check':r['check_name'],'label':label_of(r['check_name']),'severity':r['severity'],
               'quote':r['quote'],'details':r['details'] or {},
               **_plain_for_word(r)} for r in rows
              if (decisions.get(str(r['id'])) or {}).get('verdict')!='REJECT' and (info or r['severity']!='INFO')]
    body=_export_docx.build(title,source.read(gid),findings)
    safe=''.join(ch if ch.isascii() and (ch.isalnum() or ch in '-_') else '-' for ch in title).strip('-') or 'kitap'
    from urllib.parse import quote as _q
    return Response(body,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition':f"attachment; filename=\"son-okuma-{safe}.docx\"; filename*=UTF-8''"
                             + _q(f'son-okuma-{title}.docx')})

@app.get('/v1/books/{book_id}/proofing/word-map')
def book_word_map(book_id: UUID):
    """Kelime haritası: `word_variety` denetiminin son okunan nesildeki EN YENİ başarılı koşusunun
    `stats`'ı — her kök, biçimleri, sayfaları, anlamları (deyimler dahil) ve çeşitlilik ölçüleri
    (docs/son-okuma/word_variety.md). Koşu yoksa `stats` null (404 değil). Salt okuma."""
    with foundation.read_snapshot() as c:
        gen=_proofed_generation(c,str(book_id))
        if gen is None:
            raise HTTPException(404,'book not found')
        gid=str(gen['id'])
        try:
            run=c.execute(
                "SELECT check_version, stats, finished_at FROM ed.proof_run WHERE generation_id=%s"
                " AND check_name='word_variety' AND status='SUCCEEDED' ORDER BY started_at DESC LIMIT 1",
                (gid,)).fetchone()
        except psycopg.errors.UndefinedTable:
            raise HTTPException(503,'proofing tables missing (db migration 023_proofing not applied)') from None
    return {'book_id':str(book_id),'generation_id':gid,'label':label_of('word_variety'),
            'version':run['check_version'] if run else None,
            'finished_at':run['finished_at'].isoformat() if run and run['finished_at'] else None,
            'stats':run['stats'] if run else None}

@app.post('/v1/books/{book_id}/proofing/findings/{finding_id}/decision')
def book_proofing_decision(book_id: UUID, finding_id: UUID, body: dict = Body(...)):
    """Editörün bulguya kararı: «Doğru» (ACCEPT), «Yanlış alarm» (REJECT + gerekçe [+ not]) ya da «Geri al»
    (CLEAR: bulgunun kararı yok, önceki okumadan taşınan karar bu bulguya uygulanmaz).
    Servisin TEK yazma ucudur ve yazdığı şey kitap verisi değil, editörün (insanın) kaydıdır (docs/PORTAL-CARDS.md).
    Bulgu o kitabın SON nesline ait olmalı (eski nesle karar 404). `carriedFrom`: editör ekranda önceki okumadan
    gelen kararı görürken yazdıysa o kararın kimliği — aynı kitabın aynı denetiminin başka bir bulgusuna ait olmalı
    (422). Salt ekleme: yeni karar eskisini geçersiz kılar; geçerli karar döner (CLEAR'da null). Kitabı düzeltmez,
    denetim koşturmaz."""
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
            if v['carried_from'] or v['verdict']=='CLEAR':
                if not _has_carry(c):
                    raise HTTPException(503,'proof_decision.carried_from missing (db migration 028_proof_decision_carry not applied)')
                if v['carried_from'] and c.execute(
                        'SELECT 1 FROM ed.proof_decision d JOIN ed.proof_finding f ON f.id=d.finding_id'
                        ' JOIN ed.generation g ON g.id=f.generation_id JOIN ed.book_version bv ON bv.id=g.book_version_id'
                        ' WHERE d.id=%s AND bv.book_id=%s AND d.check_name=%s AND d.finding_id<>%s',
                        (v['carried_from'],str(book_id),f['check_name'],str(finding_id))).fetchone() is None:
                    raise HTTPException(422,'Taşınan karar bu kitabın bu denetimine ait değil.')
                row=c.execute(
                    'INSERT INTO ed.proof_decision(finding_id, generation_id, check_name, check_version, verdict, reason_code,'
                    ' note, decided_by, carried_from) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)'
                    ' RETURNING verdict, reason_code, note, decided_by, created_at',
                    (str(finding_id),gid,f['check_name'],f['check_version'],v['verdict'],v['reason_code'],v['note'],
                     v['decided_by'],v['carried_from'])).fetchone()
            else:
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
