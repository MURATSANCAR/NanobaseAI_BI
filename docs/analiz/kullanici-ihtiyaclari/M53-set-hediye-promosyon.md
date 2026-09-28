# M53 — Hediye, Set ve Promosyon Ürün Yönetimi: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul bekliyor (testler koordinatörde) · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M53.txt`, `specs/M28.txt` (kurumsal hediye seçimi), `ZEKİ_Veri_Haritasi2.html` (Ürün Girdileri, Satış Girdileri), `configs/semantic/knowledge/crm/table_descriptions.json` (döküm 2026-09-09), `configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`, `configs/semantic/knowledge/logo/models/` (LG_411_ITEMS, LG_411_CAMPAIGN, BOM tabloları), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/pbit-yeni-baski-oneri/README.md` («Set Kitaplar» sayfası), `docs/analiz/seo-geo-modul-2026-09-25.md`, `backend/semantic_bridge/budget.py` / `budget_sources.py` (157 kuralı, satış tanımı), `management/sql/baski_oneri/*.sql`, `seo_geo/seasons.py`, `seo_geo/llms.py` (ticari ürün ayrımı), `docs/analiz/kullanici-ihtiyaclari/M17-backlist-pazarlama.md` (set adayları), kullanıcı belleği (sales-are-invoiced-lines, system-of-record-logo, logo-155-frozen-copy, baski-oneri-pbi-birebir, tsoft-no-write, no-tech-names-on-screens, no-silent-limits-rule, llm-gate).

> Kural: sunucuya bağlanılmadı. CRM satır sayıları tablo sözlüğünün 2026-09-09 dökümündendir (canlıda **ölçülecek**). Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım**.

## 1. Modül ne işe yarar

Kitap setlerini, mevsimsel hediye paketlerini, kurumsal hediye tekliflerini ve kitap dışı promosyon/yan ürünleri (defter, ajanda, ayraç vb.) tek yerde yönetir: tematik set önerisi (yazar, konu, seri, fiyat bandı), set fiyatı ve kâr marjı hesabı (set fiyatı ↔ tek tek kitap toplamı, maliyet, ambalaj), ambalaj ve sunum brief'i, kurumsal hediye teklif şablonu, promosyon ürün stok ve tedarik planı, sezon sonu set satış analizi (iş tanımı: K2 set ve hediye paketi tasarımı, K2 promosyon ürün yönetimi, K3 satış analizi).

TİMAŞ'ın bugünkü sorunu: setler CRM'de var (kitap kartında «Tip = Set», set tipi Normal/Toplama/Dergi, set özellikleri; proje kartında set adı, set barkodu, set kitap adedi; «Set İşlemi» ile set yapma/açma ve Logo'ya aktarım — 658 işlem, 5.942 satır) ama **setin performansı ölçülmüyor**: müşterinin Power BI «Yeni Baskı Öneri» raporundaki «Set Kitaplar» sayfası kırık (kaynak tablo modelde yok). Set önerisi deneyimle, fiyat/marj hesabı elle (varsayım). Hediye talepleri ve promosyon bütçesi için CRM'de varlık var ama neredeyse kullanılmıyor (hediye talebi 11, promosyon bütçesi 2 kayıt) → iş CRM dışında (varsayım: e-posta/Excel). Kitap dışı ticari ürünler (Logo'da 157 ile başlayan kodlar) bütün satış raporlarından bilinçli olarak dışlanıyor; kendi raporu yok.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Ürün / set sorumlusu | Pazarlama (varsayım; set önerisi ve fiyatı kimde **uzmana sorulacak**) | Sezon öncesi yoğun, ayda birkaç kez | Masaüstü |
| Pazarlama müdürü (onaycı) | Pazarlama | Sezon başına | Masaüstü |
| Satış müdürü / B2B satış | Satış (ekip 49 kişi); CRM kampanyalarında «opsiyonel hediye adedi», sipariş satırında «kesin hediye», «promosyon», «bedelsiz» bayrakları | Aylık | Masaüstü |
| Kurumsal satış / kurumsal ilişkiler (kurumsal hediye) | Satış ya da Yönetim (varsayım; M28 Kanaat Önderleri ve Kurumsal İlişkiler) | Yılsonu, bayramlar | Masaüstü |
| E-ticaret sorumlusu | Varsayım; CRM kitap `new_satiskanallari` «B2C Toplama Set» (336 kitap) | Kampanya başına | Masaüstü |
| Depo / set işlemi yapan | Depo. Kanıt: CRM «Set İşlemi» kaynak/hedef depo, «Set Yapma / Set Açma», «Logoya aktarıldı» | Set üretimi başına | Masaüstü |
| Üretim / satın alma (ambalaj, promosyon ürün tedariki) | Üretim (CRM «Paketleme»: shrink, şerit çember, vakum, kraft, kutulama, kolileme; birim maliyet — 11 kayıt, üretim kaydına bağlı) | Sipariş başına | Masaüstü |
| Finans / maliyet (marj kontrolü) | Mali işler (ekip 10 kişi); M9 | Fiyat onayında | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Set tanımı** (CRM izine dayanan **varsayım**): set önerisi yayın kurulunda ya da pazarlamada doğar; proje kartına set adı, set barkodu, set tipi (Normal / Toplama Set B2C), set kitap adedi girilir; kitap kartı «Tip = Set» olarak açılır (`new_SetTipi`, `new_setozellikleri`, `new_setadetmiktari` «Set Adet (Logo)»). Üretim kartında «set yapılacak adet» ve «önerilen set adet» alanları var. Set fiziksel olarak CRM «Set İşlemi» ile yapılır/açılır (satırlar: set ürünü + alt mamuller, kaynak ve hedef depo) ve Logo'ya aktarılır. Adım: en az 4 ekran (proje, kitap, üretim, set işlemi).
- **Fiyat ve marj**: set fiyatının tek tek kitap toplamına göre indirimi ve marjı elle/Excel'de (varsayım); CRM'de set için fiyat alanı kitap kartının fiyatı.
- **Hediye paketi (tüketici)**: sipariş kartında «Hediye paketi yapılacak» + not (B2C siparişlerde, **varsayım**); kaç siparişte kullanıldığı **ölçülecek**.
- **Kurumsal hediye**: CRM «Hediye Talepleri ve Gönderimi» (talep eden departman/yazar, hediye verilecek firma/kişi, hediye tipi, tutar, teslimat, onay veren — 11 kayıt) ve «Hediye Ürünler» (5) — neredeyse kullanılmıyor. Teklif mektubu Word'de (varsayım).
- **Promosyon malzemesi**: CRM «Promosyon Bütçesi» (bülten, katalog, ayraç, poşet, stand, kartonet, afiş, kalem, takvim, insört, broşür…; editoryal → pazarlama yöneticisi → genel müdür onayı) yalnız 2 kayıt; kitap kartında `new_Tip` «Promosyon» ve «Pazarlama Materyalleri» türleri var; üretim kartında ayraç/afiş baskı adetleri. Sipariş tipi 12 «Pazarlama (Tanıtım Gönderimi)». Kupon kodları tablosu 50.000 kayıt.
- **Satış analizi**: set satışı Logo'da set stok koduyla faturalanıyor olmalı (varsayım — set kodunun Logo'da ayrı kart olduğu ve bileşenlerin reçeteyle mi düşüldüğü **ölçülecek**). Power BI'daki set sayfası kırık.
- **Tıkanma**: set performansı ve setin tek kitap satışını yiyip yemediği görünmüyor; set önerisi veriye dayanmıyor; kurumsal hediye teklifleri her seferinde sıfırdan.

## 4. İhtiyaçlar ve acı noktaları

**Ürün / set sorumlusu**
1. Mevcut bütün setlerin tek listesi: bileşenleri, set fiyatı ↔ kitapların liste toplamı (indirim %), maliyet ve marj, stok, son 12 ay satışı.
2. Veriye dayalı set önerisi: birlikte alınan kitaplar (tüketici siparişleri), aynı yazar/seri/konu/yaş bandı, stok durumu ve marj; M17'nin «uyuyan» adayları.
3. Mevsimsel paket planı: özel günlere göre (Öğretmenler Günü, yılbaşı, Anneler Günü, karne, bayramlar) hangi set ne zaman hazır olmalı.
4. Set önerisinin CRM/Logo'ya girilecek «kart listesi» olarak çıkması (setin açılması TİMAŞ'ın mevcut akışıyla).

