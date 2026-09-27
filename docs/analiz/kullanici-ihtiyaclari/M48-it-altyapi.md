# M48 — IT Altyapı ve Sistem Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok; parçaları Yönetim → Genel durum'da var) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M48.txt`,
Veri Haritası (`veri_haritasi2.txt`: «IT Girdileri», «Planlama Girdileri»), `PROJECT-MEMORY.md` (sunucu/port, VPN, GPU,
kurulum kuralları), `backend/semantic_bridge/admin.py` (`SERVICES`, `TIMERS`, `system_status`, `run_checks`),
`src/canvas/admin/Overview.tsx`, `scripts/server/semantic-watchdog.sh`, `infra/docker/bi/jobs.py`,
`backend/semantic_layer/store/schema.py` (`sl_query_log`, `sl_llm_queue`, `sl_llm_job`),
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md` (talep yönetimi, demirbaş), `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`
(CRM iş akışı hataları), `scratchpad/crm_tables.txt` (CRM tablo satır sayıları, çağıran oturumun dökümü), bellek:
`bi-app-vm-55`, `timas-logo-network-access`, `logo-155-frozen-copy`, `llm-tt-gpu`, `gpu-model-tunnel`, `tt-gpu-servers`,
`timas-alerts`, `deploy-never-deletes-customer-data`, `no-backups-preference`, `no-tech-names-on-screens`.
Sunucuya bağlanılmadı; ölçülmemiş her sayı «ölçülecek» diye işaretli.

## 1. Modül ne işe yarar

ZEKİ'yi ayakta tutan halkaların (Logo ve CRM veritabanı bağlantısı, VPN, Active Directory girişi, Zeki AI modeli,
e-posta, zamanlanmış işler, müşteri VM'i) sağlığını sürekli izler; bir halka koptuğunda BT'ye kullanıcıdan önce haber
verir ve ne yapılacağını söyler (K1). İkinci ayak planlamadır: kullanım ve kaynak trendinden kapasite ihtiyacını,
model hızını ve teknoloji yenileme önceliğini çıkarır; kararı BT yöneticisi verir (K3).

TİMAŞ'ın bugünkü sorunu: kopmalar sessiz. VPN düşünce «portal açılır, veri gelmez» (PROJECT-MEMORY «VPN nasıl açılır»);
Logo'nun okuduğumuz kopyası .155 donmuş, son fatura 2026-08-17 (bellek `logo-155-frozen-copy`) ve ekranda bunu söyleyen
bir gösterge yok; CRM'deki bir ürün iş akışı son 30 günde 332 kez «sonsuz döngü» hatasıyla iptal edilmiş, kimse
görmemiş (`crm-eticaret-entegrasyon-2026-09-27.md` §1.2). Köprü bekçisi (`semantic-watchdog.sh`) sorunu yalnız sistem
günlüğüne yazar, kimseye bildirmez.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| BT sistem sorumlusu (nöbetçi) | Bilgi İşlem. Kanıt: CRM talep yönetiminde «Bilgi İşleme Aktarıldı» durumu ve CRM/Logo/Donanım/B2B/Depo/B2C konu listesi (`crm-timas-mscrm-detay` §74); VM'deki ters vekili TİMAŞ BT'den biri kurdu (bellek `bi-app-vm-55`). Ekip büyüklüğü: **ölçülecek** (CRM TeamMembership'te BT takımı görünmüyor: Editörya 54, Satış 49, Pazarlama 35, Grafik 13, Mali İşler 10) | Her gün; uyarı gelince anında | Masaüstü; uyarı ve özet telefonda (e-posta) |
| BT yöneticisi | Bilgi İşlem yönetimi (**varsayım**: sorumluyla aynı kişi olabilir) | Haftalık özet, aylık kapasite | Masaüstü |
| NanobaseAI işletim ekibi | Bizim ekip (test sunucusu, GPU, VM kurulumu) | Her kurulumda ve her uyarıda | Masaüstü |
| Üst yönetim / DYK | Genel müdürlük (**varsayım**) | Aylık / çeyreklik rapor | Masaüstü, PDF |
| Bütün portal kullanıcıları (dolaylı) | Hepsi | Kesinti anında | Her ikisi: üst şeritte «bazı veriler şu an gelmiyor» bandı (**varsayım**: istenir) |

## 3. Bugün bu iş nasıl yapılıyor

- **BT sistem sorumlusu:** ZEKİ için elinde ekran yok; Yönetim ekranı yalnız yöneticiye açık (`admin.is_admin`). TİMAŞ
  sunucularını hangi araçla izlediği, Logo/CRM yedeklerinin nasıl alındığı **bilinmiyor** (soru 2). İç BT talepleri
  eskiden CRM «Talep yönetimi»nde tutuluyordu (354 kayıt, 70 yeni / 177 tamamlandı); son değişiklik 2024-07
  (`crm-timas-mscrm-detay` §130; ölçüm 2026-09-15, o gün CRM'in .155 kopyası okunuyordu — canlı .28'de **ölçülecek**). Bugün
  talepler nereden geliyor: **varsayım** e-posta/telefon. Demirbaş (bilgisayar/monitör/harici disk, zimmet) CRM'de 76 kayıt.
- **NanobaseAI işletim ekibi:** Yönetim → Genel durum (`Overview.tsx`) 4 servis + 6 zamanlayıcıyı `systemctl` ile okur,
  «Bağlantıları dene» Logo/CRM/model/dizin/e-posta/depo bağlantısını gerçekten kurar (`admin.run_checks`). Tıkanma:
  (1) müşteri VM'i Docker'da çalışır, `systemctl` yok → VM'de servis durumu **büyük olasılıkla «bilinmiyor»** (kod
  `_unit()` systemctl yoksa bilinmiyor döner; VM'de **ölçülecek**); VM'deki zamanlanmış işler (`jobs.py`) sonucu yalnız
  konteyner çıktısına basar. (2) VPN MFA push ile elle açılır, kopunca elle teşhis (`ip -br addr show tun0`). (3) GPU model
  tüneli (`127.0.0.1:18885`) koparsa 502; kontrol elle `curl`. (4) Kurulum sonrası «`._*` sayısı 0, imaj ve kod sürümü
  doğru» denetimi elle yapılır (CLAUDE.md dağıtım kuralı).
- **Üst yönetim:** IT raporu almıyor (**varsayım**).

## 4. İhtiyaçlar ve acı noktaları

**BT sistem sorumlusu**
1. Tek bakışta «ZEKİ çalışıyor mu, çalışmıyorsa hangi halka»: Logo, CRM, AD, Zeki AI modeli, e-posta, VPN, müşteri VM'i.
2. Kopmada anında bildirim + ne yapmalı (kısa işletim tarifi: «VPN düştü → telefona gelen onayı ver»). Düzelince ikinci bildirim.
3. Veri tazeliği: Logo'nun ve CRM'in son kaydı ne zaman — «rakamlar güncel mi?» sorusunun cevabı.
4. Entegrasyon hata listesi: gece taraması, planlı rapor, uyarı, pano tazeleme, SEO eşitlemesi, CRM iş akışı hataları.
5. Kapasite: disk, bellek, VM işlemci (VM 1 vCPU, 7,6 GB — bellek `bi-app-vm-55`), model kuyruğu bekleme süresi.

**BT yöneticisi**
1. Haftalık sağlık özeti (kesinti dakikası, en çok bozulan halka).
2. Kapasite projeksiyonu: kullanıcı ve soru artışıyla kaynak ne zaman yetmez.
3. Yenileme önceliği ve gerekçesi (ör. VM işlemci artışı, MFA'sız servis hesabı).

**NanobaseAI işletim ekibi**
1. Test sunucusu ve VM'de hangi kod sürümü, hangi imaj; iki ortam eş mi.
2. Kurulum sonrası otomatik denetim (Mac artığı `._*` = 0, konteyner imajı, sağlık).
3. Model tarafı: GPU doluluğu, kuyruk bekleme, modül başına model süresi.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- BT sorumlusu olarak sabah tek ekranda bütün halkaların durumunu görmek istiyorum, çünkü kullanıcı şikâyetinden önce bilmek istiyorum.
- BT sorumlusu olarak Logo bağlantısı koptuğunda e-posta almak istiyorum, çünkü gece kopan tünel sabaha kadar kimsenin haberi olmadan kalıyor.
- BT sorumlusu olarak her uyarının yanında ne yapacağımı görmek istiyorum, çünkü VPN/MFA adımları ezberde değil.
- BT sorumlusu olarak «Logo verisi en son ne zaman» tarihini görmek istiyorum, çünkü raporlar eski veriyle çıkıyorsa bunu önce ben bilmeliyim.
- BT sorumlusu olarak son 24 saatte başarısız olan zamanlanmış işleri listelemek istiyorum, çünkü gitmeyen rapor için bana gelinecek.
- BT yöneticisi olarak aylık kesinti ve kapasite raporunu tek tıkla PDF almak istiyorum, çünkü yönetime yatırım gerekçesi sunacağım.
- BT yöneticisi olarak disk ve kuyruk trendinden «ne zaman dolar» tahminini görmek istiyorum, çünkü bütçeyi dönem başında isterim.
- İşletim ekibi olarak VM ile test sunucusunun sürüm eşliğini görmek istiyorum, çünkü geriye sarma kuralı var (bellek `vm-deploy-no-rollback`).

**Ana ekranlar ve akış**
- İlk açılış (Sistem durumu): üstte tek cümle durum («Her şey çalışıyor» / «Logo bağlantısı 42 dk'dır yok»), altında halka
  kartları (Logo · CRM · Giriş · Zeki AI · E-posta · VPN · Müşteri VM'i), her kartta son başarılı denetim ve veri sonu tarihi;
  sağda açık olay listesi; altta zamanlanmış işler tablosu (son koşu, sonuç, sonraki).
- En sık 3 işlem: (1) durumu okumak — 0 tık (açılış); (2) bir olayın ayrıntısı ve tarifi — 1 tık; (3) «Şimdi dene»
  (bağlantı denemesini tekrar koşmak) — 1 tık.
- İkinci sekme «Kapasite»: disk/bellek/kuyruk trendi ve projeksiyon; üçüncü «Olaylar»: kapanmış olaylar, süre, kök neden notu.

**Zeki AI'ya soracakları örnek sorular** (bu soruların cevabı M48'in kendi tablolarından gelir; Zeki AI sohbetinin
bugünkü kapsamı yalnız finans sorularıdır, bellek `chat-persona-zeki-ai` — bu soru kutusu modülün içinde ayrı yol olmalı)
- «Dün gece planlı raporlardan hangileri gitmedi, neden?»
- «Bu ay Logo bağlantısı kaç kez koptu, toplam kaç dakika?»
- «Bu hafta Zeki AI'ın ortalama cevap süresi geçen haftaya göre nasıl?»
- «Model kuyruğunda en çok bekleyen modül hangisi?»
- «Mevcut artışla disk ne zaman dolar?»
- «Müşteri VM'indeki sürüm test sunucusuyla aynı mı?»
- «Son 7 günde en çok hata veren entegrasyon hangisi?»

**Otomasyon katmanı**
- K1 (tam otomatik): halka denetimleri (5 dk), veri tazeliği ölçümü, zamanlanmış iş sonucu toplama, olay açma/kapama, bildirim.
- K2 (Zeki önerir, BT onaylar): olay sonrası değerlendirme (postmortem) taslağı; haftalık sağlık raporu metni.
- K3 (Zeki analiz, BT karar): kapasite projeksiyonu, yenileme önceliği, yatırım sunumu taslağı.
- K4: yok (servis yeniden başlatma gibi müdahaleler ilk sürümde ekrandan yapılmaz; bkz. §8).

**Bildirim/uyarı**
- Halka koptu (2 ardışık başarısız denetim): BT sorumlusu + işletim ekibi, e-posta (SMTP ayarı Yönetim → Ayarlar), ekranda
  kırmızı bant. Düzelince «düzeldi, süre X dk» e-postası. Hatırlatma `ALERT_REMIND_HOURS` mantığıyla (bugünkü uyarılar gibi).
- Veri tazeliği eşiği aşıldı (Logo son fatura > N gün): BT sorumlusu + yönetici, günde bir.
- Zamanlanmış iş başarısız: işin sahibi + BT, günlük özet (tek tek değil).
- Haftalık sağlık özeti: BT yöneticisi, pazartesi sabahı.
- Kanal tercihi (Teams/SMS) **bilinmiyor** — soru 1.

**Onay ve yetki**
- Görür: `sayfa:sistem-durumu` (BT rolü + yönetici). Bugün Yönetim alanı yalnız yöneticiye açık; BT personeli yönetici
  olmayabilir, bu yüzden sayfa yetkiyle açılan yeni bir alanda durmalı (bkz. §14).
- Değiştirir: eşikler ve alıcılar `ozellik:sistem.ayar` (açıkça verilir); «Şimdi dene» `ozellik:sistem.dene`.
- Onaylar: postmortem taslağının yayımı `ozellik:sistem.olay-kapat`.
- Dışa aktarma mevcut `ozellik:veri.disa-aktar`.

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Servis/zamanlayıcı durumu | Sunucu (test: systemd; VM: Docker) | `admin.system_status()` test sunucusunda okuyor | VM'de systemd yok → Docker durumu okunmuyor (**ölçülecek**) |
| Bağlantı denemeleri (Logo, CRM, model, dizin, e-posta, depo) | Köprü | `admin.run_checks()`; sonuç `semantic_audit`'e `kind=setting, action=test` olarak yazılıyor | Otomatik ve dönemsel değil (elle); zaman serisi yok |
| Köprü sağlığı + gerçek soru | Köprü `/health`, `/ask` | `semantic-watchdog.sh` 5 dk'da bir | Sonuç yalnız sistem günlüğünde; tabloya yazılmıyor, bildirim yok |
| Logo veri sonu | Logo `LG_411_01_INVOICE.DATE_` | Bellek: 2026-08-17 (2026-09-23 ölçümü) | Ekranda yok; canlı Logo .25'e erişim yok (giriş reddi) |
| CRM veri sonu | CRM `ModifiedOn` alanları | Canlı .28 (2026-09-16'dan beri) | Ölçüm ekranı yok |
| Zamanlanmış iş sonuçları | Meta DB: `semantic_reports.last_status/last_error`, `semantic_alert_rules.last_error`, `semantic_board_cards.last_error`, SEO koşuları | Yönetim özetinde sayıları var (`reportsFailed`, `cardsFailed`) | Gece katalog taraması ve dil havuzu sonucu tabloda yok (**ölçülecek**) |
| Model kuyruğu ve süreler | Meta DB `sl_llm_queue` (modül, kuyruğa giriş/başlama/bitiş), `sl_llm_job` (`queue_wait_ms`, `llm_ms`) | Var; `/api/v1/llm/queue` anlık durum | Trend ekranı yok; hacim **ölçülecek** |
| Soru hızı | `sl_query_log.latency_ms`, `answer_type`, `error` | Var | Trend ekranı yok |
| Disk/bellek/işlemci | Sunucu | Hiç toplanmıyor | Yeni toplayıcı gerek |
| GPU doluluğu | TT GPU (`nvidia-smi`) | Erişim tünelle, elle | Toplanmıyor; ekranda teknoloji adı yazmadan «Zeki AI kapasitesi» olarak |
| VPN tüneli | Test sunucusu `tun0` | Elle kontrol | Toplanmıyor |
| Kod/imaj sürümü | Kurulum betiği çıktısı | Elle | Kayıt tablosu yok |
| CRM iş akışı hataları | CRM `AsyncOperationBase` (StatusCode 31 = iptal) | 09-27 araştırmasında okundu (332/30 gün) | Düzenli okuma yok |
| Logo/CRM yedek durumu | TİMAŞ BT | **Bilinmiyor** | Soru 2 |
| İç BT talepleri | CRM `new_talepyonetimiBase` (354) | 2024-07'den beri değişmiyor | Bugünkü kaynak **bilinmiyor** (soru 3) |
| Demirbaş/zimmet | CRM `new_demirbaslarBase` (76) | Profilde var | Güncelliği **ölçülecek** |
| IT bütçesi, yatırım planı | Kullanıcı girer | Yok | Yeni alan |

## 7. Diğer modüllerle bağ

- **M49 Veri güvenliği:** erişim/giriş kayıtları, yedek doğrulaması ortak; M48 olay listesi güvenlik olaylarını da gösterir.
- **M50 Model geliştirme:** model süresi ve kuyruk metrikleri M48'de toplanır, M50 kalite metrikleriyle aynı panoda yan yana.
- **M51 Destek:** BT'ye gelen iç talepler ve «sistem çalışmıyor» kayıtları M51'in talep hattına düşebilir; kesinti anında M51'e otomatik «bilinen sorun» notu.
- **Bütün modüller:** her modülün zamanlanmış işi (planlı rapor, uyarı, pano, SEO, M46 bütçe `run-due`, editör CRM bağlayıcısı) M48'in iş tablosunda görünür.
- **DYK:** aylık sağlık ve kapasite özeti (DYK iş tanımında «ZEKİ projesinin genel sağlık raporu»).

## 8. Kısıtlar

- T-soft'a yazma yok, CRM'e yazma yok; M48 yalnız okur. Kendi durumu köprünün tablolarında (`semantic_itops_*`).
- Müşteri VM'inde web taraması kapalı; M48 dışarıya (internet) istek atmaz.
- Ekranda teknoloji adı yok: «systemd», «Docker», «vLLM», «nginx», «OpenVPN», GPU model adı yazmaz → «Sorgu motoru»,
  «Giriş servisi», «Zeki AI modeli», «Şirket ağı bağlantısı». İç günlükte adlar kalabilir (bellek `no-tech-names-on-screens`).
- Demo veri yok; boş halka «henüz ölçülmedi» der, uydurma yeşil göstermez.
- Sayı tavanı yok: olay ve iş listeleri sayfalı, tavansız.
- Kurulum müşteri verisini silmez; M48 tabloları volume'daki meta DB'de durur (bellek `deploy-never-deletes-customer-data`).
- Yedek alma adımı ürün kurulumuna eklenmez (bellek `no-backups-preference`); M48 yalnız **TİMAŞ'ın kendi** yedeklerinin
  başarı bilgisini (verilirse) gösterir.
- Ekrandan servis yeniden başlatma ilk sürümde yok: test sunucusunda birden çok oturum aynı köprüye kurulum yapıyor (bellek
  `shared-server-gate-pollution`); yanlış restart uçuştaki işi keser. Bekçinin kendi tek restart'ı olduğu gibi kalır.
- VPN MFA push'u otomatik gönderilemez (kullanıcı onayı şart); M48 yalnız «VPN düştü, onay gerekiyor» der.
- KVKK: olay/iş kayıtlarında AD hesap adı geçer; saklama süresi M49'un politikasına bağlanır.

## 9. Kapsam önerisi

**İlk sürüm (en çok değer, en az bağımlılık)**
- Halka denetimleri 5 dk'da bir otomatik (bugünkü `run_checks` + bekçi sonucu) ve sonuçların tabloya yazılması; olay aç/kapat.
- Veri tazeliği: Logo ve CRM son kayıt tarihi, eşik uyarısı.
- Zamanlanmış iş tablosu: planlı rapor, uyarı, pano, SEO, bütçe, gece taraması — son koşu, sonuç, hata cümlesi.
- VM'de de çalışan servis durumu (Docker konteyner durumu köprü içinden okunamıyorsa `jobs` konteyneri köprüye yazar).
- E-posta bildirimi (kopma + düzelme), haftalık özet.
- Sürüm kaydı: her kurulum sonunda kod sha, imaj adı, `._*` sayısı köprüye bildirilir.

**Sonraki sürüm**
- Disk/bellek/işlemci ve model kuyruğu trendi + kapasite projeksiyonu.
- GPU doluluğu (yalnız sayı; ad yok).
- Postmortem taslağı (K2), aylık yönetim raporu PDF.
- CRM iş akışı hata okuması (`AsyncOperationBase`), iç BT talep ve demirbaş görünümü (M51 ile birlikte karar).
- Zeki AI soru kutusu (M48 tablolarına).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/admin.py`: `SERVICES`, `TIMERS`, `_unit`, `_timer_times`, `system_status`, `run_check(s)`, `database_test`, `crm_test`, `llm_test`, `directory_test`, `smtp_test`, `audit`, `conf`.
- `scripts/server/semantic-watchdog.sh` (gerçek soru ile sağlık; sonucu köprüye de yazacak şekilde genişler).
- `backend/semantic_bridge/alerts.py`: kenar tetik + hatırlatma + SMTP gönderimi deseni.
- `infra/docker/bi/jobs.py`: VM'deki zamanlayıcı; iş sonuçlarını köprüye bildirmesi eklenir.
- `src/canvas/admin/Overview.tsx` (`Tile`, servis/zamanlayıcı listesi), `src/canvas/admin/ui.tsx`.
- `sl_llm_queue`, `sl_llm_job`, `sl_query_log` (metrikler), `/api/v1/llm/queue`.

