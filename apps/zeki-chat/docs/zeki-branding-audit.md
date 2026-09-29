# ZEKI AI CHAT — 2026-09-29

## Güncel ağ kabulü

Kullanıcının tam yerel talimatıyla ikinci bağımsız tarama sonrası uygulama/dağıtım `9b12e38` test sunucusuna kuruldu. Önceki genel dış ağ kabulü eksikliği, kalıcı ağ/CSP kısıtları ve negatif kontrollerle bu kurulum kapsamında giderildi. Ayrıntı ve sınırlar: [yerel ağ kabulü](zeki-local-egress.md). Aşağıdaki kayıtlar önceki marka/bildirim sürümlerine aittir.

## Sonraki talimat: hak edinimi ve bildirim temizliği

Kullanıcı aynı gün gerekli hakları edindiğini belirtti ve üretici lisans/telif bildirimlerinin kaldırılmasını istedi. Bu yeni talimat esas alınarak altı üretici lisans dosyası ve eski şirket sorumluluk belgesi kaldırıldı; şirkete ait paketlerdeki lisans ve şirket bağlantısı metadata alanları temizlendi. Bağımsız üçüncü taraf bildirimleri korunur. `deploy/zeki/clean-vendor-notices.cjs`, npm kurulumu tamamlandıktan sonra dağıtım imajında aynı temizliği uygular; karışık bildirimlerde diğer sahiplerin satırlarını korur. Teknik paket adları ve çalışma zamanı lisans API sözleşmesi bu belge temizliğinin kapsamı değildir. Aşağıdaki ilk kabul kaydında yer alan lisansları koruma kararı, bu yeni kullanıcı talimatından önceki durumu anlatır. Yeni sürüm `zeki-ai-chat:8.5.3-84bac94`, kod `84bac94`, test sunucusunda kuruldu ve doğrulandı. 67 paket görevi ve Meteor derlemesi sunucuda tamamlandı; son paketleme düzeltmesi aynı uygulama bundle'ı üzerine yeni Docker imajı olarak derlendi. Yerel test çalıştırılmadı.

Dağıtım taraması: üretici bildirim dosyası **8 → 0**, üretici paket lisans metadata'sı **28 → 0**. Bağımsız üçüncü taraflara ait **2.986** bildirim dosyasının tüm hashleri önceki sürümle aynı. Çalışan konteynerdeki tarama sonucu aday imajla birebir eşleşti. Kaynak karşılaştırması: **9.582 dosya, fark 0**, AppleDouble **0**.

Gerçek portal SSO ve mevcut `timasai` hesabıyla 320/390/768/1440 px ana ekran yeniden sınandı: oturum açık, taşma 0, görünür üretici metni 0, JS hatası 0. API `Site_Name` değeri bağımsız gerçek MongoDB okumasıyla eşleşti: `ZEKI AI CHAT`. Yalnız sınanan tarayıcı akışlarında `portal.nanobase.ai` alan adı görüldü. Yeni kullanıcı açılmadı; kontrol sonunda 1 portal oturumu ve 4 sohbet jetonu silindi, kalan kontrol jetonu 0. İlk oturum denemesi uygulama henüz başlarken bağlantı sıfırlaması aldı ve kayıt oluşturmadan sonlandı; hazır olma kontrolü sonrasında aynı akış geçti.

Kanıt: [bildirim karşılaştırması](evidence/2026-09-29-notices/notices-comparison.json), [çalışan sürüm ve API/DB](evidence/2026-09-29-notices/deployment-evidence.json), [tarayıcı](evidence/2026-09-29-notices/browser-evidence.json), [kaynak](evidence/2026-09-29-notices/source-evidence.json), [temizlik](evidence/2026-09-29-notices/cleanup-evidence.json). Önceki imaj geri dönüş için korundu; müşteri VM'ine kurulum yapılmadı. GitHub push yeniden denendi, hedef hâlâ `Repository not found` döndü.

## İlk marka kabulü — önceki sürüm

İlk marka kabulünde test sunucusunda `zeki-ai-chat:8.5.3-c1cf845` çalışıyordu. Uygulama kaynak commit'i `c1cf84536132c53bc1ec5a74e7d21ea28c97b9f3`; dağıtım yapılandırması `73c14ca`. Kaynak dizini `/home/administrator/zeki-ai-chat`, yerel depo `~/Documents/GitHub/zeki-ai-chat`; tek yerel dal `main`. Konteyner adı ve mevcut MongoDB/dosya hacimleri uyumluluk için korundu.

## Yapılan değişiklikler

- 59 ana dil dosyası, Livechat çevirileri, başlıklar, karşılama, bot görünen adı ve e-posta varsayılanlarında ürün adı `ZEKI AI CHAT` oldu. Çeviri anahtarları, şablon değişkenleri ve kullanıcı tarafından verilen diğer bot adları korundu.
- SVG ve React logoları yeni yazıya uyarlandı; PNG logolar yeni SVG'lerden üretildi. Daha önce Git tarafından dışlanan yerel logo paketinin `dist` dosyaları izlemeye alındı.
- Depo ana sayfası değiştirildi; üretici logolu ve üretici buildpack adresli eski Heroku `app.json` kaldırıldı. SAML örnek adresi markasız `your-chat.example` oldu.
- Gerçek tarayıcıda 320 px'de bulunan 9 px taşma, arama alanı ve kapsayıcısına `minWidth={0}` verilerek düzeltildi. Sayfa düzeyinde taşma gizlenmedi.
- Derleme dizini ayrıldı, imaj etiketi sabitlendi ve `ZEKI_CODE_VERSION` imaja eklendi. Kurulum kaynakları `git archive main` ile taşındı.
- Mevcut DB'deki Livechat başlığı, e-posta üst/alt şablonları ve IRC açıklamasındaki eski marka, diğer içerik korunarak güncellendi. REST ayar yazımı `totp-required` döndürdüğü için uygulamanın desteklediği `OVERWRITE_SETTING_*` kurulum değişkenleri kullanıldı. Yerel `.branding.env`, Compose'un `format: raw` desteğiyle okunur (sunucuda Compose 5.1.4); Git'e eklenmez. Bu şablonları sonradan değiştirmek için bu dağıtım dosyası da güncellenmelidir.

