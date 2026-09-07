# Forecasting V1 Planı — "İstanbul satışları önümüzdeki 6 ay nasıl?" (2026-09-05)

Kaynak: Qwen + PostgreSQL + TimesFM tasarım notu.
Bu belge o tasarımı **bu repoya** oturtur. PDF'teki *kalıp* korunur (LLM SQL yazmaz,
deterministik SeriesBundle katmanı, adapter'lı Forecast API, baseline'a karşı
benchmark, ayrı anomali modeli yok); *teknoloji seçimleri* mevcut kilitli mimariyle
(`locked-architecture.md`, `fable-design.md`) çeliştiği yerde uyarlanır.

---

## 0. PDF ↔ repo: dört karar

| # | PDF diyor | Repo gerçeği | Karar |
|---|---|---|---|
| K1 | Main backend **Java 21 / Spring Boot** | `locked-architecture.md`: "Backend Python FastAPI (Spring/Java yok)"; orkestrasyon sahibi `nanobase_api` | **Java yok.** Orchestrator = `nanobase_api` (zaten Qwen'i sürüyor). Forecast API = ayrı FastAPI servisi (PDF de böyle diyor). |
| K3 | Qwen'e `query_semantic()` / `forecast()` **tool**'ları verilir | Chat hattı tool-calling değil: intent → deterministik resolver → compile → gateway; LLM yalnız plan/explain. Fable aksiyomu: tahmin yok, ya bilir ya görünür şekilde reddeder. | **Aynı sonuç, farklı mekanizma.** Forecast niyeti deterministik resolver ile çözülür (`resolve_revenue_intent` kalıbı). Qwen SQL'i de, seriyi de görmez; yalnız hazır forecast gerçeklerini Türkçeye çevirir. |
| K4 | TimesFM **3.0** hedef, 2.5 fallback | 3.0 checkpoint non-commercial/non-production; 2.5 Apache-2.0. Sunucuda GPU olup olmadığı repoda kayıtlı değil; host paylaşımlı ve yük ortalaması 95-105 görüldü. | **Prod = TimesFM 2.5 (CPU'da çalışır, 200M param).** 3.0 yalnız offline benchmark'ta. Faz 0'da `nvidia-smi` ile doğrulanır. |

**Veri gerçeği (en büyük engel):** `bi_reporting` seed'inde 10 sipariş var, Ocak–Haziran 2026.
Aylık forecast için ≥24, tercihen 36+ nokta gerekir. PDF'teki "2023-01 → 2026-08" test
seti bugün hiçbir datasource'ta hazır değil. Faz 0'da sentetik geçmiş seed'lenir; ikinci
dataset olarak erp (Neon) gerçek verisi benchmark'a eklenir.

---

## 1. Hedef mimari (repo diliyle)

```
"İstanbul satışları önümüzdeki 6 ay nasıl?"
        │
        ▼
chat_gateway  ──►  resolve_forecast_intent()          deterministik; metric/dimension/horizon
        │          {metric: total_revenue, dim: {branch_city: İstanbul}, grain: M, horizon: 6, history: 36}
        │          çözemezse → görünür "forecast_declined" (LLM'e düşmez)
        ▼
MetricCompiler(time_grain="month")                     SQL: SUM(line_total) GROUP BY date_trunc('month', order_date)
        │
        ▼
Query Gateway (allowlist!)  ──►  PostgreSQL            aylık satırlar
        │
        ▼
SeriesBundleBuilder                                    sırala · dedupe · frequency · boşluk · tz · min history · horizon · metrik kuralı
        │                                              hata = SeriesBundleError(code) — fail-visible
        ▼
Forecast API  :8793  (backend/forecasting, FastAPI)    POST /forecast
        │
        ├── NaiveEngine / SeasonalNaiveEngine          baseline, CI'da da çalışır
        ├── TimesFM25Engine   (prod)
        └── TimesFM3Engine    (yalnız benchmark)
        │
        ▼
ForecastResult {p10,p50,p90}[horizon] + bundle_hash + engine + version
        │
        ├── bi_meta: fc_forecast_run / fc_forecast_point   (provenance, sonradan gerçekleşenle karşılaştırma)
        ├── result-explain (Qwen)                           yalnız anlatır; sayı üretmez
        └── FE: forecast bloğu (recharts çizgi + p10-p90 bandı)
```

Değişmezler:
- LLM hiçbir aşamada SQL yazmaz, seri görmez, gelecek değeri uydurmaz.
- Her forecast çıktısı `bundle_hash` + `engine@version` + `metric@version` ile izlenebilir (fable provenance).
- Yeterli geçmiş yoksa sistem **reddeder**, "yaklaşık" tahmin üretmez.

---

## 2. Fazlar

### Faz 0 — Kararlar + veri + ortam (0.5-1 gün)

| İş | Ne | Dosya / komut |
|---|---|---|
| 0.1 | Yukarıdaki K1-K4'ü onayla; `locked-architecture.md`'ye "Forecast API :8793, TimesFM 2.5" satırı ekle | `docs/architecture/locked-architecture.md` |
| 0.2 | Sunucuda GPU/CPU/RAM envanteri (`nvidia-smi`, `nproc`, `free -g`); TimesFM 2.5 CPU'da 1 seri × 48 nokta × horizon 6 süresini ölç | `nanobase` ssh |
| 0.3 | **Sentetik geçmiş seed:** `analytics.sales_orders/sales_order_items`'a 2022-09 → 2026-08 arası, şube bazında trend + yıllık mevsimsellik + gürültü içeren 48 ay veri (`generate_series`). Additive, idempotent (`WHERE NOT EXISTS`), mevcut 10 sipariş korunur | `infra/sql/10-forecast-history-seed.sql`, `scripts/server/apply-forecast-seed.sh` |
| 0.4 | `v_sales_revenue_lines`'a `branch_city` kolonu ekle ("İstanbul" filtresi için; view'da şu an `branch_id` var). Gateway allowlist'e dokunma gerekmez — ✅ view üç biçimiyle `BI_REPORTING_TABLES`'da (datasources.py:54/70/86) | `infra/sql/09-sales-revenue-lines-view.sql` |
| 0.5 | ✅ Doğrulandı: `total_revenue` ve `total_quantity_sold` `time_field=public.v_sales_revenue_lines.order_date`, `default_granularity=MONTH` (seed satır 94/111). Ek iş yok | `seed_total_revenue_slice.py` |
| 0.6 | Quality corpus'a 6 forecast sorusu ekle (3 pozitif, 2 reddedilmesi gereken, 1 dimension'lı) | `tests/text2sql/quality-corpus.yaml` |

