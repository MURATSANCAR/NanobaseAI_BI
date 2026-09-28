# Zeki AI fırsatları — bütün modüller, ekran ekran (2026-09-28)

Kullanıcının isteği: «Bütün modülleri ve ekranları eksiksiz değerlendir; kullanıcıların bu sistemlerden AI
beklentilerini çıkar; AI ile neler yapabileceğimizi listele.» Dört değerlendirme paralel yapıldı, kaynak main
`f26e11d6` (salt okuma). Her ekran için: ne yapıyor · kim kullanıyor · bugün AI var mı (dosya:satır) · kullanıcının
AI beklentisi · yapabileceklerimiz (veri, teknik, değer 1–5, zorluk S/M/L, koruma) · eksik.

| Grup | Belge | Kapsam |
|---|---|---|
| A — Çekirdek, Analiz, Yönetim, Altyapı ve destek, destek masası | [A-cekirdek-altyapi.md](A-cekirdek-altyapi.md) | 16 menü öğesi, 57 portal ekranı (sekmeler dahil), 13 destek masası ekran grubu, Kampüs'te canlı olmayan 8 kutu |
| B — Editoryal ve Kayıtlar, editör modülü | [B-editoryal-kayitlar.md](B-editoryal-kayitlar.md) | 25 menü öğesi, 49 rota (3'ü yönlendirme), editör modülü ayrı bölüm |
| C — Pazarlama ve Platform (+ M36, M39) | [C-pazarlama-platform.md](C-pazarlama-platform.md) | 24 modül, 66 menü öğesi, 137 rota, 157 ekran/sekme başlığı |
| D — Finans, Satış ve saha, Lojistik, İK | [D-finans-satis-lojistik-ik.md](D-finans-satis-lojistik-ik.md) | 47 menü öğesi, 77 rota, 73 ekran başlığı |

Menü ve rota listeleri her belgede betikle karşılaştırıldı; atlanan ekran yok.

Bütün öneriler şu ilkelere uyar: rakamı model üretmez (SQL/kural üretir, model açıklar/seçer/taslak yazar, metindeki
her sayı olgularla denetlenir); ilk sürümde otomatik dış gönderim yok (taslak + onay + insan); CRM/Logo/T-soft'a yazma
yok; kişisel veri modele maskeli gider; model yerel ve LLM kapısından (`rt.llm_for`); ekranda «Zeki AI».

## Bugünkü durum — kısa

- **En olgun alan pazarlama ve platform:** 24 modülün hepsinde model var (~68 işlev, 74 çağrı noktası, hepsi kapıdan).
- **Satış, lojistik, İK:** bütün modüllerde model var (sınıflama, taslak, brif).
- **Hiç AI olmayan ekranlar:** M1 başvuru ve yayın kurulu, yazar giriş süreci, M2 atama, M6 sözleşme, M8 serbest
  çalışan, M12 üretim, Kişiler, Kapak arşivi, finansal denetim, M9 fiyatlama.
- **Zeki AI sohbetinin veri kataloğu eksik:** 9 konu (pazarlama, İK, destek, risk, editoryal süreç…) «veri bağlı değil».
- **Tahmin motoru** (zaman serisi) p10–p90 üretiyor ama bütçe ve stok ekranları yalnız p50 okuyor; aralık hiçbir
  yerde görünmüyor; ilk baskıda bağlı ama kapalı.
- **Hiç olmayan yapı taşları:** benzerlik araması (gömme), portalda taranmış belge okuma, ekran bağlamlı soru kutusu.

## Hemen düzeltilecekler (koddan doğrulanmış bulgular)

| # | Bulgu | Yer | Neden önemli |
|---|---|---|---|
| 1 | Destek masası talep/yazışma metnini modele **maskesiz** gönderiyor | `apps/destek/…/nanobase_brand/yz/kayit.py` | KVKK; köprüdeki M51 maskeliyor (`support.py:340`) |
| 2 | Sayı denetimi olmayan model metinleri | `author_growth.make_advice`, `it_ops.py:699` olay taslağı, destek haftalık rapor yorumu (`rapor.py`) | «Rakamı model üretmez» ilkesi |
| 3 | Modelsiz ama «Zeki AI» etiketli | Kategori ağacı «veriden taslak» (`categories.py:760/854`, `TreeEditor.tsx:144`), M10 ilk baskı, M46 bütçe önerisi, M27 fuar kitap önerisi (`FairBooks.tsx:11`, `events.py:864`) | Kullanıcıyı yanıltır |
| 4 | Kampüs'te sabit örnek içerik: «Matbaadan yeni çıkanlar»da iki uydurma kitap | `KampusPage.tsx:722` | Demo içerik kuralı |
| 5 | LLM kapısını atlayan çağrı: yönetim ekranındaki model denemesi `LlmClient`'i doğrudan kuruyor | `admin.py:2056` | Tek sıra kuralı |
| 6 | Aynı CRM hak açıklaması iki modülde ayrı sınıflanıyor | `dijital.py:877`, `royalty_api.py:718` | Çift maliyet, çelişen sonuç |
| 7 | İki ayrı destek sınıflayıcısı (masa olasılıksız, M51 `choose` ile) | `yz/kayit.py` ↔ `support.py` | Aynı talebe iki farklı sınıf |
| 8 | Basın ve web etiketlemesi serbest cevabı kelimeyle ayrıştırıyor | `web_watch.py:549` | `QueuedLlm.choose` + olasılık kullanılmalı |
| 9 | İki ayrı «huni» ekranı (H3 ve M34) | `/eticaret-musteri/huni`, `/e-ticaret/huni` | Tek ekranda birleşmeli |
| 10 | 17 ihtiyaç belgesinin başında hâlâ «analiz (kod yok)» | `docs/analiz/kullanici-ihtiyaclari/` | Durum satırı eski |

## Bütün sistemde en değerli 20 öneri

Sıra: değer (5 → 4), eşitlikte kolaydan zora. Zorluk: S ≈ 1–2 gün, M ≈ 3–5 gün, L ≈ 5+ gün (tek geliştirici,
test sunucusunda doğrulama hariç).

| # | Öneri | Ekranlar | Teknik | Değer | Zorluk |
|---|---|---|---|---|---|
| 1 | **Aylık finansal yorum taslağı** (kurul paketine de) | `/finansal-raporlar`, `/kurul` | olgu → özet + sayı denetimi, CFO onayı | 5 | S |
| 2 | **Sabah saha brifi** — temsilcinin günü 4–5 cümle (telefon) | `/saha` Bugün | özet + mevcut sayı denetimi | 5 | S |
| 3 | **Tahmin aralığını görünür yapmak** — stok kartı, bitecekler, bütçe senaryoları p10/p50/p90; yıl sonu tahmini kapanış | `/stok/*`, `/butce` | mevcut tahmin motoru | 5 | S–M |
| 4 | **Rakamın / sapmanın nedeni** — dönem farkını kanal, cari, kitap katkısına SQL ile ayırıp 2–3 cümle | Genel bakış, Uyarılar, Panolar, `/butce`, M45 | fark ayrıştırma + özet + denetim | 5 | M |
| 5 | **«Ne değişti» anlatımı** — pano kartı ve planlı rapor e-postasında önceki sonuçla fark | Panolar, Planlı raporlar | kodla fark + model madde | 5 | M |
| 6 | **Olağan dışı değer uyarısı ve eşik önerisi** — beklenen aralık dışına çıkan ölçü | Uyarılar, Panolar | tahmin motoru / mevsimsel istatistik; model yalnız açıklar | 5 | M |
| 7 | **Olasılıklı 13 haftalık nakit bandı** ve «en kötü %10» kasa çizgisi | `/finansal-raporlar` Nakit | tahmin motoru + kural vadeler | 5 | M |
| 8 | **Destek taslağına sipariş, kargo, fatura bağlamı** + tek olasılıklı sınıflayıcı + ortak maskeleme | Destek masası, `/musteri-destek` | yer tutuculu taslak, `choose`, maske | 5 | M |
| 9 | **Kitap benzerliği araması** — emsali olmayan yeni kitaba emsal; aynı yapı M39 emsal, SEO benzer kitap, kurul, Kitap 360 | M15, `/pazar-arastirma/emsal`, `/basvurular/:id`, `/kitap/:id` | gömme dizini (kitap özetleri) | 5 | M |
| 10 | **Ortak belge okuma hattı (taranmış PDF dahil)** — şartname, özgeçmiş, sertifika, sektör raporu, fatura | `/ihale/:id`, `/ik/ise-alim/aday/:id`, pazar raporları, `/kargo/mutabakat` | editör modülündeki ölçülmüş okuyucu + alıntı denetimi | 5 | M |
| 11 | **Zeki AI sohbetine modül verisi** — 9 boş konu (editoryal süreç, pazarlama, İK, destek, risk…) | Genel bakış, Kampüs, pano soru kutusu | katalog veri alanı + `choose` eşleme; rakam SQL | 5 | L |
| 12 | **Başvuru ön okuması ve editör raporu taslağı** — tür, yaş, özet, ilke riski alıntıyla; puan insanda | `/basvurular/:id` | editör motoru belge okuma, kapalı küme | 5 | L |
| 13 | **Sözleşme belgesinden şart çıkarma** — oran, avans, süre, hak bayrakları birebir alıntıyla | `/telif-sozlesme/*` | belge okuma + yapılandırılmış çıkarım | 5 | L |
| 14 | **Editör motorunda metin bütçesi ve pencereleme** — uzun ve kurgu dışı kitaplar için ön koşul | editör modülü, `/son-okuma`, `/kitap/:id` | altyapı | 5 | L |
| 15 | **Okur sesi sınıflayıcı** — site yorumu, Trendyol soru/yorum, iade açıklaması; baskı hatası kümeleri üretime iç uyarı | M37 `/yorumlar`, M40, M22 | `choose` kapalı küme, maskeli metin | 4 | S |
| 16 | **Serbest not sinyali** — CRM etkinlik ve ziyaret notlarından tahsilat sözü / şikâyet / sipariş / kapanış sinyali | `/bayi-risk/:code`, `/saha/musteri/:code`, `/musteri-iliskileri/*` | gece `choose` + özet | 4 | S |
| 17 | **Lansman risk bayrağı + hedef açığı ↔ ay planı boşluğu** | M16 `/pazarlama/lansman`, M18 `/pazarlama/aylik-plan` | kural eşik + tek cümle | 4 | S |
| 18 | **Yapılandırılmış hak haritası** — dil, ülke, format, bitiş; M36/M54 tek sınıflama | `/haklar`, `/dijital-yayin` | çıkarım + `choose` | 4 | M |
| 19 | **Kişisel «Bugün» özeti** — uyarı, e-posta ataması, ajanda, onay kuyruğu, SLA riski | Kampüs | kural toplama + 3 cümle | 4 | M |
| 20 | **Başarısız soru kümeleri** ve «sınıflanamadı» için sınıf önerisi | Soru izleme, `/zeki-kalite` | gömme kümeleme + `choose` | 4 | M |

Listenin hemen dışında kalan 4'lükler (grup belgelerinde ayrıntılı): SEO fırsat sorgusundan tek tıkla ürün önerisi,
arama sorgusu niyeti + H1 kategori, yapay zekâ cevaplarında Timaş'ın doğru/yanlış anılması, erken satış ve tükenme
tahmini (lansman, pazar yeri), kampanya indirim oranı önerisi, finansal denetim bulgu açıklaması, beyanname kapak
e-postası taslağı, son okuma isabet panosu, resim–metin tutarlılık denetimi, üretim şartname taslağı, bayi tahsil süresi
tahmini, belirsizlik tabanlı güvenlik stoku, ihale risk koşulu işaretleme, M58 birim iyileştirme önerisi, M56 kaynak bağlı
yıl sonu değerlendirme taslağı, kişisel veri kolon sınıflaması.

## Önce yapılacak ortak yapı taşları

Dört grupta da tekrar eden parçalar; önerilerin çoğu bunlara dayanıyor. Önce bunlar kurulursa her öneri küçülür.

1. **Tek sayı denetçisi** — bugün 3 ayrı kopya (`marketing/guard.py`, `numbers_ok`, risk brifing). Tek fonksiyon:
   olgular + metin → denetlenmiş metin ya da kural metni.
2. **Tablo/olgu yorumlayıcı** — «bu tabloyu 3–5 cümleyle anlat» (8 ekranda eksik: fuar sonucu, katalog raporu, SEO
   aylık rapor, Amazon özeti…); 1'i kullanır.
3. **Ortak kişisel veri maskeleme** — destek masası, e-posta, İK, okur metinleri aynı `mask_personal`.
4. **Belge okuma ve OCR hattı** — editör modülündeki ölçülmüş okuyucu portala açılır; alıntı denetimi korunur.
5. **Benzerlik araması (gömme dizini)** — kitap özetleri; emsal, benzer kitap, soru kümeleri.
6. **Tahmin istemcisi** — tek istemci, p10–p90 okur, «tahmin» etiketi ve aralıkla gösterim.
7. **Kapalı küme seçimde isabet ölçümü** — `QueuedLlm.choose` kullanan her sınıflayıcı için kör etiketleme örneği ve
   eşik; «Zeki AI kalitesi» karnesine satır.
8. **Ortak öneri onay kuyruğu** — taslak → onay → insan uygular; bugün her modülde ayrı.
9. **Ekran bağlamlı soru kutusu** — «Zeki AI'a sor» o ekranın filtresini ve kaydını taşır.
10. **Sohbet kataloğunun genişletilmesi** — portal tabloları veri alanı olarak; satır düzeyi yetkiyle.

## Kullanıcı kararı gereken noktalar

1. **SEO «Yapay zekâ görünürlüğü» ekranı ölçülen dış motorların adlarını yazıyor** (`SeoVisibility.tsx:45`).
   «Ekranda teknoloji adı yok» kuralı ölçülen dış hizmetin adını da kapsıyor mu?
2. **Saha ve okul ziyaretinde sesli not**: konuşmadan metne servisi test sunucusunda bulunamadı; GPU'ya kurulsun mu?
3. **DYK kurul panelinde net satış tanımı**: satır (`LINENET`, M45 ile aynı) mı, fatura başlığı mı?

## Önerilen sıra

1. Hemen düzeltilecekler 1–5 (yaklaşık 2 gün).
2. Ortak yapı taşları 1, 2, 3, 6 (yaklaşık 1 hafta) → öneriler 1, 2, 3, 4, 5, 7, 15, 16, 17 bunların üstüne S boyutunda.
3. Yapı taşı 4 ve 5 (belge okuma, benzerlik) → öneriler 9, 10, 12, 13, 20.
4. Sohbet kataloğu (öneri 11) ve editör motoru metin bütçesi (öneri 14) — ayrı, büyük işler.
