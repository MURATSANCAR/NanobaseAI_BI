# M22 — Sosyal Medya Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M22.txt` (ZEKİ_Moduller3.html; «M18 Aylık Plan Entegre»), `specs/M18.txt`, `specs/M19.txt`, `specs/M51.txt` başlığı, `ZEKİ_Veri_Haritasi2.html` (M18 Plan Girdisi, Platform & Performans, Sosyal Medya API), `configs/semantic/knowledge/crm/table_descriptions.json` (2026-09-09), `docs/analiz/kitap-yazar-web-taramasi-2026-09-24.md` (1.3 Sosyal medya), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `backend/semantic_bridge/seo_geo/seasons.py`, `editorial_studio_marketing.py`, `web_watch.py`, `access.py`, `access_catalog.json`, `src/canvas/nav/navModel.ts`, `docs/LLM-KAPISI.md`, kullanıcı belleği (web-watch-open-sources, customer-vm-web-watch-off, no-tech-names-on-screens, no-silent-limits-rule, no-demo-login).

> Kural: sunucuya bağlanılmadı. Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım** diye işaretlidir.

## 1. Modül ne işe yarar

Aylık pazarlama planındaki (M18) içerikleri platform bazında takvime yerleştirir, yeni kitap ve backlist paylaşımlarını dengeler, her platformun diline uygun metin/hashtag önerir, gündem ve özel günlere bağlı ek içerik fırsatlarını gösterir, önemli yorum ve mesajları öne çıkarır, kriz sinyalinde uyarır ve aylık performansı bir sonraki plana geri besler (iş tanımı M22: K1 plan bazlı zamanlama, K2 içerik üretimi ve zenginleştirme, K3 topluluk yönetimi ve kriz).

TİMAŞ'ın bugünkü sorunu: yayınevinin birden çok marka/imprint hesabı var (CRM `new_markaBase` 34 marka, her birinde `new_instagramkullaniciadi` alanı; kaçında dolu olduğu **ölçülecek**). Kitap kartında «Sosyal Medya Metni» (`new_kitapBase.new_sosyalmedyametni`) diye tek bir serbest alan var; takvim, onay, performans ve geri besleme portal/CRM'de yok. İş tanımı bu modülü M18'e bağlıyor ama **M18 kodlanmadı**; ilk sürüm M18'i beklememeli.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Sosyal medya uzmanı / içerik editörü | Pazarlama (TeamMembership «Pazarlama» 35; imprint başına ayrı kişi olup olmadığı **varsayım**) | Her gün, gün içinde çok kez | Telefon ağırlıklı (yorum, onay, hızlı taslak) + masaüstü (takvim) |
| Topluluk yöneticisi (yorum/DM) | Pazarlama ya da müşteri hizmetleri (M51) — **varsayım** | Her gün | Telefon |
| Grafik tasarımcı | Grafik (TeamMembership 13) | Haftada birkaç | Masaüstü |
| Pazarlama müdürü | Pazarlama | Haftada 1 (onay, rapor), krizde anında | Telefon |
| Editör / yayın yönetmeni | Editörya | Kitap başına (alıntı ve içerik doğruluğu) | Masaüstü |
| Dış ajans | **varsayım** (reklam planında ajans alanı var) | Haftalık | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Sosyal medya uzmanı** (varsayım): içerik takvimi Excel/paylaşılan tablo ya da platformların kendi planlayıcısında; görsel grafik ekibinden e-postayla; metin kitap kartındaki alan veya arka kapak metninden elle; onay WhatsApp/e-postayla. Tıkanma: hangi kitabın ne zaman paylaşıldığı ve nasıl performans gösterdiği bir yerde toplanmıyor; özel günler (CRM `new_ozelgunlerBase` 93 kayıt, ~820 kitap bağı) sosyal takvime bağlı değil.
- **Topluluk yöneticisi**: yorumlar platform uygulamasından tek tek; önemli yorum/şikâyet kaydı yok (**varsayım**).
- **Pazarlama müdürü**: aylık rakamlar platform istatistik ekranlarının ekran görüntüsüyle (**varsayım**).

## 4. İhtiyaçlar ve acı noktaları

**Sosyal medya uzmanı**
1. Tek takvim: tüm hesaplar, yeni kitap + backlist + özel gün, taslak/onay/yayında durumu.
2. Kitaptan hazır içerik paketi: görsel (stüdyo pazarlama kiti), platforma göre metin, alıntı, hashtag.
3. Onayın hızlı ve izli olması (telefonda tek dokunuş).
4. Hangi içerik türünün hangi hesapta işe yaradığını görmek.
5. Gündem/özel gün fırsatının önceden haber verilmesi (7–14 gün).

