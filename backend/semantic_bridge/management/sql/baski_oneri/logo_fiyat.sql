-- Stok kodu başına güncel fiyat ve o fiyatın ilk görüldüğü tarih (son fiyat değişikliği).
-- `fl` Logo'daki PBI_FiyatList görünümünün tanımıdır ve yalnız tanımdaki yılları (Yıl > 2024) okur.
-- Tek fark yazımda: `Net Tutar > 0` satır süzgeci, sorgu planını bozup 2025'te 300 sn'yi aşırıyordu.
-- Aynı koşul burada gruplamanın içindedir: fiyat yalnız net tutarı pozitif satırlardan alınır ve
-- hiç pozitif satırı olmayan grup düşer. Sonuç aynıdır (2026'da ölçüldü: 24.289 grup, fiyat toplamı eşit).
WITH fl AS (
    SELECT s.[Malzeme/Hizmet Kodu] AS StokKodu, s.[Malzeme/Hizmet Adı] AS StokAdi, s.[Yıl], s.[Ay],
           MAX(CASE WHEN s.[Net Tutar] > 0 THEN s.[Birim Fiyat] END) AS BirimFiyat,
           DATEFROMPARTS(s.[Yıl], s.[Ay], 1) AS DateField
    FROM {satis:2025} AS s
    WHERE s.[Satır Türü] = N'Malzeme'
      AND s.[Satis_Iade] = N'Satış'
      AND s.[Satıcı Kodu] NOT IN (N'CYERLIKAYA')
      AND LEFT(s.[Sipariş Numarası], 3) IN (N'B2B', N'CRM')
    GROUP BY s.[Malzeme/Hizmet Kodu], s.[Malzeme/Hizmet Adı], s.[Yıl], s.[Ay]
    HAVING MAX(CASE WHEN s.[Net Tutar] > 0 THEN 1 END) = 1
), ilk AS (
    SELECT StokKodu, BirimFiyat, MIN(DateField) AS baslangic
    FROM fl
    GROUP BY StokKodu, BirimFiyat
), sirali AS (
    SELECT StokKodu, BirimFiyat, baslangic,
           ROW_NUMBER() OVER (PARTITION BY StokKodu ORDER BY baslangic DESC) AS rn
    FROM ilk
)
SELECT StokKodu AS stok_kodu, BirimFiyat AS birim_fiyat, baslangic AS son_fiyat_degisikligi
FROM sirali
WHERE rn = 1
