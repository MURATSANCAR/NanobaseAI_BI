# M35 — E-Ticaret Kampanya ve Promosyon Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M35.txt` (ZEKİ_Moduller3.html'den), sınır için
`specs/M32.txt` başlığı, `M40.txt`, `M53.txt`, `M9.txt`, `specs/E_Ticaret_Müşteri_Yönetimi_Ent.txt`, `specs/ANALIZ-EK.md`;
depoda `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`,
`docs/analiz/seo-geo-modul-2026-09-25.md`, `docs/analiz/timesfm-baski-oneri/README.md`, `PROJECT-MEMORY.md`,
`configs/semantic/knowledge/crm/table_descriptions.json` (CRM üst verisi, 2026-09-09),
`configs/semantic/knowledge/logo/knowledge/{metrics,rules,caveats}/`, `backend/semantic_bridge/seo_geo/seasons.py`,
`backend/semantic_bridge/contracts_terms.py`, `backend/semantic_bridge/access_catalog.json`, `src/canvas/nav/navModel.ts`;
bellek: tsoft-no-write, logo-155-frozen-copy, sales-are-invoiced-lines, net-ciro-line-formula-wrong, live-bi-numbers-2026,
llm-gate, vllm-choice-logprobs. `ZEKİ_Veri_Haritasi2.html` verilen klasörde yok. Sunucuya bağlanılmadı; sayılar
depodaki tarihli ölçümlerdir.

## 1. Modül ne işe yarar

İş tanımına göre modülün iki işi var. Kampanya planlaması (K2): Trendyol flaş indirim, 11.11, kitap fuarı gibi dönemlerin
takvimi, indirim oranına göre kâr marjı analizi, set ve çapraz satış önerisi, sponsorlu ürün brifi. Kampanya takibi (K1):
kampanya süresince saatlik satış izleme, stok tükenme uyarısı, bütçe ve tıklama raporu, kampanya sonunda otomatik sonuç
özeti.

TİMAŞ'ın bugünkü sorunu şu: kampanya kararı (hangi kitap, yüzde kaç, hangi kanal) ile kararın sonucu (satış, marj, telif,
stok) aynı yerde görünmüyor. CRM'de 308 kampanya kaydı var, ancak bunlar bayi (B2B) kampanyaları; mecra seçenekleri
"CRM / B2B / CRM & B2B". Katalog notuna göre planlanan ve gerçekleşen ciro alanları kampanyaların hiçbirinde dolu değil
(`caveats/logo-timas.md`). Site ve pazar yeri kampanyalarının depoda hiçbir kaydı yok. Toptan satışta iskonto yaklaşık %46
(katalog kuralı) ve 2026 satış satırlarının %20'sinde maliyet (OUTCOST) girilmemiş. Bu iki durum, "bu indirim bize kâr
bırakır mı" sorusunu elle cevaplamayı zorlaştırıyor.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Kampanya / e-ticaret pazarlama uzmanı | Pazarlama (CRM ekip üyeliği: 35 kişi). E-ticaret kampanyasını yapan kişi **varsayım** | Kampanya öncesi haftalık, kampanya sırasında her gün | Masaüstü (plan), telefon (izleme) |
| Pazar yeri / kilit hesap sorumlusu | Satış. Satış hedefi bölgelerinde D&R, Hepsiburada, Kitapyurdu var | Platform kampanya çağrısı geldikçe | Masaüstü |
| Satış müdürü (bayi kampanyaları) | Satış. CRM'de kampanya ↔ kullanıcı bağı 617; "Bütün kullanıcılar uygulayabilir" alanı var, yani temsilci kampanyayı siparişte uyguluyor (kanıt: `new_kampanyaBase`, `new_new_kampanya_systemuserBase`) | Aylık | Masaüstü |
| Finans / maliyet onaycısı | Mali İşler (CRM ekip üyeliği: 10 kişi); marj onayı **varsayım** | Kampanya başına | Masaüstü |
| Telif birimi | Sözleşmelerde "Telif Hakları" iş akışı adımı var (kanıt); asgari perakende fiyat ve telif hesap tipi sözleşmede | Sorun çıktıkça | Masaüstü |
| Depo / stok sorumlusu | Depo — **varsayım** | Kampanya öncesi ve sırasında | Telefon |
| Pazarlama müdürü (onay) | Yönetim | Kampanya başına | Telefon ve masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Pazarlama uzmanı.** Platformun kampanya çağrısı e-postayla ya da satıcı panelinden gelir. Kitap listesi ve indirim
  oranı Excel'de hazırlanır, onay e-postayla alınır (**varsayım**). Pazarlama bütçesi CRM'deki "Pazarlama Bütçe Modülü"nde
  izleniyor (435 kayıt; tip seçenekleri arasında "Satış Kampanyası" ve "Dijital Pazarlama", mecra seçenekleri arasında
  Stant, B2B, Vade ve İskonto kampanyası var; kanıt). Kampanya sonucu ayrıca raporlanmıyor, çünkü planlanan ve gerçekleşen
  ciro alanları boş (kanıt).
