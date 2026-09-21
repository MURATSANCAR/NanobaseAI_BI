"""Read-only Logo e-ledger evidence, preserving raw flags and code meanings."""
from pathlib import Path
import hashlib
import logging

REVISION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def doc_where(year):
    return f"F.CANCELLED=0 AND F.DATE_>='{year}0101' AND F.DATE_<'{year+1}0101'"


DOC_JOIN = 'FROM dbo.LG_411_01_EBOOKDETAILDOC D JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=D.EMFICHEREF'


def read_evidence(query, year):
    errors = []
    def read(sql, period):
        try:
            return query(sql,period)
        except Exception:
            logging.getLogger(__name__).exception('Supplemental audit dataset unavailable')
            errors.append(len(errors)+1)
            return {'records':[], 'failed':True}
    # Group by the actual flags; no guessed numeric document-type dictionary.
    doc = read(f"""SELECT D.DOCUMENTTYPE AS documentType,D.PAYTYPE AS paymentType,
        D.UNDOCUMENTED AS undocumented,D.NOPAYMENT AS noPayment,COUNT(*) AS rows,
        SUM(CASE WHEN D.UNDOCUMENTED=0 AND NULLIF(LTRIM(RTRIM(D.DOCUMENTNR)),'') IS NULL THEN 1 ELSE 0 END) AS missingNumber,
        SUM(CASE WHEN D.UNDOCUMENTED=0 AND (D.DOCUMENTDATE IS NULL OR D.DOCUMENTDATE<'19010101') THEN 1 ELSE 0 END) AS missingDate,
        SUM(CASE WHEN D.NOPAYMENT=0 AND NULLIF(LTRIM(RTRIM(D.PAYTYPE)),'') IS NULL THEN 1 ELSE 0 END) AS missingPayment
        {DOC_JOIN} WHERE {doc_where(year)}
        GROUP BY D.DOCUMENTTYPE,D.PAYTYPE,D.UNDOCUMENTED,D.NOPAYMENT
        ORDER BY D.DOCUMENTTYPE,D.PAYTYPE,D.UNDOCUMENTED,D.NOPAYMENT""",year)
    mixed = read(f"""SELECT COUNT(*) AS vouchers,
        SUM(CASE WHEN V.docTypes>1 THEN 1 ELSE 0 END) AS multipleDocumentTypes,
        SUM(CASE WHEN V.paymentTypes>1 THEN 1 ELSE 0 END) AS multiplePaymentTypes
        FROM (SELECT D.EMFICHEREF,
        COUNT(DISTINCT CASE WHEN D.UNDOCUMENTED=0 THEN D.DOCUMENTTYPE ELSE NULL END) AS docTypes,
        COUNT(DISTINCT CASE WHEN D.NOPAYMENT=0 THEN NULLIF(LTRIM(RTRIM(D.PAYTYPE)),'') ELSE NULL END) AS paymentTypes
        {DOC_JOIN} WHERE {doc_where(year)} GROUP BY D.EMFICHEREF) V""",year)
    # Deduplicate each document/main-account relation before aggregation. Header
    # documents apply to the voucher; line documents only to their own line.
    account_doc = read(f"""SELECT X.code,X.documentType,X.paymentType,COUNT(*) AS rows FROM (
        SELECT DISTINCT D.LOGICALREF,LEFT(A.CODE,3) AS code,D.DOCUMENTTYPE AS documentType,D.PAYTYPE AS paymentType
        {DOC_JOIN} JOIN dbo.LG_411_01_EMFLINE L ON L.ACCFICHEREF=F.LOGICALREF
        AND (D.EMFLINEREF IS NULL OR D.EMFLINEREF=0 OR D.EMFLINEREF=L.LOGICALREF)
        JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF
        WHERE {doc_where(year)} AND L.CANCELLED=0
        AND L.DATE_>='{year}0101' AND L.DATE_<'{year+1}0101'
        AND LEFT(A.CODE,3) IN ('100','101','102','121','191','391')) X
        GROUP BY X.code,X.documentType,X.paymentType ORDER BY X.code,X.documentType,X.paymentType""",year)
    assets = read(f"""SELECT CAST(Y.TABLETY AS int) AS bookType,CAST(Y.DTYPE AS int) AS method,Y.CALCMON AS month,
        COUNT(*) AS rows,COUNT(DISTINCT Y.FREGREF) AS assetCount,
        SUM(CASE WHEN R.LOGICALREF IS NULL THEN 1 ELSE 0 END) AS missingAssetCard,
        SUM(CASE WHEN Y.LOCFIGS2_PERDDEPR IS NULL THEN 1 ELSE 0 END) AS missingAmount,
        SUM(CAST(Y.LOCFIGS2_PERDDEPR AS decimal(28,4))) AS periodDepreciation
        FROM dbo.LG_411_FAYEAR Y LEFT JOIN dbo.LG_411_FAREGIST R ON R.LOGICALREF=Y.FREGREF
        WHERE Y.YEAR_={year} GROUP BY Y.TABLETY,Y.DTYPE,Y.CALCMON
        ORDER BY Y.TABLETY,Y.DTYPE,Y.CALCMON""",year)
    return {'revision':REVISION,'documentProfiles':doc['records'],'documentVoucherProfile':mixed['records'][0] if mixed['records'] else {},
        'accountDocumentProfiles':account_doc['records'],'assetProfiles':assets['records'],
        'truncated':None if errors else False,'status':'unverified' if errors else 'observed',
        'unavailableDatasets':[name for name,r in [('documents',doc),('voucherDocuments',mixed),('accountDocuments',account_doc),('assets',assets)] if r.get('failed')],
        'limitations':['Belge türü sayısal kodları Logo sürüm sözlüğüyle eşlenmeden fatura/çek/senet uygunluk kararı verilmez.',
                       'Belge yok ve ödeme yok alanları kaynak beyanıdır; belgesizlik için hukuki istisna kanıtı değildir.',
                       'Sabit kıymet grupları ayrı hesaplama tabloları olabilir; gruplar veya aylık birikimli tutarlar toplanmaz.',
                       'Varlık türü, yöntem, kullanıma başlama, istisna ve muhasebe hesabı eşlemesi doğrulanmadan amortisman uygunluğu verilmez.'],
        'sql':[r.get('physicalSql') for r in [doc,mixed,account_doc,assets]],
        'dbMs':sum(r.get('dbMs',0) for r in [doc,mixed,account_doc,assets])}


