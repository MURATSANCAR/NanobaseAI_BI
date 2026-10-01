-- Aşama 0 (satış modeli tespiti): pazar yeri carisi adayları. Kural (koda sabit ad yok): unvanında Yönetim ayarındaki
-- platform/işletmeci adlarından biri geçen, M42 eşlemesinde bu platforma bağlı (onaylı ya da aday) ya da kanal kodu
-- bu platforma bağlı cariler. {kosul}: bu üç kuralın OR'u; ad eşleşmesi ayrıca Python'da kelime sınırıyla süzülür.
SELECT C.CODE AS cari_kodu, C.DEFINITION_ AS unvan, C.SPECODE2 AS kanal, C.CARDTYPE AS kart_turu
FROM dbo.LG_{firm}_CLCARD AS C
WHERE ({kosul})