**Topluluk yöneticisi**
1. Önemli yorumların (şikâyet, kargo/sipariş sorunu, yazar hakkında olumsuz, basın sorusu) öne çıkması.
2. Hazır ama kişisel yanıt taslağı.
3. Kargo/sipariş şikâyetini müşteri hizmetlerine (M51) aktarmak.

**Pazarlama müdürü**
1. Kriz sinyalinde anında haber.
2. Aylık performans ve bir sonraki aya öneri.
3. Kurum adına çıkan her içeriğin onaydan geçtiğinin kanıtı.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Sosyal medya uzmanı olarak bu ayın bütün hesaplarının takvimini tek ekranda görmek istiyorum, çünkü imprint hesaplarını ayrı ayrı yönetmek hata çıkarıyor.
- Sosyal medya uzmanı olarak bir kitabı seçince Instagram, X ve LinkedIn için ayrı metin taslağı almak istiyorum, çünkü her platformun dili farklı.
- Sosyal medya uzmanı olarak yaklaşan özel güne bağlı kitapları iki hafta önceden görmek istiyorum, çünkü içerik ve görsel hazırlığı zaman alıyor.
- Sosyal medya uzmanı olarak paylaşımı onaya göndermek ve onaylanınca yayına hazır paketi indirmek istiyorum, çünkü görsel ve metin ayrı yerlerde kayboluyor.
- Topluluk yöneticisi olarak son 24 saatin önemli yorumlarını sıralı görmek istiyorum, çünkü yüzlerce yorum arasında şikâyet kaçıyor.
- Pazarlama müdürü olarak olumsuz yorumlar birden artınca telefonuma uyarı gelsin istiyorum, çünkü krizde ilk saat önemli.
- Pazarlama müdürü olarak ay sonunda içerik türü × etkileşim raporunu görmek istiyorum, çünkü gelecek ayın planını buna göre yapıyoruz.

**Ana ekranlar ve akış**
- İlk açılış (`/timas/sosyal-medya`): hafta görünümü takvim (hesap renkleriyle), sağda «Onay bekleyen» ve «Yaklaşan fırsatlar» (özel gün, yeni çıkan kitap, basında çıkan haber).
- En sık 3 işlem: (1) Takvimde boş güne «kitaptan içerik» → kitap seç → platform taslakları: 3 tık. (2) Onay (telefonda kart kaydır/onayla): 1 tık. (3) Yayına hazır paketi indir (görsel + metin + hashtag): 1 tık.
- Diğer ekranlar: İçerik havuzu (kitap başına onaylı metin/görsel), Yorumlar (resmî API bağlanınca), Rapor.

**Zeki AI'a soracakları**
- «Bu ay hangi özel günler var ve hangi kitaplarımız bağlı?»
- «[Kitap] için üç Instagram metni ve beş hashtag öner.»
- «Son 30 günde en çok etkileşim alan paylaşım türü hangisi?»
- «Bu ay hiç paylaşılmamış yeni çıkan kitaplar hangileri?»
- «Dün [yazar] hakkında olumsuz yorum arttı mı?»
- «[Kitap]'tan paylaşılabilecek kısa alıntılar çıkar.»

**Otomasyon katmanı**
- K1: takvim doldurma önerisi (yeni kitap/özel gün/plan), paylaşım saati önerisi (geçmiş performanstan; veri gelince), format dönüşümü (stüdyo pazarlama kiti boyutları), performans verisinin çekilmesi (resmî API bağlanınca).
- K2: her metin ve ek içerik fırsatı insan onayından geçer. **Onaylı içeriğin platformda otomatik yayını ilk sürümde yok** (bölüm 8); onaylı paket indirilir, uzman kendi hesabından paylaşır ve «yayınlandı» işaretler (bağlantıyla).
- K3: önemli yorum/kriz sınıflaması Zeki'den, yanıt ve karar insandan.
- K4: kriz açıklaması, yazarla ilgili hassas konular.

**Bildirim/uyarı**
- Uzmana: onay çıktı/reddedildi, yarın yayın var ama görsel yok, özel güne 14 gün kaldı ve bağlı kitaplardan hiçbiri takvimde değil.
- Pazarlama müdürüne: onay bekleyen (Uyarılar rozeti), kriz sinyali (olumsuz yorum oranı son 6 saatte olağandışı; eşik ayarlı) → portal + e-posta.

