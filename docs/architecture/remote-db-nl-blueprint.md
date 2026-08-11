# Uzak DB → Anlama → Doğal Dil → Doğru Veri: Eksiksiz Plan (2026-08-11)

Amaç cümlesi (ürün sahibinin diliyle): *"Remote bir DB bağlantısı yapılsın, sistem
diğer database'i ve içindeki verileri anlasın; son kullanıcı ekranda günlük dille
yazdıkça arka tarafta doğru yerden doğru şekilde veriyi getirelim."*

Bu doküman o hedefe giden **tam** planı tanımlar: mevcut envanter (kod
doğrulamalı), hedef mimari, faz faz iş listesi, veri modeli/API değişiklikleri,
test stratejisi, rollout ve kabul ölçütleri.

---

## 0. Tasarım ilkesi: belirlilik dereceli üç katman

LLM'i her soruda "tahmin eden" tek katman yapmak yerine, sorular üç kademeden
geçer; her kademe bir üsttekinden daha az deterministik ama daha geniş kapsamlıdır:

```
Soru (günlük dil)
  │
  ├─ K1  Deterministik katman        →  %100 garanti, LLM yok
  │       ├─ precompiled scenario     (bind-paramlı şablon, 15 aile)
  │       └─ semantic metric compiler (GROUP BY/TOP-N dahil)
  │
  ├─ K2  Doğrulanmış önbellek        →  daha önce başarılı olmuş Q→SQL,
  │       (learned_query_cache)          her okumada DB'ye karşı doğrulanır
  │
  └─ K3  LLM üretimi                 →  gerçekten ad-hoc sorular;
          (AWEL plan→guard→gateway       şema-öncelikli RAG, dialect-farkındalı
           →repair→execute→explain)      repair, cost-guard emniyeti
```

Kural: **Bir soru kalıbı tekrar ediyorsa yeri K3 değil K1'dir.** K3'ün işi
"bilinmeyeni" cevaplamak; K1'e terfi ettirilebilen her kalıp oradan çıkarılır.
Ölçü: `sql_source` dağılımı (determinism coverage KPI, Faz 3).

Güvenlik sınırı: üretilen hiçbir SQL doğrudan DB'ye gitmez — Query Gateway
(tek SELECT, tablo izin listesi, EXPLAIN maliyet koruması, satır tavanı,
RO kimlik) her üç katmanın da zorunlu geçididir.

---

## 1. Mevcut envanter (2026-08-11 itibarıyla, kod doğrulamalı)

Bu bölüm plan yazılırken tek tek doğrulandı; varsayım değildir.

