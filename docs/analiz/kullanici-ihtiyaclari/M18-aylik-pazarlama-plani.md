# M18 — Aylık Pazarlama Planları (Yeni Kitap + Backlist) ve FÖY: kullanıcı ihtiyaç analizi

Durum: kodlandı (dalda, sunucuda doğrulanmadı — günlük 2026-09-28 «M18») · Tarih: 2026-09-28 · Kaynaklar: `specs/M18.txt`, `specs/M46.txt` («M18 pazarlama planları: kitap bazlı hedef vs. gerçekleşme», «%80 altı sapma → M18 ve M30»), `specs/M22.txt`, `specs/M28.txt`, `specs/M32.txt` (M18 çıktısını okuyanlar), `ZEKİ_Veri_Haritasi2.html` (Plan Girdileri, M46 Satış Hedefleri, Performans Girdileri), `configs/semantic/knowledge/crm/table_descriptions.json` (döküm 2026-09-09), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`, `docs/GELISTIRME-GUNLUGU.md` (M46 girişi), `backend/semantic_bridge/budget.py`, `budget_sources.py`, `budget_api.py`, `board.py` / `board_excel.py`, `reports.py`, `seo_geo/seasons.py`, `management/sql/baski_oneri/crm_yeni_kitap.sql`, `src/canvas/nav/navModel.ts`, `docs/analiz/kullanici-ihtiyaclari/M15-yeni-kitap-pazarlama.md` ve `M17-backlist-pazarlama.md` (ortak çekirdek ve girdiler), kullanıcı belleği (sales-are-invoiced-lines, logo-155-frozen-copy, tsoft-no-write, no-tech-names-on-screens, no-silent-limits-rule, crm-systemuser-directory, llm-gate).

> Kural: sunucuya bağlanılmadı. CRM satır sayıları tablo sözlüğünün 2026-09-09 dökümündendir (canlıda **ölçülecek**). Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım**.

## 1. Modül ne işe yarar

Her ay için tek bir **pazarlama ayı planı** kurar: o ay çıkacak yeni kitapların lansman takvimi (M15/M16), backlist aktivasyonları (M17), özel günler ve B2B kampanyaları tek takvimde; kanal bazlı bütçe yeni kitap / backlist arasında M46'nın aylık hedeflerine göre ağırlıklandırılır; çakışmalar (aynı hafta aynı kitaplıkta iki lansman, aynı kanalda üst üste kampanya) gösterilir. Aynı modül her yeni kitap için tek sayfalık **B2B Satış Föyü (FÖY)** üretir (kapak, özet, hedef kitle, fiyat, barkod, satış argümanları) ve aylık föy paketini saha satışı (M30), B2B/kurumsal satış (M32) ve kurumsal ilişkilere (M28) iletir (iş tanımı: K1 takvim, K2 FÖY — satış onaylar, K2 öncelik ve bütçe — yönetici onaylar).

TİMAŞ'ın bugünkü sorunu: ay planı pazarlamanın kendi dosyalarında (varsayım), satış hedefiyle bağı yok (hedef M46 ile daha yeni geldi); föyün metni CRM kitap kartında var (`new_TantmFyMetni` «Tanıtım / Föy Metni», 4.653 kitapta dolu; `new_FyinTaslakFiyat` «Föy İçin Taslak Fiyat») ama föy belgesi elle dizilip e-postayla dağıtılıyor (varsayım). Ay sonunda «plan tuttu mu» sorusunu cevaplayan bir ekran yok.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Pazarlama müdürü (ay planının sahibi, bütçe/öncelik onaycısı) | Pazarlama (ekip 35 kişi; CRM «Pazarlama Yöneticisi Onayı» alanları) | Ayda 1 plan + haftalık gözden geçirme | Masaüstü |
| Pazarlama ekibi (sosyal, dijital, basın, kitap sorumluları) | Pazarlama | Her gün (takvim) | Masaüstü + telefon |
| Satış müdürü (FÖY onaycısı) | Satış (ekip 49 kişi) | Ayda 1 (föy paketi), haftalık | Masaüstü |
| Bölge / saha satış temsilcisi (BMT) — föy kullanıcısı | Satış. Kanıt: CRM `SystemUser.new_KullancTipi` 1 = BMT, 2 = Kurum Temsilcisi; CRM satış hedefleri `new_satishedefleriBase` bölge + BMT alanı | Ziyaret öncesi, günlük | **Telefon** |
| Kurumsal / B2B satış | Satış (varsayım; M32) | Aylık | Masaüstü |
| Genel müdür | Yönetim | Ayda 1 (özet) | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

- **Pazarlama müdürü** (varsayım): ay planı Excel/paylaşımlı takvimde; yeni kitaplar yayın takviminden, backlist kampanyaları özel günlerden seçiliyor; bütçe payı deneyimle. CRM'de ay planı nesnesi yok. Harcama CRM «Pazarlama Bütçe Modülü»nde (435 kayıt) ve «Reklam» planında (71) tutuluyor olabilir (2026 kullanımı **ölçülecek**). B2B kampanyaları CRM `new_kampanyaBase`'te (308; başlangıç–bitiş, ek iskonto, planlanan/gerçekleşen ciro, kampanya mecrası CRM/B2B).
- **FÖY** (varsayım, CRM izine dayanarak): föy metni ve taslak fiyat kitap kartına yazılıyor; tek sayfalık föy grafik ekibince diziliyor (InDesign/benzeri, **varsayım**), PDF olarak satışa e-postayla gidiyor. Tıkanma: her ay onlarca föy elle diziliyor, fiyat/barkod değişince föy eski kalıyor, saha temsilcisi telefonda doğru sürümü bulamıyor.
- **Satış**: kitap bazlı bölge hedefleri CRM'de ayrı bir tabloda (`new_satishedefleriBase`, 334.982 satır; yıl 2023–2026, bölge — Babıali, D&R, Hepsiburada, Ege… — stok kodu, 12 ay hedef, BMT). Bu tablonun M46 hedefleriyle ilişkisi **ölçülecek** (M46 bu tabloyu okumuyor).
- **Performans** (önceki ay): sosyal medya/reklam/e-bülten metrikleri portalda yok; satış Logo'dan (donmuş kopya), saha siparişleri CRM'de.

## 4. İhtiyaçlar ve acı noktaları

**Pazarlama müdürü**
1. Ayın bütün pazarlama işlerini (yeni kitap, backlist, özel gün, B2B kampanyası) tek takvimde ve kitap/kanal/hafta kırılımında görmek.
2. Bütçeyi yeni kitap ve backlist arasında M46'nın o ayki hedef payı ve hedef açığına göre dağıtan, gerekçeli bir öneri.
3. Çakışma uyarısı: aynı hafta aynı kitaplık/hedef kitlede birden çok lansman; aynı kanalda üst üste kampanya.
4. Önceki ayın sonucu: hedef/gerçekleşen (M46), plan işlerinin yapılma oranı, lansman raporları (M16).

**Satış müdürü**
1. Her yeni kitabın föyü ayın başından önce hazır ve onaylı; fiyat/barkod CRM'le tutarlı.
2. Föy paketinin tek dosya (PDF) ve kitap kitap indirilebilir olması.

**Saha temsilcisi (BMT)**
1. Telefonda o ayın föylerini açmak, bayiye göstermek, PDF paylaşmak.
2. Föyde fiyat, barkod, hedef kitle ve «neden satılır» üç maddesi.

**Pazarlama ekibi**
1. Kendine düşen günlük işleri takvimden görmek (M22 sosyal medya zamanlaması bu takvimden beslenir).

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Pazarlama müdürü olarak **ayın 15'inde gelecek ayın taslak planını kendiliğinden hazır** bulmak istiyorum, çünkü planı sıfırdan kurmak iki gün sürüyor.
- Pazarlama müdürü olarak **bütçe dağılımını M46 hedef payı ve açığıyla gerekçeli** görmek ve düzeltip onaylamak istiyorum.
- Pazarlama müdürü olarak **çakışmaları** plan onaylanmadan görmek istiyorum.
- Satış müdürü olarak **ayın bütün yeni kitap föylerini tek listede, eksik alanlarıyla** görmek ve onaylamak istiyorum.
- Saha temsilcisi olarak **telefonda föyü açıp PDF olarak paylaşmak** istiyorum.
- Genel müdür olarak **ay sonunda plan–hedef–gerçekleşen özetini** tek sayfada görmek istiyorum.

### Ana ekranlar ve akış
- **İlk açılış (`/pazarlama/aylik-plan`)**: ay seçici (varsayılan: içinde bulunulan ay; 15'inden sonra gelecek ay önerilir). Üç blok: (1) **Takvim** (hafta × kanal ızgarası; kartlar: yeni kitap lansmanı, backlist aktivasyonu, özel gün, B2B kampanyası; çakışma kırmızı çerçeve), (2) **Bütçe ve öncelik** (yeni/backlist payı, kanal dağılımı, M46 aylık hedef payı ve önceki ay oranı; Zeki AI önerisi ve gerekçesi), (3) **FÖY** (ayın yeni kitapları: föy durumu, eksik alan, onay). Üstte önceki ay özet şeridi (hedefe oran, yapılan iş oranı).
- **FÖY ekranı (`/pazarlama/foy/:stok`)**: tek sayfa önizleme + alanlar (kaynağı yanında: CRM alanı / Zeki AI / elle); telefonda önizleme ve «Paylaş / PDF».
- En sık üç işlem: (1) takvimde karta tıklayıp ilgili plana gitmek — 1 tık; (2) bütçe önerisini düzeltip onaya göndermek — 2–3 tık; (3) föy paketini indirmek — 1 tık.

### Zeki AI'ya soracakları
1. «Kasım'da çıkan yeni kitapların hedef cirosu ayın toplam hedefinin yüzde kaçı?»
2. «Ekim planında aynı haftaya düşen çocuk kitabı lansmanları hangileri?»
3. «Eylül'de hedefin %80 altında kalan kitaplar ve o kitaplar için bu ay planlanan işler?»
4. «Bu ayın föylerinde fiyatı CRM'le uyuşmayan var mı?»
5. «Geçen ay planlanan sosyal medya işlerinin kaçı yapıldı?»
6. «Bu ayın pazarlama planını genel müdüre üç paragrafta özetle.»
7. «Aralık için backlist'e ayırdığımız bütçe geçen aralığa göre nasıl?»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| Ay takviminin toplanması (onaylı M15/M17 planları, M16 lansmanları, özel günler, CRM B2B kampanyaları) | K1 | Taslak ay planı her ayın 15'inde kendiliğinden kurulur |
| Çakışma denetimi | K1 | Kural tabanlı |
| Önceki ay sonucu (hedef/gerçekleşen, yapılan iş) | K1 | SQL + M46 izleme |
| Bütçe dağılımı (yeni/backlist, kanal) | K2 | Kod hesaplar (hedef payı × açık), Zeki AI gerekçe yazar, müdür onaylar |
| Backlist canlanma öncelikleri | K2 | M17 listesinden; müdür seçer |
| FÖY alanlarının CRM'den doldurulması | K1 | Eksik alan işaretlenir |
| FÖY satış argümanları (CRM'de yoksa) | K2 | Zeki AI taslak, satış müdürü onaylar |
| FÖY paketinin iletilmesi | K2 | Onaydan sonra tek tıkla e-posta/indirme; kendiliğinden gönderilmez |
| Platform bazlı içerik şablonları, reklam başlık varyantları | K2 | M19'a istek olarak gider |

### Bildirim / uyarı
- Ayın 15'i: gelecek ayın taslak planı hazır → pazarlama müdürüne.
- Ayın 20'si: föyü eksik ya da onaysız yeni kitaplar → kitap sorumlusuna ve satış müdürüne.
- Föy onaylanınca / paket hazır olunca → satış dağıtım listesine (Yönetim → Pazarlama ayarındaki alıcılar) tek e-posta, K2 onayıyla.
- M46 sapma uyarısı (%80 altı) ay planındaki bir kitaba denk gelirse → ay planı sahibine haftalık özet.
- Ay sonu + 3 iş günü: önceki ay özeti → pazarlama müdürü ve genel müdür.

### Onay ve yetki
- Ay planını görür: `sayfa:pazarlama-aylik`. FÖY'ü görür (saha dahil): `sayfa:pazarlama-foy`.
- Ay planı yazma: `ozellik:pazarlama.plan-yaz`; onay: `ozellik:pazarlama.plan-onay` (explicit; gönderen onaylayamaz).
- FÖY düzenleme: `ozellik:pazarlama.foy-yaz`; FÖY onayı: `ozellik:pazarlama.foy-onay` (explicit; satış müdürü).
- FÖY paketini e-postayla gönderme: `ozellik:pazarlama.foy-gonder` (explicit).
- Bütçe tutarları: `ozellik:pazarlama.butce-gor` (saha föyde bütçe görmez; föyde bütçe yok).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Ay içi yayın takvimi | M15 onaylı planları; CRM `new_kitapBase.new_ilkyayintarihi` (UTC saklanır — `crm_yeni_kitap.sql` notu), `new_projeBase` önerilen yayın tarihi, `new_UretimBase.new_dagilimtarihi` | Alanlar var | İş tanımı «M1–M8 çıktısı» diyor; bugün CRM'den |
| Backlist aktivasyonları | M17 onaylı planları | M17 henüz yok | M17'ye bağlı; yoksa blok boş ve «backlist planı yok» yazar |
| Özel günler | CRM `new_ozelgunlerBase` + kitap bağı; SEO sezon tabloları | `seo_geo/seasons.py` | — |
| B2B/CRM kampanyaları | CRM `new_kampanyaBase` (tarih, mecra, iskonto, planlanan/gerçekleşen ciro), `new_new_kampanya_productBase` | Tablo sözlüğünde | 2026 kullanımı **ölçülecek** |
| Aylık hedef (yeni + backlist) | M46 `targets?year=&segment=yeni|backlist` → `items[].aylik[ay]` | Main'de | Onaylı plan yoksa hedef boş, ekran söyler |
| Hedef sapması | M46 `deviations?status=acik&scope=kitap&module=M18` | Main'de (`modules` alanı var) | — |
| Önceki ay gerçekleşen | M46 izleme (`targets.gerceklesme`) ya da Logo STLINE faturalı satır | M46 Logo'yu saatlik okuyor | Logo .155 donmuş (17.08.2026) — önceki ay «veri yok» olabilir; ekran söyler |
| Kampanya performansı (Meta, Google, TikTok) | Platform API'leri | **Yok** | M21/M22 bağlantısına kadar yok; elle özet alanı |
| E-bülten açılma/tıklama | E-posta pazarlama aracı | **Yok**; CRM «Email Sms Kampanyası» (28) ve gönderim (139) küçük | Aracın adı **uzmana sorulacak** |
| Saha sipariş verisi | CRM `new_siparisBase` (tip, sahip), `new_etkinlikBase` (ziyaret) | Canlı | BMT ↔ sipariş eşlemesi **ölçülecek** |
| Bölge satış hedefleri | CRM `new_satishedefleriBase` (bölge × stok × ay, BMT) | 334.982 satır | M46 ile ilişkisi ve 2026 doluluğu **ölçülecek** |
| FÖY alanları | CRM `new_kitapBase`: `new_name`, `new_yazartext`, yayınevi/kitaplık/dizi, `new_ean13`, `new_kdvdahilfiyat`, `new_FyinTaslakFiyat`, `new_TantmFyMetni`, `new_tanitimfoymetni`, `new_kitapspotu`, `new_ozet`, `new_kitabinonecikanyanlari` («Bu Kitap Neden Önemli?», 6.471), `new_editorunkitabaveyazaradairgorusleri` (4.991), `new_hedefkitle`, yaş başlangıç/bitiş, sınıf, sayfa sayısı, ebat, cilt | Doluluk kısmen ölçülü (`crm-eticaret`) | Sayfa/ebat alan adları ve doluluğu **ölçülecek** |
| Kapak görseli | Stüdyo kapağı (işi varsa); CRM `new_resimurl` (göreli yol); T-soft ürün görseli (SEO modülü okuyor) | Kısmen | CRM göreli yolunun tam adresi **ölçülecek** |
| Logo fiyatı | Baskı Öneri `logo_fiyat.sql` (stok kodu başına güncel birim fiyat) | Canlı raporda | CRM fiyatıyla farkı denetlenir |

## 7. Diğer modüllerle bağ

- **Girdi**: M15 (yeni kitap planları, onaylı materyaller) · M16 (lansman takvimi ve sonuçları) · M17 (backlist aktivasyonları) · M46 (aylık hedef, sapma) · M53 (sezon setleri) · M19 (onaylı görseller) · SEO sezon takvimi.
- **Çıktı**: M22 (onaylı aylık içerik takvimi — «otomatik çekim»), M21 (kanal bütçeleri), M24 (bülten/katalog planı), M30 (föy paketi, saha öncelik listesi), M32 (föy + kampanya takvimi B2B site içerik planlaması için), M28 (föy — kurumsal hediye seçimi), M46 (bütçe revizyon önerisi bilgisi).

## 8. Kısıtlar

- **CRM'e yazma yok**: iş tanımındaki «Onay → Dynamics CRM kampanya kaydı» yapılmaz; «CRM'e işlenecek» listesi. Föyün onaylı metni CRM kitap kartına elle işlenir (liste verilir).
- **Dış kanala kendiliğinden gönderim yok**: föy paketi yalnız onaydan sonra, kişinin tıklamasıyla e-postayla gider; sosyal medya zamanlaması M22'nin işi ve orada da onaylı.
- **T-soft'a yazma yasak.**
- **Veri sonu**: önceki ay performansında Logo veri sonu yazılır.
- **Ekranda teknoloji adı yok**; **demo veri yok**; **sayı tavanı yok** (ayın bütün kitapları, föylerin tamamı).
- **Hukuki**: föydeki fiyat «tavsiye edilen satış fiyatı» ifadesiyle (varsayım; satış biriminin dili sorulacak). Föyde kapak ve yazar fotoğrafı kullanım hakkı M6 sözleşmesine bağlı.

## 9. Kapsam önerisi

**İlk sürüm**
- Ay planı taslağının kendiliğinden kurulması: CRM yayın tarihleri + (varsa) M15/M17 onaylı planlar + özel günler + CRM B2B kampanyaları.
- Takvim (hafta × kanal), çakışma denetimi.
- Bütçe/öncelik: M46 aylık hedef payı ve önceki ay oranıyla yeni/backlist dağılım önerisi (kod), Zeki AI gerekçesi, onay.
- FÖY: CRM alanlarından tek sayfa PDF, eksik alan işareti, Zeki AI satış argümanı taslağı (yalnız eksikse), satış müdürü onayı, aylık paket (birleşik PDF + zip), telefondan görüntüleme/paylaşma.
- Önceki ay özeti (M46 izleme + plan işlerinin yapılma oranı).

**Sonraki sürüm**
- Platform ve e-bülten performans okuması (M21/M22/M24 bağlantılarıyla).
- M22'ye takvim sözleşmesi (onaylı içerik günleri), M30/M32'ye föy sözleşmesi (uç).
- Kurumsal sunum sürümü (çok kitaplı katalog föyü).

**Mevcut kodda yeniden kullanılacaklar**
- Pazarlama çekirdeği (`backend/semantic_bridge/marketing/`, M15 §14) ve `semantic_mkt_plan_books` (M17 §14).
- `budget.approved_targets` (aylık dağılım), M46 sapma kayıtları.
- `seo_geo/seasons.py`, `management/sql/baski_oneri/crm_yeni_kitap.sql` (UTC notu), `logo_fiyat.sql`.
- PDF: köprüdeki fpdf2 yolu (sohbet PDF'i ve bütçe dışa aktarımıyla aynı; Türkçe yazı tipi hazır), Excel/CSV: `board_excel.py`.
- `reports.py` (planlı e-posta; ay sonu özeti planlı rapor olarak da kurulabilir), `alerts.smtp_settings`.

## 10. Uzmanlara sorulacak sorular

1. Bugünkü föy şablonu nedir (örnek PDF), hangi alanlar zorunlu, kim diziyor ve kim onaylıyor?
2. Ay planı hangi gün kesinleşmeli; ay içinde revizyon nasıl yapılıyor?
3. Yeni kitap / backlist bütçe payı için bir kural var mı (sabit oran, hedefe göre)?
4. CRM «Satış Hedefleri» (bölge × kitap × ay) tablosu bugün kullanılıyor mu; M46 hedefleriyle ilişkisi ne olmalı?
5. E-bülten ve sosyal medya için hangi araçlar kullanılıyor; performans verisi dışa alınabiliyor mu?

## 11. Başarı ölçütü

- Ayın ilk iş gününden önce onaylanan ay planı oranı; taslaktan onaya süre.
- Yayın ayından önce onaylı föyü olan yeni kitap oranı; föy–CRM fiyat/barkod uyumsuzluğu sayısı (hedef 0).
- Saha temsilcilerinin föy açma sayısı (telefon), paket indirme sayısı.
- Plan işlerinin yapılma oranı ve ay sonu hedef/gerçekleşen (M46) — trend.

## 12. Uzman gözüyle en iyi sistem

**Kim konuşuyor:** 15 yıllık pazarlama müdürü; her ay satış toplantısına plan ve föyle giren.

**Sektörde iyi örnekler** (genel sektör uygulaması; TİMAŞ'ta doğrulanmadı): yayınevleri ay/sezon başında satış ekibine «satış konferansı» öncesi föy (advance information) paketini verir; föy tek sayfadır ve meta veri sisteminden kendiliğinden üretilir (fiyat, barkod, format elle yazılmaz). Pazarlama takvimi yeni başlık ile katalog (backlist) işini birlikte planlar; bütçe hedef açığı olan kitaplara kaydırılır; ay sonunda «plan / yapılan / sonuç» üçlüsü gözden geçirilir.

**TİMAŞ için mükemmel sistem:** ayın 15'inde gelecek ayın taslak takvimi, bütçe önerisi ve föy paketi hazır; müdür bir saatte düzeltip onaylar; föy paketi saha temsilcisinin telefonuna ve satış müdürünün e-postasına tek tıkla gider; ay sonunda hedef/gerçekleşen ve yapılan işler tek sayfada.

**Bir iş günü (ayın 16'sı):**
- 09:00 — Gelecek ayın taslak planı: 14 yeni kitap, 3 özel gün (22 bağlı backlist), 2 B2B kampanyası. Takvimde iki kırmızı çakışma: aynı hafta iki gençlik romanı lansmanı.
- 09:30 — Birini bir hafta kaydırmak için kitap sorumlusuyla konuşur, M15 planında tarihi değiştirir; takvim düzelir.
- 10:00 — Bütçe: Zeki AI önerisi «yeni kitap %X / backlist %Y» (M46'da gelecek ayın hedefinin büyük kısmı backlist'te ve eylülde backlist %80 altında). Oranı biraz değiştirir, gerekçe yazar, genel müdür onayına gönderir.
- 11:00 — FÖY: 14 föyün 11'i hazır, 3'ünde fiyat CRM'de boş (kırmızı). Kitap sorumlularına iş düşer.
- 14:00 — Satış müdürü föyleri onaylar; paket PDF'i satış dağıtım listesine gönderilir.
- 16:00 — Genel müdür telefonda ay özetini açar: geçen ay hedefin %… (M46), planlanan 60 işin 51'i yapıldı.
- Ertesi gün — Bir saha temsilcisi bayide telefondan föyü açıp WhatsApp'la PDF paylaşır.

**«Bunu görürsem hemen kullanırım» (3):**
1. Föyün CRM'den kendiliğinden dolması ve fiyat/barkod uyumsuzluğunda kırmızı uyarı.
2. Tek takvimde yeni kitap + backlist + özel gün + B2B kampanyası, çakışmalar işaretli.
3. Bütçe önerisinin M46 hedef payı ve açığıyla gerekçelenmesi.

**«Bunu yaparsanız kullanmam» (3):**
1. Föyü portalda yeniden yazdırmak ya da her föyü tek tek indirmek zorunda bırakmak.
2. Onayım olmadan satış ekibine föy ya da plan göndermek.
3. Takvimi sadece masaüstünde çalışır yapmak (saha telefonla çalışıyor).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Ay takvimi toplama | — | `new_kitapBase.new_ilkyayintarihi`, `new_projeBase` tarihleri, `new_UretimBase.new_dagilimtarihi`, `new_ozelgunlerBase` + bağ, `new_kampanyaBase` (tarih, mecra) | — | Deterministik |
| Çakışma denetimi | — | Kitaplık (`new_kitaplikid`), hedef kitle, kampanya tarihleri | — | Kural |
| Aylık hedef ve sapma | — (M46 okur) | — | — | M46 uçları |
| Önceki ay gerçekleşen | `LG_{firma}_01_STLINE` faturalı satır, iade eksi, net ciro = LINENET (M46 izleme) | — | — | SQL |
| Bütçe dağılımı önerisi | Önceki ay satış/hedef oranı | Önceki ay CRM pazarlama harcaması (varsa) | Hesaplanan dağılımın gerekçe cümlesi (rakamları tablodan aynen alır) | Rakamı kod üretir |
| FÖY alanları | Güncel fiyat (`logo_fiyat.sql`) — CRM fiyatıyla karşılaştırma | `new_kitapBase` föy/künye alanları, yazar, kitaplık, dizi, hedef kitle, `new_ean13`, `new_kdvdahilfiyat`, `new_FyinTaslakFiyat` | — | Deterministik |
| FÖY satış argümanları | — | `new_kitabinonecikanyanlari`, `new_editorunkitabaveyazaradairgorusleri`, `new_ozet`, `new_TantmFyMetni` | CRM'de «Bu Kitap Neden Önemli?» boşsa üç kısa satış argümanı taslağı; CRM metninden öteye bilgi eklemez | Metin özetleme |
| Ay özeti (genel müdüre) | Önceki ay ölçüleri | Plan işleri | Üç paragraf özet; rakamlar tablodan | Yorum |
| Doğal dil soru | Katalog | Katalog | Mevcut sohbet hattı | — |

Model çağrıları LLM kapısından: `rt.llm_for("marketing", BATCH)` (15'indeki taslak, föy argümanları), ekranda yeniden yaz `NORMAL`. `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Ön koşul**: pazarlama çekirdeği (`backend/semantic_bridge/marketing/`, tablolar M15 §14) + `semantic_mkt_plan_books` (M17 §14). M18'in FÖY kısmı çekirdeğe bağlı değildir; önce o kodlanabilir.

