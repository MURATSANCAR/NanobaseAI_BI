-- CRM satış hedefleri (Kural C2): bir satır = bir kitabın bir hedef sahibi ve yıl için aylık adet hedefi; aylar sütundur.
-- Hedef sahibi 2023–2024'te bölge (new_bolge: D&R, Hepsiburada, Kitapyurdu, B2C …), 2025'ten beri BMT (new_BMT → CRM
-- kullanıcısı: kanal hesabı «Hepsiburada», «D&R» … ya da satış temsilcisi); bölge boştur. İkisi de okunur, anahtar
-- sources.read_targets'ta kurulur; anahtar ↔ platform eşlemesi portalda onaylanır.
-- {yil_kodu}: new_yil seçim kodu (StringMap'ten okunur; 100000000 = 2026).
SELECT t.new_bolge AS bolge, u.DomainName AS bmt, MAX(u.FullName) AS bmt_ad, COUNT(*) AS satir,
  SUM(ISNULL(t.new_ocak, 0)) AS m1, SUM(ISNULL(t.new_subat, 0)) AS m2, SUM(ISNULL(t.new_Mart, 0)) AS m3,
  SUM(ISNULL(t.new_Nisan, 0)) AS m4, SUM(ISNULL(t.new_mayis, 0)) AS m5, SUM(ISNULL(t.new_Haziran, 0)) AS m6,
  SUM(ISNULL(t.new_Temmuz, 0)) AS m7, SUM(ISNULL(t.new_agustos, 0)) AS m8, SUM(ISNULL(t.new_eylul, 0)) AS m9,
  SUM(ISNULL(t.new_Ekim, 0)) AS m10, SUM(ISNULL(t.new_kasim, 0)) AS m11, SUM(ISNULL(t.new_aralik, 0)) AS m12,
  SUM(ISNULL(t.new_ToplamHedef, 0)) AS toplam
FROM {schema}.new_satishedefleriBase AS t
LEFT JOIN {schema}.SystemUserBase AS u ON u.SystemUserId = t.new_BMT
WHERE t.statecode = 0 AND t.new_yil = {yil_kodu}
GROUP BY t.new_bolge, u.DomainName
