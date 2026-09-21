"""Actual subledger discovery and bounded, traceable cross-ledger checks.

Source presence is not external confirmation. Every dataset carries its missing
evidence and failed reads remain distinguishable from an empty result.
"""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import hashlib
import logging

REVISION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
D = lambda x: Decimal(str(x or 0))


def bounds(year, as_of):
    end = date.fromisoformat(str(as_of)[:10]) + timedelta(days=1)
    return f"'{year}0101'", "'"+end.strftime('%Y%m%d')+"'"


def invoice_base(year, as_of):
    start, end = bounds(year, as_of)
    return f"""SELECT I.LOGICALREF AS sourceRef,I.FICHENO AS documentNo,I.DATE_ AS date,
      I.CLIENTREF AS clientRef,CAST(I.TRCODE AS int) AS transactionType,
      I.ACCOUNTREF AS accountRef,I.ACCFICHEREF AS slipRef,CAST(I.ACCOUNTED AS int) AS posted,
      CAST(I.NETTOTAL AS decimal(28,4)) AS amount,CAST(I.TOTALVAT AS decimal(28,4)) AS vat,
      F.LOGICALREF AS foundSlip,CAST(F.CANCELLED AS int) AS cancelledSlip,F.DATE_ AS ledgerDate
      FROM dbo.LG_411_01_INVOICE I LEFT JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=I.ACCFICHEREF
      WHERE I.CANCELLED=0 AND I.DATE_>={start} AND I.DATE_<{end}"""


def invoice_match_base(year, as_of):
    """Aggregate before joining: one row per voucher and invoice account.

Only explicitly mapped, posted invoices participate. Many invoice headers may
share a voucher: neither the header total nor ledger rows are multiplied.
"""
    start,end=bounds(year,as_of)
    return f"""SELECT V.slipRef,V.accountRef,A.CODE AS accountCode,V.invoiceCount,
      V.expected,L.actual,V.expected-COALESCE(L.actual,0) AS difference,
      L.lineCount,V.firstDate,V.lastDate,F.FICHENO AS slipNo,F.DATE_ AS ledgerDate
      FROM (SELECT I.ACCFICHEREF AS slipRef,I.ACCOUNTREF AS accountRef,COUNT(*) AS invoiceCount,
      MIN(I.DATE_) AS firstDate,MAX(I.DATE_) AS lastDate,
      SUM(CASE WHEN I.TRCODE IN (2,3,1,4) THEN -CAST(I.NETTOTAL AS decimal(28,4))
          ELSE CAST(I.NETTOTAL AS decimal(28,4)) END) AS expected
      FROM dbo.LG_411_01_INVOICE I WHERE I.CANCELLED=0 AND I.ACCOUNTED=1
      AND I.TRCODE IN (1,2,3,4,6,7,8,9) AND I.ACCFICHEREF>0 AND I.ACCOUNTREF>0
      AND I.DATE_>={start} AND I.DATE_<{end}
      GROUP BY I.ACCFICHEREF,I.ACCOUNTREF) V
      JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=V.slipRef AND F.CANCELLED=0
      LEFT JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=V.accountRef
      LEFT JOIN (SELECT M.ACCFICHEREF,M.ACCOUNTREF,COUNT(*) AS lineCount,
      SUM(CAST(M.DEBIT AS decimal(28,4))-CAST(M.CREDIT AS decimal(28,4))) AS actual
      FROM dbo.LG_411_01_EMFLINE M WHERE M.CANCELLED=0 AND M.DATE_>={start} AND M.DATE_<{end}
      GROUP BY M.ACCFICHEREF,M.ACCOUNTREF) L
      ON L.ACCFICHEREF=V.slipRef AND L.ACCOUNTREF=V.accountRef"""


