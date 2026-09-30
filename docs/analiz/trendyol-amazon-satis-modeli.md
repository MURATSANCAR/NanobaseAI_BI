# Trendyol ve Amazon satış modeli — kodlama öncesi analiz

Tarih: 2026-09-29 · Durum: **kararlar verildi, Aşama 0 ve Aşama 1 kodlandı** (bkz. «Kararlar» ve §6) · Kapsam: M40 Trendyol,
M41 Amazon ve yurtdışı, M42 kanallar

---

## Kararlar (2026-09-29)

Kullanıcı §4'teki sekiz soruyu Claude'a bıraktı (bellek `business-decisions-delegated`). Kararlar ve gerekçeleri:

| # | Soru | Karar | Gerekçe |
|---|---|---|---|
| S1 | Trendyol'da nasıl satıyoruz? | **Tahmin edilmez; Aşama 0 uygulamada ölçer.** Ekran «Bu kanalın satış modeli: … (kanıt: …)» yazar; sınıf kendi mağaza / toptan / konsinye / belirsiz. | Bugün hiçbir ölçüm modeli kanıtlamıyor (§2.1–2.4). Yanlış modelle kod yazmak Aşama 1–3'ü boşa çıkarır; model Logo'daki kayıt biçiminden okunabilir (§2.5). |
| S2 | Amazon TR hangi modelde? | S1 ile aynı ölçüm, aynı ekran (`/amazon/model`). | CRM'deki kartlar üç modeli de ima ediyor (Vendor, Seller Central, konsinye tipi); veri karar verir. |
| S3 | Yurtdışı dahil mi? | **İlk sürüm yalnız Türkiye (Trendyol + Amazon TR).** Yurtdışı ayrı iş. | Ölçülen yurtdışı satış Amazon değil, yurtdışı kanal kodlu cariler (§2.3); AB KDV/ihracat kapsamı ayrı analiz ister. |
| S4 | Siparişler Logo'ya nasıl giriyor? | **Tahmin edilmez.** Aşama 1 okuması panel sipariş numarasının Logo faturasının hangi belge alanında geçtiğini veriden bulur ve alan başına isabeti ekranda yazar; bulamazsa «barkod + gün + adet». | Entegratör/elle giriş bilgisi yok; hangi alanın kullanıldığı verinin kendisinde ölçülebilir. Statik alan varsayımı yok (bellek `no-static-solutions`). |
| S5 | Kesintiler Logo'da nasıl kayıtlı? | **Tahmin edilmez.** Aşama 0 pazar yeri carilerinden alınan hizmet faturalarını (TRCODE 1, 4; LINETYPE 4) hizmet kartıyla sayar; Aşama 1 hakediş ekstresindeki belge numarasını da Logo'da arar. Bulunamazsa ekran «kesinti Logo'da bulunamadı» yazar; **uydurulmaz**. | Cari bağı olmayan muhasebe fişi bu sürümde okunmaz; o yol ölçülürse ayrı iş. |
| S6 | Veri yolu? | **Önce panel Excel'i**; API anahtarı gelince salt okuma API (Aşama 5). Bugün API kodu hazırlanmadı, yalnız belgede. | Anahtar yok; panel dosyası yolu M40'ta zaten çalışıyor. |
| S7 | Önce hangi değer? | **Aşama 1 — satış/iade mutabakatı + hakediş.** Panel sipariş/iade ve hakediş/ekstre satırları ↔ Logo faturalı satış/iade; eşleşmeyen, tutar farkı, eksik, fazla listeleri; dönem özeti; kesinti ve ödeme ↔ Logo. | Kaçan fatura ve yanlış kesinti doğrudan para; fiyat önerisi (Aşama 3) gerçek kesinti oranı olmadan yanlış alt sınır üretir. |
| S8 | Fiyat önerisi alt sınırı ve onay? | **Aşama 3 (bu turda KODLANMADI):** alt sınır = birim maliyet (M9) + gerçek kesinti (Aşama 1'in ölçtüğü oran) + hedef marj (Yönetim ayarı). **Hazırlayan ≠ onaylayan**; onaylanan öneri panel şablonu Excel'i olarak indirilir, insan panele yükler. | «Liste fiyatının %… altı» maliyeti bilmez; mevcut kural «hazırlayan onaylayamaz» (M40 vitrin, M42 iskonto) korunur. |
| — | Pazar yerine yazma | **Yok** (ilke sürüyor). | 2026-09-28 kararı; T-soft yasağıyla aynı ilke. |

Bağlam: 2026-09-28 kararı «Trendyol/Amazon satış modeli sonraya; M40–M42 yalnız okuma + Excel yükleme ile başlar»
idi ([YOL-HARITASI.md](kullanici-ihtiyaclari/YOL-HARITASI.md) › «Sonraya bırakılanlar»). Kullanıcı 2026-09-29'da bu işi
şimdi başlatmak istedi. **Geçerli kural değişmedi:** ilk sürümde pazar yerine otomatik gönderim yok. Stok, fiyat, sipariş
onayı, iade onayı, soru cevabı, listeleme ya da kampanya katılımı gibi hiçbir şey platforma yazılmaz. Sistem taslak üretir,
insan onaylar, işi insan panelde elle yapar. (T-soft'a yazma yasağı ile aynı ilke.)

Kaynaklar: [M40](kullanici-ihtiyaclari/M40-trendyol.md), [M41](kullanici-ihtiyaclari/M41-amazon-uluslararasi.md),
[M42](kullanici-ihtiyaclari/M42-pazaryeri-d2c.md), [M34](kullanici-ihtiyaclari/M34-eticaret-platform.md) analizleri,
[crm-eticaret-entegrasyon-2026-09-27.md](crm-eticaret-entegrasyon-2026-09-27.md) §4, `backend/semantic_bridge/channels/`
kodu, `scripts/acceptance/M40|M41|M42/`, geliştirme günlüğünün 2026-09-28 ve 2026-09-29 girişleri.

Belgedeki işaretler: **[kod]** depodaki koddan okundu. **[ölçüldü]** daha önceki bir oturumda gerçek DB'de ölçüldü (tarihi
yazılı). **[genel bilgi]** sektör pratiği ya da platform belgesi; TİMAŞ verisiyle doğrulanmadı. **[ölçülemedi]** bu oturumda
denendi, yapılamadı.

---

## 0. Bu oturumda gerçek veri ölçümü: ölçülemedi

Test sunucusunda (nanobase-direct, tek ControlMaster bağlantısı) Logo .25 ve CRM .28'e doğrudan salt okuma sorgusu atmak
için köprünün bağlantı ayarını okumak gerekiyordu. Bu adım izin denetiminde «kimlik bilgisi keşfi» sayılıp **reddedildi**.
Görev tarifine göre zorlanmadı. `run_sql` ucu da kullanılmadı, çünkü bellek kuralı (`verify-direct-db`) bağımsız ölçümün
o uçtan yapılmasını yasaklıyor: uç sorguyu yeniden fizikselleştiriyor.

Belgedeki rakamlar bu yüzden daha önceki oturumların ölçümleridir (§2.4). Model kararı için gereken yeni ölçümler §2.5'te,
koşmaya hazır SQL olarak duruyor. İzin verilince tek betikte, salt okuma olarak koşulur. `SEMANTIC_FIRMS` / `firm_in_scope`
kuralı uygulanır: .25'te 101 firma var; TİMAŞ'ın firmaları 411 (2026) ve 211 (2021–2025).

---

## 1. Bugün ne var (koddan kanıt)

### 1.1 Genel çerçeve

- Üç modül de `main`de, tek köprü paketinde: `backend/semantic_bridge/channels/` **[kod]**. Menü alanı «Platform»,
  rotalar `src/App.tsx` satır 468–484: `/kanallar`, `/kanallar/matris|d2c|eslesme|:platform`,
  `/trendyol`, `/trendyol/urunler|siparisler|sorular|vitrin|haftalik|yukle`, `/amazon`, `/amazon/konsinye|yurtdisi|…`.
- **Platform API'sine hiç istek gitmez.** `channels/platform_common.py` → `OfflineClient.NETWORK = False`. İzin listesi
  dışındaki her çağrı ağa çıkmadan `ReadOnlyViolation` atar. İzinli okuma da `PlatformError` («bu sürümde bağlanılmaz»)
  atar **[kod]**.
  - `channels/trendyol_client.py`: izinli yalnız 4 GET var: ürün listesi, sipariş listesi, iade (claims) listesi, soru
    listesi. **Finans / cari hesap ekstresi okuması izin listesinde yok.**
  - `channels/amazon_client.py`: izinli 4 GET var: `orders/v0/orders`, `orderItems`, `fba/inventory/v1/summaries`,
    `catalog/…/items`. **Finances ve Reports (settlement) yok.** Erişim belirteci alma adımı (LWA) yazılmadı.
- Zamanlayıcı: `scripts/server/timas-channels.{service,timer}` gece 04:00 (M42 karnesi + M40/M41 `run-due`), rapor için
  `timas-channels-report.timer` **[kod]**.

### 1.2 M42 kanallar (ortak taban)

- Kanal karnesi = Logo'da faturalı satır. `channels/sql/_metrics.sql`: satış TRCODE 7,8,9; iade 2,3; `INVOICEREF <> 0`;
  iptal hariç; net = LINENET satış − iade; iskonto = LINETYPE 2 TOTAL; maliyet yalnız `OUTCOST > 0` satırlarında.
  `logo_kanal_karne.sql` kanalı `CLCARD.SPECODE2` ile gruplar. `logo_eticaret_cari.sql` cari × ay sell-in'i verir **[kod]**.
- Cari ↔ platform eşlemesi: tablo `semantic_channel_accounts`, ekran `/kanallar/eslesme`. Kapalı platform listesi
  `mapping.PLATFORMS`: hepsiburada, trendyol, amazon, kitapyurdu, dr, idefix, timas.com.tr, diger, degil. Adla aday
  `DEFAULT_HINTS`: D-MARKET → Hepsiburada, DSM GRUP → Trendyol, TURKUVAZ → D&R, AMAZON TURKEY → Amazon. Onay insanda
  **[kod]**.
- **Komisyon, kargo, reklam gibi kanal maliyetleri Logo'dan okunmuyor.** Bunlar için finansın elle girdiği tek bir oran var:
  `mapping.extra_costs` (`ek-maliyet:<platform>`, uç `PUT /api/v1/channels/settings/ek-maliyet/{platform}`). Oran yoksa
  «katkı» hiç gösterilmez **[kod]**.
- Genel panel satış raporu yüklemesi `channels/imports.py`. Tanınan kolonlar yalnız barkod, stok kodu, ad, adet, tutar ve
  kanal stoğu; **kesinti kolonu yok** **[kod]**.

### 1.3 M40 Trendyol

- Uçlar `channels/trendyol_api.py` (`/api/v1/channels/trendyol/*`): meta, status, overview, accounts, products,
  stock-diff, price-diff, orders, claims (+classify), questions, reviews (+draft), showcase (+suggest), suggestions
  (+decision), imports, weekly, export **[kod]**.
- Tablolar (`channels/trendyol.py`): `semantic_trendyol_imports|products|orders|claims|questions|reviews|logo` **[kod]**.
- Panel dosyası türleri (`channels/trendyol_import.py` → `SPECS`): **ürün, sipariş, iade, soru, yorum**. Sipariş dosyasından
  yalnız «faturalanacak tutar / satış tutarı» alınır. **Komisyon, kargo bedeli, hizmet bedeli, hakediş ya da ödeme tarihi
  kolonu tanınmıyor; hakediş / cari ekstre dosya türü yok** **[kod]**. Alıcı adı, adres ve telefon kolonları hiç okunmaz.
- Toptan senaryo: Logo'da adı `TRENDYOL_CARI_ADLARI` ile eşleşen cari (varsayılan «TRENDYOL, DSM GRUP») M42 eşlemesine
  «aday» düşer. Ciro M42 karnesinden okunur, burada yeniden hesaplanmaz **[kod]**.
- Hesaplar: stok farkı (Trendyol stoğu ↔ Logo depo bakiyesi) ve fiyat farkı (Trendyol ↔ `PRCLIST` liste ↔ T-soft site
  fiyatı; `TRENDYOL_MAX_INDIRIM` 0,35 ölçülmemiş varsayılan). Ayrıca geciken paket, iade nedeni sınıfı (önce kural, sonra
  Zeki AI kapalı küme), cevapsız soru, düşük puan, vitrin önerisi, haftalık rapor **[kod]**.
- Test sunucusunda **Trendyol tabloları boş**: hiç panel dosyası yüklenmedi. `/orders` 200 döndü, 0 satır
  **[ölçüldü, 2026-09-29]**.

### 1.4 M41 Amazon ve yurtdışı

- Uçlar `channels/amazon_api.py` (`/api/v1/channels/amazon/*`): overview, accounts, books, consignment, international
  (+books), rights, params, drafts, market-cards, export **[kod]**.
- Konsinye kalan = onaylı Amazon carilerine faturalanmamış satış irsaliyesi (TRCODE 8, `INVOICEREF = 0`, `BILLED = 0`)
  − faturalanmamış iade irsaliyesi (TRCODE 3). Kaynak `channels/sql/logo_konsinye_kalan.sql`. Onaylı cari yoksa boş
  **[kod]**.
- Yurtdışı = `AMAZON_YURTDISI_KODLARI` (varsayılan «YURTDIŞI, YURTDISI») kanal kodlu cariler; cari × ülke × döviz × ay.
  Döviz tutarı LINENET ÷ fatura TRRATE. Kaynak `logo_yurtdisi.sql`, `logo_doviz.sql` **[kod]**.
- CRM: Amazon Konsinye siparişi (tip 14, `crm_amazon_siparis.sql`) ve Telif Satış sözleşmeleri (`crm_telif_satis.sql`).
  Tutar CRM'den okunmaz **[kod]**.
- Finans parametreleri `semantic_intl_params`: pazar, KDV, kargo birimi, `komisyon_orani`. Finans elle girer, açık yetkiyle
  **[kod]**.

### 1.5 Yol haritasındaki açık sorular (2026-09-28)

[YOL-HARITASI.md](kullanici-ihtiyaclari/YOL-HARITASI.md):

1. TİMAŞ'ın Trendyol'da kendi mağazası var mı, yoksa satış bayi / dağıtıcı üzerinden mi? (CRM'de yalnız 2020 test kaydı var.)
2. Amazon ilişkisi konsinye mi, yoksa Seller Central satıcı hesabı mı?
3. Satıcı API erişimi kimde; verilebilir mi?
4. Pazar yeri carileri Logo'da hangi kodlarla duruyor?

Bu belge 1, 2 ve 4'ü kısmen yanıtlıyor (§2.4). 3 ve kalanlar karar sorularına taşındı (§4).

---

## 2. «Satış modeli» bu projede ne demek

Bu projede «satış modeli» dört soruya verilen cevaptır:

- **Kim kime satıyor:** TİMAŞ son tüketiciye mi satıyor (platform aracı), yoksa platforma mı (platform alıcı)?
- **Logo'da nasıl kaydediliyor:** hangi cari, hangi kanal kodu, hangi fatura türü, iade nasıl giriyor?
- **Para nasıl geliyor:** hakediş, kesintiler, ödeme takvimi ve Logo ile mutabakat.
- **Fiyatı ve stoğu kim belirliyor**, kampanyayı kim fonluyor?

Kayıt sistemi Logo'dur (bellek `system-of-record-logo`). Satış = faturalı satır (bellek `sales-are-invoiced-lines`).
Platform raporu Logo'yu **doğrulamak** ve Logo'da olmayanı (sell-through, kesinti ayrıntısı) **tamamlamak** için okunur;
Logo'nun yerine geçmez.

### 2.1 Trendyol

İşletmeci: DSM Grup Danışmanlık İletişim ve Satış Tic. A.Ş. **[genel bilgi]**. M42'de adla aday bu unvandan üretilir.

| | A) Pazar yeri satıcısı (TİMAŞ'ın mağazası) | B) Trendyol'a toptan satış | C) Yalnız bayiler satıyor |
|---|---|---|---|
| Kim kime satar | TİMAŞ → tüketici; Trendyol aracı | TİMAŞ → DSM Grup; Trendyol tüketiciye | TİMAŞ → bayi; bayi Trendyol'da satar |
| Logo'da satış | Tüketiciye e-arşiv fatura. Genelde perakende satış (TRCODE 7) tek bir toplu «Trendyol müşterileri» carisine ya da entegratörün açtığı carilere **[genel bilgi]** | DSM Grup carisine toptan satış faturası (TRCODE 8) | Bayi carisine TRCODE 8 (kanal KITAPCI/DAGITICI…) |
| İade | Perakende satış iadesi (TRCODE 2) ya da iade faturası; platform iade onayından sonra | Toptan satış iadesi (TRCODE 3) | Bayi iadesi (3) |
| Kesintiler | Komisyon faturası (kategori oranı), kargo bedeli (anlaşmalı kargo, hakedişten düşer), platform hizmet bedeli (sipariş başı), e-ticaret stopajı (1 Ocak 2025'ten beri aracı ödemeden keser; oran yürürlükteki karara göre), reklam, ceza (geç kargo, tedarik edememe) **[genel bilgi]**. Logo'da alınan hizmet faturası (TRCODE 4) ya da masraf olarak girer — **ölçülecek** | Sözleşmeye bağlı: iskonto, ciro primi, lojistik katkı; fiyat farkı ya da hizmet faturası **[genel bilgi]** | Yok (TİMAŞ açısından) |
| Hakediş | Teslimattan sonra vadesinde Trendyol öder. Panelde «hesap ekstresi / ödeme detayı» Excel'i var; API'de muhasebe-finans (cari hesap ekstresi) okuma uçları var — uç adları entegrasyon belgesinde doğrulanacak **[genel bilgi]** | Normal toptan vade ve tahsilat (Logo `CLFLINE`) | — |
| Mutabakat | Sipariş ↔ Logo faturası; iade ↔ Logo iadesi; hakediş ekstresi ↔ banka tahsilatı + kesinti faturaları | DSM cari ekstresi ↔ Logo cari bakiye | — |
| Fiyat / stok | TİMAŞ belirler (PSF / TSF). Aynı barkodu başka satıcılar da satıyorsa fiyat yarışı var (öne çıkan satıcı) | Trendyol belirler; TİMAŞ liste fiyatı ve iskonto verir | Bayi belirler (**kanal çatışması riski**) |
| Kampanya | Kampanya takvimi (okula dönüş, Kasım); katılımda indirim + komisyon değişimi; fonu kimin taşıdığı kampanyaya göre değişir **[genel bilgi]** | Trendyol fonlar, TİMAŞ'tan katkı isteyebilir | — |

Hangisinin geçerli olduğu **bilinmiyor**. Bilinenler:

- CRM'de Trendyol'a ait cari ya da sipariş izi yok; tek iz 2020 «Trendyol Deneme Siparisi» kartı **[ölçüldü, 2026-09-27]**.
- Logo'da DSM Grup / Trendyol adlı cari M40 kabul K1 ile .155 kopyasında arandı (2026-09-28, «M40 9/10»). Günlükte cari adı ya
  da sayısı yazılmamış; .25'te **ölçülemedi**.

### 2.2 Amazon Türkiye

Amazon.com.tr'nin perakende şirketi CRM'de «Amazon Turkey» olarak duruyor.

| | A) Tedarikçi (Vendor, 1P) | B) Pazar yeri satıcısı (Seller Central, 3P) | C) Konsinye |
|---|---|---|---|
| Kim kime satar | TİMAŞ → Amazon (satın alma siparişiyle); Amazon tüketiciye | TİMAŞ → tüketici; Amazon aracı; gönderim FBA (Amazon deposu) ya da FBM (TİMAŞ gönderir) | TİMAŞ malı Amazon'a gönderir; Amazon sattıkça faturalanır |
| Logo'da satış | Amazon carisine toptan satış faturası (8); fiyatı Amazon belirler | Tüketiciye e-arşiv (7) — Trendyol A ile aynı soru | Önce faturasız satış irsaliyesi (8, `INVOICEREF = 0`), satış raporu gelince fatura. **M41 konsinye hesabı bunu varsayıyor** **[kod]** |
| İade | Amazon'un iadesi (3); sözleşmeye bağlı | Tüketici iadesi (2) | İade irsaliyesi (3) |
| Kesintiler | Pazarlama / co-op katkısı, hasar payı, fiyat koruma; fatura ya da ödeme kesintisi olarak **[genel bilgi]** | Satış komisyonu (kategori oranı), FBA gönderim ve depolama, aylık abonelik, reklam; medya ürünlerinde bazı pazarlarda kapanış ücreti **[genel bilgi]** | Sözleşmeye bağlı |
| Hakediş | Vadede ödeme (remittance) | Yaklaşık iki haftalık ödeme dönemi; settlement raporu **[genel bilgi]** | Satış raporuna göre fatura, sonra vade |
| Veri | Vendor Central raporları (satış, stok, satın alma siparişi) | Seller Central raporları; API'de Orders, Finances, Reports | Amazon'un satış raporu (Excel) |
| Fiyat / stok | Amazon belirler; TİMAŞ liste fiyatı / maliyet verir | TİMAŞ belirler; öne çıkan satıcı yarışı | Amazon belirler |

