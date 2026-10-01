# Kavram → kaynak sahipliği (taslak 1)

Tarih: 2026-10-01. Makinece okunur sürüm: [`kavram-sahipligi.json`](kavram-sahipligi.json). Her kavramın sette kaç soruda
geçtiği ve bu soruların hangi yola gittiği [`yonlendirme-seti.jsonl`](yonlendirme-seti.jsonl)'den sayıldı
(özet: [`YONLENDIRME.md`](YONLENDIRME.md)).

Bu belge bir **taslaktır**. Sunucuda sorgu koşturulmadı. Dayandığı kaynaklar: repo kodu, bugünkü CRM sözlüğü
([`CRM.md`](CRM.md), [`crm-sozluk-ozet.json`](crm-sozluk-ozet.json)), bugünkü Logo sözlüğü ([`LOGO.md`](LOGO.md)),
CRM↔Logo kopya ölçümü ([`CRM-LOGO-KOPYA.md`](CRM-LOGO-KOPYA.md)) ve `docs/TIMAS-IS-TANIMLARI.md` ile
`docs/TIMAS-IS-KARARLARI-BEKLEYEN.md`.
Logo tablo adları yalnız modül düzeyinde yazıldı: kart tablosu `LG_FFF_`, hareket tablosu `LG_FFF_DD_`.

## Sahiplik kuralları

1. **Gerçekleşmiş finansal ve lojistik olay Logo'dadır.** Satış, iade, fatura, tahsilat, cari bakiye, stok, irsaliye/sevk,
   alış, maliyet, muhasebe, banka, kasa ve çek/senet bu gruba girer. CRM'deki karşılığı ya kopyadır ya da süreç kaydıdır.
   Finans cevabında varsayılan kaynak Logo'dur.
2. **Künye, ilişki ve süreç CRM'dedir.** Kitap künyesi, ISBN, yazar (kişi), eser katılımı, yayınevi ve alt marka bu gruptadır.
   Sözleşme, telif oranı, haklar, iş planı, proje, yayın kurulu, editör, etkinlik ve ziyaret de CRM'dedir. Satış hedefi,
   kampanya, reklam planı ve **sipariş süreci** de buraya girer.
3. **Karma** kavramda iki kaynak birlikte gerekir ve köprü anahtarı açıkça yazılır. Köprüsü olmayan karma kavram bugün
   kurulamaz; tabloda "köprü yok" diye geçer.
4. **Portal**: kayıt portalın kendi modül tablolarındadır (`chat_portal`). İK konusu sohbete bilerek kapalıdır.
5. **Yok**: hiçbir bağlı kaynakta bulunmayan kavramlar. Örnekler: tahmin, dış veri, saha masraf formu.
6. Ad benzerliği kimlik sayılmaz. Köprüler yalnız şunlardır:
   - kitap: `ITEMS.CODE ↔ new_kitapBase.new_stokkodu`
   - müşteri: `CLCARD.TAXNR ↔ AccountBase.new_VergiNo`
   - sevkiyat: `new_sevkiyat.new_logicalref ↔ STFICHE.LOGICALREF` (yıl firması ve tarih filtresi şart)
   - hedef: `new_satishedefleri.new_StokKodu ↔ ITEMS.CODE`

## Sayılar

- Kavram sayısı **105**.
- Sahip kaynağa göre: logo 43, crm 36, karma 17, portal 6, yok 3.
- Mevcut motordaki karşılık:
  - **var** 18
  - kısmi 27 (bunlara `aging`/`profit` gibi "typed gap" dönen modlar dahil)
  - **yok** 54
  - portal 6

## Taslağı yazarken çıkan, karar isteyen bulgular

1. **Sipariş artık CRM kavramı.** `TIMAS-IS-TANIMLARI.md` #10 ve #15 siparişi ve bekleyen siparişi Logo `ORFICHE/ORFLINE`
   üzerinden tanımlıyor. 2026-10-01 kopya ölçümü ise şunu gösterdi: B2B/saha siparişi CRM'de doğuyor ve Logo `ORFICHE`'de
   kopyası yok (0/239 ve 0/238 eşleşme). Logo `ORFICHE` ayrı bir akış (e-ticaret ve perakende). Motorun `open_orders` modu
   Logo'yu okuduğu için B2B bekleyen siparişleri görmüyor. Bu taslakta `siparis`, `crm_siparis_sureci` ve `bekleyen_urun`
   CRM'e, `acik_siparis` karmaya yazıldı. İş tanımları belgesinin güncellenmesi gerekiyor.
2. **Hedef yalnız adet olarak tutuluyor.** `new_satishedefleri` kitap × BMT × yıl kırılımında aylık **adet** hedefi tutar;
   tutar alanı yok. "Hedefe göre ciro" sorusuna TL hedef verilemez. BMT bazen bir kanal hesabıdır (Hepsiburada, D&R).
3. **CRM'de hakediş tablosu yok.** `new_odeme` tablosunda yalnız 50 kayıt var. Hakediş, CRM telif oranı × Logo net satış
   ile hesaplanacak bir **karma** kavram. Ödenmiş telif ise Logo muhasebesinde.
4. **Baskı maliyetinin iki kaynağı var.** Gerçekleşen maliyet Logo Komple Baskı faturasında (`SPECODE` = stok kodu).
   CRM `new_uretim` ise matbaa, forma, kâğıt ve cilt gibi süreç ve kalem bilgisini tutuyor. Toplam maliyet → logo,
   kalem dökümü → crm.
5. **`new_ziyaretyerleri` ziyaret kaydı değil.** Bu tablo okul ve kurum dizini (öğrenci sayısı vb.). Ziyaretler
   `new_etkinlik`'te tutuluyor.
6. Bu kavramların kaydı CRM'de **neredeyse boş ya da ölü**. Motora eklenmeden önce kullanılıp kullanılmayacağına karar
   verilmeli.

   | Kavram | Durum |
   |---|---|
   | Fırsat | 12 kayıt |
   | Teklif | 1 kayıt |
   | Randevu | 33 kayıt |
   | Telefon | 21 kayıt |
   | İş planı | 2025-12'den beri güncellenmiyor |
   | Talep yönetimi | 2024-07'den beri güncellenmiyor |
   | Kargo | 2024 tek seferlik Aras yüklemesi |
7. Sözlükte **masraf formu** ve **okuma listesi** varlığı bulunamadı. Setteki 7 masraf ve 2 okuma listesi sorusunun
   kaynağı yok.
8. [`LOGO.md`](LOGO.md)'den gelen ve Logo kavramlarını sınırlayan üç bulgu:
   - **Fatura sayısı**: motor 7/8/9 sayıyor, proje KPI'ı 2/3/7/8/9 sayıyor. Tanım kararı gerekiyor.
   - **Kâr**: OUTCOST güncel satırların yalnız %0,8'inde dolu, bu yüzden güncel aylarda kâr hesaplanamıyor.
   - **Kapama**: 2026'da CROSSREF hiç dolu değil, bu yüzden yaşlandırma ve tahsil süresi ancak yaklaşık hesaplanabilir.

## Aynı adın iki kaynakta farklı anlamı (en sık karışanlar)

