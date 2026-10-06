-- Logo depo stoku (Baskı Öneri ile aynı görünüm): ilk satış takibindeki kitapların elde kalanı.
SELECT [STOK KODU] AS stok_kodu, SUM([MİKTAR]) AS depo_stok
FROM dbo.EOS_DEPO_STOK_KONTROL_211
WHERE [STOK KODU] NOT LIKE '157%'
GROUP BY [STOK KODU]