### 1.1 Zaten var ve çalışıyor
| Parça | Yer | Durum |
|---|---|---|
| Sources API (list/put/delete/test/activate/scan) | `nanobase_api/app.py:619-736` | Çalışıyor; FE BiConnectionPage bağlı |
| Schema scan job zinciri | `POST /sources/{id}/scan` → arq `run_schema_scan` → `SchemaIndexerAdapter` → CLI | Uçtan uca kablolu |
| Schema-indexer | `tools/schema-indexer/` (postgres+oracle+hana scanner, profiler, fingerprint-artımlı, Qdrant writer) | Çalışıyor; bugün 3 kaynak yeniden indekslendi (782 doküman) |
| Senaryo motoru | `scenario_engine/` — 8 aşamalı build (keşif→kombinasyon→SQL derleme→statik/çalıştırma/performans doğrulama→soru üretimi→embedding yayını), 15 aile (LIST/COUNT/SUM/TOP_N/GROUP/COMPARE_PERIOD/AGING/…) | **erp: 777, sigorta: 441 PUBLISHED senaryo; 670.071 paraphrase.** Runtime eşleştirme hash+token+slot tabanlı (Qdrant'a bağımlı değil), Redis plan cache, bind-param'lı şablonlar |
| Semantic catalog + MetricCompiler | `semantic_catalog/` — metric/filter/dimension/term, governance (promotion/review/version), sc_* persistence; compiler bugün GROUP BY/ORDER BY/LIMIT kazandı | `total_revenue` + `total_quantity_sold` canlıda deterministik çalışıyor |
| LLM yolu (K3) | AWEL: iki aşamalı retrieval + columns_complete, dialect'li repair, sqlglot guard'lar, cost-guard | Bu oturumda sertleştirildi; %76.7 execution-accuracy taban çizgisi |
| Learned cache (K2) | `learned_query_cache.py` | DB-doğrulamalı (bugün düzeltildi), TTL'li |
| Eval altyapısı | `tests/text2sql/run-quality-eval.py` (çalıştırma-tabanlı), `run-capacity-probe.py` | Elle koşuluyor; cron yok |

### 1.2 Eksik / kırık / dağınık (planın asıl konusu)
| # | Boşluk | Kanıt |
|---|---|---|
| G1 | **Onboarding parçalı**: kaynak ekle → test → scan+index → allowlist → senaryo build → semantic seed ayrı ayrı, bir kısmı yalnız CLI/elle; tek orkestre akış ve ilerleme ekranı yok | Bugünkü canlı bug: yeni view eklendi, gateway allowlist'i elle unutuldu → deterministik SQL sessizce LLM repair'e düştü |
| G2 | **Gateway tablo izin listesi koda gömülü** (`BI_REPORTING_TABLES` sabiti) — veri kaynağına göre türetilmiyor | `query_gateway/infrastructure/database/datasources.py:38` |
| G3 | **bi_reporting için senaryo hiç üretilmemiş** (erp/sigorta var) | `sc_scenario_instance` dağılımı: bi_reporting=0 |
| G4 | **Senaryo embedding koleksiyonları kayıp**: bugün taze Qdrant volume'ü kuruldu; şema koleksiyonları yeniden üretildi ama `scenario_embedding_publish` çıktıları üretilmedi | Qdrant'ta yalnız `bi_schema_*` var |
| G5 | **Metrik yayınlama kod-içi seed ile** (`seed_*.py` elle çalıştırılıyor); FE'den metrik/eş-anlamlı yönetimi akışı kapalı değil ama uçtan uca bağlanmamış | `semantic_catalog/api/routes.py` var, FE bağlantısı kısmi |
| G6 | **Resolver kod-içi regex** (`resolve_revenue_intent`) — yayınlanmış katalogdan (terim/eş-anlamlı) beslenmiyor; her yeni metrik için kod değişikliği gerekiyor | `nanobase_awel/retrieval/semantic.py` |
| G7 | **LLM destekli şema açıklama adımı yok**: tablolara/kolonlara Türkçe iş açıklaması + PII bayrağı + metrik adayı taslağı üretilmiyor; `TABLE_DESCRIPTIONS` elle yazılmış sözlük | `tools/schema-indexer/config.py:127` |
| G8 | **Kalite/kapasite ölçümü cron'da değil**; determinism-coverage KPI izlenmiyor | Elle koşuldu, baseline var |
| G9 | Senaryo store başlangıçta 670k paraphrase'i belleğe hydrate ediyor — büyüme ile başlangıç süresi/bellek riski | `scenario_engine/infrastructure/store.py` |

---

## 2. Hedef mimari — "yeni uzak DB" yaşam döngüsü

```
[Operatör: FE Bağlantı Sihirbazı]
   1. CONNECT   host/port/db/RO-kullanıcı (+Vault ref)  ── POST /sources
   2. PROBE     bağlantı + RO doğrulama + yetki listesi ── POST /sources/{id}/test
   3. SCAN      şema tara (tablo/kolon/FK/örnek değer)  ── arq: run_schema_scan
   4. INDEX     Qdrant'a embed (bi_schema_{id})          ──   (aynı job zinciri)
   5. DERIVE    tablo izin listesi = taranan tablolar    ── YENİ (G2 çözümü)
   6. ANNOTATE  LLM offline: TR açıklama + PII bayrağı   ── YENİ (G7)
               + metrik/terim ADAYLARI (hepsi DRAFT)
   7. REVIEW    insan onayı: açıklamalar, PII, metrikler ── FE onay ekranı (DRAFT→PUBLISHED)
   8. BUILD     senaryo üretimi (8 aşama, mevcut motor)  ── arq: run_scenario_build
   9. EVAL      golden-question korpusu + accuracy koşusu── YENİ (G8; soru üretimi 8'den gelir)
  10. ACTIVATE  kaynak canlıya alınır                    ── POST /sources/{id}/activate
```

Çalışma zamanı (kullanıcı sorusu) — mevcut sıra korunur, dokümante edilir:
`prepared_sql > precompiled_scenario > semantic_metric > verified > learned > LLM`

---

## 3. Faz planı

### Faz 0 — Onarım + bedava kazanım (tahmin: 1 gün) ⚡ önce bu
Mevcut yatırımı çalışır hale getirmek; yeni kod minimum.

| İş | Ne yapılacak | Dosyalar |
|---|---|---|
| 0.1 | erp/sigorta senaryo runtime'ının canlı doğrulaması (777+441 senaryo gerçekten cevaplıyor mu — hash/token eşleştirme Qdrant'sız çalışmalı, kanıtla) + `scenario_embedding_publish`'in beslediği koleksiyonların yeniden yayını | arq job tetikleme; kod değişikliği beklenmiyor |
| 0.2 | **bi_reporting için senaryo build** çalıştır (mevcut 8 aşamalı motor) → READY_FOR_REVIEW → örneklem incelemesi → publish. Kalite korpusundaki qa-018 (threshold) dahil pek çok kalıp `STATUS_FILTER`/`TOP_N`/`GROUP_MEASURE` aileleriyle K1'e taşınır | API/arq tetikleme + FE BiScenarioReviewsPage üzerinden onay |
| 0.3 | Gateway izin listesini veri-güdümlü yap: `allowed_tables` alanı zaten datasource config'de destekleniyor (`_allowed_tables()`), scan sonucu tabloları datasource kaydına yaz; kod sabiti geriye-uyumlu varsayılan kalsın | `query_gateway/.../datasources.py`, scan job'a küçük ek |
| 0.4 | Ölçüm: quality-eval'i yeniden koş — senaryolar devredeyken taban çizgisi kaç? (%76.7 → beklenti: belirgin artış) | mevcut runner |

