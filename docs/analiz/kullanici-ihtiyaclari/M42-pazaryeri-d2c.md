# M42 — Diğer Pazar Yerleri ve D2C Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M42.txt`, `specs/M34.txt`, `specs/M35.txt`, `specs/M40.txt`,
`specs/E_Ticaret_Müşteri_Yönetimi_Ent.txt`, `ZEKİ_Veri_Haritasi2.html` (M42, M34 satırları), `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`,
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, kardeş analizler `docs/analiz/kullanici-ihtiyaclari/{M34-eticaret-platform.md, H3-eticaret-musteri-yonetimi.md, M35-eticaret-kampanya.md}`
(sınır için), `configs/semantic/knowledge/logo/knowledge/{rules/logo-erp.md, rules/conventions.md, metrics/logo-timas.md, sql/2026-y-l-nda-kitapci-e-ticaret-ve-dagitici-kanallar-i-in-ay.md}`,
`configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`, `backend/semantic_bridge/seo_geo/connections.py`, main'deki `backend/semantic_bridge/budget_sources.py` (M46),
bellek: `tsoft-no-write`, `crm-tsoft-no-push-integration`, `seo-geo-module`, `sales-are-invoiced-lines`, `logo-155-frozen-copy`,
`no-tech-names-on-screens`, `customer-vm-web-watch-off`. Sunucuya bağlanılmadı; yeni ölçüm yok.

## 1. Modül ne işe yarar

İş tanımı (M42): Hepsiburada, D&R, idefix ve timas.com.tr (D2C) kanallarını birlikte yönetmek — kanal bazında stok/fiyat dengeleme,
sipariş birleştirme, kargo optimizasyonu (K1); timas.com.tr dönüşüm iyileştirme, sadakat programı, D2C'ye özel ürün/kampanya,
müşteri verisi zenginleştirme (K2). Çıktılar: çok kanal panosu (kanal satış ve **kâr** karşılaştırması, stok dağılımı), D2C analizi
(D2C ve pazar yeri müşteri değeri), büyüme planı.

**Kardeş modüllerle sınır (tekrar olmasın diye):**
- **M34 E-Ticaret ve Platform** (analizi yazıldı): ürün/içerik ve T-soft↔CRM **fark** listesi (aktiflik, ad, fiyat, stok —
  `semantic_eticaret_items/diffs`), pazar yeri carilerinin **sell-in** panosu (`/e-ticaret/pazar-yerleri`). M42 bunları yeniden
  hesaplamaz, okur.
- **H3 E-Ticaret Müşteri Yönetimi** (analizi yazıldı): T-soft **sipariş okuma**, müşteri anahtarı, RFM, tetikler
  (`semantic_commerce_*`, `/api/v1/commerce/*`). M42 D2C tarafında bu tabloları okur, sipariş okumaz.
