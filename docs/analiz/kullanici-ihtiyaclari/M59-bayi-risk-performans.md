# M59 — Kitapçı/Bayi Risk ve Performans Yönetimi: kullanıcı ihtiyaç analizi

Durum: kodlandı, dalda (2026-09-28; sunucuda doğrulanmadı — kararlar ve plandan sapmalar günlükte) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M59.txt`, `specs/M30.txt`, `specs/M31.txt`,
`specs/M46.txt`; Veri Haritası (`veri_haritasi2.txt`: «Bayi & Alacak Verileri», «Bölge & Pazar Girdileri»); `PROJECT-MEMORY.md`
(Vade/yaşlandırma, Satış = faturalı satır); `configs/semantic/knowledge/logo/knowledge/{caveats,metrics,glossary}/logo-timas.md`,
`configs/semantic/knowledge/logo/knowledge/sql/{vadesi-gecmis-yaslandirma-fifo,vadesi-gecmis-toplam-fifo,ortalama-tahsilat-suresi-dso,planlanan-odeme-vadesi,en-cok-iade-alan-10-musteri-kimler}.md`;
`configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`, `table_descriptions.json` (`AccountBase`, `new_siparisBase`,
`new_tahsilatBase`, `new_etkinlikBase`, `new_ziyaretyerleriBase`, `new_illerBase`, satış hedefleri);
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`; `backend/semantic_bridge/budget.py` (M46 bölge/bayi hedefi sözleşmesi),
`access.py`, `access_catalog.json`; kullanıcı belleği: live-bi-numbers-2026, sales-are-invoiced-lines, system-of-record-logo,
logo-155-frozen-copy, timas-alerts, crm-systemuser-directory, no-tech-names-on-screens.

## 1. Modül ne işe yarar

İş tanımına göre M59 üç iş yapar: (1) her bayi/kitapçı için **günlük risk skoru** (ödeme gecikmesi × sipariş düzensizliği ×
iade oranı), 30/60/90+ gün alacak izleme, ödeme davranışı eğilimi (K1); (2) **performans analizi ve aksiyon** — satış
hacmi, büyüme, kategori karması, düşük performanslı bayi, riskli bayide **kredi limiti revizyon önerisi**, saha ziyareti
öncesi risk brifi (M30) (K2, satış yöneticisi onaylar); (3) **bayi ağı boşluğu** — bölge kapsama haritası, M31 okul için
bayi önerisi, yeni bayi adayı, ziyaret öncelik sırası (K2/K3).

