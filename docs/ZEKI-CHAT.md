# BI içinde ZEKI AI CHAT

Sohbetin tam kaynak ağacı `apps/zeki-chat/` içindedir. Ayrı Git deposu/submodule yoktur; BI `main` tek yayın kaynağıdır. İlk taşıma, ayrı sohbet deposunun `e7334b0` commit'inden alınmıştır; uygulama kodu son canlı kabul sürümü `9b12e38` ile aynıdır. Sonraki değişiklikler bu BI dizininde yapılır.

## Kaynak ve kurulum

- Uygulama: `apps/zeki-chat/apps/meteor/`
- Ortak paketler ve Yarn workspace: `apps/zeki-chat/packages/`, `apps/zeki-chat/package.json`, `apps/zeki-chat/yarn.lock`
- Docker, yerel ağ ve firewall: `apps/zeki-chat/deploy/zeki/`
- Portal SSO köprüsü: `scripts/server/portal-login/server.py`; kurulum: `deploy/zeki/portal-sso-setup.sh`
- Canlı kabul ve sınırlar: [yerel ağ kabulü](../apps/zeki-chat/docs/zeki-local-egress.md), [ikinci tarama kanıtları](../apps/zeki-chat/docs/evidence/2026-09-29-recheck/)

BI React/Vite derlemesi ve sohbet Meteor/Yarn derlemesi ayrı çalışma alanlarıdır. Sohbet bağımlılıklarını BI köküne kurmayın. BI TypeScript yalnız `src` dizinini kapsar; mevcut Vitest yapılandırması `apps/**` altını dışlar.

Sunucuya yalnız BI `main` arşivi taşınır. Sohbet alt ağacını mevcut sohbet kaynak dizinine aktarmak gerekirse:

```bash
git archive main:apps/zeki-chat | ssh -o ControlPath=/tmp/cm-<oturum> nanobase-direct 'tar -x -C /home/administrator/zeki-ai-chat'
```

Tam BI ağacının sunucuda bulunduğu kurulumda, BI kökünden:

```bash
cd apps/zeki-chat
yarn install --immutable
cd ../..
SKIP_RESTART=1 IMAGE=zeki-ai-chat:<surum> ZEKI_CODE_VERSION=<bi-main-commit> bash deploy/zeki/build-chat.sh
```

Node `22.22.3`, Yarn `4.12.0`, Meteor ve Deno sürümleri sohbetin kendi yapılandırmasına uymalıdır. Derleme ve ürün testleri sunucuda yapılır. Restart öncesi mevcut `.env`/`.branding.env` yalnız sunucuda korunur; `ZEKI_CHAT_IMAGE` doğrulanmış imaja sabitlenir. Compose proje adı `zeki` ve mevcut `zeki_zeki-*` veri hacimleri korunur. Yerel ağ guard kurulumu için yukarıdaki kabul belgesini izleyin.

SSO kurulum betiği varsayılan olarak BI içindeki compose dizinini kullanır. Eski canlı kaynak dizini kullanılıyorsa `CHAT_COMPOSE=/home/administrator/zeki-ai-chat/deploy/zeki` açıkça verilir. Kurulum betiği mevcut canlı ayarların yerine boş bir `.env` üretmek için kullanılmaz.

## Taşımanın doğrulama sınırı

Bu işlem kaynak yerleşimi ve kurulum yolu değişikliğidir; canlı konteyner yeniden kurulmadı, UI/DB davranışı değiştirilmedi. Son test sunucusu imajı `zeki-ai-chat:8.5.3-9b12e38` olarak kalır. 9.711 dosyanın içerik/modları kaynak Git ağacıyla karşılaştırıldı; 9.709 dosya birebir aynı ([taşıma kaydı](zeki-chat-import.json)); yalnız README ve konumdan bağımsız build yolu uyarlanır. Yerel test çalıştırılmaz. Yeni BI commit'inden üretilecek bir imaj, yeniden gerçek API–DB ve tarayıcı kabulü gerektirir.
