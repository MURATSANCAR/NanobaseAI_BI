# M27 — Fuar, Etkinlik ve Ödül Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M27.txt` (ZEKİ_Moduller3.html), `ZEKİ_Veri_Haritasi2.html` (Etkinlik Girdileri, Katalog & Ödül Veritabanı, «Kampanya & Etkinlik Takvimi — M16/M27 senkron»), `configs/semantic/knowledge/crm/table_descriptions.json` (2026-09-09), `configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md` (sipariş tipi), `configs/semantic/knowledge/logo/knowledge/rules/crm-timas.md` (Kural C10, C21), `configs/semantic/knowledge/logo/knowledge/caveats/logo-timas.md`, `configs/semantic/knowledge/logo/knowledge/glossary/logo-timas.md` (kanal SPECODE2), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/kampus-kisisel-ekran-crm-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `backend/semantic_bridge/author_relations.py`, `management/`, `web_watch.py`, `src/canvas/kampus/KampusPage.tsx`, `access.py`, `access_catalog.json`, `src/canvas/nav/navModel.ts`, `docs/LLM-KAPISI.md`, kullanıcı belleği (crm-digital-rights-fields, logo-155-frozen-copy, customer-vm-web-watch-off, no-tech-names-on-screens, no-silent-limits-rule).

> Kural: sunucuya bağlanılmadı. Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım** diye işaretlidir.

## 1. Modül ne işe yarar

Yurt içi ve yurt dışı kitap fuarları, festival, imza günü, söyleşi ve okul etkinliklerinin yıllık takvimini ve katılım önceliğini (ROI) yönetir; fuar için öne çıkarılacak kitapları, set/paket (bundle) önerilerini, stant yerleşimi ve materyal brief'ini hazırlar; ulusal/uluslararası ödül takvimini, kitabın uygunluğunu ve başvuru dosyasını yönetir; fuar sonrası satış ve bundle raporu verir (iş tanımı M27: üç K2 kartı; K3 ROI analizi; çıktı CRM kaydı ve bir sonraki fuar öğrenimleri).

