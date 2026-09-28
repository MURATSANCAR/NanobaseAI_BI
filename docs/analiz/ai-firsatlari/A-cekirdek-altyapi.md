# A — Çekirdek ve altyapı: Kampüs, Analiz, Yönetim, Altyapı ve destek, Zeki AI çekirdeği, NanobaseAI Destek

Kaynak: `ai-analiz-okuma` ağacı, main `f26e11d6` (salt okuma). Dosya yolları bu ağacın köküne göredir.
Kısaltmalar: **D** = değer (1–5), **Z** = zorluk (S ≤1 gün · M 2–5 gün · L 6+ gün), `choose` = `QueuedLlm.choose` kapalı küme seçimi
(tek harf + olasılık, `docs/analiz/llm-choose.md`), «kapı» = `rt.llm_for(modül, öncelik)` LLM kapısı, «guard» = model metnindeki her
sayıyı olgu listesinde arayan denetim (`backend/semantic_bridge/marketing/guard.py`, `pazar.check_sentence`, `support.fill_draft`).

## Kapsam ve sayım (atlanan ekran yok)

| Alan (menü `navModel.ts`) | Menü öğesi | Rota (`App.tsx`) | Ekran / sekme |
|---|---|---|---|
| Kampüs (`kampus`) | 1 (`/`) | 1 | 1 ekran, 12 bölüm (soru kutusu, arama/rehber, bülten, ajanda, eğitimlerim, bildirim, profil, alkış, oda, yeni çıkanlar, ana modüller, «Tüm modüller» paneli) + 8 canlı olmayan modül kutusu |
| Analiz (`analiz`) | 7 (genel-bakis, panolar, planli-raporlar, uyarilar, pazar-arastirma, pazar-rakipler, pazar-raporlar) | 8 (`/genel-bakis`, `/panolar`, `/planli-raporlar`, `/uyarilar`, `/pazar-arastirma`, `/:section`, `/raporlar/:id`, `/ozet/:donem`) | 14 (Genel bakış; Panolar; Planlı raporlar liste/yeni + Excel taslağı; Uyarılar Kurallar + Yeni kural; Pazar: Özet, Rakipler, Emsal bul, Kategori eşlemesi (3 alt sekme), Sektör raporları, Rapor rakamları, Aylık özet) |
| Altyapı ve destek (`altyapi`) | 4 | 4 (`/sistem-durumu`, `/veri-guvenligi`, `/musteri-destek`, `/zeki-kalite`) | 25 sekme (M48: 6, M49: 7, M51: 7, M50: 5) |
| Yönetim (`yonetim`) | 4 | 4 (`/veri-sozlugu`, `/onaylar`, `/es-anlamlilar`, `/yonetim`) | 17 (Sözlük 3, Onaylar 1, Eş anlamlılar 3, Portal ayarları 10 sekme; Yetkiler içinde 3 alt görünüm) |
| NanobaseAI Destek (`apps/destek`) | — (ayrı port :8446) | 25 ekran rotası (`helpdesk/desk/src/router/index.ts`; boş/kök yönlendirme ve «bulunamadı» hariç) + `/app` masaüstü | 13 ekran grubu + 2 arka plan işi + çeviri hattı |
| **Toplam** | **16 menü öğesi** | **17 portal rotası + 26 destek yolu** | **57 portal ekranı/sekmesi + 13 destek ekran grubu** |

Zeki AI çekirdeğinin ekran dışı parçaları (sohbet hattı `app.py`, `chat_scope.py`, `chat_topics.json`, katalog adayı/çürütme hattı)
ilgili ekranın altında anlatıldı.

---

## Kampüs — Ana sayfa (`/`, `src/canvas/kampus/KampusPage.tsx`)

