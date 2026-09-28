-- M41 listeleme/brief taslağı için kitap kartı (yalnız okuma; M34 içerik paketiyle aynı alanlar). {kod}: stok kodu.
SELECT TOP 1 k.new_name AS ad, k.new_urunadi AS urun_adi, k.new_yazartext AS yazar, k.new_tercumelertext AS cevirmen,
  k.new_sayfasayisi AS sayfa, k.new_webkategorileritext AS kategori, k.new_AnahtarKelimeler AS anahtar_kelime,
  LEFT(k.new_kitapspotu, 2000) AS spot, LEFT(k.new_ozet, 6000) AS arka_kapak, k.new_ean13 AS ean
FROM {schema}new_kitapBase AS k
WHERE k.statecode = 0 AND k.new_StokKodu = {kod}