### Faz 1 — Onboarding orkestrasyonu (tahmin: 3-5 gün)
"Bir uzak DB bağla" tek bir akış olsun; bugün 6 elle adım.

| İş | Ne yapılacak |
|---|---|
| 1.1 | **Onboard sagası**: `POST /api/v1/bi/sources/{id}/onboard` → arq zinciri `probe → scan+index → derive_allowlist → annotate → (build?) → eval` — senaryo motorunun `staged_pipeline` deseni birebir kopyalanır (her aşama ayrı job, `_should_continue`, durum kaydı). Durum: `GET /sources/{id}/onboarding` (aşama, ilerleme, hatalar). |
| 1.2 | **FE sihirbazı**: BiConnectionPage'e adım göstergeli akış (bağlantı → tarama → açıklama incelemesi → yayın). Mevcut test/scan endpoint'leri kullanılıyor; yeni olan tek ekran onboarding durum sayfası. |
| 1.3 | **Artımlı yeniden indeksleme**: şema değişince (fingerprint farkı) otomatik re-index + etkilenen semantic varlıklara STALE işaretleme (mevcut `mark_stale_by_column` kullanılır) + allowlist güncelleme. Mevcut `BI_SCHEMA_REFRESH_INTERVAL_MINUTES` cron'una bağlanır. |

### Faz 2 — LLM destekli "anlama" adımı (tahmin: 3-4 gün)
G7'nin çözümü; LLM burada **offline ve tek seferlik** kullanılır, canlı yolda değil.

| İş | Ne yapılacak |
|---|---|
| 2.1 | `annotate` aşaması: taranan her tablo/kolon için lokal LLM'den Türkçe iş açıklaması + eş-anlamlılar + PII şüphe bayrağı üret (batched, şema versiyonu başına bir kez). Çıktı **her zaman DRAFT** — `bi_glossary_entries` + semantic catalog'a aday olarak yazılır, asla otomatik yayınlanmaz. |
| 2.2 | Metrik aday çıkarımı: sayısal kolon + tarih kolonu + FK deseninden "aday metrik" taslakları (ör. `SUM(amount)` + zaman alanı + durum filtresi önerisi). İnceleme ekranında tek tıkla `seed` benzeri yayın; `seed_total_revenue_slice.py` deseni genelleştirilir (`publish_metric_from_draft` servisi). |
| 2.3 | PII/maskeleme: onaylanan PII bayrakları gateway masking politikasına bağlanır (kolon bazlı). |

