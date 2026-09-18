# Yükleme sonrası doğru analiz kaydına geçiş: plan ve gerçek kabul

`apps/editor/scripts/verify-upload-analysis-navigation.cjs` gerçek tarayıcı/API/PostgreSQL ile çalıştırıldı. Son web `source-preview-v15-r2-20260918` üzerinde 64 sayfalık farklı gerçek kitapla dört genişlikte navigasyon/idempotency kabulü **PASS**. Aşağıdaki ön koşullar kabul sözleşmesidir; önceki adayın ve son webin sonuçları ayrı korunur. Bu sonuç tam kitap veya kaynak soru-cevap kabulü değildir.

## Ön koşullar

- Script, uygulamanın CPU sunucusundaki kurulum dizininde çalışır. Linux ve açıkça verilen `EDITOR_VERIFY_REMOTE_HOST` gerçek `hostname` ile eşleşmelidir; Mac üzerinde çalışmayı reddeder.
- `EDITOR_VERIFY_ROOT` hedef gerçek kurulum kökünü seçer; Compose, PostgreSQL, `secrets/api_token` ve kanıt dizini bu kökten kullanılır. Verilmezse scriptin üst dizini kullanılır. `EDITOR_VERIFY_BASE_URL` hedef API loopback adresidir. `EDITOR_VERIFY_UI_BASE_URL` ayrı aday frontend loopback adresi olabilir; verilmezse API adresi kullanılır. Aday frontend'in gerçek hedef API'ye yönlenmesi gerekir; UI'nin yarattığı işin hedef PostgreSQL'de bulunması kontrol edilir. API anahtarı çıktıya yazılmaz. Playwright bağımlılığı scriptin kendi kurulumundaki `runtime/browser-check` dizininden yüklenir.
- `EDITOR_VERIFY_COMPLETED_UPLOAD_ID` gerçek, tamamlanmış bir PDF yüklemesi olmalıdır. Bu yükleme için frontend'in `upload:<id>:analysis` anahtarı daha önce kullanılmamış olmalıdır. Önceden başlatılmış kullanıcı işi iptal edilmez.
- `EDITOR_VERIFY_PROTECTED_CONTENT_VERSION` ana kitabın gerçek içerik sürümüdür. Seçilen yükleme hem farklı içerik sürümüne hem farklı PDF hash'ine sahip olmalıdır. Ana kitabın başka bir yüklemesi kabul edilmez.
- Hedef kurulum DB'sinde herhangi bir `QUEUED`/`RUNNING` iş veya `PARSING` yükleme varsa script yeni iş açmadan hata verir. Çalıştıran kişi ayrıca model pilotu/kurulum doğrulaması bulunmadığını kontrol etmelidir; bu script diğer Docker kurulumlarının işlerini göremez. Ayrı gerçek DB üzerinde kaynakları uygun ve ana uygulamadan izole bir kabul, ana görevin koordinasyonuyla ayrıca yürütülebilir; ana R5'e iş/iptal isteği gönderilmez.
- CPU ortamında mevcut `runtime/browser-check/node_modules/playwright`, `/usr/bin/google-chrome`, Docker Compose ve gerçek editor PostgreSQL kullanılır. Fixture, mock, sahte cevap veya yerel test yoktur.

## Gerçek senaryo

1. Gerçek yüklemenin API durumunu PostgreSQL ile karşılaştırır; ana kitap ve kaynak kayıtlarının başlangıç özetini saklar.
2. Tarayıcıdan önceki yüklemeyi seçip **Kitap analizini başlat** düğmesine basar. Gerçek POST cevabındaki tam `job_id` ve `generation_id` kaydedilir.
3. Yalnız bu kabulün oluşturduğu işi gerçek iptal API'siyle iptal eder; API ve PostgreSQL birlikte `CANCELLED` olana kadar en çok 180 saniye bekler. Yeni iş bu bitmeden başlamaz.
4. Aynı farklı kitapta ikinci işi farklı idempotency anahtarıyla açıp iptal eder. Artık listede en yeni iş ikinci iştir. Liste sırası/kimliği/status'u bağımsız PostgreSQL sorgusuyla eşleştirilir.
5. 320, 390, 768 ve 1440 pikselde **Analizi görüntüle** ilk kesin işi seçmelidir. Her genişlikte sayfa yeniden açılır ve oturum yeniden başlatılır; yükleme tekrar seçilip analiz başlatma düğmesine basılır. Kalıcı idempotency ilk iş/nesli döndürmeli; toplam yeni iş sayısı tam iki kalmalıdır.
6. Yatay sayfa taşması ve ekran görüntüsü kaydedilir. Kaynak manifestleri, inceleme sayısı ve ana kitabın iş/kayıt sayıları değişmemelidir.

Kanıt `evidence/upload-analysis-navigation-<uuid>/verification.json` ve dört ekran görüntüsüdür. Script hash'i rapora yazılır. Hata halinde yalnız kendi yeni idempotency anahtarları üzerinden iş kimliklerini geri bulup aktif olanları iptal etmeye çalışır. İptal doğrulanamazsa `cleanup_error` ve başarısız çıkış bırakır; bu durum kapanmış sayılmaz. İptal edilmiş işler gerçek denetim kaydı olarak korunur, silinmez.

## Kabul sınırı

Bu kontrol navigasyon, kalıcı idempotency, kontrollü iptal ve mobil görünüm içindir. Kitabın anlamsal doğruluğu veya üretim kabulü değildir. İşçi iptal isteğini almadan kısa bir gerçek kaynak/model işi başlayabilir; script model çağrısı olmayacağını vaat etmez. Yeni iş açma kapasite kontrolü API tarafından da uygulanır; bütün harici model tüketicileri için dağıtık kilit sağlamaz.

