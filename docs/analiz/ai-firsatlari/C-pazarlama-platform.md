# C — Pazarlama ve Platform: Zeki AI fırsatları (ekran ekran)

Kaynak: `ai-analiz-okuma` ağacı (main kopyası, son işlem `f26e11d6`), salt okuma. Tarih 2026-09-28.

**Kapsanan alanlar:** menü alanı «Pazarlama» (`navModel.ts:438-518`, 49 öğe) ve «Platform» (`navModel.ts:604-626`, 12 öğe); ayrıca kapsam gereği başka alanda duran M39 «Pazar ve rakip» (Analiz, 3 öğe, `navModel.ts:201-227`) ve M36 «Dijital yayın» (Editoryal, 2 öğe, `navModel.ts:309-310`).
**Sayılar (atlanan yok kanıtı):** 66 menü öğesi · `App.tsx`'te bu modüllere ait **137 rota** (`App.tsx:396-607`) · rotası olan her ekran ve sekme bu belgede ayrı `###` başlığıyla ya da ekranın altında adıyla ele alındı (157 `###` başlık; parametreli bölümler: `/okurlar/:section` 6 bölüm, `/eticaret-musteri/:section` 5 bölüm, `/pazar-arastirma/:section` 4 bölüm; sekmeler: plan 5, lansman 5, backlist 4, ay planı 4, içerik 3, set 4, fuar kartı 5, dijital katalog 4, kampanya 5 vb.). Rota listesi ile belge otomatik karşılaştırıldı: 137/137 rota ve 66/66 menü öğesi belgede geçiyor.
**Modüller:** M15, M16, M17, M18, M19, M53 · M20, M21, M22, M23, M24 · M25–M26 (SEO & GEO, 38 ekran) · M27, M28 · H2, H3, M37, M34, M35 · M36, M39 · M42, M40, M41.

**Genel bulgular (grup çapında):**
- Grup AI bakımından en olgun alan: 24 modülün hepsinde model kullanılıyor (yaklaşık **68 ayrı Zeki AI işlevi**, arka uçta 74 `chat`/`choose` çağrı noktası) ve hepsi LLM kapısından (`rt.llm_for(modül, öncelik)`) geçiyor; metin üretenlerin çoğu `marketing/guard.py` denetiminden (birebir alıntı, kaynaksız rakam, kanıtsız üstünlük iddiası, teknoloji adı) geçiyor. Sınıflama işleri `QueuedLlm.choose` + olasılık/marj + «Belirsiz» deseninde. Otomatik dış gönderim hiçbir modülde yok (PR e-postası onaylı satırdan, kişinin elinden tek tek: `pr_api.py:521`).
- En büyük boşluklar: (1) **benzerlik araması (gömme) hiç yok** — emsal, benzer kitap, arşiv, SSS, öğrenim araması hep kural/ortak sözcükle; (2) **tablo yorumu** bazı ekranlarda var, bazılarında yok (fuar sonucu, katalog raporu, SEO aylık raporu, Amazon özeti, kurumsal ilişkiler raporu, işbirliği raporu); (3) **okur sesi sınıflaması** (yorum, soru, iade, DM) parça parça — iade nedeni var (Trendyol), yorum/soru konusu yok; (4) **belge okuma** yalnız metin PDF'inde (M39), fiş/şartname/sözleşme maddesi okuma yok; (5) ekranlardaki «Zeki AI'a sor» kutusu genel soru kutusunu açıyor, **ekran bağlamını taşımıyor**.
- Tutarsızlıklar: M27 fuar kartındaki «Zeki AI önerisi» düğmesi model çağırmıyor, kuralla liste çıkarıyor (`FairBooks.tsx:11`, `events.py:864`); SEO «Yapay zekâ görünürlüğü» ekranı ölçülen dış motorların adlarını yazıyor (`SeoVisibility.tsx:45`) — «ekranda teknoloji adı yok» kuralı için karar gerekir; H3 ve M34'te iki ayrı «huni» ekranı var; M15–M17, M19–M24, M27, M28, M34–M37, M39, M42, M53, H2 ihtiyaç dosyalarının başında hâlâ «Durum: analiz (kod yok)» yazıyor, oysa kod var.
- Ölçek notu: değer 4–5/5 olan 20 öneri var; çoğu yeni model değil, var olan yapı taşlarının (choose, guard, tablo yorumu) başka ekranlara taşınması — S (1–2 gün) boyutunda.

## M15 Yeni kitap pazarlama planı

Menü: Pazarlama › Planlama › «Yeni kitap planı» (1 öğe, `also: /pazarlama/plan`) · Rotalar: 2 (`/pazarlama/yeni-kitap`, `/pazarlama/plan/:id`) + plan ekranında 5 sekme · Arka uç: `marketing/api.py`, `marketing/plans.py`, `marketing/core.py`, `marketing/guard.py`, `marketing/export.py` · İhtiyaç: `M15-yeni-kitap-pazarlama.md`.

### Yeni kitap planları listesi (`/pazarlama/yeni-kitap`)
- **Ne yapıyor:** Yayına hazırlanan kitapları (CRM yayın tarihi adayları) plan durumu, sorumlu, yayınevi süzgeciyle listeler; «Zeki AI taslağı hazırla» ile plan açılır (`MarketingHome.tsx`, `NewBooksList.tsx`; uç `plans.new_books` `plans.py:751`).
- **Kim:** Pazarlama müdürü (haftalık öncelik), kitap pazarlama sorumlusu (yayına kaç gün kaldı, planı eksik kitap).
- **Bugün AI:** Listede doğrudan model yok; «taslak hazırla» düğmesi plan ekranındaki işi başlatır. Günlük özet `plans.digest`/`digest_text` (`plans.py:861-880`) kuraldır, model değil.
- **Beklenti:** «Bu hafta planı eksik ve yayına 30 günden az kalan kitaplar hangileri?» diye sormak; önceliklendirme (hangi kitaba önce plan); listeye toplu «taslak hazırla»; yayın tarihi üç kaynakta çelişiyorsa uyarı.
- **Yapabileceklerimiz:**
  - **Plan önceliği sırası + tek cümle gerekçe** · CRM yayın tarihi, M46 hedef, yazar geçmişi (plan karnesi) · kural puanı (hedef × gün kalan) + model yalnız gerekçe cümlesi, `marketing.guard` · 3/5 · S (~1 gün) · rakam SQL'den, cümle guard'dan geçer.
  - **Toplu taslak (gece BATCH)** · seçili kitaplar için `run_job` sıraya · `llm_for("marketing", BATCH)` · 3/5 · S (~1 gün) · GPU kuyruğu; ekranda iş durumu.
  - **Yayın tarihi çelişkisi özeti** · proje/kitap/üretim tarihleri (`resolve_pub` `plans.py:123`) · kural; model gerekmez · 2/5 · S.
- **Eksik:** Liste ekranında «Zeki AI'a sor» kutusu yok (plan ekranında var).

### Plan ekranı (`/pazarlama/plan/:id`) — sekmeler Karne · Kanal ve bütçe · Takvim · Materyaller · Onay ve geçmiş
- **Ne yapıyor:** Kitap karnesi (yazar geçmişi, emsal ilk 3/6/12 ay satışı, özel günler, hedef), kural+emsal oranıyla kanal/bütçe önerisi, takvim, 8 tür materyal (föy, arka kapak, basın bülteni, sosyal, e-bülten konu, video senaryosu, kapak brief'i, influencer brief'i — `core.py:174`), onay/geçmiş (`PlanScreen.tsx:19-26`).
- **Kim:** Kitap pazarlama sorumlusu (taslak), pazarlama müdürü (onay, bütçe), editör (materyalin editoryal onayı).
- **Bugün AI:** Var. `api.py:264-300` iş: emsal kontrolü `QueuedLlm.choose` («Evet, emsal/Hayır/Belirsiz», `plans.py:720-735`), kanal gerekçesi `explain_channels` (`plans.py:699`), hedef okur ve konumlama `positioning` (`plans.py:713`), materyal taslakları `draft_material` (`plans.py:690`); hepsi `guard.py` (birebir alıntı, rakam, kanıtsız iddia, teknoloji adı) denetiminden geçer, düşen cümle sayısı ekranda. Sağ sütunda «Zeki AI'a sor» genel soru kutusuna açılır (`PlanScreen.tsx:246`).
- **Beklenti:** Emsal girilmemişse aday emsal bulunması; rakip kitaplardan «fark» maddeleri; hedef değişince bütçe revizyonu seçenekleri; materyal taslağının tek tıkla yeniden yazımı («daha kısa», «gençlik diliyle»); «bu plandaki bütçe emsallerde hedefin yüzde kaçıydı?».
- **Yapabileceklerimiz:**
  - **Emsal adayı bulma (emsal yoksa)** · CRM `new_new_kitap_new_emsalkitap3Base` boşsa aynı kitaplık/hedef kitle/tür/fiyat bandı adayları · kural aday + gömme benzerliği (CRM `new_ozet`) + `choose` evet/hayır · 5/5 · M (~3 gün) · düşük marj «Belirsiz», insan onayı; ihtiyaç §13 bunu açıkça istiyor, kodda yalnız girilmiş emsal denetleniyor (doğrulanmadı: aday üretimi kodda bulunamadı).
  - **Rakip kitap fark maddeleri** · CRM `new_rakipkitapBase` tanıtım metinleri · özet/taslak, alıntı guard · 3/5 · S (~1–2 gün) · rakip metni yalnız karşılaştırma için, dışarı çıkmaz.
  - **Hedef değişince bütçe revizyonu iki seçenek** · `target_changed` (`plans.py:208`) + bütçe çerçevesi · kural iki seçeneği hesaplar, model gerekçe yazar · 4/5 · S (~2 gün) · karar insanda (K3).
  - **Materyal yeniden yazım komutları** (kısalt, ton değiştir, platforma uyarla) · mevcut materyal + kaynak metin · sohbet taslağı + guard · 3/5 · S · her sürüm geçmişe.
  - **Plan içi soru** («emsalde basın payı neydi?») plan bağlamı sohbet hattına aktarılır · `/api/v1/ask` + plan kimliği · 3/5 · M · sayı katalogdan.
- **Eksik:** Materyal onay oranı / Zeki önerisiyle örtüşme ölçümü (ihtiyaç §başarı ölçütü) ekranda yok (doğrulanmadı).

## M16 Lansman ve yayın ayı

Menü: Pazarlama › Planlama › «Lansman» (1 öğe) · Rotalar: 2 (`/pazarlama/lansman`, `/pazarlama/lansman/:id`) + 5 sekme · Arka uç: `marketing/launch.py`, `launch_api.py`, `launch_track.py`, `launch_report.py`, `launch_sources.py` · İhtiyaç: `M16-lansman-yayin-ayi.md`.

### Lansmanlar (`/pazarlama/lansman`)
- **Ne yapıyor:** Bu hafta + 4 hafta lansman şeridi; bütün lansmanların bugün yapılacak ve geciken maddeleri (`LaunchHome.tsx:12`).
- **Kim:** Pazarlama müdürü, lansman sorumlusu (sabah iş listesi), satış müdürü (rafa ulaşma).
- **Bugün AI:** Yok (günlük özet `launch_report.digest_text` kuraldır, `launch_report.py:230`).
- **Beklenti:** «Bu hafta riskli lansman hangisi?» tek satır; geciken maddelerin kime ait olduğuna göre sabah özeti; ilk 3 gün sipariş/hedef sapmasının öne çıkması.
- **Yapabileceklerimiz:**
  - **Lansman risk bayrağı + gerekçe cümlesi** · `launch_days` (sipariş/fatura/stok), hedef günlük payı `daily_target` (`launch.py:232`), emsal günleri · kural eşik (stok < bekleyen, sipariş < emsal %X) + model tek cümle · 4/5 · S (~2 gün) · rakam tablodan, guard.
  - **Sabah özeti (kişiye göre)** · `today_tasks` (`launch.py:385`) · şablon + kısa özet · 2/5 · S · bildirim içinde, dış gönderim yok.
- **Eksik:** —

### Lansman ekranı (`/pazarlama/lansman/:id`)
- **Kontrol listesi** — planın takvimi + lansman maddeleri; gönderi günü maddesinde onaylı metin kopyalanır, portal göndermez (`ChecklistTab.tsx:10`). AI: yok. Beklenti: eksik madde önerisi (türüne göre), kanıt bağlantısı kontrolü. Öneri: **kitap türüne göre eksik madde önerisi** · geçmiş lansmanların madde listeleri · benzer lansman (tür/kitaplık) + `choose` «bu madde gerekli mi» · 2/5 · S.
- **İzleme** — birikimli sipariş (CRM), faturalı satış (Logo), hedef payı, emsal ortalaması; rafa ulaşma kutuları (`TrackingTab.tsx:9`). AI: yok. Beklenti: «ilk haftası emsale göre iyi mi?», stok tükenme uyarısı, «hangi bayiler dağılım almadı?». Öneri: **erken satış tahmini (D+30 ve D+90)** · lansman günlük seri + emsal eğrileri · zaman serisi tahmini (sunucudaki tahmin servisi) + emsal ölçekleme; model metin değil · 4/5 · M (~4 gün) · tahmin aralığı gösterilir, «tahmin» etiketli; **dağılım almayan bayi listesi** kural (M29 dağılım) · 3/5 · S.
- **Etkinlikler** — CRM etkinlikleri + portalda girilen sonuç, yalnız sayı (`EventsTab.tsx:11`). AI: yok. Öneri: **davet/teşekkür metni taslağı** · etkinlik kaydı + kitap metni · taslak + guard · 2/5 · S · gönderim yok, kopyala. (İhtiyaç §13 «Basın lansmanı/etkinlik davet metni» — kodda bulunamadı.)
- **Medya** — basın ve web taraması kayıtları (açık ortamda) + elle kayıt, ton (`MediaTab.tsx:10`). AI: tarama tarafında ton etiketi var (web_watch; bu ekran yalnız okur). Öneri: **elle girilen yansıma için ton ve özet** · başlık+bağlantı metni · `choose` olumlu/olumsuz/nötr + 1 cümle özet · 2/5 · S.
- **Değerlendirme** — D+7/D+30 rakam tablosu SQL'den; Zeki AI 2 paragraf özet + ≤3 öneri, tabloda olmayan rakam düşer (`ReviewTab.tsx:11`, `launch_api.py:338-356`, `launch_report.py:126-135`). Beklenti: «neden hedefin altında kaldı?» sorusu için kanal kırılımına dayalı açıklama. Öneri: **sapma nedeni aday listesi** · kanal/bölge kırılımı (Logo) + etkinlik/medya sayıları · kural (en büyük sapma katkısı) + model açıklar · 3/5 · M (~3 gün).
- **Kim:** Lansman sorumlusu, pazarlama müdürü (karar: bütçe artır/kes), satış.
- **Eksik:** Ön sipariş kaynağı (B2B/pazar yeri) ihtiyaçta açık soru; ekranda kanal ayrımı doğrulanmadı.

## M17 Backlist pazarlama

Menü: Pazarlama › Planlama › «Backlist» (1 öğe) · Rota: 1 (`/pazarlama/backlist?sekme=firsatlar|gundem|aktivasyonlar|etki`) · Arka uç: `marketing/backlist.py`, `backlist_api.py`, `backlist_sql.py` · İhtiyaç: `M17-backlist-pazarlama.md`.

### Backlist › Fırsatlar (`/pazarlama/backlist?sekme=firsatlar`)
- **Ne yapıyor:** Bütün backlist «uyku endeksi» ile sıralı (bileşen çubukları, kişisel ağırlık kaydırıcıları), seçip aktivasyon planı açılır (`OpportunitiesTab.tsx:14`).
- **Kim:** Pazarlama müdürü, backlist/ürün sorumlusu.
- **Bugün AI:** Yok (endeks kural; `backlist.py:1`).
- **Beklenti:** «Satışı en çok düşen ama stoku 6 aydan fazla yeten çocuk kitapları?»; neden bu kitap üstte (tek cümle); e-kitap hakkı olup e-kitabı olmayanlar.
- **Yapabileceklerimiz:**
  - **Satır gerekçesi** («stok 14 ay, 12 ayda −%40, yazarın yeni kitabı kasımda») · endeks bileşenleri · şablon + model sadeleştirme, rakam guard · 3/5 · S (~1 gün).
  - **Canlanma tahmini** (kampanya olursa beklenen artış) · `EffectsTab` geçmiş kampanya önce/sonra verisi + benzer kitap · kural+model (benzer kitap ortalaması; model rakam üretmez) · 3/5 · M (~4 gün) · «nedensellik değil» uyarısı.
- **Eksik:** —

### Backlist › Gündem (`?sekme=gundem`)
- **Ne yapıyor:** Önümüzdeki haftaların özel günleri, bağlı kitaplar, yazarı yeni kitap çıkaran backlist, Zeki AI konu eşleşmeleri (onaylı) (`AgendaTab.tsx:12`).
- **Bugün AI:** Var. Özel gün ↔ kitap konusu kapalı küme `llm.choose(q, TOPIC_CHOICES)` + olasılık/marj, düşük güven «Belirsiz» (`backlist.py:1086`, gece `backlist_api.py:410` BATCH).
- **Beklenti:** Arama gündemi (SEO sezon takvimi) ve haber gündemiyle eşleşme; «bu gün için 5 kitaplık liste».
- **Yapabileceklerimiz:** **Gündem kaynağını genişletme** · SEO `seasons.py` arama artışı + basın/web gündemi · aynı `choose` hattı · 4/5 · S (~2 gün) · aday çiftler kuraldan, sayı tavanı yok. **Özel gün başına hazır kitap listesi** · onaylı eşleşmeler + stok · kural · 3/5 · S.

### Backlist › Aktivasyonlar (`?sekme=aktivasyonlar`)
- **Ne yapıyor:** Açılmış backlist planları; plan ekranı çekirdeği (kanal/bütçe, takvim, materyal, onay); «CRM'e işlenecek kampanya» kopyalanır (`ActivationsTab.tsx:12`).
- **Bugün AI:** Var. Materyal taslakları: «Neden şimdi oku» gönderileri, e-bülten bölümü, okul/kütüphane toplu alım mektubu (`backlist.py:173-176`, `draft` `backlist.py:1269`, iş `backlist_api.py:280`), guard'dan geçer.
- **Beklenti:** Kanal önerisinin gerekçesi; kütüphane teklif mektubunu hedef kuruma göre uyarlama.
- **Yapabileceklerimiz:** **Aktivasyon kanal gerekçesi** (M15 `explain_channels` yeniden kullanımı) · 3/5 · S (~1 gün). **Kurum tipine göre mektup varyantı** (okul/belediye kütüphanesi/kurumsal) · M31/M33 kurum türleri · taslak + guard · 2/5 · S · gönderim yok.

