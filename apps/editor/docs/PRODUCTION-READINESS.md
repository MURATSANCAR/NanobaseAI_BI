# Editor üretim kabulü — 21 Eylül 2026

**Karar: ÜRETİME HAZIR DEĞİL.** Teknik çalışabilirlik ile kitap doğruluğu ayrı kabul edilir. Kullanıcı onaysız hazırlık/yayın/doğrulama yetkisi verdi; bu belge tamamlanmamış maddeleri onaylanmış saymaz.

## Güncel genel kabul — 50152949

Kullanıcının kitaba özel çözüm yasağı [PRODUCTION-CONTRACT.md](PRODUCTION-CONTRACT.md) ve kök AGENTS.md içindedir. Sunucuda `0.17.1-contract-50152949` kuruldu: tam Critic ID kapsamı, değişmez ilk model güveni, kısmi zorunlu görev hatasında durma ve kaynak adı/betimleyici etiket ayrımı bütün kitaplara uygulanır.

Altı gerçek katalog PDF'si hash ile eşleştirildi (32, 48, 64, 128, 128, 144 sayfa). Gerçek jobs MCP üzerinden özel `editor-corpus-50152949` kuyruğunda tek ağır iş sıralı çalışır, ilk teknik hatada durur. Başlangıç iş kimliği `7dfa0e8f-a054-417f-ba2a-f4f3a1526adc`; canlı durum GPU `/data/editor/storage/corpus-50152949/state.json`. Koşunun başlaması kabul değildir; teknik ve bağımsız semantik sonuçlar henüz açık. Genel taramalar kapalı.

Salt okunur ön denetimde altı kitabın dördünde kaynakta bulunmayan ad/etiketler görüldü: [korpus başlangıç kanıtı](evidence/2026-09-21-corpus-alias-baseline.json). Eski puanları ilk model puanı diye geri doldurma veya eski kimlikleri varsayımla dönüştürme yapılmadı; yeni nesiller kullanılır.

## Önceki hedefli kabul ve sürümler

- **Son tam analiz FAILED:** `0439924a`, nesil `9e01aacf-7ab6-4e11-9b7a-b82b45e8a48a`, iş `2cc4bd08-67cf-424a-af67-4f686ea6b8a3`, adım 13/15. Hızlı tarama 32/32, derin tarama 29/29 tamamlandı. 37 görsel figür belirsiz. Tarama tamamlanması kimlik/kitap kabulü değildir.
- **Önceki GPU sürümü `f935b9d9` / v9:** rev3477, beş READY çıktı, teknik SUCCEEDED; analitik NEEDS_REVIEW, `accepted=false`. Gerçek API/PG/Qdrant 313/313 ve hedefli 5/5 kontrol geçti. Aynı sürümde yeniden çağrı `ALREADY_CURRENT`, ek model üretimi yok. Önceki `f1cc4614` sayfa rolü yazım/okuma düzeltmesi 2/2 geçti. [Kurtarma kaydı](RECOVERY-2026-09-21.md).
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
| V9 güncel çıktı tutarlılığı | [313/313 API/PG/Qdrant](evidence/2026-09-21-repair-v9-live-outputs.json), [5/5 hedefli kontrol](evidence/2026-09-21-repair-v9-api.json) | Rev3477, beş READY; tam kitap semantik kabulü değil |
| Worker SIGKILL → kendiliğinden devam | [9 OCR activity attempt 2](evidence/2026-09-21-new-generation-crash.json), yaklaşık 59 sn | Aynı iş/nesilde otomatik devam geçti; tam koşu sonradan FAILED |
| Önceki neslin çıktı kurtarması | Rev3009, 5 READY; 371 API/DB/Qdrant kontrolü | Tarihsel, farklı nesil/sürüm; yeni nesle aktarılmaz |
| Portal bağlamsal API | [8/8 geçti](evidence/2026-09-21-portal-context-api.json) | İki gerçek soru bağlamı; tüm sohbet kabulü değildir |
| Portal mobil yaşam döngüsü | [320/390/768/1440 genişlikleri](evidence/2026-09-21-portal-context-browser.json), [iki soru](evidence/2026-09-21-portal-context-lifecycle.json) | Ölçülen portal sürümü ve akışla sınırlı |

Önceki altı araçlı 317 kontrol ve ilk on sohbet kaydı tarihsel aşamalardır. İlk sohbetlerde metinden görsel yokluğu çıkarma, eski FAILED işi güncel çıktı yokluğu sanma ve yanlış kitap adı üretme görüldü. Sonraki araç/kapsam düzeltmeleri ve yeniden koşu bu sorunları ele aldı. Tam özet aracı tek başına sonu tamamlamadı: önceki nesilde 26–32. sayfalardaki 14 olay NEEDS_REVIEW olduğu için doğrulanmış özete girmiyordu. Özet taşıma bütünlüğü ile olay örgüsü kapsamı ayrı bildiriliyor; filtre gevşetilmedi.

## Açık üretim engelleri

