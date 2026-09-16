# NanobaseAI BI — Proje Belleği

Bu dosya canlı özet, tek doğru kaynak. Değişiklik olunca üzerine yazılır (eski bilgi silinir/düzeltilir). Kronolojik geçmiş için [docs/GELISTIRME-GUNLUGU.md](docs/GELISTIRME-GUNLUGU.md)'ye bak.

## Proje ne

Doğal dilde soru → yönetilen SQL → doğru veri. Tek başına kurulan BI ürünü: React arayüz, FastAPI backend, Query Gateway, semantic katman, senaryo motoru ve LLM servisi. İlk/ana müşteri: TİMAŞ Logo (mağaza/satış verisi).

## Mimari (üstten alta)

```
React (src/, Vite)  →  nanobase_api (FastAPI, :8790)  →  semantic_layer (Katalog + Evidence Engine + Resolver/Compiler)
                                                        →  semantic_bridge (:8795, Timaş'a özel köprü)
                                                        →  query_gateway (:8792, salt-okunur/izin listeli tek SQL çalışma noktası)
                        nanobase_awel  →  LLM operatörleri (planlama/onarım/açıklama iş akışları)
```

- **semantic_layer**: NL→SQL çekirdeği. Katalog + kanıt motoru esas doğru kaynak (WrenAI kaldırıldı, bkz. proje belleği `wren-teardown-done`). Detay: `docs/architecture/semantic-layer-v1.md`.
- **semantic_bridge (:8795)**: Timaş kokpitine özel köprü — `/api/v1/ask`, `/run_sql`, `/api/v1/semantic/*`, `/api/v1/schema/*`.
- **query_gateway (:8792)**: Müşteri SQL'inin tek çalışma noktası, salt okunur, izin listeli.
- **nanobase_api (:8790)**: API, chat gateway, semantic katalog, senaryo motoru.

## Stack

- Frontend: React + Vite + TypeScript (`src/`), Tailwind.
- Backend: Python/FastAPI (`backend/nanobase_api`, `backend/nanobase_awel`, `backend/query_gateway`, `backend/semantic_layer`, `backend/semantic_bridge`).
- Şema tarama/gömme: `tools/schema-indexer`.
- Kurulum: Docker Compose (`deploy/compose`, müşteri paketi), `deploy/llm-server` (GPU sunucusu LLM tanımı).
- Meta DB: Postgres (:5434).

## Sunucu / port yapısı

| Servis | Port |
|---|---|
| Web (Vite dev) | 5174 |
| API (`nanobase_api`) | 8790 |
| Query Gateway | 8792 |
| Semantic Bridge (Timaş) | 8795 |
| LLM (OpenAI uyumlu) | NVIDIA hosted `integrate.api.nvidia.com/v1`, `deepseek-ai/deepseek-v4-flash-0731`, düşünme kapalı (köprü drop-in `semantic-bridge-nvidia.env`); eski GPU sunucusu yok |
| Gömme servisi | 8083 (embedder, CPU) |
| Meta DB (Postgres) | 5434 |
| BI uygulama VM (müşteri) | http://192.168.0.55/timas/ |

Ayrıntı proje belleklerinde: `semantic-production-deployment`, `bi-app-vm-55`, `llm-nvidia-hosted`, `timas-logo-network-access`.

**Çalışma yeri kuralı (2026-09-14):** Mac'te hiçbir işlem, sorgu ya da çalıştırma yapılmaz. Tüm iş bizim test sunucusu (`nanobase-direct`) ile müşteri sunucusu arasında yürür: sunucu → VPN `tun0` → TİMAŞ ağı (Logo SQL 192.168.0.155: `LOGO_DB`; **CRM SQL 192.168.0.28 `CRMDATBASE`/`Timas_MSCRM` — 2026-09-16'da .155 kopyasından buraya taşındı**; BI VM 192.168.0.55). Mac yalnız sunucuya komut ileten uç ve dosya/git yeridir; müşteriye Mac'ten erişim yoktur.

**CRM ve Logo artık iki ayrı SQL sunucusu (2026-09-16):** Logo `.155` (socat `:14330`), CRM `.28` (`connector_from_file` → `secrets/crm-mssql-connection.json`, `zekiai`). Köprü `Runtime._conn_for(sql)` ile yönlendirir: SQL'de `timas_mscrm` varsa → .28, değilse → .155; tek sorguda ikisi de = kasıtlı hata (cross-server join yok). Ayrıntı: yerel bellek `timas-crm-prod-28`.

