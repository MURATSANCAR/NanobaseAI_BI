# Semantic Bridge — kurulum, doğrulama, geri dönüş runbook'u

Hedef: Timaş kokpitinin NL→SQL hattını WrenAI köprüsünden (:8794) Semantic Layer köprüsüne (:8795) taşımak.
Kural: **her adım geri alınabilir**, kesme (nginx anahtarı) en sona ve ayrı komuta bırakılır.

## 0. Erişim ve ön koşullar

| Şey | Kontrol | Not |
|---|---|---|
| SSH | `ssh nanobase-direct 'hostname'` → `NanobaseAI` | `nanobase` alias'ı ProxyJump (`a40legal`) üzerinden **kopuk**; `nanobase-direct` veya `nanobase-cm` kullanın |
| Kod | `/data/nanobaseai/bi/frontend` güncel mi (sunucuda **git yok**, rsync ile gelir) | `rsync -a --delete --exclude node_modules --exclude .git ./ nanobase-direct:/data/nanobaseai/bi/frontend/` |
| Venv | `/data/nanobaseai/bi/semantic-venv` (script kurar) | üretim API'sinin venv'ine **dokunulmaz**; pyodbc yalnız köprü venv'inde |
| Alembic | mevcut head `013_forecast_runs` | 014 temiz uygulanır |
| Bağlantı dosyası | `/data/nanobaseai/bi/secrets/logo-mssql-connection.json` (mod 600) | MSSQL/FreeTDS salt-okunur kullanıcı |
| Meta DB | `bi_meta` PostgreSQL 127.0.0.1:5434 erişilebilir | alembic 014 buraya yazar |
| Kapsam | `SEMANTIC_TABLE_LIKE` bilinçli verilmiş | boş bırakılırsa tüm şema taranır (aşağıya bak) |

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
# 0) kodu gönder (iş istasyonundan)
rsync -a --delete --exclude node_modules --exclude .git --exclude dist ./ nanobase-direct:/data/nanobaseai/bi/frontend/

# 1) kur (sunucuda) — kapsam verilmezse betik durur
ssh nanobase-direct
cd /data/nanobaseai/bi/frontend
SEMANTIC_TABLE_LIKE='LG_411_%' SEMANTIC_SCHEMA=dbo ./scripts/server/deploy-semantic-bridge.sh

# 2) portal sayfası yeni router'ı görsün (ÜRETİM API yeniden başlar — bilinçli adım)
sudo systemctl restart nanobase-bi-api
```

Sırasıyla: kapsam koruması → bağlantı dosyası (yoksa `mssql-ro.datasources.json`'dan türetilir, mod 600) →
ayrı venv + bağımlılıklar → `alembic upgrade head` (014) → env dosyası → offline pipeline (profil →
madencilik → doküman → sertifikasyon → katalog v1) → `nanobase-semantic-bridge.service` (:8795) → gece
worker + timer → health/engine/ask smoke (SQL üretmezse betik durur). **Trafik çevrilmez.**

## 2b. Bütçeler (canlı bir kaynağa karşı çalışırken)

Boru hattı canlı ERP'ye sorgu atar; her adımın duvar saati vardır ve bütçesi dolduğunda **durur, susmaz**:
ne yapılamadığı loga yazılır, kısmi tarama tam tarama gibi görünmez.

| Değişken | Varsayılan | Ne yapar |
|---|---|---|
| `SEMANTIC_DEEP_TABLES` | 40 | kaç tabloya değer envanteri + örnek satır + zaman penceresi çıkarılır |
| `SEMANTIC_DEEP_BUDGET_SEC` | 1800 | derin profil aşamasının duvar saati; aşılırsa kalan tablolar kataloglanır ama sondalanmaz |
| `SEMANTIC_PROBE_BUDGET_SEC` | 900 | değer dağılımı + ölçü çalıştırma aşaması; sondalanmayan kavram eski durumunu korur |
| `SEMANTIC_FRESHNESS_BUDGET_SEC` | 300 | tazelik taraması (tablo başına tek tarama) |
| `SEMANTIC_QUERY_TIMEOUT_SEC` | 120 | tek bir sorgunun üst sınırı; yavaş kaynakta 45 iyi bir başlangıç |
| `SEMANTIC_PROMPT_TABLES` / `SEMANTIC_PROMPT_COLUMNS` | 12 / 60 | modelin bağlamına sığdırılacak tablo/kolon sayısı (300 tablolu şema prompta sığmaz) |
| `SEMANTIC_GATE_STRICT` | 1 | yeni katalog eskisinden geri çıkarsa dağıtımı durdurur; `0` yalnız uyarır |

İlerleme loga tablo tablo yazılır (`profiled <tablo> (n/m, k kolon, s sn)`), yani takıldı mı çalışıyor mu
bakmak için `tail -f` yeterlidir.

## 3. Doğrulama kapıları (hepsi geçmeden kesme yok)

```bash
set -a; . /etc/nanobase/semantic-bridge.env; set +a      # DSN, kapsam ve LLM ayarları buradan gelir
VENV=/data/nanobaseai/bi/semantic-venv

