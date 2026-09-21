"""Read-only discovery of actual accounting/e-ledger fields and coverage. Server only."""
import json
import sys
from pathlib import Path
from semantic_layer.profiler.connectors import connector_from_file

db = connector_from_file('/data/nanobaseai/bi/secrets/logo-mssql-connection.json')
if '--capabilities' in sys.argv:
    sql = """SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_NAME LIKE 'LG[_]411%'
      AND ((TABLE_NAME LIKE '%EMF%' AND (COLUMN_NAME LIKE '%DOC%' OR COLUMN_NAME LIKE '%PAY%'))
           OR TABLE_NAME LIKE '%FAYEAR%' OR TABLE_NAME LIKE '%EBOOK%'
           OR COLUMN_NAME IN ('PAYMENTTYPE','DOCUMENTTYPE'))
      ORDER BY TABLE_NAME,ORDINAL_POSITION"""
    _, rows, cut = db.execute(sql, 5000)
    result = {'columns':rows,'truncated':cut,'sql':sql}
    Path('/tmp/financial-audit-capabilities.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False),flush=True)
    raise SystemExit(1 if cut else 0)
out = {}
for table in ['LG_411_01_EMFLINE', 'LG_411_01_EMFICHE', 'LG_411_EMUHACC', 'LG_411_01_FAYEAR', 'LG_411_FAREGIST', 'LG_211_01_EMFLINE']:
    try:
        cols = db.columns('dbo', table)
        out[table] = cols
        print(table, ','.join(str(c.get('name') or c.get('column_name')) for c in cols), flush=True)
    except Exception as exc:
        out[table] = {'error': type(exc).__name__}
queries = {
  'ledger_years': "SELECT YEAR(DATE_) AS year,COUNT(*) AS rows,MIN(DATE_) AS first_date,MAX(DATE_) AS last_date FROM dbo.LG_211_01_EMFLINE WHERE CANCELLED=0 GROUP BY YEAR(DATE_)",
  'source_months': "SELECT MONTH(DATE_) AS month,COUNT(*) AS rows FROM dbo.LG_411_01_EMFLINE WHERE DATE_ >= '20260101' AND DATE_ < '20270101' AND CANCELLED=0 GROUP BY MONTH(DATE_)",
  'account_class_flows': "SELECT LEFT(A.CODE,1) AS class,F.TRCODE, SUM(CAST(L.DEBIT AS decimal(28,4))) AS debit,SUM(CAST(L.CREDIT AS decimal(28,4))) AS credit, COUNT(*) AS rows FROM dbo.LG_411_01_EMFLINE L JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=L.ACCFICHEREF WHERE L.CANCELLED=0 AND F.CANCELLED=0 AND L.DATE_ >= '20260101' AND L.DATE_ < '20270101' GROUP BY LEFT(A.CODE,1),F.TRCODE ORDER BY class,F.TRCODE",
}
for name, sql in queries.items():
    cols, rows, truncated = db.execute(sql, 1000)
    out[name] = {'records':rows,'truncated':truncated,'sql':sql}
    print(json.dumps({'name':name,'records':rows,'truncated':truncated},default=str,ensure_ascii=False),flush=True)
Path('/tmp/financial-audit-discovery.json').write_text(json.dumps(out,default=str,ensure_ascii=False,indent=2))
