# Editor üretim kabulü — 21 Eylül 2026

**Karar: ÜRETİME HAZIR DEĞİL.** Teknik çalışabilirlik ile kitap doğruluğu ayrı kabul edilir. Kullanıcı onaysız hazırlık/yayın/doğrulama yetkisi verdi; bu belge tamamlanmamış maddeleri onaylanmış saymaz.

## Güncel durum ve sürümler

- **Son tam analiz FAILED:** `0439924a`, nesil `9e01aacf-7ab6-4e11-9b7a-b82b45e8a48a`, iş `2cc4bd08-67cf-424a-af67-4f686ea6b8a3`, adım 13/15. Hızlı tarama 32/32, derin tarama 29/29 tamamlandı. 37 görsel figür belirsiz. Tarama tamamlanması kimlik/kitap kabulü değildir.
- **GPU düzeltme sürümü `f1cc4614` kurulu:** `017_page_role_reviews.sql` sayfa rolü incelemesine gerçek hedef bağlantısı ekler; `validated-outputs-v8` az kanıtta az cümle ve son denemede bire bir doğrulanmış iddia sınırı uygular. Migration gerçek GPU PostgreSQL üzerinde uygulandı; `editor-repair-f1cc4614` ile 1–4. sayfa çıkarımı ve ardından yeniden üretim başlatıldı, kabul sonucu henüz yok; ayrıntı [kurtarma kaydı](RECOVERY-2026-09-21.md).
- Genel analiz ve yeniden üretim işçileri kapalı. Kontrollü kabul için servislerin açılması genel taramaların açılması anlamına gelmez. Bakım anahtarının önceki ölçümleri güncel durum yerine kullanılamaz.
- CPU portalın konuşma bağlamı `474cb2d9`; bakım hatasını cevap saymayı engelleyen düzeltme `40b19439`. `finish_reason=stop` dışındaki Hermes sonuçları kitap cevabı olarak yayımlanmaz.
- GPU yönetim tüneli **kurulu ve doğrulandı**: CPU loopback `18891` → GPU SSH. Normal VPN yolu kopuk olsa da bu yönetim yolu çalışıyor; mevcut anahtar ve host doğrulaması korunur.

## Gerçek kanıtlar ve sınırları

| Kontrol | Sonuç | Kabul sınırı |
|---|---|---|
| Orijinal PDF geometri/künye kontrolü | [45/45 geçti](evidence/2026-09-21-pdf-layout.json) | Bütün kaynak/rol/kimlik doğruluğu değildir |
| Yedi sohbet aracı, gerçek MCP/API–DB karşılaştırması | [329/329 geçti](evidence/2026-09-21-resumed-chat-tools.json) | Araç/veri sözleşmesi; bütün kitap semantiği değildir |
| Gerçek Hermes sohbeti | [10 cevap tamamlandı](evidence/2026-09-21-resumed-chat-ten.jsonl) | Hepsi içerik açısından kabul edilmiş değil; özet kapsamı eksik |
| Portal bakım hatası | [Hata durumu, cevap null](evidence/2026-09-21-portal-maintenance-rejection.json) | Hata ayırımı; kitap doğruluğu değildir |
| Worker SIGKILL → kendiliğinden devam | [9 OCR activity attempt 2](evidence/2026-09-21-new-generation-crash.json), yaklaşık 59 sn | Aynı iş/nesilde otomatik devam geçti; tam koşu sonradan FAILED |
| Önceki neslin çıktı kurtarması | Rev3009, 5 READY; 371 API/DB/Qdrant kontrolü | Tarihsel, farklı nesil/sürüm; yeni nesle aktarılmaz |
| Portal bağlamsal API | [8/8 geçti](evidence/2026-09-21-portal-context-api.json) | İki gerçek soru bağlamı; tüm sohbet kabulü değildir |
| Portal mobil yaşam döngüsü | [320/390/768/1440 genişlikleri](evidence/2026-09-21-portal-context-browser.json), [iki soru](evidence/2026-09-21-portal-context-lifecycle.json) | Ölçülen portal sürümü ve akışla sınırlı |

Önceki altı araçlı 317 kontrol ve ilk on sohbet kaydı tarihsel aşamalardır. İlk sohbetlerde metinden görsel yokluğu çıkarma, eski FAILED işi güncel çıktı yokluğu sanma ve yanlış kitap adı üretme görüldü. Sonraki araç/kapsam düzeltmeleri ve yeniden koşu bu sorunları ele aldı. Tam özet aracı tek başına sonu tamamlamadı: önceki nesilde 26–32. sayfalardaki 14 olay NEEDS_REVIEW olduğu için doğrulanmış özete girmiyordu. Özet taşıma bütünlüğü ile olay örgüsü kapsamı ayrı bildiriliyor; filtre gevşetilmedi.

