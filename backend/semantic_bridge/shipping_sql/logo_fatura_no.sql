-- M44 Kargo: CRM sevkiyatındaki fatura numaraları Logo'da (gönderi kartı: sevk Logo'da gerçekleşti mi). Satış 7/8/9.
SELECT I.FICHENO AS no, I.DATE_ AS tarih, I.TRCODE AS tur
FROM dbo.LG_{f}_01_INVOICE I
WHERE I.CANCELLED = 0 AND I.TRCODE IN (7,8,9) AND I.FICHENO IN ({numaralar})
