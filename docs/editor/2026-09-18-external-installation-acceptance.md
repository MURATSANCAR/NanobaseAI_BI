# External model uygulama paketi: ayrı kurulum kabulü

18 Eylül 2026. Test ortamı bağlı gerçek Linux Docker sunucusudur; yerel/sentetik kitap testi değildir. Ana Editör koşusu durdurulmadı, ana veritabanı ve env değiştirilmedi. Yeni GPU modeli veya kopya ana LLM başlatılmadı.

## Paket ve yeni kurulum

Paket: `/data/nanobaseai/editor-qualifications/source-analysis-v12-r1-external-20260918`. Uygulama sürümü `source-analysis-v12-r1-20260918`; paket external_models modunda GPU Qwen/OCR hizmetlerini dış bağımlılık olarak tanımlar. Uygulama imajları, CPU embedding/reranker ağırlıkları ve kaynak dosyaları hash kontrollüdür. Import ana ajan tarafından tamamlandı; bu aşama GPU ağırlık paketleme kabulü değildir.

Yeni hedef: `/data/nanobaseai/editor-qualifications/external-v12-fresh-installation`, proje `editor-external-v12-acceptance`. Kendi secrets, boş subnetler `10.203.64.0/24` ve `10.203.65.0/24`, web `18820`, metrik `19099`. İstenen `19098` dolu olduğundan boş alternatif seçildi. Geçici dar port erişim kuralları koordinasyonla eklendi; müşteri ortamında kendi özel model ağı gerekir.

- `scripts/preflight.py`: PASS; host Linux x86_64, CPU96, Docker29.1.3, çakışan subnet/eksik offline dosya yok.
- `scripts/install.sh`: PASS; imaj indirmeden/derlemeden kurulum, servisler healthy.
- Gerçek API `/v1/system` ve bağımsız PostgreSQL schema/deployments eşliği: PASS.
- 28 erişim ayrıcalığı kontrolü ve yetkisiz HTTP401: PASS.
- Yeni API konteynerinden Qwen `/health` ve OCR pasif `/gateway/status`: HTTP200. Bu iki istek yeni kitap çıkarımı veya idle/wake döngüsü kabulü değildir.
- Hedef servisler kabul sonrası durduruldu; volume/kanıt korundu. Kanıtlar hedef `evidence/preflight.log`, `install.log`, `stop.log`.

## Gerçek eski yedeğin ayrı hedefe dönüşü

Yeni restore hedefi `/data/nanobaseai/editor-qualifications/external-v12-restore-installation`, proje `editor-external-v12-restore`, subnetler `10.203.66.0/24` ve `10.203.67.0/24`, portlar `18821/19100`. İlk deneme `18820` meşgul kontrolünde veri yazmadan durdu; boş portlarla ikinci deneme başlatıldı.

Kaynak yedek `/data/nanobaseai/editor-qualifications/b652f63c/backup`, 17 Eylül `source-review-v2-r2-20260917` sürümünün gerçek kitap snapshot'ıdır. Kaynak nesil `b652f63c-6ec4-4f9a-aff4-00b32d220b1b`. Bu restore yeni V12 kitabının/semantik sonuçlarının kabulü sayılamaz.

Restore ikinci denemede PASS. Yedek DB kayıtları ve kaynak/artifact baytları başlamadan önce snapshot referansıyla birebir karşılaştırıldı. Restore sonrası yeni migration ve gerçek API/PG altyapı kontrolleri, 28 ACL kontrolü, yetkisiz HTTP401 ve özgün PDF/tüm sayfa render hashleri geçti.

Çalışan yayının backend 43 dosyası kaynakla eşleşti: `d6c3a68a40911519ddfe16677c03abe347c4bc1e3adfeaa862d55f276d5884c9`. Web kaynak/çıktı hashleri de eşleşti (9 kaynak dosyası). `verify-source-pipeline.py` gerçek restore API ve bağımsız PostgreSQL üzerinde 48 sayfanın kaynak/bölge/gözlem/iddia/check kayıtlarını karşılaştırdı: 48 PASS; elle inceleme kararı, kaynak düzeltmesi, eski serbest görsel açıklaması 0. Bu neslin anlamsal kabulü false olarak korundu.

Kanıtlar restore hedefinde `evidence/restore.log` (ilk port hatası), `restore-r2.log`, `release.log`, `source-api-pg.log`. Gerçek eski OCR29/38 kayıtlarıyla 320/390/768/1440 px tarayıcı kontrolü PASS: altı sekme, kaynak bbox/API metin eşliği, OCR aday görünümü, yatay taşma olmaması ve çıkışta erişim anahtarının temizlenmesi doğrulandı. Yeni V12 semantic/identity dolu kayıtları bu eski yedekte bulunmadığından bu koşu onları doğrulamaz. Ekran görüntüleri ve `verification.json`, `evidence/mobile-restored/` altında; terminal sonucu `evidence/mobile.log`. Kabul sonrası iki hedefin de servisleri durduruldu; Docker sorgusunda her iki projede çalışan konteyner sayısı 0, volume/kanıtlar korundu. Arama indeksi rebuild ve arama/cevap kalitesi bu sınırlı restore-okuma kabulüne dahil değildir. P6 tüm müşteri topolojileri ve GPU ağırlık dağıtımı açısından açık kalır.
