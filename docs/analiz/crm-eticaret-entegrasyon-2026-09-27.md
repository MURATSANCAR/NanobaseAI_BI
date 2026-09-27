# CRM → e-ticaret (T-soft ve diğer kanallar) entegrasyon analizi (2026-09-27)

Kaynak: Timas_MSCRM (192.168.0.28), `zekiai` kullanıcısıyla yalnız SELECT; sorgular test sunucusu
`nanobase-direct` üzerinden koşuldu. T-soft API'sine ve dış servislere gidilmedi. Kişisel veri ve
kimlik bilgisi içeren kolonların değeri okunmadı/yazılmadı; yalnız varlığı belirtildi.

Sınır: `zekiai` kullanıcısının VIEW DEFINITION ve VIEW SERVER STATE yetkisi yok. Görünümlerin
(view) SQL metni, `sys.sql_expression_dependencies`, oturum/sorgu istatistikleri okunamadı. Bu yüzden
"görünümü kim okuyor" sorusu veriyle cevaplanamadı; aşağıdaki eşleştirmeler kolon değerlerinin
birebir karşılaştırılmasıyla çıkarıldı.

## Özet (en önemli bulgu)

**CRM'den T-soft'a veri iten hiçbir mekanizma veritabanında görünmüyor.** Ne plugin, ne iş akışı,
ne servis uç noktası, ne de T-soft'a yapılan çağrıların günlüğü var. "Düzeltmeyi CRM'e yazalım,
CRM'in mevcut entegrasyonu T-soft'a taşısın" varsayımı bu veriyle **desteklenmiyor**. Olası tek
yol, T-soft'un (ya da bir ara yazılımın) CRM'deki SQL görünümlerini (`Tsoft_KitapDetay`,
`NY_WEB_*`) **kendisinin çekmesi**; bu da doğrulanamadı ve Timaş BT'ye sorulmalı. Bulguların bir
kısmı ters yönü gösteriyor: `new_tsoftaktif` bayrağı CRM dışından, doğrudan SQL ile doldurulmuş
gibi duruyor.

## 1. Mekanizma: veri CRM'den nasıl çıkıyor?

### 1.1 Plugin'ler (SdkMessageProcessingStep)
- 55 özel derleme (assembly) var: `Cube.Timas.*` (2013–2021), `Omerd.*` (2018–2024), `Cube.Omerd.*`,
  `RWB2016`, `MobileCrm`. En yenisi `Omerd.CustomWorkflows` (2024-09-09).
- `new_kitap` (ObjectTypeCode 10001) üzerinde yalnız şu adımlar kayıtlı:
  | Derleme / tip | Mesaj | Aşama | Mod | Filtre alanları | Kayıt |
  |---|---|---|---|---|---|
  | Cube.PrePlugin.AutoNumbering | Create | 20 (pre) | senkron | — | 2022-05-31 |
  | Cube.Timas.KitapGecmisi | Create | 40 (post) | senkron | — | 2016-03-24 |
  | Cube.Timas.KitapGecmisi | Update | 40 | senkron | `new_baskisayisi,new_resimurl,new_kdvdahilfiyat` | 2016-03-24 (değ. 2016-12-02) |
  | Cube.Timas.KitapKontrol | Create | 10 (doğrulama) | senkron | — | 2017-09-19 |
  | Cube.Timas.KitapKontrol | Update | 10 | senkron | `new_ean13,new_stokkodu` | 2017-12-13 |
- Hiçbir plugin adı/tipi T-soft, web, ürün aktarımı ya da dış HTTP çağrısını çağrıştırmıyor.
  `Product` (1024) üzerinde yalnız `Cube.Timas.Urun.PrePlugin` (Create/Update, 2015) ve otomatik
  numaralandırma var.
- `ServiceEndpointBase` = **0 satır** (Azure Service Bus / webhook tanımı yok).
- `PluginTraceLogBase` = 0 satır.
- **Kesin:** CRM'de T-soft'a veri gönderen plugin yok.

