# ZEKİ AI BI sohbet kapsamı — 9 Eylül 2026

Veri dışı mesajlar `MODULE_INTRO` yanıtıyla kısa ZEKİ AI tanıtımına yönlendirilir. Yanıtta SQL, kayıt, semantik iz veya doğruluk oylaması kimliği yoktur. Belirsiz iş terimleri ve veri takip soruları engellenmez. Açık selam/test/kimlik ifadeleri model çağrısı yapmaz; katalogda yerleşmeyen sorular niyet sınıflandırıcısına gider. Sınıflandırma hatası veri sorusunu reddetmez.

BI başlığı, kapsamı, giriş metni ve örnekler `chatModules.ts` içindeki BI tanımındadır. Yalnız BI uygulanmıştır; diğer modüllerin ürün davranışı henüz tanımlanmamıştır.

## Doğrulama

- Yerel semantik regresyon: 499 geçti, 2 bağımlılık kullanımdan kaldırma uyarısı.
- Gerçek model: 12/12 sınıflandırma senaryosu geçti.
- Üretim API: 6/6 veri dışı mesaj SQL olmadan tanıtım döndürdü.
- Üretim API tam satış sonucu, bağımsız gerçek DB sorgusuyla kolon/satır/sayısal değer ve kesilme bakımından eşleşti.
- Mevcut karmaşık setten P08802, üretim API tam sonucu ve bağımsız referans karşılaştırmasıyla LIVE_PASS aldı (tek soru; 100 soruluk yeni koşu değildir).
- Gerçek tarayıcıda kimlik sorusu ve `test` tanıtımı görüldü. 320/390/768/1440 pikselde yatay sayfa taşması yok. Giriş 16px; yeni sohbet ve gönderim hedefleri 44px.

Kanıtlar: `outputs/production-readiness-final-20260909/chat-acceptance.json`, `chat-classifier-results.json`, `chat-release-manifest.json`.

## Yayın sınırı

Bu yayın mevcut üretim backendine yalnız sohbet kapsamı yamasını ekler. Depoda aynı anda geliştirilen streaming/presentation değişiklikleri yayın paketine katılmadı; arayüz mevcut `/api/v1/ask` uç noktasını kullanır. Tam kaynak dosyaları ve yayın hashleri manifestte kayıtlıdır. İlk arayüz paketindeki kök varlık yolu hatası `/timas/` taban yoluyla yeniden derlenerek düzeltildi ve gerçek tarayıcıda doğrulandı.

Bu doğrulama tüm proje için yeni bir 100 soru/kapsamlı yük testi veya eksik özel ERP tanımlarının tamamlandığı iddiası değildir.
