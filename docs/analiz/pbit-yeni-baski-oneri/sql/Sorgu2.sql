-- Tablo: Sorgu2
-- Sunucu: 192.168.0.28  Veritabanı: Timas_MSCRM
-- Kaynak: 2025_Yeni_Baskı Öneri Raporu (5).pbit (Power Query'den çözüldü)

SELECT sm5.Value as Oncelik,S.new_name AS Sip_No,S.new_siparistarihi As SipTarihi, LEFT(S.new_name, 3) AS Kanal,
C.new_CariKodu AS CariKod, C.Name AS Firma,  sm2.Value AS Durum, 
sm3.Value AS SiparişTipi, P.ProductNumber AS StokKodu, 
SS.new_urunidName AS Ürün_Adı, K.new_yayineviidName AS Yayinevi, K.new_yazartext AS Yazar, 
SS.new_adet AS Sip_Adet, 
 SS.new_indirimlitoplamtutar AS NetTutar,S.new_iparaorderid as IparaId  FROM 
	dbo.new_siparis AS S LEFT OUTER JOIN 
	dbo.new_siparissatiri AS SS ON SS.new_siparisid = S.new_siparisId LEFT OUTER JOIN 
	dbo.Account AS C ON S.new_firmaid = C.AccountId LEFT OUTER JOIN dbo.Product AS P ON SS.new_urunid = P.ProductId LEFT OUTER JOIN 
	dbo.StringMap AS sm2 ON sm2.ObjectTypeCode = 10285 AND sm2.LangId = 1055 AND sm2.AttributeName = 'statuscode' AND sm2.AttributeValue = S.statuscode LEFT OUTER JOIN 
	dbo.StringMap AS sm3 ON sm3.ObjectTypeCode = 10285 AND sm3.LangId = 1055 AND sm3.AttributeName = 'new_Siparistipi' AND sm3.AttributeValue = S.new_siparistipi LEFT OUTER JOIN  
	dbo.StringMap AS sm5 ON sm5.ObjectTypeCode = 10285 AND sm5.LangId = 1055 AND sm5.AttributeName = 'new_siparisoncelikdurumu' AND sm5.AttributeValue = S.new_siparisoncelikdurumu LEFT OUTER JOIN 
	dbo.new_kitap AS K ON K.new_StokKodu = P.ProductNumber where sm2.Value not in ('Birleştirildi','Sevk Edildi','Tamamlandı','Etkin değil','İptal Edildi','Taslak') 
	and LEFT(S.new_name, 3) not in ('B2C') and S.new_siparistarihi is not null and C.new_CariKodu not in ('32001.01.PA099','12001.01.C10340')