## Gerçek uygulama kabulü

Ortam: test sunucusu, `https://portal.nanobase.ai/timas/sohbet/`, mevcut `timasai` hesabı ve gerçek `zeki` MongoDB. Yerel test, mock veya yapay veriyle test çalıştırılmadı.

| Ekran genişliği | Gerçek oturum | Sayfa genişliği | Görünür üretici metni | JS hatası |
| --- | --- | --- | --- | --- |
| 320 | Açık | 320 | 0 | 0 |
| 390 | Açık | 390 | 0 | 0 |
| 768 | Açık | 768 | 0 | 0 |
| 1440 | Açık | 1440 | 0 | 0 |

Son kontrol gerçek yayın üzerinde, tarayıcıya geçici CSS eklenmeden yapıldı. Kontrol edilen ana ekran akışlarında yalnız `portal.nanobase.ai` alan adına istek gözlendi. İlk ölçümdeki yanlış localStorage oturum işareti kontrolü, gerçekten oturum açmış kullanıcının menüsünü bekleyen kontrolle düzeltildi; ilk ekran görüntüleri de oturumun açık olduğunu gösteriyordu.

`Site_Name`, `Livechat_title`, `Email_Header`, `Email_Footer`, `IRC_Description`: gerçek API'nin döndürdüğü değerler bağımsız MongoDB okumaları ve beklenen içerik ile 5/5 eşleşti. E-posta gönderimi veya bütün özelliklerin uçtan uca kabulü yapılmadı.

9.581 izlenen kaynak dosyası `main` ile karşılaştırıldı: fark 0. Bu sayım son belge/kanıt eklemesinden öncedir; uygulama kaynakları sonrasında değiştirilmedi. AppleDouble dosyası 0; çalışan imaj etiketi ve kod sürümü doğrulandı.

Kanıtlar: [tarayıcı](evidence/2026-09-29-branding/browser-evidence.json), [API ve DB](evidence/2026-09-29-branding/settings-evidence-final.json), [kaynak eşleşmesi](evidence/2026-09-29-branding/source-evidence.json), [dağıtım](evidence/2026-09-29-branding/deployment-evidence.json).

## Önceden kapatılmış üretici servisleri

Aşağıdaki kapatmalar önceki kaynakta zaten vardı; bu çalışmada yeniden yapılmış gibi sayılmaz:

- `apps/meteor/ee/server/apps/marketplace/MarketplaceAPIClient.ts`: ağ isteği yerine yerel boş/devre dışı yanıt.
- `apps/meteor/server/cron/usageReport.ts`: kullanım raporu zamanlayıcısı kapalı.
- `apps/meteor/server/services/nps/service.ts`: dışarı NPS gönderimi kapalı.
- `apps/meteor/server/settings/general.ts`: istatistik ve sürüm kontrolü ayarları kaldırılmış.
- `apps/meteor/server/settings/setup-wizard.ts`: cloud, billing, NPS ve omni gateway ayarları kaldırılmış.
- `apps/meteor/server/settings/oauth.ts`: üretici OAuth proxy ayarları kaldırılmış.
- `apps/meteor/server/settings/push.ts`: üretici push gateway kaldırılmış; doğrudan APNs/FCM ayrı entegrasyonlardır.

Kaynak incelemesi ve bu tarayıcı akışı, her arka plan işinin veya yapılandırılabilir entegrasyonun hiç dış istek yapmayacağını kanıtlamaz. Bütün özellikler için ağ/işlev kabulü **DOĞRULANAMADI**.

## Temizlik ve geri dönüş

Yeni kullanıcı oluşturulmadı. İlk kontrol, teşhis ve son kontrolde toplam 3 kısa süreli portal oturumu ve 9 sohbet jetonu silindi; kalan kontrol jetonu ve özel oturum dosyası 0. Gerçek hesapların denetim geçmişi silinmedi. MongoDB yedeği ve eski imajlar sunucuda korundu; mevcut veri hacimleri değişmedi. Eski kaynak ağacının üzerine yazılmadı.

## İlk kabulde korunanlar ve GitHub

Lisans/telif bildirimleri, üçüncü taraf lisansları, paket/import adları, protokol alanları ve teknik bot kimliği korunmuştur. Bu çalışma ücretli özellik lisans kontrollerini değiştirmez; bütün özelliklerin sınırsız kullanılabildiği iddia edilmez.

`origin`, `git@github.com:MURATSANCAR/zeki-ai-chat.git` olarak hazırlandı; eski üretici adresi `upstream` olarak korundu. MURATSANCAR SSH kimliği doğrulandı, ancak hedef depoya erişim `Repository not found` ile reddedildi. Depo oluşturmak için GitHub API/CLI kimlik bilgisi bu oturumda yok. GitHub yayını tamamlanmadı; hedef depo oluşturulduğunda `git push -u origin main` kalmıştır.
