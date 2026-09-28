-- CRM satış hedefleri (Kural C2): bir satır = bir kitabın bir bölge ve yıl için aylık adet hedefi; aylar sütundur.
-- Bölge (new_bolge) kanal karşılığıdır (D&R, Hepsiburada, Kitapyurdu, B2C …); bölge ↔ platform eşlemesi portalda onaylanır.
-- {yil_kodu}: new_yil seçim kodu (StringMap'ten okunur; 100000000 = 2026).
SELECT t.new_bolge AS bolge, COUNT(*) AS satir,
  SUM(ISNULL(t.new_ocak, 0)) AS m1, SUM(ISNULL(t.new_subat, 0)) AS m2, SUM(ISNULL(t.new_Mart, 0)) AS m3,
  SUM(ISNULL(t.new_Nisan, 0)) AS m4, SUM(ISNULL(t.new_mayis, 0)) AS m5, SUM(ISNULL(t.new_Haziran, 0)) AS m6,
  SUM(ISNULL(t.new_Temmuz, 0)) AS m7, SUM(ISNULL(t.new_agustos, 0)) AS m8, SUM(ISNULL(t.new_eylul, 0)) AS m9,
  SUM(ISNULL(t.new_Ekim, 0)) AS m10, SUM(ISNULL(t.new_kasim, 0)) AS m11, SUM(ISNULL(t.new_aralik, 0)) AS m12,
  SUM(ISNULL(t.new_ToplamHedef, 0)) AS toplam
FROM {schema}.new_satishedefleriBase AS t
WHERE t.statecode = 0 AND t.new_yil = {yil_kodu}
GROUP BY t.new_bolge
