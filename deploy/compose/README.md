# NanobaseAI BI — Müşteri Kurulumu (Docker)

Tek paket: web arayüzü, API, iş kuyruğu, Query Gateway, meta veritabanı, önbellek,
vektör deposu ve şema gömme servisi. Müşteri verisi **uzak veritabanında kalır**;
sistem yalnız salt-okunur bağlanır ve SQL'i yalnız Query Gateway üzerinden çalıştırır.

## Gereksinimler

| Bileşen | Asgari |
|---|---|
| İşletim sistemi | Ubuntu 22.04/24.04 (x86_64) |
| Docker | Engine 24+ ve Compose v2 |
| CPU / RAM / Disk | 8 çekirdek / 16 GB / 40 GB (modeller hariç) |
| LLM (Seçenek A) | Harici GPU sunucusu, OpenAI uyumlu adres (`LLM_API_BASE`) + anahtar |
| LLM (Seçenek B) | Bu makinede NVIDIA GPU (≥ 24 GB VRAM), ≥ 128 GB RAM, ≥ 120 GB disk, `nvidia-container-toolkit` |
| Ağ | Müşteri veritabanına salt-okunur erişim (5432 vb.), model indirme için internet (yalnız kurulumda) |

## Kurulum

```bash
cd deploy/compose
cp .env.example .env          # gerekirse portu ve LLM adresini düzenleyin
./install.sh                  # LLM harici sunucuda
# ./install.sh --with-gpu-llm # LLM bu makinede (GPU)
# ./install.sh --with-analytics --with-demo   # isteğe bağlı profiller
```

`install.sh` boş bırakılan gizli değerleri üretir, modelleri indirir, imajları derler,
meta veritabanı şemasını uygular ve sağlık kontrolü geçene kadar bekler.
Arayüz: `http://<sunucu>:<PUBLIC_HTTP_PORT>` (TLS için önüne kendi reverse proxy'nizi koyun).

## Müşteri veritabanını bağlama (uzak PostgreSQL)

```bash
./add-datasource.sh --id erp --label "ERP" \
  --host db.musteri.local --port 5432 --database erpdb --user bi_ro \
  --schemas public,sales        # --no-ssl  (yalnız güvenli ağ içinde)
```

Betik şifreyi güvenli sorar, `secrets/erp.password` ve `secrets/postgres-ro.datasources.json`
dosyalarını yazar, servisleri yeniler, bağlantıyı test eder, **şema taramasını** başlatır ve
kaynağı aktif yapar. Tarama bitince arayüzden (Kaynaklar) soru sormaya başlanabilir.

Veritabanı tarafında yalnız `SELECT` yetkili bir kullanıcı açın:

```sql
CREATE ROLE bi_ro LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE erpdb TO bi_ro;
GRANT USAGE ON SCHEMA public TO bi_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bi_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO bi_ro;
```

Oracle / SAP kaynakları için `secrets/oracle-ro.datasources.json` ve
`secrets/sap-ro.datasources.json` biçimleri `configs/*.datasources.json.example` dosyalarındadır.

## LLM

Üretim profili sabittir: **greedy** (sıcaklık 0), **düşünme kapalı**, **MTP spekülatif
çözümleme** (taslak Q8, 3 token), **24K bağlam**, attention GPU'da, MoE expert ağırlıkları
`LLM_N_CPU_MOE` katman için CPU RAM'de. `LLM_PARALLEL` değeri API'nin eşzamanlılık
sınırı ile birebir aynıdır.

| Durum | Ayar |
|---|---|
| Harici sunucu | `.env` → `LLM_API_BASE=http://<gpu-sunucu>:8011/v1`, `LLM_API_KEY=<anahtar>` |
| Yerel GPU | `./install.sh --with-gpu-llm`; VRAM'e göre `LLM_N_CPU_MOE` düşürülerek hız artırılır |

Harici sunucuda servis tanımı örneği: `deploy/llm-server/` (systemd, aynı bayraklar).

## Günlük işletim

```bash
docker compose ps                         # durum
docker compose logs -f api                # canlı log
curl -s localhost/api/v1/bi/health | jq   # sağlık
docker compose pull && docker compose build && docker compose up -d   # güncelleme
```

Yedek: `secrets/`, `data/`, `.env` ve `meta-db-data` volume'u (`docker run --rm -v nanobaseai-bi_meta-db-data:/v -v $PWD:/b alpine tar czf /b/meta-db.tgz /v`).

## Sorun giderme

| Belirti | Kontrol |
|---|---|
| `health.llm=false` | `LLM_API_BASE` erişilebilir mi? `curl -H "Authorization: Bearer $LLM_API_KEY" $LLM_API_BASE/models` |
| Bağlantı testi başarısız | DB güvenlik duvarı / `pg_hba.conf`, SSL zorunluluğu (`--no-ssl`), kullanıcı yetkileri |
| Sorular "şema bulunamadı" diyor | Tarama bitti mi? `docker compose logs worker`; arayüzde Kaynaklar › Tara |
| Yavaş cevap | `LLM_PARALLEL`, GPU'ya taşınan expert katman sayısı (`LLM_N_CPU_MOE`), CPU thread sayısı |

## Ürün adı

Arayüz, hata mesajları ve loglar yalnız **NanobaseAI BI** adını taşır; kullanılan alt
bileşenlerin adları müşteriye görünmez.