TİMAŞ'ın bugünkü sorunu (kanıta dayalı): Satış toptan ağırlıklı (2026'da TRCODE 8 toptan 874,6 Mn ₺ / 21.009 fatura;
`live-bi-numbers-2026`), yani bayi/kitapçı alacağı şirketin ana riski. Ancak: Logo'da **ödeme kapama kullanılmıyor**
(PAYTRANS 116.514 plan satırının 14'ünde ödenen tutar dolu) → hangi faturanın ödendiği bilinmiyor, gecikme yalnız FIFO ile
yaklaşık; Logo'da **risk limiti hiç tanımlı değil** (`ACCRISKLIMIT > 0` olan cari yok); limit ve risk alanları ise
**CRM cari kartında** duruyor (açık hesap, çek/senet, toplam limit ve risk; «Sorunlu Müşteri» durumu; `CreditOnHold`) ve
CRM siparişi limite takılınca «Risk Limit Onayı Bekliyor» durumuna düşüyor (`new_siparisBase`). Yani risk süreci bugün
CRM'de sipariş anında işliyor, ama **skor, eğilim, yaşlandırma ve performans bir arada hiçbir yerde yok.**

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Satış müdürü / bölge satış şefi (K2 onaylayan) | Satış — **kanıt**: CRM `new_gorevbirimi` 4 = Satış; bölge listesi (Babıali, Ege, İstanbul, D&R, Kitapyurdu… 15 bölge, satış hedefleri) | Her gün | İkisi de |
| BMT (saha temsilcisi) | Satış sahası — **kanıt**: CRM kullanıcı tipi 1 = BMT; cari kartında sahip alanının etiketi «BMT», «BMT İl veya Cari», il → müşteri temsilcisi (`new_illerBase.new_musteritemsilcisi`) | Her gün, ziyaret öncesi | **Telefon** |
| Merkez müşteri temsilcisi | Satış iç destek — **kanıt**: `AccountBase.new_MerkezMusteriTemsilcisi` | Her gün | Masaüstü |
| Cari hesaplar / tahsilat uzmanı | Muhasebe — **kanıt**: CRM tahsilat kaydı onay akışı (Onay Bekliyor → Onaylandı → Logoya Aktarıldı), onaylayan/reddeden alanları | Her gün | Masaüstü |
| Risk limiti onaylayıcısı | **Kanıt (rol var)**: `new_siparisBase.new_risklimitionaylayanid / reddedenid`; kimler olduğu **ölçülecek** | Sipariş limite takılınca, anlık | Telefon |
| Finans müdürü / CFO | Finans — **varsayım** | Haftalık | İkisi de |
| Genel müdür (K3: bayi ağı yapısı) | Üst yönetim — **varsayım** | Aylık | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

- **Sipariş anı (kanıt):** CRM'de sipariş girilir; cari limitini aşarsa `new_siparislimitetakildi`, «riske takılma sebebi»
  (açık hesap limiti / çek-senet limiti / toplam limit / sorunlu müşteri), anlık limit ve anlık risk yazılır, sipariş
  «Risk Limit Onayı Bekliyor» olur; yetkili onaylar ya da reddeder. Tıkanma: onaylayan kişi o anda carinin gecikme
  eğilimini, iade oranını, son tahsilatını tek bakışta görmüyor (**varsayım**; CRM ekranında bu bileşik görünüm yok).
- **Tahsilat (kanıt):** BMT sahada çek/senet/nakit/POS tahsilatını CRM'e girer (14.089 kayıt), muhasebe onaylar ve Logo'ya
  aktarır; ret nedenleri kodlu (şekil şartı eksikliği, makbuz-evrak uyumsuzluğu, vade uyumsuzluğu).
- **Yaşlandırma:** Logo'da kapama yok; muhasebe muhtemelen cari ekstre + Excel ile yaşlandırıyor (**varsayım**).
  Portalda Zeki AI'a sorulduğunda FIFO yaklaşık yaşlandırma veriliyor (bilgi paketi sorgusu var).
- **Ziyaret (kanıt):** CRM etkinlik kayıtlarının çoğu satış ziyareti (`new_ziyarettipi` «Cari Ziyareti», `new_ziyaretsekli`
  «Cari ile Ziyaret»); okul ziyaretlerinde «Aracı Müşteri» (`new_AracMteriId`) alanı okulun hangi bayi üzerinden aldığını
  tutuyor. Ziyaret öncesi bayi durumu için BMT'nin merkeze telefon ettiği **varsayım**.
- **Performans:** Bölge × kitap × ay satış hedefi CRM'de var (334.982 satır), ama kişiye/cariye bağı zayıf; bayi bazlı
  hedef-gerçekleşme M46 ile yeni geliyor.

## 4. İhtiyaçlar ve acı noktaları

**Satış müdürü**
1. Bütün bayileri tek listede risk segmentiyle (A/B/C/D) ve eğilimiyle (iyileşiyor/kötüleşiyor) görmek.
2. Limit revizyonu önerisini gerekçesiyle görmek ve onaylamak; CRM'e ne işleneceğinin net listesi.
3. Düşük performanslı bayide nedeni: satış mı düştü, iade mi arttı, kategori karması mı kaydı.
4. Bölge bazında kapsama: hangi il/ilçede bayi yok ya da zayıf.

**BMT**
1. Ziyaretten önce telefonda tek sayfa: bakiye, vadesi geçmiş (kovalarıyla), son tahsilat, bekleyen sipariş, iade, son
   ziyaret notu, «bu ziyarette konuşulacaklar».
2. Kendi carilerinin tahsilat öncelik sırası.

**Tahsilat uzmanı**
1. 30/60/90+ kovaları cari bazında, yaklaşık olduğu açıkça yazılı.
2. Karşılıksız/iade çek olayı olan cariler.

**Risk limiti onaylayıcısı**
1. Limite takılan siparişte tek ekranda skor, bileşenler ve önerilen karar.

**CFO / genel müdür**
1. Alacak yoğunlaşması (ilk 10 cari payı), segment dağılımının ay ay değişimi, beklenen tahsilat.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- Satış müdürü olarak sabah «kötüleşen bayiler» listesini görmek istiyorum, çünkü sorun büyümeden aramalıyım.
- Satış müdürü olarak Zeki AI'ın limit revizyon önerisini gerekçesiyle onaylamak ya da reddetmek istiyorum, çünkü karar
  benim ama hazırlığı uzun sürüyor.
- Satış müdürü olarak bölge haritasında bayisiz ilçeleri ve oradaki okul sayısını görmek istiyorum, çünkü yeni bayi
  arayışını oraya yöneltmeliyim.
- BMT olarak ziyaretten önce telefonda bayinin risk brifini açmak istiyorum, çünkü tahsilatı ve yeni siparişi aynı
  görüşmede konuşacağım.
- BMT olarak ziyaret sonrası kısa not bırakmak istiyorum, çünkü bir sonraki ziyarette ve merkezde herkes aynı bilgiyi görsün.
- Tahsilat uzmanı olarak vadesi geçmiş alacağı kovalarıyla, eski bakiyeyi ayrı görmek istiyorum, çünkü hangi cariyi önce
  arayacağımı bilmeliyim.
- Risk limiti onaylayıcısı olarak limite takılan siparişin carisini skor bileşenleriyle görmek istiyorum, çünkü telefonda
  30 saniyede karar veriyorum.
- CFO olarak segment dağılımının son 6 ayını görmek istiyorum, çünkü karşılık ve nakit planına girer.

### Ana ekranlar ve akış

Öneri: yeni sayfa **«Bayi riski»** (`/bayi-risk`). Menüde yeni bir «Satış» alanı yoksa Finans alanına girer (satış
müdürünün de gördüğü bir alan olduğu için ileride «Satış» alanına taşınabilir).

1. **Pano** (ilk açılış): segment dağılımı (A/B/C/D, geçen aya göre değişim), vadesi geçmiş toplam ve kovalar (yaklaşık
   rozeti), «kötüleşenler» (segmenti düşen), «onay bekleyen limit önerileri», veri son günü.
2. **Bayiler**: liste — cari, kanal (Logo `SPECODE2`), bölge, BMT, bakiye, vadesi geçmiş, skor, segment, eğilim oku;
   süzgeçler (segment, kanal, bölge, BMT). BMT açtığında varsayılan süzgeç «benim carilerim».
3. **Bayi kartı**: skor ve bileşenleri (her biri açıklamalı), 12 ay satış/iade/tahsilat seyri, yaşlandırma, çek/senet
   olayları, CRM limit/risk alanları, son siparişler ve risk onay geçmişi, ziyaret notları, **Risk brifi** düğmesi
   (telefona uygun tek sayfa), aksiyonlar.
4. **Limit önerileri**: önerilen / mevcut (CRM) / gerekçe; onay → «CRM'e işlenecek» listesi (portal CRM'e yazmaz).
5. **Kapsama**: il → ilçe tablosu (bayi sayısı, satış, okul sayısı, aracı bayi) + harita (ikinci sürüm); okul için bayi
   önerisi (M31).