Bilinenler:

- CRM'de «Amazon Turkey» iki kart (biri «(B2C)»), ayrıca «Amazon Kindle US» ve «Amazon Seller Central» var
  **[ölçüldü, 2026-09-27]**. «Seller Central» kartı B modelinin, «(B2C)» kartı ise tüketici faturası toplu carisinin izi
  olabilir. Bu bir **varsayım**.
- CRM sipariş tipi 14 «Amazon Konsinye» seçenek olarak var, ama **etkin kayıt yok**: önbellek de canlı CRM de boş
  **[ölçüldü, 2026-09-29]**. Yani C modeli CRM'den işlemiyor. Ya kullanılmıyor ya da siparişler başka tipte giriyor.
- «M41 13/13» kabulü (2026-09-28, .155 kopyası) Amazon adlı carileri ve net ciroyu doğrudan SQL ile tuttu. Günlükte cari
  kodu ve tutar yazılmamış; .25'te **ölçülemedi**.

### 2.3 Amazon yurtdışı ve öteki yurtdışı satış

- **Amazon.de / .com ile fiziksel kitap satışı:** Seller Central'ın küresel satış yapısı (AB tek hesap) ya da oradaki bir
  distribütör. AB'de satıcı olarak satmak KDV yükümlülüğü doğurur (OSS/IOSS, depo ülkesinde kayıt) **[genel bilgi]**.
  Türkiye'den gönderim ihracattır: ihracat faturası, döviz, KDV istisnası; Logo'da döviz faturası olarak görünür.
