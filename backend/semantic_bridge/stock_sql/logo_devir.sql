-- Stok devir hızı — katalogdaki sertifikalı ölçünün birebir ifadesi (metrics/logo-timas.md, iş kararı 2026-09-20):
-- dönem satış adedi ÷ ortalama stok; ortalama stok = (açılış devri TRCODE 14 + güncel bakiye) / 2. Yalnız güncel kopya.
-- Koşullu toplamlar ELSE'siz yazılır: devir satırı ya da satış yoksa sonuç boş kalır (ölçüyle aynı davranış).
SELECT I.CODE AS stok_kodu,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT END) AS satis_adet,
  SUM(CASE WHEN L.TRCODE = 14 THEN L.AMOUNT END) AS acilis,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT END)
    / NULLIF((SUM(CASE WHEN L.TRCODE = 14 THEN L.AMOUNT END)
              + SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT WHEN L.IOCODE IN (3,4) THEN -L.AMOUNT END)) / 2.0, 0) AS devir_hizi
FROM dbo.LG_{firma}_01_STLINE AS L
JOIN dbo.LG_{firma}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0
GROUP BY I.CODE
