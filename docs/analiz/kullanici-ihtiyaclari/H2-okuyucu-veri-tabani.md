# H2 — Okuyucu Veri Tabanı Entegrasyonu: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul bekliyor; M37'nin okuduğu çekirdek sözleşmesi (`readers_core.py`) 2026-09-28'de eklendi · Analiz tarihi: 2026-09-28 · Modül kimliği `readers` (`src/canvas/modules.json`, «Hazırlıklar» grubu)

Kaynaklar: iş tanımı `specs/Okuyucu_Veri_Tabanı_Entegrasyo.txt`, `ZEKİ_Veri_Haritasi2.html` (M37/M38/M24 girdileri),
ilgili modül tanımları `specs/M24.txt`, `M37.txt`, `M38.txt`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`,
`docs/analiz/seo-geo-modul-2026-09-25.md` (T-soft sipariş okuması), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md` ve
`table_descriptions.json` (CRM Türkçe metadata, satır sayıları 2026-09-09), `configs/semantic/knowledge/logo/knowledge/
metrics/logo-timas.md`, `backend/semantic_bridge/access.py`, `people.py`, `seo_geo/connections.py`, PROJECT-MEMORY.md,
kullanıcı belleği (tsoft-no-write, crm-tsoft-no-push-integration, customer-vm-web-watch-off, no-tech-names-on-screens,
system-of-record-logo, timas-access-credentials — yalnız hesap türü, kimlik bilgisi kullanılmadı).

Sunucuya bağlanılmadı. Sayılar daha önce ölçülmüş değerlerdir, tarihleriyle verildi; «ölçülecek» işaretli olanlar
bilinmiyor. Kanıtı olmayan iddialar «varsayım».

---

## 1. Modül ne işe yarar

TİMAŞ'ın okurlarını (kitabı alan, etkinliğe gelen, bültene yazılan, formu dolduran son kişi) tek bir kayıtta
birleştirir: kim, hangi kanaldan geldi, neyle ilgileniyor, hangi iletişim izni var, en son ne zaman temas etti. Bu tekil
kayıt üzerinde segmentler kurulur; kişiselleştirilmiş öneri, bülten segmentasyonu, kampanya hedeflemesi ve topluluk
çalışmaları (M24, M37, M38) bu katmandan beslenir.

Bugünkü sorun: okur verisi en az beş yerde ve birbirine bağlanmamış hâlde duruyor — CRM kişi kartları (yazar ve bayi
çalışanıyla karışık), CRM müşteri adayları (landing page/fuar/SMS kayıtları), CRM'in İleti Yönetim Sistemi (İYS) günlüğü,
T-soft site üyeleri ve siparişleri (2021'den beri CRM'e gelmiyor), fuar/etkinlik listeleri (varsayım: Excel). İş tanımı
«CRM & E-ticaret ✓ HAZIR» diyor; veri, e-ticaret tarafının CRM'de olmadığını gösteriyor (§3, §6). İlk iş kimlik
birleştirme ve izin durumunu güvenilir kılmaktır; öneri ve topluluk bunun üstüne kurulur.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| CRM / okur pazarlama uzmanı | Pazarlama (CRM ekip üyeliği 35 kişi, 2026-09-15). Kişinin kim olduğu sorulacak | Her gün | Masaüstü |
| E-bülten / kampanya sorumlusu | Pazarlama (varsayım). CRM'de 28 e-posta/SMS kampanyası kaydı var (`CampaignBase`) | Haftalık | Masaüstü |
| Topluluk / sosyal medya yöneticisi | Pazarlama (varsayım) | Haftalık | Telefon + masaüstü |
| Etkinlik / fuar ekibi | Pazarlama ve satış (varsayım). CRM etkinlik kayıtlarının çoğu satış ziyareti; okur etkinliği ayrımı ölçülecek | Etkinlik sonrası | Telefon (yerinde), masaüstü (yükleme) |
| Okul / öğretmen ilişkileri | Satış (CRM form tipi «Timaş Okul», sipariş tipi «Öğretmen Örneği» var) — varsayım | Aylık | Masaüstü |
| KVKK irtibat / hukuk | Varsayım: idari birim | Aylık denetim, başvuru geldikçe | Masaüstü |
| Yönetim | Genel müdürlük | Aylık rapor | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

**Okur pazarlama uzmanı (kanıt: CRM şeması; kullanım biçimi varsayım):**
- CRM kişi kartı `ContactBase` 59.637 satır; aynı tabloda yazar, çevirmen, bayi yetkilisi ve okur birlikte duruyor.
  Okuru ayırt eden alanlar: `new_geliskanali` («Form Tipi»: Zürafam Uçabilir, Eticaret, Eser Katılımcısı, Fuar, Kitap
  Kahve, Hekimoğlu Form, Timaş Okul, Dosya Başvuru, Genel Kişi, Timaş Akademi, Telif, Pazarlama…), `new_kayittipi`
  (8151 SMS, Landing Page, Fuar), `new_ilgilidepartman` (B2C seçeneği). Dağılım ölçülecek.
