# H4 — Kurumsal E-posta Yönetimi (timas@timas.com.tr): kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul bekliyor (testler koordinatörde) · Analiz tarihi: 2026-09-28 · Modül kimliği `email` (`src/canvas/modules.json`, «Hazırlıklar» grubu). Kutu Google Workspace (kullanıcı kararı); Gmail API yalnız okuma + etiket.

Kaynaklar: iş tanımı `specs/Kurumsal_E_posta_Yönetimi.txt`, `ZEKİ_Veri_Haritasi2.html` (M51 destek girdileri),
`specs/M1.txt`, `M51.txt`, `M55.txt`, `docs/analiz/yazar-giris-sureci-crm-2026-09-24.md`,
`docs/analiz/editoryal-m1-m8-eksikler-2026-09-20.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `configs/semantic/knowledge/crm/table_descriptions.json` (CRM
metadata, 2026-09-09), `backend/semantic_bridge/admin.py` (SMTP ayarları), `alerts.py`, `freelance.py` (dış kişiye
e-posta ve gelen yanıt kaydı), `people.py` (kişi rehberi), `editorial_intake.py` (yazar giriş süreci), `access.py`,
PROJECT-MEMORY.md, kullanıcı belleği (timas-access-credentials — yalnız hesabın Google Workspace olduğu bilgisi
kullanıldı, kimlik bilgisi kullanılmadı; timas-alerts, no-tech-names-on-screens, system-of-record-logo).

Sunucuya ve posta kutusuna bağlanılmadı. Kutu hacmi, kategori dağılımı ve bugünkü yanıt süreleri ölçülmedi; hepsi
«ölçülecek». Kanıtsız iddialar «varsayım».

---

## 1. Modül ne işe yarar

TİMAŞ'ın genel e-posta kutusuna (timas@timas.com.tr) gelen her iletiyi okur, türünü (dosya başvurusu, iş başvurusu,
şikâyet/soru, bağış/sponsorluk, tanıtım/reklam/spam …) ve önceliğini belirler, sorumlu kişi ya da birime iş olarak
atar, cevap süresini (SLA) izler, geciken iletiler için hatırlatma ve üst yöneticiye bildirim üretir, kategori bazında
hazır yanıt taslağı sunar. Dosya başvurusu yazar giriş sürecine (M1), iş başvurusu İK'ya, şikâyet ilgili birime akar.

Bugünkü sorun (varsayım, kanıtı sorulacak): genel kutu bir ya da birkaç kişi tarafından elle okunup ileriye yönlendiriliyor;
iletinin kime gittiği, cevaplanıp cevaplanmadığı, ne kadar sürede cevaplandığı kayıt altında değil. CRM'de bu işe
ayrılmış yapılar ya ölü ya çok az kullanılıyor: dosya başvuru tablosu 19 kayıt (son 2024-05), servis talebi
(`IncidentBase`) 34 kayıt, BT talep modülü son değişiklik 2024-07 (§3, §6).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Genel kutu sorumlusu (ilk bakan) | Varsayım: sekreterya / kurumsal iletişim; kim olduğu sorulacak | Her gün, gün boyu | Masaüstü; telefonda bildirim |
| Editörya başvuru sorumlusu | Editörya (ekip 54 kişi); yazar giriş süreci ekranının kullanıcısı | Her gün / haftada birkaç | Masaüstü |
| İK uzmanı | İK (portalda henüz İK ekranı yok; kim olduğu sorulacak) | Haftalık | Masaüstü |
| Müşteri hizmetleri / satış destek | Satış (ekip 49) ya da ayrı birim — varsayım | Her gün | Masaüstü |
| Kurumsal iletişim (bağış, sponsorluk, basın) | Pazarlama / kurumsal iletişim — varsayım | Haftalık | Masaüstü, telefon |
| Birim yöneticileri | Birim başına | Eskalasyon geldikçe; haftalık rapor | Telefon |
| Portal yöneticisi / BT | BT | Kurulum, kural sürümü | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

**Genel kutu sorumlusu (varsayım):** e-posta istemcisinde kutuyu açar, iletiyi okur, ilgili kişinin adresine iletir
ya da kendisi yanıtlar. Adım sayısı ileti başına 3–5 (oku, karar ver, ilet, gerekirse gönderene bilgi ver, klasöre
taşı). Tıkanma: iletildikten sonra takip yok; aynı gönderen birkaç kez yazar; izinli/izinsiz dönemlerde kutu birikir.

**Posta altyapısı (kanıt kısmi):** timas.com.tr alan adında zeki@timas.com.tr bir Google Workspace hesabıdır (bellek:
portalın uyarı/rapor e-postaları bu hesaptan gönderiliyor). timas@ kutusunun da aynı Workspace'te olması muhtemel
(varsayım; MX kaydı ve kutu türü BT'ye sorulacak). İş tanımı «Microsoft Graph / IMAP + OAuth2» diyor; Workspace ise
doğru yol Gmail API (alan geneli yetki devriyle tek kutuya sınırlı) ya da IMAP + OAuth2'dir.

**CRM tarafı (kanıt):**
- CRM'de e-posta etkinlikleri var: son 30 günde 1.953 e-posta kaydı değişmiş (2026-09-15); 1 e-posta sunucusu profili
  (`EmailServerProfileBase`; türü Exchange/POP3 mü ölçülecek); `QueueBase` 412 (Dynamics her kullanıcıya kuyruk açar;
  genel kutu için ayrı kuyruk var mı ölçülecek). Hangi kutuların CRM'e eşitlendiği bilinmiyor.
- Dosya başvurusu: `new_dosyabasvuruBase` (geliş kaynağı Web/Posta/Kişi/E-Mail seçenekli) 19 satır, son kayıt 2024-05
  → ölü. Başvurular bugün doğrudan proje kartı (`new_projeBase`) olarak açılıyor; oluşturma kanalı
  (`new_olusturmakanali`: Web Başvurusu, Referans, Dosya Başvurusu, Fuar…) yalnız %47 dolu (2026-09-24).
- Şikâyet/talep: `IncidentBase` 34 kayıt (tür: Soru/Şikâyet/Talep/Öneri/Memnuniyet; kaynak: Telefon/E-posta/Web/
  Facebook/Twitter) → pratikte kullanılmıyor.
- İK: CRM'de çalışan/aday İK modülü görünmüyor (`new_ozgecmisBase` 89 kayıt yazar özgeçmişidir). İK'nın kullandığı sistem
  sorulacak.
- Şablon: CRM e-posta şablonu 27, özel şablon tabloları 11 + 3 (içerik ölçülecek).

**Portal tarafı (kanıt, kod):** Portal bugün e-postayı yalnız **gönderiyor** (uyarılar, planlı raporlar, bütçe, serbest
çalışana ileti; SMTP ayarı Yönetim ekranında). Gelen yanıtlar kendiliğinden okunmuyor (serbest çalışan yazışmasında
«gelen e-posta kendiliğinden okunmuyor», elle kaydediliyor).

## 4. İhtiyaçlar ve acı noktaları

**Genel kutu sorumlusu**
1. Gelen iletinin türünü ve sorumlusunu otomatik önerilmiş görmek; tek tıkla atamak.
2. Kutunun anlık durumu: yeni, atanmış, bekleyen, süresi aşan.
3. Spam ve tanıtım iletilerinin kendiliğinden ayrılması.
4. Aynı gönderenin önceki iletilerini ve CRM'deki kaydını görmek.

**Birim sorumluları (editörya, İK, müşteri hizmetleri, kurumsal iletişim)**
1. «Bana/birimime atanan» liste, SLA'ya kalan süre.
2. Hazır yanıt taslağı; düzenleyip gönderme.
3. Dosya başvurusunun eklerle birlikte yazar giriş sürecine aktarılması (editörya).
4. İş başvurularının yalnız İK tarafından görülmesi (İK).

**Birim yöneticileri**
1. Süresi aşan iletiler için bildirim; haftalık hacim ve yanıt süresi raporu.

**Portal yöneticisi**
1. Yönlendirme tablosu, şablonlar ve SLA kurallarının sürümlü, onaylı yönetimi.
2. Otomatik yanıtın açılıp kapatılabilmesi (kategori bazında).

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Genel kutu sorumlusu olarak sabah kutuyu açtığımda iletilerin türüne göre ayrılmış ve sorumlusu önerilmiş hâlde
  gelmesini istiyorum, çünkü her iletiyi tek tek okuyup karar vermek saatlerimi alıyor.
- Genel kutu sorumlusu olarak Zeki'nin emin olmadığı iletileri ayrı görmek istiyorum, çünkü yalnız onlara bakmam
  yeterli olmalı.
- Editörya sorumlusu olarak bir dosya başvurusunu ekleriyle yazar giriş sürecine tek tıkla aktarmak istiyorum, çünkü
  başvuru kaybolmamalı.
- İK uzmanı olarak iş başvurularını yalnız benim görmemi istiyorum, çünkü özgeçmişler kişisel veri.
- Müşteri hizmetleri olarak şikâyete, sipariş numarası geçiyorsa siparişin durumunu yanında görmek istiyorum.
- Birim yöneticisi olarak 48 saati geçen iletiler için bildirim almak istiyorum, çünkü müşteri cevapsız kalmamalı.
- Portal yöneticisi olarak «başvurunuz alındı» otomatik yanıtını yalnız dosya başvurularında açmak istiyorum, çünkü
  yanlış sınıflanan şikâyete bu yanıt gitmemeli.

### Ana ekranlar ve akış
1. **Gelen kutusu (ilk açılış):** sekmeler «Bana atanan», «Birimim», «Atanmamış», «Emin olunmayan», «Süresi aşan»,
   «Arşiv». Satırda: gönderen (CRM rozeti: yazar/bayi/okur), konu, Zeki özeti (1–2 cümle), tür + olasılık, öncelik,
   SLA kalan süre.
2. **İleti ayrıntısı:** ileti gövdesi (kutudan anlık), ekler, önceki yazışmalar, CRM bağlamı, tür/sorumlu düzeltme,
   atama, yanıt taslağı, «Yazar giriş sürecine aktar», «Kapat».
3. **Rapor:** kategori bazında hacim, ortalama ilk yanıt ve kapanış süresi, SLA uyumu, birim/kişi dağılımı.
4. **Kurallar:** yönlendirme tablosu (tür → birim/kişi, yedek), şablonlar, SLA eşikleri, otomatik yanıt anahtarları;
   taslak → onay → yürürlükte.
5. **Bağlantı:** kutu bağlantısı durumu, son okuma, hata.

En sık üç işlem:
- Öneriyi kabul edip atamak: satır (1) → «Ata» (2).
- Taslakla yanıtlamak: satır (1) → «Yanıt taslağı» (2) → düzenle → «Gönder» (3) (ilk sürümde «Kutuda aç» ile
  kutunun kendi arayüzünde gönderim).
- Başvuruyu aktarmak: satır (1) → «Yazar giriş sürecine aktar» (2) → onay (3).

### Zeki AI'ya soracakları örnek sorular
- «Bu hafta kaç dosya başvurusu geldi, kaçı yazar giriş sürecine aktarıldı?»
- «Şikâyetlerde ortalama ilk yanıt süremiz ne, hangi birimde en uzun?»
- «48 saati geçen ve hâlâ cevapsız iletiler kimde?»
- «Geçen ay en çok hangi konuda şikâyet geldi?»
- «Bu gönderen daha önce bize yazmış mı, CRM'de kaydı var mı?»
- «Bağış ve sponsorluk taleplerinin aylık sayısı nasıl değişiyor?»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| Kutudan okuma, kopya/konu zinciri eşleme, gönderen tanıma (CRM) | K1 | Her birkaç dakikada |
| Tür + öncelik + sorumlu önerisi | K2 başlangıç; olasılığı yüksek ve pilotta doğrulanmış türler için K1 atama | Eşik ve tür bazında açılır |
| Spam/tanıtım arşivi | K1 (kutunun kendi spam işaretine ek) | Arşiv geri alınabilir |
| «Alındı» otomatik yanıt | K1, yalnız yönetici açtığı türlerde ve pilot sonrası | Metin yönetici onaylı şablon |
| İçerikli yanıt | K2 | Zeki taslak yazar, insan gönderir |
| SLA hatırlatma ve eskalasyon | K1 | Bildirim (iç) |
| Yönlendirme tablosu, şablon, SLA kuralları | K4 | İnsan yazar, yönetici onaylar |

### Bildirim/uyarı
- Atama → atanan kişiye portal bildirimi (Kampüs zil) + isteğe bağlı iç e-posta (mevcut SMTP).
- SLA: 24 saat → atanan kişiye hatırlatma; 48 saat → birim yöneticisine; 72 saat → üst yöneticiye (iş tanımındaki
  eşikler; kategori bazında ayarlanabilir; iş saatleri takvimiyle).
- Kutu bağlantısı koptu / 30 dakikadır okuma yok → portal yöneticisi.
- Haftalık rapor → birim yöneticileri (Planlı raporlar altyapısı).

### Onay ve yetki (öneri)
| İşlem | Kim | Anahtar |
|---|---|---|
| Sayfa (yalnız kendine/birimine atananlar) | Atanabilecek herkes | `sayfa:kurumsal-eposta` |
| Bütün kutuyu görmek | Genel kutu sorumlusu, yöneticiler | `ozellik:eposta.herkesinki` |
| Atama ve tür düzeltme | Genel kutu sorumlusu, birim sorumluları | `ozellik:eposta.ata` |
| Timaş adına dışarıya yanıt göndermek | Yetkili kişiler | `ozellik:eposta.yanitla` (açıkça verilir) |
| İş başvurularını görmek | Yalnız İK | `ozellik:eposta.ik` (açıkça; yönetici dahil başkası görmez — yönetici istisnası tartışılacak) |
| Kurallar/şablon/SLA taslağı | Portal yöneticisi, genel kutu sorumlusu | `ozellik:eposta.kural` |
| Kuralları yürürlüğe almak | Yönetim | `ozellik:eposta.kural-onay` (açıkça) |
| Otomatik yanıtı açmak | Yönetim | `ozellik:eposta.otomatik-yanit` (açıkça) |

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Gelen iletiler (başlık, gövde, ek, zincir) | timas@timas.com.tr kutusu (Gmail API / IMAP + OAuth2) | Bağlantı yok | Kutu türü (Workspace mı), erişim yöntemi ve yetkisi BT'den; günlük hacim ölçülecek |
| Geçmiş iletiler (etiketleme için) | Aynı kutu | Yok | Son 6–12 ayın örneklemi insan tarafından etiketlenecek (sayı ölçülecek) |
| Gönderen tanıma | CRM `ContactBase.EMailAddress1` (59.637 kişi), `AccountBase` e-posta, `LeadBase.EMailAddress1` | Şema biliniyor | E-posta doluluk oranı ölçülecek |
| Yazar / başvuru bağlamı | CRM `new_projeBase` (`new_olasyazaryazar` → Contact, `new_olusturmakanali`, `CreatedOn`), portal yazar giriş süreci | Canlı (2.115 proje 2025'ten beri) | E-postadan gelen başvurunun projeyle eşlenmesi insan kararı |
| Sipariş/bayi bağlamı | CRM `new_siparisBase` (sipariş no), `AccountBase.new_logicalref` → Logo `CLCARD` | Bağlar ölçülmüş (%98,6) | Yalnız yetkiliye |
| Yönlendirme hedefleri | Portal kişi rehberi (`people.py`: CRM ∩ AD, 130 kişi, birim = AD OU), CRM ekip üyeliği | Hazır | Birim ↔ tür eşlemesi kullanıcı girer |
| Yönlendirme tablosu, şablon, SLA | Kullanıcı girer (portal tabloları) | Yok | İş tanımı «Excel/JSON tanım dosyası» diyor; portalda ekran olarak yapılır |
| CRM şablonları | `TemplateBase` (27), `new_emailsablonBase` (11), `new_mailiceriksablonuBase` (3) | Şema biliniyor | İçerik ve güncellik ölçülecek; başlangıç şablonu olabilir |
| İK sistemi | Bilinmiyor | — | Sorulacak |
| Şikâyet kaydı | CRM `IncidentBase` (34, kullanılmıyor) | — | CRM'e yazma yok → portal kaydı + «CRM'e işlenecek» listesi |
| Gönderilen yanıtlar | Kutunun gönderilmiş öğeleri (zincir) | — | Yanıt süresi zincirden hesaplanır |

## 7. Diğer modüllerle bağ

- **Çıktı verir:**
  - M1 / yazar giriş süreci: e-postayla gelen dosya başvurusu (yazar, eser adı, tür, ekler) «gelen başvurular»
    listesine; proje kartı CRM'de insan tarafından açılır.
  - M55 İK: iş başvuruları (İK sistemi netleşince).
  - M51 müşteri hizmetleri: şikâyet/soru kayıtları, SLA ve tekrarlayan konu analizi — H4 bu modülün e-posta kanalıdır.
  - M20 basın ve halkla ilişkiler, M28 kurumsal ilişkiler: basın, bağış, sponsorluk talepleri.
  - M8 serbest çalışanlar: dış kişiden gelen yanıtların otomatik kaydı (bugün elle).
- **Girdi alır:** CRM (gönderen tanıma, proje, sipariş), kişi rehberi (yönlendirme), H2 okur kartı (gönderen okur mu),
  M6 sözleşmeler (telif/izin talepleri — varsayım: yurt dışı yayınevi yazışmaları da bu kutuya geliyor olabilir).

## 8. Kısıtlar

- **CRM'e yazma yok:** iş tanımındaki «CRM'de görev kaydı oluşturulur», «müşteri kartına kaydedilir», «M1 tetiklenir
  (proje kartı oluşturulur)» adımları portalın kendi tablolarında yapılır; CRM'e işlenecekler liste olarak verilir.
- **Posta kutusunda en az yetki:** ilk sürüm okuma + etiket; «taşıma» kutunun kendi etiket/arşivi ile, silme yok.
  Gönderme yetkisi ayrı ve sonra; dışarıya giden her ileti insan onaylı ya da yönetici açmış «alındı» şablonu.
- **Mesaj gönderimi Timaş adına dış kişiye gider:** otomatik yanıt yalnız pilot sonrası, tür bazında, yönetici açar.
- **KVKK:**
  - Kutu kişisel veri içerir; iş başvuruları özel nitelikli veri (sağlık, din vb.) içerebilir → yalnız İK görür, gövde
    portalda saklanmaz (kutudan anlık okunur), özet ve sınıf saklanır; saklama süresi İK politikasına bağlanır.
  - Modele giden gövde yalnız sınıflama/özet/taslak için; model yerel (şirket dışına çıkmaz). Model kayıtlarında
    (istem günlüğü) ileti metninin tutulma süresi kısaltılmalı (varsayım: LLM kapısı istemi günlüğe yazıyor; kontrol).
  - Gönderene aydınlatma: otomatik yanıt şablonunda KVKK bilgilendirme bağlantısı (hukuk metni).
- **Ekranda teknoloji adı yok:** «Zeki AI». Posta sağlayıcısının adı (Google Workspace) yalnız Bağlantı ekranında
  müşteri platformu olarak kalabilir.
- **Demo veri yok, sayı tavanı yok:** bütün kutu okunur; geçmiş için başlangıç tarihi ayarı (sayı değil tarih).
- **İlk okuma dikkatli:** geçmiş iletilere otomatik yanıt ya da hatırlatma üretilmez; yalnız başlangıç tarihinden sonra
  gelenler işlenir.

## 9. Kapsam önerisi

**İlk sürüm**
- Kutu bağlantısı (okuma + etiket), gönderen tanıma (CRM), konu zinciri.
- Tür + öncelik + sorumlu önerisi (olasılıkla), «emin olunmayan» kuyruğu; insan ataması.
- Durum takibi (yeni → atandı → yanıtlandı → kapandı), SLA sayacı, 24/48/72 saat hatırlatma ve eskalasyon (iç bildirim).
- Yanıt taslağı (şablon + Zeki), gönderim kutunun kendi arayüzünden («Kutuda aç»).
- Dosya başvurusunu yazar giriş sürecine aktarma (portal kaydı).
- Rapor: hacim, yanıt süresi, SLA uyumu.
- Kurallar ekranı (yönlendirme, şablon, SLA) taslak/onay.
- Geçmiş ileti etiketleme ekranı (doğruluk ölçümü için).

**Sonraki sürüm**
- Portal içinden gönderim (ayrı yetki), «alındı» otomatik yanıtı (tür bazında).
- Olasılığı yüksek türlerde otomatik atama (K1).
- İK sistemine aktarım; M51 ile birleşik destek ekranı.
- Serbest çalışan ve yazar yazışmalarının kendi kayıtlarına bağlanması (M7, M8).
- Başka kurumsal kutular (ör. basın@, siparis@) — varsa.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/admin.py` — ayarlar (`admin.conf`, gizli alanlar), `audit`; kutu bağlantı bilgisi burada
  tutulur (Yönetim ekranından kullanıcı girer, repoya yazılmaz).
