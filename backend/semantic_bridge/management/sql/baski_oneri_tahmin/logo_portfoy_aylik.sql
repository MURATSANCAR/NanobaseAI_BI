-- Bütün kitapların toplam aylık satışı: yayınevinin büyüme eğilimi. Tahmine "yalnız geçmişte bilinen"
-- ek değişken olarak girer; okul dönemi zirvesinin her yıl büyümesini modelin görmesini sağlar.
SELECT s.[Yıl] AS yil, s.[Ay] AS ay, SUM(s.Miktar) AS miktar
FROM {satis:2015} AS s
GROUP BY s.[Yıl], s.[Ay]
