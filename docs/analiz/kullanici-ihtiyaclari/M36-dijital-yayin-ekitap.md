# M36 — Dijital Yayın ve e-Kitap Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M36.txt` (ZEKİ_Moduller3.html'den; girdi kaynağı
M14), `specs/M14.txt` başlığı, `specs/M41.txt`, `specs/ANALIZ-EK.md`; depoda `docs/analiz/seo-geo-modul-2026-09-25.md`
(«CRM kitap kartı ve dijital haklar»), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `PROJECT-MEMORY.md` (Kitap Tasarım Stüdyosu, sesli e-kitap),
`apps/editor/src/editor/production/epub.py`, `backend/semantic_bridge/editorial_studio_epub.py`,
`backend/semantic_bridge/seo_geo/crm.py`, `backend/semantic_bridge/contracts.py`, `contracts_terms.py`,
`configs/semantic/knowledge/crm/table_descriptions.json` (2026-09-09); bellek: crm-digital-rights-fields,
editor-book-visuals-qwen-image, no-tech-names-on-screens, logo-155-frozen-copy. `ZEKİ_Veri_Haritasi2.html` verilen
klasörde yok. Sunucuya bağlanılmadı; sayılar depodaki tarihli ölçümlerdir.

## 1. Modül ne işe yarar

İş tanımına göre modülün iki işi var. Dijital dağıtım (K1): Kindle, Kobo, Apple Books ve Google Play'e otomatik yükleme,
EPUB/PDF dönüşümü ve kalite denetimi, üst veri ve fiyat eşitlemesi, yeni baskıda dijital sürümün güncellenmesi. Dijital
strateji (K2): dijital ile basılı fiyat dengesi, abonelik platformu (Storytel, Scribd) anlaşma analizi, sesli kitap fırsatı,
dijitale özel promosyon. Çıktılar: platform dağıtım raporu, dijital satış panosu, strateji raporu.

TİMAŞ'ın bugünkü durumu: dijital hak ve ürün bilgisi CRM'de dağınık duruyor, dağıtım ve satış verisi ise hiç görünmüyor.
Sözleşmede e-kitap, sesli kitap, Z-kitap ve internette gösterim hakları ayrı alanlar. 7.057 aktif Telif Alış sözleşmesinin
6.629'unda e-kitap hakkı var (2026-09-26). Kitap kartında e-kitap barkodu, e-kitap stok kodu, e-ISBN ve "E-Pub Durumu"
alanları var. Ürün tipi seçeneklerinde "Ekitap" ve "SesliKitap" bulunuyor. Üretim kaydında "Grafik Aşamasında (Ekitap)" ve
"Doküman Hazır (Ekitap)" durumları var. Yani e-kitap üretimi CRM'de izleniyor. Ancak hangi kitabın hangi platformda
yayında olduğu, ne sattığı ve hangi kitabın hakkı olduğu hâlde dijitale çıkmadığı tek bir yerde görünmüyor. Portalın Kitap
Tasarım Stüdyosu basılı kitabın sayfa planından EPUB 3 üretip denetleyebiliyor (dalda; henüz kurulmadı).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Dijital yayın sorumlusu | Belirli bir birimde olduğuna dair kanıt yok. E-kitap üretim durumları üretim kaydında "Grafik" aşamasında görünüyor; işi grafik/üretim ekibinin yürüttüğü **varsayım** | Haftalık | Masaüstü |
| Telif / haklar uzmanı | Telif birimi. Sözleşme iş akışında "Telif Hakları" adımı var (kanıt) | Yeni kitapta ve "incele" kaydında | Masaüstü |
| Grafik / üretim (EPUB hazırlama) | Grafik (CRM ekip üyeliği: 13 kişi) | Kitap başına | Masaüstü |
| Yayın yönetmeni (hangi kitap dijitale çıkar) | Kültür ve Çocuk Editörya | Aylık | Masaüstü, telefon |
| Finans (dijital gelir, e-kitap telifi) | Mali İşler. E-kitap telif oranı sözleşmede (`new_e_kitap_telif`) ve M6 hakediş hesabı e-kitap stok kodunu okuyor (kanıt: `contracts.py`) | Aylık / çeyreklik | Masaüstü |
| Pazarlama (dijital promosyon) | Pazarlama — **varsayım** | Kampanya dönemlerinde | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Dijital yayın sorumlusu.** Platformlara yükleme her platformun kendi yayıncı panelinden ya da bir dağıtıcı üzerinden
  yapılıyor (**varsayım**). CRM'de "Amazon Kindle US" diye bir cari kartı var. Bu, en az bir dijital kanalın cari/fatura
  ilişkisiyle yürüdüğünü gösteriyor. Hangi kitabın hangi platformda olduğu büyük olasılıkla Excel'de tutuluyor
  (**varsayım**).