| Kullanıcının dediği | Logo anlamı | CRM/portal anlamı |
|---|---|---|
| ciro | Net satış (`LINENET`) | Kampanya "Gerçekleşen Ciro", sipariş tutarı, sevkiyat tutarı |
| sipariş | E-ticaret/perakende `ORFICHE` | B2B/saha `new_siparis` (asıl akış) |
| iskonto | Faturada uygulanan | İskonto listesi, kampanya ve sipariş iskontosu (tanım) |
| tahsilat | Cari hareket (gerçekleşen) | Saha tahsilat kaydı (onay süreci) |
| temsilci | Satış elemanı (`SALESMANREF`) | CRM kullanıcısı / BMT |
| liste fiyatı | `PRCLIST` fiyat kartı | Fiyat listesi öğesi, kitap kartı fiyatı |
| risk/kredi limiti | Cari risk limiti | Firma kredi limiti, sipariş risk onayı |
| kanal | `SPECODE2` müşteri grubu | Müşteri tipi, sipariş tipi, hedef BMT/bölge |
| stok | Stok fişi bakiyesi | Raf/lot/sayım/koli defteri |
| proje | Gider kaydındaki proje kodu | Yayın projesi |
| kampanya | — | CRM kampanya kartı, portal indirim kampanyası, e-posta/SMS kampanyası |
| bütçe | — (Logo'da bütçe yok) | CRM bütçe kalemi, pazarlama bütçe modülü, portal aylık bütçe |

## Kavram tablosu

"Soru" sütunu, kavramın yönlendirme setinde (1.100 soru) kaç soruda geçtiğini gösterir. "Boşluk" sütunu, motorun bu
kavramı karşılayamadığı durumdaki sınıftır; sınıf adları [`YONLENDIRME.md`](YONLENDIRME.md)'de.

### finans

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Cari bakiye (müşteri)** `cari_bakiye` | logo | LG_FFF_DD_CLFLINE; LG_FFF_CLCARD | — | bakiye, borcu, alacağımız, açık alacak (net), ekstre, mutabakat bakiyesi | Kaynak dönemindeki borç/alacak hareketlerinden açılış ve kapanış bakiyesi (tek kaynak dönem). | Net bakiye fatura bazlı açık alacak ya da vadesi geçmiş borç değildir; yıllık devirler toplanmaz; CRM 'anlık risk' alanı ayrıdır. | **var**: customer_balances | — | 35 |
| **Çek ve senet** `cek_senet` | logo | LG_FFF_DD_CSCARD; LG_FFF_DD_CSTRANS; LG_FFF_DD_CSROLL | — | çek, senet, portföy, karşılıksız, protesto, ciro edilen çek, teminat, bordro | Portföy durumu CSCARD güncel statüsü; olay soruları CSTRANS hareketi. | 'Ciro' çek devri anlamında; karşılıksız: olay mı güncel durum mu (karar 3); CRM tahsilat tipi Çek ayrı kayıt. | kısmi: payment_movements (çek teslim hareketi) | B03 | 28 |
| **CRM tahsilat kaydı (saha)** `tahsilat_crm` | crm | new_tahsilatBase | Doğrulanmadı (Logo kopyası adayı; makbuz/slip no ya da vergi no adayı) | CRM'e girilen tahsilat, onay bekleyen tahsilat, sahadan toplanan tahsilat, makbuz | Onay Bekliyor / Onaylandı / Reddedildi / Logoya Aktarıldı statülü saha tahsilat kaydı. | Gerçekleşen tahsilat Logo'dadır; iki kaynağı toplamak çift sayar. | yok | B17 | 26 |
| **Banka hesabı ve hareketi** `banka` | logo | LG_FFF_BNCARD; LG_FFF_DD_BNFLINE; LG_FFF_DD_BNFICHE | — | banka bakiyesi, havale, EFT, POS, kredi, virman, mevduat | Banka hesap kartı bakiyesi ve hareketleri. | CRM new_bankahesabi (kişi/firma IBAN kartı) farklı kavram. | yok | B02 | 26 |
| **Tahsilat (gerçekleşen)** `tahsilat` | logo | LG_FFF_DD_CLFLINE | — | tahsilat, tahsil edilen, para girişi, ödeme aldık, havale, çek alındı, POS | 120 müşteri carileri, iptal olmayan alacak hareketleri SIGN=1; nakit/havale/çek/senet/kart (1,20,61,62,70). | Çek/senet teslimi nakit tahsil değildir; CRM new_tahsilat saha kaydıdır (onay süreci) — ayrı kavram. | **var**: collections, payment_movements | — | 25 |
| **Açık alacak, vade ve yaşlandırma** `vade_yaslandirma` | logo | LG_FFF_DD_PAYTRANS; LG_FFF_DD_CLFLINE | — | vadesi geçmiş, yaşlandırma, 30/60/90 gün, açık kalem, gecikmiş alacak, vadesi gelecek | Kapanmamış ödeme planı satırları vade tarihine göre; kapama ilişkisi doğrulanmadan sayı üretilmez. | Net cari bakiye yaşlandırma değildir; TOTAL-PAID/FIFO varsayılamaz. LOGO.md: 2026 PAYTRANS 139.648 satırın 0'ında CROSSREF, 14'ünde PAID dolu; PAYTRANS.DATE_ vade tarihidir (işlem tarihi PROCDATE). | kısmi: aging (typed gap) | B04 | 24 |
| **Tedarikçi borcu** `tedarikci_borc` | logo | LG_FFF_DD_CLFLINE (320 carileri); LG_FFF_CLCARD | — | borcumuz, tedarikçiye borç, matbaa borcu, ödenecek, satıcılar | Satıcı carilerinin net bakiyesi ve vadesi. | Motor customer_balances yalnız 120 müşteri carilerini okur. | yok | B06 | 22 |
| **Yazara/serbest çalışana yapılan ödeme** `yazar_odemesi` | logo | Yazar/serbest çalışan carileri (CLFLINE); telif gider hesapları (EMFLINE) | Cari ↔ CRM kişi: doğrulanmadı | telif ödemesi, yazara ödediğimiz, çevirmen ödemesi, stopaj | Logo'da muhasebeleşmiş ödeme ve gider. | CRM hakediş/sözleşme tutarı ödeme değildir. | yok | B01 | 21 |
| **Tahsil süresi (DSO, ortalama tahsil günü)** `tahsilat_suresi` | logo | LG_FFF_DD_PAYTRANS (CROSSREF) | — | ortalama tahsilat vadesi, kaç günde tahsil, geç ödeyen, tahsil süresi, ödeme süresi | Planlanan: plan tarihi − fatura tarihi (kalem başına); gerçekleşen: kapatan ödeme tarihi − fatura tarihi. | 2026'da kapama kaydı yok → gerçekleşen hesaplanamaz (karar 07); CRM müşteri vade tanımı ayrı. LOGO.md: 2026 PAYTRANS 139.648 satırın 0'ında CROSSREF, 14'ünde PAID dolu; PAYTRANS.DATE_ vade tarihidir (işlem tarihi PROCDATE). | yok | B04 | 17 |
| **Döviz** `doviz` | logo | LG_FFF_DD_INVOICE (TRCURR, TRNET); CLFLINE dövizli alanlar | — | döviz, euro, dolar, kur, kur farkı, dövizli | İşlem para birimi bazında; dövizler toplanmaz. | Sözleşme para birimi CRM'de ayrı. | kısmi: currencies | B14 | 17 |
| **Risk / kredi limiti** `risk_limiti` | karma | LG_FFF_CLCARD / risk alanları (Logo); AccountBase 'Kredi Limiti', new_siparis risk alanları (CRM) | Vergi no (müşteri) | risk limiti, kredi limiti, limit doluluk, risk blokesi | Finansal risk sorusunda Logo risk limiti; sipariş onay süreci sorusunda CRM 'Risk Limit Onayı'. | CRM kredi limiti ile Logo risk limiti farklı tanımlanabilir (K0822). | yok | B08 | 14 |
| **Kasa** `kasa` | logo | LG_FFF_KSCARD; LG_FFF_DD_KSLINES | — | kasa, nakit, kasa defteri | Kasa kartı bakiyesi ve hareketleri. | Muhasebe 100 hesabı ile kasa modülü farklı olabilir. | yok | B02 | 14 |
| **Ödeme vadesi tanımı / ödeme planı** `vade_tanimi` | karma | LG_FFF_PAYPLANS, CLCARD.PAYMENTREF (Logo); new_odemevadesiBase, AccountBase 'Vade Gün' (CRM) | new_odemevadesi 'Logo Kodu' alanı | vade, tanıdığımız vade, ödeme planı, peşin, vadeli | Fatura vadesi Logo ödeme planından; müşteri sözleşme vadesi CRM'den. | İki sistemde farklı tanımlı olabilir (K0855). | yok | B08 | 13 |
| **Nakit akışı ve pozisyon** `nakit_akisi` | logo | Banka/kasa/çek/ödeme planı tabloları | — | nakit pozisyonu, nakit girişi, ödeme sıkıntısı, beklenen tahsilat, ödeme takvimi | Gerçekleşen: banka+kasa hareketi; beklenen: vadesi gelen alacak/borç ve çekler. | Beklenen nakit tahmindir; CRM sözleşme ödeme takvimi ve planlı baskılar ayrı kaynaktır. | yok | B02 | 11 |
| **Saha masraf formu** `masraf_formu` | yok |  | — | masraf formu, masraf beyanı, saha masrafı | CRM sözlüğünde masraf formu varlığı bulunamadı; gerçekleşen masraf Logo gider hesaplarında. | Kaynak yokken sayı üretilmemeli. | yok | B29 | 7 |

### satış

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Net ciro** `net_ciro` | logo | LG_FFF_DD_STLINE; LG_FFF_DD_INVOICE | — | ciro, net satış, hasılat, satış geliri, ne kadar sattık (TL), satış rakamı, iadeler düşülmüş satış, cirosu | Malzeme satırı (LINETYPE 0) LINENET: satış TRCODE 7/8/9 eksi iade 2/3; iptal hariç; iskonto sonrası KDV hariç. | CRM sipariş tutarı (new_siparis), CRM sevkiyat tutarı (Logo kopyası, sonradan fiyat düzeltmesini taşımaz), CRM kampanya 'Gerçekleşen Ciro', etkinlik 'gelir' alanı ciro değildir. INVOICE.NETTOTAL (KDV dahil fatura toplamı) ciro değildir. Muhasebe 600 hesabı ayrı kavramdır. 'Ciro edilen çek' çek devridir. LOGO.md: STLINE TRCODE 9 satırlarının hepsi hizmet (LINETYPE 4); motorun 7/8/9 + LINETYPE 0 koşulu 9'u fiilen dışlar. 2026-09'da satır net ciro 245,63 Mn, başlık NETTOTAL 245,56 Mn. | **var**: net_sales | — | 125 |
| **Satılan adet** `satilan_adet` | logo | LG_FFF_DD_STLINE | — | kaç kitap sattık, satış adedi, adet, satış miktarı, net adet | STLINE AMOUNT, TRCODE 7/8 (hizmet 9 hariç); net adet = 7/8 miktarı − 2/3 iade miktarı. | CRM sipariş adedi, CRM sevkiyat/malzeme hareketi adedi (irsaliye kısmı Logo olayını ikinci kez sayar), CRM satış hedefi adedi, telife esas adet. | **var**: sold_quantity, net_quantity | — | 49 |
| **Fatura toplamı** `fatura_tutari` | logo | LG_FFF_DD_INVOICE | — | fatura tutarı, KDV dahil toplam, fatura toplamı, kesilen faturalar | İptal edilmemiş satış faturası NETTOTAL (genel toplam, vergiler dahil). | Net ciro (LINENET) ile karıştırılır; CRM sevkiyat 'fatura numarası' Logo faturasının kopyasıdır. | **var**: invoice_amount, invoice_statistics | — | 25 |
| **Uygulanan iskonto** `iskonto` | logo | LG_FFF_DD_STLINE (LINETYPE 2); LG_FFF_DD_INVOICE.TOTALDISCOUNTS | — | iskonto, ıskonto, indirim, indirim oranı, fatura altı indirim, satır iskontosu | Satır düzeyi: iskonto satırı (LINETYPE 2) TOTAL / malzeme satırı (LINETYPE 0) TOTAL. | CRM iskonto listesi (tanımlı oran), CRM sipariş iskontosu, kampanya net/ek iskontosu tanımdır, uygulanan değildir. APPROVAL alanından okuma reddedildi. | yok | B10 | 25 |
| **İade (satış iadesi)** `iade` | logo | LG_FFF_DD_STLINE; LG_FFF_DD_INVOICE | — | iade, geri gelen, iade faturası, iadeler | İptal edilmemiş malzeme iadesi TRCODE 2/3 LINENET, pozitif gösterim. | CRM iade talebi/iade onayı (süreç), Logo iade irsaliyesi (STFICHE) ile fatura farklı belge; alış iadesi (TRCODE 6) ayrı kavram. | **var**: return_amount | — | 17 |
| **İade oranı** `iade_orani` | logo | LG_FFF_DD_STLINE | — | iade oranı, iade yüzdesi, iadelerin ciroya oranı | Tutar: return_amount / sales_amount; adet: (sold_quantity − net_quantity) / sold_quantity. Payda açıkça söylenir. | Payda net ciro mu brüt satış mı, tutar mı adet mi belirsiz kalabilir. | **var**: return_amount, sales_amount, operations:ratio | — | 9 |
| **Fatura veri kalitesi (mükerrer, başlık-satır farkı, satırsız)** `fatura_kalitesi` | logo | LG_FFF_DD_INVOICE; LG_FFF_DD_STLINE | — | mükerrer fatura, satır toplamı tutmayan, sıfır tutarlı fatura, proforma | Aday üretir; kesin hüküm vermez. | Faturasız sevk tek başına hata değildir. | kısmi: invoice_duplicates, invoice_reconciliation, orphan_invoice_lines | B15 | 8 |
| **Fırsat / teklif** `firsat_teklif` | crm | OpportunityBase (12); QuoteBase (1) | — | fırsat, teklif, kazanma oranı | Pratikte kullanılmıyor. | Boş tablodan 'sıfır' cevabı veri eksiği olarak söylenmeli. | yok | B29 | 8 |
| **Fatura sayısı** `fatura_sayisi` | logo | LG_FFF_DD_INVOICE | — | kaç fatura, fatura adedi, kesilen fatura | İptal edilmemiş satış faturası başlıkları, TRCODE 7/8/9 (satır değil). | İade faturası sayısı ayrıdır (motor saymaz); irsaliye, e-fatura/e-arşiv sayısı farklı kavram. Çelişki: motor 7/8/9 sayar (2026: 88.757), proje KPI'ı 2/3/7/8/9 (2026: 92.137); tanım kararı gerekli. | **var**: invoice_count | — | 4 |
| **Fatura türü (toptan/perakende/hizmet/ihracat)** `fatura_turu` | logo | LG_FFF_DD_INVOICE.TRCODE | — | toptan, perakende, hizmet faturası, ihracat faturası, vade farkı faturası | TRCODE 8 toptan, 7 perakende, 9 hizmet/diğer. | Kanal (SPECODE2) ile karıştırılır: 'perakende' kanal değeri de olabilir. | kısmi: metric tanımlarında süzgeç olarak | B11 | 4 |
| **Brüt satış (iade öncesi)** `brut_satis` | logo | LG_FFF_DD_STLINE | — | brüt satış, satış tutarı, iade öncesi satış, brüt ciro | LINENET, TRCODE 7/8/9; iadeler düşülmeden, iskonto sonrası KDV hariç. | Kullanıcı 'brüt' ile iskonto öncesi tutarı (TOTAL) da kastedebilir; GROSSTOTAL KDV içermez, TOTALVAT çıkarmak anlamsızdır. | kısmi: sales_amount | B10 | 2 |
| **Ortalama/medyan fatura, sepet** `fatura_istatistigi` | logo | LG_FFF_DD_INVOICE | — | ortalama fatura, sepet tutarı, ortalama sepet | Müşteri başına satış fatura başlığı NETTOTAL ortalaması/ortancası. | 'Sepet' CRM sipariş başlığı ortalaması olarak da okunabilir (karar 2). | **var**: invoice_statistics | — | 2 |
| **E-ticaret sitesi ve pazar yeri** `eticaret_pazaryeri` | portal | semantic_commerce_*; semantic_trendyol_*; semantic_intl_* | — | site siparişi, Trendyol, Amazon, sepet terk | Portal alanları; finansal gerçekleşme yine Logo faturasında. | Logo ORFICHE e-ticaret siparişleri ile aynı olayın farklı görünümü olabilir. | portal: chat_portal:eticaret-* | — | 0 |

### sipariş

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Satış siparişi (B2B/saha)** `siparis` | crm | new_siparisBase; new_siparissatiriBase | Sipariş → new_sevkiyat (new_siparisid) → new_sevkiyat.new_logicalref = LG_FFF_DD_STFICHE.LOGICALREF (yıl firması + tarih şart) → INVOICE | sipariş, girilen sipariş, sipariş aldık, sipariş tutarı, sipariş adedi | CRM sipariş (logo_oncesi_surec): Logo ORFICHE'de kopyası yok; cevap 'sipariş' diye etiketlenir, 'satış' denmez. | Logo ORFICHE ayrı akıştır (e-ticaret/perakende, TS1 önekli), CRM siparişiyle toplanmaz. TİMAŞ iş tanımı #15 (sipariş = Logo ORFICHE) 2026-10-01 ölçümüyle çelişiyor. | yok | B16 | 68 |
| **Sipariş süreci (onay, statü, tip, iptal nedeni)** `crm_siparis_sureci` | crm | new_siparisBase | — | onay bekleyen, risk blokesi, iptal nedeni, sipariş tipi, ödeme şekli, kampanya kodu, faturalanmayı bekliyor, yolda | new_siparis.statuscode (satır statüsü anlamsız) ve tip/ödeme alanları. | Logo'da bu durumların karşılığı yok. | yok | B16 | 30 |
| **Açık / bekleyen sipariş** `acik_siparis` | karma | new_siparis/new_siparissatiri açık statü (CRM, B2B); LG_FFF_DD_ORFLINE CLOSED=0 (Logo, e-ticaret) | Toplanmaz; kaynak ayrı gösterilir | bekleyen sipariş, açık sipariş, sevk edilmemiş, termini geçmiş, kısmen sevk | B2B/saha için CRM açık sipariş; Logo ORFLINE (AMOUNT > SHIPPEDAMOUNT) yalnız e-ticaret/perakende akışı. | Motorun open_orders modu Logo ORFLINE okur → B2B bekleyen siparişleri görmez. CRM 'bekleyen ürün' ayrı kavram. Termin CRM'de boş (karar 1). | kısmi: open_orders (yalnız Logo akışı) | B16 | 25 |
| **Bekleyen ürün (karşılanamayan talep)** `bekleyen_urun` | crm | new_bekleyenurunBase | new_urunid → product → new_kitap.new_stokkodu = ITEMS.CODE | bekleyen ürün, karşılanamayan, stok yokluğundan bekleyen, backorder | Stok yokken sipariş satırından düşen talep (Bekleyen / Siparişe Eklendi / İptal); satış değildir. | Bekleyen sipariş (açık sipariş) ile karıştırılır. | yok | B16 | 13 |

### pazarlama

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Müşteri/okul ziyareti** `ziyaret_okul` | crm | new_etkinlikBase (ziyaret şekli); new_ziyaretyerleriBase (kurum/okul evreni) | Okul Account ↔ Logo cari: doğrulanmadı | ziyaret, okul ziyareti, saha ziyareti, görüşme | Ziyaret = etkinlik kaydı; new_ziyaretyerleri okul/kurum dizinidir (öğrenci sayısı vb.). | Ziyaret yerleri tablosu ziyaret kaydı değildir. | yok | B18 | 35 |
| **Etkinlik** `etkinlik` | crm | new_etkinlikBase; new_new_etkinlik_contactBase; new_etkinliktipiBase | — | etkinlik, imza günü, söyleşi, fuar, okul buluşması | Planlandı/Tamamlandı/İptal; çoğunluğu satış ziyareti. | Etkinlik-yazar bağı (karar 5); etkinlik ≠ standart Appointment. | yok | B18 | 22 |
| **Etkinlik gideri** `etkinlik_gideri` | karma | Logo gider hesapları 740.03 / 760.45 / 760.47.470; new_etkinlik gider alanları (CRM) | Etkinlik ↔ gider fişi bağı yok | etkinlik gideri, fuar masrafı, konaklama ulaşım, yazar katılım ücreti | Gerçekleşen gider Logo hesapları (2026: 4,83 Mn ₺); etkinlik kırılımı CRM'den. | CRM gider alanı eksik (9.275 ₺); kapanış fişi 760'ı sıfırlar. | yok | B18 | 21 |
| **Reklam planı ve harcaması** `reklam` | karma | new_reklamplaniBase (CRM, 71); semantic_ads_* (portal dijital reklam); Logo reklam gider hesabı | Reklam planı 'Fatura Numarası' alanı ↔ Logo fatura: doğrulanmadı | reklam, tanıtım bütçesi, mecra, reklam ajansı, sosyal medya reklamı | Plan/onay CRM; dijital harcama portal; gerçekleşen gider Logo. | Üç kaynak aynı adı taşır. | yok | B20 | 18 |
| **Kampanya** `kampanya` | crm | new_kampanyaBase; new_new_kampanya_account; new_new_kampanya_product; new_siparissatiri.new_kampanyaid | Sipariş satırı kampanyası → sevkiyat → Logo fatura | kampanya, kampanya iskontosu, kampanya cirosu, kampanya kodu | CRM kampanya kartı (planlanan/gerçekleşen ciro, net/ek iskonto). | Portal indirim kampanyaları (semantic_kampanya_*) ve Email/SMS kampanyası (campaign) ayrı; CRM 'gerçekleşen ciro' Logo cirosu değildir. | yok | B20 | 16 |
| **Numune / bedelsiz / yazar nüshası** `numune_bedelsiz` | karma | Logo bedelsiz fatura satırı / sarf fişi; CRM sipariş tipi (Okul Örneği, Öğretmen Örneği), new_hediyetalebi | Sevkiyat logicalref | numune, tanıtım kitabı, bedelsiz, yazar nüshası, promosyon | Gerçekleşen çıkış Logo; talep/amaç CRM. | Bedelsiz satırların maliyet/telif hesabına girmesi (karar 7). | yok | B20 | 11 |
| **Sosyal medya ve dijital reklam** `sosyal_medya_dijital` | portal | semantic_social_*; semantic_ads_* | — | sosyal medya, dijital reklam, tıklama, ROAS | Portal alanları. | CRM reklam planı ayrı. | portal: chat_portal:sosyal-medya, reklam | — | 2 |

### sözleşme

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Sözleşme** `sozlesme` | crm | new_sozlesmeBase; new_sozlesmetarafiBase; new_new_sozlesme_new_kitapBase | — | sözleşme, kontrat, telif sözleşmesi, süresi dolacak, yenilenmemiş, imza | Aktif sözleşme (statecode=0, pasif hariç); başlangıç/bitiş/revize/yenileme/fesih ayrı. | Logo'da sözleşme yok; süresi dolan sözleşme otomatik satış yasağı değildir; ana sözleşme metin UUID'si soy ağacı değildir. | kısmi: relational:contract, contract_expiry, contract_overlap, contract_author_roles, contract_revision_evidence, contract_author_differences | B22 | 41 |
| **Telif hakedişi / tahakkuku** `telif_hakedis` | karma | CRM telif oranı; LG_FFF_DD_STLINE net satış adedi/tutarı | new_new_sozlesme_new_kitap → new_kitap.new_stokkodu ↔ ITEMS.CODE | hakediş, telif tahakkuku, telif ödeyeceğiz, yazara düşen | Sözleşme telif oranı × telife esas net satış (iadeler düşülmüş); CRM'de hakediş tablosu yok (new_odeme 50 kayıt). | Ödenmiş telif (Logo) ile hakediş (hesap) ayrı; yazar = hak sahibi varsayılamaz. | yok | B22 | 35 |
| **Telif oranı / telif tanımı** `telif_orani` | crm | new_sozlesmeBase (Karton K/E-Kitap/Yurtdışı Telif %); new_teliftanimBase; new_hakBase | — | telif oranı, telif yüzdesi, kademeli telif, royalty | Sözleşme telif yüzdesi alanları ve telif tanımı kademeleri. | new_olasitelif (Olası Telif Oranı) önerilen oran değildir (Kural C11 çürüdü); yayın kurulu önerilen oranı ayrı. | yok | B22 | 13 |
| **Telif avansı** `avans` | karma | new_sozlesmeBase 'Avans Tutarı' (CRM); yazar carisi avans hareketi (Logo) | Yazar carisi ↔ sözleşme tarafı: doğrulanmadı | avans, avans bakiyesi, avans mahsubu | Sözleşmedeki avans; ödenen avans Logo'da. | Avans mahsubu için satışa dayalı hakediş gerekir. | yok | B22 | 10 |
| **Yurtdışı hak alım/satışı** `hak_satisi` | crm | new_sozlesmeBase (Telif Satış tipi); new_new_sozlesme_new_ulkeBase; new_new_sozlesme_new_dilBase | — | hak satışı, yabancı hak, ajans, çeviri hakkı | Sözleşme tipi ve taraf tipine göre (karar 9). | Ülke-bölge AND/OR anlamı doğrulanmadı. | kısmi: contract_overlap | B22 | 7 |
| **Dijital ve yan haklar** `dijital_hak` | crm | new_sozlesmeBase (İletim Hakkı, E-Kitap, Sesli Kitap, Z-Kitap) | — | e-kitap hakkı, sesli kitap hakkı, dijital hak, iletim hakkı | Yalnız Telif Alış sözleşmelerinde hak bayrakları. | Hak varlığı satış iznini tek başına kanıtlamaz. | yok | B22 | 1 |

### üretim

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Baskı/üretim kartı (matbaa, forma, kâğıt, cilt)** `baski_karti` | crm | new_uretimBase | new_kitap → new_stokkodu; 'Logo Üretim Adeti' alanı | baskı, matbaa, forma, kâğıt cinsi, cilt, tiraj, baskı talebi, tekrar baskı | Aktif üretim kaydı ve statü (Editoryal Hazırlık … Depo Girişi). | Logo kopyası adayı; gerçekleşen adet/maliyet Logo'da. | yok | B07 | 40 |
| **Baskı maliyeti (gerçekleşen)** `baski_maliyeti` | logo | Komple Baskı alış faturası (SPECODE = stok kodu); OUTCOST | — | baskı maliyeti, birim maliyet, matbaa faturası, en pahalı baskı | M9 pricing/model.py tek hesap; kâğıt Timaş'ın (15001) ayrı. | CRM üretim 'Toplam Maliyet' girilen/planlanan tutardır. | yok | B07 | 26 |
| **Üretim emri / basılan adet** `uretim_emri` | logo | PRODORD; LG_FFF_DD_STLINE TRCODE 13 (üretimden giriş), 12 (sarf) | CRM new_malzemehareketi.new_logouretimfisi = STFICHE.SPECODE | üretim emri, baskı yapıldı, basılan adet, üretimden giriş, sarf | Tamamlanmış üretim emri (STATUS 3) ve üretimden giriş. | CRM üretim kartı aynı baskının süreç kaydı; CRM malzeme hareketi üretim girişi kısmi kopya. | yok | B07 | 25 |
| **Baskı önerisi** `baski_onerisi` | crm | new_baskioneriBase (582) | Kitap → stok kodu | baskı öneri, önerilen baskı adedi | CRM öneri kaydı; ayrıca Baskı Öneri modülü (Power BI birebir). | İki kaynak farklı öneri üretebilir. | yok | B07 | 5 |

### müşteri

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Satış temsilcisi** `satis_temsilcisi` | karma | LG_SLSMAN + INVOICE.SALESMANREF (Logo); SystemUserBase, AccountBase.OwnerId, new_satishedefleri.new_BMT (CRM) | Yok: SystemUser ↔ Logo satış elemanı eşlemesi ölçülmedi; ad eşleme yasak. | temsilci, satış elemanı, BMT, saha ekibi, bölge müdürü | Ciro/tahsilat kırılımında Logo satış elemanı; ziyaret/sipariş/hedef sorularında CRM kullanıcısı. | İki sistemdeki temsilci kimlikleri farklı; BMT bazen kanal hesabıdır (Hepsiburada, D&R). | yok | B11 | 28 |
| **Kanal / müşteri grubu** `kanal` | logo | LG_FFF_CLCARD.SPECODE2 | — | kanal, müşteri grubu, cari grubu, grup kodu, zincir, dağıtımcı, kitapçı, e-ticaret, online, okul kanalı | Logo cari kartı SPECODE2; boş kod 'Grup kodu boş'. | CRM müşteri tipi/firma tipi, CRM sipariş tipi (B2B, Pazaryeri, Okul Örneği), CRM satış hedefi bölgesi/BMT (D&R, Hepsiburada hesapları) ayrı sınıflamalardır. LOGO.md: SPECODE2 kartların %86'sında boş (cironun %2,5'i); yazım varyantları var (BAYI/BAYİ, YURTDIŞI/YURTDISI). | **var**: dimension:channel | — | 15 |
| **Müşteri (Logo cari)** `musteri_logo` | logo | LG_FFF_CLCARD | CLCARD.TAXNR ↔ CRM AccountBase.new_VergiNo | müşteri, cari, bayi, firma, Kitapyurdu, D&R | Logo CLCARD CODE + DEFINITION_; satış/bakiye soruları buradan. | Aynı ad birden çok cari kartı olabilir; ad benzerliği kimlik değildir; CRM Account ayrı kayıttır. | **var**: dimension:customer | — | 14 |
| **Müşteri kaydı (CRM firma)** `musteri_crm` | crm | AccountBase | AccountBase.new_VergiNo ↔ CLCARD.TAXNR | firma kaydı, kayıtlı müşteri, aktif müşteri, müşteri tipi, pasif müşteri | statecode=0 ve aktif durum nedeni (Aktif Müşteri); pasif kayıt hiçbir ekranda gösterilmez. | Logo cari kartıyla bire bir değildir (çoklu kart, vergi no boş). | kısmi: active_customers, duplicate_customer_tax, customers_without_contacts, contact_multiple_customers | B18 | 14 |
| **Satışın ili / ülkesi** `musteri_il` | logo | LG_FFF_CLCARD.CITY/COUNTRY | — | il, şehir, İstanbul, Anadolu, yurtdışı, ülke, ihracat | Logo cari kartı (fatura adresi) il/ülke alanı. | CRM adres ili (CustomerAddress 'Kullanılmayan Adres' / new_adres) ve CRM satış bölgesi farklıdır. | yok | B11 | 11 |
| **Müşteri iletişim ve coğrafya** `musteri_iletisim` | crm | AccountBase; ContactBase; CustomerAddressBase; new_adresBase; new_illerBase | — | ilgili kişi, e-posta, telefon, adres, illere göre müşteri dağılımı | Aktif CRM kayıtlarında doluluk ve ham/normalize şehir. | Hangi adres tablosunun güncel olduğu doğrulanmadı; Logo fatura adresi ayrıdır. | kısmi: customer_geography, customers_without_contacts | B18 | 4 |