- CRM müşteri adayı `LeadBase` 63.332 satır: katılım kaynağı, UTM kaynak/kampanya, ilgi alanı (`new_ilgialani`), doğum
  tarihi, KVKK izni alanları. Okur kayıtlarının önemli kısmının burada olması muhtemel (varsayım).
- İzin: kişi ve adayda e-posta/SMS/arama izin bayrakları + İYS alanları (`obs_sendtoiys`, `obs_iyserror`,
  `new_iysonayi`, `new_kvkkonayi`); `obs_iyslogBase` 56.867 satırlık İYS alışveriş günlüğü (onay/ret, tarih). CRM'de bir
  İYS entegrasyonu çalışıyor (varsayım: son kaydın tarihi ölçülecek).
- Kampanya: `CampaignBase` 28 kayıt («Email Sms Kampanyası»; toplam gönderim, okunma, tıklama, kara liste sayaçları),
  `obs_kampanyagonderimleriBase` 139 gönderim, `ListBase` 11 pazarlama listesi. Hacim küçük; asıl bülten aracının
  başka bir platform olması muhtemel (varsayım, sorulacak).
- Kupon: `new_kuponkodlariBase` 50.000 kod (müşteri ve kampanya bağlı). Hangi döneme ait olduğu ölçülecek.
- Adım ve tıkanma (varsayım): segment için CRM gelişmiş bulma + Excel; kopya kayıtlar elle ayıklanıyor; izin durumu
  kanallar arasında tutarsız.

**E-ticaret okuru (kanıt):** timas.com.tr T-soft üzerinde; T-soft'ta 62.903 sipariş okundu (2026-09-25, kişisel veri
içeriyor, kullanılmadı). T-soft dönemi siparişleri CRM'e gelmiyor: son 12 ayda B2C numarası dolu CRM siparişi 0
(`crm-eticaret-entegrasyon-2026-09-27.md` §1.5). Son B2C (Omerd sitesi) CRM siparişi 2021-05-20. T-soft üye sayısı ve
izin alanları ölçülecek.

**Pazaryeri okuru (kanıt):** Kitapyurdu, Hepsiburada, Amazon CRM'de **toptan cari** olarak var; son müşteri bilgisi
yok. Pazaryeri API entegrasyonu izi yok.

**Etkinlik/fuar (kanıt kısmi):** `new_etkinlikBase` 57.013 (çoğu satış ziyareti), etkinlik–kişi bağı 9.012. Fuar ve imza
günü katılımcı listelerinin nasıl tutulduğu varsayım (Excel/kâğıt form).

**Sosyal medya:** kişi kartında Instagram/YouTube/LinkedIn kullanıcı adı alanları var (yazar ve etkileyici içindir);
okur demografisi için bağlantı yok. Müşteri ortamında dış kaynak taraması kapalı.

## 4. İhtiyaçlar ve acı noktaları

**Okur pazarlama uzmanı**
1. Tekil okur sayısı ve «bugün izinli ulaşılabilir kitle» (kanal başına) — güvenilir tek rakam.
2. Kopya kayıtların birleşmesi; belirsiz eşleşmelerin insan kararıyla çözülmesi.
3. Kural tabanlı segment kurmak (ilgi alanı, yaş grubu, sadakat, kanal) ve büyüklüğünü anında görmek.
4. Segment listesini, izin kontrolünden geçmiş hâliyle gönderim aracına vermek.
5. Kayıp sinyali: bir süredir temas/alım olmayan okurlar.

**E-bülten sorumlusu**
1. Bülten segmentlerinin ilgi alanına göre ayrılması (çocuk, tarih, din, kişisel gelişim…).
2. Açılma/tıklama verisinin okur kaydına dönmesi (hangi platformdan geleceği bilinmiyor).

**Etkinlik ekibi**
1. Etkinlik sonrası katılımcı listesini yükleyip dakikalar içinde «eşleşti / yeni / izin eksik» görmek.
2. Yerinde telefonla hızlı kayıt (sonraki sürüm).

**KVKK irtibat**
1. Her okurun izin kaynağı ve tarihi; ret edenin hiçbir listeye girmediğinin kanıtı.
2. İlgili kişi başvurusunda (silme/erişim) kişinin bütün kayıtlarını bulmak.
3. Kimin hangi listeyi ne amaçla dışa aldığının kaydı.

**Yönetim**
1. Aylık okur tabanı büyümesi, kanal kırılımı, kayıp oranı.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Okur pazarlama uzmanı olarak «son 18 ayda çocuk kitabı almış, e-posta izni olan» okur sayısını anında görmek
  istiyorum, çünkü kampanya bütçesini buna göre planlıyorum.
- Okur pazarlama uzmanı olarak aynı kişiye ait görünen kayıtları gerekçesiyle görüp birleştirmek istiyorum, çünkü aynı
  kişiye iki bülten gitmesin.
- Okur pazarlama uzmanı olarak bir okurun zaman çizelgesini (form, etkinlik, sipariş, izin değişimi) görmek istiyorum,
  çünkü şikâyet ya da talep geldiğinde bağlamı bilmeliyim.