## 10. Uzmanlara sorulacak sorular

1. BT ekibi kaç kişi, nöbet var mı; uyarıyı hangi kanaldan istiyorsunuz (e-posta, Teams, SMS)?
2. Logo (.155 ve canlı .25) ve CRM (.28) veritabanlarının yedeği nasıl ve ne sıklıkla alınıyor; başarı bilgisini (iş geçmişi ya da bir dosya) bize okuma izniyle açabilir misiniz?
3. İç BT talepleri 2024-07'den beri nerede tutuluyor (CRM talep yönetimi o tarihten beri değişmiyor)?
4. Müşteri VM'inin kaynağı (1 vCPU / 7,6 GB) artırılabilir mi; kim onaylar, bütçe dönemi ne zaman?
5. VPN için MFA muafiyetli servis hesabı ya da canlı Logo (.25) için okuma hesabı verilebilir mi?

## 11. Başarı ölçütü

- Tespit süresi: bir halka koptuktan sonra ilk bildirime kadar geçen süre ≤ 10 dk (5 dk denetim × 2 ardışık hata).
- Kullanıcıdan önce yakalama oranı: kesintilerin kaçı kullanıcı şikâyetinden önce olay olarak açıldı (hedef ≥ %90; ilk ay ölçülür).
- Aylık kesinti dakikası (halka başına) ve trendi.
- Başarısız zamanlanmış işin fark edilme süresi (bugün: bilinmiyor; hedef ≤ 1 gün).
- Kullanım: BT'nin ekranı haftada açma sayısı; haftalık özetin okunma oranı (e-posta bağlantısı tıklaması).
- Yanlış alarm oranı: kapatılan olayların kaçı «gerçek değil» işaretli (hedef < %10).

