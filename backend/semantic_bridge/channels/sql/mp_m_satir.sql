-- Aşama 1: eşleşen / pazar yeri carisine kesilen faturaların satırları. Malzeme satırı (LINETYPE 0) kitap kodu ve adetle,
-- hizmet satırı (LINETYPE 4) hizmet kartıyla (kesinti kalemi). Tutar LINENET (KDV hariç net). {refs}: fatura kimlikleri.
SELECT S.INVOICEREF AS fatura, S.LINETYPE AS satir_turu, I.CODE AS stok_kodu, SV.CODE AS hizmet_kodu,
  SV.DEFINITION_ AS hizmet, S.AMOUNT AS adet, S.LINENET AS tutar
FROM dbo.LG_{firm}_01_STLINE AS S
LEFT JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF AND S.LINETYPE = 0
LEFT JOIN dbo.LG_{firm}_SRVCARD AS SV ON SV.LOGICALREF = S.STOCKREF AND S.LINETYPE = 4
WHERE S.CANCELLED = 0 AND S.LINETYPE IN (0, 4) AND S.INVOICEREF IN ({refs})