**Satış / kurumsal satış**
1. Kurumsal hediye teklifi: firma seçer, bütçe ve adet girer, uygun set/kitap seçenekleri ve teklif mektubu taslağı.
2. Fiyat kademeleri (adet arttıkça iskonto) ve teslim tarihi için stok kontrolü.

**Pazarlama müdürü / finans**
1. Marjın altına düşen set önerisini onaydan önce görmek; setin tek kitap satışını yeme riskini görmek.

**Depo / üretim**
1. Onaylanan set için set yapılacak adet ve ambalaj ihtiyacı (paketleme türü, birim maliyet) önceden.

**E-ticaret**
1. Set ürün açıklaması (SEO önerisi olarak) ve görsel (M19).

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Set sorumlusu olarak **bütün setleri marjı ve satışıyla** görmek istiyorum, çünkü hangi setin işe yaradığını bilmiyoruz.
- Set sorumlusu olarak **birlikte alınan kitaplardan ve M17 fırsatlarından set önerisi** almak istiyorum.
- Set sorumlusu olarak **set fiyatını değiştirince marjın anında** hesaplanmasını istiyorum.
- Set sorumlusu olarak **onaylanan setin CRM'e ve Logo'ya açılacak kart bilgilerini** tek listede almak istiyorum.
- Kurumsal satış olarak **bir firmaya 300 kişilik yılsonu hediyesi teklifini** bütçeye göre seçeneklerle ve mektup taslağıyla hazırlamak istiyorum.
- Pazarlama müdürü olarak **sezon sonunda set bazlı satış ve marj raporu** ve setin bileşen kitapların tek satışına etkisini görmek istiyorum.
- Depo sorumlusu olarak **onaylı setlerin yapılacak adet ve ambalaj ihtiyacını** görmek istiyorum.

### Ana ekranlar ve akış
- **İlk açılış (`/pazarlama/set-hediye`)**: dört sekme — **Setler** (mevcut + önerilen + taslak; kolonlar: set adı, tür, bileşen sayısı, set fiyatı, liste toplamı, indirim %, marj, stok, son 12 ay adet/ciro, durum), **Öneriler** (Zeki AI set adayları ve gerekçesi), **Kurumsal teklifler**, **Promosyon ürünleri** (157 ile başlayan ticari ürünler + CRM promosyon/pazarlama materyali kartları: stok, satış, bedelsiz çıkış).
- **Set ekranı (`/pazarlama/set-hediye/set/:id`)**: bileşen kitaplar (sürükle-ekle, adet), fiyat–marj hesaplayıcısı, ambalaj seçimi (CRM paketleme türleri + birim maliyet), sezon ve kanal, tanıtım metni (Zeki AI taslak), onay, «CRM/Logo'ya açılacak kart» çıktısı.
- En sık üç işlem: (1) öneriden set taslağı aç — 1 tık; (2) fiyatı değiştir, marjı gör — 1 alan; (3) kurumsal teklif oluştur (firma + adet + bütçe) → PDF — 3–4 tık.

