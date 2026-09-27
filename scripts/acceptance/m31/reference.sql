-- M31 Okul tanıtım: bağımsız referans sorguları (CRM .28 Timas_MSCRM, Logo güncel kopya). compare.py bunları
-- parametreleriyle koşturur ve köprünün cevabıyla karşılaştırır. Tarihler İstanbul günüdür: CRM UTC saklar,
-- Türkiye 2016'dan beri sabit UTC+3 → DATEADD(hour, 3, ...).

-- 1. Okul sayısı: il × kademe dağılımı (ekranda il + kademe süzgecinin toplamı; il adları sadeleştirilerek birleşir).
SELECT i.new_name AS il, CAST(z.new_okulkademesi AS int) AS kademe, COUNT(*) AS n
FROM Timas_MSCRM.dbo.new_ziyaretyerleriBase z
LEFT JOIN Timas_MSCRM.dbo.new_illerBase i ON i.new_illerId = z.new_ili
WHERE z.statecode = 0 AND z.new_KurumTipi = 1
GROUP BY i.new_name, z.new_okulkademesi;

-- 2. Öğrenci sayısı temizliği: sayıya çevrilebilen (dolu) okul sayısı; çevrilemeyen «bilinmiyor» (0 değil).
SELECT COUNT(*) AS dolu
FROM Timas_MSCRM.dbo.new_ziyaretyerleriBase
WHERE statecode = 0 AND new_KurumTipi = 1 AND TRY_CAST(new_renciSays AS int) IS NOT NULL;

-- 3. Geçmiş ziyaret: okul kartındaki «CRM'de tamamlanan (ziyaret yeri bağlı)» sayısı, @id = ziyaret yeri.
SELECT COUNT(*) AS n
FROM Timas_MSCRM.dbo.new_etkinlikBase
WHERE statecode = 0 AND new_ZiyaretYeri = @id AND new_ziyarettipi IN (1,2,3) AND statuscode = 100000002;

-- 4. Örnek/satış: dönem raporundaki sipariş tipleri (dönemde açılan; @bas–@bit İstanbul günü, bitiş dahil).
SELECT new_siparistipi, COUNT(*) AS n, SUM(new_indirimlitoplamtutar) AS tutar
FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND new_siparistipi IN (10,11,13)
  AND DATEADD(hour, 3, CreatedOn) >= @bas AND DATEADD(hour, 3, CreatedOn) < DATEADD(day, 1, @bit)
GROUP BY new_siparistipi;

-- 5a. Katalog stoku: PDF'teki her kitap için güncel kopyada stok bakiyesi > 0 (tarih filtresiz).
SELECT I.CODE, SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT ELSE -S.AMOUNT END) AS bakiye
FROM dbo.LG_411_01_STLINE S JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.IOCODE IN (1,2,3,4) AND I.CODE IN (@kodlar)
GROUP BY I.CODE;

-- 5b. Katalog fiyatı: bugün geçerli genel satış listesi (cari özel kodu boş) — en düşük.
SELECT I.CODE, MIN(P.PRICE) AS fiyat
FROM dbo.LG_411_PRCLIST P JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = P.CARDREF
WHERE P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY IN (0,160) AND ISNULL(P.CLSPECODE, '') = ''
  AND P.BEGDATE <= CAST(GETDATE() AS date) AND P.ENDDATE >= CAST(GETDATE() AS date) AND I.CODE IN (@kodlar)
GROUP BY I.CODE;

-- 6. Geçmiş bayi eşleşmesi: «cari ile ziyaret» çiftleri = semantic_school_dealer_links kaynak='gecmis'
--    (ziyaret yeri boş kayıt eşleşme olamaz; analizdeki sorguya NOT NULL eklendi).
SELECT DISTINCT new_ZiyaretYeri, new_AracMteriId
FROM Timas_MSCRM.dbo.new_etkinlikBase
WHERE statecode = 0 AND new_ziyaretsekli = 1 AND new_AracMteriId IS NOT NULL AND new_ZiyaretYeri IS NOT NULL;

-- 7. Kapsam: SQL değil — temsilci hesabıyla başka temsilcinin ziyaret raporu GET /api/v1/schools/visits/{id} → 403,
--    okul.herkesinki yetkili hesapla → 200 (compare.py --write).
