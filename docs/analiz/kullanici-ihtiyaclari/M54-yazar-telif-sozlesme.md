# M54 — Yazar Telif ve Sözleşme Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok; M6 bitti, M54 onun üstüne kurulur) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M54.txt`,
`specs/M6.txt`; Veri Haritası (`veri_haritasi2.txt`: «Telif Girdileri», «Sözleşme Girdileri», «Telif Ödeme Takvimi»);
`PROJECT-MEMORY.md` (M6 Sözleşmeler — yazma tarafı); `docs/GELISTIRME-GUNLUGU.md` (2026-09-27 gece ve 2026-09-28 M6 girişleri);
`backend/semantic_bridge/contracts*.py`, `src/canvas/editorial/contracts/`, `src/canvas/editorial/ContractsScreen.tsx`;
`configs/semantic/knowledge/logo/knowledge/caveats/logo-timas.md` (CRM sözleşme tutarları boş, hakediş yok),
`configs/semantic/knowledge/logo/knowledge/rules/crm-timas.md`, `configs/semantic/knowledge/crm/table_descriptions.json`
(`new_sozlesmeBase`, `new_tahsilatBase`); `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`;
`backend/semantic_bridge/access_catalog.json`, `access.py`; kullanıcı belleği: freelancer-payments-logo,
crm-digital-rights-fields, system-of-record-logo, sales-are-invoiced-lines, logo-155-frozen-copy, no-tech-names-on-screens,
no-silent-limits-rule.

## 1. Modül ne işe yarar

İş tanımına göre M54 iki şey yapar: (1) **telif hesaplama ve ödeme** — satış verisinden dönemsel telif hesabı (sözleşme
oranı × net satış × kanal), dönemsel telif beyannamesi, ödeme takvimi ve otomatik bildirim, dövizli uluslararası telif (K1);
(2) **sözleşme ve hak yönetimi** — standart şablonlar, yenileme ve süre takibi, hak ve bölge lisans haritası, tercüme ve alt
lisans hakları, uluslararası lisans fırsatları, hak ihlali uyarı mektupları (K2, hukuk onayı).

TİMAŞ'ın bugünkü sorunu: CRM'de ~14,8 bin sözleşme var ama **telif tutarı, hakediş ve ödeme hiç tutulmuyor**
(`new_teliftutari` 0 dolu, `NEW_ODEMEHAKEDISBASE` 0 satır, `NEW_ODEMEBASE` yalnız 2014; `caveats/logo-timas.md`). Telif
Logo'da yazar carisine ödeniyor ama sözleşmeye ve kitaba bağlanmıyor (`freelancer-payments-logo`). M6 bu boşluğun
**tek sözleşme** tarafını kapattı; dönemin tamamını, yazarın bütün sözleşmelerini ve hakların portföyünü yöneten katman yok.

### M6 ile M54'ün farkı

| Konu | M6 Sözleşmeler (bitti, test sunucusunda) | M54 (bu analiz) |
|---|---|---|
| Çalışma birimi | Tek sözleşme | Bir **dönem** × bütün satıştan/baskıdan ödemeli sözleşmeler; bir **hak sahibi** (yazarın bütün sözleşmeleri) |
| Hakediş | Sözleşme sayfasında elle: önizle → kaydet → onay, sözleşme başına | **Toplu dönem koşusu**: uygun bütün sözleşmeler tek seferde hesaplanır, istisnalar kuyruğa düşer, toplu onay (iki göz); onayda M6 hakedişleri oluşturulur |
| Yazara bildirim | Sözleşme başına Word hakediş bildirimi | Hak sahibi başına **birleşik telif beyannamesi** (birden çok sözleşme/kitap tek belgede) + gönderim kaydı |
| Ödeme | Sözleşme başına ödeme takvimi, «ödendi» + belge no; `/telif-sozlesme/odemeler` toplu liste | Dönem **ödeme listesi** (banka talimatı taslağı, stopaj özeti), Logo'daki gerçek ödemeyle **mutabakat** |
| Avans | Hakediş hesabında mahsup | Portföy **avans bakiyesi**: ödenen, kazanılan, kazanılmamış avans; geri dönmesi zor avans uyarısı; açılış bakiyesi girişi |
| Süre | Liste ekranında «60 günde bitiyor» süzgeci | **Yenileme takvimi ve karar akışı** (yenile / bırak / yeniden müzakere), yayınlanmama fesih süresi, sözleşmedeki rapor verme yükümlülüğü |
| Haklar | Sözleşmede hak bitleri (çoğaltma, yayma, iletim, e-kitap, sesli, çeviri…) | **Hak ve bölge haritası** (kitap × hak türü × dil/ülke × bitiş), **telif satışı** (Timaş'ın yurtdışına verdiği lisans), alt lisans/tercüme hakları, lisans fırsat listesi |
| Şablon | Sözleşme ve zeyilname metni | Yazar yazışma şablonları: beyanname e-postası, yenileme teklifi, hak ihlali uyarı mektubu |
| Kullanıcı | Telif birimi, editörya, hukuk | + muhasebe (ödeme, stopaj), CFO (yükümlülük), yabancı haklar sorumlusu |

Kısacası: **M6 defterdir (sözleşmenin kaydı), M54 telif muhasebesi ve hak portföyüdür.** M54 M6'nın tablolarını ve hesap
motorunu (`contracts_royalty.compute`) yeniden yazmaz, çağırır.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Telif hakları uzmanı (ana kullanıcı) | «Telif Hakları & Yayın Destek Birimi» — **kanıt**: CRM `new_sozlesmestatusu` 3 = «Telif Hakları & Yayın Destek Biriminde» | Her gün; dönem sonunda yoğun | Masaüstü |
| Muhasebe uzmanı (telif ödemesi, stopaj) | Muhasebe — **kanıt**: Logo «Yazarların Telif Ücreti» hizmet kartı, serbest meslek makbuzu ve giden havale hareketleri (`freelancer-payments-logo`) | Dönem sonu, ödeme günleri | Masaüstü |
| Yayın yönetmeni (yenileme kararı) | Editörya — **kanıt**: sözleşme statüsü 2 = «Yayın Yönetmeninde» | Aylık | İkisi de |
| Hukuk (sözleşme revizyonu, lisans, ihlal) | İş tanımı «Hukuk onaylar» der; birim iç mi dış avukat mı **varsayım** (CRM departman listesinde hukuk yok) | Olay bazlı | Masaüstü |
| Yabancı haklar / lisans sorumlusu | **Kanıt (faaliyet)**: CRM sözleşme tipi 1 = «Telif Satış» (Timaş yurtdışına satar), CRM tahsilat tipi «Telif Satış Tahsilatı»; kişi/birim **varsayım** | Haftalık; fuar dönemlerinde yoğun | İkisi de |
| CFO | Finans — **varsayım** | Aylık (telif yükümlülüğü, avans riski) | Telefon |
| Yazar / hak sahibi (dolaylı) | Dış kişi; portala giremez (giriş yalnız AD, `no-demo-login`) | Dönem sonunda beyanname alır | E-posta |

## 3. Bugün bu iş nasıl yapılıyor

- **Telif uzmanı:** Sözleşme CRM'de 6 adımlı akıştan geçer (editör → yayın yönetmeni → telif birimi → «YK onayı» → imza →
  giriş tamam; **kanıt**: statü seçim listesi). Satıştan ödemeli sözleşmelerde dönem hesabı CRM'de yapılmıyor (hakediş 0
  satır) → Logo satış raporu Excel'e alınıp sözleşme oranıyla elle hesaplanıyor (**varsayım**, CRM boşluğu kanıt).
  Ödeme şekli dağılımı (**kanıt**, 2026-09-27 CRM ölçümü): Tek ödeme 7.656 · Baskıdan 3.479 · Satıştan 2.020 · Satıştan
  kademeli 439; esas Net 9.100 · Brüt 4.475. Yani satıştan ödemeli ~2.459 sözleşme her dönem hesap ister. Tıkanma:
  kademe (birikmiş adet), taraf payları, avans mahsubu, döviz ve e-kitabın ayrı oranı elle hesapta hata yapmaya açık.
