# H3 — E-Ticaret Müşteri Yönetimi Entegrasyonu: kullanıcı ihtiyaç analizi

Durum: ilk sürüm kodlandı (dalda, test sunucusunda doğrulanmadı — günlük 2026-09-28) · Tarih: 2026-09-28 · Modül kimliği `commerce-integration` (`src/canvas/modules.json`,
«Hazırlıklar» grubu)

Kaynaklar: iş tanımı `specs/E_Ticaret_Müşteri_Yönetimi_Ent.txt`, `ZEKİ_Veri_Haritasi2.html` (M34/M35/M42 girdileri),
`specs/M34.txt`, `M35.txt`, `M38.txt`, `M42.txt`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`,
`docs/analiz/seo-geo-modul-2026-09-25.md` (T-soft okuması, Search Console denetimi), `docs/analiz/yetki-mekanizmasi-
2026-09-27.md`, `configs/semantic/knowledge/crm/` (CRM metadata, 2026-09-09), `configs/semantic/knowledge/logo/knowledge/
metrics/logo-timas.md`, `backend/semantic_bridge/seo_geo/connections.py`, `seo_geo/tech.py`, `seo_geo/cannibal.py`,
`backend/semantic_bridge/budget_sources.py`, `access.py`, H2 analizi (`H2-okuyucu-veri-tabani.md`), PROJECT-MEMORY.md,
kullanıcı belleği (tsoft-no-write, crm-tsoft-no-push-integration, seo-geo-module, system-of-record-logo,
sales-are-invoiced-lines, no-tech-names-on-screens).

Sunucuya bağlanılmadı. Sayılar önceden ölçülmüş değerlerdir; «ölçülecek» olanlar bilinmiyor; kanıtsız iddialar
«varsayım».

---

## 1. Modül ne işe yarar

timas.com.tr'nin (T-soft) müşterilerini davranış ve satın almaya göre segmentler (RFM + davranış), her segment için
ürün önerisi ve kampanya tetikleri (terk sepeti, yeni kitap, geri kazanım) hazırlar, sonuçlarını ölçer. İş tanımı
gerçek zamanlı kişiselleştirme (ana sayfa, ürün, sepet) ve otomatik kampanya (K1) öngörüyor; hedef %15 dönüşüm artışı,
%25'in altında sepet terki.

Bugünkü durum iş tanımındaki «✓ HAZIR» işaretlerinden farklı: (1) T-soft dönemi site siparişleri CRM'e gelmiyor —
müşteri ve sipariş verisinin kaynağı CRM değil T-soft'tur; (2) bizim web davranış verisine erişimimiz yok (GA4 erişimi
yok, oturum düzeyi akış yok); (3) T-soft'a yazmak yasak, dolayısıyla siteye kişiselleştirme ya da tetik gönderemeyiz;
(4) sitede zaten bir öneri kutusu çalışıyor olabilir (iç bağlantılarda `seux` parametresi — hangi araç olduğu
bilinmiyor). Modülün ilk gerçek değeri: T-soft siparişlerinden güvenilir müşteri tablosu, RFM segmentleri, tetik
listeleri ve kontrol gruplu sonuç ölçümü; siteye müdahale değil.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| E-ticaret müdürü / uzmanı | Pazarlama ya da ayrı e-ticaret birimi (varsayım; T-soft panelini yöneten kişi sorulacak) | Her gün | Sabah özeti telefonda, iş masaüstünde |
| Dijital pazarlama / performans uzmanı | Pazarlama (ekip 35 kişi, 2026-09-15) — varsayım | Her gün | Masaüstü |
| CRM / e-posta pazarlama uzmanı | Pazarlama (H2'nin kullanıcısıyla aynı kişi olabilir) | Haftalık | Masaüstü |
| Müşteri hizmetleri | Varsayım: sipariş/iade sorularına bakan birim (M51) | Günlük (müşteri kartı) | Masaüstü |
| Yönetim | Genel müdürlük | Haftalık/aylık KPI | Telefon |
| Dış ajans / T-soft tema sorumlusu | Portal kullanıcısı değil; öneri listesi onlara iletilir | — | — |

## 3. Bugün bu iş nasıl yapılıyor

**E-ticaret uzmanı (kanıt kısmi):**
- Sipariş ve ürün: T-soft paneli. T-soft API'sinden 62.903 sipariş okunabildi (kişisel veri içeriyor, okunmadı),
  ürünlerde toplam satış (`CountTotalSales`, 5.683 ürün) ve görüntülenme (`StatViews`) alanları var (2026-09-25).
- Arama performansı: portalın SEO & GEO modülü (Search Console: 3 ayda 245 B tıklama, 9,73 Mn gösterim; 2026-09-26).
- Web analitik: GA4 erişimi yok (zeki@ hesabı; bellek `seo-geo-module`). Oturum, sepet, ödeme hunisi verisini kimin nerede
  izlediği sorulacak.
- Öneri kutusu: sitede iç bağlantılara `utm_source=seux-smart…` ekleyen bir öneri bileşeni var (12.807 parametreli kopya
  sayfa; SEO denetimi). Bu bir üçüncü taraf kişiselleştirme aracı olabilir (varsayım).
- Terk sepeti / yeni kitap e-postası: var mı, hangi araçla gidiyor bilinmiyor (sorulacak).

**CRM tarafı (kanıt):** T-soft siparişleri CRM'e düşmüyor (son 12 ayda B2C numaralı CRM siparişi 0). CRM'deki B2C
kalıntıları (2018–2021 Omerd sitesi, 23.680 sipariş) eski. Pazaryerleri CRM'de toptan cari. CRM'de İYS entegrasyonu ve
küçük bir e-posta/SMS kampanya kaydı var (28 kampanya) — H2.

**Logo (kanıt, genel):** Gerçekleşmiş satış Logo'da faturalı satırdır; kanal kırılımı cari özel kodu (`SPECODE2`)
üzerinden (`kanal_net_ciro`, `v_channel_net`). T-soft siparişlerinin Logo'da kişi başına mı yoksa toplu bir e-ticaret
carisine mi faturalandığı ölçülecek. Logo kopyası (.155) 2026-08-17'de donmuş.

**Tıkanma (varsayım):** müşteri ve sipariş verisi yalnız T-soft panelinde; segment ve kampanya sonucunu ölçmek için
Excel'e dökülüyor; kampanyanın gerçekten satış getirip getirmediği kontrol grubu olmadan bilinmiyor.

## 4. İhtiyaçlar ve acı noktaları

**E-ticaret müdürü**
1. Sabah tek bakışta: dünkü sipariş, ciro, ortalama sepet (AOV), yeni/tekrar eden müşteri, en çok satanlar; Logo
   kanal cirosuyla uzlaşma.
2. RFM segmentleri (ilk alıcı, aktif, sadık, kayıp) ve segment geçişleri.
3. Kampanya sonucunun kontrol grubuna göre ölçülmesi (gerçek artış).
4. «Görüntülenen ama satmayan» kitaplar (görüntülenme ↔ satış).

**Dijital pazarlama uzmanı**
1. Tetik listeleri: yeni kitap çıktığında ilgi alanı eşleşen müşteriler; 90+ gün hareketsizler; (veri varsa) terk sepeti.
2. Kupon/kampanya kodu kullanımının siparişe bağlanması.
3. UTM kaynağına göre müşteri kazanımı.

**CRM / e-posta uzmanı**
1. Tetik listesinin H2'deki izin denetiminden geçmesi; tek tık dışa aktarım.
2. Kişiselleştirilmiş içerik taslağı (segmente göre kitap listesi ve metin).

**Müşteri hizmetleri**
1. Müşteri kartı: sipariş geçmişi, iadeler, iade gerekçesi (T-soft'ta varsa).

**Yönetim**
1. LTV, tekrar satın alma oranı, kanal payı (site vs pazaryeri vs bayi — Logo).

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- E-ticaret müdürü olarak dünkü site cirosunu Logo'daki e-ticaret kanalı cirosuyla yan yana görmek istiyorum, çünkü
  yönetime tek rakam götürmeliyim.
- E-ticaret müdürü olarak sadık müşteri segmentinin bu ay kaç kişi kaybettiğini görmek istiyorum, çünkü geri kazanım
  bütçesini ona göre ayırıyorum.
- Dijital pazarlama uzmanı olarak yeni çıkan kitabın ilgi alanına uyan ve izni olan müşteri listesini almak istiyorum,
  çünkü lansman e-postasını hedefli göndermek istiyorum.
- Dijital pazarlama uzmanı olarak kampanya listesinin bir kısmını kontrol grubu olarak ayırmak istiyorum, çünkü gerçek
  etkiyi ölçmem gerekiyor.
- CRM uzmanı olarak Zeki'nin segment için kitap önerisini ve gerekçesini görmek istiyorum, çünkü kişiselleştirilmiş
  bülteni ben onaylıyorum.
- Müşteri hizmetleri olarak bir müşterinin bütün siparişlerini ve iadelerini tek kartta görmek istiyorum.
- Yönetici olarak haftalık e-ticaret özetini telefonda almak istiyorum.

### Ana ekranlar ve akış
1. **Özet (ilk açılış):** dün/bu hafta/bu ay sipariş, ciro, AOV, yeni vs tekrar müşteri; Logo e-ticaret kanalı cirosu
   ve fark; en çok satan 10; veri tazeliği.
2. **Müşteriler (RFM):** segment matrisi (yenilik × sıklık), segment büyüklüğü ve geçişleri; tıklayınca liste (maskeli).
3. **Tetikler:** yeni kitap, geri kazanım, (veri varsa) terk sepeti; kural, bugünkü aday sayısı, izinli sayı, onay,
   dışa aktarım (kontrol grubu ayrılmış).
4. **Kampanya sonuçları:** kampanya → hedef/kontrol grubu → sipariş, ciro, artış; güven aralığı.
5. **Ürün hunisi:** görüntülenme (T-soft `StatViews`), satış, oran; satmayan çok görüntülenen kitaplar.
6. **Müşteri kartı:** sipariş geçmişi, iadeler, segment, izin (H2'den).

En sık üç işlem:
- Sabah özeti: menü (1). Telefon uyumlu.
- Yeni kitap tetiği: Tetikler (1) → kitap seç (2) → önizleme (3) → onay (4) → dışa aktar (5).
- Kampanya sonucu: Kampanyalar (1) → kampanya (2).

### Zeki AI'ya soracakları örnek sorular
- «Dün sitede kaç sipariş geldi, geçen haftanın aynı gününe göre ne değişti?»
- «Son 90 günde ilk kez alışveriş yapıp ikinci siparişi vermeyen kaç müşteri var?»
- «Sadık müşteri segmentinde en çok alınan 5 kategori hangisi?»
- «Eylül bülteni kampanyasının kontrol grubuna göre ek cirosu ne oldu?»
- «En çok görüntülenip en az satan 20 kitap hangisi?»
- «Site cirosu ile Logo'daki e-ticaret kanalı faturası bu ay ne kadar farklı, neden?»
- «Yeni çıkan kitabın ilgi alanına uyan, e-posta izni olan kaç müşterimiz var?»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| T-soft sipariş/ürün okuması, kişisel alanların ayıklanması, müşteri anahtarı | K1 | Gece (sonraki sürüm: saatlik) |
| RFM puanı ve segment ataması | K1 | Kural deterministik, eşikler ekrandan |
| Tetik aday listesi (yeni kitap, geri kazanım) | K1 hesap / K2 gönderim kararı | Liste otomatik, gönderim insan onayıyla |
| Segment başına kitap önerisi ve metin taslağı | K2 | Zeki önerir, uzman onaylar |
| Kampanya sonuç analizi | K3 | Zeki hesaplar/yorumlar, ekip karar verir |
| Siteye kişiselleştirme | — | Kapsam dışı (T-soft'a yazma yasak); öneri listesi ajansa/tema sorumlusuna iletilir (K4) |
| Otomatik e-posta/SMS/push gönderimi | — | İlk sürümde yok; gönderim aracı ve hukuki teyit sonrası ayrı karar |

### Bildirim/uyarı
- Günlük sabah özeti (07:30) → e-ticaret müdürü ve yönetim, e-posta + Kampüs kartı (mevcut Planlı raporlar/SMTP
  altyapısı).
- Sipariş sayısı önceki 4 haftanın aynı gününe göre belirgin düştü (eşik ayar) → e-ticaret müdürü (mevcut Uyarılar
  motoru kural olarak).
- T-soft okuması başarısız / 24 saatten eski → portal yöneticisi.
- Tetik listesi onay bekliyor → onay yetkilisi.

### Onay ve yetki (öneri)
| İşlem | Kim | Anahtar |
|---|---|---|
| Sayfa (toplu sayılar, maskeli liste) | E-ticaret, pazarlama, yönetim | `sayfa:eticaret-musteri` |
| Kişisel veriyi açık görmek | E-ticaret uzmanı, müşteri hizmetleri | `ozellik:okur.kisisel-veri` (H2 ile ortak; açıkça) |
| Tetik kuralı yazmak | Dijital pazarlama | `ozellik:eticaret.tetik` |
| Tetik listesini onaylamak | E-ticaret müdürü | `ozellik:eticaret.liste-onay` (açıkça; yazan onaylayamaz) |
| Listeyi dışa aktarmak | CRM uzmanı | `ozellik:okur.liste-aktar` (H2 ile ortak; açıkça) |
| RFM eşiklerini değiştirmek | E-ticaret müdürü | `ozellik:eticaret.ayar` |

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Sipariş (no, tarih, tutar, durum, ödeme, kargo, kupon, UTM) | T-soft `order/get` | 62.903 sipariş okundu (2026-09-25); kişisel alanlar okunmadı | Alan listesi, iade/iptal durumları, kupon ve UTM alanları ölçülecek |
| Sipariş satırı (ürün, adet, tutar) | T-soft sipariş detayı | Ölçülecek | Barkod = ISBN = CRM `new_ean13` (SEO modülünde 5.466/5.656 eşleşti) |
| Müşteri kimliği / üyelik | T-soft üye yöntemi | Ölçülecek (yöntem kataloğu girişsiz: `ConsoleHelper/getApiDetails`) | Üye sayısı, izin alanları, misafir sipariş oranı |
| Sepet / terk sepeti | T-soft API'de sepet yöntemi var mı | Ölçülecek | Yoksa terk sepeti tetiği yapılamaz |
| Web davranışı (oturum, sayfa, arama, huni) | GA4 ya da sitedeki başka araç | Erişim yok (GA4 yetkisi yok) | Sahibinden okuma yetkisi; oturum ↔ üye eşlemesi (iş tanımındaki zorunlu eşleme) ancak site tarafında etiketle olur — tema işi, bizim değil |
| Ürün görüntülenme | T-soft ürün `StatViews` | Okunabiliyor | Dönemsel değil toplam olabilir (ölçülecek); günlük fark alınarak dönemselleştirilir |
| Arama sorguları (site içi) | T-soft / analitik | Ölçülecek | Site içi arama kaydı erişimi yok |
| Google arama performansı | Search Console (SEO modülü) | Var (zeki@ okur) | — |
| İletişim izni | H2 izin özeti (CRM İYS + T-soft üye izni) | H2'ye bağlı | T-soft izinlerinin İYS ile ilişkisi sorulacak |
| Kampanya etkileşimi (açılma/tıklama) | Bülten/SMS platformu | Bilinmiyor | Platform ve dışa aktarım biçimi sorulacak |
| Kupon | T-soft kupon/kampanya yöntemi; CRM `new_kuponkodlariBase` (50.000, dönemi bilinmiyor) | Ölçülecek | — |
| Gerçekleşmiş satış (finansal) | Logo `LG_<firma>_01_STLINE` faturalı satır; `LG_<firma>_CLCARD.SPECODE2` kanal; `v_channel_net` | Ölçüler sertifikalı | E-ticaret carisinin kodu ve kişi başı/toplu faturalama ölçülecek; .155 kopyası 2026-08-17'de donmuş |
| İlgi alanı | H1 kategori ağacı (ürün → düğüm) | H1'e bağlı | — |
| Pazaryeri müşterisi | Trendyol/Hepsiburada/Amazon | Entegrasyon yok; CRM'de toptan cari | Kapsam dışı (M34/M40–M42) |

## 7. Diğer modüllerle bağ

- **Girdi alır:** H2 (tekil okur, izin, segment motoru), H1 (ilgi alanı = kategori ağacı), SEO & GEO modülü (T-soft
  ürün eşitlemesi, Search Console), Logo (kanal cirosu), M46 bütçe hedefleri (e-ticaret kanal hedefi, varsa).
- **Çıktı verir:** M35 e-ticaret kampanya ve promosyon (segment + tetik + sonuç), M24 bülten (segment bazlı kitap
  önerisi), M42 D2C yönetimi (site müşteri LTV'si), M38 CRM analitiği (CLV, kayıp riski), M51 müşteri hizmetleri
  (müşteri kartı), M18 aylık pazarlama planı (segment büyüklükleri), M10/M11 (site talep sinyali: görüntülenme).

## 8. Kısıtlar

- **T-soft'a yazma yasak:** tetik, kupon, kişiselleştirme, ürün sırası T-soft'a gönderilmez. Siteye kişiselleştirme
  bu modülün kapsamı dışında; öneri listesi ajansa/tema sorumlusuna iletilir.
- **CRM'e yazma yok:** müşteri ve segment portalın tablolarında.
- **Portal mesaj göndermez** (ilk sürüm): liste dışa aktarılır; gönderim mevcut araçla. Otomatik gönderim ayrı karar
  (izin denetimi, hukuk teyidi, gönderim platformu).
- **Kişisel veri:** T-soft siparişi ad, adres, telefon, e-posta içerir. Seo analizindeki karar: «kişisel alanları atan
  toplama katmanı olmadan kullanılmaz». Okuma katmanı kişisel alanları diske yazmadan ayıklar; müşteri anahtarı tuzlu
  özet (hash) olur; ad/e-posta yalnız yetkili ekranda ve dışa aktarım anında kaynaktan okunur.
- **KVKK / İYS:** profilleme (RFM, ilgi alanı) ve kişiselleştirme için açık rıza; ticari ileti öncesi İYS; ret kazanır.
  Kontrol grubu ayrılması hukuki değil yöntem gereğidir.
- **Müşteride web taraması kapalı:** rakip site fiyat/öneri taraması yapılmaz.
- **Ekranda teknoloji adı yok** («Zeki AI»); T-soft ve Search Console müşteri platformu adı olarak kalabilir.
- **Rakam kaynağı:** site cirosu T-soft'tan, finansal ciro Logo'dan; ikisi farklı kavramdır ve ekranda ayrı etiketlenir
  (kayıt sistemi Logo).
- **Demo veri yok, sayı tavanı yok.**

## 9. Kapsam önerisi

**İlk sürüm**
- T-soft sipariş (+ satır) okuması, kişisel alanların ayıklanması, müşteri anahtarı; günlük özet ve Logo kanal
  uzlaşması.
- RFM segmentleri (iş tanımındaki dört segment: ilk ziyaretçi yerine «ilk alıcı», aktif ≤ 90 gün, sadık/VIP, kayıp
  90+ gün; eşikler ekrandan).
- Tetik: yeni kitap (ilgi alanı eşleşmesi) ve geri kazanım listeleri; kontrol grubu; onay; H2 izin denetimli dışa aktarım.
- Kampanya sonuç ölçümü (hedef vs kontrol, sipariş ve ciro).
- Ürün görüntülenme ↔ satış tablosu.
- Müşteri kartı (maskeli; yetkiliye açık).

**Sonraki sürüm**
- Terk sepeti (T-soft sepet verisi varsa).
- Segment bazlı kitap önerisi + bülten metni taslağı (M24 ile).
- Web analitik bağlantısı (erişim verilirse): huni, arama sorguları.
- LTV ve kayıp riski modeli (M38).
- Otomatik gönderim (karar ve hukuk sonrası).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/connections.py` — T-soft yalnız okuma istemcisi (`READ_ONLY` deseni; yeni yöntemler
  yalnız `get*` olabilir).