def bank_base(year, as_of):
    start,end=bounds(year,as_of)
    # A bank movement may point directly to a ledger line. Treating only
    # ACCFICHEREF as valid would incorrectly reject those real postings.
    return f"""SELECT B.LOGICALREF AS sourceRef,B.DATE_ AS date,B.TRANNO AS documentNo,
      CAST(B.ACCOUNTED AS int) AS posted,CAST(B.SIGN AS int) AS direction,
      CAST(B.MODULENR AS int) AS sourceModule,B.BNACCREF AS bankAccountRef,
      B.BNACCOUNTREF AS accountRef,B.EMFLINEREF AS directLineRef,
      COALESCE(NULLIF(B.ACCFICHEREF,0),E.ACCFICHEREF) AS slipRef,
      F.LOGICALREF AS foundSlip,CAST(F.CANCELLED AS int) AS cancelledSlip,
      E.LOGICALREF AS foundLine,CAST(E.CANCELLED AS int) AS cancelledLine,
      A.LOGICALREF AS foundAccount,A.CODE AS accountCode,
      CAST(B.AMOUNT AS decimal(28,4)) AS amount,
      CAST(B.TRCURR AS int) AS currency,F.DATE_ AS ledgerDate
      FROM dbo.LG_411_01_BNFLINE B
      LEFT JOIN dbo.LG_411_01_EMFLINE E ON E.LOGICALREF=B.EMFLINEREF
      LEFT JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=COALESCE(NULLIF(B.ACCFICHEREF,0),E.ACCFICHEREF)
      LEFT JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=B.BNACCOUNTREF
      WHERE B.CANCELLED=0 AND B.DATE_>={start} AND B.DATE_<{end}"""


def vat_match_base(year,as_of):
    start,end=bounds(year,as_of)
    return f"""SELECT V.slipRef,V.invoiceCount,V.expected,L.actual,V.expected-COALESCE(L.actual,0) AS difference,
      F.FICHENO AS documentNo,F.DATE_ AS date
      FROM (SELECT I.ACCFICHEREF AS slipRef,COUNT(*) AS invoiceCount,
      SUM(CASE WHEN I.TRCODE IN (1,4,2,3) THEN CAST(I.TOTALVAT AS decimal(28,4))
          ELSE -CAST(I.TOTALVAT AS decimal(28,4)) END) AS expected
      FROM dbo.LG_411_01_INVOICE I WHERE I.CANCELLED=0 AND I.ACCOUNTED=1
      AND I.TRCODE IN (1,2,3,4,6,7,8,9) AND I.ACCFICHEREF>0 AND I.DATE_>={start} AND I.DATE_<{end}
      GROUP BY I.ACCFICHEREF) V JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=V.slipRef AND F.CANCELLED=0
      LEFT JOIN (SELECT M.ACCFICHEREF,
      SUM(CAST(M.DEBIT AS decimal(28,4))-CAST(M.CREDIT AS decimal(28,4))) AS actual
      FROM dbo.LG_411_01_EMFLINE M JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=M.ACCOUNTREF
      WHERE M.CANCELLED=0 AND M.DATE_>={start} AND M.DATE_<{end} AND LEFT(A.CODE,3) IN ('191','391')
      GROUP BY M.ACCFICHEREF) L ON L.ACCFICHEREF=V.slipRef"""


def invoice_line_base(year,as_of):
    start,end=bounds(year,as_of)
    return f"""SELECT I.LOGICALREF AS sourceRef,I.FICHENO AS documentNo,I.DATE_ AS date,I.ACCFICHEREF AS slipRef,
      CAST(I.TOTALVAT AS decimal(28,4)) AS expected,V.actual,V.lineCount,
      CAST(I.TOTALVAT AS decimal(28,4))-COALESCE(V.actual,0) AS difference
      FROM dbo.LG_411_01_INVOICE I LEFT JOIN (SELECT S.INVOICEREF,COUNT(*) AS lineCount,
      SUM(CAST(S.VATAMNT AS decimal(28,4))) AS actual FROM dbo.LG_411_01_STLINE S
      WHERE S.CANCELLED=0 AND S.INVOICEREF>0 GROUP BY S.INVOICEREF) V ON V.INVOICEREF=I.LOGICALREF
      WHERE I.CANCELLED=0 AND I.DATE_>={start} AND I.DATE_<{end}"""


