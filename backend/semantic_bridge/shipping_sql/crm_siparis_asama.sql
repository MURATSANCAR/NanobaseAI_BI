-- M44 Kargo: CRM siparişinin aşama tarihleri, kargo firması, takip no, etiket ve dört firmanın entegrasyon sonucu.
-- Yalnız okuma. Kişisel veri (teslimat adresi metni, alıcı adı, telefon) seçilmez; teslimat adresinden yalnız il adı gelir.
-- {p} = CRM şema öneki, {kosul} = Python'da doğrulanmış değerlerle kurulan WHERE parçası, {sira} = ORDER BY, {sayfa} = OFFSET/FETCH.
SELECT s.new_siparisId AS siparis_id, s.new_name AS siparis_no, s.new_siparistarihi AS siparis_tarihi,
  CAST(s.statuscode AS int) AS durum, CAST(s.new_siparistipi AS int) AS tip,
  s.new_DepodaBekliyorDurumu AS depoda_bekliyor, s.new_pusulaalinditarih AS pusula, s.new_sipariskutulanditarihi AS kutulandi,
  s.new_sevktarihi AS sevk_tarihi, s.new_tamamlanditarihi AS tamamlandi,
  s.new_kargofirmasiid AS firma_id, s.new_kargotakipno AS takip_no, s.new_kargotakipurl AS takip_url,
  CAST(s.new_etiketbasildi AS int) AS etiket, s.new_kutuadedi AS kutu, CAST(s.new_kargoodemesekli AS int) AS odeme_sekli,
  s.new_araskargoentegrasyonsonucu AS aras_sonuc, CAST(s.new_araskargoentegrasyonmesaji AS nvarchar(max)) AS aras_mesaj,
  s.new_upskargoentegrasyonsonucu AS ups_sonuc, CAST(s.new_upskargoentegrasyonmesaji AS nvarchar(max)) AS ups_mesaj,
  s.new_mngkargoentegrasyonsonucu AS mng_sonuc, CAST(s.new_mngkargoentegrasyonmesaji AS nvarchar(max)) AS mng_mesaj,
  s.new_akademikargoentegrasyonsonucu AS akademi_sonuc, CAST(s.new_akademikargoentegrasyonmesaji AS nvarchar(max)) AS akademi_mesaj,
  s.new_firmaid AS account_id, a.Name AS musteri, a.new_CariKodu AS cari_kodu, il.new_name AS il
FROM {p}new_siparisBase s
LEFT JOIN {p}AccountBase a ON a.AccountId = s.new_firmaid
LEFT JOIN {p}new_adresBase ad ON ad.new_adresId = s.new_teslimatadresiid
LEFT JOIN {p}new_illerBase il ON il.new_illerId = ad.new_ilid
WHERE s.statecode = 0 AND ({kosul})
{sira}{sayfa}
