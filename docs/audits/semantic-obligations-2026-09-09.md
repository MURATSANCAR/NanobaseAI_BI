# Semantik koşul takibi ve karşılaştırma doğrulaması — 9 Eylül 2026

## Uygulanan değişiklikler

- `CompilerRouter` içindeki deterministik, LLM ve alternatif derleyiciler aynı koşul denetiminden geçer. Köprü, onarımdan sonra **son SQL** üzerinde denetimi yeniden yapar. Karşılanmayan yükümlülük `INCOMPLETE_ANSWER` üretir; sonuç/snapshot oluşturulmaz.
- Karşılaştırma metin aramasıyla doğrulanmaz. SQL AST üzerinde ayrı çıktı sütunları, aynı ölçü, aynı tarih sütunu, başlangıç ve bitiş sınırları denetlenir. Kullanılmayan CTE, açıklama, yanlış kolon, değiştirilmiş ölçü veya dış WHERE ile düşürülen dönem kanıt sayılmaz.
- Açıkça belirtilmiş iki dönem de karşılaştırma sözleşmesi oluşturur. Güncel dönem takvimden hesaplanır; 2019 referansı 2020'yi güncel dönem yapmaz. Ay/yıl geçişleri ve artık yıl test edilir. Kanal kırılımındaki “göre” karşılaştırma sanılmaz.
- Tek dönem ve sertifikalı/çıkarılmış değer filtreleri de sonuç kapsamında denetlenir. Şehir filtresi genişletilemez veya kullanılmayan CTE'ye taşınamaz. Koşulsuz toplam, yanında filtreli bir toplam bulunmasıyla onaylanmaz.
- `AVG/MIN/MAX/SUM` koşullu hesaplarında dönem dışı satırlar yapay sıfıra çevrilmez. Boş toplam NULL kalır. Koşullu `COUNT(DISTINCT ...)` tekilleştirmeyi korur.
- Gözlenen kayıt tarihleri yükleme bütünlüğü sayılmaz. Tamamen gözlenen aralığın dışındaki soru `DATA_UNAVAILABLE` alır. Kısmi kapsam açıklaması dolu sonuçlarda da korunur. Kapsam bilgisi yanıt, snapshot ve Excel açıklamasına taşınır.
- Karşılaştırma takvim dönemleriyle yapılır; eşit yükleme kapsamı doğrulanmadığı açıkça belirtilir. Eş süreli performans değişimi iddia edilmez.
- Onaylı tanımı olmayan “pahalı/ucuz” ifadelerinde fiyat, para birimi ve eşik/karşılaştırma grubu sorulur. `human_verified` gevşetilmedi.
- Gateway auth testleri ortam değişkenlerini fixture içinde izole eder; geçersiz `cache_clear` yerine `reset_settings` kullanır. İki AWEL testi kendi event loop'unu `asyncio.run` ile yönetir.

## Doğrulama

Python 3.11, `PYTHONPATH=backend`, `SEMANTIC_TABLE_SELECTOR=off`; semantik ve API/gateway gereksinimleriyle izole `/tmp/nonobase-fix-venv` ortamı kullanıldı.

- API, katalog, senaryo, gateway, AWEL, forecasting: **1600 geçti, 2 atlandı**.
- Frontend Vitest: **24/24**.
- Ana uygulama ve cockpit TypeScript/Vite derlemeleri: başarılı. Vite mevcut büyük parça boyutu uyarısını veriyor.
- Semantik katman: **356/356**. Başlangıçta 323 test vardı; 33 yeni regresyon/adversarial örnek eklendi.
- HTTP TestClient ile eksik veri yanıtının yürütme yapmadığı; kısmi kapsamın snapshot'a taşındığı; onarımda düşen filtrenin son çalıştırmadan önce engellendiği doğrulandı.

## Sınırlar

Bu denetim keyfi SQL eşdeğerliğinin ispatı değildir. Desteklenmeyen CTE/alt sorgu biçimleri veya kanıtlanamayan olumsuzluk kapsamı güvenli biçimde reddedilir; bu durum yanlış sonucu başarılı sunmaktan kaçınır, fakat bazı doğru LLM sorgularını da durdurabilir. `ABSENCE` için genel bir anti-join ispatlayıcısı bu değişiklikte yoktur.

Kayıt min/max tarihleri ETL watermark'ı değildir. Gerçek yükleme bütünlüğü, onaylı iş kavramları ve insan tarafından incelenmiş tarihçe çiftleri harici kanıt gerektirir. Bu veriler uydurulmadı. Yapılandırılmış çok turlu konuşma ve bütün proje servislerini tek bir semantik IR'a taşıma bu değişikliğin kapsamına alınmadı.

Doğrulama yerel fixture ve uygulama testleriyle yapıldı; canlı müşteri veritabanına dağıtım veya canlı doğrulama yapılmadı. Değişiklikler commit edilmedi.
