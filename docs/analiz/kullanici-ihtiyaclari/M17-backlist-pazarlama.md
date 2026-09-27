# M17 — Backlist Kitaplar için Pazarlama Planları: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M17.txt`, `specs/M11.txt` («Donuk stok kampanya modülüne gider → M17»), `specs/M46.txt`, `ZEKİ_Veri_Haritasi2.html` (M46 Bütçe & Satış Hedefleri, Backlist Veri Girdileri, Rekabet Girdileri), `configs/semantic/knowledge/crm/table_descriptions.json` (döküm 2026-09-09), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`, `docs/analiz/kitap-yazar-web-taramasi-2026-09-24.md`, `docs/analiz/pbit-yeni-baski-oneri/README.md`, `docs/analiz/timesfm-baski-oneri/`, `docs/GELISTIRME-GUNLUGU.md` (M46 girişi), `backend/semantic_bridge/budget.py`, `budget_sources.py` (`read_forecast`), `management/`, `seo_geo/seasons.py`, `web_watch.py`, `docs/analiz/kullanici-ihtiyaclari/M15-yeni-kitap-pazarlama.md` (ortak çekirdek), kullanıcı belleği (timesfm3-baski-oneri-backtest, baski-oneri-pbi-birebir, logo-155-frozen-copy, logo-sales-view-plan-traps, crm-digital-rights-fields, sales-are-invoiced-lines, no-silent-limits-rule, web-watch-open-sources, customer-vm-web-watch-off, tsoft-no-write, no-tech-names-on-screens).

> Kural: sunucuya bağlanılmadı. CRM satır sayıları tablo sözlüğünün 2026-09-09 dökümündendir (canlıda **ölçülecek**). Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım**.

## 1. Modül ne işe yarar

Yayımlanmasının üzerinden 12 aydan fazla geçmiş kitapları (backlist) tarar, satışı düşen ama potansiyeli olan kitapları **açıklanabilir bir «uyku endeksi»** ile sıralar, gündem ve mevsimle (özel gün, yazarın yeni kitabı, arama artışı) eşleştirir ve her fırsat için aktivasyon planı önerir: yeniden lansman, set/paket, sosyal medyada «yeniden keşfet» içeriği, kütüphane/okul toplu alım teklifi, fiyat/promosyon, dijital format (iş tanımı: K3 fırsat taraması, K2 aktivasyon kampanyası). Önceliği M46'nın backlist hedef sapması belirler.

TİMAŞ'ın bugünkü sorunu: katalog çok büyük (M46 2026 planında 11.276 kitap hedefi; ilk kabulde 7.720'si eşik altında) ve backlist cironun büyük kısmını taşıyor olsa da (oran **ölçülecek**) hangi kitabın «uyuyan» olduğu, hangisinin gerçekten tükendiği, hangisine kampanya yapılınca geri döndüğü sistematik izlenmiyor. Baskı Öneri raporu (M11) stok/satış hızını gösteriyor ama pazarlama eylemine bağlanmıyor; M46 sapma uyarısı var ama «ne yapalım» sorusunun ekranı yok.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Backlist / katalog pazarlama sorumlusu | Pazarlama (varsayım: ayrı bir unvan olup olmadığı bilinmiyor; ekip «Pazarlama» 35 kişi) | Haftalık tarama, aylık kampanya | Masaüstü |
| Pazarlama müdürü | Pazarlama | Aylık öncelik kararı (K3) | Masaüstü |
| Satış müdürü | Satış (ekip 49 kişi) | Aylık; kanal kampanyası (B2B, bayi) | Masaüstü |
| Kurumsal / kütüphane-okul satış | Satış (varsayım; M31/M33) | Dönemsel (okul açılışı, kütüphane alım dönemi) | Masaüstü |
| E-ticaret / kampanya sorumlusu | Varsayım (M35) | Kampanya başına | Masaüstü |
| Yayın yönetmeni (kitaplık sahibi) | Editörya | Aylık; yeniden baskı/yeni kapak kararı | Masaüstü |
| Genel müdür | Yönetim | Çeyrekte bir | Telefon (özet) |

## 3. Bugün bu iş nasıl yapılıyor

