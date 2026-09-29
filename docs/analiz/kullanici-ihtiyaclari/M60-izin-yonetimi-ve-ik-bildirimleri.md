# M60 — İzin Yönetimi ve İK Bildirimleri (İnsan Kaynakları modülünün içinde)

Tarih: 2026-09-29. Kaynak: kullanıcı talebi («izin yönetimini ve e-posta bildirimini de planla, İK modülü içinde olacak»),
eski AppSheet «Timaş Personel Portal» menüsü (İzin Yönetimi kutucuğu, Evrak deposunda «İzin Talep Formu FRM-001»),
İK personel portalı (2026-09-29, `hr_portal.py`) ve 4857 sayılı İş Kanunu. Sunucuya bağlanılmadan yazıldı; ölçülmemiş
her şey «ölçülecek» diye işaretli. **Yasal gün sayıları İK/hukuk tarafından doğrulanmadan canlıya çıkmaz** (§8).

Büyüklük: **L** (iki faz: F1 ≈ 3 gün, F2 ≈ 2 gün).

---

## 1. Modül ne işe yarar

İki parça, ikisi de İnsan Kaynakları modülünün içinde (`/timas/ik/...`, ayrı uygulama değil):

1. **İzin yönetimi:** çalışan izni portaldan ister → yöneticisi onaylar → (ayara göre) İK onaylar → bakiye düşer; ekip
   takvimi, yıllık izin hakedişi, resmî tatil takvimi, bordroya giden aylık liste. Islak imzalı «İzin Talep Formu»nun
   yerini alır (gerekirse onaylı talebin PDF'i basılır).
2. **İK bildirimleri:** bugün portal kimseye e-posta göndermiyor; evrak talebi durumunu İK işaretliyor, çalışan
   ancak portala girince görüyor. Bu modülle İK portalının olayları (evrak talebi, izin talebi/onayı, hatırlatmalar)
   **şirket içi** e-postayla kişiye gider; her e-posta portal kaydına bağlıdır, içinde kişisel/hassas veri yoktur.

## 2. Kim kullanacak

| Rol | Ne yapar |
|---|---|
| Çalışan | Bakiyesini görür, izin ister, talebini geri alır, onay/ret e-postası alır |
| Birim yöneticisi (özlük kaydındaki `yonetici_id_no`) | Ekibinin taleplerini onaylar/reddeder, ekip takvimini görür, çakışmayı görür |
| Vekil | Kendisine vekâlet bırakıldığını görür (e-posta + portal) |
| İK uzmanı | Bütün talepler, bakiye düzeltme, açılış bakiyesi, izin türleri, tatil takvimi, bordro listesi, rapor/belge |
| Bordro / muhasebe | Ayın ücretsiz izin, rapor, doğum izni günlerini Excel olarak alır |
| Genel müdür | «Bugün kim izinde», birikmiş izin riski (İK ana sayfası özeti) |

## 3. Bugün bu iş nasıl yapılıyor

- AppSheet'te «İzin Yönetimi» kutucuğu var; içeriği bu çalışmada açılmadı — **ölçülecek** (hangi alanlar, onay var mı).
- Evrak deposunda «İzin Talep Formu (FRM-001)» duruyor: form indirilir, ıslak imzayla İK'ya verilir.
- Bakiyelerin bugün nerede tutulduğu bilinmiyor: Logo Bordro Plus, İK Excel'i ya da AppSheet tablosu — **ölçülecek**
  (Logo kayıt sistemi ise bakiye oradan okunur, portal kopyalamaz; bkz. §13).
- Evrak talebi portalda (2026-09-29): çalışan ister, İK durumu işaretler, e-posta gitmez.

## 4. İhtiyaçlar ve acı noktaları

- Çalışan «kaç günüm kaldı?» sorusunu İK'ya sormadan görmeli.
- Yönetici onayı kâğıtta kayboluyor; kim ne zaman onayladı kaydı yok.
- Resmî tatil ve hafta tatili düşülerek gün sayısı elle hesaplanıyor; hata bordroya yansıyor.
- Birikmiş (kullanılmayan) yıllık izin fark edilmiyor; ayrılışta ücret yükü çıkıyor.
- Aynı ekipten aynı günlere çok kişi izin alıyor; yönetici geç fark ediyor.
- Evrak talebi «hazır» olduğunda çalışan haber almıyor; İK ayrıca e-posta yazıyor.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

1. Çalışan olarak bakiyemi ve bu yılki hakedişimi görmek, tarih seçince kaç iş günü düşeceğini **göndermeden** görmek istiyorum.
2. Yönetici olarak ekibimden gelen talebi e-postadaki bağlantıyla açıp tek tıkla onaylamak, reddedersem gerekçe yazmak istiyorum.
3. Yönetici olarak ay takviminde ekibimden kimlerin izinde olduğunu ve seçilen günlerde çakışmayı görmek istiyorum.
4. İK olarak eski bakiyeleri Excel'den bir kez yüklemek, sonra her hareketin (hakediş, kullanım, düzeltme) defterde görünmesini istiyorum.
5. İK olarak ay sonunda bordroya giden «ücretsiz izin / rapor / doğum izni» listesini Excel almak istiyorum.
6. Çalışan olarak evrak talebim hazır olunca e-posta almak, belgeyi portaldan indirmek istiyorum.

### Ana ekranlar ve akış

| Adres | Ekran | Kim |
|---|---|---|
| `/ik/izin` | **İzinlerim:** bakiye kartları (yıllık kalan · bu dönem hakedilen · kullanılan · onay bekleyen · devreden), «İzin iste» formu (tür, başlangıç–bitiş, yarım gün, vekil, izindeyken ulaşılacak telefon, not, gerekirse belge), canlı gün hesabı, geçmiş ve iptal | Herkes |
| `/ik/izin/ekip` | **Ekibimin izinleri:** onay kuyruğu, ay takvimi (kişi × gün), çakışma uyarısı, ekibin bakiye özeti | Yöneticisi olduğu kişi varsa dolu, yoksa boş |
| `/ik/yonetim?sekme=izinler` | **İK yönetimi › İzinler:** bütün talepler (süzgeç: durum, tür, birim, ay), bakiye defteri ve düzeltme, açılış bakiyesi Excel'i, bordro listesi Excel'i | İK |
| `/ik/yonetim?sekme=izin-ayarlari` | İzin türleri, resmî tatil takvimi, çalışma takvimi (Cumartesi çalışılan birim/şube), onay akışı, e-posta bildirim ayarları | İK |
| `/ik` | Ana sayfaya **İzin yönetimi** kutucuğu (kalan gün + onay bekleyen rozeti); «Bugün izinde» kutusu (ekip/birim); İK özetine «bugün izinde», «onay bekleyen», «birikmiş izni 30+ gün», «yaklaşan hakediş» | Herkes / İK |
| `/ik/rehber` | Kişi kartında «İzinde · 7 Ekim'de dönüyor» (tür yazmaz) | Herkes |

Akış: `taslak → yönetici onayı bekliyor → (İK onayı bekliyor) → onaylandı | reddedildi | geri alındı`; onaylanan izin
başlamadan iptal edilirse bakiye iade hareketi yazılır. Yöneticisi olmayan (en üst) kişinin talebi doğrudan İK'ya düşer.

### Zeki AI'ya soracakları örnek sorular

- «Kaç gün yıllık iznim kaldı?» · «Ekim'de ekibimden kim izinde?» · «Bu ay en çok kim izin kullandı?» (İK) ·
  «Birikmiş izni en çok olan 10 kişi» (İK). Cevap izin uçlarından; kişi yalnız kendi ve (yöneticiyse) ekibinin verisini sorar.

### Otomasyon katmanı

- **Gece hakediş işi** (`timas-hr-leave.timer`, her gece 02:10): işe giriş yıldönümü gelen kişiye yıllık izin hakedişi
  hareketi yazar (kıdem ve yaş kuralına göre gün sayısı), yazdığını İK özetine düşer.
- **Hatırlatmalar** (aynı iş): 2 iş günü onaysız bekleyen talep → yöneticiye; izin dönüşünden bir gün önce → çalışana
  değil (gerek yok), vekâlet bitişi → vekile değil; yalnız onay bekleyen hatırlatması (az e-posta ilkesi).
- **E-posta kuyruğu** (`timas-hr-mail.timer`, 5 dakikada bir): kuyruktaki e-postaları gönderir, başarısızı 3 kez dener.

### Bildirim ve uyarı (e-posta)

| Olay | Kime | Konu örneği |
|---|---|---|
| Yeni evrak talebi | İK dağıtım adresi (`HR_ALERT_RECIPIENTS`) | «Evrak talebi: Çalışma belgesi» |
| Evrak talebi durumu değişti (hazırlanıyor / hazır / karşılanamadı) | Talep eden | «Evrak talebiniz hazır» |
| Yeni izin talebi | Yönetici (yoksa İK) | «İzin talebi onayınızı bekliyor» |
| Yönetici onayladı, İK onayı gerekiyor | İK | «İzin onayı: İK onayı bekleniyor» |
| Onaylandı / reddedildi / onaylı izin iptal edildi | Çalışan (+ vekil: yalnız onaylandı) | «İzin talebiniz onaylandı» |
| 2 iş günü onaysız | Yönetici | «2 izin talebi onayınızı bekliyor» (günde en çok bir kez, toplu) |

E-posta kuralları:
- Gövdede yalnız olay, tarih aralığı ve portal bağlantısı; izin türü «hassas» işaretliyse (rapor, doğum) tür yazmaz,
  «izin» der. T.C., IBAN, sağlık, belge eki yok; hazır evrak **ek olarak gönderilmez**, İK talebe dosyayı ekler, çalışan
  portaldan indirir (erişim kaydına düşer).
- Alıcı yalnız şirket içi alan adları (`HR_MAIL_DOMAINS`, varsayılan `timas.com.tr`); özlük kaydındaki kişisel e-posta
  (gmail vb.) kullanılmaz, e-posta yoksa bildirim portalda kalır.
- Açma/kapama: `HR_MAIL_ENABLED` (varsayılan kapalı — ilk açılışı İK yapar); test sunucusunda «yalnız kaydet» kipi
  (kuyruğa yazar, göndermez) ile denenir. Kişi Profilim'de e-posta bildirimini kapatabilir (onay isteyen yöneticiye
  giden e-posta kapatılamaz).