### 1.2 İş akışları (WorkflowBase, etkin)
- `new_kitap` üzerinde yalnız iki isteğe bağlı (on-demand) akış: "Çocuk/Kültür Föy Bilgileri Hazır"
  (e-posta bildirimi). Otomatik tetiklenen kitap akışı yok.
- `Product` üzerinde "Ürün Kartında Yapılan Her Değişiklikte Ürün Related Alanını Güncelle":
  tetik listesinde site bayrakları var (`new_timascomtr, new_yenitimascomtr, new_b2ctimascom,
  new_timascocukcom, new_genctimascom, new_sincapkitapcom, new_kitapsipariscom, new_webservice,
  new_websatisdurum, new_b2cid, new_b2cslug, ...`). Yaptığı iş: `new_new_relatedentitymodifiedon`
  zaman damgasını güncellemek (delta okuma için). **Son 30 günde 332 kez "sonsuz döngü" hatasıyla
  iptal edildi** (StatusCode 31) → bu akış bugün sağlıklı çalışmıyor.
- "Eser Katılımı Güncellendiğinde Kitap Related Alanını Güncelle" (2021-08-18): `new_kitap.
  new_relatedentitymodifiedon` damgasını günceller. Aynı desen: bir dış tüketici değişen kayıtları
  bu damgaya bakarak çekecek şekilde tasarlanmış (Omerd B2C sitesi, 2020–2021).
- AsyncOperation son 30 gün: T-soft/web/aktarım adlı hiçbir sistem işi yok; en yoğunlar sipariş
  e-postaları ve üretim aşama akışları.

### 1.3 Görünümler (çekme / pull modeli)
CRM veritabanında dış sistemin okuması için hazırlanmış görünümler var:

| Görünüm | Oluşturma / son değişiklik | Satır | Not |
|---|---|---|---|
| `Tsoft_KitapDetay` | 2022-12-13 / 2022-12-13 | 13.629 | Adı T-soft; 18 kolon: kitapadi, stokkodu, barkod, kapakgorseli, kitapspot, Kitaplık, Dizi, Yazar, Fiyat, Sayfasayisi, Ebat, FoyMetni, KapakVeCilt, Kagit, Renkveresim, Ilkyayintarihi, Orjinaladi, Orjinaldili. **Filtre yok** (T-soft aktif olsun olmasın bütün kitaplar). 2022'den beri değişmemiş → büyük olasılıkla T-soft'a geçişte ilk yükleme için. |
| `NY_WEB_StokKarti` | 2020-10-08 / **2026-09-21** | 12.518 | 96 kolonlu ürün beslemesi (aşağıda). Hâlâ bakımı yapılıyor. |
| `NY_WEB_Kategori`, `_Gr`, `NY_WEB_AnahtarKelime(_Gr)`, `NY_Web_EserKatilimci(_Gr)`, `NY_WEB_Fiyat`, `NY_WEB_Fiyat_Degisen`, `NY_WEB_Marka`, `NY_WEB_Temalar`, `NY_WEB_Rozetler`, `NY_WEB_OzelGunler`, `NY_WEB_Yaslar`, `NY_WEB_Siniflar`, `NY_WEB_Dersler`, `NY_WEB_Kavramlar`, `NY_WEB_ListeGruplari`, `NY_WEB_Vitrinler`, `NY_WEB_SetAltUrun`, `NY_WEB_Spesifikasyon_Coklu_Esleme`, `NY_Web_Haberler`, `NY_Web_Etkinlik`, `NY_WEB_SosyalMedya`, `NY_WEB_Adres` | 2020-10 … 2021-06 | — | Omerd B2C sitesi (2020-10) için; `ModifiedOn` + `Kaynak` kolonları delta okuma içindir. 2021'den beri dokunulmamış. |
| `NY_Web_ModifiedOn_Control` | 2021-09-16 | — | Bağlı sunucuya gidiyor, bugün hata veriyor ("Named Pipes … could not open") → ölü. |
| `NY_Web_UserName_Password` | 2018 | — | B2B kullanıcı adı/şifre kolonlarını açığa çıkarıyor (değer okunmadı). Güvenlik notu. |