**Yeni dosyalar**: `marketing/monthly.py` (ay planı), `marketing/foy.py` (föy alanları, doğrulama, PDF), `marketing/foy_pdf.py` (fpdf2 şablonu; Türkçe yazı tipi köprüdeki PDF yolundan).

**Tablolar**
- Ay planı: çekirdeğin `semantic_mkt_plans` satırı, `kind='aylik'`, `donem='YYYY-MM'` (tenant + dönem için tek yürürlükteki sürüm; revizyon yeni sürüm).
- `semantic_mkt_month_items`: `id`, `plan_id` (ay planı), `tur` (`yeni|backlist|ozel-gun|b2b-kampanya|set|diger`), `kaynak_ref` (M15/M17 plan id, CRM kampanya id, özel gün id), `stok_kodu`, `kitaplik`, `hedef_kitle`, `hafta`, `baslangic`, `bitis`, `kanal`, `butce`, `cakisma_json`.
- `semantic_mkt_month_budget`: `plan_id`, `segment` (`yeni|backlist`), `kanal`, `oneri`, `onayli`, `hedef_payi` (M46), `onceki_ay_oran`, `gerekce`.
- `semantic_mkt_foy`: `id`, `tenant_id`, `stok_kodu`, `donem`, `surum`, `alanlar_json` (her alan: değer + kaynak `crm:<alan>|logo|zeki|elle`), `eksikler_json`, `uyumsuzluk_json` (CRM fiyatı ≠ Logo fiyatı vb.), `durum` (`taslak|onayda|onayli`), `onaylayan`, `onay_zamani`, `pdf_yolu`, `crm_hash` (CRM alanları değişince föy «eski» olur).
- `semantic_mkt_foy_sends`: `id`, `donem`, `alicilar`, `gonderen`, `zaman`, `dosya`, `sonuc` (`sent|no_smtp|failed`).

