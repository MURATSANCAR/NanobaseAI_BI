# Timas_MSCRM ayrıntılı araştırma (2026-09-15)

Kaynak: semantic katalog (`sl_schema_profile`, 2026-09-09 taraması; bi_meta Postgres :5434), Dynamics'in kendi
Türkçe etiketleri (`crm_metadata_1055`). CRM'e doğrudan SQL bu oturumda çalıştırılmadı; satır sayıları ve
kodlu değer dağılımları tarama anındandır. Tarih aralıkları profilde yok (en yeni kayıt tarihi bilinmiyor).

## Büyüklük ve alanlar (753 tablo, 20.478 sütun, 7.969 açıklamalı, 1.436 profilli sütun)

| Alan | Tablo | Satır | Ana tablolar |
|---|---|---|---|
| Sipariş/Sevkiyat | 33 | 18,0 Mn | siparissatiri 9,7 Mn; sevkiyatsatiri 6,5 Mn; siparis 333 bin; sevkiyat 287 bin; bekleyenurun 773 bin |
| Kitap/Ürün | 184 | 9,5 Mn | serilothareketsatiri 9,1 Mn; kitap 13.598; kapakalternatifi 13.338; kitapgecmisi 28.552; rakipkitap 30.415 |
| Üretim/Depo | 20 | 8,8 Mn | malzemehareketsatiri 8,4 Mn; Uretim 16.129 (493 sütun) |
| Kişi/Firma/Adres | 71 | 493 bin | CustomerAddress 252 bin; Contact 59.637; Account 47.550; eserkatilim 36.330 |
| Kurum içi/İK/Bütçe | 36 | 358 bin | satishedefleri 335 bin; butcekalemi 10.042; talepyonetimi 354; ozgecmis 89; demirbaslar 76 |
| Pazarlama/Etkinlik/Web | 134 | 233 bin | ziyaretyerleri 68.713; etkinlik 57.013 (86 sütun); kuponkodlari 50.000; webuser 5.057; haberler 1.369; kampanya 308 |
| Sözleşme/Telif/Finans | 43 | 39 bin | sozlesme 14.766; tahsilat 14.089 |
| Proje/İş Planı | 69 | 27 bin | plansorumlulari 9.766; proje 6.598; sablonplansatiri 2.719; isplani 383; yayinkurulutoplantilari 499 |
| Sistem/Kullanıcı | 6 | 492 | SystemUser 386 (96 sütun) |