Görünümlerin tanımı okunamadığı için T-soft'un bugün bunlardan birini okuyup okumadığı
**bilinmiyor**. Bağlı sunucular: CRMDATBASE, LOGODATABASE (192.168.0.25), MYSQL, RAPOR (.11),
TULPAR (.167), PORTALBILGI — T-soft'a giden bağlı sunucu yok.

### 1.4 Web servis günlükleri — kimin için?
- `new_webservicelogBase` (117.587 satır, 2022-05-25 → 2026-09-20): tamamı
  `Omerd.Timas.RestAPI.B2B` servisi. **T-soft ile ilgisi yok**; bayilerin/kitapçıların Timaş'tan
  ürün listesi çektiği B2B API'si (aşağıda §2).
- `tblRestAPILogs` (361 satır): `Omerd.Timas.RestAPI.B2C`, 2020-09-23 → 2021-02-19. Eski B2C
  sitesinin CRM'den çektiği uçlar: `UrunListesiGetir`, `GuncellenenUrunListesiGetir`,
  `SilinenUrunListesiGetir`, `KategoriListesiGetir`, `MarkaListesiGetir`,
  `EserKatilimciListesiGetir`, `SiparisOlustur`, `KisiOlustur`, `AdresOlustur`... → Omerd
  sitesi CRM'den **çekiyordu**, 2021'de kapandı.
- `tblB2BRestAPILogs` (248 satır, 2021-09 → 2022-05): B2B API'nin eski günlüğü; 2022-05'te
  `new_webservicelog`'a taşınmış.
- `LineerSoft_Log` (20 satır): "PrcList tablosuna fiyat güncellendi" — fiyat aktarımı iz kaydı, eski.
- `obs_webservisBase` (11 satır, 2021-08-18): `CustomerService.SaveCustomer` test kayıtları
  (kişisel test verisi içeriyor; aktarılmadı).

### 1.5 Zaman çizelgesi (veriden çıkarılan)
- 2015-03 … 2016-02: ilk web sitesi; `new_web*` varlıkları (kategori, vitrin, slider, video,
  haber) ve `new_kitap.new_aktarim` = "Güncelleme/Yeni Kayıt – 13 Mart 2015" (3.074 kitap) ile
  toplu aktarım, `new_token` dolduruldu.
- 2018-09 … 2021-05: Omerd B2C sitesi; CRM'e 23.680 B2C sipariş (`new_siparis.new_b2cid`) düştü,
  son sipariş **2021-05-20**. 2020-10'da `NY_WEB_*` görünümleri + B2C REST.
- 2022-12-13: `Tsoft_KitapDetay` görünümü → T-soft'a geçiş dönemi.
- 2026-07-01: `new_tsoftaktif` alanıyla ilgili ilk denetim kaydı (aşağıda §3.3).
- T-soft dönemi (2022 sonrası) timas.com.tr siparişleri **CRM'e gelmiyor** (son 12 ayda
  `new_b2cid`/`new_yenib2cid`/`new_dissiparisno` dolu sipariş = 0).

## 2. `new_webservicelog` — ne kaydediyor?

Kolonlar: `new_name` (servis adı), `new_methodname`, `new_clientIP`, `new_requestdate`,
`new_requestJSON`, `new_responsedate`, `new_responseJSON`, `new_status`, `new_errorcode`,
`new_errormessage`, `new_accountid` (çağıran firma), `new_webuserid`.

- Tek servis: `Omerd.Timas.RestAPI.B2B`. Metodlar: `MoveNext` 110.993 (oturum/token alma),
  `UrunListesiGetir_JSON` 6.369, `UrunListesiGetir_XML` 225.