**Onay ve yetki**
- `sayfa:sosyal-medya`; `ozellik:sosyal.duzenle` (taslak, takvim); `ozellik:sosyal.onay` (explicit); `ozellik:sosyal.topluluk` (yorum ekranı; yorumcu kişisel verisini görür — dar tutulur, explicit).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Aylık pazarlama planı | M18 | **Kodlanmadı** | İlk sürümde plan portal içinde elle/kitaptan kurulur |
| Kitap metni, alıntı, sosyal metin | CRM `new_kitapBase` (`new_sosyalmedyametni`, `new_ozet`, `new_kisabilgi`, `new_kitabinenonemlicumlesi`, `new_youtubelink`, `new_hedefkitle`) | 13.598 kitap; dolu oranları **ölçülecek** | — |
| Hazır görsel | Kitap Tasarım Stüdyosu pazarlama kiti (sosyal medya görselleri) — `editorial_studio_marketing.py` | Test sunucusu + VM'de | Yalnız stüdyoda işlenmiş kitaplar için |
| Hesaplar | CRM `new_markaBase.new_instagramkullaniciadi` (34 marka), `new_pazarlamamoduluBase.new_sosyalmedyahesabi` | Dolu oranı **ölçülecek** | X/TikTok/YouTube/LinkedIn hesap listesi yok → kullanıcı girer |
| Özel günler ve bağlı kitaplar | CRM `new_ozelgunlerBase` (93) + `new_new_kitap_new_ozelgunlerBase` (~820); tarih kuralları `seo_geo/seasons.py` | Test sunucusunda SEO Sezon takvimi olarak çalışıyor | — |
| Yeni çıkan kitaplar | CRM `new_ilkyayintarihi`; `management/sql/baski_oneri/crm_yeni_kitap.sql` | Var | — |
| Basında çıkan haber | M20 yansımaları / web_watch | web_watch **VM'de kapalı** | M20 elle kayıt |
| Etkileşim, erişim, takipçi | Resmî API: Instagram Graph API + Facebook Pages (kendi Business hesabı: içgörü, yorum), YouTube Data API v3, X API (kullandıkça öde), LinkedIn (ortaklık onayı), TikTok (uygulama denetimi) | Hiçbiri bağlı değil; hesap türü (Business/Creator) ve erişim **ölçülecek**; oran/kota ayrıntıları **doğrulanmadı** | İlk sürüm: platform dışa aktarım dosyası içe aktarma |
| Yorum / DM | Aynı resmî API'ler (yalnız kendi hesabımız) | Bağlı değil | Kazıma yok |
| Satış etkisi | Logo `V_SatisRaporu_<yıl>` | Donmuş kopya (2026-08-17) | Canlı Logo |

## 7. Diğer modüllerle bağ

- Girdi: M18 (aylık plan — kodlanınca takvime otomatik), M19 (onaylı görsel/metin), M15/M16 (lansman), M20 (basında çıkan haber → paylaşım), M23 (influencer içeriği paylaşımı), M27 (fuar/imza günü duyurusu), M25 Sezon takvimi (özel gün + kitap), Kitap Tasarım Stüdyosu.
- Çıktı: M18 (performans geri beslemesi), M51 (sipariş/kargo şikâyeti), M28 (marka algısı/kriz), M39 (trend), Uyarılar.

## 8. Kısıtlar

- **Otomatik yayın yok (ilk sürüm).** İş tanımındaki K1 «onaylı içerik otomatik yayınlanır» dış sisteme yazmaktır; kullanıcı açıkça karar verene kadar portal yalnız yayına hazır paket üretir. Karar verilirse yalnız resmî yayın API'si, yalnız onaylı içerik, her yayın `admin.audit`'e.
- Sosyal medya kazıma ve bot korumasını aşma yok; başkalarının hesabı resmî API'nin izin verdiği kadar (ör. Instagram iş hesabı keşfi) okunur. Gündem/trend için açık RSS (web_watch) ve kullanıcı girişi.
- Müşteri VM'inde web taraması kapalı (`WEB_WATCH_ENABLED=0`): gündem fırsatı kutusu VM'de yalnız özel gün + yeni kitap + M20 elle girilen haberle çalışır.
- CRM ve T-soft'a yazma yok; takvim `semantic_social_*`.
- Ekranda teknoloji adı yok (platform adları kalır; model adı yok, «Zeki AI önerisi»).
- Demo veri yok; boş hesapta «veri yok» yazar. Sayı tavanı yok.
- KVKK: yorumcu adı ve profil kişisel veridir; yorum metni yalnız kendi hesabımıza gelen yorumlarda ve iş gereği (yanıt, şikâyet aktarımı) saklanır, saklama süresi tanımlanır; raporlarda kişi adı geçmez. Alıntı paylaşımında telif: kitap metninden alıntı kısa tutulur, sözleşmede sosyal medya kullanımına engel madde (`new_sozlesmeBase.new_haklaraciklama` dolu) varsa uyarı.
- Yapay zekâ ile üretilmiş görselin ticari kullanımı: stüdyo görsel modelinin ticari lisansı bekleniyor (editor-book-visuals belleği); lisans gelene kadar üretilen görselin paylaşımı kullanıcı kararıdır, ekranda uyarı durur.

