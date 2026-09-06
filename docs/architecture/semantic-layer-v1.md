# Semantic Layer V1 — WrenAI'siz üretim hattı (2026-09)

Karar: WrenAI (engine + memory + MDL runtime) üretim yolundan çıkarılır. Doğruluk kaynağı
**Semantic Catalog + Evidence Engine**'dir; Qwen (LLM) yalnız *aday üretici* ve *istisna işleyici*dir.

## 0. Teşhis (ölçülen)

| Yol | Doğruluk | Süre | Neden |
|---|---|---|---|
| Üretim (recall ON) | 20/20 | ~27 s | benzer geçmiş soru → doğrulanmış SQL → doğru sonuç |
| Ajan | 19/20 | ~17 s | aynı bilgi, araç döngüsü |
| Recall OFF (cold start) | 14/20 | — | "toptan / perakende / iade oranı / son günler" fiziksel karşılığı bilinmiyor → yanlış SQL |

Sorun model kapasitesi değil, **semantic knowledge coverage**. Çözüm: daha büyük model / RAG / daha çok
geçmiş soru değil; *otomatik keşif + doğrulanmış kanıt + sert sertifikasyon + deterministik çözümleme*.

## 1. Bileşenler (V1)

```
                 ┌──────────────────────── SEMANTIC CATALOG (PostgreSQL, sl_* tabloları) ────────────────────────┐
                 │ concepts · mappings · metric formulas · temporal primitives · evidence · counter-evidence      │
                 │ candidates · versions · query log · schema profile · HUMAN ANNOTATIONS (portal katmanı)        │
                 └────────────▲──────────────────────────▲──────────────────────────▲────────────────────────────┘
                              │                          │                          │
                    History Miner                  Profiler                   Portal (kullanıcı metni)
              doğrulanmış Q→SQL çiftleri      tablo/kolon/enum/anahtar        tanımsız tablo-kolon açıklaması
              sqlglot ile predicate mining    LG_{firm}_{period}_X deseni     → HUMAN evidence + candidate
                              │                          │                          │
                              └──────────────┬───────────┴──────────────────────────┘
                                             ▼
                                    Candidate Generator  (deterministik + Qwen offline)
                                             ▼
                                      Evidence Engine  (hard gate → score → counter-evidence → CERTIFIED/REJECTED/SENSE_CONFLICT/DEPRECATED)
                                             ▼
   USER ──► Runtime Resolver (term extraction → CERTIFIED lookup → temporal → metric) ──► SemanticQuery
                     │ HIT (tam)                                   │ MISS / karmaşık
                     ▼                                             ▼
            DeterministicCompiler (LLM yok)             ExistingCompiler (Qwen, katalog gerçekleri "sert kısıt" olarak istemde)
                     └──────────────── guardrails (SELECT-only, TOP, denied fn) ── dry-run ── SQL Server ────────────┘
```

Ne **yok**: WrenAI, DataHub, Graph DB, generic RAG, swarm agents, runtime DB discovery, runtime catalog
promotion, Qwen-generated certification, elle yazılmış dev glossary.

## 2. Veri modeli (`backend/semantic_layer/store/schema.py`, Alembic `014_semantic_layer`)

