# D — Finans, Satış ve saha, Lojistik, İnsan Kaynakları

Grup: `D-finans-satis-lojistik-ik`. Tarih: 2026-09-28. Kaynak: `.claude/worktrees/ai-analiz-okuma` (commit `f26e11d6`), salt
okuma; sunucuya bağlanılmadı. Kullanıcı beklentileri `docs/analiz/kullanici-ihtiyaclari/{M29–M33,M38,M43–M45,M47,M52,M55–M59}.md`
(§12–13) ve koddan; M9, M10, M11, M46 için ayrı ihtiyaç belgesi yok (M9: `docs/analiz/m9-fiyatlama-kabul-2026-09-28.md`,
M10: `docs/analiz/ilk-baski-tahmini/`), bu ekranlarda beklenti uzman gözüyle yazıldı.

## Kapsam ve «atlanan yok» kanıtı

| Alan (`navModel.ts` id) | Menü öğesi | Rota (`App.tsx`) | Bu belgedeki ekran başlığı |
|---|---:|---:|---:|
| Finans (`finans`) | 8 | 11 | 11 |
| Satış ve saha (`satis`) | 8 | 17 | 17 |
| Lojistik (`lojistik`) | 15 | 21 | 21 |
| İnsan Kaynakları (`ik`) | 16 | 28 | 24 (değerlendirme formu 3 rota, anket formu 3 rota tek başlıkta) |
| **Toplam** | **47** | **77** | **73 başlık = 77 rota** |

Rota listesi `grep 'path="' src/App.tsx` ile bu dört alanın önekleriyle çıkarıldı (77); her rotanın bu belgede başlıkta
geçtiği betikle denetlendi (eksik 0). Sekmeler, alt gezinme ve süzgeç sekmeleri her ekranın başında «Sekmeler:» satırında
koddaki adlarıyla (dosya:satır) listelenir ve maddelerde ele alınır. Menüde olup kendi rotası olmayan öğe yok; menüde
olmayan rotalar (ayrıntı sayfaları) alan başlıklarında adıyla yazılı.

**Grup düzeyinde bugünkü durum (koddan):**
- Dil modeli çağrılan modüller: M29, M30, M31, M32, M33, M38, M59 (satış — hepsi), M43, M44, M52 (lojistik — hepsi), M55,
  M56, M57, M58 (İK — hepsi), M45 (yalnız hesap eşleme), M47 (kategori, risk taslağı, brifing). **Hiç model yok:** Finansal
  denetim, M9 fiyatlama, M10 ilk baskı (deterministik emsal; «ZEKİ AI» etiketli), M11 yönetim raporları listesi, M46 bütçe
  («ZEKİ AI önerisi» etiketli kural hesabı).
- Zaman serisi tahmin motoru yalnız Baskı Öneri'de doğrudan (`management/zeki_tahmin.py`, kantil p10/p50/p80/p90); Bütçe ve
  Stok kartı aynı önbellekten **yalnız p50** okuyor, güven aralığı gösterilmiyor (`budget_sources.py:296-308`,
  `stock.py:239-247`). İlk baskıda bağlı ama kapalı (`beta = 0`).
- Kurallar tutarlı uygulanmış: rakam SQL/kuraldan, model metnindeki her sayı olgularda aranıyor (`numbers_ok` /
  `safe_model_text` / `model_text` — en az 6 ayrı kopya), dış gönderim yok (taslak + kopyala), CRM/Logo'ya yazma yok, İK'da
  maske + etiketli sıra kaydı, puan/sıralama yok.
- Soru kutusu: ekranlarda yalnız örnek soru bağlantıları (Genel bakış soru kutusuna gider): `DistributionScreen.tsx:37`,
  `TodayScreen.tsx:205`, `PanoTab.tsx:111`, `StockHome.tsx:208`. Sohbet konusu `risk` ve `ik`'nın veri kataloğu boş
  (`chat_topics.json`).

---

**Alan: Finans (`finans`)**

Menü: 8 öğe (`finansal-raporlar`, `finansal-denetim`, `yonetim-raporlari`, `baski-oneri`, `fiyatlama`, `ilk-baski`, `butce`,
`risk-uyum`). Rota: 11 (menüde olmayan: `/ilk-baski/kitap/:code`, `/ilk-baski/yeni`, `/risk-uyum/risk/:id`). Sohbet konuları
`finans` (M45, M46, DYK; veri: muhasebe, banka-kasa, satış, cari) ve `risk` (M47, M49; **veri kataloğu boş**) —
`chat_topics.json`. Bu alanda dil modeli yalnız iki modülde çağrılıyor: M45 (`finance_api.py:270`) ve M47
(`risk_api.py:71`). Tahmin motoru (sunucuda, `management/zeki_tahmin.py:123-145` `POST /forecast/batch`, 12 ay, kantil
p10/p50/p80/p90 — `:36`) yalnız Baskı Öneri'de doğrudan kullanılıyor; Bütçe ve Stok onun önbelleğinden yalnız p50 okuyor
(`budget_sources.py:296-308`).

## M45 Finansal raporlar

### Finansal raporlar (`/finansal-raporlar`)
Sekmeler: Özet · Gelir tablosu · Bütçe–gerçekleşme · Kârlılık (Kitap / Seri-kitaplık / Yayınevi / Kanal / Cari) · Nakit
(yalnız `canCash`) · Vergi takvimi (`src/canvas/finance/FinanceScreen.tsx:29-35`).
- **Ne yapıyor:** Özet kartları (net satış, brüt kâr, faaliyet gideri, kasa+banka, bütçe) ve «Bu ay dikkat» listesi (kural,
  `finance.py:1550-1610`); gelir tablosu satır → hesap → Logo fişi inişi, net satış mutabakatı, mizan farkı, Excel; kârlılık
  kırılımları ve CSV; 13 haftalık nakit (deterministik, `finance.py:1154` `build_cash`) ve «geçmiş tahmin ↔ gerçekleşen»;
  vergi takvimi (elle, `TaxTab.tsx:11-12`); ay kapatma/yeniden açma; sapma açıklaması notu (elle); iş günü 08:30 özet
  e-postası ve vergi hatırlatması (`finance_api.py:125-162`). Kaynak: Logo EMFLINE/EMFICHE/EMUHACC/STLINE/PAYTRANS/CSCARD/
  CLFLINE, CRM `new_tahsilatBase`; tablolar `semantic_finance_*`.
- **Kim:** CFO, muhasebe müdürü, bütçe/finans analisti, genel müdür (özet).
- **Bugün AI:** Yalnız **hesap eşleme önerisi**: eşlenmemiş hesap için gelir tablosu satırları arasından kapalı seçim, eşik
  altı «belirsiz» (`finance.py:834-860`, `llm.choose` satır 849; uç `finance_api.py:263-288`; ekran «Zeki AI önerisi»
  `AccountMapSheet.tsx:52-54,101-117`). Soru kutusu yok; sohbet ayrı (Genel bakış).
- **Beklenti:** Ay sonu «bu ay ne oldu» yorumu (kurul paketi için); bütçe sapmasına neden cümlesi; nakit tahmininin
  belirsizliği; olağandışı hesap hareketinin işaretlenmesi; «geçen yılın aynı ayına göre neden düştü» sorusuna cevap.
- **Yapabileceklerimiz:**
  - **Aylık finansal yorum taslağı (M45 §13; kodda yok)** — Özet + gelir tablosu + kârlılık sonuç JSON'undan 5–8 cümle;
    **çıktıdaki her sayı girdide olmalı**, tutmazsa taslak atılır · teknik: özet/taslak + sayı denetimi (risk brifingindeki
    kalıp, `risk.py:1729`) · değer 5 · S (1–2 g) · koruma: «taslak» etiketi, CFO onaylar; kurul paketine insan koyar.
  - **Sapma açıklaması taslağı (Bütçe–gerçekleşme sekmesi)** — sapan satırın alt kırılımından (hangi kitap/kanal/gider
    hesabı farkı sürüklüyor — SQL) 1–2 cümle neden; bugün not elle yazılıyor · teknik: kural (katkı ayrıştırması) + model
    cümlesi · değer 5 · S (1–2 g) · koruma: sayı denetimi; not kaydı insanın.
  - **Olasılıklı nakit bandı (Nakit sekmesi)** — deterministik 13 haftalık tablonun yanında, tahsilat ve ödeme haftalık
    serilerinden tahmin motoruyla p10–p90 bandı ve «en kötü 10 %» kasa çizgisi; «geçmiş tahmin ↔ gerçekleşen» ile sınanır ·
    veri: PAYTRANS (SIGN 0/1) haftalık, CSCARD vade, CRM onay bekleyen tahsilat · teknik: zaman serisi tahmini · değer 5 ·
    M (3 g) · koruma: vadesi belli kalemler kuraldan kalır, yalnız tahsilat gecikmesi/oranı tahmin edilir; güven aralığı
    her zaman görünür.
  - **Hesap hareketi olağandışılık işareti (Gelir tablosu)** — hesap × ay tutarının kendi 24 ay dağılımına göre sapması
    (istatistik kural) + model 1 cümle «olası neden: yıl sonu kapanış / tek büyük fiş / sınıflama» (fiş açıklama alanından
    kapalı seçim; alan adı **doğrulanmalı**) · değer 4 · M (2 g) · koruma: işaret, düzeltme değil; fiş listesine iner.
  - **Vergi takvimi belgeden** — GİB/SGK duyuru PDF'i yüklenince beyan adı, dönem, son gün satırlarını alıntıyla önerir;
    kopyalama (`tax-calendar/copy`) zaten var · teknik: belge okuma + alıntı denetimi (M33 kalıbı) · değer 3 · S (1 g) ·
    koruma: web kapalı, belge insan getirir; onay insanın.
- **Eksik:** Maliyetsiz satır (`OUTCOST = 0`) marjı «yaklaşık» yapıyor; varsayımlar ayara bırakılmış
  (`finance_sources.py:18`: `FINANCE_CLOSE_ACCOUNTS`, `FINANCE_CS_*`).

## FD Finansal denetim

### Finansal denetim (`/finansal-denetim`)
Sekmeler: Denetim özeti · Logo'da ne var? · Kontrol kütüphanesi · Logo kayıtları · Dayanak veriler (`canDetail`)
(`FinancialAudit.tsx:130`).
- **Ne yapıyor:** Logo kayıtları üzerinde deterministik SQL kontrolleri (fatura↔fiş, KDV, banka, negatif kasa günü …,
  `financial_audit_deep.py:141`), rasyolar, kapsam; bulgu sayfalama, inceleme çalışma kâğıdı notu, dışa aktarım
  (`runs/{id}/export`). Sonuçlar dosyada (`FINANCIAL_AUDIT_DATA_DIR`).
- **Kim:** İç denetçi, muhasebe müdürü, CFO, bağımsız denetim hazırlığı.
- **Bugün AI:** Yok (`financial_audit.py:72` `run_sql`; dil modeli yok).
- **Beklenti:** Bulgunun düz Türkçe açıklaması ve «ne yapmalı»; bulgu önceliği; inceleme notunun standart biçimde yazılması;
  benzer bulguların gruplanması; dönem sonu denetim raporu taslağı.
- **Yapabileceklerimiz:**
  - **Bulgu açıklaması ve önerilen inceleme adımı** — her kontrolün sonucu (satır sayısı, tutar, örnek fişler — SQL) → 2–3
    cümle «ne demek, olası neden, bakılacak belge»; kontrol tanımı ve kaynak notu isteme girer · teknik: özet + sayı
    denetimi · değer 4 · S (1–2 g) · koruma: bulgu kuraldır, model yalnız açıklar.
  - **İstisna satırlarının nedene göre kümelenmesi** — aynı kontrolün yüzlerce istisnasını fiş açıklaması/hesap/kullanıcı
    alanlarına göre kural gruplar, belirsizde kapalı seçimle «muhtemel sınıf» (zamanlama farkı / eksik belge / yanlış hesap /
    mükerrer / diğer) · teknik: `choose` · değer 4 · M (2 g).
  - **Denetim özeti raporu taslağı** — Word/PDF'e girecek yönetici özeti, her sayı girdide · değer 3 · S (1 g).
  - **İnceleme notu yapılandırma** — serbest notu «bulgu / neden / aksiyon / sorumlu / tarih» alanlarına öneri · değer 2 ·
    S (0,5 g).
- **Eksik:** Yıl ve firma sabit (`financial_audit.py:60` `year != 2026` → 422; `LG_411_*`; ön yüzde `documents?year=2026`,
  kiracı adı sabit `FinancialAudit.tsx:115,134`); kaynak notları 2020 belgesinden (`financial_audit_rules.py:1`).

## M11 Yönetim raporları

### Yönetim raporları (`/yonetim-raporlari`)
- **Ne yapıyor:** Rapor kartları (başlık, açıklama, satır sayısı, sorgu sayısı, güncelleme aralığı); görünür tek rapor Baskı
  Öneri, `baski-oneri-tahmin` ve `ilk-baski` gizli (`ManagementHome.tsx:8-10`, `management/__init__.py`).