## 9. Kapsam önerisi

**İlk sürüm**
- İçerik takvimi: hesaplar (kullanıcı tanımlar), gönderi kartı (kitap, platform, tarih/saat, metin, görsel, durum: fikir → taslak → onayda → onaylı → yayınlandı).
- «Kitaptan içerik»: CRM metinleri + stüdyo görselleri → platforma göre Zeki taslağı (K2).
- Fırsat kutusu: özel gün (Sezon takvimi verisi), bu ay çıkan kitaplar, backlist'te uzun süredir paylaşılmamış çok satanlar, M20 yansımaları.
- Onay akışı ve yayına hazır paket (zip: görsel + metin + hashtag).
- Performans içe aktarma (platform dışa aktarım dosyası) → içerik türü × etkileşim raporu.

**Sonraki sürüm**
- Resmî API ile kendi hesap içgörüleri ve yorumları (yalnız okuma) → önemli yorum/kriz sınıflaması.
- Kullanıcı kararıyla onaylı içeriğin resmî API ile yayını.
- M18 kodlanınca plan → takvim otomatik aktarım ve geri besleme.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/seasons.py` (özel gün tarih kuralları, gün ↔ kitap bağı; `semantic_seo_seasons_days/books`).
- `backend/semantic_bridge/editorial_studio_marketing.py` (sosyal görsel ve metin kiti uçları).
- `backend/semantic_bridge/web_watch.py` (gündem/haber, bayrakla), `alerts.py` (kriz eşiği), `prefs.py` (kişinin takvim görünümü).
- `backend/semantic_bridge/management/sql/baski_oneri/crm_yeni_kitap.sql` (yeni çıkan kitaplar).

## 10. Uzmanlara sorulacak sorular

1. Hangi hesaplar var (imprint başına Instagram, X, YouTube, TikTok, LinkedIn) ve kim yönetiyor (içeride/ajans)?
2. Hesaplar Meta'da Business/Creator hesabı mı; hesap sahibi e-posta kim?
3. Bugün onay kimde (pazarlama müdürü mü, imprint editörü mü)?
4. Yorum/DM'deki sipariş-kargo şikâyeti bugün kime iletiliyor?
5. Otomatik yayın ileride istenir mi, istenirse hangi hesaplarda?

## 11. Başarı ölçütü

- Takvimin doluluk oranı: ay başında 4 hafta planlı.
- Kitaptan içerik taslağına süre (bugünkü süre sorulacak) → 5 dakikanın altı.
- Özel güne bağlı kitapların takvime giriş oranı (gün tarihinden 7 gün önce ≥ %80).
- Onay süresi (taslak → onay) medyanı.
- Önemli yorumların ilk yanıt süresi (API bağlanınca).

## 12. Uzman gözüyle en iyi sistem

*15 yıllık sosyal medya yöneticisi gözüyle.*

İyi yayınevleri sosyal medyayı **kitap takvimine** bağlar: her kitabın ön duyuru, çıkış, ilk yorumlar, yazar etkinliği, özel gün ve backlist canlandırma anları vardır; takvim bu anlardan kurulur, «bugün ne paylaşalım» diye düşünülmez. Sektördeki iyi araçların ortak yanı tek takvim + onay akışı + ortak gelen kutusu + içerik performansının içerik türüne göre okunmasıdır. Kitap dünyasında asıl erişim BookTok/Bookstagram topluluklarından ve yazarın kendi hesabından gelir; kurumsal hesap bu içerikleri toplayıp yeniden paylaşan bir merkezdir. TİMAŞ için mükemmel sistem: imprint hesaplarını tek takvimde tutan, kitabın CRM bilgisinden ve stüdyo görselinden dakikalar içinde platforma uygun taslak çıkaran, özel günleri iki hafta önceden hatırlatan ve onayı telefonda saniyeye indiren bir masa.

**Bir iş günü**
- 08:45 Telefon: «Bugün 3 paylaşım planlı, biri onayda, biri görselsiz». Görselsiz olan için stüdyo kitinden görsel seçer.
- 09:30 Masaüstü: «Fırsatlar» — Öğretmenler Günü'ne 14 gün var, bağlı 11 kitap, 2'si takvimde. 4 kitap için «kitaptan içerik» → taslaklar.
- 11:00 Pazarlama müdürü telefondan 5 kartı onaylar, birine not düşer.
- 12:00 Onaylı paketleri indirir, hesaplardan paylaşır, bağlantıyı yapıştırıp «yayınlandı» işaretler.
- 15:00 (API bağlıysa) Yorumlar: Zeki «kargo şikâyeti» diye işaretlediği 2 yorumu müşteri hizmetlerine aktarır; bir yazar hakkındaki olumsuz yorum için müdüre bilgi.
- 17:00 Haftalık rapor: alıntı görselleri kapak görsellerinden iyi gidiyor → gelecek haftanın takvimine not.

**«Bunu görürsem hemen kullanırım»**
1. Kitabı seçince platform başına hazır metin + stüdyo görseli.
2. Özel günlerin bağlı kitaplarla iki hafta önceden gelmesi.
3. Telefonda tek dokunuşla onay.

**«Bunu yaparsanız kullanmam»**
1. Onaysız ya da benim bilmediğim saatte otomatik yayın.
2. Herkese aynı, «yapay» duran metinler (platform ve imprint tonunu bilmeyen).
3. Takvime girmek için masaüstü şart koşan, telefonda çalışmayan ekran.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Fırsat: yeni çıkan kitaplar | — | `new_kitapBase.new_ilkyayintarihi`, `statuscode`, `new_OnemDerecesi` | — | SQL |
| Fırsat: özel gün | — | `new_ozelgunlerBase`, `new_new_kitap_new_ozelgunlerBase` | — | `seasons.py` kuralları |
| Fırsat: backlist çok satan, uzun süredir paylaşılmamış | `V_SatisRaporu_<yıl>` son 12 ay `[Miktar]` (iade düşülmüş) | `new_StokKodu` bağı | — | Satış = faturalı satır |
| Stokta olmayan kitabı önermeme | Stok bakiyesi (STLINE IOCODE) | `new_kitap_yayincilikstatusu` | — | Kural |
| Platform metni ve hashtag | — | `new_sosyalmedyametni`, `new_ozet`, `new_kitabinenonemlicumlesi`, `new_hedefkitle`, marka (`new_markaBase.new_name`) | Platform + imprint tonuna göre taslak (3 seçenek), hashtag önerisi | Metin işi |
| Alıntı çıkarma | — | Stüdyo okuması olan kitapta kitap metni | Kısa alıntı adayları (en fazla 2 cümle) | Telif için kısa tutulur |
| İçerik türü etiketi | — | — | Kapalı seçim: `kapak/alıntı/yazar/etkinlik/özel gün/kampanya/diğer` — tek token + olasılık | Rapor gruplaması |
| Yorum önemi (sonraki sürüm) | — | — | Kapalı seçim: `şikâyet-sipariş/şikâyet-içerik/soru/basın/olumlu/olumsuz/diğer` | Önceliklendirme |
| Aylık rapor yorumu | Satış ölçüsü | — | 5 cümle yorum | Rakamı yorumlar |

Model yalnız LLM kapısından: `rt.llm_for("sosyal")` (ekranda), gece etiketleme `rt.llm_for("sosyal", BATCH)`.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/social.py` (takvim, durum makinesi, fırsat kuralları), `social_sources.py` (CRM/Logo SQL, seasons okuma, performans dosyası ayrıştırıcı), `social_api.py` (`register`).

