# Tarih bağı regresyonları: canlı doğrulama — 9 Eylül 2026

Üretim servisi yeniden başlatılmadı ve trafik değiştirilmedi. Aday kod `/tmp/codex-temporal-review-20260909-v2` altında, gerçek katalog, gerçek LLM ve mevcut salt-okunur veritabanı bağlantısıyla ayrı süreçte çalıştırıldı.

Önce sütunu, kullanıcının `/tmp/canli_olcum.json` dosyasında ölçtüğü regresyonlu adayı gösterir; dünkü üretim sürümü değildir. Sonra sütunu bu değişikliğin canlı koşusudur. Bu 14 soru geliştirme/regresyon kümesidir; bağımsız genel başarı ölçümü değildir.

## Sonuç

- İlk 10 soruda: **5 cevap → 8 cevap**.
- Tam 14 soruda: **8 cevap → 11 cevap**, 2 netleştirme ve 1 veri yok.
- Önceden cevaplanan sekiz sorunun cevap türü korundu.

| Soru | Önce | Sonra | Satır |
|---|---|---|---|
| bu yıl en çok satan 10 kitap | INCOMPLETE_ANSWER | TEXT_TO_SQL | 10 |
| hangi müşteriden en çok iade geldi | INCOMPLETE_ANSWER | TEXT_TO_SQL | 50 |
| e-ticarette bu yıl ne kadar sattık | TEXT_TO_SQL | TEXT_TO_SQL | 1 |
| en çok iskonto verdiğimiz müşteriler kimler | CLARIFICATION | CLARIFICATION | — |
| bu yıl kaç fatura kestik | TEXT_TO_SQL | TEXT_TO_SQL | 1 |
| aylık satışlarımız nasıl gidiyor | TEXT_TO_SQL | TEXT_TO_SQL | 8 |
| en pahalı 10 ürünümüz | CLARIFICATION | CLARIFICATION | — |
| geçen yıla göre satışlarımız ne durumda | TEXT_TO_SQL | TEXT_TO_SQL | 1 |
| hangi kanaldan en çok kazanıyoruz | INCOMPLETE_ANSWER | TEXT_TO_SQL | 16 |
| kitapçılara bu yıl ne kadar sattık | TEXT_TO_SQL | TEXT_TO_SQL | 1 |
| 2026 toplam net ciro nedir? | TEXT_TO_SQL | TEXT_TO_SQL | 1 |
| 2026 kanal bazında net ciro | TEXT_TO_SQL | TEXT_TO_SQL | 17 |
| 2026 ürün bazında net ciro, en yüksek 3 | TEXT_TO_SQL | TEXT_TO_SQL | 3 |
| geçen aya göre net ciro | DATA_UNAVAILABLE | DATA_UNAVAILABLE | — |

## Değişiklikler

1. Tarih bağı ve veri kapsamı, yalnız çözümlenmiş ölçünün varlığına bağlanır. Ölçü yoksa kanal/müşteri kartı gibi bir kırılım varlığının oluşturulma tarihi zorunlu kılınmaz.
2. `CAPIBLOCK_*` ve teknik oluşturma/güncelleme alanları otomatik iş tarihi seçiminden çıkarıldı. Profiler da veri aralığını bu alanlardan ölçmez.
3. Logo için açık belge–satır tarih eşdeğerliği `configs/semantic/knowledge/logo/equivalences.yml` içinde tanımlandı. Genel bir FK, iki tarihi eşdeğer yapmaz. Başlık sorguda varsa bildirilen FK gerçekten JOIN koşulunda aranır; başlık yoksa satırın çıktı ölçüsünü taşıması gerekir.
4. Canlı koşu, iade sorusunda ikinci bir bağlama kusurunu ortaya çıkardı: katalog iade filtresini STLINE üzerinde tutarken LLM doğru INVOICE iade raporunu üretiyordu. Mevcut Logo iade raporu ve canlı incelemeyle desteklenen eşdeğerlik yalnız `TRCODE IN (2,3)` için tanımlandı. Başka kodlar, müşteri/iş akışı kolonları veya kullanılmayan CTE kabul edilmez. Kavramların sertifikasyon durumu değiştirilmedi.

## Ürün kararı ve doğrulama sınırı

Geçen aya göre sorusunda güncel ayın verisi gözlenen aralığın dışında olduğundan `DATA_UNAVAILABLE` korunur. Takvim dönemi sessizce son yüklü aya kaydırılmaz ve yüklenmemiş ay sıfır olarak sunulmaz.

Tablo cevap türü ve satır sayısını ölçer; bütün sayısal sonuçların iş doğruluğunun bağımsız ispatı değildir. Çıktı kayıtları bu rapora kopyalanmadı. SQL ve bağlama izleri `artifacts/temporal-binding-live-20260909.json` dosyasında bulunur.

## Testler

- Semantik katman: **371 geçti** (356 tabanına 15 yeni regresyon testi).
- Geniş backend paketi (API, katalog, senaryo, gateway, AWEL, forecasting): **1600 geçti, 2 atlandı**.
- `git diff --check`: temiz.

Değişiklikler üretime dağıtılmadı ve commit edilmedi.