- **Kim:** Genel müdür, yayın/satış yöneticileri.
- **Bugün AI:** Yok.
- **Beklenti:** Her raporun «bu hafta ne değişti» satırı.
- **Yapabileceklerimiz:**
  - **Rapor kartına değişim cümlesi** — önceki önbellek ↔ yeni önbellek farkı (kural: kaç kitap Risk/Acil'e girdi/çıktı) +
    1 cümle · değer 2 · S (0,5 g).
- **Eksik:** Tek rapor; yeni rapor hem arka uç modülü hem `REPORT_ROUTES` satırı ister.

### Baskı önerisi (`/yonetim-raporlari/baski-oneri`)
Görünümler: Baskı Tekrar · Yeni Kitap · ZEKİ AI Tahminleme (`management/baski_oneri.py:444-472`).
- **Ne yapıyor:** Power BI raporunun birebir karşılığı: kitap başına satış hızı, stok, tükenme, öneri seviyesi (Risk/Acil …
  Yeterli Stok); sanal kaydırmalı tablo, süzgeç, her kolonda kaynağı göster (SQL), «nasıl hesaplandı», CSV, 5 dk tazeleme.
  Kaynak: `V_SatisRaporu_<yıl>`, `EOS_DEPO_STOK_KONTROL_211`, CRM `powerbikitap`, `new_baskioneri`, `new_siparis`.
- **Kim:** Yayın koordinatörü, prodüksiyon müdürü, genel müdür, satış müdürü.
- **Bugün AI:** **Tahmin motoru (zaman serisi)** — günde bir, kitap başına 12 ay; sekmede p50 tahmin, p80 «temkinli» yol,
  tükenme ayı (p50/p80), güven süzgeci, geriye dönük sınama (`zeki_tahmin.py:36,46,123-145,199-200,388-460`). Dil modeli yok.
- **Beklenti:** Neden bu kitap Risk/Acil — tek cümle; Power BI önerisi ile tahmin önerisi ayrıştığında hangisine güvenmeli;
  baskı adedi önerisinin aralığı; haftalık «yeni girenler» özeti.
- **Yapabileceklerimiz:**
  - **Satır açıklaması** — seçili kitap için hız, stok, tükenme (kural ve tahmin) ve iki önerinin farkını 2 cümleyle anlatır ·
    teknik: özet + sayı denetimi · değer 4 · S (1 g) · koruma: öneri seviyesi değişmez.
  - **Ayrışma listesi** — Power BI seviyesi ile tahmin seviyesinin ayrıştığı kitaplar (kural) + geriye dönük sınamaya göre
    hangi kitap tipinde hangisinin daha isabetli olduğu (SQL) · AI küçük · değer 4 · S (1 g).
  - **Baskı adedi aralığı** — «ai_baski» adedini p50–p90 arası iki değerle göstermek (p10/p90 zaten hesaplanıyor) ·
    değer 4 · S (0,5 g) · koruma: aralık etiketli.
  - **Mevsimsellik düzeltmesi** — stok kartında yazılı «okul sezonu zirvesini eksik tahmin ediyor» sorununa: okul/sezon
    kitaplarında kovaryat (geçen yılın aynı ay payı) ile sınama; tahmin motoru kovaryat almıyorsa kural düzeltme · değer 4 ·
    M (2–3 g) · koruma: geriye dönük sınamada iyileşmezse açılmaz (M10'daki `beta = 0` kararı gibi).
- **Eksik:** Tahmin servisine ulaşılamazsa sekme boş (`zeki_tahmin.py:413,483`); depo stok görünümü `_211` adlı, 2026'yı
  kapsadığı **doğrulanmadı**.

## M9 Fiyatlama ve maliyet

### Fiyatlama ve maliyet (`/fiyatlama`)
Bölümler: Kitap hesabı · Analizler ve onay · Gerçekleşen · Backlist revizyonu · Veri ve varsayımlar
(`src/canvas/pricing/PricingScreen.tsx:98-102`).
- **Ne yapıyor:** Kitap maliyet kalemleri, başabaş, kapak fiyatı önerisi, baskı adedi senaryoları, kanal fiyat matrisi;
  «Veriden öner» (kural, `/pricing/suggest`); analiz → onaya gönder → rol bazlı onay; gerçekleşen marj; backlist toplu zam
  teklifi ve onayı; rakip fiyatı elle giriş (`MarketPrices.tsx`); varsayılanlar. Hesap saf fonksiyon (`pricing/model.py`).
  Kaynak: Logo INVOICE/STLINE/ITEMS/SRVCARD/CLCARD, CRM `new_kitapBase`, `new_sozlesmeBase`, `new_UretimBase`.
- **Kim:** CFO, yayın yönetmeni, prodüksiyon müdürü, satış müdürü (kanal fiyatı).
- **Bugün AI:** Yok.
- **Beklenti:** «Bu kitap için doğru kapak fiyatı ne, benzerleri ne?»; zam turunda hangi kitapların fiyata duyarlı olduğu;
  rakip fiyatlarının kolay toplanması; onaycıya gerekçe; maliyet artışı beklentisi.
- **Yapabileceklerimiz:**
  - **Onay gerekçesi metni** — analizdeki maliyet, başabaş, emsal fiyatları, önerilen fiyat (kural) → onaycıya 3–4 cümle ·
    teknik: özet + sayı denetimi · değer 4 · S (1 g).
  - **Emsal kitap bulma (anlamsal)** — sayfa/ebat/kategori kuralının yanına özet gömmesiyle en yakın 10 kitabın fiyat
    ve satış adedi (SQL) · teknik: gömme/benzerlik · değer 4 · M (2 g) · koruma: fiyatı model önermez; emsal listesi gösterilir.
  - **Fiyat duyarlılığı işareti (Backlist)** — geçmiş zamlarda (PRCLIST değişimi) önce/sonra 3'er ay adet değişimi (SQL,
    kural) · AI değil istatistik; model yalnız özetler · değer 4 · M (2–3 g) · koruma: az örnekte «ölçülemedi».
  - **Rakip fiyatı belgeden** — rakip katalog/fiyat listesi (PDF/Excel) yüklenince ISBN/ad eşleştirme (M33 kalem eşleştirme
    kalıbı: ISBN → ad → `choose`) · değer 3 · M (2 g) · koruma: web taraması yok; belge insan getirir.
  - **Birim maliyet beklentisi** — M52 birim baskı maliyeti ve kağıt fiyatı serisinden tahmin bandı, senaryoya «beklenen
    maliyet» seçeneği · teknik: zaman serisi tahmini · değer 3 · M (bkz. Lojistik M52) · koruma: seçenek; varsayılan değil.
- **Eksik:** Hedef marj, genel gider, satış oranı elle (`DataPane.tsx:119`); döviz avansında kur elle (`CalcPane.tsx:306-309`).

## M10 İlk baskı tahmini

### İlk baskı (`/ilk-baski`)
Sekmeler: Yayımlanacak kitaplar · İlk satış takibi · Tahmin ne kadar tutuyor (`src/canvas/first-print/FirstPrintScreen.tsx:15-17`).
- **Ne yapıyor:** Yayımlanacak kitaplar ve senaryoları; ilk satışı takip edilen kitaplar ve «kötümserin altında» kalanlar;
  sınama (model ↔ yalnız CRM emsali ↔ son 12 ay ortancası). Kaynak: `V_SatisRaporu_<yıl>`, CRM emsal bağları
  (`new_new_kitap_new_emsalkitap3Base`), `semantic_first_print_decisions`.
- **Kim:** Yayın yönetmeni, satış müdürü, prodüksiyon (onay), genel müdür.
- **Bugün AI:** Emsal puan ağırlıklı ortanca — **deterministik**, ekranda «ZEKİ AI emsal tahmini» diye etiketli
  (`ilk_baski_model.py:382`, `BacktestTab.tsx:22`). Tahmin motoru bağlı ama kapalı: pazar düzeltmesi `beta = 0`, sınamada
  iyileştirmedi (`ilk_baski_model.py:30-35`, `ilk_baski.py:428-434,589-591`). Dil modeli yok.
- **Beklenti:** Kötümser senaryonun altında kalan kitaplar için erken uyarı ve neden; «ne kadar tutuyor» sınamasının düz
  yorumu.
- **Yapabileceklerimiz:**
  - **İlk satış takibi uyarı özeti** — kötümserin altında kalan kitaplar: hangi kanal/bölge eksik (SQL) → 2 cümle; M29
    dağılımına bağlantı · değer 4 · S (1 g).
  - **Güncellenen tahmin (ilk haftalar geldikçe)** — ilk 4–8 haftanın gerçekleşeni ile emsal eğrisini yeniden ölçekleme
    (kural, Bayes benzeri güncelleme) · AI değil istatistik · değer 4 · M (2 g) · koruma: sınama sekmesinde ölçülmeden açılmaz.
- **Eksik:** «ZEKİ AI» adı kural hesabına verilmiş (ürün kararı; kullanıcıyı yanıltmaması için «emsal tahmini» notu yeterli
  olabilir).

### Kitap tahmini (`/ilk-baski/kitap/:code`)
- **Ne yapıyor:** Senaryo kartları, birikimli satış grafiği (6/12 ay), ilk baskı önerisi, kanal dağılımı, gerekçe (kural:
  emsal nedeni sayımı, `ilk_baski.py:246-260`), emsal tablosu, karar kutusu (adet, satış + üretim ayrı onay, geri çek).
- **Kim:** Yayın yönetmeni, satış, prodüksiyon.
- **Bugün AI:** Yok (kural gerekçe; deterministik tahmin).
- **Beklenti:** Emsallerin gerçekten benzer olduğundan emin olmak; kurula sunulacak karar notu.
- **Yapabileceklerimiz:**
  - **Emsal içerik denetimi** — her emsal için «konu/okur kitlesi bakımından benzer mi» kapalı seçimi (M29'daki
    `_model_screen` kalıbı, özet + hedef yaş ile); «benzemez» çıkan emsal işaretlenir, ağırlığı insan değiştirir · değer 4 ·
    S (1–2 g) · koruma: sınama sekmesinde etkisi ölçülür; kendiliğinden ağırlık değiştirmez.
  - **Karar notu taslağı** — senaryolar, önerilen adet, emsaller → 1 paragraf (onay kutusuna eklenir) · değer 3 · S (0,5 g) ·
    koruma: sayı denetimi.
- **Eksik:** —

### Yeni kitap tahmini (`/ilk-baski/yeni`)
- **Ne yapıyor:** CRM'de kartı olmayan kitabın özellikleri formla girilir, «Tahmin et» (`FreeForecast.tsx`).
- **Kim:** Yayın yönetmeni (teklif/başvuru aşamasında), editör.
- **Bugün AI:** Yok.
- **Beklenti:** Başvuru dosyasından/sinopsisten formun dolması; benzer eski kitapların bulunması.
- **Yapabileceklerimiz:**
  - **Sinopsisten form önerisi** — yapıştırılan özet/künye metninden kategori, hedef yaş, dizi (kapalı listeler, `choose`) ve
    en yakın emsaller (gömme) · değer 4 · M (2 g) · koruma: alanlar formda, insan düzeltir; tahmin yine emsal kuralı.
- **Eksik:** —

## M46 Bütçe ve hedefler

### Bütçe ve hedefler (`/butce`)
Sekmeler: İzleme · Kitap hedefleri · Yeni kitap programı · Departman bütçesi · Senaryolar ve onay
(`src/canvas/budget/BudgetScreen.tsx:21-25`).
- **Ne yapıyor:** Üç senaryolu (muhafazakâr / temel / iyimser) taslak «ZEKİ AI önerisi oluştur» (**kural**, `budget.py:12`
  «model yok»); onay akışı; kitap ekle/çıkar; departman aylara dağıtma; izleme grafiği; sapma uyarısı e-postası
  (`budget_api.py:115`); CSV. Backlist tabanında Baskı Öneri tahmininin p50'si seçenek olarak (`budget.py:506-623`,
  `GenerateSheet.tsx:69-71`). Kaynak: Logo STLINE/EMFLINE/EMUHACC/EMCENTER, CRM `powerbikitap`.
- **Kim:** CFO, bütçe/finans analisti, departman yöneticileri, genel müdür (onay).
- **Bugün AI:** Dil modeli yok; tahmin motoru çıktısı dolaylı (yalnız p50).
- **Beklenti:** Senaryoların neye dayandığının açıklaması; sapma nedenleri; yıl sonu gerçekleşme tahmini (tahmini kapanış);
  departman bütçesi taslağı.
- **Yapabileceklerimiz:**
  - **Senaryo bantlarını tahmin kantillerine bağlamak** — muhafazakâr/temel/iyimser = p10/p50/p90 (bugün yalnız p50 okunuyor,
    `budget_sources.py:307`) · teknik: zaman serisi tahmini (mevcut) · değer 5 · S (1–2 g) · koruma: kural senaryosu
    yanında, kaynak etiketi.
  - **Tahmini yıl sonu kapanışı (İzleme)** — gerçekleşen + kalan aylar için tahmin bandı; «hedefe ulaşma olasılığı» kaba
    değil bant olarak · değer 5 · M (2 g) · koruma: bant ve kaynak her zaman görünür.
  - **Sapma nedeni taslağı** — M45 ile ortak (bkz. Bütçe–gerçekleşme sekmesi) · değer 4 · (M45 işiyle).
  - **Departman gideri aylık dağılım önerisi** — geçmiş gider mevsimselliğine göre (kural/ tahmin motoru) · değer 3 · S (1 g).
- **Eksik:** «ZEKİ AI önerisi» adı kural hesabına verilmiş; tahmin dosyası yoksa geçmiş satışa düşüyor (`GenerateSheet.tsx:71`).

## M47 Risk ve uyum

### Risk ve uyum (`/risk-uyum`)
Sekmeler: Özet · Risk kaydı · Göstergeler · Uyum · BCP ve sigorta · Raporlar (`src/canvas/risk/RiskScreen.tsx:22-27`).
- **Ne yapıyor:** Isı haritası, gözden geçirme kuyruğu, geciken aksiyonlar, kırmızı göstergeler (KRI: Logo veri gecikmesi,
  maliyetsiz satış payı, müşteri/tedarikçi yoğunlaşması, vadesi geçmiş 90+, karşılıksız çek, süresi bitmiş ama satan kitap …),
  uyum takvimi, BCP ve sigorta, çeyreklik brifing (Word). Kaynak: Logo INVOICE/STLINE/PAYTRANS/CSTRANS, CRM
  `new_sozlesmeBase`, diğer modüllerin hazır sonuçları; tablolar `semantic_risk_*`, `semantic_compliance_*`.
- **Kim:** CFO, risk/uyum sorumlusu, hukuk, KVKK sorumlusu, yönetim kurulu (brifing).
- **Bugün AI:** Kategori önerisi — kapalı seçim (`risk.py:1591` `classify`, `risk_api.py:268-280`, «Zeki AI kategori önersin»
  `RiskScreen.tsx:304-348`); eşiği aşan gösterge için risk kaydı taslağı (`risk.py:1641`, `risk_api.py:282-304`,
  `RiskScreen.tsx:238-271`); çeyreklik brifing metni, olgu dışı sayı → kural metni (`risk.py:1729`, `risk_api.py:597-615`,
  `ReportsTab.tsx:18-42,103`). Kapı `llm_for("risk")` (`risk_api.py:71`).
- **Beklenti:** Göstergenin gelecekte eşiği aşma olasılığı; mevzuat değişikliği belgesinin özeti ve etkilenen yükümlülük;
  BCP/politika taslağı; kanıt belgesinin kontrolü.
- **Yapabileceklerimiz:**
  - **KRI öncü tahmini** — sayısal göstergelerin (vadesi geçmiş 90+, maliyetsiz satış payı, yoğunlaşma) aylık serisine tahmin
    bandı; «3 ay içinde eşiği aşma riski» rozeti · teknik: zaman serisi tahmini · değer 4 · M (2 g) · koruma: eşik ve kırmızı
    durum yine ölçülen değerden; tahmin ayrı rozet.
  - **Mevzuat belgesi özeti (M47 §13; kodda yok)** — yüklenen Resmî Gazete/ tebliğ PDF'inden alıntılı özet ve etkilenen uyum
    kalemi önerisi (kapalı seçim: mevcut `semantic_compliance_items`) · teknik: belge okuma + alıntı denetimi (M33 şartname
    kalıbı) + `choose` · değer 4 · M (2 g) · koruma: web kapalı; hukuk onayı.
  - **BCP / politika taslağı (M47 §13; kodda yok)** — şablondan, «taslak — hukuk onayı» · değer 3 · S (1 g).
  - **Kanıt belgesi uygunluk kontrolü** — yüklenen kanıt (poliçe, sertifika) tarih/kapsam alanlarını alıntıyla çıkarır, uyum
    kaleminin son tarihiyle karşılaştırır (kural) · değer 3 · M (2 g).
  - **Risk sohbet verisi** — `chat_topics.json`'da `risk` konusunun `data: []`; risk kaydı ve göstergelerin kataloğa
    eklenmesiyle «hangi riskler kırmızı» sorusu sohbetten cevaplanır · değer 3 · S (1 g) · koruma: yetki süzgeci.
- **Eksik:** Hazır göstergelerin eşikleri boş gelir (`risk.py:9-10`), eşik girilene kadar kırmızı/yeşil yok.

### Risk kartı (`/risk-uyum/risk/:id`)
- **Ne yapıyor:** Kabul (puanı insan verir) / ret, gözden geçir, düzenle, aksiyon ekle, kanıt yükle; Zeki AI taslağından gelen
  kayıtta kabul uyarısı (`RiskCard.tsx:59,156`).
- **Kim:** Risk sahibi, risk/uyum sorumlusu.
- **Bugün AI:** Kaydın kendisi taslaktan gelebilir (yukarıda); kartta model çağrısı yok.
- **Beklenti:** Aksiyon planı önerisi; gözden geçirme notunun özeti.
- **Yapabileceklerimiz:**
  - **Aksiyon önerisi** — risk kategorisi ve nedeni → 3 önleyici/azaltıcı aksiyon taslağı (sorumlu ve tarih insan) · değer 3 ·
    S (1 g) · koruma: puan (olasılık × etki) model tarafından verilmez.
- **Eksik:** —

---

**Alan: Satış ve saha (`satis`)**

Menü: 8 öğe (`ilk-dagilim`, `saha`, `bayi-risk`, `okul-tanitim`, `musteri-iliskileri`, `musteri-veri-sagligi`,
`kurumsal-satis`, `ihale`). Rota: 17. Ortak sohbet konusu `satis` (M29, M30, M32, M38, M59) ve `kurumsal` (M31, M33)
— `backend/semantic_bridge/chat_topics.json`. Telefon kullanımı VPN üzerinden (README kararı).

## M29 İlk dağılım

### İlk dağılım listesi (`/ilk-dagilim`)
Sekmeler: Dağılım bekleyenler · İzlenen kitaplar · Bölgem · Uyarılar (`src/canvas/distribution/DistributionScreen.tsx:21-24`).
- **Ne yapıyor:** Son N günde depoya girip planı olmayan/onayda/onaylı/sevkte kitapları listeler, «Öneri oluştur» ile plan
  üretir; İzlenen = onaydan sonraki 8 hafta plan→sevk→fatura→iade (`TrackingTab.tsx`); Bölgem = BMT'nin kendi carilerine
  düşen adetler, telefonda salt okunur (`MyRegion.tsx`); Uyarılar = plan_yok, sevk_gecikti, hic_satmadi, tukendi (günde 2 kez).
- **Kim:** Satış müdürü (planı düzeltir), lojistik (onaylar), BMT/bölge temsilcisi (telefonda «bölgeme ne geliyor»).
- **Bugün AI:** Listede yok; örnek sorular Genel bakış soru kutusuna gider (`DistributionScreen.tsx:37`). Model plan
  üretiminde çalışır (aşağıda). Uyarılar kuraldır (`distribution.py` başlık belgesi).
- **Beklenti:** «Hangi kitabın planına önce bakayım?»; izlenen kitaplarda haftalık «ne ters gidiyor» özeti; hiç satmayan
  bölge için olası neden; BMT için «bu hafta bölgeme gelen kitaplar ve kime ne kadar» sesli/kısa özet.
