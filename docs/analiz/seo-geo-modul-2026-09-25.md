# SEO & GEO modülü — hazırlık analizi (2026-09-25)

Timaş'ın arama motoru (SEO) ve yapay zekâ cevap motoru (GEO) görünürlüğünü tek yerden izleyip
yöneten ayrı bir modül. Kod olarak kendi klasöründe durur, menüde mevcut iki girişe bağlanır:
`src/canvas/modules.json` → Pazarlama → **M25 İçerik Pazarlaması ve SEO** ve **M26 Yapay Zekâ
Görünürlüğü — GEO**. Ekranlar önce Stitch'te çizilir (tasarım sistemi «Timaş Portal Kanvas»,
`assets/12401857364778149884`, proje 13426839861607265553), sonra `src/canvas` diline çevrilir.

## Ana akış: ürün denetimi → model önerisi → insan onayı → T-soft

1. **Eşitle:** T-soft'tan tüm ürünler (`product/get`, `FetchDetails`, `FetchImageUrls`,
   sayfa 500), kategoriler, markalar/yazarlar, `link/getLinks` (meta, canonical, index/follow,
   sitemap ayarı) gece okunur, sunucudaki depoya yazılır.
2. **Denetle:** her ürün kurallardan geçer; sonuç ürün başına puan + **neden** listesi.
   Kurallar veriden türetilir ve ekranda yönetilir (eşik, açık/kapalı), koda gömülmez.
   İlk kural adayları: meta açıklama yok/uzun, SEO başlığı uzun/kısa/yinelenen, açıklama kısa,
   yazar/ISBN/yayın yılı eksik, Book/Person yapılandırılmış veri yok, canonical/index yanlış,
   kırık iç bağlantı, Search Console'da gösterim var tıklama yok (TO düşük), AI motorlarında
   hiç anılmayan çok satan kitap.
3. **Öner:** model (LLM kapısı üzerinden, `rt.llm_for`) ürünün kendi verisinden SEO başlığı,
   meta açıklama, SEO link, açıklama + SSS bloğu, arama kelimeleri, JSON-LD önerisi üretir.
   Kaynak: T-soft ürün kaydı + Logo/CRM kitap bilgisi (yazar, konu `new_ozet`, tür).
4. **Onayla:** ekranda mevcut ↔ öneri farkı; kullanıcı onaylar / düzenler / yeniden üretir /
   reddeder. **Onaysız hiçbir şey T-soft'a gitmez.** Her karar `semantic_audit`'e yazılır.
5. **Gönder:** onaylı alanlar `product/updateProducts` (SeoTitle, SeoDescription, Details,
   SearchKeywords), `product/setProductLanguage` (SeoLink), `link/setLinks` (canonical,
   index/follow, sitemap) ile gider; ardından `setting/deleteCache/product`. Gönderim öncesi
   değerler saklanır → geri alma aynı ekrandan.
6. **Ölç:** gönderilen ürünün Search Console gösterim/tıklama/pozisyonu ve AI anılma oranı
   önce/sonra karşılaştırılır.

## Kaynaklar ve bağlantı için gerekenler

