# Timaş Finans (/timas) — üretim işletme notu (2026-09-06)

## Erişim ve koruma

| Konu | Durum |
|---|---|
| Kimlik doğrulama | 2026-09-14'ten beri **Timaş Active Directory** (kişinin kendi Windows hesabı). `timas-login` (:8796) oturum çerezi verir, nginx `auth_request` ile denetler; `/timas/api/` oturumsuz **401**. Demo hesabı, davet bağlantısı ve HTTP Basic yok. Ayrıntı: [portal-login README](../../scripts/server/portal-login/README.md) |
| Hız sınırı (IP başına) | `/timas/api/v1/ask` ve `/ask_agent`: 6 istek/dk, patlama 3 → sonrası **429** · `/timas/api/`: 120/dk, patlama 30 · `/timas/auth/`: 20/dk, patlama 10 |
| AD ayarı | `/etc/nanobase/timas-ad.json` (root:www-data, 0640; repo'ya girmez). DC `192.168.0.20:389` sunucunun VPN'i (`tun0`) üzerinden; VPN kapalıysa giriş 503 |

## Eşzamanlılık ve performans

| Katman | Ayar | Etki |
|---|---|---|
| Köprü (`nanobase-semantic-bridge`, :8795) | uvicorn **2 işçi**, işçi başına ayrı katalog + pyodbc bağlantısı | Dashboard paralel sorguları tek köprüden |
| Önbellek | Köprü içinde, TTL **300 s**, 15 s'de bir arka planda tazelenir (`/health` → `cache`) | Aynı SQL 5 dk boyunca Logo'ya gitmez (`cached: true`) |
| LLM (NVIDIA hosted `deepseek-ai/deepseek-v4-flash-0731`) | OpenAI uyumlu, `thinking:false`; `OPENAI_API_BASE=https://integrate.api.nvidia.com/v1` | Yerel GPU yok; model dışarıdan sorulur, yanıt ~2-5 sn |
| BI API | `MODEL_MAX_CONCURRENCY=2` (LLM slot sayısıyla aynı olmalı) | |
| SQL zaman aşımı | Profilde `statement_timeout: "120"` (string!) | Ağır sorgu 120 s'de kesilir |
| Strict mode | `SEMANTIC_STRICT_MISS` — katalogda CERTIFIED karşılığı olmayan soru cevaplanmaz | |

## İzleme, log, yedek, regresyon

| Birim | Zamanlama | Ne yapar |
|---|---|---|
| `nanobase-semantic-watchdog.timer` | 5 dk | köprüye **gerçek bir soru** sorar (yalnız port kontrolü değil); sağlıksızsa `nanobase-semantic-bridge` restart — `scripts/server/semantic-watchdog.sh` |
| `nanobase-semantic-worker.timer` | her gece 02:00 | profil → mine → aday → sertifika → sürüm; sonunda `/api/v1/semantic/reload` |
| logrotate `/etc/logrotate.d/nanobase-bi` | haftalık, 8 kopya | `bi/logs/*.log` |
| journald | `SystemMaxUse=2G` | servis logları (uvicorn) |


## Müşteri tarafında yapılması gerekenler (bizim yapamayacaklarımız)

### 1. Logo veritabanına kalıcı erişim
Bugün Logo'ya erişim **senin Mac'inden açılan ters SSH tüneliyle** (`ssh -N -R 127.0.0.1:14330:192.168.0.155:1433 nanobase`). Mac uyursa veya kapanırsa `/timas` tamamen durur; watchdog bunu `logo-tunnel:FAIL` olarak raporlar ama düzeltemez. Seçenekler:
- **Tercih:** müşteri ağında sabit bir makineden (Logo sunucusunun kendisi olabilir) `autossh` ile kalıcı ters tünel + systemd; anahtar tabanlı, yalnız port yönlendirme yetkili kullanıcı.
- Alternatif: site-to-site VPN (WireGuard) — bağlantı dosyasındaki (`SEMANTIC_CONNECTION_FILE`) `host/port` VPN adresine çevrilir, başka değişiklik gerekmez.
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
Sonra bizde: `SEMANTIC_CONNECTION_FILE` ile gösterilen bağlantı dosyasındaki `user/password_file` güncellenir ve köprü restart edilir. Sohbette paylaşılmış olan mevcut parola **döndürülmeli**.