- **Muhasebe:** Ödeme Logo'da yazar carisine hizmet faturası/serbest meslek makbuzu ve giden havale olarak kaydediliyor
  (**kanıt**: 2026 serbest çalışan kartlarında 46 serbest meslek makbuzu, 21 giden havale; telif ödemesi aynı yolla —
  `freelancer-payments-logo`). Hangi sözleşmenin hangi döneme ait ödemesi olduğu Logo'da yok.
- **Yenileme:** CRM'de bitiş, yenileme başlangıç/bitiş, «süresiz», «yenilenme sıklığı (yıl)», «yayınlanmaması halinde fesih
  süresi (ay)», muvafakatname/ek protokol bitiş alanları var (**kanıt**: `table_descriptions.json`); takip M6 listesindeki
  60 gün süzgecine kadar elle/hatırlatmasız yapılıyordu (**varsayım**).
- **Haklar:** Hak bitleri sözleşmede (iletim 6.783 / e-kitap 6.629 aktif telif alışında; ~274 kitapta internet hakkı yok —
  **kanıt**, `crm-digital-rights-fields`); 738 sözleşmede serbest metin «haklar açıklama» var («özel maddeler var sözleşme
  incelenmeli» gibi) → insan okuyor.
- **Yabancı hak satışı:** CRM'de «Telif Satış» sözleşmeleri ve «Telif Satış Tahsilat Durumu» (yapıldı/kısmi/bekliyor/bedelsiz)
  alanı var; takibin nerede yapıldığı **varsayım** (e-posta + Excel).

## 4. İhtiyaçlar ve acı noktaları

**Telif uzmanı**
1. Dönem sonunda bütün satıştan ödemeli sözleşmeleri tek tuşla hesaplatmak, yalnız istisnalarla uğraşmak.
2. Hesabın neden öyle çıktığını satır satır görmek (kitap, ay, kanal, adet, iade, kademe, pay, avans, kur).
3. Hak sahibi başına tek beyanname; yazarın sorusuna aynı belgeyle cevap.
4. Biten/yenilenecek sözleşmelerin karar listesi ve kararın kaydı.
5. Serbest metin hak açıklamalarının hangi kitapta ne kısıt getirdiğini hızlı görmek.

**Muhasebe**
1. Onaylı dönemin ödeme listesi: kime, ne kadar, hangi para, brüt/stopaj/net.
2. Logo'daki ödemeyle portal hakedişinin eşleşmesi; ödenmemiş ya da fazla ödenmiş kalemler.
3. Muhtasar için stopaj özeti.

**Yayın yönetmeni**
1. Yenileme kararında kitabın son 3 yıl satışı, kalan stok, telif maliyeti ve kazanılmamış avans bir arada.

**Yabancı haklar**
1. Hangi kitabın hangi dil/ülke hakkı elimizde, hangisini sattık, ne zaman bitiyor.
2. Satılan hakkın telif satış tahsilatı ve yazar payının hesaplanması.

**CFO**
1. Toplam telif yükümlülüğü (tahakkuk etmiş, ödenmemiş) ve kazanılmamış avans riski.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- Telif uzmanı olarak «2026 1. yarı» dönemini açıp bütün uygun sözleşmeleri hesaplatmak istiyorum, çünkü 2.000'i aşkın
  sözleşmeyi tek tek açamam.