- E-bülten sorumlusu olarak onaylı segmenti izin kontrolünden geçmiş liste olarak almak istiyorum, çünkü izinsiz
  gönderim cezası bana düşer.
- Etkinlik ekibi olarak fuar katılımcı dosyasını yükleyip eşleşmeyi görmek istiyorum, çünkü listeyi elle
  karşılaştırmak günler sürüyor.
- KVKK irtibat kişisi olarak bir e-posta adresine ait bütün kayıtları ve dışa aktarımları görmek istiyorum, çünkü
  başvuruya 30 gün içinde cevap vermem gerekiyor (süre mevzuattan, doğrulanmalı).
- Yönetici olarak aylık okur tabanı raporunu telefonda görmek istiyorum.

### Ana ekranlar ve akış
1. **Özet (ilk açılış):** tekil okur sayısı, kaynak kırılımı (CRM kişi, CRM aday, T-soft üye, etkinlik yüklemesi),
   kanal başına izinli kitle (e-posta / SMS / arama), bekleyen birleştirme adayı, son yükleme, kaynak tazeliği
   (her kaynağın son okuma zamanı).
2. **Okur ara / okur kartı:** yalnız yetkili kişi ad/e-posta görür; diğerleri maskeli. Kart: kaynaklar, izinler (kaynak
   + tarih), ilgi alanları (kategori ağacı düğümleri), zaman çizelgesi, segmentleri.
3. **Birleştirme kuyruğu:** aday çift, eşleşme gerekçesi (aynı e-posta / aynı telefon / ad + il), «aynı / farklı».
4. **Segmentler:** kural kurucu (alan + koşul), anlık büyüklük, izinli büyüklük, Zeki'nin açıklaması; taslak → onay.
5. **Yüklemeler:** CSV/Excel yükle, kolon eşle, önizleme, eşleştirme sonucu.
6. **Dışa aktarımlar:** kim, ne zaman, hangi segment, kaç kişi, amaç.

En sık üç işlem:
- Segment büyüklüğü görmek: Segmentler (1) → segment (2). ≤ 2 tık.
- Etkinlik listesi yüklemek: Yüklemeler (1) → dosya seç (2) → kolon eşleme onayı (3) → «Eşleştir» (4).
- Birleştirme kararı: kuyruk (1) → «Aynı kişi» (2).

### Zeki AI'ya soracakları örnek sorular
- «E-posta izni olan kaç okurumuz var, geçen aya göre değişim ne?»
- «Son 6 ayda fuar kaynaklı yeni okur sayısı kaç, kaçının izni var?»
- «Tasavvuf ilgi alanında olup son bir yıldır hiç temas etmediğimiz okurlar kaç kişi?»
- «Zürafam Uçabilir formundan gelen kayıtların kaçı sonra sipariş verdi?»
- «Hangi il okur yoğunluğunda ilk 10?»
- «İYS'de ret verenlerin sayısı son 3 ayda nasıl değişti?»
- «Bu segmenti oluşturan kural ne, kimler neden dışarıda kaldı?»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| Kaynakların okunması, normalizasyon (e-posta, telefon), kesin eşleşmeyle birleştirme | K1 | Kesin kural: aynı normalize e-posta ya da telefon |
| Belirsiz eşleşme kararı | K2 | Zeki olasılıkla önerir, insan karar verir |
| İzin durumunun hesaplanması (en son kaynak kazanır, ret her zaman kazanır) | K1 | Kural deterministik |
| İlgi alanı çıkarımı (aldığı/ilgilendiği kitapların kategori düğümü) | K1 | H1 ağacından; serbest metin ilgi alanı eşlemesi K2 |
| Segment tanımı | K2 | Zeki kural önerir, uzman onaylar |
| Liste dışa aktarımı / gönderim | K4 | İnsan yapar; portal gönderim yapmaz |
| Topluluk planı, içerik takvimi | K3 | Sonraki sürüm (M37) |

### Bildirim/uyarı
- Kaynak okuması başarısız ya da 48 saatten eski → portal yöneticisi + okur pazarlama uzmanı (Kampüs zil).
- Birleştirme kuyruğu belirli sayıyı aştı (eşik ayarlanabilir) → okur pazarlama uzmanı.
- İYS ret sayısında haftalık sıçrama → okur pazarlama + KVKK irtibat (e-posta özeti, mevcut SMTP).
- Dışa aktarım yapıldı → KVKK irtibat kişisine günlük özet.

