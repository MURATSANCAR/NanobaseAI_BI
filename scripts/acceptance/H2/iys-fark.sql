-- H2 · İYS son durum farkı teşhisi (CRM prod .28, yalnız okuma; istek/cevap gövdesi seçilmez).
-- Kabulde (2026-09-28) 6 İYS alanının 4'ünde eski R5 referansı portaldan 1'er fazla çıktı. Farkı yaratabilecek her
-- kayıt sınıfı ayrı listelenir; koordinatör sunucuda koşar, sonucu günlüğe yazar. Şema: Timas_MSCRM.dbo (CRM_SCHEMA).
-- 1 = izin (READERS_IYS_APPROVE_VALUE varsayılanı; ayar farklıysa aşağıdaki «= 1»leri değiştirin).
--
-- Portal kuralı (readers.py, «son kayıt kazanır»): hatasız satır; müşterisi boş satır sayılmaz; her (müşteri, alan) —
-- alan boşsa (müşteri, kanal) — için izin tarihi, sonra oluşturma zamanı en yeni olan; ikisi de eşit ve durumu farklıysa
-- ret. Tarih sınırı yok (bütün geçmiş); durum 1 = onay, geri kalan her şey (NULL dahil) = ret.

-- F1 · Müşterisi boş hatasız satırlar, alan başına. Eski R5 bunların hepsini alan başına TEK bir «NULL müşteri» bölmesinde
--      sayıyordu (ROW_NUMBER NULL'ları bir bölmeye koyar) → her satırı olan alanda tam +1. Beklenen: fark olan 4 alan burada.
SELECT g.obs_iysintegrationfieldid AS alan, COUNT(*) AS satir,
       SUM(CASE WHEN CAST(g.obs_permissionstatus AS int) = 1 THEN 1 ELSE 0 END) AS onay_satiri,
       MIN(g.CreatedOn) AS ilk, MAX(g.CreatedOn) AS son
FROM Timas_MSCRM.dbo.obs_iyslogBase g
WHERE ISNULL(g.obs_iserror, 0) = 0 AND g.obs_customerid IS NULL
GROUP BY g.obs_iysintegrationfieldid
ORDER BY alan;

-- F1b · Aynı satırların kendisi (kimlik, alan, kanal, durum, zaman).
SELECT g.obs_iyslogId AS id, g.obs_iysintegrationfieldid AS alan, CAST(g.obs_channel AS int) AS kanal,
       CAST(g.obs_permissionstatus AS int) AS durum, g.obs_permissiondate AS izin_tarihi, g.CreatedOn AS olusturma
FROM Timas_MSCRM.dbo.obs_iyslogBase g
WHERE ISNULL(g.obs_iserror, 0) = 0 AND g.obs_customerid IS NULL
ORDER BY alan, olusturma;

-- F2 · «Son kayıt» belirsiz: aynı (müşteri, alan) için en yeni izin tarihi ve oluşturma zamanı birebir aynı, durumu
--      farklı satırlar. Eski R5 keyfî seçerdi (koşudan koşuya değişebilir); portal ve yeni R5'te ret kazanır.
WITH s AS (
  SELECT g.obs_customerid, g.obs_iysintegrationfieldid, g.obs_permissiondate, g.CreatedOn,
         ISNULL(CAST(g.obs_permissionstatus AS int), -1) AS durum,
         RANK() OVER (PARTITION BY g.obs_customerid, g.obs_iysintegrationfieldid
                      ORDER BY g.obs_permissiondate DESC, g.CreatedOn DESC) rk
  FROM Timas_MSCRM.dbo.obs_iyslogBase g
  WHERE ISNULL(g.obs_iserror, 0) = 0 AND g.obs_customerid IS NOT NULL)
SELECT obs_customerid AS musteri, obs_iysintegrationfieldid AS alan, obs_permissiondate AS izin_tarihi, CreatedOn AS olusturma,
       COUNT(*) AS satir, MIN(durum) AS durum_min, MAX(durum) AS durum_max
FROM s WHERE rk = 1
GROUP BY obs_customerid, obs_iysintegrationfieldid, obs_permissiondate, CreatedOn
HAVING COUNT(DISTINCT durum) > 1
ORDER BY alan, musteri;

-- F3 · Alanı boş satırlar (portal bunları kanal numarasıyla gruplar: «kanal:<no>»).
SELECT CAST(g.obs_channel AS int) AS kanal, COUNT(*) AS satir, COUNT(DISTINCT g.obs_customerid) AS musteri
FROM Timas_MSCRM.dbo.obs_iyslogBase g
WHERE ISNULL(g.obs_iserror, 0) = 0 AND g.obs_iysintegrationfieldid IS NULL
GROUP BY CAST(g.obs_channel AS int);

-- F4 · İzin tarihi boş satırlar: sıra oluşturma zamanına düşer (iki tarafta aynı; bilgi için).
SELECT g.obs_iysintegrationfieldid AS alan, COUNT(*) AS satir
FROM Timas_MSCRM.dbo.obs_iyslogBase g
WHERE ISNULL(g.obs_iserror, 0) = 0 AND g.obs_permissiondate IS NULL
GROUP BY g.obs_iysintegrationfieldid;

-- F5 · Alan başına eski R5 / yeni R5 (= portal kuralı) onay-ret sayıları ve fark. Yeni sütunlar portalın
--      «iysLatest» değerleriyle birebir olmalı; eski − yeni farkı F1 (+ F2'deki ret/onay yer değişimi) ile açıklanmalı.
WITH eski AS (
  SELECT g.obs_iysintegrationfieldid AS alan, CAST(g.obs_permissionstatus AS int) AS durum,
         ROW_NUMBER() OVER (PARTITION BY g.obs_customerid, g.obs_iysintegrationfieldid
                            ORDER BY g.obs_permissiondate DESC, g.CreatedOn DESC) rn
  FROM Timas_MSCRM.dbo.obs_iyslogBase g WHERE ISNULL(g.obs_iserror, 0) = 0),
yeni AS (
  SELECT g.obs_iysintegrationfieldid AS alan, CAST(g.obs_permissionstatus AS int) AS durum,
         ROW_NUMBER() OVER (PARTITION BY g.obs_customerid, g.obs_iysintegrationfieldid,
                                         CASE WHEN g.obs_iysintegrationfieldid IS NULL THEN CAST(g.obs_channel AS int) END
                            ORDER BY g.obs_permissiondate DESC, g.CreatedOn DESC,
                                     CASE WHEN CAST(g.obs_permissionstatus AS int) = 1 THEN 0 ELSE 1 END DESC) rn
  FROM Timas_MSCRM.dbo.obs_iyslogBase g WHERE ISNULL(g.obs_iserror, 0) = 0 AND g.obs_customerid IS NOT NULL),
e AS (SELECT ISNULL(CONVERT(varchar(36), alan), '(boş)') AS alan,
             SUM(CASE WHEN durum = 1 THEN 1 ELSE 0 END) AS onay, SUM(CASE WHEN durum = 1 THEN 0 ELSE 1 END) AS ret
      FROM eski WHERE rn = 1 GROUP BY ISNULL(CONVERT(varchar(36), alan), '(boş)')),
y AS (SELECT ISNULL(CONVERT(varchar(36), alan), '(boş)') AS alan,
             SUM(CASE WHEN durum = 1 THEN 1 ELSE 0 END) AS onay, SUM(CASE WHEN durum = 1 THEN 0 ELSE 1 END) AS ret
      FROM yeni WHERE rn = 1 GROUP BY ISNULL(CONVERT(varchar(36), alan), '(boş)'))
SELECT COALESCE(e.alan, y.alan) AS alan, e.onay AS eski_onay, e.ret AS eski_ret, y.onay AS yeni_onay, y.ret AS yeni_ret,
       ISNULL(e.onay, 0) + ISNULL(e.ret, 0) - ISNULL(y.onay, 0) - ISNULL(y.ret, 0) AS toplam_fark
FROM e FULL JOIN y ON y.alan = e.alan
ORDER BY alan;
