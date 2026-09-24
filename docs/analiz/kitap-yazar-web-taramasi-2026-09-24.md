# Kitap ve yazar web taraması — analiz (2026-09-24)

Soru: "Kitaplar ve yazarlar hakkında derinlemesine web taraması nasıl yapabiliriz — duygu analizi vs."

Bu belge yalnız analizdir. Kod, kurulum ve sunucu işi yoktur. Web kaynaklarının durumu 2026-09-24'te kontrol edildi.
Kontrol edilemeyen her şey **doğrulanmadı** diye işaretli. Hukuki notlar hüküm değildir. Her kaynak için
**hukuk görüşü alınmalı**.

## 0. Kısa sonuç

- En temiz yol resmi API, RSS ve açık veridir: Google News RSS, GDELT, YouTube Data API, Wikidata, Open Library,
  Google Books. Bunlarla MVP kurulabilir.
- Türkiye'nin asıl okur sesi 1000Kitap ve e-ticaret yorumlarındadır. Bunların hiçbirinin herkese açık resmi yorum
  API'si bulunamadı. Trendyol, İdefix ve Amazon robots.txt dosyaları yorum yollarını kapatıyor. Goodreads şartları
  kazımayı açıkça yasaklıyor. Bu kaynaklar izin, lisans ya da ücretli sağlayıcı olmadan taranmamalı.
- Duygu analizi Türkçe açık modellerle yerelde yapılabilir. Yön (aspect) çıkarımı ve özet için yerel LLM kapısı
  (`nanobaseAI`) yeterli. Dış bulut LLM'e veri gitmez.
- Kitabı web'de bulup CRM kaydına bağlamanın ana anahtarı ISBN'dir (`new_kitapBase.new_isbn13` / `new_isbn` /
  `new_ekitapisbn`). ISBN yoksa ad + yazar eşleştirmesi ve insan onayı gerekir.
- İlk ölçüm şart: elle etiketlenmiş Türkçe kitap yorumu seti olmadan hiçbir duygu puanı ekrana çıkmamalı.

## 1. Kaynaklar

Sütunlar: ne verir · erişim yolu · hukuki/ToS riski · güvenilirlik. "Risk" teknik bir okumadır, hukuki hüküm değildir.

### 1.1 Okur yorumları

