# M51 — Müşteri Hizmetleri ve Destek Yönetimi: kullanıcı ihtiyaç analizi

Durum: kod var (main) — köprü katmanı (main), talep kaydı TİMAŞ destek masası (`apps/destek`); test sunucusunda kabul bekliyor · Analiz tarihi:
2026-09-28 · Kaynaklar: iş tanımı `specs/M51.txt`, ilgili iş tanımları `specs/Kurumsal_E_posta_Yönetimi.txt`,
`E_Ticaret_Müşteri_Yönetimi_Ent.txt`, `Okuyucu_Veri_Tabanı_Entegrasyo.txt`, Veri Haritası (`veri_haritasi2.txt`: «Destek
Girdileri», «Kalite Girdileri»), `scratchpad/crm_tables.txt` (CRM tablo satır sayıları; çağıran oturumun dökümü, ölçüm
tarihi belgede yok), `configs/semantic/knowledge/logo/knowledge/rules/crm-timas.md` (Kural C13 sipariş, C15 talep yönetimi,
C19 kargo), `rules/logo-erp.md` (Kural 8, 10, 18, 19), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `backend/semantic_bridge/seo_geo/reviews.py` (T-soft yorum okuması),
helpdesk dalı (salt okundu): `.claude/worktrees/nanobaseai-helpdesk-flow-module-f7c001/apps/destek/README.md`,
`frappe-apps/helpdesk/.../doctype/hd_ticket/hd_ticket.json` ve doctype listesi, `deploy/nginx-destek-8446.conf`,
`scripts/install.sh`; bellek: `logo-155-frozen-copy`, `timas-crm-prod-28`, `tsoft-no-write`, `crm-tsoft-no-push-integration`,
`customer-vm-web-watch-off`, `llm-gate`, `no-tech-names-on-screens`, `chat-persona-zeki-ai`. Sunucuya bağlanılmadı.

## 1. Modül ne işe yarar

Müşteriden (okur / e-ticaret alıcısı, kitapçı-bayi, kurum, B2B web kullanıcısı) gelen her talebi tek kayıtta toplar,
konusunu ve aciliyetini belirler, benzer sorunun hazır cevabını önerir, çözüm süresini (SLA) izler ve çözümsüz kalanı
yukarı taşır (K1). Kalite tarafında memnuniyeti, tekrarlayan şikâyet konularını ve «müşteri kendi bulabilirdi» dediğimiz
self-servis içerik açıklarını çıkarır; kural dışı durumlar ve öncelikli müşteri aksiyonları temsilci/yönetici onayıyla
yürür (K2).

TİMAŞ'ın bugünkü durumu (kanıtla): Dynamics CRM'in hazır servis modülü fiilen kullanılmıyor — `IncidentBase` (Servis
Talebi) 34, `KnowledgeArticleBase` 24, `new_satisdestekBase` (Satış Destek) 25, anket tabloları 1–21 satır
(`crm_tables.txt`). İç BT talep kaydı (`new_talepyonetimiBase`, 354) 2024-07'den beri değişmiyor. Kurumsal e-posta iş
tanımına göre şikâyet/soru/destek talepleri genel kutuya (`timas@timas.com.tr`) düşüyor ve elle dağıtılıyor (iş tanımı;
bugünkü hacim **ölçülecek**). Buna karşılık bir müşterinin en sık sorusunun cevabı CRM'de canlı duruyor: sipariş durumu
(`new_siparisBase` 333.063, durum kodları Kural C13), sevkiyat (286.601), kargo takip (10.688) — .28 canlı CRM.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Müşteri hizmetleri temsilcisi (okur / e-ticaret) | **Varsayım**: e-ticaret operasyonu ya da Satış altında; CRM TeamMembership'te ayrı müşteri hizmetleri takımı görünmüyor (Editörya 54, Satış 49, Pazarlama 35, Grafik 13, Mali İşler 10) | Gün boyu | Masaüstü (çift ekran) |
| Bayi / kurum satış destek sorumlusu | Satış (CRM «Satış Destek» varlığı ve B2B web kullanıcıları 5.057 — kanıt: `crm_tables.txt`, `crm-timas-mscrm-detay` §102) | Gün boyu | Masaüstü; sahada telefon |
| Müşteri hizmetleri / e-ticaret yöneticisi | **Varsayım** | Günlük pano, haftalık kalite | Masaüstü; özet telefonda |
| Genel e-posta kutusunu dağıtan kişi | İdari işler / sekreterya (**varsayım**; Kurumsal e-posta iş tanımı) | Gün boyu | Masaüstü |
| Konu uzmanları (çözüm için topu alanlar) | Depo/sevkiyat, Muhasebe (fatura/iade), Editörya/Üretim (baskı-içerik hatası), BT (e-kitap/erişim) | Kendisine düşen talep geldikçe | Her ikisi |
| Sosyal medya uzmanı | Pazarlama (M22) | Günlük | Her ikisi |

## 3. Bugün bu iş nasıl yapılıyor

- **Temsilci:** talep e-posta, telefon, site formu ya da sosyal medyadan gelir (**varsayım**, iş tanımındaki kanal listesi).
  Sipariş durumunu sormak için CRM'de sipariş kartını, kargo için kargo firmasının sitesini, fatura/iade için muhasebeyi
  arar (**varsayım**; adım sayısı ve süre ölçülmedi). Hazır cevap şablonu CRM'de `new_emailsablonBase` 11 kayıt.
  Tıkanma: talep kaydı ve süre ölçümü yok; aynı müşterinin önceki talebi görünmüyor.