### künye

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Yazar (kişi)** `yazar` | crm | ContactBase (new_yazarmi); new_eserkatilimBase (rol Yazar) | Satışa: eser katılımı → kitap → new_stokkodu ↔ ITEMS.CODE | yazar, müellif, kalem, yazarlarımız, yerli/yabancı yazar | Aktif Contact + aktif Yazar rolüyle eser katılımı; ortak yazarlı kitap satışı bölünmez. | Logo'da yazar alanı yok; new_yazartext künye metni kimlik değil; yazar ≠ telif hak sahibi; çevirmen/editör de katılımcıdır. | **var**: active_authors, dimension:author, dimension:author_group, author_* raporları | — | 31 |
| **Yayın tarihi / yeni çıkan kitap** `yayin_tarihi` | crm | new_kitapBase.new_ilkyayintarihi; new_sonyayintarihi | Satışa stok kodu üzerinden | yeni çıkan, bu yıl çıkan, ilk baskı tarihi, son yayın, eski kitap | İlk baskı tarihi (new_ilkyayintarihi); CreatedOn katalog eklenmesidir, yayın değildir. | Tek bir 'yayın tarihi' alanı kanıtlanmadı. | kısmi: publication_dates, catalog_additions | B24 | 23 |
| **Tür / kategori / hedef kitle** `tur_kategori` | crm | new_turBase; new_kitaplikBase; new_urunkategorisiBase; new_kitapBase hedef yaş | Satışa stok kodu üzerinden | tür, kategori, çocuk kitabı, yetişkin, roman, kitaplık, set ürün, çeviri/telif kitap | CRM kitap sınıflamaları (alan seçimi doğrulanmalı). | Logo kart grup/özel kodu farklı sınıflama olabilir. | yok | B24 | 13 |
| **ISBN** `isbn` | crm | new_kitapBase.new_isbn13; new_isbnlistesiBase | — | ISBN, yayın numarası, ISBN listesi | Kitap kartındaki ISBN13; ISBN listesi ayrı varlık. | Logo barkodu ISBN'e benzeyebilir ama kimlik değildir. | **var**: book_quality, duplicate_isbn | — | 5 |
| **Eser katılımı ve roller** `eser_katilimi` | crm | new_eserkatilimBase; new_katilimcitipiBase | — | çevirmen, editör, illüstratör, katılımcı, rol | Kitap + katılım sağlayan (Contact) + rol. | Account katılımcı Contact değildir. | kısmi: relational:participation | — | 5 |
| **Bandrol** `bandrol` | crm | new_kitapBase 'Bandrol Durumu'; new_uretim 'Bandrol Yapışacak mı' | — | bandrol, bandrol stoğu, bandrol talebi | Kart/üretim alanları; bandrol alım gideri Logo'da. | Bandrol Logo'da malzeme kartı olabilir (karar 4 listesi). | yok | B29 | 3 |
| **Dizi / seri** `dizi_seri` | crm | new_diziBase; new_seriBase | Satışa stok kodu üzerinden | dizi, seri | Kitap kartındaki dizi/seri bağı. | — | yok | B24 | 3 |
| **Kitap künyesi** `kitap_kunyesi` | crm | new_kitapBase; new_kitapgecmisiBase | new_kitapBase.new_stokkodu ↔ ITEMS.CODE | kitap kartı, künye, baskı sayısı, sayfa, kapak, satış durumu | Aktif CRM kitap kartı (statecode=0, Aktif). | Logo ITEMS yalnız kod/ad; aynı adlı farklı kitaplar birleştirilmez. | kısmi: relational:book, book_quality, book_change_history | — | 2 |
| **Yayınevi / marka** `yayinevi` | crm | new_markaBase (new_kitap.new_yayineviid) | Satışa stok kodu üzerinden | yayınevi, marka, imprint | Kitap kartındaki aktif marka. | Önceki yayınevi alanı ayrı; Account olarak yayınevi (rakip/tedarikçi) farklı. | **var**: dimension:publisher, publisher_* | — | 0 |
| **Alt marka** `alt_marka` | crm | new_markaBase (new_yayinciid); new_yaynevialtmarkaBase | Satışa stok kodu üzerinden | alt marka, imprint, seri markası | new_yayinciid aktif Marka. | İki alt marka alanı var; marka-alt marka hiyerarşisi kanıtlanmadı. | **var**: dimension:subbrand, subbrand_consistency | — | 0 |