- **Telif uzmanı.** E-kitap hakkını sözleşmeden kontrol ediyor. SEO & GEO modülünün "Haklar ve CRM" ekranı internette
  gösterim hakkını kitap başına hesaplıyor (var / eksik / yok / incele / koruma dışı). Aynı okuma e-kitap ve Z-kitap
  bayraklarını da çekiyor (`seo_geo/crm.py`), ama ayrı bir "e-kitap hakkı" kararı ekranda yok. 738 sözleşmede serbest
  metinli hak notu var ("özel maddeler var" gibi); bunlar insan kararı ister.
- **Grafik / üretim.** EPUB dosyası elle ya da dış bir araçla hazırlanıyor (**varsayım**). Stüdyo EPUB üretimi (sabit
  sayfa ya da akışkan, erişilebilirlik üst verisi, e-ISBN yoksa uyarı, yapısal denetim) dalda bekliyor.
- **Finans.** Platform ya da dağıtıcı satış raporu (genellikle aylık, döviz cinsinden) e-postayla geliyor ve elle
  işleniyor (**varsayım**). M6 hakediş hesabı e-kitap satırını Logo'daki e-kitap stok kodundan arıyor. Dijital satışın
  Logo'ya bu kodla fatura olarak girip girmediği **ölçülecek**.
- **Sıkıntı.** Hak (CRM sözleşme), ürün (CRM kitap), dosya (üretim), platform durumu (Excel ya da panel) ve gelir (rapor
  ya da Logo) beş ayrı yerde duruyor.

## 4. İhtiyaçlar ve acı noktaları

**Dijital yayın sorumlusu**
1. Kitap başına tek satırda: hak, e-ISBN, EPUB var mı, hangi platformda yayında.
2. Fırsat listesi: hakkı olan, basılı satışı iyi, e-kitabı olmayan kitaplar.
3. Yeni baskıda dijital sürümün güncellenmesi gerekenler (içerik ya da kapak değişti).
4. Platformlara verilecek üst veri paketi.

**Telif uzmanı**
1. E-kitap ve sesli kitap hakkı eksik ya da belirsiz olup dijitalde satışta olan kitaplar (hukuki risk).
2. "İncele" kayıtlarında kararını kaydedebilmek ve bu kararın bir daha sorulmaması.

**Finans**
1. Platform raporlarını bir kez yükleyip kitaba eşlemek, dijital geliri aylık görmek.
2. E-kitap telifi için kitap bazında dijital satış.

**Yayın yönetmeni**
1. Dijital ile basılı satış karşılaştırması (kitap ve kategori bazında).
2. Sesli kitap için aday kitaplar.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Dijital yayın sorumlusu olarak her kitabın hak, dosya ve platform durumunu tek satırda görmek istiyorum, çünkü bugün beş
  yere bakıyorum.
- Dijital yayın sorumlusu olarak hakkı olan ama e-kitabı olmayan çok satan kitapları görmek istiyorum, çünkü dijitale
  öncelikle bunları çıkaracağım.
- Telif uzmanı olarak e-kitap hakkı "eksik" ya da "incele" olan ve dijitalde satışta görünen kitapları görmek istiyorum,
  çünkü hak sahibiyle konuşmam gerekiyor.
- Telif uzmanı olarak "incele" kaydına kararımı ve gerekçemi yazmak istiyorum, çünkü aynı sözleşme yeniden önüme gelmemeli.
- Finans uzmanı olarak platformun aylık satış raporunu yükleyip kitaplarla eşleşmeyen satırları görmek istiyorum, çünkü
  telifi eksiksiz hesaplamalıyım.
- Yayın yönetmeni olarak dijital satışın basılı satışa oranını kategori bazında görmek istiyorum, çünkü dijital yatırıma
  karar vereceğim.