- Telif uzmanı olarak yalnız istisnaları (stok kodu yok, kur yok, taraf payı toplamı %100 değil, veri dönemi bitmemiş) bir
  kuyrukta görmek istiyorum, çünkü zamanım sorunlu kayda gitmeli.
- Telif uzmanı olarak bir yazarın bütün kitaplarının telifini tek beyannamede Word olarak üretip e-postayla gönderildiğini
  kaydetmek istiyorum, çünkü yazar tek belge bekliyor.
- Telif uzmanı olarak önümüzdeki 90 günde biten sözleşmeleri yenile / bırak / yeniden müzakere diye işaretlemek istiyorum,
  çünkü bir hakkın sessizce düşmesi pahalıdır.
- Muhasebe uzmanı olarak onaylı dönemin ödeme listesini banka talimatı biçiminde indirmek istiyorum, çünkü talimatı elle
  yazmak hata doğuruyor.
- Muhasebe uzmanı olarak Logo'daki yazar ödemelerinin portal hakedişleriyle eşleşmesini görmek istiyorum, çünkü çift ödeme
  ya da unutulan ödeme olmamalı.
- Yayın yönetmeni olarak yenileme kararını kitabın satışı ve kazanılmamış avansıyla birlikte vermek istiyorum, çünkü
  satmayan kitabın hakkını uzatmak para kaybıdır.
- Yabancı haklar sorumlusu olarak bir kitabın dil/ülke bazında hak durumunu tek ekranda görmek istiyorum, çünkü fuarda
  «bu hak müsait mi» sorusuna hemen cevap vermeliyim.
- CFO olarak toplam telif yükümlülüğünü ve kazanılmamış avansı görmek istiyorum, çünkü nakit planına ve bilançoya girer.

### Ana ekranlar ve akış

Öneri: Kayıtlar › Sözleşmeler altında iki yeni sayfa (M6 ile aynı alan, ayrı yetki):

1. **Telif dönemi** (`/telif-donem`): üstte dönem seçici ve koşu durumu (taslak → hesaplandı → onayda → onaylı). Sekmeler:
   *Koşu* (özet: sözleşme sayısı, toplam brüt/avans mahsubu/stopaj/net, para birimine göre; istisna sayısı),
   *İstisnalar* (neden, çözüm bağlantısı M6 sözleşme sayfasına), *Hak sahipleri* (beyanname, gönderim durumu),
   *Ödeme listesi* (muhasebe), *Mutabakat* (Logo ödemeleri ↔ hakediş), *Avans* (portföy bakiyesi), *Yenilemeler*.
2. **Haklar ve lisanslar** (`/haklar`): kitap arama → hak kartı (hak türü × dil/ülke × bitiş, kaynak sözleşme); *Telif
   satışları* (verilen lisanslar, tahsilat durumu); *Fırsatlar* (hakkı elimizde, satışı güçlü, çevirisi satılmamış kitaplar).

En sık üç işlem:
- «Dönemi hesaplat»: Telif dönemi → «Yeni koşu» → dönem seç → «Hesapla» = **3 dokunuş** (koşu arka planda; ilerleme görünür).
- «Bir yazarın beyannamesi»: Hak sahipleri → ara → «Beyanname» = **3 dokunuş**.
- «Bu ay biten sözleşmeler»: Yenilemeler sekmesi (açılışta 90 gün süzgeci) = **2 dokunuş**.

Telefonda: Yenilemeler ve hak kartı tam; koşu ve mutabakat tabloları masaüstü işidir, telefonda özet kart + liste.

### Zeki AI'a soracakları örnek sorular

- «2026 ilk yarı telif toplamı ne kadar, en çok telif alan 10 yazar kim?»
- «Kazanılmamış avansı en yüksek 20 sözleşme hangileri?»
- «Önümüzdeki 3 ayda biten ve son 12 ayda 1.000'den fazla satan kitapların sözleşmeleri?»
- «İletim hakkı olmayan ama e-kitap stok kodu açılmış kitaplar var mı?»
- «Almanca çeviri hakkını sattığımız kitaplar ve tahsilat durumu?»
- «Logo'da ödenmiş ama portalda hakedişi olmayan yazar ödemeleri?»
- «Yayınlanmaması halinde fesih süresi dolmak üzere olan sözleşmeler?»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| Dönem koşusunun hesaplanması, istisnaların ayıklanması | K1 | M6 motoru; sonuç taslaktır. |
| Koşunun onayı → M6 hakedişleri ve ödeme takvimi satırları | K2 | İki göz: hesaplatan onaylayamaz. |
| Hak sahibi beyannamesi (Word) | K1 | Onaylı koşudan. Gönderim insan tıklar. |
| Ödeme listesi, stopaj özeti | K1 | Dosya üretir; bankaya ve Logo'ya gönderim yok. |
| Logo ödemesi ↔ hakediş eşleştirme | K2 | Kural eşleştirir (cari + tutar + tarih penceresi), belirsizi insan bağlar. |
| Yenileme listesi ve öneri gerekçesi | K2 | Zeki AI satış/avans/stok verisinden gerekçe cümlesi yazar; karar yayın yönetmeninin. |
| Hak açıklaması serbest metninin sınıflandırılması | K2 | Zeki AI sınıf önerir, telif uzmanı onaylar. |
| Lisans fırsat listesi, yenileme/ihlal yazışma taslağı | K3 / K2 | Hukuk onaylar; gönderim insan. |

### Bildirim / uyarı