- Yön: **dışarıdan CRM'e gelen** okuma istekleri (bayi → Timaş). CRM'den dışarı yazma yok.
- İstek gövdesi Key/Value listesi: `grant_type`, `username`, `password` — **düz metin kimlik
  bilgisi günlükte duruyor** (değer okunmadı; güvenlik notu olarak BT'ye iletilmeli).
- Cevap gövdesi saklanmıyor (`new_responseJSON` uzunluğu 2) → hangi ürün alanlarının döndüğü
  günlükten çıkarılamıyor.
- Durum: `status=0, errorcode=1` 104.328 (%88,7), `status=1` 13.150 başarılı, `errorcode=100` 65,
  `status=3` 44. Hataların %99'u hız sınırı: "Son 24 saatte 5 kere istek atıldığı için daha fazla
  istek atamazsınız!" (firma kartında `new_requestcount`, "Cari – 24 Saatte Request Count Sıfırla"
  akışı). Diğerleri: kullanıcı adı/şifre boş (151), yetki yok (35).
- Hacim: 2022-06 … 2025-07 ayda ~3.000 (neredeyse hepsi tek bayinin hız sınırına takılan
  döngüsü); 2025-08'den beri ayda 8–82. Son 30 gün: haftada 1 çağrı çifti (pazar 23:00), hepsi
  başarılı; son kayıt 2026-09-20.
- Çağıranlar: ~40 bayi/kitapçı/dağıtıcı firma hesabı (`new_accountid` → AccountBase). Kitap/ürün
  kaydına bağ yok (ürün kimliği kolonu yok) → `new_kitap` ile birleştirilemez.
- **Sonuç:** Bu tablo "düzeltme T-soft'a ulaştı mı" takibi için **kullanılamaz**.

## 3. Alan eşleştirmesi CRM → web

### 3.1 `NY_WEB_StokKarti` kolonlarının kaynağı (12.518 kitapla birebir karşılaştırma)
`StokId` = `new_kitap.new_kitapId` (Product değil).

| Görünüm kolonu | CRM alanı (`new_kitapBase`) | Eşleşen / dolu | Güven |
|---|---|---|---|
| StokName | `new_name` | 12.518 / 12.518 | kesin |
| ProductName | `new_urunadi` | 12.124 / 12.146 | kesin |
| Barkod | `new_ean13` | 12.518 | kesin |
| Spot | `new_kitapspotu` | 6.869 / 6.869 | kesin |
| ArkaKapak | `new_ozet` ("Arka Kapak Metni") | 9.373 / 9.373 | kesin |
| OneCikanlar | `new_kitabinonecikanyanlari` ("Bu Kitap Neden Önemli?") | 6.471 | kesin |
| EnOnemliCumle | `new_kitabinenonemlicumlesi` | 5.459 | kesin |
| EditörGorusu | `new_editorunkitabaveyazaradairgorusleri` | 4.991 | kesin |
| Alintilar | `new_alintlar` | 1.622 | kesin (kısmi dolu) |
| Resim | `new_resimurl` ("Kapak Url", göreli yol `guid\guid.jpg`) | 7.886 / 7.886 | kesin |
| TanitimUrl | `new_ProductWebsite` (YouTube embed linki) | 439 / 439 | kesin |
| SM_Hastag | `new_hastag` | 3.587 | kesin |
| Key_Count | `new_new_anahtarkelime_new_kitap` (N:N) sayısı | 6.246 kitapta >0 | tahmin |
| Web_Ktg | web kategori bağı sayısı | 3.593 kitapta >0 | tahmin |
| SiteGosterim | bilinmiyor (4.389 = 1; `new_tsoftaktif` ile örtüşmüyor) | — | bilinmiyor |
| SatisDurumName | Product.`new_websatisdurum` (1 Açık / 2 Ön Sipariş / 9 Kapalı) — neredeyse hepsi "Kapalı" | — | tahmin |

### 3.2 `Tsoft_KitapDetay` kolonlarının kaynağı (13.620 kitap)
| Kolon | CRM alanı | Eşleşen | Güven |
|---|---|---|---|
| kitapadi | `new_name` | 13.608 | kesin |
| barkod | `new_ean13` | 12.525 | kesin |
| kitapspot | `new_kitapspotu` | 7.102 | kesin |
| FoyMetni | `new_TantmFyMetni` ("Tanıtım – Föy Metni") | 4.653 / 4.653 | kesin |
| kapakgorseli | `new_resimurl` (başına "https://" eklenmiş, bozuk URL) | — | kesin |
| Yazar | `new_yazartext` | 11.487 | kesin |
| Fiyat | `new_kdvdahilfiyat` | 11.232 | kesin |
| Kitaplık, Dizi, Ebat, Sayfa… | ilgili lookup/alanlar | — | tahmin |

