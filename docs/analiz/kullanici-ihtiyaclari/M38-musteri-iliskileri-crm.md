# M38 — Müşteri İlişkileri ve CRM Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M38.txt` (ZEKİ_Moduller3.html'den),
`specs/E_Ticaret_Müşteri_Yönetimi_Ent.txt`, sınır için `specs/M30.txt`, `M32.txt`, `M51.txt`, `M59.txt`, `M15.txt`
(M38/M39 analizine atıf), `specs/ANALIZ-EK.md`; depoda `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `PROJECT-MEMORY.md`,
`configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`, `table_descriptions.json` (2026-09-09),
`configs/semantic/knowledge/logo/knowledge/{metrics,rules,glossary}/`; bellek: system-of-record-logo, live-bi-numbers-2026,
logo-155-frozen-copy, invoice-count-sales-scope, crm-systemuser-directory, period-union-double-counting,
year-copy-union-by-name, logo-period-prefixes-are-years. `ZEKİ_Veri_Haritasi2.html` verilen klasörde yok. Sunucuya
bağlanılmadı; sayılar depodaki tarihli ölçümlerdir.

## 1. Modül ne işe yarar

İş tanımına göre modülün iki işi var. CRM veri hijyeni ve otomasyonu (K1): tekrarlı ve eksik kayıt kontrolü, segmentin
otomatik güncellenmesi, iletişim tercihi ve KVKK uyum takibi, müşteri yaşam döngüsü aşamaları. Müşteri analitiği (K3):
müşteri yaşam boyu değeri, kayıp riski erken uyarısı, yeniden satın alma olasılığı, en değerli segmentin profili. Aksiyon
ekip kararındadır. Çıktılar: CRM sağlık raporu, analitik çıktılar, iletişim planı.

TİMAŞ'ta "müşteri" ağırlıkla **kurumsal cari**dir: bayi, kitapçı, dağıtıcı, e-ticaret platformu, kurum, okul. CRM'de 47.550
cari (kanal tipi Logo özel kod 2 ile eşleşir: ABONE, BAYI, DAGITICI, E-TICARET, FUAR, INTERNET, KITAPCI, KURUM…) ve 333.063
sipariş var. Kitapsiparis.com.tr B2B portalından son 90 günde 4.026 sipariş gelmiş, yaklaşık 5.090 bayi kullanıcısı var.
Logo'da 2026'nın ilk 8,5 ayında 73.660 satış faturası kesilmiş, ciro toptan ağırlıklı (TRCODE 8: 874,6 milyon TL, 21.009
fatura). İlk sıradaki cariler Turkuvaz, Kitapyurdu, D-Market ve Point. Bugünkü sorunlar: CRM'de veri kalitesi ölçülmemiş.
Ortak "Timas CRM" hesabı binlerce kaydın sahibi görünüyor (1.343 plan rolü + 1.791 sözleşme; sahiplik bilgisi bozuk).
Servis talebi (34 kayıt) ve anket (2) kullanılmıyor. Carinin değeri ve kaybolma riski hiçbir yerde hesaplanmıyor. CRM ile
Logo cari bağı iyi: `new_logicalref` dolu 26.691 carinin 26.329'u Logo'da eşleşiyor (%98,6). Ancak yaklaşık 20,9 bin
carinin Logo bağı hiç yok.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Satış müdürü / bölge müdürü | Satış (CRM ekip üyeliği: 49 kişi). Satış hedefleri 15 bölgede tutuluyor (Babıali, Ege, İstanbul, D&R, Hepsiburada, Kitapyurdu, B2C…) (kanıt) | Haftalık | Masaüstü, telefon |
| Müşteri temsilcisi / saha satış | Satış. Carilerde `new_MerkezMusteriTemsilcisi`, `PreferredSystemUserId`, il bazında müşteri temsilcisi alanları var (kanıt) | Her gün | Telefon (sahada), masaüstü |
| CRM yöneticisi / veri sorumlusu | BT. "Timas CRM" ortak hesabını kullanan ekip; kişi **varsayım** | Haftalık | Masaüstü |
| Muhasebe / finans | Mali İşler (10 kişi). Cari risk ve tahsilat M59 ile ortak | Aylık | Masaüstü |
| Pazarlama (iletişim izni, toplu ileti) | Pazarlama | Kampanya öncesi | Masaüstü |
| KVKK sorumlusu | Hukuk / idari işler — **varsayım** | Aylık | Masaüstü |
| Genel müdür / yönetim | Yönetim | Aylık | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

- **Satış müdürü.** Cari performansını Logo raporlarından ya da mevcut Power BI raporundan (ekranda "mevcut rapor")
  izliyor (**varsayım**). Hedefler CRM'de bölge × stok × ay olarak duruyor (334.982 satır). Kişiye bağları zayıf
  (Territory eşlemesi 2 satır).
- **Müşteri temsilcisi.** Siparişi CRM'den ya da B2B portalından alıyor. Ziyaret "etkinlik" olarak kaydediliyor (57.013
  etkinliğin çoğu "Cari ile Ziyaret"). Bir carinin alımının neden düştüğünü görecek bir ekran yok (**varsayım**).
- **CRM yöneticisi.** Veri kalitesini elle kontrol ediyor. Kişi kaydında `new_VeriDurumu` alanı (Kontrol Edildi / Kontrol
  Edilecek / Silinebilir / Veri Kalitesi Yetersiz) ve `new_bilgikontroledildi` var (kanıt). Bu alanların ne kadar
  kullanıldığı **ölçülecek**. Bilinen teknik sorunlar: `Product` iş akışı sonsuz döngüye giriyor (30 günde 332 iptal).
  B2B web servis günlüğünde bayi şifreleri düz metin duruyor. `new_webuser` ve bir görünüm şifreleri açığa çıkarıyor
  (crm-eticaret §1.3, §2).
- **Muhasebe.** Risk limiti CRM siparişinde kontrol ediliyor ("Riske Takılma Sebebi", "Risk Limit Onayı Bekliyor"
  durumu). Tahsilat ve vade Logo'da.
- **Sıkıntı.** Değer, risk, veri kalitesi ve izin dört ayrı yerde, çoğu ölçülmemiş.

## 4. İhtiyaçlar ve acı noktaları

**Satış müdürü**
1. Carinin son 12 ay değeri ve önceki 12 aya göre değişimi, kanal ve bölge kırılımıyla.
2. Kaybolma riski listesi: alım aralığı açılan, cirosu düşen, iadesi artan cariler, nedenleriyle.
3. Temsilci portföyü: kimin carisi, son temas (ziyaret) ne zaman.
4. Ekibin aldığı aksiyonun ve sonucunun kaydı.

**Müşteri temsilcisi**
1. Kendi carilerinin telefonda tek sayfalık özeti: son sipariş, son fatura, açık sipariş, iade, risk.
2. "Bu hafta aranacaklar": riski artan kendi carileri.

**CRM yöneticisi**
1. Veri sağlığı puanı ve düzeltme listesi: tekrar, Logo bağı yok, eksik alan, sahipsiz kayıt.
2. Güvenlik bulgularının takibi.
3. Düzeltmenin CRM'de yapıldığının ertesi gün doğrulanması.

**Pazarlama / KVKK**
1. Cari ve kişi iletişim izinlerinin tutarlılığı (İYS, KVKK, toplu e-posta izni).

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Satış müdürü olarak kaybolma riski artan carileri nedenleriyle görmek istiyorum, çünkü kaybetmeden önce temsilciyi
  yönlendirmeliyim.
- Satış müdürü olarak bir riskli cariye "arandı, görüşüldü, kampanya teklif edildi" diye aksiyon yazmak ve sonucunu 30 gün
  sonra görmek istiyorum, çünkü hangi müdahalenin işe yaradığını bilmeliyim.
- Müşteri temsilcisi olarak telefonumda kendi carilerimin sıralı listesini görmek istiyorum, çünkü ziyaret rotamı buna göre
  kuruyorum.
- CRM yöneticisi olarak Logo bağı olmayan ve tekrar olasılığı yüksek cari kayıtlarını görmek istiyorum, çünkü raporlar bu
  kayıtlar yüzünden eksik çıkıyor.
- CRM yöneticisi olarak bir bulguyu "CRM'de düzeltildi" diye işaretlediğimde ertesi gün doğrulansın istiyorum, çünkü elle
  takip edemiyorum.
- Yönetici olarak en değerli cari segmentinin profilini ve payını görmek istiyorum, çünkü kanal stratejisini buna göre
  belirleyeceğim.

**Ana ekranlar ve akış**
- *Müşteri özeti* (ilk açılış). Kanal bazında aktif cari sayısı, son 12 ay değeri, riskli cari sayısı, veri sağlığı puanı,
  Logo kesim tarihi. Altında "bu hafta bakılacak cariler" (risk × değer).
- *Cariler*. Süzgeçler: kanal, bölge, temsilci, risk düzeyi. Kolonlar: son fatura, 12 ay net, değişim, sipariş aralığı,
  iade oranı, risk, neden.
- *Cari ayrıntısı*. Aylık alım grafiği, kitap/kategori dağılımı, siparişler, ziyaretler, aksiyon geçmişi, Zeki AI'ın neden
  özeti.
- *Veri sağlığı*. Bulgu türleri ve sayıları, liste, "CRM'de düzeltildi / yoksay" işareti.
- Tık sayıları: riskli bir carinin nedenini görmek 2 tık; aksiyon yazmak 3 tık; veri bulgusunu işaretlemek 2 tık.
- Telefonda temsilci görünümü: kendi carileri kart olarak, ara/ziyaret aksiyonu tek dokunuşla (arama telefonun kendi
  uygulamasıyla; numara yalnız temsilcinin kendi carisi için).

**Zeki AI'a soracakları örnek sorular**
1. "Son 12 ayda alımı yüzde 30'dan fazla düşen kitapçılar hangileri?"
2. "Kitapyurdu'nun bu yılki net alımı geçen yılın aynı dönemine göre nasıl?"
3. "90 gündür sipariş vermeyen ama geçen yıl düzenli alan bayiler kimler?"
4. "Ege bölgesinde en çok iade eden 10 cari hangileri?"
5. "Logo'da karşılığı olmayan CRM cari kaydı kaç tane?"
6. "Hangi temsilcinin portföyünde riskli cari en çok?"
7. "Dağıtıcı kanalının cirodaki payı son üç yılda nasıl değişti?"

**Otomasyon katmanı**
- K1: Veri sağlığı taraması, cari değer ve risk puanı, segment üyeliği (kanal × değer × eğilim) her gece hesaplanır. Bulgu
  koşulu kalkınca bulgu kendiliğinden kapanır.
- K2: Zeki AI risk nedeni özeti ve aksiyon önerisi yazar ("son 3 ayda alım aralığı 2 katına çıktı, en çok aldığı kategori
  çocuk"). Aksiyonu temsilci ya da müdür seçer.
- K3: Değer ve segment analizi; kanal stratejisi ekipte (iş tanımıyla aynı).
- K4: CRM'deki düzeltme insan tarafından yapılır. İş tanımındaki "otomatik segment güncelleme" ve "yaşam döngüsü aşaması
  otomasyonu" CRM'e yazma yetkisi gelene kadar yalnız portalda tutulur. "Otomatik e-posta akışları" bu modülde yok; M24 ve
  M37 ile, izinle ve onayla yürür.

**Bildirim / uyarı**
- Temsilciye: kendi carisi "yüksek risk"e geçtiğinde e-posta (haftalık toplu; her cari için ayrı değil).
- Satış müdürüne: pazartesi risk özeti.
- CRM yöneticisine: yeni güvenlik bulgusu ya da veri sağlığı puanında belirgin düşüş.

**Onay ve yetki**
- `sayfa:musteri-iliskileri`: özet ve cari listesi. Temsilci varsayılan olarak **yalnız kendi portföyünü** görür.
- `ozellik:musteri.herkesinki` (explicit): bütün carileri görür (müdür, yönetim).
- `ozellik:musteri.eylem-yaz`: aksiyon ve not yazar.
- `sayfa:musteri-veri-sagligi` + `ozellik:musteri.bulgu-isaretle`: veri sağlığı (CRM yöneticisi).
- `ozellik:musteri.guvenlik-bulgulari` (explicit): güvenlik bulgularını görür (BT).
- `ozellik:veri.disa-aktar` (var).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Cari kartı, kanal, temsilci | CRM `AccountBase` (47.550): `new_FirmaKanal`, `new_cariozelKod2` (kanal tipi), `new_logicalref`, `new_MerkezMusteriTemsilcisi`, `PreferredSystemUserId`, `OwnerId`, `new_geliskanali`, `statecode` | Alanlar biliniyor; Logo bağı %98,6 (bağı olanlarda) | `new_logicalref`'in hangi Logo firmasının LOGICALREF'i olduğu **ölçülecek** (yıl başına ayrı firma; bkz. bölüm 13) |
| Gerçekleşmiş satış, iade | Logo `LG_411_01_INVOICE` (2026), `LG_211_01_INVOICE` (2021–2025), `CLCARD.SPECODE2`; ölçüler `net_ciro`, `iade_orani`, `kanal_net_ciro` | Tanımlı, ölçülmüş | Son fatura 2026-08-17 (donmuş kopya) |
| Sipariş sıklığı, açık sipariş | CRM `new_siparisBase` (333.063; tip, durum, tarih, risk alanları), Logo `ORFICHE/ORFLINE` | Biliniyor | — |
| Ziyaret / temas | CRM `new_etkinlikBase` (ziyaret tipi, `new_GercZiyTarihi`, `new_sorumlusu`, `new_AracMteriId`) | Biliniyor | CRM'de e-posta ve telefon aktivite tabloları katalog dışı; temas kaydı eksik |
| Tahsilat ve vade | Logo (`vadesi_gecmis_alacak_fifo`, `ortalama_tahsilat_suresi`); CRM tahsilat (14.089) | Tanımlı | Kredi riski M59'a bırakılır; burada yalnız gösterge |
| Kişi (cari yetkilisi) | CRM `ContactBase` (`ParentCustomerId`) | Biliniyor | Yetkili kişi verisi ekranda yalnız portföy sahibine |
| İletişim izinleri | CRM `AccountBase.DoNotEMail`, `DoNotBulkEMail`, `obs_donotsms`, `obs_iys_customertype`, `new_izinalinanurl`, `new_izinalinanipadresi`, `new_izinverenkullaniciid`; `ContactBase.new_kvkkonayi`, `new_iysonayi` | Alanlar biliniyor | Doluluk **ölçülecek** |
| Veri kalitesi işaretleri | CRM `ContactBase.new_VeriDurumu`, `new_bilgikontroledildi`, `new_kontroledildi` | Alanlar biliniyor | Kullanım **ölçülecek** |
| Satış hedefi | CRM satış hedefleri (334.982; yıl, bölge, stok, 12 ay) | Biliniyor | Bölge ↔ cari ↔ temsilci eşlemesi zayıf |
| Müşteri memnuniyeti | CRM `IncidentBase` (34; `CustomerSatisfactionCode`), anket (2) | Kullanılmıyor | Veri yok; ilk sürümde yok |
| Okur (bireysel müşteri) | M37 | — | Bu modülde yalnız veri sağlığı ve izin yönünden |

## 7. Diğer modüllerle bağ

- Girdi alır: M30 Saha Satış (ziyaret ve tahsilat), M32 B2B (portal siparişleri, bayi kullanıcıları), M59 Bayi Risk
  (kredi riski ve vade), M46 Bütçe (satış hedefi), M34 (pazar yeri carileri).
- Çıktı verir: M37 (kişi kaydı veri sağlığı, izin bulguları), M35 (riskli ya da değerli cariye kampanya), M24 (izinli
  toplu ileti listesi, onayla), M15/M16 (cari segmentleri), M45 ve DYK (müşteri yoğunlaşması, kanal göstergesi).
- Sınır: kredi limiti, tahsilat ve vade kararı M59'dur. Şikâyet ve talep yönetimi M51'dir. Okur topluluğu M37'dir. M38
  ilişkiyi, değeri ve CRM'in sağlığını tutar.

## 8. Kısıtlar

- **CRM'e yazılmaz.** Düzeltmeler CRM'de insan eliyle yapılır. Portal bulguyu ve işareti tutar, ertesi gece doğrular. CRM
  Web API yetkisi gelse bile `new_name`, `new_ean13`, `new_StokKodu` ve `Product` gibi entegrasyon alanlarına yazılmaz
  (crm-eticaret §7.4).
- **Kayıt sistemi Logo'dur.** "Kaç fatura", "ne kadar aldı" soruları Logo'dan cevaplanır. CRM'deki fatura numarası kopyası
  kaynak sayılmaz (bellek: system-of-record-logo).
- **Yıl kopyaları.** Logo'da yıl başına ayrı firma var (LG_211 = 2021–2025, LG_411 = 2026). 12 aylık pencere iki kopyayı
  birleştirir. Birleştirme kolon adıyla yapılır, `SELECT *` UNION yapılmaz. Cari iki firmada `CLCARD.CODE` ile eşlenir,
  LOGICALREF firmalar arasında aynı varsayılmaz.
- Ekranda teknoloji adı yok. Mevcut Power BI raporu ekranda "mevcut rapor" diye anılır. Demo veri yok, sayı tavanı yok.
- **KVKK.** Cari yetkilisinin adı ve telefonu kişisel veridir. Yalnız portföy sahibi ve açık yetkili görür, dışa aktarma
  audit'e yazılır. Tacir olan carinin ticari bilgisi kişisel veri değildir, ama şahıs şirketi carisi kişisel veri sayılır;
  bu ayrım `obs_iys_customertype` (Bireysel / Tacir) ile yapılır. İzin çelişkisi raporu hukuk için tutulur. Kayıp riski
  puanı cariye aleyhe otomatik bir sonuç doğurmaz (limit kesme, fiyat değiştirme yok; md. 11).
- **Güvenlik bulguları.** Düz metin şifreler ekranda gösterilmez, yalnız "şu tabloda şu kolon şifre içeriyor, N satır"
  bilgisi BT'ye yetkiyle gösterilir. Değer okunmaz.
- Zeki AI sohbeti finans sorularını cevaplıyor (`chat_scope.py`). Cari soruları finans kapsamında sayılabilir, ama cevapta
  kişi verisi dönmemeli.

## 9. Kapsam önerisi

**İlk sürüm**
- Cari değer ve kayıp riski: Logo (iki yıl kopyası) + CRM sipariş. Kurallı puan ve nedenler: son alımdan bu yana geçen süre
  ile carinin kendi medyan alım aralığının oranı, 12 ay net değişimi, iade oranı değişimi.
- Temsilci portföy görünümü (telefon uyumlu), aksiyon kaydı ve 30 gün sonra sonuç.
- CRM veri sağlığı: Logo bağı yok, olası tekrar (normalleştirilmiş ad + il + vergi dairesi / Logo kodu), sahipsiz ya da
  ortak hesaba ait kayıt, eksik kanal, izin çelişkisi. "CRM'de düzeltildi" işareti ve ertesi gün doğrulaması.
- Güvenlik bulgusu listesi (yalnız BT yetkisiyle).
- Zeki AI risk nedeni özeti.

**Sonraki sürüm**
- İstatistiksel kayıp modeli (geçmiş kayıplarla sınanmış) ve CLV tahmini; ancak kurallı puan geriye dönük sınandıktan sonra.
- Satış hedefi ↔ gerçekleşen, temsilci düzeyinde (bölge eşlemesi düzeltilince).
- İletişim planı: izinli cari yetkililerine toplu ileti (M24 ile, onayla).
- CRM Web API yetkisi gelince izin ve veri durumu alanlarının yazılması.
- Memnuniyet anketi (bugün veri yok).

**Mevcut kodda yeniden kullanılacaklar**
- Logo katalog ölçüleri ve kayıtlı SQL'ler: `configs/semantic/knowledge/logo/knowledge/sql/m-teri-yo-unla-mas-2026-net-ciroya-sat-eksi-iade-g-re-ilk-10.md`,
  `en-cok-iade-alan-10-musteri-kimler.md`, `kanal-bazinda-net-ciro-nedir.md`, `ortalama-tahsilat-suresi-dso.md`.
- `backend/semantic_bridge/people.py` (CRM kullanıcı ↔ AD eşlemesi, temsilci adı).
- `backend/semantic_bridge/author_relations.py` (aksiyon/görüşme kaydı deseni; M7).
- `alerts.py`, `board.py`, `reports.py`, `access.py`, `admin.py` audit.
- Kişi verisi süzgeci M37 ile ortak (`crm_people_rules.py` önerisi).

## 10. Uzmanlara sorulacak sorular

1. (Satış) "Kaybedilmiş cari" sizce kaç gün alım yapmayan caridir? Kanala göre (kitapçı, dağıtıcı, okul) fark var mı?
2. (Satış) Temsilci ↔ cari sahipliğinin doğru kaynağı hangisi: `new_MerkezMusteriTemsilcisi`, `OwnerId` ya da il bazında
   temsilci mi?
3. (BT) CRM'de tekrarlı cari için bir birleştirme kuralı var mı? Birleştirme kim tarafından yapılıyor?
4. (Muhasebe) Logo bağı olmayan yaklaşık 20,9 bin cari nedir (aday, okul, kapanmış)? Temizlenebilir mi?
5. (Yönetim) Cari değeri net ciro mu, brüt kâr mı ile ölçülmeli? (Kâr tanımı katalogda iş teyidi bekliyor.)

## 11. Başarı ölçütü

- Risk listesine giren carilerin 90 gün içinde yeniden alım oranı; aksiyon alınanlarla alınmayanların karşılaştırması.
- Geriye dönük sınama: geçen yıl bu kuralla "riskli" çıkan carilerin gerçekten kaybolma oranı. Kural buna göre ayarlanır.
- Veri sağlığı puanının aylık artışı, açık bulgu sayısının düşüşü.
- Temsilci kullanımı: haftada en az bir kez açan temsilci oranı, yazılan aksiyon sayısı.
- Güvenlik bulgularının kapanması (BT).

## 12. Uzman gözüyle en iyi sistem

*15 yıllık bir satış ve müşteri ilişkileri müdürünün gözünden (uzman görüşü, TİMAŞ verisine dayanmaz).*

Toptan satış yapan iyi şirketlerde CRM bir "kayıt defteri" değil bir "iş listesi"dir. (1) **Hesap sağlığı puanı:** her
müşteri için alım sıklığı, hacim eğilimi, iade, tahsilat ve temas tek puanda toplanır. Puanın nedeni görünür olur ("alım
aralığı açıldı"). (2) **Sonraki en iyi aksiyon:** sistem temsilciye "bu hafta şu 8 cariyi ara, nedeni şu" der. Temsilci
aksiyonu kaydeder, sistem sonucu ölçer. (3) **Veri yönetişimi:** tekrar, eksik ve sahipsiz kayıt bir sahip ve süreyle
kapanır. Veri kalitesi yönetimin izlediği bir göstergedir. (4) **Tek müşteri görünümü:** sipariş (CRM), fatura ve tahsilat
(ERP), ziyaret ve hedef tek ekranda durur.

TİMAŞ için mükemmel sistem: Logo'nun gerçekleşmiş satışı ile CRM'in sipariş ve ziyareti tek cari sayfasında birleşir.
Temsilci sabah telefonunda kendi riskli carilerini nedenleriyle görür, ziyaretten sonra aksiyonunu yazar. Müdür hangi
aksiyonun işe yaradığını çeyrek sonunda veriyle görür. CRM'in veri sağlığı da her ay puanlanır.

**Uzmanın bir günü (sistemle; bölge satış müdürü)**
- 08:30 Telefonda pazartesi özeti: "Bölgende 7 cari yüksek riske geçti. En büyüğü X Kitabevi: alım aralığı 21 günden 58
  güne çıktı."
- 09:00 Masaüstünde *Cariler* → bölge süzgeci. X Kitabevi ayrıntısı: son 12 ay −%34, çocuk kategorisinde düşüş, iade
  artmamış. Zeki AI özeti: "Çocuk kitaplarında alım durdu; son ziyaret 4 ay önce."
- 09:15 Temsilciye aksiyon atar: "Bu hafta ziyaret, çocuk yeni çıkanlar ve okul dönemi kampanyası." Termin cuma.
- 11:00 Temsilcilerle haftalık toplantıda portföy tablosu açık: her temsilcinin riskli cari sayısı ve geçen hafta
  kapattığı aksiyonlar.
- 15:00 Geçen çeyrekte aksiyon alınan 40 riskli carinin 26'sı yeniden almış, alınmayanlarda oran daha düşük. Sonucu
  yönetim özetine ekler.
- 17:00 CRM yöneticisi veri sağlığında Logo bağı olmayan 120 aktif cariyi temizlemiş; ertesi gün doğrulanacak.

**"Bunu görürsem hemen kullanırım"**
1. Nedeni yazılı risk listesi ("neden riskli" tek cümle).
2. Temsilciye telefonda kendi carileri, aksiyon tek dokunuş.
3. Aksiyonun sonucunun kendiliğinden ölçülmesi (30/90 gün sonra alım).

**"Bunu yaparsanız kullanmam"**
1. Nedeni açıklanamayan "yapay zekâ skoru". Satışçı güvenmez.
2. Her temsilciye bütün şirketi göstermek ya da hiç kimseye kendi portföyünü gösterememek (sahiplik bozukluğunu çözmeden).
3. Donmuş Logo verisiyle "90 gündür almıyor" demek. Kesim tarihi hesaba katılmalı, yoksa herkes riskli görünür.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Cari eşleme | `LG_411_CLCARD`, `LG_211_CLCARD` (`CODE`, `DEFINITION_`, `SPECODE2`, `LOGICALREF`) | `AccountBase.new_logicalref`, `AccountNumber`/kod alanı | — | İki firma kopyası `CODE` ile birleşir; kurallı |
| Cari değer (12 ay, önceki 12 ay) | `LG_411_01_INVOICE` + `LG_211_01_INVOICE` (`TRCODE 7,8,9` satış, `2,3` iade, `CANCELLED = 0`), `net_ciro` tanımı; kitap/kategori için `STLINE.LINENET`, faturalı satır | — | — | Rakam SQL'den; kesim tarihi pencerenin sonu |
| Alım aralığı ve risk puanı | Fatura tarihleri (`DATE_`) cari başına | Sipariş tarihleri `new_siparisBase.new_siparistarihi`, durum | — | Kurallı puan: son alımdan geçen gün ÷ medyan aralık, 12 ay değişim, iade değişimi |
| Risk nedeni özeti | Kategori/yayınevi kırılımı (`V_SatisRaporu_411/211`) | Son ziyaret `new_etkinlikBase.new_GercZiyTarihi` | Rakamlardan 1–2 cümle neden ve aksiyon önerisi yazar | Satışçının anlayacağı dil; rakam uydurmaz |
| Olası tekrar kayıt | — | `AccountBase.Name`, il, vergi dairesi, `new_logicalref`, `CreatedOn` | Kurallı aday çiftleri için "aynı firma / farklı / belirsiz" kapalı küme kararı (tek token + olasılık); yalnız ticari ad ve il gider | Bulanık ad eşleşmesi (kısaltma, "Ltd. Şti.") kuralla zor |
| Logo bağı yok, eksik alan, sahipsiz | `CLCARD` | `new_logicalref`, `new_FirmaKanal`, `OwnerId` = ortak hesap, `statecode` | — | Kurallı |
| İzin çelişkisi | — | `DoNotEMail`, `DoNotBulkEMail`, `obs_donotsms`, `obs_iys_customertype`; gönderim `obs_kampanyagonderimleriBase.obs_firmaid` | — | Kurallı |
| Güvenlik bulguları | `L_CAPIWEBCONN`, `LogoEntegrations` (yalnız varlık; içerik okunmaz) | `new_webservicelogBase.new_requestJSON` (şifre alanı varlığı), `new_webuser` şifre kolonu | — | Değer okunmadan "var" bilgisi |
| Doğal dil soru | `net_ciro`, `iade_orani`, `kanal_net_ciro`, `vadesi_gecmis_alacak_fifo` | Katalogdaki CRM tabloları | Soru → SQL | Mevcut hat |

Model `rt.llm_for("musteri", priority)` ile çağrılır. Gece toplu tekrar kontrolü düşük öncelikle çalışır. Modele kişi adı,
telefon ya da e-posta gönderilmez; yalnız ticari unvan, il ve rakamlar gider.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/musteri.py`: depo, risk puanı, veri sağlığı kuralları, portföy süzgeci.
- `backend/semantic_bridge/musteri_sources.py`: Logo (iki firma kopyası, kolon adıyla birleştirme, `CODE` eşlemesi), CRM
  (`connector_from_file`).
