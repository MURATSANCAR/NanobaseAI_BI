# M50 — ZEKİ Model Eğitim ve Geliştirme: kullanıcı ihtiyaç analizi

Durum: analiz (kısmen kodlu: eş anlamlı hattı, kavram onayları, kural madencisi, kalite kapısı, golden set, soru izleme,
son okuma isabeti — hepsi dağınık; birleşik kalite ekranı ve sürüm kaydı yok) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı
`specs/M50.txt`, Veri Haritası (`veri_haritasi2.txt`: «Model Girdileri», «Benchmark Girdileri»), `PROJECT-MEMORY.md`
(kalite kapısı durumu, soru hattı kararları, LLM kapısı, eş anlamlı hattı, kural madencisi, son okuma), `tests/text2sql/`
(`quality-gate.py`, `golden-timas.json`, `resolver-gate.py`, `answer-gate.py`, `answers-set100.json`, `set100.jsonl`,
`set1000.jsonl`, `set1000-karne-0918.jsonl`, `source-reading.py`), `backend/semantic_layer/store/schema.py`
(`sl_query_log`, `sl_vocabulary`, `sl_concept`, `sl_llm_job`), `backend/semantic_bridge/app.py` (`/api/v1/feedback`,
`/api/v1/semantic/gaps`), `src/canvas/admin/PromptTracker.tsx`, `src/i18n/en.json` (`bi.feedback.*`), bellek:
`quality-gate-and-golden-set`, `vocabulary-pipeline`, `refutation-step`, `llm-gate`, `full-set-regression-after-every-change`,
`fix-classes-not-questions`, `certify-demotes-authored-vocabulary`, `semantic-gate-rewrite`, `proofing-structure`,
`editor-single-visual-read-is-noise`, `llm-tt-gpu`, `vllm-choice-logprobs`, `no-static-solutions`, `shared-server-gate-pollution`,
`semantic-layer-v1-decision` (başlık). Sunucuya bağlanılmadı.

## 1. Modül ne işe yarar

Zeki AI'ın her modülde ne kadar isabetli çalıştığını ölçer, hataları sınıflar, iyileştirme önceliğini çıkarır ve her
değişikliğin (model, katalog, kural, kod) önce/sonra etkisini kayda geçirir. İnsanların onay/ret kararları (eş anlamlı,
kavram, SEO önerisi, son okuma bulgusu, çeviri düzeltmesi, soru inceleme notu) iyileştirmenin ham maddesidir. Ölçüm ve
izleme ekip kararına veri verir (K3); iyileştirme adayları (yeni eş anlamlı, yeni golden soru, kural) Zeki AI önerisi +
ekip onayıyla işlenir (K2).

TİMAŞ'taki gerçek durum: ZEKİ bir «ince ayarlı model» değil; doğru kaynak katalog + kanıt motorudur, model yalnız soruyu
okur ve SQL taslağı yazar (bellek `semantic-layer-v1-decision`). Bugün iyileştirme döngüsü çalışıyor ama **yalnız
geliştiricinin elinde**: kapılar sunucuda elle koşulur (`quality-gate.py`, `resolver-gate.py`, `answer-gate.py` ~35 dk,
`testset_regress.py`), sonuçlar JSON dosyalarında ve tek seferlik sayfalarda; müşteri tarafı Zeki AI'ın isabetini hiçbir
ekranda göremiyor. Son kaydedilen kapı durumu 60 SAĞLAM / 9 BOZUK / 0 KARARSIZ, sonra 62 (PROJECT-MEMORY «Kalite kapısı
durumu (2026-09-21)»); 1000 soruluk ilk karne 09-18: 109 doğru / 79 kısmen / 113 yanlış / 58 boş-şüpheli / 575 ret / 66
hata-netleştirme. Son kullanıcının «bu cevap yanlış» diyebileceği düğme yok: `sl_query_log.validated` kolonu ve
`/api/v1/feedback` ucu duruyor, ekrandaki bileşen kaldırılmış (`bi.feedback.*` çevirileri var, kullanan bileşen yok).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| NanobaseAI model ve katalog ekibi | Bizim ekip (bugün kapıları koşan, katalog yazan) | Her değişiklikte; günlük | Masaüstü |
| Zeki AI iş sorumlusu (TİMAŞ) | **Varsayım**: Mali İşler ya da yönetim raporlamasından bir kişi. Kanıt: golden setin 48 vakasının 27'si «iş tarafından, şemaya bakmadan» yazılmış (bellek `quality-gate-and-golden-set`) | Haftalık | Masaüstü |
| Modül sahipleri / onaycılar | Editörya (son okuma kararı, redaksiyon önerisi), Pazarlama (SEO onayı), çeviri inceleyenleri, Finans (soru cevapları) | İş akışının içinde (zaten karar veriyorlar); ayda bir kendi karnesine bakar | Masaüstü |
| Son kullanıcılar | Zeki AI'a soru soran herkes | Her cevapta tek tık geri bildirim | Her ikisi |
| Üst yönetim / DYK | Genel müdürlük | Aylık «ZEKİ sağlık ve ilerleme raporu» (DYK iş tanımı) | PDF |