Standart Dynamics aktivite tabloları (Appointment, Task, PhoneCall, Email, ActivityPointer, Annotation),
BusinessUnit, Team katalogda **yok**. Kaynakta da olmayabilir (on-prem Dynamics'te vardır); taramaya eklenip
doğrulanmalı. Sonuç: "takvim/randevu" CRM'den gelmez; ajanda TİMAŞ'ın kendi tablolarından kurulur.

## Kişi köprüsü: SystemUserBase (386)
- `DomainName` = `timas\hesap` ↔ AD sAMAccountName. `IsDisabled` 0=Etkin. `IsActiveDirectoryUser`.
- Kimlik: FullName, FirstName, LastName, Title, JobTitle, InternalEMailAddress, MobilePhone, HomePhone, PhotoUrl,
  ParentSystemUserId (yönetici), BusinessUnitId (departman; ad tablosu yok), TerritoryId (bölge), EmployeeId.
- TİMAŞ ekleri: `new_gorevbirimi` 1=Grafik 2=Editörya 3=Muhasebe 4=Satış; `new_KullancTipi` 1=BMT 2=Kurum Temsilcisi
  3=Genel Merkez; `new_bmt`, `new_toplayici`; `new_varsayilandepoid`, `new_varsayilanfiyatlistesiid`,
  `new_barkodyazici`, `new_normalyazici`, `new_defaultkoliid`. (`new_deposifre` hassas, ekrana çıkmaz.)
- Çoka-çok: kapakalternatifi↔systemuser 35.131; kampanya↔systemuser 617; systemuser↔depo 137;
  fiyatlistesi↔systemuser 74; sorumlugrup↔systemuser 32; promosyonbutcesi↔systemuser 14.

## Kişiye bağlanan alanlar (OwnerId dışında, adlandırılmış roller)
| Tablo | Kişi alanları |
|---|---|
| new_kitap (13.598) | new_yayinyonetmeni, new_Editor, new_projeeditoru, OwnerId("Kaydı Oluşturan") |
| new_Uretim (16.129) | new_SorumluEditor, new_sorumlugrafiker, new_editoryalhazirliktarihi |
| new_sozlesme (14.766) | OwnerId("Sözleşme Sahibi"), new_yayinyonetmeni, new_sozlesmeyiacanid, new_sozlesmeyikilitleyenid, new_izlenecekbelgekullanicisi |
| new_proje (6.598) | OwnerId("Oluşturan"), new_islemsahibi_* (jenerik, önsöz, kaynakça, yazar ismi) |
| new_plansorumlulari (9.766) | OwnerId("Yetkili"), new_roltipiid (Rol Tipi 64), new_isplaniid |
| new_isplani (383) | OwnerId("Plan Sorumlusu") |
| new_yayinkurulutoplantilari (499) | new_Editoru, OwnerId |
| new_etkinlik (57.013) | OwnerId, new_sorumlusu |
| new_tahsilat (14.089) | OwnerId, new_onaylayanid, new_reddedenid |
| new_siparis (333.063) | OwnerId, new_risklimitionaylayanid, new_risklimitireddedenid, new_siparisibirlestirenid |
| new_bekleyenurun (772.616) | OwnerId, new_iptaledenid |
| new_kitapgecmisi (28.552) | new_degistirenid |
| Contact/Account | PreferredSystemUserId, OwnerId, new_MerkezMusteriTemsilcisi; new_iller.new_musteritemsilcisi |
| new_reklamplani (71) | new_reklamteslimkullanicisi, new_gerceklesenteslimtarihikullaniciid |
| new_roltipi (64) | new_standartyetkili |

## Durum sözlükleri (etiketli, katalogda hazır)
- **İş planı** statuscode: 1 Taslak, 2 Tamamlanmış, 100000000 Aktif (343/383), 100000001 Durdurulmuş, 100000009 İptal,
  100000012 Red, 100000013 Beklemede. new_isEmriDurumu: 1 Yeni, 2 Yeniden Tarihlendir, 3 Tamamlandı.
  Ölçüler: toplam/tamamlanan adım, toplam/tamamlanan işçilik süresi, tamamlanma %, gecikme günü, tahmini/gerçek bitiş.
- **Plan sorumluları**: rol adı/rol no, toplam iş adedi, tamamlanan iş adedi, toplam/tamamlanan süre (saat). statuscode 1 Aktif.
- **Proje** statuscode: 2 Beklemede, 100000009 İptal, 100000011 Proje Toplantısına Hazırlanıyor, 100000012 Red,
  100000013 Basılmayacak, 100000014 YK Beklemede… new_isPlaniAsamasi: Sözleşme 1/7 → Editöryal 2/7 → Tasarım 3/7 →
  Föy 4/7 → Ön Sipariş 5/7 → Üretim 6/7 → Baskı Sonrası 7/7. Proje tipi: Yeni/Yenileme/Baskı Tekrarı/Dış/Set.
  Metin durumu: Metin Yok/Synopsis/Yazılıyor/Ham Metin. Yayın kurulu sonucu: Yayınlama/Yeniden Değerlendirme/Red.
  Proje yılı 2025-2028, proje ayı. Onay listesi bit'leri: kapak, isim, ISBN, barkod, fiyat, metadata…
- **Sözleşme** statuscode: 1 Taslak (900), 100000000 Aktif (8.121), 100000004 Pasif (3.352), 100000005 Fesih (1.563),
  100000006 Aktif-Proje (519), 100000007 Aktif-Yenileme (310), 100000002 Süresi Doldu, 100000003 Kilitli.
  new_sozlesmestatusu iş akışı: 1 Editörde → 2 Yayın Yönetmeninde → 3 Telif Hakları → 4 YK Onayı → 5 İmza → 6 Tamamlandı.
  Tip: Telif Alış (10.809) / Telif Satış (3.725) / Taahhüt / Hizmet. Tarihler: başlangıç, bitiş, revize bitiş, baskı son tarihi.
  Haklar (bit): e-kitap, sesli kitap, z-kitap, tercüme, iletim… Para birimi TL/USD/EUR/GBP.
- **Üretim** statuscode: (1) Editoryal Hazırlık → (2) Bilgi Kontrol → (3) Maliyet → (4) Kesin Adet/Fiyat → … ; üretim tipi
  Kitap/Katalog/Dergi/Defter/Ajanda/Set; baskı kartı durumu Baskı Tekrarı/Yeni Baskı/Yenileme; öncelik 0-Acil…;
  bekleme durumu (Sözleşme Sorunu, Metin Revizyonu, Kapak Değişikliği, Matbaa Belirlenmedi, Mizanpaj Bekleniyor…);
  matbaa listesi (Sistem, Çınar, Seçil, Çağlayan, Alfabe, WPC, Hat, Matsis, Kazmaz, İmak…); baskı tipi Matbu/Dijital/POD.
  Ölçüler: üretim tarihi, adet, net baskı adedi, perakende fiyat, toplam maliyet, sayfa sayısı, baskı no.
- **Talep yönetimi** (354; BT destek masası): statuscode Yeni Talep (70), Üzerinde Çalışılıyor, Ötelendi, İptal,
  Tamamlandı (177), Sıra Bekliyor, Test Aşamasında, Analiz Ediliyor. Tür: Arıza/Geliştirme/Analiz/Kurulum/Destek.
  Öncelik: Acil/Öncelikli/Normal. Konu: CRM/Logo/Donanım/B2B/Depo/B2C. Departman: Kültür Editorya, Çocuk Editorya,
  Muhasebe, Satış, Pazarlama, Depo, Grafik, Üretim. Modül: Kişi Kartı, Cari Kart, Stok Kartı, Baskı Kartı, Depo… Alanlar:
  talep konusu, açıklama, harcanan süre, planlanan bitiş, tamamlanma tarihi, e-posta.
- **Etkinlik** (57.013): Planlandı / Tamamlandı / İptal. Alanlar: ad, tip (371 tip), başlangıç/bitiş, yer, şehir, ilçe,
  okul/kurum, ilgili yazar, ilgili kitap, sorumlusu, katılımcı sayısı, satılan kitap adedi, gelir, toplam gider,
  konaklama/ulaşım, web yayın durumu, e-posta gönderim sayısı. Çoğunluğu satış ziyareti (ziyaret şekli "Cari ile Ziyaret").
- **Tahsilat** (14.089): Onay Bekliyor / Onaylandı / Reddedildi / Logoya Aktarıldı; tip Çek/Senet/Pos/Mail Order/Nakit/
  Telif Satış; tutar, vade tarihi, tahsilat tarihi, müşteri, onaylayan/reddeden, red sebebi.
- **Sipariş** (333.063): Taslak / Sipariş / Sevk Edildi / İptal / Birleştirildi / Risk Limit Onayı Bekliyor / Pazarlama
  Bütçesi Onayı Bekliyor; tip B2B/Dağılım/Standart/Fuar/Etkinlik/Telif/Market/B2C/Pazaryeri/Okul Örneği/Öğretmen
  Örneği/Amazon Konsinye; öncelik; ödeme yöntemi.
- **Kitap** (13.598, 336 sütun): statuscode Aktif/Pasif; Tip Kitap/Promosyon/Set/Dergi/Ekitap/SesliKitap; Baskı Durumu
  Baskı Kararı Alındı/Üretimde/Depo Teslim; Önem Derecesi Çok Önemli/Önemli/Normal/Özel; satış durumu Açık/Kapalı;
  hedef yaş 1-14, sınıf, okul öncesi; e-pub, bandrol; yayın yönetmeni, editör, proje editörü, telif ajansı, seri, dizi.
- **Kapak**: kapakalternatifi (13.338: proje, link, ad) ↔ systemuser (35.131 oy hakkı); kapaksecimi (2.878: sahibi, oy, yorum,
  seçilen kapak, proje). Görsel `new_Link` alanında (URL; erişilebilirliği doğrulanmalı).
- **Yayın kurulu toplantıları** (499): toplantı tarihi, editörü, kurul kararı Kabul/Red/Bekleme/Geliştirme, önerilen telif
  oranı, avans, fiyat önerisi, baskı adedi, önerilen yayın tarihi, karar notu.
- **Proje görüşü** (625): ilk yıl satış tahmini (0-1.500 … 15.000+), yayın kararı Yayınlansın/Yayınlanmasın, ilk baskı
  adedi önerisi, fiyat önerisi, isim önerisi, cilt/format önerisi.
- **Haberler** (1.369): haber tarihi, başlık, link, yazarlar, kitaplar, yayınevleri, hangi sitede yayınlandı (9 site), medya planı.
- **Satış hedefleri** (334.982): yıl (2023-2026), bölge (15 bölge: Babıali, Ege, İstanbul, D&R, Hepsiburada, Kitapyurdu, B2C…),
  stok kartı, 12 ay hedef + toplam. Kişiye bağı yok; SystemUser.TerritoryId ↔ bölge eşlemesi Territory (2 satır) ile zayıf.
- **Kampanya** (308): ad, tarih aralığı, planlanan/gerçekleşen ciro, iskonto, mecra CRM/B2B, kullanıcı listesi.
- **Demirbaş** (76): ad, tip Bilgisayar/Monitör/Harici Disk, marka, model, seri no, `new_demirbasId` = kullanıcı → zimmet.
- **Özgeçmiş** (89) yazar özgeçmişleri (kişi değil). **Uzmanlık alanı** (133) Contact'a bağlı.
- **Web user** (5.057) B2B müşterileri; şifre/token alanları hassas.

## Değerlendirme: kişisel ekrana taşınabilir "canlı" veri
1. Kimlik kartı: SystemUser (unvan, görev birimi, e-posta, cep, foto, yönetici) — eksik: departman adı (BusinessUnit).
2. İş planlarım: plansorumlulari+isplani; aktif 343 plan; gecikme ve tamamlanma % hazır.
3. Kitaplarım/Projelerim: yayın yönetmeni/editör bağı + 7 aşamalı iş planı aşaması + proje statüsü.
4. Sözleşmelerim: 6 adımlı iş akışı statüsü, bitiş tarihi, aktif/fesih.
5. Kapak oylamalarım: bana açılmış alternatifler − verdiğim oylar = bekleyen oylama.
6. Üretimde olanlar: sorumlu editör/grafiker bağı + 4+ aşamalı üretim statüsü + bekleme sebebi + matbaa.
7. Ajanda: yayın kurulu toplantı tarihi (editörü=ben), etkinlik başlangıç (sorumlusu=ben), iş planı tahmini bitiş,
   sözleşme bitiş, kampanya bitiş.
8. Taleplerim (BT masası): açık taleplerim, durum, öncelik; ortalama tamamlanma süresi hesaplanabilir.
9. Onay kuyruğum (rol bazlı): tahsilat "Onay Bekliyor", sipariş "Risk Limit Onayı Bekliyor", sözleşme "YK Onayında".
10. Zimmetim: demirbaş (76 kayıt, küçük ama gerçek).

## Riskler
- Profil 2026-09-09; kayıtların güncelliği (son ModifiedOn) bilinmiyor; canlıya çıkmadan kişi başı örnek sorgu şart.
- Kodlu alanlarda etiket yalnız gözlenen değerler için saklı; nadir kodlar "bilinmiyor" görünebilir.
- BusinessUnit, Team, Appointment, Annotation katalog dışı → departman adı ve kapak görselleri için tarama kapsamı genişletilmeli.
- Hassas sütunlar: SystemUser.new_deposifre, webuser şifre/token, Contact TC/nüfus, tahsilat vergi no → ekrana çıkmaz.

## Canlı CRM teyidi (2026-09-15, salt okunur, tünel 14330)
- Kullanıcı: 186 aktif `TIMAS\` hesabı (183 pasif, 17 domain dışı). Aktif listede sahte hesaplar var (Kitapyurdu, D&R, Point,
  Hepsiburada). `muratsancar` CRM'de **yok** → CRM'siz kişi için boş kart tasarımı şart.
- SystemUser alanları boş: Title 1/186, JobTitle 0, PhotoUrl 0, MobilePhone 2, yönetici 1, görev birimi 1. BusinessUnit'in
  139'u "Timaş CRM". Departman için **TeamMembership** kullanılır: Editörya 54, Satış 49, Pazarlama 35, Grafik 13, Mali İşler 10.
- Sahiplik kişi bazlı dağılıyor: plansorumlulari 81 kişi, sözleşme 45, üretim sorumlu editör 84, proje 104, etkinlik 43-52,
  tahsilat 37, kapak oy hakkı 231 kişi. "Timas CRM" servis hesabı (mujdatcengiz) 1.343 plan rolü + 1.791 sözleşme sahibi → süzülmeli.
- **Ölü modüller** (son değişiklik): iş planı 2025-12, plan sorumluları 2022-09, talep yönetimi 2024-07, haberler 2025-06,
  randevu (Appointment) 2024-09, telefon 2024-05. Bunlar ekrana girmez.
- **Canlı modüller** (son 30 günde değişen): e-posta 1.953, etkinlik 594, üretim 470, kitap 423, sözleşme 375, kapak alternatifi 101,
  proje 100, tahsilat 55, görev (Task) 55, kapak seçimi 17, kampanya 3.
- Üretim statuscode etiketleri: (0) Baskı Hazırlık, (1) Editoryal Hazırlık, (2) Bilgi Kontrol, (3) Maliyet, (4) Kesin Adet/Fiyat,
  (5) Matbaa Belirleme, (6) Grafik-Editorya, Matbaada, (7) Hazırda Bekliyor, Depo Girişi Yapıldı (13.443 = bitmiş), Üretimde Beklemede,
  Üretim İptal, Grafik Aşamasında (Ekitap), Doküman Hazır (Ekitap). "Üretimde" = statecode 0 ve statuscode ∉ {Depo Girişi, İptal, Doküman Hazır}.
- Kapak: `new_kapakalternatifi.new_Link` = `C:\cube\Timas_Folder_Entegrasyon\...jpg` (CRM sunucusu yerel yolu) → web'den açılmaz;
  görsel için dosya paylaşımı ya da Annotation gerekir (2.227 ekli dosya, çoğu Account/proje). `new_kapaksecimi.new_Sahibi` GUID değil
  **ad soyad metni** → eşleme FullName ile. Son 90 günde 29 kişi oy vermiş.
- Görev (Task 4212): 12.820 kayıt, 98 sahip, açık görevlerde Subject ve tarih çoğunlukla boş, %75'i 10142 tipi (iş akışı üretimi) →
  ajanda için zayıf; Yalçın Yaman'da 1.178 açık görev (gürültü).
- Örnek kişi (Seval Akbıyık, Editörya): aktif sözleşme 15; üretim kayıtları 1.035 (832'si Depo Girişi=bitmiş; gerçek üretimde ~70);
  kitap 184; açık kapak oylaması 380, verdiği oy 0; proje 198; zimmet 1; gelecek yayın kurulu 0; gelecek etkinlik 0.
