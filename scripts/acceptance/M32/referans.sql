-- M32 Kurumsal satış ve B2B — bağımsız referans sorguları (test sunucusunda, gerçek Logo/CRM üzerinde).
-- kabul.py bu sorguları kendi parametreleriyle koşturur; burada elle koşturmak için {yer tutucu}lu hâlleri durur.
-- Firma: 411 = 2026 (güncel kopya), 211 = 2021–2025. Kanal adları CORP_CHANNEL / CORP_DEALER_CHANNELS ayarıdır.

-- R1. KURUM kanalı net ciro, yıl (analiz §14 kabul 1). Portal: SUM(semantic_corp_sales.ciro WHERE year = {yil}).
SELECT SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) AS net_ciro
FROM LG_411_01_STLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF = L.CLIENTREF
WHERE C.SPECODE2 = 'KURUM' AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)
  AND L.DATE_ >= '{yil}-01-01' AND L.DATE_ < '{yil+1}-01-01';
-- Tutarlılık notu: v_channel_net görünümündeki KURUM satırı (varsa) aynı tanımla karşılaştırılır.

-- R2. Kurum alım geçmişi: satış faturası sayısı (başlıktan; analiz §14 kabul 2). Portal: semantic_corp_sales.fatura toplamı.
SELECT COUNT(DISTINCT I.LOGICALREF) AS fatura
FROM LG_411_01_INVOICE I JOIN LG_411_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE C.CODE = '{cari_kodu}' AND I.CANCELLED = 0 AND I.TRCODE IN (7,8,9)
  AND I.DATE_ >= '{yil}-01-01' AND I.DATE_ < '{yil+1}-01-01';

-- R3. B2B portal siparişi, son 90 gün (analiz §14 kabul 3). 2026-09-27 ölçümü: 4.026 (büyüklük kıyası).
SELECT COUNT(*) AS siparis FROM Timas_MSCRM.dbo.new_siparisBase s
WHERE s.statecode = 0 AND s.new_yenib2b = 1 AND s.CreatedOn >= DATEADD(day, -90, GETDATE());
-- İkinci sayım (sipariş tipi 1 = B2B): aynı süzgeç + s.new_siparistipi = 1.

-- R4. Paket fiyatı: kitabın bugün geçerli satış fiyat listeleri (analiz §14 kabul 4). Portal seçimi: cariye bağlı olmayan liste,
-- sonra küçük PRIORITY, sonra en yeni BEGDATE; semantic_corp_books.fiyat / fiyat_liste / fiyat_liste_sayisi.
SELECT P.CODE AS liste, P.PRICE, P.PRIORITY, P.BEGDATE, P.ENDDATE, P.CLIENTCODE, P.CLSPECODE, P.INCVAT
FROM LG_411_PRCLIST P JOIN LG_411_ITEMS I ON I.LOGICALREF = P.CARDREF
WHERE I.CODE = '{stok_kodu}' AND P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY = 160
  AND P.BEGDATE <= CAST(GETDATE() AS date) AND (P.ENDDATE >= CAST(GETDATE() AS date) OR P.ENDDATE IS NULL);

-- R4b. Stok bakiyesi (güncel kopya, tarihsiz). Portal: semantic_corp_books.stok.
SELECT SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT ELSE -S.AMOUNT END) AS bakiye
FROM LG_411_01_STLINE S JOIN LG_411_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE = '{stok_kodu}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.IOCODE IN (1,2,3,4);

-- R5. Tahmini birim maliyet (yalnız CORP_COST_SOURCE=logo): kitabın en son maliyeti girilmiş satış satırı (analiz §14 kabul 5).
SELECT TOP 1 S.OUTCOST, S.DATE_ FROM LG_411_01_STLINE S JOIN LG_411_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE = '{stok_kodu}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9) AND S.OUTCOST <> 0
ORDER BY S.DATE_ DESC, S.LOGICALREF DESC;

-- R6. Sessiz bayi (analiz §14 kabul 6): R = Logo'daki son satış faturası günü. Son satış faturası R−{gun} günden eski ve
-- [R−365, R] içinde en az bir satış faturası olan bayi kanalı carileri. Pencere iki firmaya düşüyorsa 211 için de koşulur.
SELECT C.CODE, MAX(I.DATE_) AS son, COUNT(*) AS fatura
FROM LG_411_01_INVOICE I JOIN LG_411_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE C.SPECODE2 IN ('BAYI','KITAPCI') AND I.CANCELLED = 0 AND I.TRCODE IN (7,8,9)
  AND I.DATE_ >= DATEADD(day, -365, '{R}') AND I.DATE_ <= '{R}'
GROUP BY C.CODE HAVING MAX(I.DATE_) <= DATEADD(day, -{gun}, '{R}');

-- R7. Hacim indirimi geçmişi: kurum faturalarında 100–299 adet aralığındaki gerçekleşen iskontonun medyanı.
SELECT DISTINCT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY 1 - x.net / x.brut) OVER () AS medyan, COUNT(*) OVER () AS n
FROM (SELECT S.INVOICEREF, SUM(S.AMOUNT) AS adet, SUM(S.TOTAL) AS brut, SUM(S.LINENET) AS net
      FROM LG_411_01_STLINE S JOIN LG_411_CLCARD C ON C.LOGICALREF = S.CLIENTREF
      WHERE C.SPECODE2 = 'KURUM' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9)
        AND S.DATE_ >= DATEADD(day, -365, '{R}') AND S.DATE_ <= '{R}'
      GROUP BY S.INVOICEREF) AS x
WHERE x.brut > 0 AND x.adet >= 100 AND x.adet < 300;

-- R8. Kurum sayısı: Logo'da KURUM kanalı cari kartı. Portal: semantic_corp_accounts (logo_code dolu, kanal = KURUM).
SELECT COUNT(*) AS kurum FROM LG_411_CLCARD WHERE SPECODE2 = 'KURUM';
