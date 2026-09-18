# P5 web adayının V16 yayın hazırlığı

Ana R7 web10kaynaklıdır; SourceImpact eklenen P5 adayının exact kaynak kümesi11dosyadır. Sabit10sayısı kabul kuralı değildir. Aday `nanobase-editor-web:impact-candidate-20260918`, image manifest SHA `24b8476a1d5b5db80d1dd5b1209c364d1cb62fb4793e81784383a05689da0821`. CPU loopback18837 imaj manifesti ile güncel checkout11/11aynı, fark0. Exact kaynak/çıktı hash kanıtı `/data/nanobaseai/editor/evidence/p5-web-release-identity.json`. Bu statik kimlik eşliğidir; ana V16 yayını yapılmadı.

## Soru ve etki arayüzünün birlikte çalışma sözleşmesi

Aynı main/token/gen kapsamında SourceQuestionForm soru sekmesinde, SourceImpact kaynak sekmesinde çalışır. Soru capability GET'i `PARTIAL_SOURCE_SUPPORTED_DRAFT` ister; gerçek POST/questions `mode=editor_preview` ve aynı soru için stabil idempotency anahtarı taşır. Callback sonrası gerçek question-jobs listesi yalnız aynı nesil/token görünüyorsa uygulanır. Etki paneli kullanıcı açana kadar GET yapmaz, hiçbir yazma endpointine gitmez; nesil/hedef değişiminde kapanır ve isteği iptal eder. Snapshot değişiminde sayfaları birleştirmez. İkisi de yayımlanmış/anlamsal kabul üretmez.

P5 aday gerçek UI/bağımsız API/PG kabulü134kayıt,3gerçek sayfa ve4genişlikte PASS; kanıt `source-impact-ui-256a9421-b9f9-4f55-b0b0-3061e03952b8`. Soru akışının gerçek R7 kabulü önceki ana webde yapıldı; soru+etki UI'nın nihai V16 backend/web üzerinde birlikte kabulü henüz DOĞRULANAMADI. Nihai sürümde exact release doğrulaması, gerçek soru UI/PG/Qdrant ve snapshot bağlı impact API/PG/UI kontrolü gerekir. Aday kanıtı yeni backend'e otomatik taşınmaz.

## Paketleme açığı ve genel düzeltme

`build-web.py` kilitli bağımlılıklardan derler, bütün kaynak/çıktı hashlerini imaja koyar; `verify-release.py` canlı gateway manifesti ve dosyalarını checkout ile exact karşılaştırır. Bunlar dosya sayısını sabitlemez. `install.sh` önceden içeri alınmış imajları `--no-build --pull never` ile başlatır. `continue-source-release.py` yalnız backend geçişi yapar, gateway imajını değiştirmez; nihai web için gateway ayrıca doğru `EDITOR_WEB_IMAGE` ile seçilmelidir.

`bundle.py` daha önce compose/.env ile seçilen gateway imajını frontend kaynaklarıyla karşılaştırmadan paketliyordu; eski web imajı yeni kaynak paketiyle taşınabilirdi. Genel düzeltme seçilmiş gerçek gateway imajının manifestini pakete kopyalanan frontend kaynaklarının exact kümesi/hashleriyle karşılaştırır; manifestteki her gerçek çıktı hashini de denetler. İmaj içeriği yalnız ağsız, salt okunur `cat` entrypointiyle okunur; servis/model/veri işlenmez, imaj indirilmez. Uyuşmazlıkta paketleme durur.

Yeni paketleme kapısı henüz finalV16paket üretiminde çalıştırılmadı: **DOĞRULANAMADI**. Ana R7 script/paket/imajı değiştirilmedi; root final sürüm sabitlendiğinde uzak gerçek paketleme/restore ile doğrulayacak.