curl -s 127.0.0.1:8795/health                                   # profiles > 0, catalog CERTIFIED > 0
curl -s 127.0.0.1:8795/api/v1/engine                            # deployed:true, catalogVersion >= 1
curl -s 127.0.0.1:8795/api/v1/llm/queue                          # model kuyruğu: kim çalışıyor, kim bekliyor
PYTHONPATH=backend $VENV/bin/python -m semantic_layer.cli status  # sertifikalı kavramlar, sürüm

# cold-start dilimleri + gerçek sonuç karşılaştırması (recall OFF, LLM istisna)
PYTHONPATH=backend $VENV/bin/python tests/text2sql/semantic-coldstart-eval.py \
  --store "$SEMANTIC_STORE_DSN" --bridge http://127.0.0.1:8795 \
  --truth artifacts/timas/complex-truth.json --out artifacts/timas/coldstart-server.json

# mevcut hatla aynı korpusta karşılaştırma (kesme kararının dayanağı)
PYTHONPATH=backend $VENV/bin/python tests/text2sql/compiler-ab-eval.py \
  --store "$SEMANTIC_STORE_DSN" --compilers deterministic,existing_llm \
  --bridge http://127.0.0.1:8795 --truth artifacts/timas/complex-truth.json \
  --out artifacts/timas/compiler-ab-server.json