### Faz 1 — `query_semantic()`: MetricCompiler time grain (1-2 gün)

| İş | Ne | Dosya |
|---|---|---|
| 1.1 | `CompileRequest.time_grain: Literal["day","week","month","quarter","year"] \| None`. Postgres: `date_trunc('month', alias."order_date") AS period`; Oracle: `TRUNC(col,'MM')`; HANA: `SERIES_ROUND`. `GROUP BY period` + mevcut `group_by` birlikte; `ORDER BY period ASC` (ranking sırası değil, zaman sırası). `period` (from/to) ile birleşir | `semantic_catalog/infrastructure/metric_compiler.py` |
| 1.2 | `try_compile_resolved_metric(..., time_grain=, period=)` genişlet; `logicalPlan`'a `timeGrain` yaz | `nanobase_awel/retrieval/semantic.py` |
| 1.3 | `POST /api/v1/bi/semantic/series` — {metricCode, dimensionFilters, grain, historyMonths} → gateway'den geçmiş aylık satırlar. PDF'teki `query_semantic` tool'unun HTTP karşılığı; forecast dışı (grafik, bütçe) tüketiciler için de kullanılır | `nanobase_api/semantic.py` |
| 1.4 | Testler: her dialect için compile snapshot, `period`+`time_grain`+`group_by` kombinasyonları, `time_grain` geçersiz değer → ValidationError | `semantic_catalog/tests/unit/test_compiler_time_grain.py` |

Kabul: `SELECT date_trunc('month', v."order_date") AS "period", SUM(...) FROM v_sales_revenue_lines v WHERE status='completed' AND branch_city='İstanbul' AND order_date >= '2023-09-01' GROUP BY 1 ORDER BY 1` gateway'den **repair'e düşmeden** geçer.

### Faz 2 — SeriesBundle: deterministik normalizasyon katmanı (1 gün)

PDF'in "en kritik parçası". LLM'in forecasting hattına yanlış veri sokamamasının garantisi.

