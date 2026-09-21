"""Server-only, read-only inventory of actual Logo audit sources."""
import json
import sys
from pathlib import Path
from semantic_layer.profiler.connectors import connector_from_file

db = connector_from_file('/data/nanobaseai/bi/secrets/logo-mssql-connection.json')
path = Path('/tmp/financial-audit-deep-discovery.json')
out = json.loads(path.read_text()) if path.exists() else {}
queries = {
 'tables': """SELECT T.name AS tableName,SUM(P.rows) AS metadataRows
 FROM sys.tables T JOIN sys.partitions P ON P.object_id=T.object_id AND P.index_id IN (0,1)
 WHERE T.name LIKE 'LG[_]411%' OR T.name LIKE 'L[_]%BANK%' OR T.name LIKE '%RECON%'
 OR T.name LIKE '%DECLAR%' OR T.name LIKE '%MUTAB%' OR T.name LIKE '%BEYAN%'
 GROUP BY T.name ORDER BY T.name""",
 'columns': """SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME IN ('LG_411_01_INVOICE','LG_411_01_STLINE','LG_411_01_BNFLINE',
 'LG_411_01_EMFLINE','LG_411_01_CLFLINE','LG_411_01_CSTRANS','LG_411_01_CSCARD',
 'LG_411_01_STFICHE','LG_411_BNCARD','LG_411_BANKACC','LG_411_ITEMS')
 ORDER BY TABLE_NAME,ORDINAL_POSITION""",
 'invoices': """SELECT TRCODE,ACCOUNTED,COUNT(*) AS rows,
 SUM(CASE WHEN ACCFICHEREF>0 THEN 1 ELSE 0 END) AS linked,
 SUM(CASE WHEN GIBACCFICHEREF>0 THEN 1 ELSE 0 END) AS gibLinked
 FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'
 GROUP BY TRCODE,ACCOUNTED ORDER BY TRCODE,ACCOUNTED""",
 'invoiceLedgerLinks': """SELECT I.TRCODE,COUNT(*) AS rows,
 SUM(CASE WHEN F.LOGICALREF IS NOT NULL THEN 1 ELSE 0 END) AS present,
 SUM(CASE WHEN F.CANCELLED<>0 THEN 1 ELSE 0 END) AS cancelled,
 SUM(CASE WHEN F.DATE_<>I.DATE_ THEN 1 ELSE 0 END) AS differentDate
 FROM dbo.LG_411_01_INVOICE I LEFT JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=I.ACCFICHEREF
 WHERE I.CANCELLED=0 AND I.DATE_>='20260101' AND I.DATE_<'20270101'
 GROUP BY I.TRCODE ORDER BY I.TRCODE""",
 'additionalColumns': """SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME IN ('LG_411_TAXDECLHDR','LG_411_TAXDECLLINE','LG_411_TAXDECLLINEACC',
 'LG_411_BNCREDITCARD','LG_411_BNCREPAYTR','LG_411_01_INVEXIMINFO','LG_411_01_INVEXIMLINES',
 'LG_411_01_PERDOC','LG_411_FIRMDOC','LG_411_RELATEDDOCS','LG_411_01_EINVOICEDET',
 'LG_411_01_STINVENS','LG_411_EBOOKINFO') ORDER BY TABLE_NAME,ORDINAL_POSITION""",
 'bankProfile': """SELECT SIGN,ACCOUNTED,COUNT(*) AS rows,
 SUM(CASE WHEN ACCFICHEREF>0 THEN 1 ELSE 0 END) AS slipLinked,
 SUM(CASE WHEN EMFLINEREF>0 THEN 1 ELSE 0 END) AS lineLinked,
 SUM(CASE WHEN BNACCOUNTREF>0 THEN 1 ELSE 0 END) AS accountLinked,
 MIN(DATE_) AS firstDate,MAX(DATE_) AS lastDate
 FROM dbo.LG_411_01_BNFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'
 GROUP BY SIGN,ACCOUNTED""",
 'stockSlips': """SELECT TRCODE,COUNT(*) AS rows,MIN(DATE_) AS firstDate,MAX(DATE_) AS lastDate
 FROM dbo.LG_411_01_STFICHE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'
 GROUP BY TRCODE ORDER BY TRCODE""",
 'taxHeaders': """SELECT YEAR_,MONTH_,TYP,COUNT(*) AS rows,MIN(BEGDT) AS firstDate,MAX(ENDDT) AS lastDate
 FROM dbo.LG_411_TAXDECLHDR GROUP BY YEAR_,MONTH_,TYP ORDER BY YEAR_,MONTH_,TYP""",
 'taxAccountLinks': """SELECT H.YEAR_,COUNT(*) AS rows,COUNT(DISTINCT X.ACCOUNTREF) AS accounts
 FROM dbo.LG_411_TAXDECLLINEACC X JOIN dbo.LG_411_TAXDECLHDR H ON H.LOGICALREF=X.TAXDECLHDREF GROUP BY H.YEAR_""",
 'loanSchedule': """SELECT YEAR(DUEDATE) AS dueYear,TRANSTYPE,COUNT(*) AS rows,
 SUM(CASE WHEN BNFCHREF>0 THEN 1 ELSE 0 END) AS bankLinked
 FROM dbo.LG_411_BNCREPAYTR GROUP BY YEAR(DUEDATE),TRANSTYPE ORDER BY dueYear,TRANSTYPE""",
 'ebookPeriods': """SELECT PERYEAR,PERMONTH,CAST(TYP AS int) AS type,CAST(BOOKSTATUS AS int) AS status,
 COUNT(*) AS rows,MIN(REPORTSTARTDATE) AS firstDate,MAX(REPORTENDDATE) AS lastDate
 FROM dbo.LG_411_EBOOKINFO GROUP BY PERYEAR,PERMONTH,TYP,BOOKSTATUS ORDER BY PERYEAR,PERMONTH,TYP""",
 'attachments': """SELECT INFOTYP,DOCTYP,COUNT(*) AS rows,
 SUM(CASE WHEN DATALENGTH(LDATA)>0 THEN 1 ELSE 0 END) AS withPayload
 FROM dbo.LG_411_01_PERDOC GROUP BY INFOTYP,DOCTYP ORDER BY INFOTYP,DOCTYP""",
 'invoiceAccounts': """SELECT TRCODE,COUNT(*) AS rows,
 SUM(CASE WHEN ACCOUNTREF>0 THEN 1 ELSE 0 END) AS accountMapped,
 SUM(CASE WHEN TOTALADDTAX<>0 THEN 1 ELSE 0 END) AS withAdditionalTax
 FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' GROUP BY TRCODE ORDER BY TRCODE""",
 'attachmentSignatures': """SELECT TOP 6 LREF,INFOTYP,INFOREF,DOCTYP,DATALENGTH(LDATA) AS byteLength,
 CONVERT(varchar(128),SUBSTRING(LDATA,1,64),2) AS prefixHex
 FROM dbo.LG_411_01_PERDOC WHERE DATALENGTH(LDATA)>0 ORDER BY LREF""",
 'loanParentLinks': """SELECT CAST(P.TRANSTYPE AS int) AS transactionType,
 COUNT(*) AS rows,SUM(CASE WHEN P.PARENTREF>0 THEN 1 ELSE 0 END) AS withParent,
 SUM(CASE WHEN Q.LOGICALREF IS NOT NULL THEN 1 ELSE 0 END) AS parentFound,
 SUM(CASE WHEN Q.CREDITREF<>P.CREDITREF THEN 1 ELSE 0 END) AS parentOtherCredit
 FROM dbo.LG_411_BNCREPAYTR P LEFT JOIN dbo.LG_411_BNCREPAYTR Q ON Q.LOGICALREF=P.PARENTREF
 WHERE P.DUEDATE>='20260101' AND P.DUEDATE<'20270101' GROUP BY P.TRANSTYPE""",
}
for key,sql in queries.items():
    if len(sys.argv)>1 and key not in sys.argv[1:]:
        continue
    try:
        _,rows,cut=db.execute(sql,10000)
        out[key]={'records':rows,'truncated':cut,'sql':sql}
        if key not in {'columns','tables','additionalColumns'}: print(json.dumps({key:rows,'truncated':cut},default=str),flush=True)
        else: print(key,len(rows),'truncated',cut,flush=True)
    except Exception as exc:
        out[key]={'error':str(exc)}
        print(key,type(exc).__name__,str(exc),flush=True)
artifact=Path('/tmp/financial-audit-deep-discovery.json')
artifact.touch(mode=0o600);artifact.chmod(0o600)
artifact.write_text(json.dumps(out,ensure_ascii=False,default=str,indent=2))
for table in out.get('tables',{}).get('records',[]):
    if any(k in table['tableName'] for k in ['BN','BANK','RECON','DECLAR','BEYAN','MUTAB','STFICHE','COUNT','FAYEAR','CSCARD','CSTRANS','CLFLINE','EBOOK','INVOICE']):
        print(json.dumps(table),flush=True)