- Telif uzmanı: dönem sonu +5 iş günü «koşu açılmadı»; sözleşmenin rapor verme süresi dolmak üzere; bitişe 90/60/30 gün.
- Muhasebe: koşu onaylanınca ödeme listesi hazır; vadesi geçmiş telif ödemesi (M6 ödeme takvimi).
- Yayın yönetmeni: sorumlu olduğu kitapların yenileme kararı beklerken haftalık özet.
- Yazar: beyanname e-postası (kişisel veri; yalnız onaylı koşudan, insanın «gönder» dokunuşuyla).
- Kanal: e-posta + portal içi; SMS/telefon bildirimi yok.

### Onay ve yetki

| Kim | Görür | Değiştirir | Onaylar |
|---|---|---|---|
| Telif uzmanı | Hepsi | Koşu, istisna çözümü, avans açılışı, yenileme kararı taslağı, hak kartı | — |
| Telif birim yöneticisi (ya da ikinci telif uzmanı) | Hepsi | — | Koşu (hazırlayan olmamak şartıyla) |
| Muhasebe | Koşu, ödeme listesi, mutabakat | Mutabakat bağı, ödendi işareti | — |
| Yayın yönetmeni | Yenilemeler, hak kartı | — | Yenileme kararı |
| Hukuk | Hak kartı, yazışma taslakları | Şablon | Lisans, ihlal mektubu |
| CFO | Özet, avans, yükümlülük | — | — |

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Sözleşme başlığı, oranlar, ödeme şekli, esas, para, bitiş | CRM `new_sozlesmeBase` | M6 okuyor (`contracts.crm_contract`); seçim listeleri `StringMapBase`'ten; ödeme şekli dağılımı ölçüldü | `new_teliftutari` 0 dolu (tutar yok, yüzde var); kademe alanlarının doluluğu ölçülecek |
| Kitap ↔ sözleşme, stok kodu | CRM `new_new_sozlesme_new_kitapBase`, `new_kitapBase.new_StokKodu`, `new_EKitapStokKodu` | Satıştan ödemeli yürürlükteki sözleşmelerin 1.368 kitabında stok kodu dolu; 1.246 kitapta ayrı e-kitap kodu | Hazır |
| Taraflar ve payları | CRM `new_sozlesmetarafiBase` (`new_kisi`/`new_Firma`, `new_Odeme`) | M6 okuyor; payların hepsi 0 olan sözleşmede eşit bölüş + uyarı | Hak sahibi e-postası CRM `ContactBase`'te; doluluk ölçülecek |
| Grup sözleşmesi | CRM `new_anasozlesmeid` (8.814 dolu) | M6 ana sözleşmeye bağlıyor | Hazır |
| Satış (kitap × ay × satış/iade) | Logo `V_SatisRaporu_<yıl>` (faturalı, `Satır Türü = Malzeme`) | M6 hesabı bununla; 9/9 bağımsız referansla eşit | .155 donmuş (17.08.2026); dönem bu günü geçerse uyarı |
| Kur | TCMB günlük dosya (Logo kur tabloları seyrek) | M6 okuyor | Müşteri VM'inde dış erişim ölçülecek (M6 VM'e kurulmadı) |
| Önceki dönem ödemeleri ve avans mahsubu | Logo yazar cari hareketleri (serbest meslek makbuzu, giden havale), «Yazarların Telif Ücreti» kartı | Ödeme cariye yapılıyor, sözleşme/dönem bağı yok; CRM ödeme 2014 | **Kritik boşluk**: açılış avans bakiyesi ve son ödenen dönem bilinmiyor → elle girilir ya da Logo'dan önerilir, insan onaylar |
| Rapor verme süresi, yenileme, fesih süresi | CRM `new_RaporVermeSresi`, `new_SzlemeYenilenmeSklyl`, `new_imhaSuresiAy`, `new_yenilemebaslangictarihi/bitistarihi`, `new_suresizsozlesme` | Alanlar var | Doluluk ölçülecek |
| Hak bitleri | CRM `new_iletimhakki`, `new_EKitap`, `new_SesliKitapHakki`, `new_ZKitapHakki`, `new_baskadilleretercume`, `new_yabancidilecevirihakki`, `new_yurtdisitelifsatis`, `new_malihaklardevir` … | İletim/e-kitap ölçüldü (6.783 / 6.629) | **Dil/ülke/bölge alanı görülmedi** → hak haritası dil/ülke kırılımı portalda tutulur |
| Hak açıklaması (serbest metin) | CRM `new_haklaraciklama` | 738 kayıt | Sınıflandırma gerekir |
| Telif satışı (Timaş lisans verir) | CRM `new_sozlesmeBase` tip 1; `new_tahsilatBase` tip «Telif Satış Tahsilatı», `new_TahsilatDurumu` | Alanlar var | Kayıt sayısı ve doluluk ölçülecek |
| Orijinal dil, hak devreden firma | CRM `new_orjinaldili`, `new_hakdevredenfirma` | Alanlar var | Doluluk ölçülecek |
| Stopaj oranı | Mevzuat | M6 hesapta stopaj alanı var | Oran tablosu elle, tarihli |
| Hak ihlali (korsan) bildirimleri | Dış | Müşteride web taraması kapalı | Yalnız elle kayıt |

## 7. Diğer modüllerle bağ

- **Girdi alır:** M6 (sözleşme kaydı, şartlar, ödeme takvimi, hakediş motoru), Logo satış, M1 (kabul → sözleşme), M4
  (çeviri sözleşmesi), M11 Baskı önerisi (baskıdan ödemeli sözleşmelerde baskı adedi), M41 (uluslararası platform satışları).
- **Çıktı verir:** M45 (kitap bazında telif tahakkuku, telif ödeme takvimi → nakit), M46 (telif gideri gerçekleşmesi),
  M47 (hak kaybı, süresi biten sözleşme, sözleşmesiz satış riski), DYK (telif yükümlülüğü, yenileme bekleyen kritik
  sözleşmeler), SEO/GEO «Haklar ve CRM» (hak haritası tek kaynaktan), M7 (yazar ilişkisinde telif özeti).