### muhasebe

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Gider ve masraf merkezi** `gider_masraf_merkezi` | logo | LG_FFF_DD_EMFLINE; LG_FFF_EMCENTER | — | gider, masraf, masraf merkezi, personel gideri, kira, pazarlama gideri, kargo gideri | 7xx gider hesapları, masraf merkezi kırılımı. | CRM masraf/bütçe kayıtları plan veya talep olabilir. | yok | B01 | 30 |
| **Muhasebe fişi, mizan, hesap** `muhasebe_fisi_mizan` | logo | LG_FFF_EMUHACC; LG_FFF_DD_EMFICHE; LG_FFF_DD_EMFLINE | — | mizan, fiş, mahsup, hesap bakiyesi, 120, 320, 600, 770, gelir tablosu | Genel muhasebe hareketleri ve hesap planı. | 600 hesabı STLINE net cirosu ile aynı değildir. | yok | B01 | 29 |
| **KDV, BA/BS, stopaj, e-belge** `kdv_vergi` | logo | LG_FFF_DD_INVOICE / STLINE vergi alanları; EMFLINE 191/391/360 | — | KDV, matrah, BA, BS, stopaj, tevkifat, muhtasar, e-fatura, e-arşiv | Fatura vergi alanları ve vergi hesapları. | — | yok | B01 | 21 |
| **Sabit kıymet / demirbaş** `sabit_kiymet` | logo | Logo sabit kıymet kayıtları; EMFLINE 25x/257/770 amortisman | — | demirbaş, amortisman, sabit kıymet | Muhasebe sabit kıymet hesapları. | CRM new_demirbaslar zimmet kaydıdır (107). | yok | B01 | 5 |

