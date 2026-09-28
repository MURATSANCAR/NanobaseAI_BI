-- CRM sipariş tipi sayıları, son {days} gün (9 = Pazaryeri, 14 = Amazon Konsinye, 8 = B2C …). Sipariş sayısıdır; tutar
-- Logo'dan okunur. new_firmaid → AccountBase.new_logicalref ile Logo carisine bağlanır.
SELECT o.new_siparistipi AS tip, a.new_logicalref AS logicalref, COUNT(*) AS sayi
FROM {schema}.new_siparisBase AS o
LEFT JOIN {schema}.AccountBase AS a ON a.AccountId = o.new_firmaid
WHERE o.statecode = 0 AND o.new_siparistarihi >= DATEADD(DAY, -{days}, GETDATE())
GROUP BY o.new_siparistipi, a.new_logicalref