## 3. Bugün bu iş nasıl yapılıyor

- **Model ve katalog ekibi:** değişiklik → `resolver-gate.py` (~2 dk, model yok) → hedefli `answer-gate.py` → tam set
  `run_testset.py` (~35 dk) + `testset_regress.py` → kaydet ya da geri al (bellek `full-set-regression-after-every-change`).
  Sınıf taraması modelsiz `set1000` üzerinde `/api/v1/semantic/resolve` ile (bellek `fix-classes-not-questions`). Tıkanma:
  sonuç dosyada; «önce» ölçümüyle «sonra» arasına başka oturumun kurulumu girebiliyor ve fark yanlış kişiye yazılıyor (bellek
  `shared-server-gate-pollution`); model/katalog/kural sürümü tek yerde kayıtlı değil (günlük ve bellek notları); sorgu
  kaydında yalnız `catalog_version` var.
- **Soru izleme:** Yönetim → Soru izleme: her soru, SQL, tam sonuç, cevap türü, kapı kararı; yönetici «Düzeltilecek /
  Düzeltildi / Önemsiz» işaretler ve not yazar (`PromptTracker.tsx`). Tıkanma: işaretlenen soru golden sete ya da sınıf
  sayımına kendiliğinden gitmiyor; yalnız yöneticiye açık.
- **Eş anlamlı ve kavram onayları:** `/es-anlamlilar` (PROPOSED/APPROVED/REJECTED, makinenin karar veremediği dört durum
  kişiye kalır), `/onaylar` (kavram inceleme → `human_certify`), kural madencisi adayları (~600 onayda, PROJECT-MEMORY dizin
  haritası). Hepsi yönetici-özel; iş sorumlusu göremez.
- **Katalog boşlukları:** `/api/v1/semantic/gaps` kullanıcıların sorup katalogda karşılığı olmayan terimleri sıklıkla
  sıralar; 1000 soruluk karnede en büyük kalem 377 ret «katalogda olmayan iş terimi».
- **Editör tarafı:** son okumada editörün «Doğru / Yanlış alarm» kararı denetim adı + sürüm bazında isabet üretir
  (bellek `proofing-structure`); model karşılaştırması `editor.compare_models` ile, tek görsel okumanın gürültüsü ölçülerek
  (bellek `editor-single-visual-read-is-noise`). Bu veriler GPU'daki editör veritabanında; köprü o veritabanına dokunmaz.
- **Çeviri:** ZEKİ ham taslak ayrı sütunda, inceleyen düzeltip onaylar, MQM puanı (PROJECT-MEMORY M4) — taslak ile onaylı
  metin farkı ölçülmüyor.
