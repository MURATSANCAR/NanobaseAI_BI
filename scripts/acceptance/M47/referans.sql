-- M47 Risk ve uyum — bağımsız referans sorguları (köprü kodu kullanılmadan; test sunucusunda, salt okunur).
-- Firma numarası yıla göre L_CAPIPERIOD'dan okunur (411 = 2026); aşağıda 411 örnektir, kabul.py güncel firmayı koyar.
-- CRM (.28) ve Logo ayrı sunuculardır: tek sorguda birleşmez, stok kodu listesiyle birleştirilir.

-- R1 · Logo veri gecikmesi: gösterge = bugün − bu tarih (beklenen 2026-08-17, donmuş kopya).
SELECT MAX(DATE_) AS son FROM dbo.LG_411_01_INVOICE WHERE CANCELLED = 0;

-- R2 · Müşteri yoğunlaşması (ilk 4): pay × 100 = gösterge. Payda 2026 net ciro 848.110.178,82 ₺ (fatura başlığı).
WITH N AS (SELECT CLIENTREF, SUM(CASE WHEN TRCODE IN (7,8,9) THEN NETTOTAL ELSE -NETTOTAL END) AS n
           FROM dbo.LG_411_01_INVOICE WHERE CANCELLED = 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '2026-01-01' AND DATE_ < '2027-01-01'
           GROUP BY CLIENTREF)
SELECT (SELECT SUM(n) FROM (SELECT TOP 4 n FROM N ORDER BY n DESC) t) / SUM(n) AS pay, SUM(n) AS payda FROM N;

-- R3 · Karşılıksız çıkan çek (2026, olay): hareket tablosundan sayılır, tutar kart başına bir kez.
-- (Gösterge CSCARD + EXISTS ile yazılmıştır; burada ters yönden, hareketten karta.) Beklenen 6 çek, 6.326.658 ₺.
SELECT COUNT(*) AS adet, SUM(K.AMOUNT) AS tutar
FROM (SELECT DISTINCT T.CSREF FROM dbo.LG_411_01_CSTRANS T
      WHERE T.STATUS = 11 AND T.DEVIR = 0 AND T.CANCELLED = 0 AND T.DATE_ >= '2026-01-01' AND T.DATE_ < '2027-01-01') E
JOIN dbo.LG_411_01_CSCARD K ON K.LOGICALREF = E.CSREF
WHERE K.CANCELLED = 0 AND K.DOC IN (1, 2);

-- R4 · Döviz cinsinden fatura: yerel para kodları dışı (varsayılan 0, 160). Bilgi paketindeki 74 (TRCURR <> 0) ayrıca yazılır.
SELECT COUNT(*) AS adet FROM dbo.LG_411_01_INVOICE WHERE CANCELLED = 0 AND TRCURR NOT IN (0, 160);
SELECT COUNT(*) AS adet_trcurr_sifir_disi FROM dbo.LG_411_01_INVOICE WHERE CANCELLED = 0 AND TRCURR <> 0;

-- R5 · Süresi bitmiş ama satan kitap. Önce CRM: süresi bitmiş telif alış sözleşmeli kitaplar ve kitap başına yürürlükte
-- sözleşme sayısı (gruplamayla; göstergenin NOT EXISTS yazımından bağımsız) …
SELECT k.new_StokKodu AS stok,
       SUM(CASE WHEN ISNULL(s.new_suresizsozlesme,0) = 0 AND s.new_SozlesmeBitisTarihi < CAST(GETDATE() AS date) THEN 1 ELSE 0 END) AS biten,
       SUM(CASE WHEN ISNULL(s.new_suresizsozlesme,0) = 1 OR s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date) THEN 1 ELSE 0 END) AS yururlukte
FROM Timas_MSCRM.dbo.new_kitapBase k
JOIN Timas_MSCRM.dbo.new_new_sozlesme_new_kitapBase sk ON sk.new_kitapid = k.new_kitapId
JOIN Timas_MSCRM.dbo.new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND k.new_StokKodu IS NOT NULL
GROUP BY k.new_StokKodu HAVING SUM(CASE WHEN ISNULL(s.new_suresizsozlesme,0) = 0 AND s.new_SozlesmeBitisTarihi < CAST(GETDATE() AS date) THEN 1 ELSE 0 END) > 0
   AND SUM(CASE WHEN ISNULL(s.new_suresizsozlesme,0) = 1 OR s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date) THEN 1 ELSE 0 END) = 0;
-- … sonra Logo: bu kodlarda veri son gününden geriye 30 günde faturalı satış (adet > 0).
SELECT I.CODE, SUM(L.AMOUNT) AS adet
FROM dbo.LG_411_01_STLINE L JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF
WHERE L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (7,8,9)
  AND L.DATE_ > DATEADD(day, -30, '2026-08-17') AND L.DATE_ <= '2026-08-17'
  AND I.CODE IN (/* @stok_listesi */ '')
GROUP BY I.CODE HAVING SUM(L.AMOUNT) > 0;

-- R6 · Maliyetsiz satış payı = 1 − (M45 kabul 4: maliyetli satır payı).
SELECT SUM(CASE WHEN OUTCOST <> 0 THEN LINENET END) / SUM(LINENET) AS maliyetli_pay
FROM dbo.LG_411_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8);

-- R7 · Tedarikçi yoğunlaşması (ilk 4): alış faturası 1, 4.
WITH N AS (SELECT CLIENTREF, SUM(NETTOTAL) AS n FROM dbo.LG_411_01_INVOICE
           WHERE CANCELLED = 0 AND TRCODE IN (1,4) AND DATE_ >= '2026-01-01' AND DATE_ < '2027-01-01' GROUP BY CLIENTREF)
SELECT (SELECT SUM(n) FROM (SELECT TOP 4 n FROM N ORDER BY n DESC) t) / SUM(n) AS pay FROM N;

-- R8 · Maliyetlendirme gecikmesi: son fatura günü − son maliyetli satış satırı günü (beklenen 30.06.2026 civarı).
SELECT MAX(DATE_) AS son_maliyetli FROM dbo.LG_411_01_STLINE
WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8) AND OUTCOST <> 0;

-- R9 · Süresi yaklaşan sözleşme (60 gün): Telif ve sözleşmeler ekranındaki «yaklaşan» ile aynı tanım.
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_sozlesmeBase s
WHERE s.statecode = 0 AND s.statuscode IN (100000000, 100000006, 100000007) AND ISNULL(s.new_suresizsozlesme, 0) = 0
  AND s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date) AND s.new_SozlesmeBitisTarihi < DATEADD(day, 61, CAST(GETDATE() AS date));
