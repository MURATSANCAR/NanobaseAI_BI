# M43 — Depo ve Stok Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M43.txt`, `specs/M11.txt`, `specs/M12.txt`, `specs/M29.txt`,
`ZEKİ_Veri_Haritasi2.html` (M43/M11 satırları), `configs/semantic/knowledge/logo/knowledge/{rules/logo-erp.md, metrics/logo-timas.md,
caveats/logo-timas.md, rules/crm-timas.md}`, `configs/semantic/knowledge/crm/{OKUNUR-TABLOLAR.md, table_descriptions.json}`,
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/pbit-yeni-baski-oneri/README.md`,
`backend/semantic_bridge/management/sql/baski_oneri/*.sql`, `backend/semantic_bridge/access_catalog.json`,
`src/canvas/nav/navModel.ts`, `src/canvas/modules.json`, bellek: `timas-logo-database-shape`, `logo-period-prefixes-are-years`,
`logo-155-frozen-copy`, `sales-are-invoiced-lines`, `timesfm3-baski-oneri-backtest`, `no-silent-limits-rule`, `no-tech-names-on-screens`.
Sunucuya bağlanılmadı; bu belgede yeni ölçüm yok. Sayılar yukarıdaki dosyalardaki eski ölçümlerdir (tarihiyle).

## 1. Modül ne işe yarar

İş tanımı (M43): depodaki her kitabın stokunu izlemek, kritik stokta uyarmak, ölü/fazla stoku bulmak, 30-60-90 günlük talep
tahminiyle yeniden sipariş (baskı tekrarı) zamanını önermek, depo yerleşimini (hızlı dönen kitap öne) iyileştirmek. Çıktılar: stok
panosu, talep tahmini, ABC analizi, fazla/ölü stok listesi, devir hızı.

TİMAŞ'ın bugünkü sorunu (kanıtla): Logo'da **asgari/azami stok seviyesi hiç girilmemiş** (`INVDEF.MINLEVEL` 3,98 milyon
malzeme–ambar satırının hiçbirinde > 0 değil, ölçüm 2026-09-18) — yani "kritik stok" bugün hiçbir sistemde tanımlı değil. Stok
kararları Power BI "Yeni Baskı Öneri" raporuyla veriliyordu (artık portalda `/yonetim-raporlari/baski-oneri`). Depo operasyonu
(raf, toplama, koli, sayım) **CRM'de** yürüyor; finansal stok **Logo'da**; ikisinin mutabakatı hiç ölçülmedi.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Depo müdürü / depo sorumlusu | CRM talep yönetiminde departman "Depo" (kod 7) var; SystemUser↔Depo çoka-çok 137 bağ | Her gün, gün içinde birkaç kez | Masaüstü + telefon (depo sahasında; varsayım) |
| Depo toplayıcı / raf personeli | SystemUser `new_toplayici` bayrağı, sipariş `new_pusulayitoplayanid` | Vardiya boyunca | Telefon / el terminali (varsayım) |
| Stok planlama – üretim (baskı tekrarı kararına girdi veren) | CRM departman "Üretim" (kod 10); M11 onay akışı Satış+Pazarlama → Üst Yönetim | Haftada 1–2, 15 günlük tarama (M11) | Masaüstü |
| Satış operasyon (bekleyen ürün, "stokta var mı?") | TeamMembership Satış 49 kişi (2026-09-15 ölçümü) | Her gün, soru bazında | Telefon + masaüstü |
| Finans / mali işler (stok değeri, sayım farkı, fire) | TeamMembership Mali İşler 10 | Ay sonu, sayım dönemi | Masaüstü |
| Üst yönetim (stok sağlığı özeti) | — | Haftalık/aylık | Telefon (varsayım) |

## 3. Bugün bu iş nasıl yapılıyor

- **Depo müdürü:** CRM'de 45 depo tanımı (`new_depo`, Logo ambar maliyet grubu `new_ambarmaliyetgrubu` ile), 6.385 raf (`new_raf`:
  raf tipi Ana/Perakende, satışa açık, raf yerleşim önceliği, barkod), raf bazında seri/lot hareketi (`new_serilothareketsatiri`
  9,06 Mn satır, `new_rafid`), malzeme hareketi (`new_malzemehareketi` 395 bin fiş: Üretimden Giriş, Faturalı Kabul, Sayım
  Fazlası/Eksiği, İade, Raf Transferi, Depolar Arası Sevk, İrsaliye, Set İşlemi) ve **`new_logoyaaktarildi` bayrağıyla Logo'ya
  aktarım**. Yani fiziksel hareket CRM'de başlıyor, Logo'ya fiş olarak geçiyor (yön CRM → Logo; kanıt: kolon adları ve
  `new_logomesaji`; aktarım hata oranı ölçülmedi). Sayım `new_stoksayimi` (742 kayıt, raf + ürün + kullanıcı). Tıkanma
  (varsayım): CRM'deki raf stoğu ile Logo bakiyesi arasındaki farkı gösteren bir ekran yok; Logo'ya aktarılamayan fiş
  `new_logomesaji`'nda kalıyor.
- **Toplayıcı:** sipariş durumu Depoda Bekliyor → Pusula Alındı/Toplanıyor → Kutulanıyor → Kutulandı → Sevk Edildi
  (`new_siparisBase.statuscode` + her geçişin tarih kolonu: `new_DepodaBekliyorDurumu`, `new_pusulaalinditarih`,
  `new_sipariskutulanditarihi`, `new_sevktarihi`). Koli stoğu `new_kutustogu` (185 bin). Adım sayısı ölçülmedi.
- **Stok planlama / yönetim:** Power BI raporu (Logo `.25` üzerindeki `EOS_DEPO_STOK_KONTROL_211` görünümü + satış hızı + CRM
  bekleyen sipariş) → portaldaki Baskı Öneri raporu 2026-09-23'ten beri aynı hesabı yapıyor. Asgari seviye olmadığından "kritik"
  kararı rapordaki "Risk/Acil" etiketiyle ve kişisel tecrübeyle veriliyor (varsayım).
- **Satış operasyon:** sipariş anındaki stok CRM satırında kopya olarak duruyor (`new_siparisanindakistokadedi`,
  `new_stokdurumu` Stok Var/Yok); stok yoksa **bekleyen ürün** kaydı açılıyor (`new_bekleyenurun` 772.616 satır). Bekleyen ürünün
  stok gelince kapatılması elle/akışla (hangisi olduğu ölçülmedi).
- **Finans:** stok bakiyesi Logo'dan; `STINVTOT` boş, stok `STLINE` hareketlerinden hesaplanıyor (katalog notu). Maliyet
  (`OUTCOST`) 30.06.2026'ya kadar işlenmiş.

## 4. İhtiyaçlar ve acı noktaları

**Depo müdürü**
1. Tek ekranda "Logo bakiyesi ↔ CRM raf stoğu" farkı, kitap ve depo bazında (sayım ve aktarım hatalarını bulmak için).
2. Logo'ya aktarılamayan CRM hareketlerinin listesi (`new_logoyaaktarildi = 0`, `new_logomesaji` dolu) ve yaşı.
3. Depo doluluk / raf yerleşimi: hızlı dönen kitap hangi rafta, arka rafta kalan çok satan var mı.
4. Sipariş hazırlık hattının darboğazı: hangi aşamada kaç sipariş, ne kadar bekliyor.

**Stok planlama**
1. Kitap başına "kaç gün yeter" (stok ÷ satış hızı) ve tükenme tarihi; asgari seviye olmadığı için sistem önerecek.
2. 30-60-90 gün talep tahmini (mevcut tahmin servisinden), okul sezonu zirvesinin eksik tahmin edildiği bilinerek.
3. Fazla/ölü stok listesi ve eritme önerisi (kampanya → M17/M35, set → M53, iade/imha kararı insan).

**Satış operasyon**
1. "Şu kitaptan kaç tane var, hangi depoda, ne zaman gelir?" sorusuna telefonda 10 saniyede cevap.
2. Bekleyen ürün birikimi: stok girdiği hâlde kapanmamış bekleyenler.

**Finans**
1. Sayım farkı (fazla/eksik) tutarı ve fire/imha, ay bazında.
2. Stok devir hızı ve stok değeri (maliyetli kısmı ayrı, maliyetsiz satır sayısı söylenerek).

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Depo müdürü olarak Logo ile CRM raf stoğu arasındaki farkı kitap bazında görmek istiyorum, çünkü sayım listesini buna göre hazırlarım.
- Depo müdürü olarak Logo'ya geçmemiş hareketleri sabah görmek istiyorum, çünkü gün içinde düzeltilmezse fatura/irsaliye kayar.
- Depo müdürü olarak son 90 günün en hızlı dönen 200 kitabının rafını görmek istiyorum, çünkü toplama yolunu kısaltırım.
- Stok planlama sorumlusu olarak "30 gün içinde bitecek kitaplar" listesini baskı süresiyle birlikte görmek istiyorum, çünkü baskı tekrarını zamanında tetiklerim (→ M11/M12).
- Stok planlama sorumlusu olarak kitap bazında güvenlik stoku önerisini onaylamak istiyorum, çünkü Logo'da seviye girilmemiş.
- Satış temsilcisi olarak telefonda kitap adı yazıp stok, bekleyen sipariş ve beklenen baskı tarihini görmek istiyorum, çünkü müşteriye söz veririm.
- Finans uzmanı olarak ay sonunda sayım farkı ve hareketsiz stok değerini görmek istiyorum, çünkü karşılık ayırırım.

**Ana ekranlar ve akış**
- Açılış (`/stok`): üstte 4 gösterge (toplam kitap stoğu adet, stokta olmayan aktif kitap, 30 gün içinde bitecek kitap, Logo'ya
  aktarılamamış hareket) — her birinin altında kaynak ve "veri tarihi" (Logo son fatura günü açıkça yazılır). Altında "bugün
  ilgilenilecekler" listesi (bitecekler + aktarım hatası + fark).
- Kitap arama (tek kutu, `SearchSelect`) → Kitap stok kartı: depo × raf dağılımı, satış hızı, gün cinsinden yeterlilik, bekleyen
  sipariş, M12'den açık üretim kartı ve tahmini depo girişi.
- Sekmeler: Stok listesi · Bitecekler · Fazla/ölü stok · Logo–CRM farkı · Depo hattı (sipariş aşamaları) · ABC.
- En sık 3 işlem: (1) kitap sor → 2 tık (ara + seç); (2) bitecekleri Excel'e al → 2 tık; (3) güvenlik stoku önerisini onayla → 3 tık.

**Zeki AI'ya soracakları örnek sorular**
- "Önümüzdeki 30 günde stoğu bitecek çocuk kitapları hangileri?"
- "Merkez depoda olup perakende rafında olmayan çok satanlar?"
- "Son 12 ayda hiç satmamış ama stokta 1.000'den fazla olan kitaplar?"
- "Mavi Kirpi'nin stok devir hızı geçen yıla göre nasıl?"
- "Bekleyen siparişi en çok olan 20 kitap ve stok durumu?"
- "Geçen ayki sayım eksiği kaç adet, hangi raflarda?"
- "Logo'ya aktarılamayan depolar arası sevkler neden hata verdi?"

**Otomasyon katmanı**
- K1 (tam otomatik, salt okuma): stok/satış hızı/yeterlilik hesabı, bitecekler ve aktarım hatası uyarısı, günlük stok bülteni.
- K2 (Zeki önerir, insan onaylar): kitap bazında güvenlik stoku / yeniden sipariş noktası önerisi, fazla stok eritme önerisi,
  raf yerleşim önerisi. Onay portal tablosuna yazılır; Logo `INVDEF`'e ve CRM'e **yazılmaz**.
- K3 (Zeki analiz, insan karar): baskı tekrarı adedi (M11/M12'ye devredilir), imha/iade kararı.
- K4 (tamamen insan): sayım, fiziksel raf değişikliği, Logo/CRM'de düzeltme fişi.
- İş tanımındaki "stok kararları → LOGO güncelleme entegrasyonu" bu sürümde **yok**: Logo'ya yazma kullanıcı kararıdır (açık soru).

**Bildirim / uyarı**
- Depo müdürü: her sabah 08:00 e-posta (planlı rapor) — aktarım hataları + fark + bitecekler; ayrıca Uyarılar'da eşik kuralı.
- Stok planlama: yeterlilik ≤ baskı süresi + güvenlik günü olduğunda anında (uyarı kuralı, 15 dk kontrol).
- Satış: bekleyen ürünün stoğu girdiğinde (günlük özet).
- Kanal: portal zili + e-posta (mevcut SMTP); telefon bildirimi yok.

**Onay ve yetki (öneri)**
- `sayfa:stok` (görme) — depo, üretim, satış, finans, yönetim.
- `ozellik:stok.esik-onay` (güvenlik stoku/yeniden sipariş noktası onayı) — **açıkça verilir** (stok planlama + depo müdürü).
- `ozellik:stok.maliyet` (stok değeri ve birim maliyet görme) — açıkça verilir (finans, yönetim).
- `ozellik:stok.depo-hatti` (sipariş hazırlık hattı ve kişi bazlı toplama süreleri) — açıkça verilir (depo müdürü); kişi
  performansı hassas veridir.

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kitap stok bakiyesi | Logo `LG_411_01_STLINE` (IOCODE 1,2 giriş − 3,4 çıkış, LINETYPE 0, CANCELLED 0, tarihsiz) | Katalog tanımı var ("iş teyidi bekliyor"); `STINVTOT` boş | Power BI'ın kullandığı `EOS_DEPO_STOK_KONTROL_211` görünümüyle fark **ölçülecek**; .155 donmuş kopya (son fatura 2026-08-17) |
| Ambar bazında stok | `STLINE.SOURCEINDEX` + `L_CAPIWHOUSE` (FIRMNR = 411) | Kural 14 tanımlı | Ambar sayısı ve adları **ölçülecek**; CRM 45 depo ↔ Logo ambar eşlemesi `new_depo.new_deponumarasi` üzerinden varsayım |
| Raf bazında stok | CRM `new_serilothareketsatiri` (`new_kalanmiktar`, `new_rafid`), `new_raf`, `new_depo` | Tablolar ve kolonlar biliniyor (2026-09-09 profili) | "Kalan miktar"ın güncel raf stoğu olup olmadığı **ölçülecek** (lot bazlı kalan mı?) |
| Depo hareketi ve Logo'ya aktarım | CRM `new_malzemehareketi` (+ satır), `new_sevkiyat` (`new_logoyaaktarildi`, `new_logomesaji`) | Kolonlar biliniyor | Aktarılamamış fiş sayısı **ölçülecek** |
| Sayım | CRM `new_stoksayimi` (742), Logo sayım fişleri (TRCODE 50/51 sayım fazlası/eksiği; varsayım — LDDS'e bakılacak) | CRM tablosu biliniyor | Son sayım tarihi ve kapsamı **ölçülecek** |
| Satış hızı | Logo `V_SatisRaporu_<yıl>` (faturalı satır) — `management/sql/baski_oneri/logo_satis_hizi.sql` | Canlıda çalışıyor (Baskı Öneri) | Yok |
| Bekleyen sipariş | CRM `new_siparis` + satır — `crm_bekleyen_siparis.sql`; Logo `ORFLINE` (AMOUNT − SHIPPEDAMOUNT) | İki tanım var; CRM tanımı raporda kullanılıyor | Hangisinin esas olduğu iş kararı (Soru 3) |
| Bekleyen ürün (stok yokken talep) | CRM `new_bekleyenurun` (statuscode 1 Bekleyen) | Tablo biliniyor | Stok girince kapanma süresi **ölçülecek** |
| Talep tahmini | Mevcut tahmin servisi (`management/zeki_tahmin.py`), geçmiş stok `LV_<firma>_01_STINVTOT.ONHAND` | Sınamada WAPE %35 (dönem toplamı); okul zirvesi −%27…−%33 eksik | Stoksuz ayları maskeleme deneyi yapılmadı |
| Açık üretim / beklenen depo girişi | M12 (`/api/v1/editorial/production/cards`), CRM `new_Uretim.new_DepoGiriTarihi` | M12 kodlanıyor | M12 bitmeden yalnız CRM planı |
| Birim maliyet | Logo `STLINE.OUTCOST` | 30.06.2026'ya kadar işli; 2026 satış satırlarının %20'sinde 0 | Maliyetsiz satırlar ayrıca sayılır |
| Asgari/azami seviye | Logo `INVDEF.MINLEVEL/MAXLEVEL` | **Girilmemiş** (ölçüm 2026-09-18) | Portal öneri + onay tablosu gerekir |
| Depo kapasitesi (m³, palet, raf hacmi) | — | Hiçbir kaynakta yok | Kullanıcı girer (Soru 4) |
| Fire / imha | Logo fire fişi (TRCODE 11 fire; varsayım — LDDS'e bakılacak) | Kural 20: imha ayrı işlem türü | **Ölçülecek** |

## 7. Diğer modüllerle bağ

- Girdi: M11 Baskı Tekrarı (satış hızı + öneri; bu modül M11'e stok ve "kaç gün yeter" verir), M12 Üretim (açık kart, beklenen
  depo girişi, `/print-exit`), M1–M4/M10 satış tahmini (iş tanımı), M35/M17 kampanya takvimi (talep sıçraması), M42 kanal
  siparişleri.
- Çıktı: M11/M12 (bitecekler → baskı tekrarı önerisi), M29 İlk Dağılım (depo stoğu), M17 Backlist pazarlama ve M35 kampanya
  (fazla stok eritme listesi), M53 Set (set işlemi stoğu), M44 (sipariş hazırlık hattı süreleri), M45 finans (stok değeri),
  M52 (depo kapasitesi × baskı adedi uyumu).

## 8. Kısıtlar

- Logo ve CRM yalnız okunur; onaylanan eşik/öneri köprünün kendi tablosunda (`semantic_stock_*`). Logo `INVDEF`'e yazma yok.
- T-soft'a yazma yasak (stok senkronu dahil); T-soft stok alanı yalnız okunabilir.
- Ekranda teknoloji adı yok (tahmin "Zeki AI tahmini"; Power BI yerine "mevcut rapor").
- Demo veri yok; asgari seviye yoksa ekranda "tanımlı değil" yazar, uydurma eşik gösterilmez.
- Sayı tavanı yok: listeler sayfalanır, "ilk N" kesilmez.
- Veri tazeliği: .155 Logo donmuş (satış 2026-08-17), CRM canlı → ekran her rakamın veri gününü gösterir; canlı Logo (.25) erişimi
  gelmeden "bugünkü stok" iddia edilmez.
- KVKK / hassas: SystemUser `new_deposifre` hiçbir sorguda seçilmez; kişi bazlı toplama süresi yalnız `ozellik:stok.depo-hatti`.

## 9. Kapsam önerisi

**İlk sürüm (en çok değer, en az bağımlılık)**
- Kitap stok listesi + kitap stok kartı (Logo bakiyesi, ambar kırılımı, CRM raf dağılımı, satış hızı, gün cinsinden yeterlilik).
- Bitecekler listesi (yeterlilik ≤ N gün; N kullanıcı seçer), bekleyen sipariş ve M12 açık kartı yanında.
- Logo–CRM stok farkı ve Logo'ya aktarılamamış hareketler.
- Fazla/ölü stok (hareketsiz, devir hızı düşük) — Kural 17 ve sertifikalı "stok devir hızı".
- Günlük stok bülteni (planlı rapor) ve eşik uyarıları (Uyarılar modülü).

**Sonraki sürüm**
- Güvenlik stoku / yeniden sipariş noktası önerisi + onay (tahmin + M12 ölçülen baskı süresi).
- 30-60-90 gün tahmin sekmesi (stoksuz ay maskesiyle), ABC analizi (ciro ve adet), raf yerleşim önerisi.
- Depo hattı (sipariş aşama süreleri) ve sayım planlama; depo kapasitesi girildikçe doluluk.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/management/sql/baski_oneri/{logo_depo_stok.sql, logo_satis_hizi.sql, crm_bekleyen_siparis.sql}` ve
  `management/baski_oneri.py` (5 dk önbellek, `{satis:<yıl>}` yer tutucusu, kaynak SQL paneli).
- `backend/semantic_bridge/management/zeki_tahmin.py` (tahmin istemcisi).
- `backend/semantic_bridge/alerts.py` (eşik kuralı), `reports.py` (planlı rapor e-postası), `board.py` (pano kartı).
- `backend/semantic_bridge/freelance_logo.py` ve M12 `production.py` içindeki firma/dönem bulma (`L_CAPIPERIOD`).
- `src/canvas/components/SearchSelect.tsx`, `src/canvas/management/` tablo + ⓘ kaynak paneli, `src/canvas/DataRefresh.tsx`.

## 10. Uzmanlara sorulacak sorular

1. Depo stoğunun "doğru" kaynağı hangisi: Logo bakiyesi mi, CRM raf/lot kalanı mı? Fark çıkarsa hangisine inanıyorsunuz?
2. 45 CRM deposundan hangileri gerçek fiziksel depo, hangileri sanal (konsinye, fuar, numune, hasarlı)? Stok hesabına hangileri girer?
3. "Bekleyen sipariş" için esas CRM sipariş satırı mı, Logo sipariş (ORFLINE) mi? B2C ve iki iç cari hariç tutma kuralı geçerli mi?
4. Depo kapasitesi (palet/raf sayısı, m²) ve baskı tekrarında kabul süresi (matbaadan çıkış → rafa yerleşme) nedir?
5. Güvenlik stoku kaç günlük satış olmalı; okul sezonu (Ağustos–Ekim) için ayrı mı? Logo'daki asgari seviyeyi ileride doldurmak ister misiniz?

## 11. Başarı ölçütü

- Satış temsilcisinin "stokta var mı" sorusunun cevap süresi < 15 sn (ekran/soru günlüğünden).
- Logo–CRM stok farkı olan kitap sayısı ilk 3 ayda azalıyor (aylık ölçüm).
- Stoksuz kalınan gün sayısı (satış hızı > 0 iken bakiye ≤ 0) çeyrek bazında azalıyor.
- Bitecekler listesinden M11/M12'ye giden öneri oranı ve öneri → depo girişi süresi.
- Haftalık aktif kullanıcı: depo + üretim + satış rollerinde ≥ %60 (erişim günlüğü).

## 12. Uzman gözüyle en iyi sistem

Rol: 15 yıllık yayınevi depo ve stok müdürü. Sektör pratiği (genel bilgi, TİMAŞ verisiyle doğrulanmadı): büyük yayınevleri ve
dağıtım merkezleri stoğu **kitap × depo × raf/lokasyon** düzeyinde, gerçek zamanlıya yakın izler; baskı tekrarı kararı "gün cinsinden
kapsama" (days of cover) ve baskı süresiyle verilir; ABC/XYZ sınıflamasıyla hızlı dönen kitaplar toplama yoluna yakın konur;
dönemsel tam sayım yerine sürekli döngüsel sayım yapılır; iade (kitapçıdan dönen) ayrı bir akış olarak ayıklanır. Gelişmiş depo
yönetim yazılımları (WMS) dalga toplama, lokasyon önerisi ve el terminali kullanır. TİMAŞ'ta bu iskelet CRM'de zaten var (raf, lot,
pusula, koli, sayım); eksik olan **üstündeki karar katmanı**: fark, kapsama, öneri, uyarı.

TİMAŞ için mükemmel sistem: Logo'nun finansal bakiyesi ile CRM'in raf stoğunu her gece karşılaştıran, farkı kök nedeniyle (aktarım
hatası, sayım, iade) gösteren; her kitap için "kaç gün yeter + baskı kaç günde gelir" hesabını yapıp bitmeden 1 baskı süresi önce
uyaran; okul sezonunu ayrı öğrenen; fazla stoğu kampanya/set önerisine çeviren bir pano.

Bir iş günü:
- 07:45 Telefonda sabah bülteni: "Logo'ya aktarılamayan 12 hareket (3'ü depolar arası sevk), 18 kitap 30 gün içinde bitiyor, 4'ünde
  açık baskı kartı yok."
- 08:15 Masaüstünde "Bugün ilgilenilecekler": aktarım hatalarını tıklar, CRM fiş numarası ve Logo mesajı görünür, BT'ye iletir.
- 09:30 Bitecekler: açık üretim kartı olmayan 4 kitabı üretime (M12) "baskı tekrarı değerlendirilsin" notuyla gönderir (portal kaydı).
- 11:00 Satıştan soru: "X kitabı 500 adet var mı?" → Zeki AI'ya sorar, kitap kartı: Logo 620, merkez depo raf 540, 80'i iade rafında.
- 14:00 Logo–CRM farkı sekmesi: farkı en büyük 30 kitabı döngüsel sayım listesine ekler (Excel).
- 16:30 Fazla stok: 24 aydır satmayan 1.000+ adetli kitapları pazarlamaya (M17/M35) öneri olarak gönderir.
- 17:30 Güvenlik stoku önerilerinden 10'unu onaylar, 3'ünü gerekçeyle düzeltir.

"Bunu görürsem hemen kullanırım":
1. Kitap kartında tek bakışta: Logo bakiyesi, raf dağılımı, kaç gün yeter, açık baskı ve tahmini depo girişi.
2. Logo'ya geçmemiş CRM hareketleri ve hata mesajı — sabah listesi.
3. "Bitmeden baskı süresi kadar önce" uyarısı (asgari seviye girmeden).

"Bunu yaparsanız kullanmam":
1. Veri tarihi yazmadan "bugünkü stok" göstermek (Logo kopyası donmuşken yanlış güven verir).
2. Logo ve CRM'i birleştirip tek sayı göstermek, farkı gizlemek.
3. Uydurma/varsayılan eşikle kırmızı alarm yağdırmak (asgari seviye yokken "kritik" demek).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Stok bakiyesi | `LG_411_01_STLINE` (IOCODE 1,2 − 3,4; LINETYPE 0; CANCELLED 0), `LG_411_ITEMS` (CODE, NAME, SPECODE = yayınevi), `EOS_DEPO_STOK_KONTROL_211` (karşılaştırma) | — | Hiçbir şey | Rakam SQL'den; finansal bakiye Logo'dadır |
| Ambar kırılımı | `STLINE.SOURCEINDEX` + `L_CAPIWHOUSE` (NR, NAME, FIRMNR = 411) | `new_depo` (`new_deponumarasi`, `new_ambarmaliyetgrubu`) | — | Depo adlarını iki sistemde eşlemek |
| Raf stoğu | — | `new_serilothareketsatiri` (`new_kalanmiktar`, `new_rafid`, `new_malzemehareketsatiriid`), `new_raf` (`new_raftipi`, `new_satisaacik`), Product (`ProductNumber` = stok kodu) | — | Operasyonel stok CRM'de |
| Aktarım hatası | — | `new_malzemehareketi` (`new_islemturu`, `new_logoyaaktarildi`, `new_logomesaji`, `new_fistarihi`) | Hata mesajını sınıflandırır (kapalı küme: cari/stok kartı yok, dönem kapalı, miktar yetersiz, bağlantı, diğer) — tek token + olasılık | Serbest metin Logo mesajını gruplamak insan için değerli |
| Satış hızı ve yeterlilik | `V_SatisRaporu_<yıl>` (faturalı satır, `Yıl*12+Ay`), `logo_satis_hizi.sql` | — | — | Aynı hesap Baskı Öneri ile birebir kalmalı |
| Bekleyen sipariş | `LG_411_01_ORFLINE` (TRCODE 1, CLOSED 0, AMOUNT − SHIPPEDAMOUNT) | `new_siparis`/`new_siparissatiri` (`crm_bekleyen_siparis.sql`), `new_bekleyenurun` | — | İki tanım yan yana, kaynağı yazılı |
| Devir hızı / ölü stok | Sertifikalı ölçü «stok devir hızı» (TRCODE 14 devir + bakiye), Kural 17 hareketsiz stok | — | Fazla stok listesine eritme önerisi gerekçesi yazar (kampanya/set/bekle), rakamlar SQL'den verilir | Öneri metni karar hızlandırır |
| Talep tahmini | Aylık satış geçmişi (`baski_oneri_tahmin/logo_aylik_gecmis.sql`), `LV_<firma>_01_STINVTOT.ONHAND` | — | Model değil, tahmin servisi (`zeki_tahmin.py`) | Sayısal tahmin dil modelinin işi değil |
| Sabah bülteni | Yukarıdaki hesaplar | Yukarıdaki | 5–8 cümlelik özet (sayılar metne SQL'den enjekte edilir, model yalnız sıralar ve bağlar) | Telefonda okunur özet |
| Doğal dil soru | Katalog ölçüleri | CRM katalog | Mevcut soru hattı (`ozellik:zeki.soru`) | Yeni hat kurulmaz |

Model çağrısı: köprü içinde `rt.llm_for("stok")`; zamanlanmış bülten betiğinde `QueuedLlm(..., purpose="bg:stok")`. `LlmClient`
doğrudan kurulmaz. Ekranda yalnız "Zeki AI".

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/stock.py` — iş kuralları: bakiye birleştirme, yeterlilik (`gun = bakiye / (satis_hizi/30)`), bitecekler,
  fark sınıflaması, öneri üretimi; 5 dk önbellek ve `X-Data-Refresh` (M12 `production.py` deseni).
- `backend/semantic_bridge/stock_sources.py` — salt okunur Logo/CRM bağlantısı (management'taki gibi kendi bağlantısı), firma
  bulma `L_CAPIPERIOD`, SQL dosyaları `backend/semantic_bridge/stock_sql/*.sql`:
  `logo_bakiye.sql`, `logo_ambar_bakiye.sql`, `logo_eos_stok.sql` (karşılaştırma), `logo_devir.sql`, `logo_hareketsiz.sql`,
  `logo_orfline_bekleyen.sql`, `crm_raf_stok.sql`, `crm_aktarim_hatasi.sql`, `crm_bekleyen_urun.sql`, `crm_depo.sql`,
  `crm_depo_hatti.sql`. Satış hızı ve CRM bekleyen sipariş için `management/sql/baski_oneri/` dosyaları **import edilir, kopyalanmaz**.
- `backend/semantic_bridge/stock_store.py` — portal tabloları.
- `backend/semantic_bridge/stock_api.py` — uçlar.

**Tablolar (bi_meta Postgres, ilk kullanımda kurulur)**
- `semantic_stock_thresholds` (id, tenant_id, stok_kodu, depo_no NULL, guvenlik_gun, yeniden_siparis_adet, kaynak 'oneri'|'elle',
  durum 'taslak'|'onayli'|'red', gerekce, onaylayan, onay_tarihi, created_at).
- `semantic_stock_suggestions` (id, tenant_id, tur 'bitecek'|'fazla'|'raf'|'esik', stok_kodu, payload_json, model_gerekce, durum,
  karar_veren, karar_tarihi, hedef_modul 'M11'|'M12'|'M17'|'M35'|'M53').
- `semantic_stock_snapshots` (tenant_id, gun, stok_kodu, logo_bakiye, crm_raf, satis_hizi) — gece fotoğrafı; eğilim ve tahminde
  stoksuz ay maskesi için. Satır sınırı yok.
- `semantic_stock_notes` (stok_kodu, not, yazan, tarih) — sayım/düzeltme notu.

**Uçlar** (`/api/v1/stock/*`): `GET meta`, `GET overview`, `GET items?q=&yayinevi=&depo=&durum=&sayfa=`, `GET items/{stok_kodu}`,
`GET running-out?gun=`, `GET excess`, `GET diff` (Logo–CRM), `GET transfer-errors`, `GET pick-line` (depo hattı),
`GET suggestions`, `POST suggestions/{id}/decision`, `GET thresholds`, `POST thresholds`, `POST thresholds/{id}/approve`,
`GET export/{liste}.xlsx`.

**Ekranlar** `src/canvas/stock/`: `StockHome.tsx` (/stok), `StockItem.tsx` (/stok/:stokKodu), `RunningOut.tsx` (/stok/bitecekler),
`Excess.tsx` (/stok/fazla), `StockDiff.tsx` (/stok/fark), `TransferErrors.tsx` (/stok/aktarim), `PickLine.tsx` (/stok/depo-hatti),
`Thresholds.tsx` (/stok/esikler). Rota `/timas/stok…`. Menü: yeni çalışma alanı `lojistik` (etiket «Lojistik»; `modules.json`
grubu ile aynı ad) — `NavGroupId`'ye eklenir; bölümler «Stok» (Stok, Bitecekler, Fazla stok, Esikler) ve «Depo» (Logo–CRM farkı,
Aktarım hataları, Depo hattı). Kampüs: modül kartı «Depo ve stok» + sabah bülteni kartı (depo rolünde).

**Yetki** (`access_catalog.json`, alan `lojistik`): `sayfa:stok`, `sayfa:stok-bitecekler`, `sayfa:stok-fazla`, `sayfa:stok-fark`,
`sayfa:stok-aktarim`, `sayfa:stok-depo-hatti`, `sayfa:stok-esikler`; `ozellik:stok.esik-onay` (explicit), `ozellik:stok.maliyet`
(explicit), `ozellik:stok.depo-hatti` (explicit), `ozellik:stok.oneri-karar`. Uçlarda `need(user, ...)` (M12 deseni).

**Zamanlayıcı**: `timas-stock.timer` her gün 06:30 — gece fotoğrafı (`semantic_stock_snapshots`), bitecek/fark/aktarım hesabı,
öneri üretimi (model kuyruğu arka plan önceliği); 07:30 planlı rapor bülteni mevcut `timas-reports.timer` ile. Uyarı kuralları
mevcut `timas-alerts.timer` (15 dk). İlk kurulumda elle bir kez koşturulur (bellek: zamanlı işi önce elle koştur).

**Kabul testleri (gerçek veri, aynı kaynakta doğrudan SQL ile birebir)**
1. 20 rastgele kitap için ekrandaki Logo bakiyesi =
   `SELECT i.CODE, SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT ELSE -l.AMOUNT END) FROM dbo.LG_411_01_STLINE l JOIN dbo.LG_411_ITEMS i ON i.LOGICALREF = l.STOCKREF WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.IOCODE IN (1,2,3,4) AND i.CODE IN (...) GROUP BY i.CODE`.
2. Ambar kırılımı toplamı = kitap toplamı (aynı sorgu `GROUP BY i.CODE, l.SOURCEINDEX`), fark 0.
3. Satış hızı: 20 kitapta ekran = Baskı Öneri raporundaki `satis_hizi` (aynı SQL dosyası; fark 0).
4. Devir hızı: 20 kitapta ekran = katalogdaki sertifikalı «stok devir hızı» formülünün doğrudan SQL'i (bilinen referans:
   İYİLİK TİMİ 1,09 — aynı kopyada yeniden ölçülerek).
5. Aktarım hatası sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_malzemehareketiBase WHERE new_logoyaaktarildi = 0 AND statecode = 0 AND new_logomesaji IS NOT NULL`.
6. CRM raf stoğu: 20 kitapta ekran = `SELECT p.ProductNumber, SUM(s.new_kalanmiktar) FROM new_serilothareketsatiriBase s JOIN new_malzemehareketsatiriBase m ON m.new_malzemehareketsatiriId = s.new_malzemehareketsatiriid JOIN Product p ON p.ProductId = m.new_urunid WHERE s.statecode = 0 GROUP BY p.ProductNumber` (kalan miktarın anlamı önce ölçülür; Soru 1).
7. Hareketsiz stok listesi sayısı = Kural 17 doğrudan SQL'i (dönem 12 ay).
8. Boş sonuç ayrıca sorgulanır: bitecekler 0 çıkarsa satış hızı ve bakiye kaynağı ayrı ayrı kontrol edilir (bellek: doğrulama doğrudan DB'den).

**Bağımlılık**: M11 ile aynı satış hızı SQL'i (var). M12 açık kart bilgisi için M12'nin `/cards` ucu (paralel kodlanabilir; M12 yoksa
CRM `new_Uretim` planı gösterilir). Yetki mekanizması (rol bazlı) mevcut `access.py`. M43, M44 ve M52'den önce bitmeli (depo hattı
ve kapasite onlara girdi).

**Tahmini büyüklük**: L (ilk sürüm: köprü + 4 ekran + zamanlayıcı ≈ 3–4 gün; öneri/eşik onayı ikinci sürümde M).