- **M35 Kampanya**: kampanya takvimi ve sonuç. **M40/M41**: Trendyol ve Amazon'a özel süreçler. **M44**: sipariş birleştirme ve kargo.
- **M42'nin kendi işi:** kanal **kârlılığı** (net ciro − iskonto − iade − satılan mal maliyeti − bilinen kargo), kanal **hedef ↔
  gerçekleşen**, **kitap × kanal** matrisi ve kanal stok/iskonto **önerisi**, cari ↔ platform eşlemesi (M40/M41 de kullanır),
  D2C **büyüme planı** (sadakat, D2C'ye özel set/ön sipariş) — H3 verisinin üstünde strateji katmanı.

Bugünkü durum (kanıtla): CRM'de pazar yeri API izi yok; pazar yerleri toptan **cari** (Kitapyurdu son 180 günde 227 sipariş,
D-MARKET/Hepsiburada 34, Amazon kartları); Logo'da kanal = `CLCARD.SPECODE2 = 'E-TICARET'` (M34 analizine göre ilk cariler Turkuvaz,
Kitapyurdu, D-Market, Point). timas.com.tr T-soft'ta; T-soft siparişleri CRM'e gelmiyor, ama T-soft `order/get` ile okunabiliyor
(H3 analizi: 62.903 sipariş okundu, 2026-09-25, kişisel alanlar okunmadı).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| E-ticaret / dijital satış müdürü (timas.com.tr + pazar yeri ilişkileri) | Ayrı ekip kanıtı yok (varsayım); CRM firma kanalı "E-Ticaret", satış hedefi bölgeleri "Hepsiburada, Kitapyurdu, B2C" | Haftalık, kampanya döneminde her gün | Masaüstü |
| Kanal / anahtar hesap yöneticisi (Kitapyurdu, Hepsiburada, D&R/Turkuvaz, idefix) | Satış (49 kişi, TeamMembership) | Haftalık | Masaüstü + telefon |
| Pazarlama (D2C sadakat, özel kampanya) | Pazarlama (35) | Kampanya dönemi | Masaüstü |
| Finans (kanal kârlılığı, iskonto politikası) | Mali İşler (10) | Aylık | Masaüstü |
| Genel müdür / satış direktörü | — | Aylık | Telefon (varsayım) |

## 3. Bugün bu iş nasıl yapılıyor

- **Kanal yöneticisi:** pazar yerleri TİMAŞ'tan toptan alıyor; sipariş CRM'de (sipariş tipi seçeneklerinde "Pazaryeri" (9) ve
  "Amazon Konsinye" (14) var; dağılım ölçülmedi) ve B2B portalı kitapsiparis.com.tr'den; fatura Logo'da. Kanalın son tüketiciye
  sattığı adet (sell-through) TİMAŞ'ta yok. İskonto görüşmesi Excel ve tecrübeyle (varsayım).
- **E-ticaret müdürü:** timas.com.tr T-soft panelinden; stok/fiyatın T-soft'a nasıl gittiği BT'ye soru (CRM `new_webstok` hiç dolu
  değil). GA4 ve Merchant Center erişimi portalda yok.
- **Finans:** kanal net ciro ve kanal brüt kâr soru hattında çalışıyor (katalog SQL çiftleri); kargo, komisyon, reklam gibi kanal
  maliyetlerinin Logo'da kanal bazında ayrıştırılıp ayrıştırılmadığı bilinmiyor.
- **Tıkanma (varsayım):** hangi kanal iskonto + iade + kargo sonrası gerçekten kârlı, tek ekranda yok; D2C müşterisinin değeri
  pazar yeri müşterisiyle karşılaştırılamıyor; kanal hedefleri (CRM) gerçekleşenle yan yana değil.

## 4. İhtiyaçlar ve acı noktaları

**Kanal yöneticisi**
1. Cari (kanal) bazında: net ciro, adet, iskonto oranı, iade oranı, vade, brüt marj — yıl karşılaştırmalı.
2. Kitap × kanal matrisi: hangi kanal hangi kitabı iyi alıyor, hangisi iade ediyor.
3. Hedef ↔ gerçekleşen (CRM satış hedefi bölgesi = kanal; M46 kitap hedefi).

