# Timaş Finans (/timas) — üretim işletme notu (2026-09-06)

## Erişim ve koruma

| Konu | Durum |
|---|---|
| Kimlik doğrulama | nginx HTTP Basic, kullanıcı `timas`; parola dosyası **`/data/nanobaseai/bi/secrets/timas-portal.password`** (sunucuda, 600). `/timas/` ve `/timas/api/` kimliksiz **401** |
| Hız sınırı (IP başına) | `/timas/api/v1/ask` ve `/ask_agent`: 6 istek/dk, patlama 3 → sonrası **429** · `/timas/api/`: 120/dk, patlama 30 |
| MCP | 127.0.0.1:8090, yalnız loopback; dışarıdan SSH tüneliyle |
| Betik | `scripts/server/deploy-timas-auth.sh` (idempotent; parola yoksa üretir, `openssl passwd -apr1`) |

Parolayı değiştirmek: dosyayı düzenle, betiği tekrar koş.

## Eşzamanlılık ve performans

| Katman | Ayar | Etki |
|---|---|---|
| Köprü (`nanobase-wren-bridge`) | uvicorn **3 işçi**, işçi başına ayrı engine + pyodbc + LanceDB | Dashboard 6 paralel sorgu: 8,6 s → 1,9 s |
| Önbellek | **Redis** `redis://127.0.0.1:6379/2`, anahtar `wren:sql:<sha256>`, TTL 300 s, işçiler arası paylaşımlı; Redis yoksa süreç-içi | Aynı SQL 5 dk boyunca Logo'ya gitmez (`cached: true`) |
| LLM (A40 `nanobaseai-bi-llm`) | `PARALLEL=2`, `CTX_SIZE=32768` → slot başına 16.384 (istem 2,6-4,1k) | İki soru aynı anda; VRAM 39,5 GB (değişmedi) |
| BI API | `MODEL_MAX_CONCURRENCY=2` (LLM slot sayısıyla aynı olmalı) | |
| SQL zaman aşımı | Profilde `statement_timeout: "120"` (string!) | Ağır sorgu 120 s'de kesilir |
| Strict mode | `~/.wren/config.json` — manifest dışı tablo ve tehlikeli fonksiyonlar reddedilir | |

WrenAI'nin `cached: true` / `refresh_time` alanları wren-core-py 0.7.6'da yalnız şema düzeyinde var, yürütmede etkisiz — bu yüzden önbellek köprüde.

## İzleme, log, yedek, regresyon

| Birim | Zamanlama | Ne yapar |
|---|---|---|
| `nanobase-wren-watchdog.timer` | 2 dk | köprü /health + gerçek sorgu, MCP initialize, forecast, memory-watch, nginx 401, **Logo tüneli** → sağlıksızsa restart; `/data/logs/wren-watchdog.{log,state}`; `WREN_ALERT_WEBHOOK` (`/etc/nanobaseai/wren-watchdog.env`) tanımlanırsa Slack/Teams'e yazar |
| `nanobase-wren-eval.timer` | her gece 03:30 | `tests/text2sql/timas-copilot-eval.py`: 10 karmaşık soru → köprü → ham DB gerçeğiyle karşılaştır; `logs/copilot-eval-YYYYMMDD.json`, hata → journal `wren-eval` |
| `nanobase-wren-backup.timer` | her gece 03:00 | `backups/wren-project-YYYYMMDD.tgz` (MDL + knowledge), 14 gün saklanır |
| `nanobase-wren-memory-watch` | sürekli | knowledge/MDL değişince indeks |
| logrotate `/etc/logrotate.d/nanobase-wren` | haftalık, 8 kopya | `bi/logs/*.log`, watchdog logu |
| journald | `SystemMaxUse=2G` | servis logları (uvicorn/wren) |

Betik: `scripts/server/deploy-wren-ops.sh` (idempotent).

## Müşteri tarafında yapılması gerekenler (bizim yapamayacaklarımız)

### 1. Logo veritabanına kalıcı erişim
Bugün Logo'ya erişim **senin Mac'inden açılan ters SSH tüneliyle** (`ssh -N -R 127.0.0.1:14330:192.168.0.155:1433 nanobase`). Mac uyursa veya kapanırsa `/timas` tamamen durur; watchdog bunu `logo-tunnel:FAIL` olarak raporlar ama düzeltemez. Seçenekler:
- **Tercih:** müşteri ağında sabit bir makineden (Logo sunucusunun kendisi olabilir) `autossh` ile kalıcı ters tünel + systemd; anahtar tabanlı, yalnız port yönlendirme yetkili kullanıcı.
- Alternatif: site-to-site VPN (WireGuard) — `wren-logo-connection.json` içindeki `host/port` VPN adresine çevrilir, başka değişiklik gerekmez.
- Alternatif: on-prem kurulum (`deploy/compose`), tünel gerekmez.

### 2. Veritabanı kullanıcısı
Mevcut login **sysadmin + db_owner** (doğrulandı: `IS_SRVROLEMEMBER('sysadmin')=1`). Gereken tek yetki `db_datareader`:
```sql
USE [LOGO_DB];
CREATE LOGIN [nanobase_ro] WITH PASSWORD = '<güçlü parola>', CHECK_POLICY = ON;
CREATE USER  [nanobase_ro] FOR LOGIN [nanobase_ro];
ALTER ROLE db_datareader ADD MEMBER [nanobase_ro];
-- isteğe bağlı: yalnız 411 firması tablolarına
-- GRANT SELECT ON SCHEMA::dbo TO [nanobase_ro];
```
Sonra bizde: `secrets/wren-logo-connection.json` + `mssql-ro.datasources.json` içindeki `user/password_file` güncellenir, `wren profile add logo-tunnel --from-file …`, köprü + MCP restart. Sohbette paylaşılmış olan mevcut parola **döndürülmeli**.
