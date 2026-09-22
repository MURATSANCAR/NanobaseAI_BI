-- Açık sipariş satırları, stok kodu başına bekleyen adet.
-- Kapanmış durumlar, B2C kanalı, tarihsiz siparişler ve iki iç cari hariç.
SELECT p.ProductNumber AS stok_kodu, SUM(ss.new_adet) AS bekleyen_siparis
FROM Timas_MSCRM.dbo.new_siparis AS s
LEFT JOIN Timas_MSCRM.dbo.new_siparissatiri AS ss ON ss.new_siparisid = s.new_siparisId
LEFT JOIN Timas_MSCRM.dbo.Account AS c ON s.new_firmaid = c.AccountId
LEFT JOIN Timas_MSCRM.dbo.Product AS p ON ss.new_urunid = p.ProductId
LEFT JOIN Timas_MSCRM.dbo.StringMap AS sm ON sm.ObjectTypeCode = 10285 AND sm.LangId = 1055
      AND sm.AttributeName = 'statuscode' AND sm.AttributeValue = s.statuscode
WHERE sm.Value NOT IN (N'Birleştirildi', N'Sevk Edildi', N'Tamamlandı', N'Etkin değil', N'İptal Edildi', N'Taslak')
  AND LEFT(s.new_name, 3) <> 'B2C'
  AND s.new_siparistarihi IS NOT NULL
  AND c.new_CariKodu NOT IN ('32001.01.PA099', '12001.01.C10340')
GROUP BY p.ProductNumber