Dikkat: `new_kitaptanitimwebmetni` ("Kitap Tanıtım – Web Metni") hiçbir görünümde yok ve T-soft
aktif kitapların yalnız 60'ında dolu.

### 3.3 T-soft alanları için olası CRM kaynakları
T-soft tarafında ne tuttuğumuzu biliyoruz (`connections.py`), CRM tarafında dolu alanları biliyoruz;
**aradaki aktarım kanıtlanamadı**. Tablo "bir aktarım varsa kaynağı bu olur" anlamında:

| T-soft alanı | Olası CRM kaynağı | T-soft aktif 6.578 kitapta doluluk | Güven |
|---|---|---|---|
| ProductName | `new_name` / `new_urunadi` | ~%100 | tahmin (ad eşleşmesi T-soft verisiyle kontrol edilmeli) |
| Details (açıklama) | `new_ozet` (arka kapak) veya `new_TantmFyMetni` | ozet 6.128, föy 3.282 | tahmin |
| SeoTitle / SeoDescription | CRM'de karşılığı **yok** | — | kesin (alan yok) |
| SearchKeywords | `new_AnahtarKelimeler` (metin) / `new_anahtarkelime` N:N | 2.687 | tahmin |
| Barcode | `new_ean13` | 6.578 | kesin (SEO modülü bu anahtarla bağlıyor) |
| Model (yazar) | `new_yazartext` | — | tahmin |
| Brand (yayınevi) | `new_yayineviid` / `new_YayneviAltMarka` | — | tahmin |
| Kategoriler | `new_webkategorileritext` ("Çocuk;6 - 10 Yaş Öykü Hikaye" biçimi) | 2.839 | tahmin |
| ImageUrls | `new_resimurl` (göreli yol) | 6.283 | tahmin |
| SeoLink | CRM'de karşılığı **yok** | — | kesin (alan yok) |
| Fiyat | `new_kdvdahilfiyat` (asıl fiyat kaynağı büyük olasılıkla Logo) | — | tahmin |
| Stok | `new_webstok` **hiç dolu değil** (6.578'in 0'ı); stok Logo'dan gelir | — | kesin (CRM'den gelmiyor) |

`new_tsoftaktif` ("TSOFT Aktif") üzerine:
- 6.578 kitapta True; bunların **5.969'unun `ModifiedOn` tarihi 2026-07-01'den önce** ve bu
  alan için denetim kaydı yok → değer **CRM arayüzü/API'si dışında, doğrudan SQL ile** yazılmış
  (denetim ve ModifiedOn atlanmış). En olası açıklama: T-soft'taki aktif ürün listesi barkodla
  CRM'e işaretlendi (**T-soft → CRM** yönü).
- 2026-07-01'den beri alanın denetim kaydı 256 (174 oluşturma, 69 güncelleme, 13 diğer); ağırlıkla
  "Timas CRM" (`TIMAS\mujdatcengiz`) ortak hesabı ve editörler. Yani yeni kitaplarda elle
  işaretleniyor.
- Hiçbir plugin/akış bu alanı tetik olarak kullanmıyor.

## 4. Diğer e-ticaret / pazar yeri kanalları

- **API entegrasyonu kanıtı yok:** Trendyol, Hepsiburada, Amazon, n11, idefix, D&R, Kitapyurdu
  adına tablo, kolon, plugin, akış, günlük yok. Tek iz: "Trendyol Deneme Siparisi" firma kartı
  (2020-09-23, Omerd B2C testi).
