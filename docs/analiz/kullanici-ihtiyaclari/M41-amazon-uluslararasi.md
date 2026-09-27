# M41 — Amazon ve Uluslararası Platform Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M41.txt`, `specs/M36.txt` (e-kitap/Kindle sınırı), `specs/M4.txt`,
`specs/M6.txt`, `specs/M42.txt`, `ZEKİ_Veri_Haritasi2.html` (M41 satırları: "Amazon Seller/KDP API", "Çevrilmiş içerik ve telif
yönetimi", "Uluslararası dağıtım anlaşmaları", "Amazon kategori bestseller", "Uluslararası rakip fiyat"), `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md` (§4),
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md` (sözleşme tipi Telif Satış, sipariş tipi Amazon Konsinye),
`configs/semantic/knowledge/logo/knowledge/{rules/logo-erp.md, caveats/logo-timas.md}` (YURTDIŞI kanal, döviz faturaları),
`configs/semantic/knowledge/crm/table_descriptions.json` (`new_sozlesmetarafi.new_yurticiyurtdisi`), `PROJECT-MEMORY.md` (M6 hakediş döviz:
`L_DAILYEXCHANGES`), bellek: `customer-vm-web-watch-off`, `no-tech-names-on-screens`, `crm-digital-rights-fields`. Bu belge M42'deki ortak kanal
paketine dayanır. Sunucuya bağlanılmadı; yeni ölçüm yok.

## 1. Modül ne işe yarar

İş tanımı (M41): Amazon (com/de/fr) hedef pazar seçimi, çeviri/yerelleştirme brief'i, uluslararası fiyatlama ve vergi analizi, FBA
değerlendirmesi (K2); Amazon hesabında stok/fiyat senkronu, sipariş ve kargo, A+ içerik şablonu, Amazon arama anahtar kelime izleme
(K1). Çıktılar: platform panosu (pazar bazlı satış, sıralama), listeleme paketi (yerelleştirilmiş başlık/açıklama, A+), aylık rapor.

**Bugünkü durum (kanıtla):** CRM'de Amazon **cari** olarak var: "Amazon Turkey" (iki kart, biri "(B2C)"), "Amazon Kindle US",
"Amazon Seller Central"; CRM sipariş tipleri arasında "Amazon Konsinye" (14) var. API entegrasyonu izi yok. Logo'da kanal kodları
arasında "YURTDIŞI" geçiyor; 2026'da döviz cinsinden fatura sayısı 74 (katalog notu; hepsinin yurtdışı olduğu kanıtlanmadı).
CRM sözleşmelerinde "Telif Satış" tipi 3.725 kayıt ve sözleşme tarafında "Yurtiçi/Yurtdışı Hak" alanı var → TİMAŞ yabancı
yayınevlerine **hak satıyor**; bu M6/M54'ün işidir. Sınır: **e-kitap (Kindle/KDP) M36'dadır**; M41 fiziksel kitabın Amazon ve
yurtdışı satışını kapsar.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Uluslararası satış / ihracat sorumlusu | Birim kanıtı yok (varsayım); Logo kanal kodu YURTDIŞI | Haftalık | Masaüstü |
| Amazon hesap sorumlusu (Seller Central / konsinye) | Varsayım (e-ticaret ekibi) | Her gün (satıcı hesabı varsa) | Masaüstü |
| Yabancı haklar / telif satış sorumlusu | Sözleşme iş akışında "Telif Hakları" aşaması (CRM) | Aylık | Masaüstü |
| Çeviri koordinatörü (yerelleştirme brief'i) | Editoryal (M4 çeviri modülü kullanıcıları) | Proje bazında | Masaüstü |
| Finans (döviz, vergi, gümrük, Amazon hakedişi) | Mali İşler | Aylık | Masaüstü |
| Genel müdür (yeni pazar kararı, K2 onayı) | — | Çeyreklik | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Amazon Türkiye:** iki cari kart ve "Amazon Konsinye" sipariş tipi → TİMAŞ Amazon.com.tr'ye konsinye/toptan mal gönderiyor
  olabilir (varsayım); ayrıca "Seller Central" carisi satıcı hesabı ödemelerini gösterebilir (varsayım). Hangi modelin aktif olduğu
  ve sipariş sayıları **ölçülmedi**.
- **Yurtdışı satış:** Logo YURTDIŞI kanalı ve döviz faturaları; kim, hangi ülkeye, hangi aracı (distribütör, fuar, Amazon) ile
  sattığı bilinmiyor.
- **Uluslararası listeleme / yerelleştirme:** iz yok. CRM ürün kartında `new_timaspublishingcom` site bayrağı var (eski çoklu site
  yapısı; bugünkü kullanımı bilinmiyor).
- **Pazar araştırması (bestseller, rakip fiyat):** portalda yok; müşteride web taraması kapalı.
- **Tıkanma (varsayım):** Amazon'daki gerçek satış (sell-through) TİMAŞ'ın elinde yok; konsinye stokta ne kaldığı belirsiz;
  uluslararası kararlar veri yerine tecrübeyle.

## 4. İhtiyaçlar ve acı noktaları

**Amazon hesap sorumlusu**
1. Amazon'a giden (sell-in) ve Amazon'un sattığı/iade ettiği (rapor varsa) adet; konsinyede kalan stok.
2. Amazon'da listelenmemiş ya da stoksuz görünen TİMAŞ kitapları.
3. Amazon fiyatı ↔ liste fiyatı farkı.

**Uluslararası satış sorumlusu**
1. Yurtdışı cariler ve ülke bazında satış, iade, vade, döviz.
2. Hangi kitaplar yurtdışında (diaspora, Türkçe okur) satıyor; hangi dile çevrilmiş hakları var (M6).
3. Yeni pazar kararı için basit bir kıyas: talep göstergesi × çeviri/hak maliyeti × lojistik.

**Finans**
1. Döviz faturalarının TL karşılığı ve kur farkı; Amazon hakediş/komisyon mutabakatı.

**Yabancı haklar**
1. Satılmış yabancı haklar (Telif Satış sözleşmeleri) ile yurtdışı satış arasında bağ (hangi kitap hangi dilde, hangi yayıncıda).

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Amazon hesap sorumlusu olarak Amazon Türkiye'ye bu yıl gönderdiğimiz ve iade aldığımız adedi kitap bazında görmek istiyorum, çünkü konsinye stoğu takip ederim.
- Amazon hesap sorumlusu olarak Amazon'da stoksuz görünen çok satanları görmek istiyorum, çünkü sevkiyat planlarım.
- Uluslararası satış sorumlusu olarak ülke bazında yurtdışı satışları döviz ve TL olarak görmek istiyorum, çünkü distribütör görüşmesine hazırlanırım.
- Yabancı haklar sorumlusu olarak hakkı satılmış kitapların listesini dil ve yayıncıyla görmek istiyorum, çünkü yeni pazarı önceliklendiririm.
- Çeviri koordinatörü olarak seçilen kitap için hedef pazara uygun başlık/açıklama taslağı istiyorum, çünkü çevirmene brief veririm.
- Genel müdür olarak yeni pazar önerisini gerekçesi ve rakamlarıyla tek sayfada görmek istiyorum.

**Ana ekranlar ve akış**
- Açılış (`/amazon`): Amazon carileri (TR konsinye/satıcı) bu yıl satış, iade, net; yurtdışı kanal toplamı (ülke kırılımı); veri günü.
- Sekmeler: Amazon Türkiye · Yurtdışı satış · Haklar ve diller (M6'dan) · Listeleme paketi (taslak) · Pazar değerlendirmesi.
- En sık 3 işlem: Amazon kitap listesini Excel'e almak (2 tık), ülke kırılımını açmak (1 tık), bir kitap için listeleme taslağı istemek (3 tık).

**Zeki AI'ya soracakları örnek sorular**
- "Amazon Türkiye'ye bu yıl kaç adet gönderdik, ne kadarı iade döndü?"
- "Yurtdışı kanalda en çok satan 20 kitap ve ülkeleri?"
- "Almanya'daki carilere 2025'te ne kadar satış yaptık?"
- "Hakkı İngilizceye satılmış kitaplarımız hangileri?"
- "Şu kitap için Almanya'daki Türkçe okura yönelik Amazon başlık ve açıklama taslağı hazırla."
- "Döviz faturalarımızın bu yılki TL toplamı ne?"

**Otomasyon katmanı**
- K1 (tam otomatik, **salt okuma**): Amazon/yurtdışı satış hesapları, (API bağlanırsa) sipariş/stok/fiyat okuma, anahtar kelime sırası
  okuma (yalnız resmî API ile). İş tanımındaki "stok ve fiyat senkronu, A+ içerik güncelleme" **hesaba yazmadır** → açık soru; bu
  analizde önerilmez.
- K2 (Zeki önerir, insan onaylar): hedef pazar önerisi, uluslararası fiyat önerisi (döviz, KDV/vergi, kargo — varsayımları açık),
  yerelleştirme brief'i, listeleme ve A+ metin taslağı (hesaba gönderilmez).
- K3: yeni pazara giriş, FBA kararı. K4: distribütör/Amazon sözleşmesi.

**Bildirim / uyarı**
- Amazon hesap sorumlusu: konsinye iade eşiği, stoksuz çok satan (API varsa) — haftalık e-posta.
- Yönetim: aylık uluslararası rapor (planlı rapor).

**Onay ve yetki (öneri)**
- `sayfa:amazon` — e-ticaret, uluslararası satış, yabancı haklar, finans, yönetim.
- `ozellik:amazon.pazar-karar` (yeni pazar/fiyat önerisi kararı) — açıkça verilir (genel müdür).
- `ozellik:amazon.baglanti` — yalnız yönetici.
- `ozellik:amazon.taslak` (listeleme/brief taslağı üretme; model harcar).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Amazon carileri ve satış/iade | Logo `CLCARD` + faturalı `STLINE`; CRM `AccountBase` ("Amazon Turkey", "Amazon Kindle US", "Amazon Seller Central") | CRM'de kartlar var | Logo cari kodları ve 2026 ciro **ölçülecek** |
| Konsinye sevk | CRM `new_siparisBase.new_siparistipi = 14`, `new_sevkiyatBase`; Logo irsaliye (TRCODE 8) faturalanmamış satırlar (Kural 18) | Alanlar biliniyor | Sipariş sayısı ve konsinyede kalan **ölçülecek** |
| Amazon satıcı hesabı verisi (sipariş, stok, fiyat, iade, hakediş) | Amazon satıcı API'si (salt okunur rapor/okuma) | Bağlantı **yok** | Hesap türü (satıcı/tedarikçi) ve yetki (Soru 1) |
| Yurtdışı satış | Logo `CLCARD.SPECODE2 = 'YURTDIŞI'` (yazım ölçülecek), `CLCARD.COUNTRY`/`CITY`, `INVOICE.TRCURR`, `TRRATE`; döviz `L_DAILYEXCHANGES` | Kanal kodu biliniyor; 2026'da 74 döviz faturası | Ülke alanı doluluğu **ölçülecek** |
| Satılmış yabancı haklar | CRM `new_sozlesmeBase` (`new_SozlesmeTipi = 1` Telif Satış — TİMAŞ hakkı yurtdışına satar; 5 = Telif Alış), kitap bağı `new_new_sozlesme_new_kitapBase`, taraf `new_sozlesmetarafiBase` (`new_Firma`/`new_kisi`, `new_yurticiyurtdisi`); M6 portal tabloları (`semantic_contracts`) | Tip kodları 2026-09-26'da canlı CRM'de ölçüldü (bellek `crm-digital-rights-fields`); ~3.725 Telif Satış (2026-09-15 profili) | Dil/ülke alanı **ölçülecek** |
| Kitap üst verisi (başlık, yazar, özet, sayfa, ebat) | CRM `new_kitapBase` (`new_name`, `new_urunadi`, `new_ozet`, `new_yazartext`, `new_ean13`) | SEO modülünde okunuyor | Yok |
| Bestseller sırası, rakip fiyat | Yalnız resmî API (satıcı API'si kendi ürünleri için sıra/fiyat verebilir; varsayım) | — | Kazıma yasak |
| Hedef pazar okur demografisi | Dış veri | — | Bu sürümde yok (kullanıcı girer) |
| Vergi/gümrük kuralları | Kullanıcı girer (finans) | — | Parametre tablosu |
| E-kitap (Kindle) | M36 | — | Bu modülde değil |

## 7. Diğer modüllerle bağ

- Girdi: M42 ortak kanal paketi, M6/M54 sözleşme ve haklar, M4 çeviri (yerelleştirme), M43 stok, M44 kargo (yurtdışı gönderim),
  M9 fiyatlama, M39 pazar araştırması.
- Çıktı: M42 çok kanal panosu (Amazon ve yurtdışı satırları), M36 (e-kitap tarafına kitap listesi), M45 finans (döviz), M27 fuar
  (uluslararası fuar hazırlığı).

## 8. Kısıtlar

- Amazon hesabına yazma yok (listeleme, fiyat, stok, A+). Taslaklar portal kaydıdır.
- Müşteride web taraması kapalı: Amazon sayfası, bestseller listesi kazınmaz.
- Döviz ve vergi hesapları yaklaşık öneridir; ekranda varsayımları (kur tarihi, KDV, kargo) açıkça yazılır.
- Telif ve hak: yabancı pazarda satış hakkı sözleşmeye bağlıdır — "yurtdışında satılabilir" ancak M6 hak bilgisi varsa gösterilir;
  yoksa "hak bilgisi yok" yazar (uydurma yok).
- Ekranda teknoloji adı yok (Amazon müşteri platformu adı olarak yazılır); demo veri yok; sayı tavanı yok.
- KVKK: Amazon sipariş verisinde son tüketici bilgisi portala alınmaz.

## 9. Kapsam önerisi

**İlk sürüm (Logo + CRM ile)**
- Amazon carileri karnesi: sevk, fatura, iade, net, kitap bazında; konsinye (faturalanmamış irsaliye) kalan adet.
- Yurtdışı satış karnesi: cari/ülke × yıl, döviz ve TL.
- Haklar ve diller: M6'dan satılmış yabancı haklar listesi (M6 portal tabloları hazırsa; yoksa CRM Telif Satış sözleşmeleri).
- Listeleme/brief taslağı (tek kitap, isteğe bağlı; gönderim yok).

**Sonraki sürüm**
- Amazon satıcı API'si salt okunur bağlantısı (hesap türü ve yetki netleşince): sipariş, stok, fiyat, iade, hakediş.
- Pazar değerlendirme kartı (K2): talep göstergesi (mevcut yurtdışı satış + hak satışı), maliyet parametreleri, gerekçe.
- Uluslararası fiyat simülatörü (döviz, vergi, kargo parametreleri finans tarafından girilir).

**Mevcut kodda yeniden kullanılacaklar**
- M42 `channels/` paketi; `contracts_royalty.py` (Logo `L_DAILYEXCHANGES` döviz okuma, okunamazsa TL + uyarı).
- M6 `contracts.py` / `contracts_api.py` (sözleşme ve hak okuma), `seo_geo/crm.py` (CRM kitap kartı, EAN-13).
- `editorial_translation.py` (M4 çeviri işleri — brief'in çeviri işine bağlanması), `reports.py`, `alerts.py`.

## 10. Uzmanlara sorulacak sorular

1. Amazon ile ilişki hangi modelde: Amazon.com.tr'ye konsinye/toptan (tedarikçi) mi, kendi satıcı hesabımız (Seller Central) mı, ikisi birden mi? Yurtdışı Amazon mağazalarında (com/de) fiziksel kitap satıyor musunuz?
2. Bu modül Amazon hesabına **yazmalı mı** (fiyat/stok/listeleme), yoksa salt okuma + taslak mı kalmalı? Kim onaylar?
3. Yurtdışı satış bugün hangi yollarla yapılıyor (distribütör, fuar, doğrudan kitapçı, Amazon)? Logo'da YURTDIŞI kanalındaki cariler bunlar mı?
4. Hedef pazar önceliği: Türkçe okuyan diaspora (Almanya, Hollanda…) mı, çeviri eserle yabancı okur mu?
5. Uluslararası fiyatlamada kullanılacak kur, KDV/vergi ve kargo parametrelerini finans mı girecek; hangi sıklıkla?

## 11. Başarı ölçütü

- Amazon ve yurtdışı satışın M42 karnesinde ölçülebilir olması (bugün yok) ve aylık rapora girmesi.
- Konsinyede kalan stoğun ay sonunda bilinmesi (fark listesi sıfıra yakın).
- Listeleme/brief taslağı üretilen kitaplardan hesaba konan (insan eliyle) oranı.
- Yeni pazar kararlarının ekrandaki değerlendirme kartıyla alınması (karar kaydı).

## 12. Uzman gözüyle en iyi sistem

Rol: 15 yıllık uluslararası satış ve haklar müdürü. Sektör pratiği (genel bilgi, TİMAŞ verisiyle doğrulanmadı): uluslararası
başarılı yayınevleri üç ayrı işi ayırır: (1) **hak satışı** (çeviri hakkını yabancı yayıncıya satmak — gelir telif), (2) **ihracat**
(Türkçe kitabı diaspora pazarına distribütörle), (3) **platform satışı** (Amazon gibi pazar yerlerinde doğrudan). Amazon'da
metadata kalitesi (başlık, yazar yazımı, kategori, anahtar kelime, A+ içerik) görünürlüğü belirler; stok modeli (FBA ya da satıcı
gönderimi) kargo süresi ve maliyetiyle seçilir. Diaspora pazarında Türkçe kitaplar için Amazon.de ve yerel Türkçe kitapçılar
belirleyicidir (varsayım).

Mükemmel sistem: kitap başına "uluslararası kart": hangi dillere hakkı satılmış, hangi ülkelerde fiziksel satılmış, Amazon'da nerede
ne kadar; pazar değerlendirme kartı rakam + gerekçe; listeleme taslağı hedef dilde, TİMAŞ'ın üslubunda; aylık rapor.

Bir iş günü:
- 09:00 Açılış: Amazon TR'ye bu ay 1.800 adet sevk, 240 iade; konsinyede kalan 3.100.
- 10:00 Yurtdışı: Almanya carilerinde geçen yıla göre %12 artış; en çok satan 20 kitap.
- 11:30 Haklar ve diller: İngilizce hakkı satılmış 14 kitaptan 3'ünün Türkçe baskısı Almanya'da iyi satıyor → fuar notu (M27).
- 14:00 Seçilen 5 kitap için Almanya diasporası listeleme taslağı; çeviri koordinatörüne iletir.
- 16:00 Pazar değerlendirme kartını genel müdüre gönderir (K2 karar bekliyor).

"Bunu görürsem hemen kullanırım":
1. Konsinye sevk − iade − fatura = kalan (Amazon TR).
2. Ülke × kitap yurtdışı satış tablosu.
3. Kitap başına haklar + satış birleşik "uluslararası kart".

"Bunu yaparsanız kullanmam":
1. Amazon hesabına onaysız listeleme/fiyat göndermek.
2. Kazıma ile toplanmış, kaynağı belirsiz rakip/sıralama verisi.
3. Döviz/vergi varsayımını gizleyen kesin fiyat önerisi.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Amazon cari karnesi | Faturalı `STLINE` (TRCODE 7,8,9 − 2,3, `LINENET`), `CLCARD` (Amazon carileri), `LG_211_*` önceki yıllar | `AccountBase` (Amazon kartları, `new_logicalref`) | Cari ↔ platform eşleme adayı (M42 `mapping.py`) | — |
| Konsinye kalan | `STLINE` TRCODE 8, `INVOICEREF = 0`, `BILLED = 0` (Kural 18) | `new_siparisBase` (`new_siparistipi = 14`), `new_sevkiyatBase` | — | Rakam SQL'den |
| Yurtdışı satış | `CLCARD.SPECODE2`, `COUNTRY`, `INVOICE.TRCURR`/`TRRATE`, `L_DAILYEXCHANGES` | — | — | — |
| Haklar ve diller | — | Sözleşme (Telif Satış), `new_sozlesmetarafi.new_yurticiyurtdisi`; M6 `semantic_contracts` | Sözleşme notlarından dil/ülke çıkarımı (kapalı küme: dil listesi) — yalnız alan boşsa, olasılıkla ve insan onayıyla | Yapısız alanı yapılandırır |
| Listeleme / brief taslağı | Satış verisi (bağlam) | `new_kitapBase` (`new_urunadi`, `new_ozet`, `new_yazartext`, `new_kitapspotu`, sayfa, ebat) | Hedef dilde başlık, açıklama, anahtar kelime, A+ metin taslağı; çeviri brief'i | Asıl dil üretimi burada değer katar; gönderim yok |
| Pazar değerlendirmesi | Yurtdışı satış rakamları | Hak satışları | Gerekçe metni (rakamlar SQL'den, parametreler finanstan) | Karar sunumu |
| Aylık rapor | Rakamlar | Rakamlar | 5–8 cümle özet | — |
| Doğal dil soru | Katalog | Katalog | Mevcut soru hattı | — |

Model: `rt.llm_for("amazon")`; toplu taslak `POST /api/v1/llm/jobs` (uzun metin, arka plan). Ekranda yalnız "Zeki AI".

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** (M42 `backend/semantic_bridge/channels/` paketine)
- `channels/amazon.py` — Amazon cari karnesi, konsinye kalan, yurtdışı karne, haklar birleşimi.
- `channels/amazon_client.py` — satıcı API'si **salt okunur** istemcisi (ikinci sürüm; `platforms.py` taban sınıfı, yazma yöntemleri
  engelli, kimlik Yönetim → «Platform bağlantıları»).
- `channels/listing_drafts.py` — listeleme/brief taslakları (model kuyruğu).
- SQL: `channels/sql/logo_amazon_cari.sql`, `logo_konsinye_kalan.sql`, `logo_yurtdisi.sql`, `logo_doviz.sql`, `crm_amazon_siparis.sql`,
  `crm_telif_satis.sql`.

**Tablolar**
- `semantic_intl_params` (tenant_id, pazar, kur_kaynagi, kdv_orani, kargo_birim, komisyon_orani, giren, tarih) — finans girer.
- `semantic_intl_drafts` (id, tenant_id, stok_kodu, pazar, dil, tur 'listeleme'|'aplus'|'brief', metin_json, durum 'taslak'|'kullanildi', yazan, tarih).
- `semantic_intl_market_cards` (id, tenant_id, pazar, gostergeler_json, model_gerekce, karar, karar_veren, tarih).
- Amazon API bağlanınca: `semantic_amazon_products`, `semantic_amazon_orders`, `semantic_amazon_returns` (kişisel veri yok; M40 tablolarıyla aynı şekil).
- Eşleme M42 `semantic_channel_accounts` (`platform = 'amazon'`).

**Uçlar** (`/api/v1/channels/amazon/*`): `GET overview`, `GET accounts`, `GET books?cari=`, `GET consignment`, `GET international?yil=`,
`GET rights`, `GET params`, `PUT params` (finans), `POST drafts` (tek kitap), `GET drafts`, `GET market-cards`, `POST market-cards`,
`POST market-cards/{id}/decision`, `GET status`, `POST test` (yönetici), `GET export/{liste}.xlsx`.

**Ekranlar** `src/canvas/channels/amazon/`: `AmazonHome.tsx` (/amazon), `Consignment.tsx` (/amazon/konsinye), `International.tsx`
(/amazon/yurtdisi), `Rights.tsx` (/amazon/haklar), `Drafts.tsx` (/amazon/taslaklar), `MarketCards.tsx` (/amazon/pazarlar). Menü:
çalışma alanı `platform`, bölüm «Amazon ve yurtdışı».

**Yetki**: `sayfa:amazon`, `sayfa:amazon-konsinye`, `sayfa:amazon-yurtdisi`, `sayfa:amazon-taslaklar`; `ozellik:amazon.pazar-karar`
(explicit), `ozellik:amazon.taslak` (model harcar), `ozellik:amazon.parametre` (finans, explicit), `ozellik:amazon.baglanti` (yönetici).

**Zamanlayıcı**: `timas-channels.timer` içinde gece 04:30 Amazon/yurtdışı karne önbelleği; API bağlanınca sipariş/stok her 30 dk.
Taslaklar isteğe bağlı (zamanlayıcı yok).

**Kabul testleri (gerçek veri)**
1. Amazon carileri: `SELECT CODE, DEFINITION_, SPECODE2 FROM dbo.LG_411_CLCARD WHERE DEFINITION_ LIKE N'%AMAZON%'` (ve `LG_211_CLCARD`) — ekrandaki cari listesiyle birebir; CRM "Amazon Turkey", "Amazon Kindle US", "Amazon Seller Central" kartlarının `new_logicalref` bağı gösterilir.
2. Amazon cari net ciro 2026 ekran = faturalı satır sorgusu (M42 kabul 1) bu carilerle.
3. Konsinye kalan: `SELECT i.CODE, SUM(l.AMOUNT) FROM dbo.LG_411_01_STLINE l JOIN dbo.LG_411_ITEMS i ON i.LOGICALREF = l.STOCKREF WHERE l.TRCODE = 8 AND l.CANCELLED = 0 AND l.LINETYPE = 0 AND l.INVOICEREF = 0 AND l.BILLED = 0 AND l.CLIENTREF IN (<Amazon cari ref>) GROUP BY i.CODE` — ekranla aynı; iade irsaliyeleri ayrıca gösterilir.
4. CRM Amazon Konsinye sipariş sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase WHERE new_siparistipi = 14 AND new_siparistarihi >= @bas`.
5. Yurtdışı satış (yıl × cari) = faturalı satır sorgusu `c.SPECODE2 = 'YURTDIŞI'` (yazım önce `SELECT DISTINCT SPECODE2` ile ölçülür) — ekranla aynı.
6. Döviz: 2026 `TRCURR <> 0` fatura sayısı = katalog notundaki ölçümle aynı yöntemle yeniden sayılır (74 değeri eski ölçüm; aynı kopyada tekrar edilir).

**Bağımlılık**: **M42 önce** (paket, eşleme). M6 hak verisi (var: test sunucusunda). M4 çeviri işine bağ sonraki sürüm. Amazon API
müşteri hesabı gelmeden ilk sürüm tamamen Logo/CRM ile. M40 ile paralel kodlanabilir.

**Tahmini büyüklük**: M (ilk sürüm karne + konsinye + yurtdışı + taslak 2 gün); API istemcisi ikinci sürümde M.