**Uçlar** (`/api/v1/marketing/…`)
- `GET months/{YYYY-MM}` (takvim + bütçe + föy özeti + önceki ay), `POST months/{YYYY-MM}/build` (taslağı yeniden kur; elle düzeltilenler korunur).
- `GET months/{YYYY-MM}/conflicts`, `PUT months/{YYYY-MM}/budget`, `POST months/{YYYY-MM}/suggest` (Zeki AI gerekçe).
- `POST months/{YYYY-MM}/submit|approve|reject|revise` (çekirdeğin onay akışı).
- `GET months/{YYYY-MM}/summary.pdf` (ay özeti).
- `GET foy?donem=&durum=`, `GET|PUT foy/{stok_kodu}`, `POST foy/{stok_kodu}/draft-args` (Zeki AI), `POST foy/{stok_kodu}/approve`, `GET foy/{stok_kodu}.pdf`, `GET foy/paket/{YYYY-MM}.pdf`, `GET foy/paket/{YYYY-MM}.zip`, `POST foy/paket/{YYYY-MM}/send`.
- `GET contract/month/{YYYY-MM}` (M22/M24/M30/M32 okur: onaylı takvim + föy bağlantıları).
- `POST months/run-due` (SYSTEM).

**Ekranlar**: `src/canvas/marketing/monthly/` — `MonthScreen.tsx` (ay seçici; `CalendarGrid.tsx` hafta × kanal; `BudgetPanel.tsx`; `FoyList.tsx`; önceki ay şeridi), `FoyScreen.tsx` (önizleme + alanlar; telefonda önizleme önce, «Paylaş» `navigator.share` + PDF). Rotalar `/pazarlama/aylik-plan`, `/pazarlama/aylik-plan/:ay`, `/pazarlama/foy`, `/pazarlama/foy/:stok`. Menü (alan `pazarlama`, bölüm «Planlama»): `{ id: 'pazarlama-aylik', label: 'Aylık plan', to: '/pazarlama/aylik-plan', section: 'Planlama' }` (bölümün ilk öğesi) ve `{ id: 'pazarlama-foy', label: 'Satış föyleri', to: '/pazarlama/foy', section: 'Planlama', keywords: ['föy', 'tanıtım', 'satış'] }`. Saha kullanıcısının rolünde yalnız `sayfa:pazarlama-foy` olur; telefon alt menüsünde görünür. Kampüs: `LIVE.M18 = '/pazarlama/aylik-plan'`, `GROUP_HOME['Pazarlama'].to = '/pazarlama/aylik-plan'`.