| Kaynak | Ne verir | Erişim yolu | Risk | Güvenilirlik |
|---|---|---|---|---|
| **1000Kitap** | Türkçe okur incelemesi, puan, alıntı, okunma sayısı. Türkiye'de en zengin okur sesi. | Resmi herkese açık API bulunamadı (**doğrulanmadı**). robots.txt kitap/yazar sayfalarını kapatmıyor, 9 site haritası veriyor ([robots.txt](https://1000kitap.com/robots.txt)). | Kullanım şartları sayfası 403 döndü, okunamadı. Arama özetine göre içeriğin yazılı izinsiz ticari kullanımı yasak ([Kullanım Şartları](https://1000kitap.com/hakkinda/kullanim-sartlari)) — metin **doğrulanmadı**. Kullanıcı adları kişisel veri (KVKK). İnceleme metni yazarının eseri olabilir (telif). | Yüksek hacim, gerçek okur. Kampanya/etkileşim kaynaklı eğilim olabilir. |
| **Goodreads** | Uluslararası puan ve yorum. Türkçe yorum azınlıkta. | API 8 Aralık 2020'den beri yeni anahtar vermiyor ([Goodreads yardım](https://help.goodreads.com/s/article/Does-Goodreads-support-the-use-of-APIs)). | Şartlar veri madenciliği, robot ve kitap/yorum toplama işini açıkça yasaklıyor ([Goodreads Terms](https://www.goodreads.com/about/terms)). **Taranmamalı.** | Çeviri eserler ve yabancı yazarlar için anlamlı. |
| **Trendyol** | Ürün yorumu, yıldız, soru-cevap. | Satıcı entegrasyon API'si var ([developers.trendyol.com](https://developers.trendyol.com/)). Soru-cevap yönetimi var; kendi ürünlerimizin yorumlarını okuma ucu olup olmadığı **doğrulanmadı**. | robots.txt `/*-p-*/yorumlar` ve yorum API yollarını kapatıyor ([robots.txt](https://www.trendyol.com/robots.txt)). Kazıma değil, yalnız satıcı API'si düşünülmeli. | Satın alan kişi yorumu. Kargo/paketleme yorumu çok (kitaptan çok hizmet). |
| **Hepsiburada** | Ürün yorumu, yıldız. | Resmi yorum API'si **doğrulanmadı**. robots.txt 403 döndü, okunamadı. | Belirsiz. Satıcı paneli üzerinden okunabiliyorsa o yol. | Trendyol ile benzer. |
| **D&R** | Ürün yorumu, yazar sayfası. | Resmi API bulunamadı. robots.txt yorum faydalılık oylamasını ve aramayı kapatıyor, ürün sayfasını kapatmıyor ([robots.txt](https://www.dr.com.tr/robots.txt)). | Kullanım şartları okunmadı (**doğrulanmadı**). | Orta hacim. |
| **İdefix** | Ürün değerlendirmesi. | Resmi API bulunamadı. robots.txt `*/degerlendirmeler` yollarını kapatıyor ve `ai-train=no` sinyali veriyor ([robots.txt](https://www.idefix.com/robots.txt)). | Değerlendirme sayfaları taranmamalı. | Orta hacim. |
| **Kitapyurdu** | Ürün yorumu, puan. | Resmi API bulunamadı. robots.txt yalnız yönetim/görsel yollarını kapatıyor ([robots.txt](https://www.kitapyurdu.com/robots.txt)). | robots.txt izin vermesi kullanım şartlarının izin verdiği anlamına gelmez. Şartlar okunmadı (**doğrulanmadı**). | Kitapseverlerin yoğun olduğu mağaza. |
| **Amazon.com.tr** | Yorum ve yıldız. | Eski Product Advertising API yorum metni vermiyor; API 2026'da Creators API'ye taşındı ve kimlik için satış şartı var ([PA-API belgesi](https://webservices.amazon.com/paapi5/documentation/), ikincil kaynak: [Vorp Labs](https://vorplabs.com/agent-tools/amazon-shopping-cli)). | robots.txt birçok tarayıcıyı (Scrapy dahil) açıkça engelliyor ([robots.txt](https://www.amazon.com.tr/robots.txt)). **Taranmamalı.** | Türkiye kitap pazarındaki payı ölçülmedi. |

### 1.2 Basın ve haber

| Kaynak | Ne verir | Erişim yolu | Risk | Güvenilirlik |
|---|---|---|---|---|
| **Google News RSS** | Kitap/yazar adıyla geçen haber başlığı, bağlantı, tarih. | `https://news.google.com/rss/search?q=...&hl=tr&gl=TR&ceid=TR:tr`. Resmi belgesi yok; tek çağrı en fazla 100 sonuç veriyor ([NewsCatcher](https://www.newscatcherapi.com/blog-posts/google-news-rss-search-parameters-the-missing-documentaiton), [cloro](https://cloro.dev/blog/google-news-rss/)). | Resmi destekli ürün değil, her an değişebilir. Yalnız başlık + bağlantı saklanmalı, haber metni kopyalanmamalı (telif). | Keşif için iyi, kapsamı bilinmiyor. |
| **GDELT DOC 2.0** | 65 dilde (Türkçe dahil) haber izleme, son 3 ay, sorgu başına en ilgili 75 makale ([GDELT duyurusu](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)). | Ücretsiz açık API. | Düşük. Metin yine yayıncının. | Arama İngilizce makine çevirisi üzerinde; Türkçe özel adlarda kaçak olabilir. |
| **Gazete kitap ekleri** (ör. Cumhuriyet Kitap, K24, Kitap-lık) | Eleştiri, söyleşi, liste. | Çoğunun RSS'i var mı **doğrulanmadı**. Sayfa sayfa bakılmalı. | Tam metin telifli. Yalnız başlık, tarih, bağlantı ve kısa özet saklanmalı. | Eleştirmen sesi; hacim düşük, etkisi yüksek. |
| **Medya takip ajansı** (ör. Ajans Press) | Basılı + TV + web + sosyal medya kupür, rapor. | Ücretli hizmet ([Ajans Press](https://ajanspressteknoloji.com.tr/medya-takibi/)). Veri teslim biçimi (API / dosya) **doğrulanmadı**. | Lisanslı; en az riskli yol. | Basılı basın için tek sağlam yol. |

### 1.3 Sosyal medya

| Kaynak | Ne verir | Erişim yolu | Risk | Güvenilirlik |
|---|---|---|---|---|
| **X** | Anlık konuşma, kampanya etkisi. | Resmi API kullandıkça öde: gönderi okuma kaynak başına 0,005 $, aylık 3 milyon gönderi okuma tavanı ([X fiyat belgesi](https://docs.x.com/x-api/getting-started/pricing)). Son 7 gün araması herkese, tam arşiv kullandıkça öde ve Enterprise müşterisine açık, `lang:` süzgeci var ([X arama](https://docs.x.com/x-api/posts/search/introduction)). | Kullanıcı adı ve içerik kişisel veri. KVKK Kurulu, alenileştirilmiş verinin alenileştirme amacı dışında işlenemeyeceğini söylüyor ([KVKK duyurusu](https://www.kvkk.gov.tr/Icerik/6843/-ALENILESTIRME-HAKKINDA-KAMUOYU-DUYURUSU)). | Bot/kampanya gürültüsü yüksek. |
| **YouTube (BookTube)** | Video başlığı, açıklama, yorum. | Resmi Data API v3. Günlük varsayılan 10.000 birim; `commentThreads.list` 1 birim ([Google belgesi](https://developers.google.com/youtube/v3/docs/commentThreads/list), kota özeti: [Phyllo](https://www.getphyllo.com/post/youtube-api-limits-how-to-calculate-api-usage-cost-and-fix-exceeded-api-quota)). | Şartlar otomatik araçla (scraper) erişimi yasaklıyor; API kullanılmalı ([YouTube Şartları](https://www.youtube.com/static?template=terms)). Yorumcu adı kişisel veri. | Video bulmak için arama çağrısı pahalı (100 birim, ikincil kaynak **doğrulanmadı**). |
| **Instagram (Bookstagram)** | Etiketli gönderi, beğeni. | Graph API hashtag arama: Business/Creator hesabı şart, 7 günde en fazla 30 farklı etiket ([Meta belgesi](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-hashtag-search)). | Yalnız TİMAŞ'ın kendi hesabı ve sınırlı etiket. | Görsel ağırlıklı, metin az. |
| **TikTok (BookTok)** | Kısa video eğilimi. | Research API yalnız ticari olmayan akademik kurumlara açık; ticari kullanıcılar uygun değil ([TikTok Research](https://developers.tiktok.com/products/research-api/), [SSS](https://developers.tiktok.com/docs/en/research-api-faq)). | Resmi yol yok. Ücretli sosyal dinleme sağlayıcısı düşünülebilir (lisans koşulları **doğrulanmadı**). | Genç okur kitlesi için önemli. |
| **Ekşi Sözlük** | Uzun, samimi okur görüşü. | Resmi herkese açık API yok; uygulamanın kullandığı API geliştiricilere açık değil, yalnız resmi olmayan istemciler var ([coluck/eksisozluk-api](https://github.com/coluck/eksisozluk-api)). | Şartlar okunmadı (**doğrulanmadı**). Resmi olmayan istemci kullanılmamalı. | İroni ve alay çok; duygu modeli sık yanılır. |

Ücretli sosyal dinleme sağlayıcıları (Brandwatch, Talkwalker, Meltwater gibi) X, Instagram, TikTok ve forumları lisanslı
toplar. Türkçe kapsamları ve fiyatları bu belgede **doğrulanmadı**. Veri, sağlayıcının bulutundan gelir; bizim
tarafa gelen metin yerel modelde işlenir.

### 1.4 Blog ve podcast

- Blog: çoğu WordPress, çoğunda RSS var. Kaynak listesi elle kurulur (yayınevinin bildiği kitap blogları).
  İçerik telifli: özet + bağlantı saklanır.
- Podcast: RSS akışı açıktır; bölüm başlığı ve açıklaması okunur. Ses çözümleme (konuşmadan metne) ayrı bir iştir,
  MVP dışında.

### 1.5 Açık künye verisi

| Kaynak | Ne verir | Erişim | Not |
|---|---|---|---|
| **Wikidata** | Yazar kimliği (doğum, ödül, diğer adlar), eser, ISBN-13 (P212). CC0 ([Veri erişimi](https://www.wikidata.org/wiki/Wikidata:Data_access/en), [P212](https://www.wikidata.org/wiki/Property_talk:P212)). | SPARQL: `query.wikidata.org` ([WDQS](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service)). | Yazar belirsizliğini çözmede en iyi dış kimlik. |
| **Wikipedia** | Yazar biyografisi, ödüller. | MediaWiki API. | Metin CC BY-SA; kaynak gösterilerek kullanılır. |
| **Open Library** | ISBN → künye, kapak. | Anahtarsız API; kimliksiz 1 istek/sn, User-Agent + e-postayla 3 istek/sn ([Open Library API](https://openlibrary.org/developers/api), [kota tartışması](https://github.com/internetarchive/openlibrary/issues/10585)). | Türkçe kitap kapsamı ölçülmedi. |
| **Google Books API** | ISBN → künye, dil, sayfa. | `isbn:` sorgusu ([Google belgesi](https://developers.google.com/books/docs/v1/using)). Günlük kota için güvenilir resmi sayı bulunamadı (**doğrulanmadı**). | Türkçe kapsamı ölçülmedi. |
| **Ödüller** | Ödül, kısa liste, jüri. | Wikidata "aldığı ödül" özelliği + ödül kurumlarının sayfaları (elle kaynak listesi). | Düşük hacim, yüksek etki. Elle doğrulanır. |

Not: Google Custom Search JSON API yeni müşteriye kapalı ve 1 Ocak 2027'de kapanıyor ([Google belgesi](https://developers.google.com/custom-search/v1/overview),
ikincil özet: [Octoparse](https://www.octoparse.com/blog/google-official-search-api)). Genel web araması için buna dayanılmamalı.

### 1.6 Hukuk notu (hüküm değildir)

- **Kazıma:** robots.txt izin vermesi, sitenin kullanım şartlarının izin verdiği anlamına gelmez. Şartlar ayrı okunmalı.
- **KVKK:** yorum sahibinin adı, profil bağlantısı, fotoğrafı kişisel veridir. Öneri: kişi bilgisi hiç saklanmasın,
  yorumcu yalnız tek yönlü özetle (hash) temsil edilsin. Alenileştirme istisnasının (md. 5/2-d) bu amaca uyup
  uymadığı **hukuk görüşü alınmalı**.
- **Telif:** yorum ve eleştiri metni yazarının eseri olabilir. Tam metni saklamak, göstermek, model eğitmek ayrı
  izinler gerektirebilir. **Hukuk görüşü alınmalı.**
- **Yurt dışına aktarım:** metin yerel GPU'da işlenir, dış bulut LLM'e gitmez. Bu, riski azaltır ama kaldırmaz.

## 2. Eşleştirme: web kaydı → CRM kaydı

CRM'deki kitap `new_kitapBase` (ISBN alanları `new_isbn13`, `new_isbn`, `new_ekitapisbn`; köprüde
`backend/semantic_bridge/editorial.py` bu alanları zaten okuyor). Yazar katkısı `new_eserkatilimBase` →
`new_Katilimsaglayan` → `ContactBase`.

Sıra (her adım bir güven düzeyi yazar):

1. **ISBN tam eşleşme** (ISBN-10 ↔ ISBN-13 dönüştürülerek, tire ve boşluk atılarak). Güven: kesin.
   Mağaza sayfaları çoğu zaman ISBN'i gösterir; Wikidata P212 ile de bağlanır.
2. **Baskı ayrımı:** bir eserin birden çok ISBN'i olabilir (yeni baskı, e-kitap, cep boy). Eşleşme önce "baskı"ya
   (ISBN), sonra "eser"e (aynı `new_kitapBase` grubu) toplanır. Yorumlar eser düzeyinde birleştirilir.
3. **Ad + yazar:** ISBN yoksa. Ad normalleştirilir (küçük harf, Türkçe İ/ı, noktalama, "Roman", "Ciltli" gibi ekler).
   Yazar adı `ContactBase` adıyla karşılaştırılır. Aday eşleşme "olası" düzeyinde kalır.
4. **Yazar adı belirsizliği:** aynı adlı iki yazar, takma ad, çeviri eserde çevirmen adının yazar yerine geçmesi.
   Çözüm: Wikidata kimliği (doğum yılı, diğer adlar), eser listesinin kesişimi, katılım tipi (yazar mı çevirmen mi).
   Makine emin değilse insan onayına düşer. Makine tek ipucuyla (yalnız ad benzerliği) onaylamaz.
5. **Logo satış bağı:** satış Logo'dadır (kayıt sistemi). Kitabın Logo malzeme kartına bağı CRM stok kartı
   üzerinden kurulmalı (`new_stakkarti`). ISBN'in Logo'da barkod olarak tutulup tutulmadığı **ölçülmedi**; önce
   ölçülmeli.

Eşleşme tablosu ayrı tutulur. Yanlış eşleşme geri alınabilir olmalı; yanlış bağlanmış yorum yanlış kitaba puan yazar.

## 3. Analizler

Bütün model işi yerelde. Duygu için küçük Türkçe sınıflandırıcı (hızlı, GPU'da ya da CPU'da), yön çıkarımı ve özet
için LLM kapısı (`nanobaseAI`, `rt.llm_for` / `QueuedLlm`, düşük öncelik `bg:`).

### 3.1 Türkçe duygu analizi

Aday modeller (web'den doğrulandı; hiçbiri kitap yorumunda ölçülmedi):

| Model | Taban | Eğitim verisi | Bildirilen sonuç |
|---|---|---|---|
| [`incidelen/bert-base-turkish-sentiment-analysis-cased`](https://huggingface.co/incidelen/bert-base-turkish-sentiment-analysis-cased) | BERTurk | TRSAv1, 150.000 e-ticaret yorumu, 3 sınıf | Kendi testinde doğruluk %83,69; nötr sınıfta F1 %76,67. Lisans kartta yazmıyor. |
| [`savasy/bert-base-turkish-sentiment-cased`](https://huggingface.co/savasy/bert-base-turkish-sentiment-cased) | BERTurk | Film (Beyazperde) + ürün yorumu (kitap dahil), 2 sınıf | Kitap yorumu eğitimde var, nötr sınıf yok. |
| [`VRLLab/TurkishBERTweet`](https://huggingface.co/VRLLab/TurkishBERTweet) + duygu LoRA | RoBERTa, 894 milyon Türkçe tweet | 42.476 tweet | Test F1 0,692 ([GitHub](https://github.com/virallab/turkishbertweet)). X/Ekşi dili için. |
| Taban: [`dbmdz/bert-base-turkish-cased`](https://huggingface.co/dbmdz/bert-base-turkish-cased) (BERTurk) | — | 35 GB Türkçe metin | Kendi etiketli setimizle ince ayar için taban. |

Türkçe duygu veri setleri ve araçlarının çapraz karşılaştırması: [arXiv 2412.05964](https://arxiv.org/abs/2412.05964).
Bu çalışma, bir veri setinde iyi olan modelin başka alanda düşebildiğini gösteriyor; kendi setimizle ölçmeden
seçim yapılmamalı.

Öneri: iki yol birlikte ölçülür — (a) hazır sınıflandırıcı, (b) LLM'e kapalı seçenek (`olumlu/olumsuz/nötr/karışık`,
vLLM `structured_outputs.choice` + logprobs, projede zaten kullanılıyor). Hangisi etiketli sette daha iyiyse o kalır.

Bilinen zorluklar: ironi (Ekşi, X), kitaba değil kargoya kızgınlık, spoiler, "kitap güzel ama çeviri kötü" gibi karışık yorum.
Bu yüzden tek duygu puanı yetmez; yön bazlı analiz şart.

### 3.2 Yön bazlı analiz (aspect-based)

Yayınevini ilgilendiren yönler (ilk liste, veriyle genişler):

- içerik / anlatım, karakter, kurgu, bilgi doğruluğu
- **çeviri kalitesi**, redaksiyon / yazım hatası
- **kapak**, **baskı kalitesi** (kağıt, cilt, punto, sayfa düzeni)
- **fiyat**
- **kargo / paketleme** (mağazanın işi — ayrı raporlanır, kitaba yazılmaz)
- yaş uygunluğu (çocuk kitapları), etkinlik kitabında malzeme

Yöntem: LLM her yorumdan `(yön, duygu, kanıt alıntısı)` üçlüsü çıkarır. Kanıt alıntısı yorumda birebir geçmelidir;
geçmiyorsa kayıt düşer (editördeki kanıt kuralıyla aynı). Türkçe e-ticaret ABSA çalışmaları var (ör. Hepsiburada
üzerinde fiyat/performans, teslimat, kalite yönleri: [ResearchGate](https://www.researchgate.net/publication/401020330_Aspect-Based_Sentiment_Analysis_for_Turkish_E-Commerce_Reviews_Using_BERTurk);
6.000 örneklik yön terimi seti: [GitHub](https://github.com/kevserbusrayildirim/turkish-aspect-term-extraction)).
Lisansları **doğrulanmadı**; yalnız ölçüm için referans.

Değer: "baskı kalitesi" ya da "çeviri" şikâyeti belirli bir baskıda yoğunlaşıyorsa yeni baskı kararına girdi olur
(Baskı Öneri ekranı).

### 3.3 Konu / tema çıkarımı

- Yorumlardan konu kümeleri: gömme servisi (CPU, :8083) ile vektör + kümeleme, küme adını LLM yazar.
- Eleştiri ve haberlerden: yazarın hangi konuyla anıldığı (ör. ödül, söyleşi, tartışma).
- Editörün kitaptan çıkardığı temalarla (book_card) karşılaştırma: "okur kitabı nasıl algılıyor" ile "kitap ne anlatıyor" farkı.

### 3.4 Sahte ve kopya yorum ayıklama

Kurallar (her biri ayrı bayrak, silme yok):
- Birebir ya da çok yakın kopya metin (gömme benzerliği) farklı ürünlerde ya da farklı hesaplarda.
- Kısa ve içeriksiz ("güzel", "harika") yorumların ani yığılması.
- Yayın tarihinden önce gelen yorum.
- Aynı saat diliminde toplu puan sıçraması.
- Hesap düzeyi sinyal (çok yorum, tek yayınevi) — kişi verisi tutulmadığı için yalnız hash üzerinden.

Bayraklı yorumlar puanlara ayrı sütun olarak girer; ekranda "bayraksız" ve "tümü" ayrı gösterilir.

### 3.5 Zaman serisi (lansman sonrası)

- Kitap başına haftalık: yorum sayısı, ortalama duygu, yön dağılımı, haber/söz sayısı.
- Referans nokta: CRM yayın tarihi. İlk 4/12/26 hafta eğrileri kitaplar arasında karşılaştırılır.
- Uyarı: web'de ölçtüğümüz şey "görünen" konuşmadır, tüm okur değildir. Kaynak kapsamı değişince eğri kırılır;
  kaynak ekleme tarihi grafikte işaretlenir.

### 3.6 Yazar görünürlüğü / medya etkisi puanı

Tek sayı yerine bileşenleri açık bir puan:
- haber sözü sayısı (kaynak ağırlıklı: ulusal gazete > blog),
- video/podcast görünümü,
- sosyal söz sayısı,
- ödül ve kısa liste,
- okur yorum hacmi ve ortalama duygu.

Ağırlıklar keyfi olmamalı: ilk sürümde bileşenler ayrı gösterilir; birleştirme ağırlığı satışla ilişkiye bakılarak
sonra kararlaştırılır. Veri azsa "yetersiz veri" yazılır, puan uydurulmaz.

### 3.7 Rakip kitap karşılaştırması

- Rakip listesi: aynı tür (`new_turlertext`), aynı hedef kitle (`new_hedefkitle`), benzer fiyat. Rakip kitap CRM'de
  olmadığından eşleşme ISBN + Wikidata ile yapılır.
- Karşılaştırma yalnız aynı kaynakta anlamlıdır (1000Kitap puanı ile Trendyol yıldızı karıştırılmaz).
- Sonuç: yön bazında fark (ör. rakipte "çeviri" olumlu, bizde olumsuz).

### 3.8 Satışla ilişki (Logo)

- Haftalık web sinyali ile Logo'daki faturalı satış (satış = faturalı satır kuralı) yan yana konur.
- Önce yalnız gecikmeli korelasyon ve görsel karşılaştırma. Nedensellik iddiası yok.
- Sonra: web sinyalinin Baskı Öneri tahminine (TimesFM denemesi) ek girdi olarak katkısı geriye dönük sınanır.
  Katkı ölçülmezse girdi eklenmez.
- Uyarı: `.155` Logo kopyası 2026-08-17'de donmuş; canlı satışla karşılaştırma canlı kaynağa erişimi bekler.

## 4. Mimari öneri

### 4.1 Nerede koşar

- **Tarama işçileri:** test sunucusu `nanobase-direct` (internet çıkışı var, köprü ve Postgres orada). Mac'te hiçbir
  şey koşmaz.
- **Duygu sınıflandırıcı:** küçük BERT modeli. İlk ölçüm GPU sunucusunda (`tt-gpu`) yapılabilir; hacim düşükse
  `nanobase-direct` CPU'su da yetebilir — ölçülmeli.
- **Yön çıkarımı / özet:** LLM kapısı üzerinden `nanobaseAI` (GPU 0), arka plan önceliğiyle. Kişinin sorusunu
  bekletmez. Editör GPU 1'e dokunulmaz.
- **Müşteri VM'i (.55):** yalnız sonuçları okur. Tarama VM'de koşmaz (ayrı karar gerekirse).

### 4.2 Zamanlama

- systemd timer (projede alışılmış yol). Önerilen sıklık kaynağa göre: haber RSS günde birkaç kez, yorum kaynakları
  günde bir, Wikidata/künye haftada bir. Kesin sıklık kota ve hacim ölçüldükten sonra.
- İlk çalıştırma elle yapılır, zamanlayıcıya sonra bırakılır (proje kuralı).
- Artımlı: her kaynak için "son görülen" imleci tutulur; yalnız yeni kayıt çekilir.

### 4.3 Depolama (Postgres, köprünün veritabanı — taslak)

```sql
-- Kaynak tanımı ve nezaket ayarı
web_source(id, ad, tur /* haber|yorum|sosyal|kunye */, erisim /* api|rss|lisans */,
           hiz_siniri_saniye, robots_kontrol_tarihi, hukuk_onayi /* bool + not */, aktif)

-- Web'deki bir kitap/yazar kimliği ve CRM bağı
web_entity(id, kaynak_id, dis_kimlik /* ISBN, Wikidata Q, ürün kodu */, tur /* kitap|yazar */,
           crm_kitap_id NULL, crm_contact_id NULL,
           eslesme_yolu /* isbn|ad_yazar|wikidata|insan */, guven /* kesin|olasi */, onaylayan NULL, onay_tarihi NULL)

-- Tek bir yorum/haber/gönderi (kişi verisi yok)
web_item(id, kaynak_id, entity_id, dis_id, url, yayin_tarihi, cekim_tarihi,
         yazar_hash /* tek yönlü, tuzlu */, puan NULL, dil,
         metin NULL /* saklama kararına bağlı */, metin_hash, ozet NULL,
         kopya_grubu NULL, sahte_bayraklari jsonb)

-- Model çıktıları (sürümlü, yeniden hesaplanabilir)
web_sentiment(item_id, model_surumu, etiket, olasilik, hesap_tarihi)
web_aspect(item_id, model_surumu, yon, duygu, kanit_alinti, hesap_tarihi)

-- Haftalık toplamlar (ekranın okuduğu)
web_weekly(entity_id, hafta, kaynak_id, yorum_sayisi, soz_sayisi, ort_duygu, yon_dagilimi jsonb, bayrakli_sayi)

-- Tarama günlüğü
web_crawl_log(id, kaynak_id, baslangic, bitis, istek_sayisi, yeni_kayit, hata, http_durumlari jsonb)
```

Notlar:
- `metin` sütunu hukuk kararına bağlı. Karar "saklama" ise yalnız özet, hash ve model çıktısı kalır.
- Kişi adı, profil bağlantısı, fotoğraf tutulmaz.
- Silme talebi: kaynakta silinen yorum yeniden taramada görülürse bizde de silinir (tutulma süresi karara bağlı).

### 4.4 Tekrar tarama ve nezaket

- Her kaynak için tek eşzamanlı bağlantı, `hiz_siniri_saniye` kadar bekleme, 429/503'te üstel geri çekilme.
- Açık User-Agent: uygulama adı + iletişim adresi (Open Library bunu açıkça istiyor).
- robots.txt her çalıştırmada önbellekten okunur, günde bir tazelenir. Kapalı yol hiç istenmez.
- `hukuk_onayi` işaretli olmayan kaynak çalışmaz (yazılımda kilit).
- Koşullu istek (ETag / If-Modified-Since) destekleyen kaynakta kullanılır.
- Kota sayacı (YouTube birimi, X kredisi) günlükte tutulur; tavana yaklaşınca iş durur, ekranda görünür.
  Tavan kullanıcı isterse konur; kendiliğinden sayı tavanı konmaz, yalnız sağlayıcının tavanına uyulur.

### 4.5 Portalda nerede görünür

- **Kitap sayfası `/kitap/:id`:** "Okur ve basın" bölmesi — kaynak başına yorum sayısı, duygu dağılımı, yön tablosu
  (kanıt alıntılarıyla), haftalık eğri, son haberler (başlık + bağlantı), sahte bayrağı sayısı, Logo satışla yan yana grafik.
- **Yazarlar `/yazarlar` (Kişiler):** yazar kartında görünürlük bileşenleri, ödüller (Wikidata), son haberler,
  kitaplarının okur duygusu özeti.
- **Masam / editoryal ana sayfa (`/editoryal`):** "bu hafta dikkat" kartı — olumsuz yön sıçraması (ör. baskı kalitesi
  şikâyeti), yeni basın sözü, yeni ödül. Kart adı ve yeri **doğrulanmadı** (bu dalda "Masam" adı kodda bulunamadı).
- **Baskı Öneri:** ileride web sinyali, katkısı ölçülürse ek sütun.
- Eşleşme onayı: "olası" eşleşmeler için küçük bir onay listesi (yönetim ya da editoryal ekranında).

## 5. Aşamalı yol haritası

Süreler tahmindir; tek geliştirici, başka iş yokken. Ölçüm olmadan sonraki aşamaya geçilmez.

### Aşama 0 — Karar ve ölçüm seti (≈1 hafta)
- Çıktı: kaynak başına hukuk görüşü listesi; saklama kararı (tam metin / özet); 300–500 elle etiketlenmiş kitap
  yorumu (duygu + yön). Etiketleme yayınevi ekibi ile.
- Kaynak: etiket seti, izinli ya da kullanıcının elle verdiği yorumlardan (ör. kendi satıcı panelinden dışa aktarım).
- Risk: hukuk yanıtı gecikir. Ölçüm: iki etiketleyici arasındaki uyum.

### Aşama 1 — MVP: açık kaynaklar + eşleştirme (≈2–3 hafta)
- Çıktı: Wikidata/Open Library/Google Books ile ISBN künye eşleşmesi; Google News RSS + GDELT haber toplama;
  `web_*` tabloları; kitap sayfasında "Basında" bölmesi (başlık + bağlantı + tarih).
- Ölçüm: CRM'deki ISBN'li kitapların kaçı dış kaynakta bulundu; 100 rastgele eşleşmede elle doğruluk.
- Risk: Türkçe kitap kapsamı düşük çıkabilir; RSS biçimi değişebilir.

### Aşama 2 — Duygu ve yön (≈2–3 hafta)
- Çıktı: aday modeller ve LLM kapalı seçeneği Aşama 0 setinde karşılaştırılır; kazanan kurulur; yön üçlüleri
  kanıt alıntısıyla; kitap sayfasında duygu/yön tablosu.
- Ölçüm: sınıf başına F1, karışıklık matrisi, yön çıkarımında kanıt alıntısı birebir oranı. Eşik kullanıcıyla
  konuşulur; eşik altındaysa ekrana çıkmaz.
- Risk: nötr ve karışık sınıf zayıf; ironi.

### Aşama 3 — Resmi API'li sosyal ve video (≈2 hafta)
- Çıktı: YouTube Data API (kitap adı/yazar araması + yorumlar), X kullandıkça öde (bütçe onayıyla), Instagram
  yalnız TİMAŞ hesabı etiketleri. Yazar görünürlük bileşenleri `/yazarlar`'da.
- Ölçüm: kota/kredi harcaması; eşleşme doğruluğu (aynı adlı başka kitap/kişi karışması).
- Risk: maliyet; kampanya/bot gürültüsü.

### Aşama 4 — Okur yorumu kaynakları (izne bağlı, süre izne göre)
- Çıktı: yalnız izin/lisans alınan kaynaklar: pazar yeri satıcı API'leri (Trendyol vb., kendi ürünlerimiz),
  1000Kitap ile veri anlaşması, gerekirse ücretli sosyal dinleme sağlayıcısı.
- Ölçüm: kaynak başına hacim, sahte bayrak oranı.
- Risk: izin çıkmaz; bu durumda aşama atlanır, kazıma yapılmaz.

### Aşama 5 — Zaman serisi, rakip ve satış (≈2–3 hafta)
- Çıktı: haftalık eğriler, lansman karşılaştırması, rakip kitap seti, Logo satışla yan yana grafik, Masam kartı.
- Ölçüm: web sinyali Baskı Öneri tahminine eklenince geriye dönük hata değişiyor mu. Değişmiyorsa eklenmez.
- Risk: donmuş Logo kopyası; kaynak kapsam değişimi eğriyi kırar.

## 6. Kullanıcıya sorulacak kararlar (en fazla 5)

1. **Hangi kaynaklar için hukuk görüşü alınsın ve kim alacak?** Özellikle 1000Kitap ve pazar yeri yorumları.
   İzin çıkmayan kaynak taranmayacak.
2. **Yorum metninin tamamı saklansın mı, yoksa yalnız özet + model çıktısı mı?** (KVKK ve telif açısından en
   az riskli olan ikincisi.)
3. **Ücretli kaynak bütçesi var mı?** X kullandıkça öde, sosyal dinleme ya da medya takip ajansı. Varsa aylık üst
   sınır ne?
4. **TİMAŞ'ın pazar yeri satıcı hesapları (Trendyol, Hepsiburada vb.) ve Instagram iş hesabı API için
   kullanılabilir mi?** Kendi ürünlerimizin yorumlarına en temiz yol bu.
5. **Etiket setini kim hazırlayacak?** 300–500 kitap yorumu, duygu + yön; yayınevinden bir-iki kişi. Bu set olmadan
   duygu puanı ekrana çıkmaz.