**Tablolar**
- `semantic_social_accounts` (id, tenant_id, platform, handle, imprint_crm_id NULL, owner_user, active)
- `semantic_social_posts` (id, tenant_id, account_id, crm_book_id NULL, occasion_key NULL, kind, planned_at, status [fikir/taslak/onayda/onaylı/yayınlandı/iptal], text, hashtags, asset_refs_json, published_url, approved_by, approved_at, created_by, updated_at)
- `semantic_social_post_events` (post_id, at, user, action, note)
- `semantic_social_metrics` (post_id NULL, account_id, day, impressions, reach, likes, comments, shares, saves, followers, import_id)
- `semantic_social_imports` (id, account_id, file_name, rows, created_by, created_at)

**Uçlar** (`/api/v1/social/*`): `GET meta`, `GET calendar?from=&to=&account=`, `GET opportunities?days=`, `POST posts`, `PATCH posts/{id}`, `POST posts/{id}/draft` (Zeki; `/api/v1/llm/jobs`), `POST posts/{id}/submit|approve|reject|published`, `GET posts/{id}/package.zip`, `GET/POST accounts`, `POST imports`, `GET report?month=`, `GET report/export.pdf`, `POST run-due` (SYSTEM).

**Ekranlar** — `src/canvas/social/` (`SocialCalendar.tsx`, `SocialPost.tsx`, `SocialOpportunities.tsx`, `SocialReport.tsx`, `SocialAccounts.tsx`); rota `/timas/sosyal-medya` (+ `/gonderi/:id`, `/firsatlar`, `/rapor`, `/hesaplar`). Menü: `pazarlama`, bölüm `section: 'İletişim'`, öğe `{ id: 'sosyal-medya', label: 'Sosyal medya', icon: Share2, hint: 'Takvim, onay ve performans' }`. Kitap sayfasına «Sosyal» sekmesi. Kampüs: M22 çalışan. Telefon: onay ve takvim gün görünümü öncelikli.

