# M21 — Dijital Pazarlama ve Reklam Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M21.txt` (ZEKİ_Moduller3.html), `ZEKİ_Veri_Haritasi2.html` (Reklam Girdileri, Dönüşüm Girdileri), `configs/semantic/knowledge/crm/table_descriptions.json` (2026-09-09), `configs/semantic/knowledge/logo/knowledge/rules/crm-timas.md` (Kural C20, C21), `configs/semantic/knowledge/logo/knowledge/caveats/logo-timas.md`, `configs/semantic/knowledge/logo/knowledge/metrics/logo-timas.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`, `docs/LLM-KAPISI.md`, `backend/semantic_bridge/seo_geo/`, `access.py`, `access_catalog.json`, `src/canvas/nav/navModel.ts`, kullanıcı belleği (seo-geo-module, tsoft-no-write, crm-tsoft-no-push-integration, logo-155-frozen-copy, no-tech-names-on-screens, no-silent-limits-rule).

> Kural: sunucuya bağlanılmadı. Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım** diye işaretlidir.

## 1. Modül ne işe yarar

Arama, sosyal medya ve pazaryeri reklamlarının harcamasını, sonucunu ve bütçesini tek ekranda toplar; kampanya bazında tıklama, maliyet ve satış getirisini (ROAS) raporlar; düşük performanslı reklamı ve bütçe kaydırma fırsatını önerir; yeni kampanya için hedef kitle ve kreatif brief taslağı hazırlar (iş tanımı M21: K1 kampanya optimizasyonu, K2 strateji ve hedefleme, K3 performans analizi).

TİMAŞ'ın bugünkü sorunu: CRM'de reklam için iki yapı var ama ikisi de karar desteği vermiyor. **Reklam Planı** (`new_reklamplaniBase`, 71 kayıt; mecra, tip, tutar, onay bitleri, teslim, fatura) — 68 planın hiçbirinde onay tarihi/onay biti ve teslim işareti dolu değil (caveats, Kural C20). **Pazarlama Bütçe Modülü** (`new_pazarlamamoduluBase`, 435 kayıt; pazarlama tipi Basın/Medya/Promosyon/Sosyal Medya/Dijital Pazarlama/Satış Kampanyası, mecra tipleri Facebook/Instagram/…/Influencer, Adwords/Seo/…/Website, tutar, başlangıç/bitiş) — ne kadar güncel tutulduğu **ölçülecek**. Reklam platformlarının kendi verisi (harcama, tıklama, dönüşüm) portala hiç gelmiyor; Google Analytics 4 ve Merchant erişimi yok (seo-geo-module belleği, 2026-09-25).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Dijital pazarlama / performans uzmanı | Pazarlama (TeamMembership «Pazarlama» 35; ayrı dijital ekip **varsayım**) | Her gün | Masaüstü |
| Reklam ajansı (dışarıdan) | CRM reklam planında `new_reklamajansi` alanı var → ajansla çalışıldığı **varsayım**; portala giriş AD hesabı ister | Haftalık | Masaüstü |
| Pazarlama müdürü | Pazarlama | Haftada 1 (bütçe, onay) | Telefon + masaüstü |
| E-ticaret sorumlusu | E-ticaret (T-soft sitesi; M34) | Haftada birkaç | Masaüstü |
| Finans / bütçe kontrol | Mali İşler (TeamMembership 10) | Ayda 1 (fatura, bütçe gerçekleşme) | Masaüstü |

Kimin reklam hesaplarını yönettiği (TİMAŞ içi mi, ajans mı) **uzmana sorulacak**.

## 3. Bugün bu iş nasıl yapılıyor

