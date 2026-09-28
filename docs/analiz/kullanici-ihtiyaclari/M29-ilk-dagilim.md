# M29 — İlk Dağılım Yönetimi: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul 34/34 (2026-09-28 06:40 ve 08:00) · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M29.txt`, `specs/M46.txt`, `specs/M12.txt`, `specs/M18.txt`,
`specs/M59.txt`, `ZEKİ_Veri_Haritasi2` (scratchpad `veri_haritasi2.txt`), `configs/semantic/knowledge/logo/knowledge/{rules,metrics,caveats,glossary}/*`,
`configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md` + `table_descriptions.json`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `docs/GELISTIRME-GUNLUGU.md` (M46 girişi, main),
`backend/semantic_bridge/budget*.py`, `backend/semantic_bridge/access.py`, `src/canvas/nav/navModel.ts`, `src/canvas/stitch/ModulesMenu.tsx`,
kullanıcı belleği (sales-are-invoiced-lines, logo-155-frozen-copy, timas-logo-database-shape, system-of-record-logo, no-tech-names-on-screens,
no-silent-limits-rule, deploy-never-deletes-customer-data).

Sunucuya bu çalışmada bağlanılmadı; «ölçülecek» yazan her sayı kodlamadan önce test sunucusunda doğrudan sorguyla ölçülmelidir.
Otomasyon katmanları: **K1** tam otomatik · **K2** Zeki önerir, insan onaylar · **K3** Zeki analiz eder, karar insanın · **K4** yalnız insan
(K3/K4 tanımı iş tanımındaki «Analiz» etiketinden türetildi — varsayım).

## 1. Modül ne işe yarar

Yeni çıkan (ya da baskısı tekrarlanan) bir kitabın ilk baskısının hangi kanala, bölgeye ve müşteriye kaç adet gideceğini önerir; onaylanan
planın depodan çıkışını, müşteriye varışını ve ilk haftalardaki satışını izler. Girdi: M46'nın onaylı kitap hedefi (adet/ciro), M12'nin baskı
çıkış tarihi ve adedi, benzer kitapların geçmiş ilk dağılım ve satış payları, stok. Çıktı: bölge × kanal × müşteri × adet dağılım planı, takip
panosu, ilk hafta/ilk ay raporu ve yeniden sipariş önerisi.
TİMAŞ'ın bugünkü sorunu (varsayım, iş tanımından): dağılım adedi deneyimle belirleniyor; bir bölgede kitap tükenirken başka bir bölgede
iade olarak geri dönüyor, ilk hafta satışını kimse sistematik izlemiyor. Veride görülen: CRM'de «Dağılım» tipli sipariş var
(`new_siparisBase.new_siparistipi = 2`), yani dağılım bugün CRM siparişi olarak açılıyor; planın nasıl kurulduğuna dair kayıt yok.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Satış müdürü / dağılım planlayıcısı (planı hazırlar, satış onayı) | Satış (CRM TeamMembership «Satış» 49 kişi — `crm-timas-mscrm-detay`) | Her yeni kitapta; ayda yeni kitap sayısı kadar (ölçülecek) | Masaüstü |
| Lojistik / depo sorumlusu (planı onaylar, sevki yürütür) | Depo (CRM talep departmanı kodu 7 = Depo; sipariş durumları «Depoda Bekliyor», «Kutulanıyor», «Sevk Edildi») | Günlük | Masaüstü + depoda tablet (varsayım) |
| BMT (bölge temsilcisi; kendi bölgesine gelen kitabı ve adedi görür, müşteriye haber verir) | Satış sahası; CRM `SystemUserBase.new_bmt`, `AccountBase.OwnerId` etiketi «BMT» | Haftalık, yeni kitap haftasında günlük | **Telefon** |
| Merkez müşteri temsilcisi (zincir/dağıtıcı/e-ticaret carileri) | Satış merkez; `AccountBase.new_MerkezMusteriTemsilcisi` | Yeni kitap haftasında günlük | Masaüstü |
| Pazarlama (M18 föyünü ve kampanya tarihini dağılımla eşler) | Pazarlama (TeamMembership 35) | Aylık | Masaüstü |
| Genel müdür / satış direktörü (özet ve sapma) | Yönetim | Haftalık | Telefon + masaüstü (varsayım) |

## 3. Bugün bu iş nasıl yapılıyor

