-- Stok kodu başına dönemsel satış ve ağırlıklı aylık satış hızı.
-- Havuz 2024 başından bu yana satışı olan kodlardır (Power BI: WHERE Yıl >= 2024).
-- Dönemler tamamlanmış aylardır; içinde bulunulan ay hiçbir döneme girmez.
--   son3   = son 3 ay           (Power BI: Ceyrek1)
--   onc3   = 4-6 ay önce        (Ceyrek2)
--   onc6   = 7-9 ay önce        (Ceyrek3)
--   gecen  = 10-12 ay önce      (Ceyrek4, geçen yılın aynı çeyreği)
--   son6   = son 6 ay           (Ilk6Ay — adı ters)
--   onceki6= 7-12 ay önce       (Son6Ay — adı ters)
WITH d AS (
    SELECT DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0) AS bu_ay
), p AS (
    SELECT bu_ay,
           DATEADD(MONTH, -3,  bu_ay) AS m3,
           DATEADD(MONTH, -6,  bu_ay) AS m6,
           DATEADD(MONTH, -9,  bu_ay) AS m9,
           DATEADD(MONTH, -12, bu_ay) AS m12
    FROM d
)
SELECT
    s.[Malzeme/Hizmet Kodu] AS stok_kodu,
    SUM(CASE WHEN s.[Fatura Tarihi] >= p.m12 AND s.[Fatura Tarihi] < p.bu_ay THEN s.Miktar ELSE 0 END)       AS yillik_toplam,
    SUM(CASE WHEN s.[Fatura Tarihi] >= p.m12 AND s.[Fatura Tarihi] < p.bu_ay THEN s.Miktar ELSE 0 END) / 12.0 AS yillik_ort,
    SUM(CASE WHEN s.[Fatura Tarihi] >= p.m6  AND s.[Fatura Tarihi] < p.bu_ay THEN s.Miktar ELSE 0 END) / 6.0  AS son6_ort,
    SUM(CASE WHEN s.[Fatura Tarihi] >= p.m12 AND s.[Fatura Tarihi] < p.m6    THEN s.Miktar ELSE 0 END) / 6.0  AS onceki6_ort,
    SUM(CASE WHEN s.[Fatura Tarihi] >= p.m3  AND s.[Fatura Tarihi] < p.bu_ay THEN s.Miktar ELSE 0 END) / 3.0  AS ceyrek1_ort,
    SUM(CASE WHEN s.[Fatura Tarihi] >= p.m6  AND s.[Fatura Tarihi] < p.m3    THEN s.Miktar ELSE 0 END) / 3.0  AS ceyrek2_ort,
    SUM(CASE WHEN s.[Fatura Tarihi] >= p.m9  AND s.[Fatura Tarihi] < p.m6    THEN s.Miktar ELSE 0 END) / 3.0  AS ceyrek3_ort,
    SUM(CASE WHEN s.[Fatura Tarihi] >= p.m12 AND s.[Fatura Tarihi] < p.m9    THEN s.Miktar ELSE 0 END) / 3.0  AS ceyrek4_ort
FROM dbo.V_SatisRaporu_All2 AS s
CROSS JOIN p
-- Havuz Power BI ile aynı: 2024 başından bu yana satışı olan her stok kodu bir satırdır.
-- Son 12 ayda satmayan kitap da listede kalır (dönem toplamları 0, hız 0, tükenme yok).
WHERE s.[Yıl] >= 2024
GROUP BY s.[Malzeme/Hizmet Kodu]