- **Pazarlama/satış** (varsayım): backlist kampanyaları özel günlere (öğretmenler günü, okul açılışı, yılbaşı) ve fuarlara göre seçiliyor; seçim deneyimle, Excel'deki satış dökümüyle. CRM'de B2B/CRM kampanyaları kayıtlı (`new_kampanyaBase` 308 kampanya: ek/net iskonto, minimum alışveriş, planlanan ve gerçekleşen ciro; kampanya ↔ ürün bağı 24.479, kampanya ↔ firma 318.631). Kampanyanın kitap satışına etkisi ölçülmüyor.
- **Stok tarafı**: Power BI «Yeni Baskı Öneri» raporu portalda birebir yeniden kuruldu (Baskı Tekrar 5.053 kitap; satış hızı, tükenme süresi, öneri Acil/Risk/Yeterli Stok). Fazla stoklu ve yavaşlayan kitap listesi buradan çıkarılabiliyor ama pazarlamaya bir iş olarak gitmiyor. Rapordaki «Set Kitaplar» sayfası kırık (kaynak tablo modelde yok).
- **Özel günler**: CRM `new_ozelgunlerBase` (93 gün, ISO hafta) ve kitap bağı (~820); SEO modülünün «Sezon takvimi» bunları geçen yılın arama artışıyla birleştiriyor (test sunucusunda).
- **Tıkanma**: (1) 11 bin kitabın içinde hangisinin «uyuyan fırsat» olduğunu gösteren bir sıralama yok, (2) M46 sapma uyarısı var ama eyleme bağlanmıyor, (3) geçmiş kampanyanın işe yarayıp yaramadığı ölçülmüyor, (4) içerik (sosyal gönderi, e-bülten, toplu alım mektubu) her seferinde sıfırdan yazılıyor.

## 4. İhtiyaçlar ve acı noktaları

**Backlist pazarlama sorumlusu**
1. Bütün backlist'in açıklanabilir sıralaması: satış eğilimi, stok, marj, tahmin, hedef sapması ayrı ayrı görünen, sıralaması değiştirilebilen liste (tavan yok).
2. Gündem eşleşmesi: önümüzdeki 8 haftanın özel günlerine bağlı kitaplar, yazarı yeni kitap çıkaran backlist kitaplar, arama ilgisi artan konular.
3. Seçilen kitaplar için tek tuşla aktivasyon planı (kanal, bütçe, takvim, içerik taslakları).
4. Geçmiş kampanya etkisi: «bu kitaba geçen yıl kampanya yaptık, satış ne oldu?»

**Pazarlama müdürü**
1. Aylık «hangi 30–50 backlist kitaba odaklanıyoruz» kararını hedef sapmasıyla gerekçelendirmek (K3).
2. Backlist bütçesinin yeni kitap bütçesine oranı (M18 ile).

**Satış / kurumsal satış**
1. Kütüphane ve okul toplu alımına uygun kitap listesi (hedef kitle, yaş, sınıf, stok var) ve teklif mektubu taslağı.
2. B2B kampanyasına girecek kitapların stok yeterliliği.

**Yayın yönetmeni**
1. «Kapak yenilensin mi, yeni baskı mı, dijitale mi» kararı için kanıt (satış eğilimi, stok, dijital hak).

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Backlist sorumlusu olarak **bütün backlist kitaplarını uyku endeksine göre ve bileşenleri görünür** şekilde sıralamak istiyorum, çünkü tek bir kara kutu puanına güvenmem.
- Backlist sorumlusu olarak **önümüzdeki özel günlere bağlı ve stoku olan kitapları** görmek istiyorum, çünkü kampanya takvimi özel günlere göre kuruluyor.
- Backlist sorumlusu olarak **yazarı yeni kitap çıkaran eski kitapları** görmek istiyorum, çünkü yeni kitap lansmanı eskisini de satar.
- Backlist sorumlusu olarak **seçtiğim kitaplar için aktivasyon planı taslağını** (kanal, bütçe, takvim, «neden şimdi oku» gönderisi) almak istiyorum.
- Pazarlama müdürü olarak **M46'da sapma uyarısı olan A sınıfı backlist kitapların** fırsat listesinin başına gelmesini istiyorum, çünkü hedefi onlar kurtarır.
- Kurumsal satış olarak **okul/kütüphane için uygun kitap listesi ve teklif mektubu taslağı** istiyorum.
- Yayın yönetmeni olarak **e-kitap hakkı olan ama e-kitabı çıkmamış** backlist kitapları görmek istiyorum.

### Ana ekranlar ve akış
- **İlk açılış (`/pazarlama/backlist`)**: üstte dört sekme — **Fırsatlar** (uyku endeksi listesi), **Gündem** (önümüzdeki 8 hafta özel gün ve yazar yeni kitap eşleşmeleri), **Aktivasyonlar** (açılmış backlist planları ve durumları), **Etki** (geçmiş kampanya öncesi/sonrası). Fırsatlar listesinde her satır: kapak, ad, yazar, kitaplık, ilk yayın yılı, son 12 ay / önceki 12 ay net adet ve değişim, stok ve tükenme süresi, marj, 12 aylık tahmin, M46 durumu (iyi/izle/sapma), özel gün etiketi, dijital format durumu; endeks ve bileşen çubukları. Süzgeçler: yayınevi, kitaplık, hedef kitle, M46 durumu, stok var, özel gün.
- **Kitap fırsat kartı** (yan panel): 36 aylık satış çizgisi, geçmiş kampanyalar, emsal/ilgili kitaplar, önerilen eylemler ve gerekçesi.
- En sık üç işlem: (1) listeyi süzüp sırala — 1–2 tık; (2) kitapları seçip «Aktivasyon planı oluştur» — 2 tık (tek plan birden çok kitap taşıyabilir: set/tema kampanyası); (3) içerik taslağı iste — 1 tık.

