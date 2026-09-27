# M34 — E-Ticaret ve Platform Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M34.txt` (ZEKİ_Moduller3.html'den
çıkarıldı), `specs/E_Ticaret_Müşteri_Yönetimi_Ent.txt`, sınır için `specs/M40.txt`, `M41.txt`, `M42.txt`;
depoda `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`,
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `PROJECT-MEMORY.md`,
`configs/semantic/knowledge/crm/table_descriptions.json` (CRM üst verisi, 2026-09-09),
`configs/semantic/knowledge/logo/knowledge/` (sözlük, kurallar, uyarılar), `src/canvas/nav/navModel.ts`,
`backend/semantic_bridge/access_catalog.json`, `backend/semantic_bridge/seo_geo/` (connections, store, crm, reviews,
sunset, watch); bellek: tsoft-no-write, crm-tsoft-no-push-integration, seo-geo-module, live-bi-numbers-2026,
logo-155-frozen-copy, no-tech-names-on-screens, chat-persona-zeki-ai.
Not: `ZEKİ_Veri_Haritasi2.html` verilen klasörde yok; veri bölümü depodaki ölçümlere dayanır. Sunucuya bağlanılmadı;
aşağıdaki sayılar depodaki belgelerde tarihiyle kayıtlı ölçümlerdir, yenisi yapılmadı.

## 1. Modül ne işe yarar

İş tanımına göre modül, Timaş kitaplarının Trendyol, Hepsiburada, Amazon, D&R gibi platformlarda ve kendi sitesinde
(timas.com.tr, T-soft altyapısı) eksiksiz, doğru fiyat ve stokla görünmesini sağlar: fiyat/stok eşitlemesi ve yeni kitap
listeleme tam otomatik (K1), düşük dönüşümlü ürünün tespiti ile başlık/açıklama/görsel/kategori iyileştirmesi Zeki önerir,
insan onaylar (K2). Çıktılar: platform panosu, iyileştirme önerileri, eşitleme raporu.

Bugünkü sorun veriyle belli. Ürün kartı içeriği CRM'de, stok ve maliyet Logo'da, vitrin T-soft'ta duruyor. Aralarındaki
aktarım belgelenmemiş: CRM'den T-soft'a veri gönderen eklenti, iş akışı ya da servis ucu yok. `new_tsoftaktif` bayrağı
CRM dışından doğrudan SQL ile doldurulmuş, `new_webstok` hiçbir kitapta dolu değil (crm-eticaret-entegrasyon §1, §3.3).
Pazar yerleri CRM'de ürün beslemesi olarak değil, **toptan cari** olarak duruyor (Kitapyurdu, D-Market/Hepsiburada,
Amazon Turkey, Amazon Kindle US, Amazon Seller Central). Trendyol, Hepsiburada ya da Amazon için API entegrasyonu izi de
yok (§4). Sitede Search Console'un bildirdiği sorunlar: 5.108 sayfa taranmış ama dizine girmemiş, 3.934 sayfa 404 veriyor,
717 eski adres anasayfaya yönleniyor (seo-geo-modul, 2026-09-26). Bu yüzden iş tanımındaki "K1 otomatik eşitleme" bugün
ne teknik olarak ne de kurallar gereği yapılabilir: T-soft'a yazmak yasak, platform API'lerine erişim yok. Kullanıcının ilk
ihtiyacı üç kaynak arasındaki farkı görmek ve kapatmak.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Site (timas.com.tr) e-ticaret sorumlusu | Pazarlama ya da B2C. CRM `new_ilgilidepartman` seçeneklerinde "B2C" var; bu işi yapan kişi ve ekip **varsayım** | Her gün | Masaüstü (liste ve düzeltme), telefonda uyarı |
| Pazar yeri / kilit hesap sorumlusu (Kitapyurdu, Hepsiburada, D&R, Amazon) | Satış. CRM satış hedefi bölgeleri arasında D&R, Hepsiburada, Kitapyurdu ve B2C var (crm-timas-mscrm-detay) | Haftalık, kampanya dönemlerinde her gün | Masaüstü |
| Ürün kartı içerik editörü (spot, arka kapak, anahtar kelime, kategori) | Editörya. 2026-07-01'den bu yana `new_tsoftaktif` alanındaki 256 denetim kaydının çoğu "Timas CRM" ortak hesabından ve editörlerden geliyor (kanıt: AuditBase) | Kitap çıkışında ve düzeltme gerektiğinde | Masaüstü |
| SEO uzmanı | Pazarlama. SEO & GEO modülünün (`/seo-geo`) kullanıcısı | Haftalık | Masaüstü |
| Pazarlama / satış müdürü | Yönetim | Haftalık özet | Telefon ve masaüstü |
| Depo / stok sorumlusu | Depo (M43 ile ortak) — **varsayım** | Uyarı geldikçe | Telefon |

CRM ekip üyeliklerinde (2026-09-15) Satış 49, Pazarlama 35, Editörya 54 kişi görünüyor. Bunlardan kaçının e-ticaret işi
yaptığı bilinmiyor.

## 3. Bugün bu iş nasıl yapılıyor

