# M23 — İnfluencer ve İşbirliği Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M23.txt` (ZEKİ_Moduller3.html; «Veritabanı + Takip + Sadakat»), `specs/M15.txt`, `specs/M18.txt`, `ZEKİ_Veri_Haritasi2.html` (İnfluencer Veritabanı, Kampanya Girdileri), `configs/semantic/knowledge/crm/table_descriptions.json` (2026-09-09), `docs/analiz/kitap-yazar-web-taramasi-2026-09-24.md` (1.3 Sosyal medya: resmî API koşulları), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `backend/semantic_bridge/freelance.py`, `author_relations.py`, `alerts.py`, `access.py`, `access_catalog.json`, `src/canvas/nav/navModel.ts`, `docs/LLM-KAPISI.md`, kullanıcı belleği (web-watch-open-sources, customer-vm-web-watch-off, freelancer-payments-logo, no-tech-names-on-screens, no-silent-limits-rule).

> Kural: sunucuya bağlanılmadı. Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım** diye işaretlidir.

## 1. Modül ne işe yarar

Kitap tanıtımında çalışılan ve aday içerik üreticilerinin (Bookstagram, BookTube, BookTok, blog, podcast) kaydını tutar; her kitap için konu uyumu, geçmiş performans ve bütçeye göre aday listesi önerir; brief → içerik onayı → yayın → ödeme akışını takip eder; kampanya sonucu ve ilişki geçmişine göre yeniden işbirliği (sadakat) önerir (iş tanımı M23: K1 veritabanı ve davranış takibi, K2 kitap bazlı eşleşme, K2 sadakat ve işbirliği yönetimi).

TİMAŞ'ın bugünkü sorunu: CRM'de influencer diye bir varlık yok. İzler dağınık: Pazarlama Bütçe Modülü'nde mecra seçeneği olarak «Influencer» (`new_pazarlamamoduluBase.new_mecratipi4 = 6`), kişilerde sosyal kullanıcı adı alanları (`ContactBase.new_Instagram`, `new_YoutubeKullancAd`, `new_TwitterKullaniciAdi`, …) ve «Pazarlama (Tanıtım Gönderimi)» tipli siparişler (`new_siparisBase.new_siparistipi = 12`). Kime kitap gönderildiği, kimin paylaştığı, paylaşımın ne getirdiği ve kime ne ödendiği bir arada tutulmuyor (**varsayım**; hacimler **ölçülecek**).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| İşbirliği / influencer sorumlusu | Pazarlama (sosyal medya ekibi içinde olduğu **varsayım**) | Her gün | Telefon (DM, içerik onayı) + masaüstü (liste, brief) |
| Sosyal medya uzmanı | Pazarlama | Haftada birkaç (içeriği yeniden paylaşma) | Telefon |
| Pazarlama müdürü | Pazarlama | Haftada 1 (bütçe, seçim onayı) | Telefon |
| Muhasebe | Mali İşler (TeamMembership 10) | Ayda 1 (ödeme) | Masaüstü |
| Editör | Editörya | Kitap başına (içerik doğruluğu, spoiler) | Masaüstü |

İçerik üreticisi portala giremez (AD hesabı yok); iletişim e-postayla.

## 3. Bugün bu iş nasıl yapılıyor

- **İşbirliği sorumlusu** (varsayım): aday listesi kişisel takip ve DM'lerle; kitap gönderimi CRM'de tanıtım siparişi olarak; paylaşım ekran görüntüsüyle arşivlenir; ücretli işbirliği bütçe modülüne ya da Excel'e. Tıkanma: bir içerik üreticisiyle geçmişte ne yapıldığını, paylaşımın satışa ya da takipçiye etkisini ve ödemenin durumunu hatırlamak.
- **Muhasebe**: ödeme Logo'da hizmet alımı olarak (hangi kart/özel kod **ölçülecek**; serbest çalışanlarda tercüme/grafik/raportörlük kartı + özel kod kullanılıyor — freelancer-payments-logo belleği; influencer için aynı yapı var mı bilinmiyor).

