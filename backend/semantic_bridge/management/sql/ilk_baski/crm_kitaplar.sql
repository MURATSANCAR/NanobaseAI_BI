-- Bütün kitap kartları: emsal aramanın özellikleri ve ilk yayın tarihi.
-- Özellik önce Baskı Öneri raporunun kullandığı `powerbikitap` görünümünden (dolu, düzeltilmiş metin), yoksa kitap
-- kartının kendi alanından okunur: yeni ve yayımlanmamış kitaplar `powerbikitap`'ta henüz yok.
-- CRM tarihi UTC saklar; ilk yayın günü İstanbul saatine (+3) çevrilerek alınır (00:00 yayın bir gün önceye düşmesin).
SELECT
    k.new_stokkodu                                          AS stok_kodu,
    k.new_kitapId                                           AS kitap_id,
    COALESCE(p.[Ürün Adı], k.new_name)                      AS ad,
    COALESCE(p.Yayınevi, k.new_yayineviidName)              AS yayinevi,
    COALESCE(p.Kitaplık, k.new_kitaplikidName)              AS kitaplik,
    COALESCE(p.Dizi_Tür, k.new_diziidName)                  AS dizi,
    COALESCE(p.Yazar, k.new_yazartext, k.new_YazarName)     AS yazar,
    COALESCE(p.HedefKitle, hk.Value)                        AS hedef_kitle,
    k.new_turlertext                                        AS tur,
    COALESCE(NULLIF(p.SayfaSayısı, 0), NULLIF(k.new_sayfasayisi, 0)) AS sayfa,
    COALESCE(NULLIF(p.Üzeri_Fiyat, 0), NULLIF(k.new_kdvdahilfiyat, 0), NULLIF(k.new_PerakendeBirimFiyat, 0)) AS fiyat,
    CAST(DATEADD(HOUR, 3, k.new_ilkyayintarihi) AS DATE)    AS ilk_yayin,
    CAST(DATEADD(HOUR, 3, k.CreatedOn) AS DATE)             AS kart_tarihi,
    p.Statü                                                 AS statu,
    k.statecode                                             AS kart_durumu,
    k.new_ilkyilsatishedefi                                 AS ilk_yil_hedefi,
    k.new_nihaibaskiadeti                                   AS nihai_baski_adedi
FROM Timas_MSCRM.dbo.new_kitap AS k
LEFT JOIN Timas_MSCRM.dbo.powerbikitap AS p ON p.StokKodu = k.new_stokkodu
LEFT JOIN Timas_MSCRM.dbo.StringMapBase AS hk
       ON hk.AttributeName = 'new_hedefkitle' AND hk.AttributeValue = k.new_hedefkitle AND hk.LangId = 1055
      AND hk.ObjectTypeCode = (SELECT ObjectTypeCode FROM Timas_MSCRM.dbo.EntityView WHERE Name = 'new_kitap')
WHERE k.new_stokkodu IS NOT NULL