## 8. Kısıtlar

- **CRM'e yazma yok** (AGENTS.md, 2026-09-28): yenileme kararı, hak kartı düzeltmesi, avans açılışı portal tablolarında;
  ekranda «CRM'e işlenmesi gereken fark» listesi (M6 deseni).
- **Logo'ya yazma yok**: ödeme Logo'da yapılır; portal yalnız tarih + belge no tutar ve Logo'dan okuyup eşleştirir.
- Banka dosyası yalnız indirilir; bankaya gönderim yok.
- Yazar portala giremez → beyanname e-posta/Word ile; kişisel veri (ad, e-posta, T.C./vergi no, IBAN) ekrana yalnız yetkiliye
  çıkar, IBAN ve vergi numarası CRM'den okunuyorsa ekranda maskelenir (KVKK; CRM tahsilat vergi no «hassas» listesinde —
  `crm-timas-mscrm-detay`).
- Sessiz tavan yok: M6'nın `contracts.due_list` sorgusu `.limit(2000)` ile kesiyor — M54 toplu takvimde bu kaldırılmalı ya
  da kesilirse ekranda yazmalı (`no-silent-limits-rule`).
- Ekranda teknoloji adı yok; demo veri yok; müşteride web taraması kapalı (ihlal izleme otomatik değil).
- Hukuki metin (ihlal mektubu, lisans) Zeki AI taslağıdır; hukuk onayı olmadan gönderilmez.

## 9. Kapsam önerisi

**İlk sürüm**
- Dönem koşusu (satıştan ve satıştan kademeli ödemeli, yürürlükteki sözleşmeler), istisna kuyruğu, iki gözlü onay → M6
  hakedişleri ve ödeme satırları.
- Hak sahibi beyannamesi (Word, birleşik) + gönderim kaydı.
- Ödeme listesi (CSV/Excel) + stopaj özeti.
- Avans açılış bakiyesi girişi (elle, gerekçeli) ve portföy avans tablosu.
- Yenilemeler: 90/60/30 gün, karar kaydı.

**Sonraki sürüm**
- Logo ödeme mutabakatı (cari hareketlerinden öneri + insan bağı).
- Hak ve lisans haritası (dil/ülke kırılımı portalda), telif satışları ve tahsilatı, fırsat listesi.
- Hak açıklaması sınıflandırma; yenileme/ihlal yazışma taslakları.
- Baskıdan ödemeli sözleşmelerde baskı adedinin M11/üretimden gelmesi.

**Yeniden kullanılacaklar**
- `backend/semantic_bridge/contracts_royalty.py` (`sales_sql`, `fold_sales`, `compute`, `tcmb_rate`, `data_end_sql`,
  `fingerprint`), `contracts.py` (`crm_contract` sorguları, `save_statement`, `approve_statement`, `add_payment`,
  `mark_paid`, `due_list`), `contracts_docs.py` (dış kütüphanesiz Word), `contracts_terms.py` (alanlar, `RIGHT_FROM_CRM`).
- `src/canvas/editorial/contracts/` (`StatementsTab.tsx`, `PaymentsScreen.tsx`, `ui.tsx`).
- `backend/semantic_bridge/freelance_logo.py` (Logo 2026 kopyasına kilitli cari hareket okuma), `seo_geo/crm.py` (hak
  kontrolü kuralı), `alerts.smtp_settings` (e-posta), `admin.audit`.

## 10. Uzmanlara sorulacak sorular

1. Satıştan ödemeli sözleşmelerde telif dönemi nedir (6 ay / yıl), yazara beyanname hangi ay gider, ödeme kaç gün sonra yapılır?
2. Bugün ödenen son dönem ve kalan avans bakiyeleri nerede tutuluyor (Excel dosyası varsa ilk yükleme ondan yapılabilir)?
3. Sözleşme akışındaki «YK onayı» Yönetim Kurulu mu, Yayın Kurulu mu?
4. Yabancı dil/ülke hakları (telif satışı ve alışı) bugün hangi kayıtta, dil/ülke bazında tutuluyor mu?
5. Telif ödemesi muhasebede hangi hesaba ve hangi cari türüne kaydediliyor; stopaj hangi oranlarla?

## 11. Başarı ölçütü

- Dönem hesabının süresi: bugünkü (ölçülecek, gün) → koşu + istisna çözümü 1 iş günü.
- Doğruluk: rastgele 20 sözleşmede portal hesabı = bağımsız referans sorgu (adet ve telif, kuruş toleransı 0,01).
- İstisna oranı: ilk koşuda ölçülür, her dönem düşmeli; sessizce düşen sözleşme 0 (koşu kapsamı = uygun sözleşme sayısı).
- Mutabakat: dönem sonunda eşleşmeyen Logo ödemesi ve ödenmemiş onaylı hakediş sayısı görünür ve azalır.
- Yenileme: bitiş tarihi geçmiş ama kararı girilmemiş sözleşme sayısı 0.

## 12. Uzman gözüyle en iyi sistem

Kendimi 15 yıllık bir telif hakları müdürünün yerine koyuyorum.