- `backend/semantic_bridge/alerts.py` / `budget_api.py` — iç bildirim e-postası (`smtp_settings`).
- `backend/semantic_bridge/people.py` — atanabilir kişiler ve birimler.
- `backend/semantic_bridge/editorial_intake.py` — yazar giriş süreci; «e-postayla gelen başvurular» bağlantısı.
- `backend/semantic_bridge/freelance.py` — dış kişiye ileti ve yanıt kaydı deseni.
- `src/canvas/editorial/MyTasksScreen.tsx` — «bana atanan işler» ekran deseni.
- `backend/semantic_bridge/reports.py` — haftalık rapor.

## 10. Uzmanlara sorulacak sorular

1. timas@ kutusu hangi sistemde (Google Workspace mı), bugün kim okuyor, günde kaç ileti geliyor?
2. Kutuya hangi türler geliyor; iş tanımındaki beş türe ek olarak sipariş/kargo, bayi, basın, telif/izin talebi,
   fatura gibi türler var mı? Tür → birim → kişi eşlemesini kim onaylar?
3. İş başvuruları için İK hangi sistemi kullanıyor; başvurular portalda tutulabilir mi, saklama süresi ne?
4. Dışarıya giden yanıt kimin adına ve hangi adresten gitmeli (timas@ mi, kişinin kendi adresi mi)?
5. Hangi türlerde otomatik «alındı» yanıtı istenir; metni kim onaylar (hukuk dahil)?

