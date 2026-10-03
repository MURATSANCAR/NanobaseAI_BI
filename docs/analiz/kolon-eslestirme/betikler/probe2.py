import sys, io, re, zipfile, collections
sys.path.insert(0,'/data/nanobaseai/bi/frontend/backend')
from pathlib import Path
from scripts.export_crm_metadata import connect
cn = connect(Path('/data/nanobaseai/bi/secrets/logo-mssql-connection.json'), 'LOGO_DB'); cur = cn.cursor()
def xml(b):
    z = zipfile.ZipFile(io.BytesIO(bytes(b))); return z.read(z.namelist()[0]).decode('utf-8','replace')
def tags(x):
    g = lambda t: (re.search(rf'<cbc:{t}[^>]*>([^<]*)<', x) or [None,None])[1]
    st = re.search(r'(ELEKTRONIK|KAGIT)', x)
    return g('ProfileID'), g('InvoiceTypeCode'), st.group(1) if st else None
# does FICHEREF point to INVOICE?
cur.execute("""SELECT TOP 1 o.FICHEREF, i.FICHENO FROM LG_411_01_FICHEOBJECT o JOIN LG_411_01_INVOICE i ON i.LOGICALREF=o.FICHEREF ORDER BY o.LOGICALREF DESC"""); print(cur.fetchall())
res = collections.defaultdict(collections.Counter)
for col, tbl in [('PROFILEID','EINVOICEDET'),('EINVOICETYP','EINVOICEDET'),('SENDMOD','EARCHIVEDET'),('INTPAYMENTTYPE','EARCHIVEDET'),('EARCHIVESTATUS','EARCHIVEDET')]:
    cur.execute(f"SELECT DISTINCT {col} FROM LG_411_01_{tbl} WITH (NOLOCK)"); codes = [r[0] for r in cur.fetchall()]
    for code in codes:
        cur.execute(f"""SELECT TOP 15 o.LDATA, i.TRCODE FROM LG_411_01_{tbl} d WITH (NOLOCK)
          JOIN LG_411_01_FICHEOBJECT o WITH (NOLOCK) ON o.FICHEREF=d.INVOICEREF
          JOIN LG_411_01_INVOICE i WITH (NOLOCK) ON i.LOGICALREF=d.INVOICEREF
          WHERE d.{col}=? ORDER BY d.LOGICALREF DESC""", code)
        rows = cur.fetchall()
        for b, tr in rows:
            try: p,t,s = tags(xml(b))
            except Exception as e: p=t=s='ERR'
            res[f'{tbl}.{col}={code}'][f'profile={p} type={t} send={s} trcode={tr}'] += 1
        if not rows: res[f'{tbl}.{col}={code}']['xml yok'] += 1
for k,v in res.items(): print(k, dict(v.most_common(4)))
cur.execute("SELECT DOCUMENTTYPE, MODULENR, COUNT(*) FROM LG_411_01_EBOOKDETAILDOC WITH (NOLOCK) GROUP BY DOCUMENTTYPE, MODULENR ORDER BY 1,3 DESC"); print(cur.fetchall())
