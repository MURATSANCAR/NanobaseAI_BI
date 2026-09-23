-- Stok kodu başına güncel fiyat ve o fiyatın ilk görüldüğü tarih (son fiyat değişikliği).
-- `fl` Logo'daki PBI_FiyatList görünümünün tanımıdır, birebir: o görünüm V_SatisRaporu_ALL2'nin
-- on iki yılını taradığı için 900 sn'de bitmiyordu. Burada yalnız tanımdaki yıllar (Yıl > 2024) okunur.
WITH fl AS (
    SELECT s.[Malzeme/Hizmet Kodu] AS StokKodu, s.[Malzeme/Hizmet Adı] AS StokAdi, s.[Yıl], s.[Ay],
           MAX(s.[Birim Fiyat]) AS BirimFiyat,
           DATEFROMPARTS(s.[Yıl], s.[Ay], 1) AS DateField
    FROM {satis:2025} AS s
    WHERE s.[Satır Türü] = N'Malzeme'
      AND s.[Satis_Iade] = N'Satış'
      AND s.[Net Tutar] > 0
      AND s.[Satıcı Kodu] NOT IN (N'CYERLIKAYA')
      AND LEFT(s.[Sipariş Numarası], 3) IN (N'B2B', N'CRM')
    GROUP BY s.[Malzeme/Hizmet Kodu], s.[Malzeme/Hizmet Adı], s.[Yıl], s.[Ay]
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
