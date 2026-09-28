-- M41 ülke adları: Telif Satış sözleşmesindeki «Telif Satılan Ülke» aramasının hedef tablosu (Yönetim ayarı
-- AMAZON_ULKE_TABLOSU; varsayılan new_ulke → new_ulkeBase, kimlik new_ulkeId, ad new_name). Tablo adı ölçülecek.
SELECT CAST(u.{entity}Id AS nvarchar(200)) AS id, u.new_name AS ad
FROM {schema}{entity}Base AS u
