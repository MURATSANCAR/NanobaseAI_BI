# ZEKI AI CHAT canlı kabul kanıtları — 2026-09-29

Uygulama sürümü: `6c6d214d4`; imaj: `zeki-ai-chat:8.5.3-6c6d214d4`. Test sunucusunda gerçek uygulama/API ve Mongo ile kabul geçti. Sonraki belge commitleri çalışma kodunu değiştirmez.

- `source-evidence.json`, `source-audit.json`: Git içerik eşitliği ve sınıflandırılmış kaynak taraması.
- `image-audit.json`: çalışan imajın dosya/manifest taraması.
- `final-deployment.json`, `deployment-evidence.json`: imaj kimliği, sürüm, ağ ve veri bağları.
- `migration-apply.json`, `empty-legacy-cleanup.json`: yedekli dönüşüm ve korunmuş veri hashleri.
- `db-inventory-after.json`, `db-metadata-evidence.json`: tüm uygulama koleksiyonları, belge ve indeks taraması.
- `browser-evidence.json`, `chat-*.png`: dört genişlikte gerçek SSO ve ekran kontrolleri.
- `capabilities-api.json`, `subscriptions-evidence.json`, `messages-evidence.json`: kaynak modül listesi ve bağımsız gerçek Mongo karşılaştırmaları.
- `network-evidence.json`, `runtime-evidence.json`, `wire-evidence.json`, `host-evidence.json`: dış çıkış, DNS/firewall ve yapılandırma denetimi.
- `cleanup-evidence.json`: yalnız bu kabulün kısa oturum ve jetonlarının temizliği.

Ham özel veritabanı yedekleri ve oturum sırları bu klasöre alınmamıştır. Kapsam ve korunan teknik istisnalar [ana raporda](../../zeki-owned-cleanup.md) açıklanır.
