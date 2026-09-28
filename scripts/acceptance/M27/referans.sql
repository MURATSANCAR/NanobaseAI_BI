-- M27 Fuar, etkinlik ve ödül — doğrudan SQL referansları (köprü kodu kullanılmaz). kabul.py yer tutucuları doldurur:
--   <firma> Logo firma numarası (2026 = 411, 2021–2025 = 211), <bas>/<bit> fuar günleri (dahil, İstanbul),
--   <bit+1> bitişten sonraki gün (hariç üst sınır), <cariler> fuara bağlanan cari kodları (boşsa satır kalkar),
--   <tipler> tip eşlemesinde «fuar» kararı verilen CRM tip kimlikleri, <yazar> CRM ContactId, <kisi> AD hesabı.
-- CRM tarihleri UTC saklanır: gün sınırı İstanbul gününden AT TIME ZONE ile çevrilir.

-- R1 Fuar kanalı net satışı (kabul 1): ekran netCiro / netAdet
SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET WHEN s.TRCODE IN (2,3) THEN -s.LINENET END) AS net_ciro,
       SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT WHEN s.TRCODE IN (2,3) THEN -s.AMOUNT END) AS net_adet
FROM LG_<firma>_01_STLINE s JOIN LG_<firma>_CLCARD c ON c.LOGICALREF = s.CLIENTREF
WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND s.TRCODE IN (2,3,7,8,9)
  AND c.SPECODE2 = 'FUAR' AND s.DATE_ >= '<bas>' AND s.DATE_ < '<bit+1>'
  AND c.CODE IN (<cariler>);

-- R2 Kitap bazında fuar satış adedi (kabul 2): ekrandaki ilk 20 kitap (net satışa göre)
SELECT TOP 20 i.CODE AS stok_kodu,
       SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT ELSE -s.AMOUNT END) AS adet,
       SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET ELSE -s.LINENET END) AS ciro
FROM LG_<firma>_01_STLINE s JOIN LG_<firma>_CLCARD c ON c.LOGICALREF = s.CLIENTREF
JOIN LG_<firma>_ITEMS i ON i.LOGICALREF = s.STOCKREF
WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND s.TRCODE IN (2,3,7,8,9)
  AND c.SPECODE2 = 'FUAR' AND s.DATE_ >= '<bas>' AND s.DATE_ < '<bit+1>' AND c.CODE IN (<cariler>)
GROUP BY i.CODE ORDER BY ciro DESC;

-- R3 CRM fuar/etkinlik/imza siparişleri (kabul 3): ekran orderCount / orderTotal. Sayılan tipler ve dışlanan durumlar
-- köprünün ayarıyla aynı (EVENTS_ORDER_TYPES 4,5,16; EVENTS_ORDER_EXCLUDED_STATUS 100000001 İptal, 100000003 Birleştirildi).
SELECT COUNT(*) AS adet, SUM(new_toplamsatistutari) AS tutar
FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND new_siparistipi IN (4,5,16) AND statuscode NOT IN (100000001,100000003)
  AND new_siparistarihi >= CAST(CAST('<bas>' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime)
  AND new_siparistarihi <  CAST(CAST('<bit+1>' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime);

-- R4 CRM etkinlik takvimi (kabul 4): seçilen ayın «fuar» sınıfı sayısı
SELECT COUNT(*) AS adet FROM Timas_MSCRM.dbo.new_etkinlikBase e
WHERE e.statecode = 0 AND e.new_etkinliktipiid IN (<tipler>)
  AND e.new_BalangTarihi >= CAST(CAST('<ay>' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime)
  AND e.new_BalangTarihi <  CAST(CAST('<sonraki ay>' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime);

-- R5 Yazar etkinlik sayısı (kabul 5): «[yazar] bu yıl kaç etkinlik»
SELECT COUNT(DISTINCT ec.new_etkinlikid) AS adet
FROM Timas_MSCRM.dbo.new_new_etkinlik_contactBase ec
JOIN Timas_MSCRM.dbo.new_etkinlikBase e ON e.new_etkinlikId = ec.new_etkinlikid
WHERE ec.contactid = '<yazar>' AND e.statuscode <> 100000000
  AND e.new_BalangTarihi >= CAST(CAST('<yil>-01-01' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime)
  AND e.new_BalangTarihi <  CAST(CAST('<yil+1>-01-01' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime);

-- R6 Kampüs ajandası (kabul 6): kişinin CRM'de sorumlusu olduğu, bugünden itibaren EVENTS_AGENDA_DAYS gün içinde başlayan,
-- iptal olmayan etkin etkinlikler (portal kartları ayrıca ekranda; bu sorgu CRM payını doğrular)
SELECT e.new_etkinlikId AS id FROM Timas_MSCRM.dbo.new_etkinlikBase e
JOIN Timas_MSCRM.dbo.SystemUserBase u ON u.SystemUserId = e.new_sorumlusu
WHERE e.statecode = 0 AND e.statuscode <> 100000000
  AND (u.DomainName LIKE '%\<kisi>' OR u.DomainName LIKE '<kisi>@%' OR u.DomainName = '<kisi>')
  AND e.new_BalangTarihi >= CAST(CAST('<bugun>' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime)
  AND e.new_BalangTarihi <  CAST(CAST('<bugun+gun+1>' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime);

-- R7 Veri sonu (kabul 7): rapordaki «satış verisi şu güne kadar»
SELECT MAX(DATE_) AS son FROM LG_411_01_INVOICE WHERE CANCELLED = 0;

-- R8 Etkinlik tipi sayısı: eşleme ekranındaki toplam
SELECT COUNT(*) AS adet FROM Timas_MSCRM.dbo.new_etkinliktipiBase;
