"""Read-only original-PDF regression on tt-gpu; not a local/fixture test.

The explicit reference strings were transcribed from the original page images.
No source ledger or generation is rewritten by this check.
"""
import hashlib,json,os,sys
import pymupdf
from editor import db,document
gid=sys.argv[1]
row=db.one('SELECT v.file_path,v.sha256,v.page_count FROM generation g '
           'JOIN book_version v ON v.id=g.book_version_id WHERE g.id=%s',gid)
checks=[]
def check(name,ok):
    checks.append({'name':name,'passed':bool(ok)})
    if len(checks)%10==0:
        print(json.dumps({'completed':len(checks),'passed':sum(c['passed'] for c in checks),
                         'failed':sum(not c['passed'] for c in checks)}),file=sys.stderr,flush=True)
with open(row['file_path'],'rb') as f:check('Original PDF hash',hashlib.file_digest(f,'sha256').hexdigest()==row['sha256'])
doc=pymupdf.open(row['file_path']);check('physical pages',len(doc)==row['page_count'])
readings={}
for n,p in enumerate(doc,1):
    lines=document._page_lines(p)
    check(f'p{n}:overprinted duplicate lines absent',len({(l['text'],l['x0'],l['y0'],l['x1'],l['y1']) for l in lines})==len(lines))
    readings[n]='\n\n'.join(document.paragraphs_from_layout(p))
for expected in ('Yayın Yönetmeni Savaş Özdemir','Proje Editörü Yalçın Yaman',
                 'Editör Gülfem Özer','Kapak Tasarımı Esra Burak','İç Tasarım Yusuf Buğra Burak'):
    check('p2 visual reference: '+expected,expected in readings[2])
for expected in ('Samsun’da doğdu.', '15 Nisan 1995’te İzmir’de doğdu.',
                 '2022 yılından bu yana çizerlik dünyasında'):
    check('p3 visual reference occurs once: '+expected,readings[3].count(expected)==1)
check('p3 original visible word preserved','Resim, hayatında hep vardı.' in readings[3])
for n in (4,10):check(f'p{n}: no invented text',not readings[n].strip())
print(json.dumps({'generation_id':gid,'code_version':os.environ.get('EDITOR_CODE_VERSION'),
    'pdf_sha256':row['sha256'],'passed':sum(c['passed'] for c in checks),
    'failed':sum(not c['passed'] for c in checks),'checks':checks,'readings':readings},ensure_ascii=False))
raise SystemExit(any(not c['passed'] for c in checks))
