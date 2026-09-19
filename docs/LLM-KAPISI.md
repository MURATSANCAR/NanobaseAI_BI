# LLM kapısı — çok modül, tek model

Projede modele ihtiyaç duyan her modül (soru hattı, sohbet, raporlar, özet, sözlük, dil havuzu, ileride eklenecekler) aynı sağlayıcıya gider. Hepsi aynı anda prompt gönderdiğinde kimsenin zaman aşımına düşmemesi, kimsenin reddedilmemesi ve birinin diğerlerini aç bırakmaması bu katmanın işidir.

Kod: `backend/semantic_layer/runtime/llm_queue.py` (sıra), `runtime/llm_jobs.py` (bırakılan işler), `candidates/llm_client.py` (sağlayıcı çağrısı), uçlar `backend/semantic_bridge/app.py`.

## İki giriş

| Kim | Nasıl | Ne olur |
|---|---|---|
| Köprü sürecinin içindeki kod | `rt.llm_for("modül").chat(messages)` | Sıra gelene kadar bekler, cevabı döner. Çağıran kod değişmez. |
| Başka servis, tarayıcı, uzun bağlantı tutmaması gereken her modül | `POST /api/v1/llm/jobs` | Anında `202 + id`. Cevap sonra sorulur. Bağlantı saniyeler içinde kapanır; zaman aşımı yaşanacak bir bağlantı kalmaz. |

İki giriş de **aynı tek sıradan** geçer (`sl_llm_queue`); modele aynı anda giden çağrı sayısı tek yerden belirlenir.

```
modül A ─┐                          ┌─ slot 1 ─┐
modül B ─┼─► sl_llm_job ─► işleyici ─┤          │
servis  ─┘   (202 + id)             │  sıra    ├─► LlmClient ─► sağlayıcı
köprü içi kod ─────────────────────►│ (öncelik,│      │
gece betikleri (ayrı süreç) ───────►│  adalet) │      └─ 429/503/504/529 ─► sl_llm_gate
                                    └─ slot N ─┘         (herkes birlikte yavaşlar)
```

## Sıranın kuralları

