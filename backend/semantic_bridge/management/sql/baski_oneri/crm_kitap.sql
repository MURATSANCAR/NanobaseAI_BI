-- Kitap kartı ve baskı ayrıntısı (CRM'de mevcut rapor için hazırlanmış görünümler).
SELECT
    a.StokKodu      AS stok_kodu,
    a.[Ürün Adı]    AS urun_adi,
    a.Statü         AS statu,
    a.Yazar         AS yazar,
    a.Yayınevi      AS yayinevi,
    a.Kitaplık      AS kitaplik,
    a.Dizi_Tür      AS dizi_tur,
    a.SayfaSayısı   AS sayfa_sayisi,
    a.Üzeri_Fiyat   AS uzeri_fiyat,
    a.BaskıTarihi   AS baski_tarihi,
    a.StokAdedi     AS stok_adedi,
    b.Baskı_Durum   AS baski_durum,
    b.SonBaskıTarihi AS son_baski_tarihi,
    b.Baskı_Adet    AS baski_adet
FROM Timas_MSCRM.dbo.powerbikitap AS a
LEFT JOIN Timas_MSCRM.dbo.powerbikitapdetay AS b ON a.StokKodu = b.Stok_Kodu