- **Kindle / KDP (e-kitap)** M36'nın işidir; bu belgenin dışında («Amazon Kindle US» carisi e-kitap hakedişi olabilir —
  **varsayım**).
- **Bugün ölçülen yurtdışı satış Amazon değil, yurtdışı kanal kodlu carilerdir.** 2025'te 6.100.825,03 ₺, 2026 Ocak–Ağustos
  1.991.930,10 ₺ (geçen yıl aynı dönem 4.701.844,95 ₺). 9 cari × ay satırı var; en büyük cari Belçika'da. Eylül 2026'da
  yurtdışı satış yok. Önbellek ile canlı .25 27/27 aynı **[ölçüldü, 2026-09-29]**. Bu carilerin Amazon'la bağı
  kanıtlanmadı.

### 2.4 Ölçülmüş gerçekler (özet)

| Olgu | Değer | Kaynak |
|---|---|---|
| Trendyol API / entegrasyon izi (CRM) | Yok; yalnız 2020 test kartı | crm-eticaret-entegrasyon §4 (2026-09-27) |
| Pazar yerleri CRM'de | Toptan cari: Kitapyurdu (180 günde 227 sipariş), D-Market / Hepsiburada (34), Amazon kartları | aynı |
| Logo kanal kodu | `CLCARD.SPECODE2`: KITAPCI, E-TICARET, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR, YURTDIŞI… | `configs/semantic/knowledge/logo/models/dbo_LG_411_CLCARD/metadata.yml` |
| E-TICARET kanalının ilk carileri | Turkuvaz (D&R), Kitapyurdu, D-Market, Point | M34 analizi §6 |
| CRM Amazon Konsinye (tip 14) | 0 etkin sipariş | günlük 2026-09-29 |
| Yurtdışı kanal cirosu | 2025: 6,10 Mn ₺; 2026 Oca–Ağu: 1,99 Mn ₺; 9 cari satırı | günlük 2026-09-29 |
| Logo barkod eşlemesi | 26.504 farklı barkod (`UNITBARCODE`) | günlük 2026-09-28 (M40 kabul, .155) |
| Trendyol panel verisi (test sunucusu) | Yüklenmemiş, tablolar boş | günlük 2026-09-29 |