**TİMAŞ erişimi:** Logo SQL (192.168.0.155) yalnız nanobase sunucusundaki WatchGuard OpenVPN tüneli (`tun0`) + socat `:14330` ile erişilir; Windows tarafına RDP (`timas\muratsancar`) de açık. VPN kullanıcısı `muratsancar` MFA (push/OTP) istiyor. Kullanıcı adı/şifreler repo'da **tutulmaz** — yerel proje belleğinde: `timas-access-credentials`.

**VPN nasıl açılır (2026-09-14'ten beri):** `timas` servis hesabı `AUTH_FAILED` veriyor; tünel `muratsancar` hesabıyla telefon onayıyla açılır. Sunucu `CRV1` meydan okumasını alır, `CRV1::<state>::p` ile bağlanır, kullanıcı WatchGuard bildirimini onaylar. Birim: `timas-vpn-mfa` (`systemd-run`). Şifreleme şartı: `--data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-256-CBC --data-ciphers-fallback AES-256-CBC`. Oturum kalıcı değil: kopma veya yeniden başlatmada push adımı tekrarlanır. Kopukken belirti: portal açılır, veri gelmez (köprü logunda FreeTDS `08001`). Kontrol: `ip -br addr show tun0`, `systemctl is-active timas-vpn-mfa`. Adım adım tarif: yerel bellek `timas-logo-network-access`.

**VPN hesabı kısıtı (2026-09-14 13:30'dan beri):** Tünel açılıyor ama WatchGuard bu hesaba yalnız `192.168.0.55:3389` (RDP) izni veriyor. Test sunucusundan `192.168.0.155:1433` (SQL: `LOGO_DB` + `Timas_MSCRM`), `.155:3389` ve `.55:22` kapalı. Aynı gün 10:44'te `.155:1433` açıktı; kural sonradan değişti. Sonuç: test sunucusundan Logo/CRM sorgusu ve `ssh timas-vm` çalışmaz. Gereken: TİMAŞ BT'den VPN hesabına `192.168.0.155 TCP 1433` ve `192.168.0.55 TCP 22` izni.

## Dizin haritası

| Dizin | İçerik |
|---|---|
| `src/` | React + Vite arayüz (tek frontend, kanvas: `src/canvas`) |
| `src/canvas/board/` | Panolar: kişiye özel kart panosu (sürükle/boyutlandır, SQL paneli, son sorgu saati, başlık/not, CSV/PDF, KPI karşılaştırma, ECharts-GL 3B); düzen + son sonuç sunucuda `semantic_board_cards` (`backend/semantic_bridge/board.py`, `/api/v1/board`), tarayıcı yalnız önbellek; zamanlayıcı `timas-board.timer` |
| `backend/semantic_layer/vocabulary.py` | Eş anlamlı üretim hattı: alan açıklaması → aday → çürütme → insan onayı → kavram `synonyms`; `sl_vocabulary`; ezmeme kuralı (`human`/karar verilmiş satıra üretim dokunmaz); ekran `/es-anlamlilar` |
| `backend/semantic_bridge/reports.py` | Planlı raporlar: cümleden plan (`parse_prompt`), `semantic_reports` tablosu, Excel/CSV üretimi (`/data/nanobaseai/bi/var/reports`), SMTP (ALERT_SMTP_*) yoksa dosya indirilir; `/api/v1/reports*`, zamanlayıcı `timas-reports.timer` (5 dk); ekran `src/canvas/reports/ReportsScreen.tsx` (`/planli-raporlar`) |
| `backend/semantic_bridge/prefs.py` | Kişi tercihleri `semantic_user_prefs` (AD hesabı + anahtar → JSON), `/api/v1/me/prefs/{key}`; Genel bakış kanvas düzeni `layout:<ekran>` burada. Kişiye özel alanların hepsi sunucuda: planlı raporlar (`username`), pano (`username`), uyarılar (`created_by`), kanvas düzeni (prefs); tarayıcı yalnız önbellek |
| `backend/semantic_bridge/admin.py` + `src/canvas/admin/` | Yönetim (`/yonetim`, yalnız `TIMAS_ADMIN_USERS`'taki AD hesapları): ayarlar tablosu `semantic_settings` (ekran > `/etc/nanobase/semantic-bridge.env` > varsayılan; SMTP, alıcı alan adları, e-posta bağlantısı, hatırlatma, rapor dosya sayısı, yöneticiler — `admin.conf()` ile okunur), değişiklik kaydı `semantic_audit` (rapor/uyarı/pano kartı/ayar/sözlük kararı/kolon açıklaması: oluşturma, güncelleme önce→sonra, silme, çalıştırma), herkesin raporları/uyarıları/kartları, kişiler ve yönetici atama, servis ve zamanlayıcı durumu; uçlar `/api/v1/admin/*` |
| `scripts/server/portal-login/` | Giriş: `timas-login` (:8796) Timaş Active Directory ile doğrular (ldap3 + NTLM), oturum çerezi + nginx `auth_request`; AD ayarı sunucuda `/etc/nanobase/timas-ad.json`. Demo/davet/Basic hesap yok (2026-09-14'te kaldırıldı) |
| `backend/nanobase_api` | API, chat gateway, semantic katalog, senaryo motoru |
| `backend/nanobase_awel` | LLM operatörleri, planlama/onarım/açıklama iş akışları |
| `backend/query_gateway` | Müşteri SQL'inin tek çalışma noktası |
| `backend/semantic_layer` | Semantic Catalog + Evidence Engine + History Miner + Profiler + Resolver/Compiler |
| `src/canvas/kampus` | Girişten sonraki ilk ekran (`/`): Kampüs intraneti + ZEKİ + modüllere geçiş; BI genel bakış `/genel-bakis` |
| `backend/semantic_bridge` | Timaş kokpiti köprüsü (:8795) |
| `tools/schema-indexer` | Şema tarama ve gömme |
| `deploy/compose` | Müşteri kurulum paketi (Docker) |
| `deploy/llm-server` | GPU sunucusu için LLM servis tanımı |
| `docs/architecture` | Kilitli mimari, tasarım ve plan belgeleri |
| `docs/audits` | Denetim/inceleme kayıtları |
| `docs/product` | Ürün belgeleri |
| `configs/` | Operatör yapılandırmaları (bağlantı profilleri, şema katalogları, semantic bağlamalar) |

## Kritik kurallar (AGENTS.md'den, kısa özet)

- **Mobil öncelik**: Her arayüz değişikliği 320/390/768/masaüstü genişliklerde tarayıcıda kontrol edilir; yatay taşma yok. Detay: `apps/cockpit/AGENTS.md`.
- **Gerçek DB ile doğrulama zorunlu**: Veri alma/SQL/hesaplama/raporlama etkileyen her değişiklik bağlı gerçek veritabanı + gerçek API akışıyla doğrulanmadan tamamlanmış sayılmaz. Yerel mock/fixture/SQLite ile test **yasak** (kullanıcı ayrıca istemedikçe). Doğrulanamıyorsa **DOĞRULANAMADI** diye raporla, başarı iddia etme.
- **Tek şirket, çok yıllık yedek**: TİMAŞ'ta tek şirket var; `211`/`411` gibi kodlar farklı şirket değil, yıl yedekleridir (bkz. proje belleği `logo-period-prefixes-are-years`, `timas-logo-database-shape`).
- Tam kural metni: [AGENTS.md](AGENTS.md).

## Notlar

- **Kokpit yayını:** kaynak sunucuda derlenir. `rsync -a --delete src/ nanobase-direct:/data/nanobaseai/bi/frontend/src/`, sunucuda `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build`, sonra `sudo rsync -a --delete --no-o --no-g dist/ /data/nanobaseai/bi/cockpit/dist/`. Commit etmek yayınlamak değildir; canlıdaki `index.html` tarihine bak.

- Bu proje için ayrıca kalıcı bellek kayıtları `~/.claude/projects/.../memory/MEMORY.md` altında tutulur (semantic layer kararları, sertifikalama, kalite kapısı, vb.) — kod tabanından türetilemeyen proje bağlamı orada.
- Bu dosya + `docs/GELISTIRME-GUNLUGU.md` çifti bir **talimat**tır, hook değildir: oturumdaki Claude'un CLAUDE.md'yi okuyup uygulamasına bağlıdır, zorlayıcı değildir. Gerçek zorlama istenirse `.claude/settings.json`'a bir hook eklenebilir (örn. commit sonrası günlük güncellendi mi kontrolü) — bu ayrı bir iş, henüz yapılmadı.
