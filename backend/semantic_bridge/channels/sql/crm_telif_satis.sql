-- M41 satılmış yabancı haklar: etkin Telif Satış sözleşmeleri (new_SozlesmeTipi = 1; TİMAŞ hakkı yurtdışına satar),
-- bağlı kitaplar ve taraf firma (yabancı yayınevi/ajans). Taraf yönü new_yurticiyurtdisi (2 = Yurtdışı Satış). Bir
-- sözleşmenin birden çok kitabı ve tarafı olabilir: satır sözleşme × kitap × taraftır, Python'da sözleşme × kitaba indirilir.
-- Ülke new_telifsatilanulke bir aramadır (kimlik); adı ayrı okunur (crm_ulke), okunamazsa «ülke adı okunamadı» yazar.
SELECT s.new_sozlesmeId AS id, s.new_name AS no, s.new_SozlesmeBaslangicTarihi AS bas, s.new_SozlesmeBitisTarihi AS bit,
  CAST(s.statuscode AS int) AS durum, CAST(s.new_telifsatilanulke AS nvarchar(200)) AS ulke,
  k.new_StokKodu AS stok_kodu, k.new_name AS kitap,
  a.Name AS firma, CAST(t.new_yurticiyurtdisi AS int) AS yon
FROM {schema}new_sozlesmeBase AS s
JOIN {schema}new_new_sozlesme_new_kitapBase AS sk ON sk.new_sozlesmeid = s.new_sozlesmeId
JOIN {schema}new_kitapBase AS k ON k.new_kitapId = sk.new_kitapid
LEFT JOIN {schema}new_sozlesmetarafiBase AS t ON t.new_sozlesmeid = s.new_sozlesmeId AND t.statecode = 0
LEFT JOIN {schema}AccountBase AS a ON a.AccountId = t.new_Firma
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 1
