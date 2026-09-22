-- Tablo: Logo_FiyatList
-- Sunucu: 192.168.0.25  Veritabanı: LOGO_DB
-- Kaynak: 2025_Yeni_Baskı Öneri Raporu (5).pbit (Power Query'den çözüldü)

WITH MinValues AS (
    SELECT StokKodu, BirimFiyat, MIN(DateField) AS MinDateField
    FROM PBI_FiyatList
    GROUP BY StokKodu, BirimFiyat
),
SortedMinValues AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY StokKodu ORDER BY MinDateField DESC) AS RowNum
    FROM MinValues
)
SELECT *
FROM SortedMinValues
WHERE RowNum = 1
ORDER BY StokKodu ASC, BirimFiyat DESC;
