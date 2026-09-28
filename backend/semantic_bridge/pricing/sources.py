"""M9 kaynak sorguları: Logo ve CRM'den yalnız okuma. Ekran bu SQL'lerin kendisini gösterir.

Ölçümler (2026-09-28, .155 Logo kopyası, CRM .28):
- **Baskı hizmeti:** matbaanın «Komple Baskı Giderleri» faturası (alınan hizmet, INVOICE.TRCODE 4, hizmet kartı
  `730.38.381`) her satırda kitabın stok kodunu satırın özel kodunda (`STLINE.SPECODE` = `15201.01.xxxx`) taşır;
  miktar basılan adet, `LINENET` KDV hariç tutar. 2026'da 21 matbaa, 1.600'ü aşkın satır.
- **Kâğıdı Timaş alır:** `15001…` kâğıt kartları (3. hamur 60/65 gr, bristol kapak…) satın alma faturasıyla (TRCODE 1)
  gelir, ₺/kg ölçülür; matbaanın baskı faturası kâğıtsızdır. Bandrol de `15001.000.000001.BD` kartıyla alınır.
- **Gerçekleşen birim maliyet:** satış satırındaki `OUTCOST` (Logo'nun maliyetlendirdiği birim maliyet; kâğıt + baskı
  + üretim fişine yüklenen her şey). Kâr = LINENET − AMOUNT × OUTCOST (katalog kuralı); OUTCOST = 0 satır sayılır.
- **Satış:** yalnız faturalı satır (`INVOICEREF <> 0`), satış 7/8/9 eksi iade 2/3, `LINETYPE = 0`, kitap kodları `152…`.
- Her yıl ayrı Logo kopyasıdır (211 = 2021–2025, 411 = 2026). Kopyalar ölçülerek bulunur, birbirine eklenmez;
  her kopyadan yalnız kendi yıllarının satırı okunur.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

START_YEAR = 2021
_FIRM = re.compile(r"^\d{3}$")


@dataclass(frozen=True)
class Source:
    id: str
    connection: str        # logo | crm
    title: str
    description: str
    sql: str               # {f} = Logo kopya kodu, {start}/{end} = tarih sınırı (YYYYMMDD)


LOGO_COPIES_SQL = (
    "SELECT SUBSTRING(t.name, 4, 3) AS firma FROM sys.tables t "
    "WHERE t.name LIKE 'LG[_][0-9][0-9][0-9][_]01[_]INVOICE'"
)
LOGO_COPY_RANGE_SQL = "SELECT MIN(DATE_) AS ilk, MAX(DATE_) AS son, COUNT(*) AS fatura FROM dbo.LG_{f}_01_INVOICE WHERE CANCELLED = 0 AND DATE_ > '19500101'"

SOURCES: list[Source] = [
    Source(
        "logo_baski", "logo", "Matbaa baskı faturaları",
        "Alınan hizmet faturasındaki «Komple Baskı Giderleri» satırları; kitap satırın özel kodundaki stok kodundan "
        "bulunur. Fatura + kitap başına basılan adet ve KDV hariç tutar.",
        "SELECT S.SPECODE AS kod, CONVERT(date, I.DATE_) AS tarih, I.FICHENO AS fatura, C.DEFINITION_ AS matbaa,\n"
        "       SUM(S.AMOUNT) AS adet, SUM(S.LINENET) AS tutar\n"
        "FROM dbo.LG_{f}_01_STLINE S\n"
        "JOIN dbo.LG_{f}_01_INVOICE I ON I.LOGICALREF = S.INVOICEREF\n"
        "JOIN dbo.LG_{f}_SRVCARD SC ON SC.LOGICALREF = S.STOCKREF\n"
        "LEFT JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = I.CLIENTREF\n"
        "WHERE I.CANCELLED = 0 AND S.CANCELLED = 0 AND I.TRCODE = 4 AND S.LINETYPE = 4\n"
        "  AND SC.DEFINITION_ LIKE N'Komple Bask%' AND S.SPECODE LIKE '152%'\n"
        "  AND I.DATE_ >= '{start}' AND I.DATE_ < '{end}'\n"
        "GROUP BY S.SPECODE, CONVERT(date, I.DATE_), I.FICHENO, C.DEFINITION_",
    ),
    Source(
        "logo_satis", "logo", "Kitap satışları ve satılan malın maliyeti",
        "Faturalı satış satırları (7, 8, 9) eksi iadeler (2, 3); kitap ve yıl başına adet, net tutar (LINENET), "
        "iskonto öncesi tutar (TOTAL) ve Logo'nun birim maliyetiyle (OUTCOST) satılan malın maliyeti.",
        "SELECT IT.CODE AS kod, YEAR(S.DATE_) AS yil,\n"
        "       SUM(CASE WHEN S.TRCODE IN (7, 8, 9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,\n"
        "       SUM(CASE WHEN S.TRCODE IN (7, 8, 9) THEN S.LINENET ELSE -S.LINENET END) AS net,\n"
        "       SUM(CASE WHEN S.TRCODE IN (7, 8, 9) THEN S.TOTAL ELSE -S.TOTAL END) AS brut,\n"
        "       SUM(CASE WHEN S.TRCODE IN (7, 8, 9) THEN S.AMOUNT * S.OUTCOST ELSE 0 END) AS maliyet,\n"
        "       SUM(CASE WHEN S.TRCODE IN (7, 8, 9) AND S.OUTCOST > 0 THEN S.AMOUNT ELSE 0 END) AS maliyetli_adet,\n"
        "       SUM(CASE WHEN S.TRCODE IN (7, 8, 9) THEN S.AMOUNT ELSE 0 END) AS satis_adet\n"
        "FROM dbo.LG_{f}_01_STLINE S\n"
        "JOIN dbo.LG_{f}_ITEMS IT ON IT.LOGICALREF = S.STOCKREF\n"
        "WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN (2, 3, 7, 8, 9) AND S.INVOICEREF <> 0\n"
        "  AND IT.CODE LIKE '152%' AND S.DATE_ >= '{start}' AND S.DATE_ < '{end}'\n"
        "GROUP BY IT.CODE, YEAR(S.DATE_)",
    ),
    Source(
        "logo_kanal", "logo", "Kanal iskontoları (son 12 ay)",
        "Kitap satış satırlarında müşteri grubuna (CLCARD.SPECODE2) göre iskonto öncesi tutar (TOTAL = adet × liste "
        "fiyatı, KDV hariç) ve net tutar (LINENET). İskonto = 1 − net ÷ iskonto öncesi.",
        "SELECT ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), N'Grup kodu boş') AS kanal,\n"
        "       SUM(S.TOTAL) AS brut, SUM(S.LINENET) AS net, SUM(S.AMOUNT) AS adet, COUNT(*) AS satir\n"
        "FROM dbo.LG_{f}_01_STLINE S\n"
        "JOIN dbo.LG_{f}_ITEMS IT ON IT.LOGICALREF = S.STOCKREF\n"
        "LEFT JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF\n"
        "WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN (7, 8) AND S.INVOICEREF <> 0\n"
        "  AND IT.CODE LIKE '152%' AND S.DATE_ >= '{start}' AND S.DATE_ < '{end}'\n"
        "GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), N'Grup kodu boş')",
    ),
    Source(
        "logo_kagit", "logo", "Kâğıt ve bandrol alışları (son 6 ay)",
        "Satın alma faturasıyla (TRCODE 1) gelen 15001 kartları: kâğıt cinsi ve gramajı kart adından, ₺/kg = tutar ÷ kg.",
        "SELECT IT.CODE AS kod, IT.NAME AS ad, SUM(S.AMOUNT) AS miktar, SUM(S.LINENET) AS tutar, COUNT(*) AS satir,\n"
        "       MAX(CONVERT(date, I.DATE_)) AS son\n"
        "FROM dbo.LG_{f}_01_STLINE S\n"
        "JOIN dbo.LG_{f}_01_INVOICE I ON I.LOGICALREF = S.INVOICEREF\n"
        "JOIN dbo.LG_{f}_ITEMS IT ON IT.LOGICALREF = S.STOCKREF\n"
        "WHERE I.CANCELLED = 0 AND S.CANCELLED = 0 AND I.TRCODE = 1 AND S.LINETYPE = 0 AND IT.CODE LIKE '15001%'\n"
        "  AND I.DATE_ >= '{start}' AND I.DATE_ < '{end}'\n"
        "GROUP BY IT.CODE, IT.NAME",
    ),
    Source(
        "logo_nakliye", "logo", "Satış nakliye gideri",
        "«Satış Nakliye Giderleri» hizmet satırları (alınan hizmet faturası). Net satışa oranı dağıtım gideri varsayılanıdır.",
        "SELECT SUM(S.LINENET) AS tutar, COUNT(*) AS satir\n"
        "FROM dbo.LG_{f}_01_STLINE S\n"
        "JOIN dbo.LG_{f}_01_INVOICE I ON I.LOGICALREF = S.INVOICEREF\n"
        "JOIN dbo.LG_{f}_SRVCARD SC ON SC.LOGICALREF = S.STOCKREF\n"
        "WHERE I.CANCELLED = 0 AND S.CANCELLED = 0 AND I.TRCODE = 4 AND S.LINETYPE = 4\n"
        "  AND SC.DEFINITION_ LIKE N'Satış Nakliye%' AND I.DATE_ >= '{start}' AND I.DATE_ < '{end}'",
    ),
    Source(
        "crm_kitap", "crm", "CRM kitap kartları",
        "Kitap künyesi (stok kodu, sayfa, ebat, KDV dahil fiyat, KDV oranı), yayınevi ve kitaplık adı, yürürlükteki "
        "sözleşmenin telif oranı, türü (brüt/net), ödeme tipi (baskıdan/satıştan) ve avansı.",
        "SELECT k.new_kitapId AS id, k.new_name AS ad, k.new_StokKodu AS kod, k.new_sayfasayisi AS sayfa, k.new_Ebat AS ebat,\n"
        "       k.new_kdvdahilfiyat AS fiyat, k.new_kdvorani AS kdv, k.new_ciltlemesekli AS cilt, k.new_yazartext AS yazar,\n"
        "       y.new_name AS yayinevi, kl.new_name AS kitaplik, k.new_ilkyayintarihi AS ilk_yayin,\n"
        "       s.new_Telif AS telif, s.new_telifturu AS telif_turu, s.new_TelifTipi AS telif_tipi,\n"
        "       s.new_sozlesmeavanstutari AS avans, s.new_sozlesmeparabirimi AS avans_para\n"
        "FROM new_kitapBase k\n"
        "LEFT JOIN new_markaBase y ON y.new_markaId = k.new_yayinciid\n"
        "LEFT JOIN new_kitaplikBase kl ON kl.new_kitaplikId = k.new_kitaplikid\n"
        "LEFT JOIN new_sozlesmeBase s ON s.new_sozlesmeId = k.new_aktifsozlesmeid AND s.statecode = 0\n"
        "WHERE k.statecode = 0 AND k.new_StokKodu LIKE '152%'",
    ),
    Source(
        "crm_baski", "crm", "CRM üretim (baskı) kayıtları",
        "Her baskının kesinleşen adedi ve kapak fiyatı, sayfa sayısı, cilt şekli, baskı tipi, iç kâğıt gramajı ve renk "
        "sayısı, matbaa, üretim tarihi.",
        "SELECT u.new_UretimId AS id, u.new_kitapid AS kitap, u.new_StokKodu AS kod, u.new_BaskiNo AS baski_no,\n"
        "       u.new_uretimyili AS yil, u.new_UretimTarihi AS tarih, u.new_DepoGiriTarihi AS depo,\n"
        "       u.new_kesinlesenbaskiadeti AS adet, u.new_kesinlesenbaskifiyati AS fiyat, u.new_onerilenbaskiadeti AS oneri_adet,\n"
        "       u.new_SayfaSayisi AS sayfa, u.new_ciltlemesekli AS cilt, u.new_baskitipi AS baski_tipi,\n"
        "       u.new_icsayfabirgramaj AS gramaj, u.new_icsayfabironsayfarenk AS renk, u.new_Matbaa AS matbaa\n"
        "FROM new_UretimBase u\n"
        "WHERE u.statecode = 0 AND ISNULL(u.new_uretimyili, YEAR(u.createdon)) >= {start_year}",
    ),
    Source(
        "crm_secenek", "crm", "CRM seçenek adları",
        "Matbaa, cilt şekli, baskı tipi, telif türü ve ödeme tipinin ekranda görünen adları (StringMap).",
        "SELECT e.Name AS varlik, m.AttributeName AS alan, m.AttributeValue AS deger, m.Value AS ad\n"
        "FROM StringMap m JOIN MetadataSchema.Entity e ON e.ObjectTypeCode = m.ObjectTypeCode\n"
        "WHERE ((e.Name = 'new_uretim' AND m.AttributeName IN ('new_matbaa', 'new_ciltlemesekli', 'new_baskitipi'))\n"
        "   OR (e.Name = 'new_sozlesme' AND m.AttributeName IN ('new_telifturu', 'new_teliftipi', 'new_sozlesmeparabirimi')))",
    ),
]
BY_ID = {s.id: s for s in SOURCES}


def logo_sql(source_id: str, firm: str, start: str, end: str) -> str:
    if not _FIRM.match(firm or ""):
        raise ValueError("Logo kopya kodu üç rakam olmalı.")
    return BY_ID[source_id].sql.format(f=firm, start=start, end=end)


def crm_sql(source_id: str, start_year: int = START_YEAR - 2) -> str:
    return BY_ID[source_id].sql.replace("{start_year}", str(int(start_year)))