## 12. Uzman gözüyle en iyi sistem

**Kimin yerine geçiyorum:** 15 yıllık, orta ölçekli bir yayınevinin tek başına ya da iki kişilik BT ekibini yöneten sistem
sorumlusu. ERP (Logo), CRM (Dynamics), e-ticaret altyapısı ve şimdi bir yapay zekâ platformu onun omzunda.

**Sektörde en iyiler nasıl yapıyor:** iyi yönetilen BT ekipleri dört şey kullanır: (1) halka bazlı sentetik izleme
(«gerçek bir soru sor, cevap geliyor mu» — yalnız port açık mı değil); (2) olay yönetimi: her kopma bir olaydır,
başlangıcı, bitişi, etkilenen kullanıcıları ve kök nedeni vardır; (3) durum sayfası: kullanıcı «sistem mi bozuk, ben mi»
diye BT'yi aramadan görür; (4) kapasite planlaması: trendden «ne zaman dolar» tahmini, bütçe dönemine bağlanmış. Yayınevi
özelinde kritik olan, iş verisinin tazeliğidir: ERP kopyası donarsa bütün satış raporları sessizce yanlıştır — iyi sistem
«veri sonu»nu bir sağlık göstergesi olarak izler.

**TİMAŞ için mükemmel sistem:** tek ekran, yedi halka, her halkada iki soru: «ulaşıyor muyum» ve «veri taze mi». Kopmada
e-posta ve ne yapılacağı; düzelince süre ve neden. Haftada bir özet, ayda bir yönetim raporu. BT sorumlusu ZEKİ'yi
«kara kutu» değil, izlediği sistemlerden biri olarak görür.

