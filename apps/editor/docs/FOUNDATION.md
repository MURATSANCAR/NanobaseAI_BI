# Editor teknik temel — 21 Eylül 2026

Bu yayın altyapı hazırlığıdır. Kitap analizleri ve model servisleri durdurulur;
eski mühürlü nesiller değiştirilmez. Kaynak kapsamı ve model kalitesi kabulü değildir.

## Sunucu düzeni

- `editor-control`, localhost `19140`: mevcut iç gateway anahtarıyla kimlik doğrulayan,
  yalnız okuyan FastAPI. Sağlık, bakım durumu, nesil kabul engelleri ve sayfalı ortak okuma.
- PostgreSQL, Qdrant ve Temporal korunur. Gateway, worker, MCP ve Hermes Compose
  `analysis` profiline alınır; normal `up` bunları açmaz. Deneysel editor-embed durdurulmuş kalır.
- `runtime_control.maintenance=true`: yeni iş/nesil ve bilgi yazımı DB seviyesinde engellenir.
  Yeni worker başlangıcı ve gateway model çalıştırma yolu da bu kilidi okur.
- Geri dönüş için `/data/editor/backups/20260921-foundation/`: önceki kod arşivi,
  PostgreSQL custom-format yedeği ve önceki worker image ID. Eski durmuş konteynerler saklanır.
- Aktif kontrol servisi ve yeni imaj main kaynaklarından hazırlanır. Eski worker imajı
  yalnız geri dönüş için durdurulmuş halde kalır; analiz yeniden açılmadan güncellenmelidir.

## Kurulan sözleşmeler

`012_foundation.sql` yalnız ek tablolar/görünümler/korumalar ekler. Mevcut nesiller
`LEGACY_UNASSESSED`, mevcut çıktılar `UNTRACKED`, yayın `BLOCKED` olarak temsil edilir.
Bu etiketler eski kayıtların içeriğine yazılmaz; ayrı altyapı tablolarındadır.

Kanonik girdide değişiklik aynı transaction içinde bilgi revizyonunu artırır,
değişikliğin önceki/sonraki değerlerini `knowledge_change` içine yazar, bağlı çıktıları
`STALE` yapar ve `rebuild_request` kuyruğundaki istenen revizyonu ilerletir.
İlk sürüm nesil düzeyinde ihtiyatlı geçersiz kılma yapar; öğe düzeyinde en az yeniden
üretim optimizasyonu henüz yoktur. Türetilmiş çıktı bağımlılıkları `artifact_definition`dadır.

`usable_claim/event/emotion` yalnız kabul durumunu ve kaynak neslini sağlayan kayıtları
verir. Eski iddia ile olay metni farklıysa olay ortak okumaya alınmaz. Düzeltme görmüş
duygu yeniden türetilmeden bu görünümden sunulmaz. Kaynak destekli önizleme,
kitabın tamamının editoryal kabulü değildir.

`generation(job_id)` benzersizdir; `prepare_generation` tekrarı mevcut nesli döndürür.
`persist_once` veritabanı yazımıyla tekrar makbuzunu aynı transaction'a alan temel
işlevdir; bütün eski aktivitelere henüz bağlanmamıştır. Dış model çağrısı bu transaction
içinde çalıştırılmamalıdır. Girdi hash'i kaynak/istem/model/ayar/kod sürümünü kapsamalıdır.

## Bu yayının sınırı ve sonraki maddeler

1. Kaynak kapsamı ilk düzeltmesi `0.11.0-source-066a3cfb` ile kuruldu: 544/544 gerçek sayfa kaynak kontrolü. Ayrıntı ve anlamsal açıklar: [SOURCE-INTEGRITY.md](SOURCE-INTEGRITY.md).
2. Yeni workflow: temel olgu Critic'i ve aktör/kimlik uzlaştırması → özetler → çıktı Critic'i;
   bütün yazımların tekrar makbuzuna, çıktı üreticilerinin revizyon kayıtlarına bağlanması.
3. Yeniden üretim tüketicisi: eski revizyonun sonucunu yayınlamayan, sınırlı denemeli işçi.
   Kuyruk bu yayında kurulur; tüketici ve otomatik yeniden tarama **açılmaz**.
4. Eski rapor/timeline/arama/katalog yollarının ortak sözleşmeye taşınması ve indeks yayın işaretçisi.
5. Kimlik/sahne, tema/duygu, görsel kapsam ve bağımsız kabul; sonra model profili/alternatifleri.

Bakım kilidi bu maddeler ve gerçek kitap kabulü tamamlanmadan kaldırılmamalı. Anahtar
değiştirmek tek başına yeni iş akışını tamamlamaz. `SUCCEEDED` analitik kabul değildir.

## Doğrulama

Yerel test yok. `deploy/verify_foundation.py` yalnız tt-gpu'daki gerçek kontrol API'sini
gerçek PostgreSQL taban tablolarından bağımsız hesaplanan sonuçlarla karşılaştırır.
Sayfalama, tam kayıt değerleri, kesilme, reddedilmiş kayıt filtresi ve eski nesillerin
hazır gösterilmemesi denetlenir. Mutasyon/çökme sonrası tekrar/otomatik yeniden üretim
bu salt okunur koşunun kabul kapsamına girmez; yeni nesil aşamasında doğrulanmalıdır.

Kurulum: `0.10.0-foundation-681f7ec`; kontrol imajı
`sha256:99f744654dec02a7b53ad80d1d4cd4310f9e53377689c2e9ceaa35958446ddbc`.
6 gerçek kitap × 3 kayıt türü = **18/18 tam API–DB karşılaştırması geçti**.
Yetki, sayfalama ve eski nesil kabul engelleri de doğrulandı. Claim/event/emotion/report/generation
tablo içerik hashleri kurulumdan önce ve sonra aynı. Aktif iş 0; GPU 1 kullanımı 0 MiB.
Kanıt: [canlı doğrulama](evidence/2026-09-21-foundation-verification.json).
Otomatik yeniden üretim, çökme sonrası tekrar ve yeni nesil semantik kabulü **DOĞRULANAMADI**.