### Faz 3 — Deterministik katmanın veri-güdümlü hale gelmesi (tahmin: 2-3 gün)
G5+G6 çözümü; "yeni metrik = kod değişikliği" denklemi kalkar.

| İş | Ne yapılacak |
|---|---|
| 3.1 | **Katalog-güdümlü resolver**: `resolve_revenue_intent`'teki kod-içi regex/kolon eşlemesi yerine, yayınlanmış metric+term+synonym kayıtlarından türetilen eşleştirme (normalize edilmiş eş-anlamlı sözlüğü + boyut kodu → kolon eşlemesi metric tanımında). Türkçe ek toleransı korunur (bugünkü \b dersleri). Mevcut hardcoded yol, katalog kaydı yoksa geriye-uyumlu devrede kalır. |
| 3.2 | Çakışma/öncelik kuralları dokümante + testli: aynı soruya hem senaryo hem metrik cevap verebildiğinde kim kazanır (öneri: confidence ≥0.99 senaryo > metrik > diğer senaryo eşikleri), `sql_source` her cevapta FE'de görünür. |
| 3.3 | Threshold (HAVING) ailesi: `param_resolver` zaten sayı/slot çözüyor — senaryo tarafında `STATUS_FILTER`+eşik kombinasyonu veya compiler'a güvenli `having` parametresi (bind'li, asla string-concat). Çoklu-boyut GROUP BY (compiler zaten liste alıyor; resolver çoklu boyut sıralaması). |

### Faz 4 — Süreklilik ve ölçüm (tahmin: 1-2 gün)
| İş | Ne yapılacak |
|---|---|
| 4.1 | Nightly cron: her aktif kaynak için quality-eval (`--compare-baseline`, gerileme = alarm) + capacity probe haftalık. Korpus, senaryo motorunun `stage_question_generation` çıktısından kaynak-başına otomatik türetilir + elle yazılmış çekirdek korunur. |
| 4.2 | **Determinism coverage KPI**: `sql_source` dağılımı (K1/K2/K3 oranı) audit'ten günlük özet; hedef eğri: K1 payı artan. LlmOccupancyPanel benzeri küçük FE paneli. |
| 4.3 | G9 iyileştirme: paraphrase hydrate'inin tembelleştirilmesi/sayfalanması (670k satır bellekte — büyümeden önce sınırla). |

### Kapsam dışı (bilinçli)
- Yeni DB motorları (MySQL/MSSQL): scanner+gateway executor soyutlaması hazır olduğundan eklenebilir; bu planda yok.
- Canlı yolda LLM'e şema dışı serbest metin üretimi (rapor yazdırma vb.).
- Çoklu-tenant self-service onboarding UI'ının yetki modeli (mevcut RBAC yeterli sayıldı).

---