- `backend/semantic_bridge/seo_geo/store.py` — eşitlenmiş ürün (barkod, kategori, görüntülenme).
- `backend/semantic_bridge/budget_sources.py` — Logo yıl→firma, faturalı satır, net ciro tanımı.
- `backend/semantic_bridge/reports.py` + `alerts.py` — sabah özeti e-postası ve eşik uyarısı (yeni kural = soru).
- H2 `readers.py` — izin, segment motoru, dışa aktarım, denetim.
- `backend/semantic_bridge/board.py` — kişisel pano kartı olarak e-ticaret özeti.

## 10. Uzmanlara sorulacak sorular

1. Site analitiği nerede tutuluyor (GA4, T-soft istatistikleri, başka araç) ve bize okuma yetkisi verilebilir mi?
2. Sitedeki öneri kutusu (iç bağlantılarda `seux` parametresi) hangi araç; terk sepeti/yeni kitap e-postaları bugün
   gidiyor mu, hangi araçla?
3. T-soft siparişleri Logo'ya nasıl faturalanıyor: kişi başı cari mi, toplu e-ticaret carisi mi; hangi cari kodu?
4. T-soft üyelerinin e-posta/SMS izinleri İYS'ye kim tarafından bildiriliyor; kaynak kayıt hangisi?
5. Kampanya başarısı bugün nasıl ölçülüyor; kontrol grubu ayırmaya itiraz var mı?