**E-ticaret müdürü (D2C)**
1. D2C'nin toplam içindeki payı ve büyümesi; D2C'de pazar yerinden daha iyi satan kitaplar.
2. D2C müşterisinin tekrar alım ve değer kohortu (H3'ten) ile pazar yerleri kıyası.
3. D2C'ye özel set/ön sipariş/imzalı baskı fırsatı listesi.

**Finans**
1. Kanal kârlılığı ve "şu iskonto oranında marj ne olur" simülasyonu.

**Yönetim**
1. Aylık kanal karnesi, telefonda okunur.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Kanal yöneticisi olarak Kitapyurdu, Hepsiburada ve D&R'ın bu yıl aylık net cirosunu, iskonto ve iade oranını yan yana görmek istiyorum, çünkü yıllık iskonto görüşmesine hazırlanırım.
- Kanal yöneticisi olarak bir kanalın son 90 günde en çok iade ettiği kitapları görmek istiyorum, çünkü sevkiyat adedini düzeltirim.
- Finans uzmanı olarak kanal bazında iskonto, iade ve maliyet sonrası marjı görmek istiyorum, çünkü iskonto politikasını belirlerim.
- Finans uzmanı olarak bir kanalın iskontosunu 2 puan değiştirirsem marjın ne olacağını görmek istiyorum.
- E-ticaret müdürü olarak D2C'de pazar yerinden oransal olarak daha iyi satan kitapları görmek istiyorum, çünkü D2C'ye özel kampanya kurarım.
- Genel müdür olarak kanal paylarını ve hedef gerçekleşmesini ay sonunda telefonda görmek istiyorum.

**Ana ekranlar ve akış**
- Açılış (`/kanallar`): kanal kartları (E-TICARET carileri + timas.com.tr) — bu ay/yıl net ciro, geçen yıl, iskonto, iade, brüt marj,
  hedef gerçekleşme; veri günü (Logo son fatura) üstte.
- Kanal detayı (`/kanallar/:platform`): aylık eğri, kitap bazında alım/iade, hedef ↔ gerçekleşen, iskonto simülasyonu.
- Kitap × kanal matrisi (`/kanallar/matris`): kitap arama, kanallar sütun.
- D2C büyüme (`/kanallar/d2c`): D2C payı, D2C'ye özgü güçlü kitaplar, H3 kohort özeti, öneri listesi.
- Eşleme (`/kanallar/eslesme`): cari ↔ platform.
- En sık 3 işlem: kanal kıyasını açmak (1 tık), kanal detayından iade listesini Excel'e almak (3 tık), bir kitabın kanal dağılımını sormak (2 tık).

**Zeki AI'ya soracakları örnek sorular**
- "Bu yıl e-ticaret kanalında en çok ciro yapan 10 cari ve geçen yıla göre değişim?"
- "Hepsiburada'nın iade oranı son 6 ayda nasıl?"
- "Kitapyurdu'nda iskonto sonrası brüt marjımız kitapçı kanalından ne kadar farklı?"
- "D2C'de pazar yerlerine göre daha çok satan çocuk kitapları?"
- "E-ticaret kanalı hedefinin ne kadarını gerçekleştirdik?"
- "D&R'a geçen ay en çok hangi yayınevinin kitapları gitti?"

**Otomasyon katmanı**
- K1 (tam otomatik, **salt okuma**): kanal karnesi, matris, marj, hedef gerçekleşme, D2C payı. İş tanımındaki "kanal senkronizasyonu /
  stok ve fiyat dengeleme" platforma **yazmadır**: T-soft'a yazma yasak; pazar yerlerine yazma kullanıcı kararı (açık soru, §10).
  "Sipariş birleştirme ve kargo optimizasyonu" M44'tedir.
- K2 (Zeki önerir, insan onaylar): kanal iskonto önerisi (simülasyon gerekçesiyle), kanal stok payı önerisi (kıt kitapta hangi
  kanala öncelik), D2C büyüme önerileri (sadakat, D2C'ye özel set/ön sipariş). Onay portal kaydıdır; hiçbir platforma gönderilmez.
- K3: kanal sözleşmesi ve iskonto oranı kararı. K4: sadakat programının hukuki/KVKK tasarımı.

**Bildirim / uyarı**
- Kanal yöneticisi: kanal iade oranı ya da iskonto eşiği aşılırsa (haftalık, pazartesi 08:00).
- Yönetim: aylık kanal karnesi (planlı rapor, ayın 2'si 08:00).
- Kanal: portal zili + e-posta.

**Onay ve yetki (öneri)**
- `sayfa:kanallar` — e-ticaret, satış, pazarlama, finans, yönetim.
- `ozellik:kanal.marj` (brüt kâr, maliyet, simülasyon) — **açıkça verilir** (finans, yönetim, satış direktörü).
- `ozellik:kanal.oneri-karar` (iskonto/stok payı/D2C önerisi onayı) — açıkça verilir.
- `ozellik:kanal.eslesme` (cari ↔ platform onayı) — e-ticaret müdürü, finans.

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kanal net ciro, adet, iade | Logo faturalı `STLINE` (`INVOICEREF <> 0`), TRCODE 7,8,9 − 2,3, `LINENET`; `CLCARD.SPECODE2` | `kanal_net_ciro` ölçüsü ve SQL çifti var | .155 donmuş (2026-08-17) |
| İskonto | `STLINE` LINETYPE 2, ölçü `iskonto_yuku` | Tanımlı | Yok |
| Brüt marj | `LINENET − AMOUNT × OUTCOST` | Tanımlı; maliyet 30.06.2026'ya kadar, 2026 satırlarının %20'si maliyetsiz | Maliyetsiz satır sayısı her ekranda yazılır |
| Kanal maliyetleri (kargo, komisyon) | Logo gider hesapları (`EMFLINE`, 7xx), M44 kargo | Bilinmiyor | Kanal bazında ayrışma **ölçülecek** (Soru 5) |
| Cari ↔ platform eşlemesi | Logo `CLCARD` (CODE, DEFINITION_), CRM `AccountBase` (`new_logicalref`, `new_FirmaKanal`, `new_cariozelKod2`) | CRM–Logo cari bağı %98,6; M34 ilk carileri adlandırdı | Kullanıcı onaylı eşleme tablosu yok |
| Kanal hedefi | CRM `new_satishedefleriBase` (bölge, stok kartı, 12 ay; 2023–2026); M46 kitap hedefleri (main'de) | Tanımlı | Bölge ↔ cari eşlemesi **ölçülecek** |
| Pazar yeri sell-in panosu, içerik/fark | M34 `semantic_eticaret_items`, `semantic_eticaret_diffs` | M34 analizi | M34'e bağlı |
| D2C sipariş ve müşteri | H3 `semantic_commerce_orders`, `_order_lines`, `_customers` (T-soft `order/get`; 62.903 sipariş okundu) | H3 analizi | H3'e bağlı; D2C'nin Logo'daki carisi **ölçülecek** |
| D2C davranış (huni) | GA4 | Erişim yok | Müşteri yetkisi |
| Stok (kanal stok payı önerisi için) | Logo stok (M43) | M43 analizi | M43'e bağlı |
| Hepsiburada/idefix/D&R satıcı mağaza verisi | Platform API'leri | TİMAŞ'ın kendi mağazası olup olmadığı **bilinmiyor** | Soru 1 |
| Rakip fiyatı | Kazıma yasak (müşteride web taraması kapalı) | — | Yalnız resmî API |

## 7. Diğer modüllerle bağ

- Girdi: M34 (sell-in, içerik ve fark), H3 (D2C sipariş, müşteri, RFM), M46 (hedef), M43 (stok), M44 (kargo maliyeti), M35 (kampanya
  sonucu), M40/M41 (Trendyol ve Amazon satırları).
- Çıktı: M40/M41 (cari ↔ platform eşlemesi ve ortak `channels/` paketi), M35 (kanal/D2C kampanya önerisi), M9 Fiyatlama (iskonto
  etkisi), M45 finans (kanal kârlılığı), M59 bayi/kanal riski (iade, vade), M53 set (D2C'ye özel set önerisi).

## 8. Kısıtlar

- **T-soft'a yazma yasak**; pazar yerlerine yazma kullanıcı kararı; bu analiz yalnız okuma önerir.
- CRM'e yazma yok; öneri/onay köprünün tablolarında (`semantic_channel_*`).
- Müşteride web taraması kapalı: rakip fiyatı/bestseller kazıma yok.
- KVKK: D2C müşteri verisi yalnız H3'ün anahtarlanmış tablolarından ve kohort düzeyinde okunur; M42 kişisel alan saklamaz.
  Sadakat programı için açık rıza ve aydınlatma metni TİMAŞ hukuk kararıdır.
- Sell-in ≠ sell-through: pazar yerine faturalanan adet "pazar yerinde satıldı" diye gösterilmez; ekranda "kanala satış" yazılır.
- Ekranda teknoloji adı yok (T-soft, Hepsiburada gibi müşteri platform adları yazılabilir — SEO modülündeki karar); demo veri yok;
  sayı tavanı yok.

## 9. Kapsam önerisi

**İlk sürüm (Logo + CRM ile, dış bağlantı gerektirmeden)**
- Cari ↔ platform eşleme ekranı (Zeki AI aday önerir, kullanıcı onaylar).
- Kanal karnesi ve kanal detayı: net ciro, adet, iskonto, iade, brüt marj (maliyetli kısım), yıl kıyası, hedef ↔ gerçekleşen.
- Kitap × kanal matrisi.
- Aylık karne e-postası.

**Sonraki sürüm**
- İskonto simülasyonu ve kanal iskonto/stok payı önerileri (K2).
- D2C büyüme sekmesi (H3 tabloları hazır olunca): D2C payı, D2C'ye özgü güçlü kitaplar, kohort kıyası, sadakat/özel set önerileri.
- Platform satıcı API'leri (kendi mağaza varsa, salt okunur; M40 deseni).

**Mevcut kodda yeniden kullanılacaklar**
- main'deki `backend/semantic_bridge/budget_sources.py` (M46): `runner`, `firms_by_year`, `read_data_end`, `sales_sql` — Logo yıl/firma
  bulma ve satış okuma.
- `backend/semantic_bridge/management/` (`{satis:<yıl>}` yer tutucusu, önbellek, kaynak SQL paneli).
- `backend/semantic_bridge/seo_geo/connections.py` (`READ_ONLY` koruma deseni — M40/M41 istemcilerinin taban sınıfı için).
- Katalog SQL çiftleri: `2026-y-l-nda-kitapci-e-ticaret-ve-dagitici-kanallar-i-in-ay.md`, `kanal-baz-nda-br-t-k-r-marj-...md`,
  `kanal-bazinda-net-ciro-nedir.md`.
- `alerts.py`, `reports.py`, `board.py`, `SearchSelect.tsx`.

## 10. Uzmanlara sorulacak sorular

1. TİMAŞ'ın Hepsiburada, idefix, D&R, Kitapyurdu üzerinde **kendi satıcı mağazası** var mı, yoksa hepsi TİMAŞ'tan toptan alıp kendisi mi satıyor?
2. Pazar yerleri ve timas.com.tr için stok ve fiyatı bugün kim, hangi araçla gönderiyor? Bu modül ileride **mağazaya yazmalı mı**, yoksa hep salt okuma + öneri mi kalmalı? (Kullanıcı kararı.)
3. Hangi Logo carisi hangi platform/kanal (ör. D-MARKET = Hepsiburada, Turkuvaz = D&R)? Tek platformun birden çok carisi var mı?
4. Kanal hedefleri CRM satış hedeflerindeki bölgelerle mi, M46 bütçesiyle mi izlenmeli?
5. Kanal kârlılığında hangi maliyetler dahil olmalı (pazar yeri komisyonu, kargo, reklam, iade lojistiği) ve bunlar Logo'da hangi hesaplarda?

## 11. Başarı ölçütü

- Kanal karnesinin aylık yönetim toplantısında kullanılması; Excel kanal raporunun bırakılması.
- İskonto görüşmesinde ekrandaki simülasyonun kullanılması (karar kaydı).
- Kanal iade oranının öneriyle sevk adedi düzeltilen kanallarda düşmesi.
- D2C payının izlenebilir hâle gelmesi (bugün ölçülemiyor) ve D2C'ye özel önerilerden hayata geçen oran.

## 12. Uzman gözüyle en iyi sistem

Rol: 15 yıllık e-ticaret ve kanal müdürü. Sektör pratiği (genel bilgi, TİMAŞ verisiyle doğrulanmadı): iyi yayınevleri kanalları
**kitap × kanal** matrisiyle yönetir: kanala satılan (sell-in), kanalın sattığı (sell-through, kanal raporundan), iade ve stok;
iskonto politikasını kanal kârlılığına göre verir (iade ve lojistik dahil); D2C sitesini fiyat savaşı değil **müşteri ilişkisi** kanalı
olarak kullanır (ön sipariş, imzalı baskı, set, abonelik). Çok kanallı satıcılar içerik ve stok dağıtımını tek merkezden yapar; TİMAŞ'ta
yazma katmanı kapsam dışı olduğu için değer ölçüm, kıyas ve öneriden gelir.

Mükemmel sistem: sabah kanal karnesi (dün + ay + yıl); kitap × kanal matrisi; kanal iskontosu değişince kâr simülasyonu; D2C'nin
güçlü olduğu kitaplar ve müşteri değeri pazar yerleriyle yan yana; aylık karne telefonda.

Bir iş günü (saatler ve sayılar örnek biçimdir, ölçüm değildir):
- 09:00 Telefonda: "Kitapyurdu bu ay geçen yılın %18 üstünde; Hepsiburada iade oranı %11; D2C payı %6,2."
- 10:00 Hepsiburada detayında en çok iade edilen 10 kitabı indirir, sevkiyat adedini düşürme notu yazar.
- 11:30 İskonto simülasyonu: Kitapyurdu'na +2 puan iskonto → marj etkisi; öneriyi finansa gönderir (K2).
- 14:00 D2C büyüme: D2C'de oransal olarak güçlü 15 kitap → Kasım'a D2C'ye özel set önerisi (M53'e).
- 16:00 Karne taslağını genel müdüre iletir.

"Bunu görürsem hemen kullanırım":
1. Kitap × kanal alım/iade matrisi.
2. Kanal bazında iskonto ve iade sonrası marj + simülasyon.
3. Hedef ↔ gerçekleşen kanal bazında.

"Bunu yaparsanız kullanmam":
1. Benim onayım olmadan mağazaya fiyat/stok göndermek.
2. Sell-in'i "pazar yerinde satılan" gibi göstermek.
3. Maliyeti eksik satırları sessizce marja katmak (maliyetsiz satırı gizlemek).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kanal karnesi | `LG_411_01_STLINE` faturalı satır (`INVOICEREF <> 0`, TRCODE 7,8,9 − 2,3, `LINENET`), `LG_411_CLCARD.SPECODE2`; önceki yıllar `LG_211_*` + tarih süzgeci; ölçüler `kanal_net_ciro`, `iade_orani`, `iskonto_yuku`, `brut_kar_marji` | — | — | Rakam kayıt sisteminden |
| Cari ↔ platform eşleme | `CLCARD` (CODE, DEFINITION_, SPECODE2) | `AccountBase` (ad, `new_logicalref`, `new_FirmaKanal`, `new_cariozelKod2`) | Aday eşleşme (kapalı küme: platform listesi + "platform değil") — tek token + olasılık; kullanıcı onaylar | Unvan platform adına benzemiyor (D-MARKET, Turkuvaz) |
| Kitap × kanal | `V_SatisRaporu_<yıl>` (`Yıl*12+Ay`) ya da faturalı `STLINE` + `ITEMS` | — | — | — |
| Hedef ↔ gerçekleşen | Kanal net ciro | `new_satishedefleriBase` (bölge, stok kartı, aylar sütun); M46 hedef tabloları | — | — |
| İskonto simülasyonu | Satır `TOTAL`, iskonto satırları (LINETYPE 2), `OUTCOST` | — | Simülasyon sonucunu 2–3 cümleyle yorumlar (rakamlar hesaptan) | Karar sunumu |
| D2C büyüme | D2C carisi (ölçülecek) | — (T-soft verisi H3 tablolarından) | D2C'ye özel set/ön sipariş önerisi ve gerekçesi | Pazarlama hızlanır |
| Aylık karne | Rakamlar | Rakamlar | 5–8 cümle "kanallarda ne oldu" özeti | Telefonda okunur |
| Doğal dil soru | Katalog | Katalog | Mevcut soru hattı | Yeni hat kurulmaz |

Model: `rt.llm_for("kanal")`; gece eşleme adayları `QueuedLlm(..., purpose="bg:kanal")`. `LlmClient` doğrudan kurulmaz. Ekranda
yalnız "Zeki AI".

## 14. Kodlama planı (kodlayıcıya devir)

**Ortak paket (M40, M41 de kullanır; önce bu modülle kurulur)** — `backend/semantic_bridge/channels/`
- `sources.py` — Logo/CRM salt okunur okumalar; firma/yıl bulma main'deki `budget_sources.runner` + `firms_by_year` ile; SQL dosyaları
  `channels/sql/`: `logo_kanal_karne.sql`, `logo_cari_kitap.sql`, `logo_iade.sql`, `logo_iskonto.sql`, `logo_marj.sql`,
  `logo_eticaret_cari.sql`, `crm_cari.sql`, `crm_kanal_siparis.sql`, `crm_hedef.sql`.
- `mapping.py` — cari ↔ platform eşleme (aday + onay).
- `platforms.py` — platform istemcileri için **salt okunur** taban sınıf (T-soft istemcisindeki `READ_ONLY` deseni; yazma yolu hata;
  kimlik Yönetim → «Platform bağlantıları», `admin.conf`). M42 ilk sürümde kullanmaz; M40/M41 kullanır.
- `scorecard.py` — karne, matris, marj, simülasyon, hedef.
- `d2c.py` — H3 tablolarını okuyup D2C payı ve öneri (H3 yoksa sekme "bağlı değil" der).
- `store.py`, `api.py` (`register(app, rt=..., can=..., audit=...)`, `contracts_api.py` deseni).

**Tablolar**
- `semantic_channel_accounts` (tenant_id, platform 'hepsiburada'|'trendyol'|'amazon'|'kitapyurdu'|'dr'|'idefix'|'timas.com.tr'|'diger',
  logo_cari_kodu, logo_firma, crm_account_id, yontem 'zeki'|'elle', olasilik, onaylayan, onay_tarihi).
- `semantic_channel_suggestions` (id, tenant_id, platform, tur 'iskonto'|'stok-payi'|'d2c-set'|'d2c-sadakat' (M40/M41 ekler: 'vitrin'|'sponsorlu'|'metin'|'pazar'), payload_json,
  model_gerekce, durum 'taslak'|'onayli'|'red', karar_veren, karar_tarihi).
- `semantic_channel_scorecards` (tenant_id, yil, ay, platform, net_ciro, adet, iade, iskonto, marj, maliyetsiz_satir, hesap_zamani) —
  önbellek; satır tavanı yok.
- `semantic_channel_settings` (tenant_id, anahtar, deger) — iade/iskonto eşikleri.
- Her yazma `semantic_audit`'e (`channel_account`, `channel_suggestion`).

**Uçlar** (`/api/v1/channels/*`): `GET meta`, `GET scorecard?yil=&ay=`, `GET channel/{platform}`, `GET channel/{platform}/books`,
`GET channel/{platform}/returns`, `GET matrix?q=`, `GET targets?yil=`, `POST simulate` (iskonto senaryosu; hiçbir yere yazmaz),
`GET accounts`, `PUT accounts/{cari}`, `GET d2c`, `GET suggestions`, `POST suggestions/{id}/decision`, `GET export/{liste}.xlsx`.

**Ekranlar** `src/canvas/channels/`: `ChannelsHome.tsx` (/kanallar), `Channel.tsx` (/kanallar/:platform), `Matrix.tsx`
(/kanallar/matris), `D2CGrowth.tsx` (/kanallar/d2c), `Accounts.tsx` (/kanallar/eslesme). Rota `/timas/kanallar…`. Menü: yeni çalışma
alanı `platform` (etiket «Platform», `modules.json` grubu «Platform Yönetimi»; `NavGroupId`'ye eklenir), bölüm «Kanallar»; M40/M41 aynı
alanda kendi bölümleriyle. M34 «E-ticaret» Pazarlama alanında kalır (M34 analizi); iki ekran birbirine bağlantı verir. Kampüs:
«Platform» modül kartı.

**Yetki** (yeni alan `platform`, `access_catalog.json` `areas`'a eklenir): `sayfa:kanallar`, `sayfa:kanal-matris`, `sayfa:kanal-d2c`,
`sayfa:kanal-eslesme`; `ozellik:kanal.marj` (explicit), `ozellik:kanal.oneri-karar` (explicit), `ozellik:kanal.eslesme`. `access.py`
kuralı: `/api/v1/channels/` → `sayfa:kanallar`; alt uçlar kendi sayfa anahtarıyla.

**Zamanlayıcı**: `timas-channels.timer` her gece 04:00 — karne önbelleği (`semantic_channel_scorecards`), eşleme adayları (model arka
plan); ayın 2'si 08:00 karne e-postası `timas-reports.timer` ile. İlk kurulumda elle koşturulur.

**Kabul testleri (gerçek veri, aynı kaynak)**
1. 2026 E-TICARET kanal net ciro (ay bazında) ekran = `SELECT MONTH(l.DATE_), SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) FROM dbo.LG_411_01_STLINE l JOIN dbo.LG_411_CLCARD c ON c.LOGICALREF = l.CLIENTREF WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = 'E-TICARET' GROUP BY MONTH(l.DATE_)`; katalogdaki başlık (`NETTOTAL`) tanımlı SQL çiftiyle fark (≈ %0,6) ekranda açıklanır.
2. Cari bazında: 10 E-TICARET carisi için ekran = aynı sorgunun `GROUP BY c.CODE` hâli; M34'ün sell-in panosuyla aynı sayı (iki modül aynı SQL dosyasını kullanır).
3. İade oranı = katalog `iade_orani` ölçüsünün kanal süzgeçli doğrudan SQL'i; iskonto = `iskonto_yuku`.
4. Brüt marj: 10 cari için `SUM(LINENET − AMOUNT × OUTCOST)` (TRCODE 7,8,9, `OUTCOST > 0`) ve maliyetsiz satır sayısı (`OUTCOST = 0`) ekranla aynı.
5. Hedef: bir bölge ve yıl için `new_satishedefleriBase` 12 ay sütununun toplamı (sütun adları `rules/crm-timas.md` Kural'daki yazımla: `new_ocak, new_subat, new_Mart, …`) = ekrandaki hedef.
6. CRM sipariş tipi sayıları: `SELECT new_siparistipi, COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase WHERE new_siparistarihi >= DATEADD(DAY,-180,GETDATE()) GROUP BY new_siparistipi`.
7. Eşleme sonrası platform toplamı = eşlenmiş carilerin toplamı (fark 0); eşlenmemiş E-TICARET carileri ayrı satırda "eşlenmemiş" görünür.

**Bağımlılık**: kanal karnesi dış bağımlılıksız, **ilk yazılır**; M40 ve M41 bu paketin üstüne kurulur. D2C sekmesi H3'e, stok payı
önerisi M43'e bağlı (yoksa kapalı). M34 ile aynı sell-in SQL dosyası paylaşılır (hangisi önce yazılırsa diğeri import eder).

**Tahmini büyüklük**: M (ilk sürüm karne + matris + eşleme 2 gün); simülasyon ve D2C büyüme ikinci sürümde M.