### Zeki AI soru kutusu (Kampüs sahnesi, KampusPage.tsx:410–460)
- **Ne yapıyor:** Soruyu `/genel-bakis?soru=…` adresine taşır; cevabı Genel bakış verir. 4 sabit hızlı örnek (net ciro, 5 kanal, aylık ciro, iade oranı; KampusPage.tsx:63–68). Yetki `zeki.soru` + Genel bakış sayfası.
- **Kim:** Herkes; en çok yönetici/CFO («bu ay nasıl gidiyoruz»), satış ve muhasebe.
- **Bugün AI:** Dolaylı — cevap Genel bakıştaki sohbet hattından. Kutunun kendisi modelsiz.
- **Beklenti:** Kişinin rolüne göre örnek soru; cevabın Kampüs'te kısa kartla görünmesi (sayfa değiştirmeden); sesli soru (telefonda); «dün ne oldu?» tarzı günlük özet.
- **Yapabileceklerimiz:**
  - *Role göre örnek sorular* — kişinin sayfa yetkisi (`usePageAccess`) + bağlı konular (`chat_topics.json` `data` dolu olanlar) + son 30 gün en çok cevaplanan sorular (`sl_query_log`, answer_type=ANSWER) → kural ile aday, `choose` ile «bu role uygun mu» süzgeci gerekmez; basit sıralama yeter. Teknik: kural + kayıt istatistiği (model yok). D3 · Z S (1 g) · Risk: başkasının sorusunu göstermek — yalnız soru kalıbı (terim), kişi adı yok.
  - *Kampüs'te kısa cevap kartı* — aynı `/api/v1/ask`, yalnız `summary` + tek KPI; «ayrıntı» Genel bakışa. D3 · Z S (1–2 g) · Risk: yok (aynı hat).
  - *Sesli soru* — telefonda konuşma → metin (yerel konuşma tanıma modeli GPU'da; bugün kurulu olduğu **doğrulanmadı**) → aynı soru hattı. D3 · Z M (4–5 g) · Risk: ses kaydı saklanmaz (KVKK), yalnız metin `sl_query_log`'a.
- **Eksik:** Kutu metni «Satış, ciro, iade, tahsilat ve cari sorularını Logo verisinden cevaplarım» diyor (KampusPage.tsx:421); 2026-09-28 kapsam genişlemesiyle (bütün modüller) uyumsuz görünüyor — bağlı konular listesinden üretilmeli.

### Omni arama ve Timaş Rehber (KampusPage.tsx:130–146, 527–640)
- **Ne yapıyor:** Arama kutusu önce rehberde (ad, ünvan, birim, kat, dahili) süzer; eşleşme yoksa soruyu Zeki'ye yollar (KampusPage.tsx:140). Rehber CRM ∩ AD ∩ son giriş kişileri (`people.py`), kat süzgeci, CSV indirme (M49'a dışa aktarma bildirimi).
- **Kim:** Herkes; santral/asistanlar, yeni çalışanlar.
- **Bugün AI:** Yok (sözcük eşleşmesi).
- **Beklenti:** «Telif ödemelerine kim bakıyor?», «Trendyol'dan kim sorumlu?» gibi **iş tarifinden kişi bulma**; yazım hatasına dayanıklı arama; aramanın soru mu kişi mi olduğunu doğru ayırma.
- **Yapabileceklerimiz:**
  - *İş tarifinden kişi* — kişinin ünvan+birim+sorumlu olduğu kayıtlar (M27 ajanda sorumlusu, M51 ekip, portal rol adları) → gömme benzerliği (`BI_EMBED_URL`, bge-m3; destek FAQ'da zaten kullanılıyor, `support_api.py:53`) ile ilk 5 kişi, gerekçe kurallı («birimi: Telif»). D4 · Z M (3 g) · Risk: kişisel veri modele gitmez (yalnız ünvan/birim metni gömülür, ad/cep gömülmez).
  - *Soru mu kişi mi* — bugünkü kural (rakam/eşleşme) yerine `choose(["kişi/dahili araması","şirket verisi sorusu"])`, yalnız kural kararsız kalınca. D2 · Z S (0,5 g).
- **Eksik:** Kat/dahili hiçbir kaynakta yok, profilden giriliyor (bellek `crm-systemuser-directory`); rehberin doluluk oranı ekranda yok.

### Sesli bülten (BulletinCard.tsx; üretim Yönetim → Sesli bülten)
- **Ne yapıyor:** Yayımlanmış son bülteni çalar (`semantic_kampus_bulletins`). Yönetici ses yükler ya da **metinden üretir**: metin stüdyoya gider, GPU'da seslendirilir, taslak bülten olur (`bulletins.py:308 start_generation`, `BulletinsAdmin.tsx:124`).
- **Kim:** Herkes dinler; kurumsal iletişim/İK yazar.
- **Bugün AI:** Var — seslendirme (metin→ses), GPU sırasında. Bülten **metni** elle yazılıyor.
- **Beklenti:** Haftanın olaylarından (yeni çıkan kitaplar, etkinlikler, duyurular, alkışlar) bülten metninin hazırlanması; kısa/uzun sürüm; ses içinde bölüm atlama.
- **Yapabileceklerimiz:**
  - *Bülten metni taslağı* — kaynak: M27 ajanda (`/api/v1/events/me/agenda` genel hâli), alkış duvarı (`greetings.py`), yeni baskılar (Logo/CRM kitap kartı, yayın tarihi), M57 eğitim duyuruları → olgu listesi → model 90 sn'lik konuşma metni yazar → guard (her ad/sayı olgu listesinde) → yönetici düzeltir → mevcut seslendirme. D3 · Z M (3 g) · Risk: kişisel veri (doğum günü vb.) yalnız kişinin izniyle; guard düşen cümle sayısını gösterir.
- **Eksik:** Özet/bölüm başlıkları (summary alanı) elle; transkript yok (erişilebilirlik).

### Önemli günler ve ajanda (AgendaCard.tsx), Eğitimlerim (hr/learning/LearningCard)
- **Ne yapıyor:** Ajanda: kişinin sorumlu olduğu fuar/etkinlik/görevler (M27). Eğitimlerim: yaklaşan oturum, dolacak zorunlu eğitim, bekleyen anket (M57).
- **Kim:** Pazarlama/etkinlik ekibi, herkes (eğitim).
- **Bugün AI:** Yok.
- **Beklenti:** «Bu hafta ne yapmalıyım?» tek paragraf; gecikme riski olan görevin öne çıkması.
- **Yapabileceklerimiz:** *Kişisel «Bugün» özeti* (aşağıda Bildirim zili ile birlikte). Ayrı öneri yok.
- **Eksik:** —

### Bildirim zili (KampusPage.tsx:296–370)
- **Ne yapıyor:** Alkış kutusu, kategori profili onayı bekleyen kitaplar (H1), onay bekleyen okur segmenti ve okunamayan okur kaynağı (H2).
- **Kim:** Herkes; editör, okur/CRM ekibi.
- **Bugün AI:** Yok (sayaçlar).
- **Beklenti:** Bütün modüllerden «bana düşen iş» tek listede, önceliğe göre; bir cümlelik ne/neden.
- **Yapabileceklerimiz:**
  - *Kişisel «Bugün» özeti* — kaynak: uyarı rozetleri (`alerts`), kurumsal e-posta atamaları (`mailbox`), ajanda, eğitim, onay kuyrukları (H1, H2, Onaylar, M39 rakam onayı, M19 içerik onayı), destek SLA riski. Sayılar kurallı; model 2–3 cümle + öncelik sırası yazar; guard. D4 · Z M (4 g) · Risk: yetki — her kaynak kişinin sayfa yetkisiyle süzülür (köprüde); model yalnız başlık/sayı görür.
- **Eksik:** Zil bugün yalnız 3 kaynağı topluyor; diğer modüllerin onay kuyrukları Kampüs'e gelmiyor.

### Profil (ProfileDialog.tsx, PhotoCropper.tsx)
- **Ne yapıyor:** CRM'den ünvan/birim; kat, dahili, masa, fotoğraf kişinin kendisince.
- **Kim:** Herkes.
- **Bugün AI:** Yok.
- **Beklenti:** Düşük; fotoğraf kırpmada yüz ortalama.
- **Yapabileceklerimiz:** *Yüz ortalamalı kırpma* — tarayıcıda yerel yüz tespiti. D1 · Z S · gerek yok denecek kadar düşük değer; önermiyoruz.
- **Eksik:** —

### Alkış duvarı (KampusPage.tsx:640–720, `greetings.py`), Oda kartı (rooms/RoomsCard.tsx, `rooms.py`)
- **Ne yapıyor:** Günde kişi başı bir alkış, duvar ve bildirim; odaların anlık durumu ve rezervasyon.
- **Kim:** Herkes.
- **Bugün AI:** Yok.
- **Beklenti:** Düşük. Oda için «yarın 14'te 6 kişilik boş oda» doğal dil rezervasyonu.
- **Yapabileceklerimiz:** *Doğal dil oda rezervasyonu* — cümle → (tarih, saat, süre, kişi) ayrıştırma kuralla (planlı raporların `parse_prompt` yaklaşımı, `reports.py:151`), model yalnız kural düşerse; boş oda SQL'den. D2 · Z S (1 g). Alkış metnine model **önerilmez** (samimiyet).
- **Eksik:** —

### Matbaadan yeni çıkanlar (KampusPage.tsx:722–760)
- **Ne yapıyor:** İki **sabit demo kitap** (resim ve ad kodda). Kaynağa bağlı değil («gerçek katalog sonra bağlanacak»).
- **Kim:** Herkes; satış ve pazarlama.
- **Bugün AI:** Yok.
- **Beklenti:** Gerçek yeni baskılar; kitabın tek cümlelik tanıtımı.
- **Yapabileceklerimiz:** *Yeni baskı kartı + tek cümle tanıtım* — Logo stok girişi/ilk fatura + CRM `new_kitapBase` (`new_ozet`, `new_kitapspotu`) → model 1 cümle, guard (alıntı/sayı yok). D2 · Z S (1 g).
- **Eksik:** **Ciddi:** çalışmayan demo içerik; kullanıcı kuralı «çalışmayan düğme bırakılmaz» ile çelişiyor.

### Ana modüller kutuları ve «Tüm modüller» paneli (KampusPage.tsx:481–525, `stitch/ModulesMenu.tsx`)
- **Ne yapıyor:** 6 ana modül kutusu (`GROUP_HOME`); panel 78 modülün 70'ini «Çalışan», 8'ini «Yakında» listeler (`modules.json` × `LIVE`).
- **Kim:** Herkes.
- **Bugün AI:** Yok.
- **Beklenti:** «Fatura itirazını nereden takip ederim?» → doğru ekran.
- **Yapabileceklerimiz:** *Ekran bulucu* — menü `hint`+`keywords` (navModel.ts) gömülür; soru → en yakın 3 ekran (kişinin yetkisindekiler). Zeki sohbeti «nasıl/nerede» sorularında da bunu kullanır. D3 · Z S (1–2 g) · Risk: yok.
- **Eksik:** —

---

## Zeki AI çekirdeği — Genel bakış ve sohbet hattı (`/genel-bakis`, `src/pages/BiCanvasPage.tsx`)

### Genel bakış (CFO kanvası + soru kutusu)
- **Ne yapıyor:** KPI kartları: net ciro, aylık seyir, kanal dağılımı (toptan/perakende/diğer/iade), en büyük cari, kanıt & kaynak (`stitch/screens.ts` ~249–310). Soru kutusu `/api/v1/ask`'e gider; sorular kuyruğa girer; cevap karar kartına düşer; belirsiz kelime çipleri (`interpret.ts`), Doğru/Kısmen/Yanlış geri bildirimi (`components/AnswerFeedback.tsx` → M50), «Panoya ekle» (grafik türü kuralla, `board/Chart.tsx:105 suggestChart`).
- **Kim:** CFO/genel müdür, muhasebe müdürü, satış müdürü, yönetici.
- **Bugün AI (hat, `backend/semantic_bridge/app.py`):**
  - Kimlik/selam kalıpla, modelsiz (`chat_scope.py:86`); kapsam/konu sınıflama modelle: `chat_scope.classify` → `llm.chat` + JSON (`chat_scope.py:241`, çağrı `app.py:933`), yalnız sertifikalı kavram yoksa.
  - Çözümleyici + dil havuzu + derleyici; SQL taslağını model yazar (router/derleyici, tablo seçici `QueuedLlm(..., purpose="nl2sql:selector")` `app.py:336`), kapı ve eleştirmen (`semantic_layer/runtime/critic.py`) kontrol eder.
  - Cevap özeti: `summary_mode="llm"` ise model 1–3 cümle yazar (`app.py:799–804`), **varsayılan `fast`** (kurallı, `semantic_layer/config.py:50`).
  - Takip sorusu bağlamı (`conversation.compose_followup`), belirsizlik yorumları (`runtime/compiler.py` interpretations).
- **Beklenti:** Rakamın **nedenini** söylemesi («ciro neden %12 düştü?» → kanal/cari/kitap katkısı); sonraki mantıklı soruların önerilmesi; grafik + kısa yorum; «bu rakam neye göre?» sorusuna sade açıklama; bütün modüllerden soru (pazarlama, İK, destek…).
- **Yapabileceklerimiz:**
  - *Modül verisini sohbete bağlama* — `chat_topics.json`'da `data: []` olan 9 konu (pazarlama, dijital, eticaret, okur, destek, ik, risk, yonetim, isletim) bugün «henüz veri bağlı değil» cevabı alıyor. Mekanizma (örnek başına SQL değil): portalın `semantic_*` tablolarını kataloğa **veri alanı** olarak profillemek (tarayıcı + sertifika, `data_domains.json` kuralı) ya da modül başına **adlandırılmış sorgu kalıpları** (M48/M49 analizindeki gibi) + `choose` ile soru→kalıp eşleme. Rakam SQL'den. D5 · Z L (8–12 g, modül modül) · Risk: İK/KVKK alanları rolle kısıtlı (veri alanı–rol bağı zaten var, `AccessAdmin.tsx:727`); yetki dışı soru `NOT_PERMITTED` olarak M49'a düşer.
  - *«Neden» ayrıştırması* — iki dönem farkını kanal/cari/kitap/kategori boyutlarında SQL ile katkıya böl (sabit sorgu değil, derleyicinin bildiği boyutlar üzerinden genel «fark ayrıştırma» planı); model en büyük 3 katkıyı cümleye çevirir; guard. D5 · Z M (5 g) · Risk: rakamı model üretmez; boyut seçimi katalogdan.
  - *Önerilen sonraki sorular* — cevaptaki ölçü/boyuttan katalogda komşu kavramlar → 3 aday soru; `choose` gerekmez, kural + sık sorulanlar. D4 · Z S (2 g).
  - *Denetimli anlatı özeti* — `summary_mode=llm`'i guard ile açmak (özet cümlesindeki her sayı sonuç satırlarında aranır; tutmayan cümle düşer). D4 · Z S (1–2 g) · Risk: gecikme — özet ayrı istekle sonradan gelsin.
  - *Kapsam sınıflayıcıyı `choose`'a taşımak* — `chat_scope.classify` JSON-chat yerine niyet ve konu için iki kapalı küme çağrısı; olasılık kaydı `gate.chatScope`'a; eşik `admin.conf`. D3 · Z S (1 g) · Risk: golden set ile önce/sonra (M50).
  - *KPI kartı açıklaması* — Genel bakış kartlarının altına «geçen aya göre ne değişti» tek cümle (sayı SQL'den, `cfo` verisinden). D4 · Z S (1–2 g).
  - *Sesli soru / telefon* — Kampüs'teki öneriyle ortak.
- **Eksik:** Özet varsayılanı kurallı; bağlı olmayan 9 konuda sohbet işe yaramıyor; cevap kartında «nasıl hesaplandı» sade dili teknik (SQL) ağırlıklı.

---

## Analiz — Panolar, Planlı raporlar, Uyarılar

### Panolar (`/panolar`, `src/canvas/board/BoardScreen.tsx`, `backend/semantic_bridge/board.py`)
- **Ne yapıyor:** Kişisel pano: soru sor → sonuç grafiğe → «Panoya ekle»; kart = SQL + grafik + yer; sonuç sunucuda (`semantic_board_cards.result_json`), elle/saatlik/günlük yenileme (`board.py:349 run_due`), KPI karşılaştırma eki («geçen yıla göre», BoardScreen.tsx:575), «bugünkü motorla yeniden sor» (609), CSV/Excel/PDF.
- **Kim:** Yönetici, CFO, satış/pazarlama müdürü, finans analisti.
- **Bugün AI:** Soru → SQL (Genel bakışla aynı hat). Grafik türü kuralla (`Chart.tsx:105`). Kartta yorum yok.
- **Beklenti:** Açılışta «bu hafta panomda ne değişti?»; olağan dışı kartın işaretlenmesi; kart için doğru grafik ve başlık; «bu kartı yöneticime özetle».
- **Yapabileceklerimiz:**
  - *Kart farkı ve anlatımı* — yenilemede önceki `result_json` ile yeni sonuç karşılaştırılır (satır/kolon eşleme kodla), en büyük değişimler SQL/kod ile; model kart başına 1 cümle; guard. D5 · Z M (3 g) · Risk: önceki sonuç yoksa «ilk koşu» der; sayı uydurma yok.
  - *Anomali rozeti* — zaman serisi kartlarında beklenen aralık (sunucudaki zaman serisi tahmin modeli TimesFM ya da mevsimsel istatistik) dışına çıkan son nokta işaretlenir; model yalnız açıklama. D4 · Z M (3–4 g) · Risk: kısa serilerde yanlış alarm — en az 24 nokta kuralı.
  - *Pano özeti (PDF/e-posta ile)* — bütün kartların fark cümleleri → yönetici özeti paragrafı; guard. D4 · Z S (2 g).
  - *Kart başlığı önerisi* — soru metninden kısa başlık (model), kişi onaylar. D2 · Z S (0,5 g).
- **Eksik:** Kartlar arası filtre (dönem/kanal) yok; her kart ayrı soru.

### Planlı raporlar (`/planli-raporlar`, `canvas/reports/ReportsScreen.tsx`, `ExcelDraft.tsx`, `backend/semantic_bridge/reports.py`)
- **Ne yapıyor:** «Her pazartesi 08:00'de … Excel'i x@y'ye gönder» cümlesi → plan (zaman, sıklık, alıcı, biçim, soru) **regex ile** (`reports.py:151 parse_prompt`); her koşuda soru yeniden sorulur; Excel/CSV + özet e-posta (satır sayısı, ilk para kolonunun toplamı, `reports.py:870 mail_summary`). Excel taslağı: 50 satır önizleme, kolon düzeni, «ne değişsin» cümlesi (`refine_plan`).
- **Kim:** Finans/muhasebe, satış operasyonu, yönetici asistanı.
- **Bugün AI:** Var — Excel taslağında düzeltme cümlesi önce kurallı kolon komutlarıyla, olmazsa model JSON ile yeni soru + kolon düzeni (`reports.py:566–606`, çağrı `app.py:3328`, modül `reports`). Plan ayrıştırma modelsiz.
- **Beklenti:** E-postada «bu hafta ne değişti» 3 madde; olağan dışı satırların vurgusu; karmaşık zaman cümlelerinin («her ayın son iş günü») anlaşılması; rapor başlığının önerilmesi.
- **Yapabileceklerimiz:**
  - *E-posta yorumu* — önceki koşunun dosyası/sonucu (satır anahtarıyla) ve yeni sonuç; farklar kodla; model 3 madde; guard; e-postada «Zeki AI yorumu» kutusu. D5 · Z M (3 g) · Risk: dış gönderim zaten iç alıcıya; yorum kapalı/açık ayarı.
  - *Plan cümlesi yedeği* — `parse_prompt` alanı bulamazsa (saat yok, «son iş günü», «çeyrek sonu») model JSON; sonuç formda gösterilir, kişi onaylar. D3 · Z S (1 g).
  - *Olağan dışı satır işaretleme* — Excel'de önceki döneme göre ±%X ve z-skoru kodla; renk; model yok. D3 · Z S (1 g).
- **Eksik:** Plan ayrıştırması yalnız kalıp; aylıkta 28'den büyük gün 28'e kırpılıyor (`reports.py:180`) — «ayın son günü» yok.

### Uyarılar — Kurallar ve Yeni kural (`/uyarilar`, `?panel=yeni`; `canvas/alerts/AlertsPanel.tsx`, `backend/semantic_bridge/alerts.py`)
- **Ne yapıyor:** Kural = soru + koşul (büyük/küçük) + **sabit eşik** + alıcı; köprü düzenli sorar, eşik aşılınca e-posta, hatırlatma (`alerts.py:335 check`, `437 render`). Yeni kural cümlesi tarayıcıda regex ile ayrışır (`AlertsPanel.tsx:53 parseRule`).
- **Kim:** CFO, finans kontrolörü, satış müdürü, stok/tedarik.
- **Bugün AI:** Yalnız kuralın sorusu Zeki hattından cevaplanır; eşik ve bildirim modelsiz.
- **Beklenti:** Eşiği kendisi önermesi («normalde 800 bin–1,1 Mn arası»); anormal düşüş/artışta eşiksiz uyarı; e-postada **neden** («iade artışı 3 carinin …»); gereksiz uyarının azalması.
- **Yapabileceklerimiz:**
  - *Eşik önerisi* — kuralın sorusu geçmiş 12–24 dönem için koşulur (dönem kaydırma derleyicide), dağılım kodla; öneri «olağan aralık» + p90; kişi seçer. D4 · Z M (2–3 g) · Risk: dönem kaydırması desteklenmeyen soruda öneri yok (sessiz tahmin yok).
  - *Beklenen aralık uyarısı (anomali türü kural)* — yeni koşul türü «olağan dışı»: zaman serisi tahmini (TimesFM sunucuda) ya da mevsimsel median±MAD; dışına çıkınca uyarı. D5 · Z M (4–5 g) · Risk: yanlış alarm oranı M50 karnesinde ölçülür; ilk sürüm yalnız ekranda, e-posta sonra.
  - *Uyarı e-postasında neden* — eşik aşılınca «Neden» ayrıştırması (Genel bakış önerisiyle aynı mekanizma) → 2 cümle; guard. D5 · Z M (paylaşımlı, +1 g).
  - *Kural cümlesi yedeği* — `parseRule` eşik/koşul bulamazsa model JSON; kişi onaylar. D2 · Z S (0,5 g).
- **Eksik:** Uyarı olayları ekranda eğilim grafiği olmadan liste; «sessize al» / ertele yok (doğrulanmadı — kod taramasında görülmedi).

---

## M39 Pazar ve rakip (`/pazar-arastirma/*`, `canvas/pazar/*`, `backend/semantic_bridge/pazar.py`, `pazar_api.py`)

Model kapıdan: `rt.llm_for("pazar", …)`, eşleme/çıkarım/özet BATCH, emsal NORMAL (`pazar_api.py:15, 96–115`).

### Özet (`/pazar-arastirma`, MarketHome.tsx)
- **Ne yapıyor:** Yönetim özeti (onaylı son dönem), TİMAŞ iç göstergeleri (Logo sell-in, kategori/kanal büyümesi), onaylı sektör rakamları, eşleme kapsamı; tazelik şeridi; haftalık kaynak okuma.
- **Kim:** Yayın yönetmeni, pazarlama müdürü, genel müdür, DYK.
- **Bugün AI:** Doğrudan yok (özet BriefEditor'dan gelir).
- **Beklenti:** «Pazarda bizim kategorimiz büyürken biz neden küçüldük?» sorusuna cevap; fırsat/tehdit listesi.
- **Yapabileceklerimiz:** *Kategori fırsat skoru* — onaylı sektör büyümesi (rapor rakamları) − TİMAŞ kategori büyümesi (Logo) + rakip yeni kitap yoğunluğu (CRM `new_rakipkitapBase` CreatedOn) → kurallı skor; model gerekçe cümlesi; guard. D4 · Z M (3 g) · Risk: sell-in ≠ pazar payı uyarısı korunur.
- **Eksik:** Rakip verisinin kaynağı/tazeliği bilinmiyor (pazar.py:5–7); dış tarama bilinçli yok.

### Rakipler ve izlenen rakipler (`/pazar-arastirma/rakipler`, CompetitorMatrix.tsx)
- **Ne yapıyor:** Yayınevi × kategori fiyat/sayfa/format matrisi (TİMAŞ aynı ölçülerle), izlenen rakip listesi, yayınevi kayıtları.
- **Kim:** Fiyatlama, yayın yönetmeni, pazarlama.
- **Bugün AI:** Yok (medyan/çeyrek SQL).
- **Beklenti:** «Bu kategoride fiyatımız pazarın üstünde mi?» tek cümle; rakibin son dönem hamlesi (yeni seri, fiyat bandı kayması).
- **Yapabileceklerimiz:** *Rakip hareket özeti* — ay bazında rakip yeni kayıt, fiyat bandı değişimi (SQL) → model 3 madde; guard. D3 · Z S (2 g). *Yayınevi adı normalleştirme* — aynı yayınevinin farklı yazımları: benzerlik (kelime + gömme) → birleştirme önerisi, insan onayı. D3 · Z S (1–2 g).
- **Eksik:** —

### Emsal bul (`/pazar-arastirma/emsal`, ComparablesScreen.tsx)
- **Ne yapıyor:** Kitap adı/konu ya da TİMAŞ kitabı → kurallı süzgeç (kategori, sayfa ±, fiyat ±) + ortak sözcük; ilk adaylar Zeki AI ile «çok benzer / kısmen / benzemiyor» (`pazar.py:1050–1058 choose`), gerekçe kurallı.
- **Kim:** Editör, yayın kurulu, fiyatlama (M9), ilk baskı (M10).
- **Bugün AI:** Var — `choose` ile konu benzerliği sınıfı.
- **Beklenti:** Özet/konu metninden anlamca yakın kitaplar (sözcük ortak olmasa da); emsalin satış seyri.
- **Yapabileceklerimiz:** *Gömme ile aday genişletme* — ortak sözcük yerine (ek olarak) `new_ozet`/`new_kitapspotu` ve rakip tanıtım metni gömmesi (bge-m3) ile ilk 50 aday, sonra bugünkü `choose`. D4 · Z S (2 g) · Risk: rakip tanıtım metni kısa — kapsam oranı gösterilsin. *Emsalden baskı/fiyat ipucu* M9/M10'a bağlantı (rakam SQL'den). D3 · Z S.
- **Eksik:** —

### Kategori eşlemesi (`/pazar-arastirma/kategori-esleme`, CategoryMap.tsx — Öneri/Belirsiz/Karar alt sekmeleri)
- **Ne yapıyor:** Rakip serbest metin kategori → TİMAŞ kategorisi; önce ad eşleşmesi, sonra `choose` (`pazar.py:706–745 suggest_mapping`), eşik altı «belirsiz»; karar insanda.
- **Kim:** Kategori sorumlusu, pazarlama analisti.
- **Bugün AI:** Var — `choose` + olasılık.
- **Beklenti:** Toplu onay (yüksek olasılıklılar tek tık), H1 kategori ağacıyla tutarlılık.
- **Yapabileceklerimiz:** *Hiyerarşik seçim* — ağaç derinse önce üst, sonra alt düğüm (`llm-choose.md` «ne zaman kullanılmaz»). D3 · Z S (1 g). *Toplu onay eşiği* `p≥0.90, margin≥0.50` ayarla. D3 · Z S (0,5 g).
- **Eksik:** —

### Sektör raporları ve Rapor rakamları (`/pazar-arastirma/raporlar`, `/raporlar/:id`; ReportsScreen.tsx, ReportFigures.tsx)
- **Ne yapıyor:** PDF/Excel/CSV yükleme; sayfa sayfa rakam çıkarımı (`pazar.py:1352 extract_page`, model `chat`), her rakam sayfa metninde birebir aranır, bulunmayan atılır; insan onay/düzelt/ret.
- **Kim:** Pazar analisti, yayın yönetmeni.
- **Bugün AI:** Var — belge okuma (metinli PDF), yapılandırılmış çıkarım + birebir doğrulama.
- **Beklenti:** Taranmış PDF'in de okunması; tablo/grafik içindeki rakamlar; raporun 5 cümlelik özeti; önceki yılın aynı raporuyla karşılaştırma.
- **Yapabileceklerimiz:**
  - *Taranmış sayfa okuma (OCR)* — bugün «metin yok» işaretleniyor (`pazar_sources.py:23, 307`). GPU'daki görsel-dil modeliyle sayfa görüntüsünden metin; çıkarım aynı birebir doğrulamayla (OCR metninde arama). D4 · Z M (4–5 g) · Risk: OCR hatası rakamı bozar → OCR'lı rakam «görüntüden» etiketli, onay zorunlu.
  - *Rapor özeti* — onaylı rakamlar + sayfa alıntıları → 5 cümle, her cümle kaynak sayfasına bağlı (`check_sentence` aynen). D3 · Z S (1 g).
  - *Yıl yıl eşleme* — aynı gösterge adı farklı raporlarda (gömme benzerliği) → seri. D3 · Z M (2–3 g).
- **Eksik:** Taranmış PDF okunmuyor.

### Aylık yönetim özeti (`/pazar-arastirma/ozet/:donem`, BriefEditor.tsx)
- **Ne yapıyor:** Zeki AI taslağı (`pazar.py:1738 draft_brief`); her madde bir kaynağa bağlı, sayı kaynağın değeriyle tutmalı (`check_sentence` 1665, `check_brief` 1704); yazan onaylayamaz; DYK'ya gider.
- **Kim:** Pazarlama müdürü (yazar), genel müdür (onay).
- **Bugün AI:** Var — denetimli taslak.
- **Beklenti:** Geçen ayın özetine göre ne değişti; aksiyon maddeleri sahibiyle.
- **Yapabileceklerimiz:** *Önceki özetle fark bölümü* — önceki onaylı özetin kaynak değerleriyle karşılaştırma (kod) → «değişen» bölümü. D3 · Z S (1 g).
- **Eksik:** —

---

## M48 Sistem durumu (`/sistem-durumu`, `canvas/it-ops/*`, `backend/semantic_bridge/it_ops*.py`)

### Durum (`?sekme=` yok)
- **Ne yapıyor:** 7 halka (Logo, CRM, giriş, Zeki AI modeli, e-posta, şirket ağı, müşteri VM'i) 5 dk'da bir denenir; halka kartı, tazelik (veri sonu), kopukluk şeridi Kampüs'te de (`OutageStrip`). Her halkanın BT tarifi (`it_ops.py:110–140 RINGS.recipe`).
- **Kim:** BT uzmanı, işletim ekibi; yönetici (tek bakış).
- **Bugün AI:** Model halkası modele tek kısa istekle bakar, kapıdan (`it_ops_sources.py:204–216`, `llm_for("sistem", BATCH)`). Yorum yok.
- **Beklenti:** «Şu an ne bozuk ve kim etkileniyor?» tek cümle; kök neden tahmini (halkalar arası bağ: ağ düşünce Logo/CRM de düşer).
- **Yapabileceklerimiz:** *Bağımlılık çıkarımı* — halka bağımlılık grafiği kodla (VPN → Logo/CRM), «asıl kopan» işaretlenir; model yok. D3 · Z S (1 g). *Durum cümlesi* — açık olaylar + etkilenen ekranlar (modül↔halka eşlemesi) → model 1 cümle; guard. D2 · Z S.
- **Eksik:** —

### Olaylar (`?sekme=olaylar`, `?olay=`; tabs.tsx:16, IncidentPanel.tsx)
- **Ne yapıyor:** Kopma/tazelik olayları, zaman çizelgesi, kök neden notu, **Zeki AI olay değerlendirmesi taslağı** ve yayımı.
- **Kim:** BT.
- **Bugün AI:** Var — `POST /api/v1/it-ops/incidents/{id}/draft` (`it_ops_api.py:204–220`), istem `it_ops.py:699 draft_prompt` (yalnız olgular; «sayı uydurma» talimatı).
- **Beklenti:** Benzer geçmiş olayları bulma; tekrar eden hata metinlerinin gruplanması.
- **Yapabileceklerimiz:** *Guard eklemek* — taslaktaki süre/sayı olgu listesinde aranmıyor (yalnız talimat); `guard` ortak modülüyle cümle düşürme. D4 · Z S (0,5 g). *Benzer olay* — ilk/son hata metni gömmesi → aynı halkada en yakın 3 eski olay ve kök neden notu. D3 · Z S (1–2 g).
- **Eksik:** Taslakta sayı denetimi yok.

### Zamanlanmış işler (`?sekme=isler`, tabs.tsx:82)
- **Ne yapıyor:** Gece/saatlik işlerin son durumu, başarısızlar; günlük iş hatası özeti e-postası.
- **Kim:** BT, model/veri ekibi.
- **Bugün AI:** Yok.
- **Beklenti:** Hata günlüğünden «ne oldu, ne yapmalı» kısa açıklama; aynı hatanın tekrarı.
- **Yapabileceklerimiz:** *Hata sınıflama* — iş hata metni → `choose` (bağlantı / yetki / zaman aşımı / veri şekli / disk / model yok / diğer), düşük marj «sınıflanamadı»; ekranda sınıf + tarif. D3 · Z S (1–2 g) · Risk: hata metninde sır olabilir → teknoloji/sır maskeleme (`it_ops._TECH` + parola kalıbı) modelden önce.
- **Eksik:** CRM iş akışı hataları (`AsyncOperationBase`) henüz yok (analiz M48 §13 «sonraki sürüm»).

### Sürümler (`?sekme=surumler`, tabs.tsx:142, `it_ops.py:556 record_release`)
- **Ne yapıyor:** Kurulum kaydı (sha, imaj, kim).
- **Kim:** BT, ürün sahibi.
- **Bugün AI:** Yok.
- **Beklenti:** «Bu sürümde ne değişti?» sade dilde.
- **Yapabileceklerimiz:** *Sürüm notu taslağı* — iki sha arası commit başlıkları (git log, kurulumda yazılır) → model kullanıcı diliyle 5 madde, teknoloji adı filtresi. D3 · Z S (1 g) · Risk: commit iletisinde iç bilgi → yalnız iç ekranda.
- **Eksik:** —

### Kapasite (`?sekme=kapasite`, tabs.tsx:187, `it_ops_sources.py:516`)
- **Ne yapıyor:** Disk doluluk, modül başına model kuyruk bekleme/model süresi (`sl_llm_job`), soru sayısı/hatası — **anlık, projeksiyon yok** (`it_ops_sources.py:495`).
- **Kim:** BT, işletim.
- **Bugün AI:** Yok.
- **Beklenti:** «Disk kaç günde dolar?», «model kuyruğu hangi saatlerde tıkanıyor?»
- **Yapabileceklerimiz:** *Doluluk tahmini* — disk ve kuyruk bekleme serisi → doğrusal/mevsimsel eğilim kodla (ya da zaman serisi modeli); model yalnız gerekçe cümlesi. D3 · Z S (1–2 g).
- **Eksik:** Projeksiyon yok.

### Ayarlar (`?sekme=ayarlar`, tabs.tsx:251)
- **Ne yapıyor:** Alıcılar, eşikler, iç alan adları.
- **Kim:** BT.
- **Bugün AI:** Yok. **Beklenti:** Yok denecek kadar düşük. **Yapabileceklerimiz:** Önerilmez. **Eksik:** —

---

## M49 Veri güvenliği (`/veri-guvenligi`, `canvas/data-security/*`, `backend/semantic_bridge/data_security*.py`)

Tasarım kararı: uyarılar **kuralla**, model «hissiyle» değil (`data_security.py:11`). Bugün modülde model çağrısı yok.

### Özet
- **Ne yapıyor:** Açık uyarı, giriş, dışa aktarma, saklama işi durumu sayıları (`data_security.py:1208 summary`).
- **Kim:** Bilgi güvenliği sorumlusu, KVKK irtibat kişisi, BT müdürü.
- **Bugün AI:** Yok.
- **Beklenti:** Haftalık güvenlik özeti cümleleri; denetime hazır rapor.
- **Yapabileceklerimiz:** *Haftalık özet cümlesi* — `digest_text` (`data_security.py:643`) sayılarına 3 cümle yorum; guard. D2 · Z S (1 g).
- **Eksik:** —

### Uyarılar (AlertsTab.tsx, `evaluate` data_security.py:485)
- **Ne yapıyor:** Art arda hatalı giriş, mesai dışı toplu dışa aktarma, yeni yönetici, «Herkes»e yetki, saklama işi durması; «gerçek / gerçek değil» kapatma.
- **Kim:** Güvenlik sorumlusu.
- **Bugün AI:** Yok.
- **Beklenti:** Uyarının sade açıklaması; kişinin olağan davranışına göre sapma.
- **Yapabileceklerimiz:** *Uyarı açıklaması* — kanıt satırlarından 1–2 cümle (analiz M49 §13). D2 · Z S. *Kişi-içi sapma* — kişinin 30 günlük kendi ortalamasından sapma kodla (model yok; analizle uyumlu). D3 · Z S (1–2 g).
- **Eksik:** —

### Giriş ve oturumlar (LoginsTab.tsx), Erişim kaydı (AccessTab.tsx)
- **Ne yapıyor:** Açık oturumlar ve kapatma; giriş olayları; 403 kararları, dışa aktarmalar, Zeki AI'ın yetki dışı soruları.
- **Kim:** Güvenlik sorumlusu, BT.
- **Bugün AI:** Yok.
- **Beklenti:** Yetki dışı soru yoğunluğundan «bu role şu alan eksik olabilir» çıkarımı.
- **Yapabileceklerimiz:** *Yetki boşluğu önerisi* — `NOT_PERMITTED` soruların konu/veri alanı sayımı (kural) → Yönetim → Yetkiler'e «rol X için alan Y isteniyor» öneri kartı; karar yöneticide. D3 · Z S (1–2 g) · Risk: soru metni kişisel veri içerebilir — yalnız çözümlenen alan kimliği kullanılır.
- **Eksik:** —

### Hesap hijyeni ve «Herkes» daraltma önizlemesi (HygieneTab.tsx)
- **Ne yapıyor:** AD, CRM, portal izleri kesişimi (pasif hesap, yetkisi kalan ayrılmış kişi); «Herkes» daraltılırsa kim ne kaybeder.
- **Kim:** BT, İK (ayrılış), güvenlik.
- **Bugün AI:** Yok (analiz gereği deterministik).
- **Beklenti:** Düşük. **Yapabileceklerimiz:** Model önerilmez (kesişim deterministik olmalı). **Eksik:** —

### Kişisel veri envanteri (InventoryTab.tsx, `inventory` data_security.py:1122)
- **Ne yapıyor:** Kaynakta (Logo, CRM) kişisel veri kolonları — `sensitive` işaretliler + **ad-soyad kalıbına uyanlar** (`_name_rx`, data_security.py:1111) — ve portal kopyaları defteri (`data_security_inventory.json`).
- **Kim:** KVKK irtibat kişisi, hukuk.
- **Bugün AI:** Yok (kalıp).
- **Beklenti:** Kalıbın kaçırdığı kolonların (serbest metin not, adres parçası) bulunması; VERBİS kategorisine eşleme; aydınlatma metni taslağı.
- **Yapabileceklerimiz:**
  - *Kişisel veri sınıf önerisi* — kolon adı + açıklama + veri tipi (değer **gönderilmez**) → `choose` («kişisel değil / kimlik / iletişim / finans / özel nitelikli / serbest metin (içerebilir)»); öneri kuyruğu, alan sahibi onaylar. D4 · Z M (2–3 g) · Risk: yanlış negatif — kalıp ve model birlikte, model yalnız ekler.
  - *Belge taslakları (aydınlatma, ihlal bildirimi)* — envanter + olay kaydı → taslak; hukuk onaylar. D3 · Z M (3 g).
- **Eksik:** Tespit yalnız ad kalıbı + elle `sensitive` işareti.

### Saklama süreleri (RetentionTab.tsx)
- **Ne yapıyor:** Kayıt türü başına süre, «kaç satır etkilenir» önizlemesi, uygulama anahtarı (varsayılan kapalı), gece kanıtı.
- **Kim:** KVKK, BT.
- **Bugün AI:** Yok. **Beklenti:** Düşük. **Yapabileceklerimiz:** Model önerilmez (silme deterministik ve kanıtlı olmalı). **Eksik:** —

---

## M50 Zeki AI kalitesi (`/zeki-kalite`, `canvas/model-quality/*`, `backend/semantic_bridge/model_quality*.py`)

### Karne (`karne`, Scorecard.tsx)
- **Ne yapıyor:** Modül başına isabet satırı; ölçülmemiş «ölçülmedi»; yetkiye göre süzülür.
- **Kim:** Model/veri ekibi, ürün sahibi, yönetici.
- **Bugün AI:** Yok (ölçüm).
- **Beklenti:** Karnenin sade yorumu; DYK'ya giden tek paragraf.
- **Yapabileceklerimiz:** *Karne yorumu* — sayılardan 3 cümle; guard. D2 · Z S (1 g). *Modül kapsamı genişletme* — M51 sınıflama isabeti, M39 eşleme kabul oranı, destek taslak düzeltme oranı karneye (hepsi zaten ölçülüyor: `support.quality` `sentAsIs`, pazar kararları). D4 · Z S (2 g).
- **Eksik:** Karne bugün yalnız sohbet/kapı; modül AI çıktıları (taslak, sınıf) ortak karnede değil.

### Koşular (`kosular`, Runs.tsx)
- **Ne yapıyor:** Kapı koşuları, önceki koşuyla önce/sonra, bozulan/düzelen sorular (`semantic_mq_runs/cases`).
- **Kim:** Model/veri ekibi.
- **Bugün AI:** Yok (hüküm referans SQL karşılaştırması).
- **Beklenti:** Bozulan soruların ortak nedeninin söylenmesi.
- **Yapabileceklerimiz:** *Bozulma kümesi* — bozulan vakaların SQL farkı (kodla diff: tablo, filtre, dönem) → kümeleme; model küme başına 1 cümle. D3 · Z M (2–3 g).
- **Eksik:** —

### Hata sınıfları (`siniflar`, ClassBoard.tsx; `model_quality.py:429 classify` kural)
- **Ne yapıyor:** Sınıf başına soru sayısı, 4 haftalık eğilim; sınıf kuralı veri (tablo satırı), ilk tutan kazanır; tutmazsa «sınıflanamadı».
- **Kim:** Model/veri ekibi.
- **Bugün AI:** Yok.
- **Beklenti:** «Sınıflanamadı»ların önerilmesi.
- **Yapabileceklerimiz:** *Sınıf önerisi* — kural düşmeyen vakada `choose(sınıf listesi)` (analiz M50 §13), olasılık + marj, ekip onaylar; onay kural adayına dönüşür. D4 · Z S (1–2 g) · Risk: soru sonucu satırları modele gitmez (kişisel veri), yalnız soru + SQL + kapı gerekçesi.
- **Eksik:** —

### Geri bildirim (`geri-bildirim`, FeedbackQueue.tsx)
- **Ne yapıyor:** Kısmen/Yanlış hükümleri kuyruğu; kural sınıf önerir, ekip düzeltir/kapatır.
- **Kim:** Model/veri ekibi.
- **Bugün AI:** Yok.
- **Beklenti:** Kullanıcının serbest notundan ne demek istediğinin çıkarılması; düzeltilen sorudan test vakası.
- **Yapabileceklerimiz:** *Golden aday varyantları* — düzeltilmiş sorudan 2–3 sade varyant (analiz M50 §13); referans SQL'i insan yazar. D3 · Z S (1 g). *Not sınıflama* — kullanıcı notu → `choose` (yanlış dönem / yanlış ölçü / eksik filtre / beklenen kırılım / diğer). D3 · Z S (1 g).
- **Eksik:** —

### Sürümler (`surumler`, Versions.tsx)
- **Ne yapıyor:** Kod, katalog, bilgi paketi, dil havuzu, model tek satırda; «değişen» sütunu.
- **Kim:** Model ekibi, BT.
- **Bugün AI:** Yok. **Beklenti:** Düşük. **Yapabileceklerimiz:** M48 sürüm notu önerisiyle ortak. **Eksik:** —

---

## M51 Müşteri hizmetleri (`/musteri-destek`, `canvas/support/*`, `backend/semantic_bridge/support*.py`)

Talep kaydı NanobaseAI Destek'tedir; bu ekran okur ve TİMAŞ bağlamını ekler (`support.py:1–20`). Model kapıdan `rt.llm_for("destek")`
(`app.py:7130`); modele giden metinde e-posta/telefon/IBAN/kimlik maskelenir (`support.py:340 mask_personal`).

### Özet ve Konular (`ozet`, `konular` → QualityTab.tsx)
- **Ne yapıyor:** Açık, SLA, ilk yanıt, çözüm, memnuniyet; konu eğilimi (önceki dönemle); tekrarlayan talep; Zeki AI karnesi (sınıflama isabeti = temsilcinin değiştirmediği pay, taslak «az düzeltmeyle gönderilen», `support.py:741`). Metin «model yorum yazmaz» (QualityTab.tsx:13).
- **Kim:** Müşteri hizmetleri yöneticisi.
- **Bugün AI:** Karne ölçümü var; yorum yok.
- **Beklenti:** «Bu hafta şikâyetler neden arttı?»; yeni çıkan konu (ör. bir kitapta baskı hatası) erken uyarısı.
- **Yapabileceklerimiz:** *Yeni konu tespiti* — «diğer»/«sınıflanamadı» taleplerin maskeli metin gömmesi → kümeleme; kümeye kısa etiket önerisi (model), eşik üstü küme uyarı. D4 · Z M (3 g) · Risk: talep metni köprüde saklanmaz — gömme vektörü + talep kimliği saklanır (KVKK notu). *Haftalık yorum* — sayılardan 3 madde; guard. D3 · Z S (1 g).
- **Eksik:** —

### Kuyruk (`kuyruk`, QueueTab.tsx)
- **Ne yapıyor:** Açık talepler SLA'ya göre; talep seçilince Zeki önerisi (konu + aciliyet `choose`, `support.py:375–387`, eşik `SUPPORT_CLASSIFY_MIN_PROB` 0,70 / marj 0,30), SSS eşleşmesi (gömme ya da kelime, `support.py:428 FaqIndex`), **cevap taslağı** (`support_api.py:439–442`, yer tutuculu; `fill_draft` sayı içeren uydurma cümleyi düşürür `support.py:585`), müşteri bağlamı.
- **Kim:** Müşteri hizmetleri temsilcisi.
- **Bugün AI:** Var — sınıflama, SSS eşleme, denetimli taslak, düzeltme oranı ölçümü.
- **Beklenti:** Uzun yazışmanın özeti; öfkeli müşteri önceliği; telefonla gelen talepte konuşma notundan kayıt.
- **Yapabileceklerimiz:** *Duygu/öfke → öncelik* — destek masasının `nb_duygu` alanı zaten dolduruluyor (destek `kayit.py`), M51 okumuyor (`support_sources.py:426 TICKET_FIELDS`'te yok) → kuyruk sıralamasına ek. D3 · Z S (0,5 g). *Sipariş/kargo gecikme sezgisi* — bağlamdaki kargo durumu + talep konusu «kargo gecikmesi» ise taslağa hazır olgu. (Zaten olgu hattı var; kapsam genişletme.) D3 · Z S.
- **Eksik:** Masadaki sınıflama (tür/öncelik/ekip/duygu, `chat_json`) ile M51 sınıflaması (konu/aciliyet, `choose`) **iki ayrı sınıflayıcı** — isabet iki yerde ölçülüyor, çelişebilir.

### Müşteri bağlamı (`baglam`, CustomerContext.tsx), Bayi görünümü (`bayi`, DealerView.tsx)
- **Ne yapıyor:** E-posta/telefon/sipariş no/cari → CRM kişi-cari, siparişler, sevkiyat, kargo takibi, Logo fatura/iade (veri sonu tarihiyle). Bayi: açık sipariş, bekleyen adet, risk limiti onayı, son sevkiyat, yaklaşık bakiye. «Zeki AI kullanılmaz» (DealerView.tsx:12).
- **Kim:** Temsilci, bayi ilişkileri.
- **Bugün AI:** Yok (bilinçli: eşleşme deterministik).
- **Beklenti:** Bağlamın 2 cümlelik özeti («3 açık sipariş, biri 9 gündür kargoda»).
- **Yapabileceklerimiz:** *Bağlam özeti* — olgular (sayılar SQL) → şablon cümle; model gerekmez, kural yeter. D2 · Z S (0,5 g).
- **Eksik:** Site (T-soft) siparişi okunmuyor («sonraki sürüm», `support.py:1062`).

### Bilgi bankası açıkları (`sss`, FaqGaps.tsx)
- **Ne yapıyor:** SSS eşleşmesi bulunamayan talepler konuya göre sayılır, eşik üstü «aday» (`support.py:855 refresh_gaps`); yönetici soru + cevap **elle** yazar, onaylı madde eşleşmeye katılır.
- **Kim:** Destek yöneticisi, içerik sorumlusu.
- **Bugün AI:** Sayım ve eşleme var; SSS metni elle.
- **Beklenti:** SSS maddesi taslağı; sitedeki SSS ile çakışma kontrolü.
- **Yapabileceklerimiz:** *SSS taslağı* — konudaki çözülmüş taleplerin temsilci cevapları (maskeli) → soru + cevap taslağı; guard; yönetici onaylar, T-soft'a elle (yazma yok). Destek masasındaki `article_draft` (kayit.py:214) aynı işi tek talepten yapıyor — ortak istem. D4 · Z S (1–2 g).
- **Eksik:** —

### Konu sınıfları (`siniflar`, ClassesTab.tsx)
- **Ne yapıyor:** Kapalı küme konu listesi + anlamı (modelin okuduğu açıklama), SLA uyarı süreleri.
- **Kim:** Destek yöneticisi.
- **Bugün AI:** Listeyi model kullanır.
- **Beklenti:** Liste değişince isabetin hemen ölçülmesi.
- **Yapabileceklerimiz:** *Liste değişikliği önce/sonra* — son 200 temsilci-onaylı talepte eski/yeni liste `choose` isabeti (arka plan). D3 · Z S (1–2 g).
- **Eksik:** —

---

## Yönetim — Veri sözlüğü, Onaylar, Eş anlamlılar, Portal ayarları

### Veri sözlüğü — Terimler / Tablolar / Eksik açıklamalar (`/veri-sozlugu`, `canvas/dictionary/GlossaryScreen.tsx`)
- **Ne yapıyor:** «Ciro dendiğinde ne hesaplanıyor» (kavram, eşleme, kanıt), tablo/kolon anlamları (kalıp başına tek satır), eksik açıklamalar; yönetici yazar. Eksik kolonda **Zeki önerisi** kabul/ret (GlossaryScreen.tsx:281–340).
- **Kim:** Model/veri ekibi, finans analisti (terim tanımı), BT.
- **Bugün AI:** Var — kolon anlamı + kod değer açıklaması önerisi (`semantic_layer/candidates/generator.py:343–368`, `add_suggestion`, gözlenen değer dışı kod atılır `_vet_reading`), öneri `LLM_CANDIDATE` kanıtı olarak zayıf ağırlıkla (0,1) girer.
- **Beklenti:** Tablo düzeyi açıklama önerisi; terimin iş diliyle tanımı («net ciro = … iade ve iskonto düşülmüş»); «bu terimi kim kullanıyor» (soru kaydından).
- **Yapabileceklerimiz:** *Terim tanımı sade dil* — kavramın SQL/eşleme/filtresinden 2 cümle iş tanımı (model), guard; yönetici onaylar. D3 · Z S (1–2 g). *Tablo açıklaması önerisi* — kolon açıklamaları + ilişkilerden tablo cümlesi. D3 · Z S (1 g). *Kullanım sıklığı* — `sl_query_log` çözümlenen kavram sayımı (kural). D2 · Z S.
- **Eksik:** —

### Onaylar (`/onaylar`, ApprovalsScreen.tsx)
- **Ne yapıyor:** Metrik/kolon/değer/ilişki/varsayılan filtre adayları; kararın düz Türkçe anlamı, teknik karşılık, örnek sonuç satırları; onay/ret.
- **Kim:** Veri sahibi (finans, satış), model ekibi.
- **Bugün AI:** Adaylar kısmen modelden (aday üretici + çürütme, `semantic_layer/evidence/refute.py`); ekranda karar yardımı yok.
- **Beklenti:** «Onaylarsam hangi sorular değişir?»; riskli adayın işaretlenmesi.
- **Yapabileceklerimiz:** *Etki önizlemesi* — adayla/adaysız son 200 sorunun çözümlemesi (modelsiz, çözümleyici tekrar koşar) → değişen soru sayısı ve örnek. D4 · Z M (3 g). *Kanıt özeti* — kanıt ve karşı kanıttan 2 cümle. D2 · Z S.
- **Eksik:** —

### Eş anlamlılar — Öneriler / Kararlar / Açıklaması olmayan alanlar (`/es-anlamlilar`, VocabularyScreen.tsx)
- **Ne yapıyor:** Alan adlarının gündelik karşılıkları: açıklamadan aday → çürütme → onay (`semantic_layer/vocabulary.py:257`, çağrı `app.py:1580`, modül `vocabulary`); boşluk sekmesinde yönetici bir cümle yazar, hat oradan üretir.
- **Kim:** Model/veri ekibi.
- **Bugün AI:** Var — aday üretimi ve çürütme.
- **Beklenti:** Kullanıcıların gerçekten yazdığı kelimelerden öneri.
- **Yapabileceklerimiz:** *Soru kaydından terim madenciliği* — çözümlenemeyen terimler (`INCOMPLETE_ANSWER` unresolved, app.py ~985) sayılır, sık olanlar için alan adayı gömme benzerliğiyle; `choose` ile «bu alan mı?»; insan onayı. D4 · Z M (3 g) · Risk: «Makine tek kelime/anahtar/satırsız tabloyu onaylamaz» kuralı korunur.
- **Eksik:** —

### Portal ayarları (`/yonetim?bolum=…`, `canvas/admin/AdminScreen.tsx`)
10 sekme; tek tek:

#### Genel durum (Overview.tsx)
- **Ne yapıyor:** Rapor/uyarı/kart/kullanıcı sayıları, servis durumu, e-posta ayarı. **Kim:** Yönetici. **Bugün AI:** Yok. **Beklenti:** Düşük. **Yapabileceklerimiz:** Önerilmez (M48 ile ortak). **Eksik:** M48 ile tekrar eden servis durumu.

#### Ayarlar (SettingsPanel.tsx)
- **Ne yapıyor:** Bağlantılar (Logo, CRM, model, SEO, e-posta kutusu, …) ve deneme düğmeleri; kaynak (ekran/env/dosya/varsayılan).
- **Kim:** Yönetici, BT.
- **Bugün AI:** Model «Sor» denemesi: `admin.llm_test` **`LlmClient`'i doğrudan kurar, kapıyı atlar** (`admin.py:2048–2059`).
- **Beklenti:** Ayar açıklaması; hatalı ayarda ne yapılacağı.
- **Yapabileceklerimiz:** *Deneme hatasının sade açıklaması* — hata metni → `choose` (parola / ağ / sertifika / yetki / zaman aşımı) + hazır tarif (M48 `RINGS.recipe` yaklaşımı). D2 · Z S (1 g).
- **Eksik:** Model denemesi kapı kuralıyla («`LlmClient` doğrudan kurulmaz») çelişiyor; M48 halkası kapıdan geçiyor — iki ölçüm farklı sonuç verebilir.

#### Yetkiler — Roller / Veri alanları / Kişi gözüyle (AccessAdmin.tsx)
- **Ne yapıyor:** Rol = sayfalar; AD grubu/OU/CRM rolü/kişiye bağ; veri alanı ataması (atanmamış tablolar yalnız yöneticiye, `AccessAdmin.tsx:725–760`); kişi gözüyle etkin yetki.
- **Kim:** Yönetici, BT, güvenlik.
- **Bugün AI:** Yok.
- **Beklenti:** Atanmamış tabloya alan önerisi; «muhasebe ekibi finans ekranlarını görsün» cümlesinden rol taslağı.
- **Yapabileceklerimiz:** *Veri alanı önerisi* — atanmamış varlık açıklaması + kolon adları → `choose(data_domains)` (analiz M49 §13), p/marj eşiği, yönetici tek tık. D4 · Z S (2 g). *Cümleden rol taslağı* — cümle → sayfa kimlikleri (`choose` ile menü öğesi başına evet/hayır ya da gömme ile aday) + bağ önerisi; önizleme (M49 «Herkes» önizlemesi) sonrası kaydet. D3 · Z M (3 g) · Risk: yetki genişletme insan onaysız yazılmaz.
- **Eksik:** —

#### Planlı raporlar / Uyarılar / Pano kartları (yönetici görünümü, Definitions.tsx:69, 159, 239)
- **Ne yapıyor:** Herkesin tanımları; durdur/sil; filtre.
- **Kim:** Yönetici.
- **Bugün AI:** Yok.
- **Beklenti:** Bozuk/boş dönen ya da hiç açılmayan tanımların bulunması.
- **Yapabileceklerimiz:** *Tanım sağlığı* — son N koşu boş/hatalı, alıcı geçersiz, kart 90 gün açılmamış (kural). D3 · Z S (1 g). Model gerekmez.
- **Eksik:** —

#### Kişiler (People.tsx)
- **Ne yapıyor:** Tanımı/kaydı olan AD hesapları. **Kim:** Yönetici. **Bugün AI:** Yok. **Beklenti:** Düşük. **Yapabileceklerimiz:** Önerilmez. **Eksik:** —

#### Soru izleme (PromptTracker.tsx; uçlar `app.py:6914–6960`)
- **Ne yapıyor:** Her soru, SQL, sonuç, kapı kararı; Toplam/Cevaplanan/Başarısız/Düzeltilecek; satır ayrıntısı ve «düzeltilecek» işareti; CSV.
- **Kim:** Model/veri ekibi.
- **Bugün AI:** Yok.
- **Beklenti:** Başarısız soruların nedene göre toplanması; «bu hafta kullanıcılar en çok neyi soramadı».
- **Yapabileceklerimiz:** *Başarısız soru kümeleri* — başarısızların soru gömmesi + kapı gerekçesi → küme, küme etiketi (model), küme başına «soru sayısı» (bellek `fix-classes-not-questions`); M50 sınıflarına bağ. D4 · Z M (3 g) · Risk: soru metni kişisel veri içerebilir → maskeleme.
- **Eksik:** —

#### Sesli bülten (BulletinsAdmin.tsx)
- **Ne yapıyor:** Yükleme, **metinden seslendirme** (GPU), yayım, düzenleme.
- **Kim:** Kurumsal iletişim.
- **Bugün AI:** Var — seslendirme.
- **Beklenti/Öneri:** Kampüs → Sesli bülten metin taslağı (yukarıda). **Eksik:** Bülten özeti/transkript yok.

#### Değişiklik kaydı (AuditLog.tsx)
- **Ne yapıyor:** Kim ne zaman neyi değiştirdi; alan farkı.
- **Kim:** Yönetici, denetçi.
- **Bugün AI:** Yok.
- **Beklenti:** «Geçen hafta yetkilerde ne değişti?» sade özet.
- **Yapabileceklerimiz:** *Dönem özeti* — kayıtlar gruplanır (kod), model 3–5 madde; guard. D2 · Z S (1 g).
- **Eksik:** —

---

## NanobaseAI Destek masası (`apps/destek`)

Yapı (`apps/destek/README.md`): Frappe v16 + Helpdesk (markalı) + Flow (yapay zekâ paneli, masaüstünde Ctrl+I) + `nanobase_brand` (marka, AD/SSO,
yapay zekâ). Model çağrıları LLM kapısından: `yz/llm.py` → nginx `/destek-llm/v1` (`deploy/nginx-destek-llm.conf`) → köprü
`/api/v1/llm/openai/v1` (`backend/semantic_bridge/llm_openai.py`), modül `destek`, öncelik başlıkla. Gömme BI'ın gömme servisi (bge-m3), bilgi
bankası «NanobaseAI Destek Bilgisi» (yayımlanmış makaleler + çözülen kayıtlar, `yz/bilgi.py`). **Uyarı:** M51 analizindeki «helpdesk paneli
kapıyı atlıyor» notu artık geçerli değil; kod kapıdan gidiyor.

### Temsilci ana sayfa ve kayıt listesi (`/helpdesk/home`, `/tickets`)
- **Ne yapıyor:** Kayıt listesi, filtre, toplu atama/yanıt (BulkReplyModal).
- **Kim:** Temsilci, ekip lideri.
- **Bugün AI:** Yeni kayıtta arka planda **sınıflama**: tür, öncelik, ekip, müşteri duygusu + gerekçe (`yz/kanca.py` → `yz/kayit.py:74 classify`, `chat_json`, yalnız boş/varsayılan alan dolar).
- **Beklenti:** Liste satırında 1 satırlık özet; SLA riskine göre sıralama; aynı sorunun toplu kayıtlarını birleştirme.
- **Yapabileceklerimiz:** *Olasılıklı sınıflama* — `chat_json` yerine `choose` (tür/öncelik/ekip/duygu dört ayrı kapalı küme), eşik altı alan boş kalır; M51'in konu/aciliyetiyle **tek sınıflayıcı** (masa alanı ↔ M51 konu eşlemesi). D4 · Z M (3 g) · Risk: iki sistemin geçiş dönemi — önce M51 masanın alanını okur.
  - *Tekrar eden kayıt birleştirme önerisi* — son 48 saatteki açık kayıtların gömme benzerliği → «aynı sorun» grubu; temsilci birleştirir. D3 · Z S (2 g).
- **Eksik:** Modele giden kayıt metninde **kişisel veri maskelenmiyor** (`kayit.py:42 _conversation`, `74 classify`); köprüdeki M51 maskeliyor (`support.py:340`). Kural «kişisel veri modele gitmez (maskele)» — ortak maskeleme şart.

### Kayıt ayrıntısı + NanobaseAI paneli (`/helpdesk/tickets/:ticketId`, `components/ticket-agent/NanobaseAIPanel.vue`)
- **Ne yapıyor:** Yazışma, müşteri, etkinlik; panelde: Özetle (`kayit.py:147`), Yanıt taslağı (`172`, bilgi bankası dayanaklı, kaynak bağlantıları), Benzer geçmiş kayıtlar + uygulanan çözüm + önerilen yol (`287`), çözülen kayıtta Makale taslağı (`214`, kişisel verisiz talimat).
- **Kim:** Temsilci.
- **Bugün AI:** Var — özet, taslak, benzer kayıt, makale.
- **Beklenti:** Taslakta sipariş/kargo gerçeği (M51 bağlamı); müşterinin diliyle yanıt; taslak tonunun ayarı.
- **Yapabileceklerimiz:** *M51 bağlamını panele taşımak* — köprü `panel/context` (docs/analiz/M51-destek-paneli-baglam-ucu.md) → taslakta sipariş/kargo olguları yer tutucuyla (`support.fill_draft` yaklaşımı). D5 · Z M (3–4 g) · Risk: bugün masa taslağında **sayı denetimi yok** (yalnız «tarih, fiyat yazma» talimatı, `kayit.py:187`) — guard eklenmeli.
  - *Taslak düzeltme oranı* — M51'deki `edit_ratio` ölçüsünü masa taslağına da (gönderilen yanıt ↔ taslak). D3 · Z S (1 g).
- **Eksik:** Taslakta olgu/guard yok; özet ve benzer kayıtta maskeleme yok.

### Yeni kayıt (`/tickets/new/:templateId?`) ve müşteri portalı yeni kayıt (`/my-tickets/new`)
- **Ne yapıyor:** Şablonlu form.
- **Kim:** Temsilci (telefonla gelen), müşteri.
- **Bugün AI:** Yok (kayıt sonrası sınıflama).
- **Beklenti:** Müşteri yazarken ilgili SSS önerisi (kayıt açmadan çözüm); telefondaki konuşmadan kayıt metni.
- **Yapabileceklerimiz:** *Yazarken SSS önerisi (self servis)* — başlık/açıklama gömmesi → yayımlanmış makaleler ilk 3 (bilgi bankası araması `bilgi.search`); dış kullanıcıya yalnız yayımlanmış makale. D4 · Z S (2 g) · Risk: iç kayıt (çözülen talepler) müşteriye gösterilmez — kaynak süzgeci şart.
- **Eksik:** —

### Bilgi bankası (`/kb`, `/kb/articles/:id`, `/articles/new/:id`) ve açık bilgi bankası (`/kb-public`, `/kb-public/:categoryId`, `/kb-public/articles/:id`)
- **Ne yapıyor:** Makale yazma/yayımlama, kategori; müşteriye açık okuma.
- **Kim:** Destek yöneticisi, içerik sorumlusu; müşteri.
- **Bugün AI:** Makale taslağı kayıttan (panelden); bilgi bankası gömmesi (Flow Knowledge, Hybrid arama).
- **Beklenti:** Eskiyen makalenin bulunması; çelişen makaleler; makale başlığı/kategori önerisi.
- **Yapabileceklerimiz:** *Makale bakımı* — makaleye bağlanan yeni kayıtlarda çözüm farklıysa «güncelle» işareti (benzerlik + `choose` «makale hâlâ geçerli mi: evet/hayır/belirsiz»). D3 · Z M (3 g). *Kategori önerisi* — `choose(HD Article Category)`. D2 · Z S (0,5 g).
- **Eksik:** Makale taslağı hep «General» kategorisine düşüyor (`kayit.py:235`).

### Arama (`/search`, SearchAgent.vue)
- **Ne yapıyor:** Temsilci araması (kayıt/makale). **Kim:** Temsilci. **Bugün AI:** Doğrulanmadı (üst kaynak arama; anlamsal olup olmadığı koddan doğrulanmadı).
- **Beklenti:** Anlamsal arama. **Yapabileceklerimiz:** *Bilgi bankası gömme aramasını arama ekranına bağlamak* (`bilgi.search`). D3 · Z S (1 g). **Eksik:** —

### Müşteriler ve kişiler (`/customers`, `/customers/:id`, `/contacts`, `/contacts/:id`)
- **Ne yapıyor:** Müşteri (kurum) ve kişi kartları, kayıt geçmişi. **Kim:** Temsilci, ekip lideri. **Bugün AI:** Yok.
- **Beklenti:** «Bu müşteri kaç kez aynı sorunu yaşadı» ve ilişki özeti; Logo/CRM cari bağı.
- **Yapabileceklerimiz:** *Müşteri özeti* — kayıt sayıları/konular (SQL) + M51 bağlamı (CRM/Logo) → 2 cümle; guard. D3 · Z S (1–2 g). **Eksik:** Masa müşterisi ile CRM/Logo cari eşleşmesi masada yok (M51 ekranında var).

### Temsilciler ve ekipler (`/agents`, `/teams`, `/teams/:teamId`)
- **Ne yapıyor:** Temsilci/ekip yönetimi, atama kuralı. **Kim:** Destek yöneticisi. **Bugün AI:** Yok (ekip sınıflamayla atanıyor).
- **Beklenti:** İş yükü dengesine göre atama önerisi. **Yapabileceklerimiz:** *Yük dengeli atama* — kural (açık kayıt sayısı, uzmanlık = geçmiş tür dağılımı); model gerekmez. D2 · Z S. **Eksik:** —

### Pano (`/dashboard`) ve zamanlanmış raporlar (Not + e-posta; `yz/rapor.py`, `hooks.py:39–45`)
- **Ne yapıyor:** Üst kaynak pano; hafta içi 08:30 SLA riski listesi (`rapor.py:78`), pazartesi 08:00 haftalık rapor: sayılar DB'den, «NanobaseAI yorumu» 5 madde konu başlıklarından (`rapor.py:88–137`).
- **Kim:** Destek yöneticisi («Agent Manager»).
- **Bugün AI:** Var — haftalık yorum.
- **Beklenti:** Yorumun sayılara dayanması; bir önceki haftayla fark.
- **Yapabileceklerimiz:** *Guard + önceki hafta farkı* — yorum yalnız konu başlığı görüyor, sayı denetimi yok («Sayı uydurma» talimatı var); olgu listesi (tür/ekip dağılımı, önceki hafta) + guard. D3 · Z S (1 g).
- **Eksik:** Yorumda sayı denetimi yok.

### Çağrı kayıtları (`/call-logs`, telephony eklentisi) ve Bildirimler (`/notifications`)
- **Ne yapıyor:** Telefon çağrı kaydı listesi; bildirimler. **Kim:** Temsilci. **Bugün AI:** Yok.
- **Beklenti:** Çağrı özeti/kayda dönüştürme (ses varsa). **Yapabileceklerimiz:** *Çağrı notundan kayıt taslağı* — temsilcinin serbest notu → konu/tür/özet (model) ; ses kaydı dökümü ancak santral kaydı bağlanırsa (**doğrulanmadı**: telefon santrali bağlı mı bilinmiyor). D2 · Z M. **Eksik:** —

### Müşteri portalı (`/my-tickets`, `/my-tickets/:ticketId`)
- **Ne yapıyor:** Müşterinin kendi kayıtları ve yazışması. **Kim:** Müşteri/bayi. **Bugün AI:** Yok.
- **Beklenti:** «Siparişim nerede?» anında cevap (kargo durumu). **Yapabileceklerimiz:** *Durum cevabı* — kayıt/sipariş numarasından M51 bağlamı (yalnız o müşterinin kendi kaydı) → hazır şablon cevap, model yok; ilk sürümde temsilci onaylı (dış gönderim kuralı). D3 · Z M (3 g) · Risk: kimlik doğrulama; başka müşterinin verisi sızmamalı. **Eksik:** —

### Masaüstü `/app` + yapay zekâ paneli (Flow, Ctrl+I)
- **Ne yapıyor:** Frappe masaüstü; Flow sohbet/ajan paneli (model kapıdan). **Kim:** Yönetici, sistem yöneticisi. **Bugün AI:** Var — genel sohbet paneli (araç çağırma üst kaynakta; yetenek kapsamı **doğrulanmadı**).
- **Beklenti:** «Bu hafta en çok bekleyen 5 kayıt?» gibi masa verisine soru. **Yapabileceklerimiz:** *Masa sorgularını Zeki sohbetine bağlamak* — `chat_topics.json` «destek» konusunun `data`'sı (bugün boş) M51 tablolarıyla doldurulunca aynı soru portaldan da cevaplanır; Flow paneli yalnız masaüstü işleri için kalır. D3 · Z (sohbet bağlama önerisinin parçası). **Eksik:** İki ayrı sohbet yüzü (Flow paneli ve Zeki AI) — kimlik/kapsam kuralı («Ben Zeki AI…») Flow'da uygulanıyor mu **doğrulanmadı**.

### İlk kurulum / kişilik formu (`/onboarding`, PersonaForm.vue)
- **Ne yapıyor:** Üst kaynağın ilk açılış formu (masa kullanım amacı); yalnız yetkili kişide açılır. **Kim:** Sistem yöneticisi (bir kez). **Bugün AI:** Yok.
- **Beklenti:** Yok. **Yapabileceklerimiz:** Önerilmez. **Eksik:** Kurulum betiği ayarları yazdığı için ekranın TİMAŞ'ta gerekip gerekmediği doğrulanmadı.

### Çeviri hattı (`apps/destek/tools/cevir.py`, `ceviri.sh`)
- **Ne yapıyor:** `.po` dosyalarındaki boş Türkçe çevirileri modelle doldurur (arka plan, modül `destek-ceviri`), yer tutucu/HTML birebir korunur, ürün adı «NanobaseAI».
- **Kim:** Geliştirici (kurulum).
- **Bugün AI:** Var — çeviri.
- **Beklenti/Öneri:** Terim sözlüğü tutarlılığı (`--sozluk`) zaten var; ek öneri yok. **Eksik:** —

---

## Kampüs'te canlı olmayan modül kutuları (`modules.json` − `LIVE`, «Yakında»)

- **İlişki Haritası (`map`)** — ekran yok — beklenti: yazar/kitap/cari/kurum ilişkilerinin grafiği; «bu yazarla bağlantılı bayiler» sorusu (M7 ilişki çekirdeği + gömme).
- **DYK — Danışma ve Yönetim Kurulu (`DYK`)** — ekran yok — beklenti: gösterge paketi, bölüm yorumu taslağı, yönetici özeti (guard), tutanaktan karar/aksiyon çıkarma, gündem önerisi (`docs/analiz/kullanici-ihtiyaclari/DYK-danisma-yonetim-kurulu.md` §13).
- **ZEKİ Proje Planı (`roadmap`)** — ekran yok — beklenti: modüllerin durumu ve «bu ay ne devreye alındı» özeti (M48 sürüm kaydından).
- **Finans & Bütçe Masası (`desk`)** — ekran yok — beklenti: bütçe–gerçekleşen sapmasının «neden» ayrıştırması (M46/M45 ile örtüşür).
- **ZEKİ Sohbet Paneli (`copilot`)** — ekran yok — beklenti: her ekranda yan panel sohbet (ekran bağlamını soruya ekleyen, konuşma geçmişli Zeki AI).
- **Yayın/İmprint Tablosu (`imprint`)** — ekran yok — beklenti: imprint başına ciro/kârlılık ve yorum (`v_imprint_perf` görünümü var).
- **Kanal Kırılımı (`channel-mix`)** — ekran yok — beklenti: kanal payı kayması ve nedeni (Genel bakış kanal kartının derin hâli).
- **Nakit Akışı Grafiği (`cashflow`)** — ekran yok — beklenti: vade/alacak–borç ile 13 haftalık nakit tahmini (zaman serisi modeli + kural).

---

## Grubun en değerli 10 AI önerisi

| # | Öneri | Ekran(lar) | Veri | Teknik | D | Z |
|---|---|---|---|---|---|---|
| 1 | Modül verisini Zeki sohbetine bağlama (9 bağlı olmayan konu) | Genel bakış, Kampüs, Panolar, Uyarılar, Flow paneli | Portal `semantic_*` tabloları (M51, M48, M50, pazarlama, İK…) + katalog veri alanı | Katalog profili/sertifika ya da adlandırılmış sorgu kalıbı + `choose` eşleme; rakam SQL | 5 | L (8–12 g) |
| 2 | Rakamın «neden»i: dönem farkını boyutlara ayrıştırma + anlatım | Genel bakış, Uyarılar e-postası, Panolar | Logo ölçüleri (net ciro `LINENET`, kanal, cari, kitap) | Genel fark ayrıştırma planı (SQL) + model 2–3 cümle + guard | 5 | M (5 g) |
| 3 | Beklenen aralık / anomali uyarısı ve eşik önerisi | Uyarılar, Panolar | Kuralın sorusu geçmiş dönemlerde | TimesFM / mevsimsel median±MAD + kural; model yalnız açıklama | 5 | M (4–5 g) |
| 4 | Pano kartı ve planlı rapor «ne değişti» anlatımı | Panolar, Planlı raporlar e-postası | `semantic_board_cards.result_json`, rapor önceki sonucu | Kodla fark + model madde + guard | 5 | M (3 g) |
| 5 | Destek taslağına M51 bağlamı (sipariş/kargo/fatura olguları) + guard | Destek kayıt paneli | CRM `new_siparisBase`, `new_kargotakipbilgisiBase`, Logo fatura | Yer tutuculu taslak (`fill_draft`), guard | 5 | M (3–4 g) |
| 6 | Tek, olasılıklı destek sınıflayıcısı + ortak kişisel veri maskeleme | Destek listesi, M51 Kuyruk | HD Ticket metni (maskeli) | `choose` (tür/öncelik/ekip/duygu/konu) + `mask_personal` | 4 | M (3 g) |
| 7 | Kişisel «Bugün» özeti (bildirim zili) | Kampüs | Uyarı, e-posta ataması, ajanda, onay kuyrukları, SLA riski | Kural toplama + model 3 cümle + guard | 4 | M (4 g) |
| 8 | Başarısız soru kümeleri + «sınıflanamadı» sınıf önerisi | Soru izleme, M50 Hata sınıfları | `sl_query_log`, `semantic_mq_cases` | Gömme kümeleme + `choose(sınıf)` | 4 | M (3–4 g) |
| 9 | Kişisel veri kolon sınıflaması + veri alanı ataması önerisi | M49 Envanter, Yetkiler → Veri alanları | Katalog profili (ad, açıklama, tip; değer yok) | `choose` + insan onayı | 4 | S–M (2–3 g) |
| 10 | Taranmış sektör raporu okuma (OCR) | M39 Sektör raporları | Yüklenen PDF görüntüsü | GPU görsel-dil modeli + birebir doğrulama + onay | 4 | M (4–5 g) |

Sıradaki adaylar (D4, S): denetimli özet (`summary_mode=llm` + guard), SSS taslağı (M51 açıkları), emsalde gömme ile aday genişletme, M48 olay taslağına guard, kapsam sınıflayıcıyı `choose`'a taşıma, yazarken SSS önerisi (müşteri portalı).

## Ortak altyapı ihtiyaçları

1. **Tek sayı denetçisi (guard)** — bugün üç ayrı uygulama var: `marketing/guard.py`, `pazar.check_sentence` (pazar.py:1665), `support.fill_draft` (support.py:585). M48 olay taslağı (it_ops.py:699), destek masası taslak/yorumu (`kayit.py`, `rapor.py`) ve sohbet özetinde (app.py:799) **hiç yok**. Ortak `semantic_bridge/ai_guard.py` + destek tarafında aynı kuralın Python kopyası (ya da köprü ucu).
2. **Kapalı küme standardı** — sınıflama işleri `choose`'a: bugün JSON-chat kullananlar `chat_scope.classify` (chat_scope.py:241) ve destek `kayit.classify` (`chat_json`). Eşikler `admin.conf`'ta, karne M50'de.
3. **Ortak kişisel veri maskeleme** — `support.mask_personal` (support.py:340) + `sensitivity.py` değer kalıpları; destek `yz/*` modele maskesiz metin gönderiyor. Soru kaydı kümeleme ve hata metni sınıflamada da gerekli.
4. **Gömme / benzerlik servisi** — `BI_EMBED_URL` (bge-m3) bugün M51 SSS ve destek bilgi bankasında. Aynı servis: rehberde iş tarifinden kişi, ekran bulucu, emsal aday genişletme, başarısız soru kümeleri, yeni destek konusu kümeleri, tekrar eden kayıt birleştirme, olay benzerliği.
5. **Fark ve «neden» motoru** — önceki sonuç ↔ yeni sonuç farkı ve dönem farkının boyutlara ayrıştırılması (SQL); Genel bakış, Uyarılar, Panolar, Planlı raporlar, DYK, M39 özeti ortak kullanır.
6. **Beklenen aralık / anomali** — sunucudaki zaman serisi modeli (TimesFM) + istatistik yedeği; Uyarılar, Panolar, M48 kapasite, M49 kişi-içi sapma, nakit akışı.
7. **Belge okuma (OCR dahil)** — `pazar_sources.pages_of` metinli PDF okuyor; görüntü sayfası için GPU görsel-dil modeli. M39 raporları, destek ekleri, (grup dışı) sözleşme/fatura belgeleri.
8. **Bildirim ve özet derleyici** — bugün dağınık: M48 `weekly_text` (it_ops.py:473), M49 `digest_text` (data_security.py:643), destek `rapor.weekly`, planlı rapor e-postası, Kampüs zili. Tek «özet» kalıbı: kurallı olgu listesi → model kısa metin → guard → kişi yetkisine göre süzme.
9. **Modül verisi → sohbet bağlayıcısı** — `chat_topics.json` `data` alanını dolduran genel mekanizma (veri alanı kaydı + yetki + adlandırılmış sorgu); 9 konu için tek tasarım.
10. **AI çıktısı geri bildirim döngüsü** — sohbetteki Doğru/Kısmen/Yanlış (AnswerFeedback → M50) ve M51 `edit_ratio` gibi ölçülerin bütün taslak/sınıflama çıktılarına (destek masası, M39 eşleme, olay taslağı) yayılması; M50 karnesinde modül satırı.
11. **Kapı disiplini** — model çağrıları `rt.llm_for`; istisna `admin.llm_test` (admin.py:2056, `LlmClient` doğrudan). Ekranda teknoloji adı filtresi (`it_ops._TECH`, guard kural 4) ortak yardımcıya.
12. **Konuşma tanıma (sesli soru)** — Kampüs/Genel bakış/telefon kullanımı için yerel model; bugün kurulu olduğu doğrulanmadı.