6. **Kurallar**: skor ağırlıkları ve segment eşikleri, sürümlü (taslak → onay → yürürlükte; M2 kural tablosu deseni).

En sık üç işlem:
- «Kötüleşen bayilere bakmak»: Pano'daki kart = **1 dokunuş**, bayi kartı **2**.
- «Ziyaret öncesi brif» (BMT, telefon): Bayi riski → ara → «Risk brifi» = **3 dokunuş** (son açılanlar listesiyle 2).
- «Limit önerisini onaylamak»: Pano'daki onay kartı → öneri → «Onayla» = **3 dokunuş**.

### Zeki AI'a soracakları örnek sorular

- «Ege bölgesinde vadesi 60 günü geçen alacağı olan kitapçılar kimler?»
- «Son 3 ayda iade oranı %20'yi geçen bayiler?»
- «Geçen yıl alıp bu yıl hiç almayan kitapçılar ve geçen yılki cirosu?» (kaybedilen müşteri tanımı bilgi paketinde)
- «Ortalama tahsilat süresi en çok uzayan 10 cari?»
- «Bu yıl karşılıksız çıkan çeki olan müşteriler?»
- «Kitapyurdu'nun alacağı toplam alacağımızın yüzde kaçı?»
- «Konya'da hangi okullar hangi bayi üzerinden alıyor?»
- «Yarın ziyaret edeceğim X Kitabevi hakkında bilmem gerekenler?»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| Günlük skor, segment, eğilim, yaşlandırma | K1 | Kural sürümüyle deterministik; model yok. |
| Kötüleşme ve karşılıksız çek uyarısı | K1 | Uyarılar altyapısı. |
| Ziyaret risk brifi metni | K2 | Zeki AI yazar (sayılar karttan), BMT kullanır. |
| Kredi limiti revizyon önerisi | K2 | Kural önerir + Zeki AI gerekçe cümlesi; satış müdürü onaylar; CRM'e insan işler. |
| Skor ağırlıkları/eşikler | K2 | Taslak → onay (iki göz). |
| Okul-bayi eşleştirme önerisi, yeni bayi adayı | K2 | Satış yöneticisi onaylar. |
| Bölge kapsama stratejisi, bayi ağı yapısı | K3 | Üst yönetim. |

### Bildirim / uyarı

- Satış müdürü: her sabah 08:00 «kötüleşen bayiler + onay bekleyen öneriler» e-postası.
- BMT: kendi carisi segment düşürünce; ertesi gün ziyaret planı olan cari için brif bağlantısı (M30 gelince).
- Tahsilat uzmanı: yeni karşılıksız/iade çek olayı (`CSTRANS`), 90+ kovasına yeni düşen cari.
- CFO: aylık segment ve yoğunlaşma özeti.
- Kanal: e-posta + portal içi; telefon bildirimi yok.

### Onay ve yetki

