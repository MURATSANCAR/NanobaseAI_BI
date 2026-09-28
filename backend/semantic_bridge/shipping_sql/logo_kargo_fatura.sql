-- M44 Kargo: kargo firmalarından alınan hizmet faturaları (TRCODE 4), bir ay. Cari kodları ayardan
-- (SHIPPING_LOGO_CARRIER_CODES, insan onaylı eşleme). KDV hariç = NETTOTAL − TOTALVAT.
SELECT C.CODE AS cari, C.DEFINITION_ AS unvan, I.FICHENO AS no, I.DATE_ AS tarih, I.NETTOTAL AS kdv_dahil, I.TOTALVAT AS kdv
FROM dbo.LG_{f}_01_INVOICE I
JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND I.TRCODE = 4 AND C.CODE IN ({cariler}) AND I.DATE_ >= '{bas}' AND I.DATE_ < '{bit}'
