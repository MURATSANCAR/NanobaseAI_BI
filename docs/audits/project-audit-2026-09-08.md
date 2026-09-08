# Proje hata incelemesi — 8 Eylül 2026

İncelenen commit: `0a785fc`. Kapsam: ana React arayüzü, kokpit, API, semantic katman, Query Gateway, AWEL, senaryo/katalog motorları, tahmin testleri ve kurulum/CI dosyaları.

Bu çalışma geniş bir kod ve yerel test incelemesidir. Canlı müşteri veritabanı, gerçek LLM, Docker/GPU kurulumu ve üretim ağı üzerinde test yapılmadı. Aşağıdaki erişim örneklerinde yalnız bellek içi veritabanı ve sahte yürütücüler kullanıldı. Üretimde istismar gerçekleştiği iddia edilmiyor.

## Öncelikli bulgular

### 1. [P1] Üretim kurulumu anonim istekleri yönetici kabul ediyor

Konum: [docker-compose.yml](/Users/msancar/Documents/GitHub/NonobaseAI-BI/deploy/compose/docker-compose.yml:30), [principal.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/nanobase_api/auth/principal.py:63).

Üretim compose dosyasında `NANOBASE_ENV: production` ile birlikte `AUTH_MODE: ${AUTH_MODE:-dev}` kullanılıyor; kurulumun `.env.example` dosyası da `dev` seçiyor. Bu modda kimlik bilgisi olmayan, hatta doğrulanamayan bearer token taşıyan istek `_dev_principal()` üzerinden `ADMIN`, `DATA_ANALYST`, `DATA_ENGINEER` alıyor. Web servisi varsayılan olarak tüm arayüzlerde 80 portunu yayınlıyor.

**Kanıt:** üretim/dev ortamında gerçek `get_current_principal` bağımlılığına tokensız TestClient isteği: HTTP 200, roller `[ADMIN, DATA_ANALYST, DATA_ENGINEER]`.

**Düzeltme:** üretimde JWT zorunlu olmalı; dev modu üretim başlangıcında reddedilmeli. Kurulum kimlik doğrulaması yapılandırılmadan dış portu açmamalı.

### 2. [P1] Eski Query Gateway uç noktası servis kimlik doğrulamasını atlıyor

Konum: [main.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/query_gateway/main.py:274). Karşılaştırma: [execution.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/query_gateway/api/v1/execution.py:32).

`/internal/v1/queries/execute` servis doğrulaması kullanırken `/api/v1/query/execute` aynı uygulamada hiçbir auth dependency olmadan kayıtlı. `QG_AUTH_REQUIRED=1` bu eski yolu kapatmıyor. Gateway ağına erişebilen bir istemci, kaynak kimliği vererek servis JWT/HMAC kontrolleri olmadan yürütücüye ulaşabiliyor. Compose gateway portunu internete yayınlamıyor; bulgunun erişim önkoşulu gateway ağına ulaşabilmek.

**Kanıt:** `QG_AUTH_REQUIRED=1` altında tokensız istek HTTP 200 döndü ve sahte OData yürütücüsü çağrıldı. Gerçek müşteri sorgusu çalıştırılmadı.

**Düzeltme:** legacy uçları kapatmak veya aynı servis kimliği, imza, replay ve tenant kontrollerinden geçirmek.

### 3. [P1] CTE adı katalog tablo izin listesini aşabiliyor

Konum: [guardrails.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/semantic_layer/runtime/guardrails.py:220).

CTE adları global bir kümeye alınıyor. Aynı ada sahip bütün tablo başvuruları, şemayla nitelenmiş olsalar bile, denetimden çıkarılıyor. Fizikselleştirme de bu adı CTE sanarak değiştirmiyor.

**Yerel yeniden üretim:** katalog yalnız `main.allowed` tablosunu tanıyor; aşağıdaki sorgu `validate_sql=True` ve `allowed_tables=True` alarak katalog dışındaki `main.secret` tablosundaki `audit-canary` değerini döndürdü:

```sql
WITH secret AS (SELECT 1 AS x)
SELECT value FROM main.secret
```

**Etki:** veritabanı hesabının okuyabildiği ancak kataloğun izin vermediği tablolar okunabilir.

