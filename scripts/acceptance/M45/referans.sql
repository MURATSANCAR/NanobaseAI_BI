-- M45 Finansal raporlar — doğrudan SQL referansları (Logo .25, 2026 kopyası 411; köprü kodu kullanılmaz).
-- «Bugün» = veri son günü: SELECT MAX(DATE_) FROM LG_411_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9)
-- kabul.py aynı sorguları ay/yıl parametresiyle koşar; burada Temmuz 2026 örneği.

-- R1 Mizan denkliği (bütün hesaplar, yıl): |Σ borç − Σ alacak| < 0,01 → ekranda «Mizan denk».
SELECT SUM(L.DEBIT) AS borc, SUM(L.CREDIT) AS alacak, SUM(L.DEBIT) - SUM(L.CREDIT) AS fark
FROM dbo.LG_411_01_EMFLINE L JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF = L.ACCFICHEREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND L.DATE_ >= '20260101' AND L.DATE_ < '20270101';

-- R2 Gelir tablosu hesapları (Temmuz 2026): hesap başına kâr etkisi (alacak − borç), rapor kuralıyla bağımsız yazılmış:
--   7x1 yansıtma hesapları hariç; 7xx için bir yansıtma hesabının BORÇ satırını içeren fiş hariç (M46 tanımı);
--   6xx için bir yansıtma hesabı ya da 690/692 içeren fiş hariç. → /pnl/lines/{satır}/accounts toplamlarıyla kuruşu kuruşuna.
SELECT A.CODE AS hesap, SUM(L.CREDIT) - SUM(L.DEBIT) AS etki
FROM dbo.LG_411_01_EMFLINE L
JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF = L.ACCFICHEREF
JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF = L.ACCOUNTREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND L.DATE_ >= '20260701' AND L.DATE_ < '20260801'
  AND (A.CODE LIKE '6%' OR A.CODE LIKE '7%')
  AND LEFT(A.CODE, 3) NOT IN ('711','721','731','741','751','761','771','781','791')
  AND NOT (A.CODE LIKE '7%' AND EXISTS (SELECT 1 FROM dbo.LG_411_01_EMFLINE K JOIN dbo.LG_411_EMUHACC KA ON KA.LOGICALREF = K.ACCOUNTREF
        WHERE K.ACCFICHEREF = L.ACCFICHEREF AND K.CANCELLED = 0 AND K.SIGN = 0
          AND LEFT(KA.CODE, 3) IN ('711','721','731','741','751','761','771','781','791')))
  AND NOT (A.CODE LIKE '6%' AND EXISTS (SELECT 1 FROM dbo.LG_411_01_EMFLINE K JOIN dbo.LG_411_EMUHACC KA ON KA.LOGICALREF = K.ACCOUNTREF
        WHERE K.ACCFICHEREF = L.ACCFICHEREF AND K.CANCELLED = 0
          AND LEFT(KA.CODE, 3) IN ('711','721','731','741','751','761','771','781','791','690','692')))
GROUP BY A.CODE ORDER BY A.CODE;

-- R3 Fatura net satış (yıl başından; 2026 tamamı M46 kaynağında 837.901.631,04 ₺ ölçüldü) → /pnl?grain=ytd faturaNetSatis.
SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN LINENET ELSE -LINENET END) AS net
FROM dbo.LG_411_01_STLINE
WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '20260101' AND DATE_ < '20260801';

-- R4 Maliyeti işlenmiş satış payı (net tutara göre, iade eksi) → /pnl?grain=ytd maliyet.maliyetliPay ve özet kartı.
SELECT SUM(CASE WHEN OUTCOST <> 0 THEN (CASE WHEN TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * LINENET ELSE 0 END)
       / NULLIF(SUM((CASE WHEN TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * LINENET), 0) AS maliyetli_pay
FROM dbo.LG_411_01_STLINE
WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '20260101' AND DATE_ < '20260801';

-- R5 Kitap kârlılığı (rastgele 5 stok kodu; :kod) → /profitability?by=kitap&q=:kod net ve maliyetLogo.
SELECT SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) AS net,
       SUM(CASE WHEN L.OUTCOST <> 0 THEN (CASE WHEN L.TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * L.AMOUNT * L.OUTCOST ELSE 0 END) AS maliyet
FROM dbo.LG_411_01_STLINE L JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF
WHERE I.CODE = :kod AND L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)
  AND L.DATE_ >= '20260101' AND L.DATE_ < '20270101';

-- R6 Vadesi geçmiş alacak (FIFO; bilgi paketi sorgusu GETDATE() yerine veri son günüyle) → /cash vadesiGecmis.alacak.
--    kabul.py sorguyu kendi metninden kurar (bkz. configs/semantic/knowledge/logo/knowledge/sql/vadesi-gecmis-yaslandirma-fifo.md).

-- R7 Gider tutarlılığı (M46 ↔ M45, köprü veritabanı): aynı ay için
--    SELECT SUM(tutar) FROM semantic_budget_expense_actuals WHERE year = 2026 AND month = 7
--    = SELECT SUM(borc - alacak) FROM semantic_finance_account_actuals WHERE year = 2026 AND month = 7 AND kural = 'dahil' AND hesap_kodu LIKE '7%'

-- R8 Kanal net satışı → /profitability?by=kanal (kanal = CLCARD.SPECODE2).
SELECT ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), N'Grup kodu boş') AS kanal,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net
FROM dbo.LG_411_01_STLINE S LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '20260101' AND S.DATE_ < '20270101'
GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), N'Grup kodu boş');

-- Ölçülecek (varsayımlar parametrede): EMFLINE.BDGTLINETYPE dağılımı (bütçe satırı var mı), CSCARD DOC × CURRSTAT dağılımı
-- (FINANCE_CS_*), new_tahsilatBase statuscode etiketleri (FINANCE_CRM_PENDING_LABEL), 7xx → 63x yansıtma aylık mı.
SELECT BDGTLINETYPE, COUNT(*) FROM dbo.LG_411_01_EMFLINE WHERE CANCELLED = 0 GROUP BY BDGTLINETYPE;
SELECT DOC, CURRSTAT, COUNT(*) AS adet, SUM(AMOUNT) AS tutar FROM dbo.LG_411_01_CSCARD GROUP BY DOC, CURRSTAT ORDER BY DOC, CURRSTAT;