## 4. İhtiyaçlar ve acı noktaları

**İşbirliği sorumlusu**
1. Tek kayıt defteri: kim, hangi platform, hangi konu, takipçi/etkileşim (tarihli), geçmiş işbirlikleri, ücret, iletişim tercihi.
2. Kitap için uygun adayların gerekçeli sırası (konu, yaş grubu, geçmiş performans, bütçe).
3. İş akışı hatırlatıcıları: kitap gitti mi, içerik taslağı geldi mi, yayın tarihi, yayından sonra rapor, ödeme.
4. Brief ve iletişim e-postasının geçmişi bilen taslağı.
5. Paylaşım bağlantısını girince sonuçların (erişim, etkileşim) kaydı.

**Pazarlama müdürü**
1. Harcama ve sonuç: işbirliği başına maliyet, etkileşim başına maliyet (CPE).
2. Seçim ve sadakat tekliflerini onaylamak.
3. Yasal etiket (reklam/işbirliği) kurallarına uyulduğundan emin olmak.

**Muhasebe**
1. Onaylı ödeme listesi, belge ve tutar.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- İşbirliği sorumlusu olarak bir içerik üreticisinin bütün geçmişini tek kartta görmek istiyorum, çünkü aynı kişiye aynı kitabı iki kez göndermemek istiyorum.
- İşbirliği sorumlusu olarak yeni kitap için adayları konu uyumu ve geçmiş sonuçla sıralı görmek istiyorum, çünkü listeyi her seferinde sıfırdan kuruyorum.
- İşbirliği sorumlusu olarak brief'i Zeki'nin taslağıyla başlatmak istiyorum, çünkü her kişiye ayrı brief yazmak uzun sürüyor.
- İşbirliği sorumlusu olarak yayın tarihi yaklaşınca ve yayın sonrası hatırlatma almak istiyorum, çünkü takip bende kalıyor.
- Pazarlama müdürü olarak kampanya sonunda harcama ve CPE tablosunu görmek istiyorum, çünkü bütçeyi kime vereceğimize karar veriyorum.
- Muhasebe olarak yalnız onaylı ve teslimi yapılmış işbirliklerinin ödeme listesini almak istiyorum, çünkü yarım kalmış işe ödeme çıkmamalı.