### stok

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Stok miktarı** `stok_miktari` | logo | LG_FFF_DD_STLINE (IOCODE); stok toplam görünümleri | — | stok, depoda kaç adet, elde kalan, stoğu bitmek üzere, negatif stok | Giriş (IOCODE 1,2) − çıkış (3,4), yalnız cari yıl kopyası (açılış devri içinde). | CRM raf/lot/sayım defteri (malzeme hareketi, koli stoğu) depo operasyonudur; eski yıl kopyasıyla birleşim çift sayar. IOCODE STLINE'da çıkış 4, STFICHE'de çıkış 3 kodlanır. | **var**: stock, stock_history | — | 20 |
| **Stok değeri** `stok_degeri` | logo | LG_FFF_DD_STLINE; maliyet alanları | — | stok değeri, kaç liralık mal, envanter değeri, ölü stok değeri | Stok miktarı × doğrulanmış birim maliyet. | Muhasebe 153 bakiyesi ayrı; maliyet tanımı doğrulanmadı. | yok | B05 | 13 |
| **Stok kartı ana verisi** `stok_karti` | logo | LG_FFF_ITEMS; LG_FFF_ITMUNITA; LG_FFF_UNITBARCODE | ITEMS.CODE ↔ new_kitapBase.new_stokkodu | stok kartı, barkod, birim, KDV oranı, asgari stok, reçete | Logo malzeme kartı alanları. | CRM 'Stok Kartları' (new_kitap) künye kartıdır; ürün (product) ayrı. | yok | B08 | 11 |
| **Stok devir hızı / gün kapsamı** `stok_kapsami` | logo | LG_FFF_DD_STLINE | — | stok devir hızı, kaç günlük stok, stok kapsama, iki yıllık stok | Gün kapsamı = stok / son dönem günlük satış; devir hızı = dönem satış adedi / ortalama stok. | Devir hızı formülü (açılış+güncel)/2 motorda yok. | kısmi: stock(lookback_days, coverage_days) | B31 | 9 |
| **Ambar fişleri (transfer, sayım, fire, hurda)** `ambar_hareketi` | logo | LG_FFF_DD_STFICHE (TRCODE 25/50/51/11/12) | — | transfer, sayım farkı, fire, sarf, hurda, konsinye | Logo stok fişleri. | Sayım ve raf transferi gerçekte CRM depo defterinde (Logo TRCODE 50/51 neredeyse boş). | yok | B09 | 8 |
| **'Kitap' kapsamı** `kitap_kapsami` | karma | LG_FFF_ITEMS; new_kitapBase (tip) | ITEMS.CODE ↔ new_stokkodu | kitap, yayın, ürün, eser | Bugün bütün malzeme kartları; karar 4 bekliyor (yalnız kitap tipleri). | Ayraç, bandrol, kahve gibi kartlar 'en çok satan kitap' listesine girebilir. | kısmi: dimension:book | — | 4 |

