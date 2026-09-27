# M24 — Katalog ve Bülten Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M24.txt` (ZEKİ_Moduller3.html), `ZEKİ_Veri_Haritasi2.html` (Katalog Girdileri, Bülten Girdileri — «Müşteri İletişimi» kategorisi), `configs/semantic/knowledge/crm/table_descriptions.json` (2026-09-09), `configs/semantic/knowledge/logo/knowledge/metrics/logo-timas.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/kampus-kisisel-ekran-crm-2026-09-15.md`, `backend/semantic_bridge/management/` (baskı önerisi SQL'leri), `bulletins.py`, `seo_geo/seasons.py`, `seo_geo/store.py`, `alerts.py`, `access.py`, `access_catalog.json`, `src/canvas/nav/navModel.ts`, `docs/LLM-KAPISI.md`, kullanıcı belleği (tsoft-no-write, crm-tsoft-no-push-integration, logo-155-frozen-copy, no-tech-names-on-screens, no-silent-limits-rule, kokpit/Kampüs sesli bülten notları).

> Kural: sunucuya bağlanılmadı. Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım** diye işaretlidir.
>
> Ad karışıklığı: Kampüs'teki **sesli bülten** şirket içi podcasttir (`bulletins.py`, Yönetim → Sesli bülten); bu modülün «bülteni» okura/bayiye giden **e-bülten**dir. İkisi ayrı; yalnız «metinden seslendirme» altyapısı ileride e-bültenin sesli sürümü için ortak kullanılabilir.

## 1. Modül ne işe yarar

İki iş: (1) **Katalog** — mevsimsel/dönemsel katalog için kitap seçimi, sıralama ve öne çıkarma önerisi, sayfa düzeni ve görsel brief, fiyat tablosunun kendiliğinden güncellenmesi (K2). (2) **E-bülten** — okur/müşteri segmentlerine göre kişiselleştirilmiş bülten içeriği, gönderim takvimi, konu satırı seçenekleri, açılma/tıklama/dönüşüm raporu (iş tanımında K1 otomatik gönderim).

TİMAŞ'ın bugünkü sorunu: CRM'de e-posta/SMS kampanya altyapısının izleri var ama küçük ve güncelliği bilinmiyor — «Email Sms Kampanyası» (`CampaignBase`, 28 kayıt; gönderim, okunma, tıklama, kara liste sayıları), kişi başına gönderim sonucu (`obs_kampanyagonderimleriBase`, 139), pazarlama listesi (`ListBase`, 11; «Mailchimp List Id» alanı var), e-posta şablonları (`TemplateBase` 27, `new_emailsablonBase` 11). Kişilerde izin alanları (İYS, KVKK, toplu e-posta izni) ve ilgi alanı işaretleri var. Katalog için CRM'de yalnız eski promosyon bütçesinde «Bülten/Katalog» tipi (`new_promosyonbutcesiBase`, 2 kayıt, 2017/2020). Katalog hazırlığının Excel + tasarımcı eliyle yapıldığı **varsayım**; fiyat ve stok her katalogda elle kontrol ediliyor olmalı (**varsayım**).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Katalog sorumlusu (pazarlama/ürün) | Pazarlama (**varsayım**) | Dönemsel yoğun (katalog başına 2–4 hafta), ara dönem haftalık | Masaüstü |
| Grafik tasarımcı | Grafik (TeamMembership 13) | Katalog başına | Masaüstü |
| Satış / bölge temsilcisi | Satış (TeamMembership 49) | Katalogu kullanır; öneri verir | Telefon (PDF) |
| E-posta / CRM pazarlama uzmanı | Pazarlama ya da e-ticaret (**varsayım**) | Haftalık bülten | Masaüstü |
| E-ticaret sorumlusu | E-ticaret | Kampanya bülteni | Masaüstü |
| Pazarlama müdürü | Pazarlama | Onay | Telefon |
| KVKK / hukuk | Hukuk ya da dış danışman (**varsayım**) | İzin denetimi | — |