- **Site sorumlusu.** Ürünleri T-soft panelinde düzenliyor (**varsayım**). Yeni kitapta CRM'de "TSOFT Aktif" elle
  işaretleniyor (kanıt: 2026-07-01'den bu yana 256 denetim kaydı: 174 oluşturma, 69 güncelleme). Ürün kartının T-soft'a
  elle mi, bir ara yazılımla mı, CRM görünümlerinden (`Tsoft_KitapDetay`, `NY_WEB_StokKarti`) çekilerek mi gittiği
  bilinmiyor; BT'ye sorulacak. Stok ve fiyatın Logo'dan T-soft'a gitmesi güçlü bir olasılık ama doğrulanmadı. Sıkıntı:
  iki sistemin farkını gösteren bir ekran yok. Hatalı ya da eksik kart ancak okur ya da Google fark ettiğinde ortaya
  çıkıyor (**varsayım**; 404 ve dizin sayıları bunu destekliyor).
- **Pazar yeri sorumlusu.** Toptan siparişler CRM'den geçiyor (kanıt: son 180 günde Kitapyurdu 227 sipariş, D-Market 34;
  crm-eticaret §4). Platformda Timaş kitaplarının içerik, fiyat ve puanını görmek için platform sitelerine tek tek
  bakıyor (**varsayım**). Platformun okura sattığı adet Timaş'a gelmiyor, gelse bile sisteme girmiyor (**varsayım**,
  sorulacak).
- **İçerik editörü.** CRM kitap kartındaki alanları dolduruyor. T-soft'ta aktif 6.578 kitapta arka kapak 6.128'inde,
  föy metni 3.282'sinde, anahtar kelime 2.687'sinde dolu. "Kitap Tanıtım – Web Metni" yalnız 60'ında dolu (crm-eticaret
  §3.1–3.3). Editörün girdiği metnin sitede görünüp görünmediğini takip edebileceği bir yol yok.