Değişiklikleri yayımlayan ana görev scripti önce statik olarak incelemeli; ana kurulum kullanılacaksa R5 ve qualifier tamamen bittikten sonra uygun diğer gerçek kitap yüklemesiyle yürütmelidir. Ayrı gerçek kurulum seçilirse doğru Compose kökü, aday frontend'in API upstream'i ve paylaşılan model kapasitesi ayrıca doğrulanmalıdır. Çalıştırmadan önce doğrulanan frontend yayın kimliği ayrıca kanıta bağlanmalıdır.
# Gerçek kabul sonucu — 18 Eylül 2026

CPU `NanobaseAI` üzerinde aday web `nanobase-editor-web:analysis-navigation-r4-20260918` (imaj SHA256 `7f468558ca3f753d57d89bc5db70d293f6b9d7e14b253690472b3a304dcce810`) gerçek API18810 ve bağımsız PostgreSQL ile geçti. UI127.0.0.1:18832 yalnız yerelden erişilen geçici gateway idi; doğrulama sonunda kapatıldı. Ana8810/R5 işine veya kaynaklarına dokunulmadı.

Gerçek kitap **Dünyanın En Korkak Hayvanı**, özgün PDF SHA256 `12cc83a4ccffe9394fa2695c76e460cf87e2ffe32e6ae69d6699fcaee43ceea2`. Gerçek ilk iş `12031b87-d930-4ee8-9677-ac6b3020ceec`, sonra oluşturulan iş `8a734608-89b5-4bce-8938-f5ed4bbfe1b8`; ikisi sırayla API üzerinden iptal edildi, CANCELLED durumu bağımsız PG ile eşleşti. Yeni iş varken ilk analizi açma, sayfa yenilemesinden sonra aynı idempotency anahtarıyla ilk işi bulma ve ek iş oluşturmama 320/390/768/1440 genişliklerinde PASS; yatay taşma yok. Kitap kaynağı ve inceleme kararı değişmedi.

Kanıt: `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation/evidence/upload-analysis-navigation-5aa9f5c7-617e-4c84-969e-cf4d26b431b7/verification.json`; dört ekran görüntüsü aynı dizinde. Betik SHA256 `1a82561f9ff295a1d826fd7dbd9ab75ef2034044ad181b5ed09cb9d644e6bcef`.

Bu, **aday frontend + mevcut ayrı gerçek kurulumun akış kabulüdür**. Ana ortama yayın henüz yapılmadı; son birleşik backend/web sürümünün kabulü ayrıca yürütülecek. Kontrollü iptal edilen işler kitabın anlamsal analiz kabulü değildir. Ağ hatası ve 50'den fazla yükleme sayfalaması bu koşuda tetiklenmedi.

## Son web yayınıyla gerçek kabul — 18 Eylül 2026

Son web `source-preview-v15-r2-20260918`, imaj `sha256:37c90054ed5b94fbf5189e44d324ba2801436a5c655871dabf4ebe150d135f90`, ayrı gerçek API `http://127.0.0.1:18810`, UI `http://127.0.0.1:18832` ve PostgreSQL ile yeniden doğrulandı. Bu kimlik V15 yayın kaydına aittir; kabul raporu salt okunur olarak tekrar incelendi. Ana backend `source-analysis-v15-r5-20260918` olarak yayımlanmıştır; bu navigasyon koşusu ayrı kurulumda yürütülmüştür.

64 sayfalık farklı gerçek PDF hash'i `fbbead4dca9a3a1b7b6e515f3df791460895cb91bdbb4f1fec74fa67ce212c73`; yükleme `311ff495-7c74-49e4-bd19-c3595128025e`, içerik sürümü `56d7d123-cfef-4bc4-8334-f9acf5103883`. Korunan ana kitap içerik sürümü `3970f5b9-769a-4fe9-8032-379834fa6831`.

- İlk iş `aecc2aea-ff5f-4448-83f2-4af1f9708d3f`, nesil `f18b28a6-26a7-43d5-bbbc-2178633b7e64`.
- Sonraki iş `18910202-c800-4071-a661-04faf8ec9cce`, nesil `872abbfa-6777-45e8-a614-a58648c1748b`.
- İki iş sırayla gerçek API üzerinden iptal edildi; her ikisi PostgreSQL ile eşleşen CANCELLED durumunda. Kayıtlar silinmedi.
- 320, 390, 768, 1440 px senaryolarının tamamında ilk kesin iş seçildi, sayfa yenileme idempotency ile aynı işi döndürdü, toplam iş sayısı iki kaldı ve yatay taşma görülmedi.
- Rapor `api_pg_equal=true`, `source_or_review_writes=0`, `semantic_acceptance=false` kaydetti.

Kanıt: `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation/evidence/upload-analysis-navigation-718c19dd-07bd-4c81-80f9-a6531f822db7/verification.json`. Dört gerçek ekran görüntüsü aynı dizindedir. Betik SHA256 `1a82561f9ff295a1d826fd7dbd9ab75ef2034044ad181b5ed09cb9d644e6bcef`.

Kabul **son webin yükleme→doğru analiz kaydı navigasyonu** ile sınırlıdır. V15 tam kaynak nesli henüz başlamadı; kaynak preview sorusu bu kayıt sırasında çalışıyordu. Yeni soru/indeks/cevap kabulü, ağ hatasından toparlanma, 50'den fazla yükleme sayfalaması ve tam kitap anlamsal doğruluğu bu koşuyla kapanmaz. Kaynak preview yalnız kısmi kaynak destekli editör taslağıdır, yayın veya tam kitap kabulü değildir. [V15 sürüm ve açık kabul](2026-09-18-source-analysis-v15.md).