**Ana ekranlar ve akış**
- *Dijital katalog* (ilk açılış). Göstergeler: dijitalde yayında kitap, hakkı olup dijitale çıkmamış kitap, hak riski olan
  kitap, son yüklenen rapor dönemi. Altında kitap tablosu: hak (e-kitap / sesli), e-ISBN, EPUB durumu, platform çipleri,
  basılı ve dijital fiyat.
- *Fırsatlar*. Basılı satış × hak × dijital yokluğu; sesli kitap adayları.
- *Satış*. Rapor yükleme (Excel/CSV), eşleme önizlemesi, onay; aylık gelir, platform ve kitap kırılımı.
- *Kitap ayrıntısı*. Sözleşmeler ve hak bayrakları, üretim durumu, stüdyo EPUB denetim sonucu, platform geçmişi.
- Tık sayıları: bir kitabın platform durumunu işaretlemek 2 tık; rapor yüklemek 3 adım (dosya → eşleme önizlemesi → onay);
  fırsat listesini indirmek 1 tık.
- Telefonda göstergeler ve fırsat listesi okunur. Rapor yükleme masaüstünde yapılır.

**Zeki AI'a soracakları örnek sorular**
1. "E-kitap hakkımız olup e-kitabı çıkmamış, geçen yıl 5.000'den fazla satan kitaplar hangileri?"
2. "Geçen çeyrekte dijital gelirimiz platformlara göre nasıl dağıldı?"
3. "Sesli kitap hakkı olan çocuk kitaplarımız hangileri?"
4. "Dijital fiyatı basılı fiyatının yüzde 70'inden yüksek kitaplar hangileri?"
5. "Yeni baskısı çıkıp e-kitabı eski baskıda kalan kitaplar var mı?"
6. "Hangi e-kitapların sözleşmesinde özel hak notu var?"

**Otomasyon katmanı**
- K1: Gece CRM'den hak, kitap ve üretim durumu okunur; fırsat puanı hesaplanır; stüdyoda üretilen EPUB'un denetim sonucu
  alınır. Yüklenen rapor satırları kitaplara kurallı eşlenir (e-ISBN, ISBN, stok kodu).
- K2: Zeki AI eşleşmeyen rapor satırları için aday kitap önerir (adla bulanık eşleşme), insan onaylar. Dijital fiyat
  önerisi ve platform tanıtım metni Zeki AI'dan gelir, onay insanda.
- K3: Abonelik platformu ve sesli kitap yatırımı için Zeki AI özet ve senaryo hazırlar, ekip karar verir.
- K4: Platforma yükleme insan tarafından yapılır. İş tanımındaki "otomatik yükleme" platform ya da dağıtıcı erişimi
  (kimlik bilgisi, sözleşme) ve yazma izni olmadan yapılamaz. Ayrı bir kullanıcı kararı gerektirir.

**Bildirim / uyarı**
- Telif uzmanına: hak riski listesine yeni kitap girdiğinde e-posta.
- Dijital sorumluya: yeni baskı ya da kapak değişikliği olan dijital kitap olduğunda haftalık e-posta (`new_kitapgecmisi`
  baskı ve kapak satırlarından).
- Finansa: beklenen aylık rapor gelmediyse (dönem kapanışından N gün sonra) hatırlatma.

