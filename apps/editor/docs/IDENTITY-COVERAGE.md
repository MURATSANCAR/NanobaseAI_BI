# Kaynak ve karakter kimliği kabulü — 21 Eylül 2026

**Üretime hazır değil.** Bu belgedeki 37/37, 36/59 kimlik ve rev3009 sonuçları önceki `1600e738-621b-434f-8d9c-0c0645b42fb2` nesline aittir. Yeni `0439924a` nesli `9e01aacf-7ab6-4e11-9b7a-b82b45e8a48a`, 32/32 hızlı ve 29/29 derin taramayı tamamladı; 37 görsel figür belirsiz kaldı ve iş 13/15'te FAILED oldu. `f1cc4614` hedefli onarımı henüz kabul edilmedi. [Güncel kurtarma kaydı](RECOVERY-2026-09-21.md).

Önceki kabulün kapanışında bakım açık, genel worker/rebuild, Hermes/MCP/gateway ve Editor modelleri kapalıydı; GPU 1 0 MiB ölçüldü. Bu tarihsel ölçüm güncel çalışma durumu değildir. Genel taramalar kapalı kalır; BI GPU 0'a dokunulmadı.

## Düzeltilenler

- Metin kimliğinde anmalar tam ve tekil bölünür. Aynı anmayı baba/yavru gruplarına yazan öneri reddedilir; ad çoğunluğu üzerinden yanlış kimlik birleştirme kaldırıldı. İkinci kaynak denetçisi tür/kimlik/açıklamayı kontrol eder. Birey, topluluk ve kavram ayrılır; topluluklar kesin kişi sayılmaz.
- Başarıyla tamamlanan boş OCR kaydı saklanır. Boş sonuç ile yapılmamış OCR ayrıdır. Kaynak baytları korunur; boş sayfa otomatik analitik kabul edilmez.
- Kimlik kapsamı API'si fiziksel sayfa, gerçek model taraması, ön eleme ve bağlı/çözülmüş anmaları ayrı sayar. Tarama tamamlanması kimlik doğruluğu değildir.
- Gerçek koşuda kitap özeti iki kez uzunluk sınırına takıldı, sonrasında geçersiz claim referanslarıyla reddedildi. `validated-outputs-v6`: en çok 24 cümle, snapshot'a özel kısa model referansları; kalıcı çıktı gerçek claim UUID ve evidence bağlantısını korur. Bilinmeyen referanslar hata olarak reddedilir.

## Önceki nesilde gerçek kabul

Ortam: tt-gpu, gerçek Editor PostgreSQL + kontrol API'si + Qdrant ve orijinal PDF. Yerel/sentetik test çalıştırılmadı.

