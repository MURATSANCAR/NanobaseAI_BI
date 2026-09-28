-- M44 Kargo: kargo firmasının gönderi kaydı (Kural C19). Bütün kolonlar metindir (ondalık virgül; tarih biçimi ölçülecek):
-- sayı ve tarih Python'da okunur, okunamayan kayıt sayılır ve ekranda yazılır. Alıcı, gönderici, teslim alan ve adres
-- kolonları burada yok; {kisisel} yalnız `ozellik:kargo.alici` olan kişinin tek gönderi kartında doldurulur.
SELECT b.new_kargobilgisiId AS id, b.new_KargoTakipNo AS takip_no, b.new_musteriirsno AS musteri_irs_no,
  b.new_kargoirsno AS kargo_irs_no, b.new_kargofirmasi AS firma, b.new_sevkiyatcikissubesi AS cikis_sube,
  b.new_sevkiyatvarissubesi AS varis_sube, b.new_alicisehir AS sehir, b.new_kargoirstarihi AS irs_tarihi,
  b.new_TeslimTarihi AS teslim_tarihi, b.new_teslimsaati AS teslim_saati, b.new_iadedurumu AS iade_durumu,
  b.new_tahsilatlikargo AS tahsilatli, b.new_sevkadeti AS sevk_adeti, b.new_desi AS desi, b.new_agirlik AS agirlik,
  b.new_Tutar AS tutar, b.new_satiskanali AS kanal, b.CreatedOn AS olusturma{kisisel}
FROM {p}new_kargobilgisiBase b
WHERE b.statecode = 0{kosul}