- **Performans uzmanı / ajans** (varsayım): kampanyalar reklam platformlarının kendi panellerinde kurulur ve izlenir; rapor platform ekranından ya da Excel'den haftalık hazırlanır. Satışa etkisi e-ticaret sitesinin paneli ve Logo satış raporu ayrı ayrı açılarak tahmin edilir. Tıkanma: harcama bir yerde, satış başka yerde; ROAS «platformun dediği» kadar.
- **Pazarlama müdürü**: bütçe CRM Pazarlama Bütçe Modülü'ne ya da Excel'e girilir (hangisinin güncel olduğu **ölçülecek**); reklam planı onay bitleri kullanılmıyor (C20).
- **Finans**: reklam faturası Logo'da hizmet alımı olarak (TRCODE 4, alınan hizmet) işlenir — hangi hizmet kartı/masraf merkezi olduğu **ölçülecek**.

## 4. İhtiyaçlar ve acı noktaları

**Performans uzmanı**
1. Tüm reklam kanallarının harcama/tıklama/dönüşümü tek tabloda, kitap bazında.
2. Satışla gerçek bağ: platformun iddia ettiği dönüşüm değil, e-ticaret kanalı net cirosu (Logo) ile karşılaştırma.
3. «Bu kampanyayı durdur / bütçeyi şuraya kaydır» önerisinin gerekçesiyle gelmesi.
4. Yeni kitap için hedef kitle ve kreatif brief taslağı (M15 planından).
5. Stokta olmayan ya da satıştan kalkmış kitaba reklam verilmediğinin uyarısı.

**Pazarlama müdürü**
1. Aylık bütçe kullanımı ve kalan bütçe (M46 hedefi gelince hedef–gerçekleşme).
2. Büyük bütçe değişikliğinin onaydan geçmesi (K3).
3. Tek sayfalık aylık rapor.

**Finans**
1. Platform harcaması ile Logo'ya işlenen fatura tutarının mutabakatı.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Performans uzmanı olarak bütün kanalların dünkü harcamasını tek ekranda görmek istiyorum, çünkü beş panel açmak sabahımı alıyor.
- Performans uzmanı olarak kampanyayı kitaba bağlamak istiyorum, çünkü kitap bazında ROAS'ı görmeden bütçe veremiyorum.
- Performans uzmanı olarak stoku bitmek üzere olan kitabın reklamı için uyarı almak istiyorum, çünkü boşa para harcıyoruz.
- Performans uzmanı olarak yeni kitap için hedef kitle ve brief taslağı almak istiyorum, çünkü her lansmanda sıfırdan yazıyorum.
- Pazarlama müdürü olarak bütçe kaydırma önerilerini telefondan onaylamak istiyorum, çünkü karar hızlı olmalı ama benden geçmeli.
- Finans olarak ay sonunda platform harcaması ile işlenen faturayı karşılaştırmak istiyorum, çünkü fark çıkınca kaynağını arıyoruz.

**Ana ekranlar ve akış**
- İlk açılış (`/timas/reklam`): üstte dönem seçici + dört gösterge (harcama, platform dönüşüm değeri, e-ticaret net ciro, pazarlama verimi = e-ticaret net ciro ÷ reklam harcaması); altında kanal × kampanya tablosu (kitap bağı, harcama, tıklama, TBM, platform ROAS, durum); sağda «Öneriler» (durdur/kaydır/stok uyarısı).
- En sık 3 işlem: (1) Harcama verisini içe aktar (platform dışa aktarım dosyası sürükle-bırak): 2 tık. (2) Kampanyayı kitaba bağla: 2 tık (arama kutusu). (3) Öneriyi onayla/reddet: 1 tık.
- Diğer ekranlar: Bütçe (ay × kanal plan/gerçekleşme), Brief taslakları, Aylık rapor.

**Zeki AI'a soracakları**
- «Geçen ay reklam harcaması kanal bazında ne kadardı?»
- «Eylülde en yüksek getirili beş kampanya hangisi?»
- «[Kitap] için ne harcadık, e-ticaret satışı ne oldu?»
- «Stoku iki haftadan az kalan ve reklamı süren kitaplar hangileri?»
- «Instagram'da tıklama başı maliyet son üç ayda nasıl değişti?»
- «[Kitap] için yetişkin okura dönük bir kampanya briefi yaz.»