**Bir iş günü:**
- 08:30 — Telefonda haftalık özet e-postası (pazartesi) ya da gece olayı yoksa hiçbir şey. Masaüstünde Sistem durumu:
  yeşil bant «Her şey çalışıyor · Logo veri sonu dün 18:42 · CRM 2 dk önce».
- 09:10 — Kırmızı bant: «Şirket ağı bağlantısı 6 dk'dır yok». Olay kartında tarif: «Telefonunuza gelen onay bildirimini
  verin; 1 dk içinde bağlantı gelmezse işletim ekibine haber verin.» Onaylar, 3 dk sonra «düzeldi, 9 dk sürdü» e-postası.
- 11:00 — Satış müdürü «rapor gelmedi» der; Zamanlanmış işler tablosunda planlı raporun hata cümlesi: «Logo'ya ulaşılamadı
  (09:05)». Kesintiyle bağını olay kartında görür, raporu «şimdi çalıştır» için sahibine yönlendirir.
- 15:00 — Kapasite sekmesi: disk %71, artış haftada %1,2 → «yaklaşık 20 hafta». Bütçe notu düşer.
- 17:30 — Olaylar sekmesinde günün tek olayına kök neden notu yazar; Zeki AI taslağını düzelterek kaydeder (K2).

**«Bunu görürsem hemen kullanırım» — 3 özellik**
1. Veri sonu tarihi her halkada: «Logo 2026-08-17'de durmuş» uyarısı.
2. Her uyarının yanında kısa, doğru işletim tarifi.
3. Kopma ve düzelme e-postası, düzelmede süreyle.