**Onay ve yetki**
- `sayfa:dijital-yayin`: katalog, fırsatlar ve kitap ayrıntısını görür.
- `ozellik:dijital.durum-yaz`: platform durumu ve not girer.
- `ozellik:dijital.rapor-yukle`: satış raporu yükler ve eşlemeyi onaylar.
- `ozellik:dijital.hak-karari` (explicit, telif birimi): "incele" kaydına karar yazar.
- `ozellik:dijital.fiyat-onay` (explicit): dijital fiyat kararını onaylar.
- Satış ve gelir görünümü finans verisidir. Ayrı sayfa anahtarı önerilir: `sayfa:dijital-satis`.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| E-kitap, sesli kitap, Z-kitap, iletim hakkı | CRM `new_sozlesmeBase` (`new_EKitap`, `new_SesliKitapHakki`, `new_ZKitapHakki`, `new_iletimhakki`, `new_haklaraciklama`, `new_ekitapmuvafakatnamesi`), yalnız `new_SozlesmeTipi = 5` | Ölçüldü: aktif Telif Alış 7.057, e-kitap hakkı 6.629, iletim 6.783. `seo_geo/crm.py` bayrakları okuyor | Sesli kitap hakkı sayısı **ölçülecek** |
| E-kitap telif oranı | CRM `new_e_kitap_telif`, `new_SesliKitap` (%) | M6 okuyor (`contracts.py`) | — |
| Dijital ürün kimliği | CRM `new_kitapBase.new_ekitapisbn`, `new_EKitapBarkod`, `new_EKitapStokKodu`, `new_EPubDurumu`, `new_Tip` (8 Ekitap, 9 SesliKitap); Product `ProductTypeCode` (3/8 E-Kitap, 9 SesliKitap) | Alanlar biliniyor | Doluluk ve Tip=8/9 kayıt sayısı **ölçülecek** |
| E-kitap üretim durumu | CRM üretim kaydı ("Grafik Aşamasında (Ekitap)", "Doküman Hazır (Ekitap)") | Etiketler biliniyor | Kayıt sayısı **ölçülecek** |
| EPUB dosyası ve denetimi | Stüdyo (`epub.py`: `epub/state.json`) | Dalda, kurulmadı | Stüdyo dışında hazırlanan EPUB'lar için dosya yükleme + aynı denetim |
| Basılı satış (fırsat için) | Logo `V_SatisRaporu_411/211` | Kullanılıyor | Son fatura 2026-08-17 |
| Dijital satış | Platform/dağıtıcı raporları (dış) ya da Logo'da e-kitap stok koduyla faturalar | Logo'da olup olmadığı **ölçülecek**; M6 bu yolu varsayıyor | **En büyük boşluk:** rapor biçimleri, dönem ve para birimi Timaş'tan alınacak |
| Hangi platformda yayında | Platform panelleri / dağıtıcı (dış) | Hiç veri yok | Kullanıcı girer ya da rapordan çıkarılır |
| Okur davranışı (sayfa tamamlama) | Platform raporları | Yok. Çoğu platform yayıncıya vermez (**varsayım**) | İlk sürümde yok |
| Rakip dijital fiyat | Dış | Yok. Kazıma yapılmaz | M39'a bırakılır |

## 7. Diğer modüllerle bağ

- Girdi alır: M14 Mizanpaj ve Kitap Tasarım Stüdyosu (sayfa planı, EPUB, sesli e-kitap), M6/M54 Telif (hak ve oran), M13
  Kapak (kapak görseli), M9 Fiyatlama (basılı fiyat), M11 (yeni baskı bilgisi), M26 GEO / SEO "Kimlik ve bilgi paneli"
  (Google Kitaplar hazırlığı, önizleme hakkı).
- Çıktı verir: M6/M54 (dijital satış → e-kitap hakedişi), M45 Finansal Raporlama (dijital gelir), M35 Kampanya (dijitale
  özel promosyon), M41 Amazon ve Uluslararası (Kindle), M39 (dijital pazar payı girdisi), DYK.

## 8. Kısıtlar

- Platformlara ya da T-soft'a hiçbir şey gönderilmez. Otomatik yükleme ayrı bir kullanıcı kararı ve erişim olmadan
  kurulmaz.
- CRM'e yazılmaz. Platform durumu, hak kararı notu ve rapor satırları köprünün tablolarında durur. CRM'e işlenmesi gereken
  (e-ISBN, E-Pub Durumu) ekranda "CRM'e işlenecek" diye listelenir.
- Ekranda teknoloji adı yok. Stüdyonun denetim bulguları zaten Türkçe ve adsız (`epub.py`). "Zeki AI" yazılır. Platform
  adları (Kindle, Apple Books, Google Play, Storytel) kalabilir.
- Demo veri yok, sayı tavanı yok.
- Hukuk:
  - E-kitap ve sesli kitap ayrı haklardır (FSEK; sözleşmede ayrı bayrak). Hak "eksik", "yok" ya da "incele" olan kitap
    dijital dağıtıma önerilmez.
  - Çeviri eserde yabancı hak sahibinin dijital hakkı ve bölge kısıtı serbest metin notlarında olabilir; insan kararı
    gerekir.
  - Font gömme lisansı stüdyo denetiminde var.
  - DRM kararı yayınevinindir.
- Vergi: dijital ürünün vergi oranı ve platform kesintisi finans tarafından teyit edilmeli. Modül oran varsaymaz.
- KVKK: platform raporları normalde okur kişisel verisi içermez (toplam). İçerirse yüklemede o kolonlar atılır ve
  saklanmaz.