## 3. Bugün bu iş nasıl yapılıyor

- **Katalog sorumlusu** (varsayım): kitap listesi Logo/CRM'den Excel'e alınır → satış ve stok elle kontrol edilir → sıralama toplantıda → tasarımcı InDesign'da dizer → fiyatlar son anda yeniden kontrol → PDF/baskı. Tıkanma: fiyat/stok değişince katalog eskir; hangi kitabın katalogda neden yer aldığı kayıtlı değil.
- **E-posta uzmanı**: gönderim CRM'e bağlı bir e-posta/SMS aracıyla (`obs_*` alanları) ya da harici bir bülten aracıyla (Mailchimp izi) — hangisinin bugün kullanıldığı **ölçülecek**. Web sitesi (T-soft) üye/bülten abonesi listesinin nerede tutulduğu **ölçülecek**.
- **Satış temsilcisi**: bayiye katalog PDF'i ya da basılı katalog götürür (**varsayım**).

## 4. İhtiyaçlar ve acı noktaları

**Katalog sorumlusu**
1. Kitap seçimini gerekçeli öneriyle başlatmak (satış hızı, stok, yenilik, sezon/özel gün, tema).
2. Fiyat ve stok bilgisinin katalog taslağında **her an güncel** olması; «fiyatı değişti / stok bitti» uyarısı.
3. Katalog türüne göre farklı liste: bayi/kitapçı, okul/kurum, fuar, yabancı hak (İngilizce).
4. Tasarımcıya giden düzenli veri paketi (Excel + kapak görselleri + tanıtım metinleri).
5. Geçmiş katalogların arşivi ve hangi kitabın kaç katalogda yer aldığı.

**E-posta uzmanı**
1. Segment tanımı (ilgi alanı, yaş grubu, son alışveriş, izin durumu) ve segment büyüklüğünü önceden görmek.
2. Segment başına kitap önerisi ve metin taslağı; 5 konu satırı seçeneği.
3. İzinsiz kişiye gitmediğinin garantisi (İYS/KVKK).
4. Açılma/tıklama/satış raporu tek yerde.

**Pazarlama müdürü**
1. Katalog ve bülten onayı; performans özeti.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Katalog sorumlusu olarak yeni sezon kataloğu için önerilen kitap listesini gerekçeleriyle almak istiyorum, çünkü listeyi elle çıkarmak bir hafta sürüyor.
- Katalog sorumlusu olarak katalog taslağındaki bir kitabın fiyatı ya da stoku değişince uyarı görmek istiyorum, çünkü basılmış katalogda yanlış fiyat bizi zor durumda bırakıyor.
- Katalog sorumlusu olarak tasarımcıya tek tıkla Excel + kapaklar + metinler paketini vermek istiyorum, çünkü dosya toplamak çok zaman alıyor.
- Satış temsilcisi olarak bayiye özel (türe/yaş grubuna göre) kısa katalog PDF'i almak istiyorum, çünkü her bayi her kitabı satmıyor.
- E-posta uzmanı olarak «tarih ilgili, e-posta izni olan, son 12 ayda alışveriş yapmış» segmentin büyüklüğünü görmek istiyorum, çünkü gönderimi planlarken hedefi bilmem gerek.
- E-posta uzmanı olarak segment başına bülten taslağı ve konu satırı seçenekleri almak istiyorum, çünkü her hafta aynı işi yapıyorum.
- Pazarlama müdürü olarak bülten sonuçlarını kitap satışıyla birlikte görmek istiyorum, çünkü bültenin satışa katkısını bilmiyoruz.

