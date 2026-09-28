-- M34 E-ticaret — bağımsız referans sorgular (kabul.py bunları kendi koşturur; köprü kodu kullanılmaz).
-- <p> = CRM şeması öneki (Timas_MSCRM.dbo.), <f> = Logo güncel firma (411), <f_i> = yılın firması, :t = tenant.

-- R1 · CRM'de «TSOFT Aktif» (CRM .28). Ekrandaki «CRM'de TSOFT Aktif» = farklı EAN-13 sayısı + EAN'sız işaretli kart.
SELECT COUNT(*) AS kart, COUNT(DISTINCT new_ean13) AS ean,
       SUM(CASE WHEN new_ean13 IS NULL THEN 1 ELSE 0 END) AS eansiz
FROM <p>new_kitapBase WHERE new_tsoftaktif = 1;

-- R2 · «CRM'de aktif, sitede yok»: CRM kümesi eksi sitedeki aktif barkodlar (meta Postgres).
SELECT new_ean13 AS ean FROM <p>new_kitapBase WHERE new_tsoftaktif = 1 AND statecode = 0 AND new_ean13 IS NOT NULL;
SELECT regexp_replace(coalesce(data_json::json->>'Barcode', ''), '[^0-9]', '', 'g') AS ean
FROM semantic_seo_products WHERE tenant_id = :t AND active;

-- R3 · Pazar yeri sell-in (faturalı satır, LINENET; iade eksi), yıl başından Logo kesimine; cari başına.
SELECT C.CODE AS kod,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net
FROM dbo.LG_<f_i>_01_STLINE S JOIN dbo.LG_<f_i>_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE C.SPECODE2 = 'E-TICARET' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0
  AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '<yil>-01-01' AND S.DATE_ < '<kesim+1>'
GROUP BY C.CODE;
-- R3-Ö · Aynı dönem fatura başlığından (NETTOTAL): satır tanımıyla farkı ÖLÇÜM olarak raporlanır.
SELECT C.CODE AS kod, SUM(CASE WHEN I.TRCODE IN (7,8,9) THEN I.NETTOTAL ELSE -I.NETTOTAL END) AS net
FROM dbo.LG_<f_i>_01_INVOICE I JOIN dbo.LG_<f_i>_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND I.TRCODE IN (2,3,7,8,9) AND C.SPECODE2 = 'E-TICARET'
  AND I.DATE_ >= '<yil>-01-01' AND I.DATE_ < '<kesim+1>'
GROUP BY C.CODE;

-- R4 · Logo stok bakiyesi (güncel firma, tarihsiz; planlanan üretim girişi hariç), rastgele 20 stok kodu.
SELECT I.CODE AS stok, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
FROM dbo.LG_<f>_01_STLINE L JOIN dbo.LG_<f>_ITEMS I ON I.LOGICALREF = L.STOCKREF
LEFT JOIN dbo.LG_<f>_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4) AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1)
  AND I.CODE = N'<kod>'
GROUP BY I.CODE;

-- R5 · «Satışta olmaması gereken»: sitede aktif ürün ⨝ CRM kitap kartı (SEO modülünün Haklar tablosu), yayın durumu bayraklı.
SELECT b.status_flag, COUNT(*) AS n
FROM semantic_seo_products p
JOIN semantic_seo_crm_books b ON b.tenant_id = p.tenant_id
 AND b.ean = regexp_replace(coalesce(p.data_json::json->>'Barcode', ''), '[^0-9]', '', 'g')
WHERE p.tenant_id = :t AND p.active AND b.status_flag IN ('bizim_degil','devredildi','geri_istendi','iptal','cekildi')
GROUP BY b.status_flag;

-- R6 · Huni: rastgele 10 ürünün sitedeki sayaçları.
SELECT product_id, data_json::json->>'Barcode' AS barkod, data_json::json->>'StatViews' AS views,
       data_json::json->>'CountTotalSales' AS sales
FROM semantic_seo_products WHERE tenant_id = :t AND active ORDER BY random() LIMIT 10;

-- R7 · Tek pazar yeri carisinin kitap kırılımı (net adet, net ciro), rastgele 10 kitap.
SELECT I.CODE AS stok,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS net_adet,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro
FROM dbo.LG_<f_i>_01_STLINE S JOIN dbo.LG_<f_i>_CLCARD C ON C.LOGICALREF = S.CLIENTREF
JOIN dbo.LG_<f_i>_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE C.CODE = N'<cari>' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '<yil>-01-01' AND S.DATE_ < '<kesim+1>'
GROUP BY I.CODE;

-- R8 · Fiyat farkındaki CRM fiyatı (KDV dahil), rastgele 10 fark.
SELECT new_ean13, new_kdvdahilfiyat FROM <p>new_kitapBase WHERE new_ean13 = N'<ean>' AND statecode = 0;
