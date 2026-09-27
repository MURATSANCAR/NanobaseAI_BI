# NanobaseAI Destek (apps/destek)

BI'dan ayrı çalışan destek modülü: müşteri destek kayıtları (Helpdesk), bilgi bankası, müşteri
portalı ve masaüstünde yapay zekâ paneli (Flow). Ekranda her yerde ad **NanobaseAI**, logo ve renkler
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

- Tek Frappe sitesi `destek`; Docker yığını `nanobase-destek` (`docker/compose.yaml`): MariaDB 11.8,
  iki Redis, gunicorn, websocket, iki kuyruk işçisi, zamanlayıcı, nginx.
- Test sunucusu: `/data/nanobaseai/destek` (yalnız `compose.yaml` + `.env`; kod imajın içinde).
  Konteyner nginx'i `127.0.0.1:8447`; dışarıya `https://portal.nanobase.ai:8446` (`deploy/nginx-destek-8446.conf`).
  Frappe kök yolda çalışır (`/helpdesk`, `/app`, `/api`, `/assets`), o yüzden `/timas/` altına değil ayrı porta konur.
- Ekranlar: `/helpdesk` temsilci ekranı ve müşteri portalı (`/helpdesk/my-tickets`), `/app` masaüstü;
  masaüstünde `Ctrl+I` yapay zekâ panelini açar.
- Giriş Frappe'nin kendi kullanıcılarıyla. Yönetici şifresi sunucuda `/etc/nanobase/destek-admin.txt` (root, 600).
- Model: NanobaseAI modeli, OpenAI uyumlu korumalı uç `https://portal.nanobase.ai/gpu-llm/v1`
  (anahtar sunucudaki `/etc/nanobase/timas-vm-gpu-llm.key` dosyasından kurulumda okunur, sitede şifreli
  alanda durur). Bu uç LLM kapısının sırasına girmez — açık iş, aşağıda.

## Kurulum / güncelleme

Sıra AGENTS.md'deki gibi: main'e merge → test sunucusu → müşteri VM'i. Kaynak her zaman `git archive main`:

```bash
git archive main apps/destek | ssh nanobase-direct 'rm -rf ~/destek-src && mkdir ~/destek-src && tar -x -C ~/destek-src'
ssh nanobase-direct "~/destek-src/apps/destek/scripts/install.sh ~/destek-src/apps/destek $(git rev-parse main)"
```

`install.sh` imajı `nanobase-destek:<sürüm>-<sha8>` adıyla derler, `.env` yoksa üretir, yığını kaldırır,
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
- `nanobase_brand/install.py` her göçte: uygulama adı NanobaseAI, logo/simge, dil Türkçe, saat dilimi
  İstanbul, tarih `gg.aa.yyyy`, para TRY, kullanım verisi (telemetri) kapalı, web alt bilgisi NanobaseAI.
- Kaldırılanlar: üreticinin destek/belge/bulut menü satırları, üretici posta hizmeti seçeneği, ERPNext
  sekmesi (kayıt sistemi Logo), karşılama kaydındaki üretici videoları.
- Ayarlar sekmelerindeki «daha fazla bilgi» bağlantıları hâlâ üreticinin belge sitesine gider (ad
  ekranda yazmaz); kendi belge sitemiz olunca değiştirilecek.

## Türkçe

Site dili Türkçe. Çeviri katmanları (sonraki öncekini ezer): çatı → helpdesk → flow → nanobase_brand.
`nanobase_brand/locale/tr.po` marka çevirileri ve çatının eksiklerini taşır. Eksik çeviriler
`tools/cevir.py` ile NanobaseAI modelinden (LLM kapısı, arka plan önceliği) doldurulur; yer tutucu ve
HTML etiketi tutmayan çeviri yazılmaz.

## Üst sürüme geçiş

1. Üst kaynağı `frappe-apps/<uygulama>`ya olduğu gibi kopyala, ayrı commit'le (fark alınabilsin).
2. `python3 apps/destek/tools/marka.py` → «SORUN» satırlarını elle düzelt, `--denetle` 0.
3. Yeni metinler için `cevir.py`; imaj sürümünü (`nanobase_brand/__init__.py`) artır; kurulum sırasıyla yayınla.

## Açık işler

- Yapay zekâ paneli modele doğrudan gidiyor, LLM kapısının sırasına girmiyor; kapıya OpenAI uyumlu
  bir giriş gerekiyor.
- Portalın AD girişiyle ortak oturum yok; Frappe'nin LDAP ayarıyla AD'ye bağlanabilir.
- Müşteri VM'ine kurulmadı.