### Backlist › Etki (`?sekme=etki`)
- **Ne yapıyor:** CRM kampanyalarında ürünlerin kampanya öncesi 3 ay / kampanya / sonraki 2 ay Logo net adedi (`EffectsTab.tsx:9`).
- **Bugün AI:** Yok.
- **Beklenti:** «Geçen yılki okul kampanyası işe yaradı mı?» sorusuna tek paragraf; hangi kampanya türünün tuttuğu.
- **Yapabileceklerimiz:** **Kampanya etkisi yorumu** · etki tablosu · model tablo okur, ≤3 öneri, rakam guard (launch_report deseni) · 3/5 · S (~1 gün). **Kampanya türü sınıflama** · CRM kampanya adı/açıklaması · `choose` (M35 `CRM_TYPE_PROMPT` yeniden kullanım `kampanya.py:1750`) · 2/5 · S.
- **Eksik:** Kontrol grubu yok; «öncesi/sonrası» doğru etiketli.

## M18 Aylık pazarlama planı ve satış föyleri

Menü: Pazarlama › Planlama › «Aylık plan», «Satış föyleri» (2 öğe) · Rotalar: 4 (`/pazarlama/aylik-plan`, `/pazarlama/aylik-plan/:ay`, `/pazarlama/foy`, `/pazarlama/foy/:stok`) + ay ekranında 4 sekme · Arka uç: `marketing/monthly.py`, `monthly_api.py`, `foy.py`, `foy_pdf.py` · İhtiyaç: `M18-aylik-pazarlama-plani.md`.

### Aylık plan (`/pazarlama/aylik-plan[/:ay]`) — sekmeler Takvim · Bütçe ve öncelik · Föyler · Özet
- **Ne yapıyor:** Önceki ay şeridi; hafta × kanal takvimi ve çakışmalar; bütçe dağılımı önerisi; ayın föyleri; genel müdür özeti (`MonthScreen.tsx:19-26`).
- **Kim:** Pazarlama müdürü (ay planını kesinleştirir), genel müdür (özet okur), kanal sorumluları.
- **Bugün AI:** Var. Bütçe dağılımı gerekçesi + genel müdür özeti `monthly.explain` (`monthly.py:986-1001`, `monthly_api.py:244`, `516`); ayın 15'i otomatik taslak BATCH (`monthly_api.py:566`); rakamlar tablodan, denetimden geçmeyen cümle düşer (`MonthScreen.tsx:187`).
- **Beklenti:** Çakışma için çözüm önerisi (hangi lansmanı kaydır); hedefin %80 altında kalan kitaplar için bu ay ne planlandı; geçen ay planlanan işlerin yapılma oranı; özetin sunum/PDF'i.
- **Yapabileceklerimiz:**
  - **Çakışma çözüm önerisi** · takvim kalemleri + öncelik puanı · kural (en düşük öncelikliyi kaydır) + model gerekçe · 3/5 · S (~2 gün) · karar insanda.
  - **Hedef açığı ↔ plan boşluğu eşleşmesi** · M46 sapma + ay kalemleri · kural liste + model tek paragraf · 4/5 · S (~2 gün).
  - **Ay kapanış karşılaştırması** (planlanan vs yapılan) · M16/M22/M21 tamamlanma kayıtları · kural + özet · 3/5 · M (~3 gün).
- **Eksik:** —

### Satış föyleri listesi (`/pazarlama/foy`)
- **Ne yapıyor:** Ayın yeni kitaplarının föyleri, eksik alan ve CRM uyumsuzluğu, aylık paket (`FoyList.tsx:16`).
- **Kim:** Pazarlama (föy hazırlığı), saha satış temsilcisi (telefonda föy açar).
- **Bugün AI:** Listede yok (föy denetimi kural; tekil föyde argüman taslağı var).
- **Beklenti:** Eksik argümanları toplu yazdırma; «fiyatı CRM'le uyuşmayan föy var mı?» sorusu.
- **Yapabileceklerimiz:** **Toplu argüman taslağı** (eksik olan föyler için gece) · `foy.draft_args` · BATCH · 3/5 · S (~1 gün). **Temsilci için sesli/tek ekran «bu kitabı nasıl anlatırım» özeti** (telefon) · föy alanları · kısa taslak + guard · 3/5 · S.

### Tek föy (`/pazarlama/foy/:stok`)
- **Ne yapıyor:** Önizleme + Paylaş/PDF, alanlar ve kaynakları, onay; «CRM'e işlenecek» listesi (portal CRM'e yazmaz) (`FoyScreen.tsx:14`, `218`).
- **Bugün AI:** Var. CRM «Bu Kitap Neden Önemli?» boşsa 3 satış argümanı taslağı `foy.draft_args` (`foy.py:577-593`), guard.
- **Beklenti:** Bayi/kanal tipine göre farklı vurgu (okul, kitapçı, zincir); itiraz cevapları («fiyat yüksek»).
- **Yapabileceklerimiz:** **Kanal tipine göre argüman varyantı** · föy + kanal tipi · taslak + guard · 3/5 · S. **Satış itirazı cevap kartı** · föy + emsal rakamı (SQL) · taslak · 2/5 · S · kanıtsız üstünlük iddiası guard.
- **Eksik:** —

## M19 Pazarlama görsel ve metin

Menü: Pazarlama › Üretim › «Görsel ve metin» (1 öğe) · Rotalar: 2 (`/pazarlama/icerik`, `/pazarlama/icerik/:id`) + ana ekranda 3 sekme · Arka uç: `marketing_creative.py`, `marketing_creative_api.py`, `marketing_creative_sources.py`; görsel dizimi editör stüdyosunun pazarlama kiti (`editorial_studio_marketing.py`) · İhtiyaç: `M19-pazarlama-gorsel-icerik.md`.

### Görsel ve metin › Talepler (`/pazarlama/icerik?sekme=talepler`)
- **Ne yapıyor:** Talep panosu (elle ya da M15 plan materyalinden), durumlar (üretim → tasarım onayı → mesaj onayı → arşiv) (`CreativeHome.tsx:16-22`, uç `from-material` `marketing_creative_api.py:298`).
- **Kim:** Pazarlama sorumlusu (talep), grafik/içerik ekibi (üretim), müdür (mesaj onayı).
- **Bugün AI:** Panoda yok; üretim talep ekranında.
- **Beklenti:** Talep formunu serbest cümleden doldurma («öğretmenler günü için 5 kitaplık Instagram karuseli»); benzer eski talebi önerme.
- **Yapabileceklerimiz:** **Serbest metinden talep formu** · talep şeması (biçim, kitap, tarih) · kapalı seçimlerle alan doldurma (`choose` biçim/kanal) + kitap araması · 3/5 · S (~2 gün). **Benzer onaylı varlık önerisi** · arşiv metinleri · gömme benzerliği · 3/5 · M (~3 gün, gömme altyapısıyla).

### Görsel ve metin › Arşiv (`?sekme=arsiv`)
- **Ne yapıyor:** Onaylı varlık arşivi, sürümler, kullanıldı işareti (`AssetLibrary.tsx`, uç `/assets` `:665-807`).
- **Bugün AI:** Yok.
- **Beklenti:** «Geçen ay onaylanan görsellerden hangileri bu kitaba ait?»; serbest metinle arama («mavi, çocuk, yaz»).
- **Yapabileceklerimiz:** **Arşivde anlamsal arama** · varlık metinleri + etiketler (görsel içerik için görsel açıklama modeli, doğrulanmadı) · gömme araması · 3/5 · M (~3 gün) · yalnız portal verisi.

### Görsel ve metin › Marka kiti (`?sekme=marka`)
- **Ne yapıyor:** Renk, yazı tipi, logo, yasaklı kalıp listesi (`BrandKit.tsx`; yetki `icerik.marka`).
- **Bugün AI:** Yok (yasaklı kalıp `guard.CLAIMS` + yönetim ayarı).
- **Beklenti:** Yasaklı kalıp önerisi (geçmiş reddedilen metinlerden); marka sesi kuralları.
- **Yapabileceklerimiz:** **Reddedilen metinlerden kalıp adayı** · mesaj onayı ret notları · özet + insan onayı · 2/5 · S.

### Talep ekranı (`/pazarlama/icerik/:id`)
- **Ne yapıyor:** Solda brief ve kaynaklar, ortada görsel varyantlar (biçim × varyant; stüdyo diziyor), sağda metin varyantları; tasarım/mesaj onayı; zip paket (`RequestScreen.tsx:18`).
- **Bugün AI:** Var. Metin varyantları `llm.chat` temperature 0.7 (`marketing_creative_api.py:539-592`) — sayı/alıntı kaynakta aranır, sınırı aşan düşer; görsel başlıkları (`:619-634`); kanıtsız üstünlük iddiası `choose` evet/hayır + olasılık (`claim_check` `:128-133`, `:592`, `:844`). Görsel: stüdyo pazarlama kiti (dizim modelsiz); model ile görsel yalnız stüdyo kuralıyla «taslak».
- **Beklenti:** Platform sınırına uyan varyant (30 karakter başlık) — var; hashtag önerisi; video senaryosu sahne sahne; A/B için hangi varyantın tutacağına dair öneri; görselde metin okunurluğu denetimi.
- **Yapabileceklerimiz:**
  - **Varyant seçim önerisi** · M21/M22 geçmiş performans (tıklama, etkileşim) + varyant özellikleri · kural sıralama + model açıklama · 3/5 · M (~4 gün) · veri yoksa gösterilmez.
  - **Görsel okunurluk/kontrast denetimi** · dizilmiş görsel · kural (kontrast, yazı alanı) + görsel açıklama modeli (doğrulanmadı) · 2/5 · M.
  - **Brief'ten eksik bilgi soruları** · brief alanları · model «şu bilgi eksik» listesi · 2/5 · S.
