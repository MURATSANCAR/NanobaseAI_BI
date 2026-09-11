# CFO özeti üretici

Ekran açılışında sekiz sorgu koşmasın diye özet arka planda üretilir.

- Betik: `/opt/timas-metrics/build.py` (kaynağı `scripts/server/timas-metrics-build.py`)
- Çıktı: `/data/nanobaseai/bi/metrics/cfo.json`, atomik yazılır
- Zamanlama: `timas-metrics.timer`, açılıştan 2 dk sonra ve her 3 dakikada bir
- Yayın: nginx `location /timas/metrics/`, oturum şartı API ile aynı (`auth_request`)

Ekran önce bu dosyayı okur. Dosya yoksa ya da üretici durursa sekiz sorguya
canlı düşer; yani özet bozulsa bile ekran boş kalmaz.

Elle çalıştırmak:

```bash
ssh nanobase-direct 'sudo /opt/timas-metrics/build.py'
systemctl list-timers timas-metrics.timer
```

## Onay kararları için nginx bloğu

Onay ekranındaki Onayla / Düzelt / Reddet düğmeleri kataloğu değiştirir, bu yüzden
motor admin başlığı ister. nginx şu yolda ve yalnız bu yolda başlığı ekler:

```
location ~ ^/timas/api/v1/semantic/concepts/[^/]+/review$
```

Oturum şartı API ile aynı (`auth_request /_timas_session_check`). Başlık değeri
`/etc/nginx/snippets/timas-semantic-admin.conf` içinde, 640 izinli.

Bunun anlamı: Timaş portalına giriş yapan herkes terim onaylayabilir. Yetkiyi
daraltmak isterseniz değişecek yer bu blok.
