# Doğrulama ve revizyona bağlı çıktı üretimi — canlı kabul

> Sonraki okuma entegrasyonu: `0.13.0-reads-7eda4ec1` ile rapor, kart, timeline, aktör, karakter geçmişi ve Hermes MCP okumaları ortak güncel sürüme geçirildi. Bu belgedeki 0.12 kabul kapsamı tarihsel olarak korunur; yeni kanıt ve kalan sınırlar [CURRENT-READS.md](CURRENT-READS.md).

21 Eylül 2026. **Tek gerçek kitapta teknik yaşam döngüsü kabulü geçti.**
Düzeltme → eski çıktıları kapatma → otomatik yeniden üretim → süreç kesintisinden
sonra devam, gerçek PostgreSQL, modeller, kontrol API'si ve Qdrant ile sınandı.
Tam kitap analitik kabulü değildir. Koşu bitti; bakım kilidi açık, üreticiler ve
Editor modelleri kapalı, GPU 1 boş. Genel taramalar açılmadı.

Kanıt: [gerçek yaşam döngüsü](evidence/2026-09-21-output-lifecycle.json).
Tam kayıtlar `/data/editor/backups/20260921-live-outputs/` altında; özette hashleri var.

## Son sürüm ve gerçek kitap

- Kitap: **Dünyanın En Korkak Hayvanı**, 32 fiziksel sayfa.
- Nesil: `3a987c80-95ba-48ce-a08e-820425cf438d`.
- PDF SHA-256: `12cc83a4ccffe9394fa2695c76e460cf87e2ffe32e6ae69d6699fcaee43ceea2`.
- Ayrı kuyruk: `editor-output-acceptance-20260921`; genel worker/MCP/Hermes kapalı.
- Kaynak üreticileri: `0.12.0-outputs-b5bfc0d7`. Son doğrulama/çıktı kodu:
  **`0.12.1-outputs-226d05ac`**, release `/data/editor/releases/226d05ac`.
- Image: `sha256:f8f702adbed39ec29f571fb4a63548334bc7507db146d696551765e18d40d5e3`.

Temporal marker ve activity geçmişinde yeni doğrulama-önce dalı doğrulandı.
İlk gerçek özette filin merakı Yavru Vombat'a aktarıldı; Critic bunu yakaladı ve
ilk Temporal işi FAILED kaldı. Bu tarihsel durum değiştirilmedi. Tamamlanmış
kaynak üreticilerinin aynı açık neslinde otomatik çıktı tüketicisiyle ilerledik.
Son kodla sıfırdan ikinci bir tam kitap Temporal koşusu yapıldığı iddia edilmiyor.

## Canlı koşuda giderilen ek sorunlar

1. İlk ret sonrası üretim duruyordu. `validated-outputs-v5`, ret gerekçesiyle en
   fazla üç taslak üretir; başarısız taslak yayımlanmaz.
2. Cümle denetçisi iddianın tür/sayfa bağlamını kaybediyordu. Artık iddia metni,
   türü, kimliği ve sayfaları birlikte aktarılır.
3. Yalnız boolean isteyen denetçi bire bir aynı metni reddedebiliyordu. Karardan
   önce kısa gerekçe üretilir; gerekçe düzeltme çağrısına taşınır. Tek doğrulanmış
   iddianın bire bir metni ayrıca `EXACT_VERIFIED_CLAIM` kanıtıdır; yalnız sondaki
   tek nokta eklenmesine izin verilir. Bulanık eşleşme, ad değiştirme veya
   belirsizlik/noktalama silme yoktur. Yeniden yazılan cümlede Critic onayı gerekir.
   Model anlaşmazlıkları saklanır. Gerçek tanı çağrıları 27144–27145: 12 doğru
   cümle kabul edildi; bir doğru ve iki gerçek hatalı cümlede bağımsız beklenti
   `true,false,false` eşleşti. Bu, genel model kalite kıyaslaması değildir.
4. Yeni kod eski deneme bütçesine takılıyordu. `016_rebuild_code_budget.sql`, üç
   denemeyi revizyon + kod sürümüne bağlar. Aynı kodun yeniden başlaması bütçeyi
   sıfırlamaz; beş dakikalık hata geri çekilmesi sürer.