| Kim | Görür | Değiştirir | Onaylar |
|---|---|---|---|
| Satış müdürü | Bütün bayiler | Aksiyon, not | Limit önerisi, okul-bayi eşleştirmesi, kural |
| BMT | **Yalnız kendi carileri** (CRM `OwnerId` = kendisi, AD GUID bağıyla) | Ziyaret notu, aksiyon durumu | — |
| Tahsilat uzmanı | Bütün bayiler (alacak tarafı) | Not | — |
| Risk limiti onaylayıcısı | Bütün bayiler | — | Limit önerisi |
| CFO / genel müdür | Pano, yoğunlaşma, segment | — | Kural (ikinci göz) |

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Cari listesi, kanal | Logo `LG_411_CLCARD` (`SPECODE2`: KITAPCI, E-TICARET, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR); CRM `AccountBase.new_cariozelKod2` (BAYI dahil), `new_FirmaKanal` | Kanal sözlüğü bilgi paketinde; CRM cari ↔ Logo cari `new_logicalref` %98,6 bağlı | «Bayi/kitapçı» kapsamının hangi kanalları içerdiği karar ister (aşağıda) |
| Cari bakiyesi | Logo `LG_411_01_CLFLINE` (SIGN, AMOUNT, CANCELLED), müşteri `CODE LIKE '120%'` | Tanım bilgi paketinde | Donmuş kopya (17.08.2026) |
| Vade planı, vadesi geçmiş, yaşlandırma | Logo `PAYTRANS` (SIGN 0) | **Kapama yok** → FIFO yaklaşık; sorgu bilgi paketinde | **Kritik boşluk**: gerçek gecikme günü ölçülemez; skorun «ödeme gecikmesi» bileşeni yaklaşık |
| Tahsilat süresi eğilimi | CLFLINE + fatura (DSO yaklaşımı) | Tanım bilgi paketinde | Yaklaşık; cari bazında aylık seri ölçülecek |
| Satış, iade (cari bazında) | Logo `INVOICE` (TRCODE 7,8,9 − 2,3), `STLINE` (faturalı satır) | Sertifikalı ölçüler; «en çok iade alan müşteri» sorgusu var | Hazır |
| Kategori karması | `STLINE` × `ITEMS.SPECODE` (yayınevi), CRM kitap kategorisi | Yayınevi ölçüsü var | Kategori ağacı modülü yok; yayınevi düzeyi ile başlanır |
| Sipariş düzensizliği | Logo `ORFICHE` (sipariş modülü tüm satışı kapsamıyor — bilgi paketi notu); CRM `new_siparisBase` (333 bin) | Tanımlar var | Sipariş aralığı varyansı tanımı kurulacak; CRM siparişi kaynak alınmalı (ölçülecek) |
| Çek/senet olayları | Logo `CSCARD.CURRSTAT`, `CSTRANS.STATUS` (11 karşılıksız, 5/7 protesto) | 2026'da 6 karşılıksız çek olayı, 6,33 Mn ₺ (ölçüldü) | Cari bağı kolonu kabulde ölçülecek |
| Limit ve risk | CRM `AccountBase`: `new_acikhesaprisklimiti`, `new_ceksenet`, `new_toplamrisklimiti`, `new_acikhesapriski`, `new_ceksenetriski`, `new_toplamrisk`, `new_crmaciksiparisriski`, `new_ekacikhesaplimiti`, `CreditLimit`, `CreditOnHold`, `StatusCode` 100000003 «Sorunlu Müşteri», `new_vadegun`, `new_Vadesablonuid` | Alanlar katalogda | **Doluluk ölçülecek** (Logo'da limit 0 — ölçüldü) |
| Risk onay geçmişi | CRM `new_siparisBase` (`statuscode` 100000004, `new_risketakilmasebebi`, `new_anliklimit`, `new_anlikrisk`, onaylayan/reddeden, onay/ret tarihi) | Alanlar katalogda | Kayıt sayısı ölçülecek |
| Tahsilat kayıtları | CRM `new_tahsilatBase` (tip, vade, tutar, durum, ret nedeni) | 14.089 kayıt | Logo'ya aktarılmamış tahsilat ayrı gösterilir |
| BMT, bölge, il | CRM `AccountBase.OwnerId` (BMT), `new_BMTilveyaCari`, `new_illerBase.new_musteritemsilcisi`, satış hedefi `new_bolge` (15 bölge) | Alanlar var; «SystemUser.TerritoryId ↔ bölge eşlemesi zayıf» (ölçüldü) | Cari → bölge eşlemesi kurulmalı (il üzerinden) |
| Cari il/ilçe | CRM `CustomerAddressBase.City` (251.517 adres); Logo `CLCARD` il/ilçe alanları | Alanlar var | Doluluk ve yazım birliği ölçülecek |
| Ziyaret ve not | CRM `new_etkinlikBase` (`new_ziyarettipi` «Cari Ziyareti», `new_GercZiyTarihi`, `new_Tahsilatinfo`, `new_sorumlusu`) | 57.013 etkinlik | Hazır (okuma); portal notu ayrı tablo |
| Okul ↔ bayi | CRM `new_ziyaretyerleriBase` (68.713; okul türü, kademe, il, ilçe), etkinlik `new_AracMteriId` (aracı müşteri) | Alanlar var | Doluluk ölçülecek; M31 yok |
| Bölge potansiyeli (nüfus, okul, öğrenci) | Dış (açık veri) | Yok; müşteride web kapalı | Dosya ile yüklenir |
| Bayi hedefi | M46 (`/api/v1/budget/targets`, `/deviations`) | M46 kitap hedefi var; bölge/bayi hedefi M30'a ileti olarak tanımlı | Bayi hedefi M46'da ayrıca kurulmalı (ölçülecek) |

## 7. Diğer modüllerle bağ

- **Girdi alır:** Logo (alacak, satış, iade, çek), CRM (limit, risk onayı, tahsilat, ziyaret, BMT, bölge), M46 (bayi/bölge
  hedefi, sapma), M30 (ziyaret planı ve notu — yoksa CRM etkinlik), M31 (okul eşleştirme talebi — yoksa CRM ziyaret yeri).
- **Çıktı verir:** M30 (ziyaret öncesi risk brifi, tahsilat öncelik listesi, ziyaret önceliği), M31 (okul için bayi
  önerisi), M45 (beklenen tahsilat, şüpheli alacak adayı → nakit ve karşılık), M47 (müşteri yoğunlaşması ve kredi riski
  göstergesi), DYK (segment dağılımı, vadesi geçmiş, yoğunlaşma).

## 8. Kısıtlar

- **CRM'e yazma yok**: onaylanan limit revizyonu, okul-bayi eşleştirmesi ve «sorunlu müşteri» önerisi portal tablosunda
  kalır; ekranda «CRM'e işlenecek» listesi. **Logo'ya yazma yok.**
- **Yaklaşık hesap dürüstlüğü:** vade/gecikme FIFO, tahsilat süresi DSO yaklaşımıdır; ekranda ve brifte «yaklaşık» yazar.
  Boş limit «limiti yok» değil «limit girilmemiş» demektir.
- «Bugün» = Logo veri son günü (donmuş kopya); aksi halde 17.08'den bu yana her vade «geçmiş» görünür.
- Skor bir sınıflandırma aracıdır, kredi kararı değildir; müşteriye gönderilen hiçbir metinde skor yazmaz.
- KVKK / ticari gizlilik: cari adları gerçek ticari müşteridir; BMT yalnız kendi carisini görür; dışa aktarma yetkiyle.
  Bayi başvurusundaki KVKK/iletişim izni alanları (`new_bayibasvurusukvkkizni`) iletişim önerisinde dikkate alınır.
- Ekranda teknoloji adı yok; demo veri yok; satır tavanı yok; müşteride web taraması kapalı (dış potansiyel verisi dosyayla).

## 9. Kapsam önerisi

**İlk sürüm**
- Günlük skor (açıklanabilir bileşenler, sürümlü kural), segment, eğilim; Pano + Bayiler + Bayi kartı.
- Yaşlandırma (FIFO, yaklaşık), iade oranı, karşılıksız çek olayı, CRM limit/risk alanları kartta.
- Risk brifi (telefon görünümü) + ziyaret notu.
- BMT kapsamı (yalnız kendi carileri).
- Sabah e-postası, kötüleşme uyarısı.

**Sonraki sürüm**
- Limit revizyon önerisi + onay + «CRM'e işlenecek» listesi.
- Kategori karması ve performans segmentasyonu; M46 bayi hedefi gelince hedef-gerçekleşme.
- Kapsama tablosu/haritası, okul-bayi önerisi (M31), yeni bayi adayı (dış veri yüklenince).
- M30 ziyaret planıyla bütünleşme.

**Yeniden kullanılacaklar**
- Bilgi paketindeki SQL'ler: `sql/vadesi-gecmis-yaslandirma-fifo.md`, `sql/vadesi-gecmis-toplam-fifo.md`,
  `sql/ortalama-tahsilat-suresi-dso.md`, `sql/planlanan-odeme-vadesi.md`, `sql/en-cok-iade-alan-10-musteri-kimler.md`.
- `backend/semantic_bridge/budget_sources.py` (Logo okuma çalıştırıcısı, `L_CAPIPERIOD` yıl eşlemesi),
  `freelance_logo.py` (cari hareket okuma), `people.py` (CRM kullanıcı ↔ AD GUID — BMT kapsamı),
  `alerts.py`, `reports.py`, `admin.audit`, M2'nin sürümlü kural tablosu deseni (`editorial_assign.py`, `rule_versions`).

## 10. Uzmanlara sorulacak sorular

1. CRM cari kartındaki limit ve risk alanlarını kim, ne sıklıkla güncelliyor; `new_toplamrisk` Logo'dan mı besleniyor?
2. «Bayi/kitapçı» kapsamı hangi kanallar: KITAPCI + BAYI + DAGITICI + ZINCIR mi; büyük e-ticaret platformları ve zincirler
   aynı skorla mı değerlendirilmeli, ayrı «anahtar hesap» grubu mu?
3. Vade şablonları (`new_Vadesablonuid`, 186 ödeme vadesi kaydı) cariye göre mi siparişe göre mi uygulanıyor?
4. Limit onayında bugün hangi bilgilere bakıyorsunuz, onaylayıcılar kimler?
5. Bölge (15 bölge) ile il/BMT eşlemesinin doğru kaynağı hangisi?

## 11. Başarı ölçütü

- Limite takılan sipariş için onay süresi: CRM'deki onay/ret tarihlerinden bugünkü ölçülür → düşmeli.
- 90+ kovasındaki tutarın ve cari sayısının ay ay seyri (yaklaşık ama aynı yöntemle karşılaştırılabilir).
- Skorun isabeti: C/D segmentine düşen carilerde sonraki 6 ayda karşılıksız çek / 90+ gecikme oranı, A/B'ye göre anlamlı
  yüksek olmalı (geriye dönük sınama 2021–25 kopyasıyla).
- BMT kullanımı: ziyaret öncesi brif açılma oranı (CRM ziyaret kaydıyla eşleştirerek).
- Sessiz kapsam kaybı 0: listedeki cari sayısı = kapsam sorgusundaki cari sayısı.

## 12. Uzman gözüyle en iyi sistem

Kendimi 15 yıllık bir bölge satış şefinin ve yanındaki kredi kontrol uzmanının yerine koyuyorum.

**İyi yayınevleri ve iyi yazılımlar bu işi nasıl yapıyor.** Toptan satan yayınevleri ve dağıtıcılarda kredi kontrolü
satıştan ayrı ama aynı ekranı kullanan bir iştir. İyi alacak yönetimi yazılımlarının ortak yanları: (1) skor **açıklanabilir**
— «neden C» sorusu üç bileşenle cevaplanır, kara kutu yoktur; (2) davranış **eğilimi** skorun kendisinden önemlidir
(ödeme süresi son 3 ayda 20 gün uzadıysa segment düşmeden uyarı verir); (3) tahsilat **iş listesi** üretir — kimi, hangi
sırayla, ne söyleyerek arayacağını; (4) iade riski yayıncılığa özgüdür — dağıtıcı ve zincirlerde iade, satıştan aylar sonra
gelir, bu yüzden «iade sonrası net alacak» ayrı izlenir; (5) büyük platformlar (e-ticaret, zincir) küçük kitapçıyla aynı
skora konmaz, anahtar hesap olarak ayrı izlenir. Zayıf yanları: veri kalitesi kötüyse (kapama yok, limit girilmemiş) skor
güven kaybeder; bunu dürüstçe göstermeyen sistem terk edilir.

**TİMAŞ için mükemmel sistem:** CRM'de sipariş limite takıldığında onaylayıcı telefonunda carinin kartını açar: skor, üç
bileşen, 12 aylık eğilim, son tahsilat, bekleyen çek, önerilen karar ve «yaklaşık» notu — 30 saniyede karar. BMT sabah
rotasındaki her bayi için brifi açar; ziyaret sonrası sesli ya da yazılı kısa not bırakır. Satış şefi haftada bir kapsama
tablosuna bakar: bayisiz ilçeler, okul yoğunluğu, aracı bayi. Kurallar (ağırlık, eşik) sürümlüdür; değişince eski ve yeni
segment dağılımı yan yana görünür.

**Bir iş günü (bölge satış şefi):**
- 08:00 — E-posta: 3 bayi C'den D'ye düştü, 5 limit önerisi onay bekliyor, 1 karşılıksız çek olayı.
- 08:20 — Telefonda D'ye düşen bayinin kartı: FIFO'ya göre 90+ kovası 420 bin ₺, iade oranı %31, son tahsilat 74 gün önce.
  BMT'ye «bu hafta ziyaret» aksiyonu atıyor.
- 10:00 — Masaüstünde limit önerileri: 4'ünü onaylıyor, birini «önce ziyaret» notuyla geri çeviriyor; onaylananlar
  «CRM'e işlenecek» listesine düşüyor, merkez müşteri temsilcisi CRM'e işliyor.
- 13:00 — BMT sahadan brifi açıp tahsilat görüşmesine giriyor; dönüşte «haftaya çek verecek» notu.
- 15:00 — Kapsama: Ege'de iki ilçede bayi yok, 40'tan fazla okul var; yeni bayi adayı araştırması için aksiyon.
- 17:00 — Kurallar sekmesinde iade ağırlığını artırma taslağı; «bu kuralla segment dağılımı nasıl değişir» önizlemesi;
  CFO'ya onaya gönderiyor.

**«Bunu görürsem hemen kullanırım»**
1. Limite takılan siparişte telefonda tek ekranda skor + bileşen + eğilim.
2. Ziyaret öncesi tek sayfa brif, konuşulacak üç madde ile.
3. Kural değişince segment dağılımının önizlemesi.

**«Bunu yaparsanız kullanmam»**
1. Açıklamasız skor; «sistem D diyor» ile bayiye limit kısamam.
2. Yaklaşık gecikmeyi kesin gibi göstermek — bayi «ben ödedim» dediğinde yanılmış olurum.
3. Kitapyurdu'nu mahalle kitapçısıyla aynı ölçüyle kırmızı göstermek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kapsam (hangi cariler) | `LG_411_CLCARD` (`CODE LIKE '120%'`, `SPECODE2` kanal, `ACTIVE`) | `AccountBase` (`new_logicalref`, `new_cariozelKod2`, `new_FirmaKanal`, `StatusCode`) | Yok | Kural. |
| Bakiye, vadesi geçmiş, kovalar | `LG_411_01_CLFLINE`, `LG_411_01_PAYTRANS`; ölçü `vadesi_gecmis_alacak_fifo` | — | Yok | Rakam SQL'den; yaklaşık etiketli. |
| Tahsilat süresi eğilimi | CLFLINE + fatura; ölçü `ortalama_tahsilat_suresi` (DSO) aylık seri | `new_tahsilatBase` (Logo'ya aktarılmamış tahsilat) | Yok | Eğilim deterministik. |
| İade oranı, satış seyri | `INVOICE` (TRCODE 7,8,9 / 2,3), ölçü `iade_orani`; `STLINE` faturalı satır | — | Yok | Sertifikalı ölçü. |
| Çek/senet olayı | `LG_411_01_CSCARD`, `LG_411_01_CSTRANS` (STATUS 11, 5, 7) | `new_tahsilatBase` (çek no, vade) | Yok | Olay kaydı Logo'da. |
| Limit/risk | — (Logo'da limit yok) | `AccountBase` limit/risk alanları, `CreditOnHold`, «Sorunlu Müşteri» | Yok | CRM tek kaynak. |
| Risk onay geçmişi | — | `new_siparisBase` (statuscode 100000004, riske takılma sebebi, onaylayan/reddeden, tarihler) | Yok | Davranış verisi. |
| Skor ve segment | Yukarıdakiler | Yukarıdakiler | Yok — ağırlıklı kural, sürümlü | Açıklanabilir ve tekrar üretilebilir olmalı. |
| Risk brifi | Kart verisi (JSON) | Son ziyaret notları (`new_etkinlikBase.new_info`, `new_Tahsilatinfo`), portal notu | 5-6 cümle brif + «konuşulacak 3 madde»; sayılar girdiden kopyalanır, sonradan denetlenir | Saha için okunur özet. |
| Ziyaret notlarının özeti | — | `new_etkinlikBase` açıklama alanları (serbest metin) | Son 5 notun özeti + tema etiketi (kapalı küme: tahsilat sözü / şikâyet / sipariş talebi / iade talebi / diğer — tek token + olasılık) | Serbest metin okunur kılınır. |
| Limit revizyon önerisi | Kart verisi | Mevcut limit | Kural öneriyi hesaplar; model yalnız **gerekçe** cümlesi yazar | Rakam kuraldan, gerekçe modelden. |
| Okul-bayi önerisi | Bayi satışı (il/ilçe, kategori) | `new_ziyaretyerleriBase` (il, ilçe, okul türü/kademe), etkinlik `new_AracMteriId` | Aday bayiler kuralla sıralanır; model uygunluk gerekçesi yazar | Karar satış yöneticisinde. |
| Serbest soru | Katalog ölçüleri | CRM okunur tablolar | Mevcut `/api/v1/ask` | Yeni motor yok. |

Model çağrıları `rt.llm_for("dealers")`; brif isteği kullanıcı beklediği için normal öncelik, toplu not etiketleme
`BATCH`. Ekranda yalnız «Zeki AI».

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/dealers.py` — kapsam, skor (kural sürümüyle), segment, eğilim, limit önerisi, aksiyon, not.
- `backend/semantic_bridge/dealers_sources.py` — Logo (CLCARD, CLFLINE, PAYTRANS, INVOICE, STLINE, CSCARD/CSTRANS) ve CRM
  (AccountBase, new_siparisBase, new_tahsilatBase, new_etkinlikBase, new_ziyaretyerleriBase, CustomerAddressBase, SystemUser)
  okumaları; `budget_sources.runner` deseni; «bugün» = veri son günü.
- `backend/semantic_bridge/dealers_api.py` — `register(app, rt, require_caller, can)`.

**Tablolar**
- `semantic_dealer_rules` (id, tenant_id, surum, durum taslak|onayda|yururlukte|arsiv, agirliklar_json, esikler_json,
  kapsam_json (kanallar), hazirlayan, onaylayan, tarihler, gerekce)
- `semantic_dealer_scores` (tenant_id, gun, cari_ref PK üçlüsü, kanal, bolge, bmt, bakiye, vadesi_gecmis, kova_json,
  iade_orani, dso, siparis_duzensizlik, cek_olay, limit_kullanim, skor, segment, egilim, kural_surum, veri_son_gunu, fingerprint)
- `semantic_dealer_limit_proposals` (id, cari_ref, mevcut_limit_json (CRM anlık), onerilen_json, gerekce_kural,
  gerekce_metin, durum oneri|onayli|red|crm_islendi, karar_veren, karar_at, crm_isleyen, crm_islendi_at)
- `semantic_dealer_notes` (id, cari_ref, yazan, tarih, metin, kaynak portal|crm, etiket, etiket_olasilik)
- `semantic_dealer_actions` (id, cari_ref, tur ziyaret|arama|limit|diger, sahip, termin, durum, not)
- `semantic_dealer_briefs` (cari_ref, uretim_at, metin, girdi_hash, llm_job_id) — önbellek
- `semantic_dealer_school_links` (okul_id (CRM ziyaret yeri), cari_ref, kaynak crm_araci|oneri, durum, onaylayan)
- `semantic_dealer_coverage` (il, ilce, bayi_sayisi, satis, okul_sayisi, dis_veri_json, guncelleme)
- `semantic_dealer_meta`

**Uçlar** (`/api/v1/dealers/*`)
- `GET summary` · `GET list?segment&kanal&bolge&bmt&q&mine&page&order` · `GET {cari}` (kart) · `GET {cari}/aging` ·
  `GET {cari}/history` · `POST {cari}/brief` (model; önbellekli) · `GET/POST {cari}/notes` · `GET/POST/PATCH actions`
- `GET limits` · `POST limits/{id}/approve|reject` · `POST limits/{id}/crm-done`
- `GET rules` · `POST rules` (taslak) · `POST rules/{id}/preview` (segment dağılımı önizleme) · `POST rules/{id}/submit|approve`
- `GET coverage?il` · `POST coverage/upload` (dış potansiyel CSV) · `GET schools/{okul}/suggest` · `POST schools/{okul}/link`
- `POST run-due` (SYSTEM) · `GET status` · `GET list/export.csv` (`ozellik:veri.disa-aktar`)

**Ekranlar** `src/canvas/dealers/`: `DealersScreen.tsx` (sekmeler Pano · Bayiler · Limit önerileri · Kapsama · Kurallar),
`DealerCard.tsx`, `BriefSheet.tsx` (telefon öncelikli tek sayfa), `RulesTab.tsx`, `api.ts`. Rota `/timas/bayi-risk`
ve `/timas/bayi-risk/:cari`. Menü: `navModel.ts` → «Finans» alanına «Bayi riski» (anahtar kelimeler: bayi, kitapçı,
alacak, vade, limit, tahsilat). Kampüs: `ModulesMenu.tsx` `LIVE.M59 = '/bayi-risk'`, `GROUP_HOME['Bayi & Kitapçı Risk
Yönetimi'] = { to: '/bayi-risk', … }`.

**Yetki**
- `sayfa:bayi-risk` → `/api/v1/dealers/`; `run-due` SYSTEM.
- `ozellik:bayi.herkesinki` (**açıkça**; yoksa yalnız CRM'de sahibi olduğu cariler — kimlik bağı `people.py` AD GUID ↔
  CRM `SystemUser`), `ozellik:bayi.not`, `ozellik:bayi.aksiyon`, `ozellik:bayi.limit-onay` (**açıkça**),
  `ozellik:bayi.kural` (taslak), `ozellik:bayi.kural-onay` (**açıkça**; hazırlayan onaylayamaz),
  `ozellik:bayi.okul-eslestir`.

**Zamanlayıcı** `scripts/server/timas-dealers.{timer,service}`: her gün 06:00 `POST /api/v1/dealers/run-due` → skorlar
(yürürlükteki kural), eğilim, kötüleşme uyarıları, limit önerisi adayları, sabah e-postası 08:00; saatte bir CRM risk onayı
bekleyen siparişleri tazeler (salt okuma). İlk koşu elle.

**Kabul testleri** (gerçek DB; «bugün» = `SELECT MAX(DATE_) FROM LG_411_01_INVOICE WHERE CANCELLED = 0`)
1. Bakiye (rastgele 10 cari): `SELECT SUM(CASE WHEN SIGN = 0 THEN AMOUNT ELSE -AMOUNT END) FROM LG_411_01_CLFLINE WHERE
   CANCELLED = 0 AND CLIENTREF = :ref` = kart bakiyesi.
2. Yaşlandırma: bilgi paketi `vadesi-gecmis-yaslandirma-fifo.md` sorgusu (GETDATE yerine veri son günü) → kova toplamları
   ve cari sayıları Pano ile eşit.
3. İade oranı: `SELECT SUM(CASE WHEN TRCODE IN (2,3) THEN NETTOTAL END) / NULLIF(SUM(CASE WHEN TRCODE IN (7,8,9) THEN
   NETTOTAL END), 0) FROM LG_411_01_INVOICE WHERE CANCELLED = 0 AND CLIENTREF = :ref AND DATE_ >= :bas` = bileşen değeri.
4. Kapsam: `SELECT COUNT(*) FROM LG_411_CLCARD WHERE CODE LIKE '120%' AND SPECODE2 IN (:kanallar)` (kural sürümündeki
   kanal listesi) = listedeki cari sayısı; eksik yok.
5. CRM limit: `SELECT new_logicalref, new_toplamrisklimiti, new_toplamrisk, new_acikhesaprisklimiti FROM
   Timas_MSCRM.dbo.AccountBase WHERE new_logicalref = :ref` = karttaki limit/risk; boşsa kart «limit girilmemiş» der.
6. Karşılıksız çek: `SELECT COUNT(*), SUM(…) FROM LG_411_01_CSTRANS WHERE STATUS = 11 AND DATE_ >= '2026-01-01'` →
   6 çek / 6.326.658 ₺ (2026-09-20 ölçümü) = cari bileşenlerinin toplamı.
7. Risk onayı: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase WHERE statuscode = 100000004` = «onay bekleyen sipariş» sayısı.
8. Tekrar üretilebilirlik: aynı gün + aynı kural sürümü ile ikinci koşu → bütün `fingerprint`ler aynı (DB'siz birim testi de).

**Bağımlılık:** Bağımsız başlayabilir (Logo + CRM okuma yeter). M46 bayi hedefi ve M30/M31 sonradan bağlanır. M45 ve DYK
`GET summary` ucunu okur → uç şekli önce sabitlenirse paralel kodlanır.

**Tahmini büyüklük:** L (skor + kart + pano M; brif/not S; limit önerisi S; kapsama/okul M).