- **Satış müdürü.** Bayi kampanyasını CRM'de tanımlar: başlangıç-bitiş, ek iskonto, net iskonto, asgari alışveriş, hediye,
  ödeme vadesi. Kampanya carilere bağlanır (kampanya ↔ cari 318.631 bağ) ve siparişte uygulanır (sipariş satırında kampanya
  kodu, indirim oranı ve tutarı). CRM'de 50.000 kupon kodu var (`new_kuponkodlariBase`). Son 30 günde 3 kampanya değişmiş
  (2026-09-15), yani modül kullanılıyor ama seyrek.
- **Finans.** Marjı Logo'dan ayrıca hesaplar (**varsayım**). Maliyeti girilmemiş satırlar bu hesabı bozar.
- **Telif birimi.** Kampanya fiyatının sözleşmedeki "Minimum Perakende Satış Fiyatı"nın altına inip inmediği ya da telifi
  perakende fiyattan hesaplanan kitapta indirimin telife etkisi kampanyadan önce kontrol edilmiyor olabilir (**varsayım**;
  alanlar sözleşmede var: `new_MinimumPerakendeSatFiyat`, `new_HesaplamaTipi` = Toptan satış fiyatı / Perakende fiyatı /
  Perakende oranlı).
- **Sıkıntı.** Karar Excel'de, sonuç Logo'da, sözleşme sınırı CRM'de duruyor ve üçünü birleştiren bir yer yok.

## 4. İhtiyaçlar ve acı noktaları

**Pazarlama uzmanı**
1. Kampanyaya aday kitaplar: stoku yeterli, hakkı ve yayın durumu uygun, marjı indirimi kaldıran, sezona uyan kitaplar.
2. "Yüzde X indirimde bu kitap ne bırakır" simülasyonu: marj, telif etkisi ve sözleşme sınırı birlikte.
3. Kampanya takvimi: platform dönemleri, özel günler, fuarlar ve çakışmalar.
4. Kampanya bitince önce/sonra satış, iade ve marj özeti.
5. Kampanya metni (başlık, kısa açıklama) taslağı.

**Satış müdürü**
1. Geçmiş bayi kampanyalarının sipariş ve iskonto etkisi (CRM sipariş satırı kampanya kodu + Logo).
2. Hangi carilerin kampanyadan yararlandığı.

**Finans**
1. Maliyeti girilmemiş kitapları kampanyadan önce görmek.
2. Onayladığı indirimin marj alt sınırını aşmadığından emin olmak.

**Depo**
1. Kampanya kitaplarında tükenme tahmini ve yeniden baskı gerekip gerekmediği.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Pazarlama uzmanı olarak bir kampanya taslağı açıp kitap eklediğimde her kitabın mevcut marjını, önerdiğim indirimdeki
  marjını ve telif etkisini görmek istiyorum, çünkü finansa gerekçeyle gitmeliyim.
- Pazarlama uzmanı olarak Zeki AI'ın "stok fazlası, satışı yavaşlamış, sezona uyan" aday kitaplarını gerekçeleriyle görmek
  istiyorum, çünkü listeyi her kampanyada sıfırdan kuruyorum.
- Pazarlama uzmanı olarak kampanya fiyatı sözleşmedeki asgari fiyatın altına düşerse ya da son 30 gündeki en düşük fiyat
  kuralını çiğnerse uyarı almak istiyorum, çünkü hukuki risk taşıyan kampanyayı yayına almamalıyım.
- Satış müdürü olarak geçmiş bayi kampanyalarının siparişe etkisini görmek istiyorum, çünkü yeni kampanyanın iskontosunu
  buna göre koyacağım.
- Finans onaycısı olarak onay bekleyen kampanyaları bir listede, maliyeti eksik satırları işaretli olarak görmek istiyorum,
  çünkü eksik maliyetle onay vermem.
- Depo sorumlusu olarak kampanya kitaplarında tükenme tarihini görmek istiyorum, çünkü kampanya ortasında stok bitmemeli.

