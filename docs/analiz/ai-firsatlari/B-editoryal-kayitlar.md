# B — Editoryal ve Kayıtlar

Kaynak: `ai-analiz-okuma` ağacı (main kopyası, HEAD `f26e11d6`), salt okuma. Tarih 2026-09-28.

**Kapsanan menü alanları:** «Editoryal» (`editoryal`) ve «Kayıtlar» (`kayitlar`) — `src/canvas/nav/navModel.ts:290-338`.

- **Menü öğesi: 25** — Editoryal 16 (Masam, Başvurular, Yazar giriş süreci, Yayın kurulu, Görevlerim, Redaksiyon,
  Çeviri, Çeviri masam, Çevirmenler, Son okuma, Kitap tasarım, Kapak arşivi, Dijital yayın, Dijital satış, Serbest
  çalışanlar, Üretim yönetimi) + Kayıtlar 9 (Kişiler, Yazar ilişkileri, Basın ve web, Sözleşmeler, Telif dönemi,
  Haklar ve lisanslar, Editör atama, Kategori ağacı, Kurumsal e-posta).
- **Rota: 49** (`src/App.tsx:544-614`), 3'ü eski adres yönlendirmesi (`/yazarlar`, `/cevirmenler`,
  `/cizer-freelancer` → `/kisiler?rol=…`). Ayrıca rotası olmayan ama ayrı ekran olan görünümler ele alındı:
  `/yayin-kurulu?gorunum=crm` (CRM kurul geçmişi, `MeetingScreen`), Kategori ağacının 6 bölümü, sekmeler.
- **Atlanan yok kanıtı:** aşağıdaki her `###` başlığı bir rota ya da rota içi görünümdür; tablo:

| # | Rota | Bölüm |
|---|---|---|
| 1–2 | `/editoryal`, `/kitap/:id` | Editoryal masa |
| 3–8 | `/basvurular`, `/basvurular/:id`, `/yayin-kurulu` (+`?gorunum=crm`), `/yayin-kurulu/oturum/:id`, `/yazar-giris`, `/yazar-giris/:id` | M1 |
| 9, 41 | `/gorevlerim`, `/editor-atama` | M2 |
| 10 | `/redaksiyon` | M3 |
| 11–14 | `/ceviri`, `/ceviri/masam`, `/ceviri/masam/:jobId`, `/ceviri/:jobId/kalite` | M4 |
| 15 | `/son-okuma` | M5 |
| 16–21 | `/kitap-tasarim`, `/kapak-arsivi`, `/:jobId`, `/:jobId/studyo`, `/:jobId/sayfalar`, `/:jobId/kapak` | M13/M14 |
| 22–25 | `/dijital-yayin`, `/dijital-yayin/kitap/:id`, `/dijital-yayin/firsatlar`, `/dijital-yayin/satis` | M36 |
| 26 | `/serbest-calisanlar` | M8 |
| 27 | `/uretim` | M12 |
| 28–31 | `/kisiler` (+3 yönlendirme) | Kişiler |
| 32 | `/yazar-iliskileri` | M7 |
| 33 | `/basin-web` | Basın ve web |
| 34–38 | `/telif-sozlesme`, `/yeni`, `/odemeler`, `/sablonlar`, `/:key` | M6 |
| 39–40 | `/telif-donem`, `/haklar` | M54 |
| 42–44 | `/kategori-agaci`, `/kategori-agaci/:section`, `/kategori-agaci/kitap/:id` | H1 |
| 45–49 | `/kurumsal-eposta`, `/ileti/:id`, `/rapor`, `/kurallar`, `/etiketleme` | H4 |

Kapsam dışı notu: **M10 İlk baskı** (`/ilk-baski`) menüde «Finans» alanındadır (`navModel.ts:265`), bu grubun
menüsünde değil — Finans grubunun raporuna bırakıldı. Editör motoru `apps/editor` ayrı bölümde (sonda).

**Bugünkü AI envanteri (özet, dosya:satır):** kitaba soru (`app.py:5811` → `editorial_books.py`, Hermes), redaksiyon
önerisi (`editorial_desk.py:502`), çeviri ham taslağı (`editorial_translation.py:1259`), çeviri kalite tahmini
(`editorial_translation_qe.py`), 19 son okuma denetimi (`apps/editor/src/editor/proofing/*`), stüdyo üretimi (resim,
profil, künye, pazarlama kiti, sesli okuma, efekt, çocuk gözüyle okuma, alt metin — `apps/editor/src/editor/production/*`),
yazar strateji önerisi (`app.py:4864`, `author_growth.py:450`), telif yenileme önerisi (`royalty_api.py:493`), hak
açıklaması sınıfı (`royalty_api.py:714`, `royalty.py:1784`), dijital hak notu ve rapor satırı eşleme (`dijital.py:877`,
`:1734`), basın-web ilgililik/ton (`web_watch.py:549`), kategori profili önerisi (`categories_propose.py:131`), e-posta
tür/öncelik/özet/başvuru çıkarma/yanıt taslağı (`mailbox_classify.py`). **AI olmayan:** M1 başvuru/kurul, yazar giriş
süreci, M2 atama, M6 sözleşme, M8 serbest çalışan, M12 üretim, Kişiler, Kapak arşivi.

---

## E0 Editoryal masa (Masam, Kitap 360)

### Masam (`/editoryal`)
- **Ne yapıyor:** Editörün ana ekranı: «Şimdi yapılacaklar», masasındaki eserler (redaksiyon bölümü/prova imzası),
  çeviri işleri, süresi yaklaşan sözleşmeler, CRM'de editörü olduğu yazar giriş projeleri (Tümü / Sizde bekleyen /
  Kurulda / Tamamlanan), editörlere göre dosyalar, kitap arama ve ZEKİ AI'ya kitap sorusu kutusu
  (`src/canvas/editorial/EditorialHome.tsx:22-451`). Açılış verisi köprüde önceden ısıtılır (`editorial_home.py`).
- **Kim:** Editör, yayın yönetmeni; günlük işi dosyaları ilerletmek, bekleyen kararı vermek, terminleri tutmak.
- **Bugün AI:** Var — `AskBox` (`EditorialHome.tsx:433`) kitap içeriğine kanıtlı soru; `POST /api/v1/editorial/ask`
  (`app.py:5807-5818`) → `editorial_books.ask` Hermes ajanına sorar, cevap sayfa numaralı, iç adlar ekranda silinir
  (`AskBox.tsx:7-12`). Sohbet PDF'i `editorial_export.py`. Masadaki iş listeleri modelsiz.
- **Beklenti:** (1) «Bugün neye bakmalıyım?» sorusuna süreç verisinden cevap (kurulda kaç dosya, hangi çeviri
  gecikiyor); (2) sabah tek paragraf durum özeti; (3) gecikme riski olan dosyanın önceden işaretlenmesi;
  (4) serbest aramada kitap/yazar/proje eşlemesi (yanlış yazımla da).
- **Yapabileceklerimiz:**
  - **Editoryal süreç sohbeti** — «hangi başvurular 30 günden fazladır değerlendirmede?», «X çevirisinin kaç segmenti
    kaldı?» gibi sorular. Veri: `semantic_editorial_*`, `semantic_translation_*`, `semantic_editorial_tasks`,
    `semantic_contracts`, CRM `new_projeBase`. Teknik: sohbet yanıtı (soru → onaylı sorgu kalıbı değil, veri katalogu
    üzerinden mevcut NL→SQL hattı); bugün `chat_topics.json`'da editoryal süreç konusu yok (yalnız «yayin» ve «telif»).
    Değer 5 · Zorluk M (3–4 g: katalog alanı + konu + yetki süzgeci) · Koruma: satır düzeyi yetki (kişi yalnız
    görebildiği dosyayı sorar), sayılar SQL'den.
  - **Sabah brifingi** — «sizde 3 prova imzası, 2 kurul dosyası, 1 geciken çeviri» özet cümlesi; ekranda ve iç e-posta.
    Veri: Masam'ın zaten hesapladığı sayaçlar. Teknik: özet/taslak (sayılar girdi, `marketing/guard.py` ile denetim).
    Değer 3 · Zorluk S (1 g; `author_reminders.py` deseni) · Koruma: yalnız iç alıcı, sayı denetimi.
  - **Gecikme riski işareti** — dosyanın aşamada bekleme süresi, editör yükü, termin; model yalnız gerekçe cümlesi.
    Veri: `editorial_intake` adım tarihleri, `semantic_editorial_tasks`. Teknik: kural (bekleme > ayar) + gerekçe
    taslağı. Değer 3 · Zorluk S · Koruma: eşik ayarda, model karar vermez.
- **Eksik/zayıf:** Masam'daki AskBox yalnız kitap metnine sorar; süreç sorularına cevap yolu yok.

### Kitap 360 (`/kitap/:id`)
- **Ne yapıyor:** Bir kitabın bütün kayıtları tek sayfada: Künye, Kitabın konusu, Emeği geçenler, Sözleşmeler, Yayın
  süreci (proje/kurul/üretim), Masadaki metin ve prova, editöre soru kuyruğu (`ReviewPanel`) ve kitaba soru
  (`BookScreen.tsx:40-318`). Sekme yok; bölümlü tek sayfa.
- **Kim:** Editör, yayın yönetmeni, telif, pazarlama — kitap hakkında hızlı bilgi.
- **Bugün AI:** Var — (a) CRM'de tür yoksa türü motor belirler ve «ZEKİ AI belirledi» notuyla gösterilir
  (`BookScreen.tsx:26-36`; motor `apps/editor/src/editor/book_type.py`, kapalı küme + olasılık); (b) `AskBox`
  kitaba özel (`BookScreen.tsx:318`), karakter ağı çizimi (`CharacterGraph.tsx`); (c) `ReviewPanel` motorun emin
  olamayıp editöre sorduğu yerler (`ReviewPanel.tsx:10-12`), karar AD kullanıcısıyla motora yazılır.
- **Beklenti:** (1) kitabın bir paragraflık özeti ve konu/tema etiketleri; (2) benzer kitaplar (katalogda,
  satışıyla); (3) «bu kitapta X geçiyor mu, hangi sayfada» aramaları; (4) künye–CRM tutarsızlığının burada görünmesi.
- **Yapabileceklerimiz:**
  - **Katalog içi benzer kitaplar** — özet/spot/arka kapak ve (okunmuşsa) motorun tema çıkarımıyla gömme benzerliği;
    listede satış rakamı Logo'dan. Veri: CRM `new_ozet`, `new_kitapspotu`, motor Qdrant indeksi, `V_SatisRaporu_<yıl>`.
    Teknik: gömme/benzerlik araması. Değer 4 · Zorluk M (3 g) · Koruma: benzerlik puanı değil gerekçe (ortak tema) gösterilir.
  - **Kitap özeti kartı** — okunmuş kitapta motorun `book_summary` çıktısı; okunmamışta CRM özetinden. Teknik: özet
    (motor zaten üretiyor, köprüde gösterilmiyor — doğrulanmadı). Değer 3 · Zorluk S · Koruma: kaynağı yazılır.
  - **Künye–CRM farkı rozeti** — son okumanın `imprint_crm` bulguları burada. Teknik: kural (var olan denetim).
    Değer 3 · Zorluk S.
