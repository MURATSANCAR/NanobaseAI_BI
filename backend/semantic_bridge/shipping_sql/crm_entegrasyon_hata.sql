-- M44 Kargo: entegrasyon hatası adayı (crm_siparis_asama.sql'in koşulu). Dört firmadan birinin sonuç ya da mesaj alanı
-- dolu ve siparişte takip no yok; pencere sipariş tarihinden. Sonucun «başarılı» değerleri Python'da ayardan elenir
-- (SHIPPING_INTEGRATION_OK_VALUES; değer kümesi ölçülecek). {haric} = hata sayılmayan durum kodları, {bas} = pencere başı.
ISNULL(s.new_kargotakipno, '') = ''
AND CAST(s.statuscode AS int) NOT IN ({haric})
AND s.new_siparistarihi >= '{bas}'
AND (ISNULL(s.new_araskargoentegrasyonsonucu, '') <> '' OR ISNULL(s.new_upskargoentegrasyonsonucu, '') <> ''
  OR ISNULL(s.new_mngkargoentegrasyonsonucu, '') <> '' OR ISNULL(s.new_akademikargoentegrasyonsonucu, '') <> ''
  OR s.new_araskargoentegrasyonmesaji IS NOT NULL OR s.new_upskargoentegrasyonmesaji IS NOT NULL
  OR ISNULL(s.new_mngkargoentegrasyonmesaji, '') <> '' OR s.new_akademikargoentegrasyonmesaji IS NOT NULL)
