# Logo ERP iş kuralları (operatör tarafından doğrulandı)

## Kural 1
Fatura türleri (dbo_LG_411_01_INVOICE.TRCODE): 7 perakende satış, 8 toptan satış, 9 verilen hizmet = SATIŞ; 2 perakende satış iadesi, 3 toptan satış iadesi = SATIŞ İADESİ; 1 mal alım, 4 alınan hizmet = SATINALMA; 6 alım iadesi. Ciro/satış sorularında TRCODE IN (7,8,9), net ciro = satış − iade (TRCODE IN (2,3)). Her zaman CANCELLED = 0 filtrele. Tutar kolonu NETTOTAL (KDV dahil net), tarih DATE_.

Örnek sorular: toplam ciro; net satış; aylık satış; iade tutarı

## Kural 2
Malzeme hareket satırları (dbo_LG_411_01_STLINE): LINETYPE 0 = malzeme satırı, 2 = İSKONTO satırı (TOTAL'i ciro kadar büyüktür); ürün bazlı ciro/adet için LINETYPE = 0 AND CANCELLED = 0 kullan; satış TRCODE IN (7,8), satış iadesi TRCODE IN (2,3). Adet = AMOUNT, satır tutarı = TOTAL. OUTCOST BİRİM maliyettir: satır maliyeti = AMOUNT * OUTCOST; brüt kâr marjı = 1 − SUM(AMOUNT*OUTCOST)/SUM(TOTAL) yalnız OUTCOST <> 0 satırlarda. Tabloyu daima DATE_ ile filtrele.

Örnek sorular: en çok satan ürünler; ürün bazında ciro; brüt kâr marjı; iskonto oranı

## Kural 3
Cari kartlar (dbo_LG_411_CLCARD): SPECODE2 = SATIŞ KANALI (KITAPCI, E-TICARET, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR, YURTDIŞI...), DEFINITION_ = cari unvanı, CODE = cari kodu, CITY = şehir. Kanal soruları SPECODE2 ile gruplanır; boş değerler '(boş)' sayılır. Kişisel veri kolonlarını (TCKNO, EMAILADDR, TELNRS1/2, adres, IBAN) asla seçme.

Örnek sorular: kanal bazında satış; müşteri bazında ciro; şehir bazında satış

## Kural 4
Malzeme kartları (dbo_LG_411_ITEMS): SPECODE = YAYINEVİ/imprint (Timaş Çocuk, Genç Timaş, Mavi Kirpi...), NAME = kitap adı, CODE = stok kodu, STGRPCODE grup kodu. Yayınevi/dizi kırılımı SPECODE ile yapılır. STLINE.STOCKREF → ITEMS.LOGICALREF, STLINE.CLIENTREF → CLCARD.LOGICALREF, INVOICE.CLIENTREF → CLCARD.LOGICALREF, STLINE.INVOICEREF → INVOICE.LOGICALREF.

Örnek sorular: yayınevi bazında satış; en çok satan kitaplar; kitap adına göre

## Kural 5
Siparişler (dbo_LG_411_01_ORFICHE / ORFLINE): bu kurulumda TRCODE = 1 fişleri satış siparişidir (e-ticaret/pazaryeri kanalı). Açık sipariş = CANCELLED = 0 AND CLOSED = 0 AND AMOUNT > SHIPPEDAMOUNT. Sipariş modülü tüm satışları kapsamaz; ciro için fatura tablosunu kullan.

Örnek sorular: açık siparişler; sevk edilmeyen sipariş; sipariş tutarı

## Kural 6
Veri 2026 yılına (firma 411, Ocak–Ağustos) aittir; yıl belirtilmeyen sorular 2026 YTD kabul edilir. Para birimi TL. Tarih kırılımı için EXTRACT(MONTH FROM DATE_) / EXTRACT(YEAR FROM DATE_) kullan. Türkçe yanıt ver.

Örnek sorular: bu yıl; aylık; geçen ay

## Kural 7 — Aylık/gruplu ortalama ve oranlar
Bir kırılım (ay, kanal, yayınevi) için ortalama veya oran isteniyorsa hesaplamayı AYNI GROUP BY içinde yap
(ör. SUM(NETTOTAL)/COUNT(*)) ya da kırılım anahtarıyla JOIN edilen bir CTE/türetilmiş tablo kullan.
ASLA tek başına bağımsız bir skaler alt sorgu (SELECT AVG(...) FROM ... WHERE <ifade> = <aynı ifade>) yazma:
böyle bir alt sorgu her satıra aynı genel değeri döndürür ve sonuç yanlış olur.

## Kural 8 — Sipariş fişleri (dbo_LG_411_01_ORFICHE / dbo_LG_411_01_ORFLINE)
Sipariş SAYISI her zaman fiş başlığından sayılır: COUNT(DISTINCT ORFICHE."LOGICALREF") — ORFLINE ile JOIN edildiğinde
satır sayısı kadar çoğalır (fan-out). Sipariş TUTARI = ORFICHE."NETTOTAL" (fiş net toplamı); ORFLINE."TOTAL" satır brüt tutarıdır.
Fiş tarihi ORFICHE."DATE_", iptal filtresi ORFICHE."CANCELLED" = 0. Genel ilke: başlık tablosundan sayarken satır tablosuna JOIN yapma
veya COUNT(DISTINCT başlık.LOGICALREF) kullan.