| İş | Ne | Dosya |
|---|---|---|
| 2.1 | Paylaşılan pydantic sözleşme paketi (hem `nanobase_api` hem forecast servisi import eder): `SeriesBundle`, `SeriesPoint`, `ForecastRequest`, `ForecastResponse`, `ForecastPoint`, `SeriesBundleError` (kodlar: `INSUFFICIENT_HISTORY`, `FREQUENCY_MISMATCH`, `GAPS_EXCEED_POLICY`, `HORIZON_TOO_LONG`, `NEGATIVE_VALUE_FOR_METRIC`, `DUPLICATE_TIMESTAMPS`) | `backend/forecasting/contracts/` |
| 2.2 | `SeriesBundleBuilder.from_rows(rows, metric, grain, tz, horizon, missing_policy)`: sırala, dedupe (aynı ay iki satır → hata, sessiz toplama yok), frequency doğrula, eksik ayları `missing_policy` ile (`zero` \| `interpolate` \| `reject`) doldur ve `filled_periods` listesine yaz, tz normalize (`Europe/Istanbul` → ay başı), **min history** (sert 12, uyarılı 24), **horizon ≤ min(12, len/3)**, metrik kuralı (revenue ≥ 0; `NullPolicy` uygula), `bundle_hash = sha256(canonical json)` | `backend/forecasting/contracts/builder.py` |
| 2.3 | Hypothesis tabanlı property testleri (repo'da `hypothesis` zaten var): idempotans, sıra bağımsızlığı, hash kararlılığı, boşluk politikası | `backend/forecasting/tests/test_series_bundle.py` |

### Faz 3 — Forecast API servisi (2 gün)

| İş | Ne | Dosya |
|---|---|---|
| 3.1 | Ayrı servis, ayrı venv (torch ~2 GB; `nanobase_api`'ye **girmez**). `POST /forecast`, `GET /health` (yüklü engine, checkpoint sha, cihaz), `GET /engines` | `backend/forecasting/app/{main,models,service,preprocessing}.py` |
| 3.2 | `ForecastEngine(ABC).forecast(request)`; `NaiveEngine`, `SeasonalNaiveEngine` (m=12), `TimesFM25Engine` (`google/timesfm-2.5-200m-pytorch`, quantile head, `torch.set_num_threads(FORECAST_THREADS)`), `TimesFM3Engine` (`TimesFM3Evaluator`+`ModelConfig`, `FORECAST_ALLOW_NONCOMMERCIAL=1` olmadan yüklenmez) | `backend/forecasting/app/engines/` |
| 3.3 | Yanıt: `forecast[]{timestamp,p10,p50,p90}` + `engine`, `engine_version`, `checkpoint_sha`, `bundle_hash`, `warnings[]`, `latency_ms`. Deterministik: aynı bundle + aynı checkpoint → aynı çıktı (seed sabit) | `models.py` |
| 3.4 | Dağıtım: `Dockerfile`, `infra/systemd/nanobase-forecast.service` (mevcut unit kalıbı; **ayrı** `backend/.venv-forecast` — mevcut unit'ler `backend/.venv` kullanıyor, torch oraya girmez), env `FORECAST_ENGINE=timesfm25`, `FORECAST_THREADS=4`, model warm-load + health'te `ready=false` → gateway ready olana kadar reddeder. Paylaşımlı host: `CPUQuota=` ile sınırla | `deploy/`, `infra/systemd/`, `configs/bi.backend.env.example` |
| 3.5 | `nanobase_api` tarafında `ForecastClient` (httpx, mevcut paylaşımlı client kalıbı, timeout 30 s, retry yok — tekrar hesap pahalı) | `nanobase_api/infrastructure/forecast_client.py` |

### Faz 4 — Benchmark: TimesFM'e güvenmeden önce ölç (1-2 gün)

PDF: "Seasonal Naive'den kötü çıkarsa bunu kabul edeceğiz." Bu V1'in kalite kapısı.

| İş | Ne | Dosya |
|---|---|---|
| 4.1 | Rolling-origin backtest: son 6 ay holdout + 3 kayan origin. Metrikler: **WAPE, sMAPE, RMSE** + **quantile coverage** (p10-p90 gerçekleşenlerin ~%80'ini kapsamalı — anomali sinyali buna dayanacağı için zorunlu) | `backend/forecasting/evaluation/benchmark.py` |
| 4.2 | Dataset'ler: (a) sentetik bi_reporting şube serileri, (b) erp (Neon) gerçek aylık ciro — erp kolonları Türkçe (`durum`), scenario discovery sınıflandırmasını kullan, guess yok | `artifacts/forecast/benchmark-{date}.json` |
| 4.3 | **Kapı:** `FORECAST_ENGINE` varsayılanı benchmark'ı kazanan engine olur; TimesFM 2.5 seasonal naive'i WAPE'de geçemezse prod engine = `seasonal_naive` ve bu belgeye yazılır | `configs/bi.backend.env.example`, bu belge §8 |
| 4.4 | Quality-eval runner'a `forecast` modu (mevcut `run-quality-eval.py` kalıbı) | `tests/text2sql/run-quality-eval.py` |

### Faz 5 — Chat entegrasyonu + FE (1-2 gün)

| İş | Ne | Dosya |
|---|---|---|
| 5.1 | `resolve_forecast_intent(message)` → `{metricCode, dimensionFilters, grain, horizon, historyMonths}` ya da `None`. Tetikleyiciler: "önümüzdeki N ay/hafta", "tahmin", "forecast", "projeksiyon", "gelecek çeyrek". Türkçe ek kuralı: kök + `\b` yok (Ağustos'ta bulunan regex hatası). Horizon çıkarılamazsa → **reddet**, varsayılan 6 uydurma. Çok boyutlu / eşikli sorular LLM'e değil, "desteklenmiyor" mesajına düşer | `nanobase_awel/retrieval/semantic.py` |
| 5.2 | `chat_gateway`: scenario → semantic hook'larından sonra, LLM plan'dan **önce** `forecast` dalı. SSE fazları: `forecast_series_hit` (sql, sql_source=`semantic_metric_compiler`), `forecast_bundle_ready` (n, filled, hash), `forecast_done` (engine, horizon) ya da `forecast_declined` (kod + Türkçe açıklama). `done` payload'ına `forecast` bloğu | `nanobase_api/chat_gateway.py` |
| 5.3 | `result-explain` prompt'una forecast gerçekleri tablo olarak (p50 + aralık + baseline farkı); talimat: "sayı üretme, yorumla". `answer_fidelity_validator` forecast rakamlarını da doğrular | `nanobase_awel/workflows/result_explain.py` |
| 5.4 | FE: `BiChatPanel` forecast bloğu — recharts (zaten lazy) çizgi + `p10-p90` Area bandı, geçmiş/gelecek ayrımı, engine rozeti; i18n `tr/en` | `src/components/BiChatPanel.tsx`, `src/i18n/*.json` |
| 5.5 | bi_meta kalıcılık: `fc_forecast_run` (tenant, datasource, metric_code, dimension_filters jsonb, bundle_hash, engine, engine_version, horizon, benchmark_ref, created_at) + `fc_forecast_point` (run_id, ts, p10, p50, p90). Alembic 0NN | `nanobase_api/alembic/versions/` |

### Faz 6 — Aralık ihlali sinyali + investigation V1 (1 gün)

PDF §11-12: ayrı anomali modeli yok; TimesFM aralığı sinyal, Qwen sebebi DB'den araştırır.

| İş | Ne | Dosya |
|---|---|---|
| 6.1 | Gecelik arq job `run_forecast_reconcile`: gerçekleşen ay kapandığında `fc_forecast_point` ile karşılaştır, `actual > p90` / `< p10` → `interval_violation` işaretle (yalnız coverage benchmark'ı geçen engine için; aksi halde "sinyal güvenilir değil" uyarısı) | `nanobase_api/infrastructure/arq_worker.py` |
| 6.2 | Investigation V1 = **deterministik follow-up seti**: ihlal olan ay için mevcut metriklerle (orders, quantity, returns, segment kırılımı) aynı aya ait sorgular `followUps` olarak sunulur; Qwen bunları "araştırma" olarak sıralar, sayı üretmez. Serbest Qwen araştırma döngüsü V2 | `chat_gateway.py`, `result_explain.py` |

---

## 3. Sonraya bırakılanlar (bilinçli, V2)

- **Multivariate** (Orders/Customers/Returns past-only covariate): TimesFM 2.5'te native yok → V1'de tek değişkenli. 3.0 lisansı çözülürse ya da benchmark'ta 3.0 anlamlı fark gösterirse tekrar ele alınır.
- **Future covariates**: yalnız *bilinen* gelecek — TR resmi tatil takvimi (statik tablo), `budget_lines`'taki planlı indirim/kampanya (repo'da zaten var). Reklam harcaması gibi bilinmeyenler asla LLM'den doldurulmaz.
- **Serbest Qwen investigation** (tool-calling döngüsü).

---

## 4. API sözleşmeleri

**`POST /api/v1/bi/semantic/series`** (Faz 1.3)
```json
{"metricCode":"total_revenue","dimensionFilters":{"branch_city":"İstanbul"},"grain":"month","historyMonths":36}
→ {"metricCode":"total_revenue","metricVersion":2,"grain":"month","sql":"...","rows":[{"period":"2023-09-01","value":8100000}],"sqlSource":"semantic_metric_compiler"}
```

**`POST :8793/forecast`** (Faz 3) — PDF'teki şema, eklerle:
```json
{"series_id":"total_revenue|branch_city=İstanbul","frequency":"M","horizon":6,
 "history":[{"timestamp":"2023-09-01","value":8100000}],
 "target_unit":"TRY","missing_policy":"zero","return_quantiles":true,"bundle_hash":"sha256:…"}
→ {"series_id":"…","engine":"timesfm-2.5-200m","engine_version":"…","checkpoint_sha":"…","bundle_hash":"sha256:…",
   "forecast":[{"timestamp":"2026-09-01","p10":18100000,"p50":19300000,"p90":20700000}],"warnings":[],"latency_ms":840}
```

**Chat SSE** fazları: `forecast_series_hit` → `forecast_bundle_ready` → `forecast_done` | `forecast_declined{code,reason_tr}`.

---

## 5. Test stratejisi

| Katman | Ne | Nerede |
|---|---|---|
| Birim | compiler `time_grain` snapshot'ları (3 dialect), resolver Türkçe ek/horizon çıkarımı, bundle builder property testleri | `semantic_catalog/tests`, `nanobase_awel/tests`, `forecasting/tests` |
| Sözleşme | `nanobase_api` ↔ forecast servisi aynı pydantic paketini import eder; şema drift'i testte yakalanır | `forecasting/contracts` |
| Engine | `NaiveEngine`/`SeasonalNaiveEngine` CI'da model indirmeden; TimesFM testleri `FORECAST_TEST_MODEL=1` ile opt-in | `forecasting/tests/test_engines.py` |
| Gateway | compile edilen grain SQL'i allowlist + EXPLAIN'den repair'e düşmeden geçer (Ağustos'ta yaşanan sınıf) | `query_gateway/tests` |
| Benchmark | rolling-origin, artifact'a yazar, kapı kararı | `artifacts/forecast/` |
| E2E | "İstanbul satışları önümüzdeki 6 ay nasıl?" → `sql_source=semantic_metric_compiler`, `engine=timesfm-2.5`, LLM SQL çağrısı 0; "önümüzdeki ay" (history < 12 olan datasource) → `forecast_declined:INSUFFICIENT_HISTORY` | `tools/release-gate/run_e2e_suite.py` |

---

## 6. Rollout ve geri alma

1. Forecast servisi önce `FORECAST_ENGINE=seasonal_naive` ile canlıya çıkar (model yok, risk yok); chat dalı `FORECAST_CHAT_ENABLED=false`.
2. Benchmark artifact'ı üretilir; kapı geçerse `timesfm25`'e alınır.
3. `semantic_shadow_mode` kalıbıyla forecast dalı önce **shadow** (SSE'de görünür, cevaba girmez), sonra açık.
4. Geri alma: `FORECAST_CHAT_ENABLED=false` → hat aynen bugünkü davranışa döner. Servis bağımsız, `nanobase_api` yeniden başlatılmaz.
5. Yeni view kolonu / metrik yayını sonrası `nanobase-bi-api` restart (katalog boot'ta hydrate olur — bilinen kural).

---

## 7. Riskler

| Risk | Etki | Önlem |
|---|---|---|
| TimesFM 3.0 lisansı | Prod'da kullanılamaz | K4: prod 2.5; 3.0 yalnız benchmark, env kilidi |
| Paylaşımlı host CPU yükü (LA 95-105 görüldü) | Forecast p95 patlar, chat'i geciktirir | Ayrı servis, `CPUQuota`, thread cap, bundle ≤ 120 nokta, sonuç `bundle_hash` ile cache (aynı seri aynı ay → tek hesap) |
| Veri azlığı | Anlamsız tahmin | Sert min-history reddi; sentetik seed yalnız pipeline/benchmark için, "gerçek doğruluk" iddiası erp verisiyle |
| Resolver aşırı tetiklenme ("tahmini maliyet", "tahmin ediyorum ki…") | Yanlış forecast dalı | Horizon ifadesi zorunlu; belirsizlik → reddet, LLM'e de düşmez; korpusa negatif örnekler |
| Allowlist tuzağı | Deterministik SQL sessizce LLM repair'e düşer | Faz 1 kabul testi gateway üzerinden; view kolonu eklerken allowlist kontrolü |
| torch bağımlılığı | `nanobase_api` imajı şişer | Ayrı venv/servis (Faz 3.1), sözleşme paketi saf pydantic |
| Quantile coverage kötü | Anomali sinyali gürültü | Faz 4.1 coverage ölçümü; geçmeyen engine için sinyal kapalı (6.1) |

---

## 7b. Karar güncellemesi — 2026-09-06: prod motoru TimesFM 3.0

Kullanıcı kararı: üretim motoru **TimesFM 3.0** (`FORECAST_ENGINE=timesfm3`), K4'teki "prod = 2.5" satırı bu kararla değişti.

| Ne | Değer |
|---|---|
| Kaynak | https://github.com/google-research/timesfm, commit `0df95ae62085a6ac0d0afd1ad40dee2e6c1356ab` (pip: `backend/forecasting/requirements-timesfm.txt`) |
| Paket / API | `timesfm3` (`ModelConfig(checkpoint_path, per_core_batch_size, device)` → `TimesFM3Evaluator.predict_batch(contexts, horizon, return_quantiles=True)` → `ForecastOutput.forecast`, `.quantiles[horizon, 9]`, seviyeler 0.1..0.9) |
| Ağırlık | `google/timesfm-3.0-pytorch`; sunucuda `/data/nanobaseai/bi/models/timesfm-3.0-pytorch` (1.3 GB), `HF_HUB_OFFLINE=1` |
| Sunucu | venv `/data/nanobaseai/bi/timesfm-venv` (torch CPU), unit `nanobase-forecast.service` :8793, `scripts/server/deploy-forecast.sh`; API bağlantısı `scripts/server/enable-forecast-chat.sh` |
| Lisans | Upstream ağırlıklar ticari olmayan lisanslı; yükleme `FORECAST_ALLOW_NONCOMMERCIAL=1` ile açıkça izinli (operatör kararı) |
| p10/p50/p90 | quantile başlığı indeks 0 / 4 / 8; negatif olmayan seriler 0'da kırpılır (`_clip_floor`) |
| Ölçüm (sunucu, CPU, 60 aylık gerçek Logo serisi) | yükleme 6.5 s, çıkarım 2.4 s (`timesfm-smoke.json`) |

`timesfm25` adaptörü repoda duruyor ama kurulu paketle doğrulanmadı; kullanılmıyor.

## 8. Kabul ölçütleri (ölçülebilir)

- [ ] E2E soru: gateway'e giden SQL `semantic_metric_compiler` kaynaklı, LLM SQL çağrısı **0**, cevapta 6 aylık p10/p50/p90.
- [ ] `artifacts/forecast/benchmark-*.json`: Naive, Seasonal Naive, TimesFM 2.5 (+3.0 offline) için WAPE/sMAPE/RMSE + p10-p90 coverage, iki dataset.
- [ ] Prod engine seçimi benchmark'a yazılı gerekçeyle bağlı (kazanan engine, kaybederse seasonal naive).
- [ ] History < 12 ay → `forecast_declined:INSUFFICIENT_HISTORY`, FE'de görünür Türkçe mesaj.
- [ ] Forecast servisi CPU p95 < 3 s (1 seri, 48 nokta, horizon 6); health `ready` gate'i çalışır.
- [ ] Her `fc_forecast_run` satırı `bundle_hash` + `engine_version` + `metric version` taşır.
- [ ] Tüm backend suite yeşil (bugün 1519) + yeni testler; FE `npm run build` yeşil.

---

## 9. Sıra ve tahmin

| Faz | Süre | Bağımlılık |
|---|---|---|
| 0 Kararlar + veri | 0.5-1 g | — |
| 1 Time grain | 1-2 g | 0.3, 0.4 |
| 2 SeriesBundle | 1 g | — (paralel) |
| 3 Forecast API | 2 g | 2 |
| 4 Benchmark | 1-2 g | 1, 3 |
| 5 Chat + FE | 1-2 g | 1, 2, 3 |
| 6 Sinyal + investigation V1 | 1 g | 5 |
| **Toplam** | **~8-10 iş günü** | |

İlk adım: Faz 0 (K1-K4 onayı + sentetik seed + GPU envanteri) ve Faz 2 aynı gün başlar;
Faz 1 ile 3 paralel yürür. `docker compose up` sonrası E2E sorunun uçtan uca çalışması
Faz 5 sonunda; benchmark kapısı Faz 4'te.