- Stüdyo EPUB üretimi GPU ve stüdyo servisine bağlı. Stüdyo dalda olduğundan ilk sürüm onu isteğe bağlı okur.

## 9. Kapsam önerisi

**İlk sürüm**
- Dijital katalog: kitap başına hak (e-kitap / sesli / iletim), e-ISBN, EPUB durumu (CRM + stüdyo), kullanıcının girdiği
  platform durumu.
- Hak riski listesi (telif birimine) ve "incele" kararlarının kaydı.
- Fırsat listesi: hakkı var + dijitali yok + basılı satış güçlü; sesli kitap adayları.
- Satış raporu yükleme (Excel/CSV), kurallı eşleme, Zeki AI'ın eşleşmeyen satır önerisi, aylık dijital gelir panosu.
- CRM'e işlenmesi gereken alanlar listesi (e-ISBN, E-Pub Durumu).

**Sonraki sürüm**
- Standart üst veri dosyası (ONIX 3.0) dışa aktarma; ekranda adı "platform üst veri dosyası".
- Stüdyo dışında hazırlanmış EPUB'u yükleyip aynı denetimden geçirme.
- Dijital fiyat önerisi (basılı fiyat, platform bandı, geçmiş dijital satış).
- Abonelik platformu senaryosu (K3) ve dijital satışın M6 hakedişine otomatik akışı.
- Platform ya da dağıtıcı API'si, kullanıcı kararıyla ve önce yalnız okuma.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/crm.py` (sözleşme hak bayrakları, `semantic_seo_crm_books`, yayın durumu etiketi).
- `backend/semantic_bridge/contracts.py`, `contracts_terms.py` (e-kitap stok kodu, `new_e_kitap_telif`, `RATE_KEYS`).
- `apps/editor/src/editor/production/epub.py` + `backend/semantic_bridge/editorial_studio_epub.py` (EPUB üretim ve
  denetim durumu).
- `backend/semantic_bridge/freelance.py` / `contracts.py` dosya yükleme deseni. `board.py`, `reports.py`, `alerts.py`,
  `access.py`.

## 10. Uzmanlara sorulacak sorular

1. (Dijital sorumlusu) E-kitaplar hangi platformlarda satılıyor ve yükleme doğrudan mı, bir dağıtıcı üzerinden mi yapılıyor?
2. (Finans) Dijital satış raporları hangi biçimde, hangi sıklıkta ve para biriminde geliyor? Logo'ya e-kitap stok koduyla
   fatura olarak işleniyor mu?
3. (Telif) E-kitap hakkı olan ama bölge ya da platform kısıtı bulunan sözleşmeler nasıl işaretleniyor? Serbest metin notu
   dışında bir yol var mı?
4. (Üretim) E-kitap dosyaları bugün kim tarafından, hangi araçla hazırlanıyor? Sabit sayfa (resimli çocuk kitabı) e-kitap
   yapılıyor mu?
5. (Yönetim) Sesli kitap ve abonelik platformları için mevcut bir anlaşma ya da görüşme var mı?

## 11. Başarı ölçütü

- Dijital katalogda platform durumu bilinen kitap oranı. Taban ilk hafta ölçülür.
- Hak riski listesinin kapanması: "eksik / yok" hakla dijitalde satışta olan kitap sayısı 0.
- Fırsat listesinden dijitale çıkan kitap sayısı (çeyreklik).
- Rapor yüklemede otomatik eşleşme oranı. Elle eşleşen satır sayısı dönemden döneme düşmeli.
- E-kitap hakedişinin rapor gelişinden sonraki hazır olma süresi.

## 12. Uzman gözüyle en iyi sistem

*Dijital yayıncılıkta 15 yıllık bir dijital ürün müdürünün gözünden (uzman görüşü, TİMAŞ verisine dayanmaz).*

İyi yayınevleri dijitali "basılı kitabın gölgesi" değil ayrı bir ürün hattı olarak yönetir. (1) **Tek kaynak dosya:** basılı
ve dijital aynı içerik kaynağından üretilir. Yeni baskıda düzeltme dijitale kendiliğinden geçer. (2) **Hak kontrolü
kapıdır:** hak sistemi "bu kitap bu bölgede bu biçimde satılabilir mi" sorusuna kitap × biçim × bölge düzeyinde cevap
verir. Yükleme bu cevapsız yapılmaz. (3) **Üst veri dağıtımı:** kitap bilgisi standart dosyayla bütün platformlara aynı
anda gider. Platform ret mesajları tek listede toplanır. (4) **Gelir mutabakatı:** her platform raporu kitaba ve sözleşmeye
eşlenir, telif hesabına akar. Eşleşmeyen satır açık iş olarak kalır. (5) **Fırsat analizi:** basılıda iyi satan ama dijitalde
olmayan kitap, sesli kitaba uygun tür (anlatı, kişisel gelişim, çocuk masalı) düzenli taranır.