**İyi yayınevleri ve iyi yazılımlar bu işi nasıl yapıyor.** Büyük yayınevlerinde telif («royalty») sistemi sözleşme kaydı
ile satış verisini her dönem kendiliğinden birleştirir; yazar başına **tek ekstre** üretir (bütün kitaplar, formatlar,
kanallar; önceki bakiye, bu dönem kazanç, avans mahsubu, iade karşılığı, ödenecek). İyi sistemlerin ortak özellikleri:
(1) **iade karşılığı** — dağıtıcı kanalında iade sonradan geldiği için kazancın bir kısmı bir dönem tutulur, sonra serbest
bırakılır; (2) **çapraz mahsup** kuralı sözleşmede açıkça seçilir (bir kitabın kazanılmamış avansı aynı yazarın başka
kitabının kazancından düşülür mü); (3) **haklar veritabanı** kitap × hak türü × dil × ülke × süre matrisiyle tutulur,
fuarda «bu hak müsait mi» sorusu saniyede cevaplanır; (4) yazar portalı — TİMAŞ'ta giriş yalnız AD olduğu için yerine
e-posta ile güvenli belge gönderimi. Zayıf yanları: sözleşmedeki özel maddelerin (serbest metin) sistem dışında kalması,
ilk kurulumda geçmiş avans bakiyelerinin aylar süren temizliği.

**TİMAŞ için mükemmel sistem:** Dönem sonu gecesi koşu kendiliğinden hesaplanır; sabah telif uzmanı yalnız istisna kuyruğunu
görür; her satırın hesabı açılır (kitap × ay × kanal, kademe sınırı, pay, avans, kur ve kur tarihi); onaylı koşu hem M6
hakedişlerini hem ödeme listesini hem de yazar beyannamelerini üretir; muhasebe Logo'da ödediğinde ertesi gün portal
eşleştirmeyi önerir; hak kartı fuar masasında telefondan açılır. Avans açılış bakiyeleri bir kez, gerekçeli girilir ve
kimin girdiği kayıtlıdır.

**Bir iş günü (telif uzmanı, dönem sonu haftası):**
- 09:00 — «2026 1. yarı» koşusu gece hesaplanmış: 2.4xx sözleşme, 61 istisna. İstisnaları nedene göre gruplu görüyor:
  «stok kodu yok» 12, «kur bulunamadı» 9, «taraf payı toplamı %100 değil» 7, «avans açılışı girilmemiş» 33.
- 10:30 — Avans açılışlarını eski Excel'den giriyor (gerekçe: «2025 sonu mutabakat dosyası»); istisna 28'e iniyor.
- 13:00 — Kalan istisnaları M6 sözleşme sayfasına geçip düzeltiyor (zeyilname gerekmeyen kayıt hatası «düzeltme» olarak).
- 15:00 — Koşuyu yeniden hesaplatıp onaya gönderiyor; birim yöneticisi onaylıyor.
- 15:30 — Hak sahipleri sekmesinden 480 beyannameyi üretiyor, önce 5 tanesini kontrol ediyor, sonra toplu gönderim; her
  gönderim kayda düşüyor.
- 16:30 — Muhasebeye «ödeme listesi hazır» bildirimi gidiyor.
- 17:00 — Yenilemeler: bu ay biten 14 sözleşme; 3'ü için yayın yönetmenine «karar bekliyor» düşüyor.

**«Bunu görürsem hemen kullanırım»**
1. Bir tuşla bütün dönem ve yalnız istisnalarla çalışmak.
2. Yazar başına tek beyanname — geçmiş dönemler ve avans bakiyesiyle.
3. Fuar masasında hak kartı: bu kitabın Arapça hakkı boş mu, kime satıldı, ne zaman bitiyor.

**«Bunu yaparsanız kullanmam»**
1. Hesabı açıklanamayan bir telif rakamı — yazar sorduğunda satır satır gösteremezsem sistem işe yaramaz.
2. Onaylanmış bir dönemi sessizce yeniden hesaplamak (iade sonradan gelince eski beyanname değişirse güven biter;
   fark sonraki döneme devreden olarak yazılmalı).
