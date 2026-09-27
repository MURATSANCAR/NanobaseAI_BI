# M55 — İşe Alım ve Yetkinlik Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M55.txt` ve `specs/Kurumsal_E_posta_Yönetimi.txt`
(ZEKİ_Moduller3.html'den), `ZEKİ_Veri_Haritasi2.html` (İnsan Kaynakları ve öteki kategoriler), `PROJECT-MEMORY.md`,
`docs/analiz/kampus-kisisel-ekran-crm-2026-09-15.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/audits/crm-kullanici-bilgileri-2026-09-14.md`, `docs/analiz/yetki-mekanizmasi-2026-09-27.md`,
`docs/analiz/oda-rezervasyon-plani-2026-09-15.md`, `docs/product/zeki-module-menu.md`, `src/canvas/nav/navModel.ts`,
`src/canvas/stitch/ModulesMenu.tsx`, `backend/semantic_bridge/access_catalog.json`, `backend/semantic_bridge/access.py`,
`backend/semantic_bridge/people.py`, `backend/semantic_bridge/app.py` (LLM iş uçları), `backend/semantic_layer/runtime/llm_queue.py`,
`backend/semantic_layer/runtime/llm_jobs.py`, `configs/semantic/knowledge/crm/table_descriptions.json`,
`configs/semantic/knowledge/logo/models/`, `configs/schemas/logo-ldds.json`, `configs/semantic/knowledge/logo/knowledge/rules/logo-erp.md`,
kullanıcı belleği (crm-systemuser-directory, no-demo-login, no-tech-names-on-screens, no-silent-limits-rule,
customer-vm-web-watch-off). Sunucuya bağlanılmadı; ölçülmemiş her sayı «ölçülecek» diye yazıldı.

> Bu belge İK dörtlüsünün (M55–M58) ilk kodlanacak modülüdür. Dört modülün ortak temeli («İK-0»: çalışan kaydı,
> birim şeması, KVKK kayıtları, yetki değişikliği) bu belgenin **§14.1** bölümünde eksiksiz tanımlıdır; M56–M58
> belgeleri oraya atıf yapar ve özetini tekrarlar.

---

## 1. Modül ne işe yarar

İş tanımına göre modülün iki kartı var. **İşe alım süreci (K2, Zeki önerir / İK onaylar):** yetkinlik bazlı iş ilanı
taslağı, özgeçmiş ön taraması ve skorlaması, mülakat soru seti önerisi, işe alım süreç panosu. **Yetkinlik haritası
(K3, Zeki analiz eder / İK karar verir):** birim bazında yetkinlik boşluğu, plana dayalı gelecek ihtiyaç tahmini, iç terfi
potansiyeli, ZEKİ projesinin gerektirdiği yeni rollerin tespiti. Çıktılar: İşe Alım Panosu, Yetkinlik Raporu, İK
belgeleri (ilan şablonları, mülakat setleri, teklif ve ret mektupları).

TİMAŞ'ın bugünkü sorunu (kısmen kanıtlı): iş başvuruları kurumsal genel kutuya kitap dosyası, şikâyet, bağış ve reklam
postalarıyla karışık geliyor (Kurumsal E-posta iş tanımı «İş başvuruları (kariyer, staj, iş birliği)» kategorisini bu
kutunun girdileri arasında sayıyor). Başvurunun kime gittiği, cevaplanıp cevaplanmadığı ve özgeçmişin ne kadar
saklandığı hiçbir kayıtta izlenmiyor (varsayım: e-posta kutusunda kalıyor). Portalda İK'ya ait hiçbir ekran, tablo ya da
veri bağlantısı yok.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| İK sorumlusu / uzmanı (süreç sahibi) | **Varsayım.** CRM'de İK birimi görünmüyor: kullanıcı ekip dağılımı Editörya 54, Satış 49, Pazarlama 35, Grafik 13, Mali İşler 10 (canlı sayım 2026-09-15); CRM seçim listelerinde «İnsan Kaynakları» değeri yok, cari kartında «İdari İşler» var. İK muhtemelen İdari İşler ya da Mali İşler içinde 1–2 kişi | Her gün (açık pozisyon varken) | Masaüstü; aday aramalarında telefon |
| İşe alan birim yöneticisi (Editörya, Satış, Pazarlama, Grafik, Mali İşler, Üretim, Depo) | CRM ekip ve departman adlarından kanıtlı; kişi-yönetici bağı yok (CRM `ParentSystemUserId` 186 etkin kullanıcının 1'inde dolu, AD `manager` 0) | Açık pozisyon başına haftada birkaç kez | Telefon ağırlıklı (aday kısa listesi, mülakat notu); masaüstü |
| Genel müdür / üst yönetim (onay) | DYK iş tanımı «İK yetkinlik ve organizasyon sağlık raporu (M55–M58)» istiyor | Pozisyon açma ve teklifte; ayda bir rapor | Telefon (onay), masaüstü (rapor) |
| Mülakata katılan çalışan (ikinci görüşmeci) | Herhangi bir birim | Nadiren | Telefon |
| KVKK irtibat kişisi / hukuk | **Varsayım** (kimin olduğu bilinmiyor) | Aydınlatma metni, saklama süresi, başvuru talebi geldiğinde | Masaüstü |
| Aday (dış kişi) | Portal kullanıcısı **olamaz**: portal girişi yalnız TİMAŞ Active Directory (demo/davet hesabı yok kuralı) | — | Aday e-postayla (ve varsa web sitesi formuyla) etkileşir |

Ölçek: AD'de 213 etkin kişi hesabı (2026-09-14), rehberde CRM ∩ AD ∩ son 365 gün girişi olan 130 kişi (2026-09-16);
bilgisayar kullanmayan depo çalışanları rehberin dışında. Gerçek çalışan sayısı (bordrodaki) **ölçülecek**.

## 3. Bugün bu iş nasıl yapılıyor

Kanıt yok; aşağıdakilerin hepsi **varsayımdır** ve §10'daki sorularla doğrulanmalıdır.

- **İK sorumlusu:** ilan metnini Word'de yazar, iş ilanı sitelerine ve web sitesine koyar; başvurular hem ilan sitesinin
  panelinde hem kurumsal e-postada birikir. Özgeçmişleri tek tek açar, beğendiklerini bir Excel listesine yazar,
  birim yöneticisine e-postayla iletir. Mülakat saatini telefonla ve takvim davetiyle ayarlar. Tıkandığı yer: iki üç
  kanaldaki başvuruyu tek listede görememek, «bu kişiye dönüş yaptık mı» sorusu, ret e-postalarının yazılmaması.
- **Birim yöneticisi:** özgeçmişleri e-posta ekinde alır, notunu kâğıda ya da e-postaya yazar; notlar özlük dosyasına
  girmez, bir sonraki pozisyonda bulunamaz. Tıkandığı yer: adaylar arasında karşılaştırma yok, soru seti her seferinde
  sıfırdan.
- **Üst yönetim:** kadro açma kararını sözlü ya da e-postayla verir; açık pozisyonların ve işe alım maliyetinin toplu
  görüntüsü yok.
- **Yetkinlik haritası:** yazılı bir yetkinlik çerçevesi ya da görev tanımı olduğuna dair depoda iz yok (CRM
  `SystemUserBase.JobTitle` 0, `Skills` 0 dolu). Terfi kararları yöneticinin bilgisiyle verilir.

## 4. İhtiyaçlar ve acı noktaları

**İK sorumlusu**
1. Bütün başvuruları tek listede, aşamasıyla görmek; hiçbir başvurunun cevapsız kalmaması.
2. Özgeçmişin pozisyona uygunluğunu hızla okumak (kanıtlı özet), ama kararın kendisinde kalması.
3. KVKK'ya uygun toplama, saklama ve imha: aydınlatma metni, rıza kaydı, süresi dolan verinin kendiliğinden silinmesi.
4. İlan, teklif ve ret metinlerini şablondan dakikalar içinde üretmek.
5. Mülakat takvimini ve odasını tek yerden ayarlamak.

**Birim yöneticisi**
1. Kısa listeyi telefondan görüp «görüşelim / görüşmeyelim» diyebilmek.
2. Pozisyona göre hazır mülakat soruları ve ortak değerlendirme formu.
3. Başka görüşmecilerin notlarını görmek (kendi pozisyonu için).

**Üst yönetim**
1. Açık pozisyonlar, bekleyen onaylar, ortalama işe alım süresi.
2. Birim bazında yetkinlik boşluğu ve iç aday havuzu (K3 karar desteği).

**KVKK irtibat kişisi**
1. Kim hangi aday verisini ne zaman gördü (erişim kaydı).
2. Saklama süresinin uygulandığının kanıtı (imha tutanağı).
3. İlgili kişi başvurusunda (KVKK md. 11) adayın bütün verisini tek yerden bulup vermek ya da silmek.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- İK sorumlusu olarak **bütün başvuruları tek listede aşamasıyla** görmek istiyorum, çünkü bugün kanallar arasında aday kaybediyorum.
- İK sorumlusu olarak **e-postayla gelen başvurunun aday kaydına kendiliğinden dönüşmesini** istiyorum, çünkü elle aktarım unutuluyor.
- İK sorumlusu olarak **özgeçmişin pozisyon yetkinliklerine göre kanıtlı özetini** görmek istiyorum, çünkü her özgeçmişi baştan sona okumak saatler alıyor.
- İK sorumlusu olarak **ret ve teklif mektubunu şablondan tek tıkla** hazırlamak istiyorum, çünkü bugün ret e-postası çoğu zaman hiç gitmiyor.
- İK sorumlusu olarak **saklama süresi dolan aday verisinin kendiliğinden imha edilmesini** ve bunun kaydını istiyorum, çünkü KVKK denetiminde kanıt göstermem gerekir.
- Birim yöneticisi olarak **telefonumdan kısa listeye «görüşelim / görüşmeyelim»** demek istiyorum, çünkü masada az duruyorum.
- Birim yöneticisi olarak **pozisyona göre önerilen mülakat sorularını** almak istiyorum, çünkü her seferinde sıfırdan hazırlanıyorum.
- Genel müdür olarak **kadro açma talebini telefondan onaylamak** istiyorum, çünkü talepler e-postada kayboluyor.
- Genel müdür olarak **birim bazında yetkinlik boşluğunu** görmek istiyorum, çünkü ZEKİ projesiyle hangi rollerin gerektiğine karar vereceğim.
- KVKK irtibat kişisi olarak **bir adayın bütün kaydını bulup dışa verebilmek ya da silebilmek** istiyorum, çünkü ilgili kişi başvurusuna 30 gün içinde cevap vermek zorundayız.

### Ana ekranlar ve akış

1. **İşe alım panosu** (`/timas/ik/ise-alim`, ilk açılış): üstte dört sayaç — açık pozisyon, bu hafta gelen başvuru,
   aşamasında 5 günden uzun bekleyen aday, cevap bekleyen aday. Altında pozisyon başına sütunlu pano: Başvurdu → Ön eleme
   → Mülakat → Teklif → Sonuç (işe alındı / ret / aday çekildi). Kartta yalnız ad, pozisyon, kaç gündür bu aşamada.
   Telefonda sütunlar sekmeye dönüşür.
2. **Aday ayrıntısı:** özgeçmiş (dosya + çıkarılan metin), Zeki AI'ın kanıtlı eşleşme özeti (yetkinlik → özgeçmişteki
   satır), görüşme notları, yazışmalar, rıza ve saklama durumu («bu kayıt 12.03.2027'de silinecek»).
3. **Pozisyonlar:** pozisyon kartı (birim, yetkinlik listesi, ilan metni, onay durumu), ilan taslağı üretme.
4. **Belgeler:** ilan, mülakat seti, teklif, ret şablonları (`{{aday_adi}}`, `{{pozisyon}}` alanlı; Word çıktısı).
5. **Yetkinlik haritası** (ikinci sürüm): birim × yetkinlik ısı tablosu, boşluklar.

En sık üç işlem ve tık sayısı: (a) yeni başvuruyu ön elemeye alma — panoda kartı sürükle ya da kartın menüsünden
«Ön elemeye al»: **1–2 tık**; (b) adaya ret mektubu gönderme — kart → «Sonuçlandır» → «Ret, mektubu hazırla» → gözden
geçir → «Gönder»: **4 tık** (gönderme insan onayıdır); (c) yöneticinin telefondan kısa liste kararı — bildirimdeki bağlantı
→ aday → «Görüşelim»: **2 tık**.

### Zeki AI'ya soracakları örnek sorular

Not: bugünkü sohbet kapsamı yalnız finans sorularını kabul ediyor (`chat_scope.py`: «Ben ZEKİ AI, size sadece finansal
sorulara cevap verebilirim»). Aşağıdaki sorular genel soru kutusuna değil, İK ekranındaki yetkili soru kutusuna gelir
ve yalnız sorana açık kayıtlar üzerinden cevaplanır (§13).

- «Editörya'daki açık pozisyona bu ay kaç başvuru geldi, kaçı ön elemeyi geçti?»
- «Çocuk kitapları editörü ilanı için yetkinlik bazlı bir ilan taslağı yaz.»
- «Bu adayın özgeçmişinde redaksiyon deneyimini gösteren satırlar hangileri?»
- «Satış temsilcisi mülakatı için davranışsal soru seti öner.»
- «Hangi pozisyonda adaylar en uzun süre bekliyor?»
- «Geçen yıl ret verdiğimiz ve rıza verip havuzda kalan grafiker adayları kimler?»
- «Bu aday için nazik bir ret mektubu taslağı hazırla.»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| E-postadaki başvurunun aday kaydına dönüşmesi | K1 (yüksek güvende) / K2 (düşük güvende İK kuyruğu) | Kurumsal E-posta modülü sınıflandırır; İK kategorisinde yanlış pozitif başka birime kişisel veri sızdırır, bu yüzden eşik muhafazakâr |
| Başvuru alındı cevabı (aydınlatma bağlantılı) | K1 | Şablon İK onaylı; içerikte kişisel değerlendirme yok |
| İlan taslağı | K2 | Zeki yazar, İK düzeltir ve yayına alır |
| Özgeçmiş ön tarama | K2 | Kanıtlı eşleşme listesi; **otomatik ret yok** (KVKK md. 11/1-g) |
| Mülakat soru seti | K2 | |
| Teklif / ret mektubu | K2 | Gönderme her zaman insan eylemi |
| Saklama süresi dolan verinin imhası | K1 | Gece işi, tutanak kaydı |
| Yetkinlik boşluğu, iç terfi, gelecek ihtiyacı | K3 | Zeki analiz eder, yönetim karar verir |

### Bildirim ve uyarı

| Kime | Ne zaman | Kanal |
|---|---|---|
| İK sorumlusu | Yeni başvuru düştüğünde (günlük özet), aday bir aşamada `SLA` gününü aştığında | Portal zili + günlük e-posta özeti |
| Birim yöneticisi | Kısa liste kararı beklediğinde; mülakattan sonra not girilmediğinde | Portal zili + e-posta (içerikte aday adı ve özgeçmiş **yok**, yalnız «bekleyen işiniz var» ve bağlantı) |
| Genel müdür | Kadro açma ya da teklif onayı beklediğinde | Portal zili + e-posta |
| KVKK irtibat kişisi | İmha işi hata verdiğinde; rıza geri çekildiğinde | Portal zili |
| Aday | Başvuru alındı, sonuç | E-posta (kurumsal adresten; hangi adres olduğu §10) |

Süre eşikleri İK'nın ayarıdır, varsayılan yok; kullanıcı sayı tavanı istemedikçe hiçbir liste kısaltılmaz.

### Onay ve yetki

| İşlem | Kim görür | Kim değiştirir | Kim onaylar | Anahtar önerisi |
|---|---|---|---|---|
| İşe alım ekranı | İK, işe alan yönetici (yalnız kendi pozisyonları), GM | İK | — | `sayfa:ik-ise-alim` (açıkça verilir) |
| Pozisyon açma | İK, GM | İK / yönetici talep eder | GM | `ozellik:ik.pozisyon-ac`, `ozellik:ik.pozisyon-onay` |
| Aday kişisel verisi | İK, pozisyonun görüşmecileri | İK | — | `ozellik:ik.aday-gor` (kapsam: yalnız atandığı pozisyon), `ozellik:ik.aday-hepsi` |
| Aday aşama kararı | İK, yönetici | İK, yönetici (kendi pozisyonu) | — | `ozellik:ik.aday-karar` |
| Teklif / ret gönderme | İK | İK | Teklif için GM | `ozellik:ik.yazisma-gonder`, `ozellik:ik.teklif-onay` |
| Şablon kütüphanesi | İK | İK | — | `ozellik:ik.sablon` |
| KVKK ayarı (saklama süresi, aydınlatma metni) | İK, KVKK irtibat | KVKK irtibat | KVKK irtibat | `ozellik:ik.kvkk-yonet` |
| Erişim kaydı | KVKK irtibat, İK müdürü | — | — | `ozellik:ik.erisim-kaydi` |
| Yetkinlik haritası | İK, GM, birim yöneticisi (kendi birimi) | İK | — | `sayfa:ik-yetkinlik`, `ozellik:ik.yetkinlik-duzenle` |
| İK dışa aktarma | İK | — | — | `ozellik:ik.disa-aktar` (genel `ozellik:veri.disa-aktar`'dan ayrı) |

Bütün İK sayfa ve özellik anahtarları **açıkça verilir**; «Herkes» rolüne ve «Bütün sayfalar ve işlemler»e girmez (§14.1).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Çalışan listesi (kim, hangi birim) | CRM `SystemUserBase` ∩ AD | `people.py` rehberi: 130 kişi (2026-09-16); birim = AD OU adı ya da CRM departmanı | İşe giriş tarihi, unvan, görev tanımı, sicil yok (CRM `JobTitle` 0, `EmployeeId` 0 dolu; AD title/department/manager 0) |
| Birim şeması ve birim yöneticisi | CRM `BusinessUnitBase` (25 satır; `ParentBusinessUnitId`, `new_departmanyoneticisiid` «Departman Yöneticisi», `new_editoryaldirektorid`) + `TeamBase` (27) / `TeamMembership` (459) | Tablolar CRM'de var, köprü kataloğunda **yok** (yalnız SQL kapısından sorgulanamaz; özel bağlantıyla okunur) | `new_departmanyoneticisiid` doluluğu **ölçülecek**; kişi-yönetici bağı yok |
| «Dynamics CRM İK modülü çalışan verileri» (iş tanımı) | İş tanımı CRM'i gösteriyor | CRM'de İK modülü kanıtı **yok**. «Kurum içi» tablolar satış hedefi, bütçe kalemi, BT talep yönetimi (354, son değişiklik 2024-07), demirbaş (76). `new_ozgecmisBase` (89) **yazar** özgeçmişidir, çalışan değil | Tamamen boşluk |
| Bordro / özlük | Logo mu, ayrı bordro yazılımı mı, dış bordro firması mı: **ölçülecek** | Logo bilgi paketinde bordro/özlük tablosu yok. Yalnız üretim modülünün `LG_411_EMPLOYEE` (çalışan kaynak kartı: kod, ad, masraf merkezi, saatlik maliyet, `PERSCARDREF` = «Çalışan kartı ref. (İK)», yani ayrı bir İK/bordro ürünündeki karta işaret) ve `LG_411_EMPGROUP`, `LG_411_SLSMAN` (satış temsilcisi) modelleri var | Satır sayıları **ölçülecek**; bordro veritabanının varlığı **ölçülecek** |
| Personel gideri (kadro maliyeti için) | Logo muhasebe fişi `LG_411_01_EMFLINE`, hesap planı `LG_411_EMUHACC`, masraf merkezi `LG_411_EMCENTER` (Kural 16: gider = `ACCOUNTCODE LIKE '7%'`, `SUM(DEBIT-CREDIT)`, `CANCELLED=0`) | Kural katalogda tanımlı; personel giderinin hangi 7xx alt hesaplarında izlendiği **ölçülecek** | 2026 Logo kopyası 2026-08-17'de bitiyor |
| Açık pozisyon, görev tanımı, yetkinlik listesi | Kullanıcı girer | Yok | Yok |
| Organizasyon şeması ve büyüme planı | Kullanıcı girer; bütçe M46'dan | M46 kodlanmadı | Yok |
| Başvurular | Kurumsal E-posta modülü (genel kutu) | Modül kodlanmadı; depoda gelen kutu bağlantısı yok (IMAP/Graph kodu yok). İş tanımındaki «✓ HAZIR» etiketi belgede, uygulamada değil | Yok |
| Özgeçmiş dosyaları | E-posta eki / İK yükler | Yok | Yok |
| Mülakat odası | Oda rezervasyonu (`rooms.py`) | Var, çalışıyor | — |
| Sektör ücret benchmark, rakip yayınevlerinin işe alım trendi, teknoloji talep trendi | Dış | Müşteri ortamında web taraması **kapalı** (kullanıcı kararı 2026-09-25); ücretli rapor yok | İlk sürüm dışı |
| Performans ve potansiyel (iç terfi) | M56 | Kodlanmadı | Yok |

**Veri Haritası hakkında düzeltme:** Haritadaki «İnsan Kaynakları — 19 veri kaynağı» başlığının altındaki 19 kartın
yalnız 1'i (Bağlılık Girdileri → M58) İK'ya aittir; öteki 18'i M1, M2, M3, M5, M9, M11, M14, M19, M22, M36, M37, M38/M45,
M48, M49, M50, M59 kartlarıdır. İK modüllerinin kendi girdileri 8 kart / 24 satırdır ve başka kategorilere dağılmıştır.
M55'in iki kartı: «IK Girdileri» «CRM / Dynamics» altında; «Pazar Girdileri» «Pazar Araştırması» altında aynı başlıklı
M35/M41 kartıyla birleşmiş — haritada M55'e «rakip yayınevlerinin kampanya fiyatları, platform kategori yoğunluğu,
mevsimsel satış trendi» bağlı görünür, iş tanımındaki ücret ve işe alım trendi satırları kaybolmuştur. Harita kartları
başlık adıyla birleştirdiği için İK ihtiyacını yanlış gösterir; «hiçbirine bağlantı yok» tespiti ise doğrudur.

## 7. Diğer modüllerle bağ

| Yön | Modül | Ne akar |
|---|---|---|
| Girdi | **Kurumsal E-posta Yönetimi** | «İş Başvurusu» kategorisindeki e-posta → İK'ya iletilir, otomatik cevapta «İK başvuru formu bağlantısı + süreç bilgisi», «İK takip sistemine otomatik aktarım». M55'in aday kaydı bu «İK takip sistemi»dir. İş tanımındaki «CRM'de görev kaydı oluşturulur» adımı İK için uygulanmaz: CRM'e yazılmaz, kayıt köprünün `semantic_hr_candidates` tablosuna düşer. Otomatik cevap aydınlatma metni bağlantısını taşımalıdır. E-posta modülünün model eğitimi («geçmiş e-postalar etiketlenerek veri seti oluşturulur») iş başvurularının içeriğini eğitim verisine almamalı; yalnız kategori etiketi ve anonimleştirilmiş özellikler |
| Girdi | M46 Bütçe | Onaylı kadro/personel bütçesi (kodlanmadı) |
| Girdi | M56 Performans | İç terfi havuzu için performans ve potansiyel (kodlanmadı) |
| Girdi | M50 ZEKİ Model Eğitim, M48 BT | «ZEKİ projesi için gerekli yeni roller» |
| Çıktı | M57 Eğitim | Yetkinlik boşluğu → eğitim ihtiyacı; işe giren kişinin oryantasyon planı |
| Çıktı | M58 Bağlılık | Yeni çalışan (işe giriş tarihi) → oryantasyon memnuniyet anketi |
| Çıktı | DYK | Açık pozisyon, işe alım süresi, yetkinlik boşluğu özeti |
| Ortak | Kampüs rehberi (`people.py`) | İşe alınan kişi AD hesabı açılınca rehbere kendiliğinden girer; İK kaydı ile rehber AD hesabıyla bağlanır |
| Ortak | Oda rezervasyonu (`rooms.py`) | Mülakat odası |

## 8. Kısıtlar

**Genel proje kuralları:** CRM'e yazılmaz (yalnız okunur; bütün İK kayıtları köprünün `semantic_hr_*` tablolarında);
T-soft'a yazma yasak (İK'nın T-soft'la işi yok); müşteri ortamında web taraması kapalı (ücret ve rakip trendi dış
taramayla toplanamaz); ekranda teknoloji ve model adı yazmaz, kullanıcı yalnız «Zeki AI» görür; demo veri ve demo aday
yok; sayı tavanı yok (liste, aday, dosya sayısında sessiz kesme yok).

**KVKK ve iş hukuku (hukuk teyidi gerekir — aşağıdakiler genel mevzuat bilgisidir, TİMAŞ'ın hukukçusu ya da KVKK
danışmanı onaylamadan uygulanmış sayılmaz):**

- **Hukuki dayanak ve açık rıza.** Başvurulan pozisyon için değerlendirme, sözleşmenin kurulmasıyla doğrudan ilgili
  işleme şartına dayanır (KVKK md. 5/2-c); bunun için açık rıza istenmez. Kurulun yaklaşımına göre başka bir işleme
  şartı varken açık rızaya dayanılmaz ve rıza bir hizmetin ön şartı yapılamaz. **Açık rıza yalnız şunlar için alınır:**
  (a) özgeçmişin başvurulan pozisyon dışında, ileride açılacak pozisyonlar için havuzda tutulması; (b) referans
  kişilerle görüşülmesi (varsayım: aday bildirmeli); (c) gerekli olmayan özel nitelikli veri paylaşılmışsa onun
  işlenmesi (tercihen hiç işlenmez, maskelenir). Rıza kaydı: kim, hangi amaç, hangi aydınlatma sürümü, ne zaman, hangi
  kanal; geri çekme aynı kolaylıkta ve geri çekilince havuz kaydı imha kuyruğuna girer.
- **Aydınlatma (md. 10).** Veri toplandığı anda: e-postayla gelen başvuruya giden otomatik cevapta ve aday kaydı elle
  açıldığında adaya giden ilk e-postada aydınlatma metni bağlantısı. Metnin sürümü kayıtta tutulur.
- **Özel nitelikli veri (md. 6).** Özgeçmişlerde sık görülen sağlık, din, dernek/sendika üyeliği, ceza mahkûmiyeti
  bilgisi ve fotoğraf/ biyometrik değil ama ayrımcılık riski taşıyan alanlar (yaş, cinsiyet, medeni hal, fotoğraf,
  adres) **modele gönderilmez ve skorlamaya girmez**; ekranda yalnız İK görür. 2024 değişikliği (7499 sayılı Kanun) özel
  nitelikli veride istihdam alanındaki hukuki yükümlülükleri ayrı şart olarak saymıştır; aday aşamasında bu şartın
  uygulanıp uygulanmayacağı hukuka sorulur.
- **Otomatik karar (md. 11/1-g).** Adayın «münhasıran otomatik sistemlerle analiz» sonucunda aleyhine bir sonuç
  doğmaması için Zeki AI hiçbir adayı elemez, sıralamayı karar gibi sunmaz; her aşama değişikliği bir insanın kaydıdır.
- **Ayrımcılık yasağı.** İşe alımda ayrımcılık yasağı (6701 sayılı Türkiye İnsan Hakları ve Eşitlik Kurumu Kanunu;
  iş ilişkisinde İş Kanunu md. 5): ilan taslağı yaş/cinsiyet/medeni hal koşulu önermez, önerirse ekranda uyarı çıkar.
- **Saklama ve imha (md. 7, silme-yok etme yönetmeliği).** Veri sınıfı başına süre (işe alınmayan aday, havuz rızalı
  aday, mülakat notu) TİMAŞ'ın saklama-imha politikasından alınır; süre **bilinmiyor** (§10). Gece işi süresi dolanı
  siler ve imha tutanağı yazar. İşe alınan adayın kaydı özlük dosyasına geçer (İş Kanunu md. 75); aday kaydı o anda
  «çalışan» sınıfına taşınır.
- **Erişim ve güvenlik (md. 12).** Görüşmeci yalnız atandığı pozisyonun adaylarını görür; her aday kaydı görüntülemesi
  erişim kaydına yazılır. Portal yöneticisi (teknik hesaplar) aday verisini kendiliğinden görmez (§14.1).
- **Yurt dışı aktarım (md. 9).** Model TİMAŞ adına Türkiye'deki GPU sunucusunda çalışıyor (dış model sağlayıcısı
  2026-09-18'de kaldırıldı); özgeçmiş metni yurt dışına gitmez. Kurumsal e-posta bulut hizmetindeyse o aktarım e-posta
  modülünün konusudur.
- **Test ortamı.** Proje kuralı «main → test sunucusunda gerçek veriyle doğrulama → müşteri VM'i». Test sunucusu TİMAŞ
  ağının dışındadır; gerçek aday verisinin oraya taşınması veri işleyen ilişkisi (ve sunucunun konumuna göre yurt dışı
  aktarım) doğurur. Öneri: test sunucusunda yalnız CRM/AD'den okunan yapı (birim, hesap sayısı) ve test hesabının
  kendi açıp sildiği kayıtlarla doğrulama; gerçek aday verisi yalnız müşteri VM'inde. Karar kullanıcınındır (§10).
- **Model kayıtları.** Bugün model sırası her çağrının son kullanıcı mesajının ilk 500 karakterini saklıyor
  (`llm_queue.py`, `question` kolonu) ve `/api/v1/llm/jobs` işleri mesajın tamamını `messages_json`'da tutuyor, varsayılan
  saklama süresi sınırsız (`SEMANTIC_LLM_JOB_KEEP_DAYS=0`). İK çağrıları bu izleri bırakmamalı (§14.1).

## 9. Kapsam önerisi

**İlk sürüm (en çok değer, en az bağımlılık):**
- İK-0 ortak temeli (§14.1): İK çalışma alanı, açıkça verilen yetkiler, çalışan ve birim kaydı, KVKK kayıtları, imha işi.
- Pozisyon kartı ve onayı (İK açar, GM onaylar), yetkinlik listesi (serbest metin + etiket), ilan taslağı (Zeki AI).
- Aday kaydı: elle özgeçmiş yükleme (PDF/DOCX/ODT) + e-posta modülünden gelecek kayıt için hazır uç; aşama panosu,
  bekleme süresi, görüşmeci atama, mülakat notu formu.
- Kanıtlı özgeçmiş özeti (sayısal skor yerine «yetkinlik → özgeçmişteki satır» listesi; bkz. §12 tuzaklar).
- Mülakat soru seti önerisi.
- Teklif/ret şablonları ve Word çıktısı; gönderim insan eylemi.
- Aydınlatma metni sürümü, rıza kaydı, saklama süresi, gece imhası, erişim kaydı.
- Mülakat odası için oda rezervasyonuna bağlantı.

**Sonraki sürüm:**
- Kurumsal E-posta modülü canlıya çıkınca başvuruların kendiliğinden aday kaydına dönüşmesi (K1/K2).
- Yetkinlik haritası: birim × yetkinlik, boşluk analizi (M56 verisi gelince), iç terfi havuzu (K3).
- Gelecek ihtiyaç tahmini (M46 bütçesi gelince), ZEKİ projesinin yeni rolleri.
- Kamuya açık başvuru formu (portal girişi AD'ye bağlı olduğu için ayrı, oturumsuz bir uç ve kötüye kullanım koruması
  gerekir; ayrı karar).
- Ücret benchmark (dış veri kararı; müşteride web taraması kapalı).

**Mevcut kodda yeniden kullanılacaklar:**
- Yetki: `backend/semantic_bridge/access.py`, `access_catalog.json`, `src/canvas/PageGate.tsx`, `useAdmin.ts` (`useCan`, `usePageAccess`), `src/canvas/admin/AccessAdmin.tsx`.
- Kişi/birim: `backend/semantic_bridge/people.py` (CRM ∩ AD, `ActiveDirectoryGuid` = `objectGUID` eşlemesi).
- Şablon ve Word çıktısı: `backend/semantic_bridge/contracts.py` (şablon tablosu deseni, `{{alan}}`), `contracts_docs.py` (dış kütüphanesiz Word).
- Taslak → yürürlük sürümleme: `editorial_assign.py` (`semantic_editorial_rule_versions`).
- Kişi + portfolyo + yazışma deseni: `freelance.py`, ekranlar `src/canvas/editorial/freelance/`.
- Oda: `backend/semantic_bridge/rooms.py`, `src/canvas/rooms/`.
- Değişiklik kaydı: `semantic_audit` (`admin.py`); bildirim zili (Kampüs), e-posta gönderimi (`reports.py`/`alerts.py` SMTP ayarı).
- Model: `rt.llm_for(...)` / `QueuedLlm` (`backend/semantic_layer/runtime/llm_queue.py`).

## 10. Uzmanlara sorulacak sorular

1. İK'da kaç kişi çalışıyor, hangi birime bağlı; işe alımda son kararı kim veriyor (İK, birim yöneticisi, GM) ve yılda
   yaklaşık kaç pozisyon açılıyor?
2. Başvurular bugün nereye geliyor (genel kurumsal kutu, ayrı bir İK adresi, ilan siteleri) ve adaylara hangi adresten
   yazılmalı?
3. Özlük ve bordro hangi sistemde tutuluyor (Logo'nun İK/bordro ürünü, dış bordro firması, Excel)? Portal salt okunur
   bağlanabilir mi?
4. TİMAŞ'ın aydınlatma metni, saklama-imha politikası ve VERBİS kaydı var mı; aday verisi için belirlenmiş süre ne;
   KVKK irtibat kişisi kim?
5. Gerçek aday verisinin test sunucusunda (TİMAŞ ağı dışında) işlenmesine izin var mı, yoksa İK verisi yalnız müşteri
   VM'inde mi doğrulanmalı?

## 11. Başarı ölçütü

- **Cevapsız başvuru = 0:** sonuçlandırılmamış ve 30 günden eski aday sayısı (panodan, doğrudan SQL ile karşılaştırılır).
- **İşe alım süresi:** pozisyon onayından teklif kabulüne gün (medyan), ilk üç ayda başlangıç değeri ölçülür, sonra izlenir.
- **Ön eleme süresi:** özgeçmiş başına İK'nın harcadığı süre; ilk ay İK'nın kendi beyanıyla önce/sonra.
- **Zeki önerisi kabul oranı:** ilan taslağı ve mülakat seti «olduğu gibi / düzeltilerek / atıldı» oranı (M50'ye girdi).
- **KVKK:** süresi dolmuş ve imha edilmemiş kayıt = 0; her imha için tutanak; ilgili kişi başvurusuna cevap süresi.
- **Kullanım:** açık pozisyonların panoda açılma oranı (%100 hedef), yöneticilerin telefondan karar oranı.

---

## 12. Uzman gözüyle en iyi sistem

Bakış açısı: kurumsal yayınevlerinde ve orta ölçekli şirketlerde 15 yıl çalışmış bir İK uzmanı.

**Sektörde bu iş nasıl yapılıyor (genel pratik; belirli bir firmanın iç süreci doğrulanmadı).** Orta ve büyük
şirketler işe alımı bir aday takip sisteminde (ATS) yürütür: her ilan tek kaynaktan birden çok kanala çıkar, bütün
başvurular tek boru hattına düşer, aşama değişiklikleri ve yazışmalar adayın kartında birikir; yapılandırılmış mülakat
(aynı pozisyona aynı sorular, puan ölçeği önceden tanımlı) ve «önce bağımsız puan, sonra tartışma» kuralı yaygındır.
İyi sistemlerde yetkinlik çerçevesi pozisyon kartına bağlıdır, ilan metni ve mülakat soruları oradan türetilir; KVKK/GDPR
için saklama süresi ve rıza aday kartındadır, imha kendiliğinden işler. Yayınevlerinde işe alımın özelliği: editörlük,
çeviri, grafik gibi rollerde **portfolyo ve deneme işi** (örnek redaksiyon, çeviri denemesi) mülakattan daha belirleyicidir;
serbest çalışan havuzu ile kadrolu aday havuzu sık kesişir.

**TİMAŞ için mükemmel sistem.** Tek boru hattı; e-postadan gelen başvuru kendiliğinden karta döner ve adaya aydınlatmalı
«aldık» cevabı gider. Pozisyon kartı yetkinlikleri taşır; Zeki AI ilanı, mülakat sorularını ve deneme işini o
yetkinliklerden taslaklar. Özgeçmiş özeti sayı değil kanıttır: «redaksiyon deneyimi → 2019–2023 X yayınevi, redaktör».
Editörlük adaylarına deneme metni verilir ve sonuç M3/M5'in kalite ölçütleriyle aynı dilde değerlendirilir. Serbest
çalışan havuzu (M8) ile aday havuzu arasında «bu kişi daha önce bizimle serbest çalıştı» bağı görünür (rıza varsa).
Kadro açma talebi bütçeden (M46) doğar, GM telefondan onaylar. Hiçbir aday cevapsız kalmaz; hiçbir veri süresinden uzun
yaşamaz.

**Uzmanın bir iş günü.**
- **09:00** Kampüs'te İK kutusu: «dün 7 başvuru, 2 aday 5 günü aştı, 1 teklif GM onayında». Panoya geçer.
- **09:15** Yeni başvuruların kanıtlı özetlerine bakar; 4'ünü ön elemeye alır, 2'sine «pozisyonla eşleşmiyor» der ve
  ret mektubunu şablondan hazırlatır, okur, gönderir. Bir adayın özgeçmişinde sağlık bilgisi var: sistem o satırı
  maskelemiş, uyarı göstermiş.
- **10:30** Editörya yöneticisi telefondan kısa listeyi onaylamış; İK iki mülakatı takvime koyar, odayı aynı ekrandan ayırır.
  Adaya giden davet şablondan çıkar.
- **12:00** Yeni «çocuk kitapları editörü» pozisyonu için yöneticinin talebini açar; Zeki AI yetkinliklerden ilan taslağı
  yazar, taslakta «25–35 yaş» gibi bir ifade olmadığını sistem denetlemiştir; İK düzeltip GM onayına gönderir.
- **14:00** Mülakat; iki görüşmeci telefondan puan formunu doldurur, birbirinin puanını kendi puanlarını girene kadar görmez.
- **16:00** Teklif mektubu şablondan; GM onayı beklenir.
- **17:30** Gün sonu: «yarın 3 adayın aşama süresi dolacak»; gece imha işi 12 eski adayı silecek, liste önceden görünür.

**«Bunu görürsem hemen kullanırım» dediği 3 özellik**
1. E-postadaki başvurunun kendiliğinden aday kartına dönüşmesi ve adaya aydınlatmalı otomatik cevap.
2. Ret/teklif/davet mektubunun şablondan tek tıkla çıkması ve gönderildiğinin kartta görünmesi.
3. Yöneticinin telefondan «görüşelim / görüşmeyelim» diyebilmesi; İK'nın yönetici kovalamaması.

**«Bunu yaparsanız kullanmam» dediği 3 tuzak**
1. Adayları 0–100 puanla sıralayıp düşük puanlıyı gizlemek: hem hukuken otomatik karar riski, hem uzman güvenmez.
   Kanıt listesi göster, sıralamayı bana bırak.
2. Her aşamada zorunlu alan yağmuru: bir kartı ilerletmek için 10 alan doldurtan sistem ilk hafta bırakılır.
3. Yöneticinin bütün adayları ve bütün notları görmesi ya da e-postaya aday özgeçmişinin eklenmesi: gizlilik biter,
   çalışan adayların (iç başvuru) bilgisi sızar.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Çalışan ve birim listesi (görüşmeci seçimi, işe alan birim) | — | `SystemUserBase` (FullName, DomainName, ActiveDirectoryGuid, BusinessUnitId, IsDisabled, AccessMode), `BusinessUnitBase` (Name, ParentBusinessUnitId, new_departmanyoneticisiid), `TeamBase`/`TeamMembership` | Hiçbir şey | Kimlik ve birim verisi kayıttan gelir; model üretmez |
| Pozisyonun kadro maliyeti (bilgi amaçlı, sonraki sürüm) | `LG_411_01_EMFLINE` ⨝ `LG_411_EMUHACC` ⨝ `LG_411_EMCENTER`; Kural 16 gider ölçüsü (`ACCOUNTCODE LIKE '7%'`, `SUM(DEBIT-CREDIT)`, `CANCELLED=0`) + İK'nın seçtiği personel gider hesapları | — | Hiçbir şey | Rakam Logo'dan SQL ile; hangi hesapların personel gideri olduğu **ölçülecek** |
| İlan taslağı | — | — | Pozisyon kartındaki yetkinliklerden ilan metni yazar; yasak koşul (yaş, cinsiyet, medeni hal) önermez | Taslak metin, modelin güçlü olduğu iş |
| Ayrımcı ifade denetimi | — | — | Kapalı seçim: «ayrımcı koşul var / yok» — tek token + olasılık (vLLM `structured_outputs.choice` + logprobs yöntemi); düşük olasılıkta uyarı | Hızlı, açıklanabilir sınıflandırma |
| Özgeçmiş metin çıkarma | — | — | Hiçbir şey (dosyadan metin: PDF/DOCX/ODT ayrıştırıcı; editör modülünün belge incelemesi kodundan) | Deterministik iş |
| Özel nitelikli ve ayrımcılık riskli alanların maskelenmesi | — | — | Önce kural (T.C. kimlik no, telefon, adres, doğum tarihi, fotoğraf kaldırılır); sonra kapalı seçim: satır «sağlık/din/sendika/ceza bilgisi içerir mi» | Modele giden metin önce temizlenir; model yalnız sınıflandırır |
| Kanıtlı eşleşme özeti | — | — | Her yetkinlik için özgeçmişteki destekleyen satırı alıntılar ya da «kanıt yok» der; sayı üretmez | Uzmanın okuma süresini kısaltır; karar insanda |
| Mülakat soru seti | — | — | Yetkinlik başına davranışsal soru ve değerlendirme ölçütü önerir | Taslak metin |
| Teklif/ret mektubu | — | — | Şablonu doldurur, tonu yumuşatır; aday adına ya da sonuç gerekçesine uydurma bilgi eklemez | Taslak metin, gönderme insan eylemi |
| Başvuru e-postasının sınıflanması | — | — | Kurumsal E-posta modülünün işi: «İş başvurusu / staj / iş birliği / diğer» kapalı seçim | Sınıflandırma; İK'ya düşük güvendeki kayıt kuyruğa |
| İK ekranı soru kutusu | — | — | Soruyu önceden tanımlı İK sorgularından birine eşler (ör. «pozisyon başına başvuru sayısı»), sayıyı SQL'den alır, cümleyi kurar | Rakam modelden gelmez; model yalnız niyet seçer ve yorumlar |

Model çağrıları: köprü içinden `rt.llm_for("ik")` (öncelik: ekranda bekleyen kullanıcı 0, toplu özet 2). `LlmClient`
doğrudan kurulmaz; `/api/v1/llm/jobs` İK için **kullanılmaz** (mesajı süresiz saklar ve yöneticiye açıktır). Ekranda model
adı yazmaz; kullanıcı yalnız «Zeki AI» görür.

## 14. Kodlama planı (kodlayıcıya devir)

### 14.1 İK-0 ortak temel (M55–M58'in hepsinden önce; bu belgede tek kez tanımlanır)

**Köprü dosyaları**
- `backend/semantic_bridge/hr_core.py` — tablolar (`ensure()` deseni, `semantic_` önek, `tenant_id` her tabloda),
  çalışan/birim deposu, KVKK kayıtları, erişim kaydı, imha işi, model çağrısı sarmalayıcısı `hr_llm(rt, purpose)`.
- `backend/semantic_bridge/hr_sources.py` — salt okunur kaynaklar: CRM (prod CRM, köprünün CRM öneki `crm_prefix` ile;
  `SystemUserBase`, `BusinessUnitBase`, `TeamBase`, `TeamMembership`), AD (`people.py`'nin AD okuma işlevleri yeniden
  kullanılır), Logo gider (`LG_411_01_EMFLINE`, `LG_411_EMUHACC`, `LG_411_EMCENTER`). CRM'deki bu tablolar semantik
  katalogda olmadığından SQL kapısından (`run_sql`) değil, `management/` raporlarındaki gibi kendi salt okunur
  bağlantısıyla okunur.
- `backend/semantic_bridge/hr_api.py` — `register(app, *, rt, access, audit, ...)` (desen: `contracts_api.py`).

**Tablolar (bi_meta Postgres)**

| Tablo | Ana kolonlar |
|---|---|
| `semantic_hr_units` | id, tenant_id, name, parent_id, manager_employee_id, crm_businessunit_id, ad_ou, active, updated_by, updated_at |
| `semantic_hr_employees` | id, tenant_id, username (AD sAMAccountName; bilgisayarsız çalışanda boş), ad_guid, crm_systemuser_id, display_name, unit_id, manager_id, title, start_date, end_date, status (`aktif`/`ayrildi`), source_json (alan → kaynak: crm/ad/ik), updated_by, updated_at. **T.C. kimlik no, adres, ücret, sağlık tutulmaz** |
| `semantic_hr_notices` | id, tenant_id, audience (`aday`/`calisan`), version, title, body, published_at, published_by |
| `semantic_hr_consents` | id, tenant_id, subject_type (`aday`/`calisan`), subject_id, purpose (ör. `aday_havuzu`, `referans`), notice_version, given_at, channel, evidence, withdrawn_at |
| `semantic_hr_retention` | data_class (ör. `aday_ret`, `aday_havuz`, `mulakat_notu`, `anket_yorum`), keep_days, legal_basis, approved_by, approved_at |
| `semantic_hr_access_log` | id, tenant_id, at, username, subject_type, subject_id, action (`goruntule`/`indir`/`disa_aktar`), purpose |
| `semantic_hr_purge_runs` | id, tenant_id, at, data_class, purged_count, detail_json (kimlik değil, yalnız kayıt kimliklerinin özeti), error |

**Uçlar**
- `GET /api/v1/hr/me` (kendi çalışan kaydım, rızalarım, haklarım) — OPEN
- `GET /api/v1/hr/employees`, `GET/PATCH /api/v1/hr/employees/{id}`, `POST /api/v1/hr/employees/sync-preview` (CRM ∩ AD'den öneri; kaydetme İK'nın onayıyla `POST /api/v1/hr/employees/sync-apply`)
- `GET/POST/PATCH /api/v1/hr/units`
- `GET/POST /api/v1/hr/notices`, `GET/POST /api/v1/hr/consents`, `POST /api/v1/hr/consents/{id}/withdraw`
- `GET/PUT /api/v1/hr/retention`
- `POST /api/v1/hr/purge/run-due` — SYSTEM (zamanlayıcı)
- `GET /api/v1/hr/access-log`

**Yetki değişikliği (kod)**
- `access_catalog.json`: yeni alan `{"id": "ik", "label": "İnsan Kaynakları"}`; İK sayfaları `"explicit": true` taşır.
- `access.py`: `explicit_keys()` bugün yalnız özellikleri kapsar; **sayfaları da kapsamalı** (`pages` içinde
  `explicit` olanlar). Aksi hâlde «Herkes» rolü (kurulumda bütün sayfalar açık) İK ekranlarını herkese açar.
- `access.py`: yeni işaret `"sensitive": true` (İK kişisel veri anahtarları). `granted()` yöneticiye `sensitive`
  anahtarları kendiliğinden vermez; yönetici Yetkiler ekranından kendine rol bağlayabilir ve bu `semantic_audit`'e
  düşer. **Karar kullanıcıya sorulur** (bugünkü kural «yönetici her şeyi görür»).
- `access.py` `RULES`: `("/api/v1/hr/purge/run-due", SYSTEM)`, `("/api/v1/hr/me", OPEN)`, `("/api/v1/hr/", OWN)` (İK uçları
  kendi anahtarını ve kapsamını — kendi pozisyonu, kendi ekibi — denetler); `test_access.py` bütün yolların bir öneke
  düştüğünü denetler.
- `navModel.ts`: `NavGroupId`'ye `'ik'`; grup «İnsan Kaynakları» (Yönetim'den önce). `navModel.test.ts` katalog eşliğini denetler.
- `ModulesMenu.tsx`: `LIVE` içine `M55: '/ik/ise-alim'` …; `GROUP_HOME['İnsan Kaynakları']`.

**Model izleri (kod)**
- `llm_queue.py` `QueuedLlm.chat`: `queue_label` argümanı; verilirse `question` kolonuna mesaj yerine etiket yazılır
  (ör. `ik: özgeçmiş özeti`). `hr_llm()` her çağrıda bunu verir.
- İK uçları `sl_query_log`'a (Promt izleyici) sonuç yazmaz; İK soru kutusu ayrı, içeriksiz bir sayaç tutar.

**Zamanlayıcı:** `timas-hr-purge.timer` her gece 03:40 → `POST /api/v1/hr/purge/run-due` (sistem jetonuyla). İlk kez
elle koşturulur, sonra zamanlayıcıya bırakılır.

**Büyüklük:** M (1–2 gün), yetki değişikliği testleriyle birlikte.

### 14.2 M55'e özgü

**Köprü dosyaları:** `backend/semantic_bridge/hr_recruit.py` (depo + iş kuralları), `hr_recruit_api.py` (uçlar),
`hr_recruit_text.py` (özgeçmiş metin çıkarma, maskeleme, model istemleri).

**Tablolar**

| Tablo | Ana kolonlar |
|---|---|
| `semantic_hr_positions` | id, tenant_id, title, unit_id, hiring_manager_id, competencies_json, posting_text, state (`taslak`/`onayda`/`acik`/`beklemede`/`kapandi`), approved_by, approved_at, opened_at, closed_at, created_by |
| `semantic_hr_candidates` | id, tenant_id, position_id, full_name, email, phone, source (`eposta`/`elle`/`ilan_sitesi`/`ic_basvuru`), stage (`basvurdu`/`on_eleme`/`mulakat`/`teklif`/`sonuc`), outcome (`ise_alindi`/`ret`/`cekildi`), stage_since, retention_class, retention_until, purged_at, employee_id (işe alınınca), created_at |
| `semantic_hr_candidate_files` | id, candidate_id, filename, mime, blob, extracted_text, masked_text, created_at |
| `semantic_hr_candidate_evidence` | id, candidate_id, competency, quote, verdict (`kanit_var`/`kanit_yok`), model_run_id, created_at |
| `semantic_hr_interviews` | id, candidate_id, starts_at, room_booking_id, interviewers_json |
| `semantic_hr_interview_notes` | id, interview_id, author, scores_json, note, submitted_at (başkasının notu kendi notunu girene kadar gizli) |
| `semantic_hr_templates` | id, tenant_id, kind (`ilan`/`davet`/`teklif`/`ret`/`alindi`), name, body, version, state |
| `semantic_hr_messages` | id, candidate_id, kind, body, sent_by, sent_at, status |
| `semantic_hr_stage_log` | id, candidate_id, at, actor, from_stage, to_stage, reason |

**Uçlar (`/api/v1/hr/recruit/*`)**
- `GET/POST /positions`, `GET/PATCH /positions/{id}`, `POST /positions/{id}/submit`, `POST /positions/{id}/approve`,
  `POST /positions/{id}/posting-draft` (Zeki AI)
- `GET /pipeline?position=` (pano), `GET/POST /candidates`, `GET/PATCH /candidates/{id}`, `POST /candidates/{id}/stage`
- `POST /candidates/{id}/files` (yükleme → metin çıkarma → maskeleme), `GET /candidates/{id}/files/{fid}`
- `POST /candidates/{id}/evidence` (Zeki AI kanıt özeti), `POST /positions/{id}/interview-kit` (soru seti)
- `GET/POST /interviews`, `POST /interviews/{id}/notes`
- `GET/POST/PATCH /templates`, `POST /candidates/{id}/letters/{kind}` (taslak), `POST /messages/{id}/send`
- `POST /intake` — Kurumsal E-posta modülünün çağıracağı uç (SYSTEM jetonuyla): gönderen, konu, gövde, ekler → aday kaydı
  + «alındı» cevabı kuyruğa
- `GET /candidates/{id}/export` (KVKK ilgili kişi talebi), `DELETE /candidates/{id}` (talep üzerine imha; tutanaklı)

**Ekranlar** `src/canvas/hr/recruit/`: `RecruitBoard.tsx` (pano), `CandidateDrawer.tsx`, `PositionEditor.tsx`,
`TemplatesScreen.tsx`, ortak `src/canvas/hr/hrApi.ts`. Rotalar: `/timas/ik/ise-alim`, `/timas/ik/ise-alim/aday/:id`,
`/timas/ik/pozisyonlar`, `/timas/ik/belgeler`. Menü: çalışma alanı «İnsan Kaynakları», bölüm «İşe alım» (İşe alım panosu,
Pozisyonlar, Belgeler); sonraki sürümde «Yetkinlik haritası». Kampüs: `GROUP_HOME['İnsan Kaynakları']` kutusu, yalnız
yetkisi olana görünür. Telefon: pano sütunları sekme, kart menüsünden aşama değişikliği (sürükleme zorunlu değil).

**Yetki anahtarları** (hepsi `explicit`, kişisel veri taşıyanlar `sensitive`)
- `sayfa:ik-ise-alim`, `sayfa:ik-pozisyonlar`, `sayfa:ik-belgeler`
- `ozellik:ik.pozisyon-ac`, `ozellik:ik.pozisyon-onay`, `ozellik:ik.aday-gor` (kapsam: görüşmecisi olduğu pozisyon),
  `ozellik:ik.aday-hepsi` (sensitive), `ozellik:ik.aday-karar`, `ozellik:ik.yazisma-gonder`, `ozellik:ik.teklif-onay`,
  `ozellik:ik.sablon`, `ozellik:ik.kvkk-yonet` (sensitive), `ozellik:ik.erisim-kaydi` (sensitive), `ozellik:ik.disa-aktar` (sensitive)

**Zamanlayıcı:** İK-0 imha işi yeterli; ek olarak `POST /api/v1/hr/recruit/reminders/run-due` 15 dakikada bir (aşama süresi
aşımı bildirimi) — uyarılar zamanlayıcısının yanına, aynı desenle.

**Kabul testleri (gerçek veri, doğrudan SQL ile karşılaştırma; test hesabıyla açılıp silinen kayıtlar dışında kişisel veri yazılmaz)**
1. **Etkin CRM kullanıcı sayısı:** ekrandaki «CRM'de etkin kullanıcı» sayısı =
   `SELECT COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase WHERE IsDisabled = 0 AND AccessMode IN (0,1) AND DomainName LIKE 'TIMAS\%';`
   (AD kesişimi `people.py`'nin bağımsız çağrısıyla; rehber `GET /api/v1/people` toplamı ile birebir).
2. **Birim dağılımı:** eşitleme önizlemesindeki birim başına kişi sayısı =
   `SELECT b.Name, COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase u JOIN Timas_MSCRM.dbo.BusinessUnitBase b ON b.BusinessUnitId = u.BusinessUnitId WHERE u.IsDisabled = 0 GROUP BY b.Name;`
3. **Departman yöneticisi doluluğu:** önizlemedeki «yöneticisi bilinen birim» sayısı =
   `SELECT COUNT(*) AS birim, SUM(CASE WHEN new_departmanyoneticisiid IS NOT NULL THEN 1 ELSE 0 END) AS yoneticili FROM Timas_MSCRM.dbo.BusinessUnitBase WHERE IsDisabled = 0;`
4. **Ekip üyeliği:** önizlemedeki ekip başına etkin üye =
   `SELECT t.Name, COUNT(*) FROM Timas_MSCRM.dbo.TeamMembership m JOIN Timas_MSCRM.dbo.TeamBase t ON t.TeamId = m.TeamId JOIN Timas_MSCRM.dbo.SystemUserBase u ON u.SystemUserId = m.SystemUserId WHERE u.IsDisabled = 0 GROUP BY t.Name;`
5. **Pano sayaçları:** panodaki pozisyon başına aşama sayıları =
   `SELECT position_id, stage, COUNT(*) FROM semantic_hr_candidates WHERE tenant_id = :t AND purged_at IS NULL GROUP BY position_id, stage;`
   ve «5 günden uzun bekleyen» = `... WHERE stage <> 'sonuc' AND stage_since < now() - interval '5 days'` (eşik İK ayarından).
6. **İmha:** gece işinden sonra `SELECT COUNT(*) FROM semantic_hr_candidates WHERE retention_until < now() AND purged_at IS NULL;` = 0
   ve `semantic_hr_purge_runs` son satırının `purged_count`'u işten önceki bu sayıya eşit.
7. **Model izi:** bir özgeçmiş özeti sonrası `SELECT purpose, question FROM sl_llm_queue WHERE purpose LIKE '%ik%' ORDER BY enqueued_at DESC LIMIT 5;`
   satırlarında özgeçmiş metni yok, yalnız etiket var (bu satırların ne kadar saklandığı **ölçülecek**).
8. **Yetki:** İK rolü olmayan test hesabı → `/timas/ik/ise-alim` «Yetkiniz yok», `GET /api/v1/hr/recruit/pipeline` 403;
   «Herkes» rolü bütün sayfalar açıkken de İK sayfaları kapalı.
9. **Personel gideri (sonraki sürüm, gösterilirse):** ekrandaki tutar =
   `SELECT SUM(l.DEBIT - l.CREDIT) FROM LG_411_01_EMFLINE l WHERE l.CANCELLED = 0 AND l.ACCOUNTCODE IN (:personel_hesaplari) AND l.DATE_ >= '2026-01-01' AND l.DATE_ < '2026-08-18';`
   (hesap listesi önce `SELECT CODE, DEFINITION_ FROM LG_411_EMUHACC WHERE CODE LIKE '7%'` ile İK/muhasebe tarafından seçilir — **ölçülecek**).

**Ölçüm betiği (kodlamadan önce, sunucu erişimi açılınca; salt okunur):**
`SELECT COUNT(*) FROM LG_411_EMPLOYEE;` · `SELECT COUNT(*) FROM LG_411_EMPGROUP;` · `SELECT COUNT(*) FROM LG_411_SLSMAN WHERE ACTIVE = 0;` ·
`SELECT COUNT(*) FROM LG_411_EMPLOYEE WHERE PERSCARDREF > 0;` (bordro/İK ürününe bağ var mı) · Logo sunucusunda ayrı bir
İK/bordro veritabanı olup olmadığı (`SELECT name FROM sys.databases`) — sonuçlar bu belgeye işlenir.

**Bağımlılık:** önce İK-0 (§14.1). Kurumsal E-posta modülü paralel kodlanabilir; M55 `POST /intake` ucunu hazır tutar, e-posta
modülü gelince bağlanır. M56–M58 İK-0 bittikten sonra M55 ile paralel kodlanabilir.

**Tahmini büyüklük:** İK-0 **M**; M55 ilk sürüm **L** (3+ gün: pano, dosya işleme, maskeleme, şablonlar, KVKK akışları);
yetkinlik haritası sonraki sürüm **M**.