**Otomasyon katmanı**
- K1 (ilk sürümde yalnız okuma/hesap): verinin içe alınması, kampanya–kitap eşleşme önerisi, günlük hesaplar, anomali işareti. **Reklam platformunda bütçe değiştirme, teklif verme, reklam durdurma ilk sürümde yok** — dış sisteme yazma kullanıcı kararıdır (T-soft yasağıyla aynı ilke; bölüm 8).
- K2: bütçe kaydırma/durdurma önerisi, yeni hedef kitle, brief → performans uzmanı platformda kendisi uygular, uygulandı işareti koyar.
- K3: kampanya sonu değerlendirme, ayı aşan bütçe değişikliği → pazarlama müdürü karar verir.
- İş tanımındaki «A/B test otomatik kazanan seçimi» ilk sürümde rapor olarak: istatistiksel anlamlılık hesaplanır, kazanan önerilir, uygulama insanda.

**Bildirim/uyarı**
- Performans uzmanına: günlük harcama planın %X üstünde (eşik ayar, varsayılan yok — kullanıcı tanımlar), stok uyarısı, veri 2 gündür gelmedi.
- Pazarlama müdürüne: onay bekleyen öneri, ay sonu bütçe aşımı tahmini. Kanal: portal Uyarılar + e-posta (mevcut `alerts` altyapısı).

**Onay ve yetki**
- `sayfa:reklam`; `ozellik:reklam.duzenle` (içe aktarma, eşleme, bütçe planı yazma); `ozellik:reklam.onay` (explicit; öneri ve bütçe onayı); maliyet/ciro rakamlarını görmek sayfa yetkisine dahil, Zeki AI veri kapsamı Aşama C'de `veri:pazarlama` ile daraltılabilir.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kampanya harcama, gösterim, tıklama, dönüşüm | Reklam platformları (Google Ads, Meta, TikTok Ads; pazaryeri reklamları M40/M42) | Portala hiç bağlanmadı; hesap sahipliği ve API yetkisi **ölçülecek** | İlk sürüm: platform dışa aktarım dosyası (CSV/Excel) içe aktarma; sonraki: resmî API yalnız okuma |
| Reklam planı ve mecra sözlüğü | CRM `new_reklamplaniBase` (71), `new_reklammecrasiBase` (50), `new_reklamtipiBase` (44), `new_mecratipiBase` (48), `new_new_reklamplani_new_kitapBase` (113) | Onay/teslim alanları boş (C20); güncelliği **ölçülecek** | Plan–gerçekleşme bağı yok |
| Pazarlama bütçesi | CRM `new_pazarlamamoduluBase` (435; `new_pazarlamatipi`, `new_mecratipi4/5`, `new_tutar`, `new_baslangictarihi`, `new_bitistarihi`) + `new_new_pazarlamamodulu_new_kitapBase` (202) | Güncelliği **ölçülecek** | M46 bütçe modülü kodlanmadı |
| E-ticaret net cirosu | Logo: cari kanal `CLCARD.SPECODE2 = 'E-TICARET'` (katalog ölçüsü `kanal_net_ciro`, görünüm `v_channel_net`); satır bazında `STLINE.LINENET` | .155 kopyası **2026-08-17'de donmuş** | Canlı Logo erişimi TİMAŞ BT kararı |
| Sipariş/UTM bazlı dönüşüm | T-soft sipariş kaydı (yalnız okuma) ya da GA4 | T-soft'tan ürün okunuyor; sipariş ve UTM okuma **ölçülecek**. GA4 erişimi **yok** | Kampanya→sipariş bağı kurulamayabilir → karşılaştırma kanal düzeyinde kalır |
| Stok | Logo stok bakiyesi (`STLINE` IOCODE, «Stok bakiyesi» tanımı metrics), `management/sql/baski_oneri/logo_depo_stok.sql` | Var (donmuş kopya uyarısıyla) | — |
| Kitap listesi, satıştan kalkma | CRM `new_kitapBase` (`new_kitap_yayincilikstatusu`), SEO modülü `semantic_seo_crm_books` | Var | — |
| Arama sorgusu verisi | Search Console (SEO modülü) | Var (zeki@ görüyor, sahip değil) | — |
| Reklam faturası | Logo alınan hizmet (TRCODE 4) | Hangi hizmet kartı **ölçülecek** | Mutabakat için eşleme |
| Onaylı kreatif | M19 | Kodlanmadı | Stüdyo pazarlama kiti kısmen karşılar |