| Tablo | İçerik |
|---|---|
| `sl_concept` | id, tenant, datasource, term, normalized_term, semantic_type (DIMENSION_VALUE / METRIC / DEFAULT_FILTER / TEMPORAL / ENTITY / COLUMN), domain, sense_id, status (DISCOVERED→CANDIDATE→CERTIFIED / REJECTED / SENSE_CONFLICT / DEPRECATED), confidence, version, explain_json |
| `sl_mapping` | concept_id, entity (INVOICE, STLINE…), table_pattern (`LG_{firm}_{period}_INVOICE`), column, operator, values_json, formula, time_primitive |
| `sl_evidence` | concept_id, evidence_type (VALIDATED_SQL / ALIAS_BINDING / DOC / PROFILE / HUMAN_ANNOTATION / EXECUTION / LLM_CANDIDATE), source_id, support_count, weight, payload_json |
| `sl_counter_evidence` | concept_id, source_id, conflict_type (VALUE_MISMATCH / COLUMN_MISMATCH / DRIFT), payload_json, severity |
| `sl_candidate` | concept_id, generated_by (history_miner / profiler / qwen / human), model_version, payload_json, status |
| `sl_catalog_version` | tenant, datasource, version, certified_count, snapshot_json, created_at |
| `sl_query_log` | question, sql, catalog_version, compiler, resolved_json, executed, validated (feedback), result_fingerprint |
| `sl_schema_profile` | datasource, table_name, table_pattern, entity, columns_json (type, distinct, top values, null ratio), keys_json, relationships_json, scanned_at |
| `sl_schema_annotation` | datasource, table_pattern, column (nullable), text, author, status (ACTIVE/RETIRED), created_at — **portal kullanıcı katmanı** |

Fiziksel tablo adı saklanmaz: `LG_411_01_INVOICE` → `LG_{firm}_{period}_INVOICE` + context `{firm: 411, period: 01}`.

## 3. Evidence Engine

Hard gate (hepsi sağlanmalı):
`validated_query_support >= 3` (veya insan onaylı sertifikasyon) ∧ fiziksel mapping var ∧ table_pattern profilde var
∧ çözümsüz şema drift yok ∧ engelleyici karşı-kanıt yok.

Skor: `E = 0.30·validated_sql + 0.20·question_correlation + 0.15·profile_fit + 0.15·physical_context_fit
+ 0.10·semantic_similarity + 0.10·execution_consistency`; karşı-kanıt: `E' = E·(1 − min(1, 2·r_contra))`.
Aynı terim için ≥2 farklı fiziksel değer kümesi ve ikisinin de desteği varsa → `SENSE_CONFLICT`
(sense_split adayı üretilir, sertifika verilmez). Profil dağılımı değişirse (certified değer artık
profilde yoksa) → `DEPRECATED` (drift).

## 4. Runtime

- Resolver: TR normalizasyon → 1..3-gram terimler → CERTIFIED concept lookup (exact/normalized/synonym,
  vektör yok) → temporal parser (bugün, dün, son N gün, bu/geçen ay, MTD/YTD/QTD, "Temmuz 2026",
  "2026 Ocak–Ağustos"; "son günler" → AMBIGUOUS) → SemanticQuery (+ "why this mapping" açıklaması).
- Compiler arayüzü: `SemanticQueryCompiler.compile(SemanticQuery, catalog) -> CompiledQuery`.
  `DeterministicCompiler` yalnız tüm slotlar CERTIFIED ve şekil basitse (metric [+group] [+time] [+filters]).
  `ExistingCompiler` = mevcut Qwen istemi (kurallar + recall + şema bağlamı) **+ sertifikalı gerçekler**.
  Router önce deterministik dener; aksi halde LLM. `SEMANTIC_STRICT_MISS=1` ise çözümsüz değer terimi
  varken SQL üretilmez (netleştirme istenir); varsayılan kapalı (20/20 korunur).