**Düzeltme:** isim kümesi yerine SQL scope çözümlemesi; şema/katalog ile nitelenmiş fiziksel tabloyu CTE saymama; parse edilemeyen sorguları izinli kabul etmeme.

### 4. [P1] Benzer soru önbelleği yeni soruya eski filtrenin SQL'ini veriyor

Konum: [learned_query_cache.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/nanobase_api/infrastructure/learned_query_cache.py:471), [chat_gateway.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/nanobase_api/chat_gateway.py:764).

Benzerlik kontrolü dönem ve kelime örtüşmesini kullanıyor. Şehir, durum, müşteri, olumsuzluk gibi semantik kısıtların eşdeğerliği kontrol edilmiyor. Eşik varsayılan olarak 0.55; eşleşen SQL chat yolunda doğrudan seçiliyor.

**Kanıt:** geçmiş soru `İstanbul müşterilerini isimleriyle listele`, yeni soru `Ankara müşterilerini isimleriyle listele`: `match=similar`, `score=0.6`, seçilen SQL hâlâ `WHERE city = 'İstanbul'` içeriyor.

**Düzeltme:** fuzzy eşleşmeyi yalnız aday/few-shot olarak kullanmak; doğrudan çalıştırma için doğrulanmış slot/filtre eşdeğerliği veya güvenli parametreli şablon istemek.

### 5. [P1] Kokpit backend'in reddettiği SQL'i tekrar çalıştırıyor

Konum: [CopilotPanel.tsx](/Users/msancar/Documents/GitHub/NonobaseAI-BI/apps/cockpit/src/components/CopilotPanel.tsx:79), [app.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/semantic_bridge/app.py:535).

Kokpit yalnız `a.sql` alanının varlığına bakıyor. `SQL_INVALID` yanıtlarında SQL tanı amacıyla bulunduğu için bu sorguyu `/api/v1/run_sql` üzerinden tekrar gönderiyor. Bu ikinci uç katalogdaki soru anlamını ve critic kararını taşımıyor; yalnız genel SQL/tablo kontrollerini uyguluyor.

**Kanıt:** bellek içi ERP fixture'ında toptan soru için perakende filtresi taşıyan SQL `/ask` tarafından `SQL_INVALID` ile reddedildi. Aynı yanıtın `sql` alanını `/run_sql`'e göndermek HTTP 200 ve `total=10149.0` döndürdü. Bu, kokpitteki mevcut koşulun yaptığı işlemdir.

**Düzeltme:** yanıt durumunu açıkça kontrol etmek; reddedilen SQL'i yürütülebilir sonuç gibi sunmamak; güvenilir sonuç/izin verilmiş yürütme kimliği kullanmak.

### 6. [P1] Kokpit yeniden çalıştırırken dönem bağlamını kaybediyor

Konum: [CopilotPanel.tsx](/Users/msancar/Documents/GitHub/NonobaseAI-BI/apps/cockpit/src/components/CopilotPanel.tsx:79), [engine.ts](/Users/msancar/Documents/GitHub/NonobaseAI-BI/apps/cockpit/src/lib/engine.ts:94), [app.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/semantic_bridge/app.py:316).

`/ask` SQL'i `_asked_period(sq)` ile çalıştırıyor; yıllara bölünmüş tablolar böylece birleştiriliyor. Kokpit aynı mantıksal SQL'i tekrar `/run_sql`'e gönderiyor, fakat dönem taşımıyor. İkinci yürütme farklı fiziksel tablo seçebiliyor. Özet ilk yürütmeden, tablo ikinci yürütmeden gelebilir. SQL tekrar çalıştırılması ayrıca gereksiz yük oluşturuyor; büyük sonuçlar önbelleğe alınmadığından maliyet yalnız teorik değil.

**Kanıt:** mevcut dönem fixture'larıyla, iki yılın 100 ve 200 değerleri için dönemli yürütme `300`, dönemsiz kokpit tekrarı `100` verdi. İlk SQL iki tabloyu UNION ALL ile birleştirirken ikinci SQL yalnız eski tabloyu okuyor.

**Düzeltme:** `/ask` sonucu doğrudan gösterilmeli veya değişmez yürütme kimliği ve aynı dönem/plan üzerinden sonuç alınmalı. Grafik, tablo, özet, dışa aktarım aynı çalıştırmaya bağlanmalı.