- **Eksik:** — (görsel modelin ticari lisansı 2026-09-29'da alındı; taslak etiketi kaldırıldı).

## M53 Set, hediye ve promosyon

Menü: Pazarlama › Üretim › «Set ve hediye» (1 öğe) · Rotalar: 3 (`/pazarlama/set-hediye`, `/pazarlama/set-hediye/set/:id`, `/pazarlama/set-hediye/teklif/:id`) + ana ekranda 4 sekme · Arka uç: `sets.py`, `sets_api.py`, `sets_docs.py`, `sets_sources.py` · İhtiyaç: `M53-set-hediye-promosyon.md`.

### Set ve hediye › Setler (`/pazarlama/set-hediye?sekme=setler`)
- **Ne yapıyor:** Mevcut setler: satış, stok, marj (bileşen birim maliyeti M9'dan), durum (`SetsTab.tsx`, `sets.py:1-40`).
- **Kim:** Ürün/pazarlama müdürü, e-ticaret, kurumsal satış.
- **Bugün AI:** Yok (hesaplar kural).
- **Beklenti:** «Son 12 ayda en çok satan setler ve marjları?»; set satışa girdikten sonra bileşen tekil satışı düştü mü (yamyamlık).
- **Yapabileceklerimiz:** **Yamyamlık analizi yorumu** · set + bileşen Logo satışı önce/sonra · kural hesap + model yorum, guard · 3/5 · M (~3 gün). **Sezon sonu analizi** (ihtiyaç §13: tabloyu yorumla, ≤3 öneri) · sezon set satışı · launch_report deseni · 3/5 · S (~1 gün) · kodda bulunamadı.

### Set ve hediye › Öneriler (`?sekme=oneriler`)
- **Ne yapıyor:** Birlikte alım (B2C sepet, birliktelik oranı ≥1), aynı yazar, aynı dizi adayları; açılacak kart listesi (`SuggestionsTab.tsx`, `sets.py:22-28`).
- **Bugün AI:** Var. Gece: öneriye ad ve kısa tanıtım (`NAME_PROMPT` `sets.py:1694`, `run_model_tasks` `sets.py:1676`), en uygun özel gün `choose` + olasılık/marj (`choose_season` `sets.py:1666-1670`).
- **Beklenti:** «7–10 yaş, stokta, liste fiyatı X–Y arası 5 kitaplık yaz seti öner» serbest isteği; tematik küme (konu) önerisi.
- **Yapabileceklerimiz:** **Serbest istekten set kurma** · stok, fiyat, yaş/hedef kitle (CRM) · kısıtları kural süzgeci; tema uyumu `choose` «bu kitap bu temaya uyar mı» · 4/5 · M (~4 gün) · rakam koddan. **Tematik küme adayı** (konu etiketleri + gömme kümeleme) · 3/5 · M.

### Set ve hediye › Kurumsal teklifler (`?sekme=teklifler`)
- **Ne yapıyor:** Kurumsal hediye teklif listesi; seçenekleri kod üretir (stok, bütçe, kademe) (`GiftOffersTab.tsx`).
- **Bugün AI:** Listede yok (mektup editörde).
- **Beklenti:** «Geçen yılbaşı hangi firmalara ne gönderdik?»; firmaya göre öneri.
- **Yapabileceklerimiz:** **Geçmiş teklif/benzer firma önerisi** · teklif kayıtları + M32 fırsatları · kural + özet · 2/5 · S.

### Set ve hediye › Promosyon ürünleri (`?sekme=promosyon`)
- **Ne yapıyor:** Promosyon ürünleri stok ve durumu (`PromoItemsTab.tsx`).
- **Bugün AI:** Yok. **Beklenti:** stoku biten promosyon uyarısı (kural). **Öneri:** model gerekmez; tükenme uyarısı kural (1/5). **Eksik:** —

### Set ekranı (`/pazarlama/set-hediye/set/:id`)
- **Ne yapıyor:** Bileşenler, fiyat–marj hesaplayıcı, ambalaj, sezon/kanal, Zeki AI metinleri, onay (`SetEditor.tsx:15`).
- **Bugün AI:** Var. Set tanıtım metni ve ambalaj brief'i `draft_text` (`sets.py:1714-1727`), guard.
- **Beklenti:** e-ticaret ürün açıklaması + SEO başlığı (T-soft'a yazmadan); fiyat için «%20 indirimde marj» (kural — var).
- **Yapabileceklerimiz:** **Set için site ürün açıklaması → SEO öneri kuyruğu** · set metni · taslak; SEO modülüne öneri olarak düşer, T-soft'a gitmez · 3/5 · S (~2 gün).

### Kurumsal hediye teklifi (`/pazarlama/set-hediye/teklif/:id`)
- **Ne yapıyor:** Seçenekler (kod), kademe indirimi, mektup (Zeki AI taslağı), onay (gönderen onaylayamaz), PDF (`GiftOfferEditor.tsx:14`).
- **Bugün AI:** Var. Teklif mektubu rakamsız taslak `draft_letter` (`sets.py:1737-1749`).
- **Beklenti:** Firma sektörüne göre ton; kişi başı bütçeye göre gerekçe.
- **Yapabileceklerimiz:** **Sektöre göre mektup tonu** · M32 firma sektörü · `choose` ton + taslak · 2/5 · S · gönderim yok, PDF insan gönderir.
- **Eksik:** —
## M20 Basın ilişkileri

Menü: Pazarlama › İletişim › «Basın ilişkileri» (1 öğe) · Rotalar: 7 (`/basin-iliskileri`, `/kitap/:bookId`, `/dosya/:id`, `/kisiler`, `/kisi/:key`, `/yansimalar`, `/rapor`) · Arka uç: `pr.py`, `pr_api.py`, `pr_export.py`, `pr_sources.py` · İhtiyaç: `M20-basin-medya-halkla-iliskiler.md`.

### Bugün (`/basin-iliskileri`)
- **Ne yapıyor:** Ayın kitapları ve PR dosyası durumu, onay bekleyenler, takip günü geçen gönderimler; listede olmayan kitap araması (`PrHome.tsx:12`, `:212`).
- **Kim:** PR sorumlusu (günlük iş), pazarlama müdürü (onay).
- **Bugün AI:** Ekranın kendisinde yok; takip günü geçen gönderimler için gece e-posta hatırlatması kuraldır (`pr_api.py:794`).
- **Beklenti:** «Bu ay hangi kitabın basın dosyası geride?»; hangi kitabın basın potansiyeli yüksek (yazar geçmişi, konu gündemi).
- **Yapabileceklerimiz:** **Basın potansiyeli sırası + gerekçe** · CRM haber arşivi (yazar/tür başına haber sayısı), web taraması, yayın takvimi · kural puan + model tek cümle · 3/5 · S (~2 gün) · rakam kayıttan.
- **Eksik:** —

### Kitabın basın geçmişi (`/basin-iliskileri/kitap/:bookId`)
- **Ne yapıyor:** PR dosyaları, CRM haber arşivi (2025-06'ya kadar, salt okunur), basına tanıtım gönderimi, kitap kartındaki basın metinleri (`PrBook.tsx:10`, `:118`).
- **Bugün AI:** Yok (bülten taslağı PR dosyasında).
- **Beklenti:** Geçmiş haberlerin özeti («bu yazar hakkında basın ne dedi?»); en çok ilgi gösteren mecralar.
- **Yapabileceklerimiz:** **Basın geçmişi özeti** · CRM haber arşivi başlık/özet + yansımalar · özet, alıntı guard · 2/5 · S (~1 gün).

### PR dosyası (`/basin-iliskileri/dosya/:id`)
- **Ne yapıyor:** Ulusal/yerel bülten, kişiye özel e-posta şablonu, 3 açılış cümlesi, onay, gönderim listesi, kişi önerisi, yansımalar (`PrKit.tsx:13-19`). Onaylı satırdan e-posta kişinin elinden tek tek gider (`pr_api.py:521`).
- **Bugün AI:** Var. Bülten/pitch/açılış taslakları `draft_part` (`pr.py:1538-1546`, istemler `pr.py:1476-1485`), kişiye özel pitch `personal_pitch` (`pr.py:1551-1567`), metinler `marketing.guard` denetimli; kişi önerisi `suggest` (`pr.py:1256`) kuraldır.
- **Beklenti:** Mecraya göre açı (edebiyat eki / yerel gazete / podcast); kişi sıralamasının gerekçesi; bülten İngilizce sürümü (yabancı basın).
- **Yapabileceklerimiz:**
  - **Kişi önerisine gerekçe cümlesi** · `suggest` puan bileşenleri (aynı tür/yazar haberi, son temas) · model gerekçe · 3/5 · S (~1 gün) · kişisel veri (e-posta) modele gitmez, yalnız mecra ve haber başlıkları.
  - **Mecra türüne göre açı önerisi** · mecra türü + kitap metinleri · `choose` açı (söyleşi/inceleme/liste/gündem) + taslak · 3/5 · S (~2 gün).
  - **Pitch sonrası takip e-postası taslağı** · gönderim kaydı + yanıt yok · taslak · 2/5 · S · gönderimi kişi yapar.
- **Eksik:** —

### Medya kişileri (`/basin-iliskileri/kisiler`)
- **Ne yapıyor:** CRM basın kişileri (mecrası dolu ya da CRM haberlerinde geçen) + portalda eklenen kişiler (`PrContacts.tsx:13`, `:122`).
- **Bugün AI:** Yok.
- **Beklenti:** Konu etiketi (hangi gazeteci çocuk kitabı yazar), mükerrer kişi birleştirme.
- **Yapabileceklerimiz:** **Kişi konu etiketi** · CRM haber arşivinde yaptığı haberlerin başlıkları · `choose` kapalı küme (H1 kategori ağacının üst düzeyi) + olasılık · 3/5 · S (~2 gün) · ad/e-posta modele gitmez. **Mükerrer aday** · ad+mecra benzerliği (kural) · 2/5 · S.

### Medya kişisi kartı (`/basin-iliskileri/kisi/:key`)
- **Ne yapıyor:** İletişim, konular, CRM haber arşivindeki haberleri, gönderimler, yansımalar (`PrContact.tsx:13`).
- **Bugün AI:** Yok.
- **Beklenti:** «Bu gazeteciye hangi yeni kitabı önerelim?».
- **Yapabileceklerimiz:** **Kişiye kitap önerisi** · kişinin konu etiketi ↔ ayın kitaplarının kategorisi · kural eşleşme + gerekçe cümlesi · 3/5 · S (~1 gün, konu etiketinden sonra).

### Yansımalar (`/basin-iliskileri/yansimalar`)
- **Ne yapıyor:** Portal yansımaları + CRM haber arşivi tek listede; ton kaynağı Zeki AI / tarama / elle (`PrCoverage.tsx:13`, `:144`).
- **Bugün AI:** Var. Ton sınıflaması `classify_tone` kapalı küme Olumlu/Nötr/Olumsuz/İlgisiz + olasılık/marj, düşük güvende «siz seçin» (`pr.py:1573-1581`, `pr_api.py:680`, gece BATCH `pr_api.py:815`).
- **Beklenti:** Yansıma metninden kitap/yazar eşleme; bağlantıdan özet çıkarma; olumsuz yansımada uyarı.
- **Yapabileceklerimiz:** **Yansıma → kitap eşleme** · başlık/özet + kitap adları · aday (ad benzerliği) + `choose` (M21 `match_campaign` deseni `ads.py:740`) · 3/5 · S (~2 gün). **Olumsuz ton bildirimi** · ton=olumsuz · kural + tek cümle özet · 2/5 · S.

### Dönem raporu (`/basin-iliskileri/rapor`)
- **Ne yapıyor:** Gönderim/dönüş, yansıma (ton, mecra türü, kitap, mecra); erişim/tiraj yok (`PrReport.tsx:11`).
- **Bugün AI:** Var. `report_comment` sayıları yorumlar, listede olmayan sayı düşer (`pr.py:1588-1596`).
- **Beklenti:** Yansımanın satışa etkisi (ihtiyaç «sonraki sürüm»).
- **Yapabileceklerimiz:** **Yansıma ↔ satış önce/sonra** · yansıma tarihi + Logo günlük/haftalık satış · kural hesap + yorum («nedensellik değil») · 3/5 · M (~3 gün).
- **Eksik:** Erişim/tiraj verisi hiçbir kaynakta yok (ekranda doğru belirtilmiş).

## M21 Dijital pazarlama ve reklam

Menü: Pazarlama › Kampanya › «Reklam» (1 öğe) · Rotalar: 5 (`/reklam`, `/reklam/kampanyalar`, `/reklam/yukle`, `/reklam/butce`, `/reklam/brief`) · Arka uç: `ads.py`, `ads_api.py`, `ads_sources.py`, `ads_export.py` · İhtiyaç: `M21-dijital-pazarlama-reklam.md`.

### Genel bakış (`/reklam`)
- **Ne yapıyor:** Dönem + 4 gösterge, kanal/kampanya tablosu, kitap bazında harcama ↔ Logo e-ticaret cirosu, öneriler (stok, satış dışı, veri yok, bütçe, durdur, kaydır — kuralla `ads.py:1152-1227`) (`AdsOverview.tsx:13`).
- **Kim:** Dijital pazarlama/reklam uzmanı, pazarlama müdürü (para kararı).
- **Bugün AI:** Var. Rapor yorumu (`/report/summary` `ads_api.py:638-661`, `BRIEF_SYSTEM`), gece BATCH (`ads_api.py:697-704`); öneriler kuraldır, karar insanda.
- **Beklenti:** Önerinin gerekçesi 1–2 cümle; «hangi kitapta reklam harcaması ciroya dönmüyor?»; stoğu biten kitapta reklamı durdur uyarısı (var, kural).
- **Yapabileceklerimiz:**
  - **Öneri başına gerekçe cümlesi** (ihtiyaç §13) · öneri kaydı olguları · model gerekçe + guard · 3/5 · S (~1 gün) · koddaki öneri metni şablon mu model mi — doğrulanmadı.
  - **Harcama ↔ ciro sapma açıklaması** · kitap bazlı tablo · kural (en büyük sapma) + yorum · 3/5 · S.
  - **Ay sonu harcama tahmini** — `AdsBudget` zaten doğrusal tahmin gösteriyor; zaman serisi modeline gerek yok (1/5).
- **Eksik:** Siparişte UTM/kampanya kaynağı yok (ihtiyaç açık sorusu); ciro eşleşmesi kitap düzeyinde, kampanya düzeyinde değil.

### Kampanya ↔ kitap (`/reklam/kampanyalar`)
- **Ne yapıyor:** Her kampanyayı bir kitaba bağlar; kod/barkod kesin, değilse Zeki AI aday listesinden önerir, uzman onaylar (`AdsCampaigns.tsx:12`).
- **Bugün AI:** Var. `match_campaign` kod → ad benzerliği adayları → `llm.choose` (aday ya da «Hiçbiri») + olasılık/marj (`ads.py:740-760`, iş `ads_api.py:205`).
- **Beklenti:** Çok kitaplı kampanya (set/yazar kampanyası) desteği; kampanya adı kuralı önerisi.
- **Yapabileceklerimiz:** **Çoklu bağ (yazar/dizi/set)** · kampanya adı + M53 setleri + yazar listesi · aday genişletme + `choose` · 2/5 · S (~2 gün).

### Harcama yükleme (`/reklam/yukle`)
- **Ne yapıyor:** Hesap seç → dosya → kolon eşlemesi onayı → yükle (`AdsImport.tsx:13`).
- **Bugün AI:** Var. Eksik kolon için `model_mapping` kapalı küme (başlıklar + «yok») olasılıkla (`ads_sources.py:195-206`, `ads_api.py:318-330`).
- **Beklenti:** Farklı platform dosyasını ilk seferde tanıma — karşılandı.
- **Yapabileceklerimiz:** Ortak **dosya kolon eşleme yapı taşı** (M22 rapor, M40 Trendyol, M36 dijital satış, H2 yükleme aynı deseni kullanabilir) · 3/5 · S (~2 gün ortaklaştırma).

### Bütçe (`/reklam/butce`)
- **Ne yapıyor:** Ay × kanal plan, yüklenen harcama, ay sonu tahmini; M15 onaylı planların reklam satırları ve CRM bütçe kayıtları (`AdsBudget.tsx:14`, `:152`).
- **Bugün AI:** Yok.
- **Beklenti:** «Kasımda hangi kanala ne kadar kaydırmalıyım?» gerekçeli öneri.
- **Yapabileceklerimiz:** **Kanal bütçe kaydırma senaryosu** · kanal bazlı harcama/ciro oranı (kural) + model gerekçe · 3/5 · M (~3 gün) · karar insanda, rakam koddan.

### Brief (`/reklam/brief`)
- **Ne yapıyor:** Kampanya brief'i: hedef kitle, mesaj, kanal, reklam metni önerisi; onay; ajansa gönderimi ekip yapar (`AdsBriefs.tsx:14`).
- **Bugün AI:** Var. Brief taslağı `BRIEF_SYSTEM` (`ads_api.py:530-557`), guard.
- **Beklenti:** Platform sınırına uyan reklam metinleri — M19'da var.
- **Yapabileceklerimiz:** **Brief'ten M19 talebine tek tık** (varyantlar M19'da üretilsin) · 2/5 · S · yeni model işi değil, bağlantı.

## M22 Sosyal medya

Menü: Pazarlama › İletişim › «Sosyal medya» (1 öğe) · Rotalar: 5 (`/sosyal-medya`, `/gonderi/:id`, `/firsatlar`, `/rapor`, `/hesaplar`) · Arka uç: `social.py`, `social_api.py`, `social_sources.py` · İhtiyaç: `M22-sosyal-medya.md`.

### Takvim (`/sosyal-medya`)
- **Ne yapıyor:** Bütün hesapların takvimi (telefonda gün, masaüstünde hafta), onay bekleyenler, yaklaşan fırsatlar; «Yeni gönderi» penceresi (`SocialCalendar.tsx:14`, `NewPost.tsx:11`).
- **Kim:** Sosyal medya uzmanı (planlama), pazarlama müdürü (onay).
- **Bugün AI:** Takvimde yok; yeni gönderide içerik türü boş bırakılırsa «Sonra (Zeki AI önerir)» (`NewPost.tsx:106`) — tür, rapordaki gece etiketlemesiyle (`label_kinds`) kapalı kümeden seçilir.
- **Beklenti:** Haftalık dengesizlik uyarısı (hep kapak, hiç yazar içeriği yok); boş gün doldurma önerisi; en iyi paylaşım saati.
- **Yapabileceklerimiz:** **İçerik karışımı denetimi** · gönderi türleri (`label_kinds` etiketleri) · kural oran + öneri cümlesi · 2/5 · S. **Paylaşım saati önerisi** · rapor dosyasından etkileşim × saat · kural (medyan) · 2/5 · S · veri yoksa gösterilmez.

### Gönderi (`/sosyal-medya/gonderi/:id`)
- **Ne yapıyor:** Metin, etiket, görsel, zaman; kitaptan içerik (CRM metinleri, stüdyo alıntıları/görselleri), Zeki AI'ın üç seçeneği, onay, yayına hazır paket (`SocialPost.tsx:16`).
- **Bugün AI:** Var. Üç seçenek + hashtag `llm.chat` (`social_api.py:405-435`), kaynak = CRM metinleri + stüdyo alıntıları; guard denetimi. Portal paylaşım yapmaz.
- **Beklenti:** İmprint tonuna uyum; alıntı adayı çıkarma (≤2 cümle); platforma göre uyarlama (Reels senaryosu, X kısa).
- **Yapabileceklerimiz:** **Kitap metninden alıntı adayı** · stüdyodaki tam metin (varsa) · gömme + kısa pasaj seçimi, birebir kontrol · 3/5 · M (~3 gün) · telif: alıntı uzunluğu sınırı. **Bir metni diğer platformlara uyarlama** · onaylı metin · taslak · 2/5 · S.

### Fırsatlar (`/sosyal-medya/firsatlar`)
- **Ne yapıyor:** Özel günler + bağlı kitaplar, yeni çıkanlar, uzun süredir paylaşılmayan çok satan backlist, basında çıkan haberler (tarama açıksa) (`SocialOpportunities.tsx:11`).
- **Bugün AI:** Yok (kural listeleri).
- **Beklenti:** Gündem (trend) ile kitap eşleşmesi; «neden şimdi» gerekçesi.
- **Yapabileceklerimiz:** **Gündem ↔ kitap eşleşmesi** · M17 konu eşleşmesi (`backlist.py:1086`) + SEO sezon verisi · aynı `choose` hattı · 3/5 · S (~1 gün, yeniden kullanım).

### Aylık rapor (`/sosyal-medya/rapor`)
- **Ne yapıyor:** İçerik türü × etkileşim, hesap bazında erişim/takipçi, onay süresi medyanı; platform dosyası içe aktarma (`SocialReport.tsx:13`).
- **Bugün AI:** Var. Rapor yorumu `run_comment` (`social_api.py:545-559`), içerik türü etiketi `label_kinds` kapalı küme `llm.choose` (`social_api.py:620-640`, BATCH).
- **Beklenti:** «Hangi içerik türü satışa döndü?»; yorum/DM önem sınıflaması (ihtiyaç: sonraki sürüm).
- **Yapabileceklerimiz:** **Yorum/DM sınıflama (dosyadan)** · platform dışa aktarımındaki yorum metni (maskeli) · `choose` şikâyet-sipariş/şikâyet-içerik/soru/basın/olumlu/olumsuz · 3/5 · M (~3 gün) · kişisel veri maskelenir; sipariş şikâyeti M51'e yönlendirme önerisi.

### Hesaplar (`/sosyal-medya/hesaplar`)
- **Ne yapıyor:** İmprint başına platform hesapları; CRM marka kartındaki Instagram adları öneri; hesabın dili taslağa girer (`SocialAccounts.tsx:11`).
- **Bugün AI:** Dolaylı (hesap dili taslak istemine girer). **Beklenti/Öneri:** Hesap başına «ton kılavuzu» (onaylı gönderilerden özet) · 2/5 · S. **Eksik:** —

## M23 İşbirlikleri (içerik üreticileri)

Menü: Pazarlama › İletişim › «İşbirlikleri» (1 öğe) · Rotalar: 7 (`/isbirlikleri`, `/kisiler`, `/kisi/:id`, `/aday`, `/aday/:kitap`, `/rapor`, `/odemeler`) · Arka uç: `influencers.py`, `influencers_api.py`, `influencers_sources.py` · İhtiyaç: `M23-influencer-isbirligi.md`.

### Pano (`/isbirlikleri`)
- **Ne yapıyor:** Teklif → kitap gönderildi → içerik bekleniyor → onayda → yayında → rapor → ödeme sütunları; iş kartı (`CollabBoard.tsx:13`, `CollabSheet.tsx:14`).
- **Kim:** İşbirliği/influencer sorumlusu, pazarlama müdürü (onay, ücret).
- **Bugün AI:** Var (iş kartında). Brief/iletişim/sadakat taslakları `render_draft` (`influencers.py:1274`) — model yalnız serbest paragrafı yazar, yasal reklam etiketi maddesi şablonda sabit (`CollabSheet.tsx:229`).
- **Beklenti:** Geciken içerik uyarısı; içerik yayınlandı mı (bağlantı) kontrolü; yayınlanan içerikte reklam etiketi var mı.
- **Yapabileceklerimiz:** **Yayınlanan içerikte reklam etiketi denetimi** · içerik bağlantısının metni (elle yapıştırılan) · kural (#işbirliği/#reklam) + `choose` · 3/5 · S (~1 gün) · Reklam Kurulu kılavuzu riski.

### İçerik üreticileri (`/isbirlikleri/kisiler`)
- **Ne yapıyor:** Kayıt defteri; süzgeç platform/konu/yaş/boş gün (`PeopleList.tsx:13`).
- **Bugün AI:** Konu etiketi kişi kartında (aşağıda). **Beklenti:** benzer kişi bulma. **Öneri:** **Benzer içerik üreticisi** · konu etiketi + biyografi gömmesi · benzerlik · 2/5 · M.

### Kişi kartı (`/isbirlikleri/kisi/:id`)
- **Ne yapıyor:** Aldığı kitaplar, paylaşımları, ödemeler, hesap ölçümleri, ilişki puanı (`PersonCard.tsx:16`).
- **Bugün AI:** Var. Biyografi/son gönderi başlıklarından konu önerisi `choose` (`influencers_api.py:197`, pencere `PersonCard.tsx:188`).
- **Beklenti:** Sahte takipçi/etkileşim şüphesi; ilişki geçmişi özeti.
- **Yapabileceklerimiz:** **Etkileşim anomalisi** · hesap ölçümleri (takipçi, etkileşim zamanla) · kural (oran sapması), model yok · 2/5 · S.

### Kitaba aday (`/isbirlikleri/aday`, `/isbirlikleri/aday/:kitap`)
- **Ne yapıyor:** Kitaba gerekçeli aday sırası; puan kuralla (ağırlıklar yönetimde); iletişim kurulmayacaklar ayrı (`Candidates.tsx:13`).
- **Bugün AI:** Var. Seçilenlere tek cümle gerekçe (`influencers_api.py:251-265`; istemde içerik üreticisinin adı geçiyor — kamuya açık hesap adı, yine de takma ad/kimlikle değiştirilebilir), kitap konusu `choose` (`influencers_api.py:108`).
- **Beklenti:** Bütçeye göre aday seti önerisi.
- **Yapabileceklerimiz:** **Bütçe kısıtlı aday seti** · ücret aralığı + puan · kural (sırt çantası), model gerekçe · 3/5 · S (~2 gün) · ücret yalnız yetkili.

### Rapor (`/isbirlikleri/rapor`)
- **Ne yapıyor:** Dönem işbirlikleri, erişim, etkileşim, yetkiliye harcama ve CPE; CRM «Influencer» bütçe kayıtları ayrı (`CollabReport.tsx:11`).
- **Bugün AI:** Yok.
- **Beklenti:** Satış etkisi yorumu (ihtiyaç «sonraki»); dönem yorumu.
- **Yapabileceklerimiz:** **Dönem yorumu + önce/sonra satış** · rapor tablosu + Logo satış · yorum + guard · 3/5 · S (~2 gün).

### Ödemeler (`/isbirlikleri/odemeler`)
- **Ne yapıyor:** Muhasebe ödeme listesi: hazır → onaylı → ödendi (Logo belge no); portal ödeme yapmaz (`Payouts.tsx:13`).
- **Bugün AI:** Yok. **Beklenti:** Logo'daki ödeme belgesiyle eşleştirme. **Öneri:** **Logo ödeme belgesi eşleme** · Logo cari hareket (serbest çalışan kartı, bkz. proje belleği «Serbest çalışan ödemeleri») · kural + `choose` aday seçimi · 3/5 · M (~3 gün). **Eksik:** —

## M24 Katalog ve bülten

Menü: Pazarlama › Kampanya › «Katalog ve bülten» (1 öğe) · Rotalar: 4 (`/katalog-bulten` [sekme katalog|bulten], `/katalog-bulten/rapor`, `/katalog/:id`, `/bulten/:id`) · Arka uç: `catalogs.py`, `catalogs_api.py`, `catalogs_sources.py`, `newsletters.py`, `bulletins.py` · İhtiyaç: `M24-katalog-bulten.md`.

### Kataloglar (`/katalog-bulten?sekme=katalog`)
- **Ne yapıyor:** Katalog listesi: durum, kitap sayısı, kritik fiyat/stok uyarısı rozeti; yeni katalog (`CatalogList.tsx:19`).
- **Kim:** Pazarlama (katalog hazırlığı), satış (bayi kataloğu), yabancı haklar (hak kataloğu).
- **Bugün AI:** Yok (listede). **Beklenti:** Katalog türüne göre hazır kitap listesi. **Öneri:** bkz. katalog düzenleme.

### Katalog düzenleme (`/katalog-bulten/katalog/:id`)
- **Ne yapıyor:** Süzgeç ve öneri (seçim puanı kuralla, `reason_parts` `catalogs.py:349`), kitap sırası/öne çıkan/metin, canlı fiyat/stok uyarısı, onay, tasarımcı paketi (`CatalogEditor.tsx:19`).
- **Bugün AI:** Var. Katalog uzunluğuna kısaltma `zeki_text` ve kitap başına gerekçe `zeki_reason` (`catalogs.py:830-862`, `llm_for("katalog", BATCH)` `catalogs_api.py:63`); düşen cümle sayısı bildirilir.
- **Beklenti:** Yabancı hak kataloğu için İngilizce taslak (ihtiyaç §13); katalog bölümlerini (tema) otomatik gruplama.
- **Yapabileceklerimiz:** **İngilizce hak kataloğu metni** · CRM tanıtım metni · çeviri taslağı + terim sözlüğü (editör çeviri hattı `editorial_translation*.py` yeniden kullanım) · 3/5 · M (~3 gün) · kodda İngilizce taslak doğrulanmadı. **Tema bölümleme** · H1 kategori + gömme kümeleme · 2/5 · M.

### Bültenler (`/katalog-bulten?sekme=bulten`)
- **Ne yapıyor:** Bülten listesi: tarih, segment büyüklüğü (yalnız sayı), son sonuç (`NewsletterList.tsx:19`).
- **Bugün AI:** Yok (listede).

### Bülten düzenleme (`/katalog-bulten/bulten/:id`)
- **Ne yapıyor:** Segment (sayı, izin kuralı köprüde — `SegmentBuilder.tsx:8`), kitaplar, gövde + konu satırı, onay, gönderime hazır HTML, sonuç (`NewsletterEditor.tsx:20`).
- **Bugün AI:** Var. Gövde ve konu satırı `run_draft` (`newsletters.py:521`, `llm_for("bulten", NORMAL)`), CRM tanıtım metinleriyle sınırlı, guard.
- **Beklenti:** Segmente göre kitap önerisi ve eşleme gerekçesi; konu satırı A/B seçenekleri; spam-tetikleyici kelime denetimi.
- **Yapabileceklerimiz:** **Segment ↔ kitap eşleşmesi + gerekçe** · segment kuralı (tür/yaş ilgisi) + kitap kategorisi · kural + gerekçe cümlesi · 3/5 · S (~2 gün) · kişi verisi yok, yalnız segment tanımı. **Konu satırı varyantları + geçmiş açılma oranına göre sıralama** · Rapor verisi · 2/5 · S.

### Rapor (`/katalog-bulten/rapor`)
- **Ne yapıyor:** Portal bültenlerinin ve CRM e-posta/SMS kampanyalarının sonuçları (`Report.tsx:10`).
- **Bugün AI:** Yok. **Beklenti:** 3 cümle sonuç yorumu (ihtiyaç §13). **Öneri:** **Sonuç yorumu** · rapor tablosu · yorum + guard (launch_report deseni) · 2/5 · S (~1 gün). **Eksik:** —
## M25–M26 SEO & GEO

Menü: Pazarlama › İzleme (15 öğe), İş (22 öğe), Ayar (1 öğe) = 38 öğe (`seo-*`) · Rotalar: 38 (`/seo-geo…`, hepsi aşağıda) · Arka uç: `backend/semantic_bridge/seo_geo/*` (40 dosya) · İhtiyaç: `docs/analiz/kullanici-ihtiyaclari/` altında M25/M26 dosyası **yok**; kaynak `docs/analiz/seo-geo-modul-2026-09-25.md` (ana akış: ürün denetimi → model önerisi → insan onayı → T-soft'a elle).
Genel kural (bütün ekranlar): T-soft'a, CRM'e, siteye yazma yok; onaylanan öneri CSV/HTML/JSON olarak iner, insan panelden girer.

**Bugün modelin (Zeki AI, yerel) kullanıldığı yerler:** ürün önerisi `propose.suggest` (`seo_geo/propose.py:178`, `__init__.py:311`); yazar/kategori/yayınevi sayfası önerisi (`pages.py:172`, `__init__.py:1052`); rehber taslakları (`guides.py:408`, `:667`); kitap soru–cevapları (`faq.py:202-213`, `:349`); yazar biyografileri (`bios.py:387`, `:598`). Başka hiçbir SEO dosyasında model çağrısı yok (yönlendirme, benzer kitap, soru önerisi, iş listesi, izleme bilinçli olarak modelsiz — `redirects.py:1`, `qsuggest.py:1`).
**Dikkat:** «Yapay zekâ görünürlüğü» ölçümü (`geo.py:1-30`) kamuya açık okur sorularını dış yapay zekâ motorlarına (anahtar girilirse) resmî API'yle sorar — bu ölçüm nesnesidir, şirket verisi gitmez; bizim işleme modelimiz yerel kalır. Ekranda ölçülen dış motorların adları yazıyor (`SeoVisibility.tsx:45`, `:62`; etiket `__init__.py:417`) — bunlar ölçüm nesnesi olduğu için gerekli olabilir, ama «ekranda teknoloji adı yok» kuralıyla (09-25) ilişkisi kullanıcı kararı ister.

### SEO özeti (`/seo-geo`)
- **Ne yapıyor:** Ürün puanları, kural dağılımı, onay bekleyenler, Search Console özeti, bağlantılar; veri yoksa ne eksik söyler (`SeoHome.tsx`).
- **Kim:** SEO/dijital pazarlama uzmanı, e-ticaret yöneticisi.
- **Bugün AI:** Yok (özet sayılar).
- **Beklenti:** «Bu hafta SEO'da ne değişti, önce ne yapmalıyım?» tek paragraf.
- **Yapabileceklerimiz:** **Haftalık durum paragrafı** · özet sayıları + `watch.py` olayları · yorum + rakam guard (`marketing/guard.py` yeniden kullanım) · 3/5 · S (~1 gün).
- **Eksik:** —

### Arama ve kelimeler (`/seo-geo/anahtar-kelimeler`)
- **Ne yapıyor:** Search Console sorguları ve sayfalar; bütün satırlar, süzme ve sayfalama (`SeoSearch.tsx`).
- **Bugün AI:** Yok.
- **Beklenti:** Sorguları niyete göre gruplama (bilgi/kitap adı/yazar/liste/satın alma); sorgu → H1 kategori.
- **Yapabileceklerimiz:** **Sorgu niyeti + H1 düğümü sınıflama** · GSC sorgu metni · `choose` kapalı küme + olasılık (gece BATCH) · 4/5 · M (~3 gün) · H3 ihtiyaç §13 «arama sorgusu → niyet» ile aynı yapı taşı; kişisel veri yok.

### Fırsatlar ve etki (`/seo-geo/firsatlar`)
- **Ne yapıyor:** Yakın sıradaki ve az tıklanan sorgular; onaylanan değişikliğin yayından sonraki etkisi (`SeoOpportunities.tsx`, `opportunities.py`, `impact.py`).
- **Bugün AI:** Yok (tahmini ek tıklama kural eğrisi).
- **Beklenti:** Fırsat sorgusu için hangi sayfada neyi değiştirmeli önerisi.
- **Yapabileceklerimiz:** **Fırsattan ürün önerisine tek tık** · sorgu + hedef sayfa · mevcut `propose.suggest`'e sorguyu hedef kelime olarak ekleme · 4/5 · S (~2 gün) · T-soft'a gitmez.

### Bing ve IndexNow (`/seo-geo/bing`)
- **Ne yapıyor:** Bing Webmaster sorgu/trafik/tarama (yalnız okuma), Google ile sıra karşılaştırması, değişen sayfaların IndexNow bildirimi (`SeoBing.tsx`, `bing.py`).
- **Bugün AI:** Yok. **Beklenti/Öneri:** Model gerekmez (bildirim kural). 1/5. **Eksik:** IndexNow bildirimi dış sisteme gönderim — kendi sitemizin arama motoruna bildirimi; «dış gönderim yok» ilkesinin kapsamı dışında sayıldığı doğrulanmadı.

### Rakipler (`/seo-geo/rakipler`)
- **Ne yapıyor:** Aynı kitap aramasında Google'da kim kaçıncı; sıra çok satandan; aylık kota (`SeoCompetitors.tsx`, `competitors.py`).
- **Bugün AI:** Yok.
- **Beklenti:** Rakibin neden önde olduğu (başlık, açıklama uzunluğu, yorum sayısı) kısa açıklama.
- **Yapabileceklerimiz:** **Rakip sayfa karşılaştırma notu** · arama sonucu başlık/snippet (kamuya açık) · kural fark + yorum · 2/5 · S (~2 gün).

### İzleme ve rapor (`/seo-geo/izleme`)
- **Ne yapıyor:** Gece çıkarılan olaylar (tıklama düşüşü, 404, robots, sitemap, yapay zekâ cevabından düşme, CRM yayın durumu, hız) ve haftalık rapor (`SeoWatch.tsx`, `watch.py`).
- **Bugün AI:** Yok.
- **Beklenti:** Olayların olası nedenini birleştirme («tıklama düşüşü = sayfa pasifleşti + 404»).
- **Yapabileceklerimiz:** **Olay kök neden birleştirme** · aynı ürün/sayfaya ait olaylar · kural bağlama + tek cümle · 3/5 · S (~2 gün). **Haftalık rapor paragrafı** (SEO özeti önerisiyle aynı yapı taşı).

### Yapay zekânın kaynakları (`/seo-geo/kaynaklar`)
- **Ne yapıyor:** Yapay zekâ cevaplarında gösterilen kaynakların alan adı toplamı, tür (kural), Timaş'ın anılmadığı sık kaynaklar = hedef listesi (`SeoSources.tsx`, `ai_sources.py:1-12`).
- **Bugün AI:** Yok (tür kuralla).
- **Beklenti:** Hedef siteye nasıl içerik verilebileceği (PR, iş birliği).
- **Yapabileceklerimiz:** **Hedef listeyi M20/M23'e aktarma + tür belirsizse `choose`** · alan adı + başlık · 2/5 · S.

### Yarışan sayfalar (`/seo-geo/yarisan`)
- **Ne yapıyor:** Aynı aramada birbirinin sırasını düşüren sayfalar (GSC sorgu+sayfa) (`SeoCannibal.tsx`, `cannibal.py`).
- **Bugün AI:** Yok. **Beklenti:** Hangi sayfa kalsın önerisi. **Öneri:** kural (tıklama/dönüşüm üstün olan) + gerekçe cümlesi · 2/5 · S.

### Google taraması (`/seo-geo/google-taramasi`)
- **Ne yapıyor:** URL Denetimi ile Google'ın son hâli, bot istatistikleri, yapay zekâ botlarının davranışı (`SeoCrawlbot.tsx`, `crawlbot.py`).
- **Bugün AI:** Yok. **Beklenti/Öneri:** Model gerekmez; «dizine alınmadı» nedenlerinin Türkçe açıklaması sabit sözlükle · 1/5 · S.

### Gelen bağlantılar (`/seo-geo/geri-baglantilar`)
- **Ne yapıyor:** Bing'in gördüğü dış bağlantılar, yeni/kaybolan, bağlantısı olmayan çok satanlar (`SeoBacklinks.tsx`, `backlinks.py`).
- **Bugün AI:** Yok. **Beklenti:** Bağlantı veren sitenin türü ve değeri. **Öneri:** alan adı türü `ai_sources` kurallarıyla + belirsizde `choose` · 2/5 · S.

### Sorgu–sayfa eşlemesi (`/seo-geo/sorgu-sayfa`)
- **Ne yapıyor:** Her önemli arama için hedef sayfa, yanlış sıralanan sayfa, sayfamızın olmadığı aramalar; karar kaydı (`SeoKeymap.tsx`, `keymap.py`).
- **Bugün AI:** Yok.
- **Beklenti:** Sayfası olmayan arama için «rehber mi, kategori mi, kitap mı» önerisi.
- **Yapabileceklerimiz:** **Boşluk türü önerisi** · sorgu + katalog · `choose` (kitap/yazar/kategori/rehber/yok) + gömme ile aday sayfa · 3/5 · M (~3 gün) · karar insanda, rehber seçilirse `guides.py` hattına düşer.

### Soru önerileri (`/seo-geo/soru-onerileri`)
- **Ne yapıyor:** GEO ölçümüne eklenecek okur soruları; GSC, CRM tema/yaş, özel günlerden **kodla** (`qsuggest.py:1-12`).
- **Bugün AI:** Yok (bilinçli: aynı veri aynı soru).
- **Beklenti:** Soruların doğal dile yakınlığı.
- **Yapabileceklerimiz:** **Kalıp sorunun doğal dil varyantı (isteğe bağlı)** · kalıp soru · taslak; ölçüm tekrarlanabilirliği için varyant sabitlenir · 1/5 · S · önerilmez de denebilir: deterministiklik bilinçli karar.

### YouTube (`/seo-geo/youtube`)
- **Ne yapıyor:** CRM tanıtım videolarının YouTube'daki açıklaması (site bağlantısı, kitap adı), erişilebilirlik; önerilen açıklama satırını kanal sahibi ekler (`SeoYoutube.tsx`, `youtube.py`).
- **Bugün AI:** Yok (öneri satırı kural).
- **Beklenti:** Video açıklaması ve bölüm (chapter) metni taslağı.
- **Yapabileceklerimiz:** **Video açıklaması taslağı** · CRM tanıtım metni + video başlığı · taslak + guard · 2/5 · S. **Altyazıdan özet** (altyazı okunabiliyorsa; doğrulanmadı) · 2/5 · M.

### Aylık rapor (`/seo-geo/aylik-rapor`)
- **Ne yapıyor:** Önceki ayın SEO & GEO özeti PDF; gece hazırlanır, alıcı tanımlıysa iç e-posta (`SeoMonthly.tsx`, `monthly.py`).
- **Bugün AI:** Yok.
- **Beklenti:** Yönetim için 5 cümle yorum ve 3 öneri.
- **Yapabileceklerimiz:** **Aylık yorum** · rapor rakamları · yorum + guard · 3/5 · S (~1 gün).

### Yapay zekâ görünürlüğü (`/seo-geo/ai-gorunurluk`)
- **Ne yapıyor:** İzlenen sorular yapay zekâ motorlarına sorulur; Timaş anıldı mı (regex `BRAND`), site kaynak gösterildi mi, hangi kitaplar geçti (`SeoVisibility.tsx`, `geo.py`).
- **Kim:** SEO/GEO uzmanı, pazarlama müdürü.
- **Bugün AI:** Ölçüm dış motorlarla; bizim modelimiz cevabı yorumlamıyor (anılma regex).
- **Beklenti:** Cevapta Timaş'ın nasıl anıldığı (olumlu/yanlış bilgi), rakip yayınevlerinin anılması, yanlış bilgi uyarısı.
- **Yapabileceklerimiz:** **Cevap içeriği sınıflama (yerel model)** · kaydedilmiş cevap metni · `choose` doğru/yanlış bilgi/olumsuz/nötr + anılan rakip listesi (kural) · 4/5 · M (~3 gün) · yanlış bilgi M28/M20 düzeltme işine düşer; dış gönderim yok.
- **Eksik:** Motor adları ekranda yazıyor (`SeoVisibility.tsx:45`, `:62`); «teknoloji adı yok» kuralı için ölçüm nesnesi istisnası mı sayılacak — kullanıcı kararı gerekir.

### Yazar ve kategori sayfaları (`/seo-geo/sayfalar`)
- **Ne yapıyor:** Yazar, kategori, yayınevi sayfalarının başlık/açıklama denetimi ve Zeki AI önerisi (SEO başlığı, meta, tanıtım) — sayfanın kitapları, satışları, doğrulanmış Wikidata bilgisinden (`SeoPages.tsx`).
- **Bugün AI:** Var. `pages.py:172`, uç `__init__.py:1045-1056` (`llm_for("seo")`).
- **Beklenti:** Karşılandı; toplu öneri kuyruğu.
- **Yapabileceklerimiz:** **Gece toplu öneri (BATCH)** · 2/5 · S.

### Yönlendirmeler (`/seo-geo/yonlendirmeler`)
- **Ne yapıyor:** Anasayfaya giden 301'ler için doğru hedef önerisi, gerekçe, alternatifler; modelsiz, kurallı (`redirects.py:1-20`).
- **Bugün AI:** Yok (bilinçli). **Beklenti:** «Eşleşme yok» kalanlar için aday. **Öneri:** **Eşleşmeyenlerde gömme benzerliği + `choose`** · eski adres kelimeleri + yaşayan sayfa başlıkları · 3/5 · S (~2 gün) · güven etiketi «orta»yı geçmez, insan onayı.

### Teknik sağlık (`/seo-geo/teknik`)
- **Ne yapıyor:** Canonical, yönlendirme, sitemap, yapay zekâ botları, görsel ve hız (LCP/INP/CLS) (`SeoTech.tsx`, `tech.py`, `speed.py`).
- **Bugün AI:** Yok. **Beklenti:** Site yöneticisine iş talebi metni. **Öneri:** **Tema/BT iş talebi taslağı** · bulgu listesi · şablon + kısa taslak · 2/5 · S. Görsel alt metin eksikse **alt metin taslağı** · kapak görseli + kitap adı · görsel açıklama modeli (doğrulanmadı) · 2/5 · M.

### Kimlik ve bilgi paneli (`/seo-geo/kimlik`)
- **Ne yapıyor:** Wikidata, Wikipedia, anasayfa, CRM'den Timaş/yazar/kitap kimlik kayıtları ve eksikler; yalnız okuma (`SeoEntity.tsx`, `entity.py`).
- **Bugün AI:** Yok.
- **Beklenti:** Wikidata'ya girilecek önerilen beyanlar (kaynaklı).
- **Yapabileceklerimiz:** **Kaynaklı beyan taslağı** · CRM künye + site · kural (alan eşleme) + kaynak bağlantısı; model gerekmez · 2/5 · S · Wikidata'ya yazma insan eliyle.

### Rehber içerikler (`/seo-geo/rehberler`)
- **Ne yapıyor:** «Hangi kitap?» sorusuna cevap veren liste sayfası taslakları; konu aramalardan ve izlenen sorulardan; kitaplar yalnız kataloğumuzdan; Zeki AI yazar, insan onaylar (`SeoGuides.tsx`).
- **Bugün AI:** Var. `guides.py:14`, `:408-415` (6000 token, hatalıysa bir kez düzeltme), `:667`.
- **Beklenti:** Kitap seçiminin gömme ile yapılması; iç bağlantı önerisi.
- **Yapabileceklerimiz:** **Konuya göre kitap seçimi için benzerlik araması** · CRM özet + tema/yaş · gömme · 3/5 · M (~3 gün, ortak yapı taşı).

### Sezon takvimi (`/seo-geo/takvim`)
- **Ne yapıyor:** Yaklaşan özel günler, bağlı kitaplar, sayfa hazırlığı, geçen yılın arama artışı (`SeoSeasons.tsx`, `seasons.py`).
- **Bugün AI:** Yok.
- **Beklenti:** Özel güne bağlı olmayan ama uygun kitap önerisi.
- **Yapabileceklerimiz:** **Konu eşleşmesi** · M17 `backlist.py:1086` `choose` hattı yeniden kullanım · 3/5 · S (~1 gün).

### Site içi bağlantılar (`/seo-geo/ic-baglantilar`)
- **Ne yapıyor:** Bağlantı almayan kitaplar, derinlik, yazar–kitap bağları (`SeoLinks.tsx`, `links.py`).
- **Bugün AI:** Yok. **Öneri:** bkz. Benzer kitaplar (bağlantı adayı) · 2/5.

### Okur yorumları (`/seo-geo/yorumlar`)
- **Ne yapıyor:** Çok satıp yorumsuz kitaplar, puan dağılımı, şemada puanı görünmeyen sayfalar (`SeoReviews.tsx`, `reviews.py`).
- **Bugün AI:** Yok. **Beklenti:** Yorum toplama kampanyası listesi. **Öneri:** M37 yorum sınıflama yapı taşı; yorumdan SSS adayı · 2/5 · S.

### Video (`/seo-geo/video`)
- **Ne yapıyor:** CRM YouTube videoları için video şeması önerisi, video sitemap, tema isteği (`SeoVideo.tsx`, `video.py`).
- **Bugün AI:** Yok. **Öneri:** Video açıklaması (bkz. YouTube) · 1/5.

### Satıştan kalkan kitaplar (`/seo-geo/satistan-kalkan`)
- **Ne yapıyor:** CRM'de bizim olmayan/çekilen/baskısı biten kitaplar ve pasif ama aranan sayfalar için 301/stokta yok/410 önerisi (`SeoSunset.tsx`, `sunset.py`).
- **Bugün AI:** Yok (kural). **Öneri:** 301 hedefi için Yönlendirmeler benzerlik yapı taşı · 2/5 · S.

### Yazar sayfaları (`/seo-geo/yazar-sayfalari`)
- **Ne yapıyor:** Çok satan yazarlar için sayfa, tanıtım, kimlik kaydı, şema, çevirmen/çizer künyesi, ödül — madde madde (`SeoAuthors.tsx`, `authors.py`).
- **Bugün AI:** Yok (biyografi ayrı ekranda). **Öneri:** bkz. Yazar biyografileri.

### İş listesi (`/seo-geo/is-listesi`)
- **Ne yapıyor:** Bütün SEO ekranlarının işleri tek kuyrukta, sorumlu ve açık etki puanıyla; kaynak üretmezse kendiliğinden kapanır (`SeoWorklist.tsx`, `worklist.py:1-15`).
- **Kim:** SEO sorumlusu, T-soft/site yöneticisi, telif, içerik ekibi, BT.
- **Bugün AI:** Yok (puan açık formül — bilinçli).
- **Beklenti:** Sorumluya göre haftalık özet; «bu hafta en çok etkisi olan 5 iş».
- **Yapabileceklerimiz:** **Sorumlu başına haftalık iş özeti** · iş listesi · şablon + kısa özet · 3/5 · S (~1 gün) · iç bildirim, dış gönderim yok.

### Kitap karnesi (`/seo-geo/kitap`)
- **Ne yapıyor:** Bir kitabın bütün SEO & GEO durumu tek sayfada (`SeoScorecard.tsx`, `scorecard.py`).
- **Bugün AI:** Yok (ekranlardan toplama).
- **Beklenti:** «Bu kitap için en önemli 3 düzeltme» özeti.
- **Yapabileceklerimiz:** **Karne özeti ve ilk 3 iş** · karne bulguları + iş listesi puanı · kural sıra + tek paragraf · 3/5 · S (~1 gün).

### Yazar biyografileri (`/seo-geo/yazar-biyografi`)
- **Ne yapıyor:** CRM özgeçmişinden yazar sayfası biyografisi; özgeçmişi olmayan yazar CRM işi; HTML indir (`SeoBios.tsx`).
- **Bugün AI:** Var. 120–220 kelime üçüncü şahıs biyografi + tek cümle özet (`bios.py:17`, `:387-394`, `:598`).
- **Beklenti:** Karşılandı; Wikidata'dan doğrulanmış olgu ekleme.
- **Yapabileceklerimiz:** **Wikidata doğrulanmış olgu ile zenginleştirme** (`entity.py` verisi) · 2/5 · S.

### Kitap soru–cevapları (`/seo-geo/sss`)
- **Ne yapıyor:** Kitap sayfası için 3–5 soru–cevap, kitabın CRM kartı ve site kaydından; okuma-anlama test soruları dışarıda; JSON-LD (`SeoFaq.tsx`).
- **Bugün AI:** Var. `faq.suggest` (`faq.py:202-213`), sınav sorusu ayıklama `drop_quiz` (`faq.py:143`, `:188`), `reality` denetimi (`faq.py:227`).
- **Beklenti:** Okurların gerçekten sorduğu sorulardan (M40 soruları, M37 yorumları) beslenme.
- **Yapabileceklerimiz:** **Gerçek okur sorularından SSS adayı** · Trendyol soruları + site yorumları (maskeli) · kümeleme + taslak · 3/5 · M (~3 gün).

### Benzer kitaplar (`/seo-geo/benzer-kitaplar`)
- **Ne yapıyor:** CRM emsal bağları + tema/yaş + yazar/dizi → «ilgili ürünler» önerisi; CSV ile elle girilir (`similar.py:1-10`).
- **Bugün AI:** Yok (kural).
- **Beklenti:** Emsali olmayan kitaplar için öneri.
- **Yapabileceklerimiz:** **Gömme benzerliği ile kapsama** · CRM özet + tema · gömme + kural süzgeç · 4/5 · M (~3 gün) · M15 emsal ve M39 emsal bulma ile tek yapı taşı.

### Google Alışveriş hazırlığı (`/seo-geo/alisveris`)
- **Ne yapıyor:** Satıştaki ürünlerin Google ürün verisi kurallarına göre denetimi; besleme dosyası elle yüklenir (`SeoShopping.tsx`, `shopping.py`).
- **Bugün AI:** Yok. **Beklenti:** Google ürün kategorisi eşlemesi. **Öneri:** **Kategori eşleme** · site kategorisi → Google taksonomisi · `choose` + olasılık · 2/5 · S.

### Şema denetimi (`/seo-geo/sema`)
- **Ne yapıyor:** Canlı kitap sayfalarının JSON-LD denetimi; tema isteği belgesi (`SeoSchema.tsx`, `schema.py`).
- **Bugün AI:** Yok. **Beklenti/Öneri:** Model gerekmez (kural) · 1/5.

### Yapay zekâ tarama dosyası (`/seo-geo/llms`)
- **Ne yapıyor:** llms.txt önerisi eşitlenmiş veriden, **modelsiz**; kopyala/indir, T-soft paneline elle (`SeoLlms.tsx`, `llms.py`).
- **Bugün AI:** Yok. **Beklenti:** Kategori açıklamalarının kısa özetleri. **Öneri:** Kategori özet cümlesi (Sayfalar önerisinden yeniden kullanım) · 1/5 · S.

### Haklar ve CRM (`/seo-geo/crm-haklar`)
- **Ne yapıyor:** T-soft'ta satıştaki kitapların CRM kartı, internette gösterim hakkı, yayın durumu (`SeoRights.tsx`, `crm.py`).
- **Bugün AI:** Yok. **Öneri:** M36 hak notu ön okuması (`dijital.py:856`) sonucunu burada göstermek · 2/5 · S.

### Ürün denetimi (`/seo-geo/urun-denetimi`)
- **Ne yapıyor:** Süzülen ürünler, seçilen ürünün sorunları, model önerisi ve karar (onay/ret); T-soft'a gitmez (`SeoAudit.tsx`).
- **Kim:** SEO uzmanı, e-ticaret içerik sorumlusu.
- **Bugün AI:** Var. `propose.suggest` SEO başlığı, meta açıklama, arama kelimeleri, açıklama (`propose.py:17`, `:178-191`); kayıtta olmayan bilgi `unsupported` ile işaretlenir (`propose.py:142`), sınırlar `enforce`/`violations` (`:106`, `:165`). M34 kart önerisi de bu hattı kullanır (`eticaret_api.py:291-321`).
- **Beklenti:** Toplu öneri; kitap metninden (stüdyo) daha zengin açıklama; onay sonrası etki takibi (Fırsatlar ve etki ekranında var).
- **Yapabileceklerimiz:** **Gece toplu öneri + güven sırası** · sorunlu ürünler · BATCH · 3/5 · S (~1 gün). **Onay/ret nedenlerinden kural öğrenme** · Karar geçmişi ret notları · özet → yönetim ayarına aday kural (insan onayı) · 2/5 · S.

### Karar geçmişi (`/seo-geo/gecmis`)
- **Ne yapıyor:** Karar verilmiş öneriler: kim, ne zaman, hangi alan, sonuç; geri alma ürün ekranında (`SeoHistory.tsx`).
- **Bugün AI:** Yok. **Beklenti/Öneri:** Ret nedeni kümeleri (bkz. Ürün denetimi) · 2/5 · S.

### Bağlantılar (`/seo-geo/baglantilar`)
- **Ne yapıyor:** Her kaynağın durumu ve kurulum adımı; değerler Yönetim ekranında (`SeoConnections.tsx`, `connections.py`).
- **Bugün AI:** Yok. **Beklenti/Öneri:** Model gerekmez (ayar ekranı). **Eksik:** —
## M27 Fuar, etkinlik ve ödül

Menü: Pazarlama › Etkinlik › «Fuar ve etkinlik» (1 öğe) · Rotalar: 6 (`/etkinlikler`, `/fuar/:id` [5 sekme], `/fuar/:id/sonuc`, `/crm`, `/oduller`, `/tip-eslemesi`) · Arka uç: `events.py`, `events_api.py`, `events_sources.py` · İhtiyaç: `M27-fuar-etkinlik-odul.md`.

### Takvim (`/etkinlikler`)
- **Ne yapıyor:** Yıl takvimi (ay şeridi), yaklaşanlar, ödül son tarihleri; satış ziyareti ve sınıflanmamış CRM kayıtları gizli (`EventsCalendar.tsx:13`).
- **Kim:** Etkinlik/fuar sorumlusu, pazarlama müdürü, yazar ilişkileri.
- **Bugün AI:** Yok (takvim onaylı tip sınıfını kullanır).
- **Beklenti:** «Bu yıl hangi fuarlara katılmalıyız?» (geçen yıl satış/gider); yazar programı çakışma uyarısı (kural — var).
- **Yapabileceklerimiz:** **Fuar katılım önerisi** · geçmiş fuar net satışı (Logo `SPECODE2='FUAR'`) + gider · kural sıralama (satış/gider) + gerekçe cümlesi · 3/5 · S (~2 gün) · karar insanda.

### Fuar kartı (`/etkinlikler/fuar/:id`) — sekmeler Özet · Kitaplar ve adetler · Görevler · Gider · Yazar programı
- **Ne yapıyor:** Fuar özeti; kitap-adet listesi; görevler; gider (fiş fotoğrafı); yazar programı ve çakışma (`FairCard.tsx:15`, `:127-131`, `FairOps.tsx:12`).
- **Bugün AI:** «Zeki AI önerisi» düğmesi kitap/adet listesini **kuralla** çıkarır (geçmiş fuar satışı × katsayı, yeni çıkanlar, stok — `FairBooks.tsx:11`, `events.suggest_books` `events.py:864`); model çağrısı yok. Diğer sekmelerde AI yok.
- **Beklenti:** Adet önerisine gerekçe cümlesi; stant/materyal brief'i; fuara özel set önerisi; gider fişinden tutar okuma.
- **Yapabileceklerimiz:**
  - **Adet satırı gerekçesi** (ihtiyaç §13) · `suggest_books` bileşenleri · model tek cümle + guard · 2/5 · S (~1 gün).
  - **Fuar seti önerisi** · M53 set önerisi hattı + fuar geçmişi · yeniden kullanım · 3/5 · S (~2 gün).
  - **Stant/materyal brief'i** · fuar bilgisi + öne çıkan kitaplar · taslak (M19 talebine düşer) · 2/5 · S.
  - **Gider fişi okuma (OCR)** · fiş fotoğrafı · belge okuma (tutar, tarih, satıcı) → form önerisi, insan onayı · 4/5 · M (~4 gün) · rakam fişte birebir görünmeli; ortak OCR yapı taşı.
- **Eksik:** —

### Fuar sonucu (`/etkinlikler/fuar/:id/sonuc`)
- **Ne yapıyor:** Fuar kanalı net satış (Logo faturalı satır), CRM fuar/imza siparişleri, gider, bütçe, geçen yıl karşılaştırması; yorum cümleleri **kuralla** yazılır (`FairResult.tsx:11`).
- **Bugün AI:** Yok (kural yorum).
- **Beklenti:** 5 cümle yorum ve gelecek yıl için öneri (ihtiyaç §13).
- **Yapabileceklerimiz:** **Sonuç yorumu + 3 öneri** · sonuç tablosu · launch_report deseni (tabloda olmayan sayı düşer) · 3/5 · S (~1 gün).

### CRM etkinlikleri (`/etkinlikler/crm`)
- **Ne yapıyor:** CRM etkinlikleri salt okunur; tarih, sınıf, metin süzgeci (`CrmEvents.tsx:11`).
- **Bugün AI:** Yok (sınıf tip eşlemesinden).
- **Beklenti:** Serbest açıklamadan yazar/kitap çıkarma; imza günü sonucu özeti.
- **Yapabileceklerimiz:** **Etkinlik açıklamasından kitap/yazar eşleme** · CRM etkinlik metni · aday + `choose` · 2/5 · S.

### Ödüller (`/etkinlikler/oduller`)
- **Ne yapıyor:** Ödül defteri (elle), başvurulan kitaplar, durum/sonuç; son tarih hatırlatması (`Awards.tsx:13`).
- **Bugün AI:** Yok.
- **Beklenti:** Koşul metnini okuyup kitabın uygunluğu; başvuru metni ve İngilizce özet taslağı.
- **Yapabileceklerimiz:** **Ödül uygunluğu** · ödül koşul metni + kitap künyesi (yayın yılı, tür, yazar uyruğu) · `choose` uygun/belirsiz/değil + gerekçe · 4/5 · S (~2 gün) · karar insanda. **Başvuru metni + İngilizce özet** · CRM tanıtım metni · taslak + guard · 3/5 · S (~2 gün).

### Tip eşlemesi (`/etkinlikler/tip-eslemesi`)
- **Ne yapıyor:** 371 CRM etkinlik tipinin fuar/imza/söyleşi/okul/satış ziyareti/diğer sınıfı; insan karar verir (`TypeMap.tsx:11`).
- **Bugün AI:** Var. `classify_types` kapalı küme `choose` + olasılık (`events.py:1201`, `events_api.py:177`).
- **Beklenti:** Karşılandı. **Öneri:** yeni tip gelince otomatik öneri kuyruğu (gece) · 1/5 · S. **Eksik:** —

## M28 Kurumsal ilişkiler (kanaat önderleri, kurumlar, kamu projeleri)

Menü: Pazarlama › İlişkiler › «Kurumsal ilişkiler» (1 öğe) · Rotalar: 7 (`/kurumsal-iliskiler`, `/kisiler`, `/kisi/:id`, `/kurumlar`, `/hediye`, `/projeler` [`?proje=` kartı], `/rapor`) · Arka uç: `public_affairs.py`, `public_affairs_api.py`, `public_affairs_docs.py`, `public_affairs_sources.py`, `public_affairs_criteria.json` · İhtiyaç: `M28-kanaat-onderleri-kurumsal-iliskiler.md`.

### Bugün (`/kurumsal-iliskiler`)
- **Ne yapıyor:** Temas zamanı gelen kişiler, açık projeler (aşama), bu ayın hediye programı (`PaHome.tsx:13`).
- **Kim:** Kurumsal ilişkiler sorumlusu, genel müdür/yönetim.
- **Bugün AI:** Yok.
- **Beklenti:** «Bu hafta kimi aramalıyım, neden?» kısa gerekçe.
- **Yapabileceklerimiz:** **Temas önceliği gerekçesi** · son temas, ısı, yeni kitap ↔ alan eşleşmesi · kural + tek cümle · 2/5 · S (~1 gün) · kişi adı modele gitmez; alan/kurum türü gider.

### Kişiler (`/kurumsal-iliskiler/kisiler`)
- **Ne yapıyor:** Alan, öncelik, temas zamanına göre süzülen liste; «Hepsi / Temas zamanı gelen / Benim ilişkilerim» (`PaPeople.tsx:13-18`).
- **Bugün AI:** Yok (listede). **Beklenti:** Alanı boş kişiler için toplu öneri. **Öneri:** bkz. kişi kartı alan önerisinin gece toplu çalıştırılması · 2/5 · S.

### Kişi kartı (`/kurumsal-iliskiler/kisi/:id`)
- **Ne yapıyor:** Kim, kurum, alan, ilişki sahibi, ısı; temas notları; giden kitaplar; aynı kitap iki kez engelli (`PaPersonCard.tsx:15`).
- **Bugün AI:** Var. Alan önerisi onaylı listeden `choose` + olasılık (`public_affairs_api.py:310-325`, `forms.tsx:404`); inanç/siyaset sınıfı listede yok (ihtiyaç).
- **Beklenti:** Temas notlarının özeti; bir sonraki temas için konu önerisi.
- **Yapabileceklerimiz:** **Temas geçmişi özeti** · portal temas notları · özet · 2/5 · S · notlar hassas olabilir: yalnız yetkiliye, modele kişi adı maskeli.

### Kurumlar (`/kurumsal-iliskiler/kurumlar`)
- **Ne yapıyor:** MEB, okul, üniversite, belediye… (CRM ziyaret yerleri) + elle kurumlar; il × kurum tipi, öğrenci toplamı (`PaOrgs.tsx:14`, `:95`).
- **Bugün AI:** Yok.
- **Beklenti:** «Hangi ilde öğrenci sayısı yüksek ama temas az?»; kurum türü sınıflama (elle girilen adlardan).
- **Yapabileceklerimiz:** **Kurum türü sınıflama** · kurum adı · kural (anahtar sözcük) + `choose` · 2/5 · S. **Fırsat haritası yorumu** · il × kurum tablosu · yorum · 2/5 · S.

### Hediye programı (`/kurumsal-iliskiler/hediye`)
- **Ne yapıyor:** Ay ay kitap × kişi listesi, gerekçe ve kişisel not, yönetim/hukuk onayı, CRM tanıtım siparişinden gönderim durumu; «kitap → kime gönderelim» kural puanı + gerekçe (`PaGifts.tsx:14`, `:266`).
- **Bugün AI:** Var. Kişisel not taslağı `llm.chat` (`public_affairs_api.py:589-601`).
- **Beklenti:** Kitap-kişi eşleştirmesinin gerekçesi (ihtiyaç: model gerekçe cümlesi — koddaki gerekçe kural mı model mi doğrulanmadı).
- **Yapabileceklerimiz:** **Eşleştirme gerekçe cümlesi** · puan bileşenleri · model + guard · 2/5 · S (~1 gün). **Kamu görevlisi hediye sınırı denetimi** · kişi kurum türü + kitap liste fiyatı · kural (hukuk eşiği) · 3/5 · S · model gerekmez.

### Kamu projeleri (`/kurumsal-iliskiler/projeler`, `?proje=`)
- **Ne yapıyor:** Fikir → ön görüşme → teklif → kurum onayı → uygulama → rapor → kapandı panosu; proje kartında kitap listesi, hedef kurumlar, bütçe onayı, Zeki AI teklif dosyası, CRM erişim raporu (`PaProjects.tsx:15-17`).
- **Bugün AI:** Var. Teklif dosyası bölümleri `llm.chat` (`public_affairs_api.py:696-703`); MEB ölçüt maddeleri `public_affairs_criteria.json`'dan aynen.
- **Beklenti:** Kurumdan gelen şartname/yazıyı okuyup gereksinim listesi çıkarma; MEB ölçütüne uygunluk kontrol listesi.
- **Yapabileceklerimiz:** **Şartname/yazı okuma** · yüklenen PDF · belge okuma + madde çıkarımı (M39 `extract_page` deseni `pazar.py:1352`) · 4/5 · M (~4 gün) · her madde sayfa numarasıyla, insan onayı. **Ölçüt uygunluk listesi** · kitap künyesi × `public_affairs_criteria.json` · `choose` uygun/belirsiz/değil · 3/5 · S.

### Etki raporu (`/kurumsal-iliskiler/rapor`)
- **Ne yapıyor:** Temas, hediye programı, CRM tanıtım/bağış siparişleri, projeler ve erişim; PDF; alan listesi yönetimi (`PaReport.tsx:11`).
- **Bugün AI:** Yok (doğrulanmadı: rapor yorumu kodda bulunamadı).
- **Beklenti:** Rapor yorumu; yansıma/paylaşımda TİMAŞ bahsi ve tonu (ihtiyaç «sonraki»).
- **Yapabileceklerimiz:** **Rapor yorumu** (guard) · 2/5 · S. **Bahsedilme tonu** · M20 `classify_tone` yeniden kullanım · 2/5 · S.
- **Eksik:** —

## M36 Dijital yayın (e-kitap, sesli kitap)

Menü: Editoryal › Yayına hazırlık › «Dijital yayın», «Dijital satış» (2 öğe; kapsam gereği bu grupta) · Rotalar: 4 (`/dijital-yayin` [4 sekme], `/dijital-yayin/kitap/:id`, `/dijital-yayin/firsatlar` [2 sekme], `/dijital-yayin/satis` [2 sekme]) · Arka uç: `dijital.py`, `dijital_api.py`, `dijital_sources.py` · İhtiyaç: `M36-dijital-yayin-ekitap.md`.

### Katalog › Katalog / Hak riski / CRM'e işlenecek / Platformlar (`/dijital-yayin?sekme=…`)
- **Ne yapıyor:** Kitap başına e-kitap/sesli hak, e-ISBN, e-kitap dosyası, platform durumu; hak riski ve telif kararı; CRM'e işlenecekler; platform tanımları (`DigitalCatalog.tsx:14-21`, `PlatformsTab.tsx:10`).
- **Kim:** Dijital yayın sorumlusu, telif/sözleşme birimi, e-ticaret.
- **Bugün AI:** Var. Sözleşme hak notu ön okuması `read_notes` → `choose` «dijitali kısıtlıyor / kısıtlamıyor / belirsiz» + olasılık (`dijital.py:856-877`); karar telif biriminde.
- **Beklenti:** Sözleşme metninden (PDF) dijital hak maddesi bulma; «e-kitap hakkı olup e-kitabı olmayan romanlar?».
- **Yapabileceklerimiz:** **Sözleşme PDF'inden dijital hak maddesi** · M54 sözleşme belgeleri (`contracts_docs.py`) · belge okuma + madde alıntısı + `choose` · 4/5 · M (~4 gün) · alıntı birebir, karar telifte.
- **Eksik:** —

### Kitap ayrıntısı (`/dijital-yayin/kitap/:id`)
- **Ne yapıyor:** Kimlik alanları, sözleşme ve hak bayrakları, telif kararı, e-kitap dosyası (CRM + stüdyo), platform geçmişi, dijital fiyat kararı, dijital satış (`DigitalTitleDrawer.tsx:11`, not okuma gösterimi `:131`).
- **Bugün AI:** Not ön okumasının sonucu gösteriliyor (yukarıda).
- **Beklenti:** Platform tanıtım metni taslağı (ihtiyaç §13); dijital fiyat önerisi.
- **Yapabileceklerimiz:** **Platform tanıtım metni** · CRM tanıtım metni · taslak + guard · 3/5 · S (~1 gün). **Dijital fiyat bandı** · basılı fiyat + platform geçmiş fiyatları · kural (oran bandı), model yok · 2/5 · S.

### Fırsatlar › E-kitap fırsatları / Sesli kitap adayları (`/dijital-yayin/firsatlar`)
- **Ne yapıyor:** Hakkı olan, basılıda iyi satan, dijitali olmayan kitaplar; sesli kitap adayları; sıra son 12 ay basılı net adet; CSV (`OpportunitiesScreen.tsx:12-17`).
- **Bugün AI:** Yok.
- **Beklenti:** Fırsat puanına gerekçe cümlesi (ihtiyaç); sesli kitaba uygunluk (diyalog yoğunluğu, tür).
- **Yapabileceklerimiz:** **Sesli kitap uygunluğu** · stüdyodaki kitap metni (varsa) + tür · kural (tür) + `choose` «sesli kitaba uygun mu» · 3/5 · S (~2 gün). **Satır gerekçesi** · 2/5 · S. Editör stüdyosunun seslendirme (`editorial_studio_narration.py`) ile bağlantı — doğrulanmadı.

### Dijital satış › Pano / Raporlar (`/dijital-yayin/satis`)
- **Ne yapıyor:** Onaylı platform raporlarından aylık gelir, platform/kitap kırılımı, eşleşmeyen satırlar, Logo e-kitap faturaları (ayrı), rapor yükleme sihirbazı (`DigitalSalesScreen.tsx:13-19`, `ImportWizard.tsx:11`).
- **Bugün AI:** Var. Kurallı eşleşmeyen rapor satırına aday kitap `suggest_matches` → `choose` + olasılık (`dijital.py:1711-1734`); kişisel kolonlar atılır.
- **Beklenti:** Farklı platform dosya biçimini tanıma; gelir sapması uyarısı (rapor gecikti/düştü).
- **Yapabileceklerimiz:** **Kolon eşleme** (M21 `model_mapping` ortak yapı taşı) · 3/5 · S. **Gelir anomalisi** · aylık platform geliri · kural (±%X) + tek cümle · 2/5 · S.
- **Eksik:** Sesli kitap satış verisi kaynağı doğrulanmadı.

## M39 Pazar araştırması ve rekabet

Menü: Analiz › «Pazar ve rakip», «Rakipler ve emsal», «Sektör raporları» (3 öğe; kapsam gereği bu grupta) · Rotalar: 4 (`/pazar-arastirma`, `/pazar-arastirma/:section` = rakipler · emsal · kategori-esleme · raporlar, `/pazar-arastirma/raporlar/:id`, `/pazar-arastirma/ozet/:donem`) · Arka uç: `pazar.py`, `pazar_api.py`, `pazar_sources.py` · İhtiyaç: `M39-pazar-arastirma-rekabet.md`.

### Özet (`/pazar-arastirma`)
- **Ne yapıyor:** Onaylı yönetim özeti, TİMAŞ iç göstergeleri (Logo sell-in), onaylı sektör rakamları, eşleme kapsamı (`MarketHome.tsx:13`).
- **Kim:** Genel müdür/DYK, pazarlama müdürü, strateji.
- **Bugün AI:** Özetin kendisi Zeki AI taslağı (aşağıda); bu ekran okur.
- **Beklenti:** «Bu çeyrekte kategorimizde ne değişti?»; TİMAŞ kategori büyümesinin sektörle karşılaştırması.
- **Yapabileceklerimiz:** **Soru kutusu (pazar bağlamı)** · onaylı rakamlar + katalog ölçüleri · sohbet hattı · 3/5 · S.

### Rakipler (`/pazar-arastirma/rakipler`)
- **Ne yapıyor:** Yayınevi × kategori fiyat/sayfa/format matrisi, izlenen rakipler, yayınevi kayıtları; yalnız onaylı eşlemeler sayılır (`CompetitorMatrix.tsx:11`).
- **Bugün AI:** Yok (matris kural).
- **Beklenti:** Rakibin yeni çıkışları özeti; fiyat konumlaması yorumu.
- **Yapabileceklerimiz:** **Rakip dönem özeti** · CRM «Rakip Kitap» anlık görüntü farkı · kural fark + yorum (rakam guard) · 3/5 · S (~2 gün) · veri tazeliği şeridi korunur.

### Emsal bul (`/pazar-arastirma/emsal`)
- **Ne yapıyor:** Kitap adı/konu → rakip ve TİMAŞ emsalleri; kurallı süzgeç + ortak sözcük; ilk adaylar Zeki AI «çok benzer/kısmen/benzemiyor» (`ComparablesScreen.tsx:10`, `pazar.comparables` `pazar.py:978`).
- **Bugün AI:** Var. Aday başına kapalı küme `choose` (`pazar.py:11-14`, `pazar_api.py:109`).
- **Beklenti:** Aynı hattın M15 plan ekranında emsal önerisi olarak kullanılması.
- **Yapabileceklerimiz:** **Gömme ile aday genişletme** · CRM özet metinleri · benzerlik araması ortak yapı taşı · 4/5 · M (~4 gün) · M15 emsal önerisi aynı hattı kullanır.

### Kategori eşlemesi (`/pazar-arastirma/kategori-esleme`)
- **Ne yapıyor:** Rakip serbest kategori → TİMAŞ kategorisi; ad eşleşmesi, sonra Zeki AI; sekmeler Öneri/Emin değil/Öneri bekliyor/Onaylı/Karşılığı yok (`CategoryMap.tsx:11-18`).
- **Bugün AI:** Var. `suggest_mapping` `choose` + olasılık (`pazar.py:706`).
- **Beklenti:** Karşılandı. **Öneri:** H1 kategori ağacıyla tek sözlük (tekrar eden eşleme yapı taşı) · 2/5 · S. **Eksik:** —

### Sektör raporları (`/pazar-arastirma/raporlar`) ve rapor rakamları (`/pazar-arastirma/raporlar/:id`)
- **Ne yapıyor:** PDF/Excel/CSV yükleme, sayfa sayfa rakam çıkarımı, onay/düzelt/reddet; sayfa numarası ve alıntı (`ReportsScreen.tsx:12`, `ReportFigures.tsx:12`).
- **Bugün AI:** Var. `extract_page` sayfa metninden gösterge/değer/birim (`pazar.py:1352`, `llm.chat` temperature 0 `pazar_api.py:115`); metinde birebir geçmeyen rakam atılır.
- **Beklenti:** Taranmış (görüntü) PDF; tablo yapısını koruma; dönemler arası aynı göstergeyi birleştirme.
- **Yapabileceklerimiz:** **Taranmış sayfa için OCR** · görüntü PDF · OCR + aynı birebir denetim · 3/5 · M (~3 gün) · ortak OCR yapı taşı. **Gösterge adı normalleştirme** · onaylı göstergeler · `choose` mevcut göstergelerden biri/yeni · 3/5 · S.

### Aylık yönetim özeti (`/pazar-arastirma/ozet/:donem`)
- **Ne yapıyor:** DYK'ya aylık özet; her madde kaynağa [Kn] bağlı, sayı kaynakla tutmazsa madde düşer; onay yönetimde, yazan onaylayamaz (`BriefEditor.tsx:12`, `draft_brief` `pazar.py:1738`, `check_brief` `pazar.py:1704`).
- **Bugün AI:** Var (yukarıda).
- **Beklenti:** Karşılandı; sunum çıktısı.
- **Yapabileceklerimiz:** **Kurul sunum sayfası** · onaylı özet · şablon (model yok) · 1/5 · S.
- **Eksik:** Dış tarama (çok satan listeleri, arama eğilimi) bilinçli olarak yok; pazar büyüklüğü yalnız yüklenen rapordan.
## H2 Okur veri tabanı

Menü: Pazarlama › Okur ve müşteri › «Okurlar» (1 öğe) · Rotalar: 3 kalıp (`/okurlar`, `/okurlar/kisi/:id`, `/okurlar/:section/*`) = 7 bölüm (Özet, `/ara`, `/birlestirme`, `/segmentler` [+`/yeni`, `/:id`], `/yuklemeler`, `/disa-aktarimlar`, `/kvkk`) + okur kartı · Arka uç: `readers.py`, `readers_api.py`, `readers_imports.py`, `readers_segments.py`, `readers_sources.py` · İhtiyaç: `H2-okuyucu-veri-tabani.md`.

### Özet (`/okurlar`)
- **Ne yapıyor:** Tekil okur, kaynak kırılımı, kanal başına izin ve ulaşılabilir kitle, kaynak tazeliği; yalnız sayı (`ReadersHome.tsx:8`).
- **Kim:** CRM/okur ekibi, pazarlama müdürü, KVKK sorumlusu.
- **Bugün AI:** Yok.
- **Beklenti:** Aylık okur tabanı raporu yorumu (ihtiyaç §13); «izinli okur sayısı neden düştü?».
- **Yapabileceklerimiz:** **Aylık yorum** · özet sayıları (SQL) · yorum + guard · 2/5 · S (~1 gün) · kişi verisi yok.

### Okur ara (`/okurlar/ara`)
- **Ne yapıyor:** E-posta/telefon/okur no ile kesin arama; ada göre yalnız kişisel veri yetkisiyle (`ReaderSearch.tsx:10`).
- **Bugün AI:** Yok. **Beklenti/Öneri:** Model uygun değil (kişisel veri) — AI önerilmez. **Eksik:** —

### Birleştirme (`/okurlar/birlestirme`)
- **Ne yapıyor:** Adı ve ili aynı, e-posta/telefonu farklı okur çiftleri; karar insanın (`MergeQueue.tsx:17`).
- **Bugün AI:** Yok (skor kural).
- **Beklenti:** Çiftin aynı kişi olma olasılığı.
- **Yapabileceklerimiz:** **Özellik özeti üzerinden aynı/farklı/belirsiz** · kişisel veri olmadan benzerlik bayrakları (aynı il, e-posta alan adı aynı mı, kaynak) · `choose` + olasılık; ya da yalnız skor (ihtiyaç iki seçeneği de açık bırakıyor) · 2/5 · S (~2 gün) · model ham ad/e-posta görmez; insan karar verir.

### Segmentler (`/okurlar/segmentler`, `/segmentler/yeni`, `/segmentler/:id`)
- **Ne yapıyor:** Kural + anlık büyüklük (toplam/e-posta/SMS), Zeki AI taslağı, onay, izin denetimli dışa aktarım (`SegmentBuilder.tsx:17`, `Segments.tsx:19`).
- **Bugün AI:** Var. Doğal dil → segment kural JSON taslağı `/segments/draft-from-text` (`readers_api.py:314-322`, temperature 0); modelden atılan kurallar notla gösterilir (`SegmentBuilder.tsx:104-105`). Modele kişisel veri gitmez.
- **Beklenti:** Kuralı okunur cümleye çevirme (ihtiyaç §13); ilgi alanı serbest metnini H1 düğümüne eşleme.
- **Yapabileceklerimiz:** **Kural → cümle** · segment JSON · şablon (deterministik) tercih; model gerekmez · 2/5 · S. **İlgi alanı → H1 düğümü** · okur ilgi alanı etiket adları (kişi değil) · `choose` kapalı küme + olasılık · 3/5 · S (~2 gün).

### Yüklemeler (`/okurlar/yuklemeler`)
- **Ne yapıyor:** Etkinlik/fuar katılımcı dosyası: yükle → kolon eşle → eşleştir (eşleşti/yeni/geçersiz/izin eksik) (`Imports.tsx:12`).
- **Bugün AI:** Yok (kolon eşleme elle — doğrulanmadı model var mı: `readers_imports.py`'de model çağrısı bulunamadı).
- **Beklenti:** Kolonları otomatik tanıma; izin metni sütununu yorumlama.
- **Yapabileceklerimiz:** **Kolon eşleme** · yalnız başlıklar ve maskeli örnek (kişisel değer yerine biçim: «e-posta biçimli») · M21 `model_mapping` yapı taşı · 3/5 · S (~1 gün) · örnek değerler maskeli gider.

### Dışa aktarımlar (`/okurlar/disa-aktarimlar`)
- **Ne yapıyor:** Dışa aktarım günlüğü: kim, ne zaman, segment, kanal, kaç kişi, amaç (`Exports.tsx:9`).
- **Bugün AI:** Yok. **Beklenti:** Olağandışı aktarım uyarısı. **Öneri:** **Anomali** · günlük (kişi başı hacim, saat) · kural eşik, model yok · 2/5 · S · M49 veri güvenliğine bildirim.

### KVKK başvurusu (`/okurlar/kvkk`)
- **Ne yapıyor:** Bir e-posta/telefona ait bütün okur kayıtları, izinler, listeler, yüklemeler (`SubjectRequest.tsx:10`).
- **Bugün AI:** Yok. **Beklenti:** Başvuru cevap yazısı taslağı. **Öneri:** **Cevap yazısı şablonu** · bulunan kayıt sayıları (kişi verisi modele gitmez; şablon kodda doldurulur) · şablon, model gerekmez · 2/5 · S.

### Okur kartı (`/okurlar/kisi/:id`)
- **Ne yapıyor:** Kaynaklar, izinler (kaynak+tarih), ilgi alanları, zaman çizelgesi; kişisel veri yalnız yetkiyle (`ReaderCard.tsx:17`).
- **Bugün AI:** Yok. **Beklenti/Öneri:** Kişi düzeyinde model kullanımı KVKK nedeniyle önerilmez; yalnız ilgi alanı H1 eşlemesinin sonucu gösterilir. **Eksik:** —

## H3 E-ticaret müşterileri

Menü: Pazarlama › Okur ve müşteri › «E-ticaret müşterileri» (1 öğe) · Rotalar: 3 kalıp (`/eticaret-musteri`, `/eticaret-musteri/musteri/:key`, `/eticaret-musteri/:section/*`) = 6 bölüm (Özet, `/musteriler`, `/tetikler`, `/kampanyalar`, `/huni`, `/veri`) + müşteri kartı · Arka uç: `commerce.py`, `commerce_api.py`, `commerce_sources.py` · İhtiyaç: `H3-eticaret-musteri-yonetimi.md`.

### Özet (`/eticaret-musteri`)
- **Ne yapıyor:** Sabah özeti: sipariş, site cirosu, sepet, yeni/tekrar müşteri; Logo kanal cirosuyla uzlaşma; en çok satan 10 (`CommerceHome.tsx:17`).
- **Kim:** E-ticaret yöneticisi (sabah telefonda), CRM ekibi.
- **Bugün AI:** Yok (e-posta özeti `summary_text` kural, `commerce.py:1756`).
- **Beklenti:** Uzlaşma farkının yorum cümlesi (ihtiyaç §13); «dün neden ciro düştü?».
- **Yapabileceklerimiz:** **Günlük fark ve değişim yorumu** · özet + uzlaşma rakamları · yorum + guard · 3/5 · S (~1 gün).

### Müşteriler / RFM (`/eticaret-musteri/musteriler`)
- **Ne yapıyor:** RFM matrisi, segment büyüklüğü ve geçişleri; maskeli müşteri listesi (`Customers.tsx:10`, `rfm` `commerce.py:837`).
- **Bugün AI:** Yok.
- **Beklenti:** Segment başına kitap önerisi (ihtiyaç §13: aday SQL'den, model gerekçe + tanıtım metni); kayıp riski.
- **Yapabileceklerimiz:** **Segment başına kitap önerisi** · segmentin aldığı H1 düğümlerinde çok satan, henüz almadığı · SQL aday + model gerekçe/tanıtım · 4/5 · M (~3 gün) · segment düzeyinde, kişi düzeyinde değil. **Kayıp olasılığı** · RFM geçiş geçmişi · kural (geçiş olasılığı tablosu), model yok · 3/5 · S.

### Tetikler (`/eticaret-musteri/tetikler`)
- **Ne yapıyor:** Kural (yeni kitap, geri kazanım, ikinci sipariş), önizleme (sayı), kontrol grubu, onay (yazan onaylayamaz), izin denetimli dışa aktarım (`Triggers.tsx:15`).
- **Bugün AI:** Yok.
- **Beklenti:** Yeni kitap tetiğinde kitabın H1 düğümü yoksa kapalı küme seçim (ihtiyaç); tetik mesajı taslağı.
- **Yapabileceklerimiz:** **Yeni kitap → H1 düğümü** · CRM kitap kartı · `choose` · 3/5 · S (~1 gün). **Tetik mesajı taslağı** (e-posta metni; gönderim yok, dışa aktarım + insan) · 3/5 · S · guard.

### Kampanya sonuçları (`/eticaret-musteri/kampanyalar`)
- **Ne yapıyor:** Hedef ve kontrol grubunun pencere içi site siparişi; dönüşüm farkı ve güven aralığı (`Campaigns.tsx:10`).
- **Bugün AI:** Var. `comment_campaign` sonuç yorumu (`commerce.py:1558-1572`, `llm_for("commerce", NORMAL)`).
- **Beklenti:** Karşılandı; «sonraki kampanyada neyi değiştirelim» önerisi.
- **Yapabileceklerimiz:** **Öğrenim kaydı** (M35 öğrenimlerine bağlama) · 2/5 · S.

### Ürün hunisi (`/eticaret-musteri/huni`)
- **Ne yapıyor:** Sitede görüntülenme (gece farkı) ↔ geçerli site satışı; çok görüntülenip az satanlar (`Funnel.tsx:10`).
- **Bugün AI:** Yok. **Öneri:** bkz. M34 Huni (aynı soru; tek yapı taşında birleştirilmeli). **Eksik:** M34 `/e-ticaret/huni` ile iki ayrı huni ekranı var — tekrar.

### Veri ve eşikler (`/eticaret-musteri/veri`)
- **Ne yapıyor:** T-soft okuma tazeliği, alanların bulunma ölçümü, eksik alanlar; RFM ve kampanya eşikleri (`DataSettings.tsx:11`).
- **Bugün AI:** Yok. **Beklenti/Öneri:** Model gerekmez (ayar ekranı). **Eksik:** —

### Müşteri kartı (`/eticaret-musteri/musteri/:key`)
- **Ne yapıyor:** Bütün siparişler ve iadeler, segment geçişleri, aldığı kategoriler, izin (`CustomerCard.tsx:15`).
- **Bugün AI:** Yok. **Beklenti:** «Bu müşteriye ne önerelim?». **Öneri:** **Kişiye öneri kural tabanlı** (aldığı kategorilerde çok satan) · model yok ya da yalnız kitap listesine gerekçe (kişi verisi gitmez) · 2/5 · S. **Eksik:** —

## M37 Okur topluluğu

Menü: Pazarlama › Okur ve müşteri › «Okur kitlesi», «Okur segmentleri», «Topluluk programları», «Yorum cevapları» (4 öğe) · Rotalar: 4 · Arka uç: `okur.py`, `okur_api.py`, `okur_sources.py` · İhtiyaç: `M37-okur-toplulugu.md`.

### Okur kitlesi (`/okur-toplulugu`)
- **Ne yapıyor:** Kaynak/kayıt tipine göre okur sayısı, KVKK/İYS/kanal izin oranları, çelişkiler, aylık eğilim, yaklaşan programlar; kişi adı yok (`AudienceScreen.tsx:10`).
- **Kim:** CRM/okur ekibi, pazarlama müdürü.
- **Bugün AI:** Yok (e-posta özeti `summary_text` kural, `okur.py:1046`).
- **Beklenti:** «Okur mu, kurum mu?» belirsiz kayıt ayrımı (ihtiyaç: rol/kaynak alanlarıyla kapalı küme); izin çelişkisi açıklaması.
- **Yapabileceklerimiz:** **Belirsiz kayıt türü** · yalnız rol/kaynak alanları · `choose` okur/kurum/katkıcı/belirsiz · 2/5 · S (~2 gün) · ad/e-posta gitmez.

### Okur segmentleri (`/okur-toplulugu/segmentler`)
- **Ne yapıyor:** Kural → anlık büyüklük → amaç/süre/kanal → KVKK onayı; ilgi alanlarının özel nitelikli çağrışım işareti ayrı sekmede (`SegmentsScreen.tsx:16-18`).
- **Bugün AI:** Var. İlgi alanı adının özel nitelikli çağrışımı `classify_interest` `choose` + yüksek eşik (0,90) (`okur.py:461-507`); son karar hukukta.
- **Beklenti:** Programa uygun segment kuralı önerisi (ihtiyaç §13).
- **Yapabileceklerimiz:** **Programdan segment önerisi** · program türü/konusu + ilgi alanları · H2 `draft-from-text` hattının yeniden kullanımı · 3/5 · S (~1 gün).

### Topluluk programları (`/okur-toplulugu/programlar`)
- **Ne yapıyor:** Okuma kulübü, imza günü, anket, çevrim içi etkinlik takvimi; Zeki AI duyuru taslağı (gönderilmez, kopyalanır); CRM geçmiş etkinlik katılım/satış özeti (`ProgramsScreen.tsx:16`).
- **Bugün AI:** Var. Duyuru/davet taslağı `m.chat` (`okur_api.py:380-395`).
- **Beklenti:** Etkinlik özeti cümlesi; okuma kulübü için tartışma soruları.
- **Yapabileceklerimiz:** **Okuma kulübü tartışma soruları** · kitap tanıtım metni (+ stüdyo metni varsa) · taslak · 3/5 · S (~1 gün). **Etkinlik sonrası özet** · katılım/satış sayıları · yorum + guard · 2/5 · S.

### Yorum cevapları (`/okur-toplulugu/yorumlar`)
- **Ne yapıyor:** Sitedeki okur yorumları (anlık, yorumcu adı yok, e-posta/telefon gizli), Zeki AI cevap taslağı, «cevaplandı» işareti; cevap sitede elle girilir (`ReviewsScreen.tsx:12`).
- **Bugün AI:** Var. Cevap taslağı `m.chat` (`okur_api.py:455`), yorum metni saklanmaz.
- **Beklenti:** Önceliklendirme (şikâyet/kargo önce); yorumdan ürün sorunu (baskı hatası) çıkarma.
- **Yapabileceklerimiz:** **Yorum sınıflama** · yorum metni (maskeli) · `choose` kargo-sipariş/baskı-kalite/içerik/övgü/soru · 4/5 · S (~2 gün) · baskı hatası M52/üretime, kargo M51'e yönlendirme önerisi (gönderim yok). Aynı yapı taşı M40 Trendyol soru/yorum ve M22 yorumlarında.
- **Eksik:** —

## M34 E-ticaret ve platform

Menü: Pazarlama › E-ticaret › «Platform durumu», «Farklar», «Huni», «Pazar yerleri» (4 öğe) · Rotalar: 4 · Arka uç: `eticaret.py`, `eticaret_api.py`, `eticaret_sources.py`; kart önerisi SEO modülüne (`seo_geo/propose.py`) · İhtiyaç: `M34-eticaret-platform.md`.

### Platform durumu (`/e-ticaret`)
- **Ne yapıyor:** 4 gösterge (kaynak ve kesim tarihiyle), bugün bakılacaklar, türe göre açık farklar, onay bekleyen Zeki AI kart önerileri, son okuma durumu (`EticaretHome.tsx:13`, `:52`).
- **Kim:** E-ticaret yöneticisi, ürün/katalog sorumlusu.
- **Bugün AI:** Var (dolaylı): onay bekleyen kart önerileri listelenir.
- **Beklenti:** «Bugün önce hangi farkı çözmeliyim?» — satış kaybı büyüklüğüne göre sıra.
- **Yapabileceklerimiz:** **Fark önceliği** · fark türü × son 30 gün satış × görüntülenme · kural puan + tek cümle · 3/5 · S (~1 gün).

### Farklar (`/e-ticaret/farklar`)
- **Ne yapıyor:** Kitap × fark (fiyat, stok, aktiflik, barkod, kart) CRM/Logo/site yan yana; toplu işaret; içerik paketi (`DiffsScreen.tsx:13`); kitap çekmecesi (`ItemDrawer.tsx:14`).
- **Bugün AI:** Var. Fiyat farkı nedeni kapalı küme «kampanya/fiyat güncellemesi/veri hatası/belirsiz» `classify_reasons` (`eticaret.py:172`, `:1080-1095`, BATCH `eticaret_api.py:198`); kart içerik önerisi `make_proposal` → `seo_propose.suggest` → SEO öneri kuyruğu (`eticaret_api.py:291-321`), T-soft'a yazılmaz.
- **Beklenti:** Neden sınıfının genişletilmesi (stok farkı nedeni: rezerve, depo gecikmesi); barkod farkında doğru değeri önerme.
- **Yapabileceklerimiz:** **Stok farkı nedeni** · T-soft stok + Logo depo + açık sipariş · kural öncelikli, belirsizde `choose` · 3/5 · S (~2 gün). **Doğru değer önerisi (barkod/ISBN)** · CRM/Logo/site üç değer + ISBN sağlama toplamı · kural, model gerekmez · 3/5 · S.

### Huni (`/e-ticaret/huni`)
- **Ne yapıyor:** Görüntülenme → satış; düşük dönüşüm; olası nedenler kurallı (kart doluluğu, yorum, stok, fiyat) (`FunnelScreen.tsx:12`).
- **Bugün AI:** Neden kurallı; kart önerisine yönlendirir (`FunnelScreen.tsx:19`).
- **Beklenti:** «Neden az satıyor olabilir» kısa yorum (ihtiyaç §13).
- **Yapabileceklerimiz:** **Kitap başına yorum** · kural nedenleri + rakip fiyat (M39) · yorum + guard · 2/5 · S (~1 gün). H3 hunisiyle birleştirme önerilir.

### Pazar yerleri (`/e-ticaret/pazar-yerleri`)
- **Ne yapıyor:** Logo pazar yeri carilerine satış (sell-in), iade, geçen yıl; cari başına kitap kırılımı; tükenme riski; içerik paketi (`MarketplacesScreen.tsx:13`).
- **Bugün AI:** Yok.
- **Beklenti:** Tükenme tarihi tahmini; iade artışı uyarısı.
- **Yapabileceklerimiz:** **Tükenme tahmini** · cari × kitap haftalık sell-in + stok · zaman serisi tahmini (sunucudaki tahmin servisi) · 3/5 · M (~3 gün) · M40/M42 ile ortak. **İade anomalisi** · kural · 2/5 · S.
- **Eksik:** Sell-through yok (ekranda belirtilmiş); M40/M42 ile ekran tekrarı var.

## M35 E-ticaret kampanyaları

Menü: Pazarlama › E-ticaret › «Kampanyalar» (1 öğe) · Rotalar: 4 (`/kampanyalar` [sekmeler Kampanyalar · Takvim · Aday kitaplar · CRM bayi kampanyaları · Öğrenimler], `/kampanyalar/takvim`, `/kampanyalar/adaylar`, `/kampanyalar/:id`) · Arka uç: `kampanya.py`, `kampanya_api.py`, `kampanya_sources.py` · İhtiyaç: `M35-eticaret-kampanya.md`.

### Kampanyalar (kayıt defteri) (`/kampanyalar`)
- **Ne yapıyor:** Site, pazar yeri, bayi, fuar kampanyaları; durum, onay (`CampaignsScreen.tsx:16-23`).
- **Kim:** Kampanya/fiyat sorumlusu, e-ticaret yöneticisi, pazarlama müdürü.
- **Bugün AI:** Listede yok.
- **Beklenti:** «Bu ay kaç kampanya marj altına düştü?» soru hattı.
- **Yapabileceklerimiz:** bkz. ortak soru hattı; ek model işi yok (1/5).

### Takvim (`/kampanyalar/takvim`)
- **Ne yapıyor:** Özel günler, platform dönemleri, fuarlar, kampanyalar ve çakışmalar (`parts.tsx:84`).
- **Bugün AI:** Yok. **Beklenti:** Çakışma çözümü. **Öneri:** M18 çakışma önerisiyle aynı yapı taşı · 2/5 · S.

### Aday kitaplar (`/kampanyalar/adaylar`)
- **Ne yapıyor:** Kural süzgeci (stok fazlası, yavaşlama, sezon; hak, maliyet, marj) ve rakamlı gerekçe (`CandidatesPanel.tsx:10`).
- **Bugün AI:** Yok (gerekçe kural).
- **Beklenti:** Gerekçenin okunur cümle olması; indirim oranı önerisi.
- **Yapabileceklerimiz:** **İndirim oranı önerisi** · geçmiş kampanya öğrenimleri (fiyat esnekliği, kitap/kategori) · kural (geçmiş etki medyanı) + model gerekçe · 4/5 · M (~4 gün) · marj/telif/asgari fiyat simülasyonu zorunlu, karar insanda.

### CRM bayi kampanyaları (`?sekme=bayi`)
- **Ne yapıyor:** CRM bayi kampanyaları; tür kurallı ya da Zeki AI (`CampaignsScreen.tsx:467`).
- **Bugün AI:** Var. Tür kapalı küme `CRM_TYPE_PROMPT` + `choose` (`kampanya.py:1750`), olasılık/marj eşiği ayarda.
- **Beklenti:** Karşılandı. **Öneri:** —.

### Öğrenimler (`?sekme=ogrenim`)
- **Ne yapıyor:** Kapanan kampanyalardan öğrenim kayıtları.
- **Bugün AI:** Dolaylı (sonuç özetinden). **Beklenti:** «Geçen yıl öğretmenler gününde ne işe yaradı?» araması. **Öneri:** **Öğrenim araması** · öğrenim metinleri · gömme araması · 3/5 · S (~2 gün, gömme altyapısıyla).

### Kampanya ayrıntısı (`/kampanyalar/:id`)
- **Ne yapıyor:** Kitaplar ve indirim simülasyonu (marj, telif, asgari fiyat), adaylar, Zeki AI metni, sonuç (önce/kampanya/sonra — `ResultsScreen.tsx:11`), onay ve «elle kurdum» işareti (`CampaignDetail.tsx:16`).
- **Bugün AI:** Var. Kampanya metni (başlık/kısa açıklama/banner) `draft_copy` (`kampanya.py:1635-1651`), sonuç özeti `draft_summary` (`kampanya.py:1698-1709`); kaynaksız rakam/iddia içeren seçenek atılır (`CampaignDetail.tsx:410`).
- **Beklenti:** Pazar yeri için ayrı metin sınırları; sonuçta yamyamlık (kampanyasız kitaplara etki).
- **Yapabileceklerimiz:** **Kanal sınırlı metin** (Trendyol/Amazon başlık sınırları) · kural sayaç + taslak · 2/5 · S. **Yamyamlık yorumu** · kampanya dönemi kategori satışı · kural + yorum · 3/5 · M.
- **Eksik:** —
## M42 Kanallar ve D2C

Menü: Platform › Kanallar › «Kanal karnesi», «Kitap × kanal», «D2C büyüme», «Cari eşleme» (4 öğe) · Rotalar: 5 (`/kanallar`, `/kanallar/matris`, `/kanallar/d2c`, `/kanallar/eslesme`, `/kanallar/:platform`) · Arka uç: `channels/api.py`, `scorecard.py`, `d2c.py`, `mapping.py`, `report.py`, `platforms.py`, `refresh.py`, `store.py`, `sources.py` · İhtiyaç: `M42-pazaryeri-d2c.md`.

### Kanal karnesi (`/kanallar`)
- **Ne yapıyor:** Platform kartları (kanala satış, iskonto, iade, marj, hedef), kanallar arası kıyas, «platform değil» carileri ayrı; Excel (`ChannelsHome.tsx:13`, `:133`).
- **Kim:** Kanal/pazar yeri sorumlusu, satış müdürü, finans.
- **Bugün AI:** Ekranda yok; aylık karne e-postasına 5–8 cümle not `KARNE_PROMPT` (`report.py:80-92`) — alıcı iç ekip (dış gönderim değil).
- **Beklenti:** Ekranda da aynı «bu ay kanallarda ne oldu» özeti; hedef sapmasının en büyük katkıcısı.
- **Yapabileceklerimiz:** **Karne özetini ekranda göstermek** (hazır metin yeniden kullanım) · 3/5 · S (~0,5 gün). **Sapma katkı analizi** · kanal × kitap net adet farkı · kural + yorum · 3/5 · S (~2 gün).

### Kitap × kanal (`/kanallar/matris`)
- **Ne yapıyor:** Satır kitap, sütun platform; net adet ve iade (`Matrix.tsx:12`).
- **Bugün AI:** Yok.
- **Beklenti:** «Hangi kanal hangi kitabı iade ediyor?» açıklaması; kanalda hiç olmayan ama benzer kanalda iyi satan kitap.
- **Yapabileceklerimiz:** **Kanal boşluğu önerisi** · matris (kitap bir kanalda güçlü, diğerinde yok) · kural + gerekçe · 3/5 · S (~2 gün). **İade kümeleri** · kural · 2/5 · S.

### D2C büyüme (`/kanallar/d2c`)
- **Ne yapıyor:** timas.com.tr payı, sitede oransal güçlü kitaplar, D2C'ye özel set önerisi (`D2CGrowth.tsx:13`, `:162`).
- **Bugün AI:** Var. Set önerisi gerekçesi `SET_PROMPT` (`d2c.py:160-168`), rakamlı satırlar atılır.
- **Beklenti:** Ön sipariş önerisi (ihtiyaç); siteye özel içerik.
- **Yapabileceklerimiz:** **M53 set hattına aktarma** (öneriden set taslağı) · 2/5 · S. **Siteye özel ön sipariş adayı** · M15 yeni kitap + yazarın D2C gücü · kural + gerekçe · 3/5 · S.

### Cari eşleme (`/kanallar/eslesme`)
- **Ne yapıyor:** Logo cari + kanal kodu + CRM bölge ↔ platform; unvan eşleşmesi ya da Zeki AI aday, kullanıcı onaylar (`Accounts.tsx:15`, `:95`).
- **Bugün AI:** Var. `mapping.py:184-189` kapalı küme `choose` (platform listesi + «platform değil») + olasılık; seçenek yoksa `chat` ile kısıtlı yanıt.
- **Beklenti:** Karşılandı. **Öneri:** —. **Eksik:** —

### Kanal detayı (`/kanallar/:platform`)
- **Ne yapıyor:** Aylık eğri, cariler, kitap/iade listeleri, hedef ↔ gerçekleşen, iskonto simülasyonu (`Channel.tsx:15`).
- **Bugün AI:** Var. Simülasyonun 2–3 cümle yorumu `_comment` (`api.py:486-492`), rakamlı satır atılır (`Channel.tsx:201-225`).
- **Beklenti:** Kanala özel ay sonu tahmini; müzakere notu.
- **Yapabileceklerimiz:** **Kanal ay/çeyrek tahmini** · kanal aylık net seri · zaman serisi tahmini (sunucudaki tahmin servisi) · 3/5 · M (~3 gün) · aralıkla gösterilir. **Müzakere notu taslağı** (iskonto görüşmesi için olgu listesi) · karne + simülasyon · taslak · 3/5 · S · iç belge.

## M40 Trendyol mağazası

Menü: Platform › Trendyol › 4 öğe (`/trendyol`, `/urunler`, `/siparisler`, `/sorular`) · Rotalar: 7 (+ `/vitrin`, `/haftalik`, `/yukle` bölüm sekmeleri) · Arka uç: `channels/trendyol.py`, `trendyol_api.py`, `trendyol_import.py`, `trendyol_client.py`, `platform_common.py` · İhtiyaç: `M40-trendyol.md` (kullanıcı kararı 2026-09-28: yalnız okuma + panel dosyası).

### Mağaza özeti (`/trendyol`)
- **Ne yapıyor:** Stok ve fiyat farkı, sipariş/iade, cevapsız soru, düşük puanlı yorum; panel dosyalarıyla Logo yan yana; mağazaya gönderim yok (`TrendyolHome.tsx:75`).
- **Kim:** Pazar yeri sorumlusu (günlük), e-ticaret yöneticisi.
- **Bugün AI:** Yok (sayılar).
- **Beklenti:** Sabah «bugün mağazada önce ne yapmalıyım» listesi.
- **Yapabileceklerimiz:** **Günlük iş sırası** · stok farkı × satış hızı, geciken paket, cevapsız soru yaşı · kural puan + kısa cümle · 3/5 · S (~1 gün).

### Ürün, stok ve fiyat (`/trendyol/urunler`)
- **Ne yapıyor:** Trendyol'da satışta ama depoda yok / depoda var ama kapalı; liste/site fiyatından sapan fiyat (`Products.tsx:139`).
- **Bugün AI:** Yok.
- **Beklenti:** Fiyat sapması nedeni; ürün başlığı/açıklama kalitesi.
- **Yapabileceklerimiz:** **Fiyat sapma nedeni** · M34 `classify_reasons` yeniden kullanım (`eticaret.py:1080`) · 2/5 · S. **Trendyol ürün başlığı taslağı** (panelde elle girilir) · CRM kartı + karakter sınırı · taslak + guard · 3/5 · S (~2 gün).

### Sipariş ve iade (`/trendyol/siparisler`)
- **Ne yapıyor:** Bekleyen/geciken paketler, iade nedenleri, kitap bazında iade oranı (`Orders.tsx`).
- **Bugün AI:** Var. İade nedeni önce anahtar sözcük kuralı, sonra `choose` `CLAIM_CLASSES` + olasılık (`trendyol.py:556-589`, istem `:167`); açıklama maskeli.
- **Beklenti:** Baskı hatası iadelerinin kitap/baskı bazında toplanıp üretime bildirimi.
- **Yapabileceklerimiz:** **Baskı hatası kümesi → üretim uyarısı** · sınıf=baskı hatası × stok kodu × baskı · kural eşik + tek cümle · 4/5 · S (~1 gün) · M52/M43 ile ortak (M37 yorum sınıflamasıyla aynı yapı taşı).

### Soru ve yorum (`/trendyol/sorular`)
- **Ne yapıyor:** Cevapsız müşteri soruları, düşük puanlı yorumlar; Zeki AI yanıt taslağı, kopyala; gönderim yok; e-posta/telefon/uzun numara maskeli (`Questions.tsx:14`, `:162`).
- **Bugün AI:** Var. `draft_reply` `REPLY_PROMPT` (`trendyol.py:667-686`).
- **Beklenti:** Duygu ve konu sınıflaması (ihtiyaç §13 — kodda bulunamadı); sık sorulan soruya hazır cevap bankası.
- **Yapabileceklerimiz:** **Soru/yorum konu sınıflama** · maskeli metin · `choose` (kargo/baskı/içerik/fiyat/stok sorusu/övgü) · 3/5 · S (~1 gün). **Onaylı cevaplardan SSS bankası + benzer soru araması** · onaylı taslaklar · gömme benzerliği · 3/5 · M (~3 gün) · M51 SSS açıklarıyla ortak.

### Vitrin önerisi (`/trendyol/vitrin`)
- **Ne yapıyor:** Depo stoğu derin ve Trendyol'da hızlı satan kitaplar (kural: satış hızı × stok haftası); Zeki AI rakamsız gerekçe (`Showcase.tsx:94`).
- **Bugün AI:** Var. `showcase_suggest` `SHOWCASE_PROMPT` (`trendyol.py:750-765`).
- **Beklenti:** Karşılandı; özel gün uyumu.
- **Yapabileceklerimiz:** **Özel gün/sezon filtresi** · M17 konu eşleşmeleri yeniden kullanım · 2/5 · S.

### Haftalık rapor (`/trendyol/haftalik`)
- **Ne yapıyor:** Son 7 gün satış/iade/bekleyen; Zeki AI rakamsız özet (`Weekly.tsx:22`, `:44`).
- **Bugün AI:** Var. `SUMMARY_PROMPT` (`trendyol.py:174`, `:810`).
- **Beklenti:** Karşılandı. **Öneri:** Geçen haftayla fark cümleleri kural tablosundan · 1/5 · S.

### Panel dosyası yükleme (`/trendyol/yukle`)
- **Ne yapıyor:** Satıcı panelinden Excel/CSV; yalnız ürün, adet, tutar, durum, metin kolonları; alıcı adı/adres/telefon okunmaz (`Imports.tsx:51`).
- **Bugün AI:** Yok (doğrulanmadı: kolon tanıma kural mı; `trendyol_import.py`'de model çağrısı bulunamadı).
- **Beklenti:** Panel biçimi değişince kolon tanıma.
- **Yapabileceklerimiz:** **Kolon eşleme** (M21 `model_mapping` ortak yapı taşı; kişisel kolon adları bilinçli olarak dışarıda) · 3/5 · S (~1 gün).

## M41 Amazon ve yurtdışı

Menü: Platform › Amazon ve yurtdışı › 4 öğe (`/amazon`, `/konsinye`, `/yurtdisi`, `/taslaklar`) · Rotalar: 6 (+ `/haklar`, `/pazarlar` bölüm sekmeleri) · Arka uç: `channels/amazon.py`, `amazon_api.py`, `amazon_client.py` · İhtiyaç: `M41-amazon-uluslararasi.md`.

### Amazon özeti (`/amazon`)
- **Ne yapıyor:** Amazon carilerine faturalı satış, konsinye, yurtdışı kanal satışı, satılmış haklar; satış raporu yüklemesi M42 panel dosyasıyla (`AmazonHome.tsx:121`, `:169`).
- **Kim:** Kanal sorumlusu, yurtdışı hak/ihracat sorumlusu, genel müdür.
- **Bugün AI:** Yok.
- **Beklenti:** Aylık 5–8 cümle özet (ihtiyaç §13 — kodda bulunamadı).
- **Yapabileceklerimiz:** **Aylık özet** · özet tabloları · M40 `SUMMARY_PROMPT` deseni · 2/5 · S (~1 gün).

### Konsinye (`/amazon/konsinye`)
- **Ne yapıyor:** Faturalanmamış sevk − iade irsaliyesi = konsinyede kalan, kitap bazında (`Consignment.tsx:22`).
- **Bugün AI:** Yok. **Beklenti:** Uzun süredir konsinyede kalan (yaşlanma) uyarısı. **Öneri:** kural yaşlanma listesi, model gerekmez · 2/5 · S. **Eksik:** —

### Yurtdışı satış (`/amazon/yurtdisi`)
- **Ne yapıyor:** Yurtdışı kanal kodlu carilere faturalı satış, döviz; ülke Logo cari yazımı (`International.tsx:65`).
- **Bugün AI:** Yok.
- **Beklenti:** Ülke yazımlarının normalleştirilmesi; ülke başına eğilim.
- **Yapabileceklerimiz:** **Ülke adı normalleştirme** · Logo cari ülke metni · kural sözlük + `choose` (ISO ülke listesi) · 2/5 · S (~1 gün).

### Satılmış haklar (`/amazon/haklar`)
- **Ne yapıyor:** CRM etkin Telif Satış sözleşmeleri: ülke, yabancı yayınevi, kitabın yurtdışı satışı (`Rights.tsx:23`).
- **Bugün AI:** Yok.
- **Beklenti:** Sözleşme notlarından dil/ülke çıkarımı — yalnız alan boşsa, olasılıkla ve onayla (ihtiyaç §13; kodda bulunamadı).
- **Yapabileceklerimiz:** **Hak notundan dil/ülke** · CRM sözleşme notu · `choose` dil listesi + olasılık · 3/5 · S (~2 gün) · M36 not okuma deseni (`dijital.py:856`). **Hak satışı adayı** · Türkçe'de güçlü + çeviri hakkı boş · kural + gerekçe · 3/5 · S.

### Pazar değerlendirme kartları (`/amazon/pazarlar`)
- **Ne yapıyor:** Yeni yurtdışı pazar gösterge kartı: ülke satışları, hak satışları, finans varsayımları; Zeki AI rakamsız gerekçe (`MarketCards.tsx:153`).
- **Bugün AI:** Var. `create_card` `CARD_PROMPT` (`amazon.py:748-761`).
- **Beklenti:** Karşılandı. **Öneri:** —. **Eksik:** Pazar büyüklüğü dış kaynağı yok (M39 ile aynı ilke).

### Listeleme taslakları (`/amazon/taslaklar`)
- **Ne yapıyor:** Tek kitap için hedef pazarda başlık, açıklama, anahtar kelime, A+ metni ya da çeviri brief'i; CRM kitap kartından; denetimden geçmeyen cümle çıkarılır; gönderim yok (`Drafts.tsx:79`).
- **Bugün AI:** Var. `create_draft` `DRAFT_PROMPT` hedef dilde (`amazon.py:155`, `:652-668`).
- **Beklenti:** Hedef dilde terim tutarlılığı; geri çeviri ile kontrol.
- **Yapabileceklerimiz:** **Geri çeviri denetimi** · taslak → Türkçe geri çeviri + anlam farkı işareti · editör çeviri kalite hattı (`editorial_translation_qe.py`) yeniden kullanım · 3/5 · S (~2 gün). **Yazar/seri terim sözlüğü** · 2/5 · S.
## Grubun en değerli 10 AI önerisi

Sıra: önce değer (yüksekten), eşitlikte zorluk (kolaydan). Rakamları hiçbirinde model üretmez; hepsi taslak/öneri + insan onayı.

| # | Öneri | Modül / ekran | Veri | Teknik | Değer | Zorluk | Koruma |
|---|---|---|---|---|---|---|---|
| 1 | **Kitap benzerliği araması** — emsali girilmemiş yeni kitaba emsal adayı; aynı hat M39 «Emsal bul», SEO «Benzer kitaplar», rehber kitap seçimi | M15 plan ekranı · M39 `/emsal` · SEO `/benzer-kitaplar`, `/rehberler` | CRM `new_kitapBase.new_ozet`, tema/yaş bağları, `new_new_kitap_new_emsalkitap3Base`, fiyat/sayfa | gömme benzerliği + kural süzgeç + `choose` «emsal mi» | 5 | M (~5 gün) | düşük marj «Belirsiz»; insan onayı; CRM'e yazılmaz |
| 2 | **Lansman risk bayrağı + gerekçe** (sipariş/stok/hedef/emsal sapması) | M16 `/pazarlama/lansman` | `launch_days`, günlük hedef payı, emsal günleri | kural eşik + tek cümle (guard) | 4 | S (~2 gün) | rakam tablodan |
| 3 | **Hedef açığı ↔ ay planı boşluğu** («hedefin altında kalan kitaplara bu ay iş planlanmamış») | M18 `/pazarlama/aylik-plan` | M46 sapma, ay kalemleri | kural liste + paragraf (guard) | 4 | S (~2 gün) | karar müdürde |
| 4 | **Hedef değişince bütçe revizyonu iki seçenek** | M15 plan › Kanal ve bütçe | `target_changed`, bütçe çerçevesi | kural hesap + gerekçe | 4 | S (~2 gün) | K3: karar insanda |
| 5 | **SEO fırsat sorgusundan ürün önerisine tek tık** (hedef kelimeli `propose`) | SEO `/firsatlar` → `/urun-denetimi` | Search Console sorgu + ürün kaydı | mevcut `propose.suggest` | 4 | S (~2 gün) | T-soft'a gitmez; onay |
| 6 | **Okur sesi sınıflayıcı** — site yorumu, Trendyol soru/yorum, iade açıklaması: konu (kargo/baskı hatası/içerik/fiyat/övgü); baskı hatası kümesi → üretime iç uyarı | M37 `/yorumlar` · M40 `/sorular`, `/siparisler` · M22 rapor | maskeli metin (`aciklama_maskeli`) | `choose` kapalı küme + olasılık, kural eşik | 4 | S (~3 gün) | kişisel veri maskeli; yalnız iç uyarı |
| 7 | **Arama sorgusu niyeti + H1 kategori** (bilgi/kitap/yazar/liste; kategori düğümü) | SEO `/anahtar-kelimeler`, `/sorgu-sayfa` · H3 | GSC sorguları, H1 ağacı | `choose` (gece BATCH) | 4 | M (~3 gün) | kişisel veri yok |
| 8 | **Yapay zekâ cevaplarında Timaş: doğru/yanlış bilgi ve ton** | SEO `/ai-gorunurluk` | kayıtlı cevap metinleri (`semantic_seo_geo_results`) | yerel model `choose` + rakip anılma kuralı | 4 | M (~3 gün) | düzeltme işi M20/M28'e öneri |
| 9 | **Erken satış ve tükenme tahmini** (lansman D+30/D+90, pazar yeri carisi, kanal ayı) | M16 İzleme · M34 `/pazar-yerleri` · M42 `/kanallar/:platform` | Logo günlük/haftalık seri, emsal eğrileri, stok | zaman serisi tahmini (sunucudaki tahmin servisi) | 4 | M (~4 gün) | «tahmin» etiketi, aralıkla |
| 10 | **Kampanya indirim oranı önerisi** (geçmiş öğrenimlerden) | M35 `/kampanyalar/adaylar`, `/:id` | M35 sonuçları (önce/sonra), marj/telif/asgari fiyat simülasyonu | kural (geçmiş etki medyanı) + gerekçe | 4 | M (~4 gün) | simülasyon zorunlu; karar insanda |

Listeye girmeyen diğer 4/5'ler: serbest istekten set kurma (M53), segment başına kitap önerisi (H3), ödül uygunluğu (M27), belge okuma — fuar gider fişi / kamu şartnamesi / sözleşme dijital hak maddesi (M27, M28, M36).

## Ortak altyapı ihtiyaçları

Birden çok ekranda tekrar eden yapı taşları. İlk dördü var ama tek modüle gömülü; genelleştirilirse yukarıdaki önerilerin çoğu S boyutuna iner.

1. **Metin denetimi (guard) — var, tekleştirilmeli.** `marketing/guard.py` (birebir alıntı, kaynaksız rakam, kanıtsız üstünlük iddiası, teknoloji adı) M15–M19, M20, M22–M24, M53'te kullanılıyor; kanal/Trendyol/Amazon metinleri rakamlı satırı regex'le siliyor (`channels/d2c.py:168`, `api.py:486`), SEO kendi kurallarını (`propose.unsupported`, `faq.reality`) kullanıyor. Tek denetim kütüphanesi + düşen cümle sayısının her ekranda aynı gösterimi.
2. **Kapalı küme sınıflayıcı + öneri onay kuyruğu — var, dağınık.** `QueuedLlm.choose` + olasılık/marj + «Belirsiz»: emsal (M15), konu–gün (M17), iddia (M19), ton (M20), kolon ve kampanya eşleme (M21), içerik türü (M22), konu (M23), tip (M27), alan (M28), fark nedeni (M34), bayi kampanya türü (M35), hak notu ve rapor satırı (M36), hassas ilgi (M37), kategori ve emsal (M39), iade nedeni (M40), cari eşleme (M42), sezon (M53). Her biri kendi onay ekranını kuruyor; ortak «Zeki AI önerileri — onayla/düzelt/reddet» bileşeni ve ortak eşik ayarı.
3. **Tablo yorumlayıcı — var, eksik ekranlar.** «Rakamlar tablodan, tabloda olmayan sayı düşer» deseni: `launch_report.draft_text`, `pr.report_comment`, sosyal rapor, reklam raporu, `commerce.comment_campaign`, `monthly.explain`, kanal karnesi, Trendyol haftalık, kampanya sonucu, M39 özet. Eksik: fuar sonucu, katalog/bülten raporu, SEO aylık rapor ve özet, Amazon özeti, kurumsal ilişkiler raporu, işbirliği raporu, H2 özeti, backlist etkisi. Tek servis + ekran başına istem.
4. **Dosya kolon eşleme — var (M21), yeniden kullanılmalı.** `ads_sources.model_mapping` (başlık + örnek → alan, «yok» seçeneği): H2 yüklemeleri, M22 rapor dosyası, M36 platform raporu, M40 panel dosyası, M24 araç dosyası. Kişisel kolonlar örnek değer olarak modele gitmez (biçim etiketi gider).
5. **Gömme / benzerlik araması — yok.** Emsal ve benzer kitap (M15, M39, SEO), M19 arşiv araması, M35 öğrenim araması, M40/M51 SSS bankası, M23 benzer içerik üreticisi, SEO yönlendirme eşleşmeyenleri, rehber kitap seçimi. Yerel gömme modeli + kitap/metin indeksi (sunucuda, gece güncellenen).
6. **Serbest metin → kitap eşleyici — üç ayrı kopya.** `ads.match_campaign` (kod → ad benzerliği → `choose`), `dijital.suggest_matches`, PR yansıma ve CRM etkinlik metni için gerekiyor. Tek «kitap bul» servisi.
7. **Okur sesi sınıflayıcı + kişisel veri maskeleyici.** Trendyol maskelemesi (`aciklama_maskeli`) ve M37 yorum maskelemesi ayrı; M22 DM/yorum ve M51 destek talepleri de aynı sınıflamayı ister. Ortak maskeleme + ortak konu kümesi + yönlendirme önerisi (üretim, lojistik, destek).
8. **Konu/gündem eşleşmesi.** `backlist.match_topics` (`backlist.py:1086`) özel gün ↔ kitap; M22 fırsatlar, SEO sezon takvimi, M40 vitrin, M53 set sezonu, M27 fuar seti aynı işi istiyor.
9. **Belge okuma / OCR.** `pazar.extract_page` yalnız metin katmanı olan PDF'i okuyor. Fuar gider fişi (M27), kamu şartnamesi (M28), sözleşme dijital hak maddesi (M36), taranmış sektör raporu (M39). Her çıkarılan değer sayfa/konum ve birebir alıntıyla, insan onayına.
10. **Zaman serisi tahmini bağlantısı.** Sunucudaki tahmin servisi (Baskı Öneri'de kullanılıyor) bu grupta hiç çağrılmıyor: lansman eğrisi (M16), backlist canlanma (M17), pazar yeri tükenme (M34/M40), kanal ayı (M42).
11. **Ekran bağlamlı «Zeki AI'a sor».** Plan, ay planı, lansman ve pazar ekranlarındaki kutu genel soru kutusunu açıyor (`PlanScreen.tsx:246`, `MonthScreen.tsx:191`); ekranın kitap/ay/kanal bağlamını soruya taşıyan ortak parametre (sayı yine katalog SQL'inden).
12. **Uzun iş ve ilerleme.** `C.job_update` deseni (durum, adım, düşen sayısı) M15/M16/M17/M24/M36 gibi yerlerde ayrı ayrı yazılmış; LLM kapısının iş ucu (`/api/v1/llm/jobs`) ile tekleştirilebilir.
