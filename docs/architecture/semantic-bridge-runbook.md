# Semantic Bridge — kurulum, doğrulama, geri dönüş runbook'u

Hedef: Timaş kokpitinin NL→SQL hattını WrenAI köprüsünden (:8794) Semantic Layer köprüsüne (:8795) taşımak.
Kural: **her adım geri alınabilir**, kesme (nginx anahtarı) en sona ve ayrı komuta bırakılır.

## 0. Erişim ve ön koşullar

| Şey | Kontrol | Not |
|---|---|---|
| SSH | `ssh nanobase-direct 'hostname'` → `NanobaseAI` | `nanobase` alias'ı ProxyJump (`a40legal`) üzerinden **kopuk**; `nanobase-direct` veya `nanobase-cm` kullanın |
| Repo | `/data/nanobaseai/bi/frontend` (bu depo) güncel mi | deploy script `ROOT` olarak kendi konumunu kullanır |
| Venv | `/data/nanobaseai/bi/frontend/backend/.venv` | nanobase_api ile **paylaşımlı** — bağımlılık çakışması riski (aşağıya bak) |
| Bağlantı dosyası | `/data/nanobaseai/bi/secrets/wren-logo-connection.json` (mod 600) | MSSQL/FreeTDS; wren köprüsüyle aynı dosya |
| Meta DB | `bi_meta` PostgreSQL 127.0.0.1:5434 erişilebilir | alembic 014 buraya yazar |
| Mevcut hat | `:8794` sağlıklı (geri dönüş hedefi) | `curl -s 127.0.0.1:8794/health` |

## 1. Kapsam kararı (dağıtımdan önce cevaplanmalı)

Profiler **canlı ERP'yi tarar**. Kapsam boş bırakılırsa `dbo` şemasındaki tüm tablolar (Logo'da 1000+)
taranır; her düşük kardinaliteli kolon için `GROUP BY` çalışır. Bu üretimde kabul edilemez.

```bash
# .env'e yazılacak kapsam — firma/dönem tablolarıyla sınırla:
SEMANTIC_SCHEMA=dbo
SEMANTIC_TABLE_LIKE=LG_411_%      # boş bırakma
```

Not: kod tarafında Logo'ya özgü hiçbir sabit yok; kapsam **operatör ayarıdır**, kurulumda bilinçli verilir.

## 2. Kurulum (idempotent, servisi ayağa kaldırır ama trafiği çevirmez)

```bash
ssh nanobase-direct
cd /data/nanobaseai/bi/frontend
SEMANTIC_TABLE_LIKE='LG_411_%' SEMANTIC_SCHEMA=dbo ./scripts/server/deploy-semantic-bridge.sh
```

Sırasıyla: bağımlılıklar → `alembic upgrade head` (014_semantic_layer) → offline pipeline (profil → madencilik →
doküman → sertifikasyon → katalog v1) → `nanobase-semantic-bridge.service` (:8795) → gece worker timer'ı →
health + tek soruluk smoke.

## 3. Doğrulama kapıları (hepsi geçmeden kesme yok)

```bash
curl -s 127.0.0.1:8795/health                                   # profiles > 0, catalog CERTIFIED > 0
curl -s 127.0.0.1:8795/api/v1/engine                            # deployed:true, catalogVersion >= 1
PYTHONPATH=backend .venv/bin/python -m semantic_layer.cli status # sertifikalı kavramlar, sürüm

# cold-start dilimleri + gerçek sonuç karşılaştırması (recall OFF, LLM istisna)
PYTHONPATH=backend .venv/bin/python tests/text2sql/semantic-coldstart-eval.py \
  --store "$NANOBASE_META_DSN" --bridge http://127.0.0.1:8795 \
  --truth artifacts/timas/complex-truth.json --out artifacts/timas/coldstart-server.json

# mevcut hatla aynı korpusta karşılaştırma (kesme kararının dayanağı)
PYTHONPATH=backend .venv/bin/python tests/text2sql/compiler-ab-eval.py \
  --store "$NANOBASE_META_DSN" --compilers deterministic,existing_llm \
  --bridge http://127.0.0.1:8795 --truth artifacts/timas/complex-truth.json \
  --out artifacts/timas/compiler-ab-server.json

# incumbent referansı: aynı korpus :8794 üzerinde
PYTHONPATH=backend python3 tests/text2sql/timas-copilot-eval.py --bridge http://127.0.0.1:8794 \
  --corpus tests/text2sql/timas-copilot-complex.json --truth artifacts/timas/complex-truth.json \
  --out artifacts/timas/wren-baseline.json
```

Kesme kriteri: yeni hat, `result` diliminde eski hattın **altında değil** ve gecikmede belirgin kazanç var.

## 4. Kesme (ayrı komut, tek satırla geri alınır)

```bash
./scripts/server/switch-timas-api.sh semantic      # nginx /timas/api/ → :8795
# geri dönüş:
./scripts/server/switch-timas-api.sh bridge        # → :8794 (WrenAI köprüsü)
```

Kesme anında kokpitteki açık `threadId`'ler yeni süreçte boştur (konuşma bağlamı sıfırlanır, veri kaybı yok).

## 5. Geri dönüş / olay müdahalesi

| Belirti | Aksiyon |
|---|---|
| Yanlış/boş cevaplar | `switch-timas-api.sh bridge` (saniyeler), sonra `sl_query_log`'dan hatalı soruları incele |
| Katalog bozulması (gece worker sonrası) | `sl_catalog_version` son iyi sürüme bak; `semantic_layer.cli certify` yeniden koş; gerekiyorsa `SEMANTIC_MIN_SUPPORT` yükselt |
| ERP yükü | `nanobase-semantic-worker.timer` durdur (`systemctl disable --now`), kapsamı daralt, tekrar profil al |
| Migrasyon geri alma | `alembic downgrade 013_forecast_runs` (sl_* tabloları düşer; portal sayfası boş görünür, üretim API'si etkilenmez) |
| Servis çökmesi | `journalctl -u nanobase-semantic-bridge -n 200`; unit `Restart=always` |

## 6. Kurulum sonrası

- Portal `/bi/semantic-layer`: tespit edilen tablolar/kolonlar, sertifikalı anlamlar, tanımsız kolonlara
  kullanıcı açıklaması; "sertifikasyonu çalıştır" ve "profili yenile" düğmeleri.
- Gece 02:00 worker: profil → madencilik → (LLM adayları) → sertifikasyon → sürüm; ardından köprüye `reload`.
- Kokpitten gelen "doğru" geri bildirimi (`/api/v1/feedback`) doğrulanmış çift havuzuna yazar; ertesi gece
  madencilik bunu kanıt olarak kullanır → katalog kendi kendine büyür.
