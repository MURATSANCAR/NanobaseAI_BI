-- CRM cari kartı (yalnız okuma): Logo carisine new_logicalref ile bağlanır (%98,6 bağlı). Firma kanalı ve özel kod 2
-- eşleme adayının kanıtıdır. {refs}: Logo LOGICALREF listesi (CRM'de metin).
SELECT a.AccountId AS crm_id, a.Name AS ad, a.new_logicalref AS logicalref, a.new_FirmaKanal AS firma_kanal,
  a.new_cariozelKod2 AS ozel_kod2
FROM {schema}.AccountBase AS a
WHERE a.StateCode = 0 AND a.new_logicalref IN ({refs})
