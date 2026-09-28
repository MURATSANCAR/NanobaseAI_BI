-- M35 E-ticaret kampanya yönetimi: bağımsız referans sorguları (kabul.py ile aynı; elle denetim için).
-- Yalnız okuma. {FIRM} = güncel yılın Logo firması (L_CAPIPERIOD; 2026 = 411), {YIL} = veri sonu yılı, {KOD} = stok kodu.

-- 1) Kitap marjı (Logo brüt farkı), satış satırları — ekranda «Logo gerçekleşen», kitap tablosunda ciro_yil − maliyet_yil
SELECT SUM(s.LINENET) - SUM(s.AMOUNT * s.OUTCOST) AS brut_fark
FROM dbo.LG_{FIRM}_01_STLINE s JOIN dbo.LG_{FIRM}_ITEMS it ON it.LOGICALREF = s.STOCKREF
WHERE it.CODE = N'{KOD}' AND s.TRCODE IN (7,8,9) AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0
  AND YEAR(s.DATE_) = {YIL};

-- 2) Maliyeti girilmemiş satış satırı — ekrandaki «Logo'da bu yıl N satış satırında maliyet girilmemiş»
SELECT COUNT(*) AS maliyetsiz
FROM dbo.LG_{FIRM}_01_STLINE s JOIN dbo.LG_{FIRM}_ITEMS it ON it.LOGICALREF = s.STOCKREF
WHERE it.CODE = N'{KOD}' AND s.TRCODE IN (7,8,9) AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0
  AND s.OUTCOST = 0 AND YEAR(s.DATE_) = {YIL};

-- 3) Satış hızı: son N ayın (veri sonu ayı dahil) net adedi; {ILK}..{SON} = Yıl*12+Ay-1 penceresi, her yıl kendi firmasından
SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT ELSE -s.AMOUNT END) AS net_adet
FROM dbo.LG_{FIRM_Y}_01_STLINE s JOIN dbo.LG_{FIRM_Y}_ITEMS it ON it.LOGICALREF = s.STOCKREF
WHERE it.CODE = N'{KOD}' AND s.TRCODE IN (2,3,7,8,9) AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0
  AND YEAR(s.DATE_) = {Y} AND YEAR(s.DATE_) * 12 + MONTH(s.DATE_) - 1 BETWEEN {ILK} AND {SON};

-- 4) CRM bayi kampanyaları — «CRM bayi kampanyaları» sekmesi (sayı ve ilk 20 satır)
SELECT COUNT(*) FROM dbo.new_kampanyaBase WHERE statecode = 0;
SELECT TOP 20 new_kampanyaId, new_name, new_baslangictarihi, new_bitistarihi, new_kampanyamecra, new_netiskonto
FROM dbo.new_kampanyaBase WHERE statecode = 0 ORDER BY new_baslangictarihi DESC, new_name;

-- 5) Kampanya kodlu sipariş satırları (ölçüm) ve kampanyaya bağlı satırlar (sekmedeki «etki»)
SELECT new_kampanyakodu, COUNT(*), SUM(new_kampanyaindirimtutari) FROM dbo.new_siparissatiriBase
WHERE new_kampanyakodu IS NOT NULL AND new_kampanyakodu <> '' GROUP BY new_kampanyakodu;
SELECT new_kampanyaid, COUNT(*) AS satir, COUNT(DISTINCT new_siparisid) AS siparis, SUM(new_adet) AS adet,
  SUM(new_kampanyaindirimtutari) AS indirim, SUM(new_indirimlitoplamtutar) AS tutar
FROM dbo.new_siparissatiriBase WHERE new_kampanyaid IS NOT NULL GROUP BY new_kampanyaid;

-- 6) Özel gün bağı (2026-09-27: ~820 bağ) ve bağlı, barkodlu, stok kodlu kitap sayısı
SELECT COUNT(*) FROM dbo.new_new_kitap_new_ozelgunlerBase;
SELECT COUNT(DISTINCT k.new_StokKodu) FROM dbo.new_new_kitap_new_ozelgunlerBase l
JOIN dbo.new_kitapBase k ON k.new_kitapId = l.new_kitapid
WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL AND k.new_ean13 IS NOT NULL;

-- 7) Asgari perakende fiyat: yürürlükteki Telif Alış sözleşmelerinde (metin alan; en büyüğü alt sınırdır)
SELECT s.new_MinimumPerakendeSatFiyat
FROM dbo.new_new_sozlesme_new_kitapBase sk
JOIN dbo.new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid
JOIN dbo.new_kitapBase k ON k.new_kitapId = sk.new_kitapid
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND s.statuscode IN (100000000, 100000006, 100000007)
  AND k.statecode = 0 AND k.new_StokKodu = N'{KOD}';

-- 8) Stok bakiyesi (güncel yıl kopyası, tarihsiz)
SELECT SUM(CASE WHEN s.IOCODE IN (1,2) THEN s.AMOUNT ELSE -s.AMOUNT END)
FROM dbo.LG_{FIRM}_01_STLINE s JOIN dbo.LG_{FIRM}_ITEMS it ON it.LOGICALREF = s.STOCKREF
WHERE it.CODE = N'{KOD}' AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.IOCODE IN (1,2,3,4);