- **Satış müdürü:** Dağılım listesi bugün muhtemelen Excel'de hazırlanıyor (varsayım). Veride görülen izler: CRM `AccountBase.new_distributionstatus`
  («Dağılım Durumu Göster») → hangi carilerin dağılım listesinde olduğu işaretleniyor; `ProductBase.new_dagilimurunu` / `new_dagilimtarihi` ve
  `new_UretimBase.new_dagilimtarihi` («Baskı Dağılım Tarihi») → kitap ve baskı kaydında dağılım tarihi alanı var (doluluk ölçülecek). Proje iş planı
  aşamasında «Ön Sipariş 5/7» adımı var (`crm-timas-mscrm-detay`). Tıkanma: benzer kitabın geçmiş dağılımını ve satışını görmek için Logo raporu +
  CRM sipariş listesi ayrı ayrı açılıyor (varsayım).
- **Depo:** Dağılım siparişleri CRM'de «Dağılım» tipli sipariş olarak açılıyor; durumlar Depoda Bekliyor → Pusula Alındı → Kutulanıyor → Kutulandı →
  Sevk Edildi (`new_siparisBase.statuscode`). Kargo kaydı `new_kargobilgisiBase` (13.242 kayıt) ve Aras Kargo entegrasyon alanları var. Logo'ya
  irsaliye/fatura olarak düşüyor (STLINE TRCODE 8). Tıkanma: sevk sonrası «müşteriye ulaştı mı, rafa çıktı mı» bilgisi hiçbir sistemde yok.
- **BMT:** Bölgesine hangi yeni kitabın kaç adet gittiğini telefonla/e-postayla öğreniyor (varsayım).
- **Merkez temsilci:** Zincirlerin ilk sipariş adedi ön siparişle mi geliyor, Timaş mı gönderiyor bilinmiyor (sorulacak, bölüm 10).

## 4. İhtiyaçlar ve acı noktaları

- **Satış müdürü:** (1) Kitap depoya girer girmez hazır bir dağılım önerisi, gerekçesiyle (hangi benzer kitaplara bakıldı). (2) Hedefle (M46) baskı
  adedi arasında tutarlılık: toplam dağılım ≤ elde kalan stok, depoya rezerv payı. (3) Bölge/kanal payını tek ekranda düzeltip onaya gönderme.
  (4) İlk 4 haftada kitabın hangi bölgede tükendiğini, hangisinde durduğunu görmek. (5) Plan → CRM dağılım siparişine aktarımın elle yeniden yazılmaması
  (Excel çıktısı ilk sürümde, bölüm 8).
- **Depo:** (1) Onaylı planın koli/sevk listesi (müşteri, adres ili, adet). (2) Sevk edilmeyen plan satırı uyarısı. (3) Baskı gecikirse planın
  kendiliğinden kayması.
- **BMT:** (1) «Bu hafta bölgeme gelen yeni kitaplar, hangi müşteriye kaç adet» — telefonda tek ekran. (2) Tükenen müşteriye yeniden sipariş önerisi.
- **Merkez temsilci:** zincir bazında ilk sipariş önerisi ve geçmiş iade oranı.
- **Yönetim:** kitap başına plan / sevk / satış / iade tek satır.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Satış müdürü olarak depoya giren yeni kitabın dağılım önerisini tek tıkla açmak istiyorum, çünkü bugün benzer kitapları elle arıyorum.
- Satış müdürü olarak önerideki bölge paylarını değiştirip gerekçe yazmak istiyorum, çünkü yazarın memleketi/etkinliği gibi veride olmayan bilgiyi ben biliyorum.
- Satış müdürü olarak planı onaya gönderdiğimde lojistiğin görmesini istiyorum, çünkü iki göz kuralı var.
- Depo sorumlusu olarak onaylı planı sevk listesi olarak indirmek istiyorum, çünkü siparişleri CRM'de açan benim.
- BMT olarak telefonda bölgeme gelen yeni kitapları ve adetlerini görmek istiyorum, çünkü müşteriyi önceden aramam gerekiyor.
- Yönetici olarak ilk 4 haftanın sonunda hangi kitabın fazla gönderildiğini görmek istiyorum, çünkü iade maliyeti burada doğuyor.

**Ana ekranlar ve akış**
- İlk açılış (masaüstü): «Dağılım bekleyen kitaplar» listesi — depoya giriş tarihi, baskı adedi, M46 hedefi, plan durumu (yok / taslak / onayda /
  onaylı / sevkte). Altında «İzlenen kitaplar» (ilk 8 hafta): plan–sevk–satış–iade oranı ve renkli durum.
- Kitap planı: üstte özet (hedef, stok, rezerv), ortada bölge × kanal matrisi (satırlar düzenlenebilir), altta müşteri listesi (sayı tavanı yok, sayfalı).
  Sağ panel: «Zeki AI gerekçesi» (benzer kitaplar ve payları).