- Her sorgu `sl_query_log`'a catalog_version + compiler ile yazılır; kullanıcı "doğru" derse
  `validated=true` → History Miner girdisi olur (memory ON/OFF'tan bağımsız).

## 5. Uygulama sırası

| Faz | Çıktı | Dosya |
|---|---|---|
| 1 Catalog | store + migration + CLI `init-db` | `semantic_layer/store/*`, `alembic/versions/014_semantic_layer.py` |
| 2 History Miner | pairs-export.yml + knowledge/sql/*.md + sl_query_log → SQL facts / question facts / correlations → candidates + evidence | `semantic_layer/history/*` |
| 3 Profiler | MSSQL/Postgres/SQLite connector + MDL offline; enum, anahtar, ilişki, table pattern | `semantic_layer/profiler/*` |
| 4 Candidate Generator | deterministik (miner+profile+doc) + Qwen offline (unresolved terms) | `semantic_layer/candidates/*` |
| 5 Evidence Engine | gate + score + counter + sense split + drift + version snapshot | `semantic_layer/evidence/engine.py` |
| 6 Resolver | term extraction, temporal, explain | `semantic_layer/runtime/resolver.py`, `temporal.py` |
| 7 Compiler | Deterministic + Existing(LLM) + router + guardrails | `semantic_layer/runtime/compiler.py` |
| 8 Bridge | `backend/semantic_bridge` (:8795) cockpit sözleşmesi (`/api/v1/ask`, `/run_sql`, `/engine`, `/generate_summary`) + `/api/v1/semantic/*` | WrenAI'siz; pyodbc/FreeTDS |
| 9 Portal | `/bi/semantic-layer`: tespit edilen tablo/kolonlar, katalog durumu, kullanıcı açıklama girişi | `nanobase_api/semantic_layer_api.py`, `src/pages/BiSemanticLayerPage.tsx` |
| 10 Bench | cold-start 6 dilim (Schema/Value/Metric/Temporal/SQL/Result) | `tests/text2sql/semantic-coldstart-eval.py` |
| 11 Ops | worker (gece 02:00: profile → mine → candidates → certify → version), deploy script | `infra/systemd/nanobase-semantic-worker.*`, `scripts/server/deploy-semantic-bridge.sh` |
| 12 SuperSonic A/B | `SuperSonicCompilerAdapter` aynı arayüzle + gölge/pinned mod + A/B ölçüm hattı | `semantic_layer/runtime/supersonic.py`, `tests/text2sql/compiler-ab-eval.py` |

## 6. Başarı kriteri

İlk milestone **Semantic Value Cold Start**: recall OFF iken kaybedilen 6 sorunun değer-çözümleme
kaynaklı olanları (toptan, perakende, iade oranı, son günler …) History Miner + Profiler + aday hattı ile
(elle katalog yazmadan) CERTIFIED'a taşınır; bench dilim bazında raporlanır (tek sayı değil).

## 7. Şemadan bağımsızlık (zorunlu tasarım kuralı)

Motor kodunda **hiçbir müşteriye özgü tablo/kolon/kod adı yoktur**; hepsi profilden türetilir:

| Soru | Eski (statik) | Yeni (dinamik) |
|---|---|---|
| Tablo ailesi / dönem deseni | `LG_(\d{3})_(\d{2})_X` regex'i | ad içindeki sayısal segmentler konumsal yer tutucuya döner: `LG_411_01_INVOICE → LG_{n0}_{n1}_INVOICE`, `sales_2024_orders → SALES_{n0}_ORDERS` (`naming.logical_table`) |
| `*REF` hangi tabloya gider? | `CLIENTREF→CLCARD` sözlüğü | (1) gerçek FK metadata, (2) doğrulanmış SQL'lerden madenlenen JOIN'ler, (3) değer örtüşmesi ile bağlantı çıkarımı (`profiler.infer_links`) |
| Hangi kolon metrik kapsamı? | `TRCODE/LINETYPE` listesi | profil: 3–64 farklı değerli enum = iş kodu (kapsam); ≤2 ve boolean-biçimli (0/1, Y/N) = bayrak (varsayılan filtre adayı) (`conventions.py`) |
| Tarih kolonu | `DATE_` tercihi | profil tip taraması + doğrulanmış sorguların fiilen filtrelediği kolon (`Conventions.learn_time_hint`) |
| Aynı kolon iki tabloda | `NETTOTAL→INVOICE` sezgisi | `preferred_entity`: satır sayısı (başlık tablosu küçüktür), referans yönü, sorgudaki diğer kolonlar |
| Doküman madenciliği | sabit kolon/varlık listesi | profildeki varlık ve enum kolonları (`mine_text(..., conventions)`) |
| LLM istemi | "TRCODE, LINETYPE, CANCELLED = 0'a uy" | yalnız profil tabloları + sertifikalı katalog + lehçe notu |
| Lehçe | T-SQL varsayımı | `Dialect` aileleri (tsql / sqlite / standard), bağlantıdan gelir |
| Ayarlar | `datasource=logo`, `LG_411_%`, `firm/period` | hepsi boş varsayılan; `SEMANTIC_CONTEXT=n0=412` ile aynı katalog başka firma/döneme derlenir |

Bunu koruyan iki test: `tests/test_dynamic_schema.py` — (a) tamamen farklı bir şema (FK'siz, `*REF`siz,
yıl ekli olgu tablosu) üzerinde profil→madencilik→sertifika→çözümleme→derleme→**çalıştırma** uçtan uca
doğru sonucu üretir, (b) motor kaynaklarında müşteri tanımlayıcısı geçmediğini grep ile doğrular.

## 7. Uygulama durumu (2026-09-06)

Kodlandı ve yerelde doğrulandı (23 birim/entegrasyon testi, SQLite üzerinde uçtan uca):

| Bileşen | Dosya | Durum |
|---|---|---|
| Catalog store + DDL | `backend/semantic_layer/store/`, `nanobase_api/alembic/versions/014_semantic_layer.py` | ✅ PG (JSONB) + SQLite |
| History Miner | `backend/semantic_layer/history/` | ✅ 52 çift (23 gerçek) → toptan→TRCODE 8, perakende→7, iade→(2,3), net ciro formülü (4 destek), kanal→CLCARD.SPECODE2, maliyetli→OUTCOST<>0 |
| Profiler | `backend/semantic_layer/profiler/` | ✅ MSSQL (pyodbc) / Postgres / SQLite / MDL-offline; Intugle opsiyonel adaptör |
| Doc miner + Candidate Generator | `backend/semantic_layer/candidates/` | ✅ enum glossları, "term" = `ENTITY.COLUMN` alias'ları, portal açıklamaları (HUMAN_ANNOTATION), Qwen offline adayları |
| Evidence Engine | `backend/semantic_layer/evidence/engine.py` | ✅ hard gate, skor, karşı-kanıt, sense conflict, doc-dominance, drift→DEPRECATED, sürüm snapshot, kanıta dayalı eş anlamlı |
| Resolver / Temporal | `backend/semantic_layer/runtime/` | ✅ yalnız CERTIFIED; "son günler" AMBIGUOUS |
| Compiler | `runtime/compiler.py` | ✅ Deterministic (pivot dahil) + Existing (Qwen + sertifikalı gerçekler) + router + `SEMANTIC_STRICT_MISS` |
| Bridge | `backend/semantic_bridge/app.py` (:8795) | ✅ kokpit sözleşmesi, feedback→validated, inventory/annotations |
| Portal | `nanobase_api/semantic_layer_api.py`, `src/pages/BiSemanticLayerPage.tsx` (`/bi/semantic-layer`) | ✅ tespit edilen tablo/kolon, durum rozetleri, kullanıcı açıklaması, "neden bu eşleme" |
| Bench | `tests/text2sql/semantic-coldstart-eval.py` + corpus | ✅ 6 dilim |
| Ops | `scripts/server/deploy-semantic-bridge.sh`, `infra/systemd/nanobase-semantic-worker.*` | ✅ gece 02:00 |

Cold-start (recall OFF, LLM YOK, yalnız katalog + deterministik derleyici, logo_timas knowledge'ından üretilen katalog v1, 37 sertifikalı kavram):

| Dilim | Sonuç |
|---|---|
| Schema | 20/20 |
| Semantic Value | 13/13 |
| Metric | 14/14 |
| Temporal | 18/18 |
| SQL (deterministik, LLM'siz) | 18/20 |
| Result | sunucuda `--bridge` ile ölçülür |

Kalan 2 SQL kaybı bilinçli reddir, LLM hattına düşer: (a) "toptan iade tutarı" — aynı kolonda çelişen iki
değer kümesi (8 ile 2,3) istendi; doğrusu "toptan iade" (tek kod) ve o kavram dokümandan CANDIDATE olarak
duruyor, bir doğrulanmış sorguyla sertifikalanır; (b) "maliyetli ciro" — `maliyetli` terimi 2 doğrulanmış
sorguda görülüyor (eşik 3) ve dokümanda karşılığı yok.

Bu turda eklenen üç kanıt mekanizması (hepsi şemadan bağımsız):
1. **Eşdeğer formül eş anlamlısı** — `SUM(CASE WHEN k THEN x ELSE 0 END)` ≡ `SUM(x)` + kapsam k; aynı
   varlıkta aynı ölçüyü adlandıran terimler tek sertifikalı kavramda birleşir ("satılan adet" ≡ "adet").
   Aynı kolonda farklı değer kümesi varsa asla birleşmez.
2. **Profil/doküman destekli değer literalleri** — sorudaki bir sözcük, *sertifikalı bir kolonun* gözlenen
   ya da dokümante edilmiş değerlerinden biriyse (KITAPCI, E-TICARET) filtre olarak çözümlenir.
3. **Bileşik metrik** — sertifikalı ölçü kolonu + ölçü kelimesi + sertifikalı filtre ("iade tutarı" =
   SUM(<ölçü kolonu>) WHERE <iade filtresi>), tümü sertifikalı olduğunda.
Ayrıca aynı kolonda çelişen filtreler artık deterministik derlemeyi durdurur (boş sonuç üretmek yerine).

Gate politikası (uygulanan): `SEMANTIC_GATE_MODE=multi_source` — `validated ≥ 3` **veya**
`validated ≥ 1 ∧ (DOC|HUMAN) ∧ profile_fit`; `strict` = yalnız `validated ≥ 3`. LLM adayı hiçbir
modda tek başına geçemez.


## 8. Faz 9 — Son kullanıcı turu (2026-09-06)

Sistemi ve tabloları bilmeyen birinin yazacağı 50 soru (`tests/text2sql/enduser-50.yaml`) hazırlandı ve
koşuldu (`tests/text2sql/enduser-eval.py`). Amaç puan değil, **eksik listesi**: her soru sistemin ne
yaptığına göre sınıflanır, çözümlenemeyen her terim toplanır.

İlk turda 50 sorunun 50'si reddedildi ve "eksik" listesi tamamen gürültüydü: Türkçe çekim ekleri
(`cirosunu`, `kitabı`, `mağazaların`), türetmeler (`kârlılığımız`), sıfat-fiiller (`satan`, `bekleyen`)
ve zamirler katalogda olmayan iş terimi sayılıyordu. Bunların tümü **dil düzeyinde** çözüldü
(`normalize.py`): iyelik+hâl ekleri zinciri, ünsüz yumuşaması geri alma, türetme eklerinde geri çekilme,
sıfat-fiil/zarf-fiil/olumsuzluk/koşaç ve sayı sözcükleri. Hiçbirinde müşteriye özgü sözcük yok.

Turun asıl çıktısı **üç sessiz yanlış cevap** oldu — hepsi sorulandan başka bir soruyu cevaplıyordu:

| Bulgu | Neden tehlikeli | Kapanış |
|---|---|---|
| `satmayan` → satış ölçüsüne köprüleniyordu | cevabı tersine çeviriyor | olumsuz çekim köprülenmez |
| kullanıcı filtresi ölçünün kendi kapsamıyla çelişiyordu | her zaman boş sonuç, gerçek sıfır gibi okunur | çelişki tespit edilip reddedilir |
| "payı yüzde kaç" düz toplamla cevaplanıyordu | oran sorusuna mutlak sayı | paydası olmayan oran reddedilir |

Ayrıca **karşılanamayan niteliyeci** diye yeni bir sınıf eklendi: konuyu daraltan ama katalogda karşılığı
olmayan sözcük ("bekleyen siparişler", "satmayan ürünler"). Gramer diye atılırsa daha geniş bir soru
cevaplanmış olur; artık deterministik yolu durdurur ve modele açıkça yazılı gider.

Bu turda kapatılan diğer maddeler:

- **Dönem kapsamı** — her varlığın ilk/son tarihi ölçülür (`sl_schema_profile.time_window_json`,
  Alembic `016`). Bu kurulumda INVOICE `2026-01-01 … 2026-08-17`; "2019'da ne kadar sattık?" artık
  boş sonuç yerine kapsam dışı diye reddediliyor. Penceresi ölçülemeyen varlıklar portalde uyarı olarak
  görünür — kontrolün kapalı olduğu yer saklanmaz.
- **Fan-out** — başlık düzeyi bir ölçü satır tablosuna bağlanınca satır başına tekrarlanır; join yönünden
  tespit edilip reddedilir (şişmiş rakam üretmek yerine).
- **Katalog denetimi** — modelin yazdığı SQL, sorunun sertifikalı okumasıyla karşılaştırılır; aynı kolonu
  sertifikalı kümeyle kesişmeyen değerlere kısıtlıyorsa çalıştırılmaz (`runtime/audit.py`).
- **Ölçü bazı** — bir kolonun dokümante edilmiş bazı ("KDV hariç", "birim maliyet") eşlemesiyle birlikte
  prompta taşınır; farklı bazdaki kolonlar tek toplamda birleştirilmez.
- **Gerileme kapısı** — her yeni katalog, 50 soruluk korpusla bir önceki kabul edilen katalogla
  karşılaştırılır; eskiden cevaplanan bir soru cevaplanmaz olduysa ya da eskiden reddedilen bir soru
  cevaplanır olduysa dağıtım durur (`deploy-semantic-bridge.sh`, `SEMANTIC_GATE_STRICT`).
- **Profil bütçesi** — derin profil aşamasının duvar saati var; aşılırsa kalan tablolar kataloglanır ama
  sondalanmaz ve hangileri olduğu loglanır (kısmi tarama tam tarama gibi görünmez).
- **Katalog önbelleği** — sürüm numarası yerine (sürüm, sertifikalı sayısı, son yazım) parmak izine
  bakılır; portaldan yapılan insan sertifikasyonu ve yarım kalmış bir yeniden kurulum artık görünür.

**Portal döngüsü uçtan uca kanıtlandı** (`test_a_gap_closes_through_one_description_from_the_portal`):
kullanıcıların söylediği ama katalogda olmayan bir sözcük → `/api/v1/semantic/gaps` ile portalde listelenir
→ bir kişi ilgili kolonu tarif eder → HUMAN_ANNOTATION kanıtı sertifikalanır → aynı soru doğru SQL ile
cevaplanır. Kod tarafında hiçbir tanım yok.

Deterministik dilim (LLM yok, yalnız katalog): cevapladığı her soru doğru; cevaplamadıkları ya modele
düşer ya da portalde tanımlanacak terim olarak listelenir. 68 test.


## 9. Faz 8 — SuperSonic A/B (uygulandı)

**Arayüz bizde kalır:** SuperSonic'in kendi web arayüzü / chat / agent yüzeyleri kullanılmaz, kuruluma
frontend gerekmez; ürünün yüzü portal (`/bi/semantic-layer`) ve kokpittir. Bu modül SuperSonic'in yalnız
sorgu API'siyle konuşur ve yalnız "çözümlenmiş SemanticQuery → SQL" için. Kataloğu onların model deposuna
yazmak bile varsayılan kapalıdır (`SUPERSONIC_ALLOW_MODEL_WRITE=1` ile açılır).

SuperSonic **bağımlılık değil, ölçülen bir aday derleyicidir**. Doğruluk kaynağı yine bizim kataloğumuz:
resolver'ın ürettiği `SemanticQuery` (sertifikalı metrik + boyut filtreleri + dönem + kırılım) SuperSonic'in
*struct query* sözleşmesine çevrilir ve SQL istenir; SuperSonic'in kendi NL anlama katmanı devrede değildir.

```
SemanticQuery ─► SuperSonicCompilerAdapter.build_struct()
                 {dataSetId, metrics, dimensions, dimensionFilters, dateInfo, limit, sqlOnly}
              ─► POST {SUPERSONIC_STRUCT_PATH} ─► querySQL ─► CompiledQuery(compiler="supersonic")
```

| Ayar | Anlamı |
|---|---|
| `SUPERSONIC_BASE` | servis adresi; boşsa adaptör hiç kurulmaz (üretim yolu değişmez) |
| `SUPERSONIC_DATASETS=INVOICE=7,STLINE=8` | varlık → dataSet eşlemesi; eksikse adaptör `None` döner ve yönlendirici bir sonraki derleyiciye geçer (asla tahmin etmez) |
| `SUPERSONIC_DATE_FIELDS=INVOICE=invoice_date` | dönem alanı adı (opsiyonel) |
| `SUPERSONIC_MODE=shadow\|off` | gölge mod: cevabı değiştirmeden yanında derler ve ölçer (varsayılan shadow) |
| `SUPERSONIC_HEADLESS=1` (varsayılan) | yalnız API; SuperSonic arayüzü hiçbir yerde kullanılmaz/gömülmez |
| `SUPERSONIC_ALLOW_MODEL_WRITE=0` (varsayılan) | katalog ihracı dosya olarak üretilir; onların deposuna yazmak açık onay ister |
| `SEMANTIC_COMPILER=supersonic` | kontrollü deney: birincil derleyiciyi sabitler |
| `SUPERSONIC_STRUCT_PATH` / `_SQL_PATH` / `_LOGIN_PATH` / `_MODEL_PATH` | sürümler arası uç nokta farkları koddan değil ayardan |

Adil karşılaştırma için katalog SuperSonic modeline dışa aktarılabilir
(`supersonic.export_semantic_model` → dataSet/metric/dimension/defaultFilter), böylece iki derleyici
**aynı bilgi tabanı** üzerinde yarışır.

Ölçüm: `tests/text2sql/compiler-ab-eval.py` her soruyu tek bir resolver koşusundan geçirip her derleyiciye
aynı `SemanticQuery`'yi verir; ürettiği SQL guardrail'den geçirilir, `--bridge` ile çalıştırılır ve
`--truth` ile karşılaştırılır. Rapor matristir: `compiled / behaviour (beklenen reddi de doğru sayar) /
executable / result_correct / certified / latency`. **Terfi kapısı:** aday ancak doğrulukta en az eşit ve
(daha doğru **veya** medyan gecikmede ≥%20 daha hızlı — mevcut zaten <50 ms ise hız tek başına yetmez) ise
önerilir; karar `verdict` alanında gerekçesiyle yazılır.

Yerel referans koşusu (LLM ve SuperSonic olmadan, yalnız deterministik):
`compiled 16/20 · behaviour 18/20 · executable 1.0 · certified 0.8 · medyan gecikme 0 ms`
(`artifacts/timas/compiler-ab-offline.json`). SuperSonic ayağa kalktığında aynı komut
`--compilers deterministic,existing_llm,supersonic --bridge … --truth …` ile çalışır.

Not: SuperSonic uç nokta yolları ve payload alanları sürüme göre değişebilir; adaptör bunları ayar olarak
alır ve sözleşmeyi taklit eden sahte bir servise karşı test edilir (`tests/test_supersonic_ab.py`).
Canlı bir SuperSonic kurulumunda ilk iş `GET /health` + tek bir struct sorgusuyla yolları doğrulamaktır.