- Kitap: Dünyanın En Korkak Hayvanı. PDF SHA `12cc83a4ccffe9394fa2695c76e460cf87e2ffe32e6ae69d6699fcaee43ceea2`.
- Nesil `1600e738-621b-434f-8d9c-0c0645b42fb2`; ilk job `8dd7f9a1-f9f7-41d0-b16d-f544e3c92205`. Üretici `d045a96f`; son okuyucu/çıktı imajı `a80be3ec` (`0.14.0-identity-a80be3ec`). Sonraki belge commitleri ürün kodunu değiştirmez.
- İlk kimlik önerisi 27373, yinelenen m28 nedeniyle reddedildi. 27374/27375 ikinci öneri/denetçi geçti. Baba Vombat ve Yavru Vombat ayrı ANIMAL/INDIVIDUAL kimlikler.
- Gerçek PDF + API + bağımsız defter karşılaştırması **37/37** geçti. 4 ve 10. sayfalar bağımsız görsel incelemede yazısız resim; API `COMPLETED_NO_TEXT` döndürüyor.
- 23. sayfanın bağımsız görsel referansı kimlik çözümünden önce kaydedildi. Taramanın ters verdiği iki ad düzeltildi: sarı gözlük/kırmızı giysi → Yavru Vombat; mavi şapka → Kirpicik. Her iki son kimlik bağlantısı doğru.
- Görsel anmalar **36/59 RESOLVED**, **23/59 UNCERTAIN**. Bu iki hedef figürün başarısı kitabın tüm kimliklerinin kabulü değildir.
- İlk tam job özet referans hatasında **FAILED** kaldı. Tarama tekrarlanmadan yeni çıktı koduyla gerçek yeniden üretim **SUCCEEDED**, bilgi revizyonu **3009**, beş çıktı READY. Başarısız job geçmişi değiştirilmedi.
- Son yayında gerçek API/DB/Qdrant çıktı tutarlılığı **371/371** geçti. Bu sayılar kaynak/kimlik semantiğinin tam kabulü değildir. Analitik durum **NEEDS_REVIEW**, `accepted=false`.
- İlk üretim 13:45 UTC'de başladı; bakım 14:55 UTC'de geri açıldı. Bu yaklaşık 70 dakika; model geçişi, denetim, Hermes çakışması ve kod düzeltmesi/yeniden üretimi içerir, temiz performans benchmarkı değildir. İlk aktör geçişi 62 olay × 16 karakter için 992 kısa çağrı yaptı; maliyet ayrıca ele alınmalı.

## Önceki nesil kabulünde kalanlar

1. Kaynak: 32 sayfa kapsamda, 30'u metin okunabilir. 2/3/18/24/26. sayfalarda metin/OCR uyuşmazlığı; 4/10 görsel-only değerlendirmesi ve 32 sayfanın rol onayı açık. Ham kaynaklar korunuyor, editör onayı uydurulmadı.
2. Kimlik: 23 görsel anma belirsiz; tüm karakterlerin bağımsız doğruluğu kabul edilmedi. İki TEXT anmasında doğrulanmış metin kanıtı yok; bunlar metinsel kimlik çözümüne alınmadı.
3. Hermes: gerçek pending sohbet son neslin hazır olmadığını, çalışan işi doğru bildirdi; eski özet sunmadı/yeni iş önermedi. Ancak servis günlüklerinde spillover dosyasına erişemeyen tekrarlı araç çağrıları ve başka bekleyen oturumlar var. Döngünün tek pending isteğe aidiyeti kanıtlanmadı. Servis durduruldu. Hazır çıktı üzerinden tam sohbet ve oturum yaşam döngüsü **DOĞRULANAMADI**; önce araç erişimi/oturum izolasyonu çözülmeli.
4. Tam yeni analiz neslinin baştan sona tek sürümle SUCCEEDED olması henüz yok: bu kabul, başarısız üretim sonrasında gerçek çıktının kurtarılmasını kanıtlar.

Hermes için yukarıdaki durdurulmuş oturum gözlemi tarihseldir. Sonraki yedi araçlı MCP kontrolleri, portal yaşam döngüsü ve sohbet yeniden koşuları [PRODUCTION-READINESS.md](PRODUCTION-READINESS.md) içinde kayıtlıdır; bunlar tam kitap kabulü değildir.

## Kanıt

[Depodaki kabul kaydı](evidence/2026-09-21-identity-coverage.json). Sunucu kanıtları `/data/editor/backups/20260921-identity/`: `before-new-generation.dump`, `identity-final.json`, `visual-reference.json`, `visual-page23-final.json`, `outputs-final.json`, `source-final.json`, `runtime-final.json`, `hermes-pending-final.json`, `hermes-background-loop.log`. Yeniden çalıştırılabilir sunucu kontrol scriptleri `deploy/verify_identity_coverage.py`, `deploy/verify_live_outputs.py`, `deploy/verify_hermes_pending.py`.

Kod yerel main'de. GitHub push bu oturumda HTTPS kimliği olmadığı için başarısız; origin yayını tamamlanmış sayılmıyor.
