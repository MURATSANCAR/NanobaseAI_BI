# M56 — Performans Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M56.txt` (ZEKİ_Moduller3.html'den),
`specs/DYK.txt`, `ZEKİ_Veri_Haritasi2.html`, `PROJECT-MEMORY.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/audits/crm-kullanici-bilgileri-2026-09-14.md`, `docs/analiz/kampus-kisisel-ekran-crm-2026-09-15.md`,
`docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `backend/semantic_bridge/access_catalog.json`, `access.py`,
`editorial_assign.py`, `people.py`, `src/canvas/nav/navModel.ts`, `configs/semantic/knowledge/crm/table_descriptions.json`,
`configs/semantic/knowledge/logo/knowledge/rules/logo-erp.md`, `configs/semantic/knowledge/logo/knowledge/reference/logo-ldds.md`,
`configs/semantic/knowledge/logo/models/`, kullanıcı belleği (crm-systemuser-directory, sales-are-invoiced-lines,
net-ciro-line-formula, no-tech-names-on-screens, no-silent-limits-rule). Ortak İK temeli: `M55-ise-alim-yetkinlik.md` §14.1.
Sunucuya bağlanılmadı; ölçülmemiş her sayı «ölçülecek» diye yazıldı.

---

## 1. Modül ne işe yarar

İş tanımının iki kartı: **Hedef ve OKR yönetimi (K2, Zeki önerir / yönetici onaylar)** — birim ve kişi OKR şablonları,
kişi → birim → şirket hedef uyumu, çeyreklik ilerleme izleme, hedef revizyonu. **Performans değerlendirme (K3, Zeki
analiz eder / yönetici karar verir)** — 360 derece geri bildirim analizi, çalışan performans skoru ve yorum özeti,
yüksek/düşük performans tespiti, ödüllendirme ve iyileştirme önerileri. Çıktılar: Performans Panosu, Değerlendirme
Raporları (360 özeti, yüksek potansiyel listesi), Gelişim Planları (M57'ye eğitim ihtiyacı). Terfi, ücret ve iyileştirme
kararları yönetimdedir (iş tanımı K3).

TİMAŞ'ın bugünkü durumu: portalda hedef ya da değerlendirme kaydı yok; CRM'de de yok. Satış hedefleri CRM'de var ama
**bölge ve stok kartı bazında**, kişiye bağlı değil (`new_satishedefleriBase`, 334.982 satır, 15 bölge, 2023–2026).
Değerlendirmenin bugün yapılıp yapılmadığı bilinmiyor (varsayım: yıllık, form ya da sözlü; §10).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Birim yöneticisi (asıl kullanıcı: hedef koyar, değerlendirir) | Editörya, Satış, Pazarlama, Grafik, Mali İşler, Üretim, Depo — CRM ekip ve departman adlarından kanıtlı. Kimin kimin yöneticisi olduğu bilinmiyor (CRM `ParentSystemUserId` 186 etkin kullanıcının 1'inde dolu; AD `manager` 0); `BusinessUnitBase.new_departmanyoneticisiid` doluluğu **ölçülecek** | Çeyrekte bir check-in, dönemde bir değerlendirme; haftalık göz atma | Masaüstü (değerlendirme yazımı), telefon (onay, ilerleme) |
| İK sorumlusu (süreç sahibi) | **Varsayım** (bkz. M55 §2: CRM'de İK birimi görünmüyor; muhtemelen İdari İşler içinde) | Dönem açılış/kapanışta yoğun, arada haftalık | Masaüstü |
| Çalışan (öz değerlendirme, kendi hedefleri) | Rehberdeki 130 kişi (CRM ∩ AD ∩ son 365 gün giriş); bilgisayarsız çalışanlar dışarıda | Çeyrekte bir; dönem sonunda | Telefon ağırlıklı |
| Genel müdür / üst yönetim (şirket hedefleri, kalibrasyon, terfi/ücret kararı) | DYK iş tanımı «İK yetkinlik ve organizasyon sağlık raporu» | Yılda bir hedef, dönem sonunda kalibrasyon | Masaüstü |
| 360 geri bildirim veren meslektaş | Herhangi bir birim | Dönemde bir, birkaç form | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

Kanıt yok; hepsi **varsayım**.

- **Birim yöneticisi:** hedefler yıl başında toplantıda sözlü ya da e-postayla konur; satışta bölge hedefi CRM'deki
  `new_satishedefleri`'nden (bölge × stok × ay) okunur, kişiye paylaştırma Excel'de yapılır. Editöryada iş yükü CRM
  proje/üretim kayıtlarından ve 2026-09'dan beri portalın editör atama ekranından (M2) izlenebilir, ama bu bir
  değerlendirme değildir. Tıkandığı yer: dönem sonunda «yıl içinde ne oldu» hafızaya kalır; yazılı iz yok.
- **İK sorumlusu:** değerlendirme varsa Word/Excel formunu dağıtır, e-postayla toplar, özlük dosyasına koyar;
  tamamlanma takibi elle.
- **Çalışan:** kendi hedefini ve değerlendirmesini yazılı olarak görmez (varsayım).
- **Üst yönetim:** birimler arası karşılaştırma yok; terfi/ücret kararı yöneticinin önerisiyle.

## 4. İhtiyaçlar ve acı noktaları

**Birim yöneticisi**
1. Ekibinin hedeflerini ve ilerlemesini tek ekranda görmek; çeyrek toplantısına hazır gelmek.
2. Değerlendirme yazarken yılın olaylarını hatırlamak (sistemdeki iş kayıtlarından özet).
3. Az zaman: form kısa olmalı, telefondan onay.
4. Ekibinin dışındaki kişilerin verisini görmemek, kendi ekibinin verisinin başkalarına açılmaması.

**İK sorumlusu**
1. Dönemi açıp kapatmak, kimin eksik olduğunu görmek ve hatırlatmak.
2. Birimler arası tutarlılık (kalibrasyon) için dağılımı görmek.
3. Değerlendirme sonucunun özlük kaydına ve M57 gelişim planına akması.

**Çalışan**
1. Hedeflerimi ve bunların şirket hedefine nasıl bağlandığını bilmek.
2. Kendi değerlendirmemi okumak, itiraz ya da yorum yazabilmek.
3. Değerlendirmede kullanılan verinin ne olduğunu bilmek (sürpriz ölçüm yok).

**Üst yönetim**
1. Şirket hedeflerinin birimlere inişi ve çeyreklik ilerleme.
2. Yüksek performans ve yüksek potansiyel özeti (K3), terfi/ücret kararına girdi.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- Birim yöneticisi olarak **ekibimin hedeflerini ve çeyrek ilerlemesini tek ekranda** görmek istiyorum, çünkü çeyrek toplantısına Excel toplayarak hazırlanıyorum.
- Birim yöneticisi olarak **değerlendirme yazarken kişinin yıl içindeki iş kayıtlarının özetini** görmek istiyorum, çünkü yalnız son iki ayı hatırlıyorum.
- Birim yöneticisi olarak **Zeki AI'dan yorumumu daha yapıcı ve somut hâle getirmesini** istemek istiyorum, çünkü geri bildirim yazmak zor.
- Birim yöneticisi olarak **telefondan hedef revizyonu talebini onaylamak** istiyorum, çünkü talepler e-postada kayboluyor.
- İK sorumlusu olarak **dönemi açıp kimin öz değerlendirmesini ya da yönetici değerlendirmesini bitirmediğini** görmek ve hatırlatma göndermek istiyorum, çünkü bugün elle kovalıyorum.
- İK sorumlusu olarak **birimlerin puan dağılımını yan yana** görmek istiyorum, çünkü bir birim herkese en yüksek puanı veriyor olabilir.
- Çalışan olarak **kendi hedeflerimi ve şirket hedefine bağını** görmek istiyorum, çünkü neye göre değerlendirileceğimi bilmek istiyorum.
- Çalışan olarak **değerlendirmemi okuyup yorum ve itiraz yazmak** istiyorum, çünkü tek taraflı karar kabul edilmez.
- Genel müdür olarak **şirket hedeflerinin birimlere inişini ve çeyrek ilerlemesini** görmek istiyorum, çünkü yönetim kuruluna rapor veriyorum.

### Ana ekranlar ve akış

1. **Performansım** (`/timas/ik/performansim`, herkes için, yalnız kendisi): hedeflerim (ilerleme çubuğu, son check-in),
   bağlı olduğu birim/şirket hedefi, açık görevlerim (öz değerlendirme, 360 formu), geçmiş değerlendirmelerim.
2. **Ekibim** (`/timas/ik/ekibim`, yönetici): ekip listesi × hedef ilerlemesi, eksik check-in, değerlendirme durumu;
   kişiye tıklayınca hedefler, notlar, «iş kayıtları özeti» (bilgi amaçlı, §13).
3. **Hedef ağacı** (`/timas/ik/hedefler`): şirket → birim → kişi; hizalanmamış hedefler işaretli.
4. **Değerlendirme dönemi** (`/timas/ik/degerlendirme`, İK): dönem aç/kapat, form şablonu, tamamlanma panosu,
   kalibrasyon görünümü (birim × dağılım; kişi adları yalnız İK ve GM'de).
5. **Değerlendirme formu:** öz değerlendirme → yönetici değerlendirmesi → görüşme → çalışan yorumu → İK onayı.

İlk açılışta: çalışan «Performansım»ı, yönetici «Ekibim»i, İK «Değerlendirme dönemi»ni görür (yetkiye göre).
En sık üç işlem: (a) çalışanın çeyrek check-in'i — Performansım → hedef → yüzde + kısa not → Kaydet: **3 tık**;
(b) yöneticinin hedef revizyonu onayı — bildirim → «Onayla»: **2 tık**; (c) yöneticinin değerlendirme yazması — Ekibim →
kişi → «Değerlendir» → formu doldur → Gönder: **4 tık + form**.

### Zeki AI'ya soracakları örnek sorular

Bugünkü sohbet yalnız finans sorusu kabul ediyor; bu sorular İK ekranındaki yetkili soru kutusundan, sorana açık
kayıtlar üzerinden cevaplanır.

- «Ekibimde bu çeyrek check-in yapmayan kim var?»
- «Satış biriminin hedeflerinden hangisi şirketin yıllık ciro hedefine bağlı değil?»
- «<Ekibimdeki bir editörün> yıl içindeki tamamlanan editörlük işlerini özetle.» (yalnız yöneticisi ve İK)
- «Bu değerlendirme yorumumu somut örneklerle yeniden yaz.»
- «Değerlendirme döneminde hangi birimlerin tamamlanma oranı yüzde 50'nin altında?»
- «Satış ekibinin bu yılki faturalı net satışı hedefin yüzde kaçında?» (Logo'dan, §13)
- «Bu çalışan için bir gelişim planı taslağı öner.»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| Dönem hatırlatmaları, eksik form listesi | K1 | Gece işi |
| Hedef ilerlemesinin sistem verisinden hesaplanması (ör. satış hedefi gerçekleşme) | K1 | Yalnız ölçüsü tanımlı hedeflerde; rakam Logo/CRM'den |
| OKR taslağı ve hizalama önerisi | K2 | Zeki önerir, yönetici onaylar |
| Değerlendirme yorumunun düzeltilmesi | K4 | Yönetici yazar, Zeki yardımcı olur |
| 360 yorumlarının tema özeti | K3 | Yorum sahibi gizli; tema düzeyinde |
| Yüksek/düşük performans ve potansiyel listesi | K3 | Yalnız İK ve GM; otomatik sonuç yok |
| Terfi, ücret, iyileştirme kararı | K3 | Yönetim kararı; sistem yalnız kaydı tutar |

### Bildirim ve uyarı

| Kime | Ne zaman | Kanal |
|---|---|---|
| Çalışan | Dönem açıldı; öz değerlendirme son tarihine 3 gün kala; yöneticisi değerlendirmeyi paylaştı | Portal zili + e-posta (içerik yok, bağlantı) |
| Yönetici | Ekibinde check-in eksik; değerlendirme bekliyor; hedef revizyonu talebi | Portal zili + haftalık e-posta özeti |
| İK | Dönem tamamlanma oranı; itiraz geldi | Portal zili |
| GM | Kalibrasyon hazır | Portal zili |

Süreler İK ayarıdır; eşik varsayılanı konmaz.

### Onay ve yetki

| İşlem | Kim görür | Kim değiştirir | Kim onaylar | Anahtar önerisi |
|---|---|---|---|---|
| Kendi hedef ve değerlendirmesi | Çalışanın kendisi | Çalışan (öz değerlendirme, yorum) | — | `sayfa:ik-performansim` (açıkça verilir; kurulumda bütün çalışanları kapsayan AD grubuna bağlanır) |
| Ekibim | Yönetici, yalnız `semantic_hr_employees.manager_id` = kendisi olanlar (ve onların altı) | Yönetici | — | `sayfa:ik-ekibim`, kapsam kodda |
| Hedef ağacı | Herkes kendi zincirini; İK ve GM hepsini | Yönetici (birim), GM (şirket) | Üst yönetici | `sayfa:ik-hedefler`, `ozellik:ik.hedef-yaz`, `ozellik:ik.hedef-onay` |
| Değerlendirme dönemi, form şablonu | İK | İK | — | `sayfa:ik-degerlendirme`, `ozellik:ik.donem-yonet` |
| Başkasının değerlendirmesi | Yöneticisi, İK, GM | Yöneticisi | İK | `ozellik:ik.degerlendirme-yaz`, `ozellik:ik.degerlendirme-onay` |
| Kalibrasyon, potansiyel listesi | İK, GM | — | — | `ozellik:ik.kalibrasyon` (sensitive) |
| İş kayıtları özeti (sistem verisi) | Yalnız yöneticisi ve İK, çalışanın kendisi de görür | — | — | `ozellik:ik.is-ozeti` |
| Dışa aktarma | İK | — | — | `ozellik:ik.disa-aktar` |

Bütün anahtarlar açıkça verilir; «Herkes» rolüne ve portal yöneticisine kendiliğinden gelmez (M55 §14.1).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kişi – yönetici hiyerarşisi | CRM `BusinessUnitBase` (`ParentBusinessUnitId`, `new_departmanyoneticisiid`), İK girer | CRM `ParentSystemUserId` 1/186, AD `manager` 0; departman yöneticisi alanı var, doluluğu **ölçülecek** | **En kritik boşluk:** «ekibim» kapsamı hiyerarşi olmadan kurulamaz; İK-0'daki birim şeması İK tarafından tamamlanmalı |
| OKR ve hedefler | Kullanıcı girer | Yok | Yok |
| 360 geri bildirim | Portal anketi (kullanıcı girer) | Yok. CRM'de anket tabloları var ama müşteri/ürün oylaması için ve neredeyse boş (`new_anketBase` 2, `new_anketmoduluBase` 14 kitap/set oylaması, `new_anketcevaplarBase` 1 satır) | Yok |
| Proje ve görev tamamlanma | Portal M2 `semantic_editorial_tasks` (editör, rol, durum, başlangıç, termin, `done_at`); CRM sahiplik kayıtları: 2026'da proje sahibi 42 kişi / 513 kayıt, sözleşme 32 / 1.506, sipariş 23 / 23.000, etkinlik 20 / 7.045 (2026-09-14 sayımı) | M2 tablosu var; CRM okunur | CRM'de toplu sahiplik servis hesabında birikiyor (bir servis hesabı 1.343 plan rolü + 1.791 sözleşme sahibi); iş planı/plan sorumlusu modülleri ölü (son değişiklik 2025-12 ve 2022-09); CRM görevlerinin %75'i iş akışı üretimi. **Bu sayılar performans ölçüsü değildir**, yalnız bağlam |
| Satış hedefi ve gerçekleşme | Hedef: CRM `new_satishedefleriBase` (bölge × stok × ay); gerçekleşme: Logo faturalı satır, net ciro = `LINENET` (satış TRCODE 7,8,9 − iade 2,3; `LINETYPE=0`, `CANCELLED=0`, `INVOICEREF<>0`) | Hedef kişiye bağlı değil; Logo `INVOICE.SALESMANREF` → `SLSMAN` var ama TİMAŞ'ta dolu mu **ölçülecek**; CRM `SystemUserBase.new_KullancKoduLogoyaGnderilen` (21 etkin kullanıcıda dolu) kişi ↔ Logo satış temsilcisi köprüsü olabilir, **ölçülecek** | Kişi bazında satış hedefi yok; 2026 Logo kopyası 2026-08-17'de bitiyor |
| Önceki dönem performans | Kullanıcı girer / eski form | Yok | Yok (ilk dönem baz olur) |
| Birim ortalaması ve norm | Portal hesaplar | — | İlk dönemden sonra |
| Sektör performans benchmark | Dış | Müşteride web taraması kapalı | İlk sürüm dışı |

**Veri Haritası hakkında düzeltme:** M56'nın iki girdi kartı haritada İK kategorisinde değil. «Performans Girdileri»
«Sosyal Medya & Dijital» altında M18/M30/M34/M40/M44 kartıyla birleşmiş: haritada M56'ya «önceki ay satış, kampanya ve
backlist performansı, platform metrikleri, e-bülten oranları» bağlı görünür — iş tanımındaki OKR, 360 ve görev
tamamlanma satırları kaybolmuştur. «Karşılaştırma Girdileri» «Pazar Araştırması» altında M42 kartıyla birleşmiş (kanal
kâr marjı, müşteri LTV). Haritadaki «İnsan Kaynakları — 19 kaynak» başlığının 19 kartından yalnız biri (M58) İK'dır.

## 7. Diğer modüllerle bağ

| Yön | Modül | Ne akar |
|---|---|---|
| Girdi | İK-0 (M55 §14.1) | Çalışan kaydı, birim şeması, yönetici bağı |
| Girdi | M46 Bütçe ve satış hedefleri | Şirket/birim hedefleri; kitap bazlı satış hedefi (kodlanmadı) |
| Girdi | M2 Editör atama | Editörün görev ve termin kayıtları (`semantic_editorial_tasks`) — bilgi amaçlı |
| Girdi | M30 Saha satış | Bölge/bayi hedef-gerçekleşme (kodlanmadı) |
| Çıktı | M57 Eğitim | Gelişim planı → eğitim ihtiyacı öncelik listesi |
| Çıktı | M55 Yetkinlik haritası | Performans × potansiyel → iç terfi havuzu |
| Çıktı | M58 Bağlılık | Değerlendirme sonrası nabız anketi (süreç memnuniyeti), anonim |
| Çıktı | DYK | Dönem tamamlanma, dağılım özeti (kişi adı yok) |

## 8. Kısıtlar

**Genel proje kuralları:** CRM'e yazılmaz; T-soft'a yazma yasak; müşteride web taraması kapalı; ekranda teknoloji/model
adı yok; demo çalışan ya da demo değerlendirme yok; sayı tavanı yok (dağılım grafiklerinde kişi kesilmez).

**KVKK ve iş hukuku (hukuk teyidi gerekir; genel mevzuat bilgisidir):**
- **Dayanak.** Performans değerlendirmesi iş sözleşmesinin ifasıyla doğrudan ilgilidir (KVKK md. 5/2-c) ve işverenin
  meşru menfaatine dayanabilir (md. 5/2-f) — bunun için açık rıza istenmez; iş ilişkisinde rızanın «özgür irade» şartı
  zayıf olduğundan rızaya dayanmak önerilmez. Çalışanlara aydınlatma yapılır (md. 10): hangi veri, hangi amaçla,
  kim görür, ne kadar saklanır.
- **Sistem verisinin değerlendirmede kullanılması.** CRM/portal iş kayıtlarının (sahip olunan proje, görev terminleri)
  değerlendirmeye bilgi olarak sunulması bir çalışan izleme faaliyetidir: ölçülü olmalı (md. 4), aydınlatmada açıkça
  yazılmalı, çalışanın kendisi de aynı özeti görmeli. **Portal kullanım kayıtları** (`sl_query_log` soru geçmişi, giriş
  sayıları) performans değerlendirmesinde **kullanılmaz**; bu kayıtlar başka amaçla toplanmıştır (amaçla sınırlılık).
- **Otomatik karar (md. 11/1-g).** Sistem kişiye puan vermez; «yüksek/düşük performans» listesi Zeki AI'ın kendi
  ürettiği bir sonuç değil, yöneticilerin girdiği değerlendirmelerin dağılımıdır. Terfi, ücret ve iyileştirme kararı
  yönetimindir ve kayıtta karar verenin adı durur.
- **Eşit davranma (İş Kanunu md. 5).** Kalibrasyon görünümü birimler arası sapmayı gösterir; cinsiyet, yaş gibi
  alanlar tutulmadığı için bu kırılım yapılmaz (tutulmaması bilinçli).
- **360 geri bildirim.** Veren kişi değerlendirilen ve yöneticisi tarafından görülmez; yorumlar tema düzeyinde
  sunulur. Az kişilik grupta anonimlik kendiliğinden bozulur: «en az kaç veren olmazsa özet gösterilmez» eşiği bir
  gizlilik kuralıdır, sayı tavanı değildir; yine de kullanıcı kuralı gereği **kendiliğinden konmaz**, karar olarak
  sorulur ve uygulanırsa ekranda «bu kırılım N'den az kişi olduğu için gösterilmiyor» diye açıkça yazar.
- **Özlük dosyası (İş Kanunu md. 75).** Onaylanan değerlendirme özlük kaydıdır; işverenin saklama yükümlülüğü ve
  saklama süresi (çalışan ayrıldıktan sonra) TİMAŞ politikasından alınır — **bilinmiyor**.
- **Erişim.** Yönetici yalnız kendi hiyerarşisini görür; her kişi kaydı görüntülemesi `semantic_hr_access_log`'a
  yazılır; portal yöneticisi kendiliğinden görmez (M55 §14.1 `sensitive`).
- **İlgili kişi hakkı (md. 11).** Çalışan kendi değerlendirmesini ve hakkında kullanılan iş kaydı özetini görür; bu,
  «Performansım» ekranıyla karşılanır.
- **Test ortamı.** Gerçek değerlendirme verisi TİMAŞ ağı dışındaki test sunucusuna taşınmaz (M55 §8); test sunucusunda
  test hesabının açıp sildiği kayıtlarla doğrulanır.

## 9. Kapsam önerisi

**İlk sürüm:**
- İK-0 üzerinde yönetici hiyerarşisinin tamamlanması (İK'nın birim şeması ve yönetici bağı ekranı).
- Hedef kaydı: şirket → birim → kişi ağacı, ağırlık, ölçüt (serbest metin ya da tanımlı sistem ölçüsü), çeyreklik
  check-in, revizyon talebi ve onayı.
- Değerlendirme dönemi: form şablonu (yetkinlik + hedef bölümü), öz değerlendirme → yönetici → görüşme → çalışan yorumu → İK onayı.
- Performansım, Ekibim, Değerlendirme dönemi panoları; hatırlatmalar.
- Zeki AI: OKR taslağı ve hizalama önerisi; yönetici yorumunu yeniden yazma; iş kayıtları özeti (bilgi amaçlı, çalışan da görür).
- Satış rolleri için tanımlı sistem ölçüsü: Logo faturalı net satış (yalnız `SALESMANREF` doluysa; ölçüm sonrası karar).

**Sonraki sürüm:**
- 360 geri bildirim (anonimlik eşiği kararıyla), yorum tema özeti.
- Kalibrasyon ve 9 kutulu performans × potansiyel görünümü (K3), yüksek potansiyel listesi.
- Gelişim planı → M57'ye otomatik eğitim ihtiyacı.
- M46 hedefleriyle otomatik bağ; sektör benchmark (dış veri kararı).

**Mevcut kodda yeniden kullanılacaklar:**
- İK-0: `hr_core.py`, `hr_sources.py`, `hr_api.py` (M55 §14.1).
- Taslak → onay → yürürlük sürümleme: `editorial_assign.py` (`semantic_editorial_rule_versions` deseni) — form şablonu sürümü için.
- Görev/termin verisi: `editorial_assign.py` (`semantic_editorial_tasks`).
- Pano kartı ve grafik: `src/canvas/board/`; planlı rapor: `reports.py`; uyarı/hatırlatma zamanlayıcı deseni: `alerts.py`.
- Yetki: `access.py`, `useCan`, `PageGate`.
- Model: `rt.llm_for("ik")` üzerinden `hr_llm()` (M55 §14.1).

## 10. Uzmanlara sorulacak sorular

1. Bugün performans değerlendirmesi yapılıyor mu; hangi sıklıkla, hangi formla, sonucu nerede saklanıyor?
2. Kim kimin yöneticisi — güncel bir organizasyon şeması var mı, kim tutuyor?
3. Değerlendirme sonucu ücret, prim ya da terfiye doğrudan bağlanıyor mu (bağlanıyorsa itiraz süreci şart)?
4. Satış temsilcilerinin kişisel hedefi var mı; Logo faturalarında satış temsilcisi alanı dolduruluyor mu?
5. CRM ve portal iş kayıtlarının değerlendirmede bilgi olarak gösterilmesine TİMAŞ yönetimi ve hukuku onay veriyor mu?

## 11. Başarı ölçütü

- **Dönem tamamlanma:** öz değerlendirme ve yönetici değerlendirmesi tamamlanma oranı (hedef %100), son tarihte.
- **Hedef hizalama:** şirket hedefine bağlı kişi hedefi oranı.
- **Check-in düzeni:** çeyrekte en az bir check-in yapan çalışan oranı.
- **Süre:** yöneticinin kişi başına değerlendirme yazma süresi (ilk dönem beyanla, sonra ekrandaki süre ile).
- **Güven:** itiraz sayısı ve sonuçlanma süresi; çalışan anketi (M58) «değerlendirme adil» maddesi.
- **KVKK:** yetkisiz erişim denemesi 403 sayısı, erişim kaydında yöneticinin kendi ekibi dışına bakış = 0.

---

## 12. Uzman gözüyle en iyi sistem

Bakış açısı: 15 yıllık İK uzmanı (performans ve yetenek yönetimi).

**Sektörde bu iş nasıl yapılıyor (genel pratik).** Yıllık tek değerlendirme yerini sürekli performans yönetimine
bırakıyor: az sayıda (3–5) hedef, çeyreklik check-in, yönetici–çalışan birebir görüşme notları, yıl sonunda bunların
toplamı üzerinden kısa bir değerlendirme. İyi sistemler hedefleri şirket hedefine görünür biçimde bağlar, hedefin
ölçüsü bir sistemde varsa (satış, üretim) ilerlemeyi oradan kendisi okur, yoksa kişinin beyanını ister. 360 geri
bildirim gelişim amaçlı kullanılır, ücret kararına doğrudan bağlanmaz. Kalibrasyon toplantısı birimler arası puan
enflasyonunu düzeltir. Yayınevlerinde üretimin bir bölümü ölçülebilir (satış, basılan kitap sayısı, termin tutma),
editoryal kalitenin büyük bölümü ölçülemez; bu yüzden iyi sistem ölçülebilen ile yargıya dayananı ayrı gösterir.

**TİMAŞ için mükemmel sistem.** Her çalışanın 3–5 hedefi var ve her biri şirket hedefine bağlı. Satışta hedefin
ilerlemesi Logo'daki faturalı net satıştan kendiliğinden gelir; editöryada termin tutma M2'den bilgi olarak görünür ama
puan değildir. Yönetici çeyrekte bir kısa not yazar; yıl sonunda Zeki AI bu notlardan ve hedef kayıtlarından bir
«yılın özeti» taslağı çıkarır, yönetici düzeltir. Çalışan her şeyi görür: hedefini, notlarını, hakkında gösterilen iş
kaydı özetini. İK dönemi tek ekrandan yönetir; kalibrasyonda birimler arası sapma görünür.

**Uzmanın bir iş günü (değerlendirme döneminin ikinci haftası).**
- **09:00** Değerlendirme dönemi panosu: öz değerlendirmelerin %72'si, yönetici değerlendirmelerinin %40'ı tamam;
  Satış ve Depo geride. Tek tıkla eksiklere hatırlatma.
- **10:00** Grafik birimi yöneticisiyle birebir: yönetici bir değerlendirmeyi «çok sert» bulmuş; Zeki AI yorumu
  somut örneklerle yeniden yazar, yönetici son hâli kendisi seçer.
- **11:30** Bir çalışan itiraz yazmış; itiraz ekranında değerlendirme, hedef kayıtları ve iki tarafın notları yan yana.
- **14:00** Kalibrasyon hazırlığı: birim × puan dağılımı; Editörya'da herkes «beklenenin üstünde». Kişi adları yalnız
  İK ve GM'de, toplantıda perdede yalnız dağılım.
- **16:00** Onaylanan değerlendirmelerden gelişim planı maddeleri M57'ye eğitim ihtiyacı olarak düşer.
- **17:30** Gün sonu: yarın son gün; 11 yönetici değerlendirmesi eksik.

**«Bunu görürsem hemen kullanırım» dediği 3 özellik**
1. Dönem tamamlanma panosu ve tek tıkla hatırlatma.
2. Yöneticinin çeyrek notlarından ve hedef kayıtlarından yıl sonu değerlendirme taslağı.
3. Satış hedefinin Logo'dan kendiliğinden ilerlemesi (elle Excel güncellemesi bitmesi).

**«Bunu yaparsanız kullanmam» dediği 3 tuzak**
1. CRM kayıt sayısını, portal giriş sayısını ya da «soru sorma» sıklığını performans puanına çevirmek: yanlış ölçer,
   güveni bitirir, hukuken de sorunlu.
2. Çalışanın görmediği bir «potansiyel skoru» ya da yapay zekâ puanı.
3. 30 alanlı form ve zorunlu 360: yöneticiler ilk dönemde bırakır.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Ekip ve hiyerarşi | — | `SystemUserBase` (BusinessUnitId), `BusinessUnitBase` (ParentBusinessUnitId, new_departmanyoneticisiid), `TeamMembership` | Hiçbir şey | Kapsam (kim kimi görür) kayıttan gelir |
| Satış hedefinin ilerlemesi (satış rolleri) | `LG_411_01_STLINE` ⨝ `LG_411_01_INVOICE` (`SALESMANREF`) ⨝ `LG_411_SLSMAN`; net ciro = satış (`TRCODE` 7,8,9) `LINENET` − iade (2,3) `LINENET`, `LINETYPE=0`, `CANCELLED=0`, `INVOICEREF<>0`; dönem 2026 için `LG_411` | Hedef: `new_satishedefleriBase` (bölge; kişiye bağ yok). Kişi ↔ Logo temsilcisi: `SystemUserBase.new_KullancKoduLogoyaGnderilen` ↔ `SLSMAN.CODE` (**ölçülecek**) | Hiçbir şey (rakam SQL'den) | Kayıt sistemi Logo; model rakam üretmez |
| İş kayıtları özeti (editör) | — | `new_projeBase` (OwnerId), `new_sozlesmeBase` (OwnerId), `new_UretimBase` (new_SorumluEditor) + portal `semantic_editorial_tasks` (termin, `done_at`) | Sayıları (SQL'den) okunur cümleye çevirir: «yılda 14 proje, 11'i termininde»; yorum katmaz | Yöneticinin hafızasını destekler; bilgi amaçlı |
| OKR taslağı ve hizalama | — | — | Birim hedefinden kişi hedefi taslağı; kapalı seçim: «bu kişi hedefi hangi birim hedefine bağlı» (aday listesi içinden, tek token + olasılık) | Eşleştirme ve taslak metin |
| Yorum yeniden yazma | — | — | Yöneticinin metnini somut, yapıcı hâle getirir; yeni olay uydurmaz, yalnız verilen notları kullanır | Taslak metin (K4) |
| Yıl sonu değerlendirme taslağı | — | — | Çeyrek notları + hedef kayıtları → özet taslak; her cümle kaynağına (not/hedef kimliği) bağlı | Özet; kanıtsız cümle yok |
| 360 yorum tema özeti (sonraki sürüm) | — | — | Yorumları temalara ayırır (kapalı tema listesi, tek token + olasılık); alıntı vermez, kimliği ele verecek ayrıntıyı atar | Sınıflandırma + özet |
| İK soru kutusu | — | — | Soruyu tanımlı İK sorgusuna eşler, sayı SQL'den | Doğal dil soru; rakam modelden gelmez |

Model çağrıları `rt.llm_for("ik")` üzerinden, `hr_llm()` sarmalayıcısıyla (kuyrukta içerik yerine etiket; M55 §14.1).
`/api/v1/llm/jobs` kullanılmaz. Ekranda yalnız «Zeki AI».

## 14. Kodlama planı (kodlayıcıya devir)

**Ön koşul — İK-0 ortak temel** (tam tanım `M55-ise-alim-yetkinlik.md` §14.1): `hr_core.py`/`hr_sources.py`/`hr_api.py`;
tablolar `semantic_hr_units`, `semantic_hr_employees` (manager_id dahil), `semantic_hr_notices`, `semantic_hr_consents`,
`semantic_hr_retention`, `semantic_hr_access_log`, `semantic_hr_purge_runs`; `access.py`'de sayfalar için `explicit`
ve yönetici için `sensitive` desteği; menüde «İnsan Kaynakları» çalışma alanı; `hr_llm()` ile kuyrukta etiket.

**Köprü dosyaları:** `backend/semantic_bridge/hr_performance.py` (depo, dönem/form iş kuralları, kapsam: yöneticinin
hiyerarşisi), `hr_performance_api.py` (uçlar), `hr_performance_sources.py` (Logo satış ölçüsü, CRM iş kaydı sayıları,
M2 görev özetleri — hepsi salt okunur).

**Tablolar**

| Tablo | Ana kolonlar |
|---|---|
| `semantic_hr_goals` | id, tenant_id, level (`sirket`/`birim`/`kisi`), owner_employee_id, unit_id, parent_goal_id, title, measure_kind (`beyan`/`sistem`), system_measure (ör. `logo_net_satis`), target_value, weight, period (ör. `2026-Q4`), state (`taslak`/`onayda`/`yururlukte`/`kapandi`), approved_by, approved_at |
| `semantic_hr_goal_checkins` | id, goal_id, at, author, progress_pct, value, note |
| `semantic_hr_goal_revisions` | id, goal_id, requested_by, requested_at, change_json, decided_by, decided_at, decision |
| `semantic_hr_review_cycles` | id, tenant_id, name, starts_on, ends_on, form_template_id, state (`hazirlik`/`acik`/`kalibrasyon`/`kapandi`) |
| `semantic_hr_review_forms` | id, tenant_id, version, sections_json, state |
| `semantic_hr_reviews` | id, cycle_id, employee_id, manager_id, self_json, self_submitted_at, manager_json, manager_submitted_at, meeting_at, employee_comment, objection, hr_approved_by, hr_approved_at, state |
| `semantic_hr_work_summaries` | id, employee_id, cycle_id, generated_at, facts_json (SQL'den sayılar ve kaynak sorgu kimliği), text (Zeki AI cümlesi), shown_to_employee_at |

**Uçlar (`/api/v1/hr/performance/*`)**
- `GET /me` (Performansım), `GET /team` (Ekibim; kapsam yöneticinin hiyerarşisi)
- `GET/POST /goals`, `PATCH /goals/{id}`, `POST /goals/{id}/checkins`, `POST /goals/{id}/revisions`, `POST /revisions/{id}/decide`
- `POST /goals/draft` (Zeki AI OKR taslağı), `POST /goals/{id}/align-suggest` (hizalama önerisi)
- `GET /goals/{id}/progress` (sistem ölçüsü: Logo satış)
- `GET/POST /cycles`, `PATCH /cycles/{id}`, `GET /cycles/{id}/status` (tamamlanma), `POST /cycles/{id}/remind`
- `GET/POST /forms`, `GET/PATCH /reviews/{id}`, `POST /reviews/{id}/submit-self`, `POST /reviews/{id}/submit-manager`,
  `POST /reviews/{id}/comment`, `POST /reviews/{id}/approve`
- `POST /reviews/{id}/rewrite` (Zeki AI yorum), `POST /reviews/{id}/work-summary` (iş kayıtları özeti)
- `GET /cycles/{id}/calibration` (İK/GM)
- `POST /reminders/run-due` — SYSTEM

**Ekranlar** `src/canvas/hr/performance/`: `MyPerformance.tsx`, `MyTeam.tsx`, `GoalTree.tsx`, `ReviewCycle.tsx`,
`ReviewForm.tsx`, `Calibration.tsx`. Rotalar: `/timas/ik/performansim`, `/timas/ik/ekibim`, `/timas/ik/hedefler`,
`/timas/ik/degerlendirme`, `/timas/ik/degerlendirme/:id`. Menü: «İnsan Kaynakları» çalışma alanı, bölüm «Performans»
(Performansım, Ekibim, Hedefler, Değerlendirme dönemi). Kampüs: «Performansım» kısa kartı (açık görevim varsa:
«Öz değerlendirmeniz 3 gün içinde bitiyor»). Telefon: check-in ve onay tek sütunda.

**Yetki anahtarları** (hepsi `explicit`)
- `sayfa:ik-performansim` (bütün çalışan AD grubuna bağlanır), `sayfa:ik-ekibim`, `sayfa:ik-hedefler`, `sayfa:ik-degerlendirme`
- `ozellik:ik.hedef-yaz`, `ozellik:ik.hedef-onay`, `ozellik:ik.donem-yonet`, `ozellik:ik.degerlendirme-yaz`,
  `ozellik:ik.degerlendirme-onay`, `ozellik:ik.kalibrasyon` (sensitive), `ozellik:ik.is-ozeti`, `ozellik:ik.disa-aktar` (sensitive)

**Zamanlayıcı:** `timas-hr-reminders.timer` her gün 08:30 → `POST /api/v1/hr/performance/reminders/run-due` (dönem son
tarihi, eksik check-in); ilk kez elle koşturulur.

**Kabul testleri (gerçek veri; kişisel değerlendirme verisi test sunucusuna yazılmaz, test hesabının kaydıyla)**
1. **Satış temsilcisi alanı doluluğu (ölçüm, kodlamadan önce):**
   `SELECT COUNT(*) AS satir, SUM(CASE WHEN i.SALESMANREF <> 0 THEN 1 ELSE 0 END) AS temsilcili FROM LG_411_01_INVOICE i WHERE i.CANCELLED = 0 AND i.TRCODE IN (7,8,9);`
   Temsilcili oran düşükse «sistem ölçüsü: Logo net satış» seçeneği ekranda kapalı kalır.
2. **Temsilci bazında net satış:** hedef ilerleme ekranındaki tutar =
   `SELECT s.CODE, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET WHEN l.TRCODE IN (2,3) THEN -l.LINENET ELSE 0 END) FROM LG_411_01_STLINE l JOIN LG_411_01_INVOICE i ON i.LOGICALREF = l.INVOICEREF JOIN LG_411_SLSMAN s ON s.LOGICALREF = i.SALESMANREF WHERE l.CANCELLED = 0 AND l.LINETYPE = 0 AND l.INVOICEREF <> 0 AND l.DATE_ >= '2026-01-01' AND l.DATE_ < '2026-08-18' GROUP BY s.CODE;`
3. **CRM kişi ↔ Logo temsilcisi köprüsü:**
   `SELECT COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase u WHERE u.IsDisabled = 0 AND u.new_KullancKoduLogoyaGnderilen IS NOT NULL;`
   ve bu kodların `LG_411_SLSMAN.CODE` ile eşleşen sayısı (Logo'da ayrı sorgu, Python'da kesişim) — ekrandaki «eşleşen temsilci» sayısına eşit.
4. **Editör iş özeti:** `work-summary` cevabındaki «tamamlanan iş» sayısı =
   `SELECT COUNT(*) FROM semantic_editorial_tasks WHERE tenant_id = :t AND editor_id = :crm_id AND status = 'tamamlandi' AND done_at >= :donem_bas AND done_at < :donem_son;`
   ve «termininde» = aynı sorgu `AND done_at::date <= due_date`.
5. **CRM proje sahipliği:** özetteki proje sayısı =
   `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_projeBase WHERE OwnerId = :systemuserid AND CreatedOn >= :donem_bas AND CreatedOn < :donem_son;`
6. **Dönem tamamlanma:** panodaki oran =
   `SELECT COUNT(*) FILTER (WHERE self_submitted_at IS NOT NULL) * 1.0 / COUNT(*), COUNT(*) FILTER (WHERE manager_submitted_at IS NOT NULL) * 1.0 / COUNT(*) FROM semantic_hr_reviews WHERE cycle_id = :c;`
7. **Kapsam:** yönetici test hesabı `GET /api/v1/hr/performance/team` yalnız `manager_id` zincirindeki kişileri döndürür
   (`WITH RECURSIVE` ile doğrudan SQL'le karşılaştırılır); zincir dışı kişinin `GET /reviews/{id}` çağrısı 403 ve
   `semantic_hr_access_log`'a reddedilen deneme düşer.
8. **Hiyerarşi doluluğu (ölçüm):** `SELECT COUNT(*) FILTER (WHERE manager_id IS NULL) FROM semantic_hr_employees WHERE tenant_id = :t AND status = 'aktif';`
   — sıfır değilse «Ekibim» ekranı eksik kişileri İK'ya listeler.

**Bağımlılık:** İK-0 önce (özellikle birim şeması ve `manager_id`). M55 ile paralel kodlanabilir. M57'ye gelişim planı
akışı M57 hazır olunca bağlanır. M46 gelene kadar şirket hedefleri elle girilir.

**Tahmini büyüklük:** ilk sürüm **L** (3+ gün: hedef ağacı, dönem/form akışı, kapsam, Logo ölçüsü, hatırlatmalar);
360 ve kalibrasyon sonraki sürüm **M**.
