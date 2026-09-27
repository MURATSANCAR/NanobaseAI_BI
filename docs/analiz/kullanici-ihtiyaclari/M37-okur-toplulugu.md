# M37 — Okuyucu Topluluğu ve Topluluk Yönetimi (CRM Katmanı): kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M37.txt` (ZEKİ_Moduller3.html'den),
`specs/Okuyucu_Veri_Tabanı_Entegrasyo.txt`, `specs/E_Ticaret_Müşteri_Yönetimi_Ent.txt`, sınır için `specs/M24.txt`,
`M27.txt`, `M38.txt`, `M51.txt`, `specs/ANALIZ-EK.md`; depoda `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`,
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`, `PROJECT-MEMORY.md`,
`AGENTS.md` («Basın ve web taraması»: kişisel veri tutulmaz), `configs/semantic/knowledge/crm/table_descriptions.json`
(2026-09-09), `backend/semantic_bridge/seo_geo/reviews.py`, `backend/semantic_bridge/web_watch.py`,
`backend/semantic_bridge/chat_scope.py` (bellek üzerinden); bellek: customer-vm-web-watch-off, web-watch-open-sources,
seo-geo-module, chat-persona-zeki-ai, no-demo-login. `ZEKİ_Veri_Haritasi2.html` verilen klasörde yok. Sunucuya
bağlanılmadı; sayılar depodaki tarihli ölçümlerdir. **Bu modül okur kişisel verisi işler; KVKK bölüm 8'de ayrıntılıdır.**

## 1. Modül ne işe yarar

İş tanımına göre modülün iki işi var. Okur segmentasyonu ve kişiselleştirme (K1): ilgi alanı ve satın alma geçmişine göre
segment, kişisel kitap önerisi, doğum günü ve yıl dönümü tebriki, okuduğu serinin yeni kitabı bildirimi. Topluluk
etkileşimi (K2): okuma kulübü ve çevrim içi etkinlik, anket, yorum teşviki, sadık okur ödülü. Çıktılar: segment kartları,
topluluk etkinlik raporu, CRM okur profili zenginleştirme.

TİMAŞ'ın bugünkü durumu iş tanımının varsaydığından farklı. Tanım "Dynamics CRM okuyucu profilleri, satın alma geçmişi ✓
HAZIR" diyor. Oysa T-soft dönemindeki (2022 sonrası) site siparişleri CRM'e hiç gelmiyor: son 12 ayda B2C sipariş numarası
dolu sipariş 0, CRM'deki son B2C sipariş 2021-05-20 tarihli (crm-eticaret §1.5). Okur satın alma geçmişi yalnız T-soft'ta
duruyor (62.903 sipariş) ve kişisel veri içerdiği için bugün hiçbir modül onu okumuyor. CRM'deki kişi kayıtları (59.637)
yazar, çevirmen, okul/kurum yetkilisi ve okuru bir arada tutuyor. KVKK onayı, İYS onayı, iletişim izinleri ve "kitap ilgi
alanı" alanları var ama dolulukları ölçülmedi. Anket modülü neredeyse hiç kullanılmamış (14 anket modülü, 2 anket). Sitede
86 okur yorumu var ve hiçbiri cevaplanmamış (2026-09-25). Yani okurla ilişkinin verisi parçalı, izin durumu belirsiz,
etkileşim düşük.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Okur ilişkileri / topluluk sorumlusu | Pazarlama (CRM ekip üyeliği: 35 kişi). Ayrı bir topluluk rolü olduğuna dair kanıt yok — **varsayım** | Her gün | Masaüstü, telefon |
| E-bülten ve CRM pazarlama uzmanı | Pazarlama. CRM'de "Email Sms Kampanyası" (28) ve "Kampanya Gönderimi" (139; okunma, tıklama, SMS ulaşım durumu) kayıtları var (kanıt) | Haftalık | Masaüstü |
| Etkinlik sorumlusu (imza günü, okuma kulübü, fuar) | Pazarlama / Satış. CRM etkinlik kaydında sorumlu alanı 43–52 kişiye dağılıyor (kanıt, 2026-09-15) | Etkinlik başına | Telefon (sahada), masaüstü |
| Editör / yazar ilişkileri (okuma kulübüne yazar) | Editörya (M7 ile) | Aylık | Masaüstü |
| KVKK sorumlusu / hukuk | Hukuk ya da idari işler — birimi **varsayım** | Segment ve kampanya onayında | Masaüstü |
| Pazarlama müdürü | Yönetim | Haftalık | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

- **Topluluk sorumlusu.** Okurla temas sosyal medya, fuar ve imza günleri üzerinden yürüyor (**varsayım**). CRM kişi
  kaydında "Kayıt Tipi" seçenekleri 8151 SMS, Landing Page ve Fuar (kanıt). Bu, okur kayıtlarının SMS kısa numarası, açılış
  sayfası ve fuar standından toplandığını gösteriyor. "Kampanya ve İndirimlerden Haberdar Olmak İstiyorum" alanı var.
- **E-bülten uzmanı.** CRM'in pazarlama listesi (11 liste, 29 üye) ve e-posta/SMS kampanyası kayıtları çok az kullanılmış.
  Toplu gönderimin başka bir araçtan yapıldığı **varsayım** (sorulacak). "Müşteri Adayı" kaydı 63.332 ve UTM kaynağı,
  katılım kaynağı, KVKK bayrağı taşıyor. Açılış sayfası ya da SMS kampanyalarıyla toplanan okur adaylarının burada durduğu
  **varsayım**.
- **Etkinlik sorumlusu.** CRM etkinlik kaydı (57.013) çoğunlukla satış ziyareti. Etkinlik ↔ kişi bağı 9.012. İmza günü
  katılımcılarının burada olup olmadığı **ölçülecek**. Fuar raporu 3 kayıt.
- **Yorumlar.** Sitede 86 yorum, 67 ürün, 80'i 5 yıldız, hiçbiri cevaplanmamış (T-soft okuması 2026-09-25).
- **Sıkıntı.** Okurun ne aldığı CRM'de yok. İzin durumu kişi kişi dağınık alanlarda. Okura yazılacak her ileti için
  "izni var mı" sorusunun hızlı ve güvenilir bir cevabı yok.

## 4. İhtiyaçlar ve acı noktaları

**Topluluk sorumlusu**
1. Okur kitlesinin gerçek büyüklüğü ve kaynakları: kaç okur, nereden geldi, kaçı izinli.
2. İzinli kitle üzerinde ilgi alanı segmentlerinin büyüklüğü (kişi listesi değil, sayı).
3. Okuma kulübü ve etkinlik planı: hangi kitap, hangi yazar, hangi segment.
4. Cevapsız okur yorumları ve cevap taslağı.
5. Etkinlik sonrası katılım ve satış (etkinlik kaydındaki satılan kitap adedi).

**E-bülten uzmanı**
1. Gönderim öncesi izin denetimi: İYS onayı ve KVKK onayı olmayan kişiye gönderim olmaması.
2. Segment tanımını onaylatıp M24 bülten akışına vermek.

**KVKK sorumlusu**
1. Hangi okur verisinin hangi amaçla işlendiğinin kaydı.
2. İzin çelişkilerinin listesi (ör. "izin yok ama kampanya gönderilmiş").
3. Özel nitelikli veri çıkarımının engellenmesi (bölüm 8).

**Pazarlama müdürü**
1. Topluluk büyüklüğü, izinli kitle ve etkileşimin aylık eğilimi.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Topluluk sorumlusu olarak okur kitlemizin kaynağa ve izin durumuna göre dağılımını görmek istiyorum, çünkü kime
  ulaşabileceğimizi bilmeden program kuramam.
- Topluluk sorumlusu olarak "çocuk kitabı ilgisi olan, izinli okur" gibi bir segmentin büyüklüğünü görmek istiyorum, çünkü
  okuma kulübünü buna göre boyutlandıracağım.
- E-bülten uzmanı olarak bir segmenti onaya göndermek ve onaylanınca yalnız izinli kişileri gönderim listesine almak
  istiyorum, çünkü izinsiz ileti hem yasal hem itibar riski.
- Topluluk sorumlusu olarak cevapsız okur yorumlarını ve Zeki AI'ın cevap taslağını görmek istiyorum, çünkü yorum
  cevaplamak okura değer verildiğini gösterir.
- Etkinlik sorumlusu olarak geçmiş imza günlerinin katılım ve satılan kitap adedini görmek istiyorum, çünkü yeni etkinliğin
  şehir ve yazar seçimini buna göre yapacağım.
- KVKK sorumlusu olarak her segmentin tanımını, amacını ve kimin onayladığını görmek istiyorum, çünkü denetimde bunu
  göstermem gerekir.

**Ana ekranlar ve akış**
- *Okur kitlesi* (ilk açılış). Yalnız sayılar: toplam okur kaydı (kişi + aday), kaynak dağılımı, KVKK ve İYS onay oranı,
  e-posta/SMS izinli sayı, ilgi alanı dolu oranı, izin çelişkisi sayısı. Kişi adı yok.
- *Segmentler*. Kural tanımı (ilgi alanı, kaynak, kayıt tarihi, etkinlik katılımı), anlık büyüklük (toplam / izinli), amaç,
  onay durumu. Onaylanmamış segment dışa aktarılamaz.
- *Programlar*. Okuma kulübü, etkinlik, anket planları: tarih, kitap, yazar, segment, durum. Zeki AI duyuru taslağı.
- *Yorumlar*. Cevapsız yorumlar (ürün, puan, tarih) ve cevap taslağı. Cevap sitede elle girilir.
- Tık sayıları: bir segmentin büyüklüğünü görmek 2 tık; segmenti onaya göndermek 1 tık; bir yoruma taslak almak 2 tık.
- Telefonda kitle sayıları ve program takvimi okunur. Segment kurma masaüstünde yapılır.

**Zeki AI'a soracakları örnek sorular**
1. "Fuardan gelen okur kayıtlarının kaçında KVKK onayı var?"
2. "Son bir yılda kaç yeni okur kaydı geldi, kaynaklara göre dağılımı ne?"
3. "Çocuk kitabı ilgi alanı işaretli ve e-postaya izin veren kaç kişi var?"
4. "Geçen yılki imza günlerinde en çok kitap satılan beş etkinlik hangileri?"
5. "Kampanya gönderimi yapılmış ama İYS onayı olmayan kişi var mı?"
6. "Cevapsız yorumu olan kitaplar hangileri?"

**Otomasyon katmanı**
- K1: Kitle envanteri, izin sağlığı ve segment büyüklükleri her gece hesaplanır (yalnız sayı).
- K2: Segment tanımı, okuma kulübü planı, duyuru ve yorum cevabı Zeki AI'dan taslak olarak gelir; insan onaylar.
  Segmentin gönderime açılması KVKK sorumlusu onayına bağlıdır.
- K3: Sadakat programı tasarımı için Zeki AI kitle ve etkinlik verisini özetler, ekip karar verir.
- K4: İletinin gönderilmesi ve yorumun sitede cevaplanması insan tarafından yapılır. Bu modül ileti göndermez.
- İş tanımındaki "doğum günü tebriki", "seri tamamlama bildirimi" ve "kişisel öneri motoru" bu sürümde yapılamaz: satın
  alma geçmişi CRM'de yok, T-soft siparişi kişisel veri toplama katmanı olmadan okunmaz ve otomatik kişisel ileti açık rıza
  gerektirir.

**Bildirim / uyarı**
- KVKK sorumlusuna: onay bekleyen segment olduğunda ve izin çelişkisi sayısı arttığında e-posta.
- Topluluk sorumlusuna: yeni cevapsız yorum geldiğinde (haftalık özet) ve program tarihi yaklaştığında.
- Pazarlama müdürüne: aylık kitle raporu.

**Onay ve yetki**
- `sayfa:okur-toplulugu`: yalnız toplam sayılar ve programlar.
- `ozellik:okur.segment-yaz`: segment tanımı yazar (yalnız sayı görür).
- `ozellik:okur.segment-onay` (explicit, KVKK sorumlusu): segmenti amaç ve süreyle onaylar.
- `ozellik:okur.liste-disa-aktar` (explicit): onaylı segmentin izinli kişi listesini gönderim için indirir. Her indirme
  audit'e kişi sayısı, amaç ve segment kimliğiyle yazılır. İlk sürümde kapalı tutulması önerilir.
- `ozellik:okur.yorum-taslak`: yorum cevap taslağı üretir.
- Kişi adı, e-posta ve telefon hiçbir ekranda ve Zeki AI cevabında görünmez. Mevcut `ozellik:veri.disa-aktar` bu modülde
  yalnız sayı tablolarını kapsar.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Okur kişi kayıtları | CRM `ContactBase` (59.637; yazar, çevirmen, kurum yetkilisi ve okur bir arada) | Alanlar biliniyor: `new_kayittipi` (8151 SMS / Landing Page / Fuar), `new_ilgilidepartman` (B2C seçeneği), kişi rolü N:N `new_contact_new_kisiroluBase` | Okur olan kayıt sayısı **ölçülecek**; ayırt edici kural kurulacak |
| Okur adayları | CRM `LeadBase` (63.332): `obs_mainsourcename`, `obs_subsourcename`, `obs_utm_source`, `obs_donotkvkk`, `LeadSourceCode`, `CampaignId` | Alanlar biliniyor | Doluluk ve kaynak dağılımı **ölçülecek** |
| İzinler | CRM `ContactBase.new_kvkkonayi`, `new_iysonayi`, `obs_sendtoemailiys`, `obs_sendtosmsiys`, `DoNotEMail`, `DoNotBulkEMail`, `obs_donotsms`, `obs_SmsezinVerme`, `new_haberdarolmakistiyorum`, izin güncelleme tarihleri, `new_VeriDurumu` (Kontrol Edildi / Kontrol Edilecek / Silinebilir / Veri Kalitesi Yetersiz) | Alanlar biliniyor | Doluluk ve çelişkiler **ölçülecek**. İYS ile CRM'in eşit olup olmadığı bilinmiyor |
| İlgi alanı | CRM `new_SMKitap_ilgiAlani` (metin), `new_contact_new_kitapilgialanBase` (7.022 bağ; `new_kitapilgialanBase` 5 kategori), `new_contact_new_diziBase` (5), `new_contact_new_markaBase` (9) | Alanlar biliniyor | Kategori adları ve doluluk **ölçülecek**; din/inanç çağrışımlı kategori var mı bakılacak (bölüm 8) |
| Doğum tarihi | CRM `new_DogumTarihi`, `obs_DogumYili` | Alanlar var | Kullanımı açık rızaya bağlı; ilk sürümde kullanılmaz |
| Satın alma geçmişi | T-soft `order/get` (62.903 sipariş, kişisel veri) | Okunmuyor | **En büyük boşluk.** CRM'de 2021-05'ten sonra yok. Toplama katmanı + KVKK değerlendirmesi olmadan okunmaz |
| Etkinlik katılımı | CRM `new_etkinlikBase` (57.013; tip, yazar, kitap, şehir, katılımcı sayısı, satılan kitap adedi), `new_new_etkinlik_contactBase` (9.012) | Alanlar biliniyor | İmza günü ve okuma etkinliği ayrımı (tip 371 seçenek) **ölçülecek** |
| Kampanya gönderim ve etkileşim | CRM `obs_kampanyagonderimleriBase` (139: okundu, tıklandı, SMS durumu), `CampaignBase` (28), `ListBase` (11), `ListMemberBase` (29) | Az kullanılmış | Asıl gönderim aracı **sorulacak** |
| Anket | CRM `new_anketmoduluBase` (14), `new_anketBase` (2), `new_anketcevaplarBase` (1) | Neredeyse boş | Anket altyapısı sıfırdan |
| Site yorumları | T-soft `product/getComments` | `seo_geo/reviews.py` yalnız sayı ve yıldız dağılımı saklıyor, metin ve yorumcu saklamıyor | Cevap taslağı için yorum metni anlık okunur, saklanmaz |
| Web davranışı | GA4 | `zeki@` hesabının erişimi yok | Erişim istenecek (toplu metrik; kişi düzeyi yok) |
| Sosyal medya | Platform API'leri (M22) | Yok | M22'ye bırakılır |

## 7. Diğer modüllerle bağ

- Girdi alır: M38 (kişi kaydı veri sağlığı ve izin uyumu; ortak veri), M27 Fuar ve Etkinlik (etkinlik takvimi ve fuar
  kayıtları), M7 Yazar İlişkileri (okuma kulübüne yazar), M24 Katalog ve Bülten (gönderim kanalı), M34 (yorumlar, ürün
  sayfası), M22 Sosyal Medya.
- Çıktı verir: M24 (onaylı segment tanımı), M35 (okur segmentine özel kampanya), M15/M16 Yeni Kitap Pazarlaması (hedef
  kitle büyüklüğü), M39 (okur anketi sonuçları), DYK (topluluk göstergesi).
- Sınır: kurumsal müşteri (cari) ve CRM'in genel veri sağlığı M38'in işidir. M37 yalnız bireysel okuru ele alır. Okur
  şikâyet ve talebi M51'e aittir.

## 8. Kısıtlar

**KVKK (6698 sayılı Kanun) — bu modülün asıl kısıtı** (hukuk birimiyle teyit edilmeli)
- **Amaç ve hukuki dayanak.** Profil ve segment çıkarmak, pazarlama iletisi göndermek genellikle açık rıza gerektirir.
  Segment yalnız `new_kvkkonayi = 1` (ve ileti kanalı için ilgili izin) olan kişilerle kurulur. Rızası olmayan kişi yalnız
  toplam sayılarda görünür.
- **Ticari elektronik ileti.** 6563 sayılı Kanun ve ilgili yönetmelik gereği e-posta ve SMS gönderimi İYS'de kayıtlı onay
  ister. Gönderim listesi `new_iysonayi` ve kanal izinleriyle süzülür. Tacir/esnaf ayrımı `obs_iys_customertype`
  (AccountBase).
- **Özel nitelikli veri çıkarımı (md. 6).** TİMAŞ din, tasavvuf ve maneviyat kitapları yayımlıyor. Okurun aldığı ya da
  ilgilendiği kitaplardan dini inanç veya felsefi görüş çıkarmak özel nitelikli kişisel veri işlemek sayılabilir. İş
  tanımı kaynağındaki "ilgi alanı grubu (din, tarih, çocuk…)" örneği tam bu riski taşıyor. Öneri: din/inanç çağrışımlı
  kategoriler kişi düzeyinde segment ölçütü olarak kullanılmaz. Kullanılacaksa ayrı açık rıza ve ek güvenlik önlemi
  gerekir. Karar hukukundur.
- **Çocuklar.** Çocuk kitabı okurlarının çoğu reşit değil. Kayıt veliyse sorun yok, çocuğun kendisiyse veli rızası
  gerekir. `obs_DogumYili` ile 18 yaş altı kayıtlar segmentten çıkarılır.
- **Veri en aza indirme.** Ekranlar yalnız sayı gösterir. Kişi listesi yalnız onaylı segment ve açık yetkiyle, gönderim
  amacıyla ve kayıt altında çıkar. Zeki AI'a (yerel model) kişi adı, e-posta ya da telefon gönderilmez. Model yalnız
  toplamları ve yorum metnini görür, yorumcu adını görmez.
- **Yurt dışına aktarım.** Yerel model TİMAŞ'ın kiraladığı GPU sunucusunda çalışır (yurt içi olduğu **varsayım**, teyit
  edilmeli). Dış yapay zekâ hizmetlerine (GEO ölçümünde kullanılanlar dahil) okur verisi gönderilmez. E-posta gönderim
  hizmeti yurt dışındaysa md. 9 değerlendirmesi gerekir.
- **Otomatik karar (md. 11).** Okura aleyhine sonuç doğuran salt otomatik karar yok; segment ödül ya da iletişim içindir,
  ret içermez.
- **Saklama ve silme.** `new_VeriDurumu = Silinebilir` olan kayıtlar segmentlere girmez. Modül kendi tablolarında kişi
  verisi tutmaz, yalnız sayı ve segment tanımı tutar.
- **Aydınlatma metni.** Açılış sayfası ve fuar formlarındaki aydınlatma metninin "profil çıkarma" amacını kapsayıp
  kapsamadığı hukuka sorulacak.

**Diğer kısıtlar**
- CRM'e yazılmaz. İş tanımındaki "CRM profil zenginleştirme" ve "segment etiketi güncelleme" Web API yetkisi ve KVKK
  onayı gelene kadar yapılmaz. Segment üyeliği portalda da kişi düzeyinde saklanmaz, her gece kuraldan yeniden hesaplanır.
- T-soft'a yazma yasak. Yorum cevabı sitede elle girilir.
- Müşteride web taraması kapalı. Okur yorumu dış sitelerden toplanmaz. Bot korumalı sitelere (1000Kitap, Kitapyurdu,
  D&R, Ekşi) gidilmez.
- Ekranda teknoloji adı yok. Demo veri yok (örnek okur uydurulmaz), sayı tavanı yok.
- Zeki AI sohbeti bugün finans dışı soruyu reddediyor (`chat_scope.py`). Okur sorularının cevaplanması için kapsam
  genişletilmeli ve cevapta kişi verisi dönmemesi için ayrı bir süzgeç kurulmalı.

## 9. Kapsam önerisi

**İlk sürüm** (kişi verisi göstermeden değer)
- Okur kitlesi envanteri: kaynak, kayıt tipi, KVKK/İYS/kanal izni oranları, ilgi alanı doluluğu. Yalnız sayı.
- İzin sağlığı: çelişki listesi sayıları (izin yok ama gönderim var, İYS ve CRM uyumsuzluğu, silinebilir ama etkin).
  Düzeltme CRM'de yapılır.
- Segment tanımı ve onay akışı (sayı önizlemesi, amaç, süre, onaylayan). Dışa aktarma kapalı.
- Program takvimi: okuma kulübü, imza günü, anket planı. Zeki AI duyuru taslağı.
- Cevapsız yorumlar ve cevap taslağı.
- Geçmiş etkinliklerin katılım ve satılan kitap adedi özeti (CRM etkinlik).

**Sonraki sürüm**
- Onaylı segmentin izinli kişi listesinin gönderim için dışa aktarılması (explicit yetki, audit, hukuk onayından sonra).
- T-soft siparişlerinin toplama katmanı: kişi düzeyinde değil, ilgi alanı × dönem sayıları. Kişi düzeyi öneri ancak açık
  rıza ve hukuk kararıyla.
- Anket altyapısı (portalda form, sonuç yalnız toplu).
- CRM Web API yetkisi gelince izin düzeltmelerinin CRM'e yazılması.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/reviews.py` (yorum sayısı ve yıldız dağılımı; kişisel veri saklamama ilkesi).
- `backend/semantic_bridge/seo_geo/connections.py` (T-soft yalnız okuma).
- `backend/semantic_bridge/author_relations.py` (M7, okuma kulübü yazarı).
- `backend/semantic_bridge/bulletins.py` yalnız desen olarak (Kampüs sesli bülteni; okura gitmez).
- `alerts.py`, `reports.py`, `access.py`, `admin.py` audit.