- **Öncelik:** `0` biri ekranda bekliyor · `1` yakında okunacak (planlı rapor) · `2` kimse beklemiyor (arka plan). Amaç adıyla da söylenir: `bg:<modül>` = 2, `std:<modül>` = 1, diğerleri 0.
- **Ayrılmış slot:** son `reserve` slot yalnız öncelik 0 içindir (varsayılan slotların çeyreği; tek slotta 0). Arka plan modeli doldurabilir ama tamamını alamaz.
- **Modüller sırayla:** aynı öncelikte boşalan slot önce en az slot tutan, sonra en uzun süredir hizmet almamış modüle gider; modül içinde geliş sırası korunur. Bir modülün 100 prompt'u diğerlerini 100 çağrı bekletmez.
- **Koşan kayıt kalp atışıyla yaşar** (10 sn'de bir, 60 sn sessizlikte terk). Eskiden 900 sn'lik kiralamayla yargılanıyordu; çağrı süresi 3600 sn olduğu için bir haftada 26 kayıt çağrısı sürerken terk edilmiş sayılmış, her biri slot sınırının üstünde bir çağrıya yol açmıştı.
- **Sağlayıcı "doluyum" derse** (429/503/504/529) bu bilgi `sl_llm_gate` üzerinden bütün süreçlerle paylaşılır: kabul kısa süre durur (sağlayıcının `Retry-After`'ı ya da 5 sn·2ⁿ, en çok 120 sn), slot sayısı yarıya iner; çağrılar başarılı oldukça 30 sn'de bir slot geri gelir. Aynı saniyede gelen sekiz ret tek olay sayılır. Bu yüzden kimsenin sorusu düşmez — bekler.
- **Kabul atomiktir:** PostgreSQL'de `pg_advisory_xact_lock`; iki süreç aynı boş slotu göremez.
- Slot boşaldığında aynı süreçteki bekleyenler anında uyandırılır (eskiden 5 sn'ye kadar boş duruyordu).
- Sayı tavanı yoktur: kimse reddedilmez. `SEMANTIC_LLM_MODULE_MAX` yalnız istenirse modül başına tavan koyar (varsayılan 0 = yok).

## Bırakılan işler (`/api/v1/llm/jobs`)

```bash
# bırak
curl -s -X POST localhost:8795/api/v1/llm/jobs -H 'content-type: application/json' -d '{
  "module": "stok-analizi", "priority": "normal",
  "messages": [{"role": "user", "content": "…"}], "maxTokens": 1200 }'
# → 202 {"id": "llmjob_…", "status": "QUEUED", "phase": "kapıda", "position": 3, "deduplicated": false}

curl -s "localhost:8795/api/v1/llm/jobs/llmjob_…?wait=25"     # kapanana ya da 25 sn'ye kadar bekler (en çok 300)
curl -sN localhost:8795/api/v1/llm/jobs/llmjob_…/events       # satır satır JSON: durum/sıra değişimi, 15 sn'de kalp atışı, en sonda kapanmış iş
curl -s -X DELETE localhost:8795/api/v1/llm/jobs/llmjob_…     # iptal (bekleyen ya da koşan)
```

- Alanlar: `module` (zorunlu), `priority` (`interactive|normal|batch` ya da `0|1|2`, varsayılan `normal`), `messages`, `maxTokens` (4096), `temperature` (0), `dedup` (true), `cacheTtlSec` (0).
- Durumlar: `QUEUED → RUNNING → DONE | FAILED | CANCELLED`. `phase`: `kapıda` → `model sırasında` → `modelde`.
- **Kalıcı:** iş, çağırana "kabul" denmeden önce katalog veritabanına yazılır. Köprü yeniden başlarsa iş kaybolmaz; işleyicisi ölen iş 60 sn sonra sıraya döner, üç kez ölürse `FAILED` olur ve nedenini söyler. Düzgün kapanışta koşan işler deneme hakkı yanmadan sıraya döner.
- **Tekilleştirme:** aynı kullanıcı + aynı modül + aynı model + aynı prompt uçuştayken ikinci gönderim aynı işi döner. Kullanıcı anahtarın parçasıdır: iki kişinin aynı sorusu iki ayrı iştir, cevabı yalnız soran (ya da yönetici / servis çağıranı) okur. `cacheTtlSec` verilirse bitmiş iş de o süre içinde yeniden kullanılır.
- İşleyici iş parçacığı sayısı slot + 2; bir kısmı (slot/4, en az 1) yalnız öncelik 0 alır — arka plan yığını bütün iş parçacıklarını tutamaz.
- Kapanmış işler silinmez (`SEMANTIC_LLM_JOB_KEEP_DAYS=0`); gün sayısı verilirse o kadar eski olanlar temizlenir.

## Durum

`GET /api/v1/llm/queue` → `slots`, `effectiveSlots`, `reservedForInteractive`, `cooldownUntil`, `lastPressure`, modül başına koşan/bekleyen, sıra, `jobs` (kapıdaki/işleyicideki iş sayıları, `runnerAlive`).

## İstemci (`LlmClient`)

- Ret ve geçici hatalarda jitter'lı bekleme (aynı anda reddedilen çağrılar aynı anda geri gelmez), `Retry-After`'a uyar, yükü sıraya bildirir.
- Bütün cevap için tek süre sınırı (eskisi gibi), iptal edilebilir çağrı.
- `LLM_STREAM=1` ile akışlı çağrı (varsayılan kapalı); `LLM_STREAM_IDLE_SEC` iki parça arası en uzun sessizlik (0 = bütün süre).

## Ayarlar

| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `SEMANTIC_LLM_SLOTS` | 1 (canlıda 8) | aynı anda modele giden çağrı |
| `SEMANTIC_LLM_INTERACTIVE_RESERVE` | slot/4 | yalnız öncelik 0'a ayrılan slot |
| `SEMANTIC_LLM_MODULE_MAX` | 0 | modül başına tavan (0 = yok) |
| `SEMANTIC_LLM_JOBS` | 1 | işleyiciyi bu süreçte çalıştır |
| `SEMANTIC_LLM_JOB_WORKERS` / `…_INTERACTIVE_WORKERS` | slot+2 / slot/4 | işleyici iş parçacıkları |
| `SEMANTIC_LLM_JOB_KEEP_DAYS` | 0 | kapanmış işleri tutma süresi (0 = silme) |
| `SEMANTIC_THREADPOOL` | 200 | köprünün eşzamanlı istek iş parçacığı (eskisi 40: 40 bekleyen prompt'tan sonra `/health` de sıraya giriyordu) |
| `LLM_STREAM`, `LLM_STREAM_IDLE_SEC` | kapalı, 0 | akışlı çağrı |

## Yeni bir modül eklerken

1. Köprü içindeyse: `rt.llm_for("modul-adi")` (arka plan işiyse `rt.llm_for("modul-adi", BATCH)`). Doğrudan `LlmClient(...)` kurup çağırmayın — sırayı atlar, slot sınırını deler.
2. Ayrı süreç/betikse: `QueuedLlm(LlmClient(...), LlmQueue.from_env(store.engine), purpose="bg:modul-adi")`.
3. Ayrı servis/arayüzse: `/api/v1/llm/jobs`.

## Testler

`semantic_layer/tests/test_llm_queue.py`, `test_llm_gate.py`, `test_llm_jobs.py`, `test_llm_client_http.py`. `LLM_GATE_TEST_DSN` verilirse sıra ve iş testleri gerçek PostgreSQL'de, kendi şemalarında koşar (advisory lock, `SKIP LOCKED`, eşzamanlı tekilleştirme yalnız orada sınanır). Gerçek kabul kayıtları: [docs/GELISTIRME-GUNLUGU.md](GELISTIRME-GUNLUGU.md) 2026-09-17 «LLM kapısı».