**Ana ekranlar ve akış**
- *Kampanyalar* (ilk açılış). Üstte yaklaşan 60 günün takvim şeridi (platform dönemleri, özel günler, fuarlar). Altında
  kampanya listesi durumlarıyla (taslak → onay bekliyor → onaylandı → yürütülüyor → bitti). Her satırda kitap sayısı,
  ortalama indirim, beklenen marj ve uyarı sayısı.
- *Kampanya ayrıntısı*. Kitap tablosu: liste fiyatı, kampanya fiyatı, indirim, mevcut ve kampanyalı marj, telif etkisi,
  stok, tükenme tahmini, kontrol simgeleri. Toplu indirim girişi ve "Zeki AI'dan aday iste" düğmesi.
- *Adaylar*. Kural süzgeçleri ve gerekçe satırları.
- *Sonuç*. Önce/sonra günlük satış, iade, marj ve Zeki AI'ın yazdığı özet.
- Tık sayıları: yeni kampanya açıp 10 kitap eklemek 4 tık + seçim; simülasyon anında; onaya göndermek 1 tık; onaylamak 2 tık
  (liste → onayla).
- Telefonda yürüyen kampanyanın günlük satış kartı ve stok uyarıları okunur. Düzenleme masaüstünde yapılır.

**Zeki AI'a soracakları örnek sorular**
1. "Son 90 günde satışı yarıya düşmüş ama stoku 2.000'in üstünde olan kitaplar hangileri?"
2. "Bu kampanyada yüzde 35 indirim yaparsak toplam brüt marjımız ne olur?"
3. "Geçen yılki Kasım bayi kampanyasında kampanya kodlu siparişlerin tutarı ne kadardı?"
4. "Anneler Günü'ne bağlı kitaplarımızdan hangilerinin stoku kampanyaya yeter?"
5. "Maliyeti girilmemiş hangi kitaplar bu kampanyada?"
6. "Kampanya bittikten sonraki iki haftada iade arttı mı?"
7. "Telifi perakende fiyattan hesaplanan kitaplarda yüzde 40 indirim telif ödemesini nasıl etkiler?"

**Otomasyon katmanı**
- K1: Takvim ve özel gün tarihleri (`seasons.py` kuralları), aday puanları, marj ve kontroller her gece hesaplanır. Yürüyen
  kampanyanın günlük sonucu otomatik gelir.
- K2: Aday kitap listesi, indirim önerisi ve kampanya metni Zeki AI'dan gelir. Katılım kararı ve indirim oranı insan
  onayındadır (iş tanımıyla aynı).
- K3: Kampanya stratejisi (hangi platform, hangi dönem) için Zeki AI geçmiş sonuçları özetler, ekip karar verir.
- K4: Platforma kampanya başvurusu ve T-soft'ta kampanya kurulumu insan tarafından yapılır. Modül hiçbir platforma
  başvuru göndermez.
- İş tanımındaki "saatlik izleme" bu sürümde yapılamaz: Logo kopyası donmuş ve günlük; saatlik site verisi ancak T-soft
  sipariş okumasına kişisel veriyi atan bir toplama katmanı kurulunca gelir.

**Bildirim / uyarı**
- Uzmana: onay kararı çıktığında (onaylandı ya da geri gönderildi) e-posta.
- Onaycıya: onay bekleyen kampanya olduğunda e-posta.
- Uzmana ve depoya: yürüyen kampanyada tükenme tahmini kampanya bitişinden önceye düştüğünde e-posta.
- Uzmana: kampanya bitiminden sonraki gün sonuç özeti hazır bildirimi.