**Yetki**: sayfalar `sayfa:pazarlama-aylik`, `sayfa:pazarlama-foy`; özellikler `ozellik:pazarlama.foy-yaz`, `ozellik:pazarlama.foy-onay` (explicit), `ozellik:pazarlama.foy-gonder` (explicit) + M15'teki `plan-yaz`, `plan-onay`, `butce-gor`. `access.RULES`: `/api/v1/marketing/foy` → `{page("pazarlama-foy"), page("pazarlama-aylik")}`; `/api/v1/marketing/months` → `page("pazarlama-aylik")`; `run-due` → SYSTEM. M46 `targets`/`deviations` satırlarına `page("pazarlama-aylik")`. Föy PDF indirme `ozellik:veri.disa-aktar` gerektirmez (saha temsilcisinin asıl işi) — bu istisna yetki kataloğunda not edilir.

**Zamanlayıcı**: `timas-marketing-monthly.timer` — her gün 06:30 `POST /api/v1/marketing/months/run-due`: ayın 15'inde gelecek ay taslağı; her gün föylerin CRM karmasını (`crm_hash`) denetleyip değişen föyü «eski» işaretleme; 20'sinde eksik föy hatırlatması; ay sonu + 3 iş günü özet. İlk kurulumda elle koşturulur.