### Onay ve yetki (öneri)
| İşlem | Kim | Anahtar |
|---|---|---|
| Sayfayı görmek (yalnız toplu sayılar, maskeli liste) | Pazarlama, yönetim | `sayfa:okurlar` |
| Kişisel veriyi açık görmek (ad, e-posta, telefon) | Okur pazarlama, KVKK irtibat | `ozellik:okur.kisisel-veri` (açıkça verilir) |
| Birleştirme kararı | Okur pazarlama | `ozellik:okur.birlestir` |
| Segment taslağı | Pazarlama | `ozellik:okur.segment` |
| Segment onayı | Pazarlama müdürü | `ozellik:okur.segment-onay` (açıkça; taslağı yazan onaylayamaz) |
| Liste dışa aktarımı | Okur pazarlama | `ozellik:okur.liste-aktar` (açıkça; amaç alanı zorunlu) |
| Etkinlik dosyası yüklemek | Etkinlik ekibi | `ozellik:okur.ice-aktar` |

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kayıtlı okur (kişi) | CRM `ContactBase` (59.637; `EMailAddress1`, `MobilePhone`, `new_il`, `BirthDate`/`new_DogumTarihi`/`obs_DogumYili`, `GenderCode`, `new_geliskanali`, `new_kayittipi`, `CreatedOn`) | Şema biliniyor | Okur/yazar/bayi ayrımı ve kanal dağılımı ölçülecek |
| Okur adayı | CRM `LeadBase` (63.332; `obs_mainsourcename`, `obs_subsourcename`, `obs_utm_source/campaign`, `new_ilgialani`, `obs_birthdate`, `obs_donotkvkk`, `StateCode`) | Şema biliniyor | Güncellik (son kayıt tarihi) ve kaynak dağılımı ölçülecek |
| Firma olarak açılmış okur | CRM `AccountBase.new_FirmaKanal` = 100000009 «Tüketici-Okur» | Seçenek var | Sayı ölçülecek |
| İletişim izni | CRM kişi/aday/firma: `DoNotEMail`, `DoNotBulkEMail`, `obs_donotsms`, `obs_SmsezinVerme`, `obs_AramayazinVerme`, `new_kvkkonayi`, `new_iysonayi`, izin güncelleme tarihleri; `obs_iyslogBase` (56.867; `obs_permissionstatus` ONAY/RET, `obs_permissiondate`, `obs_customerid`, `obs_iysintegrationfieldid`) | Şema biliniyor | Kanal ↔ entegrasyon alanı eşlemesi (`obs_iysintegrationfieldBase`, 6 satır) ve güncellik ölçülecek |
| E-ticaret üyesi ve siparişi | T-soft REST1 (`order/get` 62.903 sipariş, 2026-09-25); üye yöntemi ölçülecek | Yalnız okunabilir; kişisel alanlar okunmadı | Üye sayısı, izin alanları, silinmiş üyeler ölçülecek; H3 ile ortak |
| Satın alma geçmişi (kitap, kategori) | T-soft sipariş satırı (barkod = ISBN = CRM `new_ean13`) + H1 kategori ağacı | ISBN eşlemesi SEO'da 5.466/5.656 | Satır düzeyi T-soft okuması ölçülecek |
| Gerçekleşmiş satış (finansal kayıt) | Logo `STLINE` faturalı satır; kanal cari `SPECODE2` / `v_channel_net` | Ölçüler sertifikalı | E-ticaret siparişinin Logo'da hangi cariyle faturalandığı (kişi başı mı, toplu mu) ölçülecek |
| Kampanya etkileşimi | CRM `CampaignBase` (28; okunma, tıklama sayaçları), `obs_kampanyagonderimleriBase` (139; kişi/aday bağlı, okundu/tıklandı) | Şema biliniyor | Asıl bülten platformu bilinmiyor; açılma/tıklama kişi düzeyinde nereden gelecek sorulacak |
| Kupon kullanımı | CRM `new_kuponkodlariBase` (50.000; müşteri, kampanya) | Şema biliniyor | Dönemi ve T-soft kuponlarıyla ilişkisi ölçülecek |
| Etkinlik katılımı | CRM `new_new_etkinlik_contactBase` (9.012), `new_etkinlikBase`; dosya yüklemesi (kullanıcı girer) | Şema biliniyor | Okur etkinliği ile satış ziyareti ayrımı ölçülecek |
| Anket / geri bildirim | CRM anket tabloları (`new_anketBase` 2, `new_anketmoduluBase` 14 …) | Çok küçük | Pratikte yok |
| Pazaryeri müşteri verisi | Trendyol / D&R / idefix | Entegrasyon izi yok | Pazaryeri sözleşmesi müşteri verisinin pazarlamada kullanımına izin veriyor mu — hukuk (varsayım: izin vermiyor) |
| Sosyal medya demografisi | Platform hesap istatistikleri | Bağlantı yok; müşteride dış tarama kapalı | Platformlar bireysel değil toplu demografi verir (genel bilgi, doğrulanmalı) |
| İlgi alanı sözlüğü | H1 kategori ağacı; geçici olarak CRM Kitaplık + hedef kitle | H1 kodlanmadı | H1'e bağlı |

## 7. Diğer modüllerle bağ

- **Girdi alır:** H1 kategori ağacı (ilgi alanı), H3 e-ticaret müşteri özeti ve web davranışı, M27 fuar/etkinlik
  kayıtları, CRM, T-soft, Logo (kanal cirosu).
