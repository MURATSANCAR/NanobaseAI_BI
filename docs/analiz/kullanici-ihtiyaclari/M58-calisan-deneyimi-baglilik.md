# M58 — Çalışan Deneyimi ve Bağlılık: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M58.txt` (ZEKİ_Moduller3.html'den),
`specs/DYK.txt`, `ZEKİ_Veri_Haritasi2.html` (İnsan Kaynakları kategorisi), `PROJECT-MEMORY.md` (Kampüs, kutlamalar,
sesli bülten, rehber), `docs/analiz/kampus-kisisel-ekran-crm-2026-09-15.md`, `docs/audits/crm-kullanici-bilgileri-2026-09-14.md`,
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/yetki-mekanizmasi-2026-09-27.md`,
`backend/semantic_bridge/greetings.py`, `people.py`, `bulletins.py`, `access.py`, `access_catalog.json`,
`backend/semantic_layer/store/schema.py`, `configs/semantic/knowledge/crm/table_descriptions.json` (CRM anket tabloları),
`src/canvas/nav/navModel.ts`, kullanıcı belleği (crm-systemuser-directory, no-demo-login, no-tech-names-on-screens,
no-silent-limits-rule). Ortak İK temeli: `M55-ise-alim-yetkinlik.md` §14.1. Sunucuya bağlanılmadı; ölçülmemiş her sayı «ölçülecek».

---

## 1. Modül ne işe yarar

İş tanımının iki kartı: **Bağlılık ölçüm otomasyonu (K1, tam otomatik)** — çeyreklik bağlılık anketi, anlık nabız
(pulse) anketi, işten ayrılma niyetinin erken sinyali, yeni çalışan oryantasyon memnuniyeti. **Çalışan deneyimi
iyileştirme (K3, Zeki analiz eder / İK karar verir)** — bağlılık düşüklüğünün kök neden analizi, birim bazında
iyileştirme önerileri, ZEKİ projesinin çalışan deneyimine etkisinin izlenmesi, çalışan öneri sistemi. Çıktılar:
Bağlılık Panosu (eNPS eğilimi, birim dağılımı), Analiz Raporu (kök nedenler, «dikkat gerektiren çalışanlar» risk
segmenti), Aksiyon Planı (birim önerileri, ZEKİ etkisi özeti).

TİMAŞ'ın bugünkü durumu: bağlılığı ölçen bir anket ya da öneri sistemi kaydı yok. CRM'de anket tabloları var ama
müşteri e-posta anketi ve kitap/set oylaması içindir, neredeyse boştur (`new_anketBase` 2 satır, `new_anketmoduluBase`
14, `new_anketcevaplarBase` 1). Portalın Kampüs ekranında çalışan deneyimine dokunan üç gerçek parça var: kişi rehberi,
kutlama/alkış duvarı (`semantic_greetings`) ve sesli bülten. Eylül ortasında Kampüs'teki «Şirket Nabzı + Günün modun»
kartı kullanıcı isteğiyle kaldırıldı (2026-09-18) — nabız sorusunun Kampüs'e geri gelmesi bu yüzden ayrı bir karardır.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| İK sorumlusu (anket tasarımı, sonuç, aksiyon takibi) | **Varsayım** (CRM'de İK birimi görünmüyor; M55 §2) | Anket dönemlerinde yoğun, arada haftalık | Masaüstü |
| Çalışan (anket yanıtlar, öneri verir) | AD'de 213 etkin kişi hesabı (2026-09-14); rehberde 130 kişi. Bilgisayar kullanmayan depo çalışanları AD/rehber dışında (sayısı **ölçülecek**) | Çeyrekte bir anket, ayda bir nabız, istediğinde öneri | Telefon ağırlıklı |
| Birim yöneticisi (kendi biriminin sonucu, aksiyon) | Editörya, Satış, Pazarlama, Grafik, Mali İşler, Üretim, Depo (CRM ekip/departman adları) | Çeyrekte bir | Masaüstü ve telefon |
| Genel müdür / üst yönetim (eğilim, program kararı) | DYK iş tanımı «organizasyon sağlık raporu» istiyor | Çeyrekte bir | Masaüstü |
| Öneriyi değerlendiren birim (öneri sahibi konuya göre) | Herhangi bir birim | Öneri geldikçe | Telefon |
| ZEKİ proje sorumlusu | Portal ekibi (varsayım) | Çeyrekte bir (ZEKİ etkisi) | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

Kanıt yok; hepsi **varsayım**.
- **İK:** varsa yılda bir kâğıt ya da çevrimiçi form anketi; sonuç Excel'de; birim kırılımı ya yok ya da anonimliği
  zedeleyecek kadar ince. Ayrılan çalışanla çıkış görüşmesi sözlü.
- **Çalışan:** önerisini yöneticisine sözlü ya da e-postayla iletir; dönüş alıp almadığı izlenmez. Anonim kanal yok.
- **Yönetici:** ekibinin nabzını birebirlerden bilir; birimler arası karşılaştırma yok.
- **Yönetim:** bağlılık ve ayrılma eğilimi bir panoda değil; ZEKİ projesinin çalışanlara etkisi ölçülmüyor ve **proje
  öncesi baz ölçüm yok** — ilk anket bu yüzden baz olur.
- **Tanıma:** Kampüs'teki kutlama/alkış duvarı gerçek veriyle çalışıyor (kim kimi kutladı, `semantic_greetings`).

## 4. İhtiyaçlar ve acı noktaları

**İK sorumlusu**
1. Gerçekten anonim, kısa, telefondan cevaplanan bir anket; yanıt oranını anlık görmek.
2. Açık uçlu yorumlardan temaları hızla çıkarmak (yüzlerce yorumu okumadan).
3. Birim sonuçlarını anonimliği bozmadan yöneticilere vermek.
4. Aksiyonları (kim, ne zaman, ne yaptı) izlemek ve bir sonraki ankette etkisini görmek.
5. Öneri kutusu: gelen öneriyi ilgili birime yönlendirmek ve «cevaplandı» durumunu izlemek.

**Çalışan**
1. Cevabımın kimliğime bağlanmayacağına güvenmek (güven yoksa yanıt yok ya da hep «iyi»).
2. İki dakikada bitecek anket.
3. Önerimin nereye gittiğini ve ne olduğunu görmek (adlı verdiysem).

**Birim yöneticisi**
1. Biriminin sonucu ve en güçlü/zayıf üç madde; ne yapabileceğine dair somut öneri.
2. Kendi birimi dışındaki kişilerin cevaplarına erişmemek; kendi ekibinin tek tek cevabına da erişmemek.

**Üst yönetim**
1. eNPS ve bağlılık eğilimi, birimler arası fark.
2. ZEKİ projesinin iş yükü ve memnuniyete etkisi (öncesi/sonrası).

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- İK sorumlusu olarak **şablondan çeyreklik anketi seçip tek tıkla başlatmak** istiyorum, çünkü her dönem soruları yeniden yazmak istemiyorum.
- İK sorumlusu olarak **açık uçlu yorumların tema özetini** görmek istiyorum, çünkü 150 yorumu tek tek okuyamıyorum.
- İK sorumlusu olarak **birim sonuçlarını, anonimliği bozacak kırılımlar gizli olarak** yöneticilere paylaşmak istiyorum, çünkü küçük birimde kimin ne dediği anlaşılır.
- İK sorumlusu olarak **aksiyon planını birim yöneticisiyle birlikte izlemek** istiyorum, çünkü anket sonrası hiçbir şey yapılmazsa bir sonraki ankete kimse katılmaz.
- Çalışan olarak **anketi telefondan iki dakikada** doldurmak istiyorum, çünkü masada değilim.
- Çalışan olarak **önerimi adlı ya da adsız** verebilmek ve durumunu izlemek istiyorum, çünkü bugün önerilerin nereye gittiğini bilmiyorum.
- Yeni çalışan olarak **ilk 30 ve 90 günümde nasıl hissettiğimi** söyleyebilmek istiyorum, çünkü oryantasyon eksikleri erken düzelsin.
- Birim yöneticisi olarak **birimimin sonuçlarını ve önerilen üç aksiyonu** görmek istiyorum, çünkü neyi değiştireceğimi bilmek istiyorum.
- Genel müdür olarak **eNPS eğilimini ve ZEKİ öncesi/sonrası iş yükü algısını** görmek istiyorum, çünkü yönetim kuruluna organizasyon sağlığını raporluyorum.

### Ana ekranlar ve akış

1. **Anket formu** (`/timas/ik/anket/:token`, telefon öncelikli): tek sütun, bir ekranda bir soru grubu, ilerleme
   çubuğu, en sonda isteğe bağlı açık uç. En üstte «Cevaplarınız adınızla saklanmaz» ve nasıl sağlandığının kısa
   açıklaması (aydınlatma bağlantısı).
2. **Bağlılık panosu** (`/timas/ik/baglilik`, İK/GM): eNPS ve bağlılık endeksi eğilimi, yanıt oranı, madde bazında
   sonuç, birim kırılımı (eşik kararına tabi), tema özeti.
3. **Birimim** (yönetici): kendi biriminin sonucu (eşik altındaysa «gösterilemiyor» notu), aksiyon planı.
4. **Anket yönetimi** (İK): şablonlar, dönem, hedef kitle (birimler), hatırlatmalar, yanıt oranı.
5. **Öneri kutusu** (`/timas/ik/oneriler`): herkes öneri yazar (adlı/adsız), İK yönlendirir, sorumlu cevaplar; adlı
   öneride sahibi durumu görür.
6. **Aksiyon planı:** madde, sorumlu, son tarih, durum; bir sonraki anketteki ilgili maddeyle yan yana.

İlk açılış: çalışan için Kampüs'te «açık anketiniz var» kartı (varsa) ve «Öneri ver»; İK için bağlılık panosu.
En sık üç işlem: (a) çalışanın anketi doldurması — Kampüs kartı ya da e-postadaki bağlantı → sorular → Gönder:
**2 tık + sorular**; (b) öneri verme — «Öneri ver» → metin, adlı/adsız → Gönder: **3 tık**; (c) İK'nın anket başlatması —
Anket yönetimi → şablon → hedef kitle → Başlat: **4 tık**.

### Zeki AI'ya soracakları örnek sorular

Bugünkü sohbet yalnız finans sorusu kabul ediyor; bu sorular İK ekranındaki yetkili soru kutusundan, yalnız toplu
(anonim) sonuçlar üzerinden cevaplanır.

- «Bu çeyrek eNPS kaç, geçen çeyreğe göre ne değişti?»
- «Yorumlarda en sık geçen üç şikâyet teması ne?»
- «Hangi birimde "yöneticimden geri bildirim alıyorum" maddesi en düşük?» (eşik kararına tabi)
- «ZEKİ ekranlarını kullanan birimlerde "iş yüküm yönetilebilir" maddesi değişti mi?»
- «Satış birimi için iyileştirme önerisi taslağı hazırla.»
- «Son üç ayda gelen önerilerden kaçı cevaplandı, ortalama kaç günde?»
- «Yeni çalışanların 90. gün anketinde oryantasyonla ilgili öne çıkan konu ne?»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| Çeyreklik anket ve nabız gönderimi, hatırlatma | K1 | Şablon ve takvim İK onaylı |
| Yeni çalışana 30./90. gün anketi | K1 | İK-0 `start_date`'ten |
| eNPS, endeks, yanıt oranı hesabı | K1 | Rakam SQL'den |
| Açık uç tema özeti | K3 | Zeki sınıflar/özetler; İK yorumlar |
| Kök neden ve birim iyileştirme önerisi | K3 | İK ve yönetim karar verir |
| Öneri kutusunun yönlendirilmesi | K2 | Zeki konu önerir, İK yönlendirir |
| Öneri cevap şablonu, teşekkür mesajı | K2 | |
| **İşten ayrılma niyeti erken sinyali** | İş tanımında K1 — **önerilen: K3 ve yalnız grup düzeyi** | Bkz. §8; kişi bazında tahmin ilk sürümde yok |

### Bildirim ve uyarı

| Kime | Ne zaman | Kanal |
|---|---|---|
| Çalışan | Anket açıldı; kapanmadan 2 gün önce (yalnız henüz cevaplamamışsa — bkz. §14 anonim jeton); adlı önerisine cevap geldi | Portal zili + e-posta (bağlantı; içerik yok). Bilgisayarsız çalışan: basılı tek kullanımlık kod (§14) |
| İK | Yanıt oranı düşük; anket kapandı ve özet hazır; öneri 7 gündür yönlendirilmedi | Portal zili |
| Birim yöneticisi | Birim sonucu paylaşıldı; aksiyon son tarihi yaklaştı; birimine öneri yönlendirildi | Portal zili + e-posta |
| GM | Çeyrek özeti hazır | Portal zili |

Süreler İK ayarıdır; varsayılan eşik konmaz.

### Onay ve yetki

| İşlem | Kim görür | Kim değiştirir | Kim onaylar | Anahtar önerisi |
|---|---|---|---|---|
| Anket yanıtlama | Herkes (hedef kitlede ise) | — | — | Oturumsuz jetonlu form ya da `sayfa:ik-anketlerim` (bütün çalışanlara) |
| Öneri verme ve kendi önerisini izleme | Herkes | Öneri sahibi | — | `sayfa:ik-oneriler` (bütün çalışanlara) |
| Öneri kutusu yönetimi | İK; yönlendirilen birim yalnız kendine gelenleri | İK | — | `ozellik:ik.oneri-yonet`, `ozellik:ik.oneri-cevapla` |
| Anket yönetimi | İK | İK | GM (yeni şablon ya da yeni soru türü) | `sayfa:ik-anket-yonetimi`, `ozellik:ik.anket-yonet` |
| Bağlılık panosu (şirket geneli) | İK, GM | — | — | `sayfa:ik-baglilik` |
| Birim sonucu | Birim yöneticisi yalnız kendi birimi (eşik kararına tabi) | — | İK paylaşır | `ozellik:ik.birim-sonuc` |
| Açık uç yorum metinleri | Yalnız İK, maskelenmiş hâlde | — | — | `ozellik:ik.anket-yorum` (sensitive) |
| Aksiyon planı | İK, ilgili yönetici, GM | İK, yönetici | GM | `ozellik:ik.aksiyon` |
| Dışa aktarma | İK | — | — | `ozellik:ik.disa-aktar` (sensitive; yalnız toplu veri) |

Bütün anahtarlar açıkça verilir; «Herkes» rolüne ve portal yöneticisine kendiliğinden gelmez (M55 §14.1). Portal
yöneticisi de dahil **hiç kimse** tek tek anket cevabını bir kişiye bağlayamaz (teknik tasarım, §14).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Anket ve nabız sonuçları | Portal anketi (yeni) | Yok. CRM anket tabloları müşteri/ürün oylaması için ve neredeyse boş | Tamamı yeni |
| Çalışan listesi ve birimi (hedef kitle, kırılım) | İK-0 (CRM ∩ AD + İK girişi) | Rehber 130 kişi; birim AD OU / CRM departmanı | Bilgisayarsız çalışanlar İK tarafından eklenmeli |
| İşe giriş tarihi (oryantasyon anketi) | İK-0 `start_date` (İK girer) | CRM/AD'de yok (CRM `CreatedOn` zayıf vekil) | Yok |
| İşten ayrılma | Bordro/SGK kaydı (**ölçülecek**); İK-0 `end_date` | CRM etkin ama AD hesabı kapalı 33 kişi (2026-09-14) — ayrılanlar CRM'de kapatılmıyor; AD hesabının kapanması tarih olarak güvenilir değil | Gerçek ayrılma tarihi kaynağı yok |
| Devamsızlık | Bordro/puantaj (**ölçülecek**) | Yok. M2'deki editör izin kaydı (`semantic_editorial_absences`) yalnız editörlerin müsaitliği içindir, devamsızlık verisi değildir ve bu amaçla kullanılmaz | İlk sürüm dışı; sağlık raporu nedeni özel nitelikli veridir |
| Öneri ve şikâyet kayıtları | Portal öneri kutusu (yeni) | Yok; CRM «Talep Yönetimi» BT destek masasıdır ve 2024-07'den beri kullanılmıyor | Tamamı yeni |
| Tanıma sinyali | `semantic_greetings` (Kampüs kutlamaları) | Var, çalışıyor | Yalnız toplu sayı (birim başına gönderilen/alınan) kullanılır |
| ZEKİ öncesi/sonrası iş yükü | Anket maddeleri (algı) + portal kayıtları (M2 görev yükü, `sl_query_log` sayıları) | Portal kayıtları 2026-09'dan beri; ZEKİ öncesi baz yok | Baz, ilk anketle **şimdi** alınmalı |
| Sektör eNPS benchmark | Dış | Müşteride web taraması kapalı | İlk sürüm dışı |
| Önceki dönem bağlılık | İlk anket | Yok | İlk dönem baz |

**Veri Haritası hakkında düzeltme:** Haritadaki «İnsan Kaynakları — 19 veri kaynağı» başlığının altındaki 19 karttan
**yalnız «Bağlılık Girdileri» (M58)** İK'ya aittir; öteki 18 kart M1, M2, M3, M5, M9, M11, M14, M19, M22, M36, M37, M38/M45,
M48, M49, M50, M59 modüllerinin girdileridir. M58'in ikinci kartı «Karşılaştırma Girdileri» «Pazar Araştırması» altında
M42'nin aynı başlıklı kartıyla birleşmiş: haritada M58'e «kanal bazlı kâr marjı, D2C/pazar yeri LTV, kanal büyüme
trendi» bağlı görünür; iş tanımındaki «sektör eNPS, önceki dönem bağlılık, ZEKİ öncesi/sonrası iş yükü» satırları
kaybolmuştur. İK modüllerinin gerçek girdileri 8 kart / 24 satırdır; hiçbirine bağlantı yoktur.

## 7. Diğer modüllerle bağ

| Yön | Modül | Ne akar |
|---|---|---|
| Girdi | İK-0 (M55 §14.1) | Çalışan, birim, işe giriş/çıkış tarihi |
| Girdi | M55 İşe alım | Yeni çalışan → oryantasyon anketi |
| Girdi | M56 Performans | Değerlendirme dönemi sonrası süreç memnuniyeti nabzı (anonim) |
| Girdi | M57 Eğitim | Gelişim fırsatı algısı; eğitim memnuniyeti |
| Girdi | Kampüs kutlamaları (`greetings.py`) | Birim bazında tanıma sayısı |
| Girdi | M50 ZEKİ Model Eğitim | Modül memnuniyeti (M50 iş tanımı «modül bazlı kullanıcı memnuniyet anket verileri» istiyor) — aynı anket altyapısıyla |
| Çıktı | DYK | Organizasyon sağlığı özeti (eNPS, yanıt oranı, ana temalar) |
| Çıktı | M50 | ZEKİ etkisi ve modül memnuniyeti |
| Çıktı | Kampüs | Anket kartı, öneri ver, sesli bültende anket sonucu ve aksiyon duyurusu (`bulletins.py`) |

## 8. Kısıtlar

**Genel proje kuralları:** CRM'e yazılmaz; T-soft'a yazma yasak; müşteride web taraması kapalı (sektör benchmark
taranmaz); ekranda teknoloji/model adı yok; demo anket sonucu ya da örnek yorum gösterilmez; sayı tavanı yok.

**KVKK ve iş hukuku (hukuk teyidi gerekir; genel mevzuat bilgisidir):**
- **Anonimlik gerçek olmalı.** «Anonim» denilen ankette cevap teknik olarak kişiye bağlanabiliyorsa bu hem aydınlatma
  yükümlülüğüne aykırı bir yanıltma olur hem de verinin kişisel veri sayılmasına yol açar. Tasarım (§14): cevap
  tablosunda kişi kimliği yok; «cevapladı mı» bilgisi ayrı tabloda ve cevapla bağlanamaz; cevap zamanı güne yuvarlanır;
  birim bilgisi yalnız eşik kararı çerçevesinde tutulur.
- **Küçük grup eşiği.** Birim kırılımı 1–4 kişilik birimde cevabı ele verir. Eşik bir gizlilik kuralıdır, sayı
  tavanı değildir; kullanıcı kuralı gereği **kendiliğinden konmaz**, karar olarak sorulur. Uygulanırsa ekranda açıkça
  yazar: «Bu birimde N'den az yanıt var; sonuç üst birimle birlikte gösteriliyor». Eşik kararı verilene kadar birim
  kırılımı kapalı başlar ve bu durum da ekranda yazar.
- **Açık uçlu yorumlar.** Kişi kendini ya da başkasını tanımlayan bilgi yazabilir (ad, sağlık, sendika, dinî görüş).
  Yorumlar yöneticiye verbatim gösterilmez; İK'ya maskelenmiş hâlde; yöneticiye yalnız tema ve sayı. Model temayı
  çıkarırken alıntı üretmez.
- **İşten ayrılma niyeti tespiti.** Kişi bazında «ayrılma riski yüksek» listesi, kişinin davranışından ya da
  cevaplarından çıkarılan bir **profilleme**dir; aleyhe sonuç doğurabilir (KVKK md. 11/1-g itiraz hakkı), anonim anket
  vaadiyle çelişir ve ölçülülük ilkesine (md. 4) uymakta zorlanır. **Öneri:** ilk sürümde yalnız grup düzeyinde sinyal
  (ör. «önümüzdeki bir yılda burada olacağımı düşünüyorum» maddesinin birim dağılımı, eşik kuralıyla). İş tanımındaki
  «risk segmenti: dikkat gerektiren çalışanlar» çıktısı ancak hukuk değerlendirmesi, çalışanlara açık aydınlatma ve
  yönetim kararıyla, K3 olarak ve yalnız İK müdürüne açık yapılabilir; doğrudan yöneticiye hiçbir zaman.
- **Devamsızlık.** Sağlık raporu nedeni özel nitelikli veridir (md. 6); bu modülde yalnız toplam gün türü (izin/rapor
  ayrımı olmadan) ve birim düzeyinde, eşik kuralıyla kullanılabilir; ilk sürümde yok.
- **Portal kayıtları.** `sl_query_log` ve `semantic_audit` gibi kişiye bağlı kayıtlar bağlılık ölçüsü olarak kişi
  bazında kullanılmaz; ZEKİ etkisi için yalnız birim toplamı (amaçla sınırlılık, md. 4).
- **Öneri kutusu.** Adsız öneride öneri sahibi hiçbir tabloda tutulmaz; adlı öneride sahibi yalnız İK ve cevaplayan
  birim görür. Öneri içinde başka bir çalışanla ilgili şikâyet varsa İK'ya yönlendirilir, birime değil.
- **Dayanak ve rıza.** Anonim ankette kişisel veri işlenmez (tasarım doğruysa). Adlı öneri ve oryantasyon anketi
  (kişiye bağlıysa) iş ilişkisi ve meşru menfaatle işlenir; aydınlatma yapılır. Katılım gönüllüdür; katılmamanın hiçbir
  kayıtta izi olmaz (yöneticiye «kim katılmadı» listesi verilmez).
- **Test ortamı.** Gerçek anket cevabı TİMAŞ ağı dışındaki test sunucusuna taşınmaz (M55 §8); test sunucusunda test
  hesabının açtığı anket ve kendi cevabıyla doğrulanır, sonra silinir.

## 9. Kapsam önerisi

**İlk sürüm:**
- Anonim anket altyapısı (jeton, gün yuvarlama, cevap/katılım ayrımı), şablonlar: çeyreklik bağlılık (eNPS + 10–12
  madde + açık uç), aylık nabız (2–3 soru), yeni çalışan 30./90. gün.
- Bağlılık panosu (eNPS, endeks, yanıt oranı, madde sonuçları, eğilim); birim kırılımı eşik kararına kadar kapalı.
- Açık uç tema özeti (Zeki AI, İK'ya).
- Öneri kutusu (adlı/adsız, yönlendirme, cevap, durum).
- Aksiyon planı (madde, sorumlu, son tarih, durum).
- Kampüs anket kartı ve «Öneri ver» (Kampüs'e nabız kartının geri gelmesi kullanıcı kararıyla).
- Bilgisayarsız çalışanlar için basılı tek kullanımlık kodlar.
- İlk anket ZEKİ projesi baz maddelerini içerir (iş yükü, araçların yardımı).

**Sonraki sürüm:**
- Birim sonuçlarının yöneticiye paylaşımı (eşik kararı sonrası) ve birim iyileştirme önerisi (K3).
- Kök neden analizi (madde korelasyonu, tema × birim), eğilim uyarısı.
- ZEKİ etkisi raporu (anket maddeleri + birim toplamı portal kullanımı + M2 iş yükü).
- Grup düzeyi ayrılma niyeti sinyali; ayrılma/devamsızlık verisi bordro kaynağı bulunursa.
- M50 modül memnuniyeti anketleri aynı altyapıdan.

**Mevcut kodda yeniden kullanılacaklar:**
- İK-0: `hr_core.py`, `hr_sources.py`, `hr_api.py` (M55 §14.1).
- Kampüs kartı ve bildirim zili: `src/canvas/kampus/KampusPage.tsx`, `GreetingsInbox.tsx`; kutlama verisi `greetings.py`.
- Sesli bülten (sonuç ve aksiyon duyurusu): `bulletins.py`, `BulletinCard.tsx`.
- Zamanlayıcı ve olay deseni: `alerts.py`; planlı rapor: `reports.py`; pano: `src/canvas/board/`.
- Yetki: `access.py`, `useCan`, `PageGate`.
- Model: `hr_llm()` (M55 §14.1).

## 10. Uzmanlara sorulacak sorular

1. Daha önce çalışan bağlılık/memnuniyet anketi yapıldı mı; sonuçlar ve soru seti var mı (baz ve süreklilik için)?
2. Birim kırılımında en az kaç yanıt olmazsa sonucun gösterilmeyeceğine TİMAŞ nasıl karar veriyor (eşik)?
3. Bilgisayar kullanmayan çalışan sayısı kaç, onlara nasıl ulaşılır (basılı kod, ortak cihaz, yönetici)?
4. İşten ayrılma ve devamsızlık verisi hangi sistemde (bordro, puantaj) ve portala toplu sayı olarak verilebilir mi?
5. İş tanımındaki «işten ayrılma niyeti yüksek çalışan tespiti» kişi bazında isteniyor mu; isteniyorsa hukuk ve
   çalışan temsilcileri görüşü alındı mı?

## 11. Başarı ölçütü

- **Yanıt oranı:** çeyreklik ankette hedef kitlenin yanıt oranı (ilk anket baz; sonraki anketlerde artış).
- **Aksiyon kapanışı:** anket sonrası açılan aksiyonların son tarihinde kapanma oranı.
- **Öneri döngüsü:** önerilerin cevaplanma oranı ve ortalama cevap süresi.
- **eNPS eğilimi:** çeyrekten çeyreğe değişim (hedef yönetimin kararı; sistem hedef koymaz).
- **Güven:** anket sonundaki «cevaplarımın anonim kaldığına güveniyorum» maddesi.
- **Gizlilik:** anket cevabını kişiye bağlayan herhangi bir veri yolu = 0 (şema ve erişim testi; §14).

---

## 12. Uzman gözüyle en iyi sistem

Bakış açısı: 15 yıllık İK uzmanı (çalışan deneyimi ve iç iletişim).

**Sektörde bu iş nasıl yapılıyor (genel pratik).** Yıllık uzun anket yerini yılda iki üç «bağlılık» anketi ve arada
kısa nabız sorularına bıraktı. İyi sistemler anonimliği teknik olarak garanti eder, küçük grup eşiği uygular,
yöneticiye kendi ekibinin sonucunu ve somut aksiyon önerisini verir, aksiyonları bir sonraki ankette görünür kılar
(«sizin dediğiniz → biz yaptık»). Açık uçlu yorumlarda metin analizi temaları çıkarır; yorumun kendisi yöneticiye
gitmez. Yeni çalışanın yolculuğu (işe başlangıç, 30., 90. gün) ayrı ölçülür. Kişi bazlı «ayrılma riski» tahmini bazı
büyük şirketlerde yapılsa da gizlilik ve güven maliyeti yüksek görülür; orta ölçekli şirketlerde grup düzeyinde kalınır.

**TİMAŞ için mükemmel sistem.** Çalışan telefonuna gelen bağlantıdan iki dakikada anketi doldurur ve ekranın başında
anonimliğin nasıl sağlandığını tek cümleyle okur. Depo çalışanı İK'nın dağıttığı basılı koddan aynı anketi açar.
İK anket kapanır kapanmaz eNPS'i, madde sonuçlarını ve Zeki AI'ın çıkardığı temaları görür; yöneticiler eşik kuralına
uygun birim sonuçlarını ve üç öneri alır. Aksiyonlar Kampüs'te ve sesli bültende duyurulur. Öneri kutusu yaşar:
her öneri bir haftada cevaplanır. ZEKİ projesinin etkisi, ilk anketteki baz maddelerle çeyrekten çeyreğe izlenir.

**Uzmanın bir iş günü (anketin kapandığı hafta).**
- **09:00** Bağlılık panosu: yanıt oranı %71 (geçen çeyrek %58), eNPS +12 (geçen çeyrek +4).
- **09:30** Tema özeti: «iş yükü — yayın takvimi sıkışması» ve «birimler arası iletişim» öne çıkıyor; «araçlar işimi
  kolaylaştırdı» maddesi Editörya'da yükselmiş.
- **11:00** Birim sonuçları: iki birim eşik altında, üst birimle birlikte gösteriliyor. Satış yöneticisine sonucu ve üç
  öneriyi paylaşır.
- **14:00** Öneri kutusu: 6 yeni öneri; Zeki AI konu önerir (yemek, ulaşım, yazılım), İK yönlendirir. Bir öneri bir
  çalışanla ilgili şikâyet — birime değil, İK'da kalır.
- **15:30** GM için çeyrek özeti: eğilim, üç tema, önerilen iki şirket geneli aksiyon.
- **17:00** Sesli bülten için «anket sonuçları ve yapacaklarımız» metni taslağı.

**«Bunu görürsem hemen kullanırım» dediği 3 özellik**
1. Telefondan iki dakikalık, gerçekten anonim anket ve anlık yanıt oranı.
2. Açık uçlu yorumların tema özeti (yorumları tek tek okumadan).
3. Aksiyon planının bir sonraki anketle yan yana görünmesi.

**«Bunu yaparsanız kullanmam» dediği 3 tuzak**
1. «Anonim» deyip kişiye bağlanabilen cevap: bir kez duyulursa hiçbir anket bir daha dürüst doldurulmaz.
2. Kişi bazında ayrılma riski listesini yöneticilere açmak.
3. Sonucu paylaşıp aksiyonsuz bırakmak ya da 60 soruluk anket: yanıt oranı ikinci dönemde çöker.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Hedef kitle ve birim | — | `SystemUserBase`, `BusinessUnitBase`, `TeamMembership` (İK-0 üzerinden) | Hiçbir şey | Kimlik ve birim kayıttan |
| eNPS, endeks, yanıt oranı | — | — | Hiçbir şey (SQL) | Rakam modelden gelmez |
| Açık uç tema özeti | — | — | Önce kural tabanlı maskeleme (ad, telefon, e-posta); sonra her yorumu kapalı tema listesine sınıflar (tek token + olasılık), tema başına alıntısız özet yazar | Sınıflandırma + özet |
| Öneri konusu | — | — | Kapalı seçim: konu/birim (tek token + olasılık); «kişiyle ilgili şikâyet» sınıfı İK'da tutulur | Yönlendirme önerisi (K2) |
| Birim iyileştirme önerisi | — | — | Birim sonucu (sayılar) + temalar → 3 somut aksiyon önerisi ve gerekçesi | Öneri gerekçesi (K3) |
| ZEKİ etkisi | — | — | Anket maddeleri ve birim toplamı kullanım sayılarını (SQL) cümleye çevirir | Yorum; rakam SQL'den |
| Öneri cevabı, teşekkür, bülten metni | — | — | Taslak | Taslak metin |
| İK soru kutusu | — | — | Soruyu tanımlı toplu sorguya eşler; kişi düzeyinde sorgu tanımı yok | Doğal dil soru; anonimlik korunur |

Bu modülde Logo kullanılmaz (bağlılığın finansal kayıtla ölçüsü yok; ayrılma/devamsızlık bordrodan gelirse ayrı karar).
Model çağrıları `rt.llm_for("ik")` üzerinden `hr_llm()` ile; kuyrukta yorum metni değil etiket saklanır (M55 §14.1);
`/api/v1/llm/jobs` kullanılmaz. Ekranda yalnız «Zeki AI».

## 14. Kodlama planı (kodlayıcıya devir)

**Ön koşul — İK-0 ortak temel** (tam tanım `M55-ise-alim-yetkinlik.md` §14.1): `hr_core.py`/`hr_sources.py`/`hr_api.py`;
tablolar `semantic_hr_units`, `semantic_hr_employees` (start_date/end_date), `semantic_hr_notices`, `semantic_hr_consents`,
`semantic_hr_retention`, `semantic_hr_access_log`, `semantic_hr_purge_runs`; `access.py`'de sayfalar için `explicit` ve
yönetici için `sensitive` desteği; menüde «İnsan Kaynakları» çalışma alanı; `hr_llm()`.

**Köprü dosyaları:** `backend/semantic_bridge/hr_engagement.py` (anket, jeton, sonuç hesabı, eşik kuralı, öneri kutusu,
aksiyon), `hr_engagement_api.py` (uçlar), `hr_engagement_text.py` (maskeleme, tema sınıflama istemleri).

**Anonimlik tasarımı (zorunlu)**
- Anket açılınca hedef kitledeki her kişi için rastgele jeton üretilir; kişiye yalnız bağlantı gider. Veritabanında
  `semantic_hr_survey_invites` (survey_id, employee_id, token_hash, responded boolean) tutulur.
- Cevap gelince: jeton doğrulanır, `responded = true` yapılır, cevap `semantic_hr_survey_responses`'a **employee_id ve
  token olmadan** yazılır; `submitted_day` güne yuvarlanır; satır kimliği rastgele; iki yazma ayrı işlemde ve cevap
  eklenmesi rastgele kısa gecikmeyle (sıra/zaman eşlemesini bozmak için). Davet satırında cevap kimliği yok.
- Birim: cevaba `unit_id` yalnız anket «birim kırılımlı» açıldıysa yazılır; eşik kararı yoksa yazılmaz.
- Basılı kod: İK `POST /surveys/{id}/paper-codes?n=` ile kişiye bağlı olmayan tek kullanımlık kodlar üretir
  (`semantic_hr_survey_paper_codes`: survey_id, code_hash, used). Formun adresi oturumsuz: `/timas/ik/anket/k/:kod`.
- Oturumsuz anket uçları yalnız jeton/kod ile çalışır; nginx'te `/timas/api/v1/hr/survey-public/` yolu `auth_request`
  dışında tutulur (portalın AD girişi kuralına istisna: yalnız bu iki uç, yalnız anket formu). Bu istisna kullanıcı kararıdır.
- Hatırlatma yalnız `responded = false` davetlilere gider; hatırlatma listesi hiçbir ekranda gösterilmez.

**Tablolar**

| Tablo | Ana kolonlar |
|---|---|
| `semantic_hr_survey_templates` | id, tenant_id, kind (`baglilik`/`nabiz`/`oryantasyon_30`/`oryantasyon_90`/`modul`), title, questions_json (soru, tür: `enps`/`likert5`/`secim`/`acik`), version, state, approved_by |
| `semantic_hr_surveys` | id, tenant_id, template_id, title, opens_at, closes_at, audience_json (birimler), unit_breakdown (bool), min_group (null = karar verilmedi), state (`taslak`/`acik`/`kapandi`) |
| `semantic_hr_survey_invites` | survey_id, employee_id, token_hash, responded, reminded_at |
| `semantic_hr_survey_paper_codes` | survey_id, code_hash, used |
| `semantic_hr_survey_responses` | id (rastgele), survey_id, submitted_day, unit_id (koşullu), answers_json |
| `semantic_hr_survey_comments` | id, survey_id, question_key, masked_text, theme, theme_prob (yorum ayrı tabloda; cevap satırıyla bağı yok) |
| `semantic_hr_survey_results` | survey_id, computed_at, scope (`sirket`/birim id), n, enps, index, items_json, themes_json, suppressed (bool, eşik altı) |
| `semantic_hr_suggestions` | id, tenant_id, created_day, author_employee_id (adsızda null), text, topic, topic_prob, routed_unit_id, state (`yeni`/`yonlendirildi`/`cevaplandi`/`kapandi`), answer, answered_by, answered_at |
| `semantic_hr_actions` | id, tenant_id, survey_id, unit_id, title, owner_employee_id, due_on, state, note, closed_at |

**Uçlar**
- Oturumsuz (jeton/kod): `GET /api/v1/hr/survey-public/{token}`, `POST /api/v1/hr/survey-public/{token}`
- `/api/v1/hr/engagement/*`: `GET /me/surveys` (açık anketlerim), `GET/POST /templates`, `PATCH /templates/{id}`,
  `GET/POST /surveys`, `PATCH /surveys/{id}`, `POST /surveys/{id}/open`, `POST /surveys/{id}/close`,
  `POST /surveys/{id}/paper-codes`, `GET /surveys/{id}/progress` (yalnız toplam yanıt sayısı ve oran),
  `GET /surveys/{id}/results?scope=`, `GET /surveys/{id}/themes`, `GET /trend`
- `GET/POST /suggestions`, `GET /suggestions/mine`, `POST /suggestions/{id}/route`, `POST /suggestions/{id}/answer`
- `GET/POST /actions`, `PATCH /actions/{id}`
- `POST /run-due` — SYSTEM (anket açma/kapama, hatırlatma, oryantasyon anketi tetikleme, sonuç hesabı, tema sınıflama)

**Ekranlar** `src/canvas/hr/engagement/`: `SurveyForm.tsx` (oturumsuz ve oturumlu aynı bileşen, telefon öncelikli),
`EngagementDashboard.tsx`, `MyUnitResults.tsx`, `SurveyAdmin.tsx`, `SuggestionsScreen.tsx`, `ActionsScreen.tsx`.
Rotalar: `/timas/ik/anket/:token`, `/timas/ik/anket/k/:kod`, `/timas/ik/baglilik`, `/timas/ik/baglilik/birimim`,
`/timas/ik/anket-yonetimi`, `/timas/ik/oneriler`, `/timas/ik/aksiyonlar`. Menü: «İnsan Kaynakları» çalışma alanı, bölüm
«Çalışan deneyimi» (Bağlılık panosu, Anket yönetimi, Öneriler, Aksiyonlar). Kampüs: «Açık anketiniz var» kartı (yalnız
açık anket varken) ve «Öneri ver» bağlantısı (Kampüs düzeni kullanıcı onayıyla).

**Yetki anahtarları** (hepsi `explicit`)
- `sayfa:ik-anketlerim` ve `sayfa:ik-oneriler` (bütün çalışanlara bağlanır), `sayfa:ik-baglilik`, `sayfa:ik-anket-yonetimi`
- `ozellik:ik.anket-yonet`, `ozellik:ik.birim-sonuc`, `ozellik:ik.anket-yorum` (sensitive), `ozellik:ik.oneri-yonet`,
  `ozellik:ik.oneri-cevapla`, `ozellik:ik.aksiyon`, `ozellik:ik.disa-aktar` (sensitive)
- `access.py` `RULES`: `("/api/v1/hr/survey-public/", OPEN_NO_SESSION)` — yeni tür; uç kendi jetonunu doğrular.

**Zamanlayıcı:** `timas-hr-engagement.timer` her 15 dakikada bir → `POST /api/v1/hr/engagement/run-due`. İlk kez elle
koşturulur (açılış, hatırlatma ve kapanış aynı çağrıda sınanır).

**Kabul testleri (test sunucusunda test hesabının açtığı anket ve kendi cevabıyla; gerçek çalışan cevabı yazılmaz)**
1. **Hedef kitle sayısı:** anket açılınca davet sayısı =
   `SELECT COUNT(*) FROM semantic_hr_employees WHERE tenant_id = :t AND status = 'aktif' AND unit_id IN (:hedef_birimler);`
   ve bu sayı İK-0'ın CRM ∩ AD kaynağıyla (`GET /api/v1/people` toplamı + İK'nın elle eklediği bilgisayarsız çalışanlar) tutarlı.
2. **Yanıt oranı:** `progress` cevabı =
   `SELECT COUNT(*) FILTER (WHERE responded) * 1.0 / COUNT(*) FROM semantic_hr_survey_invites WHERE survey_id = :s;`
   ve `SELECT COUNT(*) FROM semantic_hr_survey_responses WHERE survey_id = :s;` = davetlilerden gelen yanıt + kullanılan basılı kod sayısı.
3. **eNPS:** sonuç ekranındaki eNPS =
   `SELECT 100.0 * (COUNT(*) FILTER (WHERE (answers_json->>'enps')::int >= 9) - COUNT(*) FILTER (WHERE (answers_json->>'enps')::int <= 6)) / COUNT(*) FROM semantic_hr_survey_responses WHERE survey_id = :s;`
4. **Madde ortalaması:** her Likert maddesi = `SELECT AVG((answers_json->>:madde)::numeric) FROM semantic_hr_survey_responses WHERE survey_id = :s;`
5. **Anonimlik (şema):** `SELECT column_name FROM information_schema.columns WHERE table_name IN ('semantic_hr_survey_responses','semantic_hr_survey_comments');`
   sonucunda `employee_id`, `username`, `token` geçen kolon yok; `submitted_day` tipi `date`.
6. **Anonimlik (eşleme denemesi):** aynı saatte iki test cevabı gönderildikten sonra `semantic_hr_survey_invites` ile
   `semantic_hr_survey_responses` arasında birleştirilebilecek ortak kolon yok (id, zaman damgası, sıra) — test betiği bunu kanıtlar.
7. **Eşik:** `min_group` kararı verilmemiş ankette `results?scope=<birim>` → «birim kırılımı kapalı» cevabı; karar verilmiş
   ankette `n < min_group` birim için `suppressed = true` ve ekranda açık not.
8. **Tanıma sayısı (ZEKİ/kültür özeti, sonraki sürüm):** birim başına kutlama =
   `SELECT e.unit_id, COUNT(*) FROM semantic_greetings g JOIN semantic_hr_employees e ON lower(e.display_name) = g.to_key WHERE g.created_at >= :bas GROUP BY e.unit_id;`
   (eşleme anahtarı `greetings.py`'deki `to_key` kuralıyla doğrulanır).
9. **Yetki:** yönetici test hesabı başka birimin `results?scope=` çağrısında 403; `anket-yorum` anahtarı olmayan
   hesap `GET /surveys/{id}/themes?raw=1` çağrısında 403; portal yöneticisi `sensitive` anahtarı bağlanmadan yorum göremez.

**Bağımlılık:** İK-0 önce (hedef kitle ve birim). M55–M57'den bağımsız; paralel kodlanabilir. Oryantasyon anketi İK-0
`start_date` doluysa çalışır. Oturumsuz anket uçları için nginx değişikliği kullanıcı onayı ister.

**Tahmini büyüklük:** ilk sürüm **L** (3+ gün: anonimlik tasarımı ve testleri, oturumsuz form, sonuç hesabı, tema özeti,
öneri kutusu, aksiyonlar); birim paylaşımı ve kök neden sonraki sürüm **M**.
