# Ortak yapı taşı 4 — belge okuma ve OCR hattı: kurulum notu (2026-09-28)

Portalın tek belge okuma işlevi `backend/semantic_bridge/doc_read.py`. Metin katmanı olan sayfayı köprü kendisi okur;
metin katmanı olmayan (taranmış) PDF sayfası ve görüntü dosyası GPU sunucusundaki editör **kart servisine**
(`apps/editor/src/editor/card_api.py` → `POST /v1/read`, `apps/editor/src/editor/portal_read.py`) gider. Orada kitap
okumasında ölçülerek seçilen OCR okuyucusu (`apps/editor/deploy/models.yaml` 99–104, takma ad `EDITOR_OCR_ALIAS`)
gateway üzerinden okur; model gerekiyorsa gateway açar (ana modelle aynı GPU payı kuralları).

## Bağlantı

Köprü kitap kartlarıyla aynı adresi, anahtarı ve CA'yı kullanır (`editorial_cards._headers`):
`EDITOR_CATALOG_BASE` + `EDITOR_CATALOG_KEY` (+ internet üzerinden gidiliyorsa `EDITOR_CATALOG_EXTRA_HEADER`,
`EDITOR_CATALOG_CA_FILE`). Yeni ortam değişkeni yok.

- **Test sunucusu:** kart servisine doğrudan (tünel `127.0.0.1:19141`) gider; ek ayar yok.
- **Müşteri VM'i:** TT GPU nginx'i beyaz liste çalışır (bellek `tt-gpu-nginx-card-whitelist`): listede olmayan yol
  varsayılan siteye düşer ve **200 + HTML** döner. `doc_read.remote_read` bunu yakalar ve «belge okuma servisi JSON
  dönmedi» diye yazar; sayfa «okunamadı» kalır. Aşağıdaki location eklenmeden VM'de taranmış belge okunmaz.

## TT GPU nginx — location (betik: `deploy/tt-gpu/editor-ingress/add-read-route.py`, 2026-09-29)

Dosya: `/etc/nginx/sites-available/kitap-eczanesi` (depoda değil). Var olan `/editor/cards/v1/documents` bloğunun
kalıbıyla (IP izni, gizli başlık denetimi, yöntem sınırı). Gizli başlığın adı ve değeri dosyadakiyle aynıdır; buraya
yazılmaz.

```nginx
# Portal belge okuma (ortak yapı taşı 4): taranmış PDF / görüntü → sayfa metni. Yalnız POST, gövde sınırsız
# (şartname, rapor), uzun süre (OCR modeli açılırken beklenir; köprü DOC_READ_TIMEOUT_SEC = 900).
location = /editor/cards/v1/read {
    # allow <VM köprüsünün çıkış IP'si>;  deny all;          ← mevcut kart bloklarındaki satırlar aynen
    # if ($http_x_editor_gate != "<gizli değer>") { return 403; }
    limit_except POST { deny all; }
    client_max_body_size 0;
    proxy_request_buffering off;
    proxy_read_timeout 960s;
    proxy_send_timeout 960s;
    proxy_pass http://127.0.0.1:19141/v1/read;
    proxy_set_header Authorization $http_authorization;
}
```

Uygulama sırası (kullanıcı onayıyla, paylaşılan kaynak): `nginx -t` → yalnız geçerse `systemctl reload nginx` →
VM köprüsünün içinden `editorial_cards._headers()` ile küçük bir görüntü gönderip JSON cevap alındığını doğrula.

## Kart servisi imajı

`card_api.py` ve `portal_read.py` değişti: editör kart imajı (`EDITOR_CARDS_IMAGE`, bellek `mac-tar-appledouble`)
yeniden kurulmalı. Kart servisi `editor.env` ortamını zaten okur (gateway adresi ve anahtarı); yeni ortam değişkeni
isteğe bağlı: `EDITOR_PORTAL_READ_MIN_CHARS` (20), `EDITOR_PORTAL_READ_MAX_TOKENS` (4096).

## Gizlilik

Kart servisi portal belgesinin içeriğini model defterine (`ed.model_call`) yazmaz, dosyayı diske yazmaz; yalnız sayfa
sayısı ve süre günlüğe düşer. Okunan metin portalda, bir sohbet modeline gitmeden önce maskelenir (İK'da
`hr_recruit_text.rule_mask`).

## Bağlanan yerler

| Ekran | Nerede | Davranış |
|---|---|---|
| M33 ihale şartname özeti | `tenders.document_reading` / `summarize_text(reading=…)` | taranmış sayfa OCR; madde alıntısı belgede birebir aranır, OCR sayfasındaki madde «OCR · s. n · %güven» |
| M55 özgeçmiş | `hr_recruit_text.extract_reading` | OCR metni kural maskesinden geçer; yükleme bildiriminde «n sayfa OCR ile okundu» |
| M39 sektör raporu | `pazar_sources.read_scanned` (çıkarım işinde) | metinsiz sayfalar OCR; rakam OCR metninde birebir; rakam satırında «OCR» |
| M57 sertifika | `hr_learning.certificate_check` → `POST /api/v1/hr/learning/certificates/{id}/check` | kayıttaki ad/tarih belgede birebir aranır; karar İK'nın |
| M44 kargo faturası | — | portalda kargo faturası yükleme yok (2026-09-28); bağlanacak yer yok |
| M1 başvuru ön okuması (öneri 12) | `application_preread.analyse` (pencereler `doc_extract.plan_windows`) | eser dosyası bölüm bölüm; her alan alıntılı, OCR sayfasından gelen alıntıda «OCR · %güven» |
| M6 sözleşme şartları (öneri 13) | `contract_extract.analyse` | taranmış sözleşme sayfası OCR; oran/tutar/tarih alıntıdan kodla okunur |