def bank_match_base(year,as_of):
    start,end=bounds(year,as_of)
    return f"""SELECT B.slipRef,B.accountRef,A.CODE AS accountCode,B.sourceCount,B.expected,L.actual,
      B.expected-COALESCE(L.actual,0) AS difference,F.DATE_ AS date,F.FICHENO AS documentNo
      FROM (SELECT COALESCE(NULLIF(N.ACCFICHEREF,0),E.ACCFICHEREF) AS slipRef,N.BNACCOUNTREF AS accountRef,
      COUNT(*) AS sourceCount,SUM(CASE WHEN N.SIGN=0 THEN CAST(N.AMOUNT AS decimal(28,4))
        ELSE -CAST(N.AMOUNT AS decimal(28,4)) END) AS expected
      FROM dbo.LG_411_01_BNFLINE N LEFT JOIN dbo.LG_411_01_EMFLINE E
        ON E.LOGICALREF=N.EMFLINEREF AND (N.ACCFICHEREF=0 OR N.ACCFICHEREF IS NULL)
      WHERE N.CANCELLED=0 AND N.ACCOUNTED=1 AND N.SIGN IN (0,1)
        AND N.DATE_>={start} AND N.DATE_<{end}
      GROUP BY COALESCE(NULLIF(N.ACCFICHEREF,0),E.ACCFICHEREF),N.BNACCOUNTREF) B
      JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=B.slipRef AND F.CANCELLED=0
      JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=B.accountRef
      LEFT JOIN (SELECT M.ACCFICHEREF,M.ACCOUNTREF,
      SUM(CAST(M.DEBIT AS decimal(28,4))-CAST(M.CREDIT AS decimal(28,4))) AS actual
      FROM dbo.LG_411_01_EMFLINE M WHERE M.CANCELLED=0 AND M.DATE_>={start} AND M.DATE_<{end}
      GROUP BY M.ACCFICHEREF,M.ACCOUNTREF) L ON L.ACCFICHEREF=B.slipRef AND L.ACCOUNTREF=B.accountRef"""


def daily_cash_base(year, as_of):
    start,end=bounds(year,as_of)
    return f"""SELECT X.accountRef,A.CODE AS accountCode,X.date,X.balance
      FROM (SELECT M.ACCOUNTREF AS accountRef,CAST(M.DATE_ AS date) AS date,
      SUM(SUM(CAST(M.DEBIT AS decimal(28,4))-CAST(M.CREDIT AS decimal(28,4))))
      OVER(PARTITION BY M.ACCOUNTREF ORDER BY CAST(M.DATE_ AS date) ROWS UNBOUNDED PRECEDING) AS balance
      FROM dbo.LG_411_01_EMFLINE M JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=M.ACCFICHEREF
      JOIN dbo.LG_411_EMUHACC C ON C.LOGICALREF=M.ACCOUNTREF
      WHERE M.CANCELLED=0 AND F.CANCELLED=0 AND M.DATE_>={start} AND M.DATE_<{end}
      AND C.CODE LIKE '100%' GROUP BY M.ACCOUNTREF,CAST(M.DATE_ AS date)) X
      JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=X.accountRef"""