**Yetki** — `sayfa:sosyal-medya`; `ozellik:sosyal.duzenle`; `ozellik:sosyal.onay` (explicit); `ozellik:sosyal.topluluk` (explicit, sonraki sürüm). `access.py`: `("/api/v1/social/run-due", SYSTEM)`, `("/api/v1/social/", frozenset({page("sosyal-medya")}))`; FEATURE_RULES POST/PATCH `^/api/v1/social/(posts|accounts|imports)` → `ozellik:sosyal.duzenle`; approve ucun içinde `ozellik:sosyal.onay`; package.zip ve export → `ozellik:veri.disa-aktar`.

**Zamanlayıcı** — `scripts/server/timas-social.timer` her gün 07:00: fırsat listesi (özel gün LEAD, yeni kitap), «yarın yayın var ama görsel/onay yok» uyarısı. API bağlanınca gece içgörü çekme.

**Kabul testleri**
1. Özel gün bağlı kitap sayısı: fırsat kartındaki sayı = `SELECT COUNT(DISTINCT kg.new_kitapid) FROM Timas_MSCRM.dbo.new_new_kitap_new_ozelgunlerBase kg JOIN Timas_MSCRM.dbo.new_ozelgunlerBase g ON g.new_ozelgunlerId = kg.new_ozelgunlerid WHERE g.new_name = N'<gün>'` (aynı adlı günler birleşik; SEO Sezon takvimiyle aynı sonuç).
2. Bu ay çıkan kitaplar = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitapBase WHERE statuscode = 1 AND new_ilkyayintarihi >= '<ay başı>' AND new_ilkyayintarihi < '<sonraki ay>'`.
3. Backlist çok satan listesi: ilk 10 kitabın son 12 ay net adedi `V_SatisRaporu_211/411` üzerinde `[Yıl]*12+[Ay]` penceresi, `[Satır Türü]=N'Malzeme'`, iade düşülmüş doğrudan SQL ile birebir.
4. Takvim sayımı: ekrandaki ay sayıları = `SELECT status, COUNT(*) FROM semantic_social_posts WHERE planned_at >= … GROUP BY status`.
5. İçe aktarma: dosyadaki toplam erişim = `SELECT SUM(reach) FROM semantic_social_metrics WHERE import_id = '<id>'`.
6. Marka hesap alanı: hesap listesine önerilen Instagram kullanıcı adları = `SELECT new_name, new_instagramkullaniciadi FROM Timas_MSCRM.dbo.new_markaBase WHERE NULLIF(LTRIM(new_instagramkullaniciadi),'') IS NOT NULL`.
7. VM: web bayrağı kapalıyken gündem kutusunda web kaydı yok; ekran metinlerinde model/teknoloji adı yok.

**Bağımlılık** — M18'i beklemeden kodlanır (plan portal içinde kurulur); M18 gelince `plan → posts` aktarımı eklenir. SEO Sezon takvimi verisi (test sunucusunda var) okunur; VM'de SEO modülü yoksa özel gün hesabı doğrudan CRM'den (`seasons.py` saf işlevleri) yapılır.

**Tahmini büyüklük** — L (3+ gün).