### 2.5 Model kararı için koşulacak salt okuma sorguları ([ölçülemedi] → izin gelince)

Logo .25, `LOGO_DB`. `{f}` = 411 (2026), 211 kopyasında `YEAR(DATE_) BETWEEN 2021 AND 2025` süzgeci. Tek betik, doğrudan
bağlantı (`connector_from_file`), yalnız SELECT.

```sql
-- L1 · Pazar yeri adlı cariler: kanal kodu, kart türü (1 alıcı, 2 satıcı, 3 ikisi), ülke, etkinlik.
SELECT CODE, DEFINITION_, SPECODE2, CARDTYPE, COUNTRY, ACTIVE FROM dbo.LG_{f}_CLCARD
WHERE DEFINITION_ LIKE N'%TRENDYOL%' OR DEFINITION_ LIKE N'%DSM GRUP%' OR DEFINITION_ LIKE N'%AMAZON%'
   OR DEFINITION_ LIKE N'%D-MARKET%' OR DEFINITION_ LIKE N'%HEPSİBURADA%' OR DEFINITION_ LIKE N'%KİTAPYURDU%'
   OR DEFINITION_ LIKE N'%TURKUVAZ%' OR DEFINITION_ LIKE N'%IDEFIX%' OR DEFINITION_ LIKE N'%N11%';

-- L2 · Bu carilerin fatura türü dağılımı: 7 perakende, 8 toptan, 2/3 iade, 1 alış, 4 alınan hizmet (komisyon/kargo?), 9 verilen hizmet.
SELECT C.CODE, F.TRCODE, YEAR(F.DATE_) AS yil, COUNT(*) AS fatura, SUM(F.NETTOTAL) AS net,
       SUM(CASE WHEN ISNULL(F.TRCURR,0) NOT IN (0,160) THEN 1 ELSE 0 END) AS doviz_fatura
FROM dbo.LG_{f}_01_INVOICE F JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = F.CLIENTREF
WHERE F.CANCELLED = 0 AND C.CODE IN ({L1_kodlari}) GROUP BY C.CODE, F.TRCODE, YEAR(F.DATE_);

-- L3 · Kesinti kalemleri ayrışıyor mu: bu carilerden gelen hizmet satırları (LINETYPE 4) hizmet kartıyla.
SELECT S.TRCODE, SV.CODE, SV.DEFINITION_, COUNT(*) AS satir, SUM(S.LINENET) AS tutar
FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_SRVCARD SV ON SV.LOGICALREF = S.STOCKREF
JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE S.LINETYPE = 4 AND S.CANCELLED = 0 AND C.CODE IN ({L1_kodlari}) GROUP BY S.TRCODE, SV.CODE, SV.DEFINITION_;

-- L4 · Para hareketi biçimi (hakediş tahsilatı, virman, mahsup): cari hareket türü × borç/alacak.
SELECT C.CODE, L.MODULENR, L.TRCODE, L.SIGN, COUNT(*) AS hareket, SUM(L.AMOUNT) AS tutar
FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
WHERE L.CANCELLED = 0 AND C.CODE IN ({L1_kodlari}) GROUP BY C.CODE, L.MODULENR, L.TRCODE, L.SIGN;

-- L5 · Konsinye izi: faturalanmamış satış irsaliyesi, yıl bazında (M41 kabul K3'ün genişletilmişi).
SELECT C.CODE, YEAR(S.DATE_) AS yil, SUM(S.AMOUNT) AS adet FROM dbo.LG_{f}_01_STLINE S
JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE S.TRCODE = 8 AND S.INVOICEREF = 0 AND S.BILLED = 0 AND S.CANCELLED = 0 AND S.LINETYPE = 0
  AND C.CODE IN ({L1_kodlari}) GROUP BY C.CODE, YEAR(S.DATE_);

-- L6 · Tüketici faturası nereye kesiliyor: 2026 perakende satış faturasının en yoğun 20 carisi.
SELECT TOP 20 C.CODE, C.DEFINITION_, C.SPECODE2, COUNT(*) AS fatura, SUM(F.NETTOTAL) AS net
FROM dbo.LG_411_01_INVOICE F JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF = F.CLIENTREF
WHERE F.CANCELLED = 0 AND F.TRCODE = 7 AND F.DATE_ >= '2026-01-01' GROUP BY C.CODE, C.DEFINITION_, C.SPECODE2
ORDER BY COUNT(*) DESC;

-- L7 · Kanal kodu envanteri (yazım dahil) ve 2026 faturalı net ciro.
SELECT ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)),''),'#YOK') AS kanal, COUNT(DISTINCT C.CODE) AS cari,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net
FROM dbo.LG_411_01_STLINE S JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.LINETYPE = 0 AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '2026-01-01'
GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)),''),'#YOK');

-- L8 · Platform sipariş numarası Logo'da nerede taşınıyor (mutabakat anahtarı): L1 carilerinin fatura belge alanları doluluğu.
SELECT TOP 50 F.FICHENO, F.DOCODE, F.SPECODE, F.CYPHCODE, F.GENEXP1 FROM dbo.LG_411_01_INVOICE F
JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF = F.CLIENTREF WHERE C.CODE IN ({L1_kodlari}) ORDER BY F.DATE_ DESC;
```