- `backend/semantic_bridge/musteri_api.py`: `register(app, rt=..., can=..., audit=...)`.
- Ortak yardımcı: `backend/semantic_bridge/crm_people_rules.py` (kişi kolonu beyaz listesi, okur/katkıcı/kurum ayrımı;
  M37 ile ortak).

**Tablolar** (`semantic_musteri_` öneki)
- `semantic_musteri_accounts` (tenant_id, cari_kodu, crm_account_id, ad, kanal, bolge, temsilci, bireysel_mi,
  son_fatura, son_siparis, son_ziyaret, net_12ay, net_onceki_12ay, degisim, fatura_12ay, medyan_aralik_gun,
  iade_orani_12ay, iade_orani_onceki, risk_puani, risk_duzeyi, nedenler_json, neden_ozeti, logo_kesim, hesaplandi_at)
- `semantic_musteri_actions` (id, cari_kodu, tur [arama|ziyaret|kampanya|diger], aciklama, sahip, termin, durum,
  sonuc_30g, sonuc_90g, yazan, tarih)
- `semantic_musteri_health_findings` (id, tenant_id, tur [logo_bagi_yok|olasi_tekrar|eksik_kanal|sahipsiz|
  ortak_hesap|izin_celiskisi|guvenlik], varlik [account|contact|lead], kayit_id, eslesen_kayit_id, olasilik, ozet,
  onem, durum [acik|crmde_duzeltildi|dogrulandi|yoksay], isaretleyen, ilk_goruldu, son_goruldu)