TİMAŞ için mükemmel sistem: CRM hak ve kitap kartı ile stüdyonun EPUB'u birleşir. Her kitap için "dijitale hazır mı"
sorusu hak, dosya ve üst veri yönünden tek bakışta cevaplanır. Platform raporları yüklenince gelir ve telif aynı gün
hazır olur. Sesli kitap için stüdyonun seslendirmesi aday listesinden beslenir.

**Uzmanın bir günü (sistemle)**
- 09:00 Telefonda haftalık özet: "2 yeni baskının e-kitabı eski, 1 kitap hak riski listesine girdi."
- 09:30 Masaüstünde *Dijital katalog*. Hak riski satırını açar: çevirmen sözleşmesinde e-kitap hakkı yok. Telif uzmanına
  not düşer.
- 10:00 *Fırsatlar*: hakkı olan, geçen yıl çok satan, e-kitabı olmayan 30 kitap. İlk 10'u için stüdyoda EPUB işi açılmasını
  ister.
- 11:00 Stüdyoda üretilmiş bir EPUB'un denetim sonucu yeşil. Kitap satırında "EPUB hazır", e-ISBN yok uyarısı. e-ISBN'i
  CRM'e işlemek üzere listeye alır.
- 14:00 Finans platformun aylık raporunu yükler. 412 satırın 398'i eşleşir. Kalan 14 satır için Zeki AI aday önerir,
  11'i onaylanır, 3'ü açık kalır.
- 16:30 Aylık panoda dijital gelir platform kırılımıyla hazır. Yayın yönetmenine "dijital/basılı oranı kategori bazında"
  görünümünü paylaşır.

**"Bunu görürsem hemen kullanırım"**
1. Kitap başına hak + dosya + platform durumu tek satırda.
2. "Hakkımız var, dijitali yok, basılıda çok satıyor" listesi.
3. Platform raporunu yükleyince kitaba eşlenmiş gelir ve e-kitap telif girdisi.

**"Bunu yaparsanız kullanmam"**
1. Hak notu (serbest metin) olan sözleşmeyi "hak var" sayıp listeye koymak.
2. Platform durumunu otomatik bildiğini iddia edip yanlış göstermek. Bilinmeyen "bilinmiyor" yazmalı.
3. Raporu yüklerken eşleşmeyen satırları sessizce atmak.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Hak kararı (e-kitap / sesli) | — | `new_sozlesmeBase` (`new_SozlesmeTipi = 5`, `new_EKitap`, `new_SesliKitapHakki`, `new_ZKitapHakki`, `new_iletimhakki`, `statuscode`, `new_fesihtarihi`), `new_new_sozlesme_new_kitapBase`, taraf `new_sozlesmetarafiBase` | — | Kurallı (seo_geo/crm.py ile aynı mantık, biçim ayrı) |
| Hak notu (serbest metin) ön okuma | — | `new_haklaraciklama` | Notu sınıflar: "dijitali kısıtlıyor / kısıtlamıyor / belirsiz" (tek token + olasılık). Karar yine telifte | 738 notu insanın tek tek okuması yerine önceliklendirme |
| Dijital ürün kimliği | — | `new_kitapBase.new_ekitapisbn`, `new_EKitapBarkod`, `new_EKitapStokKodu`, `new_EPubDurumu`, `new_Tip` | — | Doluluk kurallı |
| EPUB hazırlık | — | Üretim kaydı durumu (Ekitap) | — | Stüdyo `epub/state.json` denetimi deterministik |
| Fırsat puanı | `V_SatisRaporu_411/211` son 12 ay adet ve net (faturalı satır) | Hak kararı, `new_Tip`, hedef kitle | Gerekçe cümlesi yazar | Rakam SQL'den, cümle modelden |
| Rapor satırı eşleme | — | e-ISBN, ISBN, stok kodu, `new_name`, `new_yazartext` | Kurallı eşleşmeyen satıra aday kitap önerir (ad + yazar benzerliği) ve olasılık verir; insan onaylar | Platform raporlarında ad biçimi farklı olur |
| Dijital satış Logo'da mı | `LG_411_01_STLINE` + `LG_411_ITEMS.CODE IN (e-kitap stok kodları)` | `new_EKitapStokKodu` | — | Kayıt sistemi Logo ise gelir oradan okunur |
| Platform tanıtım metni | — | `new_ozet`, `new_kitapspotu`, `new_kitabinonecikanyanlari` | Taslak üretir, onay insanda | Metin |
| Strateji özeti (abonelik, sesli kitap) | Basılı ve dijital satış serileri | — | Senaryo metni, rakam girdisiyle | K3; karar ekipte |
| Doğal dil soru | `net_ciro`, yayınevi performansı | Katalogdaki CRM tabloları | Soru → SQL | `chat_scope.py` kapsamı genişletilmeli |