3. Avans bakiyesini «sıfır» varsaymak — geçmişi bilinmeyen avansı sıfır saymak fazla ödeme demektir; bilinmiyorsa istisna.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Uygun sözleşmeleri seçme | — | `new_sozlesmeBase` (`statecode = 0`, `new_SozlesmeTipi = 5` Telif Alış, `new_TelifTipi` IN 2, 5, 6, 7, `statuscode` yürürlükte), portal `semantic_contracts` (M6'ya alınmış olanlar öncelikli) | Yok | Kapsam kuraldır. |
| Satış okuma | `V_SatisRaporu_<yıl>` (`[Malzeme/Hizmet Kodu]`, `Yıl*12+Ay`, `Satis_Iade`, `Net Tutar`, `Miktar`, `Birim Fiyat`; `Satır Türü = Malzeme`) — M6 `sales_sql` | `new_kitapBase.new_StokKodu`, `new_EKitapStokKodu` | Yok | M6 ile aynı tanım; 9/9 referansla doğrulandı. |
| Telif hesabı | — | Oran, esas (net/brüt), kademe, taraf payı (`new_sozlesmetarafiBase.new_Odeme`), avans | Yok (`contracts_royalty.compute`) | Rakam hesap motorundan. |
| Kur | Logo `L_DAILYEXCHANGES` (seyrek) | `new_sozlesmeparabirimi` | Yok | TCMB günlük dosya; yoksa istisna. |
| İstisna gruplama ve açıklama | — | — | Yok (kural); açıklama metni sabit şablon | Deterministik olmalı. |
| Beyanname | Hesap sonucu | `ContactBase` (ad, e-posta), taraf | Beyanname **kapak e-postası** taslağı (yazar adı, dönem, kısa özet; sayılar girdiden kopyalanır, model sayı üretmez — sonradan denetlenir) | Yazışma yükü; K1 belge, K2 metin. |
| Logo ödeme mutabakatı | `LG_411_01_CLFLINE` (yazar carisi, `MODULENR 7` / `TRCODE 21` giden havale; serbest meslek makbuzu), `LG_411_CLCARD` (`SPECODE`), `LG_411_SRVCARD` «Yazarların Telif Ücreti» | `new_sozlesmetarafiBase` → `ContactBase`; `AccountBase.new_logicalref` → `CLCARD.LOGICALREF` (%98,6 bağlı) | Yok (kural: cari + tutar ± 0,01 + tarih penceresi) | Eşleştirme sayısaldır. |
| Yenileme önerisi | Son 36 ay satış (`V_SatisRaporu_*`), stok | Bitiş, yenileme alanları, avans | Karar **gerekçesi** cümlesi (girdideki sayılarla) | Karar insanın; gerekçe yazmayı hızlandırır. |
| Hak açıklaması sınıflandırma | — | `new_haklaraciklama` (738 serbest metin) | Kapalı küme sınıf: «bölge kısıtı / format kısıtı / süre şartı / onay şartı / ücret şartı / diğer» — tek token + olasılık (`structured_outputs.choice` + logprobs), düşük marj = «incele»; ayrıca 1 cümle özet | Serbest metni okunur kılar; insan onaylar. |
| Çeviri sözleşmesi ücret metni | — | `new_hesaplamatutari` («Sayfa başı 250 TL») | Birim + tutar + para önerisi (yapılandırılmış), insan onaylar | Serbest metin sayıya çevrilmeli, ama onaysız hesaba girmez. |
| Lisans fırsatı | Satış performansı | Hak bitleri (`new_yurtdisitelifsatis`, `new_baskadilleretercume`), telif satış sözleşmeleri | Fırsat gerekçesi cümlesi | K3; karar yabancı haklarda. |
| İhlal/yenileme mektubu | — | Sözleşme özeti | Taslak metin (şablondan), hukuk onayı | Yazma yükü. |

Model çağrıları `rt.llm_for("royalty")`; toplu sınıflandırma `BATCH` önceliğiyle. Ekranda yalnız «Zeki AI önerisi».

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/royalty.py` — koşu, istisna, onay, beyanname, avans, yenileme, hak kartı; M6'yı çağırır
  (`contracts_royalty.compute`, `contracts.save_statement` / `approve_statement` / `add_payment`).
- `backend/semantic_bridge/royalty_sources.py` — CRM uygun sözleşme listesi, taraf e-postası, hak alanları; Logo yazar
  cari hareketleri (freelance_logo deseni, 2026 kopyasına kilitli; geçmiş yıl `L_CAPIPERIOD`'dan).
- `backend/semantic_bridge/royalty_api.py` — `register(app, rt, require_caller, can)`.

**Tablolar**
- `semantic_royalty_runs` (id, tenant_id, donem_bas, donem_bit, durum taslak|hesaplaniyor|hesaplandi|onayda|onayli|iptal,
  veri_son_gunu, kapsam_json, ozet_json, hazirlayan, gonderen, onaylayan, tarihler, not)
- `semantic_royalty_run_lines` (run_id, contract_key, contract_id (M6), party_count, durum hesaplandi|istisna|haric,
  istisna_kodu, istisna_metni, brut, avans_mahsup, stopaj, net, para, kur, kur_tarihi, calc_json, fingerprint,
  statement_id (onayda dolar))
- `semantic_royalty_party_statements` (run_id, party_key (CRM kişi/firma kimliği), ad, eposta_maskeli, toplam_json,
  belge_hash, durum hazir|gonderildi|hata, gonderen, gonderim_at)
- `semantic_royalty_advances` (contract_id, acilis_tutari, para, acilis_tarihi, kaynak elle|logo, gerekce, giren, tarih)
- `semantic_royalty_logo_payments` (logo_ref, cari_kodu, tarih, tutar, tur, fis_no, payment_id eşleşme, eşleştiren, durum)
- `semantic_royalty_renewals` (contract_key, bitis, kalan_gun, karar yenile|birak|muzakere|bekliyor, gerekce,
  oneri_metni, karar_veren, karar_at)
- `semantic_rights_grants` (kitap_stok_kodu, hak_turu, dil, ulke, bas, bit, kaynak crm|portal, contract_key, not)
- `semantic_rights_licenses_out` (id, kitap, alici_yayinevi, dil, ulke, avans, oran, para, bas, bit, durum,
  tahsilat_json, crm_contract_id)
- `semantic_rights_notes` (contract_key, sinif, olasilik, ozet, durum oneri|onayli, onaylayan)

**Uçlar** (`/api/v1/royalty/*`, `/api/v1/rights/*`)
- `GET royalty/meta` · `POST royalty/runs` (dönem) · `GET royalty/runs` · `GET royalty/runs/{id}` ·
  `GET royalty/runs/{id}/lines?durum&page` · `POST royalty/runs/{id}/compute` (arka plan, ilerleme `GET …/status`) ·
  `PATCH royalty/runs/{id}/lines/{key}` (hariç tut / geri al, gerekçe) · `POST royalty/runs/{id}/submit|approve|reject|cancel`
- `GET royalty/runs/{id}/parties` · `GET royalty/runs/{id}/parties/{party}/statement.docx` ·
  `POST royalty/runs/{id}/parties/{party}/send` · `POST royalty/runs/{id}/send-all`
- `GET royalty/runs/{id}/payments.csv` · `GET royalty/runs/{id}/withholding.csv`
- `GET royalty/advances` · `PUT royalty/advances/{contract}`
- `GET royalty/reconciliation?from&to` · `POST royalty/reconciliation/{logo_ref}/link`
- `GET royalty/renewals?days=90` · `PATCH royalty/renewals/{contract}` · `POST royalty/renewals/{contract}/suggest` (model)
- `GET rights/books/{stok}` · `GET rights/search?q&hak&dil` · `PUT rights/grants/{id}` · `GET/POST/PATCH rights/licenses-out`
  · `POST rights/notes/classify` (model, 202) · `POST rights/notes/{id}/approve`
- `POST royalty/run-due` (SYSTEM)

**Ekranlar** `src/canvas/editorial/royalty/`: `RoyaltyScreen.tsx` (sekmeler Koşu · İstisnalar · Hak sahipleri · Ödeme
listesi · Mutabakat · Avans · Yenilemeler), `RunLines.tsx`, `PartyStatements.tsx`, `Renewals.tsx`, `api.ts`;
`src/canvas/editorial/rights/RightsScreen.tsx` (Hak kartı · Telif satışları · Fırsatlar). Rotalar `/timas/telif-donem`,
`/timas/haklar`. Menü: `navModel.ts` «Kayıtlar» alanında Sözleşmeler'in altında iki öğe (`parent: 'telif-sozlesme'`):
«Telif dönemi», «Haklar ve lisanslar». Kampüs: `ModulesMenu.tsx` `LIVE.M54 = '/telif-donem'`. Sözleşme sayfasına
(`ContractDetail.tsx`) «Bu sözleşmenin dönem koşuları» bağlantısı.

**Yetki**
- `sayfa:telif-donem` → `/api/v1/royalty/`; `sayfa:haklar` → `/api/v1/rights/`; `run-due` SYSTEM. `_EDITORIAL` kümesine ekle.
- `ozellik:telif.kosu` (koşu aç/hesapla/hariç tut), `ozellik:telif.kosu-onay` (**açıkça**; hazırlayan onaylayamaz),
  `ozellik:telif.bildirim` (**açıkça**; yazara e-posta), `ozellik:telif.odeme-listesi` (**açıkça**; muhasebe),
  `ozellik:telif.avans` (**açıkça**; açılış bakiyesi), `ozellik:telif.yenileme-karar`, `ozellik:haklar.duzenle`,
  `ozellik:haklar.lisans`; indirmeler `ozellik:veri.disa-aktar`.

**Zamanlayıcı** `scripts/server/timas-royalty.{timer,service}`: günde bir (06:30) `POST /api/v1/royalty/run-due` →
yenileme listesi ve kalan günler (CRM), Logo yazar ödemelerini okuyup eşleştirme önerisi, dönem sonu +5 iş günü «koşu
açılmadı» hatırlatması. Koşunun hesabı zamanlayıcıyla değil kullanıcıyla başlar (ilk sürüm). İlk koşu elle.

**Kabul testleri** (gerçek DB, test sunucusu; M6 kabul betiği `accept_m6.py` deseni)
1. Kapsam: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_sozlesmeBase WHERE statecode = 0 AND new_SozlesmeTipi = 5 AND
   new_TelifTipi IN (2,7) AND statuscode IN (100000000, 100000007)` = koşudaki `hesaplandi + istisna + haric` satır
   sayısı (sessiz düşen yok).
2. Stok kodu istisnası: aynı kümede `JOIN new_new_sozlesme_new_kitapBase … JOIN new_kitapBase k … WHERE
   ISNULL(k.new_StokKodu,'') = ''` olan sözleşme sayısı = «stok kodu yok» istisnası sayısı.
3. Telif doğruluğu (rastgele 10 sözleşme, TL ve döviz karışık): bağımsız sorgu `SELECT [Malzeme/Hizmet Kodu],
   SUM([Miktar]), SUM([Net Tutar]) FROM dbo.V_SatisRaporu_2026
   WHERE [Satır Türü] = N'Malzeme' AND [Yıl]*12+[Ay] BETWEEN 2026*12+1 AND 2026*12+6 AND [Malzeme/Hizmet Kodu] IN (…)
   GROUP BY [Malzeme/Hizmet Kodu]` (iade satırlarında miktar ve tutar zaten eksi — M6 ölçümü) + sözleşme oranı → koşu satırıyla adet ve telif eşit (0,01 tolerans; M6 kabulündeki 9/9 yöntemi).
4. Koşu toplamı = satır toplamı: `SELECT SUM(net) FROM semantic_royalty_run_lines WHERE run_id = :id AND durum = 'hesaplandi'`
   = özet kartı ve ödeme listesi CSV toplamı; onaydan sonra `semantic_contract_statements` yeni satır sayısı = hesaplandi sayısı.
5. Beyanname: bir hak sahibinin beyannamesindeki toplam = `SUM(net)` onun taraf olduğu satırlar (pay oranıyla).
6. Logo ödemeleri: `SELECT C.CODE, SUM(L.AMOUNT) FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF =
   L.CLIENTREF WHERE L.CANCELLED = 0 AND L.MODULENR = 7 AND L.TRCODE = 21 AND C.LOGICALREF IN (:yazar_carileri) GROUP BY
   C.CODE` = mutabakat ekranındaki Logo tarafı (kolon anlamları `freelance_logo.py` ölçümüyle aynı).
7. Yenileme: `SELECT COUNT(*) FROM new_sozlesmeBase WHERE statecode = 0 AND ISNULL(new_suresizsozlesme,0) = 0 AND
   new_SozlesmeBitisTarihi >= :bugun AND new_SozlesmeBitisTarihi < DATEADD(day, 90, :bugun)` = Yenilemeler (90 gün) sayısı.
8. Hak kartı: aktif telif alışta `new_iletimhakki = 1` olan kitap sayısı (2026-09-26 ölçümü 6.783 sözleşme) ile hak
   haritasındaki «iletim» satırları aynı sorgudan.

**Bağımlılık:** M6 bitti ve test sunucusunda; M54 onun üstüne. Paralel: M45 (telif tahakkuku M54'ün `runs` sonucunu okur;
uç şekli önce sabitlenirse paralel). Hak haritası SEO «Haklar ve CRM» ile ortak kurala bağlanmalı (`seo_geo/crm.py`).

**Tahmini büyüklük:** L (koşu + onay + beyanname M; avans/yenileme S; mutabakat M; haklar M).
