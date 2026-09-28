-- M39 Pazar araştırması ve rekabet — bağımsız referans sorguları (yalnız okuma).
-- kabul.py bunları aynı CRM (.28, Timas_MSCRM) ve Logo bağlantısında koşturur; portalın tablolarındaki (ekrana giden)
-- değerle karşılaştırır. Uygulamanın SQL'i yeniden koşturulmaz. <P> = CRM şema öneki (Timas_MSCRM.dbo.),
-- <F> = yılın Logo firması (L_CAPIPERIOD), <Y> = yıl, <CUT> = veri sonunun ertesi günü o yılda (aynı dönem).

-- R1 · Rakip katalog ve tazelik (K1) — analiz §14 kabul 1
SELECT COUNT(*) AS kayit, MIN(CreatedOn) AS ilk, MAX(CreatedOn) AS son_ekleme, MAX(ModifiedOn) AS son_degisme
FROM <P>new_rakipkitapBase WHERE statecode = 0;

-- R2 · Yayınevi fiyat bandı (K2) — analiz §14 kabul 2 (fiyatı 0/boş kayıt girmez)
SELECT DISTINCT new_Yaynevi AS yayinevi,
  COUNT(*) OVER (PARTITION BY new_Yaynevi) AS fiyatli,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY new_ListeFiyat) OVER (PARTITION BY new_Yaynevi) AS medyan,
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY new_ListeFiyat) OVER (PARTITION BY new_Yaynevi) AS q1,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY new_ListeFiyat) OVER (PARTITION BY new_Yaynevi) AS q3
FROM <P>new_rakipkitapBase WHERE statecode = 0 AND new_ListeFiyat > 0 AND new_Yaynevi IN (<5 yayınevi>);

-- R3 · TİMAŞ fiyat bandı (K3) — analiz §14 kabul 3; Tip 1 = kitap (set/dergi/e-kitap hariç, portal ile aynı)
SELECT DISTINCT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY new_kdvdahilfiyat) OVER () AS medyan, COUNT(*) OVER () AS n
FROM <P>new_kitapBase WHERE statecode = 0 AND new_Tip = 1 AND new_kdvdahilfiyat > 0 [AND new_kitaplikid = '<kitaplık>'];

-- R4 · Emsal bağı (K4) — analiz §14 kabul 4 (katalogda 214)
SELECT COUNT(*) AS bag, COUNT(DISTINCT CONCAT(new_kitapid, '|', new_rakipkitapid)) AS tekil
FROM <P>new_new_kitap_new_rakipkitapBase;

-- R5 · Yayınevi (marka) cirosu, aynı dönem (K5) — faturalı satır, iade eksi, LINENET
SELECT COALESCE(NULLIF(I.SPECODE, ''), '(boş)') AS yayinevi,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net_ciro,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS net_adet
FROM dbo.LG_<F>_01_STLINE S JOIN dbo.LG_<F>_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '<Y>-01-01' AND S.DATE_ < '<CUT>'
GROUP BY COALESCE(NULLIF(I.SPECODE, ''), '(boş)');
-- Ölçüm: kayıtlı SQL «yay-nevi-baz-nda-2026-ytd-net-ciro…» (TOTAL, faturasız irsaliye dahil, TRCODE 9 yok) aynı dönemde
-- ayrıca koşturulur ve farkı kayda geçer; portal katalog tanımını (LINENET, faturalı) kullanır.

-- R6 · Kanal payı (K6) — pay paydası bütün kanalların net cirosu
SELECT COALESCE(NULLIF(C.SPECODE2, ''), '(boş)') AS kanal,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net_ciro
FROM dbo.LG_<F>_01_STLINE S LEFT JOIN dbo.LG_<F>_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '<Y>-01-01' AND S.DATE_ < '<CUT>'
GROUP BY COALESCE(NULLIF(C.SPECODE2, ''), '(boş)');
-- Ölçüm: kayıtlı SQL «2026-y-l-nda-kitapci-e-ticaret…» fatura başlığı NETTOTAL ile; fark kayda geçer.

-- R7 · Onaylı eşlemenin kayıt sayısı (K9)
SELECT COUNT(*) AS kayit FROM <P>new_rakipkitapBase WHERE statecode = 0 AND new_Kategoriler = N'<ham kategori>';

-- Ö1 · «Satış adedi» alanlarının doluluğu ve alma partileri (analiz §10 soru 1 için ölçüm)
SELECT COUNT(*) AS kayit, SUM(CASE WHEN new_SatisAdedi IS NOT NULL THEN 1 ELSE 0 END) AS satis1_dolu,
  SUM(CASE WHEN NULLIF(new_SatAdedi2, '') IS NOT NULL THEN 1 ELSE 0 END) AS satis2_dolu,
  COUNT(DISTINCT ImportSequenceNumber) AS alma_partisi, COUNT(DISTINCT new_Kategoriler) AS ham_kategori,
  SUM(CASE WHEN new_Kategoriler LIKE '%>%' THEN 1 ELSE 0 END) AS buyuktur_ayirici,
  SUM(CASE WHEN new_Kategoriler LIKE '%,%' THEN 1 ELSE 0 END) AS virgul_ayirici
FROM <P>new_rakipkitapBase WHERE statecode = 0;