CRM .28 (`CRMDATBASE`, etkin kayıt `statecode = 0`):

```sql
-- C1 · Pazaryeri (9), B2C (8), Amazon Konsinye (14) sipariş sayısı, yıl × firma.
SELECT o.new_siparistipi, YEAR(o.new_siparistarihi) AS yil, a.Name, a.new_logicalref, COUNT(*) AS n
FROM new_siparisBase o LEFT JOIN AccountBase a ON a.AccountId = o.new_firmaid
WHERE o.statecode = 0 AND o.new_siparistipi IN (8, 9, 14) AND o.new_siparistarihi >= '2025-01-01'
GROUP BY o.new_siparistipi, YEAR(o.new_siparistarihi), a.Name, a.new_logicalref;
-- C2 · Platform adlı firma kartları ve Logo bağı.
SELECT Name, StateCode, new_logicalref, new_FirmaKanal, CreatedOn FROM AccountBase
WHERE Name LIKE N'%Trendyol%' OR Name LIKE N'%DSM%' OR Name LIKE N'%Amazon%';
```

Okuma kuralı: boş sonuç «satış yok» diye yorumlanmaz (öteki yıl kopyası, öteki ad yazımı ayrıca sorgulanır). L2–L4
sonuçları A/B/C modelini büyük ölçüde kendi başına ayırır:

- DSM carisine TRCODE 8 varsa → B.
- Yoğun TRCODE 7 toplu cari ile DSM/Amazon'dan TRCODE 4 hizmet faturası birlikteyse → A.
- Faturasız TRCODE 8 irsaliyesi varsa → konsinye.

---

## 3. Önerilen kapsam (aşama aşama)

İlke: her aşama bir öncekinin verisini kullanır. Hiçbir aşama platforma yazmaz. Rakamı SQL ve dosya üretir; Zeki AI yalnız
sınıflar, gerekçe ve taslak yazar. Kişisel veri içeri alınmaz (mevcut `trendyol_import` / `imports` kuralı). Demo veri yok,
sayı tavanı yok. Büyüklük: S ≤ 1 gün, M 1–2 gün, L 3+ gün.