- Pazar yerleri CRM'de **toptan müşteri (cari)** olarak var: KİTAPYURDU YAYINCILIK (son 180 günde
  227 sipariş, son 2026-09-26), D-MARKET (Hepsiburada; 34 sipariş, son 2026-09-25), Amazon Turkey
  (iki kart, biri "(B2C)"), Amazon Kindle US, Amazon Seller Central. Firma kanalı seçenek setinde
  `new_firmakanal` = 100000005 "E-Ticaret". Bunlar ürün verisi beslemesi değil, sipariş/fatura
  ilişkisi.
- **B2B portal (kitapsiparis.com.tr):** CRM'e canlı bağlı tek web kanalı. Son 90 günde 4.026
  sipariş `new_gelissekli` = "kitapsiparis.com.tr", `new_yenib2b` bayrağı, `new_webuser`
  (5.090 bayi kullanıcısı; kullanıcı adı ve şifre kolonları var — değer okunmadı). Siparişleri
  "Timas CRM" hesabı oluşturuyor.
- **B2B ürün API'si** (`Omerd.Timas.RestAPI.B2B`, §2): ~40 bayi ürün listesini JSON/XML çekiyor.
- `new_satiskanallari` (kitap, LangId 1055): 1 Timaş Satış Kanalı (13.163), 2 Market (62),
  3 KDD (21), 4 Toplama Set (47), 6 Diğer, 7 Toptan & Eticaret, 8 B2C Toplama Set (336). Pazar
  yeri ayrımı yapmıyor.
- `Product` üzerinde site bayrakları (eski çoklu site yapısı): `new_timascomtr, new_yenitimascomtr,
  new_b2ctimascom, new_timascocukcom, new_genctimascom, new_sincapkitapcom, new_mavikirpicom,
  new_portakalkitapcom, new_carpediemkitapcom, new_antikkitapcom, new_suficomtr,
  new_hekimogluismailcom, new_eglencelibilgicom, new_timasdagitimcom, new_timaspublishingcom,
  new_kitapsipariscom, new_tarcinkafe`, ayrıca `new_b2cid, new_b2cslug, new_websatisdurum,
  new_webonecikansirano, new_webservice (19.860 True)`. `new_websatisdurum` 24.738/24.752
  kartta "Kapalı" → Omerd döneminden kalma, T-soft'u beslemiyor.
- Logo tarafı: `LOGO_DB`'de `LogoEntegrations` ve `L_CAPIWEBCONN` tabloları var (içeriği
  incelenmedi; kimlik bilgisi içerebileceği için okunmadı). `MMX_*` tabloları Mobilmax saha satış
  uygulamasına ait, e-ticaret değil. T-soft'un stok/fiyatı Logo'dan alıyor olması güçlü olasılık —
  BT'ye sorulmalı.

## 5. Web kategori / vitrin tabloları

| Tablo | Satır | Son değişiklik | Ne modelliyor |
|---|---|---|---|
| `new_webkategori` | 27 | 2016-02-19 | ana kategoriler (Aile, Çocuk, Edebiyat, Tasavvuf…) + liste türleri |
| `new_webaltkategori` | 120 | 2016-01-06 | alt kategoriler |
| `new_webkategorilist` | 7 | 2016-02-01 | kategori listeleri |
| `new_webkategoriitem` | 2.483 | 2022-12-23 | kitap ↔ kategori/alt kategori + sayfa sırası |
| `new_webvitrinler` + `new_new_kitap_new_webvitrinler` | 3 / 159 | 2020-12-09 | Omerd sitesi vitrinleri |
| `new_webanasayfacoksatanlar`, `new_webslider`, `new_webvideos`, `new_webhaberetkinlik`, `new_webyaynevleri`, `new_webset` | 1–82 | 2015–2019 | ilk sitenin içerik blokları |