5. Temizlenen katılımcı listesi yokluk sayılıyordu. Düzeltme yazımları artık
   `participants_invalidated` kaynağını taşır. Aktör kontrolü geçersiz eski listeyle
   karşılaştırma yapmaz; gerçek olasılık/belirsizlik kontrolü sürer. Gözlenen yanlış
   review kayıtlı gerekçeyle kapatıldı; yeni iddia CANDIDATE olarak gerçek Critic ve
   aktör kontrolüne tekrar girdi, elle onaylanmadı.

## Ölçülen döngü

İlk hazır çıktı revizyonu 2683. Kaynaklı açıklık düzeltmesi, 6. sayfadaki
“Annesi” öznesini “Yavru Vombat'ın annesi” yaptı. 2696 revizyonunda beş API çıktısı
anında kapandı, 7 aktör kaydı silindi; eski rapor yayını ve eski indeks araması
reddedildi. Tüketici kendiliğinden 2779 revizyonunu üretti. Katılımcı-listesi
düzeltmesinden sonra **2874** son revizyonu beş çıktıda tamamlandı.

Son kodda bölüm özeti kaydedilmiş, kitap özeti BUILDING iken tüketici SIGKILL ile
sonlandırıldı (exit 137). Ölü DB bağlantısı doğrulandı. Servis yeniden başlatılınca
deneme 1→2 oldu; kaydedilmiş bölüm özeti aynı build anahtarı, içerik ve oluşturulma
zamanıyla kullanıldı. Yarım kitap özeti yeniden üretildi. Servisi Docker üzerinden
biz yeniden başlattık; kendiliğinden OS/service restart veya Temporal activity-worker
crash replay kabulü olarak sunulmuyor. Model çağrısında exactly-once garantisi yok.

- **522/522** gerçek API/DB, referans ve sürüm kontrolü; **11/11** yaşam döngüsü
  karşılaştırması. Bunlar 522 ayrı kitap/soru veya anlamsal doğruluk puanı değildir.
- Beş çıktı revizyon 2874 ve aynı snapshot'ta; düzeltilmiş iddia hem bölüm hem kitap
  özetinde referanslı, rapor/katalog olay metni ve claim kimliği eş.
- Qdrant **160/160 tam payload** bağımsız snapshot referansıyla eş; gerçek
  embedding/reranker araması düzeltilmiş olayı getirdi. Eski iki iddia güncel
  özet referanslarından çıkarıldı.
- Tamamlanmış işi tekrar çağırma: `ALREADY_CURRENT`, **0 ek model çağrısı**.
- Eski analizlerin 13 tablosunun içerik hashleri değişmedi. Son sunucu kodunda
  altı mühürlü kitap için eski çıktı okuma regresyonu **54/54**; 17 tablo sabit.
- Bakım true; aktif Temporal iş ve bekleyen rebuild yok. Gateway/worker/rebuild/
  MCP/Hermes ve Editor modelleri kapalı; GPU 1 **0 MiB**. BI modeli çalışıyor.

## Kabul sınırı

Teknik çıktı döngüsü geçti; analitik durum **NEEDS_REVIEW**, yayın **BLOCKED**.
Kaynak uyarıları, doğrulanmamış sayfa türleri ve açık incelemeler var. Görsel kimlikte
60 anılışın 7'si, metinde 33 anılışın 22'si karaktere bağlandı. Bağımsız tam kitap
semantik kabul kapısı henüz yok. Yeni artifact API'nin eski UI/Hermes okuma yollarına
ürün entegrasyonu ve eski Qdrant noktalarının temizliği bu kabulün dışında.

`deploy/verify_live_outputs.py` ve iki kaynaklı kabul yazım scripti yalnız sunucuda
gerçek veriyle çalıştırıldı. Yerel birim/mock/fixture/SQLite/yapay veri testi yok.

---

## 0.12.0 ilk yayının tarihsel notları

Aşağıdaki bölüm ilk salt okunur yayının kaydıdır. Buradaki DOĞRULANAMADI ve sürüm
bilgileri o aşamaya aittir; güncel teknik yaşam döngüsü sonucu yukarıdadır.

