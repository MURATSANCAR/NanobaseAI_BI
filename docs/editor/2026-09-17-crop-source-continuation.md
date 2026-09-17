# Kırpılmış ikinci okuyucu ve sıralı gerçek kabul

## V9 adayının kapsamı

Tam sayfa Tesseract farklı okuduğunda yalnız aynı kutunun iki stabil PSM 7/13 yeniden okuması, temiz kullanılabilir PDF metni ve en az 0,9 skorlu bölgesel Paddle aynı kelime tokenlerini veriyorsa bölgesel kaynak seçilebilir. İki PSM iki bağımsız motor sayılmaz. Ham ikinci okuma ve bütün hashler korunur; `FULL_PAGE_TESSERACT_SUPERSEDED` görünür gerekçedir. Bozuk Unicode, farklı kullanılabilir PDF veya stabil kırpım çelişkisi veto olmaya devam eder. Kitap/sayfa/karakter sabiti yoktur.

Gerçek ana API/PG 1.149 kaydında bağımsız politika ölçümü: önceki 39/39 kazanım korundu, 14 ek aday, mevcut 821 anlaşmada gerileme sıfır. Aday toplam 874/275; üretim sayısı değildir. Yeni 14 içinde 13/29/38. sayfalar yok. Ayrıntı ve immutable artifact doğrulaması [OCR denetiminde](2026-09-17-ocr-residual-audit.md).

## Mevcut koşuyu kesmeden sonraki adım

V8 `7e7db466-3576-4c23-85b2-73483ab4508e` çalışırken V9 imajı hazırlandı: `nanobase-editor:crop-source-v9-20260917`, ID `sha256:7a491d62ec48ed331ac544fdbccf29791b28e18bf77a94f4264b588c7980afaf`. Ayrı kurulumun backend checkout'u V9 adayıdır; çalışan V8 konteynerleri değişmez imajdadır. Bu yüzden V8 kabulünü host checkout'la yeniden karşılaştırmayın; önceki sabit V8 hash ve canlı konteyner kimliğini kullanın.

`continue-source-release.py` gerçek sunucuda başlatıldı; ilk gözlem `WAITING_FOR_CURRENT_JOB`. V8 başarıyla tamamlanmadan sürüm değiştirmez. FAILED/CANCELLED, beklenmeyen servis hash'i, başka aktif iş veya imaj pin uyuşmazlığında hata kaydedip durur. V8 tamamlanınca yalnız ayrı API/worker'ı V9 imajına geçirir; kaynak/model/gateway'e dokunmaz. Hash ve hazır olma doğrulamasından sonra aynı içerik ve V8 ebeveyniyle yeni nesil başlatır. Öncelik girdisi `[4,8,17,19,22,36,41]`; kalan sayfalar da işlenir. Aynı idempotency anahtarı/kalıcı checkpoint ile yinelenen analiz önlenir.

Sonraki nesil sonunda gerçek kaynak, bölgesel seçim, metin atfı, anlatı/kapsam API/PG denetimleri ve dört genişlikte tarayıcı kontrolü çalışır. Bunlar anlamsal kabul veya ana yayına geçiş izni yerine geçmez. Ana V5 otomatik değiştirilmez. Bu akış yalnız önceden hazırlanmış bu sürüm geçişini yapar; sınırsız otomatik kod düzeltme sistemi değildir.

Sunucu kökü: `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation`. Canlı ilerleme `evidence/crop-source-continuation.log`, kalıcı aşama `runtime/release-continuation/crop-source-v9-20260917.json`, sonraki nesil dosyası `evidence/crop-source-run.json`. Son dosya mevcut V8 tamamlanıp yeni analiz oluşturulana kadar bulunmayabilir. Geçiş ve final kabul henüz çalışmadığı için tamamlanmış sayılmaz.