1. Yeni neslin 1–4. sayfa çıkarım parçası, hedefsiz sayfa rolü review kaydının `review_item_check` ihlali nedeniyle geri alındı. `017` ile gerçek sayfa rolü FK hedefi kuruldu; gerçek yeniden çıkarım ilk denemede 4 anılma ve 2 olay kaydetti; 1/2/3. sayfa rol önerileri ayrı review FK hedeflerine bağlandı. [Gerçek jobs MCP–bağımsız PG karşılaştırması 2/2 geçti](evidence/2026-09-21-page-role-review-repair.json); bu yazım/okuma düzeltmesi kabul edildi, sayfa rolünün semantik kabulü ayrı.
2. Yeni özet, tema etiketlerinden kanıtsız neden–sonuç üretti; Critic üç taslağı reddetti, rapor yayımlanmadı. V8 bölüm/kitap özetlerini READY üretti; bağımsız okumada 24 cümle ön sayfa/görsel ayrıntılarla dolup 13. sayfada bitti. **Olay örgüsü kapsamı FAIL.** V9, aynı snapshot içindeki bütün VERIFIED EVENT iddialarını kullanma, ilk/son desteklenen olay sayfası kontrolü ve `ALREADY_CURRENT` kod/policy eşliği için `f935b9d9` olarak sunucuda kuruldu ve teknik kabul geçti. Rev3477 özetinde 21 cümle kullanılabilir EVENT sayfalarının tümünü (8, 9, 11, 12, 13, 15, 16, 19, 20, 22, 24, 25, 27) kapsıyor. **İlk 5–7 ve son 28–32 anlatı eksikleri nedeniyle tam kitap kabulü yok.**
3. Beş kısıt kodda giderildi, ayrı gerçek kitap kabulü bekliyor: aynı sayfadaki bütün figürlerin sürekliliğe katılması, kaynaklı tekil duygu bağı, görsel doğrulamasız elemenin kaldırılması, iki figürden başlayan tüm partilerin açık kapsamı, NON_STORY/topluluk bilgisinin korunması. [Denetim ve kabul matrisi](CONSTRAINT-AUDIT.md).
4. 37 görsel figür belirsiz; kritik kişi/figür doğruluğu bağımsız kanıtla ölçülmeli. Önceki neslin 23 belirsiz figürü bu neslin sayısı değildir.
5. Alias regresyonu 18/19; kaynak kapsamı, sayfa rolleri, ham PDF–OCR uyuşmazlıkları ve görsel-only sayfalar için tam analitik kabul yok. Eski nesillerin kaynak baytları korunur.
6. Son sürümün rev3477 beş çıktısı ve Qdrant teknik karşılaştırması geçti; bu sürümün gerçek portal sohbeti ve bağımsız kitap semantiği ayrıca doğrulanmalı. Başarısız iş geçmişi başarılıya çevrilmemeli.

## Teknolojik değerlendirme

Mevcut depo yapılandırmasında yönetici model Qwen3.8-27B-FP8; hızlı görsel Qwen3-VL-8B-Instruct; derin görsel Qwen3-VL-32B-Thinking; embedding/reranker ayrı 8B modeller. GPU0 BI, GPU1 Editor. Derin görsel model 0,90 bellek payıyla diğer Editor modelleriyle aynı anda yerleşemez; gateway değişimi gecikme kaynağıdır. FP8 derin görsel aday tanımı var, ancak gerçek sayfa/kimlik kalitesi kabul edilmeden varsayılan yapılmadı.

Gözlenen temel hatalar model yükseltmesiyle açıklanamaz: eksik araç sayfalaması, eski/güncel durum karışması, kaybolan sohbet geçmişi ve kaynak geometri sırası. Bunlar önce düzeltilir. Alternatif modelin daha iyi olduğu veya güncel sürümlerin araştırıldığı iddia edilmiyor; bu turda model değişikliği yapılmadı.

## Yayın ve sonraki kabul

GitHub origin yayını son denemede HTTPS kimliği bulunamadığından başarısız. Yerel main ve kurulu release hashleri ayrı kaydedilir; origin yayımlandı denmez. Genel taramalar kapalı kalır.

1. Sayfa rolü 2/2 ve v9 çıktı 313/313 + hedefli 5/5 kabulünü koru; eksik ilk/son anlatı olaylarını kaynak üzerinden çöz; kaynakları yeniden taramak veya ikinci ağır koşu açmak yerine mevcut kanıtı koru.
2. Sayfa rolü review hedefi, korunmuş çıkarım kayıtları, özet cümleleri ve kanıt referanslarını bağımsız kontrol et. Kanıtsız neden–sonuç veya zayıf kanıttan uzatılmış anlatı kabul edilmez.
3. Beş kısıtın her birini gerçek figür/kişi/kaynak kayıtlarıyla ayrı sonuçlandır; görülmeyen senaryoya PASS verme.
4. Beş güncel çıktı + Qdrant kabulünü yeni değişiklik olduğunda ilgili sürümde yenile; gerçek portal sohbetini son kurulu hash üzerinde doğrula; düzeltme sonrası eski revizyonun reddini kontrol et.
5. Kaynak/kimlik/analitik kabul ve main/origin/sunucu eşliği sağlanmadan üretim kararı verme. Yerel veya sentetik ürün testi kabul yerine kullanılamaz.