- **SEO:** öneri onay/ret kararları `semantic_audit`'e yazılıyor; onay oranı raporu yok.
- **Model sürümü:** tek sunulan ad `nanobaseAI` (arkada 27B, 2026-09-19'dan beri); değişiklik geçmişi yalnız bellek/günlükte.
- **İnce ayar (SFT):** yapılmıyor; veri seti yok. İş tanımındaki SFT/BLEU/MRR maddeleri bugünkü mimaride doğrudan karşılıksız (§12'de uyarlama).

## 4. İhtiyaçlar ve acı noktaları

**Model ve katalog ekibi**
1. Tek komutla koşan, sonucu köprüye yazan kapılar; önce/sonra farkının değişiklik kaydıyla (kod sha, katalog sürümü, kural dosyası özeti) eşlenmesi.
2. Hata sınıfı panosu: sınıf başına soru sayısı ve eğilim (kaynak kaçırma, ölçü yerine kolon, tanımsız terim, dönem/şekil, model reddi, veri yok, yetki dışı).
3. İnsan kararlarının tek kuyrukta toplanması (eş anlamlı, kavram, kural madencisi, «Düzeltilecek» sorular).
4. Aynı sunucuda başka kurulumun ölçümü kirletip kirletmediğinin otomatik uyarısı (ölçüm penceresinde kurulum var mı).

**Zeki AI iş sorumlusu**
1. «Zeki AI ne kadar doğru cevap veriyor, geçen aya göre» — tek sayı ve alan kırılımı (satış, cari, muhasebe, CRM).
2. İş tarafının golden soru yazabilmesi ve cevabın doğrusunu (referans rakam) girebilmesi.
3. Kullanıcı şikâyetlerinin (yanlış işaretli cevaplar) listesi ve ne olduğu.

**Modül sahipleri**
1. Kendi alanında Zeki AI isabeti: son okuma denetimi başına isabet, SEO önerisi onay oranı, çeviri taslağının düzeltilme oranı.
2. Kötü giden öneri türünü kapatma/açma talebi (ör. «bu denetimin alarmları çoğu yanlış»).

**Son kullanıcılar**
1. Cevabın altında «Doğru / Kısmen / Yanlış» + kısa not; yanlış dediğinde «incelemeye alındı» geri dönüşü.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Model ekibi olarak bir katalog değişikliğinden sonra tam seti koşturup bozulanları değişiklik kaydıyla yan yana görmek istiyorum, çünkü bozulmayı kimin/neyin yaptığını ayırmam gerekiyor.
- Model ekibi olarak hataları sınıf başına soru sayısıyla görmek istiyorum, çünkü tek soruyu değil sınıfı düzeltiyoruz.
- Model ekibi olarak kullanıcıların «yanlış» dediği cevapları tek kuyrukta görmek istiyorum, çünkü gerçek hatalar oradan geliyor.
- İş sorumlusu olarak her ay Zeki AI'ın doğru cevap oranını alan kırılımıyla görmek istiyorum, çünkü yönetime rapor veriyorum.
- İş sorumlusu olarak kendi yazdığım bir soruyu ve doğru rakamını test setine eklemek istiyorum, çünkü sistemin benim işimi bilip bilmediğini ben ölçmeliyim.
- Editör olarak son okuma denetimlerinin isabetini görmek istiyorum, çünkü çok yanlış alarm veren denetime güvenmem.
- Pazarlama uzmanı olarak SEO önerilerinin kaçını değiştirmeden onayladığımı görmek istiyorum, çünkü öneri kalitesini ölçmek istiyorum.
- Son kullanıcı olarak yanlış bulduğum cevabı tek tıkla bildirmek istiyorum, çünkü aynı yanlışı başkası da görmesin.

**Ana ekranlar ve akış** (`/timas/zeki-kalite`)
- İlk açılış «Karne»: modül başına tek satır — BI soru-cevap (SAĞLAM oranı, ret oranı, kullanıcı «yanlış» sayısı), son
  okuma (denetim isabeti), çeviri (taslağın düzeltilme oranı, MQM), SEO (değiştirmeden onay oranı), redaksiyon (öneri kabul
  oranı); her satırda son 4 hafta eğilimi ve son ölçüm tarihi. Ölçülmemiş satır «ölçülmedi» der.
- Sekmeler: Karne · Koşular (kapı koşuları, önce/sonra, bozulan sorular) · Hata sınıfları · Karar kuyruğu (eş anlamlı,
  kavram, kural adayı, kullanıcı geri bildirimi, «Düzeltilecek») · Test sorusu yaz (iş sorumlusu) · Sürümler.
- En sık 3 işlem: karneyi okumak (0 tık), bozulan soruyu açıp önce/sonra SQL ve sonucu görmek (2 tık), kuyrukta bir kararı
  vermek (1 tık/satır).
- Cevap kartlarında (Genel bakış, Pano soru kutusu, Kampüs) «Doğru / Kısmen / Yanlış» + not.

**Zeki AI'ya soracakları örnek sorular** (modül içi soru kutusu; cevap bu modülün tablolarından)
- «Geçen haftaki katalog değişikliğinden sonra hangi sorular bozuldu?»
- «Bu ay kullanıcıların yanlış dediği cevapların en sık sınıfı ne?»
- «Cari sorularında doğru cevap oranı geçen aya göre nasıl?»
- «Hangi son okuma denetiminin yanlış alarm oranı en yüksek?»
- «En çok sorulup katalogda karşılığı olmayan 10 terim ne?»
- «Model değişikliğinden sonra ortalama cevap süresi ne oldu?»
- «Onay bekleyen kaç eş anlamlı var, en eskisi ne zamandan?»

**Otomasyon katmanı**
- K1: kapı koşusu sonuçlarının kaydı, karne hesaplama, hata sınıfı sayımı (sabit kurallar + kapı kararı), ölçüm penceresinde
  başka kurulum tespiti, geri bildirimin kuyruğa düşmesi.
- K2: eş anlamlı/kavram/kural adayı (bugünkü hatlar), «Düzeltildi» işaretli sorudan golden aday üretimi, sınıflanamayan
  hatalar için sınıf önerisi → model ekibi onaylar.
- K3: model değişikliği (yeni model, istem ayarı, eşik) ve ince ayar kararı; iyileştirme önceliği sıralaması → ekip ve yönetim.

**Bildirim/uyarı**
- Kapı koşusu «bozulan > 0»: model ekibi, anında (e-posta + ekran).
- Kullanıcı «yanlış» bildirimi: model ekibi, günlük özet; aynı soruya 3+ «yanlış»: anında.
- Karar kuyruğunda 7 günden eski bekleyen: kuyruk sahibi, haftalık.
- Aylık karne: iş sorumlusu + yönetim, PDF.

**Onay ve yetki**
- `sayfa:zeki-kalite` — model ekibi, iş sorumlusu, modül sahipleri (karne satırı rolüne göre süzülür: kişi yalnız sayfa yetkisi olan modüllerin satırını görür).
- `ozellik:zeki.geri-bildirim` — cevap kartındaki düğme (Herkes).
- `ozellik:zeki-kalite.test-yaz` — golden soru ekleme/düzenleme (açıkça verilir).
- `ozellik:zeki-kalite.karar` — karar kuyruğunda onay/ret (açıkça verilir; bugün yönetici-özel olan eş anlamlı/kavram kararlarını role taşır).
- `ozellik:zeki-kalite.kosu` — kapı koşusu başlatma (açıkça verilir; model kapasitesi harcar).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Soru, SQL, cevap türü, kapı kararı, süre, katalog sürümü, soran | Meta DB `sl_query_log` | Var | Hacim ve dağılım **ölçülecek** |
| Kullanıcı geri bildirimi | `sl_query_log.validated` + `/api/v1/feedback` | Kolon ve uç var, ekran düğmesi yok | Yorum kolonu yok; «kısmen» değeri yok |
| İnceleme işaretleri | `sl_query_log.review_flag/review_note/reviewed_by` | Var | Golden sete bağ yok |
| Golden set ve taban | `tests/text2sql/golden-timas.json` (48), `quality-baseline-golden.json` | Depoda dosya | Köprüde tablo yok; iş tarafı ekleyemiyor |
| Cevap altın seti | `answers-set100.json` (bağımsız referans SQL) | Depoda dosya | Aynı |
| Tam set ve karne | `set100.jsonl`, `set1000.jsonl`, `set1000-karne-0918.jsonl` | Depoda dosya; koşu sonuçları sunucuda `~/testset/` | Koşu kaydı tabloda değil |
| Katalog boşlukları | `/api/v1/semantic/gaps` (`term_gaps`) | Var | Ekranı yönetici-özel sözlükte (**ölçülecek**: hangi ekranda gösterildiği) |
| Eş anlamlı kararları | `sl_vocabulary` (status, source, decided_by) | Var | — |
| Kavram durumu ve sürümü | `sl_concept` (status, version, explain_json.human_certified_by), `sl_catalog_version` | Var | — |
| Model süreleri | `sl_llm_job` (`queue_wait_ms`, `llm_ms`, module), `sl_llm_queue` | Var | — |
| Model sürümü | GPU `/v1/models` (`root`), env | Bellek/günlükte | Sürüm tablosu yok |
| Son okuma kararları | Editör veritabanı (GPU) `proof_decision` | Var, editörde | Köprüye okuma ucu gerek (editör kart servisi üzerinden; tablo adları editör göçlerinden teyit) |
| Çeviri taslak/onay farkı | `semantic_translation_segments` (taslak sütunu + hedef), `semantic_translation_errors` (MQM) | Var | Fark ölçümü yok |
| SEO karar oranı | SEO öneri tabloları + `semantic_audit` | Var | Oran hesabı yok |
| Redaksiyon öneri kabul/red | `semantic_editorial_*` | Var | Oran hesabı yok |
| Sektör yapay zekâ kıyasları | Dış | Yok; müşteride web taraması kapalı | İlk sürüm dışı |

## 7. Diğer modüllerle bağ

- **Bütün Zeki AI kullanan modüller (M1–M8, M10, M12, M25/M26 SEO, M46, BI):** karar kayıtlarını verir, karne satırını alır.
- **M48 IT:** model süresi/kuyruk metrikleri ortak; model değişikliği M48 sürüm kaydında da görünür.
- **M49 Güvenlik:** modele kişisel veri gitmediğinin kanıtı; `NOT_PERMITTED` cevaplar hata sınıfında «yetki dışı» olarak ayrı sayılır, isabetsizlik sayılmaz.
- **M51 Destek:** son kullanıcının «Zeki AI yanlış» şikâyeti M51'e değil M50 kuyruğuna düşer; M51'in talep sınıflandırma isabeti M50 karnesinde bir satırdır.
- **DYK:** aylık ZEKİ sağlık ve ilerleme raporu.

## 8. Kısıtlar

- Rakamı model üretmez: karne ve kapı sonuçları doğrudan veritabanı sorgusuyla doğrulanır (bellek `verify-direct-db`: referans köprünün `run_sql`'inden değil, doğrudan bağlantıdan).
- Statik çözüm yok: golden soru yalnız test kâhinidir, ürüne kural olarak girmez (bellek `no-static-solutions`); editörde kitaba özel kural yok (bellek `editor-no-book-specific-development`).
- Kapı koşuları paylaşılan sunucuda: ölçüm penceresindeki başka kurulum kayda geçmeli; köprü yeniden başlatılmaz, `reload` kullanılır.
- Sayı tavanı yok: kuyruk ve koşu listeleri tavansız; kural bütçesi sondan kesmez (bellek `full-set-regression-after-every-change`).
- Ekranda teknoloji/model adı yok: «Zeki AI modeli, sürüm 2026-09-19» gibi; iç kayıtta gerçek ad durur.
- CRM/T-soft'a yazma yok. Kararlar köprü tablolarında.
- Demo veri yok: ölçülmemiş modül karnede «ölçülmedi».
- KVKK: `sl_query_log.result_json` kişisel veri içerebilir; golden adayına dönüşen sorunun sonucu kopyalanmaz, yalnız soru + referans SQL + beklenen özet (sayı) saklanır. Saklama süresi M49 politikasıyla.
- İnce ayar (SFT) kararı K3: GPU kapasitesi (2×H100, GPU 1 editörün — bellek `llm-tt-gpu`) ve mimari karar (katalog = doğru kaynak) nedeniyle ilk sürümde eğitim yok; eğitim verisi olacak kararlar toplanır.

## 9. Kapsam önerisi

**İlk sürüm**
- Kapı koşularının köprüye yazılması (`quality-gate.py`, `resolver-gate.py`, `answer-gate.py`, `testset_regress.py` → `--report`), önce/sonra ve bozulan sorular ekranı.
- Sürüm kaydı: kod sha, katalog sürümü, bilgi paketi özeti (dosya md5), model sürümü — her koşuda ve her kurulumda.
- Kullanıcı geri bildirimi düğmesi (Doğru/Kısmen/Yanlış + not) ve kuyruk.
- Karne: BI soru-cevap satırı (koşu + geri bildirim + cevap türü dağılımı) ve SEO/çeviri/redaksiyon oranları (köprüdeki tablolardan).
- Hata sınıfı sayımı: `answer_type` + kapı kararından kurallı sınıf.

**Sonraki sürüm**
- İş sorumlusunun golden soru yazması (referans SQL'i ekip onaylar).
- Birleşik karar kuyruğu (eş anlamlı, kavram, kural adayı) ve bu kararların role taşınması.
- Son okuma isabeti (editör kart servisi üstünden).
- Model karşılaştırma koşusu (A/B: aynı set, iki model/ayar; tekrar gürültüsü tabanıyla).
- Aylık DYK raporu PDF; sınıflanamayan hatalar için Zeki AI sınıf önerisi.

**Mevcut kodda yeniden kullanılacaklar**
- `tests/text2sql/quality-gate.py`, `resolver-gate.py`, `answer-gate.py`, `run_testset.py` (sunucuda), `scripts/testset_regress.py`, `tests/text2sql/source-reading.py`.
- `backend/semantic_bridge/app.py` `/api/v1/feedback`, `/api/v1/semantic/gaps`, `/api/v1/admin/prompts*`.
- `src/canvas/admin/PromptTracker.tsx` (liste/süzgeç/işaret bileşenleri), `src/i18n/*` `bi.feedback.*` anahtarları.
- `backend/semantic_layer/vocabulary.py`, `vocabulary_probe.py`, `scripts/auto_approve_vocabulary.py`, `rule_miner/`, kavram inceleme ucu (`/api/v1/semantic/concepts/{id}/review`).
- `backend/semantic_layer/runtime/llm_queue.py`, `llm_jobs.py` (metrik), `rt.llm_for`.
- `apps/editor` `editor.compare_models`, `proof_decision` (editör tarafı, salt okunur kart servisi üstünden).

## 10. Uzmanlara sorulacak sorular

1. TİMAŞ'ta Zeki AI'ın iş tarafı sorumlusu kim olacak; golden soruları yazan 27 vakalık kaynak kişi(ler) bu işi sürdürür mü?
2. Hangi alanlarda (satış, cari, muhasebe, CRM) hangi doğruluk oranı «kullanılabilir» sayılır; ret (cevap vermeme) mi yanlış cevap mı daha kötü? (Bugünkü kural: yanlış tablodan cevap, cevapsızlıktan kötü.)
3. Son kullanıcının «yanlış» bildirimine kim, ne sürede dönmeli?
4. Modül sahipleri kendi karnesini görmek ister mi, yoksa yalnız yönetim mi görmeli?
5. Aylık raporda yönetim hangi 3 sayıyı görmek ister?

## 11. Başarı ölçütü

- Her katalog/kural/kod değişikliğinin önce/sonra koşusu kayıtlı (hedef: kurulumların %100'ü; bugün: kayıt yok).
- Bozulmanın fark edilme süresi: değişiklikten sonraki ilk koşu (≤ 1 gün).
- Kullanıcı geri bildirimi: cevapların en az %2'si işaretleniyor (ilk ay ölçülür, hedef sonra); «yanlış» bildiriminin incelenme süresi ≤ 2 iş günü.
- Karar kuyruğunda 7 günden eski bekleyen sayısı azalıyor.
- Karne eğilimi: set100 SAĞLAM oranı ve set1000 doğru oranı çeyrekten çeyreğe artıyor; ret oranı düşerken yanlış oranı artmıyor.
- İş sorumlusunun ekranı ayda en az 2 kez açması; en az 10 iş-yazımı golden soru (çeyrekte).

## 12. Uzman gözüyle en iyi sistem

**Kimin yerine geçiyorum:** kurumsal bir analitik yapay zekâ ürününü 10+ yıldır işleten ML/değerlendirme sorumlusu
(MLOps + «evaluation» ekibi başı); yanında iş tarafında 15 yıllık finans raporlama uzmanı.

**Sektörde en iyiler nasıl yapıyor:** (1) değerlendirme setleri ürünün parçasıdır; her değişiklik sürekli entegrasyonda
set üzerinde koşar, bozulma sürüm yayımını durdurur. (2) Sürümlenen her şey (model, istem, katalog, kural) kayıt altındadır;
her cevap hangi sürümlerle üretildiğini taşır. (3) Üretimde insan geri bildirimi (başparmak + not) toplanır, haftalık
triyajla sınıflanır, sınıflar değerlendirme setine yeni vaka olarak geri döner. (4) Metin-SQL ürünlerinde ölçü
«yürütme doğruluğu»dur (cevap rakamı referansla aynı mı), metin benzerliği değil; retrieval için tablo recall/precision.
(5) Model değişikliği A/B ile ve tekrar gürültüsü tabanına göre değerlendirilir. BLEU/MRR gibi genel ölçüler yalnız
uygun işte (çeviri, arama) kullanılır.

**TİMAŞ için mükemmel sistem:** «Zeki AI karnesi» tek sayfada: modül başına isabet, eğilim, son değişiklik ve etkisi.
Bozulma ekibe anında, yönetime ayda bir gider. İş tarafı soru yazar, ekip referansı doğrular, set büyür. Her yanlış
bildirim bir sınıfa düşer, sınıf kapanınca karne gösterir. İnce ayar ancak toplanan kararlar yeterli ve ölçülebilir
bir kazanç gösterdiğinde gündeme gelir (K3).

**Bir iş günü (model ekibi sorumlusu):**
- 09:00 — Karne: BI SAĞLAM 62/69, dün akşamki kural değişikliğinden sonra gece koşusunda 2 bozulma (kırmızı). Koşu
  ayrıntısı: bozulan iki soru, önce/sonra SQL ve sonuç; ölçüm penceresinde başka kurulum yok (yeşil) → değişiklik sorumlu.
- 09:40 — Kural dosyasını geri alma kararı; hedefli yeniden koşu `resolver-gate` 2 dk → temiz.
- 11:00 — Geri bildirim kuyruğu: 6 «yanlış». 4'ü aynı sınıf (ölçü yerine kolon, «iade» kelimesi). Sınıf sayımına bakar:
  set1000'de bu sınıftan 23 soru. Eş anlamlı değil kavram eksiği → katalog yazım betiğine iş.
- 14:00 — İş sorumlusunun yazdığı 3 yeni soru: ikisinin referans SQL'i doğrudan Logo'da doğrulanır, sete girer; biri
  «veri yok» (termin tarihi tutulmuyor, Kural C13) → «ölçülemez» etiketiyle ret vakası olur.
- 16:30 — Karar kuyruğu: 40 eş anlamlı; makinenin karar veremediği tek kelimeler; toplu 12 onay, 5 ret.
- Ay sonu — DYK raporu: doğru oranı, ret oranı, yanlış bildirim sayısı, kapanan sınıflar.

**«Bunu görürsem hemen kullanırım» — 3 özellik**
1. Her değişikliğin önce/sonra koşusu ve bozulan soruların yan yana SQL+sonuç görünümü.
2. Kullanıcı «yanlış» bildiriminin sınıfa düşmesi ve sınıfın kaç soruyu etkilediği.
3. İş tarafının kendi test sorusunu yazabilmesi.

**«Bunu yaparsanız kullanmam» — 3 tuzak**
1. Karneyi modelin kendi yargısıyla («LLM hakem») doldurmak; referans rakam yoksa ölçüm yoktur.
2. Tek soru düzeltip set100'le «hata yok» demek (bellek `fix-classes-not-questions`).
3. Ret oranını düşürmek için yanlış cevabı serbest bırakmak; ret ile yanlış ayrı sayılmalı.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Golden/cevap altını referansı | Referans SQL doğrudan Logo'da (`connector_from_file`): ör. net ciro satır bazlı `LINENET` (bilgi paketi `metrics/logo-timas.md`), satış = faturalı satır (`INVOICEREF` ≠ 0), yıl kopyaları `LG_211` (2021–25) / `LG_411` (2026) | CRM referans SQL'i doğrudan .28'de (ör. Kural C13 sipariş, C15 talep) | Hiçbir şey | Beklenen rakam modelden bağımsız olmalı |
| Sistem cevabının üretimi (ölçülen şey) | Katalog + derleyici; model SQL taslağı yazar | Aynı | Soruyu okur, SQL taslağı (bugünkü hat) | Ölçülen budur |
| Sonuç karşılaştırma | Referans ve sistem sonucu aynı bağlantıda | Aynı | Hiçbir şey | Yürütme doğruluğu deterministik |
| Hata sınıflama | — | — | Kural düşmeyen hatalar için sınıf önerisi (kapalı küme: kaynak kaçırma / ölçü yerine kolon / tanımsız terim / dönem-şekil / model reddi / veri yok / yetki dışı; tek token + olasılık, düşük marj «sınıflanamadı») | Kurallı sınıf çoğunu kapatır, kalan azı için model öneri verir, ekip onaylar |
| Golden aday | — | — | «Düzeltildi» işaretli sorudan soru metnini sadeleştirme ve benzer 2–3 varyant önerisi | Metin üretimi; referans SQL'i insan yazar/onaylar |
| Eş anlamlı / kavram adayı | Logo alan açıklamaları (LDDS sözlüğü) | CRM alan etiketleri | Bugünkü hat: açıklamadan aday → çürütme → onay | Mevcut |
| Terim boşluğu | — | — | Boşluk terimlerini benzer anlam kümelerine gruplama önerisi | Sıralama ve öncelik için |
| Çeviri taslak farkı | — | — | Hiçbir şey (düzenleme mesafesi kodla) | Ölçü deterministik |
| Karne özeti / DYK raporu | — | — | Sayılardan kısa yorum | Rakamlar tablodan |
| Model A/B | — | — | İki model/ayar aynı sette | Karar K3; tekrar gürültüsü tabanı şart |

Model çağrıları `rt.llm_for("zeki-kalite", priority=BATCH)` ya da ayrı betikte `QueuedLlm(..., purpose="bg:zeki-kalite")`;
kapı koşuları kullanıcı sorularının önüne geçmez (arka plan önceliği). `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/model_quality.py` — tablolar, karne hesabı, sınıf sayımı, kurulum-penceresi denetimi.
- `backend/semantic_bridge/model_quality_sources.py` — modül okumaları: `sl_query_log`, `sl_vocabulary`, `sl_concept`,
  SEO öneri tabloları + `semantic_audit`, `semantic_translation_*`, `semantic_editorial_*`, editör kart servisi (son okuma
  isabeti; köprü editör veritabanına doğrudan bağlanmaz).
- `backend/semantic_bridge/model_quality_api.py` — `register(app, *, rt, can, audit, conf)`.
- Betik değişikliği: `tests/text2sql/quality-gate.py`, `resolver-gate.py`, `answer-gate.py`, `scripts/testset_regress.py`'ye
  `--report <köprü adresi>` seçeneği: koşu bitince özet + vaka listesi `POST /api/v1/model-quality/report` (SYSTEM jetonu).
  Seçenek verilmezse bugünkü davranış aynen kalır.

**Tablolar (meta DB)**
- `semantic_mq_runs` (id, suite `golden|resolver|answer|set100|set1000|editor-proof|compare`, started_at, finished_at,
  started_by, code_sha, catalog_version, rules_digest, model_ref (iç ad), env `test|vm`, metrics_json, baseline_run_id,
  broken int, fixed int, installs_in_window_json).
- `semantic_mq_cases` (run_id, case_id, question, status `saglam|bozuk|kararsiz|veri|ret|hata`, klass, sql_text, result_digest, expected_digest, note).
- `semantic_mq_versions` (id, at, kind `model|catalog|rules|code|prompt`, ref, digest, note, by) — kurulum ve koşu kaydeder.
- `semantic_mq_feedback` (id, query_id → `sl_query_log.id`, username, verdict `dogru|kismen|yanlis`, comment, at, triage_state `yeni|siniflandi|kapandi`, klass, handled_by) — ayrıca `sl_query_log.validated` güncellenir (dogru → true, yanlis → false; kismen → null kalır).
- `semantic_mq_golden` (id, question, source `is|ekip|geri-bildirim`, author, reference_sql, reference_source `logo|crm`, expected_json, status `taslak|dogrulandi|red`, verified_by, verified_at) — doğrulanan vakalar sürümlü olarak dosyaya da dışa aktarılır (`golden-timas.json` biçiminde) ki betikler değişmeden okusun.
- `semantic_mq_classes` (klass, label, rule_json) — sabit sınıf tanımları (kurulumda tohumlanır: 7 sınıf, §13).

**Uçlar (`/api/v1/model-quality/*`)**
- `GET scorecard` (rolün sayfa yetkisine göre süzülmüş satırlar) · `GET runs` · `GET runs/{id}` · `GET runs/{id}/cases?status=bozuk`
- `POST report` (SYSTEM, çerezsiz jeton; betiklerin koşu raporu) · `POST runs/start` (`ozellik:zeki-kalite.kosu`; sunucuda `timas-testset` birimini tetikleyen iş kaydı — birimi kendisi başlatamıyorsa «sırada» kaydı açar, zamanlayıcı alır)
- `GET classes` · `GET classes/{klass}/questions`
- `POST feedback` (`ozellik:zeki.geri-bildirim`) — bugünkü `/api/v1/feedback` bunu çağıracak şekilde genişler (eski gövde uyumlu)
- `GET queue?type=feedback|vocabulary|concept|rule|todo` · `PATCH queue/{type}/{id}` (`ozellik:zeki-kalite.karar`; eş anlamlı/kavram kararında bugünkü `vocabulary.decide` ve `concepts/{id}/review` çağrılır — `human_certify` dahil)
- `GET golden` · `POST golden` · `PATCH golden/{id}` (`ozellik:zeki-kalite.test-yaz`; `status=dogrulandi` yalnız `ozellik:zeki-kalite.karar`)
- `GET versions` · `POST versions` (SYSTEM)
- `access.py` `RULES` (sistem yolu `reports/run-due` deseniyle ayrı): `("/api/v1/model-quality/report", SYSTEM)`, `("/api/v1/model-quality/versions", SYSTEM)` yalnız POST için uç içinde jeton denetimi (GET sayfa yetkisiyle), `("/api/v1/model-quality/", frozenset({page("zeki-kalite")}))`, `/api/v1/feedback` → OPEN + `FEATURE_RULES (POST, ^/api/v1/(feedback|model-quality/feedback)$, "ozellik:zeki.geri-bildirim")`.

**Ekranlar**
- `src/canvas/model-quality/ModelQualityScreen.tsx` (sekmeler §5), `Scorecard.tsx`, `RunDetail.tsx` (önce/sonra yan yana; `CardSql.tsx` yeniden kullanılır), `ClassBoard.tsx`, `DecisionQueue.tsx`, `GoldenEditor.tsx`, `Versions.tsx`. Rota `/timas/zeki-kalite`.
- `src/canvas/components/AnswerFeedback.tsx` — Genel bakış cevabı, pano soru kutusu, Kampüs soru kutusu altında; `bi.feedback.*` çevirileri (tr karşılıkları eklenir).
- Menü: `altyapi` alanında `{ id: 'zeki-kalite', label: 'Zeki AI kalitesi' }`. Yönetim → Soru izleme yerinde kalır, satırdan «Karar kuyruğuna gönder».
- Kampüs: `ModulesMenu.LIVE.M50 = '/zeki-kalite'`.
- `access_catalog.json`: `sayfa:zeki-kalite`; `ozellik:zeki.geri-bildirim` (ortak, Bütün ile gelir); açıkça verilen: `ozellik:zeki-kalite.kosu`, `ozellik:zeki-kalite.karar`, `ozellik:zeki-kalite.test-yaz`.

**Zamanlayıcı**
- Gece, katalog taramasından sonra (saat sunucudaki `nanobase-semantic-worker.timer`'a göre seçilir; ikisi üst üste binmemeli): `resolver-gate.py --report` (model yok, ~2 dk) her gece; `answer-gate.py --report` haftada bir (pazar gece; ~35 dk, arka plan önceliği).
- Her kurulumda (`deploy-*` betikleri sonunda): `POST /api/v1/model-quality/versions` (kod sha, katalog sürümü, kural özeti).
- Günlük 08:00: geri bildirim özeti e-postası.

**Kabul testleri**
1. Golden koşusu: sunucuda `PYTHONPATH=backend python3 tests/text2sql/quality-gate.py --report …` → ekranda `table_recall`, `fully_recalled`, `refused` = betiğin stdout/JSON'ındaki değerler (taban 2026-09-08: 1.0 / 39 / 3 ile de karşılaştırılır; fark varsa yeni taban kaydıyla açıklanır).
2. Cevap altını: `answer-gate.py --repeat 3 --report` → `semantic_mq_runs.metrics_json` SAĞLAM/BOZUK/KARARSIZ = betiğin özeti; rastgele 3 SAĞLAM vakanın referans SQL'i doğrudan Logo bağlantısında (`connector_from_file`) koşulup `expected_digest` ile aynı özet.
3. Cevap türü dağılımı: `SELECT answer_type, count(*) FROM sl_query_log WHERE created_at > now() - interval '30 days' GROUP BY answer_type` = Karne «BI soru-cevap» satırındaki dağılım.
4. Eş anlamlı kuyruğu: `SELECT status, count(*) FROM sl_vocabulary GROUP BY status` = kuyruk sekmesindeki sayılar; kuyruktan verilen bir onay sonrası `sl_vocabulary.status='APPROVED'` ve `decided_by` = kişi, ilgili kavramda `explain_json->>'human_certified_by'` dolu.
5. Geri bildirim: deneme oturumuyla bir cevaba «Yanlış + not» → `semantic_mq_feedback` satırı ve `SELECT validated FROM sl_query_log WHERE id = <query_id>` = false; test satırları iş sonunda silinir (AGENTS.md 2026-09-28 kuralı).
6. Çeviri satırı: M4'ün puan formülü (`(1 − ceza/incelenen kelime)×100`; ceza küçük 1 / büyük 5 / kritik 25) doğrudan `semantic_translation_errors` + incelenen segmentlerin kelime sayısıyla SQL'de hesaplanır = karnedeki MQM (kolon adları `editorial_translation.py`'den alınır).
7. Kurulum penceresi: bir koşu sırasında `semantic_mq_versions`'a kayıt düşerse koşu satırında `installs_in_window_json` dolu ve ekranda uyarı.
8. Soru hattı etkilenmedi: geri bildirim düğmesi ve `/api/v1/feedback` genişlemesinden sonra `resolver-gate.py` farksız.

**Bağımlılık:** Yetki A/B/C (var). M48 sürüm kaydıyla (`semantic_itops_releases`) `semantic_mq_versions` birleştirilebilir — M48 önce kodlanırsa onun tablosu okunur, değilse M50 kendi tablosunu yazar (ikisini birden yazmayın; kodlayıcılar tek tabloda anlaşsın: öneri M48'in tablosu + `kind` alanı). Editör isabeti için kart servisine yeni uç + TT GPU nginx beyaz listesine yeni `location` (bellek `tt-gpu-nginx-card-whitelist`) — sonraki sürüm.

**Tahmini büyüklük:** İlk sürüm **L** (betik raporu + 6 tablo + karne + geri bildirim + ekran). Sonraki sürüm (golden yazımı, birleşik kuyruk, editör isabeti, A/B) **L**.
