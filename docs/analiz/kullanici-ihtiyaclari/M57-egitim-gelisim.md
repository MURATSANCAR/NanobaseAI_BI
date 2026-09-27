# M57 — Eğitim ve Gelişim Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M57.txt` (ZEKİ_Moduller3.html'den),
`ZEKİ_Veri_Haritasi2.html`, `PROJECT-MEMORY.md`, `docs/analiz/yetki-mekanizmasi-2026-09-27.md`,
`docs/audits/crm-kullanici-bilgileri-2026-09-14.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`backend/semantic_bridge/access_catalog.json`, `access.py`, `admin.py` (`semantic_audit`), `alerts.py`, `reports.py`,
`backend/semantic_layer/store/schema.py` (`sl_query_log`), `src/canvas/nav/navModel.ts`, `src/canvas/nav/navState.ts`,
`configs/semantic/knowledge/logo/knowledge/rules/logo-erp.md` (Kural 16), `configs/semantic/knowledge/logo/models/`,
kullanıcı belleği (crm-systemuser-directory, no-tech-names-on-screens, no-silent-limits-rule, run-it-before-it-runs-itself).
Ortak İK temeli: `M55-ise-alim-yetkinlik.md` §14.1. Sunucuya bağlanılmadı; ölçülmemiş her sayı «ölçülecek».

---

## 1. Modül ne işe yarar

İş tanımının iki kartı: **Eğitim ihtiyaç analizi (K2, Zeki önerir / İK onaylar)** — yetkinlik boşluğuna göre eğitim
öncelik sırası, ZEKİ kullanım yetkinliği gelişim planı, birim bazında eğitim takvimi önerisi, dış eğitim ile iç eğitimin
maliyet karşılaştırması. **Eğitim takibi (K1, tam otomatik)** — tamamlanma oranı izleme, sertifika ve yetkinlik kazanım
kaydı, eğitim geri bildirim anketi otomasyonu, zorunlu uyum eğitimlerinin son tarih uyarısı. Çıktılar: Eğitim Panosu
(birim × eğitim tamamlanma, yaklaşan eğitimler ve son tarihler), Yetkinlik Takip (kazanım haritası, ZEKİ kullanım düzeyi
dağılımı), Etki Raporu (eğitim ROI, eğitim öncesi/sonrası karşılaştırma).

TİMAŞ'ın bugünkü durumu: portalda ve CRM'de eğitim kaydı yok. Bu modülün TİMAŞ'a özgü ve hemen değerli yanı **ZEKİ
portalının kendisinin öğretilmesi**: portal 2026 Eylül'de hızla büyüdü (Editoryal M1–M8, Kitap tasarım, SEO, Finansal
denetim, Yönetim raporları), kullanıcıların hangi modülü kullanabildiği ölçülmüyor. Zorunlu eğitimlerin (iş sağlığı ve
güvenliği, varsayım: KVKK farkındalığı) son tarihleri bir sistemde izlenmiyor (varsayım).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| İK / eğitim sorumlusu (katalog, plan, takip) | **Varsayım** (CRM'de İK birimi görünmüyor; M55 §2) | Haftalık; dönem planında yoğun | Masaüstü |
| Birim yöneticisi (ihtiyaç bildirir, katılımı onaylar) | Editörya, Satış, Pazarlama, Grafik, Mali İşler, Üretim, Depo (CRM ekip/departman adları) | Ayda birkaç kez | Telefon (onay), masaüstü |
| Çalışan (eğitimlerim, sertifikalarım, geri bildirim) | Rehberdeki 130 kişi; bilgisayarsız depo çalışanları için ayrı kanal gerekir | Eğitim oldukça | Telefon ağırlıklı |
| İş sağlığı ve güvenliği sorumlusu (zorunlu eğitimler) | **Varsayım:** dış hizmet (OSGB) ya da iç görevli | Yılda birkaç kez | Masaüstü |
| ZEKİ portal sorumlusu / iç eğitmen | Portalı yöneten ekip ve modül «uzman kullanıcıları» (ör. editoryal ekranları en çok kullananlar) — **varsayım** | Yeni modül çıktıkça | Masaüstü |
| Mali İşler (eğitim bütçesi, gerçekleşen harcama) | CRM ekip adı Mali İşler (10 kişi) | Ayda bir | Masaüstü |
| Üst yönetim (bütçe, etki) | — | Çeyrekte bir | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

Kanıt yok; hepsi **varsayım**.
- **İK:** eğitim talepleri e-postayla gelir; katılımcı listesi ve imza föyü kâğıtta/Excel'de; sertifikalar e-posta ekinde
  ya da özlük klasöründe. Zorunlu İSG eğitiminin yenileme tarihi hizmet firmasının hatırlatmasına bağlı.
- **Birim yöneticisi:** ekibinin hangi eğitimi aldığını bilmez; dış eğitim onayı e-postayla.
- **Çalışan:** aldığı eğitimleri ve sertifika geçerlilik tarihini kendisi takip eder.
- **ZEKİ eğitimi:** yeni ekran çıkınca günlükte ve toplantıda anlatılıyor (varsayım); kimin öğrendiği bilinmiyor.
  Kampüs'te sesli bülten kanalı var (`bulletins.py`), eğitim duyurusu için kullanılabilir.
- **Mali İşler:** eğitim harcaması Logo muhasebesinde bir gider hesabına düşer (varsayım; hangi hesap olduğu **ölçülecek**).

## 4. İhtiyaçlar ve acı noktaları

**İK / eğitim sorumlusu**
1. Zorunlu eğitimlerin kimde ne zaman dolacağını önceden görmek (denetimde eksik çıkmasın).
2. Katılım ve tamamlanmayı kâğıtsız kaydetmek; sertifikayı kişinin kaydına eklemek.
3. Eğitim ihtiyacını M56 gelişim planlarından ve yetkinlik boşluğundan toplu görmek.
4. Geri bildirim anketinin kendiliğinden gitmesi ve sonuçların özetlenmesi.

**Birim yöneticisi**
1. Ekibinin eğitim durumunu görmek; katılım talebini telefondan onaylamak.
2. Yeni gelen çalışanın oryantasyon ve ZEKİ eğitim planının hazır gelmesi.

**Çalışan**
1. «Eğitimlerim»: atanmış, tamamlanmış, sertifika geçerlilik tarihleri.
2. Portalda kullandığı modüllerin kısa rehberine ekrandan ulaşmak.

**ZEKİ portal sorumlusu**
1. Hangi birimde hangi modülün hiç kullanılmadığını görmek (eğitimi oraya yöneltmek).
2. Modül rehberlerini tek yerde tutmak ve yeni sürümde güncellemek.

**Mali İşler / yönetim**
1. Eğitim harcamasının bütçeye göre durumu; dış eğitim ile iç eğitimin maliyeti.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- İK sorumlusu olarak **önümüzdeki 60 gün içinde süresi dolacak zorunlu eğitimleri** kişi kişi görmek istiyorum, çünkü İSG denetiminde eksik çıkmak istemiyorum.
- İK sorumlusu olarak **eğitim oturumunu açıp katılımcıları rehberden seçmek ve yoklamayı telefondan almak** istiyorum, çünkü imza föyünü sonra Excel'e geçiriyorum.
- İK sorumlusu olarak **eğitim bitince geri bildirim anketinin kendiliğinden gitmesini** ve sonucun özetlenmesini istiyorum, çünkü bugün anketi hiç yapmıyoruz.
- İK sorumlusu olarak **M56 gelişim planlarındaki eğitim ihtiyaçlarının öncelik listesini** görmek istiyorum, çünkü bütçeyi en çok ihtiyaç olana ayırmalıyım.
- Birim yöneticisi olarak **ekibimin eğitim ve sertifika durumunu** görmek istiyorum, çünkü kimin hangi eğitimi eksik bilmiyorum.
- Çalışan olarak **eğitimlerimi ve sertifikalarımın geçerlilik tarihini** tek yerde görmek istiyorum, çünkü belgeleri e-postada arıyorum.
- ZEKİ portal sorumlusu olarak **birim × modül kullanım haritasını** görmek istiyorum, çünkü hangi birime hangi modülün eğitimini vereceğimi bilmeliyim.
- Mali İşler olarak **eğitim harcamasının Logo'daki gerçekleşenle bütçeyi** karşılaştırmak istiyorum, çünkü eğitim bütçesi yıl ortasında bitiyor.

### Ana ekranlar ve akış

1. **Eğitimlerim** (`/timas/ik/egitimlerim`, herkes, yalnız kendisi): atanmış eğitimler (son tarih), tamamlananlar,
   sertifikalar (geçerlilik), modül rehberleri («kullandığınız ekranların kısa rehberi»).
2. **Eğitim panosu** (`/timas/ik/egitim`, İK): üstte sayaçlar — 60 gün içinde dolacak zorunlu eğitim, bu ay planlı oturum,
   tamamlanma oranı, bekleyen geri bildirim. Altında birim × eğitim tamamlanma tablosu.
3. **Katalog ve oturumlar:** eğitim kartı (tür: zorunlu/gelişim/ZEKİ; iç/dış; süre; geçerlilik süresi; maliyet) ve
   oturumlar (tarih, oda, eğitmen, katılımcılar, yoklama).
4. **İhtiyaç listesi:** M56 gelişim planlarından ve yönetici taleplerinden gelen ihtiyaçlar, Zeki AI'ın öncelik önerisi
   ve gerekçesi; İK onayı.
5. **ZEKİ kullanım haritası:** birim × modül (son 30 gün, kaç farklı kişi kullandı); kişi adı yok.
6. **Etki raporu** (sonraki sürüm): harcama (Logo), katılım, memnuniyet, öncesi/sonrası.

En sık üç işlem: (a) oturum yoklaması — oturum → katılımcıya dokun «katıldı»: **2 tık + kişi başına 1**; (b) dolacak
zorunlu eğitime oturum açma — panodaki uyarı → «Oturum aç» (kişiler hazır seçili) → tarih/oda → Kaydet: **4 tık**;
(c) çalışanın sertifika yüklemesi — Eğitimlerim → eğitim → «Belge ekle»: **3 tık**.

### Zeki AI'ya soracakları örnek sorular

Bugünkü sohbet yalnız finans sorusu kabul ediyor; bu sorular İK ekranındaki yetkili soru kutusundan cevaplanır.

- «Önümüzdeki iki ayda iş güvenliği eğitimi dolacak kaç kişi var, hangi birimlerde?»
- «Editörya'da redaksiyon ekranını son bir ayda hiç kullanmamış kişi sayısı kaç?» (kişi adı değil, sayı)
- «Gelişim planlarında en sık geçen eğitim ihtiyacı hangisi?»
- «Bu yıl eğitim giderimiz ne kadar, geçen yılın aynı dönemine göre?» (Logo, §13)
- «Kitap tasarım modülü için yeni başlayanlara 45 dakikalık bir eğitim planı taslağı yaz.»
- «Geçen ayki Excel eğitiminin geri bildirimlerinde öne çıkan şikâyet neydi?»
- «Satış birimi için önümüzdeki çeyrekte bir eğitim takvimi öner.»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| Zorunlu eğitim son tarih uyarısı | K1 | Gece işi; sertifika geçerlilik süresinden hesaplanır |
| Oturum sonrası geri bildirim anketi | K1 | Oturum kapanınca katılımcılara |
| Tamamlanma oranı ve ZEKİ kullanım haritası | K1 | Gece hesaplanır; rakam SQL'den |
| Eğitim ihtiyacı öncelik sırası | K2 | Zeki önerir ve gerekçe yazar; İK onaylar |
| Birim eğitim takvimi önerisi | K2 | |
| Modül rehberi taslağı, eğitim davet metni, değerlendirme soruları | K2 | İK/portal sorumlusu düzeltir |
| Eğitim bütçesi ve dış eğitim alımı | K2 (iş tanımı: «plan ve bütçe kararları İK onayında») | |
| Etki (ROI) yorumu | K3 | Rakam Logo ve kayıtlardan; yorum yönetimde |

### Bildirim ve uyarı

| Kime | Ne zaman | Kanal |
|---|---|---|
| Çalışan | Eğitime atandı; oturumdan 1 gün önce; sertifika geçerliliği bitmeden önce; geri bildirim anketi | Portal zili + e-posta (bilgisayarsız çalışan için yöneticisine) |
| Birim yöneticisi | Ekibinde süresi dolacak zorunlu eğitim; katılım onayı bekliyor | Portal zili + haftalık özet |
| İK | Zorunlu eğitim süresi doldu (kaçırıldı); oturum doluluk | Portal zili + günlük özet |
| ZEKİ portal sorumlusu | Yeni modül yayına alındı (rehber güncellenmeli) | Portal zili |

Uyarı öne alma günleri İK ayarıdır; varsayılan eşik konmaz.

### Onay ve yetki

| İşlem | Kim görür | Kim değiştirir | Kim onaylar | Anahtar önerisi |
|---|---|---|---|---|
| Eğitimlerim | Çalışanın kendisi | Çalışan (belge yükler) | İK (belgeyi doğrular) | `sayfa:ik-egitimlerim` (bütün çalışanlara, açıkça bağlanır) |
| Eğitim panosu, katalog, oturum | İK; yönetici kendi ekibini | İK | — | `sayfa:ik-egitim`, `ozellik:ik.egitim-yonet` |
| Katılım talebi | Yönetici, İK | Çalışan/yönetici talep eder | Yönetici, dış eğitimde İK | `ozellik:ik.egitim-onay` |
| Bütçe ve harcama | İK, Mali İşler, GM | İK | GM | `ozellik:ik.egitim-butce` |
| ZEKİ kullanım haritası (birim düzeyi) | İK, portal sorumlusu | — | — | `ozellik:ik.kullanim-haritasi` |
| Kişi bazında portal kullanımı | **Yalnız kişinin kendisi** | — | — | anahtar yok (kişinin kendi ekranı) |
| Dışa aktarma | İK | — | — | `ozellik:ik.disa-aktar` |

Bütün anahtarlar açıkça verilir; «Herkes» rolüne ve portal yöneticisine kendiliğinden gelmez (M55 §14.1).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Çalışan ve birim | İK-0 (`semantic_hr_employees`, `semantic_hr_units`); kaynak CRM ∩ AD | Rehber 130 kişi; birim AD OU / CRM departmanı | Bilgisayarsız çalışanlar AD'de yok; İK elle ekler |
| Yetkinlik boşluğu ve performans | M55, M56 | Kodlanmadı | İlk sürümde yönetici talebi ve İK girişi |
| Eğitim kataloğu ve içerik kütüphanesi | Kullanıcı girer | Yok | Yok |
| Eğitim bütçesi | M46 / kullanıcı girer | M46 kodlanmadı | Yok |
| Eğitim harcaması (gerçekleşen) | Logo muhasebe fişi `LG_411_01_EMFLINE` ⨝ `LG_411_EMUHACC` (Kural 16: 7'li gider hesapları, `SUM(DEBIT-CREDIT)`, `CANCELLED=0`) | Kural katalogda; eğitim giderinin hangi alt hesapta izlendiği **ölçülecek** | 2026 Logo kopyası 2026-08-17'de bitiyor |
| Zorunlu eğitim listesi ve periyodu | İSG hizmet sağlayıcısı / İK | Yok; işyeri tehlike sınıfı **bilinmiyor** | Yok |
| Sertifikalar | Çalışan/İK yükler | Yok | Yok |
| ZEKİ kullanımı | Portalın kendi kayıtları: `sl_query_log` (soru, `username`, `created_at`), `semantic_audit` (`actor`, `kind`, `at`: rapor/uyarı/pano/sözlük işlemleri), pano/rapor sahipliği (`semantic_reports`, pano `username`), `semantic_editorial_tasks` | Var, çalışıyor. Sayfa görüntüleme kaydı **yok** («Son açılanlar» yalnız kişinin kendi tercihinde, `nav:state`) | Modül bazında «kim açtı» ölçüsü için hafif bir sayfa ziyaret sayacı gerekir (§14) |
| Eğitim memnuniyeti ve katılım | Portal anketi | Yok | Yok |
| Eğitim öncesi/sonrası performans | M56 | Kodlanmadı | Sonraki sürüm |

**Veri Haritası hakkında düzeltme:** M57'nin iki girdi kartı haritada İK kategorisinde değil: «Eğitim Girdileri»
«Finans & Muhasebe» altında, «Etki Girdileri» «ERP / LOGO Muhasebe» altında. Haritadaki «İnsan Kaynakları — 19 kaynak»
başlığının 19 kartından yalnız biri (M58) İK'dır. İş tanımında M57 «Eğitim Girdileri» kaynağı `src:'M56'`, yani girdinin
çoğu M55–M56'dan beklenir; ikisi de kodlanmadı.

## 7. Diğer modüllerle bağ

| Yön | Modül | Ne akar |
|---|---|---|
| Girdi | İK-0 (M55 §14.1) | Çalışan, birim, yönetici |
| Girdi | M56 Performans | Gelişim planı maddeleri → eğitim ihtiyacı |
| Girdi | M55 Yetkinlik haritası | Birim yetkinlik boşluğu; yeni çalışanın oryantasyon planı |
| Girdi | M46 Bütçe | Eğitim bütçesi |
| Girdi | M50 ZEKİ Model Eğitim | Modül bazında kullanıcı memnuniyeti (iş tanımında M50 «modül bazlı kullanıcı memnuniyet anket verileri» istiyor) |
| Çıktı | M50 | ZEKİ kullanım haritası ve modül rehberi geri bildirimleri (hangi ekran anlaşılmıyor) |
| Çıktı | M58 Bağlılık | Eğitim memnuniyeti, gelişim fırsatı algısı |
| Çıktı | M49 Veri Güvenliği | KVKK farkındalık eğitimi tamamlanma oranı |
| Ortak | Oda rezervasyonu (`rooms.py`), sesli bülten (`bulletins.py`) | Eğitim odası; eğitim duyurusu |

## 8. Kısıtlar

**Genel proje kuralları:** CRM'e yazılmaz; T-soft'a yazma yasak; müşteride web taraması kapalı (dış eğitim kataloğu
taranmaz); ekranda teknoloji/model adı yok (modül rehberleri de «Zeki AI» der; rehber metninde altyapı adı geçmez);
demo eğitim/demo katılımcı yok; sayı tavanı yok.

**KVKK ve iş hukuku (hukuk teyidi gerekir; genel mevzuat bilgisidir):**
- **Dayanak.** Eğitim kaydı iş sözleşmesinin ifası (md. 5/2-c) ve zorunlu eğitimlerde hukuki yükümlülük (md. 5/2-ç)
  kapsamındadır; açık rıza gerekmez, aydınlatma gerekir.
- **Zorunlu İSG eğitimi.** 6331 sayılı İş Sağlığı ve Güvenliği Kanunu md. 17 ve Çalışanların İSG Eğitimlerinin Usul ve
  Esasları Hakkında Yönetmelik eğitim süresini ve yenileme periyodunu işyerinin tehlike sınıfına bağlar (az tehlikeli,
  tehlikeli, çok tehlikeli için farklı periyotlar). TİMAŞ ofisi ile depo/üretim alanının tehlike sınıfı **bilinmiyor**;
  periyot sistemde sabit kodlanmaz, eğitim kartında «geçerlilik süresi» olarak İK/İSG sorumlusu girer.
- **Portal kullanım kayıtları.** `sl_query_log` ve `semantic_audit` kişiye bağlı kayıtlardır ve başka amaçla (hata
  inceleme, değişiklik kaydı) toplanmıştır. Eğitim ihtiyacı için kullanımı **amaçla sınırlılık** (md. 4) gereği:
  (a) İK'ya ve yöneticiye yalnız **birim düzeyinde toplam** gösterilir; (b) kişi bazındaki görünüm yalnız kişinin
  kendisine açıktır («kullanmadığınız modüller, önerilen rehber»); (c) performans değerlendirmesine (M56) **aktarılmaz**;
  (d) çalışan aydınlatma metninde yazılır. Soru metinleri hiçbir İK ekranına taşınmaz, yalnız sayılar.
- **Küçük grup.** Birim düzeyindeki toplamlar 1–2 kişilik birimde kişiyi ele verir. Bir gizlilik eşiği gerekir; kullanıcı
  kuralı gereği sayı eşiği kendiliğinden konmaz — karar olarak sorulur ve uygulanırsa ekranda açıkça yazılır
  («bu birimde N'den az kişi var, ayrı gösterilmiyor»).
- **Sertifika belgeleri.** Kimlik numarası içerebilir; yükleme ekranı uyarır, belge yalnız kişi ve İK'ya açıktır,
  saklama süresi İK-0 `semantic_hr_retention`'dan.
- **Test ortamı.** Gerçek katılım ve sertifika verisi TİMAŞ ağı dışındaki test sunucusuna taşınmaz (M55 §8).

## 9. Kapsam önerisi

**İlk sürüm (en çok değer, en az bağımlılık — M55/M56 beklemeden çalışır):**
- Eğitim kataloğu (zorunlu / gelişim / ZEKİ; iç / dış; geçerlilik süresi; maliyet).
- Oturum, katılımcı, yoklama (telefondan), tamamlanma, sertifika yükleme ve doğrulama.
- Zorunlu eğitim son tarih uyarıları (K1) ve geri bildirim anketi (K1, 3–5 soru + açık uç).
- Eğitimlerim (çalışan), Eğitim panosu (İK), ekibimin eğitimi (yönetici).
- ZEKİ kullanım haritası (birim × modül, sayılar) + modül rehberleri kütüphanesi (Zeki AI taslaklar, portal sorumlusu onaylar);
  çalışana «kullanmadığınız modüller» önerisi.
- Eğitim gideri: Logo'dan gerçekleşen (hesap listesi ölçüldükten sonra), bütçe elle.

**Sonraki sürüm:**
- M56 gelişim planlarından ve M55 yetkinlik boşluğundan otomatik ihtiyaç listesi, öncelik önerisi (K2).
- Birim eğitim takvimi önerisi; iç/dış maliyet karşılaştırması.
- Etki raporu: öncesi/sonrası (M56), memnuniyet, ROI yorumu (K3).
- Bilgisayarsız çalışanlar için kiosk ya da yönetici üzerinden yoklama.

**Mevcut kodda yeniden kullanılacaklar:**
- İK-0: `hr_core.py`, `hr_sources.py`, `hr_api.py` (M55 §14.1).
- Uyarı zamanlayıcı deseni ve olay kaydı: `backend/semantic_bridge/alerts.py` (`semantic_alert_rules`/`events`).
- Planlı rapor/e-posta: `reports.py`; pano kartı: `src/canvas/board/`.
- Oda: `rooms.py`, `src/canvas/rooms/`. Duyuru: `bulletins.py` (Kampüs sesli bülten).
- Dosya saklama/indirme deseni: `result_files.py`; Word çıktısı: `contracts_docs.py` (katılım belgesi).
- Kullanım kayıtları: `sl_query_log` (`backend/semantic_layer/store/schema.py`), `semantic_audit` (`admin.py`).
- Model: `hr_llm()` (M55 §14.1).

## 10. Uzmanlara sorulacak sorular

1. Zorunlu eğitimler hangileri (İSG, yangın, ilk yardım, KVKK…), İSG hizmetini kim veriyor, ofis ve depo hangi tehlike sınıfında?
2. Eğitim bütçesi var mı; harcama Logo'da hangi gider hesabına işleniyor?
3. Katılım ve sertifika kayıtları bugün nerede (hizmet firmasında, özlük klasöründe)? Geçmiş kayıt aktarılacak mı?
4. İç eğitimleri (editoryal yazım kuralları, portal kullanımı) kim veriyor; ZEKİ eğitimi için hangi roller öncelikli?
5. Portal kullanım sayılarının birim düzeyinde eğitim ihtiyacı için gösterilmesine yönetim ve hukuk onay veriyor mu?

## 11. Başarı ölçütü

- **Zorunlu eğitim uyumu:** süresi geçmiş zorunlu eğitimi olan çalışan sayısı = 0 (panodan, doğrudan SQL ile karşılaştırılır).
- **Kâğıtsız kayıt:** oturumların yoklamasının portalda alınma oranı (%100 hedef).
- **Geri bildirim:** anket yanıt oranı, ortalama memnuniyet.
- **ZEKİ benimseme:** her modül için son 30 günde en az bir kez kullanan kişi sayısının birim başına değişimi (eğitim öncesi/sonrası).
- **Bütçe:** eğitim gideri gerçekleşen / bütçe; dış eğitim oranı.
- **Süre:** İK'nın bir oturumu planlayıp kapatma süresi (önce/sonra beyan).

---

## 12. Uzman gözüyle en iyi sistem

Bakış açısı: 15 yıllık İK uzmanı (eğitim ve organizasyonel gelişim).

**Sektörde bu iş nasıl yapılıyor (genel pratik).** Orta ölçekli şirketler bir öğrenme yönetim sistemi (LMS) ya da İK
paketinin eğitim modülünü kullanır: katalog, atama, e-öğrenme, yoklama, sertifika geçerliliği, zorunlu eğitim uyum
raporu. İyi uygulamada eğitim ihtiyacı üç yerden gelir: zorunluluk (mevzuat), performans görüşmesindeki gelişim planı,
şirketin stratejik projesi (burada ZEKİ). Yeni yazılım yayılımında en iyi sonuç, «uzman kullanıcı» (her birimde bir
kişi) + kısa, göreve dayalı rehberler + ekranın içinden erişilen yardım ile alınır; uzun sınıf eğitimi unutulur.
Etki ölçümü genellikle katılım ve memnuniyette kalır; öncesi/sonrası iş ölçüsü nadir ve zordur.

**TİMAŞ için mükemmel sistem.** Zorunlu eğitimler hiç kaçmaz: süre dolmadan 60 gün önce kişi, yönetici ve İK uyarılır,
oturum tek tıkla açılır. Her portal ekranının sağ üstünde «Bu ekran nasıl kullanılır» bağlantısı, o modülün Zeki AI ile
taslaklanmış ve portal sorumlusunca onaylanmış kısa rehberine açılır; rehberi okuyan kişi «işime yaradı / yaramadı»
der. İK birim × modül haritasında Satış'ın panoları hiç kullanmadığını görür ve 30 dakikalık bir oturum açar. Eğitim
gideri Logo'dan kendiliğinden gelir, bütçeyle yan yana durur.

**Uzmanın bir iş günü.**
- **09:00** Eğitim panosu: 60 gün içinde 14 kişinin İSG eğitimi doluyor (Depo 9, Üretim 5). «Oturum aç» → kişiler
  seçili gelir; tarih ve oda seçilir, İSG firmasına davet metni Zeki AI taslağından.
- **10:00** ZEKİ kullanım haritası: yeni «Sözleşmeler» ekranını Editörya'da 3 kişi kullanmış, Mali İşler'de 0. Portal
  sorumlusuyla Mali İşler'e 30 dakikalık oturum planlanır; rehber taslağı hazır.
- **11:00** Dün biten Excel eğitiminin geri bildirim özeti: «örnekler muhasebe dışı» teması öne çıkmış.
- **14:00** Oturum: yoklama telefondan; iki kişi gelmedi, yeni oturuma atandı.
- **15:30** Bir çalışan yabancı dil sertifikası yükledi; İK doğrular, kayıt yetkinlik haritasına işlenir.
- **17:00** Gün sonu: Logo'dan eğitim gideri bu yıl bütçenin %68'i.

**«Bunu görürsem hemen kullanırım» dediği 3 özellik**
1. Zorunlu eğitim son tarih uyarısı ve dolacak kişiler için tek tıkla oturum.
2. Telefondan yoklama ve kendiliğinden giden geri bildirim anketi.
3. Birim × modül ZEKİ kullanım haritası ve ekranın içinden açılan kısa rehberler.

**«Bunu yaparsanız kullanmam» dediği 3 tuzak**
1. Kişi kişi «kim portalı kaç kez kullandı» listesini yöneticilere açmak: çalışanlar bunu gözetleme olarak görür, güven biter.
2. Her eğitim için uzun zorunlu form ve çok adımlı onay zinciri.
3. Uydurma «eğitim ROI'si» rakamı: gerçekleşen harcama ve katılım dışında ölçülemeyen etkiyi yüzdeyle göstermek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Katılımcı seçimi, birim | — | `SystemUserBase`, `BusinessUnitBase`, `TeamMembership` (İK-0 üzerinden) | Hiçbir şey | Kimlik kayıttan |
| Eğitim gideri (gerçekleşen) | `LG_411_01_EMFLINE` ⨝ `LG_411_EMUHACC` (hesap adı), isteğe bağlı `LG_411_EMCENTER` (masraf merkezi = birim); Kural 16 ölçüsü `SUM(DEBIT-CREDIT)`, `CANCELLED=0`, İK/Mali İşler'in seçtiği eğitim hesapları | — | Hiçbir şey (rakam SQL'den) | Kayıt sistemi Logo |
| Zorunlu eğitim son tarihi | — | — | Hiçbir şey (tarih hesabı) | Deterministik |
| ZEKİ kullanım haritası | — | — | Hiçbir şey (sayım: `sl_query_log`, `semantic_audit`, sayfa ziyaret sayacı) | Rakam SQL'den |
| Eğitim ihtiyacı öncelik önerisi | — | — | İhtiyaç listesini (gelişim planı maddeleri, talepler) kataloğa eşler — aday eğitim listesi içinden kapalı seçim (tek token + olasılık); gerekçe cümlesi yazar | Eşleştirme + öneri gerekçesi |
| Geri bildirim açık uç özeti | — | — | Yorumları kapalı tema listesine sınıflar (tek token + olasılık) ve tema başına kısa özet yazar; kimliği ele verecek ayrıntıyı atar | Sınıflandırma + özet |
| Modül rehberi taslağı | — | — | Ekranın menü tanımı (`navModel.ts` `hint`), ekran metinleri ve günlükteki modül açıklamasından adım adım rehber taslağı; teknoloji adı yazmaz | Taslak metin; portal sorumlusu onaylar |
| Davet, hatırlatma metni; değerlendirme soruları | — | — | Taslak | Taslak metin |
| İK soru kutusu | — | — | Soruyu tanımlı İK sorgusuna eşler, sayı SQL'den | Rakam modelden gelmez |

Model çağrıları `rt.llm_for("ik")` üzerinden `hr_llm()` ile (kuyrukta içerik yerine etiket; M55 §14.1); `/api/v1/llm/jobs`
kullanılmaz. Ekranda yalnız «Zeki AI».

## 14. Kodlama planı (kodlayıcıya devir)

**Ön koşul — İK-0 ortak temel** (tam tanım `M55-ise-alim-yetkinlik.md` §14.1): `hr_core.py`/`hr_sources.py`/`hr_api.py`;
tablolar `semantic_hr_units`, `semantic_hr_employees`, `semantic_hr_notices`, `semantic_hr_consents`, `semantic_hr_retention`,
`semantic_hr_access_log`, `semantic_hr_purge_runs`; `access.py`'de sayfalar için `explicit` ve yönetici için `sensitive`
desteği; menüde «İnsan Kaynakları» çalışma alanı; `hr_llm()`.

**Köprü dosyaları:** `backend/semantic_bridge/hr_learning.py` (katalog, oturum, katılım, sertifika, son tarih hesabı),
`hr_learning_api.py` (uçlar), `hr_learning_sources.py` (Logo eğitim gideri; portal kullanım sayımı — `sl_query_log`,
`semantic_audit`, `semantic_hr_page_visits`).

**Tablolar**

| Tablo | Ana kolonlar |
|---|---|
| `semantic_hr_courses` | id, tenant_id, title, kind (`zorunlu`/`gelisim`/`zeki`), delivery (`ic`/`dis`/`cevrimici`), duration_hours, validity_days (boş = süresiz), cost_per_person, provider, module_route (ZEKİ eğitiminde ilgili rota), active |
| `semantic_hr_sessions` | id, course_id, starts_at, ends_at, room_booking_id, trainer, capacity (bilgi; kayıt kesmez), state (`planli`/`yapildi`/`iptal`) |
| `semantic_hr_enrollments` | id, session_id, employee_id, requested_by, approved_by, approved_at, attendance (`katildi`/`gelmedi`/null), completed_at |
| `semantic_hr_certificates` | id, employee_id, course_id, issued_on, expires_on, file_blob, file_name, verified_by, verified_at |
| `semantic_hr_training_needs` | id, employee_id, source (`gelisim_plani`/`yonetici`/`calisan`/`yetkinlik`), text, suggested_course_id, suggestion_reason, priority, state, decided_by |
| `semantic_hr_feedback` | id, session_id, submitted_at, answers_json, comment (anonim: employee_id **tutulmaz**; tek yanıt garantisi için ayrı `semantic_hr_feedback_tokens` (session_id, employee_id, used_at)) |
| `semantic_hr_guides` | id, module_route, title, body_md, version, state (`taslak`/`yayinda`), approved_by, updated_at |
| `semantic_hr_guide_votes` | guide_id, username, useful (bool), at |
| `semantic_hr_page_visits` | tenant_id, day, route_prefix (menü öğesi), username, count — günlük özet; ham tıklama tutulmaz |

**Sayfa ziyaret sayacı (yeni, küçük):** ön yüzde menü öğesi değişiminde (`navState.ts` yakınında) `POST /api/v1/hr/visit`
(`{route}`), köprü `(tenant, gün, menü öğesi, hesap)` satırını artırır. Saklama süresi `semantic_hr_retention`'daki
`kullanim` sınıfından; gece imhası siler. Aydınlatmada yazılır.

**Uçlar (`/api/v1/hr/learning/*`)**
- `GET /me` (Eğitimlerim), `POST /me/certificates` (yükleme)
- `GET/POST /courses`, `PATCH /courses/{id}`
- `GET/POST /sessions`, `PATCH /sessions/{id}`, `POST /sessions/{id}/enroll`, `POST /enrollments/{id}/approve`,
  `POST /sessions/{id}/attendance`, `POST /sessions/{id}/close` (anket jetonlarını üretir)
- `GET /dashboard` (sayaçlar, birim × eğitim), `GET /expiring?days=` (dolacak zorunlu eğitimler; gün İK ayarı)
- `GET/POST /needs`, `POST /needs/suggest` (Zeki AI öncelik önerisi), `POST /needs/{id}/decide`
- `GET /feedback/{token}` + `POST /feedback/{token}` (anonim form), `GET /sessions/{id}/feedback-summary` (Zeki AI tema özeti)
- `GET /usage-map` (birim × modül sayıları), `GET /me/usage` (kişinin kendi kullanımı)
- `GET/POST /guides`, `POST /guides/draft` (Zeki AI), `POST /guides/{id}/publish`, `POST /guides/{id}/vote`
- `GET /spend?year=` (Logo gideri + bütçe)
- `POST /reminders/run-due` — SYSTEM
- `POST /api/v1/hr/visit` — OPEN (yalnız kendi hesabına yazar)

**Ekranlar** `src/canvas/hr/learning/`: `MyLearning.tsx`, `LearningDashboard.tsx`, `CoursesScreen.tsx`,
`SessionScreen.tsx` (telefonda yoklama), `NeedsScreen.tsx`, `UsageMap.tsx`, `GuidesScreen.tsx`, ortak «Bu ekran nasıl
kullanılır» bağlantısı `src/canvas/hr/learning/GuideLink.tsx` (Shell başlığına eklenir; rehberi olmayan ekranda görünmez).
Rotalar: `/timas/ik/egitimlerim`, `/timas/ik/egitim`, `/timas/ik/egitim/katalog`, `/timas/ik/egitim/oturum/:id`,
`/timas/ik/egitim/ihtiyaclar`, `/timas/ik/egitim/kullanim`, `/timas/ik/egitim/rehberler`. Menü: «İnsan Kaynakları» çalışma
alanı, bölüm «Eğitim». Kampüs: «Eğitimlerim» kısa kartı (yaklaşan oturum, dolacak sertifika).

**Yetki anahtarları** (hepsi `explicit`)
- `sayfa:ik-egitimlerim` (bütün çalışanlara bağlanır), `sayfa:ik-egitim`
- `ozellik:ik.egitim-yonet`, `ozellik:ik.egitim-onay`, `ozellik:ik.egitim-butce`, `ozellik:ik.kullanim-haritasi`,
  `ozellik:ik.rehber-yaz` (portal sorumlusu), `ozellik:ik.disa-aktar` (sensitive)

**Zamanlayıcı:** `timas-hr-learning.timer` her gün 07:30 → `POST /api/v1/hr/learning/reminders/run-due` (dolacak zorunlu
eğitim, oturum hatırlatma, anket hatırlatma) ve kullanım haritası önbelleği. İlk kez elle koşturulur.

**Kabul testleri (gerçek veri; kişisel katılım verisi test sunucusuna yazılmaz, test hesabının kaydıyla)**
1. **Eğitim gider hesapları (ölçüm, kodlamadan önce):**
   `SELECT CODE, DEFINITION_ FROM LG_411_EMUHACC WHERE CODE LIKE '7%' AND (UPPER(DEFINITION_) LIKE '%EĞİTİM%' OR UPPER(DEFINITION_) LIKE '%EGITIM%' OR UPPER(DEFINITION_) LIKE '%SEMİNER%' OR UPPER(DEFINITION_) LIKE '%KURS%');`
   Sonuç İK ve Mali İşler'e gösterilir, seçilen hesaplar ayar olarak kaydedilir.
2. **Eğitim gideri:** `GET /spend?year=2026` tutarı =
   `SELECT SUM(l.DEBIT - l.CREDIT) FROM LG_411_01_EMFLINE l WHERE l.CANCELLED = 0 AND l.ACCOUNTCODE IN (:egitim_hesaplari) AND l.DATE_ >= '2026-01-01' AND l.DATE_ < '2026-08-18';`
   ve 2021–2025 için aynı sorgu `LG_211_01_EMFLINE` üzerinde yıl filtresiyle.
3. **ZEKİ soru kullanımı:** kullanım haritasındaki «Genel bakış / ZEKİ soru — son 30 gün farklı kişi» birim toplamı =
   `SELECT COUNT(DISTINCT username) FROM sl_query_log WHERE username IS NOT NULL AND created_at >= now() - interval '30 days';`
   (birim kırılımı `semantic_hr_employees` ile birleştirilerek aynı sorgu).
4. **Değişiklik kaydı kullanımı:** haritadaki «Pano / Planlı rapor / Uyarı» sütunları =
   `SELECT kind, COUNT(DISTINCT actor) FROM semantic_audit WHERE at >= now() - interval '30 days' GROUP BY kind;`
5. **Dolacak zorunlu eğitim:** panodaki sayı =
   `SELECT COUNT(*) FROM semantic_hr_certificates c JOIN semantic_hr_courses k ON k.id = c.course_id WHERE k.kind = 'zorunlu' AND c.expires_on < current_date + :gun AND NOT EXISTS (SELECT 1 FROM semantic_hr_certificates c2 WHERE c2.employee_id = c.employee_id AND c2.course_id = c.course_id AND c2.expires_on > c.expires_on);`
6. **Tamamlanma oranı:** birim × eğitim hücresi =
   `SELECT e.unit_id, s.course_id, COUNT(*) FILTER (WHERE n.completed_at IS NOT NULL) * 1.0 / COUNT(*) FROM semantic_hr_enrollments n JOIN semantic_hr_sessions s ON s.id = n.session_id JOIN semantic_hr_employees e ON e.id = n.employee_id GROUP BY 1, 2;`
7. **Anonim geri bildirim:** `semantic_hr_feedback` tablosunda kişi kimliği kolonu yok (şema testi); bir jetonla ikinci
   gönderim 409.
8. **Kişisel kullanım gizliliği:** İK rolündeki test hesabı `GET /api/v1/hr/learning/me/usage?user=başkası` → 403;
   `usage-map` cevabında hesap adı alanı bulunmaz.

**Bağımlılık:** İK-0 önce. İlk sürüm M55/M56'yı beklemez (katalog, oturum, zorunlu eğitim, ZEKİ kullanımı bağımsız);
ihtiyaç listesinin otomatik beslenmesi M56 gelince bağlanır. M58 ile paralel kodlanabilir.

**Tahmini büyüklük:** ilk sürüm **M** (1–2 gün) + kullanım haritası ve rehber kütüphanesi **M**; etki raporu sonraki sürüm **S**.