**Kabul testleri** (test sunucusu, gerçek CRM .28 + Logo .155)
1. **Ayın yeni kitapları**: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitap k WHERE k.statecode = 0 AND k.new_Tip = 1 AND k.new_ilkyayintarihi >= DATEADD(hour, -3, '<ay başı>') AND k.new_ilkyayintarihi < DATEADD(hour, -3, '<sonraki ay başı>')` (UTC saklama; `crm_yeni_kitap.sql` notu) = takvimdeki «yeni kitap» kartı sayısı = föy listesi satır sayısı.
2. **Aylık hedef payı**: `GET /api/v1/budget/targets?year=Y&segment=yeni` ve `segment=backlist` → `Σ items[].aylik[ay].ciro` iki segment için = bütçe panelindeki «hedef payı» (kuruşu kuruşuna; M46 aylık toplam = yıllık kuralıyla).
3. **Önceki ay gerçekleşen**: `budget_sources.sales_sql(firma, yıl)` sonucunda `ay = önceki ay` satırlarının net ciro toplamı (157 hariç) = özet şeridindeki gerçekleşen; veri sonu `data_end_sql` ile aynı.
4. **FÖY alanları**: 5 kitapta `SELECT new_ean13, new_kdvdahilfiyat, new_TantmFyMetni, new_kitapspotu, new_hedefkitle FROM Timas_MSCRM.dbo.new_kitapBase WHERE new_StokKodu = '<kod>'` = föy JSON'undaki değerler; Logo `logo_fiyat.sql` fiyatı ≠ CRM fiyatı olan kitapta `uyumsuzluk_json` dolu.
5. **CRM B2B kampanyaları**: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kampanyaBase WHERE statecode = 0 AND new_baslangictarihi < '<sonraki ay başı>' AND new_bitistarihi >= '<ay başı>'` = takvimdeki B2B kampanya kartı sayısı.
6. **Çakışma**: aynı kitaplıkta aynı haftaya iki yeni kitap kartı düşen sentetik olmayan bir ayda `conflicts` bu çifti döndürür; biri kaydırılınca kalkar.
7. **Paket**: `foy/paket/{ay}.pdf` sayfa sayısı = onaylı föy sayısı; zip dosya sayısı aynı; gönderimde `semantic_mkt_foy_sends` satırı ve `semantic_audit` kaydı; SMTP yoksa `no_smtp`.
8. **Telefon**: föy ekranı 360 px genişlikte yatay kaydırmasız; teknoloji adı 0.

**Bağımlılık**: M46 hazır. Ay takvimi M15 ve M17 çıktısıyla zenginleşir ama CRM'den tek başına kurulabilir (onlar yokken «yalnız CRM yayın tarihleri»). FÖY M15'ten bağımsız, ilk olarak kodlanabilir. M22/M30/M32 sonra bağlanır.

**Tahmini büyüklük**: L (ay planı M + FÖY/PDF M; toplam 3 gün).