### lojistik

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Kargo** `kargo` | karma | Logo 760.34.342 kargo gideri / kargo firması faturası; new_kargobilgisiBase, new_kargotakipbilgisiBase (CRM) | Yok | kargo, gönderi, desi, teslim süresi, alıcı ödemeli | Maliyet Logo; gönderi ayrıntısı CRM (2024 tek seferlik Aras yüklemesi, tutar KDV hariç). | CRM kargo verisi güncel değil. | yok | B21 | 22 |
| **İrsaliye** `irsaliye` | logo | LG_FFF_DD_STFICHE | — | irsaliye, e-irsaliye, faturalanmamış irsaliye, alım irsaliyesi, iade irsaliyesi | Satış/alış/iade irsaliye fişleri ve fatura bağı. | CRM sevkiyat kaydı irsaliye kopyasıdır. | kısmi: orphan_invoice_lines | B09 | 19 |
| **Sevkiyat (malzeme çıkışı)** `sevkiyat` | logo | LG_FFF_DD_STFICHE; LG_FFF_DD_STLINE (TRCODE 7/8, IOCODE 4) | CRM new_sevkiyat.new_logicalref = STFICHE.LOGICALREF | sevk, sevkiyat, gönderdik, sevk adedi | Logo malzeme çıkışı; CRM sevkiyatı aynı olayın kopyasıdır (yön CRM→Logo). | CRM sevkiyat ve malzeme hareketi Logo olayını ikinci kez sayar; TRCODE 25 depolar arası sevk müşteri sevki değildir. IOCODE STLINE'da çıkış 4, STFICHE'de çıkış 3 kodlanır. | kısmi: open_orders.shipped_quantity | B09 | 15 |

