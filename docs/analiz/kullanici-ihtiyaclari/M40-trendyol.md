# M40 — Trendyol Mağaza Yönetimi: kullanıcı ihtiyaç analizi

Durum: kod var (main) — ilk sürüm: yalnız okuma + panel dosyası (kullanıcı kararı 2026-09-28); test sunucusunda kabul bekliyor (testler koordinatörde) · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M40.txt`, `specs/M34.txt`, `specs/M35.txt`, `specs/M42.txt`,
`ZEKİ_Veri_Haritasi2.html` (M40 satırları: "Trendyol Seller Panel API", "Stok ve fiyat verileri (LOGO)", "Mağaza puanı ve müşteri
yorumları", "Sponsorlu kampanya ROAS"), `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md` (§4), `configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`,
`configs/semantic/knowledge/logo/knowledge/rules/logo-erp.md`, `backend/semantic_bridge/seo_geo/connections.py`, bellek: `tsoft-no-write`,
`customer-vm-web-watch-off`, `no-tech-names-on-screens`, `seo-geo-module`, `logo-155-frozen-copy`. Bu belge M42 analizindeki ortak kanal
paketine (`backend/semantic_bridge/channels/`) dayanır. Sunucuya bağlanılmadı; yeni ölçüm yok.

## 1. Modül ne işe yarar

İş tanımı (M40): Trendyol mağazasını yönetmek — Seller API ile stok/fiyat senkronu, sipariş onayı ve kargo etiketi, iade/iptal
(K1); vitrin ve öne çıkan ürün stratejisi, sponsorlu ürün kampanya planı, mağaza puanını koruma, kategori sıralaması iyileştirme
(K2). Çıktılar: mağaza panosu (satış, görüntülenme, puan, sipariş durumu), optimizasyon planı, haftalık rapor.

**Bugünkü durum (kanıtla):** CRM'de Trendyol'a ait bir entegrasyon, cari ya da sipariş izi **yok** — tek iz 2020-09-23 tarihli
"Trendyol Deneme Siparisi" firma kartı (eski B2C sitesi testi). Diğer pazar yerleri (Kitapyurdu, D-MARKET/Hepsiburada, Amazon)
CRM'de toptan cari; Trendyol'un Logo'da cari olup olmadığı **ölçülmedi**. Yani TİMAŞ'ın Trendyol'da (a) kendi satıcı mağazası mı
var, (b) Trendyol'a toptan mı satıyor, (c) Trendyol'da yalnız başka satıcılar (kitapçılar/dağıtıcılar) mı TİMAŞ kitabı satıyor —
**bilinmiyor**. İş tanımının tamamı (a)'yı varsayıyor. Bu, modülün ilk ve en kritik sorusudur (§10, Soru 1).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Pazar yeri / Trendyol mağaza sorumlusu | Birim kanıtı yok (varsayım: e-ticaret ekibi ya da dışarıdan ajans) | Her gün, gün içinde çok kez | Masaüstü + telefon |
| E-ticaret müdürü | Varsayım (M42 ile aynı kişi olabilir) | Haftalık | Masaüstü |
| Pazarlama (sponsorlu ürün bütçesi, kampanya) | Pazarlama (35 kişi, TeamMembership) | Kampanya dönemi | Masaüstü |
| Müşteri hizmetleri (soru-cevap, yorum yanıtı) | Varsayım | Her gün | Masaüstü |
| Depo / sevkiyat (mağaza siparişi hazırlığı) | Depo | Her gün (kendi mağazası varsa) | Masaüstü |
| Yönetim (haftalık rapor) | — | Haftalık | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

- **Kanıt yok.** Kendi mağaza varsa iş Trendyol satıcı panelinde elle (varsayım); stok/fiyatın Logo'dan nasıl gittiği (T-soft pazar
  yeri modülü, entegratör, elle Excel) bilinmiyor — CRM analizi aynı soruyu BT'ye bırakmış (`crm-eticaret-entegrasyon` §7.5 soru 11).
- Trendyol'a toptan satış varsa: sipariş CRM'de tip "Pazaryeri" (9) altında olabilir (dağılım ölçülmedi), fatura Logo'da E-TICARET
  kanalında bir cari (Trendyol'un tüzel kişiliği) olarak görünür — **ölçülecek**.
- Yorum/puan ve sponsorlu ürün raporları: panelden (varsayım); portalda hiçbir iz yok.

## 4. İhtiyaçlar ve acı noktaları

**Mağaza sorumlusu (kendi mağaza varsayımıyla)**
1. Stok farkı: Trendyol'da satışa açık adet ↔ Logo depo stoğu (fazla satış/iptal riski ve stokta varken kapalı ürün).
2. Fiyat tutarlılığı: Trendyol fiyatı ↔ liste fiyatı ↔ timas.com.tr fiyatı; kâr altı satış uyarısı.
3. Sipariş ve iade durumu: bekleyen paket, geciken kargo, iade nedeni dağılımı.
4. Yorum ve sorular: cevapsız soru, olumsuz yorum, kitap bazında puan.

**E-ticaret müdürü / pazarlama**
1. Kitap bazında Trendyol satış hızı ve diğer kanallarla kıyas (M42 karnesi).
2. Sponsorlu ürün harcaması ↔ satış (veri varsa).
3. Haftalık özet: ne sattı, ne iade oldu, ne kaçtı.

**Toptan satış senaryosunda** yukarıdakilerin yerine: Trendyol carisine faturalanan adet/iade/vade (M42 karnesinde bir satır).

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Mağaza sorumlusu olarak Trendyol'da stokta görünen ama depoda olmayan kitapları sabah görmek istiyorum, çünkü iptal ve puan düşüşünü önlerim.
- Mağaza sorumlusu olarak depoda olup Trendyol'da satışa kapalı kitapları görmek istiyorum, çünkü kaçan satışı açarım.
- Mağaza sorumlusu olarak cevaplanmamış müşteri sorularını ve olumsuz yorumları kitap bazında görmek istiyorum, çünkü yanıt süresi puanı etkiler.
- Mağaza sorumlusu olarak olumsuz yoruma Zeki AI'dan yanıt taslağı almak istiyorum, çünkü tutarlı ve hızlı yanıt veririm (gönderimi ben yaparım).
- E-ticaret müdürü olarak Trendyol'un haftalık satış ve iade özetini telefonda okumak istiyorum.
- Pazarlama uzmanı olarak kampanya dönemine girmeden hangi kitapların vitrine uygun olduğunu (stok × satış hızı × sezon) görmek istiyorum.

**Ana ekranlar ve akış**
- Açılış (`/trendyol`): bağlantı durumu (bağlı değilse neyin gerektiği açıkça), dün/bu hafta sipariş-ciro-iade, stok farkı sayısı,
  cevapsız soru, olumsuz yorum, veri günü.
- Sekmeler: Ürünler (Trendyol durumu × Logo stok × fiyat), Siparişler ve iadeler, Sorular ve yorumlar, Vitrin önerisi, Haftalık rapor.
- En sık 3 işlem: stok farkı listesini Excel'e almak (2 tık), bir yoruma taslak yanıt almak ve kopyalamak (3 tık), haftalık raporu açmak (1 tık).

**Zeki AI'ya soracakları örnek sorular**
- "Trendyol'da geçen hafta en çok iade edilen 10 kitap ve iade nedenleri?"
- "Trendyol'da stokta görünüp depoda bitmiş kitaplar hangileri?"
- "Trendyol fiyatı liste fiyatının %X altına düşmüş kitaplar?"
- "Son 30 günde 3 yıldızın altında yorum alan kitaplar?"
- "Okul sezonu için vitrine hangi 20 kitabı koymalıyız?"
- "Trendyol'un bu ayki cirosu Hepsiburada'ya göre nasıl?"

**Otomasyon katmanı**
- K1 (tam otomatik, **salt okuma**): ürün, stok, fiyat, sipariş, iade, soru ve yorum okuma; fark ve eşik listeleri; haftalık rapor.
  İş tanımındaki K1 "stok/fiyat senkronizasyonu, sipariş onayı, kargo etiketi, iade işlemi" **mağazaya yazmadır** → bu analizde
  önerilmez; **açık soru** (kullanıcı kararı gerekir, §10 Soru 2). Karar verilene kadar sistem "öneri + fark listesi" üretir,
  mağazaya hiçbir şey göndermez.
- K2 (Zeki önerir, insan onaylar): vitrin/öne çıkarma listesi, sponsorlu ürün brief'i, yorum yanıt taslağı, başlık/açıklama önerisi
  (M25/M34 ile ortak). Onay portal kaydıdır.
- K3: kampanya bütçesi, fiyat kararı. K4: platform sözleşmesi ve komisyon pazarlığı.

**Bildirim / uyarı**
- Mağaza sorumlusu: stokta-görünüp-depoda-yok (her 15 dk uyarı kontrolü, portal zili + e-posta), cevapsız soru > N saat.
- E-ticaret müdürü: pazartesi 08:30 haftalık rapor (planlı rapor).

**Onay ve yetki (öneri)**
- `sayfa:trendyol` — e-ticaret, pazarlama, müşteri hizmetleri, yönetim.
- `ozellik:trendyol.oneri-karar` (vitrin/sponsorlu/metin önerisi onayı) — açıkça verilir.
- `ozellik:trendyol.baglanti` (API kimliği girme/test) — yalnız yönetici (Yönetim ekranı).
- `ozellik:magaza.yaz` — **tanımlanmaz**; mağazaya yazma kararı verilirse ayrı ve açıkça verilen bir anahtar olarak eklenir.

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| TİMAŞ'ın Trendyol ilişkisi (satıcı mı, toptan mı) | Kullanıcı + Logo `CLCARD` (DEFINITION_ Trendyol'un tüzel adıyla), CRM `AccountBase` | CRM'de yalnız 2020 test kaydı | **Ölçülecek + sorulacak** (en kritik) |
| Ürün listesi, satışa açıklık, Trendyol stok/fiyat | Trendyol satıcı API'si (ürün okuma) | Bağlantı **yok** | Satıcı kimliği + API anahtarı (müşteri Yönetim ekranından girer) |
| Sipariş/paket, kargo durumu | Satıcı API'si (sipariş/paket okuma) | Yok | Aynı |
| İade/talep | Satıcı API'si (iade okuma) | Yok | Aynı |
| Müşteri soruları | Satıcı API'si (soru-cevap okuma) | Yok | Aynı |
| Ürün yorumları ve puan, mağaza puanı | API kapsamı **belirsiz** (varsayım: yorum/mağaza puanı satıcı API'sinde tam olmayabilir) | Yok | Panel dışa aktarımı yüklenebilir (Excel) |
| Görüntülenme, tıklama, sponsorlu ROAS | Reklam paneli; API kapsamı belirsiz (varsayım) | Yok | Panel raporu yükleme (Excel) |
| Hakediş/komisyon | Satıcı API'si finans okuma (varsayım) ya da Logo'daki Trendyol faturaları | Yok | Ölçülecek |
| Depo stoğu | Logo (M43) | M43 analizi | M43'e bağlı |
| Liste fiyatı | Logo `PRCLIST` (PTYPE 2, aktif, TL), CRM `new_kdvdahilfiyat` | Tanımlı | Esas kaynak Soru 4 |
| Barkod eşleme | CRM `new_kitapBase.new_ean13`, Logo `ITEMS.CODE` | SEO modülü EAN-13 ile bağlıyor | Trendyol barkodunun EAN-13 olup olmadığı ölçülecek |
| Kategori sıralaması / rakip | Kazıma yasak (müşteride web taraması kapalı) | — | Yalnız resmî API sağlarsa |
| Toptan senaryo: fatura, iade, vade | Logo `STLINE` faturalı satır, Trendyol carisi | Kanal ölçüleri var | Cari **ölçülecek** |

## 7. Diğer modüllerle bağ

- Girdi: M42 ortak kanal paketi ve karnesi, M43 depo stoğu, M35 kampanya takvimi, M25/M34 ürün içeriği önerileri, M44 kargo.
- Çıktı: M42 çok kanal panosu (Trendyol satırı), M35 (vitrin/kampanya önerisi), M51 müşteri hizmetleri (soru/yorum), M45 finans (hakediş).
- M34 ile tek pano: M34'ün platform panosu = M40/M41/M42 sekmeleri.

## 8. Kısıtlar

- **Mağazaya yazma yok** (stok, fiyat, sipariş onayı, etiket, iade onayı, yorum yanıtı gönderimi). Yazma, kullanıcının açık kararı ve
  ayrı yetki anahtarıyla ileride eklenebilir; şimdilik taslak/öneri.
- T-soft'a yazma yasak (fiyat karşılaştırması için yalnız okunur).
- Müşteride web taraması kapalı: rakip/kategori sıralaması kazınmaz.
- KVKK: sipariş ve soru/yorumdaki müşteri adı, adresi portala alınmaz ya da maskelenir; model istemine kişisel veri girmez.
- Ekranda teknoloji adı yok (Trendyol müşteri platformu adı olarak yazılır); demo veri yok — bağlantı yoksa ekran boş ve nedenini söyler;
  sayı tavanı yok.
- API kimliği yalnız Yönetim ekranından girilir, ekrana ve günlüğe yazılmaz.

## 9. Kapsam önerisi

**İlk sürüm (bağımlılığa göre iki yol)**
- Her durumda: Logo'da Trendyol carisi varsa M42 karnesinde Trendyol satırı (toptan senaryo) — dış bağlantısız.
- Kendi mağaza ve API anahtarı gelirse: salt okunur ürün + sipariş + iade + soru okuma; stok farkı (Trendyol ↔ Logo), fiyat farkı
  (Trendyol ↔ liste ↔ timas.com.tr), iade nedeni dağılımı; haftalık rapor.
- API yoksa ya da kapsamı dışındaysa: panel dışa aktarımlarının (ürün, sipariş, yorum, reklam raporu Excel) yüklenmesi — gerçek veri,
  demo değil.

**Sonraki sürüm**
- Yorum sınıflama + yanıt taslağı; vitrin önerisi (stok × satış hızı × sezon); sponsorlu ürün brief'i.
- Mağazaya yazma (yalnız kullanıcı kararıyla, ayrı anahtar, önce tek ürün değil "önizleme + onay" akışı).

**Mevcut kodda yeniden kullanılacaklar**
- M42 `channels/` paketi (`platforms.py` salt okunur taban sınıf, `mapping.py`, `store.py`).
- `seo_geo/connections.py` `READ_ONLY` koruma deseni ve kimlik saklama (`admin.conf`), `seo_geo/crm.py` EAN-13 bağı.
- `alerts.py`, `reports.py`, `board_excel.py` (Excel okuma/yazma), `result_files.py` (yüklenen dosya).

## 10. Uzmanlara sorulacak sorular

1. TİMAŞ'ın Trendyol'da kendi satıcı mağazası var mı? Yoksa Trendyol'a toptan mı satıyorsunuz, ya da Trendyol'da kitaplarınızı yalnız bayiler mi satıyor?
2. Mağaza varsa: bu modül mağazaya **yazmalı mı** (stok/fiyat güncelleme, sipariş onayı, yorum yanıtı), yoksa hep salt okuma + öneri mi kalmalı? Kim onaylar?
3. Stok ve fiyat Trendyol'a bugün kim/hangi araçla gidiyor (T-soft pazar yeri modülü, entegratör, elle)? Çakışmayı nasıl önlüyorsunuz?
4. Trendyol fiyatının esası nedir: liste fiyatı mı, timas.com.tr fiyatı mı, kampanyaya göre ayrı mı? Alt sınır (zarar eşiği) var mı?
5. Sponsorlu ürün ve mağaza puanı raporlarını kim, ne sıklıkla indiriyor; portala yüklemeye hazır mı?

## 11. Başarı ölçütü

- Trendyol'da stokta görünüp depoda olmayan kitap sayısı → 0'a yakın; bu nedenli iptal sayısı düşüyor.
- Cevapsız soru yanıt süresi (saat) ve olumsuz yoruma yanıt oranı artıyor.
- Haftalık Trendyol raporunun elle hazırlanmasının bırakılması.
- Trendyol kanalının M42 karnesinde ölçülebilir olması (bugün hiç ölçülemiyor).

## 12. Uzman gözüyle en iyi sistem

Rol: 10+ yıllık pazar yeri (Trendyol/Hepsiburada) mağaza yöneticisi. Sektör pratiği (genel bilgi, TİMAŞ verisiyle doğrulanmadı):
başarılı yayınevi/kitapçı mağazaları stok ve fiyatı ERP'den bir entegratörle dakikalar içinde günceller; "stokta yok ama satıldı"
iptallerini sıfıra yakın tutar (mağaza puanını en çok bu düşürür); soru ve yorumlara aynı gün döner; kampanya dönemlerinde
(okul, Kasım indirimleri, kitap fuarı) vitrine stoğu derin ve satış hızı yüksek kitapları koyar; sponsorlu ürün bütçesini kitap
bazında kâr eşiğine göre ayarlar. Türkiye'de pazar yeri entegratörleri bu yazma işini üstlenir; TİMAŞ'ta yazma açık soru olduğu için
değerin çoğu **fark ve risk görünürlüğü**nden gelir.

Mükemmel sistem: sabah tek ekranda "puanı düşürecek riskler" (stok farkı, geciken paket, cevapsız soru, olumsuz yorum); kitap
bazında Trendyol satış hızı diğer kanallarla yan yana; kampanya öncesi vitrin listesi gerekçesiyle; haftalık özet telefonda.

Bir iş günü (saatler ve sayılar örnek biçimdir, ölçüm değildir):
- 08:00 Telefonda: "12 kitap Trendyol'da stokta, depoda yok; 5 paket 2 günü geçti; 9 cevapsız soru."
- 08:30 Stok farkı listesiyle panelde 12 ürünü kapatır (kendisi; sistem göndermez).
- 10:00 Sorular: Zeki AI taslaklarını düzenleyip panelden yanıtlar.
- 13:00 Olumsuz yorumlar: 2'si "baskı hatası" sınıfında → üretime (M12) not.
- 15:00 Kasım kampanyası için vitrin önerisini inceler, 20 kitabı onaylar.
- 17:00 Haftalık rapor taslağını e-ticaret müdürüne iletir.

"Bunu görürsem hemen kullanırım":
1. Trendyol stok ↔ depo stok farkı listesi (sabah).
2. Fiyatı liste fiyatının altına düşen / zarar eşiği altındaki kitaplar.
3. Cevapsız soru ve olumsuz yorum kuyruğu + yanıt taslağı.

"Bunu yaparsanız kullanmam":
1. Onayım olmadan mağazaya stok/fiyat göndermek.
2. Trendyol'a toptan satışı "mağaza satışı" gibi göstermek.
3. Uydurma rakip/kategori sıralaması (kazıma yapmadan veri varmış gibi).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Trendyol ilişkisini bulma | `LG_411_CLCARD` (DEFINITION_, SPECODE2), `LG_211_CLCARD` | `AccountBase` (ad, `new_FirmaKanal`, `new_logicalref`) | Cari ↔ platform eşleme adayı (M42 `mapping.py`) | Unvan platform adına benzemeyebilir |
| Toptan satış (varsa) | Faturalı `STLINE` (TRCODE 7,8,9 − 2,3, `LINENET`), cari süzgeci | `new_siparisBase` (`new_siparistipi` = 9) | — | Rakam SQL'den |
| Stok farkı | Stok bakiyesi (M43 sorgusu) | `new_kitapBase.new_ean13` (barkod köprüsü) | — | Deterministik karşılaştırma |
| Fiyat farkı | `PRCLIST` PTYPE 2 aktif TL | `new_kdvdahilfiyat` | — | — |
| İade nedeni | — | — | İade açıklamasını kapalı kümeye sınıflar (hasarlı, yanlış ürün, geç teslim, baskı hatası, vazgeçti, diğer) — tek token + olasılık | Serbest metin gruplanır |
| Yorum / soru | — | — | Duygu ve konu sınıflaması (kapalı küme) + yanıt taslağı (kişisel veri çıkarılmış metin) | Hız ve tutarlılık; gönderim insanda |
| Vitrin önerisi | Satış hızı (`logo_satis_hizi.sql`), stok | Kitap sezon/yaş (`new_hedefkitle` vb.) | Liste kural hesabından; model yalnız gerekçe yazar | Karar açıklanır |
| Haftalık rapor | Yukarıdaki rakamlar | — | 5–8 cümle özet | Telefonda okunur |
| Doğal dil soru | Katalog | Katalog | Mevcut soru hattı | — |

Model: `rt.llm_for("trendyol")`; gece sınıflama `QueuedLlm(..., purpose="bg:trendyol")`. Ekranda yalnız "Zeki AI".

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** (M42'nin `backend/semantic_bridge/channels/` paketine eklenir)
- `channels/trendyol_client.py` — satıcı API'si **salt okunur** istemcisi (`platforms.py` taban sınıfı; izinli yöntemler yalnız okuma
  — ürün listesi, sipariş/paket listesi, iade listesi, soru listesi; her yazma yolu istemcide hata atar ve testle kilitlenir).
  Kimlik: Yönetim → «Platform bağlantıları» (satıcı no, API anahtarı, gizli anahtar) `admin.conf`'ta.
- `channels/trendyol.py` — okuma, normalleştirme, fark hesapları, öneriler.
- `channels/trendyol_import.py` — panel dışa aktarımı (Excel) yükleme ve şema doğrulama (API yoksa ya da kapsam dışı raporlar için).
- Uçlar `channels/api.py` içinde.

**Tablolar**
- `semantic_trendyol_products` (tenant_id, barkod, trendyol_urun_id, baslik, satisa_acik, stok, fiyat, liste_fiyati, okuma_zamani, kaynak 'api'|'excel').
- `semantic_trendyol_orders` (tenant_id, paket_id, siparis_tarihi, durum, kargo_firma, kargo_durum, barkod, adet, tutar, okuma_zamani) — kişisel veri yok.
- `semantic_trendyol_claims` (tenant_id, talep_id, barkod, neden_metni, neden_sinifi, olasilik, tarih).
- `semantic_trendyol_questions` (tenant_id, soru_id, barkod, metin_maskeli, cevaplandi, soru_tarihi, taslak).
- `semantic_trendyol_reviews` (tenant_id, barkod, puan, metin_maskeli, sinif, tarih, kaynak) — API yoksa Excel.
- `semantic_trendyol_imports` (id, tenant_id, tur, dosya_adi, satir, yukleyen, tarih, hata).
- Öneriler M42'nin `semantic_channel_suggestions` tablosunda (`platform = 'trendyol'`).

**Uçlar** (`/api/v1/channels/trendyol/*`): `GET status` (bağlantı ve son okuma), `POST test` (yalnız yönetici, salt okunur çağrı),
`GET overview`, `GET products?durum=&fark=`, `GET stock-diff`, `GET price-diff`, `GET orders?durum=`, `GET claims`,
`GET questions?cevapsiz=1`, `POST questions/{id}/draft`, `GET reviews`, `POST imports` (Excel), `GET weekly`, `GET export/{liste}.xlsx`.

**Ekranlar** `src/canvas/channels/trendyol/`: `TrendyolHome.tsx` (/trendyol), `Products.tsx` (/trendyol/urunler), `Orders.tsx`
(/trendyol/siparisler), `Questions.tsx` (/trendyol/sorular), `Showcase.tsx` (/trendyol/vitrin), `Weekly.tsx` (/trendyol/haftalik),
`Imports.tsx` (/trendyol/yukle). Menü: çalışma alanı `platform`, bölüm «Trendyol». Bağlantı ayarı Yönetim → «Platform bağlantıları».

**Yetki**: `sayfa:trendyol`, `sayfa:trendyol-urunler`, `sayfa:trendyol-siparisler`, `sayfa:trendyol-sorular`; `ozellik:trendyol.oneri-karar`
(explicit), `ozellik:trendyol.yukle` (Excel yükleme), `ozellik:trendyol.taslak`. Yazma anahtarı tanımlanmaz.

**Zamanlayıcı**: `timas-channels.timer` içine Trendyol adımı — API bağlıysa ürün/stok/fiyat her 30 dk (salt okuma; hız sınırına
uyarak), sipariş/iade/soru her 15 dk; gece 04:15 sınıflama (model arka plan). Bağlantı yoksa adım "bağlı değil" kaydı yazıp geçer.

**Kabul testleri (gerçek veri)**
1. Trendyol carisi var mı: `SELECT CODE, DEFINITION_, SPECODE2 FROM dbo.LG_411_CLCARD WHERE DEFINITION_ LIKE N'%TRENDYOL%' OR DEFINITION_ LIKE N'%DSM%'` (ve `LG_211_CLCARD`); sonuç kullanıcıya onaylatılır, eşleme `semantic_channel_accounts`'a yazılır. Boş sonuç "Trendyol'a satış yok" diye sunulmaz.
2. Toptan senaryoda Trendyol cari net cirosu ekran = M42 kabul 2'deki sorgunun bu cari için çıktısı.
3. API bağlıysa: panelde görünen aktif ürün sayısı = `semantic_trendyol_products WHERE satisa_acik = 1` sayısı (aynı saat).
4. Stok farkı: 10 barkodda Trendyol stok (API) ve Logo bakiyesi (M43 kabul 1 sorgusu) elle karşılaştırılır; ekranla aynı.
5. Yazma koruması testi: istemcide izinli liste dışı her yöntem için çağrı hata atar (birim test; ağ çağrısı yapılmadan).
6. Excel yükleme: panelden indirilen gerçek bir sipariş raporunun satır sayısı = yüklenen satır sayısı; kişisel veri kolonları içeri alınmaz (şema denetimi).

**Bağımlılık**: **M42 önce** (ortak paket, eşleme, karne). M43 stok sorgusu. Kendi mağaza ve API anahtarı müşteriden gelmeden
yalnız toptan satır + Excel yükleme yapılır. M35 ile vitrin önerisi paylaşılabilir.

**Tahmini büyüklük**: M (toptan satır + Excel yükleme + fark listeleri 1–2 gün); API istemcisi ve sınıflama eklenirse M → L.