21 Eylül 2026. `verified-revision-outputs-v1` yeni Temporal işlerinin yoludur.
Önceki geçmişler eski patch dalını korur. Bakım kilidi kaldırılmaz, üreticiler
başlatılmaz. Bu yayın yeni nesil model koşusunun kabulü değildir.

## Sıra

Kaynak → adaylar → metin/görsel kimlik ve süreklilik → olgu Critic'i → aktör
kontrolü → çelişki/kuyruk → regresyon → `knowledge_snapshot` → bölüm özeti →
kitap özeti → arama indeksi → rapor → katalog.

Özet üreticisi yalnız snapshot içindeki ortak kullanılabilir iddiaları okur.
Modelin verdiği iddia kimlikleri ve kanıtları denetlenir; her cümle ikinci model
çağrısında kaynak iddialarına karşı kontrol edilir. Eksik/tekrarlı referans veya
eksik/olumsuz Critic kararı üretimi başarısız kılar. Boş girdi ayrı belirtilir;
bağlam aşımı sessiz kesilmez. Model/prompt/kod/snapshot bilgileri build anahtarına
bağlıdır; model profili değişmişse yeni nesil gerekir.

## Geçersiz kılma ve yeniden üretim

- Kanonik yazım aynı transaction'da revizyonu artırır, çıktıları STALE yapar,
  kuyruğun istenen revizyonunu ilerletir ve `validated_revision`ı temizler.
- Review, contradiction, text-visual-check ve regression değişiklikleri de izlenir.
- Critic olay metnini daraltınca claim ile event.summary birlikte güncellenir;
  eski katılımcı tahmini temizlenir. Olayın/karakterin ilgili alanı değişince
  eski aktör okumaları transaction içinde silinir ve yeniden okunur.
- `producer_completed` olmadan işçi çıktı üretmez. Aynı neslin iki tüketicisi
  session advisory lock sayesinde eşzamanlı üretim yapamaz. Çökmede kilit düşer.
- Doğrulama yazımları transaction-local bir çalışma kimliğiyle işaretlenir.
  Doğrulama sırasında başka bir düzeltme gelirse snapshot sabitlenmez; yeni
  revizyon tekrar doğrulanır. Böylece kontrol edilmemiş revizyon damgalanmaz.
- Girdi snapshot'ı ve `artifact_version` kayıtları değişmez. Üretimin başında ve
  yayınında revizyon kontrol edilir. Değişmiş bilgiyle biten sonuç güncel pointer'a
  alınmaz; yeni kuyruğu tamamlandı işaretleyemez.
- Çıktı kaydı, pointer ve bağımlı çıktıların geçersizliği tek transaction'dadır.
  Aynı build anahtarının kaydedilmiş sonucu tekrarda yeniden kullanılır. Model
  çağrısının kayıt ile sonuç commit'i arasındaki çökmede tekrar çağrı mümkündür;
  model için exactly-once iddiası yoktur.
- En fazla üç deneme; daemon hatada beş dakika geri çekilir. Başarısız çıktı
  FAILED kalır, hata kuyrukta görünür. Yeni kanonik revizyon yeni deneme bütçesidir.
- Qdrant noktaları build anahtarına özel yazılır; satır/dimension sayısı kontrol
  edilmeden pointer açılmaz. Sorgu yalnız güncel build'i arar ve dönüş öncesi
  pointer'ı yeniden kontrol eder. Eski noktalar fiziksel olarak saklanır ama
  güncel aramaya katılmaz. Eski nokta temizliği bu adımın dışında.

`rebuild` Compose servisi `analysis` profilindedir. Genel bakıma rağmen işler
çalışmaz; `pending()` boş döner. Açık TRACKED nesil değiştiğinde tüketici yeniden
olgu/aktör/çelişki doğrulaması yapar, sonra çıktıları üretir. Kaynak taraması veya
bütün görsel çıkarım bu tüketici tarafından yeniden yapılmaz; bunların değişmesi
kaynak/görsel yeniden analizini de gerektirebilir. Analitik kabul bu yüzden ayrıca
engellidir. Mühürlü eski nesil değiştirilemez; yeni nesil gerekir.

## Okuma ve kabul

- `GET /v1/generations/{id}/output-plan`: salt okunur gerçek girdi snapshot'ı,
  bağımlılık sırası, kuyruk ve özet üretilmemiş rapor önizlemesi.
