-- M42 Platform ve kanallar — bağımsız referans sorguları (test sunucusunda, doğrudan Logo/CRM bağlantısıyla; köprünün
-- run_sql ucu ve kanal paketi SQL'i kullanılmaz). kabul.py bunları aynı yazımla koşar, API'nin verdiği sonuçla karşılaştırır.
-- Yer tutucular: :firm (yılın Logo firması, L_CAPIPERIOD), :yil, :ay_sonu (seçilen ayın ertesi ayının ilk günü),
-- :kod (e-ticaret kanal kodu, varsayılan 'E-TICARET').

-- R1. E-ticaret kanalı net ciro, ay bazında (satır LINENET; iade eksi). Ekran: karnenin «Kanallar arası kıyas» satırı,
--     ay ay yıl içi toplamların farkı. Başlık NETTOTAL ile fark bilgi olarak yazılır (katalogdaki iki tanım).
SELECT MONTH(l.DATE_) AS ay,
       SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net
FROM dbo.LG_:firm_01_STLINE l JOIN dbo.LG_:firm_CLCARD c ON c.LOGICALREF = l.CLIENTREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = :kod
  AND l.DATE_ >= ':yil-01-01' AND l.DATE_ < ':ay_sonu'
GROUP BY MONTH(l.DATE_);

-- R1b. Aynı dönem, fatura başlığı NETTOTAL (bilgi).
SELECT SUM(CASE WHEN i.TRCODE IN (7,8,9) THEN i.NETTOTAL ELSE -i.NETTOTAL END) AS net
FROM dbo.LG_:firm_01_INVOICE i JOIN dbo.LG_:firm_CLCARD c ON c.LOGICALREF = i.CLIENTREF
WHERE i.CANCELLED = 0 AND i.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = :kod AND i.DATE_ >= ':yil-01-01' AND i.DATE_ < ':ay_sonu';

-- R2 + R4. Cari bazında net ciro, brüt kâr (maliyetli satış satırları), maliyetsiz satış satırı sayısı.
--     Ekran: kanal detayındaki «Cariler» tablosu (her platform + eşlenmemiş), marj yetkisiyle.
SELECT c.CODE AS cari,
       SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net,
       SUM(CASE WHEN l.TRCODE IN (7,8,9) AND ISNULL(l.OUTCOST, 0) > 0 THEN l.LINENET - l.AMOUNT * l.OUTCOST ELSE 0 END) AS brut_kar,
       SUM(CASE WHEN l.TRCODE IN (7,8,9) AND ISNULL(l.OUTCOST, 0) <= 0 THEN 1 ELSE 0 END) AS maliyetsiz_satir
FROM dbo.LG_:firm_01_STLINE l JOIN dbo.LG_:firm_CLCARD c ON c.LOGICALREF = l.CLIENTREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = :kod
  AND l.DATE_ >= ':yil-01-01' AND l.DATE_ < ':ay_sonu'
GROUP BY c.CODE;

-- R3. Kanal iade oranı (satır) ve iskonto oranı (satır iskontosu ÷ brüt satış). Katalogdaki iade_orani başlık tanımıdır
--     (NETTOTAL); o da yazılır. Ekran: «Kanallar arası kıyas» satırı.
SELECT SUM(CASE WHEN l.LINETYPE = 0 AND l.TRCODE IN (2,3) THEN l.LINENET ELSE 0 END) AS iade,
       SUM(CASE WHEN l.LINETYPE = 0 AND l.TRCODE IN (7,8,9) THEN l.LINENET ELSE 0 END) AS satis,
       SUM(CASE WHEN l.LINETYPE = 2 AND l.TRCODE IN (7,8,9) THEN l.TOTAL ELSE 0 END) AS iskonto,
       SUM(CASE WHEN l.LINETYPE = 0 AND l.TRCODE IN (7,8,9) THEN l.TOTAL ELSE 0 END) AS brut
FROM dbo.LG_:firm_01_STLINE l JOIN dbo.LG_:firm_CLCARD c ON c.LOGICALREF = l.CLIENTREF
WHERE l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.LINETYPE IN (0, 2) AND l.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = :kod
  AND l.DATE_ >= ':yil-01-01' AND l.DATE_ < ':ay_sonu';

-- R5. CRM satış hedefi, bölge × yıl: 12 ay sütununun toplamı ve new_ToplamHedef (Kural C2 yazımı). Ekran: Cari eşleme →
--     Hedef bölgeleri (yıllık ve aylık toplam).
SELECT new_bolge AS bolge,
       SUM(ISNULL(new_ocak,0) + ISNULL(new_subat,0) + ISNULL(new_Mart,0) + ISNULL(new_Nisan,0) + ISNULL(new_mayis,0)
         + ISNULL(new_Haziran,0) + ISNULL(new_Temmuz,0) + ISNULL(new_agustos,0) + ISNULL(new_eylul,0) + ISNULL(new_Ekim,0)
         + ISNULL(new_kasim,0) + ISNULL(new_aralik,0)) AS aylik_toplam,
       SUM(ISNULL(new_ToplamHedef,0)) AS toplam
FROM Timas_MSCRM.dbo.new_satishedefleriBase WHERE statecode = 0 AND new_yil = :yil_kodu GROUP BY new_bolge;

-- R6. CRM sipariş tipi sayıları, son 180 gün (yenilemeden hemen sonra; aradaki yeni sipariş farkı yazılır).
SELECT new_siparistipi AS tip, COUNT(*) AS sayi FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND new_siparistarihi >= DATEADD(DAY, -180, GETDATE()) GROUP BY new_siparistipi;

-- R7. Eşleme sonrası platform toplamı = eşlenmiş carilerin R2 toplamı (fark 0); eşlenmemiş e-ticaret carileri
--     «Eşlenmemiş» kartında. (Kanal koduyla eşlenen gruplar R1'in kanal koşuluyla ayrıca toplanır.)

-- R8. Kitap × kanal: rastgele 10 kitap için e-ticaret carilerine net adet (satış − iade). Ekran: matris satırının hücre
--     toplamı (platform dışı işaretli cariler hariç).
SELECT i.CODE AS stok, c.CODE AS cari, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.AMOUNT ELSE -l.AMOUNT END) AS net_adet
FROM dbo.LG_:firm_01_STLINE l JOIN dbo.LG_:firm_CLCARD c ON c.LOGICALREF = l.CLIENTREF
JOIN dbo.LG_:firm_ITEMS i ON i.LOGICALREF = l.STOCKREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = :kod
  AND l.DATE_ >= ':yil-01-01' AND l.DATE_ < ':ay_sonu' AND i.CODE IN (:stoklar)
GROUP BY i.CODE, c.CODE;