- **Eksik/zayıf:** Kitabın M36 dijital durumu, H1 onaylı profili ve M54 hak kartı bu sayfada bağlı değil (doğrulanmadı:
  `BookScreen.tsx`'te bu modüllere bağlantı görülmedi).

---

## M1 Başvuru, yazar giriş süreci, yayın kurulu

### Başvurular (`/basvurular`)
- **Ne yapıyor:** Başvuru kuyruğu; sekmeler «Kuyruk / Kabul edilenler / Arşiv» (`ApplicationsScreen.tsx:17-19`).
  Kayıtlar köprü tablolarında (`semantic_editorial_application*`), CRM yalnız okunur (`editorial_applications.py:1-30`).
- **Kim:** Yayın yönetmeni (dağıtım), editör (değerlendirme), editoryal asistan.
- **Bugün AI:** Yok.
- **Beklenti:** (1) gelen dosyanın ilk elemesi (tür, hedef kitle, yayın ilkelerine uygunluk); (2) kuyruğun önceliklendirilmesi;
  (3) mükerrer başvuru/aynı yazarın eski başvurusunun bulunması; (4) hangi editöre gideceği önerisi.
- **Yapabileceklerimiz:**
  - **Başvuru ön okuması (triyaj kartı)** — yüklenen PDF/DOCX'i motor okur: tür/biçim (`book_type` ekseni), hedef yaş
    (okunabilirlik + `age_fit`), 5 satırlık konu özeti, yayın ilkesi risk işaretleri (alıntılı). Veri:
    `semantic_editorial_application_files`, motorun belge okuması (`apps/editor/src/editor/document_review.py`).
    Teknik: belge okuma + kapalı küme + alıntılı özet. Değer 5 · Zorluk L (5–6 g) · Koruma: puan/karar insanın; her
    iddia metinde birebir alıntıyla; yazarın kişisel bilgisi modele gitmez; «önerilir» dili.
  - **Mükerrer/eski başvuru eşlemesi** — başlık+yazar normalleştirme, belirsizde «aynı eser mi» kapalı küme.
    Veri: portal başvuruları + CRM `new_projeBase`, `new_dosyabasvuruBase`. Değer 3 · Zorluk S (1 g).
  - **Kuyruk sıralaması** — kategori (CRM Kitaplık) satış gücü + bekleme süresi kuralı; model yalnız gerekçe.
    Değer 2 · Zorluk S.
- **Eksik/zayıf:** Web başvuru formu (yazar/ajans tarafı) yok; başvurular içeriden ya da H4'ten aktarılıyor.

### Başvuru dosyası (`/basvurular/:id`)
- **Ne yapıyor:** Tek başvuru: Sıradaki adım, Başvuru dosyası, editör değerlendirmesi (içerik skoru, üç eksen puanı,
  sınıflandırma, katalog örtüşmesi, yayın ilkeleri, öneri, rapor metni — `EvaluationPanel.tsx:12`), Yayın Kurulu Raporu
  (3 senaryolu ilk yıl satış, kanal, katalog örtüşmesi — `ReportPanel.tsx:13`), kurul, yazışma, CRM proje kartı,
  karar notu (`ApplicationScreen.tsx:219-585`).
- **Kim:** Değerlendiren editör; yayın yönetmeni.
- **Bugün AI:** Yok. Satış senaryosu kural (kohort çeyrekleri, `editorial_applications_market.py:1-30`, «Model
  kullanılmaz»); katalog örtüşmesi başlık kelimesiyle SQL (`editorial_applications_market.py:136`); kabul/red/revizyon
  yazısı sabit şablon (`editorial_applications.py:925-958`).
- **Beklenti:** (1) editör raporunun taslağı (konu, güçlü/zayıf yan, hedef okur); (2) anlamca benzer katalog kitapları
  (başlık kelimesi değil konu); (3) red/revizyon yazısının başvuruya özgü kişiselleştirilmesi; (4) rapor metninden
  eksenlere puan önerisi.
- **Yapabileceklerimiz:**
  - **Editör raporu taslağı** — ön okuma kartından (yukarıda) rapor alanlarını doldurur: konu, tür, hedef kitle,
    güçlü/zayıf yan (alıntılı), yayın ilkeleri kontrol listesi. Teknik: taslak + alıntı denetimi. Değer 5 · Zorluk M
    (ön okumanın üstüne 2 g) · Koruma: puan alanlarını model doldurmaz; taslak «öneri» olarak işaretli, kaydeden editör.
  - **Anlamsal katalog örtüşmesi** — bugünkü başlık-kelime eşleşmesinin yanına konu gömmesi (başvuru özeti ↔ CRM
    `new_ozet`/spot). Teknik: benzerlik araması. Değer 4 · Zorluk M (2–3 g, ortak benzerlik altyapısıyla) · Koruma:
    kohort rakamları yine SQL; model yalnız «neden benzer» cümlesi.
  - **Yazı kişiselleştirme** — şablon korunur, iki cümlelik gerekçe paragrafı karar notundan taslaklanır.
    Teknik: taslak. Değer 3 · Zorluk S · Koruma: gönderim insanda (bugünkü «onayla → gönderildi işaretle» akışı),
    söz/tarih içeren cümle atılır (`mailbox_classify` kuralı).
  - **Kurul raporu anlatısı** — rapordaki sayıları açıklayan 3 cümle («kategori ortancası …»). Teknik: taslak +
    `guard.check`. Değer 3 · Zorluk S.
- **Eksik/zayıf:** Değerlendirme alanlarının hepsi elle; dosya metni hiçbir yerde okunmuyor.

### Yayın kurulu (`/yayin-kurulu`, `?gorunum=crm`)
- **Ne yapıyor:** Portal kurul oturumları listesi (gündem, üye oyu, karar); `?gorunum=crm` CRM'deki geçmiş kurul
  kararlarını gün gün gösterir (`BoardSessionsScreen.tsx:14-147`, `intake/MeetingScreen.tsx:13`).
- **Kim:** Kurul başkanı, üyeler, yayın yönetmeni.
- **Bugün AI:** Yok.
- **Beklenti:** (1) oturum öncesi gündem brifingi; (2) geçmiş kararlarla tutarlılık («benzer dosyaya ne demiştik?»);
  (3) karar tutanağı taslağı.
- **Yapabileceklerimiz:**
  - **Gündem brifingi** — her başvuru için yarım sayfa: özet, senaryo sayıları, editör önerisi, açık riskler.
    Veri: `semantic_editorial_applications`, rapor anlık görüntüsü. Teknik: özet + sayı denetimi. Değer 4 · Zorluk S
    (1–2 g) · Koruma: rakam rapordan kopya, `guard.check`.
  - **Benzer geçmiş kararlar** — CRM `new_yayinkurulutoplantilariBase` kararları + portal kararlarında konu
    benzerliği. Teknik: gömme araması. Değer 3 · Zorluk M · Koruma: yalnız karar ve gerekçe; üye oyu gizliliği korunur.
  - **Tutanak taslağı** — oturum kapanınca karar listesi + notlardan tutanak. Teknik: taslak. Değer 3 · Zorluk S.
- **Eksik/zayıf:** CRM geçmişinde üye puanı/oyu yok (`editorial_applications.py:3-6`); karşılaştırma yalnız karar düzeyinde.

### Kurul oturumu (`/yayin-kurulu/oturum/:id`)
- **Ne yapıyor:** Gündemdeki her başvuruya üyenin üç eksen puanı ve oyu, oy dağılımı, başkanın kararı; oy vermeden
  başkalarının oyu görünmez (`SessionScreen.tsx:16`, `editorial_applications.py:22-28`).
- **Kim:** Kurul üyeleri, başkan.
- **Bugün AI:** Yok.
- **Beklenti:** (1) oy verirken dosyanın özeti ve rapora tek tıkla dönüş; (2) üye notlarının özetlenmesi (başkan için);
  (3) karar gerekçesi taslağı.
- **Yapabileceklerimiz:**
  - **Üye notları özeti (başkana)** — oylar kapanınca notlardan ortak görüş/ayrışma özeti. Teknik: özet. Değer 3 ·
    Zorluk S · Koruma: yalnız «üye görüşleri» yetkisine; oy verilmeden üretilmez (etkilenme kuralı).
  - **Karar gerekçesi taslağı** — oy dağılımı + notlardan bir paragraf; karar insanın. Değer 3 · Zorluk S.
- **Eksik/zayıf:** Yok (akış tam; AI isteğe bağlı).

### Yazar giriş süreci panosu (`/yazar-giris`)
- **Ne yapıyor:** Müşterinin 9 adımlık akışı üç evrede pano; her kart bir CRM projesi, adımlar CRM kanıtından çıkarılır
  (`editorial_intake.py:1-30`, `IntakeBoardScreen.tsx:13`); H4'ten gelen e-posta başvuruları üstte listelenir.
- **Kim:** Yayın yönetmeni (bütün editörler), editör (kendi projeleri).
- **Bugün AI:** Yok.
- **Beklenti:** (1) takılan projenin nedeni; (2) editör bazında darboğaz özeti; (3) sıradaki adımın hatırlatılması.
- **Yapabileceklerimiz:**
  - **Darboğaz özeti** — evre başına bekleme dağılımı ve en çok bekleyen editör; model yalnız cümle. Veri:
    `editorial_intake` adım tarihleri. Teknik: kural + özet. Değer 3 · Zorluk S.
  - **Adım tutarsızlığı açıklaması** — «kurul kabul, statü hâlâ toplantıya hazırlanıyor» (117 proje, `editorial_intake.py:3-6`)
    gibi durumları CRM'e işlenecek fark listesine çevirir. Teknik: kural; model yok. Değer 3 · Zorluk S.
- **Eksik/zayıf:** «Sıradaki kurul» üretilemiyor (CRM'de ileri tarihli kurul kaydı yok).

### Yazar giriş projesi (`/yazar-giris/:id`)
- **Ne yapıyor:** Bir projenin 9 adımı: ne bitti, ne zaman, kimde bekliyor; iki adım («Rapor bitti», «Bildirdim»)
  portaldan işaretlenir (`IntakeProjectScreen.tsx:11`, `intake/parts.tsx:67`).
- **Kim:** Editör, yayın yönetmeni.
- **Bugün AI:** Yok.
- **Beklenti:** (1) projeyle ilgili bütün yazışma/not özeti; (2) yazara bilgi e-postası taslağı («Bildirdim» adımı).
- **Yapabileceklerimiz:**
  - **Yazara bilgi taslağı** — adım 6 için kabul yazısı M1 şablonundan + proje verisi. Teknik: taslak. Değer 3 ·
    Zorluk S · Koruma: gönderim insanda, taslakta tarih/söz yok.
  - **Proje zaman çizgisi özeti** — CRM olayları + portal işaretleri → 3 cümle. Değer 2 · Zorluk S.
- **Eksik/zayıf:** Adım 6'nın CRM kanıtı yok; yalnız portal işareti.

---

## M2 Editör atama

### Görevlerim (`/gorevlerim`)
- **Ne yapıyor:** Editörün görev panosu: sırada → çalışılıyor → beklemede → tamamlandı; CRM'de editörü olduğu ama panoda
  olmayan projeler «Panoma al»; termin değişikliği gerekçe ister (`MyTasksScreen.tsx:1-10`, `editorial_assign.py:4-10`).
- **Kim:** Editör.
- **Bugün AI:** Yok.
- **Beklenti:** (1) gerçekçi termin önerisi (sayfa, tür, geçmiş hız); (2) haftalık iş planı; (3) termin gerekçesinin
  kısa yazımı.
- **Yapabileceklerimiz:**
  - **Termin tahmini** — editörün geçmiş görevlerinden sayfa başına süre (ortanca) × tahmini sayfa; model yok, istatistik.
    Veri: `semantic_editorial_tasks` geçmişi. Değer 3 · Zorluk S (1 g) · Koruma: yetersiz geçmişte «tahmin yok».
  - **Haftalık plan taslağı** — açık görevler + terminler → gün gün öneri. Teknik: kural sıralama + özet. Değer 2 · Zorluk S.
- **Eksik/zayıf:** CRM'de metin teslim/hedef baskı tarihi neredeyse hiç dolu değil (`editorial_assign.py:15-17`); takvim yalnız portal terminiyle.

### Editör atama (`/editor-atama`)
- **Ne yapıyor:** Sekmeler «Atama bekleyen / İş yükü / Takvim / Kural tablosu / Bütün projeler» (`EditorsScreen.tsx:21-25`);
  aday editörler kural+geçmiş+müsaitlikten puan ve gerekçeyle önerilir, «Model kullanılmaz» (`editorial_assign.py:19`).
- **Kim:** Yayın yönetmeni, editoryal koordinatör.
- **Bugün AI:** Yok (kurallı öneri var).
- **Beklenti:** (1) kitabın içeriğine göre uzmanlık eşlemesi (kategori dışında konu); (2) destek editör önerisi;
  (3) kural tablosunun geçmiş atamalardan önerilmesi.
- **Yapabileceklerimiz:**
  - **Konu uzmanlığı sinyali** — editörün geçmişte çalıştığı kitapların konu gömmesi ↔ yeni projenin özeti; mevcut
    sözlük sıralamasına ayrı sinyal olarak eklenir (gizli ağırlık yok). Veri: CRM `new_projeBase.new_editoru`, kitap
    özetleri. Teknik: benzerlik. Değer 3 · Zorluk M (2 g) · Koruma: sinyal ayrı gösterilir, karar insanın.
  - **Kural tablosu taslağı** — son 24 ay atamalarından kategori → birincil/yedek editör önerisi (sayım), onaya taslak.
    Teknik: kural (sayım), model yok. Değer 3 · Zorluk S.
- **Eksik/zayıf:** Kategori ölçümü: Kitaplık 2.738 projenin yalnız 1.341'inde dolu (`editorial_assign.py:15`); H1 onaylı profil bağlanırsa öneri güçlenir.

---

## M3 Redaksiyon

### Redaksiyon (`/redaksiyon`)
- **Ne yapıyor:** Metin dosyası (DOCX/TXT/PDF) yüklenir, bölümlere ayrılır, ölçülür (Ateşman, cümle uzunluğu, hece);
  «ZEKİ ile denetle» yazım ve üslup önerisi çıkarır, editör kabul/ret eder, ilk hâlden fark gösterilir
  (`RedactionScreen.tsx:10-246`, `editorial_desk.py:1-15`).
- **Kim:** Redaktör, editör.
- **Bugün AI:** Var — `POST /api/v1/editorial/chapters/{id}/review` (`app.py:5071-5078`) → `editorial_desk.start_review`
  900 kelimelik parçalarla modele sorar; sistem istemi TDK yazım + üslup, JSON öneri, «ozgun» metinde birebir olmalı
  (`editorial_desk.py:502-560`).
- **Beklenti:** (1) yayınevinin üslup kılavuzuna (tercih/kaçınılan kelime) göre öneri; (2) tutarlılık (ad yazımı, sayı
  yazımı, tırnak türü) kitap genelinde; (3) hedef yaşa göre ağır kelime işaretleme; (4) öneri gerekçesinin TDK kuralıyla verilmesi.
- **Yapabileceklerimiz:**
  - **Son okuma denetimlerini redaksiyona taşıma** — motorun `spelling`, `name_spelling`, `word_variety`,
    `sentence_starts`, `phrase_repeats`, `word_choice` denetimleri zaten belge incelemesinde çalışıyor
    (`DocumentReview.tsx:13-16`); redaksiyon bölümüne aynı bulgular. Teknik: var olan denetim. Değer 4 · Zorluk M (2–3 g)
    · Koruma: tek yazım mekanizması (bugün köprü istemi ile motorun kural+sözlük denetimi ayrı — ikisi çelişebilir).
  - **Üslup kılavuzu** — yayınevinin tercih/kaçınılan listesi (ekrandan yönetilir) istemin girdisi ve kural denetimi.
    Teknik: kural + kapalı küme. Değer 4 · Zorluk M · Koruma: liste insan onaylı, kitaba özel değil.
  - **Öneri isabeti** — kabul/ret oranı öneri türüne göre sayılır (son okumadaki `proof_decision` deseni). Değer 3 · Zorluk S.
- **Eksik/zayıf:** Stitch'teki «Versiyon arşivi», «TDK özel isim tablosu», «revizyon raporu» yok (`editoryal-m1-m8-eksikler-2026-09-20.md:55-60`).

---

## M4 Çeviri

### Çeviri yönetimi (`/ceviri`)
- **Ne yapıyor:** Sekmeler «Çeviri işleri / Terim bankası / Çeviri belleği / Çevirmenler» (`TranslationScreen.tsx:21`);
  iş açma, kaynak segmentleme, atama, ilerleme, ZEKİ ham taslak, ZEKİ kalite tahmini paneli, M8 hakediş bağı
  (`PayoutPanel.tsx`, `translation_payout.py`), XLIFF/TMX/TBX içe-dışa (`editorial_translation_io.py`).
- **Kim:** Çeviri koordinatörü, yayın yönetmeni.
- **Bugün AI:** Var — (a) ham taslak: `POST …/translation/jobs/{id}/draft` (`app.py:5276-5286`), üç geçiş (taslak,
  kapalı ikinci okuma, modelsiz denetim onarımı; `editorial_translation.py:1259-1275`), taslak ayrı sütunda;
  (b) kalite tahmini `POST …/qe` (`app.py:5296`, `editorial_translation_qe.py:1-25`), 0–100 puan + MQM kategorisi +
  birebir alıntı kuralı; (c) çevirmen eşleme modelsiz (`editorial_translation_match.py:1`).
- **Beklenti:** (1) kaynak metinden terim adaylarının çıkarılması; (2) çevirmen seçiminde üslup/tür uyumu;
  (3) teslim riski erken uyarı; (4) iş için maliyet/süre tahmini.
- **Yapabileceklerimiz:**
  - **Terim adayı çıkarımı** — kaynak metinde sık geçen özel ad/kavram öbekleri (kural: sıklık + büyük harf + öbek),
    model yalnız «terim mi» evet/hayır ve karşılık önerisi; adayı koordinatör onaylar. Veri: segmentler, terim bankası.
    Teknik: kural + kapalı küme + taslak. Değer 4 · Zorluk M (2–3 g) · Koruma: onaysız terim denetime girmez.
  - **Teslim riski** — son 30 gün hızı × kalan kelime (eşleme modülünde hesap var) → «teslime yetişmez» işareti.
    Teknik: kural. Değer 3 · Zorluk S.
  - **Çevirmen tür uyumu sinyali** — çevirmenin geçmiş işlerinin türü (M4 işleri + CRM tercüme rolü kitapları) ↔
    yeni kitabın türü. Teknik: kural/benzerlik. Değer 2 · Zorluk S.
- **Eksik/zayıf:** İkinci okuma kapalı; ölçüm tek bölümde (Alice, 796 kelime; `editorial_translation.py:1269-1272`) — daha geniş ölçüm gerek.

### Çeviri masam (`/ceviri/masam`, `/ceviri/masam/:jobId`)
- **Ne yapıyor:** Çevirmen/inceleyen ekranı: bölüm segmentleri (kaynak | hedef), yan panelde terimler, çeviri belleği,
  ZEKİ taslağı, otomatik denetim, ZEKİ kalite tahmini; süzgeçler («ZEKİ taslağı bekleyen», «ZEKİ şüpheli»),
  segment birleştir/böl (`Workbench.tsx:39-1071`, `SegmentTools.tsx`, `qe.tsx`). `:jobId`siz rota iş seçimi.
- **Kim:** Çevirmen, inceleyen (redaktör).
- **Bugün AI:** Var — taslağı boş segmentlere yerleştirme (`Workbench.tsx:827`), segment başı QE puanı ve gerekçe
  (`qe.tsx:94-128`). Bellek eşleşmesi modelsiz (birebir/benzer).
- **Beklenti:** (1) seçili segment için anında alternatif çeviri (2–3 seçenek); (2) terim tutarsızlığının yazarken
  gösterilmesi; (3) inceleyen için MQM hata kategorisi önerisi; (4) deyim/ünlem gibi zor yerlerin işaretlenmesi.
- **Yapabileceklerimiz:**
  - **Segment alternatifi** — tek segment için 2 seçenek (bağlam: önceki/sonraki segment + terimler). Teknik: taslak
    (etkileşimli öncelik). Değer 3 · Zorluk S (1–2 g) · Koruma: hedefe kendiliğinden yazılmaz; modelsiz denetimden geçer.
  - **MQM kategorisi önerisi (inceleyene)** — inceleyen düzeltince fark için kapalı küme (anlam/eksik/terim/dilbilgisi/
    yazım/üslup/biçim). Teknik: `QueuedLlm.choose`. Değer 3 · Zorluk S · Koruma: kategori insan onaylı; puan kuraldan.
  - **Bellekte anlamsal eşleşme** — bugünkü benzer eşleşmeye gömme tabanlı «anlamca yakın» segment. Değer 2 · Zorluk M.
- **Eksik/zayıf:** Yok (ekran olgun).

### Kalite raporu (`/ceviri/:jobId/kalite`)
- **Ne yapıyor:** İşin gerçek kayıtlarından MQM inceleme puanı, düzeltme oranı, ilerleme; ayrıca işaretli «ZEKİ kalite
  tahmini» paneli (dağılım, bölüm özeti, en düşük segmentler) (`QualityReport.tsx:12-302`, `qe.tsx:221-320`).
- **Kim:** Koordinatör, yayın yönetmeni.
- **Bugün AI:** Var — QE paneli (yukarıda).
- **Beklenti:** (1) raporun yönetici için 3 cümlelik yorumu; (2) çevirmene geri bildirim metni taslağı.
- **Yapabileceklerimiz:**
  - **Rapor yorumu + geri bildirim taslağı** — MQM ve QE sayılarından; en sık hata kategorisi örnekleriyle. Teknik:
    özet + `guard.check`. Değer 3 · Zorluk S · Koruma: çevirmene gönderim insanda.
  - **QE ↔ MQM uyum ölçümü** — insan incelemesi olan segmentlerde tahminin isabeti (şüpheli eşiği ayarı için).
    Teknik: kural. Değer 3 · Zorluk S.
- **Eksik/zayıf:** QE tahmininin insan MQM'iyle uyumu raporlanmıyor (doğrulanmadı).

### Çevirmenler (menü → `/kisiler?rol=cevirmen`)
- Kişiler ekranının «Çevirmenler» sekmesidir (`navModel.ts:305`, `modules.tsx:27-35`); aşağıda **Kişiler** başlığında.
  Çeviri karnesi ise `/ceviri?sekme=cevirmenler` (`Translators.tsx:9`, modelsiz).

---

## M5 Son okuma

### Son okuma (`/son-okuma`)
- **Ne yapıyor:** Üç parça: (a) prova PDF'i ön kontrolü (sayfa, ebat, gömülü font, renk uzayı, ISBN, forma) + kontrol
  listesi + SHA-256'ya imza (`ProofScreen.tsx:14-16`, `editorial_desk.py:8-12`); (b) motorun kitap metninde koştuğu son
  okuma denetimleri: bulgu listesi, sayfa görseli üzerinde işaret, «Doğru / Yanlış alarm» kararı, Word'e yorum olarak dışa
  aktarım, kelime haritası (`ProofFindings.tsx`, `ProofEvidence.tsx`, `WordMapPanel.tsx`); (c) belge incelemesi
  (yüklenen doc/docx/pdf/odt/rtf/txt/md'de metin denetimleri, `DocumentReview.tsx:13-16`).
- **Kim:** Son okuyucu, editör, yayın yönetmeni (imza).
- **Bugün AI:** Var — 19 denetim (`apps/editor/docs/son-okuma/README.md` tablosu; görev metnindeki «15» sayısı güncel
  değil): deterministik 5 (edition_diff, hyphenation, imprint_crm, layout, series_canon), model yargılı 14
  (age_fit, appearance, dialogue, name_spelling, props, setting, spelling, text_contradictions, timeline, word_variety,
  word_overuse, sentence_starts, phrase_repeats, word_choice). Karar → `ed.proof_decision`, isabet denetim+sürüm başına;
  aynı kitapta karar taşınır (`_carry.py`). Durum: çoğu «ölçüm bekliyor/kısmen».
- **Beklenti:** (1) bulguların önem sırasıyla ve toplu kararla hızlı geçilmesi; (2) yanlış alarmın azalması;
  (3) prova PDF'inde metin–dizgi farkı (yetim/dul satır, kırık hece) ; (4) baskı riski özeti.
- **Yapabileceklerimiz:**
  - **İsabet panosu + düşük isabetli kuralın kapatılması önerisi** — `ed.proof_decision`'dan denetim başına isabet;
    ret gerekçesi dağılımından «sözlük eksiği/sayfa hatası/yargı» yönü. Teknik: kural (SQL README'de var). Değer 4 ·
    Zorluk S (1 g) · Koruma: kural değişikliği insanın, kitaba özel değil.
  - **Baskı riski özeti** — ön kontrol + ciddi bulgular → imzacıya tek paragraf. Teknik: özet + sayı denetimi. Değer 3 · Zorluk S.
  - **Prova ↔ son onaylı metin farkı** — prova PDF metni ile M3'te onaylı metnin kelime dizisi (stüdyonun
    `preflight` «metin eksiksiz» kuralı zaten var) — dışarıda dizilen kitap için de. Teknik: kural. Değer 4 · Zorluk M.
- **Eksik/zayıf:** Denetimlerin çoğunda gerçek kitapta etiketli isabet ölçümü yok; kurgu dışı kitaplar için tür
  eksenleri (bkz. Editör motoru) belgede aşamalı.

---

## M13/M14 Kitap Tasarım Stüdyosu

Ortak: köprü yalnız vekildir (`backend/semantic_bridge/editorial_studio*.py`); iş, GPU'daki stüdyo servisinde
(`apps/editor/src/editor/production/*`, Temporal `editor-production`). Görsel model açılınca ana model durur.

### Stüdyo girişi (`/kitap-tasarim`)
- **Ne yapıyor:** Okunmuş bir kitaptan ya da Word dosyasından yeni tasarım işi başlatır; önceki işleri listeler;
  üretim yetkisi `tasarim.uret` (`StudioHome.tsx:1-8`).
- **Kim:** Grafik/tasarım, çocuk kitabı editörü, yayın yönetmeni.
- **Bugün AI:** Dolaylı — iş başlayınca hat modelle profil/üslup/sahne üretir (aşağıda).
- **Beklenti:** (1) hangi kitabın tasarıma uygun olduğunun önerilmesi (resimli çocuk, yeni baskı); (2) iş başına GPU süre tahmini.
- **Yapabileceklerimiz:**
  - **Süre tahmini** — geçmiş işlerin adım süreleri (sayfa × resim sayısı) → bekleme tahmini. Teknik: kural/istatistik.
    Değer 2 · Zorluk S.
- **Eksik/zayıf:** Lisans bekleniyor notu (görsel model; `MEMORY` kaydı) — ekranda durum görünürlüğü doğrulanmadı.

### Tasarım akışı (`/kitap-tasarim/:jobId`)
- **Ne yapıyor:** İçerik, CRM proje bilgisi, «sistemin kararları» (profil: yaş, tür, resim ihtiyacı; spec) ve canlı üretim
  adımları; sayfa şeridi dizilmiş PDF'ten (`StudioFlow.tsx:13-14`).
- **Kim:** Tasarım, editör.
- **Bugün AI:** Var — profil üç kaynaktan (beyan/CRM, metin ölçümü, ana modelin alıntılı okuması; 2 yıldan fazla
  ayrışma editöre gösterilir, `production/profile.py`), üslup rehberi ve sahne tarifleri alıntıyla bağlı
  (`production/art.py`), künye alanları alıntıyla (`production/front.py`).
- **Beklenti:** (1) kararların gerekçesiyle görülmesi (var); (2) üslup seçeneklerinin görsel örnekle karşılaştırılması.
- **Yapabileceklerimiz:**
  - **Üslup önerisi kapak arşivinden** — aynı kategori/yaştaki satış lideri kapakların görsel özellikleri (renk paleti,
    resimli/tipografik) → üslup rehberine girdi. Veri: `ed.cover_library`, T-soft satış. Teknik: görsel okuma + kural.
    Değer 3 · Zorluk M · Koruma: kitaba özel değil, kategori düzeyi.
- **Eksik/zayıf:** Yok.

### Sayfa stüdyosu (`/kitap-tasarim/:jobId/studyo`)
- **Ne yapıyor:** Açılım açılım kitap; resimli sayfa ve kapak için «DÜZELT» (seçili sürümü referans alır) ve «FARKLI
  ÜRET»; onaysız resim ön baskıyı geçmez (`StudioEditor.tsx:19-22`). Paneller: Pazarlama kiti (arka kapak, ürün sayfası,
  sosyal, öğretmen kılavuzu), Karakter kartları, E-kitap (alt metin), Boyama kitabı, Sesli okuma (ifade, sözlük, efekt,
  ses seçimi/yükleme), Yaş uygunluğu raporu, 3B kitap ve baskı provası (`StudioEditor.tsx:10-16`).
- **Kim:** Tasarım, editör, pazarlama (kit), eğitim/okul ekibi (kılavuz).
- **Bugün AI:** Var — resim üretimi/düzenleme + büyütme (`production/images.py`), seri karakter kartı (`characters.py`),
  pazarlama metinleri pencereli özetle, alıntılar birebir (`marketing.py:1-11`, `:393-672`), ürün sayfası SEO önerisine
  «öneri» olarak, T-soft'a yazılmaz (`editorial_studio_marketing.py`), alt metin (`epub.py:18-20`), sesli okuma +
  ifade önerisi (`expression.py`), efekt ipucu (`sfx.py`), yaş raporu (`age_report.py`), boyama çizgisi (modelsiz
  `lineart.py` + isteğe bağlı model yeniden çizimi).
- **Beklenti:** (1) resimde metinle çelişkinin otomatik yakalanması; (2) karakter tutarlılığının sayfa sayfa denetimi;
  (3) arka kapak/ürün metninin marka diline uyumu; (4) sesli okumada telaffuz hatası yakalama.
- **Yapabileceklerimiz:**
  - **Resim–metin tutarlılık denetimi** — üretilen sayfa resmi görsel okuyucuyla okunur, sahne tarifindeki karakter/
    nesne sayısı ve renk kartı ile karşılaştırılır; uyuşmayan sayfa «gözden geçir». Veri: `studio.json`, karakter kartı.
    Teknik: görsel okuma + kapalı küme + oylama (tek okuma gürültü — `editor-single-visual-read` kuralı). Değer 4 ·
    Zorluk M (3 g) · Koruma: onay insanda; en az 3 okuma oyu.
  - **Telaffuz sözlüğü önerisi** — okunuşta sözlükte olmayan özel ad/yabancı kelime listesi, editör okunuşu yazar
    (`LexiconEditor` var). Teknik: kural. Değer 3 · Zorluk S.
  - **Marka dili denetimi** — pazarlama metinlerinde yasak/tercih ifade listesi (M19 çekirdeğiyle ortak). Değer 2 · Zorluk S.
- **Eksik/zayıf:** Sesli okuma ifade katmanında açık konu: ton cümle içinde taşınamıyor (`docs/analiz/sesli-okuma-ifade-katmani.md:159-162`).

### Sayfa düzeni (`/kitap-tasarim/:jobId/sayfalar`)
- **Ne yapıyor:** Donmuş sayfa planının düzenlenmesi (kutu, balon, efekt yazı, şekil, figür, fotoğraf), okur araçları
  (çocuk gözüyle okuma, sayfa çevirme merakı), sürüm farkı (`PlanEditor.tsx:30-96`, `reader/`, `diff/`, `elements/`).
- **Kim:** Tasarım, mizanpaj, çocuk kitabı editörü.
- **Bugün AI:** Var — çocuk gözüyle okuma: hedef yaşın alt ucundaki okur gibi sayfa sayfa takılma işaretleri, alıntı
  zorunlu, çok okuma (`production/reader.py:1-15`); figür üretimi/kalite artırma (`flow.py`).
- **Beklenti:** (1) taşan/sığmayan metin için yerleşim önerisi; (2) okunurluk (kontrast, punto) uyarısı yazarken.
- **Yapabileceklerimiz:**
  - **Otomatik yerleşim önerisi** — taşan kutu için punto/kutu/sonraki sayfa seçenekleri kuralla sıralanır; model yok.
    Değer 3 · Zorluk M. · Koruma: öneri, uygulama editörün.
  - **Anlık düzen denetimi** — son okumanın `layout` kuralları (kontrast, kenar payı) plan kaydında. Değer 3 · Zorluk S.
- **Eksik/zayıf:** Yok.

### Kapak (`/kitap-tasarim/:jobId/kapak`)
- **Ne yapıyor:** Kapak tarzı (resimli / kolaj / tipografik) ve kolaj ayarları; kolajda fotoğraf adayları üretilir ya da
  editör yükler (`collage/CoverScreen.tsx:13`, `production/collage.py:822-824`).
- **Kim:** Grafik tasarım, pazarlama.
- **Bugün AI:** Var — kolaj fotoğraf adayı: sahne istemi (dil modeli) → görsel model, 2–3 tohum (`collage.py:12`, `:822`).
- **Beklenti:** (1) kapağın rafta/küçük görselde okunurluğu; (2) aynı kategorideki kapaklardan ayrışma; (3) başlık
  alternatifleri değil (editör işi) — alt başlık/spot önerisi.
- **Yapabileceklerimiz:**
  - **Küçük boy okunurluk ve ayrışma denetimi** — kapak 150 px'e küçültülür, başlık kontrastı ölçülür (kural); kapak
    arşivindeki kategori komşularına görsel benzerlik (gömme). Değer 3 · Zorluk M · Koruma: yalnız uyarı.
- **Eksik/zayıf:** Yok.

### Kapak arşivi (`/kitap-tasarim/kapak-arsivi`)
- **Ne yapıyor:** Yayımlanmış kapaklar sitedeki kategori ağacıyla; T-soft ürünü + CRM kartı beslemesi, metin araması
  (`library/CoverLibraryScreen.tsx:19`, `editorial_studio_library.py:1-20`).
- **Kim:** Tasarım, pazarlama, editör (örnek arama).
- **Bugün AI:** Yok (metin araması).
- **Beklenti:** (1) «buna benzer kapaklar» görsel araması; (2) renk/tarz ile süzme; (3) satışı iyi kapakların ortak özelliği.
- **Yapabileceklerimiz:**
  - **Görsel benzerlik araması** — kapak görsellerinin gömmesi (yerel görsel model), «benzerini bul» ve yüklenen
    taslağa en yakın arşiv kapakları. Teknik: gömme/benzerlik. Değer 3 · Zorluk M (3 g) · Koruma: yalnız iç arşiv.
  - **Tarz etiketleri** — resimli/fotoğraf/tipografik, baskın renk: kural (renk histogramı) + kapalı küme. Değer 2 · Zorluk S.
- **Eksik/zayıf:** Müşteri VM'inde T-soft tanımlı değil → besleme boş (`editorial_studio_library.py:12-13`).

---

## M36 Dijital yayın (Editoryal menüsünde)

### Dijital katalog (`/dijital-yayin`, `/dijital-yayin/kitap/:id`)
- **Ne yapıyor:** Sekmeler «Katalog / Hak riski / CRM'e işlenecek / Platformlar» ve süzgeçler (dijitalde, hakkı var-dijitalde
  yok, fırsat, stüdyoda e-kitap hazır…) (`DigitalCatalog.tsx:14-33`); hak kararı kurallı, CRM'e/platforma yazma yok
  (`dijital.py:1-15`). `kitap/:id` aynı bileşende kitap ayrıntısı.
- **Kim:** Dijital yayın sorumlusu, telif birimi.
- **Bugün AI:** Var — gece hak notu ön okuması: `new_haklaraciklama` → «dijitali kısıtlıyor / kısıtlamıyor / belirsiz»
  (`dijital.py:242`, `:877`, `QueuedLlm.choose`).
- **Beklenti:** (1) hak notlarının önceliklendirilmesi (var); (2) platform tanıtım metni taslağı; (3) e-kitaba
  dönüşüm için kitap önceliği.
- **Yapabileceklerimiz:**
  - **Platform tanıtım metni taslağı** — CRM özet/spot/öne çıkan yanlar → platform karakter sınırlı metin. Teknik: taslak;
    stüdyonun ürün sayfası üretimi yeniden kullanılır. Değer 3 · Zorluk S · Koruma: platforma gönderim insanda.
  - **Hak notu sınıfını M54 sınıfıyla birleştirme** — bugün iki ayrı sınıflama var (dijital 3 sınıf, M54 6 sınıf) aynı
    alan üzerinde; tek onaylı hak haritasından türetilmeli. Değer 3 · Zorluk S.
- **Eksik/zayıf:** Aynı `new_haklaraciklama` alanı iki modülde ayrı ayrı modele soruluyor (`dijital.py:877`, `royalty_api.py:718`).

### Fırsatlar (`/dijital-yayin/firsatlar`)
- **Ne yapıyor:** Sekmeler «E-kitap fırsatları / Sesli kitap adayları»; hakkı olan, basılıda iyi satan, dijitali olmayan
  kitaplar; sıra son 12 ay Logo net adedi; CSV (`OpportunitiesScreen.tsx:12-17`). Gerekçe cümlesi kuraldan (`dijital.py:491`).
- **Kim:** Dijital yayın, yayın yönetmeni.
- **Bugün AI:** Yok (gerekçe şablonlu).
- **Beklenti:** (1) sesli kitaba uygunluk (diyalog oranı, tür); (2) dijitalde satış tahmini.
- **Yapabileceklerimiz:**
  - **Sesli kitap uygunluk sinyali** — okunmuş kitapta motorun diyalog/anlatı ölçüsü ve türü; kural. Değer 3 · Zorluk S.
  - **Dijital satış tahmini** — benzer dijital kitapların platform raporu satışı (kohort çeyrekleri; M1 deseni), model
    yok. Değer 3 · Zorluk M · Koruma: az veri → «tahmin yok».
- **Eksik/zayıf:** Yok.

### Dijital satış (`/dijital-yayin/satis`)
- **Ne yapıyor:** Sekmeler «Pano / Raporlar»; platform raporu yükleme sihirbazı, kurallı eşleme, onaylı raporlardan gelir,
  Logo e-kitap faturası ayrı sütun (`DigitalSalesScreen.tsx:13-19`, `ImportWizard.tsx`).
- **Kim:** Dijital yayın, finans.
- **Bugün AI:** Var — kurallı eşleşmeyen rapor satırına aday kitap + olasılık (`dijital.py:1720-1740`, «hiçbiri» seçeneği),
  insan onaylar (`ImportWizard.tsx:11-18`).
- **Beklenti:** (1) yeni platform rapor biçiminde kolon eşlemesinin önerilmesi; (2) aylık dijital gelir yorumu.
- **Yapabileceklerimiz:**
  - **Kolon eşleme önerisi** — başlık adları + örnek satırlardan «bu kolon ISBN/adet/tutar mı» kapalı küme. Değer 3 · Zorluk S.
  - **Aylık yorum** — pano sayılarından 3 cümle + `guard.check`. Değer 2 · Zorluk S.
- **Eksik/zayıf:** Yok.

---

## M8 Serbest çalışanlar

### Serbest çalışanlar (`/serbest-calisanlar`)
- **Ne yapıyor:** Sekmeler «Kişiler / İş paketleri / Kapasite / Hakediş / Yazışmalar» (`FreelanceScreen.tsx:79-83`);
  kişi kartı, portfolyo, paket/görev, kapasite, teslim-kabul, hakediş, Logo cari hareketleri yan yana
  (`freelance.py:1-20`, `freelance_logo.py`).
- **Kim:** Editoryal koordinatör, grafik yönetmeni, finans (hakediş).
- **Bugün AI:** Yok (toplu dağıtım önerisi kurallı: rol + boş saat + zamanında teslim).
- **Beklenti:** (1) portfolyodan üslup etiketleri (çizim tarzı); (2) iş paketine uygun çizer önerisi üslupla;
  (3) gelen e-posta yanıtının akışa özetlenmesi; (4) teslim dosyasının ön kontrolü (çözünürlük, renk).
- **Yapabileceklerimiz:**
  - **Portfolyo üslup etiketi** — yüklenen görsellerden kapalı küme etiket (suluboya, çizgisel, dijital, karikatür…),
    kişi onaylar. Veri: portfolyo dosyaları. Teknik: görsel okuma + kapalı küme. Değer 3 · Zorluk M (2 g) · Koruma:
    etiket insan onaylı; sözlük yönetim ekranında.
  - **Teslim ön kontrolü** — görsel dosyada dpi, renk uzayı, ebat (stüdyonun `photo.py`/`preflight` kuralları). Teknik:
    kural. Değer 3 · Zorluk S.
  - **Yazışma özeti** — paket akışının son durum özeti. Teknik: özet. Değer 2 · Zorluk S · Koruma: kişisel iletişim
    bilgisi modele gitmez.
- **Eksik/zayıf:** Stitch'teki «portfolyo stil taraması» model işi olarak listelenmiş, yapılmamış (`editoryal-m1-m8-eksikler-2026-09-20.md:128`).

---

## M12 Üretim yönetimi

### Üretim yönetimi (`/uretim`)
- **Ne yapıyor:** Sekmeler «Üretim takvimi / Gecikmeler / Matbaalar / Geriye takvim» (`ProductionScreen.tsx:18-22`);
  CRM üretim kartı + Logo üretim emri/giriş fişi, dört dönüm noktası, gecikme basamakları, matbaa puanı, teklifler
  (`production.py:1-20`, `production_plan.py`, `production_store.py`). Kart ayrıntısı `CardSheet.tsx`.
- **Kim:** Üretim/prodüksiyon müdürü, yayın yönetmeni, satın alma.
- **Bugün AI:** Yok.
- **Beklenti:** (1) gecikme riski ve dengeleme önerisi (aynı ay yığılması); (2) matbaa seçiminde gerekçeli öneri;
  (3) matbaaya sipariş formu/şartname taslağı; (4) Logo fatura ↔ üretim kartı eşlemesi.
- **Yapabileceklerimiz:**
  - **Dengeleme gerekçesi** — kural (öncelik, yayın ayı, kritik yol payı) hesabı + model gerekçe cümlesi (M52 §13).
    Değer 4 · Zorluk M (2 g) · Koruma: sayılar kuraldan, `guard.check`.
  - **Şartname taslağı** — kartın teknik alanlarından (ebat, kağıt, cilt, lak, adet) matbaaya yazı taslağı. Teknik: taslak
    (alanlar kopya). Değer 3 · Zorluk S · Koruma: gönderim insanda, CRM'e yazılmaz.
  - **Fatura ↔ kart eşleme** — belirsiz eşleşmede aday kartlar + «hiçbiri» kapalı küme. Değer 3 · Zorluk M.
- **Eksik/zayıf:** CRM plan tarihleri tek güne yığılı (`production.py:9-12`); gerçekleşen için Logo emrinin %45'inde CRM no yok.

---

## Kişiler

### Kişiler (`/kisiler?rol=yazar|cevirmen|cizer`; `/yazarlar`, `/cevirmenler`, `/cizer-freelancer` yönlendirme)
- **Ne yapıyor:** Sekmeler «Yazarlar / Çevirmenler / Çizer ve serbest»; CRM eser katılımından kişi, eserleri, sözleşmeleri,
  projeleri; yazarda «İlişki» bölümü; çizer/çevirmende serbest çalışan kaydına geçiş (`modules.tsx:5-62`,
  `ContributorsScreen.tsx:14-62`).
- **Kim:** Editör, telif, koordinatör.
- **Bugün AI:** Yok (yazar kartındaki gelişim/öneri bölümü M7'den gelir).
- **Beklenti:** (1) kişinin tek paragraflık profili (kaç kitap, hangi türler, son iş); (2) mükerrer kişi kaydı uyarısı;
  (3) serbest metin katkı alanlarının (`new_tercumelertext`, `new_cizerlertext`) kişilere bağlanması.
- **Yapabileceklerimiz:**
  - **Mükerrer kişi ve serbest metin bağlama** — ad normalleştirme + belirsizde «aynı kişi mi» kapalı küme; sonuç «CRM'e
    işlenecek fark». Veri: CRM `ContactBase` (yalnız ad eşleşmesi için, ekranda maskesiz değil), `new_eserkatilimBase`.
    Değer 3 · Zorluk M · Koruma: kişisel veri modele yalnız ad düzeyinde ve yalnız eşleme için; CRM'e yazma yok.
  - **Profil paragrafı** — sayılar sorgudan, model yalnız cümle. Değer 2 · Zorluk S.
- **Eksik/zayıf:** Kapasite, puan, müsaitlik CRM'de yok (`ContributorsScreen.tsx:15-16`).

---

## M7 Yazar ilişkileri

### Yazar ilişkileri (`/yazar-iliskileri`)
- **Ne yapıyor:** Sekmeler «Isı haritası / Aday havuzu / Randevular» (`AuthorRelationsScreen.tsx:19-22`); yazar kartı,
  randevu ve görüşme notu (ton elle seçilir, `MeetingForm.tsx:30`), gelişim bölümü (satış, telif, okur sesi, sadakat),
  çapraz yazar önerisi (T-soft siparişlerinde birlikte alınma, kişisel veri okunmadan; `author_copurchase.py`),
  günlük iç hatırlatma e-postası (`author_reminders.py`).
- **Kim:** Yayın yönetmeni, editör, yazar ilişkileri sorumlusu.
- **Bugün AI:** Var — «ZEKİ AI önerisi»: `POST /api/v1/editorial/authors/advice/{id}` (`app.py:4864-4884`) → özet, en çok 4
  öneri, riskler JSON (`author_growth.py:450-461`); girdi ekran sayıları + gizli olmayan son görüşme notları, girdiyle
  saklanır (`author_growth.py:517-530`). Okur sesi özeti SEO modülünden.
- **Beklenti:** (1) görüşme sonrası notun özetlenmesi ve sıradaki adım önerisi; (2) yazarla ilgili son haberlerin karta
  düşmesi; (3) ilişkisi soğuyan yazarların uyarısı; (4) aday yazar için CRM/web geçmişi özeti.
- **Yapabileceklerimiz:**
  - **Öneriye sayı denetimi (düzeltme)** — bugün `make_advice` çıktısı `marketing/guard.py`'den geçmiyor (royalty
    yenilemesi geçiyor: `royalty_api.py:519`). Metindeki her sayı girdideki olgularla denetlenmeli. Değer 4 · Zorluk S
    (0,5 g) · Koruma: ilkenin kendisi.
  - **Görüşme notu → sıradaki adım + ton önerisi** — not kaydedilince kapalı küme ton (olumlu/nötr/olumsuz) ve bir
    «sıradaki adım» taslağı; kişi onaylar. Teknik: `QueuedLlm.choose` + taslak. Değer 3 · Zorluk S · Koruma: gizli not
    modele gitmez; ad/telefon maskelenir.
  - **Soğuma uyarısı** — ısı puanı düşüşü + yaklaşan sözleşme bitişi (M54 yenileme) birleşik iç uyarı. Teknik: kural.
    Değer 3 · Zorluk S.
- **Eksik/zayıf:** Öneri girdisine giden görüşme notlarında kişisel veri maskelemesi doğrulanmadı.

---

## Basın ve web

### Basın ve web (`/basin-web`)
- **Ne yapıyor:** Türk haber sitelerinin RSS akışları + Wikidata; CRM yazar adları başlık/özette aranır, eşleşen kayıt
  yerel modele «ilgili mi, tonu ne?» diye sorulur; yalnız olumlu/olumsuz/nötr görünür; kanal haritası
  (`web_watch.py:1-15`, `WebScreen.tsx:10-20`). Bayrak `webWatch`; müşteri VM'inde kapalı.
- **Kim:** Yayın yönetmeni, basın/halkla ilişkiler, yazar ilişkileri.
- **Bugün AI:** Var — `web_watch.ask` serbest metin cevap + kelime ayrıştırma (`web_watch.py:529-549`, `llm.chat`,
  `max_tokens=8`).
- **Beklenti:** (1) haftalık «yazarlarımız basında» özeti; (2) olumsuz haberin anında iç uyarısı; (3) ödül/etkinlik
  haberinin yazar kartına düşmesi.
- **Yapabileceklerimiz:**
  - **Kapalı küme + olasılığa geçiş** — `llm.chat` + kelime ayrıştırma yerine `QueuedLlm.choose` (ilgisiz/olumlu/olumsuz/
    nötr) ve düşük marjın «incelenecek» sayılması; isabet için kör etiket ekranı (H4 `Labeling` deseni). Değer 3 ·
    Zorluk S (1 g) · Koruma: haber metni kopyalanmaz (bugünkü kural).
  - **Haftalık özet** — ilgili haberler yazar başına 1 satır; iç e-posta. Değer 3 · Zorluk S.
  - **Olay türü etiketi** — ödül / etkinlik / röportaj / eleştiri kapalı küme → yazar kartı zaman çizgisi. Değer 2 · Zorluk S.
- **Eksik/zayıf:** Bot korumalı kaynaklar (1000Kitap, D&R…) taranmıyor — bilinçli (`web_watch.py:5-8`).

---

## M6 Sözleşmeler

### Sözleşmeler (`/telif-sozlesme`)
- **Ne yapıyor:** Sekmeler «CRM sözleşmeleri / Portal kayıtları» (`ContractsScreen.tsx:226-227`); CRM portföyü salt okunur,
  portal kaydı taslak→imza→yürürlük (`contracts.py:1-15`).
- **Kim:** Telif birimi, hukuk, yayın yönetmeni.
- **Bugün AI:** Yok.
- **Beklenti:** (1) serbest metinle arama («e-kitap hakkı olan 2020 öncesi çeviri sözleşmeleri»); (2) risk listesi
  (eksik taraf, eksik hak, süresi biten); (3) CRM'deki tutarsız kayıtların işaretlenmesi.
- **Yapabileceklerimiz:**
  - **Sözleşme sorgusu (sohbet)** — `telif` sohbet konusu var (`chat_topics.json`); portal tabloları (`semantic_contracts`)
    da katalogla bağlanırsa aynı hat. Değer 4 · Zorluk M · Koruma: yetki (`sayfa:telif-sozlesme`), sayılar SQL.
  - **Kayıt kalitesi kuralları** — taraf pay toplamı ≠ 100, hak bayrağı boş, bitiş < başlangıç; model yok. Değer 3 · Zorluk S.
- **Eksik/zayıf:** CRM telif kademesi tablosu hiçbir sözleşmeye bağlı değil (`editorial.py:6-9`) — kademe bilgisi portalda elle.

### Yeni sözleşme (`/telif-sozlesme/yeni`)
- **Ne yapıyor:** Şartlar formu + şablon; kayıt «Taslak», numara TS-<yıl>-<sıra> (`NewContract.tsx:12`, `contracts_terms.py`).
- **Kim:** Telif birimi, hukuk.
- **Bugün AI:** Yok.
- **Beklenti:** (1) imzalı/karşı taraftan gelen sözleşme belgesinden şartların doldurulması; (2) şartların standart
  pozisyondan sapmasının işaretlenmesi.
- **Yapabileceklerimiz:**
  - **Belgeden şart çıkarma** — yüklenen PDF/DOCX sözleşmeden `terms` alanları (oran, esas, kademe, avans, süre, hak
    bayrakları, para birimi); her değer metinde birebir alıntıyla, bulunmayan boş. Teknik: belge okuma + yapılandırılmış
    çıkarım + alıntı denetimi. Değer 5 · Zorluk L (4–5 g) · Koruma: kayıt insan onayıyla; sayı model üretimi değil
    metinden kopya; CRM'e yazma yok.
  - **Standart pozisyon sapması** — şablondaki varsayılanlarla fark listesi (kural) + model bir cümle risk notu.
    Değer 3 · Zorluk S.
- **Eksik/zayıf:** Portalda imzalı belge yükleme alanı yok (yalnız Word şablonu yükleme `contracts.py:1027`; doğrulanmadı: sözleşmeye ek dosya).

### Ödemeler (`/telif-sozlesme/odemeler`)
- **Ne yapıyor:** Bütün sözleşmelerin ödeme takvimi: vadesi gelen avans, tek ödeme, hakediş (`PaymentsScreen.tsx:11`).
- **Kim:** Telif birimi, muhasebe.
- **Bugün AI:** Yok.
- **Beklenti:** (1) Logo ödemesiyle mutabakat; (2) haftalık ödeme özeti.
- **Yapabileceklerimiz:**
  - **Logo ödeme mutabakatı** — yazar carisi `CLFLINE` + tutar ± 0,01 + tarih penceresi (M54 §13); model yok. Değer 4 ·
    Zorluk M (2–3 g) · Koruma: yalnız okuma; eşleşmeyen insana.
- **Eksik/zayıf:** Ödendi işareti elle.

### Şablonlar (`/telif-sozlesme/sablonlar`)
- **Ne yapıyor:** Metin ya da Word şablonu; `{{alan}}` yer tutucuları (`TemplatesScreen.tsx`, `contracts_docs.py:1-12`).
- **Kim:** Hukuk, telif.
- **Bugün AI:** Yok.
- **Beklenti:** (1) şablonda eksik yer tutucu / tanımsız alan uyarısı; (2) madde kütüphanesinden öneri.
- **Yapabileceklerimiz:**
  - **Yer tutucu denetimi** — kural (tanımsız alan, kullanılmayan zorunlu alan). Değer 2 · Zorluk S.
- **Eksik/zayıf:** Yok.

### Sözleşme ayrıntısı (`/telif-sozlesme/:key`)
- **Ne yapıyor:** Sekmeler «Şartlar / Metin / Zeyilnameler / Ödeme takvimi / Hakediş / Geçmiş» (`ContractDetail.tsx:334-339`);
  hakediş Logo satışından (`contracts_royalty.py:1-15`), dönem koşuları bağlantısı (`royalty/ContractRuns.tsx`).
- **Kim:** Telif birimi, hukuk, finans.
- **Bugün AI:** Yok.
- **Beklenti:** (1) zeyilname taslağı (şart değişikliğinden); (2) sözleşmenin tek paragraflık özeti; (3) hakediş
  açıklaması (hak sahibine).
- **Yapabileceklerimiz:**
  - **Zeyilname metni taslağı** — eski/yeni şart farkı (kural) → madde metni taslağı. Teknik: taslak. Değer 3 · Zorluk S ·
    Koruma: hukuk onayı, imza insanda.
  - **Sözleşme özeti** — şartlar sözlüğünden sade Türkçe özet; sayılar kopya + `guard.check`. Değer 3 · Zorluk S.
- **Eksik/zayıf:** Baskı adedi kaynakta yok; hakediş açılırken elle (`contracts_royalty.py:9-10`).

---

## M54 Telif dönemi ve haklar

### Telif dönemi (`/telif-donem`)
- **Ne yapıyor:** Sekmeler «Koşu / İstisnalar / Hak sahipleri / Ödeme listesi / Avans / Yenilemeler» (`RoyaltyScreen.tsx:92-97`);
  dönem koşusu M6 motoruyla, istisna, iki gözlü onay, birleşik beyanname, ödeme listesi CSV, avans portföyü, yenileme
  kararı (`royalty.py:1-15`).
- **Kim:** Telif birimi, muhasebe, yayın yönetmeni (yenileme).
- **Bugün AI:** Var — yenileme önerisi: kapalı küme karar + olasılık ve gerekçe, `guard.check` ile sayı denetimi
  (`royalty_api.py:493-523`, ekranda «Zeki AI önerisi» `Renewals.tsx:143`).
- **Beklenti:** (1) istisnaların gruplanıp açıklanması; (2) beyanname kapak e-postası taslağı; (3) avansın geri dönme
  ihtimali yorumu; (4) koşu özeti (yöneticiye).
- **Yapabileceklerimiz:**
  - **Beyanname kapak e-postası taslağı** — yazar adı, dönem, özet; sayılar beyannameden kopya (M54 §13). Teknik: taslak +
    `guard.check`. Değer 4 · Zorluk S (1 g) · Koruma: gönderim insanın kendi e-postasıyla (bugünkü kural), kişisel veri
    modele gitmez — ad yer tutucuyla, sonra doldurulur.
  - **Koşu özeti** — istisna dağılımı, toplam, önceki döneme fark; sayılar SQL. Değer 3 · Zorluk S.
  - **İstisna açıklaması** — istisna nedeni koddan; model yalnız «ne yapılmalı» cümlesi (şablon yetmezse). Değer 2 ·
    Zorluk S · Koruma: M54 §13 «deterministik olmalı» — önce şablon.
  - **Çeviri ücreti metnini yapılandırma** — `new_hesaplamatutari` («Sayfa başı 250 TL») → birim/tutar/para önerisi, insan
    onayı (M54 §13). Değer 3 · Zorluk S.
- **Eksik/zayıf:** CRM telif ödeme tablosu 2014'ten beri boş (`author_growth.py` notu); gerçek iz yalnız portal hakedişleri.

### Haklar ve lisanslar (`/haklar`)
- **Ne yapıyor:** Sekmeler «Hak kartı / Verilen lisanslar / Hak açıklamaları» (`RightsScreen.tsx:40-42`); hak açıklamaları
  «Zeki AI ile sınıfla», emin olunmayan «incelenecek», uzman onaylar (`RightsScreen.tsx:437-453`).
- **Kim:** Telif/yabancı haklar birimi.
- **Bugün AI:** Var — `POST /api/v1/rights/notes/classify` BATCH, 6 sınıf (bölge/format/süre/onay/ücret/diğer)
  `QueuedLlm.choose` + olasılık/marj (`royalty_api.py:703-725`, `royalty.py:288`, `:1784`).
- **Beklenti:** (1) serbest metinden yapılandırılmış hak haritası (hangi dil/ülke/format, ne zamana kadar); (2) yabancı hak
  satışı fırsatı gerekçesi; (3) lisans bitiş uyarısı.
- **Yapabileceklerimiz:**
  - **Yapılandırılmış hak haritası** — sınıftan öte: dil, ülke, format, bitiş tarihi alanları metinden birebir alıntıyla
    çıkarılır; hak kartına öneri. Teknik: yapılandırılmış çıkarım + alıntı denetimi. Değer 4 · Zorluk M (3 g) · Koruma:
    tarih/ülke metinde yoksa boş; onay uzmanda.
  - **Lisans fırsatı gerekçesi** — satış performansı + hak bitleri (`new_yurtdisitelifsatis`, `new_baskadilleretercume`)
    kuralı + gerekçe cümlesi (M54 §13). Değer 3 · Zorluk S.
- **Eksik/zayıf:** Sınıflama M36'daki ayrı sınıflamayla birleşik değil (bkz. M36).

---

## H1 Kategori ağacı

### Genel bakış (`/kategori-agaci`)
- **Ne yapıyor:** Kaynak okuma durumu, satış önceliği, bölümlere giriş (`CategoriesScreen.tsx:17-85`, `CategoriesHome.tsx`).
- **Kim:** Kategori/katalog sorumlusu, editör, e-ticaret.
- **Bugün AI:** Dolaylı (profil önerisi aşağıda).
- **Beklenti:** (1) ağacın kapsama durumu ve en çok satan profilsiz kitapların listesi; (2) doğal dil soru.
- **Yapabileceklerimiz:** H1 §13'teki «doğal dil soru» — ağaç tabloları sohbet kataloğuna. Değer 3 · Zorluk M.
- **Eksik/zayıf:** Yok.

### Profil kuyruğu (`/kategori-agaci/kuyruk`)
- **Ne yapıyor:** Profili bekleyen kitaplar satış önceliğiyle; toplu kabul (`ProfileQueue.tsx`, `Findings.tsx:112`).
- **Bugün AI:** Var — gece `run-due` profilsiz kitaplara öneri (`categories_api.py:214`, BATCH).
- **Beklenti/öneri:** **Toplu kabulde güven süzgeci** — yalnız olasılık+marj eşiği üstü öneriler toplu kabul edilir (kısmen
  var: «emin Zeki AI önerisi», `Findings.tsx:112`); isabet ölçümü (kör etiket örneklemi). Değer 3 · Zorluk S.
- **Eksik/zayıf:** Öneri isabetini ölçen kör etiket ekranı yok (H4'te var).

### Ağaç düzenleyici (`/kategori-agaci/agac`)
- **Ne yapıyor:** Sürümlü ağaç taslağı → onay → yürürlük; eşlemeler; «veriden taslak ağaç» (`TreeEditor.tsx:144-228`).
- **Bugün AI:** **Yok** — `suggest_draft` modelsiz (`categories.py:760-764`) ama ekranda ve notta «Zeki AI önerisi (veriden)»
  yazıyor (`categories.py:854`, `categories_api.py:375`, `TreeEditor.tsx:144`). Yanıltıcı etiket.
- **Beklenti:** (1) düğüm adlandırma önerisi; (2) çok kalabalık düğümün alt kırılım önerisi.
- **Yapabileceklerimiz:** **Alt kırılım önerisi** — kalabalık düğümdeki kitapların tema/tür kümelenmesi (gömme kümeleme) +
  küme adı önerisi (H1 §13 değil; `cluster_name.md` istemi motorda var). Değer 3 · Zorluk M · Koruma: taslak, onay insanda.
  Etiket düzeltmesi: «veriden taslak» (Zeki AI değil). Değer 2 · Zorluk S.
- **Eksik/zayıf:** Etiket.

### Tutarsızlıklar (`/kategori-agaci/tutarsizlik`)
- **Ne yapıyor:** Deterministik kurallar, açılıp kapanır (`categories.py:25`, `Findings.tsx`).
- **Bugün AI:** Yok.
- **Yapabileceklerimiz:** **Özet–kategori çelişkisi** — kuralın göremediği anlam farkı için «uyumlu/çelişkili/belirsiz»
  kapalı küme (H1 §13). Değer 3 · Zorluk S (1 g) · Koruma: yalnız bulgu, karar insanda.

### CRM'e işlenecek fark (`/kategori-agaci/crm-farki`)
- **Ne yapıyor:** Onaylı profil ile CRM bugünkü değer farkı; CRM'e insan işler (`CrmDiff.tsx`, `categories.py:5-10`).
- **Bugün AI:** Yok. **Beklenti/öneri:** Yok — bilinçli insan işi; yalnız CSV/iş listesi. Değer —.

### Etiket sözlüğü (`/kategori-agaci/etiketler`)
- **Ne yapıyor:** Yeni etiket önerileri onay/ret/birleştirme; Zeki AI sözlük dışı etiket üretmez (`TagsTab.tsx:11`).
- **Bugün AI:** Var (dolaylı) — profil önerisinde tema/etiket evet/hayır (`categories_propose.py:13`).
- **Yapabileceklerimiz:** **Eş anlamlı etiket birleştirme önerisi** — gömme benzerliğiyle yakın etiket çiftleri, insan
  birleştirir. Değer 2 · Zorluk S.

### Kitap profili (`/kategori-agaci/kitap/:id`)
- **Ne yapıyor:** Solda CRM'deki bugünkü sınıflamalar ve site kategorisi, sağda alan alan öneri ve karar
  (`BookProfile.tsx:15-96`).
- **Kim:** Kitabın editörü, yayın yönetmeni.
- **Bugün AI:** Var — «Zeki AI önerisi üret»: beyan varsa beyan, yoksa ağaçta düzey düzey kapalı küme seçim (`categories_propose.py:1-15`,
  `categories_api.py:463-475`).
- **Beklenti:** (1) önerinin gerekçesi (hangi metin parçası); (2) okunmuş kitapta motorun türü/temaları.
- **Yapabileceklerimiz:** **Motor bulgularını girdi yapma** — okunmuş kitapta `book_type` ve tema çıkarımı profil önerisine
  ek kanıt (H1 §13 «Karakter, ritim: motorun kaydı okunur»). Değer 3 · Zorluk M.
- **Eksik/zayıf:** Yok.

---

## H4 Kurumsal e-posta

### Gelen kutusu (`/kurumsal-eposta`)
- **Ne yapıyor:** Görünümler «Bana atanan / Süresi aşan / Atanmamış / Birimim …» (`MailboxHome.tsx:13-71`); 5 dakikada bir
  Gmail API (salt okuma) → CRM gönderen tanıma → Zeki AI tür/öncelik → yönlendirme tablosu → insan atar; gövde saklanmaz
  (`mailbox.py:1-20`, `mailbox_sources.py`).
- **Kim:** Genel kutu sorumlusu, birim yöneticileri, müşteri hizmetleri.
- **Bugün AI:** Var — tür ve öncelik `QueuedLlm.choose` (`mailbox_classify.py:120-177`), özet (`:189`).
- **Beklenti:** (1) doğru birime ilk seferde atama; (2) SLA riskinin önceden görülmesi; (3) aynı konudaki iletilerin gruplanması.
- **Yapabileceklerimiz:**
  - **Konu kümeleme** — son 7 gün iletilerinde benzer konu kümeleri («kargo gecikmesi» dalgası) gömme ile; birim
    yöneticisine iç özet. Değer 3 · Zorluk M · Koruma: gövde saklanmaz → yalnız özet/konu üzerinden.
  - **Otomatik atama açılışı** — kör etiket doğruluğu %90'ı geçen türde (bugünkü kural) yönetim açar; teknik hazır.
- **Eksik/zayıf:** Otomatik atama varsayılan boş (`mailbox.py:4-6`) — doğruluk ölçümü bekleniyor.

### İleti (`/kurumsal-eposta/ileti/:id`)
- **Ne yapıyor:** Gövde kutudan anlık; tür/sorumlu düzeltme, atama, durum, Zeki AI özeti, yanıt taslağı, başvuru aktarımı
  (M1'e) (`MessageDetail.tsx:23-388`).
- **Bugün AI:** Var — yanıt taslağı (rakam geçen satır atılır, söz/tarih yalnız şablondan; `mailbox_classify.py:242`),
  başvuru alanı çıkarma (metinde birebir; `:209`).
- **Beklenti:** (1) sipariş/bayi bağlamının iletinin yanında (açık bakiye, sipariş durumu); (2) yabancı dilde iletinin çevirisi.
- **Yapabileceklerimiz:**
  - **Bağlam kartı** — metinden sipariş no (desen), CRM sipariş/cari durumu SQL'den (H4 §13). Değer 4 · Zorluk M ·
    Koruma: yalnız yetkili rolde; sayılar SQL.
  - **Ek belge okuma** — dosya başvurusu ekindeki PDF/DOCX'in M1 ön okumasına bağlanması. Değer 3 · Zorluk S (M1 ön okumasıyla).
- **Eksik/zayıf:** Yok.

### Rapor (`/kurumsal-eposta/rapor`)
- **Ne yapıyor:** Hacim, ilk yanıt ve kapanış süresi (iş saatiyle), SLA uyumu, kişi/birim dağılımı (`MailReport.tsx:11`).
- **Bugün AI:** Yok.
- **Yapabileceklerimiz:** **Haftalık rapor yorumu** (H4 §13) — sayılar SQL, 3 cümle, `guard.check`. Değer 2 · Zorluk S.

### Kurallar (`/kurumsal-eposta/kurallar`)
- **Ne yapıyor:** Tür listesi (Zeki AI yalnız bundan seçer), yönlendirme, SLA, yanıt şablonları; taslak → onay
  (`MailRules.tsx:15-279`).
- **Bugün AI:** Yok (tür açıklaması modele girdi).
- **Yapabileceklerimiz:** **Tür açıklaması iyileştirme önerisi** — kör etikette sık karışan iki türün ayırt edici açıklama
  taslağı. Değer 2 · Zorluk S · Koruma: taslak, onay akışı.

### Etiketleme (`/kurumsal-eposta/etiketleme`)
- **Ne yapıyor:** Kör etiketleme; «Zeki AI doğruluğu» = insan etiketi ↔ modelin ilk seçimi, hedef %90 (`Labeling.tsx:11-43`).
- **Bugün AI:** Ölçüm ekranı. **Yapabileceklerimiz:** Bu deseni bütün kapalı küme önerilerine genelleştirmek (ortak altyapı).
- **Eksik/zayıf:** Yok — grubun en iyi ölçüm örneği.

---

## Editör motoru (`apps/editor`, Hermes Book Director)

- **Ne yapıyor:** Kanıta bağlı kitap analizi; ayrı yığın (TT GPU `/data/editor`): Hermes ajanı + 17 kitap skill'i
  (`hermes/skills/book/*`), MCP araçları (belge, görüntü, bilgi, arama, kalite, iş), model geçidi (ihtiyaçta aç/kapat),
  Temporal 15 adımlı iş akışı, Postgres kanıt defteri, Qdrant (`apps/editor/README.md:6-18`). Köprüye kart servisi ve
  OpenAI uyumlu API ile bağlanır (`editorial_cards.py`, `editorial_books.py:1-10`).
- **Bugün AI (portalda görünen):** kitaba soru, tür belirleme (`book_type.py`), editöre soru kuyruğu (`review.py` →
  `ReviewPanel`), 19 son okuma denetimi, belge incelemesi (`document_review.py`), stüdyo üretimi (M13/M14). İstem dosyaları
  `src/editor/prompts/*.md` (45 istem: özet, karakter, olay, tema, çelişki, OCR, sahne, profil, pazarlama…).
- **Ana kurallar (doğrulandı):** «Kitaba özel geliştirme yok», «veriye elle müdahale yok» (`docs/UYGULAMA-NOTLARI.md:6-9`);
  tek görsel okuma gürültü → oylama (`:64`).
- **Kitap türleri analizi (`docs/TUM-KITAP-TURLERI-ANALIZ.md`, 09-24):** tür körlüğü (kurgu dışı kitapta künye kadrosu
  «karakter» oluyor), uzunluk (tüm-kitap çağrıları 131k bağlamı aşıyor, 120 öğe sessiz kırpma `schemas.py:12`), 22 Eylül'den
  beri regresyon kapısı. Önerilen yapı: tür eksenleri (kurgu / gerçek kişi anlatısı / fikir-rehber / etkinlik / şiir) +
  resim + okur; token bütçesi ve pencereleme; kurgu dışı için bölüm ana fikri, kavram, atıf çıktıları (aşama 3, «ürün kararı
  sonrası»). `book_type.py` aşama 1'in tür kısmını uyguluyor; pencereleme ve aşama 3'ün durumu **doğrulanmadı**.
- **Kullanıcının (editör, yayın yönetmeni) motor beklentisi:** her türde kitap biter; kurgu dışında bölüm özeti ve kavram
  listesi; uzun kitap da okunur; bulgu isabeti görünür.
- **Yapabileceklerimiz (kitaptan bağımsız ilke korunarak):**
  - **Kurgu dışı çıktılar** — bölüm başına ana fikir (alıntılı), kavram/terim listesi, atıf/kaynak listesi, iddia–kaynak
    tutarlılığı. Veri: `ed.paragraph`, sayfa rolleri. Teknik: özet + çıkarım + alıntı denetimi. Değer 4 · Zorluk L (4–5 g) ·
    Koruma: tür ekseninden açılır, istemde kitap adı/örnek yok.
  - **Token bütçesi + pencereleme** (analiz §6.3) — uzun kitapların (tarih, roman) okunabilmesi; ön koşul. Değer 5 ·
    Zorluk L (2–3 g, belge tahmini) · Koruma: sınıra çarpan çıktı sayılır ve raporlanır.
  - **Başvuru ön okuması için hafif kip** — M1 dosyası için tam 15 adım yerine: metin, tür, yaş, özet, ilke riski (bkz. M1).
    Değer 5 · Zorluk M · Koruma: GPU sırası; editör analiziyle kuyruk paylaşımı.
  - **Denetim isabet ölçümünün tamamlanması** — tür test setindeki eksik türler (etkinlik, boyama, şiir, çizgi roman PDF'i)
    ile her denetimde en az bir etiketli koşu. Değer 4 · Zorluk M · Koruma: ölçülmeden «güvenilir» denmez.
- **Eksik/zayıf:** Son okuma README'sinde denetimlerin çoğu «ölçüm bekliyor»; tür analizi belgesi «kod yok» başlığıyla
  duruyor, uygulanma derecesi güncel belgelere işlenmemiş (doğrulanmadı).

---

## Grubun en değerli 10 AI önerisi

| # | Öneri | Ekran | Değer | Zorluk | Teknik | Not |
|---|---|---|---|---|---|---|
| 1 | Başvuru ön okuması + editör raporu taslağı | `/basvurular/:id` | 5 | L (5–6 g) | Motor belge okuma, kapalı küme, alıntılı özet | Puan/karar insanda; kişisel veri maskeli |
| 2 | Editoryal süreç sohbeti (başvuru, kurul, çeviri, görev, sözleşme portal tabloları) | `/editoryal` | 5 | M (3–4 g) | Mevcut NL→SQL + yeni sohbet konusu | Satır düzeyi yetki şart |
| 3 | Sözleşme belgesinden şart çıkarma | `/telif-sozlesme/yeni`, `/:key` | 5 | L (4–5 g) | Belge okuma + yapılandırılmış çıkarım + alıntı | Sayı metinden kopya, onay insanda |
| 4 | Motorda token bütçesi + pencereleme (uzun kitap) | `apps/editor` → `/son-okuma`, `/kitap/:id` | 5 | L (2–3 g) | Altyapı | Bütün kitap türleri için ön koşul |
| 5 | Yapılandırılmış hak haritası (dil/ülke/format/bitiş) + M36/M54 tek sınıflama | `/haklar`, `/dijital-yayin` | 4 | M (3 g) | Çıkarım + `choose` | Alıntısız alan boş |
| 6 | Beyanname kapak e-postası + koşu özeti | `/telif-donem` | 4 | S (1–2 g) | Taslak + `guard.check` | Gönderim insanda |
| 7 | Anlamsal benzer kitap (katalog örtüşmesi, Kitap 360, kurul) | `/basvurular/:id`, `/kitap/:id`, `/yayin-kurulu` | 4 | M (3 g) | Gömme/benzerlik | Rakam SQL'den |
| 8 | Son okuma isabet panosu + redaksiyonda aynı denetimler | `/son-okuma`, `/redaksiyon` | 4 | M (3 g) | Var olan denetim + kural | Tek yazım mekanizması |
| 9 | Resim–metin tutarlılık denetimi (oylamalı) | `/kitap-tasarim/:jobId/studyo` | 4 | M (3 g) | Görsel okuma + oylama | Onay insanda |
| 10 | Üretim dengeleme gerekçesi + matbaa şartname taslağı | `/uretim` | 4 | M (2–3 g) | Kural + taslak | CRM'e yazma yok |

Hızlı düzeltmeler (değer düşük değil, iş küçük): yazar önerisine `guard.check` (`author_growth.make_advice`, 0,5 g);
basın-web'de `llm.chat` → `QueuedLlm.choose` (1 g); kategori ağacında modelsiz taslağın «Zeki AI önerisi» etiketinin
düzeltilmesi (0,5 g); çeviri terim adayı çıkarımı (2–3 g, değer 4).

## Ortak altyapı ihtiyaçları

1. **Belge okuma servisi (tek yol):** PDF/DOCX/ODT metin + gerekirse OCR; bugün iki ayrı yol var (köprüde
   `editorial_desk` DOCX ayrıştırma, motorda `document.py`/`document_review.py`). Kullanan: M1 başvuru dosyası, M6 imzalı
   sözleşme, H4 ekler, M8 teslim, M3 metin, M36 platform raporları.
2. **Benzerlik araması (gömme + indeks):** motorda Qdrant var, köprüde yok. Kullanan: M1 katalog örtüşmesi, Kitap 360 benzer
   kitaplar, kurul geçmiş kararları, M2 konu uzmanlığı, H1 alt kırılım ve etiket birleştirme, kapak arşivi görsel arama,
   çeviri belleği, H4 konu kümeleme.
3. **Alıntı denetimi yardımcısı:** «her iddia metinde birebir» kuralı motorda ve birkaç köprü modülünde ayrı ayrı yazılmış
   (`editorial_desk`, `editorial_translation_qe`, `mailbox_classify`, `marketing.py`). Tek fonksiyon + test.
4. **Sayı denetimi (`marketing/guard.py`) zorunlu kapısı:** model metni üreten her uçta (yazar önerisi dahil) — bugün
   isteğe bağlı çağrılıyor.
5. **Kapalı küme + isabet ölçümü deseni:** `QueuedLlm.choose` var; eksik olan, her öneride kör etiket örneklemi ve
   denetim/sürüm başına isabet tablosu (H4 `Labeling` + son okuma `proof_decision` deseninin genelleştirilmesi). Kullanan:
   H1 profil, M54/M36 hak sınıfı, basın-web, M7 ton, M4 MQM kategorisi.
6. **Taslak → onay → insan gönderir akışı:** M1 yazıları, M54 beyanname e-postası, M6 zeyilname, M12 şartname, H4 yanıtı,
   M8 yazışma. Ortak «taslak» tablosu/bileşeni: kim üretti, kim onayladı, gönderildi işareti.
7. **Kişisel veri maskeleme (modele gitmeden):** `crm_people_rules.assert_no_personal` SQL tarafında; serbest metin
   (görüşme notu, e-posta gövdesi, başvuru özgeçmişi) için ad/telefon/e-posta maskeleyici gerekli.
8. **Editoryal veri alanı sohbete:** `chat_topics.json`'a editoryal süreç konusu ve `semantic_editorial_*`,
   `semantic_translation_*`, `semantic_contracts`, `semantic_production_*` tablolarının kataloğa girişi (yetki süzgeciyle).
9. **Motor kuyruğu paylaşımı:** başvuru ön okuması, son okuma, stüdyo üretimi aynı GPU'yu paylaşıyor; öncelik sınıfları
   (etkileşimli / gece) ve ekranda bekleme tahmini.
10. **Günlük iç özet (bildirim):** `author_reminders.py` deseni (kişi başına günde tek iç e-posta) Masam, M4 teslim riski,
    M12 gecikme, basın-web için tek mekanizmaya.
