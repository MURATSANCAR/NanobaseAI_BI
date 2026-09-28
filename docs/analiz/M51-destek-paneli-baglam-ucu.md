# M51 — Destek masası panelinin müşteri bağlamı ucu (sözleşme)

Durum: köprüde yazıldı (2026-09-28), test sunucusunda **DOĞRULANAMADI** (sunucu kapalı). `apps/destek` koduna dokunulmadı;
panele bağlanmak, dal sahibinin ayrı işidir (analiz §9 «Sonraki sürüm»). Bu belge o iş için sözleşmedir.

## Neden ayrı uç

Portal ekranı (`/timas/musteri-destek`) kişinin portal oturumuyla çağırır. NanobaseAI Destek'in temsilci ekranı (Frappe)
portal oturumunu taşımaz; masanın **sunucusu** köprüyü çağırır. Bu yüzden panel uçları çerezsizdir ve üç kapıdan geçer:

1. **nginx** `…/destek-baglam/v1/` — `Authorization: Bearer <destek anahtarı>` (masanın model paneliyle aynı anahtar,
   `/etc/nanobase/destek-llm.key`); köprünün çağıran jetonunu nginx ekler, çerezi siler. Dosya:
   `deploy/nanobase-direct/nginx-destek-baglam.conf`.
2. **Panel anahtarı** (isteğe bağlı): Yönetim → Ayarlar → Müşteri hizmetleri → «Masa paneli anahtarı»
   (`DESTEK_PANEL_TOKEN`) doluysa istek `X-Destek-Panel-Key` başlığında bu değeri taşımalı.
3. **Temsilcinin portal yetkisi**: `X-Destek-Agent: <AD hesap adı>` (e-posta değil; masada AD girişi `username` alanına
   `sAMAccountName` yazar). Köprü bu kişinin portal rolünü uygular: `sayfa:musteri-destek` + `ozellik:destek.baglam`
   (bağlam) ya da `ozellik:destek.oneri` (öneri/taslak) ve veri alanları (`cari`, `satis`). Panel, temsilcinin portalda
   göremeyeceği hiçbir şeyi göremez. Her bağlam okuması değişiklik kaydına (`semantic_audit`, tür `support_context`)
   temsilcinin adıyla yazılır.

## Uçlar

| Yöntem ve yol (dış) | Köprü yolu | Ne döner |
|---|---|---|
| `GET /destek-baglam/v1/context?ticket=HD-123` | `/api/v1/support/panel/context` | Talebin gönderen adresiyle müşteri bağlamı |
| `GET /destek-baglam/v1/context?email=…` / `phone=` / `order=` / `account=<CRM cari GUID>` | aynı | Aynı, ölçütle |
| `GET /destek-baglam/v1/insight?ticket=HD-123` | `/api/v1/support/panel/insight` | Zeki AI konu, aciliyet, SSS eşleşmesi, son taslak |
| `POST /destek-baglam/v1/draft` `{"ticket":"HD-123","order":"TS-1"?,"account":"…"?}` | `/api/v1/support/panel/draft` | Cevap taslağı (gönderilmez) |

Örnek (masanın sunucusundan):

```bash
curl -s https://portal.nanobase.ai/destek-baglam/v1/context?ticket=HD-123 \
  -H "Authorization: Bearer $DESTEK_KEY" -H "X-Destek-Agent: ayse.yilmaz"
```

Frappe tarafında (panelin sunucu yöntemi) aynı çağrı `frappe.session.user` → `frappe.db.get_value("User", user, "username")`
ile hesap adını bulup `requests.get(...)` yapar; anahtar masanın site ayarında durur, tarayıcıya gitmez.

## Bağlam yanıtı (özet)

```json
{
  "asOf": "2026-09-28",
  "match": {"contacts": [{"id": "…", "ad": "…", "accountId": "…", "cariKodu": "…"}], "webusers": [], "accounts": [{"id": "…", "unvan": "…", "cariKodu": "120.…", "kanal": "Kitapçı"}]},
  "needsChoice": false,
  "account": {"id": "…", "unvan": "…", "cariKodu": "…", "kanal": "…"},
  "orders": [{"id": "…", "no": "TS-…", "tarih": "2026-09-01", "durum": 100000000, "durumAd": "Sevk edildi", "tip": "B2B",
              "adet": 10, "bekleyen": 0, "acik": false, "riskte": false, "sevkTarihi": "…", "takipNo": "…", "takipUrl": "https://…",
              "kargoFirma": "…", "tutar": 0}],
  "shipments": [{"no": "…", "orderId": "…", "tarih": "…", "faturaNo": "…", "logo": {"no": "…", "tarih": "…", "tutar": 0, "iade": false}}],
  "cargo": [{"takipNo": "…", "firma": "…", "cikisSube": "…", "varisSube": "…", "teslimTarihi": "…", "iadeDurumu": "…", "desi": 1.5, "tutar": 42.0, "orderIds": ["…"]}],
  "invoices": [{"no": "…", "tarih": "…", "turAd": "Satış|İade", "tutar": 0}],
  "logo": {"dataEnd": "2026-08-17", "since": "2025-09-01", "note": "Logo verisi bu tarihe kadar; …"},
  "tickets": [{"ref": "HD-…", "subject": "…", "status": "…", "opened": "…"}],
  "summary": {"orders": 3, "open": 1, "risk": 0, "pending": 4},
  "hidden": [], "warnings": []
}
```

- `needsChoice: true` → birden çok cari eşleşti; panel `match.accounts`'u gösterir, temsilci seçince `account=` ile yeniden ister.
- `hidden` doluysa temsilcinin rolünde «Satış ve sipariş» veri alanı yok; sipariş/kargo/fatura bölümleri boş gelir.
- `logo.dataEnd`: Logo kopyası bu tarihe kadar; panel «fatura kesilmedi» demeden önce bu tarihi yazar.
- Hata gövdesi her zaman `{"detail": {"code": "…", "message": "<Türkçe cümle>"}}`: 401 anahtar, 403 yetki ya da veri alanı,
  422 geçersiz girdi, 503 CRM/Logo/masa erişilemiyor (`retryable`).

## Kimlik bilgisi ve kişisel veri

- CRM `new_kargofirmasi` ve `new_webuser` kullanıcı adı / şifre / token / secret kolonları hiçbir sorguda geçmez
  (`support_sources.guard`); yanıtlarda e-posta ve telefon döndürülmez (yalnız arama koşulunda kullanılır).
- Taslak ve sınıflama için modele giden metinde e-posta, telefon, IBAN, kart ve kimlik numarası maskelenir; imza ve
  alıntılanmış eski yazışma kırpılır; talep metni köprüde saklanmaz.
- Model çağrıları LLM kapısından (`rt.llm_for("destek")`); masanın kendi yapay zekâ paneli de kapıdan gider
  (`/destek-llm/v1`). Bağlam ucu modelsizdir: bütün rakamlar CRM/Logo SQL'inden.