- `semantic_musteri_health_score` (tenant_id, tarih, puan, bulgu_sayilari_json)
- `semantic_musteri_segments` (id, ad, kural_json, boyut, tarih): cari segmentleri (kişi değil).

**Uçlar** (`/api/v1/musteri/*`)
- `GET overview` · `GET accounts?kanal=&bolge=&temsilci=&risk=&page=` (portföy süzgeci köprüde zorunlu)
- `GET accounts/{cari_kodu}` · `GET accounts/{cari_kodu}/monthly` · `POST accounts/{cari_kodu}/actions` ·
  `PATCH actions/{id}`
- `GET my-portfolio` (temsilci; telefon) · `GET health?tur=&durum=&page=` · `POST health/{id}/mark`
- `GET health/score-history` · `GET segments` · `POST run-due` (sistem jetonu)

**Ekranlar**: `src/canvas/musteri/` → `CustomersHome.tsx`, `AccountsScreen.tsx`, `AccountDetail.tsx`,
`PortfolioPhone.tsx`, `DataHealthScreen.tsx`. Rotalar `/timas/musteri-iliskileri`, `/musteri-iliskileri/cariler`,
`/musteri-iliskileri/cari/:kod`, `/musteri-iliskileri/portfoyum`, `/musteri-iliskileri/veri-sagligi`. Menü:
`navModel.ts` Kayıtlar alanında "Müşteri ilişkileri" (Kişiler'in yanında); veri sağlığı aynı öğenin alt rotası (`also`).
Kampüs: `ModulesMenu.tsx` `LIVE` içine `M38: '/musteri-iliskileri'`, `GROUP_HOME` içine `'Müşteri & Pazar'`.

**Yetki**: `sayfa:musteri-iliskileri`, `sayfa:musteri-veri-sagligi`; `ozellik:musteri.herkesinki` (**explicit**),
`ozellik:musteri.eylem-yaz`, `ozellik:musteri.bulgu-isaretle`, `ozellik:musteri.guvenlik-bulgulari` (**explicit**); mevcut
`ozellik:veri.disa-aktar`. Portföy süzgeci köprüde uygulanır: `herkesinki` yoksa yalnız temsilcisi oturumdaki AD hesabına
eşlenen cariler döner (`people.py` CRM `SystemUser` ↔ AD eşlemesi).

**Zamanlayıcı**: `scripts/server/timas-musteri.timer`, her gece 04:15. Cari değer ve risk (Logo iki kopya + CRM), veri
sağlığı taraması, bulguların kapanması ve doğrulanması, aksiyonların 30/90 gün sonucu. Pazartesi özet e-postası. İlk tur
elle; Logo okuması ağır olduğu için cari başına değil, tek toplu sorguyla (`GROUP BY CLIENTREF`).

**Kabul testleri** (doğrudan bağlantıyla)
1. Cari 12 ay net: `SELECT c.CODE, SUM(CASE WHEN i.TRCODE IN (7,8,9) THEN i.NETTOTAL ELSE -i.NETTOTAL END) FROM
   LG_411_01_INVOICE i JOIN LG_411_CLCARD c ON c.LOGICALREF = i.CLIENTREF WHERE i.CANCELLED = 0 AND
   i.TRCODE IN (2,3,7,8,9) AND i.DATE_ > DATEADD(month, -12, :kesim) GROUP BY c.CODE` + aynısı `LG_211_01_INVOICE` /
   `LG_211_CLCARD` ile, `CODE` üzerinden toplanır. 20 cari ekranla kuruşu kuruşuna aynı.
2. Son fatura: aynı iki kopyada `MAX(i.DATE_)` cari başına = ekrandaki "son fatura".
3. Logo bağı: `SELECT COUNT(*) FROM dbo.AccountBase WHERE statecode = 0 AND new_logicalref IS NULL` ve bağı olup Logo'da
   bulunmayan sayısı (CLCARD'a karşı; hangi firmaya bağlandığı önce ölçülür) = veri sağlığındaki "Logo bağı yok".
4. Kanal dağılımı: `SELECT new_FirmaKanal, COUNT(*) FROM dbo.AccountBase WHERE statecode = 0 GROUP BY new_FirmaKanal`
   = özet ekranı kanal sayıları.
5. Ortak hesap: `SELECT COUNT(*) FROM dbo.AccountBase a JOIN dbo.SystemUserBase u ON u.SystemUserId = a.OwnerId WHERE
   u.FullName = 'Timas CRM'` = "ortak hesaba ait cari" bulgusu.
6. Kanal toplamı: 2026 `SPECODE2` kanal net cirosu (kayıtlı SQL `kanal-bazinda-net-ciro-nedir.md`) = özet ekranı kanal
   değerleri toplamı.
7. Portföy güvenliği: temsilci rolündeki test oturumuyla (`timasai` ile kısa oturum; bellek: test-login-as-timasai)
   `GET accounts` yalnız o temsilcinin carilerini döndürür; `herkesinki` yetkisiyle hepsini.
8. İlk 10 cari yoğunlaşması: kayıtlı SQL `m-teri-yo-unla-mas-2026-net-ciroya-sat-eksi-iade-g-re-ilk-10.md` = cari
   listesinin 2026 değere göre ilk 10'u.

**Bağımlılık**: Yetki mekanizması (Aşama A/B) kurulu olmalı (portföy süzgeci ve explicit özellikler). M37 ile ortak
`crm_people_rules.py` önce yazılır ya da M38 içinde başlayıp M37 onu alır. M59 (kredi riski) ile paralel; M59 bitince cari
ayrıntısına risk limiti eklenir.

**Tahmini büyüklük**: L (3+ gün). Değer ve risk hesabı M, veri sağlığı M, ekranlar ve telefon portföyü M.