## 11. Başarı ölçütü

- Sınıflandırma doğruluğu: etiketli geçmiş örnekte ≥ %90 (iş tanımı hedefi); «emin olunmayan» payı haftalık izlenir.
- İlk yanıt süresi ve SLA uyumu (kategori bazında; başlangıç değeri ilk ay ölçülür).
- Cevapsız kalan ileti sayısı (72 saati aşan) → sıfıra yakın.
- Genel kutu sorumlusunun kutuya harcadığı süre (öncesi/sonrası, kendi beyanı + atama süresi).
- Dosya başvurularının yazar giriş sürecine aktarılma oranı ve süresi.
- Yanlış otomatik yanıt sayısı = 0.

---

## 12. Uzman gözüyle en iyi sistem

Bakış açısı: 15 yıllık müşteri hizmetleri ve kurumsal iletişim müdürü (paylaşılan kutu ve çağrı merkezi yönetmiş).

**Sektörde iyi örnekler.** İyi ekipler genel kutuyu «paylaşılan gelen kutusu» olarak yönetir: her ileti bir iş kaydıdır,
bir sahibi, durumu ve süresi vardır; iki kişi aynı iletiye aynı anda yanıt yazmaz (çakışma uyarısı); hazır yanıtlar
(makrolar) kategori bazındadır ve düzenlenebilir; SLA iş saatleriyle hesaplanır; haftalık raporda tekrarlayan konular
ürün ve süreç ekiplerine gider. Yardım masası ve paylaşılan kutu yazılımları bu işte olgundur; ortak ilkeleri tek
liste, atama, süre, şablon ve rapordur. Otomatik sınıflama bu yazılımlarda önce öneri olarak açılır, doğruluğu
ölçüldükçe otomatik atamaya geçilir.