- **Yapabileceklerimiz:**
  - **Haftalık takip özeti** — izlenen her kitap için 3–4 cümle: plan/sevk/fatura/iade farkı en büyük bölge, gecikmeli
    sevk sayısı · veri: TrackingTab'ın Logo sevk (STLINE TRCODE 8) + faturalı satış + iade tabloları · teknik: olgu JSON →
    özet (`chat`), `safe_model_text` sayı denetimi (distribution.py `_rationale` ile aynı) · değer 4 · S (1 g) · koruma:
    olgu dışı sayı → kural metni.
  - **Takipte beklenen bant** — izlenen kitabın gerçekleşen haftalık satışını bir bantla karşılaştırır: baskı tekrarında
    kitabın kendi geçmişinden tahmin motoru (p10–p50–p90), yeni kitapta emsal kitapların 8 haftalık eğrisinin çeyrekleri
    (kural) · veri: Logo faturalı satış haftalık seri · teknik: zaman serisi tahmini (sunucudaki tahmin motoru) + kural ·
    değer 4 · M (2 g) · koruma: «tahmin» etiketi ve güven aralığı her zaman görünür, model rakam yazmaz.
  - **Uyarı açıklaması** — «hiç satmadı» uyarısına olası neden seçimi (sevk yok / sevk var fatura yok / bölgede benzer kitap
    da düşük / iade yüksek) · teknik: kural önce, belirsizde `QueuedLlm.choose` · değer 3 · S (1 g).
- **Eksik:** Logo .155 kopyası 17.08.2026'da donmuş; takip ve uyarı «veri sonu» gününe göre çalışıyor (kodda doğru
  işaretli) ama canlı Logo (.25) bağlanmadan takip anlamsız kalır.

### Kitabın dağılım planı (`/ilk-dagilim/:stok`)
- **Ne yapıyor:** Özet (hedef, stok, rezerv), Zeki AI gerekçesi ve benzer kitaplar, bölge × kanal matrisi, müşteri listesi;
  taslakta satır/hücre düzeltme (gerekçeli), iki göz onayı, revize, sevk listesi Excel (`PlanEditor.tsx`). Adetler kural:
  benzer kitapların 8 haftalık cari payı × M46 hedefi, en büyük kalan yuvarlaması (`distribution.py` başlık belgesi).
- **Kim:** Satış müdürü (öneriyi düzeltir, gönderir), lojistik/onaycı, satış analisti.
- **Bugün AI:** (1) Benzer kitap ayıklama — her aday için «benzer / az / değil» kapalı seçim, p ≥ 0,90 ve marj ≥ 0,50
  (`distribution.py:758-790`, `llm.choose` satır 780); (2) 3–5 cümle gerekçe, olgu dışı sayı varsa kural metni
  (`distribution.py:823-845`). Kapı: `rt().llm_for("dagilim")` (`distribution_api.py:48`).
- **Beklenti:** Benzer kitap seçiminin içerik bakımından da doğru olması (konu, yaş grubu), düzeltmelerin nedenini
  öğrenen bir öneri, onaycı için «önceki sürümden ne değişti» özeti.
- **Yapabileceklerimiz:**
  - **Benzerlik sorusuna içerik ekle** — istem bugün yalnız ad/yazar/kitaplık/yayınevi taşıyor (`_describe`,
    `distribution.py:755`); CRM `new_kitapBase` özet, hedef yaş, tür, sayfa, fiyat eklenir · teknik: aynı `choose` ·
    değer 4 · S (1 g) · koruma: özet HTML temizlenir, kişisel veri yok.
  - **Anlamsal emsal havuzu** — M10 emsal puanının kaçırdığı (yeni yazar, yeni dizi) kitaplar için özet metninin gömmesiyle
    en yakın 20 aday; sonra aynı `choose` ayıklaması · veri: `new_kitapBase` özet + ITEMS · teknik: gömme/benzerlik
    (köprüdeki gömme servisi `llm_openai.py:149`) · değer 4 · M (2–3 g) · koruma: aday yalnız öneri, puan kuraldan.
  - **Düzeltme gerekçesi sınıfı ve öğrenme raporu** — elle düzeltmelerin serbest gerekçesi kapalı kümeye (bayi talebi /
    stok / bölgesel etkinlik / geçmiş iade / diğer) · teknik: `choose` · değer 3 · S (1 g) · çıktı: «öneri hangi bölgede
    sistematik düşük/yüksek» raporu (sayılar SQL).
  - **Revizyon farkı özeti** — «Revize et» sürümünde onaycıya «şu 5 carinin adedi değişti, toplam +X» metni · teknik:
    fark SQL + özet `chat` + sayı denetimi · değer 3 · S (0,5 g).
- **Eksik:** Hedef yoksa toplam adet emsal ortancasıdır; M46 hedefi olmayan kitapta bu açıkça planın başında yazmalı
  (koddan doğrulanmadı).

## M30 Saha satış ve tahsilat

### Saha ve tahsilat (`/saha`)
Sekmeler: Bugün · Tahsilat (Vadesi geçmiş / Onay bekleyen / Reddedilen) · Ödeme planları · Haftalık rapor
(`src/canvas/field/FieldScreen.tsx:18-21`, `CollectionsTab.tsx`).
- **Ne yapıyor:** Telefonun ilk ekranı: 3 sayı, bugünün planlı ziyaretleri, kural puanıyla sıralı müşteri listesi
  (gerekçe çipleriyle, `TodayScreen.tsx`); tahsilat FIFO kovaları + CRM tahsilat onay akışı (yalnız görünür); ödeme planı
  önerisi (kural: tutar = vadesi geçmiş, taksit = ödeme hızı) → onay; müdüre temsilci × hedef–gerçekleşme raporu.