DEFINITIONS = {
 'invoice-unposted':('Muhasebeye aktarılmamış faturalar','invoice','posted=0',
     'İptal edilmemiş faturada ACCOUNTED=0. Muhasebeye aktarım gecikmesi veya kapsam farkı incelenir; kayıt dışı satış hükmü değildir.'),
 'invoice-broken-link':('Aktarıldı işaretli faturanın fiş bağlantısı','invoice','posted=1 AND (foundSlip IS NULL OR cancelledSlip<>0)',
     'Aktarıldı işaretli faturanın bağlı muhasebe fişi bulunmalı ve iptal edilmemiş olmalı.'),
 'invoice-date':('Fatura ve muhasebe kayıt tarihleri','invoice','foundSlip IS NOT NULL AND date<>ledgerDate',
     'Fatura tarihi ile bağlı muhasebe fişi tarihi farklı. Dönemleme ve aktarım açıklaması gerekir.'),
 'invoice-account':('Faturanın muhasebe hesap eşleşmesi','invoice','posted=1 AND (accountRef IS NULL OR accountRef=0)',
     'Aktarıldı işaretli faturada müşteri/satıcı muhasebe hesap referansı eksik.'),
 'invoice-ledger-amount':('Fatura tutarı ↔ bağlı muhasebe hesabı','invoice-match','ABS(difference)>0.01 OR actual IS NULL',
     'Aynı fiş ve aynı hesap için faturalar önce toplanır, muhasebe net borç−alacak ile karşılaştırılır. Alış/satış iadeleri ters işaretlidir; fark tahmini zarar değildir.'),
 'invoice-vat-ledger':('Fatura KDV’si ↔ muhasebe KDV’si','vat-match','ABS(difference)>0.01',
     'Fiş bazında fatura KDV toplamı, 191+391 net borç−alacak ile karşılaştırılır. İadelerin yönü ters alınır; tevkifat/istisna ve özel hesap kullanımı ayrıca incelenir.'),
 'invoice-vat-lines':('Fatura başlığı ↔ satır KDV toplamı','invoice-lines','ABS(difference)>0.01 OR lineCount IS NULL',
     'Fatura başlığındaki TOTALVAT ile bağlı, iptal edilmemiş stok/hizmet satırlarının VATAMNT toplamı. Satır veya tutar farkı inceleme adayıdır.'),
 'bank-unposted':('Muhasebeye aktarılmamış banka hareketleri','bank','posted=0',
     'Logo banka alt modülünde ACCOUNTED=0. Başka modülden gelen yansıma/aktarılma durumu ayrıca incelenir.'),
 'bank-broken-link':('Banka hareketinin muhasebe bağlantısı','bank',
     'posted=1 AND (foundSlip IS NULL OR cancelledSlip<>0 OR (directLineRef>0 AND (foundLine IS NULL OR cancelledLine<>0)))',
     'Fiş referansı veya doğrudan muhasebe satırı üzerinden bağlantı kontrol edilir; doğrudan satıra bağlanan hareketler dışlanmaz.'),
 'bank-account':('Banka hareketinin muhasebe hesap kartı','bank','posted=1 AND foundAccount IS NULL',
     'Aktarıldı işaretli banka hareketinin banka muhasebe hesabı kartında karşılığı aranır.'),
 'bank-ledger-amount':('Banka alt modülü ↔ muhasebe tutarı','bank-match','ABS(difference)>0.01 OR actual IS NULL',
     'Aktarılmış banka hareketlerinin net tutarı aynı fiş ve banka muhasebe hesabında toplanarak karşılaştırılır. Bağımsız banka ekstresi mutabakatı değildir.'),
 'cash-negative-day':('Gün sonu negatif kasa bakiyesi','cash','balance < -0.01',
     'Açılış dahil, hesap ve işlem günü bazında birikimli net borç−alacak. Negatif günler ayrı gösterilir; günler üzerindeki bakiyeler risk tutarı olarak toplanmaz.'),
}


def source_sql(kind,year,as_of):
    return {'invoice':invoice_base,'invoice-match':invoice_match_base,'bank':bank_base,'cash':daily_cash_base,
            'vat-match':vat_match_base,'invoice-lines':invoice_line_base,'bank-match':bank_match_base}[kind](year,as_of)