## Açık üretim engelleri

1. Yeni neslin 1–4. sayfa çıkarım parçası, hedefsiz sayfa rolü review kaydının `review_item_check` ihlali nedeniyle geri alındı. `017` ile gerçek sayfa rolü FK hedefi kuruldu; başarısız parçanın yeniden çıkarımı ve bağımsız DB/API doğrulaması bekleniyor.
2. Yeni özet, tema etiketlerinden kanıtsız neden–sonuç üretti; Critic üç taslağı reddetti, rapor yayımlanmadı. V8 düzeltmesinin gerçek üretim/kaynak karşılaştırması bekleniyor.
3. Beş kısıt kodda giderildi, ayrı gerçek kitap kabulü bekliyor: aynı sayfadaki bütün figürlerin sürekliliğe katılması, kaynaklı tekil duygu bağı, görsel doğrulamasız elemenin kaldırılması, iki figürden başlayan tüm partilerin açık kapsamı, NON_STORY/topluluk bilgisinin korunması. [Denetim ve kabul matrisi](CONSTRAINT-AUDIT.md).
4. 37 görsel figür belirsiz; kritik kişi/figür doğruluğu bağımsız kanıtla ölçülmeli. Önceki neslin 23 belirsiz figürü bu neslin sayısı değildir.
5. Kaynak kapsamı, sayfa rolleri, ham PDF–OCR uyuşmazlıkları ve görsel-only sayfalar için tam analitik kabul yok. Eski nesillerin kaynak baytları korunur.
6. Son düzeltme sürümünde aynı revizyon/snapshot'taki beş çıktı, Qdrant ve gerçek portal sohbeti yeniden doğrulanmalı. Başarısız iş geçmişi başarılıya çevrilmemeli.

## Teknolojik değerlendirme

Mevcut depo yapılandırmasında yönetici model Qwen3.8-27B-FP8; hızlı görsel Qwen3-VL-8B-Instruct; derin görsel Qwen3-VL-32B-Thinking; embedding/reranker ayrı 8B modeller. GPU0 BI, GPU1 Editor. Derin görsel model 0,90 bellek payıyla diğer Editor modelleriyle aynı anda yerleşemez; gateway değişimi gecikme kaynağıdır. FP8 derin görsel aday tanımı var, ancak gerçek sayfa/kimlik kalitesi kabul edilmeden varsayılan yapılmadı.

Gözlenen temel hatalar model yükseltmesiyle açıklanamaz: eksik araç sayfalaması, eski/güncel durum karışması, kaybolan sohbet geçmişi ve kaynak geometri sırası. Bunlar önce düzeltilir. Alternatif modelin daha iyi olduğu veya güncel sürümlerin araştırıldığı iddia edilmiyor; bu turda model değişikliği yapılmadı.

## Yayın ve sonraki kabul

GitHub origin yayını son denemede HTTPS kimliği bulunamadığından başarısız. Yerel main ve kurulu release hashleri ayrı kaydedilir; origin yayımlandı denmez. Genel taramalar kapalı kalır.

1. `f1cc4614` ile yalnız başarısız çıkarım ve çıktı aşamalarını gerçek kitap/veritabanında onar; kaynakları yeniden taramak veya ikinci ağır koşu açmak yerine mevcut kanıtı koru.
2. Sayfa rolü review hedefi, korunmuş çıkarım kayıtları, özet cümleleri ve kanıt referanslarını bağımsız kontrol et. Kanıtsız neden–sonuç veya zayıf kanıttan uzatılmış anlatı kabul edilmez.
3. Beş kısıtın her birini gerçek figür/kişi/kaynak kayıtlarıyla ayrı sonuçlandır; görülmeyen senaryoya PASS verme.
4. Beş güncel çıktı + Qdrant + gerçek portal sohbetini son kurulu hash üzerinde doğrula; düzeltme sonrası eski revizyonun reddini kontrol et.
5. Kaynak/kimlik/analitik kabul ve main/origin/sunucu eşliği sağlanmadan üretim kararı verme. Yerel veya sentetik ürün testi kabul yerine kullanılamaz.