**TİMAŞ için mükemmel sistem.** Kutu portalın içinde bir iş listesi gibi görünür; her ileti türü ve sorumlusuyla
gelir; dosya başvurusu tek tıkla yazar giriş sürecine düşer; şikâyetin yanında gönderenin CRM kaydı ve varsa siparişi
durur; SLA süresi dolmadan kişiye, dolunca yöneticisine haber gider; dışarı giden her ileti ya insan eliyle ya da
yönetimin onayladığı «alındı» şablonuyla gider; haftalık raporda hangi konuların arttığı yazar.

**Bir iş günü (kurumsal iletişim / genel kutu müdürü):**
- 08:45 «Atanmamış» sekmesi: Zeki'nin önerisi güvenli olanları iki tıkla atar; «Emin olunmayan» sekmesindeki
  iletilere tek tek bakar, türünü düzeltir (düzeltme kayda geçer).
- 09:30 Spam arşivine göz atar; yanlış arşivlenen bir basın davetini geri alır.
- 11:00 Bir okurun kargo şikâyeti: CRM'de okur kartı, sipariş numarası; hazır yanıt taslağını düzenleyip gönderir.
- 13:30 Bildirim: editöryaya atanan bir başvuru 48 saati geçti; editörya yöneticisine de gitti; telefonla hatırlatır.
- 15:00 Bağış talebi: kurumsal iletişime atar; şablonla «talebiniz ilgili birime iletildi» yanıtı.
- 17:00 Haftalık rapor taslağı: şikâyetlerde kargo konusu artmış; lojistiğe iletir.