Model `rt.llm_for("dijital", priority)` ile çağrılır. Rapor eşleme toplu olduğunda düşük öncelik. `LlmClient` doğrudan
kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/dijital.py`: depo, hak kararı (e-kitap / sesli), fırsat puanı, rapor eşleme.
- `backend/semantic_bridge/dijital_sources.py`: CRM (sözleşme, kitap, üretim durumu; `connector_from_file`), Logo (yıllık
  satış görünümü, e-kitap stok kodu satışları), stüdyo EPUB durumu (`editorial_studio` vekili üzerinden, yalnız okuma).
- `backend/semantic_bridge/dijital_api.py`: `register(app, rt=..., can=..., audit=...)`.

**Tablolar** (`semantic_dijital_` öneki)
- `semantic_dijital_titles` (tenant_id, kitap_id, stok_kodu, isbn, e_isbn, ekitap_stok_kodu, ekitap_barkod, tip,
  epub_durumu_crm, studio_epub_durumu, hak_ekitap [var|eksik|yok|incele|koruma_disi], hak_sesli, hak_notu_var,
  basili_fiyat, dijital_fiyat, basili_12ay_adet, firsat_puani, firsat_gerekcesi, okundu_at)
- `semantic_dijital_platforms` (id, ad, tur [ekitap|sesli|abonelik], dagitim [dogrudan|dagitici], para_birimi, aktif)
- `semantic_dijital_listings` (kitap_id, platform_id, durum [bilinmiyor|hazirlaniyor|yuklendi|yayinda|reddedildi|
  kaldirildi], tarih, kaynak [kullanici|rapor], not, yazan)
- `semantic_dijital_rights_decisions` (kitap_id, sozlesme_id, bicim [ekitap|sesli], karar [uygun|uygun_degil|kismi],
  gerekce, yazan, tarih)
- `semantic_dijital_imports` (id, platform_id, donem, dosya_adi, yukleyen, satir, eslesen, eslesmeyen, durum
  [onizleme|onaylandi|iptal])
- `semantic_dijital_sales` (import_id, platform_id, donem_ay, kimlik_ham, kitap_id, eslesme [kural|zeki|elle], olasilik,
  adet, brut, net, para_birimi, kur, net_tl)
- `semantic_dijital_crm_pending` (kitap_id, alan, deger, kaynak, durum): CRM'e işlenmesi gerekenler.

**Uçlar** (`/api/v1/dijital/*`)
- `GET overview` · `GET titles?hak=&durum=&q=&page=` · `GET titles/{kitap_id}`
- `PUT titles/{kitap_id}/listings/{platform_id}` · `GET opportunities?tur=ekitap|sesli`
- `GET rights-risks` · `POST rights-decisions`
- `GET platforms` · `POST platforms` · `PATCH platforms/{id}`
- `POST imports` (dosya) · `GET imports/{id}` (önizleme) · `POST imports/{id}/match` (Zeki AI önerisi) ·
  `POST imports/{id}/commit` · `DELETE imports/{id}`
- `GET sales?donem=&platform=` · `GET crm-pending` · `POST run-due` (sistem jetonu)

**Ekranlar**: `src/canvas/dijital/` → `DigitalCatalog.tsx`, `OpportunitiesScreen.tsx`, `DigitalSalesScreen.tsx`,
`ImportWizard.tsx`, `DigitalTitleDrawer.tsx`. Rotalar `/timas/dijital-yayin`, `/dijital-yayin/firsatlar`,
`/dijital-yayin/satis`, `/dijital-yayin/kitap/:id`. Menü: `navModel.ts` Editoryal alanı, "Yayına hazırlık" bölümünde
"Kitap tasarım"ın altında "Dijital yayın". Satış ekranı `sayfa:dijital-satis` ile ayrı. Kampüs: `ModulesMenu.tsx`
`LIVE` içine `M36: '/dijital-yayin'`.

**Yetki**: `sayfa:dijital-yayin`, `sayfa:dijital-satis`; `ozellik:dijital.durum-yaz`, `ozellik:dijital.rapor-yukle`,
`ozellik:dijital.hak-karari` (**explicit**), `ozellik:dijital.fiyat-onay` (**explicit**); mevcut `ozellik:veri.disa-aktar`.

**Zamanlayıcı**: `scripts/server/timas-dijital.timer`, her gece 04:00. CRM hak ve kitap okuması, fırsat puanı, stüdyo EPUB
durumunun toplanması, yeni baskı / kapak değişikliği tespiti (`new_kitapgecmisi`), rapor hatırlatması. İlk tur elle.

**Kabul testleri** (doğrudan bağlantıyla)
1. Tip sayıları: `SELECT new_Tip, COUNT(*) FROM dbo.new_kitapBase WHERE new_Tip IN (8, 9) GROUP BY new_Tip` = katalog
   üstündeki "e-kitap / sesli kitap kaydı" göstergeleri.
2. E-kitap hakkı: yürürlükteki Telif Alış sözleşmeleri üzerinden `SELECT COUNT(*) FROM dbo.new_sozlesmeBase WHERE
   new_SozlesmeTipi = 5 AND statuscode IN (100000000, 100000006, 100000007) AND new_EKitap = 1` (2026-09-26 ölçümü
   6.629, yürürlük süzgeci `seo_geo/crm.py` ile aynı) = ekrandaki sözleşme düzeyi sayı. Kitap düzeyi karar
   `semantic_seo_crm_books` ile karşılaştırılır (aynı kitapta iletim kararı ile çelişki raporu).
3. EPUB durumu: `SELECT COUNT(*) FROM dbo.new_kitapBase WHERE new_EPubDurumu = 1` = "CRM'de E-Pub: Evet" sayısı.
4. Fırsat listesi: hak = var ∧ `ISNULL(new_EKitapStokKodu,'') = ''` ∧ `new_Tip = 1` ∧ son 12 ay adet ≥ eşik
   (`V_SatisRaporu_411` + `V_SatisRaporu_211`, `Yıl*12+Ay`) → sayı ve ilk 20 kitap ekranla birebir.
5. Logo'da e-kitap satışı: `SELECT it.CODE, SUM(s.AMOUNT), SUM(s.LINENET) FROM LG_411_01_STLINE s JOIN LG_411_ITEMS it
   ON it.LOGICALREF = s.STOCKREF JOIN (VALUES …e-kitap stok kodları…) v(kod) ON v.kod = it.CODE WHERE s.TRCODE IN (7,8,9)
   AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 GROUP BY it.CODE`. Sonuç boşsa bu da bir bulgudur:
   "dijital satış Logo'da bu kodla yok" diye belgelenir, boş olmasının doğru olup olmadığı ayrıca sorgulanır (2021–2025
   kopyası).
6. Rapor yükleme: yüklenen dosyanın satır sayısı ve net toplamı = `semantic_dijital_sales` toplamı (eşleşen +
   eşleşmeyen); hiçbir satır atılmaz.
7. Hak notu: `SELECT COUNT(*) FROM dbo.new_sozlesmeBase WHERE new_SozlesmeTipi = 5 AND ISNULL(new_haklaraciklama,'') <> ''`
   (2026-09-26 ölçümü, bütün sözleşmelerde 738) = "incele" kaynağı.

**Bağımlılık**: `seo_geo/crm.py` okuması hazır, yeniden kullanılır. Stüdyo EPUB kurulumu gerekmez (varsa okunur). M6 hakediş
dijital satışı ikinci sürümde okur. M34 ve M35'ten bağımsız, paralel kodlanabilir.

**Tahmini büyüklük**: L (3+ gün). Katalog ve hak M, rapor yükleme ve eşleme M, ekranlar M.
