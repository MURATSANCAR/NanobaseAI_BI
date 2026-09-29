# ZEKİ AI (apps/destek)

BI'dan ayrı çalışan destek modülü: müşteri destek kayıtları (Helpdesk), bilgi bankası, müşteri
portalı ve masaüstünde yapay zekâ paneli (Flow). Ekranda her yerde ad **ZEKİ AI**, logo ve renkler
portalın kanvas diliyle aynı.

| Parça | Kaynak | Sürüm |
|---|---|---|
| Çatı | `frappe/frappe` (imaj derlenirken indirilir, değiştirilmez) | `v16.35.0` |
| Telefon eklentisi | `frappe/telephony` (Helpdesk'in zorunlu bağımlılığı) | `039cf39f` |
| Destek ekranı | `frappe/helpdesk` → `frappe-apps/helpdesk` (markalı) | `main` `1c3361cc` (v1.30.1) |
| Yapay zekâ paneli | `frappe/flow_client` → `frappe-apps/flow` (markalı) | `develop` `4a3189b6` |
| Marka katmanı | `frappe-apps/nanobase_brand` (bizim) | `0.1.0` |

Lisans: Helpdesk ve Flow AGPL-3.0. Değiştirilmiş kaynak bu depoda durur; kullanıcıya ağ üzerinden
sunulduğu için kaynak, istenirse kullanıcılara verilebilir olmalıdır. Lisans dosyaları ve kod içi
telif başlıkları korunur, yalnız ekrandaki ürün adları değişir.

## Nerede, nasıl çalışır

- Tek site `destek`; Docker yığını `nanobase-destek` (`docker/compose.yaml`): MariaDB 11.8,
  iki Redis (önbellek arama eklentili `redis-stack-server`: kayıt araması için), gunicorn, websocket, iki kuyruk işçisi, zamanlayıcı, nginx.
- Test sunucusu: `/data/nanobaseai/destek` (yalnız `compose.yaml` + `.env`; kod imajın içinde).
  Konteyner nginx'i `127.0.0.1:8447`; dışarıya `https://portal.nanobase.ai:8446` (`deploy/nginx-destek-8446.conf`).
  Çatı kök yolda çalışır (`/helpdesk`, `/app`, `/api`, `/assets`), o yüzden `/timas/` altına değil ayrı porta konur.
- Ekranlar: `/helpdesk` temsilci ekranı ve müşteri portalı (`/helpdesk/my-tickets`), `/app` masaüstü;
  masaüstünde `Ctrl+I` yapay zekâ panelini açar.
- Giriş Timaş Active Directory ile, iki yol:
  1. **Portal oturumuyla otomatik (tek oturum):** portala girmiş kişi Destek'e gelince giriş sayfası tarayıcıyı
     portalın `/timas/auth/destek-sso` adresine yollar (portal çerezi `Path=/timas/` olduğu için Destek onu doğrudan
     göremez). Portal giriş servisi (`scripts/server/portal-login/server.py`) oturumu okur, 60 sn'lik tek kullanımlık
     HMAC jetonla Destek'e döner; Destek imzayı, süreyi, tek kullanımı denetler, kişiyi AD'den bulur ve oturum açar
     (`nanobase_brand/sso.py`, `public/js/portal_sso.js`). Ortak anahtar `/etc/nanobase/destek-sso.key`
     (`root:www-data 640`) → site ayarı `destek_sso_secret`.
  2. **AD kullanıcı adı + şifre:** portal oturumu yoksa `/login?sso=0` formu; NTLM ile doğrulanır (`ldap_ntlm.py`).
  Her etkin AD kişisi temsilcidir; portal yöneticileri (`TIMAS_ADMIN_USERS`/`TIMAS_ADMIN_GROUP`) yöneticidir.
  Ekip: kişinin AD birimi (alan, yoksa OU) aynı adlı etkin destek ekibiyle eşleşirse girişte o ekibe eklenir
  (Türkçe harf/aksan duyarsız: «Satış» = «Satis»). Birim listesi: `nanobase_brand.ldap_ntlm.ad_departments`.
  Yerel yönetici hesabı (Administrator) şifresi `/etc/nanobase/destek-admin.txt` (root, 600), `/login?sso=0`'dan.
- Model: ZEKİ AI modeli, **LLM kapısından**: panel `https://portal.nanobase.ai/destek-llm/v1` (nginx
  `deploy/nginx-destek-llm.conf`, Bearer anahtarı `/etc/nanobase/destek-llm.key`) → köprünün OpenAI uyumlu girişi
  `/api/v1/llm/openai/v1/chat/completions` (`backend/semantic_bridge/llm_openai.py`). Her çağrı `sl_llm_queue`
  sırasından kiralık alır (modül `destek`, etkileşimli öncelik); BI soruları ve gece işleriyle aynı slotları paylaşır.

## Yapay zekâ özellikleri (`nanobase_brand/yz/`)

Model çağrılarının hepsi LLM kapısından (`/destek-llm/v1`, modül `destek`); model hiçbir şeyi müşteriye göndermez.

| Özellik | Nerede | Davranış |
|---|---|---|
| Sınıflama | yeni kayıt (arka plan, `yz/kanca.py` → `kayit.classify`) | tür, öncelik, ekip, müşteri duygusu; yalnız boş ya da sistem varsayılanındaki alan, yalnız tanımlı değer; kayıt geçmişine not. Atama kuralı çalışamazsa alanlar yine yazılır |
| Özet | temsilci ekranı → «ZEKİ AI» → Özetle | 3 satır: istek, yapılan, sıradaki adım |
| Yanıt taslağı | «Yanıt taslağı hazırla» | bilgi bankası + çözülen kayıtlardan; yanıt kutusuna eklenir, temsilci gönderir; dayanak bağlantıları |
| Benzer geçmiş kayıtlar | «Benzer geçmiş kayıtlar» → Bul | bilgi bankasında anlamca en yakın çözülmüş kayıtlar (yoksa aynı türden); her biri için DB'deki çözüm notu + temsilci yanıtlarından «uygulanan çözüm», ilgisizler elenir, en çok 3 maddelik önerilen yol. Kayıt çözülünce bilgi bankasına hemen girer |
| Makale taslağı | çözülen kayıtta | kişisel verisiz taslak makale (`HD Article`, Taslak, `nb_kaynak_kayit`) |
| SLA riski | hafta içi 08:30 | riskteki açık kayıtlar → Not + «Agent Manager» e-postası |
| Haftalık rapor | pazartesi 08:00 (elle `yz.rapor.weekly_now`) | sayılar veritabanından, 5 maddelik yorum modelden |

Bilgi bankası «ZEKİ AI Bilgi Bankası»: yayımlanmış makaleler + çözülen kayıtlar (Flow günlük eşitleme); gömme BI'ın
gömme servisi (`bge-m3`, 1024 boyut) — kapının `/embeddings` aktarıcısı. Temsilci paneli
`helpdesk/desk/src/components/ticket-agent/NanobaseAIPanel.vue` (marka.py ile kenar çubuğuna eklenir).
Giden e-posta: Gmail `zeki@timas.com.tr` (BI ile aynı hesap, uygulama şifresi köprünün yönetim ayarlarından; `nanobase_brand/eposta.py`), yalnız gönderim. Hesap yoksa raporlar yalnız Not olarak kalır.

## Kurulum / güncelleme

Sıra AGENTS.md'deki gibi: main'e merge → test sunucusu → müşteri VM'i. Kaynak her zaman `git archive main`:

```bash
git archive main apps/destek | ssh nanobase-direct 'rm -rf ~/destek-src && mkdir ~/destek-src && tar -x -C ~/destek-src'
ssh nanobase-direct "~/destek-src/apps/destek/scripts/install.sh ~/destek-src/apps/destek $(git rev-parse main)"
```

Müşteri VM'i (192.168.0.55): imaj test sunucusunda derlenir, `docker save | gzip -1 | ssh timas-vm "gunzip | docker load"`
ile taşınır; kaynak `git archive` ile `/home/ai/destek-src`'ye açılır, sonra VM'de (ai kullanıcısı):

```bash
env DESTEK_DIR=/home/ai/destek PUBLIC_URL=http://192.168.0.55:8446 LLM_BASE=http://web:8447/destek-llm/v1 LLM_KEY_FILE=/home/ai/destek/secrets/llm.key ADMIN_FILE=/home/ai/destek/secrets/admin.txt AD_FILE=/home/ai/bi-docker/infra/docker/bi/secrets/ad/timas-ad.json SSO_FILE=/home/ai/bi-docker/infra/docker/bi/secrets/destek/destek-sso.key SSO_GROUP= BRIDGE_ENV=/home/ai/bi-docker/infra/docker/bi/.env COMPOSE_EXTRA=compose.bi-net.yaml SITE_CONFIG_EXTRA=nb_bilgi_bankasi_kapali=1 SMTP_FILE=/home/ai/destek/secrets/smtp.json bash /home/ai/destek-src/apps/destek/scripts/install.sh /home/ai/destek-src/apps/destek <sha>
```

`install.sh` imajı `nanobase-destek:<sürüm>-<içerik özeti>` adıyla derler (özet Containerfile + frappe-apps; imaj varsa derlemez), `.env` yoksa üretir, yığını kaldırır,
site yoksa kurar (helpdesk + flow + nanobase_brand; telephony bağımlılık olarak), varsa `migrate` koşar,
marka/bölge ayarlarını ve modeli yazar; sonda ping, imaj, `DESTEK_CODE_VERSION` ve `._*` sayısını basar.
Veri volume'larda durur, kurulum silmez.

## Marka

- `tools/marka.py` üst kaynaktaki ekrana çıkan adları çevirir (tekrar koşturulabilir; bulamadığı satırı
  «SORUN» diye yazar). `--denetle` kalan izleri sayar, 0 olmalı.
- `marka/` logo (`logo.svg`), simge (`logo-mark.svg`, `favicon.svg`): coral→mor degrade, portal simgesiyle aynı dil.
- Tema: masaüstü ve giriş sayfası `nanobase_brand/public/css/nanobase.css`; destek ekranı
  `helpdesk/desk/src/nanobase-theme.css`; yapay zekâ paneli `flow/frontend/src/styles/nanobase.css`.
  Birincil düğme mor `#7C5CFF`, yazı DM Sans / başlık Plus Jakarta Sans, kenar çubuğu ve giriş zemini portalın mesh'i.
- `nanobase_brand/install.py` her göçte: uygulama adı ZEKİ AI, logo/simge, dil Türkçe, saat dilimi
  İstanbul, tarih `gg.aa.yyyy`, para TRY, kullanım verisi (telemetri) kapalı, web alt bilgisi ZEKİ AI.
- Kaldırılanlar: üreticinin destek/belge/bulut menü satırları, üretici posta hizmeti seçeneği, ERPNext
  sekmesi (kayıt sistemi Logo), karşılama kaydındaki üretici videoları.
- Dış bağlantı yok: üretici belge bağlantıları, belge düğmeleri, yardım merkezi ve e-posta sağlayıcılarının yardım
  sayfası bağlantıları silindi; `marka.py --denetle` dış adres deseni de tarar (yalnız yazı tipi sunucusu izinli).

## Türkçe

Site dili Türkçe. Çeviri katmanları (sonraki öncekini ezer): çatı → helpdesk → flow → nanobase_brand.
`nanobase_brand/locale/tr.po` marka çevirileri ve çatının eksiklerini taşır. Eksik çeviriler
`tools/cevir.py` ile ZEKİ AI modelinden (LLM kapısı, arka plan önceliği) doldurulur; yer tutucu ve
HTML etiketi tutmayan çeviri yazılmaz.

## Üst sürüme geçiş

1. Üst kaynağı `frappe-apps/<uygulama>`ya olduğu gibi kopyala, ayrı commit'le (fark alınabilsin).
2. `python3 apps/destek/tools/marka.py` → «SORUN» satırlarını elle düzelt, `--denetle` 0.
3. Yeni metinler için `cevir.py`; imaj sürümünü (`nanobase_brand/__init__.py`) artır; kurulum sırasıyla yayınla.

## Açık işler


- Talep eden (BT dışı AD kullanıcısı) portal ekranı `/helpdesk/my-tickets` uçtan uca sınanmadı.