## 11. Başarı ölçütü

- Veri doğruluğu: portal sipariş sayısı = T-soft sipariş sayısı (aynı gün aralığı); Logo kanal farkı açıklanmış.
- Kampanya: kontrol grubuna göre ölçülen ek ciro; iş tanımı hedefi olan %15 dönüşüm artışı ancak oturum verisi gelince
  ölçülebilir (bugün ölçülemez — açıkça yazılır).
- Tekrar satın alma oranı ve kayıp segmentinden geri dönüş oranı (aylık).
- Tetik listesinden dışa aktarıma süre (hedef aynı gün).
- İzin ihlali sıfır.
- Kullanım: sabah özetinin açılma oranı, haftalık aktif kullanıcı.

---

## 12. Uzman gözüyle en iyi sistem

Bakış açısı: 15 yıllık e-ticaret müdürü (kitap ve perakende sitelerinde müşteri yaşam döngüsü ve kampanya yönetmiş).

**Sektörde iyi örnekler.** Büyük çevrim içi kitapçılar üç şeyi iyi yapar: (1) satın alma geçmişinden «bunu alanlar
şunu da aldı» ve yazar/seri takibi; (2) yaşam döngüsü tetikleri (ilk siparişten sonra ikinci sipariş teşviki, seri
devamı çıkınca bildirim, uzun süre gelmeyene geri kazanım); (3) her kampanyada kontrol grubu ile gerçek artış ölçümü.
Türkiye'de siteler çoğunlukla hazır kişiselleştirme ve pazarlama otomasyon platformları kullanır; bu platformların
başarısı tekil müşteri kimliğine ve izin verisine bağlıdır. İyi ekipler «kaç e-posta gitti» değil «kaç ek sipariş
geldi» diye bakar.