**«Bunu yaparsanız kullanmam» — 3 tuzak**
1. Her denetimde e-posta (alarm yorgunluğu); tek hata = olay açmak.
2. Yalnız «port açık» yeşili — veri gelmezken yeşil gösteren pano (bugünkü socat tuzağı: port TCP kabul eder, SQL yok).
3. Ekrandan kontrolsüz yeniden başlat düğmesi; başkasının uçuştaki işini kesen bir müdahale.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Logo bağlantı denemesi | `SELECT 1` + `SELECT MAX(DATE_) FROM LG_411_01_INVOICE WHERE CANCELLED=0` (bugünkü `admin.database_test` genişler) | — | Hiçbir şey | Sağlık ve veri sonu deterministik ölçülür |
| CRM bağlantı denemesi | — | `SELECT MAX(ModifiedOn) FROM Timas_MSCRM.dbo.new_kitapBase` (canlı .28, `admin.crm_test` genişler) | Hiçbir şey | Aynı |
| Model halkası | — | — | Tek kısa istek (bugünkü `admin.llm_test`), süre ölçülür | Modelin yanıt verip vermediği yalnız modele sorarak anlaşılır |
| Zamanlanmış iş sonucu | — | — | Hiçbir şey | Durum tablolardan okunur |
| CRM iş akışı hataları (sonraki sürüm) | — | `AsyncOperationBase` (StatusCode 31, son 30 gün, `Name` bazında sayım) | Hata mesajlarını 5–8 sınıfa ayırır (tek token + olasılık; düşük marjlı olan «sınıflanamadı») | Aynı hata yüzlerce kez tekrarlanır; sınıf BT'ye yön verir |
| Olay sonrası değerlendirme (K2) | — | — | Olayın zaman çizelgesinden taslak metin (ne oldu, süre, etki, önerilen önlem) | Metin taslağı modelin işi; rakamlar olay tablosundan gelir, model üretmez |
| Haftalık özet cümlesi | — | — | Tablodaki sayılardan 3–4 cümlelik özet | Aynı |
| Kapasite projeksiyonu | — | — | Yok (doğrusal/mevsimsel eğilim kodla hesaplanır); model yalnız gerekçe cümlesi | Tahmin rakamı model üretmez |
| Zeki AI soru kutusu (sonraki sürüm) | — | — | Soruyu M48 tablolarına karşı sabit sorgu kalıplarından birine eşler (kapalı küme seçimi) | Serbest SQL yerine kapalı seçim: güvenli ve ölçülebilir |