- En sık 3 işlem: öneriyi açıp onaya gönder (2 tık), lojistik onayı (1 tık + onay penceresi), sevk listesini Excel indir (1 tık).
- Telefon (BMT): alt çubukta «Bölgeme gelenler» — kart listesi: kitap kapağı, adet, müşteri sayısı; karta dokununca müşteri × adet.

**Zeki AI'ya soracakları (örnek)**
- «Geçen ay çıkan romanların ilk 4 haftada en çok hangi bölgede sattı?»
- «Bu kitaba benzer son 5 kitabın zincirlere ilk gönderim adedi neydi, kaçı iade geldi?»
- «Ege'ye gönderdiğimiz yeni çocuk kitaplarından hangisi hiç satmadı?»
- «Hedefin %80'ine ulaşmak için hangi bölgeye ek sevk gerekir?»
- «D&R'a ilk dağılımda gönderdiğimiz adetin ne kadarı 90 günde iade geldi?»
- «Bu hafta sevk edilmemiş dağılım satırı var mı?»

**Otomasyon katmanı**
- K2: dağılım planı önerisi (Zeki önerir, satış müdürü düzeltir, lojistik onaylar).
- K1: depoya giriş algılama (Logo üretimden giriş), plan durumunun sevk kayıtlarından güncellenmesi, anomali uyarıları.
- K2: yeniden sipariş önerisi (öneri; siparişi CRM'de insan açar).
- K3: gelecek baskı için dağılım dersi raporu (ilk 8 hafta sonunda).
- K4: plan dışı özel gönderim kararı (yazar etkinliği, fuar) — insan.

**Bildirim/uyarı**
- Satış müdürüne: kitap depoya girdi, plan yok (ertesi sabah 08:30, portal içi + e-posta özeti).
- Lojistiğe: plan onayını bekliyor (anında, portal içi).
- Depoya: onaylı plan satırı 5 iş günü içinde sevk edilmedi (günlük özet) — eşik plan parametresi.
- BMT'ye: bölgesine yeni kitap planlandı (plan onayında; portal içi, telefon bildirimi ikinci sürüm).
- Satış müdürüne ve BMT'ye: müşteride ilk 14 günde satış/sevk oranı yüksek → yeniden sipariş önerisi; bölgede hiç satış yok → izleme uyarısı (haftalık).

**Onay ve yetki**
- Görür: `sayfa:ilk-dagilim` (satış, lojistik, pazarlama, yönetim). BMT yalnız kendi carilerine düşen satırları görür (`ozellik:dagilim.herkesinki` yoksa).
- Değiştirir: `ozellik:dagilim.plan` (öneri üret, düzelt, onaya gönder).
- Onaylar: `ozellik:dagilim.onay` (açıkça verilir; gönderen onaylayamaz — M46 ile aynı iki göz kuralı).
- Dışa aktarım: mevcut `ozellik:veri.disa-aktar`.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Onaylı kitap hedefi (adet, ciro, aylık dağılım) | M46 köprü `GET /api/v1/budget/targets?year=&stok=` | main'de; yalnız **kitap** bazlı (stokKodu, yayınevi, 12 ay) | **Bölge/kanal/bayi hedefi yok.** CRM `new_satishedefleriBase` 15 «bölge» × stok × ay tutuyor (bölgelerin bir kısmı kanal: D&R, Hepsiburada, Kitapyurdu, Point, KitapKahve, B2C); 2026 kodu `new_yil = 100000000`. Kullanılıyor mu ölçülecek/sorulacak |
| Baskı adedi, depoya giriş tarihi | Logo `LG_411_PRODORD` (PLNAMOUNT, STATUS 3), `LG_411_01_STLINE` TRCODE 13 IOCODE 1 (üretimden giriş); CRM `new_UretimBase` (statuscode «Depo Girişi Yapıldı», `new_dagilimtarihi`), `new_baskiBase` | Logo Kural 9/20 tanımlı | M12 kodlanıyor; M12 hazır olana kadar Logo üretimden giriş kaynak. CRM `new_dagilimtarihi` doluluğu ölçülecek |
| Planlanan çıkış tarihi (baskı henüz çıkmadıysa) | M12 (geriye doğru takvim) | kodlanıyor | M12 uç sözleşmesi bekleniyor |
| Stok bakiyesi (dağıtılabilir adet) | Logo STLINE IOCODE 1,2 − 3,4 (tarih filtresiz, güncel kopya) | tanımlı ölçü («stok bakiyesi», iş teyidi bekliyor) | **Logo .155 donmuş kopya, son fatura 2026-08-17** (bellek: logo-155-frozen-copy); canlı .25 okuma yetkisi BT kararı |
| Geçmiş satış (bölge, kanal, müşteri, kitap) | Logo STLINE faturalı satır (`INVOICEREF<>0`, TRCODE 7/8/9 − 2/3, `LINENET`), CLCARD `SPECODE2` (kanal), `CITY` | tanımlı (net ciro, kanal) | Bölge = CRM bölgesi mi Logo şehri mi karar gerekir (bölüm 10) |
| Geçmiş ilk dağılım (benzer kitap) | CRM `new_siparisBase` tip 2 + `new_siparissatiriBase`; Logo sevk (STLINE TRCODE 8) | tablolar katalogda | Tip 2 sipariş sayısı, yılı ve satır doluluğu **ölçülecek**; CRM sipariş→fatura bağı sevkiyattan geçer (`new_sevkiyatBase.new_faturanumarasi` → `INVOICE.FICHENO`) |
| Benzerlik (kategori, yayınevi, yaş, fiyat, yazar) | Logo ITEMS `SPECODE` (yayınevi); CRM `new_kitapBase` (hedef yaş, seri, dizi, tip, fiyat) | tablolar katalogda | Kategori ağacı modülü henüz yok (spec «Kategori Ağacı») |
| Dağılım carileri listesi | CRM `AccountBase.new_distributionstatus = 1`, `new_FirmaKanal`, `new_cariozelKod2`, `new_logicalref` → CLCARD | alanlar var | Doluluk ve Logo eşleşmesi ölçülecek (CRM→Logo cari bağı %98,6, 2026-09-09; hangi firma kopyasının LOGICALREF'i olduğu doğrulanacak) |
| Ön sipariş / bekleyen talep | CRM `new_bekleyenurunBase` (772.616; Bekleyen → Siparişe Eklendi) | tablo var | Yeni kitap ön siparişi olarak kullanılıp kullanılmadığı sorulacak |
| Dağıtıcı kapasitesi, kanal anlaşmaları (iade hakkı, konsinye) | Kullanıcı girer | hiçbir sistemde yok | Tümü boşluk; CRM sipariş tipi 14 «Amazon Konsinye» tek iz |
| Müşteri raf/satış (sell-through) | Dış (zincir raporları) | yok | Zincirlerin satış verisi yok → ilk sürümde «satış» = bizim faturamız + iade, raf verisi yok |
| İade | Logo TRCODE 2/3 satırları | tanımlı (iade oranı) | — |

## 7. Diğer modüllerle bağ

- Girdi: **M46** (`/api/v1/budget/targets`, `/api/v1/budget/deviations` — revizyon kaydı `kind=revizyon` plan kimliği değişimini bildirir), **M12**
  (baskı çıkış tarihi/adedi; hazır olana kadar Logo üretimden giriş), **M10/M11** (ilk baskı/baskı tekrarı adedi — M12 üzerinden), **M18** (föy ve
  kampanya tarihi, bilgi), **M59** (bayi risk; yüksek riskli bayiye dağılım uyarısı — M59 yoksa M30'un vadesi geçmiş sinyali), **Baskı Öneri / Zeki AI
  tahmin** (`backend/semantic_bridge/management/zeki_tahmin.py`, kitap bazlı 12 ay tahmin — backlist baskı tekrarında taban).
- Çıktı: **M30** (BMT'nin ziyaret brifingine «bölgenize gelen yeni kitaplar»), **M43 Ana Depo** (sevk listesi), **M11** (ilk 8 hafta satış hızı →
  baskı tekrarı), **M46** (dağılım planı hedefin bölge kırılımı olarak geri bildirim — ikinci sürüm).

## 8. Kısıtlar

- **CRM'e ve Logo'ya yazma yok.** İş tanımındaki «LOGO stok güncelleme» ve «dağıtıcı onay bildirimi → sipariş» adımları ilk sürümde **yapılmaz**:
  onaylı plan köprünün kendi tablolarında durur, depo CRM dağılım siparişini elle açar (Excel çıktısından). CRM Web API yazma yetkisi müşteri kararıdır.
- T-soft'a yazma yasak (bu modülde gerek de yok). Müşteride web taraması kapalı (dış kaynak yok).
- BMT'nin telefon görünümü sahadan erişim ister; portal müşteri ağında (`http://192.168.0.55/timas/`) — VPN/dış erişim BT kararı (bkz. M30 §8).
- Ekranda teknoloji/model adı yok: «Zeki AI önerisi». Demo veri yok; plan boşsa «plan yok» yazar.
- Sayı tavanı yok: müşteri listesi kesilmez; sayfalanır, süzülür.
- Kurulum müşteri verisi silmez; plan tabloları kurulumda korunur.
- Logo verisinin bittiği tarih her ekranda yazılır («veri 17.08.2026'ya kadar») — canlı Logo'ya geçilene dek takip K1 anlamını yitirir.
- KVKK: müşteri (cari) kişisel veri kolonları (TCKNO, telefon, e-posta, adres) okunmaz (Logo Kural 3); sevk listesinde yalnız cari unvanı, il.

## 9. Kapsam önerisi

- **İlk sürüm:** dağılım bekleyen kitaplar listesi (Logo üretimden giriş + CRM üretim); benzer kitap payından bölge × kanal × müşteri önerisi (K2);
  düzeltme + gerekçe; onaya gönderme / lojistik onayı (iki göz); sevk listesi Excel; takip: plan ↔ sevk (Logo irsaliye) ↔ faturalı satış ↔ iade,
  ilk 8 hafta; «sevk edilmedi» ve «hiç satmadı» uyarıları; BMT telefon görünümü (salt okunur).
- **Sonraki sürüm:** yeniden sipariş önerisi ve BMT bildirimi; M12 planlanan çıkış tarihiyle ön plan (baskı çıkmadan); dağıtıcı kapasitesi/anlaşma
  kayıtları; CRM'e dağılım siparişi aktarımı (yetki gelirse); zincir satış verisi (anlaşma olursa); M46'ya bölge kırılımı geri bildirimi.
- **Yeniden kullanılacaklar:** `backend/semantic_bridge/budget.py` (onay akışı, iki göz, audit, targets okuma `approved_targets()`),
  `budget_sources.py` (`runner`, `firms_by_year`, `sales_sql` satır tanımı), `alerts.py` (uyarı olay tablosu deseni), `board_excel.py`
  (Excel üretimi), `people.py` (AD ↔ CRM SystemUser köprüsü), `access.py` + `access_catalog.json`, `management/zeki_tahmin.py` (tahmin okuma).

## 10. Uzmanlara sorulacak sorular

1. İlk dağılım listesini bugün kim, hangi araçla hazırlıyor; CRM'deki «Dağılım» tipli siparişler bu listenin tamamı mı?
2. «Dağılım Durumu Göster» işaretli cariler otomatik dağılım alan müşteriler mi; kitap türüne (çocuk, roman, akademik) göre ayrı listeler var mı?
3. Zincirler ve e-ticaret (D&R, Kitapyurdu, Hepsiburada…) ilk adedi kendi ön siparişiyle mi veriyor, Timaş mı gönderiyor; iade hakkı/konsinye koşulları nerede?
4. «Bölge» için hangi tanım geçerli: CRM Satış Hedefleri'ndeki 15 bölge mi, BMT'lerin il ataması mı (`new_illerBase.new_musteritemsilcisi`)?
5. Depoda rezerv payı (ilk dağılımda elde tutulacak adet) için bir kural var mı?

## 11. Başarı ölçütü

- Depoya girişten dağılım planının onayına geçen gün (hedef: 2 iş günü; bugünkü değer CRM tip 2 sipariş tarihi − Logo üretimden giriş tarihiyle ölçülecek).
- İlk 90 gün iade oranı (dağılım yapılan kitaplarda, Logo TRCODE 2/3 ÷ 7/8) — önceki yıl aynı kohortla kıyas.
- İlk 4 haftada «tükendi» (müşteriye sevk edilen adedin ≥ %90'ı faturalandı ve yeniden sipariş yok) müşteri oranı.
- Önerinin düzeltilmeden kabul edilen satır payı (öneri kalitesi) ve düzeltme gerekçelerinin sınıfları.
- Kullanım: planı portaldan yapılan yeni kitap oranı; BMT telefon görünümünü açan kişi sayısı.

## 12. Uzman gözüyle en iyi sistem

**Uzman:** 15 yıllık satış ve dağıtım müdürü (yayınevi). Sektör uygulaması (genel bilgi, TİMAŞ'ta doğrulanmadı): iyi yayınevleri ilk dağılımı
«karşılaştırma kitapları» (comps) üzerinden kurar — aynı yazar/seri/kategori/fiyat bandında son 2–3 yılın 4–8 haftalık satış eğrisi, müşteri
bazında sell-through ve iade. Satış ekibi yayından 6–8 hafta önce föyle müşteriye gider, ön siparişi toplar; ön sipariş + comps + hedef + stok kuralı
birleşip müşteri bazında tahsis olur. Yayın sonrası haftalık sell-through ile ikinci dalga (replenishment) yapılır. Ticari dağıtım yazılımları bunu
«tahsis kuralı + ön sipariş + otomatik ikmal» olarak sunar; Türkiye'de zincirlerden düzenli satış verisi alınmıyorsa ikmal fatura/iade üzerinden yapılır (varsayım).

**TİMAŞ için mükemmel sistem:** kitap depoya girmeden önce (M12 planlanan çıkış) taslak plan hazır; ön sipariş (CRM bekleyen ürün/sipariş) plana
kendiliğinden işler; müşteri başına öneri gerekçesiyle (benzer 5 kitabın bu müşterideki 8 haftalık satış ve iadesi) gelir; onay tek ekranda; sevk
listesi depoya gider; ilk 8 hafta her pazartesi «nerede tükeniyor / nerede duruyor» listesi ve ikmal önerisi; 8. hafta sonunda «bu kitaptan ne öğrendik»
notu sonraki benzer kitabın comps'una girer.

**Bir iş günü:** 08:30 portal açılır, «Dağılım bekleyenler»de dün depoya giren 3 kitap; birini açar, Zeki AI önerisi hazır (İstanbul %38, Ege %14…,
zincir 1.200, bağımsız kitapçı 1.800). Yazarın Konya'da imza günü olduğunu bildiği için İç Anadolu'yu artırır, gerekçe yazar, onaya gönderir (10 dk).
10:00 lojistik onaylar, depo Excel'i alır. 14:00 «İzlenen kitaplar»da geçen ay çıkan kitabın Karadeniz'de hiç satmadığını görür, BMT'ye not düşer.
17:30 telefondan haftalık sapma özetine bakar.

**«Bunu görürsem hemen kullanırım»:** (1) Her önerinin yanında «hangi kitaplara bakıldı» ve o kitapların gerçek satış/iade rakamı. (2) Toplam dağılım
stoku ve rezervi aşarsa kaydetmeden uyarı. (3) Tek tıkla depo sevk listesi, CRM'deki sipariş formatına yakın.

**«Bunu yaparsanız kullanmam»:** (1) Rakamı kim/nasıl hesapladı belli olmayan «yapay zekâ adedi» (gerekçesiz öneri). (2) Excel'deki müşteri
listemden farklı, eksik müşteri listesi (sayı tavanıyla kesilmiş). (3) Planı iki sistemde (portal + CRM) iki kez yazdırmak — ilk sürümde çıktı CRM'e
yazım kolaylığı sağlamalı.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Depoya giriş algılama | `LG_411_01_STLINE` TRCODE 13 IOCODE 1 LINETYPE 0 CANCELLED 0, `STOCKREF`, `DATE_`; `LG_411_PRODORD` STATUS 3 | `new_UretimBase` statuscode «Depo Girişi Yapıldı», `new_dagilimtarihi` | — | Olay Logo'da kesin (kayıt sistemi) |
| Hedef | — | — (M46 köprü tablosu `semantic_budget_approved_targets`) | — | Rakam M46'dan |
| Benzer kitap seçimi | ITEMS `SPECODE` (yayınevi), satış satırları | `new_kitapBase` (hedef yaş, seri, dizi, tip, fiyat, özet) | Aday kitap kümesinden «benzer mi» sınıflaması ve benzerlik gerekçesi (kapalı seçim: benzer/az benzer/değil, tek token + olasılık) | Kategori ağacı yok; metin (özet, tür) karşılaştırması modelin işi. Rakam yok |
| Bölge/kanal payı | faturalı satış `LINENET`, `AMOUNT` (TRCODE 7/8/9 − 2/3, `INVOICEREF<>0`) × CLCARD `SPECODE2`, `CITY`; iade TRCODE 2/3 | `AccountBase.new_distributionstatus`, `new_FirmaKanal`, `OwnerId` (BMT), `new_cariyeaitil` | — | Paylar SQL ile hesaplanır, model üretmez |
| Müşteri tahsisi | cari bazında benzer kitap 8 hafta satış/iade | `new_siparisBase` tip 2 (geçmiş dağılım adedi) | — (kural: pay × plan adedi, yuvarlama, min/maks) | Deterministik ve denetlenebilir |
| Öneri gerekçesi metni | — | — | 3–5 cümle Türkçe gerekçe (hangi kitaplar, hangi pay) — sayıları SQL sonucundan alır, yeni sayı yazmaz | Satış müdürünün güveni |
| Takip | STLINE TRCODE 8 IOCODE 4 (sevk), faturalı satış, TRCODE 2/3 iade; `SHIPINFO` | `new_siparisBase` durum, `new_kargobilgisiBase` | Haftalık özet cümlesi (K1) | Olay Logo'da; CRM süreç durumu |
| Doğal dil soru | katalogdaki ölçüler (net ciro, kanal net ciro, iade oranı, stok bakiyesi) | — | Soruyu mevcut soru hattına yönlendirir (`/api/v1/ask`) | Aynı hat, statik SQL yok |

Model çağrısı yalnız LLM kapısından: `rt.llm_for("dagilim")` (`backend/semantic_bridge/app.py:718`), uzun işler `/api/v1/llm/jobs`; `LlmClient`
doğrudan kurulmaz. Benzerlik sınıflaması kapalı küme + olasılık ile yapılır; olasılık eşik altıysa kitap «benzer» sayılmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/distribution.py` — tablolar, öneri motoru, onay akışı (budget.py deseni), takip, uyarı.
- `backend/semantic_bridge/distribution_sources.py` — Logo/CRM SQL (budget_sources.py `runner`, `firms_by_year` yeniden kullanılır).
- `backend/semantic_bridge/distribution_api.py` — `register(app, rt, require_caller, can)`; `app.py`'de budget_api'nin yanına iki satır.

**Tablolar** (bi_meta Postgres, ilk kullanımda kurulur; `tenant_id` her tabloda)
- `semantic_dist_books` (stok_kodu, ad, yayinevi, depo_giris_tarihi, baski_adedi, kaynak `logo|crm|m12`, stok_bakiye, asof)
- `semantic_dist_plans` (id, stok_kodu, surum, durum `taslak|onayda|onayli|reddedildi|arsiv`, toplam_adet, rezerv_adet, hedef_plan_id (M46),
  hazirlayan, gonderen, onaylayan, onay_zamani, gerekce, olusturma/guncelleme)
- `semantic_dist_plan_lines` (plan_id, bolge, kanal, logo_clientref, crm_account_id, cari_unvan, il, onerilen_adet, adet, elle_duzeltildi, gerekce)
- `semantic_dist_comps` (plan_id, comp_stok_kodu, benzerlik_olasiligi, gerekce, secildi)
- `semantic_dist_tracking` (plan_id, logo_clientref, hafta, sevk_adet, satis_adet, iade_adet, asof)
- `semantic_dist_alerts` (id, plan_id, tur `plan_yok|sevk_gecikti|hic_satmadi|tukendi`, anahtar, durum `acik|kapandi`, ilk/son zaman)
- Her yazma `semantic_audit`'e (`dist_plan`, `dist_line`, `dist_export`).

**Uçlar** (`/api/v1/distribution/*`)
- `GET  /books?durum=` — dağılım bekleyen / izlenen kitaplar
- `POST /plans/generate` {stok_kodu} — öneri (K2)
- `GET  /plans/{id}` · `PATCH /plans/{id}` · `PATCH /plans/{id}/lines/{line}` · `DELETE /plans/{id}` (yalnız taslak)
- `POST /plans/{id}/submit` · `POST /plans/{id}/approve` · `POST /plans/{id}/reject` · `POST /plans/{id}/revise`
- `GET  /plans/{id}/export.xlsx` — sevk listesi
- `GET  /tracking?stok=&hafta=` · `GET /my-region` (BMT: kendi carileri) · `GET /alerts`
- `POST /run-due` — zamanlayıcı (SYSTEM)

**Ekranlar** — `src/canvas/distribution/` (`DistributionScreen.tsx`, `PlanEditor.tsx`, `TrackingTab.tsx`, `MyRegion.tsx` telefon öncelikli, `api.ts`).
Rota `/timas/ilk-dagilim` (+ `/ilk-dagilim/:stok`). Menü: yeni çalışma alanı **`satis` «Satış ve saha»** (`NavGroupId`'ye eklenir; M29–M33 ortak;
ilk kodlanan modül açar, `access_catalog.json` `areas`'a `{id:'satis', label:'Satış ve saha'}`), öğe `{ id: 'ilk-dagilim', label: 'İlk dağılım',
section: 'Planlama' }`. Kampüs: `src/canvas/stitch/ModulesMenu.tsx` → `M29: '/ilk-dagilim'`. Mobil: 320/390/768/masaüstü, yatay taşma yok; plan
matrisi telefonda kart listesine döner.

**Yetki** — `sayfa:ilk-dagilim`; `ozellik:dagilim.plan` (öneri/düzelt/gönder/revize), `ozellik:dagilim.onay` (**explicit**; gönderen onaylayamaz),
`ozellik:dagilim.herkesinki` (kapsam: bütün bölgeler; yoksa BMT yalnız `AccountBase.OwnerId` = kendi SystemUserId olan carileri görür, eşleme
`SystemUserBase.DomainName` = `timas\<hesap>`), export `ozellik:veri.disa-aktar`. `access.py` `RULES`: `("/api/v1/distribution/run-due", SYSTEM)`,
`("/api/v1/distribution/", frozenset({page("ilk-dagilim")}))`; M46 satırlarına `page("ilk-dagilim")` eklenir (`/api/v1/budget/targets`,
`/deviations`). `FEATURE_RULES`'a POST/PATCH/DELETE plan uçları → `ozellik:dagilim.plan`; export → `ozellik:veri.disa-aktar`.

**Zamanlayıcı** — `scripts/server/timas-distribution.{service,timer}`: her gün 07:30 ve 13:30 `POST /api/v1/distribution/run-due`: yeni depoya
girişleri okur, takip tablosunu tazeler, uyarıları açar/kapatır, özet e-postayı gönderir (SMTP yoksa kayıtta bekler). İlk kez elle koşturulur
(bellek: run-it-before-it-runs-itself).

**Kabul testleri** (test sunucusu, `git archive` kopyası, yan port, gerçek Logo + CRM; referans doğrudan SQL, köprü kopyası değil)
1. Depoya giriş: ekrandaki her kitabın giriş tarihi ve adedi =
   `SELECT I.CODE, MIN(L.DATE_) giris, SUM(L.AMOUNT) adet FROM LG_411_01_STLINE L JOIN LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF
    WHERE L.TRCODE = 13 AND L.IOCODE = 1 AND L.LINETYPE = 0 AND L.CANCELLED = 0 GROUP BY I.CODE` (ilk giriş = yeni kitap; baskı tekrarı ayrı sayılır).
2. Hedef: plan başlığındaki hedef adet = `GET /api/v1/budget/targets?year=2026&stok=<kod>` → `items[0].hedef.adet` (birebir).
3. Benzer kitap kanal payı: gerekçedeki her comp kitabın kanal payı =
   `SELECT C.SPECODE2, SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) FROM LG_411_01_STLINE L
    JOIN LG_411_CLCARD C ON C.LOGICALREF = L.CLIENTREF WHERE L.STOCKREF = @comp AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0
    AND L.TRCODE IN (2,3,7,8,9) AND L.DATE_ < DATEADD(day, 56, @ilk_satis) GROUP BY C.SPECODE2` (2021–2025 kitapları için LG_211_01_*).
4. Değişmez: onaylı planda Σ adet + rezerv ≤ stok bakiyesi (Logo stok bakiyesi ölçüsü, tarih filtresiz); aşan plan onaya gidemez (409).
5. Geçmiş dağılım: comps ekranındaki «geçmiş ilk dağılım» adedi =
   `SELECT SUM(ss.new_siparisadeti) FROM Timas_MSCRM.dbo.new_siparisBase s JOIN Timas_MSCRM.dbo.new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId
    WHERE s.new_siparistipi = 2 AND s.statecode = 0 AND ss.statecode = 0 AND ss.<ürün alanı> = @kitap` (satır ürün alanı adı kodlamada şemadan okunur).
6. Takip: kitap × cari sevk adedi = `STLINE TRCODE 8, IOCODE 4, LINETYPE 0, CANCELLED 0, STOCKREF = @kitap, DATE_ >= @onay` toplamı.
7. Dağılım carileri: ekrandaki liste sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.AccountBase WHERE new_distributionstatus = 1 AND StateCode = 0`.
8. Yetki: BMT hesabıyla `/my-region` yalnız kendi carilerini döner; `ozellik:dagilim.onay` olmadan approve 403; gönderen onaylarsa 409.

**Bağımlılık** — M46 bitti (main). M12 paralel kodlanabilir: M29 ilk sürümde Logo üretimden giriş ile çalışır, M12 uç sözleşmesi gelince
`kaynak='m12'` eklenir. `satis` çalışma alanını hangi modül önce açarsa ötekiler ona ekler. Kardeş analizler: M43 Depo/Stok
(`/api/v1/stock/items/{stok_kodu}` — kodlanınca stok bakiyesi oradan okunur, M29 aynı hesabı ikinci kez yazmaz), M44 Kargo
(`/api/v1/shipping/shipments` — kodlanınca «müşteriye ulaştı» takibi oradan), M59 Bayi riski (`/api/v1/dealers/{cari}` — yüksek riskli cariye dağılım uyarısı).

**Büyüklük** — L (3+ gün): öneri motoru + onay + takip + telefon görünümü + kabul.