- Toplu e-posta yok (modül kararı 2026-09-28): duyuru ve doğum günü e-postası bu kapsamda değil.

### Onay ve yetki

- Sayfalar: `sayfa:ik-izin` ve `sayfa:ik-izin-ekip` Herkes'e açık (uç kişinin kendi / ekibinin verisini döner);
  yönetim sekmeleri `sayfa:ik-yonetim` altında.
- Özellikler: `ozellik:ik.izin-yonet` (bütün talepler, bakiye düzeltme, açılış, bordro listesi), `ozellik:ik.izin-ayar`
  (türler, tatiller, akış, e-posta), hassas izin türünün ayrıntısı ve belgesi mevcut `ozellik:ik.ozluk-hassas` ile.
- Yönetici onayı: onaylayan = talep anındaki `yonetici_id_no`'nun portal hesabı; kendi talebini onaylayamaz; vekil
  yönetici (yönetici izindeyken) F2'de.
- Her durum değişikliği `semantic_hr_leave_events`'e ve değişiklik kaydına (ad değil, talep no) düşer.

## 6. Veri

Yeni tablolar (`semantic_hr_leave_*`, `semantic_hr_mail_outbox`):

| Tablo | İçerik |
|---|---|
| `semantic_hr_leave_types` | anahtar, ad, ücretli mi, bakiyeden düşer mi, yıllık üst sınır (gün), belge ister mi, hassas mı, yarım gün olur mu, yasal dayanak metni, açık/kapalı |
| `semantic_hr_holidays` | gün, ad, tam/yarım gün (arife), yıl |
| `semantic_hr_work_calendars` | takvim adı, çalışılan günler (Pzt–Cmt), bağlı şube/birim; kişiye özlük kaydındaki şube/lokasyondan |
| `semantic_hr_leave_requests` | personel (`semantic_hr_people.id`), tür, başlangıç, bitiş, yarım gün, hesaplanan iş günü, vekil, not, durum, onaylayan(lar), tarihler |
| `semantic_hr_leave_events` | talep olayları (açıldı, onay, ret, iptal) — kim, ne zaman |
| `semantic_hr_leave_ledger` | bakiye defteri: kişi, tür, gün (+/−), sebep (açılış, hakediş, kullanım, iade, düzeltme, devir), kaynak talep, yazan, tarih; **bakiye = toplam**, ayrı bakiye kolonu yok |
| `semantic_hr_leave_files` | rapor vb. belge (bayt DB'de, hassas) |
| `semantic_hr_mail_outbox` | alıcı, konu, gövde, olay, konu kaydı, durum (bekliyor/gönderildi/hata/kapalı), deneme sayısı, zaman; gövdede hassas veri yok |

Gün hesabı: başlangıç–bitiş aralığında kişinin çalışma takviminde **çalışılan** ve resmî tatil **olmayan** günler; arife
yarım gündür; yarım gün izin 0,5. Hesap sunucuda (tek yer), ekran yalnız gösterir.

Yıllık izin kuralları (4857 md. 53–56; **İK/hukuk doğrulayacak**, türe ayar olarak yazılır, kodda sabit değil):
hizmet süresi 1–5 yıl (5 dahil) 14 gün; 5'ten fazla 15'ten az 20 gün; 15 yıl ve fazla 26 gün; 18 yaş ve altı ile 50 yaş
ve üstü en az 20 gün. Hak, ilk yılı dolunca doğar (işe giriş yıldönümü; `f_ise_giris_tarihi`). Bölünmüş kullanımda bir
parça 10 günden az olamaz → kural ihlalinde uyarı (engel değil). Mazeret izinleri (ek md. 2: evlilik 3, eşin doğumu 5,
ölüm 3, evlat edinme 3, engelli/kronik hasta çocuk tedavisi yılda 10 gün), doğum izni (md. 74), süt izni, yol izni,
ücretsiz izin, raporlu izin türleri başlangıç listesi olarak gelir; İK açar/kapatır, gün sayısını düzeltir.

Resmî tatiller: sabit günler (1 Ocak, 23 Nisan, 1 Mayıs, 19 Mayıs, 15 Temmuz, 30 Ağustos, 28 Ekim yarım, 29 Ekim) ve
yıla göre değişen dini bayramlar (arife yarım + Ramazan 3, Kurban 4 gün). Takvim tablodadır; İK yılı açar, «geçen yılın
sabit günlerini kopyala» + bayram günlerini girer. Koda liste yazılmaz.

Açılış bakiyesi: Excel (personel no, tür, gün, tarih) → defterde «açılış» hareketi; önizleme → yaz (personel içe
aktarmasıyla aynı düzen: hatalı satır varken hiçbir şey yazılmaz).

## 7. Diğer modüllerle bağ

- **Özlük kaydı (bu dal):** yönetici zinciri (`yonetici_id_no`), işe giriş, doğum tarihi (yaş kuralı), şube/lokasyon
  (çalışma takvimi), durum (pasif kişiye talep açılmaz). Ayrılışta (işten çıkış tarihi) kalan yıllık izin İK özetine düşer.
- **İK ana sayfası / rehber / Profilim:** kutucuk, «bugün izinde», rehberde «izinde» rozeti (tür yok), Profilim'de bildirim tercihi.
- **Evrak talebi:** bildirim altyapısını ilk kullanan olay; İK talebe hazır belgeyi ekler (yeni: `semantic_hr_doc_request_files`).
- **M57 Eğitim:** eğitim oturumu ile onaylı izin çakışırsa her iki tarafa uyarı (F2).
- **Logo Bordro (varsa):** aylık bordro listesi Excel'i; Logo'ya yazma yok. Bakiyenin kayıt sistemi Logo çıkarsa defter
  «Logo'dan okunan + portal hareketleri» olarak kurulur (§10 soru 1).
- **Zeki AI sohbeti:** «kaç günüm kaldı» sınıfı sorular izin uçlarından; kapsam `chat_scope.py`'de İK'ya açık (2026-09-28 kararı).

## 8. Kısıtlar

- **KVKK:** rapor (sağlık) ve doğum izni türleri özel nitelikli/hassas: yönetici yalnız «izinli» görür, tür ve belge
  hassas yetkiyle; e-postada tür yazılmaz. Rehberde yalnız «izinde» ve dönüş tarihi.
- **Yasal değerler:** gün sayıları ve kurallar İK/hukuk onayı olmadan «taslak» kalır (izin türü satırında «onaylandı»
  işareti); onaysız türle talep açılmaz.
- **Dış gönderim yok:** yalnız şirket içi alan adına e-posta; SMS, WhatsApp, takvim daveti yok (F3 adayı).
- **Gönderen hesap:** mevcut SMTP ayarı (Uyarılar/Yönetim) kullanılır; ayrı gönderen istenirse BT'den (`Bilgiislem@timas.com.tr`) hesap.
- **Tek kayıt:** bakiye tek yerde (defter toplamı); ekranlar kopya tutmaz.
- **Mobil:** İzinlerim ve onay kuyruğu telefonda tam çalışmalı (320/390 px); takvim telefonda liste görünümüne düşer.

## 9. Kapsam önerisi

**F1 (≈3 gün) — asgari iş gören sürüm**
1. E-posta kuyruğu + gönderici iş + ayarlar (kapalı başlar) + evrak talebi bildirimleri + İK'nın talebe belge eklemesi.
2. İzin türleri (başlangıç listesi, «taslak» işaretli), resmî tatil ve çalışma takvimi ekranları.
3. İzinlerim: bakiye, talep, canlı gün hesabı, geri alma. Onay: yönetici → (ayar) İK. Bildirimler.
4. Bakiye defteri, açılış Excel'i, İK düzeltmesi. Ana sayfa kutucuğu + İK özetine iki sayı.

**F2 (≈2 gün)**
5. Ekip takvimi + çakışma uyarısı; rehberde «izinde»; vekil ve vekil yönetici.
6. Gece hakediş işi + yaklaşan hakediş + birikmiş izin uyarısı; onay hatırlatması.
7. Bordro listesi Excel'i; onaylı talebin PDF'i (ıslak imza gereken durum için).

**F3 (sonra)** saatlik izin, Logo Bordro puantaj eşlemesi (okuma), takvim aboneliği, eğitim çakışması.

## 10. Uzmanlara sorulacak sorular (kodlamadan önce)

1. Bugünkü izin bakiyeleri nerede: Logo Bordro Plus, Excel, AppSheet? (Kayıt sistemi Logo ise okunur, kopyalanmaz.)
2. Onay akışı: yalnız yönetici mi, yönetici + İK mı? Tür başına farklı mı (ör. ücretsiz izne GM onayı)?
3. Cumartesi çalışan birim/şube var mı (Depo? Babıali?) — çalışma takvimi buna göre.
4. Yarım gün izin ve avans (hakedilmeden) izin veriliyor mu? Devreden izin için üst sınır var mı?
5. Raporu kim girer (çalışan belge yükler mi, İK mı)? Yönetici rapor türünü görmeli mi?
6. Bildirim göndereni: mevcut SMTP hesabı mı, BT'nin açacağı `ik@`/`noreply@` adresi mi?
7. Hangi olaylar e-posta, hangileri yalnız portal? (Öneri §5 tablosu.)

## 11. Başarı ölçütü

- Kâğıt izin formu ilk ay içinde %90 azalır (portal talep sayısı ÷ toplam izin).
- Talebin onaylanma süresi ortanca 1 iş günü altında.
- Bordro listesinde elle düzeltme sayısı sıfıra yakın (gün hesabı hatası yok).
- Evrak talebinde «hazır mı» diye İK'ya soru gelmez; e-posta teslim oranı %98+ (kuyruk kaydından).

## 12. Uzman gözüyle en iyi sistem

Bakiye bir **defter** (hareket toplamı) olmalı, düzeltilebilir bir sayı değil: her gün sayısının neden öyle olduğu
geriye izlenebilir, ayrılışta tartışma çıkmaz. Gün hesabı tek yerde, takvim ve tatil tablosuna bağlı olmalı. Yönetici
onayı e-postadan tek tıkla açılmalı ama onay portalda verilmeli (e-postadaki bağlantı oturum ister; e-postayla onay
yok). Bildirim az ve anlamlı olmalı: toplu hatırlatma günde bir, her olayda tek alıcı. Hassas izin türü (rapor)
yöneticiye «izinli» olarak görünmeli — bu, KVKK'nın ve çalışan güveninin gereği.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Nerede | Ne | Neden |
|---|---|---|
| Zeki AI sohbeti | «Kaç günüm kaldı», «ekibimden kim izinde» → izin uçlarının cevabı cümleye döker | Rakam koddan; model yalnız anlatır (sayı denetçisi `zeki_text`) |
| Zeki AI | Talep notundan izin türü önerisi (ör. «nikâhım var» → evlilik izni) — seçimi kişi yapar | `QueuedLlm.choose`, kapalı küme |
| Logo | Bordro Plus varsa: bakiye/puantaj **okuma**; yoksa kullanılmaz | Kayıt sistemi Logo'dur (bkz. «system-of-record-logo») |
| CRM | Kullanılmaz | İzin verisi CRM'de yok |

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü**
- `backend/semantic_bridge/hr_mail.py`: `enqueue(engine, tenant, to, subject, body, event, subject_ref)` (alan adı
  süzgeci, kişi tercihi, `HR_MAIL_ENABLED`/«yalnız kaydet» kipi), `run_outbox()` (`budget_api._send_mail` ile; 3 deneme),
  `semantic_hr_mail_outbox`. Uç `POST /api/v1/hr/mail/run-due` (SYSTEM). Zamanlayıcı `timas-hr-mail.timer` (5 dk).
- `hr_portal.py`: evrak talebi olayları `hr_mail.enqueue`'ya; `semantic_hr_doc_request_files` + uçlar
  (İK yükler, çalışan `/portal/requests/{id}/file` ile indirir, erişim kaydı).
- `backend/semantic_bridge/hr_leave.py` + `hr_leave_api.py` (`/api/v1/hr/leave/*`; me, calc, requests, team, admin/*,
  settings), tablolar §6. Gün hesabı `working_days(person, start, end, half)` tek işlev; hakediş `accrual_for(person, on)`
  tür ayarından. `run_due()` (hakediş + hatırlatma) → `POST /api/v1/hr/leave/run-due` (SYSTEM), `timas-hr-leave.timer` 02:10.
- `access.py` RULES: `/api/v1/hr/leave/admin/` → `ik-yonetim`; `/api/v1/hr/leave/` → `ik-izin`, `ik-izin-ekip`, `ik-anasayfa`;
  run-due SYSTEM. `access_catalog.json`: 2 sayfa + `ik.izin-yonet`, `ik.izin-ayar`. `response_cache.NEVER_PREFIXES`'e `/api/v1/hr/leave/`.
- VM: `infra/docker/bi/jobs.py`'ye iki run-due (müşteri VM'inde zamanlayıcı yerine).

**Ön yüz** (`src/canvas/hr/leave/`)
- `leaveApi.ts`, `MyLeave.tsx` (`/ik/izin`), `TeamLeave.tsx` (`/ik/izin/ekip`, takvim + kuyruk), `admin/LeaveAdmin.tsx`
  ve `admin/LeaveSettings.tsx` (İK yönetimi sekmeleri «İzinler», «İzin ayarları»), `HrHome` kutucuk + özet,
  `Directory` «izinde» rozeti, `Profile` bildirim tercihi, İK yönetimi › Listeler'e «E-posta bildirimleri».
- `navModel.ts`: `ik-izin`, `ik-izin-ekip` (bölüm «Personel portalı»); `screenInfo` metinleri; `App.tsx` rotaları.

**Kabul** (`scripts/acceptance/M60/`, test sunucusunda, yan köprüde, timasai kısa oturumu)
- Gün hesabı: hafta sonu, resmî tatil, arife yarım gün, ay/yıl dönümü aşan talep, yarım gün; referans takvim elle.
- Akış: talep → yönetici onayı → İK onayı → defter hareketi; ret gerekçesi zorunlu; iptalde iade hareketi.
- Hakediş: 1., 5., 6., 15. yıl ve 50 yaş sınırları; yıldönümünde tek hareket (iki kez koşunca ikinci yazmaz).
- Bildirim: «yalnız kaydet» kipinde her olayın kuyruk satırı, alıcı alan adı süzgeci, hassas türde tür yazmadığı.
- Temizlik: test talebi, defter, kuyruk satırları kimliğiyle silinir; sayısı günlüğe (`temizlik.py`).
