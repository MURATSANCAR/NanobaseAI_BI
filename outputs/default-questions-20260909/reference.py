import json,hashlib
from pathlib import Path
from decimal import Decimal
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
root=Path('/data/nanobaseai/bi/backups/default-questions-20260909')
answers=json.loads((root/'defaults.json').read_text());s=SemanticSettings.from_env();c=connector_from_file(s.connection_file)
refs=[
("kanal","net_ciro", "SELECT c.SPECODE2 label, SUM(CASE WHEN i.TRCODE IN (2,3) THEN -i.NETTOTAL ELSE i.NETTOTAL END) value FROM dbo.LG_411_01_INVOICE i INNER JOIN dbo.LG_411_CLCARD c ON c.LOGICALREF=i.CLIENTREF WHERE i.DATE_ >= '20260101' AND i.DATE_ < '20270101' AND i.CANCELLED=0 AND i.TRCODE IN (2,3,7,8,9) GROUP BY c.SPECODE2"),
("muster","iade_tutar", "SELECT TOP 10 c.DEFINITION_ label, SUM(i.NETTOTAL) value FROM dbo.LG_411_01_INVOICE i LEFT JOIN dbo.LG_411_CLCARD c ON c.LOGICALREF=i.CLIENTREF WHERE i.DATE_ >= '20260101' AND i.DATE_ < '20270101' AND i.CANCELLED=0 AND i.TRCODE IN (2,3) GROUP BY c.DEFINITION_ ORDER BY value DESC"),
("ay","iskonto_ora", "WITH raw AS (SELECT DATE_,LINETYPE,TOTAL FROM dbo.LG_211_01_STLINE WHERE DATE_ >= '20260101' AND DATE_ < '20270101' AND CANCELLED=0 AND TRCODE IN (7,8) UNION ALL SELECT DATE_,LINETYPE,TOTAL FROM dbo.LG_411_01_STLINE WHERE DATE_ >= '20260101' AND DATE_ < '20270101' AND CANCELLED=0 AND TRCODE IN (7,8)), totals AS (SELECT MONTH(DATE_) m, LINETYPE, SUM(TOTAL) amount FROM raw GROUP BY MONTH(DATE_),LINETYPE) SELECT DATEFROMPARTS(2026,m,1) label, SUM(CASE WHEN LINETYPE=2 THEN amount ELSE 0 END)/NULLIF(SUM(CASE WHEN LINETYPE=0 THEN amount ELSE 0 END),0) value FROM totals GROUP BY m"),
("kitap","adet", "WITH sales AS (SELECT p.NAME title,SUM(l.AMOUNT) quantity FROM dbo.LG_211_01_STLINE l INNER JOIN dbo.LG_211_ITEMS p ON p.LOGICALREF=l.STOCKREF WHERE l.DATE_ >= '20260101' AND l.DATE_ < '20270101' AND l.CANCELLED=0 AND l.LINETYPE=0 AND l.TRCODE IN (7,8) GROUP BY p.NAME UNION ALL SELECT p.NAME,SUM(l.AMOUNT) FROM dbo.LG_411_01_STLINE l INNER JOIN dbo.LG_411_ITEMS p ON p.LOGICALREF=l.STOCKREF WHERE l.DATE_ >= '20260101' AND l.DATE_ < '20270101' AND l.CANCELLED=0 AND l.LINETYPE=0 AND l.TRCODE IN (7,8) GROUP BY p.NAME) SELECT TOP 10 title label,SUM(quantity) value FROM sales GROUP BY title ORDER BY value DESC")]
def norm(label,value):return (str(label) if label is not None else None, str(Decimal(str(value)).quantize(Decimal('0.00001'))) if value is not None else None)
reports=[]
for case,(dimension,metric,sql) in zip(answers,refs):
 cols,rows,truncated=c.execute(sql,100000)
 full=case['answer']['fullResult'];actual=full['records']
 expected=sorted([norm(row['label'],row['value']) for row in rows],key=str)
 observed=sorted([norm(row[dimension],row[metric]) for row in actual],key=str)
 passed=expected==observed and not truncated and not full['truncated'] and len(actual)==full['totalRows'] and {x['name'] for x in full['columns']}=={dimension,metric}
 reports.append({'question':case['question'],'passed':passed,'actualRows':len(actual),'referenceRows':len(rows),'referenceSQL':sql,'expected':expected,'observed':observed,'resultId':case['answer']['resultId']})
 print(json.dumps({k:v for k,v in reports[-1].items() if k not in ['referenceSQL','expected','observed']},ensure_ascii=False),flush=True)
(root/'reference-results.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2));c.close()