- **SEO uzmanı.** SEO & GEO modülünde (test sunucusunda, müşteri VM'inde yok) ürün denetimi yapıp öneri alıyor. Onay
  yalnız kayıt olarak kalıyor ve hiçbir yere gönderilmiyor (tsoft-no-write).

## 4. İhtiyaçlar ve acı noktaları

**Site sorumlusu** (önem sırasıyla)
1. Tek listede "sitede şöyle, CRM'de/Logo'da böyle" farkları: aktiflik, ad, barkod, fiyat, stok.
2. Eksik ürün kartları (görsel, açıklama, yazar, kategori), satışa etkisine göre sıralı.
3. Satışta olmaması gereken kitaplar. Haklar ekranında ölçülen: 247 "bizim değil", 55 iptal, 9 çekilmiş kitap hâlâ satışta
   (seo-geo-modul, 2026-09-27).
4. Ürün bazında görüntülenme → satış hunisi (T-soft `StatViews`, `CountTotalSales`).
5. Açılan farkın kapandığını görmek, yani bir düzeltme günlüğü.

**Pazar yeri sorumlusu**
1. Platform carisi bazında Logo'dan satış, iade ve eğilim (sell-in).
2. Stoğu tükenmek üzere olan ve platformda çok satan kitaplar.
3. Platforma gönderilecek içerik paketini (başlık, açıklama, görsel adresi, anahtar kelime, ISBN) tek dosyada alabilmek.
4. Platformda Timaş ürününün nasıl göründüğü (fiyat, puan, içerik). Bugün bu veri hiç yok.

**İçerik editörü**
1. "Benim kitaplarımda hangi alan eksik" listesi.
2. Platform uzunluk sınırlarına uyan bir Zeki AI taslağı.
3. Onayladığı metnin nereye gittiğini ve sitede görünüp görünmediğini bilmek.

**Müdür**
1. Haftalık kanal özeti: site ile pazar yeri carileri yan yana.
2. Açık fark sayısı ve kapanma hızı.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Site sorumlusu olarak her sabah CRM, Logo ve T-soft arasındaki farkları tek listede görmek istiyorum, çünkü yanlış fiyat
  ya da satışta olmayan kitap okura yansımadan önce düzeltmem gerekiyor.
- Site sorumlusu olarak bir farkı "düzeltildi" ya da "bilinçli fark" diye işaretlemek istiyorum, çünkü aynı fark ertesi gün
  yeniden karşıma çıkmamalı.
- Site sorumlusu olarak çok görüntülenip az satan kitapları görmek istiyorum, çünkü kartı iyileştirilecek ilk kitaplar
  bunlar.
- Pazar yeri sorumlusu olarak Kitapyurdu, Hepsiburada ve Amazon carilerinin son dönem alımlarını ve iadelerini kitap
  bazında görmek istiyorum, çünkü platform görüşmesine veriyle gitmeliyim.
- Pazar yeri sorumlusu olarak seçtiğim kitapların içerik paketini Excel olarak indirmek istiyorum, çünkü platformun
  yükleme ekranına elle giriyorum.
- İçerik editörü olarak kendi kitaplarımdaki eksik alanları ve Zeki AI'ın önerdiği metni yan yana görmek istiyorum, çünkü
  onaylamam için karşılaştırmam gerekiyor.
- Müdür olarak pazartesi sabahı telefonuma kanal özeti gelsin istiyorum, çünkü ayrıntıya ancak sorun varsa bakarım.

**Ana ekranlar ve akış**
- *Platform durumu* (ilk açılış). Üstte dört gösterge: T-soft'ta aktif ürün, açık fark, eksik kart, satışta olmaması gereken
  kitap. Her birinin yanında son okuma zamanı ve Logo verisinin kesim tarihi yazar. Altında "bugün bakılacaklar" listesi,
  önce satış etkisi en büyük olanlar.
- *Farklar* (eşitleme raporu). Her satır bir kitap; sütunlarda CRM, Logo ve T-soft değerleri. Fark türüne göre süzülür,
  "düzeltildi / bilinçli fark / sonra" diye işaretlenir, CSV olarak indirilir.
- *Ürün kartı sağlığı*. Eksik alanlar ve Zeki AI önerisi. Öneri akışı SEO modülünün öneri kaydıyla aynıdır.
- *Huni*. Görüntülenme, satış ve yorum; dönüşümü düşük ürünler.
- *Pazar yerleri*. Cari bazında Logo satış ve iadeleri, eğilim, içerik paketi indirme.
- Tık sayıları: farklar listesinden bir kitabın üç kaynaktaki değerini görmek 2 tık; eksik bir alan için öneri istemek 3 tık
  (liste → kitap → "Öneri iste"); haftalık özet 0 tık (e-posta).
- Telefonda gösterge kartları ve "bugün bakılacaklar" okunur. Fark tablosu telefonda kitap başına kart olarak açılır
  (AGENTS.md: mobil uyum zorunlu).

**Zeki AI'a soracakları örnek sorular**
1. "Sitede aktif olup Logo'da stoğu sıfır olan kaç kitap var?"
2. "Geçen ay en çok görüntülenip hiç satmayan 20 kitap hangileri?"
3. "Kitapyurdu'na bu yıl kaç adet sattık, iade oranı geçen yıla göre ne oldu?"
4. "CRM'deki fiyatı sitedekinden farklı olan kitaplar hangileri?"
5. "Arka kapak yazısı boş olan, çok satan kitaplarımız hangileri?"
6. "E-ticaret kanalının net cirosu aylara göre nasıl gidiyor?"
7. "Hakkı bizde olmadığı hâlde sitede satışta olan kitaplar hangileri?"

**Otomasyon katmanı**
- K1: Her gece T-soft (yalnız okuma), CRM ve Logo okunur, farklar ve eksikler hesaplanır, uyarı olayı açılır. Hiçbir sisteme
  yazılmaz.
- K2: Kart içerik önerisi, fiyat/aktiflik düzeltme önerisi. Onay portalda kayıt olarak durur.
- K3: Platform stratejisi (hangi platformda hangi kitap öne çıkarılsın): Zeki AI analiz eder, ekip karar verir.
- K4: Düzeltmeyi T-soft panelinde ya da platformda insan uygular. İş tanımındaki "otomatik listeleme ve eşitleme" bu sürümde
  K4'e iner; T-soft yazma yasağı ve CRM yazma yetkisi çözülmeden K1'e çıkamaz.

**Bildirim / uyarı**
- Site sorumlusuna: fiyat farkı, satışta olmaması gereken kitap ya da stok sıfırken aktif ürün **ilk kez** görüldüğünde
  e-posta (mevcut uyarı ilkesi: olay ilk açıldığında bir kez; `alerts.py`, `seo_geo/watch.py`).
- Pazar yeri sorumlusuna: çok satan bir kitapta stok tükenme riski, haftalık.
- Müdüre: pazartesi haftalık özet e-postası.
- Kanal e-posta ve portaldaki Uyarılar rozeti. SMS ya da anlık bildirim altyapısı yok.

**Onay ve yetki** (öneri; `docs/analiz/yetki-mekanizmasi-2026-09-27.md` modeli)
- `sayfa:eticaret` — panoyu ve farkları görür.
- `ozellik:eticaret.fark-isaretle` — farkı düzeltildi/bilinçli diye işaretler.
- `ozellik:eticaret.oneri-uret` — içerik önerisi üretir (model harcar).
- `ozellik:eticaret.oneri-onay` (explicit) — öneriyi onaylar ya da reddeder; yapan onaylayamaz.
- `ozellik:veri.disa-aktar` (var) — içerik paketi ve CSV indirir.
- Menü yeri: Pazarlama alanı. Bugün bu alanın alt başlığı "SEO & GEO"; alan adı genişletilmeli.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Sitedeki ürün, aktiflik, SEO alanları, görüntülenme, toplam satış, yorum sayısı | T-soft (`product/get`, yalnız okuma) | 6.781 ürün, 135 alan; `StatViews`, `CountTotalSales` (5.683 üründe, toplam 430.644), `CommentCount`; gece `semantic_seo_products`'a yazılıyor | Sitedeki stok ve fiyat alanlarının doluluğu **ölçülecek**. `CountTotalSales`'in dönemi (tüm zamanlar mı) **ölçülecek** |
| Ürün kartı içeriği (ad, spot, arka kapak, anahtar kelime, kategori, kapak) | CRM `new_kitapBase` | Alanlar ve doluluk ölçülmüş (crm-eticaret §3). Eşleme ISBN/EAN-13 ile (5.466/5.656) | SEO başlığı ve meta açıklama için CRM'de alan yok |
| Stok | Logo (`STINVTOT`) | .155 donmuş kopya; son fatura 2026-08-17 | Canlı Logo (.25) okuma yetkisi yok. "Gerçek zamanlı stok" bugün sağlanamaz |
| Fiyat | Logo fiyat listesi / CRM `new_kdvdahilfiyat` / T-soft | CRM alanı dolu (11.232 kitap). Asıl fiyat kaynağının Logo olduğu **varsayım** | Hangi fiyatın geçerli olduğu BT'ye sorulacak |
| Hak ve yayın durumu | CRM sözleşme + `new_kitap_yayincilikstatusu` | `seo_geo/crm.py` her gece okuyor: hak var 3.521, sözleşme kaydı yok 2.575, incele 294, eksik 184 | — |
| Pazar yeri carisine satış (sell-in) | Logo `INVOICE`/`STLINE`, cari `SPECODE2 = E-TICARET` | Kanal ölçüsü ve kayıtlı SQL var; ilk cariler Turkuvaz, Kitapyurdu, D-Market, Point | Veri 2026-08-17'de bitiyor |
| Platformun okura sattığı adet (sell-through), platform fiyatı, puanı, sıralaması | Platform satıcı panelleri / tedarikçi raporları (dış) | Depoda hiçbir iz yok. Bot korumalı siteler taranmaz (AGENTS.md kuralı) | **En büyük boşluk.** İzinli kanal gerekir: satıcı API'si, platformun tedarikçi raporu ya da kullanıcının yüklediği Excel |
| Site trafiği ve dönüşüm (oturum, sepet) | GA4 | `zeki@` hesabının GA4 erişimi yok | Erişim müşteriden istenecek |
| Arama görünürlüğü | Search Console | Okunuyor (son 3 ay: 245 bin tıklama, 9,73 milyon gösterim) | — |

## 7. Diğer modüllerle bağ

- Girdi alır: M25/M26 SEO & GEO (ürün denetimi, öneri akışı, Haklar ve CRM, yönlendirmeler), M9 Fiyatlama (liste
  fiyatı), M43 Depo ve Stok (stok), M11 Baskı Tekrarı (tükenme ve yeniden baskı tarihi), M6/M54 Telif (internette
  gösterim hakkı), M13 Kapak (kapak görseli).
- Çıktı verir: M35 Kampanya (hangi kitap kampanyaya hazır, stok ve kart durumu), M40/M41/M42 (platforma özel mağaza
  işleri; M34 ortak çatı olur, farklar ve içerik paketi oradan beslenir), M45 Finansal Raporlama (e-ticaret kanal özeti),
  DYK (kanal göstergesi).
- Sınır: platforma özel sipariş, kargo, iade süreçleri M40–M42'ye aittir, M34'e girmez.

## 8. Kısıtlar

- **T-soft'a yazma yasak** (2026-09-25 kullanıcı kararı). Yalnız `auth/*` ve `*/get*` çağrılır; `seo_geo/connections.py`
  içindeki `READ_ONLY` koruması yeniden kullanılır. Eşitleme ve listeleme gönderimi yapılmaz.
- **CRM'e yazılmaz.** Farkın işareti, notlar ve onaylar köprünün kendi tablolarında durur. CRM Web API yetkisi müşteriden
  bekleniyor. `Product` varlığındaki iş akışı sonsuz döngüye giriyor (30 günde 332 iptal); ileride yazma açılsa bile
  `Product`'a, `new_name`'e, `new_ean13`'e ve `new_StokKodu`'na yazılmaz.
- Müşteride web taraması kapalı (`WEB_WATCH_ENABLED=0`). Platform sayfaları kazınmaz; bot korumasını aşan araç kullanılmaz.
- Ekranlarda model ya da teknoloji adı geçmez, "Zeki AI" yazılır. Müşterinin kullandığı platform adları (T-soft, Trendyol,
  Amazon) kalabilir (seo-geo-module kararı).
- Demo veri yok, sayı tavanı yok. Listeler sayfalanır; kesilen bir şey varsa neyin dışarıda kaldığı yazılır.
- Logo verisi donmuş kopyadan geliyor. Her rakamın yanında kesim tarihi yazmalı.
- Zeki AI sohbeti bugün finans dışındaki soruları tek cümleyle reddediyor (`chat_scope.py`). Buradaki soruların
  cevaplanabilmesi için kapsamın genişletilmesi gerekiyor.
- Hukuk: fiyat farkı tüketiciye yanlış fiyat gösterimi riskidir. Bir platformda yanlış içerik ya da hakkı olmayan kitap
  satışı telif ihlali riski taşır; "hak yok ama satışta" listesi bu yüzden ilk sürümde yer alır. Modül okur kişisel verisi
  işlemez: T-soft siparişleri (62.903) kişisel veri içerdiğinden ilk sürümde okunmaz.

## 9. Kapsam önerisi

**İlk sürüm** (en çok değer, en az bağımlılık)
- Gece fark raporu CRM ↔ T-soft ↔ Logo: aktiflik, ad, barkod, fiyat, stok. Farkların işaretlenmesi ve günlüğü.
- Satışta olmaması gereken kitaplar (Haklar verisinden) ve eksik ürün kartı listesi, satış etkisine göre sıralı.
- Görüntülenme/satış hunisi (T-soft ürün kaydı; yeni bir dış çağrı gerekmez).
- Pazar yeri carileri sell-in panosu (Logo, kanal ve cari kırılımı).
- İçerik paketi dışa aktarma (Excel/CSV). Platformlara gönderim yok.
- Uyarı ve haftalık özet e-postası.

**Sonraki sürüm**
- Platformun okura satış ve fiyat verisi: satıcı API'si ya da tedarikçi raporunun yüklenmesi (izinli kanal açılınca).
- GA4 bağlanınca sepet ve ödeme hunisi.
- CRM Web API yetkisi gelince onaylı içeriğin CRM'e yazılması ve T-soft'ta göründüğünün gece doğrulanması (crm-eticaret §7.3).
- Kanal fiyat dengesi önerisi (M9 ve M35 ile).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/connections.py` (T-soft yalnız okuma istemcisi), `seo_geo/store.py`
  (`semantic_seo_products`), `seo_geo/crm.py` (CRM kitap kartı ve haklar, EAN-13 eşlemesi), `seo_geo/reviews.py`,
  `seo_geo/sunset.py`, `seo_geo/watch.py` (olay ve haftalık rapor).
- `backend/semantic_bridge/alerts.py` (uyarı kuralı = soru), `board.py` (pano kartı), `reports.py` (planlı Excel raporu).
- `backend/semantic_bridge/editorial_studio_marketing.py` (e-ticaret ürün sayfası metni → SEO öneri akışı).
- `backend/semantic_bridge/access.py` ve `access_catalog.json` (yetki), `admin.py` audit (`semantic_audit`).
- Logo kanal ölçüsü: `configs/semantic/knowledge/logo/knowledge/sql/2026-y-l-nda-kitapci-e-ticaret-ve-dagitici-kanallar-i-in-ay.md`.

## 10. Uzmanlara sorulacak sorular

1. (BT / entegrasyon firması) T-soft'taki ürün kartı, stok ve fiyat nereden, hangi sıklıkla ve hangi anahtarla (ISBN mı,
   stok kodu mu) besleniyor? Elle düzenlenen alanlar var mı?
2. (E-ticaret sorumlusu) Timaş Trendyol, Hepsiburada ya da Amazon'da kendi satıcı mağazasını mı işletiyor, yoksa bu
   platformlar yalnız toptan alıcı mı? Kendi mağaza varsa hangi platformlarda?
3. (Satış) Platformlar Timaş'a okur satış adedi ve stok raporu veriyor mu? Veriyorsa hangi biçimde ve ne sıklıkla?
4. (E-ticaret / finans) Sitedeki geçerli fiyatın kaynağı hangisi: Logo fiyat listesi, CRM `new_kdvdahilfiyat` ya da
   T-soft'ta elle girilen fiyat?
5. (Yönetim) Bir farkı kim kapatır, kim onaylar? Site sorumlusu tek başına mı, yoksa fiyat farkında finans onayı mı gerekir?

## 11. Başarı ölçütü

- Açık fark sayısı ve ortalama kapanma süresi. Taban ilk haftada ölçülür, hedef ekiple konur.
- "Hak yok ama satışta" ve "stok sıfır ama aktif" listelerinin sıfıra yaklaşması.
- Eksik ürün kartı sayısında hafta hafta düşüş. Düzeltilen kartlarda Search Console gösterim ve tıklama değişimi (önce/sonra;
  `seo_geo/impact.py` yöntemi).
- Kullanım: site sorumlusu haftada en az 4 gün açıyor mu, pazar yeri sorumlusu içerik paketini indiriyor mu (audit kaydı).
- Hata: kullanıcıların "yanlış fark" işaretlediği satırların oranı. Yüksekse eşleme kuralı düzeltilir.

## 12. Uzman gözüyle en iyi sistem

*15 yıllık bir e-ticaret ve kanal müdürünün gözünden (bu bölüm uzman görüşüdür, TİMAŞ verisine dayanmaz).*

Büyük yayınevleri bu işi üç katmanda çözüyor. (1) **Tek ürün bilgisi kaydı:** ürün bilgisi yönetim sistemi ya da yayıncılık
üst veri sistemi. Kitabın adı, künyesi, açıklaması, kategorisi ve görselleri bir yerde tutulur, oradan her kanala standart
dosyayla (ONIX gibi) dağıtılır. Kanalda elle düzeltme istisnadır ve kaynağa geri işlenir. (2) **Kanal yönetimi:** çok
kanallı satış yazılımları stok ve fiyatı kanallara tek yerden dağıtır, her kanalın reddettiği ürünü listeler.
(3) **Okura satış verisi:** perakende satış paneli verisi (sell-through) ve pazar yeri satıcı raporları. Kanal müdürü "ne
sattık"ı değil "okur ne aldı"yı izler. Sektörde yaygın gözlem, üst verisi eksiksiz kitabın aramada daha çok bulunduğu ve
daha çok sattığıdır. Bu yüzden "üst veri doluluk puanı" bir kanal göstergesi olarak kullanılır.

TİMAŞ için mükemmel sistem: CRM kitap kartı tek kaynak olur. Zeki AI her gece kaynak ile vitrinleri karşılaştırır, farkı
sahibine atar, farkın kapanmasını izler. Kanallara giden içerik paketini standart dosya olarak üretir. Pazar yeri raporları
yüklendikçe okura satış verisi sell-in ile yan yana gelir. Yazma yetkileri çözüldüğünde aynı akış onaylı düzeltmeyi kaynağa
yazar.

**Uzmanın bir günü (sistemle)** — *örnek senaryo; kitap/cari adları ve sayılar temsilîdir, ölçüm değildir*
- 08:40 Telefonda pazartesi özeti ya da günlük uyarı: "3 kitapta fiyat farkı, 1 kitap hak yok ama satışta."
- 09:00 Masaüstünde *Platform durumu*. Göstergelerde açık fark sayısını ve Logo kesim tarihini görür. "Bugün bakılacaklar"
  listesinde ilk satır, hakkı devredilmiş bir kitabın sitede satışta olması. Kitaba tıklar, Haklar kaydını görür, T-soft
  panelinden ürünü pasife alır, portalda "düzeltildi" der. Ertesi gecenin okuması bunu doğrular.
- 10:00 *Farklar* sekmesinde fiyat farkı olan kitaplar. CRM ile T-soft'u karşılaştırır. Bir kısmını "bilinçli fark
  (kampanya)" diye notla kapatır.
- 11:30 *Huni*: çok görüntülenip az satan kitaplar. İlk beşi için "Öneri iste" der, Zeki AI başlık ve açıklama taslağı
  üretir, içerik editörüne onaya düşer.
- 14:00 Pazar yeri toplantısı öncesi *Pazar yerleri*: Kitapyurdu'nun son 3 ayda aldığı ve iade ettiği kitaplar. İçerik
  paketini Excel olarak indirip platform temsilcisine gönderir.
- 17:30 Gün sonu: kapattığı farklar günlüğe düşmüş. Kapanmayanlar yarının listesinde, sahibinin adıyla duruyor.

**"Bunu görürsem hemen kullanırım"**
1. Üç kaynağı (CRM, Logo, site) aynı satırda gösteren fark listesi. Yanında "kim düzeltir" ve "düzeltildi mi" bilgisi.
2. "Hak yok / çekildi ama satışta" listesi. Hukuki risk olduğu için her sabah bakılır.
3. Platforma gönderilecek içerik paketinin tek tıkla Excel çıktısı.

**"Bunu yaparsanız kullanmam"**
1. Okuduğu veriyi "canlı" gibi gösterip tarih yazmamak. Donmuş Logo stokuyla "stok yok" demek güveni tek günde bitirir.
2. Her farkı uyarıya çevirip bilinçli farkı (kampanya fiyatı) susturma imkânı vermemek. Uyarı yorgunluğu başlar.
3. "Otomatik güncelledim" deyip aslında hiçbir yere yazmamak ya da onaysız bir yere yazmak. Yazma yoksa ekranda açıkça
   "bu düzeltmeyi siz yapacaksınız" yazmalı.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kitap listesi ve eşleme | `LG_411_ITEMS.CODE` (stok kodu) | `new_kitapBase.new_StokKodu`, `new_ean13`, `new_tsoftaktif`, `statecode` | — | Eşleme kurallıdır: EAN-13 (T-soft `Barcode`) ↔ CRM ↔ Logo stok kodu. Model gerekmez |
| Stok farkı | Stok bakiyesi: `LG_411_01_STLINE` (`LINETYPE=0`, `CANCELLED=0`, IOCODE 1/2 giriş, 3/4 çıkış; katalog kuralı) ya da baskı önerisinin kullandığı `LV_411_01_STINVTOT` | — | — | Rakam SQL'den gelir. Kesim tarihi ekranda yazar |
| Fiyat farkı | Fiyat listesi (hangi Logo tablosu olduğu BT'den teyit edilecek) | `new_kdvdahilfiyat`, `new_PerakendeBirimFiyat` | — | Kurallı karşılaştırma. Hangi fiyatın geçerli olduğu iş kararıdır |
| Hak / yayın durumu | — | `new_sozlesmeBase.new_iletimhakki`, `new_SozlesmeTipi=5`, `new_kitap_yayincilikstatusu` (`seo_geo/crm.py` sonucu `semantic_seo_crm_books`) | — | Hazır ve ölçülmüş; yeniden yazılmaz |
| Eksik kart / doluluk puanı | — | `new_ozet`, `new_kitapspotu`, `new_AnahtarKelimeler`, `new_webkategorileritext`, `new_resimurl`, `new_yazartext` | — | Doluluk kurallı sayılır |
| Kart içerik önerisi (başlık, açıklama, anahtar kelime) | — | Aynı alanlar + `new_ozet` (konu) | Taslak metin üretir (platform uzunluk sınırına uyar) ve gerekçesini yazar | Modelin gerçekten değer kattığı yer: metin taslağı. Onay insanda |
| Fark nedeninin sınıflanması (ör. "kampanya fiyatı", "yeni baskı", "veri hatası") | Son fiyat değişikliği (varsa) | `new_kitapgecmisi` (fiyat/kapak/baskı değişim satırı), AuditBase | Kapalı küme sınıflama: tek token + olasılık (`structured_outputs.choice` + logprobs). Marj düşükse "belirsiz" | Kullanıcının farkı hızlı ayıklaması için. Karar değil öneri |
| Huni | — | — | Rakam üretmez. "Neden az satıyor olabilir" diye kısa yorum yazar (kart doluluğu, yorum, fiyat) | Yorum; rakam T-soft kaydından |
| Pazar yeri sell-in | `LG_411_01_INVOICE` + `LG_411_CLCARD.SPECODE2='E-TICARET'`; kitap kırılımı `V_SatisRaporu_411` (2026), `V_SatisRaporu_211` + `Yıl=` (2021–2025); ölçü `kanal_net_ciro` / `v_channel_net`, satır tutarı `LINENET`, faturalı satır `INVOICEREF<>0` | `AccountBase.new_logicalref` → cari eşleme | — | Kayıt sistemi Logo'dur (gerçekleşmiş satış) |
| Doğal dil soru | Katalog ölçüleri (`net_ciro`, `kanal_net_ciro`, `iade_orani`) | Katalogdaki CRM tabloları | Soru → SQL (mevcut soru hattı). Cevabı yorumlar | Soru hattı var. `chat_scope.py` kapsamı genişletilmeli |

Model çağrısı yalnız `rt.llm_for("eticaret", priority)` ile yapılır. Gece toplu işi ayrı betikse `QueuedLlm(...,
purpose="bg:eticaret")` kullanılır. `LlmClient` doğrudan kurulmaz. Ekranda "Zeki AI önerisi" yazar.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/eticaret.py`: depo (tablolar, `ensure()`), fark hesabı, sıralama.
- `backend/semantic_bridge/eticaret_sources.py`: okumalar. T-soft verisini **yeniden okumaz**, `semantic_seo_products`
  ve `semantic_seo_crm_books`'u okur. CRM `connector_from_file(SEMANTIC_CRM_CONNECTION_FILE)` (`seo_geo/crm.py`
  deseni). Logo köprünün Logo bağlantısıyla; fiziksel tablo adlarıyla, yıllık görünümle (ALL2 değil).