**Ana ekranlar ve akış**
- İlk açılış (`/timas/katalog-bulten`): iki sekme — **Kataloglar** (taslak/onayda/yayında listesi, her birinde «fiyat/stok uyarısı» rozeti) ve **Bültenler** (takvim + son gönderim sonuçları).
- Katalog akışı: yeni katalog → tür + dönem + tema seç → Zeki önerilen liste (gerekçe sütunu) → sürükle-bırak sıralama/öne çıkarma → «tasarım paketi indir» / «PDF önizleme».
- Bülten akışı: segment seç (büyüklük görünür) → kitap önerileri → taslak + 5 konu satırı → onay → «gönderime hazır paket» (HTML + segment tanımı).
- En sık 3 işlem: (1) Katalogda uyarılı kitabı gör ve değiştir: 2 tık. (2) Tasarım paketi indir: 1 tık. (3) Bülten taslağı oluştur: 3 tık.

**Zeki AI'a soracakları**
- «Kış kataloğu için son 6 ayda en hızlı satan ve stoğu yeterli çocuk kitapları hangileri?»
- «Geçen katalogdaki kitaplardan fiyatı değişenler hangileri?»
- «Tarih ilgili ve e-posta izni olan kaç kişi var?»
- «[Özel gün] bülteni için hangi kitapları önerirsin?»
- «Son üç bültenin açılma ve tıklama oranı neydi?»
- «[Kitap] için katalog tanıtım metnini 60 kelimeye indir.»

