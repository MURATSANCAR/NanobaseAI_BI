-- Stok kodu başına güncel fiyat ve o fiyatın ilk görüldüğü tarih (son fiyat değişikliği).
WITH ilk AS (
    SELECT StokKodu, BirimFiyat, MIN(DateField) AS baslangic
    FROM dbo.PBI_FiyatList
    GROUP BY StokKodu, BirimFiyat
), sirali AS (
    SELECT StokKodu, BirimFiyat, baslangic,
           ROW_NUMBER() OVER (PARTITION BY StokKodu ORDER BY baslangic DESC) AS rn
    FROM ilk
)
SELECT StokKodu AS stok_kodu, BirimFiyat AS birim_fiyat, baslangic AS son_fiyat_degisikligi
FROM sirali
WHERE rn = 1