**«Bunu görürsem hemen kullanırım»**
1. Tek liste: bana atanan + SLA'ya kalan süre + Zeki'nin iki cümlelik özeti.
2. Önerilen tür/sorumlu ile tek tık atama; emin olunmayanların ayrı sekmede olması.
3. Dosya başvurusunu eklerle yazar giriş sürecine tek tıkla aktarma.

**«Bunu yaparsanız kullanmam»**
1. Yanlış sınıflanan iletiye otomatik yanıt gitmesi (şikâyete «başvurunuz alındı»).
2. İletilerin kutudan taşınıp kaybolması ya da portal ile kutunun iki ayrı gerçek olması (kutuda cevaplanan portalda
   «bekliyor» görünmesi).
3. Herkesin özgeçmişleri ve şikâyetleri görebilmesi.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kutudan okuma, zincir | — | — | — | Deterministik |
| Gönderen tanıma | — | `ContactBase.EMailAddress1`, `AccountBase.EMailAddress1`, `LeadBase.EMailAddress1`; kişinin yazar mı (eser katılımı), bayi mi (FirmaKanal), okur mu | — | Tam eşleşme SQL |
| Spam / tanıtım | — | — | Kutunun kendi spam işareti ve gönderen listesi önce; kalanlarda «spam/tanıtım mı» tek token + olasılık | Model yalnız kuralın çözemediğinde |
| Tür sınıflandırma | — | — | Yürürlükteki tür listesinden (A, B, C… harf etiketli) **tek token + olasılık**; marj düşükse «emin olunmayan» | Kapalı küme, ölçülebilir güven |
| Öncelik | — | Gönderen türü (yazar/bayi/okur) bağlam | Kapalı küme (yüksek/normal/düşük) | Sınıflama |
| Özet | — | — | 1–2 cümle Türkçe özet (yabancı dildeki iletide çeviri özeti) | Okuma süresini kısaltır |
| Başvuru bilgisi çıkarma | — | `new_projeBase` (yazar kişisi, yakın tarihli projeler) | Yazar adı, eser adı, tür, sayfa tahmini alanlarını çıkarır (her değer metinde birebir aranır, bulunmayan düşer); proje eşleşmesi önerisi kapalı küme | Yapılandırma |
| Sipariş/bayi bağlamı | `CLCARD` (açık bakiye, son hareket — yalnız yetkili, ör. muhasebe sorusu) | `new_siparisBase` (metindeki sipariş no), `AccountBase.new_logicalref` | Metinden sipariş no çıkarma (desenle; model yalnız desen yoksa) | Rakam SQL'den |
| Yanıt taslağı | — | Şablonlar (portal; başlangıçta CRM şablonlarından) | Şablon + iletiye özgü taslak; söz verme/tarih verme yasak listesi (yalnız şablondaki süre) | Metin üretimi gerçek değer |
| Rapor yorumu | — | — | Haftalık hacim/yanıt süresi yorumu (rakamlar SQL'den) | Yorum |

Model çağrıları: yeni ileti sınıflaması `rt.llm_for("mailbox", NORMAL)` (kuyrukta etkileşimli işlerin arkasında),
taslak `rt.llm_for("mailbox")` (etkileşimli), toplu geçmiş etiket önerisi `BATCH`. Kapalı küme `QueuedLlm.choose()`
(H1'de tanımlanan ortak iş). İş başvurusu metni modele yalnız tür/özet için gider; özet İK dışında gösterilmez.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/mailbox.py` — depo, durum makinesi, SLA hesabı (iş saatleri takvimi ayarda).
- `backend/semantic_bridge/mailbox_sources.py` — kutu bağlantısı: Gmail API (alan geneli yetki devri, tek kutuya
  sınırlı kapsam: okuma + etiket; gönderme ayrı sürüm) ya da IMAP + OAuth2; artımlı okuma (geçmiş kimliği / UID),
  zincir; CRM gönderen tanıma sorguları. Bağlantı bilgisi `admin.conf` (Yönetim ekranı, gizli alan).
- `backend/semantic_bridge/mailbox_classify.py` — sınıflama, öncelik, özet, başvuru alanı çıkarma, taslak.
- `backend/semantic_bridge/mailbox_api.py` — `register(app, rt, require_caller, can)`.

**Tablolar (bi_meta; `tenant_id`)**
- `semantic_mail_messages` — `id`, `provider_id`, `thread_id`, `received_at`, `from_addr_hash`, `from_display` (ad,
  maskeli gösterim için), `subject`, `summary`, `category`, `category_prob`, `category_source` (model|kural|insan),
  `priority`, `status` (yeni|atandi|yanitlandi|kapandi|arsiv), `assignee`, `unit`, `due_at`, `first_reply_at`,
  `closed_at`, `crm_contact_id`, `crm_account_id`, `crm_project_id`, `is_hr` (bayrak). Gövde ve ek saklanmaz (kutudan
  anlık).
- `semantic_mail_events` — `message_id`, `action` (siniflandi|atandi|tur-duzeltildi|yanitlandi|hatirlatma|eskalasyon|
  kapandi|arsivlendi|aktarildi), `by`, `at`, `detail_json` (tür düzeltmeleri aynı zamanda doğruluk ölçüm verisi).
- `semantic_mail_categories` — `key`, `label`, `enabled`, `auto_reply_enabled`, `hr_only`, `sort` (tür listesi koda
  gömülmez).
- `semantic_mail_routes` — `version`, `category_key`, `unit`, `primary_user`, `backup_user`, `status` (taslak|onayli|
  arsiv), `approved_by`.
- `semantic_mail_templates` — `id`, `category_key`, `name`, `body`, `version`, `status`, `approved_by`.
- `semantic_mail_sla` — `category_key`, `remind_h` (24), `escalate_h` (48), `top_h` (72), `business_hours_json`.
- `semantic_mail_applications` — `message_id`, `author_name`, `work_title`, `genre`, `attachments_json` (ad/boyut),
  `status` (yeni|aktarildi|reddedildi), `intake_ref` (yazar giriş süreci kaydı), `crm_project_id` (insan eşlerse).
- `semantic_mail_labels` — geçmiş ileti etiketleme ekranının kayıtları (`message_id`, `category_key`, `by`, `at`).

**Uçlar (`/api/v1/mailbox/*`)**
- `GET overview` · `GET messages?view=mine|unit|unassigned|unsure|overdue|archive` · `GET messages/{id}` (gövde
  kutudan anlık; İK iletisi yalnız `ozellik:eposta.ik`).
- `POST messages/{id}/assign` · `POST messages/{id}/category` · `POST messages/{id}/status` ·
  `POST messages/{id}/draft` (Zeki taslağı) · `POST messages/{id}/send` (sonraki sürüm; açıkça verilen yetki) ·
  `POST messages/{id}/to-intake` (başvuruyu aktar).
- `GET report?period=`.
- `GET rules` · `PUT rules` (taslak: tür, yönlendirme, SLA, şablon) · `POST rules/approve`.
- `GET labeling` · `POST labeling/{message_id}` (geçmiş etiketleme).
- `GET connection` (durum).
- `POST run-due` (SİSTEM: yeni iletileri çek + sınıfla) · `POST sla-due` (SİSTEM: hatırlatma/eskalasyon).
- Sözleşme uçları: `GET applications?status=new` (yazar giriş süreci ekranı okur).

**Ekranlar** `src/canvas/mailbox/`: `MailboxHome.tsx` (liste, sekmeler), `MessageDetail.tsx`, `MailReport.tsx`,
`MailRules.tsx`, `Labeling.tsx`, `api.ts`. Rota `/timas/kurumsal-eposta` (+ `/kurumsal-eposta/ileti/:id`, `/rapor`,
`/kurallar`, `/etiketleme`). Menü: «Kayıtlar» alanı, öğe `{ id: 'kurumsal-eposta', label: 'Kurumsal e-posta', to:
'/kurumsal-eposta', hint: 'Genel kutuya gelen iletiler, atama ve yanıt süreleri', badge: 'mailbox' }` (bana atanan ve
süresi aşan sayısı). Kampüs: zilde «bana atanan ileti», modül kutusu. Yazar giriş süreci panosuna «e-postayla gelen
başvurular» kutusu (sözleşme ucu).

**Yetki**
- `sayfa:kurumsal-eposta`; `RULES`: `("/api/v1/mailbox/run-due", SYSTEM)`, `("/api/v1/mailbox/sla-due", SYSTEM)`,
  `("/api/v1/mailbox/applications", frozenset({page("kurumsal-eposta"), page("yazar-giris")}))`,
  `("/api/v1/mailbox/", frozenset({page("kurumsal-eposta")}))`.
- Özellik (`FEATURE_RULES`): `ozellik:eposta.ata` (assign, category, status, to-intake), `ozellik:eposta.kural`
  (PUT rules), `ozellik:eposta.herkesinki` (kapsam). Açıkça verilen (uç içinde): `ozellik:eposta.yanitla`,
  `ozellik:eposta.ik`, `ozellik:eposta.kural-onay`, `ozellik:eposta.otomatik-yanit`.

**Zamanlayıcı**
- `scripts/server/timas-mailbox.{service,timer}` — her 5 dakikada `POST /api/v1/mailbox/run-due`: yeni iletileri
  artımlı okur, gönderen tanır, sınıflar, önerir; bağlantı hatasını kaydeder.
- `scripts/server/timas-mailbox-sla.{service,timer}` — saatte bir `POST /api/v1/mailbox/sla-due`: iş saatleriyle SLA,
  hatırlatma/eskalasyon (iç bildirim).
- İlk çalıştırma elle yapılır (bellek: «zamanlı işi önce elle koştur»); başlangıç tarihi ayarından önceki iletilere
  bildirim üretilmez.

**Kabul testleri**
1. Hacim: kutuda son 7 günün ileti sayısı (sağlayıcı API'sinin sayımı, örn. Gmail `newer_than:7d`) = `SELECT COUNT(*)
   FROM semantic_mail_messages WHERE received_at >= now() - interval '7 days'` (kutu etiketi «spam» olanlar dahil/hariç
   aynı tanımla).
2. Gönderen tanıma: rastgele 30 ileti için `SELECT ContactId FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0 AND
   LOWER(LTRIM(RTRIM(EMailAddress1))) = LOWER(:adres)` (ve `AccountBase`, `LeadBase` aynı biçimde) sonucu ile ekrandaki
   «CRM kişisi/firma/aday» rozeti birebir.
3. Yönlendirme hedefleri geçerli: yürürlükteki `semantic_mail_routes` içindeki her kişi için `SELECT COUNT(*) FROM
   Timas_MSCRM.dbo.SystemUserBase WHERE IsDisabled = 0 AND DomainName = 'timas\' + :hesap` = 1 ve kişi rehberinde (AD
   etkin) var.
4. SLA raporu: `SELECT category, AVG(EXTRACT(EPOCH FROM (first_reply_at - received_at))/3600) FROM
   semantic_mail_messages WHERE received_at >= :bas AND first_reply_at IS NOT NULL GROUP BY category` (iş saati düzeltmesi
   ayrıca) = rapor ekranındaki ortalama; `first_reply_at` kutudaki gönderilmiş zincirle 10 örnekte elle doğrulanır.
5. Sınıflandırma doğruluğu: insan etiketli geçmiş örnekte (`semantic_mail_labels`) model sınıfı = insan sınıfı oranı ≥
   %90 (iş tanımı); tür bazında karışıklık tablosu raporlanır. Oran tutmazsa otomatik atama açılmaz.
6. İK gizliliği: `ozellik:eposta.ik` olmayan oturumla `GET messages/{id}` (İK iletisi) → 403; liste uçlarında İK
   iletileri görünmez (test kullanıcısıyla, kısa oturum).
7. Otomatik yanıt güvenliği: `auto_reply_enabled = false` olan türlerde `semantic_mail_events`'te hiç `yanitlandi`
   (by = sistem) kaydı yok (SQL = 0).
8. Başvuru aktarımı: aktarılan her ileti için `semantic_mail_applications.status = 'aktarildi'` ve yazar giriş süreci
   ekranında aynı kayıt görünür; CRM'de proje açıldığında `SELECT new_projeId FROM Timas_MSCRM.dbo.new_projeBase WHERE
   new_projeId = :crm_project_id` bağı doğrulanır.

**Bağımlılık**
- Engelleyici: BT'den kutu türü ve erişim yetkisi (servis hesabı, kapsam); İK sistemi kararı (iş başvurusu kısmı için).
- Önce: `QueuedLlm.choose()` (H1'de tanımlı ortak iş). Geçmiş iletilerin etiketlenmesi (insan işi) sınıflama
  doğruluğu ölçülmeden otomatik atama açılmaz.
- H1–H3'ten bağımsız, paralel kodlanabilir. M1 yazar giriş süreci var (bağlantı ucu eklenir). H2 hazırsa gönderen okur
  kartı eklenir (sonraki sürüm).

**Tahmini büyüklük:** L. Parçalar: kutu bağlantısı + artımlı okuma + zincir M; gönderen tanıma S; sınıflama + özet +
başvuru çıkarma M; durum/atama/SLA + zamanlayıcılar M; ekranlar (liste, ayrıntı, rapor, kurallar, etiketleme) L;
yazar giriş süreci bağlantısı S.