### Zeki AI'ya soracakları
1. «Son 12 ayda en çok satan setler ve marjları?»
2. «Tüketici siparişlerinde en sık birlikte alınan kitap ikilileri hangileri?»
3. «7–10 yaş için stoku olan, toplam liste fiyatı X–Y arası beş kitaplık bir yaz tatili seti öner.»
4. «Bu setin fiyatı %20 indirimle olursa marj ne olur?»
5. «Geçen yılbaşı hangi firmalara kurumsal hediye gönderdik, ne kadar?»
6. «Stoku biten promosyon ürünleri hangileri?»
7. «Bu set satışa girdikten sonra içindeki kitapların tek satışı düştü mü?»
8. «Bu kurumsal müşteri için teklif mektubu yaz, 300 adet, kişi başı bütçe Z ₺.»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| Mevcut set listesi, bileşenler, satış, stok, marj | K1 | SQL (CRM + Logo) |
| Birlikte alım analizi, aday kümeleri | K1 | SQL / kod (sepet çiftleri) |
| Tematik set önerisi ve gerekçesi | K2 | Zeki AI adayları adlandırır/gerekçelendirir; insan onaylar |
| Fiyat ve marj hesabı | K1 | Kod; fiyat kararı K2 (insan) |
| Ambalaj ve sunum brief'i | K2 | Zeki AI taslak |
| Kurumsal hediye teklifi (seçenekler + mektup) | K2 | Seçenekleri kod (bütçe, stok), mektubu Zeki AI yazar; satış onaylar |
| Tanıtım ve e-ticaret metinleri | K2 | Zeki AI taslak; e-ticaret metni SEO önerisi |
| CRM/Logo'ya set kartı açılması | K4 | İnsan CRM «Set İşlemi» ve kart akışıyla yapar; sistem listeyi verir ve sonra kartı eşler |
| Sezon sonu satış analizi ve revizyon | K3 | Zeki AI analiz, karar insanda |
| Promosyon ürün stok uyarısı | K1 | Kural |

### Bildirim / uyarı
- Özel güne 8 hafta kala: o sezon için planlı setin kartı CRM/Logo'da açılmamışsa → set sorumlusuna.
- Onaylı setin bileşeninde stok, set yapılacak adetin altında → set sorumlusu ve depoya.
- Marjı Yönetim → Pazarlama'da girilen alt sınırın altında kalan set önerisi onaya gönderilince → onaycıya işaretli (sınır girilmemişse uyarı yok).
- Promosyon ürününde stok sıfıra indi (Logo) → üretim/satın almaya haftalık özet.
- Kurumsal teklifin geçerlilik tarihi yaklaşınca → teklifi hazırlayana.