TİMAŞ'ın bugünkü sorunu: etkinlik kaydı CRM'de **canlı ve büyük** (`new_etkinlikBase` 57.013 kayıt; 2026-09-15'te son 30 günde 594 değişiklik) ama çoğunluğu satış ziyareti («Cari ile Ziyaret»); fuar/imza günü/söyleşi ayrımı 371 «etkinlik tipi» içinde dağınık. Gider alanları neredeyse boş (57.486 aktif etkinliğin toplam gideri 9.275 ₺ — Kural C10), etkinliğe bağlı bütçe yok (C21). Fuar satışı Logo'da ayrı bir kanal (`CLCARD.SPECODE2 = 'FUAR'`) ve CRM'de ayrı sipariş tipi (`new_siparistipi = 4` Fuar, `5` Etkinlik, `16` İmza Siparişi) olarak izlenebilir durumda, ama gider ve satış aynı raporda birleşmiyor. Ödül takvimi ve başvuru için hiçbir kayıt yok. Kampüs'teki «Önemli Günler & Ajanda» kartı bugün tasarım yer tutucusu (sabit «TÜYAP Fuarı 2024» metni, `KampusPage.tsx`); gerçek veriye bağlanmamış.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Etkinlik / fuar koordinatörü | Pazarlama (**varsayım**; CRM etkinlik sorumlusu 43–52 kişiye dağılmış — 2026-09-15) | Fuar sezonunda her gün, ara dönem haftalık | Masaüstü (plan) + telefon (fuar alanında) |
| Satış müdürü / bölge sorumlusu | Satış (TeamMembership 49) | Fuar öncesi ve sonrası | Telefon |
| Yazar ilişkileri / editör | Editörya | İmza günü ve ödül başvurusu | Masaüstü |
| Yabancı haklar sorumlusu | Telif/haklar (CRM Telif **Satış** sözleşmeleri, `new_SozlesmeTipi = 1` — Timaş yurt dışına hak satar) | Frankfurt/Bologna/Londra dönemi | Masaüstü |
| Genel müdür / yönetim | Yönetim | Yılda 1–2 (takvim ve bütçe onayı) | Telefon |
| Muhasebe | Mali İşler | Fuar sonrası | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Koordinatör** (varsayım + CRM izi): etkinlik CRM'de açılır (ad, tip, tarih, yer/şehir, ilgili yazar ve kitap, katılımcı sayısı, satılan kitap adedi); fuar planı, stant, sevkiyat ve personel Excel/e-postada. Gider alanları doldurulmuyor. Tıkanma: «Bu fuar bize ne kazandırdı?» sorusu için satış (Logo), sipariş (CRM), gider (muhasebe) ayrı ayrı toplanıyor.
- **Satış**: fuara gidecek kitap ve adet listesi stok raporundan elle; fuar satışı fuar carisine (SPECODE2 FUAR) faturalanıyor — fuar başına ayrı cari mi, tek cari mi **ölçülecek**.
- **Editör / yazar ilişkileri**: imza günleri yazarla telefonda; M7 Yazar ilişkileri ekranında «Fuar / etkinlik» görüşme kanalı var (`author_relations.py`).
- **Ödül**: takvim kişilerin hafızasında; kitabın aldığı ödül CRM'de serbest metin (`ContactBase.new_YazarodulDurumu`, `new_etkinlikBase.new_dl` «Ödüller», `CampaignBase.new_dl` «Ödül») — dolu oranı **ölçülecek**.

## 4. İhtiyaçlar ve acı noktaları

**Koordinatör**
1. Yıllık takvim: fuar/festival/imza günü/söyleşi, katılım kararı, sorumlu, bütçe, durum.
2. Fuar başına görev listesi (stant, sevkiyat, personel, yazar programı, materyal) ve geri sayım.
3. Fuar kitap ve adet önerisi (satış × stok × fuar kitlesi) ve set/paket önerisi.
4. Fuar sonrası tek rapor: satış, sipariş, gider, katılım, yazar programı.
5. Geçmiş yılın aynı fuarıyla karşılaştırma.

**Satış müdürü**
1. Fuar kanalında hangi kitap sattı, stok nerede bitti.
2. Bir sonraki fuar için adet önerisi.

**Editör / yazar ilişkileri**
1. İmza günü takvimi ve yazarın uygunluğu.
2. Ödül takvimi, kitap uygunluğu, başvuru dosyası taslağı ve sonuç takibi.

**Yabancı haklar sorumlusu**
1. Uluslararası fuar randevuları ve hak kataloğu (İngilizce künye, özet).
2. Hangi kitapların yurt dışı hakkı satılabilir (CRM Telif Satış/Alış sözleşmeleri).

**Yönetim**
1. Fuar başına maliyet–getiri; katılım kararına gerekçe.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Koordinatör olarak yılın bütün fuar ve etkinliklerini tek takvimde görmek istiyorum, çünkü çakışmaları ve hazırlık sürelerini ancak böyle yönetebilirim.
- Koordinatör olarak fuara hangi kitaptan kaç adet götüreceğimi geçmiş fuar satışı ve stoka göre önerilmiş görmek istiyorum, çünkü fazla götürmek sevkiyat, az götürmek kayıp satış.
- Koordinatör olarak fuar bitince satış, sipariş ve gideri tek raporda görmek istiyorum, çünkü yönetime maliyet–getiriyi anlatmak zorundayım.
- Satış müdürü olarak geçen yılın aynı fuarında en çok satan kitapları görmek istiyorum, çünkü stant düzenini buna göre kuruyoruz.
- Editör olarak yaklaşan ödüllerin son başvuru tarihlerini ve uygun kitaplarımızı görmek istiyorum, çünkü tarihleri kaçırıyoruz.
- Yabancı haklar sorumlusu olarak Frankfurt için hak kataloğu taslağını almak istiyorum, çünkü her yıl sıfırdan İngilizce özet yazıyoruz.
- Genel müdür olarak gelecek yılın fuar takvimini ve tahmini bütçesini onaylamak istiyorum.

**Ana ekranlar ve akış**
- İlk açılış (`/timas/etkinlikler`): yıl takvimi (ay şeridi) + «Yaklaşan» listesi (geri sayım, hazırlık yüzdesi) + «Ödül son tarihleri».
- Fuar kartı: özet (tarih, yer, stant, bütçe, sorumlu), sekmeler Kitaplar ve adetler · Setler · Stant ve materyal · Yazar programı · Görevler · Sonuç.
- En sık 3 işlem: (1) Fuar kartı aç → kitap/adet önerisini al: 2 tık. (2) Görev işaretle: 1 tık (telefonda). (3) Fuar sonucu raporu: 1 tık.
- Diğer ekranlar: Etkinlikler (imza günü/söyleşi/okul; CRM kayıtları + portal kayıtları), Ödüller (takvim, uygunluk, başvuru, sonuç), Karşılaştırma (yıl/yıl).

**Zeki AI'a soracakları**
- «Geçen yıl TÜYAP'ta en çok satan 20 kitabımız hangisi?» (fuar–cari eşlemesine bağlı)
- «Bu yıl fuar kanalından ne kadar net satış yaptık, geçen yılla karşılaştır.»
- «Önümüzdeki üç ayda hangi fuarlar var, hazırlıkta geride olan hangisi?»
- «[Yazar] bu yıl kaç etkinliğe katıldı?»
- «Çocuk kitapları için başvurabileceğimiz ödüller ve son tarihleri neler?»
- «[Fuar] için 150–300 TL bandında 3 kitaplık set öner.»
- «Frankfurt hak kataloğu için [kitap]'ın İngilizce özetini yaz.»

**Otomasyon katmanı**
- K1: takvim geri sayımı ve görev hatırlatması, fuar satış/sipariş verisinin toplanması, geçen yıl karşılaştırması.
- K2: katılım önceliği, kitap/adet önerisi, set önerisi, stant/materyal brief'i, ödül uygunluğu ve başvuru metni, hak kataloğu metni → insan onayı; katılım kararı ve bütçe yönetimde.
- K3: fuar ROI ve set performansı raporu (Zeki raporlar, yönetim karar verir).
- İş tanımındaki «Etkinlik sonuç raporu → Dynamics CRM kaydı»: portal **CRM'e yazmaz**; sonuç portalda tutulur, CRM etkinlik kaydına bağlantı (CRM kimliği) saklanır.

**Bildirim/uyarı**
- Koordinatöre: fuara 60/30/14/7 gün (ayarlı) ve geciken görev; önerilen kitapta stok yetersiz.
- Editöre: ödül son başvuru tarihine 30/7 gün.
- Yönetime: onay bekleyen fuar katılım kararı; fuar sonucu raporu hazır.
- Kampüs «Ajanda» kartı: kişinin sorumlu olduğu yaklaşan etkinlikler (yer tutucu yerine gerçek veri).

**Onay ve yetki**
- `sayfa:etkinlikler`; `ozellik:etkinlik.duzenle`; `ozellik:etkinlik.onay` (explicit; katılım kararı ve bütçe); `ozellik:odul.duzenle` (ödül başvuruları). Maliyet alanları sayfa yetkisiyle görünür.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Etkinlik kayıtları | CRM `new_etkinlikBase` (`new_name`, `new_etkinliktipiid`→`new_etkinliktipiBase` 371, `new_aktivitecesitid`, `new_BalangTarihi`, `new_BitiTarihi`, `new_yer`, `new_sehir`, `new_il`, `new_ilce`, `new_OkulKurum`, `new_katilimcisayisi`, `new_SatilanKitapAd`, `new_etkinlikgeliri`, gider alanları, `new_sorumlusu`, `new_ziyarettipi`, `new_ziyaretsekli`, `statuscode` 1 Planlandı / 100000002 Tamamlandı / 100000000 İptal) | Canlı; tip adlarından hangisinin fuar/imza/söyleşi olduğu **ölçülecek** (371 tipin sınıflanması) | Gider alanları boş |
| Etkinlik ↔ yazar, kitap | CRM `new_new_etkinlik_contactBase` (9.012; %99,2 yazar), `new_new_etkinlik_new_kitapBase` (1.034); `new_lgiliKitap` (Ürün) | Var | — |
| Fuar satışı | Logo cari kanal `CLCARD.SPECODE2 = 'FUAR'`; satış satırı `STLINE` (`LINENET`, TRCODE 7,8,9 − 2,3); katalog ölçüsü `kanal_net_ciro` (`v_channel_net`) | Var; **fuar başına cari mi** **ölçülecek**; .155 kopyası 2026-08-17'de donmuş | Canlı Logo; fuar–cari eşlemesi |
| Fuar/etkinlik/imza siparişleri | CRM `new_siparisBase.new_siparistipi` 4/5/16, `new_siparistarihi`, `new_toplamsatistutari`, satırlar | Var; hacim **ölçülecek** | — |
| Stok ve satış hızı | Logo `logo_depo_stok.sql`, `logo_satis_hizi.sql` (baskı önerisi) | Var (donmuş kopya uyarısıyla) | — |
| Fiyat bandı (set önerisi) | CRM `new_kdvdahilfiyat`; Logo `logo_fiyat.sql` | Var | Fiyat kaynağı kararı (M24 ile ortak) |
| Sepet birlikteliği (set) | Logo fatura satırları (aynı faturadaki kitaplar) | Fuar satışı tek toplu faturayla mı kesiliyor **ölçülecek** — öyleyse sepet analizi yapılamaz | Kasa/fiş düzeyi veri |
| Fuar takvimi (tarih, yer, kapsam) | Kullanıcı girer; fuar düzenleyicilerinin kendi sitelerinden elle | Hiç kayıt yok | Otomatik tarama yok (bölüm 8) |
| Ödül takvimi ve koşulları | Kullanıcı girer; Wikidata (geçmiş ödüller, yalnız test sunucusunda) | Yok | Ödül veritabanı elle kurulur |
| Yazarın ödülleri | CRM `ContactBase.new_YazarodulDurumu`, `new_etkinlikBase.new_dl`; Wikidata | Dolu oranı **ölçülecek** | — |
| Yabancı hak durumu | CRM `new_sozlesmeBase.new_SozlesmeTipi` (1 Telif Satış, 5 Telif Alış), `new_haklaraciklama` | Var (crm-digital-rights-fields) | Yurt dışı hak (dünya hakları) alanı var mı **ölçülecek** |
| Gider | Muhasebe (Logo hizmet alımı), CRM gider alanları | CRM'de boş; Logo'da masraf merkezi **ölçülecek** | Fuar bütçesi/gideri kullanıcı girer |

## 7. Diğer modüllerle bağ

- Girdi: M24 (fuar kataloğu), M43 (stok), M11 (satış hızı), M9 (fiyat), M7 Yazar ilişkileri (imza günü randevusu), M46 (bütçe), M16 (lansman takvimi — «Kampanya & Etkinlik Takvimi M16/M27 senkron»), M53 (hediye/set/promosyon ürün), M41 (uluslararası).
- Çıktı: M20 (fuar basın bildirisi), M22 (fuar/imza günü duyurusu), M30 (saha satış), M11 (etkinlik takvimi baskı önerisi katsayısı), Kampüs Ajanda, M46 (gerçekleşen gider).

## 8. Kısıtlar

- CRM'e yazma yok: fuar kartı, görev, set, ödül, sonuç `semantic_events_*`; CRM etkinlik kaydı yalnız okunur ve kimliğiyle bağlanır.
- Fuar/ödül takvimi için site kazıma yok; düzenleyicinin sitesinden elle giriş ya da açık RSS/iCal yayımlıyorsa o (**doğrulanmadı**). Müşteri VM'inde web taraması kapalı.
- T-soft'a yazma yasak (fuar sonrası web kampanyası M35'in işi).
- Ekranda teknoloji adı yok; demo veri yok (Kampüs Ajanda'daki sabit «TÜYAP 2024» yer tutucusu modül bağlanınca kaldırılır); sayı tavanı yok.
- Logo satış verisi donmuş kopyada 2026-08-17'de bitiyor; fuar raporu veri sonu tarihini yazar.
- Ödül başvurusunda kitabın ve yazarın kişisel verisi (biyografi, fotoğraf) başvuru amacıyla paylaşılır; yazarın onayı sözleşme/yazar ilişkileri üzerinden alınır (hukuka sorulacak). Hak kataloğunda yalnız hakkı TİMAŞ'ta olan kitaplar yer alır (Telif Alış sözleşmesi kapsamı; yabancı kitabın hakkı satılamaz).

## 9. Kapsam önerisi

**İlk sürüm**
- Etkinlik takvimi: portal fuar/etkinlik kartları + CRM etkinliklerinin okunması (tip sınıflaması: fuar / imza günü / söyleşi / okul etkinliği / satış ziyareti; satış ziyaretleri varsayılan gizli).
- Fuar kartı: kitap/adet önerisi (geçmiş fuar kanalı satışı × stok × yenilik), görev listesi ve geri sayım, yazar programı (CRM yazar bağı + M7 randevu).
- Fuar sonucu: Logo FUAR kanalı net satışı (fuar tarih aralığı + fuar carisi), CRM fuar/imza siparişleri, elle girilen gider, katılımcı; geçen yılla karşılaştırma.
- Kampüs Ajanda kartının gerçek veriye bağlanması (sorumlusu ben olan yaklaşan etkinlikler).
- Ödül defteri: ödül (ad, kategori, son tarih, koşul, bağlantı — elle), kitap uygunluk işareti, başvuru durumu ve sonuç.

**Sonraki sürüm**
- Set/bundle önerisi (fiyat bandı + konu uyumu; sepet verisi varsa birliktelik).
- Stant yerleşim ve materyal brief'i (Zeki taslağı, M19'a iletim).
- Ödül başvuru metni ve hak kataloğu (İngilizce) taslakları.
- Katılım öncelik puanı (geçmiş ROI) ve yıllık takvim bütçe onayı.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/management/sql/baski_oneri/` (`logo_depo_stok.sql`, `logo_satis_hizi.sql`, `logo_fiyat.sql`, `crm_kitap.sql`), `management/__init__.py` (`{satis:<yıl>}`).
- `backend/semantic_bridge/author_relations.py` (yazar randevusu, «Fuar / etkinlik» kanalı), `rooms.py` (iç etkinlik salon rezervasyonu).
- `src/canvas/kampus/KampusPage.tsx` Ajanda kartı (yer tutucu → gerçek uç).
- `backend/semantic_bridge/web_watch.py` Wikidata ödül okuması (yalnız test ortamı, bayrakla).
- `backend/semantic_bridge/seo_geo/crm.py` (hak durumu okuma deseni) → hak kataloğu uygunluğu.

## 10. Uzmanlara sorulacak sorular

1. Yılda hangi fuarlara katılıyorsunuz (yurt içi/yurt dışı), hangileri stant satışı, hangileri hak alım-satımı?
2. Fuar satışı Logo'da nasıl faturalanıyor: fuar başına ayrı cari mi, günlük toplu fatura mı, kasa fişi mi?
3. CRM'deki 371 etkinlik tipinden hangileri fuar, imza günü, söyleşi? (liste onayı)
4. Fuar giderleri (stant kirası, konaklama, sevkiyat) nerede izleniyor?
5. Takip ettiğiniz ödüller ve son başvuru dönemleri hangileri; başvuruyu kim hazırlıyor?

## 11. Başarı ölçütü

- Yılın fuar takviminin ocakta portalda tam olması; kaçırılan ödül son tarihi 0.
- Fuar sonucu raporunun fuar bitişinden sonraki 3 iş günü içinde hazır olması.
- Fuara götürülen adet ile satılan adet oranı (iade/geri sevkiyat azalması).
- Fuar gider alanlarının dolu oranı (bugün CRM'de ≈ boş).
- Kampüs Ajanda kartının gerçek kayıtla dolması.

## 12. Uzman gözüyle en iyi sistem

*15 yıllık yayınevi etkinlik ve fuar müdürü gözüyle.*

Fuarlar iki farklı iştir: **stant satışı** (TÜYAP İstanbul ve Anadolu'daki belediye fuarları — kasa, stok, set, imza günü, kalabalık yönetimi) ve **hak alım-satımı** (Frankfurt, Bologna, Londra — randevu takvimi, hak kataloğu, teklif takibi). İyi yayınevleri stant satışını geçen yılın aynı fuarındaki kitap bazlı satışla planlar, imza günlerini satış verisiyle (hangi yazarın imza günü kaç kitap sattı) seçer ve fuar sonrası maliyet–getiriyi 1 hafta içinde çıkarır. Hak fuarlarında ise başarı, kataloğun ve randevu notlarının düzenidir. TİMAŞ için mükemmel sistem: CRM'de zaten canlı olan etkinlik kaydını ve Logo'daki FUAR kanalını tek fuar kartında buluşturan, adet önerisini stoka ve geçen yıla dayandıran, gideri ilk kez görünür kılan ve ödül takvimini kimsenin hafızasına bırakmayan bir planlama masası.

**Bir iş günü (fuardan 3 hafta önce)**
- 09:00 Takvim: TÜYAP'a 21 gün; hazırlık %55; 3 görev gecikmiş (stant materyali onayı, sevkiyat listesi, 2 yazarın imza saati).
- 09:30 Kitap/adet önerisi: geçen yılın TÜYAP satışı + yeni çıkanlar + stok; 4 kitapta stok önerilen adedin altında → baskı önerisi ekranına bağlantı.
- 11:00 Yazar programı: 6 yazarın imza günü; birinin tarihi çakışıyor → M7'de randevu değişikliği.
- 14:00 Satış müdürüyle stant düzeni: çok satanlar girişte, set masası, çocuk köşesi — Zeki'nin brief taslağı grafik ekibine.
- 16:00 Ödüller: bir çocuk edebiyatı ödülüne 10 gün kaldı; uygun 3 kitap; başvuru metni taslağı editöre.
- Fuar bittikten 2 gün sonra: tek tıkla sonuç raporu — FUAR kanalı net satış, imza günü siparişleri, gider, geçen yılla fark; yönetime PDF.

**«Bunu görürsem hemen kullanırım»**
1. Geçen yılın aynı fuarındaki kitap bazlı satışla adet önerisi.
2. Fuar sonu tek sayfalık maliyet–getiri raporu.
3. Ödül son tarihlerinin uyarısı.

**«Bunu yaparsanız kullanmam»**
1. 57 bin satış ziyaretinin fuar takvimine karışması.
2. Fuar alanında telefondan açılmayan ekran.
3. Gider girişini zorunlu, uzun form yapan tasarım (fuarda kimse form doldurmaz; fiş fotoğrafı + tutar yeter).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Etkinlik tipi sınıflaması | — | `new_etkinliktipiBase.new_name` (371) | Tip adını kapalı seçimle sınıflar: `fuar/imza/söyleşi/okul/satış ziyareti/diğer` (tek token + olasılık); sonuç insan onayıyla tablo olarak saklanır | Bir kez yapılan eşleme; her soruda model çağrılmaz |
| Takvim | — | `new_etkinlikBase` (`new_BalangTarihi`, `new_BitiTarihi`, `statuscode`, `new_sorumlusu`) | — | SQL |
| Fuar satışı | `LG_<211|411>_01_STLINE` ⨝ `LG_<211|411>_CLCARD` (211 = 2021–2025, 411 = 2026) (`SPECODE2='FUAR'`), `LINENET`, TRCODE 7,8,9 − 2,3, `LINETYPE=0`, `CANCELLED=0`, `INVOICEREF<>0`; katalog `kanal_net_ciro` | — | — | Logo kayıt sistemi; satış = faturalı satır |
| Kitap bazında fuar satışı | `STLINE.STOCKREF` → `LG_<211|411>_ITEMS.CODE` = CRM `new_StokKodu` | `new_kitapBase` | — | SQL |
| Fuar/imza siparişi | — | `new_siparisBase` (`new_siparistipi` 4/5/16, `new_toplamsatistutari`) | — | SQL |
| Adet önerisi | Geçen yıl fuar satışı, stok bakiyesi, satış hızı | Yeni çıkanlar | Öneri başına gerekçe cümlesi; adet kuralla | Rakamı model üretmez |
| Set önerisi | Fiyat (`logo_fiyat.sql`) | `new_kdvdahilfiyat`, `new_turlertext`, `new_hedefkitle` | Konu uyumu gerekçesi, set adı önerisi | Fiyat bandı kuralla |
| Stant/materyal brief'i | — | Seçilen kitaplar | Taslak metin | Metin işi |
| Ödül uygunluğu | — | Kitap türü, yayın yılı, yazar | Koşul metnini okuyup kitap için «uygun / belirsiz / değil» + gerekçe (kapalı seçim) | Koşullar serbest metin; karar insanda |
| Başvuru ve hak kataloğu metni | — | `new_ozet`, `new_kisabilgi` | Başvuru metni, İngilizce özet taslağı | Metin işi |
| Sonuç raporu | Yukarıdaki ölçüler | Etkinlik katılımcı, satılan adet | 5 cümle yorum | Rakamı yorumlar |

Model yalnız LLM kapısından: `rt.llm_for("etkinlik")`; tip sınıflaması tek seferlik `BATCH`.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/events.py` (fuar kartı, görev, öneri, sonuç hesabı), `events_sources.py` (CRM etkinlik/sipariş, Logo FUAR kanalı, baskı önerisi SQL'leri), `events_api.py` (`register`).

**Tablolar**
- `semantic_events_fairs` (id, tenant_id, name, kind [stant/hak/festival/imza/söyleşi/okul/diğer], starts_on, ends_on, city, venue, stand_info, budget_planned, status [aday/onaylı/hazırlık/sürüyor/bitti/iptal], owner_user, crm_event_ids_json, logo_client_codes_json, approved_by, created_by)
- `semantic_events_books` (fair_id, crm_book_id, qty_suggested, qty_planned, qty_sold NULL, featured, reason)
- `semantic_events_tasks` (id, fair_id, title, due_on, owner_user, done_at)
- `semantic_events_costs` (id, fair_id, kind [stant/konaklama/ulaşım/sevkiyat/materyal/yazar/diğer], amount, receipt_ref, created_by)
- `semantic_events_authors` (fair_id, crm_contact_id, slot_start, slot_end, note)
- `semantic_events_bundles` (id, fair_id, name, price, items_json, reason, status)
- `semantic_events_type_map` (crm_type_id, class, decided_by, decided_at)
- `semantic_awards` (id, tenant_id, name, category, organizer, deadline, conditions, url, recurring, created_by)
- `semantic_award_entries` (id, award_id, crm_book_id, status [aday/hazırlanıyor/gönderildi/kısa liste/kazandı/kazanamadı], text, submitted_at, result_at)

**Uçlar** (`/api/v1/events/*`): `GET meta`, `GET calendar?year=`, `GET upcoming`, `POST fairs`, `GET/PATCH fairs/{id}`, `POST fairs/{id}/suggest-books`, `PUT fairs/{id}/books`, `GET/POST/PATCH fairs/{id}/tasks`, `POST fairs/{id}/costs`, `GET fairs/{id}/result`, `GET fairs/{id}/result/export.pdf`, `GET crm-events?from=&to=&class=`, `GET/PUT type-map`, `GET awards`, `POST awards`, `POST awards/{id}/entries`, `PATCH award-entries/{id}`, `GET me/agenda` (Kampüs Ajanda), `POST run-due` (SYSTEM).

**Ekranlar** — `src/canvas/events/` (`EventsCalendar.tsx`, `FairCard.tsx`, `FairResult.tsx`, `CrmEvents.tsx`, `Awards.tsx`, `TypeMap.tsx`); rota `/timas/etkinlikler` (+ `/fuar/:id`, `/fuar/:id/sonuc`, `/crm`, `/oduller`, `/tip-eslemesi`). Menü: `pazarlama`, bölüm `section: 'Etkinlik'`, öğe `{ id: 'etkinlikler', label: 'Fuar ve etkinlik', icon: CalendarRange, hint: 'Fuar, imza günü, söyleşi ve ödüller' }`. Kampüs: Ajanda kartı `GET /api/v1/events/me/agenda` ile (yer tutucu metin silinir); M27 çalışan. Telefon: görev listesi, gider (fiş fotoğrafı + tutar), sonuç özeti.

**Yetki** — `sayfa:etkinlikler`; `ozellik:etkinlik.duzenle`; `ozellik:etkinlik.onay` (explicit); `ozellik:odul.duzenle`. `access.py`: `("/api/v1/events/run-due", SYSTEM)`, `("/api/v1/events/me/agenda", OPEN)` (Kampüs; yalnız kişinin kendi kayıtları), `("/api/v1/events/", frozenset({page("etkinlikler")}))`; FEATURE_RULES yazma uçları → `ozellik:etkinlik.duzenle`, `awards*` → `ozellik:odul.duzenle`, export → `ozellik:veri.disa-aktar`.

**Zamanlayıcı** — `scripts/server/timas-events.timer` her gün 07:45: geri sayım ve görev hatırlatması, ödül son tarih uyarısı, fuar bitişinden sonraki gün sonuç raporunun ön hesabı.

**Kabul testleri**
1. Fuar kanalı net satışı (fuar tarih aralığı): ekran = `SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET WHEN s.TRCODE IN (2,3) THEN -s.LINENET END) FROM LG_411_01_STLINE s JOIN LG_411_CLCARD c ON c.LOGICALREF = s.CLIENTREF WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND c.SPECODE2 = 'FUAR' AND s.DATE_ BETWEEN '<bas>' AND '<bit>'` (fuar carisi eşlenmişse ek `c.CODE IN (…)`); 2025 fuarları için `LG_211_*`.
2. Kitap bazında fuar satış adedi: ilk 20 kitap aynı sorgunun `STOCKREF` kırılımıyla (`ITEMS.CODE`) birebir.
3. CRM fuar siparişleri: ekran = `SELECT COUNT(*), SUM(new_toplamsatistutari) FROM Timas_MSCRM.dbo.new_siparisBase WHERE new_siparistipi IN (4,16) AND new_siparistarihi BETWEEN '<bas>' AND '<bit>'`.
4. CRM etkinlik takvimi: seçilen ayın «fuar» sınıfı sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_etkinlikBase e WHERE e.statecode = 0 AND e.new_BalangTarihi >= '<ay>' AND e.new_BalangTarihi < '<sonraki ay>' AND e.new_etkinliktipiid IN (<type-map'te fuar olan tipler>)`.
5. Yazar etkinlik sayısı: «[yazar] bu yıl kaç etkinlik» = `SELECT COUNT(DISTINCT ec.new_etkinlikid) FROM Timas_MSCRM.dbo.new_new_etkinlik_contactBase ec JOIN Timas_MSCRM.dbo.new_etkinlikBase e ON e.new_etkinlikId = ec.new_etkinlikid WHERE ec.contactid = '<guid>' AND e.new_BalangTarihi >= '2026-01-01' AND e.statuscode <> 100000000`.
6. Kampüs Ajanda: kişinin kartındaki kayıtlar = portal fuarları (`owner_user`) ∪ `new_etkinlikBase.new_sorumlusu = <kişinin SystemUserId>` ve `new_BalangTarihi >= bugün`; sabit yer tutucu metni `src/`'de kalmamış.
7. Veri sonu: rapordaki «satış verisi şu güne kadar» = `SELECT MAX(DATE_) FROM LG_411_01_INVOICE WHERE CANCELLED = 0`.

**Bağımlılık** — Bağımsız kodlanabilir. Etkinlik tipi eşlemesi (soru 3) ilk gün yapılır; uzman onayı gelene kadar Zeki sınıflaması «öneri» olarak durur. M24 fuar kataloğu ve M7 yazar randevusu ile paralel; M19 materyal brief'ini tüketir, beklenmez.

**Tahmini büyüklük** — L (3+ gün): takvim + fuar kartı + sonuç raporu L; ödüller M; set önerisi sonraki sürüm M.