### Zeki AI'ya soracakları
1. «Son 12 ayda satışı en çok düşen ama stoku 6 aydan fazla yeten çocuk kitapları hangileri?»
2. «Öğretmenler gününe bağlı kitaplardan stokta olanlar hangileri, geçen yıl kasımda ne sattılar?»
3. «Yazarı bu ay yeni kitap çıkaran backlist kitaplar hangileri?»
4. «Geçen yılki okul kampanyasına giren kitaplar kampanya ayında önceki aya göre ne kadar arttı?»
5. «E-kitap hakkı olup e-kitabı olmayan romanlar hangileri?»
6. «M46'da sapmada olan A sınıfı backlist kitapların toplam hedef açığı ne?»
7. «Bu beş kitap için 'neden şimdi okumalı' temalı üç gönderi yaz.»
8. «Kütüphanelere gönderilecek bir teklif mektubu hazırla: 7–10 yaş, stokta olan, tarih konulu kitaplar.»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| Backlist kümesinin çıkarılması, bileşenlerin hesaplanması | K1 | Gece; SQL |
| Uyku endeksi sıralaması | K1 hesap, **K3 karar** | Sıralamayı kullanıcı ağırlıklarla değiştirebilir; öncelik kararı insanda |
| Gündem eşleşmesi (özel gün, yazar yeni kitap) | K1 | CRM bağları ve M15 planları |
| Konu–gündem eşleşmesi (arama artışı, haber) | K2 | Zeki AI eşleştirir, kullanıcı onaylar; kaynaklar test sunucusunda |
| Aktivasyon planı (kanal, bütçe, takvim) | K2 | Öneri + onay (M15 onay akışı) |
| Set/paket önerisi | K2 | M53'e aday olarak gider |
| İçerik taslakları | K2 | Zeki AI taslak, onay |
| Fiyat/promosyon kararı | K3 | M9/M35 ile; bu modül yalnız aday gösterir |
| Kampanya etkisi ölçümü | K1 | Öncesi/sonrası SQL; nedensellik iddiası yok |

### Bildirim / uyarı
- Aylık (ayın ilk iş günü): «Bu ayın fırsatları» özeti pazarlama müdürüne ve backlist sorumlusuna (ilk 30 değil, eşik üstü tamamı; e-postada sayı + ekrana bağlantı).
- Özel güne 6 hafta kala: bağlı, stoklu, aktivasyonu olmayan kitaplar → backlist sorumlusuna.
- Yazarın yeni kitabının M15 planı onaylanınca: yazarın backlist kitapları → plan sahibine «çapraz satış adayı».
- M46'da backlist kitap için yeni sapma uyarısı (`deviations?status=acik&scope=kitap`) → haftalık özet.
- Kanal: e-posta (köprü SMTP) + Uyarılar rozeti.