## Diğer doğrulanmış sorunlar

### 7. [P2] Bind dönüşümü string literal içindeki iki noktayı da değiştiriyor

Konum: [bind_params.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/query_gateway/infrastructure/parser/bind_params.py:38).

Regex SQL token türlerini ayırt etmiyor. `SELECT ':status' AS label, :id AS id` için gerçek olmayan `status` parametresi çıkarılıyor; doğrulama SQL'i `SELECT ''x'' AS label, 7 AS id` oluyor. Parametre tamlığı kontrolü geçerli sorguyu eksik parametre diye reddedebilir; dönüştürülmüş sorgu da literal değerini bozabilir.

**Düzeltme:** string, quoted identifier ve yorumları koruyan tokenizer/AST üzerinden yalnız gerçek placeholder'ları dönüştürmek.

### 8. [P2] LLM kapalı modda semantic bridge başlatılamıyor

Konum: [app.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/semantic_bridge/app.py:214), [build_runtime](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/semantic_bridge/app.py:849).

`SEMANTIC_LLM=0` veya `Runtime(..., llm=None)` durumunda `existing=None`; `rebuild()` yine de `existing.selector_mode` okuyor. `SEMANTIC_TABLE_SELECTOR=off` bile AttributeError'ı önlemiyor.

**Kanıt:** gerçek Runtime yapıcısıyla `AttributeError: 'NoneType' object has no attribute 'selector_mode'` üretildi.

**Düzeltme:** LLM'ye bağımlı başlatma adımlarını `existing is not None` ile korumak; deterministik/LLM kapalı başlangıcı entegrasyon testine eklemek.

### 9. [P2] Öğrenilmiş sorgu ID'si tenant/datasource içermiyor

Konum: [learned_query_cache.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/backend/nanobase_api/infrastructure/learned_query_cache.py:347).

ID yalnız soru hash'inden üretiliyor, fakat tablo primary key'i global. Aynı soru başka tenant veya datasource için kaydedildiğinde primary key çakışıyor. ON CONFLICT yalnız `(tenant_id, datasource_id, question_hash)` hedefini kapsadığı için bunu çözmüyor; genel exception yakalama hatayı yutup `None` döndürüyor.

**Kanıt:** aynı sorunun tenant-a kaydı `lq-9393710c589bce97` ile başarılı, tenant-b kaydı `null`. Test bellek içi store ile yapıldı. Bu veri sızıntısı değil, farklı kiracılar/kaynaklar için öğrenmenin sessizce bozulmasıdır.

**Düzeltme:** ID'ye tenant ve datasource katmak veya bağımsız UUID kullanmak; depolama hatasını görünür kılmak.

### 10. [P2] Data-leakage release kontrolü gerçek maskeyi sınamıyor

Konum: [run_data_leakage.py](/Users/msancar/Documents/GitHub/NonobaseAI-BI/tools/release-gate/run_data_leakage.py:48).

Kontrol kendi yerel maskeleme örneklerini değerlendiriyor. Gateway maskesi yalnız import ediliyor, çağrılmıyor; import başarısız olsa bile bu durum `pass_` hesabına katılmıyor. `llmForbiddenRaw` ölçülmeden sabit 0 yazılıyor.

**Kanıt türü:** statik kontrol akışı. Gerçek gateway maskesi bozuk/eksik olduğunda bile, artefakt metin taramasında eşleşme yoksa bu özel kontrol başarılı olabilir. Diğer release kontrollerinin de başarılı olacağı iddia edilmiyor.

**Düzeltme:** üretim masker ve gerçek API/LLM sınırları üzerinde canary verili entegrasyon testi; eksik bağımlılık veya ölçülmeyen kontrolü başarı saymama.

### 11. [P2] CI uygulama değişiklikleri için test güvencesi vermiyor

Konum: [release-gate.yml](/Users/msancar/Documents/GitHub/NonobaseAI-BI/.github/workflows/release-gate.yml:14), [package.json](/Users/msancar/Documents/GitHub/NonobaseAI-BI/package.json:6).

Depodaki workflow yalnız release-gate/test-security yolları değişince push ile tetikleniyor. Ana API, frontend, resolver veya compiler değişiklikleri tek başına bunu çalıştırmıyor; pull_request tetikleyicisi yok. Frontend package.json içinde test komutu ve vitest bağımlılığı da yok.