Model çağrıları LLM kapısından: köprü içinde `rt.llm_for("sistem", priority=BATCH)`; `LlmClient` doğrudan kurulmaz.
Model halkası denemesi de kapıdan geçer ki kuyruk doluyken «model yok» diye yanlış alarm çıkmasın: kuyruk bekleme süresi ayrı
ölçülür, model süresi (`llm_ms`) ayrı.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/it_ops.py` — tablolar, `ensure(engine)`, denetim koşucusu, olay aç/kapat mantığı, bildirim.
- `backend/semantic_bridge/it_ops_sources.py` — halka denetimleri (admin.py'deki `*_test` fonksiyonlarını çağırır, veri sonu
  sorgularını ekler), servis durumu (systemd varsa `admin._unit`, yoksa konteyner durumu `jobs` konteynerinin bildirdiği),
  zamanlanmış iş toplayıcı (`semantic_reports`, `semantic_alert_rules`, `semantic_board_cards`, SEO koşu tablosu, bütçe),
  disk (`shutil.disk_usage` veri klasörü), kuyruk (`sl_llm_queue`/`sl_llm_job`).
- `backend/semantic_bridge/it_ops_api.py` — `register(app, *, rt, can, audit, conf)`; `app.py`'de diğer `*_api` modülleri gibi bağlanır.

**Tablolar (meta DB, `semantic_itops_` öneki)**
- `semantic_itops_checks` (id, ring, at, ok bool, latency_ms, data_end timestamptz null, detail text, source `timer|manual|watchdog`) — her denetim satırı.
- `semantic_itops_incidents` (id, ring, opened_at, closed_at, first_error, last_error, notified_at, reminded_at, root_cause text, root_cause_by, postmortem_draft text, postmortem_status `yok|taslak|yayında`).
- `semantic_itops_jobs` (job, label, every, last_at, last_ok, last_error, source `systemd|jobs-container|table`) — anlık görüntü.
- `semantic_itops_releases` (id, env `test|vm|gpu`, at, code_sha, image, appledouble_count int, reported_by).
- `semantic_itops_settings` yok: eşikler `admin.conf` + `SPEC`'e eklenir (`ITOPS_CHECK_EVERY_SEC`=300, `ITOPS_FAILS_TO_OPEN`=2, `ITOPS_LOGO_STALE_DAYS`=2, `ITOPS_CRM_STALE_HOURS`=24, `ITOPS_RECIPIENTS`).

**Uçlar**
- `GET /api/v1/it-ops/status` — halkalar (son denetim, açık olay, veri sonu), özet cümle.
- `GET /api/v1/it-ops/checks?ring=&since=` — sayfalı, tavansız.
- `GET /api/v1/it-ops/incidents?state=open|closed` ; `GET /api/v1/it-ops/incidents/{id}`.
- `PATCH /api/v1/it-ops/incidents/{id}` — kök neden notu, postmortem yayımı (`ozellik:sistem.olay-kapat`).
- `POST /api/v1/it-ops/incidents/{id}/draft` — Zeki AI taslağı (kapı üstünden, `ozellik:sistem.olay-kapat`).
- `GET /api/v1/it-ops/jobs` ; `GET /api/v1/it-ops/releases`.
- `POST /api/v1/it-ops/check-now` — tek halka ya da hepsi (`ozellik:sistem.dene`).
- `POST /api/v1/it-ops/run-due` — zamanlayıcı (SYSTEM).
- `POST /api/v1/it-ops/report-release` — kurulum betiği (SYSTEM; çerezsiz, jetonla).
- `POST /api/v1/it-ops/watchdog` — bekçi betiği sonucu (SYSTEM).
- `access.py` `RULES`: `("/api/v1/it-ops/run-due", SYSTEM)`, `("/api/v1/it-ops/report-release", SYSTEM)`, `("/api/v1/it-ops/watchdog", SYSTEM)`, `("/api/v1/it-ops/", frozenset({page("sistem-durumu")}))`.
  `FEATURE_RULES`: `(POST, ^/api/v1/it-ops/check-now$, "ozellik:sistem.dene")`, `(PATCH|POST, ^/api/v1/it-ops/incidents/[^/]+(/draft)?$, "ozellik:sistem.olay-kapat")`.

**Ekranlar**
- `src/canvas/it-ops/SystemStatusScreen.tsx` (sekmeler: Durum · Olaylar · Zamanlanmış işler · Sürümler · Kapasite[sonraki]),
  `RingCard.tsx`, `IncidentPanel.tsx`. Rota `/timas/sistem-durumu` (`src/App.tsx`).
- Menü: `navModel.ts`'e yeni çalışma alanı `altyapi` («Altyapı ve destek», M48–M51 ortak; `adminOnly` değil, sayfa yetkisiyle),
  öğe `{ id: 'sistem-durumu', label: 'Sistem durumu', to: '/sistem-durumu' }`. `NavGroupId`'ye `'altyapi'` eklenir.
  Yönetim → Genel durum sekmesi kalır; «Ayrıntı için Sistem durumu» bağlantısı verir.
- Kampüs: `ModulesMenu.LIVE.M48 = '/sistem-durumu'`; telefonda üst şerit bandı (açık olay varsa, yalnız halka adı).
- `access_catalog.json`: area `{id:'altyapi', label:'Altyapı ve destek'}`; page `sayfa:sistem-durumu`; features
  `ozellik:sistem.dene`, `ozellik:sistem.olay-kapat`, `ozellik:sistem.ayar` (üçü de `explicit: true` — bugüne kadar yalnız yönetici yapabiliyordu).

**Zamanlayıcı**
- Test sunucusu: `scripts/server/timas-itops.timer` (5 dk) → `POST /api/v1/it-ops/run-due`; bekçi betiği sonunda `POST /api/v1/it-ops/watchdog`.
- VM: `infra/docker/bi/jobs.py` `JOBS` listesine `("sistem durumu", "/api/v1/it-ops/run-due", ITOPS_EVERY_SEC=300, 120)`; ayrıca her işin sonucunu `/api/v1/it-ops/watchdog` ile bildirir (VM'de systemd yok).
- `scripts/server/deploy-customer-vm.sh` ve test kurulumu sonunda `report-release` çağrısı (sha, imaj, `._*` sayısı).
- İlk koşu elle yapılır, zamanlayıcıya bırakılmaz (bellek `run-it-before-it-runs-itself`).

**Kabul testleri (gerçek veri, doğrudan bağlantı — `connector_from_file`, köprünün `run_sql`'i değil)**
1. Logo veri sonu: `SELECT MAX(DATE_) FROM LG_411_01_INVOICE WHERE CANCELLED = 0` (doğrudan .155) = ekrandaki Logo halkasının «veri sonu».
2. CRM veri sonu: `SELECT MAX(ModifiedOn) FROM Timas_MSCRM.dbo.new_kitapBase` (doğrudan .28) = CRM halkasının «veri sonu» (dakika hassasiyeti).
3. Planlı rapor hataları: meta DB `SELECT count(*) FROM semantic_reports WHERE last_status = 'failed'` = Zamanlanmış işler tablosunda «Planlı raporlar · hatalı» sayısı = Yönetim özetindeki `reportsFailed`.
4. Pano hataları: `SELECT count(*) FROM semantic_board_cards WHERE last_error IS NOT NULL` = ekrandaki pano hata sayısı.
5. Model kuyruğu: `SELECT module, percentile_cont(0.5) WITHIN GROUP (ORDER BY queue_wait_ms), percentile_cont(0.5) WITHIN GROUP (ORDER BY llm_ms) FROM sl_llm_job WHERE created_at > now() - interval '7 days' AND status='DONE' GROUP BY module` = Kapasite sekmesindeki modül tablosu.
6. Olay açma: test sunucusunda Logo tüneli **dokunulmadan**, `ITOPS_FAILS_TO_OPEN` ve sahte hedef yerine denetimin «başarısız» dalı birim testiyle; canlıda ilk gerçek VPN kopmasında olay satırı ve e-posta birlikte görülür (kanıt: `semantic_itops_incidents` satırı + alıcının e-postası).
7. VM'de servis durumu «bilinmiyor» değil: VM'de `GET /api/v1/it-ops/status` bütün halkalar için `ok` true/false döner.
8. Sürüm eşliği: `semantic_itops_releases` son test ve VM satırlarında `code_sha` = kurulum anındaki `git rev-parse main`; `appledouble_count = 0`.
9. Ekran metni taraması: `src/canvas/it-ops/` ve uçların döndürdüğü metinlerde teknoloji adı yok (grep listesi: systemd, docker, nginx, vllm, openvpn, qwen).

**Bağımlılık:** Yetki Aşama A/B (var). M46/M49/M50/M51'den bağımsız; paralel kodlanabilir. M49'un «olay» görünümü M48 tablolarını okur → M48'in `semantic_itops_incidents` şeması önce sabitlenmeli.

**Tahmini büyüklük:** İlk sürüm **M** (1–2 gün: halka tablosu, olay, iş toplayıcı, e-posta, ekran). Kapasite + postmortem + CRM iş akışı hataları **M**. Toplam **L**.
