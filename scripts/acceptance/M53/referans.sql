-- M53 Set, hediye ve promosyon — bağımsız referans sorguları (gerçek Logo .25 + CRM .28; yalnız okuma).
-- kabul.py bunları parametreleriyle koşturur; elle denemek için <...> yer tutucularını doldurun.
-- Firma: 411 = 2026, 211 = 2021–2025 (L_CAPIPERIOD). CRM şeması Timas_MSCRM.dbo.

-- R1 · CRM set kartı sayısı (Setler sekmesindeki CRM kaynaklı set sayısı; stok kodu boş kart portala giremez)
SELECT COUNT(*) AS tumu, COUNT(new_StokKodu) AS stok_kodlu
FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_Tip = 4;

-- R2 · Bir setin bileşenleri: en son etkin «Set Yapma» işleminin alt mamul satırları = semantic_mkt_set_items
WITH son AS (
  SELECT TOP 1 si.new_setislemiId AS islem
  FROM Timas_MSCRM.dbo.new_setislemiBase si JOIN Timas_MSCRM.dbo.ProductBase ps ON ps.ProductId = si.new_urunid
  WHERE ps.ProductNumber = N'<set stok kodu>' AND si.statecode = 0 AND si.new_islemtipi = 1
  ORDER BY si.CreatedOn DESC)
SELECT p.ProductNumber AS stok, SUM(sl.new_adet) AS adet
FROM son JOIN Timas_MSCRM.dbo.new_setislemisatiriBase sl ON sl.new_setislemiid = son.islem
JOIN Timas_MSCRM.dbo.ProductBase p ON p.ProductId = sl.new_urunid
WHERE sl.new_tip = 2 AND sl.statecode = 0
GROUP BY p.ProductNumber;

-- R2b · Logo reçetesi (SETS_COMPONENT_SOURCE=logo ya da CRM işlemi olmayan set)
SELECT C.CODE AS bilesen, L.LINETYPE, SUM(L.AMOUNT) AS adet
FROM dbo.LG_411_BOMASTER B JOIN dbo.LG_411_ITEMS M ON M.LOGICALREF = B.MAINPRODREF
JOIN dbo.LG_411_BOMLINE L ON L.BOMMASTERREF = B.LOGICALREF AND L.BOMREVREF = B.VALIDREVREF
JOIN dbo.LG_411_ITEMS C ON C.LOGICALREF = L.ITEMREF
WHERE M.CODE = N'<set stok kodu>' AND B.ACTIVE = 0 AND L.ITEMREF <> B.MAINPRODREF
GROUP BY C.CODE, L.LINETYPE;

-- R3 · Set satışı (yıl): faturalı satır, iade eksi, net ciro = LINENET — semantic_mkt_set_sales toplamı, kuruşu kuruşuna
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS net_adet,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net_ciro
FROM dbo.LG_411_01_STLINE S JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE = N'<set stok kodu>' AND S.CANCELLED = 0 AND S.LINETYPE IN (0) AND S.INVOICEREF <> 0
  AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '2026-01-01' AND S.DATE_ < '2027-01-01';

-- R3b · Veri sonu
SELECT MAX(DATE_) AS son FROM dbo.LG_411_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9);

-- R4 · Liste toplamı: bileşenlerin CRM KDV dahil fiyatı × adet = liste_toplami (SETS_LIST_PRICE_SOURCE=crm)
SELECT new_StokKodu AS stok, new_kdvdahilfiyat AS fiyat FROM Timas_MSCRM.dbo.new_kitapBase
WHERE statecode = 0 AND new_StokKodu IN (N'<bileşen 1>', N'<bileşen 2>');

-- R5 · Birlikte alım çifti: B2C siparişi (tip 8 ya da adı «B2C»), taslak/iptal sipariş, iptal satır ve
--      promosyon/kesin hediye/bedelsiz satırlar hariç; dönem başı semantic_mkt_sets_meta «basket».donem[0]
SELECT COUNT(DISTINCT s.new_siparisId) AS siparis
FROM Timas_MSCRM.dbo.new_siparisBase s
JOIN Timas_MSCRM.dbo.new_siparissatiriBase a ON a.new_siparisid = s.new_siparisId
JOIN Timas_MSCRM.dbo.ProductBase pa ON pa.ProductId = a.new_urunid
JOIN Timas_MSCRM.dbo.new_siparissatiriBase b ON b.new_siparisid = s.new_siparisId
JOIN Timas_MSCRM.dbo.ProductBase pb ON pb.ProductId = b.new_urunid
WHERE (s.new_siparistipi IN (8) OR LEFT(s.new_name, 3) = N'B2C') AND s.statuscode NOT IN (1, 100000001)
  AND pa.ProductNumber = N'<a>' AND pb.ProductNumber = N'<b>' AND s.new_siparistarihi >= '<dönem başı>'
  AND a.statuscode <> 100000001 AND b.statuscode <> 100000001
  AND ISNULL(a.new_promosyon, 0) = 0 AND ISNULL(a.new_kesinhediye, 0) = 0 AND ISNULL(a.new_bedelsiz, 0) = 0
  AND ISNULL(b.new_promosyon, 0) = 0 AND ISNULL(b.new_kesinhediye, 0) = 0 AND ISNULL(b.new_bedelsiz, 0) = 0;

-- R6 · Promosyon ürünleri: 157 kart sayısı ve yılın faturalı net cirosu
SELECT COUNT(*) AS kart FROM dbo.LG_411_ITEMS WHERE CODE LIKE '157%';
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net_ciro
FROM dbo.LG_411_01_STLINE S JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE LIKE '157%' AND S.CANCELLED = 0 AND S.LINETYPE IN (0) AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '2026-01-01' AND S.DATE_ < '2027-01-01';

-- R7 · Marj: bileşenlerin satış KDV oranı (KDV ayrışması) — KDV hariç gelir = Σ set fiyatı × liste payı ÷ (1 + KDV)
SELECT CODE AS stok, SELLVAT AS kdv FROM dbo.LG_411_ITEMS WHERE CODE IN (N'<bileşen 1>', N'<bileşen 2>');

-- Ö3 · Çift sayım ölçümü: set satırı olan faturada aynı setin bileşeninin satırı (kabul.py --olcum, set ↔ bileşen çiftleri CRM'den)
SELECT COUNT(DISTINCT S1.INVOICEREF) AS fatura, SUM(CASE WHEN S2.LINENET = 0 THEN 1 ELSE 0 END) AS sifir_tutarli
FROM dbo.LG_411_01_STLINE S1 JOIN dbo.LG_411_ITEMS I1 ON I1.LOGICALREF = S1.STOCKREF
JOIN dbo.LG_411_01_STLINE S2 ON S2.INVOICEREF = S1.INVOICEREF AND S2.LOGICALREF <> S1.LOGICALREF
JOIN dbo.LG_411_ITEMS I2 ON I2.LOGICALREF = S2.STOCKREF
WHERE I1.CODE = N'<set stok kodu>' AND I2.CODE = N'<bileşen>' AND S1.CANCELLED = 0 AND S2.CANCELLED = 0
  AND S1.INVOICEREF <> 0 AND S1.TRCODE IN (7,8,9) AND S1.DATE_ >= '2026-01-01';