**TİMAŞ için mükemmel sistem.** T-soft siparişlerinden kişisel veri kopyalamadan kurulan müşteri tablosu; H2 ile tek
kimlik ve izin; RFM ve ilgi alanı segmentleri; her yeni kitap için «ilgilenecek müşteri» listesi; her kampanyada
otomatik kontrol grubu ve sonuç; site cirosunun Logo'daki faturayla her gün uzlaştırılması. Siteye müdahale gerekirse
öneriler (hangi segment için hangi kitap) ajansın ya da mevcut kişiselleştirme aracının kullanacağı dosya olarak hazır.

**Bir iş günü (e-ticaret müdürü):**
- 07:30 Telefonda sabah özeti: dünkü sipariş, ciro, AOV, yeni müşteri; Logo farkı; bir uyarı: «pazar günü siparişi
  önceki dört pazarın altında».
- 09:00 Masaüstü: RFM matrisinde sadık segmentten kayba geçenler; Zeki AI'ya «bu kişilerin son aldığı kategoriler» diye
  sorar.
- 10:00 Yeni çıkan kitabın tetiği: ilgi alanı eşleşen izinli müşteri sayısı; %10 kontrol grubu; onaya gönderir.
- 11:00 Geçen haftaki bülten sonucu: hedef grupta sipariş oranı kontrol grubuna göre ne kadar yüksek; ek ciro.
- 14:00 Ürün hunisi: çok görüntülenen az satan kitaplar; SEO modülüyle birlikte ürün sayfası önerisine gider.
- 16:00 Ajansa iletilecek «segment → önerilen kitaplar» dosyasını onaylar.
- 17:30 Haftalık KPI kartını yönetime iletir (pano).

