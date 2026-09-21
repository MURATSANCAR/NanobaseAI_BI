# Editoryal ana sayfa: hazır veri ve arka plan yenileme

## Davranış

`/timas/editoryal` özetleri ziyaretçiyi beklemeden sunucuda hazırlanır ve özel dizinde saklanır. `/api/v1/editorial/home` yalnız oturumlu kullanıcıya hazır bölümleri ve o kişinin yetkili masa kayıtlarını verir. CRM sorguları sayfa isteğine bağlanmaz. Kullanıcı masası her istekte mevcut yetki süzgecinden geçer, ortak dosyalarda tutulmaz.

- Kaydedilen bölümler: sözleşme özeti, kurul kararları, editör özeti, katkı rolleri, yaklaşan sözleşmeler ve okunmuş kitap seçimi.
- Her bölüm kendi veri zamanı/hatasını taşır. Başarılı boş sonuç kaydedilir; başarısız veya kesilmiş sonuç önceki başarılı kaydı değiştirmez. Dosyalar atomik değiştirilir, izinler 0600; dizin 0700.
- Kapsam anahtarı tenant, datasource, CRM şeması, uyarı gün sayısı, yıl ve özet kod sürümünü içerir. İşlem/dosya kilidi aynı yenilemenin eşzamanlı kopyalarını engeller.
- Servis açılışında zamanlayıcı başlar; 300 saniyede bir gerçek kaynağı okur. Yeniden başlatmada diskten son başarılı veri okunur. Zamanlayıcıdaki kontrol 5 saniyedir, DB sorgusu sıklığı 300 saniyedir.
- Oturum açılınca istemci özet verisini ve ekran kodunu önceden yükler. Sorgu kullanıcı adına göre ayrılır; normal arka plan yoklaması 300 saniye. Yalnız hiç hazırlanmamış bölüm varsa kısa yoklama kullanılır.
- Güncelleme sırasında bileşen yeniden bağlanmaz ve sayfa yenilenmez; sohbet taslağı, seçimler ve kaydırma korunur. Mevcut eser mutasyonları ana sayfa önbelleğini de geçersiz kılar.
- Son güncelleme İstanbul saatinde gösterilir. Bağlantı hatasında son başarılı değerler ve uyarı görünür; yüklenmemiş değerler sıfır diye gösterilmez.
- Kitap seçimi model yanıtını beklemez; ayrı Editor katalog API'sinin `contentAvailable` kayıtlarından gelir. Kapak/katalog kaydı tek başına okunmuş içerik sayılmaz. Katalogda uygun kayıt yoksa liste gerçekten boştur; tam kitap kabulü iddiası yok.

## Kurulum

Test sunucusu: `nanobase-direct`. Backend `/data/nanobaseai/bi/frontend/backend`; servis `nanobase-semantic-bridge`. Veri dizini `/data/nanobaseai/bi/var/editorial-home`; `EDITORIAL_HOME_CACHE_DIR` ile değiştirilebilir. Varsayılan dizin `scripts/server/deploy-semantic-bridge.sh` tarafından servis kullanıcısına ait oluşturulur. Özelleştirilmiş dizinin sahipliği ayrıca aynı olmalıdır.

Frontend sunucuda `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build` ile derlenir; `cockpit/dist`e yayınlanır. Müşteri VM'ine kurulmadı.

## Doğrulama kapsamı

Yerel test veya sentetik veri kullanılmaz. `scripts/server/editorial-home-acceptance.py`, normal AD oturumuyla gerçek köprü API'sinin tam cevabını alır; eski API uçlarının tam veri alanlarıyla ve bağımsız salt okunur CRM sorgularıyla karşılaştırır. Katalog referansı ayrı Editor API'sidir. Yetkisiz kullanıcı/caller kontrolleri, sonuç kesilmesi, tüm yıl/editör/rol değerleri, yaklaşan sözleşmeler ve masanın mevcut erişim süzgeci kapsanır.

İlk beş CRM bölümü 30/30 kontrolü geçti. Canlı CRM daha sonra değişti: atanmamış yeni proje durumu 458→459, toplam 916→917. Eski anlık görüntü ile güncel kaynağın iki karşılaştırması bu farkı yakaladı; eski kopya güncel kabul edilmedi. Güncelleme sonrası yeniden doğrulama ve gerçek beş dakikalık tarayıcı döngüsü aşağıdaki kanıtlarda kayıt altına alınır.

### Son yayın sonucu

- **32/32 PASS**: `docs/audits/editorial-home-2026-09-21/api-reference.json`. Son API yanıtı sunucu üzerinden 14,5 ms; bu tam internet sayfa yükleme süresi değildir. API'deki tüm bölümler hazır; kullanıcı masası ve eski uçların tam veri alanları eş, bağımsız CRM karşılaştırmaları geçti.
- `browser.json`: yeni bir portal sekmesinde Kampüs → Editoryal ilk açılışı dolu (`loading=false`). 320/390/768/1440 genişliklerinde yatay taşma yok.
- Gerçek bekleme: tarayıcının veri istekleri 17:15:51 → 17:20:52 (301 sn); son yayının eksik bölüm hazırlığı tamamlanırken 17:21:02'de kısa takip. Kullanıcının sayfası yenilenmeden güncelleme saati 17:12→17:20, atanmamış proje 916→917 oldu; gönderilmemiş sohbet taslağı aynen kaldı. Yapay saat/hızlandırma yok.
- Gerçek yeniden başlatmalarda eski dosyalar ve önceki başarılı değerler korundu. Yarım yenilemenin yeniden başlatma sonrası ertelenmesi, `finishedAt` kontrolüyle düzeltildi. Son kod yeni kapsam dizinini gerçek verilerle doldurdu; yeni güncel API tekrar doğrulandı.
- `before-refresh.json` güncel veri değişimini yakalayan önceki koşudur; son sürüm kabulü yerine kullanılmaz. Kontrol listesi ve statüler JSON dosyalarında, çözümler bu belgededir.
- Açık sınır: ayrı Editor kataloğu şu anda `contentAvailable=true` kitap döndürmüyor; bu yüzden okunmuş kitap seçimi boş. Kitap analizi/içerik kalitesini bu çalışma doğrulamaz. Bağlantıyı yapay biçimde kesen veya sentetik kullanıcı/eser üreten test yapılmadı.