### süreç

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Proje / yayın programı** `proje` | crm | new_projeBase; new_projeasamalariBase; new_projegrBase | Proje ↔ kitap: new_kitap.new_projekarti / new_kitapprojesi (N:N ara tablo yanıltıcı) | proje, yayın programı, aşama, ön maliyet, proje bütçesi | Aktif proje kayıtları; aşama/statü alanları. | Logo proje kodu (gider kaydı) CRM projesi değildir. | kısmi: relational:project, relational:project_stage | B23 | 18 |
| **Yayın kurulu kararı** `yayin_kurulu` | crm | new_yayinkurulutoplantilariBase; new_projegrBase | — | yayın kurulu, kurul kararı, önerilen telif, önerilen fiyat, önerilen baskı adedi, onaylanan proje | Toplantı kararı (Kabul/Red/Bekleme/Geliştirme) ve öneri alanları. | Portal editoryal başvuru/kurul tabloları (semantic_editorial_*) ayrı; yönetim kurulu kararı (portal kurul) farklı kavram. | yok | B23 | 15 |
| **İş planı** `is_plani` | crm | new_isplaniBase; new_plansorumlulariBase | — | iş planı, görev, geciken iş, tamamlanma | Aktif iptal olmayan açık iş planları. | Modül 2025-12'den, plan sorumluları 2022-09'dan beri güncellenmiyor. | kısmi: work_due, work_due_missing, work_stage_history, relational:work | B23 | 6 |
| **Editör** `editor` | crm | new_kitapBase (new_Editor, new_projeeditoru, new_yayinyonetmeni); new_uretim.new_sorumlueditor | Satışa stok kodu üzerinden | editör, proje editörü, yayın yönetmeni | Rol alanları ayrı ve kimlikli. | Portal editör görevleri (semantic_editorial_tasks) ayrı. | kısmi: editor_assignments | B24 | 4 |
| **Fiziki arşiv** `arsiv` | crm | new_fizikiarsivBase (11.948); new_fizikiarsivrafBase | — | arşiv, emanet, arşiv dosyası | Arşiv durumu ve emanet alan kişi. | Arşiv ürün/baskı kaydıdır; sözleşme dosyası alanı doğrulanmalı. | yok | B29 | 4 |
| **Randevu, görev, telefon** `randevu_gorev` | crm | TaskBase; AppointmentBase; PhoneCallBase; ActivityPointerBase | — | randevu, görev, toplantı, telefon görüşmesi, açık aksiyon | Yazar randevusundan doğan açık görevler. | Randevu (33) ve telefon (21) kaydı ölü; görevlerin çoğu iş akışı üretimi. | kısmi: open_author_actions, appointments_with_actions | B29 | 3 |
| **CRM kullanım / kayıt girişi** `kullanici_aktivitesi` | crm | SystemUserBase; AuditBase; CreatedBy alanları | — | CRM'i kullanmayan, kayıt sayısı, veri giren | Kullanıcı başına oluşturulan kayıt. | Servis hesapları (Timas CRM) süzülmeli. | yok | B29 | 3 |

### karlılık

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Satılan malın maliyeti ve kâr** `maliyet_kar` | logo | LG_FFF_DD_STLINE (AMOUNT × OUTCOST) | — | kâr, brüt kâr, marj, kârlılık, zarar, SMM, katkı payı | Satır LINENET − AMOUNT × OUTCOST; satış artı, iade eksi. | Maliyet semantiği doğrulanmadı; son alış/satış fiyatı maliyet yerine geçmez; CRM 'senaryo kârı' ayrı. LOGO.md: 2026-09 satış satırlarının yalnız %0,8'inde OUTCOST dolu; güncel aylarda kâr hesaplanamaz. | kısmi: profit (typed gap) | B05 | 34 |

### ticari koşul

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Liste fiyatı** `fiyat_listesi` | karma | LG_FFF_PRCLIST (Logo); new_fiyatlistesiogesiBase, PriceLevel (CRM) | CRM fiyat listesi öğesi Logo ref alanı taşıyor (doğrulanmadı) | liste fiyatı, fiyat listesi, zam, satış fiyatı, kapak fiyatı | Fatura karşılaştırmasında Logo fiyat kartı; hangi liste: karar 8. | Aynı kitap için birden çok geçerli kanal listesi; faturayı listeye bağlayan alan yok. | yok | B08 | 23 |
| **Tanımlı iskonto (iskonto listesi)** `iskonto_tanimi` | crm | new_iskontolistesiogeleriBase | Müşteri: vergi no | iskonto listesi, tanımlı iskonto, müşteri iskontosu | CRM iskonto listesi öğeleri. | Uygulanan iskonto Logo faturasındadır; Logo cari kartı indirim alanı da tanımdır. | yok | B08 | 11 |