- `backend/semantic_bridge/eticaret_api.py`: `register(app, rt=..., can=..., audit=...)` (`contracts_api.py` deseni).

**Tablolar** (meta Postgres, `semantic_eticaret_` öneki)
- `semantic_eticaret_items` (tenant_id, product_key [EAN-13], stok_kodu, crm_kitap_id, tsoft_product_id, ad,
  tsoft_aktif, crm_tsoftaktif, stok_logo, stok_tsoft, fiyat_crm, fiyat_tsoft, doluluk_puani, eksik_alanlar_json,
  views, total_sales, comments, hak_durumu, yayin_durumu, logo_kesim_tarihi, okundu_at)
- `semantic_eticaret_diffs` (id, tenant_id, product_key, tur [aktiflik|ad|barkod|fiyat|stok|hak|eksik_kart], crm_deger,
  logo_deger, tsoft_deger, ilk_goruldu, son_goruldu, durum [acik|duzeltildi|bilincli|sonra], neden_onerisi,
  neden_olasilik, sahip, not, kapatan, kapandi_at)
- `semantic_eticaret_diff_log` (diff_id, zaman, kullanici, eylem, not)
- `semantic_eticaret_runs` (id, basladi, bitti, kaynak_ozet_json, hata)
- Öneriler ayrı tablo açmaz: `semantic_seo_proposals`'a `source='eticaret'` ile yazılır (SeoGeo `external_proposal`).

