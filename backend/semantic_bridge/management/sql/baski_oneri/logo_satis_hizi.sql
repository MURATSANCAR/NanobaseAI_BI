-- Stok kodu başına dönemsel satış ve ağırlıklı aylık satış hızı.
-- Havuz 2024 başından bu yana satışı olan kodlardır (Power BI: WHERE Yıl >= 2024); kaynak 2024'ten bu
-- yıla yıllık satış görünümleri (V_SatisRaporu_ALL2 ile aynı satırlar, yalnız bu yıllar).
-- Dönemler tamamlanmış aylardır; içinde bulunulan ay hiçbir döneme girmez.
--   son3   = son 3 ay           (Power BI: Ceyrek1)
--   onc3   = 4-6 ay önce        (Ceyrek2)
--   onc6   = 7-9 ay önce        (Ceyrek3)
--   gecen  = 10-12 ay önce      (Ceyrek4, geçen yılın aynı çeyreği)
--   son6   = son 6 ay           (Ilk6Ay — adı ters)
--   onceki6= 7-12 ay önce       (Son6Ay — adı ters)
-- Dönem, görünümün Yıl/Ay kolonlarından ay sırasıyla seçilir (i = Yıl*12 + Ay - 1). Fatura tarihiyle
-- aralık karşılaştırması aynı satırları verir ama sorgu planını bozup süreyi katlıyordu.
WITH p AS (
    SELECT YEAR(GETDATE()) * 12 + MONTH(GETDATE()) - 1 AS bu_ay
)
SELECT
    s.[Malzeme/Hizmet Kodu] AS stok_kodu,
    SUM(CASE WHEN m.i >= p.bu_ay - 12 AND m.i < p.bu_ay     THEN s.Miktar ELSE 0 END)        AS yillik_toplam,
    SUM(CASE WHEN m.i >= p.bu_ay - 12 AND m.i < p.bu_ay     THEN s.Miktar ELSE 0 END) / 12.0 AS yillik_ort,
    SUM(CASE WHEN m.i >= p.bu_ay - 6  AND m.i < p.bu_ay     THEN s.Miktar ELSE 0 END) / 6.0  AS son6_ort,
    SUM(CASE WHEN m.i >= p.bu_ay - 12 AND m.i < p.bu_ay - 6 THEN s.Miktar ELSE 0 END) / 6.0  AS onceki6_ort,
    SUM(CASE WHEN m.i >= p.bu_ay - 3  AND m.i < p.bu_ay     THEN s.Miktar ELSE 0 END) / 3.0  AS ceyrek1_ort,
    SUM(CASE WHEN m.i >= p.bu_ay - 6  AND m.i < p.bu_ay - 3 THEN s.Miktar ELSE 0 END) / 3.0  AS ceyrek2_ort,
    SUM(CASE WHEN m.i >= p.bu_ay - 9  AND m.i < p.bu_ay - 6 THEN s.Miktar ELSE 0 END) / 3.0  AS ceyrek3_ort,
    SUM(CASE WHEN m.i >= p.bu_ay - 12 AND m.i < p.bu_ay - 9 THEN s.Miktar ELSE 0 END) / 3.0  AS ceyrek4_ort
FROM {satis:2024} AS s
CROSS APPLY (SELECT s.[Yıl] * 12 + s.[Ay] - 1 AS i) AS m
CROSS JOIN p
-- Havuz Power BI ile aynı: 2024 başından bu yana satışı olan her stok kodu bir satırdır.
-- Son 12 ayda satmayan kitap da listede kalır (dönem toplamları 0, hız 0, tükenme yok).
GROUP BY s.[Malzeme/Hizmet Kodu]