## 10. Uzmanlara sorulacak sorular

1. (Pazarlama) Okura e-posta ve SMS gönderimi bugün hangi araçla yapılıyor? İzin (İYS) kaydı orada mı, CRM'de mi tutuluyor?
2. (Hukuk / KVKK) Açılış sayfası, SMS ve fuar formlarındaki aydınlatma ve rıza metni profil çıkarma ve kişiye özel öneri
   amacını kapsıyor mu? Din/inanç çağrışımlı ilgi alanlarının kullanımı hakkında görüş nedir?
3. (Pazarlama) CRM'deki kişi kayıtlarından hangileri okur? Ayırt eden bir alan ya da kural var mı?
4. (E-ticaret) Site üyelerinin sipariş verisinin portalda toplu (kişi adı olmadan) işlenmesine izin var mı?
5. (Etkinlik) İmza günü ve okuma etkinliği katılımcıları CRM'e kaydediliyor mu, hangi etkinlik tipiyle?

## 11. Başarı ölçütü

- İzin çelişkisi sayısının sıfıra inmesi. İzinsiz kişiye gönderim olayı: 0.
- İzinli okur kitlesinin aylık büyümesi (kaynak bazında).
- Onaylı segment sayısı ve onay süresi.
- Yorum cevaplama oranı ve süresi (bugün 86 yorumun 0'ı cevaplı).
- Program sonrası katılım ve satılan kitap adedi, CRM etkinlik kaydından.
- Kullanım: topluluk sorumlusu haftada en az 3 gün açıyor mu.

## 12. Uzman gözüyle en iyi sistem

*15 yıllık bir okur topluluğu ve CRM pazarlama müdürünün gözünden (uzman görüşü, TİMAŞ verisine dayanmaz).*

İyi yayınevleri ve kitapçılar okurla ilişkiyi üç temel üzerine kurar. (1) **İzin önce gelir:** müşteri veri platformları
"kim, hangi kanaldan, hangi amaçla izin verdi" kaydını merkezde tutar, her gönderim bu kayıttan süzülür. İzin merkezi
okurun kendi tercihini değiştirebildiği bir sayfadır. (2) **Davranış verisi toplu kullanılır:** kitap önerisi "bu kitabı
alanlar şunu da aldı" gibi toplu ilişkilerden gelir. Kişi düzeyi öneri açık rızayla ve okurun görebileceği şekilde yapılır.
(3) **Topluluk içerikle yaşar:** okuma kulübü, yazar buluşması, okur seçkisi ve yorum cevapları. Ölçüt gönderilen ileti
sayısı değil, geri dönen okur ve katılımdır.

TİMAŞ için mükemmel sistem: CRM, site ve etkinliklerden gelen okur kaydı izin durumuyla birleşir. Zeki AI toplu ilgi
eğilimlerini ("çocuk ve aile kitaplarına ilgi fuarda arttı") ve program önerilerini üretir. Kişi listesi yalnız onaylı
segmentten, amaçla ve kayıtla çıkar. Yorum ve etkinlik geri bildirimi editörlere döner. Din/inanç gibi hassas çıkarımlar
sistemin tasarımında baştan kapalıdır.

**Uzmanın bir günü (sistemle)**
- 09:00 Telefonda: "4 yeni cevapsız yorum, 1 segment onay bekliyor, izin çelişkisi 12 → 9."
- 09:20 Masaüstünde *Okur kitlesi*. Fuardan gelen kayıtların KVKK onay oranı düşük. Fuar formunu güncellemek için etkinlik
  ekibine not düşer.
- 10:00 *Segmentler*: "Çocuk ve aile ilgi alanı, e-posta izinli, son 2 yılda kayıt" segmentinin büyüklüğünü görür,
  amacını "Kasım okuma kulübü duyurusu" diye yazar, KVKK sorumlusuna onaya gönderir.
- 11:00 *Programlar*: Kasım okuma kulübü taslağı. Yazar ilişkilerinden yazarın uygunluğunu görür. Zeki AI duyuru metni
  hazırlar, düzenler.
- 14:00 *Yorumlar*: 4 yeni yorum için Zeki AI cevap taslakları. İkisini düzenleyip sitede yayınlar, "cevaplandı" işaretler.
- 16:00 Geçen ayın imza günlerinin özeti: katılım ve satılan kitap adedi şehir bazında. Bir sonraki etkinlik planına
  ekler.

**"Bunu görürsem hemen kullanırım"**
1. İzinli kitlenin gerçek büyüklüğü ve kaynağı. "Kime yazabiliriz" sorusunun tek sayılık cevabı.
2. Onaylı segment akışı. Hukukla yazışmayı bitirir.
3. Cevapsız yorumlar ve hazır cevap taslağı.

**"Bunu yaparsanız kullanmam"**
1. Ekranda okur adı ve telefonu listelemek. Hukuk ilk gün kapattırır.
2. Satın alma geçmişi olmadan "kişisel öneri" iddia etmek.
3. Din ya da inanç çağrışımlı segmentleri kişi düzeyinde önermek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kitle envanteri | Okur satışı Logo'da kişi düzeyinde yok (perakende faturası `TRCODE 7`; e-arşiv faturalarının okurla bağı **ölçülecek**) | `ContactBase` (`new_kayittipi`, `statecode`, `CreatedOn`), `LeadBase` (`obs_mainsourcename`, `LeadSourceCode`) | — | Sayım kurallı |
| İzin sağlığı | — | `new_kvkkonayi`, `new_iysonayi`, `DoNotEMail`, `DoNotBulkEMail`, `obs_donotsms`, `new_VeriDurumu`; gönderim `obs_kampanyagonderimleriBase.obs_kisiid` | — | Çelişki kuralları deterministik |
| Okur mu, değil mi | — | Kişi rolü N:N, eser katılımı (yazar/çevirmen), `ParentCustomerId` (kurum), `new_kayittipi` | Kurallı ayrım sonrası kalan belirsiz kayıtlar için yalnız rol/kaynak alanlarıyla (ad, e-posta olmadan) kapalı küme sınıflama: okur / kurum / katkıcı / belirsiz (tek token + olasılık) | Kural yetmediğinde; kişisel tanımlayıcı modele gitmez |
| Segment büyüklüğü | — | İlgi alanı N:N, izinler, kayıt tarihi, etkinlik katılımı | — | SQL sayımı |
| Segment tanımı önerisi | — | Toplu sayılar | Programa uygun segment kuralını ve gerekçesini önerir | Taslak; onay insanda |
| Hassas kategori koruması | — | `new_kitapilgialanBase` adları | Kategori adlarını "özel nitelikli çağrışım var / yok" diye işaretler (tek token + olasılık); son karar hukukta | Riskli kategoriyi baştan ayırmak için |
| Program duyurusu | — | Kitap (`new_ozet`, `new_kitapspotu`), yazar (M7) | Duyuru ve davet metni taslağı | Metin |
| Yorum cevabı | — | — (yorum T-soft'tan anlık, yorumcu adı olmadan) | Cevap taslağı; olumsuz yorumda tonu yumuşatır, söz vermez | Metin; saklanmaz |
| Etkinlik özeti | — | `new_etkinlikBase` (`new_katilimcisayisi`, `new_SatilanKitapAd`, `new_sehir`, `new_lgiliYazar`, `statuscode`) | Özet cümlesi | Rakam SQL'den |
| Doğal dil soru | — | Katalogdaki CRM tabloları | Soru → SQL; cevap yalnız sayı (kişi kolonları süzgeçle engellenir) | `chat_scope.py` + kişi verisi süzgeci gerekli |

Model `rt.llm_for("okur", priority)` ile çağrılır. Modele giden istemde kişi adı, e-posta, telefon, TC kimlik ve adres
bulunmaz; bu, kodda istem kurucusunda denetlenir (test ile).

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/okur.py`: depo, izin kuralları, segment kural derleyicisi (kural → SQL; yalnız COUNT döndürür).
- `backend/semantic_bridge/okur_sources.py`: CRM okumaları (`connector_from_file`). **Kişi kolonları hiçbir SELECT'te
  seçilmez**; kural derleyicisi yalnız izinli kolon listesini kullanır (beyaz liste). T-soft yorumları `seo_geo`
  istemcisiyle anlık okunur.
- `backend/semantic_bridge/okur_api.py`: `register(app, rt=..., can=..., audit=...)`.

**Tablolar** (`semantic_okur_` öneki; kişi verisi yok)
- `semantic_okur_inventory` (tenant_id, tarih, kaynak, kayit_tipi, toplam, kvkk_onayli, iys_onayli, eposta_izinli,
  sms_izinli, ilgi_alani_dolu, silinebilir, cocuk_olasi)
- `semantic_okur_consent_issues` (tenant_id, tarih, tur, sayi, ornek_sorgu_kimligi): yalnız sayı; düzeltme CRM'de.
- `semantic_okur_segments` (id, ad, kural_json, amac, sure_bitis, durum [taslak|onay_bekliyor|onaylandi|reddedildi|
  suresi_doldu], yazan, onaylayan, onay_notu, olusturma)
- `semantic_okur_segment_sizes` (segment_id, tarih, toplam, izinli)
- `semantic_okur_programs` (id, tur [okuma_kulubu|imza_gunu|anket|cevrimici], ad, tarih, sehir, kitap_id, yazar_id,
  segment_id, durum, duyuru_taslagi, sorumlu)
- `semantic_okur_review_status` (tsoft_comment_id, product_id, durum [cevapsiz|taslak|cevaplandi], taslak, yazan, tarih):
  yorum metni ve yorumcu saklanmaz; taslak metin saklanır.
- `semantic_okur_exports` (ikinci sürüm; id, segment_id, kisi_sayisi, amac, indiren, tarih): liste kendisi saklanmaz.

**Uçlar** (`/api/v1/okur/*`)
- `GET overview` · `GET consent-health` · `GET inventory?from=&to=`
- `GET segments` · `POST segments` · `PATCH segments/{id}` · `POST segments/{id}/preview` (yalnız sayı) ·
  `POST segments/{id}/submit` · `POST segments/{id}/decision`
- `GET programs` · `POST programs` · `PATCH programs/{id}` · `POST programs/{id}/draft` (Zeki AI duyurusu)
- `GET reviews?durum=` · `POST reviews/{id}/draft` · `POST reviews/{id}/mark`
- `GET events-summary?yil=` (CRM etkinlik özeti) · `POST run-due` (sistem jetonu)
- İkinci sürüm: `POST segments/{id}/export` (explicit yetki, audit).

**Ekranlar**: `src/canvas/okur/` → `AudienceScreen.tsx`, `SegmentsScreen.tsx`, `ProgramsScreen.tsx`,
`ReviewsScreen.tsx`. Rotalar `/timas/okur-toplulugu`, `/okur-toplulugu/segmentler`, `/okur-toplulugu/programlar`,
`/okur-toplulugu/yorumlar`. Menü: `navModel.ts` Pazarlama alanı, yeni bölüm "Okur ve müşteri". SEO'daki "Okur yorumları"
(`/seo-geo/yorumlar`) sayı ekranı olarak kalır, bu ekrandan ona bağlantı verilir. Kampüs: `ModulesMenu.tsx` `LIVE`
içine `M37: '/okur-toplulugu'`, `GROUP_HOME` içine `'Dijital & Topluluk'`.

**Yetki**: `sayfa:okur-toplulugu`, `sayfa:okur-segmentler`, `sayfa:okur-programlar`, `sayfa:okur-yorumlar`;
`ozellik:okur.segment-yaz`, `ozellik:okur.segment-onay` (**explicit**), `ozellik:okur.yorum-taslak`,
`ozellik:okur.program-yaz`, `ozellik:okur.liste-disa-aktar` (**explicit**, ikinci sürüm). Köprü kapsam testi, `okur`
uçlarının hiçbir cevabında kişi kolonu (`fullname`, `emailaddress1`, `mobilephone`, `address*`) olmadığını da denetler.

**Zamanlayıcı**: `scripts/server/timas-okur.timer`, her gece 03:40. Envanter, izin sağlığı, segment büyüklükleri,
süresi dolan segmentin kapanması, cevapsız yorum sayısı. İlk tur elle.

**Kabul testleri** (doğrudan CRM bağlantısıyla)
1. `SELECT new_kayittipi, COUNT(*) FROM dbo.ContactBase WHERE statecode = 0 GROUP BY new_kayittipi` = kitle ekranındaki
   kayıt tipi dağılımı.
2. `SELECT SUM(CASE WHEN new_kvkkonayi = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN new_iysonayi = 1 THEN 1 ELSE 0 END),
   SUM(CASE WHEN DoNotEMail = 0 THEN 1 ELSE 0 END) FROM dbo.ContactBase WHERE statecode = 0` = izin oranları.
3. Çelişki: `SELECT COUNT(DISTINCT g.obs_kisiid) FROM dbo.obs_kampanyagonderimleriBase g JOIN dbo.ContactBase c ON
   c.ContactId = g.obs_kisiid WHERE ISNULL(c.new_iysonayi, 0) = 0` = "izin yok ama gönderim var" sayısı.
4. Adaylar: `SELECT obs_mainsourcename, COUNT(*), SUM(CASE WHEN obs_donotkvkk = 1 THEN 1 ELSE 0 END) FROM dbo.LeadBase
   GROUP BY obs_mainsourcename` = aday kaynak tablosu.
5. Segment önizlemesi: onaylanan örnek segmentin kuralı elle yazılmış SQL ile sayılır (ör. ilgi alanı bağı
   `new_contact_new_kitapilgialanBase` ∩ `new_kvkkonayi = 1` ∩ `DoNotEMail = 0`) = `segments/{id}/preview` toplam ve izinli.
6. Etkinlik özeti: `SELECT YEAR(new_BalangTarihi), COUNT(*), SUM(new_katilimcisayisi), SUM(new_SatilanKitapAd) FROM
   dbo.new_etkinlikBase WHERE statuscode = 100000002 GROUP BY YEAR(new_BalangTarihi)` = etkinlik özeti.
7. Yorumlar: `semantic_seo_reviews` toplamı (2026-09-25: 86 yorum, 67 ürün) = yorum ekranı toplamı; cevapsız sayısı
   `semantic_okur_review_status` ile tutarlı.
8. Kişisel veri sızıntısı testi: bütün `okur` uçlarının JSON cevaplarında e-posta ve telefon kalıbı (regex) bulunmaz.

**Bağımlılık**: M38'in CRM veri sağlığı bulguları (çift kayıt, eksik alan) kişi kaydına dokunur. İki modül aynı CRM
okumasını paylaşabilir ama paralel kodlanabilir. Okur/katkıcı ayrım kuralı M38 ile ortak bir yardımcıda
(`crm_people_rules.py` önerisi) tutulmalı. Gönderim (ikinci sürüm) M24'e bağlı. Hukuk görüşü (bölüm 10 soru 2) ikinci
sürümden önce şart.

**Tahmini büyüklük**: M (1–2 gün) ilk sürüm (yalnız sayı, segment onayı, yorum). İkinci sürüm (dışa aktarma, sipariş
toplama) L.
