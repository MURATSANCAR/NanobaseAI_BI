# ZEKI AI CHAT — ayrıntılı kod incelemesi, 2026-09-30

## Denetim sonrası temizlik

Kullanıcının silme talebiyle `c1f548205` kaynak sürümünde:

- `.github/actions/update-version-durability/` bütün dosyalarıyla silindi.
- `@rocket.chat/onboarding-ui` bağımlılığı, importları ve lockfile kayıtları kaldırıldı. Yönetici/kuruluş adımları yerel `packages/ui-client/src/views/setupWizard/components/` bileşenlerini kullanır. Kullanılmayan ek react-hook-form sürümü de kaldırıldı.
- `fetchMarketplaceApps.ts` içindeki abonelik/lisans/fiyat/kullanıcı kotası şemaları ve bulut jetonu isteği silindi; katalog yerel boş liste döndürür.
- NPS varsayılanı kapalı yapıldı; dağıtımda zaten kapalıydı.
- Giriş yetkisi/parola, özel uygulama kaynağı/modül ve Node/Mongo uyumluluk kontrolleri korunur. Diğer harici UI paketleri, protokol kimliği, hedef engelleme listeleri ve geçiş referansları bu değişikliğin kapsamı değildir.

Aşağıdaki ilk denetim kaydı tarihsel kanıttır; güncel silme sonrası durum değildir. Sunucu kabul sonuçları tamamlanınca bu bölümde kaydedilir.

İncelenen kaynak: `ebc692820489fb95701a98575ae4dc58df9a4881`.
Çalışan imaj salt okunur sorguyla doğrulandı: `zeki-ai-chat:8.5.3-157d9f6a8`.

## Sonuç

İncelenen birinci taraf lisans/yetenek, başlangıç, bulut, marketplace ve telemetri yollarında gizli Rocket.Chat lisans süresi, kullanıcı kotası veya uzaktan kapatma mekanizması bulunmadı. **Kod/imaj tamamen üretici izlerinden arınmış değil.** Aşağıdaki kalıntılar vardır. Bunların varlığı kötü niyet veya çalışan dış bağlantı kanıtı değildir.

| Bulgu | Kanıt / etkisi |
|---|---|
| Kullanılmayan dış yayımlama action'ı | `.github/actions/update-version-durability/index.js:27`: Document360 API çağrısı; GitHub release okuma ve belge güncelleme kodu. PUBLISH false olsa da belge fork/update işlemleri bulunur. Kök ve sohbet `.github` taramasında çağıran workflow bulunmadı. Uygulama başlangıç kodu değil; çalıştırılmadı. |
| İmajda eski bulut/deneme UI kodu | Sunucu npm ağacındaki `@rocket.chat/onboarding-ui@0.36.2` içinde CreateCloudWorkspace, RegisterOffline, RegisterServer, NewAccount ve RequestTrial bileşenlerinde üretici bağlantıları var. CJS/ESM kopyaları dahil 16 dosya/anahtar eşleşmesi. Kaynak uygulamada bu ekranlara import bulunmadı; `packages/ui-client/src/views/setupWizard/steps/AdminInfoStep.tsx:2` ve `OrganizationInfoStep.tsx:3` yalnız yönetici/kuruluş bileşenlerini kullanıyor. Tam paket imajda bulunuyor; bütün iç modüllerin erişilemezliği kanıtlanmış değildir. |
| Marketplace lisans şemaları duruyor | `apps/meteor/ee/server/apps/marketplace/fetchMarketplaceApps.ts:79`: subscriptionInfo, trial, license, fiyat/kota alanları şema olarak kalmış. `MarketplaceAPIClient.ts:17` ağ yerine yerel boş Response üretir; workspace token sağlayıcısı hata verir. Bu şema mesajlaşma kotası değildir. |
| Uygulama etkinleştirme kuralları var | `apps/meteor/ee/app/capabilities/server/canEnableApp.ts:8`: motor hazır olmalı, kaynak private olmalı, gereken modül bulunmalı. Marketplace uygulaması reddedilir; şirket içi kullanıcı/mesaj sınırı değildir. |
| Başlangıçta süreç sonlandırma var | `apps/meteor/server/startup/serverRunning.ts:21,37`: Node sürüm dosyası/Node-Mongo uyumluluğu. Lisans tarihi ya da üretici sunucusundan emirle kapanma değil. |
| NPS/telemetri isimleri duruyor | NPS varsayılan ayarı true, dağıtım compose'u false. `server/services/nps/service.ts:50` sonucu dışarı göndermek yerine yerel anketi kapatır. Kayıtlı iki telemetry handler yerel sayaç günceller. |
| Teknik üretici kimlikleri kalıyor | UIKit `engine: 'rocket.chat'`, harici npm isimleri, engelleme listeleri, geçiş ve yorumlar. `deploy/zeki/logo/package.json` yerel ZEKI logo ikamesidir; npm dizininin adı tek başına Rocket logosunun gösterildiğini kanıtlamaz. |

## Kontrol edilen davranışlar

- `ee/packages/capabilities/src/index.ts:15`: CoreModules yerelde açılır, callback external=false/valid=true; lisans doğrulama/son kullanma çağrısı yok.
- `packages/server-fetch/src/index.ts:123`: hedef her yönlendirme adımında üretici engeline sokulur. Bu koruma yalnız bu fetch sarmalayıcısı içindir; bütün soketleri tek başına kapsamaz.
- `app/cloud/server/functions/retrieveRegistrationStatus.ts:14`: kayıtlı=false; cloud token sağlayıcısı yerel hata verir.
- Kaynaktaki tek bulunan kendi paket prepare kancası `apps/meteor/playwright.prepare.mjs`: Playwright ağ yöneticisinde yerel cacheDisabled metnini değiştirir; ağ isteği veya lisans kontrolü değil.
- `.yarnrc.yml` yerelde paketlenmiş engines eklentisi için uzak GitHub spec adresi taşır. Derleme bağımlılığı ile çalışan sohbet trafiği ayrı kapsamdır.

## Kapsam ve sınırlar

Statik tarama 7.922 metin dosyasını kapsadı; ikililer, symlinkler, lockfile, test/spec ve belge dizinleri ana kaynak taramasından dışlandı. Paket import isimleri dışındaki 130 üretici eşleşmesi yorum, protokol, engelleme, örnek ve kalıntı kod olarak incelendi. Ham envanter `evidence/2026-09-30-code-audit/source-inventory.json` içindedir; bu sayılar bütün dosyaların satır satır insan incelemesi değildir.

Çalışan imajın sunucu npm ağacında `@rocket.chat` dizini altındaki 18 üst paket konumunda 419 JavaScript dosyası seçili üretici uçları ve process.exit dizgileriyle tarandı. Bu konumlardan logo, yerel ikamedir. Paket manifestlerinde preinstall/install/postinstall/prepare kancası bulunmadı. Tarama iç içe node_modules, Deno önbelleği, tüm tarayıcı bundle'ları veya dinamik oluşturulan bütün adresleri kapsamaz; bütün bağımlılıkların davranışsal güvenlik kanıtı değildir.

Bu tur salt okunur kod/imaj incelemesidir. Kaynak davranışı, canlı veri ve ağ kuralları değiştirilmedi; yerel test çalıştırılmadı. Önceki canlı ağ/mesajlaşma kabulü bu tur yeniden çalıştırılmadı. Gizlenmiş her türlü kodun yokluğuna mutlak garanti verilmez. Kalıntılar bu raporla tespit edildi, bu tur silinmedi.