`new_kitap.new_webanakategoriid` 6, `new_webaltkategoriid` 1 kitapta dolu. **CRM bugün site
kategorilerini/vitrinlerini yönetmiyor.** Güncel kategori bilgisi yalnız serbest metin
`new_webkategorileritext` (3.428 kitap; T-soft aktiflerin 2.839'u) — T-soft ağacına benziyor ama
bağ kanıtlanmadı.

## 6. `new_kitapgecmisi` ve denetim kaydı

- `new_kitapgecmisi` (28.637 satır, 2016 → bugün, 2026'da 1.599): `Cube.Timas.KitapGecmisi`
  plugin'i kitap oluşturulunca ve **yalnız** `new_baskisayisi`, `new_resimurl`, `new_kdvdahilfiyat`
  değişince bir satır yazar (`new_kitapid`, `new_degistirenid`, baskı sayısı, KDV dahil fiyat, kapak
  yolu). Metin alanlarını izlemez → SEO düzeltmelerinin takibine yaramaz.
- **Asıl işe yarayan: CRM denetimi (AuditBase).** `new_kitap` varlığında denetim açık ve SEO'ya
  yarayan alanların hepsinde denetim açık (`new_name`, `new_urunadi`, `new_ozet`, `new_kitapspotu`,
  `new_kitaptanitimwebmetni`, `new_tanitimfoymetni`, `new_anahtarkelimeler`,
  `new_webkategorileritext`, `new_resimurl`, `new_tsoftaktif`, `new_webstok`...). Kitapta ayda
  ~3.000–4.000 denetim satırı; son 12 ayda ad 1.797, ürün adı 1.421, özet 905, kapak 667, spot 506,
  anahtar kelime 103, web metni 27 değişiklik. Kendi yazdığımız her değişiklik burada kullanıcı ve
  eski değerle görünür (ChangeData).
- `Product` varlığında denetim kapalı.

## 7. Entegrasyon planı (öneri)

### 7.1 Gerçekçi yol
CRM'e yazmak tek başına T-soft'u güncellemiyor (kanıt yok). İki seçenek:

1. **Önerilen:** SEO alanlarını (SeoTitle, SeoDescription, SeoLink, SearchKeywords, Details)
   **doğrudan T-soft API'sine** yazmak (modülün zaten tasarladığı yol), ama T-soft'a yazma
   yasağı kalkana kadar yalnız öneri+onay. CRM'e **aynı içeriğin kalıcı kopyası** yazılır ki
   kaynak kayıt tutarlı kalsın ve olası bir yeniden yüklemede ezilmesin.
2. Timaş BT/ajans, T-soft'un CRM görünümünden (ya da Logo'dan) düzenli çektiğini doğrularsa:
   o zaman CRM'e yazmak yeterli olur; aşağıdaki alanlar kullanılır.

### 7.2 Yazılacak CRM alanları (CRM Web API yetkisi gelince)
| SEO alanı | CRM alanı | Not |
|---|---|---|
| Ürün adı düzeltmesi | `new_urunadi` (vitrindeki ad) — `new_name` iç ad, stok/Logo eşleşmelerinde kullanılıyor, dokunulmamalı | |
| Açıklama (Details) | `new_ozet` (arka kapak) değiştirilmemeli (basılı metin); web'e özel metin için `new_kitaptanitimwebmetni` ("Kitap Tanıtım – Web Metni", neredeyse boş) | T-soft bu alanı okuyor mu? sorulmalı |
| Spot / kısa açıklama | `new_kitapspotu` | |
| Anahtar kelimeler | `new_AnahtarKelimeler` (metin) ya da `new_anahtarkelime` N:N (`Cube.Timas.KitapAnahtarKelimeleri` Associate plugin'i var) | |
| Kategori | `new_webkategorileritext` | |
| SeoTitle, SeoDescription, SeoLink | **CRM'de alan yok** → yeni özel alan açılmalı (ör. `new_seobaslik`, `new_seoaciklama`, `new_seolink`) ya da yalnız T-soft'ta tutulmalı | |
| Kapak | `new_resimurl` — değişince `new_kitapgecmisi` satırı oluşur | |

### 7.3 Varış takibi
- CRM tarafı: yazma sonrası `AuditBase` (ObjectTypeCode 10001, AttributeMask'ta alanın kolon
  numarası: ozet 66, spot 128, web metni 130, anahtar 359, web kategori 460, ürün adı 472,
  kapak 244, tsoftaktif 580) → "CRM'e yazıldı" kanıtı. `new_webservicelog` bu iş için
  kullanılamaz.
- T-soft tarafı: gece okuması (`product/get` + `FetchDetails`) ile onaylanan değer `Barcode` =
  `new_ean13` üzerinden karşılaştırılır; eşitse "ulaştı", N gece sonra hâlâ farklıysa
  "ulaşmadı" uyarısı. Bu karşılaştırma, bir aktarım olup olmadığını da ilk haftada kendiliğinden
  gösterir.

### 7.4 Riskler
- Aktarım yoksa CRM'e yazılan düzeltme sitede hiç görünmez (en olası durum).
- T-soft'a zaman zaman toplu yeniden yükleme yapılıyorsa (2022'deki `Tsoft_KitapDetay` gibi),
  yalnız T-soft'a yazılan SEO alanları CRM'deki eski metinle ezilebilir → iki tarafa aynı değer.
- T-soft'ta elle yapılan düzenlemeler CRM'de yok; CRM → T-soft bir akış kurulursa bunları ezer.
- `new_name` değişikliği `Cube.Timas.KitapKontrol`'ü tetiklemez ama Logo/stok eşleşmelerini
  bozabilir; `new_ean13`/`new_StokKodu` değişikliği doğrulama plugin'ini tetikler — bunlara
  asla yazılmamalı.
- `new_resimurl`/`new_kdvdahilfiyat` yazmak `new_kitapgecmisi`'ne satır ekler (zararsız).
- Product üzerindeki "Related Alan" akışı sonsuz döngüye giriyor (30 günde 332 iptal); Product'a
  yazılmamalı.
- `new_tsoftaktif` doğrudan SQL ile doldurulmuş; güvenilir "T-soft'ta aktif" kaynağı T-soft'un
  kendisidir.

### 7.5 Timaş BT'ye / entegrasyon firmasına sorulacaklar
1. T-soft ürün kartları (ad, açıklama, görsel, kategori, yazar, yayınevi) nereden besleniyor:
   CRM görünümü (`Tsoft_KitapDetay`, `NY_WEB_StokKarti`), Logo (`LogoEntegrations`?) mı, elle mi?
2. Besleme varsa: hangi sıklıkta, tam mı değişen mi (hangi zaman damgası: `ModifiedOn`,
   `new_relatedentitymodifiedon`?), hangi SQL kullanıcısı / hangi sunucudan?
3. Stok ve fiyat T-soft'a Logo'dan mı gidiyor? Hangi ürün (hangi `ISBN/barkod`) anahtarıyla?
4. T-soft'ta elle düzenlenen alanlar hangileri (SEO başlığı, meta açıklama, link, açıklama)?
   Besleme bunları eziyor mu?
5. `new_tsoftaktif` alanını kim, hangi kaynaktan, nasıl doldurdu (5.969 kayıt denetim dışı)?
   Güncel tutuluyor mu?
6. `new_kitaptanitimwebmetni`, `new_TantmFyMetni`, `new_ozet` — hangisi sitedeki açıklamanın
   kaynağı?
7. SEO başlığı / meta açıklama / SEO link için CRM'de alan açılmasını ister misiniz, yoksa bu
   bilgiler yalnız T-soft'ta mı tutulsun?
8. CRM Web API yazma yetkisi hangi hesapla, hangi varlık/alanlarla sınırlı verilecek?
9. `NY_WEB_StokKarti` 2026-09-21'de değiştirildi — bunu kim, hangi tüketici için kullanıyor?
10. Güvenlik: `new_webservicelog.new_requestJSON` bayi şifrelerini düz metin tutuyor;
    `new_webuser.new_sifre` ve `NY_Web_UserName_Password` görünümü şifreleri açığa çıkarıyor.
11. Pazar yerleri (Trendyol, Hepsiburada, Amazon, Kitapyurdu, idefix) ürün içeriğini kim
    gönderiyor (T-soft pazar yeri modülü, ayrı entegratör, elle)? Onlara giden açıklama da
    bizim düzeltmemizden etkilenmeli mi?