## 4. Veri modeli değişiklikleri
- `bi_datasources` (veya mevcut sources kaydı): + `allowed_tables jsonb` (scan'den türetilen), + `onboarding_state jsonb` (aşama/ilerleme/hata), + `schema_fingerprint`.
- `bi_glossary_entries`: + `origin` (`llm_draft|human`), + `pii_flag bool`, + `reviewed_by/at`.
- Semantic catalog: değişiklik yok (mevcut sc_* yeterli); metrik tanımına `dimensions: {code→column}` alanı (resolver'ın 3.1'de okuyacağı eşleme) — `sc_metric_definition.payload` genişletmesi, migration 013.
- Alembic: 013_onboarding_state, 014_metric_dimensions.

## 5. API sözleşmeleri (yeni/değişen)
- `POST /api/v1/bi/sources/{id}/onboard` → `{onboarding_id}`; `GET /sources/{id}/onboarding` → aşama durumu.
- `GET/PUT /api/v1/bi/sources/{id}/annotations` → LLM taslak açıklama/PII inceleme-düzeltme.
- `POST /api/v1/bi/semantic/metrics/{id}/publish-from-draft` (2.2).
- Değişen: `scan` job'ı sonunda `allowed_tables` türetip kaydeder (0.3/1.1).

## 6. Test stratejisi
- Her faz kendi birim testleriyle gelir (bu oturumun standardı: davranışı kanıtlayan regresyon testi olmadan merge yok; bugünkü örnekler: 1460 test).
- Onboarding sagası: sahte-veri kaynaklı entegrasyon testi (sqlite/pg-testcontainer değil — mevcut kalıp: TestClient + in-memory store; execution-validation aşaması yalnız staging'de gerçek DB'ye karşı).
- Kalite kapısı: quality-eval `--compare-baseline` CI benzeri nightly; her faz sonunda tam koşu, sayı raporlanır (dürüst: senaryo katkısı ayrı satır).
- Canlı doğrulama disiplini: her deploy sonrası bugünkü smoke seti (deterministik 4'lü + threshold fall-through + retrieval sağlığı).

## 7. Rollout & geri alma
- Her faz ayrı commit dizisi + prod'a rsync-deploy (mevcut süreç); Faz 0-1 feature-flag gerektirmez (ekleme niteliğinde), Faz 3.1 resolver değişimi `SEMANTIC_RESOLVER_MODE=catalog|legacy` bayrağıyla çift-yol.
- Geri alma: allowlist veri-güdümlü kaydı boşsa kod sabiti devreye girer (0.3 tasarımı); resolver bayrakla legacy'e döner; senaryo publish'leri `STALE` işaretlenerek anında devre dışı kalır (mevcut mekanizma).
- Not (bugünden ders): semantic metrik/katalog değişikliği sonrası `nanobase-bi-api` restart şart (store başlangıçta hydrate ediyor) — 1.1 sagasının "activate" adımı bunu otomatikleştirir.

## 8. Riskler
| Risk | Etki | Önlem |
|---|---|---|
| LLM açıklama taslakları yanlış/uydurma | Yanlış iş sözlüğü | Asla otomatik yayın; zorunlu insan onayı (7. adım), örnek-veri kanıtı ekranda |
| Senaryo hacmi (670k paraphrase) bellek/başlangıç | API başlatma süresi | 4.3; kısa vadede mevcut durum çalışıyor |
| Katalog-güdümlü resolver yanlış eşleşme | Yanlış "kesin doğru" | Eşik + tek-aday kuralı; belirsizlikte K3'e düş; bugünkü test disiplini |
| Paylaşılan sunucu yükü (load 35-105 görüldü) | Eval/gerçek gecikme | Ayrı kapasite konusu; plan kapsamı dışında ama KPI'da görünür |
| Onboarding sagasında yarım kalma | Tutarsız kaynak durumu | Her aşama idempotent (senaryo pipeline deseni), `onboarding_state` üzerinden kaldığı yerden devam |

## 9. Kabul ölçütleri (ölçülebilir)
1. **Faz 0 sonu**: bi_reporting'de yayınlanmış ≥200 senaryo; quality-eval ≥ %85 (30 vakalık korpusta); gateway allowlist'i en az bi_reporting için veri-güdümlü.
2. **Faz 1 sonu**: Yeni bir test Postgres kaynağı FE sihirbazından, hiç SSH/CLI olmadan, ≤15 dk'da "activate" durumuna geliyor; onboarding durumu ekranda izlenebiliyor.
3. **Faz 2 sonu**: Yeni kaynakta tablo/kolonların ≥%90'ı için Türkçe açıklama taslağı üretilmiş ve inceleme ekranından onaylanabilir; en az 1 metrik adayı tek tıkla yayınlanabiliyor.
4. **Faz 3 sonu**: Kod değişikliği olmadan (yalnız katalog kaydıyla) yeni bir metrik + eş-anlamlıları canlıda deterministik cevap veriyor; öncelik kuralları testli.
5. **Faz 4 sonu**: Nightly eval cron'u çalışıyor, gerilemede alarm; determinism coverage panelde; hedef: sorguların ≥%60'ı K1/K2'den (LLM'siz) cevaplanıyor.

## 10. Sıralama gerekçesi
Faz 0 ilk çünkü **yazılmış ama etkin olmayan** en büyük yatırımı (senaryo motoru)
devreye alır — en yüksek kazanç/az kod oranı. Faz 1-2 "uzak DB bağla" hedefinin
kendisi; Faz 3 determinizmi ölçeklenebilir kılar; Faz 4 kalıcılığı garanti eder.