| Kaynak | Ne verir | Bağlantı |
|---|---|---|
| T-soft REST1 (`satinal.timas.com.tr/rest1`) | ürün/kategori/marka SEO alanları okuma-yazma, link/canonical/sitemap, 301 | web servis kullanıcısı; kimlik bilgisi Yönetim ekranından girilir (`admin.conf`), repo'ya yazılmaz; sunucu IP'si beyaz listeye |
| Search Console API | sorgu/sayfa/ülke/cihaz performansı (16 ay), URL denetimi (günde 2.000), sitemap | servis hesabı Search Console'a kullanıcı (okuma: Kısıtlı, sitemap: Tam) |
| GA4 Data API | organik oturum, AI asistanı yönlendirmeleri (chatgpt.com, perplexity.ai, gemini, copilot) | servis hesabına Görüntüleyici + mülk kimliği |
| Merchant API (Content API 18.08.2026'da kapandı) | ürün durumu, reddedilen ürün sorunları | servis hesabı kullanıcı + `registerGcp` (kişi e-postası) + hesap kimliği |
| PageSpeed / CrUX | Core Web Vitals | API anahtarı |
| Bing Webmaster + IndexNow | sorgu istatistikleri, URL bildirimi | API anahtarı, IndexNow anahtar dosyası (T-soft kök dizine konabiliyor mu kontrol) |
| Yandex Webmaster v4 | popüler sorgular | OAuth token |
| GEO ölçümü | sabit soru seti → OpenAI (web_search), Perplexity Sonar (citations), Gemini (grounding); anılma, sıra, atıf | ilgili API anahtarları; her soru birkaç kez sorulup oylanır |

Hesap: `zeki@timas.com.tr` (Google, Bing, Yandex web yöneticisi hesabı). Giriş kullanıcıda;
Google tarafında şifre değil servis hesabı kullanılır.

## Bilinen sınırlar (T-soft API)

- Sabit sayfalar (`content`) yalnız okunur.
- Görsel alt metni alanı API'de görünmüyor (doğrulanacak).
- Ürün başına JSON-LD basmak tema işi olabilir (`htmlBlock/set` var, ürüne özel değil).
- Hız sınırı yayımlanmamış; gönderim sıralı ve yavaş başlar, hata oranına göre ayarlanır.

## Ekranlar (Stitch)

1. Genel Bakış — KPI, organik + AI trafik, motor bazında anılma, onay bekleyenler, bağlantı durumu
2. Ürün Denetimi & Onay — kural filtreleri, ürün listesi, neden, mevcut↔öneri farkı, onay çubuğu
3. AI Görünürlük (GEO) — izlenen sorular, motor matrisi, paylaşılan ses, cevap içi atıf
4. Anahtar Kelimeler & Sıralama — pozisyon dağılımı, fırsatlar, kanibalizasyon
5. Bağlantılar — T-soft/Google/Bing/Yandex/AI anahtarları, onay kuralları, denetim kaydı

## BEKLEYEN: CRM'e yazma (müşteriden istenecek — 2026-09-25 kullanıcı kararı)

Akış: T-soft taranır → eksikler bulunur → onaylanan düzeltme **CRM'deki kitap kaydına** yazılır → CRM kendi aktarımıyla
T-soft'a gönderir → sonraki taramada T-soft'ta göründüğü doğrulanır. Şimdilik bekliyor; müşteriden istenecekler:

1. Dynamics CRM Web API adresi (on-prem, `.28` CRMDATBASE'in önündeki uygulama sunucusu) ve **kitap kaydına yazma
   yetkili servis hesabı**. SQL'e doğrudan yazılmaz (CRM eklentilerini ve kayıt geçmişini atlar).
2. SEO başlığı / meta açıklama için karar: CRM `new_kitap`'a iki yeni alan + CRM→T-soft aktarımına eklenmesi (öneri),
   ya da bu ikisinin T-soft'a doğrudan yazılması.
3. CRM→T-soft aktarımını kim yönetiyor, hangi sıklıkla çalışıyor.

Veriyle doğrulanan eşleme (ISBN ile 5.466/5.656 aktif ürün): T-soft `Details` = CRM `new_kitapBase.new_ozet`
(5.139/5.214 metin %90+ aynı), `SearchKeywords` = `new_AnahtarKelimeler` (2.351/2.353 aynı). SEO başlığı/meta CRM'de
yok; T-soft şablonundan (ad + kategori + yayınevi + yazar), ikisi birebir aynı. Yazar T-soft'ta `Model` alanında.
Bu karar gelene kadar gönderim T-soft'a doğrudan yapılır ve `Details`/`SearchKeywords` için CRM aktarımıyla ezilme riski vardır.

## T-soft API: yalnız okuyarak neler alınıyor (canlı sınama, 2026-09-25)

Bütün çağrılar yazma kilitli istemciyle (`READ_ONLY`); T-soft'a hiçbir şey gönderilmedi.

| Kaynak | Yöntem | Ne var |
|---|---|---|
| Ürün (6.781) | `product/get` | 135 alan: SeoLink/SeoTitle/SeoDescription, Details, ShortDescription (yalnız 28 dolu), SearchKeywords (2.686), Barcode=ISBN, Brand=yayınevi, **Model=yazar**, Additional6=künye (6.556), CommentCount/CommentRate, CountTotalSales (5.683 ürün, toplam 430.644), StatViews, RelatedProductsIds, GoogleCategoryId (0 dolu); `FetchFilters` Yaş/Sınıf/Eser Dili, `FetchCatalogData` yazar kimliği |
| Kategori (138) | `category/getCategories` | SeoTitle/SeoDescription 136 dolu, 42'sinde başlık = kategori adı; ShortDescription 2 |
| Marka/yayınevi (35) | `brand/getBrands` | SEO alanları 7'sinde boş |
| Yazar (1.773) | `model/getModels` | kayıtta SEO alanı yok; başlık/açıklama getLinks'te (64 boş); biyografi yok |
| Etiket (6.346) | `product/getTags` | 249'unda SEO başlığı |
| Sayfa ayarları (27.825) | `link/getLinks` | tür başına Title/Description, PageIndex/Follow/Canonical (hemen hepsi "atanmamış"), sitemap önceliği; Keywords okuma cevabında yok |
| 301 (12.464) | `link/getReferralLinks` | **717 yönlendirme anasayfaya** (yumuşak 404) |
| Yorum (86) | `product/getComments` | 67 ürün, 80×5 yıldız; hiçbiri cevaplanmamış |
| SEO şablonu | `setting/getSettingByCategory/6` | otomatik şablon Title = `%UrunAd% %KatAd% %Marka% %Model%`; **UrunDetaySchemaOrg, LocalBusinessSchemaOrg boş**; PasifUrunYonlendirme kapalı |
| İçerik | `content/getContent` (14), `news/getNews` (1 test) | blog gövdesi için okuma yöntemi yok (20 yazı yalnız getLinks'te) |
| Sipariş (62.903) | `order/get` | **kişisel veri** içerir; SEO için yalnız UTM kaynağı ve tarih — kişisel alanları atan toplama katmanı olmadan kullanılmaz |

Lisans dışı: video (PRE041), çok dil (PRE031). robots.txt / llms.txt / sitemap için API yöntemi yok.