### analiz

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Kohort / varlık-yokluk / pay sıralaması** `musteri_kohort` | logo | LG_FFF_DD_STLINE; LG_FFF_CLCARD | — | yeni müşteri, kaybedilen müşteri, hiç satmayan, ilk kez, pareto, cironun %80'i | Dönemler arası varlık/yokluk ve kümülatif pay. | Kaç yıl kopyası okunacağı (karar 6). | yok | B13 | 21 |
| **Tahmin / senaryo** `tahmin` | yok |  | — | bu hızla gidersek, beklenen, olursa ne olur, tahmini | Motor tahmin üretmez; ayrı tahmin modülü (TimesFM/baskı öneri) gerekir. | Tahmin gerçekleşen gibi sunulmamalı. | yok | B27 | 9 |
| **Dış veri (enflasyon, dini takvim, pandemi)** `dis_veri` | yok |  | — | enflasyon, Ramazan, pandemi | Kaynak yok; dönem kullanıcıdan alınır. | — | yok | B28 | 3 |

### hedef

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Hedef-gerçekleşen** `hedef_gerceklesme` | karma | new_satishedefleriBase; LG_FFF_DD_STLINE | Kitap: new_StokKodu = ITEMS.CODE; BMT ↔ Logo satış elemanı/kanal: ölçülmedi | hedefin neresindeyiz, hedef tutturma, gerçekleşme oranı, hedefin gerisinde | Hedef adet ↔ Logo faturalı net adet, kitap düzeyinde. | Ciro hedefi sorulursa 'hedef yalnız adet' denmeli. | kısmi: sold_quantity, net_quantity | B19 | 19 |
| **Satış hedefi** `satis_hedefi` | crm | new_satishedefleriBase | new_StokKodu = ITEMS.CODE (2026'da 68.327/68.327) | hedef, satış hedefi, bütçe hedefi, temsilci hedefi, bölge hedefi | Kitap × BMT × yıl aylık ADET hedefi (tutar yok); 2023-24 bölge × kitap. | '2000'/'1991' etiketli yıl kodları onaysız kullanılmaz; 114 tekrar eden anahtar; TL hedef yok. | yok | B19 | 12 |

### köprü

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Müşteri köprüsü (Logo↔CRM)** `musteri_koprusu` | karma | LG_FFF_CLCARD.TAXNR; AccountBase.new_VergiNo | Boş olmayan vergi no birebir metin eşitliği | eşleşmeyen müşteri, iki sistemde unvan farkı, vergi no farkı | Her vergi grubunun satışı bir kez. | Ad benzerliği/TC dönüşümü yok; vergi no farkını görmek için başka kimlik gerekir. | kısmi: cross_customer_sales_quality | B25 | 16 |
| **Kitap köprüsü (Logo↔CRM)** `kitap_kodu_koprusu` | karma | LG_FFF_ITEMS.CODE; new_kitapBase.new_stokkodu | ITEMS.CODE ↔ new_stokkodu (aktif anahtar tekilliği zorunlu, LEFT JOIN, ölçü çoğalmaz) | eşleşmeyen kitap, CRM'de olmayan stok kartı | Çoğul CRM kartında satış dağıtılmaz; eşleşmeyen satış NULL CRM alanıyla korunur. | ISBN, barkod ya da ad eşleme kimlik değildir. | kısmi: cross_book_sales_quality | B25 | 13 |

### tedarik

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Satınalma (alış faturası)** `satinalma` | logo | LG_FFF_DD_INVOICE (alış); LG_FFF_DD_STLINE | — | alış, satınalma, mal alımı, kâğıt alımı, hizmet alımı, matbaa faturası, alış iadesi | Gerçekleşmiş alış faturası satırları net tutarı. | Alış fiyatı SMM değildir; matbaa faturası baskı maliyetidir. | kısmi: purchase_prices | B06 | 21 |
| **Açık satınalma siparişi** `acik_satinalma_siparisi` | logo | LG_FFF_DD_ORFICHE/ORFLINE (alış) | — | açık satınalma siparişi, gelmemiş sipariş | İptal edilmemiş, kapanmamış alış sipariş satırları. | — | **var**: open_orders(order_kind=purchase) | — | 2 |
| **Alış birim fiyatı** `alis_fiyati` | logo | LG_FFF_DD_STLINE (alış) | — | alış fiyatı, birim alış fiyatı | Tedarikçi+malzeme+birim+para birimi+ay ağırlıklı birim alış fiyatı. | Maliyet (SMM) yerine kullanılamaz. | **var**: purchase_prices | — | 1 |

### denetim

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Denetim izi / kayıt meta** `denetim_izi` | karma | Logo CAPIBLOCK_* oluşturma/değiştirme alanları; CRM AuditBase, CreatedBy/ModifiedBy | — | kim değiştirdi, geriye dönük, mesai dışı, iptal edilen, seri boşluğu | Kaynak sistemin kayıt meta alanları. | ModifiedOn aşama girişi değildir. | yok | B15 | 19 |

### destek

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Destek talebi / şikâyet** `destek_talebi` | portal | semantic_support_*, semantic_mail_* (portal); new_talepyonetimiBase (BT, ölü); IncidentBase (34) | — | destek talebi, şikâyet, çözüm süresi, açık talep | Portal müşteri hizmetleri alanı. | CRM talep yönetimi 2024-07'den beri ölü. | portal: chat_portal:musteri-destek, kurumsal-eposta | — | 13 |

### pazar

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Rakip kitap** `rakip_kitap` | crm | new_rakipkitapBase (30.415) | — | rakip, rakip fiyatı, rakip yayınevi | CRM rakip kitap eşlemesi. | Portal dağıtımcı kataloğu (D&R/Başarı) ayrı pazar verisi. | yok | B29 | 10 |
| **Dağıtımcı / perakende kataloğu** `dagitimci_katalog` | portal | semantic_pazar_dagitim_titles (API_URUN_DB) | — | D&R kataloğu, Başarı Dağıtım, baskısı yok, D&R fiyatı | Portal dağıtımcı katalog alanı. | D&R müşteri satışı Logo'dadır. | portal: chat_portal:dagitimci-katalog | — | 0 |

### plan

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Bütçe** `butce` | karma | new_butcekalemiBase, new_pazarlamamoduluBase (CRM); semantic_mkt_month_budget (portal) | Yok | bütçe, pazarlama bütçesi, etkinlik bütçesi, proje bütçesi | Bütçe kaynağı soru başına netleştirilir; Logo'da bütçe yok. | set1000 'butce' konusundaki sorular çoğu gider-geçen yıl karşılaştırması. | yok | B25 | 6 |

### İK

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Personel (İK)** `personel_ik` | portal | İK modülü (sohbete kapalı); Logo 335/770 personel hesapları | — | personel, işe alım, performans, SGK, kıdem | İK kayıtları sohbete bağlanmaz (closed); personel gideri muhasebe sorusudur (Logo). | Personel gider/borç hesapları finans sorusudur, İK değil. | portal: chat_topics:ik (closed) | — | 6 |

### yönetim

| Kavram | Sahip | Birincil tablo(lar) | Köprü | Gündelik ifadeler | Varsayılan tanım | Karışma riski | Motor | Boşluk | Soru |
|---|---|---|---|---|---|---|---|---|---:|
| **Yönetim kurulu kararı** `kurul_karari` | portal | semantic_kurul_* | — | yönetim kurulu, kurul aksiyonu | Portal kurul alanı. | Yayın kurulu (CRM) farklı. | portal: chat_portal:kurul | — | 1 |