## 7. Diğer modüllerle bağ

- Girdi: M46 (kitap bazlı bütçe ve satış hedefi), M15 (kanal ve bütçe dağılımı), M18 (aylık plan), M19 (onaylı kreatif), M43 stok, M25 (arama sorguları), M34/M40/M42 (pazaryeri ve site satışları).
- Çıktı: M18 (performans geri beslemesi), M46 (bütçe gerçekleşme), M16 lansman ayı raporu, Genel bakış (pazarlama verimi kartı), Uyarılar.

## 8. Kısıtlar

- **Dış platforma yazma yok (ilk sürüm).** İş tanımındaki K1 «otomatik bütçe optimizasyonu / düşük performanslı reklamı otomatik durdurma» para harcayan bir dış sisteme yazmaktır; T-soft yasağıyla aynı ilkeyle kullanıcı açık karar verene kadar yapılmaz. Karar verilirse: tek tek onaylı işlem, günlük üst sınır kullanıcı tanımlı, her işlem `admin.audit`'e.
- T-soft'a yazma yasak; T-soft'tan yalnız okuma (`seo_geo/connections.READ_ONLY` listesi).
- CRM'e yazma yok; bağlar ve bütçe planı `semantic_ads_*` tablolarında.
- Ekranda teknoloji adı yok (platform adları — Google, Meta, Instagram — müşterinin kullandığı hedef olduğu için kalır; bizim model/altyapı adımız yazmaz).
- Demo veri yok: içe aktarma yapılmadıysa ekran «veri yok, şu dosyayı yükleyin» der. Sayı tavanı yok.
- Platform API kimlik bilgilerini kullanıcı Yönetim ekranından girer; Claude girmez.
- KVKK: benzer kitle (lookalike) için müşteri e-posta/telefon listesi platforma yüklenmesi kişisel verinin yurt dışına aktarımıdır; ilk sürümde yapılmaz, hukuka sorulur. Reklam metinleri Ticari Reklam ve Haksız Ticari Uygulamalar mevzuatına uymalıdır (indirim/«en çok satan» iddiası kanıtlanabilir olmalı).
- Logo satış verisi donmuş kopyada 2026-08-17'de bitiyor; her ekranda «satış verisi şu tarihe kadar» yazılmalı.

## 9. Kapsam önerisi

**İlk sürüm**
- Harcama içe aktarma: platform dışa aktarım dosyası (kolon eşleme bir kez kaydedilir), günlük satır.
- Kampanya ↔ kitap bağı (Zeki önerir, uzman onaylar), CRM reklam planı ve pazarlama bütçe kayıtlarının okunması.
- Gösterge: harcama, TBM, tıklama, platform ROAS, e-ticaret kanalı net ciro, pazarlama verimi; dönem ve kanal süzgeci.
- Uyarılar: stok bitiyor ve reklam sürüyor, satıştan kalkmış kitap reklamı, veri gelmedi.
- Bütçe planı (ay × kanal) ve gerçekleşme.
- Brief taslağı (K2) ve aylık rapor (PDF).