def document_sql(year, page, main_account=None):
    filtered = ''
    if main_account is not None:
        filtered=f""" AND EXISTS (SELECT 1 FROM dbo.LG_411_01_EMFLINE L
        JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF
        WHERE L.ACCFICHEREF=F.LOGICALREF AND L.CANCELLED=0 AND LEFT(A.CODE,3)='{main_account}'
        AND L.DATE_>='{year}0101' AND L.DATE_<'{year+1}0101'
        AND (D.EMFLINEREF IS NULL OR D.EMFLINEREF=0 OR D.EMFLINEREF=L.LOGICALREF))"""
    return f"""SELECT D.LOGICALREF AS documentRef,D.EMFICHEREF AS slipRef,D.EMFLINEREF AS lineRef,
        F.FICHENO AS slipNo,F.DATE_ AS date,D.DOCUMENTTYPE AS documentType,D.DOCUMENTNR AS documentNo,
        D.DOCUMENTDATE AS documentDate,D.PAYTYPE AS paymentType,D.UNDOCUMENTED AS undocumented,
        D.NOPAYMENT AS noPayment,D.EXPLAIN AS description,COUNT(*) OVER() AS totalRows
        {DOC_JOIN} WHERE {doc_where(year)} {filtered}
        ORDER BY F.DATE_,D.LOGICALREF OFFSET {page*50} ROWS FETCH NEXT 50 ROWS ONLY"""