**Etki:** aşağıdaki mevcut test hazırlık hataları ve uygulama regresyonları normal değişiklik akışında fark edilmeyebilir.

**Düzeltme:** uygulama yolları ve PR'lar için build/unit/integration CI; sabitlenmiş frontend test runner; locale ve event-loop hazırlığını test fixture'larına almak.

## Doğrulama sonuçları

| Kontrol | Sonuç |
|---|---|
| Ana React `npm run build` | Başarılı |
| Kokpit `npm run build` | Başarılı |
| API + katalog + senaryo + gateway + AWEL + forecast | 1596 geçti, 2 başarısız, 2 atlandı |
| Semantic layer | 313 geçti |
| Frontend mevcut testler, yalnız ana checkout | 19 geçti, 5 başarısız |
| Frontend, geçici locale hazırlığıyla | 24 geçti |
| Başarısız backend dosyaları tek başına | 10 geçti |
| Reddedilmiş SQL yeniden yürütme probu | Açık doğrulandı |

Backend toplamı: **1909 başarılı, 2 başarısız, 2 atlanan**. Tekrar koşulan dosyalar bu toplama ikinci kez eklenmedi.

Backend'deki iki başarısız test:

- `backend/nanobase_awel/tests/unit/test_authorized_hint_columns.py::test_hint_includes_grouped_columns_from_hits`
- `backend/nanobase_awel/tests/unit/test_dynamic_sql_quality.py::test_expand_tables_from_index_merges_match`

Her ikisi de tüm pakette `asyncio.get_event_loop()` nedeniyle `There is no current event loop` hatası veriyor, tek başına geçiyor. Bu kanıt test sırasına bağımlı fixture sorunu gösteriyor; tek başına üretim fonksiyonunun bozuk olduğunu göstermiyor.

Frontend başarısızlıkları `biFieldLabel` ve `biKpiSuggestLabel` testlerinde. Lazy locale yüklenmeden senkron çeviri beklentisi kuruluyor. Geçici setup'ta `await loadLocale('tr')` sonrası tüm 24 test geçti. Bunları kullanıcı ekranında kesin çeviri bozukluğu diye sınıflandırmadım. Vitest depoda kurulmadığı için incelemede geçici `vitest@3.2.4` kullanıldı; package dosyaları değiştirilmedi.

İlk frontend taraması `.claude/worktrees` altındaki kopya testleri de buldu; sayılar bunlar dışlanarak yeniden hesaplandı.

Semantic testlerde `SEMANTIC_TABLE_SELECTOR=off` kullanıldı. Varsayılan shadow selector testlerde gerçek LLM adresine bağlanıp beklediği için çevrimdışı çalıştırma aksi halde dış servise bağımlıydı.

## Yeniden çalıştırma

```sh
rtk npm run build
rtk proxy env PYTHONPATH=backend SEMANTIC_TABLE_SELECTOR=off uv run --python 3.11 --with-requirements backend/requirements-semantic.txt -- python -m pytest backend/semantic_layer/tests -q --disable-warnings
rtk proxy env PYTHONPATH=backend SEMANTIC_TABLE_SELECTOR=off uv run --python 3.11 --with-requirements backend/nanobase_api/requirements.txt --with-requirements backend/query_gateway/requirements.txt --with pytest --with pytest-asyncio -- python -m pytest backend/nanobase_api/tests backend/nanobase_api/semantic_catalog/tests backend/nanobase_api/scenario_engine/tests backend/query_gateway/tests backend/nanobase_awel/tests backend/forecasting/tests -q --disable-warnings --tb=short --continue-on-collection-errors
rtk proxy npx --yes --package vitest@3.2.4 vitest run --exclude '.claude/**'
```

Kokpit build komutu `apps/cockpit` çalışma dizininde çalıştırıldı.

**Önerilen düzeltme sırası:** 1–3 erişim kontrolleri; 4–6 yanlış cevap ve reddi atlama; 7–9 çalışma zamanı hataları; 10–11 test/release güvencesi. Canlı golden soru doğruluğu ve model kalitesi bu yerel test sonuçlarından çıkarılamaz.
