-- M44 Kargo maliyeti: satış irsaliyeleri (TRCODE 7, 8; iptal hariç) ay × taşıyıcı kodu (SHPAGNCOD) sayısı. Kod köprüde
-- sadeleşir (harf büyüklüğü, Türkçe harf); boş kod = mağaza kasa satışı, kargo yok (gönderi sayılmaz).
SELECT MONTH(F.DATE_) AS ay, F.SHPAGNCOD AS kod, COUNT(*) AS irsaliye, MAX(F.DATE_) AS son
FROM dbo.LG_{f}_01_STFICHE F
WHERE F.CANCELLED = 0 AND F.TRCODE IN (7,8) AND F.DATE_ >= '{bas}' AND F.DATE_ < '{bit}'
GROUP BY MONTH(F.DATE_), F.SHPAGNCOD