### Onay ve yetki
- Görür: `sayfa:pazarlama-backlist`.
- Aktivasyon planı yazma: `ozellik:pazarlama.plan-yaz`; onay `ozellik:pazarlama.plan-onay` (explicit) — M15 ile aynı anahtarlar.
- Endeks ağırlıklarını ekip varsayılanı olarak kaydetmek: `ozellik:pazarlama.backlist-ayar` (kişisel ağırlık herkese açık, kişi tercihine yazılır).
- Ciro/marj görmek: `ozellik:pazarlama.butce-gor`.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Backlist tanımı | CRM `new_kitapBase.new_ilkyayintarihi` ≤ bugün − 12 ay; M46 `segment=backlist` | M46 segmenti var | İki tanımın farkı **ölçülecek**; M46'nınki esas alınır (tek tanım) |
| Tüm zamanlar satış | Logo `LG_{firma}_01_STLINE` her yıl firması (211 = 2021–2025, 411 = 2026; 2015–2020 kapsam dışı — bellek «Logo prefixes are years») | `budget_sources.sales_sql` | 2020 öncesi yok; «tüm zamanlar» = 2021+ olarak yazılır |
| Stok | Logo görünümü `EOS_DEPO_STOK_KONTROL_211` (Baskı Öneri `logo_depo_stok.sql`, 157 hariç); geçmiş ay stoku `LV_{firma}_01_STINVTOT` `SUM(ONHAND)` | Baskı Öneri kullanıyor | .155 kopyası donmuş (son fatura 2026-08-17); stok o kopyanın |
| Satış hızı, tükenme süresi, öneri | Baskı Öneri (yönetim raporu önbelleği `var/management-reports/`) | Canlı raporda | Sözleşme ucu yok; önbellek dosyası okunur ya da `/api/v1/management/*` |
| 12 aylık tahmin | `budget_sources.read_forecast()` → `baski-oneri-tahmin.json` p50 | M46 bunu kullanıyor (≈5.200 kitap) | Tahminin okul zirvesini eksik verdiği ölçüldü (−%27…−%33) — ekranda «tahmin» etiketi |
| Baskı maliyeti / marj | Logo `STLINE.OUTCOST` (maliyetli satırlar; 2026'da satırların ~%20'sinde maliyet yok), CRM üretim `new_kesinlesenbaskifiyati` | M46 marj tanımı | Maliyetsiz kitapta marj «yok» yazılır |
| Hedef ve sapma | M46 `targets?segment=backlist`, `deviations?status=acik&scope=kitap` | Main'de | Uyarı yalnız A sınıfı (hedef cironun %80'i) kitaplarda açılır; diğerlerinin durumu `targets.gerceklesme.durum`'da |
| Özel gün | CRM `new_ozelgunlerBase` + `new_new_kitap_new_ozelgunlerBase`; SEO `semantic_seo_seasons_*` | Test sunucusunda (SEO modülü) | VM'de SEO modülü yok → CRM'den doğrudan |
| Anahtar kelime / konu | CRM `new_new_anahtarkelime_new_kitapBase` (52.135 bağ), `new_AnahtarKelimeler`, `new_turlertext`, `new_new_kitap_new_temaBase` (1.143) | Tablo sözlüğünde | — |
| Arama ilgisi | Search Console (SEO modülü; `zeki@` sahip değil, servis hesabı yetkisi eksik) | Kısmi | Google Trends resmi API'si **yok**; kazıma yapılmaz |
| Haber/gündem | «Basın ve web» (test sunucusu) | VM'de kapalı | VM'de gündem eşleşmesi yalnız özel gün + yazar yeni kitap |
| Yazar yeni kitabı | M15 planları; CRM `new_eserkatilimBase` + yayın tarihi | M15 henüz yok | CRM'den doğrudan hesaplanabilir |
| Geçmiş kampanyalar | CRM `new_kampanyaBase` (tarih, iskonto, planlanan/gerçekleşen ciro), `new_new_kampanya_productBase`, sipariş `new_kampanyaid`, satır `new_kampanyakodu`, `new_kampanyaindirimtutari`; CRM pazarlama bütçe modülü + kitap bağı | Tablo sözlüğünde | Ürün ↔ stok kodu eşlemesi `Product.ProductNumber` (Baskı Öneri `crm_bekleyen_siparis.sql`'de kullanılıyor); B2C/pazar yeri kampanyaları CRM'de yok |
| Dijital format | CRM `new_Tip` (8 Ekitap, 9 SesliKitap), `new_new_kitap_new_kitap_ekitap_seslikitapBase`; sözleşme dijital hak alanları `new_iletimhakki`, `new_EKitap` (yalnız Telif Alış) | Bellek «CRM dijital hak alanları» | Doluluk **ölçülecek** |
| Okul/kütüphane uygunluğu | CRM hedef kitle, yaş, sınıf (`new_hedefkitlesinifid`), `new_new_kitap_new_dersBase`, `new_new_kitap_new_sinifkategorisiBase`; MEB uygunluk ölçütleri belgesi | Alanlar var | MEB listesi eşleşmesi M31/M33'te |
| Rakip backlist promosyonları, fiyat kıyası | CRM `new_rakipkitapBase` (liste fiyatı) | Güncelliği **ölçülecek** | Rakip promosyon verisi **yok** (kazıma yok) |

## 7. Diğer modüllerle bağ

- **Girdi**: M46 (backlist hedefleri, sapma uyarısı) · M11 Baskı Öneri (stok, satış hızı, tahmin, «donuk stok») · M15 (yazarın yeni kitap planı → çapraz satış) · SEO sezon takvimi · M7 (yazar ilişkisi) · M9 (fiyat).
- **Çıktı**: M18 (aylık plana backlist aktivasyonları, bütçe payı) · M53 (set/paket adayları) · M35 (e-ticaret kampanya adayları) · M33/M31 (kütüphane/okul teklif listesi) · M36 (dijital format adayları) · M19 (içerik brief'i) · M22 (yeniden keşfet içerikleri) · M11 (kampanya planlanan kitapta baskı önerisine not).

## 8. Kısıtlar

- **CRM'e ve Logo'ya yazma yok**: iş tanımındaki «Onaylanan kampanya → Dynamics CRM kayıt» yapılmaz; «CRM'e işlenecek» listesi (kampanya adı, tarih, ürünler, iskonto) verilir.
- **T-soft'a yazma yasak**: e-ticaret kampanyası önerisi yalnız liste/öneri.
- **Kazıma yok**: Google Trends, rakip siteleri, pazar yerleri taranmaz. Müşteri VM'inde basın/web taraması kapalı.
- **Sayı tavanı yok**: iş tanımındaki «top 20 fırsat» bir görünüm süzgeci olabilir, veri kesilmez; liste tamdır ve toplam sayı yazar.
- **Nedensellik iddiası yok**: kampanya etkisi «öncesi/sonrası» olarak gösterilir, «kampanya şu kadar artırdı» denmez.
- **Veri sonu**: Logo 17.08.2026; her rakamın yanında.
- **Ekranda teknoloji adı yok** («Zeki AI tahmini»).
- **Hukuki**: fiyat indirimi kampanyalarında kitap fiyatına dair yasal düzenleme olup olmadığı hukuk birimine sorulmalı (**varsayım**; Türkiye'de sabit kitap fiyatı kuralı yürürlükte değil diye bilinir, doğrulanmadı). Toplu alım tekliflerinde kamu ihale kuralları M33'te.

## 9. Kapsam önerisi

**İlk sürüm**
- Backlist listesi (M46 tanımı) + bileşenler: son 12 / önceki 12 ay net adet ve değişim, 36 ay aylık seri, stok ve tükenme süresi (Baskı Öneri), marj, 12 aylık tahmin, M46 durumu ve sapma.
- Uyku endeksi: bileşenlerin sıra yüzdelikleri × kullanıcı ağırlıkları (varsayılan eşit); formül ekranda yazılı.
- Gündem sekmesi: özel gün (CRM bağı) + yazar yeni kitap (CRM).
- Aktivasyon planı: çekirdeğin `kind='backlist'` planı (çok kitaplı), M15 onay akışı.
- İçerik taslakları (K2): «neden şimdi oku» gönderileri, e-bülten bölümü, toplu alım mektubu.
- Etki sekmesi: CRM kampanyası olan kitaplarda kampanya ayı ve önceki 3 ay Logo net adet.

**Sonraki sürüm**
- Arama ilgisi (Search Console) ve haber eşleşmesi (test sunucusunda açık kaynaklarla).
- Dijital format adayları (hak alanları ölçüldükten sonra).
- M53'e set önerisi aktarımı, M33'e okul/kütüphane listesi aktarımı.
- Kapak yenileme önerisi (stüdyo kapak üretimiyle).

**Mevcut kodda yeniden kullanılacaklar**
- `budget_sources.py`: `sales_sql`, `firms_by_year`, `data_end_sql`, `read_forecast`.
- `budget.py`: `approved_targets(..., segment='backlist')`, sapma kayıtları (`deviations`).
- `backend/semantic_bridge/management/` Baskı Öneri önbelleği (stok, satış hızı, tükenme, öneri) ve `sql/baski_oneri/logo_depo_stok.sql`.
- `seo_geo/seasons.py` (özel gün ↔ kitap SQL'i `_days_sql`/`_books_sql` kalıbı).
- Pazarlama çekirdeği (M15 belgesi §14): plan, satır, takvim, materyal, onay.
- `src/canvas/management/` tablo bileşenleri (react-virtuoso sanal tablo, kolon ⓘ → SQL paneli), `SearchSelect`.

## 10. Uzmanlara sorulacak sorular

1. TİMAŞ'ta «backlist» neye denir: 12 ay mı, 18 ay mı, ikinci baskı mı? M46'nın segment tanımı kabul mü?
2. Backlist kampanyalarının bütçesi yeni kitaptan ayrı mı; yıllık backlist pazarlama bütçesi var mı?
3. Bugün backlist'e yapılan en etkili eylem ne (B2B iskonto kampanyası, set, okul listesi, sosyal medya)? Geçmişte işe yarayan bir örnek?
4. Kütüphane ve okul toplu alımları hangi dönemlerde ve hangi kanalla (ihale, doğrudan, bayi) oluyor?
5. Dijital hak (e-kitap/sesli kitap) kararını kim veriyor; hangi kitaplar için hak alınmış olduğu CRM'de güvenilir mi?

## 11. Başarı ölçütü

- Aktivasyona alınan backlist kitapların aktivasyon ayı ve sonraki 2 ay net adetinin önceki 3 aya göre değişimi (öncesi/sonrası; kontrol grubu olarak aynı kitaplıkta aktivasyonsuz kitaplar).
- M46'da sapmada olan A sınıfı backlist kitaplardan aktivasyon planı açılanların oranı ve sonraki çeyrekte «izle/iyi»ye dönenler.
- Aylık fırsat listesinden karar kaydına geçen süre.
- İçerik taslaklarının düzeltmesiz onay oranı.

## 12. Uzman gözüyle en iyi sistem

**Kim konuşuyor:** 15 yıllık pazarlama müdürü; backlist'in cironun bel kemiği olduğunu bilen.

**Sektörde iyi örnekler** (genel sektör uygulaması; TİMAŞ'ta doğrulanmadı): güçlü yayınevleri backlist'i «ürün yönetimi» gibi yönetir: her kitabın yaşam eğrisi, mevsimselliği ve stok gün sayısı izlenir; kampanyalar takvim ve gündem kancalarına (yıldönümü, film/dizi uyarlaması, yazar ödülü, okul müfredatı) bağlanır; kapak yenileme ve yeni baskı «yeniden lansman» olarak planlanır; her kampanyanın öncesi/sonrası satış karşılaştırması bir sonraki kararı besler. Yazarın yeni kitabı çıkarken eski kitapları «aynı yazardan» kampanyasıyla birlikte öne çıkarılır.

**TİMAŞ için mükemmel sistem:** her pazartesi hazır bir fırsat listesi — neden fırsat olduğu bileşenleriyle yazılı; gelecek iki ayın özel günleri ve yazar lansmanları kitaplarla eşlenmiş; seçtiğim kitaplar için plan ve içerik taslağı iki tıkta; üç ay sonra «işe yaradı mı» cevabı ekranda.

**Bir iş günü:**
- 09:00 — Fırsatlar sekmesi: M46 sapmasında olan 40 A sınıfı backlist kitap üstte; her birinde düşüş %, stok gün sayısı, tahmin.
- 09:30 — Gündem: 6 hafta sonra Öğretmenler Günü; bağlı 35 kitaptan 22'si stokta, 9'unun geçen kasım satışı güçlü. 12'sini seçer.
- 10:00 — «Aktivasyon planı oluştur»: Zeki AI kanal önerisi (B2B kampanyası + okul listesi + sosyal medya), bütçe taslağı, üç «neden şimdi» gönderisi ve öğretmenlere mektup taslağı. Mektubu düzeltir.
- 11:30 — Yayın yönetmeniyle: satışı 3 yıldır düşen ama stoku 2 yıl yeten klasik için «kapak yenileme + set» kararı; set adayı M53'e gönderilir.
- 14:00 — Etki sekmesi: geçen yılın okul kampanyasındaki 20 kitabın kampanya ayı satışı önceki 3 aya göre; «işe yarayanlar» etiketlenir.
- 16:00 — Zeki AI'a: «Yazarı bu ay yeni kitap çıkaran backlist kitaplar?» → 7 kitap, M15 plan sahiplerine çapraz satış notu.
- 17:00 — Plan müdür onayına gider.

**«Bunu görürsem hemen kullanırım» (3):**
1. Bileşenleri görünen, ağırlığını değiştirebildiğim fırsat sıralaması (kara kutu puan değil).
2. Özel gün × stok × geçen yılın aynı dönemi satışı tek tabloda.
3. Kampanya öncesi/sonrası satış karşılaştırması (hangi eylem işe yarıyor).

**«Bunu yaparsanız kullanmam» (3):**
1. «Top 20» deyip geri kalan binlerce kitabı saklamak.
2. Stokta olmayan ya da hakkı bitmiş kitabı fırsat diye önermek.
3. Donmuş stok/satış verisini tarih yazmadan göstermek; «kampanya %X artırdı» gibi kanıtsız nedensellik.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Backlist kümesi | `LG_{firma}_ITEMS` (157 ile başlayan ticari ürün hariç) | `new_kitapBase` (`new_ilkyayintarihi`, `new_Tip = 1`, `new_satisdurumu`, yayıncılık statüsü) | — | Tanım kuralı |
| Satış eğilimi (12/12 ay, 36 ay seri) | `LG_{firma}_01_STLINE` faturalı satır, iade eksi, net adet/ciro; iki firma birleşir | — | — | SQL |
| Stok, tükenme süresi | `EOS_DEPO_STOK_KONTROL_211` (güncel), `LV_{firma}_01_STINVTOT` (geçmiş ay); Baskı Öneri satış hızı (`logo_satis_hizi.sql`) | CRM açık sipariş (`crm_bekleyen_siparis.sql`) | — | SQL / mevcut rapor |
| Marj | STLINE `AMOUNT × OUTCOST` (maliyetli satırlar) | Üretim `new_kesinlesenbaskifiyati` (yedek) | — | SQL |
| Tahmin | — (Baskı Öneri tahmin önbelleği) | — | — (tahmin ayrı servisten gelir, model metni değil) | Mevcut |
| Hedef ve sapma | — (M46) | — | — | M46 uçları |
| Uyku endeksi | Yukarıdaki bileşenler | — | — | Formül kodda, açıklanabilir |
| Özel gün / yazar yeni kitap eşleşmesi | — | `new_ozelgunlerBase` + bağ; `new_eserkatilimBase` + `new_katilimcitipiBase` (Yazar) + yeni kitabın yayın tarihi | — | CRM bağları |
| Konu–gündem eşleşmesi | — | Anahtar kelime N:N, tema, tür | Özel gün/arama sorgusu ↔ kitap konusu eşleşmesi: aday çiftlerde «ilgili mi?» evet/hayır (tek token + olasılık, düşük marj belirsiz) | Eşleştirme yargısı |
| Aktivasyon planı önerisi | Geçmiş kampanya öncesi/sonrası satış | `new_kampanyaBase`, kampanya ↔ ürün, sipariş kampanya kodu | Kanal önerisinin gerekçe cümlesi; bütçe kural + geçmişten (kod) | Rakamı model üretmez |
| İçerik taslakları | — | `new_ozet`, `new_kitapspotu`, `new_kitabinenonemlicumlesi`, `new_alintlar`, `new_hastag` | «Neden şimdi oku» gönderileri, e-bülten bölümü, toplu alım mektubu; alıntı CRM metninde birebir aranır | Metin üretimi |
| Doğal dil soru | Katalog ölçüleri | Katalog CRM varlıkları | Mevcut sohbet hattı | — |

Model çağrıları LLM kapısından: eşleştirme ve içerik gece toplu `rt.llm_for("marketing", BATCH)`, ekrandaki «taslak iste» `NORMAL`. `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Ön koşul — pazarlama çekirdeği**: `backend/semantic_bridge/marketing/` ve `semantic_mkt_plans|plan_lines|tasks|materials|events` (şema M15 belgesi §14). Çekirdek şeması main'deyse M17 M15 ekranlarını beklemeden paralel kodlanabilir. Çok kitaplı plan için çekirdeğe `semantic_mkt_plan_books` (`plan_id`, `stok_kodu`, `rol` `ana|set|capraz`) eklenir (M18 ve M53 de kullanır).

**Yeni dosya**: `marketing/backlist.py` (hesap), `marketing/backlist_sql.py` (Logo/CRM SQL'leri).

**Yeni tablolar**
- `semantic_mkt_backlist`: `tenant_id`, `stok_kodu`, `ad`, `yazar`, `yayinevi`, `kitaplik`, `hedef_kitle`, `ilk_yayin`, `adet_son12`, `adet_onceki12`, `degisim`, `ciro_son12`, `marj`, `stok`, `tukenme_ay`, `tahmin12_p50`, `m46_durum`, `m46_oran`, `sapma_acik` (bool), `ozel_gunler` (json), `dijital` (json), `bilesen_json` (yüzdelikler), `endeks_varsayilan`, `veri_sonu`, `asof`.
- `semantic_mkt_backlist_series`: `stok_kodu`, `yil_ay`, `net_adet`, `net_ciro` (36 ay).
- `semantic_mkt_campaign_effect`: `kampanya_id` (CRM), `stok_kodu`, `baslangic`, `bitis`, `once3_adet`, `kampanya_adet`, `sonra2_adet`, `asof`.
- `semantic_mkt_matches`: `stok_kodu`, `tur` (`ozel-gun|yazar-yeni|konu`), `anahtar`, `tarih`, `kaynak`, `skor` (model olasılığı, yalnız `konu`), `onay` (`bekliyor|kabul|red`), `onaylayan`.

**Uçlar** (`/api/v1/marketing/backlist…`)
- `GET backlist?sirala=&agirlik=egilim:1,stok:1,marj:1,tahmin:1,sapma:1&yayinevi=&kitaplik=&m46=&stokta=1&ozel_gun=` (tavansız, sayfalı; toplam sayı döner).
- `GET backlist/{stok_kodu}` (fırsat kartı: seri, kampanyalar, eşleşmeler, öneri).
- `GET backlist/agenda?hafta=8` (gündem).
- `GET backlist/effects?yil=` (kampanya etkisi).
- `PUT backlist/weights` (ekip varsayılanı; `backlist-ayar`), kişisel ağırlık `prefs` (`/api/v1/me/prefs/backlist:weights`).
- `POST backlist/matches/{id}/decide`.
- Aktivasyon planı: çekirdeğin `POST /api/v1/marketing/plans` `{kind:'backlist', kitaplar:[…]}`; içerik: `POST plans/{id}/materials` (`tur`: `sosyal|e-bulten-bolum|toplu-alim-mektubu`).
- `POST backlist/run-due` (SYSTEM).

**Ekranlar**: `src/canvas/marketing/backlist/` — `BacklistScreen.tsx` (sekmeler `OpportunitiesTab` — sanal tablo + bileşen çubukları + ağırlık kaydırıcıları; `AgendaTab`; `ActivationsTab`; `EffectsTab`), `OpportunityPanel.tsx` (yan panel; ECharts 36 ay). Rota `/pazarlama/backlist`. Menü: alan `pazarlama`, bölüm «Planlama», `{ id: 'pazarlama-backlist', label: 'Backlist', to: '/pazarlama/backlist', section: 'Planlama', keywords: ['uyuyan', 'eski kitap', 'kampanya', 'özel gün'] }`. Kampüs `LIVE.M17 = '/pazarlama/backlist'`.

**Yetki**: `sayfa:pazarlama-backlist`; `ozellik:pazarlama.backlist-ayar`; plan anahtarları M15'teki (`plan-yaz`, `plan-onay` explicit, `butce-gor`). `access.RULES`: `/api/v1/marketing/backlist/run-due` → SYSTEM; M46 `targets` ve `deviations` satırlarına `page("pazarlama-backlist")`.

**Zamanlayıcı**: `timas-marketing-backlist.timer` — her gece 04:00 (Logo okuması M46'nın saatlik okumasıyla çakışmasın): son yıl satışları + stok + Baskı Öneri önbelleği + tahmin + M46 durumu → `semantic_mkt_backlist`; geçmiş yıllar serisi haftada bir (pazar). Konu eşleşmesi (model) haftada bir, BATCH önceliği. Ayın ilk iş günü 08:00 özet e-postası. İlk kurulumda elle koşturulur; süre ölçülür (M46'da 2025 satış okuması 163 sn).

**Kabul testleri** (test sunucusu, gerçek Logo .155 + CRM .28)
1. **Küme**: `GET /api/v1/budget/targets?year=2026&segment=backlist` madde sayısı = `semantic_mkt_backlist` satır sayısı (157 hariç; fark varsa nedeni listelenir).
2. **Eğilim**: 5 kitap için `SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) FROM dbo.LG_411_01_STLINE S JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = S.STOCKREF WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9) AND I.CODE = '<kod>' AND S.DATE_ >= '<veri sonu − 12 ay>'` + aynı sorgu `LG_211` üzerinde pencerenin 2025 kısmı = `adet_son12`; önceki 12 ay aynı yöntemle = `adet_onceki12`.
3. **Stok**: Baskı Öneri'nin `management/sql/baski_oneri/logo_depo_stok.sql` sorgusu (`SELECT [STOK KODU], SUM([MİKTAR]) FROM dbo.EOS_DEPO_STOK_KONTROL_211 WHERE [STOK KODU] NOT LIKE '157%' GROUP BY [STOK KODU]`) o kod için = `stok` = Baskı Öneri ekranındaki aynı kitabın depo stoku. (Geçmiş ay stoku gerekirse `LV_{firma}_01_STINVTOT` `SUM(ONHAND)` — bellek «TimesFM × Baskı Öneri».)
4. **Tahmin**: `sum(read_forecast()['p50']['<kod>'][:12])` = `tahmin12_p50`.
5. **Sapma**: `GET /api/v1/budget/deviations?year=2026&status=acik&scope=kitap` anahtarları ∩ backlist kodları = `sapma_acik = true` satırları (birebir küme).
6. **Özel gün**: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_new_kitap_new_ozelgunlerBase l JOIN Timas_MSCRM.dbo.new_kitapBase k ON k.new_kitapId = l.new_kitapid WHERE k.new_StokKodu = '<kod>'` = kitabın `ozel_gunler` sayısı.
7. **Endeks açıklanabilirliği**: ağırlıklar değişince sıralama değişir, her satırda bileşenler ve formül metni döner; liste toplam sayısı süzgeçsiz hâlde küme sayısına eşit (tavan yok).
8. **Kampanya etkisi**: bir CRM kampanyası için kampanya ürünlerinin kampanya tarihleri arası Logo net adet = `kampanya_adet` (kampanya ürünü → `ProductBase.ProductNumber` = stok kodu).

**Bağımlılık**: M46 hazır; M11 Baskı Öneri hazır (önbellek). Çekirdek şeması (M15) main'de olmalı; M15 ekranları beklenmez. M53 ve M18 bu modülün çıktısını okur.

**Tahmini büyüklük**: L (endeks + gündem + etki + içerik; çekirdek hazırsa 3 gün).