| # | Aşama | Veri kaynağı | Ekran | Değer | Zorluk |
|---|---|---|---|---|---|
| 0 | **Model tespiti**: §2.5 sorguları + §4 kararları. Sonuç M42 eşlemesine ve `TRENDYOL_*` / `AMAZON_*` ayarlarına yazılır | Logo, CRM (salt okuma); kullanıcı | Yok (belge + Yönetim ayarı) | Yanlış modelle kod yazmayı önler | S |
| 1 | **Satış ve iade mutabakatı (salt okuma)**: platform sipariş/iade dosyası ↔ Logo fatura/iade satırı. Anahtar önce platform sipariş no (L8'de bulunursa), yoksa barkod + gün + adet. Çıktı: «teslim edildi, Logo'da faturası yok», «iade onaylı, Logo'da iadesi yok», «Logo'da var, platformda yok», tutar farkı | Mevcut Trendyol sipariş/iade dosyaları; Amazon için sipariş raporu (yeni dosya türü); Logo STLINE / INVOICE | `/trendyol/mutabakat`, `/amazon/mutabakat` (ortak bileşen `platformKit`) | Kaçan fatura/iade, puan ve ciro kaybı görünür | M (eşleme anahtarı belirsizse M → L) |
| 2 | **Hakediş ve kesinti**: hakediş / cari ekstre dosyası (Trendyol) ya da settlement raporu (Amazon 3P) ya da ödeme / kesinti raporu (Amazon 1P) okunur. Sipariş başına brüt, komisyon, kargo, hizmet bedeli, stopaj, reklam, ceza, ödenen, ödeme tarihi. Logo'daki banka tahsilatı (`CLFLINE`) ve hizmet faturalarıyla (L3) mutabakat. Beklenen ödeme takvimi. Gerçek kesinti oranı M42'nin elle girilen `ek-maliyet` oranının yerine geçer; M9 birim maliyetiyle kitap × kanal katkı marjı | Panel ekstre Excel'i (yeni tür), Logo CLFLINE / INVOICE TRCODE 4, M9 maliyet | `/trendyol/hakedis`, `/amazon/hakedis`; M42 karnesinde «gerçek kesinti» sütunu (`kanal.marj` yetkisiyle) | Fazla/yanlış kesinti ve geciken ödeme yakalanır; kanalın gerçek kârı ilk kez görünür | M–L |
| 3 | **Fiyat ve stok önerisi (taslak + onay)**: mevcut stok ve fiyat farkına fiyat alt sınırı eklenir: birim maliyet + gerçek kesinti (aşama 2) + hedef marj. Bayi fiyatıyla çakışma yalnız resmî veriyle (kazıma yok). Onaylanan öneri, panelin toplu fiyat/stok şablonu biçiminde Excel olarak indirilir; insan panele yükler. Bir sonraki dosya ya da okumada «uygulandı mı» kendiliğinden denetlenir | Aşama 1–2, Logo `PRCLIST`, M43 depo stoğu, M9 maliyet | `/trendyol/urunler` ve Amazon ürün sekmesinde «öneri» durumu; onay `trendyol.oneri-karar` / yeni `amazon.oneri-karar` (hazırlayan onaylayamaz) | Zarar altı satış ve stoksuz satış biter; iş gücü azalır | M |
| 4 | **Kampanya değerlendirmesi**: kampanyaya katılım teklifinin simülasyonu (indirim + komisyon değişimi → katkı) ve kampanya sonrası sonuç (M35 kampanya takvimiyle) — taslak rapor | Aşama 2 oranları, sipariş dosyaları, M35 | `/trendyol/kampanya` (ya da M35 içinde platform sekmesi) | Zararına kampanyaya girmeyi önler | M |
| 5 | **API ile salt okuma (dosyanın yerine, isteğe bağlı)**: Trendyol ürün, sipariş, iade, soru ve finans (cari ekstre) okuması. Amazon'da 3P ise Orders, Finances, Reports (settlement, FBA stok); 1P ise vendor raporları. Kod: `NETWORK` bayrağı kullanıcı kararıyla açılır; izin listesine yalnız GET finans uçları eklenir. Amazon belirteç alma (kimlik sunucusuna POST) ayrı ve yalnız o adres için izinli olur; mağazaya yazma değildir | Platform API | Aynı ekranlar; «son okuma» damgası; Yönetim › «Platform ve kanallar»a anahtar alanları | Elle dosya indirme biter; veri 15–30 dk taze | M |
| 6 | (Kapsam dışı, ayrı karar) Platforma yazma: stok/fiyat gönderimi, sipariş onayı | — | — | — | — |

**Aşama 1–4 API olmadan da çalışır** (panel dosyasıyla). Aşama 5 yalnız anahtar gelirse yapılır. Kalan yeni dosya türleri
ile modele göre ayrışan kısım:

- Trendyol yeni dosya türü: «hesap ekstresi / ödeme detayı». Kolon eş anlamlıları gerçek bir örnek dosyadan çıkarılır;
  örneksiz kolon adı uydurulmaz.
- Amazon yeni dosya türleri: sipariş raporu, settlement (3P) ya da satış / ödeme raporu (1P).
- Model B (Trendyol'a toptan) çıkarsa aşama 1–2 büyük ölçüde gereksizleşir. İş M42 karnesi + cari ekstre mutabakatına
  (Logo ↔ DSM ekstresi) iner. Aşama 3 «öneri»si de yalnız toptan iskonto ve liste fiyatı olur.

**API ve yetki (kimden ne istenir):**

| Erişim | Kimden | Ne verilir | Not |
|---|---|---|---|
| Trendyol Satıcı API (okuma) | Mağaza hesabı ana kullanıcısı (e-ticaret sorumlusu) | Satıcı ID, API anahtarı, API gizli anahtarı (satıcı paneli › hesap bilgileri › entegrasyon bilgileri) | Anahtar düzeyinde salt okuma seçeneği olduğu bilinmiyor **[genel bilgi]**; koruma bizim istemcide (izin listesi, testle kilitli). Entegratör aynı anahtarı kullanıyorsa istek sınırı paylaşılır. Yalnız Yönetim ekranından girilir (bellek kuralı) |
| Amazon SP-API (3P, okuma) | Seller Central birincil hesap sahibi | Özel geliştirici kaydı; roller: Finans ve Muhasebe, Stok ve Sipariş Takibi, Satış Ortağı İçgörüleri (FBA varsa gönderim). **Kişisel veri rolleri istenmez.** Kendi kendine yetkilendirmeyle yenileme belirteci, istemci kimliği ve gizli anahtar | 2023'ten beri AWS imzası gerekmiyor **[genel bilgi]**. Kişisel veri rolü olmadan sipariş alıcı bilgisi gelmez; bu bizim kuralımızla uyumlu |
| Amazon Vendor (1P, okuma) | Vendor Central hesap yöneticisi | Aynı geliştirici kaydı, tedarikçi rolleri | 1P ise sipariş / ödeme / satış raporları buradan |
| Logo | Mevcut `zekiai` (db_datareader) | Yeni yetki gerekmez; CLFLINE, SRVCARD, INVOICE okunabilir olmalı — L2–L4'te ölçülür | — |
| Muhasebe bilgisi | Mali İşler | Komisyon, kargo ve stopajın hangi hesaba / hizmet kartına girdiği | Aşama 2'nin önkoşulu |
| Entegratör | BT | Pazar yeri siparişlerini Logo'ya kim, nasıl aktarıyor (entegratör adı, T-soft pazaryeri modülü mü, elle mi) | Aşama 1'in eşleme anahtarını belirler |

---

## 4. Kullanıcıya sorulacak karar soruları

1. **Trendyol'da TİMAŞ nasıl satıyor?**
   (a) Kendi satıcı mağazamız var (tüketiciye biz faturalıyoruz) · (b) Trendyol'a (DSM Grup) toptan satıyoruz ·
   (c) Trendyol'da yalnız bayiler / dağıtıcılar satıyor · (d) Birden fazlası (hangileri?)
2. **Amazon Türkiye ilişkisi hangi modelde?**
   (a) Tedarikçi: Amazon bizden satın alıyor (Vendor) · (b) Kendi satıcı hesabımız var (Seller Central; FBA mı kendi
   gönderimimiz mi?) · (c) Konsinye: gönderiyoruz, sattıkça faturalıyoruz · (d) Şu an pasif
3. **Yurtdışı Amazon (de / com) ve yurtdışı carileri bu işe dahil mi?**
   (a) Amazon.de / .com'da fiziksel kitap satıyoruz, dahil · (b) Satmıyoruz; yurtdışı kanal (Belçika vb. 9 cari) ayrı
   ihracat işi olarak kalsın · (c) Şimdilik yalnız Türkiye
4. **Pazar yeri siparişleri Logo'ya nasıl giriyor?**
   (a) Bir entegratör aktarıyor (adı?) · (b) T-soft'un pazar yeri modülü · (c) Elle giriliyor · (d) Bilmiyorum — BT'ye
   soralım
5. **Komisyon, kargo, hizmet bedeli ve stopaj Logo'da nasıl kayıtlı?**
   (a) Platformun kestiği hizmet faturası olarak, platform carisine · (b) Muhasebe fişiyle gider hesabına, cari bağı yok ·
   (c) Hiç girilmiyor, yalnız net ödeme görülüyor · (d) Mali İşler'e soralım
6. **İlk aşamada veri yolu ne olsun?**
   (a) Yalnız panelden indirilen Excel (sipariş, iade, hesap ekstresi / settlement) · (b) Salt okuma API anahtarı şimdi
   verilecek (kimden?) · (c) Önce Excel, anahtar gelince API
7. **Önce hangi değer?**
   (a) Mutabakat + hakediş (kaçan fatura, fazla kesinti, geciken ödeme) · (b) Fiyat / stok önerisi (zarar altı ve
   stoksuz satış) · (c) Kampanya değerlendirmesi · (d) a ve b birlikte
8. **Fiyat önerisinin alt sınırı ve onay zinciri?**
   Alt sınır: (a) maliyet + gerçek kesinti + hedef marj (%… ?) · (b) liste fiyatının en çok %… altı · (c) yalnız uyarı, öneri
   yok. Onay: (i) e-ticaret sorumlusu hazırlar, finans onaylar, sorumlu panelde uygular · (ii) tek kişi hazırlar ve onaylar
   (önerilmez; mevcut kural «hazırlayan onaylayamaz»)

---

## 5. Sonraki adım

1. İzin gelince §2.5 sorgularını tek betikte, test sunucusunda, salt okuma olarak koş; sonuçları bu belgeye «ölçüldü»
   diye işle.
2. §4 cevapları gelince aşama 0'ı kapat: M42 eşlemesi, `TRENDYOL_CARI_ADLARI` / `AMAZON_*` ayarları, modele göre
   gereksizleşen aşamaların çıkarılması.
3. Aşama 1 ve 2 için iş biriminden **gerçek bir örnek dosya** iste: Trendyol hesap ekstresi, Amazon settlement ya da ödeme
   raporu. Kolon eş anlamlıları o dosyadan yazılır.

Kod bu kararlardan önce yazılmaz. *(2026-09-29: kararlar verildi — en üstteki «Kararlar»; uygulama §6.)*

---

## 6. Uygulama (2026-09-29): Aşama 0 ve Aşama 1

Kod `backend/semantic_bridge/channels/`: `pazaryeri_model.py` (Aşama 0), `pazaryeri_dosya.py` (hakediş ve Amazon
sipariş/iade dosyası), `mutabakat.py` (Aşama 1), `kaynak_mutabakat.py` (sorgu bilgisi), `pazaryeri_api.py` (uçlar);
SQL `channels/sql/mp_*.sql`. Ekranlar `src/canvas/channels/marketplace/` (ortak) + `trendyol|amazon/Model.tsx`,
`Reconcile.tsx`. Testler `backend/semantic_layer/tests/test_pazaryeri_mutabakat.py`.

### 6.1 Pazar yeri carisi nasıl bulunur (kural; koda sabit cari adı/kodu/kitap yok)

1. M42 cari eşlemesinde bu platforma bağlı (onaylı ya da aday) cari kodları;
2. kanal kodu (özel kod 2) bütünüyle bu platforma bağlanmışsa o kanaldaki cariler;
3. unvanında platformun adı (kapalı platform listesi `mapping.PLATFORMS`) ya da Yönetim ayarındaki adlardan biri
   (`TRENDYOL_CARI_ADLARI`, `AMAZON_CARI_ADLARI`, `CHANNEL_PLATFORM_HINTS`) kelime sınırıyla geçen ve başka bir platformu
   işaret etmeyen cariler (`mapping.name_candidate`); SQL `LIKE` ile aday çekilir, Python'da kelime sınırıyla süzülür;
4. panel sipariş numarası Logo faturasında bulunursa (Aşama 1) o faturaların türü ve cari sayısı Aşama 0'a ayrıca kanıttır.

### 6.2 Aşama 0 ölçümü (salt okuma; «Veriyi yenile»)

Son `PAZARYERI_MODEL_YIL` (2) yıl, `SEMANTIC_FIRMS` ile süzülmüş yıl→firma eşlemesi; her sorgu tarih süzgeçli:
fatura türü × cari × ay (`mp_fatura_turu`), hizmet satırları (`mp_hizmet`), fatura dışı cari hareketleri
(`mp_cari_hareket`), faturalanmamış sevk ve eski açık sevk (`mp_sevk`), sevk → fatura gecikmesi (`mp_fatura_gecikme`),
belge alanlarının doluluğu (`mp_anahtar_doluluk`), belge alanında platform adı geçen satış faturaları (`mp_belge_metni`);
CRM'de platform adlı firma kartları ve sipariş tipi × yıl (`mp_crm_firma`, pasif süzgeci bağlantıda). Ham toplamlar
`semantic_channel_meta › model:<platform>`; sınıflama her istekte bu toplamlardan.

### 6.3 Sınıflama kuralı

- **konsinye izi**: `PAZARYERI_KONSINYE_GUN` (30) günden eski faturalanmamış satış irsaliyesi ya da sevkten bu kadar
  günden geç faturalanan sevk;
- **toptan izi**: pazar yeri carisine toptan satış faturası (TRCODE 8);
- **kendi mağaza izi**: pazar yeri carisine perakende satış faturası (7); belge alanında platform adı geçen perakende
  fatura ya da bir ayda pazar yeri carisi sayısından çok farklı cariye kesilen fatura; panel siparişinin tüketici
  faturasında bulunması; satış faturası olmadan platformdan alınan hizmet faturası;
- tek iz → o model; konsinye + toptan → konsinye; kendi mağaza + öteki → **belirsiz (karma)**; iz yok → **belirsiz**
  (nedeniyle). Kanıt `PAZARYERI_GUCLU_AY` (3) farklı ayda görülürse «güçlü», azsa «zayıf».
- Kesinti bulgusu: pazar yeri carilerinden alınan faturalardaki hizmet satırları, kalem hizmet kartı adından kuralla
  (komisyon, kargo, hizmet bedeli, reklam, stopaj, ceza); yoksa «Kesinti Logo'da bulunamadı».
- Hakediş yolu: pazar yeri carilerinin fatura dışı alacak hareketleri (gelen havale, virman, dekont…).

### 6.4 Aşama 1 — mutabakat ve hakediş

- **Panel tarafı:** Trendyol sipariş ve iadesi M40 yüklemesinden (`semantic_trendyol_orders|claims`); Amazon sipariş/iade
  raporu ve iki platformun hakediş/ekstresi `pazaryeri_dosya` (`semantic_mp_orders|settlement|imports`). Hakediş satırı
  işaretli tutar (TİMAŞ lehine +); uzun biçimde `tutar` ya da `alacak − borç`, geniş biçimde kalem kolonları. Kolon eş
  anlamlıları platformların bilinen dışa aktarım başlıklarından; **gerçek TİMAŞ dosyasıyla doğrulanmadı** — tanınmayan
  başlıkta dosya reddedilir ve beklenen kolonları yazar.
- **Logo okuması** (`mutabakat.refresh`, «Veriyi yenile»): panel dosyalarının tarih aralığı ± `MUTABAKAT_TOLERANS_GUN`
  (15) içindeki satış, iade ve alış/hizmet faturalarının belge alanları bellekte taranır; panel sipariş numarası (ve
  ekstredeki belge numarası) hangi alanda geçiyorsa bağ kurulur. Portala yalnız eşleşen ya da pazar yeri carisine kesilen
  faturanın kimliği, türü, tarihi, NETTOTAL'i, cari kodu ve eşleşen alanın adı yazılır (belge metni kişisel veri
  olabilir, yazılmaz). Satırlar (kitap/adet, hizmet satırı) ve pazar yeri carilerinin fatura dışı hareketleri ayrıca.
- **Sınıflar:** eşleşti · tutar farkı (panel tutarı − NETTOTAL, eşik `MUTABAKAT_TUTAR_TOLERANS` 1 ₺) · eksik fatura ·
  fazla fatura (iptal siparişe fatura, bir siparişe fazla fatura, pazar yeri carisine kesilip panelde karşılığı yok) ·
  bekliyor · iptal. Durum sınıfı panelin durum metninden kuralla.
- **Hakediş:** kalem ve ay başına satış, iade, kesinti, net, ödeme; Logo kesintisi (hizmet satırı, KDV hariç) ve Logo
  tahsilatı ay başına yan yana; ekstre belge numaralarının Logo'da bulunan/bulunmayanı; hakedişte satışı olup Logo
  faturası olmayan siparişler; ödeme tarihi gelecekte olan satırlardan beklenen ödeme takvimi.
- **Yetki:** model uçları platform özet sayfasında; mutabakat `sayfa:trendyol-mutabakat` / `sayfa:amazon-mutabakat`;
  dosya `ozellik:trendyol.yukle` / `ozellik:amazon.yukle`; Excel `ozellik:veri.disa-aktar`.

### 6.5 Aşama 0 ölçüm sonucu (2026-09-29, test sunucusu, canlı Logo .25 + CRM .28, salt okuma) **[ölçüldü]**

Dönem 2025-01-01 – 2026-09-29. §0'daki «ölçülemedi» bu ölçümle kapandı.

| Platform | Sonuç | Başlıca kanıt | Kesinti Logo'da | Para |
|---|---|---|---|---|
| Trendyol | **Kendi mağaza, güçlü** | DSM Grup carisine (32001.01.DS001 + torba cari) 32.191 perakende satış faturası, 11,54 Mn ₺; belge alanında platform adı geçen 41.357 satış faturası, bir ayda en çok 3.038 farklı cari. Yan iz: 28 toptan fatura, 4.535 ₺ (%0,0) | Evet — platformdan alınan hizmet faturası: komisyon 1,78 Mn, kargo/nakliye 2,42 Mn, reklam 0,12 Mn ₺ (KDV hariç) | Gelen havale, 187 hareket, 8,45 Mn ₺ |
| Amazon TR | **Konsinye, güçlü** | Amazon Turkey carisine (12001.01.C28561) 371 toptan satış faturası, 73,53 Mn ₺; 2026-08-30'dan eski faturalanmamış 2.144 satış irsaliyesi satırı (13.726 adet). Yan iz: satıcı hesabı carisinde (32001.01.AM004) 5.283 perakende fatura, 1,88 Mn ₺ (%2,5) — Seller Central satışı da var | Evet — reklam 4,18 Mn, komisyon 0,25 Mn ₺ | Gelen havale, 157 hareket, 67,12 Mn ₺ |

Sonuç: §2.1'deki A (Trendyol satıcı mağazası) ve §2.2'deki C (Amazon konsinye, yanında küçük bir 3P) geçerli. Trendyol'da
tüketici faturası pazar yeri carisine toplu kesiliyor; bu yüzden Aşama 1'in sipariş numarası eşlemesi (belge alanları
~%100 dolu) anlamlı. Amazon'da mutabakat konsinye satış raporu ↔ fatura yolundan yürür.

### 6.6 Açık kalanlar

- Hakediş/ekstre ve Amazon rapor kolonları gerçek bir panel dosyasıyla doğrulanmalı (iş biriminden örnek dosya).
- Kesinti cari bağı olmayan muhasebe fişiyle giriyorsa (Mali İşler) bu sürüm bulamaz, ekranda öyle yazar; o yol ayrı iş.
- Aşama 2'nin «gerçek kesinti oranı → M42 katkı» bağı, Aşama 3 fiyat önerisi, Aşama 5 API kodlanmadı.