**Onay ve yetki**
- `sayfa:kampanya`: listeyi ve sonuçları görür.
- `ozellik:kampanya.duzenle`: kampanya açar, kitap ve indirim girer.
- `ozellik:kampanya.onay` (explicit): onaylar ya da geri gönderir. Hazırlayan kişi onaylayamaz (M8 hakediş ilkesi).
- `ozellik:kampanya.metin-uret`: Zeki AI metni üretir (model harcar).
- `ozellik:veri.disa-aktar` (var): brifi ve kitap listesini indirir.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kitap bazında satış hızı (adet, net tutar) | Logo `V_SatisRaporu_411` (2026), `V_SatisRaporu_211` + `Yıl=` (2021–2025); faturalı satır | Kullanılıyor (baskı önerisi, hakediş) | Son fatura 2026-08-17 (donmuş kopya) |
| Maliyet ve marj | Logo `LG_411_01_STLINE` (`LINENET`, `AMOUNT × OUTCOST`); ölçü `brut_kar_marji`, kâr tanımı (iş teyidi bekliyor) | 2026 satırlarının %20'sinde `OUTCOST = 0` (ölçüm 2026-09-16) | Maliyetsiz kitaplar simülasyonda "hesaplanamaz" olarak işaretlenmeli |
| İskonto | Logo `STLINE LINETYPE = 2`; ölçü `iskonto_yuku` | Tanımlı | — |
| Stok ve tükenme tahmini | Logo stok (STLINE bakiyesi ya da `LV_411_01_STINVTOT`); baskı önerisi tahmini | Baskı önerisi 5.053 kitapta stoku birebir doğruladı | Canlı stok yok (donmuş kopya) |
| Bayi kampanyaları | CRM `new_kampanyaBase` (308), `new_kampanyaliurunBase` (6), `new_new_kampanya_accountBase` (318.631), `new_kuponkodlariBase` (50.000) | Alanlar biliniyor | Etkin kampanya sayısı ve kupon kullanımı **ölçülecek**. Katalog notu (4 kampanya) ile tablo (308 satır) arasındaki fark açıklanacak |
| Siparişte kampanya kullanımı | CRM `new_siparissatiriBase.new_kampanyakodu`, `new_kampanyaindirimorani`, `new_kampanyaindirimtutari`, `new_kampanyaid`; `new_siparisBase.new_isbtobcampaignorder` | Alanlar biliniyor | Doluluk **ölçülecek** |
| Pazarlama bütçesi | CRM `new_pazarlamamoduluBase` (435; tip, mecra, tutar, tarih) | Alanlar biliniyor | Kampanyaya bağ alanı yok; eşleme adla ya da tarihle |
| Sözleşme sınırları | CRM `new_sozlesmeBase.new_MinimumPerakendeSatFiyat`, `new_HesaplamaTipi`, `new_TelifTipi`, `new_telifturu`; telif oranı M6 terimlerinden (`contracts_terms.py`) | M6 kodunda okunuyor | Doluluk **ölçülecek** |
| Özel günler ve bağlı kitaplar | CRM `new_ozelgunlerBase` (93), `new_new_kitap_new_ozelgunlerBase` (820 bağ); `seasons.py` tarih kuralları | Kodda var (SEO sezon takvimi) | — |
| Site kampanyası, kuponu, fiyat geçmişi | T-soft (yalnız okuma) | Kampanya/kupon okuma yöntemleri **ölçülecek**; fiyat geçmişi yok | Son 30 günün en düşük fiyatı için günlük fiyat anlık görüntüsü bizim tarafta tutulmalı |
| Sitede günlük/saatlik sipariş | T-soft `order/get` (62.903 sipariş) | Kişisel veri içeriyor; SEO modülü kullanmıyor | Kişisel alanları atan toplama katmanı gerekir (KVKK) |
| Platform kampanya takvimi ve koşulları | Platform satıcı panelleri (dış) | Yok | Kullanıcı girer |
| Platformda okura satış, reklam bütçesi, tıklama | Platform raporları (dış) | Yok | İzinli kanal ya da dosya yükleme |

## 7. Diğer modüllerle bağ

- Girdi alır: M34 (ürün aktifliği, stok farkı, kart doluluğu), M9 Fiyatlama (liste fiyatı, maliyet), M6/M54 Telif (asgari
  fiyat, telif hesap tipi), M11 Baskı Tekrarı (tükenme tahmini), M25 SEO sezon takvimi, M27 Fuar ve Etkinlik (fuar
  tarihleri), M46 Bütçe (kampanya bütçesi).
- Çıktı verir: M40–M42 (platforma özel uygulama), M24 Katalog ve Bülten (kampanya duyurusu), M21 Dijital Reklam
  (sponsorlu ürün brifi), M45 Finansal Raporlama (kampanya sonucu), M53 Set ve Promosyon (set önerileri), DYK.
- Sınır: bayi kampanyası kanalının işletimi M30/M32'ye aittir. M35 bayi kampanyasını yalnız okur ve kampanya kararı ile
  sonucu için ortak kayıt defteri sunar.

## 8. Kısıtlar

- T-soft'a yazma yasak. Site kampanyası T-soft panelinde elle kurulur, modül yalnız kaydeder ve izler.
- CRM'e yazılmaz. Kampanya kaydı köprünün tablolarındadır. CRM'deki bayi kampanyası okunur; portalda açılan kampanyanın
  CRM'e işlenmesi gerekiyorsa ekranda "CRM'e işlenecek" diye gösterilir (M6 deseni).