**Otomasyon katmanı**
- K1: fiyat/stok senkronu ve uyarı, segment büyüklüğü hesabı, gönderim sonucu verisinin okunması (CRM'den), rapor.
- K2: katalog kitap seçimi/sıralaması/öne çıkarma, sayfa brief'i, bülten içeriği ve konu satırı → insan onayı.
- İş tanımındaki «K1 otomatik gönderim» ve «terk edilen sepet hatırlatması»: portal ilk sürümde **göndermez** (bölüm 8); gönderim TİMAŞ'ın mevcut e-posta aracından yapılır, portal içerik + segment tanımı üretir. Terk edilen sepet e-ticaret sitesinin (T-soft) olayıdır; T-soft'a yazma yasak, site tarafında kurulur.

**Bildirim/uyarı**
- Katalog sorumlusuna: taslaktaki kitapta fiyat değişti / stok kritik / satıştan kalktı (günlük).
- E-posta uzmanına: bülten onaylandı, gönderim sonucu geldi.
- Pazarlama müdürüne: onay bekleyen katalog/bülten (Uyarılar rozeti).

**Onay ve yetki**
- `sayfa:katalog-bulten`; `ozellik:katalog.duzenle`; `ozellik:bulten.duzenle`; `ozellik:katalog-bulten.onay` (explicit); `ozellik:bulten.segment` (explicit — kişi sayısı ve izin durumunu görmek; kişi listesi portalda gösterilmez).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kitap listesi, künye, tanıtım | CRM `new_kitapBase` (`new_name`, `new_isbn13`, `new_ean13`, `new_StokKodu`, `new_ozet`, `new_kisabilgi`, `new_hedefkitle`, `new_hedefkitleyasbaslangic/bitis`, `new_turlertext`, `new_rafturu`, `new_yayineviid`, `new_YayneviAltMarka`, `new_kitap_yayincilikstatusu`, `new_ilkyayintarihi`) | Var | — |
| Fiyat | CRM `new_kitapBase.new_PerakendeBirimFiyat`, `new_kdvdahilfiyat`; CRM fiyat listesi `new_fiyatlistesiogesiBase` (6.087); Logo `management/sql/baski_oneri/logo_fiyat.sql`; T-soft ürün fiyatı (`semantic_seo_products`) | Üç kaynak; hangisinin katalog fiyatı olduğu **uzmana sorulacak**, farkları **ölçülecek** | Fiyat kaynağı kararı |
| Stok | Logo stok bakiyesi (metrics «Stok bakiyesi»), `logo_depo_stok.sql` | Donmuş kopya: stok bugünün değil, 2026-08-17 hareketleriyle (.155) | Canlı Logo |
| Satış hızı | Logo `logo_satis_hizi.sql`, `V_SatisRaporu_<yıl>` | Donmuş kopya | Canlı Logo |
| Kapak görseli | CRM `new_resimurl`/`new_kapakresmi`; kapak alternatifi yolu CRM sunucusu yerel diski (açılmaz); T-soft ürün görseli | Erişilebilirlik **ölçülecek** | Yüksek çözünürlüklü kapak (baskı kataloğu) |
| Özel gün / sezon | CRM `new_ozelgunlerBase` (93) + kitap bağı (~820); `seo_geo/seasons.py` | Var | — |
| E-posta/SMS kampanya sonuçları | CRM `CampaignBase` (28; `obs_totalcount`, `obs_readcount`, `obs_clickcount`, `obs_blacklistcount`, `TypeCode`), `obs_kampanyagonderimleriBase` (139; `obs_okunmadurumu`, `obs_tiklanmadurumu`), `ListBase` (11; `new_mclistid`, `MemberCount`, `Query`), `ListMemberBase` (29) | Son kullanım tarihi **ölçülecek**; kayıt sayısı küçük → bugün başka araç kullanılıyor olabilir | Kullanılan e-posta aracı ve sonuç verisi |
| Segment: izin | CRM `ContactBase`/`LeadBase`/`AccountBase`: `DoNotBulkEMail`, `DoNotEMail`, `new_iysonayi`, `new_kvkkonayi`, `obs_sendtoemailiys`, `obs_emailpermissionupdatedate`, `new_haberdarolmakistiyorum`, `LeadBase.obs_donotkvkk` | Dolu oranları **ölçülecek** | Web sitesi üyelerinin izni T-soft'ta olabilir (**ölçülecek**, yalnız okuma) |
| Segment: ilgi alanı | CRM `new_contact_new_kitapilgialanBase` (7.022 bağ) + `new_kitapilgialanBase` (5 alan); `ContactBase` bayrakları (`new_tarihveakademi`, `new_sosyalbilimlerincelemearastirma`, `new_timasakademi`, `new_ElenceliBilgi`, `new_SMKitap_ilgiAlani`); `LeadBase.new_ilgialani` | Var; güncelliği **ölçülecek** | — |
| Segment: satın alma geçmişi | CRM sipariş (B2C `new_siparistipi = 8`), T-soft sipariş (okuma **ölçülecek**), Logo e-ticaret kanalı (kişi düzeyinde değil) | Kişi–sipariş bağı **ölçülecek** | Okur düzeyinde alışveriş verisi |
| Bayi/kurum listesi (katalog dağıtımı) | Logo `CLCARD.SPECODE2` (KITAPCI, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR, E-TICARET), CRM `AccountBase` | Var | — |

## 7. Diğer modüllerle bağ

- Girdi: M18 (aylık plan, kampanya takvimi), M17 (backlist canlandırma), M11 (baskı önerisi: stok/satış hızı), M43 (stok), M9 (fiyat), M25 Sezon takvimi, M19 (görsel), M37/M38 (okur topluluğu, CRM segmentleri).
- Çıktı: M27 (fuar kataloğu), M30 (saha satış temsilcisi kataloğu), M31/M32 (okul/kurum kataloğu, B2B), M35 (e-ticaret kampanya bülteni), M41 (yabancı hak kataloğu), M22 (katalog/bülten duyurusu).

## 8. Kısıtlar

- **Portal toplu e-posta göndermez (ilk sürüm).** Toplu ticari ileti 6563 sayılı Kanun ve İYS kurallarına tabidir; gönderim TİMAŞ'ın mevcut, izin yönetimi olan aracından yapılır. Portal SMTP hesabı (tek kişiye bildirim için) toplu bülten için kullanılmaz. Portal içerik, segment tanımı (sorgu) ve sonuç raporu üretir.
- **Kişi listesi dışarı çıkmaz.** Segment ekranı yalnız sayı ve dağılım gösterir; e-posta adresi listesi portaldan indirilmez (gönderim aracı listeyi kendi kaynağından alır). Bu hem KVKK hem veri sızıntısı kuralıdır.
- İzin kuralı: `DoNotBulkEMail = 1` ya da `DoNotEMail = 1` ya da İYS onayı yok → segment sayısına girmez; kural kodda tek yerde, testle.
- T-soft'a yazma yasak (terk edilen sepet, site içi bülten kutusu T-soft tarafında). T-soft'tan yalnız okuma.
- CRM'e yazma yok; katalog/bülten kayıtları `semantic_catalog_*`, `semantic_newsletter_*`.
- Ekranda teknoloji adı yok (e-posta aracının ürün adı müşteri platformu olduğundan ayar ekranında kalabilir; bizim model/dizgi altyapımızın adı geçmez).
- Demo veri yok; sayı tavanı yok (iş tanımındaki «5 konu satırı» öneri sayısıdır, liste tavanı değil).
- Logo verisi 2026-08-17'de donmuş: katalogda fiyat/stok uyarılarının yanında «stok verisi şu tarihe kadar» yazılır.
- Kapak ve tanıtım metni telifi: yabancı yayınevinden alınan kitapların kapak/metin kullanım hakkı sözleşmeye bağlıdır; sözleşmede özel madde (`new_sozlesmeBase.new_haklaraciklama` dolu) varsa uyarı.

## 9. Kapsam önerisi

**İlk sürüm**
- Katalog: tür (bayi, okul/kurum, fuar, yabancı hak, e-katalog), dönem, tema; önerilen liste (kural puanı: satış hızı, stok ay sayısı, yenilik, özel gün bağı, hedef kitle) + Zeki gerekçe cümlesi; sıralama/öne çıkarma; fiyat/stok/satış durumu uyarıları; tasarım paketi (Excel + kapak bağlantıları + tanıtım metinleri); basit PDF önizleme (sayfa başına N kitap şablonu).
- Bülten: segment tanımlayıcı (izin + ilgi alanı + yaş grubu + kanal) ve sayı; segment başına kitap önerisi, gövde taslağı, konu satırı seçenekleri; onay; gönderime hazır HTML.
- Sonuç okuma: CRM `CampaignBase`/`obs_kampanyagonderimleriBase` dolu ise raporlanır; değilse kullanılan araçtan dışa aktarım dosyası içe alınır.

**Sonraki sürüm**
- Baskıya hazır katalog PDF'i (Kitap Tasarım Stüdyosu'nun baskı PDF'i üretim altyapısı yeniden kullanılabilir mi **ölçülecek**).
- Bülten → satış bağı (kampanya kodu/UTM, e-ticaret).
- E-posta aracının resmî API'si ile yalnız okuma sonuç çekme.
- Sesli bülten: bülten metninin «Zeki AI sesi» ile sesli sürümü (Kampüs «Metinden üret» altyapısı).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/management/sql/baski_oneri/` (`logo_fiyat.sql`, `logo_depo_stok.sql`, `logo_satis_hizi.sql`, `crm_kitap.sql`, `crm_yeni_kitap.sql`) ve `management/__init__.py` (`{satis:<yıl>}` genişletme, rapor yenileme).
- `backend/semantic_bridge/seo_geo/seasons.py` (özel gün ↔ kitap), `seo_geo/store.py` (T-soft ürün: görsel/fiyat, EAN-13 bağı), `seo_geo/crm.py` (satıştan kalkma, internette gösterim hakkı).
- `backend/semantic_bridge/board_excel.py` / `editorial_export.py` (Excel/PDF üretimi), `bulletins.py` + stüdyo seslendirme (sonraki sürüm).

## 10. Uzmanlara sorulacak sorular

1. Yılda hangi kataloglar çıkıyor (bayi, okul, fuar, yabancı hak), kim hazırlıyor, hangi biçimde (basılı/PDF)?
2. Katalog fiyatı hangi kaynaktan alınıyor: CRM kitap kartı, CRM fiyat listesi, Logo, web sitesi?
3. E-bülten bugün hangi araçla gönderiliyor; abone listesi nerede (CRM, web sitesi, başka)?
4. İYS kaydı ve izin yönetimi kimde; web sitesi üyelerinin izni CRM'e geliyor mu?
5. Bülten başarısı nasıl ölçülüyor; satışa bağ kuruluyor mu?

## 11. Başarı ölçütü

- Katalog kitap listesinin hazırlanma süresi (bugünkü sorulacak) → 1 günün altı.
- Basıma giden katalogda fiyat/stok hatası: 0 (uyarıların kapanma oranı %100).
- Bülten taslağı → onay süresi.
- Segment başına açılma/tıklama oranının raporlanması (bugün yok).
- İzinsiz kişiye gönderim: 0 (segment kuralı testle kanıtlı).

## 12. Uzman gözüyle en iyi sistem

*15 yıllık yayınevi ürün/katalog ve CRM pazarlama müdürü gözüyle.*

İyi yayınevleri katalogu bir **satış aracı** olarak yönetir: bayiye giden katalog satış hızına ve stoka göre, okul kataloğu yaş/sınıf ve MEB uygunluğuna göre, fuar kataloğu fuarın kitlesine göre, yabancı hak kataloğu hak durumuna göre ayrı kurulur; hepsi aynı kitap verisinden beslenir ve fiyat/stok son dakikaya kadar veri kaynağına bağlıdır. Sektörün dijital katalog araçları (satış temsilcisinin bayiye özel katalog çıkarması, sipariş notu) ve e-posta pazarlama araçları (segment, otomatik akış, izin yönetimi) kendi alanında olgundur; zayıf yan, kitap verisiyle kopuk olmalarıdır. TİMAŞ için mükemmel sistem: **tek kitap verisinden birden çok katalog**, her kitabın katalogda olma gerekçesi, basıma kadar canlı fiyat/stok uyarısı; bültende ise izin kuralını asla delmeyen, segment başına kitap öneren, sonucu satışla birlikte gösteren bir masa — gönderimi izin yönetimi olan araca bırakarak.

**Bir iş günü (katalog dönemi)**
- 09:00 «Kış 2026 bayi kataloğu» taslağı: 3 uyarı (1 fiyat değişti, 1 stok 1 aydan az, 1 satıştan kalktı). Stoku az olanı listeden çıkarır, yerine Zeki'nin önerdiği aynı serinin kitabını koyar.
- 10:30 Satış şefiyle sıralama: öne çıkanlar sayfası sürükle-bırak.
- 12:00 Tasarım paketi tasarımcıya; kapak bağlantısı eksik 2 kitap için grafik ekibine görev.
- 14:00 Okul kataloğu: yaş grubuna göre süzülmüş liste; MEB uygunluk raporu olan kitaplara işaret.
- 16:00 Bülten: «Öğretmenler Günü» segmenti (öğretmen/okul ilgisi, izinli) — ekranda gerçek kişi sayısı ve izin dağılımı; kitap önerisi + 5 konu satırı; müdür onayı; HTML e-posta aracına.
- Ertesi hafta: bülten sonucu + o haftanın e-ticaret satışında önerilen kitaplar.

**«Bunu görürsem hemen kullanırım»**
1. Katalog taslağında canlı fiyat/stok uyarısı.
2. Tek tıkla tasarımcı paketi.
3. Segment büyüklüğünü izin kuralıyla birlikte gösteren sayaç.

**«Bunu yaparsanız kullanmam»**
1. İzin/İYS kontrolünü atlayan ya da kişi listesini dışarı veren özellik.
2. Gerekçesiz «yapay zekâ seçti» katalog listesi.
3. Güncel olmayan (donmuş) stoku güncel gibi gösteren ekran.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Aday kitap havuzu | — | `new_kitapBase` (`statuscode = 1`, `new_kitap_yayincilikstatusu`, `new_hedefkitle`, `new_turlertext`, `new_YayneviAltMarka`) | — | SQL |
| Satış hızı | `logo_satis_hizi.sql`, `V_SatisRaporu_<yıl>` (`[Miktar]`, `[Yıl]*12+[Ay]`, `[Satır Türü]=N'Malzeme'`) | `new_StokKodu` | — | Rakam SQL'den |
| Stok ay sayısı | Stok bakiyesi (STLINE IOCODE, güncel kopya) ÷ aylık satış | — | — | Baskı önerisi tanımı |
| Fiyat | `logo_fiyat.sql` | `new_PerakendeBirimFiyat`, `new_kdvdahilfiyat`, `new_fiyatlistesiogesiBase` | — | Kaynak kararıyla tek fiyat |
| Seçim puanı ve gerekçe | Yukarıdakiler | Özel gün bağı | Kitap başına 1 cümle gerekçe; puan kuralla | Açıklanabilir |
| Katalog tanıtım metni | — | `new_ozet`, `new_kisabilgi` | Katalog uzunluğuna kısaltma (ör. 60 kelime), yabancı hak kataloğu için İngilizce taslak | Metin işi |
| Segment sayısı | — | Contact/Lead izin alanları + ilgi alanı bağı | — | SQL; model kişi verisine dokunmaz |
| Segment başına kitap önerisi | Satış hızı | İlgi alanı ↔ kitap türü eşlemesi | Eşleme gerekçesi | — |
| Bülten metni ve konu satırı | — | Seçilen kitapların metinleri | Gövde taslağı + konu satırı seçenekleri | Metin işi |
| Sonuç raporu | (sonraki) e-ticaret kanal cirosu | `CampaignBase` sayaçları, `obs_kampanyagonderimleriBase` | 3 cümle yorum | Rakamı yorumlar |

Model yalnız LLM kapısından: `rt.llm_for("katalog")` / `rt.llm_for("bulten")`; toplu metin kısaltma `BATCH` önceliğiyle.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/catalogs.py` (katalog kayıtları, puan, uyarı), `newsletters.py` (segment kuralı, bülten kayıtları), `catalogs_sources.py` (CRM/Logo SQL — `management/sql/baski_oneri/*.sql` yeniden kullanılır), `catalogs_api.py` (`register`, iki alt yol).

**Tablolar**
- `semantic_catalogs` (id, tenant_id, kind [bayi/okul/fuar/yabanci-hak/e-katalog], title, season, theme, status [taslak/onayda/onaylı/yayında/arşiv], price_source, stock_as_of, approved_by, created_by, updated_at)
- `semantic_catalog_items` (catalog_id, crm_book_id, position, featured bool, page_hint, reason, price_snapshot, stock_months_snapshot, text_override, alert_json)
- `semantic_newsletters` (id, tenant_id, title, segment_json, segment_size, planned_at, status, subject_options_json, subject_chosen, html, approved_by, sent_ref NULL, created_by)
- `semantic_newsletter_items` (newsletter_id, crm_book_id, position, reason)
- `semantic_newsletter_results` (newsletter_id, source [crm/dosya], sent, opened, clicked, unsubscribed, bounced, imported_at)

**Uçlar** — `/api/v1/catalog-newsletter/`: `GET meta`; katalog `GET catalogs`, `POST catalogs`, `GET catalogs/{id}`, `POST catalogs/{id}/suggest`, `PUT catalogs/{id}/items`, `POST catalogs/{id}/submit|approve`, `GET catalogs/{id}/package.zip`, `GET catalogs/{id}/preview.pdf`, `GET catalogs/{id}/export.xlsx`; bülten `GET newsletters`, `POST newsletters`, `POST segments/count` (yalnız sayı ve dağılım döner), `POST newsletters/{id}/draft`, `POST newsletters/{id}/approve`, `GET newsletters/{id}/html`, `POST newsletters/{id}/results` (dosya), `GET report`; `POST run-due` (SYSTEM).

**Ekranlar** — `src/canvas/catalog-newsletter/` (`CatalogList.tsx`, `CatalogEditor.tsx`, `NewsletterList.tsx`, `NewsletterEditor.tsx`, `SegmentBuilder.tsx`, `Report.tsx`); rota `/timas/katalog-bulten` (+ `/katalog/:id`, `/bulten/:id`, `/rapor`). Menü: `pazarlama`, bölüm `section: 'Kampanya'`, öğe `{ id: 'katalog-bulten', label: 'Katalog ve bülten', icon: BookOpen, hint: 'Dönemsel katalog ve e-bülten' }`. Kampüs: M24 çalışan; Kampüs sesli bülten kartı etkilenmez. Telefon: satış temsilcisi için katalog PDF indirme.

**Yetki** — `sayfa:katalog-bulten`; `ozellik:katalog.duzenle`; `ozellik:bulten.duzenle`; `ozellik:katalog-bulten.onay` (explicit); `ozellik:bulten.segment` (explicit). `access.py`: `("/api/v1/catalog-newsletter/run-due", SYSTEM)`, `("/api/v1/catalog-newsletter/", frozenset({page("katalog-bulten")}))`; FEATURE_RULES: catalogs yazma → `ozellik:katalog.duzenle`, newsletters yazma → `ozellik:bulten.duzenle`, `segments/count` → `ozellik:bulten.segment`, package/preview/export → `ozellik:veri.disa-aktar`.

**Zamanlayıcı** — `scripts/server/timas-catalog.timer` her gün 07:15: taslak/onaylı kataloglarda fiyat/stok/satış durumu uyarılarını yeniler (`alert_json`), CRM kampanya sonuçlarını okur.

**Kabul testleri**
1. Stok ay sayısı: katalogdaki 10 kitabın stok ay sayısı, Yönetim raporları › Baskı önerisi ekranındaki değerle ve `logo_depo_stok.sql` + `logo_satis_hizi.sql` doğrudan çalıştırılarak birebir.
2. Fiyat: seçilen kaynak CRM ise `SELECT new_kdvdahilfiyat FROM Timas_MSCRM.dbo.new_kitapBase WHERE new_kitapId = '<guid>'` = katalog satırındaki fiyat; fark varsa uyarı rozeti.
3. Segment sayısı (izinli, tarih ilgili kişi) = `SELECT COUNT(DISTINCT c.ContactId) FROM Timas_MSCRM.dbo.ContactBase c WHERE c.statecode = 0 AND ISNULL(c.DoNotBulkEMail,0) = 0 AND ISNULL(c.DoNotEMail,0) = 0 AND c.new_iysonayi = 1 AND NULLIF(LTRIM(c.EMailAddress1),'') IS NOT NULL AND c.new_tarihveakademi = 1` — ekrandaki sayı ile birebir; izin alanlarından biri eksikse sayıya girmediği ayrıca test edilir.
4. Özel gün önerisi: özel güne bağlı aday sayısı SEO Sezon takvimi kabulündeki `new_new_kitap_new_ozelgunlerBase` sorgusuyla aynı.
5. CRM kampanya sonucu: rapordaki gönderim/okunma/tıklama = `SELECT obs_totalcount, obs_readcount, obs_clickcount FROM Timas_MSCRM.dbo.CampaignBase WHERE CampaignId = '<guid>'`.
6. Satıştan kalkan kitap: `new_kitap_yayincilikstatusu` «çekildi/iptal» olan kitap öneri listesinde yok; SEO «Haklar ve CRM» sınıflamasıyla aynı sonuç.
7. Kişi verisi dışarı çıkmıyor: hiçbir uç e-posta adresi döndürmüyor (uç yanıtlarında `@` içeren alan taraması).

**Bağımlılık** — Bağımsız; baskı önerisi SQL'leri ve Sezon takvimi hazır. Fiyat kaynağı kararı (soru 2) ilk kodlamadan önce alınmalı; alınmazsa ayar olarak üç kaynaktan biri seçilir, varsayılan CRM `new_kdvdahilfiyat` ve bu varsayım ekranda yazar. M27/M30/M31 kataloğu tüketir, beklemez.

**Tahmini büyüklük** — L (3+ gün): katalog M, bülten M, PDF önizleme S.
