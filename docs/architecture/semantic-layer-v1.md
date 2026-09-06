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
| 12 SuperSonic A/B | sonra: `SuperSonicCompilerAdapter` aynı arayüzle; ölçülebilir kazanırsa girer | — |

## 6. Başarı kriteri

İlk milestone **Semantic Value Cold Start**: recall OFF iken kaybedilen 6 sorunun değer-çözümleme
kaynaklı olanları (toptan, perakende, iade oranı, son günler …) History Miner + Profiler + aday hattı ile
(elle katalog yazmadan) CERTIFIED'a taşınır; bench dilim bazında raporlanır (tek sayı değil).

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
| Schema | 18/20 |
| Semantic Value | 12/13 |
| Metric | 12/14 |
| Temporal | 18/18 |
| SQL (deterministik, LLM'siz) | 13/20 |
| Result | sunucuda `--bridge` ile ölçülür |

Kalan 7 SQL kaybı LLM'siz ölçümdür: bu sorular köprüde ExistingCompiler'a (Qwen + sertifikalı gerçekler) düşer.
Kayıp nedenleri dürüst: `satılan adet` (2 formül varyantı, destek 1+1), `iade tutarı` (ölçü kelimesi
"tutar" için sertifikalı formül yok), `KITAPCI/E-TICARET` kanal kodları (kanal *değer*leri henüz
history'de yok — profil `SPECODE2` enum'unu görüyor, doğrulanmış sorgu gelince aday→sertifika).

Gate politikası (uygulanan): `SEMANTIC_GATE_MODE=multi_source` — `validated ≥ 3` **veya**
`validated ≥ 1 ∧ (DOC|HUMAN) ∧ profile_fit`; `strict` = yalnız `validated ≥ 3`. LLM adayı hiçbir
modda tek başına geçemez.