def read_deep(query, year, as_of):
    start,end=bounds(year,as_of)
    results={}; errors={}; sqls=[]; executed={}; elapsed=0
    def read(key, sql):
        nonlocal elapsed
        try:
            result=query(sql,year)
            results[key]=result['records'];sqls.append(result.get('physicalSql'));executed[key]=result.get('physicalSql');elapsed+=result.get('dbMs',0)
        except Exception:
            logging.getLogger(__name__).exception('Deep audit source unavailable: %s',key)
            errors[key]='Kaynak sorgusu tamamlanamadı; boş veri veya olumlu sonuç sayılmaz.'
            results[key]=[]
        return results[key]
    for kind in dict.fromkeys(d[1] for d in DEFINITIONS.values()):
        selected=[(key,d) for key,d in DEFINITIONS.items() if d[1]==kind]
        expressions=['COUNT(*) AS rows']
        for i,(_,d) in enumerate(selected):
            expressions.append(f'SUM(CASE WHEN {d[2]} THEN 1 ELSE 0 END) AS affected{i}')
        read(kind,f"SELECT {','.join(expressions)} FROM ({source_sql(kind,year,as_of)}) S")
    read('invoiceTypes',f"""SELECT CAST(I.TRCODE AS int) AS type,COUNT(*) AS rows,
      SUM(CASE WHEN I.ACCOUNTED=0 THEN 1 ELSE 0 END) AS unposted
      FROM dbo.LG_411_01_INVOICE I WHERE I.CANCELLED=0 AND I.DATE_>={start} AND I.DATE_<{end}
      GROUP BY I.TRCODE ORDER BY I.TRCODE""")
    read('taxPeriods',"""SELECT H.YEAR_ AS year,H.MONTH_ AS month,CAST(H.TYP AS int) AS type,
      COUNT(*) AS rows FROM dbo.LG_411_TAXDECLHDR H
      GROUP BY H.YEAR_,H.MONTH_,H.TYP ORDER BY H.YEAR_,H.MONTH_,H.TYP""")
    read('loanSchedule',f"""SELECT CAST(P.TRANSTYPE AS int) AS type,CAST(C.TRCURR AS int) AS currency,
      COUNT(*) AS rows,SUM(CASE WHEN P.BNFCHREF>0 THEN 1 ELSE 0 END) AS bankLinked,
      SUM(CASE WHEN C.LOGICALREF IS NULL THEN 1 ELSE 0 END) AS missingCredit,
      MIN(P.DUEDATE) AS firstDate,MAX(P.DUEDATE) AS lastDate,
      SUM(CAST(P.TOTAL AS decimal(28,4))) AS principal,SUM(CAST(P.INTTOTAL AS decimal(28,4))) AS interest
      FROM dbo.LG_411_BNCREPAYTR P LEFT JOIN dbo.LG_411_BNCREDITCARD C ON C.LOGICALREF=P.CREDITREF
      WHERE P.DUEDATE>={start} AND P.DUEDATE<'{year+1}0101'
      GROUP BY P.TRANSTYPE,C.TRCURR ORDER BY P.TRANSTYPE,C.TRCURR""")
    read('chequeStates',f"""SELECT CAST(C.DOC AS int) AS documentType,CAST(T.STATUS AS int) AS state,
      CAST(C.TRCURR AS int) AS currency,COUNT(*) AS rows,
      SUM(CASE WHEN C.DUEDATE<{end} THEN 1 ELSE 0 END) AS dueByCutoff,
      SUM(CAST(C.AMOUNT AS decimal(28,4))) AS amount
      FROM dbo.LG_411_01_CSCARD C JOIN (
        SELECT CSREF,STATUS,ROW_NUMBER() OVER(PARTITION BY CSREF ORDER BY DATE_ DESC,LOGICALREF DESC) AS rn
        FROM dbo.LG_411_01_CSTRANS WHERE CANCELLED=0 AND DATE_<{end}) T ON T.CSREF=C.LOGICALREF AND T.rn=1
      WHERE C.CANCELLED=0 GROUP BY C.DOC,T.STATUS,C.TRCURR ORDER BY C.DOC,T.STATUS,C.TRCURR""")
    read('stockSlips',f"""SELECT CAST(S.TRCODE AS int) AS type,COUNT(*) AS rows,
      SUM(CASE WHEN S.DATE_>={end} THEN 1 ELSE 0 END) AS afterCutoff,
      MIN(S.DATE_) AS firstDate,MAX(S.DATE_) AS lastDate FROM dbo.LG_411_01_STFICHE S
      WHERE S.CANCELLED=0 AND S.DATE_>={start} AND S.DATE_<'{year+1}0101'
      GROUP BY S.TRCODE ORDER BY S.TRCODE""")
    read('ebookPeriods',f"""SELECT E.PERYEAR AS year,E.PERMONTH AS month,CAST(E.TYP AS int) AS type,
      CAST(E.BOOKSTATUS AS int) AS state,E.REPORTSTARTDATE AS firstDate,E.REPORTENDDATE AS lastDate,
      E.JOURNALCOUNT AS journalCount FROM dbo.LG_411_EBOOKINFO E WHERE E.PERYEAR={year}
      ORDER BY E.PERMONTH,E.TYP""")
    read('exportDocuments',f"""SELECT COUNT(*) AS rows,
      SUM(CASE WHEN NULLIF(LTRIM(RTRIM(X.CUSTDOCNO)),'') IS NULL THEN 1 ELSE 0 END) AS missingCustomsNumber,
      SUM(CASE WHEN X.CUSTDOCDATE IS NULL OR X.CUSTDOCDATE<'19010101' THEN 1 ELSE 0 END) AS missingCustomsDate
      FROM dbo.LG_411_01_INVEXIMINFO X JOIN dbo.LG_411_01_INVOICE I ON I.LOGICALREF=X.INVOICEREF
      WHERE I.CANCELLED=0 AND I.DATE_>={start} AND I.DATE_<{end}""")
    read('attachments',"""SELECT CAST(P.INFOTYP AS int) AS type,CAST(P.DOCTYP AS int) AS documentType,
      COUNT(*) AS rows,SUM(CASE WHEN DATALENGTH(P.LDATA)>0 THEN 1 ELSE 0 END) AS withPayload,
      SUM(CASE WHEN SUBSTRING(P.LDATA,2,14)=0x466174757261204164726573693A THEN 1 ELSE 0 END) AS addressNotes,
      SUM(CASE WHEN SUBSTRING(P.LDATA,1,4)=0x25504446 THEN 1 ELSE 0 END) AS pdfSignatures,
      SUM(CASE WHEN SUBSTRING(P.LDATA,1,5)=0x3C3F786D6C THEN 1 ELSE 0 END) AS xmlSignatures
      FROM dbo.LG_411_01_PERDOC P GROUP BY P.INFOTYP,P.DOCTYP ORDER BY P.INFOTYP,P.DOCTYP""")
    checks=[]
    for kind in dict.fromkeys(d[1] for d in DEFINITIONS.values()):
        row=results[kind][0] if results[kind] else {}
        for i,(key,d) in enumerate((k,v) for k,v in DEFINITIONS.items() if v[1]==kind):
            count=int(row.get(f'affected{i}') or 0)
            status='unverified' if kind in errors or not row.get('rows') else 'finding' if count else 'passed'
            checks.append({'id':key,'title':d[0],'status':status,'affected':count if kind not in errors else None,
                'tested':row.get('rows'),'formula':d[3],'detailKind':kind,'sql':executed.get(kind),'sqlResultColumns':{'tested':'rows','affected':f'affected{i}'},
                'limitation':'Bu sonuç yalnız belirtilen veri kontrolüdür; belgenin hukuki geçerliliği veya dış mutabakatı değildir.'})
    def rows(key):
        return sum(int(r.get('rows') or 0) for r in results.get(key,[]))
    def card(key,title,found,usable,missing,why,next_step,source_key):
        return {'id':key,'title':title,'status':'unavailable' if source_key in errors else 'partial' if found else 'missing',
            'records':found if source_key not in errors else None,
            'found':('Kaynak sorgusu tamamlanamadı; kayıt varlığı doğrulanamadı.' if source_key in errors else usable if found or key=='tax' else 'Taranan tablolarda bu rapor kapsamına uyan kayıt bulunmadı.'),
            'missing':missing,'why':why,
            'nextStep':next_step,'sourceDataset':source_key}
    current_tax=sum(int(r['rows']) for r in results['taxPeriods'] if r['year']==year)
    cards=[
      card('invoices','Faturalar ve muhasebe bağlantısı',rows('invoice'),
           'Fatura, cari hesap, muhasebe fişi, aktarım işareti ve tutar bulundu.',
           'Asıl belge doğruluğu ve işlem niteliği; açıklama gerektiren tutar farkları.',
           'Fatura kaydı, teslimin gerçekleştiğini veya vergisel uygunluğu tek başına kanıtlamaz.',
           'Aktarılmayan faturaları ve tutar farklarını kaynak kayıtlarıyla inceleyin.','invoice'),
      card('banks','Banka hareketleri',rows('bank'),
           'Logo banka hareketleri ve fiş/doğrudan satır bağlantıları bulundu.',
           'Bankanın bağımsız hesap ekstresi ve teyit edilmiş dış mutabakatı.',
           'Logo içindeki banka kaydı ile bankanın verdiği ekstre aynı kanıt değildir.',
           'Önce iç muhasebe bağlantılarını inceleyin; dış mutabakat için banka ekstresi gerekir.','bank'),
      card('tax','Beyannameler',current_tax,
           f'Kaynakta {rows("taxPeriods")} tarihsel beyanname başlığı bulundu; {year} döneminde {current_tax} kayıt.',
           f'{year} dönemine ait onaylı beyanname, tahakkuk ve beyanname satır sözlüğü.',
           'Başka yılın beyannamesiyle bu dönemin KDV veya kurumlar vergisi doğrulanamaz.',
           'İlgili dönemin onaylı beyanname verisi geldikten sonra muhasebe satırlarıyla karşılaştırılabilir.','taxPeriods'),
      card('loans','Krediler ve ödeme planı',rows('loanSchedule'),
           'Kredi kartı, vade, anapara/faiz planı ve bankaya bağlı ödeme satırları bulundu.',
           'Sözleşme, faiz gün esası, masraf kapsamı ve bankanın bağımsız ödeme teyidi.',
           'Plan satırı ve gerçekleşen ödeme ayrı tutulur; ikisini toplamak borcu çift sayar.',
           'Plan ve ödeme satırlarını para birimiyle ayrı inceleyin.','loanSchedule'),
      card('cheques','Çek ve senetler',rows('chequeStates'),
           'Kart, vade ve rapor kesimine kadar son durum hareketi bulundu.',
           'Özgün senet/çek, hukuki nitelik, teminat ve uygulanabilir reeskont oranı.',
           'Vadenin geçmiş olması tek başına tahsil edilemeyen alacak anlamına gelmez.',
           'Durum kodu ve vade ayrı incelenmeli; reeskont için sözleşme ve dönem oranı tamamlanmalı.','chequeStates'),
      card('stock','Stok ve sayım dayanakları',rows('stockSlips'),
           'Stok fişleri ve kaynak türleri bulundu; rapor kesiminden ileri tarihli kayıtlar ayrıca sayılıyor.',
           'İmzalı fiili sayım tutanağı, sayılan miktar ve kabul edilmiş maliyet/fire politikası.',
           'Stok veya düzeltme fişi, fiziki sayımın yapıldığını ve gerçek miktarı tek başına kanıtlamaz.',
           'Kaynak fişleriyle sayım tutanağını eşleştirin; ileri tarihli kayıtları ayrı değerlendirin.','stockSlips'),
      card('ebook','Elektronik defter dönemleri',len(results['ebookPeriods']),
           'Defter dönem başlıkları, üretim tarih aralığı ve ham durum kodları bulundu.',
           'İmzalı defter/berat dosyası ve GİB kabul kanıtıyla doğrulanmış durum sözlüğü.',
           'Yerel durum kodu tek başına resmî kabul veya eksiksiz teslim kanıtı değildir.',
           'Kayıtlı aylarla muhasebe kapsamını karşılaştırın; dosya ve kabul kanıtını ayrıca doğrulayın.','ebookPeriods'),
      card('exports','İhracat ve gümrük bilgileri',rows('exportDocuments'),
           'Faturaya bağlı dış ticaret başlıkları ve gümrük belge alanları bulundu.',
           'Onaylı gümrük çıkışı, döviz getirme/ödeme teyidi ve işlem bazında istisna koşulları.',
           'Belge numarası alanının dolu olması gümrükçe onaylandığını göstermez.',
           'Fatura, gümrük tarihi ve banka transferini onaylı belgelerle eşleştirin.','exportDocuments'),
      card('attachments','Belge notları ve ek kayıtlar',rows('attachments'),
           'İçerik taşıyan depo kayıtları bulundu; adres notları ve tanınan PDF/XML başlangıçları ayrı sayılır.',
           'Dosya türü, ilgili işlem, imza/onay ve denetim kanıtı olarak uygunluk.',
           'Ek sayısını bağımsız banka ekstresi, beyanname veya sayım tutanağı sayısı kabul etmiyoruz.',
           'Kaynak türleri çözülüp dosya–işlem bağı doğrulandıktan sonra belge kontrollerine dahil edilir.','attachments'),
    ]
    return {'revision':REVISION,'asOf':str(as_of)[:10],'checks':checks,'datasets':results,'sources':cards,
        'errors':errors,'status':'unverified' if errors else 'observed','sql':sqls,'dbMs':elapsed,
        'limitations':['Tarama tek şirketin doğrulanmış 2026 kopyasındadır; diğer yılların yedekleri birleştirilmez.',
            'Hareket kontrolleri muhasebenin son veri tarihine kadar çalışır; kredi planı 2026 vadelerini ayrıca gösterir.',
            'Beyanname başlıkları ve belge ekleri bulunması, içeriklerinin bu döneme ait onaylı dış kanıt olduğunu göstermez.',
            'Aynı günün çek/senet hareketleri kaynak kayıt numarasına göre sıralanır; hukuki durum veya kesin işlem sırası kabulü değildir.']}


def exception_sql(check_id,year,as_of,page):
    d=DEFINITIONS[check_id]
    order='accountRef,date' if d[1]=='cash' else 'slipRef,accountRef' if d[1] in {'invoice-match','bank-match'} else 'slipRef' if d[1]=='vat-match' else 'date,sourceRef'
    return f"SELECT S.*,COUNT(*) OVER() AS totalRows FROM ({source_sql(d[1],year,as_of)}) S WHERE {d[2]} ORDER BY {order} OFFSET {page*50} ROWS FETCH NEXT 50 ROWS ONLY"