**Uçlar** (`/api/v1/eticaret/*`)
- `GET overview` (göstergeler + bakılacaklar + kesim tarihleri)
- `GET diffs?tur=&durum=&q=&page=` · `GET diffs/{id}` · `POST diffs/{id}/mark` (durum + not)
- `GET items/{product_key}` (üç kaynağın değerleri, geçmiş)
- `GET funnel?page=` · `GET marketplaces?donem=` · `GET marketplaces/{cari_kodu}/books`
- `POST items/{product_key}/propose` (öneriyi SEO öneri akışına atar)
- `GET export/content-pack?keys=` (Excel/CSV) · `POST run-due` (yalnız sistem jetonu)

**Ekranlar**: `src/canvas/eticaret/` → `EticaretHome.tsx`, `DiffsScreen.tsx`, `FunnelScreen.tsx`,
`MarketplacesScreen.tsx`, `ItemDrawer.tsx`. Rotalar `/timas/e-ticaret`, `/e-ticaret/farklar`, `/e-ticaret/huni`,
`/e-ticaret/pazar-yerleri` (`src/App.tsx`). Menü: `navModel.ts` Pazarlama alanı, yeni bölüm "E-ticaret" (Pazarlama alanının
`hint`'i "SEO & GEO" → "E-ticaret, SEO & GEO"). Kampüs: `ModulesMenu.tsx` `LIVE` içine `M34: '/e-ticaret'`, `GROUP_HOME`
içine `'Dijital & Topluluk'`.

**Yetki** (`access_catalog.json`): sayfalar `sayfa:eticaret`, `sayfa:eticaret-farklar`, `sayfa:eticaret-huni`,
`sayfa:eticaret-pazar-yerleri`. Özellikler `ozellik:eticaret.fark-isaretle`, `ozellik:eticaret.oneri-uret` (model
harcar), `ozellik:eticaret.oneri-onay` (**explicit**; SEO'daki `ozellik:seo.onay` ile aynı ilke), dışa aktarma için mevcut
`ozellik:veri.disa-aktar`. Köprüde yönlendirici düzeyinde `/api/v1/eticaret/*` → `sayfa:eticaret`; kapsam testi
(`page_gate`) yeni uçları yakalar.

**Zamanlayıcı**: `scripts/server/timas-eticaret.timer`, her gece 04:30 (T-soft eşitlemesini yapan `timas-seo.timer`
03:00'ten sonra). CRM + Logo okunur, farklar güncellenir, bir farkın koşulu kalktıysa kendiliğinden kapanır, yeni olaya
e-posta gider. İlk kez elle koşturulur (bellek: run-it-before-it-runs-itself). Pazartesi haftalık özeti aynı işte.

**Kabul testleri** (gerçek veri; referans köprünün `run_sql` ucundan değil, doğrudan bağlantıdan)
1. CRM'de TSOFT Aktif sayısı: `SELECT COUNT(*) FROM dbo.new_kitapBase WHERE new_tsoftaktif = 1` (CRM .28) = ekrandaki
   "CRM'de aktif" sayısı.
2. "CRM'de aktif, sitede yok" farkı: CRM `new_ean13` kümesi (yukarıdaki süzgeç) eksi
   `SELECT data_json->>'Barcode' FROM semantic_seo_products WHERE tenant_id=:t AND active` kümesi. Fark sayısı ve
   ilk 20 barkod ekranla birebir.
3. Pazar yeri sell-in (2026): `SELECT c.CODE, SUM(CASE WHEN i.TRCODE IN (7,8,9) THEN i.NETTOTAL ELSE -i.NETTOTAL END)
   FROM LG_411_01_INVOICE i JOIN LG_411_CLCARD c ON c.LOGICALREF = i.CLIENTREF WHERE i.CANCELLED = 0 AND
   i.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = 'E-TICARET' AND i.DATE_ >= '2026-01-01' GROUP BY c.CODE` → cari başına
   ekrandaki net ciro (kuruş farkı 0).
4. Stok: rastgele 20 stok kodu için `SELECT SUM(CASE WHEN IOCODE IN (1,2) THEN AMOUNT ELSE -AMOUNT END) FROM
   LG_411_01_STLINE s JOIN LG_411_ITEMS it ON it.LOGICALREF = s.STOCKREF WHERE it.CODE = :kod AND s.LINETYPE = 0 AND
   s.CANCELLED = 0 AND s.IOCODE IN (1,2,3,4)` = ekrandaki Logo stoku.
5. "Hak yok ama satışta": `semantic_seo_crm_books` üzerinde Haklar ekranının kuralıyla sayım = M34 listesi (iki ekran aynı
   sayıyı göstermeli; 2026-09-27 ölçümünde bizim değil 247, iptal 55, çekildi 9).
6. Huni: rastgele 10 ürün için `semantic_seo_products.data_json` içindeki `StatViews` / `CountTotalSales` = ekran.
7. Kitap bazında pazar yeri satışı: `V_SatisRaporu_411` üzerinden `Yıl*12+Ay` penceresiyle ve `JOIN (VALUES …)` ile
   (plan tuzağı notu) 10 kitap = ekran.

**Bağımlılık**: SEO & GEO eşitlemesi (`semantic_seo_products`, `semantic_seo_crm_books`) çalışır durumda olmalı; test
sunucusunda var, müşteri VM'inde yok. VM'e çıkış SEO modülüyle birlikte olur. M35 ve M40–M42 bu modülün `items` ve
`diffs` tablolarını okur; M34 önce biter. M43 (stok) ile paralel kodlanabilir.

**Tahmini büyüklük**: L (3+ gün). Köprü, fark motoru ve kabul M; ekranlar (4 ekran, telefon kartları) M.
