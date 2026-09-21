"""Read-only source discovery; run on the connected server only."""
import json
from semantic_layer.profiler.connectors import connector_from_file

c = connector_from_file('/data/nanobaseai/bi/secrets/logo-mssql-connection.json')
queries = {
    'scope': "SELECT YEAR(DATE_) AS year,COUNT(*) AS rows, MIN(DATE_) AS first_date,MAX(DATE_) AS last_date FROM dbo.LG_411_01_EMFLINE GROUP BY YEAR(DATE_)",
    'types': "SELECT TRCODE,CANCELLED,COUNT(*) AS rows FROM dbo.LG_411_01_EMFICHE WHERE DATE_ >= '20260101' AND DATE_ < '20270101' GROUP BY TRCODE,CANCELLED",
    'integrity': "SELECT COUNT(*) AS rows, SUM(CASE WHEN A.LOGICALREF IS NULL THEN 1 ELSE 0 END) AS missing_account, SUM(CASE WHEN F.LOGICALREF IS NULL THEN 1 ELSE 0 END) AS missing_slip FROM dbo.LG_411_01_EMFLINE L LEFT JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF LEFT JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=L.ACCFICHEREF WHERE L.DATE_ >= '20260101' AND L.DATE_ < '20270101'",
}
for name, sql in queries.items():
    cols, rows, truncated = c.execute(sql, 100)
    print(json.dumps({'name': name, 'records': rows, 'truncated': truncated}, default=str, ensure_ascii=False))