- **Bayi/kurum satış destek:** siparişin risk limiti onayı, bekleyen adet, sevk durumu CRM'de (Kural C13: «Risk Limit Onayı
  Bekliyor», «Depoda Bekliyor», «Kutulanıyor»); bayi telefonla sorar, satış destek CRM'e bakıp döner (**varsayım**).
- **Genel e-posta kutusu:** Kurumsal e-posta iş tanımında gelen kutusunda dosya başvurusu, iş başvurusu, şikâyet/soru,
  bağış/sponsorluk, reklam/spam karışık; yönlendirme tablosu ve SLA kuralı «kurulacak» durumda. Portalda e-posta
  kutusuna bağlantı yok (depoda Microsoft Graph/IMAP entegrasyonu bulunmadı).
- **Yönetici:** memnuniyet ve çözüm süresi ölçülmüyor; CRM anket modülü neredeyse boş.
- **Okur yorumları:** SEO modülü T-soft yorumlarını gece okuyor ama yalnız ürün başına sayı ve puan dağılımı saklıyor;
  yorum metni hiç saklanmıyor (`reviews.py`, KVKK kararı) → şikâyet içeren yorumlar görünmüyor.
- **Helpdesk dalı (başka oturum, yazılıyor):** `apps/destek` — BI'dan ayrı bir destek masası (talep kaydı, tür, öncelik,
  durum, SLA, ekip, hazır cevap, bilgi bankası, müşteri portalı, e-posta geri bildirimi/memnuniyet, raporlar) + masaüstünde
  yapay zekâ paneli; test sunucusunda ayrı portta (`:8446`), kendi kullanıcılarıyla (AD'ye bağlı değil), müşteri VM'ine
  kurulmadı, yapay zekâ paneli LLM kapısını atlıyor (README «Açık işler»).

## 4. İhtiyaçlar ve acı noktaları

**Temsilci**
1. Talebin yanında müşterinin bağlamı, tek ekranda: siparişleri ve durumu, kargo takip, son faturalar/iadeler, önceki talepleri.
2. Hazır ve doğru cevap önerisi (SSS eşleşmesi) — kendi sözüyle düzeltip gönderebileceği taslak.
3. Konu ve aciliyetin kendiliğinden belirlenmesi, doğru kişiye yönlendirme.
4. Aynı müşteriden aynı konuda ikinci talep geldiğinde uyarı.

**Bayi/kurum satış destek**
1. Bayi adına tek bakışta: açık siparişler, bekleyen adet, risk limiti onayı bekleyenler, son sevkiyatlar ve kargo.
2. Bayi talebinin (eksik gelen koli, hasarlı ürün, fatura farkı) iadeye/muhasebeye düzgün devri.

**Yönetici**
1. Açık talep ve SLA durumu; ortalama ilk yanıt ve çözüm süresi eğilimi.
2. En sık şikâyet konuları ve kök nedeni (kargo firması, depo, baskı hatası, site).
3. Memnuniyet (CSAT) eğilimi ve düşüş uyarısı.
4. Self-servis açığı: «sitede cevabı olsa gelmeyecekti» talep oranı ve yazılması gereken SSS listesi.

**Konu uzmanları**
1. Kendisine düşen talebi, müşterinin bağlamıyla birlikte ve SLA süresiyle görmek.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Temsilci olarak bir e-posta talebini açtığımda müşterinin son siparişlerini ve kargo durumunu yanında görmek istiyorum, çünkü bugün üç sisteme bakıyorum.
- Temsilci olarak Zeki AI'ın önerdiği cevabı düzeltip göndermek istiyorum, çünkü aynı soruyu günde onlarca kez yazıyorum.
- Temsilci olarak talebin konusu ve aciliyeti kendiliğinden gelsin istiyorum, çünkü sınıflamak zaman alıyor ve tutarsız oluyor.
- Satış destek olarak bir bayinin açık siparişlerini, bekleyen adetleri ve risk limiti onayı bekleyenleri tek listede görmek istiyorum, çünkü bayi telefonda bekliyor.
- Yönetici olarak SLA'sı dolmak üzere olan talepleri görmek istiyorum, çünkü müşteriyi kaybetmeden müdahale etmeliyim.
- Yönetici olarak bu ayın en sık 10 şikâyet konusunu ve geçen aya göre değişimini görmek istiyorum, çünkü kargo firması ya da depo ile konuşacağım.
- Yönetici olarak cevabı sitede olsaydı gelmeyecek talepleri ve önerilen SSS metnini görmek istiyorum, çünkü talep sayısını azaltmak istiyorum.
- Konu uzmanı (depo) olarak bana devredilen hasarlı ürün taleplerini sipariş ve sevkiyat bilgisiyle görmek istiyorum, çünkü tekrar sormak istemiyorum.

**Ana ekranlar ve akış**
- Temsilci ekranı (talep kaydı): talep listesi (SLA'ya göre sıralı), talep ayrıntısı ve sağda **«Müşteri bağlamı»** paneli
  (CRM kişi/cari eşleşmesi, siparişler ve durumu, kargo takip, Logo'dan son fatura/iade — veri sonu tarihiyle, önceki
  talepler) + **«Zeki AI önerisi»** (konu, aciliyet, benzer SSS, cevap taslağı).
- Portal ekranı `/timas/musteri-destek` (yönetici ve satış destek): Özet (açık, SLA'sı yaklaşan, bugün çözülen, ilk yanıt
  ve çözüm süresi medyanı, CSAT), Konular (sınıf sayısı ve eğilimi, kök neden kırılımı), Bayi görünümü (bayi seç →
  açık sipariş, bekleyen, risk onayı, sevkiyat, kargo, talepler), Bilgi bankası açıkları.
- En sık 3 işlem: (1) talebi açıp bağlamı görmek — 1 tık (bağlam kendiliğinden yüklenir); (2) öneriyi düzeltip göndermek —
  2 tık; (3) uzmana devretmek — 2 tık (kişi/ekip seç).

**Zeki AI'ya soracakları örnek sorular**
- «TS-240915 numaralı siparişin durumu ne, kargoya verildi mi?»
- «Bu bayinin risk limiti onayı bekleyen kaç siparişi var?»
- «Bu hafta en çok hangi konuda şikâyet geldi?»
- «Hasarlı ürün şikâyetleri hangi kargo firmasında yoğunlaşıyor?»
- «SLA'sı bugün dolacak kaç talep var, kimde?»
- «Geçen aya göre ilk yanıt süremiz nasıl?»
- «Hangi SSS maddesini yazarsak en çok talep azalır?»
(Sipariş/kargo soruları CRM ve Logo'ya giden veri sorularıdır; kişi bazında cevap yalnız sayfa + veri alanı yetkisi
olan temsilciye döner — Aşama C veri alanları `satis`, `cari`.)

**Otomasyon katmanı**
- K1: kanaldan talep açılması (e-posta kutusu, form), konu + aciliyet sınıflaması, müşteri eşleştirmesi (e-posta → CRM
  kişi/cari), bağlam toplanması, SSS eşleştirmesi, SLA sayacı ve aşım uyarısı, çözümsüz kalan talebin yukarı taşınması,
  tekrarlayan konu sayımı.
- K2: cevap taslağı (temsilci gönderir), yeni SSS maddesi taslağı (yönetici onaylar; siteye yayını T-soft'a yazma yasağı
  nedeniyle elle), kural dışı durumlar (iade süresi aşımı, öncelikli müşteri/kurum talebi, tazminat/ücretsiz gönderim)
  → yönetici onayı.
- K3: kök neden raporu (kargo firması değişikliği, depo süreci) → yönetim kararı.

**Bildirim/uyarı**
- Yeni talep atandı: atanan kişi, ekranda + e-posta (isteğe göre).
- SLA'nın %80'i doldu: atanan kişi + ekip lideri; SLA aşıldı: yönetici.
- Aynı müşteriden 7 gün içinde ikinci talep: atanan kişi (talep kartında uyarı).
- Haftalık kalite özeti: yönetici, pazartesi.
- Günlük CSAT düşüşü (7 günlük ortalama eşik altı): yönetici.

**Onay ve yetki**
- `sayfa:musteri-destek` — yönetici, satış destek, temsilciler.
- `ozellik:destek.baglam` — müşteri bağlam panelini görmek (kişisel veri + sipariş); temsilci ve satış destek.
- `ozellik:destek.oneri` — Zeki AI cevap taslağı üretmek (model harcar).
- `ozellik:destek.kural-disi` (açıkça verilir) — kural dışı işlem onayı.
- `ozellik:destek.sss` (açıkça verilir) — SSS taslağını onaylamak.
- `ozellik:destek.herkesinki` (açıkça verilir) — başkasına atanmış talepleri görmek/devralmak (yönetici).
- Talep kaydı ekranının kendi yetkisi (helpdesk rolleri) ile portal rolleri eşleşmeli — §14 karar noktası.

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Talep kaydı (konu, durum, öncelik, SLA, atanan, ilk yanıt, çözüm, memnuniyet) | Helpdesk dalı (`HD Ticket`: `status`, `priority`, `ticket_type`, `agent_group`, `sla`, `response_by`, `resolution_by`, `first_responded_on`, `opening_date`, `resolution_date`, `feedback_rating`, `contact`, `customer`, `email_account`, `via_customer_portal`) | Dalda, test sunucusunda ayrı site; `main`'de değil | Kullanıma alınmadı; hacim yok |
| Genel e-posta kutusu | Microsoft 365 / Exchange (**varsayım**: iş tanımı Graph/IMAP diyor) | Entegrasyon yok | Kimlik bilgisi ve izin kapsamı (soru 2) |
| Site iletişim formu, sipariş notları | T-soft (salt okuma) | SEO modülü yalnız ürün/yorum okuyor | Form/sipariş API'si **ölçülecek**; yazma yasak |
| E-ticaret (B2C) siparişleri | T-soft ve/veya CRM | CRM `new_onlinesiparisBase` 68, `new_siparissatirlariBase` (Online Sipariş Satırları) 1.843 → B2C siparişlerin çoğu CRM'de değil gibi (**varsayım**) | T-soft sipariş okuması **ölçülecek** |
| Bayi/kurum siparişleri | CRM `new_siparisBase` (333.063; tip B2B/Pazaryeri/B2C/Okul…; durum Kural C13), `new_siparissatiriBase` (9,7 Mn) | Katalogda, kural yazılı | Sipariş numarası alanı adı **ölçülecek** |
| Sevkiyat ve kargo | CRM `new_sevkiyatBase` (286.601), `new_sevkiyatsatiriBase`, `new_kargobilgisiBase` (13.242, Kural C19), `new_kargotakipbilgisiBase` (10.688), `new_kargofirmasiBase` (11) | Kural C19 kargo bilgisi | Kargo takip ↔ sipariş bağ alanı **ölçülecek** |
| Fatura, iade | Logo `LG_411_01_INVOICE`, `STFICHE`/`STLINE` (satış iade TRCODE, Kural 10/18/19) | Katalogda | **.155 donmuş (son fatura 2026-08-17)**; canlı Logo .25'e okuma yok |
| Cari (bayi/kurum/pazaryeri) | Logo `CLCARD` (kanal `SPECODE2`, pazaryeri adı `DEFINITION_`), CRM `AccountBase` (47.550) | Katalogda | Bireysel okurun Logo'da cari olup olmadığı **ölçülecek** (**varsayım**: pazaryeri/e-ticaret satışları toplu caride) |
| Kişi (okur, bayi yetkilisi) | CRM `ContactBase` (59.637), `new_webuserBase` (5.057; şifre/token hassas) | Katalogda | E-posta ile eşleştirme kapsamı **ölçülecek** |
| Hazır cevap / SSS | CRM `new_emailsablonBase` (11), `KnowledgeArticleBase` (24); helpdesk `HD Article`, `HD Saved Reply` | Az ve güncelliği bilinmiyor | İçerik yazılacak (M51 K2 taslak üretir) |
| Memnuniyet | Helpdesk `feedback_rating`; CRM anket tabloları (~boş) | — | İlk sürümde helpdesk'ten |
| Okur yorum metni | T-soft `product/getComments` | Yalnız sayı/puan saklanıyor | Metin saklanmıyor (KVKK kararı); şikâyet madenciliği için karar gerekir (soru 4) |
| Sosyal medya mesajları | M22 / platform API'leri | Yok; müşteride web taraması kapalı | İlk sürüm dışı |
| Gömme (benzerlik) | Gömme servisi (CPU, `:8083`) | Var | SSS eşleşmesi için kullanılacak |

## 7. Diğer modüllerle bağ

- **Helpdesk dalı (`claude/nanobaseai-helpdesk-flow-module-f7c001`, `apps/destek`) — örtüşme:** talep kaydı, SLA, ekip,
  hazır cevap, bilgi bankası, müşteri portalı, memnuniyet ve temel raporlar orada. M51 bunları **yeniden yazmamalı**.
  Açık belirsizlik: dal her yerde «NanobaseAI» markalı; NanobaseAI'nin kendi müşterilerine (TİMAŞ kullanıcılarına) destek
  masası mı, yoksa TİMAŞ'ın okur/bayi müşteri hizmetleri masası mı olduğu README'de net değil (soru 1). M51'in TİMAŞ'a
  özgü katmanı (CRM/Logo/T-soft bağlamı, Zeki AI sınıflama/öneri LLM kapısından, portal kalite panosu, AD girişi) iki
  durumda da gerekli ve dalda yok.
- **M48 IT:** portal/site kesintisinde «bilinen sorun» notu M51 önerisine eklenir; M51'e düşen «sistem çalışmıyor» talepleri M48 olayına bağlanır.
- **M49 Güvenlik:** talep ve müşteri bağlamı kişisel veri; saklama süresi, ilgili kişi araması ve erişim kaydı M49'dan.
- **M50 Model:** sınıflama ve öneri isabeti M50 karnesinde bir satır; temsilcinin taslağı değiştirmeden gönderme oranı ölçü.
- **M22 Sosyal medya, M24 bülten, M37 okur topluluğu:** kanal ve okur profili; tekrarlayan şikâyet M37'ye girdi.
- **M12 Üretim / M5 Son okuma:** baskı/içerik hatası şikâyetleri kitap bazında üretim ve son okumaya geri bildirim.
- **M32 B2B, M59 Bayi risk:** bayi talepleri ve sipariş sorunları bayi performansına girdi.
- **Kurumsal e-posta yönetimi (ayrı iş tanımı):** genel kutunun sınıflaması aynı motorla; müşteri talebi sınıfına düşenler M51'e açılır.

## 8. Kısıtlar

- **T-soft'a yazma yasak** (bellek `tsoft-no-write`): SSS/ürün sayfası güncellemesi portaldan gönderilmez; onaylı metin kopyalanıp elle girilir.
- **CRM'e yazma yok:** talep, not, sınıf köprünün (ya da helpdesk'in) kendi tablolarında; CRM `IncidentBase`'e yazılmaz.
- Müşteride web taraması kapalı: sosyal medya/forum taraması yok; yalnız resmi, izinli API ve müşterinin açtığı kanallar.
- Ekranda teknoloji adı yok (helpdesk dalı zaten «NanobaseAI» markasıyla çıkıyor; portal tarafında «Zeki AI»).
- Demo veri yok: boş talep listesi boş görünür; örnek talep üretilmez.
- Sayı tavanı yok: talep ve sipariş listeleri sayfalı.
- Logo verisi donmuş (.155, son fatura 2026-08-17): bağlam panelinde Logo satırları her zaman «veri sonu» tarihiyle; canlı
  sayılmaz (bellek `logo-155-frozen-copy`). Sipariş/kargo durumu için canlı kaynak CRM .28'dir.
- **KVKK:** talep metni, e-posta, ad, adres, telefon kişisel veridir. Modele giden metin gerekli en az kısım olmalı (sınıflama
  için gövde, imza/adres satırı kırpılarak); saklama süresi M49 politikası; okur yorum metinlerini saklama kararı hukukla.
  Müşteri portalı (helpdesk) açılacaksa aydınlatma metni ve açık rıza gerekir (soru 5).
- Tüketici mevzuatı (iade/cayma süreleri) kural dışı durum eşiğidir; eşik değerleri kullanıcıdan (ayar), kodda sabit değil.
- Zeki AI sohbetinin bugünkü kapsamı yalnız finans (bellek `chat-persona-zeki-ai`): destek soruları için sohbet değil,
  modülün kendi soru yolu kullanılır.

## 9. Kapsam önerisi

**İlk sürüm (en çok değer, en az bağımlılık)** — talep kaydı çekirdeği helpdesk'te kalır:
- **Müşteri bağlamı ucu** (köprü): e-posta/telefon/sipariş no/cari kodu → CRM kişi/cari eşleşmesi, sipariş + durum,
  sevkiyat, kargo takip, Logo son fatura/iade (veri sonu tarihiyle). Yetki: sayfa + `ozellik:destek.baglam` + veri alanı.
- **Bayi görünümü** (portal ekranı): bayi seç → açık sipariş, bekleyen adet, risk limiti onayı bekleyen, sevkiyat, kargo.
- **Zeki AI sınıflama** (konu + aciliyet, LLM kapısı üzerinden, tek token + olasılık) ve **SSS eşleştirme** (gömme
  servisiyle benzerlik), **cevap taslağı** (K2).
- **Kalite panosu**: helpdesk verisinden açık/SLA/ilk yanıt/çözüm/CSAT ve konu eğilimi (salt okuma).

**Sonraki sürüm**
- Genel e-posta kutusu bağlantısı (Graph/IMAP) ve kutudan talep açma (Kurumsal e-posta iş tanımıyla ortak).
- Tekrarlayan şikâyet kümeleme ve kök neden raporu; self-servis açığı listesi + SSS taslağı.
- Helpdesk temsilci ekranına «Müşteri bağlamı» ve «Zeki AI önerisi» paneli (helpdesk dalı `main`'e girdikten sonra, o dalın sahibiyle).
- AD tek oturum (helpdesk LDAP) ve portal rolleriyle eşleme; müşteri VM'ine kurulum.
- T-soft sipariş/form okuması (API ölçüldükten sonra); okur yorum metni (hukuk kararıyla).

**Mevcut kodda yeniden kullanılacaklar**
- Katalog kuralları: `crm-timas.md` C13 (sipariş durumu, bekleyen), C19 (kargo), C14 (sevkiyat indirimi); `logo-erp.md` 8, 10, 18, 19.
- `backend/semantic_bridge/app.py` `Runtime._conn_for` (CRM/Logo yönlendirmesi), `run_sql` yolu (veri alanı kapısıyla).
- `backend/semantic_bridge/access.py` (sayfa/işlem/veri alanı), `data_domains.json` (`satis`, `cari`, `yayin-crm`).
- `backend/semantic_bridge/seo_geo/reviews.py` (T-soft okuma bağlantısı, `connections.tsoft`), `seo_geo/connections.py`.
- `backend/semantic_bridge/people.py` (CRM ∩ AD kişi eşleştirme deseni; burada müşteri tarafı için değil, temsilci/uzman listesi için).
- LLM kapısı `rt.llm_for`, `vllm` kapalı küme + olasılık yöntemi (bellek `vllm-choice-logprobs`), gömme servisi.
- Helpdesk dalı: `apps/destek` (talep kaydı, SLA, bilgi bankası, memnuniyet, raporlar) — salt okuma entegrasyonu.

## 10. Uzmanlara sorulacak sorular

1. `apps/destek` (helpdesk) TİMAŞ'ın okur/bayi müşteri hizmetleri masası mı olacak, yoksa NanobaseAI'nin TİMAŞ kullanıcılarına verdiği destek masası mı? (M51'in talep çekirdeği buna göre seçilir.)
2. Müşteri talepleri bugün hangi kanallardan, günde yaklaşık kaç adet geliyor; genel e-posta kutusuna okuma izni (Microsoft 365) verilebilir mi?
3. Müşteri hizmetlerini kim yürütüyor (kaç kişi, hangi birim); bayi destek ile okur destek aynı ekip mi?
4. Okur yorumlarının metni şikâyet analizi için saklanabilir mi (hukuk görüşü), yoksa yalnız o anda okunup sınıf sayısı mı tutulsun?
5. İade/cayma, ücretsiz yeniden gönderim, tazminat gibi kural dışı kararlarda yetki sınırları ve eşikler neler?

## 11. Başarı ölçütü

- İlk yanıt süresi medyanı ve SLA'ya uyum oranı (başlangıç ilk 2 haftada ölçülür, sonra hedef konur).
- Temsilcinin bir talepte baktığı sistem sayısı: bugün 3+ (**varsayım**) → 1 (bağlam paneli).
- Zeki AI sınıflama isabeti (temsilcinin değiştirmediği oran) ≥ %85; cevap taslağının az düzeltmeyle gönderilme oranı eğilimi.
- Tekrarlayan talep oranı (7 gün içinde aynı müşteri + konu) düşüyor.
- Self-servis: yazılan SSS maddesinden sonra o konudaki talep sayısının değişimi.
- CSAT eğilimi; ekranın günlük aktif kullanıcı sayısı (temsilci sayısına oranla).

## 12. Uzman gözüyle en iyi sistem

**Kimin yerine geçiyorum:** e-ticaret ve bayi kanalı olan bir yayınevinde 15 yıllık müşteri hizmetleri müdürü; önce çağrı
merkezi, sonra çok kanallı destek masası kurmuş.

**Sektörde en iyiler nasıl yapıyor:** (1) tek gelen kutusu: e-posta, form, sosyal medya, pazaryeri mesajları tek kuyrukta,
her talep bir kayıt; (2) temsilcinin yanında müşteri 360: sipariş, kargo, fatura, iade, önceki talepler — başka sisteme
geçmeden; (3) hazır cevap + bilgi bankası, yapay zekâ ile önerilir ama temsilci gönderir; (4) SLA ve yükseltme kuralları
konuya ve müşteri değerine göre; (5) kalite: CSAT/NPS, ilk temas çözüm oranı, tekrarlayan temas; (6) kök neden döngüsü:
şikâyet konuları haftalık operasyon toplantısına (depo, kargo, üretim) veriyle gider; (7) self-servis: sipariş takibi
ve SSS sitede, en sık sorulan sorunun cevabı müşteri yazmadan bulunur. Yayıncılığa özel: baskı/cilt hatası, eksik sayfa,
e-kitap erişimi, okul/kurum toplu siparişi, sezon (okul açılışı, fuar) yığılması.

**TİMAŞ için mükemmel sistem:** talep kaydı (helpdesk) + TİMAŞ bağlamı (CRM sipariş/kargo canlı, Logo fatura/iade) +
Zeki AI önerisi tek ekranda; yönetici panosunda SLA, konu, kök neden; bayi için ayrı görünüm; SSS açıkları haftalık liste.
Veri kaynağına yazmadan (CRM, T-soft), kararlar insanda.

**Bir iş günü (temsilci):**
- 09:00 — Kuyrukta 23 açık talep, SLA'ya göre sıralı. İlk talep: «Siparişim gelmedi». Bağlam paneli: e-posta CRM kişisine
  eşleşti, sipariş «Sevk Edildi», kargo takip kaydı var, çıkış şubesi. Zeki AI: konu «kargo gecikmesi», aciliyet «normal»,
  SSS «Kargom nerede?» eşleşmesi, taslak cevap takip bilgisiyle. İki kelime düzeltir, gönderir (2 dk).
- 10:30 — «Kitabın 48–64. sayfaları eksik». Konu «baskı hatası», aciliyet «yüksek»; kural: ücretsiz değişim → kural dışı
  değil, standart. Talebi depo uzmanına devreder; kitap bazında sayaç: bu baskıdan bu hafta 3. şikâyet → üretime uyarı (K3).
- 13:00 — Bir bayi arar: «Açık siparişlerim?». Bayi görünümü: 4 açık sipariş, biri «Risk Limit Onayı Bekliyor». Satış
  desteğe aktarır.
- 16:00 — Yönetici panosu: SLA aşımı 2; konu grafiğinde «kargo gecikmesi» geçen haftanın 2 katı, bir kargo firmasında
  yoğun → kök neden notu, haftalık operasyon toplantısına.
- 17:30 — Bilgi bankası açıkları: «e-kitap nasıl indirilir» 11 talep, SSS yok → Zeki AI taslağı, yönetici onayı; metin
  T-soft'a elle girilecek.

**«Bunu görürsem hemen kullanırım» — 3 özellik**
1. Talebin yanında canlı sipariş ve kargo durumu (CRM'den), başka ekrana geçmeden.
2. Konusu ve aciliyeti kendiliğinden dolan talep + tek tıkla düzeltilen cevap taslağı.
3. Bayi adına tek listede açık sipariş, bekleyen adet ve risk onayı.

**«Bunu yaparsanız kullanmam» — 3 tuzak**
1. Müşteriye kendiliğinden (onaysız) giden yapay zekâ cevabı.
2. İkinci bir talep sistemi: temsilci hem helpdesk'e hem portala kayıt girmek zorunda kalırsa ikisini de bırakır.
3. Eski veriyi canlı gibi göstermek: 17 Ağustos'ta donmuş Logo'dan «faturanız kesilmedi» demek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Müşteri eşleştirme | Cari: `LG_…_CLCARD` (`CODE`, `DEFINITION_`, kanal `SPECODE2`) — bayi/kurum için | `ContactBase` (e-posta, telefon), `AccountBase`, `new_webuserBase` (B2B; şifre/token sütunları hiç okunmaz) | Hiçbir şey (birebir eşleşme; birden çok aday varsa temsilci seçer) | Kimlik eşleşmesi deterministik olmalı |
| Sipariş durumu | Logo sipariş `ORFICHE`/`ORFLINE` (Kural 8; donmuş kopya uyarısıyla) | `new_siparisBase` durum `statuscode` (Kural C13), `new_bekleyenadet`, tip; satır `new_siparissatiriBase` | Hiçbir şey | Canlı durum CRM'de; rakam SQL'den |
| Sevkiyat ve kargo | Satış irsaliyesi `STLINE` TRCODE 8 (Kural 10/18/19) | `new_sevkiyatBase`, `new_kargobilgisiBase` (C19: metin tutar/desi → `TRY_CAST(REPLACE(…,',','.'))`), `new_kargotakipbilgisiBase` | Hiçbir şey | Aynı |
| Fatura ve iade | `LG_411_01_INVOICE` (fatura), `STLINE` satış iadesi (TRCODE 2/3, `CANCELLED = 0`; iade tanımı bilgi paketi `metrics/logo-timas.md` → `iade_orani` ile teyit edilir), `LINENET` | — | Hiçbir şey | Kayıt sistemi Logo; veri sonu tarihiyle |
| Bayi görünümü | `CLCARD` + `CLFLINE`/`PAYTRANS` bakiye (bilgi paketi cari kuralları; yaklaşık FIFO notu) | `new_siparisBase` (risk limiti durumları 100000004/100000016), `AccountBase` | Hiçbir şey | Aynı |
| Konu + aciliyet sınıflama | — | — | Talep metninden kapalı küme seçimi (konu: kargo gecikmesi / hasarlı-eksik ürün / baskı-içerik hatası / iade-cayma / fatura / bayi siparişi / e-kitap-erişim / kampanya-kupon / diğer; aciliyet: yüksek/normal/düşük), tek token + olasılık; düşük marj → «sınıflanamadı», temsilci seçer | Sınıflama modelin güçlü olduğu iş; kapalı küme ölçülebilir |
| SSS eşleştirme | — | `KnowledgeArticleBase`, `new_emailsablonBase` (kaynak metin) + helpdesk `HD Article` | Gömme servisiyle benzerlik (model değil, vektör); en iyi 3 aday | Hızlı ve ucuz; model gerekmez |
| Cevap taslağı (K2) | Bağlamdaki rakamlar (tarih, tutar) şablona SQL sonucundan yerleşir | Sipariş/kargo alanları | Nazik, kısa taslak; rakam ve tarih **yer tutucudan** gelir, model uydurmaz | Metin modelin işi, veri SQL'in |
| Tekrarlayan konu kümeleme | — | — | «diğer» sınıfındaki talepleri benzerlik + kısa etiket önerisiyle gruplama | Yeni konuları yakalamak |
| SSS taslağı (K2) | — | — | Bir konudaki çözülmüş talep cevaplarından SSS maddesi taslağı | Metin üretimi; yönetici onaylar, T-soft'a elle |
| Haftalık kalite özeti | — | — | Sayılardan kısa yorum | Rakamlar tablodan |
| Kişisel veri koruması | — | — | Modele giden metinde e-posta/telefon/adres kalıpları maskelenir (`sensitivity.py` değer kalıpları) | KVKK; sınıflama için gerekmez |

Model çağrıları `rt.llm_for("destek")` (etkileşimli taslak: öncelik 1; toplu sınıflama/kümeleme: arka plan). Helpdesk
dalındaki yapay zekâ paneli bugün kapıyı atlıyor; M51'in bütün çağrıları köprü üzerinden kapıya girer, helpdesk'e öneri
köprüden gelir (panelin doğrudan model çağrısı M51 kapsamında kullanılmaz).

## 14. Kodlama planı (kodlayıcıya devir)

**Karar noktası (kodlamadan önce, kullanıcıdan):** soru 1. Aşağıdaki plan **A seçeneğidir**: helpdesk (`apps/destek`)
talep kaydı çekirdeğidir, M51 köprü katmanı bağlam + Zeki AI + kalite panosunu verir. B seçeneğinde (helpdesk NanobaseAI'nin
iç masası kalırsa) ek olarak köprüde küçük bir talep tablosu (`semantic_support_tickets`: id, channel, subject, body_ref,
contact_ref, klass, urgency, status, assignee, sla_due, first_response_at, resolved_at, csat) ve temsilci ekranı gerekir
(+ **L**). İki seçenekte de ilk sürümün köprü parçası aynıdır; o yüzden hemen başlanabilir.

**Helpdesk dalıyla eşgüdüm:** `apps/destek` altında **hiçbir dosya** bu işte değiştirilmez (dal başka oturumun, yazılıyor).
Köprü helpdesk'i yalnız okur: Frappe REST (`/api/resource/HD Ticket`, `HD Article`) ile, helpdesk'te açılacak salt okuma
API kullanıcısının anahtarı `admin.conf` ayarında (`DESTEK_API_BASE`, `DESTEK_API_KEY`, `DESTEK_API_SECRET`; Yönetim →
Ayarlar'a `SPEC` satırı). Helpdesk temsilci ekranına panel eklemek, dal `main`'e girdikten sonra ayrı iş.

**Köprü dosyaları**
- `backend/semantic_bridge/support.py` — tablolar, sınıflama işi, SSS eşleştirme, taslak üretimi, kalite hesabı.
- `backend/semantic_bridge/support_sources.py` — bağlam okumaları: CRM (kişi/cari eşleşmesi, sipariş, sevkiyat, kargo)
  ve Logo (fatura, iade, cari bakiye) sabit sorguları; helpdesk REST istemcisi; veri sonu tarihi (Logo `MAX(DATE_)`).
  Sabit sorgular `Runtime._conn_for` ile doğru sunucuya gider; tek SQL'de iki kaynak yok.
- `backend/semantic_bridge/support_api.py` — `register(app, *, rt, can, audit, conf)`.

**Tablolar (meta DB)**
- `semantic_support_insights` (ticket_ref, source `destek|eposta`, klass, klass_p float, urgency, urgency_p, faq_matches_json, contact_ref, account_ref, draft text, draft_by_model_at, final_sent bool null, final_edit_ratio float null, created_at, updated_at) — Zeki AI'ın talep başına çıktısı ve temsilcinin onu nasıl kullandığı.
- `semantic_support_faq_gaps` (id, klass, label, ticket_count, sample_refs_json, draft text, status `aday|taslak|onayli|yayinlandi-elle`, approved_by, approved_at).
- `semantic_support_rules` (klass, sla_first_hours, sla_resolve_hours, escalate_to, exception_threshold_json) — ayar; helpdesk SLA'sı varsa oradan okunur, burası yalnız portal uyarısı için.
- `semantic_support_classes` (klass, label, description, active) — kapalı küme; kurulumda §13'teki 9 sınıf tohumlanır, yönetici düzenler.

**Uçlar (`/api/v1/support/*`)**
- `GET context?email=&phone=&order=&account=` — müşteri bağlamı (`ozellik:destek.baglam`; CRM/Logo okuması veri alanı `satis`/`cari` ister — Aşama C `acting_as`/`DATA_ALLOWED` deseniyle).
- `GET dealer/{account}` — bayi görünümü (aynı yetki).
- `POST classify` (tek metin; `ozellik:destek.oneri`) · `POST classify/run-due` (SYSTEM: helpdesk'teki yeni talepleri sınıflar).
- `POST draft` (`ozellik:destek.oneri`; talep ref + bağlam → taslak) · `POST drafts/{ref}/outcome` (temsilci gönderdi mi, düzeltme oranı).
- `GET faq/match?text=` · `GET faq/gaps` · `PATCH faq/gaps/{id}` (`ozellik:destek.sss`).
- `GET quality?from=&to=` — açık/SLA/ilk yanıt/çözüm/CSAT/sınıf eğilimi (helpdesk + insights).
- `GET classes` · `PUT classes/{klass}` (yönetici).
- `access.py` `RULES`: `("/api/v1/support/classify/run-due", SYSTEM)`, `("/api/v1/support/", frozenset({page("musteri-destek")}))`;
  `FEATURE_RULES`: `(GET, ^/api/v1/support/(context|dealer/[^/]+)$, "ozellik:destek.baglam")`, `(POST, ^/api/v1/support/(classify|draft)$, "ozellik:destek.oneri")`, `(PATCH, ^/api/v1/support/faq/gaps/[^/]+$, "ozellik:destek.sss")`.

**Ekranlar**
- `src/canvas/support/SupportScreen.tsx` (sekmeler: Özet · Konular · Bayi görünümü · Bilgi bankası açıkları · Müşteri bağlamı [temsilci için tek başına arama]),
  `CustomerContext.tsx` (helpdesk paneline de taşınabilecek bağımsız bileşen), `DealerView.tsx`, `FaqGaps.tsx`. Rota `/timas/musteri-destek`.
- Menü: `altyapi` alanında `{ id: 'musteri-destek', label: 'Müşteri hizmetleri' }` (ya da kullanıcı kararıyla «Kayıtlar» alanında — soru 3'ün cevabına göre).
- Kampüs: `ModulesMenu.LIVE.M51 = '/musteri-destek'`; helpdesk ayrı portta olduğundan Kampüs kartında «Talep masasını aç» dış bağlantısı (yeni sekme).
- `access_catalog.json`: `sayfa:musteri-destek`; `ozellik:destek.baglam`, `ozellik:destek.oneri`; açıkça verilen: `ozellik:destek.sss`, `ozellik:destek.kural-disi`, `ozellik:destek.herkesinki`.

**Zamanlayıcı**
- `timas-support.timer` 5 dk: helpdesk'teki yeni/güncellenen talepleri çek, sınıfla (arka plan önceliği), SSS eşleştir.
- Gece: kalite özet tablosu ve SSS açığı kümelemesi. VM'de `jobs.py` `JOBS`'a aynı iki iş. İlk koşu elle.

**Kabul testleri (gerçek veri, doğrudan bağlantı)**
1. Sipariş durumu: CRM (.28, doğrudan) `SELECT TOP 1 statuscode, new_bekleyenadet, new_sevktarihi FROM Timas_MSCRM.dbo.new_siparisBase WHERE <sipariş no alanı> = '<gerçek bir no>'` = bağlam panelindeki durum etiketi (Kural C13 eşlemesi) ve bekleyen adet. (Sipariş numarası alanının adı profilden alınır; test numarası canlıdan seçilir, belgeye yazılmaz.)
2. Kargo: aynı sipariş için `new_kargotakipbilgisiBase` / `new_kargobilgisiBase` satırları (bağ alanı profilden) = panelde gösterilen kargo firması ve şube; tutar `TRY_CAST(REPLACE(new_Tutar, ',', '.') AS FLOAT)` ile aynı.
3. Bayi görünümü: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase WHERE <cari bağ alanı> = '<bayi>' AND new_bekleyenadet > 0 AND statuscode NOT IN (100000015, 100000000, 100000001, 100000003, 2)` = «açık sipariş» sayısı (Kural C13 «bekleyen» tanımı).
4. Logo fatura: `SELECT TOP 5 FICHENO, DATE_, NETTOTAL FROM LG_411_01_INVOICE WHERE CLIENTREF = <cari ref> AND CANCELLED = 0 ORDER BY DATE_ DESC` (doğrudan .155) = paneldeki son faturalar; panelde «veri sonu 2026-08-17» (ya da o günkü `MAX(DATE_)`) yazıyor.
5. Kalite: helpdesk veritabanında `SELECT status, COUNT(*) FROM \`tabHD Ticket\` GROUP BY status` ve medyan `TIMESTAMPDIFF(MINUTE, opening_date+opening_time, first_responded_on)` = Özet sekmesindeki açık talep ve ilk yanıt medyanı; `AVG(feedback_rating)` = CSAT.
6. Sınıflama: 50 gerçek talep üzerinde temsilcinin seçtiği sınıfla karşılaştırma; isabet oranı ekranda ve M50 karnesinde aynı (ilk ölçüm; hedef §11).
7. Yetki: `ozellik:destek.baglam` olmayan deneme oturumu `GET /api/v1/support/context?email=…` → 403; `satis` veri alanı olmayan rol → `NOT_PERMITTED` benzeri açık ret; iş sonunda deneme oturumu silinir.
8. KVKK: modele giden istem kaydında (`sl_llm_job.messages_json`) e-posta/telefon/IBAN kalıbı 0.

**Bağımlılık:** Yetki A/B/C (var). Helpdesk dalı `main`'e girmeden ve soru 1 cevaplanmadan talep kaydına bağlanan parçalar
(kalite panosu, sınıflama işi) çalıştırılamaz; **bağlam ucu ve bayi görünümü helpdesk'ten bağımsızdır, hemen kodlanabilir**.
M49 saklama politikası talep verisini kapsamalı. M50 karnesine satır: M50 önce ya da sonra, ikisi paralel.

**Tahmini büyüklük:** Bağlam + bayi görünümü **M**; sınıflama + SSS eşleştirme + taslak **M**; kalite panosu (helpdesk
okuması) **S–M**; e-posta kutusu bağlantısı **M**; B seçeneği talep kaydı + temsilci ekranı **L**.
