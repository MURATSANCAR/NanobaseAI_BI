-- M51 Müşteri hizmetleri: bağımsız referans sorguları (kabul.py bunları örnek değerlerle koşturur).
-- CRM: Timas_MSCRM.dbo (canlı .28). Logo: LG_<firma> (yıl → firma L_CAPIPERIOD). Masa: MariaDB `tabHD Ticket`.
-- Kimlik bilgisi kolonları (new_kargofirmasi / new_webuser parola, token, secret) hiçbir sorguda yok.

-- K1 Sipariş durumu ve bekleyen adet (Kural C13); <no> canlıdan seçilir, belgeye yazılmaz
SELECT TOP 1 CAST(statuscode AS int) AS durum, new_bekleyenadet AS bekleyen, new_sevktarihi
FROM Timas_MSCRM.dbo.new_siparisBase WHERE statecode = 0 AND new_name = N'<no>';

-- K2 Kargo kaydı (Kural C19: metin kolon, virgüllü ondalık)
SELECT b.new_KargoTakipNo, b.new_kargofirmasi, b.new_sevkiyatcikissubesi,
       TRY_CAST(REPLACE(b.new_Tutar, ',', '.') AS FLOAT) AS tutar
FROM Timas_MSCRM.dbo.new_siparisBase s
JOIN Timas_MSCRM.dbo.new_kargobilgisiBase b ON b.new_KargoTakipNo = s.new_kargotakipno AND b.statecode = 0
WHERE s.statecode = 0 AND s.new_name = N'<no>';

-- K3 Bayi: açık (bekleyen) sipariş sayısı ve bekleyen adet (C13 «bekleyen» tanımı)
SELECT COUNT(*) AS acik, SUM(new_bekleyenadet) AS bekleyen
FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND new_firmaid = '<cari guid>' AND new_bekleyenadet > 0
  AND CAST(statuscode AS int) NOT IN (100000015, 100000000, 100000001, 100000003, 2);

-- K3b Bayi: risk onayı bekleyen (100000004 Risk Limit Onayı Bekliyor, 100000016 Risk Bilgisi Bekleniyor), ekranın penceresiyle
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND new_firmaid = '<cari guid>' AND CAST(statuscode AS int) IN (100000004, 100000016)
  AND (new_siparistarihi >= DATEADD(day, -<SUPPORT_ORDER_DAYS>, CAST(GETDATE() AS date))
       OR (new_bekleyenadet > 0 AND CAST(statuscode AS int) NOT IN (100000015, 100000000, 100000001, 100000003, 2)));

-- K4 Logo: carinin penceredeki satış (7/8/9) ve iade (2/3) faturaları — her yıl firması için ayrı, toplanır
SELECT COUNT(*) AS n, SUM(I.NETTOTAL) AS t
FROM dbo.LG_<firma>_01_INVOICE I JOIN dbo.LG_<firma>_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND I.TRCODE IN (2,3,7,8,9) AND C.CODE = '<cari kodu>' AND I.DATE_ >= '<pencere başı>';

-- K4b Logo veri sonu (faturalı satış)
SELECT MAX(DATE_) FROM dbo.LG_<firma>_01_STLINE
WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9);

-- K5 Masa (MariaDB, site `destek`): son 30 günde açılan, bugün açık, ilk yanıt dakikaları, puanlar
SELECT COUNT(*) FROM `tabHD Ticket` WHERE opening_date BETWEEN CURDATE() - INTERVAL 29 DAY AND CURDATE();
SELECT COUNT(*) FROM `tabHD Ticket` WHERE IFNULL(status_category, '') <> 'Resolved';
SELECT TIMESTAMPDIFF(SECOND, TIMESTAMP(opening_date, opening_time), first_responded_on) / 60
FROM `tabHD Ticket` WHERE opening_date BETWEEN CURDATE() - INTERVAL 29 DAY AND CURDATE()
  AND first_responded_on IS NOT NULL AND first_responded_on >= TIMESTAMP(opening_date, opening_time);
SELECT feedback_rating FROM `tabHD Ticket`
WHERE opening_date BETWEEN CURDATE() - INTERVAL 29 DAY AND CURDATE() AND feedback_rating > 0;
