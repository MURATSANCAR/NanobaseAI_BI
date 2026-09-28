-- M44 Kargo: kargo firması olabilecek cariler (eşleme önerisi; insan onaylar, ayara yazar). Son 12 ayda alınan hizmet
-- faturası (TRCODE 4) olan ve ünvanında ipucu sözcüklerinden biri geçen cariler. İpuçları ayardan (SHIPPING_LOGO_CARRIER_HINTS)
-- ve CRM kargo firması adlarından; {kosul} = LIKE listesi.
SELECT C.CODE AS cari, C.DEFINITION_ AS unvan, COUNT(*) AS fatura, SUM(I.NETTOTAL - I.TOTALVAT) AS kdv_haric, MAX(I.DATE_) AS son
FROM dbo.LG_{f}_01_INVOICE I
JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND I.TRCODE = 4 AND I.DATE_ >= '{bas}' AND ({kosul})
GROUP BY C.CODE, C.DEFINITION_