- Müşteride web taraması kapalı. Rakip kampanya fiyatları kazınmaz (M39'a bakın).
- Ekranda teknoloji adı yok, "Zeki AI" yazılır. Demo veri yok, sayı tavanı yok.
- Logo verisi donmuş kopyadan geliyor; kesim tarihi her rakamın yanında yazar. "Saatlik" iddia edilmez.
- Hukuk (teyit edilmeli):
  - İndirim duyurusunda indirim öncesi fiyatın son 30 gün içindeki en düşük fiyat olması kuralı (Ticari Reklam ve Haksız
    Ticari Uygulamalar Yönetmeliği). Modül kendi günlük fiyat kaydıyla kontrol eder; hukuk birimi teyit etmeli.
  - Sözleşmedeki asgari perakende fiyat ve telif hesap tipi.
  - Çekilişli kampanyalar ayrı izne tabi olabilir.
  - Kampanya iletisi kişiye gidecekse KVKK ve İYS (M37/M38).
- KVKK: T-soft siparişleri kişisel veri içerir. İlk sürümde okunmaz; okunursa yalnız ürün × gün toplamı saklanır, ad, adres,
  e-posta ve telefon hiç saklanmaz (`seo_geo/reviews.py` ilkesi).
- Zeki AI sohbeti bugün yalnız finans sorularını cevaplıyor (`chat_scope.py`). Kampanya soruları çoğunlukla finanstır, ama
  kapsam kontrol edilmeli.

## 9. Kapsam önerisi

**İlk sürüm**
- Kampanya kayıt defteri (kanal: site / pazar yeri / bayi / fuar), durum akışı ve onay.
- Kitap bazında indirim simülasyonu: Logo marjı, telif etkisi, sözleşme asgari fiyatı, son 30 gün en düşük fiyat kontrolü,
  maliyeti eksik uyarısı.
- Aday kitap listesi: stok, satış hızındaki düşüş, sezon bağı, hak ve yayın durumu, marj.
- Takvim: özel günler (`seasons.py`), kullanıcının girdiği platform dönemleri, fuarlar.
- Sonuç özeti: günlük önce/sonra satış, iade, marj (Logo) ve Zeki AI özeti.
- Geçmiş bayi kampanyalarının okunması (CRM) ve kampanya kodlu sipariş etkisi.

**Sonraki sürüm**
- T-soft sipariş toplama katmanı (kişisel veri atılarak) ile sitede gün içi izleme.
- Platform raporlarının yüklenmesi (reklam bütçesi, tıklama, okura satış).
- Set ve çapraz satış önerisi (birlikte alınan kitaplar). Okur bazında sepet verisi olmadığı için önce bayi sipariş
  satırlarından.
- Kampanya öğrenim kaydı: indirim oranı ile satış artışı ilişkisi.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/seasons.py` (özel gün tarihleri ve bağlı kitaplar).
- `backend/semantic_bridge/contracts_terms.py`, `contracts_royalty.py` (telif hesap tipleri ve oranları, Logo satış
  görünümü okuması).
- Baskı önerisi tahmini (`/yonetim-raporlari/baski-oneri`, `docs/analiz/timesfm-baski-oneri/`).
- `alerts.py`, `reports.py`, `access.py`, `admin.py` audit.
- Onay deseni: `freelance.py` hakediş (hazırlayan onaylayamaz).

## 10. Uzmanlara sorulacak sorular

1. (Pazarlama) Site ve pazar yeri kampanyalarını bugün kim, hangi araçla planlıyor ve onayı kim veriyor?
2. (Satış) Pazar yeri kampanyalarında indirimi platform mu karşılıyor, yoksa Timaş fiyat desteği mi veriyor? Bu destek
   Logo'da nasıl kaydediliyor (iskonto satırı, fiyat farkı faturası)?
3. (Finans) Kampanya onayında kabul edilen en düşük marj ne? Maliyeti girilmemiş kitapta nasıl karar veriliyor?
4. (Hukuk / telif) Kampanya fiyatında sözleşmedeki asgari perakende fiyata ve 30 gün kuralına bugün bakılıyor mu?
5. (Satış) CRM'deki 50.000 kupon kodu ne için üretildi ve hâlâ kullanılıyor mu?

## 11. Başarı ölçütü

- Kampanya hazırlama süresi (taslak açılışından onaya): ilk ay taban ölçülür, sonra izlenir.
- Onaydan sonra fark edilen kontrol hatası (asgari fiyat, maliyet eksik, stok yetmedi) sayısı: hedef 0.
- Kampanya sonucu raporunun kampanya bitiminden sonraki ilk iş günü hazır olma oranı.
- Kullanım: kampanyaların ne kadarının modülden açıldığı (Excel yerine).
- Zeki AI aday listesinden seçilen kitap oranı. Düşükse aday kuralları gözden geçirilir.

## 12. Uzman gözüyle en iyi sistem

*15 yıllık bir e-ticaret kampanya müdürünün gözünden (uzman görüşü, TİMAŞ verisine dayanmaz).*

Güçlü perakendeciler ve yayınevleri kampanyayı bir takvim ve bir P&L tablosu olarak yönetir. Her kampanyanın bir "kâr ve
zarar kartı" vardır: indirimin maliyeti, beklenen ek satış, stok kapasitesi, telif ve kanal payı. Fiyat ve promosyon
yazılımları geçmiş kampanyalardan indirim esnekliğini ölçer ("%30 indirim bu tür kitapta satışı kaç kat artırdı") ve bir
sonraki önerinin gerekçesini bu ölçümden kurar. Kampanya sonrası "öğrenilen" kaydı zorunludur. Yayıncılıkta ek olarak
telif (indirimli perakende fiyattan mı ödeniyor) ve baskı kapasitesi (tükenen kitap yeniden basılabilir mi) hesaba katılır.

TİMAŞ için mükemmel sistem: her kampanya önce kitap listesiyle bir simülasyondur. Sistem stoku, marjı, telifi ve hukuki
sınırları kitap kitap söyler. Onaydan sonra kampanya yürür, günlük sonuç gelir, bitince kampanya kendi öğrenim satırını
yazar. Bir sonraki kampanyada Zeki AI "benzer kampanyada benzer kitap şu kadar sattı" diye gerekçe gösterir.

**Uzmanın bir günü (sistemle)**
- 09:00 Telefonda "Yürüyen kampanya: dün 3 kitapta satış arttı, 1 kitapta stok 6 gün içinde bitecek" bildirimi.
- 09:15 Masaüstünde *Kampanyalar*. Takvim şeridinde 3 hafta sonra platformun kampanya dönemi ve aynı haftada Öğretmenler
  Günü. "Yeni kampanya" açar, kanal olarak pazar yerini ve tarihleri girer.
- 09:30 "Zeki AI'dan aday iste": 40 aday gelir, her biri gerekçeli ("stok 18 ay yeter, satış hızı %45 düştü, Öğretmenler
  Günü'ne bağlı"). 25'ini seçer.
- 10:00 Toplu %30 indirim girer. 3 kitap kırmızı: biri sözleşme asgari fiyatının altında, ikisinin maliyeti yok. Asgari
  fiyatlı kitabı %20'ye çeker, maliyetsiz ikisini çıkarır.
- 10:20 "Metin üret": kampanya başlığı ve üç kısa açıklama gelir, birini düzenler. Onaya gönderir.
- 14:00 Finanstan onay e-postası gelir. Brifi Excel olarak indirip platform temsilcisine gönderir, kampanyayı panelde kendisi
  kurar.
- 17:00 Geçen haftaki bitmiş kampanyanın sonuç sayfası: satış %X arttı, iade değişmedi, marj beklenenin 2 puan altında.
  Zeki AI'ın özetine bir cümle ekleyip "öğrenim" olarak kaydeder.

**"Bunu görürsem hemen kullanırım"**
1. İndirim girer girmez kitap kitap marj, telif ve asgari fiyat kontrolü.
2. Gerekçeli aday listesi: "neden bu kitap" tek satırda.
3. Kampanya bitince kendiliğinden gelen sonuç özeti.

**"Bunu yaparsanız kullanmam"**
1. Maliyeti eksik kitapta marjı sıfır ya da yanlış göstermek. "Hesaplanamaz" demeli.
2. Platform başvurusunu sistemden yaptığını sanmak ya da sahte "gönderildi" durumu göstermek.
3. Saatlik izleme vaat edip bir gün önceki veriyi göstermek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Aday kitap süzgeci | `V_SatisRaporu_411/211` (kitap × ay adet ve net), stok bakiyesi (`LG_411_01_STLINE`) | `new_kitapBase` (yayın durumu, `new_tsoftaktif`), hak özeti (`semantic_seo_crm_books`), özel gün bağı | — | Süzgeç kurallıdır (hız düşüşü, stok ay sayısı, hak, sezon) |
| Aday gerekçesi ve sıralama açıklaması | Aynı rakamlar | Aynı | Kısa gerekçe cümlesi yazar ("stok 18 ay yeter, satış %45 düştü") | Rakam SQL'den gelir, model yalnız cümleye döker |
| Marj simülasyonu | `LG_411_01_STLINE` (`LINENET`, `AMOUNT × OUTCOST`, `LINETYPE = 0`, `TRCODE 7,8,9`, `INVOICEREF <> 0`); `brut_kar_marji`; iskonto `LINETYPE = 2` | — | — | Hesap deterministiktir |
| Telif etkisi ve asgari fiyat | — | `new_sozlesmeBase` (`new_SozlesmeTipi = 5`, `new_HesaplamaTipi`, `new_MinimumPerakendeSatFiyat`, `new_TelifTipi`), kitap ↔ sözleşme `new_new_sozlesme_new_kitapBase` | — | Kurallı kontrol (M6 terimleri) |
| 30 gün en düşük fiyat kontrolü | — | — | — | Bizim günlük fiyat anlık görüntümüzden (`semantic_kampanya_price_snapshots`) |
| Takvim | — | `new_ozelgunlerBase`, `new_new_kitap_new_ozelgunlerBase` | — | `seasons.py` kuralları |
| Kampanya metni (başlık, kısa açıklama, banner metni) | — | Kitap adı, yazar, `new_kitapspotu` | Taslak metin üretir, uzunluk sınırına uyar | Modelin değer kattığı yer. Onay insanda |
| Geçmiş bayi kampanyası sınıflaması (tür: iskonto / vade / hediye / stant) | — | `new_kampanyaBase.new_name`, `new_aciklama`, alanlar | Kapalı küme sınıflama (tek token + olasılık). Ad serbest metinse işe yarar | Öğrenim kaydını türe göre gruplamak için |
| Kampanya sonucu | `LG_411_01_INVOICE`/`STLINE` kampanya dönemi ile önceki eşit dönem; iade `TRCODE 2,3` | Kampanya kodlu sipariş satırları | Sonuç özeti yazar (rakamları yorumlar, uydurmaz) | Yönetime giden metin |
| Doğal dil soru | `net_ciro`, `iskonto_yuku`, `brut_kar_marji`, `iade_orani` | Katalogdaki CRM tabloları | Soru → SQL (mevcut hat) | — |

Model yalnız `rt.llm_for("kampanya", priority)` ile çağrılır. Sınıflamada `structured_outputs.choice` + logprobs; düşük
marjlı sınıf "belirsiz" sayılır.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/kampanya.py`: depo ve iş kuralları (durum akışı, kontroller).
- `backend/semantic_bridge/kampanya_sources.py`: Logo okumaları (yıllık görünüm, `Yıl*12+Ay`, kod listesi
  `JOIN (VALUES …)` ile; ALL2 kullanılmaz), CRM okumaları (`connector_from_file`), `seasons.py` çağrısı.
- `backend/semantic_bridge/kampanya_api.py`: `register(app, rt=..., can=..., audit=...)`.

**Tablolar** (`semantic_kampanya_` öneki)
- `semantic_kampanya_campaigns` (id, tenant_id, ad, kanal [site|pazar_yeri|bayi|fuar], platform, baslangic, bitis,
  durum [taslak|onay_bekliyor|onaylandi|yurutuluyor|bitti|iptal], hazirlayan, onaylayan, onay_notu, crm_kampanya_id,
  butce, notlar, olusturma, guncelleme)
- `semantic_kampanya_items` (campaign_id, stok_kodu, ean, ad, liste_fiyati, kampanya_fiyati, indirim_orani, stok,
  tukenme_tahmini, marj_once, marj_sonra, telif_etkisi, maliyet_eksik, kontroller_json, aday_gerekcesi)
- `semantic_kampanya_calendar` (id, tur [platform|ozel_gun|fuar], ad, baslangic, bitis, platform, kaynak [kullanici|crm],
  not)
- `semantic_kampanya_results` (campaign_id, gun, stok_kodu, adet, net_tutar, iade_adet, kaynak, logo_kesim)
- `semantic_kampanya_learnings` (campaign_id, ozet, tur, indirim_orani, satis_degisimi, yazan, tarih)
- `semantic_kampanya_price_snapshots` (tarih, product_key, fiyat, kaynak [tsoft|crm]); her gece `semantic_seo_products`'tan
  kopyalanır.

**Uçlar** (`/api/v1/kampanya/*`)
- `GET overview` · `GET calendar?from=&to=` · `POST calendar` · `DELETE calendar/{id}`
- `GET campaigns?durum=` · `POST campaigns` · `GET campaigns/{id}` · `PATCH campaigns/{id}`
- `POST campaigns/{id}/items` (toplu ekle) · `PATCH campaigns/{id}/items/{stok_kodu}` · `POST campaigns/{id}/simulate`
- `POST campaigns/{id}/submit` · `POST campaigns/{id}/decision` (onay/geri gönder)
- `GET candidates?campaign_id=&kurallar=` · `POST campaigns/{id}/copy` (Zeki AI metni)
- `GET campaigns/{id}/results` · `GET crm-campaigns?page=` (CRM bayi kampanyaları, salt okunur)
- `GET campaigns/{id}/export` · `POST run-due` (sistem jetonu)

**Ekranlar**: `src/canvas/kampanya/` → `CampaignsScreen.tsx`, `CampaignDetail.tsx`, `CandidatesPanel.tsx`,
`ResultsScreen.tsx`. Rotalar `/timas/kampanyalar`, `/kampanyalar/:id`, `/kampanyalar/adaylar`, `/kampanyalar/takvim`.
Menü: `navModel.ts` Pazarlama alanı, "E-ticaret" bölümü (M34 ile aynı bölüm). Kampüs: `ModulesMenu.tsx` `LIVE`
içine `M35: '/kampanyalar'`.

**Yetki**: `sayfa:kampanya`; `ozellik:kampanya.duzenle`, `ozellik:kampanya.onay` (**explicit**; hazırlayan onaylayamaz,
köprüde de denetlenir), `ozellik:kampanya.metin-uret`; mevcut `ozellik:veri.disa-aktar`.

**Zamanlayıcı**: `scripts/server/timas-kampanya.timer`, her gece 05:00. Fiyat anlık görüntüsü, aday puanları, yürüyen
kampanyaların günlük sonucu ve tükenme uyarısı, biten kampanyanın sonuç özeti. Logo kopyası tazelenmediği sürece sonuç
satırı "kesim tarihi" ile yazılır. İlk tur elle koşturulur.

**Kabul testleri** (doğrudan bağlantıyla)
1. Kitap marjı: 10 stok kodu için `SELECT SUM(s.LINENET) - SUM(s.AMOUNT * s.OUTCOST) FROM LG_411_01_STLINE s
   JOIN LG_411_ITEMS it ON it.LOGICALREF = s.STOCKREF WHERE it.CODE = :kod AND s.TRCODE IN (7,8,9) AND s.LINETYPE = 0
   AND s.CANCELLED = 0 AND s.INVOICEREF <> 0` = simülasyondaki "mevcut marj" tutarı.
2. Maliyeti eksik satır: aynı süzgeçle `COUNT(*) … AND s.OUTCOST = 0` = ekrandaki uyarı sayısı.
3. Satış hızı: 10 kitap için `V_SatisRaporu_411`'den son 3 tam ay adedi (`Yıl*12+Ay` penceresi) = aday ekranı.
4. CRM bayi kampanyaları: `SELECT new_name, new_baslangictarihi, new_bitistarihi, new_kampanyamecra, new_netiskonto
   FROM dbo.new_kampanyaBase WHERE statecode = 0` = "CRM kampanyaları" sekmesi (satır sayısı ve ilk 20 satır).
5. Kampanya kodlu sipariş: `SELECT new_kampanyakodu, COUNT(*), SUM(new_kampanyaindirimtutari) FROM
   dbo.new_siparissatiriBase WHERE new_kampanyakodu IS NOT NULL AND new_kampanyakodu <> '' GROUP BY new_kampanyakodu`
   = geçmiş kampanya etkisi tablosu.
6. Özel gün bağı: `SELECT COUNT(*) FROM dbo.new_new_kitap_new_ozelgunlerBase` (2026-09-27: yaklaşık 820) ve SEO Sezon
   takvimi ekranıyla aynı gün ve kitap listesi.
7. Asgari fiyat: bir kitabın yürürlükteki Telif Alış sözleşmelerinde `MAX(new_MinimumPerakendeSatFiyat)` = simülasyonun alt
   sınırı. Alan boşsa ekranda "sözleşmede asgari fiyat yok" yazar.

**Bağımlılık**: M34 `semantic_eticaret_items` (stok, aktiflik) önce biterse aday süzgeci onu okur; bitmezse doğrudan Logo'dan
okur, iki modül paralel kodlanabilir. M6 terim okuması hazır. Baskı önerisi tahmini okunur (değiştirilmez).

**Tahmini büyüklük**: L (3+ gün). Simülasyon ve kontroller M, ekranlar M, sonuç ve öğrenim S.