**Ana ekranlar ve akış**
- İlk açılış (`/timas/isbirlikleri`): «Açık işler» panosu (sütunlar: teklif → kitap gönderildi → içerik bekleniyor → yayında → rapor → ödeme), üstte bu ayın harcaması ve bekleyen onaylar.
- En sık 3 işlem: (1) Kitap için aday listesi → seç → işbirliği aç: 3 tık. (2) Kart sütunu ilerlet (ör. «yayında» + bağlantı): 2 tık. (3) Yeni içerik üreticisi ekle (kullanıcı adı yapıştır → resmî API'den temel bilgiler): 2 tık.
- Diğer ekranlar: İçerik üreticileri (kayıt defteri, süzgeç: platform/konu/yaş grubu/son işbirliği), Kişi kartı, Rapor (kampanya ve kişi bazında).

**Zeki AI'a soracakları**
- «Çocuk kitapları için son bir yılda en iyi sonuç veren içerik üreticileri kimler?»
- «[Kitap] için tarih ve biyografi okuyan adayları öner.»
- «Bu ay hangi işbirliklerinde yayın tarihi geçti ama bağlantı girilmedi?»
- «Geçen çeyrek işbirliğine ne harcadık, etkileşim başı maliyet ne?»
- «[Kişi] ile daha önce hangi kitaplarda çalıştık?»
- «[Kişi] için sadakat teklifi metni hazırla.»

**Otomasyon katmanı**
- K1: kayıt defterindeki hesapların herkese açık temel sayılarının (takipçi, gönderi sayısı, son gönderilerin beğeni/yorum sayısı) **resmî API'nin izin verdiği ölçüde** periyodik alınması; ani takipçi sıçraması uyarısı (kendi anlık görüntülerimizden); hatırlatıcılar.
- K2: aday sıralaması, brief, iletişim ve sadakat metni → sorumlu düzenler, müdür onaylar.
- K3: işbirliği ROI değerlendirmesi, uzun dönem ortaklık kararı.
- İş tanımındaki «authenticity skoru / sahte takipçi tespiti» ve «veritabanı dışından keşif» resmî API'lerle yapılamaz (takipçi listesi verilmez, konuya göre hesap araması yok); ilk sürümde **yok**, bölüm 8.

**Bildirim/uyarı**
- Sorumluya: yayın tarihi yarın/bugün, yayın tarihinden 2 gün sonra bağlantı yok, içerik onayı bekliyor 3 gün, takipçide ani sıçrama.
- Müdüre: onay bekleyen seçim/teklif (Uyarılar rozeti), ay bütçesinin %90'ı harcandı.
- Muhasebeye: ödeme listesi hazır (ayın 25'i, ayar).

**Onay ve yetki**
- `sayfa:isbirlikleri`; `ozellik:isbirligi.duzenle`; `ozellik:isbirligi.onay` (explicit; seçim, teklif, ücret); `ozellik:isbirligi.odeme` (explicit; ödeme kaydı — muhasebe).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| İçerik üreticisi kaydı | Kullanıcı girer; CRM `ContactBase` sosyal alanları (`new_Instagram`, `new_YoutubeKullancAd`, `new_TwitterKullaniciAdi`, `new_FacebookKullaniciAdi`, `new_Linkedinkullaniciadi`) | CRM'de influencer rolü var mı (`new_kisiroluBase` 38 rol) **ölçülecek** | Kayıt defteri köprü tablosunda |
| Herkese açık hesap sayıları | Instagram Graph API iş hesabı keşfi (kendi Business hesabımız üzerinden, karşı hesap Business/Creator olmalı), YouTube Data API v3 kanal istatistikleri, X API (ücretli) | Bağlı değil; hesap ve anahtar **ölçülecek**; kota/koşul ayrıntıları **doğrulanmadı** | TikTok'ta ticari kullanıcıya açık resmî okuma yolu bulunmadı (Research API akademik) → elle giriş |
| Kitap gönderimi | CRM `new_siparisBase.new_siparistipi = 12` + `new_siparissatiriBase` | Alıcı kişi mi cari mi **ölçülecek** | Kişi bağı yoksa işbirliği kartına elle bağlanır |
| İşbirliği harcaması (geçmiş) | CRM `new_pazarlamamoduluBase` (`new_mecratipi4 = 6` «Influencer», `new_tutar`, `new_sosyalmedyahesabi`) + `new_new_pazarlamamodulu_new_kitapBase` | Kayıt sayısı ve güncelliği **ölçülecek** | — |
| Ödeme | Logo hizmet alımı (TRCODE 4) | Hangi hizmet kartı/özel kod **ölçülecek** | Mutabakat |
| Kitap bilgisi, hedef kitle | CRM `new_kitapBase` (`new_ozet`, `new_hedefkitle`, `new_hedefkitleyasbaslangic/bitis`, `new_turlertext`, `new_rafturu`) | Var | — |
| Paylaşım sonucu | İçerik üreticisinin gönderdiği ekran görüntüsü/istatistik (elle), kendi hesabımızda yeniden paylaşım (M22) | — | Karşı hesabın gönderi istatistiği yalnız herkese açık sayılar |
| Satış etkisi | Logo `V_SatisRaporu_<yıl>`, e-ticaret kanalı | Donmuş kopya 2026-08-17 | İndirim kodu/UTM yoksa doğrudan bağ kurulamaz |

## 7. Diğer modüllerle bağ

- Girdi: M15 (kitap planı, hedef kitle, influencer önerisi), M18 (aylık içerik planı), M19 (brief metinleri), M46 (bütçe), M22 (kendi hesaplarımızın içgörüsü), M20 (aynı kişi hem gazeteci hem içerik üreticisi olabilir — `crm_contact_id` üzerinden birleşir).
- Çıktı: M22 (yeniden paylaşım), M21 (işbirliği harcaması pazarlama verimine), M35 (indirim kodu kampanyası), M28 (kanaat önderleriyle örtüşen kişiler), muhasebe.

## 8. Kısıtlar

- **Kazıma yok.** Takipçi listesi, bot/sahte takipçi analizi, konuya göre hesap keşfi resmî API'lerde yok; bot korumasını aşan araç ve arayüz kazıma kullanılmaz. Bu yüzden iş tanımındaki «authenticity skoru» ve «yükselen hesapların otomatik eklenmesi» ilk sürümde yok; istenirse yalnız lisanslı sağlayıcıyla (sözleşme ve KVKK değerlendirmesiyle) yapılır.
- Müşteri VM'inde web taraması kapalı; bu modülün resmî API çağrıları da dış kaynaktır → aynı bayrak mantığıyla ortam bazında açılıp kapanır (`INFLUENCER_API_ENABLED`, varsayılan 0).
- CRM'e ve T-soft'a yazma yok; kayıtlar `semantic_infl_*`.
- Ekranda teknoloji/model adı yok. Demo veri yok. Sayı tavanı yok (iş tanımındaki «10–20 profil» tavan değil; sıralı liste tamamı görünür).
- Hukuk: Reklam Kurulu'nun sosyal medya etkileyicilerine ilişkin kılavuzu (2021) ücretli ya da karşılıklı işbirliğinde reklam olduğunun açıkça belirtilmesini ister; brief şablonunda zorunlu etiket maddesi ve yayın kontrol listesinde «etiket var mı» işareti bulunmalı. Ödeme ve vergilendirme muhasebeye sorulacak.
- KVKK: içerik üreticisinin iletişim bilgisi ve ücreti kişisel veridir; ücret alanı yalnız `ozellik:isbirligi.onay`/`odeme` sahiplerine görünür. Çocuk içerik üreticisiyle (reşit olmayan) işbirliğinde veli onayı — hukuka sorulacak.

## 9. Kapsam önerisi

**İlk sürüm**
- Kayıt defteri (elle + CSV içe aktarma), platform hesapları, konu etiketleri, yaş grubu, ücret aralığı, iletişim.
- İşbirliği panosu ve aşamalar (teklif → kitap gönderildi → içerik bekleniyor → yayında → rapor → ödeme), hatırlatıcılar.
- Kitap için aday sıralaması (kural puanı + Zeki gerekçesi), brief/iletişim/sadakat taslağı (K2), onay.
- Sonuç kaydı (bağlantı, erişim, etkileşim; elle), kampanya ve kişi raporu (maliyet, CPE), ilişki puanı.
- Muhasebe ödeme listesi (Excel).

**Sonraki sürüm**
- Resmî API ile herkese açık sayıların periyodik alınması (Instagram iş hesabı keşfi, YouTube) ve ani sıçrama uyarısı.
- İndirim kodu/UTM ile satış bağı (M35, e-ticaret).
- Lisanslı sağlayıcı kararı verilirse keşif ve güvenilirlik puanı.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/freelance.py` (dış kişi havuzu, iş paketi, hakediş → onay → ödendi akışı, `send_mail` + Reply-To, portfolyo dosyası) — işbirliği ve ödeme akışının neredeyse aynısı; ortak yardımcılar paylaşılır.
- `backend/semantic_bridge/author_relations.py` (ilişki ısı puanı deseni → sadakat/ilişki puanı).
- `backend/semantic_bridge/alerts.py`, `reports.py`, `admin.audit`, `access.py`.

## 10. Uzmanlara sorulacak sorular

1. Bugün kaç içerik üreticisiyle düzenli çalışılıyor; liste nerede?
2. İşbirliği çoğunlukla ücretli mi, kitap karşılığı mı? Ücret nasıl ödeniyor ve Logo'da hangi karta işleniyor?
3. Kitap gönderimi tanıtım siparişiyle mi yapılıyor; alıcı kişi olarak CRM'de kayıtlı mı?
4. Meta'da TİMAŞ'ın Business hesabı var mı; API uygulaması açılmasına onay verilir mi?
5. Sonucu nasıl ölçüyorsunuz (erişim, satış, indirim kodu)?

## 11. Başarı ölçütü

- Açık işbirliklerinin tamamı panoda; yayın tarihi geçip bağlantısı girilmemiş iş sayısı ≈ 0.
- Aday listesinden işbirliğine dönüşme süresi.
- Kampanya başına CPE'nin raporlanması (bugün yok).
- Tekrar çalışılan içerik üreticisi oranı (sadakat).
- Ödeme listesinin ay sonunda portaldan alınması.

## 12. Uzman gözüyle en iyi sistem

*Yayınevlerinde 10+ yıl çalışmış işbirliği ve topluluk pazarlaması yöneticisi gözüyle.*

Yayıncılıkta içerik üreticisi pazarlamasının kalbi **ön okuma nüshası ve hediye kitap programıdır**: doğru kişiye, çıkıştan önce, kişisel bir notla kitap gitmesi; ücretli işbirliği bunun üstüne eklenir. Sektördeki içerik üreticisi yazılımları (ilişki defteri + kampanya panosu + ödeme + sonuç raporu) en çok ilişki geçmişi ve iş akışı hatırlatıcısıyla işe yarar; «yapay zekâ keşfi» ve «sahte takipçi skoru» çoğu zaman sağlayıcının kendi verisine dayanan kara kutudur. TİMAŞ için mükemmel sistem: kitap türlerine göre (çocuk, genç, tarih, kişisel gelişim, din/tasavvuf) segmentlenmiş, her kişinin hangi Timaş kitabını aldığı ve ne yaptığı bilinen, kargodan ödemeye kadar tek panoda ilerleyen bir **ilişki defteri**.

**Bir iş günü**
- 09:00 Pano: 3 kişi içerik taslağını gönderdi (onay bekliyor), 2 kişinin yayın tarihi bugün, 1 işte yayın geçmiş ve bağlantı yok.
- 09:20 Taslaklar editöre gider (spoiler ve bilgi doğruluğu), biri geri döner.
- 10:30 Ay lansmanı: 2 kitap için aday listesi — gerekçeli sıra («geçen yıl 3 tarih kitabında ortalamanın 2 katı etkileşim»). 15 kişi seçilir; müdür öğlen telefondan onaylar.
- 13:00 Brief taslakları: kişinin geçmişini bilen, reklam etiketini hatırlatan metinler; kargo listesi Excel.
- 16:00 Yayınlanan içeriklerin bağlantıları girilir; kendi hesabımızda yeniden paylaşım için M22'ye düşer.
- Ay sonu: kişi başına maliyet/etkileşim tablosu; muhasebeye ödeme listesi.

**«Bunu görürsem hemen kullanırım»**
1. Kişi kartında «hangi kitapları aldı, ne paylaştı, ne ödendi».
2. Kargodan ödemeye tek pano ve hatırlatıcı.
3. Kitaba göre gerekçeli aday sırası.

**«Bunu yaparsanız kullanmam»**
1. Nereden geldiği belli olmayan «güvenilirlik skoru» ile kişileri eleyen sistem.
2. Brief'i ve iletişimi herkese aynı gönderen otomasyon.
3. Ücretleri herkesin görebildiği ekran.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kişi ekleme | — | `ContactBase` sosyal alanları (varsa eşleşme) | — | Kural: kullanıcı adı eşleşmesi |
| Konu etiketi | — | — | Hesabın biyografisi ve son gönderi başlıklarından (resmî API'den gelen metin ya da elle yapıştırılan) kapalı seçim etiket: çocuk/genç/edebiyat/tarih/kişisel gelişim/din-tasavvuf/bilim/diğer — tek token + olasılık | Sınıflandırma |
| Kitap için aday sırası | — | `new_kitapBase.new_hedefkitle`, `new_turlertext`, `new_rafturu`, yaş aralığı | Puan kuralla (etiket uyumu, geçmiş CPE, son işbirliği tarihi, bütçe); model yalnız gerekçe cümlesi | Açıklanabilir sıralama |
| Kitap gönderimi izi | — | `new_siparisBase.new_siparistipi = 12`, `new_siparissatiriBase.new_StokKodu`, `new_adet` | — | SQL |
| Geçmiş harcama | — | `new_pazarlamamoduluBase` (`new_mecratipi4 = 6`, `new_tutar`) | — | SQL |
| Brief / iletişim / sadakat metni | — | Kitap metinleri (`new_ozet`, `new_kitabinonecikanyanlari`) + kişinin geçmiş işbirlikleri (köprü) | Taslak; zorunlu reklam etiketi maddesi şablonda sabit | Metin işi, yasal madde modele bırakılmaz |
| Ödeme mutabakatı (sonraki) | Logo hizmet alımı (TRCODE 4, `CLFLINE`/`INVOICE`, cari = içerik üreticisi) | — | — | Logo kayıt sistemi |
| Satış etkisi (sonraki) | `V_SatisRaporu_<yıl>` kitap bazında `[Yıl]*12+[Ay]` | `new_StokKodu` | Yorum | — |

Model yalnız LLM kapısından: `rt.llm_for("isbirligi")`, gece etiketleme `rt.llm_for("isbirligi", BATCH)`.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/influencers.py` (kayıt, aşamalar, puanlar), `influencers_sources.py` (CRM SQL, resmî API istemcileri yalnız okuma — sonraki sürüm), `influencers_api.py` (`register`).

**Tablolar**
- `semantic_infl_people` (id, tenant_id, crm_contact_id NULL, name, email, phone, city, topics_json, age_groups_json, fee_min, fee_max, currency, notes, do_not_contact, created_by, updated_at)
- `semantic_infl_accounts` (id, person_id, platform, handle, url, verified_by_api bool)
- `semantic_infl_snapshots` (account_id, day, followers, posts, avg_likes, avg_comments, source [api/elle]; PK account_id+day)
- `semantic_infl_collabs` (id, tenant_id, person_id, crm_book_id, kind [hediye/ücretli/karşılıklı], stage [teklif/gönderildi/içerik-bekleniyor/onayda/yayında/rapor/ödeme/kapalı/vazgeçildi], fee, crm_order_no NULL, due_publish, published_url, disclosure_ok bool, reach, engagement, approved_by, created_by, updated_at)
- `semantic_infl_events` (collab_id, at, user, action, note)
- `semantic_infl_payouts` (id, collab_id, amount, status [hazır/onaylı/ödendi], logo_doc_no, paid_at, by)

**Uçlar** (`/api/v1/influencers/*`): `GET meta`, `GET board`, `GET people`, `POST people`, `PATCH people/{id}`, `GET people/{id}`, `POST people/import` (CSV), `GET books/{crmBookId}/candidates`, `POST collabs`, `PATCH collabs/{id}`, `POST collabs/{id}/draft` (brief/iletişim; LLM iş), `POST collabs/{id}/mail`, `POST collabs/{id}/approve`, `GET payouts?month=`, `POST payouts/{id}/decide`, `GET report?from=&to=`, `GET report/export.xlsx`, `POST run-due` (SYSTEM).

**Ekranlar** — `src/canvas/influencers/` (`CollabBoard.tsx`, `PeopleList.tsx`, `PersonCard.tsx`, `Candidates.tsx`, `CollabReport.tsx`, `Payouts.tsx`); rota `/timas/isbirlikleri` (+ `/kisiler`, `/kisi/:id`, `/aday/:kitap`, `/rapor`, `/odemeler`). Menü: `pazarlama`, bölüm `section: 'İletişim'`, öğe `{ id: 'isbirlikleri', label: 'İşbirlikleri', icon: Handshake, hint: 'İçerik üreticileri, gönderim ve sonuç' }`. Kitap sayfasına «İşbirlikleri» sekmesi. Kampüs: M23 çalışan. Telefon: pano tek sütun, aşama ilerletme ve bağlantı girişi.

**Yetki** — `sayfa:isbirlikleri`; `ozellik:isbirligi.duzenle`; `ozellik:isbirligi.onay` (explicit); `ozellik:isbirligi.odeme` (explicit). `access.py`: `("/api/v1/influencers/run-due", SYSTEM)`, `("/api/v1/influencers/", frozenset({page("isbirlikleri")}))`; FEATURE_RULES POST/PATCH `^/api/v1/influencers/(people|collabs)` → `ozellik:isbirligi.duzenle`; approve/payouts decide ucun içinde; export → `ozellik:veri.disa-aktar`. Ücret alanları yanıtta yetkiye göre boşaltılır.

**Zamanlayıcı** — `scripts/server/timas-influencers.timer` her gün 08:00: hatırlatıcılar; `INFLUENCER_API_ENABLED=1` ise haftalık anlık görüntü (resmî API) ve sıçrama uyarısı.

**Kabul testleri**
1. Tanıtım gönderimi: kişi kartında «gönderilen kitap» adedi (bağlı sipariş no'larından) = `SELECT SUM(ss.new_adet) FROM Timas_MSCRM.dbo.new_siparissatiriBase ss JOIN Timas_MSCRM.dbo.new_siparisBase s ON s.new_siparisId = ss.new_siparisid WHERE s.new_siparistipi = 12 AND s.new_name IN (<kartın sipariş no'ları>)`.
2. Geçmiş influencer harcaması (CRM) = `SELECT SUM(new_tutar) FROM Timas_MSCRM.dbo.new_pazarlamamoduluBase WHERE statecode = 0 AND new_mecratipi4 = 6 AND new_baslangictarihi >= '<bas>' AND new_baslangictarihi < '<bit>'`.
3. CRM sosyal alanı olan kişi sayısı (içe aktarma önerisi) = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.ContactBase WHERE statecode = 0 AND (NULLIF(LTRIM(new_Instagram),'') IS NOT NULL OR NULLIF(LTRIM(new_YoutubeKullancAd),'') IS NOT NULL)` (yazarlar `new_yazarmi = 1` ayrı sayılır).
4. Rapor: dönem harcaması = `SELECT SUM(fee) FROM semantic_infl_collabs WHERE stage NOT IN ('vazgeçildi') AND due_publish BETWEEN …`; CPE = harcama ÷ `SUM(engagement)` — ekranla birebir.
5. Ödeme listesi yalnız `stage IN ('rapor','ödeme')` ve onaylı işleri içerir: `SELECT COUNT(*) FROM semantic_infl_payouts p JOIN semantic_infl_collabs c ON c.id = p.collab_id WHERE p.status = 'hazır' AND c.stage NOT IN ('rapor','ödeme')` = 0.
6. Yetki: `ozellik:isbirligi.onay` olmayan kullanıcıya `GET people/{id}` yanıtında `fee_min/fee_max` boş.

**Bağımlılık** — Bağımsız kodlanabilir; freelance.py'deki ortak parçalar (e-posta, hakediş durumu) önce küçük bir ortak yardımcıya çıkarılırsa iki modül paylaşır. M22 ile paralel.

**Tahmini büyüklük** — L (3+ gün); API anlık görüntüsü ayrı M.