**«Bunu görürsem hemen kullanırım»**
1. Kontrol gruplu kampanya sonucu: «bu kampanya X ek sipariş getirdi».
2. Yeni kitap için «ilgilenecek ve izni olan müşteri sayısı» tek tıkta.
3. Site cirosu ile Logo faturası uzlaşması, farkın açıklamasıyla.

**«Bunu yaparsanız kullanmam»**
1. Kontrol grubu olmadan «ROI» ya da «dönüşüm artışı» gösteren rakamlar.
2. İzin denetimsiz liste ya da siteye/müşteriye otomatik gönderim.
3. «Gerçek zamanlı» deyip bir gün gecikmeli veri göstermek; tazelik ekranda yazmalı.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Sipariş ve müşteri tablosu | — | — (T-soft kaynak) | — | Okuma + ayıklama deterministik |
| Günlük özet ve uzlaşma | `STLINE` faturalı satır (TRCODE 7/8/9 satış, 2/3 iade, `INVOICEREF <> 0`, `LINETYPE = 0`, `CANCELLED = 0`), `CLCARD.SPECODE2` e-ticaret kanalı; ölçü `kanal_net_ciro` | — | Farkın yorum cümlesi (rakamlar SQL'den) | Kayıt sistemi Logo; model rakam üretmez |
| RFM ve segment | — | — | — | Kural |
| İlgi alanı | — | `new_kitapBase` (barkod → kitap) + H1 düğümü | — (H1 hazır düğüm verir) | Deterministik |
| Yeni kitap tetiği | — | yeni kitap kartı (`CreatedOn`, `new_ean13`) | Kitabın düğümü H1'de yoksa kapalı küme seçim | Kapalı küme |
| Segment başına kitap önerisi | Son 90 gün satış (Logo) ya da site satışı (T-soft) | — | Aday kitaplar SQL'den (segmentin aldığı düğümlerde çok satan, henüz almadığı); model sıralama gerekçesi ve kısa tanıtım metni taslağı | Rakam/aday SQL, metin model |
| Kampanya sonucu | Logo kanal cirosu (bağlam) | — | Sonuç özeti ve öneri cümlesi | Yorum |
| Arama sorgusu → niyet | — | — | Search Console sorgusunu H1 düğümüne eşleme (kapalı küme) — sonraki sürüm | Sınıflandırma |
| Doğal dil soru | Katalog ölçüleri | Portal tabloları (sipariş özeti, segment) katalogda tanımlanır | Mevcut soru hattı | Var olan hat |

Model çağrıları `rt.llm_for("commerce")` / `rt.llm_for("commerce", BATCH)`; kapalı küme `QueuedLlm.choose()` (H1'de).
Model çağrısına kişisel veri gitmez.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/commerce.py` — depo, RFM, tetikler, kampanya sonucu.
- `backend/semantic_bridge/commerce_sources.py` — T-soft okuma (`seo_geo/connections.py` istemcisi; yalnız `get*`),
  kişisel alan ayıklama, müşteri anahtarı; Logo kanal cirosu (`budget_sources.py` yardımcıları).
- `backend/semantic_bridge/commerce_api.py` — `register(app, rt, require_caller, can)`.
- Segment, izin ve dışa aktarım H2 `readers.py`'den çağrılır (yeniden yazılmaz; `domain='eticaret'`).

**Tablolar (bi_meta; `tenant_id`)**
- `semantic_commerce_orders` — `order_no`, `ordered_at`, `status`, `total`, `discount`, `shipping`, `coupon`,
  `utm_source`, `utm_campaign`, `customer_key` (tuzlu hash), `is_guest`, `synced_at`. Kişisel alan yok.
- `semantic_commerce_order_lines` — `order_no`, `barcode`, `book_id` (CRM eşleşmesi), `qty`, `amount`.
- `semantic_commerce_customers` — `customer_key`, `reader_id` (H2), `first_order`, `last_order`, `orders`, `revenue`,
  `r_score`, `f_score`, `m_score`, `segment`, `segment_since`.
- `semantic_commerce_segment_moves` — `customer_key`, `from`, `to`, `at` (geçiş raporu).
- `semantic_commerce_product_stats` — `barcode`, `date`, `views_total`, `views_delta`, `orders`, `qty`.
- `semantic_commerce_triggers` — `id`, `kind` (yeni-kitap|geri-kazanim|terk-sepeti), `params_json`, `status`, `owner`.
- `semantic_commerce_trigger_runs` — `id`, `trigger_id`, `at`, `candidates`, `consented`, `control_share`,
  `approved_by`, `export_id` (H2 `semantic_reader_exports`).
- `semantic_commerce_campaigns` — `id`, `name`, `trigger_run_id`, `start`, `end`, `target_keys_ref`,
  `control_keys_ref` (anahtar listeleri; kişisel veri değil), `result_json`.
- `semantic_commerce_settings` — RFM eşikleri, kontrol grubu payı, kayıp günü.

**Uçlar (`/api/v1/commerce/*`)**
- `GET overview?period=` (T-soft özeti + Logo kanal cirosu + fark).
- `GET customers/rfm` · `GET customers/moves` · `GET customers?segment=` (maskeli) · `GET customers/{key}`.
- `GET products/funnel`.
- `GET triggers` · `POST triggers` · `PATCH triggers/{id}` · `POST triggers/{id}/preview` · `POST triggers/{id}/run`
  · `POST runs/{id}/approve` · `POST runs/{id}/export` (H2 dışa aktarım + kontrol grubu).
- `GET campaigns` · `GET campaigns/{id}/result`.
- `GET settings` · `PUT settings`.
- `POST run-due` (SİSTEM).
- Sözleşme uçları: `GET segments/summary` (M35, M42, M18 okur).

**Ekranlar** `src/canvas/commerce/`: `CommerceHome.tsx` (özet; telefon öncelikli), `RfmMatrix.tsx`, `Triggers.tsx`,
`Campaigns.tsx`, `Funnel.tsx`, `CustomerCard.tsx`, `api.ts`. Rota `/timas/eticaret-musteri` (+ `/eticaret-musteri/
tetikler`, `/kampanyalar`, `/musteri/:key`). Menü: «Pazarlama» → bölüm `Okur ve müşteri` (H2 ile aynı bölüm), öğe
`{ id: 'eticaret-musteri', label: 'E-ticaret müşterileri', to: '/eticaret-musteri', hint: 'Site siparişleri, müşteri
segmentleri, tetikler ve kampanya sonucu' }`. Kampüs: modül kutusu; sabah özeti kişisel pano kartı olarak.

**Yetki**
- `sayfa:eticaret-musteri`; `RULES`: `("/api/v1/commerce/run-due", SYSTEM)`, `("/api/v1/commerce/",
  frozenset({page("eticaret-musteri")}))`; `segments/summary` M35/M42 sayfalarına da açılır.
- Özellik: `ozellik:eticaret.tetik`, `ozellik:eticaret.ayar` (`FEATURE_RULES`); açıkça verilen:
  `ozellik:eticaret.liste-onay`; H2'den `ozellik:okur.kisisel-veri`, `ozellik:okur.liste-aktar`.

**Zamanlayıcı** `scripts/server/timas-commerce.{service,timer}` — her gece 02:50: T-soft siparişleri (son 7 günde
değişenler + yeni), satırlar, ürün görüntülenme farkı, RFM yeniden hesap, segment geçişleri; sabah 07:15 özet kartı
(Planlı raporlar üzerinden 07:30 e-posta). Pazar gecesi tam sipariş turu. Kampanya bitişinden 14 gün sonra sonuç
hesabı.

**Kabul testleri**
1. Sipariş sayısı: T-soft `order/get` ile bir gün aralığındaki toplam kayıt = `SELECT COUNT(*) FROM
   semantic_commerce_orders WHERE ordered_at >= :d1 AND ordered_at < :d2` (API sayfalaması sonuna kadar okunur; tavan
   yok).
2. Logo e-ticaret kanalı net ciro (ay): `SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET ELSE -s.LINENET END)
   FROM LG_411_01_STLINE s JOIN LG_411_CLCARD c ON c.LOGICALREF = s.CLIENTREF WHERE s.CANCELLED = 0 AND s.LINETYPE = 0
   AND s.INVOICEREF <> 0 AND s.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = :eticaret_kodu AND s.DATE_ >= :ay_bas AND s.DATE_ <
   :ay_son;` = özetteki «Logo e-ticaret kanalı» (kanal kodu önce ölçülür; `kanal_net_ciro` ölçüsüyle de aynı çıkmalı).
3. CRM'de site siparişi yok (özetteki «kaynak: T-soft» notunun kanıtı): `SELECT COUNT(*) FROM
   Timas_MSCRM.dbo.new_siparisBase WHERE (new_b2cid IS NOT NULL OR new_yenib2cid IS NOT NULL) AND CreatedOn >=
   DATEADD(month, -12, GETDATE());` = 0 (değilse kaynak kararı gözden geçirilir).
4. Barkod eşleşmesi: T-soft ürün `Barcode` ↔ `SELECT new_kitapId FROM Timas_MSCRM.dbo.new_kitapBase WHERE new_ean13 =
   :barkod` — sipariş satırlarında eşleşme oranı ekranda; eşleşmeyen barkod listesi boş değilse raporlanır.
5. RFM: `SELECT COUNT(*) FROM semantic_commerce_customers WHERE last_order >= CURRENT_DATE - 90` = aynı koşulun
   `semantic_commerce_orders` üzerinden `COUNT(DISTINCT customer_key)` ile hesaplanan değeri (iki yol birebir).
6. Kişisel veri yok: `semantic_commerce_*` tablolarının hiçbir kolonunda `@` içeren ya da 10+ haneli telefon biçimli
   değer yok (SQL ile tarama = 0).
7. Kampanya sonucu: seçilen kampanyada hedef ve kontrol grubunun sipariş sayısı `semantic_commerce_orders`'tan elle
   yazılan SQL ile birebir; kontrol payı ayardaki oranla ±1 kişi.

**Bağımlılık**
- Önce H2 çekirdeği (kimlik, izin, segment, dışa aktarım). H1 ağacı ilgi alanı için (yoksa geçici CRM Kitaplık).
- T-soft yöntem kataloğu okunup üye/sepet/kupon yöntemleri netleşmeli (S, keşif işi; yalnız okuma).
- Logo e-ticaret cari kodunun ölçülmesi.
- H4 ile paralel; H2 bitince H3 başlar (H2'nin tabloları hazırsa H3'ün kaynak okuma kısmı paralel başlayabilir).

**Tahmini büyüklük:** L. Parçalar: T-soft okuma + ayıklama M; özet + Logo uzlaşma M; RFM + geçiş S; tetik + kontrol
grubu + dışa aktarım M; kampanya sonucu M; ekranlar M.