- **Kim:** BMT/saha temsilcisi (telefonda, araçta, kitapçı önünde), bölge satış müdürü, tahsilat/muhasebe.
- **Bugün AI:** Reddedilen tahsilatın serbest metin nedeni kapalı kümeye (`field_sales_api.py:143-170`, `llm.choose`
  satır 164; ekranda «Zeki AI'ya göre» `CollectionsTab.tsx:156`). Öncelik puanı kural (`field_sales.py:293` WEIGHTS),
  model puan vermez. «Zeki AI'ya sorun» örnek soruları (`TodayScreen.tsx:205-211`) Genel bakış soru kutusuna gider.
- **Beklenti:** Sabah telefonda «bugün kime gitmeliyim ve neden» tek paragraf; araçta sesli not; tahsilat konuşması için
  hazır cümleler; haftalık raporun otomatik yorumu (müdür).
- **Yapabileceklerimiz:**
  - **Sabah saha brifi** — temsilcinin günü için 4–5 cümle: planlı ziyaretler, en yüksek 3 öncelik ve gerekçe çipleri,
    vadesi geçmiş toplam · veri: `semantic_field_signals`, `semantic_field_portfolio` · teknik: özet + `numbers_ok`
    (`field_sales.py` mevcut denetim) · değer 5 · S (1 g) · koruma: temsilci kapsamı süzgeci aynen, kural metni yedek.
  - **Sesli ziyaret notu** — telefonda konuşarak not; metne çevrilir, sonra model ton/sonraki adım/ödeme sözü alanlarını
    önerir (M31 `ai_note_fields` kalıbı) · teknik: konuşma→metin (sunucuda servis **doğrulanmadı**) + alan çıkarma ·
    değer 4 · M (2–3 g) · koruma: ses kaydı saklanmaz, yalnız onaylı metin; gizli not modele gitmez (`VisitNoteSheet.tsx:161`).
  - **Haftalık rapor yorumu (müdür)** — temsilci × hedef tablosundan 5 cümle: kim geride, tahsilatta kim iyi, ziyaret
    açığı · teknik: özet + sayı denetimi · değer 3 · S (1 g) · koruma: yalnız `saha.performans` yetkisinde; model sıralama
    yapmaz, tablo sırası SQL.
  - **Tahsilat konuşma notu** — vadesi geçmiş cari için kibar hatırlatma cümleleri ve ödeme planı seçenekleri metni
    (rakamlar kural planından) · değer 3 · S (0,5 g) · koruma: gönderim yok, temsilci okur.
- **Eksik:** CRM tahsilat girişi portal dışı; ret nedeni sınıflaması yalnız serbest metin doluysa çalışıyor (doğru), ret
  sınıfı dağılımı raporu yok.

### Müşteri brifingi (`/saha/musteri/:code`)
- **Ne yapıyor:** Tek sayfa: Özet · Ödeme · Sipariş · Hedef · Öneri · Notlar; alt çubuk: not bırak, planla, ödeme planı
  öner, öne al (`CustomerBrief.tsx:15-17`). Kitap önerisi kural: 24 ayda almadığı, aynı şehir+kanaldaki benzer carilerin
  aldığı ve yeni çıkan kitaplar (`field_sales.py:1449-1475`).
- **Kim:** Saha temsilcisi (ziyaretten 5 dk önce, telefonda), müdür.
- **Bugün AI:** 3 cümle özet, sayı denetimli; «Zeki AI yazsın» düğmesi (`field_sales_api.py:443-460`,
  `CustomerBrief.tsx:113-118`); ziyaret sonrası takip e-postası **taslağı** (gönderilmez, `field_sales_api.py:462-480`).
- **Beklenti:** Öneri listesinin «neden bu kitap bu kitapçıya» açıklaması; son notların özeti; itiraz/şikâyet
  geçmişinin tek cümlesi; sesli okunabilir brif.
- **Yapabileceklerimiz:**
  - **Kitap önerisine uygunluk süzgeci** — kural adaylarını (benzer cari alımı) kitapçının kanal/kategori karmasıyla
    «uygun / belki / değil» diye ayıklar, 1 satır gerekçe · veri: STLINE kategori (ITEMS.SPECODE) karması, `new_kitapBase`
    özet/yaş · teknik: `choose` + gerekçe · değer 4 · M (2 g) · koruma: sıra kuraldan, model yalnız ayıklar.
  - **Not geçmişi özeti ve tema** — portal `semantic_saha_ziyaret` + CRM `new_etkinlikBase` notlarından son 5 notun 2
    cümlesi + etiket (tahsilat sözü / şikâyet / sipariş talebi / iade talebi) · teknik: `choose` + özet · değer 4 · S (1 g)
    · koruma: gizli not hariç, kişi adları maskeli.
  - **Sesli brif** — mevcut özet metnini telefonda okutma (tarayıcı konuşma sentezi; ek model gerekmez) · değer 2 · S (0,5 g).
- **Eksik:** —

## M59 Bayi riski

### Bayi riski (`/bayi-risk`)
Sekmeler: Pano · Bayiler · Limit önerileri · Aksiyonlar · Kurallar (`src/canvas/dealers/DealersScreen.tsx:21-25`).
- **Ne yapıyor:** Günlük kural skoru (6 bileşen, toplam 100) ve A/B/C/D segmenti (anahtar hesaplar ayrı eşikle),
  kötüleşenler, vadesi geçmiş; limit önerisi (kural) → müdür onayı → «CRM'e işlenecek» listesi; aksiyonlar; sürümlü kural
  (taslak → onay, önizleme) (`dealers.py` başlık belgesi).
- **Kim:** Satış müdürü, finans/kredi kontrol, CFO, BMT (kendi carileri).
- **Bugün AI:** Skor ve segment **modelsiz** (`dealers.py` belge). Limit önerisinin gerekçe cümlesi modelden, sayı
  denetimli (`dealers_api.py:95-110`, `LimitsTab.tsx:54`). Pano'da «Zeki AI'ya sor» örnek soruları (`PanoTab.tsx:111`).
- **Beklenti:** Haftalık «kötüleşenler neden kötüleşti» özeti; kural değişikliği önizlemesinin yorumu; tahsilat
  gecikmesinin gelecekteki seyri (erken uyarı); bayi ziyaret notlarından sinyal.
- **Yapabileceklerimiz:**
  - **Kötüleşme özeti (Pano)** — segmenti düşen carilerde hangi bileşenin değiştiği (SQL) + 3–4 cümle okunur özet ·
    teknik: özet + sayı denetimi · değer 4 · S (1 g).
  - **DSO / tahsilat süresi tahmini** — bayinin aylık DSO ve vadesi geçmiş serisinden 3 ay ileri bant (p10–p90);
    «bant üstü bozulma» erken uyarı sinyali olarak skorda değil ayrı rozet olarak · veri: CLFLINE/PAYTRANS aylık seri
    (`ortalama_tahsilat_suresi`) · teknik: zaman serisi tahmini · değer 4 · M (2 g) · koruma: skoru değiştirmez (skor
    sürümlü kural kalır), güven aralığı gösterilir, cariye aleyhe otomatik sonuç yok.
  - **Ziyaret/CRM not sinyali** — `new_etkinlikBase.new_info`, `new_Tahsilatinfo` serbest metinleri kapalı kümeye
    (tahsilat sözü / şikâyet / iade talebi / kapanış-devir sinyali / diğer); karta «son 90 gün not sinyali» · teknik:
    `choose` gece `BATCH` · değer 4 · S (1–2 g) · koruma: skor bileşeni yapılmaz (kural sürümüne girmesi ayrı karar).
  - **Kural önizleme yorumu (Kurallar)** — taslak kuralın segment dağılımını nasıl değiştirdiğini 3 cümleyle anlatır ·
    değer 2 · S (0,5 g).
- **Eksik:** Analizdeki «ziyaret notlarının özeti + tema etiketi» (M59 §13) kodda yok (`dealers*.py`'de tema/not özeti
  bulunmadı).

### Bayi kartı (`/bayi-risk/:code`)
- **Ne yapıyor:** Skor ve bileşenleri · alacak · 12 ay seyri · CRM limit ve risk onayı · limit önerisi · aksiyonlar ·
  notlar; alt çubuk: Risk brifi, not bırak, aksiyon aç (`DealerCard.tsx:12-14`).
- **Kim:** BMT (ziyaret öncesi, telefonda), satış müdürü, kredi kontrol.
- **Bugün AI:** Ziyaret öncesi risk brifi — kısa özet + «konuşulacak üç madde», sayı denetimli, girdi değişmedikçe model
  çağrılmaz (`dealers_api.py:150-165`, `BriefSheet.tsx:11-14`). Skor brifte yazmaz.
- **Beklenti:** «Neden D?» sorusuna düz cümle; çek/senet olayının anlamı; ödeme planı konuşmasına hazırlık.
- **Yapabileceklerimiz:**
  - **«Neden bu segment» açıklaması** — bileşen katkılarını (SQL) sıralı cümleye çevirir · değer 3 · S (0,5 g) · koruma:
    yalnız iç kullanıcıya, bayiye söylenmez.
  - **Bakiye/ödeme seyri bandı** — 12 ay seyrine 3 ay tahmin bandı (tahmin motoru) · değer 3 · S (1 g; üstteki DSO işinin
    parçası).
- **Eksik:** —

## M31 Okul tanıtım

### Okul tanıtım ve ziyaret (`/okul-tanitim`)
Sekmeler: Bu hafta · Okullar · Bayi eşleştirme (onay kuyruğu) · Dönem raporu · Takvim ve bölge verisi
(`src/canvas/schools/SchoolsScreen.tsx:37-41`).
- **Ne yapıyor:** Haftalık plan (kural: öncelik puanı, son ziyaret, aynı ilçe aynı gün; temsilci düzeltir, yetkili onaylar);
  okul listesi (süzgeç, arama); Zeki AI'ın önerdiği ve temsilcilerin yönlendirdiği okul↔bayi eşleşmelerinin onay kuyruğu;
  dönem özeti (plan gerçekleşmesi, penetrasyon, örnek→satış); ilçe gelişmişlik endeksi ve akademik takvimin elle yüklenmesi.
- **Kim:** Okul tanıtım temsilcisi (telefonda), saha yöneticisi (onay), satış müdürü (dönem raporu).
- **Bugün AI:** Bayi eşleştirme önerisi (`school_visits.py:1713` `ai_pick_dealer`, kapalı seçim), serbest okul adının
  ziyaret yerine eşlenmesi (`school_visits.py:1694` `ai_pick_school`; `semantic_school_name_matches`), öncelik gerekçe
  cümlesi (`school_visits.py:1655` `ai_reason`). Plan ve puan kural.
- **Beklenti:** Haftalık rotanın akıllı kurulması; dönem raporunun yorumlu özeti; okul türü/kademe için hazır sunum
  anlatısı; yüklenen takvim PDF'inin okunması.
- **Yapabileceklerimiz:**
  - **Dönem raporu yorumu (K3)** — penetrasyon, örnek→satış ve bayi satış değişiminden 5 cümle · teknik: özet + sayı
    denetimi (`numbers_ok` modülde var) · değer 3 · S (1 g).
  - **Akademik takvim belgesinden satır çıkarma** — elle yüklenen MEB takvim PDF/DOCX'inden tatil/sınav haftası satırlarını
    alıntılı çıkarır, kullanıcı onaylar (M33 şartname özeti kalıbı) · teknik: belge okuma + alıntı denetimli JSON · değer 3
    · M (1–2 g) · koruma: web taraması kapalı, belge insan getirir.
  - **Rota sıralaması** — aynı gün okulların sırası ilçe/mahalle yakınlığıyla (kural, harita servisi yoksa ilçe kodu) ·
    AI değil, kural; not olarak.
- **Eksik:** Konum/harita verisi yok; «aynı ilçe aynı gün» ilçe adına dayanıyor.

### Okul kartı (`/okul-tanitim/:id`)
- **Ne yapıyor:** Profil, öncelik ve gerekçesi, Zeki AI ziyaret önerisi, bağlı/önerilen bayi, kademeye uygun katalog + PDF,
  geçmiş ziyaretler (portal + CRM), okul siparişleri; ziyaret raporu (telefondan ~1 dk) (`SchoolCard.tsx:13-14`,
  `VisitReportSheet.tsx`).
- **Kim:** Temsilci (okul kapısında), saha yöneticisi.
- **Bugün AI:** 2–3 cümle ziyaret önerisi, sayı denetimli, model yoksa kural (`school_visits.py:1665-1671`,
  `SchoolCard.tsx:131-143`); serbest nottan alan önerisi «Nottan alanları doldur» (`school_visits.py:1735`,
  `VisitReportSheet.tsx:72-81,206`).
- **Beklenti:** Kademeye göre kitap seçimi ve öğretmene tek satırlık anlatım; sesli rapor; okul kulübü/etkinlik kiti
  taslağı.
- **Yapabileceklerimiz:**
  - **Katalogda kademe/tema uygunluğu ve öğretmen notu** — analizdeki (M31 §13) «kademe/tema uygunluğu sınıflaması + 1
    satır öğretmen notu» · veri: `new_kitapBase` hedef yaş/sınıf/özet, stüdyo MEB uygunluk hükmü (okunur, üretilmez) ·
    teknik: `choose` + kısa taslak · değer 4 · M (2 g) · koruma: MEB hükmünü model vermez.
  - **Sesli ziyaret raporu** — M30 ile aynı konuşma→metin yolu, ardından mevcut `ai_note_fields` · değer 4 · S (M30
    yapılırsa +0,5 g).
  - **Sunum notu / kulüp kiti taslağı** — okul profiline göre şablondan · değer 2 · S (1 g).
- **Eksik:** Katalog PDF'i hazır; öğretmen notu yok (analizde vardı, kodda bulunmadı).

## M38 Müşteri ilişkileri

### Müşteri ilişkileri özeti (`/musteri-iliskileri`)
- **Ne yapıyor:** Kanal bazında aktif cari, son 12 ay/bu yıl net, yüksek risk, kayıp, veri sağlığı puanı; «bu hafta
  bakılacak cariler» (risk × değer); aksiyonların 30/90 gün sonucu; segmentler; kayıp riskinin nasıl hesaplandığı
  (`CustomersHome.tsx:63-170`).
- **Kim:** Satış müdürü, CRM sorumlusu, genel müdür.
- **Bugün AI:** Ekranın kendisinde yok. Kayıp riski **kural** puanı (`musteri.py` belge; «model puan vermez» ekranda da
  yazılı `CustomersHome.tsx:169`).
- **Beklenti:** «Bu ay kaybettiğimiz müşteriler kim, ortak noktaları ne?»; aksiyon etkinliği yorumu; segment önerisi.
- **Yapabileceklerimiz:**
  - **Aylık müşteri hareketi özeti** — yeni kaybedilen/geri gelen cariler, kanal dağılımı, aksiyon 30/90 gün sonucu
    (SQL) → 5 cümle · değer 4 · S (1 g) · koruma: sayı denetimi.
  - **Kayıp nedeni kümelemesi** — kayıp carilerin kategori/yayınevi kırılımı değişimi (`V_SatisRaporu`) + aksiyon notları
    → neden etiketi (fiyat / rakip / kapanış / kategori kayması / tahsilat sorunu / bilinmiyor) · teknik: `choose` ·
    değer 4 · M (2 g) · koruma: puan kural kalır, etiket yalnız açıklama.
- **Eksik:** —

### Cariler (`/musteri-iliskileri/cariler`)
- **Ne yapıyor:** Kanal, il, temsilci, risk düzeyi, segment süzgeci ve arama; sıralama Risk × değer / puan / 12 ay net /
  bu yıl / en çok düşen / en uzun alımsız / unvan (`AccountsScreen.tsx`).
- **Kim:** Satış müdürü, temsilci, analist.
- **Bugün AI:** Yok (liste). Genel bakış soru kutusu ayrı.
- **Beklenti:** Doğal dille süzme («İstanbul'da 6 aydır almayan kitapçılar»).
- **Yapabileceklerimiz:**
  - **Doğal dil süzgeç** — cümleyi mevcut süzgeç alanlarına (kanal, il, risk, sıralama, gün) çevirir; sorgu yine aynı uç ·
    teknik: kapalı alanlara yapılandırılmış çıktı (her alan için `choose`/sayı ayrıştırma kural) · değer 3 · M (2 g) ·
    koruma: süzgeç ekranda görünür, kullanıcı düzeltir.
- **Eksik:** —

### Cari ayrıntısı (`/musteri-iliskileri/cari/:kod`)
- **Ne yapıyor:** Risk ve nedeni, aylık alım grafiği, aksiyon geçmişi, kitap dağılımı, CRM siparişleri, ziyaretler (M30),
  tahsilat göstergesi; arama yalnız portföy sahibine (`AccountDetail.tsx:1-6`).
- **Kim:** Temsilci, müdür.
- **Bugün AI:** 1–2 cümle neden özeti, «Zeki AI yazsın», sayı denetimli (`musteri_api.py:270-285`, `AccountDetail.tsx:80-85`).
- **Beklenti:** Aksiyon önerisi (ne yapmalı), aylık alım eğrisinin beklenenle kıyası.
- **Yapabileceklerimiz:**
  - **Beklenen alım bandı** — carinin aylık alım serisine tahmin bandı; «beklenen altı» işareti kayıp riskinin yanında
    ikinci görüş olarak · teknik: zaman serisi tahmini (yalnız yeterli geçmişi olan carilerde) · değer 3 · M (1–2 g) ·
    koruma: puanı değiştirmez, güven aralığı.
  - **Aksiyon önerisi** — kapalı küme (ara / ziyaret et / yeni çıkan listesi gönder / tahsilat konuş / bekle) + gerekçe ·
    değer 3 · S (1 g).
- **Eksik:** —

### Portföyüm (`/musteri-iliskileri/portfoyum`)
- **Ne yapıyor:** Temsilcinin yalnız kendi carileri; üstte «bu hafta aranacaklar», her kartta tek dokunuşla aksiyon
  (`PortfolioPhone.tsx`).
- **Kim:** Temsilci (telefonda).
- **Bugün AI:** Yok.
- **Beklenti:** Arama öncesi 1 cümle; aramadan sonra sesli aksiyon notu.
- **Yapabileceklerimiz:**
  - **Arama öncesi tek cümle** — cari ayrıntısındaki neden özetinin önbellekten karta taşınması (yeni model işi yok) ·
    değer 3 · S (0,5 g).
  - **Sesli aksiyon notu** — M30 konuşma→metin yolu + aksiyon türü `choose` · değer 3 · S (M30 ile).
- **Eksik:** —

### CRM veri sağlığı (`/musteri-iliskileri/veri-sagligi`)
- **Ne yapıyor:** Logo bağı yok, olası tekrar, kanalı eksik, sahipsiz/ortak hesap, izin çelişkisi, (yetkiliye) güvenlik
  bulguları; «CRM'de düzeltildi» işareti gece doğrulanır (`DataHealthScreen.tsx:1-4`).
- **Kim:** CRM sorumlusu, satış operasyon, KVKK sorumlusu.
- **Bugün AI:** Olası tekrar çiftleri için «aynı firma / farklı / belirsiz» kapalı seçim, gece önceliğiyle, süre bütçeli
  (`musteri_api.py:110-135`, `llm.choose` satır 127); «Zeki AI kararı bekleyen» sayacı (`DataHealthScreen.tsx:104`).
  Modele yalnız ticari unvan ve il gider (M38 §13).
- **Beklenti:** Logo bağı olmayan CRM carisine olası Logo carisi önerisi; eksik kanal için öneri; düzeltme listesi.
- **Yapabileceklerimiz:**
  - **Logo bağı önerisi** — bağı olmayan CRM carisi için unvan+il+vergi dairesiyle Logo CLCARD adayları (kural), belirsizde
    `choose` «hangisi / hiçbiri» · değer 4 · S (1–2 g) · koruma: CRM'e yazılmaz; «CRM'de düzeltilecek» listesine öneri.
  - **Eksik kanal önerisi** — cari unvanı ve alım karmasından `new_FirmaKanal` önerisi · teknik: `choose` · değer 3 · S (1 g).
- **Eksik:** —

## M32 Kurumsal satış ve B2B

### Kurumsal satış (`/kurumsal-satis`)
Sekmeler: Fırsatlar · Paket oluşturucu · Kurumlar · Hatırlatmalar · (yetkiyle) Onay bekleyen · Kitap temaları · Bayi paneli
(`src/canvas/corporate/CorporateScreen.tsx:31-37`).
- **Ne yapıyor:** Fırsat hattı (kaybedilirken neden zorunlu, `Pipeline.tsx`); tema paketi (kural: onaylı tema + stok +
  geçerli fiyat, bütçeye açgözlü doldurma, `corporate_sales.py:711`); kurum listesi ve alım geçmişi; dönemsel hatırlatma
  (geçen yıl aynı ay); teklif onay kuyruğu (indirim/marj eşiği); kitap temaları onayı; sessiz bayi paneli (A/B/C).
- **Kim:** Kurumsal satış temsilcisi, satış müdürü (onay), B2B/bayi sorumlusu.
- **Bugün AI:** Gece: kurum unvanından segment önerisi, kitaba tema önerisi, kayıp nedeni sınıfı — hepsi kapalı seçim
  (`corporate_sales.py:1583-1600` `choose`, `run_model_tasks` 1635-1700); Kitap temaları sekmesinde onay/ret
  (`WorkTabs.tsx:139-194`). Paket, indirim, marj **kural** (`corporate_sales.py` belge).
- **Beklenti:** Kurum ihtiyacını (ör. «çalışanlara liderlik seti, 150 kişi, kişi başı 400 ₺») cümleyle yazıp paket
  alma; hatırlatmaya kişiselleştirilmiş temas metni; sessiz bayiye neden.
- **Yapabileceklerimiz:**
  - **İhtiyaç cümlesinden paket formu** — serbest talep metninden tema (kapalı küme: onaylı temalar), yaş aralığı, adet ve
    bütçe alanlarını çıkarır; paket yine kural motorundan · teknik: `choose` (tema) + sayı ayrıştırma (kural, metinde
    geçen sayı) · değer 4 · S (1–2 g) · koruma: çıkarılan alanlar formda görünür, insan düzeltir.
  - **Hatırlatma temas taslağı** — geçen yıl aynı ay alımı olan kuruma e-posta taslağı (geçen yıl ne aldı, bu yıl yeni
    çıkanlar) · değer 3 · S (1 g) · koruma: gönderim yok, sayı denetimi.
  - **Anlamsal tema araması** — «değerler eğitimi», «çevre bilinci» gibi onaylı listede olmayan talebe özet gömmesiyle
    en yakın kitaplar · teknik: gömme/benzerlik · değer 3 · M (2 g).
  - **Kazanma/kaybetme özeti** — kayıp sınıflarının çeyreklik dağılımı (SQL) + 3 cümle · değer 2 · S (0,5 g).
- **Eksik:** B2B sitesinden (bayi sipariş portalı) okuma yalnız sayım; bayi sipariş davranışı ayrıntısı yok.

### Fırsat sayfası (`/kurumsal-satis/firsat/:id`)
- **Ne yapıyor:** Fırsatın kurumu, aşaması, teklif(ler)i (`QuoteEditor.tsx`: satır, adet, indirim, marj, onaya gönder,
  belge), paket ekleme (`?firsat=`), kaybetme nedeni (`OpportunityPage.tsx`).
- **Kim:** Kurumsal satış temsilcisi, onaycı müdür.
- **Bugün AI:** Teklif mektubu taslağı; rakam içeren her satır atılır, tutar/adet yalnız tablodan
  (`corporate_sales.py:1623-1632` `draft_letter`, uç `corporate_sales_api.py:360-376`).
- **Beklenti:** Mektupta kurumun geçmiş alımına ve temasına dayalı gerekçe; onaycıya teklif özeti.
- **Yapabileceklerimiz:**
  - **Mektuba kurum bağlamı** — istem bugün yalnız kurum adı, fırsat adı, tema ve kitap adlarını taşıyor; kurum segmenti,
    geçen yıl aldığı temalar ve kitap özetleri (1'er cümle) eklenir · değer 3 · S (0,5 g) · koruma: «rakamlı satırı at»
    kuralı kalır (yıl gibi zararsız sayıların da atıldığı bilinmeli; olgulardaki sayıya izin veren `numbers_ok`'a
    geçmek ayrıca düşünülebilir).
  - **Onaycı özeti** — eşik aşan satırlar, marj, geçmiş medyan iskonto (SQL) → 3 cümle · değer 3 · S (0,5 g).
- **Eksik:** Kazanılan teklif CRM'e elle açılıyor (bilinçli; yazma yok).

## M33 İhale takibi

### İhaleler (`/ihale`)
Sekmeler: İlanlar · Takvim · Belge arşivi · Sonuçlar · Kamu satışları (`src/canvas/tenders/TenderList.tsx:21-25`).
- **Ne yapıyor:** Elle girilen ilanlar (durum, il, tür süzgeci), son teklif/belge geçerlilik/teminat takvimi, şirket belge
  arşivi (geçerlilik), sonuç ve kazanan fiyat oranı, kamu kurumlarına geçmiş satış (Logo LINENET). İlan içe alma kapalı
  (`TENDER_WATCH_ENABLED`, `tenders.py` belge).
- **Kim:** İhale/kamu satış uzmanı, satış müdürü, hukuk/muhasebe (belge).
- **Bugün AI:** İlan konusunun «kitap/yayın alımı mı» sınıflaması ilan kaydında (`tenders.py:1669`,
  `tenders_api.py:179-185`). Listede başka AI yok.
- **Beklenti:** İlan metnini yapıştırınca alanların dolması; kaybedilen ihalelerden ders; belge süresi uyarısının
  hazır yenileme yazısı.
- **Yapabileceklerimiz:**
  - **İlan metninden kayıt** — yapıştırılan ilan metninden kurum, il, usul, son teklif tarihi, yaklaşık tutar, teminat
    alanlarını **alıntıyla** çıkarır (şartname özetinin `_quote_ok` denetimi) · değer 4 · S (1 g) · koruma: tarih/tutar
    yalnız metinde aynen geçiyorsa; insan onaylar.
  - **Kayıp nedeni sınıfı ve öğrenme** — sonuç notlarından (fiyat / belge eksik / süre / şartname uyumsuz / rakip) ·
    `choose` · değer 3 · S (1 g).
- **Eksik:** İlan kaynağı yok (bilinçli, müşteride web kapalı).

### İhale ayrıntısı (`/ihale/:id`)
Sekmeler: Özet · Kalemler · Belgeler · Karar · Sonuç (`TenderDetail.tsx:23-27`).
- **Ne yapıyor:** İlan bilgileri + uygunluk puanı (kural: eşleşme, stok, belge, süre); şartname yükleme ve özet; kalem
  listesi alma ve katalog eşleştirme, teklif tablosu (fiyat = liste × geçmiş kazanan oranı), Excel; belge kontrol listesi
  arşive bağlanır; karar özeti ve iki göz onayı; sonuç.
- **Kim:** İhale uzmanı, satış müdürü (karar), muhasebe (teminat).
- **Bugün AI (en olgun ekranlardan):** Şartname özeti — parçalara bölünmüş, her madde kaynak cümle alıntılı, alıntısı
  tutmayan madde atılır (`tenders.py:1560-1600`); belge türü sınıflaması (`tenders.py:1613-1625`); kalem–katalog
  eşleştirme ISBN → ad → Zeki AI «aynı eser hangisi / hiçbiri», eşikli (`tenders.py:779-866`); karar özeti metni
  (`TenderDecision.tsx:10,65`). Kapı `llm_for("ihale", NORMAL)` (`tenders_api.py:84`).
- **Beklenti:** Taranmış şartnamenin de okunması; teknik şartnamedeki «yerli malı, numune, ceza» gibi risk koşullarının
  kırmızı işaretlenmesi; teklif mektubu/yanıt taslağı.
- **Yapabileceklerimiz:**
  - **Taranmış PDF için OCR** — bugün `pdf_text` yalnız metin katmanını okuyor, taranmışta «metin okunamadı» hatası
    (`tenders.py:661-670`, `1563`) · teknik: belge okuma/OCR (sunucuda; ortak altyapı) · değer 5 · M (2–3 g) · koruma:
    OCR metni «OCR» etiketli, alıntı denetimi aynen.
  - **Risk koşulu işaretleme** — özetteki `kosullar` maddelerini kapalı kümeye (ceza, numune, yerli malı, teslim yeri,
    teminat, diğer) ve «bizim için engel mi» evet/hayır/belirsiz · teknik: `choose` · değer 4 · S (1 g).
  - **Şartname yanıt / teklif mektubu taslağı (M33 §13 ikinci sürüm)** — «taslak — hukuk onayı gerekir» etiketiyle ·
    değer 3 · M (2 g) · koruma: gönderim ve e-imza yok.
- **Eksik:** —

---

**Alan: Lojistik (`lojistik`)**

Menü: 15 öğe (Stok 7, Kargo 3, Tedarik 5). Rota: 21 (menüde olmayan: `/stok/:stokKodu`, `/kargo/gonderi/:id`,
`/kargo/hatalar`, `/kargo/bekleyen`, `/tedarik/kapasite` (menüde `tedarik-yuk`'un `also`'su), `/tedarik/tedarikci/:cari`).
Sohbet konuları `stok` (M43), `lojistik` (M44), `tedarik` (M52) — `chat_topics.json`. Ortak kural: rakamı model üretmez,
metinde olgu dışı sayı varsa kural metni (`stock.py`, `shipping.py`, `supply_suggest.py:41-67` belgeleri).

## M43 Depo ve stok

### Stok (`/stok`)
Durum süzgeci: Hepsi · Stokta yok · Bitecek · Yeterli · Fazla · Hareketsiz · Satışı yok (`StockHome.tsx`).
- **Ne yapıyor:** Dört gösterge, «kitap sor» kutusu, bugün ilgilenilecekler, kitap stok listesi (Logo bakiyesi, satış hızı,
  kaç gün yeter, durum; telefonda kart) (`StockHome.tsx:1`, `ItemList.tsx`). Hız ve tükenme Baskı Öneri ile birebir kural
  (`stock.py` belge).
- **Kim:** Depo sorumlusu, stok planlama, satış operasyon, e-ticaret («stokta var mı»), yayın koordinatörü.
- **Bugün AI:** «Zeki AI'a sorun» kutusu (`StockHome.tsx:208`) Genel bakış soru hattına gider. Sabah bülteni gece işinde
  Zeki AI ile yazılıp e-postalanıyor (`stock_api.py:486-499`, `stock.py:592`); ekranda bülten okuma ucu var
  (`stock_api.py:503`) ama bu ekranda gösterildiği **doğrulanmadı**.
- **Beklenti:** Sabah «bugün ne yapmalıyım» tek paragrafı ekranda; «X kitabından kaç tane var, nerede» hızlı cevap
  (telefonda, sesli); tükenme riskinin tahmine dayalı listesi.
- **Yapabileceklerimiz:**
  - **Bülteni açılışa koy** — son sabah bültenini (zaten üretiliyor) ekranın üstünde göster · değer 4 · S (0,5 g) ·
    koruma: veri günü yanında.
  - **Tahmine dayalı «bitecek» sıralaması** — ortalama hız yerine tahmin motorunun p50 ve p90 talebiyle «90 günde tükenme
    olasılığı yüksek» listesi (okul sezonu gibi mevsimselliği yakalar) · veri: `baski_oneri_tahmin/logo_aylik_gecmis.sql`
    aylık seri, Logo bakiye · teknik: zaman serisi tahmini · değer 5 · M (2–3 g) · koruma: kural listesi yanında, bant
    gösterilir.
- **Eksik:** Logo asgari seviye girilmemiş (`stock.py` belge: ölçüm 2026-09-18) — «kritik» eşiği portal onayına bağlı.

### Kitap stok kartı (`/stok/:stokKodu`)
- **Ne yapıyor:** Logo stoğu + ambar kırılımı, CRM raf dağılımı, kaç gün yeter, bekleyen sipariş (CRM/Logo), devir hızı,
  Logo'ya geçmemiş net, açık üretim kartı ve tahmini depo girişi, güvenlik stoku, öneriler, notlar, gece fotoğrafı
  (`StockItem.tsx:1-3`).
- **Kim:** Stok planlama, depo, yayın koordinatörü.
- **Bugün AI:** «Zeki AI talep tahmini» 30/60/90 gün — Baskı Öneri önbelleğindeki tahmin motoru çıktısının **yalnız p50**'si
  (`stock.py:239-247`, `budget_sources.py:296-308`, `StockItem.tsx:124-136`); ekranda «okul sezonu zirvesini eksik tahmin
  ettiği biliniyor» notu.
- **Beklenti:** Tahminin ne kadar güvenilir olduğu; «ne zaman baskıya girmeli» önerisi; notların özeti.
- **Yapabileceklerimiz:**
  - **Güven aralığı** — tahmin işi p10/p50/p80/p90 kantillerini tutuyor (`management/zeki_tahmin.py:36` KEEP_QUANTILES)
    ama `read_forecast` yalnız p50'yi alıyor (`budget_sources.py:307`); p10–p90 okunup 30/60/90 gün aralık olarak
    gösterilir (önbellek dosyasında hangi kantillerin saklandığı **doğrulanmalı**) · teknik: zaman serisi tahmini (mevcut) ·
    değer 5 · S (1 g) ·
    koruma: «tahmin» etiketi, aralık her zaman görünür.
  - **Baskı tarihi önerisi** — tükenme tarihi (p50 ve p90 talep) − baskı süresi (M12 ölçümü) = «en geç baskı kararı günü»
    (kural) + 2 cümle gerekçe (model) · değer 4 · S (1 g) · koruma: sayı denetimi.
- **Eksik:** Tahmin başlangıcı Logo verisinin bittiği ay; donmuş kopyada tahmin eskir.

### Bitecekler (`/stok/bitecekler`)
Sekme: liste + «Üretime öneriler» (`RunningOut.tsx`).
- **Ne yapıyor:** Kaç gün yeter ≤ N ya da baskı süresi + güvenlik gününün altı; açık üretim kartı yanında; gece üretilen
  «baskı tekrarı değerlendirilsin» önerileri (M12'ye) kabul/ret (`RunningOut.tsx:1-2`, `decisions.tsx`).
- **Kim:** Stok planlama, prodüksiyon/yayın koordinatörü.
- **Bugün AI:** Yok (öneri kural; `stock.py` belge).
- **Beklenti:** Öncelik sırası ve neden; hangi kitap gerçekten tükeniyor, hangisi mevsimsel düşüşte.
- **Yapabileceklerimiz:**
  - **Tahmin bandıyla önceliklendirme** — yukarıdaki tükenme olasılığı listeyi sıralar · değer 5 · (Stok ekranı işiyle aynı).
  - **Öneri gerekçesi** — «baskı tekrarı» önerisine 2 cümle (hız, stok, açık kart, baskı süresi) · değer 3 · S (0,5 g).
- **Eksik:** —

### Fazla stok (`/stok/fazla`)
Süzgeç: Hepsi · Fazla stok · Hareketsiz · Satışı yok (`Excess.tsx`).
- **Ne yapıyor:** Çok uzun yetecek, hareketsiz ya da satışsız kitaplar; eritme yönü önerisi; imha/iade kararı burada yok.
- **Kim:** Stok planlama, pazarlama (kampanya/set), finans (stok değeri).
- **Bugün AI:** Eritme yönü kapalı seçim: kampanya (M35/M17) / set (M53) / bekle (`stock.py:555-565`, `llm.choose` satır
  560; `Excess.tsx:13,58`).
- **Beklenti:** Hangi kitapla set yapılabilir; stok değeri ve beklenen erime süresi; kampanya metni taslağı.
- **Yapabileceklerimiz:**
  - **Set eşi önerisi** — fazla kitaba, birlikte satın alınan (Logo aynı faturada) ve konu gömmesi yakın 3 kitap · teknik:
    kural (birlikte alım) + gömme/benzerlik · değer 4 · M (2 g) · koruma: M53'e öneri notu, onların kaydına yazılmaz.
  - **Erime süresi bandı** — kampanyasız devam hâlinde stoğun kaç ayda biteceği (tahmin motoru p50/p90) · değer 3 · S (1 g).
- **Eksik:** Eritme seçimine gerekçe cümlesi yok (yalnız etiket).

### Güvenlik stoku (`/stok/esikler`)
Sekmeler: Öneriler · Onay bekleyen · Onaylı · Reddedilen · Arşiv (`Thresholds.tsx`).
- **Ne yapıyor:** Günlük satış × (baskı süresi + güvenlik günü) ile eşik önerisi; stok planlama onaylar; Logo `INVDEF`'e
  yazılmaz (`Thresholds.tsx:1-2`).
- **Kim:** Stok planlama, depo müdürü.
- **Bugün AI:** Yok (formül).
- **Beklenti:** Talep dalgalanmasına göre güvenlik günü; mevsimsel kitapta farklı eşik.
- **Yapabileceklerimiz:**
  - **Belirsizlik tabanlı güvenlik stoku** — sabit gün yerine tahmin motorunun (baskı süresi ufkundaki) p90 − p50 farkı
    kadar ek stok önerisi; iki öneri yan yana · teknik: zaman serisi tahmini + formül · değer 4 · M (2 g) · koruma: onay
    akışı aynen, formül ekranda yazılı.
- **Eksik:** —

### Logo–CRM farkı (`/stok/fark`)
- **Ne yapıyor:** Kitap başına CRM raf kalanı − Logo stoğu ve kök neden (aktarılmamış hareket açıklıyor / kısmen / CRM'de
  raf yok / Logo'da hareket yok / açıklanamayan → sayım adayı, `stock.py:82-83`); döngüsel sayım Excel'i.
- **Kim:** Depo sorumlusu, muhasebe (stok mutabakatı).
- **Bugün AI:** Yok (kök neden kural).
- **Beklenti:** Sayım listesinin önceliği; sayım sonrası notun sınıflanması.
- **Yapabileceklerimiz:**
  - **Sayım notu sınıfı** — `semantic_stock_notes` serbest notunu kapalı kümeye (raf hatası / aktarım / fire-hasar /
    iade kaydı eksik / diğer) · `choose` · değer 2 · S (0,5 g).
- **Eksik:** —

### Aktarım hataları (`/stok/aktarim`)
- **Ne yapıyor:** CRM'de başlayıp Logo'ya fiş olarak geçemeyen malzeme hareketleri, yaşı ve Logo mesajı; neden süzgeci
  (`TransferErrors.tsx`).
- **Kim:** Depo, Logo/BT destek.
- **Bugün AI:** Logo mesajı kapalı kümeye (Cari ya da stok kartı yok / Dönem kapalı / Miktar yetersiz / Bağlantı / Diğer),
  eşikli, emin değilse «Sınıflanmadı» (`stock.py:81,530-545`; kolon «Neden (Zeki AI)» `TransferErrors.tsx:103`).
- **Beklenti:** Her sınıf için «nasıl düzeltilir» adımı; tekrar eden hatanın kaynağı.
- **Yapabileceklerimiz:**
  - **Düzeltme adımı kartı** — sınıf başına sabit adım metni (kural) + mesajdaki kart/cari kodunu vurgulayan tek cümle ·
    değer 3 · S (0,5 g) · AI küçük; asıl değer kuralda.
- **Eksik:** —

### Depo hattı (`/stok/depo-hatti`)
- **Ne yapıyor:** CRM sipariş aşamaları (depoda bekliyor → toplanıyor → kutulanıyor → kutulandı), aşamadaki bekleme ve
  süreler; kişi bazlı toplama süresi yalnız açık yetkiyle (`PickLine.tsx:1-3`).
- **Kim:** Depo şefi, lojistik müdürü.
- **Bugün AI:** Yok.
- **Beklenti:** Gün içi iş yükü tahmini (kaç sipariş gelecek), darboğaz uyarısı.
- **Yapabileceklerimiz:**
  - **Günlük sipariş hacmi tahmini** — CRM sipariş sayısı günlük serisinden 7 gün bant (hafta içi/sonu, kampanya etkisi) ·
    teknik: zaman serisi tahmini · değer 3 · M (1–2 g) · koruma: kişi bazlı veri kullanılmaz.
- **Eksik:** —

## M44 Lojistik ve kargo

### Kargo (`/kargo`)
Sekmeler: Gönderi ara · Takip numarasız sevk · Kutulandı, sevk edilmedi (`ShippingHome.tsx`).
- **Ne yapıyor:** Günün sevki, entegrasyon hatası, takip numarasız sevk, kutulandı-sevk edilmedi, teslim bekleyen; sipariş,
  fatura ya da takip no ile tek arama (`ShippingHome.tsx:1-2`).
- **Kim:** Lojistik/kargo sorumlusu, müşteri hizmetleri («kargom nerede»), e-ticaret operasyon.
- **Bugün AI:** Hataların Zeki AI sınıfına göre dağılımı (`ShippingHome.tsx:98`; sınıflama gece, `shipping.py:772-791`).
- **Beklenti:** Günün özeti; «kargom nerede» sorusuna müşteriye verilecek cevap; takip numarasız sevklerin olası nedeni.
- **Yapabileceklerimiz:**
  - **Gün sonu kargo özeti** — sevk, hata sınıfları, bekleyen yaşları (SQL) → 4 cümle · değer 3 · S (0,5 g).
  - **Serbest aramayı anlama** — «Ahmet Bey'in dünkü siparişi» gibi değil (kişisel veri); yalnız sipariş/fatura/takip no
    biçimini kuralla tanır — AI gerekmez (not).
- **Eksik:** —

### Gönderi kartı (`/kargo/gonderi/:id`)
- **Ne yapıyor:** Sipariş → depo → kutulama → sevk → kargo → teslim zaman çizelgesi, entegrasyon sonucu, kargo kaydı, CRM
  sevkiyatı, Logo karşılığı; mesaj taslakları; alıcı adı ve tutar yetkiyle (`Shipment.tsx:1-3`).
- **Kim:** Müşteri hizmetleri, kargo sorumlusu.
- **Bugün AI:** Gecikme / özür / iade mesajı **taslağı**; kişisel veri modele gitmez (yalnız sipariş no, durum, firma,
  aşama günleri); olgu dışı sayı → kural metni (`shipping.py:820-866`, `Shipment.tsx:231-241,292`); hata sınıfı rozeti
  (`Shipment.tsx:100`).
- **Beklenti:** Müşteri yazısına göre cevap; destek masasındaki talebe bağlanması.
- **Yapabileceklerimiz:**
  - **Destek masası talebiyle bağ** — M51 destek masasındaki «kargom nerede» talebinde gönderi kartının taslağını hazır
    sunma (sipariş no eşleşmesi kural) · değer 4 · M (2 g; destek masası entegrasyonuna bağlı) · koruma: gönderim yok,
    temsilci gönderir.
- **Eksik:** —

### Entegrasyon hataları (`/kargo/hatalar`)
- **Ne yapıyor:** Takip numarası oluşmamış, kargo servisi hata döndürmüş siparişler; entegrasyon ve sınıf süzgeci
  (`Errors.tsx`).
- **Kim:** Kargo sorumlusu, BT.
- **Bugün AI:** Hata mesajı kapalı kümeye (Adres / Telefon / Desi-ağırlık-koli / Kimlik doğrulama / Servis kapalı /
  Mükerrer / Diğer; «Belirsiz»), mesaj başına bir kez (`shipping.py:97-99,772-791`, `Errors.tsx:57`).
- **Beklenti:** Adres hatasında düzeltme önerisi; toplu tekrar gönderim listesi.
- **Yapabileceklerimiz:**
  - **Adres düzeltme önerisi** — adres sınıfında il/ilçe/posta kodu tutarsızlığını kural+sözlükle gösterir; model yok ·
    değer 3 · S (1 g) · koruma: adres modele gitmez (kişisel veri).
- **Eksik:** —

### Teslim bekleyen (`/kargo/bekleyen`)
- **Ne yapıyor:** Teslim tarihi olmayan, iade olmayan gönderiler yaşa göre; «geç teslim» değil «bekleyen gün» (termin yok)
  (`Waiting.tsx:1-2`).
- **Kim:** Kargo sorumlusu, müşteri hizmetleri.
- **Bugün AI:** Yok.
- **Beklenti:** Hangisi gerçekten kayıp olabilir; kargo firmasına toplu soru yazısı.
- **Yapabileceklerimiz:**
  - **Kayıp/iade şüphesi sırası** — firma × il teslim süresi dağılımına göre (kural: yaş > il için p95) · AI değil; tahmin
    değil ampirik çeyrek · değer 3 · S (1 g).
  - **Firmaya toplu sorgu yazısı taslağı** — takip no listesiyle · değer 2 · S (0,5 g) · koruma: gönderim yok.
- **Eksik:** —

### Firma karnesi (`/kargo/firmalar`)
- **Ne yapıyor:** Firma başına gönderi, teslim süresi, iade, (yetkiyle) desi başı maliyet; şehir/şube kırılımı; il hedef
  süresi; kurye/bölge/sözleşme karar kaydı (`Carriers.tsx:1-4`).
- **Kim:** Lojistik müdürü, satın alma, CFO (maliyet).
- **Bugün AI:** Karar kaydında «Zeki AI gerekçe özeti» (`shipping.py:870-890`, `shipping_api.py:396`, `Carriers.tsx:219,282`).
- **Beklenti:** Maliyet eğilimi ve gelecek ay kargo gideri; firma karşılaştırmasının sunumluk özeti.
- **Yapabileceklerimiz:**
  - **Aylık kargo gideri tahmini** — gönderi sayısı ve desi başı maliyet serisinden 3 ay bant · teknik: zaman serisi
    tahmini · değer 3 · S (1–2 g) · koruma: yalnız `kargo.maliyet` yetkisi.
- **Eksik:** Termin tutulmuyor (iş kararı) — «geç» oranı yalnız kullanıcı hedefiyle.

### Kargo mutabakatı (`/kargo/mutabakat`)
- **Ne yapıyor:** Kargo kaydı toplamı ↔ Logo kargo faturası (eşlenen cariler), mükerrer takip no, okunamayan tutar; Logo sevk
  ↔ CRM sevkiyat eşleşme oranı (`Reconcile.tsx:1-3`).
- **Kim:** Muhasebe, lojistik müdürü.
- **Bugün AI:** «Zeki AI fark özeti» — yalnız verilen rakamlarla, denetimli (`shipping_api.py:454-466`, `Reconcile.tsx:70`).
- **Beklenti:** Kargo firmasına itiraz yazısı; fatura PDF'inin okunması (bugün Logo'daki tutarla çalışılıyor).
- **Yapabileceklerimiz:**
  - **İtiraz yazısı taslağı** — mükerrer ve okunamayan kalemlerle · değer 3 · S (0,5 g) · koruma: gönderim yok, sayı
    denetimi.
  - **Kargo fatura ekini okuma** — firmanın gönderi bazlı fatura dökümünü (Excel/PDF) yükleyince satır satır kargo
    kaydıyla eşleme · teknik: belge okuma (Excel kural, PDF metin/OCR) · değer 4 · M (2–3 g).
- **Eksik:** —

## M52 Tedarik ve baskı

### Tedarik özeti (`/tedarik`)
- **Ne yapıyor:** Önümüzdeki aylar × matbaa yükü, eşik aşımı, bu ay kağıt, 30 gün ödeme, faturası görünmeyen baskı, birim
  maliyet eğilimi, kartı açılmamış baskı ihtiyacı, gelecek depo girişleri (`SupplyHome.tsx:1-2`).
- **Kim:** Prodüksiyon/üretim müdürü, satın alma, finans (ödeme).
- **Bugün AI:** Ekranda doğrudan yok; öneri gerekçeleri alt ekranlarda.
- **Beklenti:** Haftalık tedarik özeti (ne sıkışıyor, ne ödenecek).
- **Yapabileceklerimiz:**
  - **Haftalık tedarik bülteni** — M43 sabah bülteni kalıbıyla (olgu → 5 cümle, sayı denetimi `supply_suggest.py:41`) ·
    değer 3 · S (1 g).
- **Eksik:** —

### Baskı yükü (`/tedarik/yuk`)
Sekmeler: Yük tablosu · Eşik aşımı · Dengeleme önerileri · Kartı açılmamış ihtiyaç · Plan değişiklikleri (`Load.tsx`).
- **Ne yapıyor:** Ay × matbaa ısı tablosu (iş, adet, forma), kapasite eşiği; dengeleme önerisi (kural) kabul/ret; M11/M10'dan
  henüz kartı açılmamış ihtiyaç; plan değişikliği sebep dağılımı (`supply.py:1312`).
- **Kim:** Prodüksiyon müdürü.
- **Bugün AI:** Dengeleme önerisinin gerekçesi 2 cümle, sayı ve teknoloji adı denetimli (`supply_suggest.py:50-67`
  `model_text`, `REASON_SYSTEM`).
- **Beklenti:** Kartı açılmamış ihtiyacın hangi aya düşeceği; baskı tekrarı talebinin tahmini.
- **Yapabileceklerimiz:**
  - **Gelecek baskı yükü tahmini** — M11 tahmin motoru çıktısından (p50/p90 tükenme) «önümüzdeki 6 ayda hangi kitaplar
    baskıya girecek» dağılımı; yük tablosuna gölge satır · teknik: zaman serisi tahmini (mevcut Baskı Öneri tahmini) + kural
    · değer 4 · M (2 g) · koruma: «tahmin» gölgesi, gerçek kartlardan ayrı.
  - **Plan değişikliği sebep sınıfı** — serbest sebep metinlerinde (varsa) kapalı küme · değer 2 · S (0,5 g).
- **Eksik:** Matbaa kapasitesi hiçbir kaynakta yok; elle girilmezse eşik yalnız geçmiş referans.

### Matbaa kapasitesi (`/tedarik/kapasite`)
- **Ne yapıyor:** Matbaa × ay adet/forma kapasitesi girişi; ay boşsa her ay (`Capacity.tsx:1-2`).
- **Kim:** Prodüksiyon müdürü.
- **Bugün AI:** Yok.
- **Beklenti:** Kapasiteyi matbaa teklif/sözleşme belgesinden doldurmak.
- **Yapabileceklerimiz:** Düşük değer; AI önerilmez (elle giriş yeterli). Not: geçmiş 12 ay en yüksek yük zaten referans.
- **Eksik:** —

### Kağıt ve malzeme (`/tedarik/kagit`)
Sekmeler: Aylık ihtiyaç · Alım zamanı · Kağıt bilgisi eksik · Alış fiyatı (`Paper.tsx`).
- **Ne yapıyor:** Açık kartların baskı ayı × kağıt cinsi ihtiyacı (CRM kart alanları, brüt/net kg), alım zamanı önerisi
  (kural, `supply_suggest.py:170-200`), eksik kağıt bilgisi, kağıtçı alış fiyatı eğilimi (Logo TRCODE 1).
- **Kim:** Satın alma, prodüksiyon.
- **Bugün AI:** Alım zamanı önerisinin gerekçe metni ortak `model_text` ile (öneri kartı, `supply/parts.tsx:198`) — öneri
  türü `kagit` (`supply_store.py` belge).
- **Beklenti:** Kağıt fiyatı yönü; eksik kağıt bilgisinin doldurulması.
- **Yapabileceklerimiz:**
  - **Kağıt alış fiyatı bandı** — ton fiyatı aylık serisinden 3–6 ay bant; «alımı öne çek/bekle» kararı insanda · teknik:
    zaman serisi tahmini · değer 3 · S (1–2 g) · koruma: tahmin etiketi; dış piyasa verisi yok (sınırlılık yazılır).
  - **Eksik kağıt bilgisi önerisi** — aynı dizideki/aynı ebattaki kitapların kağıt cinsinden öneri (kural, çoğunluk) · AI
    gerekmez · değer 2.
- **Eksik:** —

### Tedarikçiler (`/tedarik/tedarikciler`)
Sekmeler: Tedarikçiler · Ödeme planı · Fatura eşleşmesi · Matbaa ↔ cari (`Suppliers.tsx`).
- **Ne yapıyor:** Matbaa/kağıtçı listesi (iş + borç + karne), 30/60/90 gün ödeme (FIFO yaklaşımı), faturası görünmeyen
  baskı ve kartı görünmeyen fatura, matbaa ↔ Logo carisi eşlemesi (`Suppliers.tsx:1-3`).
- **Kim:** Satın alma, finans/muhasebe, prodüksiyon.
- **Bugün AI:** Kuralın bağlayamadığı fatura satırı için aday kartlar arasından «hangisi / Hiçbiri» kapalı seçimi, gece
  (`supply_suggest.py:280-295`; ekran açıklaması `Suppliers.tsx:289`); onay `ozellik:tedarik.eslesme`.
- **Beklenti:** Faturası gelmeyen baskı için matbaaya hatırlatma; ödeme önceliği önerisi.
- **Yapabileceklerimiz:**
  - **Fatura PDF'inden satır okuma** — matbaa e-fatura/PDF'i yüklenince ürün adı, adet, birim fiyatı alıntıyla çıkarır ve
    kartla eşler (Logo'ya henüz düşmemiş fatura için) · teknik: belge okuma/OCR + `choose` · değer 3 · M (2–3 g) ·
    koruma: Logo'ya yazılmaz.
  - **Fatura hatırlatma yazısı taslağı** · değer 2 · S (0,5 g).
- **Eksik:** Borç FIFO yaklaşımıdır (ekranda yazılı).

### Tedarikçi sayfası (`/tedarik/tedarikci/:cari`)
- **Ne yapıyor:** Açık işler + borç ve ödeme (FIFO) + faturalar + karne (`Supplier.tsx:1`).
- **Kim:** Satın alma, finans.
- **Bugün AI:** Gecikme yazısı taslağı (eskalasyon, `supply_suggest.py:234-250`; taslak penceresi `supply/parts.tsx:156`).
- **Beklenti:** Toplantı öncesi tedarikçi özeti.
- **Yapabileceklerimiz:**
  - **Tedarikçi görüşme brifi** — açık iş, gecikme, ödeme, birim maliyet eğilimi → 4 cümle · değer 3 · S (0,5 g).
- **Eksik:** —

### Baskı maliyeti eğilimi (`/tedarik/maliyet`)
Kırılım: Bütün baskılar · Ciltleme şekli · Sayfa sayısı · Baskı tipi · Matbaa (`CostTrend.tsx`).
- **Ne yapıyor:** Logo matbaa faturasında adet başı baskı bedeli ay × kırılım; kağıt alış fiyatı; «birim maliyet» açık yetkiyle.
- **Kim:** Prodüksiyon müdürü, CFO, fiyatlama (M9).
- **Bugün AI:** Yok (analizde «eğilim yorumu 2–3 cümle» vardı, M52 §13; kodda bulunmadı).
- **Beklenti:** Eğilim yorumu; gelecek çeyrek birim maliyet beklentisi (M9 fiyatlamasına girdi).
- **Yapabileceklerimiz:**
  - **Eğilim yorumu** — seçili kırılımda 2–3 cümle (sayı denetimi) · değer 3 · S (0,5 g).
  - **Birim maliyet bandı** — kırılım başına 2 çeyrek ileri bant; M9 senaryosuna «beklenen maliyet artışı» girdisi olarak ·
    teknik: zaman serisi tahmini · değer 4 · M (2 g) · koruma: M9'da yalnız senaryo seçeneği, zorunlu değil.
- **Eksik:** —

---

**Alan: İnsan Kaynakları (`ik`)**

Menü: 16 öğe (`explicit: true` — «Herkes» rolüne girmez, `navModel.ts` `ik` alanı). Rota: 28 (menüde olmayan: aday kartı,
3 değerlendirme formu yolu, 5 eğitim alt ekranı, 3 oturumsuz anket formu yolu).

**İK'ya özgü sınırlar (bütün önerilere uygulanır):** Model kişiye puan vermez, sıralamaz, otomatik ret yapmaz (KVKK md.
11/1-g; `hr_recruit.py`, `hr_performance.py` belgeleri). Modele kişi adı, iletişim, T.C. no, özel nitelikli veri gitmez;
kural maskesi önce, model maskesi sonra (`hr_recruit_text.py:146` `rule_mask`, `:227` `model_mask`,
`hr_engagement_text.py:50-90`). Çağrılar `hr_llm()` ile, sıra kaydına mesaj değil etiket (`hr_core.py:17-18,324`);
`/api/v1/llm/jobs` İK'da kullanılmaz. Sohbet konusu `ik` var ama veri kataloğu boş (`chat_topics.json`: `data: []`) — İK
sorusuna rakamlı cevap bugün yok.

## İK-0 Ortak kayıtlar

### Çalışan ve KVKK kayıtları (`/ik/kayitlar`)
Sekmeler: Çalışanlar · Birimler · Aydınlatma metinleri · Saklama ve imha · Erişim kaydı (`HrRecordsScreen.tsx`).
- **Ne yapıyor:** CRM ∩ AD'den çalışan/birim önerisi, İK onayıyla kayıt (`hr_sources.py:102` `sync_preview`); aydınlatma metni
  sürümleri, açık rıza, veri sınıfı başına saklama süresi, gece imha tutanakları, erişim kaydı (`hr_core.py` belge).
- **Kim:** İK uzmanı, KVKK sorumlusu, İK müdürü.
- **Bugün AI:** Yok (kayıt ve kural ekranı).
- **Beklenti:** Aydınlatma metni taslağı; olağandışı erişim kaydının fark edilmesi; CRM/AD birim adlarının eşlenmesi.
- **Yapabileceklerimiz:**
  - **Aydınlatma metni taslağı** — veri sınıfı, amaç, saklama süresi alanlarından sürüm taslağı («taslak — hukuk onayı
    gerekir») · teknik: taslak metin · değer 3 · S (1 g) · koruma: kişisel veri yok; yürürlüğe alma insan onayı.
  - **Erişim kaydı olağandışılık işareti** — kişi başı günlük görüntüleme sayısının kendi ortancasından sapması (kural,
    model değil) · değer 3 · S (1 g) · koruma: sonucu yalnız KVKK sorumlusu görür.
- **Eksik:** —

## M55 İşe alım

### İşe alım panosu (`/ik/ise-alim`)
- **Ne yapıyor:** Dört sayaç ve pozisyon başına aşama sütunları; telefonda sütunlar sekmeye döner; kartta yalnız ad,
  pozisyon ve aşamadaki gün — puan/sıra yok (`RecruitBoard.tsx:1-2`). E-postadan gelen başvuru `POST /intake` ile düşer
  (`hr_recruit_api.py:337-348`); aşamada bekleyen adaylar için İK'ya özet e-posta (`:351`).
- **Kim:** İK uzmanı, işe alan yönetici.
- **Bugün AI:** Ekranda doğrudan yok; açıklama metni (`RecruitBoard.tsx:35,243`). Başvuru e-postasının sınıflanması Kurumsal
  E-posta (H4) modülünde.
- **Beklenti:** Pano üzerinde «hangi pozisyonda süreç tıkandı» özeti; aday iletişim yükünün hafiflemesi.
- **Yapabileceklerimiz:**
  - **Süreç tıkanıklık özeti** — aşama başına bekleme günleri (SQL, kişisiz) → 3 cümle · değer 3 · S (0,5 g) · koruma:
    aday adı modele gitmez; yalnız sayılar.
- **Eksik:** —

### Aday kartı (`/ik/ise-alim/aday/:id`)
- **Ne yapıyor:** Aday bilgisi (yetkiye göre), özgeçmiş dosyası (PDF/DOCX/ODT → metin, maskeli), kanıtlı özet, aşama kararı
  (gerekçe isteğe bağlı), mülakat notları (görüşmeci kendi notunu teslim etmeden başkasınınkini görmez), mektup, KVKK dışa
  aktarım ve imha (`CandidateDrawer.tsx`, `hr_recruit.py` belge).
- **Kim:** İK uzmanı, görüşmeci, işe alan yönetici.
- **Bugün AI:** (1) İki adımlı maskeleme — kural + model yalnız satır numarası söyler (`hr_recruit_text.py:146,227`); (2)
  kanıtlı özet — her yetkinlik için özgeçmişteki **satır numarası**, alıntı o satırın kendisi, puan yok
  (`hr_recruit_text.py:254`, `hr_recruit_api.py:224-237`, `CandidateDrawer.tsx:236-248`); (3) mektubu «tonu yumuşat» —
  şablon değeri kaybolur ya da yeni sayı/tarih belirirse model çıktısı atılır (`hr_recruit.py:1082`, `hr_recruit_text.py` belge).
- **Beklenti:** Mülakat notlarının yetkinlik bazında derlenmesi; aday sorularına (maaş, süreç) cevap taslağı; tarama yapılmış
  (görüntü) özgeçmişlerin de okunması.
- **Yapabileceklerimiz:**
  - **Mülakat notu derlemesi** — birden çok görüşmecinin notunu yetkinlik başlıklarına ayırır, her cümle kaynağa (not
    kimliği) bağlı; özet puan/öneri içermez · teknik: kapalı seçim (not cümlesi → yetkinlik) + alıntılı derleme · değer 4 ·
    M (2 g) · koruma: yalnız bütün notlar teslim edildikten sonra; karar cümlesi («işe alınsın») yazmaz, model çıktısında
    değerlendirme sözcükleri kuralla engellenir.
  - **Taranmış özgeçmiş OCR** — görüntü PDF'te bugün «Dosyadan metin çıkmadı (taranmış görüntü olabilir)» hatası
    (`hr_recruit_text.py:87`); depoda OCR kütüphanesi yok · teknik: belge okuma/OCR (ortak altyapı) · değer 3 · S (ortak
    altyapı hazırsa 0,5 g) ·
    koruma: OCR çıktısı da maskeden geçer.
- **Eksik:** —

### Pozisyonlar (`/ik/pozisyonlar`)
- **Ne yapıyor:** Pozisyon kartı (birim, yetkinlikler, işe alan yönetici, görüşmeciler), ilan taslağı ve ayrımcılık denetimi,
  mülakat soru seti, onay akışı (`PositionEditor.tsx:11-12`).
- **Kim:** İK uzmanı, işe alan yönetici.
- **Bugün AI:** İlan taslağı (`hr_recruit_api.py:109-135`); ayrımcı ifade denetimi kural + `choose` «var/yok» p ≥ 0,8
  (`hr_recruit_api.py:129`, `PositionEditor.tsx:233-255`); mülakat soru seti (`hr_recruit_api.py:147-156`, «Zeki AI önersin»
  `PositionEditor.tsx:280`).
- **Beklenti:** Yetkinlik listesinin önerilmesi (benzer pozisyondan); ilanın farklı kanallar için kısaltılmış sürümü.
- **Yapabileceklerimiz:**
  - **Yetkinlik önerisi** — pozisyon adı ve biriminden, şirketin yetkinlik sözlüğünden (kapalı liste) evet/hayır seçimi ·
    teknik: aday başına `choose` · değer 3 · S (1 g) · koruma: öneri; İK seçer.
  - **Kanal sürümleri** — ilanın kısa (LinkedIn/kariyer sitesi) sürümü, aynı ayrımcılık denetiminden geçer · değer 2 ·
    S (0,5 g) · koruma: gönderim yok.
- **Eksik:** —

### Belgeler (`/ik/belgeler`)
- **Ne yapıyor:** İlan, «başvurunuz alındı», mülakat daveti, teklif, ret şablonları; `{{alan}}` yer tutucuları; sürümlü
  (`TemplatesScreen.tsx:1-3`).
- **Kim:** İK uzmanı.
- **Bugün AI:** Yok (şablon); ton yumuşatma aday kartında.
- **Beklenti:** Yeni şablon taslağı; mevcut şablonun dil denetimi.
- **Yapabileceklerimiz:**
  - **Şablon dil denetimi** — ayrımcılık denetiminin (`choose`) şablonlara da uygulanması; «sert ifade var mı» evet/hayır ·
    değer 2 · S (0,5 g).
- **Eksik:** —

## M57 Eğitim ve gelişim

### Eğitimlerim (`/ik/egitimlerim`)
- **Ne yapıyor:** Kişinin zorunlu eğitimleri, oturumları, sertifikaları, anketleri, ihtiyaç bildirimi; yöneticiye ekibinin onay
  bekleyen talepleri; portal kullanımı yalnız kişinin kendisine («Zeki AI'a sorduğunuz soru» sayısı, `MyLearning.tsx:385`).
- **Kim:** Her çalışan; ekip yöneticisi.
- **Bugün AI:** İhtiyaç bildiriminin metni sonradan NeedsScreen'de eşlenir; bu ekranda model çağrısı yok.
- **Beklenti:** «Bana hangi eğitim uygun?»; bildirdiğim ihtiyacın anında katalogla eşlenmesi.
- **Yapabileceklerimiz:**
  - **Anında katalog eşleşmesi** — ihtiyaç yazarken NeedsScreen'deki eşleme (`hr_learning.py:1277` `suggest_need`) kişinin
    kendi ekranında da gösterilir · değer 3 · S (0,5 g) · koruma: metin maskelenir (`hr_learning.py:1267`).
- **Eksik:** —

### Eğitim panosu (`/ik/egitim`)
Alt gezinme: Pano · Katalog ve oturumlar · İhtiyaçlar · Kullanım haritası · Rehberler (`learning/parts.tsx:17-21`).
- **Ne yapıyor:** Sayaçlar, dolmuş/dolacak zorunlu eğitimler, seçilenlerle tek adımda oturum, birim × eğitim tamamlanma,
  doğrulama bekleyen belgeler, eğitim gideri (Logo EMFLINE, `ik.egitim-butce`) (`LearningDashboard.tsx:1-2`).
- **Kim:** İK/eğitim uzmanı, İSG sorumlusu.
- **Bugün AI:** Yok.
- **Beklenti:** Yüklenen sertifika belgesinin okunması (tarih, geçerlilik); aylık eğitim özeti.
- **Yapabileceklerimiz:**
  - **Sertifika belgesinden alan çıkarma** — doğrulama bekleyen belgeden eğitim adı, tarih, geçerlilik bitişini alıntıyla
    önerir; İK doğrular · teknik: belge okuma/OCR + alıntı denetimi · değer 4 · M (2 g) · koruma: belge modelde işlenirken ad
    maskelenir; «doğrulandı» yine insan.
  - **Aylık eğitim özeti** — tamamlanma, dolacaklar, gider (SQL) → 4 cümle · değer 2 · S (0,5 g).
- **Eksik:** —

### Katalog ve oturumlar (`/ik/egitim/katalog`)
- **Ne yapıyor:** Eğitim kartı (tür, biçim, süre, geçerlilik, maliyet, zorunlu eğitimin birimleri, ZEKİ ekranı) ve oturum
  listesi; düzenleme `ik.egitim-yonet` (`CoursesScreen.tsx:1-2`).
- **Kim:** Eğitim uzmanı.
- **Bugün AI:** Yok.
- **Beklenti:** Eğitim kartı açıklamasının ve kazanımlarının taslağı; değerlendirme sorusu önerisi.
- **Yapabileceklerimiz:**
  - **Eğitim kartı ve anket sorusu taslağı** (M57 §13 «davet, hatırlatma, değerlendirme soruları») · değer 2 · S (1 g).
- **Eksik:** —

### Oturum (`/ik/egitim/oturum/:id`)
- **Ne yapıyor:** Bilgiler, katılımcılar, telefondan yoklama, onay bekleyen talepler, kapatma (sertifika + anonim anket jetonu),
  anket sonucu (`SessionScreen.tsx:1-2`).
- **Kim:** Eğitim uzmanı, eğitmen.
- **Bugün AI:** Anonim geri bildirim yorumlarını kapalı tema listesine ayırma + tema özeti, gizlilik eşiğine bağlı
  (`hr_learning.py:1390-1410`, `hr_learning_api.py:395`, `SessionScreen.tsx:242`).
- **Beklenti:** Eğitmene iletilecek iyileştirme notu.
- **Yapabileceklerimiz:**
  - **Eğitmen geri bildirim mektubu taslağı** — tema özetlerinden (alıntısız) · değer 2 · S (0,5 g) · koruma: eşik altı oturumda
    üretilmez.
- **Eksik:** —

### İhtiyaçlar (`/ik/egitim/ihtiyaclar`)
- **Ne yapıyor:** Çalışan/yönetici/İK'nın bildirdiği ihtiyaçlar; eğitim başına açık/onaylı ihtiyaç sayısı (`NeedsScreen.tsx`).
- **Kim:** İK/eğitim uzmanı.
- **Bugün AI:** İhtiyaç → katalog eşleme (katalog dışı dahil), öncelik ve tek cümle gerekçe; kişi bilgisi modele gitmez
  (`hr_learning.py:1277-1300`, `hr_learning_api.py:486`, `NeedsScreen.tsx:45-52,122`).
- **Beklenti:** Katalog dışı kalan ihtiyaçların kümelenmesi → yeni eğitim önerisi.
- **Yapabileceklerimiz:**
  - **Katalog dışı ihtiyaç kümeleri** — «katalogda yok» dönen metinlerin gömmeyle kümelenmesi, küme başına önerilen eğitim
    başlığı · teknik: gömme/benzerlik + kısa taslak · değer 3 · M (1–2 g) · koruma: maskeli metin, küme ≥ gizlilik eşiği.
- **Eksik:** —

### Kullanım haritası (`/ik/egitim/kullanim`)
- **Ne yapıyor:** Ekran × birim, pencerede en az bir kez kullanan farklı kişi sayısı; kişi adı yok; küçük birimler eşikle
  birleşir (`UsageMap.tsx:1-3`).
- **Kim:** Portal sorumlusu, eğitim uzmanı.
- **Bugün AI:** Yok.
- **Beklenti:** «Hangi birime hangi ekranın eğitimi gerek» önerisi.
- **Yapabileceklerimiz:**
  - **Benimseme açığı önerisi** — birimin görev alanına uygun ama kullanılmayan ekranlar (kural: menü alanı ↔ birim eşlemesi)
    + rehber bağlantısı · AI küçük (1 cümle gerekçe) · değer 3 · S (1 g) · koruma: kişi düzeyi yok.
- **Eksik:** —

### Rehberler (`/ik/egitim/rehberler`)
- **Ne yapıyor:** Her menü ekranı için adım adım rehber; «yaradı/yaramadı» oyu sürüme sayılır (`GuidesScreen.tsx:12-14`).
- **Kim:** Portal sorumlusu (`ik.rehber-yaz`), bütün kullanıcılar (okur).
- **Bugün AI:** Menü tanımından (`navModel.ts` hint) rehber taslağı; teknoloji adı denetimi (`hr_learning.py:267`,
  `hr_learning_api.py:545`, `GuidesScreen.tsx:91-156`).
- **Beklenti:** Rehbere ekran metinlerinin de girmesi; «yaramadı» oylarının nedeni.
- **Yapabileceklerimiz:**
  - **Rehbere ekran metni bağlamı** — ekran bileşenindeki başlık/düğme metinleri derleme zamanında çıkarılıp isteme eklenir
    (M57 §13'te vardı) · değer 3 · S (1 g).
- **Eksik:** —

## M56 Performans

### Performansım (`/ik/performansim`)
- **Ne yapıyor:** Hedeflerim ve bağlı üst hedef, açık görevlerim (öz değerlendirme, yorum, check-in), değerlendirmelerim,
  hakkımda üretilen iş kayıtları özeti (KVKK md. 11) (`MyPerformance.tsx:1-2`).
- **Kim:** Her çalışan.
- **Bugün AI:** Hedef kartında OKR taslağı ve hizalama (bkz. Hedef ağacı). İş kayıtları özeti **modelsiz**: sayılar SQL,
  cümle sabit kalıp (`hr_performance.py` belge, `:1256`).
- **Beklenti:** Öz değerlendirme yazarken destek; check-in notu yazmanın kolaylaşması.
- **Yapabileceklerimiz:**
  - **Öz değerlendirme taslağı** — kişinin kendi check-in notları ve hedef ilerlemesinden, her cümle kaynağa bağlı taslak;
    yalnız kişinin kendisi tetikler · teknik: kaynak bağlı özet · değer 3 · M (1–2 g) · koruma: puan önerisi yok; maske;
    kişi göndermeden kimse görmez.
- **Eksik:** —

### Değerlendirme formu (`/ik/performansim/degerlendirme/:id`, `/ik/ekibim/degerlendirme/:id`, `/ik/degerlendirme/:id`)
Aynı bileşen, üç yol; rol köprüden (`ReviewForm.tsx:1-3`).
- **Ne yapıyor:** Öz değerlendirme → yönetici değerlendirmesi → görüşme ve paylaşım → çalışan yorumu/itirazı → İK onayı.
- **Kim:** Çalışan, yönetici, İK.
- **Bugün AI:** «Zeki AI ile somutlaştır» — yöneticinin metnini maskeli olarak yeniden yazar, yeni olay eklemez
  (`hr_performance_api.py:419-436`, `ReviewForm.tsx:143-163`).
- **Beklenti:** Yıl sonu değerlendirme taslağı (çeyrek notlarından); itiraz metninin yapılandırılması.
- **Yapabileceklerimiz:**
  - **Yıl sonu taslağı, kaynak bağlı** (M56 §13; kodda yok) — çeyrek check-in ve hedef kayıtlarından, her cümlenin yanında
    kaynak kimliği; kaynaksız cümle atılır · değer 4 · M (2 g) · koruma: puan alanını model doldurmaz; yönetici yazar.
  - **Önyargılı ifade uyarısı** — yönetici metninde kişilik/yaş/cinsiyet imasına «var/yok» `choose` (M55 ayrımcılık
    denetiminin performans uyarlaması) · değer 3 · S (1 g) · koruma: yalnız uyarı.
- **Eksik:** —

### Ekibim (`/ik/ekibim`)
- **Ne yapıyor:** Yönetici zincirindeki kişiler: hedef ilerlemesi, eksik check-in, onay bekleyen hedef/revizyon, değerlendirme
  durumu; kişi kartı erişim kaydına (`MyTeam.tsx:1-2`).
- **Kim:** Birim yöneticisi.
- **Bugün AI:** Yok.
- **Beklenti:** Birebir görüşme hazırlığı; ekip hedef durumunun özeti.
- **Yapabileceklerimiz:**
  - **Birebir hazırlık notu** — kişinin paylaşılmış check-in'leri ve hedef ilerlemesinden 3 madde «konuşulacaklar» (kaynak
    bağlı) · değer 3 · S (1 g) · koruma: yalnız yöneticinin zaten gördüğü veri; çalışan da aynı notu görür (md. 11); puan yok.
- **Eksik:** —

### Hedef ağacı (`/ik/hedefler`)
- **Ne yapıyor:** Şirket → birim → kişi hedefleri; üst hedefe bağlanmamışlar ayrı listede (`GoalTree.tsx`, `GoalSheet.tsx`).
- **Kim:** İK, yöneticiler, genel müdür.
- **Bugün AI:** Üst hedeften OKR taslakları (kişi adı yerine birim ve unvan; `hr_performance_api.py:201-215`,
  `hr_performance.py:683-710`); hizalama önerisi — aday üst hedefler arasından kapalı seçim (`hr_performance.py:660-680`,
  `hr_performance_api.py:219`, `GoalSheet.tsx:333`).
- **Beklenti:** Bağlanmamış hedeflerin toplu hizalama önerisi; ölçülemeyen hedefin işaretlenmesi.
- **Yapabileceklerimiz:**
  - **Toplu hizalama** — «Üst hedefe bağlanmamış» listesinin tamamı için mevcut `choose`, eşik üstü öneriler tek ekranda onaya ·
    değer 3 · S (1 g).
  - **Ölçülebilirlik denetimi** — hedef metni «ölçülebilir mi (sayı/tarih/çıktı var mı)» evet/hayır + düzeltme önerisi ·
    değer 3 · S (0,5 g).
- **Eksik:** —

### Değerlendirme dönemi (`/ik/degerlendirme`)
- **Ne yapıyor:** Dönem aç/kapat, form şablonu, tamamlanma panosu, tek tıkla hatırlatma, kalibrasyon (birim × yöneticinin
  verdiği puan dağılımı; «Adları gizle») (`ReviewCycle.tsx:1-2`, `Calibration.tsx`).
- **Kim:** İK, genel müdür (kalibrasyon).
- **Bugün AI:** Yok; sistem puan üretmez (`Calibration.tsx:1-2`).
- **Beklenti:** Form şablonu taslağı; dönem sonu İK raporu.
- **Yapabileceklerimiz:**
  - **Form şablonu taslağı** — yetkinlik listesinden davranışsal ölçüt tanımları · değer 2 · S (1 g).
  - **Dönem kapanış raporu** — tamamlanma, itiraz sayısı, birim dağılımı (SQL, eşikli) → 4 cümle · değer 2 · S (0,5 g) ·
    koruma: kalibrasyona model yorumu eklenmez (kişi sonucu doğurabilir).
- **Eksik:** 360 geri bildirim ve tema özeti analizde «sonraki sürüm».

## M58 Çalışan deneyimi ve bağlılık

### Anketlerim (`/ik/anketlerim`)
- **Ne yapıyor:** Açık anketlerim; «Cevapla» her seferinde yeni tek kullanımlık bağlantı (`MySurveys.tsx:1-2`).
- **Kim:** Her çalışan.
- **Bugün AI:** Yok. AI önerilmez (anonimlik; ekran yalnız bağlantı üretir).
- **Beklenti / öneri:** — · **Eksik:** —

### Anket formu (`/ik/anket/:token`, `/ik/anket/k`, `/ik/anket/k/:kod`)
- **Ne yapıyor:** Oturumsuz, telefon öncelikli, ekranda en çok 4 soru; jeton ya da basılı kodla (`SurveyForm.tsx:1-3`).
- **Kim:** Çalışan (bilgisayarsız çalışan dahil).
- **Bugün AI:** Yok.
- **Beklenti:** Açık uçlu cevapta kişisel bilgi yazılmaması uyarısı.
- **Yapabileceklerimiz:**
  - **Yazarken kimlik ipucu uyarısı** — tarayıcıda kural (ad, e-posta, telefon kalıbı) ile «bu cümle sizi tanıtabilir» uyarısı;
    model yok, metin sunucuya gitmeden · değer 3 · S (0,5 g) · koruma: anonimlik tasarımı değişmez.
- **Eksik:** —

### Öneri kutusu (`/ik/oneriler`)
- **Ne yapıyor:** Adlı/adsız öneri, takip kodu; İK konu düzeltir, birime yönlendirir, cevaplar; «bir çalışanla ilgili şikâyet»
  İK'da kalır (`SuggestionsScreen.tsx:1-2`).
- **Kim:** Her çalışan; İK; birim yöneticisi.
- **Bugün AI:** Konu/birim kapalı seçimi, olasılık rozeti (`hr_engagement.py:1142-1160`, `SuggestionsScreen.tsx:73`).
- **Beklenti:** Cevap taslağı; benzer önerilerin gruplanması.
- **Yapabileceklerimiz:**
  - **Cevap taslağı** (M58 §13; kodda yok) — maskeli öneri metni + İK notundan kibar cevap · değer 3 · S (0,5 g) · koruma:
    gönderen İK; adsız öneride kimlik tahmini yapılmaz.
  - **Benzer öneri gruplama** — gömmeyle yakın önerileri tek başlıkta toplar · değer 2 · S (1 g).
- **Eksik:** —

### Bağlılık panosu (`/ik/baglilik`)
- **Ne yapıyor:** eNPS ve endeks eğilimi, yanıt oranı, madde sonuçları, eşiğe tabi birim kırılımı, tema özeti (alıntısız),
  öneri kutusu döngüsü (`EngagementDashboard.tsx:13-14`).
- **Kim:** İK, genel müdür.
- **Bugün AI:** Açık uç yorumlar maskelenip kapalı tema listesine ayrılır ve tema başına alıntısız özet
  (`hr_engagement.py:932-1000`, `hr_engagement_api.py:227-236`, `EngagementDashboard.tsx:107-110`).
- **Beklenti:** Birim için somut iyileştirme önerisi; dönemler arası değişimin açıklaması.
- **Yapabileceklerimiz:**
  - **Birim iyileştirme önerisi (M58 §13 K3; kodda yok)** — birim sonucu (sayılar) + temalar → 3 aksiyon önerisi ve gerekçe,
    Aksiyon planına taslak olarak · değer 4 · S (1–2 g) · koruma: yalnız eşik üstü kapsam; sayı denetimi.
  - **Dönem değişimi özeti** — iki anket arası madde farkları (SQL) → 3 cümle · değer 3 · S (0,5 g).
- **Eksik:** —

### Birimimin sonucu (`/ik/birimim`)
- **Ne yapıyor:** Yöneticinin biriminin paylaşılmış sonucu; eşik altında «üst birimle birlikte» (`MyUnitResults.tsx:1-2`).
- **Kim:** Birim yöneticisi.
- **Bugün AI:** Yok.
- **Beklenti:** «Ne yapmalıyım» önerisi.
- **Yapabileceklerimiz:** Bağlılık panosundaki birim iyileştirme önerisinin, İK paylaştığında burada görünmesi · değer 3 · S
  (0,5 g, üstteki işle) · koruma: İK paylaşım kararı şart.
- **Eksik:** —

### Anket yönetimi (`/ik/anket-yonetimi`)
- **Ne yapıyor:** Şablonlar (ikinci kişi onaylar), anket açma, gösterim eşiği (İK girer, yalnız yükselir), birim kırılımı,
  basılı kodlar, kapanış, birim sonucunu paylaşma (`SurveyAdmin.tsx:1-2`).
- **Kim:** İK.
- **Bugün AI:** Yok.
- **Beklenti:** Soru taslağı; soru yanlılık denetimi.
- **Yapabileceklerimiz:**
  - **Soru taslağı ve yönlendirici soru denetimi** — nabız anketi için madde önerisi + «yönlendirici/çift soru var mı»
    `choose` · değer 2 · S (1 g).
- **Eksik:** —

### Aksiyon planı (`/ik/aksiyonlar`)
- **Ne yapıyor:** Anket sonrası aksiyonlar: sorumlu, son tarih, durum; sonraki ankette ilgili maddeyle yan yana (`ActionsScreen.tsx:1-3`).
- **Kim:** İK, birim yöneticisi.
- **Bugün AI:** Yok.
- **Beklenti:** Aksiyonun etkisinin ölçülmesi.
- **Yapabileceklerimiz:**
  - **Aksiyon–madde etkisi özeti** — aksiyon öncesi/sonrası madde skoru (SQL) → 2 cümle, «neden-sonuç değil ilişki» notuyla ·
    değer 2 · S (0,5 g).
- **Eksik:** —

## Grubun en değerli 10 AI önerisi

Sıra: değer (yüksekten), sonra zorluk (kolaydan). Gün tahmini tek geliştirici, test sunucusunda gerçek veriyle doğrulama dahil değil.

| # | Öneri | Ekran(lar) | Teknik | Değer | Zorluk | Koruma |
|---|---|---|---|---:|---|---|
| 1 | **Aylık finansal yorum taslağı** — özet/gelir tablosu/kârlılık JSON'undan 5–8 cümle, kurul paketine | `/finansal-raporlar` Özet | olgu → özet, sayı denetimi (risk brifing kalıbı) | 5 | S (1–2 g) | her sayı girdide; «taslak», CFO onayı |
| 2 | **Sapma nedeni taslağı** — sapan bütçe satırını alt kırılımın katkısıyla (SQL) açıklayan 1–2 cümle; bugün not elle | `/finansal-raporlar` Bütçe–gerçekleşme, `/butce` İzleme | kural katkı ayrıştırması + özet | 5 | S (1–2 g) | sayı denetimi; kayıt insanın |
| 3 | **Sabah saha brifi** — temsilcinin günü için 4–5 cümle (planlı ziyaret, ilk 3 öncelik ve gerekçe, vadesi geçmiş) | `/saha` Bugün (telefon) | özet + mevcut `numbers_ok` | 5 | S (1 g) | temsilci kapsamı süzgeci; kural metni yedek |
| 4 | **Tahmin güven aralığını görünür yapmak** — p10/p90'ı okuyup stok kartı, bitecekler ve bütçe senaryolarında göstermek (muhafazakâr/temel/iyimser = p10/p50/p90) | `/stok/:stokKodu`, `/stok/bitecekler`, `/butce` | zaman serisi tahmini (mevcut motor, yalnız okuma genişler) | 5 | S (1–2 g) | aralık her zaman görünür; kaynak etiketi |
| 5 | **Tahmini yıl sonu kapanışı** — gerçekleşen + kalan aylar bandı, hedefe göre | `/butce` İzleme | zaman serisi tahmini | 5 | M (2 g) | bant; «tahmin» etiketi |
| 6 | **Olasılıklı 13 haftalık nakit bandı** — tahsilat/ödeme haftalık serisinden p10–p90 ve «en kötü %10» kasa çizgisi | `/finansal-raporlar` Nakit | zaman serisi tahmini + kural vadeler | 5 | M (3 g) | vadesi belli kalemler kuraldan; «geçmiş tahmin ↔ gerçekleşen» ile sınanır |
| 7 | **Tahmine dayalı tükenme listesi** — ortalama hız yerine p50/p90 talep; okul sezonu gibi mevsimselliği yakalar | `/stok`, `/stok/bitecekler`, `/tedarik/yuk` (gelecek baskı yükü gölgesi) | zaman serisi tahmini | 5 | M (2–3 g) | kural listesi yanında; sınamada iyileşmezse açılmaz |
| 8 | **Taranmış belge okuma (OCR) ortak hattı** — şartname, özgeçmiş, sertifika, mevzuat, fatura dökümü | `/ihale/:id`, `/ik/ise-alim/aday/:id`, `/ik/egitim`, `/risk-uyum`, `/kargo/mutabakat` | belge okuma/OCR + mevcut alıntı denetimi | 5 | M (2–3 g) | OCR metni etiketli; İK'da maske önce |
| 9 | **Finansal denetim bulgu açıklaması + istisna kümeleme** — her kontrole «ne demek, olası neden, bakılacak belge»; istisnaları muhtemel sınıfa ayırma | `/finansal-denetim` | özet + `QueuedLlm.choose` | 4 | S–M (1–2 g + 2 g) | bulgu kuraldır; model yalnız açıklar |
| 10 | **Serbest not sinyali (CRM etkinlik + portal ziyaret notları)** — tahsilat sözü / şikâyet / sipariş / iade talebi / kapanış sinyali etiketi ve son 5 notun özeti | `/bayi-risk/:code`, `/saha/musteri/:code`, `/musteri-iliskileri/cari/:kod` | gece `choose` (BATCH) + özet | 4 | S (1–2 g) | skor bileşeni yapılmaz; gizli not ve kişi adları dışarıda |

Hemen arkasından (değer 4): emsal içerik denetimi (`/ilk-baski/kitap/:code`) ve ilk dağılım benzerlik sorusuna özet/yaş
eklenmesi (`/ilk-dagilim/:stok`) — ikisi aynı kalıp, S; bayi DSO tahmini (`/bayi-risk`, M); belirsizlik tabanlı güvenlik
stoku (`/stok/esikler`, M); ihale risk koşulu işaretleme (`/ihale/:id`, S); M58 birim iyileştirme önerisi (`/ik/baglilik`,
S); M56 kaynak bağlı yıl sonu taslağı (`/ik/*/degerlendirme/:id`, M); mülakat notu derlemesi (`/ik/ise-alim/aday/:id`, M);
fiyatlama onay gerekçesi ve anlamsal emsal (`/fiyatlama`, S/M); sesli ziyaret notu (`/saha`, `/okul-tanitim/:id`, M —
konuşma→metin servisi doğrulanmadı).

## Ortak altyapı ihtiyaçları

1. **Tahmin motoru istemcisi (tek yer).** Bugün motor yalnız `management/zeki_tahmin.py`'den çağrılıyor; Bütçe ve Stok
   onun dosya önbelleğinden p50 okuyor (`budget_sources.py:296-308`). Gerekli: kantilleri (p10/p50/p80/p90) döndüren tek
   köprü istemcisi (`forecast_for(series_id, horizon)`), seri üreten SQL'in kaynağı, önbellek ve **geriye dönük sınama
   zorunluluğu** (M10'daki `beta = 0` kararı gibi: sınamada iyileştirmeyen tahmin açılmaz). Kullananlar: M45 nakit, M46
   bütçe ve yıl sonu, M43 stok/tükenme/güvenlik stoku/depo hacmi, M52 gelecek baskı yükü, kağıt ve birim maliyet, M9 maliyet
   senaryosu, M59 DSO, M38 cari alım bandı, M47 KRI öncü tahmini, M44 kargo gideri, M29 takip bandı. Ekran sözleşmesi:
   rakam motordan, aralık her zaman görünür, «tahmin» etiketi, model adı yok.
2. **Olgu → metin anlatıcısı.** Sayı denetiminin en az altı kopyası var (`field_sales.numbers_ok`, `school_visits.py:1632`,
   `dealers.py:1217`, `supply_suggest.py:41`, `distribution` `safe_model_text`, risk/shipping içindeki denetimler) ve teknoloji
   adı denetimi iki yerde (`supply_suggest._TECH`, `hr_learning.py:267`). Tek ortak fonksiyon (olgu JSON, istem, sayı + tarih
   + teknoloji adı denetimi, kural metni yedeği, «kaynak: zeki/kural» etiketi, önbellek anahtarı = girdi özeti) bu gruptaki
   önerilerin yarısının (yorum, özet, brif, gerekçe, sapma nedeni) maliyetini S'ye indirir.
3. **Belge okuma + OCR + alıntı denetimi.** Metin katmanlı PDF/DOCX okuma M33 (`tenders.py:621-670`) ve M55'te
   (`hr_recruit_text.py`) ayrı ayrı; taranmış belgede ikisi de hata veriyor (`tenders.py:1563`, `hr_recruit_text.py:87`).
   Editör modülünde ölçülmüş bir OCR okuyucu var (`apps/editor/deploy/models.yaml:99-104`; `apps/editor/images/ocrmypdf/`).
   Gerekli: köprüden LLM kapısı gibi sıraya giren bir belge okuma ucu + M33'teki «alıntısı belgede yoksa maddeyi at»
   denetiminin (`_quote_ok`) ortak hâli. Kullananlar: M33, M55, M57 sertifika, M47 mevzuat/kanıt, M45 vergi takvimi, M44 kargo
   fatura dökümü, M52 matbaa faturası, M9 rakip fiyat listesi, M31 akademik takvim. GPU paylaşımı (editör GPU 1, BI GPU 0)
   sıraya bağlanmalı.
4. **Kitap özeti gömme dizini.** Köprüde gömme ucu (`llm_openai.py:149` `/embeddings`) ve bir vektör yönlendirici var
   (`app.py:361`), ama kitap içerik benzerliği hiçbir satış/finans ekranında kullanılmıyor; benzerlik yazar/dizi/kitaplık
   kuralıyla. Gerekli: `new_kitapBase` özet (HTML temizlenmiş) + tür + hedef yaş için gece güncellenen tek dizin. Kullananlar:
   M29 emsal havuzu, M10 emsal denetimi ve yeni kitap formu, M9 anlamsal emsal, M30 kitap önerisi, M32 tema araması, M43 set
   eşi, M57 ihtiyaç kümeleri, M58 benzer öneri.
5. **Serbest metin not etiketleyici (gece, BATCH).** CRM `new_etkinlikBase` notları ve portal `semantic_saha_ziyaret` M30,
   M38, M59'da okunuyor ama etiketlenmiyor. Tek gece işi (kapalı küme etiket + olasılık, kişi adı maskeli — İK'daki
   `rule_mask` yeniden kullanılır) üç ekranı besler.
6. **Kapalı seçim eşiklerinin ortak ayarı ve ölçümü.** Her modül kendi eşiğini tutuyor (dağılım 0,90/0,50 sabit
   `distribution.py:765`, ihale ayarlı, İK 0,8 sabit `hr_recruit_api.py:129`). `docs/analiz/llm-choose.md` «eşiği sabit yazmayın,
   golden set ile seçin» diyor: modül × karar türü başına `admin.conf` anahtarı + küçük etiketli örnek kümesiyle kabul/isabet
   ölçümü.
7. **Sohbet veri kataloğu boşlukları.** `chat_topics.json`'da `risk` ve `ik` konularının `data` listesi boş: risk kaydı ve
   göstergeler kataloğa girmeli; İK için yalnız **toplu, eşikli** tanımlı sorgular (kişi düzeyi sorgu tanımı yok, M58 §13) —
   analizdeki «İK soru kutusu» bugün kodda yok.
8. **Telefon için konuşma → metin.** M30/M31/M38 sahada not ve rapor için isteniyor; BI tarafında konuşma tanıma servisi
   bulunmadı (destek masasının akış bileşeninde transkript izleri var — `apps/destek/frappe-apps/flow` — işlevi
   **doğrulanmadı**). Ses kaydı saklanmamalı, yalnız onaylı metin.
9. **Ad tutarlılığı.** Model kullanmayan iki özellik «ZEKİ AI» adını taşıyor (M46 «ZEKİ AI önerisi oluştur», `budget.py:12`;
   M10 «ZEKİ AI emsal tahmini», `BacktestTab.tsx:22`). «Zeki AI» adının yalnız model ya da tahmin motoru çıktısına verilmesi
   kullanıcı güveni için karara bağlanmalı.