### Onay ve yetki
- Görür: `sayfa:pazarlama-set-hediye`.
- Set ve teklif yazma: `ozellik:set.yaz`. Set onayı (fiyat dahil): `ozellik:set.onay` (explicit; gönderen onaylayamaz). Kurumsal teklif gönderme onayı: `ozellik:set.teklif-onay` (explicit).
- Maliyet ve marjı görmek: `ozellik:set.maliyet-gor` (satış ekibi fiyatı görür, maliyeti görmeyebilir).
- Dışa aktarma: `ozellik:veri.disa-aktar` (teklif PDF'i hariç — satışın asıl işi).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Mevcut setler | CRM `new_kitapBase` (`new_Tip = 4` Set, `new_SetTipi` Normal/Toplama/Dergi, `new_setozellikleri`, `new_setadetmiktari`, `new_satiskanallari` 4 Toplama Set / 8 B2C Toplama Set); `new_projeBase` (`new_setadi`, `new_SetBarkodu`, `new_SetTipi`, `new_setkitapadedi`); `new_websetBase` (1) | Satış kanalı sayıları ölçülü (Toplama Set 47, B2C Toplama Set 336) | `new_Tip = 4` kayıt sayısı **ölçülecek** |
| Set bileşenleri | CRM `new_setislemiBase` (Set Yapma/Açma, set ürünü `new_urunid`, depo, Logo'ya aktarım) + `new_setislemisatiriBase` (`new_tip` 1 Set / 2 Alt Mamul, `new_urunid`, `new_adet`); Logo reçete tabloları (`LG_411_ITMBOMAS`, `LG_411_BOMASTER`, `LG_411_BOMLINE`) | Tablolar sözlükte | Setin bileşen listesinin asıl kaynağı (CRM set işlemi mi, Logo reçetesi mi) **ölçülecek** |
| Set ve kitap satışı | Logo `LG_{firma}_01_STLINE` faturalı satır, iade eksi (set stok koduyla) | Satış tanımı `budget_sources.sales_sql` | Set satıldığında bileşenlerin ayrıca satış satırı olup olmadığı **ölçülecek** (çift sayım riski) |
| Liste fiyatı | CRM `new_kdvdahilfiyat` (11.232 kitapta), `new_PerakendeBirimFiyat`; Logo güncel birim fiyat (`logo_fiyat.sql`), Logo fiyat listesi `LG_411_PRCLIST` | Kısmen | Hangisinin esas olduğu **uzmana sorulacak** |
| Maliyet | Logo `STLINE.OUTCOST` (maliyetli satırlar; 2026'da satırların ~%20'sinde maliyet yok); CRM üretim `new_kesinlesenbaskifiyati`, `new_onerilenbaskifiyati` | M46 marj tanımı | Maliyetsiz kitapta marj «yok» yazılır |
| Ambalaj maliyeti | CRM `new_paketlemeBase` (tür, kaçlı paket, birim maliyet, toplam; üretime bağlı — 11 kayıt) | Sözlükte | Güncel birim maliyetler **uzmana sorulacak** (kayıt az) |
| Stok | Logo `EOS_DEPO_STOK_KONTROL_211` (Baskı Öneri; 157 **hariç**); 157 kodları için ayrı sorgu | Kitap stoku var | Ticari ürün (157) stoku için sorgu yeni |
| Birlikte alım (sepet) | CRM `new_siparisBase` + `new_siparissatiriBase` (tüketici siparişleri: tip 8 B2C, adı «B2C» ile başlayan; stok kodu `Product.ProductNumber`) | 9,7 Mn satır | B2C siparişlerinin tamamının CRM'e düşüp düşmediği (T-soft siparişleri) **ölçülecek**; bayi siparişi tüketici sepeti değildir, kullanılmaz |
| Geçmiş set/hediye satışı | Logo set kodları satışı; CRM sipariş satırı `new_kesinhediye`, `new_promosyon`, `new_bedelsiz`; sipariş `new_hediyepaketiyapilacak`; kampanya `new_opsiyonelhediyeadedi`, kampanya ↔ hediye ürün bağı | Sözlükte | Doluluk **ölçülecek** |
| Kurumsal müşteri talep geçmişi | CRM `new_hediyetalebiBase` (11), `new_hediyeurunlerBase` (5), `AccountBase` (firma), sipariş tipi 12 «Pazarlama (Tanıtım Gönderimi)» | Az kayıt | Kurumsal hediye satışlarının hangi sipariş tipiyle girildiği **uzmana sorulacak** |
| Promosyon / yan ürünler | Logo `LG_{firma}_ITEMS` `CODE LIKE '157%'` (ticari ürün) + satış; CRM `new_Tip` 2 Promosyon, 7 Pazarlama Materyalleri; `new_promosyonbutcesiBase` (2) | 157 kuralı kodda (budget, management, seo) | Hangi 157 kodlarının promosyon/yan ürün olduğu **ölçülecek** |
| Mevsimsel takvim | CRM `new_ozelgunlerBase` (93) + kitap bağı; SEO sezon takvimi (geçen yıl arama artışı) | Var | — |
| Logo kampanya kartları | `LG_411_CAMPAIGN` | Tablo var | Kullanımı **ölçülecek** |
| Rakip set/hediye stratejileri | — | **Yok** | Kazıma yapılmaz; uzmandan örnek istenir |

## 7. Diğer modüllerle bağ

- **Girdi**: M17 (set/paket adayları, uyuyan kitaplar) · M9 (fiyatlama ve maliyet) · M11 Baskı Öneri (stok, satış hızı) · M12 (baskı, paketleme) · M28 (kurumsal ilişkiler, kanaat önderi listeleri; M18 föy paketi hediye seçimi için) · M15 (yeni kitaba set ekleme) · SEO sezon takvimi.
- **Çıktı**: M18 (sezon setleri aylık plana) · M19 (set görseli, tanıtım görseli talebi) · M25/SEO (set ürün açıklaması önerisi) · M29/M30 (sete ilk dağılım, saha teklifi) · M32 (B2B kurumsal satış teklifleri) · M35 (e-ticaret kampanyası) · M52 (promosyon ürün tedariki) · M43 (set yapma/açma stok etkisi).

## 8. Kısıtlar

- **Logo'ya ve CRM'e yazma yok**: iş tanımındaki «Set ve hediye ürün LOGO'da tanımlama ve fiyat kaydı» yapılmaz. Onaylanan set için «açılacak kart» listesi (ad, set barkodu önerisi yok — barkodu TİMAŞ verir; bileşenler, adet, önerilen fiyat, set tipi, satış kanalı) verilir; kullanıcı CRM «Set İşlemi»/kart akışını yürütür; kart açılınca modül CRM'den okuyup kendi setini eşler.
- **T-soft'a yazma yasak**: set ürün açıklaması yalnız SEO önerisi.
- **Kazıma yok**: rakip set/hediye stratejileri dış sitelerden toplanmaz.
- **Çift sayım**: set satışı ve bileşen satışı ayrı gösterilir; toplam ciroya iki kez girmez (kural ölçüldükten sonra yazılır).
- **Sayı tavanı yok** (bütün setler, bütün birlikte alım çiftleri; varsayılan süzgeç yalnız görünüm).
- **Ekranda teknoloji adı yok**; **demo veri yok**.
- **Hukuki / vergisel** (**varsayım**, uzmana/hukuka doğrulatılmalı): kurumsal hediyede fatura ve KDV oranı (kitap ile kırtasiye/ambalajın KDV oranları farklı olabilir — set fiyatında KDV'nin bileşene göre ayrışması); bedelsiz promosyon çıkışlarının muhasebesi; kupon/kampanya koşullarının tüketici mevzuatına uygunluğu.
- **KVKK**: hediye verilecek kişi bilgisi CRM'den okunur; teklif belgelerinde yalnız firma ve yetkili adı.

## 9. Kapsam önerisi

**İlk sürüm**
- Mevcut set envanteri: CRM set kartları + bileşenler (set işlemi satırları), Logo satışı (set kodu), stok, liste fiyatı toplamı, indirim %, maliyet/marj (maliyet varsa), son 12 ay; «Set Kitaplar» ihtiyacını karşılar.
- Fiyat–marj hesaplayıcı (set fiyatı, ambalaj birim maliyeti, KDV dahil/hariç).
- Set önerisi: B2C birlikte alım çiftleri + aynı yazar/seri/konu/yaş kümeleri + stok ve marj süzgeci; Zeki AI ad ve gerekçe; M17 adayları.
- Set taslağı → onay → «açılacak kart» listesi → CRM'de kart açılınca eşleme.
- Promosyon ürünleri: Logo 157 kodlarının stok ve satışı; CRM promosyon/pazarlama materyali kartları.
- Kurumsal teklif: firma (CRM), adet, kişi başı bütçe → uygun set/kitap seçenekleri (stok yeterli), fiyat kademeleri (elle), Zeki AI mektup taslağı, PDF.

**Sonraki sürüm**
- Set–bileşen yamyamlığı analizi (set satışa girince bileşenlerin tek satışı; öncesi/sonrası).
- Sezon sonu otomatik rapor ve revizyon önerisi (K3).
- Ambalaj/tedarik planı M52 ile; set yapma adedi önerisi (M11 tahmini + sezon).
- E-ticaret set açıklaması → SEO önerisi; set görseli → M19.

**Mevcut kodda yeniden kullanılacaklar**
- `budget_sources.py` (`sales_sql`, `firms_by_year`, `data_end_sql`), 157 kuralı (`budget.py:419`, `management/__init__.py SALES_VIEW_FILTER`).
- `management/sql/baski_oneri/logo_depo_stok.sql`, `logo_fiyat.sql`, `crm_bekleyen_siparis.sql` (Product ↔ stok kodu: `ProductNumber`).
- `seo_geo/seasons.py` (özel gün ↔ kitap), `seo_geo/__init__.py external_proposal`.
- Pazarlama çekirdeği (varsa) `semantic_mkt_plan_books` ile M18'e sezon seti bağı; yoksa bağımsız.
- PDF: köprünün fpdf2 yolu; `contracts_docs.py` (dış kütüphanesiz Word — teklif Word olarak istenirse).

## 10. Uzmanlara sorulacak sorular

1. Set önerisini ve fiyatını bugün kim yapıyor, kim onaylıyor? Set fiyatında standart indirim oranı ya da asgari marj kuralı var mı?
2. Set Logo'da nasıl duruyor: ayrı stok kartı mı, reçete mi; set satılınca bileşenler stoktan nasıl düşüyor (CRM «Set İşlemi» → Logo)?
3. Kurumsal hediye satışları hangi kanalla ve sipariş tipiyle giriliyor; geçmiş kurumsal müşteri listesi nerede?
4. Promosyon/yan ürünler (defter, ajanda, ayraç…) Logo'da hangi kodlarla (157 önekli hepsi mi); stok ve tedariki kim yönetiyor?
5. Ambalaj/hediye paketi seçenekleri ve güncel birim maliyetleri kimde?

## 11. Başarı ölçütü

- Set envanterinin tamamında satış, stok ve (maliyet varsa) marjın görünür olması; «Set Kitaplar» ihtiyacının karşılanması (satış ekibinin onayı).
- Önerilen setlerden onaylanıp CRM'de açılanların oranı; açılan setlerin ilk 3 ay satışı.
- Kurumsal teklif hazırlama süresi (teklif kaydından ölçülür) ve teklif → sipariş dönüşümü (CRM siparişiyle eşlenirse).
- Marj alt sınırının altında onaylanan set sayısı (bilinçli karar kaydıyla).
- Promosyon ürününde stok bitiminin önceden uyarılma oranı.

## 12. Uzman gözüyle en iyi sistem

**Kim konuşuyor:** 15 yıllık ürün ve kanal pazarlama müdürü; set, hediye ve kurumsal satışı yönetmiş.

**Sektörde iyi örnekler** (genel sektör uygulaması; TİMAŞ'ta doğrulanmadı): yayınevleri seti ayrı bir ürün olarak yönetir; setin başarısı yalnız kendi satışıyla değil, bileşenlerin tek satışına etkisiyle (yamyamlık) birlikte ölçülür. Mevsimsel hediye kutuları sezonlardan aylar önce kararlaştırılır, ambalaj ve baskı tedarik süresine göre geri sayılır. Kurumsal hediyede hazır bir seçenek kataloğu (bütçe bandına göre), kademeli fiyat tablosu ve kişiselleştirme seçenekleri (kurum logolu ayraç, not kartı) bulunur. Setler çoğu zaman yavaşlayan backlist'i hareketlendirmek için kurulur.

**TİMAŞ için mükemmel sistem:** bütün setler tek listede, satışı ve marjıyla; yeni set önerisi gerçek birlikte alım verisinden ve backlist fırsatlarından gelir; fiyatı değiştirince marj anında; onaylanan set CRM'de açılacak kart listesiyle depo ve üretime iner; kurumsal teklif firma, adet ve bütçe girince seçenekleri ve mektubuyla on dakikada hazır.

**Bir iş günü (ekim ortası, yılsonu hazırlığı):**
- 09:00 — Setler sekmesi: 60 setin 18'inde son 12 ay satış yok, 7'sinde marj bilinmiyor (maliyet yok). Satışsız setleri «kapanacak» adayı olarak işaretler.
- 09:45 — Öneriler: B2C siparişlerinde en sık birlikte alınan 30 çift; Zeki AI bunlardan 6 tematik set önermiş (ör. «Aynı yazardan üç roman», «7–10 yaş bilim serisi»), her birinde stok, liste toplamı, önerilen indirim ve marj.
- 10:30 — İkisini seçer; birinde ambalaj «kutulama» seçilince marj düşüyor, «shrink»e çevirir. Onaya gönderir.
- 12:00 — Kurumsal satış arıyor: bir holding 400 kişilik yılsonu hediyesi, kişi başı bütçe belli. Kurumsal teklif: firma CRM'den, bütçe bandında 5 seçenek (stok yeterli olanlar), kademeli fiyat, Zeki AI mektup taslağı. PDF gider.
- 14:00 — Pazarlama müdürü iki seti onaylar; «açılacak kart» listesi CRM'e set kartı açacak kişiye ve depoya iner.
- 16:00 — Promosyon ürünleri: yılbaşı ajandasının Logo stoku kampanya adedini karşılamıyor → satın almaya not.
- Ocak — Sezon sonu raporu: setlerin satışı ve bileşenlerin tek satışı öncesi/sonrası; Zeki AI «şu iki set bileşen satışını düşürmüş görünüyor, gelecek yıl indirimi azaltın» önerisi; karar insanda.

**«Bunu görürsem hemen kullanırım» (3):**
1. Bütün setlerin satışı, stoku ve marjı tek tabloda (bugün hiç yok).
2. Gerçek birlikte alım verisinden set önerisi ve anında marj hesabı.
3. On dakikada kurumsal hediye teklifi (seçenek + kademeli fiyat + mektup).

**«Bunu yaparsanız kullanmam» (3):**
1. Seti portalda tanımlayıp CRM'de bir daha açtırmak (çift giriş) — portal önerir, CRM'deki kartı okuyup eşler.
2. Bayi siparişlerini tüketici sepeti sayıp anlamsız set önermek.
3. Set satışını ve bileşen satışını iki kez sayıp ciroyu şişirmek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Set envanteri | `LG_{firma}_ITEMS` (set kodu kartı), reçete tabloları (ölçüldükten sonra) | `new_kitapBase` (`new_Tip = 4`, set alanları), `new_projeBase` set alanları, `new_setislemiBase` + `new_setislemisatiriBase` | — | SQL |
| Set satışı | `LG_{firma}_01_STLINE` faturalı satır, iade eksi, set stok koduyla; net ciro = LINENET | — | — | Kayıt sistemi Logo |
| Stok | `EOS_DEPO_STOK_KONTROL_211` (kitap), 157 kodları için ayrı stok sorgusu | — | — | SQL |
| Fiyat, maliyet, marj | `logo_fiyat.sql` birim fiyat; `STLINE.OUTCOST` | `new_kdvdahilfiyat`; üretim kesinleşen baskı fiyatı; `new_paketlemeBase` birim maliyet | — | Kod hesaplar |
| Birlikte alım | — | B2C sipariş satırları (`new_siparisBase.new_siparistipi = 8` ya da adı «B2C»; `new_siparissatiriBase`; `ProductBase.ProductNumber`) | — | Sepet çifti sayımı (kod) |
| Tematik kümeler | Satış hızı (Baskı Öneri) | Yazar (`new_eserkatilimBase` + `Yazar`), seri/dizi (`new_diziid`), tema N:N, anahtar kelime N:N, hedef kitle/yaş, `new_new_kitap_new_kitapBase` (ilgili kitap, 5.820) | Aday kümeyi adlandırır ve gerekçesini yazar; «bu kitap bu temaya uyar mı» kapalı seçim (tek token + olasılık) | Yargı ve metin |
| Ambalaj/sunum brief'i | — | Paketleme türleri | Brief taslağı | Metin |
| Kurumsal teklif | Stok, fiyat | `AccountBase` (firma), geçmiş hediye talepleri | Seçenekleri **kod** üretir (bütçe/stok), model teklif mektubunu yazar | Rakamı model üretmez |
| Tanıtım / e-ticaret metni | — | Bileşen kitapların `new_ozet`, `new_kitapspotu` | Set tanıtım metni ve ürün açıklaması taslağı | Metin |
| Sezon sonu analizi | Set ve bileşen satışı öncesi/sonrası | — | Tabloyu yorumlar, en fazla 3 öneri | Yorum |
| Promosyon ürünleri | `CODE LIKE '157%'` satış ve stok | `new_Tip` 2 / 7, promosyon bütçesi | — | SQL |

Model çağrıları LLM kapısından: `rt.llm_for("marketing", NORMAL)` (ekrandaki teklif mektubu, set adı), `BATCH` (gece set adayı gerekçeleri). `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Dosyalar**: `backend/semantic_bridge/marketing/sets.py`, `sets_sql.py`, `sets_api.py` (pazarlama paketi varsa içine; yoksa `backend/semantic_bridge/sets.py` + `sets_api.py` + `sets_sources.py` bağımsız — M15'i beklemez). `register(app, rt, require_caller, can)` kalıbı (`budget_api.py`).

**Tablolar**
- `semantic_mkt_sets`: `id` (`MS-<yıl>-<sıra>`), `tenant_id`, `ad`, `tur` (`tematik|yazar|seri|sezon|kurumsal|toplama`), `kaynak` (`crm|oneri|elle`), `crm_kitap_id` (açıldıktan sonra), `stok_kodu` (açıldıktan sonra), `durum` (`oneri|taslak|onayda|onayli|kart-bekliyor|satista|kapanacak|kapandi`), `sezon` (özel gün id / tarih), `kanal` (json), `set_fiyati`, `kdv_json`, `liste_toplami`, `maliyet_toplami`, `ambalaj_turu`, `ambalaj_birim_maliyet`, `marj`, `hedef_adet`, `gerekce`, `olusturan`, `gonderen`, `onaylayan`, zaman damgaları.
- `semantic_mkt_set_items`: `set_id`, `stok_kodu`, `adet`, `liste_fiyat`, `maliyet`, `stok`, `kaynak` (`crm-set-islemi|logo-recete|oneri|elle`).
- `semantic_mkt_set_sales`: `stok_kodu` (set), `yil_ay`, `net_adet`, `net_ciro`, `asof`, `veri_sonu`.
- `semantic_mkt_basket_pairs`: `kod_a`, `kod_b`, `siparis_sayisi`, `donem`, `asof` (yalnız B2C siparişler).
- `semantic_mkt_gift_offers`: `id` (`KT-<yıl>-<sıra>`), `firma_id` (CRM AccountId), `firma_adi`, `adet`, `kisi_basi_butce`, `secenekler_json`, `kademeler_json`, `mektup`, `gecerlilik`, `durum` (`taslak|onayda|gonderildi|kazanildi|kaybedildi`), `hazirlayan`, `onaylayan`, `pdf_yolu`.
- `semantic_mkt_promo_items`: `stok_kodu`, `ad`, `tur` (`157|crm-promosyon|crm-pazarlama-materyali`), `stok`, `son12_adet`, `bedelsiz_cikis` (ölçüm yöntemi belirlenince), `asof`.

**Uçlar** (`/api/v1/marketing/sets…`)
- `GET sets?durum=&tur=&sezon=&kanal=` (tavansız, sayfalı), `POST sets`, `GET|PATCH sets/{id}`, `PUT sets/{id}/items`, `POST sets/{id}/price` (hesap; kaydetmeden), `POST sets/{id}/submit|approve|reject`.
- `GET sets/{id}/card-todo` («CRM/Logo'ya açılacak kart» listesi; CSV/PDF), `POST sets/{id}/link` (CRM'de açılan kartla eşleme; kod CRM'de doğrulanır).
- `GET sets/suggestions?yas=&tema=&butce_min=&butce_max=` (sepet çiftleri + kümeler + Zeki AI gerekçesi), `POST sets/suggestions/{sid}/adopt`.
- `GET sets/{id}/effect` (sonraki sürüm: bileşen öncesi/sonrası).
- `GET gift-offers`, `POST gift-offers` (`{firma_id, adet, kisi_basi_butce}` → seçenekler), `PATCH gift-offers/{id}`, `POST gift-offers/{id}/letter` (Zeki AI), `POST gift-offers/{id}/approve`, `GET gift-offers/{id}.pdf`.
- `GET promo-items?stok=0`.
- `POST sets/run-due` (SYSTEM).

**Ekranlar**: `src/canvas/marketing/sets/` — `SetsScreen.tsx` (sekmeler `SetsTab`, `SuggestionsTab`, `GiftOffersTab`, `PromoItemsTab`), `SetEditor.tsx` (bileşenler, fiyat–marj hesaplayıcı, ambalaj, onay, kart listesi), `GiftOfferEditor.tsx`. Rotalar `/pazarlama/set-hediye`, `/pazarlama/set-hediye/set/:id`, `/pazarlama/set-hediye/teklif/:id`. Menü (alan `pazarlama`, bölüm «Üretim»): `{ id: 'pazarlama-set-hediye', label: 'Set ve hediye', to: '/pazarlama/set-hediye', section: 'Üretim', keywords: ['set', 'hediye', 'promosyon', 'kurumsal hediye', 'ajanda', 'defter'] }`. Kampüs `LIVE.M53 = '/pazarlama/set-hediye'`.

**Yetki**: `sayfa:pazarlama-set-hediye`; `ozellik:set.yaz`, `ozellik:set.onay` (explicit), `ozellik:set.teklif-onay` (explicit), `ozellik:set.maliyet-gor`. `access.RULES`: `/api/v1/marketing/sets` ve `/api/v1/marketing/gift-offers`, `/promo-items` → `page("pazarlama-set-hediye")`; `run-due` → SYSTEM. `FEATURE_RULES`: yazma uçları → `set.yaz`; onaylar ucun içinde (gönderen onaylayamaz → 409). Maliyet alanları `set.maliyet-gor` yoksa yanıttan çıkarılır (sunucu tarafında).

**Zamanlayıcı**: `timas-marketing-sets.timer` — her gece 04:30: set envanteri (CRM), set satışı (Logo son yıl; geçmiş yıllar haftada bir), stok, promosyon ürünleri; haftada bir (pazar) B2C sepet çiftleri; özel gün geri sayım uyarıları. İlk kurulumda elle koşturulur; sepet sorgusunun süresi ölçülür (9,7 Mn satırlık tablo — yalnız B2C ve son 24 ay süzgeciyle).

**Kabul testleri** (test sunucusu, gerçek CRM .28 + Logo .155)
1. **Set envanteri**: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_Tip = 4` = Setler sekmesindeki «CRM» kaynaklı set sayısı.
2. **Bileşenler**: bir set için `SELECT p.ProductNumber, sl.new_adet FROM Timas_MSCRM.dbo.new_setislemiBase si JOIN Timas_MSCRM.dbo.new_setislemisatiriBase sl ON sl.new_setislemiid = si.new_setislemiId JOIN Timas_MSCRM.dbo.ProductBase p ON p.ProductId = sl.new_urunid WHERE si.new_urunid = '<set ürünü>' AND si.new_islemtipi = 1 AND sl.new_tip = 2` (en son set yapma işlemi) = `semantic_mkt_set_items` (Logo reçetesi esas çıkarsa o sorgu yazılır).
3. **Set satışı**: `budget_sources.sales_sql` mantığıyla set kodu için 2025 ve 2026 net adet/ciro = `semantic_mkt_set_sales` toplamları (kuruşu kuruşuna); veri sonu `data_end_sql`.
4. **Liste toplamı**: bileşenlerin `new_kdvdahilfiyat × adet` toplamı = `liste_toplami`; `logo_fiyat.sql` ile farklıysa ikisi de ekranda.
5. **Sepet çiftleri**: seçilen bir çift için `SELECT COUNT(DISTINCT s.new_siparisId) FROM new_siparisBase s JOIN new_siparissatiriBase a ON a.new_siparisid = s.new_siparisId JOIN ProductBase pa ON pa.ProductId = a.new_urunid JOIN new_siparissatiriBase b ON b.new_siparisid = s.new_siparisId JOIN ProductBase pb ON pb.ProductId = b.new_urunid WHERE (s.new_siparistipi = 8 OR LEFT(s.new_name, 3) = 'B2C') AND s.statuscode NOT IN (1, 100000001) AND pa.ProductNumber = '<a>' AND pb.ProductNumber = '<b>' AND s.new_siparistarihi >= '<24 ay önce>'` = `semantic_mkt_basket_pairs.siparis_sayisi`.
6. **Promosyon ürünleri**: `SELECT COUNT(*) FROM dbo.LG_411_ITEMS WHERE CODE LIKE '157%'` = Promosyon ürünleri sekmesindeki «157» satırı sayısı (kullanımda/pasif ayrımı eklenecekse `ACTIVE` alanının anlamı önce katalogdan doğrulanır); 157 kodlarının 2026 faturalı satışı (`STLINE` faturalı satır tanımı, `I.CODE LIKE '157%'`) = sekmedeki toplam.
7. **Marj hesabı**: bir sette elle hesap (set fiyatı KDV hariç − Σ bileşen maliyeti − ambalaj) = `POST sets/{id}/price` sonucu; maliyeti olmayan bileşende «marj hesaplanamadı: N kitapta maliyet yok».
8. **Onay ve yazma yasağı**: gönderen onaylayınca 409; kodda Logo/CRM/T-soft'a yazan çağrı yok (statik tarama); teklif PDF'inde teknoloji adı 0.

**Bağımlılık**: Bağımsız kodlanabilir (M46 gerekmez). M17 set adaylarını, M19 set görselini, M18 sezon setlerini sonra bağlar. Ölçülmesi gereken iki şey kodlamadan önce: setin Logo'daki temsili (kart/reçete, çift sayım) ve B2C siparişlerinin CRM'deki kapsamı — ikisi de kodlayıcının ilk işi olarak gerçek DB'de ölçülür ve bu belgeye yazılır.

**Tahmini büyüklük**: L (envanter + öneri + teklif + promosyon; 3 gün).

## 15. Kodlama notu (2026-09-28, dal; sunucu kapalıyken yazıldı — DOĞRULANAMADI)

- **Kod:** `backend/semantic_bridge/sets.py`, `sets_sources.py`, `sets_api.py`, `sets_docs.py` (M15 pazarlama çekirdeğinin yanında; tablolar `semantic_mkt_set*`, metin denetimi `marketing.guard`); ekran `src/canvas/marketing/sets/`; kabul `scripts/acceptance/M53/`.
- **Setin Logo temsili — varsayılan ve gerekçe (ölçülecek: `kabul.py --olcum` Ö1–Ö3):** katalog profilinde `ITEMS.CARDTYPE` değerleri 1, 4, 10, 11, 12, 13, 20, 22; Karma Koli (2) yok. Set ayrı stok kartıdır, bileşenler CRM «Set İşlemi» (set yapma) ile stoktan düşer, faturada set kodu satılır. Bu yüzden set satışı yalnız set koduyla okunur, bileşenin tek satışı ayrı gösterilir, ikisi hiçbir toplamda birleşmez. Aynı faturada set + kendi bileşeni satırı ölçülür (Ö3b); >0 çıkarsa `SETS_SALES_LINETYPES` / kural gözden geçirilir.
- **Bileşen kaynağı:** `SETS_COMPONENT_SOURCE=auto` — CRM'deki en son etkin «Set Yapma» işleminin alt mamul satırları, yoksa Logo reçetesi (geçerli revizyon, ana ürün satırı hariç; satır türü `SETS_BOM_LINETYPES` ölçümden sonra). Ö2 hangisinin kapsadığını sayar.
- **Liste fiyatı:** CRM kitap kartı KDV dahil fiyat (kabul 4 ile aynı); Logo `PRCLIST` fiyatı ekranda ayrıca. **KDV:** kalem başına Logo `ITEMS.SELLVAT`.
- **Birim maliyet:** `sets_sources.register_cost_provider` (M9 bağlanana kadar «maliyet bilinmiyor»; `SETS_COST_SOURCE=logo` son maliyetli satış satırı, «tahmini»).
- **B2C sepeti:** sipariş tipi 8 ya da adı «B2C»; taslak/iptal sipariş, iptal satır, promosyon/kesin hediye/bedelsiz satır hariç; en az 2 siparişte birlikte geçen bütün çiftler (ayar), birliktelik oranı < 1 çift öneri gerekçesi sayılmaz. Kapsam Ö4'te aylık ölçülür.
- **Onaylı durum:** analizdeki «onayli» ve «kart-bekliyor» tek durumda birleşti («Onaylı — CRM kartı bekliyor»); kart eşlenince «satışta».
- **Kurumsal teklif ↔ M32:** teklif akışı M32'de; burada seçenek + kademe + mektup + onay + PDF. `GET /gift-offers/{id}/handoff` M32 teklif satırı biçimi, `m32FirsatId` bağ alanı. PDF yolu `/gift-offers/{id}/document.pdf`.