**Sonraki sürüm**
- Resmî API ile yalnız okuma bağlantısı (Google Ads, Meta Marketing, TikTok Ads) — hesap sahibi ve yetki müşteriden.
- A/B test anlamlılık hesabı.
- Kullanıcı kararıyla: onaylı öneriyi platforma işleme (yazma).
- M46 hedefleriyle hedef–gerçekleşme.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/connections.py` (dış bağlantı ayarı, yalnız okuma listesi deseni), `seo_geo/store.py` (T-soft ürün kaydı, EAN-13 → CRM kitap bağı), `seo_geo/crm.py` (kitabın satış/hak durumu).
- `backend/semantic_bridge/management/` (`{satis:<yıl>}` yer tutucusu, `logo_depo_stok.sql`, `logo_fiyat.sql`).
- `backend/semantic_bridge/alerts.py` (eşik kuralı ve e-posta), `reports.py` (aylık rapor gönderimi), `board.py` (Genel bakış kartı).

## 10. Uzmanlara sorulacak sorular

1. Reklam hesaplarını kim yönetiyor (TİMAŞ içi / ajans)? Hesap sahibi e-posta kim?
2. Bütçe bugün nerede tutuluyor: CRM Pazarlama Bütçe Modülü mü, Excel mi?
3. Reklam faturası Logo'da hangi hizmet kartına/masraf merkezine işleniyor?
4. E-ticaret sitesinde siparişe kampanya kaynağı (UTM) yazılıyor mu?
5. Otomatik bütçe/durdurma işlemi ileride istenirse sınırları ne olmalı (günlük tutar, hangi kanal)?

## 11. Başarı ölçütü

- Haftalık raporu hazırlama süresi (bugünkü süre sorulacak) → 15 dakikanın altı.
- Kitaba bağlı kampanya harcaması oranı (bağsız harcama ≤ %10).
- Stoku biten kitaba giden reklam gün sayısı (uyarı sonrası 1 günün altında).
- Platform harcaması ile Logo faturası farkı ay sonunda açıklanmış.
- Önerilerin onay/red oranı ve onaylanan önerinin 14 gün sonra sonucu.

## 12. Uzman gözüyle en iyi sistem

*15 yıllık performans pazarlama müdürü gözüyle.*

İyi yayınevleri reklamı kitap bazında yönetir: her kampanyanın bir kitabı (ya da serisi) vardır, bütçe kitabın yaşam evresine göre (ön sipariş, lansman ayı, backlist canlandırma) verilir, stok ve fiyat reklamla aynı ekranda görünür. Sektördeki iyi araçların ortak özelliği veriyi tek yerde toplaması ve kuralları (ör. «harcama X'i aştı ve dönüşüm yok → uyar») şeffaf tutmasıdır; kötü araçlar platformun kendi ROAS'ını gerçek sanar. Olgun ekipler platform ROAS'ının yanında **toplam pazarlama verimini** (kanal cirosu ÷ toplam reklam harcaması) izler, çünkü platformlar aynı satışı birden çok kez sahiplenir. TİMAŞ için mükemmel sistem: Logo'daki e-ticaret kanal cirosunu ve stoku reklam harcamasıyla aynı günlük tabloya koyan, önerisini gerekçesiyle veren, **para harcayan her adımı insana bırakan** bir kokpit.

**Bir iş günü**
- 09:00 Açılış: dünkü harcama 4 kanalda; bir kampanya planın %40 üstünde; iki kitapta stok 10 günün altında ve reklam açık (kırmızı).
- 09:10 Stok uyarılı kitaplar için «durdur» önerisini platformda uygular, portalda «uygulandı» işaretler.
- 10:00 Yeni ay lansmanları: M15 planından gelen 3 kitap için Zeki'nin hedef kitle + brief taslağı; biri düzeltilip ajansa gönderilir.
- 12:00 Haftalık dışa aktarım dosyaları yüklenir; kampanya–kitap eşleşmesinde 2 belirsiz kayıt elle bağlanır.
- 15:00 Pazarlama müdürü telefondan bütçe kaydırma önerisini onaylar (backlist seriden lansman kitabına).
- 17:00 Gün sonu: pazarlama verimi grafiği; satış verisinin hangi güne kadar geldiği üstte yazılı.

**«Bunu görürsem hemen kullanırım»**
1. Kitap bazında harcama ile e-ticaret cirosu yan yana.
2. «Stok bitiyor, reklam açık» uyarısı.
3. Tek dosya yüklemeyle bütün kanalların ortak tabloya girmesi.

**«Bunu yaparsanız kullanmam»**
1. Onayım olmadan platformda bütçe değiştiren ya da reklam durduran otomasyon.
2. Platformun ROAS'ını «gerçek getiri» diye sunan, finansla tutmayan rapor.
3. Satış verisinin tarihini gizleyen ekran (donmuş veriyi güncel sandırmak).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Harcama içe aktarma | — | — | Kolon adı eşleme önerisi (ilk yüklemede; «Maliyet/Cost/Harcanan» → harcama) | Dosya biçimleri değişken; eşleme bir kez insan onayıyla kaydedilir |
| Kampanya → kitap bağı | — | `new_kitapBase.new_name`, `new_ean13`, `new_StokKodu`; `new_new_reklamplani_new_kitapBase` | Kampanya adından kitap adayı + güven (kapalı seçim: aday listesinden biri ya da «yok») | Eşleştirme; tek token + olasılık yöntemi uygun |
| E-ticaret cirosu | `LG_411_01_STLINE` (`LINENET`, `TRCODE` 7,8,9 − 2,3, `LINETYPE=0`, `CANCELLED=0`, `INVOICEREF<>0`) ⨝ `LG_411_CLCARD.SPECODE2='E-TICARET'`; katalog `kanal_net_ciro` | — | — | Rakam SQL'den; model üretmez |
| Kitap bazlı ciro | `V_SatisRaporu_<yıl>` (`[Malzeme/Hizmet Kodu]`, `[Yıl]*12+[Ay]`, `[Net Tutar]`, `[Satır Türü]=N'Malzeme'`) | `new_kitapBase.new_StokKodu` | — | Logo kayıt sistemi |
| Stok uyarısı | Stok bakiyesi (`STLINE` IOCODE 1,2 − 3,4; güncel kopya) | — | — | Kural |
| Bütçe | — | `new_pazarlamamoduluBase` (`new_tutar`, `new_pazarlamatipi`, `new_mecratipi4/5`) | — | Okuma |
| Öneri gerekçesi | Yukarıdaki rakamlar | — | Öneri başına 1–2 cümle gerekçe | Rakamı yorumlar, üretmez |
| Brief taslağı | Kitabın geçmiş satışı | `new_ozet`, `new_hedefkitle`, `new_hedefkitleyasbaslangic/bitis`, `new_turlertext` | Hedef kitle ve mesaj taslağı | Metin işi |
| Aylık rapor özeti | Ölçüler | — | 5 cümlelik yorum | — |

Model yalnız LLM kapısından: `rt.llm_for("reklam")` (ekranda), gece eşleştirme `rt.llm_for("reklam", BATCH)`.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/ads.py` (tablolar, hesaplar, öneri kuralları — saf işlevler), `ads_sources.py` (Logo/CRM SQL'leri, içe aktarma ayrıştırıcıları), `ads_api.py` (`register(app, deps)`).

**Tablolar**
- `semantic_ads_accounts` (id, tenant_id, platform, account_label, currency, import_mapping_json, created_by)
- `semantic_ads_campaigns` (id, tenant_id, account_id, platform_campaign_id, name, status, crm_book_id NULL, series NULL, link_source [elle/zeki], link_confidence, first_seen, last_seen)
- `semantic_ads_daily` (campaign_id, day, spend, impressions, clicks, conversions, conv_value, currency, import_id; PK campaign_id+day)
- `semantic_ads_imports` (id, account_id, file_name, rows, period_from, period_to, created_by, created_at)
- `semantic_ads_budget` (id, tenant_id, month, channel, planned, note, created_by)
- `semantic_ads_suggestions` (id, kind [durdur/kaydir/stok/veri-yok/ab-test], campaign_id, payload_json, reason, status [yeni/onaylandı/uygulandı/reddedildi], decided_by, decided_at)
- `semantic_ads_briefs` (id, crm_book_id, body, status, created_by)

**Uçlar** (`/api/v1/ads/*`): `GET meta`, `GET overview?from=&to=&channel=`, `GET campaigns`, `PATCH campaigns/{id}` (kitap bağı), `POST imports` (dosya), `GET imports`, `GET budget?year=`, `PUT budget`, `GET suggestions`, `POST suggestions/{id}/decide`, `POST briefs`, `GET report/export.pdf|xlsx`, `POST run-due` (SYSTEM).

**Ekranlar** — `src/canvas/ads/` (`AdsOverview.tsx`, `AdsCampaigns.tsx`, `AdsImport.tsx`, `AdsBudget.tsx`, `AdsBriefs.tsx`); rota `/timas/reklam` (+ `/kampanyalar`, `/yukle`, `/butce`, `/brief`). Menü: `pazarlama` alanı, bölüm `section: 'Kampanya'`, öğe `{ id: 'reklam', label: 'Reklam', icon: BadgeDollarSign, hint: 'Harcama, getiri ve bütçe' }`. Kampüs: `modules.json` M21 çalışan. Telefon: öneri onay kartları tek sütun.

**Yetki** — `sayfa:reklam`; `ozellik:reklam.duzenle`; `ozellik:reklam.onay` (explicit). `access.py`: `("/api/v1/ads/run-due", SYSTEM)`, `("/api/v1/ads/", frozenset({page("reklam")}))`; FEATURE_RULES POST/PUT/PATCH `^/api/v1/ads/(imports|campaigns|budget|briefs)` → `ozellik:reklam.duzenle`; `…/suggestions/[^/]+/decide` ucun içinde `ozellik:reklam.onay`; export → `ozellik:veri.disa-aktar`. Yönetim → ayarlar: `ADS_*` anahtarları (`admin.conf`).

**Zamanlayıcı** — `scripts/server/timas-ads.timer` günde bir 07:30: öneri kurallarını koşar (stok, veri gelmedi, bütçe aşımı), Logo e-ticaret cirosunu önbelleğe alır. API bağlantısı eklenince aynı iş gece veri çeker.

**Kabul testleri**
1. E-ticaret net cirosu (dönem): ekran = `SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET WHEN s.TRCODE IN (2,3) THEN -s.LINENET END) FROM LG_411_01_STLINE s JOIN LG_411_CLCARD c ON c.LOGICALREF = s.CLIENTREF WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND c.SPECODE2 = 'E-TICARET' AND s.DATE_ >= '<bas>' AND s.DATE_ < '<bit>'` ve katalog `kanal_net_ciro` sorusu aynı sonucu vermeli (2025 dönemi için `LG_211_*`).
2. Kitap bazlı ciro: seçilen kitap = `V_SatisRaporu_411` üzerinde `[Malzeme/Hizmet Kodu] = '<new_StokKodu>' AND [Yıl]*12+[Ay] BETWEEN … AND [Satır Türü] = N'Malzeme'` toplamı (iade düşülmüş).
3. İçe aktarma: yüklenen dosyanın harcama toplamı = `SELECT SUM(spend) FROM semantic_ads_daily WHERE import_id = '<id>'` (kuruş farkı 0).
4. CRM bütçe: ekrandaki «CRM bütçe kaydı» toplamı = `SELECT SUM(new_tutar) FROM Timas_MSCRM.dbo.new_pazarlamamoduluBase WHERE statecode = 0 AND new_baslangictarihi < '<bit>' AND new_bitistarihi >= '<bas>'`.
5. Reklam planı: ekran sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_reklamplaniBase WHERE statecode = 0` (C20'de 68).
6. Stok uyarısı: uyarılı her kitabın stok bakiyesi, metrics «Stok bakiyesi» tanımıyla doğrudan SQL'de aynı çıkmalı.
7. Veri sınırı: ekrandaki «satış verisi şu güne kadar» = `SELECT TOP 1 [Fatura Tarihi] FROM dbo.V_SatisRaporu_411 ORDER BY [Fatura Tarihi] DESC`.

**Bağımlılık** — Bağımsız kodlanabilir; M46 gelince bütçe hedefi bağlanır. M19/M15 beklenmez. API bağlantısı müşteriden yetki gelince ayrı iş.

**Tahmini büyüklük** — L (3+ gün): içe aktarma + eşleme + hesaplar + 5 ekran + öneri kuralları.