- **Çıktı verir:** M24 bülten segmentleri; M37 okur topluluğu (segment, sadakat, seri tamamlama tetikleri); M38 CRM
  veri hijyeni (kopya ve eksik listesi — CRM'e insan işler); M35 e-ticaret kampanya hedefleme; M51 müşteri hizmetleri
  (okur kartı bağlamı); H4 kurumsal e-posta (gönderen okur mu?); M31 okul/öğretmen listeleri.

## 8. Kısıtlar

- **CRM'e yazma yok:** birleştirme, segment ve izin özeti portalın tablolarında; CRM'deki kopyalar «CRM'e işlenecek»
  listesiyle insan tarafından düzeltilir.
- **T-soft'a yazma yasak:** T-soft üyesine dokunulmaz, yalnız okunur.
- **Portal mesaj göndermez:** ilk sürümde e-posta/SMS gönderimi yok; liste dışa aktarılır, gönderim mevcut araçla.
- **Müşteride web taraması kapalı:** sosyal medya ya da dış kaynaktan okur verisi toplanmaz.
- **Ekranda teknoloji adı yok:** «Zeki AI». İYS devlet sistemidir, adı ekranda kalabilir.
- **Demo veri yok, sayı tavanı yok:** segment ve liste kesilmez; büyükse sayfalanır.
- **KVKK (modüle özgü, hukukça doğrulanmalı):**
  - Profilleme ve pazarlama amaçlı işleme için açık rıza ve aydınlatma metni; rızası olmayan okur yalnız toplu
    sayıda görünür, segmente girer ama dışa aktarılmaz.
  - Ticari elektronik ileti öncesi İYS kontrolü (6563 sayılı Kanun ve yönetmeliği): ret her zaman kazanır; İYS
    durumu bilinmeyen kişi «izinli» sayılmaz.
  - Çocuk verisi: CRM'de ebeveyn adı ve doğum yılı alanları var (çocuk yarışma/form kayıtları olabilir). 18 yaş altı
    kayıtlar ayrı işaretlenir; pazarlama listesine yalnız ebeveyn rızasıyla (varsayım, hukuk).
  - Veri minimizasyonu: portal kişisel veriyi kopyalamaz; kendi tablolarında kaynak anahtarı + tuzlu özet (hash) + izin
    özeti tutar, ad/e-posta ekranda kaynaktan anlık okunur.
  - Saklama: yüklenen etkinlik dosyaları eşleştirme sonrası belirli sürede silinir (süre ayar; sayı değil zaman sınırı).
  - Dışa aktarım denetim kaydı; ilgili kişi başvurusu için «bu kişiye ait her şey» araması.
  - Model kişisel veri görmez: sınıflama ve açıklama çağrılarına ad/e-posta/telefon gönderilmez.
  - Pazaryeri müşteri verisi kullanılmaz (sözleşme teyidine kadar).

## 9. Kapsam önerisi

**İlk sürüm**
- CRM kişi + aday + İYS günlüğü okuması; normalize e-posta/telefon ile kesin birleştirme; tekil okur sayısı.
- İzin özeti (kanal başına), kaynak tazeliği paneli.
- Belirsiz eşleşme kuyruğu.
- Kural tabanlı segment + anlık büyüklük (toplam / izinli), segment onayı.
- Etkinlik dosyası yükleme ve eşleştirme.
- İzin kontrollü liste dışa aktarımı + denetim kaydı.

**Sonraki sürüm**
- T-soft üye ve siparişleriyle birleştirme (H3 ile birlikte).
- İlgi alanını H1 ağacından satın alma geçmişiyle çıkarma; sadakat seviyesi (ilk / düzenli / kayıp) ve kayıp sinyali.
- Kişiselleştirilmiş kitap önerisi (segment bazlı) ve bülten içerik önerisi (M24).
- Bülten platformu açılma/tıklama verisinin okur kaydına dönmesi.
- Topluluk yapısı, içerik takvimi (M37).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/connections.py` — yalnız okuma T-soft istemcisi (`READ_ONLY`).
- `backend/semantic_bridge/people.py` — CRM okuma ve AD kesişimi deseni (iç kişi rehberi; okur değil ama bağlantı ve
  maskeleme deseni).
- `backend/semantic_bridge/access.py` — sayfa/özellik kapısı; açıkça verilen özellik deseni.
- `backend/semantic_bridge/admin.py` — `audit`, ayarlar; `alerts.py` SMTP (yalnız iç bildirim).
- `backend/semantic_bridge/board_excel.py` / dışa aktarım desenleri.
- Segment motoru H3 ile ortak olacak şekilde burada yazılır (H3 yeniden yazmaz).

## 10. Uzmanlara sorulacak sorular

1. Bugün bülten ve SMS hangi platformdan gidiyor; açılma/tıklama kişi düzeyinde dışa alınabiliyor mu?
2. İYS entegrasyonu CRM'de hâlâ çalışıyor mu; T-soft üyelerinin izinleri İYS'ye kimden gidiyor?
3. Okurun «ana kaydı» nerede olmalı: CRM kişi mi, aday mı, portal mı? CRM ekibi birleştirme listesini işler mi?
4. Fuar ve imza günü katılımcı listeleri hangi biçimde, hangi rıza metniyle toplanıyor?
5. Çocuk kayıtları (Zürafam Uçabilir vb.) için ebeveyn rızası alınıyor mu, bu kayıtlar pazarlamada kullanılabilir mi?

## 11. Başarı ölçütü

- Tekil okur sayısının kaynaklarla uzlaşması (kabul testlerindeki SQL'lerle birebir).
- Kopya oranı: birleştirme öncesi/sonrası; belirsiz kuyruğun haftalık erime hızı.
- İzinli ulaşılabilir kitle (kanal başına) — aylık izlenir.
- Segment kurma süresi: fikirden onaylı listeye (hedef aynı gün).
- Etkinlik dosyası eşleştirme süresi (hedef dakikalar).
- İzin ihlali sıfır: dışa aktarılan listelerde ret/izinsiz kişi yok (her dışa aktarımda SQL ile doğrulanır).
- Kullanım: haftalık aktif kullanıcı, onaylı segment sayısı.

---

## 12. Uzman gözüyle en iyi sistem

Bakış açısı: 15 yıllık CRM ve sadakat müdürü (perakende ve yayıncılıkta okur tabanı yönetmiş).

**Sektörde iyi örnekler.** Büyük yayınevleri okur verisini tek bir müşteri veri platformunda toplar (tekil kimlik,
izin merkezi, olay akışı); bülten tür ve yaş grubuna göre ayrılır, okur kendi tercih merkezinden konu seçer
(«ilerleyen profil» — her temasta bir soru). Perakende kitapçılar sadakat üyeliğiyle satın alma geçmişini kimliğe
bağlar ve «seri tamamlama», «yazarın yeni kitabı» tetiklerini buradan çalıştırır. İzin önce gelir: izin merkezi
olmadan segment motoru kurulmaz. Yazılım dünyasında bu işin iyi örnekleri müşteri veri platformları ve pazarlama
otomasyon araçlarıdır; ortak ilkeleri tekil kimlik, açıklanabilir segment, kontrol grubu ve izin denetimidir.

**TİMAŞ için mükemmel sistem.** Her okurun tek kartı: kaynaklar (CRM kişi/aday, site üyeliği, fuar), izinler (kanal,
kaynak, tarih, İYS durumu), ilgi alanları (H1 ağacı düğümleri, alımlardan ve formlardan), sadakat seviyesi, zaman
çizelgesi. Segmentler okunur bir cümleyle açıklanır; dışa aktarım izin denetimiyle ve amaç kaydıyla yapılır. Kaynaklar
gece tazelenir, tazelik ekranda görünür. Kişisel veri portalda kopyalanmaz.

**Bir iş günü (CRM ve sadakat müdürü):**
- 09:00 Özet: dünkü yeni okurlar (kaynak kırılımı), birleştirilen kopyalar, İYS ret değişimi, kaynak tazeliği (hepsi
  yeşil mi?).
- 09:20 Birleştirme kuyruğu: gece çıkan belirsiz çiftlere gerekçeye bakarak karar verir.
- 10:00 Pazarlama toplantısı için Zeki AI'ya: «6–10 yaş çocuk ilgi alanında, son 12 ayda alım yapmış, e-posta izinli
  kaç kişi var?» → segment taslağı; kural cümlesi; izinli büyüklük.
- 11:30 Segmenti müdüre onaya gönderir; onay gelince listeyi amaç «Ekim çocuk bülteni» ile dışa aktarır.
- 14:00 Fuar ekibinin yüklediği katılımcı dosyası: eşleşen/yeni/izin eksik sayıları; izin eksiklere ayrı kampanya
  önerisi (rıza alma).
- 16:00 Haftalık kayıp sinyali listesi (sonraki sürüm).
- 17:30 Gün sonu: dışa aktarım günlüğünü KVKK irtibatıyla paylaşır.

**«Bunu görürsem hemen kullanırım»**
1. Segment kurarken anında «toplam / e-posta izinli / SMS izinli» üç sayı.
2. Okur kartında tek zaman çizelgesi (form, fuar, sipariş, izin değişimi).
3. Etkinlik dosyası yükle → dakikalar içinde eşleştirilmiş sonuç.

**«Bunu yaparsanız kullanmam»**
1. İzin durumu belirsiz kişiyi listeye koyan ya da reti geç işleyen sistem.
2. Neden oluştuğu açıklanamayan «kara kutu» segment ya da skor.
3. Herkesin kişisel veriyi görüp dışa aldığı, kaydı tutulmayan ekran.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kaynak okuma | — | `ContactBase`, `LeadBase`, `AccountBase` (FirmaKanal=Tüketici-Okur), `obs_iyslogBase`, `obs_iysintegrationfieldBase` | — | Okuma SQL |
| Normalizasyon ve kesin birleştirme | — | e-posta, cep telefonu alanları | — | Kural deterministik (küçük harf, boşluk, +90) |
| Belirsiz eşleşme | — | ad, il, doğum yılı (modele gitmez; yalnız benzerlik özellikleri) | Kişisel veri olmadan, özellik vektörünün sözlü özeti üzerinden «aynı / farklı / belirsiz» tek token + olasılık — ya da hiç model yok, yalnız skor | Model değer katmıyorsa kullanılmaz; ilk sürümde deterministik skor yeter |
| İzin özeti | — | izin bayrakları + İYS günlüğü (en son kayıt, ret kazanır) | — | Hukuki karar deterministik olmalı |
| İlgi alanı | Logo'da okur yok; kanal cirosu için `v_channel_net` | `LeadBase.new_ilgialani` (serbest metin), etkinlik türü, form tipi | Serbest metin ilgi alanını H1 ağaç düğümüne eşleme: kapalı küme seçim + olasılık | Serbest metin → kontrollü sözlük |
| Segment önerisi | — | — | Doğal dil isteği («çocuk kitabı alan izinli okurlar») → segment kural JSON'u taslağı; kullanıcı kuralı görür, onaylar | Model rakam üretmez; sayı kuralın SQL'inden |
| Segment açıklaması | — | — | Kuralı okunur cümleye çevirir | Açıklanabilirlik |
| Okur tabanı raporu | Kanal net ciro (`kanal_net_ciro`, faturalı satır) — okur tabanıyla yan yana | — | Aylık rapor yorumu (rakamlar SQL'den) | Rakam SQL, yorum model |
| Doğal dil soru | Katalog ölçüleri | Portal tabloları (okur, segment, izin özeti) katalogda tanımlanır | Mevcut soru hattı | Kişisel alanlar soru hattına açılmaz |

Model çağrıları `rt.llm_for("readers")` (etkileşimli) / `rt.llm_for("readers", BATCH)` (gece). Kapalı küme için H1'de
tanımlanan `QueuedLlm.choose()`. Hiçbir model çağrısına ad, e-posta, telefon, adres gönderilmez.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/readers.py` — depo, birleştirme, izin hesabı, segment motoru (H3 de kullanır).
- `backend/semantic_bridge/readers_sources.py` — CRM okuması (`ModifiedOn` deltası; `ContactBase`, `LeadBase`,
  `AccountBase` Tüketici-Okur, `obs_iyslogBase`, etkinlik–kişi), T-soft üye/sipariş okuması (sonraki sürüm; H3'teki
  `commerce_sources.py`'den gelir), dosya yükleme ayrıştırıcı (CSV/XLSX).
- `backend/semantic_bridge/readers_api.py` — `register(app, rt, require_caller, can)`.

**Tablolar (bi_meta; hepsinde `tenant_id`)**
- `semantic_readers` — `reader_id`, `email_hash`, `phone_hash` (tuzlu SHA-256; tuz sunucu ortamında), `birth_year`
  (yalnız yıl), `city`, `is_minor` (bayrak), `first_seen`, `last_touch`, `loyalty` (ilk|duzenli|kayip — sonraki sürüm),
  `interests_json` (düğüm id + kaynak), `status` (aktif|silindi).
- `semantic_reader_links` — `reader_id`, `source` (crm_contact|crm_lead|crm_account|tsoft_member|upload),
  `source_id`, `match_rule` (email|phone|manual), `confidence`, `decided_by`, `decided_at`.
- `semantic_reader_merge_candidates` — `a_reader`, `b_reader`, `features_json`, `score`, `status`, `decided_by`.
- `semantic_reader_consents` — `reader_id`, `channel` (email|sms|call), `status` (izinli|ret|bilinmiyor), `source`
  (iys|crm|tsoft|form), `at`.
- `semantic_reader_segments` — `id`, `name`, `definition_json`, `explanation`, `status` (taslak|onay-bekliyor|onayli|
  arsiv), `owner`, `approved_by`, `version`, `domain` (okur|eticaret).
- `semantic_reader_segment_snapshots` — `segment_id`, `at`, `total`, `email_ok`, `sms_ok` (üye listesi saklanmaz; dışa
  aktarım anında hesaplanır).
- `semantic_reader_imports` — `id`, `file_name`, `uploaded_by`, `at`, `rows`, `matched`, `new`, `rejected`,
  `purge_after`.
- `semantic_reader_import_rows` — geçici; `purge_after` gelince silinir.
- `semantic_reader_exports` — `id`, `segment_id`, `user`, `at`, `purpose`, `channel`, `count`, `excluded_no_consent`.

**Uçlar (`/api/v1/readers/*`)**
- `GET overview` · `GET sources` (tazelik).
- `GET search?q=` (maskeli; açık görünüm `ozellik:okur.kisisel-veri`) · `GET item/{reader_id}` (kişisel alanlar
  kaynaktan anlık).
- `GET merge-candidates` · `POST merge-candidates/{id}/decision`.
- `GET segments` · `POST segments` · `PATCH segments/{id}` · `POST segments/{id}/submit` · `POST segments/{id}/approve`
  · `POST segments/{id}/preview` (yalnız sayılar) · `POST segments/{id}/export` (amaç zorunlu; dosya anında üretilir,
  saklanmaz) · `POST segments/draft-from-text` (Zeki önerisi).
- `POST imports` (dosya) · `GET imports/{id}` · `POST imports/{id}/confirm`.
- `GET exports` (denetim listesi) · `GET subject?email=` (KVKK başvurusu; yalnız `ozellik:okur.kisisel-veri`).
- `POST run-due` (SİSTEM).
- Sözleşme uçları (diğer modüller): `GET segments/{id}/summary` (M24, M37, M35 okur).

**Ekranlar** `src/canvas/readers/`: `ReadersHome.tsx`, `ReaderCard.tsx`, `MergeQueue.tsx`, `Segments.tsx`,
`SegmentBuilder.tsx`, `Imports.tsx`, `Exports.tsx`, `api.ts`. Rota `/timas/okurlar` (+ `/okurlar/kisi/:id`,
`/okurlar/segmentler`, `/okurlar/yuklemeler`). Menü: `navModel.ts` → «Pazarlama» alanında yeni bölüm
`section: 'Okur ve müşteri'`, öğe `{ id: 'okurlar', label: 'Okurlar', to: '/okurlar', hint: 'Tekil okur, izinler ve
segmentler' }`. Kampüs: modül kutusu; zilde kaynak hatası ve onay bekleyen segment.

**Yetki**
- `sayfa:okurlar`; `RULES`: `("/api/v1/readers/run-due", SYSTEM)`, `("/api/v1/readers/", frozenset({page("okurlar")}))`;
  `segments/{id}/summary` için M24/M37 sayfa anahtarları eklenir.
- Özellik: `ozellik:okur.birlestir`, `ozellik:okur.segment`, `ozellik:okur.ice-aktar` (`FEATURE_RULES`);
  açıkça verilen: `ozellik:okur.kisisel-veri`, `ozellik:okur.segment-onay`, `ozellik:okur.liste-aktar` (uç içinde).

**Zamanlayıcı** `scripts/server/timas-readers.{service,timer}` — her gece 03:20: CRM deltası (kişi, aday, İYS
günlüğü), kesin birleştirme, izin özeti, belirsiz aday üretimi, segment anlık görüntüsü; süresi dolan yükleme
satırlarını siler. Pazar gecesi tam tur.

**Kabul testleri (doğrudan SQL, CRM .28)**
1. Etkin kişi: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0;` = «CRM kişi» kaynak sayısı.
2. Form tipi kırılımı: `SELECT new_geliskanali, COUNT(*) FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0 GROUP BY
   new_geliskanali;` = özet ekranındaki kaynak kırılımı.
3. Aday: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.LeadBase WHERE StateCode = 0;` = «CRM aday» (açık adaylar).
4. Tekil e-posta üst sınırı: `SELECT COUNT(DISTINCT LOWER(LTRIM(RTRIM(e)))) FROM (SELECT EMailAddress1 e FROM
   Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0 UNION ALL SELECT EMailAddress1 FROM Timas_MSCRM.dbo.LeadBase WHERE
   StateCode = 0) x WHERE e LIKE '%@%';` = e-postalı tekil okur sayısı (portal aynı normalizasyonu kullanır).
5. İYS son durum: `WITH son AS (SELECT obs_customerid, obs_iysintegrationfieldid, obs_permissionstatus, ROW_NUMBER()
   OVER (PARTITION BY obs_customerid, obs_iysintegrationfieldid ORDER BY obs_permissiondate DESC, CreatedOn DESC) rn FROM
   Timas_MSCRM.dbo.obs_iyslogBase WHERE obs_iserror = 0) SELECT obs_iysintegrationfieldid, obs_permissionstatus,
   COUNT(*) FROM son WHERE rn = 1 GROUP BY obs_iysintegrationfieldid, obs_permissionstatus;` = izin panelindeki kanal
   başına onay/ret (entegrasyon alanı → kanal eşlemesi önce `obs_iysintegrationfieldBase`'ten okunur).
6. E-posta engeli: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0 AND (DoNotEMail = 1 OR
   DoNotBulkEMail = 1);` — bu kişilerden hiçbiri dışa aktarılan e-posta listesinde yok (portal tablosuyla karşılaştırma).
7. Etkinlik katılımı: `SELECT COUNT(DISTINCT contactid) FROM Timas_MSCRM.dbo.new_new_etkinlik_contactBase;` = kartlarda
   etkinlik izi olan okur sayısı.
8. Kampanya geçmişi: `SELECT Name, obs_totalcount, obs_readcount, obs_clickcount FROM Timas_MSCRM.dbo.CampaignBase;` =
   okur kartı/özet ekranındaki kampanya geçmişi.

**Bağımlılık**
- Önce: `QueuedLlm.choose()` (H1'de tanımlı, ortak). İlgi alanı için H1 ağacı (yoksa geçici CRM Kitaplık/hedef kitle).
- H3 bu modülün kimlik, izin ve segment motorunu kullanır → H2'nin çekirdeği (tablolar + birleştirme + izin + segment)
  H3'ten önce biter. H1 ve H4 ile paralel kodlanabilir.
- Hukuk teyidi (rıza metni, çocuk kayıtları) dışa aktarım uçları açılmadan önce.

**Tahmini büyüklük:** L. Parçalar: CRM kaynak okuma + normalizasyon + kesin birleştirme M; izin özeti S; segment
motoru + kurucu ekran L; birleştirme kuyruğu S; yükleme/eşleştirme M; dışa aktarım + denetim S.
