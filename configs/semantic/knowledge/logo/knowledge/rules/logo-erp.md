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
Bu kurulum tek şirketin farklı zamanlara ait yedek/anlık görüntülerini kullanır. Teknik tablo kodları ayrı şirket değildir. Dönem seçimi doğrulanmış kaynak kapsamı ve uygulamanın zaman kuralıyla yapılır; geçmiş yılların yokluğu varsayılmaz. Para birimi TL. Tarih kırılımı için EXTRACT(MONTH FROM DATE_) / EXTRACT(YEAR FROM DATE_) kullan. Türkçe yanıt ver.

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
- **Fiyat listesi karşılaştırması satır düzeyindedir:** `PRCLIST` (alış/satış fiyatları) malzeme kartına bağlıdır (`PRCLIST.CARDREF = STLINE.STOCKREF`), cariye değil. Satış listesi `PTYPE = 2`, aktif `ACTIVE = 0`, TL `CURRENCY = 160`, geçerlilik `BEGDATE <= satır tarihi <= ENDDATE`. Kıyas satırın **birim fiyatı** `STLINE.PRICE` ile yapılır; fatura toplamı (`INVOICE.NETTOTAL`) birim fiyatla kıyaslanmaz. Bir ürünün aynı anda birden çok geçerli listesi olabilir (kanal/cari özel kodu `CLSPECODE`, öncelik `PRIORITY`): "listenin altında" derken hangi liste alındığı (en düşük geçerli liste fiyatı ya da carinin `CLSPECODE`'una uyan liste) cevapta yazılır. Büyük listeler yerine önce toplam (satır/fatura sayısı ve tutar) verilir, örnek satırlar sınırlı sayıda gösterilir.

## Kural 9 — Üretim: baskı, üretim emri, sarf, üretimden giriş — iş teyidi bekliyor
Yayınevinde bir kitabın **baskısı** bir **üretim emridir**: `PRODORD` (bir satır = bir baskı/üretim emri; `ITEMREF` → ITEMS, `DATE_` emir tarihi,
`PLNAMOUNT` planlanan adet, `STATUS` 3 = tamamlandı, `CANCELLED` = 0). "Son üç baskı" = ürünün **tamamlanmış** (`STATUS = 3`) ve `DATE_`'e göre en yeni üç üretim emri
(ROW_NUMBER() OVER (PARTITION BY ITEMREF ORDER BY DATE_ DESC)); "kaç baskı yaptı" = ürünün üretim emri sayısı.
- **Çekilen / sarf edilen malzeme miktarı** = `STLINE` sarf fişi satırları: `TRCODE = 12 AND IOCODE = 4 AND LINETYPE = 0 AND CANCELLED = 0`,
  emre bağ `STLINE.PRODORDERREF = PRODORD.LOGICALREF`; miktar `AMOUNT` (malzeme kartı `STOCKREF`). Baskı başına toplam: emir bazında SUM(AMOUNT).
- **Üretilen adet / üretimden giriş** = `STLINE` üretimden giriş fişi: `TRCODE = 13 AND IOCODE = 1 AND LINETYPE = 0 AND CANCELLED = 0`, aynı `PRODORDERREF` bağı; `STOCKREF` üretilen mamul.
- Reçete/alt malzeme tabloları (`STCOMPLN` karma koli, `BOMLINE` reçete) **planlanan** bileşeni verir, fiilen çekilen miktarı vermez; "çekilen/sarf/kullanılan" sorularında sarf fişi okunur.
- "Bir kitabın …" genel bir isimdir, belli bir kitap değil: kitap kırılımı (ITEMS.CODE/NAME ile GROUP BY) yapılır, `NAME = 'kitap'` gibi bir filtre yazılmaz.
- Örnek sorular: bir kitabın son üç baskısındaki malzeme farkı; son üç ayda üretilen adet; baskı başına sarf; kaç baskı yapıldı.

## Kural 10 — Sevkiyat ve "sipariş verip hiç sevkiyat almamış" — iş teyidi bekliyor
- **Sevkiyat** = malzeme çıkış hareketi: `STLINE` satış satırları `TRCODE IN (7,8)`, `IOCODE = 4`, `LINETYPE = 0`, `CANCELLED = 0`; miktar `AMOUNT`, cari `CLIENTREF` (irsaliye satırı `STFICHEREF`, faturalanmışsa `INVOICEREF`). Sipariş satırındaki `SHIPPEDAMOUNT` ise **o satırdan** sevk edilen miktardır.
- "Hiç sevkiyat almamış / hiç sevk edilmemiş müşteri" **müşteri düzeyinde yokluktur**: siparişi olan (`LG_ORFICHE` TRCODE 1, CANCELLED 0) ama hiç sevkiyat kaydı olmayan cari → `NOT EXISTS (SELECT 1 FROM STLINE s WHERE s.CLIENTREF = c.LOGICALREF AND s.TRCODE IN (7,8) …)` (ya da sipariş satırlarının hiçbirinde `SHIPPEDAMOUNT > 0` yok). `SHIPPEDAMOUNT = 0` satırlarını listelemek "sevk bekleyen satırlar"dır, "hiç sevkiyat almamış müşteri" değildir.
- Bekleyen tutar = Σ (`AMOUNT − SHIPPEDAMOUNT`) × `PRICE` (satır fiyatı) ya da açık satırlarda Σ `TOTAL`; bekleyen adet = Σ (`AMOUNT − SHIPPEDAMOUNT`).
- Örnek sorular: sipariş verip sevkiyat almamış müşteriler; sevk edilen adet; hiç sevk edilmemiş siparişler.

## Kural 11 — Tanım kararları (2026-09-17, operatör; iş teyidi bekliyor)
- **Net ciro** satır düzeyinde: satış satırları (TRCODE 7,8,9) `LINENET` − iade satırları (2,3) `LINENET`; `LINETYPE = 0`, `CANCELLED = 0`.
- **Maliyet** yalnız satış satırlarında (TRCODE 7,8,9): `AMOUNT × OUTCOST`; `OUTCOST = 0` satırlar dahil, sayısı yazılır. **Kâr** = `LINENET − AMOUNT × OUTCOST` (iade eksi). CRM "senaryo kârı" ayrı kavramdır; yalın "kâr" Logo kârıdır.
- **Perakende / toptan / diğer satış** = TRCODE 7 / 8 / 9 (INVOICE ve STLINE). **İskonto oranı** satır düzeyinde: Σ TOTAL (LINETYPE 2) / Σ TOTAL (LINETYPE 0); kartta tanımlı iskonto `CLCARD.DISCRATE`.
- **Müşteri grubu / kanal** = `CLCARD.SPECODE2`; boş kod "Grup kodu boş".
- **Stok bakiyesi** yalnız cari kopyadan (açılış devri içinde); **bekleyen sipariş** `CLOSED = 0 AND AMOUNT > SHIPPEDAMOUNT`, adet fiş sayısı; **sipariş** = LG_ORFICHE TRCODE 1; **sevkiyat** = STLINE TRCODE 7,8 IOCODE 4.

## Kural 12 — Çek / senet (LG_CSCARD) — durum kodları veriyle doğrulandı (2026-09-18)
`LG_CSCARD`: bir satır = bir çek/senet. `DOC`: 1 müşteri çeki, 2 müşteri senedi, 3 kendi çekimiz, 4 borç senedimiz. Tutar `AMOUNT`, vade `DUEDATE`, düzenleme `SETDATE`, iptal `CANCELLED = 0`.
`CURRSTAT` (güncel durum; son `CSTRANS.STATUS` ile aynı kod): 1 portföyde · 2 ciro edildi · 3 teminata verildi · 4 tahsile verildi · 5 protestolu tahsile verildi · 6 iade edildi · 7 protesto edildi · 8 **tahsil edildi** · 11 **karşılığı yok (karşılıksız)** · 12 tahsil edilemiyor.
- "Karşılıksız çıkan" = `CURRSTAT = 11`; "protesto olan / protestolu" = `CURRSTAT IN (5, 7)`. İkisi ayrı ayrı tutar ve adet olarak verilir (koşullu toplam), toplam ayrıca yazılır. "Bu yıl" için vade tarihi `DUEDATE` kullanılır ve hangi tarihin alındığı yazılır.
- Danışman görünümü `ABCekSenetView` bu kodları farklı adlandırır (8 = "karşılıksız iade" der); veride 8'in son hareketi tahsil bordrosudur — görünümün adları kullanılmaz.

## Kural 13 — Cari risk limiti (CLRNUMS)
`CLRNUMS` (cari risk tablosu, `CLCARDREF` → CLCARD): `ACCRISKLIMIT` açık hesap risk limiti, `ACCRISKTOTAL` güncel açık hesap riski. **Limiti aşan cari** = `ACCRISKLIMIT > 0 AND ACCRISKTOTAL > ACCRISKLIMIT`; aşım tutarı = `ACCRISKTOTAL − ACCRISKLIMIT`. `ACCRISKOVER` bir durum değil, **ayardır** ("limit aşılınca işlem durdurulsun mu": 1 evet / 0 hayır) — aşanları bulmak için kullanılmaz. Limit tanımsız (0) cariler aşmış sayılmaz; `ACCRISKTOTAL` NULL ise 0 alınır.

## Kural 14 — Ambar (depo)
Ambar numarası hareket satırında `STLINE.SOURCEINDEX`; adı `L_CAPIWHOUSE.NAME` (`L_CAPIWHOUSE.NR = STLINE.SOURCEINDEX AND L_CAPIWHOUSE.FIRMNR = <firma no>`). Ambar bazında stok = malzeme ve `SOURCEINDEX` kırılımında giriş − çıkış. Malzeme–ambar parametreleri `INVDEF` (`ITEMREF`, `INVENNO` = ambar no, `MINLEVEL` asgari, `MAXLEVEL` azami, `MINLEVELCTRL` 0 kontrol yok).

## Kural 15 — Kasa ve banka giriş / çıkış
Kasa hareketleri `KSLINES` (`SIGN` 0 = giriş/tahsil, 1 = çıkış/ödeme; tutar `AMOUNT`; `CANCELLED = 0`; tarih `DATE_`). Banka hareketleri `BNFLINE` (`SIGN` 0 = giriş, 1 = çıkış; `AMOUNT`; `CANCELLED = 0`; `DATE_`). "Giriş çıkış farkı" = giriş − çıkış (net). Kasa ve banka **ayrı tablolardır**: her biri kendi alt sorgusunda ay bazında toplanır, sonra yan yana / toplam olarak verilir; iki tablo satır satır birleştirilmez. İki ay karşılaştırmasında her ay ayrı sütun ya da ayrı satırdır.

## Kural 16 — Gider ve masraf merkezi (muhasebe fişi satırlarından)

- **Gider** stok/fatura satırından okunmaz; kaynağı muhasebe fiş satırlarıdır: `EMFLINE`. Satırın hesabı `EMFLINE.ACCOUNTCODE` (hesap planı kodu), tutarı `DEBIT` (borç) ve `CREDIT` (alacak), tarihi `DATE_`, iptali `CANCELLED = 0`.
- Gider hesapları Tekdüzen Hesap Planı'nın **7 ile başlayan** maliyet/gider hesaplarıdır: `ACCOUNTCODE LIKE '7%'`. Gider tutarı = `SUM(DEBIT - CREDIT)`.
- **Masraf merkezi** `EMFLINE.CENTERREF → EMCENTER.LOGICALREF`; adı `EMCENTER.DEFINITION_`, kodu `EMCENTER.CODE`. "Masraf merkezi bazında gider" = EMFLINE ⨝ EMCENTER, `ACCOUNTCODE LIKE '7%'`, `CANCELLED = 0`, dönem `EMFLINE.DATE_` üzerinde, `GROUP BY EMCENTER.CODE, EMCENTER.DEFINITION_`.
- STLINE/INVOICE üzerindeki CENTERREF hizmet/masraf satırının merkezidir; "gider" sorusu onunla cevaplanmaz.

## Kural 17 — Malzeme (stok kartı) listeleri ve hareketsiz stok

- Malzeme/stok kartlarının **listesi ya da sayısı** istenince yalnız kullanımdaki kartlar alınır: `ITEMS.ACTIVE = 0` (1 = kullanım dışı). Bu koşul kart listesine aittir; satış/hareket toplamlarına eklenmez.
- "Hareketsiz / hiç hareket görmemiş stok" = dönemde `STLINE` satırı olmayan malzeme (`NOT EXISTS`, `CANCELLED = 0`, `LINETYPE = 0`). Listede malzemenin **eldeki miktarı** (stok bakiyesi) de gösterilir; bakiye ayrı bir alt sorguda, tarih filtresi olmadan hesaplanır ve `LEFT JOIN` ile eklenir.

