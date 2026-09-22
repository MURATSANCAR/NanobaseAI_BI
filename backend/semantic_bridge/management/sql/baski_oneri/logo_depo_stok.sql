-- Logo depo stoku; 157 ile başlayan kodlar (ticari ürün) hariç.
SELECT [STOK KODU] AS stok_kodu, SUM([MİKTAR]) AS depo_stok
FROM dbo.EOS_DEPO_STOK_KONTROL_211
WHERE [STOK KODU] NOT LIKE '157%'
GROUP BY [STOK KODU]