- `GET /v1/generations/{id}/artifacts/{kind}`: yalnız READY + güncel revizyon +
  aynı doğrulanmış revizyon eşleşirse çıktı döner. Aksi durumda `available=false`.
- Yeni özet/rapor/katalog formatı immutable artifact API'sindedir. Eski claim,
  report ve catalog_card tablolarına bağımsız kopya yazılmaz. Eski ön yüz/Hermes
  araçlarının yeni artifact API'sine ürün entegrasyonu bu yayında yapılmadı.
- Teknik SUCCEEDED ile `analytical_status=NEEDS_REVIEW` ayrıdır. Rapor adımı artık
  yeni nesli mühürlemez. Başarısız regresyon, eksik kaynak ve kimlik kontrolü olan
  bir sonuç analitik kabul sayılmaz. Bağımsız semantik kabul kapısı henüz yok;
  yeni çıktılar kaynak destekli taslak ve yayın BLOCKED olarak kalır.

## Doğrulama sınırı

Yerel test veya yapay veri koşusu yok. `deploy/verify_outputs.py`, tt-gpu'daki gerçek
kontrol API cevabını orijinal DB tablolarından bağımsız hesaplanan claim/event/emotion
listeleriyle tam değer düzeyinde karşılaştırır; rapor ve eski çıktı engelini kontrol
eder. Trigger kurulum kontrolü davranış testi değildir.

Düzeltme yazımı, model üretimi, çökme/yarış, otomatik tüketim ve Qdrant yayın kabulü,
bakım kilidi açıkken salt okunur testle doğrulanamaz: **DOĞRULANAMADI**. Bunları
gerçek bir kitabın yeni neslinde kontrollü yazma/üretim koşusu doğrulamalıdır.


## Sunucu sonucu

Aktif release `/data/editor/releases/b5bfc0d7`, sürüm
`0.12.0-outputs-b5bfc0d7`; image
`sha256:def78cd8126a7f624ccab9fde86a11000f2f6997b653db201523e230e83b14d2`.
`014_revision_outputs.sql` ve `015_validation_fence.sql` uygulandı. Yedek:
`/data/editor/backups/20260921-outputs/`. Kontrol API güncellendi; worker/gateway/
rebuild/model üreticileri başlatılmadı. GPU 1: 0 MiB, BI modeli çalışıyor.

Son yayın üzerinde gerçek DB/API sonuçları:

- 6 gerçek kitapta 54/54 çıktı girdisi, rapor önizlemesi ve güncel olmayan çıktı
  engeli kontrolü geçti. 17 tablo salt okunur koşu öncesi/sonrası aynı.
- Önceki ortak okuma regresyonu 18/18; kaynak kontrolü 544/544 sayfa, hedef özgün
  PDF ve alıntı karşılaştırmaları 6/6 geçti. Model çağrısı sayısı 26.333'te sabit.
- Transaction-local doğrulama kimliği gerçek DB'de salt okunur snapshot ve thread
  geçişiyle kontrol edildi; bağlam çıkınca kimlik temizlendi. Bakımda `pending=[]`.
- Yeni `rebuild_outputs` activity kayıtlı; sunucuda Python derleme/import kontrolü
  geçti. Bunlar Temporal replay veya gerçek düzeltme/üretim davranışı kabulü değildir.
- `knowledge_snapshot` ve `artifact_version` satır sayısı 0: eski analizleri yeni
  iş akışından geçmiş gibi işaretleyen bir backfill yapılmadı.

Kanıtlar: [çıktı okuma](evidence/2026-09-21-output-verification.json),
[ortak okuma](evidence/2026-09-21-output-foundation-regression.json),
[kaynak regresyonu](evidence/2026-09-21-output-source-regression.json).

Kod kurulu fakat otomatik üretim **bakımda ve kabul edilmemiş** durumdadır. Bir
sonraki kabul, gerçek kitabın yeni neslinde düzeltme → geçersiz kılma → yeni çıktı
üretimi → eski revizyonun reddi → tekrar/çökme kontrolüdür. Mevcut salt okunur
kabul kuralını aşan yazma koşusu bu turda yapılmadı.
