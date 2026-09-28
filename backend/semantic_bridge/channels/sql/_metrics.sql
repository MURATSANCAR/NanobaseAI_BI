-- Ortak ölçü kolonları: logo_kanal_karne.sql ve logo_eticaret_cari.sql bu parçayı ölçü yer tutucusunun yerine koyar.
-- Satış = faturalı (INVOICEREF <> 0) malzeme satırı (LINETYPE 0), TRCODE 7,8,9; iade = TRCODE 2,3; iptal hariç.
-- İskonto = satır iskontosu (LINETYPE 2) TOTAL'i; brüt satış = malzeme satırının TOTAL'i (iskonto öncesi).
-- Maliyet yalnız maliyeti girilmiş satırlarda (OUTCOST > 0): AMOUNT × OUTCOST; maliyetsiz satır ayrıca sayılır.
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (7,8,9) THEN S.LINENET ELSE 0 END) AS satis_ciro,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (2,3) THEN S.LINENET ELSE 0 END) AS iade_ciro,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE 0 END) AS satis_adet,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (2,3) THEN S.AMOUNT ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (7,8,9) THEN S.TOTAL ELSE 0 END) AS brut_satis,
  SUM(CASE WHEN S.LINETYPE = 2 AND S.TRCODE IN (7,8,9) THEN S.TOTAL ELSE 0 END) AS iskonto,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (7,8,9) AND ISNULL(S.OUTCOST, 0) > 0 THEN S.AMOUNT * S.OUTCOST ELSE 0 END) AS maliyet,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (7,8,9) AND ISNULL(S.OUTCOST, 0) > 0 THEN S.LINENET ELSE 0 END) AS maliyetli_ciro,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (7,8,9) AND ISNULL(S.OUTCOST, 0) <= 0 THEN 1 ELSE 0 END) AS maliyetsiz_satir,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (7,8,9) AND ISNULL(S.OUTCOST, 0) <= 0 THEN S.LINENET ELSE 0 END) AS maliyetsiz_ciro,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (2,3) AND ISNULL(S.OUTCOST, 0) > 0 THEN S.AMOUNT * S.OUTCOST ELSE 0 END) AS iade_maliyet,
  SUM(CASE WHEN S.LINETYPE = 0 AND S.TRCODE IN (2,3) AND ISNULL(S.OUTCOST, 0) > 0 THEN S.LINENET ELSE 0 END) AS iade_maliyetli_ciro