```

Kesme kriteri: `result` dilimi kabul edilebilir ve `behaviour` (SQL üretmesi gerekende üretiyor, reddetmesi
gerekende reddediyor) tam. Ölçümler `artifacts/timas/` altına yazılır.

## 4. Kesme (ayrı komut, tek satırla geri alınır)

```bash
./scripts/server/switch-timas-api.sh semantic --dry-run   # hangi location'lar değişecek, önce göster
./scripts/server/switch-timas-api.sh semantic             # /timas/api* bloklarının HEPSİ → :8795
```

Betik değişiklikten önce yapılandırmayı `/etc/nginx/backups/` altına yedekler, `nginx -t` başarısızsa
otomatik geri alır ve sonunda geri dönüş komutunu yazdırır:
`sudo cp /etc/nginx/backups/portal.nanobase.ai.bak-<zaman> /etc/nginx/sites-enabled/portal.nanobase.ai && sudo nginx -s reload`.

Not: site dosyasında `/timas/api/` yanında ayrı `~ ^/timas/api/v1/ask(_agent)?$` location'ları vardır;
yalnız birini çevirmek kokpiti iki motora birden konuşturur — betik hepsini birlikte çevirir.

Kesme anında kokpitteki açık `threadId`'ler yeni süreçte boştur (konuşma bağlamı sıfırlanır, veri kaybı yok).

## 5. Geri dönüş / olay müdahalesi

| Belirti | Aksiyon |
|---|---|
| Yanlış/boş cevaplar | `SEMANTIC_STRICT_MISS=1` ile köprüyü yeniden başlat (çözümlenemeyen terimde SQL üretmez) ve `sl_query_log`'dan hatalı soruları incele |
| Katalog bozulması (gece worker sonrası) | Aşağıdaki "katalog geri alma" yordamı |
| ERP yükü | `nanobase-semantic-worker.timer` durdur (`systemctl disable --now`), kapsamı daralt, tekrar profil al |
| Migrasyon geri alma | `alembic downgrade 013_forecast_runs` (sl_* tabloları düşer; portal sayfası boş görünür, üretim API'si etkilenmez) |
| Servis çökmesi | `journalctl -u nanobase-semantic-bridge -n 200`; unit `Restart=always` |

## 5b. Katalog neyi bilmiyor (portalin iş kuyruğu)

Köprü, cevapladığı her soruda yerleştiremediği terimleri kaydeder. Bunları okumak için:

```bash
curl -s 127.0.0.1:8795/api/v1/semantic/gaps?days=30 | python3 -m json.tool | head -40
```

`undefined` = kimsenin tanımlamadığı bir sözcük, `qualifier` = konuyu daraltan ama karşılığı olmayan bir
niteleyici ("bekleyen siparişler"). Aynı liste portalde `/bi/semantic-layer` sayfasının başında görünür;
oradan ilgili tabloya/kolona açıklama girmek terimi kanıt katmanına ekler ve bir sonraki sertifikasyonda
kavram olur. `unmeasuredWindows` alanı, zaman penceresi ölçülemeyen varlıkları söyler — o varlıklarda
dönem kapsamı kontrolü kapalıdır.

## 6. Kurulum sonrası

- Portal `/bi/semantic-layer`: tespit edilen tablolar/kolonlar, sertifikalı anlamlar, tanımsız kolonlara
  kullanıcı açıklaması; "sertifikasyonu çalıştır" ve "profili yenile" düğmeleri.
- Gece 02:00 worker: profil → madencilik → (LLM adayları) → sertifikasyon → sürüm; ardından köprüye `reload`.
- Kokpitten gelen "doğru" geri bildirimi (`/api/v1/feedback`) doğrulanmış çift havuzuna yazar; ertesi gece
  madencilik bunu kanıt olarak kullanır → katalog kendi kendine büyür.

## 7. Katalog yedeği ve geri alma

Katalog `bi_meta` içindeki `sl_*` tablolarıdır; sürüm geçmişi `sl_catalog_version` içinde durur.

```bash
# günlük yedek (cron/timer ile alınmalı)
PGPASSWORD="$(cat /data/nanobaseai/bi/secrets/bi-meta-db.password)" \
  pg_dump -h 127.0.0.1 -p 5434 -U bi_meta -d bi_meta \
  -t 'sl_*' -Fc -f /data/backups/semantic/sl-$(date +%Y%m%dT%H%M%S).dump

# son iyi sürümü görmek
psql ... -c "select version, certified_count, note, created_at from sl_catalog_version order by version desc limit 10"

# hızlı geri alma (sertifikaları eski sürümün anlık görüntüsüne döndürür)
PYTHONPATH=backend $VENV/bin/python -m semantic_layer.cli restore-version --version <N>

# tam geri alma (yedekten)
PGPASSWORD=... pg_restore -h 127.0.0.1 -p 5434 -U bi_meta -d bi_meta --clean --if-exists \
  -t 'sl_*' /data/backups/semantic/sl-<zaman>.dump
```

Geri alma sonrası köprüler kataloğu kendiliğinden fark eder (her işçi sürüm numarasını periyodik okur);
beklemek istemezseniz `curl -X POST -H "X-Semantic-Admin: $SEMANTIC_ADMIN_TOKEN" 127.0.0.1:8795/api/v1/semantic/reload`.
