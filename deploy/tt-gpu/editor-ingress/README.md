# Müşteri sunucusundan editör motoruna erişim

Kurulum tarihi: 2026-09-21. Müşteri VM'inin (192.168.0.55) "kitaba soru" özelliği, bizim ortamlarımızdan
(test sunucusu, TİMAŞ VPN) bağımsız olarak doğrudan GPU'ya gider.

## Neden bu yol

Ölçüm (2026-09-21):

| Yön | Sonuç |
|---|---|
| Müşteri VM → GPU özel adresleri (172.23.85.x: 22 / 19110 / 8001) | kapalı |
| GPU → müşteri VM (192.168.0.55: 22 / 80) | kapalı |
| Müşteri VM → GPU genel adresi 85.111.30.227:443 | **açık** |
| Müşteri VM → 85.111.30.227:22 | kapalı |

Tek yol GPU'nun genel adresindeki nginx (`kitap-eczanesi` sitesi, 443).

## GPU'da ne var

`/etc/nginx/sites-enabled/kitap-eczanesi` içinde `# EDITOR-BASLA … # EDITOR-BITTI` bloğu. Yalnız iki yol:

- `POST /editor/v1/chat/completions` → `127.0.0.1:19110/v1/chat/completions` (okuma zaman aşımı 1800 sn)
- `GET /editor/v1/models` → `127.0.0.1:19110/v1/models`

Üç kat koruma:

1. **Hermes API anahtarı** (`Authorization: Bearer …`).
2. **`X-Editor-Gate` gizli başlığı** — nginx'te sabit değer, yanlışsa 403.
3. **Kaynak IP kısıtı `85.105.0.0/16`** — müşteri iki farklı çıkış adresiyle göründü (`85.105.155.33`,
   `85.105.129.94`), bu yüzden tek adres yazılmadı.

Sertifika (`/data/ssl/cert.pem`) yenilendi: SAN `IP:172.23.85.10, IP:85.111.30.227`, 825 gün. Eski sertifika
`/data/ssl/cert.pem.bak.2026-09-21`, eski nginx dosyası `/root/nginx-yedek/`.

## Müşteri VM'inde ne var

- `infra/docker/bi/.env`: `EDITOR_API_BASE`, `EDITOR_API_KEY`, `EDITOR_MODEL`, `EDITOR_CA_FILE`,
  `EDITOR_EXTRA_HEADER` (değerler repoda yok).
- `infra/docker/bi/secrets/ad/gpu-editor-ca.pem` → konteynerde `/app/ad/gpu-editor-ca.pem`.
  TLS doğrulaması **kapatılmadı**; köprü bu dosyayla doğrular.

## Doğrulama

Müşteri VM'inin köprü konteynerinden: `/editor/v1/models` → 200; gizli başlık olmadan → 403.

## Bilinen sınır

Soru sorulunca motor yönetici modelini açmak ister. GPU 1'de kitap analizi sürerken (görsel model ~87 GB)
yönetici model yüklenemez, Hermes 500 alır ve soru düşer. Bu yolun değil motorun sınırıdır; test
sunucusundan sorulan soru da aynı anda aynı şekilde düşer.

## Geri alma

1. GPU: `EDITOR-BASLA … EDITOR-BITTI` bloğunu sil, `sudo nginx -t && sudo systemctl reload nginx`.
2. İstenirse eski sertifikayı geri koy: `/data/ssl/cert.pem.bak.2026-09-21`, `key.pem.bak.2026-09-21`.
3. Müşteri VM: `.env`'den `EDITOR_*` satırlarını sil, `docker compose up -d --force-recreate bridge`.
